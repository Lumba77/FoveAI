"""
FoveAI Quest 3 TTS Server — WebSocket Audio Streaming
Port 8012

Receives text requests from Quest 3 via WebSocket, synthesizes speech,
streams PCM audio chunks (22kHz, 16-bit) back for live AudioSource playback.

Usage:
    python tts_stream_server.py

Requirements:
    pip install websockets edge-tts numpy

Optional (for local Piper TTS instead of edge-tts):
    pip install piper-tts
"""

import asyncio
import io
import json
import logging
from collections.abc import AsyncGenerator

import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [TTS] %(message)s")
logger = logging.getLogger("tts_server")

HOST = "0.0.0.0"
PORT = 8403  # Unity Quest3TTSClient connects to ws://<ip>:8403/ws
SAMPLE_RATE = 24000  # Quest3TTSClient.ServerSampleRate = 24000
SAMPLE_WIDTH = 2  # 16-bit PCM
CHANNELS = 1  # Mono
CHUNK_DURATION_MS = 100  # 100ms chunks for low-latency streaming
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)
CHUNK_BYTES = CHUNK_SAMPLES * SAMPLE_WIDTH * CHANNELS

# TTS engine: "edge" or "piper"
TTS_ENGINE = "edge"
DEFAULT_VOICE = "en-US-AriaNeural"
DEFAULT_RATE = "+0%"
DEFAULT_VOLUME = "+0%"


class TTSServer:
    """TTS synthesis and streaming server."""

    def __init__(self):
        self._edge_tts = None
        self._piper = None
        self._init_engine()

    def _init_engine(self):
        """Initialize the TTS engine."""
        if TTS_ENGINE == "edge":
            try:
                import edge_tts

                self._edge_tts = edge_tts
                logger.info(f"TTS engine: edge-tts (voice={DEFAULT_VOICE})")
            except ImportError:
                logger.warning(
                    "edge-tts not installed — install with: pip install edge-tts"
                )
        elif TTS_ENGINE == "piper":
            try:
                # Path to Piper voice model (.onnx)
                import os

                from piper import PiperVoice

                model_path = os.environ.get("PIPER_MODEL_PATH", "")
                if model_path and os.path.exists(model_path):
                    self._piper = PiperVoice.load(model_path)
                    logger.info(f"TTS engine: piper (model={model_path})")
                else:
                    logger.warning(
                        "Piper model path not set — set PIPER_MODEL_PATH env var"
                    )
            except ImportError:
                logger.warning(
                    "piper-tts not installed — install with: pip install piper-tts"
                )

    async def synthesize_edge(
        self, text: str, voice: str, rate: str, volume: str
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize with edge-tts and yield PCM chunks."""
        if self._edge_tts is None:
            yield self._silence_chunk()
            return

        communicate = self._edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        audio_buffer = bytearray()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])

                # Yield when we have enough for a chunk
                while len(audio_buffer) >= CHUNK_BYTES:
                    yield bytes(audio_buffer[:CHUNK_BYTES])
                    del audio_buffer[:CHUNK_BYTES]

        # Yield remaining audio
        if len(audio_buffer) > 0:
            # Pad to chunk size
            if len(audio_buffer) < CHUNK_BYTES:
                audio_buffer.extend(b"\x00" * (CHUNK_BYTES - len(audio_buffer)))
            yield bytes(audio_buffer[:CHUNK_BYTES])

    async def synthesize_piper(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize with Piper TTS and yield PCM chunks."""
        if self._piper is None:
            yield self._silence_chunk()
            return

        # Piper outputs 16-bit PCM at its configured sample rate
        # We need to resample to SAMPLE_RATE
        import wave

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            self._piper.synthesize(text, wav_file)

        wav_buffer.seek(0)
        # Skip WAV header (44 bytes)
        wav_buffer.read(44)
        audio_data = wav_buffer.read()

        for i in range(0, len(audio_data), CHUNK_BYTES):
            chunk = audio_data[i : i + CHUNK_BYTES]
            if len(chunk) < CHUNK_BYTES:
                chunk = chunk + b"\x00" * (CHUNK_BYTES - len(chunk))
            yield chunk

    @staticmethod
    def _silence_chunk() -> bytes:
        """Return a chunk of silence."""
        return b"\x00" * CHUNK_BYTES

    async def synthesize(
        self, text: str, voice: str = None, rate: str = None, volume: str = None
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize text and yield PCM audio chunks."""
        voice = voice or DEFAULT_VOICE
        rate = rate or DEFAULT_RATE
        volume = volume or DEFAULT_VOLUME

        logger.info(f'Synthesizing: "{text[:60]}" (voice={voice})')

        if TTS_ENGINE == "edge":
            async for chunk in self.synthesize_edge(text, voice, rate, volume):
                yield chunk
        elif TTS_ENGINE == "piper":
            async for chunk in self.synthesize_piper(text):
                yield chunk
        else:
            yield self._silence_chunk()


# Global TTS instance
tts = TTSServer()


async def handle_client(websocket, path=None):
    """Handle a single Quest 3 TTS client connection."""
    # Path guard - accept / and /ws
    ws_path = getattr(websocket, "path", path or "/")
    if ws_path not in ("/", "/ws"):
        logger.warning(f"Rejected connection to unknown path: {ws_path}")
        await websocket.close(1008, "Unknown path")
        return

    client_addr = (
        websocket.remote_address if hasattr(websocket, "remote_address") else "unknown"
    )
    logger.info(f"Client connected: {client_addr} (path={ws_path})")

    # Send connected handshake so the client knows we are ready
    await websocket.send(
        json.dumps(
            {
                "type": "connected",
                "sample_rate": SAMPLE_RATE,
                "engine": TTS_ENGINE,
                "message": "TTS server ready",
            }
        )
    )
    logger.info("Sent connected handshake")

    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    req = json.loads(message)
                except json.JSONDecodeError:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "invalid JSON"})
                    )
                    continue

                if req.get("type") == "speak":
                    text = req.get("text", "").strip()
                    if not text:
                        await websocket.send(
                            json.dumps({"type": "error", "message": "empty text"})
                        )
                        continue

                    voice = req.get("voice")
                    rate = req.get("rate")
                    volume = req.get("volume")

                    # Send start signal
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "start",
                                "sampleRate": SAMPLE_RATE,
                                "channels": CHANNELS,
                                "bitsPerSample": SAMPLE_WIDTH * 8,
                            }
                        )
                    )

                    # Stream audio chunks
                    chunk_index = 0
                    async for chunk in tts.synthesize(text, voice, rate, volume):
                        await websocket.send(chunk)
                        chunk_index += 1

                    # Send end signal
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "end",
                                "chunks": chunk_index,
                                "duration": round(
                                    chunk_index * CHUNK_DURATION_MS / 1000, 2
                                ),
                            }
                        )
                    )
                    logger.info(
                        f"Streamed {chunk_index} chunks ({chunk_index * CHUNK_DURATION_MS}ms)"
                    )

                elif req.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))

                elif req.get("type") == "voices":
                    # List available edge-tts voices
                    if tts._edge_tts:
                        voices = await tts._edge_tts.list_voices()
                        voice_list = [
                            {
                                "name": v["ShortName"],
                                "gender": v["Gender"],
                                "locale": v["Locale"],
                            }
                            for v in voices
                        ]
                        await websocket.send(
                            json.dumps({"type": "voices", "voices": voice_list})
                        )
                    else:
                        await websocket.send(
                            json.dumps({"type": "voices", "voices": []})
                        )

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client disconnected: {client_addr}")


async def main():
    logger.info(f"Starting TTS WebSocket server on {HOST}:{PORT} (path=/ws)")
    logger.info(f"  Engine: {TTS_ENGINE}")
    logger.info(f"  Output: {SAMPLE_RATE}Hz, {SAMPLE_WIDTH * 8}-bit, {CHANNELS}ch")
    logger.info(f"  Chunk: {CHUNK_DURATION_MS}ms ({CHUNK_SAMPLES} samples)")
    async with websockets.serve(handle_client, HOST, PORT, max_size=2**20):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
