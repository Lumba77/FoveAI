import os

files = [
    "/home/lumba/FoveAI/Frontend/multigate/index.html",
    "/home/lumba/FoveAI/Frontend/XR_Vessel/index.html",
    "/home/lumba/FoveAI/Frontend/Webui/index.html",
    "/home/lumba/FoveAI/Frontend/Copilot/index.html"
]

script_tag = '    <script src="http://127.0.0.1:8415/foveai_theme_sync.js"></script>\n'

for fpath in files:
    if os.path.exists(fpath):
        with open(fpath, "r") as f:
            content = f.read()
        
        if "foveai_theme_sync.js" not in content:
            # Insert before </head>
            if "</head>" in content:
                content = content.replace("</head>", script_tag + "</head>")
                with open(fpath, "w") as f:
                    f.write(content)
                print(f"Injected into {fpath}")
            else:
                print(f"No </head> found in {fpath}")
        else:
            print(f"Already injected in {fpath}")
