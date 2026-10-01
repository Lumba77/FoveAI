import base64
import io
import os

import requests
from PIL import Image

URL = "http://localhost:8003/api/dream"
OUTPUT_DIR = "C:/Users/lumba/Program/VR-compagent/div/image/pedagogical_map"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── The Quadrant Map ──────────────────────────────────────────────────────────
# We define specific prompts for each "Level" of the tree
QUADRANTS = {
    "1_ROOT_FOUNDER": {
        "prompt": "Top-down view of a massive biological neural root system. At the center is 'The Founder', a radiant golden source node labeled 'MANAGER'. Glowing turquoise axons branch upwards. Hyper-detailed technical schematic, dark aesthetic.",
        "pos": (0, 0),
    },
    "2_TRUNK_ARCHITECT": {
        "prompt": "The central trunk of a digital consciousness tree. A massive crystalline node labeled 'GEMINI ARCHITECT'. Shimmering geometric patterns and code-streams flowing through the trunk. Glowing turquoise axons, cyberpunk blueprint style.",
        "pos": (512, 0),
    },
    "3_BRANCH_SENTRY": {
        "prompt": "A major branch of a biological neural tree. A node labeled 'SENTRY AGENT' with a sharp-eyed avian guardian. Labeled connections to 'SYNAPSE LEDGER' archives. Dark background, glowing turquoise and white highlights.",
        "pos": (0, 512),
    },
    "4_BLOOM_JEN": {
        "prompt": "The radiant bloom at the center of a neural tree. A beautiful glowing soul node labeled 'THE ONE: JEN'. Labeled faculty branches: EARS, EYES, MOUTH, ACT. Harmonious biological manifestation, golden and turquoise light.",
        "pos": (512, 512),
    },
}


def generate_quadrant(name, data):
    print(f"Generating Quadrant: {name}...")
    payload = {"prompt": data["prompt"], "model_type": "pastel"}
    try:
        resp = requests.post(URL, json=payload, timeout=300)
        resp.raise_for_status()
        img_data = base64.b64decode(resp.json()["image_b64"])
        img = Image.open(io.BytesIO(img_data))
        return img
    except Exception as e:
        print(f"Failed to generate {name}: {e}")
        return None


# Create a massive canvas
master_map = Image.new("RGB", (1024, 1024), (10, 10, 10))

for name, data in QUADRANTS.items():
    img = generate_quadrant(name, data)
    if img:
        master_map.paste(img, data["pos"])
        img.save(f"{OUTPUT_DIR}/{name}.png")

# Save the final consolidated map
final_path = "C:/Users/lumba/Program/VR-compagent/div/image/project_pedagogical_map.png"
master_map.save(final_path)
print(f"Successfully manifest the Pedagogical Instruction Map at: {final_path}")
