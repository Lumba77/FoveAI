#!/usr/bin/env python3
"""
Tools/train_boundary_colonies.py — Train Deference & Addressing Across the 4 Colonies
=====================================================================================
Sequentially trains:
1. neuron-general_finance on finance_boundary_curriculum.jsonl
2. neuron-general_history on history_boundary_curriculum.jsonl
3. neuron-constitutive-base on constitutive_boundary_curriculum.jsonl
4. neuron-xrl_receptor on receptor_boundary_curriculum.jsonl
Then cascades each colony to Fibonacci bedrock (34h) and verifies deference gating.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path("/home/lumba/FoveAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "Training" / "data" / "distill"
VENV_PY = ROOT / ".venv" / "bin" / "python"

from Tools.fractal_replicator import cascade_cell_to_bedrock

COLONIES_TO_TRAIN = [
    {
        "name": "general_finance",
        "file": DATA_DIR / "finance_boundary_curriculum.jsonl",
        "dir": Path("/mnt/foveai/nano-xrl-bases/neuron-general_finance"),
        "epochs": 18
    },
    {
        "name": "general_history",
        "file": DATA_DIR / "history_boundary_curriculum.jsonl",
        "dir": Path("/mnt/foveai/nano-xrl-bases/neuron-general_history"),
        "epochs": 18
    },
    {
        "name": "constitutive-base",
        "file": DATA_DIR / "constitutive_boundary_curriculum.jsonl",
        "dir": Path("/mnt/foveai/nano-xrl-bases/neuron-constitutive-base"),
        "epochs": 16
    },
    {
        "name": "xrl_receptor",
        "file": DATA_DIR / "receptor_boundary_curriculum.jsonl",
        "dir": Path("/mnt/foveai/nano-xrl-bases/neuron-xrl_receptor"),
        "epochs": 20
    }
]

def train_and_cascade_all():
    print("="*70)
    print("🚀 LAUNCHING SWARM BOUNDARY & SYNAPTIC ADDRESSING MATURATION")
    print("="*70)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["NEURON_HIDDEN"] = "384"
    env["NEURON_LAYERS"] = "8"
    env["NEURON_BATCH"] = "4"
    env["NEURON_DUTY"] = "100"
    env["NEURON_MAX_LEN"] = "256"
    env["CUDA_VISIBLE_DEVICES"] = "0"

    for idx, c in enumerate(COLONIES_TO_TRAIN):
        cname = c["name"]
        cfile = c["file"]
        epochs = c["epochs"]
        print(f"\n[{idx+1}/{len(COLONIES_TO_TRAIN)}] 🧠 Training {cname} (Epochs: {epochs})...", flush=True)

        cmd = [
            str(VENV_PY), "-u", "-m", "Forge.collective.generation_neuron_train",
            "--recipe", "generic",
            "--name", cname,
            "--pairs-file", str(cfile),
            "--epochs", str(epochs)
        ]

        t0 = time.time()
        res = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))
        elapsed = time.time() - t0

        if res.returncode == 0:
            print(f"  ✅ Trained {cname} in {elapsed:.1f}s", flush=True)
            # Cascade
            print(f"  🌀 Cascading {cname} down to Fibonacci bedrock (34h)...", flush=True)
            ranks = cascade_cell_to_bedrock(c["dir"])
            print(f"  ⚡ Cascaded {len(ranks)} ranks for {cname}", flush=True)
        else:
            print(f"  ❌ Error training {cname}:\n{res.stdout[-500:]}", flush=True)
            return False

    print("\n" + "="*70)
    print("🏆 ALL 4 COLONIES MATURED WITH DEFERENCE & SYNAPTIC ADDRESSING")
    print("="*70)
    return True

if __name__ == "__main__":
    train_and_cascade_all()
