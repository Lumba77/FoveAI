import os
import threading

import pystray
from ghost_brain import GhostBrain
from PIL import Image, ImageDraw


def create_image():
    # Create a simple generic 64x64 Ghost icon for the system tray
    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    dc = ImageDraw.Draw(image)
    # Draw a cyan ghost shape
    dc.pieslice([16, 16, 48, 48], 180, 0, fill=(0, 243, 255))
    dc.rectangle([16, 32, 48, 56], fill=(0, 243, 255))
    # Eyes
    dc.ellipse([24, 24, 28, 28], fill=(0, 0, 0))
    dc.ellipse([36, 24, 40, 28], fill=(0, 0, 0))
    return image


listening_active = True
proxy_active = True


def toggle_listener(icon, item):
    global listening_active, brain
    listening_active = not listening_active
    if brain:
        brain.is_muted = not listening_active
    icon.update_menu()


def toggle_proxy(icon, item):
    global proxy_active
    proxy_active = not proxy_active
    import subprocess

    if proxy_active:
        script = os.path.join(
            FoveAI_ROOT,
            ".agents",
            "skills",
            "manage-agy-config",
            "scripts",
            "switch-to-proxy.ps1",
        )
        subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script],
            capture_output=True,
        )
    else:
        script = os.path.join(
            FoveAI_ROOT,
            ".agents",
            "skills",
            "manage-agy-config",
            "scripts",
            "restore-agy-config.ps1",
        )
        subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script],
            capture_output=True,
        )
    icon.update_menu()


def get_status_text(item):
    state = "Active" if listening_active else "Muted"
    proxy_state = "Proxy" if proxy_active else "Direct"
    return f"Status: {state} | {proxy_state}"


def get_toggle_text(item):
    return (
        "Disable Passive Listening" if listening_active else "Enable Passive Listening"
    )


def get_proxy_toggle_text(item):
    return (
        "Switch Antigravity to Direct (Bypass Proxy)"
        if proxy_active
        else "Switch Antigravity to Proxy (:8400)"
    )


def start_tray():
    global brain, brain_thread
    brain = GhostBrain()

    # Run the listener in a background thread
    brain_thread = threading.Thread(target=brain.start_listening, daemon=True)
    brain_thread.start()

    menu = pystray.Menu(
        pystray.MenuItem(get_status_text, lambda: None, enabled=False),
        pystray.MenuItem(get_toggle_text, toggle_listener),
        pystray.MenuItem(get_proxy_toggle_text, toggle_proxy),
        pystray.MenuItem("Exit", on_quit),
    )

    icon = pystray.Icon("LumaxGhost", create_image(), "Lumax Ghost", menu)
    icon.run()


if __name__ == "__main__":
    start_tray()
