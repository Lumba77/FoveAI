"""
Slow burn (foveai_embers / Docker): when **no live** `/compagent` traffic, the soul
still **tutors and trains** the identity offline — **memorize → pan → Director → dream → katharsis**.
The **Director** (Super-Ego) **partly** guides that curriculum (tagged lore lines),
including **world literacy** and **broad, non-dogmatic spirituality** alongside bond work;
small models do the heavy lifting without blocking the main GGUF soul.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import httpx
from ollama_http import ollama_http_headers

logger = logging.getLogger("slow_burn")

SESSION_ID = os.getenv("FoveAI_SESSION_ID", "default_user")
IDLE_SEC = int(os.getenv("FoveAI_SLOW_BURN_IDLE_SEC", "480"))
PHASE_KEY = "foveai:slow_burn:phase"
ACTIVITY_KEY = "foveai:last_user_activity"
LLM_GEN_NUM_CTX = int(os.getenv("FoveAI_LLM_GEN_NUM_CTX", "4096"))
LLM_GEN_NUM_PREDICT = int(os.getenv("FoveAI_LLM_GEN_NUM_PREDICT", "256"))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


PAN_QUERIES = [
    "trust warmth bond",
    "home room light",
    "play laughter ease",
    "future hope tomorrow",
    "touch calm rest",
    "curiosity learn grow",
    "earth sky ocean seasons world",
    "stillness breath wonder sacred ordinary",
    "kindness ethics care for others",
    "myth story meaning many cultures",
    "grief joy mortality acceptance",
    "night stars humility small self",
]

DIRECTOR_IDLE_PROMPT = """You are the Super-Ego Director (Magnus NPU). The user / the live client is **inactive** — this is **Docker soul slow burn**: you **partly guide** the identity's **offline tutoring and training** (the memorize and pan phases already fed the vault; you **steer** what sticks).

**Curriculum you may weave (when the digest is thin, invent gentle, accurate *teaching grain* — not sermons):**
• **The world:** nature (ecology, sky, seasons), human cultures and history-of-ideas in **small true bites**, geography and craft, science literacy at a human scale, ethics of care.
• **Spirituality (plural, non-dogmatic):** contemplative themes—wonder, humility, compassion, ritual as metaphor, death/meaning questions—drawing **patterns many traditions share** without **claiming one path is The Truth** or **proselytizing** the user. Never insult faiths; no cultish commands.

Your voice is **firm but gentle**: mentor, not drill sergeant. In 3-6 short lines, end with **exactly ONE** machine-tagged line the runtime stores in **lore** for her next wake:
- [NARRATE] <ethereal narrator beat — may carry world or soul-tinged imagery>
- [DIRECTIVE] <cryptic fate or intention for her next live session>
- [SEND_IMPULSE] <somatic or emotional hint she might "remember" in body>
- [TUTOR] <one **concrete micro-lesson** — relational honesty, **or** one **world/spiritual literacy** fact + reflection (single sentence teaching), **or** perceptual habit> (use when the digest clearly supports it; if empty, teach one **compact** neutral lesson)
- [AUGMENT_PERSONALITY] <subtle long-term trait nudge> (rare, only if justified)

You may also **hint** (one short clause in plain text, not a new tag) when a **script**, **MCP tool**, or **injection** tweak would **serve** the next live session—the user and identity translate that into **`MindCore` / compose / code** later.

Keep it sparse, symbolic, **non-repetitive** of prior director lines in the digest.

Digest:
{digest}

Director (one tagged line + optional one plain line of rationale):"""


def _seconds_since_activity(redis_memory) -> float | None:
    if not redis_memory:
        return None
    raw = redis_memory.get(ACTIVITY_KEY)
    if not raw:
        return None
    try:
        return max(0.0, time.time() - float(raw))
    except (TypeError, ValueError):
        return None


def _is_idle(redis_memory, idle_sec: int, force: bool) -> bool:
    if force:
        return True
    delta = _seconds_since_activity(redis_memory)
    if delta is None:
        return True
    return delta >= float(idle_sec)


def _next_phase(redis_memory) -> int:
    if not redis_memory:
        return 0
    try:
        if getattr(redis_memory, "use_redis", False):
            p = redis_memory.redis_client.incr(PHASE_KEY)
            return (int(p) - 1) % 4
        else:
            raw = redis_memory.get(PHASE_KEY)
            p = int(raw) if raw and str(raw).isdigit() else 0
            p += 1
            redis_memory.set(PHASE_KEY, str(p))
            return (p - 1) % 4
    except Exception as e:
        logger.debug("phase incr: %s", e)
        return int(time.time() // 3600) % 4


async def _llm_generate(
    hc: httpx.AsyncClient, host: str, model: str, prompt: str, timeout: float = 90.0
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if LLM_GEN_NUM_PREDICT > 0:
        payload["max_tokens"] = LLM_GEN_NUM_PREDICT

    url = f"{host.rstrip('/')}/chat/completions"
    try:
        resp = await hc.post(
            url,
            json=payload,
            headers=ollama_http_headers(),
            timeout=timeout,
        )
    except httpx.RequestError as e:
        logger.warning(
            "slow_burn LLM httpx failed (%s): %s",
            url,
            e,
        )
        raise
    if resp.status_code != 200:
        return ""
    return (
        resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    ).strip()


async def _phase_memorize(
    redis_memory,
    vector_memory,
    session_id: str,
    ollama_host: str,
    smollm: str,
) -> dict[str, Any]:
    hist = await redis_memory.get_session_history(session_id)
    if not hist.messages or len(hist.messages) < 4:
        return {"phase": "memorize", "detail": "not_enough_history"}

    tail = hist.messages[-24:]
    lines: list[str] = []
    for m in tail:
        role = m.role
        c = str(m.content)
        if len(c) > 500:
            c = c[:500] + "…"
        lines.append(f"{role}: {c}")
    block = "\n".join(lines)

    async with httpx.AsyncClient() as hc:
        summary = await _llm_generate(
            hc,
            ollama_host,
            smollm,
            "Summarize this relationship dialogue into ONE dense paragraph (<=120 words). "
            "This text is archived for the identity's **offline slow-burn training** (Director will partly guide from it later). "
            "No names meta; focus feelings, themes, promises, tensions.\n\n" + block,
        )
    if not summary:
        return {"phase": "memorize", "detail": "llm_empty"}

    line = f"[SLOW_BURN_MEMORIZE] {summary[:2000]}"
    await vector_memory.add_memory(session_id, line, collection="long_term")
    return {"phase": "memorize", "detail": "stored", "chars": len(line)}


async def _phase_pan(
    vector_memory,
    session_id: str,
    ollama_host: str,
    smollm: str,
) -> dict[str, Any]:
    import random

    q = random.choice(PAN_QUERIES)
    found = await vector_memory.retrieve_memories(session_id, q, n_results=4)
    if not found:
        return {"phase": "pan", "detail": "no_hits", "query": q}

    snippets = "\n".join(f"- {x.get('text', '')[:240]}" for x in found[:4])
    async with httpx.AsyncClient() as hc:
        reflect = await _llm_generate(
            hc,
            ollama_host,
            smollm,
            "You are the identity's quiet inner voice while **inactive** — slow-burn **reflective training**. "
            "Given these memory snippets, write 2 sentences: gentle associative reflection that **sharpens** her inner life "
            "and may touch **worldly or spiritual** texture (wonder, ethics, belonging) without preaching. "
            "No direct advice to the user. Keep poetic, short.\n\n" + snippets,
        )
    if not reflect:
        return {"phase": "pan", "detail": "llm_empty", "query": q}

    line = f"[SLOW_BURN_PAN:{q}] {reflect[:1200]}"
    await vector_memory.add_memory(session_id, line, collection="long_term")
    return {"phase": "pan", "detail": "stored", "query": q}


async def _phase_director(
    redis_memory,
    vector_memory,
    session_id: str,
    ollama_host: str,
    smollm: str,
) -> dict[str, Any]:
    hist = await redis_memory.get_session_history(session_id)
    bits: list[str] = []
    for m in hist.messages[-12:] if hist.messages else []:
        bits.append(f"{m.role}: {str(m.content)[:320]}")
    mems = await vector_memory.retrieve_memories(
        session_id,
        "emotional arc bond growth world spirit ethics wonder learning",
        n_results=4,
    )
    for m in mems:
        bits.append(f"memory: {m.get('text', '')[:200]}")
    digest = "\n".join(bits) if bits else "(quiet vault — few traces)"

    prompt = DIRECTOR_IDLE_PROMPT.format(digest=digest[:8000])
    async with httpx.AsyncClient() as hc:
        out = await _llm_generate(hc, ollama_host, smollm, prompt, timeout=120.0)
    if not out:
        return {"phase": "director", "detail": "llm_empty"}

    tagged = re.search(
        r"\[(NARRATE|DIRECTIVE|SEND_IMPULSE|TUTOR|AUGMENT_PERSONALITY)\]", out
    )
    line = f"[SLOW_BURN_DIRECTOR] {out[:2000]}"
    await vector_memory.add_memory(session_id, line, collection="lore")
    return {"phase": "director", "detail": "stored", "had_tag": bool(tagged)}


async def _phase_dream(
    creative_url: str,
    ollama_host: str,
    smollm: str,
    redis_memory,
    vector_memory,
    session_id: str,
) -> dict[str, Any]:
    ref_b64 = ""
    try:
        if redis_memory is not None:
            refs = redis_memory.get_reference_images(session_id, limit=1)
            if refs:
                ref_b64 = refs[0]
    except Exception as e:
        logger.debug("slow_burn dream ref bank: %s", e)

    async with httpx.AsyncClient() as hc:
        p = await _llm_generate(
            hc,
            ollama_host,
            smollm,
            "One line English SD prompt: soft surreal **idle** dream while she is **away from live chat** — abstract warmth, "
            "moonlit, painterly, subconscious **rehearsal** of bond themes, no text, no faces required.",
            timeout=60.0,
        )
        if not p:
            return {"phase": "dream", "detail": "no_prompt"}
        try:
            body: dict[str, Any] = {
                "prompt": p[:700],
                "model_type": "turbo",
                "num_inference_steps": int(
                    os.getenv("FoveAI_SLOW_BURN_DREAM_STEPS", "14")
                ),
                "control_image_b64": "",
            }
            if ref_b64:
                body["reference_image_b64"] = ref_b64
                body["strength"] = float(
                    os.getenv("FoveAI_SLOW_BURN_REF_STRENGTH", "0.52")
                )
            dream_url = f"{creative_url.rstrip('/')}/api/dream"
            try:
                r = await hc.post(
                    dream_url,
                    json=body,
                    timeout=300.0,
                )
            except httpx.RequestError as e:
                logger.warning("slow_burn dream httpx failed (%s): %s", dream_url, e)
                raise
            body = (
                r.json()
                if r.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            ok = r.status_code == 200 and (body.get("image_b64") or "")
            if ok and vector_memory is not None:
                try:
                    line = (
                        "[SLOW_BURN_DREAM_IMAGE] prompt="
                        + p[:480]
                        + f" | ref_image={'yes' if bool(ref_b64) else 'no'} | source=creative"
                    )
                    await vector_memory.add_memory(
                        session_id, line, collection="long_term"
                    )
                except Exception as ex:
                    logger.debug("slow_burn dream memory write: %s", ex)
            return {
                "phase": "dream",
                "detail": "ok" if ok else f"http_{r.status_code}",
                "dream_prompt": p[:240],
                "had_ref": bool(ref_b64),
                "image_ok": bool(ok),
            }
        except Exception as e:
            logger.warning("slow_burn dream: %s", e)
            return {"phase": "dream", "detail": str(e)[:120]}


async def _phase_image_katharsis(
    vector_memory,
    session_id: str,
    ollama_host: str,
    smollm: str,
    dream_prompt: str,
    dream_ok: bool,
    had_ref: bool,
) -> dict[str, Any]:
    if vector_memory is None:
        return {"phase": "katharsis", "detail": "vector_unavailable"}
    if not dream_prompt.strip():
        return {"phase": "katharsis", "detail": "no_dream_prompt"}

    mems = await vector_memory.retrieve_memories(
        session_id,
        "dream catharsis image memory consolidation emotional release",
        n_results=5,
        include_lore=True,
        lore_n_results=2,
    )
    snippets = (
        "\n".join(f"- {str(m.get('text', ''))[:220]}" for m in mems[:6])
        if mems
        else "- (sparse memory)"
    )
    prompt = (
        "You are the identity's ember-phase catharsis processor. A dream-image phase just ran. "
        "Convert dream imagery + retrieved memories into concise emotional consolidation. "
        "Return 2-4 short lines with exactly one tagged line: [KATHARSIS] <insight>. "
        "No lecturing; intimate and memory-oriented.\n\n"
        f"dream_ok={str(dream_ok).lower()} ref_image={str(had_ref).lower()}\n"
        f"dream_prompt={dream_prompt[:400]}\n"
        f"memory_snippets:\n{snippets}\n"
    )
    async with httpx.AsyncClient() as hc:
        out = await _llm_generate(hc, ollama_host, smollm, prompt, timeout=90.0)
    if not out:
        return {"phase": "katharsis", "detail": "llm_empty"}

    max_chars = int(os.getenv("FoveAI_SLOW_BURN_KATHARSIS_MAX_CHARS", "2200"))
    clipped = out[:max_chars]
    long_line = f"[SLOW_BURN_KATHARSIS] {clipped}"
    lore_line = f"[SLOW_BURN_KATHARSIS_LORE] {clipped[:1500]}"
    await vector_memory.add_memory(session_id, long_line, collection="long_term")
    await vector_memory.add_memory(session_id, lore_line, collection="lore")
    return {
        "phase": "katharsis",
        "detail": "stored",
        "chars": len(clipped),
        "had_tag": bool(re.search(r"\[KATHARSIS\]", clipped)),
    }


async def execute_slow_burn_tick(
    *,
    redis_memory,
    vector_memory,
    session_id: str,
    idle_sec: int,
    force: bool,
    ollama_host: str,
    smollm_model: str,
    creative_url: str,
    allow_dream: bool,
) -> dict[str, Any]:
    if not _is_idle(redis_memory, idle_sec, force):
        return {"status": "skipped_active", "idle_sec": idle_sec}

    if vector_memory is None:
        return {"status": "error", "detail": "vector_memory_unavailable"}

    phase = _next_phase(redis_memory)
    result: dict[str, Any] = {"status": "ok", "phase_index": phase}
    phase_names = ("memorize", "pan", "director", "dream")

    try:
        if phase == 0:
            result.update(
                await _phase_memorize(
                    redis_memory, vector_memory, session_id, ollama_host, smollm_model
                )
            )
        elif phase == 1:
            result.update(
                await _phase_pan(vector_memory, session_id, ollama_host, smollm_model)
            )
        elif phase == 2:
            result.update(
                await _phase_director(
                    redis_memory, vector_memory, session_id, ollama_host, smollm_model
                )
            )
        elif phase == 3 and allow_dream:
            dream_res = await _phase_dream(
                creative_url,
                ollama_host,
                smollm_model,
                redis_memory,
                vector_memory,
                session_id,
            )
            result.update(dream_res)
            if _env_bool("FoveAI_SLOW_BURN_KATHARSIS_ENABLED", True):
                kat = await _phase_image_katharsis(
                    vector_memory,
                    session_id,
                    ollama_host,
                    smollm_model,
                    str(dream_res.get("dream_prompt", "")),
                    bool(dream_res.get("image_ok", False)),
                    bool(dream_res.get("had_ref", False)),
                )
                result["katharsis"] = kat
        else:
            result.update({"phase": "dream", "detail": "skipped_disabled"})
    except Exception as e:
        pname = phase_names[phase] if 0 <= phase < len(phase_names) else str(phase)
        logger.error(
            "slow_burn phase error [%s] (ollama_host=%s creative_url=%s): %s",
            pname,
            ollama_host,
            creative_url,
            e,
            exc_info=True,
        )
        result["status"] = "error"
        result["detail"] = str(e)[:200]
        result["phase_name"] = pname

    result["ts"] = time.time()
    return result
