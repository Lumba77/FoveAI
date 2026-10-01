import json
import os

manifest_path = os.path.expanduser("~/FoveAI/Frontend/multigate/public/themes/manifest.json")
with open(manifest_path, "r") as f:
    data = json.load(f)

new_themes = [
    {"id": "designer-deep-slate-neural", "src": "Designer1.png"},
    {"id": "designer-glass", "src": "Designer1.png"},
    {"id": "designer-ember", "src": "Designer1.png"}
]

ids = {x["id"] for x in data}
for t in new_themes:
    if t["id"] not in ids:
        data.append(t)

with open(manifest_path, "w") as f:
    json.dump(data, f, indent=1)
