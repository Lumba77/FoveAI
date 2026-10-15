"""
app/IPC/http_proxy.py — Unified HTTP proxy on :8400.

Handles web requests, memory proxy calls, and forwards chat completions
to the XRLF runtime on :8402. The WebSocket for Quest clients is on :8403,
owned by the XRLF runtime itself.

Routes:
  POST /v1/chat/completions  → proxy to XRLF :8402
  GET  /health               → health check
  GET  /themes               → theme manifest for GTK tray and multigate
  GET  /soul/status          → proxy to XRLF :8402
  GET  /memory/status        → proxy to XRLF :8402
  GET  /v1/models            → proxy to XRLF :8402
  GET  /                     → info page
"""

import asyncio
import json
import logging
import os

import aiohttp
from aiohttp import web

logger = logging.getLogger("FoveAI.HTTPProxy")


def _chat_timeout() -> float:
    """Upstream chat timeout in seconds (cloud reasoning models need headroom)."""
    try:
        return max(10.0, float(os.getenv("FoveAI_CHAT_PROXY_TIMEOUT", "300") or "300"))
    except ValueError:
        return 300.0


class HttpProxyServer:
    """
    HTTP proxy server that forwards requests to the XRLF runtime.
    Serves on :8400 — the unified HTTP port for web requests and memory.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8400,
        xrlf_url: str = "http://127.0.0.1:8402",
    ):
        self.host = host
        self.port = port
        self.xrlf_url = xrlf_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._runner: web.AppRunner | None = None

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/health", self._health)
        app.router.add_get("/themes", self._themes)
        app.router.add_post("/v1/chat/completions", self._chat_completions)
        app.router.add_get("/v1/chat/completions", self._chat_completions_get)
        app.router.add_get("/soul/status", self._proxy_get)
        app.router.add_get("/memory/status", self._proxy_get)
        app.router.add_get("/v1/models", self._proxy_get)
        app.router.add_post("/v1/completions", self._proxy_post)
        app.router.add_post("/v1/embeddings", self._proxy_post)
        return app

    # ── Handlers ────────────────────────────────────────────────────────────

    async def _index(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "service": "FoveAI HTTP Proxy",
                "port": self.port,
                "xrlf_url": self.xrlf_url,
                "routes": [
                    "POST /v1/chat/completions",
                    "GET  /health",
                    "GET  /themes",
                    "GET  /soul/status",
                    "GET  /memory/status",
                    "GET  /v1/models",
                ],
            }
        )

    async def _health(self, request: web.Request) -> web.Response:
        # Check if XRLF is reachable
        try:
            assert self._session is not None
            async with self._session.get(
                f"{self.xrlf_url}/health", timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                xrlf_ok = resp.status == 200
        except Exception:
            xrlf_ok = False
        return web.json_response(
            {
                "status": "ok" if xrlf_ok else "degraded",
                "proxy_port": self.port,
                "xrlf_url": self.xrlf_url,
                "xrlf_reachable": xrlf_ok,
            }
        )

    async def _themes(self, request: web.Request) -> web.Response:
        """Serve theme manifest from Backend/themes/manifest.json."""
        import json
        from pathlib import Path

        # Try to find themes directory relative to backend
        backend_dir = Path(__file__).parent.parent.parent
        manifest_path = backend_dir / "themes" / "manifest.json"

        if not manifest_path.exists():
            # Fallback to relative from FoveAI root
            foveai_dir = backend_dir.parent
            manifest_path = foveai_dir / "Backend" / "themes" / "manifest.json"

        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                return web.json_response(manifest)
            except Exception as e:
                logger.error(f"[HTTPProxy] Failed to load theme manifest: {e}")
                return web.json_response(
                    {"error": "Failed to load theme manifest", "detail": str(e)},
                    status=500,
                )
        else:
            # Return empty manifest if file doesn't exist
            return web.json_response(
                {"themes": [], "default": "foveai-celestial", "error": "Manifest not found"}
            )

    async def _chat_completions(self, request: web.Request) -> web.StreamResponse:
        """Proxy chat completions to XRLF, with streaming support."""
        try:
            body = await request.read()
            # Check if streaming is requested
            try:
                payload = json.loads(body)
                stream = payload.get("stream", False)
            except json.JSONDecodeError:
                stream = False

            headers = {"Content-Type": "application/json"}
            # Forward auth header if present
            auth = request.headers.get("Authorization")
            if auth:
                headers["Authorization"] = auth

            assert self._session is not None
            if stream:
                # Stream response back
                resp = await self._session.post(
                    f"{self.xrlf_url}/v1/chat/completions",
                    data=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=_chat_timeout()),
                )
                sresp = web.StreamResponse(
                    status=resp.status,
                    headers={"Content-Type": "text/event-stream"},
                )
                await sresp.prepare(request)
                async for chunk in resp.content:
                    await sresp.write(chunk)
                await sresp.write_eof()
                return sresp
            else:
                # Non-streaming
                async with self._session.post(
                    f"{self.xrlf_url}/v1/chat/completions",
                    data=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=_chat_timeout()),
                ) as resp:
                    body_resp = await resp.read()
                    return web.Response(
                        status=resp.status,
                        body=body_resp,
                        content_type="application/json",
                    )
        except aiohttp.ClientConnectorError:
            return web.json_response(
                {
                    "error": {
                        "message": "XRLF runtime not reachable",
                        "url": self.xrlf_url,
                    }
                },
                status=502,
            )
        except Exception as e:
            logger.error(f"[HTTPProxy] chat/completions error: {e}")
            return web.json_response(
                {"error": {"message": str(e)}},
                status=500,
            )

    async def _chat_completions_get(self, request: web.Request) -> web.Response:
        """GET on chat completions — return info."""
        return web.json_response(
            {
                "endpoint": "/v1/chat/completions",
                "method": "POST",
                "xrlf_url": f"{self.xrlf_url}/v1/chat/completions",
            }
        )

    async def _proxy_get(self, request: web.Request) -> web.Response:
        """Proxy a GET request to XRLF."""
        path = request.path
        try:
            assert self._session is not None
            async with self._session.get(
                f"{self.xrlf_url}{path}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.read()
                return web.Response(
                    status=resp.status,
                    body=body,
                    content_type="application/json",
                )
        except aiohttp.ClientConnectorError:
            return web.json_response(
                {"error": "XRLF runtime not reachable", "url": self.xrlf_url},
                status=502,
            )
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _proxy_post(self, request: web.Request) -> web.Response:
        """Proxy a POST request to XRLF."""
        path = request.path
        try:
            body = await request.read()
            assert self._session is not None
            async with self._session.post(
                f"{self.xrlf_url}{path}",
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                body_resp = await resp.read()
                return web.Response(
                    status=resp.status,
                    body=body_resp,
                    content_type="application/json",
                )
        except aiohttp.ClientConnectorError:
            return web.json_response(
                {"error": "XRLF runtime not reachable", "url": self.xrlf_url},
                status=502,
            )
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self):
        """Start the HTTP proxy server."""
        self._session = aiohttp.ClientSession()
        app = self._build_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        try:
            await site.start()
            logger.info(f"[HTTPProxy] ✅ Listening on http://{self.host}:{self.port}")
            print(
                f"  [HTTPProxy] ✅ Unified HTTP proxy on :{self.port} → {self.xrlf_url}"
            )
        except OSError as e:
            logger.error(f"[HTTPProxy] ❌ Failed to bind :{self.port}: {e}")
            print(f"  [HTTPProxy] ❌ Port :{self.port} in use or unavailable: {e}")
            raise
        await asyncio.Future()  # run forever

    async def stop(self):
        """Stop the server."""
        if self._runner:
            await self._runner.cleanup()
        if self._session:
            await self._session.close()
        logger.info("[HTTPProxy] Stopped")
