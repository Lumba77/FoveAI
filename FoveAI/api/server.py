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
from collections.abc import AsyncGenerator
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    from pydantic import BaseModel

    _FASTAPI = True
except ImportError:
    _FASTAPI = False

from runtime.xrlf_runtime import XRLFRuntime

# ── Pydantic models ───────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: Any  # str or list (multimodal)


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    max_tokens: int | None = 1024
    temperature: float | None = None
    stream: bool | None = False
    # XRLF extensions
    xrlf_force_profile: str | None = None


class CompletionRequest(BaseModel):
    model: str = ""
    prompt: str
    max_tokens: int | None = 512
    temperature: float | None = 0.7
    stream: bool | None = False


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "content": "[SYSTEM]\n"
                + "\n".join(system_parts)
                + "\n[USER]\n"
                + str(first.get("content", "")),
            }
            return [first] + others[1:]

    return others


# ── App factory ───────────────────────────────────────────────────────────────


def create_app(runtime: XRLFRuntime) -> "FastAPI":
    if not _FASTAPI:
        raise RuntimeError(
            "fastapi + uvicorn not installed. Run: pip install fastapi uvicorn[standard]"
        )

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
        return {
            "status": "ok",
            "model": runtime.model_name,
            "runtime": "xrlf-1.0",
            "loaded": runtime.loaded,
        }

    # ── Models ────────────────────────────────────────────────────────────────

    @app.post("/unload")
    async def unload_model():
        """Unload the current model from VRAM without killing the runtime process."""
        if not runtime.loaded:
            return {"status": "ok", "loaded": False, "message": "No model loaded"}
        try:
            runtime.close()
            return {
                "status": "ok",
                "loaded": False,
                "message": f"Unloaded {runtime.model_name}",
            }
        except Exception as e:
            return {"status": "error", "loaded": runtime.loaded, "error": str(e)}

    @app.post("/load")
    async def load_model(request: Request):
        """Hot-swap to a different model without restarting the runtime process.
        Body: {"model": "path/to/model.xrlf"}
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_path = body.get("model", "")
        if not model_path:
            return {
                "status": "error",
                "loaded": runtime.loaded,
                "error": "missing 'model' in body",
            }

        # Unload current model first if loaded
        if runtime.loaded:
            try:
                runtime.close()
            except Exception as e:
                print(f"  ⚠️ Error during unload: {e}")

        # Reconfigure runtime with new model path and load
        try:
            runtime.xrlf_path = str(model_path)
            runtime.load()
            return {"status": "ok", "loaded": True, "model": runtime.model_name}
        except Exception as e:
            return {"status": "error", "loaded": runtime.loaded, "error": str(e)}

    @app.get("/v1/models")
    async def list_models():
        model_id = runtime.model_name or "xrlf-model"
        return {
            "object": "list",
            "data": [
                {
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
                }
            ],
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

        if req.stream:
            return StreamingResponse(
                _stream_chat(
                    runtime,
                    messages,
                    req,
                    has_image,
                    has_audio,
                    has_video,
                    completion_id,
                    model_id,
                ),
                media_type="text/event-stream",
            )

        # Non-streaming
        try:
            response_text = runtime.chat(
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
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": -1,
                "completion_tokens": -1,
                "total_tokens": -1,
            },
        }

    async def _stream_chat(
        runtime, messages, req, has_image, has_audio, has_video, completion_id, model_id
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
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None,
                        }
                    ],
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
            "choices": [
                {
                    "text": text,
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
        }

    # ── Native STT: POST /v1/audio/transcriptions ─────────────────────────────
    # Uses the model's native speech-to-text (Gemma-4 audio encoder via mmproj)
    # Accepts: multipart file upload (audio file) or JSON with base64
    @app.post("/v1/audio/transcriptions")
    async def transcribe_audio(request: Request):
        import base64 as b64mod
        import os
        import tempfile

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
        tmp = tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(filename)[1], delete=False
        )
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
                if getattr(handler, "mtmd_ctx", None) is None and hasattr(
                    handler, "_init_mtmd_context"
                ):
                    handler._init_mtmd_context(llm)
                try:
                    from llama_cpp import mtmd_cpp

                    ctx = getattr(handler, "mtmd_ctx", None)
                    if (
                        ctx
                        and hasattr(mtmd_cpp, "mtmd_support_audio")
                        and mtmd_cpp.mtmd_support_audio(ctx)
                    ):
                        # Process audio through the model
                        # Create a chat completion with audio input
                        messages = [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Transcribe this audio accurately.",
                                    },
                                    {
                                        "type": "audio_url",
                                        "audio_url": {
                                            "url": f"data:audio/webm;base64,{b64mod.b64encode(audio_bytes).decode()}"
                                        },
                                    },
                                ],
                            }
                        ]
                        result = runtime.chat(messages, max_tokens=256, has_audio=True)
                        text = (
                            result.strip() if isinstance(result, str) else str(result)
                        )
                        return {"text": text}
                except (ImportError, Exception) as e:
                    print(f"[API] Native STT error: {e}")

            raise HTTPException(
                status_code=503,
                detail="Native STT not available — model has no audio support or mmproj not loaded",
            )
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
                        headers={"Content-Disposition": "inline; filename=speech.wav"},
                    )
            except Exception as e:
                print(f"[API] TTS hook error: {e}")

        raise HTTPException(
            status_code=503, detail="TTS not available — no TTS hook or external server"
        )

    # ── Image input: POST /v1/images/understand ────────────────────────────────
    # Send an image to the model for understanding (vision capability)
    @app.post("/v1/images/understand")
    async def understand_image(request: Request):

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
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
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
                    from llama_cpp import mtmd_cpp

                    handler = getattr(llm, "chat_handler", None)
                    if handler:
                        if getattr(handler, "mtmd_ctx", None) is None and hasattr(
                            handler, "_init_mtmd_context"
                        ):
                            handler._init_mtmd_context(llm)
                        ctx = getattr(handler, "mtmd_ctx", None)
                        if ctx:
                            has_vision = bool(
                                hasattr(mtmd_cpp, "mtmd_support_vision")
                                and mtmd_cpp.mtmd_support_vision(ctx)
                            )
                            if hasattr(mtmd_cpp, "mtmd_support_audio"):
                                has_audio = bool(mtmd_cpp.mtmd_support_audio(ctx))
                except (ImportError, Exception) as e:
                    print(f"[API] Capability check error: {e}")

        gpu_layers = getattr(llama, "n_gpu_layers", 0)
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

    return app


# ── CLI entry point ───────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="XRLF OpenAI-compatible API server")
    parser.add_argument("--model", required=True, help="Path to .xrlf file")
    parser.add_argument(
        "--port", type=int, default=8300, help="API port (default: 8300)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument(
        "--gpu-layers", type=int, default=-1, help="GPU layers (-1=all)"
    )
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

    print(f"\n  🚀 XRLF API ready → http://{args.host}:{args.port}/v1")
    print(f"     Model: {runtime.model_name}")
    print("     Point LM Studio / Open WebUI / Antigravity at this endpoint\n")

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
