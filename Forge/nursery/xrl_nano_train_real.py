"""
Forge/nursery/xrl_nano_train_real.py — Real Nano XRL Trainer
====================================================================
First real training run for the nano hyperdrive hypothesis:

    base = SmolLM2-135M-Instruct (cached)
    corpus = red-thread -> response pairs (xrl_nano_train.jsonl)
    objective = teach the nano model to answer from an XRLated principia seed

Uses standard transformers (Trainer + full fine-tune). No peft/trl/datasets
required. For a first data point we full fine-tune 135M on ~10 samples.

Serving (later) can use premium tools — vLLM / SGLang — once the tuned
checkpoint exists. Training here is deliberately standard to stay portable.

Evolutionary loop: run this small, measure quality, then refine (more data,
LoRA instead of full FT, degree curriculum) before scaling to 1B-2B.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from runtime.xrl_principia import XRLPrincipiaCompiler

# XRL seed special tokens (mirror runtime/xrl_principia + nano trainer)
XRL_SEED_TOKENS = [
    "<XRL-SEED>", "</XRL-SEED>",
    "<ANCHORS>", "</ANCHORS>",
    "<CONCEPTS>", "</CONCEPTS>",
    "<DIGEST>", "</DIGEST>",
    "<PRINCIPA>", "</PRINCIPA>",
    "<MEMBRANE>", "</MEMBRANE>",
    "<KV-HINT>", "</KV-HINT>",
    "<CONTINUE/>",
    "<RUBBLE>", "</RUBBLE>",
    "<PROFILE>", "</PROFILE>",
    "<USER>", "</USER>",
    "<ASSISTANT>",
    # genome compression stage tokens
    "<GENOME>", "</GENOME>",
    "<SNP>", "</SNP>",
    "<C/>",
]

DEFAULT_SNAPSHOT = (
    "/home/lumba/Models/hub/models--HuggingFaceTB--SmolLM2-135M-Instruct/"
    "snapshots/12fd25f77366fa6b3b4b768ec3050bf629380bac"
)


def resolve_model_dir(snapshot: str) -> str:
    """Return a real, existing model directory."""
    for p in (snapshot, os.path.realpath(snapshot)):
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "model.safetensors")):
            return p
    raise FileNotFoundError(f"Model snapshot not found: {snapshot}")


def load_corpus(corpus_path: str) -> list[str]:
    """Load red-thread training samples as plain text strings."""
    texts: list[str] = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            texts.append(obj["text"])
    return texts


def build_train_dataset(tokenizer, texts: list[str], max_length: int):
    """Tokenize texts into a minimal torch Dataset (causal LM)."""
    import torch
    from torch.utils.data import Dataset

    encodings = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=max_length,
        return_tensors="pt",
    )

    class _DS(Dataset):
        def __len__(self):
            return encodings["input_ids"].shape[0]

        def __getitem__(self, idx):
            input_ids = encodings["input_ids"][idx]
            attention_mask = encodings["attention_mask"][idx]
            return {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "labels": input_ids.clone(),
            }

    return _DS()


def train(
    snapshot: str,
    corpus_path: str,
    output_dir: str,
    epochs: int = 3,
    max_length: int = 512,
    smoke: bool = False,
    batch_size: int = 1,
    lr: float | None = None,
) -> dict:
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    model_dir = resolve_model_dir(snapshot)
    print(f"[load] tokenizer + model from {model_dir}")

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load in fp32 and let Trainer handle mixed precision, if enabled.
    # (Casting the model to fp16 here causes "Attempting to unscale FP16
    # gradients" when Trainer's fp16 AMP tries to unscale.)
    model = AutoModelForCausalLM.from_pretrained(model_dir)

    # Vocab surgery: add XRL seed tokens and resize embeddings.
    n_added = tokenizer.add_tokens(XRL_SEED_TOKENS)
    model.resize_token_embeddings(len(tokenizer))
    print(f"[vocab] added {n_added} XRL seed tokens -> vocab size {len(tokenizer)}")

    texts = load_corpus(corpus_path)
    print(f"[data] loaded {len(texts)} samples from {corpus_path}")
    ds = build_train_dataset(tokenizer, texts, max_length)

    max_steps = 2 if smoke else -1
    args = TrainingArguments(
        output_dir=os.path.join(output_dir, "checkpoints"),
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=1,
        num_train_epochs=epochs,
        max_steps=max_steps,
        learning_rate=lr if lr is not None else (1e-3 if smoke else 5e-4),
        logging_steps=10,
        save_strategy="no",
        bf16=True,
        report_to=[],
        seed=42,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=ds,
    )

    t0 = time.time()
    result = trainer.train()
    elapsed = time.time() - t0

    # Save the fine-tuned model + tokenizer.
    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"[save] model + tokenizer -> {output_dir}")

    report = {
        "output_dir": output_dir,
        "train_loss": round(float(result.training_loss), 4),
        "elapsed_s": round(elapsed, 1),
        "samples": len(texts),
        "epochs": epochs,
        "smoke": smoke,
        "vocab_size_after": len(tokenizer),
    }
    print("[done]", json.dumps(report))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=DEFAULT_SNAPSHOT)
    ap.add_argument(
        "--corpus",
        default="/home/lumba/FoveAI/Forge/nursery/corpus/xrl_nano_train.jsonl",
    )
    ap.add_argument(
        "--output",
        default="/home/lumba/Models/foveai-labs/nano-xrl-runs/smollm2-135m-xrl",
    )
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--max-length", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    train(
        args.snapshot,
        args.corpus,
        args.output,
        epochs=args.epochs,
        max_length=args.max_length,
        batch_size=args.batch_size,
        lr=args.lr,
        smoke=args.smoke,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
