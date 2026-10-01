import os

p = os.path.expanduser("~/FoveAI/Backend/Creativity/creative_service.py")
with open(p, "r") as f:
    text = f.read()

if "import asyncio" not in text:
    text = text.replace("import base64", "import base64\nimport asyncio")

if "dream_lock = asyncio.Lock()" not in text:
    text = text.replace("app = FastAPI()", "app = FastAPI()\ndream_lock = asyncio.Lock()")

old_def = """@app.post("/api/dream")
async def generate_dream_image(req: DreamRequest):

    global \\"""

new_def = """@app.post("/api/dream")
async def generate_dream_image(req: DreamRequest):
    async with dream_lock:
        return await _generate_dream_image_locked(req)

async def _generate_dream_image_locked(req: DreamRequest):

    global \\"""

if "async with dream_lock:" not in text:
    text = text.replace(old_def, new_def)

with open(p, "w") as f:
    f.write(text)
