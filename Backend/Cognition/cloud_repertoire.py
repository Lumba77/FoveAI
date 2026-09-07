"""
OpenAI-compatible API slot router. Configure every slot via FoveAI_REPERTOIRE_* env vars.
No IP addresses or ports are hardcoded — all local service addresses come from .env with
localhost defaults. Cloud API endpoints use their public URLs as defaults.

Local slots (LMSTUDIO, WINDOWS_NPU) do NOT require an API key — they are treated as keyless.
For LAN access (e.g. Quest 3 reaching the host PC), set FoveAI_REPERTOIRE_WINDOWS_NPU_BASE_URL
or FoveAI_REPERTOIRE_LMSTUDIO_BASE_URL to the LAN IP in .env.

Env var pattern per slot PREFIX (OPENAI, GEMINI, EXTRA, LMSTUDIO, OLLAMA, OPENROUTER, VENICE, GITHUB, WINDOWS_NPU):
  FoveAI_REPERTOIRE_{PREFIX}_API_KEY   — API key (required for cloud slots, optional for local)
  FoveAI_REPERTOIRE_{PREFIX}_BASE_URL  — Override base URL (falls back to public API default)
  FoveAI_REPERTOIRE_{PREFIX}_MODEL     — Model name (slot-specific defaults apply)
  FoveAI_REPERTOIRE_{PREFIX}_LABEL     — Display label

Additional fallbacks for specific slots:
  OLLAMA:     OLLAMA_API_KEY, FoveAI_CLOUD_BASE_URL, FoveAI_MODEL_CLOUD_ID
  LMSTUDIO:   LMSTUDIO_MAIN_MODEL
  WINDOWS_NPU: (uses windows-npu-phi-silica as default model)

OpenAI pay-as-you-go guard:
  FoveAI_OPENAI_DAILY_MAX_REQUESTS — if > 0, cap successful OpenAI-slot calls per UTC day (state file).
  FoveAI_OPENAI_USAGE_STATE_PATH — optional JSON counter file (default: system temp dir).
  FoveAI_REPERTOIRE_OPENAI_MAX_TOKENS — optional lower max_tokens for OpenAI slot only.
Also set hard limits in the OpenAI / Azure dashboard where available; this is a local safety net.

Cloud completion length:
  FoveAI_CLOUD_MAX_TOKENS — default max_tokens for /chat/completions when callers do not pass max_tokens.
  FoveAI_CLOUD_MAX_TOKENS_CAP — upper clamp for max_tokens (default 131072 if unset). Set lower (e.g. 8192)
  on small models or tight budgets.
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

import genai_daily_budget

logger = logging.getLogger("cloud_repertoire")

# Safe imports for TokenSlayer and Motor Cortex
try:
    from motor_cortex import get_motor_tools_schema  # type: ignore
except ImportError:
    try:
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from motor_cortex import get_motor_tools_schema  # type: ignore
    except ImportError:
        def get_motor_tools_schema() -> list:
            return []

try:
    from smart_context_manager import smart_context_manager  # type: ignore
except ImportError:
    try:
        import sys
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Forge")))
        from smart_context_manager import smart_context_manager  # type: ignore
    except ImportError:
        smart_context_manager = None

# --- Cloudflare Anti-Bot Bypass ---
# Cloudflare blocks Python httpx default User-Agent ("python-httpx/...").
# Ollama Cloud (ollama.com) is behind Cloudflare, so we must use a
# browser-like User-Agent header for all external cloud API calls.
_CLOUD_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"


def _cloud_max_output_tokens_ceiling() -> int:
    """Upper bound for max_tokens on OpenAI-compatible /chat/completions."""
    raw = os.getenv("FoveAI_CLOUD_MAX_TOKENS_CAP", "").strip()
    if not raw:
        return 131_072
    try:
        v = int(raw)
        return max(256, min(v, 2_000_000))
    except ValueError:
        return 131_072


# Default base URLs when BASE_URL is omitted but key+model are set.
# Repertoire slimmed: Ollama Cloud is primary (handled outside repertoire),
# repertoire only holds fallback cloud providers.
_DEFAULT_BASE = {
    "OLLAMA_CLOUD": "https://ollama.com/v1",
    "GEMINI": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "OPENROUTER": "https://openrouter.ai/api/v1",
}

# No slots are keyless in the slimmed repertoire (all are cloud providers).
_NO_KEY_REQUIRED: set = set()

# OLLAMA_CLOUD first (primary), then GEMINI and OPENROUTER as fallbacks.
_SLOT_ORDER = ("OLLAMA_CLOUD", "GEMINI", "OPENROUTER")
_SLOT_PUBLIC_ID = {
    "OLLAMA_CLOUD": "ollama_cloud",
    "GEMINI": "gemini",
    "OPENROUTER": "openrouter",
}

def _utc_date_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def openai_daily_request_cap() -> int:
    """0 = unlimited local counting (no cap enforced in this module)."""
    try:
        return max(0, int(os.getenv("FoveAI_OPENAI_DAILY_MAX_REQUESTS", "0") or "0"))
    except ValueError:
        return 0


def _openai_usage_state_path() -> str:
    p = os.getenv("FoveAI_OPENAI_USAGE_STATE_PATH", "").strip()
    if p:
        return p
    import tempfile

    return os.path.join(tempfile.gettempdir(), "foveai_openai_daily_usage.json")


def openai_daily_budget_allows() -> bool:
    cap = openai_daily_request_cap()
    if cap <= 0:
        return True
    path = _openai_usage_state_path()
    today = date.today().isoformat()
    count = 0
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                st = json.load(f)
            if st.get("date") == today:
                count = int(st.get("count", 0))
        except Exception as e:
            logger.warning("cloud_repertoire: OpenAI usage state unreadable (%s), treating as 0", e)
    return count < cap


def openai_budget_record_successful_request() -> None:
    cap = openai_daily_request_cap()
    if cap <= 0:
        return
    path = _openai_usage_state_path()
    today = date.today().isoformat()
    count = 0
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                st = json.load(f)
            if st.get("date") == today:
                count = int(st.get("count", 0))
        except Exception:
            pass
    count += 1
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": today, "count": count}, f)
    except Exception as e:
        logger.error("cloud_repertoire: could not write OpenAI usage state: %s", e)


def eligible_cloud_slot_ids() -> List[str]:
    """Configured cloud slots in priority order."""
    if os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower() == "local":
        return []
    slots = [_SLOT_PUBLIC_ID[p] for p in _SLOT_ORDER if slot_credentials(p)]
    return slots


def privacy_slot_ids() -> List[str]:
    """Slots suitable for privacy mode.
    Repertoire slimmed — only OpenRouter available for privacy."""
    if os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower() == "local":
        return []
    privacy_order = ("OPENROUTER",)
    privacy_slots = []
    for prefix in privacy_order:
        pid = _SLOT_PUBLIC_ID.get(prefix)
        if pid and slot_credentials(prefix):
            privacy_slots.append(pid)
    if not privacy_slots:
        logger.info("cloud_repertoire: no privacy slots configured — falling back to all eligible slots")
        return eligible_cloud_slot_ids()
    return privacy_slots


def _read_slot(prefix: str) -> Tuple[str, str, str, str]:
    if prefix == "OPENROUTER":
        key = os.getenv("FoveAI_CLOUD_OPENROUTER_API", "").strip()
        base = os.getenv("FoveAI_CLOUD_OPENROUTER_BASEURL", "").strip()
        model = os.getenv("FoveAI_MODEL_OPENROUTER_ID", "gryphe/mythomax-l2-13b").strip()
        label = os.getenv("FoveAI_REPERTOIRE_OPENROUTER_LABEL", "OpenRouter Intimate").strip()
        return base, key, model, label

    if prefix == "OLLAMA_CLOUD":
        key = os.getenv("FoveAI_REPERTOIRE_OLLAMA_API_KEY", "").strip()
        if not key:
            key = os.getenv("OLLAMA_API_KEY", "").strip()
        base = os.getenv("FoveAI_CLOUD_BASE_URL", "").strip()
        if not base:
            base = _DEFAULT_BASE.get(prefix, "")
        model = os.getenv("FoveAI_MODEL_CLOUD_ID", "").strip()
        if not model:
            model = "gemma3:latest"
        label = os.getenv("FoveAI_REPERTOIRE_OLLAMA_CLOUD_LABEL", "").strip() or "Ollama Cloud Mind"
        return base, key, model, label

    # Generic fallback for GEMINI and any future cloud slots
    key = os.getenv(f"FoveAI_REPERTOIRE_{prefix}_API_KEY", "").strip()
    if not key:
        if prefix == "GEMINI":
            key = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")).strip()

    model = os.getenv(f"FoveAI_REPERTOIRE_{prefix}_MODEL", "").strip()
    if prefix == "GEMINI" and not model:
        model = "gemini-2.5-flash"
    base = os.getenv(f"FoveAI_REPERTOIRE_{prefix}_BASE_URL", "").strip()
    if not base:
        base = _DEFAULT_BASE.get(prefix, "")
    label = os.getenv(f"FoveAI_REPERTOIRE_{prefix}_LABEL", prefix.title()).strip() or prefix.title()
    return base, key, model, label


def ollama_deep_model() -> str:
    """Return the deep-reasoning model for analytical tasks."""
    return os.getenv("FoveAI_REPERTOIRE_OLLAMA_DEEP_MODEL", "gemma3:27b").strip() or "gemma3:27b"


def slot_credentials(prefix: str) -> Optional[Tuple[str, str, str, str]]:
    """Returns (base_url, api_key, model, label) if the slot is usable."""
    if os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower() == "local":
        return None
    base, key, model, label = _read_slot(prefix)
    if base and model and (key or prefix in _NO_KEY_REQUIRED):
        return base, key, model, label
    return None


def configured_slots_public() -> List[Dict[str, str]]:
    """Safe for logging / prompts — no secrets."""
    if os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower() == "local":
        return []
    out: List[Dict[str, str]] = []
    for p in _SLOT_ORDER:
        cred = slot_credentials(p)
        if not cred:
            continue
        base, _key, model, label = cred
        out.append(
            {
                "id": _SLOT_PUBLIC_ID[p],
                "label": label,
                "model": model,
                "base_host": base.split("//")[-1].split("/")[0][:80],
            }
        )
    return out


def genai_budget_sensory_line() -> str:
    """Short line for soul system context when cloud ceilings are active."""
    snap = genai_daily_budget.usage_snapshot()
    cap = int(snap.get("daily_cap") or 0)
    if cap <= 0:
        return ""
    used = int(snap.get("used_today_utc") or 0)
    rem = snap.get("remaining")
    rem_s = "unknown" if rem is None else str(rem)
    return (
        f"Cloud GenAI budget (UTC day): {used} of {cap} paid completions used; {rem_s} remaining. "
        "Each cloud call is precious — default to local mind unless this moment truly needs the remote model."
    )


def repertoire_sensory_text() -> str:
    slots = configured_slots_public()
    if not slots:
        return ""
    lines = [
        "API slots configured on this deployment. ",
    ]
    for s in slots:
        lines.append(f"  — {s['label']} (`{s['id']}`): model `{s['model']}` @ `{s['base_host']}`")
    cap = openai_daily_request_cap()
    if cap > 0 and any(s["id"] == "openai" for s in slots):
        lines.append(
            f"  — OpenAI slot: local daily request cap = {cap} successful calls (UTC day, file-backed);"
        )
    return "\n".join(lines)


def resolve_cloud_slot(
    request_override: Optional[str],
    env_mode: str,
    splice_percent: int,
) -> Optional[str]:
    """
    Returns public slot id or None -> use absolute native local.
    Forcefully prevents cloud leaks if cognitive mode flags request local setups.
    """
    # Strict Enforcement Gate
    cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower()
    if cog_mode == "local":
        logger.info("cloud_repertoire: FoveAI_COGNITIVE_MODE is hard-locked to local. Bypassing cloud fallbacks.")
        return None

    slots = eligible_cloud_slot_ids()
    all_configured = [s["id"] for s in configured_slots_public()]
    if not all_configured:
        return None

    o = (request_override or "").strip().lower()
    if o == "local":
        return None
    if o in all_configured:
        return o

    mode = (env_mode or "ollama_cloud").strip().lower()
    if mode == "local":
        return None
    if mode in all_configured:
        return mode
    # Default to first configured slot (ollama_cloud)
    return all_configured[0] if all_configured else None


def _env_prefix_for_public_id(public_id: str) -> Optional[str]:
    pid_lower = public_id.lower()
    for p, pid in _SLOT_PUBLIC_ID.items():
        if pid == pid_lower:
            return p
    return None


async def openai_compatible_chat(
    base_url: str,
    api_key: str,
    model: str,
    system_text: str,
    user_text: str,
    image_base64: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json", "User-Agent": _CLOUD_USER_AGENT}
    if (api_key or "").strip():
        headers["Authorization"] = f"Bearer {api_key}"
    
    if "openrouter.ai" in url.lower():
        headers["HTTP-Referer"] = os.getenv("FoveAI_OPENROUTER_REFERER", "https://github.com/google-gemini/gemini-cli")
        headers["X-Title"] = os.getenv("FoveAI_OPENROUTER_TITLE", "FoveAI AI Companion")

    mt = max_tokens if max_tokens is not None else int(os.getenv("FoveAI_CLOUD_MAX_TOKENS", "4096") or "4096")
    mt = max(64, min(mt, _cloud_max_output_tokens_ceiling()))

    user_content: Any
    if image_base64:
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
            {"type": "text", "text": user_text},
        ]
    else:
        user_content = user_text

    messages: List[Dict[str, Any]] = []
    st = (system_text or "").strip()
    if st:
        messages.append({"role": "system", "content": st})
    messages.append({"role": "user", "content": user_content})

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("FoveAI_CLOUD_TEMPERATURE", "0.7") or "0.7"),
        "max_tokens": mt,
    }
    if os.getenv("FoveAI_MODEL_STRUCTURED_OUTPUT", "false").lower() == "true":
        payload["response_format"] = {"type": "json_object"}

    # Inject native tool call schema if available to give LLM fully spatial presence
    tools = get_motor_tools_schema()
    if tools:
        payload["tools"] = tools

    # Apply smart context manager (TokenSlayer) if available to prune messages to protect quota
    if smart_context_manager is not None:
        try:
            # We format messages to standard role/content dicts for Context Machine
            scm_messages = []
            for m in messages:
                content_str = str(m.get("content", ""))
                # If content is a complex structure (e.g. image + text list), extract the text portion
                if isinstance(m.get("content"), list):
                    for item in m.get("content"):
                        if isinstance(item, dict) and item.get("type") == "text":
                            content_str = item.get("text", "")
                            break
                scm_messages.append({"role": m.get("role", "user"), "content": content_str})
                
            processed_msgs, scm_meta = await smart_context_manager.apply_cutting_strategy(
                "cloud_repertoire", scm_messages
            )
            
            # Reconstruction: Map pruned content back to the original messages payload (preserving system/user format)
            pruned_map = {m.get("content"): m for m in messages if isinstance(m.get("content"), str)}
            new_messages = []
            for pm in processed_msgs:
                orig_m = pruned_map.get(pm.get("content"))
                if orig_m:
                    new_messages.append(orig_m)
                else:
                    # System instruction / fallbacks
                    new_messages.append({"role": pm.get("role"), "content": pm.get("content")})
            
            # Always ensure user message is present
            if not any(nm.get("role") == "user" for nm in new_messages):
                new_messages.append(messages[-1])
                
            payload["messages"] = new_messages
            
            # Report token load back to TokenSlayer
            total_tokens = sum(len(str(m.get("content", ""))) // 4 for m in new_messages)
            await smart_context_manager.report_tokens("cloud_repertoire", total_tokens, new_messages)
        except Exception as sc_err:
            logger.error(f"cloud_repertoire: SmartContext pruning failed: {sc_err}")
    
    # Context-aware logging label to prevent Kafkaesque confusion strings
    log_dest = "Local Cortex" if "localhost" in url or "127.0.0.1" in url else "Cloud Mind"
    logger.info("Executing chat routine via endpoint slot node [%s] targeting model: %s", log_dest, model)

    timeout = float(os.getenv("FoveAI_CLOUD_HTTP_TIMEOUT", "300") or "300")
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=headers, json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            snippet = (r.text or "").replace("\n", " ")[:400]
            logger.error("Endpoint slot failure on HTTP %s %s", r.status_code, snippet)
            raise
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    
    # Robustly extract reasoning/thinking content from all known vendor/spec formats
    reasoning = ""
    for k in ("reasoning_content", "reasoning", "thinking", "thought", "thinking_content"):
        val = msg.get(k)
        if val and isinstance(val, str) and val.strip():
            reasoning = val.strip()
            break
            
    content = (msg.get("content") or "").strip()
    
    # Process native tool calls and convert them to [MOTOR:tool_name{args}] format
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        tool_texts = []
        for tc in tool_calls:
            func = tc.get("function") or {}
            func_name = func.get("name")
            func_args = func.get("arguments") or "{}"
            tool_texts.append(f"[MOTOR:{func_name}{func_args}]")
        if tool_texts:
            if content:
                content = content + "\n" + "\n".join(tool_texts)
            else:
                content = "\n".join(tool_texts)
    
    if reasoning:
        # Prepend wrapped think tags so that MindCore downstream parses/extracts it perfectly
        if content:
            content = f"<think>\n{reasoning}\n</think>\n\n{content}"
        else:
            content = f"<think>\n{reasoning}\n</think>"
            
    return content


def openai_compatible_chat_sync(
    base_url: str,
    api_key: str,
    model: str,
    system_text: str,
    user_text: str,
    *,
    max_tokens: Optional[int] = None,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json", "User-Agent": _CLOUD_USER_AGENT}
    if (api_key or "").strip():
        headers["Authorization"] = f"Bearer {api_key}"
    mt = max_tokens if max_tokens is not None else int(os.getenv("FoveAI_CLOUD_MAX_TOKENS", "4096") or "4096")
    mt = max(64, min(mt, _cloud_max_output_tokens_ceiling()))
    messages: List[Dict[str, Any]] = []
    st = (system_text or "").strip()
    if st:
        messages.append({"role": "system", "content": st})
    messages.append({"role": "user", "content": user_text})
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("FoveAI_CLOUD_TEMPERATURE", "0.7") or "0.7"),
        "max_tokens": mt,
    }
    if os.getenv("FoveAI_MODEL_STRUCTURED_OUTPUT", "false").lower() == "true":
        payload["response_format"] = {"type": "json_object"}
    timeout = float(os.getenv("FoveAI_CLOUD_HTTP_TIMEOUT", "300") or "300")
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            snippet = (r.text or "").replace("\n", " ")[:400]
            logger.error("Sync slot failure on HTTP %s %s", r.status_code, snippet)
            raise
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    
    # Robustly extract reasoning/thinking content from all known vendor/spec formats
    reasoning = ""
    for k in ("reasoning_content", "reasoning", "thinking", "thought", "thinking_content"):
        val = msg.get(k)
        if val and isinstance(val, str) and val.strip():
            reasoning = val.strip()
            break
            
    content = (msg.get("content") or "").strip()
    
    if reasoning:
        # Prepend wrapped think tags so that MindCore downstream parses/extracts it perfectly
        if content:
            content = f"<think>\n{reasoning}\n</think>\n\n{content}"
        else:
            content = f"<think>\n{reasoning}\n</think>"
            
    return content


def generate_via_slot_sync(
    public_slot_id: str,
    system_text: str,
    user_text: str,
    *,
    max_tokens: Optional[int] = None,
    model_override: Optional[str] = None,
) -> str:
    if not genai_daily_budget.allows():
        logger.info("cloud_repertoire: global GenAI daily budget exhausted — skipping sync call")
        return ""
    prefix = _env_prefix_for_public_id(public_slot_id)
    if not prefix:
        raise ValueError(f"unknown slot {public_slot_id}")
    cred = slot_credentials(prefix)
    if not cred:
        raise ValueError(f"slot {public_slot_id} not configured")
    base_url, api_key, model, _label = cred
    if model_override:
        model = model_override
    max_toks = max_tokens
    if max_toks is None and prefix == "OPENAI":
        ot = os.getenv("FoveAI_REPERTOIRE_OPENAI_MAX_TOKENS", "").strip()
        if ot.isdigit():
            max_toks = int(ot)
    out = openai_compatible_chat_sync(
        base_url,
        api_key,
        model,
        system_text,
        user_text,
        max_tokens=max_toks,
    )
    if (out or "").strip():
        genai_daily_budget.record_success(1)
    if prefix == "OPENAI" and (out or "").strip():
        openai_budget_record_successful_request()
    return out


async def generate_via_slot(
    public_slot_id: str,
    system_text: str,
    user_text: str,
    image_base64: Optional[str] = None,
    *,
    model_override: Optional[str] = None,
) -> str:
    if not genai_daily_budget.allows():
        logger.info("cloud_repertoire: global GenAI daily budget exhausted — skipping slot call")
        return ""
    prefix = _env_prefix_for_public_id(public_slot_id)
    if not prefix:
        raise ValueError(f"unknown slot {public_slot_id}")
    cred = slot_credentials(prefix)
    if not cred:
        raise ValueError(f"slot {public_slot_id} not configured")
    base_url, api_key, model, _label = cred
    if model_override:
        model = model_override
    max_toks: Optional[int] = None
    if prefix == "OPENAI":
        ot = os.getenv("FoveAI_REPERTOIRE_OPENAI_MAX_TOKENS", "").strip()
        if ot.isdigit():
            max_toks = int(ot)
    out = await openai_compatible_chat(
        base_url,
        api_key,
        model,
        system_text,
        user_text,
        image_base64=image_base64,
        max_tokens=max_toks,
    )
    if (out or "").strip():
        genai_daily_budget.record_success(1)
    if prefix == "OPENAI" and (out or "").strip():
        openai_budget_record_successful_request()
    return out