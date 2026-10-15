import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """    provenance_data = {
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
    }"""

new_block = """    provenance_data = {
        "id": uid,
        "status": "completed",
        "last_completed_step": "master_builder_json",
        "theme_name": theme_data.get("theme_name", "Untitled Theme"),
        "description": theme_data.get("_vlm_text", ""),
        "colors": colors,
        "source_image_path": img_path,
        "transcript": {
            "vlm": theme_data.get("_vlm_text", ""),
            "visionary": theme_data.get("_visionary_text", ""),
            "critic": theme_data.get("_critic_text", "")
        },
        "theme_data": {k: v for k, v in theme_data.items() if not k.startswith("_")}
    }"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched main save block successfully!")
else:
    print("Could not find block 3")
