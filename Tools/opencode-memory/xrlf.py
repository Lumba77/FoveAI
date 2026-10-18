#!/usr/bin/env python3
"""XRLF seed packets - pack/unpack seed payloads using the lzssv+huff stack.

Layout (descendant of old XRLD: magic + ver/flags + dense payload):
  magic   "XRLF"  (4)
  ver     u8 = 1
  flags   u8     bit0 payload packed (lzssv+huff), bit1 payload = seed-members JSON
  name    varint len + utf8   (packet name)
  orig    varint             (uncompressed payload size)
  crc     u16 (fnv-1a mod 65536 of raw payload)
  payload                    (packed or raw)
"""
import json
import os
import sys

MAGIC = b"XRLF"
F_PACKED = 1
F_SEEDJSON = 2

import huff
import lzssv


def _venc(v, out):
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | 0x80 if v else b)
        if not v:
            break


def _vdec(d, p):
    v = s = 0
    while True:
        b = d[p]
        p += 1
        v |= (b & 0x7F) << s
        if not b & 0x80:
            return v, p
        s += 7


def _crc(raw):
    h = 0x811C9DC5
    for b in raw:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    v = 0
    for i in range(4):
        v = (v * 31 + ((h >> (i * 8)) & 0xFF)) & 0xFFFF
    return v


def pack(name, raw, packed=True, seed_json=False):
    if isinstance(raw, str):
        raw = raw.encode()
    flags = 0
    body = raw
    if packed:
        flags |= F_PACKED
        body = huff.encode(lzssv.encode(raw))
    if seed_json:
        flags |= F_SEEDJSON
    out = bytearray(MAGIC)
    out.append(1)
    out.append(flags)
    _venc(len(name.encode()), out)
    out.extend(name.encode())
    _venc(len(raw), out)
    c = _crc(raw)
    out += c.to_bytes(2, "little")
    out.extend(body)
    return bytes(out)


def unpack(blob):
    assert blob[:4] == MAGIC, "not an XRLF packet"
    ver = blob[4]
    assert ver == 1, f"unsupported XRLF version {ver}"
    flags = blob[5]
    nl, p = _vdec(blob, 6)
    name = blob[p:p + nl].decode()
    p += nl
    orig, p = _vdec(blob, p)
    crc = int.from_bytes(blob[p:p + 2], "little")
    p += 2
    body = blob[p:]
    if flags & F_PACKED:
        raw = lzssv.decode(huff.decode(body))
    else:
        raw = body
    assert len(raw) == orig, "size mismatch"
    assert _crc(raw) == crc, "crc mismatch (corrupt packet)"
    meta = {"ver": ver, "flags": flags, "name": name, "orig": orig}
    return name, raw, meta


def main(argv):
    LEDGER = "/tmp/opencode/seed_ledger.jsonl"
    PKTDIR = "/tmp/opencode/packets"
    if argv and argv[0] == "make":
        names = argv[1:] or ["lark aquifer"]
        os.makedirs(PKTDIR, exist_ok=True)
        entries = [json.loads(l) for l in open(LEDGER)]
        for nm in names:
            sel = [e for e in entries if e["name"].lower() == nm.lower()]
            if not sel:
                print(f"[xrlf] no member named {nm!r} in the ledger")
                continue
            raw = "\n".join(json.dumps(e, separators=(",", ":"))
                            for e in sel).encode()
            pk = pack(f"seed:{nm}", raw, seed_json=True)
            out = os.path.join(PKTDIR, nm.replace(" ", "_") + ".xrlf")
            open(out, "wb").write(pk)
            n, back, meta = unpack(pk)
            assert back == raw
            print(f"[xrlf] {nm:16s} {len(raw):5d}B -> {len(pk):4d}B "
                  f"({len(raw)/len(pk):6.1f}x) rt=OK -> {out}")
        return
    for path in argv or [PKTDIR]:
        if os.path.isdir(path):
            for fn in sorted(os.listdir(path)):
                main([os.path.join(path, fn)])
            continue
        blob = open(path, "rb").read()
        name, raw, meta = unpack(blob)
        tags = []
        if meta["flags"] & F_SEEDJSON:
            tags.append(f"{len(raw.splitlines())} seed-entries")
        print(f"[xrlf] {path}: '{name}' {meta['orig']}B raw -> "
              f"{len(blob)}B packet ({meta['orig']/len(blob):.1f}x) "
              f"{' | '.join(tags)}")


if __name__ == "__main__":
    main(sys.argv[1:])