#!/usr/bin/env bash
# .nest-panes.sh — content for the metric squares around the nest console.
#
# FORMAT: a header word, then one metric per line. No boxes, no rules, no
# frames — the bordered version was visually loud and made the squares
# compete with the console for attention.
#
#     NET                     <- header, dim cyan, caps
#     gateway   UP   0.30ms
#     ip        192.168.8.109
#     ttyd      :7681
#
# One accent colour only (cyan), used for the header. Everything else is
# plain text, so the console stays the brightest thing on screen.
#
# Every pane loops with pane_loop and reads single keys, so TAB-focusing a
# square is useful: the focused square prints its own keys.

FOVEAI_DIR="${FOVEAI_DIR:-/home/lumba/FoveAI}"
PROXY_URL="http://127.0.0.1:8400/api/status"
REFRESH="${NEST_REFRESH:-3}"

C=$'\033[0m'
H=$'\033[2;36m'      # dim cyan — header only
OK=$'\033[0;32m'
BAD=$'\033[0;31m'
WARN=$'\033[0;33m'

# ── primitives ──────────────────────────────────────────────────────
home() { printf '\033[H\033[2J'; }

# head <WORD>
hdr() { printf '%s%s%s\n' "$H" "$1" "$C"; }

# kv <label> <value>            plain label/value line (clipped)
# Values are clipped to pane width: a long model name or log line must
# push off the END of its line, never wrap and eat the next line / the
# header. W is set by the pane to its actual width.

# clip <text> — trim to pane width, ellipsis when cut. ${EPOCHREALTIME%.*}
# gives pane width via $COLUMNS; squares run 16-22 wide so ~13 chars of
# value fits beside the 11-char label gutter.
clip() {
  local max=$(( ${COLUMNS:-20} - 12 ))
  [ "$max" -lt 6 ] && max=6
  [ ${#1} -le $max ] && { printf '%s' "$1"; return; }
  printf '%s…' "${1:0:$(( max - 1 ))}"
}

kv() { printf "  %-9s %s\n" "$1" "$(clip "$2")"; }

# kvo <label> <value> <colour>   value gets an accent (for up/down)
kvo() { printf '  %-9s %s%s%s\n' "$1" "$3" "$(clip "$2")" "$C"; }

# kvl <label> <value>           label dimmed (for secondary lines)
kvl() { printf '  \033[2m%-9s\033[0m %s\n' "$1" "$(clip "$2")"; }

# keys <text>
keys() { printf '\n \033[7m %.34s \033[0m\n' "$*"; }

# rule
rule() { printf ' \033[2m%s\033[0m\n' "────────────────────────"; }

proxy_json() { curl -s -m 3 "$PROXY_URL" 2>/dev/null; }

# ── input ───────────────────────────────────────────────────────────
readkey() { KEY=""; IFS= read -rsn1 -t "$REFRESH" KEY 2>/dev/null || true; }

# pane_loop <draw> <key>
# Draws, waits for a key, acts. Never returns.
pane_loop() {
  local draw="$1" key="$2"
  trap '' INT
  while :; do
    home        # clear each frame — without this the pane scrolls and old
                # frames stack up as duplicated headers / hint lines
    "$draw"
    readkey
    [ -n "${KEY:-}" ] && { "$key" "$KEY"; sleep 0.4; }
  done
}

say() { [ -n "${MSG:-}" ] && { printf '  %s\n' "$MSG"; unset MSG; }; return 0; }

# ── 1. NET ──────────────────────────────────────────────────────────
d_ping() {
  hdr NET
  if ping -c1 -W1 192.168.8.1 >/dev/null 2>&1; then
    ping -c1 -W1 192.168.8.1 2>/dev/null | awk '/time=/{sub(/.*time=/,"");t=$0}
      END{ if (t!="") { split(t,a,"/"); kvo "gateway" sprintf("UP  %s ms", a[1]) OK } }'
  else
    kvo "gateway" "DOWN" BAD
  fi
  kv "ip" "$(ip -4 -o addr show enp7s0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
  kv "ttyd" ":7681"
  keys "c ping · l live · g ttyd opts"
  say
}
k_ping() {
  case "$1" in
    c|C) ping -c1 -W1 192.168.8.1 >/dev/null 2>&1 && MSG="gateway ok" || MSG="gateway DOWN" ;;
    l|L) command -v gping >/dev/null && { gping -c 3600 -i 1 192.168.8.1 >/dev/null 2>&1 & MSG="live ping started"; } || MSG="gping not installed" ;;
    g|G) MSG=$(grep TTYD_OPTIONS /etc/default/ttyd 2>/dev/null | sed 's/-c [^ ]*/-c <hidden>/' | tr -s ' ') ;;
  esac
}
pane_ping() { pane_loop d_ping k_ping; }


# nvidia-smi serialised: concurrent NVML calls from several panes return -1
nvidia-smi_lock() { flock -w 3 /tmp/.nest_gpu.lock nvidia-smi "$@"; }

# ── 2. GPU ──────────────────────────────────────────────────────────
d_gpu() {
  hdr GPU
  nvidia-smi_lock --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 \
    | while read -r n; do kvl "card" "${n% *}"; done
  t=$(nvidia-smi_lock --query-gpu=temperature.gpu --format=csv,noheader 2>/dev/null | head -1)
  u=$(nvidia-smi_lock --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | head -1)
  v=$(nvidia-smi_lock --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | head -1)
  [ -n "$t" ] && kv "temp" "$t"
  [ -n "$u" ] && kv "load" "$u"
  [ -n "$v" ] && kv "vram" "$v"
  keys "t clocks · c temps · f throttle"
}
k_gpu() {
  case "$1" in
    t|T) MSG=$(nvidia-smi_lock --query-gpu=clocks.current.graphics,power.draw --format=csv,noheader 2>/dev/null | tr -s ' ') ;;
    c|C) MSG=$(nvidia-smi -q -d TEMPERATURE 2>/dev/null | grep -E "GPU Current|GPU Shutdown" | tr -s ' \n' ' ') ;;
    f|F) MSG=$(nvidia-smi -q -d PERFORMANCE 2>/dev/null | grep -A6 "Clocks Event" | tr -s ' \n' ' ') ;;
  esac
}
pane_gpu() { pane_loop d_gpu k_gpu; }

# ── 3. MODELS ───────────────────────────────────────────────────────
d_models() {
  hdr MODELS
  if st=$(proxy_json) && [ -n "$st" ]; then
    kvl "active" "$(printf '%s' "$st" | jq -r '.vram_status.model // "none"' 2>/dev/null)"
    kv "vram" "$(printf '%s' "$st" | jq -r '((.vram_status.vram_used_gb // 0)|tostring)+" GiB"' 2>/dev/null)"
    s=$(printf '%s' "$st" | jq -r '.load_state // "-"' 2>/dev/null)
    case "$s" in ready) kvo "state" "$s" OK ;; unreachable) kvo "state" "$s" WARN ;; *) kv "state" "$s" ;; esac
  else
    kvo "proxy" ":8400 offline" BAD
  fi
  keys "l list · u unload · r runtime"
  say
}
k_models() {
  case "$1" in
    l|L) MSG=$(foveai model list 2>&1 | head -8 | tr '\n' ' ') ;;
    u|U) MSG=$(foveai unload 2>&1 | head -2 | tr '\n' ' ') ;;
    r|R) MSG=$(foveai runtime 2>&1 | head -6 | tr '\n' ' ') ;;
  esac
}
pane_models() { pane_loop d_models k_models; }

# ── 4. QUEUE — Jen's undelivered messages ───────────────────────────
# agent_message_queue: delivered=0 means the message never reached the
# chat feed. This is the "urgent follow-up never arrived" symptom.
d_queue() {
  hdr QUEUE
  DB="$FOVEAI_DIR/db/agent_memory.db"
  if [ -f "$DB" ]; then
    q=$(sqlite3 "$DB" "SELECT COUNT(*) FROM agent_message_queue WHERE delivered=0;" 2>/dev/null)
    t=$(sqlite3 "$DB" "SELECT COUNT(*) FROM agent_message_queue;" 2>/dev/null)
    [ "${q:-0}" -gt 0 ] && kvo "undelivered" "$q" WARN || kvo "undelivered" "$q" OK
    kvl "total" "${t:-?}"
    sqlite3 -noheader "$DB" \
      "SELECT substr(replace(message,char(10),' '),1,24) FROM agent_message_queue WHERE delivered=0 ORDER BY priority DESC, timestamp DESC LIMIT 3;" 2>/dev/null \
      | while IFS= read -r m; do kvl "·" "$m"; done
  else
    kv "no agent_memory.db"
  fi
  keys "f poll · x mark delivered"
  say
}
k_queue() {
  DB="$FOVEAI_DIR/db/agent_memory.db"
  case "$1" in
    f|F) n=$(curl -s -m 5 "http://127.0.0.1:8400/api/agent/messages?limit=10" 2>/dev/null \
            | jq -r 'if type=="object" then (.messages // .data // []) | length else 0 end' 2>/dev/null)
         MSG="poll returned ${n:-0}" ;;
    x|X) n=$(sqlite3 "$DB" "SELECT COUNT(*) FROM agent_message_queue WHERE delivered=0;" 2>/dev/null)
         [ "${n:-0}" -gt 0 ] && sqlite3 "$DB" "UPDATE agent_message_queue SET delivered=1 WHERE delivered=0;" 2>/dev/null
         MSG="marked ${n:-0} delivered" ;;
  esac
}
pane_queue() { pane_loop d_queue k_queue; }

# ── 5. FLEET ────────────────────────────────────────────────────────
PORTS="8400:proxy 8401:dash 8402:xrlf 8403:ws-ipc 8405:soul 8406:tts 8407:relay 8408:creative 8409:ignite 5177:multigate 5176:xr-vessel 8888:apk"
d_ports() {
  hdr FLEET
  for spec in $PORTS; do
    port=${spec%%:*}; name=${spec##*:}
    if ss -tln 2>/dev/null | grep -q ":$port "; then kvo "$name" "$port" OK; else kv "$name" "$port"; fi
  done
  keys "1 start · 4 stop · s restart"
  say
}
k_ports() {
  case "$1" in
    1)   MSG=$(foveai stack start 2>&1 | tail -2 | tr '\n' ' ') ;;
    4)   MSG=$(foveai stack stop 2>&1 | tail -2 | tr '\n' ' ') ;;
    s|S) MSG=$(foveai stack restart 2>&1 | tail -2 | tr '\n' ' ') ;;
  esac
}
pane_ports() { pane_loop d_ports k_ports; }

# ── 6. LOG ──────────────────────────────────────────────────────────
d_log() {
  hdr PROXY LOG
  if [ -f /home/lumba/foveated_proxy.log ]; then
    tail -n "${LOGN:-8}" /home/lumba/foveated_proxy.log 2>/dev/null \
      | cut -c1-30 | while IFS= read -r l; do kvl "·" "$l"; done
  else
    kv "no log yet"
  fi
  keys "+ more · c clear"
  say
}
k_log() {
  case "$1" in
    +) LOGN=$(( ${LOGN:-8} + 4 )) ;;
    c|C) : > /home/lumba/foveated_proxy.log 2>/dev/null; MSG="cleared" ;;
  esac
}
pane_log() { pane_loop d_log k_log; }

# ── 7. MEM / LOAD ───────────────────────────────────────────────────
d_procs() {
  hdr MEM
  free -h | awk '/^Mem:/{printf "  %-9s %s / %s\n","ram",$3,$2} /^Swap:/{printf "  %-9s %s / %s\n","swap",$3,$2}'
  kv "load" "$(cut -d' ' -f1-3 /proc/loadavg)  on $(nproc) cpu"
  rule
  ps -eo comm,rss --sort=-rss 2>/dev/null | head -4 \
    | awk 'NR>1{printf "  \033[2m%-9s\033[0m %6.0fM\n",$1,$2/1024}'
  keys "p full ps"
  say
}
k_procs() {
  case "$1" in
    p|P) MSG=$(ps -eo pid,comm,rss --sort=-rss 2>/dev/null | head -6 | tr '\n' ' ') ;;
  esac
}
pane_procs() { pane_loop d_procs k_procs; }

# ── 8. DISKS ────────────────────────────────────────────────────────
d_disks() {
  hdr DISKS
  df -h / /home/lumba 2>/dev/null | awk 'NR>1{printf "  %-9s %s / %s  %s\n",$6,$3,$2,$5}'
  rule
  lsblk -no NAME,SIZE,MOUNTPOINT 2>/dev/null | tail -n +2 | head -4 \
    | while IFS= read -r l; do kvl "·" "$l"; done
  keys "d usage · s FoveAI size"
  say
}
k_disks() {
  case "$1" in
    d|D) MSG=$(df -h /home/lumba | tail -1 | awk '{print "used "$3" of "$2" ("$5")"}') ;;
    s|S) MSG=$(sudo -n du -sh /home/lumba/FoveAI 2>/dev/null | cut -f1 | sed 's/^/FoveAI = /') ;;
  esac
}
pane_disks() { pane_loop d_disks k_disks; }

# ── 9. XRLF ─────────────────────────────────────────────────────────
d_xrlf() {
  hdr XRLF
  if h=$(curl -s -m 3 http://127.0.0.1:8402/health 2>/dev/null) && [ -n "$h" ]; then
    printf '%s' "$h" | jq -r 'to_entries[] | "\(.key) \(.value)"' 2>/dev/null \
      | head -4 | while IFS= read -r l; do kvl "·" "$l"; done
  else
    kvo "state" "offline" BAD
    kvl "fix" "foveai stack start"
  fi
  keys "l list · w wait"
  say
}
k_xrlf() {
  case "$1" in
    l|L) MSG=$(foveai model list 2>&1 | head -6 | tr '\n' ' ') ;;
    w|W) MSG="waiting in background…"; ( foveai runtime wait 300 >/tmp/.nest_wait 2>&1 ) & ;;
  esac
}
pane_xrlf() { pane_loop d_xrlf k_xrlf; }

# ── 10. PROCS (side square) ─────────────────────────────────────────
d_procs2() {
  hdr FOVEAI
  if pgrep -f "server.js|uvicorn|app.main|sleipnir" >/dev/null 2>&1; then
    pgrep -af "server.js|uvicorn|app.main|sleipnir" 2>/dev/null | head -5 \
      | while read -r pid cmd; do kvl "${cmd:0:9}" "$pid"; done
  else
    kv "nothing running"
  fi
  keys "s status · 1 start"
  say
}
k_procs2() {
  case "$1" in
    s|S) MSG=$(foveai stack status 2>&1 | tail -3 | tr '\n' ' ') ;;
    1)   MSG=$(foveai stack start 2>&1 | tail -2 | tr '\n' ' ') ;;
  esac
}
pane_procs2() { pane_loop d_procs2 k_procs2; }

# ── 11. NETSTAT (side square) ───────────────────────────────────────
d_netstat() {
  hdr NETSTAT
  n=$(ss -tun 2>/dev/null | awk '$2=="ESTAB"' | wc -l)
  kvo "established" "$n" OK
  ss -tun 2>/dev/null | awk '$2=="ESTAB"{print $5}' | awk -F: '{print $NF}' \
    | sort -n | uniq -c | sort -rn | head -4 \
    | while read -r c p; do kv ":$p" "$c"; done
  keys "l listening ports"
  say
}
k_netstat() {
  case "$1" in
    l|L) MSG=$(ss -tln 2>/dev/null | awk 'NR>1{print $4}' | sed 's/.*://' | sort -un | tr '\n' ' ') ;;
  esac
}
pane_netstat() { pane_loop d_netstat k_netstat; }

# ── 12. SENSORS (side square) ───────────────────────────────────────
d_sensors() {
  hdr SENSORS
  for h in /sys/class/hwmon/hwmon*; do
    [ -r "$h/temp1_input" ] || continue
    kvl "$(cat "$h/name" 2>/dev/null)" "$(( $(cat "$h/temp1_input") / 1000 ))C"
  done
  kv "uptime" "$(uptime -p 2>/dev/null | sed -E 's/up //; s/,.*//')"
  keys "f throttle reasons"
  say
}
k_sensors() {
  case "$1" in
    f|F) MSG=$(nvidia-smi -q -d PERFORMANCE 2>/dev/null | grep -A6 "Clocks Event" | tr -s ' \n' ' ') ;;
  esac
}
pane_sensors() { pane_loop d_sensors k_sensors; }

# ── 13. BORDER ──────────────────────────────────────────────────────
# Blank. It must not clear the screen or it flickers.
pane_frame() {
  printf '  \033[2m·\033[0m\n'
  sleep 86400
}

# ── 14. GRID CELL ───────────────────────────────────────────────────
pane_cell() {
  printf '  \033[2m·\033[0m\n'
  sleep 86400
}