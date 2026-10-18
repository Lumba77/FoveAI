"""
Forge/nursery/genome_extractor.py — Promethease Genome Extractor
====================================================================
Turns the Promethease DNA report (Frontend/multigate/src/assets/dna/index.html)
into a structured, queryable genome corpus.

The report stores ~21k SNPedia genos as base64 + raw-deflate JSON blobs
(`decompressString('...')`). This module decompresses them and normalizes
each geno into {snp, genotype, magnitude, summary}.

This is the "genome search bank" (Prometheus) — the source material for
teaching nano models to compress genomic data into XRL seeds.
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from pathlib import Path
from typing import Any

PROMETHEASE_HTML = Path(
    "/home/lumba/FoveAI/Frontend/multigate/src/assets/dna/index.html"
)
OUTPUT_JSONL = Path("/home/lumba/FoveAI/Forge/nursery/corpus/genome.jsonl")
OUTPUT_JSON = Path("/home/lumba/FoveAI/Forge/nursery/corpus/genome.json")


def extract_raw_objects(html_path: Path | None = None) -> list[dict[str, Any]]:
    """Decompress and JSON-parse every mygenos blob into a flat list of dicts."""
    p = html_path or PROMETHEASE_HTML
    txt = p.read_text(encoding="utf-8", errors="replace")
    blobs = re.findall(r"decompressString\('([A-Za-z0-9+/=]+)'\)", txt)

    items: list[dict[str, Any]] = []
    fails = 0
    for b in blobs:
        raw = base64.b64decode(b)
        try:
            data = zlib.decompress(raw, 47)  # auto-detect zlib/gzip
            obj = json.loads(data.decode("utf-8"))
        except Exception:
            fails += 1
            continue
        if isinstance(obj, list):
            items.extend(obj)
        else:
            items.append(obj)
    return items, fails


def normalize(genos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce each geno to the fields we care about for XRL training.

    Most SNP entries use `rsnum` (rs id) + `was` (genotype); the special
    gender/meta entries use `title` + `genosummary`. We handle both.
    """
    out: list[dict[str, Any]] = []
    for g in genos:
        snp = (g.get("rsnum") or g.get("title") or "").strip()
        genotype = (g.get("was") or g.get("genosummary") or "").strip()
        summary = (g.get("genosummary") or g.get("genobody") or "").strip()
        magnitude = g.get("magnitude", 0)
        if not snp:
            continue
        out.append({
            "snp": snp,
            "genotype": genotype,
            "magnitude": magnitude,
            "summary": summary[:500],  # cap long bodies for economy
            "genes": g.get("genes", []),
        })
    return out


def extract_and_save(
    html_path: Path | None = None,
    output_jsonl: Path | None = None,
    output_json: Path | None = None,
) -> dict[str, Any]:
    """Full pipeline: decompress -> normalize -> persist -> report stats."""
    raw, fails = extract_raw_objects(html_path)
    genos = normalize(raw)
    # Sort by magnitude desc (most important first) for the "search bank".
    genos.sort(key=lambda g: (g["magnitude"] or 0), reverse=True)

    out_jl = output_jsonl or OUTPUT_JSONL
    out_jl.parent.mkdir(parents=True, exist_ok=True)
    with open(out_jl, "w", encoding="utf-8") as f:
        for g in genos:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    out_j = output_json or OUTPUT_JSON
    with open(out_j, "w", encoding="utf-8") as f:
        json.dump(genos, f, ensure_ascii=False, indent=2)

    stats = {
        "raw_items": len(raw),
        "decompress_fails": fails,
        "total_genos": len(genos),
        "with_genotype": sum(1 for g in genos if g["genotype"] and g["genotype"] != "not tested"),
        "top_magnitude": genos[0] if genos else None,
        "output_jsonl": str(out_jl),
        "output_json": str(out_j),
    }
    return stats


if __name__ == "__main__":
    import sys

    stats = extract_and_save()
    print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))
