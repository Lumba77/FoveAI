#!/usr/bin/env python3
"""
Export a Hugging Face VisionEncoderDecoder captioning model to ONNX for Lumax local vision.

Produces encoder_model.onnx + decoder_model_merged.onnx (Optimum layout) plus tokenizer /
image-processor files so compagent can load ORTModelForVision2Seq from a single folder.

Default source: yesidcanoc/image-captioning-swin-tiny-distilgpt2 (English, Swin-tiny + DistilGPT2).

Requires: pip install "optimum[onnxruntime]" onnx onnxscript (same env as export machine).
Run once on host or inside foveai_ears after docker compose build foveai_soul.

Example:
  python export_tiny_vision_onnx.py --output D:/VR_AI_Forge_Data/models/frontend/Eyes/image-captioning-swin-tiny-distilgpt2-onnx
Then set FoveAI_LOCAL_VISION_MODEL_PATH to that directory (or use docker-compose default).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _which_optimum_cli() -> str | None:
    import shutil as sh

    w = sh.which("optimum-cli")
    if w:
        return w
    exe = Path(sys.executable).parent
    for name in ("optimum-cli", "optimum-cli.exe"):
        p = exe / name
        if p.is_file():
            return str(p)
    return None


def _export_via_cli(model: str, output: Path, opset: int) -> None:
    cli = _which_optimum_cli()
    if not cli:
        raise FileNotFoundError("optimum-cli not found (install optimum[onnxruntime])")
    output.mkdir(parents=True, exist_ok=True)
    cmd = [
        cli,
        "export",
        "onnx",
        "-m",
        model,
        "--task",
        "vision2seq-lm",
        "--opset",
        str(opset),
        "--trust-remote-code",
        str(output),
    ]
    subprocess.run(cmd, check=True)


def _export_via_python(model: str, output: Path, opset: int) -> None:
    from optimum.onnxruntime import ORTModelForVision2Seq

    output.mkdir(parents=True, exist_ok=True)
    try:
        ort_model = ORTModelForVision2Seq.from_pretrained(
            model,
            export=True,
            trust_remote_code=True,
            opset=opset,
        )
    except TypeError:
        ort_model = ORTModelForVision2Seq.from_pretrained(
            model,
            export=True,
            trust_remote_code=True,
        )
    ort_model.save_pretrained(output)


def _save_preprocessors(model: str, output: Path) -> None:
    from transformers import AutoImageProcessor, AutoProcessor, AutoTokenizer

    try:
        proc = AutoProcessor.from_pretrained(model, trust_remote_code=True)
        proc.save_pretrained(output)
        return
    except Exception:
        pass
    AutoImageProcessor.from_pretrained(model, trust_remote_code=True).save_pretrained(
        output
    )
    AutoTokenizer.from_pretrained(model, trust_remote_code=True).save_pretrained(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default="yesidcanoc/image-captioning-swin-tiny-distilgpt2",
        help="HF model id or local checkpoint directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory (e.g. .../frontend/Eyes/image-captioning-swin-tiny-distilgpt2-onnx)",
    )
    parser.add_argument(
        "--opset",
        type=int,
        default=18,
        help="ONNX opset (default 18; Optimum recommends >=18 for vision-encoder-decoder)",
    )
    parser.add_argument(
        "--method",
        choices=("cli", "python", "auto"),
        default="auto",
        help="Export implementation: optimum-cli (default when available), or in-process ORTModel export",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete output directory if it already exists",
    )
    args = parser.parse_args()

    out: Path = args.output.resolve()
    if out.exists() and args.overwrite:
        shutil.rmtree(out)

    try:
        if args.method == "python":
            _export_via_python(args.model, out, args.opset)
        elif args.method == "cli":
            _export_via_cli(args.model, out, args.opset)
        else:
            try:
                _export_via_cli(args.model, out, args.opset)
            except (FileNotFoundError, subprocess.CalledProcessError) as first:
                print(
                    f"optimum-cli export failed ({first}); trying in-process export...",
                    file=sys.stderr,
                )
                _export_via_python(args.model, out, args.opset)
    except Exception as ex:
        print(f"ONNX export failed: {ex}", file=sys.stderr)
        print(
            "Install: pip install 'optimum[onnxruntime]' onnx onnxscript  "
            "(rebuild foveai_ears if you use Docker).",
            file=sys.stderr,
        )
        return 1

    try:
        _save_preprocessors(args.model, out)
    except Exception as ex:
        print(
            f"Warning: could not save image processor / tokenizer into output: {ex}",
            file=sys.stderr,
        )

    enc = out / "encoder_model.onnx"
    if not enc.is_file():
        print(f"Expected {enc} missing after export.", file=sys.stderr)
        return 1

    print(f"OK: ONNX vision bundle ready at {out}")
    print("Set FoveAI_LOCAL_VISION_MODEL_PATH to this path (or add to models volume).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
