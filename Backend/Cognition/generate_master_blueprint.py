import requests
import base64
import os
from PIL import Image, ImageDraw, ImageFont
import io

URL = "http://localhost:8003/api/dream"

# ── 1. DRAW THE STRUCTURAL TRUTH (CANNY TEMPLATE) ────────────────────────────
def create_schematic_template():
    print("Drawing Pedagogical Template...")
    img = Image.new('RGB', (1024, 1024), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Precise Tree Nodes (Hierarchy mapping)
    nodes = {
        "FOUNDER": (512, 100),
        "ARCHITECT": (512, 300),
        "SENTRY": (200, 450),
        "JEN_CORE": (512, 600),
        "EARS": (300, 850),
        "EYES": (450, 850),
        "MOUTH": (600, 850),
        "ACT": (750, 850)
    }
    
    # Draw Axons (Lines)
    draw.line([nodes["FOUNDER"], nodes["ARCHITECT"]], fill=(255, 255, 255), width=8)
    draw.line([nodes["ARCHITECT"], nodes["SENTRY"]], fill=(255, 255, 255), width=5)
    draw.line([nodes["ARCHITECT"], nodes["JEN_CORE"]], fill=(255, 255, 255), width=10)
    for faculty in ["EARS", "EYES", "MOUTH", "ACT"]:
        draw.line([nodes["JEN_CORE"], nodes[faculty]], fill=(255, 255, 255), width=4)
        
    # Draw Circles
    for name, pos in nodes.items():
        r = 50 if "FAC" not in name else 35
        draw.ellipse([pos[0]-r, pos[1]-r, pos[0]+r, pos[1]+r], outline=(255, 255, 255), width=10)
        
    return img

# ── 2. GLOBAL GENERATION (One-ness Pass) ─────────────────────────────────────
def generate_global_diagram(template_img):
    print("Generating Unified Diagram...")
    buffered = io.BytesIO()
    template_img.save(buffered, format="PNG")
    template_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    prompt = "Professional technical infographic, flat design tree diagram, clean dark navy background, white glowing circular nodes, thick white axons, minimal sci-fi interface, high contrast, architectural blueprint style, 8k."
    
    payload = {
        "prompt": prompt,
        "model_type": "control",
        "control_image_b64": template_b64,
        "num_inference_steps": 20
    }
    
    resp = requests.post(URL, json=payload, timeout=600)
    if resp.status_code == 200:
        data = base64.b64decode(resp.json()["image_b64"])
        return Image.open(io.BytesIO(data))
    return None

# ── 3. ANNOTATION PASS (Pedagogical Labels) ─────────────────────────────────
def annotate_diagram(img):
    print("Applying Technical Labels...")
    # Scale up to 4096px for high fidelity
    img = img.resize((4096, 4096), Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    
    # Mapping labels to the scaled node positions
    labels = {
        "FOUNDER": (2048, 400, "FOUNDER (Root/Manager)"),
        "ARCHITECT": (2048, 1200, "ARCHITECT (Supervisor)"),
        "SENTRY": (800, 1800, "SENTRY (Guardian)"),
        "JEN": (2048, 2400, "THE ONE (Jen Core)"),
        "EARS": (1200, 3400, "EARS (STT)"),
        "EYES": (1800, 3400, "EYES (Vision)"),
        "MOUTH": (2400, 3400, "MOUTH (TTS)"),
        "ACT": (3000, 3400, "ACT (VR Vessel)")
    }
    
    # Try to load a clean font, fallback to default
    try: font = ImageFont.truetype("arial.ttf", 80)
    except: font = ImageFont.load_default()

    for node, data in labels.items():
        draw.text((data[0], data[1] + 150), data[2], fill=(255, 255, 255), font=font, anchor="mt")
        
    return img

# ── EXECUTION ───────────────────────────────────────────────────────────────
template = create_schematic_template()
global_img = generate_global_diagram(template)

if global_img:
    masterpiece = annotate_diagram(global_img)
    final_path = "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_master_4000px.png"
    masterpiece.save(final_path)
    print(f"Successfully manifest the Pedagogical 4000px Blueprint at: {final_path}")
