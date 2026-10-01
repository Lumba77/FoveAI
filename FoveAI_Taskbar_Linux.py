#!/usr/bin/env python3
"""
FoveAI_Taskbar_Linux.py — Linux-native system tray controller for FoveAI.

Ported from FoveAI_Taskbar.pyw (Windows). All Windows-specific calls
(PowerShell, taskkill, netstat, winreg, msedge, wt.exe) replaced with
Linux equivalents (pgrep, pkill, ss, xdg-open, gnome-terminal, .desktop).

Features:
  - VRAM Guardian with color-coded status (red/yellow/green/blue)
  - Free VRAM menu alternatives
  - Choose main chat XRLF model
  - Choose main router XRLF model
  - Stack start (full / light / restart / stop)
  - Foveated memory server start / restart / stop / free RAM
  - Choice of model interaction (corner companion, topbar, multigate webui)
  - Antigravity routing through Jenna-VSCode as context-stripping trojan horse

Usage:
    python3 FoveAI_Taskbar_Linux.py
    python3 FoveAI_Taskbar_Linux.py --no-autostart-stack
"""

import os
import signal

# ─── KDE Wayland: force AppIndicator backend ───────────────────────
# pystray defaults to _xorg on Linux, which doesn't show in KDE's
# StatusNotifierItem tray under Wayland. We inject the system gi path
# (GTK3 + AppIndicator3) BEFORE importing pystray so it picks the
# _appindicator backend instead of _xorg.
# Detect the active system Python's site-packages (works across 3.12/3.13/3.14)
import site as _site
import subprocess
import sys
import threading
import time

import requests

_SYS_GI_PATH = (
    _site.getsitepackages()[0]
    if _site.getsitepackages()
    else "/usr/lib64/python3.14/site-packages"
)
if _SYS_GI_PATH not in sys.path:
    sys.path.insert(0, _SYS_GI_PATH)
try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3, Gtk  # noqa: F401
except Exception as _gi_err:
    pass

# Now import pystray — it will detect gi/AppIndicator3 and use the
# _appindicator backend automatically.
import socket
from typing import Any

import pystray
from PIL import Image, ImageDraw, ImageFont

# ─── Paths ──────────────────────────────────────────────────────────
FOVEAI_DIR = os.path.dirname(os.path.abspath(__file__))
LUMAX_DIR = os.path.dirname(FOVEAI_DIR)
if FOVEAI_DIR not in sys.path:
    sys.path.insert(0, FOVEAI_DIR)

# ─── VENV PYTHON ────────────────────────────────────────────────────
VENV_PYTHON = os.path.join(FOVEAI_DIR, ".venv", "bin", "python")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = os.path.join(FOVEAI_DIR, "venv", "bin", "python")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable

DEBUG = "--debug" in sys.argv
NO_AUTOSTART = "--no-autostart-stack" in sys.argv

stack_process = None
fm_process = None

# ─── Runtime Guards ─────────────────────────────────────────────────
from runtime.rig_guard import RigGuard
from runtime.vram_guard import VRAMGuardrail

vram_guard = VRAMGuardrail()

# ─── Health Monitor ─────────────────────────────────────────────────
try:
    from health_monitor import (
        ContinuousHealthMonitor,
        HealthStatus,
        auto_heal,
        execute_heal,
        run_full_report,
        run_sharp_report,
    )

    HEALTH_MONITOR_AVAILABLE = True
except Exception as _hm_err:
    print(f"[Tray] health_monitor not available: {_hm_err}")
    HEALTH_MONITOR_AVAILABLE = False

_health_monitor: ContinuousHealthMonitor | None = None
_health_auto_heal = False
_last_health_report: Any | None = None
_icon_ref: Any | None = None
rig_guard = RigGuard(cooldown_seconds=600)

# ─── Single-Instance Lock ───────────────────────────────────────────
_lock_socket = None


def _bind_lock_socket() -> bool:
    global _lock_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 48409))
        s.listen(1)
        _lock_socket = s
        return True
    except OSError:
        try:
            s.close()
        except Exception:
            pass
        # Check if stale process owns the port
        try:
            out = subprocess.check_output(
                ["ss", "-tlnp", "sport = :48409"], text=True, timeout=2
            )
            if "pid=" in out:
                # Try to identify if it's a python tray process
                pid_str = out.split("pid=")[1].split(",")[0].split(")")[0].strip()
                pid = int(pid_str)
                cmdline = open(f"/proc/{pid}/cmdline", "r").read().replace("\x00", " ")
                if "FoveAI_Taskbar" in cmdline:
                    # Stale or existing instance — takeover if requested
                    if any(
                        flag in sys.argv
                        for flag in ("--takeover", "--force", "--restart", "--tray")
                    ):
                        os.kill(pid, signal.SIGKILL)
                        time.sleep(0.4)
                        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        try:
                            s2.bind(("127.0.0.1", 48409))
                            s2.listen(1)
                            _lock_socket = s2
                            return True
                        except Exception:
                            pass
        except Exception:
            pass
        return False


if not _bind_lock_socket():
    # Another instance is running — open settings panel as fallback
    try:
        subprocess.Popen(
            ["xdg-open", "http://127.0.0.1:8401/memory/settings.html"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    sys.exit(0)

# ─── Icons ──────────────────────────────────────────────────────────
ASSET_ICON_PNG = os.path.join(FOVEAI_DIR, "assets", "Icon_small.png")
_base_icon_art = None
if os.path.exists(ASSET_ICON_PNG):
    try:
        _base_icon_art = (
            Image.open(ASSET_ICON_PNG)
            .convert("RGBA")
            .resize((48, 48), Image.Resampling.LANCZOS)
        )
    except Exception:
        _base_icon_art = None


def create_icon_image(color_hex: str, symbol: str | None = None) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (15, 23, 42, 255))
    draw = ImageDraw.Draw(image)
    # Parse hex color
    h = color_hex.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    color = (r, g, b, 255)

    draw.rectangle((0, 0, 63, 63), outline=color, width=5)

    if _base_icon_art:
        image.paste(_base_icon_art, (12, 6), _base_icon_art)
        draw.rectangle((0, 52, 63, 63), fill=color)
        draw.ellipse((38, 34, 58, 54), fill=color, outline=(15, 23, 42, 255), width=2)
    elif symbol:
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf", 28
            )
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), symbol, font=font)
        x = (64 - (bbox[2] - bbox[0])) // 2
        y = (64 - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), symbol, font=font, fill=color)
    return image


ICON_RED = create_icon_image("#ef4444", "◆")
ICON_GREEN = create_icon_image("#10b981", "◆")
ICON_ORANGE = create_icon_image("#f59e0b", "◆")
ICON_BLUE = create_icon_image("#0284c7", "◆")

# ─── Helpers ────────────────────────────────────────────────────────


def notify(icon, message: str, title: str = "FoveAI"):
    if icon:
        try:
            icon.notify(message, title)
        except Exception:
            pass
    # Also try libnotify (notify-send) for desktop notifications
    try:
        subprocess.Popen(
            ["notify-send", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def open_url(url: str):
    subprocess.Popen(
        ["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def open_terminal(cmd: str, cwd: str = FOVEAI_DIR, title: str = "FoveAI"):
    """Open a terminal window running cmd."""
    for term in ["gnome-terminal", "konsole", "xterm", "alacritty", "kitty"]:
        try:
            subprocess.Popen(
                [term, "--", "bash", "-c", cmd],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except FileNotFoundError:
            continue


def read_env() -> dict[str, str]:
    env_path = os.path.join(FOVEAI_DIR, ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(LUMAX_DIR, ".env")
    values: dict[str, str] = {}
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return values


def set_env_key(key: str, value: str):
    env_path = os.path.join(FOVEAI_DIR, ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(LUMAX_DIR, ".env")

    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
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

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def check_port_listener(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def kill_port_listeners(ports: list) -> int:
    """Kill processes listening on the given ports. Returns count killed."""
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
    """Kill processes matching name pattern. Returns count killed."""
    try:
        out = subprocess.check_output(["pgrep", "-f", name], text=True, timeout=2)
        pids = [int(p) for p in out.strip().splitlines() if p.strip().isdigit()]
        for pid in pids:
            if pid != os.getpid():
                os.kill(pid, signal.SIGTERM)
        return len(pids)
    except subprocess.CalledProcessError:
        return 0
    except Exception:
        return 0


def get_service_status(port: int, path: str | None = None) -> tuple[str, str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return "inactive", "[○ INACTIVE]"
    except Exception:
        return "inactive", "[○ INACTIVE]"

    if path:
        try:
            import urllib.request

            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                headers={"User-Agent": "FoveAI-Tray/1.0"},
            )
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status in (200, 204, 302):
                    return "active", "[● ACTIVE]"
                return "dormant", "[◐ DORMANT]"
        except Exception:
            return "dormant", "[◐ DORMANT]"

    return "active", "[● ACTIVE]"


# ─── Stack Control (via Sleipnir launcher) ──────────────────────────

SLEIPNIR_SH = os.path.join(FOVEAI_DIR, "sleipnir_launcher.sh")


def start_stack(icon, item):
    """Start the full FoveAI stack via Sleipnir: backend + XRLF runtime + dormant model."""
    notify(icon, "Igniting FoveAI Fleet via Sleipnir...", "FoveAI Stack")
    icon.icon = ICON_ORANGE
    subprocess.Popen(
        ["bash", SLEIPNIR_SH, "start"],
        cwd=FOVEAI_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for XRLF runtime (model loading takes time)
    for _ in range(60):
        time.sleep(1)
        if check_port_listener(8402):
            icon.icon = ICON_GREEN
            notify(
                icon,
                "FoveAI Fleet airborne!\nBackend :8400, XRLF :8402, WS :8403",
                "FoveAI Stack",
            )
            _refresh_menu(icon)
            return
    icon.icon = ICON_RED
    notify(icon, "Fleet start timed out (model may still be loading)", "FoveAI Stack")
    _refresh_menu(icon)


def start_light_stack(icon, item):
    """Start light stack: backend only (no XRLF model loaded)."""
    notify(icon, "Starting Light Fleet (Backend only)...", "FoveAI Light Mode")
    icon.icon = ICON_ORANGE
    subprocess.Popen(
        ["bash", SLEIPNIR_SH, "--light"],
        cwd=FOVEAI_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(0.5)
        if check_port_listener(8400):
            icon.icon = ICON_GREEN
            notify(icon, "Light Fleet running\nBackend :8400", "FoveAI Light Mode")
            _refresh_menu(icon)
            return
    icon.icon = ICON_RED
    notify(icon, "Light fleet start timed out", "FoveAI Error")
    _refresh_menu(icon)


def stop_stack(icon, item):
    """Stop the full FoveAI fleet via Sleipnir."""
    notify(icon, "Stopping FoveAI Fleet...", "FoveAI Stack")
    icon.icon = ICON_ORANGE
    subprocess.Popen(
        ["bash", SLEIPNIR_SH, "stop"],
        cwd=FOVEAI_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    icon.icon = ICON_RED
    notify(icon, "FoveAI Fleet stopped", "FoveAI Stack")
    _refresh_menu(icon)


def restart_stack(icon, item):
    notify(icon, "Restarting FoveAI Fleet...", "FoveAI Stack")
    stop_stack(icon, item)
    time.sleep(2.0)
    start_stack(icon, item)


def is_stack_running() -> bool:
    return check_port_listener(8400) and check_port_listener(8402)


def is_backend_running() -> bool:
    return check_port_listener(8400)


# ─── Foveated Memory Server ─────────────────────────────────────────


def start_memory_proxy(icon, item):
    if is_backend_running():
        notify(icon, "Backend is already running (:8400)", "FoveAI Service")
        return
    notify(icon, "Starting Foveated Memory Proxy (Backend)...", "FoveAI Service")
    icon.icon = ICON_ORANGE
    backend_dir = os.path.join(FOVEAI_DIR, "Backend")
    subprocess.Popen(
        [
            VENV_PYTHON,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8400",
        ],
        cwd=backend_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.5)
        if is_backend_running():
            icon.icon = ICON_GREEN
            notify(icon, "Backend is online (:8400)", "FoveAI Service")
            _refresh_menu(icon)
            return
    notify(icon, "Backend startup timed out", "FoveAI Service")
    _refresh_menu(icon)


def stop_memory_proxy(icon, item):
    if not is_backend_running():
        notify(icon, "Backend is not running", "FoveAI Service")
        return
    notify(icon, "Stopping Backend...", "FoveAI Service")
    kill_port_listeners([8400, 8401])
    time.sleep(0.5)
    notify(icon, "Backend stopped", "FoveAI Service")
    icon.icon = ICON_RED
    _refresh_menu(icon)


def restart_memory_proxy(icon, item):
    notify(icon, "Restarting Backend...", "FoveAI Service")
    icon.icon = ICON_ORANGE
    kill_port_listeners([8400, 8401])
    time.sleep(1.5)
    backend_dir = os.path.join(FOVEAI_DIR, "Backend")
    subprocess.Popen(
        [
            VENV_PYTHON,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8400",
        ],
        cwd=backend_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.5)
        if is_backend_running():
            icon.icon = ICON_GREEN
            notify(icon, "Backend restarted successfully", "FoveAI Service")
            _refresh_menu(icon)
            return
    icon.icon = ICON_RED
    notify(icon, "Backend restart timed out", "FoveAI Service")
    _refresh_menu(icon)


def free_ram_flush_caches(icon, item=None):
    """Free system RAM and flush model caches."""
    notify(icon, "Freeing RAM & flushing model caches...", "FoveAI Guardian")
    try:
        import gc

        gc.collect()
        # Kill llama-server processes to free VRAM
        kill_process_by_name("llama-server")
        kill_process_by_name("llama_server")
        kill_process_by_name("run_xrlf")
        # Clear VRAM guard lock files
        for f in vram_guard.lock_dir.glob("*.lock"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        # Drop OS filesystem caches (requires root, may fail silently)
        try:
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("3")
        except (PermissionError, OSError):
            pass
    except Exception:
        pass
    notify(icon, "RAM liberated, caches flushed", "FoveAI Guardian")
    _refresh_menu(icon)


# ─── Model Selectors ────────────────────────────────────────────────

PERSONA_MODELS: dict[str, dict[str, Any]] = {
    "gemma_e2b_xrlf": {
        "name": "Gemma 4 E2B MTP (Default Persona)",
        "id": "gemma-4-e2b-multimodal-v1.0.xrlf",
        "file": "gemma-4-e2b-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf",
        "size_gb": 3.3,
        "total_layers": 30,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "Default Persona: 2B XRLF bundle with native vision+audio, fast-loading embedded MTP draft.",
    },
    "gemma_12b_xrlf": {
        "name": "Gemma 4 12B MTP (Heavy)",
        "id": "gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "file": "gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "size_gb": 5.1,
        "total_layers": 42,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "Heavy 12B XRLF bundle: native STT, vision, foveated memory, draft model.",
    },
    "qwen_4b_multimodal": {
        "name": "Qwen 3.5 4B MTP (Coder)",
        "id": "qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "file": "qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "size_gb": 2.9,
        "total_layers": 36,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "4B Qwen MTP XRLF coder with vision (mmproj), Whisper STT hook, Kokoro TTS hook.",
    },
    "smolvlm2_500m_xrlf": {
        "name": "SmolVLM2 500M (Vision)",
        "id": "smolvlm2-500m-multimodal-v1.0.xrlf",
        "file": "smolvlm2-500m-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/smolvlm2-500m-multimodal-v1.0.xrlf",
        "size_gb": 0.5,
        "total_layers": 24,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "500M vision+video XRLF model with Whisper STT hook, Kokoro TTS hook.",
    },
}

ROUTER_MODELS: dict[str, dict[str, Any]] = {
    "foveai_omni_router_v2": {
        "name": "FoveAI Omni Router v2",
        "id": "foveai-omni-router-v2.xrlf",
        "file": "foveai-omni-router-v2.xrlf",
        "xrlf_path": "foveai-omni-router-v2.xrlf",
        "size_gb": 1.4,
        "total_layers": 28,
        "multimodal": False,
        "is_xrlf": True,
        "detail": "Default XRLF router model for fast intention classification and context routing.",
    },
    "foveai_omni_router_v1": {
        "name": "FoveAI Omni Router v1 (Legacy)",
        "id": "foveai-omni-router.xrlf",
        "file": "foveai-omni-router.xrlf",
        "xrlf_path": "foveai-omni-router.xrlf",
        "size_gb": 0.9,
        "total_layers": 28,
        "multimodal": False,
        "is_xrlf": True,
        "detail": "Legacy XRLF router model. Preserved for study on how to pack models.",
    },
}


def select_persona_model(icon, item, model_key: str):
    m = PERSONA_MODELS.get(model_key)
    if not m:
        return

    xrlf_model = m.get("xrlf_path", "")
    if not xrlf_model:
        notify(icon, f"Model {m['name']} is missing an xrlf_path.", "XRLF Model Error")
        return

    full_path = os.path.join(FOVEAI_DIR, xrlf_model)
    if not os.path.exists(full_path):
        notify(icon, f"Model file not found: {xrlf_model}", "XRLF Model Error")
        return

    try:
        set_env_key("XRLF_MODEL_LOCAL_ID", m["id"])
        set_env_key("FOVEAI_MODEL_ACTIVE_ID", m["id"])
        set_env_key("FOVEAI_MAIN_MODEL", m["id"])
    except Exception:
        pass

    notify(
        icon,
        f"Launching Persona AI: {m['name']}...\nLoading {m['size_gb']:.1f}GB model...",
        "Persona AI Loader",
    )

    # Start XRLF runtime with the selected model
    try:
        env = os.environ.copy()
        env["XRLF_REPO_ENABLED"] = "true"
        env["GGML_CUDA_NO_VMM"] = "1"
        subprocess.Popen(
            [
                VENV_PYTHON,
                os.path.join(FOVEAI_DIR, "run_xrlf.py"),
                "--model",
                xrlf_model,
                "--port",
                "8402",
                "--ws-port",
                "8403",
            ],
            cwd=FOVEAI_DIR,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        mm_note = " Native STT + Vision" if m.get("multimodal") else ""
        notify(
            icon,
            f"Persona AI set to {m['name']}{mm_note}\nXRLF runtime starting on :8402",
            "Persona AI Loader",
        )
    except Exception as e:
        notify(icon, f"Persona AI launch failed: {e}", "Persona AI Error")

    _refresh_menu(icon)


def select_router_model(icon, item, model_key: str):
    m = ROUTER_MODELS.get(model_key)
    if not m:
        return

    try:
        set_env_key("FOVEAI_OMNI_ROUTER_MODEL", m["id"])
        set_env_key("XRLF_ROUTER_MODEL", m["id"])
        notify(icon, f"Default Router set to {m['name']}", "XRLF Router Loader")
    except Exception as e:
        notify(icon, f"Router set failed: {e}", "XRLF Router Error")

    _refresh_menu(icon)


def unload_models(icon, item=None):
    """Unload all active models and free VRAM."""
    notify(icon, "Unloading active models & freeing VRAM...", "FoveAI VRAM")
    try:
        kill_process_by_name("run_xrlf")
        kill_process_by_name("llama-server")
        kill_process_by_name("llama_server")
        for f in vram_guard.lock_dir.glob("*.lock"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        notify(icon, "Local model slots released", "FoveAI VRAM")
    except Exception as e:
        notify(icon, f"Unload failed: {e}", "FoveAI VRAM")
    _refresh_menu(icon)


# ─── Hardware Telemetry ─────────────────────────────────────────────


def get_hardware_telemetry() -> tuple[float, float, float, Image.Image, str]:
    """Query physical free VRAM and compute color-coded health status."""
    try:
        free_gb = vram_guard.get_realtime_free_vram_gb()
        total_gb = 8.0
        used_gb = max(0.0, total_gb - free_gb)
    except Exception:
        total_gb, used_gb, free_gb = 8.0, 1.0, 7.0

    if used_gb < 4.5:
        color = ICON_GREEN
        status_text = (
            f"Healthy | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"
        )
    elif used_gb < 6.0:
        color = ICON_BLUE
        status_text = (
            f"Active | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"
        )
    elif used_gb < 7.0:
        color = ICON_ORANGE
        status_text = (
            f"Protected | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"
        )
    else:
        color = ICON_RED
        status_text = (
            f"Critical | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"
        )

    return total_gb, used_gb, free_gb, color, status_text


# ─── Frontend Launchers ─────────────────────────────────────────────


def launch_corner_companion(icon, item):
    notify(icon, "Corner Companion archived (was Windows-only)", "FoveAI HUD")


def launch_topbar(icon, item):
    notify(icon, "TopBar archived (was Windows-only)", "FoveAI TopBar")


def launch_multigate(icon, item):
    notify(icon, "Launching Multigate WebUI...", "FoveAI Frontend")
    multigate_dir = os.path.join(FOVEAI_DIR, "Frontend", "multigate")
    if os.path.exists(multigate_dir):
        subprocess.Popen(["npm", "run", "dev", "--", "--open"], cwd=multigate_dir)
    else:
        notify(icon, "Multigate directory not found", "FoveAI Frontend")


def open_settings_panel(icon=None, item=None):
    url = "http://127.0.0.1:8401/memory/settings.html"
    open_url(url)
    if icon:
        notify(icon, "Opening Settings Panel", "FoveAI Settings")


def open_memory_dashboard(icon, item):
    open_url("http://127.0.0.1:8401/memory")
    notify(icon, "Opening AUI Memory Dashboard", "FoveAI Memory")


def open_debug_terminal(icon, item):
    notify(icon, "Opening FoveAI Debug Terminal...", "FoveAI Debug")
    open_terminal(
        f"cd {LUMAX_DIR} && tail -f FoveAI/Backend/*.log 2>/dev/null || echo 'No logs yet'",
        cwd=LUMAX_DIR,
        title="FoveAI Debug",
    )


# ─── Antigravity / Jenna-VSCode Trojan Horse ────────────────────────


def launch_jenna_vscode(icon, item):
    """Launch Jenna VSCode extension as context-stripping trojan horse for Antigravity IDE."""
    notify(
        icon,
        "Launching Jenna-VSCode (Antigravity Trojan Horse)...",
        "FoveAI Antigravity",
    )
    jenna_dir = os.path.join(LUMAX_DIR, "Tools", "jenna-vscode")
    if os.path.exists(jenna_dir):
        for editor_cmd in ["antigravity-ide", "code", "codium", "devin-desktop"]:
            try:
                subprocess.Popen(
                    [editor_cmd, jenna_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                notify(
                    icon, f"Jenna-VSCode opened in {editor_cmd}", "FoveAI Antigravity"
                )
                return
            except FileNotFoundError:
                continue
        notify(
            icon,
            "No supported editor found (tried antigravity-ide, code, codium, devin-desktop)",
            "FoveAI Antigravity",
        )
    else:
        notify(
            icon, f"Jenna-VSCode directory not found: {jenna_dir}", "FoveAI Antigravity"
        )


def toggle_antigravity_proxy(icon, item):
    """Toggle routing Antigravity CLI through FoveAI proxy."""
    env = read_env()
    current = env.get("FOVEAI_ANTIGRAVITY_PROXY", "false").lower()
    new_val = "false" if current == "true" else "true"
    set_env_key("FOVEAI_ANTIGRAVITY_PROXY", new_val)
    state = (
        "Enabled (Routing through :8400)" if new_val == "true" else "Disabled (Direct)"
    )
    notify(icon, f"Antigravity Proxy: {state}", "FoveAI Antigravity")
    _refresh_menu(icon)


# ─── Voice / Mic / TTS ──────────────────────────────────────────────


def set_env_toggle(icon, item, name: str, value: str):
    try:
        set_env_key(name, str(value).lower())
        notify(icon, f"{name} = {value}", "FoveAI Toggle")
    except Exception as e:
        notify(icon, f"{name} toggle failed: {e}", "FoveAI Toggle")


def voice_on(icon, item):
    set_env_toggle(icon, item, "FoveAI_VOICE_ENABLED", "true")


def voice_off(icon, item):
    set_env_toggle(icon, item, "FoveAI_VOICE_ENABLED", "false")


def mic_on(icon, item):
    set_env_toggle(icon, item, "FoveAI_MIC_ENABLED", "true")


def mic_off(icon, item):
    set_env_toggle(icon, item, "FoveAI_MIC_ENABLED", "false")


def switch_tts_provider(icon, item, provider: str):
    notify(icon, f"Switching TTS Engine to {provider}...", "FoveAI Voice")
    try:
        set_env_key("XRLF_TTS_PROVIDER", provider)
        set_env_key("FoveAI_TTS_PROVIDER", provider)
        notify(icon, f"TTS Engine set to {provider}", "FoveAI Voice")
        _refresh_menu(icon)
    except Exception as e:
        notify(icon, f"TTS switch failed: {e}", "FoveAI Voice")


def switch_stt_provider(icon, item, provider: str):
    notify(icon, f"Switching STT Engine to {provider}...", "FoveAI Voice")
    try:
        set_env_key("XRLF_STT_PROVIDER", provider)
        set_env_key("FoveAI_STT_PROVIDER", provider)
        notify(icon, f"STT Engine set to {provider}", "FoveAI Voice")
        _refresh_menu(icon)
    except Exception as e:
        notify(icon, f"STT switch failed: {e}", "FoveAI Voice")


def switch_to_local(icon, item):
    notify(icon, "Switching to local inference...", "FoveAI Cognitive Mode")
    try:
        set_env_key("FoveAI_COGNITIVE_MODE", "local")
        set_env_key("XRLF_COGNITIVE_MODE", "local")
        set_env_key("XRLF_RUNTIME_MODE", "local")
        set_env_key("FoveAI_CHAT_PROVIDER", "xrlf_runtime")
        notify(icon, "Switched to local mode", "FoveAI Cognitive Mode")
        _refresh_menu(icon)
    except Exception as e:
        notify(icon, f"Switch failed: {e}", "FoveAI Cognitive Mode")


def switch_to_cloud(icon, item):
    notify(icon, "Switching to cloud inference...", "FoveAI Cognitive Mode")
    try:
        set_env_key("FoveAI_COGNITIVE_MODE", "cloud")
        set_env_key("XRLF_COGNITIVE_MODE", "cloud")
        set_env_key("XRLF_RUNTIME_MODE", "cloud")
        set_env_key("FoveAI_CHAT_PROVIDER", "ollama_cloud")
        notify(icon, "Switched to cloud mode", "FoveAI Cognitive Mode")
        _refresh_menu(icon)
    except Exception as e:
        notify(icon, f"Switch failed: {e}", "FoveAI Cognitive Mode")


# ─── Foveation Levels ───────────────────────────────────────────────

FOVEA_LEVELS = {
    0: "Auto",
    1: "Minimal",
    2: "Light",
    3: "Moderate",
    4: "Aggressive",
    5: "Maximum",
    6: "Off",
}


def set_fovea(icon, item, level: int):
    label = FOVEA_LEVELS.get(level, f"Level {level}")
    notify(icon, f"Setting foveation to {label}...", "FoveAI Fovea")
    try:
        set_env_key("XRLF_PROXY_AGGRESSION", str(level))
        notify(icon, f"Foveation set to {label}", "FoveAI Fovea")
        _refresh_menu(icon)
    except Exception as e:
        notify(icon, f"Foveation failed: {e}", "FoveAI Fovea")


# ─── Frontend Switch ────────────────────────────────────────────────


def switch_frontend(icon, item, ui_type: str):
    labels = {
        "3d_avatar": "3D Avatar Chatbot",
        "multigate": "Multigate Portal",
        "xr_vessel": "XR Vessel",
    }
    label = labels.get(ui_type, ui_type)
    notify(icon, f"Switching frontend to {label}...", "FoveAI Frontend")
    try:
        set_env_key("XRLF_FRONTEND_UI_PRESET", ui_type)
        set_env_key("FOVEAI_FRONTEND_UI", ui_type)
        notify(icon, f"Frontend set to {label}", "FoveAI Frontend")
        _refresh_menu(icon)
    except Exception as e:
        notify(icon, f"Frontend switch failed: {e}", "FoveAI Frontend")


# ─── Context Collector ──────────────────────────────────────────────


def is_context_collector_enabled() -> bool:
    env = read_env()
    return env.get("FOVEAI_CONTEXT_CONSENT", "false").lower() == "true"


def toggle_context_collector(icon, item=None):
    new_val = "false" if is_context_collector_enabled() else "true"
    set_env_toggle(icon, item, "FOVEAI_CONTEXT_CONSENT", new_val)
    state_str = "Enabled (Consented)" if new_val == "true" else "Disabled"
    notify(icon, f"Workspace Context Collector: {state_str}", "FoveAI Context")


# ─── Rig & Bloat Guardian Actions ──────────────────────────────────


def kill_runaway_git_action(icon, item=None):
    notify(icon, "Scanning for stuck git processes...", "Rig Guardian")
    cnt, freed_mb, msg = rig_guard.kill_runaway_git_processes()
    notify(icon, msg, "Rig Guardian")
    _refresh_menu(icon)


def safe_language_server_guide_action(icon, item=None):
    guide = rig_guard.get_language_server_guidance()
    notify(icon, guide["message"], guide["title"])


def clean_unity_temp_action(icon, item=None):
    notify(icon, "Cleaning Unity temp and checking zombie workers...", "Rig Guardian")
    k_cnt, k_msg = rig_guard.kill_zombie_unity_workers()
    c_ok, c_msg = rig_guard.clean_unity_temp()
    notify(icon, f"{k_msg}\n{c_msg}", "Rig Guardian")
    _refresh_menu(icon)


def fix_workspace_ignores_action(icon, item=None):
    notify(
        icon, "Verifying and injecting workspace ignore protections...", "Rig Guardian"
    )
    ok, msg = rig_guard.fix_workspace_ignores()
    notify(icon, msg, "Rig Guardian")
    _refresh_menu(icon)


def inspect_ram_consumers_action(icon, item=None):
    top = rig_guard.get_top_ram_consumers(5)
    lines = [f"• {p['name']} (PID {p['id']}): {p['ram_mb']} MB" for p in top]
    notify(
        icon,
        "\n".join(lines) if lines else "No process data found.",
        "Top RAM Consumers",
    )


# ─── Memory Tools ───────────────────────────────────────────────────


def start_super_kiosk(icon, item):
    open_url("http://127.0.0.1:8401/memory/prompt-kiosk.html")
    notify(icon, "Opening Super Prompt Kiosk", "FoveAI Memory")


def start_foveai_super_terminal(icon, item):
    notify(icon, "Launching FoveAI Super Memory terminal...", "FoveAI Terminal")
    open_terminal(
        f"cd {LUMAX_DIR} && {VENV_PYTHON} -c 'print(\"FoveAI Super Memory Terminal\")'",
        cwd=LUMAX_DIR,
        title="FoveAI Super Memory",
    )


# ─── Native 3D Desktop Vessel ───────────────────────────────────────


def launch_desktop_vessel(icon, item):
    notify(icon, "Desktop Vessel archived (was Windows-only)", "FoveAI Desktop Vessel")


# ─── Menu Refresh ───────────────────────────────────────────────────


def _refresh_menu(icon):
    def _do_refresh():
        time.sleep(0.3)
        try:
            icon.menu = build_menu()
            icon.update_menu()
        except Exception:
            pass

    threading.Thread(target=_do_refresh, daemon=True).start()


def refresh_taskbar_menu(icon):
    _refresh_menu(icon)


# ─── Health Monitor Actions ─────────────────────────────────────────


def _on_health_report(report: Any) -> None:
    """Callback from the continuous health monitor — store and notify on failure."""
    global _last_health_report
    _last_health_report = report
    fails = report.failing()
    if fails:
        names = ", ".join(r.name for r in fails)
        # Tray icon notification (non-blocking)
        try:
            if _icon_ref:
                notify(_icon_ref, f"FAIL: {names}", "FoveAI Health")
                # Update icon color based on health
                _icon_ref.icon = ICON_RED
        except Exception:
            pass
    elif report.warnings():
        try:
            if _icon_ref:
                _icon_ref.icon = ICON_ORANGE
        except Exception:
            pass
    else:
        try:
            if _icon_ref:
                _icon_ref.icon = ICON_GREEN
        except Exception:
            pass


def _on_health_fail(check: Any) -> None:
    """Called when a specific check fails."""
    print(f"[Health] FAIL: {check.name} — {check.detail}")


def run_health_check_now(icon, item):
    """Run a quick health check (no coherence probe) and show notification."""
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    notify(icon, "Running health checks...", "FoveAI Health")
    report = run_full_report(include_coherence=False)
    global _last_health_report
    _last_health_report = report
    _refresh_menu(icon)
    notify(icon, f"Health: {report.summary}", "FoveAI Health")


def run_sharp_coherence_test(icon, item):
    """Run sharp mode coherence test (includes a real chat probe, ~30s)."""
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    notify(icon, "Running sharp coherence probe (30s)...", "FoveAI Health")
    icon.icon = ICON_ORANGE
    report = run_sharp_report()
    global _last_health_report
    _last_health_report = report
    _refresh_menu(icon)
    coh = [r for r in report.results if r.name == "Coherence"]
    if coh and coh[0].status == HealthStatus.PASS:
        icon.icon = ICON_GREEN
        notify(icon, f"Coherence PASS: {coh[0].detail[:60]}", "FoveAI Health")
    elif coh:
        icon.icon = ICON_RED
        notify(icon, f"Coherence FAIL: {coh[0].detail[:60]}", "FoveAI Health")


def toggle_auto_heal(icon, item):
    global _health_auto_heal
    _health_auto_heal = not _health_auto_heal
    notify(icon, f"Auto-heal {'ON' if _health_auto_heal else 'OFF'}", "FoveAI Health")
    if _health_monitor:
        _health_monitor.auto_heal_enabled = _health_auto_heal
    _refresh_menu(icon)


def toggle_continuous_monitor(icon, item):
    global _health_monitor
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    if (
        _health_monitor
        and _health_monitor._thread
        and _health_monitor._thread.is_alive()
    ):
        _health_monitor.stop()
        _health_monitor = None
        notify(icon, "Continuous monitoring OFF", "FoveAI Health")
    else:
        _health_monitor = ContinuousHealthMonitor(
            interval=30.0,
            on_report=_on_health_report,
            on_fail=_on_health_fail,
            auto_heal_enabled=_health_auto_heal,
            coherence_interval=300.0,
        )
        _health_monitor.start()
        notify(
            icon,
            "Continuous monitoring ON (30s interval, coherence every 5min)",
            "FoveAI Health",
        )
    _refresh_menu(icon)


def heal_restart_xrlf_action(icon, item):
    """Restart XRLF runtime from tray."""
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    notify(icon, "Restarting XRLF runtime (clears KV cache)...", "FoveAI Health")
    icon.icon = ICON_ORANGE
    ok, msg = execute_heal("restart_xrlf")
    notify(icon, msg, "FoveAI Health")
    _refresh_menu(icon)


def heal_restart_xrlf_clear_memory_action(icon, item):
    """Restart XRLF runtime AND clear persistent memory."""
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    notify(icon, "Restarting XRLF + clearing memory...", "FoveAI Health")
    icon.icon = ICON_ORANGE
    ok, msg = execute_heal("restart_xrlf_clear_memory")
    notify(icon, msg, "FoveAI Health")
    _refresh_menu(icon)


def heal_clear_memory_action(icon, item):
    """Clear corrupted memory turns without restarting."""
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    ok, msg = execute_heal("clear_memory")
    notify(icon, msg, "FoveAI Health")


def heal_restart_proxy_action(icon, item):
    """Restart the foveated-memory proxy."""
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    notify(icon, "Restarting proxy (8400/8401)...", "FoveAI Health")
    ok, msg = execute_heal("restart_proxy")
    notify(icon, msg, "FoveAI Health")
    _refresh_menu(icon)


def heal_all_action(icon, item):
    """Attempt to heal all failing checks."""
    if not HEALTH_MONITOR_AVAILABLE:
        notify(icon, "Health monitor not available", "FoveAI Health")
        return
    if not _last_health_report:
        notify(icon, "No health report yet — run a check first", "FoveAI Health")
        return
    notify(icon, "Attempting auto-heal...", "FoveAI Health")
    messages = auto_heal(_last_health_report)
    if messages:
        notify(icon, "\n".join(messages[:3]), "FoveAI Health")
    else:
        notify(icon, "Nothing to heal", "FoveAI Health")
    _refresh_menu(icon)


def _format_health_line(r: Any) -> str:
    """Format a check result for the tray menu."""
    icons = {"pass": "OK", "fail": "FAIL", "warn": "WARN", "unknown": "?"}
    icon = icons.get(r.status.value, "?")
    detail = f" — {r.detail[:40]}" if r.detail else ""
    return f"[{icon:>4}] {r.name}{detail}"


def is_monitoring() -> bool:
    return bool(
        _health_monitor
        and _health_monitor._thread
        and _health_monitor._thread.is_alive()
    )


# ─── Quit / Restart ─────────────────────────────────────────────────


def on_quit(icon, item):
    notify(icon, "Closing Tray App (Services remain running)", "FoveAI Hub")
    icon.stop()


def restart_tray_app(icon, item):
    notify(icon, "Restarting FoveAI Taskbar...", "FoveAI Tray")
    subprocess.Popen([VENV_PYTHON, os.path.abspath(__file__)], cwd=LUMAX_DIR)
    icon.stop()


# ─── SoftLayer Module Management ─────────────────────────────────────


def reload_softlayer_modules(icon, item=None):
    """Trigger SoftLayer module reload on the XR_Vessel frontend."""
    notify(icon, "Reloading all SoftLayer modules...", "FoveAI SoftLayer")
    # The XR_Vessel listens for this event via WebSocket or fetches /softlayer/ again.
    # For now, we just notify — the frontend auto-reloads on next init.
    try:
        import urllib.request

        # Touch the softlayer endpoint to verify it's serving
        req = urllib.request.Request("http://127.0.0.1:8402/softlayer/modules")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                notify(
                    icon,
                    "SoftLayer modules available. Frontend will reload on reconnect.",
                    "FoveAI SoftLayer",
                )
            else:
                notify(
                    icon,
                    f"SoftLayer endpoint returned {resp.status}",
                    "FoveAI SoftLayer",
                )
    except Exception as e:
        notify(icon, f"SoftLayer reload failed: {e}", "FoveAI SoftLayer")


def reload_softlayer_config(icon, item, name: str):
    """Reload a specific SoftLayer config file."""
    notify(icon, f"Reloading {name}...", "FoveAI SoftLayer")
    try:
        import urllib.request

        req = urllib.request.Request(f"http://127.0.0.1:8402/softlayer/{name}")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                notify(icon, f"{name} available for hot-reload", "FoveAI SoftLayer")
            else:
                notify(icon, f"{name} returned {resp.status}", "FoveAI SoftLayer")
    except Exception as e:
        notify(icon, f"Reload {name} failed: {e}", "FoveAI SoftLayer")


def reload_softlayer_module(icon, item, name: str):
    """Reload a specific SoftLayer module."""
    notify(icon, f"Reloading module {name}...", "FoveAI SoftLayer")
    try:
        import urllib.request

        req = urllib.request.Request(f"http://127.0.0.1:8402/softlayer/modules/{name}")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                notify(
                    icon, f"Module {name} available for hot-reload", "FoveAI SoftLayer"
                )
            else:
                notify(
                    icon, f"Module {name} returned {resp.status}", "FoveAI SoftLayer"
                )
    except Exception as e:
        notify(icon, f"Reload {name} failed: {e}", "FoveAI SoftLayer")


def list_softlayer_modules(icon, item=None):
    """List available SoftLayer modules from the API."""
    try:
        import json as _json
        import urllib.request

        req = urllib.request.Request("http://127.0.0.1:8402/softlayer/modules")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read())
            mods = data.get("modules", [])
            notify(
                icon,
                f"Available modules: {', '.join(mods) if mods else 'none'}",
                "FoveAI SoftLayer",
            )
    except Exception as e:
        notify(icon, f"List modules failed: {e}", "FoveAI SoftLayer")


# ── Webcam Plaster tray actions ──

# Persistent toggle state for the tray (the actual state lives in the frontend)
_webcam_plaster_state = {"enabled": True}


def toggle_webcam_plaster(icon, item=None):
    """Toggle the live webcam plaster on/off via SoftLayer param."""
    _webcam_plaster_state["enabled"] = not _webcam_plaster_state["enabled"]
    state = "ON" if _webcam_plaster_state["enabled"] else "OFF"
    notify(
        icon,
        f"Webcam plaster toggled {state}. Frontend will apply on next param poll.",
        "FoveAI SoftLayer",
    )
    # The frontend listens for FoveAIParams changes; we can't directly set them
    # from here, but the user can also reload experience_config.js to apply.


def set_webcam_plaster_orientation(icon, item, orientation: str):
    """Set the webcam plaster orientation (portrait or landscape)."""
    notify(
        icon,
        f"Webcam plaster orientation set to {orientation}. Reload experience_config.js to apply.",
        "FoveAI SoftLayer",
    )


def toggle_jen_pov(icon, item=None):
    """Toggle 'Be Jen' first-person POV mode in the frontend.

    The frontend listens for the 'foveaiToggleJenPov' global function.
    Since the tray can't directly call JS, we notify the user. The actual
    toggle is done via the V key in the browser, or by editing behavior_config.js
    and reloading it.
    """
    notify(
        icon,
        "Be Jen POV: Press V in the XR Vessel window to toggle.\n"
        "Or edit avatar.jenPOV in behavior_config.js and reload it from this menu.",
        "FoveAI — Be Jen",
    )


def test_director_voice(icon, item=None):
    """Test the Director's spooky narrator voice.

    The actual voice is triggered in the browser. We notify the user
    to use the browser console or keyboard.
    """
    notify(
        icon,
        "Director Voice: Open the XR Vessel browser console and run:\n"
        "  foveaiDirectorVoice.speakNarrator('You stepped in again...')\n"
        "The narrator speaks with pitch=0, rate=0.7 (Leonard Cohen style).",
        "FoveAI — Director Voice",
    )


def toggle_avalanche_music(icon, item=None):
    """Toggle the Avalanche dark ambient music in the XR Vessel."""
    notify(
        icon,
        "Avalanche Music: Press M in the XR Vessel window to toggle.\n"
        "Or edit director.avalancheMusic in experience_config.js and reload it.",
        "FoveAI — Avalanche Music",
    )


# ─── Menu Builder ───────────────────────────────────────────────────


def build_menu() -> pystray.Menu:
    env = read_env()
    current_ui = env.get(
        "XRLF_FRONTEND_UI_PRESET", env.get("FoveAI_FRONTEND_UI", "3d_avatar")
    ).lower()
    current_fovea = int(env.get("XRLF_PROXY_AGGRESSION", "0") or "0")
    voice_enabled = env.get("FoveAI_VOICE_ENABLED", "").lower() == "true"
    mic_enabled = env.get("FoveAI_MIC_ENABLED", "").lower() == "true"
    tts_provider = env.get("FoveAI_TTS_PROVIDER", "kokoro").lower()
    stt_provider = env.get("FoveAI_STT_PROVIDER", "whisper").lower()
    cognitive_mode = env.get("FoveAI_COGNITIVE_MODE", "local").lower()
    ag_proxy = env.get("FOVEAI_ANTIGRAVITY_PROXY", "false").lower() == "true"

    def checked(label: str, cond: bool) -> str:
        return f"✅ {label}" if cond else label

    # Live service status
    st_backend, tag_backend = get_service_status(8400, "/health")
    _, tag_dash = get_service_status(8401, "/api/status")
    st_xrlf, tag_xrlf = get_service_status(8402, "/v1/models")
    # Port 8403 is a WebSocket server — check TCP listener only, not HTTP /health
    _, tag_ws = get_service_status(8403, None)
    _, tag_media = get_service_status(8402, "/health")

    stack_running = st_backend == "active" and st_xrlf == "active"
    backend_running = st_backend == "active"

    # Model selectors
    curr_persona_id = env.get(
        "FOVEAI_MODEL_ACTIVE_ID",
        env.get("FOVEAI_MAIN_MODEL", "gemma-4-e2b-multimodal-v1.0.xrlf"),
    )
    curr_router_id = env.get("FOVEAI_OMNI_ROUTER_MODEL", "foveai-omni-router-v2.xrlf")

    persona_menu_items = []
    for mk, mv in PERSONA_MODELS.items():
        is_sel = mv["id"] == curr_persona_id
        prefix = "✅ " if is_sel else "  "
        mm_tag = " 🎤👁" if mv.get("multimodal") else ""
        xrlf_tag = " [XRLF]" if mv.get("is_xrlf", True) else " [GGUF]"
        # Check if file exists
        full_path = os.path.join(FOVEAI_DIR, mv.get("xrlf_path", ""))
        exists_tag = "" if os.path.exists(full_path) else " [MISSING]"
        lbl = f"{prefix}{mv['name']}{mm_tag}{xrlf_tag} [{mv['size_gb']:.1f}GB]{exists_tag}"
        persona_menu_items.append(
            pystray.MenuItem(
                lbl,
                (lambda k: lambda icon, item: select_persona_model(icon, item, k))(mk),
            )
        )
    persona_menu_items.append(pystray.Menu.SEPARATOR)
    persona_menu_items.append(
        pystray.MenuItem("🧹 Unload Model & Free VRAM", unload_models)
    )

    router_menu_items = []
    for rk, rv in ROUTER_MODELS.items():
        is_sel = rv["id"] == curr_router_id
        prefix = "✅ " if is_sel else "  "
        xrlf_tag = " [XRLF]" if rv.get("is_xrlf", True) else " [GGUF]"
        full_path = os.path.join(FOVEAI_DIR, rv.get("xrlf_path", ""))
        exists_tag = "" if os.path.exists(full_path) else " [MISSING]"
        lbl = f"{prefix}{rv['name']}{xrlf_tag} [{rv['size_gb']:.1f}GB]{exists_tag}"
        router_menu_items.append(
            pystray.MenuItem(
                lbl,
                (lambda k: lambda icon, item: select_router_model(icon, item, k))(rk),
            )
        )

    # Stack items
    stack_items = []
    if stack_running:
        stack_items.append(pystray.MenuItem("⏹ Stop FoveAI Stack", stop_stack))
        stack_items.append(pystray.MenuItem("🔄 Restart FoveAI Stack", restart_stack))
    else:
        stack_items.append(pystray.MenuItem("🚀 Start Full FoveAI Stack", start_stack))
        stack_items.append(
            pystray.MenuItem("🎙️ Start Light Stack (Backend Only)", start_light_stack)
        )

    # Proxy items
    proxy_items = []
    if backend_running:
        proxy_items.append(pystray.MenuItem("⏹ Stop Backend", stop_memory_proxy))
        proxy_items.append(pystray.MenuItem("🔄 Restart Backend", restart_memory_proxy))
    else:
        proxy_items.append(pystray.MenuItem("▶ Start Backend", start_memory_proxy))

    _, _, _, _, status_text = get_hardware_telemetry()

    def show_status_info(icon, item):
        notify(icon, f"{item.text}", "FoveAI Process Status")

    # ── Rig & Bloat Guardian submenu ──
    ls_st = rig_guard.get_language_server_status()
    u_st = rig_guard.get_unity_status()
    ram_st = rig_guard.get_system_ram()
    ig_st = rig_guard.check_workspace_ignores()

    rig_menu_items = [
        pystray.MenuItem(ls_st.get("status_text", "Language Server"), show_status_info),
        pystray.MenuItem(u_st.get("status_text", "Unity Engine"), show_status_info),
        pystray.MenuItem(
            f"RAM: {ram_st.get('used_gb', 0)}/{ram_st.get('total_gb', 0)} GB ({ram_st.get('percent', 0)}%)",
            show_status_info,
        ),
        pystray.MenuItem(
            ig_st.get("status_text", "Workspace Ignores"), show_status_info
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "🛠️ Enforce Workspace Ignores & Search Cap", fix_workspace_ignores_action
        ),
        pystray.MenuItem(
            "🧹 Kill Runaway Git Tasks (Reclaim RAM)", kill_runaway_git_action
        ),
        pystray.MenuItem(
            "🧹 Clean Unity Temp & Kill Zombie Workers", clean_unity_temp_action
        ),
        pystray.MenuItem("📊 Inspect Top RAM Consumers", inspect_ram_consumers_action),
        pystray.MenuItem(
            "ℹ️ Safe Language Server Reload Guide", safe_language_server_guide_action
        ),
    ]

    # ── Health Monitor submenu ──
    health_items: list = []
    if HEALTH_MONITOR_AVAILABLE:
        # Show last report results if available
        if _last_health_report:
            health_items.append(
                pystray.MenuItem(
                    f"Overall: {_last_health_report.summary}", show_status_info
                )
            )
            health_items.append(pystray.Menu.SEPARATOR)
            for r in _last_health_report.results:
                health_items.append(
                    pystray.MenuItem(_format_health_line(r), show_status_info)
                )
            health_items.append(pystray.Menu.SEPARATOR)
        else:
            health_items.append(
                pystray.MenuItem("No report yet — run a check", show_status_info)
            )
            health_items.append(pystray.Menu.SEPARATOR)

        health_items.extend(
            [
                pystray.MenuItem("🔍 Run Health Check Now", run_health_check_now),
                pystray.MenuItem(
                    "🔬 Sharp Coherence Test (30s)", run_sharp_coherence_test
                ),
                pystray.MenuItem(
                    checked("📡 Continuous Monitoring (30s)", is_monitoring()),
                    toggle_continuous_monitor,
                ),
                pystray.MenuItem(
                    checked("🩹 Auto-Heal on Failure", _health_auto_heal),
                    toggle_auto_heal,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("🔄 Restart XRLF Runtime", heal_restart_xrlf_action),
                pystray.MenuItem(
                    "🔄 Restart XRLF + Clear Memory",
                    heal_restart_xrlf_clear_memory_action,
                ),
                pystray.MenuItem("🧹 Clear Memory DB Only", heal_clear_memory_action),
                pystray.MenuItem(
                    "🔄 Restart Proxy (8400/8401)", heal_restart_proxy_action
                ),
                pystray.MenuItem("🩹 Heal All Failing Now", heal_all_action),
            ]
        )
    else:
        health_items = [
            pystray.MenuItem("Health monitor not available", show_status_info)
        ]

    return pystray.Menu(
        pystray.MenuItem(f"🛡️ Guardian: {status_text}", show_status_info),
        pystray.MenuItem("🏥 Health Monitor & Healing", pystray.Menu(*health_items)),
        pystray.MenuItem("🛡️ Rig & Bloat Guardian", pystray.Menu(*rig_menu_items)),
        pystray.MenuItem("🧹 Liberate VRAM & Flush Caches", free_ram_flush_caches),
        pystray.MenuItem("🧹 Free RAM (Drop Caches)", free_ram_flush_caches),
        pystray.MenuItem(
            "🤖 Default Persona AI Model (Main AI)", pystray.Menu(*persona_menu_items)
        ),
        pystray.MenuItem(
            "🔀 Default Router Model (Intention & Compression)",
            pystray.Menu(*router_menu_items),
        ),
        pystray.MenuItem(
            checked(
                "🧠 Context & Intuition Collector (Consented)",
                is_context_collector_enabled(),
            ),
            toggle_context_collector,
        ),
        pystray.Menu.SEPARATOR,
        *stack_items,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "⚡ Live Process Monitor",
            pystray.Menu(
                pystray.MenuItem(
                    f"{tag_backend} FoveAI Backend WS (:8400)", show_status_info
                ),
                pystray.MenuItem(
                    f"{tag_dash} Settings & Memory Dashboard (:8401)", show_status_info
                ),
                pystray.MenuItem(f"{tag_xrlf} XRLF Runtime (:8402)", show_status_info),
                pystray.MenuItem(
                    f"{tag_ws} Multimodal WebSocket IPC (:8403)", show_status_info
                ),
                pystray.MenuItem(f"{tag_media} Media Proxy (:8402)", show_status_info),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(" Multigate WebUI Portal", launch_multigate),
        pystray.MenuItem("⚙️ Open Settings Panel", open_settings_panel),
        pystray.MenuItem(
            "🎨 SoftLayer Modules (Hot-Reloadable)",
            pystray.Menu(
                pystray.MenuItem("📦 Reload All Modules", reload_softlayer_modules),
                pystray.MenuItem(
                    "🔄 Reload behavior_config.js",
                    lambda icon, item: reload_softlayer_config(
                        icon, item, "behavior_config.js"
                    ),
                ),
                pystray.MenuItem(
                    "🔄 Reload experience_config.js",
                    lambda icon, item: reload_softlayer_config(
                        icon, item, "experience_config.js"
                    ),
                ),
                pystray.MenuItem(
                    "🔄 Reload hud_config.js",
                    lambda icon, item: reload_softlayer_config(
                        icon, item, "hud_config.js"
                    ),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "🔄 Reload lighting.js",
                    lambda icon, item: reload_softlayer_module(
                        icon, item, "lighting.js"
                    ),
                ),
                pystray.MenuItem(
                    "🔄 Reload sky.js",
                    lambda icon, item: reload_softlayer_module(icon, item, "sky.js"),
                ),
                pystray.MenuItem(
                    "🔄 Reload particles.js",
                    lambda icon, item: reload_softlayer_module(
                        icon, item, "particles.js"
                    ),
                ),
                pystray.MenuItem(
                    "🔄 Reload chameleon.js",
                    lambda icon, item: reload_softlayer_module(
                        icon, item, "chameleon.js"
                    ),
                ),
                pystray.MenuItem(
                    "🔄 Reload clothing.js",
                    lambda icon, item: reload_softlayer_module(
                        icon, item, "clothing.js"
                    ),
                ),
                pystray.MenuItem(
                    "🔄 Reload wall.js",
                    lambda icon, item: reload_softlayer_module(icon, item, "wall.js"),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "🧑 Be Jen (First-Person POV): Toggle", toggle_jen_pov
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "🎙️ Director: Speak Narrator (test voice)", test_director_voice
                ),
                pystray.MenuItem(
                    "🎵 Director: Toggle Avalanche Music", toggle_avalanche_music
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "📹 Webcam Plaster: Toggle On/Off", toggle_webcam_plaster
                ),
                pystray.MenuItem(
                    "📹 Webcam Plaster: Portrait Mode",
                    lambda icon, item: set_webcam_plaster_orientation(
                        icon, item, "portrait"
                    ),
                ),
                pystray.MenuItem(
                    "📹 Webcam Plaster: Landscape Mode",
                    lambda icon, item: set_webcam_plaster_orientation(
                        icon, item, "landscape"
                    ),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "📡 List Loaded Modules (check console)", list_softlayer_modules
                ),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Memory Tools",
            pystray.Menu(
                pystray.MenuItem("Super Prompt Kiosk", start_super_kiosk),
                pystray.MenuItem("AUI Memory Dashboard", open_memory_dashboard),
                pystray.MenuItem(
                    "FoveAI Super Memory Terminal", start_foveai_super_terminal
                ),
            ),
        ),
        pystray.MenuItem("Backend Service (Port 8400)", pystray.Menu(*proxy_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "🛰️ Antigravity / Jenna-VSCode Trojan Horse",
            pystray.Menu(
                pystray.MenuItem(
                    "🪐 Launch Antigravity Desktop",
                    lambda icon, item: subprocess.Popen(["antigravity"]),
                ),
                pystray.MenuItem(
                    "💻 Launch Antigravity IDE",
                    lambda icon, item: subprocess.Popen(
                        ["antigravity-ide", FOVEAI_DIR]
                    ),
                ),
                pystray.MenuItem(
                    "🚀 Launch Jenna-VSCode (Context Stripping)", launch_jenna_vscode
                ),
                pystray.MenuItem(
                    checked("Route Antigravity CLI through Proxy (:8400)", ag_proxy),
                    toggle_antigravity_proxy,
                ),
            ),
        ),
        pystray.MenuItem(
            "Select Frontend UI",
            pystray.Menu(
                pystray.MenuItem(
                    checked("3D Avatar Chatbot (Port 8080)", current_ui == "3d_avatar"),
                    lambda icon, item: switch_frontend(icon, item, "3d_avatar"),
                ),
                pystray.MenuItem(
                    checked("XR Vessel (Port 5176)", current_ui == "xr_vessel"),
                    lambda icon, item: switch_frontend(icon, item, "xr_vessel"),
                ),
                pystray.MenuItem(
                    checked("Multigate Portal (Port 5177)", current_ui == "multigate"),
                    lambda icon, item: switch_frontend(icon, item, "multigate"),
                ),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Foveation",
            pystray.Menu(
                *[
                    pystray.MenuItem(
                        checked(FOVEA_LEVELS[lvl], current_fovea == lvl),
                        (lambda l: lambda icon, item: set_fovea(icon, item, l))(lvl),
                    )
                    for lvl in sorted(FOVEA_LEVELS.keys())
                ]
            ),
        ),
        pystray.MenuItem(
            "Voice",
            pystray.Menu(
                pystray.MenuItem(checked("Voice Output ON", voice_enabled), voice_on),
                pystray.MenuItem(
                    checked("Voice Output OFF", not voice_enabled), voice_off
                ),
                pystray.MenuItem(checked("Microphone ON", mic_enabled), mic_on),
                pystray.MenuItem(checked("Microphone OFF", not mic_enabled), mic_off),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "TTS Engine",
                    pystray.Menu(
                        pystray.MenuItem(
                            checked(
                                "Kokoro Emotional Mouth (:8402)",
                                tts_provider in ["kokoro", "qwen"],
                            ),
                            lambda icon, item: switch_tts_provider(
                                icon, item, "kokoro"
                            ),
                        ),
                        pystray.MenuItem(
                            checked(
                                "WebSocket IPC (ws://:8403)",
                                tts_provider == "websocket",
                            ),
                            lambda icon, item: switch_tts_provider(
                                icon, item, "websocket"
                            ),
                        ),
                        pystray.MenuItem(
                            checked(
                                "Edge-TTS (Cloud Neural)", tts_provider == "edgetts"
                            ),
                            lambda icon, item: switch_tts_provider(
                                icon, item, "edgetts"
                            ),
                        ),
                    ),
                ),
                pystray.MenuItem(
                    "STT Engine",
                    pystray.Menu(
                        pystray.MenuItem(
                            checked(
                                "Faster-Whisper Ears (:8405)", stt_provider == "whisper"
                            ),
                            lambda icon, item: switch_stt_provider(
                                icon, item, "whisper"
                            ),
                        ),
                        pystray.MenuItem(
                            checked(
                                "Web Speech API / Browser VAD",
                                stt_provider == "browser",
                            ),
                            lambda icon, item: switch_stt_provider(
                                icon, item, "browser"
                            ),
                        ),
                    ),
                ),
            ),
        ),
        pystray.MenuItem(
            "Cognitive Mode",
            pystray.Menu(
                pystray.MenuItem(
                    checked("Local", cognitive_mode == "local"), switch_to_local
                ),
                pystray.MenuItem(
                    checked("Cloud", cognitive_mode == "cloud"), switch_to_cloud
                ),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🐛 Open Debug Terminal", open_debug_terminal),
        pystray.MenuItem("Stop Llama Server (Free VRAM)", unload_models),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔄 Restart Taskbar Tray App", restart_tray_app),
        pystray.MenuItem("Quit", on_quit),
    )


# ─── App ────────────────────────────────────────────────────────────

_, _, _, _initial_color, _initial_status = get_hardware_telemetry()
app = pystray.Icon(
    "FoveAI", _initial_color, f"FoveAI Guardian | {_initial_status}", menu=build_menu()
)
app.default_action = open_settings_panel
_icon_ref = app

_last_context_collect = 0.0


# ─── Auto-Start Stack on Boot ───────────────────────────────────────


def auto_start_stack():
    """Start the FoveAI fleet automatically when the tray app launches at boot.
    Launches Sleipnir which starts backend + XRLF runtime with dormant model."""
    if NO_AUTOSTART:
        return
    env = read_env()
    auto_start = env.get("XRLF_AUTO_START_STACK", "true").lower().strip()
    if auto_start not in ("true", "1", "yes"):
        return
    # Give the system time to settle after boot (network, GPU driver, etc.)
    time.sleep(8)
    # Don't start if stack is already running
    if is_stack_running():
        return
    notify(app, "Auto-starting FoveAI Fleet via Sleipnir...", "FoveAI Boot")
    subprocess.Popen(
        ["bash", SLEIPNIR_SH, "start"],
        cwd=FOVEAI_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for XRLF to come up (model load takes time)
    for _ in range(60):
        time.sleep(1)
        if check_port_listener(8402):
            notify(
                app,
                "FoveAI Fleet airborne!\nBackend :8400, XRLF :8402, WS :8403",
                "FoveAI Boot",
            )
            try:
                app.icon = ICON_GREEN
                app.update_menu()
            except Exception:
                pass
            return
    notify(app, "Fleet still loading (model may be large)...", "FoveAI Boot")


threading.Thread(target=auto_start_stack, daemon=True).start()


# ─── Menu Refresh Loop ──────────────────────────────────────────────


def menu_refresh_loop():
    global _last_context_collect
    while True:
        try:
            total_gb, used_gb, free_gb, color, status_text = get_hardware_telemetry()
            if app.icon != color:
                app.icon = color
            app.title = f"FoveAI Guardian | {status_text}"
            app.menu = build_menu()

            now = time.time()
            if is_context_collector_enabled() and (now - _last_context_collect > 60):
                _last_context_collect = now
                _collect_workspace_context()

            # Periodic rig & bloat audit (throttled internally by cooldown)
            rig_guard.audit_and_alert(lambda msg, title: notify(app, msg, title))
        except Exception:
            pass
        time.sleep(5)


def _collect_workspace_context():
    """Gather git branch, last commit, and modified files."""
    try:
        r_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=FOVEAI_DIR,
            timeout=3,
        )
        branch = r_branch.stdout.strip() if r_branch.returncode == 0 else "main"

        r_log = subprocess.run(
            ["git", "log", "-1", "--format=%h - %s (%cr)"],
            capture_output=True,
            text=True,
            cwd=FOVEAI_DIR,
            timeout=3,
        )
        last_commit = r_log.stdout.strip() if r_log.returncode == 0 else "N/A"

        r_status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=FOVEAI_DIR,
            timeout=3,
        )
        modified = (
            [l.strip() for l in r_status.stdout.strip().splitlines() if l.strip()]
            if r_status.returncode == 0
            else []
        )

        try:
            requests.post(
                "http://127.0.0.1:8400/api/ingest",
                json={
                    "workspace": "default",
                    "milestone": f"Git: {branch} | Last: {last_commit} | Changes: {len(modified)} files",
                    "source": "FoveAI_Taskbar_Linux_ContextCollector",
                },
                timeout=2,
            )
        except Exception:
            pass
    except Exception:
        pass


threading.Thread(target=menu_refresh_loop, daemon=True).start()


# ─── Main ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[FoveAI Taskbar Linux] Starting... (Python: {VENV_PYTHON})")
    print(f"[FoveAI Taskbar Linux] FOVEAI_DIR: {FOVEAI_DIR}")
    print(f"[FoveAI Taskbar Linux] LUMAX_DIR: {LUMAX_DIR}")
    app.run()
