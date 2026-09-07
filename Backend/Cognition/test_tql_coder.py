"""
Phase 13: TQL-Coder Evaluation — run actual compression benchmarks.
Tests TQL-Coder-Qwen3.5-4B-thinking on levels 3/4/5 compression.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.INFO)

from summarizer_compressor import SummarizerCompressor

TQL_PATH = r"F:\Lumax\Models\Backend\Cognition\qwen\TQL-Coder\TQL-Coder-Qwen3.5-4B-thinking.IQ4_XS.gguf"

TEST_CODE = """import asyncio
from typing import Optional

class Server:
    \"\"\"Async HTTP server.\"\"\"
    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port

    async def start(self) -> None:
        \"\"\"Start the server.\"\"\"
        self._server = await asyncio.start_server(
            self._handle_client, host=self.host, port=self.port
        )
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader, writer):
        data = await reader.read(1024)
        writer.write(data)
        await writer.drain()
        writer.close()

async def main():
    server = Server()
    await server.start()
"""

# Also test on a real file
REAL_FILE = os.path.join(os.path.dirname(__file__), "tokenslayer_proxy_server.py")


def main():
    print("=" * 60)
    print("Phase 13: TQL-Coder Evaluation")
    print("=" * 60)

    # Check model exists
    print(f"\nTQL-Coder exists: {os.path.exists(TQL_PATH)}")
    if os.path.exists(TQL_PATH):
        size_gb = os.path.getsize(TQL_PATH) / 1e9
        print(f"Size: {size_gb:.2f} GB")

    # Load model
    print("\nLoading TQL-Coder (this may take a moment)...")
    t0 = time.time()
    compressor = SummarizerCompressor(
        model_path=TQL_PATH,
        n_ctx=8192,
        n_gpu_layers=-1,
        verbose=False,
    )
    load_time = time.time() - t0
    print(f"Load time: {load_time:.1f}s")
    print(f"Loaded: {compressor.is_loaded}")

    if not compressor.is_loaded:
        print("\nModel failed to load. Checking fallback paths...")
        for path in SummarizerCompressor.FALLBACK_MODEL_PATHS:
            exists = os.path.exists(path)
            size = os.path.getsize(path) / 1e9 if exists else 0
            print(f"  {os.path.basename(path) if path else 'None'}: {'EXISTS' if exists else 'NOT FOUND'} ({size:.2f} GB)" if exists else f"  {os.path.basename(path) if path else 'None'}: NOT FOUND")
        return

    # Test 1: Small test code
    print(f"\n--- Test 1: Small test code ---")
    print(f"Input: {len(TEST_CODE)} chars, {len(TEST_CODE.splitlines())} lines")

    for level in [3, 4, 5]:
        t0 = time.time()
        result = compressor.compress(TEST_CODE, level=level)
        elapsed = time.time() - t0
        ratio = len(result) / len(TEST_CODE) * 100
        print(f"\n  Level {level}: {elapsed:.2f}s, {len(result)} chars ({ratio:.1f}%)")
        print(f"  Result: {result[:200]}")

    # Test 2: Real file (tokenslayer_proxy_server.py)
    print(f"\n--- Test 2: Real file (tokenslayer_proxy_server.py) ---")
    with open(REAL_FILE, "r", encoding="utf-8") as f:
        real_code = f.read()
    print(f"Input: {len(real_code)} chars, {len(real_code.splitlines())} lines")

    for level in [3, 4, 5]:
        t0 = time.time()
        result = compressor.compress(real_code, level=level)
        elapsed = time.time() - t0
        ratio = len(result) / len(real_code) * 100
        reduction = 100 - ratio
        print(f"\n  Level {level}: {elapsed:.2f}s, {len(result)} chars ({ratio:.1f}%, {reduction:.0f}% reduction)")
        print(f"  Result (first 300 chars): {result[:300]}")

    print("\nDone.")


if __name__ == "__main__":
    main()