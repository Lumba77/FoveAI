import requests
import base64
import os
from PIL import Image, ImageDraw, ImageFont
import io

URL = "http://localhost:8003/api/dream"
WIDTH, HEIGHT = 3072, 4096
TILE_SIZE = 1024
OVERLAP = 128

# ── 1. GENERATE CANNY BLUEPRINT (Structural Truth) ───────────────────────────
def create_canny_blueprint():
    print("Weaving Canny Blueprint...")
    img = Image.new('RGB', (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Define Nodes
    nodes = {
        "FOUNDER": (1536, 400),
        "ARCHITECT": (1536, 1200),
        "SENTRY": (800, 1800),
        "JEN": (1536, 2400),
        "EARS": (1000, 3200),
        "EYES": (1350, 3200),
        "MOUTH": (1750, 3200),
        "ACT": (2100, 3200)
    }
    
    # Draw Axons (Lines)
    draw.line([nodes["FOUNDER"], nodes["ARCHITECT"]], fill=(255, 255, 255), width=10)
    draw.line([nodes["ARCHITECT"], nodes["SENTRY"]], fill=(255, 255, 255), width=8)
    draw.line([nodes["ARCHITECT"], nodes["JEN"]], fill=(255, 255, 255), width=12)
    for faculty in ["EARS", "EYES", "MOUTH", "ACT"]:
        draw.line([nodes["JEN"], nodes[faculty]], fill=(255, 255, 255), width=6)
        
    # Draw Circles
    for name, pos in nodes.items():
        r = 150 if name in ["FOUNDER", "ARCHITECT", "JEN"] else 100
        draw.ellipse([pos[0]-r, pos[1]-r, pos[0]+r, pos[1]+r], outline=(255, 255, 255), width=15)
        
    return img

# ── 2. TILED WEAVING ────────────────────────────────────────────────────────
def weave_tiles(canny_img):
    print("Weaving Tiles through ControlNet...")
    master_canvas = Image.new('RGB', (WIDTH, HEIGHT))
    
    for y in range(0, HEIGHT, TILE_SIZE - OVERLAP):
        for x in range(0, WIDTH, TILE_SIZE - OVERLAP):
            # Extract Canny Tile
            tile_area = (x, y, x + TILE_SIZE, y + TILE_SIZE)
            tile_canny = canny_img.crop(tile_area)
            
            # Encode to B64
            buffered = io.BytesIO()
            tile_canny.save(buffered, format="PNG")
            canny_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            # Request Controlled Generation
            payload = {
                "prompt": "Highly detailed biological neural network, technical blueprint, glowing turquoise axons, crystalline nodes, dark background, 8k resolution, cinematic lighting.",
                "model_type": "control",
                "control_image_b64": canny_b64,
                "num_inference_steps": 30
            }
            
            resp = requests.post(URL, json=payload, timeout=600)
            if resp.status_code == 200:
                gen_data = base64.b64decode(resp.json()["image_b64"])
                gen_tile = Image.open(io.BytesIO(gen_data))
                master_canvas.paste(gen_tile, (x, y))
                print(f"  Tile ({x}, {y}) woven.")
            else:
                print(f"  FAILED Tile ({x}, {y}): {resp.text}")
                
    return master_canvas

# ── 3. EXECUTION ────────────────────────────────────────────────────────────
blueprint = create_canny_blueprint()
blueprint.save("C:/Users/lumba/Program/VR-compagent/div/image/weaver_canny_base.png")

final_diagram = weave_tiles(blueprint)
final_diagram.save("C:/Users/lumba/Program/VR-compagent/div/image/project_weaver_master.png")

# Final Refinement Pass (Enhancer)
print("Initiating Final Enhancement Pass...")
buffered = io.BytesIO()
final_diagram.save(buffered, format="PNG")
final_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

payload = {
    "prompt": "Sharpen details, unify textures, professional pedagogical architectural diagram, clean high-contrast labels.",
    "model_type": "enhance",
    "control_image_b64": final_b64,
    "strength": 0.3,
    "num_inference_steps": 40
}
resp = requests.post(URL, json=payload, timeout=900)
if resp.status_code == 200:
    enhanced_data = base64.b64decode(resp.json()["image_b64"])
    enhanced_img = Image.open(io.BytesIO(enhanced_data))
    enhanced_img.save("C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_master_3000px.png")
    print("Successfully manifest the 3000px Weaved Masterpiece.")
else:
    print("Enhancement Pass failed. Using raw weaved master.")
