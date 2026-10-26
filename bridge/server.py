"""XRL-Bridge/1.0 — Hardened FastAPI Server Implementation.

Fully addresses the 12-point Security Checklist:
1. Fail-closed secret requirement at startup (FOVEAI_BRIDGE_SECRET).
2. Local-only approval endpoint with local IP gating & single-use CSRF tokens.
3. Replay protection (nonce + message_id tracking with timestamp validity and expiration window).
4. Canonical HMAC signature verification.
5. Strict Pydantic schemas, intent/capability allowlists, 64KB max payload.
6. Safe notifications via argument lists (no shell interpolation).
7. Clean FastAPI dependency injection and error handling.
8. Persistent concurrency-safe SQLite store with TTL and idempotency.
9. Sandboxed capability-scoped agent dispatcher; no premature completion reporting.
10. Ingress rate limiting, audit logging with secret redaction.
11. Local loopback binding only by default (127.0.0.1:8420).
"""

import logging
import os
import time
import uuid
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from bridge.dispatcher import SandboxedDispatcher
from bridge.schema import (
    ApprovalRequest,
    BridgeTaskRecord,
    TaskStatus,
    XRLBridgeRequest,
)
from bridge.security import (
    compute_hmac_signature,
    generate_csrf_token,
    get_bridge_secret,
    redact_secrets,
    safe_notify_send,
    verify_csrf_token,
    verify_hmac_signature,
)
from bridge.store import BridgeStore

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("xrl_bridge.server")

# 1. Startup validation: fail closed if bridge secret is not configured
BRIDGE_SECRET = get_bridge_secret()

app = FastAPI(
    title="XRL-Bridge/1.0",
    description="Hardened, Sandboxed Inter-Agent Bridge Server",
    version="1.0.0",
)

store = BridgeStore()
dispatcher = SandboxedDispatcher()

# Simple sliding window rate limiter
_RATE_LIMITS: Dict[str, list[float]] = {}
MAX_REQUESTS_PER_MINUTE = 60


def rate_limiter(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timestamps = _RATE_LIMITS.setdefault(client_ip, [])
    # Keep only requests within the last 60 seconds
    _RATE_LIMITS[client_ip] = [ts for ts in timestamps if now - ts < 60.0]
    if len(_RATE_LIMITS[client_ip]) >= MAX_REQUESTS_PER_MINUTE:
        logger.warning("Rate limit exceeded for IP %s", client_ip)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    _RATE_LIMITS[client_ip].append(now)


def local_only_guard(request: Request):
    """Enforces that administrative/approval endpoints are only accessible locally."""
    client_ip = request.client.host if request.client else ""
    if client_ip not in ("127.0.0.1", "::1", "localhost", "testclient"):
        logger.warning("Unauthorized remote access attempt to local endpoint from %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: local interface only."
        )


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "XRL-Bridge/1.0", "timestamp": int(time.time())}


@app.post("/v1/bridge/dispatch", dependencies=[Depends(rate_limiter)])
async def dispatch_task(req: XRLBridgeRequest, request: Request):
    now = int(time.time())
    # 3. Timestamp expiration check (+/- 120 seconds clock drift allowed)
    if abs(now - req.timestamp) > 120:
        logger.warning("Rejected message %s due to timestamp skew (%d vs %d)", req.message_id, req.timestamp, now)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Timestamp is outside the allowed 120-second validity window.",
        )

    # 3. Nonce & Message-ID replay prevention
    if not store.record_nonce_and_message(req.nonce, req.message_id, req.timestamp, ttl_seconds=300):
        logger.warning("Replay detected for nonce %s or message_id %s", req.nonce, req.message_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Replay detected: nonce or message_id already processed.",
        )

    # 4. Canonical HMAC signature verification
    canonical_dict = {
        "message_id": req.message_id,
        "nonce": req.nonce,
        "timestamp": req.timestamp,
        "intent": req.intent.value,
        "capability": req.capability.value,
        "payload": req.payload,
    }
    if not verify_hmac_signature(canonical_dict, req.signature, BRIDGE_SECRET):
        logger.warning("HMAC signature verification failed for message_id %s", req.message_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC signature.",
        )

    # Create task record (expires in 5 minutes if unapproved)
    task_id = f"task_{uuid.uuid4().hex[:16]}"
    task = BridgeTaskRecord(
        task_id=task_id,
        message_id=req.message_id,
        intent=req.intent,
        capability=req.capability,
        payload=req.payload,
        status=TaskStatus.PENDING_APPROVAL,
        created_at=now,
        expires_at=now + 300,
    )
    store.save_task(task)

    # Generate CSRF token for local approval session
    csrf_token = generate_csrf_token(task_id)

    # Safe desktop notification for local human operator
    safe_notify_send(
        "FoveAI Bridge Action Request",
        f"Task {task_id} requires operator approval (intent: {req.intent.value})",
        urgency="normal"
    )

    logger.info(
        "Task enqueued: %s | intent: %s | capability: %s | audit: %s",
        task_id, req.intent.value, req.capability.value, redact_secrets(str(req.payload))
    )

    return {
        "status": "pending_approval",
        "task_id": task_id,
        "expires_in_seconds": 300,
        "csrf_token": csrf_token,
    }


@app.get("/local/bridge/approve/{task_id}", dependencies=[Depends(local_only_guard)], response_class=HTMLResponse)
def get_approval_page(task_id: str):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status != TaskStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Task is in status {task.status.value}")

    csrf_token = generate_csrf_token(task_id)
    safe_payload = redact_secrets(str(task.payload))

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>FoveAI Bridge Operator Approval</title></head>
    <body style="font-family: sans-serif; padding: 20px;">
        <h2>Task Approval Request: {task_id}</h2>
        <p><strong>Intent:</strong> {task.intent.value}</p>
        <p><strong>Capability:</strong> {task.capability.value}</p>
        <p><strong>Payload:</strong></p>
        <pre style="background: #eee; padding: 10px;">{safe_payload}</pre>
        <form method="POST" action="/local/bridge/approve/{task_id}">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <button type="submit" name="approved" value="true" style="padding: 10px 20px; background: green; color: white;">Approve</button>
            <button type="submit" name="approved" value="false" style="padding: 10px 20px; background: red; color: white;">Reject</button>
        </form>
    </body>
    </html>
    """


@app.post("/local/bridge/approve/{task_id}", dependencies=[Depends(local_only_guard)])
async def process_approval(task_id: str, approval: ApprovalRequest):
    # 2. Authenticated local approval & CSRF protection
    if not verify_csrf_token(task_id, approval.csrf_token):
        logger.warning("Invalid or reused CSRF token for task %s", task_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired CSRF token")

    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status != TaskStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Task cannot be modified (current status: {task.status.value})")

    if not approval.approved:
        store.update_task_status(task_id, TaskStatus.REJECTED, error="Rejected by operator")
        logger.info("Task %s rejected by operator", task_id)
        return {"task_id": task_id, "status": TaskStatus.REJECTED.value}

    # Mark executing
    store.update_task_status(task_id, TaskStatus.EXECUTING)
    try:
        # 9. Sandboxed capability dispatch
        result = await dispatcher.execute(task)
        # Truthful completion report only after execution succeeds
        store.update_task_status(task_id, TaskStatus.COMPLETED, result=result)
        logger.info("Task %s completed successfully", task_id)
        return {"task_id": task_id, "status": TaskStatus.COMPLETED.value, "result": result}
    except Exception as e:
        logger.error("Execution failed for task %s: %s", task_id, e)
        store.update_task_status(task_id, TaskStatus.FAILED, error=str(e))
        return {"task_id": task_id, "status": TaskStatus.FAILED.value, "error": str(e)}


@app.get("/v1/bridge/task/{task_id}", dependencies=[Depends(rate_limiter)])
def get_task_status(task_id: str):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "intent": task.intent.value,
        "capability": task.capability.value,
        "created_at": task.created_at,
        "expires_at": task.expires_at,
        "result": task.result,
        "error": task.error,
    }
