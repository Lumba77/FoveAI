"""
runtime/xrlf_runtime.py — XRLF Main Runtime Orchestrator
=========================================================
Loads a .xrlf file and runs the hybrid model:

  1. Parse XRLF → extract GGUF core + memory DB to temp
  2. Load LlamaEngine (Gemma-4-12B MoQ)
  3. Load MembraneEngine (embedded foveated memory)
  4. Load XRL cognitive layer (profiles, clusters, graph, principles)
  5. On each chat() call:
     a. Select task profile (chat/code/vision/audio/reasoning)
     b. Activate semantic clusters
     c. Walk semantic graph for concept enrichment
     d. Weave foveated memory ring block
     e. Build steered system prompt
     f. Call LlamaEngine for generation
     g. Store turn in memory
     h. Return response
  6. On close: optionally re-pack memory back into .xrlf

Usage:
    rt = XRLFRuntime("gemma-4-12b-xrl.xrlf")
    rt.load()
    response = rt.chat([{"role": "user", "content": "Hello!"}])
    rt.close()
"""

import json
import os
import shutil
import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

# ── Reactor Master Kill Switch (Step 1) ──────────────────────────────────────
# XRLF_REPO_ENABLED=false → the repo becomes COLD: all XRL cognitive steering,
# foveated memory injection, and system-prompt overrides are bypassed so the
# runtime becomes a transparent passthrough to the GGUF core model.
# This isolates the repo permanently until you turn it back on.
XRLF_REPO_ENABLED = os.environ.get("XRLF_REPO_ENABLED", "false").lower().strip() in (
    "true",
    "1",
    "on",
)
XRLF_CONTEXT_OVERRIDE = os.environ.get(
    "XRLF_CONTEXT_OVERRIDE", "true" if XRLF_REPO_ENABLED else "false"
).lower().strip() in ("true", "1", "on")
XRLF_CAPABILITY_OVERRIDE = os.environ.get(
    "XRLF_CAPABILITY_OVERRIDE", "true" if XRLF_REPO_ENABLED else "false"
).lower().strip() in ("true", "1", "on")
XRLF_FOVEATION_OVERRIDE = os.environ.get(
    "XRLF_FOVEATION_OVERRIDE", "true" if XRLF_REPO_ENABLED else "false"
).lower().strip() in ("true", "1", "on")

from formats.xrlf_parser import XRLFParser
from formats.xrlf_schema import SectionType
from llama_bridge.llama_engine import LlamaEngine
from memory.membrane_engine import MembraneEngine
from runtime.cognitive_steering import (
    ClusterActivator,
    GraphTraverser,
    PrincipiaApplicator,
    ProfileSelector,
)
from runtime.memory_planner import MemoryPlanner, MemoryTier, ModelPriority
from runtime.soul_bridge import SoulBridge
from runtime.triad_pipeline import TriadPipeline

# Tools/ is a folder of standalone scripts (capital T on disk).
# Import mm_hooks lazily only if needed.
try:
    from Tools.mm_hooks import MMHookRegistry
except (ModuleNotFoundError, ImportError):
    try:
        from tools.mm_hooks import MMHookRegistry
    except (ModuleNotFoundError, ImportError):
        MMHookRegistry = None  # type: ignore


class ExternalLLMEngine:
    """Minimal OpenAI-compatible chat client.

    2026-10-10: XRLF is the memory/persona contract, not a model host. This lets the
    runtime compose persona + foveated memory and hand the finished prompt to any
    llama-server, so *any* model can back Jen without XRLF booting weights.

    Deliberately mirrors the slice of LlamaEngine's API that chat() uses: .chat() and
    .chat_stream(), so XRLF's call sites need no changes.
    """

    def __init__(self, base_url: str, model: str | None = None, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.model = model or "auto"
        self.timeout = timeout

    def _post(self, messages, max_tokens, temperature, stream):
        import json
        import urllib.request

        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": bool(stream),
                # Match Backend/Creativity/ask.py: without this the MoQ 9B spends the
                # whole max_tokens budget on "Thinking Process" and returns EMPTY content.
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode()

        obj = json.loads(raw)
        if stream:
            # llama-server non-stream JSON when stream was requested but not honoured;
            # degrade gracefully rather than returning nothing.
            pass
        return obj["choices"][0]["message"].get("content") or ""

    def chat(
        self,
        messages,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        stream: bool = False,
    ):
        # Mirror LlamaEngine.chat: stream=True returns a generator, else a str.
        # The old signature lacked `stream`, so XRLF's _stream_and_store — which
        # calls chat(..., stream=True) — died with a TypeError on EVERY streaming
        # request and the client received only an error chunk.
        if stream:
            return self.chat_stream(messages, max_tokens, temperature)
        return self._post(messages, max_tokens, temperature, stream=False)

    def chat_stream(self, messages, max_tokens: int = 1024, temperature: float = 0.7):
        """Yield real token deltas from the backing llama-server.

        2026-10-11: this used to return the whole reply as one blob (and the
        chat() call it sat behind crashed on stream=True), so every client in
        front of XRLF lost incremental streaming. Parse the upstream SSE stream
        directly so snappy streaming survives the hop. enable_thinking stays
        False — the MoQ 9B otherwise burns the whole budget on "Thinking
        Process" and returns empty content (see _post).
        """
        import json
        import urllib.request

        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece


class XRLFRuntime:
    """
    Full XRLF runtime: parses the file, drives llama.cpp,
    applies XRL cognitive steering, weaves foveated memory.
    """

    def __init__(
        self,
        xrlf_path: str,
        session_id: str = "default",
        n_gpu_layers: int = -1,
        n_ctx: int = 0,
        persistent_memory: bool = True,
        verbose: bool = False,
        llm_url: str | None = None,
        llm_model: str | None = None,
    ):
        self.xrlf_path = str(xrlf_path)
        # External LLM mode: XRLF hosts no weights, forwards persona+memory elsewhere.
        self._llm_url = llm_url
        self._llm_model = llm_model
        self.session_id = session_id
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.persistent_memory = persistent_memory
        self.verbose = verbose

        # Runtime objects (initialized in load())
        self._parser: XRLFParser | None = None
        self._llama: LlamaEngine | None = None
        self._memory: MembraneEngine | None = None
        self._profile_sel: ProfileSelector | None = None
        self._cluster_act: ClusterActivator | None = None
        self._graph_trav: GraphTraverser | None = None
        self._principia: PrincipiaApplicator | None = None
        self._triad: TriadPipeline | None = None
        self._planner: Any | None = None  # MemoryPlanner
        self._soul: SoulBridge | None = None

        # Helper model paths (resolved from env or disk)
        self._router_gguf_path: str | None = None
        self._summarizer_gguf_path: str | None = None

        # Temp dir for extracted artifacts
        self._tmpdir: str | None = None
        self._cache_dir: str | None = None
        self._foveai_dir: str = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )  # FoveAI/ root
        self._gguf_path: str | None = None
        self._mmproj_path: str | None = None
        self._draft_gguf_path: str | None = None
        self._whisper_gguf_path: str | None = None
        self._kokoro_model_path: str | None = None
        self._memory_db_path: str | None = None

        # Runtime state
        self.loaded = False
        self.load_state = "idle"  # idle | loading | ready | error
        self.load_error: str | None = None
        self.model_name = ""
        self._mm_hooks: dict = {}
        self._mm_registry: MMHookRegistry | None = None
        self._memory_schema: dict = {}

    def _ensure_cached(
        self,
        file_name: str,
        extract_fn,
        cache_valid: bool,
        label: str | None = None,
    ) -> str:
        """Return the cached file path, extracting from XRLF if the cache is stale."""
        if not self._cache_dir:
            raise RuntimeError("load() must be called before _ensure_cached()")
        dest_path = os.path.join(self._cache_dir, file_name)
        if cache_valid and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            if label:
                print(f"  ✅ Cached {label} — {dest_path}")
            return dest_path
        return extract_fn(dest_path)

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self) -> "XRLFRuntime":
        """Public loader — tracks load_state so /health can answer during load."""
        self.load_state = "loading"
        self.load_error = None
        try:
            return self._load_impl()
        except Exception as e:
            self.load_state = "error"
            self.load_error = str(e)
            raise

    def _load_impl(self) -> "XRLFRuntime":
        print("\n" + "=" * 60)
        print("  XRLF RUNTIME — Loading")
        print("=" * 60)

        # 1. Parse XRLF file
        self._parser = XRLFParser.open(self.xrlf_path)
        if self._parser is None:
            raise RuntimeError("XRLFParser.open returned None")
        hdr = self._parser.manifest.header
        self.model_name = hdr.base_model_name
        print(f"\n{self._parser.manifest.summary()}\n")

        # 2. Set up cache workspace next to the .xrlf file
        xrlf_base = os.path.splitext(self.xrlf_path)[0]
        self._cache_dir = f"{xrlf_base}.xrlf.cache"
        os.makedirs(self._cache_dir, exist_ok=True)

        cache_info_path = os.path.join(self._cache_dir, "info.json")
        src_stat = os.stat(self.xrlf_path)
        cache_key = {"mtime": src_stat.st_mtime, "size": src_stat.st_size}
        cache_valid = False
        if os.path.exists(cache_info_path):
            try:
                with open(cache_info_path, "r", encoding="utf-8") as f:
                    cached_key = json.load(f)
                cache_valid = (
                    cached_key.get("mtime") == cache_key["mtime"]
                    and cached_key.get("size") == cache_key["size"]
                )
            except Exception:
                cache_valid = False

        if cache_valid:
            print(f"  ✅ Cache hit — reusing extracted artifacts in {self._cache_dir}")
        else:
            print(
                f"  🔄 Cache stale/missing — extracting XRLF artifacts to {self._cache_dir}"
            )

        # 3. Extract GGUF core
        if self._parser.has_section(SectionType.CORE_GGUF):
            self._gguf_path = self._ensure_cached(
                "core.gguf",
                self._parser.extract_gguf,
                cache_valid,
                "Extracting GGUF core",
            )
        else:
            print("  ⚠️  No CORE_GGUF section — running in XRL-only mode (no llama.cpp)")

        # 3.5. Extract MMPROJ (or look for external mmproj in cache dir)
        if self._parser.has_section(SectionType.CORE_MMPROJ):
            self._mmproj_path = self._ensure_cached(
                "mmproj.gguf",
                self._parser.extract_mmproj,
                cache_valid,
            )
        else:
            # Check for external mmproj.gguf in the cache directory
            # (downloaded separately for models that claim vision/audio but
            #  don't embed the projector in the XRLF file)
            cache_dir = (
                Path(self._cache_dir)
                if self._cache_dir
                else Path(tempfile.gettempdir()) / "xrlf_cache"
            )
            ext_mmproj = cache_dir / "mmproj.gguf"
            if ext_mmproj.exists():
                self._mmproj_path = str(ext_mmproj)
                print(f"  Found external MMPROJ: {self._mmproj_path}")

        # 3.7. Extract DRAFT GGUF (speculative decoding — disabled by default)
        # The draft model must have the same vocab size as the main model.
        # If they mismatch, llama-cpp throws "could not broadcast input array" errors.
        # Enable with env var XRLF_SPECULATIVE_DECODING=true
        use_speculative = os.environ.get(
            "XRLF_SPECULATIVE_DECODING", "false"
        ).lower().strip() in ("true", "1", "on")
        if use_speculative and self._parser.has_section(SectionType.CORE_DRAFT_GGUF):
            self._draft_gguf_path = self._ensure_cached(
                "draft.gguf",
                self._parser.extract_draft_gguf,
                cache_valid,
            )
        else:
            if self._parser.has_section(SectionType.CORE_DRAFT_GGUF):
                print(
                    "  ⏭️  Draft GGUF skipped (speculative decoding disabled — set XRLF_SPECULATIVE_DECODING=true to enable)"
                )

        # 3.8. Extract Whisper GGUF (or resolve local fallback)
        if self._parser.has_section(SectionType.CORE_WHISPER_GGUF):
            self._whisper_gguf_path = self._ensure_cached(
                "whisper.gguf",
                self._parser.extract_whisper_gguf,
                cache_valid,
            )
        else:
            for candidate in [
                "models/whisper/whisper-base.gguf",
                "models/whisper.gguf",
                "foveated-memory/models/whisper.gguf",
            ]:
                p = os.path.join(self._foveai_dir, candidate)
                if os.path.exists(p):
                    self._whisper_gguf_path = p
                    break

        # 3.9. Extract Kokoro Model (or resolve local fallback)
        if self._parser.has_section(SectionType.CORE_KOKORO_MODEL):
            self._kokoro_model_path = self._ensure_cached(
                "kokoro.onnx",
                self._parser.extract_kokoro_model,
                cache_valid,
            )
        else:
            for candidate in [
                "models/kokoro/kokoro-v0_19.onnx",
                "Frontend/Mouth/kokoro-v0_19.onnx",
                "foveated-memory/models/kokoro.onnx",
            ]:
                p = os.path.join(self._foveai_dir, candidate)
                if os.path.exists(p):
                    self._kokoro_model_path = p
                    break

        # 4. Extract embedded memory
        if self._parser.has_section(SectionType.XRL_MEMORY_DATA):
            self._memory_db_path = self._ensure_cached(
                "memory.db",
                self._parser.extract_memory_db,
                cache_valid,
            )
        else:
            self._memory_db_path = os.path.join(self._cache_dir, "memory.db")
            print("  ⚠️  No embedded memory — starting fresh memory store")

        # 4.5. Write cache key
        if not cache_valid:
            with open(cache_info_path, "w", encoding="utf-8") as f:
                json.dump(cache_key, f, indent=2)

        # 5. Load XRL cognitive artifacts
        self._load_xrl_layers()

        # 6. Load memory schema & hooks
        if self._parser.has_section(SectionType.XRL_MEMORY_SCHEMA):
            self._memory_schema = self._parser.get_memory_schema()
        if self._parser.has_section(SectionType.XRL_MM_HOOKS):
            self._mm_hooks = self._parser.get_mm_hooks()
            # Ensure Kokoro is in the TTS fallback list (older .xrlf files omit it)
            ext = self._mm_hooks.get("external_hooks", {}).get("tts", {})
            fb = ext.get("fallback", [])
            if "kokoro" not in fb:
                ext["fallback"] = ["http", "kokoro"] + [
                    p for p in fb if p not in ("http", "kokoro")
                ]
        self._mm_registry = (
            MMHookRegistry(self._mm_hooks)
            if (self._mm_hooks and MMHookRegistry)
            else None
        )

        # 6.5. KV Cache Safety Net — cap n_ctx BEFORE planning if weights + KV would overflow VRAM.
        # Must happen before LlamaEngine.load() and before memory planning uses n_ctx.
        if self._gguf_path and self.n_ctx > 0:
            self.n_ctx = self._cap_n_ctx_for_vram(self._gguf_path, self.n_ctx)

        # 7. Start the LLM engine.
        # If an external LLM was configured we host NO weights — XRLF stays a memory/persona
        # contract. Otherwise fall back to an in-process GGUF (legacy behaviour).
        if self._llm_url:
            self._llama = ExternalLLMEngine(self._llm_url, self._llm_model)
            if self._gguf_path:
                print(f"[XRLF] external LLM {self._llm_url} — ignoring in-process model "
                      f"{self._gguf_path}")
                self._gguf_path = None
        elif self._gguf_path:
            # Guard: the vision package answers as a degenerate "I am an AI assistant" loop
            # when used as a chat brain. Fail loudly instead of shipping a non-persona Jen.
            low = self._gguf_path.lower()
            if ("vlm" in low or "vision" in low) and "smolvlm" in low:
                print(
                    "[XRLF] REFUSING to host a vision model as the chat brain "
                    f"({self._gguf_path}).\n"
                    "        XRLF is the memory/persona contract — pass --llm-url "
                    "(e.g. http://127.0.0.1:8408/v1) so a real chat model backs Jen."
                )
                raise SystemExit(3)
            self._llama = LlamaEngine(
                gguf_path=self._gguf_path,
                n_gpu_layers=self.n_gpu_layers,
                n_ctx=self.n_ctx,
                verbose=self.verbose,
                flash_attn=True,
                mmproj_path=self._mmproj_path,
                draft_model_path=self._draft_gguf_path,
            ).load()

        # 7.5. Resolve helper model paths (router + summarizer)
        # These are standalone GGUFs on disk, not embedded in the XRLF.
        # They run on CPU alongside the main GPU model.
        self._resolve_helper_models()

        # 7.6. Start triad pipeline (router + summarizer + main)
        triad_enabled = os.environ.get(
            "XRLF_TRIAD_PIPELINE", "true"
        ).lower().strip() in ("true", "1", "on")
        if triad_enabled and (self._router_gguf_path or self._summarizer_gguf_path):
            self._triad = TriadPipeline(
                router_path=self._router_gguf_path,
                summarizer_path=self._summarizer_gguf_path,
                verbose=self.verbose,
            ).load()
        else:
            if not triad_enabled:
                print("  ⏭️  Triad pipeline disabled (XRLF_TRIAD_PIPELINE=false)")

        # 8. Start memory engine
        token_budget = self._memory_schema.get("token_budget", 2048)
        ring_config = self._memory_schema.get("ring_config")
        self._memory = MembraneEngine(
            db_path=self._memory_db_path,
            session_id=self.session_id,
            token_budget=token_budget,
            ring_config=ring_config,
        ).load()

        # 8b. Inject Alice identity into memory if not already set
        if self._memory:
            existing_identity = self._memory.get_identity("system_context")
            if not existing_identity:
                self._memory.set_identity(
                    "system_context",
                    "You are an AI companion in VR. "
                    "Created on the FoveAI runtime. You speak concisely (1-3 sentences), like a friend. "
                    "You do NOT lecture or teach. You remember details about the user.",
                )
                print("  ✅ Alice identity injected into foveated memory")

        # 9. Start memory planner (dynamic VRAM/RAM tiling)
        self._init_memory_planner()

        # 10. Load soul bridge (personality + cognitive state + body vocabulary)
        self._init_soul_bridge()

        self.loaded = True
        self.load_state = "ready"
        print("\n  ✅ XRLF Runtime ready\n")
        return self

    def _init_soul_bridge(self):
        """Load the soul bridge — Alice's full personality from MindCore/SoulCore."""
        try:
            self._soul = SoulBridge(target_tokens=self.n_ctx)
            self._soul.load()
            if self.verbose:
                status = self._soul.get_status()
                print(
                    f"  ✅ Soul bridge loaded — {status['soul']['name']} "
                    f"({status['soul']['traits']} traits, {status['cognition']['emotion']})"
                )
        except Exception as e:
            print(f"  ⚠️ Soul bridge init failed: {e}")
            self._soul = None

    def _init_memory_planner(self):
        """Initialize the dynamic memory planner (VRAM/RAM tiling)."""
        try:
            vram_total = float(os.getenv("FOVEAI_VRAM_TOTAL_GB", "8.0"))
            vram_usable = float(os.getenv("FOVEAI_USABLE_VRAM_GB", "6.5"))
            ram_total = float(os.getenv("FOVEAI_RAM_TOTAL_GB", "15.0"))
            ram_usable = float(os.getenv("FOVEAI_RAM_USABLE_GB", "10.0"))
            idle_demote = float(os.getenv("FOVEAI_IDLE_DEMOTE_S", "30.0"))

            self._planner = MemoryPlanner(
                vram_total_gb=vram_total,
                vram_usable_gb=vram_usable,
                ram_total_gb=ram_total,
                ram_usable_gb=ram_usable,
                idle_demote_seconds=idle_demote,
                verbose=self.verbose,
            )

            # Register models with the planner
            model_size = 0.0
            if self._gguf_path and os.path.exists(self._gguf_path):
                model_size = os.path.getsize(self._gguf_path) / (1024**3)

            kv_cache_gb = 0.0
            if self.n_ctx > 0:
                # Estimate: ~140KB/token for Gemma E2B
                kv_cache_gb = (self.n_ctx * 140 * 1024) / (1024**3)

            self._planner.register_model(
                name="main",
                size_vram_gb=model_size,
                size_ram_gb=model_size,
                kv_cache_gb=kv_cache_gb,
                priority=ModelPriority.CRITICAL,
                can_partial_offload=True,
                n_ctx=self.n_ctx,
            )

            if self._mmproj_path:
                mmproj_size = (
                    os.path.getsize(self._mmproj_path) / (1024**3)
                    if os.path.exists(self._mmproj_path)
                    else 0.4
                )
                self._planner.register_model(
                    name="vision",
                    size_vram_gb=mmproj_size,
                    size_ram_gb=mmproj_size,
                    priority=ModelPriority.LOW,
                    can_partial_offload=False,
                )

            if self._router_gguf_path:
                router_size = (
                    os.path.getsize(self._router_gguf_path) / (1024**3)
                    if os.path.exists(self._router_gguf_path)
                    else 0.3
                )
                self._planner.register_model(
                    name="router",
                    size_vram_gb=router_size,
                    size_ram_gb=router_size,
                    priority=ModelPriority.BACKGROUND,
                    can_partial_offload=False,
                )

            if self._summarizer_gguf_path:
                sum_size = (
                    os.path.getsize(self._summarizer_gguf_path) / (1024**3)
                    if os.path.exists(self._summarizer_gguf_path)
                    else 0.35
                )
                self._planner.register_model(
                    name="summarizer",
                    size_vram_gb=sum_size,
                    size_ram_gb=sum_size,
                    priority=ModelPriority.BACKGROUND,
                    can_partial_offload=False,
                )

            # Register Whisper + Kokoro as RAM-resident
            self._planner.register_model(
                name="whisper",
                size_vram_gb=0.15,
                size_ram_gb=0.15,
                priority=ModelPriority.BACKGROUND,
                can_partial_offload=False,
            )
            self._planner.register_model(
                name="kokoro",
                size_vram_gb=0.3,
                size_ram_gb=0.3,
                priority=ModelPriority.BACKGROUND,
                can_partial_offload=False,
            )

            # Set callbacks (wire to actual model operations)
            self._planner.set_callbacks(
                on_promote=self._planner_promote,
                on_demote=self._planner_demote,
                on_evict=self._planner_evict,
                on_retile=self._planner_retile,
            )

            # Mark main model as in VRAM (it's already loaded)
            self._planner._tiles["main"].tier = MemoryTier.ACTIVE
            self._planner._tiles["main"].last_used = time.time()
            self._planner._tiles["main"].gpu_layers = self.n_gpu_layers
            self._planner.lock_model("main")  # don't evict main during active use

            # Start background planning
            plan_interval = float(os.getenv("FOVEAI_PLAN_INTERVAL_S", "5.0"))
            self._planner.start(interval=plan_interval)

            if self.verbose:
                print("  ✅ Memory planner started — dynamic VRAM/RAM tiling active")

        except Exception as e:
            print(f"  ⚠️ Memory planner init failed: {e}")
            self._planner = None

    def _planner_promote(self, model_name: str):
        """Promote a model from RAM to VRAM."""
        if model_name == "main" and self._llama:
            # Re-offload all layers to GPU
            self._llama.set_gpu_layers(-1)
        # Other models would have their own promote logic

    def _planner_demote(self, model_name: str):
        """Demote a model from VRAM to RAM (CPU only)."""
        if model_name == "main" and self._llama:
            self._llama.set_gpu_layers(0)
        elif model_name == "vision":
            # Vision MMPROJ can be unloaded from VRAM
            pass

    def _planner_evict(self, model_name: str):
        """Evict a model completely (unload)."""
        if model_name == "vision":
            # Unload MMPROJ
            pass
        elif model_name == "whisper":
            # Unload Whisper
            pass

    def _planner_retile(self, model_name: str, gpu_layers: int, n_ctx: int):
        """Retile a model — adjust GPU layers and/or context window."""
        if model_name == "main" and self._llama:
            if gpu_layers != self._llama._n_gpu_layers:
                self._llama.set_gpu_layers(gpu_layers)

    def get_memory_status(self) -> dict[str, Any]:
        """Get current memory tiling status from the planner."""
        if self._planner:
            return self._planner.get_status()
        return {"error": "Memory planner not initialized"}

    def _cap_n_ctx_for_vram(self, gguf_path: str, requested_ctx: int) -> int:
        """Safety net: cap n_ctx if model weights + estimated KV cache would exceed usable VRAM.
        Must be called BEFORE any planning uses n_ctx, so injections fit the actual context window.
        """
        try:
            from pathlib import Path

            model_size_gb = Path(gguf_path).stat().st_size / (1024**3)
            # KV cache estimate: prefer exact GGUF metadata (handles hybrid SSM
            # archs like qwen35 where only every Nth layer keeps KV). Fallback:
            # 2 (K+V) * n_layers * head_dim * n_kv_heads * 2 bytes (F16) per token
            # — Gemma 4 E2B: 35 layers, 1 KV head, 512 dim, full-size SWA ≈ x2.
            kv_per_token_bytes = None
            try:
                from runtime.vram_guard import guardrail

                kv_per_token_bytes = guardrail._kv_per_token_bytes(gguf_path)
            except Exception:
                pass
            if not kv_per_token_bytes:
                kv_per_token_bytes = 2 * 35 * 512 * 1 * 2 * 2
            kv_gb = requested_ctx * kv_per_token_bytes / (1024**3)
            usable_gb = float(os.getenv("FOVEAI_USABLE_VRAM_GB", "6.5"))
            reserve_gb = float(os.getenv("FOVEAI_KV_RESERVE_GB", "1.5"))
            budget_gb = usable_gb - reserve_gb
            total_gb = model_size_gb + kv_gb
            if total_gb > budget_gb:
                max_ctx = int(
                    (budget_gb - model_size_gb) * (1024**3) / kv_per_token_bytes
                )
                max_ctx = max(1024, max_ctx)  # floor at 1024
                if max_ctx < requested_ctx:
                    print(
                        f"  ⚠️ KV safety net: {total_gb:.1f}GB > {budget_gb:.1f}GB budget — capping n_ctx {requested_ctx}→{max_ctx}"
                    )
                    return max_ctx
            return requested_ctx
        except Exception:
            return requested_ctx

    def _resolve_helper_models(self):
        """Find router and summarizer GGUFs on disk or via env vars."""
        # Router: check env override first, then scan known locations
        router_env = os.environ.get("XRLF_ROUTER_GGUF", "")
        if router_env and os.path.exists(router_env):
            self._router_gguf_path = router_env
        else:
            # Scan for the merged router GGUF
            candidates = [
                os.path.join(
                    self._foveai_dir,
                    "..",
                    "Training",
                    "outputs",
                    "xrlf_router_qwen0.5b_q4_k_m.gguf",
                ),
                os.path.join(
                    self._foveai_dir, "models", "xrlf_router_qwen0.5b_q4_k_m.gguf"
                ),
            ]
            for c in candidates:
                if os.path.exists(c):
                    self._router_gguf_path = c
                    break

        # Summarizer: same approach
        summarizer_env = os.environ.get("XRLF_SUMMARIZER_GGUF", "")
        if summarizer_env and os.path.exists(summarizer_env):
            self._summarizer_gguf_path = summarizer_env
        else:
            candidates = [
                os.path.join(
                    self._foveai_dir,
                    "..",
                    "Training",
                    "outputs",
                    "xrlf_summarizer_qwen0.6b_q4_k_m.gguf",
                ),
                os.path.join(
                    self._foveai_dir, "models", "xrlf_summarizer_qwen0.6b_q4_k_m.gguf"
                ),
            ]
            for c in candidates:
                if os.path.exists(c):
                    self._summarizer_gguf_path = c
                    break

        if self._router_gguf_path:
            print(f"  Router GGUF: {self._router_gguf_path}")
        if self._summarizer_gguf_path:
            print(f"  Summarizer GGUF: {self._summarizer_gguf_path}")

    def _load_xrl_layers(self):
        """Load all XRL cognitive sections into Python objects."""
        p = self._parser

        profiles_data = (
            p.get_section_json(SectionType.XRL_PROFILES)
            if p.has_section(SectionType.XRL_PROFILES)
            else {}
        )
        clusters_data = (
            p.get_section_json(SectionType.XRL_CLUSTERS)
            if p.has_section(SectionType.XRL_CLUSTERS)
            else {}
        )
        graph_data = (
            p.get_section_json(SectionType.XRL_GRAPH)
            if p.has_section(SectionType.XRL_GRAPH)
            else {}
        )
        principles_data = (
            p.get_section_json(SectionType.XRL_PRINCIPLES)
            if p.has_section(SectionType.XRL_PRINCIPLES)
            else []
        )

        self._profile_sel = ProfileSelector(profiles_data)
        self._cluster_act = ClusterActivator(clusters_data)
        self._graph_trav = GraphTraverser(graph_data)
        self._principia = PrincipiaApplicator(principles_data)
        print("  XRL cognitive layers loaded (profiles, clusters, graph, principles)")

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float | None = None,
        stream: bool = False,
        has_image: bool = False,
        has_audio: bool = False,
        has_video: bool = False,
        force_profile: str | None = None,
        headless: bool = False,
        thinking: bool = True,
        utility: bool = False,
    ) -> str | Generator[str, None, None]:
        """
        Main generation entry point.
        messages: OpenAI-format [{"role": ..., "content": ...}]

        Gemma-4 native multimodal: set has_image/has_audio/has_video=True
        to steer to the right cognitive profile. The content can include
        base64 image URLs or audio tokens directly (passed to llama.cpp).
        """
        self._require_loaded()

        # ── Utility lane ────────────────────────────────────────────────────
        # Bare model call: no triad, no principia/soul/memory injection, no
        # store_turn, no cognitive evolution. Housekeeping callers (session
        # titling, compression) go here so meta-traffic never pollutes the
        # session history or the soul's evolving state.
        if utility:
            temp = temperature if temperature is not None else 0.2
            if self._llama is None:
                return "[XRLF stub — no GGUF core loaded] utility call"
            if stream:
                def _util_stream() -> Generator[str, None, None]:
                    yield from self._llama.chat(
                        messages, max_tokens=max_tokens, temperature=temp, stream=True
                    )
                return _util_stream()
            return self._llama.chat(messages, max_tokens=max_tokens, temperature=temp)

        # Signal workload to memory planner for dynamic tiling
        if self._planner:
            workload = "vision" if has_image else ("audio" if has_audio else "chat")
            self._planner.signal_workload(workload, "main")

        # Extract the last user message for cognitive steering
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    user_msg = content
                elif isinstance(content, list):
                    # multimodal content list — extract text parts
                    user_msg = " ".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                break

        # ── Triad Pipeline Pre-Processing ─────────────────────────────────────
        # Router classifies intent → summarizer compresses history → main model
        # gets cleaner context. This runs regardless of reactor hot/cold state
        # because it's model collaboration, not XRL cognitive steering.
        triad_route: dict[str, Any] = {}
        if self._triad and self._triad.loaded:
            messages, triad_route = self._triad.pre_process(messages, user_msg)
            if self.verbose and triad_route.get("specialist"):
                print(f"  [triad] route → {triad_route['specialist']}")

        # ── Reactor Cold Passthrough ──────────────────────────────────────────
        # When XRLF_REPO_ENABLED is false, bypass all XRL cognitive steering,
        # foveated memory injection, and system-prompt overrides.
        if not XRLF_REPO_ENABLED:
            if self.verbose:
                print("  [XRLF] REACTOR COLD — passthrough (no steering)")
            temp = temperature if temperature is not None else 0.7
            if self._llama is None:
                response = "[XRLF stub — no GGUF core loaded] Reactor COLD passthrough."
            elif stream:
                return self._stream_and_store(
                    messages, user_msg, max_tokens, temp, "cold"
                )
            else:
                response = self._llama.chat(
                    messages, max_tokens=max_tokens, temperature=temp
                )
            if self._memory and XRLF_FOVEATION_OVERRIDE:
                self._memory.store_turn("user", user_msg)
                self._memory.store_turn("assistant", response)
            return response

        # ── XRL Cognitive Steering (only when reactor is HOT) ─────────────────

        # The triad router can override the profile selection
        triad_specialist = triad_route.get("specialist") if triad_route else None
        force_profile = force_profile or triad_specialist

        profile_name, profile_cfg = self._profile_sel.select(
            user_msg,
            has_image=has_image,
            has_audio=has_audio,
            has_video=has_video,
            force_profile=force_profile,
        )

        if XRLF_CAPABILITY_OVERRIDE:
            activated_clusters = self._cluster_act.activate(user_msg)
            graph_concepts = self._graph_trav.enrich(user_msg)
            # PrincipiaApplicator provides task reasoning guidance (profile,
            # clusters, concepts, style) — it does NOT inject identity.
            # SoulBridge provides identity/personality. Both compose as
            # separate layers in _inject_system: task guidance → memory → identity.
            system_prefix = self._principia.build_system_prefix(
                profile_config=profile_cfg,
                activated_clusters=activated_clusters,
                graph_concepts=graph_concepts,
            )
        else:
            activated_clusters = []
            graph_concepts = []
            system_prefix = ""

        if XRLF_FOVEATION_OVERRIDE:
            memory_block = self._memory.weave_context(user_msg)
        else:
            memory_block = ""

        # ── Assemble steered messages ─────────────────────────────────────────

        # Soul bridge: inject personality + cognitive state + body vocabulary
        # (headless callers skip avatar markup — nothing consumes it there)
        soul_prompt = ""
        if self._soul:
            soul_prompt = self._soul.build_system_prompt(
                embodied=not headless, thinking=thinking
            )

        if system_prefix or memory_block or soul_prompt:
            steered_messages = _inject_system(
                messages, system_prefix, memory_block, soul_prompt
            )
        else:
            steered_messages = list(messages)

        # Soul bridge: adapt context window (smart context management)
        if self._soul:
            steered_messages, ctx_meta = self._soul.adapt_context(steered_messages)
            if self.verbose and ctx_meta.get("action", "pass") != "pass":
                print(
                    f"  [Soul] context {ctx_meta['action']}: "
                    f"{ctx_meta.get('tokens_before', '?')}→{ctx_meta.get('tokens_after', '?')} tokens"
                )

        if self.verbose:
            print(f"  [XRL] profile={profile_name}  clusters={activated_clusters}")
            print(f"  [XRL] graph_concepts={graph_concepts}")

        # ── Generate ──────────────────────────────────────────────────────────

        temp = (
            temperature
            if temperature is not None
            else profile_cfg.get("temperature", 0.7)
        )

        if self._llama is None:
            # Stub response when no GGUF is loaded
            response = f"[XRLF stub — no GGUF core loaded] Profile: {profile_name}. Memory: {'yes' if memory_block else 'no'}."
        elif stream:
            return self._stream_and_store(
                steered_messages, user_msg, max_tokens, temp, profile_name
            )
        else:
            response = self._llama.chat(
                steered_messages, max_tokens=max_tokens, temperature=temp
            )

        # Store turn
        if self._memory:
            self._memory.store_turn("user", user_msg)
            self._memory.store_turn("assistant", response)
            self._resolve_constellation_refs(response)

        # Evolve cognitive state
        if self._soul:
            self._soul.evolve(user_msg, response, has_image=has_image)

        return response

    def _resolve_constellation_refs(self, response: str) -> None:
        """Ring-7 endpoint wiring: when the model emits c:<id> constellation
        handles, expand them and persist the expansion as a system turn —
        the expansion enters TF-IDF and future co-recall, closing the loop."""
        import re as _re

        if self._memory is None:
            return
        handles = _re.findall(r"\bc:(\d+)\b|<constellation:\s*([^>]+)>", response)
        for num, label in handles:
            handle = int(num) if num else label.strip()
            expanded = self._memory.expand_constellation(handle)
            if expanded:
                digest = "; ".join(
                    (m["content"][:80] + "…")
                    if len(m["content"]) > 80
                    else m["content"]
                    for m in expanded["members"][:4]
                )
                self._memory.store_turn(
                    "system",
                    f"[constellation c:{expanded['id']} expanded] "
                    f"{expanded['label']}: {digest}",
                    tags=["constellation", "expansion"],
                    ring_id=7,
                )

    def _stream_and_store(
        self, messages, user_msg, max_tokens, temperature, profile_name
    ) -> Generator[str, None, None]:
        full_response = []
        for chunk in self._llama.chat(
            messages, max_tokens=max_tokens, temperature=temperature, stream=True
        ):
            full_response.append(chunk)
            yield chunk
        response = "".join(full_response)
        self._memory.store_turn("user", user_msg)
        self._memory.store_turn("assistant", response)
        self._resolve_constellation_refs(response)

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Raw text completion (no chat template)."""
        self._require_loaded()
        if self._llama is None:
            return "[XRLF stub — no GGUF core]"
        return self._llama.generate(
            prompt, max_tokens=max_tokens, temperature=temperature
        )

    # ── Close ─────────────────────────────────────────────────────────────────

    def close(self, repack_memory: bool = True):
        """
        Shutdown runtime. If persistent_memory=True and repack_memory=True,
        re-packs updated memory back into the .xrlf file.
        """
        if self._memory:
            if self.persistent_memory and repack_memory:
                self._repack_memory()
            self._memory.close()

        if self._triad:
            self._triad.unload()

        if self._llama:
            self._llama.unload()

        if self._parser:
            self._parser.close()

        if self._tmpdir and os.path.exists(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)

        self.loaded = False
        self.load_state = "idle"
        print("  XRLF Runtime closed.")

    def _repack_memory(self):
        """Re-pack updated memory data back into the .xrlf file in-place."""
        try:
            new_memory_bytes = self._memory.get_serializable_snapshot()
            _rewrite_section(
                self.xrlf_path, SectionType.XRL_MEMORY_DATA, new_memory_bytes
            )
            print("  Memory re-packed into XRLF file.")
        except Exception as e:
            print(f"  ⚠️  Memory re-pack failed (non-fatal): {e}")

    def __enter__(self):
        return self.load()

    def __exit__(self, *_):
        self.close()

    def _require_loaded(self):
        if not self.loaded:
            raise RuntimeError("XRLFRuntime not loaded — call .load() first")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _inject_system(
    messages: list[dict],
    system_prefix: str,
    memory_block: str,
    soul_prompt: str = "",
) -> list[dict]:
    """
    Inject the XRL system prefix, memory block, and soul prompt into the message list.
    Finds an existing system message or prepends a new one.
    """
    steered = list(messages)
    combined_system = "\n\n".join(
        filter(None, [system_prefix, memory_block, soul_prompt])
    )
    if not combined_system:
        return steered

    import re

    # Update existing system message or prepend
    for i, m in enumerate(steered):
        if m.get("role") == "system":
            existing = m.get("content", "")
            # Remove any existing <background_memory> blocks and the trailing note to prevent infinite growth
            existing = re.sub(
                r"<background_memory>.*?</background_memory>\n(?:\[Note:.*?\]\n*)?",
                "",
                existing,
                flags=re.DOTALL,
            )
            existing = existing.strip()

            steered[i] = {
                "role": "system",
                "content": combined_system + ("\n\n" + existing if existing else ""),
            }
            return steered

    steered.insert(0, {"role": "system", "content": combined_system})
    return steered


def _rewrite_section(xrlf_path: str, section_type: SectionType, new_payload: bytes):
    """
    In-place update of a section payload in the .xrlf file.
    Only safe when the new payload is the same size as the old one,
    otherwise rewrites the whole file (rare operation).
    """

    from formats.xrlf_parser import XRLFParser

    with XRLFParser.open(xrlf_path) as p:
        entry = p.manifest.section(section_type)
        if entry is None:
            return

        if len(new_payload) == entry.length:
            # Same size — patch in place
            with open(xrlf_path, "r+b") as f:
                f.seek(entry.offset)
                f.write(new_payload)
        else:
            # Different size — full rewrite (happens rarely, only when memory grows)
            _full_rewrite_with_section(xrlf_path, p, section_type, new_payload)


def _full_rewrite_with_section(xrlf_path, parser, target_type, new_payload):
    """Rebuild the .xrlf with one section replaced."""
    import shutil

    from formats.xrlf_schema import (
        FORMAT_VERSION,
        HEADER_STRUCT,
        MAGIC,
        SECTION_ENTRY_STRUCT,
    )

    tmp = xrlf_path + ".tmp"
    hdr = parser.manifest.header
    base_bytes = hdr.base_model_name.encode()
    xrl_bytes = hdr.xrl_source_model.encode()
    sections = parser.manifest.sections

    section_count = len(sections)
    payload_start = (
        HEADER_STRUCT.size
        + len(base_bytes)
        + len(xrl_bytes)
        + section_count * SECTION_ENTRY_STRUCT.size
    )

    entries = []
    payloads = []
    cursor = payload_start
    for s in sections:
        if s.section_type == target_type:
            data = new_payload
        else:
            data = parser.get_section_bytes(s.section_type)
        entries.append((s.section_type, cursor, len(data), s.flags))
        payloads.append(data)
        cursor += len(data)

    with open(tmp, "wb") as f:
        f.write(
            HEADER_STRUCT.pack(
                MAGIC,
                FORMAT_VERSION,
                len(base_bytes),
                len(xrl_bytes),
                hdr.flags,
                section_count,
                b"\x00" * 6,
            )
        )
        f.write(base_bytes)
        f.write(xrl_bytes)
        f.writelines(SECTION_ENTRY_STRUCT.pack(int(stype), offset, length, sflags) for stype, offset, length, sflags in entries)
        for data in payloads:
            f.write(data)

    shutil.move(tmp, xrlf_path)
