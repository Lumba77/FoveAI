"""
FoveAI Media Proxy Server
Lightweight HTTP server that:
  - Proxies YouTube video streams for VR playback
  - Serves as a web content fetcher for the VR browser
  - Streams audio from URLs

Runs alongside the WebSocket IPC server on port 8402.
"""

import asyncio
import logging
import re

from aiohttp import ClientSession, web

logger = logging.getLogger("FoveAI.MediaProxy")


class MediaProxyServer:
    """HTTP proxy for VR browser media streaming."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8402):
        self.host = host
        self.port = port
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/api/health", self._health)
        self.app.router.add_get("/api/youtube/stream", self._youtube_stream)
        self.app.router.add_get("/api/youtube/info", self._youtube_info)
        self.app.router.add_get("/api/web/fetch", self._web_fetch)
        self.app.router.add_get("/api/audio/stream", self._audio_stream)
        self.app.router.add_get("/", self._index)

    async def start(self):
        """Start the HTTP media proxy server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        try:
            await site.start()
            logger.info(
                f"[MediaProxy] ✅ HTTP server listening on http://{self.host}:{self.port}"
            )
            print(f"  [MediaProxy] ✅ HTTP media proxy on :{self.port}")
            await asyncio.Future()  # run forever
        except OSError as e:
            if "address already in use" in str(e).lower() or getattr(
                e, "errno", None
            ) in (10048, 98):
                logger.info(
                    f"[MediaProxy] ⚡ Port :{self.port} already in use — adopting"
                )
                print(f"  [MediaProxy] ⚡ Port :{self.port} already bound — adopting")
                await asyncio.Future()
            else:
                raise

    # ── Routes ──

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "FoveAI Media Proxy"})

    async def _index(self, request: web.Request) -> web.Response:
        return web.Response(
            text="FoveAI Media Proxy — endpoints: /api/youtube/stream, /api/web/fetch, /api/audio/stream",
            content_type="text/plain",
        )

    async def _youtube_info(self, request: web.Request) -> web.Response:
        """Get YouTube video metadata without downloading."""
        video_id = request.query.get("id", "")
        if not video_id:
            return web.json_response({"error": "Missing 'id' parameter"}, status=400)

        try:
            async with ClientSession() as session:
                # Try oEmbed for basic info (no API key needed)
                oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                async with session.get(oembed_url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return web.json_response(
                            {
                                "video_id": video_id,
                                "title": data.get("title", ""),
                                "author": data.get("author_name", ""),
                                "thumbnail": data.get("thumbnail_url", ""),
                            }
                        )
        except Exception as e:
            logger.warning(f"[MediaProxy] YouTube info failed: {e}")

        return web.json_response(
            {"video_id": video_id, "error": "Could not fetch info"}, status=502
        )

    async def _youtube_stream(self, request: web.Request) -> web.StreamResponse:
        """
        Extract direct video stream URL from YouTube and redirect.
        Uses yt-dlp if available, otherwise returns embed page.
        """
        video_id = request.query.get("id", "")
        if not video_id:
            return web.json_response({"error": "Missing 'id' parameter"}, status=400)

        # Try yt-dlp for direct stream extraction
        try:
            import yt_dlp

            ydl_opts = {
                "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
                if info and "url" in info:
                    stream_url = info["url"]
                    title = info.get("title", "Unknown")
                    logger.info(f"[MediaProxy] YouTube stream extracted: {title}")
                    # Redirect to direct stream URL
                    return web.HTTPFound(stream_url)
        except ImportError:
            logger.warning(
                "[MediaProxy] yt-dlp not installed — install with: pip install yt-dlp"
            )
        except Exception as e:
            logger.error(f"[MediaProxy] YouTube extraction failed: {e}")

        # Fallback: return embed page info
        return web.json_response(
            {
                "error": "Direct stream extraction failed. Install yt-dlp: pip install yt-dlp",
                "video_id": video_id,
                "embed_url": f"https://www.youtube.com/embed/{video_id}",
            },
            status=502,
        )

    async def _web_fetch(self, request: web.Request) -> web.Response:
        """
        Fetch a web page and return simplified content for VR rendering.
        Strips scripts, styles, and returns clean HTML.
        """
        url = request.query.get("url", "")
        if not url:
            return web.json_response({"error": "Missing 'url' parameter"}, status=400)

        if not url.startswith("http"):
            url = "https://" + url

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; Quest 3) AppleWebKit/537.36"
            }
            async with ClientSession(headers=headers) as session:
                async with session.get(url, timeout=15, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return web.json_response(
                            {"error": f"HTTP {resp.status}"}, status=502
                        )

                    html = await resp.text()
                    final_url = str(resp.url)

                    # Strip script and style blocks
                    html = re.sub(
                        r"<script[^>]*>.*?</script>",
                        "",
                        html,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    html = re.sub(
                        r"<style[^>]*>.*?</style>",
                        "",
                        html,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

                    # Truncate if too large
                    if len(html) > 50000:
                        html = html[:50000] + "\n<!-- truncated -->"

                    return web.Response(
                        text=html,
                        content_type="text/html",
                        headers={"X-Final-URL": final_url},
                    )
        except asyncio.TimeoutError:
            return web.json_response({"error": "Request timed out"}, status=504)
        except Exception as e:
            logger.error(f"[MediaProxy] Web fetch failed: {e}")
            return web.json_response({"error": str(e)}, status=502)

    async def _audio_stream(self, request: web.Request) -> web.StreamResponse:
        """
        Proxy audio stream — useful for URLs that don't support direct cross-origin requests.
        """
        url = request.query.get("url", "")
        if not url:
            return web.json_response({"error": "Missing 'url' parameter"}, status=400)

        if not url.startswith("http"):
            url = "https://" + url

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; Quest 3)"}
            async with ClientSession(headers=headers) as session:
                async with session.get(url, timeout=30) as resp:
                    if resp.status != 200:
                        return web.json_response(
                            {"error": f"HTTP {resp.status}"}, status=502
                        )

                    stream = web.StreamResponse()
                    stream.content_type = resp.content_type or "audio/mpeg"
                    stream.content_length = resp.content_length

                    await stream.prepare(request)
                    async for chunk in resp.content.iter_any():
                        await stream.write(chunk)
                    await stream.write_eof()
                    return stream
        except Exception as e:
            logger.error(f"[MediaProxy] Audio stream failed: {e}")
            return web.json_response({"error": str(e)}, status=502)


async def main():
    """Run the media proxy server standalone."""
    logging.basicConfig(level=logging.INFO)
    server = MediaProxyServer()
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
