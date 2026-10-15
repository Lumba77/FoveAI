with open("/home/lumba/FoveAI/theme/theme_api.py", "r") as f:
    content = f.read()

if "from fastapi.responses import StreamingResponse" in content:
    content = content.replace("from fastapi.responses import StreamingResponse", "from fastapi.responses import StreamingResponse, FileResponse\nfrom fastapi.staticfiles import StaticFiles")

if "@app.post(\"/api/theme/generate\")" in content and "theme_sync.js" not in content:
    content = content.replace("@app.post(\"/api/theme/generate\")", """@app.get("/foveai_theme_sync.js")
async def get_theme_sync():
    return FileResponse("/home/lumba/FoveAI/theme/theme_sync.js")

@app.post("/api/theme/generate")""")

with open("/home/lumba/FoveAI/theme/theme_api.py", "w") as f:
    f.write(content)
