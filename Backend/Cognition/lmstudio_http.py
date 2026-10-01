"""LM Studio HTTP auth: API token for local LM Studio server."""

from __future__ import annotations

import os


def lmstudio_api_key() -> str:
    """Get LM Studio API token from environment."""
    return os.getenv("LMSTUDIO_API_TOKEN", "").strip()


def lmstudio_http_headers() -> dict[str, str]:
    """Return HTTP headers for LM Studio API authentication."""
    k = lmstudio_api_key()
    if not k:
        return {}
    return {"Authorization": f"Bearer {k}"}


def lmstudio_base_url() -> str:
    """Get LM Studio base URL from environment."""
    return os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1").rstrip("/")
