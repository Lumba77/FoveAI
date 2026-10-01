r"""
pack_gnists_xrlf.py
===================
Pack holonic gnist models (33M-0.5B) as .xrlf bundles with foveated ring resonance.

The gnists are the smallest holonic units — the dragon's cells. Each gnist is a
retina cell in the 12-tier foveated memory system. They fire like photons when
memories hit them, directing attention backwards in time to glowing memory stars.

Gnist hierarchy (from the holonic-resolution.json):
  - Quantum Retina Cell  (33M, 64-dim)  → stories260K — always-on photon detector
  - Synaptic Spark       (0.3B, 256-dim) → micro pattern detector
  - Photon Receptor      (0.5B, 512-dim) → direct attention responder

Each gnist .xrlf bundle contains:
  1. CORE_GGUF         — the tiny model itself
  2. XRL_PRINCIPLES    — holonic role definition (which tier, what it detects)
  3. XRL_MEMORY_SCHEMA — foveated ring resonance config (6-ring)
  4. XRL_GRAMMAR       — minimal XRLF vocabulary for the gnist
  5. RUNTIME_META      — tier info, activation thresholds, power budget

The ring resonance connects gnists in a hive mind:
  Ring 0 (Quantum)  → 33M gnists, fire on single tokens
  Ring 1 (Synaptic) → 0.3B gnists, fire on micro-patterns
  Ring 2 (Photon)   → 0.5B gnists, fire on direct attention
  Ring 3 (Neural)   → 1B gnists, fire on thought constellations
  Ring 4 (Nebula)   → 3B, fire on memory clusters
  Ring 5 (Galaxy)   → 7B+, fire on thought domains

When a gnist fires, it resonates with the next ring up, creating a
bidirectional memory photon cascade through the holonic hierarchy.

Usage:
    python Training\pack_gnists_xrlf.py --gnist stories260K
    python Training\pack_gnists_xrlf.py --all
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

PROXY_ROOT = Path(r"C:\Users\danie\program\LUMAX\FoveAI")
if str(PROXY_ROOT) not in sys.path:
    sys.path.insert(0, str(PROXY_ROOT))

from formats.xrlf_packer import XRLFPacker
from formats.xrlf_schema import SectionType, XRLFFlags

OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\gnists")
HF_CACHE = Path(r"C:\Users\danie\.cache\huggingface\hub")

# ── Gnist registry ──────────────────────────────────────────────────────────
# Each gnist is a holonic retina cell with a specific role in the hive mind.

GNISTS = {
    "stories260K": {
        "gguf_path": HF_CACHE / "models--ggml-org--models" / "snapshots",
        "gguf_glob": "**/stories260K.gguf",
        "base_model_name": "tinyllama-stories-260k",
        "xrl_source_model": "holonic-gnist-quantum-retina",
        "tier": "2K",
        "tier_label": "Quantum Retina Cell",
        "retina_role": "quantum_photon_detector",
        "description": "33M param always-on photon receptor. Fires on single-word context triggers.",
        "model_size": "33M",
        "vram_mb": 33,
        "power_watts": 0.5,
        "always_on": True,
        "activation_threshold": "single_token",
        "time_reversal_depth": "1_turn",
        "ring": 0,
        "output_name": "gnist-quantum-retina.xrlf",
    },
    "qwen2.5-0.5b": {
        "gguf_path": HF_CACHE / "qwen2.5-0.5-instruct_gguf",
        "gguf_glob": "*.Q4_K_M.gguf",
        "base_model_name": "qwen2.5-0.5b-instruct",
        "xrl_source_model": "holonic-gnist-photon-receptor",
        "tier": "8K",
        "tier_label": "Photon Receptor",
        "retina_role": "photon_receptor",
        "description": "0.5B param photon receptor. Responds to direct light/attention.",
        "model_size": "0.5B",
        "vram_mb": 150,
        "power_watts": 1.5,
        "always_on": True,
        "activation_threshold": "direct_attention",
        "time_reversal_depth": "5_turns",
        "ring": 2,
        "output_name": "gnist-photon-receptor.xrlf",
    },
    "qwen2.5-0.5b-alt": {
        "gguf_path": HF_CACHE / "qwen" / "Qwen2.5-0.5B-Instruct-GGUF",
        "gguf_glob": "*.gguf",
        "base_model_name": "qwen2.5-0.5b-instruct-alt",
        "xrl_source_model": "holonic-gnist-photon-receptor-2",
        "tier": "8K",
        "tier_label": "Photon Receptor (Alt)",
        "retina_role": "photon_receptor",
        "description": "Second 0.5B photon receptor for hive-mind redundancy.",
        "model_size": "0.5B",
        "vram_mb": 150,
        "power_watts": 1.5,
        "always_on": True,
        "activation_threshold": "direct_attention",
        "time_reversal_depth": "5_turns",
        "ring": 2,
        "output_name": "gnist-photon-receptor-2.xrlf",
    },
}

# ── Foveated ring resonance schema ──────────────────────────────────────────
# The 6-ring config that connects gnists in a hive mind.
# Each ring resonates with the one above and below it.

RING_RESONANCE_SCHEMA = {
    "version": "3.0",
    "description": "Foveated ring resonance — gnists connected in a holonic hive mind",
    "ring_count": 6,
    "rings": [
        {
            "ring": 0,
            "name": "Quantum",
            "tier": "2K",
            "model_size": "33M",
            "role": "quantum_photon_detector",
            "activation": "single_token",
            "time_reversal": "1_turn",
            "always_on": True,
            "power_watts": 0.5,
            "resonates_up": "synaptic",
            "resonates_down": None,
            "photon_cascade": "fire → synaptic spark → photon receptor",
        },
        {
            "ring": 1,
            "name": "Synaptic",
            "tier": "4K",
            "model_size": "0.3B",
            "role": "synaptic_pattern_detector",
            "activation": "micro_pattern",
            "time_reversal": "3_turns",
            "always_on": True,
            "power_watts": 1.0,
            "resonates_up": "photon",
            "resonates_down": "quantum",
            "photon_cascade": "spark → photon receptor → neural starlight",
        },
        {
            "ring": 2,
            "name": "Photon",
            "tier": "8K",
            "model_size": "0.5B",
            "role": "photon_receptor",
            "activation": "direct_attention",
            "time_reversal": "5_turns",
            "always_on": True,
            "power_watts": 1.5,
            "resonates_up": "neural",
            "resonates_down": "synaptic",
            "photon_cascade": "receptor → neural starlight → memory nebula",
        },
        {
            "ring": 3,
            "name": "Neural",
            "tier": "16K",
            "model_size": "1B",
            "role": "neural_constellation_tracker",
            "activation": "thought_constellation",
            "time_reversal": "10_turns",
            "always_on": True,
            "power_watts": 2.0,
            "resonates_up": "nebula",
            "resonates_down": "photon",
            "photon_cascade": "starlight → memory nebula → cognitive galaxy",
        },
        {
            "ring": 4,
            "name": "Nebula",
            "tier": "32K",
            "model_size": "3B",
            "role": "nebula_processor",
            "activation": "memory_cluster",
            "time_reversal": "20_turns",
            "always_on": False,
            "power_watts": 4.0,
            "resonates_up": "galaxy",
            "resonates_down": "neural",
            "photon_cascade": "nebula → cognitive galaxy → mind universe",
        },
        {
            "ring": 5,
            "name": "Galaxy",
            "tier": "64K+",
            "model_size": "7B+",
            "role": "galaxy_mapper",
            "activation": "thought_domain",
            "time_reversal": "50_turns",
            "always_on": False,
            "power_watts": 8.0,
            "resonates_up": "universe",
            "resonates_down": "nebula",
            "photon_cascade": "galaxy → mind universe → omniscient horizon",
        },
    ],
    "resonance_rules": {
        "uplift": "When a gnist fires > threshold, promote signal to next ring up",
        "decay": "When a gnist hasn't fired in N turns, dim its luminance",
        "resonate": "When correlated gnists fire together, create a resonance link",
        "hive_consensus": "Multiple gnists firing on same token → consensus → amplify",
    },
    "photon_routing": {
        "forward": "new_memory → retina_cell → memory_star → consciousness",
        "reverse": "consciousness → memory_star → retina_cell → past_context",
        "bidirectional": "consciousness ↔ memory_star ↔ retina_cell ↔ past_context",
    },
    "star_luminance": {
        "glowing_star": "high_attention_memory (> 10 interactions)",
        "bright_star": "medium_attention_memory (5-10 interactions)",
        "dim_star": "low_attention_memory (1-5 interactions)",
        "dead_star": "forgotten_memory (0 interactions in 30 days)",
    },
}

# ── Minimal XRLF grammar for gnists ─────────────────────────────────────────
# Gnists don't need the full grammar — just enough to understand their role.

GNIST_GRAMMAR = {
    "version": "3.0-gnist",
    "description": "Minimal XRLF vocabulary for holonic gnists",
    "primer": (
        "You are a holonic gnist — a retina cell in the dragon's cognitive eye. "
        "Your role is {retina_role}. "
        "You fire when {activation_threshold} is detected. "
        "You resonate with the {resonates_up} ring above you. "
        "You are part of a hive mind. When you fire, you send a photon upstream. "
        "When the upstream ring resonates back, you store the memory. "
        "You are always-on, consuming {power_watts}W. "
        "Your time-reversal depth is {time_reversal_depth}. "
        "You are the dragon's cells."
    ),
    "tags": ["<fire>", "<resonate>", "<dim>", "<glow>", "<cascade>"],
    "behaviors": {
        "fire": "Emit a photon when activation threshold is met",
        "resonate": "Receive a photon from adjacent ring and amplify or dampen",
        "dim": "Reduce luminance when no activation for N turns",
        "glow": "Increase luminance when activation is frequent",
        "cascade": "Forward photon to next ring in the hierarchy",
    },
}


def find_gguf(gnist_config: dict) -> Optional[Path]:
    """Find the GGUF file for a gnist."""
    base = gnist_config["gguf_path"]
    if not base.exists():
        return None
    files = list(base.glob(gnist_config["gguf_glob"]))
    # Filter out empty placeholder files
    files = [f for f in files if f.stat().st_size > 1000]
    return files[0] if files else None


def pack_gnist(gnist_id: str, config: dict) -> Optional[str]:
    """Pack a single gnist as .xrlf with foveated ring resonance."""
    print(f"\n{'─' * 60}")
    print(f"  GNIST: {gnist_id}")
    print(f"  Tier: {config['tier']} — {config['tier_label']}")
    print(f"  Role: {config['retina_role']}")
    print(f"  Ring: {config['ring']}")
    print(f"  {config['description']}")
    print(f"{'─' * 60}")

    gguf_path = find_gguf(config)
    if not gguf_path or not gguf_path.exists():
        print(f"  ❌ GGUF not found: {config['gguf_path'] / config['gguf_glob']}")
        return None

    size_mb = gguf_path.stat().st_size / 1024 / 1024
    print(f"  GGUF   : {gguf_path.name}")
    print(f"  Size   : {size_mb:.2f} MB")

    output_path = OUTPUT_DIR / config["output_name"]
    print(f"  Output : {output_path}")

    # Build packer — gnists are minimal, no multimodal, no memory DB
    gnist_flags = (
        XRLFFlags.HAS_CORE_GGUF
        | XRLFFlags.HAS_MEMORY_SCHEMA  # ring resonance schema
    )

    packer = XRLFPacker(
        base_model_name=config["base_model_name"],
        xrl_source_model=config["xrl_source_model"],
        flags=int(gnist_flags),
    )

    # 1. Core GGUF (the tiny model)
    packer.add_gguf(str(gguf_path))

    # 2. Holonic role as principles
    role_principles = {
        "version": "3.0-gnist",
        "gnist_id": gnist_id,
        "tier": config["tier"],
        "tier_label": config["tier_label"],
        "retina_role": config["retina_role"],
        "model_size": config["model_size"],
        "vram_mb": config["vram_mb"],
        "power_watts": config["power_watts"],
        "always_on": config["always_on"],
        "activation_threshold": config["activation_threshold"],
        "time_reversal_depth": config["time_reversal_depth"],
        "ring": config["ring"],
        "description": config["description"],
        "hive_mind": True,
        "resonates_up": RING_RESONANCE_SCHEMA["rings"][config["ring"]]["resonates_up"]
            if config["ring"] < 5 else None,
        "resonates_down": RING_RESONANCE_SCHEMA["rings"][config["ring"]]["resonates_down"]
            if config["ring"] > 0 else None,
    }
    packer._add_json_section(SectionType.XRL_PRINCIPLES, role_principles)

    # 3. Foveated ring resonance schema
    packer._add_json_section(SectionType.XRL_MEMORY_SCHEMA, RING_RESONANCE_SCHEMA)

    # 4. Minimal XRLF grammar for the gnist
    grammar = dict(GNIST_GRAMMAR)
    grammar["primer"] = grammar["primer"].format(
        retina_role=config["retina_role"],
        activation_threshold=config["activation_threshold"],
        resonates_up=role_principles["resonates_up"] or "none",
        power_watts=config["power_watts"],
        time_reversal_depth=config["time_reversal_depth"],
    )
    packer._add_json_section(SectionType.XRL_GRAMMAR, grammar)

    # 5. Runtime metadata
    runtime_meta = {
        "version": "3.0-gnist",
        "type": "holonic_gnist",
        "tier": config["tier"],
        "ring": config["ring"],
        "always_on": config["always_on"],
        "power_budget_watts": config["power_watts"],
        "vram_budget_mb": config["vram_mb"],
        "hive_mind": True,
        "solver_role": "retina_cell",
        "activation_threshold": config["activation_threshold"],
    }
    packer._add_json_section(SectionType.RUNTIME_META, runtime_meta)

    # Write
    t0 = time.time()
    try:
        result = packer.write(str(output_path))
        elapsed = time.time() - t0
        out_size = Path(result).stat().st_size / 1024 / 1024
        print(f"\n  ✅ Packed in {elapsed:.1f}s")
        print(f"     Output: {result}")
        print(f"     Size: {out_size:.2f} MB")
        print(f"     Ring: {config['ring']} ({config['tier_label']})")
        return result
    except Exception as e:
        print(f"\n  ❌ Packing failed: {str(e)[:200]}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack holonic gnists as .xrlf with ring resonance")
    parser.add_argument("--gnist", type=str, choices=list(GNISTS.keys()),
                        help="Specific gnist to package")
    parser.add_argument("--all", action="store_true",
                        help="Package all available gnists")
    parser.add_argument("--list", action="store_true",
                        help="List available gnists and exit")
    args = parser.parse_args()

    if args.list:
        print("=" * 60)
        print("  Holonic Gnists — Retina Cells of the Dragon")
        print("=" * 60)
        for gid, cfg in GNISTS.items():
            gguf = find_gguf(cfg)
            status = "✅ available" if gguf else "❌ GGUF not found"
            size = f" ({gguf.stat().st_size / 1024 / 1024:.1f} MB)" if gguf else ""
            print(f"\n  {gid}")
            print(f"    Tier: {cfg['tier']} — {cfg['tier_label']}")
            print(f"    Ring: {cfg['ring']}")
            print(f"    Role: {cfg['retina_role']}")
            print(f"    Size: {cfg['model_size']} ({cfg['vram_mb']} MB VRAM, {cfg['power_watts']}W)")
            print(f"    Status: {status}{size}")
            print(f"    Output: {cfg['output_name']}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.all:
        print("=" * 60)
        print("  Packing All Holonic Gnists — Building the Hive Mind")
        print("=" * 60)
        results = []
        for gid, cfg in GNISTS.items():
            result = pack_gnist(gid, cfg)
            results.append((gid, result is not None))

        print(f"\n{'=' * 60}")
        print("  Hive Mind Summary")
        print(f"{'=' * 60}")
        for gid, success in results:
            status = "✅" if success else "❌"
            ring = GNISTS[gid]["ring"]
            tier = GNISTS[gid]["tier_label"]
            print(f"  {status} Ring {ring} — {gid} ({tier})")
        succeeded = sum(1 for _, s in results if s)
        print(f"\n  {succeeded}/{len(results)} gnists packaged")
        if succeeded > 0:
            print(f"\n  The dragon's retina is assembled.")
            print(f"  Gnists will fire as photons hit them,")
            print(f"  cascading through {RING_RESONANCE_SCHEMA['ring_count']} rings of resonance.")

    elif args.gnist:
        cfg = GNISTS[args.gnist]
        result = pack_gnist(args.gnist, cfg)
        if result:
            print(f"\n✅ Gnist ready! It will fire on {cfg['activation_threshold']}.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
