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
            media_port = getattr(cfg, "MEDIA_PROXY_PORT", 8402)
        except ImportError:
            media_host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")
            media_port = int(os.getenv("FOVEAI_MEDIA_PROXY_PORT", "8402"))

        media_proxy = MediaProxyServer(host=media_host, port=media_port)
        media_proxy_task = asyncio.create_task(media_proxy.start())
        logger.info(f"[FoveAI] Media proxy starting on :{media_port}")
    except Exception as e:
        logger.warning(f"[FoveAI] Media proxy not started: {e}")

    # Start WebSocket IPC server
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from server_config import ServerConfig as cfg

        _host = cfg.BIND_HOST
        _port = cfg.WS_PORT
    except ImportError:
        _host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")
        _port = int(os.getenv("FOVEAI_WS_PORT", "8400"))
    server = IPCServer(host=_host, port=_port)

    # Start the AI Director daemon — the off-scene creative mind
    director = None
    try:
        from app.IPC.director_daemon import DirectorDaemon

        director = DirectorDaemon(ws_server=server)
        server.attach_director(director)
        await director.start()
        logger.info("[FoveAI] AI Director daemon started — the garden is growing")
    except Exception as e:
        logger.warning(f"[FoveAI] Director daemon not started: {e}")

    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
