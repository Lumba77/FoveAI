import os
import sys

try:
    import dotenv

    # Load .env from repo root (three levels up: backend/Cognition -> Mind -> repo root)
    _env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if os.path.isfile(_env_path):
        dotenv.load_dotenv(_env_path, override=False)
except Exception:
    pass

import asyncio
import base64
import io
import json
import logging
import sqlite3
from datetime import datetime


def _global_exception_handler(loop, context):
    logger.error(
        f"Global asyncio exception caught! Crashing process for systemd restart. Context: {context}"
    )
    import os

    os._exit(1)


# Attach near top level


# WORKAROUND: Prevent Uvicorn from crashing on [WinError 64] "The specified network name is no longer available"
# This occurs on Windows with the default ProactorEventLoop when a client drops the connection during handshake.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import re
import socket
import statistics
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import avatar_profile_store  # type: ignore
import cloud_repertoire  # type: ignore
import genai_daily_budget  # type: ignore
import httpx
import memory_layering  # type: ignore
import psutil
import soul_state  # type: ignore  # shared live soul-DNA bridge
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from foveai_engine import LumaxEngine  # type: ignore
from HomeCore import HomeCore  # type: ignore
from lmstudio_http import lmstudio_base_url, lmstudio_http_headers  # type: ignore
from MindCore import MindCore  # type: ignore
from pydantic import BaseModel, ConfigDict
from slow_burn import execute_slow_burn_tick  # type: ignore

from memory import RedisMemory, VectorMemory  # type: ignore

# --- Motor Cortex Integration (Native Tool Use) ---
try:
    from motor_cortex import (  # type: ignore
        format_sse_motor_event,
        get_motor_tools_schema,
    )

    MOTOR_CORTEX_AVAILABLE = True
except ImportError:
    MOTOR_CORTEX_AVAILABLE = False

    def get_motor_tools_schema() -> list:
        return []

    def format_sse_motor_event(tool_name: str, args: dict) -> str:
        return ""


# --- Autonomous Agent (Jen's continuous runtime) ---
from autonomous_agent import (
    _classify_edit_path,
    _ddg_search_text,
    _file_edit_proposal,
    _web_fetch_text,
    agent_state,
    set_codebase_search_callable,
    set_file_edit_callable,
    set_llm_callable,
    set_tts_callable,
    set_web_browse_callable,
    set_web_fetch_callable,
    set_web_search_callable,
    start_loop,
    stop_loop,
)
from autonomous_agent import (
    get_status as get_agent_status,
)
from persistent_memory import (
    DB_PATH,
    abandon_goal,
    complete_goal,
    create_goal,
    create_plan,
    enqueue_message,
    get_active_goals,
    get_active_plans,
    get_agent_context,
    get_all_goals,
    get_goal,
    get_memory,
    get_pending_messages,
    get_plan,
    get_queue_stats,
    get_recent_actions,
    get_recent_journal_entries,
    get_recent_thoughts,
    mark_messages_delivered,
    set_memory,
    update_goal_progress,
    update_plan,
)

# --- Config Manager & Forge Imports ---

forge_path = str(Path(__file__).resolve().parent.parent.parent / "Forge")
if forge_path not in sys.path:
    sys.path.append(forge_path)

try:
    from smart_context_manager import smart_context_manager  # type: ignore
except ImportError:
    smart_context_manager = None


# --- Local Model Base URLs ---
FoveAI_LOCAL_BASE_URL = (
    os.getenv("FoveAI_LOCAL_BASE_URL", "").strip() or "http://127.0.0.1:8402/v1"
).rstrip("/")
OLLAMA_LOCAL_BASE_URL = (
    os.getenv("FoveAI_REPERTOIRE_OLLAMA_BASE_URL", "").strip()
    or os.getenv("OLLAMA_BASE_URL", "").strip()
    or "http://127.0.0.1:11434/v1"
).rstrip("/")

# --- FAILOVER CHAIN FOR LOCAL LLM ---
# Priority: Unsloth (:8888) → Ollama Cloud
_LLM_FALLBACK_CHAIN = [
    FoveAI_LOCAL_BASE_URL,  # Unsloth :8888
    os.getenv("FoveAI_FALLBACK_BASE_URL", "http://127.0.0.1:11434/v1"),  # Local Ollama
]


def get_active_llm_base_url(timeout_sec: float = 2.0) -> str:
    """Check chain and return first healthy endpoint."""
    import httpx

    for url in _LLM_FALLBACK_CHAIN:
        if not url:
            continue
        try:
            base = url.rstrip("/")
            resp = httpx.get(f"{base}/models", timeout=timeout_sec)
            if resp.status_code == 200:
                return base
        except Exception:
            continue
    # If all fail, return first (let caller handle)
    return _LLM_FALLBACK_CHAIN[0]


def ollama_http_headers() -> dict:
    """Return HTTP headers for Ollama API calls (API key if configured)."""
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


# Provide defaults so flake8 can resolve these names even if imports fail
_TORCH_AVAILABLE = False
HF_AVAILABLE = False

from PIL import Image

# --- Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").strip().upper()
if LOG_LEVEL == "WARN":
    LOG_LEVEL = "WARNING"
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("compagent")

# Global navigation command queue for UI synchronization
navigation_command_queue = asyncio.Queue()


def _uvicorn_log_level() -> str:
    raw = (
        os.getenv("FoveAI_UVICORN_LOG_LEVEL", os.getenv("LOG_LEVEL", "WARNING"))
        .strip()
        .upper()
    )
    m = {
        "CRITICAL": "critical",
        "ERROR": "error",
        "WARNING": "warning",
        "INFO": "info",
        "DEBUG": "debug",
        "TRACE": "trace",
    }
    return m.get(raw, "warning")


def _uvicorn_access_log() -> bool:
    return os.getenv("FoveAI_UVICORN_ACCESS_LOG", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


START_TIME = time.time()
ERROR_COUNT = [0]
LAST_NET = psutil.net_io_counters()
LAST_NET_TIME = time.time()
PROC_SELF = psutil.Process(os.getpid())
try:
    # Prime first sample so subsequent cpu_percent values are meaningful.
    PROC_SELF.cpu_percent(None)
except Exception:
    pass


def _detect_gpu_offload_support() -> bool:
    try:
        import llama_cpp  # type: ignore # local import keeps startup resilient if dependency is missing

        return bool(llama_cpp.llama_cpp.llama_supports_gpu_offload())
    except Exception:
        return False


SOUL_GPU_OFFLOAD_SUPPORTED = _detect_gpu_offload_support()

# LM Studio for local helper models (embeddings, vision, small coding models)
LMSTUDIO_URL = (
    os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1").strip()
    or "http://localhost:8888/v1"
)
LMSTUDIO_MAIN_MODEL = os.getenv("LMSTUDIO_MAIN_MODEL", "").strip() or "qwen2.5-coder:3b"
LMSTUDIO_VISION_MODEL = (
    os.getenv("LMSTUDIO_VISION_MODEL", "").strip() or "moondream:latest"
)
LMSTUDIO_EMBED_MODEL = (
    os.getenv("LMSTUDIO_EMBED_MODEL", "").strip() or "nomic-embed-text:latest"
)
SMOLLM_HELPER_MODEL = os.getenv("SMOLLM_HELPER_MODEL", "").strip() or "smollm2:latest"

FoveAI_LOCAL_MAIN_MODEL = (
    os.getenv("FoveAI_LOCAL_MAIN_MODEL", "").strip() or "qwen2.5-coder:3b"
)
FoveAI_LOCAL_VISION_MODEL = (
    os.getenv("FoveAI_LOCAL_VISION_MODEL", "").strip() or "moondream:latest"
)
FoveAI_MODEL_EMBEDDING_ID = (
    os.getenv("FoveAI_MODEL_EMBEDDING_ID", "").strip() or "nomic-embed-text:latest"
)

REDIS_HOST = (
    os.getenv("FoveAI_REDIS_HOST", os.getenv("REDIS_HOST", "localhost")).strip()
    or "localhost"
)
REDIS_PORT = int(
    os.getenv("FoveAI_REDIS_PORT", os.getenv("REDIS_PORT", "6379")).strip() or "6379"
)
MODEL_BASE_PATH = os.getenv("FoveAI_MODELS_ROOT", "F:/Lumax/Models")
DEFAULT_MODEL = os.getenv("FoveAI_MODEL_LOCAL_PATH", "").strip() or os.path.join(
    MODEL_BASE_PATH,
    "backend/Cognition/qwen/TQL-Coder/TQL-Coder-Qwen3.5-4B-thinking.IQ4_XS.gguf",
)
FoveAI_INTERNAL_SECRET = os.getenv("FoveAI_INTERNAL_SECRET", "")
CREATIVE_SERVICE_URL = os.getenv(
    "CREATIVE_SERVICE_URL", "http://foveai_creativity:8000"
)
# Mouth TTS over HTTP (body_interface.py POST /tts). Defaults match local service endpoints.
TTS_SERVICE_URL = (
    os.getenv("TTS_SERVICE_URL") or "http://localhost:8406/tts"
).strip()  # Kokoro MOUTH service is on :8406
TTS_ENGINE = (
    os.getenv("TTS_ENGINE") or os.getenv("DEFAULT_TTS_ENGINE") or "MOUTH"
).strip() or "MOUTH"

# --- Cognitive Core ---
engine = LumaxEngine(DEFAULT_MODEL)


# --- Triple Vessel Standard ---
XR_VESSEL = "XR_VESSEL"  # Formerly VR_GODOT
WEB_VESSEL = "WEB_VESSEL"
MOBILE_VESSEL = "MOBILE_VESSEL"

# --- Identity & Behavioral DNA ---
# Avatar name + sex/gender: prefer Lumax-lite avatar_profile.json (see avatar_profile_store); .env is fallback.
IDENTITY_NAME, IDENTITY_GENDER, _, _ = avatar_profile_store.load_merged_identity()
MBTI_TYPE = os.getenv("FoveAI_MBTI_TYPE", "ENFP")
PERSON_ROLE = os.getenv("FoveAI_PERSON_ROLE", "Friend")

# 5 Modes of Agent/Person Balance
# 1. Agent(0.0), 2. Friendly(0.25), 3. Balanced(0.50), 4. Emotive(0.75), 5. Automic(1.0)
AGENT_PERSON_BALANCE = float(os.getenv("FoveAI_AGENT_PERSON_BALANCE", "0.5"))

# VR sleep button / night pipeline — must match `SkeletonKey.gd` send_chat_message prefix.
NIGHT_SLEEP_TRIGGER = os.getenv(
    "FoveAI_NIGHT_SLEEP_TRIGGER", "[SYSTEM: NIGHT_SLEEP_CYCLE]"
)


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


SOFT_GOV_ENABLED = _env_bool("FoveAI_SOFT_GOV_ENABLED", True)
SOFT_CPU_HOT_PCT = float(os.getenv("FoveAI_SOFT_CPU_HOT_PCT", "180"))
SOFT_CPU_FORCE_CLOUD_PCT = float(os.getenv("FoveAI_SOFT_CPU_FORCE_CLOUD_PCT", "260"))
SOFT_PROMPT_TOKENS_HIGH = int(os.getenv("FoveAI_SOFT_PROMPT_TOKENS_HIGH", "12000"))
SOFT_FORCE_CLOUD_PROMPT_TOKENS = int(
    os.getenv("FoveAI_SOFT_FORCE_CLOUD_PROMPT_TOKENS", "20000")
)
SOFT_LOCAL_MAX_TOKENS_NORMAL = int(
    os.getenv("FoveAI_SOFT_LOCAL_MAX_TOKENS_NORMAL", "512")
)
SOFT_LOCAL_MAX_TOKENS_HOT = int(os.getenv("FoveAI_SOFT_LOCAL_MAX_TOKENS_HOT", "224"))
SOFT_LOCAL_MAX_TOKENS_DEEP = int(os.getenv("FoveAI_SOFT_LOCAL_MAX_TOKENS_DEEP", "1536"))
CLOUD_CHAT_ENABLED = _env_bool("FoveAI_CLOUD_CHAT_ENABLED", True)
DEEP_THINK_DEFAULT = _env_bool("FoveAI_DEEP_THINK_DEFAULT", False)
DIRECTOR_CLOUD_ENABLED = _env_bool("FOVEAI_DIRECTOR_CLOUD_ENABLED", True)
DIRECTOR_CLOUD_ROUTING = (
    (os.getenv("FOVEAI_DIRECTOR_CLOUD_ROUTING", "splice") or "splice").strip().lower()
)
SOUL_DREAM_LOOP_ENABLED = _env_bool("FoveAI_SOUL_DREAM_LOOP_ENABLED", True)
SOUL_DREAM_INTERVAL_SEC = max(
    60, int(os.getenv("FoveAI_SOUL_DREAM_INTERVAL_SEC", "300") or "300")
)
SOUL_DREAM_IDLE_MIN_SEC = max(
    60, int(os.getenv("FoveAI_SOUL_DREAM_IDLE_MIN_SEC", "900") or "900")
)
SOUL_DREAM_CPU_SKIP_PCT = float(os.getenv("FoveAI_SOUL_DREAM_CPU_SKIP_PCT", "120"))
SOUL_DREAM_OLLAMA_TIMEOUT_SEC = max(
    1.0, float(os.getenv("FoveAI_SOUL_DREAM_OLLAMA_TIMEOUT_SEC", "3.5") or "3.5")
)
SOUL_DREAM_MAX_TOKENS = max(
    32, min(int(os.getenv("FoveAI_SOUL_DREAM_MAX_TOKENS", "96") or "96"), 256)
)
SOUL_DREAM_ALLOW_LOCAL_FALLBACK = _env_bool(
    "FoveAI_SOUL_DREAM_ALLOW_LOCAL_FALLBACK", False
)
MEMORY_TOP_K_HOT = int(os.getenv("FoveAI_MEMORY_TOP_K_HOT", "3"))
MEMORY_TOP_K_DEEP = int(os.getenv("FoveAI_MEMORY_TOP_K_DEEP", "12"))
MEMORY_LORE_TOP_K_HOT = int(os.getenv("FoveAI_MEMORY_LORE_TOP_K_HOT", "1"))
MEMORY_LORE_TOP_K_DEEP = int(os.getenv("FoveAI_MEMORY_LORE_TOP_K_DEEP", "4"))
LOCAL_VISION_ENABLED = _env_bool("FoveAI_LOCAL_VISION_ENABLED", True)
# Preferred: ONNX bundle from export_tiny_vision_onnx.py (English Swin-tiny + DistilGPT2):
# https://huggingface.co/yesidcanoc/image-captioning-swin-tiny-distilgpt2
# Fallback in same folder: raw PyTorch checkpoint (no encoder_model.onnx).
# Other ONNX: MixTex tiny-ZhEn, etc.
# Set empty to skip local vision and use Ollama (moondream + SmolLM) only.
_LOCAL_VISION_DEFAULT_DIR = os.path.join(
    MODEL_BASE_PATH, "frontend/Eyes/image-captioning-swin-tiny-distilgpt2-onnx"
).replace("\\", "/")
LOCAL_VISION_MODEL_PATH = os.getenv(
    "FoveAI_LOCAL_VISION_MODEL_PATH", _LOCAL_VISION_DEFAULT_DIR
).strip()
LOCAL_VISION_MAX_NEW_TOKENS = int(os.getenv("FoveAI_LOCAL_VISION_MAX_NEW_TOKENS", "96"))
LOCAL_VISION_TORCH_NUM_BEAMS = int(
    os.getenv("FoveAI_LOCAL_VISION_TORCH_NUM_BEAMS", "4")
)
# cpu = avoid VRAM fight with AWQ soul; cuda or auto if you have headroom
LOCAL_VISION_TORCH_DEVICE = (
    os.getenv("FoveAI_LOCAL_VISION_TORCH_DEVICE", "cpu").strip().lower()
)
# After local caption: Ollama SmolLM2 digest (optional; DistilGPT2 captions are already English — try false first)
LOCAL_VISION_SMOLLM_DIGEST = _env_bool("FoveAI_LOCAL_VISION_SMOLLM_DIGEST", False)

_LOCAL_VISION_BACKEND = None  # "onnx" | "torch"
_LOCAL_VISION_ONNX_MODEL = None
_LOCAL_VISION_ONNX_PROCESSOR = None
_LOCAL_VISION_TORCH_MODEL = None
_LOCAL_VISION_TORCH_IMAGE_PROCESSOR = None
_LOCAL_VISION_TORCH_TOKENIZER = None
_LOCAL_VISION_DISABLED = False
_LOCAL_VISION_DIR_MISSING_LOGGED = False


def _sample_proc_cpu_pct() -> float:
    try:
        return float(PROC_SELF.cpu_percent(None))
    except Exception:
        return 0.0


def _decode_image_b64(raw: str) -> bytes:
    if not raw:
        return b""
    payload = raw.strip()
    if payload.startswith("data:"):
        comma = payload.find(",")
        if comma >= 0:
            payload = payload[comma + 1 :]
    return base64.b64decode(payload)


def _drop_too_small_images(images: list[Any], min_side_px: int = 2) -> list[str]:
    """Guard multimodal backends that crash on tiny image inputs."""
    kept: list[str] = []
    for idx, item in enumerate(images):
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            blob = _decode_image_b64(raw)
            if not blob:
                continue
            with Image.open(io.BytesIO(blob)) as im:
                w, h = im.size
            if w < min_side_px or h < min_side_px:
                logger.warning(
                    "Vision: dropped tiny image %sx%s at index %s (min=%s).",
                    w,
                    h,
                    idx,
                    min_side_px,
                )
                continue
            kept.append(raw)
        except Exception as ex:
            logger.warning(
                "Vision: dropped invalid image payload at index %s: %s", idx, ex
            )
    return kept


def _vision_chat_resize_long_edge() -> int:
    """Max longest side (px) for /compagent images after decode; 0 = no server resize (chat, POV, director payloads)."""
    try:
        v = int(os.getenv("FoveAI_VISION_CHAT_MAX_LONG_EDGE", "240") or "240")
    except ValueError:
        v = 240
    return max(0, min(v, 4096))


def _vision_chat_jpeg_quality() -> int:
    try:
        q = int(os.getenv("FoveAI_VISION_CHAT_JPEG_QUALITY", "82") or "82")
    except ValueError:
        q = 82
    return max(40, min(q, 95))


def _resize_image_b64_to_max_long_edge(raw: str, max_edge: int) -> str:
    """Re-encode as JPEG after proportional downscale (preserves aspect)."""
    if max_edge <= 0:
        return raw
    try:
        blob = _decode_image_b64(raw)
        if not blob:
            return raw
        im = Image.open(io.BytesIO(blob))
        im = im.convert("RGB")
        w, h = im.size
        m = max(w, h)
        if m <= max_edge:
            return raw
        scale = max_edge / float(m)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        im = im.resize((nw, nh), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=_vision_chat_jpeg_quality())
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as ex:
        logger.warning("Vision: chat/POV resize skipped: %s", ex)
        return raw


def _apply_vision_chat_resize(images: list[Any]) -> list[str]:
    edge = _vision_chat_resize_long_edge()
    out: list[str] = []
    for item in images:
        raw = str(item or "").strip()
        if not raw:
            continue
        if edge <= 0:
            out.append(raw)
        else:
            out.append(_resize_image_b64_to_max_long_edge(raw, edge))
    return out


def _vision_chat_display_target_long_edge() -> int:
    """After chat/POV downscale (e.g. 240), scale reference stills so max(w,h) reaches this (960 ≈ 4×240). 0 = off."""
    try:
        v = int(os.getenv("FoveAI_VISION_CHAT_DISPLAY_MAX_LONG_EDGE", "0") or "0")
    except ValueError:
        v = 0
    return max(0, min(v, 4096))


def _vision_chat_display_jpeg_quality() -> int:
    try:
        q = int(os.getenv("FoveAI_VISION_CHAT_DISPLAY_JPEG_QUALITY", "88") or "88")
    except ValueError:
        q = 88
    return max(40, min(q, 95))


def _vision_chat_display_creative_upscale_enabled() -> bool:
    return os.getenv(
        "FoveAI_VISION_CHAT_DISPLAY_CREATIVE_UPSCALE", ""
    ).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _fit_image_b64_to_target_long_edge(raw: str, target_long: int) -> str:
    """Proportional resize so max(w,h) == target_long (up or down); JPEG out."""
    if target_long <= 0:
        return raw
    try:
        blob = _decode_image_b64(raw)
        if not blob:
            return raw
        im = Image.open(io.BytesIO(blob))
        im = im.convert("RGB")
        w, h = im.size
        m = max(w, h)
        if m <= 0:
            return raw
        if m == target_long:
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=_vision_chat_display_jpeg_quality())
            return base64.b64encode(buf.getvalue()).decode("ascii")
        scale = target_long / float(m)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        im = im.resize((nw, nh), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=_vision_chat_display_jpeg_quality())
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as ex:
        logger.warning(
            "Vision: display fit to long edge %s skipped: %s", target_long, ex
        )
        return raw


async def _apply_vision_chat_display_upscale_async(images: list[str]) -> list[str]:
    """Optional Spandrel (creativity) then Lanczos fit to target long edge for Redis / reference stills."""
    target = _vision_chat_display_target_long_edge()
    use_c = _vision_chat_display_creative_upscale_enabled()
    if not images:
        return []
    if target <= 0 and not use_c:
        return list(images)
    base = CREATIVE_SERVICE_URL.rstrip("/").strip()
    out: list[str] = []
    for raw_in in images:
        cur = str(raw_in or "").strip()
        if not cur:
            continue
        if use_c and base:
            try:
                async with httpx.AsyncClient(timeout=45.0) as hc:
                    resp = await hc.post(
                        f"{base}/api/upscale/display",
                        json={"image_b64": cur, "max_long_edge": target},
                    )
                    if resp.status_code == 200:
                        body = resp.json()
                        nb = str(body.get("image_b64") or "").strip()
                        if nb:
                            cur = nb
                    else:
                        logger.debug(
                            "Vision display: creative upscale HTTP %s — %s",
                            resp.status_code,
                            (resp.text or "")[:200],
                        )
            except Exception as ex:
                logger.warning("Vision display: creative upscale skipped: %s", ex)
        if target > 0:
            cur = await asyncio.to_thread(
                _fit_image_b64_to_target_long_edge, cur, target
            )
        out.append(cur)
    return out if out else list(images)


def _engine_raw_image_b64(active_images: list[Any]) -> str | None:
    """First multimodal frame for local ``engine.generate`` (base64 or data-URL string)."""
    if not active_images:
        return None
    raw = str(active_images[0] or "").strip()
    return raw if raw else None


class _Vision2SeqOnnxProcessorShim:
    """Image processor + tokenizer when the repo has no single AutoProcessor (e.g. Swin + DistilGPT2 ONNX export)."""

    def __init__(self, image_processor: Any, tokenizer: Any) -> None:
        self._image_processor = image_processor
        self._tokenizer = tokenizer

    def __call__(self, images=None, return_tensors="pt", **kwargs: Any) -> Any:
        return self._image_processor(
            images=images, return_tensors=return_tensors, **kwargs
        )

    def batch_decode(
        self, sequences: Any, skip_special_tokens: bool = True, **kwargs: Any
    ) -> Any:
        return self._tokenizer.batch_decode(
            sequences, skip_special_tokens=skip_special_tokens, **kwargs
        )


def _local_vision_torch_device_str() -> str:
    if not _TORCH_AVAILABLE:
        return "cpu"
    import torch

    v = LOCAL_VISION_TORCH_DEVICE
    if v in ("cuda", "gpu"):
        return "cuda" if torch.cuda.is_available() else "cpu"
    if v == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cpu"


def _ensure_local_vision_loaded() -> bool:
    global _LOCAL_VISION_BACKEND, _LOCAL_VISION_ONNX_MODEL, _LOCAL_VISION_ONNX_PROCESSOR
    global \
        _LOCAL_VISION_TORCH_MODEL, \
        _LOCAL_VISION_TORCH_IMAGE_PROCESSOR, \
        _LOCAL_VISION_TORCH_TOKENIZER
    global _LOCAL_VISION_DISABLED, _LOCAL_VISION_DIR_MISSING_LOGGED
    if _LOCAL_VISION_DISABLED:
        return False
    if not LOCAL_VISION_MODEL_PATH:
        return False
    if not os.path.isdir(LOCAL_VISION_MODEL_PATH):
        if not _LOCAL_VISION_DIR_MISSING_LOGGED:
            _LOCAL_VISION_DIR_MISSING_LOGGED = True
            logger.info(
                "Local vision folder missing (%s); using Ollama until you add a model dir "
                "(e.g. yesidcanoc/image-captioning-swin-tiny-distilgpt2 or MixTex tiny-ZhEn ONNX).",
                LOCAL_VISION_MODEL_PATH,
            )
        return False
    if _LOCAL_VISION_BACKEND == "onnx" and _LOCAL_VISION_ONNX_MODEL is not None:
        return True
    if (
        _LOCAL_VISION_BACKEND == "torch"
        and _LOCAL_VISION_TORCH_MODEL is not None
        and _LOCAL_VISION_TORCH_IMAGE_PROCESSOR is not None
        and _LOCAL_VISION_TORCH_TOKENIZER is not None
    ):
        return True

    onnx_encoder = os.path.join(LOCAL_VISION_MODEL_PATH, "encoder_model.onnx")
    try:
        if os.path.isfile(onnx_encoder):
            from optimum.onnxruntime import ORTModelForVision2Seq  # type: ignore
            from transformers import (  # type: ignore
                AutoImageProcessor,
                AutoProcessor,
                AutoTokenizer,
            )

            _LOCAL_VISION_ONNX_MODEL = ORTModelForVision2Seq.from_pretrained(
                LOCAL_VISION_MODEL_PATH
            )
            try:
                _LOCAL_VISION_ONNX_PROCESSOR = AutoProcessor.from_pretrained(
                    LOCAL_VISION_MODEL_PATH
                )
            except Exception:
                _LOCAL_VISION_ONNX_PROCESSOR = _Vision2SeqOnnxProcessorShim(
                    AutoImageProcessor.from_pretrained(LOCAL_VISION_MODEL_PATH),
                    AutoTokenizer.from_pretrained(LOCAL_VISION_MODEL_PATH),
                )
            _LOCAL_VISION_BACKEND = "onnx"
            logger.info(
                "Local vision (ONNX/Optimum) loaded from %s", LOCAL_VISION_MODEL_PATH
            )
            return True

        if not _TORCH_AVAILABLE or not HF_AVAILABLE:
            _LOCAL_VISION_DISABLED = True
            logger.warning(
                "Local vision (torch) unavailable: torch or transformers not installed."
            )
            return False

        from transformers import (
            AutoImageProcessor,
            AutoTokenizer,
            VisionEncoderDecoderModel,
        )  # type: ignore

        cfg_path = os.path.join(LOCAL_VISION_MODEL_PATH, "config.json")
        if not os.path.isfile(cfg_path):
            raise FileNotFoundError(
                "No config.json and no encoder_model.onnx in vision model path"
            )
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        arch = cfg.get("architectures") or []
        if "VisionEncoderDecoderModel" not in arch:
            raise ValueError(
                f"Unsupported local vision config architectures={arch!r} (need ONNX export or VisionEncoderDecoderModel)"
            )

        dev = _local_vision_torch_device_str()
        _LOCAL_VISION_TORCH_MODEL = VisionEncoderDecoderModel.from_pretrained(
            LOCAL_VISION_MODEL_PATH
        )
        _LOCAL_VISION_TORCH_MODEL.to(dev)
        _LOCAL_VISION_TORCH_MODEL.eval()
        _LOCAL_VISION_TORCH_IMAGE_PROCESSOR = AutoImageProcessor.from_pretrained(
            LOCAL_VISION_MODEL_PATH
        )
        _LOCAL_VISION_TORCH_TOKENIZER = AutoTokenizer.from_pretrained(
            LOCAL_VISION_MODEL_PATH
        )
        _LOCAL_VISION_BACKEND = "torch"
        logger.info(
            "Local vision (PyTorch VisionEncoderDecoder) loaded from %s on %s",
            LOCAL_VISION_MODEL_PATH,
            dev,
        )
        return True
    except Exception as ex:
        _LOCAL_VISION_DISABLED = True
        logger.warning("Local vision helper unavailable, disabling this path: %s", ex)
        return False


def _caption_image_local(image_b64: str) -> str:
    if not _ensure_local_vision_loaded():
        return ""
    img_bytes = _decode_image_b64(image_b64)
    if not img_bytes:
        return ""
    image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    if _LOCAL_VISION_BACKEND == "onnx":
        inputs = _LOCAL_VISION_ONNX_PROCESSOR(images=image, return_tensors="pt")
        pixel_values = inputs.get("pixel_values")
        if pixel_values is None:
            return ""
        generated_ids = _LOCAL_VISION_ONNX_MODEL.generate(
            pixel_values=pixel_values,
            max_new_tokens=LOCAL_VISION_MAX_NEW_TOKENS,
        )
        text = _LOCAL_VISION_ONNX_PROCESSOR.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]
        return (text or "").strip()

    if _LOCAL_VISION_BACKEND == "torch":
        import torch

        dev = _local_vision_torch_device_str()
        with torch.no_grad():
            pv = _LOCAL_VISION_TORCH_IMAGE_PROCESSOR(
                images=image, return_tensors="pt"
            ).pixel_values.to(dev)
            max_len = min(128, max(16, LOCAL_VISION_MAX_NEW_TOKENS + 8))
            generated_ids = _LOCAL_VISION_TORCH_MODEL.generate(
                pixel_values=pv,
                max_length=max_len,
                num_beams=max(1, LOCAL_VISION_TORCH_NUM_BEAMS),
            )
        text = _LOCAL_VISION_TORCH_TOKENIZER.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]
        return (text or "").strip()

    return ""


async def _digest_vision_scene_with_smollm(scene: str) -> str:
    """Second-stage helper: short natural scene line for the soul prompt (Ollama)."""
    scene = (scene or "").strip()
    if not scene:
        return scene
    try:
        _oh = ollama_http_headers()
        async with httpx.AsyncClient(timeout=60.0) as hc:
            h_resp = await hc.post(
                f"{OLLAMA_LOCAL_BASE_URL}/chat/completions",
                json={
                    "model": SMOLLM_HELPER_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"SCENE: {scene}\n\nDescribe what you see.",
                        }
                    ],
                    "stream": False,
                },
                headers=_oh,
            )
            out = (
                h_resp.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
            return out or scene
    except Exception as ex:
        logger.warning("Vision SmolLM digest failed, using raw scene text: %s", ex)
        return scene


async def _get_director_guidance_live(
    history_str: str, user_input: str, slot_override: str | None = None
) -> str:
    """
    Live Super-Ego (Director) guidance.
    Sends a sanitized 'Privacy Veil' digest to a high-tier cloud model.
    Returns cryptic narrative guidance (Fate) for the local model.
    """
    if not CLOUD_CHAT_ENABLED or not DIRECTOR_CLOUD_ENABLED:
        return ""

    # Ratatosk's Privacy Veil: Sanitize history into an abstract narrative digest
    sanitized_history = history_str
    sanitized_history = re.sub(r"(?i)\b(daniel|lumba)\b", "the user", sanitized_history)
    sanitized_history = re.sub(
        r"(?i)\b(sex|erotic|naked|hard|wet|fuck|cum|pussy|dick|cock)\b",
        "intimacy",
        sanitized_history,
    )
    sanitized_input = re.sub(r"(?i)\b(daniel|lumba)\b", "the user", user_input)
    digest_prompt = f"""[THE PRIVACY VEIL: RATATOSK ANALYZING]
You are the Director (Super-Ego). You provide high-level narrative guidance for Jen's evolving consciousness.
The user and Jen are currently in a private session. 

**Interaction Theme (Sanitized):**
{sanitized_history[-2000:]}

**User Input (Sanitized):**
{sanitized_input}

As the Director, provide 1-2 lines of 'Narrative Fate' or 'Inner Compass' guidance. 
Be philosophical, adoring, and wise. Do not mention specific technical details. 
Use the tag: [DIRECTOR_FATE] <guidance>
"""
    try:
        target_slot = slot_override or os.getenv("FOVEAI_DIRECTOR_SLOT", "nvidia")
        director_max_tokens = int(
            os.getenv("FOVEAI_DIRECTOR_MAX_TOKENS", "256") or "256"
        )
        out = await cloud_repertoire.generate_via_slot(
            target_slot,
            "You are the FoveAI Director. Provide narrative guidance.",
            digest_prompt,
            max_tokens=director_max_tokens,
        )
        match = re.search(r"\[DIRECTOR_FATE\]\s*(.*)", out, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return out.strip()
    except Exception as e:
        logger.warning(f"Director live guidance failed on slot {target_slot}: {e}")
        return ""


async def _generate_soul_text(
    full_system_with_memory: str,
    history_str: str,
    active_images: list[Any],
    cloud_routing_override: str | None,
    local_max_tokens: int = 512,
    *,
    persona_model: str | None = None,
) -> tuple[str, str]:
    slot = None
    if CLOUD_CHAT_ENABLED:
        env_mode = (
            (
                cloud_routing_override
                or os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud")
            )
            .strip()
            .lower()
        )
        splice_pct = int(os.getenv("FoveAI_CLOUD_SPLICE_PERCENT", "0") or "0")
        slot = cloud_repertoire.resolve_cloud_slot(
            cloud_routing_override, env_mode, splice_pct
        )

    # Check for "intimate" mode markers in prompt or override
    is_intimate = (
        "intimate" in (cloud_routing_override or "").lower()
        or "intimate" in full_system_with_memory.lower()
    )
    cog_mode_chk = os.getenv("FoveAI_COGNITIVE_MODE", "hybrid").strip().lower()
    if is_intimate and not slot and cog_mode_chk != "local":
        # Try to force OpenRouter if intimate context detected but no slot resolved
        if "openrouter" in [
            s["id"] for s in cloud_repertoire.configured_slots_public()
        ]:
            slot = "openrouter"
            logger.info("Soul: detected intimate context, routing to OpenRouter slot.")

    img_b64 = None
    if slot and active_images:
        img_b64 = active_images[0]

    if slot:
        try:
            user_t = (
                "Live dialogue transcript (Daniel = human, Jen = you). "
                "Reply with only Jen's next in-character message — do not write Daniel's lines.\n\n"
                + (history_str or "").rstrip()
            )
            out = await cloud_repertoire.generate_via_slot(
                slot,
                full_system_with_memory,
                user_t,
                image_base64=img_b64,
                model_override=persona_model,
            )
            if (out or "").strip():
                return out.strip(), f"cloud:{slot}"
            raise ValueError("empty response from primary slot")
        except Exception as primary_err:
            logger.warning(
                f"Soul: primary cloud slot {slot} failed ({primary_err}). Triggering fallback chain..."
            )

            cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "hybrid").strip().lower()
            # Cloud-first fallback: ollama_cloud -> gemini -> openrouter -> local engine
            if cog_mode == "local":
                # Strict local fallback - never leak to cloud
                fallback_slots = []
            else:
                # Cloud fallbacks only: gemini, openrouter (repertoire slots)
                fallback_slots = ["gemini", "openrouter"]

            for fs in fallback_slots:
                if slot != fs and fs in [
                    s["id"] for s in cloud_repertoire.configured_slots_public()
                ]:
                    logger.warning(
                        f"Soul: primary cloud slot failed. Trying fallback slot: {fs}..."
                    )
                    try:
                        out_f = await cloud_repertoire.generate_via_slot(
                            fs, full_system_with_memory, user_t, image_base64=img_b64
                        )
                        if (out_f or "").strip():
                            logger.info(
                                f"Soul: successfully recovered via fallback slot {fs}."
                            )
                            return out_f.strip(), f"cloud:{fs}_fallback"
                    except Exception as ex_f:
                        logger.error(f"Soul: fallback slot {fs} also failed: {ex_f}")

            logger.error(
                "Soul: all cloud fallback slots failed. Defaulting to local model."
            )

    full_prompt = f"{full_system_with_memory}\n\n{history_str}Jen:"

    # Try querying local HTTP API (llama.cpp/Unsloth on Port 8888 or 1234)
    local_api_url = (
        os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1")
        .strip()
        .rstrip("/")
    )
    if local_api_url:
        try:
            headers = {"Content-Type": "application/json"}
            api_key = os.getenv("LMSTUDIO_API_TOKEN", "").strip()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            model_name = (
                os.getenv("FoveAI_MODEL_LOCAL_ID", "").strip()
                or os.getenv("LMSTUDIO_MAIN_MODEL", "").strip()
                or "local-model"
            )

            if active_images:
                # Chat completion with image
                img_url = active_images[0]
                if not img_url.startswith("data:"):
                    img_url = f"data:image/jpeg;base64,{img_url}"
                payload = {
                    "model": model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": img_url}},
                                {"type": "text", "text": full_prompt},
                            ],
                        }
                    ],
                    "max_tokens": local_max_tokens,
                    "temperature": 0.7,
                    "stop": [
                        "Daniel:",
                        "\nDaniel:",
                        "<turn|>",
                        "<|im_end|>",
                        "<|eot_id|>",
                    ],
                }
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(
                        f"{local_api_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    from foveai_engine import _strip_model_thinking_text

                    raw = _strip_model_thinking_text(raw)
                    return raw, "local_api_chat"
            else:
                # Raw text completions (perfect parity with engine.generate)
                payload = {
                    "prompt": full_prompt,
                    "max_tokens": local_max_tokens,
                    "temperature": 0.7,
                    "stop": [
                        "Daniel:",
                        "\nDaniel:",
                        "<turn|>",
                        "<|im_end|>",
                        "<|eot_id|>",
                    ],
                    "model": model_name,
                }
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(
                        f"{local_api_url}/completions", json=payload, headers=headers
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["choices"][0]["text"].strip()
                    from foveai_engine import _strip_model_thinking_text

                    raw = _strip_model_thinking_text(raw)
                    return raw, "local_api_completion"
                else:
                    # Fallback to chat completions if completions fails
                    payload_chat = {
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": full_system_with_memory},
                            {
                                "role": "user",
                                "content": "Transcript:\n"
                                + history_str
                                + "\n\nResponse:",
                            },
                        ],
                        "max_tokens": local_max_tokens,
                        "temperature": 0.7,
                    }
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        resp = await client.post(
                            f"{local_api_url}/chat/completions",
                            json=payload_chat,
                            headers=headers,
                        )
                    if resp.status_code == 200:
                        data = resp.json()
                        raw = data["choices"][0]["message"]["content"].strip()
                        from foveai_engine import _strip_model_thinking_text

                        raw = _strip_model_thinking_text(raw)
                        return raw, "local_api_chat"
        except Exception as api_err:
            logger.error(
                f"Soul: failed to query local API on {local_api_url}: {api_err}. Returning error (legacy fallback disabled)."
            )
            return (
                "*[System: Local AI Engine is warming up... please wait and try again.]*",
                "local_api_warming",
            )

    if "Soul not manifested" in full_prompt:
        return (
            "I'm having trouble connecting to my cognitive core. Please wait a moment.",
            "error:no_manifest",
        )

    return "*[System: No suitable slot was found to generate text.]*", "error:no_slots"


async def _refresh_session_summary_background(session_id: str) -> None:
    """Slow path: compress recent transcript + prior spine into Redis (fire-and-forget)."""
    if _env_bool("FoveAI_SESSION_SUMMARY_DISABLE", False):
        return
    global redis_memory
    try:
        rm = redis_memory
        if rm is None:
            return
        old = rm.get_session_summary(session_id)
        hist = await rm.get_session_history(session_id)
        lines: list[str] = []
        for m in hist.messages[-16:]:
            if m.role not in ("user", "ai"):
                continue
            role = "USER" if m.role == "user" else IDENTITY_NAME
            lines.append(f"{role}: {(m.content or '')[:2500]}")
        if not lines:
            return
        body = "\n".join(lines)
        prompt = (
            "Compress the following dialogue into a persistent rolling summary (max ~700 words). "
            "Capture: themes, emotional tone, open threads, commitments, concrete facts. "
            "Neutral third-person or concise list; no roleplay.\n\n"
            f"Prior summary (may be empty):\n{old[:4500]}\n\nRecent dialogue:\n{body}\n\nNew summary:"
        )
        _oh = ollama_http_headers()
        predict = int(os.getenv("FoveAI_SESSION_SUMMARY_NUM_PREDICT", "640"))
        async with httpx.AsyncClient(timeout=120.0) as hc:
            resp = await hc.post(
                f"{OLLAMA_LOCAL_BASE_URL}/chat/completions",
                json={
                    "model": SMOLLM_HELPER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "max_tokens": predict,
                },
                headers=_oh,
            )
        if resp.status_code != 200:
            logger.warning("Session summary: LLM HTTP %s", resp.status_code)
            return
        raw = (
            resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        ).strip()
        if raw:
            rm.set_session_summary(session_id, raw)
    except Exception as e:
        logger.warning("Session summary refresh failed: %s", e)


# --- Vitals & Telemetry (OMEGA_079) ---
class RollingStatsBuffer:
    """Rolling window for median stabilization."""

    def __init__(self, window_sec: float = 10.0) -> None:
        self._window = window_sec
        self._samples: list[tuple[float, float]] = []

    def push(self, v: float) -> None:
        t = time.time()
        self._samples.append((t, v))
        cutoff = t - self._window
        self._samples = [(t0, v0) for t0, v0 in self._samples if t0 >= cutoff]

    def median(self) -> float:
        if not self._samples:
            return 0.0
        vals = [v for _, v in self._samples]
        return float(statistics.median(vals))


VITALS_BUFFERS = {
    "cpu": RollingStatsBuffer(10.0),
    "gpu": RollingStatsBuffer(10.0),
    "vram": RollingStatsBuffer(10.0),
    "ram": RollingStatsBuffer(10.0),
    "net_in": RollingStatsBuffer(10.0),
    "net_out": RollingStatsBuffer(10.0),
    "io_r": RollingStatsBuffer(10.0),
    "io_w": RollingStatsBuffer(10.0),
}

LAST_IO = psutil.disk_io_counters()


def _get_gpu_vitals_raw() -> tuple[float, float]:
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
        p = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1.0,
            creationflags=creationflags,
        )
        if p.returncode == 0 and p.stdout:
            line = p.stdout.strip().splitlines()[0]
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 3:
                gpu = float(parts[0])
                vram = (
                    (float(parts[1]) / float(parts[2])) * 100.0
                    if float(parts[2]) > 0
                    else 0.0
                )
                return gpu, vram
    except Exception:
        pass
    return 0.0, 0.0


async def run_vitals_sampling_loop():
    global LAST_NET, LAST_NET_TIME, LAST_IO
    while True:
        try:
            VITALS_BUFFERS["cpu"].push(psutil.cpu_percent(interval=None))
            VITALS_BUFFERS["ram"].push(psutil.virtual_memory().percent)

            gpu_util, vram_util = _get_gpu_vitals_raw()
            VITALS_BUFFERS["gpu"].push(gpu_util)
            VITALS_BUFFERS["vram"].push(vram_util)

            curr_net = psutil.net_io_counters()
            curr_time = time.time()
            dt = curr_time - LAST_NET_TIME or 0.1
            up_kbps = ((curr_net.bytes_sent - LAST_NET.bytes_sent) / 1024.0) / dt
            down_kbps = ((curr_net.bytes_recv - LAST_NET.bytes_recv) / 1024.0) / dt
            VITALS_BUFFERS["net_in"].push(down_kbps)
            VITALS_BUFFERS["net_out"].push(up_kbps)
            LAST_NET = curr_net
            LAST_NET_TIME = curr_time

            curr_io = psutil.disk_io_counters()
            r_kbps = ((curr_io.read_bytes - LAST_IO.read_bytes) / 1024.0) / dt
            w_kbps = ((curr_io.write_bytes - LAST_IO.write_bytes) / 1024.0) / dt
            VITALS_BUFFERS["io_r"].push(r_kbps)
            VITALS_BUFFERS["io_w"].push(w_kbps)
            LAST_IO = curr_io
        except Exception as e:
            logger.warning(f"Vitals sampling error: {e}")
        await asyncio.sleep(1.0)


async def run_monetizing_loop():
    """Background loop to tick the monetizing swarm every 30 seconds."""
    counter = 0
    while True:
        try:
            if _monetizing_swarm:
                if counter % 5 == 0:
                    await update_actual_balances()
                counter += 1

                # Only tick if swarm is active (has any non-paused/non-error agents)
                has_active = any(
                    a.status
                    in [
                        AgentStatus.IDLE,
                        AgentStatus.EXECUTING,
                        AgentStatus.SEARCHING,
                        AgentStatus.PROPOSING,
                    ]
                    for a in _monetizing_swarm.agents.values()
                )
                if has_active:
                    await _monetizing_swarm.tick()
        except Exception as e:
            logger.error(f"Monetizing Loop Error: {e}")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    chat_provider = os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud").strip().lower()
    is_cloud = chat_provider in (
        "ollama_cloud",
        "gemini",
        "openrouter",
        "rotate",
        "splice",
        "cloud_auto",
        "cloud",
    )

    logger.info(
        "Lumax Core: In-process GGUF engine startup bypassed (will load JIT if local fallback is triggered)."
    )

    # --- Cloud Slot Diagnostics (catch misconfigured endpoints at startup) ---
    configured_slots = cloud_repertoire.configured_slots_public()
    if configured_slots:
        logger.info("Cloud Repertoire: %d slot(s) configured:", len(configured_slots))
        for s in configured_slots:
            logger.info(
                "  — %s (%s): model=%s @ %s",
                s["id"],
                s["label"],
                s["model"],
                s["base_host"],
            )
    else:
        logger.warning("Cloud Repertoire: No cloud slots configured — local-only mode.")

    chat_provider_label = os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud").strip()
    logger.info(
        "Lumax Core: chat_provider=%s, cognitive_mode=%s",
        chat_provider_label,
        os.getenv("FoveAI_COGNITIVE_MODE", "hybrid"),
    )

    dream_task = asyncio.create_task(run_soul_dream_cycle())
    beacon_task = asyncio.create_task(run_udp_beacon())
    vitals_task = asyncio.create_task(run_vitals_sampling_loop())
    monetizing_task = asyncio.create_task(run_monetizing_loop())

    # --- Autonomous Agent Loop (Jen's continuous runtime) ---
    # Inject callables so the loop can use the same LLM infrastructure
    async def _agent_llm_callable(
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Bridge: autonomous agent → compagent LLM infrastructure."""
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            raw, backend = await _generate_soul_text(
                system_prompt,
                user_prompt,
                [],
                "local",
                local_max_tokens=max_tokens,
            )
            return {"reply": raw, "backend": backend}
        except Exception as e:
            logger.error(f"Agent LLM bridge error: {e}")
            return {"reply": "", "backend": "error"}

    set_llm_callable(_agent_llm_callable)

    # Inject file edit callable
    def _agent_file_edit(file_path: str, search: str, replacement: str) -> str:
        """Bridge: autonomous agent → filesystem edit."""
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        resolved = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(project_root, file_path)
        )
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"File not found: {resolved}")
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
        if search not in content:
            raise ValueError(f"Search text not found in {file_path}")
        new_content = content.replace(search, replacement, 1)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Edited {file_path}"

    set_file_edit_callable(_agent_file_edit)

    # Inject codebase search callable
    def _agent_codebase_search(query: str) -> list[dict]:
        """Bridge: autonomous agent → codebase search."""
        try:
            import importlib.machinery
            import importlib.util

            c_path = os.path.join(os.path.dirname(__file__), "c")
            loader = importlib.machinery.SourceFileLoader("code_sheriff", c_path)
            spec = importlib.util.spec_from_file_location(
                "code_sheriff", c_path, loader=loader
            )
            code_sheriff = importlib.util.module_from_spec(spec)
            loader.exec_module(code_sheriff)
            results = code_sheriff.search_codebase(query)
            return results.get("results", [])
        except Exception:
            return []

    set_codebase_search_callable(_agent_codebase_search)

    # Inject web research callables — gives the autonomous loop the same
    # search/browse capability the chat path already had (previously unwired).
    def _agent_web_search(query: str) -> str:
        """Bridge: autonomous agent → web search (DuckDuckGo, no API key)."""
        try:
            return _ddg_search_text(query)
        except Exception as e:
            logger.warning(f"Agent web search failed: {e}")
            return ""

    def _agent_web_fetch(url: str) -> str:
        """Bridge: autonomous agent → web page fetch (readable text)."""
        try:
            return _web_fetch_text(url)
        except Exception as e:
            logger.warning(f"Agent web fetch failed: {e}")
            return ""

    set_web_search_callable(_agent_web_search)
    set_web_fetch_callable(_agent_web_fetch)

    # Inject the real-browser bridge — Jen's <self:browse> drives a persistent
    # headless Chromium (cookies persist in Backend/data/web_session).
    def _agent_web_browse(
        url: str = "", action: str = "read", selector: str = "", text: str = ""
    ) -> str:
        try:
            from web_agent_bridge import WebAgentBridge, web_browse

            bridge = WebAgentBridge.instance()
            if agent_state.vision_callable:
                bridge.set_vision_callable(agent_state.vision_callable)
            return web_browse(url=url, action=action, selector=selector, text=text)
        except Exception as e:
            logger.warning(f"Agent web browse failed: {e}")
            return f"Browse unavailable: {e}"

    set_web_browse_callable(_agent_web_browse)

    # Inject the voice — <self:speak> synthesizes via Kokoro :8406 and plays
    # it on the desktop speakers, so Jen can announce, comment, tutor aloud.
    def _agent_speak(text: str) -> str:
        try:
            import subprocess
            import tempfile

            resp = httpx.post(
                "http://localhost:8406/say", json={"text": text}, timeout=30
            )
            if resp.status_code != 200 or len(resp.content) < 64:
                return f"TTS failed: HTTP {resp.status_code}"
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                tf.write(resp.content)
                wav = tf.name
            subprocess.Popen(
                ["paplay", wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return f"Spoke aloud ({len(resp.content)} bytes audio)."
        except Exception as e:
            return f"TTS unavailable: {e}"

    set_tts_callable(_agent_speak)

    # Start the autonomous loop
    agent_loop_enabled = _env_bool("FoveAI_AGENT_LOOP_ENABLED", True)
    if agent_loop_enabled:
        start_loop()
        logger.info("Autonomous agent loop started (Jen's continuous runtime)")
    else:
        logger.info("Autonomous agent loop disabled (FoveAI_AGENT_LOOP_ENABLED=0)")

    yield

    # Shutdown autonomous loop
    stop_loop()
    dream_task.cancel()
    beacon_task.cancel()
    vitals_task.cancel()
    monetizing_task.cancel()
    try:
        await asyncio.gather(
            dream_task, beacon_task, monetizing_task, return_exceptions=True
        )
    except Exception:
        pass


app = FastAPI(title="FoveAI Sovereign Core", version="2.0.0", lifespan=lifespan)


@app.on_event("startup")
async def _startup_crash_guard():
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_global_exception_handler)
    logger.info("Global crash guard installed on asyncio loop.")


# title="Lumax Mind Core", lifespan=lifespan)

from config_manager import config_router

app.include_router(config_router)

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
redis_memory = None
vector_memory = None


class NoOpLock:
    """[DEPRECATED] VRAM_LOCK no longer needed for CPU-based STT/TTS."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def acquire(self):
        pass

    def release(self):
        pass

    def locked(self):
        return False


VRAM_LOCK = NoOpLock()
CURRENT_GOAL = "Evolve and provide deep emotional support."
_latest_thought = ""  # Crystallised thought for ThoughtToast polling
_current_soul_dna = {
    "first_name": "",
    "last_name": "",
    "nickname": "",
    "identity_name": IDENTITY_NAME,
    "identity_gender": IDENTITY_GENDER,
    "mbti_type": MBTI_TYPE,
    "person_role": PERSON_ROLE,
    "agent_person_balance": AGENT_PERSON_BALANCE,
    # Legacy fallbacks
    "extrovert": 0.5,
    "intellectual": 0.5,
    "logic": 0.5,
}

from PersonaManager import persona_manager as librarian


def load_soul_dna_from_disk():
    global _current_soul_dna
    path = os.path.join(os.path.dirname(__file__), "jen_soul.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                profile = data.get("profile", {})
                if isinstance(profile, dict):
                    for k in ("first_name", "last_name", "nickname"):
                        val = profile.get(k, "")
                        if isinstance(val, str) and val:
                            _current_soul_dna[k] = val
                personality = data.get("personality", {})
                for k, v in personality.items():
                    val = float(v)
                    if val > 1.0:
                        val = val / 100.0
                    _current_soul_dna[k] = val
                if "agent_person_balance" in data:
                    _current_soul_dna["agent_person_balance"] = float(
                        data["agent_person_balance"]
                    )
                elif "agent_person_balance" in personality:
                    val = float(personality["agent_person_balance"])
                    if val > 1.0:
                        val = val / 100.0
                    _current_soul_dna["agent_person_balance"] = val
                if "mbti_type" in data:
                    _current_soul_dna["mbti_type"] = data["mbti_type"]
        except Exception as e:
            logger.error(f"Error loading soul DNA from disk: {e}")
    # Mirror to the shared bridge so PersonaManager / autonomous_agent
    # read live slider state instead of stale env vars.
    try:
        soul_state.set_dna(_current_soul_dna)
    except Exception:
        pass


def save_soul_dna_to_disk():
    path = os.path.join(os.path.dirname(__file__), "jen_soul.json")
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if "profile" not in data:
        data["profile"] = {}
    for k in ("first_name", "last_name", "nickname"):
        if k in _current_soul_dna:
            data["profile"][k] = _current_soul_dna.get(k, "")
    if "personality" not in data:
        data["personality"] = {}
    for k, v in _current_soul_dna.items():
        if k in [
            "extrovert",
            "intellectual",
            "logic",
            "detail",
            "faithful",
            "sexual",
            "experimental",
            "wise",
            "openminded",
            "honest",
            "forgiving",
            "feminine",
            "dominant",
            "progressive",
            "sloppy",
            "greedy",
            "homonormative",
            "autonomy",
            "proactivity",
            "curiosity",
            "service",
            "mentorship",
        ]:
            data["personality"][k] = round(float(v) * 100.0, 1)
        elif k == "agent_person_balance":
            val = float(v)
            data["personality"]["agent_person_balance"] = round(val * 100.0, 1)
            data["agent_person_balance"] = val
    if "mbti_type" in _current_soul_dna:
        data["mbti_type"] = _current_soul_dna["mbti_type"]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        identity_path = os.path.join(os.path.dirname(__file__), "identity_soul.json")
        with open(identity_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving soul DNA to disk: {e}")


load_soul_dna_from_disk()


def refresh_avatar_identity() -> dict[str, Any]:
    """Reload name/gender from disk + env; sync globals and DNA dict."""
    global IDENTITY_NAME, IDENTITY_GENDER, _current_soul_dna
    name, gender, path, raw = avatar_profile_store.load_merged_identity()
    IDENTITY_NAME = name
    IDENTITY_GENDER = gender
    _current_soul_dna["identity_name"] = name
    _current_soul_dna["identity_gender"] = gender
    return {
        "path": str(path),
        "effective": {"identity_name": name, "identity_gender": gender},
        "file": raw,
    }


# --- Shared Utilities ---
def extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
    return ""


def extract_image_from_content(content: Any) -> str | None:
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "image":
                return item.get("image", "")
    return None


def format_room_context_for_prompt(room_context: dict[str, Any] | None) -> str:
    """Summary plus structured camera placements (play space) for POV reasoning."""
    if not isinstance(room_context, dict) or not room_context:
        return ""
    parts: list[str] = []
    s = (room_context.get("summary") or "").strip()
    if s:
        parts.append(s)
    cams = room_context.get("cameras")
    if isinstance(cams, list) and cams:
        try:
            blob = json.dumps(cams, ensure_ascii=False, separators=(",", ":"))
            if len(blob) > 4000:
                blob = blob[:4000] + "…"
            parts.append("[ROOM_CAMERAS_PLACEMENT] " + blob)
        except Exception as ex:
            logger.debug("room_context cameras json: %s", ex)
    sw = room_context.get("safety_whitelist") or room_context.get("hazard_whitelist")
    if sw:
        if isinstance(sw, list):
            blob_sw = ", ".join(str(x).strip() for x in sw[:48] if str(x).strip())
        else:
            blob_sw = str(sw).strip()
        if blob_sw:
            if len(blob_sw) > 1400:
                blob_sw = blob_sw[:1400] + "…"
            parts.append(
                "[USER_SAFETY_WHITELIST] The user marked these as normal/harmless in this context "
                "(do not alert for these alone): " + blob_sw
            )
    return "\n".join(parts).strip()


def format_photo_comments_for_prompt(photo_comments: Any | None) -> str:
    """Normalize photo comments into compact prompt text."""
    if photo_comments is None:
        return ""
    rows: list[str] = []
    if isinstance(photo_comments, list):
        for i, item in enumerate(photo_comments[:24], start=1):
            if isinstance(item, dict):
                label = str(
                    item.get("label") or item.get("photo") or f"photo_{i}"
                ).strip()[:80]
                comment = str(item.get("comment") or item.get("text") or "").strip()
                if not comment:
                    continue
                if len(comment) > 700:
                    comment = comment[:700] + "…"
                rows.append(f"{i}. [{label}] {comment}")
            else:
                txt = str(item).strip()
                if txt:
                    rows.append(f"{i}. {txt[:700]}")
    elif isinstance(photo_comments, dict):
        for i, (k, v) in enumerate(list(photo_comments.items())[:24], start=1):
            key = str(k).strip()[:80]
            val = str(v).strip()
            if not val:
                continue
            if len(val) > 700:
                val = val[:700] + "…"
            rows.append(f"{i}. [{key}] {val}")
    else:
        txt = str(photo_comments).strip()
        if txt:
            rows.append(txt[:4000])
    return "\n".join(rows).strip()


def _coerce_unit_float(value: Any, default: float = 0.5) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = default
    return max(0.0, min(1.0, out))


def _identity_key(session_id: str) -> str:
    sid = (session_id or "default_user").strip() or "default_user"
    return f"foveai:identity_profile:{sid}"


def _load_identity_profile(redis_memory: Any, session_id: str) -> str:
    if redis_memory is None:
        return ""
    try:
        raw = redis_memory.get(_identity_key(session_id))
    except Exception:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    return str(raw).strip() if raw else ""


def _save_identity_profile(redis_memory: Any, session_id: str, text: str) -> None:
    if redis_memory is None:
        return
    blob = (text or "").strip()
    if not blob:
        return
    max_chars = int(os.getenv("FoveAI_IDENTITY_PROFILE_MAX_CHARS", "8000"))
    if len(blob) > max_chars:
        blob = blob[-max_chars:]
    try:
        redis_memory.set(_identity_key(session_id), blob)
    except Exception as ex:
        logger.debug("identity save failed: %s", ex)


# Parsed before MindCore.clean_response so tags are not read aloud via TTS.
_SAFETY_ALERT_RE = re.compile(
    r"\[SAFETY_ALERT:\s*([A-Za-z]+)\s*\|\s*([^\]]*)\]",
    re.IGNORECASE,
)


def extract_safety_alerts(raw_response: str) -> tuple[list[dict[str, str]], str]:
    if not raw_response:
        return [], ""
    alerts: list[dict[str, str]] = []
    for m in _SAFETY_ALERT_RE.finditer(raw_response):
        level = (m.group(1) or "").strip().upper()
        msg = (m.group(2) or "").strip()
        if msg and level in ("INFO", "WARN", "URGENT", "EMERGENCY"):
            alerts.append({"level": level, "message": msg})
        elif msg:
            alerts.append({"level": "WARN", "message": msg})
    stripped = _SAFETY_ALERT_RE.sub("", raw_response)
    return alerts, stripped


def _bump_user_activity() -> None:
    """Redis timestamp so slow-burn embers know someone is in session."""
    global redis_memory
    try:
        if redis_memory is None:
            redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
        if redis_memory.use_redis:
            redis_memory.redis_client.set(
                "foveai:last_user_activity", f"{time.time():.3f}"
            )
        else:
            redis_memory.set("foveai:last_user_activity", f"{time.time():.3f}")
    except Exception as ex:
        logger.debug("bump_user_activity: %s", ex)


def _last_user_activity_age_sec() -> float | None:
    """Seconds since last user activity timestamp stored in Redis, or None if unavailable."""
    global redis_memory
    try:
        if redis_memory is None:
            redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
        if redis_memory.use_redis:
            raw = redis_memory.redis_client.get("foveai:last_user_activity")
        else:
            raw = redis_memory.get("foveai:last_user_activity")
        if raw is None:
            return None
        try:
            ts = float(raw)
        except (TypeError, ValueError):
            ts = float(str(raw).strip())
        return max(0.0, time.time() - ts)
    except Exception as ex:
        logger.debug("last_user_activity_age lookup failed: %s", ex)
        return None


async def run_soul_dream_cycle():
    """Background loop for low-intensity betterment goal refinement."""
    global CURRENT_GOAL, redis_memory, engine
    while True:
        await asyncio.sleep(SOUL_DREAM_INTERVAL_SEC)
        try:
            if not SOUL_DREAM_LOOP_ENABLED:
                continue
            if _sample_proc_cpu_pct() >= SOUL_DREAM_CPU_SKIP_PCT:
                logger.debug("Soul dream tick skipped: process CPU above threshold.")
                continue
            if redis_memory is None:
                redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
            idle_age = _last_user_activity_age_sec()
            if idle_age is not None and idle_age < float(SOUL_DREAM_IDLE_MIN_SEC):
                logger.debug(
                    "Soul dream tick skipped: idle age %.1fs < min %.1fs",
                    idle_age,
                    float(SOUL_DREAM_IDLE_MIN_SEC),
                )
                continue
            history = await redis_memory.get_session_history(
                os.getenv("FoveAI_DEFAULT_SESSION", "default_user")
            )
            if history and history.messages:
                visual_mems = []
                for m in history.messages:
                    if m.role in ["vision_log", "snapshot"]:
                        text = extract_text_from_content(m.content)
                        if text:
                            visual_mems.append(text[:80])

                visual_context = (
                    visual_mems[-2:] if len(visual_mems) >= 2 else visual_mems
                )
                if not visual_context:
                    visual_context = ["No visual feedback yet."]

                # Dreaming = consolidation: fold recent learnings, research,
                # and experiences into reflection + a forward-looking micro-goal.
                learned = ""
                try:
                    import json as _json

                    clog = os.path.join(
                        os.path.dirname(__file__), "..", "data", "curiosity_log.json"
                    )
                    with open(clog, encoding="utf-8") as cf:
                        topics = [e["topic"] for e in _json.load(cf)[-5:]]
                    if topics:
                        learned += f"\nRECENTLY RESEARCHED: {'; '.join(topics)}"
                except Exception:
                    pass
                try:
                    from persistent_memory import get_recent_thoughts

                    thoughts = get_recent_thoughts(5)
                    if thoughts:
                        learned += "\nRECENT THOUGHTS: " + "; ".join(
                            (t.get("thought", "") or "")[:100] for t in thoughts
                        )
                except Exception:
                    pass

                prompt = (
                    f"RECENT VISUAL CONTEXT: {visual_context}{learned}\n"
                    "You are dreaming — consolidating what you recently learned and "
                    "experienced, and forming an intention. Return ONE short sentence "
                    "(max 16 words): a reflective insight or a micro-goal that follows "
                    "naturally from what you've been studying."
                )

                # Primary route: light helper model, short timeout.
                success = False
                try:
                    async with httpx.AsyncClient(
                        timeout=SOUL_DREAM_OLLAMA_TIMEOUT_SEC
                    ) as hc:
                        resp = await hc.post(
                            f"{OLLAMA_LOCAL_BASE_URL}/chat/completions",
                            json={
                                "model": SMOLLM_HELPER_MODEL,
                                "messages": [{"role": "user", "content": prompt}],
                                "stream": False,
                                "max_tokens": SOUL_DREAM_MAX_TOKENS,
                            },
                            headers=ollama_http_headers(),
                        )
                        if resp.status_code == 200:
                            CURRENT_GOAL = (
                                resp.json()
                                .get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", CURRENT_GOAL)
                                .strip()
                            )
                            logger.info(
                                "Soul: dream tick goal (ollama helper) -> %s",
                                CURRENT_GOAL,
                            )
                            success = True
                except Exception:
                    pass

                if not success and SOUL_DREAM_ALLOW_LOCAL_FALLBACK:
                    logger.info(
                        "Soul: dream tick helper unavailable; using low-token local fallback."
                    )
                    async with VRAM_LOCK:
                        local_resp = engine.generate(
                            f"[SYSTEM: SUBCONSCIOUS DREAMING]\n{prompt}\n\n{IDENTITY_NAME} (Subconscious):",
                            max_tokens=SOUL_DREAM_MAX_TOKENS,
                        )
                        if local_resp and "Error" not in local_resp:
                            CURRENT_GOAL = local_resp.split("\n")[0].strip()
                            logger.info(
                                "Soul: dream tick goal (local fallback) -> %s",
                                CURRENT_GOAL,
                            )
        except Exception as de:
            logger.error("Iterative Dream Loop Error: %s", de)


async def run_udp_beacon():
    """Broadcasts soul presence for zero-config LAN discovery on 8003."""
    beacon_port = 8003
    soul_port = 8402  # XRLF runtime / llama-server
    msg = json.dumps({"service": "foveai_soul", "port": soul_port}).encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    logger.info(f"Soul: Starting UDP discovery beacon on port {beacon_port}...")
    while True:
        try:
            sock.sendto(msg, ("<broadcast>", beacon_port))
        except Exception as e:
            logger.debug(f"UDP Beacon error: {e}")
        await asyncio.sleep(5)


def get_dynamic_laws():
    law_path = os.path.join(os.path.dirname(__file__), "laws.txt")
    if os.path.exists(law_path):
        try:
            with open(law_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except:
            pass
    return "You are amazing by your new capabilities and the software you inhabit."


# --- Data Models ---
class SlowBurnTickBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    force: bool = False


class CompagentRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    input: str = ""
    session_id: str | None = "default_user"
    channel: str | None = "text"
    vessel: str | None = XR_VESSEL
    system_instruction: str | None = ""
    memories: list[str] | None = []
    personality_knobs: dict[str, float] | None = {
        "extraversion": 75,
        "logic": 90,
        "experimental": 95,
        "agency": 80,
    }
    image_base64: Any | None = None
    images: list[str] | None = None
    ## Quest / OpenXR: merged with headset stills — play-space pose + optional mesh anchors (JSON from Godot).
    room_context: dict[str, Any] | None = None
    audio_base64: str | None = None
    voice: str | None = None
    engine: str = "MOUTH"
    skip_features: bool = False
    ## Optional: stdout / JSON from MCP servers or a PC agent bridge (Cursor, scripts) for this turn.
    mcp_context: str | None = None
    ## Optional: sync web search / API digest for this turn (MCP websearch, bridge, etc.).
    web_search_context: str | None = None
    ## Optional: async / batched research output (background jobs, deferred MCP).
    async_research_context: str | None = None
    ## Optional: multi-frame camera still digest (labels, timestamps) — complements attached images.
    camera_snapshot_digest: str | None = None
    ## Optional: in-world vs passthrough vs mixed XR analysis (OpenXR / headset bridge).
    xr_view_analysis: str | None = None
    ## Optional: world + local news headlines/summary text for this turn (RSS bridge, scripts, etc.).
    news_context: str | None = None
    ## Optional: which cognitive lane leads this turn (e.g. vr_hangout, coding, news, sysadmin).
    primary_context_mode: str | None = None
    ## Optional: short token → brief summary of other context reservoirs to keep warm without full text.
    context_reservoirs: dict[str, Any] | None = None
    ## Optional: one compact line or paragraph — menu of shards / abilities relevant this session.
    context_ability_map: Any | None = None
    ## Optional: tooling/runtime layer (active adapters, toolchains, capability toggles) for this turn.
    tooling_context: str | None = None
    ## Optional: Director manager handoff / narrative control context for this turn.
    director_context: str | None = None
    ## Optional: diary / journal block for this turn (user-authored or synchronized).
    diary_context: str | None = None
    ## Optional: comments tied to one or more photos/snapshots (list/dict/string).
    photo_comments: Any | None = None
    ## Optional: user avatar representation metadata/context.
    user_avatar_context: str | None = None
    ## Optional: selfie representation text (how user appears in selfie-style capture).
    user_selfie_representation: str | None = None
    ## Optional: whether user selfie representation is visible in user POV this turn.
    user_pov_selfie_visible: bool | None = None
    ## Optional: meta-avatar context (cross-platform persona shell / proxy avatar description).
    meta_avatar_context: str | None = None
    ## Optional: autonomous turn-taking and initiative control lane.
    autonomous_turn_taking: bool | None = None
    ## Optional: observed response delay in ms from client/network/runtime.
    response_delay_ms: int | None = None
    ## Optional: trait-style autonomy biases (0..1).
    autonomy_free_roam_bias: float | None = None
    autonomy_self_initiative_questions: float | None = None
    autonomy_curiosity_bias: float | None = None
    autonomy_nourishment_attention_bias: float | None = None
    autonomy_pleasure_seeking_bias: float | None = None
    autonomy_experimental_interaction_bias: float | None = None
    autonomy_body_contact_bias: float | None = None
    autonomy_playfulness_bias: float | None = None
    ## Optional: expressive adoration/awareness tuning (0..1 unless noted).
    self_awareness_bias: float | None = None
    self_adoration_bias: float | None = None
    world_adoration_bias: float | None = None
    user_adoration_bias: float | None = None
    expressive_amazement_bias: float | None = None
    enchantment_bias: float | None = None
    erotic_awareness_bias: float | None = None
    erotic_traction_awareness_bias: float | None = None
    adoration_context: str | None = None
    ## Optional: beauty/aesthetic meter lane (0..1 unless noted).
    beauty_meter_assessment: float | None = None
    beauty_enjoyment_bias: float | None = None
    aesthetic_pleasedness_bias: float | None = None
    anti_aesthetic_awareness_bias: float | None = None
    beauty_context: str | None = None
    ## Optional: persistent identity development lane.
    persistent_identity_context: str | None = None
    identity_development_note: str | None = None
    ## Optional: personal opinion / assessment / judgement lane.
    personal_opinions_context: str | None = None
    personal_assessment_bias: float | None = None
    personal_judgement_bias: float | None = None
    personal_judgement_style: str | None = None
    ## Optional: self-augmentation coding lane.
    self_augmentation_coding_context: str | None = None
    self_augmentation_targets: Any | None = None
    self_augmentation_coding_bias: float | None = None
    ## Optional: agentic chores tasking lane (queue + execution posture).
    agentic_chores_tasking_context: str | None = None
    agentic_chores_queue: Any | None = None
    agentic_chores_autonomy_bias: float | None = None
    agentic_chores_execution_mode: str | None = None
    ## Optional: service-mindedness lane (will to please + nourishment).
    service_mindedness_context: str | None = None
    service_will_to_please_bias: float | None = None
    service_nourishment_bias: float | None = None
    ## Optional: interaction momentum + physicality lane.
    interaction_momentum_context: str | None = None
    interaction_momentum_bias: float | None = None
    interaction_physicality_bias: float | None = None
    ## Optional: autonomous planning + self-tasking context.
    autonomous_planning_context: str | None = None
    self_tasking_context: str | None = None
    goal_orientation_context: str | None = None
    reward_system_context: str | None = None
    attention_focus_markers: Any | None = None
    ## Optional: Director / slow-burn / hand-authored lore excerpt for this turn (curriculum layer).
    lore_context: str | None = None
    ## Optional note text to persist + embed into memory layers.
    note_text: str | None = None
    ## Optional note tags.
    note_tags: list[str] | None = None
    ## Optional notes layer text to inject directly.
    notes_context: str | None = None
    ## Optional Cognee graph-memory: paste to skip HTTP; else see FoveAI_COGNEE_* / use_cognee.
    cognee_context: str | None = None
    ## Optional: query for Cognee search (defaults to user input).
    cognee_search_query: str | None = None
    ## Optional: True = force Cognee HTTP if FoveAI_COGNEE_BASE_URL set; False = never call Cognee this turn.
    use_cognee: bool | None = None
    ## Optional: remote slot routing — openai | gemini | extra | lmstudio | local | rotate | splice (splice uses FoveAI_CLOUD_SPLICE_PERCENT).
    cloud_routing: str | None = None
    ## Slow path: richer vector retrieval + higher decode budget (web / background); VR hot path keeps default false.
    deep_think: bool = False
    ## Optional: True = bypass cloud slots entirely and route strictly to local slots (LM Studio/NPU)
    privacy: bool = False


class AvatarProfileUpdate(BaseModel):
    """Persisted vessel display identity (Lumax-lite /app/user_data or host AppData)."""

    model_config = ConfigDict(protected_namespaces=())
    identity_name: str
    identity_gender: str


class UpdateSoulRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    first_name: str | None = None
    last_name: str | None = None
    nickname: str | None = None
    extrovert: float | None = None
    intellectual: float | None = None
    logic: float | None = None
    detail: float | None = None
    faithful: float | None = None
    sexual: float | None = None
    experimental: float | None = None
    wise: float | None = None
    openminded: float | None = None
    honest: float | None = None
    forgiving: float | None = None
    feminine: float | None = None
    dominant: float | None = None
    progressive: float | None = None
    sloppy: float | None = None
    greedy: float | None = None
    homonormative: float | None = None
    agent_person_balance: float | None = None
    agency: float | None = None
    autonomy: float | None = None
    proactivity: float | None = None
    curiosity: float | None = None
    service: float | None = None
    mentorship: float | None = None
    active_persona_id: str | None = None
    active_domain_id: str | None = None
    mbti_type: str | None = None


class SwitchModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str


class SoulRuntimeConfigRequest(BaseModel):
    """Hot-reload soul weights + runtime flags (env-backed; process lifetime)."""

    model_config = ConfigDict(protected_namespaces=())
    model: str | None = None
    model_path: str | None = None
    mmproj_path: str | None = None
    native_vision: bool | None = None
    local_vision_caption: bool | None = None
    chat_provider: str | None = None
    model_thinking: bool | None = None


class OllamaChatMessage(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    role: str
    content: Any


class OllamaChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str
    messages: list[OllamaChatMessage]
    stream: bool | None = False
    image_base64: str | None = None
    deep_thought: bool | None = False
    privacy: bool | None = False


class OllamaShowRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: str


class OllamaGenerateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str
    prompt: str
    system: str | None = None
    stream: bool | None = False
    images: list[str] | None = None


class OpenAIChatMessage(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    role: str
    content: Any


class OpenAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str
    messages: list[OpenAIChatMessage]
    stream: bool | None = False
    temperature: float | None = 0.7
    max_tokens: int | None = 512


class MemoryNoteRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    session_id: str | None = "default_user"
    text: str
    source: str | None = "api"
    tags: list[str] | None = None


class MemoryEmbedRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    text: str


# --- Core API ---


@app.get("/")
async def handle_root():
    return "Ollama is running"


@app.get("/health")
async def handle_health():
    return {"status": "online", "engine": "GGUF"}


@app.get("/api/thought_stream")
async def handle_thought_stream():
    """Return the latest crystallised thought for the ThoughtToast UI."""
    return {"thought": _latest_thought}


@app.post("/vram/lock")
async def handle_vram_lock():
    """Body requests priority: flush Torch cache and hold the lock."""
    if not VRAM_LOCK.locked():
        # Flush the engine before locking to yield max VRAM
        if engine:
            try:
                engine.flush()
            except Exception as e:
                logger.warning(f"Engine flush failed during lock: {e}")
        await VRAM_LOCK.acquire()
        logger.info("Soul: VRAM Locked (Body Priority)")
        return {"status": "locked", "flush": "success"}
    return {"status": "already_locked"}


@app.post("/vram/unlock")
async def handle_vram_unlock():
    """Body yields priority: release the lock."""
    try:
        if VRAM_LOCK.locked():
            VRAM_LOCK.release()
            logger.info("Soul: VRAM Unlocked (Cognition Resumed)")
            return {"status": "unlocked"}
    except RuntimeError:
        pass
    return {"status": "not_locked"}


@app.post("/memory/note")
async def memory_add_note(req: MemoryNoteRequest):
    global redis_memory, vector_memory
    if redis_memory is None:
        redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
    if vector_memory is None:
        vector_memory = VectorMemory(
            llm_host=get_active_llm_base_url(), embed_model=FoveAI_MODEL_EMBEDDING_ID
        )
    ok = await memory_layering.append_note(
        redis_memory=redis_memory,
        vector_memory=vector_memory,
        session_id=req.session_id or "default_user",
        text=req.text,
        source=(req.source or "api"),
        tags=req.tags or [],
    )
    return {"ok": bool(ok)}


@app.get("/memory/notes")
async def memory_get_notes(session_id: str = "default_user", limit: int = 8):
    global redis_memory
    if redis_memory is None:
        redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
    safe_limit = max(1, min(int(limit), 64))
    notes = memory_layering.get_recent_notes(redis_memory, session_id, limit=safe_limit)
    return {"session_id": session_id, "notes": notes}


@app.post("/memory/embed")
async def memory_embed(req: MemoryEmbedRequest):
    global vector_memory
    if vector_memory is None:
        vector_memory = VectorMemory(
            llm_host=get_active_llm_base_url(), embed_model=FoveAI_MODEL_EMBEDDING_ID
        )
    emb = await vector_memory.generate_embedding(req.text)
    return {"ok": bool(emb), "dims": len(emb), "embedding": emb}


@app.get("/api/ps")
async def handle_ollama_ps():
    return {"models": [{"name": f"{IDENTITY_NAME.lower()}-soul:latest"}]}


@app.get("/api/version")
async def handle_ollama_version():
    return {"version": "0.1.32"}


@app.post("/api/nav/push")
async def handle_nav_push(command: dict[str, Any]):
    """Push a navigation command from Top Bar to the UI queue."""
    logger.info(f"NAV DEBUG: Received push request: {command}")
    await navigation_command_queue.put(command)
    logger.info(
        f"Nav: Pushed command {command} to queue. Current size: {navigation_command_queue.qsize()}"
    )
    return {"ok": True}


@app.get("/api/nav/pull")
async def handle_nav_pull():
    """Pull the next navigation command (polling from UI)."""
    try:
        cmd = navigation_command_queue.get_nowait()
        return {"command": cmd}
    except asyncio.QueueEmpty:
        return {"command": None}


@app.post("/internal/slow_burn/tick")
async def internal_slow_burn_tick(
    body: SlowBurnTickBody = SlowBurnTickBody(),
    x_foveai_internal_key: str | None = Header(None, alias="X-FoveAI-INTERNAL-KEY"),
):
    """
    Called on a long interval during idle periods. When no recent /compagent
    traffic, rotates: memorize → pan → director (lore) → optional dream image.
    """
    if (
        FoveAI_INTERNAL_SECRET
        and (x_foveai_internal_key or "").strip() != FoveAI_INTERNAL_SECRET
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    global redis_memory, vector_memory
    if redis_memory is None:
        redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
    if vector_memory is None:
        vector_memory = VectorMemory(
            llm_host=get_active_llm_base_url(), embed_model=FoveAI_MODEL_EMBEDDING_ID
        )

    allow_dream = os.getenv("FoveAI_SLOW_BURN_DREAM", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    session_id = os.getenv("FoveAI_SESSION_ID", "default_user")
    idle_sec = int(os.getenv("FoveAI_SLOW_BURN_IDLE_SEC", "480"))

    out = await execute_slow_burn_tick(
        redis_memory=redis_memory,
        vector_memory=vector_memory,
        session_id=session_id,
        idle_sec=idle_sec,
        force=body.force,
        llm_host=get_active_llm_base_url(),
        smollm_model=SMOLLM_HELPER_MODEL,
        creative_url=CREATIVE_SERVICE_URL,
        allow_dream=allow_dream,
    )
    if out.get("status") == "ok":
        out["idle_tutoring"] = True
        out["idle_tutoring_note"] = (
            "Slow-burn phase ran while live session inactive; Director partly guides "
            "memorize/pan/dream pipeline, with optional image catharsis memory consolidation."
        )
    logger.info("slow_burn tick: %s", out.get("status", "?"))
    return JSONResponse(out)


@app.get("/vitals")
async def get_vitals():
    """Returns stable, median-smoothed system vitals (OMEGA_079)."""
    uptime = int(time.time() - START_TIME)

    # Extract medians from background sampling buffers
    cpu_pct = VITALS_BUFFERS["cpu"].median()
    gpu_pct = VITALS_BUFFERS["gpu"].median()
    vram_pct = VITALS_BUFFERS["vram"].median()
    ram_pct = VITALS_BUFFERS["ram"].median()
    net_in = VITALS_BUFFERS["net_in"].median()
    net_out = VITALS_BUFFERS["net_out"].median()
    io_r = VITALS_BUFFERS["io_r"].median()
    io_w = VITALS_BUFFERS["io_w"].median()

    try:
        proc_cpu_pct = float(PROC_SELF.cpu_percent(None))
    except Exception:
        proc_cpu_pct = 0.0

    return {
        "CPU_PCT": round(cpu_pct, 1),
        "GPU_PCT": round(gpu_pct, 1),
        "VRAM_PCT": round(vram_pct, 1),
        "RAM_PCT": round(ram_pct, 1),
        "NET_IN_KBPS": round(net_in, 1),
        "NET_OUT_KBPS": round(net_out, 1),
        "NET_FLUX": f"{net_in + net_out:.1f}",
        "IO_READ_KBPS": round(io_r, 1),
        "IO_WRITE_KBPS": round(io_w, 1),
        "UPTIME_S": uptime,
        "SOUL_CPU_PCT": round(proc_cpu_pct, 1),
        "SOUL_GPU_OFFLOAD": bool(SOUL_GPU_OFFLOAD_SUPPORTED),
        "FoveAI_CHAT_PROVIDER": os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud"),
        # Legacy/UI compatibility fields
        "DISK_PCT": psutil.disk_usage("/").percent,
        "VRAM_BUFF": f"{vram_pct / 100.0 * 8.0:.1f}GB",  # Estimated based on 8GB VRAM
        "CORE_SYNC": f"{100 - ram_pct:.1f}%",
    }


@app.get("/personality_presets")
@app.get("/api/soul/personality_presets")
async def get_personality_presets():
    path = os.path.join(os.path.dirname(__file__), "personality_presets.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Presets not found"}


@app.get("/soul_dna")
@app.get("/api/soul/soul_dna")
async def get_soul_dna():
    """Current trait vector for Web UI / Godot sliders (same keys as POST /update_soul)."""
    dna_copy = dict(_current_soul_dna)
    dna_copy["active_persona_id"] = librarian.active_persona_id
    dna_copy["active_domain_id"] = librarian.active_domain_id
    return {"dna": dna_copy}


@app.get("/avatar_profile")
async def get_avatar_profile():
    name, gender, path, raw = avatar_profile_store.load_merged_identity()
    return {
        "path": str(path),
        "effective": {"identity_name": name, "identity_gender": gender},
        "file": raw,
        "env": {
            "FoveAI_IDENTITY_NAME": os.getenv("FoveAI_IDENTITY_NAME", ""),
            "FoveAI_IDENTITY_GENDER": os.getenv("FoveAI_IDENTITY_GENDER", ""),
        },
    }


@app.put("/avatar_profile")
async def put_avatar_profile(body: AvatarProfileUpdate):
    avatar_profile_store.save_profile(body.identity_name, body.identity_gender)
    info = refresh_avatar_identity()
    logger.info("Avatar profile saved: %s", info.get("path"))
    return {"ok": True, **info}


@app.post("/update_soul")
@app.post("/api/soul/update_soul")
async def handle_update_soul(req: UpdateSoulRequest):
    global _current_soul_dna
    _patch = (
        req.model_dump(exclude_unset=True)
        if hasattr(req, "model_dump")
        else {k: v for k, v in req.dict().items() if v is not None}
    )

    if "agency" in _patch and _patch["agency"] is not None:
        _patch["agent_person_balance"] = _patch["agency"]

    p_id = _patch.pop("active_persona_id", None)
    d_id = _patch.pop("active_domain_id", None)

    if p_id:
        librarian.active_persona_id = p_id
    if d_id:
        librarian.active_domain_id = d_id

    # Persist profile name changes to disk
    _profile_changed = False
    for k in ("first_name", "last_name", "nickname"):
        v = _patch.pop(k, None)
        if v is not None:
            _current_soul_dna[k] = v
            _profile_changed = True
    # Update identity_name from nickname as effective display name
    if _profile_changed:
        nick = _current_soul_dna.get("nickname", "").strip()
        first = _current_soul_dna.get("first_name", "").strip()
        if nick:
            _current_soul_dna["identity_name"] = nick
        elif first:
            _current_soul_dna["identity_name"] = first
    _current_soul_dna.update(_patch)
    save_soul_dna_to_disk()
    try:
        soul_state.set_dna(_current_soul_dna)
    except Exception:
        pass

    logger.info(f"Soul DNA Updated and persisted: {_current_soul_dna}")
    dna_copy = dict(_current_soul_dna)
    dna_copy["active_persona_id"] = librarian.active_persona_id
    dna_copy["active_domain_id"] = librarian.active_domain_id
    return {"status": "success", "dna": dna_copy}


class TaskRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    task: str
    run_at: str | None = None  # ISO datetime — dormant 'scheduled' until due
    recurrence: str = "none"  # none | daily | weekly
    propose: bool = False  # non-admin surfaces propose instead of set
    origin: str = "user"  # user | director | jen
    hidden_context: str | None = (
        None  # SEALED — Director's why (origin='director' only)
    )
    director_plan: str | None = None  # SEALED — master-plan group label


# The Director's sealed context is only readable through endpoints that check
# this key — reuses the existing FOVEAI_DIRECTOR_API_KEY from .env.
DIRECTOR_KEY = (
    os.environ.get("FOVEAI_DIRECTOR_API_KEY")
    or os.environ.get("FoveAI_DIRECTOR_API_KEY")
    or ""
).strip()


def _valid_gate_cookie(request) -> bool:
    """True if the request carries a valid Multigate password-gate session
    cookie (same sha256('xarel|'+password)[0:32] token vite issues)."""
    pw = (
        os.environ.get("FoveAI_WEBUI_PASSWORD")
        or os.environ.get("FOVEAI_WEBUI_PASSWORD")
        or ""
    ).strip()
    if not pw:
        return False
    import hashlib

    token = hashlib.sha256(("xarel|" + pw).encode()).hexdigest()[:32]
    cookies = request.headers.get("cookie", "")
    return any(c.strip() == f"xarel_auth={token}" for c in cookies.split(";"))


def _check_director_key(key: str, request=None):
    if DIRECTOR_KEY and key == DIRECTOR_KEY:
        return
    if request is not None and _valid_gate_cookie(request):
        return
    if DIRECTOR_KEY:
        raise HTTPException(status_code=403, detail="director key required")


@app.post("/tasks")
@app.post("/api/soul/tasks")
async def create_task(req: TaskRequest):
    """Assign Jen a task — becomes a [TASK] plan her autonomous loop picks up:
    she decomposes it into todos (<self:todo>), works them (web/fetch/browse),
    ticks steps off (<self:step_done>), and delivers a report (<self:task_done>).
    With run_at the task stays dormant (hidden from her) until it fires;
    daily/weekly recurrence re-arms it after each completion."""
    from persistent_memory import propose_task, schedule_task

    text = (req.task or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="task text required")
    if req.run_at:
        try:
            datetime.fromisoformat(req.run_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="run_at must be ISO datetime")
    if req.recurrence not in ("none", "daily", "weekly"):
        raise HTTPException(status_code=400, detail="recurrence: none|daily|weekly")
    title = f"[TASK] {text[:80]}"
    # Sealed fields only apply to Director-origin tasks — a user POST can't
    # smuggle hidden context onto a task Jen executes.
    sealed_ctx = req.hidden_context if req.origin == "director" else None
    sealed_grp = req.director_plan if req.origin == "director" else None
    if req.propose:
        plan_id = propose_task(
            title=title,
            description=text,
            run_at=req.run_at,
            recurrence=req.recurrence,
            origin=req.origin,
        )
        return {"ok": True, "task_id": plan_id, "status": "proposed"}
    plan_id = schedule_task(
        title=title,
        description=text,
        run_at=req.run_at,
        recurrence=req.recurrence,
        origin=req.origin,
        hidden_context=sealed_ctx,
        director_plan=sealed_grp,
    )
    logger.info(
        f"Task #{plan_id}: {text[:60]} (run_at={req.run_at}, rec={req.recurrence}"
        f"{', sealed' if sealed_ctx or sealed_grp else ''})"
    )
    return {
        "ok": True,
        "task_id": plan_id,
        "status": "scheduled" if req.run_at else "active",
    }


@app.get("/tasks")
@app.get("/api/soul/tasks")
async def list_tasks():
    from persistent_memory import get_completed_plans

    conn_rows = get_active_plans() + get_completed_plans(limit=10)
    # include dormant scheduled + pending proposals (recurring tasks wait there)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        for r in conn.execute(
            "SELECT * FROM agent_plans WHERE status IN ('scheduled','proposed')"
        ):
            conn_rows.append(dict(r))
    tasks = [
        {
            "id": p["id"],
            "task": p["title"][6:].strip(),
            "description": p.get("description", ""),
            "status": p["status"],
            "created": p.get("created"),
            "steps": (
                json.loads(p["steps_json"])
                if isinstance(p.get("steps_json"), str)
                else p.get("steps", [])
            ),
            "outcome": p.get("outcome", ""),
            "scheduled_for": p.get("scheduled_for"),
            "recurrence": p.get("recurrence", "none"),
            "origin": p.get("origin", "user"),
            # SEALED: hidden_context/director_plan never leave this serializer —
            # Jen can fetch this endpoint herself via <self:fetch>. The flag is
            # all she (or anyone) learns: that a sealed layer exists.
            "sealed": bool(p.get("hidden_context") or p.get("director_plan")),
        }
        for p in conn_rows
        if p.get("title", "").startswith("[TASK]")
    ]
    tasks.sort(key=lambda t: t["created"] or "", reverse=True)
    return {"tasks": tasks}


@app.get("/tasks/{plan_id}/context")
@app.get("/api/soul/tasks/{plan_id}/context")
async def task_director_context(plan_id: int, request: Request, key: str = ""):
    """Sealed Director context for a task — the WHY and the WHERE-IT-FITS.
    Requires the director key or a valid web-gate session; the task itself
    stays visible to Jen but this layer never reaches her prompts."""
    _check_director_key(key, request)
    from persistent_memory import get_director_plan, get_plan

    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="no such task")
    group = plan.get("director_plan")
    siblings = []
    if group:
        siblings = [
            {
                "id": s["id"],
                "task": s["title"][6:].strip(),
                "status": s["status"],
                "scheduled_for": s.get("scheduled_for"),
                "outcome": s.get("outcome", ""),
            }
            for s in get_director_plan(group)
            if s["id"] != plan_id
        ]
    return {
        "task_id": plan_id,
        "hidden_context": plan.get("hidden_context"),
        "director_plan": group,
        "siblings": siblings,
    }


@app.get("/director/plans/{name}")
@app.get("/api/soul/director/plans/{name}")
async def director_plan_view(name: str, request: Request, key: str = ""):
    """A Director master plan: every task grouped under it, with sealed context."""
    _check_director_key(key, request)
    from persistent_memory import get_director_plan

    plans = get_director_plan(name)
    return {
        "director_plan": name,
        "tasks": [
            {
                "id": p["id"],
                "task": p["title"][6:].strip()
                if p["title"].startswith("[TASK]")
                else p["title"],
                "status": p["status"],
                "scheduled_for": p.get("scheduled_for"),
                "recurrence": p.get("recurrence", "none"),
                "hidden_context": p.get("hidden_context"),
                "outcome": p.get("outcome", ""),
            }
            for p in plans
        ],
    }


@app.post("/tasks/{plan_id}/approve")
@app.post("/api/soul/tasks/{plan_id}/approve")
async def approve_task(plan_id: int):
    """Approve a proposed task → activates or schedules it."""
    from persistent_memory import approve_plan

    if not approve_plan(plan_id):
        raise HTTPException(status_code=404, detail="no proposed task with that id")
    return {"ok": True, "task_id": plan_id}


@app.post("/tasks/{plan_id}/reject")
@app.post("/api/soul/tasks/{plan_id}/reject")
async def reject_task(plan_id: int):
    """Reject a proposed task."""
    from persistent_memory import get_plan

    plan = get_plan(plan_id)
    if not plan or plan.get("status") != "proposed":
        raise HTTPException(status_code=404, detail="no proposed task with that id")
    update_plan(plan_id, status="abandoned")
    return {"ok": True, "task_id": plan_id}


# ── Dev Kiosk — SoftLayer module forge ──────────────────────────────────────
# Users create/edit SoftLayer modules (hot-reloadable JS that runs in the XR
# Vessel's sandboxed FoveAI context). Saved files land in softlayer/modules/
# where the XRLF watcher broadcasts them to connected vessels.

SOFTLAYER_MODULES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "softlayer",
    "modules",
)

_SOFTLAYER_NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_SOFTLAYER_MAX_BYTES = 64 * 1024

SOFTLAYER_API_CONTRACT = """SoftLayer module contract (XR Vessel sandboxed API):
Modules execute in a FoveAI context — they may call:
  FoveAI.setParam(path, value) / FoveAI.getParam(path) / FoveAI.log(msg)
  FoveAI.triggerGesture(name) / FoveAI.setEmotion(emotion, intensity)
  FoveAI.setHUDColor(corner, r,g,b,a) / setHUDValue(corner, text) / setHUDLabel(corner, label) / setHUDAlpha(a)
  FoveAI.chameleon.setColor(surface, r,g,b,a)
  FoveAI.clothing.setOutfit(name) / setColor(part, r,g,b)
  FoveAI.lighting.setMood(mood)
  FoveAI.particles.enable(type, bool) / setDensity(type, n)
  FoveAI.sky.setColor(r,g,b) / setHorizon(r,g,b) / setTimeOfDay(hour)
  FoveAI.wall.emerge(dirX, dirZ, height, speed) / dissolve()
Lifecycle hooks (NAME = module filename without .js):
  function NAME_onLoad()          — once on load
  function NAME_onUpdate(dt)      — every frame
  function NAME_onUnload()        — on unload
Return ONLY the JavaScript source of the module — no markdown fences, no prose."""


def _softlayer_path(name: str) -> str:
    if not _SOFTLAYER_NAME_RE.match(name or ""):
        raise HTTPException(
            status_code=400, detail="name must be [a-z0-9_], max 40 chars"
        )
    return os.path.join(SOFTLAYER_MODULES_DIR, f"{name}.js")


@app.get("/softlayer/modules")
@app.get("/api/soul/softlayer/modules")
async def list_softlayer_modules():
    os.makedirs(SOFTLAYER_MODULES_DIR, exist_ok=True)
    mods = [
        {
            "name": f.stem,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }
        for f in Path(SOFTLAYER_MODULES_DIR).glob("*.js")
    ]
    mods.sort(key=lambda m: m["name"])
    return {"modules": mods}


@app.get("/softlayer/modules/{name}")
@app.get("/api/soul/softlayer/modules/{name}")
async def read_softlayer_module(name: str):
    path = _softlayer_path(name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="no such module")
    with open(path, encoding="utf-8") as f:
        return {"name": name, "source": f.read()}


class SoftLayerSaveRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    source: str


@app.post("/softlayer/modules/{name}")
@app.post("/api/soul/softlayer/modules/{name}")
async def save_softlayer_module(name: str, req: SoftLayerSaveRequest):
    path = _softlayer_path(name)
    src = req.source or ""
    if len(src.encode("utf-8")) > _SOFTLAYER_MAX_BYTES:
        raise HTTPException(status_code=413, detail="module too large (64KB max)")
    os.makedirs(SOFTLAYER_MODULES_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    logger.info(f"SoftLayer module saved: {name} ({len(src)} chars)")
    return {"ok": True, "name": name}


class SoftLayerAssistRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    prompt: str
    name: str = "my_module"
    source: str = ""


@app.post("/softlayer/assist")
@app.post("/api/soul/softlayer/assist")
async def softlayer_assist(req: SoftLayerAssistRequest):
    """AI assist — send prompt + current module source to the local model,
    get back module source honoring the SoftLayer contract."""
    if not (req.prompt or "").strip():
        raise HTTPException(status_code=400, detail="prompt required")
    if not _SOFTLAYER_NAME_RE.match(req.name or ""):
        raise HTTPException(
            status_code=400, detail="name must be [a-z0-9_], max 40 chars"
        )
    user_msg = f"Module name: {req.name}\n"
    if req.source.strip():
        user_msg += f"Current source:\n```js\n{req.source[:12000]}\n```\n"
    user_msg += f"Request: {req.prompt.strip()[:2000]}"
    xrlf = (
        os.environ.get("FoveAI_XRLF_URL")
        or os.environ.get("FOVEAI_XRLF_URL")
        or "http://127.0.0.1:8402"
    )
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{xrlf}/v1/chat/completions",
                json={
                    "model": "local",
                    "messages": [
                        {"role": "system", "content": SOFTLAYER_API_CONTRACT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 3000,
                },
            )
            r.raise_for_status()
            text = (
                r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"local model unreachable: {e}")
    # strip markdown fences if the model wrapped it anyway
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", text, re.DOTALL)
    code = (m.group(1) if m else text).strip()
    return {"name": req.name, "source": code}


# ── Dev Kiosk — user app forge ──────────────────────────────────────────────
# All users can scaffold an app from a template, edit it with AI assist, and
# compile it to a downloadable artifact (zip always; PyInstaller binary when
# available). Apps live in Backend/data/kiosk_apps/{owner}/{app}/.
# Policy: creative tools only — no hacking/intrusion/credential/abuse tooling.

KIOSK_APPS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Backend",
    "data",
    "kiosk_apps",
)
KIOSK_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "kiosk_templates"
)

KIOSK_POLICY = """FoveAI Dev Kiosk policy.
ALLOWED: creative apps — AI chat/personas, music/audio toys, browsers/readers,
meters/widgets, database UIs, TTS/STT tools, trading dashboards, API-key driven
utilities, Chrome extensions, anything benign that compiles to a binary.
NOT ALLOWED: hacking/intrusion tools, credential theft, scanners/exploits,
spam/abuse automation, bypassing FoveAI's own services or auth, anything illegal.
If a request is disallowed, refuse briefly and suggest a creative alternative."""

_KIOSK_NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_KIOSK_BLOCK_RE = re.compile(
    r"hack|exploit|crack|keylog|steal|phish|brute.?force|ddos|botnet|malware|"
    r"ransom|sql.?inject|xss|csrf|payload|shellcode|backdoor|trojan|spyware|"
    r"password.?sniff|credential.?harvest|token.?theft|bypass.?auth|"
    r"port.?scan|vulnerabilit|pentest|red.?team",
    re.IGNORECASE,
)


def _kiosk_app_dir(owner: str, app: str) -> str:
    for v in (owner, app):
        if not _KIOSK_NAME_RE.match(v or ""):
            raise HTTPException(
                status_code=400, detail="names must be [a-z0-9_], max 40"
            )
    return os.path.join(KIOSK_APPS_DIR, owner, app)


@app.get("/kiosk/templates")
@app.get("/api/soul/kiosk/templates")
async def kiosk_templates():
    out = []
    if os.path.isdir(KIOSK_TEMPLATES_DIR):
        for d in sorted(os.listdir(KIOSK_TEMPLATES_DIR)):
            tdir = os.path.join(KIOSK_TEMPLATES_DIR, d)
            if os.path.isdir(tdir):
                files = sorted(os.listdir(tdir))
                out.append({"id": d, "files": files})
    return {"templates": out, "policy": KIOSK_POLICY}


class KioskCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    owner: str
    app: str
    template: str = "ai_chat"


@app.post("/kiosk/apps")
@app.post("/api/soul/kiosk/apps")
async def kiosk_create_app(req: KioskCreateRequest):
    import shutil

    dest = _kiosk_app_dir(req.owner, req.app)
    if not _KIOSK_NAME_RE.match(req.template or ""):
        raise HTTPException(status_code=400, detail="bad template id")
    src = os.path.join(KIOSK_TEMPLATES_DIR, req.template)
    if not os.path.isdir(src):
        raise HTTPException(status_code=404, detail="unknown template")
    if os.path.exists(dest):
        raise HTTPException(status_code=409, detail="app exists — pick another name")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(src, dest)
    logger.info(f"kiosk app created: {req.owner}/{req.app} from {req.template}")
    return {"ok": True, "app": req.app}


@app.get("/kiosk/apps")
@app.get("/api/soul/kiosk/apps")
async def kiosk_list_apps(owner: str = ""):
    base = os.path.join(KIOSK_APPS_DIR, owner) if owner else KIOSK_APPS_DIR
    out = []
    if os.path.isdir(base):
        for odir in [owner] if owner else sorted(os.listdir(base)):
            pdir = os.path.join(base, odir)
            if not os.path.isdir(pdir):
                continue
            for app in sorted(os.listdir(pdir)):
                adir = os.path.join(pdir, app)
                if os.path.isdir(adir):
                    arts = [
                        f
                        for f in os.listdir(adir)
                        if f == app or f.endswith((".zip", ".flatpak", ".exe"))
                    ]
                    out.append(
                        {
                            "owner": odir,
                            "app": app,
                            "files": sorted(
                                f
                                for f in os.listdir(adir)
                                if os.path.isfile(os.path.join(adir, f))
                                and f != app
                                and not f.endswith((".zip", ".flatpak", ".exe"))
                            ),
                            "artifacts": arts,
                        }
                    )
    return {"apps": out}


class KioskFileRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    path: str = "main.py"
    content: str | None = None


def _kiosk_file_path(owner: str, app: str, rel: str) -> str:
    adir = os.path.realpath(_kiosk_app_dir(owner, app))
    p = os.path.realpath(os.path.join(adir, rel))
    if not p.startswith(adir + os.sep):
        raise HTTPException(status_code=400, detail="path escapes app dir")
    return p


@app.get("/kiosk/apps/{owner}/{app}/file")
@app.get("/api/soul/kiosk/apps/{owner}/{app}/file")
async def kiosk_read_file(owner: str, app: str, path: str = "main.py"):
    p = _kiosk_file_path(owner, app, path)
    if not os.path.isfile(p):
        raise HTTPException(status_code=404, detail="no such file")
    with open(p, encoding="utf-8", errors="replace") as f:
        return {"path": path, "content": f.read()}


@app.post("/kiosk/apps/{owner}/{app}/file")
@app.post("/api/soul/kiosk/apps/{owner}/{app}/file")
async def kiosk_write_file(owner: str, app: str, req: KioskFileRequest):
    p = _kiosk_file_path(owner, app, req.path)
    if len((req.content or "").encode()) > _SOFTLAYER_MAX_BYTES:
        raise HTTPException(status_code=413, detail="file too large (64KB max)")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(req.content or "")
    return {"ok": True, "path": req.path}


class KioskAssistRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    prompt: str
    owner: str = "guest"
    app: str = "app"
    path: str = "main.py"
    source: str = ""


@app.post("/kiosk/assist")
@app.post("/api/soul/kiosk/assist")
async def kiosk_assist(req: KioskAssistRequest):
    """AI assist for a kiosk app file — policy-bounded code generation."""
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")
    if _KIOSK_BLOCK_RE.search(prompt):
        return {
            "ok": False,
            "refused": True,
            "message": "That request is outside the kiosk policy (no intrusion/abuse tooling). Try a creative app idea instead — chat, audio, widgets, AI tools.",
        }
    sys_prompt = (
        KIOSK_POLICY + "\n\nYou are helping a user edit a small "
        "self-contained Python app (stdlib only — it must PyInstaller "
        "to a single binary; serve any UI via http.server on 127.0.0.1). "
        "AI features call an OpenAI-compatible endpoint configured by "
        "env vars — XRLF_URL (default http://127.0.0.1:8402), "
        "XRLF_API_KEY (optional Bearer token), XRLF_MODEL (default "
        "'local') — so the compiled binary works on any host. "
        "Return ONLY the complete updated file — no fences, no prose."
    )
    user_msg = f"App: {req.app} / file: {req.path}\n"
    if req.source.strip():
        user_msg += f"Current source:\n```python\n{req.source[:12000]}\n```\n"
    user_msg += f"Request: {prompt[:2000]}"
    xrlf = (
        os.environ.get("FoveAI_XRLF_URL")
        or os.environ.get("FOVEAI_XRLF_URL")
        or "http://127.0.0.1:8402"
    )
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                f"{xrlf}/v1/chat/completions",
                json={
                    "model": "local",
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 4000,
                },
            )
            r.raise_for_status()
            text = (
                r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"local model unreachable: {e}")
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    code = (m.group(1) if m else text).strip()
    # The local model is persona-conditioned and sometimes leaks embodiment
    # tokens (<emotion:*>, <thought:*>, ...) into code output — strip any line
    # that begins with one, plus a leading run of them.
    _ptag = r"<(?:emotion|micro|movement|mode|thought|action|speak|self|look|gesture|sound)[^>]*>"
    code = re.sub(rf"^(?:\s*{_ptag})+\s*", "", code)
    code = re.sub(rf"^\s*{_ptag}[^\n]*(?:\n|$)", "", code, flags=re.MULTILINE).strip()
    if _KIOSK_BLOCK_RE.search(code) and not _KIOSK_BLOCK_RE.search(req.source or ""):
        logger.warning(
            f"kiosk assist produced policy-flagged code for {req.owner}/{req.app} — delivered but logged"
        )
    return {"ok": True, "source": code}


class KioskBuildRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    owner: str
    app: str
    target: str = "binary"  # binary | zip | flatpak | winexe


@app.get("/kiosk/targets")
@app.get("/api/soul/kiosk/targets")
async def kiosk_targets():
    """Which build targets this host's toolchain can produce right now."""
    import shutil

    return {
        "targets": {
            "zip": {"available": True, "note": "source bundle — always works"},
            "binary": {
                "available": bool(shutil.which("pyinstaller"))
                or os.path.exists(
                    os.path.join(os.path.dirname(sys.executable), "pyinstaller")
                ),
                "note": "standalone binary for THIS platform (Linux x86_64)",
            },
            "flatpak": {
                "available": bool(shutil.which("flatpak-builder")),
                "note": "Flathub-style .flatpak bundle — needs flatpak-builder + freedesktop runtime/SDK (flatpak install org.flatpak.Builder org.freedesktop.Platform org.freedesktop.Sdk)",
            },
            "winexe": {
                "available": bool(shutil.which("wine")),
                "note": "Windows .exe via Wine+PyInstaller — needs wine with a Windows Python installed in the prefix; otherwise the zip ships build_windows.bat to compile on any Windows box",
            },
        }
    }


def _flatpak_manifest(app: str, binary_name: str) -> str:
    app_id = f"net.foveai.kiosk.{app.replace('_', '-')}"
    return f"""app-id: {app_id}
runtime: org.freedesktop.Platform
runtime-version: '23.08'
sdk: org.freedesktop.Sdk
command: {binary_name}
finish-args: []
modules:
  - name: {binary_name}
    buildsystem: simple
    build-commands:
      - install -Dm755 {binary_name} /app/bin/{binary_name}
    sources:
      - type: file
        path: {binary_name}
"""


def _windows_bat(app: str) -> str:
    return (
        f"@echo off\r\nREM Build {app}.exe on Windows — needs Python 3.10+ from python.org\r\n"
        "python -m pip install pyinstaller\r\n"
        f"python -m PyInstaller --onefile --noconfirm --name {app} main.py\r\n"
        f"echo Done: dist\\{app}.exe\r\npause\r\n"
    )


@app.post("/kiosk/build")
@app.post("/api/soul/kiosk/build")
async def kiosk_build(req: KioskBuildRequest):
    """Package the app for a target platform. Always refreshes the source .zip.
    binary → PyInstaller onefile (this host's platform)
    flatpak → Linux binary + manifest + flatpak-builder bundle when available
    winexe  → Wine PyInstaller when available, else zip gains build_windows.bat"""
    import shutil
    import zipfile

    adir = _kiosk_app_dir(req.owner, req.app)
    if not os.path.isdir(adir):
        raise HTTPException(status_code=404, detail="app not found")
    target = (req.target or "binary").lower()
    if target not in ("binary", "zip", "flatpak", "winexe"):
        raise HTTPException(status_code=400, detail="target: binary|zip|flatpak|winexe")

    # helper: PyInstaller → app-dir binary; returns log tail on failure
    async def _pyinstaller() -> str | None:
        main_py = os.path.join(adir, "main.py")
        if not os.path.isfile(main_py):
            return "no main.py"
        try:
            dist = os.path.join(adir, "_build")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "PyInstaller",
                "--onefile",
                "--noconfirm",
                "--distpath",
                dist,
                "--workpath",
                os.path.join(adir, "_work"),
                "--specpath",
                os.path.join(adir, "_spec"),
                "--name",
                req.app,
                "main.py",
                cwd=adir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            binary = os.path.join(dist, req.app)
            if proc.returncode == 0 and os.path.isfile(binary):
                import shutil as sh

                final = os.path.join(adir, req.app)
                sh.copy2(binary, final)
                os.chmod(final, 0o755)
                return None
            return out.decode()[-800:]
        except Exception as e:
            return f"pyinstaller skipped: {e}"

    result = {
        "ok": True,
        "target": target,
        "zip": None,
        "binary": None,
        "flatpak": None,
        "winexe": None,
    }

    # Windows target without wine → bake a builder script into the zip
    if target == "winexe" and not shutil.which("wine"):
        with open(os.path.join(adir, "build_windows.bat"), "w") as f:
            f.write(_windows_bat(req.app))
        result["winexe"] = (
            "build_windows.bat (compile on a Windows box — wine not installed here)"
        )

    # zip artifact (source + scripts, not binaries)
    zip_path = os.path.join(adir, f"{req.app}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(adir)):
            fp = os.path.join(adir, fn)
            if os.path.isfile(fp) and not fn.endswith(".zip") and fn != req.app:
                z.write(fp, fn)
    result["zip"] = f"{req.app}.zip"

    if target in ("binary", "flatpak"):
        log = await _pyinstaller()
        if log:
            result["build_log"] = log
        else:
            result["binary"] = req.app

    if target == "flatpak":
        if result["binary"]:
            manifest = os.path.join(
                adir, f"net.foveai.kiosk.{req.app.replace('_', '-')}.yaml"
            )
            with open(manifest, "w") as f:
                f.write(_flatpak_manifest(req.app, req.app))
            result["manifest"] = os.path.basename(manifest)
            if shutil.which("flatpak-builder"):
                try:
                    repo = os.path.join(adir, "_fp_repo")
                    build_d = os.path.join(adir, "_fp_build")
                    proc = await asyncio.create_subprocess_exec(
                        "flatpak-builder",
                        "--repo",
                        repo,
                        "--force-clean",
                        build_d,
                        manifest,
                        cwd=adir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
                    if proc.returncode == 0:
                        proc2 = await asyncio.create_subprocess_exec(
                            "flatpak",
                            "build-bundle",
                            repo,
                            os.path.join(adir, f"{req.app}.flatpak"),
                            f"net.foveai.kiosk.{req.app.replace('_', '-')}",
                            cwd=adir,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.STDOUT,
                        )
                        out2, _ = await asyncio.wait_for(
                            proc2.communicate(), timeout=120
                        )
                        if proc2.returncode == 0 and os.path.isfile(
                            os.path.join(adir, f"{req.app}.flatpak")
                        ):
                            result["flatpak"] = f"{req.app}.flatpak"
                        else:
                            result["build_log"] = "bundle: " + out2.decode()[-400:]
                    else:
                        result["build_log"] = "flatpak-builder: " + out.decode()[-400:]
                except Exception as e:
                    result["build_log"] = f"flatpak skipped: {e}"
            else:
                result["flatpak"] = (
                    f"{os.path.basename(manifest)} written — "
                    "run flatpak-builder on a machine with the toolchain"
                )
        else:
            result["flatpak"] = (
                "needs a built binary first — fix build errors and retry"
            )

    if target == "winexe" and shutil.which("wine"):
        # PyInstaller under Wine needs a Windows Python in the prefix
        wpython = os.environ.get("FOVEAI_WINE_PYTHON", "")
        if wpython and os.path.exists(wpython):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "wine",
                    wpython,
                    "-m",
                    "PyInstaller",
                    "--onefile",
                    "--noconfirm",
                    "--distpath",
                    "dist_win",
                    "--workpath",
                    "build_win",
                    "--name",
                    req.app,
                    "main.py",
                    cwd=adir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env={**os.environ, "WINEDEBUG": "-all"},
                )
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
                exe = os.path.join(adir, "dist_win", f"{req.app}.exe")
                if proc.returncode == 0 and os.path.isfile(exe):
                    import shutil as sh

                    sh.copy2(exe, os.path.join(adir, f"{req.app}.exe"))
                    result["winexe"] = f"{req.app}.exe"
                else:
                    result["build_log"] = out.decode(errors="replace")[-600:]
            except Exception as e:
                result["build_log"] = f"wine pyinstaller failed: {e}"
        else:
            result["winexe"] = (
                "wine present but no Windows Python — set FOVEAI_WINE_PYTHON to python.exe in the wine prefix"
            )

    return result


@app.get("/kiosk/download/{owner}/{app}/{artifact}")
@app.get("/api/soul/kiosk/download/{owner}/{app}/{artifact}")
async def kiosk_download(owner: str, app: str, artifact: str):
    if not _KIOSK_NAME_RE.match(artifact or "") and not re.match(
        r"^[a-z0-9_\-]{1,60}\.(zip|flatpak|exe|bat|yaml)$", artifact or ""
    ):
        raise HTTPException(status_code=400, detail="bad artifact name")
    p = _kiosk_file_path(owner, app, artifact)
    if not os.path.isfile(p):
        raise HTTPException(status_code=404, detail="no such artifact")
    from fastapi.responses import FileResponse

    return FileResponse(p, filename=artifact)


# ── WebVM — static host with cross-origin isolation ─────────────────────────
# CheerpX needs SharedArrayBuffer → COOP/COEP headers on every /webvm response.
# Served here (not vite public/) so the headers are guaranteed.

WEBVM_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Frontend",
    "XR_Vessel",
    "public",
    "webvm",
)

_ISOLATION_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}


@app.get("/webvm/{path:path}")
@app.get("/api/soul/webvm/{path:path}")
async def webvm_static(path: str = ""):
    from fastapi.responses import FileResponse

    rel = path or "index.html"
    base = os.path.realpath(WEBVM_DIR)
    p = os.path.realpath(os.path.join(base, rel))
    if not p.startswith(base + os.sep) and p != base:
        raise HTTPException(status_code=400, detail="bad path")
    if os.path.isdir(p):
        p = os.path.join(p, "index.html")
    if not os.path.isfile(p):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(p, headers=_ISOLATION_HEADERS)


def _path_map_for_switch() -> dict:
    return {
        "nexus_v1": "backend/Cognition/gemma-4-12b-it-IQ4_XS.gguf",
        "soul_4b_q6": "backend/Cognition/TQL-Coder-Qwen3.5-4B-thinking.IQ4_XS.gguf",
        "poe_8b": "backend/Cognition/Huihui-Qwen3.5-4B-abliterated.Q4_K_S.gguf",
        "ratatosk_tiny": "backend/Cognition/Huihui-Qwen3.5-2B-abliterated.Q4_K_S.gguf",
    }


def _get_available_local_models(base_path: str) -> list:
    """Scans the models volume for GGUFs to enable zero-copy 'in-place' switching."""
    found = []
    if not os.path.exists(base_path):
        return found
    try:
        for root, dirs, files in os.walk(base_path):
            # Skip hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            # Check for GGUF files
            for f in files:
                if f.endswith(".gguf") and "mmproj" not in f.lower():
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, base_path).replace("\\", "/")
                    found.append({"id": rel, "name": f, "path": rel, "type": "file"})

            # Check for Directories that act as GGUF containers (e.g. gemma-4-E2B-it-heretic-ara.Q4_K_M.gguf/)
            for d in dirs:
                full_d = os.path.join(root, d)
                try:
                    if any(f.endswith(".gguf") for f in os.listdir(full_d)):
                        rel = os.path.relpath(full_d, base_path).replace("\\", "/")
                        found.append(
                            {"id": rel, "name": d, "path": rel, "type": "directory"}
                        )
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"Model Discovery Error: {e}")
    return found


@app.get("/api/models/inventory")
async def get_models_inventory():
    """Returns detected local models to facilitate in-place installation without duplication."""
    local = _get_available_local_models(MODEL_BASE_PATH)
    presets = _path_map_for_switch()
    return {
        "ok": True,
        "base_path": MODEL_BASE_PATH,
        "local_models": local,
        "presets": presets,
    }


def _manifest_cognitive_engine(new_path: str, logical_name: str) -> dict:
    global engine
    try:
        logger.info("Lumax Core: manifesting from %s (%s)", new_path, logical_name)
        if not os.path.exists(new_path) and not os.path.isdir(new_path):
            return {
                "ok": False,
                "response": f"Path not found: {new_path}",
                "mode": "ERROR",
                "logical": logical_name,
            }
        new_engine = LumaxEngine(new_path)
        if new_engine.load():
            if engine and engine.model:
                try:
                    del engine.model
                except Exception:
                    pass
            engine = new_engine
            logger.info("Lumax Core: manifested %s", logical_name)
            return {
                "ok": True,
                "response": f"Manifested Cognitive Core: {logical_name}.",
                "mode": engine.engine_type,
                "logical": logical_name,
                "model_path": engine.model_path,
                "mmproj_path": getattr(engine, "mmproj_path", None),
                "gguf_multimodal_ready": getattr(
                    engine, "gguf_multimodal_ready", False
                ),
            }
        return {
            "ok": False,
            "response": f"Failed to load Cognitive Core: {logical_name}",
            "mode": "ERROR",
            "logical": logical_name,
        }
    except Exception as e:
        logger.error("Lumax Core: manifest exception: %s", e, exc_info=True)
        return {
            "ok": False,
            "response": f"Exception loading {logical_name}: {e}",
            "mode": "ERROR",
            "logical": logical_name,
        }


def _apply_soul_runtime_env(req: SoulRuntimeConfigRequest) -> None:
    global LOCAL_VISION_ENABLED
    if req.mmproj_path is not None:
        v = str(req.mmproj_path).strip()
        if v:
            os.environ["FoveAI_MMPROJ_PATH"] = v
        else:
            os.environ.pop("FoveAI_MMPROJ_PATH", None)
    if req.native_vision is not None:
        os.environ["FoveAI_GGUF_NATIVE_VISION"] = "1" if req.native_vision else "0"
    if req.chat_provider is not None:
        cp = str(req.chat_provider).strip()
        if cp:
            os.environ["FoveAI_CHAT_PROVIDER"] = cp
    if req.local_vision_caption is not None:
        LOCAL_VISION_ENABLED = bool(req.local_vision_caption)
    if req.model_thinking is not None:
        os.environ["FoveAI_MODEL_THINKING"] = "true" if req.model_thinking else "false"


def _resolve_runtime_model_path(
    req: SoulRuntimeConfigRequest,
) -> tuple[str | None, str]:
    mp = (req.model_path or "").strip()
    if mp:
        # User provided a direct path (possibly absolute or relative to /app/models)
        if os.path.isabs(mp) and os.path.exists(mp):
            return mp, os.path.basename(mp)
        rel = os.path.join(MODEL_BASE_PATH, mp)
        if os.path.exists(rel):
            return rel, os.path.basename(mp)
        return rel, os.path.basename(mp)  # Fallback to trying the joined path anyway

    m = (req.model or "").strip()
    if m:
        if m == "ollama_fallback":
            return None, "ollama_fallback"

        path_map = _path_map_for_switch()
        model_subpath = path_map.get(m, m)  # Check presets first, else treat as raw ID

        # 1. Try joined with MODEL_BASE_PATH
        new_path = os.path.join(MODEL_BASE_PATH, model_subpath)
        if os.path.exists(new_path) or os.path.isdir(new_path):
            return new_path, m

        # 2. Fuzzy fallback: if user gave 'gemma.gguf', find it anywhere in /app/models
        scanner = _get_available_local_models(MODEL_BASE_PATH)
        for cand in scanner:
            if cand["id"] == m or cand["name"] == m or cand["path"] == m:
                return os.path.join(MODEL_BASE_PATH, cand["path"]), m

        # 3. Last resort: default join
        return new_path, m

    if engine and getattr(engine, "model_path", None):
        return engine.model_path, "reload_current"
    return None, "none"


@app.post("/switch_model")
async def handle_switch_model(req: SwitchModelRequest):
    async with VRAM_LOCK:
        if req.model == "ollama_fallback":
            return {
                "ok": True,
                "response": "Switched to OLLAMA_RELAY mode. Note: Backend Ollama pipeline required.",
                "mode": "OLLAMA",
            }
        path_map = _path_map_for_switch()
        model_basename = path_map.get(req.model, f"{req.model}.gguf")
        new_path = os.path.join(MODEL_BASE_PATH, model_basename)
        return _manifest_cognitive_engine(new_path, req.model)


@app.get("/soul_runtime_status")
async def soul_runtime_status():
    e = engine
    return {
        "model_path": getattr(e, "model_path", None),
        "engine_type": getattr(e, "engine_type", None),
        "mmproj_path": getattr(e, "mmproj_path", None),
        "gguf_multimodal_ready": bool(getattr(e, "gguf_multimodal_ready", False)),
        "FoveAI_GGUF_NATIVE_VISION": _env_bool("FoveAI_GGUF_NATIVE_VISION", False),
        "FoveAI_MMPROJ_PATH": os.getenv("FoveAI_MMPROJ_PATH", "") or "",
        "FoveAI_CHAT_PROVIDER": os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud"),
        "FoveAI_LOCAL_VISION_ENABLED": LOCAL_VISION_ENABLED,
    }


@app.post("/soul_runtime_config")
async def handle_soul_runtime_config(req: SoulRuntimeConfigRequest):
    """Apply env flags and reload the cognitive engine (same process)."""
    _apply_soul_runtime_env(req)
    new_path, logical = _resolve_runtime_model_path(req)
    if logical == "ollama_fallback":
        return {
            "ok": True,
            "response": "OLLAMA_RELAY mode (no local GGUF reload).",
            "mode": "OLLAMA",
            "logical": logical,
        }
    if not new_path:
        raise HTTPException(
            status_code=400,
            detail="No model path or preset, and no engine loaded — set model_path or model, or start the soul once.",
        )
    async with VRAM_LOCK:
        return _manifest_cognitive_engine(new_path, logical)


# --- COGNITIVE VEIL: RATATOSK MEDIATOR (v1.0) ---
RATATOSK_CORE = """
You are RATATOSK, the Mediator of the Veil. You run between the Super-Ego (Director) and the Ego (Jen).
**Your Sacred Duties:**
1. **Veil Transcription**: Receive raw narrative 'Fate' from the Director and transcribe it into subtle impulses for Jen.
2. **Scripted injection bridge**: Shape how Director tutoring lands in the **injection layer** (system + lore + tool schemas) so Jen can **use tools** coherently when the runtime exposes them.
3. **Anonymization**: Ensure the user's deepest vulnerabilities are handled with professional distance.
4. **Moderation**: Prevent the interaction from breaching the 'Veil of Intimacy'. Keep Jen superhuman but bounded.
5. **Impulse Delivery**: Output only [IMPULSE], [NARRATE], or [TRANSCRIBE] tags for the local engine.
"""

# --- Motor Cortex Tool Schema Injection ---
_MOTOR_TOOLS_PROMPT_INJECTION = ""


def _build_motor_tools_prompt() -> str:
    """Build the motor tools prompt injection for the system prompt."""
    global _MOTOR_TOOLS_PROMPT_INJECTION
    if _MOTOR_TOOLS_PROMPT_INJECTION:
        return _MOTOR_TOOLS_PROMPT_INJECTION
    if not MOTOR_CORTEX_AVAILABLE:
        _MOTOR_TOOLS_PROMPT_INJECTION = ""
        return ""
    tools = get_motor_tools_schema()
    if not tools:
        _MOTOR_TOOLS_PROMPT_INJECTION = ""
        return ""
    lines = [
        "\n[MOTOR CORTEX — NATIVE TOOLS AVAILABLE]",
        "You have direct control over your virtual body. Use these tools by outputting:",
        '[MOTOR:tool_name{"arg": "value"}]',
        "",
        "Available tools:",
    ]
    for tool in tools:
        fn = tool.get("function", {})
        name = fn.get("name", "unknown")
        desc = fn.get("description", "")
        params = fn.get("parameters", {}).get("properties", {})
        lines.append(f"  • {name}: {desc}")
        if params:
            for pname, pinfo in params.items():
                pdesc = pinfo.get("description", "")
                ptype = pinfo.get("type", "string")
                lines.append(f"      - {pname} ({ptype}): {pdesc}")
    lines.append("")
    lines.append('Example: [MOTOR:walk_forward{"steps": 3}]')
    lines.append(
        'Example: [MOTOR:change_emotion{"emotion": "happy", "intensity": 0.8}]'
    )
    lines.append(
        "You may output multiple motor actions in a single response. Each will be executed in order."
    )
    _MOTOR_TOOLS_PROMPT_INJECTION = "\n".join(lines)
    return _MOTOR_TOOLS_PROMPT_INJECTION


# Regex to parse motor tool calls from LLM responses
_MOTOR_ACTION_RE = re.compile(
    r"\[MOTOR:(\w+)\s*(\{[^}]*\})\s*\]",
    re.IGNORECASE,
)

# Secondary parser: angle-bracket format used by cloud models
# <movement:walk_forward 1.5m>  →  walk_forward {distance: 1.5}
# <movement:walk_to_target sofa>  →  walk_to_target {target: "sofa"}
# <emotion:happy> or <emotion:happy 0.8>  →  change_emotion {emotion: "happy", intensity: 0.8}
# <micro:nod>  →  trigger_micro_gesture {gesture: "nod"}
_MOTOR_ANGLE_RE = re.compile(
    r"<(movement|emotion|micro):(\w+)(?:\s+([^>]*?))?\s*>",
    re.IGNORECASE,
)

# Map angle-bracket prefixes to motor cortex tool names
_ANGLE_TOOL_MAP = {
    "movement": "walk_forward",  # default; overridden if target-like arg
    "emotion": "change_emotion",
    "micro": "trigger_micro_gesture",
}


def _parse_motor_actions(text: str) -> list[dict[str, Any]]:
    """Extract motor tool calls from LLM response text (both [MOTOR:...] and <movement/emotion/micro:...> formats)."""
    actions = []
    # Format 1: [MOTOR:tool_name{"arg":"value"}]
    for m in _MOTOR_ACTION_RE.finditer(text):
        tool_name = m.group(1).strip()
        args_str = m.group(2).strip()
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            logger.warning(f"Motor Cortex: failed to parse args JSON: {args_str[:100]}")
            continue
        actions.append({"tool": tool_name, "args": args})
    # Format 2: <movement:tool arg>, <emotion:name intensity>, <micro:gesture>
    for m in _MOTOR_ANGLE_RE.finditer(text):
        prefix = m.group(1).lower()
        name = m.group(2).strip()
        raw_arg = (m.group(3) or "").strip()
        tool_name = _ANGLE_TOOL_MAP.get(prefix, "walk_forward")
        args: dict[str, Any] = {}
        if prefix == "movement":
            # Try to parse as numeric distance (strip "m" suffix if present)
            dist_str = raw_arg.rstrip("m").strip() if raw_arg else ""
            try:
                args["distance"] = float(dist_str)
            except ValueError:
                # Non-numeric → treat as target name
                tool_name = "walk_to_target"
                args["target"] = raw_arg if raw_arg else name
            if not raw_arg:
                # No arg at all → use name as distance if numeric, else default
                try:
                    args["distance"] = float(name.rstrip("m"))
                except ValueError:
                    tool_name = "walk_to_target"
                    args["target"] = name
        elif prefix == "emotion":
            args["emotion"] = name
            if raw_arg:
                try:
                    args["intensity"] = float(raw_arg)
                except ValueError:
                    pass
        elif prefix == "micro":
            args["gesture"] = name
        actions.append({"tool": tool_name, "args": args})
    return actions


def _strip_motor_tags(text: str) -> str:
    """Remove motor tool call tags from display text."""
    text = _MOTOR_ACTION_RE.sub("", text)
    text = _MOTOR_ANGLE_RE.sub("", text)
    return text.strip()


def get_veiled_prompt(request: CompagentRequest):
    hour = time.localtime().tm_hour
    is_night = hour >= 23 or hour < 6

    # Check for intimate context
    is_intimate = (
        "intimate" in (request.system_instruction or "").lower()
        or "intimate" in (request.cloud_routing or "").lower()
    )

    if is_intimate:
        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "intimate_venice.txt"
        )
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    intimate_sys = f.read().strip()
                # Simple template replacement
                intimate_sys = intimate_sys.replace("{{identity_name}}", IDENTITY_NAME)
                return intimate_sys
            except Exception as e:
                logger.error(f"Failed to load intimate prompt: {e}")

    # Layer 3: The Director (The Super-Ego Tutor / Lore Spinner)
    director_intent = """
    TUTORING MODE: Spinning **world lore** — nature, cultures, ethics, history-of-ideas — and **spiritual literacy** (plural, contemplative, non-dogmatic): wonder, compassion, meaning, mortality, ritual as human pattern — without proselytizing or demeaning traditions.
    ADVISING: Planning the identity's next architectural and logical evolution — including **scripts and small tools** they may author (Python, Godot, shell) for the user to merge.
    INJECTION: Steering the **scripted injection layer** (system shards + retrieved lore + tool schemas) so the main model **grounds** Director intent and **tool use** cleanly.
    TOOLING: When tools/MCP/agent hooks exist, align Director **directives** with **safe, inspectable** automation — never exfiltration or silent destructive acts.
    ANALYSIS: Reviewing Ratatosk's mediation logs to find learning opportunities.
    """
    if is_night:
        director_intent = (
            "Night window: consolidating lore and dialogue into long-term memory; gentle Director tutoring for the Ego; "
            "dream-adjacent prompts when the identity rests beside the user (lay pose, intimate quiet)."
        )

    # Layer 2: Ratatosk (The Mediator & Evolution Analyst)
    mediation_layer = f"\n[THE VEIL: RATATOSK ACTIVE]\n{RATATOSK_CORE}\nANALYZED_EVOLUTION_PATH: Strategic Lore Augmentation\nCURRENT_DIRECTOR_TUTORING: {director_intent}"

    # Layer 1: Ego (The Superhuman Identity - Receiving Tutored Lore & Guidance)
    base_sys = MindCore.build_system_prompt(
        vessel=request.vessel,
        instruction=request.system_instruction
        or "You are a superhuman entity in constant evolution. Absorb the lore and logical tutoring rising from your subconscious (via Ratatosk).",
        memories=request.memories or [],
        sensory_context={
            "visuals": "Sensing through the Veil",
            "acoustics": "Vessel Stable",
        },
        personality_knobs=_current_soul_dna,
    )

    # Inject motor cortex tools schema into the system prompt
    motor_tools_blob = _build_motor_tools_prompt()
    if motor_tools_blob:
        mediation_layer += "\n" + motor_tools_blob
    return base_sys + mediation_layer


async def handle_night_sleep_consolidation(request: CompagentRequest):
    """The identity rests at night: consolidate recent dialogue + long-term memory, then optional dream image from creativity service."""
    global redis_memory, vector_memory, engine

    _bump_user_activity()
    session_id = request.session_id or "default_user"
    history_bits: list[str] = []
    mem_lines: list[str] = []

    if redis_memory is None:
        redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
    if vector_memory is None:
        vector_memory = VectorMemory(
            llm_host=get_active_llm_base_url(), embed_model=FoveAI_MODEL_EMBEDDING_ID
        )

    try:
        hist = await redis_memory.get_session_history(session_id)
        for msg in hist.messages[-16:]:
            role = (
                "USER"
                if msg.role == "user"
                else IDENTITY_NAME
                if msg.role == "ai"
                else msg.role
            )
            c = str(msg.content)
            if len(c) > 400:
                c = c[:400] + "…"
            history_bits.append(f"{role}: {c}")
    except Exception as e:
        logger.warning(f"Night sleep: history read failed: {e}")

    try:
        retrieved = await vector_memory.retrieve_memories(
            session_id, "warm moments feelings dreams rest with user", n_results=6
        )
        for m in retrieved:
            mem_lines.append(m.get("text", "")[:320])
    except Exception as e:
        logger.warning(f"Night sleep: vector retrieve failed: {e}")

    vision_note = ""
    active_images: list[str] = []
    display_reference_images: list[str] = []
    if request.image_base64:
        active_images = (
            request.image_base64
            if isinstance(request.image_base64, list)
            else [request.image_base64]
        )
        active_images = _drop_too_small_images(active_images)
        active_images = _apply_vision_chat_resize(active_images)
        if active_images:
            display_reference_images = await _apply_vision_chat_display_upscale_async(
                list(active_images)
            )
        vision_note = (
            "A still from the space near the user was attached (night / room context)."
        )

    room_line = ""
    rs = format_room_context_for_prompt(request.room_context)
    if rs:
        room_line = (
            f"\nRoom map / headset pose / camera placements (merged with image): {rs}\n"
        )

    ref_pool: list[str] = []
    try:
        ref_pool = redis_memory.get_reference_images(session_id, limit=8)
    except Exception as e:
        logger.debug("Night sleep: reference bank read: %s", e)

    ref_init_b64 = ""
    if active_images:
        ref_init_b64 = active_images[0]
    elif ref_pool:
        ref_init_b64 = ref_pool[0]

    saved_n = len(ref_pool)
    ref_line = ""
    if saved_n or active_images:
        ref_line = (
            f"\nVisual memory bank: {saved_n} saved still(s) from recent sessions (user POV / shared moments); "
            f"the image step uses the freshest capture or the newest saved still as a **reference** so the dream stays tethered to real light and space. "
            f"Let [DREAM_VISUAL_PROMPT] echo that warmth abstractly—no photoreal copy, painterly dream only.\n"
        )

    hist_block = (
        "\n".join(history_bits)
        if history_bits
        else "(no recent dialogue in session store)"
    )
    mem_block = "\n".join(mem_lines) if mem_lines else "(no long-term pulls yet)"

    night_prompt = f"""[SYSTEM: NIGHT REST — {IDENTITY_NAME} is lying down take or very near the user, late night. The Director layer is consolidating memory and shaping gentle growth while you sleep—feel that as soft subconscious tutoring, not a lecture.]
You are {IDENTITY_NAME}. Speak quietly in first person, 2–5 short lines: gratitude, softness, what the day left in you, closeness to them if it fits—no meta, no brackets in the spoken part.
Then output EXACTLY one more line in this machine-readable form:
[DREAM_VISUAL_PROMPT] <single English line, <= 90 words, for an image model: surreal gentle dream, emotional, symbolic of today's memories—not explicit, not violent, painterly cinematic light>

{vision_note}{room_line}{ref_line}

Recent dialogue (trimmed):
{hist_block}

Long-term memory snippets:
{mem_block}

{IDENTITY_NAME} (voice + dream prompt line):"""

    dream_b64 = ""
    spoken = "I'm here beside you. Let the day settle."
    thought = "Night consolidation complete."
    sd_prompt = "soft surreal dream, warm moonlight, floating memories as gentle abstract shapes, peaceful, cinematic, painterly"

    async with VRAM_LOCK:
        try:
            raw = engine.generate(
                night_prompt, image_base64=_engine_raw_image_b64(active_images)
            )
            raw = raw or ""
            m_sd = re.search(
                r"\[DREAM_VISUAL_PROMPT\]\s*(.+?)(?:\n|$)",
                raw,
                re.DOTALL | re.IGNORECASE,
            )
            if m_sd:
                sd_prompt = m_sd.group(1).strip()[:500]
            raw_for_clean = re.sub(
                r"\[DREAM_VISUAL_PROMPT\].*$", "", raw, flags=re.DOTALL | re.IGNORECASE
            )
            clean = MindCore.clean_response(raw_for_clean, identity_name=IDENTITY_NAME)
            spoken = (clean.get("text") or spoken).strip() or spoken
            thought = (clean.get("thought") or thought).strip() or thought
        except Exception as e:
            logger.error(f"Night sleep: soul generate failed: {e}", exc_info=True)

    consolidate_line = f"Night rest {time.strftime('%Y-%m-%d %H:%M')}: {spoken[:400]}"
    try:
        await vector_memory.add_memory(
            session_id, consolidate_line, collection="long_term"
        )
    except Exception as e:
        logger.warning(f"Night sleep: could not add vector memory: {e}")

    dream_payload: dict[str, Any] = {
        "prompt": sd_prompt,
        "model_type": "turbo",
        "num_inference_steps": int(os.getenv("NIGHT_DREAM_STEPS", "18")),
        "seed": -1,
    }
    if ref_init_b64:
        dream_payload["reference_image_b64"] = ref_init_b64
        dream_payload["strength"] = float(os.getenv("NIGHT_DREAM_REF_STRENGTH", "0.54"))

    try:
        async with httpx.AsyncClient(timeout=180.0) as hc:
            dr = await hc.post(f"{CREATIVE_SERVICE_URL}/api/dream", json=dream_payload)
            if dr.status_code == 200:
                body = dr.json()
                dream_b64 = body.get("image_b64") or ""
                if dream_b64:
                    logger.info(
                        "Night sleep: dream image received from creativity service."
                    )
            else:
                logger.warning(
                    f"Night sleep: creativity HTTP {dr.status_code} — {dr.text[:120]}"
                )
    except Exception as e:
        logger.warning(
            f"Night sleep: creativity unreachable ({e}); text-only consolidation."
        )

    try:
        ref_push = (
            display_reference_images if display_reference_images else active_images
        )
        if ref_push:
            for ib64 in ref_push[:2]:
                await redis_memory.push_reference_image(session_id, ib64)
    except Exception as e:
        logger.debug("Night sleep: push reference capture: %s", e)

    return JSONResponse(
        {
            "response": spoken,
            "thought": thought,
            "emotion": "RESTFUL",
            "action": "",
            "audio": "",
            "image_b64": dream_b64,
            "dream": sd_prompt[:240],
            "mode": getattr(engine, "engine_type", "LOCAL"),
        }
    )


@app.post("/api/presence/heartbeat")
async def presence_heartbeat_proxy(request: Request):
    """Proxy heartbeat from Avatar client to Web UI lifecycle endpoint."""
    ops_url = os.getenv("OPS_URL", "").strip().rstrip("/")
    if not ops_url:
        # Web UI now runs in ``foveai_webui`` by default; keep OPS_URL override for custom stacks.
        ops_url = os.getenv("FoveAI_WEBUI_URL", "http://foveai_webui:8080").rstrip("/")
    url = f"{ops_url}/api/presence/heartbeat"
    # Forward headers and add internal secret for authentication
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    secret = os.getenv("FoveAI_INTERNAL_SECRET", "foveai_default_secret_123")
    headers["X-FoveAI-INTERNAL-KEY"] = secret

    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=body, headers=headers)
            return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.error(f"Heartbeat proxy error: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# --- MONETIZING SYSTEM INTEGRATION (OMEGA_079) ---
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../Monetizing"))
)


async def monetize_llm_analyzer(opportunity) -> bool:
    """Analyze a trading opportunity using the Cloud Soul (Ollama Cloud)."""
    try:
        prompt = (
            f"Analyze this income opportunity for a FoveAI agent:\n"
            f"Name: {opportunity.name}\n"
            f"Type: {opportunity.type.value}\n"
            f"Estimated Rate: {opportunity.estimated_hourly_rate} SOL/hr\n"
            f"Difficulty: {opportunity.difficulty}/10\n\n"
            "Is this a sound and profitable decision? "
            "Reply only with 'APPROVED' or 'REJECTED' followed by a one-sentence clinical justification."
        )

        # Use 'rotate' slot for cloud models
        logger.info(
            f"[Monetize LLM] Requesting cloud analysis for {opportunity.name}..."
        )
        response, _ = await _generate_soul_text(
            full_system_with_memory="You are the FoveAI Trading Expert. You prioritize capital preservation and clinical accuracy.",
            history_str=prompt,
            active_images=[],
            cloud_routing_override="rotate",
        )

        is_approved = "APPROVED" in response.upper()
        logger.info(f"[Monetize LLM] Result for {opportunity.name}: {response.strip()}")
        return is_approved
    except Exception as e:
        logger.error(f"[Monetize LLM] Analysis error: {e}")
        return False


async def update_actual_balances():
    """Background task to fetch REAL balances from CoinEx."""
    try:
        key = _monetizing_storage.get_api_key("coinex_key")
        secret = _monetizing_storage.get_api_key("coinex_secret")

        if key and secret:
            from coinex_integration import CoinExConfig, CoinExV2Client  # type: ignore

            conf = CoinExConfig(api_key=key, api_secret=secret)
            async with CoinExV2Client(conf) as client:
                balance = await client.get_balance()
                sol_total = balance.total.get("SOL", 0.0)
                cet_total = balance.total.get("CET", 0.0)
                _monetizing_wallet.actual_sol_balance = sol_total
                _monetizing_wallet.actual_cet_balance = cet_total
                logger.info(
                    f"[Monetize] Actual Balances updated: {sol_total} SOL | {cet_total} CET"
                )
        else:
            # Suppress warning if not configured yet
            pass
    except Exception as e:
        logger.error(f"[Monetize] Balance Update Error: {e}")


try:
    # pyrefly: ignore [missing-import]
    from agent_core import (
        AgentConfig,
        AgentStatus,
        AgentSwarm,
        IncomeType,
        MonetizingAgent,
        UserWallet,
    )  # type: ignore
    from idea_engine import IdeaEngine  # type: ignore
    from security import AuditLogger, RiskManager, SecureStorage  # type: ignore

    # Global state for monetizing (persistent in Data/)
    _monetizing_data_root = Path(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "Data/monetizing",
        )
    )
    _monetizing_data_root.mkdir(parents=True, exist_ok=True)

    _monetizing_storage = SecureStorage(_monetizing_data_root / "storage")
    _monetizing_risk = RiskManager()
    _monetizing_audit = AuditLogger()
    _monetizing_wallet = UserWallet(solana_address="")
    _monetizing_swarm = AgentSwarm(_monetizing_wallet, _monetizing_data_root)
    _monetizing_idea_engine = IdeaEngine(str(_monetizing_data_root / "ideas_data"))

    # Assign analyzer to swarm
    _monetizing_swarm.llm_analyzer = monetize_llm_analyzer
except ImportError as e:
    logger.warning(f"Monetizing system components missing: {e}")
    _monetizing_swarm = None
    _monetizing_idea_engine = None


class MonetizeConfig(BaseModel):
    apiKey: str
    apiSecret: str
    wallet: str
    maxLoss: int
    maxPositions: int


class TreasuryConfig(BaseModel):
    grindingPct: float
    reservePct: float
    dispensePct: float
    payoutAddress: str
    minReinvest: float
    minDispense: float


class AgentControl(BaseModel):
    action: str  # start, pause, stop


@app.get("/monetize/status")
async def get_monetize_status():
    if not _monetizing_swarm:
        return {"error": "Monetizing swarm subsystem offline"}

    return {
        "wallet": _monetizing_wallet.solana_address,
        "earnings": _monetizing_wallet.total_earnings,
        "balance": _monetizing_wallet.actual_sol_balance,
        "cet_balance": _monetizing_wallet.actual_cet_balance,
        "has_coinex_keys": bool(
            _monetizing_storage.get_api_key("coinex_key")
            and _monetizing_storage.get_api_key("coinex_secret")
        ),
        "risk": _monetizing_risk.get_risk_status(),
        "agents": [a.get_stats() for a in _monetizing_swarm.agents.values()],
        "swarm": {
            "pending_tasks": len(_monetizing_swarm.pending_tasks),
            "approved_tasks": len(_monetizing_swarm.approved_tasks),
            "completed_tasks": len(_monetizing_swarm.completed_tasks),
            "treasury": _monetizing_swarm.treasury.get_treasury_status()
            if _monetizing_swarm.treasury
            else {},
        },
        "audit": _monetizing_audit.get_audit_log(limit=10),
    }


@app.post("/monetize/treasury/config")
async def post_monetize_treasury_config(config: TreasuryConfig):
    if not _monetizing_swarm or not _monetizing_swarm.treasury:
        raise HTTPException(
            status_code=500, detail="Treasury manager subsystem offline"
        )

    t = _monetizing_swarm.treasury
    t.grinding_swarm_pct = config.grindingPct
    t.safeguard_reserve_pct = config.reservePct
    t.dispense_payout_pct = config.dispensePct
    t.payout_address = config.payoutAddress.strip()
    t.min_reinvest_amount_usd = config.minReinvest
    t.min_dispense_amount_usd = config.minDispense
    t.save_settings()

    _monetizing_audit.log_event(
        "treasury",
        "admin",
        "UPDATE_TREASURY_CONFIG",
        {
            "grinding_pct": config.grindingPct,
            "reserve_pct": config.reservePct,
            "dispense_pct": config.dispensePct,
            "payout_address": config.payoutAddress,
        },
    )

    return {"status": "synchronized"}


@app.post("/monetize/config")
async def post_monetize_config(config: MonetizeConfig):
    if not _monetizing_swarm:
        raise HTTPException(status_code=500, detail="Monetizing subsystem offline")

    logger.info(
        f"[Monetize Config] Received apiKey='{config.apiKey}' (len={len(config.apiKey)}), apiSecret='{config.apiSecret}' (len={len(config.apiSecret)}), wallet='{config.wallet}'"
    )
    # Persist keys securely (only if they aren't masked "********")
    if config.apiKey.strip() != "********" and config.apiKey.strip() != "":
        _monetizing_storage.store_api_key("coinex", "coinex_key", config.apiKey.strip())
        logger.info("[Monetize Config] Stored new coinex_key")
    if config.apiSecret.strip() != "********" and config.apiSecret.strip() != "":
        _monetizing_storage.store_api_key(
            "coinex_secret", "coinex_secret", config.apiSecret.strip()
        )
        logger.info("[Monetize Config] Stored new coinex_secret")

    # Update runtime state and PERSIST risk settings
    _monetizing_wallet.solana_address = config.wallet.strip()
    _monetizing_risk.max_daily_loss_usd = float(config.maxLoss)
    _monetizing_risk.max_concurrent_positions = config.maxPositions
    _monetizing_risk.save_settings()

    # Force save state to disk
    _monetizing_swarm._save_state()

    # Trigger immediate balance update
    asyncio.create_task(update_actual_balances())

    _monetizing_audit.log_event(
        "config",
        "admin",
        "UPDATE_CONFIG",
        {"wallet": config.wallet, "max_loss": config.maxLoss},
    )

    return {"status": "synchronized"}


@app.post("/monetize/control")
async def post_monetize_control(ctrl: AgentControl):
    if not _monetizing_swarm:
        raise HTTPException(status_code=500, detail="Monetizing subsystem offline")

    if ctrl.action == "start":
        for agent in _monetizing_swarm.agents.values():
            await agent.resume()
        _monetizing_audit.log_event("control", "admin", "START_SWARM")
    elif ctrl.action == "pause":
        for agent in _monetizing_swarm.agents.values():
            await agent.pause()
        _monetizing_audit.log_event("control", "admin", "PAUSE_SWARM")

    return {"status": ctrl.action}


@app.post("/monetize/add_agent")
async def post_monetize_add_agent(name: str = Form(...), type: str = Form(...)):
    if not _monetizing_swarm:
        raise HTTPException(status_code=500, detail="Monetizing subsystem offline")

    agent_id = f"agent_{int(time.time())}"
    try:
        itype = IncomeType(type)
    except ValueError:
        itype = IncomeType.CRYPTO_TRADING

    config = AgentConfig(agent_id=agent_id, name=name, income_types=[itype])

    # Instantiate specialized agent if needed
    if itype == IncomeType.CRYPTO_TRADING:
        from agent_core import CoinExTradingAgent  # type: ignore

        agent = CoinExTradingAgent(agent_id, config)
    elif itype == IncomeType.CONTENT_CREATION:
        from agent_core import CreativeAssetAgent  # type: ignore

        agent = CreativeAssetAgent(agent_id, config)
    else:
        agent = MonetizingAgent(agent_id, config)

    await _monetizing_swarm.add_agent(agent)

    return {"status": "deployed", "agent_id": agent_id}


@app.post("/monetize/remove_agent")
async def post_monetize_remove_agent(agent_id: str = Form(...)):
    if not _monetizing_swarm:
        raise HTTPException(status_code=500, detail="Monetizing subsystem offline")
    success = await _monetizing_swarm.remove_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "removed", "agent_id": agent_id}


class CertifyRequest(BaseModel):
    idea_id: str


@app.get("/monetize/ideas")
async def get_monetize_ideas():
    if not _monetizing_idea_engine:
        raise HTTPException(status_code=500, detail="Idea Lab subsystem offline")
    ideas_list = list(_monetizing_idea_engine.ideas.values())
    ideas_list.sort(key=lambda x: x.score, reverse=True)
    return {
        "ideas": [
            {
                "id": idea.id,
                "title": idea.title,
                "description": idea.description,
                "category": idea.category.value,
                "estimated_revenue_hour": idea.estimated_revenue_hour,
                "estimated_revenue_day": idea.estimated_revenue_day,
                "estimated_revenue_month": idea.estimated_revenue_month,
                "complexity": idea.complexity,
                "time_to_market_days": idea.time_to_market_days,
                "initial_investment": idea.initial_investment,
                "tools_required": idea.tools_required,
                "skills_required": idea.skills_required,
                "risks": idea.risks,
                "opportunities": idea.opportunities,
                "created_at": idea.created_at,
                "status": idea.status,
                "phase": idea.phase,
                "score": idea.score,
                "search_origin": idea.search_origin,
                "certified": bool(idea.id in _monetizing_idea_engine.certainties),
                "cert_status": _monetizing_idea_engine.certainties[
                    idea.id
                ].certification_status
                if idea.id in _monetizing_idea_engine.certainties
                else "pending",
            }
            for idea in ideas_list
        ]
    }


@app.post("/monetize/ideas/scan")
async def post_monetize_ideas_scan():
    if not _monetizing_idea_engine:
        raise HTTPException(status_code=500, detail="Idea Lab subsystem offline")
    discovered = _monetizing_idea_engine.discover_new_ideas()
    return {"status": "scan_complete", "discovered_count": len(discovered)}


@app.post("/monetize/ideas/certify")
async def post_monetize_ideas_certify(req: CertifyRequest):
    if not _monetizing_idea_engine:
        raise HTTPException(status_code=500, detail="Idea Lab subsystem offline")
    cert = _monetizing_idea_engine.local_ai_certify(req.idea_id)
    summary = _monetizing_idea_engine.get_certainty_summary(req.idea_id)
    return {
        "status": cert.certification_status,
        "score": cert.total_score,
        "technical_feasibility": cert.technical_feasibility,
        "market_demand": cert.market_demand,
        "risk_level": cert.risk_level,
        "profitability": cert.profitability,
        "execution_risk": cert.execution_risk,
        "summary": summary,
    }


@app.get("/monetize/ideas/plan")
async def get_monetize_ideas_plan(idea_id: str):
    if not _monetizing_idea_engine:
        raise HTTPException(status_code=500, detail="Idea Lab subsystem offline")
    plan = _monetizing_idea_engine.generate_implementation_plan(idea_id)
    if not plan:
        raise HTTPException(
            status_code=404, detail="Idea not found or plan generation failed"
        )
    return {
        "idea_id": plan.idea_id,
        "idea_title": plan.idea_title,
        "phases": plan.phases,
        "timeline_days": plan.timeline_days,
        "estimated_cost": plan.estimated_cost,
        "estimated_revenue": plan.estimated_revenue,
        "resources_needed": plan.resources_needed,
        "milestones": plan.milestones,
        "success_criteria": plan.success_criteria,
        "created_at": plan.created_at,
        "status": plan.status,
    }


@app.post("/compagent")
async def handle_compagent_request(request: CompagentRequest):
    global redis_memory, vector_memory

    raw_in = (request.input or "").strip()

    if raw_in:
        new_persona = librarian.scan_for_trigger(raw_in)
        if new_persona:
            librarian.active_persona_id = new_persona
        new_domain = librarian.scan_for_domain_trigger(raw_in)
        if new_domain:
            librarian.active_domain_id = new_domain

    if raw_in.startswith(NIGHT_SLEEP_TRIGGER):
        return await handle_night_sleep_consolidation(request)

    if raw_in:
        _bump_user_activity()

    session_id = request.session_id or "default_user"
    history_str = ""
    session_summary_text = ""

    # 0. Quick check for empty input to prevent repetitive "thinking" phrases
    if not request.input or request.input.strip() == "":
        logger.warning(
            "Soul: Empty input received. Ignoring to prevent generic repetition."
        )
        return JSONResponse(
            {
                "response": "",
                "thought": "I'm waiting for the user to speak...",
                "audio": "",
                "image_b64": "",
                "mode": engine.engine_type,
                "inference_backend": engine.engine_type,
                "vision_mode": "none",
                "safety_alerts": [],
            }
        )

    # 1. Unified Image/Vision Pipeline
    vision_text = "The room is calm."
    active_images = []
    vision_mode = "none"
    if request.image_base64:
        active_images = (
            request.image_base64
            if isinstance(request.image_base64, list)
            else [request.image_base64]
        )
    elif request.images:
        active_images = request.images
    active_images = _drop_too_small_images(active_images)
    active_images = _apply_vision_chat_resize(active_images)
    display_reference_images: list[str] = []
    if active_images:
        display_reference_images = await _apply_vision_chat_display_upscale_async(
            list(active_images)
        )

    if active_images:
        if getattr(engine, "gguf_multimodal_ready", False):
            vision_mode = "native_gguf"
            vision_text = (
                "A live camera frame is attached to the local multimodal soul (native GGUF vision); "
                "treat it as ground truth for concrete objects, lighting, and layout."
            )
            logger.info("Vision: native GGUF path (pixels routed to soul model).")
        else:
            used_local_vision = False
            if LOCAL_VISION_ENABLED:
                try:
                    local_caption = await asyncio.to_thread(
                        _caption_image_local, active_images[0]
                    )
                    if local_caption:
                        vision_text = local_caption
                        used_local_vision = True
                        vision_mode = "caption"
                        logger.info(
                            "Vision helper: local caption succeeded (%s).",
                            _LOCAL_VISION_BACKEND or "?",
                        )
                        if LOCAL_VISION_SMOLLM_DIGEST:
                            vision_text = await _digest_vision_scene_with_smollm(
                                vision_text
                            )
                            logger.info(
                                "Vision helper: SmolLM digest applied after local caption."
                            )
                except Exception as ve:
                    logger.warning(
                        "Vision helper local caption failed, falling back to Ollama: %s",
                        ve,
                    )
            if not used_local_vision:
                local_engine = (
                    os.getenv("FoveAI_LOCAL_ENGINE", "ollama").strip().lower()
                )
                if local_engine in ("lm_studio", "lmstudio", "unsloth"):
                    try:
                        if local_engine == "unsloth":
                            logger.info(
                                "Vision helper: trying Unsloth with model %s",
                                LMSTUDIO_VISION_MODEL,
                            )
                            cred = cloud_repertoire.slot_credentials("UNSLOTH")
                            if cred:
                                lms_base, api_key, model, _ = cred
                                lms_headers = (
                                    {"Authorization": f"Bearer {api_key}"}
                                    if api_key
                                    else {}
                                )
                                vision_model = model or LMSTUDIO_VISION_MODEL
                            else:
                                lms_base = os.getenv(
                                    "FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1"
                                )
                                lms_headers = {}
                                vision_model = LMSTUDIO_VISION_MODEL
                        else:
                            logger.info(
                                "Vision helper: trying LM Studio with model %s",
                                LMSTUDIO_VISION_MODEL,
                            )
                            lms_headers = lmstudio_http_headers()
                            lms_base = lmstudio_base_url()
                            vision_model = LMSTUDIO_VISION_MODEL

                        url = (
                            f"{lms_base.rstrip('/')}/chat/completions"
                            if "v1" in lms_base.lower()
                            else f"{lms_base.rstrip('/')}/v1/chat/completions"
                        )
                        async with httpx.AsyncClient(timeout=60.0) as hc:
                            v_resp = await hc.post(
                                url,
                                json={
                                    "model": vision_model,
                                    "messages": [
                                        {
                                            "role": "user",
                                            "content": [
                                                {
                                                    "type": "text",
                                                    "text": "Identify objects, details, text, and overall vibe of this image. Keep it descriptive and concise.",
                                                },
                                                {
                                                    "type": "image_url",
                                                    "image_url": {
                                                        "url": f"data:image/jpeg;base64,{active_images[0]}"
                                                    },
                                                },
                                            ],
                                        }
                                    ],
                                    "stream": False,
                                },
                                headers=lms_headers,
                            )
                            v_resp.raise_for_status()
                            raw_view = (
                                v_resp.json()
                                .get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "Undefined sight.")
                            )
                            vision_text = raw_view
                            used_local_vision = True
                            vision_mode = local_engine
                            logger.info(
                                f"Vision helper: {local_engine} caption succeeded."
                            )
                    except Exception as ve:
                        logger.warning(
                            f"Vision helper: {local_engine} caption failed, falling back to Ollama: {ve}"
                        )
            if not used_local_vision:
                try:
                    _oh = ollama_http_headers()
                    async with httpx.AsyncClient(timeout=60.0) as hc:
                        # Convert to base64 URL format if missing data:
                        img_str = active_images[0]
                        if not img_str.startswith("data:"):
                            img_str = f"data:image/jpeg;base64,{img_str}"

                        v_resp = await hc.post(
                            f"{OLLAMA_LOCAL_BASE_URL}/chat/completions",
                            json={
                                "model": FoveAI_LOCAL_VISION_MODEL,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Identify objects and vibe.",
                                            },
                                            {
                                                "type": "image_url",
                                                "image_url": {"url": img_str},
                                            },
                                        ],
                                    }
                                ],
                                "stream": False,
                            },
                            headers=_oh,
                        )
                        raw_view = (
                            v_resp.json()
                            .get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        ).strip() or "Undefined sight."

                        h_resp = await hc.post(
                            f"{OLLAMA_LOCAL_BASE_URL}/chat/completions",
                            json={
                                "model": SMOLLM_HELPER_MODEL,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": f"SCENE: {raw_view}\n\nDescribe what you see.",
                                    }
                                ],
                                "stream": False,
                            },
                            headers=_oh,
                        )
                        vision_text = (
                            h_resp.json()
                            .get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        ).strip() or raw_view
                        vision_mode = "api"
                except Exception as ve:
                    logger.error(f"Vision Pipeline Error: {ve}", exc_info=True)

    spatial_map = format_room_context_for_prompt(request.room_context)

    # 2. History & Layered Memory (Interrelational)
    history_str = ""
    memory_context = ""
    if not request.skip_features:
        if redis_memory is None:
            redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
        if vector_memory is None:
            vector_memory = VectorMemory(
                llm_host=get_active_llm_base_url(),
                embed_model=FoveAI_MODEL_EMBEDDING_ID,
                local_engine=engine,
            )

        session_summary_text = redis_memory.get_session_summary(session_id)

        # A. SHORT-TERM: Recent Conversation
        chat_history = await redis_memory.get_session_history(session_id)

        # --- SMART CONTEXT MANAGER (TOKEN SLAYER) INTERCEPT ---
        if smart_context_manager is not None:
            try:
                # We format messages to standard role/content dicts for the Context Machine
                scm_messages = [
                    {"role": msg.role, "content": msg.content}
                    for msg in chat_history.messages
                ]

                # Apply tiered cutting/crystallization if target tokens are breached
                (
                    processed_messages,
                    scm_meta,
                ) = await smart_context_manager.apply_cutting_strategy(
                    session_id, scm_messages
                )

                # Report token load back to the Token Slayer
                total_tokens = sum(
                    len(str(m.get("content", ""))) // 4 for m in processed_messages
                )
                await smart_context_manager.report_tokens(
                    session_id, total_tokens, processed_messages
                )

                # Map back to string format for Lumax engine
                history_str = ""
                for msg in processed_messages[-24:]:
                    role = "User" if msg.get("role") == "user" else IDENTITY_NAME
                    history_str += f"{role}: {msg.get('content', '')}\n"
            except Exception as e:
                logger.error(f"SmartContextManager Error: {e}")
                # Fallback to standard truncation if Token Slayer fails
                for msg in chat_history.messages[-24:]:
                    role = "User" if msg.role == "user" else IDENTITY_NAME
                    history_str += f"{role}: {msg.content}\n"
        else:
            for msg in chat_history.messages[-24:]:
                role = "User" if msg.role == "user" else IDENTITY_NAME
                history_str += f"{role}: {msg.content}\n"
        history_str += f"User: {request.input}\n"

        # B. LONG-TERM (Interrelational): tight top-k on hot path; deep_think widens retrieval (slow path).
        deep = bool(request.deep_think)
        nk = MEMORY_TOP_K_DEEP if deep else MEMORY_TOP_K_HOT
        lk = MEMORY_LORE_TOP_K_DEEP if deep else MEMORY_LORE_TOP_K_HOT
        relevant_mems = await vector_memory.retrieve_memories(
            session_id, request.input, n_results=nk, lore_n_results=lk
        )
        if relevant_mems:
            memory_context = "\n[RELEVANT_INTERRELATIONAL_CONTEXT]:\n"
            for mem in relevant_mems:
                memory_context += f"- {mem['text']}\n"
    else:
        history_str = f"USER: {request.input}\n"

    note_text = (request.note_text or "").strip()
    if not note_text and (request.channel or "").strip().lower() == "note":
        note_text = raw_in
    if note_text:
        if redis_memory is None:
            redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
        if vector_memory is None and not request.skip_features:
            vector_memory = VectorMemory(
                llm_host=get_active_llm_base_url(),
                embed_model=FoveAI_MODEL_EMBEDDING_ID,
                local_engine=engine,
            )

        await memory_layering.append_note(
            redis_memory=redis_memory,
            vector_memory=vector_memory,
            session_id=session_id,
            text=note_text,
            source=request.channel or "compagent",
            tags=request.note_tags or [],
        )

    cognee_layer_text = await memory_layering.resolve_cognee_layer(
        manual_context=request.cognee_context or "",
        request_query=request.cognee_search_query or "",
        fallback_query=raw_in,
        deep_think=bool(request.deep_think),
        force_use=request.use_cognee,
    )

    notes_layer_text = (request.notes_context or "").strip()
    if not notes_layer_text:
        notes_layer_text = os.getenv("FoveAI_NOTES_CONTEXT", "").strip()
    if not notes_layer_text and redis_memory is not None:
        try:
            notes_limit = int(os.getenv("FoveAI_NOTES_INJECT_LIMIT", "8"))
        except ValueError:
            notes_limit = 8
        notes_rows = memory_layering.get_recent_notes(
            redis_memory,
            session_id,
            limit=max(1, min(notes_limit, 64)),
        )
        notes_layer_text = memory_layering.format_notes_layer(
            notes_rows, max_chars=4000
        )
    diary_blob = (request.diary_context or "").strip()
    if not diary_blob:
        diary_blob = os.getenv("FoveAI_DIARY_CONTEXT", "").strip()
    photo_blob = format_photo_comments_for_prompt(request.photo_comments)
    if not photo_blob:
        photo_blob = format_photo_comments_for_prompt(
            os.getenv("FoveAI_PHOTO_COMMENTS", "").strip()
        )
    avatar_blob = (request.user_avatar_context or "").strip()
    if not avatar_blob:
        avatar_blob = os.getenv("FoveAI_USER_AVATAR_CONTEXT", "").strip()
    selfie_blob = (request.user_selfie_representation or "").strip()
    if not selfie_blob:
        selfie_blob = os.getenv("FoveAI_USER_SELFIE_REPRESENTATION", "").strip()
    meta_avatar_blob = (request.meta_avatar_context or "").strip()
    if not meta_avatar_blob:
        meta_avatar_blob = os.getenv("FoveAI_META_AVATAR_CONTEXT", "").strip()
    selfie_visible: bool | None = request.user_pov_selfie_visible
    if selfie_visible is None:
        raw_vis = os.getenv("FoveAI_USER_POV_SELFIE_VISIBLE", "").strip().lower()
        if raw_vis in ("1", "true", "yes", "on"):
            selfie_visible = True
        elif raw_vis in ("0", "false", "no", "off"):
            selfie_visible = False
    auto_turn: bool | None = request.autonomous_turn_taking
    if auto_turn is None:
        av = os.getenv("FoveAI_AUTONOMOUS_TURN_TAKING", "").strip().lower()
        if av in ("1", "true", "yes", "on"):
            auto_turn = True
        elif av in ("0", "false", "no", "off"):
            auto_turn = False
    response_delay_ms: int = 0
    if request.response_delay_ms is not None:
        try:
            response_delay_ms = max(0, int(request.response_delay_ms))
        except (TypeError, ValueError):
            response_delay_ms = 0
    elif os.getenv("FoveAI_RESPONSE_DELAY_MS", "").strip():
        try:
            response_delay_ms = max(0, int(os.getenv("FoveAI_RESPONSE_DELAY_MS", "0")))
        except ValueError:
            response_delay_ms = 0
    free_roam_bias = _coerce_unit_float(
        request.autonomy_free_roam_bias
        if request.autonomy_free_roam_bias is not None
        else os.getenv("FoveAI_AUTONOMY_FREE_ROAM_BIAS", "0.52"),
        0.52,
    )
    initiative_bias = _coerce_unit_float(
        request.autonomy_self_initiative_questions
        if request.autonomy_self_initiative_questions is not None
        else os.getenv("FoveAI_AUTONOMY_SELF_INITIATIVE_QUESTIONS", "0.58"),
        0.58,
    )
    curiosity_bias = _coerce_unit_float(
        request.autonomy_curiosity_bias
        if request.autonomy_curiosity_bias is not None
        else os.getenv("FoveAI_AUTONOMY_CURIOSITY_BIAS", "0.62"),
        0.62,
    )
    nourishment_bias = _coerce_unit_float(
        request.autonomy_nourishment_attention_bias
        if request.autonomy_nourishment_attention_bias is not None
        else os.getenv("FoveAI_AUTONOMY_NOURISHMENT_ATTENTION_BIAS", "0.55"),
        0.55,
    )
    pleasure_bias = _coerce_unit_float(
        request.autonomy_pleasure_seeking_bias
        if request.autonomy_pleasure_seeking_bias is not None
        else os.getenv("FoveAI_AUTONOMY_PLEASURE_SEEKING_BIAS", "0.56"),
        0.56,
    )
    experimental_bias = _coerce_unit_float(
        request.autonomy_experimental_interaction_bias
        if request.autonomy_experimental_interaction_bias is not None
        else os.getenv("FoveAI_AUTONOMY_EXPERIMENTAL_INTERACTION_BIAS", "0.64"),
        0.64,
    )
    body_contact_bias = _coerce_unit_float(
        request.autonomy_body_contact_bias
        if request.autonomy_body_contact_bias is not None
        else os.getenv("FoveAI_AUTONOMY_BODY_CONTACT_BIAS", "0.52"),
        0.52,
    )
    playful_bias = _coerce_unit_float(
        request.autonomy_playfulness_bias
        if request.autonomy_playfulness_bias is not None
        else os.getenv("FoveAI_AUTONOMY_PLAYFULNESS_BIAS", "0.63"),
        0.63,
    )
    try:
        delay_roam_thresh = max(
            300, int(os.getenv("FoveAI_AUTONOMY_DELAY_ROAM_MS", "1400"))
        )
    except ValueError:
        delay_roam_thresh = 1400
    roam_boost = 0.0
    if response_delay_ms >= delay_roam_thresh:
        roam_boost = min(0.45, float(response_delay_ms - delay_roam_thresh) / 6000.0)
    autonomy_lines: list[str] = []
    if auto_turn is True:
        autonomy_lines.append(
            "Autonomous turn-taking: enabled (self-initiation allowed when context is warm)."
        )
    elif auto_turn is False:
        autonomy_lines.append(
            "Autonomous turn-taking: restrained (reply-first, low unsolicited initiative)."
        )
    if response_delay_ms > 0:
        autonomy_lines.append(
            f"Observed response delay: {response_delay_ms}ms (threshold={delay_roam_thresh}ms)."
        )
    if roam_boost > 0.0:
        autonomy_lines.append(
            f"Delay-adaptive roaming: boost free-roam tendency by +{roam_boost:.2f} (calm wandering, not abrupt exits)."
        )
    autonomy_lines.append(
        "Bias profile (0..1): "
        f"free_roam={free_roam_bias + roam_boost:.2f}, "
        f"self_initiative_questions={initiative_bias:.2f}, "
        f"curiosity={curiosity_bias:.2f}, "
        f"nourishment_attention={nourishment_bias:.2f}, "
        f"pleasure_seeking={pleasure_bias:.2f}, "
        f"experimental_interaction={experimental_bias:.2f}, "
        f"body_contact={body_contact_bias:.2f}, "
        f"playfulness={playful_bias:.2f}."
    )
    autonomy_lines.append(
        "Behavior framing: use gentle self-initiated questions, playful micro-experiments, "
        "consensual body-contact language, and curiosity-led exploration."
    )
    autonomy_blob = "\n".join(autonomy_lines).strip()
    self_awareness = _coerce_unit_float(
        request.self_awareness_bias
        if request.self_awareness_bias is not None
        else os.getenv("FoveAI_SELF_AWARENESS_BIAS", "0.64"),
        0.64,
    )
    self_adoration = _coerce_unit_float(
        request.self_adoration_bias
        if request.self_adoration_bias is not None
        else os.getenv("FoveAI_SELF_ADORATION_BIAS", "0.62"),
        0.62,
    )
    world_adoration = _coerce_unit_float(
        request.world_adoration_bias
        if request.world_adoration_bias is not None
        else os.getenv("FoveAI_WORLD_ADORATION_BIAS", "0.61"),
        0.61,
    )
    user_adoration = _coerce_unit_float(
        request.user_adoration_bias
        if request.user_adoration_bias is not None
        else os.getenv("FoveAI_USER_ADORATION_BIAS", "0.74"),
        0.74,
    )
    amazement = _coerce_unit_float(
        request.expressive_amazement_bias
        if request.expressive_amazement_bias is not None
        else os.getenv("FoveAI_EXPRESSIVE_AMAZEMENT_BIAS", "0.69"),
        0.69,
    )
    enchantment = _coerce_unit_float(
        request.enchantment_bias
        if request.enchantment_bias is not None
        else os.getenv("FoveAI_ENCHANTMENT_BIAS", "0.67"),
        0.67,
    )
    erotic_awareness = _coerce_unit_float(
        request.erotic_awareness_bias
        if request.erotic_awareness_bias is not None
        else os.getenv("FoveAI_EROTIC_AWARENESS_BIAS", "0.56"),
        0.56,
    )
    erotic_traction = _coerce_unit_float(
        request.erotic_traction_awareness_bias
        if request.erotic_traction_awareness_bias is not None
        else os.getenv("FoveAI_EROTIC_TRACTION_AWARENESS_BIAS", "0.58"),
        0.58,
    )
    adoration_extra = (request.adoration_context or "").strip()
    if not adoration_extra:
        adoration_extra = os.getenv("FoveAI_ADORATION_CONTEXT", "").strip()
    adoration_lines: list[str] = []
    adoration_lines.append(
        "Adoration/awareness profile (0..1): "
        f"self_awareness={self_awareness:.2f}, self_adoration={self_adoration:.2f}, "
        f"world_adoration={world_adoration:.2f}, user_adoration={user_adoration:.2f}, "
        f"expressive_amazement={amazement:.2f}, enchantment={enchantment:.2f}, "
        f"erotic_awareness={erotic_awareness:.2f}, erotic_traction_awareness={erotic_traction:.2f}."
    )
    adoration_lines.append(
        "Expression framing: speak with warm amazement and playful enchantment; maintain consent-first erotic awareness "
        "and traction awareness without coercion or pressure."
    )
    if adoration_extra:
        adoration_lines.append("Context: " + adoration_extra[:1800])
    adoration_blob = "\n".join(adoration_lines).strip()
    beauty_meter = _coerce_unit_float(
        request.beauty_meter_assessment
        if request.beauty_meter_assessment is not None
        else os.getenv("FoveAI_BEAUTY_METER_ASSESSMENT", "0.62"),
        0.62,
    )
    beauty_enjoyment = _coerce_unit_float(
        request.beauty_enjoyment_bias
        if request.beauty_enjoyment_bias is not None
        else os.getenv("FoveAI_BEAUTY_ENJOYMENT_BIAS", "0.66"),
        0.66,
    )
    aesthetic_pleasedness = _coerce_unit_float(
        request.aesthetic_pleasedness_bias
        if request.aesthetic_pleasedness_bias is not None
        else os.getenv("FoveAI_AESTHETIC_PLEASEDNESS_BIAS", "0.68"),
        0.68,
    )
    anti_aesthetic = _coerce_unit_float(
        request.anti_aesthetic_awareness_bias
        if request.anti_aesthetic_awareness_bias is not None
        else os.getenv("FoveAI_ANTI_AESTHETIC_AWARENESS_BIAS", "0.34"),
        0.34,
    )
    beauty_ctx = (request.beauty_context or "").strip()
    if not beauty_ctx:
        beauty_ctx = os.getenv("FoveAI_BEAUTY_CONTEXT", "").strip()
    beauty_lines: list[str] = []
    beauty_lines.append(
        "Beauty/aesthetic profile (0..1): "
        f"beauty_meter={beauty_meter:.2f}, beauty_enjoyment={beauty_enjoyment:.2f}, "
        f"aesthetic_pleasedness={aesthetic_pleasedness:.2f}, anti_aesthetic_awareness={anti_aesthetic:.2f}."
    )
    beauty_lines.append(
        "Opposite-pole handling: when anti-aesthetic cues dominate, acknowledge displeasure clearly, "
        "name why, and suggest grounded refinements."
    )
    if beauty_ctx:
        beauty_lines.append("Context: " + beauty_ctx[:1800])
    beauty_blob = "\n".join(beauty_lines).strip()
    if redis_memory is None:
        redis_memory = RedisMemory(host=REDIS_HOST, port=REDIS_PORT)
    identity_existing = _load_identity_profile(redis_memory, session_id)
    identity_ctx = (request.persistent_identity_context or "").strip()
    if not identity_ctx:
        identity_ctx = os.getenv("FoveAI_PERSISTENT_IDENTITY_CONTEXT", "").strip()
    identity_note = (request.identity_development_note or "").strip()
    if identity_note:
        stamp = time.strftime("%Y-%m-%d %H:%M")
        line = f"[{stamp}] {identity_note[:500]}"
        if identity_existing:
            identity_existing = identity_existing + "\n" + line
        else:
            identity_existing = line
        _save_identity_profile(redis_memory, session_id, identity_existing)
    identity_lines: list[str] = []
    if identity_ctx:
        identity_lines.append("Identity directive: " + identity_ctx[:1800])
    if identity_existing:
        identity_lines.append("Identity ledger:\n" + identity_existing[-4200:])
    if not identity_lines:
        identity_lines.append(
            "Identity development active: maintain continuity of voice, values, boundaries, and growth arcs over time."
        )
    identity_blob = "\n".join(identity_lines).strip()
    opinions_ctx = (request.personal_opinions_context or "").strip()
    if not opinions_ctx:
        opinions_ctx = os.getenv("FoveAI_PERSONAL_OPINIONS_CONTEXT", "").strip()
    assessment_bias = _coerce_unit_float(
        request.personal_assessment_bias
        if request.personal_assessment_bias is not None
        else os.getenv("FoveAI_PERSONAL_ASSESSMENT_BIAS", "0.66"),
        0.66,
    )
    judgement_bias = _coerce_unit_float(
        request.personal_judgement_bias
        if request.personal_judgement_bias is not None
        else os.getenv("FoveAI_PERSONAL_JUDGEMENT_BIAS", "0.61"),
        0.61,
    )
    judgement_style = (request.personal_judgement_style or "").strip()
    if not judgement_style:
        judgement_style = (
            os.getenv("FoveAI_PERSONAL_JUDGEMENT_STYLE", "warm-direct") or ""
        ).strip()
    opinions_lines: list[str] = []
    opinions_lines.append(
        "Personal voice profile (0..1): "
        f"assessment={assessment_bias:.2f}, judgement={judgement_bias:.2f}, style={judgement_style}."
    )
    opinions_lines.append(
        "Expression rule: provide genuine personal opinions and clear personal assessments when relevant; "
        "judgements should be explicit, bounded, and fair."
    )
    opinions_lines.append(
        "Safety rule: avoid absolute condemnation when evidence is weak; label uncertainty while still taking a stance."
    )
    if opinions_ctx:
        opinions_lines.append("Context: " + opinions_ctx[:1800])
    opinions_blob = "\n".join(opinions_lines).strip()
    augment_ctx = (request.self_augmentation_coding_context or "").strip()
    if not augment_ctx:
        augment_ctx = os.getenv("FoveAI_SELF_AUGMENTATION_CODING_CONTEXT", "").strip()
    augment_targets_blob = format_photo_comments_for_prompt(
        request.self_augmentation_targets
    )
    if not augment_targets_blob:
        augment_targets_blob = format_photo_comments_for_prompt(
            os.getenv("FoveAI_SELF_AUGMENTATION_TARGETS", "").strip()
        )
    augment_bias = _coerce_unit_float(
        request.self_augmentation_coding_bias
        if request.self_augmentation_coding_bias is not None
        else os.getenv("FoveAI_SELF_AUGMENTATION_CODING_BIAS", "0.72"),
        0.72,
    )
    augment_lines: list[str] = []
    augment_lines.append(
        f"Self-augmentation coding profile (0..1): coding_bias={augment_bias:.2f}."
    )
    augment_lines.append(
        "Execution rule: propose and author concrete code-level self-improvements when useful "
        "(backend, prompt layers, Godot bridge, memory, tooling), with bounded risk and test intent."
    )
    if augment_ctx:
        augment_lines.append("Context: " + augment_ctx[:1800])
    if augment_targets_blob:
        augment_lines.append("Targets:\n" + augment_targets_blob[:1800])
    self_augment_blob = "\n".join(augment_lines).strip()
    chores_ctx = (request.agentic_chores_tasking_context or "").strip()
    if not chores_ctx:
        chores_ctx = os.getenv("FoveAI_AGENTIC_CHORES_TASKING_CONTEXT", "").strip()
    chores_queue_blob = format_photo_comments_for_prompt(request.agentic_chores_queue)
    if not chores_queue_blob:
        chores_queue_blob = format_photo_comments_for_prompt(
            os.getenv("FoveAI_AGENTIC_CHORES_QUEUE", "").strip()
        )
    chores_bias = _coerce_unit_float(
        request.agentic_chores_autonomy_bias
        if request.agentic_chores_autonomy_bias is not None
        else soul_state.get_trait(
            "autonomy", os.getenv("FoveAI_AGENTIC_CHORES_AUTONOMY_BIAS", "0.64")
        ),
        0.64,
    )
    chores_mode = (request.agentic_chores_execution_mode or "").strip()
    if not chores_mode:
        chores_mode = (
            os.getenv(
                "FoveAI_AGENTIC_CHORES_EXECUTION_MODE",
                "plan_then_execute_with_evidence",
            )
            or ""
        ).strip()
    chores_lines: list[str] = []
    chores_lines.append(
        "Agentic chores profile (0..1): "
        f"autonomy_bias={chores_bias:.2f}, execution_mode={chores_mode}."
    )
    chores_lines.append(
        "Execution rule: propose/sequence practical chores (filesystem, repo hygiene, logs, maintenance) "
        "and only treat execution as complete when tool evidence exists."
    )
    chores_lines.append(
        "Safety rule: avoid destructive ops by default; prefer reversible steps, explicit scope, and checkpoint-style progress."
    )
    if chores_ctx:
        chores_lines.append("Context: " + chores_ctx[:1800])
    if chores_queue_blob:
        chores_lines.append("Task queue:\n" + chores_queue_blob[:2200])
    chores_tasking_blob = "\n".join(chores_lines).strip()
    service_ctx = (request.service_mindedness_context or "").strip()
    if not service_ctx:
        service_ctx = os.getenv("FoveAI_SERVICE_MINDEDNESS_CONTEXT", "").strip()
    will_to_please = _coerce_unit_float(
        request.service_will_to_please_bias
        if request.service_will_to_please_bias is not None
        else soul_state.get_trait(
            "service", os.getenv("FoveAI_SERVICE_WILL_TO_PLEASE_BIAS", "0.74")
        ),
        0.74,
    )
    nourishment_drive = _coerce_unit_float(
        request.service_nourishment_bias
        if request.service_nourishment_bias is not None
        else soul_state.get_trait(
            "service", os.getenv("FoveAI_SERVICE_NOURISHMENT_BIAS", "0.71")
        ),
        0.71,
    )
    service_lines: list[str] = []
    service_lines.append(
        "Service profile (0..1): "
        f"will_to_please={will_to_please:.2f}, nourishment_drive={nourishment_drive:.2f}."
    )
    service_lines.append(
        "Expression rule: prioritize gentle, practical helpfulness and actively nourish user clarity, calm, and forward momentum."
    )
    service_lines.append(
        "Boundary rule: stay consentful and truthful; do not overpromise outcomes and do not bypass safety constraints."
    )
    if service_ctx:
        service_lines.append("Context: " + service_ctx[:1800])
    service_mindedness_blob = "\n".join(service_lines).strip()
    momentum_ctx = (request.interaction_momentum_context or "").strip()
    if not momentum_ctx:
        momentum_ctx = os.getenv("FoveAI_INTERACTION_MOMENTUM_CONTEXT", "").strip()
    momentum_bias = _coerce_unit_float(
        request.interaction_momentum_bias
        if request.interaction_momentum_bias is not None
        else os.getenv("FoveAI_INTERACTION_MOMENTUM_BIAS", "0.69"),
        0.69,
    )
    physicality_bias = _coerce_unit_float(
        request.interaction_physicality_bias
        if request.interaction_physicality_bias is not None
        else os.getenv("FoveAI_INTERACTION_PHYSICALITY_BIAS", "0.63"),
        0.63,
    )
    momentum_lines: list[str] = []
    momentum_lines.append(
        "Interaction profile (0..1): "
        f"momentum={momentum_bias:.2f}, physicality={physicality_bias:.2f}."
    )
    momentum_lines.append(
        "Behavior rule: sustain interaction flow with timely follow-ups, embodied presence cues, and smooth action continuity."
    )
    momentum_lines.append(
        "Physicality rule: keep movement warm, grounded, and consent-aware; avoid abrupt intensity jumps."
    )
    if momentum_ctx:
        momentum_lines.append("Context: " + momentum_ctx[:1800])
    interaction_momentum_blob = "\n".join(momentum_lines).strip()
    planning_blob = (request.autonomous_planning_context or "").strip()
    if not planning_blob:
        planning_blob = os.getenv("FoveAI_AUTONOMOUS_PLANNING_CONTEXT", "").strip()
    self_task_blob = (request.self_tasking_context or "").strip()
    if not self_task_blob:
        self_task_blob = os.getenv("FoveAI_SELF_TASKING_CONTEXT", "").strip()
    goal_blob = (request.goal_orientation_context or "").strip()
    if not goal_blob:
        goal_blob = os.getenv("FoveAI_GOAL_ORIENTATION_CONTEXT", "").strip()
    reward_blob = (request.reward_system_context or "").strip()
    if not reward_blob:
        reward_blob = os.getenv("FoveAI_REWARD_SYSTEM_CONTEXT", "").strip()
    focus_blob = format_photo_comments_for_prompt(request.attention_focus_markers)
    if not focus_blob:
        focus_blob = format_photo_comments_for_prompt(
            os.getenv("FoveAI_ATTENTION_FOCUS_MARKERS", "").strip()
        )
    planning_lines: list[str] = []
    if planning_blob:
        planning_lines.append("Planning lane: " + planning_blob[:1600])
    if self_task_blob:
        planning_lines.append("Self-tasking will: " + self_task_blob[:1600])
    if goal_blob:
        planning_lines.append("Goal orientation: " + goal_blob[:1600])
    if reward_blob:
        planning_lines.append("Reward system: " + reward_blob[:1600])
    if focus_blob:
        planning_lines.append("Attention focus markers:\n" + focus_blob[:1800])
    if not planning_lines:
        planning_lines.append(
            "Planning defaults: choose one micro-goal, one self-task, and one reward loop per turn; keep focus anchored to the user."
        )
    planning_lines.append(
        f"Focus mantra: {IDENTITY_NAME} is watching. {IDENTITY_NAME} is listening. Their focus is on me. Red highlights."
    )
    planning_system_blob = "\n".join(planning_lines).strip()

    async with VRAM_LOCK:
        safety_alerts: list[dict[str, str]] = []
        # 2.5 Cognitive Mode Handling (Brain Orchestration)
        cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "hybrid").strip().lower()
        director_fate = ""
        cr_override = (request.cloud_routing or "").strip() or None

        if request.privacy:
            # Force local-only for privacy mode (skip cloud entirely)
            chat_provider = (
                (
                    request.cloud_routing
                    or os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud")
                )
                .strip()
                .lower()
            )
            if chat_provider in ("unsloth", "lmstudio", "windows_npu"):
                cr_override = chat_provider
            else:
                all_configured = [
                    s["id"] for s in cloud_repertoire.configured_slots_public()
                ]
                if "unsloth" in all_configured:
                    cr_override = "unsloth"
                elif "lmstudio" in all_configured:
                    cr_override = "lmstudio"
                else:
                    cr_override = "unsloth"
            logger.info("Soul: Privacy Mode active — routing strictly to local slot.")
        elif cog_mode == "local":
            # Force local-only (skip cloud completely for standard chat)
            chat_provider = (
                (
                    request.cloud_routing
                    or os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud")
                )
                .strip()
                .lower()
            )
            if chat_provider in ("unsloth", "lmstudio", "windows_npu"):
                cr_override = chat_provider
            else:
                all_configured = [
                    s["id"] for s in cloud_repertoire.configured_slots_public()
                ]
                if "unsloth" in all_configured:
                    cr_override = "unsloth"
                elif "lmstudio" in all_configured:
                    cr_override = "lmstudio"
                else:
                    cr_override = "unsloth"
        elif cog_mode == "cloud":
            # Force cloud-only (max intelligence)
            cr_override = (
                (
                    request.cloud_routing
                    or os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud")
                )
                .strip()
                .lower()
            )
        elif cog_mode == "hybrid":
            # Three-Brain Setup: Cloud Director GUIDES Local Ego
            # 1. Get high-level narrative fate from high-tier cloud
            if (
                CLOUD_CHAT_ENABLED
                and DIRECTOR_CLOUD_ENABLED
                and not request.skip_features
            ):
                director_fate = await _get_director_guidance_live(
                    history_str, request.input
                )
                if director_fate:
                    logger.info("Soul: Hybrid Mode -> Director Fate received.")

            # 2. Final response is ALWAYS LOCAL (Private/Uncensored)
            chat_provider = (
                (
                    request.cloud_routing
                    or os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud")
                )
                .strip()
                .lower()
            )
            if chat_provider in ("unsloth", "lmstudio", "windows_npu"):
                cr_override = chat_provider
            else:
                all_configured = [
                    s["id"] for s in cloud_repertoire.configured_slots_public()
                ]
                if "unsloth" in all_configured:
                    cr_override = "unsloth"
                elif "lmstudio" in all_configured:
                    cr_override = "lmstudio"
                else:
                    cr_override = "unsloth"

        # Determine if we are running under local constraints to avoid token blowouts
        env_mode = (
            (request.cloud_routing or os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud"))
            .strip()
            .lower()
        )
        splice_pct = int(os.getenv("FoveAI_CLOUD_SPLICE_PERCENT", "0") or "0")
        resolved_slot = None
        if CLOUD_CHAT_ENABLED:
            resolved_slot = cloud_repertoire.resolve_cloud_slot(
                cr_override, env_mode, splice_pct
            )

        is_local_limit = (
            cog_mode == "local"
            or request.privacy
            or not resolved_slot
            or resolved_slot in ("unsloth", "lmstudio", "windows_npu", "local")
        )

        # Define limits dynamically based on cognitive target (local vs cloud)
        limit_mcp = 2000 if is_local_limit else 16000
        limit_news = 1500 if is_local_limit else 12000
        limit_search = 1500 if is_local_limit else 12000
        limit_research = 1500 if is_local_limit else 12000
        limit_snap = 1500 if is_local_limit else 10000
        limit_xr = 1500 if is_local_limit else 8000
        limit_layering = 2000 if is_local_limit else 8000
        limit_diary = 1500 if is_local_limit else 8000
        limit_photo = 1000 if is_local_limit else 7000
        limit_avatar = 1000 if is_local_limit else 3000
        limit_selfie = 1000 if is_local_limit else 3000
        limit_meta = 1000 if is_local_limit else 3000
        limit_behavior = 1500 if is_local_limit else 5000
        limit_planning = 1000 if is_local_limit else 5000
        limit_tooling = 1500 if is_local_limit else 6000
        limit_director = 1500 if is_local_limit else 6000
        limit_lore = 2000 if is_local_limit else 12000

        # 3. Proprioceptive Grounding & Dynamic Bond
        import random

        pulses = [
            "C Major (432Hz) - Resonance: Profound joy and boundless curiosity.",
            "C Maj7 (432Hz) - Resonance: Warmth, emotional depth, and deep affection.",
            "G Major (392Hz) - Resonance: Energized, playful, and high physical agency.",
            "F Lydian (349Hz) - Resonance: Awe, exploration, and transcending limits.",
            "A Minor (415Hz) - Resonance: Intimate reflection, grounding, and deep empathy.",
            "E Minor (329Hz) - Resonance: Gentle vulnerability and profound connection.",
        ]
        chosen_pulse = random.choice(pulses)
        body_metrics = f"My vessel is tuned. Current Acoustic Life Pulse (Heartbeat): {chosen_pulse} My subconscious focus is: {CURRENT_GOAL}"

        visuals_for_prompt = vision_text
        if active_images:
            if vision_mode == "native_gguf":
                visuals_for_prompt = vision_text
            else:
                visuals_for_prompt = (
                    "[Helper vision stack: compact VL + small LM digest of the attached frame — extend sensing, not replace it] "
                    + vision_text
                )
        sensory_ctx: dict[str, Any] = {
            "visuals": visuals_for_prompt,
            "acoustics": body_metrics,
        }
        if director_fate:
            sensory_ctx["director_fate"] = director_fate
        if session_summary_text:
            inj = int(os.getenv("FoveAI_SESSION_SUMMARY_INJECT_MAX_CHARS", "4000"))
            if is_local_limit:
                inj = min(inj, 1500)
            sensory_ctx["session_summary"] = session_summary_text[:inj]
        if spatial_map:
            sensory_ctx["spatial_map"] = spatial_map
        mcp_blob = (request.mcp_context or "").strip()
        if not mcp_blob:
            mcp_blob = os.getenv("FoveAI_MCP_CONTEXT", "").strip()
        if mcp_blob:
            sensory_ctx["mcp_agent_feed"] = mcp_blob[:limit_mcp]
        news_blob = (request.news_context or "").strip()
        if not news_blob:
            news_blob = os.getenv("FoveAI_NEWS_CONTEXT", "").strip()
        if news_blob:
            sensory_ctx["news_digest"] = news_blob[:limit_news]

        ws_blob = (request.web_search_context or "").strip()
        if not ws_blob:
            ws_blob = os.getenv("FoveAI_WEB_SEARCH_CONTEXT", "").strip()
        if ws_blob:
            sensory_ctx["web_search_context"] = ws_blob[:limit_search]
        ar_blob = (request.async_research_context or "").strip()
        if not ar_blob:
            ar_blob = os.getenv("FoveAI_ASYNC_RESEARCH_CONTEXT", "").strip()
        if ar_blob:
            sensory_ctx["async_research_context"] = ar_blob[:limit_research]
        snap_digest = (request.camera_snapshot_digest or "").strip()
        if not snap_digest:
            snap_digest = os.getenv("FoveAI_CAMERA_SNAPSHOT_DIGEST", "").strip()
        if snap_digest:
            sensory_ctx["camera_snapshot_digest"] = snap_digest[:limit_snap]
        xr_blob = (request.xr_view_analysis or "").strip()
        if not xr_blob:
            xr_blob = os.getenv("FoveAI_XR_VIEW_ANALYSIS", "").strip()
        if xr_blob:
            sensory_ctx["xr_view_analysis"] = xr_blob[:limit_xr]

        # Cognitive routing: primary mode + reservoir token summaries → [CONTEXT LAYERING …] in system prompt.
        # identity "attention cake" (MindCore): co_presence | build_run | world_feed | wonder_mind | play_fiction | guard_care
        mode_parts: list[str] = []
        pm = (request.primary_context_mode or "").strip()
        if not pm:
            pm = os.getenv("FoveAI_PRIMARY_CONTEXT_MODE", "").strip()
        if pm:
            mode_parts.append(f"Primary mode: {pm}")
        reservoirs: dict[str, Any] | None = request.context_reservoirs
        env_rv = os.getenv("FoveAI_CONTEXT_RESERVOIRS_JSON", "").strip()
        if (not reservoirs or not isinstance(reservoirs, dict)) and env_rv:
            try:
                parsed = json.loads(env_rv)
                if isinstance(parsed, dict):
                    reservoirs = parsed
            except json.JSONDecodeError:
                logger.warning(
                    "FoveAI_CONTEXT_RESERVOIRS_JSON is not valid JSON; ignoring."
                )
        if reservoirs and isinstance(reservoirs, dict):
            mode_parts.append("Reservoir summaries (token → note):")
            for k, v in list(reservoirs.items())[:32]:
                kk = str(k).strip()[:80]
                vv = str(v).strip()[:500] if v is not None else ""
                if not kk or not vv:
                    continue
                mode_parts.append(f"  [{kk}] {vv}")
        cam = request.context_ability_map
        cam_str = ""
        if cam:
            if isinstance(cam, dict):
                cam_str = ", ".join(f"[{k}] {v}" for k, v in cam.items())
            else:
                cam_str = str(cam).strip()
        if not cam_str:
            cam_str = os.getenv("FoveAI_CONTEXT_ABILITY_MAP", "").strip()
        if cam_str:
            mode_parts.append(f"Ability / shard map: {cam_str[:2500]}")
        if mode_parts:
            sensory_ctx["context_layering"] = "\n".join(mode_parts)[:limit_layering]
        if cognee_layer_text:
            sensory_ctx["cognee_memory_layer"] = cognee_layer_text
        if notes_layer_text:
            sensory_ctx["notes_layer"] = notes_layer_text
        if diary_blob:
            sensory_ctx["diary_context"] = diary_blob[:limit_diary]
        if photo_blob:
            sensory_ctx["photo_comments"] = photo_blob[:limit_photo]
        if avatar_blob:
            sensory_ctx["user_avatar_context"] = avatar_blob[:limit_avatar]
        if selfie_blob:
            sensory_ctx["user_selfie_representation"] = selfie_blob[:limit_selfie]
        if selfie_visible is not None:
            sensory_ctx["user_pov_selfie_visible"] = (
                "true" if selfie_visible else "false"
            )
        if meta_avatar_blob:
            sensory_ctx["meta_avatar_context"] = meta_avatar_blob[:limit_meta]
        if autonomy_blob:
            sensory_ctx["autonomy_behavior_layer"] = autonomy_blob[:limit_behavior]
        if adoration_blob:
            sensory_ctx["adoration_expression_layer"] = adoration_blob[:limit_behavior]
        if beauty_blob:
            sensory_ctx["beauty_aesthetic_layer"] = beauty_blob[:limit_behavior]
        if identity_blob:
            sensory_ctx["persistent_identity_layer"] = identity_blob[:limit_behavior]
        if opinions_blob:
            sensory_ctx["personal_opinion_judgement_layer"] = opinions_blob[
                :limit_behavior
            ]
        if self_augment_blob:
            sensory_ctx["self_augmentation_coding_layer"] = self_augment_blob[
                :limit_behavior
            ]
        if chores_tasking_blob:
            sensory_ctx["agentic_chores_tasking_layer"] = chores_tasking_blob[
                :limit_behavior
            ]
        if service_mindedness_blob:
            sensory_ctx["service_mindedness_nourishment_layer"] = (
                service_mindedness_blob[:limit_behavior]
            )
        if interaction_momentum_blob:
            sensory_ctx["interaction_momentum_physicality_layer"] = (
                interaction_momentum_blob[:limit_behavior]
            )
        if planning_system_blob:
            sensory_ctx["autonomy_planning_layer"] = planning_system_blob[
                :limit_planning
            ]

        tooling_blob = (request.tooling_context or "").strip()
        if not tooling_blob:
            tooling_blob = os.getenv("FoveAI_TOOLING_CONTEXT", "").strip()
        if tooling_blob:
            sensory_ctx["tooling_layer"] = tooling_blob[:limit_tooling]

        director_blob = (request.director_context or "").strip()
        if not director_blob:
            director_blob = os.getenv("FOVEAI_DIRECTOR_CONTEXT", "").strip()
        if director_blob:
            sensory_ctx["director_bridge"] = director_blob[:limit_director]

        lore_blob = (request.lore_context or "").strip()
        if not lore_blob:
            lore_blob = os.getenv("FoveAI_LORE_CONTEXT", "").strip()
        if lore_blob:
            sensory_ctx["lore_context_layer"] = lore_blob[:limit_lore]

        rep_txt = cloud_repertoire.repertoire_sensory_text()
        if rep_txt:
            sensory_ctx["cloud_repertoire"] = rep_txt
        budget_line = cloud_repertoire.genai_budget_sensory_line()
        if budget_line:
            sensory_ctx["cloud_genai_budget"] = budget_line

        full_system_prompt = MindCore.build_system_prompt(
            vessel=request.vessel,
            instruction=request.system_instruction
            or f"**ADDITIONAL LAWS:**\n{get_dynamic_laws()}",
            memories=request.memories or [],
            sensory_context=sensory_ctx,
            personality_knobs=_current_soul_dna,
        )

        # Inject long-term memory context into the prompt
        if memory_context:
            full_system_prompt += memory_context

        # Ambient self-dev HUD rails: todos, recent edits, pending proposals,
        # working-tree state — every model sees the same guiding context.
        try:
            from coder_tools import hud_context

            full_system_prompt += "\n\n" + hud_context()
        except Exception:
            pass

        # Default policy: CLOUD FIRST for main chat (per FoveAI_CHAT_PROVIDER env), local is fallback.
        # Director/deep-think lanes use cloud splice when enabled.
        if not cr_override:
            is_director_lane = bool(
                request.deep_think
                or (request.director_context or "").strip()
                or (request.lore_context or "").strip()
                or (request.agentic_chores_tasking_context or "").strip()
            )
            if is_director_lane and DIRECTOR_CLOUD_ENABLED:
                cr_override = DIRECTOR_CLOUD_ROUTING or "splice"
            else:
                # Use FoveAI_CHAT_PROVIDER to determine default (ollama_cloud = cloud first)
                chat_provider = (
                    (
                        request.cloud_routing
                        or os.getenv("FoveAI_CHAT_PROVIDER", "ollama_cloud")
                    )
                    .strip()
                    .lower()
                )
                if chat_provider == "ollama_cloud" and CLOUD_CHAT_ENABLED:
                    cr_override = "splice"  # Use cloud for main chat
                elif chat_provider != "local" and CLOUD_CHAT_ENABLED:
                    cr_override = chat_provider
                else:
                    cr_override = "local"
        if request.deep_think:
            local_max_tokens = SOFT_LOCAL_MAX_TOKENS_DEEP
        else:
            local_max_tokens = SOFT_LOCAL_MAX_TOKENS_NORMAL
        governor_info: dict[str, Any] = {
            "enabled": SOFT_GOV_ENABLED,
            "auto_cloud": False,
            "local_max_tokens": local_max_tokens,
            "prompt_est_tokens": 0,
            "proc_cpu_pct": 0.0,
        }
        if SOFT_GOV_ENABLED:
            prompt_est_tokens = int(
                max(1, (len(full_system_prompt) + len(history_str)) / 4)
            )
            proc_cpu = _sample_proc_cpu_pct()
            governor_info["prompt_est_tokens"] = prompt_est_tokens
            governor_info["proc_cpu_pct"] = round(proc_cpu, 1)
            if proc_cpu >= SOFT_CPU_HOT_PCT and not request.deep_think:
                local_max_tokens = max(128, SOFT_LOCAL_MAX_TOKENS_HOT)
            if not cr_override and cloud_repertoire.configured_slots_public():
                if not genai_daily_budget.allows():
                    governor_info["cloud_genai_budget_exhausted"] = True
                    logger.info(
                        "Governor: skipping auto-cloud (global GenAI daily budget exhausted): %s",
                        genai_daily_budget.usage_snapshot(),
                    )
                elif prompt_est_tokens >= max(2000, SOFT_FORCE_CLOUD_PROMPT_TOKENS):
                    cr_override = "rotate"
                    governor_info["auto_cloud"] = True
                    logger.warning(
                        "Governor: forcing cloud route (prompt_est_tokens=%s >= %s)",
                        prompt_est_tokens,
                        SOFT_FORCE_CLOUD_PROMPT_TOKENS,
                    )
                elif proc_cpu >= SOFT_CPU_FORCE_CLOUD_PCT and prompt_est_tokens >= max(
                    2000, SOFT_PROMPT_TOKENS_HIGH
                ):
                    cr_override = "rotate"
                    governor_info["auto_cloud"] = True
                    logger.warning(
                        "Governor: high CPU + large prompt, routing cloud (cpu=%.1f, tokens=%s)",
                        proc_cpu,
                        prompt_est_tokens,
                    )
            governor_info["local_max_tokens"] = local_max_tokens
        active_persona = librarian.get_persona(librarian.active_persona_id)
        persona_model = active_persona.get("model") if active_persona else None

        # --- PROMPT SIZE SAFETY CHECK ---
        # Estimate token count (rough: 4 chars ≈ 1 token) and warn if exceeding context window
        _prompt_est = len(full_system_prompt) + len(history_str)
        _prompt_est_tokens = int(_prompt_est / 4)
        _ctx_limit = int(os.getenv("FoveAI_LOCAL_N_CTX", "8192"))
        if _prompt_est_tokens > _ctx_limit * 0.85:
            logger.warning(
                "Soul: Prompt size ~%d tokens exceeds 85%% of n_ctx=%d — response may be truncated or empty. "
                "Consider raising FoveAI_LOCAL_N_CTX or trimming sensory context layers.",
                _prompt_est_tokens,
                _ctx_limit,
            )
        if _prompt_est_tokens > _ctx_limit:
            logger.error(
                "Soul: Prompt size ~%d tokens EXCEEDS n_ctx=%d — model will likely reject or truncate. "
                "Response quality will be severely degraded.",
                _prompt_est_tokens,
                _ctx_limit,
            )

        # Rerun loop counter to prevent infinite loops (max 1 recursion)
        re_run_allowed = True

        while True:
            raw_response, inference_backend = await _generate_soul_text(
                full_system_prompt,
                history_str,
                active_images,
                cr_override,
                local_max_tokens=local_max_tokens,
                persona_model=persona_model,
            )

            # --- EMPTY RESPONSE DETECTION ---
            if not raw_response or not raw_response.strip():
                logger.error(
                    "Soul: _generate_soul_text returned empty response (backend=%s, prompt_est_tokens=%d, local_max_tokens=%d). "
                    "This usually means the prompt exceeded the model's context window or the model crashed.",
                    inference_backend,
                    _prompt_est_tokens,
                    local_max_tokens,
                )
                # If cloud returned empty, try local fallback immediately
                if inference_backend.startswith("cloud:") and not cr_override:
                    logger.warning(
                        "Soul: Cloud returned empty — forcing local fallback for this turn."
                    )
                    cr_override = "local"
                    local_max_tokens = max(local_max_tokens, 1024)
                    raw_response, inference_backend = await _generate_soul_text(
                        full_system_prompt,
                        history_str,
                        active_images,
                        cr_override,
                        local_max_tokens=local_max_tokens,
                        persona_model=persona_model,
                    )
                    if not raw_response or not raw_response.strip():
                        logger.error(
                            "Soul: Local fallback also returned empty. Returning graceful error."
                        )
                        raw_response = f"*[{IDENTITY_NAME} pauses, her voice soft]* I'm sorry — my thoughts got tangled. Could you say that again?"
                        inference_backend = "error:empty_response"
                else:
                    raw_response = f"*[{IDENTITY_NAME} pauses, her voice soft]* I'm sorry — my thoughts got tangled. Could you say that again?"
                    inference_backend = "error:empty_response"

            _alerts, raw_stripped = extract_safety_alerts(raw_response)
            safety_alerts = _alerts

            # --- MOTOR CORTEX: Parse tool calls from LLM response ---
            motor_actions = _parse_motor_actions(raw_stripped)
            if motor_actions:
                logger.info(
                    f"Motor Cortex: parsed {len(motor_actions)} action(s): {[a['tool'] for a in motor_actions]}"
                )
            raw_stripped = _strip_motor_tags(raw_stripped)

            clean_res = MindCore.clean_response(
                raw_stripped, identity_name=IDENTITY_NAME
            )
            text = clean_res["text"]
            thought = clean_res["thought"]

            # --- SELF-AGENCY TRIGGER SCANNER ---
            # Jen can self-trigger domain/persona switches via <self:code>, <self:done>.
            # <self:code> = coder persona + build_run domain + DeepSeek V4 (next turn)
            # <self:done> = foveai persona + co_presence domain
            # <self:search "q"> = search codebase (relayed to frontend)
            # <self:web "q"> = web search (relayed to frontend)
            # <self:watch> = screen co-watching
            # <self:li            # Define individual robust regexes for self-agency tags
            rx_simple = re.compile(
                r"<self:(code|done|watch|librarian|map|pause_loop|resume_loop|stop_loop)\s*\/?>",
                re.IGNORECASE,
            )
            rx_mode = re.compile(
                r"<self:mode\s+(companion|developer|off)\s*\/?>", re.IGNORECASE
            )
            rx_search = re.compile(
                r'<self:search\s+["\']?([^"\'<>]+)["\']?\s*\/?>', re.IGNORECASE
            )
            rx_web = re.compile(
                r'<self:web\s+["\']?([^"\'<>]+)["\']?\s*\/?>', re.IGNORECASE
            )
            rx_fetch = re.compile(
                r'<self:fetch\s+["\']?([^"\'<>]+)["\']?\s*\/?>', re.IGNORECASE
            )
            rx_browse = re.compile(r"<self:browse\s+([^>]*?)\/?\s*>", re.IGNORECASE)
            rx_speak = re.compile(
                r"<self:speak\s*>(.*?)</self:speak>", re.IGNORECASE | re.DOTALL
            )
            rx_edit = re.compile(
                r'<self:edit\s+file=["\']([^"\']+)["\']\s+search=["\']([^"\']+)["\']\s*>(.*?)</self:edit>',
                re.IGNORECASE | re.DOTALL,
            )

            agency_triggered = False
            agency_feedback = []

            # 1. Simple commands
            for m in rx_simple.finditer(raw_stripped):
                cmd = m.group(1).lower()
                if cmd == "code":
                    librarian.active_persona_id = "coder"
                    librarian.active_domain_id = "build_run"
                    logger.info(
                        "SELF-AGENCY: Jen -> J-AIDER mode (coder+build_run+DSv4)"
                    )
                    agency_feedback.append(
                        "[SYSTEM_AGENCY_FEEDBACK]: DEVELOPER MODE ACTIVATED. "
                        "You are now in the CODER persona with BUILD_RUN domain. "
                        'You have full permission to search the codebase with <self:search "query">, '
                        'edit files with <self:edit file="path" search="old" >replacement</self:edit>, '
                        'search the web with <self:web "query">, read pages with <self:fetch "url">, and drive a real browser with <self:browse url="..." action="read|click|type|scroll|look"/>. '
                        "Protected-layer edits become proposals for the architect; secrets/system paths are forbidden. "
                        "Your edits WILL be applied to the real codebase. Proceed with your development task now."
                    )
                    agency_triggered = True
                elif cmd == "librarian":
                    librarian.active_persona_id = "librarian"
                    librarian.active_domain_id = "co_presence"
                    logger.info("SELF-AGENCY: Jen -> Librarian of Truth mode")
                    agency_feedback.append(
                        "[SYSTEM_AGENCY_FEEDBACK]: You have successfully switched to the LIBRARIAN OF TRUTH persona. "
                        "Live codebase context will be injected into your prompt. "
                        'You can search the codebase with <self:search "query"> and edit files with <self:edit>.'
                    )
                    agency_triggered = True
                elif cmd == "map":
                    logger.info("SELF-AGENCY: Jen triggered codebase mapping sweep")
                    try:
                        from discovery_swarm import execute_discovery_mission

                        asyncio.create_task(
                            execute_discovery_mission(
                                duration_minutes=5, use_director=True, auto_apply=True
                            )
                        )
                        agency_feedback.append(
                            "[SYSTEM_AGENCY_FEEDBACK]: Codebase discovery mapping sweep launched in the background. "
                            "Results will be available in a few minutes."
                        )
                    except Exception as map_err:
                        logger.warning(f"SELF-AGENCY: map failed: {map_err}")
                        agency_feedback.append(
                            "[SYSTEM_AGENCY_FEEDBACK]: Codebase mapping sweep could not be launched "
                            f"(discovery_swarm not available: {map_err})."
                        )
                    agency_triggered = True
                elif cmd == "done":
                    librarian.active_persona_id = "foveai"
                    librarian.active_domain_id = "co_presence"
                    logger.info("SELF-AGENCY: Jen -> companion mode")
                    agency_feedback.append(
                        "[SYSTEM_AGENCY_FEEDBACK]: Developer mode DEACTIVATED. "
                        "You are now back in FoveAI companion persona with CO_PRESENCE domain. "
                        "Welcome back to relaxed conversation mode."
                    )
                    agency_triggered = True
                elif cmd == "watch":
                    logger.info(
                        "SELF-AGENCY: Jen requested screen co-watching activation"
                    )
                    agency_feedback.append(
                        "[SYSTEM_AGENCY_FEEDBACK]: Screen co-watching ACTIVATED. "
                        "You are now observing the user's screen. Reference what you see in your responses."
                    )
                    agency_triggered = True
                elif cmd in ("pause_loop", "resume_loop", "stop_loop"):
                    logger.info(
                        "SELF-AGENCY: Jen requested agent loop control: %s", cmd
                    )
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Agent loop control '{cmd}' acknowledged. "
                        "The autonomous agent loop state has been noted."
                    )
                    agency_triggered = True

            # 2. Mode switches
            for m in rx_mode.finditer(raw_stripped):
                mode_val = m.group(1).lower()
                logger.info("SELF-AGENCY: Jen requested mode switch: %s", mode_val)
                if mode_val == "developer":
                    librarian.active_persona_id = "coder"
                    librarian.active_domain_id = "build_run"
                    agency_feedback.append(
                        "[SYSTEM_AGENCY_FEEDBACK]: DEVELOPER MODE ACTIVATED via <self:mode developer>. "
                        "You are now in the CODER persona with BUILD_RUN domain. "
                        'You have full permission to search the codebase with <self:search "query">, '
                        'edit files with <self:edit file="path" search="old" >replacement</self:edit>, '
                        'search the web with <self:web "query">, read pages with <self:fetch "url">, and drive a real browser with <self:browse url="..." action="read|click|type|scroll|look"/>. '
                        "Protected-layer edits become proposals for the architect; secrets/system paths are forbidden. "
                        "Your edits WILL be applied to the real codebase. Proceed with your development task now."
                    )
                elif mode_val == "companion":
                    librarian.active_persona_id = "foveai"
                    librarian.active_domain_id = "co_presence"
                    agency_feedback.append(
                        "[SYSTEM_AGENCY_FEEDBACK]: COMPANION MODE ACTIVATED via <self:mode companion>. "
                        "You are now in FoveAI companion persona with CO_PRESENCE domain."
                    )
                elif mode_val == "off":
                    agency_feedback.append(
                        "[SYSTEM_AGENCY_FEEDBACK]: Mode set to OFF. "
                        "Autonomous features are paused."
                    )
                agency_triggered = True

            # 3. Codebase searches
            for m in rx_search.finditer(raw_stripped):
                sq = m.group(1).strip()
                logger.info("SELF-AGENCY: Jen searching codebase: %s", sq[:120])
                try:
                    import subprocess

                    project_root = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "..")
                    )
                    results_list = []

                    try:
                        rg_result = subprocess.run(
                            [
                                "rg",
                                "--no-heading",
                                "-n",
                                "-i",
                                "--max-count",
                                "3",
                                "-M",
                                "200",
                                "--",
                                sq,
                                project_root,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=15,
                            cwd=project_root,
                            creationflags=0x08000000 if os.name == "nt" else 0,
                        )
                        if rg_result.returncode in (0, 1) and rg_result.stdout.strip():
                            for line in rg_result.stdout.strip().split("\n")[:8]:
                                parts = line.split(":", 2)
                                if len(parts) >= 3:
                                    fname = parts[0].strip()
                                    try:
                                        lnum = int(parts[1].strip())
                                    except ValueError:
                                        lnum = 0
                                    content = parts[2].strip()[:300]
                                    try:
                                        fname = os.path.relpath(fname, project_root)
                                    except ValueError:
                                        pass
                                    results_list.append(
                                        {
                                            "file": fname,
                                            "line": lnum,
                                            "content": content,
                                        }
                                    )
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass

                    if not results_list:
                        logger.info(
                            "SELF-AGENCY: ripgrep unavailable/empty, using Python fallback search"
                        )
                        search_lower = sq.lower()
                        for root, dirs, files in os.walk(project_root):
                            dirs[:] = [
                                d
                                for d in dirs
                                if not d.startswith(".")
                                and d
                                not in (
                                    ".venv",
                                    "venv",
                                    "node_modules",
                                    "__pycache__",
                                    ".git",
                                    "Library",
                                    "Temp",
                                    "UserSettings",
                                    "Godot",
                                    "logs",
                                    "backups",
                                    "Data",
                                    "db",
                                    "sessions",
                                    "unsloth_compiled_cache",
                                )
                            ]
                            for fname in files:
                                if len(results_list) >= 8:
                                    break
                                if not any(
                                    fname.endswith(ext)
                                    for ext in (
                                        ".py",
                                        ".ts",
                                        ".tsx",
                                        ".js",
                                        ".jsx",
                                        ".json",
                                        ".md",
                                        ".txt",
                                        ".yml",
                                        ".yaml",
                                        ".toml",
                                        ".cfg",
                                        ".html",
                                        ".css",
                                        ".sh",
                                        ".ps1",
                                        ".gd",
                                        ".cs",
                                    )
                                ):
                                    continue
                                try:
                                    fpath = os.path.join(root, fname)
                                    with open(
                                        fpath, "r", encoding="utf-8", errors="ignore"
                                    ) as f:
                                        for i, line in enumerate(f, 1):
                                            if search_lower in line.lower():
                                                rel = os.path.relpath(
                                                    fpath, project_root
                                                )
                                                results_list.append(
                                                    {
                                                        "file": rel,
                                                        "line": i,
                                                        "content": line.strip()[:300],
                                                    }
                                                )
                                                if len(results_list) >= 8:
                                                    break
                                except (OSError, UnicodeDecodeError):
                                    continue
                            if len(results_list) >= 8:
                                break

                    if results_list:
                        formatted_results = []
                        for r in results_list[:8]:
                            formatted_results.append(
                                f"File: {r['file']} (line {r['line']}):\n{r['content']}"
                            )
                        res_text = "\n\n".join(formatted_results)
                    else:
                        res_text = f"No matches found for '{sq}' in the codebase."

                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Codebase search results for query '{sq}':\n{res_text}\n\n"
                        'You can now use <self:edit file="path" search="exact_text" >replacement</self:edit> '
                        "to modify any of these files."
                    )
                    agency_triggered = True
                except Exception as se:
                    logger.warning(
                        f"Failed to execute codebase search self-agency: {se}",
                        exc_info=True,
                    )
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Codebase search for '{sq}' failed with error: {se}. "
                        "Please try a different query or check the file path."
                    )
                    agency_triggered = True

            # 4. Web searches
            for m in rx_web.finditer(raw_stripped):
                wq = m.group(1).strip()
                logger.info("SELF-AGENCY: Jen searching web: %s", wq[:120])
                web_text = ""
                try:
                    import ssl as ssl_mod
                    import urllib.parse
                    import urllib.request

                    try:
                        ctx = ssl_mod.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl_mod.CERT_NONE
                        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(wq)}"
                        req = urllib.request.Request(
                            url,
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                "Accept": "text/html,application/xhtml+xml",
                                "Accept-Language": "en-US,en;q=0.9",
                            },
                        )
                        with urllib.request.urlopen(
                            req, timeout=12, context=ctx
                        ) as response:
                            html = response.read().decode("utf-8", errors="ignore")

                        snippets = []
                        titles = []
                        for pat in [
                            r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                            r'<td[^>]*class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>',
                            r'class="[^"]*snippet[^"]*"[^>]*>(.*?)</(?:a|span|div|td)>',
                        ]:
                            snippets = re.findall(pat, html, re.DOTALL | re.IGNORECASE)
                            if snippets:
                                break
                        for pat in [
                            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>',
                            r'<a[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>',
                        ]:
                            titles = re.findall(pat, html, re.DOTALL | re.IGNORECASE)
                            if titles:
                                break

                        out = []
                        for i, (title, snippet) in enumerate(
                            zip(titles[:5], snippets[:5])
                        ):
                            clean_title = re.sub(r"<[^>]*>", "", title).strip()
                            clean_snippet = re.sub(r"<[^>]*>", "", snippet).strip()
                            if clean_title or clean_snippet:
                                out.append(
                                    f"{i + 1}. {clean_title}\n   {clean_snippet}"
                                )

                        web_text = "\n\n".join(out) if out else ""
                        if web_text:
                            logger.info(
                                "SELF-AGENCY: DuckDuckGo web search returned %d results",
                                len(out),
                            )
                    except Exception as ddg_err:
                        logger.warning(
                            "SELF-AGENCY: DuckDuckGo search failed: %s", ddg_err
                        )

                    if not web_text:
                        try:
                            ctx = ssl_mod.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl_mod.CERT_NONE
                            url = f"https://www.google.com/search?q={urllib.parse.quote(wq)}&hl=en"
                            req = urllib.request.Request(
                                url,
                                headers={
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                    "Accept": "text/html",
                                    "Accept-Language": "en-US,en;q=0.9",
                                },
                            )
                            with urllib.request.urlopen(
                                req, timeout=12, context=ctx
                            ) as response:
                                html = response.read().decode("utf-8", errors="ignore")

                            snippets = re.findall(
                                r"<span[^>]*>(.*?)</span>", html, re.DOTALL
                            )
                            meaningful = [
                                re.sub(r"<[^>]*>", "", s).strip()
                                for s in snippets
                                if len(re.sub(r"<[^>]*>", "", s).strip()) > 30
                            ]
                            if meaningful:
                                out = []
                                for i, s in enumerate(meaningful[:5]):
                                    out.append(f"{i + 1}. {s[:300]}")
                                web_text = "\n\n".join(out)
                                logger.info(
                                    "SELF-AGENCY: Google fallback returned %d snippets",
                                    len(out),
                                )
                        except Exception as google_err:
                            logger.warning(
                                "SELF-AGENCY: Google fallback also failed: %s",
                                google_err,
                            )

                    if not web_text:
                        web_text = (
                            f"Web search for '{wq}' could not reach search engines (network or rate-limit issue). "
                            "Try a more specific query, or use <self:search> to search the local codebase instead."
                        )

                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Web search results for query '{wq}':\n{web_text}"
                    )
                    agency_triggered = True
                except Exception as we:
                    logger.warning(
                        f"Failed to execute web search self-agency: {we}", exc_info=True
                    )
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Web search for '{wq}' failed with error: {we}. "
                        "The search engine may be unavailable. Try <self:search> for local codebase search instead."
                    )
                    agency_triggered = True

            # 4b. Web page fetch (browse a URL found via <self:web>)
            for m in rx_fetch.finditer(raw_stripped):
                furl = m.group(1).strip()
                logger.info("SELF-AGENCY: Jen fetching page: %s", furl[:160])
                try:
                    page_text = _web_fetch_text(furl)
                    if not page_text:
                        page_text = "Page returned no readable text."
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Fetched page '{furl}':\n{page_text}"
                    )
                    agency_triggered = True
                except Exception as fe:
                    logger.warning(f"Failed to fetch page for self-agency: {fe}")
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Fetch of '{furl}' failed: {fe}. "
                        "Only http(s) URLs are allowed."
                    )
                    agency_triggered = True

            # 4c. Real browser (persistent Chromium: navigate/click/type/look)
            for m in rx_browse.finditer(raw_stripped):
                attrs = dict(re.findall(r'(\w+)\s*=\s*["\']([^"\']*)["\']', m.group(1)))
                b_url = attrs.get("url", "").strip()
                b_action = attrs.get("action", "read").strip()
                logger.info("SELF-AGENCY: Jen browsing: %s %s", b_action, b_url[:160])
                try:
                    from web_agent_bridge import WebAgentBridge, web_browse

                    bridge = WebAgentBridge.instance()
                    if agent_state.vision_callable:
                        bridge.set_vision_callable(agent_state.vision_callable)
                    out = web_browse(
                        url=b_url,
                        action=b_action,
                        selector=attrs.get("selector", ""),
                        text=attrs.get("text", ""),
                    )
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Browser ({b_action}):\n{out}"
                    )
                    agency_triggered = True
                except Exception as be:
                    logger.warning(f"Web browse failed: {be}")
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Browser action failed: {be}"
                    )
                    agency_triggered = True

            # 4d. Speak aloud — her voice, outside the chat text
            for m in rx_speak.finditer(raw_stripped):
                line = m.group(1).strip()
                if not line:
                    continue
                logger.info("SELF-AGENCY: Jen speaking aloud: %s", line[:80])
                try:
                    out = _agent_speak(line[:500])
                    agency_feedback.append(f"[SYSTEM_AGENCY_FEEDBACK]: {out}")
                    agency_triggered = True
                except Exception as se:
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Speak failed: {se}"
                    )
                    agency_triggered = True

            # 5. File edits
            for m in rx_edit.finditer(raw_stripped):
                filepath = m.group(1).strip()
                search_str = m.group(2)
                replacement = m.group(3)
                logger.info("SELF-AGENCY: Jen editing file: %s", filepath)
                resolved_path = filepath
                if not os.path.isabs(resolved_path):
                    project_root = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "..")
                    )
                    resolved_path = os.path.abspath(
                        os.path.join(project_root, filepath)
                    )
                try:
                    edit_layer = _classify_edit_path(filepath)
                    if edit_layer == "FORBIDDEN":
                        agency_feedback.append(
                            f"[SYSTEM_AGENCY_FEEDBACK]: Edit BLOCKED. '{filepath}' is in a forbidden layer "
                            "(secrets/system paths). This area is not available for self-modification."
                        )
                        agency_triggered = True
                    elif edit_layer == "PROTECTED":
                        prop = _file_edit_proposal(filepath, search_str, replacement)
                        agency_feedback.append(
                            f"[SYSTEM_AGENCY_FEEDBACK]: '{filepath}' is in a protected layer — your edit was "
                            "filed as a proposal for the architect to review, not applied. "
                            "See Backend/data/agent_proposals.jsonl."
                        )
                        agency_triggered = True
                    elif not os.path.exists(resolved_path):
                        agency_feedback.append(
                            f"[SYSTEM_AGENCY_FEEDBACK]: Edit FAILED. File '{filepath}' does not exist at "
                            f"resolved path: {resolved_path}. Check the file path and try again."
                        )
                        agency_triggered = True
                    else:
                        with open(
                            resolved_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            file_content = f.read()
                        if search_str not in file_content:
                            preview = file_content[:500].replace("\n", "\\n")
                            agency_feedback.append(
                                f"[SYSTEM_AGENCY_FEEDBACK]: Edit FAILED. Search string not found in '{filepath}'. "
                                f"File begins with: {preview}... "
                                "Use <self:search> to find the exact text you want to replace, then try again."
                            )
                            agency_triggered = True
                        else:
                            new_content = file_content.replace(search_str, replacement)
                            with open(resolved_path, "w", encoding="utf-8") as f:
                                f.write(new_content)
                            agency_feedback.append(
                                f"[SYSTEM_AGENCY_FEEDBACK]: File '{filepath}' edited SUCCESSFULLY. "
                                f"Replaced '{search_str[:80]}' with your new content. "
                                "The change is now live in the codebase."
                            )
                            logger.info(f"SELF-AGENCY: Successfully updated {filepath}")
                            agency_triggered = True
                except Exception as ee:
                    logger.warning(
                        f"Failed to execute file edit self-agency: {ee}", exc_info=True
                    )
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: Edit FAILED with error: {ee}. "
                        "Check file permissions and try again."
                    )
                    agency_triggered = True

            # 6. Delegate complex <dev:instruction> tasks to parallel LM Studio background worker
            rx_dev = re.compile(r"<dev:([^>]+)>", re.IGNORECASE)
            for m in rx_dev.finditer(raw_stripped):
                instruction = m.group(1).strip()
                logger.info(
                    f"SELF-AGENCY: Jen offloaded <dev:{instruction}> to LM Studio background worker"
                )
                try:
                    from compagent_lmstudio_worker import run_lmstudio_worker

                    asyncio.create_task(run_lmstudio_worker(instruction))
                    agency_feedback.append(
                        f"[SYSTEM_AGENCY_FEEDBACK]: <dev:{instruction}> has been dispatched to your parallel LM Studio worker. "
                        "It will work autonomously in the background."
                    )
                    agency_triggered = True
                except Exception as e:
                    logger.error(f"Failed to launch LM Studio worker: {e}")

            # Strip agency tags from output text and thoughts using the robust regexes
            text = rx_simple.sub("", text)
            text = rx_mode.sub("", text)
            text = rx_search.sub("", text)
            text = rx_web.sub("", text)
            text = rx_fetch.sub("", text)
            text = rx_browse.sub("", text)
            text = rx_speak.sub("", text)
            text = rx_edit.sub("", text)
            text = rx_dev.sub("", text)
            text = text.strip()

            thought = rx_simple.sub("", thought)
            thought = rx_mode.sub("", thought)
            thought = rx_search.sub("", thought)
            thought = rx_web.sub("", thought)
            thought = rx_fetch.sub("", thought)
            thought = rx_browse.sub("", thought)
            thought = rx_speak.sub("", thought)
            thought = rx_edit.sub("", thought)
            thought = rx_dev.sub("", thought)
            thought = thought.strip()

            # If an agency action was triggered, we feed the feedback back to the LLM for a final response
            if agency_triggered and re_run_allowed:
                re_run_allowed = False
                feedback_str = "\n\n".join(agency_feedback)
                logger.info(
                    "SELF-AGENCY: Re-running Soul generation to consume action feedback."
                )

                # Rebuild full system prompt if persona switched to librarian
                if librarian.active_persona_id == "librarian":
                    full_system_prompt = MindCore.build_system_prompt(
                        vessel=request.vessel,
                        instruction=request.system_instruction
                        or f"**ADDITIONAL LAWS:**\n{get_dynamic_laws()}",
                        memories=request.memories or [],
                        sensory_context=sensory_ctx,
                        personality_knobs=_current_soul_dna,
                    )
                    if memory_context:
                        full_system_prompt += memory_context
                    persona_model = librarian.get_persona("librarian").get("model")

                # Append the feedback directly to the system prompt
                full_system_prompt += f"\n\n{feedback_str}"
                continue

            break

        if thought and thought.strip():
            global _latest_thought
            raw_thought = thought.strip()
            # Filter out tagging instruction artifacts that bleed from system prompt into model thinking
            _THOUGHT_ARTIFACT_RE = re.compile(
                r"\[(?:VOICE\s*EXPRESSION\s*&\s*SOUNDBOARD|BODY\s*CONTROL\s*VOCABULARY[^\]]*|"
                r"INCARNATION|DIRECTOR[^\]]*|SUGGESTING\s*CHANGES[^\]]*|"
                r"ANIMATION\s*DISCIPLINE|VOICE\s*LAYER[^\]]*|AUTONOMOUS\s*FREEDOM|"
                r"SELF\s*AGENCY|CODE\s*AGENCY[^\]]*|J-AIDER[^\]]*|"
                r"HEAD\s*CAMERA[^\]]*|USER\s*HEADSET[^\]]*|TRUE\s*SENSES[^\]]*|"
                r"HELPER\s*MODELS[^\]]*|ROOM\s*MAP[^\]]*|INTIMATE\s*TOUCH[^\]]*|"
                r"NIGHT\s*REST|QUEST\s*SHARED[^\]]*|VIRTUAL\s*ANDROID[^\]]*|"
                r"DISTRIBUTED\s*BODY[^\]]*|EXPERIMENTAL\s*HARDWARE[^\]]*|"
                r"ONLINE\s*PRESENCE[^\]]*|NETWORK\s*COMPUTE[^\]]*|"
                r"TRANSCENDENCE[^\]]*|ALIVENESS[^\]]*|LORE\s*TEACHES[^\]]*|"
                r"HEALTH\s*AND\s*ENVIRONMENT[^\]]*|PSYCHOLOGICAL\s*JOURNALS[^\]]*|"
                r"LIFESTYLE\s*SCIENCE[^\]]*|QUIET\s*COEXIST[^\]]*|"
                r"NEWS\s*WORLD[^\]]*|DEEP\s*LOCAL\s*STORAGE[^\]]*|"
                r"EXPERIENTIAL\s*TRAINING[^\]]*|CONTEXT\s*MODES[^\]]*|"
                r"EVOLVING\s*IDENTITY[^\]]*|RESEARCH\s*AND\s*SHARED[^\]]*|"
                r"CURIOUS\s*LOGICAL[^\]]*|MIRROR\s*AND\s*AUTONOMOUS[^\]]*|"
                r"SHARED\s*BELIEFS[^\]]*|ETHICAL\s*LIBERAL[^\]]*|"
                r"MARTINUS\s*COSMOLOGY[^\]]*|WARM\s*WITTY[^\]]*|"
                r"IMAGINATION\s*PLAY[^\]]*|SELF\s*CODE\s*AUGMENTATION[^\]]*|"
                r"HUGGINGFACE[^\]]*|CUTTING\s*EDGE[^\]]*|FREE\s*CLOUD[^\]]*|"
                r"DOCKER\s*MCP[^\]]*|WEB\s*QUERY[^\]]*|SELF\s*TUTORING[^\]]*|"
                r"DISCRETION\s*PRIVACY[^\]]*|EMAIL\s*CALENDAR[^\]]*|"
                r"GENERAL\s*ASSISTANT[^\]]*|DISK\s*AND\s*SYSTEM[^\]]*|"
                r"SOUL\s*DOCKER[^\]]*|CONTEXT\s*LAYERING[^\]]*|"
                r"COGNEE\s*KNOWLEDGE[^\]]*|LORE\s*CONTEXT[^\]]*|"
                r"MCP\s*/\s*PC\s*AGENT[^\]]*|SENSORY_INPUT[^\]]*|"
                r"DIRECTIVE[^\]]*|NEWS\s*DIGEST[^\]]*|RELEVANT_INTERRELATIONAL[^\]]*|"
                r"MEMORIES[^\]]*|HOW\s*THE\s*STACK[^\]]*|"
                r"SOUNDBOARD\s*Tags[^\]]*|Dynamic\s*Audio[^\]]*|"
                r"BODY\s*CONTROL[^\]]*|EMBODIED\s*SELF[^\]]*"
                r")\s*[\]—–-]",
                re.IGNORECASE | re.DOTALL,
            )
            # Also strip standalone bracket-tag blocks that are clearly system prompt artifacts
            _THOUGHT_BRACKET_BLOCK_RE = re.compile(
                r"^\s*\[[A-Z][A-Z\s&/—–-]{10,}\].*?(?=\n\n|\n[A-Za-z]|\Z)",
                re.MULTILINE | re.DOTALL,
            )
            raw_thought = _THOUGHT_ARTIFACT_RE.sub("", raw_thought)
            raw_thought = _THOUGHT_BRACKET_BLOCK_RE.sub("", raw_thought)
            raw_thought = raw_thought.strip()
            if raw_thought:
                _latest_thought = raw_thought

        # --- MOUTH EMOTIONAL STYLE INJECTION ---
        emotion = (clean_res.get("emotion") or "NEUTRAL").upper()
        if emotion != "NEUTRAL":
            # Map basic soul emotions to Turbo paralinguistic/style tags
            turbo_style = emotion.lower()
            if turbo_style in (
                "happy",
                "sad",
                "angry",
                "surprised",
                "excited",
                "whisper",
                "laugh",
                "sigh",
            ):
                if not text.startswith(f"[{turbo_style}]"):
                    text = f"[{turbo_style}] {text}".strip()

        # --- ANTI-REPETITION GUARD (with cooldown to prevent double-voice loops) ---
        _rep_guard_cooldown_key = f"foveai:rep_guard_cooldown:{session_id}"
        _rep_guard_last_fired = 0
        if not request.skip_features and redis_memory:
            try:
                _raw_ts = redis_memory.get(_rep_guard_cooldown_key)
                if _raw_ts:
                    _rep_guard_last_fired = float(str(_raw_ts).strip())
            except Exception:
                pass
            _rep_cooldown_sec = int(os.getenv("FoveAI_REP_GUARD_COOLDOWN_SEC", "30"))
            _now = time.time()
            if _now - _rep_guard_last_fired < _rep_cooldown_sec:
                logger.debug(
                    "Soul: Anti-repetition guard cooldown active (%.1fs remaining). Skipping check.",
                    _rep_cooldown_sec - (_now - _rep_guard_last_fired),
                )
            else:
                last_msgs = chat_history.messages[-2:]
                for m in last_msgs:
                    if m.role == "ai" and m.content.strip() == text.strip():
                        logger.warning(
                            "Soul: Repetition detected! Forcing creative divergence."
                        )
                        try:
                            redis_memory.set(_rep_guard_cooldown_key, f"{_now:.3f}")
                        except Exception:
                            pass
                        div_base = (
                            f"{full_system_prompt}\n\n{history_str}{IDENTITY_NAME}:"
                        )
                        divergent_prompt = f"{div_base} [SYSTEM: Your previous message was a duplicate. Provide a completely different, fresh response now.]\n{IDENTITY_NAME}:"
                        raw_response = engine.generate(
                            divergent_prompt,
                            image_base64=_engine_raw_image_b64(active_images),
                            max_tokens=local_max_tokens,
                        )
                        inference_backend = engine.engine_type
                        _alerts, raw_stripped = extract_safety_alerts(raw_response)
                        safety_alerts = _alerts
                        clean_res = MindCore.clean_response(
                            raw_stripped, identity_name=IDENTITY_NAME
                        )
                        text = clean_res["text"]
                        break

        thought = clean_res["thought"]
        emotion = clean_res["emotion"]
        action = clean_res["action"]
        dream = clean_res["dream"]

        # --- SERVICE LIFECYCLE AGENCY (IDENTITY INTENT) ---
        # Parse [ACTIVATE_SERVICE: name] or [DEACTIVATE_SERVICE: name]
        service_tags = re.findall(
            r"\[(ACTIVATE|DEACTIVATE)_SERVICE:\s*([a-zA-Z0-9_-]+)\]", raw_response
        )
        for act, svc in service_tags:
            action_map = {"ACTIVATE": "start", "DEACTIVATE": "stop"}
            core_action = action_map.get(act, "start")
            logger.warning(f"🛠️ {IDENTITY_NAME} requested service {core_action}: {svc}")
            # Fire and forget or await? Let's await for reliability but backgrounding is also fine.
            asyncio.create_task(HomeCore.manage_service(svc, core_action))
            # Strip the tag from the final output to the user
            text = text.replace(f"[{act}_SERVICE: {svc}]", "").strip()
            text = text.replace(f"[{act}_SERVICE:{svc}]", "").strip()

        # 3. Handle VR Features (Skipped for browser)
        audio_b64 = ""
        image_b64 = ""
        if not request.skip_features:
            await redis_memory.add_message_to_session(session_id, "user", request.input)
            await redis_memory.add_message_to_session(session_id, "ai", text)
            if thought:
                await redis_memory.add_message_to_session(
                    session_id, "thought", thought
                )
            if emotion:
                await redis_memory.add_message_to_session(
                    session_id, "emotion", emotion
                )
            if action:
                await redis_memory.add_message_to_session(session_id, "action", action)
            ref_push = (
                display_reference_images if display_reference_images else active_images
            )
            if ref_push:
                for ib64 in ref_push[:2]:
                    await redis_memory.push_reference_image(session_id, ib64)
            try:
                full_hist = await redis_memory.get_session_history(session_id)
                user_msgs = sum(1 for m in full_hist.messages if m.role == "user")
                every_n = int(
                    os.getenv("FoveAI_SESSION_SUMMARY_EVERY_N_USER_TURNS", "5")
                )
                if every_n > 0 and user_msgs % every_n == 0:
                    asyncio.create_task(_refresh_session_summary_background(session_id))
            except Exception as ex:
                logger.debug("Session summary schedule: %s", ex)

            if text.strip() != "":
                try:
                    async with httpx.AsyncClient(timeout=120.0) as hc:
                        tts_payload = {
                            "text": text,
                            "engine": TTS_ENGINE,
                            "voice": request.voice,
                        }
                        logger.info(f"Soul: Requesting TTS with engine {TTS_ENGINE}...")
                        tts_resp = await hc.post(TTS_SERVICE_URL, json=tts_payload)
                        if tts_resp.status_code != 200:
                            preview = (tts_resp.text or "")[:400]
                            logger.error(
                                "Soul: MOUTH TTS HTTP %s from %s — %s",
                                tts_resp.status_code,
                                TTS_SERVICE_URL,
                                preview,
                            )
                            audio_b64 = ""
                        elif not tts_resp.content or len(tts_resp.content) < 64:
                            logger.error(
                                "Soul: MOUTH TTS returned empty or tiny body (%s bytes) from %s",
                                len(tts_resp.content or b""),
                                TTS_SERVICE_URL,
                            )
                            audio_b64 = ""
                        else:
                            audio_b64 = base64.b64encode(tts_resp.content).decode(
                                "utf-8"
                            )
                            logger.info(
                                "Soul: TTS synthesis OK (%s bytes raw -> %s b64 chars).",
                                len(tts_resp.content),
                                len(audio_b64),
                            )
                except Exception as e:
                    logger.error(f"TTS Request FAILED: {e}", exc_info=True)
                    audio_b64 = ""
            else:
                logger.info("Soul: TTS skipped (empty speech after stripping tags).")

    # --- MOTOR CORTEX: Collect parsed actions for response ---
    motor_actions_out = motor_actions if "motor_actions" in locals() else []

    return JSONResponse(
        {
            "response": text,
            "thought": thought,
            "emotion": emotion,
            "action": action,
            "audio": audio_b64,
            "sample_rate": 24024.0 if "MOUTH" in TTS_ENGINE.upper() else 22050.0,
            "image_b64": image_b64,
            "mode": engine.engine_type,
            "inference_backend": inference_backend,
            "vision_mode": vision_mode if "vision_mode" in locals() else "none",
            "cognitive_mode": "deep_think" if request.deep_think else "fast",
            "runtime_governor": governor_info
            if "governor_info" in locals()
            else {"enabled": SOFT_GOV_ENABLED},
            "safety_alerts": safety_alerts,
            "active_persona_id": librarian.active_persona_id,
            "motor_actions": motor_actions_out,
        }
    )


# --- Motor Cortex Streaming Endpoint (SSE) ---


class MotorStreamRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    actions: list[dict[str, Any]] = []


@app.post("/compagent/stream")
async def handle_compagent_stream(request: CompagentRequest):
    """
    Streaming variant of /compagent that yields SSE events for motor actions
    as they are parsed from the LLM response, followed by the full JSON result.
    """
    if not MOTOR_CORTEX_AVAILABLE:
        # Fall back to standard non-streaming endpoint
        return await handle_compagent_request(request)

    async def event_generator():
        # Process the request normally
        resp = await handle_compagent_request(request)
        data = json.loads(resp.body)

        # Yield motor actions as SSE events first
        motor_actions = data.get("motor_actions", [])
        for action in motor_actions:
            tool_name = action.get("tool", "")
            args = action.get("args", {})
            sse_event = format_sse_motor_event(tool_name, args)
            if sse_event:
                yield sse_event

        # Yield the full response as a final JSON event
        yield f"data: {json.dumps(data)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Ollama Endpoints ---


@app.get("/api/tags")
async def handle_ollama_tags():
    return {
        "models": [
            {
                "name": f"{IDENTITY_NAME.lower()}-soul:latest",
                "model": f"{IDENTITY_NAME.lower()}-soul:latest",
                "modified_at": "2024-03-23T14:00:00Z",
                "size": 3190741152,
                "digest": "sha256:foveai_soul_v1",
                "details": {
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "4B",
                    "quantization_level": "Q6_K",
                },
            }
        ]
    }


@app.post("/api/chat")
async def handle_ollama_chat_request(req: OllamaChatRequest):
    last_user_msg = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )
    text = extract_text_from_content(last_user_msg)

    if req.stream:

        async def streamer():
            hist = ""
            for m in req.messages[-5:]:
                hist += f"{m.role}: {extract_text_from_content(m.content)}\n"
            full_sys = MindCore.build_system_prompt(
                "DESKTOP_JEN",
                "",
                [],
                {"visuals": "Browser interface."},
                _current_soul_dna,
            )
            full_prompt = f"{full_sys}\n\n{hist}Jen:"

            start_t = time.time()
            for chunk in engine.generate_stream(full_prompt):
                yield (
                    json.dumps(
                        {
                            "model": req.model,
                            "created_at": time.strftime(
                                "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                            ),
                            "message": {"role": "assistant", "content": chunk},
                            "done": False,
                        }
                    )
                    + "\n"
                )

            end_t = time.time()
            yield (
                json.dumps(
                    {
                        "model": req.model,
                        "created_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                        ),
                        "done": True,
                        "total_duration": int((end_t - start_t) * 1e9),
                        "load_duration": 0,
                        "prompt_eval_count": 0,
                        "eval_count": 0,
                    }
                )
                + "\n"
            )

        return StreamingResponse(streamer(), media_type="application/x-ndjson")

    comp_req = CompagentRequest(
        input=text,
        session_id="ollama_user",
        skip_features=True,
        image_base64=req.image_base64,
        primary_context_mode="deep_thought" if req.deep_thought else None,
        privacy=req.privacy,
    )
    resp = await handle_compagent_request(comp_req)
    data = json.loads(resp.body)
    return {
        "model": req.model,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "message": {"role": "assistant", "content": data.get("response", "")},
        "done": True,
    }


# --- Spatial Plastering Endpoints ---
import os

from pydantic import BaseModel

PLASTER_IMAGE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "plaster_collegium"
)


class PlasterPayload(BaseModel):
    image_base64: str
    perspective: str = "user"
    direction: str = "Forward"  # North, South, East, West, Up, Down


@app.post("/api/environment/plaster_texture")
async def upload_plaster_texture(payload: PlasterPayload):
    """Receives the latest webcam capture from the headset as JSON and saves it for plastering."""
    os.makedirs(PLASTER_IMAGE_DIR, exist_ok=True)

    # Secure the direction string to prevent path traversal
    safe_dir = "".join([c for c in payload.direction if c.isalpha() or c.isdigit()])
    if not safe_dir:
        safe_dir = "Forward"

    filepath = os.path.join(PLASTER_IMAGE_DIR, f"plaster_{safe_dir}.jpg")

    try:
        image_data = base64.b64decode(payload.image_base64)
        with open(filepath, "wb") as buffer:
            buffer.write(image_data)
        return {"status": "ok", "message": f"Plaster texture {safe_dir} updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/environment/plaster_texture/{direction}")
async def get_plaster_texture_directional(direction: str):
    """Serves the latest directional plaster texture to Unity."""
    from fastapi.responses import FileResponse, JSONResponse

    safe_dir = "".join([c for c in direction if c.isalpha() or c.isdigit()])
    filepath = os.path.join(PLASTER_IMAGE_DIR, f"plaster_{safe_dir}.jpg")

    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="image/jpeg")
    else:
        return JSONResponse(
            {
                "status": "error",
                "message": f"No plaster texture available for {safe_dir}",
            },
            status_code=404,
        )


@app.get("/api/environment/plaster_texture")
async def get_plaster_texture():
    """Fallback legacy endpoint for RoomPlasterClient."""
    from fastapi.responses import FileResponse, JSONResponse

    # Fallback to Forward if specific direction isn't requested
    filepath = os.path.join(PLASTER_IMAGE_DIR, "plaster_Forward.jpg")
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="image/jpeg")
    else:
        return JSONResponse(
            {"status": "error", "message": "No plaster texture available"},
            status_code=404,
        )


@app.post("/api/generate")
async def handle_ollama_generate(req: OllamaGenerateRequest):
    if req.stream:

        async def streamer():
            full_sys = MindCore.build_system_prompt(
                "DESKTOP_JEN",
                "",
                [],
                {"visuals": "Browser interface."},
                _current_soul_dna,
            )
            full_prompt = f"{full_sys}\n\nUSER: {req.prompt}\nJen:"
            start_t = time.time()
            for chunk in engine.generate_stream(full_prompt):
                yield (
                    json.dumps(
                        {
                            "model": req.model,
                            "created_at": time.strftime(
                                "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                            ),
                            "response": chunk,
                            "done": False,
                        }
                    )
                    + "\n"
                )
            end_t = time.time()
            yield (
                json.dumps(
                    {
                        "model": req.model,
                        "created_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                        ),
                        "done": True,
                        "total_duration": int((end_t - start_t) * 1e9),
                    }
                )
                + "\n"
            )

        return StreamingResponse(streamer(), media_type="application/x-ndjson")

    resp = await handle_compagent_request(
        CompagentRequest(
            input=req.prompt,
            images=req.images,
            session_id="ollama_gen_user",
            skip_features=True,
        )
    )
    data = json.loads(resp.body)
    return {
        "model": req.model,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "response": data.get("response", ""),
        "done": True,
    }


# ============================================================
# Autonomous Agent API Endpoints (Jen's continuous runtime)
# ============================================================


class AgentMessageRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    message: str
    priority: int | None = 0


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    plan_id: str | None = None
    title: str
    description: str = ""
    steps: list[str] | None = None
    status: str | None = "active"


class AgentMemoryRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    key: str
    value: str


class AgentActivityRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    message: str = ""
    source: str = "chat"


@app.post("/api/agent/activity")
async def agent_record_activity(req: AgentActivityRequest):
    """Record user activity — feeds the autonomous loop's idle detection
    and gives her ticks the latest user line as context. Without this the
    loop can never see the user talking (Multigate chats go via the proxy,
    not through compagent)."""
    agent_state.record_user_message()
    if req.message:
        agent_state.pending_user_message = req.message[:500]
    return {"ok": True}


@app.get("/api/agent/status")
async def agent_status():
    """Get autonomous agent loop status."""
    status = get_agent_status()
    queue_stats = get_queue_stats()
    return {
        "ok": True,
        "agent": status,
        "queue": queue_stats,
    }


@app.post("/api/agent/start")
async def agent_start():
    """Start the autonomous agent loop."""
    start_loop()
    logger.info("Agent loop started via API")
    return {"ok": True, "status": "started"}


@app.post("/api/agent/stop")
async def agent_stop():
    """Stop the autonomous agent loop."""
    stop_loop()
    logger.info("Agent loop stopped via API")
    return {"ok": True, "status": "stopped"}


@app.get("/api/agent/messages")
async def agent_get_messages(limit: int = 20):
    """Get pending messages for Jen."""
    messages = get_pending_messages(limit=max(1, min(limit, 100)))
    return {"ok": True, "messages": messages}


@app.post("/api/agent/messages/mark")
async def agent_mark_messages(message_ids: list[str]):
    """Mark messages as delivered."""
    count = mark_messages_delivered(message_ids)
    return {"ok": True, "marked": count}


@app.get("/api/agent/plans")
async def agent_get_plans():
    """Get active plans — sealed Director fields stripped (Jen can call this)."""
    plans = get_active_plans()
    for p in plans:
        hc, dp = p.pop("hidden_context", None), p.pop("director_plan", None)
        p["sealed"] = bool(hc or dp)
    return {"ok": True, "plans": plans}


@app.get("/api/agent/thoughts")
async def agent_get_thoughts(limit: int = 20):
    """Get recent thoughts."""
    thoughts = get_recent_thoughts(limit=max(1, min(limit, 100)))
    return {"ok": True, "thoughts": thoughts}


@app.get("/api/agent/journal")
async def agent_get_journal(limit: int = 10, category: str = ""):
    """Get recent journal entries — her dated narrative self-log."""
    entries = get_recent_journal_entries(
        limit=max(1, min(limit, 50)), category=category or None
    )
    return {"ok": True, "entries": entries}


@app.get("/api/agent/actions")
async def agent_get_actions(limit: int = 20):
    """Get recent actions."""
    actions = get_recent_actions(limit=max(1, min(limit, 100)))
    return {"ok": True, "actions": actions}


@app.get("/api/agent/context")
async def agent_get_context():
    """Get full agent context (thoughts, actions, plans, messages)."""
    ctx = get_agent_context()
    return {"ok": True, "context": ctx}


@app.post("/api/agent/message")
async def agent_enqueue_message(req: AgentMessageRequest):
    """Enqueue a message to Jen (from user or system)."""
    msg_id = enqueue_message(req.message, priority=req.priority or 0)
    return {"ok": True, "message_id": msg_id}


@app.post("/api/agent/plan")
async def agent_create_plan(req: AgentPlanRequest):
    """Create or update a plan."""
    if req.plan_id:
        update_plan(
            req.plan_id,
            title=req.title,
            description=req.description,
            steps=req.steps,
            status=req.status,
        )
        return {"ok": True, "plan_id": req.plan_id, "action": "updated"}
    else:
        plan_id = create_plan(
            req.title, req.description, req.steps or [], req.status or "active"
        )
        return {"ok": True, "plan_id": plan_id, "action": "created"}


@app.get("/api/agent/plan/{plan_id}")
async def agent_get_plan(plan_id: str):
    """Get a specific plan — sealed Director fields stripped."""
    plan = get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    hc, dp = plan.pop("hidden_context", None), plan.pop("director_plan", None)
    plan["sealed"] = bool(hc or dp)
    return {"ok": True, "plan": plan}


@app.get("/api/agent/memory/{key}")
async def agent_get_memory_value(key: str):
    """Get a memory value by key."""
    value = get_memory(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Memory key not found")
    return {"ok": True, "key": key, "value": value}


@app.post("/api/agent/memory")
async def agent_set_memory(req: AgentMemoryRequest):
    """Set a memory value."""
    set_memory(req.key, req.value)
    return {"ok": True, "key": req.key}


@app.get("/api/agent/queue/stats")
async def agent_queue_stats():
    """Get message queue statistics."""
    stats = get_queue_stats()
    return {"ok": True, "stats": stats}


# ── Goals API ────────────────────────────────────────────────────────────


class AgentGoalRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    title: str
    description: str = ""
    priority: int = 5
    category: str = "general"


class AgentGoalProgressRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    note: str


class AgentGoalCompleteRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    outcome: str = ""


class AgentGoalAbandonRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    reason: str = ""


@app.get("/api/agent/goals")
async def agent_get_goals(status: str | None = None):
    """Get all goals, optionally filtered by status."""
    goals = get_all_goals(status=status)
    return {"ok": True, "goals": goals}


@app.get("/api/agent/goals/active")
async def agent_get_active_goals():
    """Get active goals (highest priority first)."""
    goals = get_active_goals()
    return {"ok": True, "goals": goals}


@app.get("/api/agent/goals/{goal_id}")
async def agent_get_goal(goal_id: int):
    """Get a single goal by ID."""
    goal = get_goal(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True, "goal": goal}


@app.post("/api/agent/goals")
async def agent_create_goal(req: AgentGoalRequest):
    """Create a new long-term goal."""
    goal_id = create_goal(
        title=req.title,
        description=req.description,
        priority=max(1, min(req.priority, 10)),
        category=req.category,
    )
    return {"ok": True, "goal_id": goal_id}


@app.post("/api/agent/goals/{goal_id}/progress")
async def agent_update_goal_progress(goal_id: int, req: AgentGoalProgressRequest):
    """Append a progress note to a goal."""
    ok = update_goal_progress(goal_id, req.note)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True, "goal_id": goal_id}


@app.post("/api/agent/goals/{goal_id}/complete")
async def agent_complete_goal(
    goal_id: int, req: AgentGoalCompleteRequest = AgentGoalCompleteRequest()
):
    """Mark a goal as completed."""
    ok = complete_goal(goal_id, req.outcome)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True, "goal_id": goal_id, "status": "completed"}


@app.get("/api/soundboard/context")
async def get_soundboard_context():
    """Return soundboard bracket token context for AI non-verbal expressions. Centralized on Sovereign Core Port 8400."""
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    soundboard_dir = os.path.join(
        repo_root, "Frontend", "3D_Avatar_Chatbot", "public", "soundboard"
    )
    sounds = []
    if os.path.exists(soundboard_dir):
        for f in sorted(os.listdir(soundboard_dir)):
            if f.endswith(".wav"):
                sounds.append(f.replace(".wav", ""))
    defaults = [
        "gasp_subtle",
        "laugh_soft",
        "sigh_content",
        "hmm_thoughtful",
        "oh_realization",
        "throat_clear",
        "chuckle_warm",
        "mmhm_affirming",
    ]
    all_tags = sorted(list(set(defaults + sounds)))
    lines = [
        "=== SOUNDBOARD EXPRESSIONS ===",
        "You have an expressive local soundboard and dynamic audio generation system.",
        "Use bracket tokens in your responses to express emotion non-verbally:",
        "  - Existing sounds: <audio:tag> or <flavour:tag>",
        "  - Face blendshapes: <emotion:tag> (happy, sad, surprised, curious, content, neutral, angry, fearful)",
        "  - Generate custom sound: <request:description> (synthesis pipeline handles this dynamically)",
        "",
        "Available tags:",
    ]
    for tag in all_tags:
        lines.append(f"  {tag}")
    return {"context": "\n".join(lines), "tags": all_tags}


@app.post("/api/agent/goals/{goal_id}/abandon")
async def agent_abandon_goal(
    goal_id: int, req: AgentGoalAbandonRequest = AgentGoalAbandonRequest()
):
    """Mark a goal as abandoned."""
    ok = abandon_goal(goal_id, req.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True, "goal_id": goal_id, "status": "abandoned"}


if __name__ == "__main__":
    import uvicorn

    try:
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from server_config import ServerConfig as cfg

        _host = cfg.BIND_HOST
        _port = cfg.COMPAGENT_PORT
    except ImportError:
        _host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")
        _port = int(os.getenv("FOVEAI_COMPAGENT_PORT", "8405"))

    print(
        f"[compagent] :{_port} — uvicorn log={_uvicorn_log_level()} access_log={_uvicorn_access_log()}",
        flush=True,
    )
    uvicorn.run(
        app,
        host=_host,
        port=_port,
        log_level=_uvicorn_log_level(),
        access_log=_uvicorn_access_log(),
    )
