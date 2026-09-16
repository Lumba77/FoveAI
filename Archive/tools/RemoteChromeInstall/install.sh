#!/usr/bin/env bash
#
# Chrome Remote Desktop Installer for any Linux distro
# Installs and configures Chrome Remote Desktop host as a system service.
#
# Usage:
#   ./install.sh                    # Interactive: prompts for OAuth code
#   ./install.sh --code="4/0AXx..." # Non-interactive with OAuth code
#   ./install.sh --help             # Show help
#
# After install, go to remotedesktop.google.com/access from any browser,
# sign in with the same Google account, and connect to this machine.
#
set -euo pipefail

# ─── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[CRD]${NC} $*"; }
warn() { echo -e "${YELLOW}[CRD]${NC} $*"; }
err()  { echo -e "${RED}[CRD]${NC} $*" >&2; }

# ─── Detect distro ─────────────────────────────────────────────────
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif [ -f /etc/redhat-release ]; then
        echo "rhel"
    elif [ -f /etc/debian_version ]; then
        echo "debian"
    else
        echo "unknown"
    fi
}

DISTRO=$(detect_distro)
ARCH=$(uname -m)

case "$ARCH" in
    x86_64|amd64) ARCH_DEB="amd64"; ARCH_RPM="x86_64" ;;
    aarch64|arm64) ARCH_DEB="arm64"; ARCH_RPM="aarch64" ;;
    *) err "Unsupported architecture: $ARCH"; exit 1 ;;
esac

log "Detected: $DISTRO on $ARCH"

# ─── Check root/sudo ────────────────────────────────────────────────
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO="sudo"
    else
        err "Need root or sudo access"
        exit 1
    fi
fi

# ─── Install dependencies ──────────────────────────────────────────
install_deps() {
    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)
            $SUDO apt-get update -qq
            $SUDO apt-get install -y -qq wget ar xdg-utils
            ;;
        fedora|rhel|centos|rocky|alma|nobara)
            $SUDO dnf install -y -q wget xdg-utils
            ;;
        arch|manjaro|endeavouros)
            $SUDO pacman -Sy --noconfirm wget xdg-utils
            ;;
        opensuse*|suse)
            $SUDO zypper -q install wget xdg-utils
            ;;
        *)
            warn "Unknown distro — trying to install wget manually"
            ;;
    esac
}

# ─── Download CRD ───────────────────────────────────────────────────
download_crd() {
    local tmpdir="/tmp/crd-install-$$"
    mkdir -p "$tmpdir"
    cd "$tmpdir"

    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)
            log "Downloading CRD .deb..."
            wget -q "https://dl.google.com/linux/direct/chrome-remote-desktop_current_${ARCH_DEB}.deb" -O crd.deb
            CRD_FILE="crd.deb"
            ;;
        fedora|rhel|centos|rocky|alma|nobara)
            log "Downloading CRD .deb (converting to rpm)..."
            wget -q "https://dl.google.com/linux/direct/chrome-remote-desktop_current_${ARCH_DEB}.deb" -O crd.deb
            CRD_FILE="crd.deb"
            ;;
        *)
            log "Downloading CRD .deb..."
            wget -q "https://dl.google.com/linux/direct/chrome-remote-desktop_current_${ARCH_DEB}.deb" -O crd.deb
            CRD_FILE="crd.deb"
            ;;
    esac

    if [ ! -f "$CRD_FILE" ]; then
        err "Download failed"
        exit 1
    fi

    log "Downloaded: $(ls -lh $CRD_FILE | awk '{print $5}')"
    echo "$tmpdir"
}

# ─── Install CRD ────────────────────────────────────────────────────
install_crd() {
    local tmpdir="$1"

    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)
            $SUDO apt-get install -y -q "$tmpdir/crd.deb"
            ;;
        fedora|rhel|centos|rocky|alma|nobara|arch|manjaro|opensuse*|suse|*)
            # Extract .deb and copy manually (avoids package conflicts)
            log "Extracting CRD..."
            mkdir -p "$tmpdir/extract"
            cd "$tmpdir/extract"

            if command -v dpkg-deb &>/dev/null; then
                dpkg-deb -x "$tmpdir/crd.deb" .
            elif command -v ar &>/dev/null; then
                ar x "$tmpdir/crd.deb"
                tar xf data.tar.* 2>/dev/null || tar xf data.tar.xz 2>/dev/null || tar xf data.tar.gz 2>/dev/null
            else
                # Install ar/dpkg tools
                case "$DISTRO" in
                    fedora|rhel|centos|rocky|alma|nobara)
                        $SUDO dnf install -y -q binutils dpkg
                        ;;
                    arch|manjaro)
                        $SUDO pacman -S --noconfirm dpkg binutils
                        ;;
                    opensuse*|suse)
                        $SUDO zypper -q install dpkg binutils
                        ;;
                esac
                dpkg-deb -x "$tmpdir/crd.deb" . 2>/dev/null || {
                    ar x "$tmpdir/crd.deb"
                    tar xf data.tar.* 2>/dev/null
                }
            fi

            # Copy files
            $SUDO mkdir -p /opt/google/chrome-remote-desktop
            $SUDO cp -r opt/google/chrome-remote-desktop/* /opt/google/chrome-remote-desktop/ 2>/dev/null || true

            # Copy binaries if present
            [ -d usr/bin ] && $SUDO cp -r usr/bin/* /usr/bin/ 2>/dev/null || true
            [ -d usr/share ] && $SUDO cp -r usr/share/* /usr/share/ 2>/dev/null || true

            # Verify
            if [ -f /opt/google/chrome-remote-desktop/start-host ]; then
                log "CRD installed to /opt/google/chrome-remote-desktop/"
            else
                err "Installation failed — start-host not found"
                exit 1
            fi
            ;;
    esac
}

# ─── Create system service ─────────────────────────────────────────
create_service() {
    local user="${SUDO_USER:-$(whoami)}"
    local display="${DISPLAY:-:0}"

    local service_file="/tmp/crd-host-$$.service"
    cat > "$service_file" <<EOF
[Unit]
Description=Chrome Remote Desktop Host
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$user
Environment=DISPLAY=$display
ExecStart=/opt/google/chrome-remote-desktop/chrome-remote-desktop-host --console
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    $SUDO cp "$service_file" /etc/systemd/system/crd-host.service
    $SUDO systemctl daemon-reload
    rm -f "$service_file"

    log "System service created: crd-host.service"
}

# ─── Configure host ────────────────────────────────────────────────
configure_host() {
    local code="$1"
    local user="${SUDO_USER:-$(whoami)}"
    local home_dir=$(eval echo "~$user")
    local config_dir="$home_dir/.config/chrome-remote-desktop"
    local display="${DISPLAY:-:0}"

    mkdir -p "$config_dir"

    # Check if already configured
    if [ -f "$config_dir/host.json" ] || ls "$config_dir"/host#*.json &>/dev/null; then
        log "Host already configured — using existing config"
        # Ensure host.json exists
        if [ ! -f "$config_dir/host.json" ]; then
            local existing=$(ls "$config_dir"/host#*.json 2>/dev/null | head -1)
            if [ -n "$existing" ]; then
                cp "$existing" "$config_dir/host.json"
                log "Copied existing config to host.json"
            fi
        fi
        return 0
    fi

    if [ -z "$code" ]; then
        echo
        warn "No OAuth code provided. To get one:"
        echo "  1. Open a browser on this machine"
        echo "  2. Go to https://remotedesktop.google.com"
        echo "  3. Click 'Set up remote access'"
        echo "  4. Copy the authorization code from the URL"
        echo
        read -p "Enter OAuth code (or press Enter to skip and configure later): " code
    fi

    if [ -n "$code" ]; then
        log "Configuring Chrome Remote Desktop host..."
        DISPLAY="$display" /opt/google/chrome-remote-desktop/start-host \
            --code="$code" \
            --redirect-url="https://remotedesktop.google.com/_/oauthredirect" \
            --name="$(hostname)" || {
            warn "Configuration may have failed. You can retry with a fresh code."
            warn "The host can be configured later by running start-host manually."
        }

        # Copy config to expected filename
        local existing=$(ls "$config_dir"/host#*.json 2>/dev/null | head -1)
        if [ -n "$existing" ] && [ ! -f "$config_dir/host.json" ]; then
            cp "$existing" "$config_dir/host.json"
            log "Config saved to host.json"
        fi
    else
        warn "Skipping configuration. Run this script again with --code=\"<your_code>\" to configure."
    fi
}

# ─── Start service ──────────────────────────────────────────────────
start_service() {
    $SUDO systemctl enable --now crd-host
    sleep 2

    if $SUDO systemctl is-active --quiet crd-host; then
        log "✅ Chrome Remote Desktop is running!"
    else
        err "Service failed to start. Check: sudo systemctl status crd-host"
        return 1
    fi
}

# ─── Show status ───────────────────────────────────────────────────
show_status() {
    local ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    local user="${SUDO_USER:-$(whoami)}"

    echo
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Chrome Remote Desktop — Installation Complete${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo
    echo "  Host name : $(hostname)"
    echo "  IP address: $ip"
    echo "  User      : $user"
    echo "  Service   : crd-host.service"
    echo
    echo "  To connect from any browser (including VR headsets):"
    echo "    1. Go to https://remotedesktop.google.com/access"
    echo "    2. Sign in with the same Google account"
    echo "    3. Click this machine ($(hostname))"
    echo "    4. Enter the PIN you set during configuration"
    echo
    echo "  Service commands:"
    echo "    sudo systemctl status crd-host    # Check status"
    echo "    sudo systemctl restart crd-host   # Restart"
    echo "    sudo systemctl stop crd-host      # Stop"
    echo
}

# ─── Help ──────────────────────────────────────────────────────────
show_help() {
    cat <<'EOF'
Chrome Remote Desktop Installer for Linux
==========================================
Installs Chrome Remote Desktop host as a system service on any Linux distro.

Usage:
  ./install.sh                    Interactive: prompts for OAuth code
  ./install.sh --code="4/0AXx..." Non-interactive with OAuth code
  ./install.sh --help             Show this help

How to get an OAuth code:
  1. Open a browser on this machine
  2. Go to https://remotedesktop.google.com
  3. Click "Set up remote access"
  4. Copy the authorization code from the URL

Supported distros:
  Debian, Ubuntu, Mint, Pop!_OS, Fedora, RHEL, CentOS, Rocky, Alma,
  Nobara, Arch, Manjaro, EndeavourOS, openSUSE, SUSE

After install:
  - Go to remotedesktop.google.com/access from any browser
  - Sign in with the same Google account
  - Click this machine and enter your PIN
EOF
}

# ─── Main ──────────────────────────────────────────────────────────
OAUTH_CODE=""

for arg in "$@"; do
    case "$arg" in
        --code=*) OAUTH_CODE="${arg#*=}" ;;
        --help|-h) show_help; exit 0 ;;
        *) warn "Unknown argument: $arg" ;;
    esac
done

log "Chrome Remote Desktop Installer"
log "Distro: $DISTRO | Arch: $ARCH"
echo

# Step 1: Install dependencies
log "Step 1/5: Installing dependencies..."
install_deps

# Step 2: Download
log "Step 2/5: Downloading Chrome Remote Desktop..."
TMPDIR=$(download_crd)

# Step 3: Install
log "Step 3/5: Installing..."
install_crd "$TMPDIR"

# Step 4: Configure
log "Step 4/5: Configuring host..."
configure_host "$OAUTH_CODE"

# Step 5: Create and start service
log "Step 5/5: Creating system service..."
create_service
start_service

# Cleanup
rm -rf "$TMPDIR"

# Status
show_status
