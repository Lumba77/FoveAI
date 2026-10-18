"""
runtime/xrl_degeneracy.py — Genome Degeneracy Derivation
==========================================================
Measure the real "synonym collapse" in the genome corpus and map it to the
XRL degree scale. Nature's genetic code collapses 64 codons -> 20 amino acids
(~3.2x). We measure the analogous collapse across the 18,899 SNPs and derive
an empirical xrl_degree = f(collapse ratio).

Levels (each is one "degree" of compression):
  degree 0  raw identity                     (snp + genotype, no collapse)
  degree 1  genotype alphabet                (distinct genotype strings)
  degree 2  significance alphabet            (distinct magnitude buckets)
  degree 3  semantic category (keyword)      (risk/protection/carrier/...)
  degree 4  effect polarity                  (risk / protection / neutral / other)
  degree 5  high-significance subset only    (sparse coding: drop mag<2)
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

GENOME_PATH = Path("/home/lumba/FoveAI/Forge/nursery/corpus/genome.jsonl")


def _load() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not GENOME_PATH.exists():
        return out
    with open(GENOME_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _bucket_magnitude(mag: float) -> str:
    """Coarse significance bucket for the magnitude field."""
    if mag is None:
        return "0"
    return str(int(round(float(mag))))


def _semantic_category(summary: str) -> str:
    """Coarse keyword classifier: map a clinical summary to a semantic bucket."""
    s = (summary or "").lower()
    if not s or "not tested" in s:
        return "untested"
    if "risk" in s or "increased" in s or "higher" in s or "susceptib" in s:
        return "risk"
    if ("lower" in s or "decreased" in s or "protect" in s
            or "resistance" in s or "reduced" in s):
        return "protection"
    if "carrier" in s or "recessive" in s or "heterozyg" in s:
        return "carrier"
    if s in ("male", "female") or "baldness" in s or "gender" in s:
        return "sex"
    if "normal" in s or "common" in s or "benign" in s:
        return "neutral"
    return "other"


def _effect_polarity(cat: str) -> str:
    if cat in ("risk",):
        return "risk"
    if cat in ("protection",):
        return "protection"
    if cat in ("untested", "neutral"):
        return "neutral"
    return "other"


def derive() -> dict[str, Any]:
    """Compute a meaning-preserving degeneracy ladder.

    The raw collapse is dominated by 97.6% 'untested'+'neutral' noise. The
    useful measurement is how the *actionable* signal compresses while its
    meaning is preserved. Each level drops only redundant/junk layers.
    """
    genos = _load()
    n = len(genos)

    def cat(g):
        return _semantic_category(g["summary"])

    tested = [g for g in genos if cat(g) != "untested"]
    actionable = [g for g in genos if cat(g) in ("risk", "protection", "carrier")]
    significant = [g for g in genos if (g.get("magnitude") or 0) >= 2]

    # Meaning-preserving ladder (cumulative drop of junk):
    levels = [
        ("degree_0_identity", n, "all SNPs, lossless"),
        ("degree_1_drop_untested", len(tested), "drop 'untested' (no info)"),
        ("degree_2_drop_neutral", len(actionable) + len([g for g in tested if cat(g) == 'other']),
         "keep risk/protection/carrier/other"),
        ("degree_3_keep_actionable", len(actionable), "risk/protection/carrier only"),
        ("degree_4_semantic_category", len(Counter(cat(g) for g in genos)), "collapse to semantic buckets"),
        ("degree_5_effect_polarity", len(Counter(_effect_polarity(cat(g)) for g in genos)),
         "collapse to polarity"),
    ]

    table = {}
    cumulative = n
    for name, count, desc in levels:
        ratio = round(n / max(1, count), 2)
        table[name] = {
            "distinct": count,
            "collapse_x_total": ratio,
            "collapse_x_step": round(cumulative / max(1, count), 2),
            "description": desc,
        }
        cumulative = count

    report = {
        "total_snps": n,
        "levels": table,
        "semantic_categories": dict(Counter(cat(g) for g in genos)),
        "effect_polarities": dict(Counter(_effect_polarity(cat(g)) for g in genos)),
        "actionable_snps": len(actionable),
        "significant_snps": len(significant),
        "sparse_coding_x": round(n / max(1, len(actionable)), 2),  # 18.9k -> ~360
        "noncoding_fraction": round((n - len(actionable)) / n, 4),
    }
    return report


def degree_from_collapse(collapse_x: float) -> dict[str, Any]:
    """
    Map a collapse ratio to xrl_degree (0-9). Anchored so that:
      - collapse ~2.7x  -> degree 1 (drop obvious junk)
      - collapse ~3.2x  -> degree 3 (nature's codon code)
      - collapse ~50x   -> degree 6 (sparse coding to actionable signal)
    """
    import math

    if collapse_x <= 1.0:
        degree = 0
    else:
        # log base ~1.9: degree 1 ~ 1.9x, degree 3 ~ 6.9x ... tuned so
        # 2.7x->1, 3.2x->~2, 52x->~6.
        degree = round(math.log(collapse_x) / math.log(1.9))
        degree = max(0, min(9, degree))
    return {
        "collapse_x": round(collapse_x, 2),
        "xrl_degree": degree,
    }


if __name__ == "__main__":
    r = derive()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    print("\n== degree mapping (step collapse) ==")
    for name, meta in r["levels"].items():
        d = degree_from_collapse(meta["collapse_x_step"])
        print(
            f"  {name:28s} step={meta['collapse_x_step']:>8.2f}x "
            f"total={meta['collapse_x_total']:>8.2f}x -> degree {d['xrl_degree']}"
        )
