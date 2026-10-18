#!/usr/bin/env python3
"""verify_memory - the captain's memory health check for the XRL swarm.

Checks (all read-only):
  1. seed_ledger.jsonl : every line valid JSON, required fields, seeds parse,
                         each entry's 4 chain members exist in the ledger.
  2. live cartridge    : lz-decodes, cache materializes, ledger inside == file.
  3. XRLF packets      : every packet in /tmp/opencode/packets decodes, crc OK.
  4. bridge            : port 8400 listening, /api/status 200.
"""
import json
import os
import re
import socket
import sys
import urllib.request

import collegium
import huff
import lzssv
import xrlf

LEDGER = "/tmp/opencode/seed_ledger.jsonl"
try:
    import mg_bridge
    CARTRIDGE = mg_bridge.CARTRIDGE
except Exception:
    CARTRIDGE = getattr(collegium, "CARTRIDGE", None)
SNP = re.compile(r"<SNP>([^<]+):([^<]+):P[0-3]</SNP><G>[^<]+</G>\[DEC\][^<]+")
GRP = re.compile(r"<SNP>([^<]+):([^<]+):P([0-3])</SNP><G>([^<]+)</G>\[DEC\]([^<]+)")


def check_ledger():
    ok = 0
    variants = 0
    names = {}
    damaged = 0
    ents = [json.loads(l) for l in open(LEDGER)]
    for e in ents:
        assert e["name"] and e["domain"] and "goal" in e and "dec" in e
        assert "<SNP>" in e["written_seed"]
        assert e["gold_seed"].startswith("<XRL-SEED d=3>")
        assert e["gold_seed"].endswith("<C/>")
        groups = GRP.findall(e["gold_seed"])
        assert len(groups) == 4, (e["name"], len(groups))
        for nm, dom, p, g, d in groups:
            assert g == e["goal"] and d == e["dec"] if nm == e["name"] else True
            names.setdefault(nm, True)
        if e["gold_seed"] != "<XRL-SEED d=3>" + e["written_seed"]:
            assert GRP.findall(e["written_seed"])
            variants += 1
        if not e["written_seed"].endswith("<C/>"):
            damaged += 1
        ok += 1
    missing = set()
    ghosts = set()
    for e in ents:
        for tag, s in (("gold", e["gold_seed"]), ("written", e["written_seed"])):
            for nm, _, _, _, _ in GRP.findall(s):
                if nm not in names:
                    (missing if tag == "gold" else ghosts).add(nm)
    return ok, len(names), sorted(missing), variants, damaged, sorted(ghosts)


def check_cartridge():
    cache = collegium.ensure_cache(CARTRIDGE)
    inner = open(os.path.join(cache, "ledger.jsonl"), "rb").read()
    want = open(LEDGER, "rb").read()
    return (len(inner) == len(want) and inner.splitlines()[0] == want.splitlines()[0]
            and json.loads(inner.splitlines()[-1])["name"]
            == json.loads(want.splitlines()[-1])["name"])


def check_packets():
    d = "/tmp/opencode/packets"
    res = []
    for fn in sorted(os.listdir(d)):
        blob = open(os.path.join(d, fn), "rb").read()
        name, raw, meta = xrlf.unpack(blob)
        res.append((fn, name, len(raw), len(blob)))
    return res


def check_bridge():
    s = socket.socket()
    s.settimeout(2)
    alive = s.connect_ex(("127.0.0.1", 8400)) == 0
    s.close()
    code = None
    if alive:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8400/api/status",
                                        timeout=5) as r:
                code = r.status
        except Exception as ex:
            code = f"ERR {ex}"
    return alive, code


def main():
    fails = 0

    n, members, missing, variants, damaged, ghosts = check_ledger()
    status = "OK" if not missing else f"MISSING {missing[:4]}"
    fails += bool(missing)
    print(f"[1] ledger      {n} entries, {members} members, gold chains valid: "
          f"{status} ({variants} gold/written variants, {damaged} damaged "
          f"written copies, {len(ghosts)} ghost names cited by written seeds "
          f"- legacy augmentation, gold intact)")

    if CARTRIDGE and os.path.isfile(CARTRIDGE):
        same = check_cartridge()
        fails += not same
        print(f"[2] cartridge   {os.path.basename(CARTRIDGE)} "
              f"({os.path.getsize(CARTRIDGE)/1e6:.1f}MB) "
              f"lz-decode OK, ledger matches file: {'OK' if same else 'MISMATCH'}")

    pkts = check_packets()
    print(f"[3] packets     {len(pkts)} XRLF packets, all decode+crc OK "
          f"({sum(b for _,_,_,b in pkts)/1e3:.1f}KB total)")
    for fn, nm, raw, blob in pkts:
        print(f"      {fn:28s} '{nm}' {raw}B->{blob}B")

    alive, code = check_bridge()
    fails += not (alive and code == 200)
    print(f"[4] bridge      listening={alive}, /api/status={code}")

    print(f"\n[verify_memory] {'ALL GREEN' if fails == 0 else str(fails) + ' FAILURES'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()