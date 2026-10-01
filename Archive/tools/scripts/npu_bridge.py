import logging
import os
import time

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("npu_bridge")

app = FastAPI(title="FoveAI Windows NPU/GPU Acceleration Bridge")

# Define the absolute local path to your ONNX optimized model directory
# Example model: microsoft/Phi-3-mini-4k-instruct-onnx (DirectML variant)
MODEL_PATH = os.getenv(
    "FoveAI_NPU_MODEL_PATH", "D:/Lumax/models/ONNX/phi3-mini-dml"
).strip()

has_ort_genai = False
model = None
tokenizer = None

try:
    # Use the official ONNX Runtime Generative AI sub-architecture
    import onnxruntime_genai as og

    has_ort_genai = True
    logger.info("onnxruntime_genai module detected successfully.")

    if os.path.exists(MODEL_PATH) and any(os.listdir(MODEL_PATH)):
        logger.info(f"Loading local ONNX model from: {MODEL_PATH} ...")
        start_time = time.time()
        # Initialize the model directly on the DirectX 12 / DirectML hardware accelerator
        model = og.Model(MODEL_PATH)
        tokenizer = og.Tokenizer(model)
        logger.info(
            f"Model loaded onto DirectML hardware pipeline in {time.time() - start_time:.2f}s."
        )
    else:
        logger.warning(
            f"Model directory empty or missing at '{MODEL_PATH}'. Running in structural MOCK mode."
        )
except ImportError:
    logger.warning(
        "onnxruntime_genai NOT installed. Run: pip install --pre onnxruntime-genai-directml"
    )
except Exception as e:
    logger.error(f"Failed to initialize DirectML hardware execution session: {e}")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool | None = False
    max_tokens: int | None = 512
    temperature: float | None = 0.7


@app.get("/v1/models")
async def list_models():
    return {
        "data": [
            {
                "id": "windows-npu-phi-silica",
                "object": "model",
                "owned_by": "microsoft",
                "permission": [],
            }
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    logger.info(
        f"Routing transaction to DirectML Engine Node. Model request string: {req.model}"
    )

    # 1. Verification Gate for Unconfigured Environments
    if not has_ort_genai or model is None:
        fallback_text = (
            "Windows NPU/GPU Bridge is currently running in MOCK mode.\n"
            f"Please verify that 'onnxruntime-genai-directml' is installed and your model weights "
            f"exist inside your local directory path: {MODEL_PATH}"
        )
        return JSONResponse(content=_build_openai_response(req.model, fallback_text))

    try:
        # 2. Format incoming chat arrays into a clean, unified instruction prompt string
        full_prompt = ""
        for msg in req.messages:
            if msg.role == "system":
                full_prompt += f"<|system|>\n{msg.content}<|end|>\n"
            elif msg.role == "user":
                full_prompt += f"<|user|>\n{msg.content}<|end|>\n"
            elif msg.role == "assistant":
                full_prompt += f"<|assistant|>\n{msg.content}<|end|>\n"
        full_prompt += "<|assistant|>\n"

        # 3. Tokenize input strings into hardware-native tensors
        input_tokens = tokenizer.encode(full_prompt)

        # 4. Bind compilation params to the generator execution thread
        params = og.GeneratorParams(model)
        params.set_search_option(
            "max_length", len(input_tokens) + (req.max_tokens or 512)
        )
        params.set_search_option("temperature", req.temperature or 0.7)
        params.input_ids = input_tokens

        # 5. Execute synchronous loop generation over the target device processing units
        generator = og.Generator(model, params)
        generated_tokens = []

        while not generator.is_done():
            generator.compute_logits()
            generator.generate_next_token()
            # Snip out the latest sequential token index element
            new_token = generator.get_sequence(0)[-1]
            generated_tokens.append(new_token)

        # 6. Decode output arrays back into clean human text strings
        reply = tokenizer.decode(generated_tokens)

    except Exception as e:
        logger.error(f"Execution failure during DirectML tensor generation pass: {e}")
        reply = f"Internal execution error on local DirectML hardware engine node: {e}"

    return JSONResponse(content=_build_openai_response(req.model, reply))


def _build_openai_response(model_name: str, content_text: str) -> dict:
    """Helper layout matrix to bundle text strings into strict OpenAI formatting arrays."""
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content_text.strip()},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


if __name__ == "__main__":
    # Exposed on port 11436 across all interface bridges for seamless WSL2 accessibility
    uvicorn.run(app, host="0.0.0.0", port=11436)
