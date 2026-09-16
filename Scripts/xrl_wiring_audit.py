#!/usr/bin/env python3
"""
xrl_wiring_audit.py — cross-repo wiring audit via XRL scan.

Maps the real wiring of the fleet:
  LISTENERS   — files that bind ports (uvicorn.run / app.listen / PORT=)
  CALLERS     — files that call ports (127.0.0.1:N, localhost:N, ws://…:N)
  IMPORTS     — local module import edges
  PARALLEL    — duplicate definitions / archive copies (parallel wirings)
  UNWIRED     — source files nothing references (missing links)

Usage:
    python3 Scripts/xrl_wiring_audit.py [--json]
"""

import fnmatch
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ.get("FOVEAI_ROOT") or Path(__file__).resolve().parent.parent)

IGNORE_FILE = ROOT / ".xrl-ignore"
if not IGNORE_FILE.exists():
    IGNORE_FILE = ROOT / ".tokenslayer-ignore"

SCAN_DIRS = [
    "Backend", "runtime", "memory", "formats", "builder", "llama_bridge",
    "foveated-memory", "Frontend/XR_Vessel/src", "Frontend/multigate/src",
    "client_quest/Assets/Scripts", "Tools", "Scripts", "tests",
]
EXTS = {".py", ".ts", ".tsx", ".js", ".cs", ".sh"}
SKIP_DIRS = {"__pycache__", "node_modules", ".venv", ".git", "dist", "build", ".venv.bak.20260906"}
MAX_BYTES = 400_000

CALL_RE = re.compile(r'(?:127\.0\.0\.1|localhost|192\.168\.\d+\.\d+|ws://[\d.]+|0\.0\.0\.0):(\d{4})')
BIND_RE = re.compile(
    r'(?:port\s*=\s*(\d{4})|\.listen\(\s*(\d{4})|uvicorn\.run\([^)]*port\s*=\s*(\d{4})'
    r'|PORT\s*=\s*(\d{4})|--port["\']?\s*[,=]?\s*["\']?(\d{4}))'
)
IMPORT_RE = re.compile(r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.M)
ENV_PORT_RE = re.compile(r'(?:PORT|_URL)\s*=\s*[^\n]*?(\d{4})')

# Local top-level modules that exist in-repo (for import edge resolution)
LOCAL_ROOTS = ["Backend/Cognition", "Backend/Memory", "Backend/Creativity", "runtime", "memory", "formats", "builder", "llama_bridge", "Tools"]


def load_ignores() -> list:
    pats = []
    if IGNORE_FILE.exists():
        for line in IGNORE_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line)
    return pats


def is_ignored(rel: str, pats: list) -> bool:
    for p in pats:
        p = p.replace("\\", "/")
        if fnmatch.fnmatch(rel, p):
            return True
        if p.endswith("/") and rel.startswith(p):
            return True
        if not p.endswith("*") and (rel == p or rel.startswith(p + "/")):
            return True
    return False


def discover(pats: list) -> list:
    found = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for name in filenames:
                p = Path(dirpath) / name
                if p.suffix not in EXTS:
                    continue
                try:
                    if p.stat().st_size > MAX_BYTES:
                        continue
                except OSError:
                    continue
                rel = p.relative_to(ROOT).as_posix()
                if not is_ignored(rel, pats):
                    found.append(rel)
    return sorted(found)


def main() -> None:
    pats = load_ignores()
    files = discover(pats)

    # module name index: stem → files providing it
    stems = defaultdict(list)
    for f in files:
        stems[Path(f).stem].append(f)

    callers = defaultdict(set)    # file -> ports it calls
    binders = defaultdict(set)    # file -> ports it binds
    env_ports = defaultdict(set)  # file -> ports in PORT=/URL= assignments
    imports = defaultdict(set)    # file -> local modules it imports
    references = defaultdict(set) # filename stem -> files that mention it
    defs = defaultdict(list)      # symbol -> files defining it (parallel check)

    def_re = re.compile(r'^\s*(?:async\s+)?(?:def|class|function)\s+(\w+)|^\s*(?:export\s+)?(?:class|interface)\s+(\w+)', re.M)

    texts = {}
    for rel in files:
        try:
            texts[rel] = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

    for rel, text in texts.items():
        for m in CALL_RE.finditer(text):
            callers[rel].add(int(m.group(1)))
        for m in BIND_RE.finditer(text):
            for g in m.groups():
                if g:
                    binders[rel].add(int(g))
        for m in ENV_PORT_RE.finditer(text):
            env_ports[rel].add(int(m.group(1)))
        if rel.endswith(".py"):
            for m in IMPORT_RE.finditer(text):
                mod = (m.group(1) or m.group(2) or "").split(".")[-1]
                if mod in stems:
                    imports[rel].add(mod)
        for m in def_re.finditer(text):
            sym = m.group(1) or m.group(2)
            if sym:
                defs[sym].append(rel)

    # reference pass over cached texts (stem must appear as a word)
    for rel in files:
        stem = Path(rel).stem
        if len(stem) < 4:
            continue
        pat = re.compile(rf'(?<![\w]){re.escape(stem)}(?![\w])')
        for other, text in texts.items():
            if other != rel and pat.search(text):
                references[stem].add(other)

    # ── Report ──────────────────────────────────────────────────────
    out = []

    out.append("═" * 60)
    out.append("XRL WIRING AUDIT — %d files scanned" % len(files))
    out.append("═" * 60)

    out.append("\n▶ LISTENERS (files that bind ports)")
    for f, ports in sorted(binders.items()):
        out.append(f"  {f}  binds {sorted(ports)}")

    out.append("\n▶ CALLERS (files that dial ports)")
    interesting = {p for ps in callers.values() for p in ps if 8000 <= p <= 8510 or p in (5176, 5177, 1234, 11434)}
    for f, ports in sorted(callers.items()):
        hits = sorted(p for p in ports if 8000 <= p <= 8510 or p in (5176, 5177, 1234, 11434))
        if hits:
            out.append(f"  {f}  → {hits}")

    # Wiring edges: caller file → binder file (via shared port)
    port_to_binder = defaultdict(list)
    for f, ports in binders.items():
        for p in ports:
            port_to_binder[p].append(f)
    out.append("\n▶ EDGES (caller → listener via port)")
    for f, ports in sorted(callers.items()):
        for p in sorted(ports):
            for b in port_to_binder.get(p, []):
                if b != f:
                    out.append(f"  {f}  ──:{p}──▶  {b}")

    out.append("\n▶ PARALLEL WIRINGS (duplicate symbol definitions)")
    for sym, fs in sorted(defs.items()):
        u = sorted(set(fs))
        if len(u) > 1 and len(sym) > 4:
            out.append(f"  {sym}  defined in {len(u)} files:")
            for f in u:
                out.append(f"      {f}")

    out.append("\n▶ PARALLEL FILES (archive/backup/nested copies)")
    for f in files:
        name = Path(f).name
        if re.search(r'(_archive|_v\d+|\.bak|_old|_legacy|_copy)', name, re.I):
            out.append(f"  {f}")
    # same-stem collisions in different dirs
    for stem, fs in sorted(stems.items()):
        if len(fs) > 1 and len(stem) > 3:
            out.append(f"  stem '{stem}' exists in:")
            for f in fs:
                out.append(f"      {f}")

    out.append("\n▶ UNWIRED (source files nothing references or imports)")
    entry_ok = re.compile(r'(test_|^tests/|__init__|run_|_main|main\.|index\.|server\.js|Console|Taskbar|launcher)')
    for f in files:
        stem = Path(f).stem
        wired = bool(references.get(stem)) or any(stem in im for im in imports.values())
        if not wired and not entry_ok.search(f):
            out.append(f"  {f}")

    report = "\n".join(out)
    print(report)

    if "--json" in sys.argv:
        (ROOT / "wiring_audit.json").write_text(json.dumps({
            "binders": {k: sorted(v) for k, v in binders.items()},
            "callers": {k: sorted(v) for k, v in callers.items()},
            "imports": {k: sorted(v) for k, v in imports.items()},
        }, indent=2))
        print("\n[wrote wiring_audit.json]")


if __name__ == "__main__":
    main()
