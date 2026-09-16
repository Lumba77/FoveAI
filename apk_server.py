#!/usr/bin/env python3
"""
APK download server with Range request support.
Serves AliceVR.apk on port 8888 with resume capability.
"""
import http.server
import os
import socketserver

PORT = 8888
DIRECTORY = "/home/lumba/FoveAI/client_quest"
APK_FILE = "AliceVR.apk"

class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def send_head(self):
        # Support Range requests for large APK
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            return super().send_head()

        file_size = os.path.getsize(path)
        range_header = self.headers.get("Range")

        if range_header:
            # Parse Range: bytes=start-end
            try:
                start, end = range_header.replace("bytes=", "").split("-")
                start = int(start) if start else 0
                end = int(end) if end else file_size - 1
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return None

            if start >= file_size or end >= file_size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return None

            self.send_response(206)
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            f = open(path, "rb")
            f.seek(start)
            return f

        # Full file
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return open(path, "rb")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # Silent

if __name__ == "__main__":
    import socket
    # Allow quick restart
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), RangeRequestHandler) as httpd:
        print(f"APK server on :{PORT}, serving {DIRECTORY}/{APK_FILE}")
        httpd.serve_forever()
