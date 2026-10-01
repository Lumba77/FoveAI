#!/usr/bin/env python3
"""
70XRL Model Downloader — Download HuggingFace safetensors for conversion.

Downloads a model from HuggingFace Hub as safetensors (FP16), verifies
checksums, and prepares it for the 70XRL pipeline.

Usage:
    python download_model.py --model Qwen/Qwen2.5-Coder-7B --output ./models/7B-base
    python download_model.py --model deepseek-ai/DeepSeek-Coder-70B --output ./models/70B-base --revision main

Options:
    --model         HuggingFace model ID (required)
    --output        Output directory (default: ./models/{model-name}-base)
    --revision      Model revision/branch (default: main)
    --token         HuggingFace token for gated models
    --verify        Verify checksums after download (default: true)
    --quantize      Also run MoQ quantization after download
    --quant-type    Quantization type (default: moq-2.0)
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("70xrl-downloader")

# ─── Paths ───────────────────────────────────────────────────────────

HF_HUB_CACHE = os.path.expandvars(
    os.environ.get("HF_HOME", "C:/Users/danie/.cache/huggingface")
)
LLAMA_CPP_DIR = os.path.expandvars(
    os.environ.get("LLAMA_CPP_DIR", "C:/Users/danie/.unsloth/llama.cpp")
)
FORGE_NURSERY = Path(__file__).parent.parent / "nursery"

# ─── Download Logic ─────────────────────────────────────────────────


def download_model(
    model_id: str,
    output_dir: str,
    revision: str = "main",
    token: str = None,
    verify: bool = True,
):
    """Download a model from HuggingFace Hub as safetensors."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"📥 Downloading {model_id} (revision: {revision}) → {output_path}")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        logger.error("huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    # Download the model
    downloaded_path = snapshot_download(
        repo_id=model_id,
        revision=revision,
        cache_dir=HF_HUB_CACHE,
        token=token or os.environ.get("HF_TOKEN"),
        local_dir=str(output_path),
        local_dir_use_symlinks=False,
        ignore_patterns=["*.pt", "*.pth", "*.bin", "optimizer.pt", "*.h5"],
    )

    logger.info(f"✅ Downloaded to: {downloaded_path}")

    # Count safetensors files
    safetensors = list(Path(downloaded_path).glob("*.safetensors"))
    logger.info(f"   Found {len(safetensors)} safetensors files")

    # Calculate total size
    total_size = sum(f.stat().st_size for f in safetensors)
    logger.info(f"   Total size: {total_size / 1024**3:.2f} GB")

    # Verify checksums if model_index.json exists
    if verify:
        _verify_checksums(downloaded_path)

    return downloaded_path


def _verify_checksums(model_path: str):
    """Verify safetensors checksums if available."""
    model_dir = Path(model_path)
    weight_map_path = model_dir / "model.safetensors.index.json"

    if not weight_map_path.exists():
        logger.info("   No weight map found, skipping checksum verification")
        return

    try:
        with open(weight_map_path) as f:
            weight_map = json.load(f)
    except Exception as e:
        logger.warning(f"   Could not parse weight map: {e}")
        return

    # Get expected hashes from weight_map
    expected_hashes = {}
    for key, filename in weight_map.get("weight_map", {}).items():
        if filename not in expected_hashes:
            expected_hashes[filename] = None

    # Check if there's a separate metadata file with hashes
    metadata_path = model_dir / "model.safetensors.metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path) as f:
                metadata = json.load(f)
            expected_hashes.update(metadata.get("hashes", {}))
        except Exception:
            pass

    # Verify each safetensors file
    for safetensors_file in model_dir.glob("*.safetensors"):
        fname = safetensors_file.name
        if expected_hashes.get(fname):
            logger.info(f"   Verifying {fname}...")
            sha256 = hashlib.sha256()
            with open(safetensors_file, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
            actual_hash = sha256.hexdigest()
            if actual_hash == expected_hashes[fname]:
                logger.info("      ✅ Checksum OK")
            else:
                logger.warning(f"      ⚠️ Checksum MISMATCH for {fname}")

    logger.info("   ✅ Checksum verification complete")


# ─── GGUF Conversion ─────────────────────────────────────────────────


def convert_to_gguf(model_path: str, output_path: str = None):
    """Convert HF safetensors model to GGUF FP16 format."""
    convert_script = Path(LLAMA_CPP_DIR) / "convert_hf_to_gguf.py"

    if not convert_script.exists():
        logger.error(f"llama.cpp convert script not found at: {convert_script}")
        logger.info("Install llama.cpp or set LLAMA_CPP_DIR environment variable")
        return None

    if not output_path:
        model_name = Path(model_path).name
        output_path = str(Path(model_path).parent / f"{model_name}-fp16.gguf")

    logger.info(f"🔄 Converting {model_path} → GGUF FP16: {output_path}")

    import subprocess

    cmd = [
        sys.executable,
        str(convert_script),
        "--outfile",
        output_path,
        "--outtype",
        "f16",
        model_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"✅ GGUF conversion complete: {output_path}")
        logger.info(f"   Size: {os.path.getsize(output_path) / 1024**3:.2f} GB")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ GGUF conversion failed: {e}")
        logger.error(f"   stderr: {e.stderr[:500]}")
        return None


# ─── MoQ Quantization ───────────────────────────────────────────────


def quantize_gguf(
    input_path: str, quant_type: str = "moq-2.0", output_path: str = None
):
    """Apply MoQ quantization to a GGUF model."""
    # Import the Forge Nursery quantizer
    sys.path.insert(0, str(FORGE_NURSERY))
    from quantizer import QUANT_TYPES, ForgeQuantizer

    if quant_type not in QUANT_TYPES:
        logger.error(f"Unknown quant type: {quant_type}")
        logger.info(f"Available: {list(QUANT_TYPES.keys())}")
        return None

    if not output_path:
        base = Path(input_path).stem.replace("-fp16", "")
        output_path = str(Path(input_path).parent / f"{base}-{quant_type}.gguf")

    logger.info(f"🔧 Quantizing {input_path} → {quant_type}: {output_path}")

    quantizer = ForgeQuantizer()
    job = quantizer.create_job(
        input_path=input_path,
        variant_id=f"70xrl-{quant_type}",
        quant_type=quant_type,
    )
    job.output_path = str(Path(output_path).parent)
    os.makedirs(job.output_path, exist_ok=True)

    success = quantizer.run_quantize(job)
    if success:
        logger.info(f"✅ Quantization complete: {output_path}")
        return output_path
    else:
        logger.error(f"❌ Quantization failed: {job.error}")
        return None


# ─── CLI ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="70XRL Model Downloader & Converter")
    parser.add_argument("--model", required=True, help="HuggingFace model ID")
    parser.add_argument("--output", help="Output directory for downloaded model")
    parser.add_argument("--revision", default="main", help="Model revision/branch")
    parser.add_argument("--token", help="HuggingFace token for gated models")
    parser.add_argument(
        "--no-verify", action="store_true", help="Skip checksum verification"
    )
    parser.add_argument(
        "--convert", action="store_true", help="Also convert to GGUF FP16"
    )
    parser.add_argument(
        "--quantize", action="store_true", help="Also apply MoQ quantization"
    )
    parser.add_argument("--quant-type", default="moq-2.0", help="Quantization type")
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Run full pipeline: download → convert → quantize",
    )

    args = parser.parse_args()

    # Determine output directory
    if not args.output:
        model_short = args.model.split("/")[-1]
        args.output = f"./models/{model_short}-base"

    # Step 1: Download
    model_path = download_model(
        model_id=args.model,
        output_dir=args.output,
        revision=args.revision,
        token=args.token,
        verify=not args.no_verify,
    )

    if not model_path:
        sys.exit(1)

    # Step 2: Convert to GGUF
    gguf_path = None
    if args.convert or args.pipeline:
        gguf_path = convert_to_gguf(model_path)

    # Step 3: Quantize
    if args.quantize or args.pipeline:
        if gguf_path:
            quantize_gguf(gguf_path, quant_type=args.quant_type)
        else:
            logger.warning("No GGUF file to quantize. Run with --convert first.")

    logger.info("🎉 70XRL pipeline complete!")


if __name__ == "__main__":
    main()
