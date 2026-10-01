r"""
package_gemma12b_mtp_xrlf.py
=============================
Package the complete XRLF 3.0 bundle:
  - Gemma 4 12B MoQ 3.5 (5GB)        ← main model, multimodal
  - Gemma 4 12B MTP assistant (310MB) ← draft model for speculative decoding
  - Mind Matter library (781 + 96)    ← knowledge layer
  - Foveated memory schema            ← memory rings
  - Multimodal hooks                  ← TTS, vision, audio

Output: gemma-4-12b-mtp-xrlf-3.0.xrlf
"""
import json
import sys
from pathlib import Path

# Add the FoveAI to path for the packer
sys.path.insert(0, str(Path(r"C:\Users\danie\program\LUMAX\FoveAI")))

from formats.xrlf_packer import XRLFPacker, DEFAULT_MM_HOOKS, DEFAULT_MEMORY_SCHEMA
from formats.xrlf_schema import XRLFFlags, GEMMA4_DEFAULT_FLAGS

# ── Paths ────────────────────────────────────────────────────────────────────
GEMMA_MOQ_35 = r"C:\Users\danie\.cache\huggingface\hub\models--w-ahmad--Gemma-4-12B-GGUF-MoQ\MoQ-Quants\MoQ-3.5.gguf"
GEMMA_MTP_DRAFT = r"C:\Users\danie\.cache\huggingface\hub\models--gemma-4-12b-mtp-assistant\gemma-4-12B-it-assistant-MTP-Q4_K_M.gguf"
MIND_MATTER_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_protocol")
MARTINUS_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_martinus")
OUTPUT = r"C:\Users\danie\program\LUMAX\FoveAI\xrl_encoded\gemma-4-12b-mtp-xrlf-3.0.xrlf"


def load_xrlf_file(path: Path) -> str:
    """Load a .xrlf protocol file as text."""
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_mind_matter_json() -> dict:
    """Convert the .xrlf protocol files into a single JSON structure for the packer."""
    mm = {}
    for f in ["xrlf_rules.xrlf", "xrlf_clusters.xrlf", "xrlf_profiles.xrlf",
              "xrlf_emotes.xrlf", "xrlf_principles.xrlf", "xrlf_graph.xrlf"]:
        content = load_xrlf_file(MIND_MATTER_DIR / f)
        if content:
            mm[f.replace(".xrlf", "")] = content

    # Add Martinus metaphysical layer
    for f in ["xrlf_rules.xrlf", "xrlf_clusters.xrlf", "xrlf_graph.xrlf",
              "xrlf_principles.xrlf"]:
        content = load_xrlf_file(MARTINUS_DIR / f)
        if content:
            key = f"martinus_{f.replace('.xrlf', '')}"
            mm[key] = content

    return {
        "version": "3.0",
        "source": "mind_matter_extractor",
        "total_units": 781 + 96,
        "domains": [
            "emotion", "social", "memory", "reasoning", "code", "vision",
            "audio", "music", "ethics", "philosophy", "spirituality",
            "martinus_cosmology"
        ],
        "protocol_files": mm,
    }


def main():
    print("=" * 70)
    print("  XRLF 3.0 Bundle Packaging — Gemma 4 12B + MTP + Mind Matter")
    print("=" * 70)

    # Verify all files exist
    print("\n  Verifying components...")
    for label, path in [
        ("Gemma 12B MoQ 3.5", GEMMA_MOQ_35),
        ("Gemma MTP Draft", GEMMA_MTP_DRAFT),
    ]:
        p = Path(path)
        if not p.exists():
            print(f"  ❌ {label}: {path} NOT FOUND")
            sys.exit(1)
        size_gb = p.stat().st_size / 1e9
        print(f"  ✅ {label}: {size_gb:.2f} GB")

    mm_json = build_mind_matter_json()
    print(f"  ✅ Mind Matter: {mm_json['total_units']} units across {len(mm_json['domains'])} domains")

    # Build the packer
    print("\n  Building XRLF bundle...")
    packer = XRLFPacker(
        base_model_name="gemma-4-12b-it-qat-GGUF-MoQ-3.5",
        xrl_source_model="mind-matter-extractor-3.0",
        flags=int(GEMMA4_DEFAULT_FLAGS),
    )

    # 1. Core GGUF (Gemma 12B)
    packer.add_gguf(GEMMA_MOQ_35)

    # 2. Draft GGUF (Gemma MTP assistant)
    packer.add_draft_gguf(GEMMA_MTP_DRAFT)

    # 3. Mind matter as XRL principles + graph + clusters
    packer._add_json_section(
        SectionType := type("ST", (), {"name": "XRL_MIND_MATTER"})(),
        mm_json
    ) if False else None  # Use proper section type

    # Use the existing section types
    from formats.xrlf_schema import SectionType

    # Add mind matter as principles (the main knowledge layer)
    packer._add_json_section(SectionType.XRL_PRINCIPLES, mm_json)

    # Add XRLF grammar primer — teaches Gemma the protocol vocabulary
    grammar_path = Path(r"C:\Users\danie\program\LUMAX\Backend\app\xrlf_grammar.py")
    if grammar_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("xrlf_grammar", grammar_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        grammar = {
            "version": "3.0",
            "primer": mod.XRLF_GRAMMAR_PRIMER,
            "primer_compact": mod.XRLF_GRAMMAR_PRIMER_COMPACT,
        }
        packer._add_json_section(SectionType.XRL_GRAMMAR, grammar)
        print(f"  ✅ XRLF grammar primer added ({len(mod.XRLF_GRAMMAR_PRIMER)} chars)")

    # 4. Multimodal hooks (TTS, vision, audio)
    packer.add_multimodal_hooks(DEFAULT_MM_HOOKS)

    # 5. Memory schema
    packer.add_memory_schema(DEFAULT_MEMORY_SCHEMA)

    # 6. Runtime metadata
    packer.add_runtime_meta()

    # 7. Memory DB (empty seed)
    packer.add_memory_db(None)

    # Write
    print(f"\n  Writing to: {OUTPUT}")
    packer.write(OUTPUT)

    print("\n" + "=" * 70)
    print("  ✅ XRLF 3.0 bundle complete!")
    print(f"     {Path(OUTPUT).stat().st_size / 1e9:.2f} GB total")
    print("=" * 70)


if __name__ == "__main__":
    main()
