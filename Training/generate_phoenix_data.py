#!/usr/bin/env python3
"""
Phoenix Architecture — Sprint 1: Training Data Generator
=========================================================
Generates skeleton→full code pairs from the LUMAX codebase using TokenSlayer CLI.

Output: Training/data/phoenix_dataset.json
Format: {skeleton, full, filepath, language, token_count_skeleton, token_count_full, compression_ratio}

Augmentation strategies:
  - Cross-file pairs: skeleton of file A → full of file B
  - Partial skeletons: randomly drop 10-30% of signatures
  - Noisy skeletons: introduce minor errors in skeleton

Usage:
  python Training/generate_phoenix_data.py
  python Training/generate_phoenix_data.py --tier micro   # Level 4 (ultra-compact)
  python Training/generate_phoenix_data.py --tier full    # Level 0 (no compression)
"""

import os
import sys
import json
import subprocess
import random
import re
from pathlib import Path
from datetime import datetime

# ─── Configuration ───────────────────────────────────────────────────────────

LUMAX_ROOT = Path(__file__).resolve().parent.parent
TOKENSLAYER_CLI = LUMAX_ROOT / "Forge" / "scratch" / "TokenSlayer" / "standalone" / "tokenslayer.js"
OUTPUT_DIR = LUMAX_ROOT / "Training" / "data"
OUTPUT_PATH = OUTPUT_DIR / "phoenix_dataset.json"
AUGMENTED_OUTPUT_PATH = OUTPUT_DIR / "phoenix_dataset_augmented.json"

# Source directories to scan for code files
SOURCE_DIRS = [
    LUMAX_ROOT / "Backend",
    LUMAX_ROOT / "Forge",
    LUMAX_ROOT / "Frontend",
    LUMAX_ROOT / "Training",
    LUMAX_ROOT / "Scripts",
]

# File extensions to include
INCLUDE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx"}

# Directories to exclude (venvs, node_modules, cache, etc.)
EXCLUDE_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", ".pytest_cache",
    "chroma_db", "redis-data", "onnx", "ollama", "data", "outputs",
    ".SafeSaves", ".SafeSave", ".backup", ".backups", ".logs",
}

# TokenSlayer level for skeleton generation
# Level 3 = deep (imports + signatures only) — ~85-96% reduction
SKELETON_LEVEL = 3

# Augmentation settings
AUGMENT_CROSS_FILE = True
AUGMENT_PARTIAL = True
AUGMENT_NOISY = True
AUGMENT_PARTIAL_DROP_RATE = 0.2  # Drop 20% of signatures
AUGMENT_NOISE_RATE = 0.1  # Introduce noise in 10% of tokens

random.seed(3407)  # Reproducible randomness


# ─── TokenSlayer Integration ─────────────────────────────────────────────────

def run_tokenslayer(filepath: str, level: int = SKELETON_LEVEL) -> str:
    """Run TokenSlayer CLI on a file and return the skeleton text."""
    cmd = [
        "node", str(TOKENSLAYER_CLI),
        filepath,
        "--level", str(level),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  ⚠ TokenSlayer error on {filepath}: {result.stderr.strip()}")
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        print(f"  ⚠ Timeout on {filepath}")
        return None
    except FileNotFoundError:
        print(f"  ⚠ TokenSlayer CLI not found at {TOKENSLAYER_CLI}")
        return None


def count_tokens(text: str) -> int:
    """Rough token count (words + punctuation)."""
    if not text:
        return 0
    return len(text.split())


# ─── File Discovery ───────────────────────────────────────────────────────────

def discover_source_files() -> list[Path]:
    """Discover all source files in the configured directories."""
    files = []
    for src_dir in SOURCE_DIRS:
        if not src_dir.exists():
            print(f"  ⚠ Source directory not found: {src_dir}")
            continue
        for root, dirs, filenames in os.walk(src_dir):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            for f in filenames:
                ext = Path(f).suffix.lower()
                if ext in INCLUDE_EXTS:
                    files.append(Path(root) / f)
    return files


def detect_language(filepath: Path) -> str:
    """Detect programming language from file extension."""
    ext = filepath.suffix.lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
    }
    return lang_map.get(ext, "unknown")


# ─── Augmentation Strategies ─────────────────────────────────────────────────

def create_partial_skeleton(skeleton: str, drop_rate: float = AUGMENT_PARTIAL_DROP_RATE) -> str:
    """Randomly drop a percentage of function/class signatures from the skeleton."""
    if not skeleton:
        return skeleton
    
    lines = skeleton.split("\n")
    kept_lines = []
    
    for line in lines:
        # Detect function/class signatures
        is_signature = bool(re.match(r'^\s*(def |class |async def |fn |function |const \w+ = )', line))
        if is_signature and random.random() < drop_rate:
            continue  # Drop this signature
        kept_lines.append(line)
    
    return "\n".join(kept_lines)


def create_noisy_skeleton(skeleton: str, noise_rate: float = AUGMENT_NOISE_RATE) -> str:
    """Introduce minor errors in the skeleton (typos in comments, parameter names)."""
    if not skeleton:
        return skeleton
    
    lines = skeleton.split("\n")
    noisy_lines = []
    
    for line in lines:
        if random.random() < noise_rate:
            # Introduce a minor typo: swap two adjacent characters
            if len(line) > 5:
                idx = random.randint(0, len(line) - 2)
                chars = list(line)
                chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
                line = "".join(chars)
        noisy_lines.append(line)
    
    return "\n".join(noisy_lines)


# ─── Dataset Generation ───────────────────────────────────────────────────────

def generate_dataset(tier: str = "standard") -> list[dict]:
    """Generate the primary skeleton→full dataset."""
    
    # Map tier to TokenSlayer level
    tier_level_map = {
        "micro": 4,    # Ultra-compact (symbol table)
        "standard": 3, # Deep (imports + signatures)
        "full": 0,     # No compression
    }
    level = tier_level_map.get(tier, SKELETON_LEVEL)
    
    print(f"🔍 Discovering source files...")
    files = discover_source_files()
    print(f"   Found {len(files)} source files")
    
    dataset = []
    errors = []
    
    for i, filepath in enumerate(files):
        rel_path = filepath.relative_to(LUMAX_ROOT)
        lang = detect_language(filepath)
        
        print(f"  [{i+1}/{len(files)}] Processing {rel_path} ({lang})...", end=" ")
        
        # Read full source
        try:
            full_source = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"⚠ Read error: {e}")
            errors.append({"file": str(rel_path), "error": str(e)})
            continue
        
        # Skip empty or tiny files
        if len(full_source.strip()) < 20:
            print("⏭ Too small")
            continue
        
        # Generate skeleton via TokenSlayer
        skeleton = run_tokenslayer(str(filepath), level=level)
        if skeleton is None:
            print("⚠ Skeleton failed")
            errors.append({"file": str(rel_path), "error": "TokenSlayer returned None"})
            continue
        
        # Count tokens
        skel_tokens = count_tokens(skeleton)
        full_tokens = count_tokens(full_source)
        compression_ratio = skel_tokens / max(full_tokens, 1)
        
        pair = {
            "skeleton": skeleton.strip(),
            "full": full_source.strip(),
            "filepath": str(rel_path),
            "language": lang,
            "token_count_skeleton": skel_tokens,
            "token_count_full": full_tokens,
            "compression_ratio": round(compression_ratio, 4),
            "tier": tier,
            "level": level,
        }
        
        dataset.append(pair)
        print(f"✅ {skel_tokens}/{full_tokens} tok ({compression_ratio:.1%})")
    
    print(f"\n📊 Dataset summary:")
    print(f"   Total pairs: {len(dataset)}")
    print(f"   Errors: {len(errors)}")
    if dataset:
        avg_compression = sum(p["compression_ratio"] for p in dataset) / len(dataset)
        print(f"   Avg compression ratio: {avg_compression:.2%}")
        print(f"   Avg skeleton tokens: {sum(p['token_count_skeleton'] for p in dataset) // len(dataset)}")
        print(f"   Avg full tokens: {sum(p['token_count_full'] for p in dataset) // len(dataset)}")
    
    return dataset


def generate_augmented_dataset(base_dataset: list[dict]) -> list[dict]:
    """Generate augmented pairs from the base dataset."""
    augmented = []
    
    for pair in base_dataset:
        # 1. Partial skeleton (drop random signatures)
        if AUGMENT_PARTIAL:
            partial_skel = create_partial_skeleton(pair["skeleton"])
            if partial_skel and partial_skel != pair["skeleton"]:
                aug_pair = dict(pair)
                aug_pair["skeleton"] = partial_skel
                aug_pair["augmentation"] = "partial"
                aug_pair["token_count_skeleton"] = count_tokens(partial_skel)
                aug_pair["compression_ratio"] = round(aug_pair["token_count_skeleton"] / max(pair["token_count_full"], 1), 4)
                augmented.append(aug_pair)
        
        # 2. Noisy skeleton (introduce minor errors)
        if AUGMENT_NOISY:
            noisy_skel = create_noisy_skeleton(pair["skeleton"])
            if noisy_skel and noisy_skel != pair["skeleton"]:
                aug_pair = dict(pair)
                aug_pair["skeleton"] = noisy_skel
                aug_pair["augmentation"] = "noisy"
                aug_pair["token_count_skeleton"] = count_tokens(noisy_skel)
                aug_pair["compression_ratio"] = round(aug_pair["token_count_skeleton"] / max(pair["token_count_full"], 1), 4)
                augmented.append(aug_pair)
    
    # 3. Cross-file pairs (skeleton of file A → full of file B)
    if AUGMENT_CROSS_FILE and len(base_dataset) >= 2:
        for i in range(min(20, len(base_dataset))):  # Limit to 20 cross-file pairs
            a = base_dataset[i]
            b = base_dataset[(i + 1) % len(base_dataset)]
            if a["language"] == b["language"]:  # Same language only
                cross_pair = {
                    "skeleton": a["skeleton"],
                    "full": b["full"],
                    "filepath": f"{a['filepath']} → {b['filepath']}",
                    "language": a["language"],
                    "token_count_skeleton": a["token_count_skeleton"],
                    "token_count_full": b["token_count_full"],
                    "compression_ratio": round(a["token_count_skeleton"] / max(b["token_count_full"], 1), 4),
                    "augmentation": "cross_file",
                    "tier": a.get("tier", "standard"),
                    "level": a.get("level", 3),
                }
                augmented.append(cross_pair)
    
    print(f"\n📊 Augmented dataset: {len(augmented)} additional pairs")
    return augmented


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Phoenix Training Data Generator")
    parser.add_argument("--tier", choices=["micro", "standard", "full"], default="standard",
                        help="Skeleton tier (default: standard)")
    parser.add_argument("--no-augment", action="store_true",
                        help="Skip augmentation")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path (default: Training/data/phoenix_dataset.json)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🦅 PHOENIX DATA GENERATOR — Sprint 1")
    print("=" * 60)
    print(f"   Tier: {args.tier}")
    print(f"   TokenSlayer CLI: {TOKENSLAYER_CLI}")
    print(f"   Output: {OUTPUT_DIR}")
    print()
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate base dataset
    dataset = generate_dataset(tier=args.tier)
    
    if not dataset:
        print("\n❌ No pairs generated. Check source directories and TokenSlayer CLI.")
        sys.exit(1)
    
    # Save base dataset
    output_path = Path(args.output) if args.output else OUTPUT_PATH
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved {len(dataset)} base pairs to {output_path}")
    
    # Generate and save augmented dataset
    if not args.no_augment:
        augmented = generate_augmented_dataset(dataset)
        if augmented:
            all_pairs = dataset + augmented
            with open(AUGMENTED_OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(all_pairs, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved {len(all_pairs)} total pairs (base + augmented) to {AUGMENTED_OUTPUT_PATH}")
    
    # Print summary
    print()
    print("=" * 60)
    print("✅ SPRINT 1 COMPLETE")
    print("=" * 60)
    print(f"   Base pairs: {len(dataset)}")
    if not args.no_augment:
        print(f"   Augmented pairs: {len(dataset) + len(augmented) if 'augmented' in dir() else 0}")
    print(f"   Next: Run Training/distill_teacher.py for Sprint 2")
    print()


if __name__ == "__main__":
    main()