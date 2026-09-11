r"""
FoveAI Wake Listener — Windows PC side
=======================================
Listens on UDP port 9999 for a wake broadcast from the Quest 3 APK.
When received, auto-starts all 3 backend services if they are not already running.

Usage (run once on your PC, add to Windows startup if desired):
    & C:\Users\danie\program\LUMAX\.venv\Scripts\python.exe wake_listener.py

The Quest sends a UDP broadcast {"cmd":"wake","client":"AliceVR_Quest3"}.
This script responds by starting:
  - Backend/app/main.py          (FoveAI soul, port 8400)
  - Backend/stt_whisper_server.py (STT Whisper, port 8402)
  - Backend/tts_stream_server.py  (TTS Edge,    port 8403)
"""

import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WakeListener] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
WAKE_PORT   = 9999
BACKEND_DIR = Path(__file__).resolve().parent
VENV_PYTHON = Path(r"C:\Users\danie\program\LUMAX\.venv\Scripts\python.exe")

# ── XRLF Bundle Runtime ───────────────────────────────────────────────────────
# The .xrlf file is a self-contained binary container with these embedded sections:
#
#  0x01 CORE_GGUF        — Neural core weights (Qwen / Gemma GGUF)
#  0x02 XRL_PRINCIPLES   — Distilled reasoning principia (cognitive exoskeleton)
#  0x03 XRL_GRAPH        — Semantic concept graph
#  0x04 XRL_CLUSTERS     — Cognitive cluster definitions
#  0x05 XRL_PROFILES     — Task profiles: chat / code / vision / reasoning
#  0x06 XRL_EXPANSION    — Expansion rules
#  0x07 XRL_MM_HOOKS     — Multimodal hooks: Kokoro TTS spawned from inside
#  0x08 XRL_MEMORY_DATA  — Foveated memory: SQLite DB + TF-IDF (INSIDE the file)
#  0x09 XRL_MEMORY_SCHEMA— Memory retrieval policy & 6-ring compression config
#  0x0A RUNTIME_META     — Build flags, capability map
#  0x0B CORE_MMPROJ      — Vision projector GGUF (image/video understanding)
#  0x0C CORE_DRAFT_GGUF  — Speculative decoding draft model
#
# Flag: STT_NATIVE (1<<7)  → speech decoded natively by the core model
# Flag: VISION_NATIVE      → image/video input native
# Flag: MEMORY_PERSISTENT  → SQLite re-packed into .xrlf on session end
#
# The separate stt_whisper_server.py is a BRIDGE only:
#   Quest mic (PCM) → port 8402 WebSocket → forward to XRLF core (native STT)
# The tts_stream_server.py is a BRIDGE only:
#   XRLF Kokoro hook output → port 8403 WebSocket → Quest speaker
#
# The foveated-memory Node.js proxy (port 8200) is OPTIONAL / ADDITIVE.
# When running: Soul → 8200 → 8300 (adds in-flight compression for very long sessions)
# When not running: Soul → 8300 directly (embedded memory still works)

XRLF_DEV_DIR    = Path(r"C:\Users\danie\program\LUMAX\Tools\XRLF 1.0 dev")
XRLF_PYTHON     = XRLF_DEV_DIR / ".venv" / "Scripts" / "python.exe"
XRLF_SERVER_PY  = XRLF_DEV_DIR / "api" / "server.py"
XRLF_MODEL_PATH = Path(r"C:\Users\danie\.cache\huggingface\hub\foveai-forge\XRLF\qwen4b-concise-v1.0.xrlf")

# Foveated-memory proxy is optional — only started if script exists
FOVEATED_MEMORY_DIR   = Path(r"C:\Users\danie\program\LUMAX\Tools\foveated-memory")
FOVEATED_MEMORY_ENTRY = FOVEATED_MEMORY_DIR / "server.js"
USE_FOVEATED_PROXY    = FOVEATED_MEMORY_ENTRY.exists()  # auto-detect

# Soul LLM endpoint: prefer foveated proxy if running, else direct to XRLF
SOUL_LLM_UPSTREAM = "http://127.0.0.1:8400/v1" if USE_FOVEATED_PROXY else "http://127.0.0.1:8400/v1"

# ── STARTUP SEQUENCE ─────────────────────────────────────────────────────────
# Each service starts only after its probe_port is confirmed open (or times out).
# startup_delay = extra grace time after probe succeeds before next service starts.
SERVICES = [
    # ① The brain — self-contained, loads all sections from .xrlf
    {
        "name":          "XRLF Bundle Server (8300)",
        "type":          "xrlf",
        "script":        XRLF_SERVER_PY,
        "probe_port":    8300,
        "extra_args":    [
            "--model",      str(XRLF_MODEL_PATH),
            "--port",       "8300",
            "--host",       "0.0.0.0",    # LAN accessible
            "--gpu-layers", "-1",          # full GPU offload
            "--ctx",        "8192",
            "--session",    "AliceVR",
        ],
        "env_extra":     {},
        "startup_delay": 5.0,  # GGUF load + XRL layer injection takes a few seconds
    },
    # ② Optional: foveated-memory proxy (in-flight context compression for long sessions)
    *([{
        "name":          "Foveated Memory Proxy (8200) [optional]",
        "type":          "node",
        "script":        FOVEATED_MEMORY_ENTRY,
        "probe_port":    8200,
        "extra_args":    [],
        "env_extra":     {
            "PORT":            "8200",
            "UPSTREAM_URL":    "http://127.0.0.1:8400",  # → XRLF bundle
            "WORKSPACE_ID":    "AliceVR",
            "XRLF_DEV_DIR":    str(XRLF_DEV_DIR),
            "XRLF_MODEL_FILE": XRLF_MODEL_PATH.name,
        },
        "startup_delay": 2.0,
    }] if USE_FOVEATED_PROXY else []),
    # ③ FoveAI Soul — cognitive WebSocket hub for Quest 3
    {
        "name":          "FoveAI Soul / Cognitive Engine (8400)",
        "type":          "python",
        "script":        BACKEND_DIR / "app" / "main.py",
        "probe_port":    8400,
        "extra_args":    [],
        "env_extra":     {
            "OPENAI_BASE_URL": SOUL_LLM_UPSTREAM,
            "OPENAI_API_KEY":  "AliceVR",
        },
        "startup_delay": 0.0,
    },
    # ④ STT bridge — Quest mic PCM → XRLF native STT
    {
        "name":          "STT Bridge (8402)",
        "type":          "python",
        "script":        BACKEND_DIR / "stt_whisper_server.py",
        "probe_port":    8402,
        "extra_args":    [],
        "env_extra":     {},
        "startup_delay": 0.0,
    },
    # ⑤ TTS bridge — XRLF Kokoro output → Quest speaker
    {
        "name":          "TTS Kokoro Bridge (8403)",
        "type":          "python",
        "script":        BACKEND_DIR / "tts_stream_server.py",
        "probe_port":    8403,
        "extra_args":    [],
        "env_extra":     {},
        "startup_delay": 0.0,
    },
]

_procs: dict[str, subprocess.Popen] = {}
# ─────────────────────────────────────────────────────────────────────────────



# Foveated-memory proxy (Node.js) — wraps XRLF server, adds infinite foveated memory
FOVEATED_MEMORY_DIR   = Path(r"C:\Users\danie\program\LUMAX\Tools\foveated-memory")
FOVEATED_MEMORY_ENTRY = FOVEATED_MEMORY_DIR / "server.js"

# ──────────────────────────────────────────────────────────────────────────────
# STARTUP ORDER — do NOT change this sequence. Each service depends on the one above it.
#
#  8300  XRLF Bundle Server   — Self-contained brain:
#                               GGUF (Qwen 4B) + XRL rational layers
#                               + Kokoro TTS adapter + Whisper STT adapter
#                               + MMPROJ vision adapter
#                               OpenAI-compatible endpoint at /v1
#
#  8200  Foveated Memory Proxy — Node.js proxy wrapping 8300
#                               Adds persistent XRL foveated memory to all requests
#                               Quest clients & FoveAI soul ALWAYS talk via 8200
#
#  8400  FoveAI Soul           — Cognitive engine / WebSocket hub for Quest 3
#                               Routes all LLM calls → 8200 → 8300 → XRLF bundle
#
#  8402  STT WebSocket Bridge  — Quest 3 mic audio → 8300 Whisper adapter (I/O bridge)
#  8403  TTS WebSocket Bridge  — 8300 Kokoro output → Quest 3 speaker (I/O bridge)
# ──────────────────────────────────────────────────────────────────────────────
SERVICES = [
    {
        "name":          "XRLF Bundle Server (8300)",
        "type":          "xrlf",          # uses XRLF_PYTHON, not VENV_PYTHON
        "script":        XRLF_SERVER_PY,
        "probe_port":    8300,
        "extra_args":    [
            "--model",    str(XRLF_MODEL_PATH),
            "--port",     "8300",
            "--host",     "0.0.0.0",      # must be 0.0.0.0, not 127.0.0.1
            "--gpu-layers", "-1",          # full GPU offload
            "--ctx",      "8192",
            "--session",  "AliceVR",
        ],
        "env_extra":     {},
        "startup_delay": 5.0,             # allow model to load into VRAM before dependents
    },
    {
        "name":          "Foveated Memory Proxy (8200)",
        "type":          "node",
        "script":        FOVEATED_MEMORY_ENTRY,
        "probe_port":    8200,
        "extra_args":    [],
        "env_extra":     {
            "PORT":            "8200",
            "UPSTREAM_URL":    "http://127.0.0.1:8400",  # → XRLF bundle server
            "WORKSPACE_ID":    "AliceVR",
            "XRLF_DEV_DIR":    str(XRLF_DEV_DIR),
            "XRLF_MODEL_FILE": "qwen4b-concise-v1.0.xrlf",
        },
        "startup_delay": 2.0,
    },
    {
        "name":          "FoveAI Soul / Cognitive Engine (8400)",
        "type":          "python",
        "script":        BACKEND_DIR / "app" / "main.py",
        "probe_port":    8400,
        "extra_args":    [],
        "env_extra":     {
            "OPENAI_BASE_URL": "http://127.0.0.1:8400/v1",  # → foveated proxy
            "OPENAI_API_KEY":  "AliceVR",
        },
        "startup_delay": 0.0,
    },
    {
        "name":          "STT Whisper Bridge (8402)",
        "type":          "python",
        "script":        BACKEND_DIR / "stt_whisper_server.py",
        "probe_port":    8402,
        "extra_args":    [],
        "env_extra":     {},
        "startup_delay": 0.0,
    },
    {
        "name":          "TTS Kokoro Bridge (8403)",
        "type":          "python",
        "script":        BACKEND_DIR / "tts_stream_server.py",
        "probe_port":    8403,
        "extra_args":    [],
        "env_extra":     {},
        "startup_delay": 0.0,
    },
]

_procs: dict[str, subprocess.Popen] = {}
# ---------------------------------------------------------------------------



def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if something is already listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_service(svc: dict) -> None:
    """Start a backend service subprocess if not already running."""
    name   = svc["name"]
    script = svc["script"]
    port   = svc["probe_port"]

    if is_port_open("127.0.0.1", port):
        logger.info(f"[OK] {name} already running on port {port}")
        return

    if name in _procs:
        proc = _procs[name]
        if proc.poll() is None:
            logger.info(f"[OK] {name} subprocess still alive")
            return
        else:
            logger.warning(f"[!!] {name} process died (code={proc.returncode}), restarting")

    if not script.exists():
        logger.error(f"[ERR] Script not found: {script}")
        return

    logger.info(f"[>>] Starting {name} ...")
    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(script)],
        cwd=str(BACKEND_DIR),
        # Each service gets its own console window so you can see logs
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    _procs[name] = proc
    logger.info(f"[>>] {name} PID {proc.pid}")


def start_all_services() -> None:
    for svc in SERVICES:
        try:
            start_service(svc)
        except Exception as ex:
            logger.error(f"Failed to start {svc['name']}: {ex}")
    logger.info("All services start commands issued.")


def main() -> None:
    logger.info(f"FoveAI Wake Listener started. Listening on UDP port {WAKE_PORT}...")
    logger.info("Waiting for AliceVR Quest3 APK broadcast...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", WAKE_PORT))
    sock.settimeout(60.0)  # log heartbeat every 60s

    last_wake_time = 0.0

    while True:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            logger.debug("Heartbeat — still listening...")
            continue

        try:
            msg = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        if msg.get("cmd") == "wake":
            now = time.time()
            # Debounce: ignore repeated wakes within 10s
            if now - last_wake_time < 10.0:
                logger.debug(f"Wake from {addr} debounced")
                continue

            last_wake_time = now
            logger.info(f"Wake received from {addr} — starting backend services...")
            start_all_services()


if __name__ == "__main__":
    main()
