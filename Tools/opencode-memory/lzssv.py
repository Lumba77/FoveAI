#!/usr/bin/env python3
"""LZSS-varint: the evolved dictionary layer for XRLF streams (note-180 step 2).

Token stream (all lengths LE-varint, MIN_MATCH=4):
  literal run : varint((run_len-1)*2 + 0)  followed by run bytes
  match       : varint((len-MIN_MATCH)*2 + 1)  then varint(offset-1)

Greedy encoder, hash table on 4-byte heads, bounded chain, window 256K.
Decoder is ~20 lines, no dictionary state, embeddable.

Usage: python lzssv.py encode|decode IN OUT
       python lzssv.py bench
"""
import struct
import sys

W_BITS = 18                     # 256K window
W = 1 << W_BITS
MIN_MATCH = 4
MAX_CHAIN = 24
MAGIC = b"LZSSV"


def _venc(n, out):
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def _vdec(buf, pos):
    n = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, pos
        shift += 7


def encode(data, lazy=True):
    out = bytearray(MAGIC + struct.pack("<I", len(data)))
    n = len(data)
    heads = {}

    def look(i):
        if i + MIN_MATCH > n:
            return 0, 0
        chain = heads.get(data[i:i + MIN_MATCH])
        if not chain:
            return 0, 0
        limit = i - W
        best_l = best_o = 0
        tried = 0
        for j in reversed(chain):
            if j < limit:
                break
            if tried >= MAX_CHAIN:
                break
            tried += 1
            l = MIN_MATCH
            maxl = n - i
            while l < maxl and data[j + l] == data[i + l]:
                l += 1
            if l > best_l:
                best_l, best_o = l, i - j
                if best_l >= 64:
                    break
        return best_l, best_o

    def run(s, e):
        if e > s:
            _venc((e - s - 1) * 2, out)
            out.extend(data[s:e])

    def mtok(ln, off):
        _venc((ln - MIN_MATCH) * 2 + 1, out)
        _venc(off - 1, out)

    i = 0
    lit_start = 0
    pend = False
    pl = po = 0
    while i < n:
        ln, off = look(i)
        hk = data[i:i + MIN_MATCH]
        if len(hk) == MIN_MATCH:
            heads.setdefault(hk, []).append(i)
        if pend:
            if ln > pl:
                pl, po = ln, off    # better match here; pending pos -> literal
                i += 1
                continue
            e = i - 1
            run(lit_start, e)
            for k in range(e + 1, e + pl):
                hk2 = data[k:k + MIN_MATCH]
                if len(hk2) == MIN_MATCH:
                    heads.setdefault(hk2, []).append(k)
            mtok(pl, po)
            i = e + pl
            lit_start = i
            pend = False
        elif ln >= MIN_MATCH and lazy:
            pl, po = ln, off
            pend = True
            i += 1
        elif ln >= MIN_MATCH:
            run(lit_start, i)
            for k in range(i + 1, i + ln):
                hk2 = data[k:k + MIN_MATCH]
                if len(hk2) == MIN_MATCH:
                    heads.setdefault(hk2, []).append(k)
            mtok(ln, off)
            i += ln
            lit_start = i
        else:
            i += 1
    if pend:
        e = i - 1
        run(lit_start, e)
        mtok(pl, po)
    else:
        run(lit_start, n)
    return bytes(out)


def decode(buf):
    if buf[:5] != MAGIC:
        raise ValueError("bad magic")
    (n,) = struct.unpack_from("<I", buf, 5)
    pos = 9
    out = bytearray()
    while len(out) < n:
        tok, pos = _vdec(buf, pos)
        if tok & 1:
            ln = (tok >> 1) + MIN_MATCH
            off, pos = _vdec(buf, pos)
            off += 1
            start = len(out) - off
            for k in range(ln):
                out.append(out[start + k])
        else:
            m = (tok >> 1) + 1
            out.extend(buf[pos:pos + m])
            pos += m
    return bytes(out[:n])


def bench():
    import time
    import zlib
    for path in ["/tmp/opencode/seed_ledger.jsonl",
                 "/tmp/opencode/kqat_corpus.jsonl"]:
        d = open(path, "rb").read()
        t0 = time.time()
        e = encode(d)
        t1 = time.time()
        ok = decode(e) == d
        z = zlib.compress(d, 9)
        print(f"{path.split('/')[-1]:22s} {len(d)/1e3:8.1f}KB -> "
              f"{len(e)/1e3:8.1f}KB ({len(d)/len(e):5.2f}x) "
              f"| zlib {len(z)/1e3:8.1f}KB ({len(d)/len(z):5.2f}x) "
              f"| enc {t1-t0:4.1f}s rt={ok}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "bench"
    if cmd == "encode":
        open(sys.argv[3], "wb").write(encode(open(sys.argv[2], "rb").read()))
    elif cmd == "decode":
        open(sys.argv[3], "wb").write(decode(open(sys.argv[2], "rb").read()))
    else:
        bench()