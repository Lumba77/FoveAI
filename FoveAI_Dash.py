#!/usr/bin/env python3
"""FoveAI_Dash.py — FoveAI Desktop App (pywebview).

Replaces the legacy GTK3 Dash with a full pywebview wrapper of the Multigate React app.
This brings ALL core FoveAI web and app features (XR avatars, audio, chat, settings)
natively into the desktop environment.
"""

import sys
import threading
import time
import urllib.request
import webview

MULTIGATE_URL = "http://127.0.0.1:5177"

def wait_for_server():
    """Wait for the Multigate server to be available before showing the window."""
    retries = 30
    for i in range(retries):
        try:
            req = urllib.request.Request(MULTIGATE_URL, method='HEAD')
            urllib.request.urlopen(req, timeout=1.0)
            return True
        except Exception:
            time.sleep(1)
    return False

def main():
    # We can create the window immediately, but it might show a connection error if Vite is still starting.
    # Creating it with a loading string or pointing to URL directly:
    
    # We enable transparent background, frameless if we want, but standard window is fine for now
    window = webview.create_window(
        title='FoveAI Studio',
        url=MULTIGATE_URL,
        width=1280,
        height=800,
        min_size=(800, 600),
        background_color='#0a0a0a',
        text_select=True,
        confirm_close=True
    )
    
    webview.start(private_mode=False, debug=True)

if __name__ == '__main__':
    main()
