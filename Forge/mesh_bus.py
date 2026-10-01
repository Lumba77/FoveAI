"""
Mesh Bus — Lightweight internal pub/sub for The Forge.

A simple in-memory event bus that connects Forge components without
interfering with Cline's conversation flow. This runs alongside the
normal operation, observing and broadcasting events but never modifying
the actual LLM traffic.

Architecture:
    Publisher (proxy, checkpoint_engine, etc.)
           ↓
      mesh_bus.publish(event)
           ↓
    Subscribers (StreamRouter, MemoryVault, etc.)
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("forge.mesh_bus")


@dataclass
class MeshEvent:
    """Standardized event format for Forge mesh communications."""

    type: str
    timestamp: float
    session_id: str | None
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "data": self.data,
        }

    @classmethod
    def create(
        cls, event_type: str, data: dict[str, Any], session_id: str | None = None
    ) -> "MeshEvent":
        return cls(
            type=event_type, timestamp=time.time(), session_id=session_id, data=data
        )


class MeshBus:
    """Lightweight in-memory pub/sub bus for Forge component communication."""

    def __init__(self, log_dir: Path | None = None):
        self._subscribers: dict[str, list[Callable]] = {}
        self._global_subscribers: list[Callable] = []
        self._lock = asyncio.Lock()
        self._event_count = 0
        self._dropped_count = 0

        self._log_file: Path | None = None
        if log_dir:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            self._log_file = log_dir / "mesh_events.jsonl"

    def subscribe(self, event_type: str, handler: Callable[[MeshEvent], Any]) -> None:
        """Subscribe a handler to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[MeshEvent], Any]) -> None:
        """Subscribe a handler to ALL events (global subscriber)."""
        self._global_subscribers.append(handler)

    def publish(self, event: MeshEvent) -> None:
        """Publish an event to all subscribers (fire-and-forget)."""
        asyncio.create_task(self._dispatch(event))
        if self._log_file:
            self._log_event(event)

    def publish_simple(
        self, event_type: str, data: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Convenience method to create and publish an event."""
        self.publish(MeshEvent.create(event_type, data, session_id))

    async def _dispatch(self, event: MeshEvent) -> None:
        """Internal: Dispatch event to all relevant subscribers."""
        self._event_count += 1
        handlers = []

        if event.type in self._subscribers:
            handlers.extend(self._subscribers[event.type])
        handlers.extend(self._global_subscribers)

        if not handlers:
            self._dropped_count += 1
            return

        await asyncio.gather(
            *[self._call_handler(h, event) for h in handlers], return_exceptions=True
        )

    async def _call_handler(self, handler: Callable, event: MeshEvent) -> None:
        """Internal: Call a single handler with error isolation."""
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning(f"Handler failed for {event.type}: {e}")

    def _log_event(self, event: MeshEvent) -> None:
        """Internal: Append event to log file."""
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), default=str) + "\n")
        except Exception:
            pass

    def get_stats(self) -> dict[str, int]:
        return {
            "events_published": self._event_count,
            "events_dropped": self._dropped_count,
            "subscriber_types": len(self._subscribers),
            "global_subscribers": len(self._global_subscribers),
        }


# Global singleton instance
FORGE_DIR = Path(__file__).parent.resolve()
mesh_bus = MeshBus(log_dir=FORGE_DIR / "logs")


# Convenience helpers
def publish_context_warning(
    token_count: int, threshold: int, session_id: str | None = None
) -> None:
    mesh_bus.publish_simple(
        "context_warning",
        {
            "token_count": token_count,
            "threshold": threshold,
        },
        session_id,
    )


def publish_checkpoint_needed(
    token_count: int, session_id: str | None = None
) -> None:
    mesh_bus.publish_simple(
        "checkpoint_needed", {"token_count": token_count}, session_id
    )


def publish_checkpoint_created(
    summary_length: int,
    tokens_before: int,
    tokens_after: int,
    session_id: str | None = None,
) -> None:
    mesh_bus.publish_simple(
        "checkpoint_created",
        {
            "summary_length": summary_length,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
        },
        session_id,
    )
