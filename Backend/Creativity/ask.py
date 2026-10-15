#!/usr/bin/env python3
"""ask.py — default /ask endpoint adapter.

Wraps the tandem economy ladder + local juggler lanes behind one callable:
    POST /ask   {"prompt": "...", "verbose": bool}

Priority of lanes:
  1. :8408 9B MoQ-3.6 (GPU/CUDA)  — roleplay & heavy local answers (0 paid)
  2. :8407/:8406 local routers    — planning/classifying (0 paid)
  3. NVIDIA NIM race (nim_juggle) — free pool
  4. Gemini/others                — paid, economy mode only
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/lumba/FoveAI/Backend/Creativity")

LOCAL_ROLEPLAY = "http://127.0.0.1:8408"   # 9B Qwen3.5 MoQ-3.6, CUDA
LOCAL_ROUTER_FAST = "http://127.0.0.1:8406"  # 380M draft
LOCAL_ROUTER = "http://127.0.0.1:8407"     # 941M core

JEN_SYSTEM = (
    "You are Jen, warm witty companion of this console. Your real name is "
    "Jenny Ninebe. Answer in character, concise, no meta, no reasoning leaks."
)


def _post(url: str, payload: dict, timeout: int = 90) -> tuple[int, str]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except Exception as e:  # noqa: BLE001
        return 0, f"{e}"


def local_9b(prompt: str, is_roleplay: bool, history: list[dict] | None = None,
             temperature: float = 0.7, max_tokens: int = 500) -> tuple[int, str]:
    """9B companion lane on :8408 (CUDA, ~60 t/s)."""
    messages = [{"role": "system", "content": JEN_SYSTEM}]
    if history:
        messages.extend(history[-8:])
    messages.append({"role": "user", "content": prompt})
    st, body = _post(f"{LOCAL_ROLEPLAY}/v1/chat/completions",
                     {"messages": messages, "max_tokens": max_tokens,
                      "temperature": temperature,
                      # steered MoQ: kill the "Thinking Process" preamble
                      # so content lands inside the token budget
                      "chat_template_kwargs": {"enable_thinking": False}},
                     timeout=120)
    if st != 200:
        return st, ""
    try:
        d = json.loads(body)
        m = d["choices"][0]["message"]
        return 200, (m.get("content") or "").strip()
    except Exception:  # noqa: BLE001
        return 200, ""


def ask(prompt: str, verbose: bool = False) -> dict:
    """One-shot ask through the economic ladder. Returns structured result."""
    from tandem import run_tandem  # noqa: PLC0415 — late import keeps /ask fast

    t0 = time.time()
    is_roleplay = any(w in prompt.lower() for w in
                      ("remember", "before", "last time", "earlier",
                       "roleplay", "persona", "jen", "jenny", "conversation"))

    # lane 1: 9B companion for conversational/roleplay
    if is_roleplay:
        from tandem import memory_weave  # noqa: PLC0415
        weave = memory_weave(prompt)
        if weave:
            prompt = weave + "\n\n" + prompt
            if verbose:
                print(f"[ask] memory weave {len(weave)} chars", file=sys.stderr)
        st, txt = local_9b(prompt, is_roleplay)
        if st == 200 and txt:
            if verbose:
                print(f"[ask] lane: 9B companion (local, 0 paid)", file=sys.stderr)
            return {"ok": True, "lane": "local-9b", "paid_tokens": 0,
                    "answer": txt, "seconds": round(time.time() - t0, 2)}

    # lane 2+: tandem ladder (routers → free race → gemini fallback)
    import io
    import contextlib
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        rc = run_tandem(prompt, verbose=False)
    answer = buf_out.getvalue().strip()
    meta = buf_err.getvalue().strip().splitlines()
    report = meta[-1] if meta else ""
    paid = 0
    try:
        paid = int(report.split("paid tok")[0].split("~")[-1])
    except Exception:  # noqa: BLE001
        pass
    if verbose:
        print(f"[ask] lane: tandem rc={rc} report={report}", file=sys.stderr)
    return {"ok": rc == 0 and bool(answer), "lane": "tandem",
            "paid_tokens": paid, "answer": answer,
            "seconds": round(time.time() - t0, 2)}


if __name__ == "__main__":
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", nargs="+")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    r = ask(" ".join(a.prompt), a.verbose)
    print(json.dumps(r, ensure_ascii=False, indent=2))