"""Ollama HTTP auth: same key works for Ollama Cloud (Bearer) and optional local server auth."""
from __future__ import annotations

import os
from typing import Dict


def ollama_api_key() -> str:
    return os.getenv("OLLAMA_API_KEY", "").strip()


def ollama_http_headers() -> Dict[str, str]:
    k = ollama_api_key()
    if not k:
        return {}
    return {"Authorization": f"Bearer {k}"}
