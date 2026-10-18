"""
Forge/nursery/nano_evaluate.py — Nano XRL Fitness Evaluator
====================================================================
The selection pressure for the nano evolutionary loop.

Loads a tuned nano model and measures how well it reproduces the expected
responses when fed only the red-thread prompt (the seed, without the answer).
This is the quality gate that decides which individuals survive.

Fitness = exact-match accuracy + fuzzy (token-overlap) score.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch


def load_corpus_prompts(corpus_path: str) -> list[tuple[str, str]]:
    """Return [(prompt_without_answer, expected_answer)] from a corpus JSONL."""
    pairs: list[tuple[str, str]] = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            text = obj["text"]
            # Prompt ends at the <ASSISTANT> marker; everything after is the answer.
            if "<ASSISTANT>" in text:
                prompt, answer = text.split("<ASSISTANT>", 1)
                pairs.append((prompt + "<ASSISTANT>", answer.strip()))
            else:
                pairs.append((text, ""))
    return pairs


def fuzzy_score(pred: str, expected: str) -> float:
    """Token-overlap score in [0,1]."""
    if not expected:
        return 0.0
    pred_toks = set(pred.lower().split())
    exp_toks = set(expected.lower().split())
    if not exp_toks:
        return 0.0
    return len(pred_toks & exp_toks) / len(exp_toks)


def evaluate(
    model_dir: str,
    corpus_path: str,
    max_new_tokens: int = 32,
    limit: int | None = None,
) -> dict:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_dir)
    model.eval()

    pairs = load_corpus_prompts(corpus_path)
    if limit:
        pairs = pairs[:limit]

    exact = 0
    fuzzy_sum = 0.0
    results = []
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    for prompt, expected in pairs:
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        gen = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        gen_clean = gen.strip()
        exp_clean = expected.strip()

        is_exact = gen_clean == exp_clean
        score = fuzzy_score(gen_clean, exp_clean)
        if is_exact:
            exact += 1
        fuzzy_sum += score
        results.append({
            "expected": exp_clean[:60],
            "generated": gen_clean[:60],
            "exact": is_exact,
            "fuzzy": round(score, 3),
        })

    n = len(pairs)
    report = {
        "model_dir": model_dir,
        "samples": n,
        "exact_accuracy": round(exact / n, 3) if n else 0.0,
        "mean_fuzzy": round(fuzzy_sum / n, 3) if n else 0.0,
        "fitness": round((exact / n + fuzzy_sum / n) / 2, 3) if n else 0.0,
    }
    print(json.dumps(report, indent=2))
    for r in results:
        mark = "✓" if r["exact"] else "·"
        print(f"  {mark} exp={r['expected']!r}")
        if not r["exact"]:
            print(f"      got={r['generated']!r}")
    return report


GENOME_EVAL_CORPUS = "/home/lumba/FoveAI/Forge/nursery/corpus/genome_compression_eval.jsonl"
GENOME_SPLIT_MARKER = "<XRL-SEED d=3>"


def load_genome_prompts(corpus_path: str) -> list[tuple[str, str]]:
    """[(xrl-seed prompt, expected genome response)] from a genome-corpus JSONL."""
    pairs: list[tuple[str, str]] = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            text = json.loads(line)["text"]
            if GENOME_SPLIT_MARKER in text:
                prompt, answer = text.rsplit(GENOME_SPLIT_MARKER, 1)
                pairs.append((prompt + GENOME_SPLIT_MARKER, answer.strip()))
    return pairs


def normalize_genome_text(text: str) -> str:
    """Strip chat-end tokens and collapse whitespace (tokenizer artifacts)."""
    return " ".join(text.replace("<|im_end|>", "").split())


def evaluate_genome_compression(
    model_dir: str,
    corpus_path: str | None = None,
    max_new_tokens: int = 256,
    limit: int | None = None,
    verbose: bool = False,
) -> dict:
    """Quality gate for the genome_compression stage.

    The genome corpus has no <ASSISTANT> marker (why nano_evaluate.evaluate
    can't score it); samples split at <XRL-SEED d=3> instead, and answers
    are matched with whitespace-normalized compare + token-overlap fuzz.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer

    corpus_path = corpus_path or GENOME_EVAL_CORPUS
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_dir)
    model.eval()

    pairs = load_genome_prompts(corpus_path)
    if limit:
        pairs = pairs[:limit]

    exact = 0
    fuzzy_sum = 0.0
    misses: list[dict] = []
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    for prompt, expected in pairs:
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        gen = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        gen_clean = normalize_genome_text(gen)
        exp_clean = normalize_genome_text(expected)

        is_exact = gen_clean == exp_clean
        score = fuzzy_score(gen_clean, exp_clean)
        if is_exact:
            exact += 1
        else:
            misses.append({"expected": exp_clean[:80], "generated": gen_clean[:80]})
        fuzzy_sum += score

    n = len(pairs)
    report = {
        "model_dir": model_dir,
        "stage": "genome_compression",
        "samples": n,
        "exact_accuracy": round(exact / n, 3) if n else 0.0,
        "mean_fuzzy": round(fuzzy_sum / n, 3) if n else 0.0,
        "fitness": round((exact / n + fuzzy_sum / n) / 2, 3) if n else 0.0,
        "misses": misses if verbose else misses[:3],
    }
    if verbose:
        print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/home/lumba/Models/foveai-labs/nano-xrl-runs/smollm2-135m-xrl-full")
    ap.add_argument("--corpus", default="/home/lumba/FoveAI/Forge/nursery/corpus/seed_decode.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-new-tokens", type=int, default=32)
    args = ap.parse_args()
    evaluate(args.model, args.corpus, max_new_tokens=args.max_new_tokens, limit=args.limit)
