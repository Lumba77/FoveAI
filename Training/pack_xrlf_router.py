r"""
pack_xrlf_router.py
===================
Pack the XRLF router GGUF into a .xrlf bundle with XRLF artifacts.

Input: Training/outputs/xrlf_router_qwen0.5b_q4_k_m.gguf
Output: Training/outputs/xrlf_router_qwen0.5b.xrlf
"""

import os
import sys
import time
from pathlib import Path

# Make FoveAI/formats importable
PROXY_ROOT = Path(r"C:\Users\danie\program\LUMAX\FoveAI")
if str(PROXY_ROOT) not in sys.path:
    sys.path.insert(0, str(PROXY_ROOT))

from formats.xrlf_packer import XRLFPacker

GGUF_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_qwen0.5b_q4_k_m.gguf")
XRL_DIR = PROXY_ROOT / "xrl_encoded"
OUTPUT_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_qwen0.5b.xrlf")


def main():
    print("=" * 60)
    print("  Pack XRLF Router Bundle")
    print("=" * 60)
    print(f"  GGUF   : {GGUF_PATH}")
    print(f"  XRL dir: {XRL_DIR}")
    print(f"  Output : {OUTPUT_PATH}")
    print("=" * 60)

    if not GGUF_PATH.exists():
        print(f"\n❌ GGUF not found at {GGUF_PATH}")
        return

    packer = XRLFPacker(
        base_model_name="qwen2.5-0.5b-instruct",
        xrl_source_model="xrlf-router-qwen0.5b",
    )

    packer.add_gguf(str(GGUF_PATH))
    packer.add_xrl_json_dir(str(XRL_DIR))
    packer.add_multimodal_hooks()
    packer.add_memory_db(None)
    packer.add_memory_schema()
    packer.add_runtime_meta()

    t0 = time.time()
    output = packer.write(str(OUTPUT_PATH))
    elapsed = time.time() - t0
    print(f"\n✅ Bundle packed in {elapsed:.1f}s → {output}")
    print(f"   Size: {Path(output).stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
