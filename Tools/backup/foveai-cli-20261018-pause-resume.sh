#!/bin/bash
# foveai — one switch for every FoveAI service, plus the console/nest UI.
#
# Merged 2026-10-10. Keeps the service-control CLI (the file that replaced the
# foveai.sh symlink) and re-adds the console/nest, so nothing is lost:
#   backup: /home/lumba/FoveAI/Tools/backup/foveai-cli-20261010.sh
#
# Service control (stop/start/status/units) lives here. The full stack
# launcher, the settings console and the nest dashboard are delegated to the
# repo scripts so there is a single source of truth:
#   /home/lumba/FoveAI/foveai.sh          (launcher)
#   /home/lumba/FoveAI/FoveAI_Console.py  (settings / model switching)
#   /home/lumba/FoveAI/foveai_nest.sh     (13-pane dashboard)
#
# New: `--unload` (and `systemctl stop foveai`) tears the whole stack down and
# frees VRAM.
#
# Why `stop` no longer masks: it used to, because the model units ran
# Restart=always and `unload`'s `pkill llama-server` looked like a crash, so
# systemd respawned them within RestartSec. The model units are now
# Restart=no, and a deliberate `systemctl stop` never triggers Restart, so
# the mask addressed a respawn that can no longer happen. `stop` just stops.
#
# New (Phase 1 of Docs/JEN_MIND.md): `foveai mind|wake|idle|lever` — the
# residency controller (runtime/residency.py) that loads the right brain tier
# on demand and frees VRAM when idle.

set -u

FOVEAI_DIR=/home/lumba/FoveAI
LAUNCHER="$FOVEAI_DIR/foveai.sh"
NEST="$FOVEAI_DIR/foveai_nest.sh"
VENV_PY="$FOVEAI_DIR/.venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$(command -v python3)"

# Everything FoveAI knows about, for STATUS — including deliberately-disabled
# units, because seeing them is the point. foveai.service itself is excluded
# so a teardown never stops the umbrella that owns the teardown.
units() {
    systemctl list-unit-files 'foveai-*' 'multigate*' 'xr-vessel*' \
        --no-legend --no-pager 2>/dev/null | awk '{print $1}' | grep -vx 'foveai.service'
}

# Only what you actually want running, for start/stop/halt.
#
# Without this filter `start` woke every foveai-* unit including the ones
# deliberately left disabled — which is how three llama-servers came up
# holding 6.2 GB of VRAM that nothing was using. An override that overrides
# your own decisions is not an override.
# NOTE: `list-unit-files --enabled` is not a valid flag on this systemd, and
# using it silently returned zero units — `foveai start` would have started
# NOTHING. Filter with is-enabled instead, which is slower but honest.
units_enabled() {
    units | while read -r u; do
        [ "$(systemctl is-enabled "$u" 2>/dev/null)" = "enabled" ] && echo "$u"
    done
}

run_on() {
    local list_fn=$1; shift
    local verb=$1; shift
    local u
    for u in $($list_fn); do
        if sudo systemctl "$verb" "$u" >/dev/null 2>&1; then
            printf '  %-34s %s\n' "$u" "$verb"
        else
            printf '  %-34s %-6s skipped\n' "$u" "$verb"
        fi
    done
}

# ── pause/resume: freeze the live fleet in RAM without unloading ──
# SIGSTOP keeps every pid, VRAM allocation and listening socket; frozen
# services just stop answering until resumed. Same scope as unload:
# the looping user units, then every system foveai unit that is live.
# (systemctl is-active still reports "active" for SIGSTOP'd units, so
# resume can find them the same way.)
freeze() {
    local sig="$1"
    local u
    for u in foveai-harden.timer foveai-harden.service foveai-gamepad.service \
             foveai-ptt.service multigate-dev.service; do
        [ "$(systemctl --user is-active "$u" 2>/dev/null)" = "active" ] || continue
        systemctl --user kill --signal="$sig" "$u" >/dev/null 2>&1 \
            && printf '  %-34s %s (user)\n' "$u" "$sig"
    done
    for u in $(units); do
        [ "$(systemctl is-active "$u" 2>/dev/null)" = "active" ] || continue
        sudo systemctl kill --signal="$sig" "$u" >/dev/null 2>&1 \
            && printf '  %-34s %s\n' "$u" "$sig"
    done
}

# Run a mind/residency module from the repo root (the modules import `runtime.*`).
mind_py() { ( cd "$FOVEAI_DIR" && exec "$VENV_PY" "$@" ); }

# ── unload: the full teardown (used by --unload and systemd ExecStop) ──
# Idempotent and safe to re-run. Runs as the invoking user for `foveai
# --unload`, and as root when systemd calls it from ExecStop.
unload() {
    echo "Unloading FoveAI: models, stack, ports..."
    local u

    # 1. user services that loop / hold ports / re-trigger work
    for u in foveai-harden.timer foveai-harden.service foveai-gamepad.service \
             foveai-ptt.service multigate-dev.service; do
        systemctl --user stop "$u" >/dev/null 2>&1 && printf '  %-34s stopped (user)\n' "$u"
    done

    # 2. every system foveai unit, enabled or not (incl. root-run llama units)
    for u in $(units); do
        if sudo systemctl stop "$u" >/dev/null 2>&1 || systemctl stop "$u" >/dev/null 2>&1; then
            printf '  %-34s stopped\n' "$u"
        fi
    done

    # 3. stray, non-systemd instances that systemctl cannot see
    pkill -f 'llama-server'  >/dev/null 2>&1 || true
    pkill -f 'run_xrlf.py'   >/dev/null 2>&1 || true

    # 4. model locks so the next load starts clean
    rm -f "$FOVEAI_DIR"/.model_locks/*.lock \
          "$FOVEAI_DIR"/.model_locks/evict_*.json >/dev/null 2>&1 || true

    # 5. report freed VRAM
    echo "  VRAM now:"
    nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader 2>/dev/null \
        | sed 's/^/    /' || echo "    (nvidia-smi unavailable)"
}

case "${1:-menu}" in
    menu|--menu)         exec /home/lumba/.local/bin/foveai-menu ;;
    # ── settings / consoles ──────────────────────────────────────────
    ghost|--ghost)       exec "$VENV_PY" "$FOVEAI_DIR/Backend/Cognition/session_ghost.py" --chat ;;
    console|--console|chat|--chat)    exec "$VENV_PY" "$FOVEAI_DIR/Backend/Cognition/session_ghost.py" --chat ;;
    settings|fleet)    exec "$VENV_PY" "$FOVEAI_DIR/FoveAI_Console.py" ;;
    spotify|music)     exec "$VENV_PY" "$FOVEAI_DIR/scripts/spotify_ctl.py" "${2:-status}" ;;
    nest|--nest)         exec "$NEST" ;;

    # ── teardown ──────────────────────────────────────────────────────
    unload|--unload)     unload ;;
    # ── freeze / thaw (keeps VRAM + sockets, services just idle) ─────
    pause|--pause)       echo "Pausing FoveAI fleet (SIGSTOP — RAM kept)..."
                         freeze SIGSTOP
                         echo "-> frozen. Thaw with: foveai resume" ;;
    resume|--resume|unpause)
                         echo "Resuming FoveAI fleet (SIGCONT)..."
                         freeze SIGCONT
                         echo "-> live again" ;;
    stop|--stop)
        unload
        echo "Stopping enabled FoveAI services..."
        run_on units_enabled stop
        echo "-> down, VRAM freed. Bring back with: foveai start" ;;

    # ── bring-up / passthrough to the launcher ───────────────────────
    start|--start|--light|--no-front|restart|--restart|apk|--apk|front|--front)
        exec "$LAUNCHER" "$@" ;;

    # ── unit table (kept from the service-control CLI) ───────────────
    units|--units)
        printf '  %-34s %-10s %s\n' UNIT ACTIVE ENABLED
        for u in $(units); do
            printf '  %-34s %-10s %s\n' "$u" \
                "$(systemctl is-active  "$u" 2>&1)" \
                "$(systemctl is-enabled "$u" 2>&1)"
        done ;;
    status|--status)
        exec "$LAUNCHER" --status ;;

    # ── the mind: residency + nerve (Phase 1 of Docs/JEN_MIND.md) ────
    mind|--mind)
        mind_py -m runtime.residency status
        echo
        mind_py -m runtime.nerve show ;;
    wake|--wake)
        mind_py -m runtime.residency load "${2:-A}" ;;
    idle|--idle)
        mind_py -m runtime.residency unload ;;
    lever|--lever)
        mind_py -m runtime.residency lever "${2:?usage: foveai lever 0.0..1.0}" ;;

    help|--help|-h)
        cat <<'EOF'
foveai — FoveAI control switch

  foveai                 open the settings console (switch models, etc.)
  foveai console         same as above
  foveai nest            the 13-pane control dashboard
  foveai --unload        unload all models + close the whole stack, free VRAM
  foveai stop            unload + stop enabled services
  foveai start           start the full stack
  foveai pause           freeze the live fleet in RAM (SIGSTOP, VRAM kept)
  foveai resume          thaw a paused fleet (SIGCONT)
  foveai --light         start backend only (no XRLF model)
  foveai --no-front      start backend + APK, skip frontends
  foveai restart         stop then start
  foveai status          fleet status (ports + VRAM)
  foveai units           systemd unit table (active/enabled)

  The mind (residency + nerve):
  foveai mind            mind state: lever, tier, busy ladder, nerve cells
  foveai wake [A|B]      load a brain tier on demand (default A = background)
  foveai idle            release the resident brain, free VRAM
  foveai lever <0..1>    Companion<->Agent crossfade (0 tool .. 1 partner)

  systemctl stop foveai  unload everything (same as foveai --unload)
EOF
        ;;

    *)
        echo "usage: foveai [console|nest|--unload|stop|start|pause|resume|--light|--no-front|restart|apk|front|status|units|mind|wake|idle|lever|help]"
        exit 1 ;;
esac
