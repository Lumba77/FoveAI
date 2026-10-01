r"""
smoke_test_xrlf_draft.py
========================
Quick smoke test of the XRLF draft GGUF using llama_cpp.
"""

import sys
from pathlib import Path
from llama_cpp import Llama

MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_draft_qwen0.5b_q4_k_m.gguf")

PROMPTS = [
    {
        "name": "XRLF intent classification",
        "prompt": (
            "<|im_start|>system\n"
            "You are an XRLF-aware drafting model. Identify the user's intent and emotion, "
            "then produce one or more XRLF tags.\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            "I'm frustrated that the UI keeps crashing when I save my project.\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        ),
    },
    {
        "name": "Skeleton drafting",
        "prompt": (
            "<|im_start|>system\n"
            "You are an XRLF-aware drafting model. Draft a skeleton response for the user query.\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            "How do I create a Python function that reads a JSON file and returns a dictionary?\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        ),
    },
    {
        "name": "Specialist routing",
        "prompt": (
            "<|im_start|>system\n"
            "You are an XRLF-aware drafting model. Pick the best specialist model for the user request.\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            "Rewrite this code in TypeScript and make it type-safe: function add(a, b) { return a + b; }\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        ),
    },
]


def main():
    if not MODEL_PATH.exists():
        print(f"❌ GGUF not found at {MODEL_PATH}")
        sys.exit(1)

    print("Loading XRLF draft GGUF...")
    print(f"  {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    llm = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=2048,
        n_threads=4,
        verbose=False,
    )

    for item in PROMPTS:
        print(f"\n{'='*60}")
        print(f"Prompt: {item['name']}")
        print(f"{'='*60}")
        output = llm(
            item["prompt"],
            max_tokens=200,
            stop=["<|im_end|>", "<|endoftext|>"],
            temperature=0.3,
        )
        text = output["choices"][0]["text"].strip()
        print(text)

    print("\n✅ Smoke test complete.")


if __name__ == "__main__":
    main()
