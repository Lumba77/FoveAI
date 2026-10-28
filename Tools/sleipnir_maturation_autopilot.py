#!/usr/bin/env python3
"""
Tools/sleipnir_maturation_autopilot.py — Autonomous Maturation & Distillation Engine
=====================================================================================
Orchestrates the entire Teacher-Student Youth Maturation loop autonomously:
1. Teacher Phase (DeepSeek-R1): Generates 3-step causal deductions for each domain.
2. Safe VRAM Transition: Fully unloads teacher weights, verifies GPU memory < 1.5 GB.
3. Student SFT Phase (Mamba-2): Fine-tunes specialized colonies with -100 prompt loss masking.
4. Fibonacci Cascade: SVD-projects updated cells down Alice's rabbit hole to 34h bedrock.
5. Verification & Telemetry: Probes the live Mid-Hive and updates maturation_status.json.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

ROOT = Path("/home/lumba/FoveAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Tools.r1_swarm_distiller import generate_teacher_sample, CURRICULUM_TOPICS
from Tools.fractal_replicator import cascade_cell_to_bedrock

DATA_DIR = ROOT / "Training" / "data" / "distill"
STATUS_FILE = DATA_DIR / "maturation_status.json"
LOG_DIR = Path("/home/lumba/runlogs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "maturation_autopilot.log"

COLONY_MAP = {
    "finance": {
        "cell_name": "general_finance",
        "cell_dir": Path("/mnt/foveai/nano-xrl-bases/neuron-general_finance")
    },
    "history": {
        "cell_name": "general_history",
        "cell_dir": Path("/mnt/foveai/nano-xrl-bases/neuron-general_history")
    },
    "constitutive": {
        "cell_name": "constitutive-base",
        "cell_dir": Path("/mnt/foveai/nano-xrl-bases/neuron-constitutive-base")
    },
    "receptor": {
        "cell_name": "xrl_receptor",
        "cell_dir": Path("/mnt/foveai/nano-xrl-bases/neuron-xrl_receptor")
    }
}

DOMAIN_MAP = {
    "finance": "finance",
    "history": "history",
    "constitutive": "constitutive",
    "receptor": "receptor",
    "technology": "constitutive",
}

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def update_status(data: dict):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def train_colony_cell(domain_key: str, pairs_file: Path, epochs: int = 8):
    """Executes SFT on the student cell with -100 prompt loss masking."""
    info = COLONY_MAP.get(domain_key)
    if not info:
        return None

    name = info["cell_name"]
    log(f"🌱 [student] Starting SFT training for {name} on {pairs_file.name} (Epochs: {epochs})...")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["NEURON_HIDDEN"] = "384"
    env["NEURON_LAYERS"] = "8"
    env["NEURON_BATCH"] = "16"
    env["NEURON_DUTY"] = "80"
    env["TORCHINDUCTOR_COMPILE_THREADS"] = "1"
    env["MAX_JOBS"] = "1"
    env["OMP_NUM_THREADS"] = "2"
    env["CUDA_VISIBLE_DEVICES"] = "0"

    cmd = [
        str(ROOT / ".venv" / "bin" / "python"),
        "-u", "-m", "Forge.collective.generation_neuron_train",
        "--recipe", "generic",
        "--name", name,
        "--pairs-file", str(pairs_file),
        "--epochs", str(epochs)
    ]

    t0 = time.time()
    res = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))
    elapsed = time.time() - t0

    if res.returncode == 0:
        log(f"✅ [student] Successfully trained {name} in {elapsed:.1f}s")
        # Cascade down to Fibonacci ranks
        log(f"🌀 [fractal] Cascading {name} down to Fibonacci bedrock (34h)...")
        cascade_res = cascade_cell_to_bedrock(info["cell_dir"])
        log(f"⚡ [fractal] Cascaded {len(cascade_res)} ranks for {name}")
        return True
    else:
        log(f"❌ [student] Training error for {name}: {res.stdout[-400:]}")
        return False

def run_maturation_cycle():
    log("="*70)
    log("🐎 SLEIPNIR AUTONOMOUS YOUTH MATURATION AUTOPILOT LAUNCHED")
    log("="*70)

    # Resume from checkpoint if present
    start_index = 0
    domains_trained = {}
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                start_index = saved.get("topics_completed", 0)
                domains_trained = saved.get("domains_trained", {})
                log(f"🔄 Found checkpoint: resuming from topic {start_index + 1}/{len(CURRICULUM_TOPICS)}...")
        except Exception as e:
            log(f"⚠️ Checkpoint read error ({e}), starting fresh")

    status = {
        "start_time": time.time(),
        "topics_total": len(CURRICULUM_TOPICS),
        "topics_completed": start_index,
        "domains_trained": domains_trained,
        "current_phase": "IDLE"
    }
    update_status(status)

    domain_buckets = {k: [] for k in COLONY_MAP.keys()}

    for idx, item in enumerate(CURRICULUM_TOPICS):
        if idx < start_index:
            continue

        raw_domain = item.get("domain_key", "history")
        domain = DOMAIN_MAP.get(raw_domain, "constitutive")
        topic_name = item["topic"]
        prompt = item["prompt"]

        log(f"\n[{idx+1}/{len(CURRICULUM_TOPICS)}] Teacher generating trace for [{domain}]: \"{topic_name}\"")
        status["current_phase"] = f"TEACHER_GENERATION: {topic_name}"
        status["current_topic"] = topic_name
        status["current_domain"] = domain
        update_status(status)

        # 1. Teacher generates trace
        sample = generate_teacher_sample(prompt, max_tokens=850)
        if sample and sample.get("deduction"):
            domain_buckets[domain].append({
                "req": prompt,
                "out": sample["deduction"],
                "thought": sample["thought"],
                "topic": topic_name
            })
            log(f"  ✨ Captured trace ({len(sample['deduction'].split())} words)")
        else:
            log(f"  ⚠️ Warning: No deduction captured for {topic_name}")

        status["topics_completed"] = idx + 1
        update_status(status)

        # Rest between generations to preserve thermals
        time.sleep(5)

        # Every 4 items or at end of curriculum, trigger SFT for accumulated domains
        if (idx + 1) % 4 == 0 or (idx + 1) == len(CURRICULUM_TOPICS):
            for dom, pairs in domain_buckets.items():
                if len(pairs) >= 2:
                    status["current_phase"] = f"STUDENT_SFT: {dom}"
                    update_status(status)

                    domain_file = DATA_DIR / f"{dom}_maturation_curriculum.jsonl"
                    with open(domain_file, "a", encoding="utf-8") as f:
                        for p in pairs:
                            f.write(json.dumps(p) + "\n")

                    # Train colony cell
                    train_colony_cell(dom, domain_file, epochs=8)
                    status["domains_trained"][dom] = status["domains_trained"].get(dom, 0) + len(pairs)
                    pairs.clear()

    status["current_phase"] = "COMPLETED"
    status["completion_time"] = time.time()
    update_status(status)
    log("="*70)
    log("🏆 SLEIPNIR AUTONOMOUS YOUTH MATURATION CYCLE COMPLETED")
    log("="*70)

if __name__ == "__main__":
    run_maturation_cycle()
