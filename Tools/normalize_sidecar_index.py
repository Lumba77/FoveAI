#!/usr/bin/env python3
"""
Tools/normalize_sidecar_index.py — Normalize Windows backslashes to Linux forward slashes.

Fixes Task 3.5.2 in OPEN-XRL-PLAN.md.
Creates backup files (.bak) before modifying JSON metadata in .sidecar/cache/.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path("/home/lumba/FoveAI")
CACHE_DIR = ROOT / ".sidecar" / "cache"

FILES = [
    "workspace-index.json",
    "symbol-embeddings-meta.json",
    "symbol-graph.json",
    "embeddings-meta.json"
]


def normalize_cache():
    if not CACHE_DIR.exists():
        print(f"[ERROR] Cache directory does not exist: {CACHE_DIR}")
        sys.exit(1)

    print(f"Normalizing cache files in {CACHE_DIR}...")
    for fname in FILES:
        p = CACHE_DIR / fname
        if not p.exists():
            print(f"  [SKIP] {fname} not found.")
            continue

        bak = CACHE_DIR / f"{fname}.bak"
        if not bak.exists():
            shutil.copy2(p, bak)
            print(f"  [BAK] Created backup: {bak.name}")

        text = p.read_text(encoding="utf-8")
        # Replace Windows path separators in JSON strings
        normalized = text.replace(r"\\", "/")
        p.write_text(normalized, encoding="utf-8")
        print(f"  [OK]  Normalized: {fname}")

    # Verify resolution
    print("\nVerifying normalized path resolution on Linux:")
    ws_file = CACHE_DIR / "workspace-index.json"
    if ws_file.exists():
        ws_data = json.loads(ws_file.read_text(encoding="utf-8"))
        files = ws_data.get("files", [])
        resolved = sum(1 for f in files if (ROOT / f["path"]).exists())
        print(f"  workspace-index.json: {resolved} / {len(files)} files resolve on host ({resolved / max(len(files), 1) * 100:.1f}%)")

    sym_file = CACHE_DIR / "symbol-embeddings-meta.json"
    if sym_file.exists():
        sym_data = json.loads(sym_file.read_text(encoding="utf-8"))
        entries = sym_data.get("entries", {})
        resolved = sum(1 for k, e in entries.items() if (ROOT / e["filePath"]).exists())
        print(f"  symbol-embeddings-meta.json: {resolved} / {len(entries)} symbols resolve on host ({resolved / max(len(entries), 1) * 100:.1f}%)")

    graph_file = CACHE_DIR / "symbol-graph.json"
    if graph_file.exists():
        graph_data = json.loads(graph_file.read_text(encoding="utf-8"))
        symbols = graph_data.get("symbols", [])
        resolved = sum(1 for s in symbols if (ROOT / s.get("filePath", "")).exists())
        print(f"  symbol-graph.json: {resolved} / {len(symbols)} graph symbols resolve on host ({resolved / max(len(symbols), 1) * 100:.1f}%)")


if __name__ == "__main__":
    normalize_cache()
