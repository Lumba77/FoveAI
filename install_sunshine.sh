#!/bin/bash
set -e

echo "=== 1. Downloading official Sunshine deb for Ubuntu 24.04 ==="
DEB_URL="https://github.com/LizardByte/Sunshine/releases/download/v2026.914.233613/sunshine_2026.914.233613-1%2Bubuntu24.04_amd64.deb"
TMP_DEB="/tmp/sunshine_ubuntu24.04.deb"

curl -L -o "$TMP_DEB" "$DEB_URL"

echo "=== 2. Installing Sunshine package and dependencies ==="
apt-get update -y
apt-get install -y "$TMP_DEB"

echo "=== 3. Configuring udev rules for virtual input (/dev/uinput) ==="
cat << 'EOF' > /etc/udev/rules.d/85-sunshine-input.rules
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
udevadm control --reload-rules
udevadm trigger

echo "=== 4. Adding user lumba to input group ==="
usermod -aG input lumba

echo "=== 5. Setting capture capabilities on Sunshine binary ==="
SUNSHINE_BIN=$(which sunshine || echo "/usr/bin/sunshine")
setcap cap_sys_admin+p "$SUNSHINE_BIN" || true

echo "=== 6. Opening Sunshine firewall ports in UFW ==="
# TCP: HTTPS web API (47984), HTTP web API (47989), Web UI (47990), RTSP (48010)
ufw allow 47984/tcp comment 'Sunshine HTTPS API'
ufw allow 47989/tcp comment 'Sunshine HTTP API'
ufw allow 47990/tcp comment 'Sunshine Web UI'
ufw allow 48010/tcp comment 'Sunshine RTSP'

# UDP: Audio (47998), Video (47999), Control (48000), RTSP Stream (48002), Control (48010)
ufw allow 47998/udp comment 'Sunshine Audio'
ufw allow 47999/udp comment 'Sunshine Video'
ufw allow 48000/udp comment 'Sunshine Control'
ufw allow 48002/udp comment 'Sunshine Stream'
ufw allow 48010/udp comment 'Sunshine Control'
ufw reload

echo "=== Sunshine Installation & System Setup Complete ==="
sunshine --version
