import os

from win32com.client import Dispatch

LUMAX_DIR = r"C:\Users\danie\program\LUMAX"
SHORTCUT_DIR = os.path.join(LUMAX_DIR, "Tools", "shortcuts")
PWSH = r"C:\Program Files\PowerShell\7\pwsh.exe"
if not os.path.exists(PWSH):
    PWSH = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def make_lnk(name, target, args=None, icon=None, description=""):
    shell = Dispatch("WScript.Shell")
    path = os.path.join(SHORTCUT_DIR, f"{name}.lnk")
    shortcut = shell.CreateShortcut(path)
    shortcut.TargetPath = target
    if args:
        shortcut.Arguments = args
    shortcut.WorkingDirectory = LUMAX_DIR
    if icon:
        shortcut.IconLocation = icon
    shortcut.Description = description
    shortcut.save()
    print(f"Created: {path}")


# 1. Start LUMAX Stack — runs the real Start_Concordia.PS1 launcher in a visible terminal
make_lnk(
    "Start LUMAX Stack",
    PWSH,
    args=f"-ExecutionPolicy Bypass -NoExit -Command \"cd '{LUMAX_DIR}'; .\\Start_Concordia.PS1\"",
    description="Launch full LUMAX Concordia stack",
)

# 2. LUMAX Tray Hub
make_lnk(
    "LUMAX Tray Hub",
    os.path.join(LUMAX_DIR, "LUMAX_Taskbar.pyw"),
    description="Launch LUMAX system tray hub",
)

# 3. Super Prompt Kiosk
make_lnk(
    "Super Prompt Kiosk",
    PWSH,
    args='-NoProfile -Command "Import-Module LumaxMemory; Start-SuperKiosk"',
    description="Open the LUMAX Super Prompt Kiosk",
)

# 4. AUI Memory Dashboard
make_lnk(
    "AUI Memory Dashboard",
    PWSH,
    args='-NoProfile -Command "Import-Module LumaxMemory; Enter-AUI"',
    description="Open the LUMAX AUI Memory Dashboard",
)

# 5. LUMAX Super Memory Terminal
make_lnk(
    "LUMAX Super Memory Terminal",
    r"C:\Users\danie\AppData\Local\Microsoft\WindowsApps\wt.exe",
    args='new-tab --profile "LUMAX Super Memory" -d "C:\\Users\\danie\\program\\LUMAX"',
    description="Open LUMAX Super Memory Windows Terminal profile",
)

# 6. Settings Panel (web UI on 8201)
make_lnk(
    "LUMAX Settings Panel",
    PWSH,
    args="-NoProfile -Command \"Start-Process 'http://127.0.0.1:8401/memory/settings.html'\"",
    description="Open LUMAX web-based settings panel",
)
