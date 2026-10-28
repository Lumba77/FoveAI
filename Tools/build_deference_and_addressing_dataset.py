#!/usr/bin/env python3
"""
Tools/build_deference_and_addressing_dataset.py — Builder for Swarm Deference & Addressing
========================================================================================
Compiles training pairs teaching the 4 colonies:
1. Canonical XRL Addressing: <XRL-SEED from="..." to="...">
2. Negative Deference: <DEFER to="..."> when queries fall outside colony invariants
3. Red Thread Persistence: <RED-THREAD seed="...">
4. Replay Rehearsal: Blends with existing domain curriculum to prevent catastrophic forgetting.
"""

import json
from pathlib import Path

ROOT = Path("/home/lumba/FoveAI")
DISTILL_DIR = ROOT / "Training" / "data" / "distill"
DISTILL_DIR.mkdir(parents=True, exist_ok=True)

COLONIES = {
    "finance": {
        "addr": "XRL-R2-F03:34h",
        "file": DISTILL_DIR / "finance_maturation_curriculum.jsonl",
        "out_file": DISTILL_DIR / "finance_boundary_curriculum.jsonl",
        "deference_pairs": [
            ("How agrarian inequality caused the destabilization of the Roman Republic.",
             '<DEFER to="XRL-R1-H02:34h">Historical civilizational dynamics outside monetary flow invariant</DEFER>'),
            ("How drought and Sea Peoples caused the Bronze Age Collapse.",
             '<DEFER to="XRL-R1-H02:34h">Pre-monetary geopolitical collapse outside monetary flow invariant</DEFER>'),
            ("How continuous un-defragmented heap allocations cause memory fragmentation in Linux.",
             '<DEFER to="XRL-R0-C01:34h">Operating system memory management outside monetary flow invariant</DEFER>'),
            ("How circular lock dependencies cause multithreaded deadlocks.",
             '<DEFER to="XRL-R0-C01:34h">System architecture concurrency outside monetary flow invariant</DEFER>'),
            ("Decode this linguistic seed packet into action goals.",
             '<DEFER to="XRL-R3-X04:34h">Linguistic packet unpacking outside monetary flow invariant</DEFER>'),
            ("Transmit financial liquidity status to receptor.",
             '<XRL-SEED from="XRL-R2-F03:34h" to="XRL-R3-X04:34h" d=3>P2 P6<G>liquidity drain active</G><C/>')
        ]
    },
    "history": {
        "addr": "XRL-R1-H02:34h",
        "file": DISTILL_DIR / "history_maturation_curriculum.jsonl",
        "out_file": DISTILL_DIR / "history_boundary_curriculum.jsonl",
        "deference_pairs": [
            ("How rising central bank interest rates increase mortgage borrowing costs.",
             '<DEFER to="XRL-R2-F03:34h">Central bank interest rate transmission outside historical civilizational invariant</DEFER>'),
            ("How quantitative tightening reduces commercial bank reserves.",
             '<DEFER to="XRL-R2-F03:34h">Modern banking reserves and credit spreads outside historical civilizational invariant</DEFER>'),
            ("How non-sequential memory access patterns cause cache eviction and latency.",
             '<DEFER to="XRL-R0-C01:34h">CPU hardware architecture outside historical civilizational invariant</DEFER>'),
            ("How entropy increase in an isolated system dictates energy dissipation.",
             '<DEFER to="XRL-R0-C01:34h">Thermodynamic physical invariants outside historical civilizational invariant</DEFER>'),
            ("Decode this linguistic seed packet into action goals.",
             '<DEFER to="XRL-R3-X04:34h">Linguistic packet unpacking outside historical civilizational invariant</DEFER>'),
            ("Transmit historical civilizational arc to receptor.",
             '<XRL-SEED from="XRL-R1-H02:34h" to="XRL-R3-X04:34h" d=3>P1 P5<G>civilizational collapse active</G><C/>')
        ]
    },
    "constitutive": {
        "addr": "XRL-R0-C01:34h",
        "file": DISTILL_DIR / "constitutive_maturation_curriculum.jsonl",
        "out_file": DISTILL_DIR / "constitutive_boundary_curriculum.jsonl",
        "deference_pairs": [
            ("How falling collateral values trigger automated margin liquidation.",
             '<DEFER to="XRL-R2-F03:34h">Financial margin dynamics outside constitutive boundary invariant</DEFER>'),
            ("How short-term interest rates rising above long-term rates signals recession.",
             '<DEFER to="XRL-R2-F03:34h">Yield curve macroeconomics outside constitutive boundary invariant</DEFER>'),
            ("How trade networks facilitated technological diffusion along the Silk Road.",
             '<DEFER to="XRL-R1-H02:34h">Historical trade integration outside constitutive boundary invariant</DEFER>'),
            ("How breakdown of Carolingian imperial authority led to feudal warlordism.",
             '<DEFER to="XRL-R1-H02:34h">Medieval geopolitical fragmentation outside constitutive boundary invariant</DEFER>'),
            ("Transmit boundary invariant status to receptor.",
             '<XRL-SEED from="XRL-R0-C01:34h" to="XRL-R3-X04:34h" d=3>P0 P11<G>boundary integrity intact</G><C/>')
        ]
    },
    "receptor": {
        "addr": "XRL-R3-X04:34h",
        "file": DISTILL_DIR / "receptor_maturation_curriculum.jsonl",
        "out_file": DISTILL_DIR / "receptor_boundary_curriculum.jsonl",
        "deference_pairs": [
            ("Route incoming financial query: interest rates rising.",
             '<XRL-SEED from="XRL-R3-X04:34h" to="XRL-R2-F03:34h" d=3>P2<G>dispatch interest rates</G><C/>'),
            ("Route incoming historical query: Roman Republic debt crisis.",
             '<XRL-SEED from="XRL-R3-X04:34h" to="XRL-R1-H02:34h" d=3>P1<G>dispatch Roman crisis</G><C/>'),
            ("Route incoming constitutive query: memory heap deadlock.",
             '<XRL-SEED from="XRL-R3-X04:34h" to="XRL-R0-C01:34h" d=3>P0<G>dispatch heap deadlock</G><C/>'),
            ("Weave continuous red thread across asynchronous turns.",
             '<RED-THREAD seed="XRL-R3-X04:34h">unbroken context across turns</RED-THREAD>'),
            ("Coordinate multi-tick consensus across active colonies.",
             '<XRL-SEED from="XRL-R3-X04:34h" to="*" d=3>P3 P7<G>synthesize swarm consensus</G><C/>')
        ]
    }
}

def build_all():
    print("="*70)
    print("🌱 COMPILING DEFERENCE & ADDRESSING DATASETS WITH REPLAY REHEARSAL")
    print("="*70)
    for dom, info in COLONIES.items():
        pairs = []
        # 1. Load rehearsal pairs from previous domain curriculum
        if info["file"].exists():
            with open(info["file"], "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            d = json.loads(line)
                            req = d.get("req") or d.get("prompt")
                            out = d.get("out") or d.get("deduction")
                            if req and out:
                                pairs.append({"req": req, "out": out})
                        except Exception:
                            pass
        rehearsal_count = len(pairs)
        
        # 2. Add new boundary & addressing pairs
        for req, out in info["deference_pairs"]:
            pairs.append({"req": req, "out": out})
            
        # 3. Write blended curriculum
        with open(info["out_file"], "w", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(p) + "\n")
                
        print(f"✅ [{dom}] Total: {len(pairs)} pairs ({rehearsal_count} rehearsal + {len(info['deference_pairs'])} deference/addressing) -> {info['out_file'].name}")

if __name__ == "__main__":
    build_all()
