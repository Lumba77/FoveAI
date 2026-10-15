import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """    if args.apply:
        active_file = os.path.join(THEME_DIR, "foveai-aurora.css")
        with open(active_file, "w") as f:
            f.write(css)
        print(f"Applied theme to {active_file}! Multigate and Settings will pick it up.")"""

new_block = """    if args.apply:
        import shutil
        active_file = os.path.join(THEME_DIR, "foveai-aurora.css")
        with open(active_file, "w") as f:
            f.write(css)
        # Force it into the frontend public directories where Vite actually looks for it
        try:
            shutil.copy(active_file, os.path.join(FOVEAI_DIR, "Frontend", "multigate", "public", "foveai-aurora.css"))
            shutil.copy(active_file, os.path.join(FOVEAI_DIR, "Frontend", "3D_Avatar_Chatbot", "foveai-aurora.css"))
        except Exception as e:
            print(f"Failed to copy to frontend: {e}")
        print(f"Applied theme to {active_file}! Multigate and Settings will pick it up.")"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find block")
