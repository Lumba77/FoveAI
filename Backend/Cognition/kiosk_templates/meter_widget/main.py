"""Meter Widget — live CPU/RAM gauges served as a tiny dashboard."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


def _cpu_pct():
    def snap():
        with open("/proc/stat") as f:
            p = f.readline().split()[1:]
        idle, total = int(p[3]), sum(map(int, p))
        return idle, total

    i1, t1 = snap()
    import time

    time.sleep(0.3)
    i2, t2 = snap()
    return round(100 * (1 - (i2 - i1) / max(1, t2 - t1)), 1)


def _mem_pct():
    info = {}
    with open("/proc/meminfo") as f:
        for l in f:
            k, v = l.split(":")
            info[k] = int(v.split()[0])
    return round(100 * (1 - info["MemAvailable"] / info["MemTotal"]), 1)


PAGE = """<!doctype html><title>Meter Widget</title><style>
body{background:#050a08;color:#a0ffd0;font-family:monospace;margin:30px}
.bar{width:300px;height:24px;border:1px solid #4dffa0;margin:6px 0 18px}
.fill{height:100%;background:#4dffa0;transition:width .4s}
</style>CPU<div class=bar><div id=c class=fill></div></div>
RAM<div class=bar><div id=m class=fill></div></div>
<script>
async function tick(){const d=await(await fetch('/stats')).json();
c.style.width=d.cpu+'%';m.style.width=d.mem+'%';
c.textContent=d.cpu+'%';m.textContent=d.mem+'%';}
setInterval(tick,1500);tick();
</script>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/stats":
            out = json.dumps({"cpu": _cpu_pct(), "mem": _mem_pct()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(PAGE.encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Meter Widget on http://127.0.0.1:8792")
    HTTPServer(("127.0.0.1", 8792), H).serve_forever()
