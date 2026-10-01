#!/usr/bin/env python3
"""
LUMAX Native Desktop Vessel — 3D Avatar & Interactive Companion Window.
Embeds Jen's 3D VRM avatar, PTT, Voice, and direct conversation into a frameless,
native Windows WebView2 Desktop Vessel (Bottom-Right corner or Transparent Pop-Out).
"""

import os

import webview

LUMAX_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class DesktopVesselAPI:
    def __init__(self, window):
        self._window = window

    def toggle_frameless(self):
        """Toggle frameless / transparent pop-out mode."""


import urllib.request


def resolve_target_url() -> str:
    """Find active 3D Avatar Vessel endpoint (5176, 8000, 8080, or Cloudflare Tunnel)."""
    candidates = [
        "http://127.0.0.1:5176",  # WebXR Vessel Frontend (Vite)
        "http://127.0.0.1:8000",  # Sovereign Core / Soul API
        "http://127.0.0.1:8080",  # Legacy proxy port
        "https://lumax.1um6a.se",  # Secure Cloudflare Tunnel
    ]
    for url in candidates:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status in (200, 301, 302, 304, 404):
                    print(f"[DesktopVessel] Found active Avatar server at: {url}")
                    return url
        except Exception:
            continue
    print("[DesktopVessel] Using default WebXR endpoint: http://127.0.0.1:5176")
    return "http://127.0.0.1:5176"


def main():
    target_url = resolve_target_url()

    # Position in bottom-right corner of primary screen
    w, h = 380, 560

    window = webview.create_window(
        title="LUMAX Desktop Vessel — Jen",
        url=target_url,
        width=w,
        height=h,
        resizable=True,
        frameless=False,
        easy_drag=True,
        on_top=True,
        background_color="#090c12",
    )

    # Enable native WebView2
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
