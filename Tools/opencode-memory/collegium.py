#!/usr/bin/env python3
"""FoveAI collegium v1 - "Nova": a unison model run by a roster of nanos.

Roster tonight:
  pawn   (reader/copy) - reads seeds, answers decision questions verbatim
  knight (binder)      - converts a read answer into the asked answer type
Ledger + roster live outside the weights (the motherboard).

Usage:
  python collegium.py --roster
  python collegium.py "What decision did the north promenade team make?"
  python collegium.py --k 8 "What outcome did lark aquifer commit to?"
  python collegium.py --cartridge /path/nova.collegium "question"
"""
import argparse
import json
import os
import random
import zipfile

CARTRIDGE = "/tmp/opencode/nova.collegium"
DEC_Q = "What decision did the {n} team make?"
GOAL_Q = "What outcome did {n} commit to?"


def ensure_cache(path):
    tag = os.path.splitext(os.path.basename(path))[0]
    cache = f"/tmp/opencode/collegium_cache_{tag}"
    mf = os.path.join(cache, "manifest.json")
    if os.path.isfile(mf):
        return cache
    print(f"[cartridge] unpacking {path} -> {cache} (first run only)", flush=True)
    with zipfile.ZipFile(path) as z:
        z.extractall(cache)
        packed = [n for n in z.namelist() if n.endswith(".lzs")]
    if packed:
        import huff
        import lzssv
        for arc in packed:
            dst = arc[:-4]
            p = os.path.join(cache, dst)
            if os.path.isfile(p):
                continue
            raw = huff.decode(open(os.path.join(cache, arc), "rb").read())
            blob = lzssv.decode(raw)
            open(p, "wb").write(blob)
            print(f"[cartridge] lz-decoded {arc} -> {dst} "
                  f"({os.path.getsize(p)/1e3:.1f}KB)", flush=True)
    return cache


def find_member(question, ledger):
    ql = question.lower()
    best = None
    for e in ledger:
        if e["name"].lower() in ql and (best is None or len(e["name"]) > len(best["name"])):
            best = e
    return best


def gen(model, tok, dev, prompt):
    import torch
    enc = tok(prompt, return_tensors="pt").to(dev)
    out = model.generate(**enc, max_new_tokens=24, do_sample=False,
                         pad_token_id=tok.pad_token_id)
    a = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)
    return a.split("</A>", 1)[0].strip()


def load_member(dirpath, dev, bits_default=6):
    """Load a quantized member dir (weights_k4.safetensors) as a live model."""
    import numpy as np
    import torch
    import safetensors.torch as st
    from transformers import AutoConfig, AutoModelForCausalLM

    def unpack_bits(stream, n, bits):
        flat = np.unpackbits(stream, bitorder="little")[: n * bits].reshape(n, bits)
        acc = np.zeros(n, np.uint64)
        for j in range(bits):
            acc |= flat[:, j].astype(np.uint64) << np.uint64(j)
        return acc

    def dequant_2d(codes, scales, rows, cols, bits, group):
        zero = 1 << (bits - 1)
        ng = (cols + group - 1) // group
        u = unpack_bits(np.ascontiguousarray(codes), rows * ng * group, bits)
        q = u.astype(np.float32).reshape(rows, ng, group)
        q -= zero
        x = q * scales.astype(np.float32).reshape(rows, ng, 1)
        x = x.reshape(rows, ng * group)[:, :cols]
        return torch.from_numpy(np.ascontiguousarray(x))

    cfg = AutoConfig.from_pretrained(dirpath)
    cfg.use_cache = True
    model = AutoModelForCausalLM.from_config(cfg, dtype=torch.float32)
    model.tie_weights()
    fp = os.path.join(dirpath, "weights_k4.safetensors")
    f = st.load_file(fp)
    from safetensors import safe_open
    with safe_open(fp, framework="pt") as fo:
        meta = fo.metadata() or {}
    bits = int(meta.get("k4_bits", 6))
    group = int(meta.get("k4_group", 64))
    if "_k4_bits" in f:
        bits = int(f["_k4_bits"].item())
        group = int(f["_k4_group"].item())
    bits_map = json.loads(meta["k4_bits_map"]) if meta.get("k4_bits_map") else None
    ref = model.state_dict()
    for k in list(f):
        if k.startswith("q::") and k[3:] not in ref:
            raise RuntimeError(f"unknown quantized tensor {k[3:]}")
    sd = {}
    for k in list(f):
        if k.startswith("q::"):
            name = k[3:]
            rows, cols = ref[name].shape
            ng = (cols + group - 1) // group
            scales = f["s::" + name].numpy()
            b = bits_map.get(name, bits) if bits_map else bits
            sd[name] = dequant_2d(f[k].numpy(), scales, rows, cols, b, group).to(torch.bfloat16)
        elif not k.startswith(("s::", "_k4_")):
            sd[k] = v = f[k]
    missing, unexpected = model.load_state_dict(sd, strict=False)
    missing = [m for m in missing if "lm_head" not in m]
    if missing or unexpected:
        raise RuntimeError(f"load error: missing={missing} unexpected={unexpected}")
    model.tie_weights()
    return model.to(dev).eval()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cartridge", default=CARTRIDGE)
    ap.add_argument("--k", type=int, default=1, help="seeds stacked (default 1)")
    ap.add_argument("--roster", action="store_true")
    ap.add_argument("question", nargs="*")
    args = ap.parse_args()

    cache = ensure_cache(args.cartridge)
    mf = json.load(open(os.path.join(cache, "manifest.json")))
    ledger = [json.loads(l) for l in open(os.path.join(cache, "ledger.jsonl"))]

    if args.roster or not args.question:
        print(json.dumps({"collegium": mf.get("name", "nova"),
                          "version": mf.get("version", 1),
                          "members": [{"name": m, **v} for m, v in mf["members"].items()],
                          "ledger_entries": len(ledger)}, indent=1))
        return
    question = " ".join(args.question)

    entry = find_member(question, ledger)
    if entry is None:
        names = sorted({e["name"] for e in ledger})
        print("[router] no ledger member named in the question.")
        print(f"[router] members include: {', '.join(names[:12])} ...")
        print('[router] try: What decision did the <member> team make?')
        return

    ql = question.lower()
    if "outcome" in ql or "commit" in ql:
        qtype = "goal"
    elif "decision" in ql:
        qtype = "dec"
    else:
        print("[router] question type unclear - answering as goal-type", flush=True)
        qtype = "goal"

    pool = {}
    for e in ledger:
        pool.setdefault(e["gold_seed"], e)
    seeds = [entry["gold_seed"]]
    if args.k > 1:
        rng = random.Random(len(entry["name"]) * 131 + args.k)
        seeds += rng.sample([s for s in pool if s != entry["gold_seed"]], args.k - 1)
        rng.shuffle(seeds)
    stack = "\n".join(seeds)
    print(f"[seed] member '{entry['name']}' ({entry['domain']}) - "
          f"{len(seeds)} seed(s) injected (k={args.k})", flush=True)

    import torch
    from transformers import AutoTokenizer

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(os.path.join(cache, "pawn"))
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"
    pawn = load_member(os.path.join(cache, "pawn"), dev)

    qd = DEC_Q.format(n=entry["name"])
    ad = gen(pawn, tok, dev, f"{stack}\n<Q>{qd}</Q>\n<A>")
    print(f"[pawn] {ad}", flush=True)

    if qtype == "dec":
        print(f"[nova] {ad}", flush=True)
        return

    del pawn
    torch.cuda.empty_cache()
    knight = load_member(os.path.join(cache, "knight"), dev)
    qg = GOAL_Q.format(n=entry["name"])
    ag = gen(knight, tok, dev,
             f"{stack}\n<Q>{qd}</Q>\n<A>{ad}</A>\n<Q>{qg}</Q>\n<A>")
    print(f"[knight] {ag}", flush=True)
    print(f"[nova] {ag}", flush=True)


if __name__ == "__main__":
    main()