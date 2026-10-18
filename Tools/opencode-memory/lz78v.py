#!/usr/bin/env python3
"""LZ78 + LEB128-varint codec for XRLF weight streams.

Canonical LZ78: dictionary of phrases built during encode; each token is
(parent_index, next_byte). We varint the parent index (LEB128) and emit the
raw next byte. Decoder rebuilds the same dictionary from scratch, no
dictionary in the file. This is the "dictionary layer" from note 180.

Usage: python lz78v.py encode|decode IN OUT
       python lz78v.py bench SLICE_MB   (benchmarks on kqatt code streams)
"""
import json
import struct
import sys

MAGIC = b"LZ78V"


def varint_enc(n, out):
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def varint_dec(buf, pos):
    n = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, pos
        shift += 7


def encode(data):
    """Returns compressed bytes."""
    out = bytearray(MAGIC + struct.pack("<I", len(data)))
    # canonical LZ78: dict maps (parent, byte) -> index; phrases[i] = bytes
    phrases = {}
    children = {}          # (parent_idx, byte) -> phrase idx
    parent = 0             # 0 = root
    for b in data:
        key = (parent, b)
        nxt = children.get(key)
        if nxt is not None:
            parent = nxt
            continue
        # emit token: varint(parent) + byte
        varint_enc(parent, out)
        out.append(b)
        idx = len(phrases) + 1
        phrases[idx] = None
        children[key] = idx
        parent = 0
    if parent:
        varint_enc(parent, out)
    return bytes(out)


def decode(buf):
    if buf[:5] != MAGIC:
        raise ValueError("bad magic")
    (n,) = struct.unpack_from("<I", buf, 5)
    pos = 9
    root = b""
    phrases = [root]        # index 0 = empty; children dict below
    children = {}
    out = bytearray()
    cur = 0
    while pos < len(buf) and len(out) < n:
        p, pos = varint_dec(buf, pos)
        b = buf[pos]
        pos += 1
        if cur:
            emit = 0
        else:
            emit = 0
        # flush pending phrase first
        if cur:
            out.extend(phrases[cur] if isinstance(phrases[cur], bytes)
                       else root)
            cur = 0
        # rebuild
        base = phrases[p] if p else b""
        s = base + bytes([b])
        idx = len(phrases)
        phrases.append(s)
        children[(p, b)] = idx
        out.extend([b])
        # LZ78 semantics: out emits phrase walk; we stream as we go
        cur = idx
    if cur:
        out.extend(phrases[cur])
    return bytes(out[:n])


class Tokenizer:
    """Streaming encoder that flushes a phrase per token (canonical)."""
    pass


def encode_v2(data):
    """Faster array-based encoder; same format as encode()."""
    out = bytearray(MAGIC + struct.pack("<I", len(data)))
    children = {}
    parent = 0
    append = out.append
    get = children.get
    for b in data:
        k = (parent << 8) | b
        nxt = get(k, 0)
        if nxt:
            parent = nxt
            continue
        varint_enc(parent, out)
        append(b)
        children[k] = len(children) + 1
        parent = 0
    if parent:
        varint_enc(parent, out)
    return bytes(out)


def decode_v2(buf):
    if buf[:5] != MAGIC:
        raise ValueError("bad magic")
    (n,) = struct.unpack_from("<I", buf, 5)
    pos = 9
    sizes = [0]              # phrase length per index
    back = [0]               # parent index per phrase
    lastb = [0]
    children = {}
    out = bytearray()
    # LZ78 streaming decode: when we get (p, b), the phrase p's full bytes
    # should be emitted, followed by b; then phrase (p,b) registered.
    # Build via back-pointers, emit on flush.
    pending = []

    def phrase_bytes(idx):
        # resolve iteratively (back pointers)
        stack = []
        while idx:
            stack.append(lastb[idx])
            idx = back[idx]
        return bytes(reversed(stack))

    while pos < len(buf) and len(out) < n:
        p, pos = varint_dec(buf, pos)
        if pos >= len(buf):
            # bare trailing parent token: flush phrase, done
            if p:
                out.extend(phrase_bytes(p))
            break
        b = buf[pos]
        pos += 1
        if p:
            out.extend(phrase_bytes(p))
        out.append(b)
        idx = len(sizes)
        back.append(p)
        lastb.append(b)
        sizes.append((sizes[p] if p else 0) + 1)
        children[(p << 8) | b] = idx
        if len(out) >= n:
            break
    return bytes(out[:n])


def bench():
    import time
    import zlib
    import zipfile
    import numpy as np
    import safetensors.torch as st

    f = st.load_file("/tmp/opencode/kqat/weights_k4.safetensors")
    targets = []
    for k in list(f):
        if k.startswith("q::"):
            targets.append((k, f[k].numpy().tobytes()))
    targets.sort(key=lambda t: -len(t[1]))
    total_raw = sum(len(t[1]) for t in targets)
    print(f"[bench] {len(targets)} code streams, raw total {total_raw/1e6:.1f} MB")

    # demo on redundant data first (sanity, note-180 target ~4x)
    demo = (b"the quick brown fox " * 5000)
    e = encode_v2(demo)
    print(f"[demo] redundant data: {len(demo)} -> {len(e)} "
          f"({len(demo)/len(e):.1f}x)")

    MB = int(sys.argv[2]) * 1_000_000 if len(sys.argv) > 2 else 1_000_000
    rows = []
    acc_e = acc_z = 0
    t0 = time.time()
    for k, raw in targets[:6]:
        raw_s = raw[:MB]
        t1 = time.time()
        e = encode_v2(raw_s)
        dt = time.time() - t1
        zc = zlib.compress(raw_s, 9)
        acc_e += len(e)
        acc_z += len(zc)
        rows.append((k, len(raw_s), len(e), len(zc), dt))
        print(f"  {k[3:][:46]:46s} {len(raw_s)/1e6:6.2f}MB -> "
              f"{len(e)/1e6:6.3f}MB ({len(raw_s)/len(e):5.2f}x) | "
              f"zlib {len(zc)/1e6/len(raw_s)*1e6/1e6:5.3f}MB "
              f"({len(raw_s)/len(zc):4.2f}x) | {dt:4.1f}s")
    print(f"[bench] slice subtotal ({MB/1e6:.0f}MB/stream): "
          f"lz78v {acc_e/1e6:.2f}MB, zlib {acc_z/1e6:.2f}MB, "
          f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "bench"
    if cmd == "encode":
        open(sys.argv[3], "wb").write(encode_v2(open(sys.argv[2], "rb").read()))
    elif cmd == "decode":
        open(sys.argv[3], "wb").write(decode_v2(open(sys.argv[2], "rb").read()))
    else:
        bench()