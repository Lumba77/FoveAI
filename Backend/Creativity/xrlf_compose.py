"""
Backend/Creativity/xrlf_compose.py — XRLF Steering Composer
===========================================================
Mimics Mixture-of-Quantization (MoQ) principles for conditional computation:

  MoQ (weights):  non-uniform bit budget — spend precision where tensors
                  are sensitive, squash the elastic/redundant pathways.
  Here (tokens):  non-uniform token budget — every instruction token is
                  expensive for a tiny quantized generator (e.g. a
                  Q2_K GGUF image model fusing encoder tokens directly
                  into a S3-DiT sequence), so we *score* each steering
                  directive for density and keep only the densest ones.

The composer reads the repo's steering corpus (resonance config,
cognitive geometry, refactor directive), scores each directive with an
elasticity scorer, and emits a compact instruction envelope:
    [xrlf: d1; d2; d3] <user prompt>

Everything is typed; no implicit Any survives.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── corpus model ────────────────────────────────────────────────────────

ELASTIC_RE = re.compile(
    r"^\s*(?P<key>[a-z_]+)\s*:=\s*(?P<val>.+)$", re.MULTILINE
)
RULE_RE = re.compile(r"<(?P<tag>objective|rule)>\s*(?P<txt>.+?)\s*</", re.S)


@dataclass(frozen=True)
class Directive:
    """One steering line from the corpus."""
    key: str
    text: str
    weight: float  # 0..1 elasticity density — higher = keep


@dataclass
class Composition:
    """Result of composing corpus guidance around a prompt."""
    envelope: str
    prompt: str
    kept: list[Directive] = field(default_factory=list)
    dropped: int = 0

    @property
    def full(self) -> str:
        return f"{self.envelope} {self.prompt}".strip()


# ── elasticity scorer ───────────────────────────────────────────────────

# tokens that carry structural/logical weight — always dense
_DENSE_TOKENS = ("strength", "policy", "temperature", "steps", "seed", "gate")
# fluff markers — predictable grammatical transitions
_SOFT_TOKENS = ("please", "maybe", "kind of", "sort of", "could you")


def elasticity(text: str) -> float:
    """Density of a candidate directive: 0 (fluff) .. 1 (structural)."""
    low = text.lower()
    w = 0.4  # base
    w += 0.15 * sum(1 for t in _DENSE_TOKENS if t in low)
    w -= 0.2 * sum(1 for t in _SOFT_TOKENS if t in low)
    # compact directives beat verbose ones (token discipline)
    w += 0.1 if len(text) <= 60 else -0.1 * min(3, (len(text) - 60) // 40)
    return max(0.05, min(1.0, w))


# ── corpus readers ──────────────────────────────────────────────────────

def _repo_root() -> Path:
    # .../Backend/Creativity/xrlf_compose.py → repo root is ../../..
    here = Path(__file__).resolve()
    return here.parents[2]


def read_corpus() -> list[Directive]:
    """Collect steering lines from the repo's XRLF corpus files."""
    root = os.getenv("FOVEAI_STEERING_ROOT", str(Path.cwd()))
    root_p = Path(root)
    candidates = [
        root_p / ".xrlf" / "config" / "resonance.config.xrlf",
        root_p / "XRLF_REFACTOR_STEERING.xrlf.xml",
    ]
    out: list[Directive] = []
    for fp in candidates:
        try:
            raw = Path(fp).read_text(encoding="utf-8")[:4096]
        except OSError:
            continue
        for m in ELASTIC_RE.finditer(raw):
            if m.group("key") in ("steering_strength", "temperature", "compute_policy"):
                out.append(Directive(m.group("key"), m.group("val").strip(), elasticity(m.group("val"))))
        for m in RULE_RE.finditer(raw):
            txt = re.sub(r"\s+", " ", m.group("txt")).strip()
            out.append(Directive(m.group("tag"), txt[:70], elasticity(txt)))
    return out


# ── compose ─────────────────────────────────────────────────────────────

def compose(prompt: str, keep: int = 5) -> Composition:
    """Fold the steering corpus around a user prompt."""
    dirs = read_corpus()
    # always-on quality anchors: cheap, dense, dense-semantic for a tiny model
    fixed = [
        Directive("compose", "composition follows the user's subject precisely", 0.9),
        Directive("detail", "coherent local details, no artifact duplication", 0.9),
        Directive("edge", "clean edges, natural light, high perceived sharpness", 0.9),
    ]
    pool = sorted(dirs, key=lambda d: d.weight, reverse=True)[: max(0, keep - len(fixed))]
    kept = fixed + pool
    env = "[xrlf: " + "; ".join(f"{d.key}:{d.text}" for d in kept) + "]"
    composition = Composition(
        envelope=env,
        prompt=prompt.strip(),
        kept=kept,
        dropped=max(0, len(dirs) - (keep - len(fixed))),
    )
    return composition


if __name__ == "__main__":  # pragma: no cover — demo
    import sys

    user = " ".join(sys.argv[1:]) or "a tiny detailed toenail, painterly like an oil portrait"
    print(compose(user).full)