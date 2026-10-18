#!/usr/bin/env python3
"""Pack collegium v1 - the whole swarm into one single file (nova.collegium)."""
import json
import os
import sys
import zipfile

PAWN = "/tmp/opencode/k6_pawn"
KNIGHT = "/tmp/opencode/k6_knight"
LEDGER = "/tmp/opencode/seed_ledger.jsonl"
OUT = "/tmp/opencode/nova.collegium"
SKIP = {"checkpoints"}


def add_dir(z, d, arc):
    for fn in sorted(os.listdir(d)):
        if fn in SKIP:
            continue
        p = os.path.join(d, fn)
        if os.path.isfile(p):
            z.write(p, f"{arc}/{fn}")


def main():
    manifest = {"name": "nova", "version": 1,
                "members": {"pawn": {"role": "reader - seed copy / decisions"},
                            "knight": {"role": "binder - answer -> goal judgment"}}}
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=1))
        z.write(LEDGER, "ledger.jsonl")
        add_dir(z, PAWN, "pawn")
        add_dir(z, KNIGHT, "knight")
    print(f"[ok] {OUT} ({os.path.getsize(OUT) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()

def main_v4():
    """v4: kqatt pawn + lz-compressed ledger (lzssv+huff -> ledger.jsonl.lzs)."""
    import huff
    import lzssv
    OUTV4 = "/tmp/opencode/nova_kqatt_lz.collegium"
    manifest = {"name": "nova", "version": 4,
                "ledger_codec": "lzssv+huff1 (decode: huff.decode -> lzssv.decode)",
                "members": {
                    "pawn": {"role": "reader - seed copy / decisions",
                             "build": "kqatt QAT 82MB (attn8/ffn3/emb6)"},
                    "knight": {"role": "binder - answer -> goal judgment",
                               "build": "k6 6-bit 137MB"}}}
def main_v4(vers=5):
    """v4/v5: kqatt pawn + lz-compressed ledger (lzssv+huff -> ledger.jsonl.lzs)."""
    import huff
    import lzssv
    OUTV4 = f"/tmp/opencode/nova_kqatt_lz_v{vers}.collegium"
    manifest = {"name": "nova", "version": vers,
                "ledger_codec": "lzssv+huff1 (decode: huff.decode -> lzssv.decode)",
                "members": {
                    "pawn": {"role": "reader - seed copy / decisions",
                             "build": "kqatt QAT 82MB (attn8/ffn3/emb6)"},
                    "knight": {"role": "binder - answer -> goal judgment",
                               "build": "k6 6-bit 137MB"}}}
    led = open(LEDGER, "rb").read()
    packed = huff.encode(lzssv.encode(led))
    print(f"[v{vers}] ledger {len(led)/1e3:.0f}KB -> {len(packed)/1e3:.1f}KB "
          f"({len(led)/len(packed):.1f}x)")
    with zipfile.ZipFile(OUTV4, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=1))
        z.writestr("ledger.jsonl.lzs", packed)
        add_dir(z, PAWN_V4, "pawn")
        add_dir(z, KNIGHT, "knight")
    print(f"[ok] {OUTV4} ({os.path.getsize(OUTV4) / 1e6:.1f} MB)")


PAWN_V4 = "/tmp/opencode/kqat"

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] in ("v4", "v5") or \
        len(sys.argv) > 1 and sys.argv[1].startswith("v") and sys.argv[1][1:].isdigit():
    _arg = sys.argv[1][1:]
    main_v4(int(_arg))
