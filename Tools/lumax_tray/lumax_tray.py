#!/usr/bin/env python3
"""
LUMAX System Tray Icon — Primary Launcher for Windows.
Replaces the Chrome Extension as the recommended way to start/stop the LUMAX stack.
Provides: Start, Stop, Open Web UI, Service Status, Auto-start registration.

Usage:
    python Tools/lumax_tray/lumax_tray.py          # Run interactively
    python Tools/lumax_tray/lumax_tray.py --register  # Add to Windows Startup
    python Tools/lumax_tray/lumax_tray.py --unregister # Remove from Startup
"""

import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

# ── Project Root ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))

# ── Service Health Endpoints ──
HEALTH_ENDPOINTS = {
    "Soul Core": ("http://127.0.0.1:8000/health", 8000),
    "Nexus Proxy": ("http://127.0.0.1:8080/", 8080),
    "TokenSlayer": ("http://127.0.0.1:8103/health", 8103),
    "Motor Cortex": ("http://127.0.0.1:8110/health", 8110),
    "Stardust": ("http://127.0.0.1:8109/health", 8109),
    "Ears (STT)": ("http://127.0.0.1:8001/health", 8001),
    "Mouth (TTS)": ("http://127.0.0.1:8004/health", 8004),
}

LUMAX_PORTS = [
    8000,
    8001,
    8002,
    8003,
    8004,
    8080,
    8103,
    8104,
    8106,
    8109,
    8110,
    8112,
    8113,
    8888,
    5000,
]

# ── State ──
_stack_running = False
_stack_starting = False
_health_results = {}
_health_lock = threading.Lock()
_health_monitor_active = False  # Only start pinging after user explicitly starts stack
_tray_start_time = time.time()  # Timestamp when tray started — used for grace period

# ── Helpers ──


def http_ok(url, timeout=3, quiet=False):
    """Check if a URL returns HTTP 200.
    Uses GET instead of HEAD because many LUMAX services (uvicorn FastAPI)
    don't implement HEAD handlers and return 405 Method Not Allowed.
    Returns True/False and logs failures for debugging unless quiet is True."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if status == 200:
                return True
            if not quiet:
                print(f"[LumaxTray] ⚠️ {url} returned HTTP {status}")
            return False
    except urllib.error.HTTPError as e:
        # 405 Method Not Allowed — service is running but doesn't support GET on this path
        if e.code == 405:
            return True  # Service is alive, just wrong method
        if not quiet:
            print(f"[LumaxTray] ⚠️ {url} HTTP {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        if not quiet:
            print(f"[LumaxTray] ⚠️ {url} unreachable: {e.reason}")
        return False
    except Exception as e:
        if not quiet:
            print(f"[LumaxTray] ⚠️ {url} error: {e}")
        return False


def check_services():
    """Check all LUMAX services and return status dict."""
    results = {}
    for name, (url, port) in HEALTH_ENDPOINTS.items():
        results[name] = http_ok(url)
    return results


def is_stack_running():
    """Return True if at least Soul Core and Nexus Proxy are up.
    Nexus Proxy (port 8080) runs npm install first, which can take 30-60s.
    Soul Core starts much faster (~5s). We check Soul Core first, then
    Nexus Proxy with a longer timeout.
    Verifies the response body contains 'status":"ok"' to avoid false positives
    from other services that might be squatting on port 8000."""
    soul_ok = _check_soul_health(timeout=2)
    if not soul_ok:
        return False
    proxy_ok = http_ok("http://127.0.0.1:8080/", timeout=3)
    return proxy_ok


def _check_soul_health(timeout=2):
    """Check Soul Core health by verifying HTTP 200 AND response body contains 'status":"ok"'.
    This prevents false positives from zombie processes or other services on port 8000."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read().decode("utf-8")
            # Verify the response is actually from Soul Core — must contain 'status":"ok"'
            if '"status":"ok"' in body or '"status": "ok"' in body:
                return True
            return False
    except Exception:
        return False


def is_stack_running_quiet():
    """Same as is_stack_running() but suppresses all logging — used during grace period
    to avoid frantic 'unreachable' messages when the stack hasn't been started yet.
    Also verifies response body to avoid false positives from zombie processes."""
    return _check_soul_health(timeout=2)


def start_stack():
    """Start the LUMAX stack via sleipnir_launcher.js directly.
    Skips Start_Concordia.PS1 because it requires Microsoft.PowerShell.Security
    module (Get-ExecutionPolicy) which may not load in all environments.
    Node.js sleipnir_launcher.js is the canonical launcher."""
    global _stack_starting, _health_monitor_active
    _stack_starting = True
    _health_monitor_active = (
        True  # Activate health monitoring now that user explicitly started
    )

    js_path = os.path.join(PROJECT_ROOT, "sleipnir_launcher.js")

    if os.path.exists(js_path):
        subprocess.Popen(
            ["node", js_path],
            cwd=PROJECT_ROOT,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        print("[LumaxTray] ERROR: sleipnir_launcher.js not found")
        _stack_starting = False
        return False

    # Background health poll with real-time progress
    def _poll():
        global _stack_running, _stack_starting
        poll_start = time.time()
        max_wait = 120  # npm install can take 60s+
        soul_up = False
        proxy_up = False

        # Initial delay: give the launcher time to spawn processes before first ping.
        time.sleep(5)

        print("\n[LumaxTray] ⏳ Starting Stack... please wait.")
        while time.time() - poll_start < max_wait:
            elapsed = time.time() - poll_start

            # Simple visual loading percentage (0-99%) based on a typical 40s boot time
            progress = min(int((elapsed / 40.0) * 100), 99)
            print(f"\r[LumaxTray] ⏳ Loading... {progress}%", end="", flush=True)

            if not soul_up:
                soul_up = http_ok("http://127.0.0.1:8000/health", timeout=2, quiet=True)
                if soul_up:
                    print(f"\n[LumaxTray] ✅ Soul Core UP ({elapsed:.0f}s)")
            if soul_up and not proxy_up:
                proxy_up = http_ok("http://127.0.0.1:8080/", timeout=3, quiet=True)
                if proxy_up:
                    print(f"\n[LumaxTray] ✅ Nexus Proxy UP ({elapsed:.0f}s)")
            if soul_up and proxy_up:
                _stack_running = True
                _stack_starting = False
                print(
                    f"\n[LumaxTray] ✅ Stack started successfully in {elapsed:.0f}s\n"
                )

                # Auto-start Top Bar now that the stack is ready
                topbar_path = os.path.join(
                    PROJECT_ROOT, "Tools", "lumax_top_bar", "lumax_top_bar.py"
                )
                if os.path.exists(topbar_path):
                    print("[LumaxTray] 🚀 Launching Top Bar...")
                    subprocess.Popen(
                        [sys.executable, topbar_path],
                        cwd=PROJECT_ROOT,
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )

                return
            time.sleep(2)

        elapsed = time.time() - poll_start
        print(f"[LumaxTray] ⚠️ Stack start timed out after {elapsed:.0f}s")
        if soul_up:
            print(
                "[LumaxTray]   Soul Core: UP — Nexus Proxy may still be installing npm packages"
            )
        _stack_starting = False

    threading.Thread(target=_poll, daemon=True).start()
    return True


def stop_stack():
    """Stop all LUMAX services by killing processes on known ports.
    Uses netstat (native Windows) instead of Get-NetTCPConnection (PowerShell module)
    to avoid module loading issues."""
    global _stack_running, _health_monitor_active
    _stack_running = False
    _health_monitor_active = False  # Deactivate health monitoring — no more pinging

    # Use netstat to find PIDs on LUMAX ports (native Windows, no PS modules needed)
    pids = set()
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in out.stdout.split("\n"):
            for port in LUMAX_PORTS:
                if f":{port} " in line and ("LISTENING" in line or "TIME_WAIT" in line):
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        try:
                            pids.add(int(parts[4]))
                        except ValueError:
                            pass
                    break
    except Exception as e:
        print(f"[LumaxTray] ⚠️ netstat scan failed: {e}")

    # Kill found PIDs
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/pid", str(pid), "/f"], capture_output=True, timeout=5
            )
        except Exception:
            pass

    # Wait for ports to clear
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=3
            )
            still_busy = False
            for port in LUMAX_PORTS:
                for line in out.stdout.split("\n"):
                    if f":{port} " in line and (
                        "LISTENING" in line or "TIME_WAIT" in line
                    ):
                        still_busy = True
                        break
                if still_busy:
                    break
            if not still_busy:
                print("[LumaxTray] ✅ All ports cleared")
                return
        except Exception:
            pass
        time.sleep(1)
    print("[LumaxTray] ⚠️ Some ports may still be in TIME_WAIT")


def kill_all():
    """Aggressively kill ALL node.exe and python.exe processes on LUMAX ports — no preservation.
    Uses netstat (native Windows) instead of Get-NetTCPConnection (PowerShell module)
    to avoid module loading issues."""
    global _stack_running, _health_monitor_active
    _stack_running = False
    _health_monitor_active = False  # Deactivate health monitoring

    print(
        "[LumaxTray] 💀 Kill All: Terminating ALL LUMAX processes (no preservation)..."
    )

    # Use netstat to find PIDs on LUMAX ports (native Windows, no PS modules needed)
    pids = set()
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in out.stdout.split("\n"):
            for port in LUMAX_PORTS:
                if f":{port} " in line and ("LISTENING" in line or "TIME_WAIT" in line):
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        try:
                            pids.add(int(parts[4]))
                        except ValueError:
                            pass
                    break
    except Exception as e:
        print(f"[LumaxTray] ⚠️ netstat scan failed: {e}")

    # Kill found PIDs
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/pid", str(pid), "/f"], capture_output=True, timeout=5
            )
        except Exception:
            pass

    # Then kill ALL node.exe and python.exe (nuclear option — catches any stragglers)
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Get-Process node,python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        timeout=10,
    )

    # Wait for ports to clear
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=3
            )
            still_busy = False
            for port in LUMAX_PORTS:
                for line in out.stdout.split("\n"):
                    if f":{port} " in line and (
                        "LISTENING" in line or "TIME_WAIT" in line
                    ):
                        still_busy = True
                        break
                if still_busy:
                    break
            if not still_busy:
                print("[LumaxTray] ✅ All ports cleared after nuclear sweep")
                return
        except Exception:
            pass
        time.sleep(1)
    print("[LumaxTray] ⚠️ Some ports may still be in TIME_WAIT after nuclear sweep")


def restart_stack():
    """Kill ALL processes, then start fresh — no preservation."""
    kill_all()
    # Small delay to let ports fully release
    time.sleep(2)
    start_stack()


def register_startup():
    """Add tray icon to Windows Startup folder."""
    startup_folder = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )
    if not os.path.exists(startup_folder):
        print("[LumaxTray] Could not find Startup folder")
        return False

    vbs_path = os.path.join(startup_folder, "LumaxTray.lnk")
    # Create a VBS script to launch the tray icon silently
    vbs_content = f'''CreateObject("Wscript.Shell").Run """{sys.executable}"" ""{os.path.join(SCRIPT_DIR, "lumax_tray.py")}""", 0, False
'''
    vbs_launcher = os.path.join(startup_folder, "LumaxTray.vbs")
    try:
        with open(vbs_launcher, "w") as f:
            f.write(vbs_content)
        print(f"[LumaxTray] ✅ Startup shortcut created: {vbs_launcher}")
        return True
    except Exception as e:
        print(f"[LumaxTray] Failed to create startup shortcut: {e}")
        return False


def unregister_startup():
    """Remove tray icon from Windows Startup."""
    startup_folder = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )
    vbs_launcher = os.path.join(startup_folder, "LumaxTray.vbs")
    if os.path.exists(vbs_launcher):
        os.remove(vbs_launcher)
        print("[LumaxTray] ✅ Startup shortcut removed")
    else:
        print("[LumaxTray] No startup shortcut found")


# ── 3D Avatar Toggle ──

_avatar_3d_enabled = True  # cached state, refreshed on menu open


def _read_env_bool(key: str, default: str = "true") -> str:
    """Read a boolean value from .env file."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return default
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return val
    except Exception:
        pass
    return default


def _write_env_bool(key: str, value: str) -> None:
    """Write a boolean value to .env file."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"[LumaxTray] Failed to write {key} to .env: {e}")


def _refresh_avatar_state():
    """Refresh cached 3D avatar enabled state from .env."""
    global _avatar_3d_enabled
    val = _read_env_bool("LUMAX_HUD_ENABLED", "true")
    _avatar_3d_enabled = val.lower() in ("true", "1", "yes")


def on_toggle_avatar(icon, item):
    """Toggle 3D avatar on/off by writing to .env."""
    global _avatar_3d_enabled
    _avatar_3d_enabled = not _avatar_3d_enabled
    new_val = "true" if _avatar_3d_enabled else "false"
    _write_env_bool("LUMAX_HUD_ENABLED", new_val)
    print(f"[LumaxTray] 3D Avatar toggled to: {new_val}")
    # Update the menu text immediately
    icon.update_menu()


# ── Chat Provider Toggle ──

_chat_provider = "ollama_cloud"


def _refresh_chat_provider():
    global _chat_provider
    val = _read_env_bool("LUMAX_CHAT_PROVIDER", "ollama_cloud")
    _chat_provider = val.lower()


def on_set_chat_provider(provider):
    def inner(icon, item):
        global _chat_provider
        _chat_provider = provider
        _write_env_bool("LUMAX_CHAT_PROVIDER", provider)
        print(f"[LumaxTray] Chat Provider set to: {provider}")
        icon.update_menu()

    return inner


def get_prov_menu_text(provider, display_name):
    def inner(item):
        _refresh_chat_provider()
        return f"{'✅' if _chat_provider == provider else '  '} {display_name}"

    return inner


# ── Front-End UI & OpenXR Runtime State ──

_frontend_mode = "desktop_avatar"
_openxr_runtime = "virtual_desktop"


def _refresh_frontend_settings():
    global _frontend_mode, _openxr_runtime
    _frontend_mode = _read_env_bool("LUMAX_FRONTEND_MODE", "desktop_avatar").lower()
    _openxr_runtime = _read_env_bool("LUMAX_OPENXR_RUNTIME", "virtual_desktop").lower()


def on_set_frontend_mode(mode):
    def inner(icon, item):
        global _frontend_mode
        _frontend_mode = mode
        _write_env_bool("LUMAX_FRONTEND_MODE", mode)
        print(f"[LumaxTray] Front-End Mode set to: {mode}")
        if mode == "desktop_audio":
            topbar_script = os.path.join(
                PROJECT_ROOT, "Tools", "lumax_top_bar", "lumax_top_bar.py"
            )
            subprocess.Popen(
                [sys.executable, topbar_script, "--quick-controls"],
                cwd=PROJECT_ROOT,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        elif mode == "desktop_avatar":
            subprocess.Popen(
                [
                    sys.executable,
                    os.path.join(PROJECT_ROOT, "Tools", "lumax_desktop_vessel.py"),
                ],
                cwd=PROJECT_ROOT,
            )
        elif mode == "text_chat":
            webbrowser.open("http://127.0.0.1:5176?mode=chat")
        elif mode == "xr_passthrough":
            webbrowser.open("http://127.0.0.1:5176?mode=ar&passthrough=true")
        elif mode == "xr_vr":
            webbrowser.open("http://127.0.0.1:5176?mode=vr")
        icon.update_menu()

    return inner


def on_set_openxr_runtime(runtime):
    def inner(icon, item):
        global _openxr_runtime
        _openxr_runtime = runtime
        _write_env_bool("LUMAX_OPENXR_RUNTIME", runtime)
        print(f"[LumaxTray] OpenXR Runtime set to: {runtime}")
        icon.update_menu()

    return inner


def get_fe_menu_text(mode, display_name):
    def inner(item):
        _refresh_frontend_settings()
        return f"{'✅' if _frontend_mode == mode else '  '} {display_name}"

    return inner


def get_xr_menu_text(runtime, display_name):
    def inner(item):
        _refresh_frontend_settings()
        return f"{'✅' if _openxr_runtime == runtime else '  '} {display_name}"

    return inner


# ── Tray Icon ──


def create_tray_icon():
    """Create and run the system tray icon."""
    import pystray
    from PIL import Image, ImageDraw, ImageFont

    _refresh_avatar_state()

    def create_image():
        """Create a 64x64 LUMAX icon (cyan 'Λ' on dark background)."""
        img = Image.new("RGB", (64, 64), color=(5, 7, 10))
        dc = ImageDraw.Draw(img)
        # Draw a cyan circle
        dc.ellipse([4, 4, 60, 60], outline=(0, 243, 255), width=3)
        # Draw 'Λ' symbol
        try:
            font = ImageFont.truetype("segoeui.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        dc.text((20, 14), "Λ", fill=(0, 243, 255), font=font)
        return img

    def get_status_text():
        """Return current status string."""
        if _stack_starting:
            return "Starting..."
        if _stack_running:
            return "Running"
        return "Stopped"

    def on_start(icon, item):
        if not _stack_running and not _stack_starting:
            threading.Thread(target=start_stack, daemon=True).start()

    def on_stop(icon, item):
        if _stack_running:
            threading.Thread(target=stop_stack, daemon=True).start()

    def on_restart(icon, item):
        """Kill ALL processes and restart fresh — no preservation."""
        threading.Thread(target=restart_stack, daemon=True).start()

    def on_open_web(icon, item):
        domain = _read_env_bool("LUMAX_TOP_DOMAIN", "")
        if domain and domain.lower() != "false":
            webbrowser.open(f"https://{domain}")
        else:
            webbrowser.open("http://localhost:8080")

    def on_open_topbar(icon, item):
        subprocess.Popen(
            [
                sys.executable,
                os.path.join(
                    PROJECT_ROOT, "Tools", "lumax_top_bar", "lumax_top_bar.py"
                ),
            ],
            cwd=PROJECT_ROOT,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def on_open_quick_controls(icon, item):
        topbar_script = os.path.join(
            PROJECT_ROOT, "Tools", "lumax_top_bar", "lumax_top_bar.py"
        )
        subprocess.Popen(
            [sys.executable, topbar_script, "--quick-controls"],
            cwd=PROJECT_ROOT,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def on_show_status(icon, item):
        """Show service status in a popup."""
        results = check_services()
        status_lines = []
        for name, ok in results.items():
            icon_str = "✅" if ok else "❌"
            status_lines.append(f"  {icon_str} {name}")

        def show_popup():
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            # Make sure it appears on top
            root.attributes("-topmost", True)
            msg = "LUMAX Service Status:\n\n" + "\n".join(status_lines)
            messagebox.showinfo("LUMAX Status", msg)
            root.destroy()

        threading.Thread(target=show_popup, daemon=True).start()

    def on_register(icon, item):
        register_startup()

    def on_unregister(icon, item):
        unregister_startup()

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    def get_avatar_menu_text(item):
        """Return dynamic menu text for 3D avatar toggle."""
        _refresh_avatar_state()
        return f"{'✅' if _avatar_3d_enabled else '❌'} 3D Avatar ({'ON' if _avatar_3d_enabled else 'OFF'})"

    # Build menu
    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: f"LUMAX — {get_status_text()}", None, enabled=False
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "🚀 Start Stack",
            on_start,
            enabled=lambda item: not _stack_running and not _stack_starting,
        ),
        pystray.MenuItem("⏹ Stop Stack", on_stop, enabled=lambda item: _stack_running),
        pystray.MenuItem(
            "🔄 Kill All & Restart",
            on_restart,
            enabled=lambda item: not _stack_starting,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "🖥️ Select Front-End UI",
            pystray.Menu(
                pystray.MenuItem(
                    get_fe_menu_text(
                        "desktop_audio", "🎧 Desktop Audio Only (Lightweight PTT)"
                    ),
                    on_set_frontend_mode("desktop_audio"),
                ),
                pystray.MenuItem(
                    get_fe_menu_text("desktop_avatar", "🎭 Desktop 3D Avatar + Audio"),
                    on_set_frontend_mode("desktop_avatar"),
                ),
                pystray.MenuItem(
                    get_fe_menu_text("text_chat", "💬 Text Chat Only WebUI"),
                    on_set_frontend_mode("text_chat"),
                ),
                pystray.MenuItem(
                    get_fe_menu_text(
                        "xr_passthrough", "🥽 XR Quest 3 Passthrough (WebXR AR)"
                    ),
                    on_set_frontend_mode("xr_passthrough"),
                ),
                pystray.MenuItem(
                    get_fe_menu_text("xr_vr", "🌌 XR Quest 3 Immersive VR"),
                    on_set_frontend_mode("xr_vr"),
                ),
            ),
        ),
        pystray.MenuItem(
            "🎮 OpenXR & VR Runtime",
            pystray.Menu(
                pystray.MenuItem(
                    get_xr_menu_text(
                        "virtual_desktop", "🖥️ Virtual Desktop (VDX / VDVAD 24kHz)"
                    ),
                    on_set_openxr_runtime("virtual_desktop"),
                ),
                pystray.MenuItem(
                    get_xr_menu_text("meta_link", "🔗 Meta Quest Link / AirLink"),
                    on_set_openxr_runtime("meta_link"),
                ),
                pystray.MenuItem(
                    get_xr_menu_text("steam_vr", "♨️ SteamVR / SteamXR"),
                    on_set_openxr_runtime("steam_vr"),
                ),
            ),
        ),
        pystray.MenuItem(
            "🧠 AI Provider",
            pystray.Menu(
                pystray.MenuItem(
                    get_prov_menu_text("lmstudio", "Local (LM Studio)"),
                    on_set_chat_provider("lmstudio"),
                ),
                pystray.MenuItem(
                    get_prov_menu_text("unsloth", "Local (Unsloth)"),
                    on_set_chat_provider("unsloth"),
                ),
                pystray.MenuItem(
                    get_prov_menu_text("ollama_cloud", "Ollama Cloud"),
                    on_set_chat_provider("ollama_cloud"),
                ),
                pystray.MenuItem(
                    get_prov_menu_text("gemini", "Google Gemini"),
                    on_set_chat_provider("gemini"),
                ),
                pystray.MenuItem(
                    get_prov_menu_text("openrouter", "OpenRouter"),
                    on_set_chat_provider("openrouter"),
                ),
            ),
        ),
        pystray.MenuItem(get_avatar_menu_text, on_toggle_avatar),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🌐 Open Secure WebXR UI (HTTPS)", on_open_web),
        pystray.MenuItem("📊 Open Top Bar", on_open_topbar),
        pystray.MenuItem("🎙️ Quick Controls / PTT Mode", on_open_quick_controls),
        pystray.MenuItem(
            "⚙ Settings Panel (Port 8201)",
            lambda icon, item: webbrowser.open("http://127.0.0.1:8401/settings.html"),
        ),
        pystray.MenuItem("🔍 Show Service Status", on_show_status),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("📌 Register Auto-Start", on_register),
        pystray.MenuItem("🗑 Remove Auto-Start", on_unregister),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ Exit", on_quit),
    )

    icon = pystray.Icon("LumaxTray", create_image(), "LUMAX", menu)

    # Background health monitor — updates the tooltip
    # Uses a grace period: only starts pinging after the user explicitly starts the stack,
    # or after 30 seconds of tray uptime (to avoid frantic "unreachable" messages at boot).
    def _health_monitor():
        global _stack_running, _health_monitor_active
        grace_period = 30  # seconds — don't ping at all during this window
        while True:
            elapsed = time.time() - _tray_start_time
            if elapsed < grace_period and not _health_monitor_active:
                # Grace period: only check if stack was already running when tray started
                if not _stack_running:
                    time.sleep(5)
                    continue
            if not _stack_starting:
                if _health_monitor_active or _stack_running:
                    # Use quiet check to avoid log spam when stack is intentionally stopped
                    _stack_running = is_stack_running_quiet()
                else:
                    # Stack is stopped and monitor not active — just sleep
                    time.sleep(5)
                    continue
            time.sleep(5)

    threading.Thread(target=_health_monitor, daemon=True).start()

    icon.run()


# ── Main ──

if __name__ == "__main__":
    if "--register" in sys.argv:
        register_startup()
        sys.exit(0)
    elif "--unregister" in sys.argv:
        unregister_startup()
        sys.exit(0)

    print("[LumaxTray] Starting LUMAX System Tray Icon...")
    print(f"[LumaxTray] Project root: {PROJECT_ROOT}")
    print(f"[LumaxTray] Python: {sys.executable}")

    # Check initial state — use quiet check to avoid log spam at boot
    _stack_running = is_stack_running_quiet()
    if _stack_running:
        _health_monitor_active = True  # Stack was already running, activate monitoring
    print(
        f"[LumaxTray] Initial stack state: {'Running' if _stack_running else 'Stopped'}"
    )

    create_tray_icon()
