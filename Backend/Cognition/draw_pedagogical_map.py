import os

from PIL import Image, ImageDraw, ImageFont

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 4000
BG_COLOR = (20, 25, 30)  # Deep Industrial Navy
ACCENT_COLOR = (0, 200, 255)  # Turquoise
TEXT_COLOR = (255, 255, 255)  # White
LINE_WIDTH = 10

OUTPUT_PATH = (
    "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_map_v2.png"
)


def draw_map():
    print("Drafting pedagogical map v2 (Pure Vector Truth)...")
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Try to load a font, fallback to default
    try:
        font_large = ImageFont.truetype("arial.ttf", 120)
        font_small = ImageFont.truetype("arial.ttf", 60)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # 1. DEFINE NODES (The 3-Node Relay + Faculties)
    nodes = {
        "FOUNDER": {"pos": (1500, 400), "label": "THE FOUNDER\n(Strategy & Manager)"},
        "MIND": {
            "pos": (1500, 1200),
            "label": "NODE 1: MIND CORE\n(Docker: Logic & Identity)",
        },
        "INTERFACE": {
            "pos": (1500, 2200),
            "label": "NODE 2: BODY INTERFACE\n(Docker: Sensory Translation)",
        },
        "HOST": {
            "pos": (1500, 3200),
            "label": "NODE 3: HOST VESSEL\n(OS: Godot VR/Mobile/Act)",
        },
        "EARS": {"pos": (800, 2600), "label": "EARS (STT)"},
        "EYES": {"pos": (1200, 2600), "label": "EYES (Vision)"},
        "MOUTH": {"pos": (1800, 2600), "label": "MOUTH (TTS)"},
        "ACT": {"pos": (2200, 2600), "label": "ACT (Movement)"},
    }

    # 2. DRAW CONNECTIONS (Axons of Truth)
    # Founder -> Mind
    draw.line(
        [nodes["FOUNDER"]["pos"], nodes["MIND"]["pos"]],
        fill=ACCENT_COLOR,
        width=LINE_WIDTH * 2,
    )
    # Mind <-> Interface
    draw.line(
        [nodes["MIND"]["pos"], nodes["INTERFACE"]["pos"]],
        fill=ACCENT_COLOR,
        width=LINE_WIDTH * 2,
    )
    # Interface <-> Host
    draw.line(
        [nodes["INTERFACE"]["pos"], nodes["HOST"]["pos"]],
        fill=ACCENT_COLOR,
        width=LINE_WIDTH * 2,
    )

    # Interface -> Faculties
    for faculty in ["EARS", "EYES", "MOUTH", "ACT"]:
        draw.line(
            [nodes["INTERFACE"]["pos"], nodes[faculty]["pos"]],
            fill=ACCENT_COLOR,
            width=LINE_WIDTH,
        )

    # 3. DRAW NODES (Spheres of Influence)
    for name, data in nodes.items():
        pos = data["pos"]
        is_main = name in ["MIND", "INTERFACE", "HOST", "FOUNDER"]
        r = 250 if is_main else 150

        # Draw Shadow/Glow
        draw.ellipse(
            [pos[0] - r - 10, pos[1] - r - 10, pos[0] + r + 10, pos[1] + r + 10],
            outline=ACCENT_COLOR,
            width=15,
        )
        draw.ellipse(
            [pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r], fill=(30, 40, 50)
        )

        # Draw Labels
        draw.text(
            (pos[0], pos[1]),
            data["label"],
            fill=TEXT_COLOR,
            font=font_large if is_main else font_small,
            anchor="mm",
            align="center",
        )

    # 4. SAVE
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully drafted high-res pedagogical map at: {OUTPUT_PATH}")


if __name__ == "__main__":
    draw_map()
