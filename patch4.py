import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """    try:
        resp = requests.post("http://127.0.0.1:8400/v1/chat/completions", json=payload, headers={"Authorization": "Bearer theme_engine"})
        if hasattr(resp, 'status_code') and resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content']"""

new_block = """    try:
        # BYPASS Foveated Proxy completely to avoid workspace ring-injection bloat!
        # Send it directly to Nvidia NIM API which finishes in 2 seconds.
        headers = {
            "Authorization": "Bearer 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",
            "Content-Type": "application/json"
        }
        resp = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=payload, headers=headers)
        if hasattr(resp, 'status_code') and resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content']"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find block")
