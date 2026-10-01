#!/usr/bin/env python3
"""
Generate default Stress Meter prototype PNGs (@2x: 440×68).

Seven-cell layout: 14% width each, six gutters, row centered (full ROW_W).

Layers (see ui_reference/layer_stack_authoritative.txt):
  05_color_cells  04_dimmer_cells  03_mask_*  02_chrome_frame  01_mist_cells
  00_prototype_preview_full — composite for sanity check.

Requires Pillow.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print("Install Pillow: pip install Pillow", file=sys.stderr)
    sys.exit(1)

W, H = 440, 68
ROW_W = float(W)
CELL_FRAC = 0.14
GAP_FRAC = (1.0 - 7.0 * CELL_FRAC) / 6.0
CELL_W = ROW_W * CELL_FRAC
GAP_W = ROW_W * GAP_FRAC
MARGIN_V = 8
BAR_TOP = MARGIN_V
BAR_H = H - 2 * MARGIN_V
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "prototype_default"


def cell_rects() -> list[tuple[int, int, int, int]]:
    rects: list[tuple[int, int, int, int]] = []
    total_w = 7 * CELL_W + 6 * GAP_W
    x0 = (ROW_W - total_w) / 2.0
    y0 = float(BAR_TOP)
    y1 = float(BAR_TOP + BAR_H)
    x = x0
    for _ in range(7):
        rects.append(
            (int(round(x)), int(round(y0)), int(round(x + CELL_W)), int(round(y1)))
        )
        x += CELL_W + GAP_W
    return rects


def _lerp(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


COOL = (32, 128, 255)
HOT = (255, 48, 56)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    r_int = cell_rects()
    radius = 6

    # --- ⑤ Colored lights (per-cell vertical tint for subtle glass) ---
    color_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for i, box in enumerate(r_int):
        t = i / 6.0
        base = _lerp(COOL, HOT, t)
        hi = tuple(min(255, c + 28) for c in base)
        lo = tuple(max(0, c - 32) for c in base)
        cw, ch = box[2] - box[0], box[3] - box[1]
        cell = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cell)
        for row in range(ch):
            ft = row / max(ch - 1, 1)
            c = tuple(int(hi[j] * (1 - ft) + lo[j] * ft) for j in range(3))
            cd.line([(0, row), (cw, row)], fill=c + (255,))
        cell = cell.filter(ImageFilter.GaussianBlur(radius=0.4))
        color_img.paste(cell, (box[0], box[1]), cell)

    color_img.save(OUT_DIR / "05_color_cells.png", optimize=True)

    # --- ④ Dimmer ---
    dimmer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ddraw = ImageDraw.Draw(dimmer)
    for i, box in enumerate(r_int):
        a = 85 + (i % 3) * 12
        ddraw.rounded_rectangle(box, radius=radius, fill=(10, 12, 18, a))
    dimmer.save(OUT_DIR / "04_dimmer_cells.png", optimize=True)

    # --- ③ Mask L: 255 in lamp holes ---
    mask_l = Image.new("L", (W, H), 0)
    mdraw = ImageDraw.Draw(mask_l)
    for box in r_int:
        mdraw.rounded_rectangle(box, radius=radius, fill=255)
    mask_l.save(OUT_DIR / "03_mask_lamp_holes_alpha.png", optimize=True)
    Image.merge("RGBA", (mask_l, mask_l, mask_l, mask_l)).save(
        OUT_DIR / "03_mask_lamp_holes.png", optimize=True
    )

    # --- ② Chrome: RGB plate + alpha (opaque bezel, transparent holes) ---
    alpha = Image.new("L", (W, H), 255)
    hdraw = ImageDraw.Draw(alpha)
    for box in r_int:
        hdraw.rounded_rectangle(box, radius=radius, fill=0)
    rgb = Image.new("RGB", (W, H), (32, 36, 44))
    chrome = Image.merge("RGBA", (*rgb.split(), alpha))
    odraw = ImageDraw.Draw(chrome)
    odraw.rounded_rectangle(
        (2, 2, W - 3, H - 3), radius=10, outline=(88, 96, 108, 255), width=2
    )
    odraw.line(
        [(int(W * 0.12), 5), (int(W * 0.5), 12)], fill=(255, 255, 255, 50), width=2
    )
    chrome.save(OUT_DIR / "02_chrome_frame.png", optimize=True)

    # --- ① Mist ---
    mist = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for box in r_int:
        cw, ch = box[2] - box[0], box[3] - box[1]
        mx = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        md = ImageDraw.Draw(mx)
        cx, cy = cw // 3, ch // 4
        md.ellipse((cx - 16, cy - 8, cx + 20, cy + 14), fill=(240, 248, 255, 28))
        mist.paste(mx, (box[0], box[1]), mx)
    mist.save(OUT_DIR / "01_mist_cells.png", optimize=True)

    # --- 00 Full preview ---
    desk = Image.new("RGBA", (W, H), (22, 24, 30, 255))
    lit = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lit.paste(color_img, (0, 0), mask_l)
    dim_clip = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dim_clip.paste(dimmer, (0, 0), mask_l)
    lit = Image.alpha_composite(lit, dim_clip)
    comp = Image.alpha_composite(desk, lit)
    comp = Image.alpha_composite(comp, chrome)
    comp = Image.alpha_composite(comp, mist)
    comp.save(OUT_DIR / "00_prototype_preview_full.png", optimize=True)

    (OUT_DIR / "README.txt").write_text(
        "Prototype default theme (@2x 440×68).\n"
        "Generated by: python scripts/generate_prototype_meter_assets.py\n\n"
        "Stack (bottom → top for preview): desk → ⑤+④ (masked) → ② → ①\n"
        "Files:\n"
        "  00_prototype_preview_full.png\n"
        "  01_mist_cells.png\n"
        "  02_chrome_frame.png\n"
        "  03_mask_lamp_holes.png / 03_mask_lamp_holes_alpha.png (L: 255 in holes)\n"
        "  04_dimmer_cells.png\n"
        "  05_color_cells.png\n",
        encoding="utf-8",
    )
    print(f"OK: {OUT_DIR}")


if __name__ == "__main__":
    main()
