r"""
evaluate_xrlf_summarizer.py
===========================
Evaluate the XRLF summarizer GGUF on the eval set.

Metrics:
  1. Compression ratio — output length / input length (target: 8-30%)
  2. Key information preservation — fraction of key terms from input found in output
  3. Semantic similarity — cosine similarity of bag-of-words vectors
  4. Per-category breakdown (code, conversation, context, xrlf)

Usage:
    python Training\evaluate_xrlf_summarizer.py
"""

import json
import re
import sys
import time
from pathlib import Path
from collections import Counter
import math
from llama_cpp import Llama

# ── Paths ──────────────────────────────────────────────────────────────────
MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_summarizer_qwen0.6b_q4_k_m.gguf")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_summarizer_eval.jsonl")
REPORT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\eval_reports")

SYSTEM_PROMPT = (
    "You are an XRLF summarizer. Compress the input to its essential skeleton. "
    "Preserve logic, structure, and key information. Drop boilerplate, comments, "
    "and redundant details. Output only the compressed version."
)


def format_prompt(user_text: str) -> str:
    return (
        "<|im_start|>system\n"
        f"{SYSTEM_PROMPT}\n"
        "<|im_end|>\n"
        f"<|im_start|>user\n{user_text}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def generate(llm: Llama, prompt: str, max_tokens: int = 512) -> str:
    out = llm(
        prompt,
        max_tokens=max_tokens,
        stop=["<|im_end|>", "<|im_start|>"],
        temperature=0.15,
        top_p=0.85,
        top_k=40,
        repeat_penalty=1.1,
    )
    return out["choices"][0]["text"].strip()


def classify_category(user_text: str) -> str:
    """Classify eval row by content type."""
    if "```" in user_text or "def " in user_text or "function " in user_text:
        return "code"
    if "conversation" in user_text.lower():
        return "conversation"
    if "xrl:" in user_text or "xrlf" in user_text.lower():
        return "xrlf"
    return "context"


def compression_ratio(output: str, input_text: str) -> float:
    """Output length / input length. Lower = more compressed."""
    if len(input_text) == 0:
        return 0
    return len(output) / len(input_text)


def key_info_preservation(output: str, input_text: str) -> float:
    """Fraction of significant input tokens found in output."""
    # Extract significant tokens (skip stop words and short tokens)
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "about", "than",
        "that", "this", "these", "those", "it", "its", "they", "them",
        "their", "there", "here", "where", "when", "what", "which", "who",
        "and", "or", "but", "not", "no", "if", "then", "so", "because",
        "you", "your", "i", "me", "my", "we", "our", "user", "s",
    }

    input_tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', input_text.lower())
    output_tokens = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', output.lower()))

    significant = [t for t in input_tokens if t not in stop_words and len(t) > 2]
    if not significant:
        return 0

    preserved = sum(1 for t in significant if t in output_tokens)
    return preserved / len(significant)


def cosine_similarity(text1: str, text2: str) -> float:
    """Bag-of-words cosine similarity."""
    tokens1 = re.findall(r'\b\w+\b', text1.lower())
    tokens2 = re.findall(r'\b\w+\b', text2.lower())

    if not tokens1 or not tokens2:
        return 0

    vec1 = Counter(tokens1)
    vec2 = Counter(tokens2)

    all_tokens = set(vec1.keys()) | set(vec2.keys())

    dot = sum(vec1.get(t, 0) * vec2.get(t, 0) for t in all_tokens)
    mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

    if mag1 == 0 or mag2 == 0:
        return 0

    return dot / (mag1 * mag2)


def main() -> None:
    if not MODEL_PATH.exists():
        print(f"❌ GGUF not found: {MODEL_PATH}")
        sys.exit(1)
    if not EVAL_FILE.exists():
        print(f"❌ Eval file not found: {EVAL_FILE}")
        sys.exit(1)

    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        eval_data = [json.loads(line) for line in f if line.strip()]

    print("=" * 70)
    print("  XRLF Summarizer Evaluation")
    print("=" * 70)
    print(f"  Model: {MODEL_PATH}")
    print(f"  Eval:  {EVAL_FILE}")
    print(f"  Rows:  {len(eval_data)}")
    print("=" * 70)

    t0 = time.time()
    llm = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=3072,
        n_threads=4,
        n_gpu_layers=-1,
        flash_attn=True,
        type_k=8,   # q8_0 KV cache
        type_v=8,   # q8_0 KV cache
        verbose=False,
    )
    print(f"  Loaded in {time.time()-t0:.1f}s")

    results = []
    category_stats: dict[str, dict] = {}

    for i, ex in enumerate(eval_data):
        messages = ex.get("messages", [])
        if len(messages) < 3:
            continue

        user_text = messages[1]["content"]
        expected = messages[2]["content"]
        category = classify_category(user_text)

        prompt = format_prompt(user_text)
        output = generate(llm, prompt)

        comp_ratio = compression_ratio(output, user_text)
        info_pres = key_info_preservation(output, user_text)
        sem_sim = cosine_similarity(output, expected)

        if category not in category_stats:
            category_stats[category] = {
                "count": 0,
                "comp_ratios": [],
                "info_pres": [],
                "sem_sims": [],
            }
        category_stats[category]["count"] += 1
        category_stats[category]["comp_ratios"].append(comp_ratio)
        category_stats[category]["info_pres"].append(info_pres)
        category_stats[category]["sem_sims"].append(sem_sim)

        results.append({
            "category": category,
            "input_length": len(user_text),
            "output_length": len(output),
            "expected_length": len(expected),
            "compression_ratio": round(comp_ratio, 4),
            "key_info_preservation": round(info_pres, 4),
            "semantic_similarity": round(sem_sim, 4),
            "output_preview": output[:200],
        })

        if (i + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(eval_data)}] {elapsed:.0f}s elapsed")

    eval_time = time.time() - t0

    # Aggregate metrics
    all_comp = [r["compression_ratio"] for r in results]
    all_info = [r["key_info_preservation"] for r in results]
    all_sem = [r["semantic_similarity"] for r in results]

    avg_comp = sum(all_comp) / len(all_comp) if all_comp else 0
    avg_info = sum(all_info) / len(all_info) if all_info else 0
    avg_sem = sum(all_sem) / len(all_sem) if all_sem else 0

    print(f"\n{'=' * 70}")
    print(f"  Overall Results ({eval_time:.1f}s)")
    print(f"{'=' * 70}")
    print(f"  Compression ratio (avg):     {avg_comp:.1%}  (target: 8-30%)")
    print(f"  Key info preservation (avg): {avg_info:.1%}  (target: >50%)")
    print(f"  Semantic similarity (avg):   {avg_sem:.3f}  (target: >0.5)")

    # Per-category breakdown
    print(f"\n  Per-category breakdown:")
    print(f"  {'Category':<15} {'Count':>6} {'Comp%':>8} {'Info%':>8} {'SemSim':>8}")
    print(f"  {'─'*15} {'─'*6} {'─'*8} {'─'*8} {'─'*8}")
    for cat in sorted(category_stats.keys()):
        stats = category_stats[cat]
        n = stats["count"]
        cat_comp = sum(stats["comp_ratios"]) / n if n > 0 else 0
        cat_info = sum(stats["info_pres"]) / n if n > 0 else 0
        cat_sem = sum(stats["sem_sims"]) / n if n > 0 else 0
        print(f"  {cat:<15} {n:>6} {cat_comp:>7.1%} {cat_info:>7.1%} {cat_sem:>8.3f}")

    # Verdict
    print(f"\n  Verdict:")
    comp_ok = 0.08 <= avg_comp <= 0.30
    info_ok = avg_info >= 0.50
    sem_ok = avg_sem >= 0.50
    print(f"    Compression ratio {'✅' if comp_ok else '❌'} ({'in range' if comp_ok else 'out of range'})")
    print(f"    Info preservation {'✅' if info_ok else '❌'} ({'good' if info_ok else 'needs improvement'})")
    print(f"    Semantic similarity {'✅' if sem_ok else '❌'} ({'good' if sem_ok else 'needs improvement'})")

    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": timestamp,
        "model": str(MODEL_PATH),
        "eval_file": str(EVAL_FILE),
        "eval_rows": len(results),
        "eval_time_s": round(eval_time, 1),
        "overall": {
            "compression_ratio": round(avg_comp, 4),
            "key_info_preservation": round(avg_info, 4),
            "semantic_similarity": round(avg_sem, 4),
        },
        "category_stats": {
            cat: {
                "count": s["count"],
                "compression_ratio": round(sum(s["comp_ratios"]) / s["count"], 4) if s["count"] > 0 else 0,
                "key_info_preservation": round(sum(s["info_pres"]) / s["count"], 4) if s["count"] > 0 else 0,
                "semantic_similarity": round(sum(s["sem_sims"]) / s["count"], 4) if s["count"] > 0 else 0,
            }
            for cat, s in category_stats.items()
        },
        "results": results,
    }
    report_path = REPORT_DIR / f"summarizer_eval_{timestamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to {report_path}")


if __name__ == "__main__":
    main()
