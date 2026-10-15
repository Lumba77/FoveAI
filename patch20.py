import sys
import re

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """    with open(out_file, "w") as f:
        f.write(css)
    print(f"\\n✅ Saved unique raw theme bundle to: {out_file}")"""

new_block = """    with open(out_file, "w") as f:
        f.write(css)
    print(f"\\n✅ Saved unique raw theme bundle to: {out_file}")
    
    # Save Provenance Record for the Theme Gallery
    gallery_dir = os.path.join(THEME_DIR, "gallery")
    os.makedirs(gallery_dir, exist_ok=True)
    provenance_file = os.path.join(gallery_dir, f"foveai-{name}-{uid}.json")
    
    provenance_data = {
        "id": uid,
        "status": "completed",
        "last_completed_step": "master_builder_json",
        "theme_name": theme_data.get("theme_name", "Untitled Theme"),
        "description": image_description,
        "colors": colors,
        "source_image_path": img_path,
        "transcript": {
            "vlm": image_description,
            "visionary": pitch_text,
            "critic": critique_text
        },
        "theme_data": theme_data
    }
    
    with open(provenance_file, "w", encoding="utf-8") as f:
        import json
        json.dump(provenance_data, f, indent=2)
    print(f"✅ Saved Provenance Record to: {provenance_file}")"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched theme_engine.py to save the Provenance JSON!")
else:
    print("Could not find block")
