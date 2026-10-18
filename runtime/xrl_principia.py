"""
runtime/xrl_principia.py — XRLated Principia Compiler
========================================================
Convert the FoveAI invariants and derived state into compact XRL seeds
that trained nano models can consume natively. Feeding a nano model an
XRLated principia seed puts it in "hyperdrive": it inherits the system's
constitutional rules, current priorities, and compressed context without
needing to parse long natural-language prompts.

This is the bridge between the human-readable principia files
(`Plans/Kimi-principia-plan.MD`, `repo-principia.md`) and the structured
XRL seed language used by `XRLContextCompressor` and the nano-native
trainers.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.xrl_context_compressor import XRLContextSeed

DEFAULT_PRINCIPLES = {
    "P0": "One base, many faces: model record is (base, adapter); adapters/LoRA first-class.",
    "P1": "Contracts are granted, not claimed: identity proven by key, access by grant.",
    "P2": "Conference room with host-gated ingress; no open collegium.",
    "P3": "Voice is Quest-native; server has no mic dependency.",
    "P4": "No duplicate build runs; AliceVR3.apk intermediate, AliceVR72.apk final.",
    "P5": "Single sources of truth: grants, identity keys, FUI palette.",
    "P6": "No Windows ghosts; resolve under /home/lumba/Models/...",
    "P7": "Evidence before promotion: TTFT, tokens/s, quality, RAM, cost, stability.",
    "P8": "No hardcoded UX values; derive from FUI palette.",
    "P9": "Security floor: ~/.sudo_pass secret; restart after upstream deps alive.",
    "P10": "Name is final: FoveAI Labs replaces Birth Chamber/Nursery/AI Lab.",
    "P11": "Configured model must resolve to a file; empty-dir default is a bug.",
}


@dataclass
class XRLPrincipiaSeed:
    """
    A compact, machine-readable principia seed.

    Fields mirror XRLContextSeed so the compressor can merge them directly.
    """

    version: int = 1
    degree: int = 3
    profile: str = "xrlated-principia"
    principles: dict[str, str] = field(default_factory=dict)
    derived_state: list[str] = field(default_factory=list)
    active_goals: list[str] = field(default_factory=list)
    known_paths: dict[str, str] = field(default_factory=dict)
    compression_profile: str = "xrlated-principia-v1"
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "degree": self.degree,
            "profile": self.profile,
            "principles": self.principles,
            "derived_state": self.derived_state,
            "active_goals": self.active_goals,
            "known_paths": self.known_paths,
            "compression_profile": self.compression_profile,
            "generated_at": self.generated_at or time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def to_context_seed(self) -> XRLContextSeed:
        """Cast this principia seed into a generic XRLContextSeed."""
        return XRLContextSeed(
            degree=self.degree,
            version=self.version,
            profile=self.profile,
            anchors=[
                {"role": "system", "content": f"P{k}: {v}"}
                for k, v in self.principles.items()
            ],
            concepts=self.active_goals + self.derived_state[:5],
            digest="XRLated principia seed: constitutional invariants + current derived state.",
            metadata={
                "compression_profile": self.compression_profile,
                "known_paths": self.known_paths,
                "generated_at": self.generated_at or time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            kv_hint="retain-all",  # principia is tiny but essential
        )

    def to_micro_seed_string(self) -> str:
        """
        Render as an ultra-terse seed: principle IDs + short goal slugs only.
        Designed for 33M-135M nano models where every token matters.
        """
        keys = " ".join(sorted(self.principles.keys()))
        # Keep goal slugs ultra-short (first 24 chars) to stay within budget.
        slugs = [g.split("::", 1)[-1].strip()[:24] for g in self.active_goals[:3]]
        goals = " | ".join(slugs) if slugs else ""
        return (
            f"<XRL-SEED d={self.degree}>{keys}"
            + (f"<G>{goals}</G>" if goals else "")
            + "<C/>"
        )

    def to_seed_string(self) -> str:
        """Render as a terse, token-efficient XRL seed string."""
        lines = [
            "<XRL-SEED degree={} profile={}>".format(self.degree, self.profile),
            "<PRINCIPA>",
        ]
        for key, value in self.principles.items():
            lines.append(f"{key}: {value}")
        lines.append("</PRINCIPA>")
        if self.active_goals:
            lines.append("<GOALS>")
            lines.extend(f"- {g}" for g in self.active_goals)
            lines.append("</GOALS>")
        if self.derived_state:
            lines.append("<STATE>")
            lines.extend(f"- {s[:120]}" for s in self.derived_state[:8])
            lines.append("</STATE>")
        lines.append("<CONTINUE/>")
        lines.append("</XRL-SEED>")
        return "\n".join(lines)


class XRLPrincipiaCompiler:
    """
    Compile principia markdown files into XRLPrincipiaSeed objects.

    Phase 0: reads the principia files and emits a seed from the static
    kernel invariants plus a few hand-picked derived-state lines.
    Phase 1+: parse the markdown tables and bullet lists automatically.
    """

    def __init__(self, plan_path: str | None = None, repo_path: str | None = None):
        self.plan_path = Path(
            plan_path or "/home/lumba/FoveAI/Plans/Kimi-principia-plan.MD"
        )
        self.repo_path = Path(
            repo_path or "/home/lumba/FoveAI/repo-principia.md"
        )

    def compile(self) -> XRLPrincipiaSeed:
        """Build the current XRLated principia seed."""
        principles = dict(DEFAULT_PRINCIPLES)
        derived_state: list[str] = []
        active_goals: list[str] = []
        known_paths: dict[str, str] = {}

        if self.plan_path.exists():
            text = self.plan_path.read_text(encoding="utf-8")
            # Extract derived-state bracket lines: `[ ... ] :: ...`
            derived_state = self._extract_bracket_lines(text)
            # Extract goals from hypermind/nano-xrl vision statements
            active_goals = self._extract_goals(text)

        if self.repo_path.exists():
            repo_text = self.repo_path.read_text(encoding="utf-8")
            known_paths = self._extract_paths(repo_text)

        return XRLPrincipiaSeed(
            degree=3,
            principles=principles,
            derived_state=derived_state,
            active_goals=active_goals,
            known_paths=known_paths,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    @staticmethod
    def _extract_bracket_lines(text: str) -> list[str]:
        """Pull out lines that look like `[ P0, P7 ] :: something`."""
        pattern = re.compile(r"^\[\s*[^\]]+\s*\]\s*::\s*(.+)$", re.MULTILINE)
        matches = pattern.findall(text)
        return [m.strip() for m in matches if m.strip()]

    @staticmethod
    def _extract_goals(text: str) -> list[str]:
        """Heuristic goal extraction from vision/research lines."""
        goals: list[str] = []
        for line in text.splitlines():
            lowered = line.lower()
            if any(
                tag in lowered
                for tag in [
                    "vision",
                    "target architecture",
                    "aspirational win",
                    "reference benchmark",
                    "nano-native",
                    "hypermind",
                    "xrl 3.0",
                    "hive-mind",
                ]
            ):
                goals.append(line.strip().lstrip("- ").strip()[:200])
        return goals[:12]

    @staticmethod
    def _extract_paths(text: str) -> dict[str, str]:
        """Pull known file/path references out of repo-principia."""
        paths: dict[str, str] = {}
        # Lines like: "Backend/Cognition/compagent.py (8405)"
        for match in re.finditer(r"^\s*([\w/_.-]+)\s*\((\d{4,5})\)", text, re.MULTILINE):
            path, port = match.groups()
            paths[path] = port
        return paths

    def compile_to_file(self, output_path: str) -> str:
        """Compile and write the seed JSON to disk."""
        seed = self.compile()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(seed.to_dict(), indent=2, ensure_ascii=False))
        return str(out)


# Convenience singleton
def compile_xrl_principia() -> XRLPrincipiaSeed:
    return XRLPrincipiaCompiler().compile()
