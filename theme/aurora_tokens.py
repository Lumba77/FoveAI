#!/usr/bin/env python3
"""aurora_tokens.py — FoveAI AURORA theme → GTK3 provider.

Parses theme/foveai-aurora.css :root tokens and hands them to GTK apps
(FoveAI_Studio, FoveAI_Dash, taskbar dialogs) as one CssProvider.
Surfaces import like:   from theme.aurora_tokens import apply_theme
"""

import re
from pathlib import Path

_CANDIDATES = (
    Path(__file__).resolve().parent / "foveai-aurora.css",
    Path("/home/lumba/FoveAI/theme/foveai-aurora.css"),
)

_DEFAULTS = {
    "accent": "#5eead4", "accent2": "#a78bfa",
    "text": "#c7d0dd", "muted": "#8b95a5",
    "bg": "#151923", "bg2": "#1b2230",
    "danger": "#f87171", "warn": "#fbbf24", "ok": "#34d399",
    "border": "rgba(148,163,184,0.14)",
}


def _load_tokens() -> dict:
    css = None
    for p in _CANDIDATES:
        if p.exists():
            css = p.read_text()
            break
    tokens = dict(_DEFAULTS)
    if css:
        root = css.split(":root", 1)[-1].split("}", 1)[0]
        # map fv accents → GTK palette
        def grab(name, default):
            m = re.search(rf"--fv-{name}:\s*([^;]+);", root)
            return m.group(1).strip() if m else default
        tokens["accent"] = grab("accent", tokens["accent"])
        tokens["accent2"] = _strip(grab("accent-2", tokens["accent2"]))
        tokens["danger"] = _strip(grab("danger", tokens["danger"]))
        tokens["warn"] = _strip(grab("warn", tokens["warn"]))
        tokens["ok"] = _strip(grab("ok", tokens["ok"]))
        tokens["text"] = _strip(grab("text", tokens["text"]))
        tokens["muted"] = _strip(grab("muted", tokens["muted"]))
    return tokens


def _strip(v: str) -> str:
    v = v.strip()
    # rgba(...) in CSS = GTK CSS also supports rgba — keep as-is
    return v


def hex_at(v: str, alpha: float = 1.0) -> str:
    """accent-dim variants: turn any color into an alpha-blended rgba."""
    m = re.match(r"#([0-9a-fA-F]{6})", v.strip())
    if m:
        r, g, b = (int(m.group(1)[i:i+2], 16) for i in (0, 2, 4))
        return f"rgba({r},{g},{b},{alpha})"
    return v


def gtk_css() -> bytes:
    t = _load_tokens()
    a = t["accent"]; a2 = t["accent2"]
    a_dim = hex_at(a, 0.14); a_border = hex_at(a, 0.42)
    text = t["text"]; muted = t["muted"]
    bg = t["bg"]; bg2 = t["bg2"]
    ok_ = t["ok"]; warn_ = t["warn"]; danger = t["danger"]
    return f"""
window, dialog {{ background: {bg}; color: {text}; }}
notebook header.top {{ background: {bg2}; border-bottom: 1px solid {a_border}; }}
notebook tab {{ background: transparent; padding: 6px 18px; color: {muted}; }}
notebook tab:checked {{
    color: {a};
    box-shadow: inset 0 -2px 0 0 {a};
}}
label {{ color: {text}; }}
label.dim-label {{ color: {muted}; }}

.lcd {{
    font-family: monospace; font-size: 13px; font-weight: bold;
    color: {ok_}; background: rgba(0,0,0,0.5);
    border-radius: 6px; padding: 5px 10px;
    border: 1px solid {hex_at(ok_, 0.28)};
}}
.lcd.amber {{ color: {warn_}; border-color: {hex_at(warn_, 0.30)}; }}
.lcd.red   {{ color: {danger}; border-color: {hex_at(danger, 0.30)}; }}

button {{
    background: rgba(148,163,184,0.07);
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 999px; padding: 5px 14px;
    color: {text};
}}
button:hover {{
    background: {a_dim}; border-color: {a_border}; color: {a};
}}
button.suggested-action {{
    background: {a_dim}; border-color: {a_border}; color: {a};
    font-weight: bold;
}}
button.destructive-action {{
    background: rgba(248,113,113,0.10); border-color: rgba(248,113,113,0.35);
    color: {danger};
}}
switch {{ background: rgba(148,163,184,0.16); }}
switch:checked {{ background: {a}; }}
spinbutton, entry, combobox box {{
    background: rgba(0,0,0,0.35); color: {text};
    border: 1px solid rgba(148,163,184,0.18); border-radius: 8px;
}}
""".encode()


_applied = False


def apply_theme() -> None:
    """Install the AURORA provider on the default screen (idempotent)."""
    global _applied
    if _applied:
        return
    from gi.repository import Gtk, Gdk
    
    # Enable GNOME native dark theme
    settings = Gtk.Settings.get_default()
    if settings:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    prov = Gtk.CssProvider()
    prov.load_from_data(gtk_css())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), prov,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _applied = True
