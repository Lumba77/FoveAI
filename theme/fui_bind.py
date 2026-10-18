"""
FoveAI FUI Bind — the handoff where a generated blueprint joins the
canonical FUI vocabulary and gains its voices.

This is where the generators COINCIDE into the theme engine:
  image generator  → blueprint accents (kept as identity)
  code generator   → FUI-dialect CSS (canonical tokens + media grammar)
  audio generator  → sound fingerprint (finish, made audible)
                     + soundscape (the Dirigent-specified recording)

Canvas rule: dark, calm — always re-rooted. Economy: OGG mono ~56k,
≤ 1.2 MB. Structure serves readability; under-band stays untouched.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

_THEMES_DIR = os.path.dirname(os.path.abspath(__file__))
_FOVEAI_DIR = os.path.dirname(_THEMES_DIR)
if _FOVEAI_DIR not in sys.path:
    sys.path.insert(0, _FOVEAI_DIR)

from theme.sound_fingerprint import fingerprint as sound_fingerprint  # noqa: E402
from theme.soundscape import render_soundscape as render_soundscape  # noqa: E402


def _dirigent_spec(theme: dict[str, Any]) -> dict[str, Any]:
    """The Dirigent (resident LLM via :8400) interprets the theme into a
    chord family + atmosphere scene — the soundscape is prompted into
    existence. Deterministic sector map when the conductor is silent."""
    DEFAULT = {
        "cyan": ("F_LYDIAN", "COSMIC"), "azure": ("F_LYDIAN", "COSMIC"),
        "gold": ("G_MAJOR", "FOREST"), "yellow": ("G_MAJOR", "FOREST"),
        "orange": ("G_MAJOR", "MECHANIC"), "red": ("C_DOMINANT7", "MECHANIC"),
        "green": ("C_MAJ7", "FOREST"), "violet": ("D_HARMONIC", "VOID"),
        "pink": ("A_MINOR", "COSMIC"), "magenta": ("G_PHRYGIAN", "OCEANIC"),
        "blue": ("E_MINOR", "OCEANIC"),
    }
    fp = (theme.get("generative_audio") or {}).get("acoustic") or {}
    chord, scene = DEFAULT.get(fp.get("sector"), ("A_MINOR", "SUBTERRANEAN"))
    try:
        import urllib.request as _u

        prompt = (
            "You are the FoveAI Dirigent — sound conductor. A theme was designed "
            f"named '{theme.get('theme_name', 'Unknown')}' with visual mood: "
            f"{(theme.get('background_prompt') or '')[:300]}. "
            "Choose the matching acoustic atmosphere. Reply ONLY compact JSON: "
            "{\"chord\": \"<one of C_MAJOR, C_MAJ7, A_MINOR, E_MINOR, G_MAJOR, "
            "F_LYDIAN, C_DOMINANT7, D_HARMONIC>\", "
            "\"scene\": \"<one of VOID, SUBTERRANEAN, COSMIC, OCEANIC, MECHANIC, FOREST>\"}"
        )
        req = _u.Request(
            "http://127.0.0.1:8400/v1/chat/completions",
            data=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "stream": False, "max_tokens": 60,
            }).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with _u.urlopen(req, timeout=6) as r:
            txt = json.loads(r.read())["choices"][0]["message"]["content"]
        d = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        if d.get("chord") in CHORD_NAMES:
            chord = d["chord"]
        if d.get("scene") in SCENE_NAMES:
            scene = d["scene"]
    except Exception:
        pass
    return {"chord": chord, "scene": scene, "dirigent": True}


CHORD_NAMES = {"C_MAJOR", "C_MAJ7", "A_MINOR", "E_MINOR", "G_MAJOR",
               "F_LYDIAN", "C_DOMINANT7", "D_HARMONIC"}
SCENE_NAMES = {"VOID", "SUBTERRANEAN", "COSMIC", "OCEANIC", "MECHANIC", "FOREST"}


def fui_bind_theme(theme: dict[str, Any], image_path: str | None = None,
                   with_soundscape: bool = True) -> dict[str, Any]:
    """Bind a generated (or hand-made) theme onto the canonical FUI grammar:
    dark canvas, FUI-dialect identity accents kept, fingerprinted audio,
    Dirigent-specified soundscape loop (economially encoded)."""
    theme = dict(theme)
    theme["fui_family"] = True
    theme.setdefault("fv_bg_dark", "#1E1E1E")      # canvas rule: dark, calm
    theme.setdefault("fv_bg_panel", "#2D2D2D")
    theme.setdefault("fv_text_main", "#E0E0E0")
    theme.setdefault("fv_text_muted", "#888888")

    stats = None
    if image_path and os.path.exists(image_path):
        try:
            from theme.sound_fingerprint import analyze_image, design_sound

            stats = analyze_image(image_path)
            theme["generative_audio"] = design_sound(stats)
            theme["fui_sounded"] = True
        except Exception as e:
            print(f"[fui_bind] sound fingerprint failed (skipping): {e}")

    if with_soundscape:
        try:
            spec = _dirigent_spec(theme)
            spec["name"] = theme.get("theme_name", "fui-theme")
            if theme.get("generative_audio", {}).get("acoustic"):
                a = theme["generative_audio"]["acoustic"]
                spec["sector"] = a.get("sector", spec.get("sector"))
            spec.setdefault("warmth", -0.2)
            spec.setdefault("contrast", 0.2)
            spec.setdefault("saturation", 0.4)
            spec["dark"] = theme.get("fv_bg_dark", "#1E1E1E") not in ("#ECEFF3",)
            path = render_soundscape(spec)
            if path and os.path.exists(path):
                import soundfile as _sf
                info = _sf.info(path)
                theme["soundscape_url"] = f"/api/theme/sound/{os.path.basename(path)}"
                theme["soundscape_loop_seconds"] = round(info.duration, 1)
        except Exception as e:
            print(f"[fui_bind] soundscape render failed (silent theme): {e}")
    return theme


# Back-compat: theme_api.py re-exports via import
SoundFingerprintError = ValueError