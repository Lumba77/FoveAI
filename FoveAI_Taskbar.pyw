import pystray
from PIL import Image, ImageDraw, ImageFont
import subprocess
import os
import requests
import sys
import threading
import time
from pathlib import Path

# ─── Single-Instance Socket Lock (Takeover & Clean Bind) ───────────
import socket
import time

_lock_socket = None

def _get_process_on_port(port):
    """Find process ID listening on specified local port."""
    try:
        import subprocess
        cmd = f"powershell -NoProfile -Command \"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess\""
        out = subprocess.check_output(cmd, shell=True, text=True).strip()
        pids = [int(p) for p in out.splitlines() if p.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None

def _bind_lock_socket():
    global _lock_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', 48409))
        s.listen(1)
        _lock_socket = s
        return True
    except socket.error:
        try:
            s.close()
        except Exception:
            pass

        # Check if takeover is requested or if stale pythonw process exists
        pid = _get_process_on_port(48409)
        if pid and pid != os.getpid():
            should_takeover = "--takeover" in sys.argv or "--force" in sys.argv or "--restart" in sys.argv or "--tray" in sys.argv
            if not should_takeover:
                # If launching from shortcut or command line without specific flags, check if PID is stale pythonw
                try:
                    import subprocess
                    proc_info = subprocess.check_output(f"powershell -NoProfile -Command \"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).ProcessName\"", shell=True, text=True).strip()
                    if "python" in proc_info.lower():
                        should_takeover = True
                except Exception:
                    should_takeover = True

            if should_takeover:
                try:
                    import signal
                    os.kill(pid, 9)
                    time.sleep(0.4)
                except Exception:
                    pass
                s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s2.bind(('127.0.0.1', 48409))
                    s2.listen(1)
                    _lock_socket = s2
                    return True
                except Exception:
                    pass

        return False

if not _bind_lock_socket():
    # Tray app is already running in background and responsive.
    # Opening another instance launches Settings Panel as a convenience.
    try:
        url = "http://127.0.0.1:8414/memory/settings.html"
        edge_candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        edge_exe = next((c for c in edge_candidates if os.path.exists(c)), "msedge.exe")
        subprocess.Popen([edge_exe, f"--app={url}", "--window-size=1280,850"], creationflags=0x08000000)
    except Exception:
        pass
    sys.exit(0)

# Add directory to sys.path so runtime and core modules import reliably
FOVEAI_DIR = os.path.dirname(os.path.abspath(__file__))
LUMAX_DIR = os.path.dirname(FOVEAI_DIR)
if FOVEAI_DIR not in sys.path:
    sys.path.insert(0, FOVEAI_DIR)

from runtime.vram_guard import VRAMGuardrail
from runtime.rig_guard import RigGuard

rig_guard = RigGuard(cooldown_seconds=600)

# ─── VENV PYTHON ───────────────────────────────────────────────────
# Always use the repo venv Python, never system Python.
VENV_PYTHON = os.path.join(FOVEAI_DIR, ".venv", "Scripts", "python.exe")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = os.path.join(FOVEAI_DIR, "venv", "Scripts", "python.exe")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable

def _find_pwsh():
    """Return the best available PowerShell 7+ executable, fallback to Windows PowerShell."""
    candidates = [
        r"C:\Program Files\PowerShell\7\pwsh.exe",
        r"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    try:
        result = subprocess.run(["where", "pwsh"], capture_output=True, text=True, check=True, timeout=5)
        first = result.stdout.strip().splitlines()[0]
        if first and os.path.exists(first):
            return first
    except Exception:
        pass
    return "powershell.exe"

PWSH = _find_pwsh()
WT_EXE = r"C:\Users\danie\AppData\Local\Microsoft\WindowsApps\wt.exe"
DEBUG = "--debug" in sys.argv or "-debug" in sys.argv

stack_process = None

# ─── Icons ─────────────────────────────────────────────────────────
ASSET_ICON_PNG = os.path.join(FOVEAI_DIR, "assets", "Icon_small.png")
_base_icon_art = None
if os.path.exists(ASSET_ICON_PNG):
    try:
        _base_icon_art = Image.open(ASSET_ICON_PNG).convert("RGBA").resize((48, 48), Image.Resampling.LANCZOS)
    except Exception:
        _base_icon_art = None

def create_icon_image(color, symbol=None):
    image = Image.new('RGBA', (64, 64), (15, 23, 42, 255))
    draw = ImageDraw.Draw(image)
    
    # Outer bold status border (5px thick) - unmistakable even at 16x16
    draw.rectangle((0, 0, 63, 63), outline=color, width=5)
    
    if _base_icon_art:
        # Center the user's custom icon art
        image.paste(_base_icon_art, (12, 6), _base_icon_art)
        # Bold bottom status accent bar (12px height) - punchy at all DPI scalings
        draw.rectangle((0, 52, 63, 63), fill=color)
        # Dynamic colored status orb in bottom-right
        draw.ellipse((38, 34, 58, 54), fill=color, outline=(15, 23, 42, 255), width=2)
    elif symbol:
        try:
            font = ImageFont.truetype("segoeui.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), symbol, font=font)
        x = (64 - (bbox[2] - bbox[0])) // 2
        y = (64 - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), symbol, font=font, fill=color)
    return image

ICON_RED = create_icon_image('#ef4444', '◆')      # Vibrant Crimson Red
ICON_GREEN = create_icon_image('#10b981', '◆')    # Vibrant Emerald Green
ICON_ORANGE = create_icon_image('#f59e0b', '◆')   # Vibrant Amber Orange
ICON_BLUE = create_icon_image('#0284c7', '◆')     # Vibrant Azure Blue

# ─── Helpers ───────────────────────────────────────────────────────
def notify(icon, message, title="FoveAI"):
    if icon:
        try:
            icon.notify(message, title)
        except Exception:
            pass

def run_ps(command, hidden=True, timeout=30, cwd=FOVEAI_DIR):
    creation = 0x08000000 if hidden else 0
    return subprocess.run(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=cwd, creationflags=creation, timeout=timeout,
        capture_output=True, text=True
    )

def run_cmd(command, hidden=True, timeout=30, cwd=FOVEAI_DIR):
    creation = 0x08000000 if hidden else 0
    return subprocess.run(
        ["cmd", "/c", command],
        cwd=cwd, creationflags=creation, timeout=timeout,
        capture_output=True, text=True
    )

def open_url(url):
    subprocess.run([PWSH, "-NoProfile", "-Command", f"Start-Process '{url}'"], creationflags=0x08000000)

def read_env():
    env_path = os.path.join(FOVEAI_DIR, ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(LUMAX_DIR, ".env")
    values = {}
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

def set_env_key(key, value):
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
        # Ensure the last line has a newline before appending
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

# ─── Stack Control ─────────────────────────────────────────────────
def start_stack(icon, item):
    """Start the full FoveAI Concordia stack via sleipnir_launcher.js.
    Uses the FoveAI-local sleipnir (with XRLF legacy gating), NOT the root one."""
    global stack_process
    notify(icon, "Igniting FoveAI Concordia Stack...", "FoveAI Stack")
    # Prefer FoveAI-local sleipnir (has XRLF_LEGACY_SERVICES gating);
    # fall back to root sleipnir if the FoveAI copy doesn't exist.
    sleipnir_path = os.path.join(FOVEAI_DIR, "sleipnir_launcher.js")
    sleipnir_cwd = FOVEAI_DIR
    if not os.path.exists(sleipnir_path):
        sleipnir_path = os.path.join(LUMAX_DIR, "sleipnir_launcher.js")
        sleipnir_cwd = LUMAX_DIR
    if os.path.exists(sleipnir_path):
        stack_process = subprocess.Popen(
            ["node", sleipnir_path],
            cwd=sleipnir_cwd,
            creationflags=0x08000000
        )
        notify(icon, "FoveAI Stack running in background.\nProxy :8400, Dashboard :8414, XRLF Runtime :8414, WS IPC :8414, MM WS :8300", "FoveAI Stack")
        icon.icon = ICON_GREEN
    else:
        # Fallback to starting memory proxy
        fm_dir = os.path.join(FOVEAI_DIR, "foveated-memory")
        subprocess.Popen(["node", "server.js"], cwd=fm_dir, creationflags=0x08000000)
        notify(icon, "Proxy starting on :8400...", "FoveAI Stack")

    def _refresh():
        time.sleep(2.0)
        try:
            icon.menu = build_menu()
            icon.update_menu()
        except Exception:
            pass
    threading.Thread(target=_refresh, daemon=True).start()

def stop_stack(icon, item):
    """Stop the full FoveAI stack: kill sleipnir, run_xrlf, python backend, and node servers."""
    global stack_process
    notify(icon, "Stopping FoveAI Stack...", "FoveAI Stack")
    if stack_process:
        try:
            stack_process.terminate()
        except Exception:
            pass
        stack_process = None

    # Kill sleipnir, run_xrlf, and llama-server
    run_ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_xrlf*' -or $_.CommandLine -like '*sleipnir_launcher*' -or $_.ProcessName -eq 'llama-server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }", hidden=True)

    # Cleanly terminate listeners on FoveAI ports: 8400, 8414, 8402, 8403, 8300, 8004, 8109, 8110, 8113
    for port in [8400, 8414, 8402, 8403, 8300, 8004, 8109, 8110, 8113]:
        try:
            netstat = subprocess.check_output("netstat -ano -p tcp", creationflags=0x08000000).decode(errors="ignore")
            for line in netstat.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5 and parts[-1].strip().isdigit():
                        subprocess.run(["taskkill", "/F", "/PID", parts[-1].strip()], creationflags=0x08000000)
        except Exception:
            pass
    icon.icon = ICON_RED
    notify(icon, "FoveAI Stack stopped", "FoveAI Stack")

    def _refresh():
        time.sleep(1.0)
        try:
            icon.menu = build_menu()
            icon.update_menu()
        except Exception:
            pass
    threading.Thread(target=_refresh, daemon=True).start()

# ─── Fovea / Model ─────────────────────────────────────────────────

FOVEA_LEVELS = {
    0: "Auto",
    1: "Minimal",
    2: "Light",
    3: "Moderate",
    4: "Aggressive",
    5: "Maximum",
    6: "Off"
}

def set_fovea(icon, item, level):
    label = FOVEA_LEVELS.get(level, f"Level {level}")
    notify(icon, f"Setting foveation to {label}...", "FoveAI Fovea")
    try:
        set_env_key("XRLF_PROXY_AGGRESSION", level)
        notify(icon, f"Foveation set to {label}. Restarting Proxy...", "FoveAI Fovea")
        import threading
        threading.Thread(target=restart_memory_proxy_service, args=(icon, item), daemon=True).start()
    except Exception as e:
        notify(icon, f"Foveation failed: {e}", "FoveAI Fovea")

# ─── Voice / Mic / TTS ─────────────────────────────────────────────
def set_env_toggle(icon, item, name, value):
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

def switch_tts_provider(icon, item, provider):
    notify(icon, f"Switching TTS Engine to {provider}...", "FoveAI Voice")
    try:
        set_env_key("XRLF_TTS_PROVIDER", provider)
        set_env_key("FoveAI_TTS_PROVIDER", provider)
        notify(icon, f"TTS Engine set to {provider}", "FoveAI Voice")
        refresh_taskbar_menu(icon)
    except Exception as e:
        notify(icon, f"TTS switch failed: {e}", "FoveAI Voice")

def switch_stt_provider(icon, item, provider):
    notify(icon, f"Switching STT Engine to {provider}...", "FoveAI Voice")
    try:
        set_env_key("XRLF_STT_PROVIDER", provider)
        set_env_key("FoveAI_STT_PROVIDER", provider)
        notify(icon, f"STT Engine set to {provider}", "FoveAI Voice")
        refresh_taskbar_menu(icon)
    except Exception as e:
        notify(icon, f"STT switch failed: {e}", "FoveAI Voice")

def switch_to_local(icon, item):
    notify(icon, "Switching to local inference...", "FoveAI Cognitive Mode")
    try:
        set_env_key("FoveAI_COGNITIVE_MODE", "local")
        set_env_key("XRLF_COGNITIVE_MODE", "local")
        set_env_key("LUMAX_COGNITIVE_MODE", "local")
        set_env_key("XRLF_RUNTIME_MODE", "local")
        set_env_key("LUMAX_CHAT_PROVIDER", "xrlf_runtime")
        set_env_key("FoveAI_CHAT_PROVIDER", "xrlf_runtime")
        notify(icon, "Switched to local mode", "FoveAI Cognitive Mode")
        refresh_taskbar_menu(icon)
    except Exception as e:
        notify(icon, f"Switch failed: {e}", "FoveAI Cognitive Mode")

def switch_to_cloud(icon, item):
    notify(icon, "Switching to cloud inference...", "FoveAI Cognitive Mode")
    try:
        set_env_key("FoveAI_COGNITIVE_MODE", "cloud")
        set_env_key("XRLF_COGNITIVE_MODE", "cloud")
        set_env_key("LUMAX_COGNITIVE_MODE", "cloud")
        set_env_key("XRLF_RUNTIME_MODE", "cloud")
        set_env_key("LUMAX_CHAT_PROVIDER", "ollama_cloud")
        set_env_key("FoveAI_CHAT_PROVIDER", "ollama_cloud")
        notify(icon, "Switched to cloud mode", "FoveAI Cognitive Mode")
        refresh_taskbar_menu(icon)
    except Exception as e:
        notify(icon, f"Switch failed: {e}", "FoveAI Cognitive Mode")

def unload_models(icon, item):
    notify(icon, "Unloading active models & freeing VRAM...", "FoveAI VRAM")
    try:
        # Kill XRLF runtime processes (run_xrlf.py spawns llama-server internally)
        run_ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_xrlf*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }", hidden=True)
        # Also kill any standalone llama-server.exe
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], creationflags=0x08000000)
        g = VRAMGuardrail()
        for f in g.lock_dir.glob("*.lock"):
            try: f.unlink(missing_ok=True)
            except: pass
        notify(icon, "Local model slots released", "FoveAI VRAM")
    except Exception as e:
        notify(icon, f"Unload failed: {e}", "FoveAI VRAM")

# ─── Memory Tools ──────────────────────────────────────────────────
def start_super_kiosk(icon, item):
    open_url("http://127.0.0.1:8414/memory/prompt-kiosk.html")
    notify(icon, "Opening Super Prompt Kiosk", "FoveAI Memory")

def enter_aui(icon, item):
    open_url("http://127.0.0.1:8414/memory")
    notify(icon, "Opening AUI Memory Dashboard", "FoveAI Memory")

def start_foveai_super_terminal(icon, item):
    notify(icon, "Launching FoveAI Super Memory terminal...", "FoveAI Terminal")
    if os.path.exists(WT_EXE):
        subprocess.run([WT_EXE, "new-tab", "--profile", "LUMAX Super Memory", "-d", LUMAX_DIR], creationflags=0x08000000)
    else:
        run_ps("Import-Module LumaxMemory; Show-MemoryMeter", hidden=False)

def open_debug_terminal(icon, item):
    notify(icon, "Opening FoveAI Debug Log Terminal...", "FoveAI Debug")
    if os.path.exists(WT_EXE):
        subprocess.run([
            WT_EXE, "new-tab", "--profile", "LUMAX Debug Log", "-d", LUMAX_DIR,
            "--title", "FoveAI Debug"
        ], creationflags=0x08000000)
    else:
        subprocess.Popen([PWSH, "-NoExit", "-WorkingDirectory", LUMAX_DIR, "-Command", "Import-Module LumaxMemory -Force; Show-LumaxDebugLog"], creationflags=0)

def open_settings_panel(icon=None, item=None):
    url = "http://127.0.0.1:8414/memory/settings.html"
    try:
        # Open as dedicated standalone desktop app window (no browser tabs/address bar)
        edge_candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        edge_exe = next((c for c in edge_candidates if os.path.exists(c)), "msedge.exe")
        subprocess.Popen([edge_exe, f"--app={url}", "--window-size=1280,850"], creationflags=0x08000000)
        notify(icon, "Opening Desktop Settings App Window", "FoveAI Settings")
    except Exception:
        open_url(url)
        notify(icon, "Opening Settings Panel", "FoveAI Settings")

def register_memory_proxy_service(icon, item):
    notify(icon, "Registering Foveated Memory Proxy as startup task...", "FoveAI Service")
    fm_dir = os.path.join(FOVEAI_DIR, "foveated-memory")
    server_path = os.path.join(fm_dir, "server.js")
    cmd = f'schtasks /create /tn "FoveAI_Foveated_Memory" /tr "node \\"{server_path}\\"" /sc onlogon /f'
    r = run_cmd(cmd)
    if r.returncode == 0:
        notify(icon, "Memory Proxy registered to start at logon", "FoveAI Service")
    else:
        notify(icon, f"Registration failed: {r.stderr[:80]}", "FoveAI Service")

def deregister_memory_proxy_service(icon, item):
    notify(icon, "Deregistering Foveated Memory Proxy startup task...", "FoveAI Service")
    cmd = 'schtasks /delete /tn "FoveAI_Foveated_Memory" /f'
    r = run_cmd(cmd)
    if r.returncode == 0:
        notify(icon, "Memory Proxy startup task removed", "FoveAI Service")
    else:
        notify(icon, f"Deregistration failed: {r.stderr[:80]}", "FoveAI Service")

def is_memory_proxy_running():
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8400/health", headers={"User-Agent": "FoveAI-Tray/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:8414/api/status", headers={"User-Agent": "FoveAI-Tray/1.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

def start_memory_proxy_service(icon, item):
    if is_memory_proxy_running():
        notify(icon, "Memory Proxy is already running (:8400)", "FoveAI Service")
        return
    notify(icon, "Starting Foveated Memory Proxy...", "FoveAI Service")
    fm_dir = os.path.join(FOVEAI_DIR, "foveated-memory")
    subprocess.Popen(["node", "server.js"], cwd=fm_dir, creationflags=0x08000000)
    # Wait briefly for the service to come up, then refresh the menu
    for _ in range(12):
        time.sleep(0.5)
        if is_memory_proxy_running():
            icon.icon = ICON_GREEN
            notify(icon, "Memory Proxy is online (:8400)", "FoveAI Service")
            try:
                icon.update_menu()
            except Exception:
                pass
            return
    notify(icon, "Memory Proxy startup timed out", "FoveAI Service")
    try:
        icon.update_menu()
    except Exception:
        pass

def stop_memory_proxy_service(icon, item):
    if not is_memory_proxy_running():
        notify(icon, "Memory Proxy is not running", "FoveAI Service")
        return
    notify(icon, "Stopping Foveated Memory Proxy service...", "FoveAI Service")
    run_cmd('schtasks /end /tn "FoveAI_Foveated_Memory"')
    for port in [8400, 8414]:
        try:
            netstat = subprocess.check_output("netstat -ano -p tcp", creationflags=0x08000000).decode(errors='ignore')
            for line in netstat.splitlines():
                if f":{port}" not in line:
                    continue
                if "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1].strip()
                        if pid.isdigit():
                            subprocess.run(["taskkill", "/F", "/PID", pid], creationflags=0x08000000)
        except Exception:
            pass
    notify(icon, "Memory Proxy service stopped", "FoveAI Service")
    try:
        icon.update_menu()
    except Exception:
        pass

def restart_memory_proxy_service(icon, item):
    notify(icon, "Restarting Foveated Memory Proxy...", "FoveAI Service")
    icon.icon = ICON_ORANGE
    # Stop
    if is_memory_proxy_running():
        run_cmd('schtasks /end /tn "FoveAI_Foveated_Memory"')
        for port in [8400, 8414]:
            try:
                netstat = subprocess.check_output("netstat -ano -p tcp", creationflags=0x08000000).decode(errors='ignore')
                for line in netstat.splitlines():
                    if f":{port}" not in line:
                        continue
                    if "LISTENING" in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            pid = parts[-1].strip()
                            if pid.isdigit():
                                subprocess.run(["taskkill", "/F", "/PID", pid], creationflags=0x08000000)
            except Exception:
                pass
    # Wait for ports to release
    time.sleep(1.5)
    # Start
    fm_dir = os.path.join(LUMAX_DIR, "FoveAI", "foveated-memory")
    subprocess.Popen(["node", "server.js"], cwd=fm_dir, creationflags=0x08000000)
    # Wait for it to come up
    for _ in range(15):
        time.sleep(0.5)
        if is_memory_proxy_running():
            icon.icon = ICON_GREEN
            notify(icon, "Memory Proxy restarted successfully", "FoveAI Service")
            try:
                icon.update_menu()
            except Exception:
                pass
            return
    icon.icon = ICON_RED
    notify(icon, "Memory Proxy restart timed out", "FoveAI Service")
    try:
        icon.update_menu()
    except Exception:
        pass



# ─── Pfoveai XRLF Omni Router (Port 8300) ─────────────────────────────
# RETIRED: Port 8300 is no longer used. The proxy on port 8400 now uses
# LM Studio (port 7272) directly as its backend for both completions and
# summarization. This block is kept for reference only.


# ─── Spatial Machine (FoveAI Unified Core) ────────────────────────────
SPATIAL_MACHINE_DIR = FOVEAI_DIR
SPATIAL_MACHINE_PORT = 8000 # Soul Core Port
spatial_machine_process = None

def is_spatial_machine_running():
    """True if the unified Spatial Machine (Soul Core) is running."""
    return check_port_listener(SPATIAL_MACHINE_PORT)

def _kill_spatial_machine_port():
    """Force kill processes on Soul Core (8000) and Web UI (8080)."""
    for port in [8000, 8080]:
        try:
            netstat = subprocess.check_output(
                "netstat -ano -p tcp", creationflags=0x08000000
            ).decode(errors="ignore")
            for line in netstat.splitlines():
                if f":{port}" not in line:
                    continue
                if "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1].strip()
                        if pid.isdigit():
                            subprocess.run(
                                ["taskkill", "/F", "/PID", pid],
                                creationflags=0x08000000,
                            )
        except Exception:
            pass

def start_spatial_machine(icon, item):
    global spatial_machine_process
    if is_spatial_machine_running():
        notify(icon, "Spatial Machine is already running", "Spatial Machine")
        return
    notify(icon, "Starting Spatial Machine (Soul Core & Web UI)...", "Spatial Machine")
    icon.icon = ICON_ORANGE
    _kill_spatial_machine_port()
    time.sleep(0.5)

    # Launch the unified Spatial Machine powershell script
    ps1_path = os.path.join(LUMAX_DIR, "Scripts", "start_spatial_machine.ps1")
    run_ps(f"& '{ps1_path}'", hidden=False, timeout=5)

    # Wait for Soul Core to bind to 8000
    for _ in range(20):
        time.sleep(0.5)
        if is_spatial_machine_running():
            icon.icon = ICON_GREEN
            notify(icon, "Spatial Machine is online", "Spatial Machine")
            try:
                icon.update_menu()
            except Exception:
                pass
            return
    icon.icon = ICON_RED
    notify(icon, "Spatial Machine start timed out", "Spatial Machine")
    try:
        icon.update_menu()
    except Exception:
        pass

def stop_spatial_machine(icon, item):
    notify(icon, "Stopping Spatial Machine (Soul Core & Web UI)...", "Spatial Machine")
    icon.icon = ICON_ORANGE
    _kill_spatial_machine_port()
    time.sleep(0.5)
    icon.icon = ICON_RED
    notify(icon, "Spatial Machine stopped", "Spatial Machine")
    try:
        icon.update_menu()
    except Exception:
        pass

def restart_spatial_machine(icon, item):
    notify(icon, "Restarting Spatial Machine...", "Spatial Machine")
    stop_spatial_machine(icon, item)
    time.sleep(1.0)
    start_spatial_machine(icon, item)

def open_spatial_machine_settings(icon, item):
    """Toggle the in-scene settings panel via WebSocket 'settings.toggle' event.

    The settings panel renders inside the Unity Quest 3 scene as a world-space
    canvas — the Meta Quest 3 system keyboard is used for text input.
    Falls back to opening the HTML overlay in a desktop browser if the backend
    is unreachable (desktop webapp mode).
    """
    import json as _json
    import urllib.request as _urllib
    try:
        payload = _json.dumps({"event": "settings.toggle", "payload": {}}).encode("utf-8")
        req = _urllib.request.Request(
            f"http://127.0.0.1:{SPATIAL_MACHINE_PORT}/settings/toggle",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _urllib.request.urlopen(req, timeout=3)
        notify(icon, "Settings panel toggled in Quest 3 scene", "Spatial Machine")
    except Exception:
        url = f"file:///{SPATIAL_MACHINE_DIR}/Frontend/multigate/settings_overlay.html".replace("\\", "/")
        open_url(url)
        notify(icon, "Opening Spatial Machine Settings (Desktop Fallback)", "Spatial Machine")

def launch_spatial_machine_portal(icon, item):
    notify(icon, "Launching Spatial Machine Web Portal...", "Spatial Machine")
    subprocess.Popen(
        ["cmd.exe", "/c", "npm run dev -- --open"],
        cwd=os.path.join(SPATIAL_MACHINE_DIR, "Frontend", "multigate"),
        creationflags=0x08000000,
    )

def switch_frontend(icon, item, ui_type):
    if ui_type == "3d_avatar":
        label = "3D Avatar Chatbot"
    elif ui_type == "multigate":
        label = "Multigate Portal"
    else:
        label = "XR Vessel"
    notify(icon, f"Switching frontend to {label}...", "FoveAI Frontend")
    try:
        set_env_key("XRLF_FRONTEND_UI_PRESET", ui_type)
        set_env_key("LUMAX_FRONTEND_UI", ui_type)
        import urllib.request
        import json
        req = urllib.request.Request("http://127.0.0.1:8400/api/setting", data=json.dumps({"key": "XRLF_FRONTEND_UI_PRESET", "val": ui_type}).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=5)
        notify(icon, f"Frontend set to {label}. Tunnel + stack updated.", "FoveAI Frontend")
        refresh_taskbar_menu(icon)
    except Exception as e:
        notify(icon, f"Frontend switch failed: {str(e)}", "FoveAI Frontend")

def is_autostart_registered():
    """Check if FoveAI Tray is registered in HKCU Run key."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, "FoveAITray")
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False

def toggle_autostart(icon, item=None):
    """Toggle auto-start of FoveAI Tray on Windows user logon."""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
        if is_autostart_registered():
            try:
                winreg.DeleteValue(key, "FoveAITray")
                notify(icon, "Removed FoveAI Tray from Windows startup", "Auto-Start")
            except Exception:
                pass
        else:
            pythonw = os.path.join(FOVEAI_DIR, ".venv", "Scripts", "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable.replace("python.exe", "pythonw.exe")
            target = f'"{pythonw}" "{os.path.join(FOVEAI_DIR, "FoveAI_Taskbar.pyw")}"'
            winreg.SetValueEx(key, "FoveAITray", 0, winreg.REG_SZ, target)
            notify(icon, "Registered FoveAI Tray to start automatically at logon!", "Auto-Start")
        winreg.CloseKey(key)
        refresh_taskbar_menu(icon)
    except Exception as e:
        notify(icon, f"Auto-start toggle failed: {e}", "Auto-Start Error")

def on_quit(icon, item):
    notify(icon, "Closing Tray App (Services & Proxy remain running)", "FoveAI Hub")
    icon.stop()

def restart_stack(icon, item):
    notify(icon, "Restarting FoveAI Stack...", "FoveAI Stack")
    stop_stack(icon, item)
    time.sleep(2.0)
    start_stack(icon, item)

def ensure_memory_proxy_running():
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8400/health", timeout=1)
    except Exception:
        fm_dir = os.path.join(FOVEAI_DIR, "foveated-memory")
        subprocess.Popen(["node", "server.js"], cwd=fm_dir, creationflags=0x08000000)

def launch_corner_companion(icon, item):
    ensure_memory_proxy_running()
    notify(icon, "Launching Corner Companion HUD...", "FoveAI HUD")
    subprocess.Popen([VENV_PYTHON, os.path.join(FOVEAI_DIR, "Tools", "lumax_top_bar", "lumax_top_bar.py"), "--quick-controls"], cwd=FOVEAI_DIR)

def launch_topbar(icon, item):
    ensure_memory_proxy_running()
    notify(icon, "Launching FoveAI TopBar...", "FoveAI TopBar")
    subprocess.Popen(
        [VENV_PYTHON, os.path.join(FOVEAI_DIR, "Tools", "lumax_top_bar", "lumax_top_bar.py"), "--mode=topbar"],
        cwd=FOVEAI_DIR
    )

def launch_desktop_vessel(icon, item):
    ensure_memory_proxy_running()
    notify(icon, "Launching Native 3D Desktop Vessel...", "FoveAI Desktop Vessel")
    subprocess.Popen(
        [VENV_PYTHON, os.path.join(FOVEAI_DIR, "Tools", "lumax_desktop_vessel.py")],
        cwd=FOVEAI_DIR
    )

def start_light_voice_stack(icon, item):
    """Start light stack: proxy + XRLF runtime with voice hooks. No separate TTS/STT services."""
    notify(icon, "Starting Light Voice Stack (Proxy + XRLF Runtime)...", "FoveAI Light Mode")
    try:
        fm_dir = os.path.join(FOVEAI_DIR, "foveated-memory")
        # 1. Start proxy
        if not is_memory_proxy_running():
            subprocess.Popen(["node", "server.js"], cwd=fm_dir, creationflags=0x08000000)
        # 2. Wait for proxy
        for _ in range(15):
            if is_memory_proxy_running():
                break
            time.sleep(0.5)
        # 3. Start XRLF runtime via proxy (handles STT/TTS/vision via hooks)
        import json as _json, urllib.request as _urllib
        payload = _json.dumps({"action": "start-xrlf-runtime"}).encode()
        req = _urllib.Request("http://127.0.0.1:8400/api/control", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with _urllib.urlopen(req, timeout=30) as resp:
            _json.loads(resp.read())
        time.sleep(1.0)
        launch_corner_companion(icon, item)
        icon.icon = ICON_GREEN
        notify(icon, "Light Voice Stack running\nProxy :8411, Runtime :8411", "FoveAI Light Mode")
    except Exception as e:
        notify(icon, f"Light Stack launch failed: {e}", "FoveAI Error")

def register_shortcuts(icon, item):
    subprocess.Popen(
        [VENV_PYTHON, os.path.join(LUMAX_DIR, "Tools", "register_start_menu_shortcuts.py")],
        cwd=LUMAX_DIR
    )
    notify(icon, "Windows Start Menu shortcuts registered!", "FoveAI Setup")

def restart_tray_app(icon, item):
    notify(icon, "Restarting FoveAI Taskbar Tray App...", "FoveAI Tray")
    subprocess.Popen(
        [VENV_PYTHON, os.path.abspath(__file__)],
        cwd=LUMAX_DIR,
        creationflags=0x08000000
    )
    icon.stop()

def check_port_listener(port):
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False



def is_stack_running():
    """True if the XRLF stack (proxy + runtime) is running."""
    return is_memory_proxy_running() and check_port_listener(8402)

def get_service_status(port, path=None):
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return 'inactive', '[○ INACTIVE]'
    except Exception:
        return 'inactive', '[○ INACTIVE]'

    if path:
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"User-Agent": "FoveAI-Tray/1.0"})
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status in (200, 204, 302):
                    return 'active', '[● ACTIVE]'
                return 'dormant', '[◐ DORMANT]'
        except Exception:
            return 'dormant', '[◐ DORMANT]'

    return 'active', '[● ACTIVE]'

# ─── Inference Engine (XRLF / Llama Server) ───────────────────────
def stop_llama_server(icon, item):
    notify(icon, "Stopping XRLF Runtime / Llama Server to free VRAM...", "Inference Engine")
    try:
        # Kill XRLF runtime processes (run_xrlf.py contains the llama-server)
        run_ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_xrlf*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }", hidden=True)
        # Also kill any standalone llama-server.exe
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], creationflags=0x08000000)
        g = VRAMGuardrail()
        for f in g.lock_dir.glob("*.lock"):
            try: f.unlink(missing_ok=True)
            except: pass
    except: pass

# ─── Model Selector & Smart CPU Offloader ───────────────────────────
PERSONA_MODELS = {
    "gemma_e2b_xrlf": {
        "name": "Gemma 4 E2B MTP (gemma-4-e2b-multimodal-v1.0.xrlf - Default Persona)",
        "id": "gemma-4-e2b-multimodal-v1.0.xrlf",
        "file": "gemma-4-e2b-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf",
        "size_gb": 3.3,
        "total_layers": 30,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "Default Persona: 2B XRLF bundle with native vision+audio, fast-loading embedded MTP draft."
    },
    "gemma_12b_xrlf": {
        "name": "Gemma 4 12B MTP (gemma-4-12b-mtp-xrlf-3.0.xrlf)",
        "id": "gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "file": "gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "size_gb": 5.1,
        "total_layers": 42,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "Heavy 12B XRLF bundle: native STT, vision, foveated memory, draft model."
    },
    "qwen_4b_multimodal": {
        "name": "Qwen 3.5 4B MTP (qwen3.5-4b-mtp-multimodal-v1.0.xrlf)",
        "id": "qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "file": "qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "size_gb": 2.9,
        "total_layers": 36,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "4B Qwen MTP XRLF coder with vision (mmproj), Whisper STT hook, Kokoro TTS hook."
    },
    "smolvlm2_500m_xrlf": {
        "name": "SmolVLM2 500M (smolvlm2-500m-multimodal-v1.0.xrlf)",
        "id": "smolvlm2-500m-multimodal-v1.0.xrlf",
        "file": "smolvlm2-500m-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/smolvlm2-500m-multimodal-v1.0.xrlf",
        "size_gb": 0.5,
        "total_layers": 24,
        "multimodal": True,
        "is_xrlf": True,
        "detail": "500M vision+video XRLF model with Whisper STT hook, Kokoro TTS hook."
    },
    "qwen_9b_xrlf": {
        "name": "Qwen 3.5 9B MoQ (qwen3.5-9b-moq.xrlf)",
        "id": "qwen3.5-9b-moq.xrlf",
        "file": "qwen3.5-9b-moq.xrlf",
        "xrlf_path": "../Training/outputs/qwen3.5-9b-moq.xrlf",
        "size_gb": 4.0,
        "total_layers": 36,
        "multimodal": False,
        "is_xrlf": True,
        "detail": "9B Qwen XRLF model with MoQ quantization. Text-only."
    }
}

ROUTER_MODELS = {
    "foveai_omni_router_v2": {
        "name": "FoveAI Omni Router v2 (foveai-omni-router-v2.xrlf)",
        "id": "foveai-omni-router-v2.xrlf",
        "file": "foveai-omni-router-v2.xrlf",
        "xrlf_path": "foveai-omni-router-v2.xrlf",
        "size_gb": 1.4,
        "total_layers": 28,
        "multimodal": False,
        "is_xrlf": True,
        "detail": "Default XRLF router model for fast intention classification and context routing."
    },
    "slim_summary": {
        "name": "Slim Summary Tiny Tool (tiny-summary.gguf)",
        "id": "slim-summary-tiny-tool",
        "file": "tiny-summary.gguf",
        "path": r"C:/Users/danie/.cache/huggingface/hub/llmware/slim-summary-tiny-tool/tiny-summary.gguf",
        "size_gb": 0.2,
        "total_layers": 16,
        "multimodal": False,
        "is_xrlf": False,
        "detail": "Ultra-lightweight 0.2GB summary model running purely on CPU."
    }
}

def select_persona_model(icon, item, model_key):
    m = PERSONA_MODELS.get(model_key)
    if not m:
        return

    xrlf_model = m.get("xrlf_path") or m.get("path")
    if not xrlf_model:
        notify(icon, f"Model {m['name']} is missing an xrlf_path.", "XRLF Model Loader Error")
        return

    try:
        set_env_key("XRLF_MODEL_LOCAL_ID", m['id'])
        set_env_key("LUMAX_MODEL_ACTIVE_ID", m['id'])
        set_env_key("FOVEAI_MAIN_MODEL", m['id'])
    except Exception:
        pass
    
    notify(icon, f"🚀 Launching Persona AI: {m['name']}...\nLoading {m['size_gb']:.1f}GB model...", "Persona AI Loader")

    import json as _json
    import urllib.request as _urllib
    try:
        payload = _json.dumps({
            "action": "start-xrlf",
            "model": xrlf_model,
            "port": 8402,
            "ws_port": 8403
        }).encode()
        req = _urllib.Request(
            "http://127.0.0.1:8400/api/control",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        proxy_handler = _urllib.ProxyHandler({})
        opener = _urllib.build_opener(proxy_handler)
        with opener.open(req, timeout=120) as resp:
            _json.loads(resp.read())
            mm_note = " 🎤 Native STT + 👁 Vision" if m.get("multimodal") else ""
            notify(icon, f"✅ Persona AI set to {m['name']}{mm_note}\nXRLF runtime on :8402", "Persona AI Loader")
    except Exception as e:
        notify(icon, f"Persona AI launch failed: {e}", "Persona AI Loader Error")

    def refresh():
        time.sleep(0.5)
        try:
            icon.menu = build_menu()
            icon.update_menu()
        except Exception:
            pass
    threading.Thread(target=refresh, daemon=True).start()

def select_router_model(icon, item, model_key):
    m = ROUTER_MODELS.get(model_key)
    if not m:
        return

    try:
        set_env_key("FOVEAI_OMNI_ROUTER_MODEL", m['id'])
        set_env_key("XRLF_ROUTER_MODEL", m['id'])
        import json as _json, urllib.request as _urllib
        req = _urllib.request.Request(
            "http://127.0.0.1:8400/api/setting",
            data=_json.dumps({"key": "FOVEAI_OMNI_ROUTER_MODEL", "val": m['id']}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        _urllib.request.urlopen(req, timeout=3)
        notify(icon, f"✅ Default Router set to {m['name']}", "XRLF Router Loader")
    except Exception as e:
        notify(icon, f"Router set to {m['name']} (.env updated)", "XRLF Router Loader")

    def refresh():
        time.sleep(0.5)
        try:
            icon.menu = build_menu()
            icon.update_menu()
        except Exception:
            pass
    threading.Thread(target=refresh, daemon=True).start()


    def refresh():
        time.sleep(0.5)
        try:
            icon.menu = build_menu()
            icon.update_menu()
        except Exception:
            pass
    threading.Thread(target=refresh, daemon=True).start()

# ─── Sensible Guardian & Hardware Telemetry ─────────────────────────
def get_hardware_telemetry():
    """Query physical free VRAM and compute color-coded health status."""
    try:
        g = VRAMGuardrail()
        free_gb = g.get_realtime_free_vram_gb()
        total_gb = 8.0
        used_gb = max(0.0, total_gb - free_gb)
    except Exception:
        total_gb, used_gb, free_gb = 8.0, 1.0, 7.0

    # 🟢 Green: Safe (< 4.5 GB used, plentiful headroom)
    # 🔵 Blue: Inference/Proxy Active (4.5 - 6.0 GB used)
    # 🟠 Orange: Guardrail Warning (6.0 - 7.0 GB used) - Clamping layers
    # 🔴 Red: Critical (> 7.0 GB used)
    if used_gb < 4.5:
        color = ICON_GREEN
        status_text = f"🟢 Healthy | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"
    elif used_gb < 6.0:
        color = ICON_BLUE
        status_text = f"🔵 Active | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"
    elif used_gb < 7.0:
        color = ICON_ORANGE
        status_text = f"🟠 Protected | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"
    else:
        color = ICON_RED
        status_text = f"🔴 Critical | VRAM {used_gb:.1f}/{total_gb:.0f}GB ({free_gb:.1f}GB Free)"

    return total_gb, used_gb, free_gb, color, status_text

def flush_vram(icon, item=None):
    notify(icon, "Liberating VRAM & flushing model caches...", "FoveAI Guardian")
    try:
        import gc
        gc.collect()
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], creationflags=0x08000000)
        g = VRAMGuardrail()
        for f in g.lock_dir.glob("*.lock"):
            try: f.unlink(missing_ok=True)
            except: pass
    except Exception:
        pass
    notify(icon, "VRAM liberated successfully.", "FoveAI Guardian")

# ─── Rig & Bloat Guardian Actions ──────────────────────────────────
def refresh_taskbar_menu(icon):
    def _refresh():
        time.sleep(0.3)
        try:
            icon.menu = build_menu()
            icon.update_menu()
        except Exception:
            pass
    threading.Thread(target=_refresh, daemon=True).start()

def kill_runaway_git_action(icon, item=None):
    notify(icon, "Scanning for stuck git processes...", "Rig Guardian")
    cnt, freed_mb, msg = rig_guard.kill_runaway_git_processes()
    notify(icon, msg, "Rig Guardian")
    refresh_taskbar_menu(icon)

def safe_language_server_guide_action(icon, item=None):
    guide = rig_guard.get_language_server_guidance()
    notify(icon, guide["message"], guide["title"])

def clean_unity_temp_action(icon, item=None):
    notify(icon, "Cleaning Unity temp and checking zombie workers...", "Rig Guardian")
    k_cnt, k_msg = rig_guard.kill_zombie_unity_workers()
    c_ok, c_msg = rig_guard.clean_unity_temp()
    notify(icon, f"{k_msg}\n{c_msg}", "Rig Guardian")
    refresh_taskbar_menu(icon)

def fix_workspace_ignores_action(icon, item=None):
    notify(icon, "Verifying and injecting workspace ignore protections...", "Rig Guardian")
    ok, msg = rig_guard.fix_workspace_ignores()
    notify(icon, msg, "Rig Guardian")
    refresh_taskbar_menu(icon)

def inspect_ram_consumers_action(icon, item=None):
    top = rig_guard.get_top_ram_consumers(5)
    lines = [f"• {p['name']} (PID {p['id']}): {p['ram_mb']} MB" for p in top]
    notify(icon, "\n".join(lines) if lines else "No process data found.", "Top RAM Consumers")

# ─── Consented Context & Uptodate-ness Collector ─────────────────────
def is_context_collector_enabled():
    env = read_env()
    return env.get("FOVEAI_CONTEXT_CONSENT", "false").lower() == "true"

def toggle_context_collector(icon, item=None):
    new_val = "false" if is_context_collector_enabled() else "true"
    set_env_toggle(icon, item, "FOVEAI_CONTEXT_CONSENT", new_val)
    state_str = "Enabled (Consented)" if new_val == "true" else "Disabled"
    notify(icon, f"Workspace Context Collector: {state_str}", "FoveAI Context")
    if new_val == "true":
        threading.Thread(target=collect_workspace_context, daemon=True).start()

def collect_workspace_context():
    """Gathers git branch, last commit, and modified files to keep uptodate.md & context.md fresh."""
    if not is_context_collector_enabled():
        return
    try:
        r_branch = run_ps("git rev-parse --abbrev-ref HEAD", hidden=True, cwd=FOVEAI_DIR)
        branch = r_branch.stdout.strip() if r_branch.returncode == 0 else "main"

        r_log = run_ps("git log -1 --format='%h - %s (%cr)'", hidden=True, cwd=FOVEAI_DIR)
        last_commit = r_log.stdout.strip() if r_log.returncode == 0 else "N/A"

        r_status = run_ps("git status --short", hidden=True, cwd=FOVEAI_DIR)
        modified_files = [line.strip() for line in r_status.stdout.strip().splitlines() if line.strip()] if r_status.returncode == 0 else []

        # Push to Port 8400 memory proxy if running
        try:
            payload = {
                "workspace": "default",
                "milestone": f"Git: {branch} | Last: {last_commit} | Changes: {len(modified_files)} files",
                "source": "FoveAI_Taskbar_ContextCollector"
            }
            requests.post("http://127.0.0.1:8400/api/ingest", json=payload, timeout=2)
        except Exception:
            pass
    except Exception:
        pass

# ─── Menu ──────────────────────────────────────────────────────────
def build_menu():
    env = read_env()
    current_ui = env.get("XRLF_FRONTEND_UI_PRESET", env.get("XRLF_FRONTEND_UI", env.get("FoveAI_FRONTEND_UI", "3d_avatar"))).lower()
    current_fovea = int(env.get("XRLF_PROXY_AGGRESSION", env.get("FoveAI_PROXY_AGGRESSION", "0")) or "0")
    voice_enabled = env.get("XRLF_VOICE_ENABLED", env.get("FoveAI_VOICE_ENABLED", "")).lower() == "true"
    mic_enabled = env.get("XRLF_MIC_ENABLED", env.get("FoveAI_MIC_ENABLED", "")).lower() == "true"
    tts_provider = env.get("XRLF_TTS_PROVIDER", env.get("FoveAI_TTS_PROVIDER", "qwen")).lower()
    stt_provider = env.get("XRLF_STT_PROVIDER", env.get("FoveAI_STT_PROVIDER", "whisper")).lower()
    cognitive_mode = env.get("FoveAI_COGNITIVE_MODE", env.get("XRLF_COGNITIVE_MODE", "local")).lower()
    proxy_running = is_memory_proxy_running()

    def checked(label, cond):
        return f"✅ {label}" if cond else label

    # Check live ports & states (Concordia 8400+ architecture)
    st_proxy, tag_proxy  = get_service_status(8400, "/health")
    _, tag_dash          = get_service_status(8414, "/api/status")
    st_xrlf, tag_xrlf    = get_service_status(8402, "/v1/models")
    _, tag_ws            = get_service_status(8403, "/health")
    st_soul, tag_soul    = get_service_status(8404, "/health")
    _, tag_stt           = get_service_status(8405)
    _, tag_tts           = get_service_status(8411, "/health")
    _, tag_star          = get_service_status(8413)
    _, tag_motor         = get_service_status(8412)
    _, tag_solver        = get_service_status(8401)
    _, tag_ui5176        = get_service_status(5176)

    stack_running = st_proxy == 'active' and st_xrlf == 'active'
    proxy_running = st_proxy == 'active'
    spatial_running = False

    # Spatial Machine dynamic menu items
    spatial_items = []
    if spatial_running:
        spatial_items.append(pystray.MenuItem("⏹ Stop Spatial Machine", stop_spatial_machine))
        spatial_items.append(pystray.MenuItem("🔄 Restart Spatial Machine", restart_spatial_machine))
    else:
        spatial_items.append(pystray.MenuItem("▶ Start Spatial Machine (XRLF 3.0)", start_spatial_machine))
    spatial_items.append(pystray.MenuItem("🌐 Launch Web Portal (Multigate)", launch_spatial_machine_portal))

    def show_status_info(icon, item):
        notify(icon, f"{item.text}", "FoveAI Process Status")


    # ── Model Selectors: Persona AI & Default Router ─────────────────
    curr_persona_id = env.get("LUMAX_MODEL_ACTIVE_ID", env.get("XRLF_MODEL_LOCAL_ID", env.get("FOVEAI_MAIN_MODEL", "gemma-4-e2b-multimodal-v1.0.xrlf")))
    curr_router_id = env.get("FOVEAI_OMNI_ROUTER_MODEL", env.get("XRLF_ROUTER_MODEL", "foveai-omni-router-v2.xrlf"))
    
    vg = VRAMGuardrail()
    persona_menu_items = []
    for mk, mv in PERSONA_MODELS.items():
        is_sel = mv["id"] == curr_persona_id
        prefix = "✅ " if is_sel else "  "
        mm_tag = " 🎤👁" if mv.get("multimodal") else ""
        xrlf_tag = " [XRLF Bundle]" if mv.get("is_xrlf", True) else " [GGUF]"
        try:
            model_path = mv.get("path", mv.get("xrlf_path", ""))
            offload = vg.calculate_smart_offload(model_path, total_layers=mv.get("total_layers", 33))
            lbl = f"{prefix}{mv['name']}{mm_tag}{xrlf_tag} [{offload['gpu_layers']}/{mv.get('total_layers', 33)} GPU | {offload['cpu_layers']} CPU]"
        except Exception:
            lbl = f"{prefix}{mv['name']}{mm_tag}{xrlf_tag} [{mv['size_gb']:.1f}GB]"
        persona_menu_items.append(pystray.MenuItem(lbl, (lambda k: lambda icon, item: select_persona_model(icon, item, k))(mk)))
    
    persona_menu_items.append(pystray.Menu.SEPARATOR)
    persona_menu_items.append(pystray.MenuItem("🧹 Unload Model & Free VRAM", unload_models))

    router_menu_items = []
    for rk, rv in ROUTER_MODELS.items():
        is_sel = rv["id"] == curr_router_id
        prefix = "✅ " if is_sel else "  "
        xrlf_tag = " [XRLF Bundle]" if rv.get("is_xrlf", True) else " [GGUF]"
        lbl = f"{prefix}{rv['name']}{xrlf_tag} [{rv['size_gb']:.1f}GB]"
        router_menu_items.append(pystray.MenuItem(lbl, (lambda k: lambda icon, item: select_router_model(icon, item, k))(rk)))

    # ── Dynamic service menu items ──────────────────────────────────
    stack_items = []
    if stack_running:
        stack_items.append(pystray.MenuItem("⏹ Stop FoveAI Stack", stop_stack))
        stack_items.append(pystray.MenuItem("🔄 Restart FoveAI Stack", restart_stack))
    else:
        stack_items.append(pystray.MenuItem("🚀 Start Full FoveAI Stack", start_stack))



    proxy_items = []
    if proxy_running:
        proxy_items.append(pystray.MenuItem("⏹ Stop Memory Proxy", stop_memory_proxy_service))
        proxy_items.append(pystray.MenuItem("🔄 Restart Memory Proxy", restart_memory_proxy_service))
    else:
        proxy_items.append(pystray.MenuItem("▶ Start Memory Proxy", start_memory_proxy_service))
    proxy_items.append(pystray.MenuItem("Register Auto-Start (Logon)", register_memory_proxy_service))
    proxy_items.append(pystray.MenuItem("Deregister Auto-Start", deregister_memory_proxy_service))



    bench_items = []
    _, _, _, _, status_text = get_hardware_telemetry()

    # ── Rig & Bloat Guardian Submenu ─────────────────────────────────
    ls_st = rig_guard.get_language_server_status()
    u_st = rig_guard.get_unity_status()
    ram_st = rig_guard.get_system_ram()
    ig_st = rig_guard.check_workspace_ignores()

    rig_menu_items = [
        pystray.MenuItem(ls_st.get("status_text", "Language Server"), show_status_info),
        pystray.MenuItem(u_st.get("status_text", "Unity Engine"), show_status_info),
        pystray.MenuItem(f"RAM: {ram_st.get('used_gb', 0)}/{ram_st.get('total_gb', 0)} GB ({ram_st.get('percent', 0)}%)", show_status_info),
        pystray.MenuItem(ig_st.get("status_text", "Workspace Ignores"), show_status_info),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🛠️ Enforce Workspace Ignores & Search Cap", fix_workspace_ignores_action),
        pystray.MenuItem("🧹 Kill Runaway Git Tasks (Reclaim RAM)", kill_runaway_git_action),
        pystray.MenuItem("🧹 Clean Unity Temp & Kill Zombie Workers", clean_unity_temp_action),
        pystray.MenuItem("📊 Inspect Top RAM Consumers", inspect_ram_consumers_action),
        pystray.MenuItem("ℹ️ Safe Language Server Reload Guide", safe_language_server_guide_action),
    ]

    return pystray.Menu(
        pystray.MenuItem(f"🛡️ Guardian: {status_text}", show_status_info),
        pystray.MenuItem("🛡️ Rig & Bloat Guardian", pystray.Menu(*rig_menu_items)),
        pystray.MenuItem("🧹 Liberate VRAM & Flush Caches", flush_vram),
        pystray.MenuItem("🤖 Default Persona AI Model (Main AI)", pystray.Menu(*persona_menu_items)),
        pystray.MenuItem("🔀 Default Router Model (Intention & Compression)", pystray.Menu(*router_menu_items)),
        pystray.MenuItem(checked("🧠 Context & Intuition Collector (Consented)", is_context_collector_enabled()), toggle_context_collector),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🎙️ Start Light Voice Stack (No Web UI)", start_light_voice_stack),
        *stack_items,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("⚡ Live Process Monitor", pystray.Menu(
            pystray.MenuItem(f"{tag_proxy} Foveated Memory Proxy (:8400)", show_status_info),
            pystray.MenuItem(f"{tag_dash} Settings & Memory Dashboard (:8414)", show_status_info),
            pystray.MenuItem(f"{tag_xrlf} XRLF Runtime (:8402)", show_status_info),
            pystray.MenuItem(f"{tag_ws} Multimodal WebSocket IPC (:8403)", show_status_info),
            pystray.MenuItem(f"{tag_soul} Sovereign Core Soul (:8404)", show_status_info),
            pystray.MenuItem(f"{tag_stt} Ears Speech-to-Text (:8405)", show_status_info),
            pystray.MenuItem(f"{tag_tts} Kokoro Emotional Mouth (:8411)", show_status_info),
            pystray.MenuItem(f"{tag_star} Stardust Vector Gnists (:8413)", show_status_info),
            pystray.MenuItem(f"{tag_motor} Motor Cortex (:8412)", show_status_info),
            pystray.MenuItem(f"{tag_solver} FoveAI Core Solver (:8401)", show_status_info),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"{tag_ui5176} WebXR Vessel UI (:5176)", show_status_info),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🧪 Benchmark Comparison Proxy", pystray.Menu(*bench_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🎙️ Corner Companion HUD (Bottom-Right)", launch_corner_companion),
        pystray.MenuItem("🖼️ Native 3D Desktop Vessel (WebView2)", launch_desktop_vessel),
        pystray.MenuItem("📊 Desktop TopBar (Top Edge)", launch_topbar),
        pystray.MenuItem("⚙️ Open Settings Panel", open_settings_panel),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Memory Tools", pystray.Menu(
            pystray.MenuItem("Super Prompt Kiosk", start_super_kiosk),
            pystray.MenuItem("AUI Memory Dashboard", enter_aui),
            pystray.MenuItem("FoveAI Super Memory Terminal", start_foveai_super_terminal),
        )),
        pystray.MenuItem("Memory Proxy Service (Port 8400)", pystray.Menu(*proxy_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Antigravity CLI Proxy", pystray.Menu(
            pystray.MenuItem(checked("Use Foveated Memory Proxy (:8400)", os.path.exists(r"C:\Users\danie\.gemini\antigravity-cli\settings.json") and "apiBaseUrl" in open(r"C:\Users\danie\.gemini\antigravity-cli\settings.json", "r", encoding="utf-8", errors="ignore").read()),
                             lambda icon, item: run_ps(f"& '{LUMAX_DIR}\\.agents\\skills\\manage-agy-config\\scripts\\switch-to-proxy.ps1'", hidden=True)),
            pystray.MenuItem(checked("Direct Google Cloud (Bypass Proxy)", not (os.path.exists(r"C:\Users\danie\.gemini\antigravity-cli\settings.json") and "apiBaseUrl" in open(r"C:\Users\danie\.gemini\antigravity-cli\settings.json", "r", encoding="utf-8", errors="ignore").read())),
                             lambda icon, item: run_ps(f"& '{LUMAX_DIR}\\.agents\\skills\\manage-agy-config\\scripts\\restore-agy-config.ps1'", hidden=True)),
        )),
        pystray.MenuItem("Select Frontend UI", pystray.Menu(
            pystray.MenuItem(checked("3D Avatar Chatbot (Port 8080)", current_ui == "3d_avatar"),
                             lambda icon, item: switch_frontend(icon, item, "3d_avatar")),
            pystray.MenuItem(checked("XR Vessel (Port 5176)", current_ui == "xr_vessel"),
                             lambda icon, item: switch_frontend(icon, item, "xr_vessel")),
            pystray.MenuItem(checked("Multigate Portal (Port 5177 / Dist)", current_ui == "multigate"),
                             lambda icon, item: switch_frontend(icon, item, "multigate")),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Foveation", pystray.Menu(
            *[pystray.MenuItem(checked(FOVEA_LEVELS[lvl], current_fovea == lvl),
                               (lambda l: lambda icon, item: set_fovea(icon, item, l))(lvl))
              for lvl in sorted(FOVEA_LEVELS.keys())]
        )),
        pystray.MenuItem("Voice", pystray.Menu(
            pystray.MenuItem(checked("Voice Output ON", voice_enabled), voice_on),
            pystray.MenuItem(checked("Voice Output OFF", not voice_enabled), voice_off),
            pystray.MenuItem(checked("Microphone ON", mic_enabled), mic_on),
            pystray.MenuItem(checked("Microphone OFF", not mic_enabled), mic_off),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("TTS Engine / Provider", pystray.Menu(
                pystray.MenuItem(checked("Real-Time WebSocket IPC (ws://127.0.0.1:8403/ws)", tts_provider == "websocket"),
                                 lambda icon, item: switch_tts_provider(icon, item, "websocket")),
                pystray.MenuItem(checked("Kokoro Emotional Mouth (Port 8411 / Native XRLF :8411)", tts_provider in ["qwen", "kokoro"]),
                                 lambda icon, item: switch_tts_provider(icon, item, "kokoro")),
                pystray.MenuItem(checked("Edge-TTS (Cloud Neural — Fast)", tts_provider == "edgetts"),
                                 lambda icon, item: switch_tts_provider(icon, item, "edgetts")),
            )),
            pystray.MenuItem("STT Engine / Provider", pystray.Menu(
                pystray.MenuItem(checked("Faster-Whisper Ears (Port 8401 / WebSocket IPC :8401)", stt_provider == "whisper"),
                                 lambda icon, item: switch_stt_provider(icon, item, "whisper")),
                pystray.MenuItem(checked("Web Speech API / Browser VAD", stt_provider == "browser"),
                                 lambda icon, item: switch_stt_provider(icon, item, "browser")),
            )),
        )),
        pystray.MenuItem("Cognitive Mode", pystray.Menu(
            pystray.MenuItem(checked("Local", cognitive_mode == "local"), switch_to_local),
            pystray.MenuItem(checked("Cloud", cognitive_mode == "cloud"), switch_to_cloud),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(checked("Auto-Start Tray at Windows Logon", is_autostart_registered()), toggle_autostart),
        pystray.MenuItem("📌 Register Start Menu Shortcuts", register_shortcuts),
        pystray.MenuItem("🐛 Open Debug Terminal", open_debug_terminal),
        pystray.MenuItem("Stop Llama Server (Free VRAM)", stop_llama_server),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔄 Restart Taskbar Tray App", restart_tray_app),
        pystray.MenuItem("Quit", on_quit)
    )

# ─── App ───────────────────────────────────────────────────────────
_, _, _, _initial_color, _initial_status = get_hardware_telemetry()
app = pystray.Icon("FoveAI", _initial_color, f"FoveAI Guardian | {_initial_status}", menu=build_menu())

app.default_action = open_settings_panel

_last_context_collect = 0

# ─── Auto-Start Stack on Boot ───────────────────────────────────────
def auto_start_stack():
    """Start the FoveAI stack automatically when the tray app launches at boot.
    Gated by XRLF_AUTO_START_STACK in .env (defaults to true).
    Waits a few seconds for network + GPU to settle before launching sleipnir."""
    env = read_env()
    auto_start = env.get("XRLF_AUTO_START_STACK", "true").lower().strip()
    if auto_start not in ("true", "1", "yes"):
        return
    # Give the system time to settle after boot (network, GPU driver, etc.)
    time.sleep(8)
    # Don't start if stack is already running
    if is_memory_proxy_running():
        return
    sleipnir_path = os.path.join(FOVEAI_DIR, "sleipnir_launcher.js")
    sleipnir_cwd = FOVEAI_DIR
    if not os.path.exists(sleipnir_path):
        sleipnir_path = os.path.join(LUMAX_DIR, "sleipnir_launcher.js")
        sleipnir_cwd = LUMAX_DIR
    if os.path.exists(sleipnir_path):
        notify(app, "Auto-starting FoveAI Stack...", "FoveAI Boot")
        global stack_process
        stack_process = subprocess.Popen(
            ["node", sleipnir_path],
            cwd=sleipnir_cwd,
            creationflags=0x08000000
        )
        notify(app, "FoveAI Stack auto-started.\nProxy :8400, Dashboard :8414, XRLF :8414, WS IPC :8414", "FoveAI Boot")
        try:
            app.icon = ICON_GREEN
            app.update_menu()
        except Exception:
            pass

threading.Thread(target=auto_start_stack, daemon=True).start()

def menu_refresh_loop():
    global _last_context_collect
    while True:
        try:
            total_gb, used_gb, free_gb, color, status_text = get_hardware_telemetry()
            if app.icon != color:
                app.icon = color
            app.title = f"FoveAI Guardian | {status_text}"
            app.menu = build_menu()

            # Periodic context collection if consented (every 60s)
            now = time.time()
            if is_context_collector_enabled() and (now - _last_context_collect > 60):
                _last_context_collect = now
                collect_workspace_context()

            # Periodic rig & bloat audit (throttled internally by cooldown)
            rig_guard.audit_and_alert(lambda msg, title: notify(app, msg, title))
        except Exception:
            pass
        time.sleep(5)

threading.Thread(target=menu_refresh_loop, daemon=True).start()

if __name__ == "__main__":
    app.run()





