#!/usr/bin/env bash
#
# foveai.sh — One-command launcher for the full FoveAI stack.
#
# Starts everything the Quest app needs:
#   1. Foveated Memory Proxy  (:8400)  — Node.js proxy (Jenna, Quest, WebXR)
#   2. XRLF Runtime + API     (:8402)  — Gemma 4 E2B model (local LLM)
#   3. WebSocket IPC          (:8403)  — Real-time avatar/soul bridge
#   4. Memory Dashboard       (:8414)  — Web UI for memory inspection
#   5. Ignition Server        (:8416)  — Lightweight HTTP trigger for the button
#   6. APK Download Server    (:8888)  — Serves AliceVR.apk to Quest browser
#   7. Multigate Frontend     (:5177)  — React dashboard (xarel.net)
#   8. XR Vessel Frontend     (:5176)  — WebXR Three.js avatar scene
#
# Usage:
#   foveai.sh              # Start everything (full stack + frontends + APK)
#   foveai.sh --light      # Backend only, no XRLF model (saves VRAM)
#   foveai.sh --no-front   # Skip frontends (just backend + APK)
#   foveai.sh --stop       # Stop all services
#   foveai.sh --status     # Check what's running
#   foveai.sh --restart    # Stop then start
#   foveai.sh --apk        # Start only the APK server
#   foveai.sh --nest       # 13-pane control dashboard (big console centre,
#                          #   12 metric panes; moves with Ctrl-b n)
#   foveai.sh console      # The numbered-menu console on its own
#   foveai.sh --help       # Show this help
#
# Install globally:
#   sudo ln -sf /home/lumba/FoveAI/foveai.sh /usr/local/bin/foveai
#
# Then just run: foveai

set -euo pipefail

# Prefer the bundled Node 24 — vite 8/rolldown needs node:util's styleText
# (Node ≥20.12); the system node is 18.x and the frontends crash on boot.
if [ -x "$HOME/.local/node24/bin/node" ]; then
    export PATH="$HOME/.local/node24/bin:$PATH"
fi

# ─── Paths ──────────────────────────────────────────────────────────
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
FOVEAI_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
SLEIPNIR="$FOVEAI_DIR/sleipnir_launcher.sh"
IGNITION_SCRIPT="$FOVEAI_DIR/ignition_server.py"
APK_DIR="$FOVEAI_DIR/client_quest"
APK_FILE="$APK_DIR/AliceVR.apk"
VENV_PYTHON="$FOVEAI_DIR/.venv/bin/python"

# ─── Ports ──────────────────────────────────────────────────────────
BACKEND_PORT=8400
XRLF_PORT=8402
WS_PORT=8403
DASHBOARD_PORT=8414
SOUL_PORT=8405
TTS_PORT=8401
RELAY_PORT=8413
CREATIVE_PORT=8412
STT_PORT=8408
IGNITION_PORT=8416
APK_PORT=8888
MULTIGATE_PORT=5177
VESSEL_PORT=5176

# ─── Frontend dirs ──────────────────────────────────────────────────
MULTIGATE_DIR="$FOVEAI_DIR/Frontend/multigate"
VESSEL_DIR="$FOVEAI_DIR/Frontend/XR_Vessel"

# ─── Helpers ────────────────────────────────────────────────────────
log()  { echo "🛸 [FoveAI] $*"; }
warn() { echo "⚠️  [FoveAI] $*" >&2; }
err()  { echo "❌ [FoveAI] $*" >&2; }

port_alive() {
    ss -tlnp "sport = :$1" 2>/dev/null | grep -q LISTEN
}

kill_port() {
    local port="$1"
    local pids
    pids=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' || true)
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
}

# ─── APK Server ─────────────────────────────────────────────────────

start_apk_server() {
    if port_alive "$APK_PORT"; then
        log "APK server already running (:$APK_PORT)"
        return
    fi
    if [ ! -f "$APK_FILE" ]; then
        warn "APK not found at $APK_FILE — skipping APK server"
        return
    fi
    log "Starting APK download server (:$APK_PORT)..."
    cd "$APK_DIR"
    nohup python3 -m http.server "$APK_PORT" --bind 0.0.0.0 > /tmp/foveai_apk_server.log 2>&1 &
    sleep 1
    if port_alive "$APK_PORT"; then
        log "  ✅ APK server online (:$APK_PORT)"
        log "  📦 Download: http://$(hostname -I | awk '{print $1}'):${APK_PORT}/AliceVR.apk"
    else
        err "  ❌ APK server failed to start"
    fi
}

stop_apk_server() {
    kill_port "$APK_PORT"
}

# ─── Ignition Server ────────────────────────────────────────────────

start_ignition() {
    if port_alive "$IGNITION_PORT"; then
        log "Ignition server already running (:$IGNITION_PORT)"
        return
    fi
    if [ ! -f "$IGNITION_SCRIPT" ]; then
        warn "Ignition script not found — skipping"
        return
    fi
    log "Starting ignition server (:$IGNITION_PORT)..."
    cd "$FOVEAI_DIR"
    nohup python3 "$IGNITION_SCRIPT" > /tmp/foveai_ignition.log 2>&1 &
    sleep 1
    if port_alive "$IGNITION_PORT"; then
        log "  ✅ Ignition server online (:$IGNITION_PORT)"
    else
        err "  ❌ Ignition server failed to start"
    fi
}

stop_ignition() {
    kill_port "$IGNITION_PORT"
}

# ─── Frontends ──────────────────────────────────────────────────────

start_frontends() {
    local lan_ip
    lan_ip="$(hostname -I | awk '{print $1}')"

    # Multigate (React dashboard — port 8414)
    if port_alive "$MULTIGATE_PORT"; then
        log "Multigate already running (:$MULTIGATE_PORT)"
    elif [ -f "$MULTIGATE_DIR/package.json" ] && command -v npm &>/dev/null; then
        log "Starting Multigate frontend (:$MULTIGATE_PORT)..."
        cd "$MULTIGATE_DIR"
        [ -d node_modules ] || npm install --silent 2>/dev/null
        setsid bash -c "cd '$MULTIGATE_DIR' && npm run dev -- --port $MULTIGATE_PORT --host >> /tmp/foveai_multigate.log 2>&1" &
        sleep 3
        if port_alive "$MULTIGATE_PORT"; then
            log "  ✅ Multigate online (:$MULTIGATE_PORT)"
            log "  🌐 http://${lan_ip}:${MULTIGATE_PORT}"
        else
            err "  ❌ Multigate failed to start (check /tmp/foveai_multigate.log)"
        fi
    else
        warn "Multigate not found or npm missing — skipping"
    fi

    # XR Vessel (WebXR Three.js — port 5176)
    if port_alive "$VESSEL_PORT"; then
        log "XR Vessel already running (:$VESSEL_PORT)"
    elif [ -f "$VESSEL_DIR/package.json" ] && command -v npm &>/dev/null; then
        log "Starting XR Vessel frontend (:$VESSEL_PORT)..."
        cd "$VESSEL_DIR"
        [ -d node_modules ] || npm install --silent 2>/dev/null
        setsid bash -c "cd '$VESSEL_DIR' && npm run dev -- --port $VESSEL_PORT --host >> /tmp/foveai_vessel.log 2>&1" &
        sleep 3
        if port_alive "$VESSEL_PORT"; then
            log "  ✅ XR Vessel online (:$VESSEL_PORT)"
            log "  🌐 http://${lan_ip}:${VESSEL_PORT}"
        else
            err "  ❌ XR Vessel failed to start (check /tmp/foveai_vessel.log)"
        fi
    else
        warn "XR Vessel not found or npm missing — skipping"
    fi
}

stop_frontends() {
    kill_port "$MULTIGATE_PORT"
    kill_port "$VESSEL_PORT"
}

# ─── Status ─────────────────────────────────────────────────────────

cmd_status() {
    echo
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║              FoveAI Fleet Status                          ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo

    for svc in \
        "Foveated Proxy:$BACKEND_PORT" \
        "XRLF Runtime:$XRLF_PORT" \
        "WS-IPC:$WS_PORT" \
        "Dashboard:$DASHBOARD_PORT" \
        "Soul:$SOUL_PORT" \
        "TTS:$TTS_PORT" \
        "Relay:$RELAY_PORT" \
        "Creative:$CREATIVE_PORT" \
        "STT:$STT_PORT" \
        "Ignition:$IGNITION_PORT" \
        "Multigate:$MULTIGATE_PORT" \
        "XR Vessel:$VESSEL_PORT" \
        "APK Server:$APK_PORT"
    do
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

    echo
    echo "  Endpoints:"
    echo "    Backend API : http://localhost:${BACKEND_PORT}/v1/chat/completions"
    echo "    Dashboard   : http://localhost:${DASHBOARD_PORT}/memory"
    echo "    XRLF Health : http://localhost:${XRLF_PORT}/health"
    echo "    APK Download: http://$(hostname -I | awk '{print $1}'):${APK_PORT}/AliceVR.apk"
    echo "    Multigate    : http://$(hostname -I | awk '{print $1}'):${MULTIGATE_PORT}"
    echo "    XR Vessel    : http://$(hostname -I | awk '{print $1}'):${VESSEL_PORT}"
    echo "    Ignition    : http://localhost:${IGNITION_PORT}/ignition/status"
    echo
}

# ─── Stop ───────────────────────────────────────────────────────────

# systemd fleet units (installed from /tmp/opencode/units — see
# sleipnir_launcher.sh). When present, stop/start/status all wrap systemctl
# across the entire stack: 8400/8412/8402/8403/8405/8401/8413/8413/8409.
have_fleet_unit() {
    command -v systemctl &>/dev/null && systemctl cat "$1" &>/dev/null
}

FLEET_UNITS=(
    foveai-nerve.service
    foveai-residency.service
    foveai-backend.service
    foveai-nova.service
    foveai-xrlf.service
    foveai-soul.service
    foveai-tts.service
    foveai-relay.service
    foveai-creative.service
    foveai-stt.service
)

cmd_stop() {
    log "Stopping FoveAI fleet..."
    stop_frontends
    stop_apk_server
    stop_ignition
    local units=()
    for u in "${FLEET_UNITS[@]}"; do
        have_fleet_unit "$u" && units+=("$u")
    done
    if [ ${#units[@]} -gt 0 ]; then
        sudo systemctl stop "${units[@]}" 2>/dev/null || \
            systemctl stop "${units[@]}" 2>/dev/null || true
    fi
    if [ -f "$SLEIPNIR" ]; then
        bash "$SLEIPNIR" --stop 2>/dev/null || true
    fi
    # Kill any stray XRLF processes
    pkill -f "run_xrlf.py" 2>/dev/null || true
    sleep 1
    log "Fleet stopped."
    cmd_status
}

# ─── Start ──────────────────────────────────────────────────────────

cmd_start() {
    local light_mode=false
    local skip_frontends=false
    [ "${1:-}" = "--light" ] && light_mode=true
    [ "${1:-}" = "--no-front" ] && skip_frontends=true
    [ "${2:-}" = "--no-front" ] && skip_frontends=true

    log "Igniting FoveAI fleet..."

    # 1. Core backend + XRLF runtime via sleipnir
    if [ -f "$SLEIPNIR" ]; then
        if [ "$light_mode" = true ]; then
            bash "$SLEIPNIR" --light
        else
            bash "$SLEIPNIR"
        fi
    else
        err "sleipnir_launcher.sh not found at $SLEIPNIR"
        return 1
    fi

    # 2. Ignition server (for the multigate button)
    start_ignition

    # 3. APK download server
    start_apk_server

    # 4. Frontends (multigate + XR vessel)
    if [ "$skip_frontends" = false ]; then
        start_frontends
    else
        log "Skipping frontends (--no-front)"
    fi

    # 5. Summary
    echo
    log "🛸 FoveAI fleet ready!"
    cmd_status
}

# ─── Help ───────────────────────────────────────────────────────────

cmd_help() {
    cat <<'EOF'
FoveAI — One-command launcher for the full FoveAI stack

Usage:
  foveai.sh              Start everything (full stack + frontends + APK)
  foveai.sh --light      Backend only, no XRLF model (saves VRAM)
  foveai.sh --no-front   Skip frontends (just backend + APK)
  foveai.sh --stop       Stop all services
  foveai.sh --status     Check what's running
  foveai.sh --restart    Stop then start
  foveai.sh --apk        Start only the APK download server
  foveai.sh --help       Show this help

Services started:
  :8400  Foveated Memory Proxy (Node.js — Jenna, Quest, WebXR)
  :8402  XRLF Runtime (Gemma 4 E2B local LLM)
  :8403  WebSocket IPC (real-time avatar/soul bridge)
  :8414  Memory Dashboard (web UI)
  :8401  Ignition Server (HTTP trigger for multigate button)
  :8888  APK Download Server (serves AliceVR.apk to Quest)
  :5177  Multigate Frontend (React dashboard)
  :5176  XR Vessel Frontend (WebXR Three.js avatar scene)

Install globally:
  sudo ln -sf /home/lumba/FoveAI/foveai.sh /usr/local/bin/foveai
  Then just run: foveai
EOF
}

# ─── Main ───────────────────────────────────────────────────────────

case "${1:-start}" in
    nest|--nest) exec "$FOVEAI_DIR/foveai_nest.sh" ;;
    console)     exec "$VENV_PYTHON" "$FOVEAI_DIR/FoveAI_Console.py" ;;
    start|--start)        cmd_start ;;
    --light)     cmd_start --light ;;
    --no-front)  cmd_start --no-front ;;
    stop|--stop) cmd_stop ;;
    status|--status) cmd_status ;;
    restart|--restart) cmd_stop; sleep 2; cmd_start ;;
    apk|--apk)   start_apk_server; cmd_status ;;
    front|--front) start_frontends; cmd_status ;;
    help|--help|-h) cmd_help ;;
    *)
        echo "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
