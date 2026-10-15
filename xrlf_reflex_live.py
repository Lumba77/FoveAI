#!/usr/bin/env python3
"""
xrlf_reflex_live.py — end-to-end live test of the XRLF reflex.

Joins the two isolated halves:
  1. xrlf_memory_ws.py   prefetch  (semantic recall, ~3ms)
  2. xrlf_interrupt.py   inject    (safe-boundary placement)

Streams from the live XRLF runtime (:8402), prefetches memory in parallel at
turn start, then injects at the first safe boundary. Nothing is rewired and
recall-interceptor.js is untouched — this is an observer that re-runs the
generation and compares against a baseline.

    python xrlf_reflex_live.py --q "question" [--no-reflex] [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import aiohttp

sys.path.insert(0, "/home/lumba/FoveAI")
from xrlf_interrupt import find_safe_boundary, inject  # noqa: E402

WS_URL = "ws://127.0.0.1:8404"
XRLF_URL = "http://127.0.0.1:8402/v1/chat/completions"


async def prefetch(session, query: str, k: int = 4) -> dict:
    """Query the read-only memory WS. Session is accepted for symmetry."""
    import websockets

    async with websockets.connect(WS_URL) as ws:
        t0 = time.time()
        await ws.send(json.dumps({"op": "prefetch", "query": query, "k": k}))
        reply = json.loads(await ws.recv())
        reply["round_trip_ms"] = round((time.time() - t0) * 1000, 1)
        return reply


async def stream_generate(query: str, max_tokens: int = 160):
    """Yield (piece, cumulative_text) deltas from the live runtime, streaming."""
    payload = {
        "model": "gemma-4-E2B-it",
        "messages": [{"role": "user", "content": query}],
        "max_tokens": max_tokens,
        "temperature": 0.4,
        "stream": True,
        "xrlf_headless": True,
    }
    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(XRLF_URL, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"XRLF {resp.status}: {body[:200]}")
            buf = ""
            async for raw in resp.content:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    buf += piece
                    yield piece, buf


def format_memory(hits: list[dict]) -> str:
    lines = []
    for h in hits[:3]:
        txt = " ".join(h["text"].split())[:220]
        lines.append(f"  (relevance {h['score']:.2f}) {h['role']}: {txt}")
    return "\n".join(lines)


async def run(query: str, use_reflex: bool, max_tokens: int) -> dict:
    report: dict = {"query": query, "reflex": use_reflex}
    t_start = time.time()

    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        pf = None
        if use_reflex:
            # Phase 1: prefetch in parallel with generation start
            pf = asyncio.create_task(prefetch(session, query))

        emitted = ""
        injected_at = None
        t_first = None
        full = ""

        async for piece, sofar in stream_generate(query, max_tokens):
            if t_first is None:
                t_first = time.time()
            if use_reflex and injected_at is None:
                pf_result = pf.done() and pf.result()
                # Only inject once memory is in hand AND boundary is safe
                if pf_result and pf_result.get("buffered"):
                    b = find_safe_boundary(sofar)
                    if b.safe:
                        emitted = inject(
                            sofar[: b.offset],
                            format_memory(pf_result["buffered"]),
                            sofar[b.offset :],
                        )
                        injected_at = b.offset
            emitted += piece
            full += piece

        report["gen_first_token_ms"] = round(((t_first or time.time()) - t_start) * 1000, 1)
        report["gen_total_ms"] = round((time.time() - t_start) * 1000, 1)
        report["injected"] = injected_at is not None
        report["inject_offset"] = injected_at
        if use_reflex and pf is not None:
            p = pf.result()
            report["prefetch"] = {
                "fire": p.get("fire"),
                "score": p.get("score"),
                "threshold": p.get("threshold"),
                "service_ms": p.get("ms"),
                "round_trip_ms": p.get("round_trip_ms"),
                "hits": len(p.get("buffered") or []),
            }
        report["raw_output"] = full
        report["composed_output"] = emitted
    return report


async def amain(args):
    rep = await run(args.q, not args.no_reflex, args.max_tokens)
    if args.json:
        print(json.dumps(rep, indent=2))
        return

    print(f"\nQUERY: {rep['query']}")
    print(f"  prefetch      : {rep.get('prefetch')}")
    print(f"  TTFT          : {rep['gen_first_token_ms']} ms")
    print(f"  total         : {rep['gen_total_ms']} ms")
    print(f"  injected      : {rep['injected']} at offset {rep['inject_offset']}")
    print("\n--- RAW (no memory) ---")
    print(rep["raw_output"][:700])
    print("\n--- COMPOSED (with reflex) ---")
    print(rep["composed_output"][:900])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True)
    ap.add_argument("--no-reflex", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=160)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()