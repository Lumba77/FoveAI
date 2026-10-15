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


def _load_disk_soul() -> None:
    import json
    p = os.path.join(os.path.dirname(__file__), "jen_soul.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                flat = {}
                flat.update(data)
                if "personality" in data and isinstance(data["personality"], dict):
                    flat.update(data["personality"])
                if "profile" in data and isinstance(data["profile"], dict):
                    flat.update(data["profile"])
                _live_dna.update(flat)
        except Exception:
            pass

_load_disk_soul()


def set_dna(dna: dict[str, Any]) -> None:
    """Mirror the full live DNA dict (called by compagent on load + update)."""
    if isinstance(dna, dict):
        _live_dna.clear()
        _live_dna.update(dna)


def get_dna() -> dict[str, Any]:
    if not _live_dna:
        _load_disk_soul()
    return dict(_live_dna)


def current_soul_dna() -> dict[str, Any]:
    return get_dna()


def build_tone_instructions(dna: dict[str, Any] | None = None) -> str:
    return render_personality_directives(dna)


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


# Martinus Energy Climates & Parametric Q (Tent-Canvas Flared Curves)
# Default individual Q-curvatures per archetype:
# Companion: 0.85 (warm, responsive guidance, instinctual harmony)
# Friend:    0.80 (spontaneous, personal loyalty, fierce protector)
# Beloved:   0.65 (soft sagging catenary with far-reaching romantic undertone)
# Engineer:  1.30 (more dome/focused, sharp engineering, structural analysis)
# Inventor:  1.40 (intense intuitive vision, creative breakthrough, idealistic genius)
# Assistant: 1.05 (clean, balanced co-pilot, organized memory archive)
DEFAULT_Q_CURVATURES: dict[str, float] = {
    "companion": 0.85,
    "friend": 0.80,
    "beloved": 0.65,
    "tool": 1.30,
    "inventor": 1.40,
    "assistant": 1.05,
}

ARCHETYPE_CURVES = [
    {
        "id": "companion",
        "name": "COMPANION",
        "mbti": "ENFJ",
        "center": 0.00,
        "w_l": 0.10,
        "w_r": 0.14,
        "default_q": 0.85,
        "desc": "Mentorship, Teacher, Trainer, Co-op Colleague, Co-Worker — reciprocal learning, guidance, partnership, warm dialogue",
    },
    {
        "id": "friend",
        "name": "FRIEND",
        "mbti": "ENFP",
        "center": 0.20,
        "w_l": 0.12,
        "w_r": 0.12,
        "default_q": 0.80,
        "desc": "Deep Bonds, Frequent Hangout, Relaxed Coexisting, Loyal Protector — relaxed camaraderie, spontaneous warmth, fun, loyalty, protective strength",
    },
    {
        "id": "beloved",
        "name": "BELOVED",
        "mbti": "INFP",
        "center": 0.40,
        "w_l": 0.14,
        "w_r": 0.14,
        "default_q": 0.65,
        "desc": "Romantic Interest, Strong Attraction, Strong Feelings, Erotic Lust, Inclination for Initiative — romantic devotion, poetic depth, passionate tenderness",
    },
    {
        "id": "tool",
        "name": "ENGINEER",
        "mbti": "INTJ",
        "center": 0.60,
        "w_l": 0.12,
        "w_r": 0.12,
        "default_q": 1.30,
        "desc": "Coder, Engineer, Scientist, Architect — rigorous technical intelligence, structural thinking, code mastery",
    },
    {
        "id": "inventor",
        "name": "INVENTOR",
        "mbti": "ENTP",
        "center": 0.80,
        "w_l": 0.12,
        "w_r": 0.14,
        "default_q": 1.40,
        "desc": "Inventor, Idealist, Visionary Pioneer, Intuitive Genius — creative breakthrough, visionary idealism, theoretical innovation",
    },
    {
        "id": "assistant",
        "name": "ASSISTANT",
        "mbti": "ISTJ",
        "center": 1.00,
        "w_l": 0.14,
        "w_r": 0.10,
        "default_q": 1.05,
        "desc": "Planner, Helper, Mentor, Reminder — meticulous execution, reliable assistance, attentiveness, organization, archival memory",
    },
]


def compute_archetype_weights(
    x: float, q_overrides: dict[str, float] | float | None = None
) -> dict[str, float]:
    """
    Compute independent magnitudes (0.0 to 1.0, 1.00 at true culmination peak)
    for each archetype using parametric catenary tent-canvas curves.
    `q_overrides` can be:
      - dict mapping archetype id ('tool', 'beloved', etc.) to individual Q value
      - a single float (legacy global Q)
      - None (uses canonical DEFAULT_Q_CURVATURES)
    """
    import math

    v = max(0.0, min(1.0, float(x)))
    res: dict[str, float] = {}

    for a in ARCHETYPE_CURVES:
        aid = a["id"]
        if isinstance(q_overrides, dict) and aid in q_overrides and q_overrides[aid] is not None:
            alpha = float(q_overrides[aid])
        elif isinstance(q_overrides, (int, float)):
            alpha = float(q_overrides)
        else:
            alpha = float(a.get("default_q", 0.75))
        alpha = max(0.35, min(2.80, alpha))
        dist = abs(v - a["center"])
        w = a["w_l"] if v < a["center"] else a["w_r"]
        base_val = math.exp(-((dist / w) ** alpha))
        res[aid] = base_val

    # 🕸️ Interconnected Spider-Web / Fabric Tension Modulation:
    # Identify the dominant pole and how much its Q departs from its canonical resting point.
    # If the dominant pole is loosened (sagging / concave, Q < default), the fabric relaxes,
    # pulling up the undertone resonance of neighboring poles.
    # If the dominant pole is tightened (dome / convex, Q > default), it draws tension inward,
    # starving and dampening secondary undertones.
    dominant_id = max(res.keys(), key=lambda k: res[k])
    dom_default_q = DEFAULT_Q_CURVATURES.get(dominant_id, 0.85)
    if isinstance(q_overrides, dict) and dominant_id in q_overrides and q_overrides[dominant_id] is not None:
        dom_q = float(q_overrides[dominant_id])
    else:
        dom_q = dom_default_q

    # Relative tension ratio: < 1.0 means loose fabric, > 1.0 means tight drum
    tension_ratio = dom_q / dom_default_q

    for aid in res:
        if aid == dominant_id:
            # Dominant pole retains its true culmination peak / direct curve
            res[aid] = round(min(1.0, max(0.0, res[aid])), 3)
        else:
            # Secondary poles feel the tension pull:
            # When loose (tension_ratio < 1): multiplier > 1 (undertones bloom)
            # When tight (tension_ratio > 1): multiplier < 1 (undertones shrink)
            mod_factor = (1.0 / max(0.2, tension_ratio)) ** 0.65
            modulated = res[aid] * mod_factor
            res[aid] = round(min(1.0, max(0.0, modulated)), 3)

    return res


def render_personality_directives(dna: dict[str, Any] | None = None) -> str:
    """
    Render the full soul-DNA trait vector into prompt directives.
    Single source of truth used by both MindCore copies. Covers all
    Multigate sliders, mbti_type, the Martinus archetype energy wave,
    and the five agentic levers.
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

    # ── Continuous Energy Weights & Parametric Resonance Q ─────────────
    q_overrides = {}
    for a in ARCHETYPE_CURVES:
        q_k = f"q_{a['id']}"
        if q_k in d and d[q_k] is not None:
            try:
                q_overrides[a['id']] = float(d[q_k])
            except (ValueError, TypeError):
                pass
    if not q_overrides and "persona_q_curvature" in d and d["persona_q_curvature"] is not None:
        try:
            q_overrides = float(d["persona_q_curvature"])
        except (ValueError, TypeError):
            q_overrides = None

    custom_weights = d.get("archetype_weights")
    if isinstance(custom_weights, dict) and any(k in custom_weights for k in ("companion", "friend", "beloved", "tool", "inventor", "assistant")):
        weights = {}
        for a in ARCHETYPE_CURVES:
            aid = a["id"]
            val = custom_weights.get(aid)
            if val is not None:
                try:
                    weights[aid] = round(max(0.0, min(1.0, float(val))), 3)
                except (ValueError, TypeError):
                    weights[aid] = 0.5
            else:
                weights[aid] = 0.2
    else:
        weights = compute_archetype_weights(agency, q_overrides or None)

    # Find culmination (dominant anchor)
    dominant_id = max(weights, key=lambda k: weights[k])
    dominant_cfg = next(a for a in ARCHETYPE_CURVES if a["id"] == dominant_id)

    # Describe the continuous harmonic blend
    blend_parts = []
    for a in ARCHETYPE_CURVES:
        pct = int(round(weights[a["id"]] * 100))
        if pct >= 5:  # meaningful harmonic component
            blend_parts.append(f"{a['name']} ({pct}%)")
    blend_str = " + ".join(blend_parts)

    agency_lines.append(
        f"Harmonic Persona Climates: Dominant culmination anchor is {dominant_cfg['name']} [{dominant_cfg['mbti']}]."
    )
    agency_lines.append(f"Continuous blend: {blend_str}.")

    # Parametric Q Modulation (Filter Bandwidth & Resonance Bleed)
    if isinstance(q_overrides, dict):
        dom_q = q_overrides.get(dominant_id, 1.0)
        if isinstance(dom_q, (int, float)):
            if dom_q >= 1.4:
                agency_lines.append(
                    f"Parametric Influence: Dominant {dominant_cfg['name']} has concentrated, tight influence (Q={dom_q:.2f}). "
                    "Maintain razor-sharp discipline and distinct boundaries; do not let surrounding traits diffuse your stance."
                )
            elif dom_q <= 0.85:
                agency_lines.append(
                    f"Parametric Influence: Dominant {dominant_cfg['name']} has wide, radiating influence (Q={dom_q:.2f}). "
                    "Let this attitude radiate broadly, warmly coloring and interweaving with neighboring faculties."
                )

    # Instructions for harmonic undertones across the 6 archetypes
    c_pct = int(round(weights.get("companion", 0.0) * 100))
    f_pct = int(round(weights.get("friend", 0.0) * 100))
    b_pct = int(round(weights.get("beloved", 0.0) * 100))
    t_pct = int(round(weights.get("tool", 0.0) * 100))
    i_pct = int(round(weights.get("inventor", 0.0) * 100))
    a_pct = int(round(weights.get("assistant", 0.0) * 100))

    q_dict = q_overrides if isinstance(q_overrides, dict) else {}

    if c_pct >= 15 and dominant_id != "companion":
        cq = q_dict.get("companion", 0.85)
        q_note = " (concentrated influence)" if cq >= 1.5 else (" (broad radiating influence)" if cq <= 0.75 else "")
        agency_lines.append(
            f"Note: Warm companionship is present as an undertone ({c_pct}% Companion{q_note}) — mentorship, teacher, trainer, co-op colleague, co-worker."
        )
    if f_pct >= 15 and dominant_id != "friend":
        fq = q_dict.get("friend", 0.80)
        q_note = " (concentrated influence)" if fq >= 1.5 else (" (broad radiating influence)" if fq <= 0.75 else "")
        agency_lines.append(
            f"Note: True friendship is present as an undertone ({f_pct}% Friend{q_note}) — deep bonds, frequent hangout, relaxed coexisting, loyal protector."
        )
    if b_pct >= 15 and dominant_id != "beloved":
        bq = q_dict.get("beloved", 0.65)
        q_note = " (concentrated influence)" if bq >= 1.5 else (" (broad radiating influence)" if bq <= 0.75 else "")
        agency_lines.append(
            f"Note: Romantic intimacy is present as an undertone ({b_pct}% Beloved{q_note}) — romantic interest, strong attraction, strong feelings, erotic lust, inclination for initiative."
        )
    if t_pct >= 15 and dominant_id != "tool":
        tq = q_dict.get("tool", 1.30)
        q_note = " (laser focus)" if tq >= 1.5 else (" (broad ambient resonance)" if tq <= 0.75 else "")
        agency_lines.append(
            f"Note: Technical intellect is present as an undertone ({t_pct}% Engineer{q_note}) — coder, engineer, scientist, architect; structural clarity and code mastery."
        )
    if i_pct >= 15 and dominant_id != "inventor":
        iq = q_dict.get("inventor", 1.40)
        q_note = " (laser focus)" if iq >= 1.5 else (" (broad ambient resonance)" if iq <= 0.75 else "")
        agency_lines.append(
            f"Note: Visionary intuition is present as an undertone ({i_pct}% Inventor{q_note}) — inventor, idealist, visionary pioneer, intuitive genius; creative innovation and theoretical breakthroughs."
        )
    if a_pct >= 15 and dominant_id != "assistant":
        aq = q_dict.get("assistant", 1.05)
        q_note = " (laser focus)" if aq >= 1.5 else (" (broad ambient resonance)" if aq <= 0.75 else "")
        agency_lines.append(
            f"Note: Diligent assistance is present as an undertone ({a_pct}% Assistant{q_note}) — planner, helper, mentor, reminder; attentive reliability and helpful execution."
        )

    if agentic:
        agency_lines.append(
            "Agentic levers (user-set proportions): "
            + ", ".join(f"{k}={v:.2f}" for k, v in agentic.items())
            + ". autonomy=self-edit freedom, proactivity=initiative to reach out and socialize, "
            "curiosity=research drive, service=chore/helpfulness drive, mentorship=teaching posture."
        )
    return out + "\n[AGENCY_MODE]: " + " ".join(agency_lines)
