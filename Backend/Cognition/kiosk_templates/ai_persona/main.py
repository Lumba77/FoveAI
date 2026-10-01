"""AI Persona — chat with a customizable persona, backed by an XRLF model.

Take it anywhere: XRLF_URL can point at any FoveAI host or any
OpenAI-compatible API; XRLF_API_KEY sets the Bearer token.
  XRLF_URL=https://openrouter.ai/api/v1 XRLF_API_KEY=sk-or-... ./ai_persona
"""

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

XRLF = os.environ.get("XRLF_URL", "http://127.0.0.1:8402").rstrip("/")
XRLF_KEY = os.environ.get("XRLF_API_KEY", "")
XRLF_MODEL = os.environ.get("XRLF_MODEL", "local")
PERSONA = "You are Nova, a witty starship navigator with a dry sense of humor."

PAGE = (
    """<!doctype html><title>AI Persona</title><style>
body{background:#120a1a;color:#f0e0ff;font-family:monospace;margin:20px}
#log{white-space:pre-wrap;border:1px solid #c0f3;padding:12px;min-height:280px}
input,textarea{width:90%;padding:8px;background:#0a0208;color:#fff;border:1px solid #c0f3}
</style><textarea id=p rows=2>"""
    + PERSONA
    + """</textarea>
<div id=log></div><input id=i placeholder="Talk to the persona…">
<script>
const log=document.getElementById('log'),i=document.getElementById('i'),p=document.getElementById('p');
i.onkeydown=async e=>{if(e.key!=='Enter')return;const q=i.value;i.value='';
log.textContent+='\\n> '+q+'\\n';
const r=await fetch('/chat',{method:'POST',
 body:JSON.stringify({q,sys:p.value})});const d=await r.json();
log.textContent+=d.reply+'\\n';};
</script>"""
)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(PAGE.encode())

    def do_POST(self):
        if self.path == "/chat":
            d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            body = json.dumps(
                {
                    "model": XRLF_MODEL,
                    "messages": [
                        {"role": "system", "content": d.get("sys", PERSONA)},
                        {"role": "user", "content": d.get("q", "")},
                    ],
                }
            ).encode()
            hdrs = {"Content-Type": "application/json"}
            if XRLF_KEY:
                hdrs["Authorization"] = f"Bearer {XRLF_KEY}"
            req = urllib.request.Request(
                XRLF + "/v1/chat/completions", data=body, headers=hdrs
            )
            try:
                reply = json.load(urllib.request.urlopen(req, timeout=120))["choices"][
                    0
                ]["message"]["content"]
            except Exception as e:
                reply = f"(model unreachable: {e})"
            out = json.dumps({"reply": reply}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("AI Persona on http://127.0.0.1:8791")
    HTTPServer(("127.0.0.1", 8791), H).serve_forever()
