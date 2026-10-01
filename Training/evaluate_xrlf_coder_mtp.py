r"""
evaluate_xrlf_coder_mtp.py
==========================
Evaluate the XRLF coder MTP GGUF on code generation + XRLF tag usage.

Metrics:
  1. Code correctness — does the generated code run / parse?
  2. XRLF tag usage — does the model emit <xrl:route> tags appropriately?
  3. Code quality — length, structure, presence of error handling
  4. MTP speed test — speculative decoding speedup vs non-MTP

Usage:
    python Training\evaluate_xrlf_coder_mtp.py
    python Training\evaluate_xrlf_coder_mtp.py --speed-test
"""

import argparse
import ast
import json
import re
import sys
import time
from pathlib import Path
from llama_cpp import Llama

# ── Paths ──────────────────────────────────────────────────────────────────
MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_coder_mtp_q4_k_m.gguf")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_coder_eval.jsonl")
REPORT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\eval_reports")

SYSTEM_PROMPT = (
    "You are an XRLF coder assistant. Generate clean, correct code. "
    "Use XRLF routing tags where appropriate: <xrl:route specialist=\"code\" /> "
    "for code tasks, <xrl:route specialist=\"memory\" /> for memory operations. "
    "Follow XRL principles: precision, step-by-step reasoning, test awareness."
)


def format_prompt(user_text: str) -> str:
    return (
        "<|im_start|>system\n"
        f"{SYSTEM_PROMPT}\n"
        "<|im_end|>\n"
        f"<|im_start|>user\n{user_text}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def generate(llm: Llama, prompt: str, max_tokens: int = 1024) -> str:
    out = llm(
        prompt,
        max_tokens=max_tokens,
        stop=["<|im_end|>", "<|im_start|>"],
        temperature=0.2,
        top_p=0.92,
        top_k=40,
        repeat_penalty=1.05,
    )
    return out["choices"][0]["text"].strip()


def extract_code_blocks(text: str) -> list[str]:
    """Extract code from markdown code blocks."""
    blocks = re.findall(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    return [b.strip() for b in blocks]


def check_python_syntax(code: str) -> bool:
    """Check if Python code parses without syntax errors."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def check_xrlf_tags(text: str) -> dict:
    """Check for XRLF tag usage in the output."""
    return {
        "has_route_tag": "<xrl:route" in text,
        "has_principle_tag": "<xrl:principle>" in text,
        "route_specialists": re.findall(r'specialist="([^"]+)"', text),
        "tag_count": text.count("<xrl:"),
    }


def check_code_quality(code: str) -> dict:
    """Basic code quality metrics."""
    lines = code.strip().splitlines()
    return {
        "line_count": len(lines),
        "has_functions": "def " in code or "function " in code,
        "has_classes": "class " in code,
        "has_error_handling": "try:" in code or "try {" in code or "catch" in code,
        "has_type_hints": ": " in code and ("->" in code or "str" in code or "int" in code),
        "has_comments": "#" in code or "//" in code,
    }


def run_evaluation() -> dict:
    """Run code generation evaluation."""
    if not MODEL_PATH.exists():
        print(f"❌ GGUF not found: {MODEL_PATH}")
        sys.exit(1)
    if not EVAL_FILE.exists():
        print(f"❌ Eval file not found: {EVAL_FILE}")
        sys.exit(1)

    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        eval_data = [json.loads(line) for line in f if line.strip()]

    print("=" * 70)
    print("  XRLF Coder MTP Evaluation")
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
        n_gpu_layers=0,    # 4B won't fit fully on 8GB — keep on CPU
        verbose=False,
    )
    print(f"  Loaded in {time.time()-t0:.1f}s")

    results = []
    stats = {
        "total": 0,
        "has_code": 0,
        "python_valid": 0,
        "python_total": 0,
        "has_xrlf_tags": 0,
        "has_functions": 0,
        "has_error_handling": 0,
        "has_type_hints": 0,
        "avg_lines": 0,
    }

    for i, ex in enumerate(eval_data):
        messages = ex.get("messages", [])
        if len(messages) < 3:
            continue

        user_text = messages[1]["content"]
        expected = messages[2]["content"]

        prompt = format_prompt(user_text)
        output = generate(llm, prompt)

        code_blocks = extract_code_blocks(output)
        primary_code = code_blocks[0] if code_blocks else ""
        is_python = "python" in user_text.lower() or "def " in primary_code

        xrlf = check_xrlf_tags(output)
        quality = check_code_quality(primary_code) if primary_code else {}

        py_valid = None
        if is_python and primary_code:
            stats["python_total"] += 1
            py_valid = check_python_syntax(primary_code)
            if py_valid:
                stats["python_valid"] += 1

        stats["total"] += 1
        if code_blocks:
            stats["has_code"] += 1
        if xrlf["has_route_tag"]:
            stats["has_xrlf_tags"] += 1
        if quality.get("has_functions"):
            stats["has_functions"] += 1
        if quality.get("has_error_handling"):
            stats["has_error_handling"] += 1
        if quality.get("has_type_hints"):
            stats["has_type_hints"] += 1
        stats["avg_lines"] += quality.get("line_count", 0)

        results.append({
            "user": user_text[:100],
            "has_code": bool(code_blocks),
            "code_blocks": len(code_blocks),
            "python_valid": py_valid,
            "xrlf_tags": xrlf,
            "quality": quality,
            "output_preview": output[:300],
        })

        if (i + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(eval_data)}] {elapsed:.0f}s elapsed")

    eval_time = time.time() - t0
    n = stats["total"]
    stats["avg_lines"] = round(stats["avg_lines"] / n, 1) if n > 0 else 0

    print(f"\n{'=' * 70}")
    print(f"  Results ({eval_time:.1f}s)")
    print(f"{'=' * 70}")
    print(f"  Code generated:        {stats['has_code']}/{n} ({stats['has_code']/n*100:.0f}%)")
    if stats["python_total"] > 0:
        print(f"  Python syntax valid:   {stats['python_valid']}/{stats['python_total']} ({stats['python_valid']/stats['python_total']*100:.0f}%)")
    print(f"  XRLF tags used:        {stats['has_xrlf_tags']}/{n} ({stats['has_xrlf_tags']/n*100:.0f}%)")
    print(f"  Has functions:         {stats['has_functions']}/{n} ({stats['has_functions']/n*100:.0f}%)")
    print(f"  Has error handling:    {stats['has_error_handling']}/{n} ({stats['has_error_handling']/n*100:.0f}%)")
    print(f"  Has type hints:        {stats['has_type_hints']}/{n} ({stats['has_type_hints']/n*100:.0f}%)")
    print(f"  Avg lines per output:  {stats['avg_lines']}")

    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": timestamp,
        "model": str(MODEL_PATH),
        "eval_file": str(EVAL_FILE),
        "eval_rows": n,
        "eval_time_s": round(eval_time, 1),
        "stats": stats,
        "results": results,
    }
    report_path = REPORT_DIR / f"coder_mtp_eval_{timestamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to {report_path}")

    return report


def run_speed_test() -> None:
    """Run speculative decoding speed test to verify MTP works."""
    if not MODEL_PATH.exists():
        print(f"❌ GGUF not found: {MODEL_PATH}")
        sys.exit(1)

    print("=" * 70)
    print("  MTP Speculative Decoding Speed Test")
    print("=" * 70)

    test_prompt = format_prompt("Write a Python function that sorts a list of dictionaries by a given key.")

    # Test 1: Normal generation
    print("\n[1/2] Normal generation (no speculative)...")
    llm = Llama(model_path=str(MODEL_PATH), n_ctx=3072, n_threads=4,
                n_gpu_layers=0,
                verbose=False)
    t0 = time.time()
    out1 = llm(test_prompt, max_tokens=256, stop=["<|im_end|>"],
               temperature=0.2, top_p=0.92, top_k=40, repeat_penalty=1.05)
    normal_time = time.time() - t0
    normal_tokens = len(out1["choices"][0]["text"].split())
    print(f"  Time: {normal_time:.2f}s, Tokens: ~{normal_tokens}, Speed: {normal_tokens/normal_time:.1f} tok/s")

    # Test 2: With speculative decoding (if MTP is available)
    print("\n[2/2] Speculative decoding (if MTP available)...")
    try:
        t0 = time.time()
        out2 = llm(test_prompt, max_tokens=256, stop=["<|im_end|>"],
                   temperature=0.2, top_p=0.92, top_k=40, repeat_penalty=1.05,
                   speculative=True)
        spec_time = time.time() - t0
        spec_tokens = len(out2["choices"][0]["text"].split())
        print(f"  Time: {spec_time:.2f}s, Tokens: ~{spec_tokens}, Speed: {spec_tokens/spec_time:.1f} tok/s")
        speedup = (spec_tokens / spec_time) / (normal_tokens / normal_time)
        print(f"\n  Speedup: {speedup:.2f}x")
        if speedup > 1.1:
            print("  ✅ MTP speculative decoding is working!")
        else:
            print("  ⚠️ No significant speedup — MTP may not be active")
    except Exception as e:
        print(f"  ⚠️ Speculative decoding not supported: {str(e)[:100]}")
        print("     This may indicate MTP metadata was lost during export")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate XRLF coder MTP")
    parser.add_argument("--speed-test", action="store_true",
                        help="Run MTP speculative decoding speed test")
    args = parser.parse_args()

    if args.speed_test:
        run_speed_test()
    else:
        run_evaluation()


if __name__ == "__main__":
    main()
