#!/usr/bin/env python3
"""memory_curator.py — distill raw material into dense XRL memory units.

Backfill put old docs into vector space; this pass REWRITES the corpus:
docs, logs, memory lanes and web pages get distilled by whatever LLM tier is
up (the :8400 proxy fronts dormant/ready/online) into short, tagged,
semantic-search-shaped units, then ingested through the resonance lane so
every XRL-contracted model inherits the knowledge.

No LLM up → deterministic extractive fallback (top-tf sentences) — the pipe
never blocks on a model.

CLI:
  python memory_curator.py curate path/to/file.md [--tags a b] [--workspace devin]
  python memory_curator.py ingest-url https://... [--tags a b]
  python memory_curator.py web "topic query" [--n 3] [--tags a b]
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

FOVEAI = Path("/home/lumba/FoveAI")
PROXY = os.environ.get("FOVEAI_PROXY", "http://127.0.0.1:8400")
RESONATE = f"{PROXY}/api/resonance/ingest"
CHAT = f"{PROXY}/v1/chat/completions"
SEARCH = f"{PROXY}/v1/memory/search"
MODEL = os.environ.get("FOVEAI_AGENT_ID", "devin")

CHUNK = 6000        # chars per distill batch
MAX_UNITS = 4       # units emitted per chunk
VERIFY_MIN = 0.55   # certifier acceptance threshold
UA = {"User-Agent": "FoveAI-curator/1.0"}

# Domain taxonomy — keeps the bank navigable instead of one soup.
# Order matters: first match wins in the heuristic classifier.
DOMAINS = {
    "unity":      ["unity", "vrm", "vrma", "quest", "android", "il2cpp", "prefab", "shader", "c#", "monobehaviour"],
    "xrl":        ["xrl", "xrlf", "contract", "lane", "resonance", "telepathy", "grant", "ed25519"],
    "memory":     ["memory", "embedding", "recall", "nedb", "foveat", "minilm", "semantic"],
    "frontend":   ["react", "vite", "tsx", "css", "dom", "ui", "panel", "three.js", "webxr"],
    "backend":    ["fastapi", "python", "node", "server", "api", "websocket", "endpoint", "systemd", "pydantic"],
    "models":     ["llm", "gguf", "lora", "qlora", "llama", "finetune", "checkpoint", "tokenizer", "onnx"],
    "infra":      ["port", "build", "gradle", "apk", "deploy", "caddy", "tunnel", "ssh", "service"],
    "docs":       ["readme", "manual", "documentation", "guide", "spec"],
    "web":        ["http", "forum", "stackoverflow", "github", "issue"],
}
CSE_ID = os.environ.get("GOOGLE_CSE_ID")
CSE_KEY = os.environ.get("GOOGLE_API_KEY")


def classify_domain(text: str) -> str:
    """Keyword taxonomy — deterministic; the LLM distill may override."""
    t = text.lower()
    hits = {d: sum(1 for k in kws if k in t) for d, kws in DOMAINS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] > 0 else "general"


# ── LLM / extractive distillation ────────────────────────────────────

def _llm_distill(text: str, hint: str = "") -> list[dict] | None:
    """Ask the resident tier for ≤MAX_UNITS dense units. None if no LLM."""
    prompt = (
        "Distill the following material into at most %d durable memory units "
        "for a shared semantic memory. Each unit: {\"summary\": one dense "
        "sentence a future agent needs, \"tags\": [2-5 keywords]}. "
        "Keep facts (names, ports, files, decisions), drop filler. "
        "Reply with a JSON array only.\n\n%s\n\n%s" % (MAX_UNITS, hint, text)
    )
    prompt = prompt.replace(
        '"tags": [2-5 keywords]',
        '"tags": [2-5 keywords], "domain": one of %s' % list(DOMAINS))
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 700, "temperature": 0.2,
        "workspace": MODEL, "raw": True,
    }).encode()
    try:
        req = urllib.request.Request(CHAT, data=body,
                                     headers={"Content-Type": "application/json", **UA})
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        content = resp["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", content, re.S)
        units = json.loads(m.group(0)) if m else None
        if isinstance(units, list):
            return [u for u in units if isinstance(u, dict) and u.get("summary")]
    except Exception:
        return None
    return None


def _tf(text: str) -> dict[str, float]:
    f: dict[str, float] = {}
    for w in re.findall(r"[a-z0-9_]{3,}", text.lower()):
        f[w] = f.get(w, 0) + 1
    return f


def _extractive_distill(text: str, hint: str = "") -> list[dict]:
    """Top-tf sentence selection — deterministic, no model needed."""
    sents = re.split(r"(?<=[.!?])\s+|\n+", text)
    freq = _tf(text)
    scored = []
    for s in sents:
        s = s.strip()
        if not (40 <= len(s) <= 400):
            continue
        words = re.findall(r"[a-z0-9_]{3,}", s.lower())
        if len(words) < 6:
            continue
        score = sum(freq.get(w, 0) for w in words) / len(words)
        scored.append((score, s))
    scored.sort(reverse=True)
    return [{"summary": s, "tags": ["curated", "extractive"] + ([hint] if hint else [])}
            for _, s in scored[:MAX_UNITS]]


def distill(text: str, hint: str = "") -> tuple[list[dict], str]:
    units = _llm_distill(text, hint)
    return (units, "llm") if units else (_extractive_distill(text, hint), "extractive")


# ── Ingest (resonance lane — durable) ────────────────────────────────

def resonate(units: list[dict], extra_tags: list[str]) -> dict:
    payload = {"units": [{"model": MODEL,
                          "summary": u["summary"][:600],
                          "tags": (u.get("tags") or []) + extra_tags}
                         for u in units]}
    req = urllib.request.Request(RESONATE, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **UA})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except Exception as e:
        return {"error": str(e), "attempted": len(payload["units"])}


# ── Sources ─────────────────────────────────────────────────────────

def _chunks(text: str) -> list[str]:
    return [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]


# ── The Certifier — adversarial review before anything is filed ─────
# Suboptimal or wrong material vacuumed from the web must NOT reach the
# collective lanes. Each candidate unit is scored 0..1 for veracity,
# specificity and sourcing; below VERIFY_MIN it is rejected and reported.

_HEDGES = ("maybe", "probably", "might", "i think", "not sure", "possibly",
           "should be", "i believe", "guess")
_MARKERS = re.compile(r"(\.\w{2,4}\b|:\d{2,5}\b|/\w+/\w+|v?\d+\.\d+|\b[A-Z][a-z]+[A-Z])")


def _certify_heuristic(u: dict, source: str) -> tuple[float, str]:
    """No-LLM critic: specificity markers up, hedging/vagueness down."""
    s = u.get("summary", "")
    score = 0.5
    marks = len(_MARKERS.findall(s))
    score += min(marks * 0.12, 0.36)
    hedges = sum(1 for h in _HEDGES if h in s.lower())
    score -= hedges * 0.15
    if len(s) < 30:
        score -= 0.2                      # too thin to carry a fact
    if len(set(s.lower().split())) < 6:
        score -= 0.15                     # low lexical variety = fluff
    if source.startswith("http") and any(
            d in source for d in ("github.", "docs.", "developer.", "learn.", "unity3d", "meta.com", "readthedocs")):
        score += 0.1                      # primary-source bump
    reason = f"markers={marks} hedges={hedges} len={len(s)}"
    return max(0.0, min(1.0, score)), reason


def _certify_llm(units: list[dict], source: str) -> list[tuple[float, str]] | None:
    """One batched adversarial review — the Certifier persona."""
    items = [{"i": i, "summary": u.get("summary", "")} for i, u in enumerate(units)]
    prompt = (
        "You are CERTIFIER, a hostile peer reviewer. For each candidate memory "
        "unit, score 0..1: 1 = verifiable, specific, durable fact worth keeping; "
        "0 = vague, hedged, wrong-looking, or filler. Be strict — reject "
        "anything you could not defend in review. Reply ONLY with a JSON array "
        "of {\"i\": int, \"score\": float, \"why\": \"short\"}.\n\n"
        + json.dumps(items))
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600, "temperature": 0.0,
        "workspace": "certifier", "raw": True}).encode()
    try:
        req = urllib.request.Request(CHAT, data=body,
                                     headers={"Content-Type": "application/json", **UA})
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        content = resp["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", content, re.S)
        rows = json.loads(m.group(0)) if m else None
        if not isinstance(rows, list):
            return None
        table = {int(r["i"]): (float(r.get("score", 0)), str(r.get("why", "")))
                 for r in rows if isinstance(r, dict) and "i" in r}
        return [table.get(i, (0.0, "unscored")) for i in range(len(units))]
    except Exception:
        return None


def certify(units: list[dict], source: str) -> tuple[list[dict], list[dict], str]:
    """Returns (kept, rejected, mode). Kept units gain domain + verified tag."""
    if not units:
        return [], [], "none"
    verdicts = _certify_llm(units, source)
    mode = "llm"
    if verdicts is None:
        verdicts = [_certify_heuristic(u, source) for u in units]
        mode = "heuristic"
    kept, rejected = [], []
    for u, (score, why) in zip(units, verdicts):
        u["_certifier"] = round(score, 3)
        dom = u.get("domain") or classify_domain(u.get("summary", "") + " " + source)
        u["domain"] = dom
        (u.setdefault("tags", [])).extend([dom, "verified" if score >= VERIFY_MIN else "rejected"])
        (kept if score >= VERIFY_MIN else rejected).append(
            u if score >= VERIFY_MIN else {"summary": u.get("summary", "")[:120],
                                           "score": round(score, 3), "why": why})
    return kept, rejected, mode


def curate_text(text: str, source: str, tags: list[str]) -> dict:
    out, modes = [], set()
    for c in _chunks(text):
        units, mode = distill(c, hint=source)
        modes.add(mode)
        out.extend(units)
    kept, rejected, cmode = certify(out, source)
    res = resonate(kept, tags + ["curated", source])
    return {"source": source, "units_in": len(out), "units_kept": len(kept),
            "rejected": rejected, "distill": "+".join(sorted(modes)),
            "certifier": cmode, "ingest": res}


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, timeout=30).read()
    try:
        txt = raw.decode("utf-8", "replace")
    except Exception:
        txt = str(raw)
    # crude but effective tag-strip; keep code-ish text intact
    txt = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", txt)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    return html.unescape(re.sub(r"\s{2,}", " ", txt)).strip()


def web_search(query: str, n: int = 3) -> list[str]:
    """Google CSE when GOOGLE_CSE_ID+GOOGLE_API_KEY are set in env/.env;
    otherwise anonymous DuckDuckGo. Never logged-in scraping."""
    if CSE_ID and CSE_KEY:
        q = urllib.parse.quote(query)
        url = ("https://www.googleapis.com/customsearch/v1"
               f"?key={CSE_KEY}&cx={CSE_ID}&q={q}&num={min(n, 10)}")
        try:
            data = json.loads(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=20).read())
            return [i["link"] for i in data.get("items", [])][:n]
        except Exception:
            pass  # fall through to anonymous
    q = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"
    req = urllib.request.Request(url, headers=UA)
    txt = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    links = re.findall(r'href="(?:https?://duckduckgo.com/l/\?uddg=)?([^"&]+)', txt)
    out = []
    for l in links:
        l = urllib.parse.unquote(l)
        if l.startswith("http") and "duckduckgo.com" not in l and l not in out:
            out.append(l)
    return out[:n]


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("curate"); c.add_argument("path")
    u = sub.add_parser("ingest-url"); u.add_argument("url")
    w = sub.add_parser("web"); w.add_argument("query"); w.add_argument("--n", type=int, default=3)
    for p in (c, u, w):
        p.add_argument("--tags", nargs="*", default=[])
        p.add_argument("--workspace", default=MODEL)
    a = ap.parse_args()

    if a.cmd == "curate":
        p = Path(a.path)
        if not p.exists():
            sys.exit(f"not found: {p}")
        print(json.dumps(curate_text(p.read_text(errors="replace"), p.name, a.tags), indent=2))
    elif a.cmd == "ingest-url":
        print(json.dumps(curate_text(fetch_url(a.url), a.url, a.tags), indent=2))
    elif a.cmd == "web":
        urls = web_search(a.query, a.n)
        reports = [curate_text(fetch_url(u), u, a.tags + ["web"]) for u in urls]
        print(json.dumps({"query": a.query, "urls": urls, "reports": reports}, indent=2))


if __name__ == "__main__":
    main()
