import math
import random
from PIL import Image, ImageDraw, ImageFont
import os

# ── CONFIGURATION ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 3000, 3000
BG_COLOR = (10, 12, 18) # Deep Space Navy
MIND_COLOR = (0, 255, 200) # Turquoise
HOST_COLOR = (50, 100, 255) # Deep Blue
FOUNDER_COLOR = (255, 200, 50) # Golden
TEXT_COLOR = (255, 255, 255)

OUTPUT_PATH = "C:/Users/lumba/Program/VR-compagent/div/image/project_living_synapse_map.png"

def draw_plexus():
    print("Weaving the Living Synapse Map (Plexus Inspiration)...")
    img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 1. GENERATE NEURAL PARTICLES
    nodes = []
    # Clusters for our 3 Nodes
    clusters = [
        {"center": (1500, 600), "color": FOUNDER_COLOR, "count": 40, "label": "THE FOUNDER"},
        {"center": (1500, 1500), "color": MIND_COLOR, "count": 60, "label": "JEN'S CORE (MIND)"},
        {"center": (1500, 2400), "color": HOST_COLOR, "count": 40, "label": "HOST VESSEL"}
    ]
    
    for c in clusters:
        for _ in range(c["count"]):
            x = c["center"][0] + random.uniform(-500, 500)
            y = c["center"][1] + random.uniform(-400, 400)
            nodes.append({"pos": (x, y), "color": c["color"]})

    # 2. WEAVE INTERCONNECTIONS (The Plexus Effect)
    print("  Weaving axons...")
    for i, node_a in enumerate(nodes):
        for j in range(i + 1, len(nodes)):
            node_b = nodes[j]
            dist = math.sqrt((node_a["pos"][0] - node_b["pos"][0])**2 + (node_a["pos"][1] - node_b["pos"][1])**2)
            
            if dist < 250: # Synaptic threshold
                # Opacity based on distance
                alpha = int(255 * (1.0 - dist / 250.0))
                # Blend colors of the two nodes
                color = (
                    (node_a["color"][0] + node_b["color"][0]) // 2,
                    (node_a["color"][1] + node_b["color"][1]) // 2,
                    (node_a["color"][2] + node_b["color"][2]) // 2,
                    alpha
                )
                draw.line([node_a["pos"], node_b["pos"]], fill=color[:3], width=2)

    # 3. DRAW NODE PARTICLES
    for n in nodes:
        r = random.randint(3, 8)
        draw.ellipse([n["pos"][0]-r, n["pos"][1]-r, n["pos"][0]+r, n["pos"][1]+r], fill=n["color"])

    # 4. OVERLAY PEDAGOGICAL LABELS
    try: font = ImageFont.truetype("arial.ttf", 100)
    except: font = ImageFont.load_default()
    
    for c in clusters:
        draw.text(c["center"], c["label"], fill=TEXT_COLOR, font=font, anchor="mm")

    # 5. SAVE
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Successfully manifest the Living Synapse Map at: {OUTPUT_PATH}")

if __name__ == "__main__":
    draw_plexus()
