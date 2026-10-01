"""
run_xrlf.py — XRLF One-Command Launcher
=========================================
Loads xrlf_config.yaml (or a custom config), starts the XRLF runtime
and the OpenAI-compatible API server.

Usage:
    # Start with default config
    python run_xrlf.py

    # Start with custom model
    python run_xrlf.py --model gemma-4-12b-xrl.xrlf --port 8300

    # Self-test (no llama.cpp required)
    python run_xrlf.py --test
"""

import argparse
import os
import sys

# Ensure project root is on the path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── Tiny .env loader (no external dependency) ────────────────────────────────
# xrlf_runtime.py reads XRLF_REPO_ENABLED via os.environ at import time. Python
# does NOT auto-load .env files. This loader reads the local `Tools/XRLF 1.0
# dev/.env` (if present) into os.environ BEFORE xrlf_runtime is imported, so
# the Reactor turns HOT. Critically, it only mutates THIS process's environment
# — it cannot leak into the main proxy (8200), the swarm router, or LM Studio.
def _load_local_env():
    env_path = os.path.join(ROOT, ".env")
    try:
        if not os.path.exists(env_path):
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                key, _, val = s.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and not os.environ.get(key):
                    os.environ[key] = val
    except Exception as e:
        sys.stderr.write(f"[run_xrlf] .env load skipped: {e}\n")


_load_local_env()

try:
    import yaml

    _YAML = True
except ImportError:
    _YAML = False


def load_config(config_path: str = "xrlf_config.yaml") -> dict:
    if _YAML and os.path.exists(config_path):
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    return {}


def run_test(config: dict):
    """
    Self-test: pack a stub XRLF from existing XRL artifacts (no GGUF),
    load it with XRLFRuntime, and run a sample chat.
    """
    import tempfile

    from formats.xrlf_packer import XRLFPacker
    from runtime.xrlf_runtime import XRLFRuntime

    print("\n" + "=" * 60)
    print("  XRLF SELF-TEST")
    print("=" * 60)

    # 1. Pack a stub .xrlf (no GGUF core)
    stub_path = os.path.join(tempfile.mkdtemp(), "test.xrlf")
    packer = XRLFPacker(
        base_model_name="gemma-4-12b-it-qat-GGUF-MoQ",
        xrl_source_model="qwen3.5-4b",
    )
    packer.add_xrl_json_dir("xrl_encoded")
    packer.add_multimodal_hooks()
    packer.add_memory_db(None)  # empty seed
    packer.add_memory_schema()
    packer.add_runtime_meta()
    packer.write(stub_path)

    print(f"\n  Stub XRLF written: {stub_path}")

    # 2. Load with runtime
    rt = XRLFRuntime(stub_path, session_id="test", verbose=True)
    rt.load()

    # 3. Sample chats
    test_prompts = [
        {"role": "user", "content": "Explain semantic compression in two sentences."},
        {"role": "user", "content": "Write a Python function to add two numbers."},
        {
            "role": "user",
            "content": "Describe what you see in this image.",
        },  # vision test
    ]

    for i, msg in enumerate(test_prompts):
        has_image = "image" in msg["content"].lower()
        print(f"\n  --- Test {i + 1}: {'[VISION]' if has_image else ''} ---")
        print(f"  User: {msg['content']}")
        response = rt.chat([msg], has_image=has_image)
        print(f"  XRLF: {response}")

    # 4. Memory test
    print("\n  --- Memory recall test ---")
    rt._memory.set_identity("system_context", "I am XRLF, a hybrid AI model.")
    rt.chat([{"role": "user", "content": "Remember that I am a researcher."}])
    response = rt.chat([{"role": "user", "content": "Who are you and who am I?"}])
    print(f"  Memory recall response: {response}")

    rt.close(repack_memory=False)
    print("\n  ✅ XRLF self-test complete!")


def main():
    parser = argparse.ArgumentParser(description="XRLF Runtime Launcher")
    parser.add_argument("--model", help="Path to .xrlf file (overrides config)")
    parser.add_argument("--port", type=int, help="API port (overrides config)")
    parser.add_argument(
        "--ws-port",
        type=int,
        default=None,
        help="WebSocket IPC port (default: API port + 1)",
    )
    parser.add_argument("--config", default="xrlf_config.yaml", help="Config file path")
    parser.add_argument("--test", action="store_true", help="Run self-test and exit")
    parser.add_argument(
        "--pack",
        action="store_true",
        help="Pack a new .xrlf from config settings, then exit",
    )
    parser.add_argument(
        "--draft",
        help="Path to Draft Model GGUF for speculative decoding (used in --pack)",
    )
    parser.add_argument("--whisper", help="Path to Whisper GGUF model (used in --pack)")
    parser.add_argument("--kokoro", help="Path to Kokoro ONNX model (used in --pack)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)

    # ── Self-test ─────────────────────────────────────────────────────────────
    if args.test:
        run_test(config)
        return

    # ── Pack mode ─────────────────────────────────────────────────────────────
    if args.pack:
        from formats.xrlf_packer import XRLFPacker

        gguf = "foveai-summarizer-draft.gguf"
        output = args.model or config.get("model", "gemma-4-12b-xrl.xrlf")
        memory_db = config.get("memory_db_source", None)

        packer = XRLFPacker(
            base_model_name="gemma-4-12b-it-qat-GGUF-MoQ",
            xrl_source_model="qwen3.5-4b",
        )
        if gguf and os.path.exists(gguf):
            packer.add_gguf(gguf)
        else:
            print(
                "  ⚠️  No GGUF source in config — packing without core GGUF (stub mode)"
            )

        draft = args.draft or config.get("draft_source", "") or ""
        if draft and os.path.exists(draft):
            packer.add_draft_gguf(draft)

        whisper_model = args.whisper or config.get("whisper_source", "") or ""
        if whisper_model and os.path.exists(whisper_model):
            packer.add_whisper_gguf(whisper_model)

        kokoro_model = args.kokoro or config.get("kokoro_source", "") or ""
        if kokoro_model and os.path.exists(kokoro_model):
            packer.add_kokoro_model(kokoro_model)

        packer.add_xrl_json_dir("xrl_encoded")
        packer.add_multimodal_hooks()
        packer.add_memory_db(memory_db)
        packer.add_memory_schema()
        packer.add_runtime_meta()
        packer.write(output)
        return

    # ── Server mode ───────────────────────────────────────────────────────────
    model_path = args.model or config.get("model", "gemma-4-12b-xrl.xrlf")
    port = args.port or config.get("api", {}).get("port", 8300)
    # The HTTP API can stay on localhost, but the WebSocket IPC server must
    # bind to 0.0.0.0 so Quest 3 / network clients can connect.
    # FOVEAI_BACKEND_HOST env var overrides config for network accessibility.
    api_host = config.get("api", {}).get("host", "127.0.0.1")
    ws_host = os.environ.get("FOVEAI_BACKEND_HOST", "0.0.0.0")
    gpu_layers = config.get("gpu_layers", -1)
    n_ctx = config.get("n_ctx", 8192)
    session_id = config.get("session", {}).get("id", "default")
    persistent = config.get("session", {}).get("persistent_memory", True)
    verbose = args.verbose or config.get("xrl", {}).get("verbose", False)

    if not os.path.exists(model_path):
        print(f"\n  ❌ Model not found: {model_path}")
        print("  Run with --pack to create a new .xrlf, or --test for a self-test.\n")
        sys.exit(1)

    import asyncio

    import uvicorn

    from api.server import create_app
    from Backend.app.IPC.websocket_server import IPCServer
    from runtime.xrlf_runtime import XRLFRuntime

    runtime = XRLFRuntime(
        xrlf_path=model_path,
        session_id=session_id,
        n_gpu_layers=gpu_layers,
        n_ctx=n_ctx,
        persistent_memory=persistent,
        verbose=verbose,
    )
    runtime.load()
    app = create_app(runtime)

    # ── WebSocket IPC Server (socket-based, minimal latency) ─────────────
    # Runs alongside the HTTP API on port+1 (e.g., 8402 HTTP → 8403 WS)
    # or on a dedicated WS port. The Quest client and Multigate connect here.
    ws_port = args.ws_port if args.ws_port else (port + 1)
    ipc_server = IPCServer(runtime=runtime, host=ws_host, port=ws_port)
    ipc_server.runtime_url = f"http://127.0.0.1:{port}"

    # Set fallback URLs for STT/TTS (used only when model lacks native audio)
    ipc_server.soul_url = os.environ.get("SOUL_URL", "http://127.0.0.1:8402")
    ipc_server.mouth_url = os.environ.get("MOUTH_URL", f"http://127.0.0.1:{port}")

    print(f"\n  🚀 XRLF API   → http://{api_host}:{port}/v1")
    print(
        f"  🔌 XRLF Socket → ws://{ws_host}:{ws_port}/ws  (Quest clients connect here)"
    )
    print(f"     Model : {runtime.model_name}")
    print(f"     Memory: embedded foveated (6-ring, persistent={persistent})")
    print("     TTS   : provider-driven (http / Piper / espeak / stub)")
    print(f"\n  HTTP clients  → http://{api_host}:{port}/v1/chat/completions")
    print(
        f"  Socket clients → ws://{ws_host}:{ws_port}/ws  (event: chat, payload: {{text: ...}})\n"
    )

    # Run both servers: WebSocket in a background thread, HTTP in main thread
    import threading

    def _run_ws():
        """Run the WebSocket IPC server in its own event loop thread."""
        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)

        # Suppress Windows Proactor connection_lost exception noise during socket resets/shutdowns
        def _silent_loop_exception_handler(loop, context):
            exception = context.get("exception")
            if isinstance(exception, (ConnectionResetError, ConnectionAbortedError)):
                return
            msg = str(context.get("message", "")).lower()
            if "connection_lost" in msg or "connection_lost" in str(context).lower():
                return
            loop.default_exception_handler(context)

        ws_loop.set_exception_handler(_silent_loop_exception_handler)

        try:
            ws_loop.run_until_complete(ipc_server.start())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        except Exception as e:
            print(f"  ⚠️ WebSocket server notice: {e}")

    ws_thread = threading.Thread(target=_run_ws, daemon=True, name="xrlf-ws")
    ws_thread.start()
    print(f"  📡 WebSocket thread started ({ws_thread.name})")

    # Run HTTP server in the main thread (uvicorn manages its own loop)
    try:
        uvicorn.run(app, host=api_host, port=port, log_level="warning")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
