#!/usr/bin/env python3
"""
FoveAI Local Webcam Streamer — captures your desk webcam and serves it
to the Quest as a virtual window feed.

Also fetches real weather data and broadcasts it to the Quest for
SeasonalTheming.

Endpoints:
  GET /webcam/frame   — Latest JPEG frame from the local webcam
  GET /webcam/stream  — MJPEG stream (for RawImage texture updates)
  GET /weather        — Current weather JSON
  WS  /ws             — Pushes weather updates + webcam frames to connected Quest clients

Usage:
  python3 local_webcam.py [--port 8410] [--camera 0] [--city "Stockholm"]

The Quest's WebcamWindowGazing can point to:
  http://<PC_IP>:8410/webcam/frame
"""

import argparse
import asyncio
import base64
import json
import threading
import time

import cv2
from aiohttp import web

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_PORT = 8410
DEFAULT_CAMERA = 0
DEFAULT_CITY = "Stockholm"
WEATHER_API = "https://wttr.in/{city}?format=j1"
FRAME_INTERVAL = 0.1  # 10 FPS for webcam
WEATHER_INTERVAL = 600  # 10 minutes

# ── Webcam capture ──────────────────────────────────────────────────────────


class WebcamCapture:
    """Threaded webcam capture — always has the latest frame ready."""

    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 360):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self._cap = None
        self._latest_frame: bytes | None = None
        self._running = False
        self._lock = threading.Lock()

    def start(self):
        self._cap = cv2.VideoCapture(self.camera_index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not self._cap.isOpened():
            print(f"[Webcam] Cannot open camera {self.camera_index}", flush=True)
            # Try default
            self._cap = cv2.VideoCapture(0)
            if not self._cap.isOpened():
                print(
                    "[Webcam] No camera available — running weather-only mode",
                    flush=True,
                )
                self._cap = None
                return

        self._running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        print(
            f"[Webcam] Camera {self.camera_index} started ({self.width}x{self.height})",
            flush=True,
        )

    def _capture_loop(self):
        while self._running and self._cap:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            # Encode as JPEG
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            with self._lock:
                self._latest_frame = buf.tobytes()
            time.sleep(FRAME_INTERVAL)

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_frame

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()


# ── Weather fetcher ─────────────────────────────────────────────────────────


class WeatherFetcher:
    """Fetches real weather data and caches it."""

    def __init__(self, city: str = DEFAULT_CITY):
        self.city = city
        self._cache: dict | None = None
        self._last_fetch = 0.0
        self._lock = threading.Lock()

    def get_weather(self) -> dict:
        """Return cached weather or fetch fresh."""
        with self._lock:
            if self._cache and (time.time() - self._last_fetch < WEATHER_INTERVAL):
                return self._cache

        # Fetch fresh
        try:
            import urllib.request

            url = WEATHER_API.format(city=self.city)
            req = urllib.request.Request(url, headers={"User-Agent": "FoveAI/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            # Parse wttr.in format
            current = data.get("current_condition", [{}])[0]
            weather = {
                "city": self.city,
                "temp_c": int(current.get("temp_C", 0)),
                "feels_like_c": int(current.get("FeelsLikeC", 0)),
                "humidity": int(current.get("humidity", 0)),
                "description": current.get("weatherDesc", [{}])[0].get(
                    "value", "unknown"
                ),
                "wind_kmph": int(current.get("windspeedKmph", 0)),
                "wind_dir": current.get("winddir16Point", "N"),
                "visibility": int(current.get("visibility", 0)),
                "pressure": int(current.get("pressure", 0)),
                "uv_index": int(current.get("uvIndex", 0)),
                "cloud_cover": int(current.get("cloudcover", 0)),
                "is_day": current.get("dayOrNight", "D") == "D",
                "weather_code": current.get("weatherCode", "0"),
                "fetched_at": time.time(),
            }

            # Determine season from description
            desc = weather["description"].lower()
            if any(w in desc for w in ["snow", "blizzard", "ice", "frost"]):
                weather["season"] = "winter"
            elif any(w in desc for w in ["blossom", "spring", "shower", "mild"]):
                weather["season"] = "spring"
            elif any(w in desc for w in ["sunny", "hot", "clear", "warm", "heat"]):
                weather["season"] = "summer"
            elif any(
                w in desc for w in ["leaf", "autumn", "fall", "mist", "fog", "cool"]
            ):
                weather["season"] = "autumn"
            else:
                # Fallback: month-based
                month = time.localtime().tm_mon
                if month in (12, 1, 2):
                    weather["season"] = "winter"
                elif month in (3, 4, 5):
                    weather["season"] = "spring"
                elif month in (6, 7, 8):
                    weather["season"] = "summer"
                else:
                    weather["season"] = "autumn"

            with self._lock:
                self._cache = weather
                self._last_fetch = time.time()

            print(
                f"[Weather] {self.city}: {weather['temp_c']}°C, {weather['description']}, season={weather['season']}",
                flush=True,
            )
            return weather

        except Exception as e:
            print(f"[Weather] Fetch failed: {e}", flush=True)
            with self._lock:
                if self._cache:
                    return self._cache
            return {
                "city": self.city,
                "temp_c": 0,
                "description": "unknown",
                "season": "spring",
                "error": str(e),
                "fetched_at": time.time(),
            }


# ── Server ──────────────────────────────────────────────────────────────────

webcam: WebcamCapture | None = None
weather: WeatherFetcher | None = None
ws_clients: set = set()


async def handle_webcam_frame(request):
    """Return latest webcam frame as JPEG."""
    if webcam is None:
        return web.Response(text="Webcam not initialized", status=503)

    frame = webcam.get_frame()
    if frame is None:
        return web.Response(text="No frame available", status=503)

    return web.Response(
        body=frame,
        content_type="image/jpeg",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def handle_webcam_stream(request):
    """MJPEG stream for continuous video."""
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await response.prepare(request)

    try:
        while True:
            frame = webcam.get_frame() if webcam else None
            if frame:
                await response.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            await asyncio.sleep(FRAME_INTERVAL)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return response


async def handle_weather(request):
    """Return current weather as JSON."""
    if weather is None:
        return web.json_response({"error": "Weather not initialized"}, status=503)
    return web.json_response(
        weather.get_weather(), headers={"Access-Control-Allow-Origin": "*"}
    )


async def handle_ws(request):
    """WebSocket endpoint for pushing weather + webcam to Quest."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)

    # Send initial weather
    if weather:
        await ws.send_json({"type": "weather", "data": weather.get_weather()})

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "get_weather":
                    if weather:
                        await ws.send_json(
                            {"type": "weather", "data": weather.get_weather()}
                        )
                elif data.get("type") == "get_webcam_frame":
                    frame = webcam.get_frame() if webcam else None
                    if frame:
                        b64 = base64.b64encode(frame).decode()
                        await ws.send_json({"type": "webcam_frame", "data": b64})
    except Exception:
        pass
    finally:
        ws_clients.discard(ws)
    return ws


async def weather_broadcast_loop():
    """Periodically broadcast weather updates to all WS clients."""
    while True:
        await asyncio.sleep(WEATHER_INTERVAL)
        if weather and ws_clients:
            w = weather.get_weather()
            msg = json.dumps({"type": "weather", "data": w})
            dead = set()
            for ws in ws_clients:
                try:
                    await ws.send_str(msg)
                except Exception:
                    dead.add(ws)
            ws_clients -= dead


async def main():
    global webcam, weather

    parser = argparse.ArgumentParser(description="FoveAI Local Webcam + Weather")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--camera", type=int, default=DEFAULT_CAMERA)
    parser.add_argument("--city", type=str, default=DEFAULT_CITY)
    parser.add_argument("--no-webcam", action="store_true", help="Weather only")
    args = parser.parse_args()

    print(
        f"""
  ╔══════════════════════════════════════════════════╗
  ║  FoveAI Local Webcam + Weather Streamer          ║
  ╠══════════════════════════════════════════════════╣
  ║  Webcam: http://0.0.0.0:{args.port}/webcam/frame           ║
  ║  Stream: http://0.0.0.0:{args.port}/webcam/stream          ║
  ║  Weather: http://0.0.0.0:{args.port}/weather               ║
  ║  WS:      ws://0.0.0.0:{args.port}/ws                      ║
  ║  City: {args.city:<43s} ║
  ╚══════════════════════════════════════════════════╝
    """,
        flush=True,
    )

    # Initialize
    if not args.no_webcam:
        webcam = WebcamCapture(args.camera)
        webcam.start()

    weather = WeatherFetcher(args.city)
    weather.get_weather()  # Initial fetch

    # Start server
    app = web.Application()
    app.router.add_get("/webcam/frame", handle_webcam_frame)
    app.router.add_get("/webcam/stream", handle_webcam_stream)
    app.router.add_get("/weather", handle_weather)
    app.router.add_get("/ws", handle_ws)

    # Start weather broadcast
    asyncio.create_task(weather_broadcast_loop())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", args.port)
    await site.start()

    print(f"  [Server] Listening on :{args.port}", flush=True)
    print(
        f"  [Quest] Point WebcamWindowGazing to http://<PC_IP>:{args.port}/webcam/frame",
        flush=True,
    )

    # Keep running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Bye!", flush=True)
        if webcam:
            webcam.stop()
