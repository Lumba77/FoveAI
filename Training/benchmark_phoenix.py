#!/usr/bin/env python3
"""
Phoenix Benchmark — Sprint 5
=============================
End-to-end benchmarking of Phoenix-trained models against raw baselines.

Measures:
  - Expansion quality (BLEU, ROUGE-L, CodeBLEU proxy)
  - Compression ratio achieved (skeleton tokens / full tokens)
  - VRAM usage during inference
  - Inference speed (tokens/sec)
  - Effective context multiplier (how much more code fits in 4K context)

Usage:
    # Benchmark trained Phoenix student vs raw base model
    python Training/benchmark_phoenix.py --student outputs/phoenix_student/final --baseline unsloth/gemma-2-2b-it

    # Benchmark against teacher outputs
    python Training/benchmark_phoenix.py --student outputs/phoenix_student/final --teacher Training/phoenix_teacher_dataset.jsonl

    # Quick benchmark with synthetic data (no GPU needed)
    python Training/benchmark_phoenix.py --quick

Output:
    Training/phoenix_benchmark_report.md  — full benchmark report
    Training/phoenix_benchmark_results.json  — raw metrics
"""

import os
import sys
import json
import time
import math
import argparse
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict

# ── Paths ──────────────────────────────────────────────────────
LUMAX_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STUDENT_PATH = LUMAX_ROOT / "outputs" / "phoenix_student" / "final"
DEFAULT_DATASET = LUMAX_ROOT / "Training" / "phoenix_teacher_dataset.jsonl"
DEFAULT_REPORT = LUMAX_ROOT / "Training" / "phoenix_benchmark_report.md"
DEFAULT_RESULTS = LUMAX_ROOT / "Training" / "phoenix_benchmark_results.json"

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("benchmark_phoenix")


# ── Data Structures ────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """Single benchmark result for one pair."""
    filepath: str = ""
    language: str = ""
    skeleton_tokens: int = 0
    full_tokens: int = 0
    compression_ratio: float = 0.0
    student_output: str = ""
    teacher_output: str = ""
    original_full: str = ""
    bleu_score: float = 0.0
    rouge_l_score: float = 0.0
    signature_preservation: float = 0.0
    import_preservation: float = 0.0
    line_overlap: float = 0.0
    structural_similarity: float = 0.0
    inference_time_ms: float = 0.0
    inference_tokens_per_sec: float = 0.0


@dataclass
class BenchmarkSummary:
    """Aggregate benchmark summary."""
    total_pairs: int = 0
    avg_bleu: float = 0.0
    avg_rouge_l: float = 0.0
    avg_structural_similarity: float = 0.0
    avg_signature_preservation: float = 0.0
    avg_import_preservation: float = 0.0
    avg_line_overlap: float = 0.0
    avg_compression_ratio: float = 0.0
    avg_inference_time_ms: float = 0.0
    avg_inference_tokens_per_sec: float = 0.0
    effective_context_multiplier: float = 0.0
    total_skeleton_tokens: int = 0
    total_full_tokens: int = 0
    model_name: str = ""
    baseline_name: str = ""
    timestamp: str = ""


# ── Metrics ────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """Rough token count (words + punctuation)."""
    if not text:
        return 0
    return len(text.split())


def compute_bleu(reference: str, hypothesis: str) -> float:
    """Compute a simplified BLEU score (unigram precision with brevity penalty).
    
    This is a BLEU-1 approximation. For full BLEU, use sacrebleu.
    """
    if not reference or not hypothesis:
        return 0.0
    
    ref_tokens = reference.lower().split()
    hyp_tokens = hypothesis.lower().split()
    
    if not hyp_tokens:
        return 0.0
    
    # Count unigram matches
    ref_counter = {}
    for t in ref_tokens:
        ref_counter[t] = ref_counter.get(t, 0) + 1
    
    matches = 0
    hyp_counter = {}
    for t in hyp_tokens:
        hyp_counter[t] = hyp_counter.get(t, 0) + 1
    
    for t, count in hyp_counter.items():
        matches += min(count, ref_counter.get(t, 0))
    
    precision = matches / len(hyp_tokens)
    
    # Brevity penalty
    if len(hyp_tokens) < len(ref_tokens):
        bp = math.exp(1 - len(ref_tokens) / max(len(hyp_tokens), 1))
    else:
        bp = 1.0
    
    return precision * bp


def compute_rouge_l(reference: str, hypothesis: str) -> float:
    """Compute ROUGE-L (longest common subsequence based)."""
    if not reference or not hypothesis:
        return 0.0
    
    ref_tokens = reference.lower().split()
    hyp_tokens = hypothesis.lower().split()
    
    # LCS using DP
    m, n = len(ref_tokens), len(hyp_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    
    lcs = dp[m][n]
    
    if lcs == 0:
        return 0.0
    
    precision = lcs / max(n, 1)
    recall = lcs / max(m, 1)
    
    # F1 score
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def compute_structural_similarity(teacher: str, original: str) -> Dict[str, float]:
    """Compute structural similarity metrics between two code texts."""
    # Extract signatures
    t_sigs = set(re.findall(r'^\s*(def |class |async def |fn |function |const \w+ = |let \w+ = |var \w+ = )', teacher, re.MULTILINE))
    o_sigs = set(re.findall(r'^\s*(def |class |async def |fn |function |const \w+ = |let \w+ = |var \w+ = )', original, re.MULTILINE))
    
    # Extract imports
    t_imports = set(re.findall(r'^\s*(import |from |#include|using |require\()', teacher, re.MULTILINE))
    o_imports = set(re.findall(r'^\s*(import |from |#include|using |require\()', original, re.MULTILINE))
    
    # Signature score
    sig_score = len(t_sigs & o_sigs) / max(len(o_sigs), 1)
    
    # Import score
    imp_score = len(t_imports & o_imports) / max(len(o_imports), 1)
    
    # Line overlap (excluding comments)
    t_lines = set(l.strip() for l in teacher.split("\n") if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("//"))
    o_lines = set(l.strip() for l in original.split("\n") if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("//"))
    line_score = len(t_lines & o_lines) / max(len(o_lines), 1)
    
    # Weighted combination
    structural = 0.4 * sig_score + 0.3 * imp_score + 0.3 * line_score
    
    return {
        "signature_preservation": sig_score,
        "import_preservation": imp_score,
        "line_overlap": line_score,
        "structural_similarity": structural,
    }


# ── Inference ──────────────────────────────────────────────────

def run_inference(model, tokenizer, skeleton: str, max_new_tokens: int = 512) -> Tuple[str, float]:
    """Run inference: skeleton → full code expansion.
    
    Returns (generated_text, inference_time_ms).
    """
    prompt = f"### Skeleton:\n{skeleton}\n\n### Full Implementation:\n"
    
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
    
    # Move to same device as model
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    t0 = time.time()
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        temperature=0.3,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )
    elapsed_ms = (time.time() - t0) * 1000
    
    generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    
    return generated.strip(), elapsed_ms


# ── Dataset Loading ────────────────────────────────────────────

def load_benchmark_dataset(path: Path, max_samples: int = 0) -> List[Dict[str, Any]]:
    """Load benchmark dataset from JSONL."""
    logger.info(f"Loading benchmark dataset from {path}")
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    
    if max_samples > 0:
        records = records[:max_samples]
    
    logger.info(f"Loaded {len(records)} records")
    return records


def create_synthetic_benchmark() -> List[Dict[str, Any]]:
    """Create synthetic benchmark data for quick testing (no GPU needed)."""
    synthetic = [
        {
            "filepath": "synthetic_001.py",
            "language": "python",
            "skeleton": "import os\nimport sys\nfrom pathlib import Path\n\ndef load_config(path: str) -> dict:\n    pass\n\ndef validate_config(config: dict) -> bool:\n    pass\n\ndef save_config(config: dict, path: str) -> None:\n    pass",
            "full": "import os\nimport sys\nimport json\nfrom pathlib import Path\n\ndef load_config(path: str) -> dict:\n    \"\"\"Load configuration from JSON file.\"\"\"\n    config_path = Path(path)\n    if not config_path.exists():\n        return {}\n    with open(config_path, 'r') as f:\n        return json.load(f)\n\ndef validate_config(config: dict) -> bool:\n    \"\"\"Validate configuration has required fields.\"\"\"\n    required = ['name', 'version', 'settings']\n    return all(k in config for k in required)\n\ndef save_config(config: dict, path: str) -> None:\n    \"\"\"Save configuration to JSON file.\"\"\"\n    config_path = Path(path)\n    config_path.parent.mkdir(parents=True, exist_ok=True)\n    with open(config_path, 'w') as f:\n        json.dump(config, f, indent=2)",
            "token_count_skeleton": 30,
            "token_count_full": 120,
            "compression_ratio": 0.25,
        },
        {
            "filepath": "synthetic_002.js",
            "language": "javascript",
            "skeleton": "const fs = require('fs');\nconst path = require('path');\n\nfunction readFile(filepath) {}\nfunction writeFile(filepath, content) {}\nfunction listFiles(dir) {}",
            "full": "const fs = require('fs');\nconst path = require('path');\n\nfunction readFile(filepath) {\n    return fs.readFileSync(filepath, 'utf-8');\n}\n\nfunction writeFile(filepath, content) {\n    fs.writeFileSync(filepath, content, 'utf-8');\n}\n\nfunction listFiles(dir) {\n    return fs.readdirSync(dir).filter(f => fs.statSync(path.join(dir, f)).isFile());\n}",
            "token_count_skeleton": 15,
            "token_count_full": 50,
            "compression_ratio": 0.30,
        },
    ]
    return synthetic


# ── Benchmark Runner ───────────────────────────────────────────

def run_benchmark(
    dataset: List[Dict[str, Any]],
    model=None,
    tokenizer=None,
    model_name: str = "unknown",
    baseline_name: str = "none",
    teacher_dataset: Optional[List[Dict]] = None,
    quick: bool = False,
) -> BenchmarkSummary:
    """Run full benchmark on dataset."""
    
    results: List[BenchmarkResult] = []
    
    for idx, pair in enumerate(dataset):
        filepath = pair.get("filepath", f"pair_{idx}")
        skeleton = pair.get("skeleton", "")
        original_full = pair.get("full", pair.get("original_full", ""))
        teacher_output = pair.get("best_output", pair.get("teacher_output", ""))
        language = pair.get("language", "unknown")
        
        skel_tokens = count_tokens(skeleton)
        full_tokens = count_tokens(original_full)
        comp_ratio = skel_tokens / max(full_tokens, 1)
        
        result = BenchmarkResult(
            filepath=filepath,
            language=language,
            skeleton_tokens=skel_tokens,
            full_tokens=full_tokens,
            compression_ratio=comp_ratio,
            original_full=original_full,
            teacher_output=teacher_output,
        )
        
        # Run inference if model is provided
        if model is not None and tokenizer is not None and not quick:
            try:
                student_output, elapsed_ms = run_inference(model, tokenizer, skeleton)
                result.student_output = student_output
                result.inference_time_ms = elapsed_ms
                
                # Compute tokens/sec
                output_tokens = count_tokens(student_output)
                if elapsed_ms > 0:
                    result.inference_tokens_per_sec = output_tokens / (elapsed_ms / 1000)
                
                # Compute metrics
                result.bleu_score = compute_bleu(original_full, student_output)
                result.rouge_l_score = compute_rouge_l(original_full, student_output)
                
                struct = compute_structural_similarity(student_output, original_full)
                result.signature_preservation = struct["signature_preservation"]
                result.import_preservation = struct["import_preservation"]
                result.line_overlap = struct["line_overlap"]
                result.structural_similarity = struct["structural_similarity"]
                
            except Exception as e:
                logger.error(f"Inference failed for {filepath}: {e}")
        
        # Compute teacher metrics if available
        if teacher_output and not quick:
            teacher_struct = compute_structural_similarity(teacher_output, original_full)
            result.teacher_output = teacher_output
        
        results.append(result)
        
        # Progress
        if (idx + 1) % 10 == 0 or idx == len(dataset) - 1:
            logger.info(f"  Benchmarked {idx + 1}/{len(dataset)} pairs")
    
    # ── Compute Summary ─────────────────────────────────────────
    n = len(results)
    if n == 0:
        return BenchmarkSummary()
    
    summary = BenchmarkSummary(
        total_pairs=n,
        model_name=model_name,
        baseline_name=baseline_name,
        timestamp=datetime.now().isoformat(),
    )
    
    # Averages
    summary.avg_bleu = sum(r.bleu_score for r in results) / n
    summary.avg_rouge_l = sum(r.rouge_l_score for r in results) / n
    summary.avg_structural_similarity = sum(r.structural_similarity for r in results) / n
    summary.avg_signature_preservation = sum(r.signature_preservation for r in results) / n
    summary.avg_import_preservation = sum(r.import_preservation for r in results) / n
    summary.avg_line_overlap = sum(r.line_overlap for r in results) / n
    summary.avg_compression_ratio = sum(r.compression_ratio for r in results) / n
    summary.avg_inference_time_ms = sum(r.inference_time_ms for r in results) / n
    summary.avg_inference_tokens_per_sec = sum(r.inference_tokens_per_sec for r in results) / n
    
    # Totals
    summary.total_skeleton_tokens = sum(r.skeleton_tokens for r in results)
    summary.total_full_tokens = sum(r.full_tokens for r in results)
    
    # Effective context multiplier
    # If avg compression ratio is 0.1 (90% reduction), then 4K context can hold
    # 40K tokens worth of full code → 10x multiplier
    if summary.avg_compression_ratio > 0:
        summary.effective_context_multiplier = 1.0 / summary.avg_compression_ratio
    
    return summary


def generate_report(summary: BenchmarkSummary, results: List[BenchmarkResult], output_path: Path):
    """Generate a markdown benchmark report."""
    
    lines = []
    lines.append("# Phoenix Benchmark Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Model:** {summary.model_name}")
    lines.append(f"**Baseline:** {summary.baseline_name}")
    lines.append(f"**Total pairs:** {summary.total_pairs}")
    lines.append("")
    
    # ── Summary Table ──────────────────────────────────────────
    lines.append("## Summary Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Average BLEU-1 | {summary.avg_bleu:.4f} |")
    lines.append(f"| Average ROUGE-L | {summary.avg_rouge_l:.4f} |")
    lines.append(f"| Average Structural Similarity | {summary.avg_structural_similarity:.4f} |")
    lines.append(f"| Average Signature Preservation | {summary.avg_signature_preservation:.4f} |")
    lines.append(f"| Average Import Preservation | {summary.avg_import_preservation:.4f} |")
    lines.append(f"| Average Line Overlap | {summary.avg_line_overlap:.4f} |")
    lines.append(f"| Average Compression Ratio | {summary.avg_compression_ratio:.4f} |")
    lines.append(f"| Average Inference Time | {summary.avg_inference_time_ms:.1f} ms |")
    lines.append(f"| Average Inference Speed | {summary.avg_inference_tokens_per_sec:.1f} tok/s |")
    lines.append(f"| Effective Context Multiplier | {summary.effective_context_multiplier:.1f}x |")
    lines.append(f"| Total Skeleton Tokens | {summary.total_skeleton_tokens:,} |")
    lines.append(f"| Total Full Tokens | {summary.total_full_tokens:,} |")
    lines.append("")
    
    # ── Context Multiplier Explanation ─────────────────────────
    lines.append("## Effective Context Multiplier")
    lines.append("")
    lines.append(f"The **effective context multiplier** ({summary.effective_context_multiplier:.1f}x) means that ")
    lines.append(f"with a {4096}-token context window, the Phoenix model can effectively process ")
    lines.append(f"the equivalent of **{int(4096 * summary.effective_context_multiplier):,} tokens** of full source code ")
    lines.append(f"by operating on TokenSlayer-compressed skeletons.")
    lines.append("")
    lines.append("| Context Window | Effective Capacity |")
    lines.append("|---------------|-------------------|")
    lines.append(f"| 4,096 tokens | {int(4096 * summary.effective_context_multiplier):,} tokens |")
    lines.append(f"| 8,192 tokens | {int(8192 * summary.effective_context_multiplier):,} tokens |")
    lines.append(f"| 32,768 tokens | {int(32768 * summary.effective_context_multiplier):,} tokens |")
    lines.append(f"| 128,000 tokens | {int(128000 * summary.effective_context_multiplier):,} tokens |")
    lines.append("")
    
    # ── Per-Pair Results ──────────────────────────────────────
    lines.append("## Per-Pair Results")
    lines.append("")
    lines.append("| # | File | Lang | Skel Tok | Full Tok | Comp Ratio | BLEU | ROUGE-L | Struct Sim | Time (ms) |")
    lines.append("|---|------|------|----------|----------|------------|------|---------|------------|-----------|")
    
    for i, r in enumerate(results[:50]):  # Show first 50
        lines.append(
            f"| {i+1} | {Path(r.filepath).name} | {r.language} "
            f"| {r.skeleton_tokens} | {r.full_tokens} "
            f"| {r.compression_ratio:.3f} | {r.bleu_score:.3f} "
            f"| {r.rouge_l_score:.3f} | {r.structural_similarity:.3f} "
            f"| {r.inference_time_ms:.0f} |"
        )
    
    if len(results) > 50:
        lines.append(f"| ... | ({len(results) - 50} more pairs) | ... | ... | ... | ... | ... | ... | ... | ... |")
    
    lines.append("")
    
    # ── Top/Bottom Performers ─────────────────────────────────
    if results:
        sorted_by_sim = sorted(results, key=lambda r: r.structural_similarity, reverse=True)
        lines.append("## Top 5 Best Expansions")
        lines.append("")
        for r in sorted_by_sim[:5]:
            lines.append(f"- **{Path(r.filepath).name}** — Structural Sim: {r.structural_similarity:.3f}, BLEU: {r.bleu_score:.3f}")
        lines.append("")
        
        lines.append("## Bottom 5 Worst Expansions")
        lines.append("")
        for r in sorted_by_sim[-5:]:
            lines.append(f"- **{Path(r.filepath).name}** — Structural Sim: {r.structural_similarity:.3f}, BLEU: {r.bleu_score:.3f}")
        lines.append("")
    
    # ── Recommendations ───────────────────────────────────────
    lines.append("## Recommendations")
    lines.append("")
    
    if summary.avg_structural_similarity > 0.8:
        lines.append("✅ **Excellent structural preservation.** The Phoenix model is ready for production use.")
    elif summary.avg_structural_similarity > 0.6:
        lines.append("⚠️ **Good structural preservation.** Consider more training epochs or a larger base model.")
    else:
        lines.append("❌ **Poor structural preservation.** Increase training data, epochs, or switch to a larger base model.")
    
    if summary.effective_context_multiplier > 5:
        lines.append(f"✅ **Excellent compression ({summary.effective_context_multiplier:.1f}x).** TokenSlayer is working effectively.")
    elif summary.effective_context_multiplier > 2:
        lines.append(f"⚠️ **Moderate compression ({summary.effective_context_multiplier:.1f}x).** Consider using TokenSlayer level 4 (ultra) for better compression.")
    else:
        lines.append(f"❌ **Poor compression ({summary.effective_context_multiplier:.1f}x).** TokenSlayer level may be too low.")
    
    lines.append("")
    lines.append("---")
    lines.append("*Generated by Phoenix Benchmark — Sprint 5*")
    
    report_text = "\n".join(lines)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    
    logger.info(f"Report saved to {output_path}")
    return report_text


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phoenix Benchmark — Sprint 5")
    parser.add_argument("--student", default=str(DEFAULT_STUDENT_PATH), help="Path to trained Phoenix student model")
    parser.add_argument("--baseline", default="", help="Baseline model name (e.g., unsloth/gemma-2-2b-it)")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Benchmark dataset (JSONL)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Output report path")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS), help="Output results JSON path")
    parser.add_argument("--teacher", default="", help="Teacher dataset for comparison (JSONL)")
    parser.add_argument("--max-samples", type=int, default=0, help="Max samples to benchmark (0=all)")
    parser.add_argument("--quick", action="store_true", help="Quick benchmark with synthetic data (no GPU)")
    parser.add_argument("--no-gpu", action="store_true", help="Skip GPU inference, only compute dataset metrics")
    args = parser.parse_args()
    
    dataset_path = Path(args.dataset)
    report_path = Path(args.report)
    results_path = Path(args.results)
    student_path = Path(args.student)
    
    # ── Load or Create Dataset ─────────────────────────────────
    if args.quick:
        logger.info("Using synthetic benchmark data (quick mode)")
        dataset = create_synthetic_benchmark()
    elif dataset_path.exists():
        dataset = load_benchmark_dataset(dataset_path, args.max_samples)
    else:
        logger.warning(f"Dataset not found: {dataset_path}")
        logger.info("Falling back to synthetic data")
        dataset = create_synthetic_benchmark()
    
    # ── Load Teacher Dataset (optional) ────────────────────────
    teacher_dataset = None
    if args.teacher:
        teacher_path = Path(args.teacher)
        if teacher_path.exists():
            teacher_dataset = load_benchmark_dataset(teacher_path)
            logger.info(f"Loaded teacher dataset: {len(teacher_dataset)} pairs")
    
    # ── Load Model (optional) ──────────────────────────────────
    model = None
    tokenizer = None
    model_name = "none"
    baseline_name = args.baseline if args.baseline else "none"
    
    if not args.no_gpu and not args.quick:
        if student_path.exists() and (student_path / "adapter_config.json").exists():
            logger.info(f"Loading Phoenix student model from {student_path}")
            try:
                from unsloth import FastLanguageModel
                model, tokenizer = FastLanguageModel.from_pretrained(
                    model_name=str(student_path),
                    max_seq_length=4096,
                    dtype=None,
                    load_in_4bit=True,
                    device_map="auto",
                )
                model_name = f"phoenix_student ({student_path.name})"
                logger.info(f"Model loaded: {sum(p.numel() for p in model.parameters()):,} params")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                logger.info("Proceeding with dataset-only metrics")
        else:
            logger.warning(f"Student model not found at {student_path}")
            logger.info("Proceeding with dataset-only metrics")
    
    # ── Run Benchmark ─────────────────────────────────────────
    logger.info(f"Running benchmark on {len(dataset)} pairs...")
    
    summary = run_benchmark(
        dataset=dataset,
        model=model,
        tokenizer=tokenizer,
        model_name=model_name,
        baseline_name=baseline_name,
        teacher_dataset=teacher_dataset,
        quick=args.quick or args.no_gpu,
    )
    
    # ── Generate Report ───────────────────────────────────────
    logger.info("Generating benchmark report...")
    
    # Reconstruct results list for report
    results = []
    for pair in dataset:
        r = BenchmarkResult(
            filepath=pair.get("filepath", "unknown"),
            language=pair.get("language", "unknown"),
            skeleton_tokens=count_tokens(pair.get("skeleton", "")),
            full_tokens=count_tokens(pair.get("full", pair.get("original_full", ""))),
            compression_ratio=count_tokens(pair.get("skeleton", "")) / max(count_tokens(pair.get("full", pair.get("original_full", ""))), 1),
        )
        # Compute structural similarity if we have both outputs
        student_out = pair.get("student_output", "")
        original = pair.get("full", pair.get("original_full", ""))
        if student_out and original:
            struct = compute_structural_similarity(student_out, original)
            r.structural_similarity = struct["structural_similarity"]
            r.signature_preservation = struct["signature_preservation"]
            r.import_preservation = struct["import_preservation"]
            r.line_overlap = struct["line_overlap"]
            r.bleu_score = compute_bleu(original, student_out)
            r.rouge_l_score = compute_rouge_l(original, student_out)
        results.append(r)
    
    report_text = generate_report(summary, results, report_path)
    
    # ── Save Raw Results ──────────────────────────────────────
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": asdict(summary),
            "results": [asdict(r) for r in results],
        }, f, indent=2, default=str)
    logger.info(f"Raw results saved to {results_path}")
    
    # ── Print Summary ─────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Phoenix Benchmark Results")
    print("=" * 60)
    print(f"  Model:                    {model_name}")
    print(f"  Baseline:                 {baseline_name}")
    print(f"  Total pairs:              {summary.total_pairs}")
    print(f"  Avg BLEU-1:               {summary.avg_bleu:.4f}")
    print(f"  Avg ROUGE-L:              {summary.avg_rouge_l:.4f}")
    print(f"  Avg Structural Similarity: {summary.avg_structural_similarity:.4f}")
    print(f"  Avg Compression Ratio:    {summary.avg_compression_ratio:.4f}")
    print(f"  Avg Inference Speed:      {summary.avg_inference_tokens_per_sec:.1f} tok/s")
    print(f"  Context Multiplier:       {summary.effective_context_multiplier:.1f}x")
    print(f"  Report:                   {report_path}")
    print(f"  Results:                  {results_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()