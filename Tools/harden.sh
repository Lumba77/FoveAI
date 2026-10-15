#!/usr/bin/env bash
# harden.sh — the standing guard.
#
# Runs on a timer and does what a person kept having to do by hand:
#   1. port linter  — finds references to services that are not running
#   2. UI smoke test — drives a real browser through login → setup → ignition → app
#   3. triage       — when something is broken, ask the LOCAL model to read the
#                     evidence and propose a fix, and write the verdict to disk
#
# No secrets are printed. Credentials come from the environment.
#
# Exits non-zero when the browser step did not actually verify the app. It used
# to exit 0 unconditionally, so systemd logged "Finished" for runs that had
# silently done nothing — a guard that lies is worse than no guard.
set -uo pipefail

ROOT=/home/lumba/FoveAI
OUT="$ROOT/memory/ui_health"
STAMP=$(date +%Y%m%d-%H%M%S)
REPORT="$OUT/run-$STAMP.json"
mkdir -p "$OUT"

# Resolve node explicitly: a systemd oneshot does not get the login shell's
# PATH, and a missing node used to make the whole smoke step vanish silently.
NODE=""
for cand in /home/lumba/.local/node24/bin/node "$(command -v node 2>/dev/null || true)" /usr/bin/node; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then NODE="$cand"; break; fi
done
if [ -z "$NODE" ]; then
  echo "FATAL: no node binary found — the browser smoke test cannot run"
  exit 2
fi

echo "── harden: port linter"
# Count the actual ":PORT file:line" findings under the heading. Counting the
# heading line itself always returned 1, so triage fired on every run.
DEAD=$("$ROOT/.venv/bin/python" "$ROOT/Tools/check_ports.py" 2>&1 | tee "$OUT/ports-$STAMP.txt" \
  | awk '/DEAD REFERENCES/{f=1;next} /^── /{f=0} f && /^[[:space:]]*:[0-9]+[[:space:]]/{n++} END{print n+0}')

echo "── harden: ui smoke (node: $(basename "$(dirname "$NODE")")/$(basename "$NODE"))"
if [ -z "${FOVEAI_SMOKE_TOKEN:-}" ]; then
  echo "   WARNING: FOVEAI_SMOKE_TOKEN is unset — the smoke test will stop at the login portal"
fi
"$NODE" "$ROOT/Tools/smoke_ui.mjs" --out "$REPORT" > "$OUT/smoke-$STAMP.log" 2>&1
SMOKE_RC=$?
VERDICT=$(grep -m1 '"verdict"' "$REPORT" 2>/dev/null | sed -E 's/.*: *"([A-Z]+)".*/\1/')
ERRS=$(grep -m1 '"error_count"' "$REPORT" 2>/dev/null | tr -dc '0-9')

echo "   smoke verdict: ${VERDICT:-UNKNOWN} (errors: ${ERRS:-?}, rc=$SMOKE_RC)"

# ── triage with the local model only when something is actually broken
if [ "${VERDICT:-FAIL}" != "PASS" ] || [ "${DEAD:-0}" -gt 0 ]; then
  echo "── harden: triage via local model"
  {
    echo "FoveAI UI health triage — $(date -Is)"
    echo
    echo "Port linter (dead references: ${DEAD}):"
    sed -n '/DEAD REFERENCES/,/NOT IN THE COGNITIVE/p' "$OUT/ports-$STAMP.txt" | head -40
    echo
    echo "UI smoke report:"
    head -60 "$OUT/smoke-$STAMP.log"
    echo
    cat <<'PROMPT'
List the distinct root causes above. For each: (1) one-line cause, (2) the exact
file:line to change, (3) the minimal fix. Prefer same-origin paths and existing
services over new ones. Do not invent new subsystems. Be brief and concrete.
PROMPT
  } > "$OUT/triage-input-$STAMP.txt"

  # Prefer the real 9B (it can actually read a stack trace). The 0.5B CPU
  # router answers instantly but produces generic filler, so it is the fallback.
  for PORT in 8408 8406; do
    if curl -sf -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      python3 - "$PORT" "$OUT/triage-input-$STAMP.txt" "$OUT/triage-$STAMP.md" <<'PY' 2>/dev/null
import json, sys, urllib.request
port, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
prompt = open(src).read()[-6000:]
body = json.dumps({"model": "Xrlf_Router_Qwen0.5B_Merged" if port == "8406" else "local-model",
                   "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": 900, "temperature": 0.2, "stream": False,
                   "chat_template_kwargs": {"enable_thinking": False}}).encode()
try:
    r = urllib.request.urlopen(urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"}), timeout=90)
    txt = json.load(r)["choices"][0]["message"]["content"]
    open(dst, "w").write(f"# Triage via :{port} — {__import__('datetime').datetime.now().isoformat()}\n\n{txt}\n")
    print(f"   triage written from :{port}")
except Exception as e:
    print(f"   triage via :{port} failed: {e}")
PY
      [ -s "$OUT/triage-$STAMP.md" ] && break
    fi
  done
fi

# keep the last 20 runs
ls -1t "$OUT"/run-*.json 2>/dev/null | tail -n +21 | xargs -r rm -f
ls -1t "$OUT"/smoke-*.log 2>/dev/null | tail -n +21 | xargs -r rm -f
echo "── harden: done (smoke=${VERDICT:-UNKNOWN}, dead_refs=$DEAD)"

if [ "${VERDICT:-}" != "PASS" ]; then
  if [ ! -s "$REPORT" ]; then
    echo "FAIL: no smoke report produced — the browser step did not run"
  else
    echo "FAIL: smoke verdict ${VERDICT:-UNKNOWN} (errors: ${ERRS:-?})"
  fi
  exit 1
fi
exit 0
