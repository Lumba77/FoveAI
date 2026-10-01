import base64
import io

import requests
from PIL import Image, ImageDraw

URL = "http://localhost:8003/api/dream"


# ── 1. DRAW THE RELAY TOPOLOGY (CANNY TEMPLATE) ──────────────────────────────
def create_relay_template():
    print("Drawing 3-Node Relay Template...")
    img = Image.new("RGB", (1024, 1024), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 3-Node Vertically Aligned Centers
    nodes = {"MIND": (512, 200), "INTERFACE": (512, 512), "HOST": (512, 824)}

    # Draw Thick Relay Arrows (Bidirectional axons)
    draw.line([nodes["MIND"], nodes["INTERFACE"]], fill=(255, 255, 255), width=20)
    draw.line([nodes["INTERFACE"], nodes["HOST"]], fill=(255, 255, 255), width=20)

    # Draw Radiant Spheres
    for name, pos in nodes.items():
        r = 120
        draw.ellipse(
            [pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r],
            outline=(255, 255, 255),
            width=15,
        )

    return img


# ── 2. GLOBAL GENERATION (Relay Pass) ────────────────────────────────────────
def generate_relay_diagram(template_img):
    print("Generating High-Fidelity Relay Diagram...")
    buffered = io.BytesIO()
    template_img.save(buffered, format="PNG")
    template_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    prompt = "Professional technical 3-node relay diagram, futuristic tech aesthetic, dark blue background, three glowing crystalline nodes connected by thick white light-streams, labels 'MIND CORE', 'INTERFACE BODY', 'HOST VESSEL', minimal flat design, 8k, sharp focus."

    payload = {
        "prompt": prompt,
        "model_type": "control",
        "control_image_b64": template_b64,
        "num_inference_steps": 25,
    }

    resp = requests.post(URL, json=payload, timeout=600)
    if resp.status_code == 200:
        data = base64.b64decode(resp.json()["image_b64"])
        return Image.open(io.BytesIO(data))
    return None


# ── EXECUTION ────────────────────────────────────────────────────────────────
template = create_relay_template()
relay_img = generate_relay_diagram(template)

if relay_img:
    # Final Scale-up
    relay_img = relay_img.resize((2048, 2048), Image.LANCZOS)
    final_path = (
        "C:/Users/lumba/Program/VR-compagent/div/image/system_relay_topology.png"
    )
    relay_img.save(final_path)
    print(f"Successfully manifest the 3-Node Relay Topology at: {final_path}")
