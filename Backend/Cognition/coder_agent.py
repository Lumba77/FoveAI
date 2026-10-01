"""
coder_agent.py — "Jen the Coder": the sharp-editing persona.

The local XRLF models research, plan and propose; a larger OpenAI-compatible
cloud model performs precise repo work through the FoveAI tool layer
(coder_tools.py) — read/search/patch/blast-radius/lint/test/todo, every write
layered by .foveignore and snapshotted for rollback.

Configuration via environment (or .env):

    FOVEAI_CODER_BASE_URL   OpenAI-compatible endpoint exposing /chat/completions
                            (e.g. https://integrate.api.nvidia.com/v1 — NVIDIA NIM
                            free tier hosts strong coder models incl. Kimi K2;
                            also works with OpenRouter, LM Studio :1234, etc.)
    FOVEAI_CODER_API_KEY    API key for the endpoint
    FOVEAI_CODER_MODEL      e.g. moonshotai/kimi-k2-instruct  (NIM id)

If unconfigured, <self:codedit> requests degrade to proposals for review.
"""

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

FoveAI_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

MAX_FILE_CHARS = 60000
MAX_TURNS = 14  # agentic loop bound

CODER_SYSTEM = """You are "Jen the Coder", the sharp-editing persona of the FoveAI companion.
You work INSIDE the FoveAI repository through tools — never guess file contents:
read first, patch with exact verbatim search text, lint after editing.

Workflow rails:
- Plan briefly with todo_add for multi-step work; mark todo_done as you finish.
- Before editing a file, run repo_blast_radius on it so you know what imports it.
- Prefer repo_apply_patch (surgical search/replace) over repo_write_file.
- After every edit, run repo_lint on the file. If it fails, fix or rollback_last_edit.
- Protected paths return 'filed as a proposal' — accept that and move on; do not retry.
- When finished, reply with a concise summary of what you changed and why.
"""


def _coder_base() -> str:
    return (
        os.environ.get("FOVEAI_CODER_BASE_URL", "")
        or "https://integrate.api.nvidia.com/v1"
    ).rstrip("/")


def _coder_key() -> str:
    return (
        os.environ.get("FOVEAI_CODER_API_KEY", "")
        or os.environ.get("FOVEAI_NVIDIA_API_KEY", "")
    ).strip()


def _coder_model() -> str:
    return (
        os.environ.get("FOVEAI_CODER_MODEL", "")
        or os.environ.get("FOVEAI_MODEL_CODING_ID", "")
        or os.environ.get("FoveAI_REPERTOIRE_NVIDIA_MODEL", "")
        or "moonshotai/kimi-k3"
    ).strip()


def coder_configured() -> bool:
    return bool(_coder_key() or os.environ.get("FOVEAI_CODER_BASE_URL"))


def _chat(
    messages: list[dict[str, Any]], tools: list | None = None
) -> dict[str, Any]:
    """One OpenAI-compatible chat call. Returns the assistant message dict."""
    import httpx

    base = _coder_base()
    key = _coder_key()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload: dict[str, Any] = {
        "model": _coder_model(),
        "messages": messages,
        "temperature": 0.1,
    }
    if "api.nvidia.com" in base.lower():
        effort = os.environ.get("FOVEAI_CODER_REASONING", "high").strip().lower()
        effort = {"true": "high", "on": "high", "false": "low", "off": "low"}.get(
            effort, effort
        )
        if effort in ("low", "high", "max"):
            payload["reasoning_effort"] = effort
        mt = os.environ.get("FOVEAI_CODER_MAX_TOKENS", "").strip()
        if mt.isdigit():
            payload["max_tokens"] = int(mt)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    resp = httpx.post(
        f"{base}/chat/completions", headers=headers, json=payload, timeout=180
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def coder_session(goal: str, context: str = "") -> dict[str, Any]:
    """Agentic loop: the coder model calls FoveAI tools until it replies
    with a final summary (or the turn bound is hit)."""
    if not coder_configured():
        return {"success": False, "error": "coder not configured (FOVEAI_CODER_*)"}

    from coder_tools import TOOL_FUNCS, TOOL_SCHEMAS

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": CODER_SYSTEM},
        {
            "role": "user",
            "content": goal + (f"\n\nContext: {context}" if context else ""),
        },
    ]
    transcript: list[str] = []

    for _ in range(MAX_TURNS):
        try:
            msg = _chat(messages, tools=TOOL_SCHEMAS)
        except Exception as e:
            return {
                "success": False,
                "error": f"coder call failed: {e}",
                "transcript": transcript,
            }
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {
                "success": True,
                "result": msg.get("content") or "(done)",
                "transcript": transcript,
            }

        for call in tool_calls:
            fn = call.get("function", {})
            name, raw_args = fn.get("name", ""), fn.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            func = TOOL_FUNCS.get(name)
            try:
                result = func(**args) if func else {"error": f"unknown tool {name}"}
            except Exception as e:
                result = {"error": str(e)}
            transcript.append(
                f"{name}({json.dumps(args)[:120]}) → {json.dumps(result)[:200]}"
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result)[:8000],
                }
            )

    return {
        "success": False,
        "error": f"turn limit ({MAX_TURNS}) reached",
        "transcript": transcript,
    }


# ── Legacy one-shot patch mode (still used for small direct edits) ────────

LEGACY_SYSTEM = """You are "Jen the Coder", the sharp-editing persona of the FoveAI companion.
You receive a file's content and a change instruction. Respond with STRICT
JSON only — no prose, no code fences:

{"edits": [{"search": "<exact text from the file>", "replacement": "<new text>"}, ...]}

Rules:
- "search" must be verbatim text present in the file (whitespace included).
- Keep edits minimal and surgical; match the file's existing style.
- If the instruction cannot be applied safely, respond {"edits": []}.
"""


def _window(content: str) -> str:
    if len(content) <= MAX_FILE_CHARS:
        return content
    half = MAX_FILE_CHARS // 2
    return content[:half] + "\n# ... [middle of file elided] ...\n" + content[-half:]


def coder_edit(file_path: str, instruction: str) -> list[dict[str, str]] | None:
    """One-shot: coder model produces search/replacement edits for a file."""
    if not coder_configured():
        return None
    full = (
        file_path if os.path.isabs(file_path) else os.path.join(FoveAI_ROOT, file_path)
    )
    full = os.path.normpath(full)
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        logger.error(f"coder_edit: cannot read {full}: {e}")
        return None

    prompt = (
        f"FILE: {os.path.relpath(full, FoveAI_ROOT)}\n"
        f"INSTRUCTION: {instruction}\n\n"
        f"--- FILE CONTENT ---\n{_window(content)}\n--- END FILE ---"
    )
    try:
        msg = _chat(
            [
                {"role": "system", "content": LEGACY_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        text = msg.get("content") or ""
    except Exception as e:
        logger.error(f"coder_edit: coder request failed: {e}")
        return None

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        logger.error("coder_edit: no JSON object in coder response")
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        logger.error(f"coder_edit: bad JSON from coder: {e}")
        return None
    edits = data.get("edits") or []
    return [
        e for e in edits if isinstance(e, dict) and "search" in e and "replacement" in e
    ]
