import os
import glob

# Find all HTML files, ignoring node_modules, .venv, .git
def find_htmls(root_dir):
    matches = []
    for root, dirs, files in os.walk(root_dir):
        if 'node_modules' in dirs: dirs.remove('node_modules')
        if '.venv' in dirs: dirs.remove('.venv')
        if '.git' in dirs: dirs.remove('.git')
        if 'client_quest' in dirs: dirs.remove('client_quest') # Unity has its own thing
        for file in files:
            if file.endswith(".html"):
                matches.append(os.path.join(root, file))
    return matches

html_files = find_htmls("/home/lumba/FoveAI")
script_tag = '    <script src="http://127.0.0.1:8415/foveai_theme_sync.js"></script>\n'
count = 0

for fpath in html_files:
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        
        if "foveai_theme_sync.js" not in content and "</head>" in content:
            content = content.replace("</head>", script_tag + "</head>")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            count += 1
            print(f"Injected into {fpath}")
    except Exception as e:
        print(f"Error reading {fpath}: {e}")

print(f"Injected into {count} new HTML files.")
