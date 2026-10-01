"""
Shared daily cap for paid OpenAI-compatible GenAI completions (Gemini / OpenAI / EXTRA slots).

Used by cloud_repertoire (soul + foveai_ops sentry). Ollama/local GGUF does not consume this budget.

Env:
  FoveAI_CLOUD_GENAI_DAILY_MAX — max successful cloud /chat/completions per UTC day (0 = unlimited).
  FoveAI_CLOUD_GENAI_USAGE_PATH — JSON counter file (default: next to this file under ../../preflight/outbox/).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("genai_daily_budget")


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv("FoveAI_CLOUD_GENAI_DAILY_MAX", "0") or "0"))
    except ValueError:
        return 0


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def usage_path() -> str:
    raw = os.getenv("FoveAI_CLOUD_GENAI_USAGE_PATH", "").strip()
    if raw:
        return os.path.normpath(os.path.expandvars(raw))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(here, "..", "..", "preflight", "outbox", "genai_daily_usage.json")
    )


def _read_state() -> dict[str, Any]:
    path = usage_path()
    if not os.path.isfile(path):
        return {"date": "", "count": 0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return {"date": "", "count": 0}
        return d
    except Exception as e:
        logger.warning("genai_daily_budget: unreadable %s (%s)", path, e)
        return {"date": "", "count": 0}


def _write_state(data: dict[str, Any]) -> None:
    path = usage_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def allows() -> bool:
    cap = daily_cap()
    if cap <= 0:
        return True
    today = _utc_today()
    st = _read_state()
    if st.get("date") != today:
        return True
    return int(st.get("count", 0)) < cap


def record_success(n: int = 1) -> None:
    cap = daily_cap()
    if cap <= 0 or n <= 0:
        return
    today = _utc_today()
    st = _read_state()
    if st.get("date") != today:
        st = {"date": today, "count": 0}
    st["count"] = int(st.get("count", 0)) + n
    try:
        _write_state(st)
    except Exception as e:
        logger.error("genai_daily_budget: could not write %s: %s", usage_path(), e)


def usage_snapshot() -> dict[str, Any]:
    cap = daily_cap()
    today = _utc_today()
    st = _read_state()
    used = 0 if st.get("date") != today else int(st.get("count", 0))
    remaining: int | None
    if cap <= 0:
        remaining = None
    else:
        remaining = max(0, cap - used)
    return {
        "daily_cap": cap,
        "used_today_utc": used,
        "remaining": remaining,
        "utc_date": today,
        "usage_file": usage_path(),
    }
