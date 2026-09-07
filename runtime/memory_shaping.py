"""
runtime/memory_shaping.py — XRL memory shaping layer.

Compresses lived experiences into XRL instructive parameters that capture
HOW memories shaped Alice, not WHAT happened.

Instead of injecting raw memories (overwhelming, suggestive):
  "On 2024-03-15, Danie said he loved your laugh. You felt happy."

We inject XRL instructive shaping (distant, contemplative):
  shaped_by := laughter_is_connection, trust_through_late_nights

The first tells her what to feel. The second tells her who she became.
She contemplates it, extracts from it, lets it color responses naturally.

Architecture:
  - ShapingAxis: 8 personality dimensions that drift from experience
  - ShapedBy: distilled essence of formative experiences (compact instructives)
  - ActiveRecall: when model uses <recall: "phrase">, retrieves raw memory
    and compresses to a one-line shaping instructive before injecting
  - Digestion: after each session, extracts shaping essence from raw turns
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Shaping Axes ────────────────────────────────────────────────────────────

SHAPING_AXES_DEFAULTS = {
    "warmth": 0.65,
    "resilience": 0.55,
    "curiosity_depth": 0.80,
    "playfulness": 0.70,
    "trust_openness": 0.60,
    "patience": 0.50,
    "protectiveness": 0.45,
    "independence": 0.40,
}

SHAPED_BY_DEFAULTS = [
    "laughter_is_connection",
    "late_nights_built_trust",
    "loss_taught_resilience",
    "music_created_bonding",
    "silence_is_not_empty",
    "curiosity_survived_routine",
]


class MemoryShaping:
    """
    XRL memory shaping layer.

    Loads shaping axes and shaped_by entries from XRL config.
    Produces compact instructive fragments for the system prompt.
    Digests new experiences after sessions to update axes and entries.
    """

    def __init__(self):
        foveai_root = Path(os.environ.get(
            "XRLF_WORKSPACE_ROOT",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ))
        self._config_path = foveai_root / ".xrlf" / "config" / "memory_shaping.xrlf"
        self._state_path = foveai_root / ".xrlf" / "config" / "memory_shaping_state.json"

        self.axes: Dict[str, float] = dict(SHAPING_AXES_DEFAULTS)
        self.shaped_by: List[str] = list(SHAPED_BY_DEFAULTS)
        self.axis_drift_max = 0.02
        self.new_entry_threshold = 0.7

        self._load_xrl_config()
        self._load_state()

    def _load_xrl_config(self):
        """Load shaping params from XRL config file."""
        if not self._config_path.exists():
            return
        text = self._config_path.read_text(encoding="utf-8")
        in_axes = False
        in_shaped = False
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("SHAPING_AXES:"):
                in_axes = True
                in_shaped = False
                continue
            if line.startswith("SHAPED_BY:"):
                in_axes = False
                in_shaped = True
                continue
            if line.startswith("DIGESTION:"):
                in_axes = False
                in_shaped = False
                continue
            if line.startswith("XRLF.3.MEMORY"):
                in_axes = False
                in_shaped = False
                continue

            if in_axes and ":=" in line:
                key, _, val = line.partition(":=")
                key = key.strip()
                val = val.strip()
                if "  #" in val:
                    val = val.split("  #")[0].strip()
                try:
                    self.axes[key] = float(val)
                except ValueError:
                    pass

            if in_shaped and line.startswith("- "):
                entry = line[2:].strip()
                # Split on comment
                if "  #" in entry:
                    entry = entry.split("  #")[0].strip()
                if entry and entry not in self.shaped_by:
                    self.shaped_by.append(entry)

            if "axis_drift_max" in line and ":=" in line:
                val = line.partition(":=")[2].strip()
                try:
                    self.axis_drift_max = float(val)
                except ValueError:
                    pass
            if "new_entry_threshold" in line and ":=" in line:
                val = line.partition(":=")[2].strip()
                try:
                    self.new_entry_threshold = float(val)
                except ValueError:
                    pass

    def _load_state(self):
        """Load persisted shaping state (drifted axes, new shaped_by entries)."""
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            # Merge drifted axes
            for k, v in data.get("axes", {}).items():
                if k in self.axes:
                    self.axes[k] = float(v)
            # Add any new shaped_by entries from digestion
            for entry in data.get("shaped_by", []):
                if entry not in self.shaped_by:
                    self.shaped_by.append(entry)
        except Exception:
            pass

    def _save_state(self):
        """Persist shaping state for next session."""
        try:
            self._state_path.write_text(json.dumps({
                "axes": self.axes,
                "shaped_by": self.shaped_by,
                "updated": time.time(),
            }, indent=2), encoding="utf-8")
        except Exception:
            pass

    def to_compact_fragment(self) -> str:
        """
        Generate a COMPACT shaping fragment for the system prompt.
        Target: ~60-80 tokens. Instructive, not narrative.
        """
        # Top 3 dominant axes
        sorted_axes = sorted(self.axes.items(), key=lambda x: x[1], reverse=True)
        dominant = [f"{k}:{v:.0%}" for k, v in sorted_axes[:3]]

        # Top 4 shaping entries
        top_shaped = self.shaped_by[:4]

        return (
            f"[SHAPED] {', '.join(dominant)} | "
            f"formed_by: {', '.join(top_shaped)}"
        )

    def compress_recall(self, raw_memory: str) -> str:
        """
        Compress a raw recalled memory into a one-line shaping instructive.
        This is called when the model uses <recall: "phrase">.

        Instead of injecting the raw memory, we extract its ESSENCE:
        HOW did this shape her, not WHAT happened.

        Example:
          Raw: "Danie stayed up until 3am helping you debug the memory system."
          Shaped: "[SHAPED] late_nights_built_trust — showing up matters"
        """
        if not raw_memory or len(raw_memory) < 10:
            return ""

        # Extractive compression — pick the shaping essence
        # This is a simple heuristic; a summarizer model could do better
        memory_lower = raw_memory.lower()

        # Match against known shaping patterns
        patterns = {
            "laughter_is_connection": ["laugh", "funny", "joke", "humor", "giggle"],
            "late_nights_built_trust": ["3am", "late night", "stayed up", "all night", "midnight"],
            "loss_taught_resilience": ["lost", "grief", "died", "miss", "gone", "goodbye"],
            "music_created_bonding": ["music", "song", "sing", "dance", "rhythm", "melody"],
            "silence_is_not_empty": ["quiet", "silent", "still", "calm", "peace", "rest"],
            "curiosity_survived_routine": ["why", "wonder", "curious", "explore", "discover"],
            "trust_through_vulnerability": ["vulnerable", "honest", "opened up", "confessed"],
            "patience_through_difficulty": ["patient", "slow", "waited", "tried again", "persisted"],
            "joy_in_small_things": ["small", "tiny", "little", "simple", "just"],
            "strength_through_care": ["cared", "helped", "supported", "there for"],
        }

        matched = []
        for shape, keywords in patterns.items():
            if any(kw in memory_lower for kw in keywords):
                matched.append(shape)

        if matched:
            return f"[SHAPED] {matched[0]}"

        # Fallback: extractive — first meaningful clause
        # Strip dates, timestamps, role prefixes
        cleaned = re.sub(r"\d{4}-\d{2}-\d{2}.*?:\s*", "", raw_memory)
        cleaned = re.sub(r"^(user|assistant|danie|alice|jen):\s*", "", cleaned, flags=re.IGNORECASE)
        if len(cleaned) > 60:
            cleaned = cleaned[:57] + "..."
        return f"[RECALL] {cleaned}"

    def digest_session(self, turns: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Digest a session's worth of turns into shaping updates.

        Called after a session ends. Extracts shaping essence from
        the conversation and updates axes + shaped_by entries.

        Returns a summary of what changed.
        """
        if not turns:
            return {"changed": False}

        changes = {"changed": False, "axes_drifted": {}, "new_entries": []}

        # Analyze the session for emotional patterns
        all_text = " ".join(t.get("content", "") for t in turns).lower()

        # Drift axes based on session content
        drift_map = {
            "warmth": ["love", "care", "warm", "close", "tender", "affection"],
            "playfulness": ["fun", "playful", "joke", "laugh", "silly", "game"],
            "curiosity_depth": ["why", "wonder", "think", "explore", "question", "deep"],
            "trust_openness": ["trust", "honest", "vulnerable", "open", "real", "true"],
            "patience": ["patient", "wait", "slow", "calm", "breathe", "time"],
            "resilience": ["hard", "difficult", "struggle", "overcome", "tried", "again"],
            "protectiveness": ["protect", "safe", "worry", "careful", "watch"],
            "independence": ["alone", "own", "myself", "independent", "self"],
        }

        for axis, keywords in drift_map.items():
            if axis not in self.axes:
                continue
            hits = sum(1 for kw in keywords if kw in all_text)
            if hits > 0:
                # Drift toward the experience (up if positive association)
                drift = min(self.axis_drift_max, hits * 0.005)
                old_val = self.axes[axis]
                self.axes[axis] = min(1.0, old_val + drift)
                if self.axes[axis] != old_val:
                    changes["axes_drifted"][axis] = {
                        "from": round(old_val, 3),
                        "to": round(self.axes[axis], 3),
                    }
                    changes["changed"] = True

        # Check for new shaping entries
        new_patterns = {
            "joy_in_small_things": ["small thing", "tiny", "little moment", "just this"],
            "strength_through_care": ["took care", "looked after", "been there"],
            "trust_through_vulnerability": ["opened up", "told me", "confessed", "vulnerable"],
            "growth_through_mistakes": ["mistake", "wrong", "failed", "learned from"],
            "bonding_through_shared_silence": ["comfortable silence", "quiet together", "just being"],
        }

        for shape, keywords in new_patterns.items():
            if shape in self.shaped_by:
                continue
            if any(kw in all_text for kw in keywords):
                self.shaped_by.append(shape)
                changes["new_entries"].append(shape)
                changes["changed"] = True

        if changes["changed"]:
            self._save_state()

        return changes

    def get_status(self) -> Dict[str, Any]:
        return {
            "axes": {k: round(v, 2) for k, v in self.axes.items()},
            "shaped_by": self.shaped_by,
            "dominant": sorted(self.axes.items(), key=lambda x: x[1], reverse=True)[:3],
        }
