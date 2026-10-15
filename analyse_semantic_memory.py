#!/usr/bin/env python3
"""
analyse_semantic_memory.py — read-only structural probe of the XRLF membrane.

Embeds the cleaned turn corpus with local MiniLM and reports whether semantic
similarity finds structure that the old TF-IDF path could not.

Changes nothing. Reads the membrane, writes a JSON report.
"""

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/lumba/FoveAI")
from xrlf_embedder import Embedder  # noqa: E402

DB = "/home/lumba/FoveAI/xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf.cache/memory.db"
OUT = Path("/tmp/opencode/semantic_report.json")
TAGS = re.compile(r"<(\w+):\s*([^>]*)>")
DEGENERATE = re.compile(r"^(<.*|\W*)$")


def clean(text: str) -> str:
    """Strip avatar markup, keep the substance."""
    t = TAGS.sub(" ", text or "")
    t = re.sub(r"\((?:thought|mood)\s*:?[^)]*\)", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select id, role, content, timestamp from turns order by id"
    ).fetchall()
    con.close()
    print(f"[probe] read {len(rows)} turns (read-only)")

    cleaned = [(i, r, clean(c)) for i, r, c, _ in rows]
    usable = [(i, r, t) for i, r, t in cleaned if len(t) >= 25 and not DEGENERATE.match(t)]
    dropped = len(cleaned) - len(usable)
    print(f"[probe] usable after tag-strip + min-length: {len(usable)} (dropped {dropped})")

    counts = Counter(t for _, _, t in usable)
    uniq_texts = list(counts.keys())
    print(f"[probe] exact-duplicate collapse: {len(usable)} -> {len(uniq_texts)} unique")

    emb = Embedder()
    print(f"[probe] embedding {len(uniq_texts)} unique texts (dim={emb.dim})...")
    vecs = emb.encode(uniq_texts)

    # nearest neighbours for a structural read
    sim = vecs @ vecs.T
    np.fill_diagonal(sim, -1.0)
    report = {
        "turns_total": len(rows),
        "usable": len(usable),
        "dropped_degenerate": dropped,
        "unique_texts": len(uniq_texts),
        "dim": emb.dim,
        "top_duplicates": [
            {"count": n, "text": t[:120]} for t, n in counts.most_common(6)
        ],
        "clusters": [],
    }

    # greedy clustering at a fixed cosine threshold — no sklearn dependency
    THRESH = 0.72
    assigned = [-1] * len(uniq_texts)
    clusters = []
    for idx in range(len(uniq_texts)):
        if assigned[idx] != -1:
            continue
        cid = len(clusters)
        members = [idx]
        assigned[idx] = cid
        for j in np.where(sim[idx] >= THRESH)[0]:
            if assigned[j] == -1:
                assigned[j] = cid
                members.append(int(j))
        members.sort(key=lambda m: -float(sim[idx, m]))
        clusters.append(members)

    print(f"[probe] {len(clusters)} clusters at cosine>={THRESH}")
    clusters.sort(key=len, reverse=True)
    for members in clusters[:14]:
        report["clusters"].append(
            {
                "size": len(members),
                "members": [
                    {"text": uniq_texts[m][:200], "sim": round(float(sim[members[0], m]), 3)}
                    for m in members[:5]
                ],
            }
        )
        print(f"\n  cluster n={len(members)}")
        for m in members[:4]:
            print(f"    {sim[members[0], m]:.3f}  {uniq_texts[m][:96]}")

    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n[probe] report -> {OUT}")


if __name__ == "__main__":
    main()