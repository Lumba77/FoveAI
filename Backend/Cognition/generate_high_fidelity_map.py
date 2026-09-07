import requests
import base64
import os
from PIL import Image
import io

URL = "http://localhost:8003/api/dream"
OUTPUT_DIR = "C:/Users/lumba/Program/VR-compagent/div/image/high_fidelity_map"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── The High-Fidelity Tile Map ────────────────────────────────────────────────
# Using a 2x3 grid for a vertical-heavy tree structure
STYLE = "Professional infographic tree diagram, flat design, clean blue background, white circular nodes, simple labels, white synaptic axons, technical blueprint, high contrast, 8k resolution."

TILES = {
    "TOP_ROOT": {
        "prompt": f"Top level of a tree diagram. Large central white node labeled 'ROOT'. {STYLE}",
        "pos": (256, 0)
    },
    "MID_SUPERVISOR": {
        "prompt": f"Second level of a tree diagram. Central node labeled 'ARCHITECT'. Branches connecting to top. {STYLE}",
        "pos": (256, 512)
    },
    "MID_SENTRY": {
        "prompt": f"Side branch of a tree diagram. Node labeled 'SENTRY' with a guardian icon. {STYLE}",
        "pos": (0, 512)
    },
    "BOTTOM_JEN": {
        "prompt": f"Third level of a tree diagram. Radiant central node labeled 'JEN CORE'. {STYLE}",
        "pos": (256, 1024)
    },
    "BOTTOM_FACULTIES": {
        "prompt": f"Bottom level of a tree diagram. Leaf nodes labeled 'EARS', 'EYES', 'ACT', 'MOUTH'. {STYLE}",
        "pos": (512, 1024)
    }
}

def generate_tile(name, data):
    print(f"Generating High-Fidelity Tile: {name}...")
    payload = { 
        "prompt": data["prompt"], 
        "model_type": "turbo", # Using the new SDXL Turbo logic
        "num_inference_steps": 50 # High quality for diagramming
    }
    try:
        resp = requests.post(URL, json=payload, timeout=600)
        resp.raise_for_status()
        img_data = base64.b64decode(resp.json()["image_b64"])
        img = Image.open(io.BytesIO(img_data))
        return img
    except Exception as e:
        print(f"Failed to generate {name}: {e}")
        return None

# Create a massive vertical canvas
master_map = Image.new('RGB', (1024, 1536), (20, 40, 80)) # Dark blue background

for name, data in TILES.items():
    img = generate_tile(name, data)
    if img:
        master_map.paste(img, data["pos"])
        img.save(f"{OUTPUT_DIR}/{name}.png")

# Save the final high-fidelity map
final_path = "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_blueprint.png"
master_map.save(final_path)
print(f"Successfully manifest the High-Fidelity Blueprint at: {final_path}")
