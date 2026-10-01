"""Inspect the holonic gnist models (stories260K, ~33M params)."""
from pathlib import Path
from llama_cpp import Llama

models = [
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--ggml-org--models\snapshots"),
]

# Find stories260K
for search_root in models:
    if not search_root.exists():
        print(f"Search root not found: {search_root}")
        continue
    for gguf in search_root.rglob("stories260K*.gguf"):
        print(f"\n{'='*60}")
        print(f"  GNIST: {gguf.name}")
        print(f"  Size: {gguf.stat().st_size / 1024 / 1024:.2f} MB")
        print(f"  Path: {gguf}")
        print(f"{'='*60}")

        try:
            ll = Llama(
                model_path=str(gguf),
                verbose=False,
                n_ctx=512,
                n_gpu_layers=0,
                logits=False,
            )

            print("\n  --- Metadata ---")
            for k, v in ll.metadata.items():
                print(f"  {k}: {v}")

            print(f"\n  n_vocab: {ll.n_vocab()}")
            print(f"  n_embd: {ll.n_embd()}")

            print("\n  --- Generation test ---")
            prompts = [
                "Once upon a time, a dragon",
                "The XRLF protocol is",
                "Error: TypeError at line 42. Fix:",
            ]
            for p in prompts:
                out = ll(p, max_tokens=30, temperature=0.7, echo=False)
                text = out["choices"][0]["text"].strip()
                print(f"\n  Prompt: {p}")
                print(f"  Output: {text}")

            del ll
        except Exception as e:
            print(f"  ERROR loading: {e}")
