"""nano_queue.py — the nano compile pipeline.

One compile at a time, in the background, throttled (duty %), with a visible
queue. Cells are compiled per knowledge domain from extensive datasets;
a finished cell supersedes the old one of the same domain (successive
replacement). Templates capture a compile configuration for reuse.

Queue file:  /mnt/foveai/nano-xrl-bases/compile_queue.json
Controls:    /mnt/foveai/nano-xrl-bases/compile_queue.pause  (touch = hold)

GUI (Dash panel, planned): date/time as calendar + time selection boxes or
  strictly-masked inputs with format hints (combined list + manual entry) for
  pause/postpone scheduling.

Commands:
  list | serve | display-date-time
  add <recipe> [--id ID] [--pairs FILE] [--epochs N] [--replaces R]
      [--domain NAME] [--end-mb MB | --hidden H --layers L]
      [--duty PCT] [--marker M --end-marker E]
  edit <id> [--epochs N] [--pairs FILE] [--end-mb MB] [--duty PCT]
  remove <id> | clear-queue
  pause-queue [HH:MM] | postpone-until "YYYY-MM-DD HH:MM" | restart-queue-now
  duty <pct>
  new-template NAME [same options as add] | save-template <entry-id> <name>
  list-templates | modify-template NAME [--epochs N --end-mb MB --duty PCT ...]
  remove-template NAME | add-from-template NAME --domain NAME [--pairs FILE]
  seed-domains | serve
"""
from __future__ import annotations
import os, sys, json, time, math, signal, argparse, subprocess, datetime

BASE = "/mnt/foveai/nano-xrl-bases"
QUEUE = os.path.join(BASE, "compile_queue.json")
PAUSE = os.path.join(BASE, "compile_queue.pause")
VENVPY = "/home/lumba/FoveAI/.venv/bin/python"
LOG_DIR = "/home/lumba/runlogs"
CWD = "/home/lumba/FoveAI"

def now(): return datetime.datetime.now().isoformat(timespec="seconds")

def load():
    if os.path.exists(QUEUE):
        return json.load(open(QUEUE))
    return {"duty": 40, "entries": [], "templates": {}}

def save(q):
    tmp = QUEUE + ".tmp"
    json.dump(q, open(tmp, "w"), indent=2, ensure_ascii=False)
    os.replace(tmp, QUEUE)

def endmb_to_hidden(mb, layers=8):
    """End state: 5-bit quantization (0.625 B/param → 1.6M params per MB).
    mamba2 params ≈ 6.5 × layers × hidden². 20MB → 32M params."""
    return int(round(math.sqrt((mb * 1_600_000) / (6.5 * layers)) / 32) * 32)

# ── worker ──────────────────────────────────────────────────────────────────
def serve(_=None):
    print(f"[nanoq] worker up · {now()}", flush=True)
    stopped = None
    while True:
        q = load()
        if stopped is not None and not os.path.exists(PAUSE):
            try: os.kill(stopped, signal.SIGCONT)
            except ProcessLookupError: pass
            stopped = None
        resume_at = q.get("resume_at")
        if os.path.exists(PAUSE) or (resume_at and now() < resume_at):
            time.sleep(15)
            continue
        if resume_at and now() >= resume_at:
            q.pop("resume_at", None); save(q)
        entry = next((e for e in q["entries"] if e["status"] == "pending"), None)
        if entry is None:
            time.sleep(15)
            continue
        entry["status"] = "compiling"; entry["started"] = now(); save(q)
        log = os.path.join(LOG_DIR, f"nanoq_{entry['id']}.log")
        duty = entry.get("duty") or q.get("duty", 40)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES="0", HF_HUB_OFFLINE="1",
                   PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True",
                   NEURON_BATCH="8", NEURON_DUTY=str(duty))
        if entry.get("hidden"):
            env["NEURON_HIDDEN"] = str(entry["hidden"])
            env["NEURON_LAYERS"] = str(entry.get("layers", 8))
        if entry.get("kind") == "lora":
            # The self-training voice-router: harvest -> LoRA -> 5-bit GGUF.
            cmd = ["/home/lumba/FoveAI/Tools/unsloth_env/bin/python", "-B", "-u",
                   "-m", "Forge.collective.train_router_lora",
                   "--epochs", str(entry.get("epochs", 3)),
                   "--out", os.path.join(OUT_ROOT, "router-voice")]
            env["PYTHONPATH"] = "/home/lumba/FoveAI"
            if entry.get("pairs_file"):  # optional extra seed dir override
                env["ROUTER_SEED_DIR"] = entry["pairs_file"]
        elif entry.get("kind") == "unit":
            # XRL slot unit retrain (the 16-piece replacement queue).
            cmd = [VENVPY, "-u", "-m", "Forge.collective.xrl_units_train",
                   "--slot", str(entry["slot"]), "--hidden", str(entry.get("hidden", 384)),
                   "--layers", str(entry.get("layers", 36)),
                   "--epochs", str(entry.get("epochs", 60)),
                   "--out", entry["id"].replace("unit-slot", "slot")]
        else:
            cmd = [VENVPY, "-u", "-m", "Forge.collective.generation_neuron_train",
                   "--recipe", entry["recipe"], "--epochs", str(entry.get("epochs", 25)),
                   "--name", entry["id"]]
            if entry.get("pairs_file"): cmd += ["--pairs-file", entry["pairs_file"]]
            if entry.get("marker"):
                cmd += ["--marker", entry["marker"],
                        "--end-marker", entry.get("end_marker", "</REPLY>")]
        print(f"[nanoq] compiling {entry['id']} ({entry.get('hidden','896')}h · "
              f"duty {duty}%) -> {log}", flush=True)
        with open(log, "w") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, cwd=CWD, env=env)
            entry["pid"] = proc.pid; save(q)
            rc = proc.wait()
        entry["pid"] = None; entry["finished"] = now(); entry["exit"] = rc
        entry["status"] = "done" if rc == 0 else "failed"
        if rc == 0 and entry.get("replaces"):
            entry["replaced_at"] = now()
        save(q)
        print(f"[nanoq] {entry['id']} -> {entry['status']} (rc={rc})", flush=True)

# ── controls ────────────────────────────────────────────────────────────────
def current_pid():
    q = load()
    for e in q["entries"]:
        if e["status"] == "compiling" and e.get("pid"):
            return e["pid"], e
    return None, None

def pause_queue(args):
    open(PAUSE, "w").close()
    q = load()
    if getattr(args, "for_hhmm", None):
        h, m = args.for_hhmm.split(":")
        q["resume_at"] = (datetime.datetime.now()
                          + datetime.timedelta(hours=int(h), minutes=int(m))
                          ).isoformat(timespec="seconds")
        save(q)
    pid, e = current_pid()
    if pid:
        os.kill(pid, signal.SIGSTOP)
        print(f"queue paused · compile {e['id']} frozen (pid {pid})")
    else:
        print("queue paused · no compile running")
    ra = load().get("resume_at")
    print(f"auto-resume: {ra}" if ra else "manual resume: nanoq restart-queue-now")

def postpone(args):
    open(PAUSE, "w").close()
    q = load(); q["resume_at"] = args.until; save(q)
    print(f"queue postponed until {args.until}")

def restart_now(_):
    q = load(); q.pop("resume_at", None); save(q)
    if os.path.exists(PAUSE): os.remove(PAUSE)
    pid, _ = current_pid()
    if pid:
        try: os.kill(pid, signal.SIGCONT)
        except ProcessLookupError: pass
    print("queue restarted now")

def display_dt(_):
    q = load()
    print(f"now: {now()}")
    print(f"duty: {q.get('duty', 40)}%   pause flag: {'ON' if os.path.exists(PAUSE) else 'off'}")
    ra = q.get("resume_at")
    if ra:
        print(f"resume_at: {ra} ({'waiting' if now() < ra else 'elapsed'})")

def resume(_): restart_now(_)

def abort(_):
    pid, e = current_pid()
    if pid:
        try: os.kill(pid, signal.SIGKILL)
        except ProcessLookupError: pass
    q = load()
    for x in q["entries"]:
        if x["status"] == "compiling":
            x["status"] = "pending"; x["pid"] = None
    q.pop("resume_at", None); save(q)
    if os.path.exists(PAUSE): os.remove(PAUSE)
    print(f"aborted {e['id'] if e else '(none)'} · requeued · VRAM freed")

# ── entries ─────────────────────────────────────────────────────────────────
def _size_from(args, e):
    if args.end_mb:
        e["layers"] = args.layers or 8
        e["hidden"] = endmb_to_hidden(args.end_mb, e["layers"])
        e["end_mb"] = args.end_mb
    elif args.hidden:
        e["hidden"] = args.hidden; e["layers"] = args.layers or 8
        e["end_mb"] = round(6.5 * e["layers"] * args.hidden * args.hidden / 2e6, 1)

def add(args):
    q = load()
    eid = args.id or args.domain or args.recipe
    if any(x["id"] == eid for x in q["entries"]):
        print(f"{eid} already queued"); return
    e = {"id": eid, "recipe": args.recipe if args.recipe != "generic" else "generic",
         "pairs_file": args.pairs_file, "epochs": args.epochs,
         "replaces": args.replaces or f"neuron-{eid}",
         "duty": args.duty, "marker": args.marker,
         "end_marker": args.end_marker or ("</REPLY>" if args.marker else None),
         "status": "pending" if args.pairs_file else "needs-data",
         "added": now()}
    if args.recipe == "generic" and not args.marker:
        e["marker"], e["end_marker"] = "<REPLY>", "</REPLY>"
    _size_from(args, e)
    q["entries"].append(e); save(q)
    sz = f" · {e.get('end_mb','?')}MB ({e.get('hidden','?')}h)" if e.get("hidden") else ""
    print(f"queued {eid} (epochs={e['epochs']}, duty={e.get('duty') or q['duty']}%{sz}, {e['status']})")

def edit(args):
    q = load()
    e = next((x for x in q["entries"] if x["id"] == args.id), None)
    if not e: print("no such entry"); return
    if args.epochs: e["epochs"] = args.epochs
    if args.pairs_file: e["pairs_file"] = args.pairs_file
    if args.duty: e["duty"] = args.duty
    _size_from(args, e)
    if args.pairs_file and e["status"] == "needs-data": e["status"] = "pending"
    save(q); print(json.dumps(e, indent=1, ensure_ascii=False))

def remove(args):
    q = load(); q["entries"] = [x for x in q["entries"] if x["id"] != args.id]
    save(q); print(f"removed {args.id}")

def clear(_):
    q = load(); n = len(q["entries"]); q["entries"] = []; save(q)
    print(f"cleared {n} entries (templates kept)")

def duty(args):
    q = load(); q["duty"] = int(args.pct); save(q)
    print(f"duty set to {q['duty']}%")

def listq(_):
    q = load()
    print(f"now: {now()} · duty {q.get('duty',40)}% · "
          f"pause {'ON' if os.path.exists(PAUSE) else 'off'}"
          + (f" · resumes {q['resume_at']}" if q.get("resume_at") else ""))
    print(f"{'id':22} {'status':10} {'ep':4} {'size':12} {'duty':4} note")
    for e in q["entries"]:
        size = f"{e.get('end_mb','?')}MB/{e.get('hidden','?')}h" if e.get("hidden") else "std"
        note = e.get("pairs_file") or ""
        if e["status"] == "done" and e.get("replaced_at"): note = "replaced old ✓"
        if e["status"] == "failed": note = f"rc={e.get('exit')}"
        print(f"{e['id'][:22]:22} {e['status']:10} {str(e.get('epochs','')):4} {size:12} "
              f"{str(e.get('duty') or ''):4} {note[:44]}")

def seed(_):
    man = "/mnt/foveai/nano-xrl-bases/chorus/skills/manifest.json"
    q = load(); have = {e["id"] for e in q["entries"]}; added = 0
    if os.path.exists(man):
        for s in json.load(open(man)).get("skills", []):
            name = s.get("name")
            if not name or name in have: continue
            q["entries"].append({"id": name, "recipe": "generic",
                                 "pairs_file": f"Training/data/nano/{name}.jsonl",
                                 "epochs": 25, "replaces": f"skill:{name}",
                                 "marker": "<REPLY>", "end_marker": "</REPLY>",
                                 "status": "needs-data", "added": now()})
            have.add(name); added += 1
    save(q); print(f"seeded {added} domains (needs-data until datasets exist)")

# ── templates ───────────────────────────────────────────────────────────────
def save_template(args):
    q = load()
    e = next((x for x in q["entries"] if x["id"] == args.id), None)
    if not e: print("no such entry"); return
    t = {k: e.get(k) for k in ("recipe", "epochs", "hidden", "layers", "end_mb",
                               "duty", "marker", "end_marker", "pairs_file")}
    q.setdefault("templates", {})[args.name] = t; save(q)
    print(f"template '{args.name}' saved from {args.id}")

def new_template(args):
    q = load()
    t = {"recipe": args.recipe or "generic", "epochs": args.epochs or 25,
         "duty": args.duty, "marker": args.marker,
         "end_marker": args.end_marker or ("</REPLY>" if args.marker else None),
         "pairs_file": args.pairs_file}
    _size_from(args, t)
    q.setdefault("templates", {})[args.name] = t; save(q)
    print(f"template '{args.name}' created")

def list_templates(_):
    q = load()
    for n, t in q.get("templates", {}).items():
        size = f"{t['end_mb']}MB/{t['hidden']}h" if t.get("hidden") else "std"
        print(f"{n:24} {t.get('recipe'):14} ep={t.get('epochs')} {size:12} "
              f"duty={t.get('duty') or 'global'} {t.get('marker') or ''}")

def modify_template(args):
    q = load()
    t = q.get("templates", {}).get(args.name)
    if not t: print("no such template"); return
    if args.epochs: t["epochs"] = args.epochs
    if args.pairs_file: t["pairs_file"] = args.pairs_file
    if args.duty: t["duty"] = args.duty
    if args.marker: t["marker"] = args.marker
    _size_from(args, t)
    save(q); print(json.dumps(t, indent=1, ensure_ascii=False))

def remove_template(args):
    q = load(); q.get("templates", {}).pop(args.name, None); save(q)
    print(f"template '{args.name}' removed")

def add_from_template(args):
    q = load()
    t = q.get("templates", {}).get(args.name)
    if not t: print("no such template"); return
    eid = args.domain
    if any(x["id"] == eid for x in q["entries"]):
        print(f"{eid} already queued"); return
    e = dict(t)
    e.update({"id": eid, "replaces": f"neuron-{eid}" if not args.recipe else e.get("replaces"),
              "pairs_file": args.pairs_file or t.get("pairs_file"),
              "status": "pending" if e.get("pairs_file") else "needs-data",
              "added": now()})
    q["entries"].append(e); save(q)
    print(f"queued {eid} from template '{args.name}'")

# ── cli ─────────────────────────────────────────────────────────────────────
def _size_opts(sp):
    sp.add_argument("--end-mb", type=float); sp.add_argument("--hidden", type=int)
    sp.add_argument("--layers", type=int); sp.add_argument("--duty", type=int)

def main():
    ap = argparse.ArgumentParser(prog="nanoq")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("list", "serve", "seed-domains", "restart-queue-now", "resume",
              "abort", "clear-queue", "display-date-time", "list-templates"):
        sub.add_parser(c)
    p = sub.add_parser("pause-queue"); p.add_argument("for_hhmm", nargs="?", metavar="HH:MM")
    p = sub.add_parser("postpone-until"); p.add_argument("until", metavar='"YYYY-MM-DD HH:MM"')
    d = sub.add_parser("duty"); d.add_argument("pct", type=int)
    a = sub.add_parser("add"); a.add_argument("recipe"); a.add_argument("--id")
    a.add_argument("--domain"); a.add_argument("--pairs", dest="pairs_file")
    a.add_argument("--epochs", type=int, default=25); a.add_argument("--replaces")
    a.add_argument("--marker"); a.add_argument("--end-marker"); _size_opts(a)
    e = sub.add_parser("edit"); e.add_argument("id"); e.add_argument("--epochs", type=int)
    e.add_argument("--pairs", dest="pairs_file"); _size_opts(e)
    r = sub.add_parser("remove"); r.add_argument("id")
    t = sub.add_parser("save-template"); t.add_argument("id"); t.add_argument("name")
    t = sub.add_parser("new-template"); t.add_argument("name"); t.add_argument("recipe", nargs="?")
    t.add_argument("--pairs", dest="pairs_file"); t.add_argument("--epochs", type=int)
    t.add_argument("--marker"); t.add_argument("--end-marker"); _size_opts(t)
    t = sub.add_parser("modify-template"); t.add_argument("name"); t.add_argument("--epochs", type=int)
    t.add_argument("--pairs", dest="pairs_file"); t.add_argument("--marker"); _size_opts(t)
    t = sub.add_parser("remove-template"); t.add_argument("name")
    t = sub.add_parser("add-from-template"); t.add_argument("name")
    t.add_argument("--domain", required=True); t.add_argument("--pairs", dest="pairs_file")
    args = ap.parse_args()
    {"list": listq, "serve": serve, "seed-domains": seed,
     "pause-queue": pause_queue, "postpone-until": postpone,
     "restart-queue-now": restart_now, "resume": resume, "abort": abort,
     "display-date-time": display_dt, "duty": duty, "add": add, "edit": edit,
     "remove": remove, "clear-queue": clear, "save-template": save_template,
     "new-template": new_template, "list-templates": list_templates,
     "modify-template": modify_template, "remove-template": remove_template,
     "add-from-template": add_from_template}[args.cmd](args)

if __name__ == "__main__":
    main()