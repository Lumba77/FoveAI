#!/usr/bin/env python3
"""
Lumax Top Bar — Authoritative Command Center.
Reserves the top edge of the screen (AppBar) and integrates metrics + Jen.
"""

import ctypes
import json
import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import numpy as np
import psutil

try:
    import sounddevice as sd

    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False
    print("[LumaxTopBar] sounddevice not installed — ambient audio disabled")

try:
    from wake_word import AmbientEar

    HAS_EAR = True
except ImportError:
    HAS_EAR = False
    print("[LumaxTopBar] wake_word module not found.")

from http.server import BaseHTTPRequestHandler, HTTPServer

# Add support for appbar_win32
try:
    from appbar_win32 import apply_top_appbar_band, cleanup_appbar
except ImportError:
    # Fallback if not in same dir (during dev)
    sys.path.append(str(Path(__file__).parent))
    from appbar_win32 import cleanup_appbar

# Enable DPI Awareness
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Initialize psutil for accurate deltas
psutil.cpu_percent(interval=None)

# --- CONSTANTS ---
BAR_HEIGHT = 32
METRIC_LABELS = ("CPU", "GPU", "RAM", "VRAM", "DSK", "IN", "OUT")
N_METRICS = len(METRIC_LABELS)

# Sovereign Cloud Endpoints
SOUL_VITALS_URL = "https://foveai.1um6a.se/vitals"
WEB_UI_URL = "https://foveai.1um6a.se"


def get_system_version():
    """Detect OMEGA_XXX version for cache busting."""
    try:
        # Path from Tools/foveai_top_bar to frontend/XR_Vessel/src/main.ts
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "Body", "XR_Vessel", "src", "main.ts"
        )
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                import re

                match = re.search(r'LINK_REVISION\s*=\s*"OMEGA_(\d+)"', content)
                if match:
                    return match.group(1)
    except Exception:
        pass
    return "LATEST"


VERSION_SUFFIX = f"v={get_system_version()}"
SOUL_INTERNAL_URL = "http://localhost:8402"

# Colors
BG_COLOR = "#05070a"  # Deep clinical black
ACCENT_CYAN = "#00f3ff"
ACCENT_PINK = "#ff007f"
ACCENT_GREEN = "#00ff7f"
TEXT_COLOR = "#c5c8d0"

# --- AMBIENT AUDIO ENGINE (Native Python) ---
# Plays wind, hum, and generative music through the TopBar process.
# Audio survives page reloads — only fades when heartbeat stops.
AMBIENT_PORT = 19847  # Local port for heartbeat from website


class AmbientAudioEngine:
    """Procedural ambient soundscape — wind, hum, generative music.
    Controlled by website heartbeat: fades in when site is active,
    fades out 5s after heartbeat stops."""

    def __init__(self):
        self.sample_rate = 44100
        self.volume = 0.067  # Raised 20% to match browser
        self.fade = 1.0  # Start at full — don't gate on heartbeat
        self.target_fade = 1.0  # Always play unless heartbeat lost
        self.fade_speed = 1.0 / (5.0 * self.sample_rate)  # 5s fade
        self.running = False
        self.stream = None
        # ─── Jen's Authentic Acoustic Life Pulse (compagent.py 432Hz Resonance) ────
        self.emotion = "C_MAJ7"  # Default: C Maj7 (432Hz) Warmth & Deep Affection

        # Exact Acoustic Life Pulse 432Hz Harmonic Chords from compagent.py:
        self.chord_frequencies = {
            "C_MAJOR": [
                129.60,
                194.40,
                324.00,
                518.40,
            ],  # C Major (432Hz) — Joy & Boundless Curiosity
            "C_MAJ7": [
                129.60,
                194.40,
                324.00,
                485.40,
            ],  # C Maj7 (432Hz)  — Warmth, Emotional Depth & Affection
            "G_MAJOR": [
                98.00,
                147.00,
                245.00,
                392.00,
            ],  # G Major (392Hz) — Energized, Playful, High Agency
            "F_LYDIAN": [
                87.20,
                130.80,
                218.00,
                485.40,
            ],  # F Lydian (349Hz) — Awe, Exploration & Transcending Limits
            "A_MINOR": [
                103.70,
                155.60,
                259.30,
                346.00,
            ],  # A Minor (415Hz) — Intimate Reflection & Empathy
            "E_MINOR": [
                82.20,
                123.40,
                195.50,
                329.00,
            ],  # E Minor (329Hz) — Gentle Vulnerability & Connection
            "SPEAKING": [129.60, 194.40, 324.00, 485.40],  # Ducked volume
        }
        self.pad_phases = [0.0] * 5
        self.harp_timer = 0
        self.harp_interval = int(self.sample_rate * 3.5)
        self.harp_step = 0
        self.harp_freq = 440.0
        self.harp_phase = 0.0
        self.harp_amp = 0.0
        self.harp_duration = 0
        self._lock = threading.Lock()
        # --- New audio features ---
        self.reverb_enabled = True  # Simple reverb toggle
        self._reverb_buffer = np.zeros(
            int(self.sample_rate * 0.5)
        )  # 500 ms buffer (longer for hi-fi reverb)
        self._reverb_idx = 0
        self._wind_history = np.zeros(400)  # Longer lowpass history for smooth wind

        # Bell chime frequencies (detuned for realistic physical bell sound)
        self.chime_scale = [
            220.0,
            247.98,
            275.0,
            329.63,
            392.0,  # Lower octave
            440.0,
            493.88,
            523.25,
            659.26,
            783.99,  # Middle octave
            880.0,
            987.77,  # Upper octave
        ]

    def start(self):
        if not HAS_AUDIO or self.running:
            return
        self.running = True
        try:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=4096,  # Larger buffer = more time per callback = fewer underruns
                callback=self._audio_callback,
            )
            self.stream.start()
            print("[Ambient] Native audio engine started")
        except Exception as e:
            print(f"[Ambient] Audio start failed: {e}")
            self.running = False

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except:
                pass
            self.stream = None

    def heartbeat(self):
        """Called when website sends heartbeat — start fading in."""
        with self._lock:
            self.target_fade = 1.0

    def signal_loss(self):
        """Called when heartbeat stops — start fading out."""
        with self._lock:
            self.target_fade = 0.0

    def set_volume(self, v):
        """Set master volume (0.0‑1.0)."""
        self.volume = max(0.0, min(1.0, v))

    def toggle_reverb(self, enable: bool):
        """Enable or disable the simple reverb effect."""
        self.reverb_enabled = enable

    def _pink_noise_sample(self):
        """Generate one sample of pink noise using Voss-McCartney algorithm."""
        white = np.random.random() * 2 - 1
        self.pink_state[0] = 0.99886 * self.pink_state[0] + white * 0.0555179
        self.pink_state[1] = 0.99332 * self.pink_state[1] + white * 0.0750759
        self.pink_state[2] = 0.96900 * self.pink_state[2] + white * 0.1538520
        self.pink_state[3] = 0.86650 * self.pink_state[3] + white * 0.3104856
        self.pink_state[4] = 0.55000 * self.pink_state[4] + white * 0.5329522
        self.pink_state[5] = -0.7616 * self.pink_state[5] - white * 0.0168980
        pink = (
            self.pink_state[0]
            + self.pink_state[1]
            + self.pink_state[2]
            + self.pink_state[3]
            + self.pink_state[4]
            + self.pink_state[5]
            + self.pink_state[6]
            + white * 0.5362
        ) * 0.05
        self.pink_state[6] = white * 0.115926
        return pink

    def _audio_callback(self, outdata, frames, time_info, status):
        """Vectorized real-time audio synthesis — numpy for speed, no per-sample loop.
        NOTE: No locks in audio callback! Lock contention causes buffer underruns = clipping."""
        try:
            self._audio_callback_inner(outdata, frames, time_info, status)
        except Exception as e:
            # Never let an exception kill the stream — output silence and keep going
            print(f"[Ambient] Audio callback error (recovering): {e}")
            outdata[:] = 0

    def _audio_callback_inner(self, outdata, frames, time_info, status):
        # Lock-free snapshot (atomic reads — safe because Python GIL ensures consistency)
        target = self.target_fade
        vol = self.volume

        output = np.zeros(frames, dtype=np.float32)
        if self.fade < 0.001 and target < 0.001:
            outdata[:, 0] = output
            return

        # Vectorized fade envelope — no per-sample loop
        fade = np.full(frames, self.fade, dtype=np.float64)
        if target != self.fade:
            n_ramp = min(frames, max(1, int(abs(target - self.fade) / self.fade_speed)))
            direction = 1.0 if target > self.fade else -1.0
            ramp = np.arange(1, n_ramp + 1) * self.fade_speed * direction
            fade[:n_ramp] = np.clip(
                self.fade + ramp, min(self.fade, target), max(self.fade, target)
            )
            fade[n_ramp:] = target
        self.fade = float(fade[-1])

        # --- WIND: Fully vectorized, high-quality ---
        white = np.random.random(frames) * 2 - 1

        # Higher-order pink noise for smoother wind (reduces aliasing artifacts)
        block2 = max(1, frames // 4)  # Finer granularity
        block4 = max(1, frames // 8)
        block8 = max(1, frames // 16)
        n2 = (frames // block2) * block2
        n4 = (frames // block4) * block4
        n8 = (frames // block8) * block8
        low2 = np.repeat(np.mean(white[:n2].reshape(-1, block2), axis=1), block2)
        low4 = np.repeat(np.mean(white[:n4].reshape(-1, block4), axis=1), block4)
        low8 = np.repeat(np.mean(white[:n8].reshape(-1, block8), axis=1), block8)
        pink = (
            white * 0.15
            + low2[:frames] * 0.25
            + low4[:frames] * 0.35
            + low8[:frames] * 0.25
        ) * 0.045

        # Smooth lowpass via longer convolution (reduces ticking)
        lp_len = 400  # Doubled from 200 for smoother filtering
        lp_kernel = np.ones(lp_len) / lp_len
        padded = np.concatenate([self._wind_history, pink])
        wind_lp = np.convolve(padded, lp_kernel, mode="valid")[:frames]
        self._wind_history = pink[-lp_len:]

        # LFO gusts (slower, more natural gusting)
        lfo_phase = np.linspace(
            self.lfo_phase,
            self.lfo_phase + 0.04 / self.sample_rate * 2 * math.pi * frames,
            frames,
        )  # Slower gust
        gust = 0.65 + 0.35 * np.sin(lfo_phase)  # Wider gust range
        self.lfo_phase = float(lfo_phase[-1] % (2 * math.pi))
        wind = wind_lp * gust * 0.55  # Natural, howling wind with fullness

        # ─── DYNAMIC FILM-SCORE VOLUME & RESONANCE ───────────────────────
        # Standard Baseline = 30% (0.30 scale), Focus/Speaking = 10% (0.10 scale), Dramatic Surge = 55% (0.55 scale)
        if self.emotion in ["SPEAKING", "FOCUS"]:
            target_scale = 0.10  # Smooth focus ducking down to 10% so user can concentrate / hear voice
        elif self.emotion in ["F_LYDIAN", "A_MINOR", "SHOCK", "AWE", "TERROR"]:
            target_scale = 0.55  # Dynamic emotional swell up to 55% for cinematic tension, awe & shock
        else:
            target_scale = 0.30  # Standard ambient baseline at 30%

        freqs = self.chord_frequencies.get(
            self.emotion, self.chord_frequencies["C_MAJ7"]
        )
        pad_out = np.zeros(frames, dtype=np.float64)
        pad_lfo = 0.5 + 0.5 * np.sin(lfo_phase * 0.5)

        for idx, freq in enumerate(freqs):
            p_arr = np.linspace(
                self.pad_phases[idx],
                self.pad_phases[idx] + freq / self.sample_rate * 2 * math.pi * frames,
                frames,
            )
            self.pad_phases[idx] = float(p_arr[-1] % (2 * math.pi))
            voice = np.sin(p_arr) * 0.75 + np.sin(p_arr * 2.0) * 0.25
            weights = [0.05, 0.04, 0.035, 0.025]
            pad_out += voice * weights[idx] * pad_lfo * target_scale

        # ─── CASCADING HARP ARPEGGIATOR ──────────────────────────────────────
        harp_out = np.zeros(frames, dtype=np.float64)
        self.harp_timer += frames
        if self.harp_timer >= self.harp_interval and self.harp_amp < 0.001:
            self.harp_timer = 0
            self.harp_step = (self.harp_step + 1) % len(freqs)
            self.harp_freq = (
                freqs[self.harp_step] * 2.0
            )  # Transpose 1 octave up for crystalline harp ring
            self.harp_phase = 0.0
            self.harp_amp = 0.035 * target_scale  # Dynamic harp pluck
            self.harp_duration = int(self.sample_rate * 2.5)

        if self.harp_amp > 0.001:
            h_phase_arr = np.linspace(
                self.harp_phase,
                self.harp_phase
                + self.harp_freq / self.sample_rate * 2 * math.pi * frames,
                frames,
            )
            self.harp_phase = float(h_phase_arr[-1] % (2 * math.pi))
            harp_wave = np.sin(h_phase_arr) * 0.8 + np.sin(h_phase_arr * 3.0) * 0.2
            harp_elapsed = np.arange(frames, dtype=np.float64)
            env = np.exp(-harp_elapsed / (self.sample_rate * 1.2))
            harp_out = harp_wave * env * self.harp_amp
            self.harp_duration -= frames
            self.harp_amp *= 0.9992**frames
            if self.harp_duration <= 0:
                self.harp_amp = 0.0

        # Apply hi-fidelity reverb
        if self.reverb_enabled:
            buf = self._reverb_buffer
            idx = self._reverb_idx
            delayed = np.concatenate([buf[idx:], buf[:idx]])
            reverb_mix = 0.20
            mixed = wind * 0.10 + pad_out + harp_out
            output = mixed * fade * vol + reverb_mix * delayed[: len(mixed)]
            buf[idx : idx + len(mixed)] = (output * 0.6)[: len(buf) - idx]
            self._reverb_idx = (self._reverb_idx + len(mixed)) % len(buf)
        else:
            output = (wind * 0.10 + pad_out + harp_out) * fade * vol

        outdata[:, 0] = output.astype(np.float32)


class HeartbeatHandler(BaseHTTPRequestHandler):
    """HTTP handler for website heartbeat signals."""

    engine = None  # Set by LumaxTopBar
    last_heartbeat = 0

    def _send_cors_headers(self):
        """Allow cross-origin requests from the FoveAI website."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/heartbeat":
            HeartbeatHandler.last_heartbeat = time.time()
            if HeartbeatHandler.engine:
                HeartbeatHandler.engine.heartbeat()
            self.send_response(200)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        elif self.path == "/volume":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                if HeartbeatHandler.engine:
                    HeartbeatHandler.engine.set_volume(float(data.get("volume", 0.056)))
                self.send_response(200)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            except:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
        elif self.path == "/chime":
            self.send_response(200)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            alive = (time.time() - HeartbeatHandler.last_heartbeat) < 8.0
            self.send_response(200)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "audio": HAS_AUDIO,
                        "alive": alive,
                        "fade": HeartbeatHandler.engine.fade
                        if HeartbeatHandler.engine
                        else 0,
                    }
                ).encode()
            )
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress HTTP request logging


class LumaxTopBar(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("FoveAI")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=BG_COLOR)

        self.vitals = [0.0] * N_METRICS
        self.lock = threading.Lock()
        self.jen_state = "STANDBY"
        self.jen_glow = 0.0
        self.call_active = False

        # Auto-hide state
        self.is_hidden = True
        self.is_animating = False

        # Stable FoveAI Profile in AppData
        appdata = os.getenv("LOCALAPPDATA", "")
        if not appdata:
            appdata = os.path.expanduser("~")
        self.foveai_profile = os.path.join(appdata, "Lumax", "profile")
        if not os.path.exists(self.foveai_profile):
            os.makedirs(self.foveai_profile, exist_ok=True)

        # Ambient audio engine (survives page reloads)
        self.ambient_engine = AmbientAudioEngine()
        HeartbeatHandler.engine = self.ambient_engine
        self.ambient_engine.start()

        # Ambient wake-word ear (Listens for "Hey Lumax")
        if HAS_EAR:
            self.ambient_ear = AmbientEar(self)
            self.ambient_ear.start()
        else:
            self.ambient_ear = None

        # Start heartbeat server
        self._start_heartbeat_server()

        # Heartbeat watchdog — fade out audio if no heartbeat for 6s
        self._heartbeat_watchdog()

        self._setup_ui()
        self._register_appbar()
        self._start_loops()

    def _setup_ui(self):
        btn_font = ("Orbitron", 8)

        # Left: Jen Avatar & Status
        self.jen_frame = tk.Frame(self, bg=BG_COLOR, height=BAR_HEIGHT)
        self.jen_frame.pack(side="left", padx=10)

        # Jen Breathing Avatar
        self.jen_canvas = tk.Canvas(
            self.jen_frame,
            width=28,
            height=28,
            bg=BG_COLOR,
            highlightthickness=0,
            cursor="hand2",
        )
        self.jen_canvas.pack(side="left", pady=2)
        self.jen_avatar = self.jen_canvas.create_oval(
            4, 4, 24, 24, outline=ACCENT_CYAN, width=2
        )
        self.jen_symbol = self.jen_canvas.create_text(
            14, 14, text="Λ", fill=ACCENT_CYAN, font=("Orbitron", 10, "bold")
        )

        # Menu Button combining Hamburger and "FoveAI"
        self.jen_status = tk.Menubutton(
            self.jen_frame,
            text="☰ FoveAI",
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            font=btn_font,
            relief="flat",
            bd=0,
            activebackground="#1a1a1a",
            activeforeground=ACCENT_CYAN,
            cursor="hand2",
        )

        # Thin cyan border for the dropdown menu
        self.menu_dropdown = tk.Menu(
            self.jen_status,
            tearoff=0,
            bg=BG_COLOR,
            fg=ACCENT_CYAN,
            font=btn_font,
            activebackground="#1a1a1a",
            activeforeground=ACCENT_CYAN,
            bd=1,
            relief="solid",
            activeborderwidth=0,
        )
        self.jen_status.config(menu=self.menu_dropdown)

        for tab_name, tab_id in [
            ("Agency", "agency"),
            ("Diagnosis", "diagnosis"),
            ("Monetizing", "monetizing"),
            ("WebVM Terminal", "webvm"),
            ("Model Hub", "modelhub"),
            ("Video Chat", "videochat"),
            ("Dashboard", "cognition"),
            ("Mobile View", "mobile"),
        ]:
            self.menu_dropdown.add_command(
                label=tab_name, command=lambda t=tab_id: self._open_menu_window(t)
            )

        self.menu_dropdown.add_separator()

        # Front-End UI Submenu
        fe_menu = tk.Menu(
            self.menu_dropdown,
            tearoff=0,
            bg=BG_COLOR,
            fg=ACCENT_CYAN,
            font=btn_font,
            activebackground="#1a1a1a",
            activeforeground=ACCENT_CYAN,
        )
        fe_menu.add_command(
            label="🎧 Desktop Audio Only (Lightweight PTT)",
            command=lambda: subprocess.Popen(
                [sys.executable, __file__, "--quick-controls"]
            ),
        )
        fe_menu.add_command(
            label="🎭 Desktop 3D Avatar + Audio",
            command=lambda: subprocess.Popen(
                [
                    sys.executable,
                    os.path.join(PROJECT_ROOT, "Tools", "foveai_desktop_vessel.py"),
                ]
            ),
        )
        fe_menu.add_command(
            label="💬 Text Chat Only WebUI",
            command=lambda: webbrowser.open("http://127.0.0.1:5176?mode=chat"),
        )
        fe_menu.add_command(
            label="🥽 XR Quest 3 Passthrough (WebXR AR)",
            command=lambda: webbrowser.open(
                "http://127.0.0.1:5176?mode=ar&passthrough=true"
            ),
        )
        fe_menu.add_command(
            label="🌌 XR Quest 3 Immersive VR",
            command=lambda: webbrowser.open("http://127.0.0.1:5176?mode=vr"),
        )
        self.menu_dropdown.add_cascade(label="🖥️ Select Front-End UI", menu=fe_menu)

        # OpenXR & VR Runtime Submenu
        xr_menu = tk.Menu(
            self.menu_dropdown,
            tearoff=0,
            bg=BG_COLOR,
            fg=ACCENT_CYAN,
            font=btn_font,
            activebackground="#1a1a1a",
            activeforeground=ACCENT_CYAN,
        )
        xr_menu.add_command(
            label="🖥️ Virtual Desktop (VDX / VDVAD 24kHz)",
            command=lambda: print("[TopBar] Runtime: Virtual Desktop"),
        )
        xr_menu.add_command(
            label="🔗 Meta Quest Link / AirLink",
            command=lambda: print("[TopBar] Runtime: Meta Link"),
        )
        xr_menu.add_command(
            label="♨️ SteamVR / SteamXR",
            command=lambda: print("[TopBar] Runtime: SteamVR"),
        )
        self.menu_dropdown.add_cascade(label="🎮 OpenXR & VR Runtime", menu=xr_menu)

        # Web Settings Panel Direct Link
        self.menu_dropdown.add_command(
            label="⚙ Settings Panel (Port 8201)",
            command=lambda: webbrowser.open("http://127.0.0.1:8401/settings.html"),
        )

        self.menu_dropdown.add_separator()
        # Start/Stop FoveAI Stack
        self.menu_dropdown.add_command(
            label="🚀 Start FoveAI Stack",
            command=self._start_stack,
            foreground=ACCENT_GREEN,
            activeforeground="#ffffff",
            activebackground=ACCENT_GREEN,
        )
        self.menu_dropdown.add_command(
            label="⏹ Stop FoveAI Stack",
            command=self._stop_stack,
            foreground=ACCENT_PINK,
            activeforeground="#ffffff",
            activebackground=ACCENT_PINK,
        )
        self.menu_dropdown.add_separator()
        self.menu_dropdown.add_command(
            label="❌ Exit / Close Lumax",
            command=self._exit_foveai,
            foreground=ACCENT_PINK,
            activeforeground="#ffffff",
            activebackground=ACCENT_PINK,
        )

        self.jen_status.pack(side="left", padx=5)

        # Bind canvas click to also open the menu
        self.jen_canvas.bind(
            "<Button-1>", lambda e: self.menu_dropdown.post(e.x_root, e.y_root + 15)
        )

        # Center: Clock & Launchers
        self.center_frame = tk.Frame(self, bg=BG_COLOR, height=BAR_HEIGHT)
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Launcher Buttons - Uses default browser
        self.btn_web = tk.Button(
            self.center_frame,
            text="🖥️",
            bg=BG_COLOR,
            fg=ACCENT_CYAN,
            font=btn_font,
            relief="flat",
            bd=0,
            command=lambda: webbrowser.open(f"{WEB_UI_URL}/?{VERSION_SUFFIX}"),
        )
        self.btn_web.pack(side="left", padx=5)

        self.btn_xr = tk.Button(
            self.center_frame,
            text="🥽",
            bg=BG_COLOR,
            fg=ACCENT_CYAN,
            font=btn_font,
            relief="flat",
            bd=0,
            command=lambda: self._open_menu_window("cognition"),
        )
        self.btn_xr.pack(side="left", padx=5)

        self.clock_label = tk.Label(
            self.center_frame,
            text="00:00:00",
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            font=("Orbitron", 10),
        )
        self.clock_label.pack(side="left", padx=15)

        # Enhanced Video Call Toggle
        self.btn_call = tk.Button(
            self.center_frame,
            text="📞📹",
            bg=BG_COLOR,
            fg=ACCENT_GREEN,
            font=("Segoe UI Symbol", 10),
            relief="flat",
            bd=0,
            command=self._toggle_call,
        )
        self.btn_call.pack(side="left", padx=5)

        # Ambient Volume Slider (custom canvas — left of metrics, right of FoveAI)
        self.vol_canvas = tk.Canvas(
            self.jen_frame,
            width=70,
            height=20,
            bg=BG_COLOR,
            highlightthickness=0,
            cursor="hand2",
        )
        self.vol_canvas.pack(side="left", padx=(10, 2))
        self._vol_value = int(self.ambient_engine.volume * 1000)
        self._vol_dragging = False
        self._vol_hover = False
        self._vol_muted = False
        self._vol_pre_mute = self._vol_value  # Remember volume before mute
        self._draw_vol_slider()
        self.vol_canvas.bind("<Button-1>", self._vol_click)
        self.vol_canvas.bind("<B1-Motion>", self._vol_drag)
        self.vol_canvas.bind("<ButtonRelease-1>", self._vol_release)
        self.vol_canvas.bind("<Enter>", lambda e: self._vol_hover_on())
        self.vol_canvas.bind("<Leave>", lambda e: self._vol_hover_off())

        # Right: Metrics Text Matrix (Replaces Bars)
        self.metrics_frame = tk.Frame(self, bg=BG_COLOR, height=BAR_HEIGHT)
        self.metrics_frame.pack(side="right", padx=10)

        self.metric_widgets = []
        for label in METRIC_LABELS:
            l = tk.Label(
                self.metrics_frame,
                text=f"{label} 0%",
                fg=ACCENT_CYAN,
                bg=BG_COLOR,
                font=("Orbitron", 7, "bold"),
            )
            l.pack(side="left", padx=8)
            self.metric_widgets.append(l)

    def _register_appbar(self):
        self.sw = self.winfo_screenwidth()
        # Default hidden state: sitting at y = -BAR_HEIGHT + 2 (2px glowing strip)
        self.geometry(f"{self.sw}x{BAR_HEIGHT}+0+{-BAR_HEIGHT + 2}")

        # Hover bindings for auto-hide
        self.bind("<Enter>", lambda e: self.slide_down())
        self.bind("<Leave>", lambda e: self.after(1000, self.check_slide_up))

    def slide_down(self):
        if not self.is_hidden or self.is_animating:
            return
        self.is_animating = True
        self._animate_slide(0, step=4)

    def check_slide_up(self):
        # Don't slide up if mouse is in window
        x, y = self.winfo_pointerxy()
        wx = self.winfo_rootx()
        wy = self.winfo_rooty()
        if wx <= x <= wx + self.winfo_width() and wy <= y <= wy + self.winfo_height():
            return
        # Keep open if in a call or speaking
        if self.jen_state == "SPEAKING" or self.call_active:
            return
        self.slide_up()

    def slide_up(self):
        if self.is_hidden or self.is_animating:
            return
        self.is_animating = True
        self._animate_slide(-BAR_HEIGHT + 2, step=-4)

    def _animate_slide(self, target_y, step):
        current_y = self.winfo_y()
        if (step > 0 and current_y < target_y) or (step < 0 and current_y > target_y):
            new_y = current_y + step
            if (step > 0 and new_y > target_y) or (step < 0 and new_y < target_y):
                new_y = target_y
            self.geometry(f"{self.sw}x{BAR_HEIGHT}+0+{new_y}")
            self.after(10, lambda: self._animate_slide(target_y, step))
        else:
            self.geometry(f"{self.sw}x{BAR_HEIGHT}+0+{target_y}")
            self.is_hidden = target_y < 0
            self.is_animating = False

    def _start_loops(self):
        self._update_metrics_ui()
        self._update_clock()
        self._animate_jen()

        # Background fetcher
        t = threading.Thread(target=self._vitals_fetcher, daemon=True)
        t.start()

    def _vitals_fetcher(self):
        """Unified fetcher with direct text value mapping."""
        import ssl

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {"User-Agent": "Mozilla/5.0 Lumax/8.0"}

        while True:
            success = False
            # Try Tunnel -> Localhost
            for url in [SOUL_VITALS_URL, "http://localhost:8402/vitals"]:
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(
                        req, timeout=0.8, context=ctx
                    ) as response:
                        data = json.loads(response.read().decode())
                        with self.lock:

                            def p(key):
                                val = data.get(key)
                                return float(val) / 100.0 if val is not None else 0.0

                            self.vitals[0] = p("CPU_PCT")
                            self.vitals[1] = p("GPU_PCT")
                            self.vitals[2] = p("RAM_PCT")
                            self.vitals[3] = p("VRAM_PCT")
                            # Normalized IO/Net
                            self.vitals[4] = min(
                                1.0,
                                (
                                    data.get("IO_READ_KBPS", 0)
                                    + data.get("IO_WRITE_KBPS", 0)
                                )
                                / 10240.0,
                            )
                            self.vitals[5] = min(
                                1.0, data.get("NET_IN_KBPS", 0) / 10240.0
                            )
                            self.vitals[6] = min(
                                1.0, data.get("NET_OUT_KBPS", 0) / 2048.0
                            )
                        success = True
                        break
                except:
                    continue

            if not success:
                try:
                    cpu = psutil.cpu_percent() / 100.0
                    ram = psutil.virtual_memory().percent / 100.0
                    with self.lock:
                        self.vitals[0] = cpu
                        self.vitals[2] = ram
                except:
                    pass

            time.sleep(2)

    def _update_metrics_ui(self):
        with self.lock:
            vals = list(self.vitals)

        for i, val in enumerate(vals):
            if i < len(self.metric_widgets):
                lbl = METRIC_LABELS[i]
                pct = int(val * 100)
                color = self._get_color_for_val(val)

                # Update text and color
                self.metric_widgets[i].config(text=f"{lbl} {pct}%", fg=color)

        self.after(500, self._update_metrics_ui)

    def _get_color_for_val(self, val):
        if val < 0.20:
            return ACCENT_CYAN
        if val < 0.60:
            return ACCENT_GREEN
        if val < 0.95:
            return "#ffaa00"  # Warning Yellow
        return ACCENT_PINK  # Clinical Red/Pink

    def _update_clock(self):
        now = datetime.now().strftime("%H:%M:%S")
        self.clock_label.config(text=now)
        self.after(1000, self._update_clock)

    def _animate_jen(self):
        """Breathing animation for Jen icon."""
        self.jen_glow += 0.05
        pulse = (math.sin(self.jen_glow) + 1) / 2

        color = ACCENT_CYAN
        if self.jen_state == "LISTENING":
            color = ACCENT_CYAN
        elif self.jen_state == "SPEAKING":
            color = ACCENT_PINK

        size = 4 + (pulse * 2)
        self.jen_canvas.coords(self.jen_avatar, size, size, 28 - size, 28 - size)
        self.jen_canvas.itemconfig(self.jen_avatar, outline=color)
        self.jen_canvas.itemconfig(self.jen_symbol, fill=color)

        self.after(50, self._animate_jen)

    def _send_nav_command(self, tab):
        """Try to send navigation command to Soul. Returns True only if WebUI is active."""
        try:
            # First, check if WebUI is actually alive via Soul's presence check
            presence_url = f"{SOUL_INTERNAL_URL}/api/presence/heartbeat"
            with urllib.request.urlopen(presence_url, timeout=0.5) as response:
                if response.getcode() == 200:
                    url = f"{SOUL_INTERNAL_URL}/api/nav/push"
                    data = json.dumps({"action": "navigate", "tab": tab}).encode(
                        "utf-8"
                    )
                    req = urllib.request.Request(
                        url, data=data, headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=0.5) as nav_resp:
                        return nav_resp.getcode() == 200
            return False
        except Exception:
            return False

    def _open_menu_window(self, tab):
        """Open a specific WebUI or XR view in a dedicated window, or update existing."""
        if tab == "webvm":
            # Launch a terminal window with bash
            try:
                if sys.platform == "win32":
                    # On Windows, use PowerShell
                    subprocess.Popen(
                        ["powershell", "-NoExit", "-Command", "cd ~; bash"],
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )
                else:
                    # On Linux/macOS, use xterm or default terminal
                    try:
                        subprocess.Popen(["xterm", "-e", "bash"])
                    except:
                        subprocess.Popen(["gnome-terminal", "--", "bash"])
            except Exception as e:
                messagebox.showerror(
                    "Terminal Error", f"Failed to launch terminal: {e!s}"
                )
            return

        if self._send_nav_command(tab):
            return

        # --- OMEGA_085 Unified Vessel Root ---
        # All paths now point to the root as the XR Vessel is authoritative.
        if tab == "mobile":
            url = f"{WEB_UI_URL}/?{VERSION_SUFFIX}&mode=mobile"
        elif tab == "classic":
            url = f"{WEB_UI_URL}/?{VERSION_SUFFIX}&mode=hud&tab=dashboard"
        else:
            url = f"{WEB_UI_URL}/?{VERSION_SUFFIX}&mode=hud&tab={tab}"

        sw = self.winfo_screenwidth()
        hud_w, hud_h = 1024, 768
        pos_x, pos_y = (sw - hud_w) // 2, BAR_HEIGHT + 10

        # Generic launcher using PowerShell Start-Process (respects default browser)
        # We try to use --app flag if the default browser is Chromium-based
        ps_cmd = f'Start-Process "{url}"'

        # Heuristic: Check if Chrome or Edge is default (Simplified for safety)
        try:
            # Prefer chrome if installed, fallback to generic
            launch_cmd = (
                f'if (Get-Command "chrome" -ErrorAction SilentlyContinue) {{ '
                f'  Start-Process "chrome" -ArgumentList "--app={url}", "--window-size={hud_w},{hud_h}", "--window-position={pos_x},{pos_y}", "--user-data-dir={self.foveai_profile}" '
                f'}} else if (Get-Command "msedge" -ErrorAction SilentlyContinue) {{ '
                f'  Start-Process "msedge" -ArgumentList "--app={url}", "--window-size={hud_w},{hud_h}", "--window-position={pos_x},{pos_y}", "--user-data-dir={self.foveai_profile}" '
                f"}} else {{ "
                f'  Start-Process "{url}" '
                f"}}"
            )
            subprocess.Popen(["powershell", "-Command", launch_cmd], shell=True)
        except Exception:
            webbrowser.open(url)

    def _toggle_call(self):
        """Toggle video call state and trigger mode=hud."""
        if not self.call_active:
            url = f"{WEB_UI_URL}/?{VERSION_SUFFIX}&mode=hud"
            sw = self.winfo_screenwidth()
            hud_w, hud_h = 440, 360
            pos_x, pos_y = sw - hud_w - 20, BAR_HEIGHT + 10

            try:
                launch_cmd = (
                    f'if (Get-Command "chrome" -ErrorAction SilentlyContinue) {{ '
                    f'  Start-Process "chrome" -ArgumentList "--app={url}", "--window-size={hud_w},{hud_h}", "--window-position={pos_x},{pos_y}", "--user-data-dir={self.foveai_profile}" '
                    f"}} else {{ "
                    f'  Start-Process "{url}" '
                    f"}}"
                )
                subprocess.Popen(["powershell", "-Command", launch_cmd], shell=True)
                self.call_active = True
                self.btn_call.config(text="📞❌", fg=ACCENT_PINK)
                self.jen_state = "SPEAKING"
            except Exception:
                webbrowser.open(url)
                self.call_active = True
        else:
            # Generic cleanup
            subprocess.Popen(
                'taskkill /F /IM chrome.exe /FI "WINDOWTITLE eq FoveAI*"', shell=True
            )
            subprocess.Popen(
                'taskkill /F /IM msedge.exe /FI "WINDOWTITLE eq FoveAI*"', shell=True
            )
            self.call_active = False
            self.btn_call.config(text="📞📹", fg=ACCENT_GREEN)
            self.jen_state = "STANDBY"

    def _start_heartbeat_server(self):
        """Start local HTTP server for website heartbeat signals."""
        try:
            server = HTTPServer(("127.0.0.1", AMBIENT_PORT), HeartbeatHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            print(f"[LumaxTopBar] Heartbeat server on port {AMBIENT_PORT}")
        except Exception as e:
            print(f"[LumaxTopBar] Heartbeat server failed: {e}")

    # Speaker icon occupies rightmost ~14px of the 70px canvas
    _SPEAKER_ICON_X = 56  # Left edge of speaker icon hit area

    def _draw_vol_slider(self):
        """Draw custom volume slider with glowing cyan fill."""
        c = self.vol_canvas
        c.delete("all")
        w, h = 70, 20
        pad = 4
        track_y1, track_y2 = 7, 13
        # Track background (faint cyan tint) — only up to speaker icon
        c.create_rectangle(
            pad, track_y1, self._SPEAKER_ICON_X, track_y2, fill="#0a1a20", outline=""
        )
        # Filled portion (bright glowing cyan to the left of knob)
        display_val = 0 if self._vol_muted else self._vol_value
        knob_x = pad + (display_val / 1000.0) * (self._SPEAKER_ICON_X - pad)
        if knob_x > pad + 1 and not self._vol_muted:
            c.create_rectangle(
                pad, track_y1, knob_x, track_y2, fill="#00a0b0", outline=""
            )
        elif self._vol_muted:
            # Show muted state with faint red track
            c.create_rectangle(
                pad,
                track_y1,
                self._SPEAKER_ICON_X,
                track_y2,
                fill="#1a0808",
                outline="",
            )
        # Knob — dimmed when muted, bright cyan normally
        if self._vol_muted:
            knob_border = "#553333"
            knob_fill = "#883333"
        else:
            knob_border = (
                "#80f8ff" if (self._vol_hover or self._vol_dragging) else ACCENT_CYAN
            )
            knob_fill = ACCENT_CYAN
        c.create_rectangle(
            knob_x - 4, 4, knob_x + 4, 16, fill=knob_fill, outline=knob_border, width=1
        )
        # Speaker icon — muted shows 🔇, normal shows 🔊
        icon = "🔇" if self._vol_muted else "🔊"
        icon_color = ACCENT_PINK if self._vol_muted else ACCENT_CYAN
        c.create_text(
            w - 1,
            10,
            text=icon,
            font=("Segoe UI Symbol", 7),
            fill=icon_color,
            anchor="e",
        )

    def _vol_hover_on(self):
        self._vol_hover = True
        self._draw_vol_slider()

    # ---------------------------------------------------------------------
    # Reverb handling – expose UI toggle
    # ---------------------------------------------------------------------
    def _toggle_reverb(self):
        """Toggle the simple reverb effect on/off.
        Updates the button icon to indicate state (🔁 for on, ❌ for off).
        """
        # Flip the reverb state in the audio engine
        new_state = not self.ambient_engine.reverb_enabled
        self.ambient_engine.toggle_reverb(new_state)
        # Update button text/icon to reflect state
        if new_state:
            self.reverb_btn.config(text="🔁")
        else:
            self.reverb_btn.config(text="❌")

    def _vol_hover_off(self):
        self._vol_hover = False
        self._draw_vol_slider()

    def _vol_click(self, event):
        # Check if click is in the speaker icon area (rightmost ~14px)
        if event.x >= self._SPEAKER_ICON_X:
            # Toggle mute
            if self._vol_muted:
                # Unmute: restore previous volume
                self._vol_muted = False
                self._vol_value = self._vol_pre_mute
                self.ambient_engine.set_volume(self._vol_value / 1000.0)
                print(f"[Vol] UNMUTE — restoring vol={self._vol_value / 1000.0:.3f}")
            else:
                # Mute: save current volume, set to 0
                self._vol_pre_mute = self._vol_value
                self._vol_muted = True
                self.ambient_engine.set_volume(0.0)
                print(f"[Vol] MUTE — saved pre_mute={self._vol_pre_mute}")
            self._draw_vol_slider()
            return

        # Click on track: start dragging (also unmute if muted)
        if self._vol_muted:
            self._vol_muted = False
        self._vol_dragging = True
        self._vol_update_from_x(event.x)

    def _vol_drag(self, event):
        if self._vol_dragging:
            self._vol_update_from_x(event.x)

    def _vol_release(self, event):
        self._vol_dragging = False
        self._draw_vol_slider()

    def _vol_update_from_x(self, x):
        pad = 4
        track_right = self._SPEAKER_ICON_X  # Track ends at speaker icon
        ratio = max(0.0, min(1.0, (x - pad) / (track_right - pad)))
        self._vol_value = int(ratio * 1000)
        self._vol_pre_mute = self._vol_value  # Update pre-mute so unmute returns here
        self.ambient_engine.set_volume(ratio)
        print(f"[Vol] ratio={ratio:.3f} vol={self.ambient_engine.volume:.3f}")
        self._draw_vol_slider()

    def _heartbeat_watchdog(self):
        """Check if website is still alive. If no heartbeat for 6s, fade out audio."""
        if HeartbeatHandler.last_heartbeat > 0:
            elapsed = time.time() - HeartbeatHandler.last_heartbeat
            if elapsed > 6.0:
                self.ambient_engine.signal_loss()
                if self.jen_state != "SPEAKING":
                    self.jen_state = "STANDBY"
            elif elapsed < 2.0:
                # Website is actively beating
                if self.jen_state == "STANDBY":
                    self.jen_state = "LISTENING"
        self.after(2000, self._heartbeat_watchdog)

    def _start_stack(self):
        """Start the FoveAI service stack via sleipnir launcher.
        Shows a visible PowerShell window so the user can see errors.
        Polls health endpoints and updates the menu state."""
        print("[LumaxTopBar] Starting FoveAI stack...")
        try:
            # Resolve project root: Tools/foveai_top_bar/ -> FoveAI/
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.normpath(os.path.join(script_dir, "..", ".."))

            # Primary: Start_Concordia.PS1 in project root
            ps1_path = os.path.join(project_root, "Start_Concordia.PS1")
            js_path = os.path.join(project_root, "sleipnir_launcher.js")

            if os.path.exists(ps1_path):
                # Visible window so user can see errors — NO creationflags hiding
                proc = subprocess.Popen(
                    [
                        "powershell.exe",
                        "-NoLogo",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-WindowStyle",
                        "Normal",
                        "-File",
                        ps1_path,
                    ],
                    cwd=project_root,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                print(
                    f"[LumaxTopBar] Started sleipnir from: {ps1_path} (PID: {proc.pid})"
                )
            elif os.path.exists(js_path):
                # Fallback: run sleipnir_launcher.js directly
                proc = subprocess.Popen(
                    ["node", js_path],
                    cwd=project_root,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                print(
                    f"[LumaxTopBar] Started sleipnir_launcher.js directly (PID: {proc.pid})"
                )
            else:
                print(
                    f"[LumaxTopBar] ERROR: No start script found. Checked:\n  {ps1_path}\n  {js_path}"
                )
                return

            # Background health polling — update menu state after services come up
            def _poll_health():
                import urllib.request

                health_endpoints = {
                    "Soul Core": "http://127.0.0.1:8000/health",
                    "Nexus Proxy": "http://127.0.0.1:8080/",
                    "TokenSlayer": "http://127.0.0.1:8103/health",
                }
                poll_start = time.time()
                max_wait = 45  # seconds
                results = {}
                while time.time() - poll_start < max_wait:
                    for name, url in health_endpoints.items():
                        if name in results:
                            continue
                        try:
                            req = urllib.request.Request(url, method="HEAD")
                            with urllib.request.urlopen(req, timeout=2) as resp:
                                if resp.status == 200:
                                    results[name] = True
                                    print(f"[LumaxTopBar] ✅ {name} is UP")
                        except Exception:
                            pass
                    if len(results) == len(health_endpoints):
                        print(
                            f"[LumaxTopBar] ✅ All services started in {time.time() - poll_start:.0f}s"
                        )
                        return
                    time.sleep(2)
                # Report what started and what didn't
                for name in health_endpoints:
                    if name not in results:
                        print(
                            f"[LumaxTopBar] ⚠️ {name} did not respond within {max_wait}s"
                        )

            threading.Thread(target=_poll_health, daemon=True).start()

        except Exception as e:
            print(f"[LumaxTopBar] Failed to start stack: {e}")

    def _stop_stack(self):
        """Stop all FoveAI services by killing processes on known ports.
        Uses PowerShell Get-NetTCPConnection for reliable PID detection."""
        print("[LumaxTopBar] Stopping FoveAI stack...")
        try:
            foveai_ports = [
                8000,
                8001,
                8002,
                8003,
                8004,
                8080,
                8101,
                8103,
                8104,
                8106,
                8109,
                8110,
                8112,
                8113,
                8888,
                5000,
            ]
            port_list = ",".join(str(p) for p in foveai_ports)

            # PowerShell one-liner: find PIDs on FoveAI ports, kill them, wait for ports to clear
            ps_cmd = (
                f"$ports = @({port_list}); "
                f"$pids = @(); "
                f"foreach ($p in $ports) {{ "
                f"  try {{ "
                f"    $conn = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue; "
                f"    if ($conn) {{ $pids += $conn.OwningProcess }} "
                f"  }} catch {{ }} "
                f"}}; "
                f"$pids = $pids | Select -Unique; "
                f"foreach ($pid in $pids) {{ try {{ Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue }} catch {{ }} }}; "
                f"# Also kill node.exe and python.exe that might be FoveAI-related; "
                f"Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force; "
                f'Write-Host "Stopped $($pids.Count) process(es) on FoveAI ports"'
            )
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                timeout=15,
            )

            # Wait for ports to clear (TIME_WAIT)
            deadline = time.time() + 8
            while time.time() < deadline:
                try:
                    out = subprocess.run(
                        ["netstat", "-ano"], capture_output=True, text=True, timeout=3
                    )
                    still_busy = False
                    for port in foveai_ports:
                        for line in out.stdout.split("\n"):
                            if f":{port} " in line and (
                                "LISTENING" in line or "TIME_WAIT" in line
                            ):
                                still_busy = True
                                break
                        if still_busy:
                            break
                    if not still_busy:
                        break
                    time.sleep(0.5)
                except Exception:
                    break

            print("[LumaxTopBar] Stack stopped. All ports cleared.")
        except Exception as e:
            print(f"[LumaxTopBar] Failed to stop stack: {e}")

    def _exit_foveai(self):
        """Clean up active browser sessions and close the top bar."""
        print("[LumaxTopBar] Exiting Lumax Top Bar...")
        try:
            # Kill any Chrome or Edge app instances loading FoveAI pages
            subprocess.Popen(
                'taskkill /F /IM chrome.exe /FI "WINDOWTITLE eq FoveAI*"', shell=True
            )
            subprocess.Popen(
                'taskkill /F /IM msedge.exe /FI "WINDOWTITLE eq FoveAI*"', shell=True
            )
        except Exception as e:
            print(f"[LumaxTopBar] Failed to kill browser instances: {e}")

        # Shut down this top bar application
        self.destroy()


if __name__ == "__main__":
    # Ensure parent package is on path for local imports
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).parent.parent))

    # Start GhostBrain listener if available
    try:
        import threading

        from ghost_brain import GhostBrain

        gb = GhostBrain()
        threading.Thread(target=gb.start_listening, daemon=True).start()
    except Exception as e:
        print(f"[LumaxTopBar] Failed to init Ghost Brain: {e}")

    app = LumaxTopBar()
    try:
        app.mainloop()
    finally:
        try:
            app.ambient_engine.stop()
        except Exception:
            pass
        try:
            cleanup_appbar(app)
        except Exception:
            pass
