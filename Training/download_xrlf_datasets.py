r"""
download_xrlf_datasets.py
=========================
Download all curated XRLF training datasets from Hugging Face.
Total: ~100 MB across 16 datasets spanning 8 domains.
"""

from huggingface_hub import snapshot_download
from pathlib import Path
import time

CACHE_DIR = Path(r"C:\Users\danie\.cache\huggingface\hub")

DATASETS = [
    # Emotional intelligence & social interaction
    ("nivvis/eq-convos", "emotional"),
    ("iteshxt/diachat-dataset", "emotional"),
    # Companionship & intimate relationships
    ("claudiapersists/voice-dataset", "companionship"),
    ("opus-research/companion-boundaries", "companionship"),
    ("AI-companionship/INTIMA", "companionship"),
    # Self-awareness & introspection
    ("vanta-research/grounded-meta-awareness", "self-awareness"),
    ("syntropy-ai/Its-Me-Soren", "self-awareness"),
    # VR / spatial reasoning
    ("Phineas476/EmbSpatial-Bench", "spatial"),
    # Temporal reasoning & spacetime awareness
    ("wjieun/TiMeR", "temporal"),
    ("yizecheng/TicToc", "temporal"),
    # Persistent memory & episodic recall
    ("erik1988/elias-memory-traces-v1", "memory"),
    ("11-47/Aspire_Memory_256K", "memory"),
    # Metacognition
    ("iamseungpil/metacot", "metacognition"),
    # AI consciousness & self-model
    ("erik1988/consciousness-agent-sft-v3", "consciousness"),
    ("franknocode/Semantic-Physiont", "consciousness"),
    # Coding instruction
    ("junaid17/qwen-coding-assistant-dataset", "coding"),
]


def main() -> None:
    print("=" * 60)
    print("  XRLF Dataset Download — 16 datasets across 8 domains")
    print("=" * 60)
    print(f"  Cache dir: {CACHE_DIR}")
    print(f"  Total datasets: {len(DATASETS)}")
    print("=" * 60)

    success = []
    failed = []

    for i, (repo_id, domain) in enumerate(DATASETS, 1):
        print(f"\n[{i}/{len(DATASETS)}] Downloading {repo_id} ({domain})...")
        try:
            t0 = time.time()
            snapshot_download(
                repo_id=repo_id,
                repo_type="dataset",
                cache_dir=str(CACHE_DIR),
            )
            elapsed = time.time() - t0
            print(f"  ✅ Done in {elapsed:.1f}s")
            success.append(repo_id)
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            failed.append((repo_id, str(e)))

    print("\n" + "=" * 60)
    print(f"  Results: {len(success)} succeeded, {len(failed)} failed")
    print("=" * 60)
    if failed:
        print("\nFailed datasets:")
        for repo_id, error in failed:
            print(f"  - {repo_id}: {error[:100]}")
    print(f"\n✅ {len(success)}/{len(DATASETS)} datasets downloaded successfully")


if __name__ == "__main__":
    main()
