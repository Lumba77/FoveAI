from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

try:
    import cognee_client
except ImportError:
    cognee_client = None

logger = logging.getLogger("memory_layering")

_NOTES_KEY_PREFIX = "foveai:notes:"


def _notes_key(session_id: str) -> str:
    sid = (session_id or "default_user").strip() or "default_user"
    return f"{_NOTES_KEY_PREFIX}{sid}"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _parse_json_list(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    if not isinstance(raw, str):
        return []
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, list):
        return []
    out: list[dict[str, Any]] = []
    for item in obj:
        if isinstance(item, dict):
            out.append(item)
    return out


def _clamp_chars(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) > max_chars:
        return t[:max_chars] + "…"
    return t


def get_recent_notes(
    redis_memory: Any, session_id: str, limit: int = 8
) -> list[dict[str, Any]]:
    """Load compact note entries from Redis/local fallback through RedisMemory.get()."""
    if redis_memory is None:
        return []
    try:
        raw = redis_memory.get(_notes_key(session_id))
    except Exception as ex:
        logger.debug("notes read failed: %s", ex)
        return []
    rows = _parse_json_list(raw)
    lim = max(1, min(int(limit), 64))
    return rows[-lim:]


def format_notes_layer(notes: list[dict[str, Any]], max_chars: int = 4000) -> str:
    if not notes:
        return ""
    lines: list[str] = []
    for idx, n in enumerate(notes, start=1):
        txt = _clamp_chars(str(n.get("text", "") or ""), 500)
        if not txt:
            continue
        source = _clamp_chars(str(n.get("source", "note") or "note"), 24)
        tags_raw = n.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            for t in tags_raw[:8]:
                tt = str(t).strip()
                if tt:
                    tags.append(tt[:24])
        tag_blob = f" tags={','.join(tags)}" if tags else ""
        lines.append(f"{idx}. [{source}{tag_blob}] {txt}")
    blob = "\n".join(lines).strip()
    return _clamp_chars(blob, max_chars)


async def append_note(
    *,
    redis_memory: Any,
    vector_memory: Any,
    session_id: str,
    text: str,
    source: str = "user",
    tags: list[str] | None = None,
) -> bool:
    """Persist note in key-value store and optionally embed into long_term memory."""
    note = _clamp_chars(text, 1200)
    if not note:
        return False
    clean_tags: list[str] = []
    if isinstance(tags, list):
        for t in tags[:12]:
            tt = str(t).strip()
            if tt:
                clean_tags.append(tt[:40])

    max_items = int(os.getenv("FoveAI_NOTES_MAX_ITEMS", "64"))
    entry = {
        "ts": int(time.time()),
        "source": _clamp_chars(source, 40) or "user",
        "tags": clean_tags,
        "text": note,
    }

    if redis_memory is not None:
        try:
            existing = get_recent_notes(redis_memory, session_id, limit=max_items)
            existing.append(entry)
            if len(existing) > max_items:
                existing = existing[-max_items:]
            redis_memory.set(
                _notes_key(session_id), json.dumps(existing, ensure_ascii=False)
            )
        except Exception as ex:
            logger.warning("append_note store failed: %s", ex)

    if vector_memory is not None and _env_bool("FoveAI_NOTES_EMBED", True):
        try:
            tag_blob = f" tags={','.join(clean_tags)}" if clean_tags else ""
            marker = f"[NOTE:{entry['source']}{tag_blob}] {entry['text']}"
            await vector_memory.add_memory(
                session_id,
                marker,
                metadata={
                    "kind": "note",
                    "source": entry["source"],
                    "tags": clean_tags,
                },
                collection="long_term",
            )
        except Exception as ex:
            logger.warning("append_note embedding failed: %s", ex)
    return True


async def resolve_cognee_layer(
    *,
    manual_context: str,
    request_query: str,
    fallback_query: str,
    deep_think: bool,
    force_use: bool | None,
) -> str:
    """
    Resolve Cognee layer text.
    Order: manual context -> env context -> optional live Cognee HTTP query.
    """
    direct = (manual_context or "").strip()
    if not direct:
        direct = (os.getenv("FoveAI_COGNEE_CONTEXT", "") or "").strip()
    if direct:
        max_c = int(os.getenv("FoveAI_COGNEE_PROMPT_MAX_CHARS", "10000"))
        return _clamp_chars(direct, max_c)

    if cognee_client is None:
        return ""
    want_http = False
    if force_use is True:
        want_http = bool((os.getenv("FoveAI_COGNEE_BASE_URL", "") or "").strip())
    elif force_use is False:
        want_http = False
    else:
        want_http = cognee_client.cognee_enabled()
    if not want_http:
        return ""

    q = (request_query or "").strip() or (fallback_query or "").strip()
    if not q:
        return ""
    out = await cognee_client.cognee_search_memory_layer(q, deep_think=deep_think)
    return (out or "").strip()
