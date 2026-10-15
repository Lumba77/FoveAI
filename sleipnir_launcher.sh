#!/usr/bin/env bash
#
# sleipnir_launcher.sh — Linux-native fleet launcher for FoveAI
# Ported from sleipnir_launcher.js (Windows).
#
# Starts the core stack:
#   - Foveated Memory Proxy  (:8400)
#   - XRLF Runtime + API     (:8402)
#   - WebSocket IPC          (:8403)
#   - Memory Dashboard       (:8414)
#
# The model loads in "dormant" mode — VRAM allocated, ready for inference,
# but no active generation until a request arrives.
#
# Usage:
#   ./sleipnir_launcher.sh              # Start full stack
#   ./sleipnir_launcher.sh --light      # Backend only, no XRLF model
#   ./sleipnir_launcher.sh --stop       # Stop all services
#   ./sleipnir_launcher.sh --status     # Check fleet status

set -euo pipefail

# ─── Paths ──────────────────────────────────────────────────────────
FOVEAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LUMAX_DIR="$(dirname "$FOVEAI_DIR")"
VENV_PYTHON="$FOVEAI_DIR/.venv/bin/python"
[ -x "$VENV_PYTHON" ] || VENV_PYTHON="$(which python3)"
NODE_BIN="${NODE_BIN:-node}"

# ─── Config ─────────────────────────────────────────────────────────
MODEL="${XRLF_MODEL_LOCAL_ID:-gemma-4-e2b-multimodal-v1.0.xrlf}"
XRLF_MODEL_PATH="xrl_encoded/$MODEL"
XRLF_PORT=8402
XRLF_WS_PORT=8403
BACKEND_PORT=8400
DASHBOARD_PORT=8414

# Companion services (orphaned since migration — now systemd-managed).
# STT (:8401) is WebSocket-only: probed via TCP, not HTTP.
SOUL_PORT=8405
TTS_PORT=8409
RELAY_PORT=8413
STT_PORT=8414

# systemd fleet units — the launcher is a thin wrapper once these exist.
have_unit() {
    command -v systemctl &>/dev/null && systemctl cat "$1" &>/dev/null
}

FLEET_UNITS=(
    foveai-nerve.service
    foveai-residency.service
    foveai-backend.service
    foveai-xrlf.service
    foveai-soul.service
    foveai-tts.service
    foveai-relay.service
    foveai-creative.service
    foveai-stt.service
)

# ─── Helpers ────────────────────────────────────────────────────────
log()  { echo "🛸 [Sleipnir] $*"; }
warn() { echo "⚠️  [Sleipnir] $*" >&2; }
err()  { echo "❌ [Sleipnir] $*" >&2; }

port_alive() {
    ss -tlnp "sport = :$1" 2>/dev/null | grep -q LISTEN
}

kill_port() {
    local port="$1"
    local pids
    pids=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' || true)
    for pid in $pids; do
        if [ "$pid" != "$$" ]; then
            kill "$pid" 2>/dev/null || true
        fi
    done
}

# ─── .env loader ────────────────────────────────────────────────────
load_env() {
    local env_path="$FOVEAI_DIR/.env"
    [ -f "$env_path" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip comments and empty lines
        line="${line%%#*}"
        [ -z "${line// }" ] && continue
        # Must contain =
        [[ "$line" != *=* ]] && continue
        key="${line%%=*}"
        val="${line#*=}"
        # Trim whitespace
        key="${key// /}"
        [ -z "$key" ] && continue
        # Strip quotes
        val="${val#\"}"; val="${val%\"}"
        val="${val#\'}"; val="${val%\'}"
        export "$key=$val"
    done < "$env_path"
}

load_env

CREATIVE_PORT="${FOVEAI_CREATIVE_PORT:-8412}"
CREATIVE_VENV="$FOVEAI_DIR/.venv/creative/bin/python"

# ─── Actions ────────────────────────────────────────────────────────

cmd_status() {
    echo "╔══════════════════════════════════════════════╗"
    echo "║         FoveAI Fleet Status                  ║"
    echo "╚═══════════════════════════════════════════════╝"
    echo

    for svc in "Backend:$BACKEND_PORT" "XRLF-Runtime:$XRLF_PORT" "WS-IPC:$XRLF_WS_PORT" "Dashboard:$DASHBOARD_PORT" "Soul:$SOUL_PORT" "TTS:$TTS_PORT" "Relay:$RELAY_PORT" "Creative:$CREATIVE_PORT" "STT:$STT_PORT"; do
        name="${svc%%:*}"
        port="${svc##*:}"
        if port_alive "$port"; then
            echo "  ✅ $name  (:$port)  ACTIVE"
        else
            echo "  ⚪ $name  (:$port)  INACTIVE"
        fi
    done

    echo
    echo "  GPU VRAM:"
    nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv,noheader 2>/dev/null || echo "    (nvidia-smi unavailable)"
}

# systemd owns the fleet when units exist (Restart=always, boot-ordered,
# cgroup-clean teardown). Launcher wraps it: start/stop/status/restart all
# go through systemctl, with nohup fallback only if units are missing.

cmd_stop() {
    log "Stopping FoveAI fleet..."
    local units=()
    for u in "${FLEET_UNITS[@]}"; do
        have_unit "$u" && units+=("$u")
    done
    if [ ${#units[@]} -gt 0 ]; then
        sudo systemctl stop "${units[@]}" 2>/dev/null || \
            systemctl stop "${units[@]}" 2>/dev/null || \
            warn "could not stop units (try: sudo $0 stop)"
    fi
    # fallback / strays: port-kill whatever systemd did not own
    for port in $BACKEND_PORT $XRLF_PORT $XRLF_WS_PORT $DASHBOARD_PORT \
                $SOUL_PORT $TTS_PORT $RELAY_PORT $CREATIVE_PORT $STT_PORT; do
        systemctl is-active --quiet "foveai-*" 2>/dev/null || kill_port "$port"
    done
    pkill -f "run_xrlf.py" 2>/dev/null || true
    sleep 1
    log "Fleet stopped."
    cmd_status
}

cmd_start() {
    local light_mode=false
    [ "${1:-}" = "--light" ] && light_mode=true

    log "Igniting FoveAI fleet..."

    # ── Auto-Cache Busting for Multigate Theme ──
    local mg_idx="$FOVEAI_DIR/Frontend/multigate/index.html"
    if [ -f "$mg_idx" ]; then
        local ts=$(date +%s)
        sed -i -E "s/foveai-aurora\.css\?v=[0-9]+/foveai-aurora.css?v=$ts/g" "$mg_idx"
    fi
    "$VENV_PYTHON" "$FOVEAI_DIR/server_config.py" --refresh-network-config || warn "Network config refresh failed"

    # ── systemd fleet path (preferred): units carry Restart=always and
    # boot ordering, so the fleet survives reboots and crashes on its own.
    local units=()
    for u in "${FLEET_UNITS[@]}"; do
        have_unit "$u" && units+=("$u")
    done
    if [ ${#units[@]} -gt 0 ]; then
        if [ "$light_mode" = true ]; then
            units=($(printf '%s\n' "${units[@]}" | grep -v foveai-xrlf))
        fi
        log "Starting via systemd: ${units[*]}"
        sudo systemctl start "${units[@]}" 2>/dev/null || \
            systemctl start "${units[@]}" 2>/dev/null || \
            err "systemd start failed — falling back to nohup"
        wait_fleet
        cmd_status
        return 0
    fi
    warn "No foveai-*.service units found — legacy nohup mode"

    # ── Zombie sweep ──
    log "Sweeping for zombie processes..."
    for port in $BACKEND_PORT $XRLF_PORT $XRLF_WS_PORT $DASHBOARD_PORT; do
        if port_alive "$port"; then
            warn "Port :$port already in use — killing zombie"
            kill_port "$port"
            sleep 0.5
        fi
    done

    # ── Node 1: Foveated Memory Proxy (:8400) ──
    log "Launching Foveated Memory Proxy (:$BACKEND_PORT)..."
    local fm_dir="$FOVEAI_DIR/foveated-memory"
    if have_unit foveai-backend.service; then
        systemctl --user restart foveai-backend.service
    elif [ -d "$fm_dir" ] && [ -f "$fm_dir/server.js" ] && command -v "$NODE_BIN" &>/dev/null; then
        cd "$fm_dir"
        nohup "$NODE_BIN" server.js >> /home/lumba/foveated_proxy.log 2>&1 &
    else
        # Fallback: Python backend (when Node.js is not installed)
        if ! command -v "$NODE_BIN" &>/dev/null; then
            log "  (Node.js not found — using Python backend fallback)"
        fi
        cd "$FOVEAI_DIR/Backend"
        nohup "$VENV_PYTHON" -m app.main >> /home/lumba/foveai_backend.log 2>&1 &
    fi

    # Wait for backend
    log "Waiting for backend (:$BACKEND_PORT)..."
    for i in $(seq 1 30); do
        port_alive "$BACKEND_PORT" && break
        sleep 0.5
    done
    if port_alive "$BACKEND_PORT"; then
        log "  ✅ Backend online (:$BACKEND_PORT)"
    else
        err "  ❌ Backend failed to start"
    fi

    # ── Node 2: XRLF Runtime (:8402 + :8403 WS) ──
    if [ "$light_mode" = false ]; then
        log "Launching XRLF Runtime with model: $MODEL"
        log "  Model path: $XRLF_MODEL_PATH"
        log "  API: :$XRLF_PORT  WS: :$XRLF_WS_PORT  Dashboard: :$DASHBOARD_PORT"

        if have_unit foveai-xrlf.service; then
            systemctl --user restart foveai-xrlf.service
        else
            cd "$FOVEAI_DIR"
            nohup env XRLF_REPO_ENABLED=true GGML_CUDA_NO_VMM=1 "$VENV_PYTHON" run_xrlf.py \
                --model "$XRLF_MODEL_PATH" \
                --port "$XRLF_PORT" \
                --ws-port "$XRLF_WS_PORT" >> /home/lumba/xrlf_live.log 2>&1 &
        fi

        # The API binds before the model loads — /health answers immediately
        # with load_state. Wait for a real "loaded" (or a real error), not
        # just an open port.
        log "Waiting for XRLF Runtime (:$XRLF_PORT)..."
        local waited=0
        for i in $(seq 1 180); do
            if port_alive "$XRLF_PORT"; then
                local h
                h=$(curl -sf -m 2 "http://127.0.0.1:$XRLF_PORT/health" 2>/dev/null || true)
                if [ -n "$h" ]; then
                    case "$h" in
                        *'"loaded": true'*|*'"loaded":true'*)
                            log "  ✅ XRLF Runtime online — model loaded (:$XRLF_PORT)"
                            break ;;
                        *'"load_state": "error"'*|*'"load_state":"error"'*)
                            err "  ❌ XRLF load_state=error — see /home/lumba/xrlf_live.log"
                            break ;;
                    esac
                fi
            fi
            waited=$((waited+2)); sleep 2
        done
        if ! port_alive "$XRLF_PORT"; then
            err "  ❌ XRLF Runtime never bound :$XRLF_PORT — process died. See /home/lumba/xrlf_live.log"
        elif [ $waited -ge 360 ]; then
            warn "  ⏳ XRLF still loading after 6min — probably still initializing."
            warn "  Watch: tail -f /home/lumba/xrlf_live.log"
        fi
    else
        log "Light mode — skipping XRLF Runtime (no model loaded)"
    fi

    # ── Node 4: Theme API (:8415 — Gallery & Nano-UI) ──
    if port_alive 8415; then
        log "Theme API already online (:8415)"
    else
        log "Launching Theme API (:8415)..."
        cd "$FOVEAI_DIR"
        nohup "$VENV_PYTHON" theme/theme_api.py >> /home/lumba/foveai_theme_api.log 2>&1 &
        for i in $(seq 1 10); do
            port_alive 8415 && break
            sleep 0.5
        done
        if port_alive 8415; then
            log "  ✅ Theme API online (:8415)"
        else
            warn "  ⚠️  Theme API did not bind :8415"
        fi
    fi

    # ── Node 3: Creative Service (:8412 — Dreamscape image gen) ──
    if port_alive "$CREATIVE_PORT"; then
        log "Creative Service already online (:$CREATIVE_PORT)"
    elif [ -x "$CREATIVE_VENV" ] && [ -f "$FOVEAI_DIR/Backend/Creativity/creative_service.py" ]; then
        log "Launching Creative Service (:$CREATIVE_PORT)..."
        cd "$FOVEAI_DIR/Backend/Creativity"
        nohup env FOVEAI_CREATIVE_PORT="$CREATIVE_PORT" FOVEAI_BIND_HOST=127.0.0.1 \
            "$CREATIVE_VENV" creative_service.py >> /home/lumba/foveai_creative.log 2>&1 &
        cd "$FOVEAI_DIR"
        for i in $(seq 1 20); do
            port_alive "$CREATIVE_PORT" && break
            sleep 0.5
        done
        if port_alive "$CREATIVE_PORT"; then
            log "  ✅ Creative Service online (:$CREATIVE_PORT)"
        else
            warn "  ⚠️  Creative Service did not bind :$CREATIVE_PORT — see /home/lumba/foveai_creative.log"
        fi
    else
        warn "Creative Service skipped (no .venv/creative — run the Creativity setup)"
    fi

    # ── Summary ──
    echo
    log "🛸 Fleet deployment complete!"
    cmd_status
}

# Wait for ports across the fleet (systemd path); STT is WS-only (TCP probe).
wait_fleet() {
    local waited=0
    log "Waiting for fleet (XRLF model load can take ~2min)..."
    for i in $(seq 1 120); do
        local all_up=true
        for port in $BACKEND_PORT $XRLF_PORT $XRLF_WS_PORT; do
            port_alive "$port" || all_up=false
        done
        $all_up && break
        waited=$((waited+2)); sleep 2
    done
    if port_alive "$BACKEND_PORT" && port_alive "$XRLF_PORT"; then
        log "  ✅ Core fleet online (backend + XRLF)"
    else
        warn "  ⏳ still waiting — check journalctl -u foveai-xrlf -u foveai-backend"
    fi
}

# ─── Main ───────────────────────────────────────────────────────────
case "${1:-start}" in
    start)   cmd_start "${2:-}" ;;
    --light) cmd_start --light ;;
    stop|--stop) cmd_stop ;;
    status|--status) cmd_status ;;
    restart|--restart) cmd_stop; sleep 2; cmd_start ;;
    list-units) systemctl list-units 'foveai-*' --no-pager ;;
    journal) sudo journalctl -u 'foveai-*' -f --no-pager ;;
    *)
        echo "Usage: $0 {start|--light|stop|status|restart|list-units|journal}"
        exit 1
        ;;
esac
