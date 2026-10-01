#!/usr/bin/env bash
#
# foveai-autostart.sh — Master autostart for all FoveAI services
# Starts at login. Ensures everything is LAN-bound and web-reachable.
#
# Services started:
#   1. SSHD              (system, already enabled)
#   2. xrdp              (system, already enabled)
#   3. Sunshine/Moonlight (user service, already enabled)
#   4. Chrome Remote Desktop
#   5. FoveAI Sleipnir stack (8400-8409, 5176, 5177, 8888)
#   6. Caddy reverse proxy (xarel.net → local services)
#
set -euo pipefail

LOG="/home/lumba/FoveAI/logs/autostart.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG" 2>&1; }

log "=== FoveAI autostart beginning ==="

# ─── 1. Ensure system services are up (SSH, xRDP) ───────────────────
log "Checking system services..."
for svc in sshd xrdp; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        log "  $svc: already running"
    else
        log "  $svc: attempting start (may need sudo)..."
        sudo systemctl start "$svc" 2>/dev/null && log "  $svc: started" || log "  $svc: needs sudo to start"
    fi
done

# ─── 2. Start Sunshine (user service) ───────────────────────────────
log "Checking Sunshine..."
if systemctl --user is-active --quiet sunshine 2>/dev/null; then
    log "  Sunshine: already running"
else
    systemctl --user start sunshine 2>/dev/null && log "  Sunshine: started" || log "  Sunshine: failed to start"
fi

# ─── 3. Start Chrome Remote Desktop ────────────────────────────────
log "Checking Chrome Remote Desktop..."
if pgrep -f "chrome-remote-desktop-host" &>/dev/null; then
    log "  CRD: already running"
elif [ -x /opt/google/chrome-remote-desktop/chrome-remote-desktop-host ]; then
    # Ensure host.json exists
    CRD_CONFIG="$HOME/.config/chrome-remote-desktop"
    if [ ! -f "$CRD_CONFIG/host.json" ]; then
        EXISTING=$(ls "$CRD_CONFIG"/host#*.json 2>/dev/null | head -1)
        if [ -n "$EXISTING" ]; then
            cp "$EXISTING" "$CRD_CONFIG/host.json"
            log "  CRD: copied config to host.json"
        fi
    fi
    DISPLAY=:0 nohup /opt/google/chrome-remote-desktop/chrome-remote-desktop-host --console >> "$LOG" 2>&1 &
    log "  CRD: started (PID $!)"
else
    log "  CRD: not installed"
fi

# ─── 4. Start FoveAI Sleipnir stack ─────────────────────────────────
log "Starting FoveAI stack..."
FOVEAI="/home/lumba/FoveAI"
cd "$FOVEAI"

# Source environment
if [ -f "$FOVEAI/.env" ]; then
    set -a
    source "$FOVEAI/.env"
    set +a
fi

# Start the backend stack (light mode = no frontends, we start them separately)
if ! pgrep -f "foveated-memory" &>/dev/null; then
    nohup "$FOVEAI/foveai.sh" --light >> "$LOG" 2>&1 &
    log "  Sleipnir: started (PID $!)"
    sleep 5  # Give it time to spin up
else
    log "  Sleipnir: already running"
fi

# ─── 5. Start frontend (Multigate — serves XR features when detected) ─
log "Starting frontend..."

# Multigate (:5177) — single frontend, serves XR features when XR client detected
if ! ss -tlnp | grep -q ':5177 '; then
    cd "$FOVEAI/Frontend/multigate"
    nohup npx vite --host 0.0.0.0 --port 5177 >> "$LOG" 2>&1 &
    log "  Multigate: started on 0.0.0.0:5177 (PID $!)"
else
    log "  Multigate: already running"
fi

# APK Server (:8888)
if ! ss -tlnp | grep -q ':8888 '; then
    cd "$FOVEAI"
    nohup python3 apk_server.py >> "$LOG" 2>&1 &
    log "  APK Server: started on 0.0.0.0:8888 (PID $!)"
else
    log "  APK Server: already running"
fi

# ─── 6. Start Cloudflare Tunnel (xarel.net → local) ────────────────
log "Checking Cloudflare Tunnel..."
if command -v cloudflared &>/dev/null; then
    if pgrep -f "cloudflared" &>/dev/null; then
        log "  cloudflared: already running"
    elif [ -f "$HOME/.cloudflared/credentials.json" ]; then
        nohup cloudflared tunnel run --config "$HOME/.cloudflared/config.yml" foveai >> "$LOG" 2>&1 &
        log "  cloudflared: started (PID $!)"
    else
        log "  cloudflared: no credentials.json — run setup first"
        log "  See: cloudflared tunnel login && cloudflared tunnel create foveai"
    fi
else
    log "  cloudflared: not installed"
    log "  Install with: sudo dnf install -y cloudflared"
    log "  Or: https://github.com/cloudflare/cloudflared/releases"
fi

# ─── 7. Firewall — ensure LAN ports are open ────────────────────────
log "Checking firewall..."
if command -v firewall-cmd &>/dev/null; then
    # Open all FoveAI ports for LAN access
    PORTS="3389 47989 47990 48010 5176 5177 8400 8401 8402 8403 8409 8888"
    for port in $PORTS; do
        if ! sudo firewall-cmd --list-ports 2>/dev/null | grep -q "$port/"; then
            sudo firewall-cmd --add-port="$port/tcp" --permanent 2>/dev/null && \
            log "  Firewall: opened $port/tcp"
        fi
    done
    sudo firewall-cmd --reload 2>/dev/null
    log "  Firewall: reloaded"
else
    log "  Firewall: firewall-cmd not found"
fi

# ─── 8. Summary ────────────────────────────────────────────────────
log "=== Autostart complete ==="
log "Services:"
log "  SSH:        $(systemctl is-active sshd 2>/dev/null) on 0.0.0.0:22"
log "  xRDP:       $(systemctl is-active xrdp 2>/dev/null) on 0.0.0.0:3389"
log "  Sunshine:   $(systemctl --user is-active sunshine 2>/dev/null) on 0.0.0.0:47989"
log "  CRD:        $(pgrep -f chrome-remote-desktop-host >/dev/null && echo active || echo inactive)"
log "  Multigate:  $(ss -tlnp | grep -q ':5177' && echo active || echo inactive) on 0.0.0.0:5177"
log "  Backend:     $(ss -tlnp | grep -q ':8400' && echo active || echo inactive) on 0.0.0.0:8400"
log "  APK Server:  $(ss -tlnp | grep -q ':8888' && echo active || echo inactive) on 0.0.0.0:8888"
log ""
LAN_IP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && .venv/bin/python -B -c 'from server_config import ServerConfig; print(ServerConfig.SERVER_IP)')
log "LAN access:  http://${LAN_IP}:5177"
log "Web access:  https://xarel.net (via Cloudflare Tunnel)"
