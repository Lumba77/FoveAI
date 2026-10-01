"""
The Forge Stream Router — JSON event fan-out to WebSocket clients.

Receives parsed events from ClineBridge and routes them to connected
WebSocket clients. Maintains a registry of active connections and
supports event filtering, replay, and broadcast.

Architecture:
    stream_router.py
    ├── register(ws)      → add WebSocket to active set
    ├── unregister(ws)     → remove WebSocket
    ├── broadcast(event)   → send to all connected clients
    ├── replay(count)      → send recent events to a new client
    └── active_connections → set of WebSocket objects
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("forge.stream_router")


class StreamRouter:
    """
    Manages WebSocket connections and broadcasts Cline events.

    Acts as the bridge between ClineBridge (subprocess events) and
    the Forge UI (WebSocket clients).
    """

    def __init__(self, max_replay_events: int = 200):
        self._connections: set[WebSocket] = set()
        self._event_history: list[dict[str, Any]] = []
        self._max_replay = max_replay_events
        self._lock = asyncio.Lock()

    # ── Connection Management ────────────────────────────────────────────

    async def register(self, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and add to active set."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(f"WebSocket connected (total: {len(self._connections)})")

        # Send welcome message with current state
        await self._send_json(
            websocket,
            {
                "type": "forge_welcome",
                "version": "1.0.0",
                "connections": len(self._connections),
                "event_count": len(self._event_history),
            },
        )

    async def unregister(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from active set."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(f"WebSocket disconnected (total: {len(self._connections)})")

    async def handle_client(self, websocket: WebSocket) -> None:
        """
        Full client lifecycle: accept, listen for messages, handle disconnect.

        Usage in FastAPI:
            @app.websocket("/ws/agent-stream")
            async def agent_stream(ws: WebSocket):
                await router.handle_client(ws)
        """
        await self.register(websocket)
        try:
            while True:
                # Listen for client messages (commands, prompts, etc.)
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    msg = {"type": "raw", "content": raw}

                await self._handle_client_message(websocket, msg)

        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            await self.unregister(websocket)

    async def _handle_client_message(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        """Process incoming messages from the UI client."""
        msg_type = msg.get("type", "")

        if msg_type == "replay":
            count = msg.get("count", 50)
            await self.replay(ws, count)
        elif msg_type == "ping":
            await self._send_json(
                ws, {"type": "pong", "connections": len(self._connections)}
            )
        elif msg_type == "user_prompt":
            # Forward to bridge (handled by forge_core)
            logger.debug(f"User prompt received: {msg.get('content', '')[:100]}")
        else:
            logger.debug(f"Unknown client message type: {msg_type}")

    # ── Event Broadcasting ────────────────────────────────────────────────

    async def broadcast(self, event: dict[str, Any]) -> None:
        """
        Send an event to all connected WebSocket clients.

        This is the primary subscriber callback for ClineBridge.
        """
        # Store in history
        async with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_replay * 2:
                self._event_history = self._event_history[-self._max_replay :]

        # Broadcast to all connections
        dead_connections: set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await self._send_json(ws, event)
            except Exception:
                dead_connections.add(ws)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                self._connections -= dead_connections

    async def replay(self, websocket: WebSocket, count: int = 50) -> None:
        """Send recent event history to a client (for reconnection catch-up)."""
        events = self._event_history[-count:] if self._event_history else []
        await self._send_json(
            websocket,
            {
                "type": "replay_start",
                "count": len(events),
            },
        )
        for event in events:
            await self._send_json(websocket, event)
        await self._send_json(
            websocket,
            {
                "type": "replay_end",
                "count": len(events),
            },
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _send_json(self, ws: WebSocket, data: dict[str, Any]) -> None:
        """Send JSON data to a WebSocket, handling disconnects."""
        try:
            await ws.send_json(data)
        except Exception as e:
            logger.debug(f"Failed to send to WebSocket: {e}")
            raise

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def event_count(self) -> int:
        return len(self._event_history)

    def get_recent_events(self, count: int = 50) -> list[dict[str, Any]]:
        return self._event_history[-count:]
