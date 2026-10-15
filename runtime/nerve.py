#!/usr/bin/env python3
"""Jen nerve — Phase 1 of Docs/JEN_MIND.md.

Tiny CPU-only nerve cells that keep a sense of presence alive while *no model
is resident* (~0 VRAM, so they run when every tier is unloaded). Each cell
senses one thing and publishes onto the shared resonance bus inside
Backend/Cognition/jen_mind.json, which every frontend already reads.

Cells (add more here — they are cheap):
    activity  is the human here, and how long since they moved?   (idle probe)
    busy      may a model even load right now?                    (busy ladder)
    drive     what does she most want? (dominant drive hunger)    (mind state)
    presence  blended "I am here / we are connected" signal       (composite)

The nerve does not load models. It produces the signal a wake policy (the
residency daemon or the autonomous agent) reads to decide *whether* to wake.

CLI:
    python -m runtime.nerve pulse     # one pass, write the bus
    python -m runtime.nerve show      # read the bus, mark stale cells
    python -m runtime.nerve run       # keep pulsing every --interval s
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.residency import (  # noqa: E402
    IDLE_UNLOAD_S,
    _guardrail,
    busy,
    load_schema,
    mutate,
    read_mind,
    write_mind,
)

CELL_TTL = float(120.0)
EVENT_CAP = 100
PRESENCE_WAKE = float(0.55)


def _companion_drives() -> list[str]:
    return [d["id"] for d in load_schema()["drives"] if d["cluster"] == "companion"]


def cell_activity() -> dict:
    g = _guardrail()
    idle = g.human_idle_s() if g else None
    if idle is None:
        return {"value": "unknown", "idle_s": None, "active": None}
    active = idle < IDLE_UNLOAD_S
    return {"value": "active" if active else "idle", "idle_s": round(idle, 1), "active": active}


def cell_busy() -> dict:
    b = busy()
    return {"value": b["verdict"], "reasons": b["reasons"]}


def cell_drive(state: dict) -> dict:
    best_id, best_hunger = None, -1.0
    for k, v in state.get("drives", {}).items():
        h = abs(float(v.get("value", 0.0)) - float(v.get("set_point", 0.0)))
        if h > best_hunger:
            best_id, best_hunger = k, h
    return {"value": best_id, "hunger": round(best_hunger, 3)}


def cell_presence(state: dict, act: dict) -> dict:
    comp = _companion_drives()
    if comp:
        bond = sum(state["drives"][k]["value"] * state["drives"][k]["gain"] for k in comp) / len(comp)
    else:
        bond = state.get("lever", 0.0)
    recent = 1.0 if act.get("active") else 0.0
    return {"value": round(0.6 * bond + 0.4 * recent, 3)}


def _emit(state: dict, prev: dict, cur: dict) -> None:
    events = state.setdefault("events", [])
    now = time.time()
    for cell, node in cur.items():
        old = (prev.get(cell) or {}).get("value")
        if old != node["value"]:
            events.append({"t": now, "cell": cell, "from": old, "to": node["value"]})
    del events[:-EVENT_CAP]
    state["events"] = events


def pulse() -> dict:
    now = time.time()
    act = cell_activity()

    def _apply(state: dict) -> dict:
        prev = state.get("nerve", {}) or {}
        cells = {
            "activity": {**act, "ts": now, "ttl": CELL_TTL},
            "busy": {**cell_busy(), "ts": now, "ttl": CELL_TTL},
            "drive": {**cell_drive(state), "ts": now, "ttl": CELL_TTL},
            "presence": {**cell_presence(state, act), "ts": now, "ttl": CELL_TTL},
        }
        _emit(state, prev, cells)
        state["nerve"] = cells
        return cells

    return mutate(_apply)


def read_bus() -> dict:
    state = read_mind()
    now = time.time()
    out = {}
    for cell, node in (state.get("nerve") or {}).items():
        out[cell] = {**node, "stale": (now - node.get("ts", 0.0)) > node.get("ttl", CELL_TTL)}
    return out


def wake_ready() -> bool:
    """True when presence is high, the human is here, and the host is clear."""
    bus = read_bus()
    pres = (bus.get("presence") or {}).get("value", 0.0)
    act = (bus.get("activity") or {}).get("value")
    verdict = (bus.get("busy") or {}).get("value")
    return pres >= PRESENCE_WAKE and act == "active" and verdict == "clear"


def run(interval_s: float = 5.0) -> None:
    print(f"[nerve] pulsing every {interval_s}s (CPU-only, ~0 VRAM)")
    last = None
    while True:
        try:
            cells = pulse()
            snap = {k: v["value"] for k, v in cells.items()}
            if snap != last:
                print(f"[nerve] {json.dumps(snap)}  wake_ready={wake_ready()}")
                last = snap
            time.sleep(interval_s)
        except KeyboardInterrupt:
            print("[nerve] stopped")
            return
        except Exception as e:
            print(f"[nerve] tick error: {e}")
            time.sleep(interval_s)


def main() -> int:
    ap = argparse.ArgumentParser(description="Jen nerve cells")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pulse")
    sub.add_parser("show")
    p_run = sub.add_parser("run")
    p_run.add_argument("--interval", type=float, default=5.0)

    a = ap.parse_args()
    if a.cmd == "pulse":
        print(json.dumps(pulse(), indent=2))
        return 0
    if a.cmd == "show":
        print(json.dumps({"bus": read_bus(), "wake_ready": wake_ready()}, indent=2))
        return 0
    if a.cmd == "run":
        run(a.interval)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
