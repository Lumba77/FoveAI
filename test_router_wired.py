r"""
test_router_wired.py
====================
Quick load + one-turn smoke test of the wired router XRLF bundle.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.xrlf_runtime import XRLFRuntime

XRLF_PATH = ROOT / "foveai-omni-router-v2.xrlf"


def main():
    if not XRLF_PATH.exists():
        print(f"❌ XRLF not found: {XRLF_PATH}")
        sys.exit(1)

    print("=" * 60)
    print("  Wiring smoke test — load XRLF with router draft")
    print("=" * 60)

    t0 = time.time()
    rt = XRLFRuntime(
        str(XRLF_PATH),
        session_id="router-wired-test",
        n_ctx=1024,
        n_gpu_layers=-1,
        verbose=True,
    )
    rt.load()
    load_t = time.time() - t0
    print(f"\n  Loaded in {load_t:.1f}s")

    print("\n--- One-turn chat smoke test ---")
    response = rt.chat(
        [{"role": "user", "content": "What is 7 + 5?"}],
        max_tokens=64,
        temperature=0.3,
    )
    print(f"Response: {response}")

    rt.close(repack_memory=False)
    print("\n✅ Wiring smoke test complete.")


if __name__ == "__main__":
    main()
