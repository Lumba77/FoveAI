"""
available_models.py — Context-Aware Dynamic Model Filter
Rules:
1. If GPU is in manual 100% duty (training or heavy task owns the GPU):
   -> Allow ONLY RAM models (Gear 1: Qwen 1.5B, 0 MB VRAM).
2. If in AUTO mode:
   -> Auto mode drops duty to 40% (or 20%) when web activity is detected.
   -> Models that fit along with currently allocated GPU memory are available:
      * Gear 1 (RAM 1.5B) -> Always available.
      * Gear 2 (4B) -> Available if free VRAM >= 3.0 GB.
      * Gear 3 (9B) -> Available if free VRAM >= 5.0 GB.
      * Gears 4, 5, 6 (12B, 14B, 32B) require solo access and are locked while heavy background compute is running.
"""
from __future__ import annotations
import os, sys, json, subprocess

sys.path.insert(0, "/home/lumba/FoveAI")
from runtime.throttle_controller import get_status

GEARS_MAP = {
    "1": {"id": "1", "name": "Gear 1: Ambient RAM (1.5B)", "model": "qwen2.5-coder-1.5b-instruct", "size_gb": 1.1, "vram_req_gb": 0.0, "placement": "ram"},
    "2": {"id": "2", "name": "Gear 2: Light 4B MTP", "model": "qwen3.5-4b-mtp-multimodal-v1.0", "size_gb": 2.9, "vram_req_gb": 3.0, "placement": "gpu_coexist"},
    "3": {"id": "3", "name": "Gear 3: Flagship 9B Coder", "model": "qwen3.5-9b-mtp-v1.0", "size_gb": 4.8, "vram_req_gb": 5.0, "placement": "gpu_coexist"},
    "4": {"id": "4", "name": "Gear 4: Balanced 12B Nemo", "model": "Mistral-Nemo-Instruct-2407-Q3_K_M", "size_gb": 5.8, "vram_req_gb": 6.2, "placement": "gpu_solo"},
    "5": {"id": "5", "name": "Gear 5: DeepSeek R1 14B Reasoning (MoQ)", "model": "deepseek-r1-distill-qwen-14b-iq3_xs", "size_gb": 6.0, "vram_req_gb": 6.8, "placement": "gpu_solo"},
    "6": {"id": "6", "name": "Gear 6: Sleipnir Mamba-2 Swarm & Companion Weave (:8420)", "model": "neuron-companion-weave", "size_gb": 0.06, "vram_req_gb": 0.1, "placement": "gpu_coexist"},
}

def get_free_vram_gb() -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            timeout=2, text=True
        )
        return float(out.strip().split()[0]) / 1024.0
    except Exception:
        return 0.0

def get_available_gears() -> dict:
    th = get_status()
    free_vram = get_free_vram_gb()
    mode = th.get("mode", "auto")
    duty = th.get("duty", 100)

    allowed = {}
    locked_reasons = {}

    # Rule 1: Manual 100% duty -> ONLY RAM and ultra-lean Swarm models allowed
    if mode == "manual" and duty >= 100:
        allowed["1"] = GEARS_MAP["1"]
        allowed["6"] = GEARS_MAP["6"]
        for g in ["2", "3", "4", "5"]:
            locked_reasons[g] = f"Locked: GPU duty pinned to manual 100% (training owns GPU). Only RAM / Swarm models allowed."
        return {
            "mode": mode,
            "duty": duty,
            "free_vram_gb": round(free_vram, 2),
            "allowed_gears": allowed,
            "locked_reasons": locked_reasons,
            "rule": "manual_100_ram_and_swarm_only"
        }

    # Rule 2: Auto mode or relaxed manual duty
    allowed["1"] = GEARS_MAP["1"]  # RAM model always permitted
    allowed["6"] = GEARS_MAP["6"]  # Mamba-2 Companion Weave always permitted (~60MB)

    # 4B and 9B are permitted if they fit in remaining free VRAM alongside background apps
    if free_vram >= GEARS_MAP["2"]["vram_req_gb"]:
        allowed["2"] = GEARS_MAP["2"]
    else:
        locked_reasons["2"] = f"Requires {GEARS_MAP['2']['vram_req_gb']}GB free VRAM (have {free_vram:.1f}GB)"

    if free_vram >= GEARS_MAP["3"]["vram_req_gb"]:
        allowed["3"] = GEARS_MAP["3"]
    else:
        locked_reasons["3"] = f"Requires {GEARS_MAP['3']['vram_req_gb']}GB free VRAM (have {free_vram:.1f}GB)"

    # Gears 4, 5 (Solo VRAM / Heavy Gears):
    # When user chooses them, room is made automatically by pausing background training (game mode).
    for g in ["4", "5"]:
        allowed[g] = GEARS_MAP[g]

    return {
        "mode": mode,
        "duty": duty,
        "free_vram_gb": round(free_vram, 2),
        "allowed_gears": allowed,
        "locked_reasons": locked_reasons,
        "rule": "coexistence_fit"
    }

if __name__ == "__main__":
    print(json.dumps(get_available_gears(), indent=2))
