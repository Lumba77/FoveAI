"""
build_multimodal_4b.py
======================
Pack the trained XRLF Coder MTP (Qwen3.5-4B) into a multimodal .xrlf bundle.

Bundle contents:
  - CORE_GGUF:     Trained Qwen3.5-4B-MTP (XRLF coder LoRA merged, Q5_K_M)
  - CORE_MMPROJ:   Qwen3.5-4B-MTP mmproj (vision: images + video)
  - XRL_MM_HOOKS:  External hooks — Whisper (STT) + Kokoro (TTS)
  - XRL_MEMORY:    Embedded foveated memory (empty seed, populated at runtime)
  - XRL cognitive:  Principles, graph, clusters from the trained model

The model is vision-native (mmproj) but NOT audio-native.
STT is handled by external Whisper hook, TTS by external Kokoro hook.
This makes the bundle truly multimodal: text + vision + audio-in + audio-out.
"""

import sys
import os
from pathlib import Path

# Add FoveAI to path for the packer
FOVEAI_DIR = Path(r"C:\Users\danie\program\LUMAX\FoveAI")
sys.path.insert(0, str(FOVEAI_DIR))

from formats.xrlf_packer import XRLFPacker
from formats.xrlf_schema import XRLFFlags

# ── Paths ────────────────────────────────────────────────────────────────────

GGUF_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_coder_mtp_q5_k_m.gguf")
MMPROJ_PATH = Path(r"C:\Users\danie\.cache\huggingface\hub\models--unsloth--Qwen3.5-4B-MTP-GGUF\snapshots\86835bf9949e4d14d6860f7910b1340ad4f271a9\mmproj-F16.gguf")
XRL_DIR = Path(r"C:\Users\danie\program\LUMAX\Tools\XRLF 1.0 dev\xrl_encoded")
OUTPUT_PATH = Path(r"C:\Users\danie\program\LUMAX\FoveAI\xrl_encoded\qwen3.5-4b-mtp-multimodal-v1.0.xrlf")

# ── Multimodal hook config ───────────────────────────────────────────────────
# Vision: native via mmproj (no external hook needed)
# STT: external Whisper (faster-whisper-base.en on :8001)
# TTS: external Kokoro (Kokoro-82M on :8004)

MULTIMODAL_HOOKS = {
    "version": 2,
    "native_multimodal": {
        "image_in":  True,   # via mmproj
        "video_in":  True,   # via mmproj (Qwen3.5-4B supports video)
        "audio_in":  False,  # NOT native — uses external Whisper hook
        "text_in":   True,
        "text_out":  True,
    },
    "external_hooks": {
        "stt": {
            "enabled": True,
            "engine": "whisper",
            "provider": "http",
            "endpoint": "http://127.0.0.1:8001/stt",
            "model": "base.en",
            "language": "en",
            "fallback": ["http", "faster-whisper", "stub"],
        },
        "tts": {
            "enabled": True,
            "engine": "auto",
            "provider": "http",
            "endpoint": "http://127.0.0.1:8004/tts",
            "voice": "default",
            "sample_rate": 22050,
            "format": "wav",
            "fallback": ["http", "kokoro", "piper", "espeak", "stub"],
        },
        "image_gen": {
            "enabled": False,
            "endpoint": "http://127.0.0.1:7860",
        },
        "audio_gen": {
            "enabled": False,
        },
    },
    "capability_map": {
        "input": {
            "text":  {"native": True,  "hook": None},
            "image": {"native": True,  "hook": None},    # mmproj
            "video": {"native": True,  "hook": None},    # mmproj
            "audio": {"native": False, "hook": "stt"},   # external Whisper
        },
        "output": {
            "text":   {"native": True,  "hook": None},
            "speech": {"native": False, "hook": "tts"},  # external Kokoro
            "image":  {"native": False, "hook": "image_gen"},
            "audio":  {"native": False, "hook": "audio_gen"},
        },
    },
}

# ── Flags: vision native, STT external, MTP for speculative decoding ─────────

MULTIMODAL_4B_FLAGS = (
    XRLFFlags.HAS_CORE_GGUF
    | XRLFFlags.IS_MULTIMODAL
    | XRLFFlags.HAS_MM_HOOKS
    | XRLFFlags.HAS_EMBEDDED_MEMORY
    | XRLFFlags.HAS_MEMORY_SCHEMA
    | XRLFFlags.MEMORY_PERSISTENT
    | XRLFFlags.VISION_NATIVE       # mmproj provides vision
    # STT_NATIVE NOT set — audio handled by external Whisper hook
    # HAS_MMPROJ NOT set — mmproj is external (in cache dir), not embedded
)

# ── Memory schema (6-ring foveated, 2048 token budget) ───────────────────────

MEMORY_SCHEMA = {
    "version": 1,
    "ring_count": 6,
    "token_budget": 2048,
    "tfidf_top_k": 5,
    "persistent": True,
    "ring_config": {
        "ring_0": {"label": "identity",    "max_tokens": 128,  "ttl_turns": None},
        "ring_1": {"label": "task",        "max_tokens": 256,  "ttl_turns": None},
        "ring_2": {"label": "recent",      "max_tokens": 512,  "ttl_turns": 8},
        "ring_3": {"label": "working",     "max_tokens": 512,  "ttl_turns": 32},
        "ring_4": {"label": "background",  "max_tokens": 384,  "ttl_turns": 128},
        "ring_5": {"label": "archive",     "max_tokens": 256,  "ttl_turns": None},
    },
}


def main():
    print("\n" + "=" * 60)
    print("  XRLF Multimodal 4B Packer")
    print("  Qwen3.5-4B-MTP Coder + Vision + Whisper + Kokoro")
    print("=" * 60)

    if not GGUF_PATH.exists():
        print(f"\n  GGUF not found: {GGUF_PATH}")
        print("  Run the f16 conversion + Q5_K_M quantization first.")
        return

    if not MMPROJ_PATH.exists():
        print(f"\n  mmproj not found: {MMPROJ_PATH}")
        return

    print(f"  Core GGUF  : {GGUF_PATH.name} ({GGUF_PATH.stat().st_size / 1e9:.2f} GB)")
    print(f"  mmproj     : {MMPROJ_PATH.name} ({MMPROJ_PATH.stat().st_size / 1e6:.0f} MB)")
    print(f"  XRL dir    : {XRL_DIR}")
    print(f"  Output     : {OUTPUT_PATH}")
    print(f"  Flags      : VISION_NATIVE, IS_MULTIMODAL, HAS_MM_HOOKS, HAS_EMBEDDED_MEMORY")
    print(f"  STT        : External Whisper hook (:8001)")
    print(f"  TTS        : External Kokoro hook (:8004)")
    print(f"  Vision     : Native via mmproj (images + video)")
    print("=" * 60 + "\n")

    packer = XRLFPacker(
        base_model_name="qwen3.5-4b-mtp-xrlf-coder",
        xrl_source_model="qwen3.5-4b-mtp",
        flags=int(MULTIMODAL_4B_FLAGS),
    )

    # 1. Core GGUF (trained model)
    packer.add_gguf(str(GGUF_PATH))

    # 2. mmproj (vision projector — external, copied to cache dir at runtime)
    # NOTE: We don't embed it in the XRLF (too large at 672MB).
    # Instead the runtime finds it in the cache dir next to the .xrlf file.
    # We'll copy it there after packing.

    # 3. XRL cognitive artifacts
    if XRL_DIR.exists():
        packer.add_xrl_json_dir(str(XRL_DIR))
    else:
        print("  WARNING: XRL dir not found, adding empty artifacts")
        packer.add_xrl_json_dir(str(FOVEAI_DIR / "xrl_encoded"))

    # 4. Multimodal hooks (Whisper STT + Kokoro TTS)
    packer.add_multimodal_hooks(MULTIMODAL_HOOKS)

    # 5. Foveated memory (empty seed — populated at runtime)
    packer.add_memory_db()
    packer.add_memory_schema(MEMORY_SCHEMA)

    # 6. Runtime metadata
    packer.add_runtime_meta()

    # 7. Write
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = packer.write(str(OUTPUT_PATH))

    print(f"\n  XRLF packed: {output}")

    # 8. Copy mmproj to cache dir so runtime finds it
    cache_dir = OUTPUT_PATH.with_suffix(".xrlf.cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    mmproj_dest = cache_dir / "mmproj.gguf"
    if not mmproj_dest.exists():
        import shutil
        print(f"  Copying mmproj to cache dir...")
        shutil.copy2(str(MMPROJ_PATH), str(mmproj_dest))
        print(f"  mmproj cached: {mmproj_dest} ({mmproj_dest.stat().st_size / 1e6:.0f} MB)")

    print(f"\n  DONE! Multimodal 4B XRLF ready.")
    print(f"  Launch: .venv/Scripts/python.exe run_xrlf.py --model {output} --port 8402 --ws-port 8403")


if __name__ == "__main__":
    main()