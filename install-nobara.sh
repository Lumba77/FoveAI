#!/usr/bin/env bash
#
# install-nobara.sh — One-shot failsafe installer for FoveAI on Nobara/Fedora Linux
#
# Installs everything needed for a complete FoveAI development and runtime
# environment with at least 3 remote desktop services, full backend stack,
# web frontend, and Cloudflare Tunnel for xarel.net access.
#
# Design principles:
#   - Idempotent: safe to run multiple times
#   - Graceful: detects existing services/ports/processes and skips if running
#   - Failsafe: continues on errors, reports what failed, never destroys data
#   - Non-interactive: no prompts that could hang (except sudo password)
#
# Remote desktop services installed:
#   1. SSHD              — Secure shell access (port 22)
#   2. xRDP             — Remote Desktop Protocol (port 3389)
#   3. Chrome Remote Desktop — Google relay-based remote access
#   4. Sunshine/Moonlight — Game streaming (ports 47989-48010)
#   5. VNC (fallback)    — Virtual Network Computing (port 5901)
#   6. RustDesk (bonus)  — P2P remote desktop
#
# Usage:
#   ./install-nobara.sh                    Full install
#   ./install-nobara.sh --skip-remote      Skip remote desktop setup
#   ./install-nobara.sh --skip-stack       Skip FoveAI backend stack
#   ./install-nobara.sh --skip-frontend    Skip Multigate frontend
#   ./install-nobara.sh --skip-tunnel      Skip Cloudflare Tunnel
#   ./install-nobara.sh --skip-autostart   Skip autostart configuration
#   ./install-nobara.sh --force-restart    Restart services even if running
#   ./install-nobara.sh --dry-run          Show what would be done
#   ./install-nobara.sh --help             Show help
#

# ─── Don't use set -e; we handle errors manually for failsafe ──────
set -uo pipefail

# ─── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
BLUE='\033[0;34m'
NC='\033[0m'

# ─── Counters ───────────────────────────────────────────────────────
INSTALLED=0
SKIPPED=0
FAILED=0
WARNINGS=0

# ─── Logging ────────────────────────────────────────────────────────
log()  { echo -e "${GREEN}[INSTALL]${NC} $*"; }
warn() { echo -e "${YELLOW}[INSTALL]${NC} $*"; ((WARNINGS++)); }
err()  { echo -e "${RED}[INSTALL]${NC} $*" >&2; ((FAILED++)); }
step() { echo -e "${CYAN}[INSTALL]${NC} ${BOLD}Step $1${NC}: $2"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; ((INSTALLED++)); }
skip() { echo -e "${BLUE}  ⊘${NC} $* (already $2)"; ((SKIPPED++)); }
fail() { echo -e "${RED}  ✗${NC} $*"; ((FAILED++)); }

# ─── Paths ─────────────────────────────────────────────────────────
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
FOVEAI_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
USER_NAME="$(whoami)"
USER_HOME="$HOME"
LOG_DIR="$FOVEAI_DIR/logs"
LOG_FILE="$LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$LOG_DIR"

# ─── Parse args ────────────────────────────────────────────────────
SKIP_REMOTE=0
SKIP_STACK=0
SKIP_FRONTEND=0
SKIP_TUNNEL=0
SKIP_AUTOSTART=0
FORCE_RESTART=0
DRY_RUN=0

for arg in "$@"; do
    case "$arg" in
        --skip-remote)    SKIP_REMOTE=1 ;;
        --skip-stack)     SKIP_STACK=1 ;;
        --skip-frontend)  SKIP_FRONTEND=1 ;;
        --skip-tunnel)    SKIP_TUNNEL=1 ;;
        --skip-autostart) SKIP_AUTOSTART=1 ;;
        --force-restart)  FORCE_RESTART=1 ;;
        --dry-run)        DRY_RUN=1 ;;
        --help|-h)
            cat <<'EOF'
FoveAI Nobara/Fedora Installer (Failsafe)
=========================================
Installs a complete FoveAI environment with remote desktop services.
Idempotent — safe to run multiple times. Detects existing services and
skips gracefully.

Usage:
  ./install-nobara.sh                    Full install
  ./install-nobara.sh --skip-remote      Skip remote desktop setup
  ./install-nobara.sh --skip-stack       Skip FoveAI backend stack
  ./install-nobara.sh --skip-frontend    Skip Multigate frontend
  ./install-nobara.sh --skip-tunnel      Skip Cloudflare Tunnel
  ./install-nobara.sh --skip-autostart   Skip autostart configuration
  ./install-nobara.sh --force-restart    Restart services even if running
  ./install-nobara.sh --dry-run          Show what would be done
  ./install-nobara.sh --help             Show this help

Remote desktop services installed:
  1. SSHD              — Secure shell (port 22)
  2. xRDP             — Remote Desktop Protocol (port 3389)
  3. Chrome Remote Desktop — Google relay (no ports needed)
  4. Sunshine/Moonlight — Game streaming (ports 47989-48010)
  5. VNC (fallback)    — Virtual Network Computing (port 5901)
  6. RustDesk (bonus)  — P2P remote desktop
EOF
            exit 0
            ;;
        *) warn "Unknown argument: $arg" ;;
    esac
done

# ─── Sudo check ────────────────────────────────────────────────────
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO="sudo"
    else
        err "Need root or sudo access"
        exit 1
    fi
fi

# ─── Dry run helper ─────────────────────────────────────────────────
run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        echo -e "${BLUE}  [DRY]${NC} $*"
        return 0
    fi
    eval "$@" 2>&1
    return $?
}

# ─── Service helpers ───────────────────────────────────────────────
service_active() {
    systemctl is-active --quiet "$1" 2>/dev/null
}

service_user_active() {
    systemctl --user is-active --quiet "$1" 2>/dev/null
}

service_enabled() {
    systemctl is-enabled "$1" 2>/dev/null | grep -q "enabled"
}

port_open() {
    ss -tlnp 2>/dev/null | grep -q ":$1 "
}

port_open_udp() {
    ss -ulnp 2>/dev/null | grep -q ":$1 "
}

process_running() {
    pgrep -f "$1" &>/dev/null
}

file_exists() {
    [ -f "$1" ]
}

dir_exists() {
    [ -d "$1" ]
}

command_exists() {
    command -v "$1" &>/dev/null
}

package_installed() {
    rpm -q "$1" &>/dev/null
}

# ─── Welcome ───────────────────────────────────────────────────────
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  FoveAI Nobara/Fedora Installer (Failsafe)                  ║"
echo "║  Complete setup: remote desktop + backend + frontend + web  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  Repo:       $FOVEAI_DIR"
echo "  User:       $USER_NAME"
echo "  Home:       $USER_HOME"
echo "  Log:        $LOG_FILE"
[ "$DRY_RUN" -eq 1 ] && echo -e "  ${YELLOW}DRY RUN${NC} — no changes will be made"
[ "$FORCE_RESTART" -eq 1 ] && echo -e "  ${YELLOW}FORCE RESTART${NC} — services will be restarted"
echo ""

# Tee all output to log
exec > >(tee -a "$LOG_FILE") 2>&1

# ═══════════════════════════════════════════════════════════════════
# STEP 1: System packages
# ═══════════════════════════════════════════════════════════════════
step 1 "System packages"

PACKAGES="wget curl git unzip python3 python3-pip python3-devel nodejs npm binutils dpkg xdg-utils firewall-config"
NEED_INSTALL=""

for pkg in $PACKAGES; do
    if package_installed "$pkg" 2>/dev/null || command_exists "$pkg" 2>/dev/null; then
        skip "$pkg" "installed"
    else
        NEED_INSTALL="$NEED_INSTALL $pkg"
    fi
done

if [ -n "$NEED_INSTALL" ]; then
    log "Installing missing packages:$NEED_INSTALL"
    run "$SUDO dnf install -y -q$NEED_INSTALL 2>&1 | tail -5" || warn "Some packages may have failed"
else
    log "All system packages already installed"
fi

# Install UV (Python package manager)
if command_exists "uv"; then
    skip "uv" "installed"
else
    log "Installing uv..."
    run "curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1 | tail -3" || warn "uv install failed"
    export PATH="$HOME/.local/bin:$PATH"
fi

ok "System packages checked"

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Remote desktop services (at least 3)
# ═══════════════════════════════════════════════════════════════════
if [ "$SKIP_REMOTE" -eq 0 ]; then
step 2 "Remote desktop services (6 services)"

# ─── 2a. SSHD ──────────────────────────────────────────────────────
log "Checking SSHD..."
if package_installed "openssh-server" 2>/dev/null; then
    skip "openssh-server" "installed"
else
    log "  Installing openssh-server..."
    run "$SUDO dnf install -y -q openssh-server 2>&1 | tail -3" || fail "openssh-server install"
fi

# Generate host keys if missing
if [ ! -f /etc/ssh/ssh_host_ed25519_key ] && [ "$DRY_RUN" -eq 0 ]; then
    $SUDO ssh-keygen -A 2>/dev/null || warn "ssh-keygen failed"
fi

# Enable password authentication if not already set
if [ "$DRY_RUN" -eq 0 ]; then
    if grep -q "^#PasswordAuthentication" /etc/ssh/sshd_config 2>/dev/null; then
        $SUDO sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
        log "  Enabled password authentication in sshd_config"
    elif ! grep -q "^PasswordAuthentication" /etc/ssh/sshd_config 2>/dev/null; then
        echo "PasswordAuthentication yes" | $SUDO tee -a /etc/ssh/sshd_config > /dev/null
        log "  Added PasswordAuthentication yes to sshd_config"
    fi
fi

if service_active "sshd"; then
    if [ "$FORCE_RESTART" -eq 1 ]; then
        run "$SUDO systemctl restart sshd" && ok "SSHD restarted" || fail "SSHD restart"
    else
        skip "SSHD service" "running on :22"
    fi
else
    run "$SUDO systemctl enable --now sshd" && ok "SSHD started on :22" || fail "SSHD start"
fi

# ─── 2b. xRDP ──────────────────────────────────────────────────────
log "Checking xRDP..."
if package_installed "xrdp" 2>/dev/null; then
    skip "xrdp package" "installed"
else
    log "  Installing xrdp..."
    run "$SUDO dnf install -y -q xrdp 2>&1 | tail -3" || fail "xrdp install"
fi

if service_active "xrdp"; then
    if [ "$FORCE_RESTART" -eq 1 ]; then
        run "$SUDO systemctl restart xrdp" && ok "xRDP restarted" || fail "xRDP restart"
    else
        skip "xRDP service" "running on :3389"
    fi
else
    run "$SUDO systemctl enable --now xrdp" && ok "xRDP started on :3389" || fail "xRDP start"
    # Also start sesman if available
    if systemctl list-unit-files 2>/dev/null | grep -q "xrdp-sesman"; then
        run "$SUDO systemctl enable --now xrdp-sesman 2>/dev/null" || true
    fi
fi

# ─── 2c. Chrome Remote Desktop ─────────────────────────────────────
log "Checking Chrome Remote Desktop..."
CRD_DIR="/opt/google/chrome-remote-desktop"
CRD_CONFIG="$USER_HOME/.config/chrome-remote-desktop"

if file_exists "$CRD_DIR/start-host"; then
    skip "CRD binary" "installed"
else
    log "  Downloading CRD..."
    ARCH_DEB="amd64"
    [ "$(uname -m)" = "aarch64" ] && ARCH_DEB="arm64"

    CRD_TMP="/tmp/crd-install-$$"
    mkdir -p "$CRD_TMP"

    if run "wget -q 'https://dl.google.com/linux/direct/chrome-remote-desktop_current_${ARCH_DEB}.deb' -O $CRD_TMP/crd.deb"; then
        log "  Extracting CRD..."
        cd "$CRD_TMP"
        if command_exists "dpkg-deb"; then
            dpkg-deb -x crd.deb . 2>/dev/null
        else
            ar x crd.deb 2>/dev/null
            tar xf data.tar.* 2>/dev/null || tar xf data.tar.xz 2>/dev/null || tar xf data.tar.gz 2>/dev/null
        fi

        if [ -d "opt/google/chrome-remote-desktop" ]; then
            run "$SUDO mkdir -p $CRD_DIR"
            run "$SUDO cp -r opt/google/chrome-remote-desktop/* $CRD_DIR/"
            [ -d usr/bin ] && run "$SUDO cp -r usr/bin/* /usr/bin/" || true
            [ -d usr/share ] && run "$SUDO cp -r usr/share/* /usr/share/" || true
            ok "CRD installed to $CRD_DIR"
        else
            fail "CRD extraction"
        fi
        cd /tmp && rm -rf "$CRD_TMP"
    else
        fail "CRD download"
    fi
fi

# Create CRD system service (idempotent — only if not exists or differs)
CRD_SERVICE="/etc/systemd/system/crd-host.service"
CRD_SERVICE_CONTENT="[Unit]
Description=Chrome Remote Desktop Host
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Environment=DISPLAY=:0
ExecStart=$CRD_DIR/chrome-remote-desktop-host --console
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target"

if [ "$DRY_RUN" -eq 0 ]; then
    NEEDS_WRITE=1
    if file_exists "$CRD_SERVICE"; then
        EXISTING=$(cat "$CRD_SERVICE" 2>/dev/null)
        if [ "$EXISTING" = "$CRD_SERVICE_CONTENT" ]; then
            NEEDS_WRITE=0
        fi
    fi
    if [ "$NEEDS_WRITE" -eq 1 ]; then
        echo "$CRD_SERVICE_CONTENT" | $SUDO tee "$CRD_SERVICE" > /dev/null
        $SUDO systemctl daemon-reload
        log "  CRD service file written"
    fi
fi

# Enable CRD service
if service_enabled "crd-host" 2>/dev/null; then
    skip "CRD service" "enabled"
else
    run "$SUDO systemctl enable crd-host 2>/dev/null" && ok "CRD service enabled" || true
fi

# Start CRD if not running and config exists
mkdir -p "$CRD_CONFIG"
if [ ! -f "$CRD_CONFIG/host.json" ]; then
    EXISTING=$(ls "$CRD_CONFIG"/host#*.json 2>/dev/null | head -1)
    if [ -n "$EXISTING" ]; then
        cp "$EXISTING" "$CRD_CONFIG/host.json"
        log "  CRD: copied existing config to host.json"
    fi
fi

if process_running "chrome-remote-desktop-host"; then
    skip "CRD daemon" "running"
elif file_exists "$CRD_CONFIG/host.json"; then
    if [ "$DRY_RUN" -eq 0 ]; then
        run "$SUDO systemctl start crd-host 2>/dev/null" && ok "CRD daemon started" || {
            # Fallback: start directly
            DISPLAY=:0 nohup "$CRD_DIR/chrome-remote-desktop-host" --console >> "$LOG_FILE" 2>&1 &
            ok "CRD daemon started (direct)"
        }
    fi
else
    warn "  CRD: not configured — run with OAuth code to configure"
fi

# ─── 2d. Sunshine (Moonlight host) ────────────────────────────────
log "Checking Sunshine..."
SUNSHINE_INSTALLED=0
if package_installed "sunshine" 2>/dev/null; then
    SUNSHINE_INSTALLED=1
    skip "Sunshine package" "installed"
elif flatpak list 2>/dev/null | grep -qi "sunshine"; then
    SUNSHINE_INSTALLED=1
    skip "Sunshine flatpak" "installed"
else
    log "  Installing Sunshine..."
    if run "$SUDO dnf install -y -q sunshine 2>&1 | tail -3"; then
        SUNSHINE_INSTALLED=1
        ok "Sunshine installed via dnf"
    else
        warn "  Sunshine not in repos — trying Flatpak..."
        if run "flatpak install -y flathub dev.lizardbyte.app.Sunshine 2>/dev/null"; then
            SUNSHINE_INSTALLED=1
            ok "Sunshine installed via Flatpak"
        else
            fail "Sunshine install"
        fi
    fi
fi

if [ "$SUNSHINE_INSTALLED" -eq 1 ]; then
    if service_user_active "sunshine"; then
        if [ "$FORCE_RESTART" -eq 1 ]; then
            run "systemctl --user restart sunshine" && ok "Sunshine restarted" || fail "Sunshine restart"
        else
            skip "Sunshine service" "running"
        fi
    else
        run "systemctl --user enable sunshine 2>/dev/null" || true
        run "systemctl --user start sunshine 2>/dev/null" && ok "Sunshine started" || warn "Sunshine will start at login"
    fi
fi

# ─── 2e. VNC (fallback) ────────────────────────────────────────────
log "Checking VNC..."
if package_installed "tigervnc-server" 2>/dev/null; then
    skip "tigervnc-server" "installed"
else
    log "  Installing tigervnc-server..."
    run "$SUDO dnf install -y -q tigervnc-server 2>&1 | tail -3" || fail "tigervnc-server install"
fi

# Assign user to display :1 (idempotent)
VNC_USERS="/etc/tigervnc/vncserver.users"
if [ "$DRY_RUN" -eq 0 ]; then
    if ! grep -q ":1=$USER_NAME" "$VNC_USERS" 2>/dev/null; then
        echo ":1=$USER_NAME" | $SUDO tee -a "$VNC_USERS" > /dev/null
        log "  VNC: assigned :1 to $USER_NAME"
    fi
fi

# Set default session
mkdir -p "$USER_HOME/.config/tigervnc"
if [ ! -f "$USER_HOME/.config/tigervnc/config" ]; then
    echo "session=gnome" > "$USER_HOME/.config/tigervnc/config"
    log "  VNC: set session to gnome"
fi

if service_active "vncserver@:1"; then
    skip "VNC :1" "running"
else
    run "$SUDO systemctl enable vncserver@:1 2>/dev/null" || true
    if [ -f "$USER_HOME/.vnc/passwd" ]; then
        run "$SUDO systemctl start vncserver@:1 2>/dev/null" && ok "VNC started on :5901" || warn "VNC start failed (set password with: vncpasswd)"
    else
        warn "  VNC: needs password — run: vncpasswd"
    fi
fi

# ─── 2f. RustDesk (bonus) ──────────────────────────────────────────
log "Checking RustDesk..."
if command_exists "rustdesk"; then
    skip "RustDesk" "installed"
else
    log "  Downloading RustDesk..."
    ARCH_RPM="x86_64"
    [ "$(uname -m)" = "aarch64" ] && ARCH_RPM="aarch64"

    RDESK_URL=""
    # Try to find latest RustDesk release
    case "$ARCH_RPM" in
        x86_64) RDESK_URL="https://github.com/rustdesk/rustdesk/releases/download/1.3.9/rustdesk-1.3.9-0.x86_64.rpm" ;;
        aarch64) RDESK_URL="https://github.com/rustdesk/rustdesk/releases/download/1.3.9/rustdesk-1.3.9-0.aarch64.rpm" ;;
    esac

    if [ -n "$RDESK_URL" ]; then
        if run "wget -q '$RDESK_URL' -O /tmp/rustdesk.rpm 2>/dev/null"; then
            run "$SUDO dnf install -y -q /tmp/rustdesk.rpm 2>&1 | tail -3" && ok "RustDesk installed" || warn "RustDesk install failed"
            rm -f /tmp/rustdesk.rpm
        else
            warn "  RustDesk download failed"
        fi
    fi
fi

log "Remote desktop services checked."
else
    step 2 "Remote desktop services — SKIPPED"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Firewall — open all FoveAI ports
# ═══════════════════════════════════════════════════════════════════
step 3 "Firewall configuration"

if command_exists "firewall-cmd"; then
    TCP_PORTS="22 3389 47989 47990 48010 5177 5901 8400 8408 8402 8403 8414 8888"
    UDP_PORTS="47998 47999 48000 48010"

    OPENED_TCP=0
    OPENED_UDP=0

    for port in $TCP_PORTS; do
        if $SUDO firewall-cmd --list-ports 2>/dev/null | grep -q "$port/tcp"; then
            : # already open
        else
            run "$SUDO firewall-cmd --add-port=$port/tcp --permanent 2>/dev/null" && OPENED_TCP=$((OPENED_TCP+1)) || true
        fi
    done

    for port in $UDP_PORTS; do
        if $SUDO firewall-cmd --list-ports 2>/dev/null | grep -q "$port/udp"; then
            : # already open
        else
            run "$SUDO firewall-cmd --add-port=$port/udp --permanent 2>/dev/null" && OPENED_UDP=$((OPENED_UDP+1)) || true
        fi
    done

    if [ "$OPENED_TCP" -gt 0 ] || [ "$OPENED_UDP" -gt 0 ]; then
        run "$SUDO firewall-cmd --reload 2>/dev/null" && ok "Firewall: opened $OPENED_TCP TCP + $OPENED_UDP UDP ports" || warn "Firewall reload failed"
    else
        skip "Firewall ports" "open"
    fi
else
    warn "firewall-cmd not found — skipping firewall config"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 4: FoveAI backend stack
# ═══════════════════════════════════════════════════════════════════
if [ "$SKIP_STACK" -eq 0 ]; then
step 4 "FoveAI backend stack"

cd "$FOVEAI_DIR"

# ─── 4a. .env ─────────────────────────────────────────────────────
if file_exists "$FOVEAI_DIR/.env"; then
    skip ".env" "exists"
else
    if file_exists "$FOVEAI_DIR/.env.example"; then
        run "cp $FOVEAI_DIR/.env.example $FOVEAI_DIR/.env" && ok ".env created from .env.example"
    else
        warn "  No .env or .env.example — creating minimal .env"
        cat > "$FOVEAI_DIR/.env" <<EOF
FoveAI_WEBUI_PASSWORD=foveai
FoveAI_WEBUI_ALLOW_INSECURE=0
XRLF_REPO_ENABLED=true
XRLF_WORKSPACE_ROOT=$FOVEAI_DIR
EOF
        ok ".env created (minimal)"
    fi
fi

# ─── 4b. Python venv ───────────────────────────────────────────────
log "Checking Python virtual environment..."
if file_exists "$FOVEAI_DIR/.venv/bin/python"; then
    skip "Python venv" "exists"
else
    log "  Creating Python venv with uv..."
    if command_exists "uv"; then
        run "uv venv $FOVEAI_DIR/.venv --python 3.12 2>&1 | tail -3" && ok "venv created (Python 3.12)" || fail "venv creation"
    else
        run "python3 -m venv $FOVEAI_DIR/.venv 2>&1" && ok "venv created (system python)" || fail "venv creation"
    fi
fi

# ─── 4c. Python dependencies ───────────────────────────────────────
log "Checking Python dependencies..."
if file_exists "$FOVEAI_DIR/requirements.txt"; then
    log "  Installing/updating Python dependencies..."
    if command_exists "uv"; then
        run "cd $FOVEAI_DIR && uv pip install -r requirements.txt 2>&1 | tail -5" || warn "Some requirements may have failed"
    elif file_exists "$FOVEAI_DIR/.venv/bin/pip"; then
        run "$FOVEAI_DIR/.venv/bin/pip install -r requirements.txt 2>&1 | tail -5" || warn "Some requirements may have failed"
    else
        run "pip3 install -r requirements.txt 2>&1 | tail -5" || warn "Some requirements may have failed"
    fi

    if file_exists "$FOVEAI_DIR/requirements-dev.txt"; then
        if command_exists "uv"; then
            run "cd $FOVEAI_DIR && uv pip install -r requirements-dev.txt 2>&1 | tail -3" || true
        elif file_exists "$FOVEAI_DIR/.venv/bin/pip"; then
            run "$FOVEAI_DIR/.venv/bin/pip install -r requirements-dev.txt 2>&1 | tail -3" || true
        fi
    fi
    ok "Python dependencies checked"
else
    warn "  requirements.txt not found"
fi

# ─── 4d. Foveated Memory Proxy (Node.js) ───────────────────────────
log "Checking Foveated Memory Proxy..."
FOVEATED_DIR="$FOVEAI_DIR/foveated-memory"
if dir_exists "$FOVEATED_DIR"; then
    if dir_exists "$FOVEATED_DIR/node_modules"; then
        skip "Foveated Memory deps" "installed"
    else
        log "  Installing Foveated Memory dependencies..."
        run "cd $FOVEATED_DIR && npm install 2>&1 | tail -5" && ok "Foveated Memory deps installed" || fail "Foveated Memory npm install"
    fi
else
    warn "  Foveated Memory directory not found"
fi

# ─── 4e. Verify model exists ───────────────────────────────────────
log "Checking local model..."
MODEL_PATH="$FOVEAI_DIR/xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf"
if file_exists "$MODEL_PATH"; then
    ok "Model found: $(ls -lh "$MODEL_PATH" 2>/dev/null | awk '{print $5}')"
else
    warn "  Model not found at $MODEL_PATH"
    warn "  XRLF runtime will not start without it"
fi

# ─── 4f. Verify key scripts ────────────────────────────────────────
for script in run_xrlf.py apk_server.py ignition_server.py sleipnir_launcher.sh foveai.sh; do
    if file_exists "$FOVEAI_DIR/$script"; then
        skip "$script" "found"
    else
        warn "  $script not found"
    fi
done

# ─── 4g. Verify APK ────────────────────────────────────────────────
log "Checking Quest APK..."
APK_PATH="$FOVEAI_DIR/client_quest/AliceVR.apk"
if file_exists "$APK_PATH"; then
    ok "APK found: $(ls -lh "$APK_PATH" 2>/dev/null | awk '{print $5}')"
else
    warn "  APK not found — build with Unity or download"
fi

# ─── 4h. Check running services ────────────────────────────────────
log "Checking running backend services..."

check_port() {
    local port=$1 name=$2
    if port_open "$port"; then
        skip "$name" "running on :$port"
    else
        warn "  $name not running on :$port (start with: foveai)"
    fi
}

check_port 8400 "Foveated Memory Proxy"
check_port 8414 "Memory Dashboard"
check_port 8402 "XRLF Runtime"
check_port 8403 "WebSocket IPC"
check_port 8416 "Ignition Server"
check_port 8888 "APK Server"

log "Backend stack checked."
else
    step 4 "FoveAI backend stack — SKIPPED"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 5: Multigate frontend
# ═══════════════════════════════════════════════════════════════════
if [ "$SKIP_FRONTEND" -eq 0 ]; then
step 5 "Multigate frontend"

MULTIGATE_DIR="$FOVEAI_DIR/Frontend/multigate"
if dir_exists "$MULTIGATE_DIR"; then
    if dir_exists "$MULTIGATE_DIR/node_modules"; then
        skip "Multigate deps" "installed"
    else
        log "  Installing Multigate dependencies..."
        run "cd $MULTIGATE_DIR && npm install 2>&1 | tail -5" && ok "Multigate deps installed" || fail "Multigate npm install"
    fi

    if port_open "5177"; then
        skip "Multigate" "running on :5177"
    else
        warn "  Multigate not running on :5177 (start with: foveai or foveai-autostart.sh)"
    fi
else
    warn "  Multigate directory not found at $MULTIGATE_DIR"
fi

log "Frontend checked."
else
    step 5 "Multigate frontend — SKIPPED"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 6: Cloudflare Tunnel (xarel.net)
# ═══════════════════════════════════════════════════════════════════
if [ "$SKIP_TUNNEL" -eq 0 ]; then
step 6 "Cloudflare Tunnel (xarel.net)"

# ─── 6a. Install cloudflared ───────────────────────────────────────
log "Checking cloudflared..."
CFLARED_BIN="$USER_HOME/.local/bin/cloudflared"

if command_exists "cloudflared" || file_exists "$CFLARED_BIN"; then
    skip "cloudflared" "installed"
else
    log "  Installing cloudflared..."
    ARCH="linux-amd64"
    [ "$(uname -m)" = "aarch64" ] && ARCH="linux-arm64"
    mkdir -p "$USER_HOME/.local/bin"
    if run "wget -q 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-${ARCH}' -O $CFLARED_BIN"; then
        chmod +x "$CFLARED_BIN"
        ok "cloudflared installed to $CFLARED_BIN"
    else
        fail "cloudflared download"
    fi
fi

# ─── 6b. Tunnel config (idempotent — don't overwrite if exists) ────
log "Checking tunnel config..."
mkdir -p "$USER_HOME/.cloudflared"

if file_exists "$USER_HOME/.cloudflared/config.yml"; then
    skip "Tunnel config" "exists"
else
    log "  Creating tunnel config..."
    cat > "$USER_HOME/.cloudflared/config.yml" <<'EOF'
# Cloudflare Tunnel config for xarel.net
# Routes all xarel.net traffic to local FoveAI services
# Multigate (:5177) is the single frontend — serves XR features when XR client detected

tunnel: foveai
credentials-file: CREDENTIALS_PATH_PLACEHOLDER

ingress:
  # FoveAI backend API (XRLF Runtime)
  - hostname: xarel.net
    path: /api/*
    service: http://localhost:8402

  # WebSocket IPC (avatar/events)
  - hostname: xarel.net
    path: /ws/*
    service: ws://localhost:8403

  # Memory Dashboard
  - hostname: xarel.net
    path: /dashboard/*
    service: http://localhost:8414

  # Foveated Memory Proxy
  - hostname: xarel.net
    path: /memory/*
    service: http://localhost:8400

  # Ignition control
  - hostname: xarel.net
    path: /ignition/*
    service: http://localhost:8401

  # APK download
  - hostname: xarel.net
    path: /apk/*
    service: http://localhost:8888

  # Default → Multigate (serves XR features when XR client detected)
  - hostname: xarel.net
    service: http://localhost:5177

  # Catch-all
  - service: http_status:404
EOF
    ok "Tunnel config created"
fi

# ─── 6c. System service (idempotent) ───────────────────────────────
log "Checking tunnel service..."
TUNNEL_SERVICE="/etc/systemd/system/cloudflared-tunnel.service"
TUNNEL_CONTENT="[Unit]
Description=Cloudflare Tunnel (xarel.net → FoveAI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
ExecStart=$CFLARED_BIN tunnel run --config $USER_HOME/.cloudflared/config.yml foveai
Restart=always
RestartSec=10
Environment=HOME=$USER_HOME

[Install]
WantedBy=multi-user.target"

if [ "$DRY_RUN" -eq 0 ]; then
    NEEDS_WRITE=1
    if file_exists "$TUNNEL_SERVICE"; then
        EXISTING=$(cat "$TUNNEL_SERVICE" 2>/dev/null)
        if [ "$EXISTING" = "$TUNNEL_CONTENT" ]; then
            NEEDS_WRITE=0
        fi
    fi
    if [ "$NEEDS_WRITE" -eq 1 ]; then
        echo "$TUNNEL_CONTENT" | $SUDO tee "$TUNNEL_SERVICE" > /dev/null
        $SUDO systemctl daemon-reload
        log "  Tunnel service file written"
    fi
fi

if service_enabled "cloudflared-tunnel" 2>/dev/null; then
    skip "Tunnel service" "enabled"
else
    run "$SUDO systemctl enable cloudflared-tunnel 2>/dev/null" && ok "Tunnel service enabled" || true
fi

# Check if tunnel is running
if process_running "cloudflared"; then
    skip "Tunnel daemon" "running"
elif file_exists "$USER_HOME/.cloudflared/credentials.json"; then
    run "$SUDO systemctl start cloudflared-tunnel 2>/dev/null" && ok "Tunnel started" || warn "Tunnel start failed"
else
    warn "  Tunnel not configured — run: cloudflared tunnel login && cloudflared tunnel create foveai"
fi

log "Cloudflare Tunnel checked."
else
    step 6 "Cloudflare Tunnel — SKIPPED"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 7: Autostart configuration
# ═══════════════════════════════════════════════════════════════════
if [ "$SKIP_AUTOSTART" -eq 0 ]; then
step 7 "Autostart configuration"

# ─── 7a. Autostart script (idempotent) ────────────────────────────
log "Checking autostart script..."
AUTOSTART="$FOVEAI_DIR/foveai-autostart.sh"

if file_exists "$AUTOSTART"; then
    skip "Autostart script" "exists"
else
    log "  Creating autostart script..."
    cat > "$AUTOSTART" <<'AUTOSTART_EOF'
#!/usr/bin/env bash
set -uo pipefail
LOG="$HOME/FoveAI/logs/autostart.log"
mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG" 2>&1; }

log "=== FoveAI autostart beginning ==="

# System services (graceful — don't fail if already running or sudo unavailable)
for svc in sshd xrdp; do
    if ! systemctl is-active --quiet "$svc" 2>/dev/null; then
        sudo systemctl start "$svc" 2>/dev/null && log "$svc started" || log "$svc start failed (needs sudo)"
    else
        log "$svc already running"
    fi
done

# Sunshine (user service — no sudo needed)
if ! systemctl --user is-active --quiet sunshine 2>/dev/null; then
    systemctl --user start sunshine 2>/dev/null && log "Sunshine started" || log "Sunshine start failed"
else
    log "Sunshine already running"
fi

# Chrome Remote Desktop (graceful — check binary, config, and process)
CRD_BIN="/opt/google/chrome-remote-desktop/chrome-remote-desktop-host"
CRD_CONFIG="$HOME/.config/chrome-remote-desktop"
if [ -x "$CRD_BIN" ] && ! pgrep -f "chrome-remote-desktop-host" &>/dev/null; then
    mkdir -p "$CRD_CONFIG"
    if [ ! -f "$CRD_CONFIG/host.json" ]; then
        EXISTING=$(ls "$CRD_CONFIG"/host#*.json 2>/dev/null | head -1)
        [ -n "$EXISTING" ] && cp "$EXISTING" "$CRD_CONFIG/host.json" 2>/dev/null
    fi
    if [ -f "$CRD_CONFIG/host.json" ]; then
        DISPLAY=:0 nohup "$CRD_BIN" --console >> "$LOG" 2>&1 &
        log "CRD started (PID $!)"
    else
        log "CRD not configured — skipping"
    fi
else
    log "CRD already running or not installed"
fi

# FoveAI stack (graceful — check if already running)
FOVEAI="$HOME/FoveAI"
if [ -d "$FOVEAI" ]; then
    cd "$FOVEAI"
    [ -f "$FOVEAI/.env" ] && { set -a; source "$FOVEAI/.env" 2>/dev/null; set +a; }

    if ! pgrep -f "foveated-memory" &>/dev/null && [ -x "$FOVEAI/foveai.sh" ]; then
        nohup "$FOVEAI/foveai.sh" --light >> "$LOG" 2>&1 &
        log "Sleipnir started (PID $!)"
        sleep 5
    else
        log "Sleipnir already running or not executable"
    fi

    # Multigate frontend (check port before starting)
    if ! ss -tlnp 2>/dev/null | grep -q ':5177 '; then
        MG_DIR="$FOVEAI/Frontend/multigate"
        if [ -d "$MG_DIR/node_modules" ]; then
            cd "$MG_DIR"
            nohup npx vite --host 0.0.0.0 --port 5177 >> "$LOG" 2>&1 &
            log "Multigate started on 0.0.0.0:5177 (PID $!)"
        else
            log "Multigate: node_modules not found — run install-nobara.sh"
        fi
    else
        log "Multigate already running on :5177"
    fi

    # APK server (check port before starting)
    if ! ss -tlnp 2>/dev/null | grep -q ':8888 '; then
        if [ -f "$FOVEAI/apk_server.py" ]; then
            cd "$FOVEAI"
            nohup python3 apk_server.py >> "$LOG" 2>&1 &
            log "APK server started on :8888 (PID $!)"
        fi
    else
        log "APK server already running on :8888"
    fi
fi

# Cloudflare Tunnel (graceful — check binary, creds, and process)
CFLARED="$HOME/.local/bin/cloudflared"
if [ -x "$CFLARED" ] && [ -f "$HOME/.cloudflared/credentials.json" ] && ! pgrep -f "cloudflared" &>/dev/null; then
    nohup "$CFLARED" tunnel run --config "$HOME/.cloudflared/config.yml" foveai >> "$LOG" 2>&1 &
    log "Cloudflare tunnel started (PID $!)"
else
    log "Cloudflare tunnel already running or not configured"
fi

log "=== Autostart complete ==="
AUTOSTART_EOF
    chmod +x "$AUTOSTART"
    ok "Autostart script created"
fi

# ─── 7b. Desktop autostart entries (idempotent) ───────────────────
log "Checking desktop autostart entries..."
mkdir -p "$USER_HOME/.config/autostart"

create_desktop_entry() {
    local file="$1" name="$2" comment="$3" exec_cmd="$4"
    local content="[Desktop Entry]
Type=Application
Name=$name
Comment=$comment
Exec=$exec_cmd
Icon=utilities-terminal
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false"

    if file_exists "$file"; then
        skip "$name desktop entry" "exists"
    else
        echo "$content" > "$file"
        ok "$name desktop entry created"
    fi
}

create_desktop_entry \
    "$USER_HOME/.config/autostart/foveai-sleipnir.desktop" \
    "FoveAI Autostart" \
    "Start all FoveAI services + remote access + xarel.net tunnel" \
    "$FOVEAI_DIR/foveai-autostart.sh"

create_desktop_entry \
    "$USER_HOME/.config/autostart/chrome-remote-desktop.desktop" \
    "Chrome Remote Desktop" \
    "Chrome Remote Desktop host daemon" \
    "/opt/google/chrome-remote-desktop/chrome-remote-desktop-host --console"

# ─── 7c. Global foveai command (idempotent) ───────────────────────
log "Checking global 'foveai' command..."
if [ -L "/usr/local/bin/foveai" ] || file_exists "/usr/local/bin/foveai"; then
    skip "'foveai' command" "linked"
else
    run "$SUDO ln -sf $FOVEAI_DIR/foveai.sh /usr/local/bin/foveai" && ok "'foveai' command linked system-wide" || warn "Could not create global command"
fi

log "Autostart configured."
else
    step 7 "Autostart — SKIPPED"
fi

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Installation Summary                                        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}Installed:${NC}  $INSTALLED"
echo -e "  ${BLUE}Skipped:${NC}   $SKIPPED (already present/running)"
echo -e "  ${YELLOW}Warnings:${NC}  $WARNINGS"
echo -e "  ${RED}Failed:${NC}    $FAILED"
echo ""
echo "  Remote Desktop Services:"
echo "    1. SSHD              $(service_active sshd 2>/dev/null && echo -e "${GREEN}active${NC} on :22" || echo -e "${RED}inactive${NC}")"
echo "    2. xRDP             $(service_active xrdp 2>/dev/null && echo -e "${GREEN}active${NC} on :3389" || echo -e "${RED}inactive${NC}")"
echo "    3. Chrome Remote     $(process_running "chrome-remote-desktop-host" && echo -e "${GREEN}running${NC}" || echo -e "${YELLOW}not running${NC}")"
echo "    4. Sunshine          $(service_user_active sunshine 2>/dev/null && echo -e "${GREEN}active${NC}" || echo -e "${YELLOW}inactive${NC}")"
echo "    5. VNC               $(service_active vncserver@:1 2>/dev/null && echo -e "${GREEN}active${NC} on :5901" || echo -e "${YELLOW}inactive${NC}")"
echo "    6. RustDesk          $(command_exists rustdesk && echo -e "${GREEN}installed${NC}" || echo -e "${YELLOW}not installed${NC}")"
echo ""
echo "  FoveAI Stack:"
echo "    Foveated Memory  :8400  $(port_open 8400 && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo "    XRLF Runtime     :8402  $(port_open 8402 && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo "    WebSocket IPC    :8403  $(port_open 8403 && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo "    Dashboard        :8414  $(port_open 8414 && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo "    Ignition         :8416  $(port_open 8416 && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo "    Multigate        :5177  $(port_open 5177 && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo "    APK Server       :8888  $(port_open 8888 && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo "    Cloudflare       xarel  $(process_running cloudflared && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}")"
echo ""
echo "  Access:"
echo "    LAN:    http://192.168.8.100:5177"
echo "    Web:    https://xarel.net (after Cloudflare Tunnel setup)"
echo "    RDP:    192.168.8.100:3389"
echo "    SSH:    ssh $USER_NAME@192.168.8.100"
echo ""

if [ "$FAILED" -gt 0 ]; then
    echo -e "  ${RED}Some steps failed — check the log: $LOG_FILE${NC}"
fi

# Only show manual steps if things aren't configured yet
NEEDS_MANUAL=0

if ! file_exists "$USER_HOME/.vnc/passwd" 2>/dev/null; then
    [ "$NEEDS_MANUAL" -eq 0 ] && echo -e "  ${YELLOW}Manual steps needed:${NC}"
    echo "    1. VNC password:        vncpasswd"
    NEEDS_MANUAL=1
fi

if ! file_exists "$USER_HOME/.config/chrome-remote-desktop/host.json" 2>/dev/null; then
    [ "$NEEDS_MANUAL" -eq 0 ] && echo -e "  ${YELLOW}Manual steps needed:${NC}"
    echo "    2. CRD configure:       /opt/google/chrome-remote-desktop/start-host \\"
    echo "                              --code=\"<oauth_code>\" \\"
    echo "                              --redirect-url=\"https://remotedesktop.google.com/_/oauthredirect\" \\"
    echo "                              --name=\$(hostname)"
    NEEDS_MANUAL=1
fi

if ! file_exists "$USER_HOME/.cloudflared/credentials.json" 2>/dev/null; then
    [ "$NEEDS_MANUAL" -eq 0 ] && echo -e "  ${YELLOW}Manual steps needed:${NC}"
    echo "    3. Cloudflare Tunnel:"
    echo "       cloudflared tunnel login"
    echo "       cloudflared tunnel create foveai"
    echo "       cloudflared tunnel route dns foveai xarel.net"
    echo "       cp ~/.cloudflared/*.json ~/.cloudflared/credentials.json"
    echo "       sudo systemctl enable --now cloudflared-tunnel"
    NEEDS_MANUAL=1
fi

if [ "$NEEDS_MANUAL" -eq 0 ]; then
    echo -e "  ${GREEN}Everything configured!${NC} Start with: foveai"
else
    echo ""
    echo "    After manual steps:    foveai  (or reboot for autostart)"
fi

echo ""
echo "  Log: $LOG_FILE"
echo ""
