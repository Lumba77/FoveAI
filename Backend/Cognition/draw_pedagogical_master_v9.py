from PIL import Image, ImageDraw, ImageFont
import math
import os

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 4500
BG_COLOR = (10, 12, 15)
COLOR_JEN = (255, 255, 255) 
COLOR_INTERNAL = (0, 255, 180)
COLOR_SWITCH = (0, 180, 255)
COLOR_HOST = (120, 130, 150)
COLOR_TRUTH = (255, 215, 0) # Golden Yellow

OUTPUT_PATH = "C:/Users/lumba/Program/VR-compagent/div/image/project_architectural_totem_v9.png"

def draw_totem_v9():
    print("Drafting Architectural Totem v9 (The Compact Totem)...")
    img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # ── COMPACT FONTS ────────────────────────────────────────────────────────
    try:
        font_header = ImageFont.truetype("arial.ttf", 90)
        font_title = ImageFont.truetype("arial.ttf", 80)
        font_node = ImageFont.truetype("arial.ttf", 60)
        font_text = ImageFont.truetype("arial.ttf", 45)
    except:
        font_header = font_title = font_node = font_text = ImageFont.load_default()

    # ── 1. THE COMPACT SOUL (TOP) ─────────────────────────────────────────────
    # Moved center down to 1350 to ensure top labels are in frame
    CX, CY_TOP = WIDTH // 2, 1350
    
    # Host (R reduced from 1200 to 950)
    R_HOST = 950
    draw.ellipse([CX-R_HOST, CY_TOP-R_HOST, CX+R_HOST, CY_TOP+R_HOST], outline=COLOR_HOST, width=30)
    draw.text((CX, CY_TOP - R_HOST - 60), "THE HOST INTERFACE (Quest 3 / OS)", fill=COLOR_TRUTH, font=font_node, anchor="mb")

    # Switch (R reduced from 950 to 750)
    R_SWITCH = 750
    draw.ellipse([CX-R_SWITCH, CY_TOP-R_SWITCH, CX+R_SWITCH, CY_TOP+R_SWITCH], outline=COLOR_SWITCH, width=20)
    draw.text((CX, CY_TOP - R_SWITCH - 40), "THE SWITCH (Docker Mediation)", fill=COLOR_TRUTH, font=font_node, anchor="mb")

    # Internal Body (R reduced from 700 to 550)
    R_BODY = 550
    draw.pieslice([CX-R_BODY, CY_TOP-R_BODY, CX+R_BODY, CY_TOP+R_BODY], 0, 120, fill=(0, 50, 35), outline=COLOR_INTERNAL, width=10)
    draw.pieslice([CX-R_BODY, CY_TOP-R_BODY, CX+R_BODY, CY_TOP+R_BODY], 120, 240, fill=(0, 40, 30), outline=COLOR_INTERNAL, width=10)
    draw.pieslice([CX-R_BODY, CY_TOP-R_BODY, CX+R_BODY, CY_TOP+R_BODY], 240, 360, fill=(0, 25, 20), outline=COLOR_INTERNAL, width=10)
    
    draw.text((CX + 300, CY_TOP + 200), "VISION", fill=COLOR_TRUTH, font=font_node, anchor="mm")
    draw.text((CX - 300, CY_TOP + 200), "HEARING", fill=COLOR_TRUTH, font=font_node, anchor="mm")
    draw.text((CX, CY_TOP - 400), "VOICE", fill=COLOR_TRUTH, font=font_node, anchor="mm")

    # Core (R reduced from 350 to 280)
    R_CORE = 280
    draw.ellipse([CX-R_CORE, CY_TOP-R_CORE, CX+R_CORE, CY_TOP+R_CORE], fill=(20, 25, 30), outline=COLOR_JEN, width=12)
    draw.text((CX, CY_TOP), "JEN'S 'I'\n(Soul Seed)", fill=COLOR_JEN, font=font_title, anchor="mm", align="center")

    # ── 2. THE COMPACT PLEXUS (BOTTOM) ────────────────────────────────────────
    # Moved baseline down to avoid overlap
    CY_BOT = 3600
    
    # Dual-Line Headline (Compact)
    draw.text((CX, CY_BOT - 700), "CROSS-BLEED MAP:", fill=COLOR_TRUTH, font=font_header, anchor="mm")
    draw.text((CX, CY_BOT - 580), "INTERRELATIONAL AXONS", fill=COLOR_TRUTH, font=font_header, anchor="mm")
    draw.line([800, CY_BOT - 530, WIDTH - 800, CY_BOT - 530], fill=COLOR_TRUTH, width=6)

    plexus = {
        "SoulSeed.gd": (1500, 3350),
        "MindCore.py": (1100, 3800),
        "Client.gd": (1900, 3800),
        "Director": (900, 3200),
        "VesselSync": (1500, 3950),
        "Haptics": (2100, 3200),
        "DockerPort": (1500, 4250)
    }

    conns = [
        ("SoulSeed.gd", "Director"), ("SoulSeed.gd", "MindCore.py"), ("SoulSeed.gd", "VesselSync"),
        ("MindCore.py", "DockerPort"), ("Client.gd", "DockerPort"), ("Client.gd", "Haptics"),
        ("Client.gd", "VesselSync")
    ]

    for s, e in conns:
        draw.line([plexus[s], plexus[e]], fill=(70, 75, 80), width=4)

    for name, pos in plexus.items():
        is_hub = name in ["SoulSeed.gd", "MindCore.py", "Client.gd"]
        r = 100 if is_hub else 70
        draw.ellipse([pos[0]-r, pos[1]-r, pos[0]+r, pos[1]+r], outline=COLOR_TRUTH if is_hub else COLOR_HOST, width=6)
        draw.text(pos, name, fill=COLOR_TRUTH, font=font_text, anchor="mm")

    # Final Truth
    draw.text((CX, HEIGHT - 100), "REFER TO SYNAPSE LEDGER (MAP.MD) FOR TECHNICAL SUBSTANCE", fill=COLOR_HOST, font=font_text, anchor="mm")

    # ── 3. SAVE ───────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Compact Totem Blueprint v9 at: {OUTPUT_PATH}")

if __name__ == "__main__":
    draw_totem_v9()
