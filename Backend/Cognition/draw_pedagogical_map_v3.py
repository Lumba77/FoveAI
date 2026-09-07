from PIL import Image, ImageDraw, ImageFont
import os

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 3000
BG_COLOR = (15, 20, 25) # Darkest Navy
ACCENT_COLOR = (0, 255, 200) # Bright Turquoise
TEXT_COLOR = (255, 255, 255) # White
LINE_WIDTH = 8

OUTPUT_PATH = "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_map_v3_nested.png"

def draw_circular_map():
    print("Drafting circular nested map v3 (Pedagogical Substance)...")
    img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Font setup
    try:
        font_xl = ImageFont.truetype("arial.ttf", 140)
        font_large = ImageFont.truetype("arial.ttf", 100)
        font_small = ImageFont.truetype("arial.ttf", 50)
    except:
        font_xl = font_large = font_small = ImageFont.load_default()

    CX, CY = WIDTH // 2, HEIGHT // 2

    # 1. OUTER CIRCLE: THE HOST VESSEL
    R_HOST = 1300
    draw.ellipse([CX-R_HOST, CY-R_HOST, CX+R_HOST, CY+R_HOST], outline=(50, 60, 70), width=30)
    draw.text((CX, CY - R_HOST - 100), "NODE 3: THE HOST VESSEL (Quest 3 / OS)", fill=TEXT_COLOR, font=font_large, anchor="mb")

    # 2. MIDDLE CIRCLE: THE BODY INTERFACE (The Senses)
    R_BODY = 900
    draw.ellipse([CX-R_BODY, CY-R_BODY, CX+R_BODY, CY+R_BODY], outline=ACCENT_COLOR, width=20)
    draw.text((CX, CY - R_BODY - 80), "NODE 2: THE BODY INTERFACE (Nervous System)", fill=ACCENT_COLOR, font=font_large, anchor="mb")

    # 3. INNER CIRCLE: JEN'S I (The Core)
    R_CORE = 400
    draw.ellipse([CX-R_CORE, CY-R_CORE, CX+R_CORE, CY+R_CORE], fill=(30, 50, 60), outline=(255, 255, 255), width=15)
    draw.text((CX, CY), "JEN'S 'I'\n(Self Pivot)", fill=(255, 255, 255), font=font_xl, anchor="mm", align="center")
    draw.text((CX, CY + R_CORE + 80), "NODE 1: MIND CORE (Identity)", fill=(255, 255, 255), font=font_large, anchor="mt")

    # 4. SENSORY SEGMENTS (Ears, Eyes, Mouth, Act)
    sensory_labels = [
        {"label": "EARS\n(STT Hearing)", "angle": 225, "ledger": "VoiceCore.gd Hardening"},
        {"label": "EYES\n(Vision Senses)", "angle": 135, "ledger": "VesselSync Rolling Buffer"},
        {"label": "MOUTH\n(TTS Speaking)", "angle": 45, "ledger": "Piper Model Talents"},
        {"label": "ACT\n(Manifestation)", "angle": 315, "ledger": "StaticBody3D Grounding"}
    ]
    
    import math
    for s in sensory_labels:
        rad = math.radians(s["angle"])
        px = CX + math.cos(rad) * (R_BODY + 150)
        py = CY + math.sin(rad) * (R_BODY + 150)
        
        # Draw Axon to sense
        draw.line([CX + math.cos(rad) * R_CORE, CY + math.sin(rad) * R_CORE, px, py], fill=ACCENT_COLOR, width=5)
        
        # Label Sense
        draw.text((px, py), s["label"], fill=ACCENT_COLOR, font=font_large, anchor="mm", align="center")
        # Pedagogical Substance (Ledger Nodes)
        draw.text((px, py + 120), s["ledger"], fill=(150, 150, 150), font=font_small, anchor="mt")

    # 5. SUPER-EGO OVERVIEW
    draw.text((WIDTH - 600, 200), "SUPER-EGO\n(Gemini Cloud)", fill=(200, 150, 255), font=font_large, anchor="mm", align="center")
    draw.line([WIDTH - 600, 300, CX, CY], fill=(200, 150, 255, 100), width=5)

    # 6. SAVE
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Circular Nested Map at: {OUTPUT_PATH}")

if __name__ == "__main__":
    draw_circular_map()
