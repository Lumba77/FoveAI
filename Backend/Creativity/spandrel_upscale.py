"""Spandrel-based super-resolution for Dreamscape enhance mode (InvokeAI-compatible checkpoints)."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger("foveai_spandrel")

_SPANDREL_MODEL: tuple[str, Any] | None = None


def _maybe_register_extra_arches() -> None:
    try:
        from spandrel import MAIN_REGISTRY
        from spandrel_extra_arches import EXTRA_REGISTRY

        MAIN_REGISTRY.add(*EXTRA_REGISTRY)
    except Exception:
        pass


def _get_model(path: str) -> Any:
    global _SPANDREL_MODEL
    from spandrel import ImageModelDescriptor, ModelLoader

    if path is None or not str(path).strip():
        raise ValueError("Spandrel model path is missing or empty")
    path = os.fspath(path)

    _maybe_register_extra_arches()
    if _SPANDREL_MODEL and _SPANDREL_MODEL[0] == path:
        return _SPANDREL_MODEL[1]

    if _SPANDREL_MODEL:
        old = _SPANDREL_MODEL[1]
        try:
            old.to("cpu")
        except Exception:
            pass
        del old
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    loaded = ModelLoader().load_from_file(path)
    if not isinstance(loaded, ImageModelDescriptor):
        raise TypeError(f"Not an image Spandrel model: {path}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    loaded = loaded.eval()
    loaded.to(device)
    _SPANDREL_MODEL = (path, loaded)
    logger.info("Loaded Spandrel model %s on %s", path, device)
    return loaded


def spandrel_upscale_pil(pil_img: Image.Image, checkpoint_path: str) -> Image.Image:
    """
    Run a single forward pass (NCHW, same convention as ComfyUI ImageUpscaleWithModel).
    """
    if checkpoint_path is None or not str(checkpoint_path).strip():
        raise ValueError("Spandrel checkpoint_path is missing or empty")
    model = _get_model(checkpoint_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    rgb = pil_img.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32) / 255.0
    t = torch.from_numpy(arr).unsqueeze(0).movedim(-1, -3).to(device)

    with torch.no_grad():
        out = model(t)

    if isinstance(out, (tuple, list)):
        out = out[0]

    out = torch.clamp(out.movedim(-3, -1), min=0.0, max=1.0)
    out_cpu = out[0].detach().float().cpu().numpy()
    out_u8 = (np.clip(out_cpu, 0.0, 1.0) * 255.0).round().astype(np.uint8)
    return Image.fromarray(out_u8, mode="RGB")
