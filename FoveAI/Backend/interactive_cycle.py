import asyncio
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Load the biological cycle port map from the local .env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)

# Extract the ports from the .env
PORT_SIGHT = int(os.getenv("FOVEAI_BACKEND_PORT_SIGHT", 8400))
PORT_HEARING = int(os.getenv("FOVEAI_BACKEND_PORT_HEARING", 8401))
PORT_CONTEMPLATION = int(os.getenv("FOVEAI_BACKEND_PORT_CONTEMPLATION", 8402))
PORT_SPEECH = int(os.getenv("FOVEAI_BACKEND_PORT_SPEECH", 8403))
PORT_BODY = int(os.getenv("FOVEAI_BACKEND_PORT_BODY", 8404))
PORT_SUB_IN = int(os.getenv("FOVEAI_BACKEND_PORT_SUBCONSCIOUS_IN", 8405))
PORT_SUB_OUT = int(os.getenv("FOVEAI_BACKEND_PORT_SUBCONSCIOUS_OUT", 8406))

# Define the Microservice Apps
app_sight = FastAPI(title="Sight Nerve (Vision Stream)")
app_hearing = FastAPI(title="Hearing Nerve (STT Stream)")
app_contemplation = FastAPI(title="Frontal Lobe (XRLF Base API)")
app_speech = FastAPI(title="Speech Nerve (TTS Stream)")
app_body = FastAPI(title="Body Language Nerve (Animation Stream)")
app_sub_in = FastAPI(title="Subconscious IN (Director)")
app_sub_out = FastAPI(title="Subconscious OUT (State)")


# --- BASE API (Port 8402 - Contemplation) ---
@app_contemplation.get("/")
async def root():
    return {"status": "online", "identity": "XRLF_Omni_Model", "role": "Frontal Lobe"}


@app_contemplation.post("/v1/chat/completions")
async def chat_completions():
    # This will hook directly into the .xrlf bundle logic
    return {"message": "OpenAI-compatible endpoint active. Awaiting XRLF core."}


# --- SENSORY STREAMS (WebSockets) ---
@app_sight.websocket("/ws")
async def ws_sight(websocket: WebSocket):
    await websocket.accept()
    print("[8400] Optical Nerve connected to Quest.")
    try:
        while True:
            data = await websocket.receive_bytes()
            # Feed raw video frame directly to XRLF multimodal projector
    except WebSocketDisconnect:
        print("[8400] Optical Nerve disconnected.")


@app_hearing.websocket("/ws")
async def ws_hearing(websocket: WebSocket):
    await websocket.accept()
    print("[8401] Auditory Nerve connected to Quest.")
    try:
        while True:
            data = await websocket.receive_bytes()
            # Feed raw PCM audio directly to XRLF STT engine
    except WebSocketDisconnect:
        print("[8401] Auditory Nerve disconnected.")


@app_speech.websocket("/ws")
async def ws_speech(websocket: WebSocket):
    await websocket.accept()
    print("[8403] Vocal Cords connected to Quest.")
    # Stream TTS audio back to Quest here


@app_body.websocket("/ws")
async def ws_body(websocket: WebSocket):
    await websocket.accept()
    print("[8404] Motor Cortex connected to Quest.")
    # Stream Blendshapes back to Quest here


async def run_server(app, port):
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def ignite_interactive_cycle():
    print("🦋 Igniting XRLF Interactive Cycle (One Model Philosophy)...")
    print(f"👁️  SIGHT: {PORT_SIGHT}")
    print(f"👂 HEARING: {PORT_HEARING}")
    print(f"🧠 CONTEMPLATION: {PORT_CONTEMPLATION}")
    print(f"🗣️  SPEECH: {PORT_SPEECH}")
    print(f"💃 BODY: {PORT_BODY}")
    print(f"🔮 SUBCONSCIOUS IN: {PORT_SUB_IN}")
    print(f"📡 SUBCONSCIOUS OUT: {PORT_SUB_OUT}")

    # Spin up all 7 biological ports concurrently
    await asyncio.gather(
        run_server(app_sight, PORT_SIGHT),
        run_server(app_hearing, PORT_HEARING),
        run_server(app_contemplation, PORT_CONTEMPLATION),
        run_server(app_speech, PORT_SPEECH),
        run_server(app_body, PORT_BODY),
        run_server(app_sub_in, PORT_SUB_IN),
        run_server(app_sub_out, PORT_SUB_OUT),
    )


if __name__ == "__main__":
    asyncio.run(ignite_interactive_cycle())
