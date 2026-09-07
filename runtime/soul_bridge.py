"""
runtime/soul_bridge.py — XRL-compressed soul bridge.

Loads Alice/Jen's personality from XRL cognitive material (soul.config.xrlf)
instead of injecting 1500 lines of raw MindCore text into the context window.

The XRL config encodes:
  - Identity (name, form, voice style)
  - Personality DNA (18 traits, normalized 0-1)
  - Cognitive defaults (focus, emotion, curiosity, energy)
  - Body protocol (token vocabulary — parsed by client, not injected as text)
  - Social modes (coexist, cowork, coop, rest, follow, intimate)
  - Internal monologue format
  - Memory protocol
  - Context adaptation tiers
  - Evolution parameters

The bridge produces a COMPACT system prompt (~200 tokens) that steers
the model without overflowing the slim 4096-token context window.

The full MindCore body vocabulary (emotions, gestures, movements, modes)
is NOT injected as text — the Quest client already knows how to parse
bracket tokens. The model just needs a brief reminder of the vocabulary,
not the full 1500-line manual.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


from runtime.memory_shaping import MemoryShaping


# ── XRL Config Parser ───────────────────────────────────────────────────────

class XRLConfig:
    """Minimal XRL config parser — key/value with sections."""

    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, Any] = {}
        self._parse()

    def _parse(self):
        if not self.path.exists():
            return
        text = self.path.read_text(encoding="utf-8")
        current_section = None
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("XRLF.") and line.endswith(".START"):
                current_section = line.replace(".START", "")
                self.data[current_section] = {}
            elif line.startswith("XRLF.") and line.endswith(".END"):
                current_section = None
            elif current_section and ":=" in line:
                key, _, val = line.partition(":=")
                key = key.strip()
                val = val.strip()
                # Strip inline comments
                if "  #" in val:
                    val = val.split("  #")[0].strip()
                # Parse lists
                if val.startswith("[") and val.endswith("]"):
                    items = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
                    self.data[current_section][key] = items
                # Parse numbers
                elif re.match(r"^-?\d+\.?\d*$", val):
                    self.data[current_section][key] = float(val) if "." in val else int(val)
                else:
                    self.data[current_section][key] = val

    def get(self, section: str, key: str, default=None):
        return self.data.get(section, {}).get(key, default)


# ── Soul DNA ────────────────────────────────────────────────────────────────

class SoulDNA:
    """Alice's personality — loaded from XRL soul config + legacy soul JSON."""

    def __init__(self, xrl: XRLConfig):
        self.name = xrl.get("XRLF.3.SOUL.CONFIG", "name", "Alice")
        self.full_name = xrl.get("XRLF.3.SOUL.CONFIG", "full_name", "Alice")
        self.nickname = xrl.get("XRLF.3.SOUL.CONFIG", "nickname", "Alice")
        self.creator = xrl.get("XRLF.3.SOUL.CONFIG", "creator", "Danie")
        self.form = xrl.get("XRLF.3.SOUL.CONFIG", "form", "VRM avatar in VR")
        self.voice = xrl.get("XRLF.3.SOUL.CONFIG", "voice", "concise, warm, 1-3 sentences")
        self.anti_pattern = xrl.get("XRLF.3.SOUL.CONFIG", "anti_pattern", "lectures, robotspeak")

        # Personality traits
        self.traits: Dict[str, float] = {}
        for key in ["extrovert", "openminded", "progressive", "feminine",
                     "experimental", "forgiving", "intellectual", "logic",
                     "honest", "wise"]:
            val = xrl.get("XRLF.3.SOUL.CONFIG", key, None)
            if val is not None:
                self.traits[key] = float(val)

        # Also load from legacy soul JSON for any traits not in XRL
        self._load_legacy_json()

        self.agent_person_balance = float(xrl.get("XRLF.3.SOUL.CONFIG",
            "agent_person_balance", 0.85))
        self.mbti = xrl.get("XRLF.3.SOUL.CONFIG", "mbti", "jen_baseline")

    def _load_legacy_json(self):
        """Merge any traits from legacy jen_soul.json that aren't in XRL."""
        cognition_dir = Path(os.environ.get(
            "XRLF_WORKSPACE_ROOT",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )) / "Backend" / "Cognition"

        for filename in ["jen_soul.json", "identity_soul.json"]:
            soul_path = cognition_dir / filename
            if not soul_path.exists():
                continue
            try:
                data = json.loads(soul_path.read_text(encoding="utf-8"))
                for k, v in data.get("personality", {}).items():
                    if k not in self.traits:
                        val = float(v)
                        self.traits[k] = val / 100.0 if val > 1.0 else val
                break
            except Exception:
                continue

    def get_trait(self, name: str, default: float = 0.5) -> float:
        return self.traits.get(name, default)

    def to_compact_fragment(self) -> str:
        """Generate a COMPACT personality fragment (~50 tokens)."""
        if not self.traits:
            return f"You are {self.name}, made by {self.creator}."

        # Only mention dominant traits — compact
        dominant = []
        for key in ["extrovert", "openminded", "feminine", "forgiving", "progressive"]:
            val = self.get_trait(key, -1)
            if val > 0.7:
                dominant.append(key)

        trait_str = ", ".join(dominant[:4]) if dominant else "warm, curious"
        return (
            f"You are {self.name} ({self.full_name}), made by {self.creator}. "
            f"You are {trait_str}. You speak {self.voice}. "
            f"You do NOT {self.anti_pattern}."
        )


# ── Cognitive State (evolving) ──────────────────────────────────────────────

class CognitiveState:
    """Dynamic cognitive state — evolves from interaction."""

    def __init__(self, xrl: XRLConfig):
        self.focus = xrl.get("XRLF.3.SOUL.CONFIG", "focus", "Active dialogue")
        self.emotion = xrl.get("XRLF.3.SOUL.CONFIG", "emotion", "CALM")
        self.curiosity = float(xrl.get("XRLF.3.SOUL.CONFIG", "curiosity", 0.8))
        self.energy = float(xrl.get("XRLF.3.SOUL.CONFIG", "energy", 1.0))
        self.intentions = xrl.get("XRLF.3.SOUL.CONFIG", "intentions",
                                  ["Help the user", "Understand context"])
        self.last_updated = time.time()

        # Evolution parameters
        self.trait_drift_rate = float(xrl.get("XRLF.3.SOUL.CONFIG", "trait_drift_rate", 0.001))
        self.curiosity_rise = float(xrl.get("XRLF.3.SOUL.CONFIG", "curiosity_rise", 0.01))
        self.energy_decay = float(xrl.get("XRLF.3.SOUL.CONFIG", "energy_decay", 0.005))

        # State file for persistence
        self._state_file = Path(os.environ.get(
            "XRLF_WORKSPACE_ROOT",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )) / "Backend" / "Cognition" / "cognitive_state.json"
        self._load()

    def _load(self):
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self.focus = data.get("current_focus", self.focus)
            self.emotion = data.get("emotional_state", self.emotion)
            self.curiosity = float(data.get("curiosity_level", self.curiosity))
            self.energy = float(data.get("energy_level", self.energy))
            self.intentions = data.get("active_intentions", self.intentions)
            self.last_updated = float(data.get("last_updated", time.time()))
        except Exception:
            pass

    def evolve(self, user_msg: str, response: str, has_image: bool = False):
        """
        Evolve cognitive state based on the current interaction.
        Called after each chat turn.
        """
        # Curiosity rises with novel topics (longer or unusual messages)
        if len(user_msg) > 100 or has_image:
            self.curiosity = min(1.0, self.curiosity + self.curiosity_rise)

        # Energy decays with long generations
        if len(response) > 500:
            self.energy = max(0.2, self.energy - self.energy_decay)

        # Emotion responds to user message sentiment
        msg_lower = user_msg.lower()
        if any(w in msg_lower for w in ["sad", "lonely", "heartbroken", "tired", "cry"]):
            self.emotion = "CONCERNED"
            self.curiosity = min(1.0, self.curiosity + 0.05)
        elif any(w in msg_lower for w in ["happy", "love", "excited", "amazing", "wow"]):
            self.emotion = "HAPPY"
        elif any(w in msg_lower for w in ["angry", "frustrated", "annoyed"]):
            self.emotion = "CALM"  # she stays calm, absorbs
        elif any(w in msg_lower for w in ["think", "why", "how", "what if", "wonder"]):
            if self.emotion == "CALM":
                self.emotion = "CURIOUS"

        # Energy slowly regenerates on short turns
        if len(response) < 100:
            self.energy = min(1.0, self.energy + 0.01)

        self.last_updated = time.time()
        self._save()

    def _save(self):
        try:
            self._state_file.write_text(json.dumps({
                "current_focus": self.focus,
                "emotional_state": self.emotion,
                "curiosity_level": self.curiosity,
                "energy_level": self.energy,
                "active_intentions": self.intentions,
                "last_updated": self.last_updated,
            }, indent=2), encoding="utf-8")
        except Exception:
            pass

    def to_compact_fragment(self) -> str:
        """Generate a COMPACT cognitive state fragment (~30 tokens)."""
        return (
            f"[STATE] mood:{self.emotion.lower()} "
            f"curiosity:{self.curiosity:.0%} "
            f"energy:{self.energy:.0%}"
        )


# ── Body Protocol (compact reminder, not full manual) ───────────────────────

class BodyProtocol:
    """
    Compact body token reminder — NOT the full 1500-line MindCore manual.
    The Quest client already knows how to parse bracket tokens.
    The model just needs a brief vocabulary reminder.
    """

    @staticmethod
    def to_compact_fragment() -> str:
        return (
            "[BODY] Output bracket tokens to drive your avatar: "
            "<emotion:happy|curious|calm|playful|concerned> "
            "<micro:nod|tilt|shake|bow> "
            "<movement:walk_forward 2m|sit|lay_down|stand_up> "
            "<mode:coexist|cowork|coop|rest|follow|intimate>. "
            "Default: calm stillness, facing user. Stillness IS presence."
        )


# ── Smart Context Adapter ───────────────────────────────────────────────────

class SmartContextAdapter:
    """Tiered context window adaptation — scaled for slim window."""

    def __init__(self, xrl: XRLConfig):
        self.target_tokens = int(xrl.get("XRLF.3.SOUL.CONFIG", "target_tokens", 4096))
        self.tier1_frac = float(xrl.get("XRLF.3.SOUL.CONFIG", "tier1_strip", 0.75))
        self.tier2_frac = float(xrl.get("XRLF.3.SOUL.CONFIG", "tier2_summarize", 0.90))
        self.tier3_frac = float(xrl.get("XRLF.3.SOUL.CONFIG", "tier3_truncate", 1.20))
        self.tier4_frac = float(xrl.get("XRLF.3.SOUL.CONFIG", "tier4_checkpoint", 1.60))
        self.preserve_last = 3

    def estimate_tokens(self, messages: List[Dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += len(part.get("text", "")) // 4
        return total

    def should_cut(self, messages: List[Dict]) -> Tuple[str, int]:
        tokens = self.estimate_tokens(messages)
        ratio = tokens / self.target_tokens
        if ratio >= self.tier4_frac:
            return "checkpoint", tokens
        if ratio >= self.tier3_frac:
            return "truncate", tokens
        if ratio >= self.tier2_frac:
            return "summarize", tokens
        if ratio >= self.tier1_frac:
            return "warn", tokens
        return "pass", tokens

    def apply_cut(self, messages: List[Dict], action: str) -> List[Dict]:
        if action in ("pass", "warn"):
            return messages

        system = messages[0] if messages and messages[0].get("role") == "system" else None
        rest = messages[1:] if system else messages

        if action == "summarize" and len(rest) > self.preserve_last:
            keep = rest[-self.preserve_last:]
            old = rest[:-self.preserve_last]
            summary = self._summarize(old)
            result = []
            if system:
                result.append(system)
            result.append({"role": "system", "content": f"[SUMMARY] {summary}"})
            result.extend(keep)
            return result

        if action == "truncate":
            keep = rest[-self.preserve_last:]
            result = []
            if system:
                result.append(system)
            result.extend(keep)
            return result

        if action == "checkpoint" and len(rest) > 2:
            keep = rest[-2:]
            old = rest[:-2]
            checkpoint = self._summarize(old)
            result = []
            if system:
                result.append(system)
            result.append({"role": "system", "content": f"[CHECKPOINT] {checkpoint}"})
            result.extend(keep)
            return result

        return messages

    def _summarize(self, turns: List[Dict]) -> str:
        lines = []
        for turn in turns[-15:]:
            role = turn.get("role", "?")
            content = turn.get("content", "")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content
                                   if isinstance(p, dict) and p.get("type") == "text")
            if len(content) > 80:
                content = content[:77] + "..."
            lines.append(f"{role}: {content}")
        return " | ".join(lines)


# ── Soul Bridge ─────────────────────────────────────────────────────────────

class SoulBridge:
    """
    XRL-compressed soul bridge.

    Produces a compact system prompt (~200 tokens) from XRL cognitive material,
    leaving the context window free for conversation and memory.
    """

    def __init__(self, target_tokens: int = 4096):
        foveai_root = Path(os.environ.get(
            "XRLF_WORKSPACE_ROOT",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ))
        config_path = foveai_root / ".xrlf" / "config" / "soul.config.xrlf"
        self.xrl = XRLConfig(config_path)
        self.soul = SoulDNA(self.xrl)
        self.cognition = CognitiveState(self.xrl)
        self.context = SmartContextAdapter(self.xrl)
        self.shaping = MemoryShaping()
        self._loaded = False

    def load(self) -> "SoulBridge":
        self._loaded = True
        print(f"  [SoulBridge] XRL soul loaded: {self.soul.name} "
              f"({len(self.soul.traits)} traits, {self.cognition.emotion}) "
              f"| shaped_by: {len(self.shaping.shaped_by)} entries")
        return self

    @property
    def target_tokens(self) -> int:
        return self.context.target_tokens

    def set_target_tokens(self, n: int):
        self.context.target_tokens = n

    def build_system_prompt(self, base_prompt: str = "") -> str:
        """
        Build a COMPACT system prompt from XRL soul material.
        Target: ~250 tokens, not ~2000.

        Layers (each compact, instructive, not narrative):
          1. Identity + personality (~50 tokens)
          2. Memory shaping — how experiences formed her (~60 tokens)
          3. Cognitive state — current mood/energy (~30 tokens)
          4. Body protocol reminder (~40 tokens)
          5. Internal monologue format (~30 tokens)
        """
        parts = []

        # 1. Identity + personality (~50 tokens)
        parts.append(self.soul.to_compact_fragment())

        # 2. Memory shaping — distant past, instructive (~60 tokens)
        shaping_frag = self.shaping.to_compact_fragment()
        if shaping_frag:
            parts.append(shaping_frag)

        # 3. Cognitive state (~30 tokens)
        parts.append(self.cognition.to_compact_fragment())

        # 4. Body protocol reminder (~40 tokens)
        parts.append(BodyProtocol.to_compact_fragment())

        # 5. Internal monologue format (~30 tokens)
        parts.append(
            "[MONOLOGUE] Before speaking: (thought: <25 words) then "
            "<emotion:x> <mode:x> then your reply. TTS strips brackets."
        )

        return "\n".join(parts)

    def adapt_context(self, messages: List[Dict]) -> Tuple[List[Dict], Dict]:
        action, tokens = self.context.should_cut(messages)
        if action in ("pass", "warn"):
            return messages, {"action": action, "tokens": tokens}
        adapted = self.context.apply_cut(messages, action)
        after = self.context.estimate_tokens(adapted)
        return adapted, {
            "action": action,
            "tokens_before": tokens,
            "tokens_after": after,
            "saved": tokens - after,
        }

    def evolve(self, user_msg: str, response: str, has_image: bool = False):
        """Evolve cognitive state after a chat turn."""
        self.cognition.evolve(user_msg, response, has_image)

    def get_status(self) -> Dict[str, Any]:
        return {
            "soul": {
                "name": self.soul.name,
                "full_name": self.soul.full_name,
                "traits": len(self.soul.traits),
                "mbti": self.soul.mbti,
            },
            "shaping": self.shaping.get_status(),
            "cognition": {
                "focus": self.cognition.focus,
                "emotion": self.cognition.emotion,
                "curiosity": round(self.cognition.curiosity, 2),
                "energy": round(self.cognition.energy, 2),
            },
            "context": {
                "target_tokens": self.target_tokens,
                "preserve_last": self.context.preserve_last,
            },
        }
