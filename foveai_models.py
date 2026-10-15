#!/usr/bin/env python3
"""
foveai_models.py — single source of truth for FoveAI model selection.

Replaces two divergent PERSONA_MODELS dicts:
  - FoveAI_Taskbar_Linux.py  (keys: gemma_e2b_xrlf, …)
  - FoveAI_Console.py         (keys: gemma_e2b,      …)
which disagreed on both contents and key naming, so a model added to one was
invisible in the other.

Two engines, because llama.cpp decides this:

  engine="xrlf"          in-process via run_xrlf.py → llama-cpp-python.
                         Cannot express speculative decoding: common/
                         speculative.cpp is statically linked into the
                         llama-server binary and is NOT exported by
                         libllama.so, so the Python binding has no eagle3 /
                         dflash / draft-simple API.

  engine="llama-server"  external llama-server owns the weights. Required for
                         Eagle3 + a vision projector. VRAM is exclusive —
                         the XRLF runtime must be unloaded first.

Bundling rule: weights and the vision projector stay in the bundle because
llama-server consumes the projector at load (coupled to inference). Audio
bridges do not — they are services (foveai-tts :8411, foveai-stt :8411).
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

FOVEAI_DIR = "/home/lumba/FoveAI"

LLAMA_SERVER = os.path.join(
    FOVEAI_DIR, "Tools", "llama-b11053-cuda", "llama-b11053", "llama-server"
)
if not os.path.exists(LLAMA_SERVER):
    LLAMA_SERVER = "llama-server"


def _venv_python() -> str:
    p = os.path.join(FOVEAI_DIR, ".venv", "bin", "python")
    if not os.path.exists(p):
        p = os.path.join(FOVEAI_DIR, "venv", "bin", "python")
    return p if os.path.exists(p) else "python3"


PERSONA_MODELS: dict[str, dict[str, Any]] = {
    "qwen_9b_moq32_eagle": {
        "name": "Qwen3.5 9B MoQ 3.2 (Eagle3 + Vision)",
        "id": "qwen3.5-9b-moq32-eagle",
        "xrlf_path": "/xrl_build/qwen3.5-9b-multimodal-v3.2.xrlf.cache/core.gguf",
        "mmproj": "/xrl_build/qwen3.5-9b-multimodal-v3.2.xrlf.cache/mmproj.gguf",
        "draft": "models/drafts/Qwen3.5-9B-Eagle3-ShareGPT-Q5_K_M.gguf",
        "spec_type": "draft-eagle3",
        "spec_p_min": 0.75,
        "engine": "llama-server",
        "port": 8408,
        "n_gpu_layers": 99,
        "n_gpu_draft_layers": 99,
        "n_ctx": 2048,
        "cache_type": "q4_0",
        "size_gb": 4.7,
        "total_layers": 40,
        "multimodal": True,
        "is_xrlf": False,
        "stt_native": False,
        "detail": "9B MoQ 3.2 via llama-server: Eagle3 speculative decoding (90.5% "
        "acceptance) + vision projector. Measured 95.8 tok/s vs 11.9 baseline. "
        "Exclusive VRAM — unloads the XRLF runtime. Speech stays on :8411/:8409.",
    },
    "gemma_e2b_xrlf": {
        "name": "Gemma 4 E2B MTP (Default Persona)",
        "id": "gemma-4-e2b-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf",
        "size_gb": 3.3,
        "total_layers": 30,
        "multimodal": True,
        "is_xrlf": True,
        "stt_native": True,
        "detail": "Default Persona: 2B XRLF bundle, native vision+audio, embedded MTP draft.",
    },
    "gemma_12b_xrlf": {
        "name": "Gemma 4 12B MTP (Heavy)",
        "id": "gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "xrlf_path": "xrl_encoded/gemma-4-12b-mtp-xrlf-3.0.xrlf",
        "size_gb": 5.1,
        "total_layers": 42,
        "multimodal": True,
        "is_xrlf": True,
        "stt_native": True,
        "detail": "Heavy 12B. 5.1GB weights exceed usable VRAM on an 8GB card "
        "(~5.0GiB after the 1.8GB reserve) — clamped to hybrid, not full offload.",
    },
    "qwen_4b_xrlf": {
        "name": "Qwen 3.5 4B MTP (Coder)",
        "id": "qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/qwen3.5-4b-mtp-multimodal-v1.0.xrlf",
        "size_gb": 2.9,
        "total_layers": 36,
        "multimodal": True,
        "is_xrlf": True,
        "stt_native": False,
        "detail": "4B Qwen MTP XRLF coder. No mmproj section present despite a "
        "vision=True flag — vision claim is unbacked in this bundle.",
    },
    "smolvlm2_500m_xrlf": {
        "name": "SmolVLM2 500M (Vision)",
        "id": "smolvlm2-500m-multimodal-v1.0.xrlf",
        "xrlf_path": "xrl_encoded/smolvlm2-500m-multimodal-v1.0.xrlf",
        "size_gb": 0.5,
        "total_layers": 24,
        "multimodal": True,
        "is_xrlf": True,
        "stt_native": False,
        "detail": "500M vision+video. Cheapest resident — drone/idle mode candidate.",
    },
}

# Mode-aware policy. VRAM is exclusive (one resident model at a time — the 8GB
# card cannot hold two), so a mode change is unload followed by load.
# unload_models() already kills run_xrlf + llama-server and clears the
# vram_guard locks, so this mapping is all the policy that is missing.
#
#   dormant   — unattended; the BOOT resident. Cheapest possible, because a
#               model resident at boot holds VRAM hostage from every other app
#               for as long as it is up. Measured: 9B+Eagle3+mmproj takes
#               4716 MiB of 7.99 GiB, leaving ~400 MiB for browser/XR/desktop.
#   active    — on demand, when the user or Jen initiates an interactive
#               session. The flagship, loaded for the session and released
#               afterwards. Never resident by default.
#   dreaming  — idle background cognition. Not yet a mode in the codebase —
#               .env declares FOVEAI_MODEL_DORMANT_ID and FOVEAI_MODEL_SWAP_*
#               but no code reads them. Provisional mapping.
MODE_DEFAULTS: dict[str, str] = {
    "dormant": "smolvlm2_500m_xrlf",
    "active": "qwen_9b_moq32_eagle",
    "dreaming": "gemma_e2b_xrlf",
}

# Boot resident. Deliberately NOT the 9B: at boot there is no interactive
# session, and holding 4.7GiB for an unused flagship starves everything else.
DEFAULT_MODEL_KEY = MODE_DEFAULTS["dormant"]

# Loads on demand; must be unloaded when the session ends.
ESCALATION_KEY = MODE_DEFAULTS["active"]


def model_for_mode(mode: str) -> dict[str, Any]:
    key = MODE_DEFAULTS.get((mode or "").strip().lower(), DEFAULT_MODEL_KEY)
    return PERSONA_MODELS[key]


def transition(mode: str) -> tuple[str | None, str]:
    """(outgoing_key, incoming_key) for a mode change. None if already there."""
    incoming = MODE_DEFAULTS.get((mode or "").strip().lower(), DEFAULT_MODEL_KEY)
    return (None, incoming) if incoming == DEFAULT_MODEL_KEY else (DEFAULT_MODEL_KEY, incoming)


def escalate() -> tuple[str, str]:
    """(dormant → 9B) for an interactive session. Caller must release after."""
    return DEFAULT_MODEL_KEY, ESCALATION_KEY


def release() -> str:
    """Return to the cheap resident after an interactive session."""
    return DEFAULT_MODEL_KEY


def _resolve(p: str) -> str:
    """Absolute paths pass through; relatives anchor to FOVEAI_DIR."""
    return p if os.path.isabs(p) else os.path.join(FOVEAI_DIR, p)


def build_command(m: dict[str, Any]) -> list[str]:
    """Argv for the model's engine. Raises if a required artefact is missing."""
    if m.get("engine") == "llama-server":
        cmd = [LLAMA_SERVER, "-m", _resolve(m["xrlf_path"])]
        if m.get("mmproj"):
            cmd += ["--mmproj", _resolve(m["mmproj"])]
        if m.get("draft"):
            cmd += ["-md", _resolve(m["draft"]),
                    "--spec-type", m.get("spec_type", "draft-eagle3"),
                    "--spec-draft-p-min", str(m.get("spec_p_min", 0.75))]
        cmd += ["-ngl", str(m.get("n_gpu_layers", 99)),
                "-ngld", str(m.get("n_gpu_draft_layers", 99)),
                "-c", str(m.get("n_ctx", 2048)),
                "--cache-type-k", m.get("cache_type", "q4_0"),
                "--cache-type-v", m.get("cache_type", "q4_0"),
                "-fa", "on",
                "--port", str(m.get("port", 8408)),
                "-np", "1"]
        return cmd

    return [_venv_python(), os.path.join(FOVEAI_DIR, "run_xrlf.py"),
            "--model", _resolve(m["xrlf_path"]),
            "--port", "8402", "--ws-port", "8403"]


def missing_artifacts(m: dict[str, Any]) -> list[str]:
    paths = [("xrlf_path", m.get("xrlf_path", ""))]
    if m.get("mmproj"):
        paths.append(("mmproj", m["mmproj"]))
    if m.get("draft"):
        paths.append(("draft", m["draft"]))
    return [f"{k}: {p}" for k, p in paths if p and not os.path.exists(_resolve(p))]


def launch(m: dict[str, Any], log: str | None = None) -> subprocess.Popen:
    missing = missing_artifacts(m)
    if missing:
        raise FileNotFoundError(
            f"{m.get('name')}: missing artefact(s): {', '.join(missing)}"
        )
    env = os.environ.copy()
    env["XRLF_REPO_ENABLED"] = "true"
    env["GGML_CUDA_NO_VMM"] = "1"
    stdout = open(log, "a") if log else subprocess.DEVNULL
    return subprocess.Popen(
        build_command(m),
        cwd=FOVEAI_DIR,
        env=env,
        stdout=stdout,
        stderr=subprocess.STDOUT if log else subprocess.DEVNULL,
    )


def describe(m: dict[str, Any]) -> str:
    bits = [m["name"]]
    if m.get("engine") == "llama-server":
        bits.append(f"llama-server :{m.get('port', 8408)}")
        if m.get("draft"):
            bits.append(m.get("spec_type", "draft"))
        if m.get("mmproj"):
            bits.append("vision")
    else:
        bits.append("XRLF :8402")
    if m.get("stt_native"):
        bits.append("native STT")
    return " · ".join(bits)


def catalog() -> list[dict[str, Any]]:
    """Serialisable list for any consumer (API, Dash, Multigate, tray)."""
    out = []
    for key, m in PERSONA_MODELS.items():
        out.append({
            "key": key,
            "id": m["id"],
            "name": m["name"],
            "size_gb": m["size_gb"],
            "engine": m.get("engine", "xrlf"),
            "port": m.get("port", 8402),
            "multimodal": m.get("multimodal", False),
            "stt_native": m.get("stt_native", False),
            "speculative": m.get("spec_type"),
            "default": key == DEFAULT_MODEL_KEY,
            "available": not missing_artifacts(m),
            "detail": m.get("detail", ""),
        })
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(catalog(), indent=2))