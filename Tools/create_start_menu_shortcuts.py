"""
Tools/create_start_menu_shortcuts.py — Create LUMAX Start Menu Folder & Shortcuts
Generates a dedicated Windows Start Menu folder containing one-click launchers for all LUMAX modes!
"""

import os


def create_start_menu_folder():
    """Create Windows Start Menu folder `LUMAX Sovereign Modes` with shortcode launchers."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        appdata = os.path.expanduser("~")

    start_menu_dir = os.path.join(
        appdata,
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "LUMAX Sovereign Modes",
    )
    os.makedirs(start_menu_dir, exist_ok=True)

    shortcuts = [
        ("🎧 LUMAX — Desktop Audio Only.url", "lx://audio"),
        ("🎭 LUMAX — Desktop 3D Avatar.url", "lx://avatar"),
        ("⚙️ LUMAX — Settings Panel (Port 8201).url", "lx://settings"),
        ("🥽 LUMAX — Quest 3 AR Passthrough.url", "lx://ar"),
        ("🌌 LUMAX — Quest 3 Immersive VR.url", "lx://vr"),
        ("💬 LUMAX — Text Chat Only WebUI.url", "lx://chat"),
        (
            "🌐 LUMAX — Secure WebXR Cloud (HTTPS).url",
            "https://lumax.1um6a.se/?u=q3&m=ar",
        ),
    ]

    for filename, target_url in shortcuts:
        filepath = os.path.join(start_menu_dir, filename)
        content = f"[InternetShortcut]\nURL={target_url}\nIconIndex=0\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[Start Menu] Created shortcut: {filename}")

    print(
        f"\n[Start Menu] ✅ Successfully created Start Menu folder at:\n             {start_menu_dir}"
    )
    return start_menu_dir


if __name__ == "__main__":
    create_start_menu_folder()
