#!/usr/bin/env python3
"""grow_ledger - add new seed members to the ledger, zero retraining.

New members are pure data: same <SNP>name:domain:Pn</SNP><G>goal</G>[DEC]dec
4-member chain format the pawn already recites. Usage:
  grow_ledger.py 20           # grow 20 new members
  grow_ledger.py 20 --dry    # just print, do not append
"""
import json
import random
import sys
import urllib.request

LEDGER = "/tmp/opencode/seed_ledger.jsonl"
HDRTAG = "<XRL-SEED d=3>"


def load():
    return [json.loads(l) for l in open(LEDGER)]


def pools(ents):
    adjs, nouns, doms, goals, decs = set(), set(), set(), set(), set()
    for e in ents:
        a, _, n = e["name"].partition(" ")
        adjs.add(a)
        nouns.add(n)
        doms.add(e["domain"])
        goals.add(e["goal"])
        decs.add(e["dec"])
    return sorted(adjs), sorted(nouns), sorted(doms), sorted(goals), sorted(decs)


def make_entries(ents, count, rng):
    reg = {e["name"]: (e["domain"], e["goal"], e["dec"]) for e in ents}
    adjs, nouns, doms, goals, decs = pools(ents)
    have = {e["name"] for e in ents}
    new = []
    added = []
    while len(added) < count:
        nm = f"{rng.choice(adjs)} {rng.choice(nouns)}"
        if nm in have or any(x["name"] == nm for x in added):
            continue
        dom, gol, dec = rng.choice(doms), rng.choice(goals), rng.choice(decs)
        added.append({"name": nm, "domain": dom, "goal": gol, "dec": dec})
        reg[nm] = (dom, gol, dec)
    # one entry per new member: chain of 4 = self + 3 sampled members
    for m in added:
        others = rng.sample([e["name"] for e in ents], 3)
        chain = [m["name"]] + others
        rng.shuffle(chain)
        body = "".join(
            f"<SNP>{nm}:{reg[nm][0]}:P{i}</SNP><G>{reg[nm][1]}</G>"
            f"[DEC]{reg[nm][2]}"
            for i, nm in enumerate(chain)) + "<C/>"
        new.append({"name": m["name"], "domain": m["domain"],
                    "dec": m["dec"], "goal": m["goal"],
                    "gold_seed": HDRTAG + body, "written_seed": body})
    return new


def main():
    count = int(sys.argv[1]) if len(sys.argv) else 20
    dry = "--dry" in sys.argv
    rng = random.Random(20261018)
    ents = load()
    print(f"[grow] ledger now: {len(ents)} entries")
    new = make_entries(ents, count, rng)
    for e in new:
        print(f"[grow] + {e['name']:18s} {e['domain']:12s} "
              f"goal={e['goal']!r} dec={e['dec']!r}")
    if dry:
        print("[grow] dry run - nothing written")
        return
    import shutil
    shutil.copy(LEDGER, LEDGER + ".bak-480")
    with open(LEDGER, "a") as f:
        for e in new:
            f.write(json.dumps(e, separators=(", ", ": ")) + "\n")
    grown = load()
    print(f"[grow] appended {len(new)} -> {len(grown)} entries "
          f"({LEDGER}.bak-480 kept)")


if __name__ == "__main__":
    main()