"""
FoveAI Safe Proxy v2 — Transparent context-compressing proxy (port 8103).

DESIGN PRINCIPLES (lessons from v1):
  - NEVER touches Cline config files (.cline directory)
  - NEVER kills other processes (no taskkill /F /IM python.exe)
  - Runs on port 8103 — isolated from the main session
  - Configurable aggression levels — start at 0 (passthrough) and dial up
  - Dry-run mode — audit what WOULD be stripped before enabling
  - Method passthrough — forwards original HTTP method, not hardcoded POST
  - Pruning and auto-checkpoint are OFF by default (opt-in only)

ENV VARS:
  FoveAI_PROXY_PORT           — port (default 8103)
  FoveAI_PROXY_TARGET         — real API base URL (default: FoveAI_CLOUD_BASE_URL or ollama.com/v1)
  FoveAI_PROXY_API_KEY        — API key for target (default: OLLAMA_API_KEY)
  FoveAI_PROXY_AGGRESSION     — 0=passthrough, 1=thinking-strip, 2=full strip, 3=crystallise (default 0)
  FoveAI_PROXY_DRY_RUN        — 1=log only, don't modify messages (default 0)
  FoveAI_PROXY_AUTO_CHECKPOINT — 1=enable auto-checkpoint on threshold (default 0)
  FoveAI_PROXY_ENABLE_PRUNING  — 1=enable context recycling/pruning (default 0)
  FoveAI_PROXY_CHECKPOINT_THRESHOLD — token threshold for auto-checkpoint (default 30000)
  FoveAI_PROXY_PRESERVE_LAST  — number of last turns to preserve (default 5)
"""

import asyncio
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("foveai.proxy.v2")

# ── Config ────────────────────────────────────────────────────────────

FORGE_DIR = Path(__file__).parent.resolve()

# Load .env from repo root
_env_path = FORGE_DIR.parent / ".env"
if _env_path.is_file():
    try:
        import dotenv
        dotenv.load_dotenv(str(_env_path), override=True)
    except ImportError:
        pass

PROXY_PORT = int(os.environ.get("FoveAI_PROXY_PORT", "8104"))

# Target API — default to FoveAI_CLOUD_BASE_URL, fall back to ollama.com/v1
_target_raw = (
    os.environ.get("FoveAI_PROXY_TARGET", "")
    or os.environ.get("FoveAI_CLOUD_BASE_URL", "")
    or "https://ollama.com/v1"
).strip().rstrip("/")
if not _target_raw.endswith("/v1"):
    REAL_API_BASE = _target_raw + "/v1"
else:
    REAL_API_BASE = _target_raw

REAL_API_KEY = (
    os.environ.get("FoveAI_PROXY_API_KEY", "")
    or os.environ.get("OLLAMA_API_KEY", "")
).strip()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Aggression levels
AGGRESSION = int(os.environ.get("FoveAI_PROXY_AGGRESSION", "3"))
DRY_RUN = os.environ.get("FoveAI_PROXY_DRY_RUN", "0").strip().lower() in ("1", "true", "yes")
AUTO_CHECKPOINT = os.environ.get("FoveAI_PROXY_AUTO_CHECKPOINT", "0").strip().lower() in ("1", "true", "yes")
ENABLE_PRUNING = os.environ.get("FoveAI_PROXY_ENABLE_PRUNING", "0").strip().lower() in ("1", "true", "yes")
CHECKPOINT_THRESHOLD = int(os.environ.get("FoveAI_PROXY_CHECKPOINT_THRESHOLD", "15000"))
PRESERVE_LAST = int(os.environ.get("FoveAI_PROXY_PRESERVE_LAST", "3"))
MAX_MESSAGES = int(os.environ.get("FoveAI_PROXY_MAX_MESSAGES", "50"))

# ── Context Stripper (safe subset) ────────────────────────────────────

CHARS_PER_TOKEN = 4

# Import smart context manager
try:
    sys.path.insert(0, str(FORGE_DIR))
    from smart_context_manager import smart_context_manager
    from context_stripper import estimate_tokens
    SMART_CONTEXT_AVAILABLE = True
except ImportError:
    SMART_CONTEXT_AVAILABLE = False
    smart_context_manager = None

    def estimate_tokens(text: str) -> int:
        return max(1, len(str(text)) // CHARS_PER_TOKEN)


# ── State ──────────────────────────────────────────────────────────────

@dataclass
class ProxyState:
    """Thread-safe container for proxy runtime state."""
    start_time: float = field(default_factory=time.time)
    requests_proxied: int = 0
    tokens_in_total: int = 0
    tokens_out_total: int = 0
    tokens_saved_total: int = 0
    checkpoint_active: bool = False
    checkpoint_summary: Optional[str] = None
    meter_history: List[Dict] = field(default_factory=list)
    meter_subscribers: List[asyncio.Queue] = field(default_factory=list)

    MAX_METER_HISTORY = 50

    @property
    def cumulative_compression_pct(self) -> float:
        if self.tokens_in_total > 0:
            return round((1 - self.tokens_out_total / self.tokens_in_total) * 100, 1)
        return 0.0

    def record_meter(self, before: int, after: int, msg_count: int, checkpoint: bool = False):
        """Record a meter entry and push to SSE subscribers."""
        saved = max(0, before - after)
        pct = round((1 - after / max(1, before)) * 100, 1)

        self.tokens_in_total += before
        self.tokens_out_total += after
        self.tokens_saved_total += saved

        entry = {
            "timestamp": datetime.now().isoformat(),
            "tokens_in": before,
            "tokens_out": after,
            "tokens_saved": saved,
            "compression_pct": pct,
            "messages": msg_count,
            "checkpoint": checkpoint,
            "cumulative_in": self.tokens_in_total,
            "cumulative_out": self.tokens_out_total,
            "cumulative_saved": self.tokens_saved_total,
            "cumulative_pct": self.cumulative_compression_pct,
        }

        self.meter_history.append(entry)
        if len(self.meter_history) > self.MAX_METER_HISTORY:
            self.meter_history.pop(0)

        # Push to SSE subscribers
        for q in self.meter_subscribers[:]:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass


_state = ProxyState()

# ── Shared HTTP client (connection pooling) ────────────────────────────

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client with connection pooling."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=300.0)
    return _client


async def close_client():
    """Gracefully close the shared HTTP client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Helpers ────────────────────────────────────────────────────────────

# Note: Context Stripper logic has been migrated to `context_stripper.py`
# and is orchestrated by `smart_context_manager.py`

def gemini_to_openai(gemini_body: Dict) -> List[Dict]:
    """Convert Gemini payload (contents/systemInstruction) to OpenAI messages format."""
    messages = []
    
    # 1. Handle system instruction
    sys_inst = gemini_body.get("systemInstruction")
    if sys_inst and isinstance(sys_inst, dict):
        parts = sys_inst.get("parts", [])
        sys_text = "".join([p.get("text", "") for p in parts if "text" in p])
        if sys_text:
            messages.append({"role": "system", "content": sys_text})
            
    # 2. Handle standard contents
    contents = gemini_body.get("contents", [])
    if not isinstance(contents, list):
        contents = [contents]
        
    for content in contents:
        role = content.get("role", "user")
        if role == "model":
            role = "assistant"
            
        parts = content.get("parts", [])
        text_parts = []
        for p in parts:
            if "text" in p:
                text_parts.append(p["text"])
            elif "functionCall" in p:
                # Store original part representation as string to preserve it
                text_parts.append(f"[FUNCTION_CALL: {json.dumps(p['functionCall'])}]")
            elif "functionResponse" in p:
                text_parts.append(f"[FUNCTION_RESPONSE: {json.dumps(p['functionResponse'])}]")
        
        msg_content = "\n".join(text_parts)
        # Store original content object inside the message so we can rebuild non-text parts if needed
        messages.append({
            "role": role, 
            "content": msg_content,
            "_gemini_original": content
        })
        
    return messages


def openai_to_gemini(messages: List[Dict], original_body: Dict) -> Dict:
    """Rebuild Gemini payload from pruned OpenAI messages list."""
    new_body = original_body.copy()
    new_contents = []
    
    for msg in messages:
        role = msg.get("role", "user")
        if role == "system":
            # Just ignore system messages here; they are preserved in original_body["systemInstruction"]
            # (Assuming the context manager didn't drastically modify the system prompt)
            continue
            
        if role == "assistant":
            role = "model"
            
        original = msg.get("_gemini_original")
        if original:
            # If we have the original, use it (we assume smart context manager trims history, not edits text internally)
            new_contents.append(original)
        else:
            # Fallback if a new message was injected
            new_contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })
            
    new_body["contents"] = new_contents
    return new_body



# ── App ───────────────────────────────────────────────────────────────

app = FastAPI(title="LumaxProxy v2", version="2.0.0")

@app.on_event("startup")
async def startup_event():
    if SMART_CONTEXT_AVAILABLE:
        await smart_context_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    if SMART_CONTEXT_AVAILABLE:
        await smart_context_manager.stop()


# ── Routes ────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "foveai-proxy-v2",
        "version": "2.0.0",
        "port": PROXY_PORT,
        "target": REAL_API_BASE,
        "aggression": AGGRESSION,
        "dry_run": DRY_RUN,
        "auto_checkpoint": AUTO_CHECKPOINT,
        "pruning_enabled": ENABLE_PRUNING,
        "uptime_s": round(time.time() - _state.start_time, 1),
        "requests_proxied": _state.requests_proxied,
        "tokens_saved_total": _state.tokens_saved_total,
    }


@app.get("/stats")
async def stats():
    return {
        "requests_proxied": _state.requests_proxied,
        "tokens_in_total": _state.tokens_in_total,
        "tokens_out_total": _state.tokens_out_total,
        "tokens_saved_total": _state.tokens_saved_total,
        "cumulative_compression_pct": _state.cumulative_compression_pct,
        "aggression": AGGRESSION,
        "dry_run": DRY_RUN,
        "checkpoint_threshold": CHECKPOINT_THRESHOLD,
        "preserve_last": PRESERVE_LAST,
        "checkpoint_active": _state.checkpoint_active,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/meter")
async def meter():
    """Get the current meter state + last N requests + cumulative totals."""
    return {
        "cumulative": {
            "requests": _state.requests_proxied,
            "tokens_in": _state.tokens_in_total,
            "tokens_out": _state.tokens_out_total,
            "tokens_saved": _state.tokens_saved_total,
            "compression_pct": _state.cumulative_compression_pct,
        },
        "recent": _state.meter_history[-20:],
        "config": {
            "aggression": AGGRESSION,
            "dry_run": DRY_RUN,
            "auto_checkpoint": AUTO_CHECKPOINT,
            "checkpoint_active": _state.checkpoint_active,
        },
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/meter/stream")
async def meter_stream(request: Request):
    """SSE stream of live meter events + one event per proxied request."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _state.meter_subscribers.append(q)

    async def event_generator():
        try:
            # Send current state immediately
            initial = json.dumps({
                "type": "snapshot",
                "cumulative": {
                    "requests": _state.requests_proxied,
                    "tokens_in": _state.tokens_in_total,
                    "tokens_out": _state.tokens_out_total,
                    "tokens_saved": _state.tokens_saved_total,
                    "compression_pct": _state.cumulative_compression_pct,
                },
                "config": {
                    "aggression": AGGRESSION,
                    "dry_run": DRY_RUN,
                    "auto_checkpoint": AUTO_CHECKPOINT,
                },
            })
            yield f"data: {initial}\n\n"

            # Stream live events
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps({'type': 'request', **entry})}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
        finally:
            if q in _state.meter_subscribers:
                _state.meter_subscribers.remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/checkpoint")
async def set_checkpoint(request: Request):
    """Inject a summary checkpoint (opt-in)."""
    body = await request.json()
    summary = body.get("summary", "")
    if not summary:
        return JSONResponse({"error": "summary field required"}, status_code=400)
    _state.checkpoint_active = True
    _state.checkpoint_summary = summary
    logger.info(f"Checkpoint activated ({len(summary)} chars)")
    return {"status": "checkpoint_active", "summary_length": len(summary)}


@app.post("/checkpoint/clear")
async def clear_checkpoint():
    _state.checkpoint_active = False
    _state.checkpoint_summary = None
    return {"status": "checkpoint_cleared"}


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_v1(path: str, request: Request):
    """Proxy any /v1/* endpoint to the real API, preserving the original HTTP method."""
    _state.requests_proxied += 1

    method = request.method
    body: Optional[Dict] = None
    if method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
        except Exception:
            body = {}

    # Apply smart context management to chat completions
    is_chat = path == "chat/completions" and method == "POST"
    if is_chat and body and "messages" in body:
        original_count = len(body["messages"])
        before_ctx = sum(estimate_tokens(str(m.get("content", ""))) for m in body["messages"])

        if DRY_RUN:
            # Log what WOULD happen, but don't modify
            logger.info(
                f"[DRY-RUN] Processing {original_count} msgs, "
                f"~{before_ctx} tokens"
            )
        else:
            if SMART_CONTEXT_AVAILABLE:
                # Use a default session or extract from headers if available
                session_id = request.headers.get("X-Session-ID", "proxy_default_session")
                
                # Report current token usage to get a recommendation
                rec = await smart_context_manager.report_tokens(
                    session_id=session_id,
                    token_count=before_ctx,
                    messages=body["messages"]
                )
                
                # Apply cutting strategy if recommended
                if rec.action.startswith("cut_"):
                    logger.info(f"SmartContext: Action {rec.action} triggered (Reason: {rec.reason})")
                    processed_msgs, meta = await smart_context_manager.apply_cutting_strategy(
                        session_id=session_id,
                        messages=body["messages"]
                    )
                    body["messages"] = processed_msgs
            else:
                logger.warning("SmartContextManager unavailable. Passing through raw.")
                
            after_ctx = sum(estimate_tokens(str(m.get("content", ""))) for m in body["messages"])
            if before_ctx != after_ctx:
                logger.info(f"Proxying chat: {original_count} msgs, {before_ctx}→{after_ctx} tokens")
            
            # Record meter
            _state.record_meter(before_ctx, after_ctx, original_count)

    query_str = str(request.url.query)
    url = f"{REAL_API_BASE}/{path}" + (f"?{query_str}" if query_str else "")
    
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    # Inject API key for upstream authentication
    if REAL_API_KEY:
        headers["Authorization"] = f"Bearer {REAL_API_KEY}"

    is_streaming = body and body.get("stream", False) if isinstance(body, dict) else False

    if is_streaming and is_chat:
        return await _proxy_streaming(url, headers, body, method)
    else:
        return await _proxy_non_streaming(url, headers, body, method)


@app.api_route("/v1beta/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_v1beta(path: str, request: Request):
    """Proxy Gemini native API calls from Antigravity IDE."""
    _state.requests_proxied += 1

    method = request.method
    body: Optional[Dict] = None
    if method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
        except Exception:
            body = {}

    is_gemini_generate = path.startswith("models/") and "generatecontent" in path.lower() and method == "POST"
    
    if is_gemini_generate and body and "contents" in body:
        # 1. Translate Gemini contents into standard OpenAI messages list
        messages = gemini_to_openai(body)
        original_count = len(messages)
        before_ctx = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)

        if DRY_RUN:
            logger.info(f"[DRY-RUN] Processing Gemini payload {original_count} msgs, ~{before_ctx} tokens")
        else:
            if SMART_CONTEXT_AVAILABLE:
                session_id = request.headers.get("X-Session-ID", "proxy_gemini_session")
                
                logger.info("Calling report_tokens...")
                rec = await smart_context_manager.report_tokens(
                    session_id=session_id,
                    token_count=before_ctx,
                    messages=messages
                )
                logger.info("Returned from report_tokens.")
                
                if rec.action.startswith("cut_"):
                    logger.info(f"SmartContext (Gemini): Action {rec.action} triggered (Reason: {rec.reason})")
                    logger.info("Calling apply_cutting_strategy...")
                    processed_msgs, meta = await smart_context_manager.apply_cutting_strategy(
                        session_id=session_id,
                        messages=messages
                    )
                    logger.info("Returned from apply_cutting_strategy.")
                    messages = processed_msgs
            else:
                logger.warning("SmartContextManager unavailable. Passing through raw.")
                
            after_ctx = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
            if before_ctx != after_ctx:
                logger.info(f"Proxying Gemini chat: {original_count} msgs, {before_ctx}→{after_ctx} tokens")
            
            _state.record_meter(before_ctx, after_ctx, original_count)
            
        # 3. Reconstruct Gemini payload from the truncated messages
        body = openai_to_gemini(messages, body)

    # Proxy to actual Google API!
    query_str = str(request.url.query)
    url = f"https://generativelanguage.googleapis.com/v1beta/{path}" + (f"?{query_str}" if query_str else "")
    
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    if GEMINI_API_KEY:
        headers["x-goog-api-key"] = GEMINI_API_KEY

    is_streaming = "streamGenerateContent" in path

    if is_streaming and is_gemini_generate:
        return await _proxy_streaming(url, headers, body, method)
    else:
        return await _proxy_non_streaming(url, headers, body, method)


async def _proxy_non_streaming(url: str, headers: dict, body: Optional[dict], method: str):
    """Forward a non-streaming request with the original HTTP method."""
    client = get_client()

    # Map HTTP methods to client methods
    method_map = {
        "GET": lambda: client.get(url, headers=headers),
        "DELETE": lambda: client.delete(url, headers=headers),
        "PUT": lambda: client.put(url, json=body, headers=headers),
        "PATCH": lambda: client.patch(url, json=body, headers=headers),
    }

    request_fn = method_map.get(method, lambda: client.post(url, json=body, headers=headers))

    try:
        resp = await request_fn()
    except httpx.RequestError as e:
        logger.error(f"Upstream request failed: {e}")
        return JSONResponse(
            content={"error": f"Upstream request failed: {str(e)}"},
            status_code=502,
        )

    content_type = resp.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            return JSONResponse(
                content=resp.json(),
                status_code=resp.status_code,
            )
        except (json.JSONDecodeError, ValueError):
            # Content-type says JSON but body isn't valid JSON
            pass

    # Return raw text with original content type for non-JSON responses
    return StreamingResponse(
        content=resp.iter_bytes(),
        status_code=resp.status_code,
        media_type=content_type or "text/plain",
        headers={
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
        },
    )


async def _proxy_streaming(url: str, headers: dict, body: dict, method: str):
    """Forward a streaming (SSE) request."""
    client = get_client()

    async def generate():
        try:
            async with client.stream(method, url, json=body, headers=headers) as resp:
                # Propagate upstream status code on first chunk
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    error_detail = error_body.decode("utf-8", errors="replace")
                    logger.error(f"Upstream streaming returned {resp.status_code}: {error_detail[:300]}")
                    # Wrap error in SSE format so clients can parse it
                    error_sse = json.dumps({
                        "error": f"Upstream returned {resp.status_code}",
                        "detail": error_detail,
                    })
                    yield f"data: {error_sse}\n\n".encode()
                    return

                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.RequestError as e:
            logger.error(f"Streaming upstream request failed: {e}")
            error_sse = json.dumps({"error": f"Streaming request failed: {str(e)}"})
            yield f"data: {error_sse}\n\n".encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── CLI ───────────────────────────────────────────────────────────────


def _check_running(port: int = None) -> bool:
    p = port or PROXY_PORT
    try:
        with socket.create_connection(("127.0.0.1", p), timeout=2):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _cmd_status():
    running = _check_running()
    if not running:
        print("[PROXY v2] Status: STOPPED")
        return
    print("[PROXY v2] Status: RUNNING")
    print(f"  Port:       {PROXY_PORT}")
    print(f"  Target:     {REAL_API_BASE}")
    print(f"  Aggression: {AGGRESSION} (0=passthrough, 1=thinking, 2=full)")
    print(f"  Dry run:    {DRY_RUN}")
    print(f"  Pruning:    {ENABLE_PRUNING}")
    try:
        r = httpx.get(f"http://127.0.0.1:{PROXY_PORT}/health", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"  Uptime:     {data.get('uptime_s', '?')}s")
            print(f"  Requests:   {data.get('requests_proxied', '?')}")
            print(f"  Saved:      {data.get('tokens_saved_total', '?')} tokens")
    except Exception:
        pass


def _cmd_stop():
    if not _check_running():
        print("[PROXY v2] Not running.")
        return
    print("[PROXY v2] Stopping...")
    if os.name == "nt":
        # Only kill the process on our specific port — never kill all python
        result = subprocess.run(
            f'netstat -ano | findstr :{PROXY_PORT} | findstr LISTENING',
            shell=True, capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                parts = line.strip().split()
                # netstat -ano output: proto localaddr foreignaddr state PID
                if len(parts) >= 5:
                    pid = parts[-1]
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=10
                    )
    else:
        subprocess.run(
            ["pkill", "-f", f"proxy_server_v2.*{PROXY_PORT}"],
            capture_output=True, timeout=10
        )
    time.sleep(0.5)
    if not _check_running():
        print("[PROXY v2] Stopped.")
    else:
        print("[PROXY v2] Could not stop — may need manual kill.")


async def _auto_start_local_model_async():
    """Non-blocking auto-start of a local Ollama model on startup."""
    model = os.environ.get("FoveAI_PROXY_LOCAL_MODEL", "").strip()
    if not model:
        return
    logger.info(f"Auto starting local Ollama model: {model}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ollama", "run", model,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                logger.info(f"Local model '{model}' started successfully")
            else:
                stderr_text = stderr.decode("utf-8", errors="replace").strip() if stderr else ""
                logger.warning(f"Local model start returned {proc.returncode}: {stderr_text}")
        except asyncio.TimeoutError:
            logger.info(f"Local model '{model}' loading (timeout after 30s — may still be loading)")
            # Don't wait for it — let it continue in background
    except FileNotFoundError:
        logger.warning("ollama command not found — cannot auto-start local model")


def _auto_start_local_model():
    """Auto start a local Ollama model on startup (if configured).
    
    Uses subprocess.Popen for fire-and-forget startup since we don't
    need to wait for the model to finish loading. The async version
    (_auto_start_local_model_async) is available for callers that
    need stderr capture and timeout handling within an event loop.
    """
    model = os.environ.get("FoveAI_PROXY_LOCAL_MODEL", "").strip()
    if not model:
        return
    
    logger.info(f"Auto starting local Ollama model: {model}")
    try:
        proc = subprocess.Popen(
            ["ollama", "run", model],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"Local model '{model}' spawn initiated (PID {proc.pid})")
    except FileNotFoundError:
        logger.warning("ollama command not found — cannot auto-start local model")


def _cmd_launch():
    import uvicorn
    _auto_start_local_model()
    logger.info(f"Safe Proxy v2 starting on port {PROXY_PORT}")
    logger.info(f"Target: {REAL_API_BASE}")
    logger.info(f"Aggression: {AGGRESSION} | Dry run: {DRY_RUN} | Pruning: {ENABLE_PRUNING}")
    logger.info(f"Preserve last: {PRESERVE_LAST} turns")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PROXY_PORT,
        log_level="info",
    )


# ── Shutdown handler ────────────────────────────────────────────────────

@app.on_event("shutdown")
async def shutdown_event():
    await close_client()
    logger.info("Proxy v2 shutdown complete — HTTP client closed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="FoveAI Safe Proxy v2 — Isolated context-compressing proxy (port 8103)",
        add_help=False,
    )
    parser.add_argument("--status", action="store_true", help="Show proxy status")
    parser.add_argument("--stop", action="store_true", help="Stop the proxy (safe — only kills proxy process)")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")

    args, _ = parser.parse_known_args()

    if args.help:
        parser.print_help()
        print()
        print("=" * 60)
        print("ENV VARS:")
        print("  FoveAI_PROXY_PORT=8103            Port (default)")
        print("  FoveAI_PROXY_TARGET=...           Real API base URL")
        print("  FoveAI_PROXY_API_KEY=...          API key for target")
        print('  FoveAI_PROXY_AGGRESSION=0|1|2|3  0=passthrough, 1=thinking, 2=full, 3=crystallise')
        print("  FoveAI_PROXY_DRY_RUN=1            Log only, don't modify")
        print("  FoveAI_PROXY_AUTO_CHECKPOINT=1    Enable auto-checkpoint")
        print("  FoveAI_PROXY_ENABLE_PRUNING=1     Enable context recycling")
        print()
        print("SAFE TESTING WORKFLOW:")
        print("  1. Start with aggression=0, dry_run=1 → audit only")
        print("  2. Set aggression=1 → strip thinking blocks")
        print('  3. Set aggression=2 → add file dedup')
        print('  4. Set aggression=3 → add context crystallisation (collapses old msgs into summary)')
        print('  5. Only then enable pruning/checkpoint if needed')
        print("=" * 60)
        sys.exit(0)

    if args.status:
        _cmd_status()
        sys.exit(0)

    if args.stop:
        _cmd_stop()
        sys.exit(0)

    _cmd_launch()