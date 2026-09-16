#!/usr/bin/env python3
"""
FoveAI Ignition Server — Lightweight HTTP server that starts the backend stack.
Listens on port 8400/ignition (alongside the foveated-memory proxy).
When POST /ignition is received, runs sleipnir_launcher.sh --light.

Usage:
    python3 ignition_server.py &

The multigate frontend's IgnitionButton calls POST /ignition to boot the stack.
"""

import http.server
import json
import os
import subprocess
import sys
import time
from pathlib import Path

FOVEAI_DIR = Path(__file__).resolve().parent
LAUNCHER = FOVEAI_DIR / "sleipnir_launcher.sh"
LOG_FILE = FOVEAI_DIR / "ignition_backend.log"

PORT = 8409  # Dedicated ignition port (avoids conflict with foveated-memory on 8400)
HOST = "127.0.0.1"

class IgnitionHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/ignition/status":
            # Check if backend is up by probing port 8400
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            try:
                sock.connect(("127.0.0.1", 8400))
                sock.close()
                self._json_response({"status": "up", "port": 8400})
            except:
                self._json_response({"status": "down"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/ignition":
            self._start_backend()
        else:
            self.send_response(404)
            self.end_headers()

    def _start_backend(self):
        if not LAUNCHER.exists():
            self._json_response({"ok": False, "error": f"Launcher not found: {LAUNCHER}"}, 500)
            return

        try:
            # Start the backend in the background
            log_fp = open(LOG_FILE, "a")
            log_fp.write(f"\n{'='*60}\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ignition triggered\n")
            log_fp.flush()

            proc = subprocess.Popen(
                ["bash", str(LAUNCHER), "--light"],
                cwd=str(FOVEAI_DIR),
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # Detach from this process
            )

            log_fp.write(f"Started sleipnir_launcher.sh --light (PID: {proc.pid})\n")
            log_fp.close()

            self._json_response({
                "ok": True,
                "pid": proc.pid,
                "message": "Backend ignition started. Check /ignition/status in ~10s."
            })
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)}, 500)

    def _json_response(self, data, code=200):
        self.send_response(code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        # Silent logging
        pass


def main():
    print(f"[Ignition] Server starting on http://{HOST}:{PORT}")
    print(f"[Ignition] POST /ignition → starts sleipnir_launcher.sh --light")
    print(f"[Ignition] GET  /ignition/status → checks if backend is up")
    server = http.server.HTTPServer((HOST, PORT), IgnitionHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Ignition] Stopped")
        server.shutdown()


if __name__ == "__main__":
    main()
