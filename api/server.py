"""
api/server.py — OpenAI-Compatible REST API for XRLF
====================================================
Exposes the XRLFRuntime as an OpenAI-compatible endpoint.
Point LM Studio, Open WebUI, Antigravity, or any OpenAI SDK at:

    http://localhost:8400/v1

Endpoints:
  GET  /health
  GET  /v1/models
  POST /v1/chat/completions   (streaming + non-streaming)
  POST /v1/completions

Usage:
  python api/server.py --model gemma-4-12b-xrl.xrlf --port 8400
"""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
    import uvicorn
    from pydantic import BaseModel
    _FASTAPI = True
except ImportError:
    _FASTAPI = False

from runtime.xrlf_runtime import XRLFRuntime


# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: Any   # str or list (multimodal)

class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = None
    stream: Optional[bool] = False
    # XRLF extensions
    xrlf_force_profile: Optional[str] = None

class CompletionRequest(BaseModel):
    model: str = ""
    prompt: str
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False


def _normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge any leading/standalone system messages into the first user message.

    Some XRLF runtimes (llama.cpp-based) do not accept a separate `system` role
    and raise an embedding shape error. This keeps the instructions but only
    sends the runtime roles it understands.
    """
    if not messages:
        return messages

    system_parts = []
    others = []
    for m in messages:
        if m.get("role") == "system":
            system_parts.append(str(m.get("content", "")))
        else:
            others.append(m)

    if system_parts and others:
        # Prepend the collected system prompt to the first user message
        first = others[0]
        if first.get("role") == "user":
            first = {
                **first,
                "content": "[SYSTEM]\n" + "\n".join(system_parts) + "\n[USER]\n" + str(first.get("content", "")),
            }
            return [first] + others[1:]

    return others


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(runtime: XRLFRuntime) -> "FastAPI":
    if not _FASTAPI:
        raise RuntimeError("fastapi + uvicorn not installed. Run: pip install fastapi uvicorn[standard]")

    app = FastAPI(
        title="XRLF Runtime API",
        version="1.0.0",
        description="OpenAI-compatible API for XRLF hybrid models",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        load_state = getattr(runtime, "load_state", "ready" if runtime.loaded else "idle")
        return {
            "status": "ok",
            "model": runtime.model_name,
            "runtime": "xrlf-1.0",
            "loaded": runtime.loaded,
            "loading": load_state == "loading",
            "load_state": load_state,
            "load_error": getattr(runtime, "load_error", None),
        }

    # ── SoftLayer: serve hot-reloadable JS modules ────────────────────────────
    softlayer_dir = Path(__file__).parent.parent / "softlayer"

    @app.get("/softlayer/{module_name}.js")
    async def get_softlayer_module(module_name: str):
        js_file = softlayer_dir / f"{module_name}.js"
        if not js_file.exists():
            raise HTTPException(status_code=404, detail=f"Module '{module_name}' not found")
        source = js_file.read_text(encoding="utf-8")
        return PlainTextResponse(source, media_type="application/javascript")

    @app.get("/softlayer")
    async def list_softlayer_modules():
        modules = []
        if softlayer_dir.exists():
            modules = [f.stem for f in softlayer_dir.glob("*.js")]
        return {"modules": modules}

    # ── SoftLayer modules (modular environment control) ───────────────────────
    modules_dir = softlayer_dir / "modules"

    @app.get("/softlayer/modules/{module_name}.js")
    async def get_softlayer_module_file(module_name: str):
        js_file = modules_dir / f"{module_name}.js"
        if not js_file.exists():
            raise HTTPException(status_code=404, detail=f"Module '{module_name}' not found")
        source = js_file.read_text(encoding="utf-8")
        return PlainTextResponse(source, media_type="application/javascript")

    @app.get("/softlayer/modules")
    async def list_softlayer_module_files():
        mods = []
        if modules_dir.exists():
            mods = [f.stem for f in modules_dir.glob("*.js")]
        return {"modules": mods}

    # ── Memory planner status ─────────────────────────────────────────────────
    @app.get("/memory/status")
    async def memory_status():
        """Get dynamic VRAM/RAM tiling status from the memory planner."""
        if hasattr(runtime, 'get_memory_status'):
            return runtime.get_memory_status()
        return {"error": "Memory planner not available"}

    # ── Soul bridge status ────────────────────────────────────────────────────
    @app.get("/soul/status")
    async def soul_status():
        """Get Alice's soul and cognitive state."""
        if hasattr(runtime, '_soul') and runtime._soul:
            return runtime._soul.get_status()
        return {"error": "Soul bridge not available"}

    # ── Models ────────────────────────────────────────────────────────────────

    @app.post("/unload")
    async def unload_model():
        """Unload the current model from VRAM without killing the runtime process."""
        if getattr(runtime, "load_state", "idle") == "loading":
            raise HTTPException(status_code=409, detail="Model load in progress — wait or restart the runtime")
        if not runtime.loaded:
            return {"status": "ok", "loaded": False, "message": "No model loaded"}
        try:
            await asyncio.to_thread(runtime.close)
            return {"status": "ok", "loaded": False, "message": f"Unloaded {runtime.model_name}"}
        except Exception as e:
            return {"status": "error", "loaded": runtime.loaded, "error": str(e)}

    @app.post("/load")
    async def load_model(request: Request):
        """Hot-swap to a different model without restarting the runtime process.
        Body: {"model": "path/to/model.xrlf"}
        Runs in a thread so /health stays responsive and reports load_state.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_path = body.get("model", "")
        if not model_path:
            return {"status": "error", "loaded": runtime.loaded, "error": "missing 'model' in body"}

        if getattr(runtime, "load_state", "idle") == "loading":
            raise HTTPException(status_code=409, detail="Model load already in progress")

        # Resolve and validate BEFORE unloading — a bad path must not kill the
        # currently loaded model.
        import os as _os
        if not _os.path.exists(str(model_path)):
            alt = _os.path.join("xrl_encoded", str(model_path))
            if _os.path.exists(alt):
                model_path = alt
            else:
                return {"status": "error", "loaded": runtime.loaded,
                        "error": f"model file not found: {model_path}"}

        # Report loading through the whole unload+load window so /health and
        # pollers see 'loading' (also blocks a concurrent /load via the 409).
        runtime.load_state = "loading"
        runtime.load_error = None

        # Unload current model first if loaded
        if runtime.loaded:
            try:
                await asyncio.to_thread(runtime.close)
            except Exception as e:
                print(f"  ⚠️ Error during unload: {e}")
            runtime.load_state = "loading"  # close() resets to 'idle' — re-assert

        # Reconfigure runtime with new model path and load
        try:
            runtime.xrlf_path = str(model_path)
            await asyncio.to_thread(runtime.load)
            return {"status": "ok", "loaded": True, "model": runtime.model_name}
        except Exception as e:
            return {"status": "error", "loaded": runtime.loaded,
                    "load_state": getattr(runtime, "load_state", "error"),
                    "error": str(e)}

    @app.get("/v1/models")
    async def list_models():
        model_id = runtime.model_name or "xrlf-model"
        return {
            "object": "list",
            "data": [{
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "xrlf-runtime",
                "capabilities": {
                    "vision": True,
                    "audio": True,
                    "video": True,
                    "tts": True,
                    "xrl_cognitive_layer": True,
                    "foveated_memory": True,
                },
            }],
        }

    @app.get("/v1/context")
    async def get_context_info():
        """Proxy-internal: exposes actual n_ctx (after safety net cap) for injection planning.
        NOT exposed to end clients — the proxy spoofs a larger window to them while
        injecting a smaller, planned amount that fits this real n_ctx.
        """
        return {
            "context_window": runtime.n_ctx,
            "model": runtime.model_name,
            "loaded": runtime.loaded,
        }

    # ── Chat completions ──────────────────────────────────────────────────────

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest, request: Request):
        messages = [m.model_dump() for m in req.messages]

        # Detect multimodal content
        has_image = has_audio = has_video = False
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        t = part.get("type", "")
                        if t in ("image_url", "image"):
                            has_image = True
                        elif t in ("audio_url", "audio", "input_audio"):
                            has_audio = True

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        model_id = runtime.model_name or "xrlf-model"

        if not runtime.loaded:
            state = getattr(runtime, "load_state", "idle")
            detail = getattr(runtime, "load_error", None) or (
                "model still loading" if state == "loading" else "no model loaded"
            )
            raise HTTPException(status_code=503, detail=f"XRLF runtime not ready ({state}): {detail}")

        if req.stream:
            return StreamingResponse(
                _stream_chat(
                    runtime, messages, req, has_image, has_audio, has_video,
                    completion_id, model_id
                ),
                media_type="text/event-stream",
            )

        # Non-streaming — run in a thread so the event loop (and /health)
        # stays responsive during blocking inference.
        try:
            response_text = await asyncio.to_thread(
                runtime.chat,
                messages=messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=False,
                has_image=has_image,
                has_audio=has_audio,
                has_video=has_video,
                force_profile=req.xrlf_force_profile,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": -1,
                "completion_tokens": -1,
                "total_tokens": -1,
            },
        }

    async def _stream_chat(
        runtime, messages, req, has_image, has_audio, has_video,
        completion_id, model_id
    ) -> AsyncGenerator[str, None]:
        """SSE streaming generator."""
        try:
            gen = runtime.chat(
                messages=messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=True,
                has_image=has_image,
                has_audio=has_audio,
                has_video=has_video,
                force_profile=req.xrlf_force_profile,
            )
            for chunk in gen:
                data = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_id,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(data)}\n\n"
                await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            done = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(done)}\n\n"
            yield "data: [DONE]\n\n"

    # ── Raw completions ───────────────────────────────────────────────────────

    @app.post("/v1/completions")
    async def completions(req: CompletionRequest):
        try:
            text = runtime.generate(
                req.prompt,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        return {
            "id": f"cmpl-{uuid.uuid4().hex[:12]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": runtime.model_name,
            "choices": [{
                "text": text,
                "index": 0,
                "finish_reason": "stop",
            }],
        }

    # ── Native STT: POST /v1/audio/transcriptions ─────────────────────────────
    # Uses the model's native speech-to-text (Gemma-4 audio encoder via mmproj)
    # Accepts: multipart file upload (audio file) or JSON with base64
    @app.post("/v1/audio/transcriptions")
    async def transcribe_audio(request: Request):
        import base64 as b64mod
        import tempfile, os

        audio_bytes = None
        filename = "audio.webm"

        # Check content type for multipart vs JSON
        content_type = request.headers.get("content-type", "")

        if "multipart" in content_type:
            form = await request.form()
            file = form.get("file") or form.get("audio")
            if file:
                audio_bytes = await file.read()
                filename = file.filename or "audio.webm"
        else:
            body = await request.json()
            audio_b64 = body.get("audio_base64") or body.get("audio")
            if audio_b64:
                audio_bytes = b64mod.b64decode(audio_b64)
                filename = body.get("filename", "audio.webm")

        if not audio_bytes:
            raise HTTPException(status_code=400, detail="No audio data provided")

        # Save to temp file
        tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False)
        tmp.write(audio_bytes)
        tmp.close()

        try:
            # Use the model's chat handler to process audio
            # Gemma-4 supports audio input via the MTMD chat handler
            llama = getattr(runtime, "_llama", None)
            llm = getattr(llama, "_llm", None) if llama else None
            handler = getattr(llm, "chat_handler", None) if llm else None
            if handler:
                # Init the mtmd context (lazy-initialized)
                if getattr(handler, "mtmd_ctx", None) is None and hasattr(handler, "_init_mtmd_context"):
                    handler._init_mtmd_context(llm)
                try:
                    import llama_cpp.mtmd_cpp as mtmd_cpp
                    ctx = getattr(handler, "mtmd_ctx", None)
                    if ctx and hasattr(mtmd_cpp, 'mtmd_support_audio') and mtmd_cpp.mtmd_support_audio(ctx):
                        # Process audio through the model
                        # Create a chat completion with audio input
                        messages = [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Transcribe this audio accurately."},
                                {"type": "audio_url", "audio_url": {"url": f"data:audio/webm;base64,{b64mod.b64encode(audio_bytes).decode()}"}}
                            ]
                        }]
                        result = runtime.chat(messages, max_tokens=256, has_audio=True)
                        text = result.strip() if isinstance(result, str) else str(result)
                        return {"text": text}
                except (ImportError, Exception) as e:
                    print(f"[API] Native STT error: {e}")

            # Fallback to IPCServer Whisper if available
            ipc_server = getattr(request.app.state, "ipc_server", None)
            fwhisper = getattr(ipc_server, "_fwhisper_model", None) if ipc_server else None
            if fwhisper:
                try:
                    import io, wave, numpy as np
                    import asyncio
                    with wave.open(io.BytesIO(audio_bytes), 'rb') as wav:
                        sr = wav.getframerate()
                        n_channels = wav.getnchannels()
                        frames = wav.readframes(wav.getnframes())
                        audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                        if n_channels > 1:
                            audio_np = audio_np[::n_channels]
                        if sr != 16000:
                            n_samples = int(len(audio_np) * 16000 / sr)
                            indices = np.linspace(0, len(audio_np) - 1, n_samples)
                            audio_np = np.interp(indices, np.arange(len(audio_np)), audio_np)
                    
                    segments, info = await asyncio.to_thread(
                        fwhisper.transcribe,
                        audio_np, language="en", beam_size=5,
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
                    )
                    text = " ".join(seg.text.strip() for seg in segments).strip()
                    return {"text": text}
                except Exception as e:
                    print(f"[API] IPC Whisper STT error: {e}")

            raise HTTPException(status_code=503, detail="Native STT not available — model has no audio support or mmproj not loaded")
        finally:
            os.unlink(tmp.name)

    # ── Native TTS: POST /v1/audio/speech ──────────────────────────────────────
    # Uses the MMHookRegistry's TTS hook (which auto-detects Kokoro/Piper/espeak)
    # or the model's native audio output if available
    @app.post("/v1/audio/speech")
    async def generate_speech(request: Request):
        body = await request.json()
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")

        voice = body.get("voice", "default")

        # Try the MMHookRegistry TTS first
        mm_registry = getattr(runtime, "_mm_registry", None)
        tts_hook = getattr(mm_registry, "tts", None) if mm_registry else None
        if tts_hook and getattr(tts_hook, "available", False):
            try:
                wav_path = tts_hook.speak(text)
                if wav_path and os.path.exists(wav_path):
                    with open(wav_path, "rb") as f:
                        audio_data = f.read()
                    os.unlink(wav_path)
                    return Response(
                        content=audio_data,
                        media_type="audio/wav",
                        headers={"Content-Disposition": "inline; filename=speech.wav"}
                    )
            except Exception as e:
                print(f"[API] TTS hook error: {e}")

        # Fallback to IPCServer Kokoro if available
        ipc_server = getattr(request.app.state, "ipc_server", None)
        if ipc_server and hasattr(ipc_server, "_kokoro_tts"):
            try:
                import asyncio
                pcm_data = await asyncio.to_thread(ipc_server._kokoro_tts, text, voice, 24000)
                if pcm_data:
                    import wave, io
                    buf = io.BytesIO()
                    with wave.open(buf, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(24000)
                        wf.writeframes(pcm_data)
                    return Response(
                        content=buf.getvalue(),
                        media_type="audio/wav",
                        headers={"Content-Disposition": "inline; filename=speech.wav"}
                    )
            except Exception as e:
                print(f"[API] IPC Kokoro TTS error: {e}")

        raise HTTPException(status_code=503, detail="TTS not available — no TTS hook or external server")

    # ── Image input: POST /v1/images/understand ────────────────────────────────
    # Send an image to the model for understanding (vision capability)
    @app.post("/v1/images/understand")
    async def understand_image(request: Request):
        import base64 as b64mod

        body = await request.json()
        image_b64 = body.get("image_base64") or body.get("image")
        prompt = body.get("prompt", "Describe this image in detail.")
        if not image_b64:
            raise HTTPException(status_code=400, detail="image_base64 required")

        # Strip data URL prefix if present
        if "," in image_b64 and image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        # Build multimodal chat message
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ]

        try:
            result = runtime.chat(messages, max_tokens=512, has_image=True)
            text = result.strip() if isinstance(result, str) else str(result)
            return {"text": text}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Vision error: {e}")

    # ── Capability check: GET /v1/capabilities ─────────────────────────────────
    @app.get("/v1/capabilities")
    async def capabilities():
        llama = getattr(runtime, "_llama", None)
        mmproj_path = getattr(llama, "mmproj_path", None) if llama else None
        has_mmproj = bool(mmproj_path and os.path.exists(mmproj_path))
        mm_registry = getattr(runtime, "_mm_registry", None)
        tts_hook = getattr(mm_registry, "tts", None) if mm_registry else None
        has_tts = bool(tts_hook and getattr(tts_hook, "available", False))
        has_vision = False
        has_audio = False

        if has_mmproj and llama:
            llm = getattr(llama, "_llm", None)
            if llm:
                try:
                    import llama_cpp.mtmd_cpp as mtmd_cpp
                    handler = getattr(llm, "chat_handler", None)
                    if handler:
                        if getattr(handler, "mtmd_ctx", None) is None and hasattr(handler, "_init_mtmd_context"):
                            handler._init_mtmd_context(llm)
                        ctx = getattr(handler, "mtmd_ctx", None)
                        if ctx:
                            has_vision = bool(hasattr(mtmd_cpp, 'mtmd_support_vision') and mtmd_cpp.mtmd_support_vision(ctx))
                            if hasattr(mtmd_cpp, 'mtmd_support_audio'):
                                has_audio = bool(mtmd_cpp.mtmd_support_audio(ctx))
                except (ImportError, Exception) as e:
                    print(f"[API] Capability check error: {e}")

        gpu_layers = getattr(llama, 'n_gpu_layers', 0)
        if gpu_layers is None:
            gpu_layers = 0

        return {
            "vision": has_vision,
            "audio_stt": has_audio,
            "tts": has_tts,
            "mmproj_loaded": has_mmproj,
            "gpu_layers": gpu_layers,
            "model": getattr(runtime, "model_name", "xrlf-model"),
        }

    # ── Spatial environment: POST /api/environment/plaster_texture ────────────
    # Quest client sends room scan texture data for spatial memory storage.
    @app.post("/api/environment/plaster_texture")
    async def plaster_texture(request: Request):
        try:
            body = await request.body()
            data = json.loads(body) if body else {}
            # Store in foveated memory or pass to environment processor
            session = data.get("session_id", "quest3_spatial")
            texture_id = data.get("texture_id", f"plaster_{int(time.time())}")
            # Persist to the spatial memory directory
            spatial_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "foveated-memory", "memory_data", "spatial")
            os.makedirs(spatial_dir, exist_ok=True)
            meta_path = os.path.join(spatial_dir, f"{texture_id}.json")
            with open(meta_path, "w") as f:
                json.dump({"session": session, "texture_id": texture_id, "timestamp": time.time(), "data_size": len(body)}, f)
            return {"status": "ok", "texture_id": texture_id, "stored": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Plaster texture error: {e}")

    # ── Camera stream: GET /api/camera/stream ─────────────────────────────────
    # Returns latest webcam frame from the Quest/phone camera as JPEG.
    @app.get("/api/camera/stream")
    async def camera_stream():
        # Return a placeholder frame — actual camera frames are pushed via WS
        from fastapi import Response
        # Generate a 1x1 black JPEG placeholder
        placeholder = bytes([0xFF, 0xD8, 0xFF, 0xD9])  # Minimal JPEG header
        return Response(content=placeholder, media_type="image/jpeg")

    # ── Alias: /api/health (for Quest clients that check this path) ───────────
    @app.get("/api/health")
    async def api_health():
        return {"status": "ok", "model": getattr(runtime, "model_name", "xrlf-model"), "runtime": "xrlf-1.0"}

    return app


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="XRLF OpenAI-compatible API server")
    parser.add_argument("--model", required=True, help="Path to .xrlf file")
    parser.add_argument("--port", type=int, default=8300, help="API port (default: 8300)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--gpu-layers", type=int, default=-1, help="GPU layers (-1=all)")
    parser.add_argument("--ctx", type=int, default=8192, help="Context window size")
    parser.add_argument("--session", default="default", help="Session ID for memory")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    runtime = XRLFRuntime(
        xrlf_path=args.model,
        session_id=args.session,
        n_gpu_layers=args.gpu_layers,
        n_ctx=args.ctx,
        verbose=args.verbose,
    )
    runtime.load()

    app = create_app(runtime)

    # ── SoftLayer file watcher ────────────────────────────────────────────────
    softlayer_dir = Path(__file__).parent.parent / "softlayer"
    if softlayer_dir.exists():
        try:
            import threading
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class SoftLayerHandler(FileSystemEventHandler):
                def __init__(self):
                    self._last = 0.0
                def on_modified(self, event):
                    if event.is_directory or not event.src_path.endswith(".js"):
                        return
                    now = time.time()
                    if now - self._last < 0.5:
                        return
                    self._last = now
                    p = Path(event.src_path)
                    print(f"  [SoftLayer] File changed: {p.name} — restart XRLF to push to Quest", flush=True)

            observer = Observer()
            observer.schedule(SoftLayerHandler(), str(softlayer_dir), recursive=True)
            observer.daemon = True
            observer.start()
            print(f"  [SoftLayer] Watching {softlayer_dir} for hot-reloads")
        except ImportError:
            print("  [SoftLayer] watchdog not installed — file watching disabled")

    print(f"\n  🚀 XRLF API ready → http://{args.host}:{args.port}/v1")
    print(f"     Model: {runtime.model_name}")
    print(f"     SoftLayer: http://{args.host}:{args.port}/softlayer/{{name}}.js")
    print(f"     Point LM Studio / Open WebUI / Antigravity at this endpoint\n")

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
