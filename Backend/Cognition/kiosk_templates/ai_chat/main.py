"""AI Chat — talks to an XRLF model (OpenAI-compatible).

Take it anywhere: XRLF_URL can point at any FoveAI host or any
OpenAI-compatible API (OpenRouter, Ollama Cloud…). Set XRLF_API_KEY
for endpoints that need a Bearer token.
  XRLF_URL=https://openrouter.ai/api/v1 XRLF_API_KEY=sk-or-... XRLF_MODEL=deepseek/deepseek-chat-v3.1:free ./ai_chat
"""

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

XRLF = os.environ.get("XRLF_URL", "http://127.0.0.1:8402").rstrip("/")
XRLF_KEY = os.environ.get("XRLF_API_KEY", "")
XRLF_MODEL = os.environ.get("XRLF_MODEL", "local")

PAGE = """<!doctype html><title>AI Chat</title><style>
body{background:#0a0f1a;color:#e0faff;font-family:monospace;margin:20px}
#log{white-space:pre-wrap;border:1px solid #0ff3;padding:12px;min-height:300px}
input{width:80%;padding:8px;background:#020508;color:#fff;border:1px solid #0ff3}
</style><div id=log></div><input id=i placeholder="Say something…">
<script>
const log=document.getElementById('log'),i=document.getElementById('i');
i.onkeydown=async e=>{if(e.key!=='Enter')return;const q=i.value;i.value='';
log.textContent+='\\n> '+q+'\\n';
const r=await fetch('/chat',{method:'POST',body:q});const d=await r.json();
log.textContent+=d.reply+'\\n';};
</script>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(PAGE.encode())

    def do_POST(self):
        if self.path == "/chat":
            q = self.rfile.read(int(self.headers["Content-Length"])).decode()
            body = json.dumps(
                {"model": XRLF_MODEL, "messages": [{"role": "user", "content": q}]}
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
    print("AI Chat on http://127.0.0.1:8790")
    HTTPServer(("127.0.0.1", 8790), H).serve_forever()
