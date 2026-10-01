r"""
package_big_models_xrlf.py
===========================
Package big MoQ GGUF core models as .xrlf bundles with XRL cognitive steering layers.

Supports packaging multiple core models with different XRL profiles:
  - Qwen3.5-9B-MoQ  → general-purpose core (chat profile)
  - Qwen3.5-4B-MTP  → lightweight coder core (coder profile)
  - jica98/super-coder → alternative coder core (coder profile)

The XRL instruction store is designed with a clean separation so that
a "folded" XRL graph (Track L / EXP-110) can be swapped in later as a
drop-in replacement for the flat XRL directory.

Usage:
    python Training\package_big_models_xrlf.py --model qwen3.5-9b-moq
    python Training\package_big_models_xrlf.py --model qwen3.5-4b-mtp
    python Training\package_big_models_xrlf.py --model super-coder
    python Training\package_big_models_xrlf.py --all
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

# Make FoveAI importable
PROXY_ROOT = Path(r"C:\Users\danie\program\LUMAX\FoveAI")
if str(PROXY_ROOT) not in sys.path:
    sys.path.insert(0, str(PROXY_ROOT))

from formats.xrlf_packer import XRLFPacker

# ── Paths ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs")
XRL_DIR = PROXY_ROOT / "xrl_encoded"

# ── Model registry ─────────────────────────────────────────────────────────
# Each entry: (id, gguf_path, base_model_name, xrl_source_model, profile, description)

HF_CACHE = Path(r"C:\Users\danie\.cache\huggingface\hub")

MODELS = {
    "qwen3.5-9b-moq": {
        "gguf_path": HF_CACHE / "models--w-ahmad--Qwen3.5-9B-GGUF-MoQ" / "snapshots",
        "gguf_glob": "**/Qwen3.5-9B-MoQ-3.6.gguf",
        "base_model_name": "qwen3.5-9b",
        "xrl_source_model": "xrlf-core-qwen3.5-9b-moq",
        "profile": "chat",
        "description": "General-purpose 9B core with MoQ 3.6 quantization",
        "output_name": "qwen3.5-9b-moq.xrlf",
    },
    "qwen3.5-4b-mtp": {
        "gguf_path": HF_CACHE / "models--unsloth--Qwen3.5-4B-MTP-GGUF" / "snapshots",
        "gguf_glob": "**/Qwen3.5-4B-UD-Q4_K_XL.gguf",
        "mmproj_glob": "**/mmproj-F16.gguf",
        "base_model_name": "qwen3.5-4b-mtp",
        "xrl_source_model": "xrlf-coder-qwen3.5-4b-mtp",
        "profile": "coder",
        "description": "Lightweight 4B coder core with MTP (speculative decoding)",
        "output_name": "qwen3.5-4b-mtp.xrlf",
    },
    "super-coder": {
        "gguf_path": HF_CACHE / "models--jica98--qwen3.5-4B-super-coder" / "snapshots",
        "gguf_glob": "**/qwen3.5-4B-super-coder.Q4_0.gguf",
        "mmproj_glob": "**/qwen3.5-4B-super-coder.BF16-mmproj.gguf",
        "base_model_name": "qwen3.5-4b-super-coder",
        "xrl_source_model": "xrlf-coder-super-coder",
        "profile": "coder",
        "description": "Alternative 4B coder core (jica98 super-coder fine-tune)",
        "output_name": "super-coder.xrlf",
    },
}

# ── XRL profiles ───────────────────────────────────────────────────────────
# Different cognitive steering configurations for different use cases.
# The XRL JSON files in xrl_encoded/ are shared, but the profile determines
# which principles/clusters are emphasized at runtime.

PROFILES = {
    "chat": {
        "description": "General conversation — warmth, reasoning, memory, self-awareness",
        "active_principles": ["empathy", "honesty", "conciseness", "memory_awareness"],
        "active_clusters": ["affective", "cognitive", "temporal"],
    },
    "coder": {
        "description": "Code generation — precision, debugging, architecture reasoning",
        "active_principles": ["precision", "conciseness", "step_by_step", "test_awareness"],
        "active_clusters": ["cognitive", "spatial", "temporal"],
    },
}


def find_gguf(model_config: dict) -> tuple[Optional[Path], Optional[Path]]:
    """Find the GGUF file (and optional mmproj) for a model."""
    base = model_config["gguf_path"]
    if not base.exists():
        return None, None

    # Find main GGUF
    gguf_files = list(base.glob(model_config["gguf_glob"]))
    gguf_path = gguf_files[0] if gguf_files else None

    # Find mmproj if specified
    mmproj_path = None
    if "mmproj_glob" in model_config:
        mmproj_files = list(base.glob(model_config["mmproj_glob"]))
        # Skip empty placeholder files
        mmproj_files = [f for f in mmproj_files if f.stat().st_size > 1000]
        mmproj_path = mmproj_files[0] if mmproj_files else None

    return gguf_path, mmproj_path


def pack_model(model_id: str, model_config: dict) -> Optional[str]:
    """Package a single model as .xrlf."""
    print(f"\n{'─' * 60}")
    print(f"  Packaging: {model_id}")
    print(f"  {model_config['description']}")
    print(f"  Profile: {model_config['profile']}")
    print(f"{'─' * 60}")

    gguf_path, mmproj_path = find_gguf(model_config)

    if not gguf_path or not gguf_path.exists():
        print(f"  ❌ GGUF not found: {model_config['gguf_path'] / model_config['gguf_glob']}")
        return None

    print(f"  GGUF   : {gguf_path}")
    print(f"  Size   : {gguf_path.stat().st_size / 1024 / 1024:.1f} MB")
    if mmproj_path:
        print(f"  MMProj : {mmproj_path} ({mmproj_path.stat().st_size / 1024 / 1024:.1f} MB)")

    output_path = OUTPUT_DIR / model_config["output_name"]
    print(f"  Output : {output_path}")

    # Build packer
    packer = XRLFPacker(
        base_model_name=model_config["base_model_name"],
        xrl_source_model=model_config["xrl_source_model"],
    )

    # Add core GGUF
    packer.add_gguf(str(gguf_path))

    # Add mmproj if available (multimodal support)
    if mmproj_path:
        packer.add_mmproj(str(mmproj_path))

    # Add XRL cognitive steering layers
    # This is the flat XRL store — designed as a clean interface so
    # a folded XRL graph (Track L / EXP-110) can replace it later.
    if XRL_DIR.exists():
        packer.add_xrl_json_dir(str(XRL_DIR))
    else:
        print(f"  ⚠️ XRL directory not found: {XRL_DIR}")

    # Add multimodal hooks
    packer.add_multimodal_hooks()

    # Add memory layer (foveated memory schema, empty DB to start)
    packer.add_memory_db(None)
    packer.add_memory_schema()

    # Add runtime metadata with profile info
    packer.add_runtime_meta()

    # Write the bundle
    t0 = time.time()
    try:
        result = packer.write(str(output_path))
        elapsed = time.time() - t0
        size_mb = Path(result).stat().st_size / 1024 / 1024
        print(f"\n  ✅ Packed in {elapsed:.1f}s")
        print(f"     Output: {result}")
        print(f"     Size: {size_mb:.1f} MB")
        return result
    except Exception as e:
        print(f"\n  ❌ Packing failed: {str(e)[:200]}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Package big MoQ GGUFs as .xrlf bundles")
    parser.add_argument("--model", type=str, choices=list(MODELS.keys()),
                        help="Specific model to package")
    parser.add_argument("--all", action="store_true",
                        help="Package all available models")
    parser.add_argument("--list", action="store_true",
                        help="List available models and exit")
    args = parser.parse_args()

    if args.list:
        print("=" * 60)
        print("  Available Models for XRLF Packaging")
        print("=" * 60)
        for mid, cfg in MODELS.items():
            gguf, mmproj = find_gguf(cfg)
            status = "✅ available" if gguf else "❌ GGUF not found"
            size = f" ({gguf.stat().st_size / 1024 / 1024:.0f} MB)" if gguf else ""
            print(f"\n  {mid}")
            print(f"    {cfg['description']}")
            print(f"    Profile: {cfg['profile']}")
            print(f"    Status: {status}{size}")
            print(f"    Output: {cfg['output_name']}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.all:
        print("=" * 60)
        print("  Packaging All Available Big Core Models")
        print("=" * 60)
        results = []
        for mid, cfg in MODELS.items():
            result = pack_model(mid, cfg)
            results.append((mid, result is not None))

        print(f"\n{'=' * 60}")
        print("  Summary")
        print(f"{'=' * 60}")
        for mid, success in results:
            status = "✅" if success else "❌"
            print(f"  {status} {mid}")
        succeeded = sum(1 for _, s in results if s)
        print(f"\n  {succeeded}/{len(results)} models packaged successfully")

    elif args.model:
        cfg = MODELS[args.model]
        result = pack_model(args.model, cfg)
        if result:
            print(f"\n✅ Done! Smoke test with:")
            print(f"   XRLFRuntime.load('{result}')")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
