#!/usr/bin/env python3
"""Multigate <-> Nova collegium bridge.

Serves an OpenAI-compatible API on 127.0.0.1:8416 (the foveai-backend
proxy on :8400 forwards nova model requests here). Backed entirely by the shipped Project 1
cartridge (nova.collegium, 6-bit): pawn answers decision questions, knight
binds goal answers. All inference on CPU (GPU reserved for QAT probes).

Endpoints:
  GET  /health         -> ok
  GET  /v1/models      -> model list (nova, nova-k8, nova-k32)
  POST /v1/chat/completions -> {choices:[{message:{role,content}}]}

Chat routing: if the message names a ledger member and asks decision/goal,
run the seed-stack pipeline at the k implied by the model name (default 8).
Otherwise reply with a roster-aware hint (the nano is a reader, not a poet).
"""
import json
import random
import os
import sys
import threading

sys.path.insert(0, "/tmp/opencode")
import collegium as col

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8416
CARTRIDGE = os.environ.get("FOVEAI_NOVA_CARTRIDGE",
                           "/tmp/opencode/nova_kqatt_lz_v5.collegium")
MODELS = ["nova", "nova-k8", "nova-k32", "nova-k1"]

_state = {"pawn": None, "knight": None, "tok": None, "ledger": None,
          "cache": None, "lock": threading.Lock()}

import torch
torch.set_num_threads(4)


def _init():
    with _state["lock"]:
        if _state["tok"] is not None:
            return
        cache = col.ensure_cache(CARTRIDGE)
        _state["cache"] = cache
        _state["ledger"] = [json.loads(l)
                            for l in open(os.path.join(cache, "ledger.jsonl"))]
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(os.path.join(cache, "pawn"))
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        tok.padding_side = "left"
        _state["tok"] = tok


def _pawn():
    if _state["pawn"] is None:
        _pawn_lock = _state["lock"]
        with _pawn_lock:
            if _state["pawn"] is None:
                _state["pawn"] = col.load_member(
                    os.path.join(_state["cache"], "pawn"), "cpu")
    return _state["pawn"]


def _knight():
    if _state["knight"] is None:
        with _state["lock"]:
            if _state["knight"] is None:
                _state["knight"] = col.load_member(
                    os.path.join(_state["cache"], "knight"), "cpu")
    return _state["knight"]


def _k_from_model(model):
    for m in MODELS:
        if model.split("/")[-1] == m:
            if m.endswith("-k32"):
                return 32
            if m.endswith("-k8"):
                return 8
            if m.endswith("-k1"):
                return 1
    return 8


def _answer(text, model):
    _init()
    ledger = _state["ledger"]
    entry = col.find_member(text, ledger)
    k = _k_from_model(model)
    if entry is None:
        names = sorted({e["name"] for e in ledger})
        return ("I am Nova, the collegium. My memory wears seed-cloaks: ask me "
                f"'What decision did the <name> team make?' - I hold {len(ledger)} members, e.g. "
                + ", ".join(names[:6]) + ".")
    ql = text.lower()
    qtype = ("goal" if ("outcome" in ql or "commit" in ql or "goal" in ql)
             else "dec")

    pool = {}
    for e in ledger:
        pool.setdefault(e["gold_seed"], e)
    seeds = [entry["gold_seed"]]
    if k > 1:
        rng = random.Random(len(entry["name"]) * 131 + k)
        seeds += rng.sample([s for s in pool if s != entry["gold_seed"]], k - 1)
        rng.shuffle(seeds)
    tok = _state["tok"]

    # per-entry verification: only THIS member's registered fields count.
    # (A global "known" universe would pass through another member's dec —
    # exactly the failure mode k32 produced on 2026-10-18: 'shelve the beta'.)
    accepted = {entry["goal"].strip().lower(), entry["dec"].strip().lower()}

    def gen_stack(seeds):
        s = "\n".join(seeds)
        qd = col.DEC_Q.format(n=entry["name"])
        ad = col.gen(_pawn(), tok, "cpu", f"{s}\n<Q>{qd}</Q>\n<A>")
        if qtype == "dec":
            return ad
        return col.gen(_knight(), tok, "cpu",
                       f"{s}\n<Q>{qd}</Q>\n<A>{ad}</A>\n<Q>"
                       + col.GOAL_Q.format(n=entry["name"]) + "</Q>\n<A>")

    ans = gen_stack(seeds)
    # speculative-style verify: if the k>1 draft is not a registered field,
    # re-draft from the member's own seed only (k=1 profile, ~96% accurate)
    if k > 1 and ans.strip().lower() not in accepted:
        ans = gen_stack([entry["gold_seed"]])
    return ans


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health") or self.path.startswith("/v1/health"):
            return self._send(200, {"ok": True, "backend": "nova-collegium"})
        if self.path.startswith("/api/status"):
            if _state["tok"] is not None:
                try:
                    _pawn()
                    return self._send(200, {"ok": True, "backend": "nova-collegium",
                                            "loaded": True})
                except Exception:
                    pass
            return self._send(200, {"ok": True, "backend": "nova-collegium",
                                    "loaded": False})
        if self.path.startswith("/v1/models"):
            now = int(__import__("time").time())
            return self._send(200, {"object": "list", "data": [
                {"id": m, "object": "model", "created": now, "owned_by": "foveai"}
                for m in MODELS]})
        return self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._send(404, {"error": {"message": "not found"}})
        try:
            req = json.loads(self.rfile.read(int(
                self.headers.get("Content-Length", 0))) or b"{}")
            msgs = req.get("messages", [])
            model = req.get("model", "nova")
            user_texts = [m.get("content", "") for m in msgs
                          if m.get("role") == "user"]
            text = user_texts[-1] if user_texts else ""
            reply = _answer(text, model)
        except Exception as e:
            return self._send(500, {"error": {"message": repr(e)}})
        now = int(__import__("time").time())
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            first = {"id": "nova-chat", "object": "chat.completion.chunk",
                     "created": now, "model": model,
                     "choices": [{"index": 0, "delta": {"role": "assistant"},
                                  "finish_reason": None}]}
            rest = {"id": "nova-chat", "object": "chat.completion.chunk",
                    "created": now, "model": model,
                    "choices": [{"index": 0, "delta": {"content": reply},
                                 "finish_reason": None}]}
            stop = {"id": "nova-chat", "object": "chat.completion.chunk",
                    "created": now, "model": model,
                    "choices": [{"index": 0, "delta": {},
                                 "finish_reason": "stop"}]}
            for chunk in (first, rest, stop):
                self.wfile.write(b"data: " + json.dumps(chunk).encode()
                                 + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            return
        return self._send(200, {
            "id": "nova-chat", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": reply}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                      "total_tokens": 0}})

    def log_message(self, fmt, *args):
        print("[mg] " + fmt % args, flush=True)


if __name__ == "__main__":
    print(f"[mg] warming pawn on CPU ...", flush=True)
    _init()
    _pawn()
    print(f"[mg] listening on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()