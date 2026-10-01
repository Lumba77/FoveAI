r"""
dataset_to_xrlf.py
==================
Extract knowledge from Hugging Face datasets and compress it into XRLF
protocol material for in-context injection.

The XRLF philosophy: the protocol IS the intelligence. Models are compute
engines. Knowledge lives in the protocol layer, not in the weights.

This pipeline:
  1. Streams a HF dataset (any schema: ShareGPT, Alpaca, ChatML, instruction)
  2. Classifies each row into an XRLF domain (code, emotion, social, music, etc.)
  3. Compresses the instruction/response into XRLF tag form
  4. Outputs structured JSON ready for MindCore prompt injection

Output formats:
  - xrlf_rules.json     — flat rule list for static prompt injection
  - xrlf_clusters.json  — semantic clusters for ClusterActivator
  - xrlf_profiles.json  — task profiles for ProfileSelector
  - xrlf_emotes.json    — emotion→tag mappings for the emote layer

Usage:
  python Training/dataset_to_xrlf.py --dataset HuggingFaceH4/no_robots --max 200
  python Training/dataset_to_xrlf.py --local data/my_dataset.jsonl --domain emotion
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Paths ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_protocol")

# ── XRLF Domain Classifiers ──────────────────────────────────────────────────
# Each domain maps to XRLF tags and protocol material types.

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "code": [
        "function", "python", "javascript", "typescript", "rust", "java",
        "sql", "docker", "api", "debug", "refactor", "algorithm", "class",
        "react", "node", "compile", "syntax", "variable", "loop", "array",
    ],
    "emotion": [
        "feel", "feeling", "happy", "sad", "angry", "scared", "excited",
        "anxious", "calm", "joy", "grief", "love", "frustrated", "proud",
        "grateful", "overwhelmed", "lonely", "content", "hopeful", "worried",
    ],
    "social": [
        "conversation", "people", "friend", "relationship", "talk", "listen",
        "empathy", "boundary", "conflict", "apologize", "thank", "greet",
        "etiquette", "polite", "rude", "social", "interact", "communicate",
    ],
    "music": [
        "music", "song", "melody", "chord", "rhythm", "tempo", "key",
        "scale", "harmony", "verse", "chorus", "bridge", "instrument",
        "piano", "guitar", "drum", "vocals", "compose", "improvise",
    ],
    "reasoning": [
        "prove", "deduce", "logic", "fallacy", "argument", "because",
        "therefore", "implies", "contradiction", "hypothesis", "inference",
        "syllogism", "premise", "conclusion", "analytical", "trade-off",
    ],
    "creative": [
        "poem", "story", "write", "imagine", "create", "design", "art",
        "character", "scene", "dialogue", "screenplay", "lyrics", "novel",
        "metaphor", "imagery", "narrative", "fiction", "worldbuilding",
    ],
    "memory": [
        "remember", "recall", "earlier", "before", "last time", "previous",
        "forgot", "memory", "store", "retrieve", "archive", "history",
    ],
    "diagnostic": [
        "error", "crash", "fail", "bug", "broken", "why is", "diagnose",
        "troubleshoot", "investigate", "root cause", "trace", "log",
    ],
    "vision": [
        "image", "picture", "photo", "see", "visual", "color", "object",
        "scene", "detect", "recognize", "describe what", "look at",
    ],
    "audio": [
        "audio", "sound", "voice", "speech", "transcribe", "noise",
        "frequency", "waveform", "listen", "hear", "accent", "tone",
    ],
}

# ── XRLF Tag Templates per Domain ────────────────────────────────────────────
# These map extracted knowledge to the actual XRLF tags the router/summarizer
# already understand.

DOMAIN_TAGS: Dict[str, Dict[str, str]] = {
    "code": {
        "route": '<xrl:route specialist="code" />',
        "hint_prefix": "<hint:",
        "skeleton": "<skeleton:code>",
    },
    "emotion": {
        "route": '<xrl:route specialist="reasoning" />',
        "emote_prefix": "<emote:",
        "skeleton": "<skeleton:comfort>",
    },
    "social": {
        "route": '<xrl:route specialist="reasoning" />',
        "emote_prefix": "<emote:",
        "skeleton": "<skeleton:comfort>",
    },
    "music": {
        "route": '<xrl:route specialist="creative" />',
        "hint_prefix": "<hint:",
        "skeleton": "<skeleton:explanation>",
    },
    "reasoning": {
        "route": '<xrl:route specialist="reasoning" />',
        "hint_prefix": "<hint:",
        "skeleton": "<skeleton:explanation>",
    },
    "creative": {
        "route": '<xrl:route specialist="creative" />',
        "hint_prefix": "<hint:",
        "skeleton": "<skeleton:explanation>",
    },
    "memory": {
        "route": '<xrl:route specialist="memory" />',
        "recall_prefix": "<recall:",
    },
    "diagnostic": {
        "route": '<xrl:route specialist="diagnostic" />',
        "hint_prefix": "<hint:",
        "skeleton": "<skeleton:explanation>",
    },
    "vision": {
        "route": '<xrl:route specialist="vision" />',
    },
    "audio": {
        "route": '<xrl:route specialist="audio" />',
    },
}

# Emotion keyword → XRLF emote tag mapping (from MindCore vocabulary)
EMOTION_MAP: Dict[str, str] = {
    "happy": "joy", "joy": "joy", "glad": "joy", "delighted": "joy",
    "sad": "concern", "grief": "concern", "depressed": "concern", "down": "concern",
    "angry": "concern", "frustrated": "concern", "annoyed": "concern", "mad": "concern",
    "excited": "joy", "thrilled": "joy", "enthusiastic": "joy",
    "anxious": "concern", "worried": "concern", "nervous": "concern", "stressed": "concern",
    "calm": "calm", "peaceful": "calm", "relaxed": "calm", "serene": "calm",
    "curious": "curiosity", "interested": "curiosity", "fascinated": "curiosity",
    "proud": "proud", "accomplished": "proud", "confident": "proud",
    "grateful": "grateful", "thankful": "grateful", "appreciative": "grateful",
    "content": "content", "satisfied": "content", "fulfilled": "content",
    "shy": "shy", "bashful": "shy", "timid": "shy",
    "playful": "playful", "mischievous": "playful", "silly": "playful",
    "affectionate": "affectionate", "loving": "affectionate", "warm": "affectionate",
    "overwhelmed": "concern", "lonely": "concern", "hopeful": "curiosity",
    "surprised": "curiosity", "shocked": "curiosity", "amazed": "curiosity",
    "thinking": "curiosity", "pensive": "curiosity", "reflective": "curiosity",
    "neutral": "neutral",
}


# ── Extraction Logic ─────────────────────────────────────────────────────────

def classify_domain(text: str) -> str:
    """Classify a text snippet into an XRLF domain via keyword scoring."""
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score:
            scores[domain] = score
    if scores:
        return max(scores, key=scores.__getitem__)
    return "general"


def extract_emotion_tags(text: str) -> List[str]:
    """Extract emotion tags from text by mapping emotion words to XRLF emote tags."""
    text_lower = text.lower()
    found: List[str] = []
    for emotion_word, emote_tag in EMOTION_MAP.items():
        if emotion_word in text_lower and emote_tag not in found:
            found.append(emote_tag)
    return found[:3]  # max 3 emotions per snippet


def compress_instruction(text: str, max_chars: int = 200) -> str:
    """Compress an instruction into a compact XRLF rule."""
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text.strip())
    # Truncate at sentence boundary if possible
    if len(text) <= max_chars:
        return text
    # Find a good break point
    cut = text[:max_chars]
    last_period = cut.rfind(". ")
    last_comma = cut.rfind(", ")
    break_point = max(last_period, last_comma, max_chars - 30)
    return cut[:break_point].strip() + ("…" if break_point < max_chars else "")


def extract_response_summary(text: str, max_chars: int = 150) -> str:
    """Extract the key insight from a response, compressed."""
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= max_chars:
        return text
    # Take first sentence or first max_chars
    first_sentence = text.split(". ")[0]
    if len(first_sentence) <= max_chars:
        return first_sentence + "."
    return first_sentence[:max_chars].strip() + "…"


def parse_dataset_row(row: Dict) -> Tuple[str, str]:
    """
    Parse a dataset row into (instruction, response) regardless of schema.
    Supports: messages (ChatML), conversations (ShareGPT), instruction/response (Alpaca), prompt/completion.
    """
    instruction = ""
    response = ""

    # ChatML / OpenAI messages format
    if "messages" in row and isinstance(row["messages"], list):
        for msg in row["messages"]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and not instruction:
                instruction = content
            elif role == "assistant" and not response:
                response = content
            elif role == "system" and not instruction:
                instruction = content

    # ShareGPT conversations format
    elif "conversations" in row and isinstance(row["conversations"], list):
        for msg in row["conversations"]:
            sender = msg.get("from", msg.get("role", ""))
            value = msg.get("value", msg.get("content", ""))
            if sender in ("human", "user") and not instruction:
                instruction = value
            elif sender in ("gpt", "assistant", "model") and not response:
                response = value
            elif sender == "system" and not instruction:
                instruction = value

    # Alpaca format
    elif "instruction" in row:
        instruction = row.get("instruction", "")
        response = row.get("output", row.get("response", ""))

    # Prompt/completion format
    elif "prompt" in row:
        instruction = row.get("prompt", "")
        response = row.get("completion", row.get("response", ""))

    # System prompt format
    elif "system_prompt" in row:
        instruction = row.get("system_prompt", "")
        response = row.get("response", row.get("output", ""))

    return instruction.strip(), response.strip()


def row_to_xrlf_entry(row: Dict, row_id: int, forced_domain: Optional[str] = None) -> Optional[Dict]:
    """Convert a dataset row into an XRLF protocol entry."""
    instruction, response = parse_dataset_row(row)
    if len(instruction) < 15:
        return None

    domain = forced_domain or classify_domain(instruction + " " + response)
    compressed_instruction = compress_instruction(instruction)
    compressed_response = extract_response_summary(response) if response else ""

    entry: Dict[str, Any] = {
        "id": row_id,
        "domain": domain,
        "directive": compressed_instruction,
        "insight": compressed_response,
        "tags": DOMAIN_TAGS.get(domain, {}),
    }

    # Add emotion tags if emotion domain
    if domain in ("emotion", "social"):
        emotions = extract_emotion_tags(instruction + " " + response)
        if emotions:
            entry["emote_tags"] = [f"<emote:{e} />" for e in emotions]

    # Add routing tag
    route_tag = DOMAIN_TAGS.get(domain, {}).get("route", "")
    if route_tag:
        entry["route_tag"] = route_tag

    return entry


# ── XRLF 3.0 Output Builders ─────────────────────────────────────────────────
# XRLF 3.0 format: compressed, machine-readable, strict formatting.
# Two-space indent for paragraphs, four-space + "-" for lists, no tabs.

def build_rules_xrlf(entries: List[Dict]) -> str:
    """Build XRLF 3.0 rules file — compressed directive list for prompt injection."""
    lines = ["XRLF.3.RULES.START", ""]
    for e in entries:
        domain = e["domain"].upper()
        directive = e["directive"].replace("\n", " ")
        lines.append(f"RULE.{e['id']} ({domain}):")
        lines.append(f"  {directive}")
        if e.get("insight"):
            insight = e["insight"].replace("\n", " ")
            lines.append(f"  → {insight}")
        if e.get("route_tag"):
            lines.append(f"  TAG: {e['route_tag']}")
        if e.get("emote_tags"):
            lines.append(f"  EMOTE: {' '.join(e['emote_tags'])}")
        lines.append("")
    lines.append("XRLF.3.RULES.END")
    return "\n".join(lines)


def build_clusters_xrlf(entries: List[Dict]) -> str:
    """Build XRLF 3.0 semantic clusters for ClusterActivator."""
    clusters: Dict[str, Dict[str, int]] = {}
    for e in entries:
        domain = e["domain"]
        if domain not in clusters:
            clusters[domain] = {}
        words = re.findall(r"\b\w{4,}\b", e["directive"].lower())
        for word in words[:5]:
            clusters[domain][word] = clusters[domain].get(word, 0) + 1

    lines = ["XRLF.3.CLUSTERS.START", ""]
    for domain, word_counts in clusters.items():
        lines.append(f"CLUSTER.{domain}:")
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:30]
        for word, count in sorted_words:
            lines.append(f"    - {word} ({count})")
        lines.append("")
    lines.append("XRLF.3.CLUSTERS.END")
    return "\n".join(lines)


def build_profiles_xrlf(entries: List[Dict]) -> str:
    """Build XRLF 3.0 task profiles for ProfileSelector."""
    domains_present = set(e["domain"] for e in entries)
    lines = ["XRLF.3.PROFILES.START", "", "DEFAULT_PROFILE: chat", "AUTO_DETECT: true", ""]
    for domain in domains_present:
        keywords = DOMAIN_KEYWORDS.get(domain, [])[:12]
        route = DOMAIN_TAGS.get(domain, {}).get("route", "")
        lines.append(f"PROFILE.{domain}:")
        lines.append(f"  TRIGGERS: {', '.join(keywords)}")
        if route:
            lines.append(f"  ROUTE: {route}")
        lines.append("")
    lines.append("XRLF.3.PROFILES.END")
    return "\n".join(lines)


def build_emotes_xrlf(entries: List[Dict]) -> str:
    """Build XRLF 3.0 emotion→tag mappings for the emote layer."""
    emote_entries = [e for e in entries if e.get("emote_tags")]
    mappings: Dict[str, List[str]] = {}
    for e in emote_entries:
        for tag in e["emote_tags"]:
            emotion = tag.split(":")[1].split(" ")[0].rstrip("/>")
            if emotion not in mappings:
                mappings[emotion] = []
            directive = e["directive"].replace("\n", " ")
            if directive not in mappings[emotion]:
                mappings[emotion].append(directive)

    lines = ["XRLF.3.EMOTES.START", ""]
    for emotion, examples in mappings.items():
        lines.append(f"EMOTE.{emotion}:")
        lines.append(f"  TAG: <emote:{emotion} />")
        for ex in examples[:5]:
            lines.append(f"    - {ex}")
        lines.append("")
    lines.append("XRLF.3.EMOTES.END")
    return "\n".join(lines)


# ── Dataset Loading ──────────────────────────────────────────────────────────

def load_hf_dataset(name: str, split: str, max_samples: int, streaming: bool = True) -> List[Dict]:
    """Load a dataset from Hugging Face, streaming or full."""
    from datasets import load_dataset
    print(f"  Loading HF dataset: {name} ({split})...")
    ds = load_dataset(name, split=split, streaming=streaming)
    rows = []
    for i, row in enumerate(ds):
        if i >= max_samples:
            break
        rows.append(dict(row))
    print(f"  Loaded {len(rows)} rows")
    return rows


def load_local_dataset(path: str, max_samples: int) -> List[Dict]:
    """Load a local JSONL dataset."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Local dataset not found: {path}")
    rows = []
    with open(p, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= max_samples:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"  Loaded {len(rows)} rows from {path}")
    return rows


# ── Main Pipeline ────────────────────────────────────────────────────────────

def run_pipeline(
    dataset_name: Optional[str] = None,
    local_path: Optional[str] = None,
    split: str = "train",
    max_samples: int = 200,
    forced_domain: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> None:
    """Run the full extraction pipeline."""
    print("=" * 70)
    print("  XRLF Dataset Extraction Pipeline")
    print("=" * 70)

    out = output_dir or OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    # 1. Load dataset
    print("\n[1/4] Loading dataset...")
    if local_path:
        rows = load_local_dataset(local_path, max_samples)
    elif dataset_name:
        rows = load_hf_dataset(dataset_name, split, max_samples)
    else:
        print("  ❌ No dataset specified. Use --dataset or --local.")
        return

    if not rows:
        print("  ❌ No rows loaded. Check dataset name/path.")
        return

    # 2. Extract XRLF entries
    print(f"\n[2/4] Extracting XRLF protocol material from {len(rows)} rows...")
    entries: List[Dict] = []
    for i, row in enumerate(rows):
        entry = row_to_xrlf_entry(row, i + 1, forced_domain)
        if entry:
            entries.append(entry)

    # Domain distribution
    domain_counts: Dict[str, int] = {}
    for e in entries:
        domain_counts[e["domain"]] = domain_counts.get(e["domain"], 0) + 1
    print(f"  Extracted {len(entries)} entries")
    print(f"  Domain distribution: {domain_counts}")

    # 3. Build output files (XRLF 3.0 compressed format)
    print("\n[3/4] Building XRLF 3.0 protocol files...")

    rules_text = build_rules_xrlf(entries)
    rules_path = out / "xrlf_rules.xrlf"
    with open(rules_path, "w", encoding="utf-8") as f:
        f.write(rules_text)
    print(f"  ✅ {rules_path} ({len(entries)} rules)")

    clusters_text = build_clusters_xrlf(entries)
    clusters_path = out / "xrlf_clusters.xrlf"
    with open(clusters_path, "w", encoding="utf-8") as f:
        f.write(clusters_text)
    print(f"  ✅ {clusters_path}")

    profiles_text = build_profiles_xrlf(entries)
    profiles_path = out / "xrlf_profiles.xrlf"
    with open(profiles_path, "w", encoding="utf-8") as f:
        f.write(profiles_text)
    print(f"  ✅ {profiles_path}")

    emotes_text = build_emotes_xrlf(entries)
    emotes_path = out / "xrlf_emotes.xrlf"
    with open(emotes_path, "w", encoding="utf-8") as f:
        f.write(emotes_text)
    print(f"  ✅ {emotes_path}")

    # 4. Generate injection prompt preview
    print("\n[4/4] Generating injection prompt preview...")
    preview = generate_injection_preview_xrlf(entries, limit=10)
    preview_path = out / "xrlf_injection_preview.txt"
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(preview)
    print(f"  ✅ {preview_path}")

    print("\n" + "=" * 70)
    print("  ✅ XRLF protocol extraction complete!")
    print(f"  Output directory: {out}")
    print("\n  Next steps:")
    print("    1. Inject xrlf_rules.json into MindCore system prompt")
    print("    2. Load xrlf_clusters.json into ClusterActivator")
    print("    3. Load xrlf_profiles.json into ProfileSelector")
    print("    4. Load xrlf_emotes.json into the emote layer")
    print("=" * 70)


def generate_injection_preview_xrlf(entries: List[Dict], limit: int = 10) -> str:
    """Generate a preview of how the XRLF 3.0 rules look when injected."""
    lines = ["[XRLF.3 EXTERNAL COGNITIVE LAYER]"]
    for e in entries[:limit]:
        domain = e["domain"].upper()
        lines.append(f"RULE.{e['id']} ({domain}): {e['directive']}")
        if e.get("route_tag"):
            lines.append(f"  → {e['route_tag']}")
    if len(entries) > limit:
        lines.append(f"... ({len(entries) - limit} more rules)")
    lines.append("[END XRLF.3 LAYER]")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract XRLF protocol material from Hugging Face datasets"
    )
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="Hugging Face dataset name (e.g. HuggingFaceH4/no_robots)",
    )
    parser.add_argument(
        "--local", type=str, default=None,
        help="Local JSONL dataset path",
    )
    parser.add_argument(
        "--split", type=str, default="train",
        help="Dataset split (default: train)",
    )
    parser.add_argument(
        "--max", type=int, default=200,
        help="Maximum samples to process (default: 200)",
    )
    parser.add_argument(
        "--domain", type=str, default=None,
        choices=list(DOMAIN_KEYWORDS.keys()) + ["general"],
        help="Force a specific domain classification",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory (default: outputs/xrlf_protocol)",
    )
    args = parser.parse_args()

    if not args.dataset and not args.local:
        print("Error: specify --dataset or --local")
        parser.print_help()
        sys.exit(1)

    run_pipeline(
        dataset_name=args.dataset,
        local_path=args.local,
        split=args.split,
        max_samples=args.max,
        forced_domain=args.domain,
        output_dir=Path(args.output) if args.output else None,
    )


if __name__ == "__main__":
    main()
