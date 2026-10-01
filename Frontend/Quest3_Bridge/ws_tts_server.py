"""
LUMAX Quest 3 TTS WebSocket Streaming Server — Port 8012

Receives text over WebSocket, generates audio via Kokoro TTS (port 8004),
and streams PCM chunks back to the Quest 3 client for real-time playback
and lip-sync via SetVisemeWeight().

Protocol (client → server):
  Text frame: {"type":"speak","text":"Hello world","voice":"af_bella","speed":1.0}
  Text frame: {"type":"stop"}  — stop current utterance
  Text frame: {"type":"config","sample_rate":24000}

Protocol (server → client):
  Binary frame: raw int16 LE PCM @ 24 kHz mono (audio chunk)
  Text frame:   {"type":"start","sample_rate":24000,"visemes":15}
  Text frame:   {"type":"end","duration_ms":1234}
  Text frame:   {"type":"error","message":"..."}
  Text frame:   {"type":"ready","sample_rate":24000}

Env vars:
  LUMAX_TTS_WS_BIND     — host (default 0.0.0.0)
  LUMAX_TTS_WS_PORT     — port (default 8012)
  LUMAX_KOKORO_URL      — Kokoro TTS endpoint (default http://localhost:8004)
  LUMAX_TTS_CHUNK_MS    — chunk duration in ms for streaming (default 200)
"""

import asyncio
import io
import json
import logging
import os
import sys
import time
import wave

import httpx
import numpy as np
import websockets
from websockets.server import serve

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lumax.ws_tts")

# ── Config ──────────────────────────────────────────────────────────────
BIND_HOST = os.getenv("LUMAX_TTS_WS_BIND", "0.0.0.0").strip()
BIND_PORT = int(os.getenv("LUMAX_TTS_WS_PORT", "8012"))
KOKORO_URL = os.getenv("LUMAX_KOKORO_URL", "http://localhost:8004").rstrip("/")
CHUNK_MS = int(os.getenv("LUMAX_TTS_CHUNK_MS", "200"))
TTS_SAMPLE_RATE = 24000  # Kokoro outputs 24 kHz

# ── Helpers ─────────────────────────────────────────────────────────────


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    try:
        return float(v) if v else default
    except (ValueError, TypeError):
        return default


async def _generate_tts(text: str, voice: str, speed: float) -> bytes:
    """Call Kokoro TTS HTTP endpoint and return raw WAV bytes."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{KOKORO_URL}/tts",
            json={"text": text, "voice": voice, "speed": speed},
        )
        resp.raise_for_status()
        return resp.content  # audio/wav


def _wav_to_pcm(wav_bytes: bytes) -> np.ndarray:
    """Extract int16 PCM samples from a WAV byte stream."""
    with io.BytesIO(wav_bytes) as buf, wave.open(buf, "rb") as wf:
        assert wf.getnchannels() == 1, f"Expected mono, got {wf.getnchannels()}"
        assert wf.getsampwidth() == 2, f"Expected 16-bit, got {wf.getsampwidth()}"
        frames = wf.readframes(wf.getnframes())
        return np.frombuffer(frames, dtype=np.int16)


def _split_pcm_into_chunks(pcm: np.ndarray, chunk_samples: int) -> list[bytes]:
    """Split PCM array into chunk-sized byte segments."""
    chunks = []
    for i in range(0, len(pcm), chunk_samples):
        chunk = pcm[i : i + chunk_samples]
        chunks.append(chunk.tobytes())
    return chunks


# ── Per-connection session ──────────────────────────────────────────────
class TTSSession:
    """Manages one WebSocket client's TTS streaming."""

    def __init__(self, ws):
        self.ws = ws
        self.sample_rate = TTS_SAMPLE_RATE
        self.current_task: asyncio.Task | None = None
        self._stop_flag = False

    async def speak(self, text: str, voice: str = "", speed: float = 1.0):
        """Generate TTS audio and stream PCM chunks to the client."""
        if self.current_task and not self.current_task.done():
            self._stop_flag = True
            try:
                await asyncio.wait_for(self.current_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.current_task.cancel()
            self._stop_flag = False

        self.current_task = asyncio.create_task(self._speak_task(text, voice, speed))

    async def _speak_task(self, text: str, voice: str, speed: float):
        """Background task: generate TTS and stream chunks."""
        try:
            # Notify client that audio is starting
            await self.ws.send(
                json.dumps(
                    {
                        "type": "start",
                        "sample_rate": self.sample_rate,
                        "visemes": 15,  # Oculus viseme count
                        "ts": time.time(),
                    }
                )
            )

            # Generate TTS via Kokoro
            wav_bytes = await _generate_tts(text, voice, speed)
            pcm = _wav_to_pcm(wav_bytes)

            # Stream in chunks
            chunk_samples = int(self.sample_rate * CHUNK_MS / 1000)
            chunks = _split_pcm_into_chunks(pcm, chunk_samples)
            total_bytes = len(pcm) * 2
            duration_ms = int(len(pcm) / self.sample_rate * 1000)

            log.info(
                "Streaming TTS: %d chunks, %d samples, %d ms",
                len(chunks),
                len(pcm),
                duration_ms,
            )

            for chunk in chunks:
                if self._stop_flag:
                    log.info("TTS playback stopped by client.")
                    await self.ws.send(json.dumps({"type": "stopped"}))
                    return
                await self.ws.send(chunk)
                # Small yield to let the client process
                await asyncio.sleep(0.001)

            await self.ws.send(
                json.dumps(
                    {
                        "type": "end",
                        "duration_ms": duration_ms,
                        "bytes": total_bytes,
                        "ts": time.time(),
                    }
                )
            )

        except httpx.HTTPStatusError as e:
            log.error("Kokoro TTS HTTP error: %s", e)
            await self.ws.send(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"tts_http_error: {e.response.status_code}",
                    }
                )
            )
        except Exception as e:
            log.error("TTS streaming error: %s", e)
            await self.ws.send(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"tts_error: {e!r}",
                    }
                )
            )

    def stop(self):
        """Signal current utterance to stop."""
        self._stop_flag = True


# ── WebSocket handler ───────────────────────────────────────────────────
async def handle_tts_client(ws):
    """Per-connection WebSocket handler."""
    peer = ws.remote_address if ws.remote_address else "unknown"
    log.info("TTS client connected: %s", peer)

    session = TTSSession(ws)

    await ws.send(
        json.dumps(
            {
                "type": "ready",
                "sample_rate": TTS_SAMPLE_RATE,
                "chunk_ms": CHUNK_MS,
            }
        )
    )

    try:
        async for message in ws:
            if isinstance(message, bytes):
                # Ignore binary frames from client
                continue

            try:
                cmd = json.loads(message)
            except json.JSONDecodeError:
                await ws.send(json.dumps({"type": "error", "message": "invalid JSON"}))
                continue

            msg_type = cmd.get("type", "")

            if msg_type == "speak":
                text = cmd.get("text", "").strip()
                if not text:
                    await ws.send(
                        json.dumps({"type": "error", "message": "empty text"})
                    )
                    continue
                voice = cmd.get("voice", "")
                speed = float(cmd.get("speed", 1.0))
                log.info(
                    "Speak request: '%s...' (voice=%s, speed=%.2f)",
                    text[:60],
                    voice,
                    speed,
                )
                await session.speak(text, voice, speed)

            elif msg_type == "stop":
                session.stop()

            elif msg_type == "config":
                sr = cmd.get("sample_rate", TTS_SAMPLE_RATE)
                if sr != TTS_SAMPLE_RATE:
                    log.warning(
                        "Client requested sr=%d, but Kokoro outputs %d",
                        sr,
                        TTS_SAMPLE_RATE,
                    )
                session.sample_rate = TTS_SAMPLE_RATE  # Always use Kokoro's rate
                await ws.send(
                    json.dumps(
                        {
                            "type": "config_ack",
                            "sample_rate": session.sample_rate,
                        }
                    )
                )

            else:
                await ws.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"unknown type: {msg_type}",
                        }
                    )
                )

    except websockets.exceptions.ConnectionClosed:
        log.info("TTS client disconnected: %s", peer)
    except Exception as e:
        log.error("TTS handler error: %s", e)
    finally:
        session.stop()
        if session.current_task and not session.current_task.done():
            session.current_task.cancel()
        log.info("TTS session ended: %s", peer)


# ── HTTP health endpoint ───────────────────────────────────────────────
async def health_handler(path, request_headers):
    """Minimal HTTP health response for non-WebSocket requests."""
    if path == "/health":
        body = json.dumps(
            {
                "status": "ok",
                "kokoro_url": KOKORO_URL,
                "sample_rate": TTS_SAMPLE_RATE,
                "port": BIND_PORT,
            }
        ).encode()
        return (200, [("Content-Type", "application/json")], body)
    return None


# ── Main ────────────────────────────────────────────────────────────────
async def main():
    log.info(
        "Starting LUMAX Quest 3 TTS WebSocket Bridge on %s:%d", BIND_HOST, BIND_PORT
    )
    log.info("Kokoro TTS backend: %s", KOKORO_URL)

    async with serve(
        handle_tts_client,
        BIND_HOST,
        BIND_PORT,
        process_request=health_handler,
        max_size=2**20,
        ping_interval=20,
        ping_timeout=10,
    ):
        log.info("TTS WS server listening on ws://%s:%d", BIND_HOST, BIND_PORT)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down TTS WS bridge.")
        sys.exit(0)
