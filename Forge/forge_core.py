"""
The Forge Core — Main orchestrator for the AI-native IDE.

Manages the lifecycle of ClineBridge sessions, connects them to
the StreamRouter for WebSocket broadcasting, and provides the
central API for session management.

Architecture:
    forge_core.py
    ├── sessions: Dict[str, ClineBridge]  → active session registry
    ├── router: StreamRouter              → WebSocket fan-out
    ├── spawn_session()                   → create new Cline session
    ├── stop_session()                    → terminate a session
    ├── send_prompt()                     → send user input to agent
    └── shutdown()                        → stop all sessions
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List

from cline_bridge import ClineBridge
from stream_router import StreamRouter
from mesh_bus import mesh_bus
from checkpoint_engine import checkpoint_engine

logger = logging.getLogger("forge.core")


class ForgeCore:
    """
    Central orchestrator for The Forge IDE.

    Manages multiple concurrent ClineBridge sessions, each connected
    to the shared StreamRouter for real-time UI updates.
    """

    def __init__(
        self,
        workspace: str = None,
        router: StreamRouter = None,
        cline_command: str = "cline",
    ):
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.router = router
        self.cline_command = cline_command
        self._sessions: Dict[str, ClineBridge] = {}
        self._started_at: float = time.time()
        self._lock = asyncio.Lock()

        logger.info(f"ForgeCore initialized — workspace: {self.workspace}")

    # ── Session Lifecycle ─────────────────────────────────────────────────

    async def spawn_session(
        self,
        model: str = "deepseek-v4-pro",
        prompt: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> str:
        """
        Spawn a new Cline CLI 3 session.

        Creates a ClineBridge, subscribes the StreamRouter to it,
        and starts the subprocess.

        Args:
            model: Model to use (deepseek-v4-pro, glm-5.1-cloud, etc.)
            prompt: Optional initial prompt
            workspace: Optional workspace override

        Returns:
            session_id: Unique session identifier
        """
        ws = Path(workspace).resolve() if workspace else self.workspace

        bridge = ClineBridge(
            workspace=str(ws),
            cline_command=self.cline_command,
        )

        # Subscribe the stream router to this bridge
        if self.router:
            bridge.subscribe(self.router.broadcast)

        # Spawn the subprocess
        session_id = await bridge.spawn(model=model, prompt=prompt)

        async with self._lock:
            self._sessions[session_id] = bridge

        logger.info(f"Session spawned: {session_id} (total: {len(self._sessions)})")
        
        # NEW: Integrate with checkpoint engine and memory vault
        await checkpoint_engine.monitor_session(session_id)
        mesh_bus.publish_simple("session_started", {"model": model}, session_id)
        
        return session_id

    async def stop_session(self, session_id: str, reason: str = "user_requested") -> None:
        """
        Stop a running session.

        Args:
            session_id: The session to stop
            reason: Why the session is ending

        Raises:
            KeyError: If session_id not found
        """
        async with self._lock:
            bridge = self._sessions.get(session_id)
            if bridge is None:
                raise KeyError(f"Session not found: {session_id}")

        # Unsubscribe router
        if self.router:
            bridge.unsubscribe(self.router.broadcast)

        # Stop the subprocess
        await bridge.stop(reason=reason)

        async with self._lock:
            del self._sessions[session_id]

        logger.info(f"Session stopped: {session_id} (remaining: {len(self._sessions)})")
        
        # NEW: Notify checkpoint engine and memory vault
        await checkpoint_engine.end_session(session_id)
        mesh_bus.publish_simple("session_ended", {"reason": reason}, session_id)

    async def send_prompt(self, session_id: str, text: str) -> None:
        """
        Send a user prompt to a running session.

        Args:
            session_id: Target session
            text: Prompt text

        Raises:
            KeyError: If session not found
            RuntimeError: If session is not running
        """
        bridge = self._sessions.get(session_id)
        if bridge is None:
            raise KeyError(f"Session not found: {session_id}")

        await bridge.send_prompt(text)

    async def shutdown(self) -> None:
        """Stop all active sessions and clean up."""
        logger.info(f"Shutting down ForgeCore ({len(self._sessions)} sessions)")

        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            try:
                await self.stop_session(sid, reason="forge_shutdown")
            except Exception as e:
                logger.error(f"Error stopping session {sid}: {e}")

        logger.info("ForgeCore shutdown complete")

    # ── Query Methods ─────────────────────────────────────────────────────

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return summary list of all active sessions."""
        return [
            {
                "session_id": sid,
                "model": bridge.model,
                "is_running": bridge.is_running,
                "uptime_s": bridge.uptime_s,
                "subscriber_count": bridge.subscriber_count,
                "event_summary": bridge.get_event_summary(),
            }
            for sid, bridge in self._sessions.items()
        ]

    def get_session_events(self, session_id: str, count: int = 50) -> List[Dict[str, Any]]:
        """Get recent events from a specific session."""
        bridge = self._sessions.get(session_id)
        if bridge is None:
            raise KeyError(f"Session not found: {session_id}")
        return bridge.get_recent_events(count)

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Get detailed status of a session."""
        bridge = self._sessions.get(session_id)
        if bridge is None:
            raise KeyError(f"Session not found: {session_id}")

        return {
            "session_id": session_id,
            "model": bridge.model or "unknown",
            "is_running": bridge.is_running,
            "uptime_s": bridge.uptime_s,
            "subscriber_count": bridge.subscriber_count,
            "event_summary": bridge.get_event_summary(),
            "timestamp": datetime.now().isoformat(),
        }

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    @property
    def uptime_s(self) -> float:
        return time.time() - self._started_at


# ── Singleton accessor ────────────────────────────────────────────────────

_forge_instance: Optional[ForgeCore] = None


def get_forge() -> Optional[ForgeCore]:
    """Get the global ForgeCore instance (set by forge_api startup)."""
    return _forge_instance


def set_forge(instance: ForgeCore) -> None:
    """Set the global ForgeCore instance."""
    global _forge_instance
    _forge_instance = instance
