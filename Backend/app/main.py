"""Main entry point for FoveAI Backend Server."""
import asyncio
import logging
import os
import sys
try:
    from app.IPC.websocket_server import IPCServer
except ImportError:
    from app.IPC.websocket_server import IPCServer  # type: ignore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FoveAI")

async def main():
    logger.info("Initializing FoveAI Backend Engine...")

    # Start media proxy HTTP server (for VR browser: YouTube, web fetch, audio streaming)
    media_proxy_task = None
    try:
        from app.media_proxy_server import MediaProxyServer
        try:
            from server_config import ServerConfig as cfg
            media_host = cfg.BIND_HOST
            media_port = getattr(cfg, 'MEDIA_PROXY_PORT', 8402)
        except ImportError:
            media_host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")
            media_port = int(os.getenv("FOVEAI_MEDIA_PROXY_PORT", "8402"))

        media_proxy = MediaProxyServer(host=media_host, port=media_port)
        media_proxy_task = asyncio.create_task(media_proxy.start())
        logger.info(f"[FoveAI] Media proxy starting on :{media_port}")
    except Exception as e:
        logger.warning(f"[FoveAI] Media proxy not started: {e}")

    # Start HTTP proxy on :8400 — web requests, memory, proxy calls to XRLF
    # The WebSocket for Quest clients is on :8403 (owned by XRLF runtime).
    # 8400 is the unified HTTP proxy: chat completions, soul status, memory, TTS.
    proxy_port = int(os.getenv("FOVEAI_LEGACY_WS_PORT", "8400"))
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from server_config import ServerConfig as cfg
        _host = cfg.BIND_HOST
    except ImportError:
        _host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")

    from app.IPC.http_proxy import HttpProxyServer
    xrlf_url = os.getenv("FOVEAI_XRLF_URL", "http://127.0.0.1:8402")
    proxy = HttpProxyServer(host=_host, port=proxy_port, xrlf_url=xrlf_url)
    proxy_task = asyncio.create_task(proxy.start())
    logger.info(f"[FoveAI] HTTP proxy on :{proxy_port} → proxying to XRLF {xrlf_url}")

    # Keep the process alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
