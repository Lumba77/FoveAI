"""Mini Web Browser — fetch & render pages through a local reader proxy."""

import re
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

PAGE = """<!doctype html><title>Mini Browser</title><style>
body{background:#050a12;color:#cfe8ff;font-family:monospace;margin:16px}
input{width:85%;padding:8px;background:#020508;color:#fff;border:1px solid #4da0ff}
#view{margin-top:12px;border:1px solid #4da0ff;padding:14px;white-space:pre-wrap}
a{color:#4da0ff}
</style><input id=u placeholder="https://example.com"><div id=view></div>
<script>
const u=document.getElementById('u'),v=document.getElementById('view');
u.onkeydown=async e=>{if(e.key!=='Enter')return;
 v.textContent='loading…';
 const r=await fetch('/go?u='+encodeURIComponent(u.value));
 v.innerHTML=await r.text();};
</script>"""


def fetch_text(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "MiniBrowser/1.0"})
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    html = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # make links clickable through the proxy
    html = re.sub(
        r'href="([^"]+)"', lambda m: f'href="#" onclick="load(\'{m.group(1)}\')"', html
    )
    return html


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/go?u="):
            url = unquote(self.path[6:])
            try:
                body = fetch_text(url)
            except Exception as e:
                body = f"(fetch failed: {e})"
            out = body.encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(out)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(PAGE.encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Mini Browser on http://127.0.0.1:8794")
    HTTPServer(("127.0.0.1", 8794), H).serve_forever()
