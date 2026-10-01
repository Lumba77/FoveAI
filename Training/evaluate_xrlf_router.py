r"""
evaluate_xrlf_router.py
=======================
Objective evaluation of the XRLF router GGUF on a golden eval set.

Usage:
    python Training\evaluate_xrlf_router.py
"""

import json
import re
import sys
from pathlib import Path
from llama_cpp import Llama

MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_qwen0.5b_q4_k_m.gguf")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_router_eval.jsonl")


def format_prompt(user_text):
    return (
        "<|im_start|>system\n"
        "You are an XRLF router. Emit only a control token or a tiny XRLF tag. Do not explain.\n"
        "।\n"
        f"<|im_start|>user\n{user_text}।\n"
        "<|im_start|>assistant\n"
    )


def generate(llm, prompt):
    out = llm(
        prompt,
        max_tokens=40,
        stop=["।", "<|im_start|>", "<|endoftext|>", "\n"],
        temperature=0.1,
    )
    return out["choices"][0]["text"].strip()


def normalize(text):
    return re.sub(r"\s+", " ", text.lower().strip())


def score_control(output, expected):
    out = normalize(output)
    exp = normalize(expected)
    if exp in out:
        return True
    # synonyms / fuzzy
    if exp in ["solved", "continue"]:
        return exp in out
    return False


def score_routing(output, expected):
    out = normalize(output)
    # Expected looks like <xrl:route specialist="code" />
    m = re.search(r'specialist=\"([^\"]+)\"', expected)
    if not m:
        return False
    spec = m.group(1).lower()
    has_spec = f'specialist="{spec}"' in out or spec in out
    has_route = "route" in out
    return has_route and has_spec


def score_tag(output, expected):
    out = normalize(output)
    # Check that key substrings appear
    for tok in expected.lower().split():
        if tok.strip("<>") not in out:
            return False
    return True


def main():
    if not MODEL_PATH.exists():
        print(f"❌ GGUF not found: {MODEL_PATH}")
        sys.exit(1)
    if not EVAL_FILE.exists():
        print(f"❌ Eval file not found: {EVAL_FILE}")
        sys.exit(1)

    llm = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=1024,
        n_threads=4,
        verbose=False,
    )

    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        evals = [json.loads(line) for line in f if line.strip()]

    results = []
    for ex in evals:
        user = ex["messages"][0]["content"]
        expected = ex["messages"][1]["content"]
        prompt = format_prompt(user)
        output = generate(llm, prompt)

        if "<xrl:route" in expected:
            passed = score_routing(output, expected)
        elif expected.startswith(("<recall", "<fovea", "<compress", "<emote", "INTENT:")):
            passed = score_tag(output, expected)
        else:
            passed = score_control(output, expected)

        results.append({
            "user": user,
            "expected": expected,
            "output": output,
            "passed": passed,
        })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = passed / total * 100

    print("=" * 70)
    print("  XRLF Router Evaluation")
    print("=" * 70)
    print(f"  Model : {MODEL_PATH}")
    print(f"  Eval  : {EVAL_FILE}")
    print(f"  Total : {total}")
    print(f"  Pass  : {passed}")
    print(f"  Fail  : {total - passed}")
    print(f"  Acc   : {accuracy:.1f}%")
    print("=" * 70)

    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"{status} E: {r['expected']!r}")
        print(f"      G: {r['output']!r}")

    # Save report
    report_path = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_eval_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"accuracy": accuracy, "passed": passed, "total": total, "results": results}, f, indent=2)
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
