#!/usr/bin/env bash
# ==============================================================================
# enable_session_adoption.sh — Configure XRDP to adopt active :0 desktop session
# ==============================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Please run with sudo or pkexec:"
    echo "        sudo ./enable_session_adoption.sh"
    exit 1
fi

XRDP_INI="/etc/xrdp/xrdp.ini"
BACKUP_INI="/etc/xrdp/xrdp.ini.bak.$(date +%s)"

echo "==> [1/4] Backing up $XRDP_INI -> $BACKUP_INI..."
cp "$XRDP_INI" "$BACKUP_INI"

echo "==> [2/4] Adding Adopt Active Desktop (:0) session to xrdp.ini..."
python3 - << 'PYEOF'
import sys

path = "/etc/xrdp/xrdp.ini"
with open(path, "r") as f:
    content = f.read()

section = """[Adopt-Active-Desktop]
name=Adopt Active Desktop (:0)
lib=libvnc.so
ip=127.0.0.1
port=5900
username=lumba
password=ask
pamsessionmng=127.0.0.1
pamusername=lumba
pampassword=asksame

"""

if "[Adopt-Active-Desktop]" not in content:
    # Insert right before [Xorg]
    target = "[Xorg]"
    if target in content:
        content = content.replace(target, section + target, 1)
    else:
        content += "\n" + section
    with open(path, "w") as f:
        f.write(content)
    print("Section [Adopt-Active-Desktop] inserted successfully.")
else:
    print("Section [Adopt-Active-Desktop] already present.")
PYEOF

echo "==> [3/4] Restarting XRDP service..."
systemctl restart xrdp

echo "==> [4/4] Verifying XRDP and x11vnc ports..."
systemctl is-active --quiet xrdp && echo "  [✓] XRDP service is ACTIVE"
ss -tulpn | grep -q ":3389" && echo "  [✓] XRDP listening on :3389"
ss -tulpn | grep -q ":5900" && echo "  [✓] x11vnc listening on 127.0.0.1:5900"

echo ""
echo "=============================================================================="
echo "Session Adoption is now configured!"
echo "When connecting from your RDP client:"
echo "1. Select session: 'Adopt Active Desktop (:0)'"
echo "2. Username is set to: lumba"
echo "3. Enter your Linux password"
echo "-> You will be seamlessly bridged into your live Cinnamon desktop on :0!"
echo "=============================================================================="
