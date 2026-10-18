"""
runtime/xrl_codebook_evolution.py — Evolve the Shared Perspective
==================================================================
"Not a smaller model — a shared perspective that makes everything small."

Evolve the universal codebook (the inherited perspective, like DNA's genetic
code) to match the data domain, maximising density with ZERO per-file table
overhead. The genome is a 256-slot frequency vector; the fitness is the mean
compression ratio over a benchmark corpus (repetitive text + real markdown +
your genome) using the SHARED codebook and a fixed 46-byte header.
"""

from __future__ import annotations

import json
import random
import struct
from pathlib import Path
from typing import Any

from runtime.xrl_dense_format import (
    MAGIC,
    VERSION,
    _build_codes,
    _build_tree_from_freq,
    _complement_checksum,
    _pack_bits,
    _universal_freq,
)

HEADER_BYTES = 46  # fixed .xrld header (magic+version+degree+orig_size+checksum)

# ── Corpus ────────────────────────────────────────────────────────────────────

def _benchmark_corpus() -> list[bytes]:
    samples = [
        b"FoveAI Labs compresses semantically. " * 200,
        b"the quick brown fox jumps over the lazy dog " * 50,
        Path("/home/lumba/FoveAI/Plans/Kimi-principia-plan.MD").read_bytes(),
    ]
    g = Path("/home/lumba/FoveAI/Forge/nursery/corpus/genome.jsonl")
    if g.exists():
        samples.append(g.read_bytes()[:200000])  # a real 200KB slice of your genome
    return samples


# ── Genome = frequency vector ────────────────────────────────────────────────

def initial_genome() -> list[int]:
    """Seed from the base universal perspective (all 256 bytes covered)."""
    freq = _universal_freq()
    return [freq.get(b, 1) for b in range(256)]


def genome_to_codes(genome: list[int]) -> dict[int, str]:
    freq = {b: max(1, w) for b, w in enumerate(genome)}
    return _build_codes(_build_tree_from_freq(freq))


def compress_with(codes: dict[int, str], data: bytes) -> bytes:
    bits = "".join(codes[b] for b in data)
    return _pack_bits(bits)


def encode_container(codes: dict[int, str], data: bytes) -> bytes:
    payload = compress_with(codes, data)
    checksum = _complement_checksum(payload)
    header = struct.pack(">4sBBQ32s", MAGIC, VERSION, 0, len(data), checksum)
    return header + payload


def _decode_container(container: bytes, codes: dict[int, str]) -> bytes:
    orig_size = struct.unpack(">Q", container[6:14])[0]
    payload = container[HEADER_BYTES:]
    rev = {v: k for k, v in codes.items()}
    bits = "".join(f"{b:08b}" for b in payload)
    out = bytearray()
    cur = ""
    for ch in bits:
        cur += ch
        if cur in rev:
            out.append(rev[cur])
            cur = ""
            if len(out) >= orig_size:
                break
    return bytes(out)


def fitness(genome: list[int], corpus: list[bytes] | None = None) -> float:
    """Mean compression ratio; hard gate on exact roundtrip."""
    corpus = corpus or _benchmark_corpus()
    codes = genome_to_codes(genome)
    ratios = []
    for data in corpus:
        c = encode_container(codes, data)
        if _decode_container(c, codes) != data:
            return 0.0  # lossless gate failed (shouldn't happen: base freq >= 1)
        ratios.append(len(data) / len(c))
    return round(sum(ratios) / len(ratios), 4)


# ── Evolution ────────────────────────────────────────────────────────────────

def mutate(genome: list[int], rng: random.Random, k: int = 8) -> list[int]:
    g = list(genome)
    for _ in range(k):
        b = rng.randrange(256)
        factor = rng.choice([0.5, 0.75, 1.33, 2.0, 4.0])
        g[b] = max(1, int(g[b] * factor))
    return g


def crossover(a: list[int], b: list[int], rng: random.Random) -> list[int]:
    return [rng.choice([x, y]) for x, y in zip(a, b)]


def evolve(
    generations: int = 6,
    population: int = 12,
    seed: int = 7,
    corpus: list[bytes] | None = None,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    corpus = corpus or _benchmark_corpus()
    pop = [initial_genome() for _ in range(population)]
    log = []

    for gen in range(generations):
        scored = [(fitness(g, corpus), g) for g in pop]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_fit, best_g = scored[0]
        mean_fit = sum(s for s, _ in scored) / len(scored)
        log.append({
            "generation": gen,
            "best_fitness": best_fit,
            "mean_fitness": round(mean_fit, 4),
            "best_genome": best_g,  # stored for wiring back
        })
        print(f"  gen {gen}: best={best_fit:.4f} mean={mean_fit:.4f}")

        if gen == generations - 1:
            break
        elite = [g for _, g in scored[: population // 2]]
        new_pop = []
        while len(new_pop) < population:
            a = rng.choice(elite)
            b = rng.choice(elite)
            child = crossover(a, b, rng) if rng.random() < 0.7 else mutate(a, rng)
            new_pop.append(child)
        pop = new_pop

    return log


if __name__ == "__main__":
    corpus = _benchmark_corpus()
    print("corpus samples:", [len(c) for c in corpus])

    print("\n== baseline (universal English codebook) ==")
    print("fitness:", fitness(initial_genome(), corpus))

    print("\n== codebook evolution ==")
    log = evolve(corpus=corpus)

    best = log[-1]["best_genome"]
    # save the evolved perspective
    out = Path("/home/lumba/FoveAI/Forge/nursery/corpus/evolved_codebook.json")
    out.write_text(json.dumps(best))
    print(f"\n[saved] evolved codebook -> {out}")

    # verify a roundtrip with the best genome
    codes = genome_to_codes(best)
    for c in corpus[:2]:
        enc = encode_container(codes, c)
        assert _decode_container(enc, codes) == c
    print("roundtrip verified on 2 samples")
