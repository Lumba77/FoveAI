#!/usr/bin/env python3
"""
Phoenix Teacher Distillation — Sprint 2
Sends skeleton→full pairs to kimi-k2.7-code (primary) and deepseek-v4-pro (secondary)
via Ollama Cloud API. Stores teacher outputs, compares quality, generates report.

TOKEN BUDGET: Uses TokenSlayer-compressed skeletons (91.7% reduction) to minimize
Ollama Cloud quota usage. Each pair costs ~skeleton_tokens + teacher_output_tokens.
With 59 pairs at ~500 tokens each → ~30K tokens total (~$0.15).

Usage:
    python Training/distill_teacher.py [--model kimi-k2.7-code] [--limit 59] [--resume]

Output:
    Training/phoenix_teacher_dataset.jsonl  — teacher outputs + originals
    Training/phoenix_teacher_report.md      — quality comparison report
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx

# ── Load .env for API keys ─────────────────────────────────────
try:
    import dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        dotenv.load_dotenv(str(_env_path), override=False)
        print(f"  Loaded .env from {_env_path}")
except ImportError:
    print("  Note: python-dotenv not installed, relying on env vars")

# ── Paths ──────────────────────────────────────────────────────
LUMAX_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = LUMAX_ROOT / "Training" / "phoenix_dataset.jsonl"
DEFAULT_OUTPUT = LUMAX_ROOT / "Training" / "phoenix_teacher_dataset.jsonl"
DEFAULT_REPORT = LUMAX_ROOT / "Training" / "phoenix_teacher_report.md"
PROGRESS_FILE = LUMAX_ROOT / "Training" / ".distill_progress.json"

# ── Ollama Cloud Config ────────────────────────────────────────
OLLAMA_BASE_RAW = os.environ.get("LUMAX_CLOUD_BASE_URL", "https://ollama.com/v1")
# Ensure the base URL always includes /v1 (Ollama Cloud API is OpenAI-compatible)
OLLAMA_BASE = OLLAMA_BASE_RAW.rstrip("/")
if not OLLAMA_BASE.endswith("/v1"):
    OLLAMA_BASE += "/v1"
OLLAMA_KEY = (
    os.environ.get("LUMAX_REPERTOIRE_OLLAMA_API_KEY", "")
    or os.environ.get("OLLAMA_API_KEY", "")
)

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("distill_teacher")

# ── Distillation Prompt ────────────────────────────────────────
DISTILL_PROMPT = """You are a code expansion expert. Given a skeletonized code file (imports + function signatures only), reconstruct the full implementation.

SKELETON:
{skeleton}

TASK: Write the complete implementation. Follow these rules:
1. Preserve ALL signatures exactly as shown
2. Implement each function with realistic, working code
3. Use appropriate error handling
4. Follow Python best practices
5. Output ONLY the complete file content, no explanations

FULL IMPLEMENTATION:"""


def count_matching_lines(teacher: str, original: str) -> int:
    """Count how many non-empty lines in teacher output match original."""
    t_lines = set(l.strip() for l in teacher.split("\n") if l.strip())
    o_lines = set(l.strip() for l in original.split("\n") if l.strip())
    if not o_lines:
        return 0
    matches = t_lines & o_lines
    return len(matches)


def structural_similarity(teacher: str, original: str) -> float:
    """Compute structural similarity score (0.0 to 1.0).
    
    Measures:
    - Signature preservation (function/class defs match)
    - Import preservation
    - Line-level overlap
    """
    import re
    
    # Extract signatures from both
    t_sigs = set(re.findall(r'^(def |class |async def )', teacher, re.MULTILINE))
    o_sigs = set(re.findall(r'^(def |class |async def )', original, re.MULTILINE))
    
    # Extract imports from both
    t_imports = set(re.findall(r'^(import |from )', teacher, re.MULTILINE))
    o_imports = set(re.findall(r'^(import |from )', original, re.MULTILINE))
    
    # Signature score
    sig_score = len(t_sigs & o_sigs) / max(len(o_sigs), 1)
    
    # Import score
    imp_score = len(t_imports & o_imports) / max(len(o_imports), 1)
    
    # Line overlap score
    t_lines = set(l.strip() for l in teacher.split("\n") if l.strip() and not l.strip().startswith("#"))
    o_lines = set(l.strip() for l in original.split("\n") if l.strip() and not l.strip().startswith("#"))
    line_score = len(t_lines & o_lines) / max(len(o_lines), 1)
    
    # Weighted combination
    return 0.4 * sig_score + 0.3 * imp_score + 0.3 * line_score


def call_ollama_cloud(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    timeout: float = 300.0,
) -> Optional[str]:
    """Call an Ollama Cloud model via OpenAI-compatible API.
    
    Uses 32K context window (not 128K) to save quota — each request
    is only 100-6000 tokens (skeleton + prompt + output).
    """
    url = f"{OLLAMA_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if OLLAMA_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_KEY}"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            else:
                logger.error(f"HTTP {resp.status_code}: {resp.text[:300]}")
                return None
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None


def load_progress() -> Dict[str, Any]:
    """Load progress from previous run."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed": [], "failed": [], "started_at": None}


def save_progress(progress: Dict[str, Any]):
    """Save progress for resume support."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Phoenix Teacher Distillation — Sprint 2")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input dataset (JSONL)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output dataset (JSONL)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Output report (MD)")
    parser.add_argument("--model", default="kimi-k2.7-code", help="Primary teacher model")
    parser.add_argument("--secondary-model", default="deepseek-v4-pro", help="Secondary teacher model")
    parser.add_argument("--limit", type=int, default=0, help="Max pairs to process (0=all)")
    parser.add_argument("--resume", action="store_true", help="Resume from last progress")
    parser.add_argument("--temperature", type=float, default=0.3, help="LLM temperature")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max output tokens (32K context saves quota)")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)
    
    if not input_path.exists():
        logger.error(f"Input dataset not found: {input_path}")
        logger.error("Run Training/generate_phoenix_data.py first (Sprint 1)")
        sys.exit(1)
    
    # ── Load dataset ────────────────────────────────────────────
    logger.info(f"Loading dataset from {input_path}")
    pairs = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    
    logger.info(f"Loaded {len(pairs)} skeleton→full pairs")
    
    if args.limit > 0:
        pairs = pairs[:args.limit]
        logger.info(f"Limited to {len(pairs)} pairs")
    
    # ── Load progress for resume ────────────────────────────────
    progress = load_progress() if args.resume else {"completed": [], "failed": [], "started_at": None}
    if progress["started_at"] is None:
        progress["started_at"] = datetime.now().isoformat()
    
    completed_ids = set(progress.get("completed", []))
    failed_ids = set(progress.get("failed", []))
    
    # ── Process each pair ───────────────────────────────────────
    results = []
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print(f"  Phoenix Teacher Distillation — Sprint 2")
    print(f"  Primary model:   {args.model}")
    print(f"  Secondary model: {args.secondary_model}")
    print(f"  Pairs to process: {len(pairs)}")
    print(f"  Already completed: {len(completed_ids)}")
    print(f"  Already failed: {len(failed_ids)}")
    print("=" * 60)
    print()
    
    for idx, pair in enumerate(pairs):
        filepath = pair.get("filepath", f"pair_{idx}")
        pair_id = f"{filepath}::{idx}"
        
        if pair_id in completed_ids:
            logger.info(f"[{idx+1}/{len(pairs)}] SKIP (already done): {filepath}")
            skip_count += 1
            continue
        
        skeleton = pair.get("skeleton", "")
        original_full = pair.get("full", "")
        
        if not skeleton or not original_full:
            logger.warning(f"[{idx+1}/{len(pairs)}] SKIP (empty): {filepath}")
            failed_ids.add(pair_id)
            fail_count += 1
            continue
        
        print(f"  [{idx+1}/{len(pairs)}] {filepath}")
        print(f"       Skeleton: {pair.get('token_count_skeleton', '?')} tokens")
        print(f"       Original: {pair.get('token_count_full', '?')} tokens")
        
        # ── Call primary teacher (kimi-k2.7-code) ──────────────
        print(f"       → Calling {args.model}...", end=" ", flush=True)
        t0 = time.time()
        teacher_output = call_ollama_cloud(
            model=args.model,
            system_prompt="You are a code expansion expert. Reconstruct full implementations from skeletons.",
            user_prompt=DISTILL_PROMPT.format(skeleton=skeleton),
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        elapsed = time.time() - t0
        
        if teacher_output is None:
            print(f"FAILED ({elapsed:.1f}s)")
            failed_ids.add(pair_id)
            fail_count += 1
            save_progress(progress)
            continue
        
        print(f"OK ({elapsed:.1f}s, {len(teacher_output)} chars)")
        
        # ── Call secondary teacher (deepseek-v4-pro) ────────────
        secondary_output = None
        print(f"       → Calling {args.secondary_model}...", end=" ", flush=True)
        t0 = time.time()
        secondary_output = call_ollama_cloud(
            model=args.secondary_model,
            system_prompt="You are a code expansion expert. Reconstruct full implementations from skeletons.",
            user_prompt=DISTILL_PROMPT.format(skeleton=skeleton),
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        elapsed2 = time.time() - t0
        
        if secondary_output is None:
            print(f"FAILED ({elapsed2:.1f}s)")
        else:
            print(f"OK ({elapsed2:.1f}s, {len(secondary_output)} chars)")
        
        # ── Quality assessment ──────────────────────────────────
        primary_sim = structural_similarity(teacher_output, original_full)
        secondary_sim = structural_similarity(secondary_output, original_full) if secondary_output else 0.0
        
        # Pick best teacher output
        if secondary_output and secondary_sim > primary_sim:
            best_output = secondary_output
            best_model = args.secondary_model
            best_sim = secondary_sim
        else:
            best_output = teacher_output
            best_model = args.model
            best_sim = primary_sim
        
        quality = "HIGH" if best_sim > 0.6 else "MEDIUM" if best_sim > 0.3 else "LOW"
        
        print(f"       Quality: {quality} (primary={primary_sim:.2f}, secondary={secondary_sim:.2f})")
        
        # ── Store result ────────────────────────────────────────
        result = {
            "skeleton": skeleton,
            "original_full": original_full,
            "teacher_output_kimi": teacher_output,
            "teacher_output_pro": secondary_output,
            "best_output": best_output,
            "best_model": best_model,
            "filepath": filepath,
            "language": pair.get("language", "python"),
            "token_count_skeleton": pair.get("token_count_skeleton", 0),
            "token_count_full": pair.get("token_count_full", 0),
            "compression_ratio": pair.get("compression_ratio", 0),
            "quality_score": best_sim,
            "quality_label": quality,
            "primary_similarity": primary_sim,
            "secondary_similarity": secondary_sim,
        }
        
        results.append(result)
        
        # Write immediately for crash safety
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
        
        completed_ids.add(pair_id)
        success_count += 1
        
        # Update progress every 5 pairs
        if success_count % 5 == 0:
            progress["completed"] = list(completed_ids)
            progress["failed"] = list(failed_ids)
            save_progress(progress)
        
        # Rate limiting: be nice to Ollama Cloud
        if idx < len(pairs) - 1:
            time.sleep(1.0)
    
    # ── Final progress save ─────────────────────────────────────
    progress["completed"] = list(completed_ids)
    progress["failed"] = list(failed_ids)
    progress["finished_at"] = datetime.now().isoformat()
    save_progress(progress)
    
    # ── Generate Report ────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Generating report...")
    
    # Reload all results from file for accurate report
    all_results = []
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_results.append(json.loads(line))
    
    high_quality = [r for r in all_results if r.get("quality_label") == "HIGH"]
    medium_quality = [r for r in all_results if r.get("quality_label") == "MEDIUM"]
    low_quality = [r for r in all_results if r.get("quality_label") == "LOW"]
    
    avg_primary_sim = sum(r.get("primary_similarity", 0) for r in all_results) / max(len(all_results), 1)
    avg_secondary_sim = sum(r.get("secondary_similarity", 0) for r in all_results) / max(len(all_results), 1)
    
    report_lines = [
        f"# Phoenix Teacher Distillation Report",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"Primary teacher: `{args.model}`",
        f"Secondary teacher: `{args.secondary_model}`",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total pairs processed | {len(all_results)} |",
        f"| Success | {success_count} |",
        f"| Failed | {fail_count} |",
        f"| Skipped (already done) | {skip_count} |",
        f"| High quality (sim > 0.6) | {len(high_quality)} |",
        f"| Medium quality (sim 0.3-0.6) | {len(medium_quality)} |",
        f"| Low quality (sim < 0.3) | {len(low_quality)} |",
        f"| Avg primary similarity | {avg_primary_sim:.3f} |",
        f"| Avg secondary similarity | {avg_secondary_sim:.3f} |",
        f"",
        f"## Per-File Results",
        f"",
        f"| # | File | Primary Sim | Secondary Sim | Best Model | Quality |",
        f"|---|------|-------------|---------------|------------|---------|",
    ]
    
    for i, r in enumerate(all_results):
        report_lines.append(
            f"| {i+1} | {r['filepath']} | {r.get('primary_similarity', 0):.3f} | "
            f"{r.get('secondary_similarity', 0):.3f} | {r.get('best_model', '?')} | "
            f"{r.get('quality_label', '?')} |"
        )
    
    report_lines.extend([
        f"",
        f"## Quality Distribution",
        f"",
        f"- **HIGH** (sim > 0.6): {len(high_quality)} pairs — teacher output closely matches original",
        f"- **MEDIUM** (sim 0.3-0.6): {len(medium_quality)} pairs — structurally similar, different implementation",
        f"- **LOW** (sim < 0.3): {len(low_quality)} pairs — teacher produced different code",
        f"",
        f"## Next Steps",
        f"",
        f"1. Review low-quality pairs — decide if they should be included in training",
        f"2. Proceed to Sprint 3: Student Training",
        f"   ```bash",
        f"   python Training/train_phoenix_student.py",
        f"   ```",
    ])
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")
    
    print(f"  Report: {report_path}")
    print(f"  Output: {output_path}")
    print("=" * 60)
    print()
    print(f"Summary:")
    print(f"  Processed: {len(all_results)} pairs")
    print(f"  High quality: {len(high_quality)}")
    print(f"  Medium quality: {len(medium_quality)}")
    print(f"  Low quality: {len(low_quality)}")
    print(f"  Avg primary similarity: {avg_primary_sim:.3f}")
    print(f"  Avg secondary similarity: {avg_secondary_sim:.3f}")


if __name__ == "__main__":
    main()