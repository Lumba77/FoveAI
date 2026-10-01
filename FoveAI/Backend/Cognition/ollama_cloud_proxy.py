"""
Ollama Cloud Proxy — Simple transparent proxy (port 8107)
that forwards all /v1/* requests to Ollama Cloud with the API key injected.

Chain position: TokenSlayer Proxy (8106) → Ollama Cloud Proxy (8107) → Ollama Cloud
"""

import json
import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OllamaCloudProxy")

# ── Config ────────────────────────────────────────────────────────────

FORGE_DIR = Path(__file__).parent.resolve()

# Load .env from repo root
_env_path = FORGE_DIR.parent.parent / ".env"
if _env_path.is_file():
    try:
        import dotenv

        dotenv.load_dotenv(str(_env_path), override=True)
    except ImportError:
        pass

OLLAMA_CLOUD_BASE = (
    (os.environ.get("FoveAI_CLOUD_BASE_URL", "") or "https://ollama.com")
    .strip()
    .rstrip("/")
)

API_KEY = (
    os.environ.get("FoveAI_PROXY_API_KEY", "") or os.environ.get("OLLAMA_API_KEY", "")
).strip()

PROXY_PORT = int(os.environ.get("OLLAMA_CLOUD_PROXY_PORT", "8107"))

# ── App ─────────────────────────────────────────────────────────────

app = FastAPI(title="Ollama Cloud Proxy", version="1.0.0")


@app.get("/health")
async def health():
    return {
        "status": "ONLINE",
        "service": "Ollama Cloud Proxy",
        "port": PROXY_PORT,
        "target": OLLAMA_CLOUD_BASE,
        "api_key_configured": bool(API_KEY),
    }


@app.api_route(
    "/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
)
async def proxy_v1(path: str, request: Request):
    """Forward any /v1/* request to Ollama Cloud with API key injected."""
    method = request.method

    # Read body for methods that support it
    body = None
    if method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
        except Exception:
            body = {}

    # Build upstream URL
    query_str = str(request.url.query)
    url = f"{OLLAMA_CLOUD_BASE}/v1/{path}" + (f"?{query_str}" if query_str else "")

    # Forward headers (strip host/content-length, inject auth)
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    is_streaming = isinstance(body, dict) and body.get("stream", False)

    if is_streaming:
        return await _proxy_streaming(url, headers, body, method)
    else:
        return await _proxy_non_streaming(url, headers, body, method)


async def _proxy_non_streaming(url: str, headers: dict, body: dict | None, method: str):
    """Forward a non-streaming request."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            elif method == "PUT":
                resp = await client.put(url, json=body, headers=headers)
            elif method == "PATCH":
                resp = await client.patch(url, json=body, headers=headers)
            else:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as e:
            logger.error(f"Upstream request failed: {e}")
            return JSONResponse(
                content={"error": f"Upstream request failed: {e!s}"},
                status_code=502,
            )

    content_type = resp.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except (json.JSONDecodeError, ValueError):
            pass

    return StreamingResponse(
        content=resp.iter_bytes(),
        status_code=resp.status_code,
        media_type=content_type or "text/plain",
        headers={
            k: v
            for k, v in resp.headers.items()
            if k.lower()
            not in ("content-encoding", "transfer-encoding", "content-length")
        },
    )


async def _proxy_streaming(url: str, headers: dict, body: dict, method: str):
    """Forward a streaming (SSE) request."""

    async def generate():
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                async with client.stream(
                    method, url, json=body, headers=headers
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        error_detail = error_body.decode("utf-8", errors="replace")
                        logger.error(
                            f"Upstream streaming returned {resp.status_code}: {error_detail[:300]}"
                        )
                        error_sse = json.dumps(
                            {
                                "error": f"Upstream returned {resp.status_code}",
                                "detail": error_detail,
                            }
                        )
                        yield f"data: {error_sse}\n\n".encode()
                        return

                    async for chunk in resp.aiter_bytes():
                        yield chunk
            except httpx.RequestError as e:
                logger.error(f"Streaming upstream request failed: {e}")
                error_sse = json.dumps({"error": f"Streaming request failed: {e!s}"})
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


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Ollama Cloud Proxy starting on port {PROXY_PORT}")
    logger.info(f"Target: {OLLAMA_CLOUD_BASE}")
    logger.info(f"API key configured: {bool(API_KEY)}")
    uvicorn.run(app, host="127.0.0.1", port=PROXY_PORT, log_level="info")
