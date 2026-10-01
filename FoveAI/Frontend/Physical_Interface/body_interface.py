import base64
import logging
import os
import tempfile
import threading
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BodyInterface")

app = FastAPI(title="Lumax Body Interface")

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment State
MODE = os.getenv("MODE", "EARS")  # Default to EARS if not set
logger.info("BodyInterface process MODE=%s (EARS=STT/whisper, MOUTH=TTS/forward)", MODE)

# Docker DNS names (same compose network). Do not hardcode 172.x — subnet changes per bridge.
# Optional full XTTS on 8020: set CHATTERBOX_URL if you add a separate XTTS service (not in default compose).
TURBO_URL = os.getenv("TURBO_URL", "http://foveai_turbochat:8005").rstrip("/")
CHATTERBOX_URL = os.getenv("CHATTERBOX_URL", "").rstrip("/")
# Turbo ONNX / first GPU inference often exceeds 15s; short read timeout looked like "unreachable" in logs.
_TURBO_CONNECT_TIMEOUT = float(os.getenv("TURBO_HTTP_CONNECT_TIMEOUT", "10"))
_TURBO_READ_TIMEOUT = float(os.getenv("TURBO_HTTP_READ_TIMEOUT", "180"))


def _turbo_client_timeout() -> httpx.Timeout:
    # httpx 0.28+: Timeout needs a default for all phases or all four set explicitly.
    # Long read for first GPU inference; connect stays short so dead hosts fail fast.
    return httpx.Timeout(_TURBO_READ_TIMEOUT, connect=_TURBO_CONNECT_TIMEOUT)


# Extra fallbacks, e.g. host.docker.internal or a LAN IP — comma-separated base URLs without /tts
def _extra_tts_bases(env_name: str) -> list[str]:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return []
    return [u.rstrip("/") for u in raw.split(",") if u.strip()]


# --- Whisper Model Initialization (Only in EARS mode to save VRAM) ---
whisper_model = None
if MODE == "EARS":
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    logger.info(f"Initializing Faster-Whisper Model on {device.upper()} (base.en)...")
    try:
        from faster_whisper import WhisperModel

        whisper_model = WhisperModel(
            "base.en", device=device, compute_type=compute_type
        )
        logger.info(f"Faster-Whisper Model Ready ({device.upper()}).")
    except Exception as e:
        logger.error(f"Failed to load Faster-Whisper: {e}")
        try:
            whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
            logger.info("Faster-Whisper Fallback to CPU Ready.")
        except:
            logger.error("Faster-Whisper Critical Failure.")

_DEFAULT_TTS_ENGINE = os.getenv("DEFAULT_TTS_ENGINE", os.getenv("TTS_ENGINE", "TURBO"))
# Maps to turbochat speaker_id (audio_ref/<id>.wav). Override via FoveAI_DEFAULT_TTS_VOICE or FoveAI_TURBO_DEFAULT_SPEAKER.
_dtv = os.getenv(
    "FoveAI_DEFAULT_TTS_VOICE",
    os.getenv("FoveAI_TURBO_DEFAULT_SPEAKER", "female_american1-lumba"),
).strip()
_DEFAULT_TTS_VOICE = _dtv if _dtv else "female_american1-lumba"

_voice_lock = threading.Lock()
_runtime_voice_override: str | None = (
    None  # PUT /tts/default_voice; None = use file/env
)


def _voice_from_file() -> str | None:
    """First non-empty, non-# line from FoveAI_TTS_DEFAULT_VOICE_FILE (optional hot-reload without restart)."""
    path = os.getenv("FoveAI_TTS_DEFAULT_VOICE_FILE", "").strip()
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError:
        return None
    return None


def _resolved_default_voice() -> str:
    """Priority: in-memory override → voice file → env defaults."""
    with _voice_lock:
        ov = _runtime_voice_override
    if ov is not None and str(ov).strip():
        return str(ov).strip()
    fv = _voice_from_file()
    if fv:
        return fv
    return _DEFAULT_TTS_VOICE


def _default_voice_source() -> str:
    with _voice_lock:
        if _runtime_voice_override is not None and str(_runtime_voice_override).strip():
            return "override"
    if _voice_from_file():
        return "file"
    return "env"


def _set_voice_override(v: str | None) -> None:
    global _runtime_voice_override
    with _voice_lock:
        if v is None or not str(v).strip():
            _runtime_voice_override = None
        else:
            _runtime_voice_override = str(v).strip()


def resolve_tts_voice(voice: str | None) -> str:
    """Per-request `voice` wins; omit/null uses runtime default (override / file / env)."""
    if voice is not None and str(voice).strip():
        return str(voice).strip()
    return _resolved_default_voice()


def _resolved_tts_backend() -> str:
    """Which HTTP TTS stack the mouth uses: turbo (foveai_turbochat XTTS) or chatterbox (Resemble server).

    Resemble engine (Original / Multilingual / Turbo) is selected in that server's Web UI or config — not here.
    Hot-switch without container env change: FoveAI_TTS_BACKEND_FILE (first line: turbo | chatterbox).
    """
    path = os.getenv(
        "FoveAI_TTS_BACKEND_FILE", "/app/Backend/preflight/tts_backend"
    ).strip()
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    low = line.lower()
                    if low in ("turbo", "chatterbox"):
                        return low
                    break
        except OSError:
            pass
    v = os.getenv("FoveAI_TTS_BACKEND", "turbo").strip().lower()
    return v if v in ("turbo", "chatterbox") else "turbo"


def _chatterbox_openai_voice_filename(foveai_voice: str) -> str:
    """OpenAI /v1/audio/speech requires a filename present under voices/ or reference_audio/ on the Chatterbox server."""
    v = foveai_voice.strip()
    if v.lower().endswith((".wav", ".mp3", ".flac")):
        return v
    return (
        os.getenv("FoveAI_CHATTERBOX_DEFAULT_VOICE", "Emily.wav").strip() or "Emily.wav"
    )


def _piper_synthesize(text: str) -> Response:
    import subprocess

    model_path = os.getenv(
        "PIPER_MODEL_PATH", "/app/models/Mouth/en_US-amy-medium.onnx"
    )
    if not os.path.exists(model_path):
        raise HTTPException(
            status_code=500, detail=f"Piper model missing at {model_path}"
        )
    cmd = ["piper", "--model", model_path, "--output_raw"]
    process = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate(input=text.encode("utf-8"))
    if process.returncode != 0:
        raise HTTPException(
            status_code=500, detail=f"Piper process error: {stderr.decode()}"
        )
    return Response(content=stdout, media_type="audio/wav")


class TTSRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    text: str
    voice: str | None = None
    engine: str = _DEFAULT_TTS_ENGINE


class TTSDefaultVoiceBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    voice: str | None = None  # null or "" clears in-memory override


class TTSBackendBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    backend: Literal["turbo", "chatterbox"]


class STTRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    audio_base64: str


@app.get("/health")
async def health_check():
    return {"status": "online", "mode": MODE}


@app.get("/tts/default_voice")
async def get_tts_default_voice():
    """Current default speaker id (when JSON omits `voice`). GET/PUT/DELETE only in MOUTH mode."""
    if MODE != "MOUTH":
        raise HTTPException(status_code=400, detail="Node not in MOUTH mode")
    return {
        "voice": _resolved_default_voice(),
        "source": _default_voice_source(),
    }


@app.get("/tts/backend")
async def get_tts_backend():
    """Current TTS stack: turbo (foveai_turbochat) or chatterbox (Resemble HTTP)."""
    if MODE != "MOUTH":
        raise HTTPException(status_code=400, detail="Node not in MOUTH mode")
    return {"backend": _resolved_tts_backend()}


@app.put("/tts/backend")
async def put_tts_backend(body: TTSBackendBody):
    """Persist routing preference (FoveAI_TTS_BACKEND_FILE). GPU containers: use Web UI or switch_gpu_tts_stack.ps1."""
    if MODE != "MOUTH":
        raise HTTPException(status_code=400, detail="Node not in MOUTH mode")
    path = os.getenv(
        "FoveAI_TTS_BACKEND_FILE", "/app/Backend/preflight/tts_backend"
    ).strip()
    if not path:
        raise HTTPException(status_code=500, detail="FoveAI_TTS_BACKEND_FILE not set")
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body.backend.strip().lower() + "\n")
    except OSError as e:
        logger.error("Failed to write tts_backend: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    logger.info("TTS backend file set to %s (%s)", body.backend, path)
    return {"backend": _resolved_tts_backend()}


@app.put("/tts/default_voice")
async def put_tts_default_voice(body: TTSDefaultVoiceBody):
    """Set in-memory default voice: turbochat speaker_id (XTTS) or Chatterbox voice filename when using chatterbox backend."""
    if MODE != "MOUTH":
        raise HTTPException(status_code=400, detail="Node not in MOUTH mode")
    _set_voice_override(body.voice)
    logger.info(
        "TTS default voice: source=%s voice=%r",
        _default_voice_source(),
        _resolved_default_voice(),
    )
    return {
        "voice": _resolved_default_voice(),
        "source": _default_voice_source(),
    }


@app.delete("/tts/default_voice")
async def delete_tts_default_voice():
    """Clear in-memory override (fall back to voice file or env)."""
    if MODE != "MOUTH":
        raise HTTPException(status_code=400, detail="Node not in MOUTH mode")
    _set_voice_override(None)
    return {
        "voice": _resolved_default_voice(),
        "source": _default_voice_source(),
    }


@app.post("/stt")
async def handle_stt(request: STTRequest):
    """Bridge for Speech-to-Text"""
    if MODE != "EARS":
        raise HTTPException(status_code=400, detail="Node not in EARS mode")
    if not whisper_model:
        return {"text": "[STT Offline - Model Failed to Load]"}
    try:
        audio_data = base64.b64decode(request.audio_base64)
        # Use .webm extension so ffmpeg decodes the MediaRecorder container correctly.
        # Saving as .wav when the data is actually WebM causes decoder confusion and
        # triggers Whisper hallucination (repeated words like "you you you").
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
            temp_audio.write(audio_data)
            temp_file_path = temp_audio.name
        segments, info = whisper_model.transcribe(
            temp_file_path,
            beam_size=1,
            language="en",
            # --- Hallucination / stutter fixes ---
            # Disable previous-text conditioning: the single biggest cause of
            # "you you you" / "alright alright" repetition loops in Whisper.
            condition_on_previous_text=False,
            # Enable Silero VAD to literally delete silence BEFORE whisper decodes it, killing "Ok" loops
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            # Drop silent or near-silent chunks before beam decode.
            no_speech_threshold=0.6,
            # Greedy deterministic decode — stochastic sampling amplifies hallucinations.
            temperature=0.0,
            # Reject outputs with very high repetition (compression ratio too high = garbage).
            compression_ratio_threshold=2.4,
        )
        transcription = " ".join([segment.text for segment in segments]).strip()
        os.unlink(temp_file_path)
        if not transcription:
            return {"text": ""}
        logger.info(f"Transcribed Text: {transcription}")
        return {"text": transcription}
    except Exception as e:
        logger.error(f"STT Error: {e}")
        return {"text": f"[STT Error: {str(e)[:50]}]"}


async def _post_chatterbox_openai_speech(
    client: httpx.AsyncClient, text: str, foveai_voice: str
) -> Response | None:
    """Resemble Chatterbox OpenAI-compatible endpoint; uses server's active model (UI / config)."""
    base = os.getenv(
        "FoveAI_CHATTERBOX_HTTP_URL", "http://foveai_chatterbox_resemble:8004"
    ).rstrip("/")
    model = os.getenv("FoveAI_CHATTERBOX_OPENAI_MODEL", "chatterbox")
    voice_fn = _chatterbox_openai_voice_filename(foveai_voice)
    url = f"{base}/v1/audio/speech"
    payload = {
        "model": model,
        "input": text,
        "voice": voice_fn,
        "response_format": "wav",
    }
    logger.info("Mouth: Chatterbox OpenAI POST %s (voice file=%s)", url, voice_fn)
    resp = await client.post(url, json=payload, timeout=_turbo_client_timeout())
    if resp.status_code == 200:
        return Response(content=resp.content, media_type="audio/wav")
    logger.warning(
        "Chatterbox OpenAI %s returned %s: %s",
        url,
        resp.status_code,
        (resp.text or "")[:200],
    )
    return None


@app.post("/tts")
async def handle_tts(request: TTSRequest):
    """Bridge for Text-to-Speech"""
    if MODE != "MOUTH":
        raise HTTPException(status_code=400, detail="Node not in MOUTH mode")

    voice = resolve_tts_voice(request.voice)
    backend = _resolved_tts_backend()
    logger.info(
        "TTS Request: %s (backend=%s, Engine: %s, voice: %s)",
        request.text,
        backend,
        request.engine,
        voice,
    )

    # Resemble Chatterbox (HTTP): engine / Original vs Multilingual vs Turbo is on that server, not the JSON engine field.
    if backend == "chatterbox":
        try:
            async with httpx.AsyncClient() as client:
                spoken = await _post_chatterbox_openai_speech(
                    client, request.text, voice
                )
                if spoken is not None:
                    return spoken
        except Exception as e:
            logger.warning("Chatterbox request failed: %s: %s", type(e).__name__, e)
        logger.warning("Chatterbox failed; falling back to Piper")
        try:
            return _piper_synthesize(request.text)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Piper synthesis failed: %s", e)
            raise HTTPException(
                status_code=500, detail=f"Chatterbox and Piper failed: {e}"
            )

    engine_to_use = request.engine

    def _turbo_tts_targets() -> list[str]:
        bases = [TURBO_URL] + _extra_tts_bases("TURBO_EXTRA_URLS")
        return [f"{b}/tts" for b in bases if b]

    def _legacy_xtts_targets() -> list[str]:
        if not CHATTERBOX_URL:
            return []
        bases = [CHATTERBOX_URL] + _extra_tts_bases("CHATTERBOX_EXTRA_URLS")
        return [f"{b}/tts" for b in bases if b]

    try:
        async with httpx.AsyncClient() as client:
            # TURBO PRIMARY (same API as turbochat_server: speaker_id)
            if engine_to_use == "TURBO":
                for target in _turbo_tts_targets():
                    try:
                        payload = {"text": request.text, "speaker_id": voice}
                        logger.info(
                            f"Mouth: Attempting TURBO at {target} (read timeout {_TURBO_READ_TIMEOUT}s)"
                        )
                        resp = await client.post(
                            target, json=payload, timeout=_turbo_client_timeout()
                        )
                        if resp.status_code == 200:
                            return Response(
                                content=resp.content, media_type="audio/wav"
                            )
                        body_preview = (resp.text or "")[:200]
                        logger.warning(
                            f"TURBO target {target} returned status {resp.status_code}: {body_preview}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to reach TURBO {target}: {type(e).__name__}: {e}"
                        )

                logger.warning(
                    "All TURBO attempts failed. Falling back to CHATTERBOX..."
                )
                engine_to_use = "CHATTERBOX"

            # CHATTERBOX: try turbo surrogate (fast), then optional legacy XTTS on CHATTERBOX_URL, then Piper
            if engine_to_use == "CHATTERBOX":
                logger.info(
                    "Mouth: CHATTERBOX requested. Attempting TURBO surrogate first..."
                )
                for target in _turbo_tts_targets():
                    try:
                        payload = {"text": request.text, "speaker_id": voice}
                        resp = await client.post(
                            target, json=payload, timeout=_turbo_client_timeout()
                        )
                        if resp.status_code == 200:
                            logger.info(f"Mouth: TURBO surrogate OK via {target}.")
                            return Response(
                                content=resp.content, media_type="audio/wav"
                            )
                        logger.warning(
                            f"Mouth: TURBO surrogate HTTP {resp.status_code} from {target}: {(resp.text or '')[:200]}"
                        )
                    except Exception as te:
                        logger.warning(
                            f"Mouth: TURBO surrogate attempt at {target} failed: {type(te).__name__}: {te}"
                        )

                xtts_targets = _legacy_xtts_targets()
                if xtts_targets:
                    for target in xtts_targets:
                        try:
                            payload = {
                                "text": request.text,
                                "speaker_wav": voice,
                                "language": "en",
                            }
                            logger.info(f"Mouth: Forwarding to legacy XTTS at {target}")
                            resp = await client.post(target, json=payload, timeout=45.0)
                            if resp.status_code == 200:
                                return Response(
                                    content=resp.content, media_type="audio/wav"
                                )
                            logger.warning(
                                f"XTTS target {target} returned status {resp.status_code}"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to reach XTTS {target}: {e}")
                else:
                    logger.info(
                        "Mouth: CHATTERBOX_URL unset — skipping legacy XTTS container (see docker-compose)."
                    )

                logger.warning("All XTTS attempts failed. Attempting PIPER fallback...")
                engine_to_use = "PIPER"

            # PIPER LOCAL SYNTHESIS
            if engine_to_use == "PIPER":
                try:
                    return _piper_synthesize(request.text)
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Piper synthesis failed: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"All TTS engines failed. Piper Error: {e!s}",
                    )

    except Exception as e:
        logger.error(f"TTS Failure: {e!s}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = 8001 if MODE == "EARS" else 8002
    uvicorn.run(app, host="0.0.0.0", port=port)
