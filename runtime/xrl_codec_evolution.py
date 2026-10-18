"""
runtime/xrl_codec_evolution.py — Evolutionary Codec Search
==========================================================
Use evolutionary principles to iterate a technique for coding/decoding
condensed data. We evolve the *codec parameters* (symbol alphabet, chunking,
degree) to maximise information density, measured as compression ratio.

Genome  : {alphabet, chunk, degree}
Fitness : mean compression ratio over a benchmark corpus (lossless roundtrip
          is a hard gate — any genome that fails decode gets fitness 0).

The search is fast (pure Python, small corpus) and produces a measurable
fitness curve, exactly like the nano-model evolution loop.
"""

from __future__ import annotations

import heapq
import json
import struct
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Any


# ── Symbolization (alphabet choice) ──────────────────────────────────────────

def symbolize(data: bytes, alphabet: str) -> list[int]:
    """Split bytes into symbols under a chosen alphabet."""
    if alphabet == "nibble":
        out = []
        for b in data:
            out.append(b >> 4)
            out.append(b & 0x0F)
        return out
    if alphabet == "bigram":
        out = []
        for i in range(0, len(data), 2):
            hi = data[i]
            lo = data[i + 1] if i + 1 < len(data) else 0
            out.append((hi << 8) | lo)
        return out
    if alphabet == "word":
        # split on whitespace into variable-length tokens (bytes as words)
        out = []
        cur = b""
        for b in data:
            if b in (32, 10, 9):  # space/newline/tab
                if cur:
                    out.append(int.from_bytes(cur, "big"))
                    cur = b""
                out.append(b)
            else:
                cur += bytes([b])
        if cur:
            out.append(int.from_bytes(cur, "big"))
        return out
    return list(data)  # byte


def desymbolize(syms: list[int], alphabet: str, n_bytes: int) -> bytes:
    """Reconstruct bytes from symbols (lossless modes only)."""
    if alphabet == "nibble":
        out = bytearray()
        for i in range(0, len(syms), 2):
            hi = syms[i]
            lo = syms[i + 1] if i + 1 < len(syms) else 0
            out.append((hi << 4) | lo)
        return bytes(out[:n_bytes])
    if alphabet == "bigram":
        out = bytearray()
        for s in syms:
            out.append((s >> 8) & 0xFF)
            out.append(s & 0xFF)
        return bytes(out[:n_bytes])
    if alphabet == "word":
        # join words with single spaces (lossy-ish; only used in degree>0 demos)
        return b" ".join(s.to_bytes((s.bit_length() + 7) // 8, "big") for s in syms if s > 32)[:n_bytes]
    return bytes(syms)[:n_bytes]


# ── Huffman over integer symbols ─────────────────────────────────────────────

def _build_codes(freq: dict[int, int]) -> dict[int, str]:
    heap = [[f, i, sym, ""] for i, (sym, f) in enumerate(freq.items())]
    heapq.heapify(heap)
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        for node in (a, b):
            pass
        # a gets 0 prefix, b gets 1 prefix
        _prepend(a, "0")
        _prepend(b, "1")
        merged = [a[0] + b[0], a[1]] + a[2:] + b[2:]
        heapq.heappush(heap, merged)
    root = heap[0]
    # root is flat: [freq, idx, sym1, bits1, sym2, bits2, ...]
    return {root[i]: root[i + 1] for i in range(2, len(root), 2)}


def _prepend(node, prefix):
    for i in range(3, len(node), 2):
        node[i] = prefix + node[i]


def _pack(bitstring: str) -> bytes:
    bitstring += "0" * ((8 - len(bitstring) % 8) % 8)
    return bytes(int(bitstring[i:i + 8], 2) for i in range(0, len(bitstring), 8))


def _unpack(payload: bytes) -> str:
    return "".join(f"{b:08b}" for b in payload)


def huffman_encode(syms: list[int]) -> tuple[bytes, dict[int, str]]:
    codes = _build_codes(Counter(syms))
    bits = "".join(codes[s] for s in syms)
    return _pack(bits), codes


def huffman_decode(payload: bytes, codes: dict[int, str], n_syms: int) -> list[int]:
    rev = {v: k for k, v in codes.items()}
    bits = _unpack(payload)
    out = []
    cur = ""
    for ch in bits:
        cur += ch
        if cur in rev:
            out.append(rev[cur])
            cur = ""
            if len(out) >= n_syms:
                break
    return out


# ── Degeneracy (lossy degree) ────────────────────────────────────────────────

def collapse(syms: list[int], degree: int) -> list[int]:
    if degree <= 0:
        return syms
    freq = Counter(syms)
    ordered = [s for s, _ in freq.most_common()]
    cut = max(1, len(ordered) - degree * max(1, len(ordered) // 8))
    tail = set(ordered[cut:])
    anchor = ordered[0]
    return [anchor if s in tail else s for s in syms]


# ── Genome + codec ───────────────────────────────────────────────────────────

@dataclass
class Genome:
    alphabet: str = "byte"   # nibble | byte | bigram | word
    chunk: int = 0           # 0 = global table, else symbols per chunk
    degree: int = 0          # 0 = lossless

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _encode_symbols(syms: list[int], chunk: int) -> tuple[bytes, list[dict], list[list[int]]]:
    """Encode symbols, optionally chunked into per-block Huffman tables.

    Returns (payload, code_tables, chunk_specs) where chunk_specs is a list of
    [payload_len, sym_count] per block.
    """
    if chunk <= 0:
        payload, codes = huffman_encode(syms)
        return payload, [codes], [[len(payload), len(syms)]]

    payloads = []
    code_tables = []
    specs = []
    for i in range(0, len(syms), chunk):
        block = syms[i:i + chunk]
        p, codes = huffman_encode(block)
        payloads.append(p)
        code_tables.append(codes)
        specs.append([len(p), len(block)])
    return b"".join(payloads), code_tables, specs


def _decode_symbols(payload: bytes, code_tables: list[dict], specs: list[list[int]]) -> list[int]:
    if len(code_tables) == 1:
        _, n_syms = specs[0]
        return huffman_decode(payload, code_tables[0], n_syms)
    out = []
    off = 0
    for codes, (plen, n_syms) in zip(code_tables, specs):
        block = huffman_decode(payload[off:off + plen], codes, n_syms)
        out.extend(block)
        off += plen
    return out


def compress(data: bytes, genome: Genome) -> bytes:
    """Compress data into a self-describing container."""
    syms = symbolize(data, genome.alphabet)
    if genome.degree > 0:
        syms = collapse(syms, genome.degree)

    payload, tables, specs = _encode_symbols(syms, genome.chunk)

    meta = {
        "alphabet": genome.alphabet,
        "chunk": genome.chunk,
        "degree": genome.degree,
        "n_bytes": len(data),
        "n_syms": len(syms),
        "tables": [{str(k): v for k, v in t.items()} for t in tables],
        "specs": specs,
    }
    meta_json = json.dumps(meta).encode("utf-8")
    header = struct.pack(">II", len(meta_json), len(payload))
    return header + meta_json + payload


def decompress(container: bytes) -> bytes:
    meta_len, payload_len = struct.unpack(">II", container[:8])
    meta_json = container[8:8 + meta_len]
    payload = container[8 + meta_len:8 + meta_len + payload_len]
    meta = json.loads(meta_json.decode("utf-8"))

    alphabet = meta["alphabet"]
    n_syms = meta["n_syms"]
    n_bytes = meta["n_bytes"]
    tables = [{int(k): v for k, v in t.items()} for t in meta["tables"]]
    specs = meta["specs"]

    syms = _decode_symbols(payload, tables, specs)
    return desymbolize(syms[:n_syms], alphabet, n_bytes)


# ── Benchmark corpus ─────────────────────────────────────────────────────────

def _benchmark_corpus() -> list[bytes]:
    samples = [
        b"FoveAI Labs compresses semantically. " * 200,          # repetitive
        (b"the quick brown fox jumps over the lazy dog " * 50),  # repeated words
        open("/home/lumba/FoveAI/Plans/Kimi-principia-plan.MD", "rb").read(),  # real text
    ]
    return samples


def fitness(genome: Genome, corpus: list[bytes] | None = None) -> float:
    """Mean compression ratio; hard gate on lossless roundtrip."""
    corpus = corpus or _benchmark_corpus()
    ratios = []
    for data in corpus:
        try:
            c = compress(data, genome)
            if genome.degree == 0:
                d = decompress(c)
                if d != data:
                    return 0.0  # lossless gate failed
            ratios.append(len(data) / max(1, len(c)))
        except Exception:
            return 0.0
    return round(sum(ratios) / len(ratios), 4)


# ── Evolutionary search ──────────────────────────────────────────────────────

ALPHABETS = ["nibble", "byte", "bigram"]
CHUNKS = [0, 64, 256, 1024]


def random_genome() -> Genome:
    import random
    return Genome(
        alphabet=random.choice(ALPHABETS),
        chunk=random.choice(CHUNKS),
        degree=0,
    )


def mutate(g: Genome) -> Genome:
    import random
    ng = Genome(g.alphabet, g.chunk, g.degree)
    if random.random() < 0.5:
        ng.alphabet = random.choice(ALPHABETS)
    if random.random() < 0.5:
        ng.chunk = random.choice(CHUNKS)
    return ng


def crossover(a: Genome, b: Genome) -> Genome:
    import random
    return Genome(
        alphabet=random.choice([a.alphabet, b.alphabet]),
        chunk=random.choice([a.chunk, b.chunk]),
        degree=0,
    )


def evolve(generations: int = 4, population: int = 8, seed: int = 1) -> list[dict]:
    import random
    rng = random.Random(seed)
    corpus = _benchmark_corpus()
    pop = [random_genome() for _ in range(population)]
    log = []

    for gen in range(generations):
        scored = []
        for g in pop:
            scored.append((fitness(g, corpus), g))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_fit, best_g = scored[0]
        mean_fit = sum(s for s, _ in scored) / len(scored)
        log.append({
            "generation": gen,
            "best_fitness": best_fit,
            "mean_fitness": round(mean_fit, 4),
            "best_genome": best_g.to_dict(),
        })

        if gen == generations - 1:
            break
        elite = [g for _, g in scored[:population // 2]]
        new_pop = []
        while len(new_pop) < population:
            a = rng.choice(elite)
            b = rng.choice(elite)
            child = crossover(a, b) if rng.random() < 0.7 else mutate(a)
            new_pop.append(child)
        pop = new_pop

    return log


if __name__ == "__main__":
    corpus = _benchmark_corpus()
    print("== baseline (byte, global, lossless) ==")
    base = Genome("byte", 0, 0)
    print("fitness:", fitness(base, corpus))

    log = evolve()
    print("\n== evolution ==")
    for e in log:
        g = e["best_genome"]
        print(f"  gen {e['generation']}  best={e['best_fitness']:.4f} "
              f"mean={e['mean_fitness']}  {g}")

    # ── "No size, only perspective" demonstration ────────────────────────────
    print("\n" + "=" * 60)
    print("  NO SIZE, ONLY PERSPECTIVE")
    print("=" * 60)
    # A shared codebook (perspective) built once — a *universal* perspective
    # covering all 256 bytes, with frequencies learned from a training corpus.
    # This is the analog of DNA's inherited genetic code: never transmitted.
    freq = Counter({b: 1 for b in range(256)})  # base: every byte has a code
    freq.update(symbolize(corpus[0] + corpus[1], "byte"))  # learn perspective
    codebook = _build_codes(freq)

    for label, data in [("repetitive", corpus[0]), ("markdown", corpus[2])]:
        syms = symbolize(data, "byte")
        # Fixed perspective: payload only, no table shipped.
        bits = "".join(codebook[s] for s in syms)
        fixed_payload = _pack(bits)
        # Reconstruct from the shared perspective.
        back = huffman_decode(fixed_payload, codebook, len(syms))
        tangible = desymbolize(back, "byte", len(data)) == data

        # Adaptive perspective: table shipped WITH the payload.
        c = compress(data, Genome("byte", 0, 0))

        print(f"\n  [{label}] data is tangible: {tangible}")
        print(f"    fixed perspective  : {len(fixed_payload):>6} bytes "
              f"({len(data)/len(fixed_payload):.2f}x smaller)")
        print(f"    adaptive (table+s) : {len(c):>6} bytes "
              f"({len(data)/len(c):.2f}x smaller)")
        print(f"    perspective cost   : {len(c) - len(fixed_payload):>6} bytes "
              f"(the codebook we keep transmitting)")
