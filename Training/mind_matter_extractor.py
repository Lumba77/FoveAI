r"""
mind_matter_extractor.py
========================
The Mind Matter Extractor — unified pipeline for extracting cognitive material
from any source and compressing it into XRLF 3.0 protocol files.

THE PRINCIPLE:
  The XRLF protocol IS the intelligence. Models are compute engines.
  Knowledge lives in the protocol layer, not in the weights.
  Mind matter can be extracted from any source and compressed into XRLF 3.0.

INPUT ADAPTERS (pluggable):
  --source model     Extract from a GGUF model (logits, confidence, volatility)
  --source dataset   Extract from a Hugging Face dataset (instructions, responses)
  --source local     Extract from a local JSONL file (any schema)
  --source conversation  Extract from conversation logs (emotion patterns, social dynamics)
  --source music     Extract from musical structures (tempo, key, harmony → emote tags)

OUTPUT (XRLF 3.0 compressed format):
  xrlf_rules.xrlf       — compressed directive list for prompt injection
  xrlf_clusters.xrlf    — semantic clusters for ClusterActivator
  xrlf_profiles.xrlf    — task profiles for ProfileSelector
  xrlf_emotes.xrlf      — emotion→tag mappings for the emote layer
  xrlf_principles.xrlf  — extracted principles (strength, volatility, trend)
  xrlf_graph.xrlf       — semantic concept graph for GraphTraverser

USAGE:
  # From a frozen GGUF model
  python mind_matter_extractor.py --source model --model path/to/model.gguf

  # From a Hugging Face dataset
  python mind_matter_extractor.py --source dataset --dataset HuggingFaceH4/no_robots --max 200

  # From a local JSONL file
  python mind_matter_extractor.py --source local --path data/conversations.jsonl

  # From conversation logs (emotion/social extraction)
  python mind_matter_extractor.py --source conversation --path logs/chat_history.jsonl

  # From musical structures
  python mind_matter_extractor.py --source music --path data/midi_analysis.json

  # Multiple sources, merged output
  python mind_matter_extractor.py --source dataset --dataset HuggingFaceH4/no_robots --max 100 --source model --model path/to/model.gguf
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ── Paths ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_protocol")

# ── XRLF Domain Classifiers ──────────────────────────────────────────────────

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
    "music": [
        "music", "song", "melody", "chord", "rhythm", "tempo", "key",
        "scale", "harmony", "verse", "chorus", "bridge", "instrument",
        "piano", "guitar", "drum", "vocals", "compose", "improvise",
        "progression", "mode", "tonal", "notation", "abc", "midi",
        "counterpoint", "cadence", "dominant", "seventh", "triad",
    ],
    "ethics": [
        "ethics", "moral", "right", "wrong", "ought", "should", "duty",
        "virtue", "justice", "fairness", "harm", "consent", "autonomy",
        "beneficence", "non-maleficence", "integrity", "honesty",
        "responsibility", "accountability", "dilemma", "trolley",
        "consequence", "deontolog", "utilitarian", "categorical",
    ],
    "philosophy": [
        "philosophy", "metaphysic", "epistemolog", "ontology", "being",
        "existence", "reality", "consciousness", "mind-body", "dualism",
        "monism", "idealism", "materialism", "phenomenolog", "rationalism",
        "empiricism", "pragmatism", "existential", "nihilism", "absurd",
        "dialectic", "socratic", "plato", "aristotle", "kant", "hegel",
        "nietzsche", "wisdom", "virtue", "flourishing", "eudaimonia",
    ],
    "spirituality": [
        "spiritual", "spirituality", "soul", "sacred", "divine", "holy",
        "meditation", "mindfulness", "prayer", "contemplation", "mystic",
        "transcendent", "enlightenment", "awakening", "consciousness",
        "self-realization", "atman", "brahman", "vedanta", "buddhism",
        "tao", "zen", "sufi", "mysticism", "devotion", "faith", "grace",
        "presence", "awareness", "stillness", "surrender", "ego-death",
        "nondual", "advaita", "samadhi", "dharm", "karma", "reincarn",
        "god", "religion", "theolog", "hermetic", "esoteric", "occult",
        "ritual", "sacrament", "liturgy", "scripture", "gospel", "quran",
        "bhagavad", "upanishad", "sutra", "tantra", "yoga", "mantra",
    ],
}

DOMAIN_TAGS: Dict[str, Dict[str, str]] = {
    "code": {"route": '<xrl:route specialist="code" />', "hint_prefix": "<hint:", "skeleton": "<skeleton:code>"},
    "emotion": {"route": '<xrl:route specialist="reasoning" />', "emote_prefix": "<emote:", "skeleton": "<skeleton:comfort>"},
    "social": {"route": '<xrl:route specialist="reasoning" />', "emote_prefix": "<emote:", "skeleton": "<skeleton:comfort>"},
    "music": {"route": '<xrl:route specialist="creative" />', "hint_prefix": "<hint:", "skeleton": "<skeleton:explanation>"},
    "reasoning": {"route": '<xrl:route specialist="reasoning" />', "hint_prefix": "<hint:", "skeleton": "<skeleton:explanation>"},
    "creative": {"route": '<xrl:route specialist="creative" />', "hint_prefix": "<hint:", "skeleton": "<skeleton:explanation>"},
    "memory": {"route": '<xrl:route specialist="memory" />', "recall_prefix": "<recall:"},
    "diagnostic": {"route": '<xrl:route specialist="diagnostic" />', "hint_prefix": "<hint:", "skeleton": "<skeleton:explanation>"},
    "vision": {"route": '<xrl:route specialist="vision" />'},
    "audio": {"route": '<xrl:route specialist="audio" />'},
    "music": {"route": '<xrl:route specialist="creative" />', "emote_prefix": "<emote:", "skeleton": "<skeleton:explanation>"},
    "ethics": {"route": '<xrl:route specialist="reasoning" />', "hint_prefix": "<hint:", "skeleton": "<skeleton:explanation>"},
    "philosophy": {"route": '<xrl:route specialist="reasoning" />', "hint_prefix": "<hint:", "skeleton": "<skeleton:explanation>"},
    "spirituality": {"route": '<xrl:route specialist="reasoning" />', "emote_prefix": "<emote:", "skeleton": "<skeleton:comfort>"},
}

# Emotion keyword → XRLF emote tag (from MindCore vocabulary)
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
    # Spiritual feeling tones
    "awe": "curiosity", "wonder": "curiosity", "reverence": "content",
    "peace": "calm", "serene": "calm", "bliss": "joy", "unity": "content",
    "transcendent": "content", "surrender": "calm", "devotion": "affectionate",
    "compassion": "affectionate", "mercy": "affectionate", "forgiveness": "content",
    "humility": "shy", "reverent": "content", "sacred": "content",
    "grace": "grateful", "blessed": "grateful", "surrendered": "calm",
    "stillness": "calm", "presence": "calm", "emptiness": "calm",
    "liberation": "joy", "freedom": "joy", "awakening": "curiosity",
    "realization": "curiosity", "insight": "curiosity", "clarity": "curiosity",
}

# Musical mode → emotion mapping (Western music theory)
MUSICAL_MODE_EMOTIONS: Dict[str, str] = {
    "major": "joy", "ionian": "joy",
    "minor": "concern", "aeolian": "concern",
    "dorian": "content", "mixolydian": "playful",
    "lydian": "curiosity", "phrygian": "concern", "locrian": "concern",
}

MUSICAL_TEMPO_EMOTIONS: Dict[str, Tuple[int, str]] = {
    # bpm_range → emotion
    "grave": (0, 40, "concern"),
    "largo": (40, 60, "calm"),
    "adagio": (60, 76, "calm"),
    "andante": (76, 108, "content"),
    "moderato": (108, 120, "neutral"),
    "allegro": (120, 156, "joy"),
    "presto": (156, 200, "excited" if "excited" in EMOTION_MAP else "joy"),
}


# ════════════════════════════════════════════════════════════════════════════
# RAW COGNITIVE MATERIAL — the intermediate representation
# ════════════════════════════════════════════════════════════════════════════

class MindMatter:
    """A single unit of extracted cognitive material, source-agnostic."""

    __slots__ = ("id", "source", "domain", "directive", "insight",
                 "confidence", "volatility", "trend", "emote_tags",
                 "route_tag", "keywords", "metadata")

    def __init__(self, id: int, source: str, domain: str, directive: str,
                 insight: str = "", confidence: float = 0.0,
                 volatility: float = 0.0, trend: str = "",
                 emote_tags: Optional[List[str]] = None,
                 route_tag: str = "", keywords: Optional[List[str]] = None,
                 metadata: Optional[Dict] = None):
        self.id = id
        self.source = source
        self.domain = domain
        self.directive = directive
        self.insight = insight
        self.confidence = confidence
        self.volatility = volatility
        self.trend = trend
        self.emote_tags = emote_tags or []
        self.route_tag = route_tag
        self.keywords = keywords or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "source": self.source, "domain": self.domain,
            "directive": self.directive, "insight": self.insight,
            "confidence": self.confidence, "volatility": self.volatility,
            "trend": self.trend, "emote_tags": self.emote_tags,
            "route_tag": self.route_tag, "keywords": self.keywords,
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════════════════
# INPUT ADAPTERS — each extracts MindMatter from a different source
# ════════════════════════════════════════════════════════════════════════════

class InputAdapter:
    """Base class for input adapters."""
    source_name: str = "base"

    def extract(self, **kwargs) -> List[MindMatter]:
        raise NotImplementedError


class DatasetAdapter(InputAdapter):
    """Extract mind matter from a Hugging Face dataset or local JSONL."""
    source_name = "dataset"

    def extract(self, dataset_name: Optional[str] = None,
                local_path: Optional[str] = None, split: str = "train",
                max_samples: int = 200,
                forced_domain: Optional[str] = None,
                config: Optional[str] = None) -> List[MindMatter]:
        rows = self._load_rows(dataset_name, local_path, split, max_samples, config=config)
        matter: List[MindMatter] = []
        for i, row in enumerate(rows):
            instruction, response = self._parse_row(row)
            if len(instruction) < 15:
                continue
            domain = forced_domain or classify_domain(instruction + " " + response)
            compressed = compress_text(instruction, 200)
            insight = compress_text(response, 150) if response else ""
            emote_tags = extract_emotion_tags(instruction + " " + response) if domain in ("emotion", "social") else []
            route_tag = DOMAIN_TAGS.get(domain, {}).get("route", "")
            # Extract keywords from BOTH instruction and response
            combined_text = (compressed + " " + insight).lower()
            keywords = extract_keywords(combined_text)
            matter.append(MindMatter(
                id=len(matter) + 1, source=self.source_name, domain=domain,
                directive=compressed, insight=insight,
                emote_tags=[f"<emote:{e} />" for e in emote_tags],
                route_tag=route_tag, keywords=keywords,
            ))
        return matter

    def _load_rows(self, dataset_name: Optional[str], local_path: Optional[str],
                   split: str, max_samples: int, config: Optional[str] = None) -> List[Dict]:
        if local_path:
            p = Path(local_path)
            if not p.exists():
                raise FileNotFoundError(f"Local file not found: {local_path}")
            rows = []
            with open(p, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= max_samples:
                        break
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
            print(f"  [dataset] Loaded {len(rows)} rows from {local_path}")
            return rows
        elif dataset_name:
            from datasets import load_dataset
            cfg_str = f" config={config}" if config else ""
            print(f"  [dataset] Streaming HF: {dataset_name}{cfg_str} ({split})...")
            ds = load_dataset(dataset_name, name=config, split=split, streaming=True) if config else load_dataset(dataset_name, split=split, streaming=True)
            rows = []
            for i, row in enumerate(ds):
                if i >= max_samples:
                    break
                rows.append(dict(row))
            print(f"  [dataset] Loaded {len(rows)} rows")
            return rows
        return []

    def _parse_row(self, row: Dict) -> Tuple[str, str]:
        instruction, response = "", ""
        if "messages" in row and isinstance(row["messages"], list):
            for msg in row["messages"]:
                role, content = msg.get("role", ""), msg.get("content", "")
                if role == "user" and not instruction:
                    instruction = content
                elif role == "assistant" and not response:
                    response = content
                elif role == "system" and not instruction:
                    instruction = content
        elif "conversations" in row and isinstance(row["conversations"], list):
            for msg in row["conversations"]:
                sender = msg.get("from", msg.get("role", ""))
                value = msg.get("value", msg.get("content", ""))
                if sender in ("human", "user") and not instruction:
                    instruction = value
                elif sender in ("gpt", "assistant", "model") and not response:
                    response = value
        elif "instruction" in row:
            instruction = row.get("instruction", "")
            response = row.get("output", row.get("response", ""))
        elif "prompt" in row:
            instruction = row.get("prompt", "")
            response = row.get("completion", row.get("response", ""))
        return instruction.strip(), response.strip()


class ModelAdapter(InputAdapter):
    """Extract mind matter from a GGUF model via logits and confidence paths."""
    source_name = "model"

    def extract(self, model_path: str, prompts: Optional[List[str]] = None,
                max_tokens: int = 128, n_ctx: int = 2048,
                n_gpu_layers: int = -1) -> List[MindMatter]:
        from llama_cpp import Llama
        if prompts is None:
            prompts = [
                "Explain semantic compression.",
                "Write a Python function that adds two numbers.",
                "Describe pruning vs quantization.",
                "Summarize the concept of attention in transformers.",
                "Explain how emotions affect decision making.",
                "Describe the relationship between music and mood.",
            ]
        print(f"  [model] Loading: {model_path}")
        llm = Llama(model_path=model_path, n_ctx=n_ctx,
                    n_gpu_layers=n_gpu_layers, verbose=False)
        matter: List[MindMatter] = []
        for prompt in prompts:
            result = llm(prompt, max_tokens=max_tokens, echo=True, temperature=0.7)
            text = result["choices"][0]["text"]
            logits_seq = result.get("logits", None)
            confidence, volatility, trend = 0.0, 0.0, "stable"
            if logits_seq:
                strengths = [sum(abs(l) for l in step) / max(1, len(step)) for step in logits_seq]
                confidence = sum(strengths) / len(strengths)
                mean = confidence
                var = sum((s - mean) ** 2 for s in strengths) / len(strengths)
                volatility = math.sqrt(var)
                split = max(1, len(strengths) // 3)
                early = sum(strengths[:split]) / split
                late = sum(strengths[-split:]) / max(1, split)
                trend = "strengthening" if late > early else "weakening" if late < early else "stable"
            domain = classify_domain(prompt + " " + text)
            compressed = compress_text(text, 200)
            route_tag = DOMAIN_TAGS.get(domain, {}).get("route", "")
            keywords = extract_keywords(compressed)
            matter.append(MindMatter(
                id=len(matter) + 1, source=self.source_name, domain=domain,
                directive=compress_text(prompt, 200), insight=compressed,
                confidence=round(confidence, 4), volatility=round(volatility, 4),
                trend=trend, route_tag=route_tag, keywords=keywords,
                metadata={"model": Path(model_path).name, "max_tokens": max_tokens},
            ))
        return matter


class ConversationAdapter(InputAdapter):
    """Extract mind matter from conversation logs — emotion and social patterns."""
    source_name = "conversation"

    def extract(self, local_path: str, max_samples: int = 200) -> List[MindMatter]:
        p = Path(local_path)
        if not p.exists():
            raise FileNotFoundError(f"Conversation log not found: {local_path}")
        rows = []
        with open(p, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_samples:
                    break
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        print(f"  [conversation] Loaded {len(rows)} turns from {local_path}")
        matter: List[MindMatter] = []
        for row in rows:
            user_msg = row.get("user", row.get("input", row.get("content", "")))
            ai_msg = row.get("assistant", row.get("response", row.get("output", "")))
            if isinstance(user_msg, list):
                user_msg = " ".join(m.get("content", "") for m in user_msg if isinstance(m, dict))
            if isinstance(ai_msg, list):
                ai_msg = " ".join(m.get("content", "") for m in ai_msg if isinstance(m, dict))
            if len(user_msg) < 10:
                continue
            domain = classify_domain(user_msg + " " + ai_msg)
            emote_tags = extract_emotion_tags(user_msg + " " + ai_msg)
            route_tag = DOMAIN_TAGS.get(domain, {}).get("route", "")
            matter.append(MindMatter(
                id=len(matter) + 1, source=self.source_name, domain=domain,
                directive=compress_text(user_msg, 200),
                insight=compress_text(ai_msg, 150) if ai_msg else "",
                emote_tags=[f"<emote:{e} />" for e in emote_tags],
                route_tag=route_tag,
                keywords=extract_keywords(user_msg),
                metadata={"emotions_detected": emote_tags},
            ))
        return matter


class MusicAdapter(InputAdapter):
    """Extract mind matter from musical structures — tempo, key, harmony → emote tags."""
    source_name = "music"

    def extract(self, local_path: str, max_samples: int = 200) -> List[MindMatter]:
        p = Path(local_path)
        if not p.exists():
            raise FileNotFoundError(f"Music data not found: {local_path}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        tracks = data if isinstance(data, list) else data.get("tracks", [data])
        tracks = tracks[:max_samples]
        print(f"  [music] Loaded {len(tracks)} tracks from {local_path}")
        matter: List[MindMatter] = []
        for track in tracks:
            title = track.get("title", track.get("name", "unknown"))
            tempo = track.get("tempo", track.get("bpm", 120))
            key = track.get("key", "C")
            mode = track.get("mode", "major").lower()
            chords = track.get("chords", track.get("harmony", []))
            # Map musical features to emotions
            emote = MUSICAL_MODE_EMOTIONS.get(mode, "neutral")
            for label, (lo, hi, emo) in MUSICAL_TEMPO_EMOTIONS.items():
                if lo <= tempo < hi:
                    emote = emo
                    break
            chord_str = " → ".join(chords[:8]) if chords else f"{key} {mode}"
            directive = f"Track '{title}': {tempo}BPM, {key} {mode}, chords: {chord_str}"
            insight = f"Emotional character: {emote}. Tempo suggests {self._tempo_label(tempo)}."
            matter.append(MindMatter(
                id=len(matter) + 1, source=self.source_name, domain="music",
                directive=compress_text(directive, 200),
                insight=compress_text(insight, 150),
                emote_tags=[f"<emote:{emote} />"],
                route_tag=DOMAIN_TAGS.get("music", {}).get("route", ""),
                keywords=[mode, str(tempo), key, emote],
                metadata={"tempo": tempo, "key": key, "mode": mode, "emote": emote},
            ))
        return matter

    def _tempo_label(self, bpm: int) -> str:
        for label, (lo, hi, _) in MUSICAL_TEMPO_EMOTIONS.items():
            if lo <= bpm < hi:
                return label
        return "unknown"


# ════════════════════════════════════════════════════════════════════════════
# SHARED EXTRACTION UTILITIES
# ════════════════════════════════════════════════════════════════════════════

def classify_domain(text: str) -> str:
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score:
            scores[domain] = score
    return max(scores, key=scores.__getitem__) if scores else "general"

# Common instruction/template words to filter out of keyword extraction
_INSTRUCTION_STOPWORDS = frozenset({
    "extract", "principle", "from", "this", "passage", "martinus",
    "third", "testament", "provide", "question", "answer", "input",
    "output", "query", "signal", "xrlf", "quick", "simple", "help",
    "need", "know", "determine", "classify", "route", "handler",
    "best", "handle", "check", "review", "suggest", "improvement",
    "write", "explain", "describe", "summarize", "generate", "create",
    "make", "give", "show", "tell", "what", "when", "where", "which",
    "that", "with", "have", "been", "will", "would", "could", "should",
    "they", "them", "their", "there", "these", "those", "then",
    "than", "into", "your", "youre", "were", "more", "most", "some",
    "such", "only", "very", "also", "just", "like", "even", "still",
    "well", "back", "down", "here", "into", "about", "after", "before",
})


def compress_text(text: str, max_chars: int = 200) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_period = cut.rfind(". ")
    last_comma = cut.rfind(", ")
    break_point = max(last_period, last_comma, max_chars - 30)
    return cut[:break_point].strip() + ("…" if break_point < max_chars else "")


def extract_keywords(text: str, max_count: int = 8) -> List[str]:
    """Extract meaningful keywords, filtering out instruction stopwords."""
    words = re.findall(r"\b\w{4,}\b", text.lower())
    filtered = [w for w in words if w not in _INSTRUCTION_STOPWORDS]
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: List[str] = []
    for w in filtered:
        if w not in seen:
            seen.add(w)
            result.append(w)
        if len(result) >= max_count:
            break
    return result


def extract_emotion_tags(text: str) -> List[str]:
    text_lower = text.lower()
    found: List[str] = []
    for emotion_word, emote_tag in EMOTION_MAP.items():
        if emotion_word in text_lower and emote_tag not in found:
            found.append(emote_tag)
    return found[:3]


# ════════════════════════════════════════════════════════════════════════════
# XRLF 3.0 OUTPUT BUILDERS
# ════════════════════════════════════════════════════════════════════════════

def build_rules_xrlf(matter: List[MindMatter]) -> str:
    lines = ["XRLF.3.RULES.START", ""]
    for m in matter:
        domain = m.domain.upper()
        directive = m.directive.replace("\n", " ")
        lines.append(f"RULE.{m.id} ({domain}) [{m.source}]:")
        lines.append(f"  {directive}")
        if m.insight:
            lines.append(f"  → {m.insight.replace(chr(10), ' ')}")
        if m.route_tag:
            lines.append(f"  TAG: {m.route_tag}")
        if m.emote_tags:
            lines.append(f"  EMOTE: {' '.join(m.emote_tags)}")
        if m.confidence > 0:
            lines.append(f"  CONF: {m.confidence} VOL: {m.volatility} TREND: {m.trend}")
        lines.append("")
    lines.append("XRLF.3.RULES.END")
    return "\n".join(lines)


def build_clusters_xrlf(matter: List[MindMatter]) -> str:
    clusters: Dict[str, Dict[str, int]] = {}
    for m in matter:
        if m.domain not in clusters:
            clusters[m.domain] = {}
        for word in m.keywords:
            clusters[m.domain][word] = clusters[m.domain].get(word, 0) + 1
    lines = ["XRLF.3.CLUSTERS.START", ""]
    for domain, word_counts in clusters.items():
        lines.append(f"CLUSTER.{domain}:")
        for word, count in sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:30]:
            lines.append(f"    - {word} ({count})")
        lines.append("")
    lines.append("XRLF.3.CLUSTERS.END")
    return "\n".join(lines)


def build_profiles_xrlf(matter: List[MindMatter]) -> str:
    domains = set(m.domain for m in matter)
    lines = ["XRLF.3.PROFILES.START", "", "DEFAULT_PROFILE: chat", "AUTO_DETECT: true", ""]
    for domain in domains:
        keywords = DOMAIN_KEYWORDS.get(domain, [])[:12]
        route = DOMAIN_TAGS.get(domain, {}).get("route", "")
        lines.append(f"PROFILE.{domain}:")
        lines.append(f"  TRIGGERS: {', '.join(keywords)}")
        if route:
            lines.append(f"  ROUTE: {route}")
        lines.append("")
    lines.append("XRLF.3.PROFILES.END")
    return "\n".join(lines)


def build_emotes_xrlf(matter: List[MindMatter]) -> str:
    emote_matter = [m for m in matter if m.emote_tags]
    mappings: Dict[str, List[str]] = {}
    for m in emote_matter:
        for tag in m.emote_tags:
            emotion = tag.split(":")[1].split(" ")[0].rstrip("/>")
            if emotion not in mappings:
                mappings[emotion] = []
            if m.directive not in mappings[emotion]:
                mappings[emotion].append(m.directive)
    lines = ["XRLF.3.EMOTES.START", ""]
    for emotion, examples in mappings.items():
        lines.append(f"EMOTE.{emotion}:")
        lines.append(f"  TAG: <emote:{emotion} />")
        for ex in examples[:5]:
            lines.append(f"    - {ex}")
        lines.append("")
    lines.append("XRLF.3.EMOTES.END")
    return "\n".join(lines)


def build_principles_xrlf(matter: List[MindMatter]) -> str:
    """Extract principles from model-sourced matter (confidence, volatility, trend)."""
    principled = [m for m in matter if m.confidence > 0 or m.trend]
    lines = ["XRLF.3.PRINCIPLES.START", ""]
    for m in principled:
        lines.append(f"PRINCIPLE.{m.id} ({m.domain.upper()}):")
        lines.append(f"  DIRECTIVE: {m.directive}")
        lines.append(f"  CONFIDENCE: {m.confidence}")
        lines.append(f"  VOLATILITY: {m.volatility}")
        lines.append(f"  TREND: {m.trend}")
        if m.volatility < m.confidence * 0.1:
            lines.append(f"  ROLE: confident_consistent")
        elif m.volatility > m.confidence * 0.5:
            lines.append(f"  ROLE: highly_volatile")
        else:
            lines.append(f"  ROLE: mixed_confidence")
        lines.append("")
    lines.append("XRLF.3.PRINCIPLES.END")
    return "\n".join(lines)


def build_graph_xrlf(matter: List[MindMatter]) -> str:
    """Build a semantic concept graph from keywords across all matter."""
    edges: Dict[str, Dict[str, int]] = {}
    for m in matter:
        kws = m.keywords
        for i in range(len(kws)):
            for j in range(i + 1, len(kws)):
                a, b = kws[i], kws[j]
                if a not in edges:
                    edges[a] = {}
                edges[a][b] = edges[a].get(b, 0) + 1
    lines = ["XRLF.3.GRAPH.START", ""]
    for source, targets in edges.items():
        lines.append(f"NODE.{source}:")
        for target, weight in sorted(targets.items(), key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"    - → {target} (w:{weight})")
        lines.append("")
    lines.append("XRLF.3.GRAPH.END")
    return "\n".join(lines)


def build_injection_preview(matter: List[MindMatter], limit: int = 10) -> str:
    lines = ["[XRLF.3 EXTERNAL COGNITIVE LAYER]"]
    for m in matter[:limit]:
        domain = m.domain.upper()
        lines.append(f"RULE.{m.id} ({domain}) [{m.source}]: {m.directive}")
        if m.route_tag:
            lines.append(f"  → {m.route_tag}")
    if len(matter) > limit:
        lines.append(f"... ({len(matter) - limit} more rules)")
    lines.append("[END XRLF.3 LAYER]")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def run_pipeline(sources: List[Dict[str, Any]], output_dir: Optional[Path] = None) -> None:
    print("\n" + "=" * 70)
    print("  MIND MATTER EXTRACTOR — XRLF 3.0 Protocol Material Generation")
    print("=" * 70)

    out = output_dir or OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    all_matter: List[MindMatter] = []
    for src in sources:
        source_type = src.pop("source", "dataset")
        print(f"\n  Extracting from: {source_type}")
        adapter = _get_adapter(source_type)
        matter = adapter.extract(**src)
        all_matter.extend(matter)
        print(f"  → {len(matter)} mind matter units extracted")

    if not all_matter:
        print("\n  ❌ No mind matter extracted. Check inputs.")
        return

    # Domain distribution
    domain_counts: Dict[str, int] = {}
    for m in all_matter:
        domain_counts[m.domain] = domain_counts.get(m.domain, 0) + 1
    print(f"\n  Total mind matter: {len(all_matter)}")
    print(f"  Domain distribution: {domain_counts}")

    # Build XRLF 3.0 output files
    print("\n  Building XRLF 3.0 protocol files...")

    files = [
        ("xrlf_rules.xrlf", build_rules_xrlf(all_matter), f"{len(all_matter)} rules"),
        ("xrlf_clusters.xrlf", build_clusters_xrlf(all_matter), "semantic clusters"),
        ("xrlf_profiles.xrlf", build_profiles_xrlf(all_matter), "task profiles"),
        ("xrlf_emotes.xrlf", build_emotes_xrlf(all_matter), "emotion mappings"),
        ("xrlf_principles.xrlf", build_principles_xrlf(all_matter), "principles"),
        ("xrlf_graph.xrlf", build_graph_xrlf(all_matter), "concept graph"),
    ]
    for filename, content, label in files:
        path = out / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✅ {path} ({label})")

    # Injection preview
    preview = build_injection_preview(all_matter, limit=10)
    preview_path = out / "xrlf_injection_preview.txt"
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(preview)
    print(f"  ✅ {preview_path}")

    print("\n" + "=" * 70)
    print("  ✅ Mind matter extraction complete!")
    print(f"  Output: {out}")
    print("\n  Inject into:")
    print("    MindCore.py     → xrlf_rules.xrlf (system prompt)")
    print("    ClusterActivator → xrlf_clusters.xrlf")
    print("    ProfileSelector  → xrlf_profiles.xrlf")
    print("    Emote layer      → xrlf_emotes.xrlf")
    print("    GraphTraverser   → xrlf_graph.xrlf")
    print("=" * 70)


def _get_adapter(source: str) -> InputAdapter:
    adapters = {
        "dataset": DatasetAdapter,
        "model": ModelAdapter,
        "conversation": ConversationAdapter,
        "music": MusicAdapter,
    }
    cls = adapters.get(source)
    if not cls:
        raise ValueError(f"Unknown source: {source}. Choose from: {list(adapters.keys())}")
    return cls()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mind Matter Extractor — extract XRLF 3.0 protocol material from any source",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", action="append", default=[],
                        choices=["dataset", "model", "conversation", "music"],
                        help="Input source type (can specify multiple)")
    parser.add_argument("--dataset", type=str, default=None, help="HF dataset name")
    parser.add_argument("--path", type=str, default=None, help="Local file path")
    parser.add_argument("--model", type=str, default=None, help="GGUF model path")
    parser.add_argument("--split", type=str, default="train", help="Dataset split")
    parser.add_argument("--max", type=int, default=200, help="Max samples")
    parser.add_argument("--domain", type=str, default=None, help="Force domain classification")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    if not args.source:
        print("Error: specify at least one --source")
        parser.print_help()
        sys.exit(1)

    sources: List[Dict[str, Any]] = []
    for src in args.source:
        if src == "dataset":
            if not args.dataset and not args.path:
                print("Error: --source dataset requires --dataset or --path")
                sys.exit(1)
            sources.append({"source": "dataset", "dataset_name": args.dataset,
                           "local_path": args.path, "split": args.split,
                           "max_samples": args.max, "forced_domain": args.domain})
        elif src == "model":
            if not args.model:
                print("Error: --source model requires --model")
                sys.exit(1)
            sources.append({"source": "model", "model_path": args.model, "max_samples": args.max})
        elif src == "conversation":
            if not args.path:
                print("Error: --source conversation requires --path")
                sys.exit(1)
            sources.append({"source": "conversation", "local_path": args.path, "max_samples": args.max})
        elif src == "music":
            if not args.path:
                print("Error: --source music requires --path")
                sys.exit(1)
            sources.append({"source": "music", "local_path": args.path, "max_samples": args.max})

    run_pipeline(sources, Path(args.output) if args.output else None)


if __name__ == "__main__":
    main()
