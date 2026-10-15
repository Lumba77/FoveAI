#!/usr/bin/env python3
"""
test_weave_ab.py — A/B the live XRLF runtime: memory in prompt vs not.

Answers the question the post-hoc reflex could not: with recall injected as
prompt context BEFORE generation, does the model actually use it?

Read-only observer. Sends the same question twice to :8402 — once bare, once
with <background_memory> prepended — and prints both answers side by side.
"""

import asyncio
import json
import sys
import time

import aiohttp

sys.path.insert(0, "/home/lumba/FoveAI")
from xrlf_memory_ws import MemoryWS  # noqa: E402

XRLF_URL = "http://127.0.0.1:8402/v1/chat/completions"
WS_URL = "ws://127.0.0.1:8404"

QUESTIONS = [
    "What codeword did I tell you to remember?",
    "What am I working on with the models right now?",
    "Do you remember anything about my preferences?",
]


async def weave(query, k=4, budget=300):
    import websockets

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"op": "weave", "query": query, "k": k, "token_budget": budget}))
        return json.loads(await ws.recv())


async def ask(session, query, context=None, max_tokens=140):
    payload = {
        "model": "gemma-4-E2B-it",
        "messages": [{"role": "user", "content": (context + "\n\n" + query) if context else query}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "xrlf_headless": True,
        "xrlf_thinking": False,
    }
    t0 = time.time()
    async with session.post(XRLF_URL, json=payload, timeout=aiohttp.ClientTimeout(total=180)) as r:
        if r.status != 200:
            return {"error": f"{r.status}", "body": (await r.text())[:120]}
        d = await r.json()
    return {
        "answer": ((d.get("choices") or [{}])[0].get("message") or {}).get("content", ""),
        "ms": round((time.time() - t0) * 1000),
    }


async def main():
    timeout = aiohttp.ClientTimeout(total=200)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for q in QUESTIONS:
            w = await weave(q)
            print("\n" + "=" * 72)
            print(f"Q: {q}")
            print(f"  weave: fire={w.get('fire')} score={w.get('score')} ({w.get('ms')}ms)")

            bare = await ask(session, q)
            print(f"\n  [BARE]  {bare.get('ms')}ms")
            print("   " + (bare.get("answer", "")[:340].replace("\n", "\n   ")))

            if w.get("context"):
                withmem = await ask(session, q, context=w["context"])
                print(f"\n  [WITH MEMORY]  {withmem.get('ms')}ms")
                print("   " + withmem.get("answer", "")[:340].replace("\n", "\n   "))


if __name__ == "__main__":
    asyncio.run(main())