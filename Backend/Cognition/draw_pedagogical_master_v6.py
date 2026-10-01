import os

from PIL import Image, ImageDraw, ImageFont

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 5500  # Slightly taller for the Plexus
BG_COLOR = (10, 12, 15)
COLOR_JEN = (255, 255, 255)
COLOR_INTERNAL = (0, 255, 180)
COLOR_SWITCH = (0, 180, 255)
COLOR_HOST = (120, 130, 150)
COLOR_BLEED = (255, 200, 0)  # Gold for Cross-Bleed axons
TEXT_COLOR = (255, 255, 255)

OUTPUT_PATH = "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_master_v6_interconnected.png"


def draw_blueprint_v6():
    print("Drafting Master Schematic v6 (The Interconnected Ledger)...")
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font_header = ImageFont.truetype("arial.ttf", 160)
        font_title = ImageFont.truetype("arial.ttf", 110)
        font_node = ImageFont.truetype("arial.ttf", 85)
        font_text = ImageFont.truetype("arial.ttf", 55)
        font_tiny = ImageFont.truetype("arial.ttf", 35)
    except:
        font_header = font_title = font_node = font_text = font_tiny = (
            ImageFont.load_default()
        )

    CX, CY_TOP = WIDTH // 2, 1350

    # ── 1. CIRCULAR TOPOLOGY (The Mediator) ──────────────────────────────────

    # A. HOST INTERFACE (Outer)
    R_HOST = 1250
    draw.ellipse(
        [CX - R_HOST, CY_TOP - R_HOST, CX + R_HOST, CY_TOP + R_HOST],
        outline=COLOR_HOST,
        width=40,
    )
    draw.text(
        (CX, CY_TOP - R_HOST - 100),
        "NODE 3: THE HOST INTERFACE (Quest 3 / OS / Hardware)",
        fill=COLOR_HOST,
        font=font_node,
        anchor="mb",
    )

    # B. THE SWITCH (Docker Layer)
    R_SWITCH = 1000
    draw.ellipse(
        [CX - R_SWITCH, CY_TOP - R_SWITCH, CX + R_SWITCH, CY_TOP + R_SWITCH],
        outline=COLOR_SWITCH,
        width=30,
    )
    draw.text(
        (CX, CY_TOP - R_SWITCH - 60),
        "THE SWITCH (Docker: Mediation & Port Negotiation)",
        fill=COLOR_SWITCH,
        font=font_node,
        anchor="mb",
    )

    # C. INTERNAL INTERFACE (Segmented Body)
    R_BODY_OUTER = 750
    R_BODY_INNER = 400
    draw.pieslice(
        [
            CX - R_BODY_OUTER,
            CY_TOP - R_BODY_OUTER,
            CX + R_BODY_OUTER,
            CY_TOP + R_BODY_OUTER,
        ],
        0,
        120,
        fill=(0, 70, 50),
        outline=COLOR_INTERNAL,
        width=12,
    )
    draw.pieslice(
        [
            CX - R_BODY_OUTER,
            CY_TOP - R_BODY_OUTER,
            CX + R_BODY_OUTER,
            CY_TOP + R_BODY_OUTER,
        ],
        120,
        240,
        fill=(0, 50, 40),
        outline=COLOR_INTERNAL,
        width=12,
    )
    draw.pieslice(
        [
            CX - R_BODY_OUTER,
            CY_TOP - R_BODY_OUTER,
            CX + R_BODY_OUTER,
            CY_TOP + R_BODY_OUTER,
        ],
        240,
        360,
        fill=(0, 30, 30),
        outline=COLOR_INTERNAL,
        width=12,
    )

    draw.text(
        (CX + 450, CY_TOP + 250),
        "VISION",
        fill=COLOR_INTERNAL,
        font=font_node,
        anchor="mm",
    )
    draw.text(
        (CX - 450, CY_TOP + 250),
        "HEARING",
        fill=COLOR_INTERNAL,
        font=font_node,
        anchor="mm",
    )
    draw.text(
        (CX, CY_TOP - 550), "VOICE", fill=COLOR_INTERNAL, font=font_node, anchor="mm"
    )

    # D. JEN'S CORE
    draw.ellipse(
        [
            CX - R_BODY_INNER,
            CY_TOP - R_BODY_INNER,
            CX + R_BODY_INNER,
            CY_TOP + R_BODY_INNER,
        ],
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

    # ── 2. THE VISUAL CROSS-BLEED MAP (Lower Part) ───────────────────────────
    INFO_Y = 2800
    draw.text(
        (CX, INFO_Y),
        "CROSS-BLEED MAP: INTERRELATIONAL AXONS",
        fill=COLOR_BLEED,
        font=font_header,
        anchor="mm",
    )
    draw.line(
        [200, INFO_Y + 100, WIDTH - 200, INFO_Y + 100], fill=COLOR_BLEED, width=10
    )

    # Define Plexus Nodes
    plexus_nodes = {
        "SoulSeed.gd": (1500, 3400),
        "DirectorManager": (1000, 3200),
        "VesselSync": (1000, 3600),
        "Resonance": (2000, 3200),
        "DroneLink": (2000, 3600),
        "Client.gd": (1500, 4200),
        "VoiceInput": (1000, 4400),
        "Atmosphere": (2000, 4400),
        "MindCore.py": (1500, 4800),
        "compagent.py": (1000, 5000),
        "BodyInterface": (2000, 5000),
    }

    # Draw Synaptic Axons (Connections)
    connections = [
        ("SoulSeed.gd", "DirectorManager"),
        ("SoulSeed.gd", "VesselSync"),
        ("SoulSeed.gd", "Resonance"),
        ("SoulSeed.gd", "DroneLink"),
        ("Client.gd", "VoiceInput"),
        ("Client.gd", "Atmosphere"),
        ("Client.gd", "VesselSync"),
        ("MindCore.py", "compagent.py"),
        ("MindCore.py", "BodyInterface"),
    ]

    for start, end in connections:
        draw.line(
            [plexus_nodes[start], plexus_nodes[end]], fill=(100, 100, 100), width=4
        )

    # Draw Nodes & Labels
    for name, pos in plexus_nodes.items():
        is_hub = name in ["SoulSeed.gd", "Client.gd", "MindCore.py"]
        r = 100 if is_hub else 70
        draw.ellipse(
            [pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r],
            outline=COLOR_BLEED if is_hub else COLOR_HOST,
            width=8,
        )
        draw.text(
            (pos[0], pos[1]),
            name,
            fill=TEXT_COLOR,
            font=font_text if is_hub else font_tiny,
            anchor="mm",
        )

    # Instruction Note
    INSTR = (
        "INSTRUCTION: Modifying a HUB node (Gold) affects all connected faculty nodes."
    )
    draw.text((CX, 5350), INSTR, fill=COLOR_BLEED, font=font_text, anchor="mm")

    # ── 3. SAVE ───────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Interconnected Ledger Master at: {OUTPUT_PATH}")


if __name__ == "__main__":
    draw_blueprint_v6()
