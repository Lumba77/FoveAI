"""
VoiceChat — Minimal Voice & Text Chat Frontend
================================================
Single-page chat UI with push-to-talk voice input and text fallback.
Connects directly to the XRLF Plumax engine on port 8400.

Usage:
    python server.py [--port 8080] [--upstream http://127.0.0.1:8400]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import httpx

try:
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
except ImportError:
    print("Missing dependencies. Run: pip install fastapi uvicorn")
    sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────
DEFAULT_UPSTREAM = "http://127.0.0.1:8400"
PORT = int(os.environ.get("VOICECHAT_PORT", "8080"))
UPSTREAM = os.environ.get("VOICECHAT_UPSTREAM", DEFAULT_UPSTREAM)

app = FastAPI(title="LUMAX Voice Chat")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_html() -> str:
    """Load the chat HTML from the same directory."""
    html_path = Path(__file__).parent / "chat.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<html><body><h1>chat.html not found</h1></body></html>"


@app.get("/", response_class=HTMLResponse)
async def index():
    html = load_html()
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/health")
async def health():
    # Check if upstream XRLF is alive
    try:
        r = urllib.request.urlopen(f"{UPSTREAM}/health", timeout=3)
        upstream_status = json.loads(r.read())
        return {
            "status": "ok",
            "upstream": UPSTREAM,
            "upstream_ok": True,
            "model": upstream_status.get("model", "unknown"),
        }
    except Exception as e:
        return {
            "status": "degraded",
            "upstream": UPSTREAM,
            "upstream_ok": False,
            "error": str(e),
        }


@app.post("/api/chat")
async def chat(request: Request):
    """Proxy chat request to upstream XRLF engine on 8400."""
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    # Default model if not specified
    model = body.get("model", "lumax-plumax-omni-router")

    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": stream,
            "max_tokens": body.get("max_tokens", 512),
            "temperature": body.get("temperature", 0.7),
        }
    ).encode()

    if stream:
        return StreamingResponse(
            _stream_chat(payload),
            media_type="text/event-stream",
        )

    try:
        req = urllib.request.Request(
            f"{UPSTREAM}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


async def _stream_chat(payload: bytes):
    """Stream chat response chunks from upstream using httpx for proper SSE support."""
    try:
        async with httpx.AsyncClient(timeout=120) as client, client.stream(
            "POST",
            f"{UPSTREAM}/v1/chat/completions",
            content=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            async for chunk in resp.aiter_text():
                if chunk:
                    yield chunk
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


def main():
    global PORT, UPSTREAM
    parser = argparse.ArgumentParser(description="LUMAX Voice Chat Frontend")
    parser.add_argument("--port", type=int, default=PORT, help="Port to serve on")
    parser.add_argument("--upstream", default=UPSTREAM, help="XRLF engine URL")
    args = parser.parse_args()

    PORT = args.port
    UPSTREAM = args.upstream

    print("\n  🎙️  LUMAX Voice Chat")
    print(f"     Listen : http://127.0.0.1:{PORT}")
    print(f"     Engine : {UPSTREAM}")
    print("     Open your browser and start talking!\n")

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
