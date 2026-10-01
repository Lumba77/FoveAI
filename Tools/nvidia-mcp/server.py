#!/usr/bin/env python3
"""Zero-dependency MCP stdio server exposing NVIDIA NIM (integrate.api.nvidia.com)
chat models as a 'parallel brain' tool for Devin sessions.

Protocol: newline-delimited JSON-RPC 2.0 over stdin/stdout.
All logs go to stderr — stdout is protocol-only.

Config resolution order (first hit wins):
  1. FOVEAI_NVIDIA_API_KEY / NVIDIA_API_KEY env vars
  2. nearest .env walking up from this file containing FOVEAI_NVIDIA_API_KEY
URL/model likewise: env vars, then .env, then built-in defaults.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"
DEFAULT_MODEL = "moonshotai/kimi-k3"

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "nvidia-nim", "version": "1.0.0"}


def _log(msg: str) -> None:
    print(f"[nvidia-mcp] {msg}", file=sys.stderr, flush=True)


def _env_from_file() -> dict:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        env = parent / ".env"
        if not env.is_file():
            continue
        out = {}
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
        return out
    return {}


_FILE_ENV = _env_from_file()


def _cfg(name: str, default: str = "") -> str:
    return os.environ.get(name) or _FILE_ENV.get(name) or default


API_KEY = _cfg("FOVEAI_NVIDIA_API_KEY") or _cfg("NVIDIA_API_KEY")
API_URL = _cfg("FOVEAI_NVIDIA_URL", DEFAULT_API_URL)
MODELS_URL = (
    API_URL.rsplit("/chat/completions", 1)[0] + "/models"
    if "/chat/completions" in API_URL
    else DEFAULT_MODELS_URL
)
DEFAULT_MODEL = _cfg("FOVEAI_NVIDIA_MODEL", DEFAULT_MODEL)
DEFAULT_REASONING = _cfg("FOVEAI_NVIDIA_REASONING", "").lower()

TOOLS = [
    {
        "name": "nvidia_chat",
        "description": (
            "Send a prompt to an NVIDIA NIM hosted model (build.nvidia.com free tier) "
            "and return its reply. Use as a second opinion / parallel brain alongside "
            "the primary model. 80+ models available; call nvidia_list_models to see them."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The user message to send.",
                },
                "system": {"type": "string", "description": "Optional system prompt."},
                "model": {
                    "type": "string",
                    "description": f"Model id, e.g. 'moonshotai/kimi-k3', 'deepseek-ai/deepseek-v4-pro-0813', 'openai/gpt-oss-20b'. Default: {DEFAULT_MODEL}",
                },
                "reasoning_effort": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Thinking effort for reasoning models (kimi-k3, deepseek-v4). Omit for non-reasoning models.",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Completion cap. Default 4096.",
                    "default": 4096,
                },
                "temperature": {
                    "type": "number",
                    "description": "Sampling temperature. Default 0.4.",
                    "default": 0.4,
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "nvidia_list_models",
        "description": "List model ids available on the NVIDIA NIM endpoint with the configured key.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _post(url: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _text(s: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": s}], "isError": is_error}


def tool_chat(args: dict) -> dict:
    if not API_KEY:
        return _text("FOVEAI_NVIDIA_API_KEY is not set (env or .env).", True)
    body: dict = {
        "model": args.get("model") or DEFAULT_MODEL,
        "messages": (
            [{"role": "system", "content": args["system"]}]
            if args.get("system")
            else []
        )
        + [{"role": "user", "content": args["prompt"]}],
        "max_tokens": int(args.get("max_tokens") or 4096),
        "temperature": float(
            args.get("temperature") if args.get("temperature") is not None else 0.4
        ),
        "stream": False,
    }
    effort = args.get("reasoning_effort") or {"max": "high", "min": "low"}.get(
        DEFAULT_REASONING, DEFAULT_REASONING
    )
    if effort in ("low", "medium", "high"):
        body["reasoning_effort"] = effort
    try:
        data = _post(API_URL, body)
    except urllib.error.HTTPError as e:
        if e.code == 400 and "reasoning_effort" in body:
            body.pop("reasoning_effort")
            try:
                data = _post(API_URL, body)
            except urllib.error.HTTPError as e2:
                return _text(
                    f"NVIDIA API HTTP {e2.code}: {e2.read()[:500].decode(errors='replace')}",
                    True,
                )
        else:
            return _text(
                f"NVIDIA API HTTP {e.code}: {e.read()[:500].decode(errors='replace')}",
                True,
            )
    except Exception as e:
        return _text(f"NVIDIA API error: {e}", True)
    msg = data.get("choices", [{}])[0].get("message", {})
    parts = []
    if msg.get("reasoning_content"):
        parts.append(f"[reasoning]\n{msg['reasoning_content'].strip()}\n[/reasoning]")
    parts.append(msg.get("content") or "(empty content)")
    usage = data.get("usage") or {}
    if usage:
        parts.append(
            f"\n— model={data.get('model')} tokens={usage.get('total_tokens')}"
        )
    return _text("\n\n".join(parts))


def tool_list_models(_args: dict) -> dict:
    if not API_KEY:
        return _text("FOVEAI_NVIDIA_API_KEY is not set (env or .env).", True)
    try:
        req = urllib.request.Request(
            MODELS_URL, headers={"Authorization": f"Bearer {API_KEY}"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        ids = sorted(m["id"] for m in data.get("data", []))
        return _text("\n".join(ids) if ids else "(no models returned)")
    except Exception as e:
        return _text(f"NVIDIA API error: {e}", True)


HANDLERS = {"nvidia_chat": tool_chat, "nvidia_list_models": tool_list_models}


def respond(req_id, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    _log(f"ready model={DEFAULT_MODEL} key={'set' if API_KEY else 'MISSING'}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method", "")
        req_id = req.get("id")
        if req_id is None:  # notification
            continue
        if method == "initialize":
            respond(
                req_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            )
        elif method == "ping":
            respond(req_id, {})
        elif method == "tools/list":
            respond(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = req.get("params") or {}
            fn = HANDLERS.get(params.get("name", ""))
            if fn is None:
                respond(
                    req_id,
                    error={
                        "code": -32601,
                        "message": f"unknown tool {params.get('name')}",
                    },
                )
            else:
                try:
                    respond(req_id, fn(params.get("arguments") or {}))
                except Exception as e:
                    respond(req_id, _text(f"tool error: {e}", True))
        else:
            respond(
                req_id, error={"code": -32601, "message": f"method not found: {method}"}
            )


if __name__ == "__main__":
    main()
