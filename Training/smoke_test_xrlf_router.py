r"""
smoke_test_xrlf_router.py
=========================
Quick smoke test of the XRLF router GGUF using llama_cpp.
"""

import sys
from pathlib import Path
from llama_cpp import Llama

MODEL_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_qwen0.5b_q4_k_m.gguf")

PROMPTS = [
    ("Stop on solved math", "XRLF: judge whether this query can be answered in one step.\nQuery: A store has 24 apples. They sell 7 in the morning and 5 in the afternoon. How many remain?"),
    ("Continue on hard task", "XRLF: judge whether this user query can be answered in one step.\nQuery: Prove Fermat's Last Theorem."),
    ("Route to code", "XRLF: route this query.\nQuery: fix this python syntax error"),
    ("Route to audio", "XRLF: route this query.\nQuery: make the music sadder"),
    ("Concise reformulation", "XRLF: rewrite this response concisely and append the control token.\nWorld War II ended in 1945, after six years of conflict involving many nations."),
]


def main():
    if not MODEL_PATH.exists():
        print(f"❌ GGUF not found at {MODEL_PATH}")
        sys.exit(1)

    print("Loading XRLF router GGUF...")
    print(f"  {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    llm = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=1024,
        n_threads=4,
        verbose=False,
    )

    for name, user in PROMPTS:
        print(f"\n{'='*60}")
        print(f"Prompt: {name}")
        print(f"{'='*60}")
        prompt = (
            "<|im_start|>system\n"
            "You are an XRLF router. Emit only a control token or a tiny XRLF tag. Do not explain.\n"
            "<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        output = llm(
            prompt,
            max_tokens=30,
            stop=["<|im_end|>", "<|im_start|>", "\n", "<|endoftext|>"],
            temperature=0.1,
        )
        text = output["choices"][0]["text"].strip()
        print(repr(text) if text else "(empty)")

    print("\n✅ Smoke test complete.")


if __name__ == "__main__":
    main()
