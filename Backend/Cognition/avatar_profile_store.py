"""Persisted avatar (AI vessel) identity: display name and sex/gender for prompts.

File layout (default):
  Windows: %LOCALAPPDATA%\\Lumax-lite\\avatar_profile.json
  macOS:   ~/Library/Application Support/Lumax-lite/avatar_profile.json
  Linux:   $XDG_CONFIG_HOME/foveai-lite/avatar_profile.json (else ~/.config/foveai-lite/)

Docker: default /app/user_data/avatar_profile.json — bind host dir with FoveAI_USER_DATA_BIND
(see docker-compose foveai_soul).

Override paths:
  FoveAI_AVATAR_PROFILE_PATH — full path to JSON file
  FoveAI_USER_DATA_DIR     — directory containing avatar_profile.json

Future (OS-agnostic): keep the soul as the authority and avoid host paths entirely—e.g. only
``GET/PUT /avatar_profile`` from Web/VR, plus a Docker named volume on ``/app/user_data`` or
Redis persistence—so no %LOCALAPPDATA% / XDG on the client.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from pathlib import Path
from typing import Any

logger = logging.getLogger("avatar_profile_store")

DEFAULT_FILE_NAME = "avatar_profile.json"
APP_DIR_NAME = "Lumax-lite"


def _is_container() -> bool:
    return os.path.exists("/.dockerenv") or os.getenv(
        "FoveAI_IN_CONTAINER", ""
    ).strip().lower() in (
        "1",
        "true",
        "yes",
    )


def default_user_data_dir() -> Path:
    explicit = os.getenv("FoveAI_USER_DATA_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    if _is_container():
        return Path("/app/user_data")
    system = platform.system()
    if system == "Windows":
        local = os.getenv("LOCALAPPDATA", "").strip()
        if local:
            return Path(local).expanduser() / APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    xdg = os.getenv("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "foveai-lite"


def resolved_profile_path() -> Path:
    p = os.getenv("FoveAI_AVATAR_PROFILE_PATH", "").strip()
    if p:
        return Path(p).expanduser()
    return default_user_data_dir() / DEFAULT_FILE_NAME


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as ex:
        logger.warning("Avatar profile read failed %s: %s", path, ex)
        return {}


def _sanitize_display_name(name: str) -> str:
    s = " ".join((name or "").split())
    return s[:64] if s else ""


def _sanitize_gender(g: str) -> str:
    s = " ".join((g or "").split())
    return s[:48] if s else ""


def _pick_str(file_data: dict[str, Any], key: str) -> str | None:
    if key not in file_data:
        return None
    raw = file_data.get(key)
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def load_merged_identity() -> tuple[str, str, Path, dict[str, Any]]:
    """Return (identity_name, identity_gender, path, file_dict).

    Precedence per field: non-empty value in avatar_profile.json wins if the file exists;
    otherwise FoveAI_IDENTITY_* env vars; otherwise Jen / female.
    """
    path = resolved_profile_path()
    file_data = _read_json_file(path) if path.is_file() else {}
    env_name = os.getenv("FoveAI_IDENTITY_NAME", "").strip()
    env_gender = os.getenv("FoveAI_IDENTITY_GENDER", "").strip()

    fn = _pick_str(file_data, "identity_name")
    fg = _pick_str(file_data, "identity_gender")

    if path.is_file():
        name = fn or env_name or "Jen"
        gender = fg or env_gender or "female"
    else:
        name = env_name or fn or "Jen"
        gender = env_gender or fg or "female"

    return _sanitize_display_name(name), _sanitize_gender(gender), path, file_data


def default_profile_document(
    identity_name: str, identity_gender: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "identity_name": _sanitize_display_name(identity_name),
        "identity_gender": _sanitize_gender(identity_gender),
    }


def save_profile(identity_name: str, identity_gender: str) -> Path:
    path = resolved_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = default_profile_document(identity_name, identity_gender)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)
    logger.info("Wrote avatar profile %s", path)
    return path
