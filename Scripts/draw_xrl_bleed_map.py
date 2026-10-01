#!/usr/bin/env python3
"""
draw_xrl_bleed_map.py — Foveated context bleed-radius map.

Renders the codebase as concentric rings around the context window:
  Ring 0 (fovea)      — files injected into every prompt (the injection chain)
  Ring 1 (parafovea)  — one hop away: import/port/reference edge to ring 0
  Ring 2 (mid-field)  — wired to the fleet, two hops out
  Ring 3 (periphery)  — referenced but cold
  Outer dark          — unwired: nothing references them (missing links)

Output: xrl_bleed_map.png in repo root.

Usage:
    python3 Scripts/draw_xrl_bleed_map.py
"""

import fnmatch
import math
import os
import random
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(os.environ.get("FOVEAI_ROOT") or Path(__file__).resolve().parent.parent)
OUT = ROOT / "xrl_bleed_map.png"

W, H = 3200, 3200
CX, CY = W // 2, H // 2
BG = (8, 10, 16)

RING_RADII = [420, 780, 1140, 1450]  # ring0..ring3 orbit radius
RING_COLORS = [
    (0, 255, 220),  # ring0 — fovea, hot cyan
    (80, 200, 255),  # ring1 — parafovea, blue-cyan
    (90, 120, 255),  # ring2 — mid-field, indigo
    (110, 110, 160),  # ring3 — periphery, dim violet
]
UNWIRED_COLOR = (200, 90, 90)  # outer dark — cold red specks
EDGE_COLOR = (40, 140, 160)

# ── Ring-0 seed: the prompt-injection chain ─────────────────────────
INJECTORS = {
    "run_xrlf.py",
    "runtime/xrlf_runtime.py",
    "runtime/soul_bridge.py",
    "runtime/cognitive_steering.py",
    "runtime/triad_pipeline.py",
    "runtime/memory_planner.py",
    "memory/membrane_engine.py",
    "memory/tfidf_store.py",
    "llama_bridge/llama_engine.py",
    "formats/xrlf_parser.py",
    "foveated-memory/server.js",
    "foveated-memory/core/system-prompt-patch.js",
    "foveated-memory/core/ring-builder.js",
    "foveated-memory/core/memory-continuity.js",
    "foveated-memory/core/xrl-compressor.js",
    "foveated-memory/core/recall-interceptor.js",
    "foveated-memory/core/context-healer.js",
    "foveated-memory/core/context-compressor.js",
    "foveated-memory/core/importance-scorer.js",
    "Backend/Cognition/MindCore.py",
    "Backend/Cognition/soul_core.py",
    "Backend/Cognition/compagent.py",
    "Backend/Cognition/PersonaManager.py",
    "Backend/Cognition/persistent_memory.py",
    "Backend/Cognition/jen_soul.json",
    "Backend/Cognition/identity_soul.json",
}

SCAN_DIRS = [
    "Backend",
    "runtime",
    "memory",
    "formats",
    "builder",
    "llama_bridge",
    "foveated-memory",
    "Frontend/XR_Vessel/src",
    "Frontend/multigate/src",
    "client_quest/Assets/Scripts",
    "Tools",
    "Scripts",
    "tests",
]
EXTS = {".py", ".ts", ".tsx", ".js", ".cs", ".sh", ".xrlf", ".json"}
SKIP_DIRS = {
    "__pycache__",
    "node_modules",
    ".venv",
    ".git",
    "dist",
    "build",
    ".venv.bak.20260906",
    "out",
}
MAX_BYTES = 400_000

IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE)
CALL_RE = re.compile(r"(?:127\.0\.0\.1|localhost):(\d{4})")
BIND_RE = re.compile(
    r"(?:\.listen\(\s*(\d{4})|uvicorn\.run\([^)]*port\s*=\s*(\d{4})|PORT\s*=\s*(\d{4})|port\s*=\s*(\d{4}))"
)


def load_ignores():
    f = ROOT / ".xrl-ignore"
    if not f.exists():
        f = ROOT / ".tokenslayer-ignore"
    return (
        [
            l.strip()
            for l in f.read_text().splitlines()
            if l.strip() and not l.startswith("#")
        ]
        if f.exists()
        else []
    )


def is_ignored(rel, pats):
    for p in pats:
        p = p.replace("\\", "/")
        if (
            fnmatch.fnmatch(rel, p)
            or (p.endswith("/") and rel.startswith(p))
            or (not p.endswith("*") and (rel == p or rel.startswith(p + "/")))
        ):
            return True
    return False


def discover(pats):
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


def build_graph(files):
    """Edges between files: stem reference, local import, or shared port."""
    texts, sizes = {}, {}
    for rel in files:
        try:
            fp = ROOT / rel
            texts[rel] = fp.read_text(encoding="utf-8", errors="replace")
            sizes[rel] = fp.stat().st_size
        except Exception:
            pass

    stems = defaultdict(list)
    for f in files:
        stems[Path(f).stem].append(f)

    callers = {f: set(CALL_RE.findall(t)) for f, t in texts.items()}
    binders = {}
    for f, t in texts.items():
        ports = set()
        for m in BIND_RE.finditer(t):
            ports.update(g for g in m.groups() if g)
        binders[f] = ports
    port_owner = defaultdict(list)
    for f, ps in binders.items():
        for p in ps:
            port_owner[p].append(f)

    edges = set()
    # stem references + imports + shared ports
    for rel, text in texts.items():
        stem = Path(rel).stem
        for other, ot in texts.items():
            if other == rel:
                continue
            ostem = Path(other).stem
            if len(ostem) >= 5 and re.search(
                rf"(?<![\w]){re.escape(ostem)}(?![\w])", text
            ):
                edges.add((rel, other))
        if rel.endswith(".py"):
            for m in IMPORT_RE.finditer(text):
                mod = (m.group(1) or m.group(2) or "").split(".")[-1]
                for tgt in stems.get(mod, []):
                    if tgt != rel:
                        edges.add((rel, tgt))
        for port in callers.get(rel, ()):
            for owner in port_owner.get(port, []):
                if owner != rel:
                    edges.add((rel, owner))
    return edges, sizes, texts


def assign_rings(files, edges):
    """BFS outward from INJECTORS through edges."""
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)

    ring = {}
    seeds = [
        f
        for f in files
        if f in INJECTORS or Path(f).name in {Path(s).name for s in INJECTORS}
    ]
    for s in seeds:
        ring[s] = 0
    frontier = list(seeds)
    depth = 0
    while frontier and depth < 3:
        nxt = []
        for f in frontier:
            for nb in adj.get(f, ()):
                if nb not in ring:
                    ring[nb] = depth + 1
                    nxt.append(nb)
        frontier = nxt
        depth += 1
    for f in files:
        ring.setdefault(f, 4)  # 4 = unwired outer dark
    return ring


def font(sz, bold=False):
    for p in (
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def draw():
    random.seed(7)
    pats = load_ignores()
    files = discover(pats)
    print(f"scanning {len(files)} files…")
    edges, sizes, texts = build_graph(files)
    ring = assign_rings(files, edges)
    counts = defaultdict(int)
    for f in files:
        counts[ring[f]] += 1
    print("rings:", dict(counts), "| edges:", len(edges))

    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img, "RGBA")

    # halo rings (bleed gradient)
    for i, r in enumerate(RING_RADII):
        c = RING_COLORS[i]
        for k in range(3):
            dr.ellipse(
                [CX - r - k, CY - r - k, CX + r + k, CY + r + k],
                outline=c + (60 - k * 18,),
            )
        # ring fill glow — fainter inside
        dr.ellipse([CX - r, CY - r, CX + r, CY + r], fill=c + (10 if i == 0 else 6,))

    # core: the context window
    for r, a in [(90, 200), (140, 90), (200, 40)]:
        dr.ellipse([CX - r, CY - r, CX + r, CY + r], fill=(255, 255, 255, a))
    dr.text(
        (CX, CY - 14), "CONTEXT", font=font(34, True), fill=(10, 12, 20), anchor="mm"
    )
    dr.text(
        (CX, CY + 18), "system prompt", font=font(22), fill=(30, 40, 60), anchor="mm"
    )

    # node positions: even angular slots per ring, slight radial jitter
    per_ring = defaultdict(list)
    for f in files:
        per_ring[ring[f]].append(f)

    pos = {}
    for r_idx in range(4):
        members = sorted(per_ring[r_idx])
        n = len(members)
        for i, f in enumerate(members):
            ang = 2 * math.pi * i / max(n, 1) + r_idx * 0.7
            rad = RING_RADII[r_idx] + random.uniform(-60, 60)
            pos[f] = (CX + rad * math.cos(ang), CY + rad * math.sin(ang))

    # unwired — far outer field, sparse
    uw = sorted(per_ring[4])
    for i, f in enumerate(uw):
        ang = 2 * math.pi * i / max(len(uw), 1)
        rad = random.uniform(1520, 1580)
        pos[f] = (CX + rad * math.cos(ang), CY + rad * math.sin(ang))

    # edges — only between nodes at ring ≤2 to keep it readable
    for a, b in edges:
        if ring.get(a, 4) <= 2 and ring.get(b, 4) <= 2 and a in pos and b in pos:
            dr.line([pos[a], pos[b]], fill=EDGE_COLOR + (38,), width=1)

    # nodes
    label_budget = {0: 40, 1: 30, 2: 8, 3: 0}
    for f, (x, y) in pos.items():
        r = ring[f]
        sz = max(3.0, min(16.0, math.sqrt(sizes.get(f, 4000)) / 30))
        col = UNWIRED_COLOR if r == 4 else RING_COLORS[r]
        alpha = 110 if r == 4 else 230
        dr.ellipse([x - sz, y - sz, x + sz, y + sz], fill=col + (alpha,))

    # labels — ring0 always, ring1 top by size
    labeled = sorted(per_ring[0], key=lambda f: -sizes.get(f, 0))[: label_budget[0]]
    labeled += sorted(per_ring[1], key=lambda f: -sizes.get(f, 0))[: label_budget[1]]
    labeled += sorted(per_ring[2], key=lambda f: -sizes.get(f, 0))[: label_budget[2]]
    for f in labeled:
        x, y = pos[f]
        name = Path(f).name
        if len(name) > 26:
            name = name[:24] + "…"
        r = ring[f]
        dr.text(
            (x + 12, y - 8), name, font=font(19, r == 0), fill=RING_COLORS[r] + (255,)
        )

    # ring captions on the left axis
    for i, r in enumerate(RING_RADII):
        dr.text(
            (CX - r, CY - 18),
            [
                "RING 0 · FOVEA — injected",
                "RING 1 · PARAFOVEA — one hop",
                "RING 2 · MID-FIELD — fleet-wired",
                "RING 3 · PERIPHERY — cold refs",
            ][i],
            font=font(22, True),
            fill=RING_COLORS[i] + (220,),
            anchor="rm",
        )
    dr.text(
        (CX - 1560, CY - 18),
        "OUTER DARK — unwired",
        font=font(22, True),
        fill=UNWIRED_COLOR + (230,),
        anchor="lm",
    )

    # title + stats
    dr.text(
        (60, 50),
        "FoveAI — XRL Context Bleed-Radius Map",
        font=font(46, True),
        fill=(235, 245, 255),
    )
    dr.text(
        (60, 112),
        f"{len(files)} files · {len(edges)} edges · "
        f"r0:{counts[0]} injected · r1:{counts[1]} · r2:{counts[2]} · "
        f"r3:{counts[3]} · unwired:{counts[4]}",
        font=font(24),
        fill=(150, 170, 200),
    )
    dr.text(
        (60, H - 70),
        "node size ∝ file size · edges = imports / port calls / stem references",
        font=font(20),
        fill=(110, 125, 150),
    )

    img.save(OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    draw()
