#!/usr/bin/env bash
#
# FoveAI_command.sh — one entry point for the FoveAI stack.
#
# Linux-native equivalent of FoveAI_command.bat. All service lifecycle goes
# through systemd --user (foveai-backend / foveai-xrlf / foveai-soul), which
# owns the processes, restarts them on crash, and kills them cleanly.
#
# Usage:
#   ./FoveAI_command.sh            # start fleet + open FoveAI Command panel
#   ./FoveAI_command.sh status     # fleet status
#   ./FoveAI_command.sh stop       # stop fleet
#   ./FoveAI_command.sh restart    # restart fleet
#   ./FoveAI_command.sh panel      # open the Command panel only
#   ./FoveAI_command.sh logs       # tail the XRLF runtime log
#
set -euo pipefail

FOVEAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PANEL_URL="http://localhost:8401/memory/settings.html"
MULTIGATE_URL="http://localhost:5177"

log()  { echo "🎛️  [FoveAI] $*"; }
err()  { echo "❌ [FoveAI] $*" >&2; }

open_panel() {
    log "Opening FoveAI Command → $PANEL_URL"
    if command -v xdg-open &>/dev/null; then
        xdg-open "$PANEL_URL" &>/dev/null &
    else
        echo "  Panel URL: $PANEL_URL"
        echo "  Multigate: $MULTIGATE_URL  (Settings → FoveAI Command)"
    fi
}

cmd_status() {
    systemctl --user list-units 'foveai*' --no-pager --no-legend 2>/dev/null || true
    echo
    for p in 8400 8401 8402 8403 5176 5177; do
        if ss -tln "sport = :$p" 2>/dev/null | grep -q LISTEN; then
            echo "  ✅ :$p listening"
        else
            echo "  ⚪ :$p down"
        fi
    done
    echo
    h=$(curl -sf -m 2 http://127.0.0.1:8402/health 2>/dev/null || true)
    [ -n "$h" ] && echo "  XRLF: $h"
}

cmd_start() {
    log "Starting FoveAI fleet (systemd)…"
    systemctl --user start foveai-backend.service foveai-soul.service
    systemctl --user start foveai-xrlf.service
    log "Model loads in background — watch: ./FoveAI_command.sh logs"
}

cmd_stop() {
    log "Stopping FoveAI fleet…"
    systemctl --user stop foveai-xrlf.service foveai-backend.service foveai-soul.service 2>/dev/null || true
    pkill -f 'run_xrlf\.py' 2>/dev/null || true
    log "Fleet stopped."
}

case "${1:-start}" in
    start)    cmd_start; open_panel ;;
    panel)    open_panel ;;
    status)   cmd_status ;;
    stop)     cmd_stop ;;
    restart)  cmd_stop; sleep 2; cmd_start ;;
    logs)     exec tail -f /home/lumba/xrlf_live.log ;;
    *)        grep -E '^#( |$)' "$0" | sed 's/^# \{0,2\}//' ;;
esac
