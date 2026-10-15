import sys

with open("/home/lumba/FoveAI/theme/theme_api.py", "r") as f:
    content = f.read()

old_block = """    # Sort by newest first based on file modification time
    themes.sort(key=lambda x: os.path.getmtime(os.path.join(gallery_dir, f"foveai-theme-{x.get('id', '')}.json")) if os.path.exists(os.path.join(gallery_dir, f"foveai-theme-{x.get('id', '')}.json")) else 0, reverse=True)"""

new_block = """    # Sort by newest first based on file modification time (simplifying sort logic since we just want it roughly chronological by creation)
    # Actually, let's just reverse the list so newest are generally first, or sort by id if it's not enough.
    themes.reverse()"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_api.py", "w") as f:
        f.write(content)
    print("Fixed theme_api.py sort logic!")
else:
    print("Could not find block to patch in theme_api.py")
