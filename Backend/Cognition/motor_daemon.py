"""
Motor Cortex Daemon — Node 5 in the Concordia Fleet
Port: 8110 | Service: Subconscious Motor Cortex (LM Studio SDK bridge)

Wraps motor_cortex.py tool schemas behind a FastAPI service so the
Sleipnir launcher can spawn it as a managed worker node.
"""
import json
import sys
import os
from typing import Dict, Any

# Ensure sibling imports work when spawned from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

from motor_cortex import get_motor_tools_schema, format_sse_motor_event

app = FastAPI(
    title="Motor Cortex Daemon",
    version="1.0.0",
    description="Subconscious motor bridge for Jen's physical avatar — walk, gesture, emotion."
)


@app.get("/health")
async def health():
    """Liveness probe for the Sleipnir watchdog."""
    return {"status": "healthy", "service": "motor-cortex", "port": 8110}


@app.get("/motor/tools")
async def list_tools():
    """Return the OpenAI-compatible tool schemas for Jen's motor actions."""
    return JSONResponse(content={"tools": get_motor_tools_schema()})


@app.post("/motor/execute")
async def execute_motor(request: Request):
    """
    Execute a single motor command synchronously.
    Body: { "tool": "walk_forward", "args": { "distance": 1.0 } }
    """
    body = await request.json()
    tool_name = body.get("tool", "")
    args = body.get("args", {})

    # Validate tool exists
    valid_tools = {t["function"]["name"] for t in get_motor_tools_schema()}
    if tool_name not in valid_tools:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown tool '{tool_name}'. Valid: {sorted(valid_tools)}"}
        )

    # In a full implementation this would bridge to LM Studio / Unreal / Godot.
    # For now, echo back the command so the frontend can consume it via SSE.
    sse_event = format_sse_motor_event(tool_name, args)
    return JSONResponse(content={
        "status": "dispatched",
        "tool": tool_name,
        "args": args,
        "sse": sse_event.strip()
    })


@app.post("/motor/stream")
async def stream_motor(request: Request):
    """
    SSE streaming endpoint. Accepts a list of motor commands and yields
    Server-Sent Events for each one.
    Body: { "actions": [{ "tool": "...", "args": {...} }, ...] }
    """
    body = await request.json()
    actions = body.get("actions", [])

    async def event_generator():
        for action in actions:
            tool_name = action.get("tool", "")
            args = action.get("args", {})
            yield format_sse_motor_event(tool_name, args)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# --- Live event bus: soul_core publishes here, frontend subscribes ---
import asyncio
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_subscribers: list[asyncio.Queue] = []


@app.post("/motor/publish")
async def publish_motor(request: Request):
    """
    soul_core calls this to dispatch a motor intent to all connected frontends.
    Body: { "tool": "trigger_micro_gesture", "args": { "gesture": "nod" } }
    """
    body = await request.json()
    event = format_sse_motor_event(body.get("tool", ""), body.get("args", {}))
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass
    return {"dispatched": len(_subscribers)}


@app.get("/motor/subscribe")
async def subscribe_motor():
    """
    Persistent SSE stream — the frontend MotorBridge connects here
    and receives motor events as Jen decides to move, gesture, or emote.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=32)
    _subscribers.append(q)

    async def event_stream():
        try:
            yield "data: {\"type\":\"connected\"}\n\n"
            while True:
                event = await q.get()
                yield event
        finally:
            _subscribers.remove(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from server_config import ServerConfig as cfg
        _host = cfg.BIND_HOST
        _port = cfg.MOTOR_DAEMON_PORT
    except ImportError:
        _host = os.getenv("FOVEAI_BIND_HOST", "127.0.0.1")
        _port = int(os.getenv("FOVEAI_MOTOR_PORT", "8110"))
    uvicorn.run(app, host=_host, port=_port, log_level="info")
