# Sleipnir Cellular Swarm: Production Chain & Replication Runbook

**Document Version:** 1.0.0  
**Repository Path:** `Docs/SLEIPNIR_CELLULAR_SWARM_PRODUCTION_CHAIN.md`  
**Target Hardware:** NVIDIA RTX 4060 (8 GB VRAM), Linux Mint (X11)  
**Cell Standard:** Mamba-2 SSM (7.59M parameters, FP16 15.2 MB / Int4 3.8 MB)  

---

## 1. Production Chain Overview

This document formalizes the reproducible, end-to-end production pipeline for training, compressing, and deploying sovereign Mamba-2 cellular SLMs for the Sleipnir Swarm.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       STAGE 1: TEACHER DISTILLATION                         │
│ DeepSeek-R1 (14B IQ3_XS) via llama-cli (-c 4096, --single-turn, --temp 0.6) │
│ Generates explicit 3-step causal deductions: Premise -> Mechanism -> Outcome│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Raw traces (.jsonl)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAGE 2: SFT WITH PROMPT LOSS MASKING                    │
│ Forge.collective.generation_neuron_train (labels = -100 up to <REPLY>)      │
│ Sequence capacity: max_len=256, batch=4. 100% gradient on causal deductions │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Base Model (Rank 384h, 15.2 MB)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAGE 3: FIBONACCI SVD BEDROCK CASCADE                   │
│ Tools.fractal_replicator (Singular Value Decomposition)                     │
│ 384h -> 233h -> 144h -> 89h -> 34h (Telomere Bedrock: ~1.3 MB)              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Tiered Model Shards
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   STAGE 4: CENTRAL THALAMUS & MID-HIVE                      │
│ Tools.central_thalamus_coordinator & Tools.thalamus_xrl_bridge (:8420)      │
│ Influx to ring_2_mid -> Colony forward passes -> Consensus sealed in 2.8s   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Stage-by-Stage Specifications

### Stage 1: Elder Teacher Trace Harvesting
* **Script:** [`Tools/r1_swarm_distiller.py`](file:///home/lumba/FoveAI/Tools/r1_swarm_distiller.py)
* **Model:** DeepSeek-R1-Distill-Qwen-14B-IQ3_XS (`/mnt/foveai/Models/qwen2.5-14b/`)
* **Engine:** `llama-cli` (b11053, CUDA backend, `-ngl 28`)
* **Context Budget:** `-c 4096`, `-n 850` (to allow full `<think>` deliberation without truncating final deductions).
* **Deliberation Parsing:** Strips `<think>` or `[Start thinking]` markers; isolates explicit `Step 1 / Step 2 / Step 3` deductions.
* **Output Path:** `Training/data/distill/<domain>_maturation_curriculum.jsonl`

### Stage 2: Loss-Masked Student SFT Training
* **Script:** [`Forge/collective/generation_neuron_train.py`](file:///home/lumba/FoveAI/Forge/collective/generation_neuron_train.py)
* **Architecture:** Mamba2ForCausalLM (`hidden_size=384`, `layers=8`, `heads=12`, `chunk_size=64`)
* **Key Invariant: Prompt Loss Masking (`-100`):**
  ```python
  # All prompt tokens up to <REPLY> and padding tokens set to -100
  prefix_len = min(len(prompt_ids), max_len)
  for idx in range(prefix_len):
      label_row[idx] = -100
  for idx in range(prefix_len, max_len):
      if label_row[idx] == t2i["<pad>"]:
          label_row[idx] = -100
  ```
* **Context Window:** `max_len = 256` (configured via `NEURON_MAX_LEN=256`).
* **Batch Size:** `batch_size = 4` (prevents PyTorch reference scan OOM on 8 GB GPU).
* **Duty Cycle:** 80% duty throttling via `DutyThrottle` callback to preserve GPU thermals.
* **Target Loss:** $\mathcal{L} \le 1.0 \times 10^{-4}$ (consistently achieves $\sim 10^{-5}$ to $10^{-6}$).

### Stage 3: Fibonacci SVD Bedrock Cascade
* **Script:** [`Tools/fractal_replicator.py`](file:///home/lumba/FoveAI/Tools/fractal_replicator.py)
* **Mechanism:** Computes SVD factorization ($W \approx U_k \Sigma_k V_k^T$) on all Linear and Conv weights.
* **Hierarchy:**
  1. $F_{13} = 233h$ (`_micro_233h`, ~9.2 MB)
  2. $F_{12} = 144h$ (`_micro_144h`, ~5.7 MB)
  3. $F_{11} = 89h$ (`_micro_89h`, ~3.5 MB)
  4. $F_9 = 34h$ (`_micro_34h`, ~1.3 MB — Telomere Floor)
* **Execution Time:** ~0.35s per rank projection.
* **Destination:** `/mnt/foveai/nano-xrl-bases/fractal_micro/`

### Stage 4: Central Thalamus Coordination & Consensus
* **Router Daemon:** [`Tools/central_thalamus_coordinator.py`](file:///home/lumba/FoveAI/Tools/central_thalamus_coordinator.py)
* **API Bridge:** [`Tools/thalamus_xrl_bridge.py`](file:///home/lumba/FoveAI/Tools/thalamus_xrl_bridge.py) (listening on port `:8420`, bridged to `:8403`)
* **Residency Enforcement:** Calls `unload()` and garbage collection before loading the next cell, ensuring single-model residency.
* **Consensus Latency:** 2.6 – 2.8 seconds end-to-end across 4 colonies.

---

## 3. Directory Layout & Artifact Registry

| Resource | Path | Description |
|:---|:---|:---|
| **Base Cell Weights** | `/mnt/foveai/nano-xrl-bases/neuron-<name>` | Master 384h FP16 models (15.2 MB) |
| **Fractal Micro Shards**| `/mnt/foveai/nano-xrl-bases/fractal_micro/` | Fibonacci sub-ranks (233h down to 34h) |
| **Curriculum Datasets** | `Training/data/distill/*.jsonl` | Distilled reasoning pairs |
| **Constitutive Childhood**| `Training/data/constitutive/stage00-11_full.jsonl` | Stages 0–11 temporal & identity invariants |
| **Master Blueprint** | `~/.gemini/antigravity-cli/brain/.../FOVEAI_HIGH_DENSITY_SWARM_PLAN.md` | Architectural theory (3-6-9, Wafers) |
| **Autopilot Daemon** | `Tools/sleipnir_maturation_autopilot.py` | Automated background teacher-student engine |
| **Live Logs** | `/home/lumba/runlogs/maturation_autopilot.log` | Complete timestamped execution trace |

---

## 4. Hardware & Thermal Invariants

* **Active VRAM Cap:** $\le 1.5\text{ GB}$ during student SFT; $\le 5.2\text{ GB}$ during teacher generation.
* **Zero VRAM Contention:** Teacher process terminates completely before PyTorch launches.
* **Thermals:** GPU maintained below 65°C under continuous operation.
