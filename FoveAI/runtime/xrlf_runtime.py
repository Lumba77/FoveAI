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
    ):
        self.xrlf_path = str(xrlf_path)
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

        # 7. Start llama engine
        if self._gguf_path:
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

        self.loaded = True
        print("\n  ✅ XRLF Runtime ready\n")
        return self

    def _cap_n_ctx_for_vram(self, gguf_path: str, requested_ctx: int) -> int:
        """Safety net: cap n_ctx if model weights + estimated KV cache would exceed usable VRAM.
        Must be called BEFORE any planning uses n_ctx, so injections fit the actual context window.
        """
        try:
            from pathlib import Path

            model_size_gb = Path(gguf_path).stat().st_size / (1024**3)
            # KV cache estimate: 2 (K+V) * n_layers * head_dim * n_kv_heads * 2 bytes (F16) per token
            # Gemma 4 E2B: 35 layers, 1 KV head, 512 dim, full-size SWA ≈ x2
            # Conservative: ~140 KB/token. Non-SWA models will be smaller, so this is a safe upper bound.
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
    ) -> str | Generator[str, None, None]:
        """
        Main generation entry point.
        messages: OpenAI-format [{"role": ..., "content": ...}]

        Gemma-4 native multimodal: set has_image/has_audio/has_video=True
        to steer to the right cognitive profile. The content can include
        base64 image URLs or audio tokens directly (passed to llama.cpp).
        """
        self._require_loaded()

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

        if system_prefix or memory_block:
            steered_messages = _inject_system(messages, system_prefix, memory_block)
        else:
            steered_messages = list(messages)

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

        return response

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
) -> list[dict]:
    """
    Inject the XRL system prefix and memory block into the message list.
    Finds an existing system message or prepends a new one.
    """
    steered = list(messages)
    combined_system = "\n\n".join(filter(None, [memory_block, system_prefix]))
    if not combined_system:
        return steered

    # Update existing system message or prepend
    for i, m in enumerate(steered):
        if m.get("role") == "system":
            existing = m.get("content", "")
            steered[i] = {
                "role": "system",
                "content": combined_system + "\n\n" + existing,
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
