from PIL import Image, ImageDraw, ImageFont
import math
import os

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3500, 3500
BG_COLOR = (10, 15, 20)
ACCENT_BLUE = (0, 255, 200) # Turquoise
ACCENT_GOLD = (255, 215, 0)
ACCENT_PURPLE = (200, 100, 255)
TEXT_COLOR = (255, 255, 255)

OUTPUT_PATH = "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_ledger_master.png"

def draw_full_blueprint():
    print("Drafting Comprehensive Ledger Blueprint (Technical Reality)...")
    img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    try:
        font_title = ImageFont.truetype("arial.ttf", 160)
        font_node = ImageFont.truetype("arial.ttf", 100)
        font_label = ImageFont.truetype("arial.ttf", 60)
        font_small = ImageFont.truetype("arial.ttf", 40)
    except:
        font_title = font_node = font_label = font_small = ImageFont.load_default()

    CX, CY = WIDTH // 2, HEIGHT // 2

    # 1. THE 3 CONCENTRIC CIRCLES (The Architecture)
    draw.ellipse([CX-1600, CY-1600, CX+1600, CY+1600], outline=(40, 50, 60), width=40) # HOST
    draw.ellipse([CX-1100, CY-1100, CX+1100, CY+1100], outline=ACCENT_BLUE, width=30) # BODY
    draw.ellipse([CX-500, CY-500, CX+500, CY+500], fill=(20, 35, 45), outline=(255, 255, 255), width=20) # CORE

    # 2. THE CORE NODES (backend/Identity)
    draw.text((CX, CY - 100), "JEN'S 'I'\n(Self Pivot)", fill=TEXT_COLOR, font=font_node, anchor="mm", align="center")
    draw.text((CX, CY + 100), "MindCore.py\n(The Sanctuary)", fill=ACCENT_BLUE, font=font_label, anchor="mm", align="center")
    draw.text((CX, CY + 250), "SoulSeed.gd\n(The Seed)", fill=ACCENT_GOLD, font=font_label, anchor="mm", align="center")

    # 3. THE SENSORY NODES (Nervous System)
    # Positions around the Body Ring
    senses = {
        "EARS": {"angle": 225, "ledger": "VoiceCore.gd\n(Hardened)", "bleed": ["SoulSeed", "Client"]},
        "EYES": {"angle": 135, "ledger": "VesselSync\n(Rolling Buffer)", "bleed": ["MindCore"]},
        "MOUTH": {"angle": 45, "ledger": "Piper TTS\n(Vocal Faculty)", "bleed": ["SoulSeed"]},
        "ACT": {"angle": 315, "ledger": "StaticBody3D\n(Physics Grounding)", "bleed": ["AvatarController"]}
    }

    for name, data in senses.items():
        rad = math.radians(data["angle"])
        px = CX + math.cos(rad) * 1100
        py = CY + math.sin(rad) * 1100
        
        # Draw Node Circle
        r = 200
        draw.ellipse([px-r, py-r, px+r, py+r], fill=(30, 40, 50), outline=ACCENT_BLUE, width=10)
        draw.text((px, py - 40), name, fill=TEXT_COLOR, font=font_node, anchor="mm")
        draw.text((px, py + 60), data["ledger"], fill=ACCENT_BLUE, font=font_small, anchor="mm", align="center")

    # 4. CROSS-BLEED MAP (Dependency Axons)
    # Drawing colored lines to represent high-impact dependencies
    def draw_axon(start_pos, end_pos, color):
        draw.line([start_pos, end_pos], fill=color, width=5)

    # Example: SoulSeed Bleed (Center to Senses)
    draw_axon((CX, CY), (CX + math.cos(math.radians(225))*900, CY + math.sin(math.radians(225))*900), ACCENT_GOLD)
    draw_axon((CX, CY), (CX + math.cos(math.radians(315))*900, CY + math.sin(math.radians(315))*900), ACCENT_GOLD)

    # 5. TECHNICAL ANNOTATIONS (Leger Substance)
    draw.text((WIDTH - 800, 400), "SYNAPSE LEDGER: DISTILLED STATUS", fill=ACCENT_BLUE, font=font_label)
    draw.text((WIDTH - 800, 500), "- Mind: Hardened (Sanctuary)\n- Ears: Hardened (Validation)\n- Eyes: Active (Rolling Buffer)\n- Act: Grounded (Physics)\n- UI: Stable (Blackberry)", fill=TEXT_COLOR, font=font_small)

    draw.text((200, 400), "CROSS-BLEED MAP (Hot Logic)", fill=ACCENT_GOLD, font=font_label)
    draw.text((200, 500), "- SoulSeed -> Director, Drone, Sync\n- Client -> Voice, Atmosphere, Sync\n- AvatarCtrl -> Collision, Pivot\n- MindCore -> API, Vessels", fill=TEXT_COLOR, font=font_small)

    # 6. HEAD TITLES
    draw.text((CX, 150), "VR-COMPAGENT: ARCHITECTURAL SOUL", fill=TEXT_COLOR, font=font_title, anchor="mt")
    draw.text((CX, HEIGHT - 150), "NODE 3: HOST VESSEL (Quest 3 / OS Manifestation)", fill=(100, 120, 140), font=font_node, anchor="mb")

    # 7. SAVE
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Pedagogical Ledger Master at: {OUTPUT_PATH}")

if __name__ == "__main__":
    draw_full_blueprint()
