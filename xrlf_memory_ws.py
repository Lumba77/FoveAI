#!/usr/bin/env python3
"""
xrlf_memory_ws.py — pluggable foveated-memory service (READ-ONLY).

Part of the XRLF WS redesign (see XRLF_WS_REDESIGN.md). Additive: touches no
live service, writes nothing, opens the MembraneEngine SQLite with mode=ro so
it cannot mutate the memory the running runtime owns.

Why read-only first: two writers on one NeDB/SQLite store is the known risk in
the design. Proving the contract works against read-only data lets the wiring
change happen later, as a single deliberate step, with rollback.

Transport is a low-latency WebSocket because clients are remote (Quest 3,
WebXR frontend) — see design doc §Decided.2.

Memory discipline (learned from the 2026-10-06 freeze): NO n x n similarity
matrix anywhere. Corpus vectors are held as one float32 matrix and each query
is a single matvec. For 4,287 turns that matrix is ~6.6 MB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

FOVEAI = Path("/home/lumba/FoveAI")
sys.path.insert(0, str(FOVEAI))

from xrlf_embedder import Embedder  # noqa: E402

DEFAULT_DB = (
    FOVEAI / "xrl_encoded" / "gemma-4-e2b-multimodal-v1.0.xrlf.cache" / "memory.db"
)

# Avatar markup is presentation, not content. Strip it before embedding so
# clustering judges meaning rather than which emotion tag happened to fire.
#
# The `<name: value>` form is only sometimes closed — 690/4289 turns carry an
# unterminated tag, which a `[^>]*>` pattern cannot match and which leaked
# verbatim into recall. Matching to the next `<` or end-of-string handles both.
TAGS = re.compile(r"<\w+:[^<>]*>?")
# Some turns are truncated mid-tag, leaving "<emotion" with neither the colon
# nor the closing bracket (157/4289). Match known tag names directly so those
# cannot leak either — scoped to a name list so real text is never touched.
KNOWN_TAGS = re.compile(
    r"<\/?(?:emotion|micro|movement|mode|thought|interaction|emote|gesture|avatar)\b[^<>]*>?",
    re.I,
)
PAREN_THOUGHT = re.compile(r"\((?:thought|mood)\s*:?[^)]*\)")
BLOCK_THOUGHT = re.compile(r"<\s*thought\s*>.*?<\s*/\s*thought\s*>", re.I | re.S)
WS = re.compile(r"\s+")
# A memory that is only the query asked back: topically maximal, informationally empty.
ECHO = re.compile(r"^[^.!?]{0,90}\?$")


def clean(text: str) -> str:
    """Strip avatar markup and internal reasoning.

    <thought> spans are the model's private reasoning channel and must never
    reach a user-facing surface. Measured 2026-10-06: only 10/400 sampled turns
    carried a thought tag, but those spans were long enough to dominate recall
    and surfaced verbatim in a live reflex test.
    """
    t = text or ""
    t = BLOCK_THOUGHT.sub(" ", t)
    t = PAREN_THOUGHT.sub(" ", t)
    t = TAGS.sub(" ", t)
    t = KNOWN_TAGS.sub(" ", t)
    return WS.sub(" ", t).strip()


def is_echo(query: str, text: str) -> bool:
    """True when a candidate is just the query reflected back.

    Measured: asking about the SPECTRAL-42 codeword returned three copies of
    the question itself at 0.80 / 0.56 / 0.44 — all topically maximal, none
    informative. They crowd out the real recall at 0.44.
    """
    q = clean(query).lower().rstrip(" ?.")
    t = clean(text).lower().rstrip(" ?.")
    if not q or not t:
        return False
    if ECHO.match(t) and len(t) < len(q) * 1.3:
        return True
    return t.startswith(q[: min(len(q), 30)]) or q.startswith(t[: min(len(t), 30)])


class MemoryIndex:
    """Read-only semantic index over the membrane corpus."""

    def __init__(self, db_path: Path, embedder: Embedder, chunk: int = 256):
        self.db_path = db_path
        self.emb = embedder
        self.chunk = chunk
        self.ids: list[int] = []
        self.roles: list[str] = []
        self.texts: list[str] = []
        self.vecs: np.ndarray | None = None  # (N, dim) float32
        self.loaded_at: float = 0.0

    def _connect(self) -> sqlite3.Connection:
        # mode=ro — this process cannot write, by construction.
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    def build(self) -> dict:
        t0 = time.time()
        con = self._connect()
        rows = con.execute(
            "select id, role, content from turns order by id"
        ).fetchall()
        con.close()

        for r in rows:
            txt = clean(r["content"])
            if len(txt) < 25:
                continue
            self.ids.append(r["id"])
            self.roles.append(r["role"])
            self.texts.append(txt)

        # chunked encode: bounded transient memory, never all-at-once
        chunks = []
        for i in range(0, len(self.texts), self.chunk):
            chunks.append(self.emb.encode(self.texts[i : i + self.chunk]))
        self.vecs = (
            np.vstack(chunks).astype(np.float32) if chunks else np.zeros((0, self.emb.dim), np.float32)
        )
        self.loaded_at = time.time()
        return {
            "turns_indexed": len(self.ids),
            "dim": int(self.emb.dim),
            "vector_mb": round(self.vecs.nbytes / 1e6, 2),
            "build_s": round(self.loaded_at - t0, 1),
            "read_only": True,
        }

    def recall(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.30,
        drop_echo: bool = True,
        oversample: int = 3,
    ) -> list[dict]:
        """Single matvec against the corpus. O(N) — never O(N^2).

        Echo suppression: over-fetch, drop candidates that merely repeat the
        query, then trim to k. Over-fetching keeps this O(N) — the cost is one
        extra cheap filter, not a second similarity pass.
        """
        if self.vecs is None or not self.ids:
            return []
        q = self.emb.encode([query])[0]
        sims = self.vecs @ q                      # (N,)
        k = max(1, min(int(k), len(self.ids)))
        want = min(len(self.ids), k * max(1, oversample) if drop_echo else k)
        top = np.argpartition(-sims, want - 1)[:want]
        top = top[np.argsort(-sims[top])]

        out: list[dict] = []
        seen: set[str] = set()
        for idx in top:
            s = float(sims[idx])
            if s < min_score:
                continue
            text = self.texts[idx]
            if drop_echo and is_echo(query, text):
                continue
            # collapse near-identical content returned twice
            key = text[:160].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "turn_id": self.ids[idx],
                    "role": self.roles[idx],
                    "score": round(s, 4),
                    "text": self.texts[idx][:400],
                }
            )
            if len(out) >= k:
                break
        return out

    def stats(self) -> dict:
        con = self._connect()
        try:
            turns = con.execute("select count(*) from turns").fetchone()[0]
            archived = con.execute(
                "select count(*) from sqlite_master where type='table' and name='turns_archive'"
            ).fetchone()[0]
            n_arch = con.execute("select count(*) from turns_archive").fetchone()[0] if archived else 0
            co = con.execute("select count(*) from co_recall").fetchone()[0]
            ident = [
                dict(r)
                for r in con.execute("select key, value from identity").fetchall()
            ]
        finally:
            con.close()
        return {
            "turns_in_db": turns,
            "turns_indexed": len(self.ids),
            "archived": n_arch,
            "co_recall_edges": co,
            "identity": ident,
            "vector_mb": round(self.vecs.nbytes / 1e6, 2) if self.vecs is not None else 0,
        }


class MemoryWS:
    """Line-delimited JSON over WebSocket. One op per message, one reply."""

    def __init__(self, index: MemoryIndex, reflex_threshold: float = 0.62):
        self.ix = index
        self.reflex_threshold = reflex_threshold

    @staticmethod
    def build_context(hits: list[dict], token_budget: int) -> str:
        """Render recall as background reference for prompt injection.

        Mirrors MembraneEngine.weave_context's contract: discrete notes, not
        dialogue, wrapped so the model treats it as material to reason over
        rather than a turn to continue.
        """
        if not hits:
            return ""
        notes = []
        used = 0
        max_chars = max(200, token_budget * 4)
        for h in hits:
            txt = " ".join(h["text"].split())[:260]
            if not txt:
                continue
            who = "User said" if h["role"] == "user" else "You previously said"
            line = f"- ({who}, {h['score']:.2f}) {txt}"
            if used + len(line) > max_chars:
                break
            notes.append(line)
            used += len(line)
        if not notes:
            return ""
        return (
            "<background_memory>\n"
            "Relevant things you remember from earlier with this person:\n"
            + "\n".join(notes)
            + "\n</background_memory>\n"
            "[Use the above only if it actually answers the question. It is "
            "reference material, not something to repeat. Otherwise ignore it "
            "and respond normally to the current message.]"
        )

    async def handle(self, ws) -> None:
        peer = getattr(ws, "remote_address", None)
        print(f"[memws] client connected {peer}", flush=True)
        try:
            async for raw in ws:
                try:
                    req = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"error": "bad json"}))
                    continue
                reply = await self.dispatch(req)
                await ws.send(json.dumps(reply, default=str))
        except Exception as e:  # noqa: BLE001
            print(f"[memws] connection error: {type(e).__name__}: {e}", flush=True)
        finally:
            print(f"[memws] client disconnected {peer}", flush=True)

    async def dispatch(self, req: dict) -> dict:
        op = req.get("op")
        if op == "health":
            return {"ok": True, "op": op, "service": "xrlf-memory-ws", "read_only": True}
        if op == "stats":
            return {"ok": True, "op": op, **self.ix.stats()}
        if op == "recall":
            q = req.get("query") or ""
            if not q.strip():
                return {"ok": False, "error": "query required"}
            return {
                "ok": True,
                "op": op,
                "query": q,
                "results": self.ix.recall(q, k=int(req.get("k", 5))),
            }
        if op == "prefetch":
            # Reflex, phase 1: buffer the recall for a later safe-boundary inject.
            # No stream mutation happens here by design.
            q = req.get("query") or ""
            if not q.strip():
                return {"ok": False, "error": "query required"}
            t0 = time.time()
            hits = self.ix.recall(q, k=int(req.get("k", 4)))
            top = hits[0]["score"] if hits else 0.0
            return {
                "ok": True,
                "op": op,
                "fire": bool(hits and top >= self.reflex_threshold),
                "score": round(top, 4),
                "threshold": self.reflex_threshold,
                "ms": round((time.time() - t0) * 1000, 1),
                "buffered": hits,
            }
        if op == "weave":
            # Context injection: memory the model reads BEFORE generating.
            #
            # The live test showed why this is the op that matters: post-hoc
            # reflex surfaces evidence to the user but the model has already
            # committed, so it quoted the question back instead of answering.
            # Prompt-level injection is what makes recall usable by the model.
            #
            # Read-only is sufficient: this builds a string from a query and
            # returns it. Nothing here writes. (The MembraneEngine equivalent,
            # weave_context, needs its write-capable load() only because it
            # also commits co-recall edges — which this path deliberately skips.)
            q = req.get("query") or ""
            if not q.strip():
                return {"ok": False, "error": "query required"}
            budget = int(req.get("token_budget", 320))
            t0 = time.time()
            hits = self.ix.recall(q, k=int(req.get("k", 4)))
            block = self.build_context(hits, budget)
            return {
                "ok": True,
                "op": op,
                "fire": bool(hits and hits[0]["score"] >= self.reflex_threshold),
                "score": round(hits[0]["score"], 4) if hits else 0.0,
                "threshold": self.reflex_threshold,
                "ms": round((time.time() - t0) * 1000, 1),
                "context": block,
                "hits": len(hits),
            }
        return {"ok": False, "error": f"unknown op: {op!r}"}


async def amain(args) -> None:
    emb = Embedder()
    ix = MemoryIndex(Path(args.db), emb)
    info = ix.build()
    print(f"[memws] indexed {info['turns_indexed']} turns, {info['vector_mb']}MB vectors "
          f"in {info['build_s']}s (read-only)", flush=True)

    import websockets

    server = MemoryWS(ix, reflex_threshold=args.reflex_threshold)

    async def handler(ws):
        await server.handle(ws)

    async with websockets.serve(handler, args.host, args.port, max_size=1 << 20):
        print(f"[memws] READY ws://{args.host}:{args.port}", flush=True)
        await asyncio.Future()


def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only XRLF foveated memory WS service")
    ap.add_argument("--host", default="127.0.0.1")
    # 8404 is the free slot in the fleet's 84xx block (8400 proxy, 8414 dash,
    # 8402 XRLF, 8403 model WS, 8405 soul, 8411 TTS, 8411 relay, 8411 STT).
    ap.add_argument("--port", type=int, default=8404)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--reflex-threshold", type=float, default=0.62)
    args = ap.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()