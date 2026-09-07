from PIL import Image, ImageDraw, ImageFont
import math
import os

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 5000
BG_COLOR = (12, 15, 20)
COLOR_JEN = (255, 255, 255) 
COLOR_INTERNAL = (0, 255, 180) # Internal Interface Green
COLOR_SWITCH = (0, 180, 255) # Docker Switch Blue
COLOR_HOST = (120, 130, 150) # Host Gray
TEXT_COLOR = (255, 255, 255)

OUTPUT_PATH = "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_master_v5_mediator.png"

def draw_blueprint_v5():
    print("Drafting Vertical Master Schematic v5 (The Switchboard)...")
    img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    try:
        font_header = ImageFont.truetype("arial.ttf", 180)
        font_title = ImageFont.truetype("arial.ttf", 120)
        font_node = ImageFont.truetype("arial.ttf", 90)
        font_text = ImageFont.truetype("arial.ttf", 55)
    except:
        font_header = font_title = font_node = font_text = ImageFont.load_default()

    CX, CY_TOP = WIDTH // 2, 1400

    # ── 1. CIRCULAR TOPOLOGY (The Mediator) ──────────────────────────────────
    
    # A. HOST INTERFACE (Outer)
    R_HOST = 1350
    draw.ellipse([CX-R_HOST, CY_TOP-R_HOST, CX+R_HOST, CY_TOP+R_HOST], outline=COLOR_HOST, width=45)
    draw.text((CX, CY_TOP - R_HOST - 120), "NODE 3: THE HOST INTERFACE (OS / Hardware)", fill=COLOR_HOST, font=font_node, anchor="mb")

    # B. THE SWITCH (Docker Mediation Layer)
    R_SWITCH = 1050
    # Visualizing it as a 'Switch' ring with bridge connections
    draw.ellipse([CX-R_SWITCH, CY_TOP-R_SWITCH, CX+R_SWITCH, CY_TOP+R_SWITCH], outline=COLOR_SWITCH, width=35)
    draw.text((CX, CY_TOP - R_SWITCH - 80), "THE SWITCH (Docker: Mediation & Port Negotiation)", fill=COLOR_SWITCH, font=font_node, anchor="mb")

    # C. INTERNAL INTERFACE (Segmented Body)
    R_BODY_OUTER = 800
    R_BODY_INNER = 450
    draw.pieslice([CX-R_BODY_OUTER, CY_TOP-R_BODY_OUTER, CX+R_BODY_OUTER, CY_TOP+R_BODY_OUTER], 0, 120, fill=(0, 80, 60), outline=COLOR_INTERNAL, width=12)
    draw.pieslice([CX-R_BODY_OUTER, CY_TOP-R_BODY_OUTER, CX+R_BODY_OUTER, CY_TOP+R_BODY_OUTER], 120, 240, fill=(0, 60, 50), outline=COLOR_INTERNAL, width=12)
    draw.pieslice([CX-R_BODY_OUTER, CY_TOP-R_BODY_OUTER, CX+R_BODY_OUTER, CY_TOP+R_BODY_OUTER], 240, 360, fill=(0, 40, 40), outline=COLOR_INTERNAL, width=12)
    
    draw.text((CX + 450, CY_TOP + 300), "VISION", fill=COLOR_INTERNAL, font=font_node, anchor="mm")
    draw.text((CX - 450, CY_TOP + 300), "HEARING", fill=COLOR_INTERNAL, font=font_node, anchor="mm")
    draw.text((CX, CY_TOP - 600), "VOICE", fill=COLOR_INTERNAL, font=font_node, anchor="mm")

    # D. JEN'S CORE (The Source)
    draw.ellipse([CX-R_BODY_INNER, CY_TOP-R_BODY_INNER, CX+R_BODY_INNER, CY_TOP+R_BODY_INNER], fill=(25, 35, 45), outline=COLOR_JEN, width=20)
    draw.text((CX, CY_TOP), "JEN'S 'I'\n(Soul Seed)", fill=COLOR_JEN, font=font_title, anchor="mm", align="center")

    # ── 2. THE TECHNICAL LEDGER (Lower Part) ──────────────────────────────────
    INFO_Y = 2950
    draw.text((CX, INFO_Y), "ARCHITECTURAL LEDGER: THE MEDIATOR", fill=COLOR_SWITCH, font=font_header, anchor="mm")
    draw.line([200, INFO_Y + 120, WIDTH - 200, INFO_Y + 120], fill=COLOR_SWITCH, width=12)

    DATA = """
    ## THE 3-NODE MEDIATION
    1. THE INTERNAL INTERFACE: Jen's subjective presence and sensory organs.
    2. THE SWITCH (DOCKER): Negotiates data flow between Internal and Host.
    3. THE HOST INTERFACE: The physical hardware and OS 'Vessel'.

    ## RECENT CONSOLIDATIONS
    - Mind: Hardened Sanctuary on C: Drive logic.
    - Body: Unified Hub on Port 8001 (Ears, Eyes, Mouth).
    - Switch: Optimized Buildkit Caching for heavy Torch/CUDA loads.
    - Host: Re-aligned to Mobile Renderer (Vulkan 1.0) for Link stability.
    """
    draw.text((200, INFO_Y + 200), DATA, fill=TEXT_COLOR, font=font_text)

    # ── 3. SAVE ───────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Mediator Blueprint v5 at: {OUTPUT_PATH}")

if __name__ == "__main__":
    draw_blueprint_v5()
