"""
Checkpoint Engine — Auto-checkpointing monitor for The Forge.

Watches token counts and fires checkpoint_needed events. Does NOT
modify context — only signals need. Summary comes from Cline (Tier 3).
"""

import asyncio
import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass, field

from mesh_bus import mesh_bus, MeshEvent, publish_checkpoint_needed, publish_checkpoint_created

logger = logging.getLogger("forge.checkpoint")


@dataclass
class SessionCheckpointState:
    """Tracks checkpoint state for a single session."""
    session_id: str
    threshold: int
    current_tokens: int = 0
    checkpoint_count: int = 0
    last_checkpoint_tokens: int = 0
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    active: bool = True
    
    def should_checkpoint(self) -> bool:
        if not self.active:
            return False
        if self.current_tokens > self.threshold:
            tokens_since_last = self.current_tokens - self.last_checkpoint_tokens
            return tokens_since_last > (self.threshold * 0.5)
        return False
    
    def record_checkpoint(self, tokens_after: int) -> None:
        self.checkpoint_count += 1
        self.last_checkpoint_tokens = tokens_after
        self.last_activity = time.time()


class CheckpointEngine:
    """Monitors token counts and manages checkpoint lifecycle."""
    
    DEFAULT_THRESHOLD = 30000
    CHECK_INTERVAL = 5.0
    
    def __init__(self):
        self._sessions: Dict[str, SessionCheckpointState] = {}
        self._lock_obj = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._pending_checkpoints: set = set()
        mesh_bus.subscribe("checkpoint_created", self._on_checkpoint_created)

    @property
    def _lock(self):
        if self._lock_obj is None:
            self._lock_obj = asyncio.Lock()
        return self._lock_obj
    
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("CheckpointEngine started")
    
    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CheckpointEngine stopped")
    
    async def monitor_session(self, session_id: str, threshold: Optional[int] = None) -> SessionCheckpointState:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].threshold = threshold or self.DEFAULT_THRESHOLD
                return self._sessions[session_id]
            
            state = SessionCheckpointState(
                session_id=session_id,
                threshold=threshold or self.DEFAULT_THRESHOLD
            )
            self._sessions[session_id] = state
            logger.info(f"Monitoring session {session_id} (threshold: {state.threshold})")
            return state
    
    async def end_session(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].active = False
                del self._sessions[session_id]
    
    async def report_token_count(self, session_id: str, token_count: int) -> None:
        async with self._lock:
            if session_id not in self._sessions:
                state = SessionCheckpointState(
                    session_id=session_id,
                    threshold=self.DEFAULT_THRESHOLD
                )
                self._sessions[session_id] = state
            else:
                state = self._sessions[session_id]
            
            state.current_tokens = token_count
            state.last_activity = time.time()
            
            if state.should_checkpoint() and session_id not in self._pending_checkpoints:
                self._pending_checkpoints.add(session_id)
                logger.warning(f"Session {session_id}: {token_count} tokens exceeds threshold")
                publish_checkpoint_needed(token_count=token_count, session_id=session_id)
                
                # Auto-create checkpoint via API
                await self._auto_checkpoint(session_id, token_count)
    
    async def _auto_checkpoint(self, session_id: str, token_count: int) -> None:
        """Automatically create a checkpoint via API call."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://127.0.0.1:8100/checkpoint",
                    json={
                        "summary": f"Auto-checkpoint at {token_count} tokens",
                        "session_id": session_id,
                        "tokens_before": token_count,
                        "tokens_after": 500
                    },
                    timeout=5.0
                )
                logger.info(f"Auto-checkpoint created for {session_id}")
        except Exception as e:
            logger.warning(f"Auto-checkpoint failed: {e}")
    
    async def report_checkpoint_created(self, session_id: str, summary_length: int, 
                                        tokens_before: int, tokens_after: int) -> None:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].record_checkpoint(tokens_after)
                self._pending_checkpoints.discard(session_id)
                publish_checkpoint_created(summary_length, tokens_before, tokens_after, session_id)
    
    def get_session_state(self, session_id: str) -> Optional[SessionCheckpointState]:
        return self._sessions.get(session_id)
    
    def get_all_stats(self) -> Dict:
        return {
            sid: {"current_tokens": s.current_tokens, "threshold": s.threshold,
                  "checkpoint_count": s.checkpoint_count, "active": s.active}
            for sid, s in self._sessions.items()
        }
    
    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL)
                await self._check_stale_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
    
    async def _check_stale_sessions(self) -> None:
        now = time.time()
        async with self._lock:
            stale = [sid for sid, state in self._sessions.items()
                     if now - state.last_activity > 300 and not state.active]
            for sid in stale:
                del self._sessions[sid]
    
    def _on_checkpoint_created(self, event: MeshEvent) -> None:
        if event.session_id:
            self._pending_checkpoints.discard(event.session_id)


# Global singleton
checkpoint_engine = CheckpointEngine()
