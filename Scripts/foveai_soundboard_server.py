from __future__ import annotations

import os, sys
_venv = os.getenv("FoveAI_VENV_PATH", ".venv")
_venv_python = os.path.join(os.path.dirname(__file__), ".." if "/" in __file__ else "..", _venv, "Scripts", "python.exe")
if not os.path.exists(_venv_python):
    _venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", _venv, "Scripts", "python.exe")

"""
FoveAI Soundboard Server - Stable Audio Tools integration (SOUNDBOARD :8006)

Generates short emotional audio clips from text descriptions using
Stability AI's stable-audio-open-1.0 model. Triggered by the <request:description>
bracket token in Jen's text stream.

Architecture: ARCHITECTURE.md S9B / FoveAI.md S12
Frontend calls /api/soundboard/generate (proxied via xr_app.py :8080 -> :8006).

Requires: stable-audio-tools, torch, torchaudio, fastapi, uvicorn
Install: pip install -r Scripts/requirements.soundboard.txt
         pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
         pip install stable-audio-tools

Env vars:
  FoveAI_SOUNDBOARD_PORT       - port to serve on (default 8006)
  FoveAI_SOUNDBOARD_MODEL      - HuggingFace model name or local path (default stabilityai/stable-audio-open-1.0)
  FoveAI_SOUNDBOARD_DEVICE     - torch device (default cuda if available, else cpu)
  FoveAI_SOUNDBOARD_OUTPUT_DIR - directory to save generated WAV files (default frontend/XR_Vessel/public/soundboard)
  FoveAI_SOUNDBOARD_DURATION   - default generation duration in seconds (default 1.0)
"""

import base64
import io
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("foveai_soundboard")

# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------
PORT = int(os.getenv("FoveAI_SOUNDBOARD_PORT", "8006"))
MODEL_NAME = os.getenv("FoveAI_SOUNDBOARD_MODEL", "stabilityai/stable-audio-open-1.0")
def _detect_device():
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"

DEVICE = os.getenv("FoveAI_SOUNDBOARD_DEVICE", "") or _detect_device()
OUTPUT_DIR = os.getenv(
    "FoveAI_SOUNDBOARD_OUTPUT_DIR",
    os.path.join(os.path.dirname(__file__), "..", "Frontend", "XR_Vessel", "public", "soundboard"),
)
DEFAULT_DURATION = float(os.getenv("FoveAI_SOUNDBOARD_DURATION", "1.0"))
SAMPLE_RATE = int(os.getenv("FoveAI_SOUNDBOARD_SAMPLE_RATE", "44100"))

# Ensure output directory exists
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
#  Model loading (lazy - loaded on first request)
# ---------------------------------------------------------------------------
_model = None
_model_config = None


def _load_model():
    """Load Stable Audio model on first request (heavy - ~10s on GPU, ~60s on CPU)."""
    global _model, _model_config
    if _model is not None:
        return _model, _model_config

    logger.info("Loading Stable Audio model: %s on %s ...", MODEL_NAME, DEVICE)
    try:
        import torch
        import torchaudio
        from stable_audio_tools import get_pretrained_model
        _model, _model_config = get_pretrained_model(MODEL_NAME)
        _model = _model.to(DEVICE)
        _model.eval()
        logger.info("Stable Audio model loaded successfully (sample_rate=%s)", _model_config.get("sample_rate", SAMPLE_RATE))
    except ImportError:
        logger.error(
            "stable-audio-tools not installed. Run: pip install stable-audio-tools"
        )
        raise
    except Exception as e:
        logger.error("Failed to load Stable Audio model: %s", e)
        raise
    return _model, _model_config


# ---------------------------------------------------------------------------
#  FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="FoveAI Soundboard (Stable Audio)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    description: str
    category: str = "generated"
    duration: Optional[float] = None


class GenerateResponse(BaseModel):
    tag: str
    url: str
    audio_base64: Optional[str] = None
    duration_ms: int
    blend_shapes: Dict[str, float]
    model: str


# Track generated sounds for the /list and /context endpoints
_generated: List[Dict[str, Any]] = []


@app.get("/health")
async def health():
    model_loaded = _model is not None
    return {
        "status": "ok" if model_loaded else "model_not_loaded",
        "model": MODEL_NAME,
        "device": DEVICE,
        "generated_count": len(_generated),
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Generate a short audio clip from a text description using Stable Audio."""
    if not req.description or not req.description.strip():
        raise HTTPException(status_code=400, detail="description is required")

    model, config = _load_model()

    duration = req.duration or DEFAULT_DURATION
    sample_rate = config.get("sample_rate", SAMPLE_RATE) if config else SAMPLE_RATE

    # Sanitise description for the model prompt
    prompt = f"{req.description.strip()}, high quality, short sound effect"

    logger.info("Generating: '%s' (%.1fs @ %dHz)", prompt, duration, sample_rate)
    start_time = time.time()

    try:
        import torch
        import torchaudio
        with torch.no_grad():
            # Stable Audio conditional generation
            conditioning = [{"prompt": prompt, "seconds_start": 0, "seconds_total": duration}]
            output = model.generate(conditioning, sample_rate=sample_rate)

        # output is a dict with 'audio' key containing waveform tensor
        audio_tensor = output.get("audio", output) if isinstance(output, dict) else output

        # Ensure correct shape: [batch, channels, samples] -> [channels, samples]
        if audio_tensor.dim() == 3:
            audio_tensor = audio_tensor.squeeze(0)
        if audio_tensor.dim() == 1:
            audio_tensor = audio_tensor.unsqueeze(0)

        # Trim to requested duration
        max_samples = int(duration * sample_rate)
        if audio_tensor.shape[-1] > max_samples:
            audio_tensor = audio_tensor[..., :max_samples]

        # Apply gentle fade-out to avoid clicks
        fade_samples = min(int(sample_rate * 0.05), audio_tensor.shape[-1] // 4)
        if fade_samples > 0:
            fade = torch.linspace(1.0, 0.0, fade_samples, device=audio_tensor.device)
            audio_tensor[..., -fade_samples:] *= fade

        gen_time = time.time() - start_time
        logger.info("Generated in %.1fs - shape: %s", gen_time, list(audio_tensor.shape))

    except Exception as e:
        logger.error("Stable Audio generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    # Create a safe tag from the description
    safe_tag = re.sub(r"[^a-z0-9]", "_", req.description.lower().strip())[:24]
    tag = f"gen_{safe_tag}_{uuid.uuid4().hex[:6]}"

    # Save WAV to output directory
    filename = f"{tag}.wav"
    filepath = os.path.join(OUTPUT_DIR, filename)

    try:
        torchaudio.save(filepath, audio_tensor.cpu(), sample_rate)
        logger.info("Saved: %s", filepath)
    except Exception as e:
        logger.warning("Failed to save WAV file: %s - returning base64 only", e)
        filepath = None

    # Encode as base64 for immediate frontend playback
    buffer = io.BytesIO()
    torchaudio.save(buffer, audio_tensor.cpu(), sample_rate, format="wav")
    audio_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    # Derive simple blend shapes from category
    category_blends: Dict[str, Dict[str, float]] = {
        "surprise": {"surprised": 0.4, "eyeWide": 0.3},
        "joy": {"happy": 0.5, "mouthSmile": 0.4},
        "contentment": {"relaxed": 0.3, "mouthSmile": 0.2},
        "contemplation": {"thinking": 0.4, "eyeSquint": 0.2},
        "realization": {"surprised": 0.5, "mouthOpen": 0.2},
        "mannerism": {"neutral": 0.2},
        "agreement": {"nod": 0.3, "mouthSmile": 0.2},
        "generated": {"neutral": 0.1},
    }
    blend_shapes = category_blends.get(req.category, category_blends["generated"])

    result = {
        "tag": tag,
        "url": f"/soundboard/{filename}" if filepath else "",
        "audio_base64": audio_base64,
        "duration_ms": int(duration * 1000),
        "blend_shapes": blend_shapes,
        "model": MODEL_NAME,
    }

    _generated.append({**result, "description": req.description, "category": req.category})

    return result


@app.get("/list")
async def list_sounds():
    """List all dynamically generated sounds."""
    return {"sounds": _generated, "total": len(_generated)}


@app.get("/context")
async def context():
    """Return sensory text for brain context injection."""
    if not _generated:
        return {"context": "", "tags": []}
    tags = [s["tag"] for s in _generated]
    lines = [
        "Dynamically generated soundboard expressions (Stable Audio):",
    ]
    for s in _generated:
        lines.append(f"  [{s.get('category', 'generated')}] {s['tag']} - \"{s.get('description', '')}\"")
    return {"context": "\n".join(lines), "tags": tags}


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn not installed. Run:")
        print("  call .\\.venv\\unified\\Scripts\\activate.bat && pip install uvicorn[standard]")
        raise SystemExit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("FoveAI Soundboard Server starting on port %d (model=%s, device=%s)", PORT, MODEL_NAME, DEVICE)
    logger.info("Output directory: %s", os.path.abspath(OUTPUT_DIR))
    uvicorn.run(app, host="0.0.0.0", port=PORT)
