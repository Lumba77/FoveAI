"""
FoveAI Corner Companion — Always-on-top mini video chat window.

Uses Chrome in --app mode for reliable rendering, then pins the
window on top via a PowerShell loop using SetWindowPos.

Usage:
    python foveai_corner_companion.py
    python foveai_corner_companion.py --url http://127.0.0.1:8401/companion.html
    python foveai_corner_companion.py --width 380 --height 520
"""

import sys
import os
import time
import argparse
import subprocess

# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_URL = os.environ.get("CORNER_COMPANION_URL", "http://127.0.0.1:8401/companion.html")
DEFAULT_WIDTH = 380
DEFAULT_HEIGHT = 520


def get_corner_position(width, height):
    """Position the window in the bottom-right corner of the primary monitor."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDpiAwareness(2)
        except AttributeError:
            try:
                user32.SetProcessDPIAware()
            except AttributeError:
                pass
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
    except Exception:
        screen_w = 1920
        screen_h = 1080
    x = screen_w - width - 12
    y = screen_h - height - 56
    return x, y


def find_browser():
    """Find Chrome or Edge executable."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def pin_window_on_top_ps(title_keyword, duration=3600):
    """Use PowerShell to find the window by title and pin it on top.
    Runs in a loop to re-pin if the window loses topmost status."""
    ps_script = f'''
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {{
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")] public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
}}
"@
$found = $null
$deadline = (Get-Date).AddSeconds(15)
while (-not $found -and (Get-Date) -lt $deadline) {{
    [Win32]::EnumWindows({{
        param($hWnd, $lParam)
        if ([Win32]::IsWindowVisible($hWnd)) {{
            $sb = New-Object System.Text.StringBuilder 256
            [Win32]::GetWindowText($hWnd, $sb, 256) | Out-Null
            $title = $sb.ToString()
            if ($title -like "*$title_keyword*") {{
                $script:found = $hWnd
                return $false
            }}
        }}
        return $true
    }}, [IntPtr]::Zero) | Out-Null
    if ($script:found) {{ $found = $script:found }}
    Start-Sleep -Milliseconds 500
}}
if ($found) {{
    $HWND_TOPMOST = [IntPtr](-1)
    $SWP_NOMOVE = 0x0002
    $SWP_NOSIZE = 0x0001
    $SWP_SHOWWINDOW = 0x0040
    # Pin on top in a loop for {duration} seconds
    $end = (Get-Date).AddSeconds({duration})
    while ((Get-Date) -lt $end) {{
        [Win32]::SetWindowPos($found, $HWND_TOPMOST, 0, 0, 0, 0, $SWP_NOMOVE -bor $SWP_NOSIZE -bor $SWP_SHOWWINDOW)
        Start-Sleep -Seconds 2
    }}
}}
'''
    return subprocess.Popen(
        ['powershell', '-NoProfile', '-Command', ps_script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )


def main():
    parser = argparse.ArgumentParser(description="FoveAI Corner Companion")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL to load")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Window width")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Window height")
    parser.add_argument("--title", default="FoveAI Companion", help="Window title")
    args = parser.parse_args()

    browser = find_browser()
    if not browser:
        print("[CornerCompanion] ERROR: No Chrome or Edge found")
        sys.exit(1)

    x, y = get_corner_position(args.width, args.height)
    print(f"[CornerCompanion] Browser: {browser}")
    print(f"[CornerCompanion] URL: {args.url}")
    print(f"[CornerCompanion] Window: {args.width}x{args.height} at ({x}, {y})")

    # Launch Chrome in app mode — borderless, positioned, sized
    cmd = [
        browser,
        f"--app={args.url}",
        f"--window-size={args.width},{args.height}",
        f"--window-position={x},{y}",
        "--disable-features=TranslateUI",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={os.environ.get('TEMP', 'C:\\\\Temp')}\\foveai_companion",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[CornerCompanion] Browser PID: {proc.pid}")

    # Launch PowerShell to pin the window on top
    print("[CornerCompanion] Launching pin-on-top helper…")
    pin_proc = pin_window_on_top_ps("FoveAI", duration=86400)

    # Wait for browser to close
    proc.wait()
    pin_proc.terminate()
    print("[CornerCompanion] Closed.")


if __name__ == "__main__":
    main()
