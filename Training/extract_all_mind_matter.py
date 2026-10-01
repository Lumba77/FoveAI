r"""
extract_all_mind_matter.py
==========================
Run the Mind Matter Extractor across all downloaded Hugging Face datasets
and merge the results into a unified XRLF 3.0 protocol library.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mind_matter_extractor import (
    DatasetAdapter, MindMatter, run_pipeline, OUTPUT_DIR,
    build_rules_xrlf, build_clusters_xrlf, build_profiles_xrlf,
    build_emotes_xrlf, build_principles_xrlf, build_graph_xrlf,
    build_injection_preview,
)

# All downloaded datasets, organized by expected domain
DATASETS = [
    # Emotional intelligence & social
    {"name": "JesusAura999/SELFAWAREEMOTIONALINTELLIGENCE_DATASET_QWEN_FORMAT", "domain": "emotion", "max": 100},
    {"name": "nivvis/eq-convos", "domain": "emotion", "max": 80},
    {"name": "AI-companionship/INTIMA", "domain": "social", "max": 80},
    {"name": "opus-research/companion-boundaries", "domain": "social", "max": 60},
    {"name": "syntropy-ai/Its-Me-Soren", "domain": "social", "max": 60},

    # Memory
    {"name": "11-47/Aspire_Memory_256K", "domain": "memory", "max": 80},
    {"name": "erik1988/elias-memory-traces-v1", "domain": "memory", "max": 60},
    {"name": "wjieun/TiMeR", "domain": "memory", "max": 60},

    # Coding
    {"name": "guell00/qwen-3.8-code", "domain": "code", "max": 100},

    # Reasoning & consciousness
    {"name": "iamseungpil/metacot", "domain": "reasoning", "max": 80},
    {"name": "erik1988/consciousness-agent-sft-v3", "domain": "reasoning", "max": 80},
    {"name": "vanta-research/grounded-meta-awareness", "domain": "reasoning", "max": 60},

    # Spatial
    {"name": "Phineas476/EmbSpatial-Bench", "domain": "vision", "max": 60},

    # Audio & dialogue
    {"name": "claudiapersists/voice-dataset", "domain": "audio", "max": 60},
    {"name": "iteshxt/diachat-dataset", "domain": "audio", "max": 60},

    # Summarization
    {"name": "npc-engine/light-batch-summarize-dialogue", "domain": "memory", "max": 60},

    # General instruction
    {"name": "Magpie-Align/Magpie-Air-300K-Filtered", "domain": None, "max": 100},

    # Action commands
    {"name": "acengnew/simple-action-command-dataset", "domain": "code", "max": 60},

    # Semantic
    {"name": "franknocode/Semantic-Physiont", "domain": "reasoning", "max": 60},

    # DPO / preference
    {"name": "IntimateUser6969/llmtwin-dpo", "domain": "social", "max": 60},

    # Temporal
    {"name": "yizecheng/TicToc", "domain": "memory", "max": 60},

    # ── MUSIC: the bridge between logic and emotion ──
    {"name": "meganwei/syntheory", "config": "simple_progressions", "domain": "music", "max": 100},
    {"name": "meganwei/syntheory", "config": "chords", "domain": "music", "max": 50},
    {"name": "meganwei/syntheory", "config": "scales", "domain": "music", "max": 50},
    {"name": "4esv/rameau", "domain": "music", "max": 80},
    {"name": "sander-wood/melodyhub", "domain": "music", "max": 80},
    {"name": "m-a-p/MusicPile", "domain": "music", "max": 80},

    # ── ETHICS: the moral compass ──
    {"name": "lthn/LEM-Ethics", "config": "gold-full", "domain": "ethics", "max": 100},
    {"name": "lthn/LEM-Ethics", "config": "sovereignty", "domain": "ethics", "max": 50},

    # ── PHILOSOPHY: the higher rational mind ──
    {"name": "kiranz38/wisdom-spark-philosophical-wisdom", "domain": "philosophy", "max": 80},
    {"name": "asadf1729/convergent-wisdom", "domain": "philosophy", "max": 80},

    # ── SPIRITUALITY: the soul layer ──
    {"name": "teknium/trismegistus-project", "domain": "spirituality", "max": 80},
    {"name": "aaravshirpurkar/turiya_dataset", "domain": "spirituality", "max": 80},
    {"name": "om-ashish-soni/vivechan-spritual-text-dataset-v3", "domain": "spirituality", "max": 60},
]


def main():
    print("=" * 70)
    print("  MIND MATTER EXTRACTOR — Full Dataset Library Extraction")
    print("=" * 70)
    print(f"  Datasets to process: {len(DATASETS)}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    all_matter: list[MindMatter] = []
    adapter = DatasetAdapter()
    succeeded = 0
    failed = 0

    for i, ds in enumerate(DATASETS):
        name = ds["name"]
        domain = ds.get("domain")
        max_samples = ds.get("max", 80)
        config = ds.get("config")
        cfg_str = f" config={config}" if config else ""
        print(f"\n[{i+1}/{len(DATASETS)}] {name}{cfg_str} (domain={domain}, max={max_samples})")
        try:
            matter = adapter.extract(
                dataset_name=name,
                local_path=None,
                split="train",
                max_samples=max_samples,
                forced_domain=domain,
                config=config,
            )
            all_matter.extend(matter)
            print(f"  → {len(matter)} units extracted")
            succeeded += 1
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"  Extraction complete: {succeeded} succeeded, {failed} failed")
    print(f"  Total mind matter units: {len(all_matter)}")

    # Domain distribution
    domain_counts: dict[str, int] = {}
    for m in all_matter:
        domain_counts[m.domain] = domain_counts.get(m.domain, 0) + 1
    print(f"  Domain distribution: {domain_counts}")
    print(f"{'=' * 70}")

    if not all_matter:
        print("  ❌ No mind matter extracted.")
        return

    # Build merged XRLF 3.0 output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n  Building unified XRLF 3.0 protocol library...")

    files = [
        ("xrlf_rules.xrlf", build_rules_xrlf(all_matter), f"{len(all_matter)} rules"),
        ("xrlf_clusters.xrlf", build_clusters_xrlf(all_matter), "semantic clusters"),
        ("xrlf_profiles.xrlf", build_profiles_xrlf(all_matter), "task profiles"),
        ("xrlf_emotes.xrlf", build_emotes_xrlf(all_matter), "emotion mappings"),
        ("xrlf_principles.xrlf", build_principles_xrlf(all_matter), "principles"),
        ("xrlf_graph.xrlf", build_graph_xrlf(all_matter), "concept graph"),
    ]
    for filename, content, label in files:
        path = OUTPUT_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✅ {path} ({label})")

    preview = build_injection_preview(all_matter, limit=15)
    preview_path = OUTPUT_DIR / "xrlf_injection_preview.txt"
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(preview)
    print(f"  ✅ {preview_path}")

    print(f"\n{'=' * 70}")
    print(f"  ✅ Unified mind matter library complete!")
    print(f"  {len(all_matter)} units across {len(domain_counts)} domains")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
