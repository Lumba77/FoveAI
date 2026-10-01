"""
xrl_pack_qwopus9b.py — Build qwopus3.5-9b-coder-mtp-moq.xrlf
=============================================================
Two stages:

  1. XRL analysis — loads the GGUF once, traces semantic threads over a set of
     probe prompts, and derives principles / graph / clusters / expansion
     artifacts (same pipeline as xrl_process_qwen4b_gguf.py).

  2. Pack — assembles the .xrlf binary via formats/xrlf_packer.XRLFPacker:
       CORE_GGUF          (MoQ-4.6, ~5.1 GB)
       CORE_MMPROJ        (BF16 projector, ~0.9 GB — vision via projector)
       XRL_*              (artifacts from stage 1)
       XRL_MM_HOOKS       (external TTS :8406 / STT :8409 — text-native core)
       XRL_MEMORY_DATA    (live foveated memory DB — transplanted from gemma cache)
       XRL_MEMORY_SCHEMA  (default 6-ring)
       RUNTIME_META

Usage:
    .venv/bin/python xrl_pack_qwopus9b.py            # full pipeline
    .venv/bin/python xrl_pack_qwopus9b.py --pack-only  # reuse existing artifacts
"""

import json
import math
import os
import sys

# -----------------------------------------------------------
# CONFIG
# -----------------------------------------------------------

GGUF_MODEL_PATH = os.path.join("models", "gguf", "Qwen3.5-9B-MoQ-3.6.gguf")
MMPROJ_PATH = os.path.join("models", "gguf", "mmproj-qwen35-9b-Q8_0.gguf")
MEMORY_DB_PATH = "memory.db.backup-20260919"  # transplanted foveated memory

WORK_DIR = os.path.abspath(os.path.dirname(__file__))
XRL_DIR = os.path.join(WORK_DIR, "xrl_encoded", "qwopus9b_artifacts")
OUT_XRLF = os.path.join(WORK_DIR, "xrl_encoded", "qwopus3.5-9b-coder-mtp-moq.xrlf")

os.makedirs(XRL_DIR, exist_ok=True)

# Probe prompts — mix of general + coding, this is a coder-weighted model
THREAD_PROMPTS = [
    "Explain semantic compression.",
    "Write a Python function that adds two numbers.",
    "Describe pruning vs quantization.",
    "Summarize the concept of attention in transformers.",
    "Implement a retry loop with exponential backoff in Python.",
    "Debug: a FastAPI endpoint returns 500 only under load. What do you check first?",
    "Refactor a nested for-loop into a comprehension and explain the trade-off.",
    "Explain the difference between a process and a thread to a friend.",
]


# -----------------------------------------------------------
# LAYER 0 — GGUF MODEL LOAD
# -----------------------------------------------------------


def load_gguf_model():
    from llama_cpp import Llama

    import llama_bridge.llama_engine  # noqa: F401 — preloads in-venv CUDA 13 libs

    print(f"=== Loading GGUF model from: {GGUF_MODEL_PATH} ===")
    llm = Llama(
        model_path=GGUF_MODEL_PATH,
        n_ctx=4096,
        n_gpu_layers=-1,
    )
    print("=== GGUF model loaded ===\n")
    return llm


# -----------------------------------------------------------
# LAYER 1 — XRL THREADING
# -----------------------------------------------------------


def xrl_trace_threads_gguf(llm):
    print("=== XRL threading: tracing semantic paths ===")
    threads = []

    for prompt in THREAD_PROMPTS:
        result = llm(prompt, max_tokens=128, echo=True, temperature=0.7)
        text = result["choices"][0]["text"]
        logits_seq = result.get("logits", None)

        if logits_seq is None:
            threads.append(
                {
                    "prompt": prompt,
                    "thread": {
                        "text": text,
                        "note": "logits not available; text-only thread",
                    },
                }
            )
            continue

        confidence_path = [
            {"step": i, "avg_logit_strength": sum(abs(l) for l in step) / len(step)}
            for i, step in enumerate(logits_seq)
        ]
        threads.append(
            {
                "prompt": prompt,
                "thread": {"text": text, "confidence_path": confidence_path},
            }
        )

    path = os.path.join(XRL_DIR, "threads_gguf.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(threads, f, indent=2)
    print(f"=== threads → {path} ===\n")
    return threads


# -----------------------------------------------------------
# LAYER 2 — XRL PRINCIPATION
# -----------------------------------------------------------


def xrl_principiate_gguf(threads):
    print("=== XRL principiation ===")
    principles = []

    for t in threads:
        prompt = t["prompt"]
        thread = t["thread"]
        text = thread.get("text", "")
        confidence_path = thread.get("confidence_path", None)

        if not confidence_path:
            principles.append(
                {
                    "prompt": prompt,
                    "text_preview": text[:120],
                    "principle_strength": None,
                    "volatility": None,
                    "trend": None,
                    "role": "text_only_thread",
                    "note": "no confidence path available",
                }
            )
            continue

        strengths = [s["avg_logit_strength"] for s in confidence_path]
        avg = sum(strengths) / len(strengths)
        var = sum((s - avg) ** 2 for s in strengths) / len(strengths)
        volatility = math.sqrt(var)

        split = max(1, len(strengths) // 3)
        early_avg = sum(strengths[:split]) / split
        late_avg = sum(strengths[-split:]) / split
        delta = late_avg - early_avg
        trend = (
            "strengthening" if delta > 0 else ("weakening" if delta < 0 else "stable")
        )

        if avg > 0 and volatility < avg * 0.1:
            role = "confident_consistent_sequence"
        elif volatility > avg * 0.5:
            role = "highly_volatile_sequence"
        else:
            role = "mixed_confidence_sequence"

        principles.append(
            {
                "prompt": prompt,
                "text_preview": text[:160],
                "principle_strength": avg,
                "volatility": volatility,
                "trend": trend,
                "role": role,
                "early_strength": early_avg,
                "late_strength": late_avg,
            }
        )

    path = os.path.join(XRL_DIR, "principles_gguf.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(principles, f, indent=2)
    print(f"=== principles → {path} ===\n")
    return principles


# -----------------------------------------------------------
# LAYER 3 — SEMANTIC GRAPH → CLUSTERS → EXPANSION
# -----------------------------------------------------------


def xrl_semantic_graph_gguf(threads):
    print("=== XRL semantic graph ===")
    graph = {"nodes": {}, "edges": []}

    for t in threads:
        thread = t["thread"]
        text = thread.get("text", "")
        confidence_path = thread.get("confidence_path", None)
        if not confidence_path:
            continue
        tokens = text.split()
        if len(tokens) < 2:
            continue
        strengths = [s["avg_logit_strength"] for s in confidence_path]
        avg = sum(strengths) / len(strengths)

        for tok in tokens:
            node = graph["nodes"].setdefault(
                tok, {"count": 0, "strength_sum": 0.0, "prompts": []}
            )
            node["count"] += 1
            node["strength_sum"] += avg
            node["prompts"].append(t["prompt"])
        for i in range(len(tokens) - 1):
            graph["edges"].append(
                {"from": tokens[i], "to": tokens[i + 1], "strength": avg}
            )

    for info in graph["nodes"].values():
        info["importance"] = info["strength_sum"] / max(1, info["count"])

    path = os.path.join(XRL_DIR, "semantic_graph_gguf.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    print(f"=== graph → {path} ===\n")
    return graph


def xrl_graph_clustering_gguf(graph):
    print("=== XRL graph clustering ===")
    clusters = {}
    for tok, info in graph["nodes"].items():
        imp = info.get("importance", 0)
        bucket = (
            "high_importance"
            if imp > 5
            else ("medium_importance" if imp > 2 else "low_importance")
        )
        clusters.setdefault(bucket, []).append(
            {
                "token": tok,
                "importance": imp,
                "count": info["count"],
                "prompts": info["prompts"],
            }
        )
    path = os.path.join(XRL_DIR, "semantic_clusters_gguf.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clusters, f, indent=2)
    print(f"=== clusters → {path} ===\n")
    return clusters


def xrl_graph_expansion_gguf(clusters):
    print("=== XRL graph expansion ===")
    expansions = []
    for name, items in clusters.items():
        top = sorted(items, key=lambda x: x["importance"], reverse=True)[:3]
        toks = [t["token"] for t in top]
        if len(toks) < 3:
            continue
        expansions.append(
            {
                "cluster": name,
                "tokens": toks,
                "generated_prompts": [
                    f"Explain the relationship between {toks[0]} and {toks[1]}.",
                    f"Describe how {toks[0]} influences {toks[2]}.",
                    f"What is the role of {toks[1]} in {toks[2]}?",
                ],
            }
        )
    path = os.path.join(XRL_DIR, "semantic_expansion_gguf.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(expansions, f, indent=2)
    print(f"=== expansion → {path} ===\n")
    return expansions


# -----------------------------------------------------------
# STAGE 2 — PACK
# -----------------------------------------------------------


def pack():
    from formats.xrlf_packer import DEFAULT_MM_HOOKS, XRLFPacker
    from formats.xrlf_schema import XRLFFlags

    # Qwen 9B flags: MoQ core, multimodal via mmproj (not native), no native STT
    # (Whisper :8409), persistent embedded memory, MM hooks enabled.
    qwen_flags = (
        XRLFFlags.HAS_CORE_GGUF
        | XRLFFlags.IS_MULTIMODAL
        | XRLFFlags.HAS_MM_HOOKS
        | XRLFFlags.HAS_EMBEDDED_MEMORY
        | XRLFFlags.HAS_MEMORY_SCHEMA
        | XRLFFlags.MEMORY_PERSISTENT
        | XRLFFlags.CORE_IS_GGUF_MoQ
        | XRLFFlags.HAS_MMPROJ
    )

    # Hooks: vision via mmproj, no native audio-in (external Whisper),
    # TTS via Kokoro service on :8406.
    hooks = json.loads(json.dumps(DEFAULT_MM_HOOKS))  # deep copy
    hooks["native_multimodal"]["audio_in"] = False
    hooks["native_multimodal"]["video_in"] = False
    hooks["external_hooks"]["tts"]["endpoint"] = "http://127.0.0.1:8406/tts"
    hooks["external_hooks"]["stt"] = {
        "enabled": True,
        "engine": "whisper",
        "endpoint": "ws://127.0.0.1:8409",
    }

    packer = XRLFPacker(
        base_model_name="qwopus3.5-9b-coder-mtp-moq",
        xrl_source_model="qwen3.5-9b",
        flags=int(qwen_flags),
    )
    packer.add_gguf(GGUF_MODEL_PATH)
    if os.path.exists(MMPROJ_PATH):
        packer.add_mmproj(MMPROJ_PATH)
    packer.add_xrl_json_dir(XRL_DIR)
    packer.add_multimodal_hooks(hooks)
    packer.add_memory_db(MEMORY_DB_PATH if os.path.exists(MEMORY_DB_PATH) else None)
    packer.add_memory_schema()
    packer.add_runtime_meta()
    packer.write(OUT_XRLF)


def main():
    pack_only = "--pack-only" in sys.argv
    if not pack_only:
        llm = load_gguf_model()
        threads = xrl_trace_threads_gguf(llm)
        xrl_principiate_gguf(threads)
        graph = xrl_semantic_graph_gguf(threads)
        clusters = xrl_graph_clustering_gguf(graph)
        xrl_graph_expansion_gguf(clusters)
        del llm  # free VRAM before packing

    pack()
    print(f"\n=== DONE → {OUT_XRLF} ===")


if __name__ == "__main__":
    main()
