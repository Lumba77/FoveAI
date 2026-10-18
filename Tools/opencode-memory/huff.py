#!/usr/bin/env python3
"""Canonical byte-Huffman post-pass (note-180 step 3, ceiling ~1.3x).

Sits on lzssv varint token streams (or any byte stream). Format:
  magic "HUFF1" + 4B raw length + 128B table of 4-bit code lengths
  (symbols 0..255) + bit-packed codes (LSB-first, streamable decode by
  width-walk over canonical first-codes).

Usage: python huff.py encode|decode IN OUT
       python huff.py bench   (lzssv vs lzssv+huff vs zlib on seed data)
"""
import heapq
import struct
import sys

MAGIC = b"HUFF1"
TABLE_END = 9 + 128             # stream data starts here


def _encode_lengths(data):
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    heap = [(freq[s], idx, s, None, None)
            for idx, s in enumerate(s for s in range(256) if freq[s])]
    if not heap:
        return [0] * 256
    if len(heap) == 1:
        lens = [0] * 256
        lens[heap[0][2]] = 1
        return lens
    heapq.heapify(heap)
    tie = 256
    while len(heap) > 1:
        w1, _, sym1, a1, b1 = heapq.heappop(heap)
        w2, _, sym2, a2, b2 = heapq.heappop(heap)
        heapq.heappush(heap, (w1 + w2, tie, None,
                              (sym1, a1, b1), (sym2, a2, b2)))
        tie += 1
    lens = [0] * 256
    root = heap[0]              # 5-tuple (w, tie, sym=None, left, right)
    stack = [(root[3], 1), (root[4], 1)]
    while stack:
        node, depth = stack.pop()
        sym, a, b = node
        if sym is not None:
            lens[sym] = max(depth, 1)
        else:
            stack.append((a, depth + 1))
            stack.append((b, depth + 1))
    if max(lens) > 15:
        raise ValueError("code length overflow (unrealistic for our sizes)")
    return lens


def _canonical_codes(lens):
    """RFC1951 next_code recurrence; symbol order within each length."""
    bl_count = [0] * 16
    for l in lens:
        if l:
            bl_count[l] += 1
    code = 0
    next_code = [0] * 16
    for bits in range(1, 16):
        code = (code + bl_count[bits - 1]) << 1
        next_code[bits] = code
    codes = [0] * 256
    for s in sorted(range(256), key=lambda s: (lens[s], s)):
        if lens[s]:
            codes[s] = next_code[lens[s]]
            next_code[lens[s]] += 1
    return codes


def encode(data):
    lens = _encode_lengths(data)
    codes = _canonical_codes(lens)
    hdr = bytearray(128)
    for s in range(256):
        hdr[s >> 1] |= lens[s] << (4 * (s & 1))
    out = bytearray(MAGIC + struct.pack("<I", len(data)) + hdr)
    rev = [(0, 0)] * 256
    for b in range(256):
        if lens[b]:
            c, l = codes[b], lens[b]
            r = 0
            for _ in range(l):
                r = (r << 1) | (c & 1)
                c >>= 1
            rev[b] = (r, l)
    acc = 0
    nbits = 0
    for b in data:
        r, l = rev[b]
        acc |= r << nbits
        nbits += l
        while nbits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nbits -= 8
    if nbits:
        out.append(acc & 0xFF)
    return bytes(out)


def decode(buf):
    if buf[:5] != MAGIC:
        raise ValueError("bad magic")
    (n,) = struct.unpack_from("<I", buf, 5)
    hdr = buf[9:137]
    lens = [(hdr[s >> 1] >> (4 * (s & 1))) & 0xF for s in range(256)]
    by_len = {}
    for s in range(256):
        if lens[s]:
            by_len.setdefault(lens[s], []).append(s)
    # canonical first codes per width
    bl_count = {w: len(v) for w, v in by_len.items()}
    code = 0
    first = {}
    for bits in range(1, 16):
        code = (code + bl_count.get(bits - 1, 0)) << 1
        if bits in bl_count:
            first[bits] = (code, bl_count[bits])
    out = bytearray()
    acc = 0
    nbits = 0
    pos = TABLE_END
    end = len(buf)
    cur_code = 0
    cur_bits = 0
    while len(out) < n:
        # feed a bit
        if nbits == 0:
            if pos >= end:
                break
            acc = buf[pos]
            pos += 1
            nbits = 8
        bit = acc & 1
        acc >>= 1
        nbits -= 1
        cur_code = (cur_code << 1) | bit
        cur_bits += 1
        if cur_bits in first:
            fc, cnt = first[cur_bits]
            if fc <= cur_code < fc + cnt:
                # symbol index: canonical order = within-length symbol order
                out.append(by_len[cur_bits][cur_code - fc])
                cur_code = 0
                cur_bits = 0
    return bytes(out[:n])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "bench"
    if cmd == "encode":
        open(sys.argv[3], "wb").write(encode(open(sys.argv[2], "rb").read()))
    elif cmd == "decode":
        open(sys.argv[3], "wb").write(decode(open(sys.argv[2], "rb").read()))
    else:
        import time
        import zlib
        import lzssv
        for path in ["/tmp/opencode/seed_ledger.jsonl",
                     "/tmp/opencode/kqat_corpus.jsonl"]:
            d = open(path, "rb").read()
            e = lzssv.encode(d)
            t0 = time.time()
            eh = encode(e)
            t1 = time.time()
            full_ok = decode(eh) == e and lzssv.decode(e) == d
            z = zlib.compress(d, 9)
            print(f"{path.split('/')[-1]:22s} {len(d)/1e3:8.1f}KB -> "
                  f"huff(lzssv) {len(eh)/1e3:7.1f}KB ({len(d)/len(eh):5.2f}x) "
                  f"| lzssv {len(e)/1e3:7.1f}KB ({len(d)/len(e):5.2f}x) "
                  f"| zlib {len(z)/1e3:7.1f}KB ({len(d)/len(z):5.2f}x) "
                  f"| rt={full_ok} huff-enc {t1-t0:4.1f}s")