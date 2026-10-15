#!/usr/bin/env python3
"""Jen residency controller — Phase 1 of Docs/JEN_MIND.md.

One mind, two hardware tiers, loaded on demand and freed when idle:

    A  Background  Gemma-4-E2B (interim)  :8407   coexists with the user's apps
    B  Present    Qwen3.5-9B-MoQ + Eagle3 :8408   exclusive VRAM, the flagship

Truth lives in Backend/Cognition/jen_mind.json (shared with every frontend).
The busy ladder and smart layer split are delegated to runtime.vram_guard;
loading goes through runtime/llama_launch.py (guard-gated). This module only
decides *when* and *which* — never *how much*.

CLI:
    python -m runtime.residency status
    python -m runtime.residency lever 1.0
    python -m runtime.residency load B
    python -m runtime.residency unload
    python -m runtime.residency mode dreaming
    python -m runtime.residency run            # idle-unload + wake-cycle daemon
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA_PATH = ROOT / "Backend" / "Cognition" / "jen_mind.schema.json"
MIND_PATH = ROOT / "Backend" / "Cognition" / "jen_mind.json"
PYTHON = ROOT / ".venv" / "bin" / "python"
LAUNCHER = ROOT / "runtime" / "llama_launch.py"
TURN_LOCK = ROOT / "runtime" / ".jen_turn.lock"  # backend touches this during a turn
WAKE_REQ = ROOT / "runtime" / ".jen_wake.json"   # backend drops a wake request here
LOG_DIR = ROOT / "runtime" / "logs"

# Foreign VRAM (GB) above which no new model may load — the machine is owned.
HARD_FOREIGN_VRAM_GB = float(os.environ.get("FOVEAI_HARD_FOREIGN_VRAM_GB", "1.5"))
# Seconds after the last user input before a Present-tier model is released.
IDLE_UNLOAD_S = float(os.environ.get("FOVEAI_IDLE_UNLOAD_S", "30"))


# ── state ────────────────────────────────────────────────────────────────
def load_schema() -> dict[str, Any]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def read_mind() -> dict[str, Any]:
    with open(MIND_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_mind(state: dict[str, Any]) -> None:
    state["updated"] = time.time()
    tmp = MIND_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, MIND_PATH)


# ── cross-process guard for the shared mind file ─────────────────────────
# nerve.py, residency.py and the CLI all read-modify-write the SAME
# Backend/Cognition/jen_mind.json. Without a lock, a fast writer (nerve, every
# few seconds) can clobber the residency section back to None and orphan a
# loaded brain. Every mutation must go through here.
MIND_LOCK = ROOT / "runtime" / ".jen_mind.lock"


@contextmanager
def mind_lock():
    MIND_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(MIND_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def mutate(fn):
    """Atomic read-modify-write of the shared mind file. `fn(state)` mutates
    the freshly-read state; its return value is passed back to the caller.
    NEVER call load()/unload() from inside `fn` — they take the same lock."""
    with mind_lock():
        state = read_mind()
        result = fn(state)
        write_mind(state)
        return result


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def apply_lever(state: dict[str, Any], schema: dict[str, Any], value: float) -> None:
    """Set the Companion<->Agent crossfade and recompute every drive's gain."""
    value = max(0.0, min(1.0, value))
    state["lever"] = round(value, 4)
    preset = min(
        schema["lever"]["presets"], key=lambda p: abs(p["value"] - value)
    )
    state["preset"] = preset["id"]
    ss = smoothstep(value)
    for d in schema["drives"]:
        eff = schema["clusters"][d["cluster"]]["lever_effect"]
        if eff == "falls":
            gain = 1.0 - ss
        elif eff == "rises":
            gain = ss
        else:  # const
            gain = schema["clusters"][d["cluster"]].get("base", 0.7)
        state["drives"].setdefault(d["id"], {})["gain"] = round(gain, 4)


# ── guard: the busy ladder ────────────────────────────────────────────────
def _guardrail():
    try:
        from runtime.vram_guard import guardrail
        return guardrail
    except Exception:
        return None


def turn_active() -> bool:
    """A conversation turn is in flight — never cut it (residency contract)."""
    try:
        return (time.time() - TURN_LOCK.stat().st_mtime) < 120.0
    except OSError:
        return False


def pending_wake() -> str | None:
    """The tier the proxy asked for, if any. 'A'/'B', or None."""
    try:
        with open(WAKE_REQ, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("tier")
    except Exception:
        return None


def clear_wake() -> None:
    try:
        WAKE_REQ.unlink(missing_ok=True)
    except OSError:
        pass


def busy() -> dict[str, Any]:
    """Survey the host. hard = do not load; soft = tier A only; clear = go."""
    reasons: list[str] = []
    hard = soft = False

    g = _guardrail()
    if g is None:
        return {"hard": False, "soft": False, "reasons": ["guard unavailable"], "verdict": "clear"}

    gate = g.gaming_gate()
    if gate:
        hard = True
        reasons += gate.get("reasons", ["game owns the GPU"])

    foreign = [c for c in g.foreign_vram_consumers()
               if "llama" not in c["name"].lower()]
    heavy = [c for c in foreign if c["gb"] >= HARD_FOREIGN_VRAM_GB]
    if heavy:
        hard = True
        reasons.append("foreign GPU: " + ", ".join(f"{c['name']} {c['gb']:.1f}G" for c in heavy))

    verdict = g.lane_state().get("verdict", "clear")
    if verdict == "blocked":
        hard = True
        reasons.append("lane blocked")
    elif verdict == "busy":
        soft = True
        reasons.append("lane busy")

    return {
        "hard": hard,
        "soft": soft,
        "reasons": reasons or ["clear"],
        "verdict": "blocked" if hard else ("busy" if soft else "clear"),
    }


# ── tier launch / teardown ────────────────────────────────────────────────
def _resolve(p: str) -> str:
    return p if os.path.isabs(p) else str(ROOT / p)


def tier_argv(schema: dict[str, Any], tier: str) -> list[str]:
    t = schema["tiers"][tier]
    argv = [
        str(PYTHON), str(LAUNCHER),
        "--llama", schema["llama_server"],
        "--model", _resolve(t["path"]),
        "--port", str(t["port"]),
        "--ctx", str(t["ctx"]),
        "--requested-layers", str(t.get("requested_layers", 40)),
    ]
    if t.get("mmproj"):
        argv += ["--mmproj", _resolve(t["mmproj"])]
    if t.get("draft"):
        argv += ["--draft", _resolve(t["draft"])]
        argv += ["--spec-draft-n-max", str(t.get("spec_draft_n_max", 40))]
    if t.get("cache_type"):
        argv += ["--cache-type", t["cache_type"]]
    if t.get("flash_attn"):
        argv += ["--flash-attn"]
    if t.get("jinja"):
        argv += ["--jinja"]
    return argv


def _health(port: int, timeout: float = 2.0) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def load(tier: str, wait_s: float = 120.0, force: bool = False) -> dict[str, Any]:
    schema = load_schema()
    if tier not in schema["tiers"]:
        return {"ok": False, "error": f"unknown tier {tier}"}

    b = busy()
    spec = schema["tiers"][tier]
    if not force and (b["hard"] or (b["soft"] and spec.get("exclusive"))):
        return {"ok": False, "error": "host busy", "busy": b}

    # Quick locked check + intent marker; the slow spawn happens OUTSIDE the lock.
    with mind_lock():
        state = read_mind()
        cur = state.get("residency", {})
        if cur.get("tier") == tier and _alive(cur.get("pid")) and _health(spec["port"]):
            return {"ok": True, "tier": tier, "note": "already present", "pid": cur["pid"]}
        prev_tier, prev_pid = cur.get("tier"), cur.get("pid")
        state["residency"] = {
            "tier": tier, "model": spec["model"], "port": spec["port"],
            "pid": None, "state": "loading",
            "last_activity": cur.get("last_activity"),
            "last_wake": cur.get("last_wake"),
        }
        write_mind(state)

    if (prev_tier and prev_tier != tier) or _alive(prev_pid):
        unload()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / f"jen_{tier}_{spec['port']}.log", "a", buffering=1)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = schema["llama_ld_path"] + ":" + env.get("LD_LIBRARY_PATH", "")
    proc = subprocess.Popen(
        tier_argv(schema, tier), cwd=str(ROOT), env=env,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )

    deadline = time.time() + wait_s
    while time.time() < deadline:
        if proc.poll() is not None:
            return {"ok": False, "error": "launcher exited", "code": proc.returncode}
        if _health(spec["port"]):
            break
        time.sleep(1.5)
    else:
        return {"ok": False, "error": "health timeout", "pid": proc.pid}

    def _finish(s: dict[str, Any]) -> dict[str, Any]:
        s["residency"] = {
            "tier": tier, "model": spec["model"], "port": spec["port"],
            "pid": proc.pid, "state": "present",
            "last_activity": (s.get("residency") or {}).get("last_activity"),
            "last_wake": time.time(),
        }
        return s["residency"]

    mutate(_finish)
    return {"ok": True, "tier": tier, "pid": proc.pid, "port": spec["port"]}


def unload() -> dict[str, Any]:
    with mind_lock():
        state = read_mind()
        res = state.get("residency", {})
        pid = res.get("pid")
        freed = False
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                for _ in range(20):
                    if not _alive(pid):
                        break
                    time.sleep(0.25)
                if _alive(pid):
                    os.kill(pid, signal.SIGKILL)
                freed = True
            except OSError:
                pass
        if not freed:
            g = _guardrail()
            if g is not None:
                ok, _msg = g.unload_all_models()
                freed = bool(ok)
        state["residency"] = {
            "tier": None, "model": None, "port": None, "pid": None,
            "state": "idle",
            "last_activity": res.get("last_activity"),
            "last_wake": res.get("last_wake"),
        }
        write_mind(state)
        return {"ok": True, "freed": freed}


def status() -> dict[str, Any]:
    schema = load_schema()
    state = read_mind()
    res = state.get("residency", {})
    live = _alive(res.get("pid"))
    port = res.get("port")
    return {
        "lever": state.get("lever"),
        "preset": state.get("preset"),
        "mode": state.get("mode"),
        "tier": res.get("tier"),
        "pid": res.get("pid") if live else None,
        "port": port,
        "healthy": bool(port and _health(port)),
        "busy": busy(),
        "idle_s": _idle_s(),
        "turn_active": turn_active(),
        "tiers": {k: {"port": v["port"], "exclusive": v.get("exclusive")}
                  for k, v in schema["tiers"].items()},
    }


def _idle_s() -> float | None:
    g = _guardrail()
    return g.human_idle_s() if g else None


# ── daemon: idle-unload + wake-cycle ──────────────────────────────────────
def run(poll_s: float = 5.0) -> None:
    schema = load_schema()
    print(f"[residency] running  idle_unload={IDLE_UNLOAD_S}s "
          f"wake_cycle={schema['residency']['wake_cycle_s']}s")
    while True:
        try:
            state = read_mind()
            res = state.get("residency", {})
            tier = res.get("tier")

            # 1) Wake requests from the proxy (it runs as root and must never
            #    spawn the loader itself — the daemon owns all load/unload).
            req = pending_wake()
            if req in ("A", "B"):
                present = tier == req and _alive(res.get("pid"))
                if not present and not busy()["hard"]:
                    print(f"[residency] wake request -> loading tier {req}")
                    clear_wake()  # consume before the slow load; never spin
                    load(req)
                    continue

            # 2) Idle-unload a present brain once the human has stepped away.
            idle = _idle_s()
            if tier and _alive(res.get("pid")) and not turn_active():
                if idle is not None and idle >= IDLE_UNLOAD_S:
                    print(f"[residency] idle {idle:.0f}s -> unloading tier {tier}")
                    unload()
            time.sleep(poll_s)
        except KeyboardInterrupt:
            print("[residency] stopped")
            return
        except Exception as e:  # keep the daemon alive
            print(f"[residency] tick error: {e}")
            time.sleep(poll_s)


# ── CLI ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Jen residency controller")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p_lever = sub.add_parser("lever")
    p_lever.add_argument("value", type=float)
    p_load = sub.add_parser("load")
    p_load.add_argument("tier", choices=["A", "B"])
    p_load.add_argument("-f", "--force", action="store_true", help="bypass soft busy guard")
    sub.add_parser("unload")
    p_mode = sub.add_parser("mode")
    p_mode.add_argument("name")
    sub.add_parser("run")

    a = ap.parse_args()
    if a.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if a.cmd == "lever":
        schema = load_schema()
        out = mutate(lambda s: (apply_lever(s, schema, a.value) or {"lever": s["lever"], "preset": s["preset"]}))
        print(json.dumps(out, indent=2))
        return 0
    if a.cmd == "load":
        print(json.dumps(load(a.tier, force=a.force), indent=2))
        return 0
    if a.cmd == "unload":
        print(json.dumps(unload(), indent=2))
        return 0
    if a.cmd == "mode":
        mutate(lambda s: s.__setitem__("mode", a.name))
        print(json.dumps({"mode": a.name}, indent=2))
        return 0
    if a.cmd == "run":
        run()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
