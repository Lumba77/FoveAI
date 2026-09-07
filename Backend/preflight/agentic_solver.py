import importlib.util
import json
import logging
import os
import random
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from preflight.json_util import load_playbook_path


logger = logging.getLogger("AgenticSolver")

_cloud_repertoire_mod: Any = None


def _get_cloud_repertoire() -> Any:
    """Load Mind/Cognition/cloud_repertoire.py without package imports (sentry cwd is Backend/)."""
    global _cloud_repertoire_mod
    if _cloud_repertoire_mod is not None:
        return _cloud_repertoire_mod
    path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "Mind", "Cognition", "cloud_repertoire.py")
    )
    if not os.path.isfile(path):
        raise FileNotFoundError(f"cloud_repertoire not found at {path}")
    spec = importlib.util.spec_from_file_location("foveai_cloud_repertoire_sentry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cloud_repertoire import spec invalid")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _cloud_repertoire_mod = mod
    return mod


def _sentry_repertoire_max_tokens() -> int:
    try:
        return max(128, min(4096, int(os.getenv("FoveAI_SENTRY_REPERTOIRE_MAX_TOKENS", "768") or "768")))
    except ValueError:
        return 768


def _resolve_sentry_repertoire_slot(cr: Any) -> Optional[str]:
    """
    Which cloud slot the sentry uses: openai | gemini | extra | rotate | auto.
    auto|rotate pick from eligible_cloud_slot_ids() (respects OpenAI daily cap when configured).
    """
    raw = os.getenv("FoveAI_SENTRY_REPERTOIRE_SLOT", "gemini").strip().lower()
    slots: List[str] = list(cr.eligible_cloud_slot_ids())
    if not slots:
        return None
    if raw in ("openai", "gemini", "extra"):
        if raw not in slots:
            logger.warning(
                "Sentry repertoire: slot %r unavailable (not configured or cap); using %r",
                raw,
                slots[0],
            )
            return slots[0]
        return raw
    if raw in ("rotate", "auto"):
        return random.choice(slots)
    logger.warning("Unknown FoveAI_SENTRY_REPERTOIRE_SLOT=%r — using %r", raw, slots[0])
    return slots[0]


def _solve_with_repertoire_cloud(prompt: str) -> Dict:
    """OpenAI-compatible cloud (same .env slots as Jen / cloud_repertoire)."""
    try:
        cr = _get_cloud_repertoire()
    except Exception as e:
        logger.warning("Sentry could not load cloud_repertoire: %s", e)
        return {"actions": ["none"], "reason": f"repertoire-import:{e}"}
    slot = _resolve_sentry_repertoire_slot(cr)
    if not slot:
        return {"actions": ["none"], "reason": "repertoire-no-slots"}
    system = (
        "You are a JSON-only API. Output a single JSON object, no markdown, no commentary. "
        "The user message contains the exact schema required."
    )
    mt = _sentry_repertoire_max_tokens()
    try:
        text = cr.generate_via_slot_sync(slot, system, prompt, max_tokens=mt)
    except Exception as e:
        logger.warning("Sentry repertoire HTTP error: %s", e)
        return {"actions": ["none"], "reason": f"repertoire-http:{e}"}
    return _parse_actions(text)


def _solve_text_with_repertoire(prompt: str) -> str:
    try:
        cr = _get_cloud_repertoire()
    except Exception as e:
        return f"Repertoire solver unavailable: {e}"
    slot = _resolve_sentry_repertoire_slot(cr)
    if not slot:
        return "No cloud API slots configured (set FoveAI_REPERTOIRE_* in .env for foveai_ops)."
    mt = _sentry_repertoire_max_tokens()
    try:
        return str(cr.generate_via_slot_sync(slot, "", prompt, max_tokens=mt) or "").strip()
    except Exception as e:
        return f"Repertoire request failed: {e}"

ALLOWED_ACTIONS = {
    "docker_compose_up",
    "bridge_reverse",
    "recheck_services",
    "sleep_short",
    "refresh_network_config",
    "preflight_standard",
    "preflight_deep",
    "restart_service_soul",
    "restart_service_body",
    "restart_service_turbo",
    "restart_service_ops",
    "inspect_containers",
    "capture_service_logs",
    "extended_test_probe",
    "request_architecture_plan",
    "none",
}


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default)).strip().lower()
    return v in ("1", "true", "yes", "on")


def _build_prompt(failures: Dict[str, bool]) -> str:
    return (
        "You are a backend sentry healer for Lumax.\n"
        "Given failing services, return strict JSON only with schema:\n"
        '{"actions":[<allowed_action>],"reason":"...","confidence":0.0,"request_approval":false,'
        '"improvement_notes":[],"test_measures":[]}\n'
        "Allowed actions are: "
        + ", ".join(sorted(ALLOWED_ACTIONS))
        + "\n"
        f"Failures: {json.dumps(failures)}\n"
        "Rules: Prefer minimal actions. Never suggest destructive operations.\n"
        "If only WEBUI is failing, prefer inspect_containers or restart_service_ops (when policy allows restarts).\n"
    )


def _is_temporarily_paused() -> str:
    # Manual pause switch for deploy windows.
    if _bool_env("FoveAI_SENTRY_AGENTIC_PAUSED", False):
        return "agentic-paused-env"
    # Simple file lock, useful from deploy scripts: create lock before rollout, remove after.
    lock_path = os.getenv("FoveAI_SENTRY_DEPLOY_LOCK_PATH", "").strip()
    if lock_path and os.path.exists(lock_path):
        return "agentic-paused-lockfile"
    # Optional time window pause (unix epoch seconds).
    pause_until = os.getenv("FoveAI_SENTRY_PAUSE_UNTIL_EPOCH", "").strip()
    if pause_until:
        try:
            if time.time() < float(pause_until):
                return "agentic-paused-time-window"
        except ValueError:
            pass
    return ""


def _parse_actions(text: str) -> Dict:
    raw = text.strip()
    # Try exact JSON first
    try:
        data = json.loads(raw)
    except Exception:
        # Try extracting first JSON object region
        lb = raw.find("{")
        rb = raw.rfind("}")
        if lb >= 0 and rb > lb:
            try:
                data = json.loads(raw[lb : rb + 1])
            except Exception:
                return {"actions": ["none"], "reason": "unparseable-model-output"}
        else:
            return {"actions": ["none"], "reason": "no-json-found"}

    actions = data.get("actions", [])
    if not isinstance(actions, list):
        actions = ["none"]
    cleaned: List[str] = []
    for a in actions:
        if isinstance(a, str) and a in ALLOWED_ACTIONS:
            cleaned.append(a)
    if not cleaned:
        cleaned = ["none"]
    notes = data.get("improvement_notes", [])
    tests = data.get("test_measures", [])
    if not isinstance(notes, list):
        notes = []
    if not isinstance(tests, list):
        tests = []
    return {
        "actions": cleaned,
        "reason": str(data.get("reason", "")),
        "confidence": float(data.get("confidence", 0.0) or 0.0),
        "request_approval": bool(data.get("request_approval", False)),
        "improvement_notes": [str(x) for x in notes[:12]],
        "test_measures": [str(x) for x in tests[:12]],
    }


def _strip_ollama_api_suffixes(url: str) -> str:
    """Strip trailing /api/* paths so we get scheme://host:port."""
    u = (url or "").strip().rstrip("/")
    for suffix in ("/api/generate", "/api/chat", "/api/embeddings", "/v1/chat/completions"):
        if u.endswith(suffix):
            return u[: -len(suffix)].rstrip("/")
    return u


def solver_ollama_base_url() -> str:
    """
    Ollama base URL (no /api/... path).

    Priority: FoveAI_SENTRY_OLLAMA_HOST → FoveAI_SENTRY_SOLVER_URL (legacy full URL) → OLLAMA_HOST.
    """
    explicit = os.getenv("FoveAI_SENTRY_OLLAMA_HOST", "").strip()
    if explicit:
        return _strip_ollama_api_suffixes(explicit)
    legacy = os.getenv("FoveAI_SENTRY_SOLVER_URL", "").strip()
    if legacy:
        return _strip_ollama_api_suffixes(legacy)
    oh = os.getenv("OLLAMA_HOST", "http://foveai_ollama_backup:11434").strip().rstrip("/")
    return oh


def _ollama_try_generate(client: httpx.Client, base: str, model: str, prompt: str) -> Tuple[Optional[int], str]:
    r = client.post(
        f"{base}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
    )
    if r.status_code != 200:
        return r.status_code, ""
    try:
        body = r.json()
    except Exception:
        return 200, ""
    return 200, str(body.get("response", "")).strip()


def _ollama_try_chat(client: httpx.Client, base: str, model: str, prompt: str) -> Tuple[Optional[int], str]:
    r = client.post(
        f"{base}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
    )
    if r.status_code != 200:
        return r.status_code, ""
    try:
        body = r.json()
    except Exception:
        return 200, ""
    msg = body.get("message")
    if isinstance(msg, dict):
        return 200, str(msg.get("content", "")).strip()
    return 200, str(body.get("response", "") or "").strip()


def _ollama_complete_text(model: str, prompt: str, timeout: float) -> str:
    """
    Call Ollama /api/generate and optionally /api/chat. Does not raise on HTTP errors; logs and returns "".
    FoveAI_SENTRY_SOLVER_HTTP_MODE: auto | generate | chat
    """
    base = solver_ollama_base_url()
    mode = os.getenv("FoveAI_SENTRY_SOLVER_HTTP_MODE", "auto").strip().lower()
    if mode not in ("auto", "generate", "chat"):
        mode = "auto"

    try:
        with httpx.Client(timeout=timeout) as client:
            if mode == "chat":
                code, text = _ollama_try_chat(client, base, model, prompt)
                if code == 200 and text:
                    return text
                logger.debug("Ollama chat-only mode: code=%s empty=%s base=%s", code, not text, base)
                return ""

            # generate first for "auto" and "generate"
            code, text = _ollama_try_generate(client, base, model, prompt)
            if code == 200 and text:
                return text
            if mode == "generate":
                if code == 404:
                    logger.warning(
                        "Ollama /api/generate returned 404 — missing model %r or wrong base %s",
                        model,
                        base,
                    )
                else:
                    logger.debug("Ollama /api/generate non-OK code=%s base=%s", code, base)
                return ""

            # auto: fallback to chat if generate failed or returned empty
            if mode == "auto":
                c2, t2 = _ollama_try_chat(client, base, model, prompt)
                if c2 == 200 and t2:
                    return t2
                if c2 == 404:
                    logger.debug(
                        "Ollama /api/chat not available (404) at %s — generate may have failed or model missing",
                        base,
                    )
                elif c2 != 200:
                    logger.debug("Ollama /api/chat code=%s base=%s", c2, base)
                if code == 404:
                    logger.warning(
                        "Ollama solver: both generate and chat failed for model %r at %s",
                        model,
                        base,
                    )
                return ""
    except httpx.RequestError as e:
        logger.warning("Ollama request error (base=%s): %s", base, e)
        return ""

    return ""


def _solve_with_ollama(prompt: str) -> Dict:
    model = os.getenv("FoveAI_SENTRY_SOLVER_MODEL", "qwen2.5-coder:latest").strip()
    timeout = float(os.getenv("FoveAI_SENTRY_SOLVER_TIMEOUT_SEC", "20"))
    text = _ollama_complete_text(model, prompt, timeout)
    return _parse_actions(text)


def _solve_text_with_ollama(prompt: str) -> str:
    model = os.getenv("FoveAI_SENTRY_SOLVER_MODEL", "qwen2.5-coder:latest").strip()
    timeout = float(os.getenv("FoveAI_SENTRY_SOLVER_TIMEOUT_SEC", "20"))
    return _ollama_complete_text(model, prompt, timeout)


def _solve_with_command(prompt: str) -> Dict:
    """
    Command mode for ONNX/TensorRT runner wrappers.
    Env:
      FoveAI_SENTRY_SOLVER_CMD='runner --model qwen2.5-coder-onnx --prompt "{prompt}"'
    """
    cmd_tpl = os.getenv("FoveAI_SENTRY_SOLVER_CMD", "").strip()
    if not cmd_tpl:
        return {"actions": ["none"], "reason": "missing-command-template"}
    cmd = cmd_tpl.replace("{prompt}", prompt.replace('"', '\\"'))
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        text = (proc.stdout or proc.stderr or "").strip()
        return _parse_actions(text)
    except Exception as e:
        return {"actions": ["none"], "reason": f"command-error:{e}"}


def _solve_text_with_command(prompt: str) -> str:
    cmd_tpl = os.getenv("FoveAI_SENTRY_SOLVER_CMD", "").strip()
    if not cmd_tpl:
        return "Solver command template is missing."
    cmd = cmd_tpl.replace("{prompt}", prompt.replace('"', '\\"'))
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=40)
        return (proc.stdout or proc.stderr or "").strip()
    except Exception as e:
        return f"Solver command failed: {e}"


def _read_unstable_features() -> List[Dict]:
    path = os.getenv("FoveAI_SENTRY_UNSTABLE_FEATURES_PATH", "/app/ops/playbooks/unstable_features.json").strip()
    if not path or not os.path.isfile(path):
        return []
    try:
        data = load_playbook_path(path, encoding="utf-8-sig")
        if not isinstance(data, dict):
            return []
        features = data.get("features", [])
        if not isinstance(features, list):
            return []
        out: List[Dict] = []
        for item in features:
            if isinstance(item, dict) and item.get("name"):
                out.append(item)
        return out
    except Exception as e:
        logger.warning("Could not read unstable feature registry: %s", e)
        return []


def read_unstable_features() -> List[Dict]:
    """Public wrapper for sentry loop usage."""
    return _read_unstable_features()


def _build_architect_prompt(failures: Dict[str, bool], unstable_features: List[Dict], solver_reason: str) -> str:
    return (
        "You are a senior architect for Lumax reliability.\n"
        "Create a concrete implementation proposal for missing/unstable features.\n"
        "Return strict JSON with schema:\n"
        '{"title":"...",'
        '"summary":"...",'
        '"missing_capabilities":["..."],'
        '"proposed_implementation":["..."],'
        '"code_change_candidates":[{"path":"...","change":"..."}],'
        '"extended_tests":["..."],'
        '"safety_guards":["..."],'
        '"requires_user_approval":true}\n'
        f"Current service failures: {json.dumps(failures)}\n"
        f"Unstable feature registry: {json.dumps(unstable_features)}\n"
        f"Current solver reason: {solver_reason}\n"
    )


def propose_architecture_plan(failures: Dict[str, bool], solver_decision: Optional[Dict] = None) -> Dict:
    if not _bool_env("FoveAI_SENTRY_ARCHITECT_ENABLED", False):
        return {
            "title": "architect-disabled",
            "summary": "Architect escalation is disabled.",
            "missing_capabilities": [],
            "proposed_implementation": [],
            "code_change_candidates": [],
            "extended_tests": [],
            "safety_guards": [],
            "requires_user_approval": True,
        }
    cmd_tpl = os.getenv("FoveAI_SENTRY_ARCHITECT_CMD", "").strip()
    if not cmd_tpl:
        return {
            "title": "architect-missing-command",
            "summary": "Architect command template is not configured.",
            "missing_capabilities": [],
            "proposed_implementation": [],
            "code_change_candidates": [],
            "extended_tests": [],
            "safety_guards": [],
            "requires_user_approval": True,
        }

    unstable = _read_unstable_features()
    reason = str((solver_decision or {}).get("reason", ""))
    prompt = _build_architect_prompt(failures, unstable, reason)
    cmd = cmd_tpl.replace("{prompt}", prompt.replace('"', '\\"'))
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        text = (proc.stdout or proc.stderr or "").strip()
        if not text:
            return {
                "title": "architect-empty",
                "summary": "No output from architect model.",
                "missing_capabilities": [],
                "proposed_implementation": [],
                "code_change_candidates": [],
                "extended_tests": [],
                "safety_guards": [],
                "requires_user_approval": True,
            }
        lb = text.find("{")
        rb = text.rfind("}")
        if lb >= 0 and rb > lb:
            text = text[lb : rb + 1]
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("architect output is not a JSON object")
        data["requires_user_approval"] = True
        return data
    except Exception as e:
        logger.warning("Architect proposal failed: %s", e)
        return {
            "title": "architect-failed",
            "summary": f"Architect proposal failed: {e}",
            "missing_capabilities": [],
            "proposed_implementation": [],
            "code_change_candidates": [],
            "extended_tests": [],
            "safety_guards": [],
            "requires_user_approval": True,
        }


def propose_actions(failures: Dict[str, bool], unstable_features: Optional[List[Dict]] = None) -> Dict:
    """
    Returns:
      {"actions":[...], "reason":"..."}
    """
    if not _bool_env("FoveAI_SENTRY_AGENTIC", False):
        return {"actions": ["none"], "reason": "agentic-disabled"}
    pause_reason = _is_temporarily_paused()
    if pause_reason:
        return {"actions": ["none"], "reason": pause_reason}

    # Default matches docker-compose foveai_ops (command / local runner); set FoveAI_SENTRY_SOLVER_MODE=ollama to use Ollama.
    mode = os.getenv("FoveAI_SENTRY_SOLVER_MODE", "command").strip().lower()
    prompt = _build_prompt(failures)
    if unstable_features:
        prompt += f"Unstable features: {json.dumps(unstable_features)}\n"
    try:
        if mode == "command":
            out = _solve_with_command(prompt)
        elif mode in ("repertoire", "cloud"):
            out = _solve_with_repertoire_cloud(prompt)
        else:
            out = _solve_with_ollama(prompt)
        logger.debug("Agentic solver proposed actions=%s reason=%s", out.get("actions"), out.get("reason"))
        return out
    except Exception as e:
        logger.warning("Agentic solver failed: %s", e)
        return {"actions": ["none"], "reason": f"solver-failed:{e}"}


def answer_runtime_question(question: str, context: Dict) -> str:
    """
    Ask solver for an investigation answer using runtime context.
    Returns plain text markdown.
    """
    mode = os.getenv("FoveAI_SENTRY_SOLVER_MODE", "command").strip().lower()
    prompt = (
        "You are Lumax watchdog investigator.\n"
        "Answer with: findings, likely causes, safe checks, and recommended next steps.\n"
        "Do not propose destructive actions.\n"
        f"Question: {question}\n"
        f"Runtime context JSON: {json.dumps(context)[:40000]}\n"
    )
    try:
        if mode == "command":
            text = _solve_text_with_command(prompt)
        elif mode in ("repertoire", "cloud"):
            text = _solve_text_with_repertoire(prompt)
        else:
            text = _solve_text_with_ollama(prompt)
        txt = (text or "").strip()
        if not txt:
            return _fallback_runtime_answer(question, context, "empty-solver-output")
        # If wrapper returns a degenerate none/reason payload, provide useful local analysis.
        if "runner-error" in txt or "missing-command-template" in txt:
            return _fallback_runtime_answer(question, context, txt[:400])
        return txt
    except Exception as e:
        return _fallback_runtime_answer(question, context, f"solver-exception:{e}")


def _fallback_runtime_answer(question: str, context: Dict, failure_reason: str) -> str:
    failures = context.get("failures", {}) if isinstance(context, dict) else {}
    inspect = context.get("inspect_report", {}) if isinstance(context, dict) else {}
    service_inspect = inspect.get("service_inspect", {}) if isinstance(inspect, dict) else {}
    recent_logs = inspect.get("recent_logs", {}) if isinstance(inspect, dict) else {}

    down = [k for k, v in failures.items() if v]
    likely = []
    if "TURBO" in down:
        likely.append("Turbo service appears unreachable from foveai_ops (DNS/network/container state).")
    if not down:
        likely.append("No service heartbeat failures detected in this cycle.")
    if any("No such file or directory: 'runner'" in str(v) for v in [failure_reason]):
        likely.append("Local ONNX runner command is not available in container PATH.")

    safe_checks = [
        "Verify foveai_turbochat container exists and is on foveai_local network.",
        "Check solver runtime command/env: FoveAI_LOCAL_RUNNER_CMD and FoveAI_SENTRY_SOLVER_CMD.",
        "Keep bridge maintenance active; compare failure signatures across 3 cycles.",
    ]
    if "animation" in question.lower():
        safe_checks.extend(
            [
                "Capture latest Godot animation diagnostics and compare player path/root_node consistency.",
                "Temporarily keep startup auto greeting disabled while validating idle path only.",
            ]
        )

    return (
        "## Watchdog fallback investigation\n"
        f"- Solver reason: {failure_reason}\n"
        f"- Failing services: {down if down else ['none']}\n"
        f"- Likely causes: {likely}\n"
        f"- Safe next checks: {safe_checks}\n"
        f"- Evidence keys: service_inspect={list(service_inspect.keys())[:8]}, recent_logs={list(recent_logs.keys())[:8]}\n"
    )

