"""
runtime/foveated_rationalia.py — Foveated Rationalia
========================================================
Infinite memory through foveated compression:

  - Fovea (center): verbatim recent turns + active goals.
  - Periphery: XRL seeds summarising older conversation chunks.
  - Deep store: XRLated principia seeds that compress the very long-term
    context (hours, days, sessions) into constitutional red threads.

All context is translated into red threads and woven like the membrane
bridge does in `foveated-memory/server.js`. A trained XRL model fed these
red threads runs in hyperdrive: it behaves like a much larger model because
it receives compressed, structured, principia-governed context instead of
raw text.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from runtime.xrl_context_compressor import XRLContextSeed
from runtime.xrl_principia import XRLPrincipiaSeed


@dataclass
class RationaliaLayer:
    """One tier of the foveated memory pyramid."""

    name: str
    max_tokens: int
    retention: str  # "verbatim", "seed", "principia"
    seeds: list[XRLContextSeed] = field(default_factory=list)


class FoveatedRationalia:
    """
    Manage long-running context as a foveated, tiered memory system.

    Usage:
        fr = FoveatedRationalia()
        fr.ingest_turn("user", "I want a Python sorting example.")
        fr.ingest_turn("assistant", "Use sorted() for a new list.")
        seed = fr.get_composite_seed()

    Phase 0: simple token counting and seed stacking. Later phases will
    use a trained nano model to compress periphery layers.
    """

    def __init__(
        self,
        fovea_tokens: int = 1024,
        periphery_tokens: int = 1536,
        deep_tokens: int = 512,
    ):
        self.fovea_tokens = fovea_tokens
        self.periphery_tokens = periphery_tokens
        self.deep_tokens = deep_tokens

        self.turns: list[dict[str, Any]] = []
        self.periphery: list[XRLContextSeed] = []
        self.deep: XRLPrincipiaSeed | None = None
        self._red_threads: list[str] = []

    def set_principia(self, principia_seed: XRLPrincipiaSeed) -> None:
        """Lock the deep constitutional red thread."""
        self.deep = principia_seed

    def ingest_turn(self, role: str, content: str, tags: list[str] | None = None) -> None:
        """Add a fresh turn to the fovea."""
        self.turns.append(
            {
                "role": role,
                "content": content,
                "tags": tags or [],
                "timestamp": time.time(),
            }
        )
        self._maybe_compress()

    def weave_red_thread(self, user_intent: str) -> str:
        """
        Weave a red thread from principia + periphery + latest intent,
        similar to how the membrane bridge builds the Agent HUD.
        """
        parts: list[str] = []
        if self.deep:
            parts.append(self.deep.to_seed_string())
        for seed in self.periphery[-3:]:
            if seed.digest:
                parts.append(f"[PERIPHERY] {seed.digest}")
        parts.append(f"[FOVEA] {user_intent[:200]}")
        return "\n".join(parts)

    def get_composite_seed(self, user_msg: str = "") -> XRLContextSeed:
        """Return one XRL seed that fuses all tiers for the next inference."""
        anchors = [
            {"role": t["role"], "content": t["content"][:300]} for t in self.turns[-6:]
        ]
        concepts: list[str] = []
        for seed in self.periphery:
            concepts.extend(seed.concepts)
        concepts = list(dict.fromkeys(concepts))[:20]

        digest_parts = [
            f"fovea_turns={len(self.turns)}",
            f"periphery_seeds={len(self.periphery)}",
        ]
        if self.deep:
            digest_parts.append("deep_principia=active")

        return XRLContextSeed(
            degree=3,
            profile="foveated-rationalia",
            anchors=anchors,
            concepts=concepts,
            digest="; ".join(digest_parts),
            metadata={
                "fovea_tokens": self.fovea_tokens,
                "periphery_tokens": self.periphery_tokens,
                "deep_tokens": self.deep_tokens,
                "red_thread": self.weave_red_thread(user_msg),
            },
            kv_hint="retain-recent",
        )

    def _maybe_compress(self) -> None:
        """
        When the fovea exceeds its token budget, compress oldest turns into
        a periphery seed and drop them from verbatim memory.
        """
        chars = sum(len(str(t.get("content", ""))) for t in self.turns)
        if chars > self.fovea_tokens * 4:
            old = self.turns[:-4]
            if not old:
                return
            seed = self._compress_turns(old)
            self.periphery.append(seed)
            self.turns = self.turns[-4:]

    def _compress_turns(self, turns: list[dict[str, Any]]) -> XRLContextSeed:
        """
        Heuristic compression of a turn batch into an XRL seed.
        Phase 0: keep first user + last assistant and a short digest.
        Phase 1+: call a trained nano model to write the seed.
        """
        user_turns = [t for t in turns if t.get("role") == "user"]
        assistant_turns = [t for t in turns if t.get("role") == "assistant"]
        anchors: list[dict[str, Any]] = []
        if user_turns:
            anchors.append({"role": "user", "content": str(user_turns[0]["content"])[:200]})
        if assistant_turns:
            anchors.append(
                {"role": "assistant", "content": str(assistant_turns[-1]["content"])[:300]}
            )

        topics: list[str] = []
        for t in user_turns:
            topics.extend(str(t["content"]).split()[:5])
        concepts = list(dict.fromkeys(topics))[:10]

        return XRLContextSeed(
            degree=3,
            profile="periphery-compressed",
            anchors=anchors,
            concepts=concepts,
            digest=f"Compressed {len(turns)} turns into periphery seed.",
            metadata={
                "compressed_turns": len(turns),
                "compression_profile": "heuristic-phase0",
            },
            kv_hint="retain-recent",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fovea_tokens": self.fovea_tokens,
            "periphery_tokens": self.periphery_tokens,
            "deep_tokens": self.deep_tokens,
            "turn_count": len(self.turns),
            "periphery_seeds": len(self.periphery),
            "deep_principia": self.deep.to_dict() if self.deep else None,
            "red_threads": self._red_threads[-5:],
        }


# Singleton helper
_default_rationalia: FoveatedRationalia | None = None


def get_default_rationalia() -> FoveatedRationalia:
    global _default_rationalia
    if _default_rationalia is None:
        _default_rationalia = FoveatedRationalia()
    return _default_rationalia
