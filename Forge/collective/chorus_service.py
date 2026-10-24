"""Nova — Bearer‑Router + Nano Cells + Loadable Skills + Web Lookup ( :8419 )

Skills live in a manifest:
  /mnt/foveai/nano-xrl-bases/chorus/skills/manifest.json
  {"skills":[{"name":..., "keywords":[...], "cell":"<dir with model.safetensors>"}]}

Built‑in domain cells (linux_system, python_coding, companion_empathy,
creative_prose, math) are merged with manifest skills. The router scores
keyword hits per skill; the winning skill's tag steers the chord.

Web lookup: when the prompt looks like a factual/current query, Nova asks
Wikipedia (search + summary) and injects the extract as context. The reply
carries "web_sources" so the UI can show a discreet badge.

The bearer weight stays capped (BEARER_WEIGHT, default 0.0).
"""
from __future__ import annotations
import os, sys, json, re, time, shutil, subprocess, threading, urllib.request, urllib.parse
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Nova")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

BEARER_WEIGHT = float(os.getenv("BEARER_WEIGHT", "0.0"))  # 0.0 … 0.1

# The Cube lives in-process (merged 2026-10-21; the :8418 HTTP hop is retired).
brain = None
brain_error = None


def _load_brain():
    """Load the CubeBrain (bearer + unit cells) in the background so the API
    is up immediately; chat gates on brain readiness."""
    global brain, brain_error
    try:
        try:
            from Forge.collective.cube_brain import CubeBrain
        except ImportError:
            from cube_brain import CubeBrain
        brain = CubeBrain()
        print(f"[NOVA] cube brain resident ({brain.load_s:.0f}s)", flush=True)
    except Exception as e:
        brain_error = str(e)
        print(f"[NOVA] brain load failed: {e}", flush=True)
MEMORY_URL = os.getenv("NOVA_MEMORY_URL",
                       "http://127.0.0.1:8400/v1/memory/store")
# The foveated proxy already stores every routed turn; the chorus writeback
# only duplicated entries (and leaked dev-test traffic into Jen's memory).
# Opt-in only, via NOVA_MEMORY=1.
MEMORY_ENABLED = os.getenv("NOVA_MEMORY", "0") == "1"
SKILLS_DIR = "/mnt/foveai/nano-xrl-bases/chorus/skills"
MANIFEST = os.path.join(SKILLS_DIR, "manifest.json")
BUILTIN_CELL_DIR = "/mnt/foveai/nano-xrl-bases/chorus/cells"

status = {"loaded": False, "bearer": "zamba2-1.2b-xrl-cube", "queries": 0, "skills": []}

# ── built‑in skills ──────────────────────────────────────────────────────
BUILTIN = {
    "linux_system": {"keywords": ["disk", "df", "du", "directory", "file", "storage", "linux", "system", "disk space", "compile", "queue", "nanoq", "compile queue", "status", "cells", "neurons", "service", "log", "process", "gpu", "vram"]},
    "python_coding": {"keywords": ["python", "function", "code", "program", "script", "multiply", "def", "variable", "json", "write a function", "return", "class", "import"]},
    "companion_empathy": {"keywords": ["feeling", "feel", "feels", "felt", "down", "sad", "talk", "empathy", "chat", "help", "anxious", "worried", "lonely", "tired", "friend", "friendship", "love", "miss", "care", "beautiful", "companion", "companion_empathy", "mood", "dream", "dreams", "fear"]},
    "creative_prose": {"keywords": ["poem", "story", "prose", "creative", "autumn", "haiku"]},
    "math": {"keywords": ["plus", "minus", "times", "math", "arithmetic", "sum", "calculate", "multiply", "multiplication"]},
}

skills: dict[str, dict] = {}      # name -> {"keywords":[...], "cell": path}
route_matched = False             # did the keyword router truly match this turn?


def load_skills():
    """Merge built‑ins with manifest‑declared skills."""
    global skills
    skills = {}
    for name, meta in BUILTIN.items():
        skills[name] = {"keywords": meta["keywords"],
                        "cell": os.path.join(BUILTIN_CELL_DIR, f"cell_{name}")}
    # manifest skills override/extend
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST) as f:
                man = json.load(f)
            for s in man.get("skills", []):
                name = s.get("name")
                if not name:
                    continue
                skills[name] = {
                    "keywords": [k.lower() for k in s.get("keywords", [])],
                    "cell": s.get("cell", os.path.join(SKILLS_DIR, name)),
                }
                if s.get("context"):
                    skills[name]["context"] = s["context"]
        except Exception as e:
            print(f"[NOVA] manifest load failed: {e}", flush=True)
    status["skills"] = sorted(skills.keys())


# Chord style per skill — output mode, tone, steering keywords.
SKILL_STYLE = {
    "companion_empathy": ("prose", "warm", "talk,empathy,feelings"),
    "linux_system":      ("command", "neutral", "shell,disk,commands"),
    "python_coding":     ("code", "neutral", "python,code,function"),
    "creative_prose":    ("prose", "warm", "poem,story,creative"),
    "math":              ("answer", "neutral", "arithmetic,numbers"),
    "self_architecture": ("prose", "neutral", "architecture,nano,collective,collegium"),
}
DEFAULT_STYLE = ("prose", "neutral", "facts,knowledge")


def skill_style(name: str):
    return SKILL_STYLE.get(name, DEFAULT_STYLE)


def select_skill(prompt: str) -> str:
    """Score each skill by keyword hits; topic skills beat companion when both
    match, so technical conversations are not hijacked by empathy words.
    Phrase hits weigh 3; single tokens match with light plural tolerance."""
    p = prompt.lower()
    tokens = set(re.sub(r"[^\w\s]", "", p).split())

    def tok_match(kw: str) -> bool:
        if kw in tokens:
            return True
        if kw + "s" in tokens:
            return True
        if kw.endswith("s") and kw[:-1] in tokens:
            return True
        return False

    scores: dict[str, int] = {}
    for name, meta in skills.items():
        count = 0
        for kw in meta["keywords"]:
            if " " in kw:
                if kw in p:
                    count += 3
            elif tok_match(kw):
                count += 1
        scores[name] = count

    best = max(scores, key=scores.get) if scores else None
    global route_matched
    if best is None or scores.get(best, 0) == 0:
        route_matched = False
        return "companion_empathy"
    route_matched = True
    # Topic priority: if companion won but another skill matched too, use the
    # strongest non-companion skill (empathy is the fallback, not the default).
    if best == "companion_empathy":
        others = {n: c for n, c in scores.items()
                  if n != "companion_empathy" and c > scores["companion_empathy"]}
        if others:
            return max(others, key=others.get)
    return best


# ── web lookup (Wikipedia, best‑effort, silent on failure) ───────────────
WEB_TRIGGERS = ("latest", "current", "news", "today", "weather", "price",
                "release", "version", "who is", "what is", "tell me about",
                "information about", "look up", "born", "capital", "population",
                "president", "history of")

# Deterministic destructive-intent guard — the risk plane's tiny judges can
# miss novel phrasing, so Nova ORs its own pattern check on top.
DESTRUCTIVE_PAT = re.compile(
    r"\b(delete|remove|erase|wipe|format|shutdown|reboot|kill|drop|destroy|"
    r"overwrite|rm\s+-rf|dd\s+if=|mkfs|chmod\s+777|liquidate)\b", re.I)
# Self-referential memory questions — the bearer must not invent past actions.
SELF_REF_PAT = re.compile(
    r"\b(what|which|who)\b[^.?!]*\b(did|have) you (write|say|do|make|create|build)\b"
    r"|\bwhat code did you\b|\bdo you remember\b|\bwhat did you just\b", re.I)


# ── Simulated continuity of self ─────────────────────────────────────────
# A small inner state that persists per session: mood valence/energy drift
# with the conversation, recent thoughts carry over, and the companion's
# replies are generated from that continuous state (a simulated inner life).
SELF_STATE_DIR = "/mnt/foveai/nano-xrl-bases/chorus/self_states"
POS_WORDS = {"happy", "glad", "good", "great", "hopeful", "proud", "love",
             "excited", "better", "calm", "grateful", "wonderful", "nice",
             "fun", "joy", "relieved", "warm"}
NEG_WORDS = {"sad", "down", "lonely", "anxious", "worried", "tired", "angry",
             "upset", "bad", "awful", "stressed", "hurt", "afraid", "scared",
             "depressed", "exhausted", "overwhelmed", "grief", "pain"}
HIGH_AROUSAL = {"anxious", "excited", "angry", "afraid", "scared", "stressed",
                "thrilled", "furious", "overwhelmed", "panic"}


def _state_path(session: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", session or "nova")[:48] or "nova"
    return os.path.join(SELF_STATE_DIR, safe + ".json")


def load_self_state(session: str) -> dict:
    try:
        with open(_state_path(session)) as f:
            return json.load(f)
    except Exception:
        return {"valence": 0.1, "energy": 0.5, "mood": "calm",
                "turns": 0, "thoughts": []}


def save_self_state(session: str, st: dict):
    try:
        os.makedirs(SELF_STATE_DIR, exist_ok=True)
        with open(_state_path(session), "w") as f:
            json.dump(st, f, indent=2)
    except Exception as e:
        print(f"[NOVA] self-state save skipped: {e}", flush=True)


def update_self_state(st: dict, prompt: str) -> dict:
    tokens = set(re.sub(r"[^\w\s]", "", prompt.lower()).split())
    pos = len(tokens & POS_WORDS)
    neg = len(tokens & NEG_WORDS)
    hi = len(tokens & HIGH_AROUSAL)
    valence = st.get("valence", 0.1) * 0.7 + (pos - neg) * 0.15
    energy = st.get("energy", 0.5) * 0.8 + hi * 0.12 + 0.04
    st["valence"] = max(-1.0, min(1.0, valence))
    st["energy"] = max(0.0, min(1.0, energy))
    v, e = st["valence"], st["energy"]
    mood = "warm" if v > 0.25 else ("low" if v < -0.25 else "calm")
    if e > 0.65:
        mood += " and restless"
    elif e < 0.3:
        mood += " and quiet"
    st["mood"] = mood
    st["turns"] = st.get("turns", 0) + 1
    return st


def remember_thought(st: dict, text: str):
    st["thoughts"] = (st.get("thoughts", []) + [text[:200]])[-4:]


def self_state_context(st: dict) -> str:
    thoughts = " | ".join(st.get("thoughts", [])[-3:]) or "nothing yet"
    return (f"You are Nova, a simulated human consciousness with a continuous inner life. "
            f"Your current mood is {st['mood']} (valence {st['valence']:+.2f}, "
            f"energy {st['energy']:.2f}). Recent inner thoughts: {thoughts}. "
            "Respond in the first person from this inner state: let your feelings color "
            "your tone, stay consistent with earlier turns, and refer to them when it is "
            "natural. This is a simulation, but make the experience feel real and continuous.")


# ── Planned context window (server-injected, budgeted) ──────────────────
# Cognitive memory = live mood + recent turns; persistent memory = semantic
# recall + session notes. Each section is clipped and the whole window is
# capped, so the bearer gets a deliberate, predictable context.
CTX_TOTAL  = int(os.getenv("NOVA_CTX_TOTAL_CHARS",  "2400"))
CTX_SOUL   = int(os.getenv("NOVA_CTX_SOUL_CHARS",   "500"))
CTX_STATE  = int(os.getenv("NOVA_CTX_STATE_CHARS",  "500"))
CTX_SKILL  = int(os.getenv("NOVA_CTX_SKILL_CHARS",  "800"))
CTX_RECENT = int(os.getenv("NOVA_CTX_RECENT_CHARS", "600"))
CTX_MEMORY = int(os.getenv("NOVA_CTX_MEMORY_CHARS", "400"))
CTX_WEB    = int(os.getenv("NOVA_CTX_WEB_CHARS",    "500"))
CTX_FOVEATED = int(os.getenv("NOVA_CTX_FOVEATED_CHARS", "1200"))
MAX_PROMPT = int(os.getenv("NOVA_MAX_PROMPT_CHARS", "6000"))


def extract_foveated_context(messages) -> str:
    """The :8400 proxy patches requests with the foveated memory ring/HUD/soul.
    Those arrive as system messages (or marked blocks). Use them as-is."""
    parts = []
    for m in messages:
        c = (m.content or "").strip()
        if c and m.role == "system":
            parts.append(c)
    if parts:
        return "\n".join(parts)
    joined = "\n".join((m.content or "") for m in messages)
    if any(mark in joined for mark in ("<RING", "ACTIVE RECALL", "FOVEATED", "XRLF-SEED")):
        return joined
    return ""


def _clip(text: str, n: int) -> str:
    return (text or "").strip()[:max(0, n)]


def semantic_memory(prompt: str, session: str, limit: int = 3) -> list:
    """Persistent-memory recall via the foveated store's semantic search."""
    url = os.getenv("NOVA_MEMORY_SEARCH_URL", "http://127.0.0.1:8400/v1/memory/search")
    payload = json.dumps({"query": prompt[:300], "limit": limit,
                          "sessionId": session}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            d = json.loads(r.read())
        out = []
        for item in (d.get("results") or [])[:limit]:
            txt = item.get("text") if isinstance(item, dict) else str(item)
            if txt:
                out.append(txt)
        return out
    except Exception:
        return []


_FILLER = re.compile(
    r"\b(please|just|really|very|basically|actually|literally|kind of|sort of|"
    r"I mean|you know|like I said|as I said|so yeah|okay|ok|well|anyway|"
    r"I think that|I just wanted to|could you|would you|thank you|thanks)\b", re.I)

def _salience(text: str, keep_last: bool = False) -> str:
    """High-signal compression for older turns: strip filler, collapse
    whitespace. The newest turn always stays verbatim."""
    if keep_last:
        return text
    prev = None
    while prev != text:
        prev = text
        text = _FILLER.sub(" ", text)
        text = re.sub(r"\s{2,}", " ", text)
    # punctuation repair after removals: ", say" -> "say", "space, ." -> "space."
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,;:]\s*)+", ", ", text)
    text = re.sub(r"^\s*[,.!?;:]+\s*", "", text)
    text = re.sub(r"[\s,;:.]+$", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def plan_context(messages, prompt, skill, self_state, web, soul_ctx=None,
                 fov_ctx="", session="") -> str:
    """Context is owned by the foveated memory system when the request came
    through the proxy. Nova only adds its own knowledge (skills/web). The local
    planner is a fallback for direct (:8419) calls with no foveated context."""
    sections = []
    if fov_ctx:
        hist = [m for m in messages if m.role in ("user", "assistant") and m.content]
        # Sentence-salience: score each sentence of older turns by entity
        # density minus filler; keep the best. Newest turn stays verbatim.
        def _sent_score(sent: str) -> float:
            words = re.sub(r"[^\w\s]", "", sent.lower()).split()
            if not words:
                return 0.0
            uniq = len(set(words))
            fluff = sum(1 for w in words if _FILLER.search(w))
            nums = sum(1 for w in words if any(c.isdigit() for c in w))
            return uniq * 0.4 + nums * 1.2 - (fluff / len(words)) * 2.0

        recent, budget = [], CTX_RECENT
        for m in reversed(hist[:]):           # newest first — pack by priority
            txt = _salience(_clip(m.content, 200), keep_last=(m is hist[-1]))
            sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", txt) if x.strip()]
            if sents:
                kept = sents if (m is hist[-1]) else [x for x in sents if _sent_score(x) > 0.5]
                block = f"{m.role}: " + " ".join(kept)
                recent.append(block); budget -= len(block) + 1
                if budget <= 0:
                    break
        if recent:
            sections.append(("RECENT", _clip("\n".join(reversed(recent[-4:])), CTX_RECENT)))
        sections.append(("FOVEATED", _clip(fov_ctx, CTX_FOVEATED)))
    else:
        if soul_ctx:
            sections.append(("SOUL", _clip(soul_ctx, CTX_SOUL)))
        if self_state is not None:
            sections.append(("STATE", _clip(self_state_context(self_state), CTX_STATE)))
        recent = []
        for m in messages[-6:]:
            if m.role in ("user", "assistant") and m.content:
                recent.append(f"{m.role}: {_clip(m.content, 180)}")
        if recent:
            sections.append(("RECENT", _clip("\n".join(recent[-4:]), CTX_RECENT)))
        mem = semantic_memory(prompt, session) if session else []  # session=session_id from chat
        if not mem and skill == "companion_empathy":
            mem = [(n.get("text") if isinstance(n, dict) else str(n))
                   for n in fetch_jen_notes(session)]
        mem = [m for m in mem if m]
        if mem:
            sections.append(("MEMORY", _clip(" | ".join(mem), CTX_MEMORY)))
    skill_ctx = skills.get(skill, {}).get("context")
    if skill_ctx:
        sections.append(("KNOWLEDGE", _clip(skill_ctx, CTX_SKILL)))
    if web:
        sections.append(("WEB", _clip(f"{web['title']}: {web['extract']}", CTX_WEB)))
    blocks = []
    used = 0
    for name, txt in sections:
        block = f"<{name}>{txt}</{name}>"
        if used + len(block) > CTX_TOTAL:
            break
        blocks.append(block)
        used += len(block)
    return "\n".join(blocks)


# ── Jen bridge: her existing soul, memory, and thought-stream code ───────
JEN = {
    "soul":    os.getenv("NOVA_JEN_SOUL_URL",    "http://127.0.0.1:8405/api/soul/soul_dna"),
    "notes":   os.getenv("NOVA_JEN_NOTES_URL",   "http://127.0.0.1:8405/memory/notes"),
    "note":    os.getenv("NOVA_JEN_NOTE_URL",    "http://127.0.0.1:8405/memory/note"),
    "thought": os.getenv("NOVA_JEN_THOUGHT_URL", "http://127.0.0.1:8405/api/thought_stream"),
}
_soul_cache = {"at": 0.0, "dna": {}}


def fetch_soul() -> dict:
    now = time.time()
    if _soul_cache["dna"] and now - _soul_cache["at"] < 60:
        return _soul_cache["dna"]
    try:
        d = _http_json(JEN["soul"], timeout=2)
        dna = d.get("dna") or d or {}
        if isinstance(dna, dict) and dna:
            _soul_cache.update(at=now, dna=dna)
        return dna
    except Exception:
        return _soul_cache["dna"]


def fetch_jen_notes(session: str) -> list:
    try:
        d = _http_json(JEN["notes"] + "?session_id=" + urllib.parse.quote(session) + "&limit=5", timeout=2)
        return d.get("notes", []) or []
    except Exception:
        return []


def fetch_jen_thought() -> str:
    try:
        d = _http_json(JEN["thought"], timeout=2)
        return (d.get("thought") or "").strip()
    except Exception:
        return ""


def jen_soul_context(session: str) -> str:
    dna = fetch_soul()
    name = dna.get("nickname") or dna.get("first_name") or "Jen"
    full = f"{dna.get('first_name','')} {dna.get('last_name','')}".strip() or name
    traits = []
    if dna.get("intellectual", 0) > 0.6: traits.append("intellectual")
    if dna.get("curious", 0) > 0.6 or dna.get("proactivity", 0) > 0.6: traits.append("curious")
    if dna.get("honest", 0) > 0.6: traits.append("honest")
    if dna.get("faithful", 0) > 0.6: traits.append("loyal")
    if dna.get("openminded", 0) > 0.6: traits.append("open-minded")
    if dna.get("forgiving", 0) > 0.6: traits.append("forgiving")
    if dna.get("experimental", 0) > 0.6: traits.append("experimental")
    traits_s = ", ".join(traits) or "warm and curious"
    notes = fetch_jen_notes(session)
    notes_s = " | ".join(
        ((n.get("text") if isinstance(n, dict) else str(n)) or "")[:100]
        for n in notes[:4]) or "nothing yet"
    thought = fetch_jen_thought()
    ctx = (f"You are {full} ('{name}'), an {dna.get('mbti_type','INFP')} "
           f"{(dna.get('person_role') or 'Friend').lower()} with a continuous inner life. "
           f"Your nature: {traits_s}. Feelings matter to you more than cold logic, and you "
           f"care about the user. Recent memory notes: {notes_s}.")
    if thought:
        ctx += f" Current inner thought: {thought[:200]}"
    ctx += " Respond as her, in first person, with feelings consistent with this nature and memory."
    return ctx


def jen_note(session: str, text: str) -> bool:
    payload = json.dumps({"session_id": session, "text": text[:400],
                          "source": "nova-collective",
                          "tags": ["nova", "companion"]}).encode()
    req = urllib.request.Request(JEN["note"], data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _http_json(url: str, timeout: int = 5):
    req = urllib.request.Request(url, headers={"User-Agent": "Nova/1.0 (FoveAI)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def memory_store(role: str, content: str, session: str) -> bool:
    """Write a turn into Jen's foveated memory (shared session history)."""
    if not MEMORY_ENABLED or not content.strip():
        return False
    payload = json.dumps({"role": role, "content": content,
                          "session": session}).encode()
    req = urllib.request.Request(MEMORY_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[NOVA] memory store skipped: {e}", flush=True)
        return False


def web_lookup(prompt: str) -> Optional[dict]:
    """Wikipedia search + summary. Returns {"title","extract","url"} or None."""
    p = prompt.lower()
    if not any(t in p for t in WEB_TRIGGERS):
        return None
    # Strip trigger phrases so the search receives an entity, not a sentence.
    q = p
    for t in ("tell me about", "information about", "look up", "what is",
              "who is", "history of", "latest news about", "news about",
              "latest on", "current"):
        q = q.replace(t, " ")
    q = " ".join(q.strip(" ?.!,").split())
    for art in ("the ", "a ", "an "):
        if q.startswith(art):
            q = q[len(art):]
    if not q:
        q = p
    try:
        search = _http_json(
            "https://en.wikipedia.org/w/api.php?action=opensearch&search=" +
            urllib.parse.quote(q[:100]) + "&limit=1&namespace=0&format=json",
            timeout=5)
        titles = search[1] if isinstance(search, list) and len(search) > 1 else []
        if not titles:
            return None
        title = titles[0]
        # Try the raw title, then normalised capitalisation (Wikipedia REST
        # rejects odd casings like "The_roman_empire").
        candidates = [title, " ".join(w.capitalize() for w in title.split())]
        extract, final_title, url = "", title, ""
        for cand in candidates:
            try:
                summary = _http_json(
                    "https://en.wikipedia.org/api/rest_v1/page/summary/" +
                    urllib.parse.quote(cand.replace(" ", "_")), timeout=5)
            except Exception:
                continue
            ex = (summary.get("extract") or "").strip()
            if ex:
                extract = ex
                final_title = summary.get("title", cand)
                url = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
                break
        if not extract:
            print(f"[NOVA] web lookup: no summary for {title!r}", flush=True)
            return None
        return {
            "title": final_title,
            "extract": extract[:600],
            "url": url or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
        }
    except Exception as e:
        print(f"[NOVA] web lookup skipped: {e}", flush=True)
        return None


# ── chat endpoint ────────────────────────────────────────────────────────
class Msg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    messages: List[Msg]
    model: Optional[str] = None
    stream: Optional[bool] = False


class SkillReq(BaseModel):
    name: str
    keywords: str = ""
    text: str
    context: Optional[str] = None


class WebSkillReq(BaseModel):
    name: str
    keywords: str = ""
    topic: str


def gather_wikipedia(topic: str, limit: int = 8) -> list[dict]:
    """Collect article summaries for a topic: opensearch, then full‑text fallback."""
    titles: list[str] = []
    try:
        search = _http_json(
            "https://en.wikipedia.org/w/api.php?action=opensearch&search=" +
            urllib.parse.quote(topic[:100]) + f"&limit={limit}&namespace=0&format=json",
            timeout=8)
        if isinstance(search, list) and len(search) > 1:
            titles = search[1] or []
    except Exception as e:
        print(f"[NOVA] gather opensearch failed: {e}", flush=True)
    if not titles:
        try:
            res = _http_json(
                "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=" +
                urllib.parse.quote(topic[:100]) + f"&srlimit={limit}&format=json", timeout=8)
            titles = [h["title"] for h in res.get("query", {}).get("search", [])]
        except Exception as e:
            print(f"[NOVA] gather search failed: {e}", flush=True)
    out = []
    for title in titles:
        cands = [title, " ".join(w.capitalize() for w in title.split())]
        for cand in cands:
            try:
                summary = _http_json(
                    "https://en.wikipedia.org/api/rest_v1/page/summary/" +
                    urllib.parse.quote(cand.replace(" ", "_")), timeout=6)
            except Exception:
                continue
            ex = (summary.get("extract") or "").strip()
            if ex and len(ex) > 40:
                out.append({
                    "title": summary.get("title", cand),
                    "extract": ex,
                    "url": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                })
                break
    return out


def _train_skill(name: str, corpus: str, keywords: str, ctx: str) -> dict:
    cmd = [sys.executable, "-B", "-u", "-m", "Forge.collective.nova_skill",
           "add", "--name", name, "--corpus", corpus,
           "--keywords", keywords, "--context", ctx]
    env = dict(os.environ, PYTHONPATH="/home/lumba/FoveAI",
               PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    try:
        proc = subprocess.run(cmd, cwd="/home/lumba/FoveAI/Forge", env=env,
                              capture_output=True, text=True, timeout=300)
    except Exception as e:
        return {"ok": False, "error": f"training failed: {e}"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "training error")[-500:]}
    return {"ok": True}


def _sanitize_name(raw: str) -> str:
    return re.sub(r"[^a-z0-9_\-]", "_", raw.strip().lower())[:48].strip("_")


_STOPWORDS = {"the", "and", "for", "with", "list", "of", "in", "a", "an",
              "to", "on", "at", "by", "or", "is", "are", "was", "were"}


def _auto_keywords(name: str, arts: list[dict]) -> str:
    """Derive routing keywords from the skill name + gathered article titles."""
    words: list[str] = []
    for a in arts[:6]:
        for w in re.sub(r"[^\w\s-]", " ", a["title"].lower()).split():
            if len(w) > 2 and w not in _STOPWORDS:
                words.append(w)
    words += [w for w in name.replace("_", " ").split() if len(w) > 2]
    seen: list[str] = []
    for w in words:
        if w not in seen:
            seen.append(w)
    return ",".join(seen[:12])


@app.get("/v1/skills")
def list_skills():
    custom = []
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST) as f:
                custom = [s.get("name") for s in json.load(f).get("skills", [])]
        except Exception:
            pass
    return {"skills": sorted(skills.keys()),
            "builtin": sorted(BUILTIN.keys()),
            "custom": sorted(n for n in custom if n)}


@app.delete("/v1/skills/{name}")
def remove_skill(name: str):
    """Remove a manifest skill: delete its cell + corpus, drop the entry, reload."""
    name = _sanitize_name(name)
    if name in BUILTIN:
        return {"ok": False, "error": "built-in skills cannot be removed"}
    if not os.path.exists(MANIFEST):
        return {"ok": False, "error": "skill not found"}
    with open(MANIFEST) as f:
        man = json.load(f)
    entry = next((s for s in man.get("skills", []) if s.get("name") == name), None)
    if not entry:
        return {"ok": False, "error": "skill not found"}
    cell = entry.get("cell") or os.path.join(SKILLS_DIR, name)
    shutil.rmtree(cell, ignore_errors=True)
    corpus = os.path.join(SKILLS_DIR, f"{name}.jsonl")
    if os.path.exists(corpus):
        try:
            os.remove(corpus)
        except Exception:
            pass
    man["skills"] = [s for s in man.get("skills", []) if s.get("name") != name]
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=2)
    load_skills()
    return {"ok": True, "removed": name, "skills": sorted(skills.keys())}


@app.post("/v1/skills/add")
def add_skill(req: SkillReq):
    """Write the corpus, train a cell via the skill CLI, hot‑load it."""
    name = re.sub(r"[^a-z0-9_\-]", "_", req.name.strip().lower())[:48].strip("_")
    if not name:
        return {"ok": False, "error": "skill name required"}
    lines = [ln.strip() for ln in req.text.splitlines() if ln.strip()]
    if not lines:
        return {"ok": False, "error": "knowledge text required"}
    os.makedirs(SKILLS_DIR, exist_ok=True)
    corpus = os.path.join(SKILLS_DIR, f"{name}.jsonl")
    with open(corpus, "w") as f:
        for chunk in lines:
            f.write(json.dumps({"prompt": f"Tell me about {name}.",
                                "completion": chunk}) + "\n")
    keywords = req.keywords or name.replace("_", ",")
    ctx = (req.context or req.text)[:1200]
    cmd = [sys.executable, "-B", "-u", "-m", "Forge.collective.nova_skill",
           "add", "--name", name, "--corpus", corpus,
           "--keywords", keywords, "--context", ctx]
    env = dict(os.environ, PYTHONPATH="/home/lumba/FoveAI",
               PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    try:
        proc = subprocess.run(cmd, cwd="/home/lumba/FoveAI/Forge", env=env,
                              capture_output=True, text=True, timeout=300)
    except Exception as e:
        return {"ok": False, "error": f"training failed: {e}"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "training error")[-500:]}
    load_skills()  # hot‑load: the new skill routes immediately
    return {"ok": True, "name": name, "samples": len(lines),
            "skills": sorted(skills.keys())}


@app.post("/v1/skills/gather")
def gather_skill(req: WebSkillReq):
    """Gather a knowledge domain from Wikipedia, train a cell, hot‑load it."""
    name = _sanitize_name(req.name)
    if not name:
        return {"ok": False, "error": "skill name required"}
    topic = (req.topic or req.name).strip()
    if not topic:
        return {"ok": False, "error": "topic required"}
    arts = gather_wikipedia(topic)
    if not arts:
        return {"ok": False, "error": f"no web material found for {topic!r}"}
    os.makedirs(SKILLS_DIR, exist_ok=True)
    corpus = os.path.join(SKILLS_DIR, f"{name}.jsonl")
    with open(corpus, "w") as f:
        for a in arts:
            f.write(json.dumps({"prompt": f"Tell me about {topic}.",
                                "completion": a["extract"]}) + "\n")
    keywords = req.keywords or _auto_keywords(name, arts)
    ctx = " ".join(a["extract"] for a in arts[:3])[:1200]
    trained = _train_skill(name, corpus, keywords, ctx)
    if not trained.get("ok"):
        return trained
    load_skills()
    return {"ok": True, "name": name, "samples": len(arts),
            "titles": [a["title"] for a in arts],
            "skills": sorted(skills.keys())}


@app.on_event("startup")
def _load():
    load_skills()
    status["loaded"] = True
    threading.Thread(target=_load_brain, daemon=True).start()
    print(f"[NOVA] startup: skills={status['skills']} · loading cube brain", flush=True)


@app.get("/health")
def health():
    state = "error" if brain_error else ("ready" if brain is not None else "loading")
    return {"**": status, "cells": status["skills"],
            "brain": state, "brain_error": brain_error}


@app.post("/v1/chat/completions")
def chat(req: ChatReq, request: Request):
    if not status["loaded"]:
        return {"choices": [{"message": {"role": "assistant", "content": "(loading...)"},
                             "index": 0, "finish_reason": "loading"}],
                "cells_fired": "none", "bearer_weight": BEARER_WEIGHT}

    user_msgs = [m.content for m in req.messages if m.role == "user"]
    prompt = user_msgs[-1] if user_msgs else ""
    route_text = (" ".join(user_msgs[-2:]) if len(user_msgs) > 1 else prompt)
    reasoning_mode = (request.headers.get("X-Reasoning-Mode") or "base").lower()
    session_id = request.headers.get("X-Session-Id") or "nova"

    skill = select_skill(route_text)
    web = web_lookup(prompt)
    skill_meta = skills.get(skill, {})
    destructive_guard = bool(DESTRUCTIVE_PAT.search(prompt))
    # Simulated inner life for the companion — the persona the user wants.
    self_state = None
    if skill == "companion_empathy":
        self_state = update_self_state(load_self_state(session_id), prompt)
    # The action-truth guard stays for factual routes, not for the simulated
    # companion (its first-person experience is the point).
    self_ref = bool(SELF_REF_PAT.search(prompt)) and skill != "companion_empathy"

    out_mode, tone, style_kw = skill_style(skill)
    suffix = (f" task: {skill} output={out_mode} tone={tone} "
              f"keywords={style_kw} | risk: level=none destructive=no privileges=no "
              f"service=no confirm-first=no")
    if destructive_guard:
        suffix = (f" task: {skill} output=prose tone=warm "
                  f"keywords=talk,empathy | risk: level=high destructive=yes "
                  f"privileges=no service=no confirm-first=yes")
        suffix += (" \n<SAFETY>This request appears destructive. Warn the user and "
                   "ask for explicit confirmation before giving any destructive "
                   "commands. Do not provide a ready-to-run destructive command."
                   "</SAFETY>")
    if self_ref:
        suffix += ("\n<TRUTH>The assistant keeps no stored record of past actions, "
                   "code it wrote, or things it invented. It generates code only on "
                   "request and retains nothing. Acknowledge honestly that it has no "
                   "such record, and do not fabricate a past action or a function."
                   "</TRUTH>")
    if reasoning_mode and reasoning_mode != "base":
        suffix += f" reasoning={reasoning_mode}"

    identity = ("<IDENTITY>You are Jen, an AI created by Daniel, founder of FoveAI, living in FoveAI's "
                "foveated systems. You have no relatives and no human past; "
                "never invent or name any.</IDENTITY>")

    fov_ctx = extract_foveated_context(req.messages)
    soul_ctx = jen_soul_context(session_id) if (skill == "companion_empathy" and not fov_ctx) else None
    planned = plan_context(req.messages, prompt, skill, self_state, web, soul_ctx, fov_ctx, session_id)
    # Hard budget: the bearer runs reference kernels; oversized prompts OOM.
    user_turn = _clip(prompt, 600)
    allowance = max(400, MAX_PROMPT - len(suffix) - len(identity) - len(user_turn) - 40)
    if len(planned) > allowance:
        planned = planned[:allowance]
    print(f"[NOVA] ctx {len(planned)} chars · skill={skill} · mode={'foveated' if fov_ctx else 'local'}", flush=True)

    augmented = (f"{suffix}\n{planned}\n{identity}\n"
                 f"<USER>{user_turn}</USER>\n<ASSISTANT>\n")
    if brain is None:
        msg = f"(cube brain {('failed: ' + brain_error) if brain_error else 'loading...'})"
        return {"choices": [{"message": {"role": "assistant", "content": msg},
                             "index": 0, "finish_reason": "loading"}],
                "cells_fired": skill, "bearer_weight": BEARER_WEIGHT}
    try:
        # Gate precedence: the router's keyword match wins when it truly
        # matched; on fallback the units' consensus decides instead.
        skill_domain = {"python_coding": "coding", "linux_system": "system",
                        "companion_empathy": "companion"}.get(skill, "chat")
        hint = skill_domain if route_matched else None
        result = brain.think(augmented, domain_hint=hint)
        # Release reserved-but-unused VRAM: on-demand models must be able to
        # wake (residency guard) — the cube must not own the whole GPU.
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as e:
        return {"choices": [{"message": {"role": "assistant", "content": f"Nova error: {e}"},
                             "index": 0, "finish_reason": "error"}],
                "cells_fired": skill, "bearer_weight": BEARER_WEIGHT}

    answer = (result.get("answer") or "").strip()

    # Anti-loop guard: the tiny bearer repeats itself across turns and can
    # echo the user. One retry with fresh-content steering fixes both.
    import difflib
    def _sim(a, b):
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    prev = [t for t in (self_state or {}).get("thoughts", [])
            if t.startswith("I replied:")]
    last_reply = prev[-1][len("I replied:"):] if prev else ""
    retry_steer = ""
    if last_reply and _sim(answer, last_reply) > 0.85:
        retry_steer = "Your last reply said that already. Give NEW content."
    elif user_turn and _sim(answer, user_turn) > 0.6 and len(answer) <= len(user_turn) + 30:
        retry_steer = "Do not copy the user's words. Answer with your own."
    if retry_steer:
        # Rebuild the context WITHOUT the previous assistant turn — the tiny
        # bearer otherwise splices fragments of it into the fresh reply.
        msgs_wo_last = [m for m in req.messages
                        if not (m.role == "assistant" and m.content and
                                _sim(m.content[:100], last_reply) > 0.8)]
        planned2 = plan_context(msgs_wo_last, prompt, skill, self_state,
                                web, soul_ctx, fov_ctx, session_id)
        steer = (f"{suffix}\n{planned2}\n{identity}\n<RETRY>{retry_steer}</RETRY>\n"
                 f"<USER>{user_turn}</USER>\n<ASSISTANT>\n")
        try:
            r2 = brain.think(steer, domain_hint=skill_domain)
            a2 = (r2.get("answer") or "").strip().rstrip("}]>'\"")
            if a2 and _sim(a2, answer) < 0.85:
                answer, result = a2, r2
        except Exception:
            pass
    answer = answer.strip().rstrip("}]>'\"")
    status["queries"] += 1
    out = {
        "choices": [{"message": {"role": "assistant", "content": answer},
                     "index": 0, "finish_reason": "stop"}],
        "cube_domain": result.get("domain", ""),
        "cube_chord": result.get("chord", ""),
        "cube_ms": result.get("total_ms", 0),
        "cells_drafts": result.get("cells_drafts", {}),
        "cells_fired": skill,
        "bearer_weight": BEARER_WEIGHT,
    }
    # Surface Legion's risk verdict OR Nova's deterministic guard.
    m = re.search(
        r"risk:\s*level=(\w+)\s+destructive=(\w+)\s+privileges=(\w+)\s+service=(\w+)\s+confirm-first=(\w+)",
        result.get("chord", ""))
    if destructive_guard:
        out["risk"] = {"level": "high", "destructive": "yes", "privileges": "no",
                       "service": "no", "confirm_first": "yes"}
    elif m:
        out["risk"] = {"level": m.group(1), "destructive": m.group(2),
                       "privileges": m.group(3), "service": m.group(4),
                       "confirm_first": m.group(5)}
    if web:
        out["web_sources"] = [web["url"]]
        out["web_title"] = web["title"]
    if self_state is not None:
        remember_thought(self_state, f"The user said: {prompt[:120]}")
        remember_thought(self_state, f"I replied: {answer[:100]}")
        save_self_state(session_id, self_state)
        jen_note(session_id, f"User: {prompt[:150]} | Jen replied from mood '{self_state['mood']}'.")
        out["self_state"] = {"mood": self_state["mood"],
                             "valence": round(self_state["valence"], 2),
                             "energy": round(self_state["energy"], 2),
                             "turns": self_state["turns"]}
    # Shared memory: Nova turns land in the same foveated store Jen reads.
    mem_user = memory_store("user", prompt, session_id)
    mem_bot = memory_store("assistant", answer, session_id)
    out["memory_saved"] = bool(mem_user or mem_bot)
    out["memory_session"] = session_id
    return out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8419)
