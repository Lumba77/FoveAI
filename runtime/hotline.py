"""
runtime/hotline.py — the inter-actor communication hotline
==================================================================

One channel. Everyone on it. Urgent messages and plain explanations travel the
same road, because an explanation you can only find in a log is not an
explanation anyone receives.

Why this exists
---------------
`vram_guard._broadcast_silent_ipc()` posted to
`http://127.0.0.1:8400/v1/internal/ipc` — a route that exists NOWHERE in the
codebase. Its `except Exception: pass` swallowed every failure, so the governor
had been "communicating" into a void for as long as it had existed. Silent
failure is worse than no channel, because it looks like a working one.

The rule this module is built around
------------------------------------
    A message is durable BEFORE any delivery is attempted.

If every listener is down — no :8400, no WebSocket, no dunst — the message is
still on disk, replayable with `since(cursor)`. Nothing is ever lost to a
missing listener. That is the whole difference between a hotline and a
footnote.

Transport-agnostic by design
----------------------------
The port map on this box is mid-remap and `AGENTS.md` disagrees with the code
about what :8411 even is. So the hotline does NOT bind a port of its own. The
durable log is the source of truth; HTTP/WebSocket/dunst are transports bolted
on top, and any of them can be absent without data loss. Wire `/v1/hotline`
into server.js when the port question is settled — by then this module already
has the semantics right.

Envelope follows the project convention (hard rule 6): {"event": ..., "payload": {...}}
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

BUS_DIR = Path(
    os.environ.get("FOVEAI_HOTLINE_DIR", Path(__file__).parent.parent / ".hotline")
)
BUS_LOG = BUS_DIR / "bus.jsonl"

# Levels. `urgent` is the only one that is allowed to interrupt a human.
LEVELS = ("info", "notice", "warn", "urgent")
_LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}

# WHO is speaking decides how loudly they are heard.
#
# Severity alone is not a fair ordering: a storm of system telemetry could
# otherwise weigh exactly as much as a person asking for help. A human plea
# outranks any amount of machine chatter, because the whole point of this bus
# is that the thing which reaches a human in time is treated as human.
#
#   human  — a person, directly. Never displaced by telemetry.
#   agent  — a process acting for someone (the model, a service, a request).
#   system — telemetry, housekeeping, forecasts.
ORIGINS = ("system", "agent", "human")
ORIGIN_RANK = {"system": 0, "agent": 1, "human": 2}


def weight(msg: dict) -> int:
    """
    Single comparable number for 'how much does this deserve attention'.
    Level sets the floor; origin raises it. A human 'info' outranks a system
    'urgent', which is the entire intent.
    """
    return ORIGIN_RANK.get(msg.get("origin", "system"), 0) * 10 + _LEVEL_RANK.get(
        msg.get("level", "info"), 0
    )

# How long a message stays relevant. Urgent things expire; explanations don't.
DEFAULT_TTL_S = {
    "info": 3600.0,
    "notice": 1800.0,
    "warn": 900.0,
    "urgent": 300.0,
}
# Explanations and audit trails never expire — that is the point of them.
PERMANENT_TTL_S = 0.0


def _now() -> float:
    return time.time()


def _ensure_dir() -> None:
    BUS_DIR.mkdir(parents=True, exist_ok=True)


# ── Explanations must be COMPLETE, not merely present ──────────────────────
# An obstruction nobody can explain is bearable up to a point; an explanation
# that gives only a cause ("disk busy") is the worst of both — enough
# information to feel the weight, not enough to know what to do about it.
#
# A good explanation carries four things, and all four are load-bearing:
#
#   cause        what is specifically blocking
#   category     what KIND of thing this is  (malfunction / natural / illness
#                / contention). Category picks the moral response: identical
#                obstruction, opposite behaviour, depending on which.
#   horizon      whether it ends, and roughly when
#   implication  what to do instead
#
# The governing distinction is omission vs. stated-unknown. "I don't know how
# long this will take" is a COMPLETE explanation — the horizon is honestly
# unknown and says so. Saying nothing about duration is INCOMPLETE, because it
# leaves the reader to assume the worst. A system that explains badly should be
# able to notice that about itself.
REQUIRED_EXPLANATION_FIELDS = ("cause", "category", "horizon", "implication")

# "unknown" is a legitimate, honest value for any field — it is OMISSION that
# makes an explanation opaque, not uncertainty itself.
_UNKNOWN = "unknown"


def completeness(explanation: dict[str, Any] | None) -> dict[str, Any]:
    """
    Audit an explanation against the four required components.

    Distinguishes two very different things:
      missing[]  — the field was never said        (opacity; a defect)
      unknown[]  — the field was stated as unknown (honesty; acceptable)
    """
    if not explanation:
        return {
            "complete": False, "missing": list(REQUIRED_EXPLANATION_FIELDS),
            "unknown": [], "note": "no explanation given at all",
        }
    missing, unknown = [], []
    for field in REQUIRED_EXPLANATION_FIELDS:
        if field not in explanation or explanation[field] in (None, ""):
            missing.append(field)
        elif str(explanation[field]).strip().lower() == _UNKNOWN:
            unknown.append(field)
    return {
        "complete": not missing,
        "missing": missing,
        "unknown": unknown,
        "note": "complete" if not missing else f"never said: {', '.join(missing)}",
    }


def render_explanation(explanation: dict[str, Any]) -> str:
    """The four components as one readable block, in plain words."""
    lines = []
    for field, label in (
        ("cause", "Because"),
        ("category", "This is"),
        ("horizon", "Duration"),
        ("implication", "Instead"),
    ):
        val = explanation.get(field, _UNKNOWN)
        if str(val).strip().lower() == _UNKNOWN:
            val = "not known yet — flagged rather than guessed"
        lines.append(f"{label}: {val}")
    return "\n".join(lines)


def publish(
    event: str,
    payload: dict[str, Any] | None = None,
    level: str = "info",
    actor: str | None = None,
    ttl_s: float | None = None,
    explain: str | None = None,
    not_before: float | None = None,
    warn_ahead_s: float = 0.0,
    origin: str = "system",
    explanation: dict[str, Any] | None = None,
) -> str:
    """
    Put a message on the hotline. Returns its id.

    Durable first: the JSONL append happens before any delivery is attempted,
    so a total absence of listeners cannot lose the message.

    `explain` carries the human-readable sentence. It is a first-class field,
    not a rendering detail — an event nobody can read in words is not an
    explanation.

    `not_before` schedules the message: it is written now but only becomes
    relevant then. This is the post-it note. `warn_ahead_s` starts the warning
    clock early, so an actor gets told "this is coming" before it arrives.
    """
    if level not in _LEVEL_RANK:
        level = "info"

    msg_id = uuid.uuid4().hex[:12]
    if ttl_s is None:
        ttl_s = PERMANENT_TTL_S if explain else DEFAULT_TTL_S[level]

    record = {
        "id": msg_id,
        "ts": _now(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": event,
        "level": level,
        "actor": actor or os.uname().nodename if hasattr(os, "uname") else "unknown",
        "payload": payload or {},
        "explain": explain,
        "ttl_s": ttl_s,
        "not_before": not_before,
        "warn_ahead_s": warn_ahead_s,
        "origin": origin if origin in ORIGIN_RANK else "system",
        # Audited at send time so an inadequate explanation is visible to the
        # system itself, not only to whoever happens to read it.
        "explanation": explanation,
        "explanation_audit": completeness(explanation),
    }

    # ── durability first ────────────────────────────────────────────────
    _ensure_dir()
    line = json.dumps(record, ensure_ascii=False)
    with open(BUS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())

    _deliver(record)
    return msg_id


def _deliver(record: dict[str, Any]) -> None:
    """
    Best-effort fan-out. Every transport is allowed to fail; none of them may
    raise, because a failed notification must never take down the caller.

    A scheduled message whose moment has not arrived is NOT delivered yet — but
    it IS already on disk, so a process starting later can see what is coming.
    """
    now = _now()
    nb = record.get("not_before")
    warn_ahead = record.get("warn_ahead_s") or 0.0
    if nb and now < nb - warn_ahead and record.get("level") != "urgent":
        # Too early to bother anyone — but an urgent message is never held
        # back. Whatever the countdown says, if someone needs to hear it now,
        # the countdown loses.
        return

    # ── humans: dunst ───────────────────────────────────────────────────
    if record["level"] in ("warn", "urgent") or record.get("origin") == "human":
        try:
            import subprocess as _sp

            urgency = "critical" if record["level"] == "urgent" else "normal"
            body = record.get("explain") or record["event"]
            _sp.run(
                ["notify-send", "-u", urgency, "FoveAI hotline", body],
                timeout=3,
                capture_output=True,
            )
        except Exception:
            pass

    # ── processes on :8400, if and when the route exists ─────────────────
    try:
        import urllib.request

        req = urllib.request.Request(
            "http://127.0.0.1:8400/v1/internal/ipc",
            data=json.dumps(
                {"event": record["event"], "payload": record["payload"]}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=0.2).close()
    except Exception:
        pass  # route absent — the message is already on disk, so nothing is lost


def since(cursor: float = 0.0, levels: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """
    Replay messages after `cursor` (a unix timestamp, or 0.0 for everything).

    This is what makes the hotline survivable: a process that starts later, or
    one that was offline during a storm, catches up by asking for everything
    since it last looked. Nobody has to have been listening at the right moment.
    """
    out: list[dict[str, Any]] = []
    try:
        with open(BUS_LOG, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except Exception:
                    continue
                if rec.get("ts", 0.0) <= cursor:
                    continue
                if levels and rec.get("level") not in levels:
                    continue
                out.append(_normalize(rec))
    except FileNotFoundError:
        return []
    return out


def _normalize(rec: dict[str, Any]) -> dict[str, Any]:
    """
    Backfill defaults on records written before a field existed.

    The log is append-only and outlives any schema change, so readers get the
    same shape regardless of when a message was written. Without this, adding
    `origin` in October would have broken every consumer reading messages from
    September — a log that cannot be read after a schema change is not a log.
    """
    rec.setdefault("origin", "system")
    rec.setdefault("level", "info")
    rec.setdefault("not_before", None)
    rec.setdefault("warn_ahead_s", 0.0)
    rec.setdefault("explain", None)
    rec.setdefault("actor", "unknown")
    return rec


def upcoming(window_s: float = 3600.0) -> list[dict[str, Any]]:
    """
    Messages already on the board whose moment is still ahead — the forecast.

    This is what a process reads on waking to learn what is COMING, rather than
    only what already happened.
    """
    now = _now()
    out = []
    for m in since(0.0):
        nb = m.get("not_before")
        if nb and nb > now and (nb - now) <= window_s:
            out.append({**m, "in_s": round(nb - now, 1)})
    return out


def due(now: float | None = None) -> list[dict[str, Any]]:
    """Scheduled messages whose moment has arrived."""
    t = now if now is not None else _now()
    return [m for m in since(0.0) if m.get("not_before") and m["not_before"] <= t]


def countdown(m: dict[str, Any]) -> str:
    """
    Human phrasing for a scheduled message — the post-it note, in words.
    Falls back to 'now' rather than printing a negative countdown, because a
    message that slipped past its moment must not read as broken.
    """
    secs = int(m.get("in_s", 0))
    if secs <= 0:
        return "now"
    mins = secs // 60
    if mins < 1:
        return f"in {secs}s"
    if mins < 60:
        return f"in {mins} min"
    return f"in {mins // 60}h {mins % 60:02d}m"


def latest(level: str | None = None) -> dict[str, Any] | None:
    """Most recent message, optionally filtered by level."""
    msgs = since(0.0, levels=(level,) if level else None)
    return msgs[-1] if msgs else None


def prioritized(limit: int = 20) -> list[dict[str, Any]]:
    """
    What deserves attention most, regardless of arrival order.

    Sorted by weight, so a human's request is never queued behind a backlog of
    system telemetry that happened to fire first.
    """
    return sorted(since(0.0), key=weight, reverse=True)[:limit]


def active(min_level: str = "notice") -> list[dict[str, Any]]:
    """
    Messages that have not yet expired — what a newly-woken process should
    actually be told about right now.
    """
    floor = _LEVEL_RANK.get(min_level, 1)
    now = _now()
    return [
        m
        for m in since(0.0)
        if _LEVEL_RANK.get(m.get("level", "info"), 0) >= floor
        and (not m.get("ttl_s") or m["ts"] + m["ttl_s"] > now)
        and (not m.get("not_before") or m["not_before"] <= now)
    ]


def stream(min_level: str = "info", poll_s: float = 1.0) -> Iterator[dict[str, Any]]:
    """
    Blocking iterator over the hotline. The simplest way for any process to
    listen, in any language: read the tail, yield what is new, sleep, repeat.
    """
    cursor = _now()
    while True:
        batch = since(cursor, levels=tuple(
            l for l in LEVELS if _LEVEL_RANK[l] >= _LEVEL_RANK.get(min_level, 0)
        ))
        for m in batch:
            cursor = max(cursor, m["ts"])
            yield m
        time.sleep(poll_s)


def explain_state(verdict: str, reasons: list[str] | None = None) -> str:
    """
    Shared vocabulary for resource decisions, in words.

    Lives here rather than in the governor so that anything can produce the same
    explanation — a service, a CLI, a chat reply — and they will all say the
    same thing about the same condition.
    """
    base = {
        "clear": "Lane is free — nothing else is competing for it.",
        "busy": "Lane is busy — measured pressure, but the work fits. "
                "Proceeding, and saying so out loud.",
        "blocked_io": "Disk is saturated — tasks are spending real time stalled "
                      "on I/O. Starting now would slow everything else down.",
        "blocked_vram": "Not enough video memory — another program is holding "
                        "the GPU, and this would spill into system RAM, which "
                        "is the resource that causes freezes.",
        "blocked_ram": "Not enough system memory free — this would push the "
                       "desktop into swap, which is what causes long freezes.",
    }.get(verdict, verdict)

    lines = [base]
    for r in reasons or []:
        lines.append(f"  • {r}")
    lines.append("  (Yield only happens between batches, never mid-task.)")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        publish(
            "hotline.test",
            {"hello": "world"},
            level="info",
            explain="Hotline self-test — if you can read this, the channel is live.",
        )
        print("published to", BUS_LOG)
    elif len(sys.argv) > 1 and sys.argv[1] == "tail":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        for m in since(0.0)[-n:]:
            print(f"[{m['iso']}] {m['level']:>6}  {m['event']}")
            if m.get("explain"):
                print("        " + m["explain"].replace("\n", "\n        "))
    else:
        print("usage: hotline.py publish | hotline.py tail [n]")
        print(f"log: {BUS_LOG}")
