#!/usr/bin/env bash
# pc_speedup_root.sh — make the HDD-hosted home/agent dirs stop starving the machine.
#
# Context (measured 2026-10-16/17): after migrating accounts from the SSD (sdb2)
# to the 5400 rpm HDD (sda2), sda sits at ~100% util. Culprits:
#   1. foveai-jen-snapshot.service: `git add -A` over /agent/jen on the HDD, runs
#      for >1 h per pass and the OnCalendar timer re-triggers it back to back.
#   2. vm.swappiness=60 + 40 GB swapfile on the same HDD (11.9 GB in use).
#
# Modes:
#   (default) --diagnose   read-only report (root adds a size breakdown of /agent/jen)
#   --apply                gentler snapshot job + no overlap + leaner pathspec + sysctl
#   --flush-swap --yes     pull swapped pages back into RAM (only when it is safe)
#   --rollback <dir>       restore files from a backup dir printed by --apply
#
# Every change is backed up to /var/backups/foveai-speedup/<stamp>/ first.
set -uo pipefail

MODE="${1:---diagnose}"
SNAP_SH=/usr/local/lib/foveai/jen_snapshot.sh
UNIT=foveai-jen-snapshot
SYSCTL=/etc/sysctl.d/99-foveai-speed.conf
STAMP="$(date +%Y%m%d-%H%M%S)"
BK="/var/backups/foveai-speedup/$STAMP"

say()  { printf '\n== %s\n' "$*"; }
need_root() { [ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo bash $0 $MODE" >&2; exit 1; }; }

diagnose() {
  say "disks (ROTA 1 = spinning)"; lsblk -d -o NAME,ROTA,SIZE,MODEL
  say "root/home/agent filesystems"; df -h / /home/lumba /agent 2>/dev/null
  say "sda utilisation (3 s)"
  a=$(awk '$3=="sda"{print $13}' /proc/diskstats); sleep 3; b=$(awk '$3=="sda"{print $13}' /proc/diskstats)
  echo "sda util=$(( (b-a)/30 ))%"
  say "swap"; swapon --show; sysctl vm.swappiness vm.vfs_cache_pressure
  say "snapshot job"; systemctl show $UNIT.service -p ActiveState,ExecMainStartTimestamp --no-pager
  systemctl list-timers $UNIT.timer --no-pager 2>/dev/null | head -n 3
  say "processes stuck in D state"; ps -eo stat,etime,user,cmd | awk '$1 ~ /^D/' | cut -c1-120
  if [ "$(id -u)" -eq 0 ] && [ -d /agent/jen ]; then
    say "what /agent/jen contains (top, max 90 s)"
    timeout 90 du -xh --max-depth=2 /agent/jen 2>/dev/null | sort -rh | head -n 15
  else
    echo; echo "(run with sudo to also see the size breakdown of /agent/jen)"
  fi
}

apply() {
  need_root
  [ -f "$SNAP_SH" ] || { echo "missing $SNAP_SH" >&2; exit 1; }
  mkdir -p "$BK"
  cp -a "$SNAP_SH" "$BK/jen_snapshot.sh"
  cp -a /etc/systemd/system/$UNIT.service /etc/systemd/system/$UNIT.timer "$BK/"
  [ -f "$SYSCTL" ] && cp -a "$SYSCTL" "$BK/" || true
  echo "backup: $BK"

  say "1/4 snapshot job: lowest CPU/IO priority + hard time limit"
  mkdir -p /etc/systemd/system/$UNIT.service.d
  cat > /etc/systemd/system/$UNIT.service.d/10-gentle.conf <<'EOF'
[Service]
Nice=19
IOSchedulingClass=idle
CPUWeight=10
IOWeight=10
TimeoutStartSec=25min
EOF

  say "2/4 timer: never overlap, wait 30 min AFTER a pass finishes"
  mkdir -p /etc/systemd/system/$UNIT.timer.d
  cat > /etc/systemd/system/$UNIT.timer.d/10-no-overlap.conf <<'EOF'
[Timer]
OnCalendar=
Persistent=false
OnBootSec=10min
OnUnitInactiveSec=30min
EOF

  say "3/4 leaner pathspec (the bare repo inside the tree, venvs, node_modules, model blobs)"
  if grep -q ":!/.snapshots.git" "$SNAP_SH"; then
    echo "already patched"
  else
    sed -i "s#':!/\*.sock' ':!/.Xauthority'#':!/*.sock' ':!/.Xauthority' ':!/.snapshots.git' ':!.venv' ':!node_modules' ':!__pycache__' ':!*.gguf' ':!*.safetensors' ':!*.xrlf'#" "$SNAP_SH"
    if bash -n "$SNAP_SH" && grep -q ":!/.snapshots.git" "$SNAP_SH"; then echo "patched ok"
    else echo "PATCH FAILED — restoring"; cp -a "$BK/jen_snapshot.sh" "$SNAP_SH"; exit 1; fi
  fi

  say "4/4 kernel: stop preferring swap while RAM is free"
  cat > "$SYSCTL" <<'EOF'
vm.swappiness = 10
vm.vfs_cache_pressure = 50
EOF
  sysctl --system >/dev/null && sysctl vm.swappiness vm.vfs_cache_pressure

  say "reload + stop the stuck pass"
  systemctl daemon-reload
  timeout 90 systemctl stop $UNIT.service || echo "(stop timed out — it is waiting on the disk; it will end on its own)"
  systemctl restart $UNIT.timer
  systemctl list-timers $UNIT.timer --no-pager | head -n 3
  echo; echo "Done. Roll back with: sudo bash $0 --rollback $BK"
}

flush_swap() {
  need_root
  [ "${2:-}" = "--yes" ] || { echo "add --yes to confirm" >&2; exit 1; }
  if systemctl is-active --quiet $UNIT.service; then echo "snapshot job is running — wait or stop it first" >&2; exit 1; fi
  used_kb=$(awk '/SwapTotal/{t=$2}/SwapFree/{f=$2}END{print t-f}' /proc/meminfo)
  avail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
  echo "swap used: $((used_kb/1024)) MB, RAM available: $((avail_kb/1024)) MB"
  [ "$avail_kb" -gt $((used_kb + 2*1024*1024)) ] || { echo "not enough free RAM to swap back in safely" >&2; exit 1; }
  swapoff -a && swapon -a && swapon --show
}

rollback() {
  need_root
  dir="${2:-}"; [ -d "$dir" ] || { echo "usage: $0 --rollback <backup dir>" >&2; exit 1; }
  cp -a "$dir/jen_snapshot.sh" "$SNAP_SH"
  cp -a "$dir/$UNIT.service" "$dir/$UNIT.timer" /etc/systemd/system/
  rm -rf /etc/systemd/system/$UNIT.service.d /etc/systemd/system/$UNIT.timer.d
  [ -f "$dir/99-foveai-speed.conf" ] && cp -a "$dir/99-foveai-speed.conf" "$SYSCTL" || rm -f "$SYSCTL"
  systemctl daemon-reload; systemctl restart $UNIT.timer; sysctl --system >/dev/null
  echo "rolled back from $dir"
}

case "$MODE" in
  --diagnose)   diagnose ;;
  --apply)      apply ;;
  --flush-swap) flush_swap "$@" ;;
  --rollback)   rollback "$@" ;;
  *) echo "usage: $0 [--diagnose|--apply|--flush-swap --yes|--rollback <dir>]"; exit 1 ;;
esac
