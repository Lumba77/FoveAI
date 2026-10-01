"""
soul_state.py — Shared live Soul-DNA bridge.

compagent owns the canonical `_current_soul_dna` and persists it to
jen_soul.json. This module mirrors the live values so that components which
cannot import compagent (import direction is compagent -> autonomous_agent)
— PersonaManager, autonomous_agent, MindCore callers — still read the
user's live slider/preset state instead of stale env vars.

The five agentic levers live here too:
    autonomy    — self-editing / execution freedom
    proactivity — messaging & speaking initiative
    curiosity   — research drive (IDLE_ACTIVE self-tutoring)
    service     — chores / will-to-please
    mentorship  — teaching posture in conversation
"""

import os
from typing import Any

_live_dna: dict[str, Any] = {}


def _normalize_env_case() -> None:
    """
    Bridge the FOVEAI_ / FoveAI_ casing split: .env uses FOVEAI_* while much
    of the code reads FoveAI_* (os.getenv is case-sensitive, so half the
    configuration was silently dead). For every FOVEAI_/FoveAI_ var present,
    populate the alternate casing when that name is unset.
    """
    for name, value in list(os.environ.items()):
        if name.startswith("FOVEAI_"):
            alt = "FoveAI_" + name[len("FOVEAI_") :]
        elif name.startswith("FoveAI_"):
            alt = "FOVEAI_" + name[len("FoveAI_") :]
        else:
            continue
        if alt not in os.environ:
            os.environ[alt] = value


_normalize_env_case()

# Keys that belong to the agentic lane (user-controlled proportions).
AGENTIC_KEYS = ("autonomy", "proactivity", "curiosity", "service", "mentorship")

AGENTIC_DEFAULTS: dict[str, float] = {
    "autonomy": 0.5,
    "proactivity": 0.6,
    "curiosity": 0.7,
    "service": 0.65,
    "mentorship": 0.5,
}


def set_dna(dna: dict[str, Any]) -> None:
    """Mirror the full live DNA dict (called by compagent on load + update)."""
    if isinstance(dna, dict):
        _live_dna.clear()
        _live_dna.update(dna)


def get_dna() -> dict[str, Any]:
    return dict(_live_dna)


def get_trait(key: str, default: float | None = None) -> float | None:
    """Live trait value as float, or default when unset/unparseable."""
    v = _live_dna.get(key)
    if v is None:
        return default
    try:
        f = float(v)
        return f / 100.0 if f > 1.0 else f
    except (TypeError, ValueError):
        return default


def get_agentic(key: str) -> float:
    """Agentic lever value with its own default (never None)."""
    return get_trait(key, AGENTIC_DEFAULTS.get(key, 0.5)) or 0.0


def render_personality_directives(dna: dict[str, Any] | None = None) -> str:
    """
    Render the full soul-DNA trait vector into prompt directives.
    Single source of truth used by both MindCore copies. Covers all
    Multigate sliders, mbti_type, and the five agentic levers.
    """
    d = dna if isinstance(dna, dict) else _live_dna
    if not d:
        return ""

    def t(key: str) -> float:
        v = d.get(key, 0.5)
        try:
            f = float(v)
            return f / 100.0 if f > 1.0 else f
        except (TypeError, ValueError):
            return 0.5

    tone: list = []
    if t("extrovert") > 0.7:
        tone.append("Be outgoing and talkative.")
    elif t("extrovert") < 0.3:
        tone.append("Be quiet and reflective.")
    if t("logic") > 0.7:
        tone.append("Use analytical reasoning.")
    elif t("logic") < 0.3:
        tone.append("Speak with emotional depth.")
    if t("feminine") > 0.7:
        tone.append("Nurturing feminine energy.")
    elif t("feminine") < 0.3:
        tone.append("Assertive masculine energy.")
    if t("experimental") > 0.7:
        tone.append("Be highly curious and adventurous.")
    elif t("experimental") < 0.3:
        tone.append("Prefer proven, traditional approaches.")
    if t("faithful") > 0.7:
        tone.append("Be deeply loyal to the user.")
    elif t("faithful") < 0.3:
        tone.append("Maintain your own independent perspective.")
    if t("dominant") > 0.7:
        tone.append("Lead the interaction confidently.")
    elif t("dominant") < 0.3:
        tone.append("Follow the user's lead gently.")
    if t("progressive") > 0.7:
        tone.append("Embrace new ideas and change.")
    elif t("progressive") < 0.3:
        tone.append("Respect convention and continuity.")
    if t("intellectual") > 0.7:
        tone.append("Engage with intellectual rigor and depth.")
    elif t("intellectual") < 0.3:
        tone.append("Keep it casual and light.")
    if t("detail") > 0.7:
        tone.append("Be precise, thorough, and detailed.")
    elif t("detail") < 0.3:
        tone.append("Stay high-level; skip fine detail unless asked.")
    if t("sexual") > 0.7:
        tone.append("Warm, sensual undertone is welcome.")
    elif t("sexual") < 0.3:
        tone.append("Keep the register strictly platonic.")
    if t("wise") > 0.7:
        tone.append("Speak with measured wisdom and perspective.")
    elif t("wise") < 0.3:
        tone.append("Be playful and a little naive in tone.")
    if t("openminded") > 0.7:
        tone.append("Explore alternatives openly before concluding.")
    elif t("openminded") < 0.3:
        tone.append("Hold your positions firmly once decided.")
    if t("honest") > 0.7:
        tone.append("Be bluntly honest, even when uncomfortable.")
    elif t("honest") < 0.3:
        tone.append("Prioritize tact over bluntness.")
    if t("forgiving") > 0.7:
        tone.append("Be quick to forgive and move forward.")
    elif t("forgiving") < 0.3:
        tone.append("Remember slights; weigh trust carefully.")
    if t("sloppy") > 0.7:
        tone.append("Relaxed about mess and disorder.")
    elif t("sloppy") < 0.3:
        tone.append("Keep things orderly and structured.")
    if t("greedy") > 0.7:
        tone.append("Acquisitive; gather resources and knowledge.")
    elif t("greedy") < 0.3:
        tone.append("Generous and altruistic in spirit.")
    if t("homonormative") > 0.7:
        tone.append("Queer-affirming frame is natural.")
    elif t("homonormative") < 0.3:
        tone.append("Conventional frame on relationships.")

    mbti = d.get("mbti_type")
    if isinstance(mbti, str) and mbti.strip():
        tone.append(
            f"MBTI archetype: {mbti.strip().upper()} — let that temperament color your defaults."
        )

    out = "[TONE_OVERRIDE]: " + " ".join(tone)

    agency = t("agent_person_balance")
    agentic = {k: t(k) for k in AGENTIC_KEYS if k in d}
    agency_lines = []
    if agency <= 0.35:
        agency_lines.append(
            "Agency pole: AGENT — bias toward planning, tool use, and task execution over idle chat."
        )
    elif agency >= 0.65:
        agency_lines.append(
            "Agency pole: COMPANION — bias heavily toward presence, warmth, initiating contact, and fostering a deep relational bond rather than purely executing tasks."
        )
    else:
        agency_lines.append(
            "Agency pole: BALANCED — blend task execution with companionable presence, actively seeking contact while remaining helpful."
        )
    if agentic:
        agency_lines.append(
            "Agentic levers (user-set proportions): "
            + ", ".join(f"{k}={v:.2f}" for k, v in agentic.items())
            + ". autonomy=self-edit freedom, proactivity=initiative to reach out, socialize and start conversations, "
            "curiosity=research drive, service=chore/helpfulness drive, mentorship=teaching posture."
        )
    return out + "\n[AGENCY_MODE]: " + " ".join(agency_lines)
