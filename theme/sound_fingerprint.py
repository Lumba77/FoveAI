"""
FoveAI Sound Fingerprint — image-derived acoustic theme design.

The FUI finish layer, made audible. The same analysis that drives the
theme's visual finish (warmth, brightness, gloss, pattern) drives the
ambient sound design and click timbre — one image, one coherent
sensory theme.

Readability-first analog for sound: the ambient bed must stay calm
(the canvas rule); guiding motion = filters and rhythm; nothing is
screamy unless the finish is (intensity ladder).

Pure stdlib + PIL (already a repo dependency). No cloud.
"""

from __future__ import annotations

import colorsys
from typing import Any

from PIL import Image, ImageFilter


# hue sector → chord root (Hz, A2-based, just audible bed tones)
HUE_ROOTS = {
    "red":        (0, 55.0),      # A1 — weight, gravity
    "orange":     (30, 65.4),     # C2 — warmth, ember
    "gold":       (50, 73.4),     # D2 — friend warmth
    "yellow":     (60, 82.4),     # E2 — alert clarity
    "green":      (120, 49.0),    # G1 — grounded, engineer calm
    "cyan":       (180, 49.0),    # G1+octave shimmer handled by filter
    "azure":      (210, 43.7),    # F1 — cool instrument
    "blue":       (240, 43.7),    # F1 low — depth
    "violet":     (270, 58.3),    # A#1 — invention
    "magenta":    (300, 61.7),    # B1 — beloved pulse
    "pink":       (330, 61.7),    # B1 soft
}


def _sector(hue_deg: float) -> tuple[str, float]:
    name = min(HUE_ROOTS, key=lambda k: abs((HUE_ROOTS[k][0] - hue_deg + 180) % 360 - 180))
    return name, HUE_ROOTS[name][1]


def analyze_image(image_path: str, sample: int = 128) -> dict[str, Any]:
    """Foveated one-look analysis: mean color, warmth, contrast, edges."""
    img = Image.open(image_path).convert("RGB")
    img = img.resize((sample, sample), Image.Resampling.LANCZOS)

    hue_sum = sat_sum = luma_sum = 0.0
    red_blue = 0.0
    px = img.load()
    n = sample * sample
    for y in range(sample):
        for x in range(sample):
            r, g, b = px[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            hue_sum += h * 360
            sat_sum += s
            luma_sum += (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
            red_blue += (r - b) / 255

    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    ep = edges.load()
    edge_sum = sum(max(0, ep[x, y] - 16) for y in range(sample) for x in range(sample))
    edge_density = min(edge_sum / (n * 80), 1.0)

    return {
        "hue": (hue_sum / n) % 360,
        "saturation": sat_sum / n,
        "luminance": luma_sum / n,
        "warmth": max(-1.0, min(1.0, red_blue / n)),     # +warm / −cool
        "contrast": edge_density,
        "dark": luma_sum / n < 0.5,
    }


def design_sound(stats: dict[str, Any]) -> dict[str, Any]:
    """Image stats → acoustic finish (the FUI grammar in sound)."""
    sector, root_hz = _sector(stats["hue"])

    # Ambience: luminance sets the filter's openness — a bright image
    # breathes higher frequencies; a dark one keeps a warm murmur.
    filter_hz = int(220 + stats["luminance"] * 1400)
    # Warmth pulls the drone slightly sharp and adds mid body density.
    warmth = (stats["warmth"] + 1) / 2
    mid_ratio = 2.5 + warmth * 2.5
    # Contrast = dynamics: quiet images drone steadily, edgy ones breathe.
    pulse_hz = 0.15 + stats["contrast"] * 2.0        # LFO rate (Hz)
    drone_gain = 0.35 + (1 - stats["contrast"]) * 0.35
    # Saturation = presence: saturated image gets a shimmer overtone.
    shimmer_gain = min(0.25, stats["saturation"] * 0.4)
    shimmer_hz = root_hz * (8 if stats["saturation"] > 0.4 else 6)

    words = []
    if stats["dark"]:
        words.append(f"dark {sector} drone, subterranean calm")
    else:
        words.append(f"luminous {sector} pad, airy calm")
    if warmth > 0.6:
        words.append("warm analog body")
    elif warmth < 0.4:
        words.append("cool glass shimmer")
    if stats["contrast"] > 0.5:
        words.append("breathing pulse")
    else:
        words.append("still, sustained")

    # Click timbre follows material guess: bright + saturated = glass,
    # dark + warm = soft wood/metal.
    click_kind = "glass" if (stats["luminance"] > 0.5 or stats["saturation"] > 0.5) else "soft-metal"

    return {
        "ambient_loop_prompt": ", ".join(words) + ", minimal, no melody",
        "ui_clicks": (f"light crystalline chime, airy tap" if click_kind == "glass"
                      else "muted wooden tick, soft tap"),
        "acoustic": {
            "root_hz": round(root_hz, 1),
            "filter_hz": filter_hz,
            "mid_ratio": round(mid_ratio, 2),
            "pulse_hz": round(pulse_hz, 3),
            "drone_gain": round(drone_gain, 2),
            "shimmer_hz": round(shimmer_hz, 1),
            "shimmer_gain": round(shimmer_gain, 3),
            "sector": sector,
        },
    }


def fingerprint(image_path: str) -> dict[str, Any]:
    """One call: analyze → acoustic design."""
    return design_sound(analyze_image(image_path))


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: python3 sound_fingerprint.py <image>")
        sys.exit(1)
    print(json.dumps(fingerprint(sys.argv[1]), indent=2))