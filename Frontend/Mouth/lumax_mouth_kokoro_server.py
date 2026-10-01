#!/usr/bin/env python3
"""
HTTP bridge for Kokoro TTS — primary MOUTH service for LUMAX (port 8004).

Kokoro provides high-quality, emotionally expressive TTS with minimal VRAM
footprint, making it ideal for the 8GB RTX 4060 constraint.

POST /tts returns audio/wav (24 kHz). Also exposes /synthesize as alias
and /health for diagnostics.

Voice selection: explicit `voice` param > emotion-mapped > LUMAX_KOKORO_VOICE env > "af_bella".

Env vars:
  LUMAX_KOKORO_BIND         — host (default 0.0.0.0)
  LUMAX_KOKORO_PORT         — port (default 8004)
  LUMAX_KOKORO_LANG_CODE    — language code (default "a" = American English)
  LUMAX_KOKORO_VOICE        — default voice when no emotion mapping (default "af_bella")
  LUMAX_KOKORO_SPEED         — default speed multiplier (default 1.0)
  LOG_LEVEL                  — logging verbosity
"""

from __future__ import annotations

import io
import logging
import os

# Fix OpenBLAS memory allocation crashes by restricting threads
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
# Allow Kokoro to download the voice models from Hugging Face if missing
os.environ.pop("HF_HUB_OFFLINE", None)

import json as _json
import re
import threading
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

_log = logging.getLogger("lumax.kokoro")
_pipeline: Any = None
_load_error: str | None = None
_model_lock = threading.Lock()
_sample_rate: int = 24000


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _load_model_sync() -> None:
    global _pipeline, _load_error, _sample_rate
    try:
        from kokoro import KPipeline
    except Exception as e:
        _load_error = f"import_kokoro:{e!r}"
        _log.error("Failed to import kokoro: %s", e)
        return

    lang = os.getenv("LUMAX_KOKORO_LANG_CODE", "a").strip()
    try:
        # Kokoro 0.9.x: KPipeline accepts lang_code and optionally repo_id/model
        import torch

        # User confirmed LLM is in the cloud, leaving 8GB VRAM free for STT and TTS
        device = os.getenv(
            "LUMAX_KOKORO_DEVICE", "cuda" if torch.cuda.is_available() else "cpu"
        ).strip()
        kwargs: dict[str, Any] = {"lang_code": lang, "device": device}
        repo_id = os.getenv("LUMAX_KOKORO_REPO_ID", "").strip()
        if repo_id:
            kwargs["repo_id"] = repo_id
        _pipeline = KPipeline(**kwargs)
        _sample_rate = int(getattr(_pipeline, "sample_rate", 24000))
        _load_error = None
        _log.info(
            "Kokoro pipeline created (lang_code=%s, sample_rate=%d)",
            lang,
            _sample_rate,
        )
    except Exception as e:
        _load_error = f"kokoro_init:{e!r}"
        _pipeline = None
        _log.error("Failed to initialise Kokoro pipeline: %s", e)
        return

    # Warm-up: trigger lazy model download + first inference so /health is honest
    try:
        _log.info("Kokoro: warming up model (first inference may download weights)...")
        warm_voice = os.getenv("LUMAX_KOKORO_VOICE", "af_bella").strip()
        chunks = 0
        for result in _pipeline("OK", voice=warm_voice, speed=1.0):
            # Validate audio extraction works (KResult vs tuple)
            if hasattr(result, "audio"):
                _ = result.audio
            elif isinstance(result, (tuple, list)) and len(result) >= 3:
                _ = result[2]
            chunks += 1
        _log.info(
            "Kokoro: warm-up complete (%d chunk(s), voice=%s, sample_rate=%d)",
            chunks,
            warm_voice,
            _sample_rate,
        )
    except Exception as e:
        _load_error = f"kokoro_warmup:{e!r}"
        _pipeline = None
        _log.error("Kokoro warm-up failed (model may not have downloaded): %s", e)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _load_model_sync()
    yield


class TTSBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=8192)
    voice: str | None = None
    style: str | None = None
    emotion: str | None = None
    speed: float = Field(default=1.08, ge=0.25, le=4.0)
    lang_code: str | None = None


app = FastAPI(title="Lumax Kokoro TTS (MOUTH :8004)", lifespan=_lifespan)


@app.get("/health", response_model=None)
def health():
    ok = _pipeline is not None and _load_error is None
    body: dict[str, Any] = {
        "ok": ok,
        "model_loaded": ok,
        "error": _load_error,
        "engine": "kokoro",
        "sample_rate": _sample_rate if ok else None,
    }
    if not ok:
        return JSONResponse(body, status_code=503)
    return body


# Emotion → Kokoro voice mapping for Jen's persona
_EMOTION_VOICE_MAP: dict[str, str] = {
    "happy": "af_bella",
    "excited": "af_bella",
    "sad": "af_bella",
    "angry": "af_bella",
    "surprised": "af_bella",
    "neutral": "af_bella",
    "content": "af_bella",
    "fearful": "af_bella",
    "calm": "af_bella",
    "curious": "af_bella",
    "concerned": "af_bella",
}

# Strip bracket tokens (e.g. <audio:gasp_subtle>) and thought/action tags (*...*)
# These are handled by the frontend UI, not the speech engine.
_STRIP_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_STRIP_BRACKETS = re.compile(r"<[^>]+>")
_STRIP_THOUGHTS = re.compile(r"\*[^*]+\*")


@app.post("/tts")
def tts(body: TTSBody) -> Response:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail=_load_error or "model_not_loaded")

    # Strip think blocks, bracket tokens, thought actions, and normalise whitespace
    text = _STRIP_THINK_BLOCK.sub("", body.text.strip())
    text = _STRIP_BRACKETS.sub("", text)
    text = _STRIP_THOUGHTS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty_text_after_strip")

    # Resolve voice: explicit > emotion-mapped > env default > hardcoded default
    _VOICE_ALIASES = {
        "female": "af_bella",
        "male": "am_adam",
        "default": "af_bella",
        "jen": "af_bella",
        "en-us": "af_bella",
    }
    voice = body.voice
    if voice and voice.lower() in _VOICE_ALIASES:
        voice = _VOICE_ALIASES[voice.lower()]

    if not voice:
        emotion = (body.emotion or body.style or "").strip().lower()
        voice = _EMOTION_VOICE_MAP.get(emotion)
    if not voice:
        voice = os.getenv("LUMAX_KOKORO_VOICE", "af_bella").strip()

    speed = body.speed or _env_float("LUMAX_KOKORO_SPEED", 1.08)

    with _model_lock:
        try:
            audio_chunks: list[np.ndarray] = []
            for result in _pipeline(text, voice=voice, speed=speed):
                # Kokoro 0.9.x yields KResult(graphemes, phonemes, audio)
                if hasattr(result, "audio"):
                    audio = result.audio
                elif isinstance(result, (tuple, list)) and len(result) >= 3:
                    audio = result[2]
                else:
                    audio = result
                if hasattr(audio, "detach"):
                    # Torch tensor → numpy
                    audio = audio.detach().cpu().float().numpy()
                if audio is not None and len(audio) > 0:
                    audio_chunks.append(np.asarray(audio, dtype=np.float32))
        except Exception as e:
            _log.error("Kokoro inference failed: %s", e)
            raise HTTPException(status_code=500, detail=f"kokoro_inference:{e!r}")

    if not audio_chunks:
        raise HTTPException(status_code=500, detail="kokoro_produced_no_audio")

    # Concatenate chunks for long text
    full_audio = (
        np.concatenate(audio_chunks) if len(audio_chunks) > 1 else audio_chunks[0]
    )
    if full_audio.ndim > 1:
        if full_audio.shape[-1] <= 8:
            full_audio = np.mean(full_audio, axis=-1)
        else:
            full_audio = full_audio.reshape(-1)

    buf = io.BytesIO()
    sf.write(buf, full_audio, _sample_rate, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.get("/voices")
def voices():
    """List configured emotion→voice mappings and default voice."""
    default_voice = os.getenv("LUMAX_KOKORO_VOICE", "af_bella").strip()
    return {
        "default": default_voice,
        "emotion_map": _EMOTION_VOICE_MAP,
        "lang_code": os.getenv("LUMAX_KOKORO_LANG_CODE", "a").strip(),
        "sample_rate": _sample_rate if _pipeline else None,
    }


# Alias for compatibility with other mouth server conventions
@app.post("/synthesize")
def synthesize(body: TTSBody) -> Response:
    return tts(body)


@app.websocket("/ws")
async def tts_websocket(ws: WebSocket):
    """WebSocket TTS endpoint for Quest 3 streaming audio.

    Protocol:
      Client sends {"type":"config","sample_rate":24000} → Server replies {"type":"ready"}
      Client sends {"type":"speak","text":"...","voice":"af_bella","speed":1.0}
        → Server sends {"type":"start","sample_rate":24000}
        → Server streams binary PCM chunks (16-bit mono)
        → Server sends {"type":"end","duration_ms":...}
      Client sends {"type":"stop"} → Server stops current utterance
    """
    await ws.accept()
    _log.info("[TTS-WS] Quest client connected: %s", ws.client)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = _json.loads(raw)
            except _json.JSONDecodeError:
                await ws.send_text(
                    _json.dumps({"type": "error", "message": "invalid json"})
                )
                continue

            mtype = msg.get("type", "")

            if mtype == "config":
                await ws.send_text(
                    _json.dumps({"type": "ready", "sample_rate": _sample_rate})
                )
                _log.info("[TTS-WS] Config received, sent ready")

            elif mtype == "speak":
                text = msg.get("text", "")
                voice = msg.get("voice", "af_bella")
                speed = float(msg.get("speed", 1.0))
                if not text:
                    continue

                # Strip artifacts same as HTTP endpoint
                text = _STRIP_THINK_BLOCK.sub("", text.strip())
                text = _STRIP_BRACKETS.sub("", text)
                text = _STRIP_THOUGHTS.sub("", text)
                text = re.sub(r"\s+", " ", text).strip()
                if not text:
                    continue

                # Resolve voice aliases
                _VOICE_ALIASES = {
                    "female": "af_bella",
                    "male": "am_adam",
                    "default": "af_bella",
                    "jen": "af_bella",
                    "en-us": "af_bella",
                }
                if voice and voice.lower() in _VOICE_ALIASES:
                    voice = _VOICE_ALIASES[voice.lower()]
                if not voice:
                    voice = os.getenv("LUMAX_KOKORO_VOICE", "af_bella").strip()

                await ws.send_text(
                    _json.dumps({"type": "start", "sample_rate": _sample_rate})
                )

                try:
                    with _model_lock:
                        for result in _pipeline(text, voice=voice, speed=speed):
                            if hasattr(result, "audio"):
                                audio = result.audio
                            elif isinstance(result, (tuple, list)) and len(result) >= 3:
                                audio = result[2]
                            else:
                                audio = result
                            if hasattr(audio, "detach"):
                                audio = audio.detach().cpu().float().numpy()
                            if audio is None or len(audio) == 0:
                                continue
                            audio = np.asarray(audio, dtype=np.float32)
                            if audio.ndim > 1:
                                audio = (
                                    np.mean(audio, axis=-1)
                                    if audio.shape[-1] <= 8
                                    else audio.reshape(-1)
                                )
                            # Convert to 16-bit PCM bytes
                            pcm = (
                                (audio * 32767)
                                .clip(-32768, 32767)
                                .astype(np.int16)
                                .tobytes()
                            )
                            # Stream in chunks for low latency
                            chunk_size = (
                                int(_sample_rate * 0.1) * 2
                            )  # 100ms chunks (2 bytes/sample)
                            for i in range(0, len(pcm), chunk_size):
                                await ws.send_bytes(pcm[i : i + chunk_size])
                except Exception as e:
                    _log.error("[TTS-WS] Synthesis error: %s", e)
                    await ws.send_text(
                        _json.dumps({"type": "error", "message": str(e)})
                    )

                duration_ms = int(
                    len(text) / max(speed, 0.1) * 1000 * 0.07
                )  # rough estimate
                await ws.send_text(
                    _json.dumps({"type": "end", "duration_ms": duration_ms})
                )

            elif mtype == "stop":
                _log.info("[TTS-WS] Stop received")

            else:
                await ws.send_text(
                    _json.dumps({"type": "error", "message": f"unknown type: {mtype}"})
                )

    except WebSocketDisconnect:
        _log.info("[TTS-WS] Quest client disconnected")
    except Exception as e:
        _log.error("[TTS-WS] Error: %s", e)


def main() -> None:
    raw_level = os.getenv("LOG_LEVEL", "INFO").strip()
    py_level = "WARNING" if raw_level.upper() == "WARN" else raw_level.upper()
    uvi_level = "warning" if raw_level.lower() == "warn" else raw_level.lower()

    logging.basicConfig(
        level=py_level,
        format="%(levelname)s %(name)s %(message)s",
    )
    host = os.getenv("LUMAX_KOKORO_BIND", "0.0.0.0").strip()
    port = _env_int("LUMAX_KOKORO_PORT", 8004)
    _log.info("Starting Kokoro TTS on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level=uvi_level)


if __name__ == "__main__":
    main()
