"""
Forge/nursery/xrl_nano_data.py — Nano XRL Training Data Generator
====================================================================
Generates a multi-stage training corpus for nano-native XRL models.

Stages (one JSONL each):
  seed_decode         micro-seed + profile + user  ->  response
  seed_encode         long verbose context         ->  compact XRL seed
  rubble_to_principa  noisy/repetitive text        ->  clean terse seed
  red_thread_weaving  seed fragments               ->  single woven thread

Each sample uses the ultra-terse micro-seed (principle IDs + goal slugs)
so the corpus stays as small as possible — the "economy rule".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from runtime.xrl_principia import XRLPrincipiaCompiler

logger = logging.getLogger(__name__)

CORPUS_DIR = Path("/home/lumba/FoveAI/Forge/nursery/corpus")

GENOME_CURRICULUM_CAP = 240

# ── Stage 1: seed decode exemplars ────────────────────────────────────────────
# (profile, user_prompt, expected_response)
SEED_EXEMPLARS: list[tuple[str, str, str]] = [
    # chat
    ("chat", "Explain semantic compression in one sentence.",
     "Semantic compression keeps the meaning while discarding the wording."),
    ("chat", "What is XRL?",
     "XRL is a semantic compression protocol that turns context into compact, structured seeds."),
    ("chat", "What is the goal of FoveAI Labs?",
     "FoveAI Labs builds compression and efficiency technology for smarter, smaller models."),
    ("chat", "What is a red thread?",
     "A red thread is a compact woven context seed that carries constitution, goals, and memory."),
    ("chat", "Name the compression target.",
     "2.6x size reduction on 1B-2B models at MoQ 3.6-equivalent quality."),
    ("chat", "How many principles does FoveAI follow?",
     "Eleven kernel invariants, P0 through P11."),
    ("chat", "What is the hypermind?",
     "A swarm of one seed bearer, three weavers, and one core router."),
    ("chat", "What is foveated memory?",
     "Memory split into a sharp center and compressed periphery for infinite recall."),
    # code
    ("code", "Write a Python function to add two numbers.",
     "def add(a, b):\n    return a + b"),
    ("code", "Sort a list of numbers in Python.",
     "nums.sort()  # in-place\nsorted(nums)  # returns a new list"),
    ("code", "Reverse a string in Python.",
     "s[::-1]"),
    ("code", "Read a file in Python.",
     "with open('f.txt') as f:\n    data = f.read()"),
    ("code", "Count list length in Python.",
     "len(items)"),
    ("code", "Check if a key exists in a dict.",
     "key in d"),
    # vision
    ("vision", "Describe the image.",
     "[vision] A description of the salient objects and their arrangement."),
    ("vision", "What is the dominant color?",
     "[vision] The dominant color of the scene."),
    # memory
    ("memory", "Recall the user's name.",
     "Recall the salient identity facts from the seed."),
    ("memory", "What was the last decision?",
     "The most recent decision recorded in the digest."),
    # logic
    ("logic", "Reason about the tradeoff.",
     "State the tradeoff and the chosen balance."),
    ("logic", "Which option is better?",
     "The option that best satisfies the principia and goal."),
    # style
    ("style", "Make the tone warmer.",
     "A warmer, friendlier phrasing of the same content."),
    ("style", "Make it more concise.",
     "A shorter phrasing that keeps the meaning."),
]


# ── Stage 2: seed encode (long context -> seed) ───────────────────────────────
# Each entry: (long_verbose_context, compact_seed)
SEED_ENCODE_EXAMPLES: list[tuple[str, str]] = [
    (
        "The user asked a long, rambling question about how to sort a list of numbers in Python, "
        "going on about how they tried a for loop and it was too slow, and then wondered if there "
        "was a built-in function, and then asked again about sorting in place versus returning a new list.",
        "<XRL-SEED d=3>P0 P1 P2<G>python list sort</G><C/>",
    ),
    (
        "Over several messages the user explained they wanted to rename the model nursery to FoveAI Labs, "
        "mentioned it should focus on compression technology rather than making more variants, and asked "
        "about smaller and smarter models.",
        "<XRL-SEED d=3>P10<G>foveai labs compression</G><C/>",
    ),
    (
        "The user talked at length about a swarm of small models, first mentioning draft models, then a hive "
        "mind, then a hypermind with a seed bearer and weavers and a core router.",
        "<XRL-SEED d=3>P0 P2<G>hypermind swarm</G><C/>",
    ),
]


# ── Stage 3: rubble -> principa (noise -> clean) ──────────────────────────────
RUBBLE_EXAMPLES: list[tuple[str, str]] = [
    (
        "sort list sort list sort list python sort python sort in place in place sorted sorted new list new list",
        "Python list sorting: sort() in-place, sorted() returns new list.",
    ),
    (
        "foveai labs foveai labs foveai labs rename nursery rename nursery compression compression compression",
        "FoveAI Labs: compression technology lab, not a model nursery.",
    ),
    (
        "hypermind hypermind seed bearer weaver weaver weaver router router router core router core router",
        "Hypermind: seed bearer + 3 weavers + core router.",
    ),
]


# ── Stage 5: genome compression (raw SNPs -> terse XRL seed) ─────────────────
# Magnitude-ranked selection (sparse coding): keep snp+genotype+significance,
# drop the verbose clinical prose. This is codon-degeneracy applied to DNA.
def _load_genome(limit: int | None = None) -> list[dict[str, Any]]:
    """Load top-magnitude SNPs from the extracted genome corpus."""
    genos: list[dict[str, Any]] = []
    p = CORPUS_DIR / "genome.jsonl"
    if not p.exists():
        return genos
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            genos.append(json.loads(line))
            if limit is not None and len(genos) >= limit:
                break
    return genos


def _genome_samples(
    genos: list[dict[str, Any]],
    chunk: int,
    omit_mag_frac: float = 0.0,
    omit_gt_frac: float = 0.0,
    rng: "random.Random | None" = None,
) -> list[dict[str, Any]]:
    """Build genome -> XRL seed samples from a SNP list.

    With omit_mag_frac/omit_gt_frac > 0, some raw lines drop mag (or gt)
    exactly like the redaction eval: `{snp} {gt}:` / `{snp} mag{n}:`.
    The seed always keeps the full value, so the model must fill it in
    from memorized knowledge instead of copying.
    """
    if (omit_mag_frac or omit_gt_frac) and rng is None:
        import random
        rng = random.Random(7)
    samples: list[dict[str, Any]] = []
    for i in range(0, len(genos) - chunk + 1, chunk):
        group = genos[i:i + chunk]
        raw_parts = []
        seed_parts = []
        for g in group:
            snp = g["snp"]
            gt = g["genotype"]
            mag = g.get("magnitude", 0)
            roll = rng.random() if rng is not None else 0.0
            if omit_mag_frac and roll < omit_mag_frac:
                raw_parts.append(f"{snp} {gt}: {g.get('summary','')}")
            elif omit_gt_frac and roll < omit_mag_frac + omit_gt_frac:
                raw_parts.append(f"{snp} mag{mag}: {g.get('summary','')}")
            else:
                raw_parts.append(f"{snp} {gt} mag{mag}: {g.get('summary','')}")
            seed_parts.append(f"{snp}:{gt}:{mag}")
        raw_block = "<GENOME>\n" + "\n".join(raw_parts) + "\n</GENOME>"
        seed = "<XRL-SEED d=3>" + " ".join(f"<SNP>{s}</SNP>" for s in seed_parts) + "<C/>"
        samples.append({
            "text": raw_block + "\n" + seed,
            "metadata": {"stage": "genome_compression", "chunk": chunk},
        })
    return samples


def generate_genome_compression(
    path: Path,
    chunk: int = 6,
    holdout: int = 240,
    random_holdout: bool = False,
    omit_mag_frac: float = 0.0,
    omit_gt_frac: float = 0.0,
    rng: "random.Random | None" = None,
) -> int:
    """Build genome -> XRL seed samples: verbose SNP block -> terse seed.

    The last `holdout` SNPs (file order = magnitude rank) are held out into
    genome_compression_eval.jsonl so compression quality can be measured
    on unseen SNPs. With random_holdout=True the split is a seeded shuffle
    over the full bank instead, mixing magnitudes into eval."""
    genos = _load_genome()
    if holdout and len(genos) > holdout:
        import random
        if random_holdout:
            random.Random(42).shuffle(genos)
        eval_genos = genos[-holdout:]
        genos = genos[:-holdout]
        eval_path = path.with_name("genome_compression_eval.jsonl")
        n_eval = _write_jsonl(eval_path, _genome_samples(eval_genos, chunk))
        logger.info(f"Held out {len(eval_genos)} SNPs -> {n_eval} eval samples")
    samples = _genome_samples(genos, chunk, omit_mag_frac, omit_gt_frac, rng)
    return _write_jsonl(path, samples)


# ── Stage 4: red-thread weaving (fragments -> thread) ─────────────────────────
RED_THREAD_EXAMPLES: list[tuple[list[str], str]] = [
    (
        ["P0 one base many faces", "goal 2.6x compression", "memory recall name"],
        "<XRL-SEED d=3>P0<G>2.6x compression</G>[MEM]recall name<C/>",
    ),
    (
        ["P1 grants not claims", "goal hypermind", "style warm"],
        "<XRL-SEED d=3>P1<G>hypermind</G>[STYLE]warm<C/>",
    ),
]


def _seed_text() -> str:
    return XRLPrincipiaCompiler().compile().to_micro_seed_string()


def seed_text_for_variant(variant: str) -> str:
    """Return the principia seed string for a given variant.

    - micro : principle IDs + goal slugs (~140 chars)
    - terse : principle short-text + goal slugs (~500 chars)
    - full  : full prose seed (principles + goals + derived state)
    """
    seed = XRLPrincipiaCompiler().compile()
    if variant == "terse":
        lines = [f"<XRL-SEED d={seed.degree}>"]
        for k in sorted(seed.principles.keys()):
            lines.append(f"{k}:{seed.principles[k]}")
        slugs = [g.split("::", 1)[-1].strip()[:24] for g in seed.active_goals[:3]]
        lines.append("<G>" + " | ".join(slugs) + "</G><C/>")
        return "\n".join(lines)
    if variant == "full":
        return seed.to_seed_string()
    return seed.to_micro_seed_string()


def build_red_thread(seed_text: str, profile: str, user_prompt: str) -> str:
    return (
        f"{seed_text}\n"
        f"<PROFILE>{profile}</PROFILE>\n"
        f"<USER>{user_prompt}</USER>\n"
        f"<ASSISTANT>"
    )


def _write_jsonl(path: Path, samples: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    return len(samples)


def generate_seed_decode(path: Path, seed_variant: str = "micro") -> int:
    seed_text = seed_text_for_variant(seed_variant)
    samples = []
    for profile, user_prompt, expected in SEED_EXEMPLARS:
        samples.append({
            "text": build_red_thread(seed_text, profile, user_prompt) + "\n" + expected,
            "metadata": {"stage": "seed_decode", "profile": profile, "user": user_prompt, "expected": expected},
        })
    return _write_jsonl(path, samples)


def build_training_corpus(path: Path, seed_variant: str, curriculum: list[str]) -> int:
    """Build a single combined training corpus from selected stages + variant.

    seed_decode is regenerated with `seed_variant`; other stages are copied
    verbatim from the shared corpus. Returns total sample count.
    """
    cdir = CORPUS_DIR
    merged: list[dict[str, Any]] = []

    for stage in curriculum:
        if stage == "seed_decode":
            seed_text = seed_text_for_variant(seed_variant)
            for profile, user_prompt, expected in SEED_EXEMPLARS:
                merged.append({
                    "text": build_red_thread(seed_text, profile, user_prompt) + "\n" + expected,
                    "metadata": {"stage": "seed_decode", "profile": profile, "user": user_prompt, "expected": expected},
                })
            continue
        src = cdir / f"{stage}.jsonl"
        if not src.exists():
            continue
        # genome_compression is huge (3.1k samples); cap it so curriculum
        # mixing inside the evolution loop stays cheap.
        cap = GENOME_CURRICULUM_CAP if stage == "genome_compression" else None
        n_read = 0
        with open(src, "r", encoding="utf-8") as f:
            for line in f:
                if cap is not None and n_read >= cap:
                    break
                line = line.strip()
                if not line:
                    continue
                merged.append(json.loads(line))
                n_read += 1

    return _write_jsonl(path, merged)


def generate_seed_encode(path: Path) -> int:
    samples = []
    for long_ctx, seed in SEED_ENCODE_EXAMPLES:
        samples.append({
            "text": f"<RUBBLE>{long_ctx}</RUBBLE>\n{seed}",
            "metadata": {"stage": "seed_encode"},
        })
    return _write_jsonl(path, samples)


def generate_rubble_to_principa(path: Path) -> int:
    samples = []
    for noise, clean in RUBBLE_EXAMPLES:
        samples.append({
            "text": f"<RUBBLE>{noise}</RUBBLE>\n<PRINCIPA>{clean}</PRINCIPA>",
            "metadata": {"stage": "rubble_to_principa"},
        })
    return _write_jsonl(path, samples)


def generate_red_thread_weaving(path: Path) -> int:
    samples = []
    for fragments, thread in RED_THREAD_EXAMPLES:
        joined = " ".join(fragments)
        samples.append({
            "text": f"<FRAGMENTS>{joined}</FRAGMENTS>\n{thread}",
            "metadata": {"stage": "red_thread_weaving"},
        })
    return _write_jsonl(path, samples)


def generate_full_corpus(corpus_dir: Path | None = None) -> dict[str, int]:
    """Generate all four stage corpora and return per-stage sample counts."""
    cdir = corpus_dir or CORPUS_DIR
    counts = {
        "seed_decode": generate_seed_decode(cdir / "seed_decode.jsonl"),
        "seed_encode": generate_seed_encode(cdir / "seed_encode.jsonl"),
        "rubble_to_principa": generate_rubble_to_principa(cdir / "rubble_to_principa.jsonl"),
        "red_thread_weaving": generate_red_thread_weaving(cdir / "red_thread_weaving.jsonl"),
        "genome_compression": generate_genome_compression(cdir / "genome_compression.jsonl"),
    }
    total = sum(counts.values())
    logger.info(f"Generated {total} samples across {len(counts)} stages -> {cdir}")
    return counts


def generate_nano_dataset(output_path: str, max_examples: int | None = None) -> str:
    """Back-compat: emit the seed_decode corpus to a single path."""
    cdir = CORPUS_DIR
    generate_seed_decode(cdir / "seed_decode.jsonl")
    return str(cdir / "seed_decode.jsonl")


def dataset_stats(output_path: str) -> dict[str, Any]:
    p = Path(output_path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    lines = [l for l in text.splitlines() if l.strip()]
    total_chars = sum(len(l) for l in lines)
    return {
        "samples": len(lines),
        "total_chars": total_chars,
        "avg_chars_per_sample": round(total_chars / len(lines), 1) if lines else 0,
        "bytes": p.stat().st_size if p.exists() else 0,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    counts = generate_full_corpus()
    print(json.dumps(counts, indent=2))
    for name in counts:
        print(name, json.dumps(dataset_stats(str(CORPUS_DIR / f"{name}.jsonl"))))
