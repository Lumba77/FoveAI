#!/usr/bin/env python3
"""
xrlf_embedder.py — local, self-contained sentence embeddings for FoveAI memory.

Replaces LM Studio (/v1/embeddings) as the embedding backend. Runs
Xenova/all-MiniLM-L6-v2 (quantized ONNX, 384-dim) on CPU via onnxruntime.
Model is already cached locally under .sidecar/, so there is no network
dependency at runtime.

Usage:
    python xrlf_embedder.py --diagnose          # one-off clustering check
    python xrlf_embedder.py --serve PORT        # newline-delimited JSON socket
"""

import argparse
import json
import os
import socket
import socketserver
import sys
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

FOVEAI = Path("/home/lumba/FoveAI")
MODEL_DIR = FOVEAI / ".sidecar" / "cache" / "models" / "Xenova" / "all-MiniLM-L6-v2"
ONNX = MODEL_DIR / "onnx" / "model_quantized.onnx"
TOKENIZER = MODEL_DIR / "tokenizer.json"

MAX_TOKENS = 256


class Embedder:
    def __init__(self, threads: int = 2):
        if not ONNX.exists() or not TOKENIZER.exists():
            raise SystemExit(f"model not cached at {MODEL_DIR}")
        opts = ort.SessionOptions()
        # Capped deliberately: AGENTS.md forbids running heavy CPU work alongside
        # the 9B, and unbounded ORT threads steal cycles from llama.cpp prompt eval.
        opts.intra_op_num_threads = max(1, min(threads, os.cpu_count() or 4))
        self.sess = ort.InferenceSession(
            str(ONNX), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.tok = Tokenizer.from_file(str(TOKENIZER))
        self.tok.enable_truncation(max_length=MAX_TOKENS)
        self.tok.enable_padding(pad_id=0, pad_token="[PAD]")
        self.dim = self.sess.get_outputs()[0].shape[-1]

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        encs = self.tok.encode_batch(texts)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        name = {i.name for i in self.sess.get_inputs()}
        if "token_type_ids" in name:
            feed["token_type_ids"] = np.zeros_like(ids)
        out = self.sess.run(None, feed)[0]
        # mean-pool over real tokens, then L2-normalise
        m = mask[..., None].astype(np.float32)
        pooled = (out * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / np.clip(norms, 1e-9, None)).astype(np.float32)


def diagnose(emb: Embedder) -> None:
    """Check whether semantic embeddings fix the string-equality clustering
    that made co_recall bind 'hello'/'Hello' and 'hi' into constellations."""
    print("=== 1. lexical problem (what TF-IDF did) ===")
    lex = [
        ("hello", ["hello", "Hello", "hi", "the mitochondria is the powerhouse"]),
    ]
    print("   TF-IDF treats 'hello' and 'Hello' as identical;")
    print("   'hi' shares no terms, so the two groups never co-fire.\n")

    print("=== 2. semantic clustering (MiniLM) ===")
    corpus = [
        "hello",
        "Hello",
        "hi",
        "hey there",
        "the mitochondria is the powerhouse of the cell",
        "mitochondria generate ATP through cellular respiration",
        "what is 2 + 2?",
        "can you add those numbers together",
        "I'm feeling anxious about tomorrow's meeting",
        "I am nervous about the presentation",
    ]
    v = emb.encode(corpus)
    sim = v @ v.T

    def show(i, j):
        a, b = corpus[i], corpus[j]
        print(f"   sim={sim[i, j]:.3f}   {a[:42]!r:46s} ~ {b[:42]!r}")

    print("   greetings that SHOULD cluster:")
    for i, j in [(0, 1), (0, 2), (0, 3), (8, 9)]:
        show(i, j)
    print("\n   topics that should be DISTINCT:")
    for i, j in [(4, 5), (6, 7), (0, 6), (4, 8)]:
        show(i, j)

    print("\n=== 3. verdict ===")
    greet = sim[0, 1]
    unrelated = sim[0, 6]
    print(f"   'hello' ~ 'Hello'          = {greet:.3f}")
    print(f"   'hello' ~ 'what is 2 + 2?' = {unrelated:.3f}")
    print(f"   margin = {greet - unrelated:+.3f}")
    print("   semantic recall separates meaning where TF-IDF saw surface form."
          if greet > unrelated + 0.2 else "   MARGIN TOO SMALL — embeddings will not fix it.")


class Handler(socketserver.StreamRequestHandler):
    embedder: Embedder = None

    def handle(self):
        emb = Handler.embedder
        for raw in self.rfile:
            raw = raw.strip()
            if not raw:
                continue
            try:
                req = json.loads(raw)
                vecs = emb.encode(req.get("input", []))
                resp = {"embedding": vecs.tolist(), "model": "all-MiniLM-L6-v2", "dim": emb.dim}
            except Exception as e:
                resp = {"error": f"{type(e).__name__}: {e}"}
            self.wfile.write((json.dumps(resp) + "\n").encode())
            self.wfile.flush()


class Threaded(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(emb: Embedder, port: int):
    Handler.embedder = emb
    srv = Threaded(("127.0.0.1", port), Handler)
    print(f"[embedder] listening on 127.0.0.1:{port} (dim={emb.dim}, cpu)")
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", type=int, metavar="PORT")
    ap.add_argument("--threads", type=int, default=2, metavar="N",
                    help="ONNX intra-op threads (default 2; keep low next to the 9B)")
    ap.add_argument("--diagnose", action="store_true")
    args = ap.parse_args()

    emb = Embedder(threads=args.threads)
    print(f"[embedder] model ready, dim={emb.dim}, threads={args.threads}", file=sys.stderr)
    if args.diagnose or not args.serve:
        diagnose(emb)
    else:
        serve(emb, args.serve)


if __name__ == "__main__":
    main()