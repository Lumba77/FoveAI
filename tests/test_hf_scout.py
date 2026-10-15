"""
Unit test for Hugging Face Model Scout and Open XRL candidate filtering.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Forge.nursery.hf_scout import get_model_scout


def test_hf_scout_search():
    scout = get_model_scout()
    candidates = scout.search_candidates(query="Qwen3.5 MoQ", limit=3)
    assert len(candidates) > 0
    first = candidates[0]
    assert first.repo_id != ""
    assert first.filename.endswith(".gguf")
    print(f"✓ HF Scout verified: found {len(candidates)} candidates, top: {first.repo_id}/{first.filename}")


if __name__ == "__main__":
    test_hf_scout_search()
