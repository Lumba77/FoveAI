"""
LUMAX Quest 3 STT WebSocket Bridge — Port 8011

Receives raw 16-bit PCM mono audio from Quest 3 over WebSocket,
buffers it into ~1-second chunks, runs faster-whisper transcription
on the RTX 4060 GPU, and returns partial/final transcripts as JSON.

Protocol (client → server):
  Binary frame: raw int16 LE PCM @ 16 kHz mono
  Text frame:   {"type":"config","sample_rate":16000,"language":"en"}
  Text frame:   {"type":"stop"}  — flush remaining buffer and finalize

Protocol (server → client):
  Text frame: {"type":"partial","text":"...","segment":0}
  Text frame: {"type":"final","text":"...","segment":1}
  Text frame: {"type":"error","message":"..."}
  Text frame: {"type":"ready","sample_rate":16000}

Env vars:
  LUMAX_STT_WS_BIND     — host (default 0.0.0.0)
  LUMAX_STT_WS_PORT     — port (default 8011)
  LUMAX_STT_MODEL      — whisper model size (default "base.en")
  LUMAX_STT_DEVICE     — "cuda" or "cpu" (default auto-detect)
  LUMAX_STT_COMPUTE    — compute type (default "float16" on CUDA, "int8" on CPU)
  LUMAX_STT_CHUNK_MS   — chunk duration in ms (default 1000)
"""

import asyncio
import json
import logging
import os
import sys
import time

import numpy as np
import websockets
from websockets.server import serve

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lumax.ws_stt")

# ── Config ──────────────────────────────────────────────────────────────
BIND_HOST = os.getenv("LUMAX_STT_WS_BIND", "0.0.0.0").strip()
BIND_PORT = int(os.getenv("LUMAX_STT_WS_PORT", "8011"))
MODEL_SIZE = os.getenv("LUMAX_STT_MODEL", "base.en").strip()
CHUNK_MS = int(os.getenv("LUMAX_STT_CHUNK_MS", "1000"))
TARGET_SR = 16000

# ── Whisper model (lazy-loaded) ─────────────────────────────────────────
_whisper_model = None
_whisper_lock = asyncio.Lock()
_load_error: str | None = None


def _detect_device() -> tuple[str, str]:
    """Return (device, compute_type) based on CUDA availability."""
    try:
        import torch

        if torch.cuda.is_available():
            return ("cuda", os.getenv("LUMAX_STT_COMPUTE", "float16"))
    except ImportError:
        pass
    return ("cpu", "int8")


def _load_whisper():
    """Load faster-whisper model. Called once at startup."""
    global _whisper_model, _load_error
    if _whisper_model is not None or _load_error is not None:
        return

    device, compute_type = _detect_device()
    log.info(
        "Loading faster-whisper '%s' on %s (%s)...", MODEL_SIZE, device, compute_type
    )
    try:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            MODEL_SIZE, device=device, compute_type=compute_type
        )
        log.info("Whisper model loaded on %s.", device.upper())
    except Exception as e:
        _load_error = f"whisper_load: {e!r}"
        log.error("Failed to load Whisper: %s", e)
        # Fallback to CPU int8
        try:
            from faster_whisper import WhisperModel

            _whisper_model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
            _load_error = None
            log.warning("Whisper loaded on CPU (fallback).")
        except Exception as e2:
            _load_error = f"whisper_load_cpu: {e2!r}"
            log.error("Whisper CPU fallback also failed: %s", e2)


async def _transcribe(audio_np: np.ndarray, language: str = "en") -> str:
    """Run Whisper transcription on a float32 numpy array. Thread-safe via lock."""
    if _whisper_model is None:
        return ""

    def _do_transcribe():
        segments, _info = _whisper_model.transcribe(
            audio_np,
            language=language,
            beam_size=1,
            vad_filter=True,
            without_timestamps=True,
        )
        return " ".join(seg.text.strip() for seg in segments)

    async with _whisper_lock:
        return await asyncio.to_thread(_do_transcribe)


# ── Per-connection session ──────────────────────────────────────────────
class STTSession:
    """Manages one WebSocket client's audio buffer and transcription loop."""

    def __init__(self, ws):
        self.ws = ws
        self.pcm_buffer = bytearray()
        self.sample_rate = TARGET_SR
        self.language = "en"
        self.segment_idx = 0
        self.is_streaming = True
        self._flush_task: asyncio.Task | None = None

    def _chunk_samples(self) -> int:
        """Number of samples per transcription chunk."""
        return int(self.sample_rate * CHUNK_MS / 1000)

    def _bytes_per_sample(self) -> int:
        return 2  # int16 LE

    async def add_audio(self, data: bytes):
        """Append PCM bytes and trigger transcription when enough data accumulates."""
        self.pcm_buffer.extend(data)
        threshold = self._chunk_samples() * self._bytes_per_sample()
        while len(self.pcm_buffer) >= threshold:
            chunk = self.pcm_buffer[:threshold]
            del self.pcm_buffer[:threshold]
            await self._transcribe_chunk(chunk)

    async def _transcribe_chunk(self, chunk_bytes: bytes):
        """Convert int16 PCM to float32 and run Whisper."""
        if len(chunk_bytes) < self._bytes_per_sample():
            return

        audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
        audio_f32 = audio_int16.astype(np.float32) / 32768.0

        text = await _transcribe(audio_f32, language=self.language)
        self.segment_idx += 1

        msg = json.dumps(
            {
                "type": "partial",
                "text": text,
                "segment": self.segment_idx,
                "ts": time.time(),
            }
        )
        try:
            await self.ws.send(msg)
        except Exception as e:
            log.warning("Failed to send partial transcript: %s", e)

    async def flush(self):
        """Transcribe any remaining buffered audio."""
        if len(self.pcm_buffer) >= self._bytes_per_sample():
            # Pad to even
            if len(self.pcm_buffer) % 2 != 0:
                self.pcm_buffer.append(0)
            audio_int16 = np.frombuffer(bytes(self.pcm_buffer), dtype=np.int16)
            audio_f32 = audio_int16.astype(np.float32) / 32768.0
            self.pcm_buffer.clear()

            if len(audio_f32) > 0:
                text = await _transcribe(audio_f32, language=self.language)
                self.segment_idx += 1
                msg = json.dumps(
                    {
                        "type": "final",
                        "text": text,
                        "segment": self.segment_idx,
                        "ts": time.time(),
                    }
                )
                try:
                    await self.ws.send(msg)
                except Exception as e:
                    log.warning("Failed to send final transcript: %s", e)


# ── WebSocket handler ───────────────────────────────────────────────────
async def handle_stt_client(ws):
    """Per-connection WebSocket handler."""
    peer = ws.remote_address if ws.remote_address else "unknown"
    log.info("STT client connected: %s", peer)

    if _load_error is not None:
        await ws.send(json.dumps({"type": "error", "message": _load_error}))
        await ws.close()
        return

    session = STTSession(ws)
    await ws.send(
        json.dumps(
            {
                "type": "ready",
                "sample_rate": TARGET_SR,
                "model": MODEL_SIZE,
            }
        )
    )

    try:
        async for message in ws:
            if isinstance(message, bytes):
                # Binary frame = raw PCM audio
                await session.add_audio(message)
            else:
                # Text frame = control message
                try:
                    cmd = json.loads(message)
                except json.JSONDecodeError:
                    await ws.send(
                        json.dumps({"type": "error", "message": "invalid JSON"})
                    )
                    continue

                msg_type = cmd.get("type", "")
                if msg_type == "config":
                    sr = cmd.get("sample_rate", TARGET_SR)
                    if sr != TARGET_SR:
                        log.warning(
                            "Client sample_rate=%d, resampling not implemented; using %d",
                            sr,
                            TARGET_SR,
                        )
                    session.language = cmd.get("language", "en")
                    log.info(
                        "Config: language=%s, sample_rate=%d", session.language, sr
                    )
                elif msg_type == "stop":
                    await session.flush()
                    await ws.send(
                        json.dumps({"type": "stopped", "segment": session.segment_idx})
                    )
                else:
                    await ws.send(
                        json.dumps(
                            {"type": "error", "message": f"unknown type: {msg_type}"}
                        )
                    )

    except websockets.exceptions.ConnectionClosed:
        log.info("STT client disconnected: %s", peer)
    except Exception as e:
        log.error("STT handler error: %s", e)
    finally:
        # Final flush
        try:
            await session.flush()
        except Exception:
            pass
        log.info("STT session ended: %s (segments=%d)", peer, session.segment_idx)


# ── HTTP health endpoint (simple) ───────────────────────────────────────
async def health_handler(path, request_headers):
    """Minimal HTTP health response for non-WebSocket requests."""
    if path == "/health":
        body = json.dumps(
            {
                "status": "ok" if _whisper_model is not None else "loading",
                "model": MODEL_SIZE,
                "error": _load_error,
                "port": BIND_PORT,
            }
        ).encode()
        return (200, [("Content-Type", "application/json")], body)
    return None


# ── Main ────────────────────────────────────────────────────────────────
async def main():
    log.info(
        "Starting LUMAX Quest 3 STT WebSocket Bridge on %s:%d", BIND_HOST, BIND_PORT
    )
    _load_whisper()

    async with serve(
        handle_stt_client,
        BIND_HOST,
        BIND_PORT,
        process_request=health_handler,
        max_size=2**20,  # 1 MiB max message
        ping_interval=20,
        ping_timeout=10,
    ):
        log.info("STT WS server listening on ws://%s:%d", BIND_HOST, BIND_PORT)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down STT WS bridge.")
        sys.exit(0)
