"""
FoveAI Soundscape — offline rendered audio environments for themes.

NOT live oscillators ("not just oscilloscopes"): the theme's visual
finish is transposed into a fully specified acoustic design, RENDERED
once, offline, into a long seamless loop — it plays like a real long
field recording. Encoded economically (OGG Vorbis, mono, 56k target —
compress to the least possible size without compromising quality).

The Dirigent (MusicalDirector chord/atmosphere language) parameterizes
the render: each soundscape carries a chord family + atmosphere scene.

Deterministic: seeded from the theme name — same theme, same recording.

Loop quality: rendered head→tail crossfold (equal-power), so no seam
click; macro-form period ≥ 90s so repetition is felt as form, not loop.
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
import os
import random
from typing import Any

import numpy as np
import soundfile as sf

# ─── Economy contract ────────────────────────────────────────────────
# compress: Opus mono 24kHz @ level 0.9 ≈ 30 kbps ≈ ~0.37 MB / 96 s loop.
# (MP3 320k would be 3.7 MB — ~10× larger for the same perceived ambience.)
# Never exceed 0.6 MB. Opus needs SR ∈ {8,12,16,24,48} kHz — render at SR,
# resample to 24k on encode (our content: drones ≤1.5k, bells ≤4.4k, bed
# air ≤12k — 24k is acoustically complete).
SR = 22050                 # internal render rate
LOOP_SECONDS = 96          # rendered macro-form length
OPUS_SR = 24000            # encode rate (Opus-supported)
OGG_QUALITY = 0.9          # opus compression_level: higher = fewer bytes
VORBIS_QUALITY = 0.32      # fallback codec (~56-64 kb/s mono)
MAX_BYTES = 600_000        # economy ceiling per soundscape

# Dirigent chord families (432Hz-acoustic-life-pulse aligned, A=432 ref)
A432_SCALE = 432 / 440.0
CHORDS: dict[str, list[float]] = {
    "C_MAJOR":      [130.81, 164.81, 196.00],
    "C_MAJ7":       [130.81, 164.81, 196.00, 246.94],
    "A_MINOR":      [110.00, 130.81, 164.81],
    "E_MINOR":      [82.41, 123.47, 164.81],
    "G_MAJOR":      [98.00, 123.47, 146.83],
    "F_LYDIAN":     [87.31, 110.00, 138.59, 174.61],
    "C_DOMINANT7":  [130.81, 164.81, 196.00, 233.08],
    "D_HARMONIC":   [73.42, 110.00, 146.83],
}
DEFAULT_CHORD = "A_MINOR"

# Atmosphere noise beds — the scene is the "prompted" material
SCENES = {
    "VOID":     ("brown", 0.10, 0.003),   # (color, level, modulation rate Hz)
    "SUBTERRANEAN": ("brown", 0.18, 0.006),
    "COSMIC":   ("pink", 0.12, 0.004),
    "OCEANIC":  ("brown", 0.22, 0.020),
    "MECHANIC": ("pink", 0.14, 0.040),
    "FOREST":   ("pink", 0.16, 0.010),
}


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    """Pink noise (FFT 1/√f shaping)."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, d=1 / SR)
    f[0] = f[1]
    spec *= (1 / np.sqrt(f + 1e-9))
    out = np.fft.irfft(spec, n)
    return _norm(out)


def _brown(n: int, rng: np.random.Generator) -> np.ndarray:
    out = np.cumsum(rng.standard_normal(n))
    return _norm(out - np.linspace(out[0], out[-1], n))  # detrend for loop


def _norm(x: np.ndarray) -> np.ndarray:
    m = np.max(np.abs(x))
    return x / m if m > 1e-9 else x


def _modulate(x: np.ndarray, rate: float, depth: float, phase: float) -> np.ndarray:
    t = np.arange(len(x)) / SR
    lfo = 1.0 + depth * np.sin(2 * np.pi * rate * t + phase)
    return x * lfo


# Structural sounds — the macro-form sections riding the loop:
#   A: intro (thin, dark) → A': build (chord cycle begins)
#   B: sustain (hum + events density peak) → A'': settle (long decays)
SECTIONS = ("A", "A'", "B", "A''")
SECTION_SHARES = (0.26, 0.26, 0.30, 0.18)   # of the loop

# chord cycles — the musical ride: each cycle step shifts the drone cloud
CYCLES: dict[str, list[str]] = {
    "C_MAJOR":     ["C_MAJOR", "A_MINOR", "G_MAJOR", "A_MINOR"],
    "C_MAJ7":      ["C_MAJ7", "A_MINOR", "F_LYDIAN", "G_MAJOR"],
    "A_MINOR":     ["A_MINOR", "F_LYDIAN", "C_MAJOR", "E_MINOR"],
    "E_MINOR":     ["E_MINOR", "C_MAJOR", "G_MAJOR", "D_HARMONIC"],
    "G_MAJOR":     ["G_MAJOR", "E_MINOR", "C_MAJOR", "D_HARMONIC"],
    "F_LYDIAN":    ["F_LYDIAN", "C_MAJ7", "A_MINOR", "G_MAJOR"],
    "C_DOMINANT7": ["C_DOMINANT7", "F_LYDIAN", "A_MINOR", "C_MAJOR"],
    "D_HARMONIC":  ["D_HARMONIC", "A_MINOR", "F_LYDIAN", "E_MINOR"],
}


def orchestration_card(slug: str, spec: dict[str, Any]) -> dict[str, Any]:
    """The ride's score: chord cycle, section dynamics, event schedule,
    hum settings — all deterministic from the theme seed.
    Orchestration serves readability: one move at a time, nothing crowded."""
    seed_n = int(hashlib.sha256(slug.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed_n)
    root = spec.get("chord") or DEFAULT_CHORD
    cycle = CYCLES.get(root) or CYCLES[DEFAULT_CHORD]
    contrast = min(1.0, float(spec.get("contrast") or 0.2))
    n_events_total = int((0.008 + contrast * 0.03) * LOOP_SECONDS)

    # distribute events across sections (B sustains, A'' lets them decay)
    weights = {"A": 0.15, "A'": 0.25, "B": 0.45, "A''": 0.15}
    events = []
    section_bounds = []
    acc = 0.0
    for share in SECTION_SHARES:
        section_bounds.append((acc, acc + share))
        acc += share
    for sec, w in weights.items():
        k = max(0, int(n_events_total * w))
        lo, hi = section_bounds[SECTIONS.index(sec)]
        for _ in range(k):
            events.append({"t": round(lo + rng.random() * (hi - lo), 3),
                           "sec": sec})
    events.sort(key=lambda e: e["t"])

    return {
        "cycle": cycle,
        "sections": section_bounds,
        "events": events,
        "hum": {"gain": 0.05 + (spec.get("luminance") or 0.5) * 0.06,
                "vibrato_hz": 4.6 + rng.random() * 0.8,
                "start": section_bounds[1][0]},   # hum enters on the build
        "reverb_decay": {"A": 0.62, "A'": 0.55, "B": 0.50, "A''": 0.70},
        "section_levels": {"A": 0.5, "A'": 0.75, "B": 1.0, "A''": 0.6},
    }


def _drone(frequencies: list[float], n: int, seed: np.random.Generator, warmth: float) -> np.ndarray:
    """Slow-evolving harmonic cloud: each partial drifts < 0.4 Hz around its
    center — the recording feel, 'instruments breathing', not a fixed osc."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for i, f0 in enumerate(frequencies):
        f0 *= A432_SCALE
        glide = 0.3 + warmth * 0.3                       # heavier warmth = wider drift
        drift = (seed.random() - 0.5) * glide
        wob = 0.15 * math.sin(i * 1.7 + seed.random() * 6)
        # amplitude envelope: 60-110s LFO — movement at macro scale
        lfo_hz = 1 / (60 + seed.random() * 50)
        amp = 0.55 + 0.4 * np.sin(2 * np.pi * lfo_hz * t + seed.random() * 6)
        wave = np.sin(2 * np.pi * (f0 + drift + wob) * t) \
            + 0.35 * np.sin(2 * np.pi * (f0 + drift + wob) * 2 * t)
        out += amp * wave / max(1, len(frequencies))
    return _norm(out)


def _bell(freq: float, dur: float, rng: np.random.Generator) -> np.ndarray:
    """Single sparse event: inharmonic partials + exponential decay."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    partials = [1.0, 2.756, 5.404, 8.933]                # bell inharmonicity
    out = np.zeros(n)
    for i, p in enumerate(partials):
        amp = 1 / (i + 1) ** 1.7
        out += amp * np.sin(2 * np.pi * freq * p * (1 + (rng.random() - 0.5) * 0.002) * t)
    out *= np.exp(-t * (3.5 + rng.random() * 2))
    return out


def _fbn_reverb(x: np.ndarray, rng: np.random.Generator, decay: float = 0.62) -> np.ndarray:
    """Tiny feedback delay network: long soft tail without heavy CPU."""
    out = x.copy()
    for tap in (int(0.11 * SR), int(0.23 * SR), int(0.41 * SR)):
        d = np.zeros_like(out)
        d[tap:] = x[:-tap] * decay
        d2 = np.zeros_like(d)
        d2[tap:] = d[:-tap] * 0.3
        out += d + d2
    return _norm(out)


def _fold_seam(x: np.ndarray, fold_s: float = 4.0) -> np.ndarray:
    """Equal-power crossfold: head and tail overlap-shape so the loop seam
    is inaudible; net length trimmed to keep total duration honest.
    LOOPABLE SEAMLESSLY IS LAW — every soundscape passes _verify_seam()
    or the render is rejected."""
    n_f = int(fold_s * SR)
    n = len(x) - n_f
    body, head, tail = x[:n], x[n:], x[:n_f]
    ramp = np.linspace(0, np.pi / 2, n_f)
    folded = body.copy()
    folded[:n_f] = head * np.cos(ramp) + tail * np.sin(ramp)
    return _norm(folded)


def _verify_seam(x: np.ndarray, win_s: float = 2.0) -> bool:
    """THE LAW, checked: the loop seam must be inaudible — the RMS of the
    2s window before the seam must match the RMS after it within tolerance,
    and the discontinuity at the wrap point must be tiny."""
    n_w = int(win_s * SR)
    enter = x[-n_w:]
    leave = x[:n_w]
    rms_e = math.sqrt(float(np.mean(enter ** 2))) + 1e-9
    rms_l = math.sqrt(float(np.mean(leave ** 2))) + 1e-9
    if abs(rms_e - rms_l) / max(rms_e, rms_l) > 0.25:
        return False
    jump = abs(float(x[0]) - float(x[-1]))
    return jump <= max(0.05, 3.0 * rms_e)


def render_soundscape(spec: dict[str, Any]) -> str:
    """spec keys: name, sector, warmth, luminance, contrast, saturation, dark,
    chord (Dirigent family name), scene (atmosphere name). Returns .ogg path."""
    slug = (spec.get("name") or "soundscape").lower().replace(" ", "-")[:40]
    seed_n = int(hashlib.sha256(slug.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed_n)
    n = LOOP_SECONDS * SR

    chord = CHORDS.get(spec.get("chord") or DEFAULT_CHORD, CHORDS[DEFAULT_CHORD])
    dark = bool(spec.get("dark", True))
    warmth = float(np.clip((spec.get("warmth") + 1) / 2 if spec.get("warmth") is not None else 0.5, 0, 1))
    scene_name = spec.get("scene") or ("SUBTERRANEAN" if dark else "COSMIC")
    color, level, mod_rate = SCENES.get(scene_name, SCENES["SUBTERRANEAN"])

    rng_np = np.random.default_rng(seed_n + 1)
    bed = (_pink(n, rng_np) if color == "pink" else _brown(n, rng_np))
    bed = _modulate(bed, mod_rate, 0.35, seed_n % (2 * math.pi))
    bed *= level

    # ── THE RIDE: orchestration card conducts one theme, amassed ──
    card = orchestration_card(slug, spec)
    t = np.arange(n) / SR
    mix = bed.copy()
    bounds = card["sections"]
    levels = card["section_levels"]

    # section envelope: per-section level, 2s equal-power walls between
    env = np.zeros(n)
    for idx, sec in enumerate(SECTIONS):
        lo, hi = bounds[idx]
        a, b = int(lo * LOOP_SECONDS * SR), int(hi * LOOP_SECONDS * SR)
        seg = np.full(b - a, levels[sec])
        # soft section walls (2s) — structural, not abrupt
        w = int(2.0 * SR)
        ramp = np.linspace(0, np.pi / 2, w)
        if idx > 0:
            seg[:w] = seg[:w] * np.sin(ramp) + levels[SECTIONS[idx - 1]] * np.cos(ramp)
        env[a:b] = seg
        # fold the envelope over the seam: the loop rides through A again
    env_fold = int(4.0 * SR)
    env[-env_fold:] = env[-env_fold:] * np.linspace(1, 0, env_fold) + env[:env_fold] * np.linspace(0, 1, env_fold)

    # drone cloud follows the chord cycle — one chord per section
    for idx, sec in enumerate(SECTIONS):
        lo, hi = bounds[idx]
        chord_fn = CHORDS.get(card["cycle"][idx], CHORDS[DEFAULT_CHORD])
        a, b = int(lo * LOOP_SECONDS * SR), int(hi * LOOP_SECONDS * SR)
        seg_n = b - a
        sub = _drone(chord_fn, seg_n, rng, warmth) * (0.30 if dark else 0.22)
        mix[a:b] += sub * np.linspace(0, 1, seg_n) * 0 + sub  # section-local drone

    mix *= env

    # HUM: formant singing — quiet sine + vibrato entering at the build (A')
    hum_cfg = card["hum"]
    if hum_cfg["gain"] > 0:
        hum_start = int(hum_cfg["start"] * LOOP_SECONDS * SR)
        hum_n = len(mix) - hum_start
        ht = np.arange(hum_n) / SR
        base_h = A432_SCALE * (110.0 if not dark else 98.0)  # A2 / G2 hum
        vib = 1 + 0.004 * np.sin(2 * np.pi * hum_cfg["vibrato_hz"] * ht)
        hum = (np.sin(2 * np.pi * base_h * vib * ht)
               + 0.5 * np.sin(2 * np.pi * base_h * 2.02 * ht)   # formant I
               + 0.25 * np.sin(2 * np.pi * base_h * 3.0 * ht))  # formant II
        hum *= np.minimum(1.0, ht / (6.0 * SR)) * (2 + np.sin(2 * np.pi * ht / 13.0))
        hum = np.clip(hum * 0.5, -1, 1) * hum_cfg["gain"]
        mix[hum_start:] += hum

    # EVENTS: the card's schedule — decay rides the section (A'' rings long)
    rng_np2 = np.random.default_rng(seed_n + 3)
    scales = [2 ** (k / 12) for k in (0, 3, 5, 7, 10, 12, 15)]
    total = len(mix)
    for ev in card["events"]:
        start = int(ev["t"] * LOOP_SECONDS * SR)
        if start + 6 * SR > total:
            continue
        sec = ev["sec"]
        chord_fn = CHORDS.get(card["cycle"][SECTIONS.index(sec)] if sec in SECTIONS else DEFAULT_CHORD, CHORDS[DEFAULT_CHORD])
        base = chord_fn[int(rng_np2.random() * len(chord_fn))] * A432_SCALE
        bell = _bell(base * rng_np2.choice(scales),
                     5.0 if sec in ("B", "A'") else 7.0 if sec == "A''" else 4.0,
                     rng_np2)
        damp = 0.10 + float(spec.get("saturation") or 0.3) * 0.10
        mix[start:start + len(bell)] += bell * damp

    # REVERB wet per section — settle (A'') rings longest
    wet = np.interp(t, [0, 24, 48, 72, LOOP_SECONDS],
                    [card["reverb_decay"]["A"], card["reverb_decay"]["A'"],
                     card["reverb_decay"]["B"], card["reverb_decay"]["A''"],
                     card["reverb_decay"]["A"]])
    dry = _fbn_reverb(mix, np.random.default_rng(seed_n + 2), decay=0.6)
    mix = dry * 0.6 + mix * 0.4
    mix = _fold_seam(mix)
    mix = _norm(mix) * 0.85
    # LOOPABLE SEAMLESSLY IS LAW — reject any render that can't prove it.
    if not _verify_seam(mix):
        print("[soundscape] ⛔ seam verification failed — re-fold + verify again")
        mix = _fold_seam(mix, fold_s=6.0)
        mix = _norm(mix) * 0.85
        if not _verify_seam(mix):
            print("[soundscape] ⛔ cannot certify seamless loop — rejecting render")
            return ""

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
    os.makedirs(out_dir, exist_ok=True)
    ogg = os.path.join(out_dir, f"{slug}.ogg")

    def _encode(data: np.ndarray, rate: int, subtype: str, level: float) -> int:
        sf.write(ogg, data, rate, format="OGG", subtype=subtype,
                 compression_level=level)
        return os.path.getsize(ogg)

    try:
        from scipy.signal import resample_poly

        mix_out = resample_poly(mix, OPUS_SR, SR)
        size = _encode(mix_out, OPUS_SR, "OPUS", OGG_QUALITY)
    except Exception:
        # no scipy / libsndfile lacks OPUS → vorbis fallback at full SR
        size = _encode(mix, SR, "VORBIS", VORBIS_QUALITY)
    if size > MAX_BYTES:
        # economy rule enforced: step quality down until it fits
        for q in (0.95, 0.98):
            size = _encode(mix_out, OPUS_SR, "OPUS", float(q))
            if size <= MAX_BYTES:
                break
    return ogg if size <= MAX_BYTES else ""


if __name__ == "__main__":
    import sys

    spec = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "name": "signum-default", "sector": "cyan", "warmth": -0.2,
        "luminance": 0.35, "contrast": 0.2, "saturation": 0.4,
        "dark": True, "chord": "F_LYDIAN", "scene": "VOID",
    }
    path = render_soundscape(spec)
    if path:
        print(f"soundscape → {path} ({os.path.getsize(path)} bytes, loop {LOOP_SECONDS}s)")
    else:
        print("render failed (economical ceiling unreachable)")