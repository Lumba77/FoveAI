#!/usr/bin/env python3
"""FoveAI_Studio.py — FoveAI Settings Studio (GTK3).

The tray's control surface as a real app: pavucontrol-style tabs with
dials, sliders, LCD readouts and buttons. Click the tray icon → this
window as a normal taskbar app. Close = hide to tray (tray persists).

Tabs:
  Fleet    — service grid + start/stop/restart + GPU LCD
  Audio    — voice mic/tts toggles, Kokoro voice, speech rate dials
  Memory   — proxy aggression dial, ctx windows, preserve-last
  Model    — active model, thinking toggle, deep-think, cloud mode
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path
import asyncio
import json
import websockets

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402
import cairo  # noqa: E402

import sys
sys.path.insert(0, "/home/lumba/FoveAI")
from theme.aurora_tokens import apply_theme  # noqa: E402

PROXY_BASE = "http://127.0.0.1:8400"
TIMEOUT = 4

# ── the 10-trait ring — ported from trackball/useTraits.ts ─────────────
# each trait: id, label, env key (None = cosmetic/local), options or range
RING: list[dict] = [
    {"id": "mode",     "label": "MODE",     "key": "XRLF_COGNITIVE_MODE",
     "options": ["local", "cloud", "juggle"]},
    {"id": "think",    "label": "REASON",   "key": "XRLF_MODEL_THINKING",
     "options": ["false", "true"]},
    {"id": "compress", "label": "COMPRESS", "key": "XRLF_PROXY_AGGRESSION",
     "min": 0, "max": 5, "step": 1},
    {"id": "keep",     "label": "KEEP",     "key": "XRLF_CLOUD_PRESERVE_LAST",
     "min": 0, "max": 64, "step": 4},
    {"id": "cadence",  "label": "CADENCE",  "key": "FOVEA_COMPRESS_EVERY",
     "min": 2, "max": 64, "step": 2},
    {"id": "tokcap",   "label": "TOK CAP",  "key": "XRLF_CLOUD_MAX_TOKENS_CAP",
     "min": 0, "max": 32768, "step": 2048},
    {"id": "ctx",      "label": "CTX",      "key": "XRLF_SPOOF_CONTEXT_WINDOW",
     "options": ["8192", "16384", "32768", "65536", "131072"]},
    {"id": "voice",    "label": "VOICE",    "key": "XRLF_VOICE_ENABLED",
     "options": ["true", "false"]},
    {"id": "mic",      "label": "MIC",      "key": "XRLF_MIC_ENABLED",
     "options": ["false", "true"]},
    {"id": "finish",   "label": "FINISH",   "key": None,
     "options": ["brass", "gunmetal", "copper", "chrome"]},
]
FINISH_TINT = {
    "brass": (1.0, 0.72, 0.20), "gunmetal": (0.60, 0.64, 0.68),
    "copper": (0.88, 0.54, 0.31), "chrome": (0.81, 0.89, 0.92),
}


def api_get_setting(key: str) -> str | None:
    import json as _json
    import urllib.request as _u
    try:
        with _u.urlopen(f"{PROXY_BASE}/api/setting?key={key}", timeout=TIMEOUT) as r:
            return str(_json.load(r).get("value") or "")
    except Exception:
        return None


def api_set_setting(key: str, val: str) -> bool:
    import json as _json
    import urllib.request as _u
    body = _json.dumps({"key": key, "val": val}).encode()
    req = _u.Request(f"{PROXY_BASE}/api/setting", data=body,
                     headers={"Content-Type": "application/json"})
    try:
        with _u.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


def _fmt(v: str) -> str:
    return {"true": "ON", "false": "OFF"}.get(v, v.upper())


def _norm(tr: dict, v: str) -> float:
    if tr.get("options"):
        opts = tr["options"]
        i = opts.index(v) if v in opts else 0
        return i / max(1, len(opts) - 1)
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    lo, hi = tr["min"], tr["max"]
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def _bump(tr: dict, v: str, d: int) -> str:
    if tr.get("options"):
        opts = tr["options"]
        i = opts.index(v) if v in opts else 0
        return opts[(i + d) % len(opts)]
    try:
        x = float(v) if v else tr["min"]
    except (TypeError, ValueError):
        x = tr["min"]
    x = min(tr["max"], max(tr["min"], x + d * tr["step"]))
    return str(int(x)) if float(x).is_integer() else str(x)

FOVEAI_DIR = Path("/home/lumba/FoveAI")
ENV_PATH = FOVEAI_DIR / ".env"

FLEET: list[tuple[str, int, str]] = [
    ("Foveated Proxy", 8400, "foveai-backend"),
    ("XRLF Runtime", 8402, "foveai-xrlf"),
    ("WS-IPC", 8403, "foveai-xrlf"),
    ("Dashboard", 8414, "foveai-xrlf"),
    ("Soul", 8405, "foveai-soul"),
    ("TTS", 8411, "foveai-tts"),
    ("Relay", 8413, "foveai-relay"),
    ("Creative", 8412, "foveai-creative"),
    ("STT", 8401, "foveai-stt"),
    ("Llama Core", 8407, "foveai-llama-core"),
    ("Llama 9B", 8408, "foveai-llama-9b"),
    ("Llama Draft", 8406, "foveai-llama-draft"),
    ("Multigate", 5177, "multigate"),
    ("XR Vessel", 5176, "xr-vessel"),
]



def port_up(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.35)
        return s.connect_ex(("127.0.0.1", port)) == 0


def systemctl(action: str, *units: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(["systemctl", action, *units],
                           capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            return True, ""
        r2 = subprocess.run(["sudo", "-n", "systemctl", action, *units],
                            capture_output=True, text=True, timeout=90)
        return r2.returncode == 0, (r2.stderr or r.stderr or "").strip()[:200]
    except Exception as e:
        return False, str(e)[:200]


# ── local cosmetic storage (FINISH dial) — mirrors localStorage in web ──
_LS = Path("/home/lumba/FoveAI/.foveai_studio_local.json")


def localStorage_get(key: str) -> str:
    try:
        import json
        d = json.loads(_LS.read_text())
        return d.get(key, "brass" if key == "finish" else "")
    except Exception:
        return "brass" if key == "finish" else ""


def localStorage_set(key: str, val: str) -> None:
    try:
        import json
        d = json.loads(_LS.read_text()) if _LS.exists() else {}
        d[key] = val
        _LS.write_text(json.dumps(d))
    except Exception:
        pass


class Lcd(Gtk.Label):
    """Pavucontrol-ish LCD chip: green ok / amber warn / red down."""

    def __init__(self, text: str = "", mood: str = "ok"):
        super().__init__(label=text)
        self.set_mood(mood)
        self.set_halign(Gtk.Align.START)

    def set_mood(self, mood: str) -> None:
        st = self.get_style_context()
        for c in ("lcd", "amber", "red"):
            st.remove_class(c)
        st.add_class("lcd")
        if mood == "warn":
            st.add_class("amber")
        elif mood == "down":
            st.add_class("red")


class Dial(Gtk.SpinButton):
    """Numeric dial with label + optional env key persistence."""

    def __init__(self, label: str, lo: float, hi: float, step: float,
                 value: float, env_key: str | None = None,
                 digits: int = 0):
        super().__init__()
        self.env_key = env_key
        self.set_range(lo, hi)
        self.set_increments(step, step * 5)
        self.set_digits(digits)
        self.set_value(value)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=label)
        lab.set_xalign(0.0)
        lab.set_size_request(190, -1)
        box.pack_start(lab, False, False, 2)
        box.pack_start(self, False, False, 2)
        self._box = box
        if env_key:
            self.connect("value-changed", self._persist)

    def _persist(self, *_):
        if not self.env_key:
            return
        v = self.get_value()
        s = str(int(v)) if self.get_digits() == 0 else f"{v}"
        write_env(self.env_key, s)

    @property
    def widget(self) -> Gtk.Widget:
        return self._box


class Toggle(Gtk.Switch):
    """Labeled boolean switch bound to an env key."""

    def __init__(self, label: str, value: bool, env_key: str | None = None):
        super().__init__()
        self.env_key = env_key
        self.set_active(value)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=label)
        lab.set_xalign(0.0)
        lab.set_size_request(190, -1)
        box.pack_start(lab, False, False, 2)
        box.pack_start(self, False, False, 2)
        self._box = box
        if env_key:
            self.connect("notify::active", self._persist)

    def _persist(self, *_):
        if self.env_key:
            write_env(self.env_key, "true" if self.get_active() else "false")

    @property
    def widget(self) -> Gtk.Widget:
        return self._box


# ── .env helpers (single-key rewrite; never dump values) ────────────────
def read_env() -> dict[str, str]:
    out = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def write_env(key: str, value: str) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    pat = re.compile(rf"^#?\s*{re.escape(key)}=")
    replaced = False
    for i, line in enumerate(lines):
        if pat.match(line):
            lines[i] = f"{key}={value}"
            replaced = True
    if not replaced:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


# ── the studio window ───────────────────────────────────────────────────
class Studio(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="FoveAI Studio — Fleet Control")
        self.set_default_size(760, 700)
        self.connect("delete-event", self._on_close)

        apply_theme()  # AURORA — canonical theme engine tokens

        self._rows = {}
        self._build()
        self._tick()
        GLib.timeout_add_seconds(3, self._tick)

        # Dynamic Theme setup
        self._css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        threading.Thread(target=self._start_theme_listener, daemon=True).start()

    def _start_theme_listener(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._theme_ws_loop())

    async def _theme_ws_loop(self) -> None:
        uri = "ws://127.0.0.1:8415/ws/theme"
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if data.get("type") == "theme_update" and data.get("theme"):
                            GLib.idle_add(self._apply_dynamic_theme, data["theme"])
            except Exception:
                await asyncio.sleep(3)

    def _apply_dynamic_theme(self, theme_data: dict) -> None:
        # Generate GTK CSS based on the incoming theme_data dict.
        bg = theme_data.get("fv_bg_dark", "#1E1E1E")
        bg_mid = theme_data.get("fv_bg_panel", "#2D2D2D")
        accent = theme_data.get("fv_accent", "#00A3FF")
        text = theme_data.get("fv_text_main", "#E0E0E0")
        text_dim = theme_data.get("fv_text_muted", "#888888")
        danger = theme_data.get("fv_danger", "#ff4444")
        warn = theme_data.get("fv_warn", "#ffaa00")

        css = f"""
        window, dialog, box {{
            background-color: {bg};
            color: {text};
        }}
        label {{
            color: {text};
        }}
        .dim-label {{
            color: {text_dim};
        }}
        .top-settings-menu {{
            background-color: {bg_mid};
            border-bottom: 1px solid {accent};
        }}
        stacksidebar list {{
            background-color: {bg};
        }}
        stacksidebar row {{
            padding: 10px;
            color: {text_dim};
        }}
        stacksidebar row:selected {{
            background-color: {bg_mid};
            color: {text};
            border-left: 3px solid {accent};
        }}
        notebook tab {{
            color: {text_dim};
        }}
        notebook tab:checked {{
            color: {accent};
        }}
        button {{
            background-color: {bg_mid};
            color: {text};
            border: 1px solid rgba(148,163,184,0.16);
            border-radius: 999px;
            padding: 5px 14px;
        }}
        button:hover {{
            background-color: {bg};
            border-color: {accent};
            color: {accent};
        }}
        button.suggested-action {{
            background-color: {bg_mid};
            color: {accent};
            border-color: {accent};
            font-weight: bold;
        }}
        button.destructive-action {{
            color: {danger};
            border-color: {danger};
        }}
        spinbutton, entry, combobox box {{
            background: rgba(0,0,0,0.35); 
            color: {text};
        }}
        .lcd {{
            color: {accent}; 
            background: rgba(0,0,0,0.5);
            border: 1px solid {accent};
        }}
        .lcd.amber {{ color: {warn}; border-color: {warn}; }}
        .lcd.red   {{ color: {danger}; border-color: {danger}; }}
        switch:checked {{ background: {accent}; }}
        """
        try:
            self._css_provider.load_from_data(css.encode('utf-8'))
        except Exception as e:
            print(f"Error applying dynamic theme: {e}")

    # ────────────────────────────────────────────────────────── build ──
    def _build(self) -> None:
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Top Settings Menu
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top_bar.get_style_context().add_class("top-settings-menu")
        
        title_lbl = Gtk.Label()
        title_lbl.set_markup("<b>FoveAI Dashboard</b>")
        title_lbl.set_margin_start(16)
        title_lbl.set_margin_top(12)
        title_lbl.set_margin_bottom(12)
        top_bar.pack_start(title_lbl, False, False, 0)
        
        main_box.pack_start(top_bar, False, False, 0)
        
        # Content Area: Sidebar + Stack
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        self.stack.set_transition_duration(250)
        
        self.sidebar = Gtk.StackSidebar()
        self.sidebar.set_stack(self.stack)
        self.sidebar.set_size_request(160, -1)
        
        self.stack.add_titled(self._tab_fleet(), "fleet", "Fleet")
        self.stack.add_titled(self._tab_ring(), "ring", "Dial Ring")
        self.stack.add_titled(self._tab_ops(), "ops", "Operations")
        self.stack.add_titled(self._tab_audio(), "audio", "Audio")
        self.stack.add_titled(self._tab_memory(), "memory", "Memory")
        self.stack.add_titled(self._tab_model(), "model", "Model")
        
        content_box.pack_start(self.sidebar, False, False, 0)
        
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        content_box.pack_start(sep, False, False, 0)
        
        content_box.pack_start(self.stack, True, True, 0)
        
        main_box.pack_start(content_box, True, True, 0)
        
        self.add(main_box)

    # ──────────────────────────────────────────────────── operations ──
    # One app runs the whole FoveAI surface: the foveai.sh flags, the tray
    # guardian actions, and the web UIs — as buttons.
    def _tab_ops(self) -> Gtk.Widget:
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vb.set_margin_top(12); vb.set_margin_bottom(12)
        vb.set_margin_start(12); vb.set_margin_end(12)

        def section(title: str) -> Gtk.Label:
            l = Gtk.Label()
            l.set_markup(f"<b>{title}</b>")
            l.set_halign(Gtk.Align.START)
            return l

        def btnrow(rows):
            bb = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
            bb.set_layout(Gtk.ButtonBoxStyle.EXPAND)
            for label, fn, cls in rows:
                b = Gtk.Button(label=label)
                if cls:
                    b.get_style_context().add_class(cls)
                b.connect("clicked", self._safe, fn)
                bb.add(b)
            return bb

        vb.pack_start(section("Stack — foveai.sh / sleipnir"), False, False, 0)
        vb.pack_start(btnrow((
            ("🚀 Full stack", self._sh("foveai.sh", "start"), "suggested-action"),
            ("🎙️ Light stack", self._sh("foveai.sh", "--light"), None),
            ("⏹ Stop", self._sh("foveai.sh", "stop"), "destructive-action"),
            ("🔍 Status", self._sh("foveai.sh", "--status"), None),
        )), False, False, 0)

        vb.pack_start(section("Guardian — RAM / VRAM"), False, False, 0)
        vb.pack_start(btnrow((
            ("🧹 Free RAM + flush", self._sh("_free_ram"), None),
            ("💎 Unload model (free VRAM)", self._sh("_unload_vram"), None),
        )), False, False, 0)

        vb.pack_start(section("Web UIs"), False, False, 0)
        vb.pack_start(btnrow((
            ("🌐 Multigate", self._web("http://localhost:5177"), None),
            ("🧭 XR Vessel", self._web("http://localhost:5176"), None),
            ("📊 Memory dash", self._web("http://localhost:8414/memory"), None),
            ("🖼️ Gallery", self._web("http://localhost:8400/api/tools/images"), None),
        )), False, False, 0)

        vb.pack_start(section("Terminal UIs / helpers"), False, False, 0)
        vb.pack_start(btnrow((
            ("📺 Nest", self._sh("foveai.sh", "nest"), None),
            ("🖥️ Console", self._sh("foveai.sh", "console"), None),
            ("📦 APK server", self._sh("foveai.sh", "--apk"), None),
        )), False, False, 0)

        self.ops_lcd = Lcd("ready", "ok")
        vb.pack_start(self.ops_lcd, False, False, 0)
        return vb

    def _safe(self, _btn, fn) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            if getattr(self, "ops_lcd", None):
                self.ops_lcd.set_text(f"error: {e}")
                self.ops_lcd.set_mood("down")

    def _sh(self, script: str, *args: str):
        """foveai.sh flag in a thread (or a guardian helper by name)."""
        def run() -> None:
            if script == "_free_ram":
                self._free_ram()
                return
            if script == "_unload_vram":
                self._unload_vram()
                return
            cmdline = ["/usr/bin/env", "bash", str(FOVEAI_DIR / script), *args]
            if args and args[0] in ("nest", "console"):
                # terminal UIs need a real terminal window from a GUI app
                term = ("gnome-terminal -- /bin/bash -lc "
                        f"'cd {FOVEAI_DIR} && bash {FOVEAI_DIR / script}'")
                subprocess.Popen(["/bin/bash", "-c", term],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                if getattr(self, "ops_lcd", None):
                    GLib.idle_add(self.ops_lcd.set_text, f"{args[0]} in terminal")
                    GLib.idle_add(self.ops_lcd.set_mood, "ok")
                return
            r = subprocess.run(cmdline, capture_output=True, text=True,
                               timeout=240, cwd=str(FOVEAI_DIR))
            tail = (r.stdout or r.stderr or "").strip().splitlines()[-3:]
            if getattr(self, "ops_lcd", None):
                GLib.idle_add(self.ops_lcd.set_text, " · ".join(tail)[-160:])
                GLib.idle_add(self.ops_lcd.set_mood,
                              "ok" if r.returncode == 0 else "down")
        return lambda: threading.Thread(target=run, daemon=True).start()

    def _free_ram(self) -> None:
        subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
        subprocess.run(["pkill", "-f", "run_xrlf"], capture_output=True)
        try:
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("3")
        except Exception:  # noqa: BLE001
            pass
        if getattr(self, "ops_lcd", None):
            self.ops_lcd.set_text("RAM liberated, caches flushed")
            self.ops_lcd.set_mood("ok")

    def _unload_vram(self) -> None:
        import urllib.request as _u
        try:
            _u.urlopen(f"{PROXY_BASE}/api/unload_models", timeout=6)
        except Exception:  # noqa: BLE001
            subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
        if getattr(self, "ops_lcd", None):
            self.ops_lcd.set_text("VRAM unload requested")
            self.ops_lcd.set_mood("ok")

    def _web(self, url: str):
        def open_url() -> None:
            subprocess.Popen(["xdg-open", url],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return open_url

    def _tab_ring(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        outer.set_margin_top(16); outer.set_margin_bottom(16)
        outer.set_margin_start(16); outer.set_margin_end(16)
        outer.set_halign(Gtk.Align.CENTER)

        # ── the bolted metal ring (cairo) ──
        self.ring_vals: dict[str, str] = {}
        self.ring_armed = 2  # COMPRESS by default, like the trackball
        zone = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.drawing = Gtk.DrawingArea()
        self.drawing.set_size_request(400, 400)
        self.drawing.set_halign(Gtk.Align.CENTER)
        self.drawing.set_valign(Gtk.Align.START)
        self.drawing.connect("draw", self._ring_draw)
        self.drawing.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.drawing.connect("button-press-event", self._ring_click)
        zone.pack_start(self.drawing, False, False, 0)
        outer.pack_start(zone, False, False, 0)

        # ── control cluster: the ARMED dial's settings live RIGHT NEXT to
        # the ring — one compact card per armed position ──
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(240, -1)

        armed_head = Gtk.Label()
        armed_head.set_markup("<b>ARMED DIAL</b>")
        armed_head.set_halign(Gtk.Align.START)
        card.pack_start(armed_head, False, False, 0)

        # LCD tightly coupled with the big −/+ dials beneath it
        self.ring_lcd = Lcd("…", "ok")
        card.pack_start(self.ring_lcd, False, False, 0)

        stepbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        minus = Gtk.Button(label="−  turn")
        minus.set_hexpand(True)
        minus.connect("clicked", self._ring_turn, -1)
        stepbox.pack_start(minus, True, True, 0)
        plus = Gtk.Button(label="turn  +")
        plus.set_hexpand(True)
        plus.get_style_context().add_class("suggested-action")
        plus.connect("clicked", self._ring_turn, +1)
        stepbox.pack_start(plus, True, True, 0)
        card.pack_start(stepbox, False, False, 0)

        # per-position quick index (all 10, one-line each = the dial list)
        idx_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ring_rows: list[Gtk.Button] = []
        for i, tr in enumerate(RING):
            b = Gtk.Button(label=f"◈ {tr['label']}")
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.set_halign(Gtk.Align.START)
            b.connect("clicked", self._ring_arm, i)
            self.ring_rows.append(b)
            idx_list.pack_start(b, False, False, 0)
        frame = Gtk.Frame()
        frame.add(idx_list)
        card.pack_start(frame, True, True, 8)

        hint = Gtk.Label()
        hint.set_markup("<small>click ring or list to arm · −/+ turn ·\nlive via :8400/api/setting</small>")
        hint.set_justify(Gtk.Justification.LEFT)
        hint.set_halign(Gtk.Align.START)
        card.pack_start(hint, False, False, 2)

        outer.pack_start(card, False, False, 0)

        self._ring_reload()
        return outer

    def _ring_arm(self, _btn, i: int) -> None:
        self.ring_armed = i
        self._ring_update_lcd()
        self.drawing.queue_draw()

    # ───────────────────────────────────────────────── ring internals ──
    def _ring_reload(self) -> None:
        for tr in RING:
            if tr["key"]:
                self.ring_vals[tr["id"]] = api_get_setting(tr["key"]) or ""
            else:
                self.ring_vals[tr["id"]] = localStorage_get("finish")
        self.drawing.queue_draw()
        self._ring_update_lcd()

    def _ring_update_lcd(self) -> None:
        tr = RING[self.ring_armed]
        v = self.ring_vals.get(tr["id"], "") or "—"
        self.ring_lcd.set_text(f"◈ {tr['label']}  =  {_fmt(v)}")
        self.ring_lcd.set_mood("ok")
        # tint the armed row in the quick list
        for i, b in enumerate(getattr(self, "ring_rows", [])):
            ctx = b.get_style_context()
            ctx.remove_class("suggested-action")
            if i == self.ring_armed:
                ctx.add_class("suggested-action")

    def _ring_turn(self, _btn, d: int) -> None:
        tr = RING[self.ring_armed]
        nv = _bump(tr, self.ring_vals.get(tr["id"], ""), d)
        self.ring_vals[tr["id"]] = nv
        if tr["key"]:
            api_set_setting(tr["key"], nv)
        else:
            localStorage_set("finish", nv)
        self.drawing.queue_draw()
        self._ring_update_lcd()

    def _ring_click(self, _da, event) -> None:
        alloc = self.drawing.get_allocation()
        cx = cy = alloc.width / 2
        dx, dy = event.x - cx, event.y - cy
        ang = (Math.atan2 if False else __import__("math").atan2)(dy, dx)
        deg = __import__("math").degrees(ang) + 90  # 0 at top
        if deg < 0:
            deg += 360
        idx = round(deg / 36) % 10
        tr = RING[idx]
        if abs(deg - idx * 36) < 16 or idx == self.ring_armed:
            self.ring_armed = idx
            self._ring_update_lcd()
            self.drawing.queue_draw()

    def _ring_draw(self, _da, cr) -> None:
        m = __import__("math")
        alloc = self.drawing.get_allocation()
        w = h = min(alloc.width, alloc.height)
        cx = cy = alloc.width / 2
        # R sized so the meter ring (0.86R) + labels always fit inside:
        # R*(0.86) + line-width margin + label radius stays < min(w,h)/2
        R = w * 0.36

        # core disc
        cr.arc(cx, cy, R * 0.52, 0, 2 * m.pi)
        cr.set_source_rgb(0.04, 0.07, 0.06)
        cr.fill_preserve()
        cr.set_source_rgb(0.12, 0.20, 0.16)
        cr.set_line_width(2)
        cr.stroke()

        # finishing tint from the FINISH dial
        fr = FINISH_TINT.get(self.ring_vals.get("finish", "brass"),
                             FINISH_TINT["brass"])

        for i, tr in enumerate(RING):
            a = m.radians(-90 + i * 36)
            px, py = cx + R * m.cos(a), cy + R * m.sin(a)
            armed = i == self.ring_armed
            # tick dot
            cr.arc(px, py, R * (0.075 if armed else 0.055), 0, 2 * m.pi)
            v = self.ring_vals.get(tr["id"], "")
            frac = _norm(tr, v) if v else 0.0
            if armed:
                cr.set_source_rgb(*fr)
            else:
                cr.set_source_rgb(0.35, 0.38, 0.42)
            cr.fill()
            # dial-meter arc
            cr.arc(cx, cy, R * 0.86, a - m.radians(14), a + m.radians(14))
            cr.set_line_width(4)
            cr.set_source_rgba(*fr, 0.18 + 0.62 * frac
                               if armed else 0.10 + 0.25 * frac)
            cr.stroke()
            # label
            cr.set_source_rgb(0.85, 0.87, 0.80 if armed else 0.55)
            cr.set_font_size(10 if armed else 8.5)
            lx, ly = cx + (R + 16) * m.cos(a), cy + (R + 16) * m.sin(a)
            ext = cr.text_extents(tr["label"])
            cr.move_to(lx - ext.width / 2, ly + ext.height / 2)
            cr.show_text(tr["label"])

        # center LCD-ish readout
        tr = RING[self.ring_armed]
        v = _fmt(self.ring_vals.get(tr["id"], "") or "—")
        cr.set_source_rgb(*fr)
        cr.set_font_size(15)
        ext = cr.text_extents(v)
        cr.move_to(cx - ext.width / 2, cy + 4)
        cr.show_text(v)

    def _tab_fleet(self) -> Gtk.Widget:
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vb.set_margin_top(12); vb.set_margin_bottom(12)
        vb.set_margin_start(12); vb.set_margin_end(12)

        # LCD GPU strip
        self.gpu_lcd = Lcd("GPU …", "ok")
        vb.pack_start(self.gpu_lcd, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=3)
        for col, head in enumerate(("Service", "Port", "State", "Unit")):
            l = Gtk.Label(label=f"<b>{head}</b>", use_markup=True)
            if head in ("Service", "Unit"):
                l.set_halign(Gtk.Align.START)
            grid.attach(l, col, 0, 1, 1)
        for r, (name, port, unit) in enumerate(FLEET, start=1):
            grid.attach(Gtk.Label(label=name, xalign=0.0), 0, r, 1, 1)
            grid.attach(Gtk.Label(label=f":{port}"), 1, r, 1, 1)
            st = Lcd("…", "ok"); st.set_halign(Gtk.Align.START)
            self._rows[(*(), )] = None  # placeholder to appease linters
            self._rows[r] = st
            grid.attach(st, 2, r, 1, 1)
            u = Gtk.Label(label=unit, xalign=0.0)
            u.get_style_context().add_class("dim-label")
            grid.attach(u, 3, r, 1, 1)
        vb.pack_start(grid, True, True, 0)

        btns = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        btns.set_layout(Gtk.ButtonBoxStyle.EXPAND)
        for label, cb, cls in (
                ("▶  Start all", self._act_start, "suggested-action"),
                ("■  Stop all", self._act_stop, "destructive-action"),
                ("↻  Restart all", self._act_restart, None)):
            b = Gtk.Button(label=label)
            if cls:
                b.get_style_context().add_class(cls)
            b.connect("clicked", cb)
            btns.add(b)
        vb.pack_start(btns, False, False, 0)
        self.note = Lcd("", "ok")
        vb.pack_start(self.note, False, False, 0)
        return vb

    def _tab_audio(self) -> Gtk.Widget:
        env = read_env()
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vb.set_margin_top(12); vb.set_margin_bottom(12)
        vb.set_margin_start(12); vb.set_margin_end(12)

        vb.pack_start(Lcd("Voice pipeline — TTS Kokoro :8411 · STT :8411 (WS)",
                          "ok"), False, False, 0)
        vb.pack_start(Toggle(
            "Voice enabled", self._b(env, "FoveAI_VOICE_ENABLED"),
            "FoveAI_VOICE_ENABLED").widget, False, False, 0)
        vb.pack_start(Toggle(
            "Microphone enabled", self._b(env, "FoveAI_MIC_ENABLED"),
            "FoveAI_MIC_ENABLED").widget, False, False, 0)
        vb.pack_start(Toggle(
            "Push-to-talk", self._b(env, "FoveAI_MIC_PTT"),
            "FoveAI_MIC_PTT").widget, False, False, 0)
        vb.pack_start(Toggle(
            "Global vocal mode (hold L-CTRL anywhere — foveai_ptt daemon)",
            os.path.exists("/home/lumba/.config/systemd/user/foveai-ptt.service"),
            None).widget, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(sep, False, False, 4)

        voices = ("af_heart", "af_nova", "am_onyx", "bf_emma", "bm_george")
        vb.pack_start(self._combo("Kokoro voice", voices,
                                  env.get("FoveAI_KOKORO_VOICE",
                                          env.get("FOVEAI_KOKORO_VOICE", "af_heart")),
                                  "FoveAI_KOKORO_VOICE"), False, False, 2)

        vb.pack_start(self._combo("TTS provider", ("kokoro", "edge", "piper"),
                                  env.get("FoveAI_TTS_PROVIDER", "kokoro"),
                                  "FoveAI_TTS_PROVIDER"), False, False, 2)
        vb.pack_start(self._combo("STT provider", ("whisper", "webvm"),
                                  env.get("FoveAI_STT_PROVIDER", "whisper"),
                                  "FoveAI_STT_PROVIDER"), False, False, 2)
        return vb

    def _tab_memory(self) -> Gtk.Widget:
        env = read_env()
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vb.set_margin_top(12); vb.set_margin_bottom(12)
        vb.set_margin_start(12); vb.set_margin_end(12)

        vb.pack_start(Lcd("Foveated memory proxy — compression & context", "ok"),
                      False, False, 0)
        vb.pack_start(Dial(
            "Proxy aggression (0–5)", 0, 5, 1,
            float(env.get("XRLF_PROXY_AGGRESSION",
                          env.get("FOVEAI_PROXY_AGGRESSION", "3"))),
            "XRLF_PROXY_AGGRESSION").widget, False, False, 2)
        vb.pack_start(Dial(
            "CTX max chars", 1000, 64000, 500,
            float(env.get("XRLF_CTX_MAX_CHARS", "16000")),
            "XRLF_CTX_MAX_CHARS").widget, False, False, 2)
        vb.pack_start(Dial(
            "CTX min chars", 500, 8000, 250,
            float(env.get("XRLF_CTX_MIN_CHARS", "4000")),
            "XRLF_CTX_MIN_CHARS").widget, False, False, 2)
        vb.pack_start(Dial(
            "Cloud preserve-last turns", 0, 64, 1,
            float(env.get("FOVEAI_CLOUD_PRESERVE_LAST", "8")),
            "FOVEAI_CLOUD_PRESERVE_LAST").widget, False, False, 2)
        vb.pack_start(Toggle(
            "Adaptive n_ctx", self._b(env, "FOVEAI_ADAPTIVE_N_CTX"),
            "FOVEAI_ADAPTIVE_N_CTX").widget, False, False, 2)
        return vb

    def _tab_model(self) -> Gtk.Widget:
        env = read_env()
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vb.set_margin_top(12); vb.set_margin_bottom(12)
        vb.set_margin_start(12); vb.set_margin_end(12)

        persona_opts = (
            "gemma-4-e2b-multimodal-v1.0.xrlf",
            "gemma-4-12b-mtp-xrlf-3.0.xrlf",
            "qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
            "smolvlm2-500m-multimodal-v1.0.xrlf"
        )
        router_opts = (
            "foveai-omni-router-v2.xrlf",
            "foveai-omni-router.xrlf"
        )

        active = env.get("FOVEAI_MODEL_ACTIVE_ID", "gemma-4-e2b-multimodal-v1.0.xrlf")
        vb.pack_start(self._combo("Persona AI", persona_opts, active, "FOVEAI_MODEL_ACTIVE_ID"), False, False, 2)
        
        router = env.get("FOVEAI_OMNI_ROUTER_MODEL", "foveai-omni-router-v2.xrlf")
        vb.pack_start(self._combo("Router AI", router_opts, router, "FOVEAI_OMNI_ROUTER_MODEL"), False, False, 2)

        vb.pack_start(self._combo("Chat provider",
                                  ("local", "cloud", "nvidia", "juggle"),
                                  env.get("FOVEAI_CHAT_PROVIDER",
                                          env.get("FoveAI_CHAT_PROVIDER", "local")),
                                  "FOVEAI_CHAT_PROVIDER"), False, False, 2)
        vb.pack_start(Toggle(
            "Model thinking", self._b(env, "FOVEAI_MODEL_THINKING"),
            "FOVEAI_MODEL_THINKING").widget, False, False, 2)
        vb.pack_start(Toggle(
            "Deep think default", self._b(env, "FOVEAI_DEEP_THINK_DEFAULT"),
            "FOVEAI_DEEP_THINK_DEFAULT").widget, False, False, 2)
        vb.pack_start(Dial(
            "Local n_ctx", 1024, 65536, 1024,
            float(env.get("FOVEAI_LOCAL_N_CTX", "4096")),
            "FOVEAI_LOCAL_N_CTX").widget, False, False, 2)
        self.active_disp = Lcd("Frontend UI: "
                               + env.get("XRLF_FRONTEND_UI_PRESET", "3d_avatar"),
                               "ok")
        vb.pack_start(self.active_disp, False, False, 2)
        return vb

    # ─────────────────────────────────────────────────────── widgets ──
    def _combo(self, label: str, options: tuple[str, ...], current: str,
               env_key: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=label)
        lab.set_xalign(0.0); lab.set_size_request(190, -1)
        combo = Gtk.ComboBoxText()
        for o in options:
            combo.append_text(o)
        if current in options:
            combo.set_active(options.index(current))
        combo.set_size_request(160, -1)
        combo.connect("changed", self._combo_changed, env_key)
        box.pack_start(lab, False, False, 2)
        box.pack_start(combo, False, False, 2)
        return box

    def _combo_changed(self, combo: Gtk.ComboBoxText, env_key: str) -> None:
        t = combo.get_active_text()
        if t:
            write_env(env_key, t)

    @staticmethod
    def _b(env: dict[str, str], key: str) -> bool:
        return env.get(key, "").lower() in ("1", "true", "yes")

    # ───────────────────────────────────────────────────────── actions ──
    @staticmethod
    def _act_start(_btn) -> None:
        threading.Thread(target=systemctl, args=("start", *ALL_UNITS),
                         daemon=True).start()

    @staticmethod
    def _act_stop(_btn) -> None:
        threading.Thread(target=systemctl, args=("stop", *ALL_UNITS),
                         daemon=True).start()

    @staticmethod
    def _act_restart(_btn) -> None:
        threading.Thread(target=systemctl, args=("restart", *ALL_UNITS),
                         daemon=True).start()

    # ─────────────────────────────────────────────────────────- refresh ──
    def _tick(self) -> bool:
        for r, (name, port, _unit) in enumerate(FLEET, start=1):
            lbl = self._rows.get(r)
            if not lbl:
                continue
            if port_up(port):
                lbl.set_mood("ok"); lbl.set_text("🟢 up")
            else:
                lbl.set_mood("down"); lbl.set_text("⚪ down")
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader"], capture_output=True, text=True, timeout=4)
            self.gpu_lcd.set_text(f"GPU {r.stdout.strip()}")
        except Exception:
            self.gpu_lcd.set_text("GPU n/a")
        return True

    def _on_close(self, *_):
        Gtk.main_quit()
        return False


ALL_UNITS = sorted({u for _, _, u in FLEET})


def main() -> None:
    w = Studio()
    w.connect("destroy", Gtk.main_quit)
    w.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()