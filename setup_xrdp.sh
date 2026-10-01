#!/usr/bin/env bash
# ==============================================================================
# setup_xrdp.sh — Setup XRDP for Linux Mint 22.3 (Cinnamon) + Configure UFW
# ==============================================================================
set -euo pipefail

# Ensure the script is run with root privileges
if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Please run this script with sudo:"
    echo "        sudo ./setup_xrdp.sh"
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

wait_for_apt_lock() {
    local max_wait=120
    local waited=0
    while fuser /var/lib/dpkg/lock >/dev/null 2>&1 || \
          fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
          fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
        if [ "$waited" -ge "$max_wait" ]; then
            echo "[ERROR] Timed out waiting for package manager locks to clear."
            exit 1
        fi
        echo "Waiting for background package update (mint-refresh-cache/apt) to finish... (${waited}s)"
        sleep 3
        waited=$((waited + 3))
    done
}

echo "==> [1/6] Installing XRDP and Xorg backends via apt..."
wait_for_apt_lock
apt-get update -qq
wait_for_apt_lock
apt-get install -y -q xrdp xorgxrdp

echo "==> [2/6] Granting xrdp user access to SSL certificates..."
adduser xrdp ssl-cert

echo "==> [3/6] Setting up Polkit rules to eliminate authentication popups..."
mkdir -p /etc/polkit-1/rules.d
cat << 'EOF' > /etc/polkit-1/rules.d/45-allow-colord.rules
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.color-manager.create-device" ||
         action.id == "org.freedesktop.color-manager.create-profile" ||
         action.id == "org.freedesktop.color-manager.delete-device" ||
         action.id == "org.freedesktop.color-manager.delete-profile" ||
         action.id == "org.freedesktop.color-manager.modify-device" ||
         action.id == "org.freedesktop.color-manager.modify-profile") &&
        subject.isInGroup("sudo")) {
        return polkit.Result.YES;
    }
});
EOF

echo "==> [4/6] Configuring Cinnamon desktop session for remote desktop..."
TARGET_USER="${SUDO_USER:-lumba}"
USER_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)

if [ -d "$USER_HOME" ]; then
    # Software-rendered Cinnamon (cinnamon-session-cinnamon2d) is reliable over RDP
    echo "cinnamon-session-cinnamon2d" > "$USER_HOME/.xsession"
    chown "$TARGET_USER:$TARGET_USER" "$USER_HOME/.xsession"
    chmod 644 "$USER_HOME/.xsession"
    echo "Configured $USER_HOME/.xsession -> cinnamon-session-cinnamon2d"
fi

echo "==> [5/6] Opening RDP port (3389/tcp) in UFW firewall..."
if command -v ufw >/dev/null 2>&1; then
    ufw allow 3389/tcp comment "XRDP Remote Desktop"
    ufw reload
    echo "UFW firewall rule enabled for 3389/tcp."
else
    echo "[WARN] UFW not found, skipping firewall rule."
fi

echo "==> [6/6] Enabling and starting XRDP service..."
systemctl daemon-reload
systemctl enable xrdp
systemctl restart xrdp

echo ""
echo "==> Verification:"
systemctl is-active --quiet xrdp && echo "  [✓] XRDP service is ACTIVE" || echo "  [✗] XRDP service failed to start"

if ss -tulpn | grep -q ":3389"; then
    echo "  [✓] Port 3389/tcp is LISTENING"
else
    echo "  [!] Port 3389 not yet listening"
fi

if ufw status verbose | grep -q "3389/tcp"; then
    echo "  [✓] UFW port 3389/tcp ALLOWED"
fi

IP_ADDR=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1 || echo "127.0.0.1")
echo ""
echo "=============================================================================="
echo "XRDP is ready for incoming connections!"
echo "Target Host IP: $IP_ADDR:3389"
echo "Username:       $TARGET_USER"
echo "Password:       (your Linux login password)"
echo ""
echo "IMPORTANT USAGE NOTE:"
echo "In Linux X11/Cinnamon, the same user cannot be logged in simultaneously"
echo "on the local physical screen (:0) and through XRDP. Before connecting from"
echo "your RDP client, please lock or log out of the physical desktop session."
echo "=============================================================================="
