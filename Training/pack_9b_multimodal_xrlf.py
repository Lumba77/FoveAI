#!/usr/bin/env python3
"""
pack_9b_multimodal_xrlf.py
============================
Linux-native packer for the Qwen3.5-9B-MoQ multimodal XRLF bundle.

Replaces the Windows-only Training/package_big_models_xrlf.py, whose hardcoded
C:\\Users\\danie\\... paths cannot run on this host.

Bundle contents:
  CORE_GGUF       Qwen3.5-9B-MoQ-<ver>.gguf        (MoQ quant core)
  CORE_MMPROJ     mmproj-qwen35-9b-Q8_0.gguf      (vision projector)
  CORE_DRAFT_GGUF draft.gguf                      (optional, --no-draft to skip)

Architecture note — "virtual android" → open service
------------------------------------------------------
Bundles were originally self-sufficient: memory AND multimodality travelled in
one file, so a virtual android carried its own senses. With XRL memory now an
open service (:8404), that argument no longer applies to the modality bridges
either — they are independently deployable and already run well as services.

  audio  → foveai-stt :8401  faster-whisper (CTranslate2) → text
  speech → foveai-tts :8411  kokoro (pip + HF cache)     → audio
  pixels → CORE_MMPROJ                                        → features

Weights and the projector stay bundled because llama-server consumes them at
load — they are coupled to inference, not separable services.

Measured reason not to embed audio (2026-10-06): XRLFRuntime extracts both
sections (xrlf_runtime.py:265, :283) and reads neither for inference. Their only
consumer is /health (api/server.py:692-693), which reports "pass" purely on file
existence. The embedded Kokoro is a PyTorch .pth stored as kokoro.onnx; the
embedded Whisper is a GGUF only whisper.cpp can read. Both ~1.2GB per bundle.

Pass --embed-audio to restore the old self-contained behaviour.

Flag policy:
  VISION_NATIVE  set   - mmproj is embedded, vision works
  STT_NATIVE     clear - Qwen3.5-9B has no audio modality; speech-in stays on
                         the faster-whisper service (:8401)
  HAS_WHISPER    set   - section embedded for a future whisper-enabled build
"""

import argparse
import sys
import time
from pathlib import Path

FOVEAI = Path("/home/lumba/FoveAI")
sys.path.insert(0, str(FOVEAI))

from formats.xrlf_packer import XRLFPacker
from formats.xrlf_schema import XRLFFlags

HUB = Path("/home/lumba/Models/hub")

CORE_GGUF = (
    HUB
    / "models--w-ahmad--Qwen3.5-9B-GGUF-MoQ"
    / "snapshots"
    / "81de037cc8ed891706af71ab294a7e882b171283"
    / "MoQ-Quants-Latest"
    / "Qwen3.5-9B-MoQ-3.6.gguf"
)
MMPROJ = HUB / "models--w-ahmad--Qwen3.5-9B-GGUF-MoQ" / "mmproj-qwen35-9b-Q8_0.gguf"
DRAFT_GGUF = HUB / "lumax-plumax-omni-router-v2.xrlf.cache" / "draft.gguf"
WHISPER_GGUF = FOVEAI / "models" / "whisper" / "whisper-base.gguf"
KOKORO_PTH = (
    HUB
    / "models--hexgrad--Kokoro-82M"
    / "snapshots"
    / "f3ff3571791e39611d31c381e3a41a3af07b4987"
    / "kokoro-v1_0.pth"
)
XRL_DIR = FOVEAI / "xrl_encoded"

# Gemma-4 defaults minus STT_NATIVE: this core cannot transcribe audio.
FLAGS = (
    XRLFFlags.HAS_CORE_GGUF
    | XRLFFlags.IS_MULTIMODAL
    | XRLFFlags.HAS_MM_HOOKS
    | XRLFFlags.HAS_EMBEDDED_MEMORY
    | XRLFFlags.HAS_MEMORY_SCHEMA
    | XRLFFlags.MEMORY_PERSISTENT
    | XRLFFlags.CORE_IS_GGUF_MoQ
    | XRLFFlags.VISION_NATIVE
)


def check(path: Path, label: str, required: bool = True) -> bool:
    if path.exists():
        print(f"  OK      {label:14s} {path.stat().st_size / 1e6:9.1f} MB  {path}")
        return True
    print(f"  MISSING {label:14s} {path}")
    if required:
        raise SystemExit(f"required input missing: {label}")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--output",
        default="/xrl_build/qwen3.5-9b-multimodal-v1.0.xrlf",
        help="output .xrlf path (default writes to /xrl_build)",
    )
    ap.add_argument(
        "--core",
        default=None,
        help="override the core GGUF path (default: MoQ 3.6 from the HF hub)",
    )
    ap.add_argument(
        "--embed-audio",
        action="store_true",
        help=(
            "Embed Kokoro/Whisper sections in the bundle. Off by default: "
            "neither is invokable from a bundle (XRLFRuntime extracts both but "
            "reads neither for inference; /health is their only consumer), and "
            "the live bridges at :8411/:8401 are strictly better "
            "(faster-whisper CTranslate2 > whisper.cpp, kokoro pip+HF cache > "
            "a .pth stored as .onnx). Bundled copies cost ~1.2GB per bundle and "
            "misreport audio capability via /health."
        ),
    )
    ap.add_argument("--no-draft", action="store_true", help="skip draft GGUF")
    ap.add_argument("--dry-run", action="store_true", help="packer dry run only")
    args = ap.parse_args()

    core = Path(args.core) if args.core else CORE_GGUF

    print("Verifying inputs")
    check(core, "core")
    check(MMPROJ, "mmproj")
    check(KOKORO_PTH, "kokoro")
    check(WHISPER_GGUF, "whisper", required=False)
    check(DRAFT_GGUF, "draft", required=False)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    free = out.parent.stat().st_f_bavail * out.stat().st_blocks if out.exists() else 0
    print(f"\nOutput: {out}")

    packer = XRLFPacker(
        base_model_name="qwen3.5-9b-coder-mtp-moq",
        xrl_source_model="qwen3.5-9b",
        flags=int(FLAGS),
    )

    packer.add_gguf(str(core))
    # Vision projector stays bundled: llama-server consumes it at load, so it is
    # coupled to inference like the weights. See module docstring.
    packer.add_mmproj(str(MMPROJ))
    if not args.no_draft and DRAFT_GGUF.exists():
        packer.add_draft_gguf(str(DRAFT_GGUF))
    if args.embed_audio:
        packer.add_whisper_gguf(str(WHISPER_GGUF))
        packer.add_kokoro_model(str(KOKORO_PTH))

    if XRL_DIR.exists():
        packer.add_xrl_json_dir(str(XRL_DIR))
    else:
        print(f"  WARN  XRL dir missing: {XRL_DIR}")

    packer.add_multimodal_hooks()
    packer.add_memory_db(None)
    packer.add_memory_schema()
    packer.add_runtime_meta()

    t0 = time.time()
    result = packer.write(str(out), dry_run=args.dry_run)
    elapsed = time.time() - t0
    print(f"\nPacked in {elapsed:.1f}s")
    print(f"  {result}")
    if not args.dry_run:
        print(f"  {Path(result).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()