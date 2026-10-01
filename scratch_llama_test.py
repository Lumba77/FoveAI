import os

from llama_cpp import Llama
from llama_cpp.llama_chat_format import Gemma4ChatHandler

os.environ["GGML_CUDA_NO_VMM"] = "1"

print("Loading model...")
handler = Gemma4ChatHandler(
    clip_model_path="xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf.cache/mmproj.gguf"
)
llm = Llama(
    model_path="xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf.cache/core.gguf",
    n_gpu_layers=40,
    chat_handler=handler,
    n_ctx=2048,
    verbose=True,
)
print("Model loaded.")

messages = [{"role": "user", "content": "Hello!"}]
print("Generating...")
res = llm.create_chat_completion(messages=messages, max_tokens=10)
print(res)
print("Done.")
