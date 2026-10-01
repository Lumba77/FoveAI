import json
import os
import sys

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request

# Load ENV
FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(FoveAI_ROOT, ".env"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

app = FastAPI(
    title="Subconscious Daemon",
    description="Situational anomaly detection for proactive barge-ins",
)

gemini_client = None
gemini_chat = None

if GEMINI_API_KEY:
    try:
        from google import genai

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_chat = gemini_client.chats.create(
            model="gemini-1.5-flash",
            config={
                "system_instruction": "You are the Subconscious of an AI companion. You receive raw telemetry (pulse, steps, audio sentiment). You do NOT talk to the user. You evaluate if an anomaly requires the main AI to reach out (barge in). If yes, reply exactly with: BARGE_IN: [Reasoning]. If no, reply exactly with: IGNORE."
            },
        )
    except Exception as e:
        print(f"[Subconscious] Failed to load Gemini: {e}")


@app.post("/telemetry")
async def receive_telemetry(request: Request):
    """Receives physical/audio context and decides if a barge-in is warranted."""
    body = await request.json()
    sensor_type = body.get("sensor", "unknown")

    # Simple thresholding before invoking the LLM to save tokens
    if sensor_type == "accelerometer":
        # Check for violent shaking
        x, y, z = body.get("x", 0), body.get("y", 0), body.get("z", 0)
        magnitude = (x**2 + y**2 + z**2) ** 0.5
        if magnitude < 20.0:
            return {"status": "ignored", "reason": "normal_movement"}

    if sensor_type == "audio_sentiment":
        score = body.get("stress_score", 0.0)
        if score < 0.8:
            return {"status": "ignored", "reason": "normal_sentiment"}

    if not gemini_chat:
        return {"status": "ignored", "reason": "no_llm"}

    print(f"[Subconscious] Anomaly threshold crossed. Evaluating context: {body}")

    try:
        resp = gemini_chat.send_message(f"Telemetry: {json.dumps(body)}")
        text = resp.text.strip()
        print(f"[Subconscious] Evaluation: {text}")

        if text.startswith("BARGE_IN:"):
            reason = text.replace("BARGE_IN:", "").strip()
            # In a real setup, we would POST to soul_core to trigger the voice pipeline
            import requests

            try:
                requests.post(
                    "http://127.0.0.1:8402/api/chat",
                    json={
                        "message": f"SYSTEM_OVERRIDE: Subconscious indicates {reason}. Reach out to the user immediately."
                    },
                    timeout=2,
                )
            except:
                pass
            return {"status": "barge_in_triggered", "reason": reason}

    except Exception as e:
        print(f"[Subconscious] Eval Error: {e}")

    return {"status": "ignored"}


if __name__ == "__main__":
    print("==============================================")
    print(" 🧠 GHOST SUBCONSCIOUS - Situational Awareness")
    print("==============================================")
    try:
        import os
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from server_config import ServerConfig as cfg

        _host = cfg.BIND_HOST
        _port = cfg.SUBCONSCIOUS_PORT
    except ImportError:
        _host = os.getenv("FOVEAI_BIND_HOST", "127.0.0.1")
        _port = int(os.getenv("FOVEAI_SUBCONSCIOUS_PORT", "8111"))
    uvicorn.run(app, host=_host, port=_port, log_level="warning")
