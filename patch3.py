import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """        print(f"Applied theme to {active_file}! Multigate and Settings will pick it up.")"""

new_block = """        # Bust Vite cache by updating index.html
        import time, re
        index_file = os.path.join(FOVEAI_DIR, "Frontend", "multigate", "index.html")
        try:
            with open(index_file, "r") as f:
                html = f.read()
            html = re.sub(r'href="/foveai-[^"]+" id="foveai-theme-stylesheet"', f'href="/foveai-aurora.css?v={int(time.time())}" id="foveai-theme-stylesheet"', html)
            with open(index_file, "w") as f:
                f.write(html)
            print(f"Busted cache in Multigate index.html!")
        except Exception as e:
            print(f"Failed to bust cache: {e}")
        
        print(f"Applied theme to {active_file}! Multigate and Settings will pick it up.")"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find block")
