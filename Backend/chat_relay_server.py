"""
Backend/chat_relay_server.py — 4-Way XR Chat Relay
====================================================
WebSocket hub that broadcasts chat messages between all participants:
  - You (the user, via terminal or XR input)
  - Jen (the avatar, via XRLF LLM on port 8402)
  - Devin (via CLI client)
  - Antigravity (via CLI client)

Port: 8407 (FOVEAI_BACKEND_PORT_CHAT, configurable via .env)

Message format (JSON):
  {"from": "user|jen|devin|antigravity", "text": "...", "time": "ISO timestamp"}

Connect:
  ws://127.0.0.1:8407/ws   — WebSocket for chat clients
  http://127.0.0.1:8407/health  — health check
  http://127.0.0.1:8407/history — recent message history (JSON)
"""

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

PORT_CHAT: int = int(os.getenv("FOVEAI_BACKEND_PORT_CHAT", 8407))
MAX_HISTORY: int = 200

app: FastAPI = FastAPI(title="FoveAI Chat Relay")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connected clients
_clients: Set[WebSocket] = set()
# Message history (in-memory, capped)
_history: List[Dict[str, Any]] = []


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "chat_relay",
        "port": PORT_CHAT,
        "clients": len(_clients),
        "messages": len(_history),
    }


@app.get("/history")
async def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent chat messages, newest last."""
    n: int = min(limit, len(_history))
    return _history[-n:]


async def _broadcast(message: Dict[str, Any]) -> None:
    """Send a message to all connected clients."""
    raw: str = json.dumps(message)
    dead: List[WebSocket] = []
    for ws in _clients:
        try:
            await ws.send_text(raw)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


def _store_and_broadcast(message: Dict[str, Any]) -> None:
    """Store message in history and schedule broadcast."""
    _history.append(message)
    if len(_history) > MAX_HISTORY:
        _history.pop(0)
    asyncio.ensure_future(_broadcast(message))


@app.websocket("/ws")
async def chat_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)

    # Send recent history to new client
    if _history:
        await websocket.send_text(json.dumps({
            "type": "history",
            "messages": _history[-50:],
        }))

    try:
        while True:
            data: str = await websocket.receive_text()
            try:
                msg: Dict[str, Any] = json.loads(data)
            except json.JSONDecodeError:
                msg = {"from": "unknown", "text": data}

            # Normalize and timestamp
            msg["time"] = _now()
            msg.setdefault("from", "unknown")
            msg.setdefault("text", "")
            msg["type"] = "chat"

            _store_and_broadcast(msg)

    except WebSocketDisconnect:
        _clients.discard(websocket)
    except Exception:
        _clients.discard(websocket)


@app.post("/send")
async def send_message(message: Dict[str, Any]) -> Dict[str, str]:
    """HTTP endpoint to send a message without WebSocket (for scripts/agents)."""
    msg: Dict[str, Any] = {
        "type": "chat",
        "from": message.get("from", "unknown"),
        "text": message.get("text", ""),
        "time": _now(),
    }
    _store_and_broadcast(msg)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    print(f"[Chat Relay] Starting on port {PORT_CHAT}")
    print(f"[Chat Relay] WebSocket: ws://127.0.0.1:{PORT_CHAT}/ws")
    print(f"[Chat Relay] HTTP send: http://127.0.0.1:{PORT_CHAT}/send")
    print(f"[Chat Relay] History:   http://127.0.0.1:{PORT_CHAT}/history")
    uvicorn.run(app, host="0.0.0.0", port=PORT_CHAT, log_level="warning")
