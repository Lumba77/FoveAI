"""
Tools/register_lx_protocol.py — Register Windows Custom Protocol Handler `lx://`
Allows typing `lx://settings`, `lx://audio`, `lx://avatar`, `lx://ar`, `lx://vr` in Windows (Run, Browser, Shell)
"""

import os
import subprocess
import sys
import winreg

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def register_protocol():
    """Register lx:// URI scheme in Windows Registry (HKCU\\Software\\Classes\\lx)."""
    try:
        key_path = r"Software\Classes\lx"

        # Open / Create HKCU\Software\Classes\lx
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "URL:LUMAX Protocol Handler")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

        # Command key
        cmd_key_path = r"Software\Classes\lx\shell\open\command"
        py_exe = sys.executable
        handler_script = os.path.abspath(__file__)
        cmd_str = f'"{py_exe}" "{handler_script}" "%1"'

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, cmd_str)

        print(
            "[lx Protocol] ✅ Successfully registered lx:// protocol in Windows Registry!"
        )
        print(f"             Command: {cmd_str}")
        return True
    except Exception as e:
        print(f"[lx Protocol] ❌ Failed to register protocol: {e}")
        return False


def handle_uri(uri_str: str):
    """Handle invoked lx:// URI string."""
    import webbrowser

    print(f"[lx Protocol] Invoked URI: {uri_str}")

    # Strip protocol prefix
    clean = uri_str.replace("lx://", "").strip("/").lower()

    if clean == "settings" or "settings.html" in clean:
        webbrowser.open("http://127.0.0.1:8401/settings.html")
    elif clean == "audio" or clean == "voice" or clean == "ptt":
        topbar_script = os.path.join(
            PROJECT_ROOT, "Tools", "lumax_top_bar", "lumax_top_bar.py"
        )
        subprocess.Popen(
            [sys.executable, topbar_script, "--quick-controls"], cwd=PROJECT_ROOT
        )
    elif clean == "avatar" or clean == "desktop":
        vessel_script = os.path.join(PROJECT_ROOT, "Tools", "lumax_desktop_vessel.py")
        subprocess.Popen([sys.executable, vessel_script], cwd=PROJECT_ROOT)
    elif clean == "ar" or clean == "passthrough" or clean == "q3":
        webbrowser.open("https://lumax.1um6a.se/?u=q3&m=ar&passthrough=true")
    elif clean == "vr" or clean == "xr":
        webbrowser.open("https://lumax.1um6a.se/?u=q3&m=xr")
    elif clean == "chat":
        webbrowser.open("https://lumax.1um6a.se/?m=chat")
    else:
        # Fallback: pass as query params if present
        if clean.startswith("open?"):
            query = clean.replace("open?", "")
            webbrowser.open(f"https://lumax.1um6a.se/?{query}")
        else:
            webbrowser.open("https://lumax.1um6a.se/")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Invoked by Windows Protocol
        handle_uri(sys.argv[1])
    else:
        # Installer mode
        register_protocol()
