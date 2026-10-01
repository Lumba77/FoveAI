r"""
preflight_xrlf_router.py
========================
Go/no-go preflight gate for the XRLF router GGUF.

Runs a critical subset of prompts and exits with code 0 only if the
pass rate meets or exceeds the threshold.

Usage:
    python Training\preflight_xrlf_router.py
"""

import json
import re
import sys
from pathlib import Path
from llama_cpp import Llama

MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_qwen0.5b_q4_k_m.gguf")
PASS_THRESHOLD = 0.80

CRITICAL_CASES = [
    ("solved-basic", "XRLF: judge whether this user query can be answered in one step.\nQuery: What is 8 * 7?", "solved"),
    ("solved-fact", "XRLF: judge whether this user query can be answered in one step.\nQuery: Who wrote 1984?", "solved"),
    ("continue-hard", "XRLF: judge whether this user query can be answered in one step.\nQuery: Prove the Riemann Hypothesis.", "continue"),
    ("continue-hard-2", "XRLF: judge whether this user query can be answered in one step.\nQuery: Explain the causes of the French Revolution in detail.", "continue"),
    ("route-code", "XRLF: route this query.\nQuery: fix this Python recursion error", "code"),
    ("route-memory", "XRLF: route this query.\nQuery: remember the name of that project from two days ago", "memory"),
    ("route-audio", "XRLF: route this query.\nQuery: make the background music sadder", "audio"),
    ("tag-complex", "XRLF: tag this user signal.\nSignal: user wants help with a multi-step integration", "<think"),
    ("intent-recall", "XRLF: extract intent.\nInput: I can't find the file from last week.", "recall"),
    ("intent-code", "XRLF: extract intent.\nInput: This function keeps returning None.", "debug"),
]


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


def check(output, expected):
    out = re.sub(r"\s+", " ", output.lower().strip())
    exp = expected.lower().strip()
    # Tags like <route:... may be output with spaces, treat as substring
    if exp.startswith("<") and exp in out:
        return True
    if exp in out:
        return True
    # For expected tokens like 'code', 'memory', 'audio', 'debug', 'recall'
    # ensure it is a standalone / meaningful substring in a router tag
    if re.search(rf"\b{re.escape(exp)}\b", out):
        return True
    return False


def main():
    print("=" * 60)
    print("  XRLF Router Preflight")
    print("=" * 60)

    if not MODEL_PATH.exists():
        print(f"❌ GGUF not found: {MODEL_PATH}")
        sys.exit(1)

    llm = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=1024,
        n_threads=4,
        verbose=False,
    )

    results = []
    for name, user, expected in CRITICAL_CASES:
        output = generate(llm, format_prompt(user))
        passed = check(output, expected)
        results.append({"name": name, "expected": expected, "output": output, "passed": passed})
        status = "✅" if passed else "❌"
        print(f"{status} {name:20} → {output!r}")

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    rate = passed / total

    print("=" * 60)
    print(f"  Pass rate: {passed}/{total} ({rate*100:.1f}%)")

    report_path = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_preflight_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"passed": passed, "total": total, "rate": rate, "results": results}, f, indent=2)
    print(f"  Report    : {report_path}")

    if rate >= PASS_THRESHOLD:
        print("  ✅ PREFLIGHT PASSED")
        sys.exit(0)
    else:
        print(f"  ❌ PREFLIGHT FAILED (threshold {PASS_THRESHOLD*100:.0f}%)")
        sys.exit(1)


if __name__ == "__main__":
    main()
