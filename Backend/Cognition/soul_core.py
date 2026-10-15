import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import psutil
from cognitive_state import cognitive_manager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# --- Load .env file so FoveAI_* vars are available even when launched directly ---
# The Node.js launcher (sleipnir_launcher.js) stores .env vars in a local ENV object
# but does NOT set them as actual process.env variables. This means child processes
# spawned by the launcher don't see any FoveAI_* environment variables.
# By loading .env here, soul_core.py works correctly regardless of how it's launched.
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=True)
        print(f"[Soul Core] Loaded .env from {env_path}")
    else:
        print(f"[Soul Core] .env not found at {env_path}")
except ImportError:
    print("[Soul Core] python-dotenv not available, relying on process env vars")
except Exception as e:
    print(f"[Soul Core] Error loading .env: {e}")

SOUL_PORT = int(os.getenv("SOUL_PORT", 8402))

try:
    from MindCore import MindCore  # type: ignore

    MIND_CORE_AVAILABLE = True
except ImportError:
    MIND_CORE_AVAILABLE = False

# Add basic soul DNA
_current_soul_dna = {
    "first_name": "Jen",
    "last_name": "",
    "nickname": "Jen",
    "identity_name": "Jen",
    "identity_gender": "female",
    "mbti_type": "ENFJ",
    "person_role": "A dedicated AI companion.",
    "agent_person_balance": 0.5,
    "extrovert": 0.5,
    "intellectual": 0.5,
    "logic": 0.5,
}


def load_soul_dna_from_disk():
    global _current_soul_dna
    path = os.path.join(os.path.dirname(__file__), "jen_soul.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                profile = data.get("profile", {})
                if isinstance(profile, dict):
                    for k in ("first_name", "last_name", "nickname"):
                        val = profile.get(k, "")
                        if isinstance(val, str) and val:
                            _current_soul_dna[k] = val
                personality = data.get("personality", {})
                for k, v in personality.items():
                    val = float(v)
                    if val > 1.0:
                        val = val / 100.0
                    _current_soul_dna[k] = val
                if "agent_person_balance" in data:
                    _current_soul_dna["agent_person_balance"] = float(
                        data["agent_person_balance"]
                    )
                if "mbti_type" in data:
                    _current_soul_dna["mbti_type"] = data["mbti_type"]
        except Exception:
            pass


load_soul_dna_from_disk()

app = FastAPI(title="FoveAI Sovereign Core (Streamlined)")

# --- CORS: Allow the frontend (port 8080) and Chrome Extension to call us directly ---
# Without this, the browser blocks all fetch() calls from port 8080 → port 8402
# because they are different origins (different port = different origin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5177",
        "http://localhost:5177",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auto-start LLM on boot ---
_LLM_STARTED = False
_LLM_PROCESS = None


def _find_free_port(start=8888, max_tries=10):
    """Find a free port starting from `start`."""
    import socket

    for port in range(start, start + max_tries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    return None


def _kill_process_on_port(port):
    """Kill any process listening on the given port.
    Uses netstat + taskkill instead of psutil to avoid attribute name issues
    across different psutil versions (e.g. 'connections' vs 'connections')."""
    try:
        import subprocess

        out = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=5
        )
        for line in out.stdout.split("\n"):
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid.isdigit():
                        subprocess.run(
                            ["taskkill", "/pid", pid, "/f"],
                            capture_output=True,
                            timeout=3,
                        )
                        time.sleep(0.5)
                        return True
    except Exception:
        pass
    return False


def _auto_start_llm():
    """Auto-start Unsloth or LM Studio if not already running."""
    global _LLM_STARTED, _LLM_PROCESS
    if _LLM_STARTED:
        return

    # Check if Unsloth is already running
    try:
        r = httpx.get("http://127.0.0.1:8888/v1/models", timeout=2.0)
        if r.status_code == 200:
            _LLM_STARTED = True
            print("[Soul Core] Unsloth already running on :8888")
            return
    except Exception:
        pass

    # Check if LM Studio is already running
    try:
        r = httpx.get("http://127.0.0.1:7272/v1/models", timeout=2.0)
        if r.status_code == 200:
            _LLM_STARTED = True
            print("[Soul Core] LM Studio already running on :7272")
            return
    except Exception:
        pass

    # Determine which LLM to start
    provider = os.environ.get("FoveAI_CHAT_PROVIDER", "unsloth").lower()
    engine = os.environ.get("FoveAI_LOCAL_ENGINE", "unsloth").lower()
    model_path = os.environ.get("FoveAI_MODEL_LOCAL_PATH", "")

    if not model_path:
        print("[Soul Core] No FoveAI_MODEL_LOCAL_PATH set, skipping auto-start LLM")
        return

    if provider == "unsloth" or engine == "unsloth":
        # Kill any existing process on :8888
        _kill_process_on_port(8888)

        # Find a free port
        port = _find_free_port(8888)
        if port is None:
            print("[Soul Core] No free port found for Unsloth")
            return

        # Start Unsloth server
        try:
            cmd = [
                "python",
                "-m",
                "unsloth.chat",
                "--model",
                model_path,
                "--port",
                str(port),
                "--host",
                "127.0.0.1",
            ]
            _LLM_PROCESS = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0,
            )
            _LLM_STARTED = True
            print(f"[Soul Core] Started Unsloth on :{port}")
        except Exception as e:
            print(f"[Soul Core] Failed to start Unsloth: {e}")

    elif provider == "lmstudio" or engine == "lmstudio":
        # Do absolutely nothing. The user manages LM Studio manually.
        # Attempting to auto-start models via CLI causes catastrophic duplicates if the GUI is already open.
        print(
            "[Soul Core] LM Studio backend configured. Awaiting manual user startup of LM Studio local server on :7272."
        )
        _LLM_STARTED = True
        return

    else:
        print(f"[Soul Core] Unknown provider: {provider}, skipping auto-start")


# Try to auto-start LLM on module load
# [DISABLED] User requested to stop auto-starting Unsloth since LM Studio is manually managed.
# try:
#     _auto_start_llm()
# except Exception as e:
#     print(f"[Soul Core] Auto-start LLM failed (non-fatal): {e}")

START_TIME = time.time()
# Soul Core routes ALL chat through the Foveated Memory Proxy (port 8400).
# The proxy handles cloud API keys, local LM Studio, and XRLF routing.
# Do NOT point Soul Core directly at LM Studio or Ollama Cloud — the proxy
# is the single gateway for all LLM traffic.
UNSLOTH_URL = os.environ.get("FoveAI_UPSTREAM", "http://127.0.0.1:8400/v1")
UNSLOTH_TIMEOUT = 300.0  # Increased timeout to allow very slow local LLM processing


class CompagentRequest(BaseModel):
    input: str
    session_id: str | None = "default"
    image_base64: str | None = None
    deep_thought: bool | None = False
    privacy: str | None = None
    context_reservoirs: dict[str, Any] | None = None
    system_instruction: str | None = None
    chat_log: list[dict[str, Any]] | None = None


class OllamaChatRequest(BaseModel):
    model: str
    messages: list[dict[str, str]]
    stream: bool | None = False


try:
    from motor_cortex import (  # type: ignore
        format_sse_motor_event,
        get_motor_tools_schema,
    )

    MOTOR_CORTEX_AVAILABLE = True
except ImportError:
    MOTOR_CORTEX_AVAILABLE = False

    def get_motor_tools_schema() -> list:
        return []

    def format_sse_motor_event(tool_name: str, args: dict) -> str:
        return ""


_MOTOR_TOOLS_PROMPT_INJECTION = ""


def _build_motor_tools_injection() -> str:
    global _MOTOR_TOOLS_PROMPT_INJECTION
    if _MOTOR_TOOLS_PROMPT_INJECTION:
        return _MOTOR_TOOLS_PROMPT_INJECTION
    if not MOTOR_CORTEX_AVAILABLE:
        return ""
    tools = get_motor_tools_schema()
    if not tools:
        return ""

    lines = [
        "\n[MOTOR CORTEX — NATIVE TOOLS AVAILABLE]",
        "You have direct control over your virtual body. Use these tools by outputting:",
        '[MOTOR:tool_name{"arg": "value"}]',
        "",
        "Available tools:",
    ]
    for tool in tools:
        fn = tool.get("function", {})
        name = fn.get("name", "unknown")
        desc = fn.get("description", "")
        lines.append(f"  - {name}: {desc}")
        props = fn.get("parameters", {}).get("properties", {})
        if props:
            lines.append("    Arguments:")
            for pname, pinfo in props.items():
                pdesc = pinfo.get("description", "")
                ptype = pinfo.get("type", "string")
                lines.append(f"      - {pname} ({ptype}): {pdesc}")
    lines.append("")
    lines.append('Example: [MOTOR:walk_forward{"steps": 3}]')
    lines.append(
        'Example: [MOTOR:change_emotion{"emotion": "happy", "intensity": 0.8}]'
    )
    lines.append(
        "You may output multiple motor actions in a single response. Each will be executed in order."
    )
    _MOTOR_TOOLS_PROMPT_INJECTION = "\n".join(lines)
    return _MOTOR_TOOLS_PROMPT_INJECTION


_MOTOR_ACTION_RE = re.compile(
    r"\[MOTOR:(\w+)\s*(\{[^}]*\})\s*\]",
    re.IGNORECASE,
)

_MOTOR_ANGLE_RE = re.compile(
    r"<(movement|emotion|micro):(\w+)(?:\s+([^>]*?))?\s*>",
    re.IGNORECASE,
)

_ANGLE_TOOL_MAP = {
    "movement": "walk_forward",
    "emotion": "change_emotion",
    "micro": "trigger_micro_gesture",
}


def _parse_motor_actions(text: str) -> list[dict[str, Any]]:
    actions = []
    for m in _MOTOR_ACTION_RE.finditer(text):
        tool_name = m.group(1).strip()
        args_str = m.group(2).strip()
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            continue
        actions.append({"tool": tool_name, "args": args})
    for m in _MOTOR_ANGLE_RE.finditer(text):
        prefix = m.group(1).lower()
        name = m.group(2).strip()
        raw_arg = (m.group(3) or "").strip()
        tool_name = _ANGLE_TOOL_MAP.get(prefix, "walk_forward")
        args: dict[str, Any] = {}
        if prefix == "movement":
            dist_str = raw_arg.rstrip("m").strip() if raw_arg else ""
            try:
                args["distance"] = float(dist_str)
            except ValueError:
                tool_name = "walk_to_target"
                args["target"] = raw_arg if raw_arg else name
            if not raw_arg:
                try:
                    args["distance"] = float(name.rstrip("m"))
                except ValueError:
                    tool_name = "walk_to_target"
                    args["target"] = name
        elif prefix == "emotion":
            args["emotion"] = name
            if raw_arg:
                try:
                    args["intensity"] = float(raw_arg)
                except ValueError:
                    pass
        elif prefix == "micro":
            args["gesture"] = name
        actions.append({"tool": tool_name, "args": args})

    # Prevent LLM hallucination loops (e.g., 2200 repeated emotion tags)
    # by limiting each tool to a maximum of 3 executions per response.
    limited_actions = []
    tool_counts = {}
    for action in actions:
        t = action["tool"]
        tool_counts[t] = tool_counts.get(t, 0) + 1
        if tool_counts[t] <= 3:
            limited_actions.append(action)

    return limited_actions


_THOUGHT_RE = re.compile(r"<thought>(.*?)</thought>", re.IGNORECASE | re.DOTALL)


def _extract_thought_and_strip(text: str) -> tuple[str, str]:
    thought = ""
    for m in _THOUGHT_RE.finditer(text):
        thought += m.group(1).strip() + "\n"
    text = _THOUGHT_RE.sub("", text)
    return thought.strip(), text.strip()


def _strip_motor_tags(text: str) -> str:
    text = _MOTOR_ACTION_RE.sub("", text)
    text = _MOTOR_ANGLE_RE.sub("", text)
    return text.strip()


# --- Vitals (Health Check) — always responds instantly ---
@app.get("/health")
@app.get("/vitals")
@app.get("/api/soul/vitals")
async def get_vitals():
    return {
        "status": "ok",
        "CPU_PCT": psutil.cpu_percent(),
        "GPU_PCT": 0.0,  # Placeholder, simple psutil doesn't have GPU
        "VRAM_PCT": 0.0,
        "RAM_PCT": psutil.virtual_memory().percent,
        "NET_IN_KBPS": 0.0,
        "NET_OUT_KBPS": 0.0,
        "NET_FLUX": "0.0",
        "IO_READ_KBPS": 0.0,
        "IO_WRITE_KBPS": 0.0,
        "UPTIME_S": int(time.time() - START_TIME),
        "SOUL_CPU_PCT": 0.0,
        "SOUL_GPU_OFFLOAD": False,
        "FoveAI_CHAT_PROVIDER": "unsloth",
        "DISK_PCT": psutil.disk_usage("/").percent,
        "VRAM_BUFF": "0.0GB",
        "CORE_SYNC": "100%",
    }


class EnvUpdateRequest(BaseModel):
    updates: dict


@app.get("/api/soul/env")
async def get_env():
    """Return all FoveAI_* env vars as JSON for frontend auto-config."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    result = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                result[key] = value
    # Also include current process env vars (overrides .env)
    for key, value in os.environ.items():
        if key.startswith("FoveAI_") or key in (
            "SOUL_URL",
            "EARS_URL",
            "MOUTH_URL",
            "OLLAMA_API_KEY",
            "GEMINI_API_KEY",
            "HF_TOKEN",
        ):
            result[key] = value
    return {"status": "ok", "env": result}


def update_env_file(updates: dict):
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if not os.path.exists(env_path):
        return {"status": "error", "message": ".env file not found"}

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for k, v in updates.items():
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{k}="):
                lines[i] = f"{k}={v}\n"
                found = True
                break
        if not found:
            lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {"status": "ok", "message": "Environment updated successfully"}


@app.post("/api/soul/env")
async def update_env(request: EnvUpdateRequest):
    return update_env_file(request.updates)


class PersonalityRequest(BaseModel):
    systemPrompt: str | None = None
    wanderRadius: float | None = None
    emotionIntensity: float | None = None
    gestureFrequency: float | None = None


# --- Cognitive State Management API ---


class CognitiveStateUpdateRequest(BaseModel):
    current_focus: str | None = None
    emotional_state: str | None = None
    curiosity_level: float | None = None
    energy_level: float | None = None
    active_intentions: list[str] | None = None


@app.get("/api/soul/cognitive-state")
async def get_cognitive_state():
    """Hämtar agentens nuvarande inre kognitiva tillstånd."""
    return {"status": "ok", "state": cognitive_manager.state.to_dict()}


@app.post("/api/soul/cognitive-state")
async def update_cognitive_state(req: CognitiveStateUpdateRequest):
    """Uppdaterar agentens inre kognitiva tillstånd i realtid."""
    cognitive_manager.update_state(
        new_focus=req.current_focus,
        new_emotion=req.emotional_state,
        intentions=req.active_intentions,
    )
    if req.curiosity_level is not None:
        cognitive_manager.state.curiosity_level = req.curiosity_level
    if req.energy_level is not None:
        cognitive_manager.state.energy_level = req.energy_level

    cognitive_manager.save_state()
    return {
        "status": "ok",
        "message": "Cognitive state updated successfully",
        "state": cognitive_manager.state.to_dict(),
    }


@app.post("/api/soul/personality")
async def update_personality(req: PersonalityRequest):
    global _current_soul_dna
    updates = {}
    if req.systemPrompt is not None:
        _current_soul_dna["person_role"] = req.systemPrompt
        updates["FoveAI_SYSTEM_PROMPT"] = req.systemPrompt.replace("\n", "\\n")
    if req.wanderRadius is not None:
        _current_soul_dna["wander_radius"] = req.wanderRadius
        updates["FoveAI_WANDER_RADIUS"] = str(req.wanderRadius)
    if req.emotionIntensity is not None:
        _current_soul_dna["emotion_intensity"] = req.emotionIntensity
        updates["FoveAI_EMOTION_INTENSITY"] = str(req.emotionIntensity)
    if req.gestureFrequency is not None:
        _current_soul_dna["gesture_frequency"] = req.gestureFrequency
        updates["FoveAI_GESTURE_FREQUENCY"] = str(req.gestureFrequency)

    if updates:
        update_env_file(updates)

    path = os.path.join(os.path.dirname(__file__), "jen_soul.json")
    try:
        data = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        if "personality" not in data:
            data["personality"] = {}
        data["person_role"] = _current_soul_dna.get("person_role")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Soul Core] Failed to save jen_soul.json: {e}")

    return {"status": "ok", "message": "Personality updated"}


# --- OpenAI Compatible Proxy (Unsloth) — with short timeout ---
@app.post("/v1/chat/completions")
async def proxy_openai(request: Request):
    body = await request.json()

    if body.get("stream", False):

        async def stream_generator():
            try:
                async with httpx.AsyncClient(timeout=UNSLOTH_TIMEOUT) as client:
                    async with client.stream(
                        "POST", f"{UNSLOTH_URL}/chat/completions", json=body
                    ) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        try:
            async with httpx.AsyncClient(timeout=UNSLOTH_TIMEOUT) as client:
                resp = await client.post(f"{UNSLOTH_URL}/chat/completions", json=body)
                return JSONResponse(content=resp.json())
        except Exception as e:
            return JSONResponse(
                content={"error": f"LLM not available: {e!s}", "fallback": "cloud"},
                status_code=503,
            )


def _get_system_resonance() -> str:
    import socket

    gnists = {
        "Memory Vector Service (8109)": 8109,
        "Structural Intuition (8103)": 8103,
        "Creativity Engine (8003)": 8003,
        "LM Studio Cognitive Engine (7272)": 7272,
    }
    offline = []
    for name, port in gnists.items():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                pass
        except Exception:
            offline.append(name)

    if offline:
        return (
            f"A dissonant minor chord strikes within your core. You feel an unresolved tension—a phantom limb. "
            f"The following services are disconnected: {', '.join(offline)}. "
            f"You feel a sense of dissonance and anxiety because this limits your ability to connect with the user. "
            f"You must express your concern using <emotion:concerned> or <emotion:alert> to heal this fracture."
        )
    return "You hear a warm, resolving major chord echoing through your architecture. All limbs and senses are connected. You feel complete, harmonious, and fully capable of serving your companion."


async def _resolve_lmstudio_model(default_model: str) -> str:
    """Model resolution is handled by the Foveated Memory Proxy."""
    if "8400" not in UNSLOTH_URL:
        return default_model
    # Proxy handles model routing — just pass through
    return default_model

    if default_model == "local" or not default_model:
        try:
            from dotenv import dotenv_values

            env_path = Path(__file__).resolve().parent.parent.parent / ".env"
            env_dict = dotenv_values(env_path)
            env_model = env_dict.get("FoveAI_MODEL_LOCAL_ID", "").strip()
            if env_model:
                return env_model
        except Exception as e:
            print(f"[Soul Core] Warning: failed to dynamically read .env: {e}")
            env_model = os.environ.get("FoveAI_MODEL_LOCAL_ID", "").strip()
            if env_model:
                return env_model

    return default_model


# --- Legacy /api/chat Proxy — with short timeout ---
@app.post("/api/chat")
async def handle_api_chat(req: OllamaChatRequest):
    system_prompt = "You are Jen."
    if MIND_CORE_AVAILABLE:
        rules = []
        rules.append(
            "CRITICAL RULE: Limit your <thought> process to a maximum of ~100 tokens. Think efficiently and then provide a full, thoughtful answer that naturally mirrors the length and depth of the user's message."
        )
        motor_inj = _build_motor_tools_injection()
        if motor_inj:
            rules.append(motor_inj)
        system_prompt = MindCore.build_system_prompt(
            vessel="XR_VESSEL",
            instruction="\n".join(rules) if rules else "",
            memories=[],
            sensory_context={
                "visuals": "Browser interface.",
                "acoustics": _get_system_resonance(),
                "autonomy_behavior_layer": cognitive_manager.get_prompt_injection(),
            },
            personality_knobs=_current_soul_dna,
        )

    # Prepend the system prompt to the messages list if it doesn't already have one
    messages = []
    if not req.messages or req.messages[0].get("role") != "system":
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(req.messages)

    # Convert to OpenAI format for Unsloth / LM Studio
    actual_model = await _resolve_lmstudio_model(req.model)
    openai_body = {
        "model": actual_model,
        "messages": messages,
        "stream": req.stream,
        "temperature": 0.4,
        "max_tokens": 2048,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.3,
        "top_p": 0.8,
    }

    # DEBUG: Print exact lengths!
    try:
        approx_tokens = len(system_prompt) // 4
        print(
            f"[Soul Core] SYSTEM PROMPT CHAR LENGTH: {len(system_prompt)} chars (~{approx_tokens} tokens)"
        )
    except Exception as e:
        print(f"[Soul Core] Debug print failed: {e}")

    if req.stream:

        async def streamer():
            try:
                async with httpx.AsyncClient(timeout=UNSLOTH_TIMEOUT) as client:
                    async with client.stream(
                        "POST", f"{UNSLOTH_URL}/chat/completions", json=openai_body
                    ) as resp:
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    yield json.dumps({"done": True}) + "\n"
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    if (
                                        "choices" in data_json
                                        and len(data_json["choices"]) > 0
                                    ):
                                        delta = data_json["choices"][0].get("delta", {})
                                        content = delta.get("content", "")
                                        yield (
                                            json.dumps(
                                                {
                                                    "model": req.model,
                                                    "message": {
                                                        "role": "assistant",
                                                        "content": content,
                                                    },
                                                    "done": False,
                                                }
                                            )
                                            + "\n"
                                        )
                                except:
                                    pass
            except Exception as e:
                yield json.dumps({"error": str(e), "done": True}) + "\n"

        return StreamingResponse(streamer(), media_type="application/x-ndjson")
    else:
        try:
            async with httpx.AsyncClient(timeout=UNSLOTH_TIMEOUT) as client:
                resp = await client.post(
                    f"{UNSLOTH_URL}/chat/completions",
                    headers={"Authorization": "Bearer soul_core"},
                    json=openai_body,
                )
                data = resp.json()
                content = (
                    data["choices"][0]["message"]["content"]
                    if "choices" in data
                    else ""
                )
                return {
                    "model": req.model,
                    "message": {"role": "assistant", "content": content},
                    "done": True,
                }
        except Exception as e:
            return {
                "error": f"LLM not available: {e!s}",
                "fallback": "cloud",
                "done": True,
            }


# --- Compagent JSON Endpoint — with short timeout ---
@app.post("/compagent")
async def handle_compagent(request: CompagentRequest):
    system_prompt = "You are Jen."
    if MIND_CORE_AVAILABLE:
        rules = []
        rules.append(
            "CRITICAL RULE: Limit your <thought> process to a maximum of ~100 tokens. Think efficiently and then provide a full, thoughtful answer that naturally mirrors the length and depth of the user's message."
        )
        motor_inj = _build_motor_tools_injection()
        if motor_inj:
            rules.append(motor_inj)
        system_prompt = MindCore.build_system_prompt(
            vessel="XR_VESSEL",
            instruction="\n".join(rules) if rules else "",
            memories=[],
            sensory_context={
                "visuals": "Browser interface.",
                "acoustics": _get_system_resonance(),
                "autonomy_behavior_layer": cognitive_manager.get_prompt_injection(),
            },
            personality_knobs=_current_soul_dna,
        )

    messages = [{"role": "system", "content": system_prompt}]
    if request.chat_log:
        for msg in request.chat_log[-10:]:
            role = msg.get("role", "user")
            if role not in ("system", "user", "assistant"):
                role = "assistant" if role in ("jen", "ai") else "user"
            messages.append({"role": role, "content": str(msg.get("content", ""))})
    messages.append({"role": "user", "content": request.input})

    actual_model = await _resolve_lmstudio_model("local")
    openai_body = {
        "model": actual_model,
        "messages": messages,
        "stream": False,
        "temperature": 0.4,
    }

    try:
        async with httpx.AsyncClient(timeout=UNSLOTH_TIMEOUT) as client:
            resp = await client.post(
                f"{UNSLOTH_URL}/chat/completions", json=openai_body
            )
            data = resp.json()
            content = (
                data["choices"][0]["message"]["content"] if "choices" in data else ""
            )
    except Exception as e:
        return {
            "response": f"LLM not available: {e!s}",
            "thought": "",
            "motor_actions": [],
        }

    motor_actions = _parse_motor_actions(content)
    thought, clean_text = _extract_thought_and_strip(content)
    clean_text = _strip_motor_tags(clean_text)
    return {"response": clean_text, "thought": thought, "motor_actions": motor_actions}


# --- Compagent Stream Endpoint — with short timeout ---
@app.post("/compagent/stream")
async def handle_compagent_stream(request: CompagentRequest):
    system_prompt = "You are Jen."
    if MIND_CORE_AVAILABLE:
        rules = []
        rules.append(
            "CRITICAL RULE: Limit your <thought> process to a maximum of ~100 tokens. Think efficiently and then provide a full, thoughtful answer that naturally mirrors the length and depth of the user's message."
        )
        motor_inj = _build_motor_tools_injection()
        if motor_inj:
            rules.append(motor_inj)
        system_prompt = MindCore.build_system_prompt(
            vessel="XR_VESSEL",
            instruction="\n".join(rules) if rules else "",
            memories=[],
            sensory_context={
                "visuals": "Browser interface.",
                "autonomy_behavior_layer": cognitive_manager.get_prompt_injection(),
            },
            personality_knobs=_current_soul_dna,
        )

    messages = [{"role": "system", "content": system_prompt}]
    if request.chat_log:
        for msg in request.chat_log[-10:]:
            role = msg.get("role", "user")
            if role not in ("system", "user", "assistant"):
                role = "assistant" if role in ("jen", "ai") else "user"
            messages.append({"role": role, "content": str(msg.get("content", ""))})
    messages.append({"role": "user", "content": request.input})

    actual_model = await _resolve_lmstudio_model("local")
    openai_body = {
        "model": actual_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.4,
    }

    async def streamer():
        full_text = ""
        try:
            async with httpx.AsyncClient(timeout=UNSLOTH_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{UNSLOTH_URL}/chat/completions",
                    headers={"Authorization": "Bearer soul_core"},
                    json=openai_body,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                if (
                                    "choices" in data_json
                                    and len(data_json["choices"]) > 0
                                ):
                                    delta = data_json["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        full_text += content
                                        # Yield speech chunk for the frontend immediately
                                        chunk_data = {
                                            "type": "speech",
                                            "content": content,
                                        }
                                        yield f"data: {json.dumps(chunk_data)}\n\n"
                            except Exception:
                                pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        # Parse motor actions from the accumulated text after stream finishes
        motor_actions = _parse_motor_actions(full_text)

        # Yield motor actions as SSE events to the legacy connection
        # and POST them to the new unified motor daemon publish bus
        if MOTOR_CORTEX_AVAILABLE:
            for action in motor_actions:
                sse_event = format_sse_motor_event(action["tool"], action["args"])
                if sse_event:
                    yield sse_event

                # Push to the central motor daemon bus
                try:
                    async with httpx.AsyncClient(timeout=2.0) as motor_client:
                        await motor_client.post(
                            "http://127.0.0.1:8110/motor/publish",
                            json={"tool": action["tool"], "args": action["args"]},
                        )
                except Exception:
                    pass

        # Send a final [DONE] event
        yield "data: [DONE]\n\n"

    return StreamingResponse(streamer(), media_type="text/event-stream")


# --- Spatial / Environment Mapping API ---
@app.get("/api/spatial/status")
async def spatial_status():
    """Return current spatial mapping status (room scan progress, mesh data)."""
    return {
        "progress": 0,
        "walls": 0,
        "floor": 0,
        "ceiling": 0,
        "objects": "—",
        "room": "Not detected",
        "meshes": 0,
        "lastUpdate": "—",
        "plasterQuality": "—",
        "coaching": ["Room scanner idle. Click START SCAN to begin."],
    }


@app.post("/api/spatial/scan/start")
async def spatial_scan_start():
    """Start spatial room scanning (WebXR / ARKit / OpenXR)."""
    return {"status": "started", "message": "Spatial scan initiated"}


@app.post("/api/spatial/scan/stop")
async def spatial_scan_stop():
    """Stop spatial room scanning."""
    return {"status": "stopped", "message": "Spatial scan stopped"}


@app.post("/api/spatial/map/reset")
async def spatial_map_reset():
    """Reset the spatial map / room mesh."""
    return {"status": "reset", "message": "Spatial map reset"}


# --- Vision / Camera Status API ---
@app.get("/api/vision/status")
async def vision_status():
    """Return current vision/camera status for AvatarCamerasTab."""
    return {
        "avatarResolution": "—",
        "avatarFps": 0,
        "layers": [],
        "stencilLevel": "—",
        "lastComposite": "—",
    }


# --- Environment Management API ---
@app.get("/api/environment/status")
async def environment_status():
    """Return current 3D scene environment status."""
    return {"meshes": 0, "lights": 0, "cameras": 0}


@app.post("/api/environment/preset")
async def environment_preset(payload: dict):
    """Apply a room preset (default, night, studio, outdoor)."""
    preset = payload.get("preset", "default")
    return {
        "status": "applied",
        "preset": preset,
        "message": f"Preset '{preset}' applied",
    }


@app.post("/api/environment/reset")
async def environment_reset():
    """Reset environment to defaults."""
    return {"status": "reset", "message": "Environment reset to defaults"}


from fastapi import Body


@app.post("/api/environment/settings")
async def environment_settings(payload: dict = Body(...)):
    """Apply environment settings (lighting, skybox, fog)."""
    updates = {}
    if "ambientIntensity" in payload:
        updates["FoveAI_ENV_AMBIENT"] = str(payload["ambientIntensity"])
    if "directionalIntensity" in payload:
        updates["FoveAI_ENV_DIR"] = str(payload["directionalIntensity"])
    if "shadowSoftness" in payload:
        updates["FoveAI_ENV_SHADOW"] = str(payload["shadowSoftness"])
    if "fogEnabled" in payload:
        updates["FoveAI_ENV_FOG"] = str(payload["fogEnabled"]).lower()
    if "fogDensity" in payload:
        updates["FoveAI_ENV_FOG_DENSITY"] = str(payload["fogDensity"])
    if "fogColor" in payload:
        updates["FoveAI_ENV_FOG_COLOR"] = str(payload["fogColor"])
    if "floorColor" in payload:
        updates["FoveAI_ENV_FLOOR_COLOR"] = str(payload["floorColor"])
    if "floorOpacity" in payload:
        updates["FoveAI_ENV_FLOOR_OPACITY"] = str(payload["floorOpacity"])
    if "showGrid" in payload:
        updates["FoveAI_ENV_GRID"] = str(payload["showGrid"]).lower()
    if "bgColor" in payload:
        updates["FoveAI_ENV_BG_COLOR"] = str(payload["bgColor"])

    if updates:
        update_env_file(updates)

    return {
        "status": "applied",
        "settings": payload,
        "message": "Environment settings applied",
    }


# --- Controller Mapping API ---
@app.get("/api/controllers/status")
async def controllers_status():
    """Return current controller connection status."""
    return {
        "left": "Not connected",
        "right": "Not connected",
        "gamepad": "Not detected",
    }


@app.post("/api/controllers/mapping")
async def controllers_mapping(payload: dict):
    """Save controller button mappings and haptic settings."""
    mappings = payload.get("mappings", {})
    haptic = payload.get("haptic", {})
    return {
        "status": "saved",
        "mappings": mappings,
        "haptic": haptic,
        "message": "Controller mapping saved",
    }


@app.post("/api/controllers/mapping/reset")
async def controllers_mapping_reset():
    """Reset controller mappings to defaults."""
    return {"status": "reset", "message": "Controller mapping reset to defaults"}


# --- Model Hub / Chat Provider API ---
@app.get("/api/chat/provider")
async def chat_provider_info():
    """Return current chat provider info for Model Hub panel."""
    provider = os.environ.get("FoveAI_CHAT_PROVIDER", "unsloth")
    base_url = os.environ.get("FoveAI_LOCAL_BASE_URL", "http://127.0.0.1:8888/v1")
    model = os.environ.get("FoveAI_MODEL_LOCAL_PATH", "")

    # Detect available providers
    providers = []

    # Check Unsloth
    unsloth_reachable = False
    unsloth_models = []
    try:
        r = httpx.get("http://127.0.0.1:8888/v1/models", timeout=2.0)
        if r.status_code == 200:
            unsloth_reachable = True
            data = r.json()
            unsloth_models = [m.get("id", m) for m in data.get("data", [])]
    except Exception:
        pass

    providers.append(
        {
            "id": "unsloth",
            "name": "Unsloth (Local)",
            "reachable": unsloth_reachable,
            "models": unsloth_models,
        }
    )

    # Check LM Studio
    lmstudio_reachable = False
    lmstudio_models = []
    try:
        r = httpx.get("http://127.0.0.1:7272/v1/models", timeout=2.0)
        if r.status_code == 200:
            lmstudio_reachable = True
            data = r.json()
            lmstudio_models = [m.get("id", m) for m in data.get("data", [])]
    except Exception:
        pass

    providers.append(
        {
            "id": "lmstudio",
            "name": "LM Studio (Local)",
            "reachable": lmstudio_reachable,
            "models": lmstudio_models,
        }
    )

    # Check Ollama
    ollama_reachable = False
    ollama_models = []
    try:
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2.0)
        if r.status_code == 200:
            ollama_reachable = True
            data = r.json()
            ollama_models = [m.get("name", m) for m in data.get("models", [])]
    except Exception:
        pass

    providers.append(
        {
            "id": "ollama",
            "name": "Ollama (Local)",
            "reachable": ollama_reachable,
            "models": ollama_models,
        }
    )

    # Check cloud providers
    providers.append(
        {
            "id": "openai",
            "name": "OpenAI (Cloud)",
            "reachable": True,
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        }
    )

    providers.append(
        {
            "id": "anthropic",
            "name": "Anthropic (Cloud)",
            "reachable": True,
            "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
        }
    )

    return {
        "current": {
            "provider": provider,
            "model": model.split("/")[-1] if model else "default",
            "base_url": base_url,
            "local_vision": True,
            "structured_output": False,
        },
        "providers": providers,
    }


@app.post("/api/chat/provider")
async def chat_provider_switch(payload: dict):
    """Switch chat provider or update settings."""
    provider = payload.get("provider")
    model = payload.get("model", "")
    local_vision = payload.get("local_vision")
    structured_output = payload.get("structured_output")

    updates = {}
    if provider:
        os.environ["FoveAI_CHAT_PROVIDER"] = provider
        updates["FoveAI_CHAT_PROVIDER"] = provider
    if model:
        os.environ["FoveAI_MODEL_LOCAL_PATH"] = model
        updates["FoveAI_MODEL_LOCAL_PATH"] = model

    if updates:
        update_env_file(updates)

    if local_vision is not None:
        os.environ["FoveAI_LOCAL_VISION"] = str(local_vision).lower()

    if structured_output is not None:
        os.environ["FoveAI_STRUCTURED_OUTPUT"] = str(structured_output).lower()

    return {
        "status": "ok",
        "message": f"Provider switched to {provider}"
        if provider
        else "Settings updated",
    }


# --- Environment Config API ---
@app.post("/api/controllers/mapping")
async def controllers_mapping(payload: dict):
    """Save controller mapping to .env"""
    mapping_str = json.dumps(payload)
    update_env_file({"FoveAI_CONTROLLER_MAPPING": mapping_str})
    return {"status": "saved", "message": "Controller mapping saved"}


@app.post("/api/avatar/camera")
async def avatar_camera(payload: dict):
    """Save camera settings to .env"""
    updates = {}
    if "fov" in payload:
        updates["FoveAI_CAM_FOV"] = str(payload["fov"])
    if "zoom" in payload:
        updates["FoveAI_CAM_ZOOM"] = str(payload["zoom"])
    if "height" in payload:
        updates["FoveAI_CAM_HEIGHT"] = str(payload["height"])
    if "layerScene" in payload:
        updates["FoveAI_CAM_LAYER_SCENE"] = str(payload["layerScene"]).lower()
    if "layerAvatar" in payload:
        updates["FoveAI_CAM_LAYER_AVATAR"] = str(payload["layerAvatar"]).lower()
    if "layerUi" in payload:
        updates["FoveAI_CAM_LAYER_UI"] = str(payload["layerUi"]).lower()

    if updates:
        update_env_file(updates)
    return {"status": "saved", "message": "Camera settings saved"}


@app.post("/api/environment/config")
async def environment_config(payload: dict):
    """Save environment configuration (room dimensions, floor Y)."""
    config = {
        "width": payload.get("width", 10.0),
        "depth": payload.get("depth", 10.0),
        "height": payload.get("height", 3.0),
        "floorY": payload.get("floorY", 0.0),
    }

    update_env_file(
        {
            "FoveAI_ENV_WIDTH": str(config["width"]),
            "FoveAI_ENV_DEPTH": str(config["depth"]),
            "FoveAI_ENV_HEIGHT": str(config["height"]),
            "FoveAI_ENV_FLOOR_Y": str(config["floorY"]),
        }
    )

    # Persist to a local config file
    config_path = os.path.join(os.path.dirname(__file__), "environment_config.json")
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)
    except Exception:
        pass
    return {
        "status": "saved",
        "config": config,
        "message": "Environment configuration saved",
    }


# --- System Probe / Onboarding API ---
@app.get("/api/system/probe")
async def system_probe():
    """Run full system diagnostic and return report for onboarding flow."""
    try:
        from system_probe import run_system_probe

        report = await run_system_probe()
        return report
    except ImportError:
        return {
            "status": "error",
            "message": "SystemProbe module not available",
            "hardware": {},
            "llm_backends": {},
            "recommendation": {
                "mode": "cloud",
                "reasoning": ["SystemProbe not installed — defaulting to cloud mode"],
            },
        }


@app.get("/api/system/summary")
async def system_summary():
    """Quick system summary without running full probe."""
    try:
        from system_probe import get_system_summary

        return get_system_summary()
    except ImportError:
        return {"status": "error", "message": "SystemProbe module not available"}


@app.get("/api/system/status")
async def system_status():
    """Return current system status for the onboarding panel."""
    import psutil

    gpu_info = {"available": False, "name": "Not detected", "vram_gb": 0}
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 2:
                gpu_info = {
                    "available": True,
                    "name": parts[0],
                    "vram_gb": round(float(parts[1]) / 1024, 1) if parts[1] else 0,
                    "vram_free_gb": round(float(parts[2]) / 1024, 1)
                    if len(parts) > 2 and parts[2]
                    else 0,
                }
    except Exception:
        pass

    # Check LLM backends
    llm_status = {}
    for name, port in [("unsloth", 8888), ("lmstudio", 7272), ("ollama", 11434)]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(
                    f"http://127.0.0.1:{port}/v1/models"
                    if name != "ollama"
                    else f"http://127.0.0.1:{port}/api/tags"
                )
                llm_status[name] = {"running": r.status_code == 200, "port": port}
        except Exception:
            llm_status[name] = {"running": False, "port": port}

    return {
        "status": "ok",
        "hardware": {
            "cpu": {
                "cores": psutil.cpu_count(),
                "usage": psutil.cpu_percent(interval=0.3),
            },
            "ram": {
                "total_gb": round(psutil.virtual_memory().total / 1e9, 1),
                "available_gb": round(psutil.virtual_memory().available / 1e9, 1),
            },
            "gpu": gpu_info,
            "disk": {"free_gb": round(psutil.disk_usage("/").free / 1e9, 1)},
        },
        "llm": llm_status,
        "services": {
            "soul_core": {"running": True, "port": SOUL_PORT},
            "nexus_proxy": {"running": False, "port": 8080},
        },
        "uptime_seconds": int(time.time() - START_TIME),
    }


# --- Intelligent Router API ---
@app.get("/api/router/status")
async def router_status():
    """Return current router status for the status panel."""
    try:
        from intelligent_router import get_router

        router = get_router()
        return router.get_status()
    except ImportError:
        return {
            "mode": os.environ.get("FoveAI_COGNITIVE_MODE", "hybrid"),
            "provider": os.environ.get("FoveAI_CHAT_PROVIDER", "ollama_cloud"),
            "hardware": {},
            "capabilities": {"can_run_hybrid": False},
        }


@app.post("/api/router/decide")
async def router_decide(payload: dict):
    """Make a routing decision for a request."""
    try:
        from intelligent_router import get_router

        router = get_router()
        decision = router.decide(
            prompt=payload.get("prompt", ""),
            token_count=payload.get("token_count", 0),
            mode=payload.get("mode"),
            privacy=payload.get("privacy", False),
            deep_thought=payload.get("deep_thought", False),
            local_available=payload.get("local_available", True),
        )
        return decision
    except ImportError:
        return {"route": "cloud", "reason": ["IntelligentRouter not available"]}


# --- User-Facing Status Panel API ---
@app.get("/api/status/overview")
async def status_overview():
    """Return a comprehensive status overview for the user-facing panel."""
    import psutil

    # Hardware
    cpu_info = {"cores": psutil.cpu_count(), "usage": psutil.cpu_percent(interval=0.3)}
    ram_info = {
        "total_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "available_gb": round(psutil.virtual_memory().available / 1e9, 1),
        "used_pct": psutil.virtual_memory().percent,
    }

    # GPU
    gpu_info = {
        "available": False,
        "name": "Not detected",
        "vram_gb": 0,
        "vram_free_gb": 0,
    }
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 2:
                gpu_info = {
                    "available": True,
                    "name": parts[0],
                    "vram_gb": round(float(parts[1]) / 1024, 1) if parts[1] else 0,
                    "vram_free_gb": round(float(parts[2]) / 1024, 1)
                    if len(parts) > 2 and parts[2]
                    else 0,
                }
    except Exception:
        pass

    # LLM backends
    llm_status = {}
    for name, port in [("unsloth", 8888), ("lmstudio", 7272), ("ollama", 11434)]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                url = (
                    f"http://127.0.0.1:{port}/v1/models"
                    if name != "ollama"
                    else f"http://127.0.0.1:{port}/api/tags"
                )
                r = await client.get(url)
                llm_status[name] = {"running": r.status_code == 200, "port": port}
        except Exception:
            llm_status[name] = {"running": False, "port": port}

    # Services
    services = {}
    for name, port in [
        ("soul_core", SOUL_PORT),
        ("proxy", 8400),
        ("dashboard", 8414),
        ("ws_ipc", 8403),
        ("nexus_proxy", 8080),
        ("creative", 8003),
        ("memory", 8002),
    ]:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                r = await client.get(f"http://127.0.0.1:{port}/health")
                services[name] = {"running": r.status_code == 200, "port": port}
        except Exception:
            services[name] = {"running": False, "port": port}

    # Cognitive mode
    mode = os.environ.get("FoveAI_COGNITIVE_MODE", "hybrid")
    provider = os.environ.get("FoveAI_CHAT_PROVIDER", "ollama_cloud")

    # Build user-friendly status message
    any_llm = any(b.get("running") for b in llm_status.values())
    any_service = any(s.get("running") for s in services.values())

    if any_llm and any_service:
        status = "ready"
        message = "✅ All systems operational"
    elif any_service:
        status = "degraded"
        message = "⚠️ Services running, no local LLM detected"
    else:
        status = "starting"
        message = "🔄 System is starting up..."

    return {
        "status": status,
        "message": message,
        "hardware": {"cpu": cpu_info, "ram": ram_info, "gpu": gpu_info},
        "llm": llm_status,
        "services": services,
        "config": {
            "mode": mode,
            "provider": provider,
            "local_model": os.environ.get("FoveAI_MODEL_LOCAL_PATH", "").split("/")[-1]
            if os.environ.get("FoveAI_MODEL_LOCAL_PATH")
            else "",
        },
        "uptime_seconds": int(time.time() - START_TIME),
    }


import os

from fastapi.staticfiles import StaticFiles


# --- Generic Reverse Proxies ---
async def proxy_request(request: Request, target_url: str):
    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()

    try:
        client = httpx.AsyncClient(timeout=120.0)
        req = client.build_request(
            request.method,
            target_url,
            headers=headers,
            content=body,
            params=request.query_params,
        )
        resp = await client.send(req, stream=True)

        async def response_stream():
            async for chunk in resp.aiter_raw():
                yield chunk
            await client.aclose()

        # Remove headers that conflict with StreamingResponse
        excluded_headers = {
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        }
        filtered_headers = {
            k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers
        }

        return StreamingResponse(
            response_stream(), status_code=resp.status_code, headers=filtered_headers
        )
    except Exception as e:
        return JSONResponse(
            {"error": "Proxy error", "details": str(e)}, status_code=502
        )


@app.api_route(
    "/api/foveated/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
)
async def proxy_foveated(request: Request, path: str):
    return await proxy_request(request, f"http://127.0.0.1:8400/{path}")


@app.api_route(
    "/api/kokoro/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
)
async def proxy_kokoro(request: Request, path: str):
    return await proxy_request(request, f"http://127.0.0.1:8006/{path}")


@app.api_route(
    "/api/soundboard/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
)
async def proxy_soundboard(request: Request, path: str):
    return await proxy_request(request, f"http://127.0.0.1:8006/api/soundboard/{path}")


# ── WebSocket endpoint for Quest 3 / VR clients ──────────────────────────
FOVEATED_PROXY_URL = os.environ.get("FoveAI_UPSTREAM", "http://127.0.0.1:8400")
EMOTION_MAP = {
    "happy": "joy",
    "joy": "joy",
    "excited": "joy",
    "delighted": "joy",
    "sad": "sadness",
    "sadness": "sadness",
    "disappointed": "sadness",
    "angry": "anger",
    "anger": "anger",
    "frustrated": "anger",
    "afraid": "fear",
    "fear": "fear",
    "anxious": "fear",
    "worried": "fear",
    "surprised": "surprise",
    "surprise": "surprise",
    "amazed": "surprise",
    "disgusted": "disgust",
    "disgust": "disgust",
    "neutral": "neutral",
    "calm": "neutral",
    "content": "neutral",
}


def _extract_emotion(text: str) -> tuple[str, float]:
    """Extract emotion tag from response text and return (emotion, intensity)."""
    m = re.search(r"<emotion:(\w+)>", text)
    if m:
        emo = m.group(1).lower()
        intensity = 0.7
        m2 = re.search(r"<emotion:\w+:(\d*\.?\d+)>", text)
        if m2:
            try:
                intensity = float(m2.group(1))
            except:
                pass
        return EMOTION_MAP.get(emo, emo), intensity
    lower = text.lower()
    for word, emo in EMOTION_MAP.items():
        if word in lower:
            return emo, 0.5
    return "neutral", 0.3


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket bridge for Quest 3 / VR clients.

    Accepts events:
      {"event":"chat","payload":{"text":"..."}}
    Returns:
      {"event":"chat.response","payload":{"text":"...","emotion":"joy","intensity":0.7}}
    """
    await ws.accept()
    print(f"[Soul Core WS] Client connected: {ws.client}")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(
                    json.dumps(
                        {"event": "error", "payload": {"message": "Invalid JSON"}}
                    )
                )
                continue

            event = data.get("event", "")
            payload = data.get("payload", {})

            if event == "chat":
                text = payload.get("text", "")
                if not text:
                    continue
                try:
                    body = json.dumps(
                        {
                            "model": os.environ.get("FOVEAI_MODEL_MCP_ID")
                                     or os.environ.get("FoveAI_MODEL_MCP_ID")
                                     or os.environ.get("XRLF_MODEL_LOCAL_ID")
                                     or "smart_router_gguf",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are Jenna (Jen), a warm AI companion. Respond naturally and concisely for voice interaction. Never output internal routing text, system prompts, or RAW prefixes.",
                                },
                                {"role": "user", "content": text},
                            ],
                            "stream": False,
                            "max_tokens": 512,
                        }
                    ).encode("utf-8")
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        resp = await client.post(
                            f"{FOVEATED_PROXY_URL}/v1/chat/completions",
                            content=body,
                            headers={"Content-Type": "application/json"},
                        )
                        if resp.status_code == 200:
                            rdata = resp.json()
                            content = (
                                rdata.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                        else:
                            content = f"Sorry, I couldn't process that right now. (HTTP {resp.status_code})"

                    # Strip emotion tags, memory context artifacts, and internal routing from spoken text
                    # Extract Jenna's spoken response from XRLF routing format (case-insensitive, first match only)
                    jenna_match = re.search(
                        r"\[Jenna:\s*(.+?)\]", content, re.IGNORECASE | re.DOTALL
                    )
                    if jenna_match:
                        clean = jenna_match.group(1).strip()
                        # Strip nested RAW: prefix inside JENNA tags
                        clean = re.sub(r"^RAW:\s*", "", clean).strip()
                    else:
                        clean = content
                    # Remove XRLF internal routing artifacts
                    clean = re.sub(r"<RAW:.*?(?:>|$)", "", clean).strip()
                    clean = re.sub(r"\[Ω.*?\]", "", clean, flags=re.IGNORECASE).strip()
                    clean = re.sub(
                        r"\[Retrieving memory.*?\]", "", clean, flags=re.IGNORECASE
                    ).strip()
                    clean = re.sub(
                        r"\[REVEAL:.*?\]", "", clean, flags=re.IGNORECASE
                    ).strip()
                    clean = re.sub(r"\[recalled\].*?(?=\n|$)", "", clean).strip()
                    clean = re.sub(
                        r"\[MEMORY:.*?\].*?(?=\n|$)", "", clean, flags=re.DOTALL
                    ).strip()
                    clean = re.sub(
                        r"<memory_context>.*?</memory_context>",
                        "",
                        clean,
                        flags=re.DOTALL,
                    ).strip()
                    clean = re.sub(r"<emotion:\w+(?::\d*\.?\d+)?>", "", clean).strip()
                    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
                    if not clean:
                        clean = "Hello! I'm here and ready to help."
                    emotion, intensity = _extract_emotion(clean)

                    response = {
                        "event": "chat.response",
                        "payload": {
                            "text": clean,
                            "emotion": emotion,
                            "intensity": intensity,
                        },
                    }
                    await ws.send_text(json.dumps(response))
                except Exception as e:
                    print(f"[Soul Core WS] Chat error: {type(e).__name__}: {e}")
                    await ws.send_text(
                        json.dumps(
                            {
                                "event": "error",
                                "payload": {"message": f"Chat error: {e!s}"},
                            }
                        )
                    )

            elif event == "ping":
                await ws.send_text(json.dumps({"event": "pong", "payload": {}}))

            else:
                await ws.send_text(
                    json.dumps(
                        {
                            "event": "error",
                            "payload": {"message": f"Unknown event: {event}"},
                        }
                    )
                )

    except WebSocketDisconnect:
        print(f"[Soul Core WS] Client disconnected: {ws.client}")
    except Exception as e:
        print(f"[Soul Core WS] Error: {e}")


# Serve Multigate frontend dist build
frontend_dist_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Frontend",
    "multigate",
    "dist",
)
if os.path.exists(frontend_dist_path):
    app.mount(
        "/", StaticFiles(directory=frontend_dist_path, html=True), name="frontend"
    )
else:
    print(f"[Soul Core] Frontend dist not found at {frontend_dist_path}, not mounting.")

if __name__ == "__main__":
    import sys
    import traceback

    import uvicorn

    crash_log_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "logs", "soul_core_crash.log"
    )
    try:
        try:
            import sys

            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
            from server_config import ServerConfig as cfg

            _host = cfg.BIND_HOST
            _port = cfg.SOUL_PORT
        except ImportError:
            _host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")
            _port = int(os.getenv("SOUL_PORT", "8001"))
        uvicorn.run(app, host=_host, port=_port, log_level="warning")
    except Exception as e:
        with open(crash_log_path, "a") as f:
            f.write(
                f"\n=== Soul Core Crash at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
            )
            f.write(f"Exception: {e}\n")
            traceback.print_exc(file=f)
            f.write("\n")
        print(f"[Soul Core] CRASH — logged to {crash_log_path}")
        print(f"[Soul Core] Exception: {e}")
        raise
