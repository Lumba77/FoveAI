#!/usr/bin/env python3
"""
FoveAI Multi-Cam Streamer — serves up to 5 webcams + weather to the Quest.

Each webcam becomes a "room" Alice can see through. Switch between rooms
on the Quest, or let Alice auto-cycle through them.

Endpoints:
  GET /cams                    — List all available cameras + their rooms
  GET /cam/{id}/frame          — Latest JPEG from camera N (0-4)
  GET /cam/{id}/stream         — MJPEG stream from camera N
  GET /cam/all/frames          — All cameras as a mosaic JPEG
  GET /weather                 — Current weather JSON
  WS  /ws                      — Push frames + weather to Quest clients

Usage:
  python3 multi_cam.py [--port 8410] [--city Stockholm]
  python3 multi_cam.py --rooms "Desk,Kitchen,Living Room,Garage,Garden"

The Quest's WebcamWindowGazing can point to:
  http://<PC_IP>:8410/cam/0/frame   (Desk)
  http://<PC_IP>:8410/cam/1/frame   (Kitchen)
  http://<PC_IP>:8410/cam/2/frame   (Living Room)
  etc.
"""

import argparse
import asyncio
import base64
import io
import json
import os
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from aiohttp import web, ClientSession

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_PORT = 8410
DEFAULT_CITY = "Stockholm"
DEFAULT_ROOMS = "Desk,Kitchen,Living Room,Garage,Garden"
FRAME_INTERVAL = 0.1  # 10 FPS per camera
WEATHER_INTERVAL = 600  # 10 minutes
MOSAIC_WIDTH = 1280
MOSAIC_HEIGHT = 720

# ── Multi-camera capture ────────────────────────────────────────────────────

class CameraCapture:
    """Threaded capture for a single camera."""

    def __init__(self, cam_id: int, room_name: str, width: int = 640, height: int = 360):
        self.cam_id = cam_id
        self.room_name = room_name
        self.width = width
        self.height = height
        self._cap = None
        self._latest_frame: bytes | None = None
        self._latest_mat = None  # cv2 frame for mosaic
        self._running = False
        self._lock = threading.Lock()
        self.connected = False

    def start(self) -> bool:
        """Try to open the camera. Returns True if successful."""
        # Try the camera index directly
        self._cap = cv2.VideoCapture(self.cam_id)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not self._cap.isOpened():
            # Try with V4L2 backend
            self._cap = cv2.VideoCapture(self.cam_id, cv2.CAP_V4L2)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not self._cap.isOpened():
            print(f"  [Cam {self.cam_id}] ✕ {self.room_name} — not available", flush=True)
            self.connected = False
            return False

        self._running = True
        self.connected = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        print(f"  [Cam {self.cam_id}] ● {self.room_name} — live ({self.width}x{self.height})", flush=True)
        return True

    def _capture_loop(self):
        while self._running and self._cap:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.5)
                # Try to reconnect
                self._cap.release()
                time.sleep(1.0)
                self._cap = cv2.VideoCapture(self.cam_id, cv2.CAP_V4L2)
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                continue

            # Encode as JPEG
            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            with self._lock:
                self._latest_frame = buf.tobytes()
                self._latest_mat = frame
            time.sleep(FRAME_INTERVAL)

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_frame

    def get_mat(self):
        with self._lock:
            return self._latest_mat.copy() if self._latest_mat is not None else None

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()


class MultiCamManager:
    """Manages multiple cameras across rooms."""

    def __init__(self, room_names: list[str]):
        self.room_names = room_names
        self.cameras: dict[int, CameraCapture] = {}
        self.max_cams = len(room_names)

    def start_all(self):
        """Try to open all cameras. Available ones go live, others are skipped."""
        print(f"\n  [MultiCam] Scanning for up to {self.max_cams} cameras...", flush=True)
        for i, room in enumerate(self.room_names):
            cam = CameraCapture(i, room)
            if cam.start():
                self.cameras[i] = cam
            time.sleep(0.3)  # let each camera settle

        print(f"  [MultiCam] {len(self.cameras)}/{self.max_cams} cameras live", flush=True)

    def get_camera(self, cam_id: int) -> CameraCapture | None:
        return self.cameras.get(cam_id)

    def get_available(self) -> list[dict]:
        """List available cameras with room names."""
        result = []
        for cam_id, cam in self.cameras.items():
            result.append({
                "id": cam_id,
                "room": cam.room_name,
                "width": cam.width,
                "height": cam.height,
                "live": cam.connected,
            })
        return result

    def get_mosaic(self) -> bytes | None:
        """Create a mosaic of all cameras in a single frame."""
        mats = []
        for cam_id in sorted(self.cameras.keys()):
            mat = self.cameras[cam_id].get_mat()
            if mat is not None:
                # Resize to uniform size
                mat = cv2.resize(mat, (320, 180))
                # Add room label
                cv2.putText(mat, f"Cam {cam_id}: {self.cameras[cam_id].room_name}",
                           (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                mats.append(mat)

        if not mats:
            return None

        # Arrange in a grid (up to 3 columns)
        cols = min(3, len(mats))
        rows = (len(mats) + cols - 1) // cols

        # Pad to fill grid
        while len(mats) < cols * rows:
            mats.append(np.zeros((180, 320, 3), dtype=np.uint8))

        # Build grid
        grid_rows = []
        for r in range(rows):
            row_mats = mats[r * cols : (r + 1) * cols]
            grid_rows.append(np.hstack(row_mats))
        mosaic = np.vstack(grid_rows)

        _, buf = cv2.imencode('.jpg', mosaic, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()

    def stop_all(self):
        for cam in self.cameras.values():
            cam.stop()


# ── Weather fetcher (same as before) ────────────────────────────────────────

class WeatherFetcher:
    def __init__(self, city: str = DEFAULT_CITY):
        self.city = city
        self._cache = None
        self._last_fetch = 0.0
        self._lock = threading.Lock()

    def get_weather(self) -> dict:
        with self._lock:
            if self._cache and (time.time() - self._last_fetch < WEATHER_INTERVAL):
                return self._cache

        try:
            import urllib.request
            url = f"https://wttr.in/{self.city}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "FoveAI/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            current = data.get("current_condition", [{}])[0]
            weather = {
                "city": self.city,
                "temp_c": int(current.get("temp_C", 0)),
                "feels_like_c": int(current.get("FeelsLikeC", 0)),
                "humidity": int(current.get("humidity", 0)),
                "description": current.get("weatherDesc", [{}])[0].get("value", "unknown"),
                "wind_kmph": int(current.get("windspeedKmph", 0)),
                "wind_dir": current.get("winddir16Point", "N"),
                "is_day": current.get("dayOrNight", "D") == "D",
                "fetched_at": time.time(),
            }

            # Season detection
            desc = weather["description"].lower()
            if any(w in desc for w in ["snow", "blizzard", "ice"]):
                weather["season"] = "winter"
            elif any(w in desc for w in ["blossom", "spring", "shower"]):
                weather["season"] = "spring"
            elif any(w in desc for w in ["sunny", "hot", "clear", "warm"]):
                weather["season"] = "summer"
            elif any(w in desc for w in ["leaf", "autumn", "fall", "mist", "fog", "cool"]):
                weather["season"] = "autumn"
            else:
                month = time.localtime().tm_mon
                weather["season"] = ["winter","spring","spring","spring","summer","summer",
                                    "summer","autumn","autumn","autumn","winter","winter"][month-1]

            with self._lock:
                self._cache = weather
                self._last_fetch = time.time()

            print(f"  [Weather] {self.city}: {weather['temp_c']}°C, {weather['description']}", flush=True)
            return weather
        except Exception as e:
            print(f"  [Weather] Fetch failed: {e}", flush=True)
            return {"city": self.city, "error": str(e), "fetched_at": time.time()}


# ── Server ──────────────────────────────────────────────────────────────────

cam_manager: MultiCamManager | None = None
weather_fetcher: WeatherFetcher | None = None
ws_clients: set = set()

async def handle_cams_list(request):
    """List all available cameras."""
    cams = cam_manager.get_available() if cam_manager else []
    return web.json_response({"cameras": cams},
                             headers={"Access-Control-Allow-Origin": "*"})

async def handle_cam_frame(request):
    """Get latest frame from a specific camera."""
    cam_id = int(request.match_info['id'])
    cam = cam_manager.get_camera(cam_id) if cam_manager else None
    if cam is None:
        return web.json_response({"error": f"Camera {cam_id} not available"}, status=404)
    frame = cam.get_frame()
    if frame is None:
        return web.json_response({"error": "No frame yet"}, status=503)
    return web.Response(body=frame, content_type="image/jpeg",
                        headers={"Access-Control-Allow-Origin": "*"})

async def handle_cam_stream(request):
    """MJPEG stream from a specific camera."""
    cam_id = int(request.match_info['id'])
    cam = cam_manager.get_camera(cam_id) if cam_manager else None
    if cam is None:
        return web.json_response({"error": f"Camera {cam_id} not available"}, status=404)

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
            frame = cam.get_frame()
            if frame:
                await response.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            await asyncio.sleep(FRAME_INTERVAL)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return response

async def handle_mosaic(request):
    """Get a mosaic of all cameras in one frame."""
    frame = cam_manager.get_mosaic() if cam_manager else None
    if frame is None:
        return web.json_response({"error": "No cameras available"}, status=503)
    return web.Response(body=frame, content_type="image/jpeg",
                        headers={"Access-Control-Allow-Origin": "*"})

async def handle_weather(request):
    """Get current weather."""
    if weather_fetcher is None:
        return web.json_response({"error": "Weather not initialized"}, status=503)
    return web.json_response(weather_fetcher.get_weather(),
                             headers={"Access-Control-Allow-Origin": "*"})

async def handle_ws(request):
    """WebSocket for pushing frames + weather to Quest."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)

    # Send initial state
    if cam_manager:
        await ws.send_json({"type": "cams", "data": cam_manager.get_available()})
    if weather_fetcher:
        await ws.send_json({"type": "weather", "data": weather_fetcher.get_weather()})

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "get_weather":
                    if weather_fetcher:
                        await ws.send_json({"type": "weather", "data": weather_fetcher.get_weather()})
                elif data.get("type") == "get_cams":
                    if cam_manager:
                        await ws.send_json({"type": "cams", "data": cam_manager.get_available()})
                elif data.get("type") == "get_frame":
                    cam_id = data.get("cam_id", 0)
                    cam = cam_manager.get_camera(cam_id) if cam_manager else None
                    if cam:
                        frame = cam.get_frame()
                        if frame:
                            b64 = base64.b64encode(frame).decode()
                            await ws.send_json({"type": "frame", "cam_id": cam_id, "data": b64})
                elif data.get("type") == "get_mosaic":
                    frame = cam_manager.get_mosaic() if cam_manager else None
                    if frame:
                        b64 = base64.b64encode(frame).decode()
                        await ws.send_json({"type": "mosaic", "data": b64})
    except Exception:
        pass
    finally:
        ws_clients.discard(ws)
    return ws

async def weather_loop():
    """Periodically broadcast weather updates."""
    while True:
        await asyncio.sleep(WEATHER_INTERVAL)
        if weather_fetcher and ws_clients:
            w = weather_fetcher.get_weather()
            msg = json.dumps({"type": "weather", "data": w})
            dead = set()
            for ws in ws_clients:
                try: await ws.send_str(msg)
                except: dead.add(ws)
            ws_clients -= dead

async def cam_broadcast_loop():
    """Periodically push mosaic frames to WS clients (every 2s)."""
    while True:
        await asyncio.sleep(2.0)
        if cam_manager and ws_clients:
            frame = cam_manager.get_mosaic()
            if frame:
                b64 = base64.b64encode(frame).decode()
                msg = json.dumps({"type": "mosaic", "data": b64})
                dead = set()
                for ws in ws_clients:
                    try: await ws.send_str(msg)
                    except: dead.add(ws)
                ws_clients -= dead

async def main():
    global cam_manager, weather_fetcher

    parser = argparse.ArgumentParser(description="FoveAI Multi-Cam + Weather Streamer")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--city", type=str, default=DEFAULT_CITY)
    parser.add_argument("--rooms", type=str, default=DEFAULT_ROOMS,
                       help="Comma-separated room names for each camera")
    parser.add_argument("--no-cam", action="store_true", help="Weather only")
    args = parser.parse_args()

    rooms = [r.strip() for r in args.rooms.split(",")]

    print(f"""
  ╔══════════════════════════════════════════════════════╗
  ║  FoveAI Multi-Cam Streamer — {len(rooms)} rooms              ║
  ╠══════════════════════════════════════════════════════╣""", flush=True)
    for i, room in enumerate(rooms):
        print(f"  ║  Cam {i}: {room:<44s} ║", flush=True)
    print(f"""  ╠══════════════════════════════════════════════════════╣
  ║  Cams:   http://0.0.0.0:{args.port}/cams                    ║
  ║  Frame:  http://0.0.0.0:{args.port}/cam/{{id}}/frame          ║
  ║  Stream: http://0.0.0.0:{args.port}/cam/{{id}}/stream         ║
  ║  Mosaic: http://0.0.0.0:{args.port}/cam/all/frames            ║
  ║  Weather:http://0.0.0.0:{args.port}/weather                   ║
  ║  WS:     ws://0.0.0.0:{args.port}/ws                         ║
  ╚══════════════════════════════════════════════════════╝
    """, flush=True)

    # Initialize cameras
    if not args.no_cam:
        cam_manager = MultiCamManager(rooms)
        cam_manager.start_all()

    # Initialize weather
    weather_fetcher = WeatherFetcher(args.city)
    weather_fetcher.get_weather()

    # Server
    app = web.Application()
    app.router.add_get("/cams", handle_cams_list)
    app.router.add_get("/cam/{id}/frame", handle_cam_frame)
    app.router.add_get("/cam/{id}/stream", handle_cam_stream)
    app.router.add_get("/cam/all/frames", handle_mosaic)
    app.router.add_get("/weather", handle_weather)
    app.router.add_get("/ws", handle_ws)

    asyncio.create_task(weather_loop())
    asyncio.create_task(cam_broadcast_loop())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", args.port)
    await site.start()

    print(f"  [Server] Listening on :{args.port}", flush=True)
    if cam_manager and cam_manager.cameras:
        print(f"  [Quest] WebcamWindowGazing → http://<PC_IP>:{args.port}/cam/0/frame", flush=True)
        print(f"  [Quest] Mosaic (all rooms) → http://<PC_IP>:{args.port}/cam/all/frames", flush=True)

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Bye!", flush=True)
        if cam_manager:
            cam_manager.stop_all()
