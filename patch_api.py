import sys

with open("/home/lumba/FoveAI/theme/theme_api.py", "r") as f:
    content = f.read()

old_block = """    return StreamingResponse(stream_generator(), media_type="text/plain")

if __name__ == "__main__":"""

new_block = """    return StreamingResponse(stream_generator(), media_type="text/plain")

@app.get("/api/themes")
async def get_themes():
    import glob
    import json
    gallery_dir = "/home/lumba/FoveAI/theme/gallery"
    themes = []
    if os.path.exists(gallery_dir):
        for fpath in glob.glob(os.path.join(gallery_dir, "*.json")):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    themes.append(data)
            except Exception as e:
                print(f"Failed to load {fpath}: {e}")
    # Sort by newest first based on file modification time
    themes.sort(key=lambda x: os.path.getmtime(os.path.join(gallery_dir, f"foveai-theme-{x.get('id', '')}.json")) if os.path.exists(os.path.join(gallery_dir, f"foveai-theme-{x.get('id', '')}.json")) else 0, reverse=True)
    return {"themes": themes}

if __name__ == "__main__":"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_api.py", "w") as f:
        f.write(content)
    print("Patched theme_api.py!")
else:
    print("Could not find block to patch in theme_api.py")
