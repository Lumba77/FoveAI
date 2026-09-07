"""
bridge_server.py — minimal OpenAI-compatible server for a raw .gguf model.
Used as a fallback when the XRLF bundled core is not chat-coherent.
"""

import json
import time
import uuid
import argparse
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from llama_cpp import Llama


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: int = Field(default=1024, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = False


app = FastAPI(title="GGUF Bridge")
llm: Optional[Llama] = None
model_id = "foveai-omni-router"


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "foveai-bridge",
        }],
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": model_id, "loaded": llm is not None}


def _to_dicts(messages: List[ChatMessage]) -> List[Dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


def _stream_response(payload: ChatCompletionRequest):
    for chunk in llm.create_chat_completion(
        messages=_to_dicts(payload.messages),
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
        stop=["</s>", "<|endoftext|>", "<|im_end|>", "<|im_start|>"],
        stream=True,
    ):
        delta = chunk["choices"][0]["delta"].get("content", "")
        data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": payload.model,
            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(data)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
def chat_completions(payload: ChatCompletionRequest, request: Request):
    if llm is None:
        return {"error": "model not loaded"}, 503

    if payload.stream:
        return StreamingResponse(_stream_response(payload), media_type="text/event-stream")

    result = llm.create_chat_completion(
        messages=_to_dicts(payload.messages),
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
        stop=["</s>", "<|endoftext|>", "<|im_end|>", "<|im_start|>"],
    )
    content = result["choices"][0]["message"].get("content", "")
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": result["choices"][0].get("finish_reason", "stop"),
        }],
        "usage": result.get("usage", {"prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1}),
    }


def main():
    global llm, model_id
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, default=8402)
    parser.add_argument("--n_ctx", type=int, default=4096)
    parser.add_argument("--n_gpu_layers", type=int, default=0)
    args = parser.parse_args()

    print(f"Loading GGUF: {args.model}")
    llm = Llama(
        model_path=args.model,
        n_ctx=args.n_ctx,
        n_gpu_layers=args.n_gpu_layers,
        n_threads=None,
        verbose=False,
    )
    print("GGUF loaded. Starting server on port", args.port, flush=True)

    import uvicorn
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info", access_log=True)
    except Exception as e:
        print("Uvicorn crashed:", e, flush=True)
        raise


if __name__ == "__main__":
    main()
