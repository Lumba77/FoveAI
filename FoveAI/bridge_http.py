"""
bridge_http.py — minimal OpenAI-compatible HTTP server for a raw .gguf model.
Uses only the Python stdlib so it doesn't need uvicorn/flask/fastapi.
"""

import argparse
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from llama_cpp import Llama

llm: Llama | None = None
model_id = "foveai-omni-router"


def make_completion(
    messages: list[dict[str, str]], max_tokens: int, temperature: float
) -> str:
    result = llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stop=["</s>", "<|endoftext|>", "<|im_start|>"],
    )
    return result["choices"][0]["message"].get("content", "")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep logs quiet

    def _send_json(self, status: int, obj: Any):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model_id,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "foveai-bridge",
                        }
                    ],
                },
            )
        elif self.path == "/health":
            self._send_json(
                200, {"status": "ok", "model": model_id, "loaded": llm is not None}
            )
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
            messages = [
                {"role": m.get("role"), "content": m.get("content")}
                for m in payload.get("messages", [])
            ]
            max_tokens = int(payload.get("max_tokens", 1024))
            temperature = float(payload.get("temperature", 0.7))
            content = make_completion(messages, max_tokens, temperature)
            self._send_json(
                200,
                {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": payload.get("model", model_id),
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": -1,
                        "completion_tokens": -1,
                        "total_tokens": -1,
                    },
                },
            )
        except Exception as e:
            self._send_json(500, {"error": str(e)})


def main():
    global llm
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, default=8402)
    parser.add_argument("--n_ctx", type=int, default=4096)
    parser.add_argument("--n_gpu_layers", type=int, default=0)
    args = parser.parse_args()

    print(f"Loading GGUF: {args.model}", flush=True)
    llm = Llama(
        model_path=args.model,
        n_ctx=args.n_ctx,
        n_batch=128,
        n_gpu_layers=args.n_gpu_layers,
        n_threads=4,
        verbose=False,
    )
    print(f"GGUF loaded. Serving on http://127.0.0.1:{args.port}", flush=True)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("serve_forever starting", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception:
        import traceback

        traceback.print_exc()
    finally:
        server.server_close()
        print("server closed", flush=True)


if __name__ == "__main__":
    main()
