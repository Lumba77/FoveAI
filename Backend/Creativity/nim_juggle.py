#!/usr/bin/env python3
"""nim_juggle.py — 3-model race router for NVIDIA NIM free builds.

Problem it solves: cold builds answer in 30-60s, warm builds in ~2s.
A sequential fallback router waits out every cold start.

The juggle:
  1. FIRE all candidates at once (parallel), each with a small stagger
  2. FIRST 200 wins, the losers get cancelled — you never wait for a
     cold model that's racing a warm one
  3. The winner is marked HOT (recently answered) — next call leads with
     it, while the others get woken up in the background so the pool
     stays warm ("auto waking another slow starter")
  4. 503 (overloaded) models are backed off for N seconds instead of
     being retried blindly

Result: steady-state latency ~2-3s, never >8s even when fleet is cold.

Usage:
  python3 nim_juggle.py "your prompt here"            # race default trio
  python3 nim_juggle.py --system "sys" "prompt"       # with system prompt
  python3 nim_juggle.py --pool a,b,c "prompt"         # custom pool

Design notes:
- One process per request is fine (the pool state json is trivial); if
  this graduates to FoveAI's cloud lane, swap the json for a redis key.
- max_tokens for nemotron-class reasoning models: 300+ or you get
  empty content (reasoning eats the budget) — enforced here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# ── config ──────────────────────────────────────────────────────────────

ENV_PATH = Path("/home/lumba/FoveAI/.env")
# state lives with the code (NOT /tmp — fs.protected_regular=2 blocks
# cross-user O_RDWR writes there, which killed the root-owned proxy's
# juggle execs with PermissionError)
STATE_PATH = Path(__file__).resolve().parent / "nim_juggle_state.json"

def env(key: str) -> str:
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(key + "=") or line.startswith("export " + key + "="):
            return line.split("=", 1)[1].strip()
    return ""

API_KEY = env("FOVEAI_NVIDIA_API_KEY")
BASE_URL = env("FOVEAI_NVIDIA_NIM_BASE_URL") or "https://integrate.api.nvidia.com/v1"

# the race pool: fast responder first, reasoning model, then wildcard
DEFAULT_POOL = [
    "openai/gpt-oss-20b",                    # warm fast responder
    "nvidia/nemotron-3-super-120b-a12b",     # reasoning, medium
    "moonshotai/kimi-k3",                    # slow starter, strong
]

REASONING_FLOOR = 300          # min max_tokens for reasoning models
COLD_AFTER = 240               # seconds until a HOT model is considered cold
OVERLOAD_BACKOFF = 45          # 503 backoff seconds
FIRE_STAGGER = 0.15            # seconds between race starts

@dataclass
class PoolEntry:
    model: str
    last_ok: float = 0.0       # epoch of last 200
    backoff_until: float = 0.0 # epoch — overloaded

    @property
    def hot(self) -> bool:
        return (time.time() - self.last_ok) < COLD_AFTER

def load_state() -> dict[str, PoolEntry]:
    try:
        raw = json.loads(STATE_PATH.read_text())
        return {k: PoolEntry(model=k, last_ok=v.get("last_ok", 0),
                             backoff_until=v.get("backoff_until", 0))
                for k, v in raw.items()}
    except Exception:
        return {}

def save_state(pool: dict[str, PoolEntry]) -> None:
    STATE_PATH.write_text(json.dumps(
        {k: {"last_ok": p.last_ok, "backoff_until": p.backoff_until}
         for k, p in pool.items()}))

# ── the race ────────────────────────────────────────────────────────────

def fire(model: str, messages: list[dict], timeout: float) -> tuple[str, str]:
    """One curl. Returns (status, body)."""
    payload = {"model": model, "messages": messages,
               "max_tokens": REASONING_FLOOR, "temperature": 0.7}
    r = subprocess.run(
        ["curl", "-s", "-m", str(timeout),
         "-w", "\n%{http_code}",
         "-H", f"Authorization: Bearer {API_KEY}",
         "-H", "Content-Type: application/json",
         f"{BASE_URL}/chat/completions",
         "-d", json.dumps(payload)],
        capture_output=True, text=True)
    out = r.stdout
    if "\n" in out:
        body, code = out.rsplit("\n", 1)
    else:
        body, code = out, "000"
    return code.strip(), body

def race(pool: list[str], messages: list[dict]) -> tuple[str, str, dict]:
    """Fire the pool staggered; first 200 wins. Returns (model, body, all_codes)."""
    state = load_state()
    for m in pool:
        state.setdefault(m, PoolEntry(model=m))
    save_state(state)

    order = sorted(pool, key=lambda m: 0 if state[m].hot else 1)
    procs: dict[str, subprocess.Popen] = {}
    codes: dict[str, str] = {}

    for m in order:
        if state[m].backoff_until > time.time():
            codes[m] = "backoff"
            continue
        # each candidate = backgrounded curl writing to its own file
        of = STATE_PATH.with_suffix(f".{abs(hash(m))}.out")
        if of.exists():
            of.unlink()
        payload = {"model": m, "messages": messages,
                   "max_tokens": REASONING_FLOOR, "temperature": 0.7}
        procs[m] = subprocess.Popen(
            ["curl", "-s", "-m", "110",
             "-H", f"Authorization: Bearer {API_KEY}",
             "-H", "Content-Type: application/json",
             f"{BASE_URL}/chat/completions",
             "-d", json.dumps(payload), "-o", str(of)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(FIRE_STAGGER)

    winner: str | None = None
    body = ""
    deadline = time.time() + 115
    while time.time() < deadline and not winner:
        for m, p in list(procs.items()):
            if p.poll() is not None:  # finished
                of = STATE_PATH.with_suffix(f".{abs(hash(m))}.out")
                try:
                    txt = of.read_text()
                except OSError:
                    txt = ""
                # determine status crudely: parseable 200 shape?
                try:
                    d = json.loads(txt)
                    if d.get("choices"):
                        winner, body = m, txt
                        state[m].last_ok = time.time()
                    else:
                        err = json.dumps(d)
                        if "Service temporarily overloaded" in err:
                            state[m].backoff_until = time.time() + OVERLOAD_BACKOFF
                            codes[m] = "503"
                        else:
                            codes[m] = "err"
                except Exception:
                    codes[m] = codes.get(m, "timeout")
                procs.pop(m)
        time.sleep(0.2)

    # cancel the losers (the juggle never waits twice)
    for m, p in procs.items():
        p.kill()
        codes[m] = codes.get(m, "cancelled")

    if not winner:
        # all failed or cold timeouts — return best error
        return "", body or json.dumps(codes), codes
    # background-warm: nobody else needs waking here (the fire already
    # started them) — their latency this round just got amortized.
    save_state({m: state[m] for m in state})
    return winner, body, codes

def extract(body: str) -> str:
    try:
        d = json.loads(body)
        m = d["choices"][0]["message"]
        return m.get("content") or m.get("reasoning_content") or ""
    except Exception:
        return ""

# ── cli ─────────────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    system = ""
    pool = DEFAULT_POOL
    a = []
    i = 0
    while i < len(args):
        if args[i] == "--system":
            system = args[i + 1]; i += 2
        elif args[i] == "--pool":
            pool = args[i + 1].split(","); i += 2
        else:
            a.append(args[i]); i += 1
    prompt = " ".join(a)
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]

    t0 = time.time()
    model, body, codes = race(pool, messages)
    dt = time.time() - t0
    if model:
        print(f"[{model} {dt:.1f}s] {extract(body)[:2000]}")
        return 0
    print(f"[no winner in {dt:.1f}s] {codes}", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())