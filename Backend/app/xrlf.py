"""XRLF (eXtensible Reality Link Format) protocol implementation.

Enforces the XRLF.CONTRACT.XRLF standard for all IPC event payloads.
Every envelope contains: xrlf_version, event, agent_id, timestamp,
payload, geometry, and phase fields.
"""

from __future__ import annotations

import json
import time
from typing import Any

XRLF_VERSION = "3.0"
AGENT_ID = "lumax-backend"


def envelope(
    event: str,
    payload: dict[str, Any],
    phase: str = "runtime",
    agent_id: str = AGENT_ID,
    geometry: str = "3D",
) -> dict[str, Any]:
    """Build an XRLF-compliant envelope dict."""
    return {
        "xrlf_version": XRLF_VERSION,
        "event": event,
        "agent_id": agent_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "payload": payload,
        "geometry": geometry,
        "phase": phase,
    }


def parse(raw: str) -> dict[str, Any] | None:
    """Parse a raw JSON string into an XRLF envelope dict.
    Returns None if the input is not valid XRLF.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    # Validate required fields
    required = {"xrlf_version", "event", "payload"}
    if not required.issubset(data.keys()):
        return None

    return data


def ack(event: str = "ack", payload: dict[str, Any] | None = None) -> str:
    """Build an ack envelope as a JSON string."""
    return json.dumps(envelope(event, payload or {}, phase="ack"))


def error(message: str, event: str = "error") -> str:
    """Build an error envelope as a JSON string."""
    return json.dumps(envelope(event, {"error": message}, phase="error"))


def chat_envelope(text: str) -> str:
    """Build a chat event envelope as a JSON string."""
    return json.dumps(envelope("chat", {"text": text}, phase="runtime"))
