#!/usr/bin/env python3
"""
70XRL Dataset Preprocessor — Converts training data through XRL tokenizer.

Takes any text/code dataset and preprocesses it through the XRL tokenizer
so the model learns to understand XRL skeletons natively during fine-tuning.

The key insight: we train the model on pairs of (XRL skeleton, full code)
so it learns to expand skeletons into full implementations, and to understand
code structure from skeletons alone.

Usage:
    python xrl_preprocessor.py --input ./datasets/code --output ./datasets/xrl-train
    python xrl_preprocessor.py --hf-dataset bigcode/the-stack --output ./datasets/xrl-stack --max-samples 10000

Options:
    --input         Local directory with code files
    --hf-dataset    HuggingFace dataset ID
    --output         Output directory for XRL-processed dataset
    --max-samples   Max samples to process (default: all)
    --depth         XRL skeleton depth 0-3 (default: 2)
    --format        Output format: jsonl, parquet (default: jsonl)
    --workers       Parallel workers (default: 4)
"""

import argparse
import json
import logging
import multiprocessing
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("70xrl-preprocessor")

# ─── Paths ───────────────────────────────────────────────────────────

XRL_CLI = Path(__file__).parent.parent / "xrs" / "xrl.cjs"
XRS_CLI = Path(__file__).parent.parent / "xrs" / "xrs.cjs"

# Supported file extensions for code
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".m",
    ".mm",
    ".vue",
    ".svelte",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".less",
}


# ─── XRL Tokenizer Interface ────────────────────────────────────────


def run_xrl(filepath: str, depth: int = 2) -> dict | None:
    """Run XRL tokenizer on a file and return the result."""
    if not XRL_CLI.exists():
        logger.error(f"XRL CLI not found at: {XRL_CLI}")
        return None

    cmd = ["node", str(XRL_CLI), filepath, "--depth", str(depth), "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.debug(f"XRL failed on {filepath}: {result.stderr[:100]}")
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.debug(f"XRL error on {filepath}: {e}")
        return None


def run_xrs(filepath: str) -> str | None:
    """Run XRS skeletonizer and return the text skeleton."""
    if not XRS_CLI.exists():
        logger.error(f"XRS CLI not found at: {XRS_CLI}")
        return None

    cmd = ["node", str(XRS_CLI), filepath]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        return None


# ─── Dataset Processing ─────────────────────────────────────────────


def process_file(filepath: str, depth: int = 2) -> dict | None:
    """Process a single file: generate XRL skeleton + training pair."""
    # Read original content
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
    except Exception as e:
        logger.debug(f"Could not read {filepath}: {e}")
        return None

    if not original.strip():
        return None

    # Skip files that are too large (>100KB)
    if len(original) > 100_000:
        logger.debug(f"Skipping large file: {filepath} ({len(original)} bytes)")
        return None

    # Generate XRL skeleton
    xrl_result = run_xrl(filepath, depth=depth)
    if not xrl_result:
        return None

    # Generate XRS text skeleton (for training the model to understand text skeletons)
    xrs_skeleton = run_xrs(filepath)

    # Create training pair
    training_pair = {
        "file": filepath,
        "language": Path(filepath).suffix.lstrip("."),
        "original": original,
        "original_tokens": xrl_result.get("original_tokens", 0),
        "skeleton_tokens": xrl_result.get("skeleton_tokens", 0),
        "reduction_pct": xrl_result.get("reduction_pct", 0),
        "xrl_tokens": xrl_result.get("tokens", []),
        "xrs_skeleton": xrs_skeleton,
        "depth": depth,
        # Training formats:
        # Mode 1: Skeleton → Code (learn to expand)
        "skeleton_to_code": {
            "instruction": f"Expand this {Path(filepath).suffix.lstrip('.')} code skeleton into a complete implementation.",
            "input": xrs_skeleton or "",
            "output": original,
        },
        # Mode 2: Code Understanding (learn from skeleton)
        "code_understanding": {
            "instruction": f"Analyze this {Path(filepath).suffix.lstrip('.')} code. Describe its structure, imports, types, and key functions.",
            "input": xrs_skeleton or "",
            "output": _generate_understanding(original, xrs_skeleton),
        },
    }

    return training_pair


def _generate_understanding(original: str, skeleton: str) -> str:
    """Generate a simple structural understanding of the code."""
    lines = original.split("\n")
    imports = [
        l
        for l in lines
        if l.strip().startswith(("import ", "from ", "require(", "include"))
    ]
    functions = [
        l
        for l in lines
        if any(kw in l for kw in ["def ", "fn ", "function ", "async def"])
    ]
    classes = [
        l for l in lines if any(kw in l for kw in ["class ", "struct ", "interface "])
    ]

    parts = []
    if imports:
        parts.append(f"Imports: {len(imports)}")
    if classes:
        parts.append(f"Classes: {len(classes)}")
    if functions:
        parts.append(f"Functions: {len(functions)}")

    return (
        f"This code has {len(lines)} lines. {' | '.join(parts)}"
        if parts
        else f"This code has {len(lines)} lines."
    )


def process_directory(
    input_dir: str,
    output_dir: str,
    depth: int = 2,
    max_samples: int = None,
    workers: int = 4,
):
    """Process all code files in a directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Collect all code files
    files = []
    for ext in CODE_EXTENSIONS:
        files.extend(input_path.rglob(f"*{ext}"))

    # Filter out common non-source directories
    skip_dirs = {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".cache",
        "dist",
        "build",
        ".next",
        "target",
        "bin",
        "obj",
    }
    files = [f for f in files if not any(d in f.parts for d in skip_dirs)]

    if max_samples:
        files = files[:max_samples]

    logger.info(f"Found {len(files)} code files in {input_dir}")

    # Process files in parallel
    results = []
    with multiprocessing.Pool(workers) as pool:
        tasks = [(str(f), depth) for f in files]
        for i, result in enumerate(pool.starmap(process_file, tasks)):
            if result:
                results.append(result)
            if (i + 1) % 100 == 0:
                logger.info(
                    f"  Processed {i + 1}/{len(files)} files ({len(results)} valid)"
                )

    logger.info(f"Generated {len(results)} training pairs from {len(files)} files")

    # Write output
    output_file = output_path / "xrl_dataset.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(item, ensure_ascii=False) + "\n" for item in results)

    # Write stats
    stats = {
        "total_files": len(files),
        "valid_pairs": len(results),
        "depth": depth,
        "avg_reduction": sum(r.get("reduction_pct", 0) for r in results) / len(results)
        if results
        else 0,
        "languages": {},
    }
    for r in results:
        lang = r.get("language", "unknown")
        stats["languages"][lang] = stats["languages"].get(lang, 0) + 1

    stats_file = output_path / "xrl_dataset_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    logger.info(f"✅ Dataset written to: {output_file}")
    logger.info(f"   Stats: {json.dumps(stats, indent=2)}")

    return results


def process_hf_dataset(
    dataset_id: str, output_dir: str, max_samples: int = None, depth: int = 2
):
    """Process a HuggingFace dataset through XRL."""
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets library not installed. Run: pip install datasets")
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"📦 Loading HF dataset: {dataset_id}")
    dataset = load_dataset(dataset_id, split="train", streaming=True)

    if max_samples:
        dataset = dataset.take(max_samples)

    results = []
    for i, sample in enumerate(dataset):
        # Extract code content (varies by dataset format)
        content = (
            sample.get("content") or sample.get("text") or sample.get("code") or ""
        )
        if not content or len(content) > 100_000:
            continue

        # Write to temp file for XRL processing
        ext = sample.get("language", "py")
        if ext == "javascript":
            ext = "js"
        elif ext == "typescript":
            ext = "ts"

        temp_file = output_path / f"temp_{i}.{ext}"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(content)

            result = process_file(str(temp_file), depth=depth)
            if result:
                result["source_dataset"] = dataset_id
                results.append(result)
        finally:
            if temp_file.exists():
                temp_file.unlink()

        if (i + 1) % 100 == 0:
            logger.info(f"  Processed {i + 1} samples ({len(results)} valid)")

    # Write output
    output_file = output_path / "xrl_dataset.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(item, ensure_ascii=False) + "\n" for item in results)

    logger.info(f"✅ HF dataset processed: {len(results)} pairs → {output_file}")


# ─── CLI ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="70XRL Dataset Preprocessor")
    parser.add_argument("--input", help="Local directory with code files")
    parser.add_argument("--hf-dataset", help="HuggingFace dataset ID")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--max-samples", type=int, help="Max samples to process")
    parser.add_argument(
        "--depth", type=int, default=2, choices=[0, 1, 2, 3], help="XRL skeleton depth"
    )
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")

    args = parser.parse_args()

    if args.input:
        process_directory(
            input_dir=args.input,
            output_dir=args.output,
            depth=args.depth,
            max_samples=args.max_samples,
            workers=args.workers,
        )
    elif args.hf_dataset:
        process_hf_dataset(
            dataset_id=args.hf_dataset,
            output_dir=args.output,
            max_samples=args.max_samples,
            depth=args.depth,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
