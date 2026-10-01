import os
import random

from PIL import Image, ImageDraw, ImageFont

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 3000
BG_COLOR = (10, 12, 15)
COLOR_PRIMARY = (255, 215, 0)  # Gold
COLOR_SATELLITE = (0, 255, 200)  # Turquoise
COLOR_PLEXUS = (40, 45, 50)  # Faint Gray
TEXT_COLOR = (255, 255, 255)

OUTPUT_PATH = (
    "C:/Users/lumba/Program/VR-compagent/div/image/project_focus_plexus_soulseed.png"
)


def draw_focus_plexus():
    print("Drafting Focus Plexus: Soul Seed Cluster...")
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        font_large = ImageFont.truetype("arial.ttf", 120)
        font_small = ImageFont.truetype("arial.ttf", 60)
    except:
        font_large = font_small = ImageFont.load_default()

    CX, CY = WIDTH // 2, HEIGHT // 2

    # 1. DRAW FAINT BACKGROUND PLEXUS (The System)
    print("  Generating system noise...")
    bg_nodes = []
    for _ in range(300):
        bg_nodes.append((random.uniform(0, WIDTH), random.uniform(0, HEIGHT)))

    for i, node_a in enumerate(bg_nodes):
        for j in range(i + 1, len(bg_nodes)):
            node_b = bg_nodes[j]
            dist_sq = (node_a[0] - node_b[0]) ** 2 + (node_a[1] - node_b[1]) ** 2
            if dist_sq < 200**2:  # Close distance for faint lines
                draw.line([node_a, node_b], fill=COLOR_PLEXUS, width=1)

    # 2. DEFINE FOCUS NODES
    focus_nodes = {
        "CENTER": {
            "pos": (CX, CY),
            "label": "SoulSeed.gd\n(The 'I' Core)",
            "color": COLOR_PRIMARY,
            "r": 250,
        },
        "NW": {
            "pos": (CX - 800, CY - 800),
            "label": "DirectorManager\n(Narrative)",
            "color": COLOR_SATELLITE,
            "r": 180,
        },
        "NE": {
            "pos": (CX + 800, CY - 800),
            "label": "InteractionResonance\n(Touch)",
            "color": COLOR_SATELLITE,
            "r": 180,
        },
        "SW": {
            "pos": (CX - 800, CY + 800),
            "label": "VesselSync\n(Feeling)",
            "color": COLOR_SATELLITE,
            "r": 180,
        },
        "SE": {
            "pos": (CX + 800, CY + 800),
            "label": "DroneLink\n(Space)",
            "color": COLOR_SATELLITE,
            "r": 180,
        },
    }

    # 3. DRAW GLOWING RELATIONSHIP AXONS
    for key in ["NW", "NE", "SW", "SE"]:
        target = focus_nodes[key]["pos"]
        # Outer glow line
        draw.line([(CX, CY), target], fill=(255, 200, 0, 100), width=30)
        # Inner truth line
        draw.line([(CX, CY), target], fill=COLOR_PRIMARY, width=10)

    # 4. DRAW FOCUS NODES
    for key, data in focus_nodes.items():
        pos = data["pos"]
        r = data["r"]
        # Draw Glow
        draw.ellipse(
            [pos[0] - r - 20, pos[1] - r - 20, pos[0] + r + 20, pos[1] + r + 20],
            outline=data["color"],
            width=10,
        )
        draw.ellipse(
            [pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r], fill=(20, 25, 30)
        )

        # Draw Labels
        draw.text(
            pos,
            data["label"],
            fill=TEXT_COLOR,
            font=font_large if key == "CENTER" else font_small,
            anchor="mm",
            align="center",
        )

    # 5. TECHNICAL FOOTER
    draw.text(
        (CX, HEIGHT - 150),
        "PEDAGOGICAL FOCUS: PRIMARY CORE RELATIONSHIPS",
        fill=COLOR_PRIMARY,
        font=font_small,
        anchor="mm",
    )

    # 6. SAVE
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Focus Plexus at: {OUTPUT_PATH}")


if __name__ == "__main__":
    draw_focus_plexus()
