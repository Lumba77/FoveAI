"""XRLF 3.0 Protocol Envelope & Validation.

Enforces the XRLF.CONTRACT.XRLF standard for all WebSocket IPC events.
Every inbound and outbound message is wrapped in a deterministic envelope
that preserves coherence, clarity, and structural integrity (Principle 0).

Envelope schema:
    {
        "xrlf_version": "3.0",
        "event": "<event_name>",
        "payload": { ... },
        "request_id": "<optional uuid>",
        "status": "ok" | "error",
        "timestamp": "<ISO8601 UTC>"
    }
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("FoveAI.XRLF")

XRLF_VERSION = "3.0"
XRLF_RUNTIME = "XRLF-3.0 Unified Cognitive Engine"


def _now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def make_envelope(
    event: str,
    payload: dict[str, Any],
    *,
    status: str = "ok",
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a compliant XRLF 3.0 response envelope."""
    envelope: dict[str, Any] = {
        "xrlf_version": XRLF_VERSION,
        "status": status,
        "event": event,
        "payload": payload,
        "timestamp": _now_iso(),
    }
    if request_id is not None:
        envelope["request_id"] = request_id
    return envelope


def make_error_envelope(
    error_code: str,
    message: str,
    *,
    event: str = "error",
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a compliant XRLF 3.0 error envelope."""
    return make_envelope(
        event,
        {"error_code": error_code, "message": message},
        status="error",
        request_id=request_id,
    )


def make_health_payload() -> dict[str, Any]:
    """Build the /health payload required by the XRLF contract."""
    return {
        "xrlf_version": XRLF_VERSION,
        "runtime": XRLF_RUNTIME,
        "status": "online",
        "timestamp": _now_iso(),
        "uptime_seconds": round(time.monotonic(), 3),
    }


def validate_inbound(data: dict[str, Any]) -> tuple[Optional[str], dict[str, Any], Optional[str]]:
    """Validate an inbound XRLF envelope.

    Returns:
        (event, payload, request_id) or raises ValueError on malformed input.
    """
    if not isinstance(data, dict):
        raise ValueError("Inbound message must be a JSON object")

    event = data.get("event")
    if not isinstance(event, str) or not event:
        raise ValueError("Missing or invalid 'event' field")

    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("'payload' must be a JSON object")

    request_id = data.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        request_id = str(request_id)

    return event, payload, request_id


def serialize(envelope: dict[str, Any]) -> str:
    """Serialize an envelope to compact JSON."""
    return json.dumps(envelope, separators=(",", ":"))


def new_request_id() -> str:
    """Generate a new request id."""
    return str(uuid.uuid4())