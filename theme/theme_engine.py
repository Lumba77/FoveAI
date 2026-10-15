import os
import sys
import json
import base64
import argparse
import uuid
from typing import List, Tuple
from PIL import Image

from pipeline.config import Config
from pipeline.models import ThemeSpec
from pipeline.stages import ThemeStages
from pipeline.evaluators import ThemeEvaluator
from pipeline.renderer import ThemeRenderer

def rgb_distance(c1, c2):
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5

def extract_dominant_colors(image_path: str, num_colors: int = 4, threshold: int = 50) -> List[str]:
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((150, 150))
    pixels = list(img.getdata())
    
    counts = {}
    for p in pixels:
        counts[p] = counts.get(p, 0) + 1
        
    sorted_colors = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    
    dominant = []
    for color, count in sorted_colors:
        if len(dominant) >= num_colors:
            break
        if all(rgb_distance(color, dom) > threshold for dom in dominant):
            dominant.append(color)
            
    while len(dominant) < num_colors:
        dominant.append((50, 50, 50))
        
    return ["#{:02x}{:02x}{:02x}".format(*rgb) for rgb in dominant]

def run_asset_factory(requested_assets: List[dict]):
    print("\n\n🏭 [ASSET FACTORY] Generating requested visual elements...", flush=True)
    for asset in requested_assets:
        print(f"   [+] Generating '{asset.get('name')}'...")
        print(f"       -> Prompt: {asset.get('prompt')}")
        print(f"       -> Transparent: {asset.get('make_transparent')}")

def get_schema_json() -> str:
    schema_path = os.path.join(Config.THEME_DIR, "FoveAIThemeSchema.json")
    try:
        with open(schema_path, "r") as f:
            return f.read()
    except Exception:
        return "{}"

def main():
    parser = argparse.ArgumentParser(description="FoveAI Theme Engine - Orchestrator")
    parser.add_argument("image_path", help="Path to the source image")
    parser.add_argument("--variants", type=int, default=1, help="Number of structural variants to explore")
    parser.add_argument("--apply", action="store_true", help="Apply as the active foveai-aurora.css")
    args = parser.parse_args()

    if not os.path.exists(args.image_path):
        print(f"Error: File {args.image_path} not found.")
        sys.exit(1)

    print(f"Extracting colors from {args.image_path}...")
    colors_hex = extract_dominant_colors(args.image_path)
    print(f"Extracted 4 dominant colors: {', '.join(colors_hex)}")
    
    stages = ThemeStages()
    
    # 1. Image Analysis (Run once)
    with open(args.image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    image_description = stages.analyze_image(img_b64)
    
    schema_json = get_schema_json()
    
    candidates = []
    archetypes = ["radical", "brutalist", "soft-rounded", "isometric", "holographic"]
    
    # Generate K variants
    num_variants = min(args.variants, len(archetypes))
    for i in range(num_variants):
        archetype = archetypes[i]
        print(f"\n\n{'='*40}\n🚀 GENERATING VARIANT {i+1}/{num_variants}: {archetype.upper()}\n{'='*40}")
        
        # 2. Visionary Pitch
        pitch = stages.pitch_concept(colors_hex, image_description, archetype)
        
        # 3. Critique
        critique = stages.critique_concept(pitch)
        
        # 4. Visionary Refine
        refined = stages.refine_concept(pitch, pitch, critique)
        
        # 5. Master Builder
        raw_json = stages.build_json(colors_hex, refined, schema_json)
        
        if raw_json:
            try:
                # Pydantic validation
                theme_spec = ThemeSpec(**raw_json)
                
                # 6. Evaluate
                scores = ThemeEvaluator.evaluate(theme_spec.model_dump())
                theme_spec.scores = scores
                
                # Attach provenance
                theme_spec._vlm_text = image_description
                theme_spec._visionary_text = refined
                theme_spec._critic_text = critique
                
                candidates.append(theme_spec)
                print(f"\n✅ Variant '{archetype}' generated and scored: {scores.get('overall', 0):.2f}/1.0")
            except Exception as e:
                print(f"\n❌ Validation failed for variant '{archetype}': {e}")
        else:
            print(f"\n❌ Master Builder failed to return JSON for '{archetype}'.")

    if not candidates:
        print("\n❌ Failed to generate any valid candidates. Exiting.")
        sys.exit(1)
        
    # Pick the best candidate based on overall score
    best_candidate = max(candidates, key=lambda c: c.scores.get("overall", 0) if c.scores else 0)
    
    name = best_candidate.theme_name.replace(" ", "-").lower()
    print("\n" + "="*80)
    print(f"🎨 WINNING THEME: {name.upper()} (Score: {best_candidate.scores.get('overall', 0):.2f})")
    print("="*80)
    
    if best_candidate.requested_assets:
        run_asset_factory(best_candidate.requested_assets)
        
    # Generate CSS
    css = ThemeRenderer.generate_css(best_candidate)

    uid = uuid.uuid4().hex[:8]
    out_file = os.path.join(Config.THEME_DIR, f"foveai-{name}-{uid}.css")
    with open(out_file, "w") as f:
        f.write(css)
    print(f"\n✅ Saved unique raw theme CSS bundle to: {out_file}")
    
    os.makedirs(Config.GALLERY_DIR, exist_ok=True)
    provenance_file = os.path.join(Config.GALLERY_DIR, f"foveai-{name}-{uid}.json")
    
    prov_dict = best_candidate.model_dump(exclude={"_vlm_text", "_visionary_text", "_critic_text"})
    prov_dict["source_image_path"] = args.image_path
    prov_dict["transcript"] = {
        "vlm": best_candidate._vlm_text,
        "visionary_refined": best_candidate._visionary_text,
        "critic": best_candidate._critic_text
    }
    
    with open(provenance_file, "w", encoding="utf-8") as f:
        json.dump(prov_dict, f, indent=2)
    print(f"✅ Saved Provenance Record to: {provenance_file}")
    
    # Save all candidates for inspection
    candidates_dir = os.path.join(Config.GALLERY_DIR, f"foveai-{name}-{uid}_candidates")
    os.makedirs(candidates_dir, exist_ok=True)
    for idx, cand in enumerate(candidates):
        c_file = os.path.join(candidates_dir, f"candidate_{idx}.json")
        with open(c_file, "w", encoding="utf-8") as f:
            json.dump(cand.model_dump(exclude={"_vlm_text", "_visionary_text", "_critic_text"}), f, indent=2)
            
    print("\n✅ Multigate UI applying the theme dynamically via CSS root injection.")
    print("\n___FOVEAI_THEME_JSON_START___\n" + best_candidate.model_dump_json(indent=2))

if __name__ == "__main__":
    main()
