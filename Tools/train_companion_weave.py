#!/usr/bin/env python3
"""
Tools/train_companion_weave.py — Train Standardized 7.59M Mamba-2 Companion Weave Colony
========================================================================================
1. Trains neuron-companion-weave with:
   - 7.59M parameters (hidden=384, layers=8, heads=12, state=64)
   - Loss-masked causal reproduction (-100 prompt masking up to <REPLY>)
   - Max length 256 characters (batch_size=4)
   - Single-Turn Empathy (STE) + 432Hz Musical Chords (<CHORD=...>)
   - Spontaneous Attention Sparks (<SPARK ...>)
   - Embodied Motor Control & Postures (<emotion:...>, <micro:...>, <movement:...>, <mode:...>)
   - Negative Deference (<DEFER to="...">) to Finance, History, and Constitutive colonies.
2. Cascades the colony down to Fibonacci bedrock floor (34h) in fractal_micro/.
3. Evaluates live inference across all 4 interaction modes.
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path

ROOT = Path("/home/lumba/FoveAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Tools.fractal_replicator import cascade_cell_to_bedrock

DATA_FILE = ROOT / "Training" / "data" / "distill" / "companion_boundary_curriculum.jsonl"
VENV_PY = ROOT / ".venv" / "bin" / "python"
OUT_DIR = Path("/mnt/foveai/nano-xrl-bases/neuron-companion-weave")

def train_companion_colony():
    print("=" * 75)
    print("🧠 FORGING EMBODIED COMPANION WEAVE NEURON (7.59M MAMBA-2)")
    print("=" * 75)

    if not DATA_FILE.exists():
        print(f"❌ Curriculum data file not found: {DATA_FILE}")
        sys.exit(1)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["NEURON_HIDDEN"] = "384"
    env["NEURON_LAYERS"] = "8"
    env["NEURON_BATCH"] = "4"
    env["NEURON_DUTY"] = "100"
    env["NEURON_MAX_LEN"] = "256"
    env["CUDA_VISIBLE_DEVICES"] = "0"

    epochs = 20
    print(f"Dataset: {DATA_FILE}")
    print(f"Geometry: hidden=384, layers=8, batch=4, max_len=256, epochs={epochs}")
    print(f"Target: {OUT_DIR}\n", flush=True)

    cmd = [
        str(VENV_PY), "-u", "-m", "Forge.collective.generation_neuron_train",
        "--recipe", "companion-weave",
        "--name", "companion-weave",
        "--pairs-file", str(DATA_FILE),
        "--epochs", str(epochs)
    ]

    t0 = time.time()
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))

    for line in proc.stdout:
        print(line, end="", flush=True)

    proc.wait()
    elapsed = time.time() - t0

    if proc.returncode != 0:
        print(f"\n❌ Training failed with returncode {proc.returncode}")
        sys.exit(proc.returncode)

    print(f"\n✅ Training completed successfully in {elapsed:.1f}s!", flush=True)

    # Cascade to Fibonacci Bedrock (34h)
    print(f"\n🌀 Cascading neuron-companion-weave down to Fibonacci bedrock (34h)...", flush=True)
    cascade_cell_to_bedrock(OUT_DIR)
    print(f"✅ Bedrock cascade complete!", flush=True)

    # Live Verification
    verify_inference()

def verify_inference():
    import torch
    from transformers import Mamba2ForCausalLM

    print("\n" + "=" * 75)
    print("🔍 LIVE SILICON INFERENCE VERIFICATION")
    print("=" * 75)

    meta_file = OUT_DIR / "neuron_meta.json"
    if not meta_file.exists():
        print(f"❌ Meta file missing: {meta_file}")
        return

    meta = json.loads(meta_file.read_text())
    t2i = meta["tok2id"]
    i2t = {int(v): k for k, v in t2i.items()}
    marker = meta["marker"]
    end_marker = meta["end_marker"]

    model = Mamba2ForCausalLM.from_pretrained(str(OUT_DIR)).to("cuda")
    model.eval()

    test_queries = [
        ("Single-Turn Empathy (Loneliness)",
         "I felt really lonely today, can we talk?"),
        ("Spontaneous Attention Spark (Silence)",
         '<SPARK source="silence" duration="240s">'),
        ("Spontaneous Somatic Spark (Port Health Drop)",
         '<SPARK source="somatic" event="port_drop" target="8401">'),
        ("Embodied Motor Movement (Locomotion)",
         "Come closer, please."),
        ("Negative Deference Boundary (Finance)",
         "Calculate the interest rate swap spread on sovereign bonds.")
    ]

    for label, query in test_queries:
        print(f"▶ [{label}]")
        print(f"  Prompt : {query}")
        ids = [t2i["<bos>"]] + [t2i[c] for c in query if c in t2i] + [t2i[marker]]
        inp = torch.tensor([ids], dtype=torch.long, device="cuda")
        with torch.no_grad():
            out_ids = model.generate(inp, max_new_tokens=140, do_sample=False, pad_token_id=t2i["<pad>"])
        gen_tokens = out_ids[0][inp.shape[1]:].tolist()
        gen_text = "".join(i2t.get(i, "?") for i in gen_tokens)
        if end_marker in gen_text:
            gen_text = gen_text.split(end_marker)[0]
        print(f"  Reply  : {gen_text}\n")

if __name__ == "__main__":
    train_companion_colony()
