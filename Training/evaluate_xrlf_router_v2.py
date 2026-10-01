r"""
evaluate_xrlf_router_v2.py
==========================
Objective evaluation of the XRLF router v2 GGUF on the v2 eval set.

Supports baseline comparison (EXP-001): if the v1 GGUF also exists,
runs both and prints a side-by-side comparison.

Usage:
    python Training\evaluate_xrlf_router_v2.py
    python Training\evaluate_xrlf_router_v2.py --compare   # also eval v1
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from llama_cpp import Llama

# ── Paths ──────────────────────────────────────────────────────────────────
V2_MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_coder1.5b_q4_k_m.gguf")
V1_MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_qwen0.5b_q4_k_m.gguf")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_router_eval_v2.jsonl")
REPORT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\eval_reports")

SYSTEM_PROMPT = (
    "You are an XRLF router. Emit only a control token or a tiny XRLF tag. "
    "Do not explain."
)


def format_prompt(user_text: str) -> str:
    return (
        "<|im_start|>system\n"
        f"{SYSTEM_PROMPT}\n"
        "<|im_end|>\n"
        f"<|im_start|>user\n{user_text}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def generate(llm: Llama, prompt: str) -> str:
    out = llm(
        prompt,
        max_tokens=20,
        stop=["<|im_end|>", "<|im_start|>", "\n"],
        temperature=0.0,
        top_p=0.5,
        top_k=20,
        repeat_penalty=1.0,
    )
    return out["choices"][0]["text"].strip()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def classify_expected(expected: str) -> str:
    """Classify eval row into category for per-category breakdown."""
    exp = expected.lower().strip()
    if exp in ("stop", "solved", "continue"):
        return "control_token"
    if "<xrl:route" in exp:
        return "routing_tag"
    if exp.startswith(("<recall", "<fovea", "<compress", "<emote", "<hint", "<skeleton")):
        return "xrlf_tag"
    if exp.startswith("intent:"):
        return "intent"
    return "other"


def score_control(output: str, expected: str) -> bool:
    out = normalize(output)
    exp = normalize(expected)
    return exp in out


def score_routing(output: str, expected: str) -> bool:
    out = normalize(output)
    m = re.search(r'specialist="([^"]+)"', expected)
    if not m:
        return False
    spec = m.group(1).lower()
    has_spec = f'specialist="{spec}"' in out or spec in out
    has_route = "route" in out
    return has_route and has_spec


def score_tag(output: str, expected: str) -> bool:
    out = normalize(output)
    # Skeleton tags: check opening tag type matches, be lenient on inner content
    if expected.strip().lower().startswith("<skeleton:"):
        exp_tag = expected.strip().lower().split(">")[0] + ">"
        # Extract the skeleton type (e.g., "skeleton:code")
        m = re.match(r"<(skeleton:\w+)", exp_tag)
        if not m:
            return False
        skel_type = m.group(1)
        # Model must emit the same skeleton tag type with closing tag
        return skel_type in out and f"</{skel_type.split(':')[0]}" in out
    # Other tags: check that key substrings appear
    for tok in expected.lower().split():
        cleaned = tok.strip("<>/=\"")
        if cleaned and cleaned not in out:
            return False
    return True


def score_intent(output: str, expected: str) -> bool:
    out = normalize(output)
    exp = normalize(expected)
    # INTENT: <category> — check category matches
    m = re.search(r"intent:\s*(\S+)", exp)
    if not m:
        return exp in out
    category = m.group(1)
    return category in out and "intent" in out


def score_row(output: str, expected: str, category: str) -> bool:
    if category == "control_token":
        return score_control(output, expected)
    elif category == "routing_tag":
        return score_routing(output, expected)
    elif category == "xrlf_tag":
        return score_tag(output, expected)
    elif category == "intent":
        return score_intent(output, expected)
    else:
        return normalize(expected) in normalize(output)


def run_evaluation(
    model_path: Path,
    eval_data: list[dict],
    model_label: str,
) -> dict:
    """Run evaluation on a single model. Returns results dict."""
    print(f"\n{'─' * 60}")
    print(f"  Evaluating: {model_label}")
    print(f"  Model: {model_path}")
    print(f"  Eval rows: {len(eval_data)}")
    print(f"{'─' * 60}")

    if not model_path.exists():
        print(f"  ⚠️ Model not found, skipping: {model_path}")
        return {"label": model_label, "model": str(model_path), "skipped": True}

    t0 = time.time()
    llm = Llama(
        model_path=str(model_path),
        n_ctx=768,
        n_threads=4,
        n_gpu_layers=-1,
        flash_attn=True,
        type_k=8,   # q8_0 KV cache
        type_v=8,   # q8_0 KV cache
        verbose=False,
    )
    load_time = time.time() - t0
    print(f"  Loaded in {load_time:.1f}s")

    results = []
    category_stats: dict[str, dict] = {}

    for i, ex in enumerate(eval_data):
        user = ex["messages"][0]["content"]
        expected = ex["messages"][1]["content"]
        category = classify_expected(expected)

        prompt = format_prompt(user)
        output = generate(llm, prompt)
        passed = score_row(output, expected, category)

        if category not in category_stats:
            category_stats[category] = {"total": 0, "passed": 0}
        category_stats[category]["total"] += 1
        if passed:
            category_stats[category]["passed"] += 1

        results.append({
            "category": category,
            "user": user[:80],
            "expected": expected,
            "output": output,
            "passed": passed,
        })

        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(eval_data)}] {elapsed:.0f}s elapsed")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = passed / total * 100 if total > 0 else 0
    eval_time = time.time() - t0

    # Per-category breakdown
    print(f"\n  Per-category breakdown:")
    print(f"  {'Category':<20} {'Pass':>6} {'Total':>6} {'Acc':>8}")
    print(f"  {'─'*20} {'─'*6} {'─'*6} {'─'*8}")
    for cat in sorted(category_stats.keys()):
        stats = category_stats[cat]
        cat_acc = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  {cat:<20} {stats['passed']:>6} {stats['total']:>6} {cat_acc:>7.1f}%")

    print(f"\n  Overall: {passed}/{total} = {accuracy:.1f}% ({eval_time:.1f}s)")

    return {
        "label": model_label,
        "model": str(model_path),
        "total": total,
        "passed": passed,
        "accuracy": round(accuracy, 2),
        "eval_time_s": round(eval_time, 1),
        "category_stats": {
            cat: {
                "total": s["total"],
                "passed": s["passed"],
                "accuracy": round(s["passed"] / s["total"] * 100, 2) if s["total"] > 0 else 0,
            }
            for cat, s in category_stats.items()
        },
        "results": results,
        "skipped": False,
    }


def print_comparison(v1_result: dict, v2_result: dict) -> None:
    """Print side-by-side comparison for EXP-001."""
    print("\n" + "=" * 70)
    print("  EXP-001: Router 1.5B (Coder) vs 0.5B — Comparison")
    print("=" * 70)

    if v1_result.get("skipped") or v2_result.get("skipped"):
        print("  ⚠️ One or both models skipped — cannot compare")
        return

    print(f"\n  {'Metric':<25} {'0.5B (v1)':>12} {'1.5B Coder (v2)':>16} {'Delta':>10}")
    print(f"  {'─'*25} {'─'*12} {'─'*16} {'─'*10}")

    v1_acc = v1_result["accuracy"]
    v2_acc = v2_result["accuracy"]
    delta = v2_acc - v1_acc
    print(f"  {'Overall Accuracy':<25} {v1_acc:>11.1f}% {v2_acc:>15.1f}% {delta:>+9.1f}%")

    v1_time = v1_result["eval_time_s"]
    v2_time = v2_result["eval_time_s"]
    print(f"  {'Eval Time (s)':<25} {v1_time:>12.1f} {v2_time:>16.1f} {v2_time-v1_time:>+10.1f}")

    # Per-category comparison
    all_cats = sorted(set(list(v1_result.get("category_stats", {}).keys()) +
                         list(v2_result.get("category_stats", {}).keys())))
    print(f"\n  {'Category':<25} {'0.5B':>12} {'1.5B Coder':>16} {'Delta':>10}")
    print(f"  {'─'*25} {'─'*12} {'─'*16} {'─'*10}")
    for cat in all_cats:
        v1_cat = v1_result.get("category_stats", {}).get(cat, {"accuracy": 0})
        v2_cat = v2_result.get("category_stats", {}).get(cat, {"accuracy": 0})
        v1_a = v1_cat["accuracy"]
        v2_a = v2_cat["accuracy"]
        d = v2_a - v1_a
        print(f"  {cat:<25} {v1_a:>11.1f}% {v2_a:>15.1f}% {d:>+9.1f}%")

    # Verdict
    print(f"\n  Verdict: ", end="")
    if delta > 5:
        print(f"1.5B Coder is significantly better (+{delta:.1f}%)")
    elif delta > 1:
        print(f"1.5B Coder is slightly better (+{delta:.1f}%)")
    elif delta > -1:
        print(f"Roughly equivalent ({delta:+.1f}%) — 0.5B may be preferred for size")
    elif delta > -5:
        print(f"1.5B Coder is slightly worse ({delta:.1f}%) — unexpected")
    else:
        print(f"1.5B Coder is significantly worse ({delta:.1f}%) — investigate")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate XRLF router v2")
    parser.add_argument("--compare", action="store_true",
                        help="Also evaluate v1 (0.5B) for EXP-001 comparison")
    args = parser.parse_args()

    if not EVAL_FILE.exists():
        print(f"❌ Eval file not found: {EVAL_FILE}")
        sys.exit(1)

    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        eval_data = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(eval_data)} eval rows from {EVAL_FILE}")

    # Evaluate v2
    v2_result = run_evaluation(V2_MODEL_PATH, eval_data, "v2 (1.5B Coder)")

    # Optionally evaluate v1 for comparison
    v1_result = None
    if args.compare:
        v1_result = run_evaluation(V1_MODEL_PATH, eval_data, "v1 (0.5B)")

    # Print comparison if both ran
    if v1_result and v2_result:
        print_comparison(v1_result, v2_result)

    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": timestamp,
        "eval_file": str(EVAL_FILE),
        "eval_rows": len(eval_data),
        "v2_result": {k: v for k, v in v2_result.items() if k != "results"},
    }
    if v1_result:
        report["v1_result"] = {k: v for k, v in v1_result.items() if k != "results"}
        report["comparison"] = {
            "v1_accuracy": v1_result.get("accuracy", 0),
            "v2_accuracy": v2_result.get("accuracy", 0),
            "delta": round(v2_result.get("accuracy", 0) - v1_result.get("accuracy", 0), 2),
        }

    report_path = REPORT_DIR / f"router_eval_{timestamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {report_path}")

    # Also save detailed results
    detail_path = REPORT_DIR / f"router_eval_{timestamp}_detailed.json"
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump({"v2_result": v2_result, "v1_result": v1_result}, f, indent=2)
    print(f"Detailed results saved to {detail_path}")


if __name__ == "__main__":
    main()
