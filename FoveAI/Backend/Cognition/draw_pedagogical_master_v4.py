import os

from PIL import Image, ImageDraw, ImageFont

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 5000
BG_COLOR = (15, 18, 22)  # Professional Charcoal Navy
COLOR_JEN = (255, 255, 255)  # Pure White Core
COLOR_BODY = (0, 255, 150)  # Vibrant Green (The Organic Interface)
COLOR_DOCKER = (0, 150, 255)  # Docker Blue
COLOR_HOST = (100, 110, 130)  # Industrial Gray
TEXT_COLOR = (255, 255, 255)

OUTPUT_PATH = (
    "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_master_v4.png"
)


def draw_blueprint_v4():
    print("Drafting Vertical Master Schematic v4...")
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        font_header = ImageFont.truetype("arial.ttf", 180)
        font_title = ImageFont.truetype("arial.ttf", 120)
        font_node = ImageFont.truetype("arial.ttf", 90)
        font_text = ImageFont.truetype("arial.ttf", 55)
        font_mono = ImageFont.truetype("cour.ttf", 50)
    except:
        font_header = font_title = font_node = font_text = font_mono = (
            ImageFont.load_default()
        )

    CX, CY_TOP = WIDTH // 2, 1400  # Center of the circular diagram

    # ── 1. CIRCULAR TOPOLOGY (Upper Part) ─────────────────────────────────────

    # A. USER HOST SYSTEM (The Final boundary)
    R_HOST = 1300
    draw.ellipse(
        [CX - R_HOST, CY_TOP - R_HOST, CX + R_HOST, CY_TOP + R_HOST],
        outline=COLOR_HOST,
        width=40,
    )
    draw.text(
        (CX, CY_TOP - R_HOST - 120),
        "USER HOST SYSTEM (Quest 3 / OS / Hardware)",
        fill=COLOR_HOST,
        font=font_node,
        anchor="mb",
    )

    # B. DOCKER CONTAINER LAYER (The 3-Node Nerve)
    R_DOCKER = 1000
    draw.ellipse(
        [CX - R_DOCKER, CY_TOP - R_DOCKER, CX + R_DOCKER, CY_TOP + R_DOCKER],
        outline=COLOR_DOCKER,
        width=25,
    )
    draw.text(
        (CX, CY_TOP - R_DOCKER - 80),
        "DOCKER ARCHITECTURE (Nervous System)",
        fill=COLOR_DOCKER,
        font=font_node,
        anchor="mb",
    )

    # C. SEGMENTED BODY (Mouth, Ears, Eyes)
    R_BODY_OUTER = 750
    R_BODY_INNER = 400
    # Draw segments as arcs
    # 0-120: Eyes, 120-240: Ears, 240-360: Mouth
    draw.pieslice(
        [
            CX - R_BODY_OUTER,
            CY_TOP - R_BODY_OUTER,
            CX + R_BODY_OUTER,
            CY_TOP + R_BODY_OUTER,
        ],
        0,
        120,
        fill=(0, 100, 60),
        outline=COLOR_BODY,
        width=10,
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
        fill=(0, 80, 50),
        outline=COLOR_BODY,
        width=10,
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
        fill=(0, 60, 40),
        outline=COLOR_BODY,
        width=10,
    )

    # Segment Labels
    draw.text(
        (CX + 450, CY_TOP + 300),
        "EYES (Vision)",
        fill=COLOR_BODY,
        font=font_node,
        anchor="mm",
    )
    draw.text(
        (CX - 450, CY_TOP + 300),
        "EARS (Hearing)",
        fill=COLOR_BODY,
        font=font_node,
        anchor="mm",
    )
    draw.text(
        (CX, CY_TOP - 550),
        "MOUTH (Voice)",
        fill=COLOR_BODY,
        font=font_node,
        anchor="mm",
    )

    # D. JEN'S CORE (The One)
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

    # ── 2. THE SYNAPSE LEDGER & CROSSBLEED (Lower Part) ───────────────────────
    INFO_Y = 2900

    # Header
    draw.text(
        (CX, INFO_Y),
        "TECHNICAL SYNAPSE LEDGER",
        fill=COLOR_DOCKER,
        font=font_header,
        anchor="mm",
    )
    draw.line(
        [200, INFO_Y + 120, WIDTH - 200, INFO_Y + 120], fill=COLOR_DOCKER, width=10
    )

    # Distilled Faculty Status
    LEDGER_DATA = """
    ## FACULTY STATUS
    - MIND: HARDENED (MindCore.py Sanctuary on C: Drive)
    - EARS: HARDENED (VoiceCore.gd Buffer Validation)
    - EYES: ACTIVE (VesselSync Rolling Context)
    - ACT:  GROUNDED (StaticBody3D Floor Alignment)
    - UI:   STABLE (Blackberry Vertical Ergonomics)
    """
    draw.text((200, INFO_Y + 200), LEDGER_DATA, fill=TEXT_COLOR, font=font_text)

    # Cross-Bleed Map
    CROSSBLEED_DATA = """
    ## CROSS-BLEED MAP (DEPENDENCY AXONS)
    - [SoulSeed.gd]  -> Director, Drone, InteractionResonance
    - [Compagent.py] -> STT (8001), TTS (8001), Vision (8001)
    - [AvatarCtrl]   -> Collision Layers, Pose Scaling, Gaze
    - [VesselSync]   -> MindCore Perception, Proprioception
    """
    draw.text((1600, INFO_Y + 200), CROSSBLEED_DATA, fill=COLOR_BODY, font=font_text)

    # Evolutionary Truth
    TRUTH = "IMMUTABLE PRINCIPLE: Simple is True. The Center is One."
    draw.text((CX, HEIGHT - 200), TRUTH, fill=COLOR_HOST, font=font_node, anchor="mm")

    # ── 3. SAVE ───────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Final Pedagogical Blueprint v4 at: {OUTPUT_PATH}")


if __name__ == "__main__":
    draw_blueprint_v4()
