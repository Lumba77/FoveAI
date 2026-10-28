#!/usr/bin/env python3
"""
Tools/central_thalamus_coordinator.py — Central Thalamus Swarm Coordinator
===========================================================================
Pure, zero-pollution gating and routing for the Sleipnir Holonic Swarm.
- Receives user query.
- Employs Pure Thalamic Gating (no large LLM mouthpiece).
- Routes query dynamically to winning Colony (e.g. History vs Finance).
- Dispatches execution to the specialized Mamba cell (384h or 233h).
- Emits pure, unpolluted domain output directly to caller.
- Exposes OpenAI-compatible HTTP server on :8419.
"""

import os
import sys
import json
import time
import re
import math
import gc
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import torch
from transformers import Mamba2ForCausalLM

BASE_DIR = Path("/mnt/foveai/nano-xrl-bases")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ── Colony Registries with Multi-Tier Alice Tiers ──────────────────────────────
ALICE_TIERS = {
    0: {"name": "Tier 0 (Macro: 384h • F₁₄)", "rank": 384, "suffix": ""},
    1: {"name": "Tier 1 (Micro: 233h • F₁₃)", "rank": 233, "suffix": "_micro_233h"},
    2: {"name": "Tier 2 (Nano:  144h • F₁₂)", "rank": 144, "suffix": "_micro_144h"},
    3: {"name": "Tier 3 (Gate:   89h • F₁₁)", "rank": 89,  "suffix": "_micro_89h"},
    4: {"name": "Tier 4 (Bedrock: 34h • F₉)",  "rank": 34,  "suffix": "_micro_34h"}
}

COLONIES = {
    "history": {
        "colony_id": 0,
        "name": "Colony History (Temporal/Ontological)",
        "base_path": BASE_DIR / "neuron-general_history",
        "keywords": [
            "history", "historical", "war", "empire", "emperor", "century", "ancient",
            "rome", "roman", "greece", "medieval", "republic", "revolution", "battle",
            "treaty", "dynasty", "past", "civilization", "archaeology", "era", "feudal"
        ]
    },
    "finance": {
        "colony_id": 1,
        "name": "Colony Finance (Economic/Quantitative)",
        "base_path": BASE_DIR / "neuron-general_finance",
        "keywords": [
            "finance", "financial", "money", "bank", "interest", "compound", "stock",
            "market", "inflation", "investment", "capital", "portfolio", "credit",
            "debt", "asset", "liability", "dividend", "yield", "rate", "accounting",
            "revenue", "profit", "loss", "fiscal", "currency", "equity"
        ]
    },
    "constitutive": {
        "colony_id": 2,
        "name": "Colony Constitutive (Physical Grounding & Boundary Law)",
        "base_path": BASE_DIR / "neuron-constitutive-base",
        "keywords": [
            "constitutive", "boundary", "self", "other", "slot", "duty", "body",
            "physical", "invariant", "atonement", "individuation", "soul", "duty", "grounding"
        ]
    },
    "receptor": {
        "colony_id": 3,
        "name": "Colony Receptor (XRL Lingua & Weaver)",
        "base_path": BASE_DIR / "neuron-xrl_receptor",
        "keywords": [
            "xrl", "seed", "rubble", "principa", "thread", "weave", "lingua",
            "encode", "decode", "receptor", "instiller", "hive", "hypermind", "lingua"
        ]
    },
    "companion": {
        "colony_id": 4,
        "name": "Colony Companion (Social Empathy, Motorics & Attention Sparks)",
        "base_path": BASE_DIR / "neuron-companion-weave",
        "keywords": [
            "spark", "lonely", "feel", "anxious", "sad", "happy", "talk", "miss",
            "friend", "closer", "sit", "walk", "follow", "quiet", "coexist",
            "cowork", "rest", "proud", "playlist", "coffee", "love", "comfort", "tired"
        ]
    }
}

class CentralThalamus:
    def __init__(self, device: str = DEVICE):
        self.device = device
        self.current_key = None
        self.active_model = None
        self.metas = {}
        self._load_metadata()

    def _load_metadata(self):
        for cid, info in COLONIES.items():
            meta_path = info["base_path"] / "neuron_meta.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    self.metas[cid] = json.load(f)

    def unload(self):
        """Reclaims all memory immediately."""
        if self.active_model is not None:
            del self.active_model
            self.active_model = None
            self.current_key = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def get_model(self, cid: str, depth: int = 0):
        depth = max(0, min(depth, 4))
        tier_info = ALICE_TIERS[depth]
        key = f"{cid}_{depth}"
        
        # If requested model is already active, return it
        if self.current_key == key and self.active_model is not None:
            return self.active_model
            
        # Unload previous model before loading new one (strict single-model residency)
        self.unload()
        
        if depth == 0:
            model_dir = COLONIES[cid]["base_path"]
        else:
            model_dir = BASE_DIR / "fractal_micro" / f"{COLONIES[cid]['base_path'].name}{tier_info['suffix']}"
            
        # print(f"[thalamus] Loading {key} ({tier_info['name']}) with strict GC...", flush=True)
        model = Mamba2ForCausalLM.from_pretrained(
            str(model_dir),
            torch_dtype=torch.float32 if self.device == "cpu" else torch.float16
        )
        model.to(self.device)
        model.eval()
        self.active_model = model
        self.current_key = key
        return self.active_model

    def route_query(self, query: str) -> dict:
        """Computes thalamic gating probabilities across colonies."""
        words = re.findall(r"\w+", query.lower())
        if not words:
            return {"winning_colony": "history", "confidence": 0.5, "scores": {}}

        scores = {}
        for cid, info in COLONIES.items():
            match_count = sum(1 for w in words if w in info["keywords"])
            # Prefix / substring match for inflected terms
            stem_count = sum(1 for w in words for k in info["keywords"] if len(w) > 3 and (w.startswith(k) or k.startswith(w)))
            scores[cid] = match_count * 2.0 + stem_count * 1.0

        # Softmax normalization
        max_score = max(scores.values()) if scores else 0.0
        exp_sum = sum(math.exp(s - max_score) for s in scores.values())
        probs = {cid: math.exp(s - max_score) / exp_sum for cid, s in scores.items()}

        winner = max(probs, key=probs.get)
        confidence = probs[winner]

        return {
            "winning_colony": winner,
            "colony_info": COLONIES[winner],
            "confidence": round(confidence, 4),
            "distribution": {k: round(v, 4) for k, v in probs.items()}
        }

    def generate_with_colony(self, cid: str, query: str, depth: int = 0, max_tokens: int = 80) -> dict:
        """Direct generation with a specific colony cell (bypassing horizontal thalamic routing)."""
        if cid not in COLONIES:
            cid = "history"
            
        t1 = time.time()
        model = self.get_model(cid, depth=depth)
        tier_info = ALICE_TIERS[depth]
        meta = self.metas.get(cid, {})
        t2i = meta.get("tok2id", {})
        i2t = {int(v): k for k, v in t2i.items()}
        marker = meta.get("marker", "<REPLY>")
        end_marker = meta.get("end_marker", "</REPLY>")

        # Tokenize (Char-level Mamba)
        bos = [t2i["<bos>"]] if "<bos>" in t2i else []
        marker_tok = [t2i[marker]] if marker in t2i else []
        char_ids = [t2i[c] for c in query if c in t2i]
        input_ids = torch.tensor([bos + char_ids + marker_tok], dtype=torch.long, device=self.device)

        with torch.no_grad():
            output_ids = model.generate(
                input_ids,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=0.3,
                pad_token_id=t2i.get("<pad>", 0)
            )

        gen_tokens = output_ids[0][input_ids.shape[1]:].tolist()
        gen_text = "".join(i2t.get(int(t), "") for t in gen_tokens)
        if end_marker in gen_text:
            gen_text = gen_text.split(end_marker)[0]

        return {
            "query": query,
            "colony": cid,
            "output": gen_text.strip(),
            "generation_latency_s": round(time.time() - t1, 3)
        }

    def dispatch(self, query: str, depth: int = 0, max_tokens: int = 80) -> dict:
        """Full pipeline: Thalamic Route -> Alice Fractal Depth -> Direct Specialist Emission."""
        t0 = time.time()
        routing = self.route_query(query)
        cid = routing["winning_colony"]
        route_time = time.time() - t0

        res = self.generate_with_colony(cid, query, depth=depth, max_tokens=max_tokens)
        total_time = time.time() - t0

        return {
            "query": query,
            "routing": routing,
            "specialist": COLONIES[cid]["name"],
            "alice_depth": depth,
            "alice_tier": ALICE_TIERS[depth]["name"],
            "output": res["output"],
            "route_latency_ms": round(route_time * 1000, 2),
            "generation_latency_s": res["generation_latency_s"],
            "total_latency_s": round(total_time, 3),
            "tokens_per_sec": round(len(res["output"]) / max(0.001, res["generation_latency_s"]), 1)
        }

# ── HTTP Server (:8419) ───────────────────────────────────────────────────────
thalamus_instance = None

class ThalamusHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path in ["/v1/chat/completions", "/api/chat"]:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            messages = data.get("messages", [])
            query = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    query = m.get("content", "")
                    break

            res = thalamus_instance.dispatch(query, max_tokens=data.get("max_tokens", 80))
            resp_payload = {
                "id": f"thalamus-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "sleipnir-central-thalamus",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": res["output"]
                    },
                    "finish_reason": "stop"
                }],
                "thalamus_meta": {
                    "routing": res["routing"],
                    "specialist": res["specialist"],
                    "latency": res["total_latency_s"]
                }
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet logging

def run_server(port: int = 8419):
    global thalamus_instance
    thalamus_instance = CentralThalamus(device=DEVICE)
    server = HTTPServer(("0.0.0.0", port), ThalamusHandler)
    print(f"[thalamus] Central Thalamus Coordinator listening on port :{port} ({DEVICE})...")
    server.serve_forever()

if __name__ == "__main__":
    if "--serve" in sys.argv:
        run_server()
    else:
        # Run Interactive Fractal Alice Dispatch Benchmark
        ct = CentralThalamus(device=DEVICE)
        
        print("\n" + "="*80)
        print("🐇 THALAMUS FRACTAL ALICE — 2D HOLONIC ROUTING BENCHMARK")
        print("   Axis 1: Horizontal Colony Gating (History vs Finance)")
        print("   Axis 2: Vertical Fibonacci Rabbit Hole (Alice Depth 0 -> 4)")
        print("="*80)
        
        test_cases = [
            ("Explain the constitutional dynamics of the Roman Republic.", 0), # Deep Macro
            ("Teach me about general history.", 1),                            # Micro Reflex
            ("What is compound interest in finance?", 0),                      # Deep Macro Finance
            ("Define financial stock yield.", 1),                              # Micro Reflex Finance
            ("State the historical axiom of human society.", 2)                 # Nano Filter
        ]
        
        for q, depth in test_cases:
            res = ct.dispatch(q, depth=depth, max_tokens=85)
            winner = res["routing"]["winning_colony"].upper()
            conf = res["routing"]["confidence"] * 100
            print(f"\n📥 Query: \"{q}\"")
            print(f"🎯 Horizontal Thalamus: [{winner}] ({conf:.1f}% confidence)")
            print(f"🐇 Alice Fractal Depth: Level {depth} ➔ {res['alice_tier']}")
            print(f"🏛️  Specialist Unit: {res['specialist']}")
            print(f"⚡ Latency: {res['total_latency_s']}s ({res['tokens_per_sec']} tok/s)")
            print(f"💬 Zero-Pollution Emission:\n   \"{res['output']}\"")
            print("-" * 80)
