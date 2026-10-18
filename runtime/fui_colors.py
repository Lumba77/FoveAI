"""
FoveAI Color Language (FUI) — single source of truth for color semantics.

The pedagogical color signum born in the Consciousness Equalizer
(~/.local/bin/foveai-menu). Color NEVER means decoration, it means state
or identity. Two families:

  1. ARCHETYPES — identity ("who/what am I talking to / who built this")
  2. STATES     — health  ("how is the fleet right now")

Every surface binds one of three medium adapters to the same roles:
  Terminal / SSH  → ansi
  Qt / GTK / PIL  → hex  (e.g. tray icons, Studio CSS)
  Web / HTML      → css  (same hex, injected as CSS vars)

If you need a color anywhere in FoveAI, import it from here. Never
hard-code hexes or ANSI codes in app code.
"""

import json
import os
import sys

# ─── Archetype palette (identity family) ─────────────────────────────
# Mirrors ARCHETYPE_PALETTE in ~/.local/bin/foveai-menu (the reference
# implementation). Do not diverge — change both together or change here
# and point the menu at this module.
ARCHETYPE_PALETTE: dict[str, dict] = {
    "companion": {
        "name": "COMPANION", "icon": "🤝", "mbti": "ENFJ",
        "desc": "Teacher & Co-op Partner [ENFJ]",
        "rgb": (255, 50, 50), "ansi": "\033[1;31m",
    },
    "friend": {
        "name": "FRIEND", "icon": "🌸", "mbti": "ENFP",
        "desc": "Deep Bonds & Protector [ENFP]",
        "rgb": (255, 230, 0), "ansi": "\033[1;33m",
    },
    "beloved": {
        "name": "BELOVED", "icon": "💖", "mbti": "INFP",
        "desc": "Romance, Lust & Initiative [INFP]",
        "rgb": (255, 60, 200), "ansi": "\033[1;35m",
    },
    "tool": {
        "name": "ENGINEER", "icon": "🔧", "mbti": "INTJ",
        "desc": "Coder, Engineer & Architect [INTJ]",
        "rgb": (0, 230, 100), "ansi": "\033[1;32m",
    },
    "inventor": {
        "name": "INVENTOR", "icon": "💡", "mbti": "ENTP",
        "desc": "Inventor, Idealist & Visionary [ENTP]",
        "rgb": (0, 220, 255), "ansi": "\033[1;36m",
    },
    "assistant": {
        "name": "ASSISTANT", "icon": "💼", "mbti": "ISTJ",
        "desc": "Planner & Helper [ISTJ]",
        "rgb": (95, 175, 255), "ansi": "\033[38;5;75m",
    },
}

# ─── State palette (health family) ───────────────────────────────────
# ok    : healthy, ready, idle-able                 → ENGINEER green
# busy  : loading / transitioning / active work     → orange (amber work)
# warn  : attention needed, dormant, pressure       → FRIEND gold
# crit  : failing, stopped, critical pressure       → COMPANION red
# idle  : offline, dormant, inactive UI             → gray
# info  : informational, brand accent               → INVENTOR cyan
# select: cursor / highlighted (via reverse or box) → current color + invert
STATES: dict[str, dict] = {
    "ok":    {"rgb": (0, 230, 100),    "ansi": "\033[1;32m", "glyph": "●", "word": "ACTIVE"},
    "busy":  {"rgb": (255, 158, 31),   "ansi": "\033[1;33m", "glyph": "◐", "word": "BUSY"},
    "warn":  {"rgb": (255, 230, 0),    "ansi": "\033[1;33m", "glyph": "⚠", "word": "WARN"},
    "crit":  {"rgb": (255, 50, 50),    "ansi": "\033[1;31m", "glyph": "✖", "word": "CRITICAL"},
    "idle":  {"rgb": (136, 136, 136),  "ansi": "\033[2m",    "glyph": "○", "word": "IDLE"},
    "info":  {"rgb": (0, 220, 255),    "ansi": "\033[1;36m", "glyph": "ℹ", "word": "INFO"},
    "select": {"rgb": (0, 220, 255),   "ansi": "\033[7m",    "glyph": "▶", "word": "SELECT"},
}

ANSI_RESET = "\033[0m"
ANSI_DIM = "\033[2m"


def _hex(rgb: tuple) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def archetype(cid: str) -> dict:
    return ARCHETYPE_PALETTE.get(cid, ARCHETYPE_PALETTE["inventor"])


def archetype_hex(cid: str) -> str:
    return _hex(archetype(cid)["rgb"])


def state(name: str) -> dict:
    return STATES.get(name, STATES["idle"])


def state_ansi(name: str) -> str:
    return state(name)["ansi"]


def state_hex(name: str) -> str:
    return _hex(state(name)["rgb"])


def state_glyph(name: str) -> str:
    return state(name)["glyph"]


def paint(text: str, ansi_code: str) -> str:
    """Wrap text in an ANSI code + reset (no-op if code empty)."""
    if not ansi_code:
        return text
    return f"{ansi_code}{text}{ANSI_RESET}"


def colorize(text: str, ansi_code: str, enabled: bool) -> str:
    """paint() that honors an isatty()/env gate — use in every TUI."""
    return paint(text, ansi_code) if enabled else text


def colorize_state(text: str, state_name: str, enabled: bool) -> str:
    return colorize(text, state_ansi(state_name), enabled)


def striped(text: str, ansi_a: str, ansi_b: str, row: int, enabled: bool) -> str:
    """Trademark FoveAI stripe: alternate two tints on even/odd rows.
    `row` is the 0-based line index. For the signature look prefer
    rainbow_band() — the lollipop comes from adjacent archetype hues."""
    if not enabled:
        return text
    return paint(text, ansi_a if row % 2 == 0 else ansi_b)


def rainbow_band(width: int, block: str = "█", enabled: bool = True) -> str:
    """The FoveAI lollipop: a horizontal band of adjacent archetype hues.

    The six archetype colors rendered side by side as colored blocks read
    as stripes — the Equalizer's signature aesthetic. Width = number of
    blocks; hues cycle companion→friend→beloved→tool→inventor→assistant.
    """
    if not enabled:
        return block * width
    order = ["companion", "friend", "beloved", "tool", "inventor", "assistant"]
    parts = []
    for i in range(width):
        ansi = ARCHETYPE_PALETTE[order[i % len(order)]]["ansi"]
        parts.append(f"{ansi}{block}")
    parts.append(ANSI_RESET)
    return "".join(parts)


def archetype_ansi(i: int) -> str:
    """Categorical color for item i — cycles the archetype hues, the same
    assignment rule as ITEM_CATEGORY_COLORS in foveai-menu."""
    order = ["companion", "friend", "beloved", "tool", "inventor", "assistant"]
    return ARCHETYPE_PALETTE[order[i % len(order)]]["ansi"]


# ─── Luminance staircase (menu grammar) ──────────────────────────────
# Sequential menu entries alternate DARK ↔ LIGHT so the column reads as
# an accordion / staircase rather than a uniform rainbow. Dark rows use
# normal-intensity hues, light rows use their bold variants — same six
# hues, two perceived brightness tiers.
_DARK_ANSI: dict[str, str] = {
    "companion": "\033[31m",    # dark red
    "tool": "\033[32m",         # dark green
    "inventor": "\033[36m",     # dark cyan
    "assistant": "\033[34m",    # dark blue
}
_LIGHT_ANSI: dict[str, str] = {
    "friend": "\033[1;33m",     # bright gold
    "beloved": "\033[1;35m",    # bright magenta
    "assistant": "\033[1;34m",  # bright blue
    "inventor": "\033[1;36m",   # bright cyan
}


def staircase_ansi(i: int) -> str:
    """Color for menu row i: dark ↔ light alternating (the accordion)."""
    if i % 2 == 0:
        order = list(_DARK_ANSI)
        return _DARK_ANSI[order[(i // 2) % len(order)]]
    order = list(_LIGHT_ANSI)
    return _LIGHT_ANSI[order[(i // 2) % len(order)]]


# ─── Surface grammar (canvas + theme coupling) ───────────────────────
# Main app surfaces share one canvas rule:
#   • Background: DARK, either base #1E1E1E → panel #2D2D2D or a dark
#     soft-gradient image. Colorful FUI colors are GUIDING colors only
#     (table headers, table framing, content-area accents) — never the
#     canvas.
#   • Dynamic: when the app runs/edits a main theme, the guiding colors
#     switch to the theme's accent (fv_accent / Theme API), falling back
#     to the FUI state/archetype roles when no theme is bound. Studio
#     already does this via the theme_update WebSocket; new surfaces
#     follow the same pattern:
#       canvas      ← theme bg (fallback #1E1E1E/#2D2D2D)
#       header      ← theme accent (fallback state_hex("info"))
#       frame       ← theme accent (fallback state_hex("info"))
#       content     ← theme fg   (fallback #E0E0E0)
#       danger/warn ← state_hex("crit"/"busy")


def use_color(stream=None) -> bool:
    """Gate: colors only on real TTYs and never when NO_FUI_COLOR is set."""
    if os.environ.get("NO_FUI_COLOR"):
        return False
    stream = stream or sys.stdout
    try:
        return stream.isatty()
    except Exception:
        return False


# ─── Cross-medium exports ─────────────────────────────────────────────
# This module IS the palette. Web, desktop and Android consumers bind it
# through the generated artifacts below (`python3 runtime/fui_colors.py`
# writes assets/fui_palette.css + assets/fui_palette.json). Never duplicate
# the values by hand in CSS/C# — regenerate from here.

_CSS_VAR_PREFIX = "fui"


_APP_BIND_VARS = {
    # generic app tokens (dashboard index.css + any var-driven surface).
    # Bound as vars so themes and pages can't hardcode them anymore.
    "--bg": "var(--fui-canvas)",
    "--panel": "var(--fui-canvas-panel)",
    "--panel-2": "var(--fui-canvas-panel)",
    "--text": "var(--fui-canvas-fg)",
    "--muted": "var(--fui-canvas-fg-dim)",
    "--accent": "var(--fui-info)",
    "--accent-2": "var(--fui-beloved)",
    "--ok": "var(--fui-ok)",
    "--success": "var(--fui-ok)",
    "--warn": "var(--fui-warn)",
    "--warning": "var(--fui-warn)",
    "--danger": "var(--fui-crit)",
    "--border": "color-mix(in srgb, var(--fui-info) 25%, transparent)",
}


def app_bind_vars() -> str:
    """Re-root the generic app tokens (--bg/--accent/--ok/…) on the FUI.

    Order of precedence after this ships:
      runtime themes (JS-injected --fv-*)  >  these bindings  >  nothing.
    Surfaces still follow the active main theme; FUI is the floor."""
    lines = [":root {", "  /* App token bindings — FUI is the semantic floor; */",
             "  /* runtime theme --fv-* injections still win on top.  */"]
    lines.extend(f"  {k}: {v};" for k, v in _APP_BIND_VARS.items())
    lines.append("}")
    return "\n".join(lines)


def css_vars() -> str:
    """`:root` CSS variable block for web surfaces (site, dashboard, XR).

    Vars are additions only — they don't change rendering until components
    reference them, so shipping them is safe without visual verification.
    """
    lines = [":root {"]
    for cid, a in ARCHETYPE_PALETTE.items():
        lines.append(f"  --{_CSS_VAR_PREFIX}-{cid}: {_hex(a['rgb'])};")
    for name, s in STATES.items():
        lines.append(f"  --{_CSS_VAR_PREFIX}-{name}: {_hex(s['rgb'])};")
    lines.extend(
        [
            "  --fui-canvas: #1E1E1E;",
            "  --fui-canvas-panel: #2D2D2D;",
            "  --fui-canvas-fg: #E0E0E0;",
            "  --fui-canvas-fg-dim: #888888;",
            "}",
        ]
    )
    return "\n".join(lines)


def json_palette() -> dict:
    """Canonical machine-readable palette for desktop + Android/Unity.

    The `unity` section carries the same data as flat key/hex arrays —
    JsonUtility (no Newtonsoft in the Unity project) parses those."""
    out = {
        "version": 1,
        "source": "runtime/fui_colors.py",
        "archetypes": {},
        "states": {},
        "canvas": {
            "base": "#1E1E1E", "panel": "#2D2D2D",
            "fg": "#E0E0E0", "fg_dim": "#888888",
        },
        "unity": {
            "states": [{"key": k, "hex": _hex(s["rgb"])} for k, s in STATES.items()],
            "archetypes": [
                {"key": cid, "hex": _hex(a["rgb"])} for cid, a in ARCHETYPE_PALETTE.items()
            ],
            "canvas": {
                "base": "#1E1E1E", "panel": "#2D2D2D",
                "fg": "#E0E0E0", "fg_dim": "#888888",
            },
        },
    }
    for cid, a in ARCHETYPE_PALETTE.items():
        out["archetypes"][cid] = {
            "name": a["name"], "icon": a["icon"], "mbti": a["mbti"],
            "desc": a["desc"], "hex": _hex(a["rgb"]), "rgb": list(a["rgb"]),
            "ansi": a["ansi"],
        }
    for name, s in STATES.items():
        out["states"][name] = {
            "hex": _hex(s["rgb"]), "rgb": list(s["rgb"]),
            "ansi": s["ansi"], "glyph": s["glyph"], "word": s["word"],
        }
    return out


def write_palette_assets(assets_dir: str) -> list[str]:
    """Regenerate the cross-platform palette artifacts into assets_dir."""
    written = []
    css_path = os.path.join(assets_dir, "fui_palette.css")
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(
            "/* GENERATED by `python3 runtime/fui_colors.py` — do not edit.\n"
            "   FoveAI Color Language: guiding colors for web surfaces.\n"
            "   Vars only — components opt in, rendering unchanged until used. */\n"
            + css_vars() + "\n" + app_bind_vars() + "\n" + MEDIA_CSS + "\n"
        )
    written.append(css_path)
    json_path = os.path.join(assets_dir, "fui_palette.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_palette(), f, indent=2)
        f.write("\n")
    written.append(json_path)
    return written


# ─── The -fui Theme Family ────────────────────────────────────────────
# One blob schema, four intensity/canvas variants. Ordering principle:
# readability first (canvas → text → muted → border → discreet accents →
# warn → crit), intensity = how loud the guiding colors are. The core
# directive never changes: color means state/identity, canvas stays calm,
# graphics are table shapes (framed panels) + a large image background.
#
#   signum   (dark,  balanced)  — THE authoritative default
#   whisper  (dark,  discreet)  — desaturated, quiet
#   screamer (dark,  loud)      — full-chroma, very screamy
#   daylight (LIGHT)            — light canvas, hues darkened for contrast

def _lerp(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


_GRAY = (128, 128, 128)
_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)


def _variant_states(mode: str, intensity: float) -> dict:
    """State colors adapted for canvas mode + intensity (readability order)."""
    out = {}
    for name, s in STATES.items():
        rgb = s["rgb"]
        if intensity < 0.5:            # discreet: toward gray
            rgb = _lerp(rgb, _GRAY, 0.45)
        elif intensity > 0.5:          # screamy: full chroma
            rgb = _lerp(rgb, tuple(255 if c > 128 else 0 for c in rgb), 0.35)
        if mode == "light":            # light canvas needs darker inks
            rgb = _lerp(rgb, _BLACK, 0.28)
        out[name] = {"rgb": rgb, "hex": _hex(rgb)}
    return out


# full --fv-* vocabulary (as consumed by settings.css / aurora css),
# written in terms of the per-variant --fui-* roles the theme emits.
_FV_TOKEN_MAP: dict[str, str] = {
    "--fv-base": "var(--fui-canvas)",
    "--fv-surface": "color-mix(in srgb, var(--fui-panel) 80%, transparent)",
    "--fv-surface-2": "var(--fui-panel)",
    "--fv-glass-top": "color-mix(in srgb, var(--fui-info) 10%, transparent)",
    "--fv-glass-card": "linear-gradient(135deg, color-mix(in srgb, var(--fui-info) 4%, transparent), color-mix(in srgb, var(--fui-info) 1%, transparent))",
    "--fv-text": "var(--fui-fg)",
    "--fv-muted": "var(--fui-fg-dim)",
    "--fv-accent": "var(--fui-info)",
    "--fv-accent-2": "var(--fui-beloved)",
    "--fv-accent-dim": "color-mix(in srgb, var(--fui-info) 13%, transparent)",
    "--fv-violet-dim": "color-mix(in srgb, var(--fui-beloved) 13%, transparent)",
    "--fv-ok": "var(--fui-ok)",
    "--fv-warn": "var(--fui-busy)",
    "--fv-danger": "var(--fui-crit)",
    "--fv-border": "color-mix(in srgb, var(--fui-info) 25%, transparent)",
    "--fv-border-strong": "color-mix(in srgb, var(--fui-info) 45%, transparent)",
    "--fv-border-accent": "color-mix(in srgb, var(--fui-info) 55%, transparent)",
    "--fv-inset-hi": "inset 0 1px 0 rgba(127,127,127,0.12)",
    "--fv-inset-press": "inset 0 2px 6px rgba(0,0,0,0.35)",
    "--fv-shadow": "0 3px 14px rgba(0,0,0,0.35)",
    "--fv-shadow-lg": "0 12px 36px rgba(0,0,0,0.5)",
    "--fv-shadow-btn": "0 2px 8px rgba(0,0,0,0.3)",
    "--fv-radius": "var(--fui-radius, 6px)",
    "--fv-light-angle": "var(--fui-light-angle, 135deg)",
    "--fv-gradient": "linear-gradient(180deg, var(--fui-canvas) 0%, var(--fui-panel) 100%)",
    "--fv-grad": "linear-gradient(180deg, var(--fui-canvas) 0%, var(--fui-panel) 100%)",
    "--fv-animation-style": "breathe",
    "--fv-ornamentation": "minimal",
}


# ─── Media grammar (images/video) ─────────────────────────────────────
# Proportions are ALWAYS kept — never distort. Scale to fit; overscale
# ("overtrass") where most suitable. Canonical first choice: overtrass
# HORIZONTALLY (fill the width, bleed/crop the height) unless overruled.
MEDIA_CSS = """
/* media grammar — proportions always preserved, scale to fit;
   canonical: overtrass horizontally (fill width, crop height) and center
   horizontally unless overruled;
   override: .fui-media-v (vertical) or .fui-media-fit (contain) */
.fui-media {
  display: block; margin: 0 auto;
  width: 100%; height: auto;
  object-fit: cover; object-position: center;
}
.fui-media-v { display: block; margin: 0 auto; width: auto; height: 100%; }
.fui-media-fit { object-fit: contain; margin: 0 auto; display: block; }
.fui-media-bg {
  background-size: 100% auto;      /* horizontal overtrass */
  background-position: center;     /* horizontal centering norm */
  background-repeat: no-repeat;
  background-attachment: fixed;
}
"""


def media_css() -> str:
    return MEDIA_CSS
# Same rule: serves readability first. Structure = geometry grammar.
# ─── Structure layer (shapes, cutouts, ornamentation) ─────────────────
# Same rule: serves readability first. Structure = geometry grammar.
STRUCTURES: dict[str, dict] = {
    "signum": {
        "structure": "left-menu",       # menu position grammar
        "shape_radius": "6px",          # corner shape language
        "ornamentation": "minimal",     # none beyond function
        "cutout": "inset 0 2px 6px rgba(0,0,0,0.45)",        # pressed well
        "cutout_hi": "inset 0 1px 0 rgba(255,255,255,0.09)", # well lip
    },
    "whisper": {
        "structure": "left-menu",
        "shape_radius": "4px",
        "ornamentation": "minimal",
        "cutout": "inset 0 1px 4px rgba(0,0,0,0.25)",
        "cutout_hi": "inset 0 1px 0 rgba(255,255,255,0.03)",
    },
    "screamer": {
        "structure": "left-menu",
        "shape_radius": "10px",
        "ornamentation": "cyber-lines",
        "cutout": "inset 0 3px 10px rgba(0,0,0,0.7)",
        "cutout_hi": "inset 0 1px 0 rgba(0,220,255,0.25)",
    },
    "daylight": {
        "structure": "left-menu",
        "shape_radius": "8px",
        "ornamentation": "minimal",
        "cutout": "inset 0 2px 5px rgba(23,32,42,0.14)",
        "cutout_hi": "inset 0 1px 0 rgba(0,0,0,0.04)",
    },
}


def structure_css(struct: dict) -> list[str]:
    """Structure layer as CSS: geometry + cutout tokens + helper classes."""
    return [
        "",
        "/* structure layer — shapes, ornamentation, surface cutouts */",
        ":root {",
        f"  --fui-structure: {struct['structure']};",
        f"  --fui-shape: {struct['shape_radius']};",
        f"  --fui-ornamentation: {struct['ornamentation']};",
        f"  --fui-cutout: {struct['cutout']};",
        f"  --fui-cutout-hi: {struct['cutout_hi']};",
        "}",
        "",
        ".fui-cutout, input, textarea, select {  /* pressed surface well (inputs, LCDs) */",
        "  box-shadow: var(--fui-cutout), var(--fui-cutout-hi);",
        "  border-radius: var(--fui-shape);",
        "}",
        ".fui-raised {  /* elevated card with shape */",
        "  border-radius: var(--fui-shape);",
        "  box-shadow: var(--fui-shadow-rest), var(--fui-highlight);",
        "}",
    ]


# ─── Finish layer (beyond color) ─────────────────────────────────────
# Materials, gloss, shadows, highlights, gradients, patterns, fades.
# Same rule as color: structure serves readability first.
FINISHES: dict[str, dict] = {
    "signum": {                      # satin instrument
        "material": "satin",
        "gloss": 0.10,
        "highlight": "inset 0 1px 0 rgba(255,255,255,0.10)",
        "shadow_rest": "0 3px 14px rgba(0,0,0,0.40)",
        "shadow_hover": "0 6px 22px rgba(0,0,0,0.50)",
        "pattern": "stripes",        # the House lollipop, 1px hairlines
        "pattern_strength": 0.06,
        "fade": 24,                  # content-edge fade px
    },
    "whisper": {                     # matte, nearly invisible structure
        "material": "matte",
        "gloss": 0.03,
        "highlight": "inset 0 1px 0 rgba(255,255,255,0.04)",
        "shadow_rest": "0 1px 6px rgba(0,0,0,0.20)",
        "shadow_hover": "0 2px 10px rgba(0,0,0,0.28)",
        "pattern": "none",
        "pattern_strength": 0.0,
        "fade": 12,
    },
    "screamer": {                    # neon gloss, glowing edges
        "material": "neon",
        "gloss": 0.25,
        "highlight": "inset 0 1px 0 rgba(255,255,255,0.25)",
        "shadow_rest": "0 0 18px rgba(0,220,255,0.25), 0 4px 16px rgba(0,0,0,0.5)",
        "shadow_hover": "0 0 30px rgba(0,220,255,0.45), 0 8px 26px rgba(0,0,0,0.55)",
        "pattern": "stripes",
        "pattern_strength": 0.12,
        "fade": 32,
    },
    "daylight": {                    # clean light material
        "material": "satin-light",
        "gloss": 0.12,
        "highlight": "inset 0 1px 0 rgba(0,0,0,0.06)",
        "shadow_rest": "0 2px 10px rgba(23,32,42,0.14)",
        "shadow_hover": "0 4px 18px rgba(23,32,42,0.20)",
        "pattern": "none",
        "pattern_strength": 0.0,
        "fade": 16,
    },
}


def finish_css(finish: dict) -> list[str]:
    """Finish layer emitted as CSS: material vars + helpers."""
    pat = ""
    if finish["pattern"] == "stripes" and finish["pattern_strength"] > 0:
        a = int(finish["pattern_strength"] * 100)
        pat = (
            "repeating-linear-gradient(135deg, "
            f"rgba(127,127,127,{finish['pattern_strength']}) 0 1px, transparent 1px 7px)"
        )
    return [
        "",
        "/* finish layer — material, gloss, shadows, gradient, pattern, fade */",
        ":root {",
        f"  --fui-material: {finish['material']};",
        f"  --fui-gloss: {finish['gloss']};",
        f"  --fui-highlight: {finish['highlight']};",
        f"  --fui-shadow-rest: {finish['shadow_rest']};",
        f"  --fui-shadow-hover: {finish['shadow_hover']};",
        f"  --fui-pattern: {pat or 'none'};",
        f"  --fui-fade: {finish['fade']}px;",
        "}",
        "",
        ".fui-finish {",
        "  box-shadow: var(--fui-shadow-rest), var(--fui-highlight);",
        f"  background-image: {pat or 'none'};" if pat else "",
        "}",
        ".fui-finish:hover { box-shadow: var(--fui-shadow-hover), var(--fui-highlight); }",
        ".fui-fade-r {",
        f"  -webkit-mask-image: linear-gradient(90deg, #000 calc(100% - var(--fui-fade)), transparent);",
        "          mask-image: linear-gradient(90deg, #000 calc(100% - var(--fui-fade)), transparent);",
        "}",
    ]


def fui_variant(name: str) -> dict:
    """Full variant spec: canvas + ordered guiding roles + theme blob."""
    modes = {
        "signum": ("dark", 0.5),
        "whisper": ("dark", 0.25),
        "screamer": ("dark", 1.0),
        "daylight": ("light", 0.5),
    }
    if name not in modes:
        name = "signum"
    mode, intensity = modes[name]

    st = _variant_states(mode, intensity)
    # archetype identity colors follow the same intensity/mode as states
    arch = {}
    for cid, a in ARCHETYPE_PALETTE.items():
        rgb = a["rgb"]
        if intensity < 0.5:
            rgb = _lerp(rgb, _GRAY, 0.45)
        elif intensity > 0.5:
            rgb = _lerp(rgb, tuple(255 if c > 128 else 0 for c in rgb), 0.35)
        if mode == "light":
            rgb = _lerp(rgb, _BLACK, 0.28)
        arch[cid] = _hex(rgb)
    if mode == "dark":
        canvas = {"base": "#1E1E1E", "panel": "#2D2D2D",
                  "fg": "#E0E0E0", "fg_dim": "#888888"}
    else:
        canvas = {"base": "#ECEFF3", "panel": "#FFFFFF",
                  "fg": "#17202A", "fg_dim": "#5A6B7B"}

    display = {
        "signum": "FoveAI Signum",
        "whisper": "Signum Whisper",
        "screamer": "Signum Screamer",
        "daylight": "Signum Daylight",
    }[name]
    canvas_word = "Dark" if mode == "dark" else "Light"
    loud = {"whisper": "discreet", "signum": "balanced",
            "screamer": "very screamy", "daylight": "balanced"}[name]

    blob = {
        "id": f"fui-{name}",
        "theme_name": display,
        "fui_family": True,
        "fui_variant": name,
        "fui_mode": mode,
        "fv_accent": st["info"]["hex"],
        "fv_accent_2": st["warn"]["hex"],
        "fv_ok": st["ok"]["hex"],
        "fv_warn": st["busy"]["hex"],
        "fv_danger": st["crit"]["hex"],
        "fv_bg_dark": canvas["base"],
        "fv_bg_panel": canvas["panel"],
        "fv_text_main": canvas["fg"],
        "fv_text_muted": canvas["fg_dim"],
        "background_prompt": (
            f"{'Light airy' if mode == 'light' else 'Dark soft'} {canvas['base']} "
            f"gradient canvas with a {st['info']['hex']} guiding bloom, large calm "
            f"surface, no objects, 8k. FoveAI {display} — {loud} guiding colors, "
            "readability ordered."
        ),
        "ui_structure": {
            "menu_position": STRUCTURES[name]["structure"].split("-")[0],
            "border_radius": STRUCTURES[name]["shape_radius"],
            "glass_opacity": FINISHES[name]["gloss"],
            "shadow_intensity": "glowing" if FINISHES[name]["material"] == "neon" else "soft",
            "light_angle": "135deg" if mode == "dark" else "315deg",
            "time_of_day_sync": False,
            "animation_style": "breathe",
            "ornamentation": STRUCTURES[name]["ornamentation"],
        },
        "_canvas": canvas,
        "_states": st,
        "_archetypes": arch,
        "_finish": FINISHES[name],
        "_structure": STRUCTURES[name],
    }
    return blob


FUI_VARIANTS = ("signum", "whisper", "screamer", "daylight")


def theme_blob(name: str = "signum") -> dict:
    b = fui_variant(name)
    return {k: v for k, v in b.items() if not k.startswith("_")}


def theme_css(name: str = "signum", bg_image: str | None = None) -> str:
    """Variant stylesheet: --fv-* vocabulary re-rooted on the variant's
    --fui-* roles, plus .fui-table/.fui-frame helpers and the large-surface
    background-image hook."""
    b = fui_variant(name)
    st, canvas, arch = b["_states"], b["_canvas"], b["_archetypes"]
    fin, struct = b["_finish"], b["_structure"]
    order = [
        ("canvas", canvas["base"], "1 - canvas: calm, always"),
        ("panel", canvas["panel"], "2 - panel: content surface"),
        ("fg", canvas["fg"], "3 - text ink (readability first)"),
        ("fg-dim", canvas["fg_dim"], "4 - muted ink"),
        ("ok", st["ok"]["hex"], "5 - discreet accent (state: ok)"),
        ("info", st["info"]["hex"], "6 - guiding accent (state: info)"),
        ("busy", st["busy"]["hex"], "7 - attention (state: busy)"),
        ("crit", st["crit"]["hex"], "8 - loudest, reserve for failure"),
    ]
    lines = [
        "/* GENERATED by `python3 runtime/fui_colors.py` - do not edit.",
        f"   {b['theme_name']} - -fui theme family ({b['fui_mode']} canvas, readability-ordered).",
        "   Graphics = table shapes + large image background.",
        "   Core directive: color means state/identity; canvas stays calm. */",
        "", ":root {",
        "  /* ordered by readability - canvas, ink, accent, alarm */",
    ]
    lines += [f'  --fui-{var}: {val};' for var, val, _ in order]
    lines += ['  /* archetype identity colors (same intensity/mode) */']
    lines += [f'  --fui-{cid}: {hx};' for cid, hx in arch.items()]
    lines += [
        f"  --fui-warn: {st['busy']['hex']};",
        f"  --fui-idle: {'#5A6B7A' if b['fui_mode'] == 'dark' else '#9AA7B4'};",
        "  --fui-radius: 6px;",
        "  --fui-light-angle: 135deg;",
        f"  --fui-bg-image: {'url(' + bg_image + ')' if bg_image else 'none'};",
        "}",
    ]
    lines += structure_css(struct)
    lines += finish_css(fin)
    lines += [
        "",
        "body {",
        "  background: var(--fui-bg-image),",
        "    linear-gradient(180deg, var(--fui-canvas) 0%, var(--fui-panel) 100%);",
        "  background-size: 100% auto, auto;   /* horizontal overtrass for bg art */",
        "  background-position: center;        /* horizontal centering, the norm */",
        "  background-repeat: no-repeat;",
        "  background-attachment: fixed;",
        "  color: var(--fui-fg);",
        "}",
        "",
        "/* table shapes - the FUI graphic language */",
        ".fui-frame {",
        "  background: var(--fui-panel);",
        "  border: 1px solid color-mix(in srgb, var(--fui-info) 25%, transparent);",
        "  border-radius: var(--fui-radius);",
        "}",
        ".fui-table {",
        "  width: 100%; border-collapse: separate; border-spacing: 0;",
        "  background: var(--fui-panel);",
        "  border: 1px solid color-mix(in srgb, var(--fui-info) 25%, transparent);",
        "  border-radius: var(--fui-radius); overflow: hidden;",
        "}",
        ".fui-table th {",
        "  background: color-mix(in srgb, var(--fui-info) 14%, transparent);",
        "  color: var(--fui-fg); border-bottom: 1px solid var(--fui-info);",
        "  text-align: left; padding: 8px 10px;",
        "}",
        ".fui-table td {",
        "  color: var(--fui-fg);",
        "  border-top: 1px solid color-mix(in srgb, var(--fui-fg-dim) 30%, transparent);",
        "  padding: 7px 10px;",
        "}",
        ".fui-table tr:nth-child(even) td {",
        "  background: color-mix(in srgb, var(--fui-fg-dim) 8%, transparent);",
        "}",
        "",
        "/* --fv-* dialect map (theme propagation) */",
        ":root {",
    ]
    lines += [f"  {k}: {v};" for k, v in _FV_TOKEN_MAP.items()]
    lines += ["}", ""]
    lines += MEDIA_CSS.strip().split("\n")
    lines += [""]
    return "\n".join(lines)



def master_theme() -> dict:
    """Compat alias — the authoritative Signum blob."""
    return theme_blob("signum")


def update_manifest(manifest_path: str | None = None) -> None:
    """Refresh the fui-* family in Backend/themes/manifest.json (read-modify-
    write, other themes untouched; default = fui-signum)."""
    p = manifest_path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Backend", "themes", "manifest.json")
    mf: dict = {}
    if os.path.exists(p):
        try:
            mf = json.load(open(p, "r", encoding="utf-8"))
        except Exception:
            mf = {}
    themes = [t for t in mf.get("themes", []) if not t.get("fui_family")]
    for name in FUI_VARIANTS:
        b = theme_blob(name)
        themes.insert(0, {
            "id": b["id"], "name": b["theme_name"], "fui_family": True,
            "fui_variant": name, "fui_mode": b["fui_mode"],
            "authoritative": name == "signum",
            "description": (
                f"-fui {b['fui_mode']} canvas, {'the authoritative default' if name == 'signum' else b['ui_structure']['ornamentation']} finish"
            ),
            "colors": {"bg": b["fv_bg_dark"], "panel": b["fv_bg_panel"],
                       "accent": b["fv_accent"], "accent-2": b["fv_accent_2"],
                       "ok": b["fv_ok"], "warn": b["fv_warn"], "danger": b["fv_danger"]},
            **{k: v for k, v in b.items() if k in ("theme_name", "fv_", "background_prompt", "ui_structure") or k.startswith("fv_")},
        })
    mf["themes"] = themes
    mf["default"] = "fui-signum"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(mf, f, indent=2)
        f.write("\n")


def render_fui_theme(variant: str = "signum", bg_image: str | None = None,
                     apply_live: bool = True) -> list[str]:
    """ENGINE ENTRY: render (a) new -fui theme variant and live-apply it.

    Writes fui-<variant>.css into every public dir (+ palette artifacts),
    refreshes the manifest, POSTs the blob to :8400/api/theme/set_active
    (persisted → survives restart). Returns written paths."""
    written = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = [os.path.join(root, "assets")]
    for sub in ("Frontend/multigate/public", "Frontend/XR_Vessel/public",
                "foveated-memory/public"):
        if os.path.isdir(os.path.join(root, sub)):
            targets.append(os.path.join(root, sub))
    css = theme_css(variant, bg_image=bg_image)
    fname = "foveai-signum.css" if variant == "signum" else f"fui-{variant}.css"
    for d in targets:
        for p in write_palette_assets(d):
            written.append(p)
        tp = os.path.join(d, fname)
        with open(tp, "w", encoding="utf-8") as f:
            f.write(css)
        written.append(tp)
    update_manifest()
    if apply_live:
        blob = theme_blob(variant)
        if bg_image:
            blob["background_image_url"] = bg_image
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8400/api/theme/set_active",
                data=json.dumps(blob).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=4).read()
        except Exception:
            pass
    return written


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--render":
        variant = args[1] if len(args) > 1 else "signum"
        bg = args[args.index("--bg-image") + 1] if "--bg-image" in args else None
        for p in render_fui_theme(variant, bg_image=bg):
            print(f"-fui render → {p}")
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        targets = [os.path.join(root, "assets")]
        for sub in (
            "Frontend/multigate/public",
            "Frontend/XR_Vessel/public",
            "foveated-memory/public",
        ):
            if os.path.isdir(os.path.join(root, sub)):
                targets.append(os.path.join(root, sub))
        for _dir in targets:
            for p in write_palette_assets(_dir):
                print(f"FUI palette → {p}")
            fname = "foveai-signum.css"
            with open(os.path.join(_dir, fname), "w", encoding="utf-8") as f:
                f.write(theme_css("signum"))
            print(f"FUI Signum theme → {os.path.join(_dir, fname)}")
        update_manifest()
        print("Manifest updated (fui family + default=fui-signum)")