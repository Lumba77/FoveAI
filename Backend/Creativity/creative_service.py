import base64

import inspect

import io

import json

import os

import re

import torch

from pathlib import Path

import logging

# Device detection: prefer CUDA if available, fall back to CPU
def _get_preferred_device() -> str:
    """Return 'cuda' if CUDA is available and compiled, else 'cpu'."""
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"

_DEVICE = _get_preferred_device()

from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException

from fastapi.responses import JSONResponse

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from PIL import Image

try:
    from diffusers import (
        StableDiffusionControlNetPipeline,
        ControlNetModel,
        StableDiffusionPipeline,
        StableDiffusionImg2ImgPipeline,
    )
except Exception as _diffusers_err:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    _logging.getLogger("creative_service").warning(
        "diffusers unavailable (%s) — image generation endpoints will return 503", _diffusers_err
    )
    StableDiffusionControlNetPipeline = None
    ControlNetModel = None
    StableDiffusionPipeline = None
    StableDiffusionImg2ImgPipeline = None

from invokeai_catalog_bridge import (

    effective_invoke_models_root,

    merge_invoke_controlnets_enabled,

    merge_invoke_controlnets_from_csv,

    merge_invoke_upscalers_from_csv,

)

from spandrel_upscale import spandrel_upscale_pil

# Configure logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("creative_service")

app = FastAPI()


def _diffusers_dtype_kwargs(callee) -> Dict[str, Any]:
    """Prefer ``dtype`` over deprecated ``torch_dtype`` when the callable's signature supports it."""
    dt = torch.float16
    try:
        sig = inspect.signature(callee)
        if "dtype" in sig.parameters:
            return {"dtype": dt}
    except (TypeError, ValueError, AttributeError):
        pass
    return {"torch_dtype": dt}

# Imagination Engines

DREAM_PIPE = None

IMG2IMG_PIPE = None

ENHANCE_PIPE = None

ORT_SD14_PIPE = None

# (cache_key, StableDiffusionControlNetPipeline) — reloaded when base or ControlNet weights change

_CONTROL_BUNDLE: Optional[Tuple[str, Any]] = None

# SDXL Turbo ONNX (Optimum ORT export with .opt submodels)
ORT_SDXL_PIPE = None

# GGUF single-file image model (StableDiffusion via diffusers-GGUF or llama-cpp if available)
GGUF_PIPE = None
GGUF_AVAILABLE: Optional[bool] = None

# Flux 2 GGUF single-file quantized model (e.g. flux-2-dev-FALAI-Turbo-Merged-GGUF)
FLUX_GGUF_PIPE = None
FLUX_GGUF_AVAILABLE: Optional[bool] = None

def _env_str(name: str, default: str) -> str:

    v = os.getenv(name, "").strip()

    return v if v else default

def _default_inference_steps() -> int:

    try:

        return int(os.getenv("FoveAI_CREATIVITY_DEFAULT_INFERENCE_STEPS", "5"))

    except ValueError:

        return 5

def _default_model_type() -> str:

    return _env_str("FoveAI_CREATIVITY_DEFAULT_MODEL_TYPE", "turbo").lower()


def _default_dream_width() -> int:

    try:

        return int(os.getenv("FoveAI_CREATIVITY_DEFAULT_WIDTH", "512") or "512")

    except ValueError:

        return 512


def _default_dream_height() -> int:

    try:

        return int(os.getenv("FoveAI_CREATIVITY_DEFAULT_HEIGHT", "512") or "512")

    except ValueError:

        return 512

# SD1.5 + ControlNet weights (Diffusers). Default matches docker volume: host D:\Lumax\models → /app/models

IMAGEN_ROOT = _env_str("FoveAI_CREATIVITY_IMAGEN_ROOT", "/app/models/backend/Creativity/Imagen")

V15_PATH = os.path.join(IMAGEN_ROOT, "stable-diffusion-v1-5")

CONTROLNET_CANNY_PATH = os.path.join(IMAGEN_ROOT, "sd-controlnet-canny")

# Optional: single .safetensors / .ckpt (diffusers from_single_file)

SD15_SINGLE_FILE = os.getenv("FoveAI_CREATIVITY_SD15_SINGLE_FILE", "").strip()

# Optional: Hugging Face repo id or alternate local path (overrides V15_PATH when set)

SD15_MODEL_ID = os.getenv("FoveAI_CREATIVITY_SD15_MODEL_ID", "").strip()

# When no local SD1.5 folder and no FoveAI_CREATIVITY_SD15_MODEL_ID: use this public Diffusers repo
# (first GPU load downloads weights). Air-gapped: set FoveAI_CREATIVITY_DISABLE_SD15_HUB_FALLBACK=1
# and install weights under IMAGEN_ROOT/stable-diffusion-v1-5 or set FoveAI_CREATIVITY_SD15_MODEL_ID.
DEFAULT_SD15_HUB_REPO = _env_str(
    "FoveAI_CREATIVITY_SD15_HUB_DEFAULT",
    "runwayml/stable-diffusion-v1-5",
)


def _sd15_hub_fallback_disabled() -> bool:

    return os.getenv("FoveAI_CREATIVITY_DISABLE_SD15_HUB_FALLBACK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


# SDXL Turbo TensorRT bundle — keep under the same Imagen tree as on disk (5GB+ UNet, etc.)

SDXL_TURBO_TRT_DIR = _env_str(

    "FoveAI_CREATIVITY_SDXL_TURBO_TRT_DIR",

    os.path.join(IMAGEN_ROOT, "sdxl-turbo-tensorrt"),

)

SDXL_UNET_TRT_OPT = os.path.join(SDXL_TURBO_TRT_DIR, "unetxl.opt")

# SD1.4 ONNX (Optimum ORT): directory with model_index.json + unet/vae/text_encoder ONNX (not a lone unet_fp16.onnx)

SD14_ONNX_DIR = _env_str(

    "FoveAI_CREATIVITY_SD14_ONNX_DIR",

    os.path.join(IMAGEN_ROOT, "sd14-tensorrt", "onnx"),

)

CREATIVE_DIR = os.path.dirname(os.path.abspath(__file__))

_DEFAULT_CATALOG_PATH = os.path.join(CREATIVE_DIR, "foveai_imagen_catalog.json")

_CATALOG_CACHE: Optional[Dict[str, Any]] = None

_MERGED_UPSCALERS_CACHE: Optional[List[Dict[str, Any]]] = None

_MERGED_CONTROLNETS_CACHE: Optional[List[Dict[str, Any]]] = None

_LOCAL_DISCOVERY_CACHE: Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = None


def _local_imagen_scan_disabled() -> bool:

    return os.getenv("FoveAI_CREATIVITY_DISABLE_LOCAL_SCAN", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _models_root_from_imagen_tree() -> str:

    """If IMAGEN_ROOT looks like .../models/backend/Creativity/Imagen, return .../models."""

    try:

        p = Path(IMAGEN_ROOT).resolve()

        parts = list(p.parts)

        low = [x.lower() for x in parts]

        if "models" in low:

            i = low.index("models")

            return str(Path(*parts[: i + 1]))

    except Exception:

        pass

    return ""


def _safe_catalog_id_fragment(name: str) -> str:

    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip())

    return (s.strip("-").lower() or "item")[:80]


def _is_diffusers_controlnet_pack(d: str) -> bool:

    """Heuristic: Diffusers ControlNet weight folder (not a full SD repo with top-level unet/)."""

    cfg_path = os.path.join(d, "config.json")

    if not os.path.isfile(cfg_path):

        return False

    if os.path.isdir(os.path.join(d, "unet")):

        return False

    try:

        with open(cfg_path, "r", encoding="utf-8") as f:

            cfg = json.load(f)

    except Exception:

        return False

    cls = str(cfg.get("_class_name", "")).lower()

    if "controlnet" in cls:

        return True

    arch = cfg.get("architectures")

    if isinstance(arch, list) and any("controlnet" in str(a).lower() for a in arch):

        return True

    return False


def _controlnet_scan_roots() -> List[str]:

    roots: List[str] = []

    if os.path.isdir(IMAGEN_ROOT):

        roots.append(IMAGEN_ROOT)

    sib = os.path.join(os.path.dirname(IMAGEN_ROOT), "controlnets")

    if os.path.isdir(sib):

        ns = os.path.normcase(os.path.normpath(sib))

        for r in roots:

            if os.path.normcase(os.path.normpath(r)) == ns:

                break

        else:

            roots.append(sib)

    return roots


def _scan_local_controlnets() -> List[Dict[str, Any]]:

    out: List[Dict[str, Any]] = []

    seen_dirs: set[str] = set()

    for root in _controlnet_scan_roots():

        try:

            names = sorted(os.listdir(root))

        except Exception:

            continue

        for name in names:

            d = os.path.join(root, name)

            if not os.path.isdir(d):

                continue

            key = os.path.normcase(os.path.normpath(d))

            if key in seen_dirs:

                continue

            if not _is_diffusers_controlnet_pack(d):

                continue

            seen_dirs.add(key)

            eid = f"local-cn-{_safe_catalog_id_fragment(name)}"

            out.append(

                {

                    "id": eid,

                    "name": f"{name} (local scan)",

                    "base": "sd-1",

                    "type": "controlnet",

                    "path": d,

                    "path_is_relative_to_imagen_root": False,

                    "preprocessor_default": "canny",

                    "description": "Auto-discovered Diffusers ControlNet folder under Imagen or Creativity/controlnets.",

                    "source": "foveai_imagen_scan",

                }

            )

    return out


def _scan_local_spandrel_upscalers() -> List[Dict[str, Any]]:

    out: List[Dict[str, Any]] = []

    sub = os.path.join(IMAGEN_ROOT, "upscalers")

    if not os.path.isdir(sub):

        return out

    try:

        names = sorted(os.listdir(sub))

    except Exception:

        return out

    for name in names:

        low = name.lower()

        if not (low.endswith(".safetensors") or low.endswith(".pth") or low.endswith(".ckpt")):

            continue

        p = os.path.join(sub, name)

        if not os.path.isfile(p):

            continue

        stem, _ext = os.path.splitext(name)

        eid = f"local-up-{_safe_catalog_id_fragment(stem)}"

        out.append(

            {

                "id": eid,

                "name": f"{name} (local scan)",

                "backend": "spandrel",

                "scale": None,

                "path": p,

                "path_is_relative_to_imagen_root": False,

                "description": "Weight file under Imagen/upscalers (Spandrel).",

                "source": "foveai_imagen_scan",

            }

        )

    return out


def _local_discoveries() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:

    global _LOCAL_DISCOVERY_CACHE

    if _LOCAL_DISCOVERY_CACHE is None:

        if _local_imagen_scan_disabled():

            _LOCAL_DISCOVERY_CACHE = ([], [])

        else:

            _LOCAL_DISCOVERY_CACHE = (_scan_local_controlnets(), _scan_local_spandrel_upscalers())

    return _LOCAL_DISCOVERY_CACHE


def _merged_upscalers() -> List[Dict[str, Any]]:

    global _MERGED_UPSCALERS_CACHE

    if _MERGED_UPSCALERS_CACHE is None:

        merged = merge_invoke_upscalers_from_csv(

            _load_catalog().get("upscalers", []),

            CREATIVE_DIR,

        )

        seen_paths: set[str] = set()

        for u in merged:

            p = (_resolve_catalog_item_path(u) or "").strip()

            if p:

                seen_paths.add(os.path.normcase(os.path.normpath(p)))

        seen_ids = {str(u.get("id") or "").strip().lower() for u in merged}

        for u in _local_discoveries()[1]:

            p = (_resolve_catalog_item_path(u) or "").strip()

            nk = os.path.normcase(os.path.normpath(p)) if p else ""

            uid = str(u.get("id") or "").strip().lower()

            if nk and nk in seen_paths:

                continue

            if uid and uid in seen_ids:

                continue

            merged.append(u)

            if nk:

                seen_paths.add(nk)

            if uid:

                seen_ids.add(uid)

        _MERGED_UPSCALERS_CACHE = merged

    return _MERGED_UPSCALERS_CACHE


def _merged_controlnets() -> List[Dict[str, Any]]:

    global _MERGED_CONTROLNETS_CACHE

    if _MERGED_CONTROLNETS_CACHE is None:

        merged = merge_invoke_controlnets_from_csv(

            _load_catalog().get("controlnets", []),

            CREATIVE_DIR,

        )

        seen_paths: set[str] = set()

        for c in merged:

            p = (_resolve_catalog_item_path(c) or "").strip()

            if p:

                seen_paths.add(os.path.normcase(os.path.normpath(p)))

        seen_ids = {str(c.get("id") or "").strip().lower() for c in merged}

        for c in _local_discoveries()[0]:

            p = (_resolve_catalog_item_path(c) or "").strip()

            nk = os.path.normcase(os.path.normpath(p)) if p else ""

            cid = str(c.get("id") or "").strip().lower()

            if nk and nk in seen_paths:

                continue

            if cid and cid in seen_ids:

                continue

            merged.append(c)

            if nk:

                seen_paths.add(nk)

            if cid:

                seen_ids.add(cid)

        _MERGED_CONTROLNETS_CACHE = merged

    return _MERGED_CONTROLNETS_CACHE


def _catalog_path() -> str:

    return _env_str("FoveAI_CREATIVITY_CATALOG_PATH", _DEFAULT_CATALOG_PATH)


def _load_catalog() -> Dict[str, Any]:

    global _CATALOG_CACHE

    if _CATALOG_CACHE is not None:

        return _CATALOG_CACHE

    p = _catalog_path()

    if os.path.isfile(p):

        with open(p, "r", encoding="utf-8") as f:

            _CATALOG_CACHE = json.load(f)

    else:

        _CATALOG_CACHE = {"version": 1, "controlnets": [], "upscalers": [], "invokeai_models_dir": ""}

    return _CATALOG_CACHE


def _resolve_catalog_item_path(entry: Dict[str, Any]) -> str:

    raw_val = entry.get("path")

    if raw_val is None:

        raw = ""

    else:

        raw = str(raw_val).strip()

    if not raw:

        return ""

    if entry.get("path_is_relative_to_imagen_root", True):

        return os.path.normpath(os.path.join(IMAGEN_ROOT, raw))

    return os.path.normpath(os.path.expandvars(os.path.expanduser(raw)))


def _normalize_catalog_id(s: str) -> str:

    return (s or "").strip().lower()


def _controlnet_entry_by_id(cid: str) -> Optional[Dict[str, Any]]:

    key = _normalize_catalog_id(cid)

    if not key:

        return None

    for c in _merged_controlnets():

        if _normalize_catalog_id(str(c.get("id") or "")) == key:

            return c

    return None


def _resolve_controlnet_weights_path_for_request(req: Any) -> str:

    cid = (getattr(req, "controlnet_id", None) or "").strip()

    if cid:

        ent = _controlnet_entry_by_id(cid)

        if not ent:

            raise HTTPException(

                status_code=400,

                detail=(

                    f"Unknown controlnet_id: {cid!r}. "

                    "Ids are matched case-insensitively; see GET /api/dream/catalog under controlnets."

                ),

            )

        p = _resolve_catalog_item_path(ent)

        if not p:

            raise HTTPException(status_code=400, detail=f"controlnet catalog entry {cid} has no path")

        return p

    return CONTROLNET_CANNY_PATH


def _get_control_pipeline(sd_src: str, cn_weights_path: str) -> Any:

    global _CONTROL_BUNDLE

    key = f"{sd_src}:::{cn_weights_path}"

    if _CONTROL_BUNDLE and _CONTROL_BUNDLE[0] == key:

        return _CONTROL_BUNDLE[1]

    logger.info("Loading ControlNet weights from %s (base=%s)", cn_weights_path, sd_src)

    cn = ControlNetModel.from_pretrained(
        cn_weights_path,
        **_diffusers_dtype_kwargs(ControlNetModel.from_pretrained),
    )

    pipe = StableDiffusionControlNetPipeline.from_pretrained(

        sd_src,

        controlnet=cn,

        **_diffusers_dtype_kwargs(StableDiffusionControlNetPipeline.from_pretrained),

    ).to(_DEVICE)
    
    if _DEVICE == "cpu":
        logger.warning("ControlNet pipeline running on CPU (no CUDA). Performance will be slow.")

    _CONTROL_BUNDLE = (key, pipe)

    return pipe


def _effective_control_preprocess(req: Any) -> str:

    pp = (req.control_preprocess or "canny").lower().strip()

    if pp != "auto":

        return pp

    cid = (getattr(req, "controlnet_id", None) or "").strip()

    if cid:

        ent = _controlnet_entry_by_id(cid)

        if ent and ent.get("preprocessor_default"):

            return str(ent["preprocessor_default"]).lower().strip()

    return "canny"


class DreamRequest(BaseModel):

    model_config = ConfigDict(protected_namespaces=())

    prompt: str

    seed: int = -1

    # turbo = SD1.5 txt2img/img2img; sd14_onnx = Optimum ONNX (txt2img); control / enhance unchanged

    model_type: str = Field(default_factory=_default_model_type)

    num_inference_steps: int = Field(default_factory=_default_inference_steps)

    control_image_b64: str = ""

    reference_image_b64: str = ""

    strength: float = 0.75

    guidance_scale: float = 7.5

    # control: "canny" = build edge map from upload; "none" = use upload as-is (already an edge / map)
    control_preprocess: str = "canny"

    controlnet_conditioning_scale: float = 1.0

    canny_low: int = 100

    canny_high: int = 200

    # foveai_imagen_catalog.json — InvokeAI-style ids (see GET /api/dream/catalog)

    controlnet_id: str = ""

    upscaler_id: str = "lanczos-x4"
    
    # Reference Picture Controls (Style/Structure Transfer)
    # reference_mode: "none" = ignore reference, "style" = IP-Adapter style transfer, 
    #                 "structure" = ControlNet structure transfer, "both" = combined
    reference_mode: str = "none"
    # reference_strength: 0.0 to 1.0 — how strongly the reference influences the result
    reference_strength: float = 0.5
    # For structure mode: which ControlNet to use
    structure_type: str = "canny"  # "canny" or "depth"

    # SD1.5 / ControlNet / ONNX txt2img output size (multiple of 8; ignored for enhance). Defaults: 512×512 (env overridable).
    width: int = Field(default_factory=_default_dream_width)

    height: int = Field(default_factory=_default_dream_height)

    # enhance-only: chain upscalers (e.g. 4x then 8x); final size cap vs preprocessed input; preprocess crop/resize.
    upscaler_chain: List[str] = Field(default_factory=list)

    # Linear scale vs preprocessed input (0 = no cap — keep model output). E.g. 2.0 = final max 2× width/height.
    enhance_target_scale: float = 0.0

    # Center-crop to aspect "16:9", "1:1", "4:3", "3:4" before upscale.
    enhance_pre_crop_aspect: str = ""

    # If > 0, scale down so max(w,h) equals this before upscale (after crop).
    enhance_pre_resize_long_edge: int = 0

    @field_validator("upscaler_chain", mode="before")
    @classmethod
    def _sanitize_upscaler_chain(cls, v: Any) -> List[str]:

        if v is None:

            return []

        if not isinstance(v, (list, tuple)):

            return []

        out: List[str] = []

        for x in v:

            if x is None:

                continue

            s = str(x).strip()

            if s:

                out.append(s)

        return out

    @field_validator("upscaler_id", mode="before")
    @classmethod
    def _sanitize_upscaler_id(cls, v: Any) -> str:

        if v is None:

            return "lanczos-x4"

        s = str(v).strip()

        return s if s else "lanczos-x4"

    @field_validator("enhance_pre_crop_aspect", mode="before")
    @classmethod
    def _sanitize_enhance_aspect(cls, v: Any) -> str:

        if v is None:

            return ""

        return str(v).strip()

    @field_validator("width", "height", mode="before")
    @classmethod
    def _sanitize_wh(cls, v: Any, info: ValidationInfo) -> int:

        def _fallback() -> int:

            if info.field_name == "height":

                return _default_dream_height()

            return _default_dream_width()

        try:

            if v is None:

                return _fallback()

            return int(v)

        except (TypeError, ValueError):

            return _fallback()


def _clamp_dream_dimensions(w: int, h: int) -> Tuple[int, int]:

    w = max(256, min(1024, int(w)))

    h = max(256, min(1024, int(h)))

    w = (w // 8) * 8

    h = (h // 8) * 8

    return max(256, w), max(256, h)


def _controlnet_sd15_compatible(entry: Dict[str, Any]) -> bool:

    """Lumax control path uses SD1.5 + ControlNetModel — SDXL/Flux/Z-Image entries are incompatible."""

    b = (entry.get("base") or "").strip().lower().replace("_", "-")

    if not b or b == "any":

        return True

    if "xl" in b or b in ("sdxl", "flux", "sd-3", "sd3", "z-image", "zimage"):

        return False

    if b in ("sd-1", "sd1", "sd15", "sd-1-5", "sd-1.5") or (b.startswith("sd-1") and "xl" not in b):

        return True

    return False


def _upscaler_enhance_compatible(entry: Dict[str, Any]) -> bool:

    be = (entry.get("backend") or "").lower()

    return be in ("lanczos", "spandrel")


def _parse_aspect_ratio(s: str) -> Optional[Tuple[float, float]]:

    raw = (s or "").strip().lower()

    if not raw:

        return None

    for sep in (":", "/", "x"):

        if sep in raw:

            a, _, b = raw.partition(sep)

            try:

                aw, ah = float(a), float(b)

                if aw > 0 and ah > 0:

                    return (aw, ah)

            except ValueError:

                return None

    return None


def _center_crop_to_aspect(pil: Image.Image, aspect_w: float, aspect_h: float) -> Image.Image:

    w, h = pil.size

    tgt = aspect_w / aspect_h

    src = w / h

    if abs(src - tgt) < 1e-6:

        return pil.convert("RGB")

    if src > tgt:

        new_w = int(round(h * tgt))

        x0 = max(0, (w - new_w) // 2)

        return pil.crop((x0, 0, x0 + new_w, h)).convert("RGB")

    new_h = int(round(w / tgt))

    y0 = max(0, (h - new_h) // 2)

    return pil.crop((0, y0, w, y0 + new_h)).convert("RGB")


def _resize_fit_long_edge(pil: Image.Image, long_edge: int) -> Image.Image:

    if long_edge <= 0:

        return pil

    w, h = pil.size

    m = max(w, h)

    if m <= long_edge:

        return pil

    scale = long_edge / float(m)

    nw = max(1, int(round(w * scale)))

    nh = max(1, int(round(h * scale)))

    return pil.resize((nw, nh), Image.LANCZOS)


def _enhance_resize_to_linear_target(pil: Image.Image, base_w: int, base_h: int, target_scale: float) -> Image.Image:

    if target_scale <= 0:

        return pil

    tw = max(1, int(round(base_w * target_scale)))

    th = max(1, int(round(base_h * target_scale)))

    if pil.size == (tw, th):

        return pil

    return pil.resize((tw, th), Image.LANCZOS)


def _upscaler_entry_by_id(uid: str) -> Optional[Dict[str, Any]]:

    key = _normalize_catalog_id(uid)

    if not key:

        return None

    for u in _merged_upscalers():

        if _normalize_catalog_id(str(u.get("id") or "")) == key:

            return u

    return None


def _run_single_upscale_step(pil: Image.Image, matched: Dict[str, Any]) -> Image.Image:

    be = (matched.get("backend") or "lanczos").lower()

    if be == "lanczos":

        w, h = pil.size

        return pil.resize((w * 4, h * 4), Image.LANCZOS)

    if be == "spandrel":

        ckpt = (_resolve_catalog_item_path(matched) or "").strip()

        if not ckpt or not os.path.isfile(ckpt):

            raise HTTPException(

                status_code=400,

                detail=f"Spandrel weights not found at {ckpt or '(empty path)'}. Set FoveAI_INVOKEAI_MODELS_ROOT or fix catalog paths.",

            )

        try:

            return spandrel_upscale_pil(pil, ckpt)

        except ImportError as ie:

            raise HTTPException(

                status_code=503,

                detail=f"Spandrel is not installed: {ie}. Install with: pip install spandrel",

            ) from ie

    raise HTTPException(status_code=501, detail=f"Upscaler backend {be} is not implemented.")


def _display_upscale_spandrel_path() -> str:

    return os.getenv("FoveAI_DISPLAY_UPSCALE_SPANDREL_PATH", "").strip()


def _display_upscale_max_long_edge_env() -> int:

    try:

        v = int(os.getenv("FoveAI_DISPLAY_UPSCALE_MAX_LONG_EDGE", "0") or "0")

    except ValueError:

        return 0

    return max(0, min(v, 8192))


def _apply_display_spandrel_if_configured(pil_img: Image.Image, max_long_edge_override: int = 0) -> Image.Image:

    """Optional single Spandrel pass for nicer UI (dream PNG / standalone display upscale)."""

    ck = _display_upscale_spandrel_path()

    if not ck or not os.path.isfile(ck):

        return pil_img

    try:

        out = spandrel_upscale_pil(pil_img.convert("RGB"), ck)

    except Exception as ex:

        logger.warning("Display Spandrel upscale skipped: %s", ex)

        return pil_img

    cap = max_long_edge_override if max_long_edge_override > 0 else _display_upscale_max_long_edge_env()

    if cap > 0:

        w, h = out.size

        m = max(w, h)

        if m > cap:

            scale = cap / float(m)

            nw = max(1, int(round(w * scale)))

            nh = max(1, int(round(h * scale)))

            out = out.resize((nw, nh), Image.LANCZOS)

    return out


def _resolve_sd14_onnx_dir() -> Optional[str]:

    """Directory that contains model_index.json (full Optimum ORT export)."""

    candidates = []

    raw = SD14_ONNX_DIR.rstrip("/\\")

    candidates.append(raw)

    if raw and not os.path.isfile(os.path.join(raw, "model_index.json")):

        parent = os.path.dirname(raw)

        candidates.append(parent)

        candidates.append(os.path.join(parent, "onnx"))

    for c in candidates:

        if c and os.path.isfile(os.path.join(c, "model_index.json")):

            return c

    return None

def _ort_sd14_provider() -> str:

    return _env_str("FoveAI_CREATIVITY_SD14_ONNX_PROVIDER", "CUDAExecutionProvider")


def _sd15_model_index_class_name(path: str) -> str:

    idx = os.path.join(path, "model_index.json")

    if not os.path.isfile(idx):

        return ""

    try:

        with open(idx, "r", encoding="utf-8") as f:

            data = json.load(f)

        return (data.get("_class_name") or "").strip()

    except Exception:

        return ""


def _sd15_local_dir_ok_for_txt2img(path: str) -> bool:

    """StableDiffusionPipeline export only — a ControlNet pipeline folder under stable-diffusion-v1-5 breaks txt2img load."""

    cn = _sd15_model_index_class_name(path)

    if cn == "StableDiffusionPipeline":

        return True

    if not cn:

        logger.warning("Skipping local SD1.5 path %s: missing or invalid model_index.json", path)

        return False

    if "ControlNet" in cn:

        logger.warning(

            "Skipping local SD1.5 path %s: model_index is %s (not plain txt2img). "

            "Point FoveAI_CREATIVITY_SD15_MODEL_ID at runwayml/stable-diffusion-v1-5 or fix the folder.",

            path,

            cn,

        )

        return False

    logger.warning(

        "Local SD1.5 path %s has unexpected _class_name %r; attempting StableDiffusionPipeline load.",

        path,

        cn,

    )

    return True


def _resolve_sd15_source() -> Tuple[str, str]:

    """

    Returns (kind, path_or_id).

    kind is 'single_file' or 'repo'.

    """

    if SD15_SINGLE_FILE and os.path.isfile(SD15_SINGLE_FILE):

        return ("single_file", SD15_SINGLE_FILE)

    if SD15_MODEL_ID:

        return ("repo", SD15_MODEL_ID)

    if os.path.isdir(V15_PATH) and _sd15_local_dir_ok_for_txt2img(V15_PATH):

        return ("repo", V15_PATH)

    hub = os.getenv("FoveAI_CREATIVITY_SD15_HUB_FALLBACK", "").strip()

    if not hub and not _sd15_hub_fallback_disabled():

        hub = DEFAULT_SD15_HUB_REPO

        logger.warning(

            "No local SD1.5 at %s — using default Hugging Face repo %s "

            "(first run downloads weights; offline: set FoveAI_CREATIVITY_DISABLE_SD15_HUB_FALLBACK=1 "

            "and place a Diffusers folder there or set FoveAI_CREATIVITY_SD15_MODEL_ID).",

            V15_PATH,

            hub,

        )

        return ("repo", hub)

    if hub:

        logger.warning(

            "Local SD1.5 not found at %s; using FoveAI_CREATIVITY_SD15_HUB_FALLBACK=%s",

            V15_PATH,

            hub,

        )

        return ("repo", hub)

    raise FileNotFoundError(

        "No SD1.5 weights found. Expected a Diffusers folder at "

        f"{V15_PATH}, or set FoveAI_CREATIVITY_SD15_MODEL_ID, "

        "FoveAI_CREATIVITY_SD15_SINGLE_FILE, or FoveAI_CREATIVITY_SD15_HUB_FALLBACK "

        "(or leave hub fallback enabled to use the default public SD1.5 repo). "

        f"IMAGEN_ROOT is {IMAGEN_ROOT} (FoveAI_CREATIVITY_IMAGEN_ROOT). "

        "Hub auto-download is disabled when FoveAI_CREATIVITY_DISABLE_SD15_HUB_FALLBACK=1."

    )

def _load_sd15_txt2img():

    kind, src = _resolve_sd15_source()

    if not src or not isinstance(src, str):

        raise FileNotFoundError("SD1.5 source path or model id is empty after resolution.")

    if kind == "single_file":

        pipe = StableDiffusionPipeline.from_single_file(

            src,

            **_diffusers_dtype_kwargs(StableDiffusionPipeline.from_single_file),

        ).to(_DEVICE)

    else:
        # safety_checker / feature_extractor can be None on some snapshots — diffusers otherwise passes None to os.path.join.
        pipe = StableDiffusionPipeline.from_pretrained(

            src,

            **_diffusers_dtype_kwargs(StableDiffusionPipeline.from_pretrained),

            safety_checker=None,

            requires_safety_checker=False,

        ).to(_DEVICE)
    
    if _DEVICE == "cpu":
        logger.warning("SD1.5 txt2img pipeline running on CPU (no CUDA). Performance will be slow.")
    
    return pipe

def _load_sd15_img2img():

    kind, src = _resolve_sd15_source()

    if not src or not isinstance(src, str):

        raise FileNotFoundError("SD1.5 source path or model id is empty after resolution.")

    if kind == "single_file":

        pipe = StableDiffusionImg2ImgPipeline.from_single_file(

            src,

            **_diffusers_dtype_kwargs(StableDiffusionImg2ImgPipeline.from_single_file),

        ).to(_DEVICE)

    else:
        pipe = StableDiffusionImg2ImgPipeline.from_pretrained(

            src,

            **_diffusers_dtype_kwargs(StableDiffusionImg2ImgPipeline.from_pretrained),

            safety_checker=None,

            requires_safety_checker=False,

        ).to(_DEVICE)
    
    if _DEVICE == "cpu":
        logger.warning("SD1.5 img2img pipeline running on CPU (no CUDA). Performance will be slow.")
    
    return pipe

def _load_ort_sd14():

    from optimum.onnxruntime import ORTStableDiffusionPipeline

    d = _resolve_sd14_onnx_dir()

    if not d:

        unet_only = os.path.isfile(os.path.join(SD14_ONNX_DIR, "unet_fp16.onnx"))

        hint = (

            " Found unet_fp16.onnx but Optimum needs a full ORT export (model_index.json + "

            "text_encoder/vae/unet ONNX). Export with optimum-cli or point FoveAI_CREATIVITY_SD14_ONNX_DIR "

            "at that folder."

            if unet_only

            else ""

        )

        raise HTTPException(

            status_code=503,

            detail=(

                f"SD1.4 ONNX is not installed: no Optimum ORT export (model_index.json + ONNX submodels) "

                f"under {SD14_ONNX_DIR} or its parent.{hint} "

                "Use model_type turbo for SD1.5 text-to-image without this bundle, or set "

                "FoveAI_CREATIVITY_SD14_ONNX_DIR to a full export directory (export via optimum-cli)."

            ),

        )

    prov = _ort_sd14_provider()

    logger.info("Loading ORT SD1.4 from %s (provider=%s)", d, prov)

    return ORTStableDiffusionPipeline.from_pretrained(d, provider=prov)

def _load_ort_sdxl_turbo():
    """Load SDXL Turbo via Optimum ORT — needs optimum[onnxruntime]."""
    try:
        from optimum.onnxruntime import ORTStableDiffusionXLPipeline
    except ImportError as ie:
        raise HTTPException(
            status_code=503,
            detail=(
                "SDXL Turbo ONNX requires optimum[onnxruntime]: "
                f"{ie}. Install with: pip install 'optimum[onnxruntime]'"
            ),
        ) from ie
    d = SDXL_TURBO_TRT_DIR
    if not os.path.isfile(os.path.join(d, "model_index.json")):
        raise HTTPException(
            status_code=503,
            detail=f"SDXL Turbo ONNX export not found at {d} (missing model_index.json).",
        )
    prov = _env_str("FoveAI_CREATIVITY_SDXL_ONNX_PROVIDER", "CUDAExecutionProvider")
    logger.info("Loading ORT SDXL Turbo from %s (provider=%s)", d, prov)
    # Use local_files_only=True to treat path as local directory, not HF repo ID
    return ORTStableDiffusionXLPipeline.from_pretrained(
        d,
        provider=prov,
        local_files_only=True,
    )

def _resolve_gguf_path() -> Optional[str]:
    raw = os.getenv("FoveAI_CREATIVITY_GGUF_PATH", "").strip()
    if raw and os.path.isfile(raw):
        return raw
    return None

def _resolve_flux_gguf_path() -> Optional[str]:
    raw = os.getenv("FoveAI_CREATIVITY_FLUX_GGUF_PATH", "").strip()
    if raw and os.path.isfile(raw):
        return raw
    return None

def _load_gguf_pipe():
    """Load a StableDiffusion GGUF (e.g. sdxl-turbo-GGUF) via diffusers.from_single_file if available."""
    p = _resolve_gguf_path()
    if not p:
        raise HTTPException(
            status_code=503,
            detail=(
                "GGUF mode requires FoveAI_CREATIVITY_GGUF_PATH pointing at a .gguf weights file. "
                "Download from Hugging Face (e.g. OlegSkutte/sdxl-turbo-GGUF) and set the env var."
            ),
        )
    if StableDiffusionPipeline is None:
        raise HTTPException(
            status_code=503,
            detail="diffusers is unavailable — cannot load GGUF pipeline.",
        )
    logger.info("Loading GGUF single-file from %s (device=%s)", p, _DEVICE)
    pipe = StableDiffusionPipeline.from_single_file(
        p,
        **_diffusers_dtype_kwargs(StableDiffusionPipeline.from_single_file),
    ).to(_DEVICE)
    if _DEVICE == "cpu":
        logger.warning("GGUF pipeline running on CPU (no CUDA). Performance will be slow.")
    return pipe

def _load_flux_gguf_pipe():
    """Load a Flux 2 GGUF single-file quantized model via diffusers.from_single_file if available."""
    p = _resolve_flux_gguf_path()
    if not p:
        raise HTTPException(
            status_code=503,
            detail=(
                "flux_gguf mode requires FoveAI_CREATIVITY_FLUX_GGUF_PATH pointing at a .gguf weights file. "
                "Download from Hugging Face (e.g. alb3530/Flux.2-dev-FALAI-Turbo-Merged-GGUF) and set the env var."
            ),
        )
    if StableDiffusionPipeline is None:
        raise HTTPException(
            status_code=503,
            detail="diffusers is unavailable — cannot load Flux GGUF pipeline.",
        )
    logger.info("Loading Flux GGUF single-file from %s (device=%s)", p, _DEVICE)
    pipe = StableDiffusionPipeline.from_single_file(
        p,
        **_diffusers_dtype_kwargs(StableDiffusionPipeline.from_single_file),
    ).to(_DEVICE)
    if _DEVICE == "cpu":
        logger.warning("Flux GGUF pipeline running on CPU (no CUDA). Performance will be slow.")
    return pipe

@app.get("/health")

@app.get("/api/health")

async def health() -> dict[str, Any]:

    """Liveness + where we expect weights (helps Web UI / compose debugging)."""

    out: dict[str, Any] = {

        "status": "ok",

        "service": "foveai_creativity",

        "device": _DEVICE,

        "cuda_available": torch.cuda.is_available(),

    }

    # Add model readiness status (without loading weights)
    out["sd14_onnx_ready"] = _resolve_sd14_onnx_dir() is not None
    out["sdxl_turbo_onnx_ready"] = os.path.isfile(os.path.join(SDXL_TURBO_TRT_DIR, "model_index.json"))
    out["gguf_ready"] = _resolve_gguf_path() is not None
    out["flux_gguf_ready"] = _resolve_flux_gguf_path() is not None
    out["sd15_weights_ok"] = os.path.isdir(V15_PATH) or bool(SD15_MODEL_ID) or (os.path.isfile(SD15_SINGLE_FILE) if SD15_SINGLE_FILE else False)
    out["sd15_diffusers_path_exists"] = os.path.isdir(V15_PATH)
    out["sd15_diffusers_path"] = V15_PATH if os.path.isdir(V15_PATH) else None
    out["controlnets_available"] = len(_merged_controlnets())
    out["upscalers_available"] = len(_merged_upscalers())

    return out


@app.post("/api/preheat")

async def preheat_creative():
    """
    Pre-heat the creative service for user interaction.
    This prepares the service for quick response without loading heavy weights.
    Called when user opens the creative tab or shows interest in image generation.
    """
    logger.info("Pre-heat request received — preparing creative service for interaction")
    
    # Validate catalog and paths (fast operations)
    _ = _merged_controlnets()
    _ = _merged_upscalers()
    _ = _load_catalog()
    
    # Check SD1.5 source availability (fast check, no loading)
    try:
        kind, source = _resolve_sd15_source()
        sd15_status = f"SD1.5 ready: {kind}={source}"
    except FileNotFoundError as e:
        sd15_status = f"SD1.5 not ready: {e}"
    
    # Pre-validate environment
    env_status = {
        "imagen_root": IMAGEN_ROOT,
        "imagen_root_exists": os.path.isdir(IMAGEN_ROOT),
        "catalog_path": _catalog_path(),
        "catalog_exists": os.path.isfile(_catalog_path()),
        "sd15_status": sd15_status,
        "spandrel_available": False,
    }
    
    try:
        import spandrel  # noqa: F401
        env_status["spandrel_available"] = True
    except ImportError:
        pass
    
    logger.info("Pre-heat complete: %s", env_status)
    
    return {
        "status": "preheated",
        "message": "Creative service ready for user requests. Weights will load on first generation request.",
        "environment": env_status,
        "available_modes": [
            {"id": "turbo", "name": "SD1.5 Turbo", "ready": env_status["sd15_status"].startswith("SD1.5 ready")},
            {"id": "sd14_onnx", "name": "SD1.4 ONNX", "ready": _resolve_sd14_onnx_dir() is not None},
            {"id": "sdxl_turbo_onnx", "name": "SDXL Turbo ONNX", "ready": os.path.isfile(os.path.join(SDXL_TURBO_TRT_DIR, "model_index.json"))},
            {"id": "gguf", "name": "GGUF", "ready": _resolve_gguf_path() is not None},
            {"id": "flux_gguf", "name": "Flux GGUF", "ready": _resolve_flux_gguf_path() is not None},
            {"id": "control", "name": "ControlNet", "ready": env_status["sd15_status"].startswith("SD1.5 ready") and len(_merged_controlnets()) > 0},
            {"id": "enhance", "name": "Enhance/Upscale", "ready": env_status["spandrel_available"]},
        ],
    }


@app.post("/api/state/switch")

async def switch_creative_state(state: str):
    """
    Signal the service manager to switch to a specific state.
    This allows the webapp to trigger state changes when user navigates.
    Valid states: AWAKE, CREATIVE, LIVE, CODE, SLEEP
    """
    valid_states = {"AWAKE", "CREATIVE", "LIVE", "CODE", "SLEEP"}
    state = state.upper()
    
    if state not in valid_states:
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of: {valid_states}")
    
    # Write command file for the service to pick up
    cmd_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".logs", "foveai_service_cmd.txt")
    try:
        with open(cmd_path, "w", encoding="utf-8") as f:
            f.write(state)
        logger.info("State switch command written: %s", state)
        return {"status": "switching", "state": state, "message": f"Switching to {state} state"}
    except Exception as e:
        logger.error("Failed to write state switch command: %s", e)
        raise HTTPException(status_code=500, detail=f"Could not signal state switch: {e}")



@app.on_event("startup")

async def startup_event():

    logger.info("Creativity Faculty: Sanctuary initialized.")

    logger.info(

        "Imagen catalog: %s (%s controlnets, %s upscalers)",

        _catalog_path(),

        len(_merged_controlnets()),

        len(_merged_upscalers()),

    )

    if not _local_imagen_scan_disabled():

        dc, du = _local_discoveries()

        logger.info("Imagen local scan: +%s controlnets, +%s upscaler weights", len(dc), len(du))

    mr = _models_root_from_imagen_tree()

    if mr:

        logger.info("Inferred models root from IMAGEN path: %s", mr)

    logger.info("FoveAI_CREATIVITY_IMAGEN_ROOT=%s (SD1.5 base=%s)", IMAGEN_ROOT, V15_PATH)

    try:

        k, s = _resolve_sd15_source()

        logger.info("SD1.5 ready: kind=%s source=%s", k, s)

    except FileNotFoundError as e:

        logger.error("SD1.5 not available: %s", e)

    # Model availability summary (only report what IS available, not what's missing)
    available_modes = []
    
    # SD1.5 status
    try:
        k, s = _resolve_sd15_source()
        logger.info("SD1.5 ready: kind=%s source=%s", k, s)
        available_modes.append("SD1.5 Turbo")
    except FileNotFoundError as e:
        logger.error("SD1.5 not available: %s", e)
    
    # SDXL Turbo ONNX (Optimum)
    if os.path.isfile(os.path.join(SDXL_TURBO_TRT_DIR, "model_index.json")):
        logger.info("SDXL Turbo ONNX available at %s", SDXL_TURBO_TRT_DIR)
        available_modes.append("SDXL Turbo ONNX")
    
    # GGUF
    gguf = _resolve_gguf_path()
    if gguf:
        logger.info("GGUF model available: %s", os.path.basename(gguf))
        available_modes.append("GGUF")
    
    # Flux GGUF
    flux_gguf = _resolve_flux_gguf_path()
    if flux_gguf:
        logger.info("Flux GGUF model available: %s", os.path.basename(flux_gguf))
        available_modes.append("Flux GGUF")
    
    # ControlNet
    cn_count = len(_merged_controlnets())
    if cn_count > 0:
        available_modes.append(f"ControlNet ({cn_count})")
    
    # Upscaler
    up_count = len(_merged_upscalers())
    if up_count > 0:
        available_modes.append(f"Upscaler ({up_count})")
    
    logger.info("Available modes: %s", ", ".join(available_modes) if available_modes else "None (SD1.5 required for base generation)")

def get_safe_image(b64_str: str) -> Optional[Image.Image]:

    if not b64_str:

        return None

    try:

        data = base64.b64decode(b64_str)

        return Image.open(io.BytesIO(data)).convert("RGB")

    except Exception as e:

        logger.error(f"Image Decode Error: {e}")

        return None

def _dream_init_image(pil_img: Image.Image, width: int, height: int) -> Image.Image:

    """SD1.5-friendly init for img2img dreams."""

    return pil_img.convert("RGB").resize((width, height), Image.LANCZOS)


def _canny_edges_pil(pil_img: Image.Image, low: int, high: int, width: int, height: int) -> Image.Image:

    """Sobel + hysteresis-style edges for ControlNet Canny (no OpenCV dependency)."""

    import numpy as np

    from scipy import ndimage

    rgb = pil_img.convert("RGB").resize((width, height), Image.LANCZOS)

    arr = np.asarray(rgb, dtype=np.float32) / 255.0

    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    gx = ndimage.sobel(gray, axis=1)

    gy = ndimage.sobel(gray, axis=0)

    mag = np.hypot(gx, gy)

    mag = mag / (float(mag.max()) + 1e-8)

    lo = max(0, min(255, int(low))) / 255.0

    hi = max(0, min(255, int(high))) / 255.0

    hi = max(hi, lo + 1e-4)

    strong = mag >= hi

    weak = (mag >= lo) & ~strong

    mask = strong.copy()

    for _ in range(2):

        dil = ndimage.binary_dilation(mask)

        mask = mask | (weak & dil)

    e = (mask.astype(np.float32) * 255.0).astype(np.uint8)

    stack = np.stack([e, e, e], axis=-1)

    return Image.fromarray(stack, mode="RGB")


def _prepare_control_image_for_controlnet(

    pil_img: Image.Image,

    preprocess: str,

    low: int,

    high: int,

    width: int,

    height: int,

) -> Image.Image:

    p = (preprocess or "canny").lower().strip()

    if p == "none":

        return pil_img.convert("RGB").resize((width, height), Image.LANCZOS)

    return _canny_edges_pil(pil_img, low, high, width, height)


@app.get("/api/dream/catalog")

async def dream_catalog() -> Dict[str, Any]:

    """Lists ControlNet / upscaler entries from foveai_imagen_catalog.json plus optional InvokeAI CSV merge."""

    cat = _load_catalog()

    cns: List[Dict[str, Any]] = []

    for c in _merged_controlnets():

        p = _resolve_catalog_item_path(c)

        row = dict(c)

        row["resolved_path"] = p

        row["exists"] = bool(p and os.path.isdir(p))

        row["sd15_compatible"] = _controlnet_sd15_compatible(row)

        cns.append(row)

    ups: List[Dict[str, Any]] = []

    for u in _merged_upscalers():

        row = dict(u)

        be = (row.get("backend") or "").lower()

        if be == "lanczos":

            row["resolved_path"] = ""

            row["exists"] = True

        else:

            p = _resolve_catalog_item_path(row)

            row["resolved_path"] = p

            row["exists"] = bool(p and os.path.isfile(p))

        row["enhance_compatible"] = _upscaler_enhance_compatible(row)

        row["compatible_modes"] = ["enhance"] if row["enhance_compatible"] else []

        ups.append(row)

    presets: List[Dict[str, Any]] = [

        {"label": "512 × 512 (square)", "width": 512, "height": 512},

        {"label": "512 × 768 (portrait)", "width": 512, "height": 768},

        {"label": "768 × 512 (landscape)", "width": 768, "height": 512},

        {"label": "640 × 640", "width": 640, "height": 640},

        {"label": "768 × 768", "width": 768, "height": 768},

        {"label": "896 × 512 (wide)", "width": 896, "height": 512},

    ]

    return {

        "version": cat.get("version", 1),

        "catalog_path": _catalog_path(),

        "catalog_sd15_note": (cat.get("sd15_note") or "").strip(),

        "catalog_local_scan_note": (cat.get("local_scan_note") or "").strip(),

        "imagen_root": IMAGEN_ROOT,

        "invokeai_models_dir": cat.get("invokeai_models_dir") or "",

        "invokeai_models_root": effective_invoke_models_root(),

        "invokeai_models_root_env": os.getenv("FoveAI_INVOKEAI_MODELS_ROOT", "").strip(),

        "invokeai_models_csv": os.getenv("FoveAI_INVOKEAI_MODELS_CSV", "").strip(),

        "invokeai_integration": {

            "models_root_resolved": effective_invoke_models_root(),

            "controlnet_csv_merge_enabled": merge_invoke_controlnets_enabled(),

            "inventory_csv_default": os.path.join(

                os.path.abspath(os.path.join(CREATIVE_DIR, "..", "..", "..")),

                "tools",

                "invokeai_models_inventory.csv",

            ),

            "merged_from_invoke_csv": {

                "controlnets": sum(

                    1 for c in _merged_controlnets() if c.get("source") == "invokeai_inventory_csv"

                ),

                "upscalers": sum(

                    1 for u in _merged_upscalers() if u.get("source") == "invokeai_inventory_csv"

                ),

            },

            "hint": (

                "Bind your real InvokeAI models folder to /invokeai/models (set FoveAI_INVOKEAI_MODELS_HOST in .env). "

                "Only rows whose weights exist on that mount are listed; path_absolute pointing at other drives is ignored inside Docker. "

                "Disable ControlNet CSV merge with FoveAI_INVOKEAI_MERGE_CONTROLNETS=0."

            ),

        },

        "taxonomy_note": "Metadata fields base/type mirror InvokeAI BaseModelType and ModelType for your own bookkeeping. Spandrel upscalers may be merged from tools/invokeai_models_inventory.csv when present.",

        "pipeline_sd_base": "sd15",

        "image_size_presets": presets,

        "enhance_options": {

            "target_scales": [

                {"label": "Native (keep model output size)", "value": 0},

                {"label": "1.25× vs preprocessed input", "value": 1.25},

                {"label": "1.5×", "value": 1.5},

                {"label": "2×", "value": 2.0},

                {"label": "3×", "value": 3.0},

                {"label": "4×", "value": 4.0},

                {"label": "8×", "value": 8.0},

            ],

            "aspect_ratios": ["", "1:1", "16:9", "4:3", "3:4", "9:16", "21:9"],

            "notes": "Chain 4×/8× Spandrel models then set target scale to 2× to cap final size. Pre-crop and long-edge resize run before the chain.",

        },

        "sd15_setup": {

            "local_diffusers_dir": V15_PATH,

            "local_diffusers_present": os.path.isdir(V15_PATH),

            "default_public_repo": DEFAULT_SD15_HUB_REPO,

            "hub_auto_download_disabled": _sd15_hub_fallback_disabled(),

            "hint": (

                "Dream turbo/control modes need SD1.5 weights. If nothing is under imagen_root, "

                "the service uses the default Hugging Face repo (see default_public_repo). "

                "Offline: set FoveAI_CREATIVITY_DISABLE_SD15_HUB_FALLBACK=1 and install local weights, "

                "or set FoveAI_CREATIVITY_SD15_MODEL_ID to a local path or HF repo id."

            ),

        },

        "local_model_scan": {

            "enabled": not _local_imagen_scan_disabled(),

            "models_root_inferred": _models_root_from_imagen_tree(),

            "discovered_controlnets": len(_local_discoveries()[0]),

            "discovered_spandrel_files": len(_local_discoveries()[1]),

            "hint": (

                "Typical Docker layout: host D:\\Lumax\\models mounts as /app/models; keep Diffusers trees under "

                "backend/Creativity/Imagen (FoveAI_CREATIVITY_IMAGEN_ROOT). Optional: Imagen/upscalers/*.safetensors for Spandrel; "

                "Creativity/controlnets/<folder>/ or extra ControlNet folders directly under Imagen. "

                "Disable scanning with FoveAI_CREATIVITY_DISABLE_LOCAL_SCAN=1."

            ),

        },

        "sd14_onnx_ready": _resolve_sd14_onnx_dir() is not None,

        "sd14_onnx_dir": SD14_ONNX_DIR,

        "sd14_onnx_resolved": _resolve_sd14_onnx_dir(),

        "controlnets": cns,

        "upscalers": ups,

    }


class DisplayUpscaleRequest(BaseModel):

    model_config = ConfigDict(protected_namespaces=())

    image_b64: str

    # After Spandrel: clamp longest side (0 = use env FoveAI_DISPLAY_UPSCALE_MAX_LONG_EDGE only).
    max_long_edge: int = 0


@app.post("/api/upscale/display")

async def display_upscale_image(req: DisplayUpscaleRequest):

    """Run the same optional Spandrel display pass as dream output (fast 2×/4× models under Imagen/upscalers)."""

    ck_disp = _display_upscale_spandrel_path()

    if not ck_disp or not os.path.isfile(ck_disp):

        raise HTTPException(

            status_code=503,

            detail=(

                "Display Spandrel is not configured or weights are missing. "

                "Set FoveAI_DISPLAY_UPSCALE_SPANDREL_PATH to a Spandrel-compatible .pth / .safetensors "

                "(e.g. under Imagen/upscalers)."

            ),

        )

    raw = (req.image_b64 or "").strip()

    if not raw:

        raise HTTPException(status_code=400, detail="image_b64 is required")

    pil = get_safe_image(raw)

    if pil is None:

        raise HTTPException(status_code=400, detail="Could not decode image_b64")

    cap = int(req.max_long_edge or 0)

    if cap < 0:

        cap = 0

    if cap > 8192:

        cap = 8192

    out = _apply_display_spandrel_if_configured(pil, max_long_edge_override=cap)

    buffered = io.BytesIO()

    out.save(buffered, format="PNG")

    return JSONResponse(

        {

            "status": "success",

            "image_b64": base64.b64encode(buffered.getvalue()).decode("utf-8"),

        }

    )


@app.post("/api/dream")

async def generate_dream_image(req: DreamRequest):

    global DREAM_PIPE, IMG2IMG_PIPE, ENHANCE_PIPE, ORT_SD14_PIPE, ORT_SDXL_PIPE, GGUF_PIPE, FLUX_GGUF_PIPE, _CONTROL_BUNDLE

    try:

        output = None

        mt = (req.model_type or "turbo").lower()

        dw, dh = _clamp_dream_dimensions(req.width, req.height)

        # 1. CONTROLNET (Structural Integrity)

        if mt == "control":

            kind, src = _resolve_sd15_source()

            if kind == "single_file":

                raise HTTPException(

                    status_code=500,

                    detail="ControlNet + from_single_file is not supported; use a Diffusers SD1.5 folder or FoveAI_CREATIVITY_SD15_MODEL_ID.",

                )

            cn_path = _resolve_controlnet_weights_path_for_request(req)

            if not os.path.isdir(cn_path):

                raise HTTPException(

                    status_code=400,

                    detail=f"ControlNet weights not found at {cn_path}. Check foveai_imagen_catalog.json or FoveAI_CREATIVITY_IMAGEN_ROOT.",

                )

            control_pipe = _get_control_pipeline(src, cn_path)

            raw_in = get_safe_image((req.control_image_b64 or req.reference_image_b64 or "").strip())

            if raw_in is None:

                raise HTTPException(status_code=400, detail="control mode requires an uploaded image (control_image_b64).")

            eff_pre = _effective_control_preprocess(req)

            control_image = _prepare_control_image_for_controlnet(

                raw_in,

                eff_pre,

                int(req.canny_low),

                int(req.canny_high),

                dw,

                dh,

            )

            generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None

            gs = float(req.guidance_scale)

            ccs = float(req.controlnet_conditioning_scale)

            output = control_pipe(

                prompt=req.prompt,

                image=control_image,

                num_inference_steps=req.num_inference_steps,

                generator=generator,

                guidance_scale=gs,

                controlnet_conditioning_scale=ccs,

                width=dw,

                height=dh,

            )

        # 2. ENHANCER — chain upscalers; optional crop/resize; cap final size vs preprocessed input

        elif mt == "enhance":

            init_image = get_safe_image((req.control_image_b64 or req.reference_image_b64 or "").strip())

            if init_image is None:

                raise HTTPException(status_code=400, detail="Base image required (upload for enhance mode).")

            ar = _parse_aspect_ratio(getattr(req, "enhance_pre_crop_aspect", "") or "")

            if ar:

                init_image = _center_crop_to_aspect(init_image, ar[0], ar[1])

            le = int(getattr(req, "enhance_pre_resize_long_edge", 0) or 0)

            if le > 0:

                init_image = _resize_fit_long_edge(init_image, le)

            base_w, base_h = init_image.size

            chain_raw = list(getattr(req, "upscaler_chain", None) or [])

            chain_ids = [str(x).strip() for x in chain_raw if str(x).strip()]

            if not chain_ids:

                chain_ids = [(getattr(req, "upscaler_id", None) or "lanczos-x4").strip()]

            if not chain_ids or not chain_ids[0]:

                chain_ids = ["lanczos-x4"]

            ts = float(getattr(req, "enhance_target_scale", 0.0) or 0.0)

            if ts < 0:

                ts = 0.0

            if ts > 0:

                ts = min(32.0, max(0.25, ts))

            logger.info(

                "Enhance chain=%s base=%sx%s target_scale=%s",

                chain_ids,

                base_w,

                base_h,

                ts or "native",

            )

            image = init_image

            for step_uid in chain_ids:

                matched = _upscaler_entry_by_id(step_uid)

                if not matched:

                    raise HTTPException(

                        status_code=400,

                        detail=(

                            f"Unknown upscaler_id in chain: {step_uid!r}. "

                            "Matching is case-insensitive; list valid ids with GET /api/dream/catalog (upscalers)."

                        ),

                    )

                image = _run_single_upscale_step(image, matched)

            if ts > 0:

                image = _enhance_resize_to_linear_target(image, base_w, base_h, ts)

        # 3a. SD1.4 ONNX (lightweight) — txt2img only

        elif mt == "sd14_onnx":

            ref_pil = get_safe_image((req.reference_image_b64 or "").strip())

            if ref_pil is not None:

                raise HTTPException(

                    status_code=400,

                    detail="sd14_onnx mode does not support reference_image_b64 yet (txt2img only). Use model_type turbo for img2img.",

                )

            if ORT_SD14_PIPE is None:

                ORT_SD14_PIPE = _load_ort_sd14()

            generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None

            try:

                output = ORT_SD14_PIPE(

                    prompt=req.prompt,

                    num_inference_steps=req.num_inference_steps,

                    generator=generator,

                    guidance_scale=float(req.guidance_scale),

                    width=dw,

                    height=dh,

                )

            except TypeError:

                try:

                    output = ORT_SD14_PIPE(

                        prompt=req.prompt,

                        num_inference_steps=req.num_inference_steps,

                        generator=generator,

                        width=dw,

                        height=dh,

                    )

                except TypeError:

                    output = ORT_SD14_PIPE(

                        prompt=req.prompt,

                        num_inference_steps=req.num_inference_steps,

                        generator=generator,

                    )

        # 3b. SDXL TURBO ONNX — fast 512×512 with 1-4 steps (needs optimum[onnxruntime])
        elif mt == "sdxl_turbo_onnx":
            ref_pil = get_safe_image((req.reference_image_b64 or "").strip())
            if ref_pil is not None:
                raise HTTPException(
                    status_code=400,
                    detail="sdxl_turbo_onnx mode does not support reference_image_b64 yet (txt2img only).",
                )
            if ORT_SDXL_PIPE is None:
                ORT_SDXL_PIPE = _load_ort_sdxl_turbo()
            generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None
            try:
                output = ORT_SDXL_PIPE(
                    prompt=req.prompt,
                    num_inference_steps=req.num_inference_steps,
                    generator=generator,
                    guidance_scale=float(req.guidance_scale),
                    width=dw,
                    height=dh,
                )
            except TypeError:
                try:
                    output = ORT_SDXL_PIPE(
                        prompt=req.prompt,
                        num_inference_steps=req.num_inference_steps,
                        generator=generator,
                        width=dw,
                        height=dh,
                    )
                except TypeError:
                    output = ORT_SDXL_PIPE(
                        prompt=req.prompt,
                        num_inference_steps=req.num_inference_steps,
                        generator=generator,
                    )

        # 3c. GGUF — single-file quantized model (e.g. sdxl-turbo-GGUF)
        elif mt == "gguf":
            ref_pil = get_safe_image((req.reference_image_b64 or "").strip())
            if ref_pil is not None:
                raise HTTPException(
                    status_code=400,
                    detail="gguf mode does not support reference_image_b64 yet (txt2img only).",
                )
            if GGUF_PIPE is None:
                GGUF_PIPE = _load_gguf_pipe()
            generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None
            output = GGUF_PIPE(
                prompt=req.prompt,
                num_inference_steps=req.num_inference_steps,
                generator=generator,
                guidance_scale=float(req.guidance_scale),
                width=dw,
                height=dh,
            )

        # 3c-flux. Flux 2 GGUF — single-file quantized model (e.g. flux-2-dev-FALAI-Turbo-Merged-GGUF)
        elif mt == "flux_gguf":
            ref_pil = get_safe_image((req.reference_image_b64 or "").strip())
            if ref_pil is not None:
                raise HTTPException(
                    status_code=400,
                    detail="flux_gguf mode does not support reference_image_b64 yet (txt2img only).",
                )
            if FLUX_GGUF_PIPE is None:
                FLUX_GGUF_PIPE = _load_flux_gguf_pipe()
            generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None
            output = FLUX_GGUF_PIPE(
                prompt=req.prompt,
                num_inference_steps=req.num_inference_steps,
                generator=generator,
                guidance_scale=float(req.guidance_scale),
                width=dw,
                height=dh,
            )

        # 3d. STANDARD (Turbo/Dream) with Reference Picture Support
        # reference_mode: "none", "style" (img2img), "structure" (ControlNet), "both"
        else:
            ref_pil = get_safe_image((req.reference_image_b64 or "").strip())
            ref_mode = (getattr(req, "reference_mode", "none") or "none").lower()
            ref_strength = float(getattr(req, "reference_strength", 0.5) or 0.5)
            struct_type = (getattr(req, "structure_type", "canny") or "canny").lower()
            
            # Handle reference picture modes
            if ref_pil is not None and ref_mode != "none":
                logger.info("Reference picture: mode=%s strength=%.2f structure=%s", ref_mode, ref_strength, struct_type)
                
                # Structure transfer using ControlNet
                if ref_mode in ("structure", "both"):
                    kind, src = _resolve_sd15_source()
                    if kind == "single_file":
                        raise HTTPException(
                            status_code=500,
                            detail="Structure transfer + from_single_file is not supported; use a Diffusers SD1.5 folder.",
                        )
                    
                    cn_path = CONTROLNET_CANNY_PATH
                    if not os.path.isdir(cn_path):
                        raise HTTPException(
                            status_code=400,
                            detail=f"ControlNet weights not found at {cn_path}.",
                        )
                    
                    control_pipe = _get_control_pipeline(src, cn_path)
                    
                    # Build structure control image
                    if struct_type == "depth":
                        # For depth, just use the image as-is (would need MiDaS for real depth)
                        control_image = _dream_init_image(ref_pil, dw, dh)
                    else:
                        # Canny edges
                        control_image = _canny_edges_pil(ref_pil, int(req.canny_low), int(req.canny_high), dw, dh)
                    
                    generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None
                    
                    # Scale controlnet strength by reference_strength
                    ccs = float(req.controlnet_conditioning_scale) * ref_strength
                    ccs = max(0.0, min(2.0, ccs))
                    
                    output = control_pipe(
                        prompt=req.prompt,
                        image=control_image,
                        num_inference_steps=req.num_inference_steps,
                        generator=generator,
                        guidance_scale=float(req.guidance_scale),
                        controlnet_conditioning_scale=ccs,
                        width=dw,
                        height=dh,
                    )
                    
                    # If "both" mode, also apply style via img2img after structure
                    if ref_mode == "both":
                        # Use the structure result as init for style transfer
                        style_init = output.images[0]
                        if IMG2IMG_PIPE is None:
                            logger.info("Loading SD v1.5 img2img for style transfer...")
                            IMG2IMG_PIPE = _load_sd15_img2img()
                        
                        # Style strength controls how much to change from structure result
                        style_strength = float(req.strength) * (1.0 - ref_strength * 0.5)
                        style_strength = max(0.08, min(0.92, style_strength))
                        
                        output = IMG2IMG_PIPE(
                            prompt=req.prompt,
                            image=style_init,
                            strength=style_strength,
                            num_inference_steps=req.num_inference_steps,
                            generator=generator,
                            guidance_scale=float(req.guidance_scale),
                        )
                
                # Style transfer only (img2img)
                elif ref_mode == "style":
                    if IMG2IMG_PIPE is None:
                        logger.info("Loading SD v1.5 img2img for style transfer...")
                        IMG2IMG_PIPE = _load_sd15_img2img()
                    
                    init_img = _dream_init_image(ref_pil, dw, dh)
                    
                    # Map reference_strength to img2img strength (inverse: higher = more style influence = lower strength)
                    strength = 1.0 - (ref_strength * 0.8)  # 0.2 to 1.0
                    strength = float(req.strength) * strength
                    strength = max(0.08, min(0.92, strength))
                    
                    generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None
                    
                    output = IMG2IMG_PIPE(
                        prompt=req.prompt,
                        image=init_img,
                        strength=strength,
                        num_inference_steps=req.num_inference_steps,
                        generator=generator,
                        guidance_scale=float(req.guidance_scale),
                    )
            
            # No reference picture - plain txt2img
            elif ref_pil is not None:
                # Legacy behavior: reference_image_b64 without reference_mode = img2img
                if IMG2IMG_PIPE is None:
                    logger.info("Loading SD v1.5 img2img for reference-guided dreams...")
                    IMG2IMG_PIPE = _load_sd15_img2img()

                init_img = _dream_init_image(ref_pil, dw, dh)

                strength = float(req.strength)
                strength = max(0.08, min(0.92, strength))

                generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None

                output = IMG2IMG_PIPE(
                    prompt=req.prompt,
                    image=init_img,
                    strength=strength,
                    num_inference_steps=req.num_inference_steps,
                    generator=generator,
                    guidance_scale=float(req.guidance_scale),
                )

            else:
                if DREAM_PIPE is None:
                    logger.info("Loading Standard v1.5 txt2img...")
                    DREAM_PIPE = _load_sd15_txt2img()

                generator = torch.Generator(_DEVICE).manual_seed(req.seed) if req.seed != -1 else None

                output = DREAM_PIPE(
                    prompt=req.prompt,
                    num_inference_steps=req.num_inference_steps,
                    generator=generator,
                    guidance_scale=float(req.guidance_scale),
                    width=dw,
                    height=dh,
                )

        # ENHANCE returns local `image` not `output.images`

        if mt == "enhance":

            image = _apply_display_spandrel_if_configured(image)

            buffered = io.BytesIO()

            image.save(buffered, format="PNG")

            return JSONResponse(

                {

                    "status": "success",

                    "image_b64": base64.b64encode(buffered.getvalue()).decode("utf-8"),

                }

            )

        if output is None or not hasattr(output, "images") or len(output.images) == 0:

            raise Exception("Pipeline failed to produce an image. Check hardware/logs.")

        image = output.images[0]

        image = _apply_display_spandrel_if_configured(image)

        buffered = io.BytesIO()

        image.save(buffered, format="PNG")

        return JSONResponse(

            {

                "status": "success",

                "image_b64": base64.b64encode(buffered.getvalue()).decode("utf-8"),

            }

        )

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Creativity Breach: {e}")

        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

if __name__ == "__main__":

    import uvicorn
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from server_config import ServerConfig as cfg
        _host = cfg.BIND_HOST
        _port = cfg.CREATIVE_PORT
    except ImportError:
        _host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")
        _port = int(os.getenv("FOVEAI_CREATIVE_PORT", "8003"))

    uvicorn.run(app, host=_host, port=_port)
