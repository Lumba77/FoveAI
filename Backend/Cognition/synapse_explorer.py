import math
import random
import sys

from PIL import Image, ImageDraw, ImageFont

# ── ARCHITECTURAL DATA (The 'DNA' of Cross-Bleed) ───────────────────────────
NODES = {
    "SoulSeed.gd": {
        "layer": "CORE",
        "desc": "The immutable source of Jen's identity and pulse.",
        "connections": [
            "DirectorManager",
            "VesselSync",
            "InteractionResonance",
            "DroneLink",
        ],
    },
    "CompagentClient.gd": {
        "layer": "BODY",
        "desc": "The primary signal relay between Godot and the Docker Switch.",
        "connections": [
            "VoiceInputManager",
            "AtmosphereCore",
            "VesselSync",
            "BodyInterface",
        ],
    },
    "MindCore.py": {
        "layer": "CORE",
        "desc": "The sanctuary of logic and prompt synthesis on the C: Drive.",
        "connections": ["compagent.py", "BodyInterface", "Super-Ego"],
    },
    "VesselSync.gd": {
        "layer": "BODY",
        "desc": "Bridges physical tracking and sensory buffers to the Mind.",
        "connections": ["SoulSeed.gd", "CompagentClient.gd", "MindCore.py"],
    },
}

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 5000
BG_COLOR = (10, 12, 15)
COLOR_HUB = (255, 215, 0)  # Gold
COLOR_SATELLITE = (0, 255, 200)  # Turquoise
COLOR_LAYER_HL = (255, 255, 255, 50)
TEXT_COLOR = (255, 255, 255)  # White font


def generate_focus_map(target_node):
    if target_node not in NODES:
        print(f"Error: Node '{target_node}' not found in registry.")
        return

    data = NODES[target_node]
    print(f"Manifesting Synapse Explorer: Focus on {target_node}...")

    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font_xl = ImageFont.truetype("arial.ttf", 160)
        font_large = ImageFont.truetype("arial.ttf", 100)
        font_small = ImageFont.truetype("arial.ttf", 60)
    except:
        font_xl = font_large = font_small = ImageFont.load_default()

    CX = WIDTH // 2

    # ── PHASE 1: THE SOUL HIGHLIGHT (Top) ────────────────────────────────────
    CY_SOUL = 1200
    # Highlight the layer where the node lives
    layers = {"CORE": 400, "BODY": 850, "HOST": 1200}
    for l_name, r in layers.items():
        color = (255, 255, 255, 30) if l_name == data["layer"] else (50, 60, 70)
        draw.ellipse(
            [CX - r, CY_SOUL - r, CX + r, CY_SOUL + r],
            outline=color,
            width=15 if l_name == data["layer"] else 5,
        )

    draw.text(
        (CX, CY_SOUL),
        f"LAYER: {data['layer']}",
        fill=COLOR_HUB,
        font=font_large,
        anchor="mm",
    )

    # ── PHASE 2: THE RELATIONSHIP PLEXUS (Middle) ────────────────────────────
    CY_PLEXUS = 3200
    # Draw faint background plexus
    for _ in range(150):
        x, y = random.uniform(0, WIDTH), random.uniform(2200, 4200)
        draw.point((x, y), fill=(60, 60, 60))

    # Center Node (The Focus)
    draw.ellipse(
        [CX - 250, CY_PLEXUS - 250, CX + 250, CY_PLEXUS + 250],
        outline=COLOR_HUB,
        width=20,
    )
    draw.text(
        (CX, CY_PLEXUS), target_node, fill=TEXT_COLOR, font=font_large, anchor="mm"
    )

    # Satellites
    angle_step = 360 / len(data["connections"])
    for i, satellite in enumerate(data["connections"]):
        angle = math.radians(i * angle_step)
        sx = CX + math.cos(angle) * 800
        sy = CY_PLEXUS + math.sin(angle) * 800

        # Connection Axon
        draw.line([(CX, CY_PLEXUS), (sx, sy)], fill=COLOR_HUB, width=10)
        # Satellite Node
        r = 150
        draw.ellipse(
            [sx - r, sy - r, sx + r, sy + r], outline=COLOR_SATELLITE, width=10
        )
        draw.text((sx, sy), satellite, fill=TEXT_COLOR, font=font_small, anchor="mm")

    # ── PHASE 3: THE LEDGER TRUTH (Bottom) ──────────────────────────────────
    draw.text(
        (CX, 4600),
        "TECHNICAL TRUTH NODES",
        fill=COLOR_HUB,
        font=font_large,
        anchor="mm",
    )
    draw.line([200, 4700, WIDTH - 200, 4700], fill=COLOR_HUB, width=8)

    info = f"DEFINITION: {data['desc']}\n\nCROSS-BLEED IMPACT:\nModifying this node requires a Sentinel Shield update for: {', '.join(data['connections'])}"
    draw.text((200, 4800), info, fill=TEXT_COLOR, font=font_small)

    # SAVE
    output_name = f"explorer_focus_{target_node.replace('.', '_')}.png"
    final_path = f"C:/Users/lumba/Program/VR-compagent/div/image/{output_name}"
    img.save(final_path)
    print(f"Successfully manifest Synapse Explorer Map at: {final_path}")


if __name__ == "__main__":
    node = sys.argv[1] if len(sys.argv) > 1 else "SoulSeed.gd"
    generate_focus_map(node)
