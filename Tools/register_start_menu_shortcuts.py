#!/usr/bin/env python3
"""
register_start_menu_shortcuts.py — Register LUMAX Start Menu Shortcuts in Windows

Creates Start Menu shortcuts under:
C:\\Users\\<User>\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\LUMAX\\
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
VENV_PYTHONW = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHONW.exists():
    VENV_PYTHONW = Path(sys.executable).parent / "pythonw.exe"
    VENV_PYTHON = Path(sys.executable)

APPDATA = os.getenv("APPDATA", "")
START_MENU_DIR = (
    Path(APPDATA) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "LUMAX"
)

SHORTCUTS = [
    {
        "name": "LUMAX Taskbar & Tray Hub.lnk",
        "target": str(VENV_PYTHONW),
        "args": f'"{PROJECT_ROOT / "LUMAX_Taskbar.pyw"}"',
        "cwd": str(PROJECT_ROOT),
        "desc": "LUMAX System Tray Manager & Core Controller",
    },
    {
        "name": "LUMAX Corner Companion HUD.lnk",
        "target": str(VENV_PYTHON),
        "args": f'"{PROJECT_ROOT / "Tools" / "lumax_top_bar" / "lumax_top_bar.py"}" --quick-controls',
        "cwd": str(PROJECT_ROOT),
        "desc": "LUMAX Corner Companion Floating HUD App",
    },
    {
        "name": "LUMAX TopBar.lnk",
        "target": str(VENV_PYTHON),
        "args": f'"{PROJECT_ROOT / "Tools" / "lumax_top_bar" / "lumax_top_bar.py"}" --mode=topbar',
        "cwd": str(PROJECT_ROOT),
        "desc": "LUMAX Desktop TopBar Header",
    },
    {
        "name": "LUMAX Settings Panel.lnk",
        "target": "C:\\Windows\\System32\\cmd.exe",
        "args": "/c start http://127.0.0.1:8401/memory/settings.html",
        "cwd": str(PROJECT_ROOT),
        "desc": "LUMAX Web Settings Panel",
    },
    {
        "name": "LUMAX Desktop Vessel.lnk",
        "target": str(VENV_PYTHON),
        "args": f'"{PROJECT_ROOT / "Tools" / "lumax_desktop_vessel.py"}"',
        "cwd": str(PROJECT_ROOT),
        "desc": "LUMAX 3D Desktop Vessel Window",
    },
]


def create_shortcuts():
    START_MENU_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[StartMenu] Registering shortcuts in {START_MENU_DIR}...")

    for sc in SHORTCUTS:
        lnk_path = START_MENU_DIR / sc["name"]
        ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{lnk_path!s}')
$Shortcut.TargetPath = '{sc["target"]}'
$Shortcut.Arguments = '{sc["args"]}'
$Shortcut.WorkingDirectory = '{sc["cwd"]}'
$Shortcut.Description = '{sc["desc"]}'
$Shortcut.Save()
"""
        cmd = ["powershell", "-NoProfile", "-Command", ps_script]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  ✅ Created shortcut: {sc['name']}")
        else:
            print(f"  ❌ Failed to create shortcut {sc['name']}: {r.stderr}")


if __name__ == "__main__":
    create_shortcuts()
