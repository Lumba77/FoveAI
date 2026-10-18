"""
api/server.py — OpenAI-Compatible REST API for XRLF
====================================================
Exposes the XRLFRuntime as an OpenAI-compatible endpoint.
Point LM Studio, Open WebUI, Antigravity, or any OpenAI SDK at:

    http://localhost:8400/v1

Endpoints:
  GET  /health
  GET  /v1/models
  POST /v1/chat/completions   (streaming + non-streaming)
  POST /v1/completions

Usage:
  python api/server.py --model gemma-4-12b-xrl.xrlf --port 8400
"""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
    from pydantic import BaseModel

    _FASTAPI = True
except ImportError:
    _FASTAPI = False

from runtime.xrlf_runtime import XRLFRuntime

# ── Request telemetry ────────────────────────────────────────────────────────
# Shared JSONL log dir with the :8400 proxy (core/request-log.js writes
# requests-*.jsonl; this writes runtime-*.jsonl). One append per request /
# inference — a single-line write costs microseconds and never blocks.
_LOG_DIR = Path(
    os.environ.get(
        "FOVEAI_LOG_DIR",
        Path(__file__).parent.parent / "foveated-memory" / "memory_data" / "logs",
    )
)


def _reqlog(entry: dict) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d", time.gmtime())
        line = json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **{k: v for k, v in entry.items() if v is not None},
            }
        )
        with open(_LOG_DIR / f"runtime-{day}.jsonl", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass  # telemetry must never break inference


# ── Pydantic models ───────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: Any  # str or list (multimodal)


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    max_tokens: int | None = 1024
    temperature: float | None = None
    stream: bool | None = False
    # XRLF extensions
    xrlf_force_profile: str | None = None
    xrlf_headless: bool | None = None  # skip avatar markup for API/IDE clients
    xrlf_thinking: bool | None = (
        None  # None = default on; False drops the thought channel
    )
    xrlf_utility: bool | None = (
        None  # bare model call — no steering/soul/memory/evolution
    )


class CompletionRequest(BaseModel):
    model: str = ""
    prompt: str
    max_tokens: int | None = 512
    temperature: float | None = 0.7
    stream: bool | None = False


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge any leading/standalone system messages into the first user message.

    Some XRLF runtimes (llama.cpp-based) do not accept a separate `system` role
    and raise an embedding shape error. This keeps the instructions but only
    sends the runtime roles it understands.
    """
    if not messages:
        return messages

    system_parts = []
    others = []
    for m in messages:
        if m.get("role") == "system":
            system_parts.append(str(m.get("content", "")))
        else:
            others.append(m)

    if system_parts and others:
        # Prepend the collected system prompt to the first user message
        first = others[0]
        if first.get("role") == "user":
            first = {
                **first,
                "content": "[SYSTEM]\n"
                + "\n".join(system_parts)
                + "\n[USER]\n"
                + str(first.get("content", "")),
            }
            return [first] + others[1:]

    return others


# ── App factory ───────────────────────────────────────────────────────────────


def create_app(runtime: XRLFRuntime) -> "FastAPI":
    if not _FASTAPI:
        raise RuntimeError(
            "fastapi + uvicorn not installed. Run: pip install fastapi uvicorn[standard]"
        )

    app = FastAPI(
        title="XRLF Runtime API",
        version="1.0.0",
        description="OpenAI-compatible API for XRLF hybrid models",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Access log — one JSONL line per request (status + latency). Streaming
    # latency here is time-to-first-response; true decode time is logged by
    # the inference events below.
    @app.middleware("http")
    async def _access_log(request: Request, call_next):
        t0 = time.time()
        status = 500
        err = None
        try:
            resp = await call_next(request)
            status = resp.status_code
            return resp
        except Exception as e:
            err = str(e)[:200]
            raise
        finally:
            _reqlog(
                {
                    "layer": "runtime",
                    "endpoint": f"{request.method} {request.url.path}",
                    "status": status,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "error": err or (f"http_{status}" if status >= 400 else None),
                }
            )

    # llama.cpp's CUDA pool asserts (SIGABRT) when two decodes overlap on one
    # context. The :8400 proxy serializes its own calls, but internal services
    # (EcologicalWorker, importance-scorer, MindCore) hit :8402 directly — so
    # the lock lives here, at the inference boundary, where every caller pays it.
    import threading

    _inference_lock = threading.Lock()

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        load_state = getattr(
            runtime, "load_state", "ready" if runtime.loaded else "idle"
        )
        return {
            "status": "ok",
            "model": runtime.model_name,
            "runtime": "xrlf-1.0",
            "loaded": runtime.loaded,
            "loading": load_state == "loading",
            "load_state": load_state,
            "load_error": getattr(runtime, "load_error", None),
            "xrl_degree": getattr(runtime, "xrl_degree", 0),
            "compression_profile": getattr(runtime, "compression_profile", ""),
        }

    # ── SoftLayer: serve hot-reloadable JS modules ────────────────────────────
    softlayer_dir = Path(__file__).parent.parent / "softlayer"

    @app.get("/softlayer/{module_name}.js")
    async def get_softlayer_module(module_name: str):
        js_file = softlayer_dir / f"{module_name}.js"
        if not js_file.exists():
            raise HTTPException(
                status_code=404, detail=f"Module '{module_name}' not found"
            )
        source = js_file.read_text(encoding="utf-8")
        return PlainTextResponse(source, media_type="application/javascript")

    @app.get("/softlayer")
    async def list_softlayer_modules():
        modules = []
        if softlayer_dir.exists():
            modules = [f.stem for f in softlayer_dir.glob("*.js")]
        return {"modules": modules}

    # ── SoftLayer modules (modular environment control) ───────────────────────
    modules_dir = softlayer_dir / "modules"

    @app.get("/softlayer/modules/{module_name}.js")
    async def get_softlayer_module_file(module_name: str):
        js_file = modules_dir / f"{module_name}.js"
        if not js_file.exists():
            raise HTTPException(
                status_code=404, detail=f"Module '{module_name}' not found"
            )
        source = js_file.read_text(encoding="utf-8")
        return PlainTextResponse(source, media_type="application/javascript")

    @app.get("/softlayer/modules")
    async def list_softlayer_module_files():
        mods = []
        if modules_dir.exists():
            mods = [f.stem for f in modules_dir.glob("*.js")]
        return {"modules": mods}

    # ── Memory planner status ─────────────────────────────────────────────────
    @app.get("/memory/status")
    async def memory_status():
        """Get dynamic VRAM/RAM tiling status from the memory planner."""
        if hasattr(runtime, "get_memory_status"):
            return runtime.get_memory_status()
        return {"error": "Memory planner not available"}

    # ── Soul bridge status ────────────────────────────────────────────────────
    @app.get("/soul/status")
    async def soul_status():
        """Get Alice's soul and cognitive state."""
        if hasattr(runtime, "_soul") and runtime._soul:
            return runtime._soul.get_status()
        return {"error": "Soul bridge not available"}

    # ── Models ────────────────────────────────────────────────────────────────

    @app.post("/unload")
    async def unload_model():
        """Unload the current model from VRAM without killing the runtime process."""
        if getattr(runtime, "load_state", "idle") == "loading":
            raise HTTPException(
                status_code=409,
                detail="Model load in progress — wait or restart the runtime",
            )
        if not runtime.loaded:
            return {"status": "ok", "loaded": False, "message": "No model loaded"}
        try:
            await asyncio.to_thread(runtime.close)
            return {
                "status": "ok",
                "loaded": False,
                "message": f"Unloaded {runtime.model_name}",
            }
        except Exception as e:
            return {"status": "error", "loaded": runtime.loaded, "error": str(e)}

    @app.post("/load")
    async def load_model(request: Request):
        """Hot-swap to a different model without restarting the runtime process.
        Body: {"model": "path/to/model.xrlf"}
        Runs in a thread so /health stays responsive and reports load_state.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_path = body.get("model", "")
        if not model_path:
            return {
                "status": "error",
                "loaded": runtime.loaded,
                "error": "missing 'model' in body",
            }

        if getattr(runtime, "load_state", "idle") == "loading":
            raise HTTPException(
                status_code=409, detail="Model load already in progress"
            )

        # Resolve and validate BEFORE unloading — a bad path must not kill the
        # currently loaded model.
        import os as _os

        if not _os.path.exists(str(model_path)):
            alt = _os.path.join("xrl_encoded", str(model_path))
            if _os.path.exists(alt):
                model_path = alt
            else:
                return {
                    "status": "error",
                    "loaded": runtime.loaded,
                    "error": f"model file not found: {model_path}",
                }

        # Report loading through the whole unload+load window so /health and
        # pollers see 'loading' (also blocks a concurrent /load via the 409).
        runtime.load_state = "loading"
        runtime.load_error = None

        # Load in a background thread and return immediately — the "finished"
        # signal is /health.load_state flipping to 'ready'/'error'. Holding this
        # request open for the whole load outlives every client timeout (120s+),
        # which made callers abort mid-load and spawn a second runtime that
        # fought the first for the port.
        def _swap():
            try:
                if runtime.loaded:
                    try:
                        runtime.close()
                    except Exception as e:
                        print(f"  ⚠️ Error during unload: {e}")
                    runtime.load_state = "loading"  # close() resets to 'idle'
                runtime.xrlf_path = str(model_path)
                runtime.load()
            except Exception as e:
                import traceback

                traceback.print_exc()
                runtime.load_state = "error"
                runtime.load_error = str(e)

        asyncio.get_event_loop().run_in_executor(None, _swap)
        return {
            "status": "loading",
            "loaded": False,
            "model": model_path,
            "poll": "/health until load_state == 'ready'",
        }

    @app.get("/v1/models")
    async def list_models():
        model_id = runtime.model_name or "xrlf-model"
        return {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "xrlf-runtime",
                    "capabilities": {
                        "vision": True,
                        "audio": True,
                        "video": True,
                        "tts": True,
                        "xrl_cognitive_layer": True,
                        "foveated_memory": True,
                    },
                }
            ],
        }

    @app.get("/v1/packages")
    async def list_packages():
        """Loadable .xrlf packages on disk, with the active one flagged.
        Lets UIs offer real model selection (via POST /load) instead of
        the merged provider registry on the proxy."""
        import glob as _glob

        active = os.path.abspath(getattr(runtime, "xrlf_path", "") or "")
        # Packages hidden from pickers — still on disk and loadable via POST
        # /load by an admin, but won't appear in UIs where a tester could
        # click something that crashes the host (e.g. 12B on 8GB VRAM).
        hidden = {
            s.strip()
            for s in os.environ.get(
                "XRLF_HIDDEN_PACKAGES",
                "gemma-4-12b-mtp-xrlf-3.0,qwen3.5-4b-mtp-multimodal-v1.0",
            ).split(",")
            if s.strip()
        }
        pkgs = []
        for path in sorted(_glob.glob(os.path.join("xrl_encoded", "*.xrlf"))):
            if os.path.splitext(os.path.basename(path))[0] in hidden:
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            pkgs.append(
                {
                    "id": os.path.splitext(os.path.basename(path))[0],
                    "object": "xrlf_package",
                    "path": path,
                    "size_mb": round(size / (1024 * 1024)),
                    "active": os.path.abspath(path) == active,
                }
            )

        # Open XRL Micro-Workers & Nursery Models
        try:
            from Forge.nursery.model_registry import get_registry
            reg = get_registry()
            for vid, vdata in reg.variants.items():
                if vid in ["tier_a_light", "tier_b_flagship"]:
                    continue
                size_mb = int(vdata.training_config.get("size_gb", 0.5) * 1024)
                pkgs.append({
                    "id": f"micro_{vid}",
                    "name": vdata.name,
                    "object": "micro_worker",
                    "path": vdata.training_config.get("file", vid),
                    "size_mb": size_mb,
                    "active": False,
                    "is_micro": True,
                })
        except Exception:
            pass

        return {"object": "list", "data": pkgs}

    # ── Forge Nursery Micro-Tools & UI Automation ─────────────────────────────
    @app.get("/v1/tools")
    async def list_micro_tools():
        """Expose Forge Nursery micro-tools to Multigate and UI clients."""
        try:
            from Forge.nursery.micro_tools import get_micro_tool_engine
            engine = get_micro_tool_engine()
            return {"object": "list", "data": engine.list_tools()}
        except Exception as e:
            return {"object": "list", "data": [], "error": str(e)}

    @app.post("/v1/tools/execute")
    async def execute_micro_tool(request: Request):
        """Execute a micro-tool on the fast adopted model."""
        try:
            body = await request.json()
            tool_id = body.get("tool_id", "ui_action_router")
            user_input = body.get("input", "")
            model_variant = body.get("variant")
            from Forge.nursery.micro_tools import get_micro_tool_engine
            engine = get_micro_tool_engine()
            res = await asyncio.to_thread(engine.execute_tool, tool_id, user_input, model_variant)
            return res
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/v1/tools/register")
    async def register_micro_tool(request: Request):
        """Dynamically create and register a new custom automated tool."""
        try:
            body = await request.json()
            from Forge.nursery.micro_tools import get_micro_tool_engine
            engine = get_micro_tool_engine()
            tool = engine.register_tool(
                tool_id=body["id"],
                name=body["name"],
                description=body.get("description", ""),
                system_prompt=body["system_prompt"],
                preferred_variant=body.get("preferred_variant", "qwen25_coder_05b"),
                output_type=body.get("output_type", "json"),
            )
            return {"ok": True, "tool": tool.to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/v1/context")
    async def get_context_info():
        """Proxy-internal: exposes actual n_ctx (after safety net cap) for injection planning.
        NOT exposed to end clients — the proxy spoofs a larger window to them while
        injecting a smaller, planned amount that fits this real n_ctx.
        """
        return {
            "context_window": runtime.n_ctx,
            "model": runtime.model_name,
            "loaded": runtime.loaded,
        }

    # ── System diagnostics (settings-panel verification) ─────────────────────
    @app.get("/v1/diagnostics")
    async def diagnostics():
        """Read-only verification of the full XRLF stack: package, XRL layers,
        prompt gates, memory, MTP/draft, GPU offload, and inference health.
        Each check reports pass|warn|fail plus a human-readable detail."""
        import sqlite3 as _sq

        checks = []

        def add(name: str, status: str, detail: str, group: str):
            checks.append(
                {"name": name, "status": status, "detail": detail, "group": group}
            )

        parser = getattr(runtime, "_parser", None)
        loaded = runtime.loaded
        load_state = getattr(runtime, "load_state", "unknown")

        # ── Runtime / model ──
        add(
            "runtime_state",
            "pass" if loaded else ("warn" if load_state == "loading" else "fail"),
            f"state={load_state}"
            + (
                f" error={getattr(runtime, 'load_error', None)}"
                if getattr(runtime, "load_error", None)
                else ""
            ),
            "runtime",
        )
        add(
            "model_identity",
            "pass" if runtime.model_name else "fail",
            f"{runtime.model_name or 'none'} ({getattr(runtime, 'xrlf_path', '?')})",
            "runtime",
        )

        # ── Package / sections ──
        if parser:
            try:
                from formats.xrlf_schema import SectionType as ST

                sec_map = {
                    "CORE_GGUF": ST.CORE_GGUF,
                    "CORE_MMPROJ": ST.CORE_MMPROJ,
                    "CORE_DRAFT_GGUF": ST.CORE_DRAFT_GGUF,
                    "XRL_PRINCIPLES": ST.XRL_PRINCIPLES,
                    "XRL_PROFILES": ST.XRL_PROFILES,
                    "XRL_GRAPH": ST.XRL_GRAPH,
                    "XRL_CLUSTERS": ST.XRL_CLUSTERS,
                    "XRL_MM_HOOKS": ST.XRL_MM_HOOKS,
                    "XRL_MEMORY_DATA": ST.XRL_MEMORY_DATA,
                    "XRL_MEMORY_SCHEMA": ST.XRL_MEMORY_SCHEMA,
                }
                sizes = {
                    e.section_type.name: e.length
                    for e in getattr(parser.manifest, "sections", [])
                }
                for name, st in sec_map.items():
                    has = parser.has_section(st)
                    sz = sizes.get(name, 0)
                    if not has:
                        status = (
                            "fail"
                            if name in ("CORE_GGUF", "XRL_PRINCIPLES")
                            else "warn"
                        )
                        add(f"section_{name.lower()}", status, "absent", "package")
                    else:
                        # Validate JSON-bearing sections actually parse;
                        # XRL_MEMORY_DATA is a binary SQLite DB — check magic.
                        if name == "XRL_MEMORY_DATA":
                            try:
                                head = parser.get_section_bytes(st)[:20]
                                ok = b"SQLite format 3" in head
                                add(
                                    f"section_{name.lower()}",
                                    "pass" if ok else "fail",
                                    f"{sz / 1024:.1f} KB, {'sqlite_ok' if ok else 'bad magic'}",
                                    "package",
                                )
                            except Exception as e:
                                add(
                                    f"section_{name.lower()}",
                                    "fail",
                                    f"read error: {e}",
                                    "package",
                                )
                        elif name.startswith("XRL_") or name == "RUNTIME_META":
                            try:
                                j = parser.get_section_json(st)
                                add(
                                    f"section_{name.lower()}",
                                    "pass",
                                    f"{sz / 1024:.1f} KB, json_ok ({len(str(j))} chars)",
                                    "package",
                                )
                            except Exception as e:
                                add(
                                    f"section_{name.lower()}",
                                    "fail",
                                    f"{sz / 1024:.1f} KB, JSON parse error: {e}",
                                    "package",
                                )
                        else:
                            add(
                                f"section_{name.lower()}",
                                "pass",
                                f"{sz / (1024**2):.1f} MB",
                                "package",
                            )
            except Exception as e:
                add("package_sections", "fail", f"inspection error: {e}", "package")
        else:
            add("package_sections", "fail", "no parser — model not loaded", "package")

        # ── XRL cognitive layers (loaded objects, not just sections) ──
        for attr, label in (
            ("_principia", "principia_applicator"),
            ("_profile_sel", "profile_selector"),
            ("_cluster_act", "cluster_activator"),
            ("_graph_trav", "graph_traverser"),
        ):
            obj = getattr(runtime, attr, None)
            add(
                f"xrl_{label}",
                "pass" if obj else "warn",
                "active" if obj else "not initialized",
                "xrl_layers",
            )

        # ── Prompt gates ──
        for env_key in (
            "XRLF_REPO_ENABLED",
            "XRLF_CONTEXT_OVERRIDE",
            "XRLF_CAPABILITY_OVERRIDE",
            "XRLF_FOVEATION_OVERRIDE",
        ):
            val = os.environ.get(env_key, "unset")
            on = val.lower().strip() in ("true", "1", "on")
            add(
                f"gate_{env_key.lower()}",
                "pass" if on else "fail",
                f"{env_key}={val}",
                "prompt",
            )

        add(
            "soul_bridge",
            "pass" if getattr(runtime, "_soul", None) else "warn",
            "active" if getattr(runtime, "_soul", None) else "not initialized",
            "prompt",
        )

        # ── Memory ──
        mem = getattr(runtime, "_memory", None)
        db_path = getattr(runtime, "_memory_db_path", None)
        add(
            "memory_engine",
            "pass" if mem else "fail",
            f"{db_path or 'no path'}",
            "memory",
        )
        if db_path and os.path.exists(db_path):
            try:
                con = _sq.connect(f"file:{db_path}?mode=ro", uri=True)
                turns = con.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
                con.close()
                add(
                    "memory_db",
                    "pass" if turns > 0 else "warn",
                    f"{os.path.getsize(db_path) / (1024**2):.1f} MB, {turns} turns",
                    "memory",
                )
            except Exception as e:
                add("memory_db", "fail", f"open failed: {e}", "memory")
        add(
            "memory_planner",
            "pass" if getattr(runtime, "_planner", None) else "warn",
            "active" if getattr(runtime, "_planner", None) else "not initialized",
            "memory",
        )

        # ── MTP / speculative decoding ──
        llama = getattr(runtime, "_llama", None)
        draft_path = getattr(runtime, "_draft_gguf_path", None)
        spec_env = os.environ.get("XRLF_SPECULATIVE_DECODING", "false")
        has_draft_section = (
            bool(parser and parser.has_section(ST.CORE_DRAFT_GGUF)) if parser else False
        )
        mtp_active = bool(getattr(llama, "_mtp_active", False)) if llama else False
        if mtp_active:
            add(
                "mtp_speculative",
                "pass",
                f"native MTP active (draft: {os.path.basename(draft_path or '?')})",
                "inference",
            )
        elif (
            has_draft_section and spec_env.lower() in ("true", "1", "on") and draft_path
        ):
            add(
                "mtp_speculative",
                "pass",
                f"classic speculative via {os.path.basename(draft_path)}",
                "inference",
            )
        elif has_draft_section:
            add(
                "mtp_speculative",
                "warn",
                f"draft bundled but XRLF_SPECULATIVE_DECODING={spec_env}",
                "inference",
            )
        else:
            add(
                "mtp_speculative",
                "warn",
                "no CORE_DRAFT_GGUF in package — single-model decode",
                "inference",
            )

        # ── Inference / GPU ──
        if llama:
            fa = getattr(llama, "_flash_attn_active", None)
            kvq = getattr(llama, "_kv_quant", "f16")
            add(
                "llama_engine",
                "pass" if getattr(llama, "loaded", False) else "fail",
                f"n_ctx={runtime.n_ctx}, gpu_layers={getattr(llama, 'n_gpu_layers', '?')}, "
                f"flash_attn={'on' if fa else 'off'}, kv_cache={kvq}",
                "inference",
            )
        else:
            add("llama_engine", "fail", "not initialized", "inference")
        add(
            "context_window",
            "pass",
            f"effective n_ctx={runtime.n_ctx} (after VRAM safety cap)",
            "inference",
        )
        mmproj = getattr(runtime, "_mmproj_path", None)
        add(
            "multimodal",
            "pass" if mmproj else "warn",
            f"mmproj={os.path.basename(mmproj)}"
            if mmproj
            else "no projector — text only",
            "inference",
        )

        # ── Auxiliary models ──
        wh = getattr(runtime, "_whisper_gguf_path", None)
        ko = getattr(runtime, "_kokoro_model_path", None)
        add(
            "stt_whisper",
            "pass" if wh else "warn",
            os.path.basename(wh)
            if wh
            else "no embedded/fallback whisper — external :8409 only",
            "aux",
        )
        add(
            "tts_kokoro",
            "pass" if ko else "warn",
            os.path.basename(ko)
            if ko
            else "no embedded/fallback kokoro — external :8406 only",
            "aux",
        )

        worst = "pass"
        if any(c["status"] == "fail" for c in checks):
            worst = "fail"
        elif any(c["status"] == "warn" for c in checks):
            worst = "warn"

        return {
            "overall": worst,
            "model": runtime.model_name,
            "loaded": loaded,
            "timestamp": int(time.time()),
            "checks": checks,
        }

    # ── Chat completions ──────────────────────────────────────────────────────

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest, request: Request):
        messages = [m.model_dump() for m in req.messages]

        # Detect multimodal content
        has_image = has_audio = has_video = False
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        t = part.get("type", "")
                        if t in ("image_url", "image"):
                            has_image = True
                        elif t in ("audio_url", "audio", "input_audio"):
                            has_audio = True

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        model_id = runtime.model_name or "xrlf-model"

        if not runtime.loaded:
            state = getattr(runtime, "load_state", "idle")
            detail = getattr(runtime, "load_error", None) or (
                "model still loading" if state == "loading" else "no model loaded"
            )
            raise HTTPException(
                status_code=503, detail=f"XRLF runtime not ready ({state}): {detail}"
            )

        if req.stream:
            return StreamingResponse(
                _stream_chat(
                    runtime,
                    messages,
                    req,
                    has_image,
                    has_audio,
                    has_video,
                    completion_id,
                    model_id,
                ),
                media_type="text/event-stream",
            )

        # Non-streaming — run in a thread so the event loop (and /health)
        # stays responsive during blocking inference. The inference lock is
        # acquired inside the worker so overlapping callers queue, not crash.
        def _run_chat():
            t_queue = time.time()
            with _inference_lock:
                queue_ms = int((time.time() - t_queue) * 1000)
                t_decode = time.time()
                try:
                    out = runtime.chat(
                        messages=messages,
                        max_tokens=req.max_tokens,
                        temperature=req.temperature,
                        stream=False,
                        has_image=has_image,
                        has_audio=has_audio,
                        has_video=has_video,
                        force_profile=req.xrlf_force_profile,
                        headless=bool(req.xrlf_headless),
                        thinking=req.xrlf_thinking
                        if req.xrlf_thinking is not None
                        else True,
                        utility=bool(req.xrlf_utility),
                    )
                    _reqlog(
                        {
                            "layer": "runtime",
                            "event": "inference",
                            "model": model_id,
                            "stream": False,
                            "queue_ms": queue_ms,
                            "decode_ms": int((time.time() - t_decode) * 1000),
                            "chars": len(out or ""),
                            "headless": bool(req.xrlf_headless),
                        }
                    )
                    return out
                except Exception as e:
                    _reqlog(
                        {
                            "layer": "runtime",
                            "event": "inference",
                            "model": model_id,
                            "stream": False,
                            "queue_ms": queue_ms,
                            "error": str(e)[:200],
                        }
                    )
                    raise

        try:
            response_text = await asyncio.to_thread(_run_chat)
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": -1,
                "completion_tokens": -1,
                "total_tokens": -1,
            },
        }

    async def _stream_chat(
        runtime, messages, req, has_image, has_audio, has_video, completion_id, model_id
    ) -> AsyncGenerator[str, None]:
        """SSE streaming generator.

        The blocking sync decode runs in a worker thread and feeds an
        asyncio.Queue, so the uvicorn event loop (and /health) stays responsive
        while tokens stream. The inference lock is held for the whole decode and
        released in this generator's finally — a client disconnect can no longer
        strand the lock (llama.cpp's CUDA pool asserts if two decodes overlap).
        """
        t_queue = time.time()
        await asyncio.to_thread(_inference_lock.acquire)
        queue_ms = int((time.time() - t_queue) * 1000)
        t_decode = time.time()
        out_chars = 0
        loop = asyncio.get_running_loop()
        chunks: asyncio.Queue = asyncio.Queue()
        err: str | None = None

        def _pump():
            gen = None
            try:
                gen = runtime.chat(
                    messages=messages,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    stream=True,
                    has_image=has_image,
                    has_audio=has_audio,
                    has_video=has_video,
                    force_profile=req.xrlf_force_profile,
                    headless=bool(req.xrlf_headless),
                    thinking=req.xrlf_thinking if req.xrlf_thinking is not None else True,
                    utility=bool(req.xrlf_utility),
                )
                for chunk in gen:
                    loop.call_soon_threadsafe(chunks.put_nowait, ("chunk", chunk))
            except Exception as e:  # surface to the SSE client, never the loop
                loop.call_soon_threadsafe(chunks.put_nowait, ("error", str(e)[:200]))
            finally:
                if gen is not None and hasattr(gen, "close"):
                    try:
                        gen.close()
                    except Exception:
                        pass
                try:
                    loop.call_soon_threadsafe(chunks.put_nowait, ("done", None))
                except RuntimeError:
                    pass  # event loop already gone — nothing left to feed

        threading.Thread(target=_pump, name="xrlf-stream", daemon=True).start()

        try:
            while True:
                kind, val = await chunks.get()
                if kind == "done":
                    break
                if kind == "error":
                    err = val
                    break
                out_chars += len(val)
                data = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": val},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(data)}\n\n"
            if err:
                yield f"data: {json.dumps({'error': err})}\n\n"
            done = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(done)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            _inference_lock.release()
            _reqlog(
                {
                    "layer": "runtime",
                    "event": "inference",
                    "model": model_id,
                    "stream": True,
                    "queue_ms": queue_ms,
                    "decode_ms": int((time.time() - t_decode) * 1000),
                    "chars": out_chars,
                    "headless": bool(req.xrlf_headless),
                    "error": err,
                }
            )

    # ── Raw completions ───────────────────────────────────────────────────────

    @app.post("/v1/completions")
    async def completions(req: CompletionRequest):
        try:
            with _inference_lock:
                text = runtime.generate(
                    req.prompt,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        return {
            "id": f"cmpl-{uuid.uuid4().hex[:12]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": runtime.model_name,
            "choices": [
                {
                    "text": text,
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
        }

    # ── Native STT: POST /v1/audio/transcriptions ─────────────────────────────
    # Uses the model's native speech-to-text (Gemma-4 audio encoder via mmproj)
    # Accepts: multipart file upload (audio file) or JSON with base64
    @app.post("/v1/audio/transcriptions")
    async def transcribe_audio(request: Request):
        import base64 as b64mod
        import os
        import tempfile

        audio_bytes = None
        filename = "audio.webm"

        # Check content type for multipart vs JSON
        content_type = request.headers.get("content-type", "")

        if "multipart" in content_type:
            form = await request.form()
            file = form.get("file") or form.get("audio")
            if file:
                audio_bytes = await file.read()
                filename = file.filename or "audio.webm"
        else:
            body = await request.json()
            audio_b64 = body.get("audio_base64") or body.get("audio")
            if audio_b64:
                audio_bytes = b64mod.b64decode(audio_b64)
                filename = body.get("filename", "audio.webm")

        if not audio_bytes:
            raise HTTPException(status_code=400, detail="No audio data provided")

        # Save to temp file
        tmp = tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(filename)[1], delete=False
        )
        tmp.write(audio_bytes)
        tmp.close()

        try:
            # Use the model's chat handler to process audio
            # Gemma-4 supports audio input via the MTMD chat handler
            llama = getattr(runtime, "_llama", None)
            llm = getattr(llama, "_llm", None) if llama else None
            handler = getattr(llm, "chat_handler", None) if llm else None
            if handler:
                # Init the mtmd context (lazy-initialized)
                if getattr(handler, "mtmd_ctx", None) is None and hasattr(
                    handler, "_init_mtmd_context"
                ):
                    handler._init_mtmd_context(llm)
                try:
                    from llama_cpp import mtmd_cpp

                    ctx = getattr(handler, "mtmd_ctx", None)
                    if (
                        ctx
                        and hasattr(mtmd_cpp, "mtmd_support_audio")
                        and mtmd_cpp.mtmd_support_audio(ctx)
                    ):
                        # Process audio through the model
                        # Create a chat completion with audio input
                        messages = [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Transcribe this audio accurately.",
                                    },
                                    {
                                        "type": "audio_url",
                                        "audio_url": {
                                            "url": f"data:audio/webm;base64,{b64mod.b64encode(audio_bytes).decode()}"
                                        },
                                    },
                                ],
                            }
                        ]
                        with _inference_lock:
                            result = runtime.chat(
                                messages, max_tokens=256, has_audio=True
                            )
                        text = (
                            result.strip() if isinstance(result, str) else str(result)
                        )
                        return {"text": text}
                except (ImportError, Exception) as e:
                    print(f"[API] Native STT error: {e}")

            # Fallback to IPCServer Whisper if available
            ipc_server = getattr(request.app.state, "ipc_server", None)
            fwhisper = (
                getattr(ipc_server, "_fwhisper_model", None) if ipc_server else None
            )
            if fwhisper:
                try:
                    import asyncio
                    import io
                    import wave

                    import numpy as np

                    with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                        sr = wav.getframerate()
                        n_channels = wav.getnchannels()
                        frames = wav.readframes(wav.getnframes())
                        audio_np = (
                            np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                            / 32768.0
                        )
                        if n_channels > 1:
                            audio_np = audio_np[::n_channels]
                        if sr != 16000:
                            n_samples = int(len(audio_np) * 16000 / sr)
                            indices = np.linspace(0, len(audio_np) - 1, n_samples)
                            audio_np = np.interp(
                                indices, np.arange(len(audio_np)), audio_np
                            )

                    segments, info = await asyncio.to_thread(
                        fwhisper.transcribe,
                        audio_np,
                        language="en",
                        beam_size=5,
                        vad_filter=True,
                        vad_parameters=dict(
                            min_silence_duration_ms=500, speech_pad_ms=200
                        ),
                    )
                    text = " ".join(seg.text.strip() for seg in segments).strip()
                    return {"text": text}
                except Exception as e:
                    print(f"[API] IPC Whisper STT error: {e}")

            raise HTTPException(
                status_code=503,
                detail="Native STT not available — model has no audio support or mmproj not loaded",
            )
        finally:
            os.unlink(tmp.name)

    # ── Native TTS: POST /v1/audio/speech ──────────────────────────────────────
    # Uses the MMHookRegistry's TTS hook (which auto-detects Kokoro/Piper/espeak)
    # or the model's native audio output if available
    @app.post("/v1/audio/speech")
    async def generate_speech(request: Request):
        body = await request.json()
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")

        voice = body.get("voice", "default")

        # Try the MMHookRegistry TTS first
        mm_registry = getattr(runtime, "_mm_registry", None)
        tts_hook = getattr(mm_registry, "tts", None) if mm_registry else None
        if tts_hook and getattr(tts_hook, "available", False):
            try:
                wav_path = tts_hook.speak(text)
                if wav_path and os.path.exists(wav_path):
                    with open(wav_path, "rb") as f:
                        audio_data = f.read()
                    os.unlink(wav_path)
                    return Response(
                        content=audio_data,
                        media_type="audio/wav",
                        headers={"Content-Disposition": "inline; filename=speech.wav"},
                    )
            except Exception as e:
                print(f"[API] TTS hook error: {e}")

        # Fallback to IPCServer Kokoro if available
        ipc_server = getattr(request.app.state, "ipc_server", None)
        if ipc_server and hasattr(ipc_server, "_kokoro_tts"):
            try:
                import asyncio

                pcm_data = await asyncio.to_thread(
                    ipc_server._kokoro_tts, text, voice, 24000
                )
                if pcm_data:
                    import io
                    import wave

                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(24000)
                        wf.writeframes(pcm_data)
                    return Response(
                        content=buf.getvalue(),
                        media_type="audio/wav",
                        headers={"Content-Disposition": "inline; filename=speech.wav"},
                    )
            except Exception as e:
                print(f"[API] IPC Kokoro TTS error: {e}")

        raise HTTPException(
            status_code=503, detail="TTS not available — no TTS hook or external server"
        )

    # ── Image input: POST /v1/images/understand ────────────────────────────────
    # Send an image to the model for understanding (vision capability)
    @app.post("/v1/images/understand")
    async def understand_image(request: Request):

        body = await request.json()
        image_b64 = body.get("image_base64") or body.get("image")
        prompt = body.get("prompt", "Describe this image in detail.")
        if not image_b64:
            raise HTTPException(status_code=400, detail="image_base64 required")

        # Strip data URL prefix if present
        if "," in image_b64 and image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        # Build multimodal chat message
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ]

        try:
            with _inference_lock:
                result = runtime.chat(messages, max_tokens=512, has_image=True)
            text = result.strip() if isinstance(result, str) else str(result)
            return {"text": text}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Vision error: {e}")

    # ── Capability check: GET /v1/capabilities ─────────────────────────────────
    @app.get("/v1/capabilities")
    async def capabilities():
        llama = getattr(runtime, "_llama", None)
        mmproj_path = getattr(llama, "mmproj_path", None) if llama else None
        has_mmproj = bool(mmproj_path and os.path.exists(mmproj_path))
        mm_registry = getattr(runtime, "_mm_registry", None)
        tts_hook = getattr(mm_registry, "tts", None) if mm_registry else None
        has_tts = bool(tts_hook and getattr(tts_hook, "available", False))
        has_vision = False
        has_audio = False

        if has_mmproj and llama:
            llm = getattr(llama, "_llm", None)
            if llm:
                try:
                    from llama_cpp import mtmd_cpp

                    handler = getattr(llm, "chat_handler", None)
                    if handler:
                        if getattr(handler, "mtmd_ctx", None) is None and hasattr(
                            handler, "_init_mtmd_context"
                        ):
                            handler._init_mtmd_context(llm)
                        ctx = getattr(handler, "mtmd_ctx", None)
                        if ctx:
                            has_vision = bool(
                                hasattr(mtmd_cpp, "mtmd_support_vision")
                                and mtmd_cpp.mtmd_support_vision(ctx)
                            )
                            if hasattr(mtmd_cpp, "mtmd_support_audio"):
                                has_audio = bool(mtmd_cpp.mtmd_support_audio(ctx))
                except (ImportError, Exception) as e:
                    print(f"[API] Capability check error: {e}")

        gpu_layers = getattr(llama, "n_gpu_layers", 0)
        if gpu_layers is None:
            gpu_layers = 0

        return {
            "vision": has_vision,
            "audio_stt": has_audio,
            "tts": has_tts,
            "mmproj_loaded": has_mmproj,
            "gpu_layers": gpu_layers,
            "model": getattr(runtime, "model_name", "xrlf-model"),
        }

    # ── Spatial environment: POST /api/environment/plaster_texture ────────────
    # Legacy path: the soul service (compagent, :8405) owns plaster storage now.
    # Older Quest builds still POST here — forward the payload so the image
    # actually lands in plaster_collegium instead of being discarded.
    @app.post("/api/environment/plaster_texture")
    async def plaster_texture(request: Request):
        body = await request.body()
        soul_url = os.environ.get("SOUL_URL", "http://127.0.0.1:8405")
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{soul_url}/api/environment/plaster_texture",
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code < 500:
                    try:
                        return resp.json()
                    except Exception:
                        return {"status": "ok", "forwarded": True}
        except Exception:
            pass  # fall through to metadata stub if soul is down
        try:
            data = json.loads(body) if body else {}
            session = data.get("session_id", "quest3_spatial")
            texture_id = data.get("texture_id", f"plaster_{int(time.time())}")
            spatial_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "foveated-memory",
                "memory_data",
                "spatial",
            )
            os.makedirs(spatial_dir, exist_ok=True)
            meta_path = os.path.join(spatial_dir, f"{texture_id}.json")
            with open(meta_path, "w") as f:
                json.dump(
                    {
                        "session": session,
                        "texture_id": texture_id,
                        "timestamp": time.time(),
                        "data_size": len(body),
                        "soul_unreachable": True,
                    },
                    f,
                )
            return {
                "status": "ok",
                "texture_id": texture_id,
                "stored": True,
                "warning": "soul unreachable — image not persisted",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Plaster texture error: {e}")

    # ── Camera stream: GET /api/camera/stream ─────────────────────────────────
    # Returns latest webcam frame from the Quest/phone camera as JPEG.
    @app.get("/api/camera/stream")
    async def camera_stream():
        # Return a placeholder frame — actual camera frames are pushed via WS
        from fastapi import Response

        # Generate a 1x1 black JPEG placeholder
        placeholder = bytes([0xFF, 0xD8, 0xFF, 0xD9])  # Minimal JPEG header
        return Response(content=placeholder, media_type="image/jpeg")

    # ── Alias: /api/health (for Quest clients that check this path) ───────────
    @app.get("/api/health")
    async def api_health():
        return {
            "status": "ok",
            "model": getattr(runtime, "model_name", "xrlf-model"),
            "runtime": "xrlf-1.0",
        }

    # ── Transformative State Drive (TSD) · Photonic Znake & Legion UI Blasters ─
    @app.get("/tsd")
    @app.get("/api/tsd/ui")
    async def tsd_ui_blaster_page():
        from fastapi.responses import HTMLResponse
        ui_path = Path(ROOT) / "foveated-memory" / "public" / "tsd_blaster.html"
        if ui_path.exists():
            return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))
        return PlainTextResponse("tsd_blaster.html not found", status_code=404)

    @app.get("/api/tsd/status")
    async def tsd_status():
        from runtime.xrl_swarm import get_tsd_motherboard
        mb = get_tsd_motherboard()
        return {
            "status": "ok",
            "telemetry": mb.telemetry(),
            "biosphere": mb.biosphere_scale_hierarchy(),
        }

    @app.post("/api/tsd/seek-and-destroy")
    async def tsd_seek_and_destroy(request: Request):
        from runtime.xrl_swarm import get_tsd_motherboard
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        tasks = body.get("tasks") if isinstance(body, dict) else None
        mb = get_tsd_motherboard()
        res = mb.seek_and_destroy_tasks(tasks)
        res["telemetry"] = mb.telemetry()
        return res

    @app.post("/api/tsd/dream-2036")
    async def tsd_dream_2036():
        from runtime.xrl_swarm import get_tsd_motherboard
        mb = get_tsd_motherboard()
        return mb.dream_cycle_evolution()

    @app.post("/api/tsd/legion")
    async def tsd_legion_counter(request: Request):
        from runtime.xrl_swarm import get_tsd_motherboard
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        prompt = (body.get("prompt") if isinstance(body, dict) else None) or "Verify 1,000 Virtual Pentahedrons on TSD"
        thesis = (body.get("thesis") if isinstance(body, dict) else None) or ""
        mb = get_tsd_motherboard()
        res = mb.legion_countermodel(prompt, thesis)
        res["telemetry"] = mb.telemetry()
        return res

    @app.post("/api/tsd/rejuvenate")
    async def tsd_rejuvenate():
        from runtime.repo_youth_engine import RepoYouthEngine
        return RepoYouthEngine().rejuvenate()

    @app.post("/api/tsd/benchmark")
    async def tsd_benchmark():
        from runtime.benchmark_tsd_legion import run_comprehensive_benchmark
        return run_comprehensive_benchmark()

    return app


# ── CLI entry point ───────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="XRLF OpenAI-compatible API server")
    parser.add_argument("--model", required=True, help="Path to .xrlf file")
    parser.add_argument(
        "--port", type=int, default=8300, help="API port (default: 8300)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument(
        "--gpu-layers", type=int, default=-1, help="GPU layers (-1=all)"
    )
    parser.add_argument("--ctx", type=int, default=8192, help="Context window size")
    parser.add_argument("--session", default="default", help="Session ID for memory")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    runtime = XRLFRuntime(
        xrlf_path=args.model,
        session_id=args.session,
        n_gpu_layers=args.gpu_layers,
        n_ctx=args.ctx,
        verbose=args.verbose,
    )
    runtime.load()

    app = create_app(runtime)

    # ── SoftLayer file watcher ────────────────────────────────────────────────
    softlayer_dir = Path(__file__).parent.parent / "softlayer"
    if softlayer_dir.exists():
        try:
            import threading

            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            class SoftLayerHandler(FileSystemEventHandler):
                def __init__(self):
                    self._last = 0.0

                def on_modified(self, event):
                    if event.is_directory or not event.src_path.endswith(".js"):
                        return
                    now = time.time()
                    if now - self._last < 0.5:
                        return
                    self._last = now
                    p = Path(event.src_path)
                    print(
                        f"  [SoftLayer] File changed: {p.name} — restart XRLF to push to Quest",
                        flush=True,
                    )

            observer = Observer()
            observer.schedule(SoftLayerHandler(), str(softlayer_dir), recursive=True)
            observer.daemon = True
            observer.start()
            print(f"  [SoftLayer] Watching {softlayer_dir} for hot-reloads")
        except ImportError:
            print("  [SoftLayer] watchdog not installed — file watching disabled")

    print(f"\n  🚀 XRLF API ready → http://{args.host}:{args.port}/v1")
    print(f"     Model: {runtime.model_name}")
    print(f"     SoftLayer: http://{args.host}:{args.port}/softlayer/{{name}}.js")
    print("     Point LM Studio / Open WebUI / Antigravity at this endpoint\n")

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
