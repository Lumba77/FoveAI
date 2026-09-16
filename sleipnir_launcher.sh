#!/usr/bin/env bash
#
# sleipnir_launcher.sh — Linux-native fleet launcher for FoveAI
# Ported from sleipnir_launcher.js (Windows).
#
# Starts the core stack:
#   - Foveated Memory Proxy  (:8400)
#   - XRLF Runtime + API     (:8402)
#   - WebSocket IPC          (:8403)
#   - Memory Dashboard       (:8401)
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
NODE_BIN="${NODE_BIN:-node}"

# ─── Config ─────────────────────────────────────────────────────────
MODEL="${XRLF_MODEL_LOCAL_ID:-gemma-4-e2b-multimodal-v1.0.xrlf}"
XRLF_MODEL_PATH="xrl_encoded/$MODEL"
XRLF_PORT=8402
XRLF_WS_PORT=8403
BACKEND_PORT=8400
DASHBOARD_PORT=8401

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

# ─── Actions ────────────────────────────────────────────────────────

cmd_status() {
    echo "╔══════════════════════════════════════════════╗"
    echo "║         FoveAI Fleet Status                  ║"
    echo "╚═══════════════════════════════════════════════╝"
    echo

    for svc in "Backend:$BACKEND_PORT" "XRLF-Runtime:$XRLF_PORT" "WS-IPC:$XRLF_WS_PORT" "Dashboard:$DASHBOARD_PORT"; do
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

# systemd --user owns the fleet when the units exist (Restart=always,
# cgroup-clean teardown). nohup spawns remain as fallback only.
have_unit() {
    command -v systemctl &>/dev/null && systemctl --user cat "$1" &>/dev/null
}

cmd_stop() {
    log "Stopping FoveAI fleet..."
    if have_unit foveai-xrlf.service || have_unit foveai-backend.service; then
        systemctl --user stop foveai-xrlf.service foveai-backend.service 2>/dev/null || true
    fi
    kill_port "$XRLF_PORT"
    kill_port "$XRLF_WS_PORT"
    kill_port "$BACKEND_PORT"
    kill_port "$DASHBOARD_PORT"
    # Kill any stray run_xrlf processes
    pkill -f "run_xrlf.py" 2>/dev/null || true
    sleep 1
    log "Fleet stopped."
    cmd_status
}

cmd_start() {
    local light_mode=false
    [ "${1:-}" = "--light" ] && light_mode=true

    log "Igniting FoveAI fleet..."

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

    # ── Summary ──
    echo
    log "🛸 Fleet deployment complete!"
    cmd_status
}

# ─── Main ───────────────────────────────────────────────────────────
case "${1:-start}" in
    start)   cmd_start "${2:-}" ;;
    --light) cmd_start --light ;;
    stop|--stop) cmd_stop ;;
    status|--status) cmd_status ;;
    restart|--restart) cmd_stop; sleep 2; cmd_start ;;
    *)
        echo "Usage: $0 {start|--light|stop|status|restart}"
        exit 1
        ;;
esac
