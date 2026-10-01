import os

from PIL import Image, ImageDraw, ImageFont

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 4500
BG_COLOR = (10, 12, 15)
COLOR_JEN = (255, 255, 255)
COLOR_INTERNAL = (0, 255, 180)
COLOR_SWITCH = (0, 180, 255)
COLOR_HOST = (120, 130, 150)
COLOR_HUB = (255, 215, 0)  # Gold
TEXT_COLOR = (255, 255, 255)

OUTPUT_PATH = (
    "C:/Users/lumba/Program/VR-compagent/div/image/project_architectural_totem_v7.png"
)


def draw_totem():
    print("Drafting Architectural Totem v7 (The Final Truth)...")
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font_header = ImageFont.truetype("arial.ttf", 140)
        font_title = ImageFont.truetype("arial.ttf", 100)
        font_node = ImageFont.truetype("arial.ttf", 80)
        font_text = ImageFont.truetype("arial.ttf", 50)
    except:
        font_header = font_title = font_node = font_text = ImageFont.load_default()

    # ── 1. THE CONCENTRIC SOUL (TOP) ──────────────────────────────────────────
    CX, CY_TOP = WIDTH // 2, 1300

    # Host
    R_HOST = 1200
    draw.ellipse(
        [CX - R_HOST, CY_TOP - R_HOST, CX + R_HOST, CY_TOP + R_HOST],
        outline=COLOR_HOST,
        width=35,
    )
    draw.text(
        (CX, CY_TOP - R_HOST - 80),
        "THE HOST INTERFACE (Quest 3 / OS)",
        fill=COLOR_HOST,
        font=font_node,
        anchor="mb",
    )

    # Switch
    R_SWITCH = 950
    draw.ellipse(
        [CX - R_SWITCH, CY_TOP - R_SWITCH, CX + R_SWITCH, CY_TOP + R_SWITCH],
        outline=COLOR_SWITCH,
        width=25,
    )
    draw.text(
        (CX, CY_TOP - R_SWITCH - 60),
        "THE SWITCH (Docker Mediation)",
        fill=COLOR_SWITCH,
        font=font_node,
        anchor="mb",
    )

    # Internal Body (Segmented)
    R_BODY = 700
    draw.pieslice(
        [CX - R_BODY, CY_TOP - R_BODY, CX + R_BODY, CY_TOP + R_BODY],
        0,
        120,
        fill=(0, 60, 45),
        outline=COLOR_INTERNAL,
        width=10,
    )
    draw.pieslice(
        [CX - R_BODY, CY_TOP - R_BODY, CX + R_BODY, CY_TOP + R_BODY],
        120,
        240,
        fill=(0, 45, 35),
        outline=COLOR_INTERNAL,
        width=10,
    )
    draw.pieslice(
        [CX - R_BODY, CY_TOP - R_BODY, CX + R_BODY, CY_TOP + R_BODY],
        240,
        360,
        fill=(0, 30, 25),
        outline=COLOR_INTERNAL,
        width=10,
    )

    draw.text(
        (CX + 400, CY_TOP + 250),
        "VISION",
        fill=COLOR_INTERNAL,
        font=font_node,
        anchor="mm",
    )
    draw.text(
        (CX - 400, CY_TOP + 250),
        "HEARING",
        fill=COLOR_INTERNAL,
        font=font_node,
        anchor="mm",
    )
    draw.text(
        (CX, CY_TOP - 500), "VOICE", fill=COLOR_INTERNAL, font=font_node, anchor="mm"
    )

    # Core
    R_CORE = 350
    draw.ellipse(
        [CX - R_CORE, CY_TOP - R_CORE, CX + R_CORE, CY_TOP + R_CORE],
        fill=(20, 30, 40),
        outline=COLOR_JEN,
        width=15,
    )
    draw.text(
        (CX, CY_TOP),
        "JEN'S 'I'\n(Soul Seed)",
        fill=COLOR_JEN,
        font=font_title,
        anchor="mm",
        align="center",
    )

    # ── 2. THE INTERRELATIONAL PLEXUS (BOTTOM) ───────────────────────────────
    CY_BOT = 3400
    draw.text(
        (CX, CY_BOT - 600),
        "CROSS-BLEED MAP: INTERRELATIONAL AXONS",
        fill=COLOR_HUB,
        font=font_header,
        anchor="mm",
    )
    draw.line([400, CY_BOT - 500, WIDTH - 400, CY_BOT - 500], fill=COLOR_HUB, width=8)

    plexus = {
        "SoulSeed.gd": (1500, 3300),
        "MindCore.py": (1000, 3800),
        "Client.gd": (2000, 3800),
        "Director": (800, 3100),
        "VesselSync": (1500, 3900),
        "Haptics": (2200, 3100),
        "DockerPort": (1500, 4300),
    }

    conns = [
        ("SoulSeed.gd", "Director"),
        ("SoulSeed.gd", "MindCore.py"),
        ("SoulSeed.gd", "VesselSync"),
        ("MindCore.py", "DockerPort"),
        ("Client.gd", "DockerPort"),
        ("Client.gd", "Haptics"),
        ("Client.gd", "VesselSync"),
    ]

    for s, e in conns:
        draw.line([plexus[s], plexus[e]], fill=(80, 85, 90), width=5)

    for name, pos in plexus.items():
        is_hub = name in ["SoulSeed.gd", "MindCore.py", "Client.gd"]
        r = 120 if is_hub else 80
        draw.ellipse(
            [pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r],
            outline=COLOR_HUB if is_hub else COLOR_HOST,
            width=8,
        )
        draw.text(
            pos,
            name,
            fill=TEXT_COLOR,
            font=font_text if is_hub else font_text,
            anchor="mm",
        )

    # Final Truth
    draw.text(
        (CX, HEIGHT - 150),
        "REFER TO SYNAPSE LEDGER (MAP.MD) FOR TECHNICAL SUBSTANCE",
        fill=COLOR_HOST,
        font=font_text,
        anchor="mm",
    )

    # ── 3. SAVE ───────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Architectural Totem v7 at: {OUTPUT_PATH}")


if __name__ == "__main__":
    draw_totem()
