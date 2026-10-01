#!/usr/bin/env python3
"""
gen_rack_textures.py — generates the glass/LED skin textures for the
sound@cinnamon.org FX rack. Outputs 9-slice-safe PNGs next to applet.js:

  rack-panel-<theme>.png   — 64x64 glass plate (rounded, specular streaks)
  rack-deep-<theme>.png    — 64x64 recessed LCD well (darker, scanlines)
  rack-btn-<theme>.png     — 48x24 plastic button (gloss cap, shade bottom)

Run after editing palette below:  python3 gen_rack_textures.py
Then copy the PNGs to ~/.local/share/cinnamon/applets/sound@cinnamon.org/
(install.sh already copies the whole folder) and reload the applet.
"""

import os

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.dirname(os.path.abspath(__file__))
S = 4  # supersample


def _rounded_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return m


def _vgrad(w, h, top, bot):
    g = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line(
            [(0, y), (w, y)],
            fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(4)),
        )
    return g


def _diag_streaks(w, h, mask, color, bands):
    """Diagonal light bands clipped to the panel mask."""
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for cx, cw, alpha in bands:  # cx: center x of band as fraction of w
        x = int(cx * w)
        pts = [
            (x - cw // 2, -h // 4),
            (x + cw // 2, -h // 4),
            (x + cw // 2 - h // 2, h + h // 4),
            (x - cw // 2 - h // 2, h + h // 4),
        ]
        d.polygon(pts, fill=color[:3] + (alpha,))
    ov = ov.filter(ImageFilter.GaussianBlur(S))
    return Image.composite(ov, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)


def _top_spec(w, h, mask, color):
    """Hard top-edge highlight — the glass lip catching light."""
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    y = int(1.4 * S)
    d.line([(6 * S, y), (w - 6 * S, y)], fill=color, width=S)
    # fade the ends
    fade = Image.new("L", (w, h), 0)
    fd = ImageDraw.Draw(fade)
    for x in range(w):
        a = min(1.0, x / (8 * S), (w - x) / (8 * S))
        fd.line([(x, 0), (x, h)], fill=int(255 * a))
    ov.putalpha(Image.composite(ov.split()[3], Image.new("L", (w, h), 0), fade))
    return Image.composite(ov, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)


def _rim(w, h, r, mask, color):
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rounded_rectangle(
        [S // 2, S // 2, w - 1 - S // 2, h - 1 - S // 2],
        radius=r,
        outline=color,
        width=S,
    )
    return Image.composite(ov, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)


def _bottom_shade(w, h, mask, depth=14 * S, alpha=90):
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for i in range(depth):
        a = int(alpha * (i / depth))
        d.line([(0, h - 1 - i), (w, h - 1 - i)], fill=(0, 0, 0, a))
    return Image.composite(ov, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)


def _scanlines(w, h, mask, alpha=10):
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(0, h, 3 * S):
        d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha), width=S)
    return Image.composite(ov, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)


def panel(top, bot, rim, spec, streak, deep=False):
    w = h = 64 * S
    mask = _rounded_mask(w, h, 12 * S)
    img = Image.composite(
        _vgrad(w, h, top, bot), Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask
    )
    img.alpha_composite(_diag_streaks(w, h, mask, (255, 255, 255), streak))
    img.alpha_composite(_top_spec(w, h, mask, spec))
    img.alpha_composite(_bottom_shade(w, h, mask, alpha=100 if deep else 60))
    if deep:
        img.alpha_composite(_scanlines(w, h, mask))
    img.alpha_composite(_rim(w, h, 12 * S, mask, rim))
    return img.resize((64, 64), Image.LANCZOS)


def button(top, bot, rim, gloss):
    w, h = 48 * S, 24 * S
    mask = _rounded_mask(w, h, 5 * S)
    img = Image.composite(
        _vgrad(w, h, top, bot), Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask
    )
    # gloss cap: bright band across the top third, fading downward
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(h // 3):
        a = int(gloss[3] * (1 - y / (h // 3)) ** 1.6)
        d.line([(3 * S, y + S), (w - 3 * S, y + S)], fill=gloss[:3] + (a,))
    ov = ov.filter(ImageFilter.GaussianBlur(S))
    img.alpha_composite(
        Image.composite(ov, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)
    )
    # crisp top specular line
    img.alpha_composite(_top_spec(w, h, mask, rim[:3] + (min(255, rim[3] + 80),)))
    img.alpha_composite(_rim(w, h, 5 * S, mask, rim))
    return img.resize((48, 24), Image.LANCZOS)


SKINS = {
    #          top gradient          bottom gradient        rim                  top specular        streaks (cx,w,alpha)
    "phosphor": dict(
        p=(
            (20, 34, 22, 232),
            (9, 15, 9, 240),
            (70, 125, 78, 150),
            (160, 255, 175, 80),
            [(0.16, 6, 14), (0.30, 10, 9), (0.82, 7, 7)],
        ),
        d=(
            (13, 22, 14, 240),
            (6, 10, 6, 246),
            (70, 125, 78, 150),
            (150, 255, 165, 60),
            [(0.16, 6, 10), (0.30, 10, 6)],
        ),
        b=(
            (24, 42, 26, 235),
            (12, 20, 12, 242),
            (70, 125, 78, 150),
            (190, 255, 200, 60),
        ),
    ),
    "glass-dark": dict(
        p=(
            (28, 34, 46, 195),
            (8, 10, 15, 220),
            (255, 255, 255, 40),
            (255, 255, 255, 120),
            [(0.16, 6, 22), (0.30, 10, 13), (0.82, 7, 9)],
        ),
        d=(
            (16, 20, 28, 220),
            (5, 6, 9, 235),
            (255, 255, 255, 40),
            (255, 255, 255, 90),
            [(0.16, 6, 16), (0.30, 10, 9)],
        ),
        b=(
            (40, 48, 62, 200),
            (14, 17, 24, 225),
            (255, 255, 255, 48),
            (255, 255, 255, 110),
        ),
    ),
    "glass-light": dict(
        p=(
            (255, 255, 255, 175),
            (226, 233, 243, 195),
            (15, 23, 42, 55),
            (255, 255, 255, 210),
            [(0.16, 6, 70), (0.30, 10, 45), (0.82, 7, 30)],
        ),
        d=(
            (238, 243, 250, 200),
            (214, 222, 234, 215),
            (15, 23, 42, 55),
            (255, 255, 255, 170),
            [(0.16, 6, 50), (0.30, 10, 30)],
        ),
        b=(
            (255, 255, 255, 190),
            (232, 238, 247, 205),
            (15, 23, 42, 60),
            (255, 255, 255, 170),
        ),
    ),
    "onyx-logo": dict(
        p=(
            (24, 22, 17, 230),
            (6, 6, 8, 242),
            (251, 191, 36, 80),
            (255, 222, 145, 100),
            [(0.16, 6, 12), (0.30, 10, 8), (0.82, 7, 6)],
        ),
        d=(
            (14, 13, 10, 240),
            (4, 4, 5, 248),
            (251, 191, 36, 80),
            (255, 222, 145, 75),
            [(0.16, 6, 9), (0.30, 10, 6)],
        ),
        b=((32, 28, 20, 232), (10, 9, 8, 240), (251, 191, 36, 90), (255, 228, 160, 95)),
    ),
}

for name, cfg in SKINS.items():
    panel(*cfg["p"]).save(os.path.join(OUT, f"rack-panel-{name}.png"))
    panel(*cfg["d"], deep=True).save(os.path.join(OUT, f"rack-deep-{name}.png"))
    button(*cfg["b"]).save(os.path.join(OUT, f"rack-btn-{name}.png"))
    print(f"  rack-{name}: panel/deep/btn")
print("done")
