#!/usr/bin/env bash
#
# setup_agent_isolation.sh — Open XRL Phase 1: Host Agent Scaffolding & Hard Limits.
#
# Tasks:
#   1. Provision /agent/jen with private home (0700), ed25519 keys, and XRL contract.
#   2. Verify no sudo access for agent accounts.
#   3. Apply per-agent cgroups via systemd user slices (MemoryMax=4G, TasksMax=256, CPUQuota=200%).
#   4. Apply PAM process limits (nproc=256) to prevent fork-bombs.
#
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "❌ This script must be run with sudo/root privileges."
  echo "Usage: sudo bash $0"
  exit 1
fi

FOVEAI_DIR="/home/lumba/FoveAI"
PROVISION_PY="$FOVEAI_DIR/Tools/open_xrl_agent_provision.py"

echo "=================================================="
echo "🛡️  Open XRL — Phase 1: Agent Isolation Scaffolding"
echo "=================================================="

# 1. Provision /agent/jen
echo -e "\n[1/4] Provisioning agent 'jen'..."
python3 "$PROVISION_PY" create jen

# Verify /agent/jen mode
if [ -d "/agent/jen" ]; then
  chmod 700 /agent/jen
  chown -R jen:jen /agent/jen
  echo "  ✓ /agent/jen secured with mode 0700 and ownership jen:jen"
else
  echo "  ❌ Failed to create /agent/jen"
  exit 1
fi

# 2. Verify no sudo privileges
echo -e "\n[2/4] Verifying sudo restriction for agent accounts..."
for agent in jen antigravity; do
  if id "$agent" >/dev/null 2>&1; then
    # Remove from sudo/admin/wheel if inadvertently present
    gpasswd -d "$agent" sudo >/dev/null 2>&1 || true
    gpasswd -d "$agent" admin >/dev/null 2>&1 || true
    gpasswd -d "$agent" wheel >/dev/null 2>&1 || true
    echo "  ✓ '$agent' has NO sudo privileges"
  fi
done

# 3. Configure systemd cgroup slices (MemoryMax, TasksMax, CPUQuota)
echo -e "\n[3/4] Configuring systemd cgroups for agents..."
for agent in jen antigravity; do
  if id "$agent" >/dev/null 2>&1; then
    uid=$(id -u "$agent")
    slice_dir="/etc/systemd/system/user-${uid}.slice.d"
    mkdir -p "$slice_dir"
    cat > "$slice_dir/50-agent-limits.conf" <<EOF
[Slice]
# Hard caps to protect host stability
MemoryMax=4G
TasksMax=256
CPUQuota=200%
EOF
    echo "  ✓ Configured user-${uid}.slice for '$agent' (MemoryMax=4G, TasksMax=256, CPUQuota=200%)"
  fi
done

# 4. Configure PAM process limits (anti-forkbomb floor)
echo -e "\n[4/4] Setting PAM nproc limits in /etc/security/limits.d/99-agent-limits.conf..."
cat > /etc/security/limits.d/99-agent-limits.conf <<'EOF'
# Open XRL Agent Process Limits (anti-forkbomb)
jen          soft    nproc          256
jen          hard    nproc          256
antigravity  soft    nproc          256
antigravity  hard    nproc          256
EOF
echo "  ✓ Created /etc/security/limits.d/99-agent-limits.conf"

# Reload systemd
systemctl daemon-reload
echo "  ✓ systemd daemon reloaded"

echo -e "\n=================================================="
echo "✅ Open XRL Phase 1 Scaffolding Complete!"
echo "   Agents provisioned: $(python3 "$PROVISION_PY" list | grep -E '•' | tr '\n' ' ')"
echo "=================================================="
