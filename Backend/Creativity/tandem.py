#!/usr/bin/env python3
"""tandem.py — paid planner + free juggler pool, relayed as one answer.

Architecture (the tandem):
    user prompt ──▶ GEMINI 3.7 FLASH (paid, small budget)
                       │  ONE cheap call: classify + (if complex) plan
                       │  decision: ROUTINE | PLAN
                       ▼
        ROUTINE ──▶ NIM juggle race (free pool) ──▶ relay answer as-is
        PLAN    ──▶ NIM pool executes each leg in parallel
                 ──▶ GEMINI synthesizes legs into the final answer
                 ──▶ relay (paid tokens: ~2 short calls + synthesis,
                     legwork is FREE on NVIDIA builds)

The user never sees the machinery — they see one answer (relay), and
stderr carries the plumbing for us developers.

Why this is 2-3x more token-efficient:
  The paid model stops doing legwork: no long context reads, no file
  dumps, no test runs. It plans (small, structured) and synthesizes
  (compressed legs). The heavy lifting tokens burn on the free builds.

Usage:
  python3 tandem.py "prompt"
  python3 tandem.py --verbose "prompt"        # show legs + races on stderr
  python3 tandem.py --dry-run "prompt"        # show routing decision only
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from nim_juggle import race, extract, env, load_state, PoolEntry, save_state  # noqa: E402

import urllib.request

# ── config ──────────────────────────────────────────────────────────────

GOOGLE_KEY = ""
def _load_google() -> None:
    global GOOGLE_KEY
    # env first, then opencode config
    GOOGLE_KEY = env("GOOGLE_API_KEY") or env("FOVEAI_GOOGLE_API_KEY")
    if not GOOGLE_KEY:
        try:
            cfg = json.loads(Path(
                "/home/lumba/.config/opencode/opencode.jsonc").read_text())
            GOOGLE_KEY = cfg["provider"]["google"]["options"]["apiKey"]
        except Exception:
            pass
_load_google()

GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/"
              "models/{model}:generateContent?key={k}")

PLANNER_MODEL = "gemini-2.5-flash"       # cheap, fast, quota-friendly
SYNTH_MODEL = PLANNER_MODEL

ROUTINE_MARKERS = ("hi", "hello", "thanks", "ok", "ping", "who are you",
                   "what time", "status", "health")

ROUTER_INSTRUCTION = """Tandem router. Cheap call, reply ONLY one of:

A) "A: <answer>" — if trivial (greeting/smalltalk/one-liner). Max 2 short sentences.

B) JSON, nothing else — if any real work:
{"p":["leg","leg"],
 "m":1}
   - "p": 1-3 self-contained prompts for a free model (facts inline, no tools)
   - "m": 0 = synthesize legs after (default) · 1 = relay BEST leg directly

Request:"""

SYNTH_INSTRUCTION = """Merge the legs below into one direct answer for the
user. Keep the best facts; resolve contradictions; no meta-commentary; no
mention of legs or models.

Legs:
"""

LOCAL_ROUTER_FAST = "http://127.0.0.1:8406"   # 380M draft — 140ms classifier
LOCAL_ROUTER = "http://127.0.0.1:8407"         # 941M core — planning
LOCAL_ROLEPLAY = "http://127.0.0.1:8408"      # 4B super-coder — roleplay/memory legs

# ── XRLF ROUTING ENVELOPE ───────────────────────────────────────────
# The repo's instructive language, compiled for the router's role:
# key := value directives frame the task so the tiny model's context is
# fully occupied by ONE well-formed protocol instead of hallucinated
# training-memory formats (cache JSONs, timestamps).
XRLF_ROUTING_ENVELOPE = """XRLF.3.ROUTER.CONFIG.START

DESCRIPTION:
  Tandem juggle routing for the FoveAI companion.

ROLE:
  classifier := route only; never answer in prose
  worker := outsourced; legs execute in a free external pool
  output := strictly one line; either 'A: <answer>' or JSON plan

ROUTING:
  trivial := greeting, one-liner, identity, single fact
  complex := research, comparison, planning, multi-part work
  trivial_result := A: <max 2 short sentences>
  complex_result := {"p":["leg1","leg2","leg3"],"m":1}

INVARIANTS:
  deny := file system access in legs
  deny := explanations about self
  deny := meta-commentary about routing
  inline := facts needed by legs are embedded in leg text

XRLF.3.ROUTER.CONFIG.END
"""

def local_router_call(prompt: str, max_tokens: int = 200) -> tuple[str, str]:
    """The free local router — FAST 380M draft on :8408 (140ms), steered by
    the XRLF routing envelope (repo language). 0 paid tokens.
    Returns (status, text)."""
    body = json.dumps({"messages": [
        {"role": "system", "content": XRLF_ROUTING_ENVELOPE},
        {"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.2}).encode()
    req = urllib.request.Request(LOCAL_ROUTER_FAST + "/v1/chat/completions",
                                 data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
            return "200", d["choices"][0]["message"]["content"]
    except Exception as e:
        return "000", str(e)[:150]

def gemini_call(prompt: str, model: str = PLANNER_MODEL,
                max_tokens: int = 800) -> tuple[str, str]:
    """Returns (status, text-or-error)."""
    url = GEMINI_URL.format(model=model, k=GOOGLE_KEY)
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens,
                             "temperature": 0.4,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            d = json.load(r)
            parts = d["candidates"][0]["content"]["parts"]
            return "200", "".join(p.get("text", "") for p in parts)
    except urllib.error.HTTPError as e:
        return str(e.code), e.read().decode()[:300]
    except Exception as e:
        return "000", str(e)

MEM_DB = Path("/home/lumba/FoveAI/db/agent_memory.db")

def memory_weave(prompt: str, sessions: int = 6, memories: int = 5,
                 persona: str = "") -> str:
    """Fill in the blanks for legs from the foveated memory layer.
    Returns a compact context block (persona + related memories + recent
    turns) to prepend to a leg prompt. Best-effort: DB issues → ''. """
    if not MEM_DB.exists():
        return ""
    parts: list[str] = []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True, timeout=2)
        # long prompts never LIKE-match; use keyword tokens instead
        stop = {"the", "and", "that", "was", "what", "did", "was", "remember",
                "hey", "jen", "about", "we", "our", "how", "many", "with",
                "for", "this", "does", "were", "are", "you", "your"}
        toks = [w.strip("?,.!:'\"") for w in prompt.split()]
        toks = [t for t in toks if len(t) > 3 and t.lower() not in stop][:8]
        rows: list[tuple[str, str]] = []
        for tok in toks:
            rows.extend(con.execute(
                "SELECT key, value FROM agent_memories "
                "WHERE value LIKE ? OR key LIKE ? ORDER BY importance DESC "
                "LIMIT ?", (f"%{tok}%", f"%{tok}%", memories)).fetchall())
        seen: set[str] = set()
        rows = [r for r in rows if not (r[0] in seen or seen.add(r[0]))]
        rows.sort(key=lambda r: -(len(r[0])))
        for k, v in rows:
            parts.append(f"memory[{k}]: {v[:160]}")
        hist = con.execute(
            "SELECT role, content FROM agent_chat_history "
            "ORDER BY id DESC LIMIT ?", (sessions,)).fetchall()
        convo = "\n".join(f"{r}: {c[:120]}" for r, c in reversed(hist))
        if convo:
            parts.append(f"recent: {convo}")
        con.close()
    except Exception:
        return ""
    if persona:
        parts.append(f"persona: {persona}")
    return "\n".join(parts)

def looks_routine(prompt: str) -> bool:
    """Cheap local prefilter: tiny prompts that need no plan never cost
    Google tokens (the free pool answers standalone)."""
    p = prompt.strip().lower()
    if len(p) < 120 and any(p.startswith(m) or p == m for m in ROUTINE_MARKERS):
        return True
    return False

# ── the tandem flow ─────────────────────────────────────────────────────

def run_tandem(prompt: str, verbose: bool = False,
               dry_run: bool = False,
               history: list[dict] | None = None) -> int:
    t0 = time.time()
    paid_tokens = 0
    free_pool_used: list[str] = []

    # Context: prior turns first, current question last.
    history = [h for h in (history or []) if h.get("content") != prompt]
    convo: list[dict] = history[-11:] + [{"role": "user", "content": prompt}]

    # ── shortcut 1: obvious routine → straight to free pool (0 paid tokens)
    if looks_routine(prompt):
        if verbose: print("[tandem] prefilter: ROUTINE (0 paid tokens)",
                          file=sys.stderr)
        if dry_run: print("ROUTINE (prefilter)"); return 0
        model, body, codes = race(["openai/gpt-oss-20b",
                                   "nvidia/nemotron-3-super-120b-a12b"],
                                  convo)
        if model:
            free_pool_used.append(model)
            print(extract(body))
            _report(time.time() - t0, 0, free_pool_used, verbose)
            return 0
        print("[tandem] free pool failed; falling back to planner",
              file=sys.stderr)

    # ── stage 1: route via LOCAL router first (free, instant); gemini only
    # if the tiny model errors or returns garbage
    _plan_ctx = "\n".join(f"{m['role']}: {m['content'][:300]}"
                          for m in convo[-8:])
    st, txt = local_router_call(ROUTER_INSTRUCTION + "\n" + _plan_ctx[-4000:])
    _local_ok = st == "200" and (
        _parse_plan(txt) is not None
        or txt.strip().lower().startswith("a:")
        or txt.strip().lower().startswith("b:")
    )
    if not _local_ok:
        if verbose: print(f"[tandem] local router unusable ({st}) → gemini",
                          file=sys.stderr)
        st, txt = gemini_call(ROUTER_INSTRUCTION + "\n" + _plan_ctx[-4000:],
                              max_tokens=300)
        if st != "200":
            # any planner failure (429/5xx/key) → FULL-FREE local mode:
            # core router plans (CUDA, instant) or the prompt itself is
            # the leg. Never return rc=2 when we still have a local lane.
            if verbose:
                print(f"[tandem] planner {st} → CORE router fallback "
                      "(full-free mode)", file=sys.stderr)
            import urllib.request as _u
            body = json.dumps({"messages": [
                {"role": "system", "content": XRLF_ROUTING_ENVELOPE},
                {"role": "user", "content":
                 'Plan JSON ONLY {"p":[legs],"m":0} — conversation:\n'
                 + _plan_ctx[-3500:]}],
                "max_tokens": 400, "temperature": 0.2}).encode()
            txt = ""
            try:
                with _u.urlopen(_u.Request(LOCAL_ROUTER + "/v1/chat/completions",
                                data=body, headers={"Content-Type": "application/json"}), timeout=45) as r:
                    txt = json.load(r)["choices"][0]["message"]["content"]
            except Exception as e:
                if verbose:
                    print(f"[tandem] core router failed ({e}) → "
                          "prompt-as-leg", file=sys.stderr)
            parsed = _parse_plan(txt) if txt else None
            if parsed is not None:
                kwlegs = [l for l in (parsed.get("p") or []) if l]
                real = [k for k in kwlegs if len(k) >= 12
                        and not k.lower().startswith("leg")]
                legs = real or [prompt]
            else:
                legs = [prompt]   # free pool executes the raw prompt — 0 paid
            if verbose:
                print(f"[tandem] FULL-FREE: {len(legs)} leg(s), planner "
                      f"{'core' if parsed is not None else 'bypassed'}",
                      file=sys.stderr)
            # jump straight to the leg loop — the core's txt may be garbage
            # and must NOT be re-parsed/relayed as a 'routine' answer
            st, txt = "200", json.dumps({"p": legs, "m": 0})
        else:
            paid_tokens += 4 + max(1, len(prompt) // 4)
    elif txt.strip().lower().startswith("a:") and _parse_plan(txt) is None:
        if verbose:
            print("[tandem] ROUTINE answered by LOCAL router (0 paid)",
                  file=sys.stderr)
        print(_strip_answer(txt))
        _report(time.time() - t0, 0, [], verbose)
        return 0
    elif verbose:
        print("[tandem] routed by LOCAL router (0 paid)", file=sys.stderr)

    parsed = _parse_plan(txt)
    if parsed is None:
        # planner answered directly (A: ...) → relay as-is
        if verbose:
            print(f"[tandem] ROUTINE via planner ({time.time()-t0:.1f}s)",
                  file=sys.stderr)
        print(_strip_answer(txt))
        _report(time.time() - t0, paid_tokens, [], verbose)
        return 0

    legs = parsed.get("p") or parsed.get("plan") or []
    # discard placeholder legs ("leg1") — shallow planners emit them; the
    # user prompt itself is the only real leg we can trust
    legs = [l for l in legs if l and (len(str(l)) >= 12
            and not str(l).lower().startswith("leg"))] or [prompt]
    relay_best = (parsed.get("m") == 1) and len(legs) == 1
    if dry_run:
        print(f"PLAN: {len(legs)} legs → free pool")
        for i, l in enumerate(legs):
            print(f"  leg {i+1}: {l[:70]}")
        return 0

    if verbose:
        print(f"[tandem] PLAN: {len(legs)} legs (free pool executes)",
              file=sys.stderr)
        for i, l in enumerate(legs):
            print(f"   leg {i+1}: {l[:80]}", file=sys.stderr)

    # ── stage 2: legs run through the FREE juggle race, parallel-ish
    leg_answers: list[str] = []
    # one race per leg; the juggle keeps everything warm so legs are fast
    for i, leg in enumerate(legs):
        weave = ""
        roleplay_leg = any(w in leg.lower() for w in
               ("remember", "before", "last time", "earlier", "session",
                "roleplay", "persona", "jen", "jenny", "conversation"))
        if roleplay_leg:
            weave = memory_weave(leg)
            if weave and verbose:
                print(f"   leg {i+1}: memory weave {len(weave)} chars",
                      file=sys.stderr)
        legtext = (f"{weave}\n\n" if weave else "") + leg
        if roleplay_leg:
            # roleplay/memory lane: the 4B core, dedicated + XRLF persona envelope
            import urllib.request as _u
            body = json.dumps({"messages": [
                {"role": "system", "content":
                 "You are Jen, warm witty companion. Reply in character, "
                 "max 120 words, no meta."},
                {"role": "user", "content": legtext}],
                "max_tokens": 350, "temperature": 0.7}).encode()
            try:
                with _u.urlopen(_u.Request(LOCAL_ROLEPLAY + "/v1/chat/completions",
                                data=body, headers={"Content-Type": "application/json"}), timeout=90) as r:
                    d = json.load(r)
                    ans_body = json.dumps(d)
                    model = "local:4b-super-coder"
                    body = ans_body
                ans = extract(body)
            except Exception as e:
                ans, model = "", None
        else:
            # race legs: instruction goes in the SYSTEM role — baking it
            # into the user text made the leaker models recite it back
            model, body, codes = race(
                ["openai/gpt-oss-20b", "nvidia/nemotron-3-super-120b-a12b",
                 "moonshotai/kimi-k3"],
                [{"role": "system",
                  "content": "Answer directly, final answer only, no "
                             "thinking out loud, no reasoning traces. "
                             "Max 120 words. Start with the substance. "
                             "Use the earlier turns for context."}]
                + _leg_convo(convo, legtext))
            ans = extract(body) if model else ""
        if model: free_pool_used.append(model)
        # reject thinking-aloud leg drafts (nemotron reasoning leakage):
        bad = ans.strip().lower().startswith(
            ("we need", "user wants", "but the", "the user", "maybe",
             "perhaps", "the instruction", "i ", "let's", "okay"))
        leg_answers.append(ans if (ans and not bad and len(ans) > 25) else "")
        if verbose:
            print(f"   leg {i+1} → {model or 'FAILED'} "
                  f"({len(ans)} chars)", file=sys.stderr)

    # ── stage 3: relay best leg (0 extra paid) or synth
    good = [a for a in leg_answers if a]
    if relay_best and good:
        print(good[0])
        _report(time.time() - t0, paid_tokens, free_pool_used, verbose)
        return 0
    if not good:
        # every leg leaked thinking → relay the raw first leg stripped
        raw = extract(body) if 'body' in dir() else ''
        print(raw[:600] or "all legs failed this round")
        _report(time.time() - t0, paid_tokens, free_pool_used, verbose)
        return 0
    leg_answers = good
    legs_blob = "\n".join(f"--- leg {i+1} ---\n{a}" for i, a in
                          enumerate(leg_answers))
    st, txt = gemini_call(SYNTH_INSTRUCTION + "\n" + legs_blob,
                          model=SYNTH_MODEL, max_tokens=1200)
    if st != "200":
        # synthesis failed → relay best leg as graceful fallback
        best = max(leg_answers, key=len)
        print(best)
        paid_tokens += 4 + len(legs_blob) // 4
        _report(time.time() - t0, paid_tokens, free_pool_used, verbose)
        return 0
    paid_tokens += 4 + len(legs_blob) // 4 + 300
    print(txt)
    _report(time.time() - t0, paid_tokens, free_pool_used, verbose)
    return 0

def _parse_plan(txt: str) -> dict | None:
    t = txt.strip()
    low = t.lower()
    if low.startswith("a:") or low.startswith("b"):
        # strip the letter marker (router sometimes echoes B before json)
        for mark in ("A:", "a:", "B", "b", "B:", "b:"):
            if t.startswith(mark):
                t = t[len(mark):].strip()
        low = t.lower()
        if low.startswith("a:"):
            return None
    if low.startswith("a:") and not t.lstrip().startswith("{"):
        return None
    # if it even LOOKS like json anywhere, it's a plan attempt
    if "{" in t and ('"plan"' in t or '"p"' in t):
        pass
    elif len(t) < 40 and "{" not in t:   # very short non-json = direct answer
        return None
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        base = t[i:j + 1]
        for cand in (base, base + '"]}', base.rstrip(',') + '"}]}'):
            try:
                d = json.loads(cand)
                if isinstance(d.get("plan"), list) or isinstance(d.get("p"), list):
                    return d
            except Exception:
                continue
    # unparseable plan → treat the text as a direct answer
    return None

def _leg_convo(convo: list[dict], legtext: str) -> list[dict]:
    """Prior turns + the current leg — a leg must never run amnesiac."""
    prior = [m for m in convo if m.get("content") != legtext]
    return prior[-11:] + [{"role": "user", "content": legtext}]


def _strip_answer(txt: str) -> str:
    return txt.strip()[2:].strip() if txt.strip().lower().startswith("a:") \
        else txt.strip()

def _report(dt: float, paid_tokens: int, free: list[str],
            verbose: bool) -> None:
    print(f"\n─ [tandem {dt:.1f}s · ~{paid_tokens} paid tok · "
          f"free pool: {', '.join(free) or '—'}]",
          file=sys.stderr if not verbose else sys.stderr)

def _parse_history(raw: str) -> list[dict]:
    """Prior turns handed over by the proxy — legs must not answer blind."""
    import json as _json
    try:
        msgs = _json.loads(raw)
    except Exception:
        return []
    if not isinstance(msgs, list):
        return []
    out = []
    for m in msgs:
        if isinstance(m, dict) and m.get("role") in ("system", "user", "assistant") \
                and isinstance(m.get("content"), str) and m["content"].strip():
            out.append({"role": m["role"], "content": m["content"]})
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    verbose = "--verbose" in args or "-v" in args
    dry = "--dry-run" in args
    history: list[dict] = []
    if "--history" in args:
        i = args.index("--history")
        if i + 1 < len(args):
            history = _parse_history(args[i + 1])
            del args[i:i + 2]
    args = [a for a in args if a not in ("--verbose", "-v", "--dry-run")]
    if not args:
        print(__doc__)
        sys.exit(1)
    sys.exit(run_tandem(" ".join(args), verbose, dry, history))