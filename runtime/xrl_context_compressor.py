"""
runtime/xrl_context_compressor.py — XRL Context Compressor (XCC)
==================================================================
Convert assembled model context into a compact XRL seed and decode it back
into a minimal but sufficient prompt for the next turn.

Vision: "Model context conversion to XRL raw data, automated function
makes models faster than draft models."

Phase 0 (current): placeholder / pass-through. The compressor exists in the
runtime path but returns the input unchanged, proving wiring without
breaking inference.

Phases 1–3 will add heuristic, structured, and model-assisted compression.
"""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class XRLContextSeed:
    """
    Lossy semantic prior that stands in for full conversation history.

    Fields:
        degree: XRL compression level (0-9). Higher = more compressed.
        version: seed format version for forward compatibility.
        profile: active task profile name and config snapshot.
        anchors: verbatim user/assistant utterances that must survive.
        concepts: extracted graph concepts / activated clusters.
        digest: short narrative or structured summary of older turns.
        metadata: compression profile, timestamps, ratios, etc.
        kv_hint: optional KV-cache retention / eviction instruction.
    """

    degree: int = 0
    version: int = 1
    profile: str = ""
    anchors: list[dict[str, Any]] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    digest: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    kv_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "degree": self.degree,
            "version": self.version,
            "profile": self.profile,
            "anchors": self.anchors,
            "concepts": self.concepts,
            "digest": self.digest,
            "metadata": self.metadata,
            "kv_hint": self.kv_hint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "XRLContextSeed":
        return cls(
            degree=max(0, min(9, int(data.get("degree", 0)))),
            version=int(data.get("version", 1)),
            profile=data.get("profile", ""),
            anchors=list(data.get("anchors", [])),
            concepts=list(data.get("concepts", [])),
            digest=data.get("digest", ""),
            metadata=dict(data.get("metadata", {})),
            kv_hint=data.get("kv_hint", ""),
        )


class XRLContextCompressor:
    """
    Encode assembled chat context into an XRL seed; decode the seed back into
    a minimal prompt for the next turn.

    Phase 0: pass-through. encode()/decode()/fit_context() return the input
    unchanged but record seed metadata so the runtime can observe the
    compressor in /health and logs.
    """

    def __init__(
        self,
        degree: int = 3,
        compression_profile: str = "",
        target_tokens: int = 4000,
    ):
        self.degree = max(0, min(9, degree))
        self.compression_profile = compression_profile or "xcc-phase0-pass-through"
        self.target_tokens = target_tokens
        self._last_seed: XRLContextSeed | None = None
        self._last_ratio: float = 1.0

    # ── Public API ────────────────────────────────────────────────────────────

    def fit_context(
        self,
        messages: list[dict[str, Any]],
        user_msg: str,
        profile: str = "",
        concepts: list[str] | None = None,
        rationalia_seed: "XRLContextSeed | None" = None,
    ) -> list[dict[str, Any]]:
        """
        Fit `messages` to the target token budget by producing an XRL seed
        and decoding it into a shorter message list.

        Optionally accepts a `rationalia_seed` from `FoveatedRationalia` to
        inject XRLated principia / infinite-memory context as the first
        system message.

        Phase 0: returns `messages` unchanged, but builds and stores a seed
        from metadata for observability.
        """
        concepts = concepts or []

        # Build a seed from the current context (metadata only in phase 0).
        self._last_seed = self._build_seed(messages, user_msg, profile, concepts)

        # If a foveated rationalia seed is provided, prepend it as a compact
        # system context layer. This is the "hyperdrive" path for nano models.
        if rationalia_seed is not None:
            messages = self._inject_rationalia(messages, rationalia_seed)

        # Phase 0: pass-through. Later phases will decode the seed into a
        # compressed message list.
        compressed = self._decode_seed(self._last_seed, messages)

        # Record compression ratio (1.0 in phase 0).
        raw_chars = self._estimate_chars(messages)
        compressed_chars = self._estimate_chars(compressed)
        self._last_ratio = raw_chars / max(1, compressed_chars)

        if self._last_ratio > 1.01:
            print(
                f"  [XCC] compressed context: {raw_chars} -> {compressed_chars} "
                f"chars (ratio {self._last_ratio:.2f}x, degree {self.degree})"
            )
        else:
            print(
                f"  [XCC] context seed built (degree {self.degree}, "
                f"profile={profile!r}, concepts={concepts})"
            )

        return compressed

    def get_last_seed(self) -> XRLContextSeed | None:
        return self._last_seed

    def get_last_ratio(self) -> float:
        return self._last_ratio

    # ── Phase 0 internals ─────────────────────────────────────────────────────

    def _build_seed(
        self,
        messages: list[dict[str, Any]],
        user_msg: str,
        profile: str,
        concepts: list[str],
    ) -> XRLContextSeed:
        """Build a seed from the current assembled context."""
        # Keep the most recent user message as a verbatim anchor.
        anchors = []
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                anchors.append({"role": "user", "content": str(m["content"])[:200]})
                break

        return XRLContextSeed(
            degree=self.degree,
            profile=profile,
            anchors=anchors,
            concepts=list(concepts),
            digest=f"Phase-0 pass-through seed for: {user_msg[:80]!r}",
            metadata={
                "compression_profile": self.compression_profile,
                "target_tokens": self.target_tokens,
                "raw_turns": len(messages),
                "raw_chars": self._estimate_chars(messages),
            },
            kv_hint="retain-recent" if self.degree <= 3 else "retain-all",
        )

    def _decode_seed(
        self,
        seed: XRLContextSeed,
        original_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Decode a seed back into a message list.

        Phase 0: returns the original messages unchanged. Later phases will
        reconstruct a shorter prompt from the seed + the latest user message.
        """
        return list(original_messages)

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _inject_rationalia(
        messages: list[dict[str, Any]], rationalia_seed: "XRLContextSeed"
    ) -> list[dict[str, Any]]:
        """
        Prepend a compact XRLated principia/rationalia seed as a system note.
        """
        seed_text = rationalia_seed.to_dict()
        # Prefer the terse seed-string if available; otherwise JSON.
        seed_text = json.dumps(seed_text, ensure_ascii=False)
        rationalia_msg = {
            "role": "system",
            "content": f"[XRLATED-PRINCIPIA / RED-THREAD]\n{seed_text}",
            "name": "foveated_rationalia",
        }
        out = [rationalia_msg] + [dict(m) for m in messages]
        return out

    @staticmethod
    def _estimate_chars(messages: list[dict[str, Any]]) -> int:
        """Rough character budget estimate for a message list."""
        total = 0
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += len(str(part["text"]))
        return total

    @staticmethod
    def token_estimate(chars: int, chars_per_token: int = 4) -> int:
        """Map character count to approximate token count."""
        return (chars + chars_per_token - 1) // max(1, chars_per_token)

    @staticmethod
    def family_step_tokens(tokens: int) -> int:
        """
        Round DOWN to the canonical context family steps.
        Mirrors foveated-memory/core/context-healer.js contract.
        """
        steps = [4000, 8000, 16000, 32000, 64000]
        chosen = steps[0]
        for step in steps:
            if tokens >= step:
                chosen = step
            else:
                break
        return chosen


# Convenience singleton helper
_default_compressor: XRLContextCompressor | None = None


def get_default_compressor() -> XRLContextCompressor:
    global _default_compressor
    if _default_compressor is None:
        _default_compressor = XRLContextCompressor()
    return _default_compressor
