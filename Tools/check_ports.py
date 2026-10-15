#!/usr/bin/env python3
"""
check_ports.py — find hardcoded and dead ports before they break the app.

The recurring failure was never the code: it was references to services that
weren't running. A hardcoded `127.0.0.1:8402` is fine until that service is
disabled by the model cycle, and then it silently breaks a page.

This linter answers three questions, per reference:
  1. Is the port live right now?
  2. Is it the *right* service for that port (per the cognitive port series)?
  3. Should this be a same-origin path instead of an absolute port?

Usage:
    python3 Tools/check_ports.py                    # scan everything
    python3 Tools/check_ports.py --live             # only currently-dead refs
    python3 Tools/check_ports.py Frontend/multigate # one subtree
Exit: 0 clean (or only same-origin suggestions), 1 if a dead reference exists.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── the cognitive port series (mirror of AGENTS.md / server_config.py)
PORT_TRUTH = {
    8400: "gateway  foveated proxy + resonant influx",
    8401: "hearing  Whisper STT",
    8402: "vision   XRLF vision runtime",
    8403: "touch    unified WS (chat/tts/stt/memory/telepathy/theme)",
    8404: "memory   sense-memory WS bridge",
    8405: "soul     persona/DNA",
    8406: "dormant  router-dreamer Qwen0.5B (CPU)",
    8407: "waking   Gemma E2B",
    8408: "interactive Qwopus 9B + Eagle3",
    8409: "deep     subconscious",
    8410: "hands    motor/body",
    8411: "voice    Kokoro TTS",
    8412: "create   dreamscape creative",
    8413: "relay    chat relay",
    8414: "eyes     dashboard",
    8415: "skin     theme engine",
    8416: "spark    ignition gate",
    5176: "vessel   XR Vessel (vite)",
    5177: "webui    Multigate (vite)",
}

# services that are OFF by design (cycle law) — referencing them is not a bug,
# but it must degrade gracefully rather than throw.
OPTIONAL = {8402, 8403, 8407, 8409, 8410}

SCAN_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".html", ".sh"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".SafeSaves", ".SafeSave", "backups", "Library", "client_quest", ".cache"}
SKIP_FILES = {"uptodate.md", "context.md", "repo-principia.md", "principia.md",
              "AGENTS.md", "check_ports.py"}

ABS_RE = re.compile(r"(?:127\.0\.0\.1|localhost):(\d{4,5})\b")
WS_RE = re.compile(r"ws://(?:127\.0\.0\.1|localhost):(\d{4,5})\b")
# same-origin paths that should be preferred in browser code
PREFER_SAME_ORIGIN = {
    8400: "/api", 8405: "/api/soul", 8411: "/api/kokoro", 8414: "/",
    8415: "/api/themes", 8413: "/api/relay",
}


def live_ports() -> set[int]:
    out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
    found = set()
    for m in re.finditer(r":(\d{4,5})\s", out):
        found.add(int(m.group(1)))
    return found


def tcp_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def scan(subtrees: list[str]) -> list[dict]:
    live = live_ports()
    findings: list[dict] = []
    targets = []
    for sub in subtrees:
        p = ROOT / sub
        if p.is_file():
            targets.append(p)
        elif p.is_dir():
            for dirpath, dirnames, filenames in __import__("os").walk(p):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fn in filenames:
                    if Path(fn).suffix.lower() in SCAN_EXT and fn not in SKIP_FILES:
                        targets.append(Path(dirpath) / fn)
    for f in targets:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "127.0.0.1:" not in text and "localhost:" not in text:
            continue
        for lineno, line in enumerate(text.split("\n"), 1):
            if line.strip().startswith(("*", "//", "#")) and "127.0.0.1" not in line.split("//")[-1][:20]:
                continue
            for rx, kind in ((ABS_RE, "http"), (WS_RE, "ws")):
                for m in rx.finditer(line):
                    port = int(m.group(1))
                    if port < 5000:      # LM Studio/ollama territory, skip
                        continue
                    if port in (11434,):
                        continue
                    is_live = port in live or tcp_open(port)
                    findings.append({
                        "file": str(f.relative_to(ROOT)),
                        "line": lineno,
                        "port": port,
                        "kind": kind,
                        "live": is_live,
                        "truth": PORT_TRUTH.get(port, "UNKNOWN — not in the cognitive series"),
                        "same_origin": PREFER_SAME_ORIGIN.get(port),
                        "text": line.strip()[:120],
                    })
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("subtrees", nargs="*", default=["Frontend/multigate/src",
                                                   "Frontend/XR_Vessel/src",
                                                   "Backend", "foveated-memory",
                                                   "theme"])
    ap.add_argument("--live", action="store_true", help="only dead references")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    findings = scan(args.subtrees)
    dead = [f for f in findings if not f["live"]]
    unknown = [f for f in findings if f["truth"].startswith("UNKNOWN")]
    suggestions = [f for f in findings if f["live"] and f["same_origin"]]

    if args.as_json:
        print(json.dumps({"total": len(findings), "dead": dead,
                          "unknown": unknown, "same_origin_suggestions": suggestions}, indent=2))
        return 1 if dead else 0

    print(f"\n  scanned references : {len(findings)}")
    print(f"  DEAD (service down): {len(dead)}")
    print(f"  off-series ports   : {len(unknown)}")
    print(f"  could be same-origin: {len(suggestions)}\n")

    if dead:
        print("  ── DEAD REFERENCES (these break pages when the service is down)")
        for f in sorted(dead, key=lambda x: (x["port"], x["file"])):
            opt = "  [optional by design]" if f["port"] in OPTIONAL else ""
            print(f"    :{f['port']}  {f['file']}:{f['line']}  {f['kind']}{opt}")
            print(f"            {f['text']}")
    if unknown:
        print("\n  ── NOT IN THE COGNITIVE SERIES")
        for f in sorted(unknown, key=lambda x: x["port"]):
            print(f"    :{f['port']}  {f['file']}:{f['line']}")
    print()
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())