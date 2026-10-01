#!/usr/bin/env python3
"""
FoveAI_Console.py — Console (TUI) port of FoveAI_Taskbar_Linux.py.

Numbered-menu control app for the FoveAI fleet. Works over SSH (Quest)
and in any local terminal — no pystray/GTK dependency.

Settings panel interlink: http://127.0.0.1:5177/settings.html (multigate).
Includes a port of Scripts/windows/Set-FoveAISetting.ps1: arbitrary .env
key writes + FoveaLevel shortcut, with optional service restart for
FoveAI_* / XRLF_PROXY_AGGRESSION keys.

Usage:
    python3 FoveAI_Console.py            # interactive menu
    python3 FoveAI_Console.py <command>  # any panel action as an argument —
                                         # 'help' lists them all (set/get/env/
                                         # engine/mode/model/load/unload/fovea/
                                         # toggle/tts/stt/subsystems/diag/...)
                                         # every write updates .env AND pushes
                                         # live to proxy :8400 + runtime :8402
                                         # + WS :8403 (Set-FoveAISetting port)
"""

import base64
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.request

FOVEAI_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(FOVEAI_DIR, ".venv", "bin", "python")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable

SLEIPNIR_SH = os.path.join(FOVEAI_DIR, "sleipnir_launcher.sh")
SETTINGS_URL = "http://127.0.0.1:5177/settings.html"
DASHBOARD_URL = "http://127.0.0.1:8401/memory/settings.html"
KIOSK_URL = "http://127.0.0.1:8401/memory/prompt-kiosk.html"
XRLF_API = "http://127.0.0.1:8402"
PROXY_API = "http://127.0.0.1:8400"
WS_IPC_PORT = 8403

# ─── Service registry (full .env port scheme) ───────────────────────
SERVICES = [
    ("Memory Proxy", 8400, "/health"),
    ("Dashboard", 8401, "/api/status"),
    ("XRLF Runtime", 8402, "/health"),
    ("WS IPC", 8403, None),
    ("TTS", 8406, None),
    ("Memory Service", 8407, None),
    ("Creative Service", 8408, None),
    ("STT / Ignition", 8409, None),
    ("Motor/Autonomous", 8410, None),
    ("Subconscious", 8411, None),
    ("XR Vessel", 5176, "/"),
    ("Multigate WebUI", 5177, "/"),
]

FOVEA_LEVELS = {
    0: "Auto",
    1: "Minimal",
    2: "Light",
    3: "Moderate",
    4: "Aggressive",
    5: "Maximum",
    6: "Off",
}

PERSONA_MODELS = {
    "gemma_e2b": {
        "name": "Gemma 4 E2B MTP (Default Persona)",
        "id": "gemma-4-e2b-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf",
        "size_gb": 3.3,
        "multimodal": True,
    },
    "gemma_12b": {
        "name": "Gemma 4 12B MTP (Heavy)",
        "id": "gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "size_gb": 5.1,
        "multimodal": True,
    },
    "qwen_4b": {
        "name": "Qwen 3.5 4B MTP (Coder)",
        "id": "qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "size_gb": 2.9,
        "multimodal": True,
    },
    "smolvlm2": {
        "name": "SmolVLM2 500M (Vision)",
        "id": "smolvlm2-500m-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/smolvlm2-500m-multimodal-v1.0.xrlf",
        "size_gb": 0.5,
        "multimodal": True,
    },
}

ROUTER_MODELS = {
    "router_v2": {
        "name": "FoveAI Omni Router v2",
        "id": "foveai-omni-router-v2.xrlf",
        "xrlf_path": "foveai-omni-router-v2.xrlf",
        "size_gb": 1.4,
    },
    "router_v1": {
        "name": "FoveAI Omni Router v1 (Legacy)",
        "id": "foveai-omni-router.xrlf",
        "xrlf_path": "foveai-omni-router.xrlf",
        "size_gb": 0.9,
    },
}

SOFTLAYER_CONFIGS = ["behavior_config.js", "experience_config.js", "hud_config.js"]
SOFTLAYER_MODULES = [
    "lighting.js",
    "sky.js",
    "particles.js",
    "chameleon.js",
    "clothing.js",
    "wall.js",
]

# ─── Helpers ────────────────────────────────────────────────────────


def env_path() -> str:
    p = os.path.join(FOVEAI_DIR, ".env")
    return p if os.path.exists(p) else os.path.join(os.path.dirname(FOVEAI_DIR), ".env")


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(env_path(), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return values


def set_env_key(key: str, value: str) -> None:
    """Port of Scripts/windows/Set-FoveAISetting.ps1."""
    p = env_path()
    lines = []
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip() and not line.startswith("#") and line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
    with open(p, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"  Set {key}={value} in {p}")


def maybe_restart_for_key(key: str) -> None:
    """Set-FoveAISetting.ps1 auto-restart behavior for critical keys."""
    if (
        key == "XRLF_PROXY_AGGRESSION"
        or key.startswith("FoveAI_")
        or key.startswith("FOVEAI_")
    ):
        ans = input("  Restart services to apply? [y/N] ").strip().lower()
        if ans == "y":
            stack("restart")


def port_open(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def http_ok(port: int, path: str | None) -> str:
    if not port_open(port):
        return "down"
    if not path:
        return "up"
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            headers={"User-Agent": "FoveAI-Console/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return "up" if resp.status in (200, 204, 302) else "dormant"
    except Exception:
        return "dormant"


def kill_port_listeners(ports: list) -> int:
    killed = 0
    for port in ports:
        try:
            out = subprocess.check_output(
                ["ss", "-tlnp", f"sport = :{port}"], text=True, timeout=2
            )
            for line in out.splitlines():
                if "pid=" not in line:
                    continue
                pid_str = line.split("pid=")[1].split(",")[0].split(")")[0].strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if pid != os.getpid():
                        os.kill(pid, signal.SIGTERM)
                        killed += 1
        except Exception:
            pass
    return killed


def kill_process_by_name(name: str) -> int:
    try:
        out = subprocess.check_output(["pgrep", "-f", name], text=True, timeout=2)
        pids = [int(p) for p in out.strip().splitlines() if p.strip().isdigit()]
        for pid in pids:
            if pid != os.getpid():
                os.kill(pid, signal.SIGTERM)
        return len(pids)
    except Exception:
        return 0


def open_url(url: str) -> None:
    try:
        subprocess.Popen(
            ["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print(f"  Opened {url}")
    except FileNotFoundError:
        print(f"  (no xdg-open — headless?) URL: {url}")


# ─── Live API helpers (proxy :8400 + runtime :8402 + WS :8403) ────────


def http_get_json(url: str, timeout: float = 3.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FoveAI-Console/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def http_post(
    url: str, payload: dict | None, timeout: float = 10.0
) -> tuple[int, str]:
    try:
        data = json.dumps(payload).encode() if payload is not None else b""
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "FoveAI-Console/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")[:400]
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode(errors="replace")[:400]
        except Exception:
            return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def proxy_set(key: str, val: str) -> None:
    """Write .env AND push live to the running proxy (/api/setting applies
    routing changes without a restart)."""
    set_env_key(key, val)
    st, txt = http_post(f"{PROXY_API}/api/setting", {"key": key, "val": val}, timeout=4)
    if st:
        print(f"  live push → proxy :8400  [{st}] {txt[:120]}")
    else:
        print("  proxy :8400 unreachable — .env written, applies on next start")


def ws_send(
    payload: dict, host: str = "127.0.0.1", port: int = WS_IPC_PORT, path: str = "/"
) -> bool:
    """Minimal dependency-free WebSocket text send (handshake + masked frame)."""
    try:
        s = socket.create_connection((host, port), timeout=2)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall(
            (
                f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        resp = s.recv(4096)
        if b" 101" not in resp.split(b"\r\n", 1)[0]:
            s.close()
            return False
        data = json.dumps(payload).encode()
        mask = os.urandom(4)
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        s.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        s.close()
        return True
    except Exception:
        return False


def send_ws_setting(setting: str, value) -> None:
    """Push a live setting to the runtime over the IPC socket (tts_engine etc)."""
    ok = ws_send({"event": "settings", "payload": {"setting": setting, "value": value}})
    print(
        f"  WS :{WS_IPC_PORT} {setting}={value} → {'sent' if ok else 'FAILED (ws down?)'}"
    )


def vram() -> tuple[float, float]:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        )
        used, total = [float(x) / 1024 for x in out.strip().split(",")]
        return used, total
    except Exception:
        return 0.0, 0.0


def sleipnir(*args: str) -> None:
    print(f"  $ bash sleipnir_launcher.sh {' '.join(args)}")
    subprocess.run(["bash", SLEIPNIR_SH, *args], cwd=FOVEAI_DIR)


def stack(action: str) -> None:
    sleipnir(action if action != "light" else "--light")


# ─── Status ─────────────────────────────────────────────────────────


def print_status() -> None:
    env = read_env()
    used, total = vram()
    from server_config import detect_lan_ip

    lan_ip = env.get("FOVEAI_SERVER_IP", "").strip() or detect_lan_ip()
    print("\n─── FoveAI Fleet ─────────────────────────────────")
    for name, port, path in SERVICES:
        st = http_ok(port, path)
        mark = {"up": "●", "dormant": "◐", "down": "○"}[st]
        extra = ""
        if port == 8402:
            h = http_get_json(f"{XRLF_API}/health", timeout=1.5) or {}
            state = h.get("load_state")
            if state:
                extra = f" [{state}{' — ' + h['model'] if h.get('model') else ''}]"
            if h.get("load_error"):
                extra += f" ERR:{h['load_error'][:60]}"
        print(f"  {mark} :{port:<5} {name:<18} {st}{extra}")
    if total:
        pct = used / total * 100
        print(f"\n  VRAM: {used:.1f}/{total:.0f} GB ({pct:.0f}%)")
    if lan_ip:
        print(f"  LAN IP (Quest): {lan_ip}   panel: http://{lan_ip}:8401/settings.html")
    print(
        f"\n  persona : {env.get('FOVEAI_MODEL_ACTIVE_ID', env.get('FOVEAI_MAIN_MODEL', '-'))}"
    )
    print(f"  router  : {env.get('FOVEAI_OMNI_ROUTER_MODEL', '-')}")
    print(
        f"  fovea   : {env.get('XRLF_PROXY_AGGRESSION', '0')} "
        f"({FOVEA_LEVELS.get(int(env.get('XRLF_PROXY_AGGRESSION', '0') or 0), '?')})"
    )
    print(
        f"  mode    : {env.get('FoveAI_COGNITIVE_MODE', 'local')}  |  "
        f"voice: {env.get('FoveAI_VOICE_ENABLED', '-')}  mic: {env.get('FoveAI_MIC_ENABLED', '-')}  |  "
        f"tts: {env.get('FoveAI_TTS_PROVIDER', 'kokoro')}  stt: {env.get('FoveAI_STT_PROVIDER', 'whisper')}"
    )
    print(
        f"  frontend: {env.get('XRLF_FRONTEND_UI_PRESET', env.get('FOVEAI_FRONTEND_UI', '3d_avatar'))}"
    )
    print("──────────────────────────────────────────────────\n")


# ─── Menus ──────────────────────────────────────────────────────────


def menu(title: str, items: list) -> None:
    """items: list of (label, callable). 0/back returns."""
    while True:
        print(f"\n== {title} ==")
        for i, (label, _) in enumerate(items, 1):
            print(f"  {i}. {label}")
        print("  0. back")
        choice = input("> ").strip()
        if choice in ("0", "q", "back"):
            return
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                items[idx][1]()
            else:
                print("  ?")
        except (ValueError, IndexError):
            print("  ?")


# ─── Runtime / Mode / Diagnostics (settings.html ports) ─────────────


def runtime_status() -> dict | None:
    h = http_get_json(f"{XRLF_API}/health", timeout=2)
    if h is None:
        print("  runtime :8402 — DOWN (port not listening)")
        return None
    print(
        f"  runtime :8402 — state={h.get('load_state', '?')} "
        f"loaded={h.get('loaded')} model={h.get('model') or '—'}"
    )
    if h.get("load_error"):
        print(f"    load_error: {h['load_error']}")
    return h


def wait_runtime_loaded(timeout_s: int = 360) -> bool:
    """Poll :8402/health until loaded/error/timeout. The runtime binds the port
    before the model finishes loading, so 'loading' is a real state now."""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout_s:
        h = http_get_json(f"{XRLF_API}/health", timeout=2)
        if h is None:
            state = "waiting (port not bound yet)"
        elif h.get("loaded"):
            print(f"\n  ✅ loaded — {h.get('model')}")
            return True
        elif h.get("load_state") == "error":
            print(f"\n  ❌ load error: {h.get('load_error')}")
            return False
        else:
            state = h.get("load_state", "?")
        if state != last:
            print(f"  … {state}")
            last = state
        else:
            print(".", end="", flush=True)
        time.sleep(2)
    print(f"\n  ⏳ still not loaded after {timeout_s}s (check ~/xrlf_live.log)")
    return False


def runtime_load_model(m: dict) -> None:
    """Hot-swap via /load when the runtime is alive, else cold-spawn run_xrlf."""
    full = os.path.join(FOVEAI_DIR, m["xrlf_path"])
    if not os.path.exists(full):
        print(f"  MISSING: {m['xrlf_path']}")
        return
    h = runtime_status()
    if h and h.get("load_state") == "loading":
        print("  runtime is already loading — wait for it or kill it first")
        return
    if h is not None:
        st, txt = http_post(f"{XRLF_API}/load", {"model": m["xrlf_path"]}, timeout=600)
        print(f"  /load → [{st}] {txt[:200]}")
    else:
        kill_port_listeners([8402, 8403])
        e = os.environ.copy()
        e["XRLF_REPO_ENABLED"] = "true"
        subprocess.Popen(
            [
                VENV_PYTHON,
                "run_xrlf.py",
                "--model",
                m["xrlf_path"],
                "--port",
                "8402",
                "--ws-port",
                "8403",
            ],
            cwd=FOVEAI_DIR,
            env=e,
            stdout=open("/home/lumba/xrlf_live.log", "a"),
            stderr=subprocess.STDOUT,
        )
        print(f"  spawned run_xrlf.py → {m['name']} (log: ~/xrlf_live.log)")


def persona_apply(key: str) -> None:
    """Select a persona model: write .env everywhere + optionally relaunch."""
    m = PERSONA_MODELS[key]
    set_env_key("XRLF_MODEL_LOCAL_ID", m["id"])
    set_env_key("FOVEAI_MODEL_ACTIVE_ID", m["id"])
    set_env_key("FOVEAI_MAIN_MODEL", m["id"])
    runtime_load_model(m)


def runtime_menu() -> None:
    """Port of the settings panel model card: status / load / unload / restart."""

    def load_model():
        items = [
            (f"{m['name']} [{m['size_gb']}GB]", m) for m in PERSONA_MODELS.values()
        ]
        for i, (label, _) in enumerate(items, 1):
            print(f"  {i}. {label}")
        raw = input("  model # (0=cancel): ").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(items)):
            return
        runtime_load_model(items[int(raw) - 1][1])
        if input("  watch until loaded? [Y/n] ").strip().lower() != "n":
            wait_runtime_loaded()

    def unload():
        st, txt = http_post(f"{XRLF_API}/unload", {}, timeout=60)
        print(f"  /unload → [{st}] {txt[:200]}")

    menu(
        "XRLF Runtime :8402/:8403",
        [
            ("Status (load_state/model/error)", runtime_status),
            ("Load / hot-swap model", load_model),
            ("Unload model (frees VRAM, keeps process)", unload),
            ("Wait until loaded (watch load_state)", lambda: wait_runtime_loaded()),
            (
                "Kill runtime process",
                lambda: print(
                    f"  killed {kill_process_by_name('run_xrlf') + kill_port_listeners([8402, 8403])} proc(s)"
                ),
            ),
        ],
    )


ENGINE_PRESETS = {
    "xrlf": ("xrlf_proxy", "local", "http://127.0.0.1:8402/v1", "XRLF local"),
    "lmstudio": ("lmstudio", "local", "http://127.0.0.1:1234/v1", "LM Studio local"),
    "cloud": ("cloud", "cloud", "https://ollama.com/v1", "Cloud"),
}


def engine_apply(engine: str) -> None:
    provider, cognitive, base_url, label = ENGINE_PRESETS[engine]
    print(f"  → {label}")
    proxy_set("XRLF_LLM_PROVIDER", provider)
    proxy_set("XRLF_COGNITIVE_MODE", cognitive)
    proxy_set("XRLF_CHAT_PROVIDER", provider)
    proxy_set("XRLF_LOCAL_BASE_URL", base_url)
    print("  routing updated (live push + .env)")


def mode_menu() -> None:
    """Port of the panel's Mode/Engine steps — writes env + live-pushes routing."""
    env = read_env()
    cur = env.get("XRLF_LLM_PROVIDER", "xrlf_proxy")
    menu(
        f"Mode & Engine (cur: {cur})",
        [
            ("Local → XRLF Runtime (:8402)", lambda: engine_apply("xrlf")),
            ("Local → LM Studio (:1234)", lambda: engine_apply("lmstudio")),
            ("Cloud (Ollama/external)", lambda: engine_apply("cloud")),
        ],
    )


def _loaded_model_name() -> str:
    h = http_get_json(f"{XRLF_API}/health", timeout=2) or {}
    return h.get("model") or "lumax-plumax-omni-router-v2"


def diag_system_test() -> None:
    print("  🧪 System test — chat ping via proxy :8400")
    body = {
        "model": _loaded_model_name(),
        "messages": [
            {
                "role": "user",
                "content": "Hello, can you hear me? Reply in one short sentence.",
            }
        ],
        "stream": False,
        "max_tokens": 80,
    }
    t0 = time.time()
    st, txt = http_post(f"{PROXY_API}/v1/chat/completions", body, timeout=60)
    ms = round((time.time() - t0) * 1000)
    try:
        data = json.loads(txt) if txt else {}
        reply = data["choices"][0]["message"]["content"]
        print(f"  ✅ PASS — {ms}ms  model={data.get('model')}")
        print(f'     "{reply}"')
    except Exception:
        print(f"  ❌ FAIL — HTTP {st}: {txt[:200]}")


def diag_coherence() -> None:
    import random

    q = random.choice(
        [
            "What is 7 multiplied by 8? Reply with just the number.",
            "Name three colors in the rainbow.",
            "If I have 5 apples and eat 2, how many are left? Reply with just the number.",
        ]
    )
    print(f'  🧠 Coherence test — "{q}"')
    body = {
        "model": _loaded_model_name(),
        "messages": [{"role": "user", "content": q}],
        "stream": False,
        "max_tokens": 100,
    }
    st, txt = http_post(f"{PROXY_API}/v1/chat/completions", body, timeout=60)
    try:
        data = json.loads(txt) if txt else {}
        reply = data["choices"][0]["message"]["content"].strip()
        print(f'     "{reply}"')
        print("  ✅ PASS" if reply and "⚠️" not in reply else "  ⚠️ suspicious reply")
    except Exception:
        print(f"  ❌ FAIL — HTTP {st}: {txt[:200]}")


def diag_context() -> None:
    healer = http_get_json(f"{PROXY_API}/api/healer-state", timeout=3) or {}
    env = http_get_json(f"{PROXY_API}/api/env", timeout=3) or {}
    if not healer and not env:
        print("  ❌ proxy :8400 unreachable")
        return
    real = healer.get("currentBudget", 0)
    spoofed = int(env.get("XRLF_SPOOF_CONTEXT_WINDOW") or 32768)
    print(f"  provider : {env.get('XRLF_LLM_PROVIDER', '?')}")
    print(f"  mode     : {env.get('XRLF_COGNITIVE_MODE', '?')}")
    print(
        f"  budget   : {real} / {healer.get('maxBudget', 0)} chars "
        f"(shrinks={healer.get('totalShrinks', 0)}, ok-streak={healer.get('consecutiveOk', 0)})"
    )
    width = 40
    filled = min(width, int(width * real / spoofed)) if spoofed else 0
    print(
        f"  ctx      : [{'█' * filled}{'·' * (width - filled)}] real {real} / spoofed {spoofed}"
    )
    print(
        f"  pipeline : Client → Proxy (foveation) → XRLF :8402 → GGUF  (~{real // 4} tok/req)"
    )


def diag_subsystems() -> None:
    """Server-side probe via proxy /api/subsystems (checks run on the PC)."""
    data = http_get_json(f"{PROXY_API}/api/subsystems", timeout=10)
    if not data:
        print("  proxy :8400 unreachable or endpoint missing — local port scan instead")
        for name, port, path in SERVICES:
            st = http_ok(port, path)
            mark = {"up": "●", "dormant": "◐", "down": "○"}[st]
            print(f"  {mark} :{port:<5} {name:<18} {st}")
        return
    for c in data.get("checks", []):
        ok = c["state"] in ("online", "listening")
        mark = "✅" if ok else ("⚠️" if c["state"] == "dormant" else "❌")
        extra = f" http:{c['http_status']}" if c.get("http_status") else ""
        if c.get("port") == 8402 and c.get("load_state"):
            extra += f" {c['load_state']}" + (
                f" ({c['model']})" if c.get("model") else ""
            )
            if c.get("load_error"):
                extra += f" ERR:{c['load_error'][:60]}"
        print(f"  {mark} :{c['port']:<5} {c['name']:<18} {c['state']}{extra}")


def diagnostics_menu() -> None:
    menu(
        "Diagnostics",
        [
            ("System test (chat ping :8400)", diag_system_test),
            ("Coherence test (random question)", diag_coherence),
            ("Context debugger (healer budget)", diag_context),
            ("Subsystems health (server-side)", diag_subsystems),
            (
                "Run all",
                lambda: (diag_subsystems(), diag_context(), diag_system_test()),
            ),
        ],
    )


def stack_menu() -> None:
    menu(
        "Stack (sleipnir)",
        [
            ("Start FULL stack (proxy + XRLF model)", lambda: stack("start")),
            ("Start LIGHT (backend only, no model)", lambda: stack("light")),
            ("Restart stack", lambda: stack("restart")),
            ("Stop stack", lambda: stack("stop")),
            ("Fleet status", lambda: sleipnir("status")),
        ],
    )


def proxy_menu() -> None:
    def start():
        subprocess.Popen(
            ["node", "server.js"],
            cwd=os.path.join(FOVEAI_DIR, "foveated-memory"),
            stdout=open("/home/lumba/foveated_proxy.log", "a"),
            stderr=subprocess.STDOUT,
        )
        print("  Proxy starting on :8400/:8401")

    menu(
        "Memory Proxy :8400/:8401",
        [
            ("Start proxy", start),
            (
                "Stop proxy",
                lambda: print(
                    f"  killed {kill_port_listeners([8400, 8401])} listener(s)"
                ),
            ),
            ("Restart proxy", lambda: (kill_port_listeners([8400, 8401]), start())),
        ],
    )


def persona_menu() -> None:
    env = read_env()
    cur = env.get("FOVEAI_MODEL_ACTIVE_ID", env.get("FOVEAI_MAIN_MODEL", ""))

    def pick(key):
        m = PERSONA_MODELS[key]
        set_env_key("XRLF_MODEL_LOCAL_ID", m["id"])
        set_env_key("FOVEAI_MODEL_ACTIVE_ID", m["id"])
        set_env_key("FOVEAI_MAIN_MODEL", m["id"])
        ans = input("  Load this model on the runtime now? [y/N] ").strip().lower()
        if ans == "y":
            runtime_load_model(m)

    items = []
    for k, m in PERSONA_MODELS.items():
        sel = "✓ " if m["id"] == cur else "  "
        exists = os.path.exists(os.path.join(FOVEAI_DIR, m["xrlf_path"]))
        tag = "" if exists else " [MISSING]"
        mm = " [mm]" if m["multimodal"] else ""
        items.append(
            (
                f"{sel}{m['name']} [{m['size_gb']}GB]{mm}{tag}",
                (lambda kk: lambda: pick(kk))(k),
            )
        )
    items.append(
        (
            "Unload models & free VRAM",
            lambda: print(
                f"  killed {kill_process_by_name('run_xrlf') + kill_process_by_name('llama-server')} proc(s)"
            ),
        )
    )
    menu("Persona Model", items)


def router_menu() -> None:
    env = read_env()
    cur = env.get("FOVEAI_OMNI_ROUTER_MODEL", "")

    def pick(key):
        m = ROUTER_MODELS[key]
        set_env_key("FOVEAI_OMNI_ROUTER_MODEL", m["id"])
        set_env_key("XRLF_ROUTER_MODEL", m["id"])
        print(f"  Router → {m['name']}")

    items = [
        (
            f"{'✓ ' if m['id'] == cur else '  '}{m['name']} [{m['size_gb']}GB]",
            (lambda kk: lambda: pick(kk))(k),
        )
        for k, m in ROUTER_MODELS.items()
    ]
    menu("Router Model", items)


def settings_menu() -> None:
    def set_key():
        kv = input("  KEY=VALUE : ").strip()
        if "=" not in kv:
            print("  need KEY=VALUE")
            return
        k, v = kv.split("=", 1)
        proxy_set(k.strip(), v.strip())
        maybe_restart_for_key(k.strip())

    def show_env():
        for k, v in sorted(read_env().items()):
            disp = (
                "***"
                if any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASS"))
                else v
            )
            print(f"  {k}={disp}")

    menu(
        "Settings",
        [
            (f"Open settings panel ({SETTINGS_URL})", lambda: open_url(SETTINGS_URL)),
            ("Set .env key (Set-FoveAISetting port)", set_key),
            (
                f"Set foveation level ({'/'.join(f'{k}={v}' for k, v in FOVEA_LEVELS.items())})",
                lambda: set_fovea_cli(),
            ),
            ("Show .env (secrets masked)", show_env),
        ],
    )


def set_fovea_cli() -> None:
    raw = input("  level 0-6: ").strip()
    try:
        lvl = int(raw)
    except ValueError:
        print("  not a number")
        return
    set_env_key("XRLF_PROXY_AGGRESSION", str(lvl))
    print(f"  Foveation → {FOVEA_LEVELS.get(lvl, lvl)}")
    maybe_restart_for_key("XRLF_PROXY_AGGRESSION")


def voice_menu() -> None:
    env = read_env()

    def tog(k, on):
        proxy_set(k, "true" if on else "false")

    v = env.get("FoveAI_VOICE_ENABLED", "").lower() == "true"
    m = env.get("FoveAI_MIC_ENABLED", "").lower() == "true"
    t = env.get("FoveAI_TTS_PROVIDER", "kokoro")
    s = env.get("FoveAI_STT_PROVIDER", "whisper")
    menu(
        "Voice",
        [
            (
                f"Voice output [{'on' if v else 'off'}] → toggle",
                lambda: tog("FoveAI_VOICE_ENABLED", not v),
            ),
            (
                f"Microphone [{'on' if m else 'off'}] → toggle",
                lambda: tog("FoveAI_MIC_ENABLED", not m),
            ),
            (f"TTS → kokoro (cur: {t})", lambda: set_tts("kokoro")),
            (f"TTS → websocket (cur: {t})", lambda: set_tts("websocket")),
            (f"TTS → edgetts (cur: {t})", lambda: set_tts("edgetts")),
            (f"STT → whisper (cur: {s})", lambda: set_stt("whisper")),
            (f"STT → browser (cur: {s})", lambda: set_stt("browser")),
        ],
    )


def set_tts(p: str) -> None:
    proxy_set("XRLF_TTS_PROVIDER", p)
    proxy_set("FoveAI_TTS_PROVIDER", p)
    send_ws_setting("tts_engine", p)


def set_stt(p: str) -> None:
    proxy_set("XRLF_STT_PROVIDER", p)
    proxy_set("FoveAI_STT_PROVIDER", p)
    send_ws_setting("stt_engine", p)


def softlayer_menu() -> None:
    def hit(path):
        try:
            with urllib.request.urlopen(f"{XRLF_API}{path}", timeout=2) as r:
                print(f"  {path} → {r.status}")
                return r.read()
        except Exception as e:
            print(f"  {path} → FAIL {e}")
            return None

    def list_mods():
        raw = hit("/softlayer/modules")
        if raw:
            try:
                print("  modules:", ", ".join(json.loads(raw).get("modules", [])))
            except Exception:
                pass

    items = [
        ("List modules", list_mods),
        (
            "Reload all (frontend re-fetches on next init)",
            lambda: hit("/softlayer/modules"),
        ),
    ]
    items += [
        (f"Reload config {c}", (lambda cc: lambda: hit(f"/softlayer/{cc}"))(c))
        for c in SOFTLAYER_CONFIGS
    ]
    items += [
        (f"Reload module {m}", (lambda mm: lambda: hit(f"/softlayer/modules/{mm}"))(m))
        for m in SOFTLAYER_MODULES
    ]
    menu("SoftLayer (XR Vessel :8402)", items)


def tools_menu() -> None:
    def top_ram():
        try:
            out = subprocess.check_output(
                ["ps", "-eo", "comm,rss", "--sort=-rss"], text=True, timeout=3
            )
            for line in out.splitlines()[1:8]:
                parts = line.split()
                print(f"  {parts[0]:<24} {int(parts[1]) // 1024} MB")
        except Exception as e:
            print(f"  {e}")

    def drop_caches():
        print("  sync + drop_caches requires root — showing biggest consumers instead")
        top_ram()

    def health():
        try:
            with urllib.request.urlopen(f"{XRLF_API}/health", timeout=3) as r:
                print("  /health:", r.read().decode()[:200])
        except Exception as e:
            print(f"  XRLF health: {e}")

    menu(
        "Tools",
        [
            ("XRLF /health", health),
            ("Top RAM consumers", top_ram),
            (
                "Free VRAM (kill run_xrlf/llama-server)",
                lambda: print(
                    f"  killed {kill_process_by_name('run_xrlf') + kill_process_by_name('llama-server')} proc(s)"
                ),
            ),
            ("Drop caches / free RAM", drop_caches),
            (
                "Kill zombie port listeners (8400-8411)",
                lambda: print(
                    f"  killed {kill_port_listeners(list(range(8400, 8412)))} listener(s)"
                ),
            ),
        ],
    )


def openers_menu() -> None:
    menu(
        "Open",
        [
            (f"Settings panel — {SETTINGS_URL}", lambda: open_url(SETTINGS_URL)),
            (f"Memory dashboard — {DASHBOARD_URL}", lambda: open_url(DASHBOARD_URL)),
            (f"Prompt kiosk — {KIOSK_URL}", lambda: open_url(KIOSK_URL)),
            (
                "Multigate portal — http://127.0.0.1:5177",
                lambda: open_url("http://127.0.0.1:5177"),
            ),
            (
                "XR Vessel — http://127.0.0.1:5176",
                lambda: open_url("http://127.0.0.1:5176"),
            ),
        ],
    )


def main_menu() -> None:
    while True:
        print_status()
        menu(
            "FoveAI Console",
            [
                ("Stack control (start/stop/light/restart)", stack_menu),
                ("XRLF runtime :8402 (load/unload/status)", runtime_menu),
                ("Mode & engine (local/cloud routing)", mode_menu),
                ("Memory proxy :8400/:8401", proxy_menu),
                ("Persona model select / unload", persona_menu),
                ("Router model select", router_menu),
                ("Settings (.env, foveation, panel :5177)", settings_menu),
                ("Voice / TTS / STT", voice_menu),
                ("SoftLayer modules", softlayer_menu),
                ("Open panels & frontends", openers_menu),
                ("Diagnostics (system/coherence/context/subsystems)", diagnostics_menu),
                ("Tools (health, RAM, VRAM, zombies)", tools_menu),
            ],
        )
        break


# ─── CLI entry — every menu action is also a command ────────────────
# Commands write .env AND live-push to the proxy (:8400 /api/setting),
# the runtime (:8402), and the IPC socket (:8403) where applicable —
# the same automatic env+live update the Windows Set-FoveAISetting did.

USAGE = """FoveAI Console — command reference

  status                    fleet status (ports, VRAM, persona, mode)
  runtime                   XRLF :8402 status (load_state/model/error)
  runtime wait [secs]       block until the model reports loaded
  model list                list persona models
  model <key|id-substr>     select persona + load on runtime
  load <path.xrlf>          runtime /load (hot-swap)
  unload                    runtime /unload (frees VRAM)
  restart runtime|proxy     restart via proxy control
  stack start|stop|restart|light   sleipnir stack control
  mode local|cloud          routing mode
  engine xrlf|lmstudio|cloud       provider + base URL (live)
  frontend multigate|xr_vessel|3d_avatar
  set KEY=VALUE             .env write + live proxy push
  get KEY                   read env value (secrets masked)
  env [filter]              dump env
  toggle voice|mic on|off
  tts kokoro|websocket|edgetts     env + WS push
  stt whisper|browser              env + WS push
  fovea 0-6                 foveation level (live)
  cap N                     cloud max-tokens cap (live)
  preserve N                preserve-last turns (live)
  ws <setting> <value>      raw WS IPC push (:8403)
  control <action>          raw /api/control passthrough
  persona <key>             alias for model <key>
  router <key>              router model select
  subsystems                server-side fleet probe (:8400/api/subsystems)
  diag | test               system test (chat ping via :8400)
  coherence                 random-question coherence check
  context                   healer budget debugger
  open <panel|dashboard|kiosk|multigate|xr>  open a web surface
  help                      this text

No arguments → interactive menu.
"""


def cli(args: list) -> int:
    cmd, rest = args[0].lower(), args[1:]
    arg = " ".join(rest)

    if cmd == "status":
        print_status()
    elif cmd == "runtime":
        if rest and rest[0] == "wait":
            wait_runtime_loaded(int(rest[1]) if len(rest) > 1 else 360)
        else:
            runtime_status()
    elif cmd in ("model", "persona"):
        if not rest or rest[0] == "list":
            for k, m in PERSONA_MODELS.items():
                print(f"  {k:<12} {m['name']} [{m['size_gb']}GB] → {m['xrlf_path']}")
        else:
            q = rest[0]
            key = (
                q
                if q in PERSONA_MODELS
                else next((k for k, m in PERSONA_MODELS.items() if q in m["id"]), None)
            )
            if not key:
                print(f"  unknown model '{q}' — try 'model list'")
                return 1
            persona_apply(key)
    elif cmd == "router":
        if not rest or rest[0] == "list":
            for k, m in ROUTER_MODELS.items():
                print(f"  {k:<12} {m['name']} → {m['xrlf_path']}")
        elif rest[0] in ROUTER_MODELS:
            m = ROUTER_MODELS[rest[0]]
            proxy_set("FOVEAI_OMNI_ROUTER_MODEL", m["id"])
            proxy_set("XRLF_ROUTER_MODEL", m["id"])
        else:
            print(f"  unknown router '{rest[0]}'")
            return 1
    elif cmd == "load":
        if not arg:
            print("  usage: load <path.xrlf>")
            return 1
        st, txt = http_post(f"{XRLF_API}/load", {"model": arg}, timeout=600)
        print(f"  /load → [{st}] {txt[:200]}")
    elif cmd == "unload":
        st, txt = http_post(f"{XRLF_API}/unload", {}, timeout=60)
        print(f"  /unload → [{st}] {txt[:200]}")
    elif cmd == "restart":
        if arg == "runtime":
            print(http_post(f"{PROXY_API}/api/control", {"action": "restart-local"})[1])
        elif arg == "proxy":
            print(http_post(f"{PROXY_API}/api/control", {"action": "restart-proxy"})[1])
        else:
            print("  usage: restart runtime|proxy")
            return 1
    elif cmd == "stack":
        if arg in ("start", "stop", "restart", "light"):
            stack(arg)
        else:
            print("  usage: stack start|stop|restart|light")
            return 1
    elif cmd in ("start", "stop", "--light", "light"):
        stack(cmd.lstrip("-"))
    elif cmd == "mode":
        if arg not in ("local", "cloud"):
            print("  usage: mode local|cloud")
            return 1
        proxy_set("XRLF_COGNITIVE_MODE", arg)
    elif cmd == "engine":
        if arg not in ENGINE_PRESETS:
            print("  usage: engine xrlf|lmstudio|cloud")
            return 1
        engine_apply(arg)
    elif cmd == "frontend":
        if arg not in ("multigate", "xr_vessel", "3d_avatar"):
            print("  usage: frontend multigate|xr_vessel|3d_avatar")
            return 1
        proxy_set("XRLF_FRONTEND_UI_PRESET", arg)
    elif cmd == "set":
        if "=" not in arg:
            print("  usage: set KEY=VALUE")
            return 1
        k, v = arg.split("=", 1)
        proxy_set(k.strip(), v.strip())
        maybe_restart_for_key(k.strip())
    elif cmd == "get":
        v = read_env().get(arg)
        masked = any(t in arg.upper() for t in ("KEY", "TOKEN", "SECRET", "PASS"))
        print(f"  {arg}={'(unset)' if v is None else ('***' if masked else v)}")
    elif cmd == "env":
        f = arg.lower()
        for k, v in sorted(read_env().items()):
            if f and f not in k.lower():
                continue
            disp = (
                "***"
                if any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASS"))
                else v
            )
            print(f"  {k}={disp}")
    elif cmd == "toggle":
        parts = rest
        if len(parts) != 2 or parts[1].lower() not in ("on", "off", "true", "false"):
            print("  usage: toggle voice|mic on|off")
            return 1
        name = {"voice": "XRLF_VOICE_ENABLED", "mic": "XRLF_MIC_ENABLED"}.get(
            parts[0], parts[0]
        )
        proxy_set(name, "true" if parts[1].lower() in ("on", "true") else "false")
    elif cmd == "tts":
        if arg not in ("kokoro", "websocket", "edgetts"):
            print("  usage: tts kokoro|websocket|edgetts")
            return 1
        set_tts(arg)
    elif cmd == "stt":
        if arg not in ("whisper", "browser"):
            print("  usage: stt whisper|browser")
            return 1
        set_stt(arg)
    elif cmd == "fovea":
        if not arg:
            print("  usage: fovea 0-6")
            return 1
        st, txt = http_post(f"{PROXY_API}/api/fovea", {"level": int(arg)}, timeout=4)
        set_env_key("XRLF_PROXY_AGGRESSION", arg)
        print(f"  Foveation → {FOVEA_LEVELS.get(int(arg), arg)}  (live push [{st}])")
    elif cmd == "cap":
        st, txt = http_post(f"{PROXY_API}/api/cap", {"cap": int(arg or 0)}, timeout=4)
        print(f"  cap → [{st}] {txt[:120]}")
    elif cmd == "preserve":
        st, txt = http_post(
            f"{PROXY_API}/api/preserve", {"preserve": int(arg or 4)}, timeout=4
        )
        print(f"  preserve → [{st}] {txt[:120]}")
    elif cmd == "ws":
        parts = arg.split(None, 1)
        if len(parts) != 2:
            print("  usage: ws <setting> <value>")
            return 1
        send_ws_setting(parts[0], parts[1])
    elif cmd == "control":
        if not arg:
            print("  usage: control <action>")
            return 1
        st, txt = http_post(f"{PROXY_API}/api/control", {"action": arg}, timeout=10)
        print(f"  {arg} → [{st}] {txt[:200]}")
    elif cmd == "subsystems":
        diag_subsystems()
    elif cmd in ("diag", "test"):
        diag_system_test()
    elif cmd == "coherence":
        diag_coherence()
    elif cmd == "context":
        diag_context()
    elif cmd == "open":
        urls = {
            "panel": SETTINGS_URL,
            "dashboard": DASHBOARD_URL,
            "kiosk": KIOSK_URL,
            "multigate": "http://127.0.0.1:5177",
            "xr": "http://127.0.0.1:5176",
        }
        open_url(urls.get(arg, arg))
    elif cmd in ("help", "-h", "--help"):
        print(USAGE)
    else:
        print(USAGE)
        return 1
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        try:
            main_menu()
        except (KeyboardInterrupt, EOFError):
            print("\nbye")
    else:
        sys.exit(cli(args))
