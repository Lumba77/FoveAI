"""
FoveAI Quest 3 STT Server — WebSocket Whisper Bridge
Port 8011

Receives 16kHz 16-bit PCM audio chunks from Quest 3 via WebSocket,
runs faster-whisper transcription on RTX 4060 GPU, returns JSON results.

Usage:
    python stt_whisper_server.py

Requirements:
    pip install faster-whisper websockets numpy
"""

import asyncio
import json
import logging
import time
from typing import Optional

import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [STT] %(message)s")
logger = logging.getLogger("stt_server")

import os

HOST = os.getenv("STT_HOST", "0.0.0.0")
PORT = int(os.getenv("STT_PORT", "8401"))
HTTP_PORT = int(os.getenv("STT_HTTP_PORT", "8430"))  # POST /stt for browsers (webm→whisper)
SAMPLE_RATE = 16000
WHISPER_MODEL = os.getenv(
    "STT_MODEL",
    "Systran/faster-whisper-small.en",   # repo id — resolved from HF cache
)
DEVICE = os.getenv("STT_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "int8" if DEVICE == "cpu" else "float16")
LANGUAGE = "en"

# Minimum chunk duration before attempting transcription (seconds)
MIN_CHUNK_DURATION = 0.5
# Silence threshold (RMS amplitude) to auto-stop recording
# Room noise floor here measures ~0.045 RMS; 0.01 would hold the VAD open
# forever. Override per-environment via STT_SILENCE_THRESHOLD.
SILENCE_THRESHOLD = float(os.getenv("STT_SILENCE_THRESHOLD", "0.08"))
SILENCE_DURATION = 1.5  # seconds of silence before auto-finalize


class WhisperSTTServer:
    def __init__(self):
        self.model: WhisperModel | None = None
        self._load_model()

    def _load_model(self):
        if WhisperModel is None:
            logger.warning("faster-whisper not installed — running in passthrough mode")
            return
        logger.info(f"Loading Whisper {WHISPER_MODEL} on {DEVICE} ({COMPUTE_TYPE})...")
        self.model = WhisperModel(
            WHISPER_MODEL,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
        logger.info("Whisper model loaded successfully")

    def transcribe(self, audio_np: np.ndarray) -> dict:
        """Transcribe audio numpy array and return result dict."""
        if self.model is None:
            return {"text": "[whisper not available]", "language": "en", "segments": []}

        try:
            segments, info = self.model.transcribe(
                audio_np,
                language=LANGUAGE,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )
            segment_list = []
            full_text = ""
            for seg in segments:
                segment_list.append(
                    {
                        "start": round(seg.start, 3),
                        "end": round(seg.end, 3),
                        "text": seg.text.strip(),
                    }
                )
                full_text += seg.text

            return {
                "text": full_text.strip(),
                "language": info.language,
                "language_probability": round(info.language_probability, 3),
                "duration": round(info.duration, 3),
                "segments": segment_list,
            }
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {"text": "", "error": str(e), "segments": []}

    @staticmethod
    def pcm_to_numpy(pcm_bytes: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to float32 numpy array [-1.0, 1.0]."""
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        return samples.astype(np.float32) / 32768.0

    @staticmethod
    def compute_rms(audio: np.ndarray) -> float:
        """Compute RMS amplitude for VAD."""
        if len(audio) == 0:
            return 0.0
        return float(np.sqrt(np.mean(audio**2)))


# One shared Whisper model — was loaded per-connection (30s stall on every
# client). Preload at startup so the first connect is instant.
_STT_INSTANCE: Optional["WhisperSTTServer"] = None


def _get_stt() -> "WhisperSTTServer":
    global _STT_INSTANCE
    if _STT_INSTANCE is None:
        _STT_INSTANCE = WhisperSTTServer()
    return _STT_INSTANCE


async def handle_client(websocket, path=None):
    """Handle a single Quest 3 STT client connection."""
    # Reject connections that are NOT to /ws path
    ws_path = getattr(websocket, "path", path or "/")
    if ws_path not in ("/", "/ws"):
        logger.warning(f"Rejected connection to unknown path: {ws_path}")
        await websocket.close(1008, "Unknown path")
        return

    client_addr = (
        websocket.remote_address if hasattr(websocket, "remote_address") else "unknown"
    )
    logger.info(f"Client connected: {client_addr} (path={ws_path})")

    # Send 'ready' handshake immediately — Unity client waits for this before starting mic
    await websocket.send(
        json.dumps(
            {"type": "ready", "sample_rate": SAMPLE_RATE, "message": "STT server ready"}
        )
    )
    logger.info("Sent ready handshake")

    stt = _get_stt()  # shared model — loaded once, not per connection
    audio_buffer = bytearray()
    silence_start: float | None = None
    is_recording = False

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Binary PCM audio chunk
                audio_buffer.extend(message)
                chunk_audio = stt.pcm_to_numpy(message)
                rms = stt.compute_rms(chunk_audio)

                if rms > SILENCE_THRESHOLD:
                    silence_start = None
                    if not is_recording:
                        is_recording = True
                        await websocket.send(json.dumps({"type": "speech_start"}))
                elif is_recording and silence_start is None:
                    silence_start = time.time()
                elif not is_recording:
                    pre_roll_bytes = int(SAMPLE_RATE * 2 * 0.3)
                    if len(audio_buffer) > pre_roll_bytes:
                        del audio_buffer[:-pre_roll_bytes]

                # Auto-finalize after silence
                if silence_start and (time.time() - silence_start) > SILENCE_DURATION:
                    await websocket.send(json.dumps({"type": "speech_end"}))
                    if len(audio_buffer) > SAMPLE_RATE * 2 * MIN_CHUNK_DURATION:
                        full_audio = stt.pcm_to_numpy(bytes(audio_buffer))
                        result = stt.transcribe(full_audio)
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "final",
                                    **result,
                                }
                            )
                        )
                        logger.info(f"Final: {result.get('text', '')[:80]}")
                    audio_buffer.clear()
                    silence_start = None
                    is_recording = False

            elif isinstance(message, str):
                # JSON control message
                try:
                    cmd = json.loads(message)
                except json.JSONDecodeError:
                    continue

                if cmd.get("type") == "start":
                    audio_buffer.clear()
                    silence_start = None
                    is_recording = True
                    await websocket.send(
                        json.dumps({"type": "ack", "status": "recording"})
                    )
                    logger.info("Recording started")

                elif cmd.get("type") == "stop":
                    if len(audio_buffer) > 0:
                        full_audio = stt.pcm_to_numpy(bytes(audio_buffer))
                        result = stt.transcribe(full_audio)
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "final",
                                    **result,
                                }
                            )
                        )
                        logger.info(f"Final: {result.get('text', '')[:80]}")
                    audio_buffer.clear()
                    is_recording = False
                    await websocket.send(
                        json.dumps({"type": "ack", "status": "stopped"})
                    )

                elif cmd.get("type") == "reset":
                    audio_buffer.clear()
                    silence_start = None
                    is_recording = False
                    await websocket.send(json.dumps({"type": "ack", "status": "reset"}))

                elif cmd.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client disconnected: {client_addr}")
    finally:
        audio_buffer.clear()


async def handle_http(reader, writer):
    """Minimal HTTP: POST /stt {audio_base64, format} → {text}.
    Browser MediaRecorder produces webm/opus; ffmpeg decodes to 16k PCM
    and the same whisper pipeline as the WS path runs. (2026-10-08: the
    frontend posted /api/soul/stt — the route never existed; 'listening'
    ate words. Now the browser path is real.)"""
    import base64 as _b64, subprocess as _sp, tempfile as _tf, os as _os, json as _json
    try:
        raw = await asyncio.wait_for(reader.read(64 * 1024 * 1024), timeout=60)
        head, _, body = raw.partition(b"\r\n\r\n")
        # keep reading if content-length says more (simple robustness for big chunks)
        cl = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                cl = int(line.split(b":")[1].strip())
        while len(body) < cl:
            body += await asyncio.wait_for(reader.read(64 * 1024 * 1024), timeout=30)
        if b"POST /stt" not in head.split(b"\r\n")[0]:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain(); writer.close(); return
        payload = _json.loads(body or b"{}")
        audio = _b64.b64decode(payload.get("audio_base64", "") or "")
        # PyAV decode (ffmpeg binary absent on this host): webm/opus → 16k mono float32
        import io as _io
        import av as _av
        container = _av.open(_io.BytesIO(audio))
        frames = []
        resampler = _av.AudioResampler(format='s16', layout='mono', rate=16000)
        for frame in container.decode(audio=0):
            for rf in resampler.resample(frame):
                frames.append(rf.to_ndarray().tobytes())
        pcm = b"".join(frames)
        np_pcm = WhisperSTTServer.pcm_to_numpy(pcm)
        result = _get_stt().transcribe(np_pcm)
        out = _json.dumps(result).encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                     b"Access-Control-Allow-Origin: *\r\nContent-Length: "
                     + str(len(out)).encode() + b"\r\n\r\n" + out)
        await writer.drain()
    except Exception as e:
        logger.error(f"HTTP STT error: {e}")
        try:
            writer.write(b'HTTP/1.1 500\r\nContent-Type: application/json\r\n\r\n{"text":"","error":"stt failed"}')
            await writer.drain()
        except Exception:
            pass
    finally:
        try: writer.close()
        except Exception: pass


async def main():
    logger.info(f"Starting STT WebSocket server on {HOST}:{PORT} (path=/ws, POST /stt)")
    _get_stt()  # warm the model before the port opens
    # HTTP bridge shares the port via a starter protocol split: HTTP on same
    # socket is complex — use a dedicated port + vite proxy instead.
    http_srv = await asyncio.start_server(handle_http, HOST, HTTP_PORT)
    async with websockets.serve(handle_client, HOST, PORT, max_size=2**20), http_srv:
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
