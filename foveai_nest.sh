#!/usr/bin/env bash
# foveai_nest.sh — the FoveAI console surrounded by small metric squares.
#
#        ┌────────┬────────┬────────┬────────┐
#        │  net   │  gpu   │ models │ queue  │   4 across the top
#        ├────────┼────────┼────────┼────────┤
#        │ fleet  │ procs  │CONSOLE │  log   │   4 beside the console
#        ├────────┼────────┼────────┼────────┤
#        │  mem   │ disks  │  xrlf  │sensors │   4 across the bottom
#        └────────┴────────┴────────┴────────┘
#
# ── how the geometry is produced ─────────────────────────────────────
# Nothing is resized after the fact. The layout falls out of two
# properties of split-window, used together:
#
#   split-window -b -l N   new pane ABOVE, N tall
#   split-window -d -l N   new pane BELOW, N tall
#   split-window -h -l N   new pane RIGHT, N wide
#
# Pane A is created as the FULL WINDOW and everything else is split off
# it, so A keeps all the slack in both directions — which is exactly what
# the console wants. Every other pane gets an explicit size at birth.
#
# This replaced two approaches that both failed:
#
#   * COLUMNS FIRST (repeated -h), then rows. That makes every row share
#     one set of vertical boundaries, so the middle row cannot hold a wide
#     cell between narrow ones — the columns are forced to line up, and the
#     result is lopsided rows like 15/84/1/84.
#
#   * swap-pane to move a pre-built console into the centre. Geometry is
#     bound to a pane's POSITION but swap-pane moves the PROCESS, so an id
#     captured before the swap stops naming the console afterwards.
#
# ── why this cannot trap you ─────────────────────────────────────────
# The centre pane runs FoveAI_Console.py, and if that exits the pane falls
# back to a plain shell (nest_console.sh). Neither can spawn a nest, so
# the runaway recursion has no first step — which is the bug that used to
# crush every square into the middle and leave a dead, inescapable ring.
# If that ever changes, these guards stop a nest building inside a nest:
#
#   $TMUX set         already inside tmux
#   NEST_DEPTH >= 1   already in a nest
#
# Escape is bound to kill the whole session.

set -uo pipefail

SESSION="${NEST_SESSION:-foveai-nest}"
NEST_DEPTH="${NEST_DEPTH:-0}"
MAX_DEPTH=1

FOVEAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PANE_LIB="$FOVEAI_DIR/.nest-panes.sh"
CONSOLE_SH="$FOVEAI_DIR/nest_console.sh"
CONSOLE_PY="$FOVEAI_DIR/FoveAI_Console.py"
VENV_PY="$FOVEAI_DIR/.venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$(command -v python3)"

# ── guards ──────────────────────────────────────────────────────────
if [ -n "${TMUX:-}" ] || [ "$NEST_DEPTH" -ge "$MAX_DEPTH" ]; then
  cat >&2 <<EOF

🛸 [Nest] Already inside a nest — refusing to build another.

    Nesting used to shrink every square into the middle and leave a dead,
    inescapable ring around it. A nest never contains another one.

    where : depth=$NEST_DEPTH
    quit  : tmux kill-session -t $SESSION

EOF
  exit 0
fi

command -v tmux >/dev/null || { echo "🛸 [Nest] tmux required: sudo apt install -y tmux" >&2; exit 1; }
[ -f "$PANE_LIB" ] || { echo "🛸 [Nest] missing $PANE_LIB" >&2; exit 1; }
[ -x "$CONSOLE_SH" ] || { echo "🛸 [Nest] missing $CONSOLE_SH" >&2; exit 1; }
[ -x "$VENV_PY" ] || { echo "🛸 [Nest] no python found" >&2; exit 1; }

# ── size ────────────────────────────────────────────────────────────
# Measured from the real terminal so the squares fit the screen you are
# actually looking at. No TTY falls back to a sane default.
if [ -z "${NEST_COLS:-}" ] && [ -t 1 ] && command -v tput >/dev/null; then
  COLS=$(tput cols 2>/dev/null || echo 200)
  ROWS=$(tput lines 2>/dev/null || echo 50)
else
  COLS="${NEST_COLS:-200}"
  ROWS="${NEST_ROWS:-50}"
fi

# ── squares ─────────────────────────────────────────────────────────
# How many metric squares sit beside the console, and how wide they are.
NCOL="${NEST_NCOL:-2}"
[ "$NCOL" -lt 0 ] && NCOL=0
[ "$NCOL" -gt 8 ] && NCOL=8
# Outer margin: a blank frame of dead space around EVERYTHING, so the TV
# crops the frame instead of a square or the console's edge. Roughly 1-2cm.
MARGIN="${NEST_MARGIN:-4}"
[ "$MARGIN" -lt 0 ] && MARGIN=0
[ "$MARGIN" -gt 12 ] && MARGIN=12

# Side columns beside the console. These need real width to be readable,
# and the outer margin is what buys it: without a frame the only way to
# widen them was to take width from the console, or leave them narrow
# enough to fall outside the cropped area.
SIDE="${NEST_SIDE:-0}"
if [ "$SIDE" -eq 0 ]; then
  SIDE=$(( COLS * 5 / 100 ))
  [ "$SIDE" -lt 16 ] && SIDE=16
  [ "$SIDE" -gt 22 ] && SIDE=22
fi

# Band height: slim, and the console keeps the vertical slack. Never let
# the bands take more than a third of the height.
BAND="${NEST_BAND:-8}"
[ "$BAND" -gt 12 ] && BAND=12
_avail=$(( ROWS - 1 ))
_maxband=$(( _avail / 5 ))
[ "$BAND" -gt "$_maxband" ] && BAND=$_maxband
[ "$BAND" -lt 6 ] && BAND=6

# A band spans only the console's width, not the whole window — the
# console's own squares sit beside it. Sizing a band by the full width
# overran it and left 1px slivers in the row.
WORK_COLS=$(( COLS - MARGIN * 2 ))
CON_W=$(( WORK_COLS - SIDE * NCOL ))
[ "$CON_W" -lt 40 ] && CON_W=40
W4=$(( (WORK_COLS - 2) / 3 ))
[ "$W4" -lt 6 ] && W4=6

# Refuse rather than build something broken. Too small to hold a console
# plus four squares is a real limit, and a clear message beats 1px
# slivers you cannot type into.
if [ "$(( SIDE * NCOL + 40 ))" -gt "$COLS" ] || [ "$(( BAND * 2 + 10 ))" -gt "$ROWS" ]; then
  cat >&2 <<EOF
🛸 [Nest] terminal too small: ${COLS}x${ROWS} cannot hold a console plus ${NCOL} squares.

    Widen the window, or ask for fewer squares:
      NEST_NCOL=0 foveai --nest      # console only
      NEST_NCOL=2 foveai --nest      # console + two squares
EOF
  exit 1
fi

run_pane() {
  printf 'exec bash --noprofile --norc -c "source %q; pane_%s"' "$PANE_LIB" "$1"
}
sp() {
  local target="$1" fn="$2"; shift 2
  tmux split-window -P -F '#{pane_id}' -t "$target" "$@" \
    -c "$FOVEAI_DIR" "$(run_pane "$fn")"
}

tmux kill-session -t "$SESSION" 2>/dev/null

# ═══ build ═════════════════════════════════════════════════════════
# Pane A is the whole window, and ends up the CONSOLE.
tmux new-session -d -s "$SESSION" -x "$COLS" -y "$ROWS" "$(run_pane ports)"
tmux set-environment -t "$SESSION" FOVEAI_DIR "$FOVEAI_DIR" 2>/dev/null
A=$(tmux display-message -p -t "$SESSION" '#{pane_id}')

# ── the outer frame ─────────────────────────────────────────────────
# Carved while A is still the FULL window, so the top and bottom margins
# span the whole width and the corners are covered. Then A is pinned
# narrow to become the left margin, and what is left over is the working
# area the grid is built in.
if [ "$MARGIN" -gt 0 ]; then
  sp "$A" frame -b -l "$MARGIN" >/dev/null      # top margin
  sp "$A" frame -d -l "$MARGIN" >/dev/null      # bottom margin
  _rem=$(sp "$A" frame -h -l "$MARGIN")         # grows into the working area
  tmux resize-pane -t "$A" -x "$MARGIN"         # A becomes the left margin
  tmux respawn-pane -k -t "$A" "$(run_pane frame)"  # strip its old command
  sp "$_rem" frame -h -l "$MARGIN" >/dev/null    # right margin
  A="$_rem"                                     # the grid is built in here
fi

# ── one band above, one below ───────────────────────────────────────
# Both applied to A, so A keeps the vertical slack and becomes the
# tallest row. NOTE: -b and -d must come BEFORE -l, or tmux reads the
# flag as the command and the split silently does nothing.
B_TOP=$(sp "$A" ping -b -l "$BAND")
B_BOT=$(sp "$A" xrlf -d -l "$BAND")

# ── four squares across each band ───────────────────────────────────
# Three splits on the band's own leftmost pane: it keeps the remainder,
# the three new ones get W4 exactly.
t2=$(sp "$B_TOP" models -h -l "$W4")
t3=$(sp "$B_TOP" gpu    -h -l "$W4")
b2=$(sp "$B_BOT" disks  -h -l "$W4")
b3=$(sp "$B_BOT" xrlf   -h -l "$W4")

# ── the squares beside the console ──────────────────────────────────
# The middle row is:  [square] [ CONSOLE ] [square]
#
# tmux split-window -h ALWAYS puts the new pane to the RIGHT of its
# target, so a pane can never gain a LEFT neighbour by splitting — which
# is why an earlier version ended up with the console on the left edge and
# every square to its right.
#
# The way round it: split A and then PIN A narrow. A becomes a square on
# the left, and whatever was left over is the next cell. Repeat for each
# left square; the last remainder is the console. Right squares are then
# split off that, which -h does natively.
NCOL_L=$(( NCOL / 2 ))
NCOL_R=$(( NCOL - NCOL_L ))
LEFTFNS=(procs2 sensors)
RIGHTFNS=(log netstat)

REM="$A"
for (( _i = 0; _i < NCOL_L; _i++ )); do
  _new=$(sp "$REM" "${LEFTFNS[$(( _i % 2 ))]}" -h -l "$SIDE")
  tmux resize-pane -t "$REM" -x "$SIDE"     # REM becomes the left square
  REM="$_new"                                # and _new is the next cell
done
CONSOLE="$REM"

for (( _i = 0; _i < NCOL_R; _i++ )); do
  sp "$CONSOLE" "${RIGHTFNS[$(( _i % 2 ))]}" -h -l "$SIDE" >/dev/null
done

# ── the console ────────────────────────────────────────────────────
# Respawned, never split again, so nothing can move it afterwards.
#
# The depth guard is inlined here rather than set with tmux
# set-environment, which applies only to panes started AFTER the call —
# so it never reached the console and the guard silently did nothing.
tmux respawn-pane -k -t "$CONSOLE" \
  "NEST_PANE=console NEST_DEPTH=$((NEST_DEPTH + 1)) FOVEAI_DIR=$FOVEAI_DIR exec $CONSOLE_SH $VENV_PY $CONSOLE_PY"

# ── even out the bands ──────────────────────────────────────────────
# By explicit id, not by position.
#
# Matching on pane_top also catches the outer frame — the left margin
# spans the full height, so it shares a top offset with the top band and
# got resized to W4 as well, which is what left 1px slivers and shrank the
# console to 45%. The six band panes are already known by id.
# The band squares and the console are sized INDEPENDENTLY.
# Each band holds 3 squares across the working width; the console holds
# itself plus the two side columns. Sizing the band off CON_W made the
# numbers impossible to satisfy (156 + 52 + 52 > 188) and tmux resolved
# the conflict by crushing one square to 1px.
BAND_W=$(( WORK_COLS - W4 * 2 ))
tmux resize-pane -t "$B_TOP" -x "$BAND_W"
tmux resize-pane -t "$B_BOT" -x "$BAND_W"
for p in "$t2" "$t3" "$b2" "$b3"; do
  tmux resize-pane -t "$p" -x "$W4"
done

# ── presentation ────────────────────────────────────────────────────
tmux set-option -t "$SESSION" -g focus-events on >/dev/null 2>&1 || true
tmux set-option -t "$SESSION" -g mouse on       >/dev/null 2>&1 || true
tmux set-window-option -t "$SESSION" -g pane-active-border-style \
  'fg=cyan,bold' >/dev/null 2>&1 || true
tmux set-window-option -t "$SESSION" -g pane-border-style \
  'fg=grey' >/dev/null 2>&1 || true
# window-size latest: the grid must fit whatever terminal you attach
# from. `manual` pins it at the build size and pushes the outer squares
# outside your view when attaching from a different-sized terminal.
tmux set-option -t "$SESSION" -g window-size latest >/dev/null 2>&1 || true

# Console scrolling — CONSOLE PANE ONLY.
# The squares are live-updating one-glance cells; scrolling one of them
# into copy-mode just freezes its refresh and looks like a freeze.
# So the wheel and PageUp are scoped: they check #{pane_id} against the
# console pane we keep in $CONSOLE, and only the console page-backs.
# The metric squares pass mouse events straight through to the app.
tmux set-option -t "$SESSION" -g history-limit 100000 >/dev/null 2>&1 || true
tmux set-window-option -t "$SESSION:0" -g history-limit 100000 >/dev/null 2>&1 || true
tmux set-option -t "$SESSION" -g alternate-screen on >/dev/null 2>&1 || true
ISCONSOLE="tmux compare-versions 3.2 >= 3.2;"        # no-op guard, readability only
tmux bind-key -T root WheelUpPane   "if -Ft= '#{&&:#{==:#{pane_id},$CONSOLE},#{mouse_any_flag}}' 'send-keys -M' 'if -Ft= '#{==:#{pane_id},$CONSOLE}' 'copy-mode -e; send-keys -U 3' 'send-keys -M''" >/dev/null 2>&1 || true
tmux bind-key -T root WheelDownPane "if -Ft= '#{&&:#{==:#{pane_id},$CONSOLE},#{mouse_any_flag}}' 'send-keys -M' 'if -Ft= '#{==:#{pane_id},$CONSOLE}' 'send-keys -D 3' 'send-keys -M''" >/dev/null 2>&1 || true
tmux bind-key -T root PageUp        "if -Ft= '#{==:#{pane_id},$CONSOLE}' 'copy-mode -e' 'send-keys PageUp'" >/dev/null 2>&1 || true

# Scroll/copy-mode draws a SECOND status line (status-format[1]) listing
# every pane with index and size. On a 13-pane dashboard it reads as
# "time + message count" noise, and it is only cosmetic. Hide it: the
# single normal status line is enough in copy-mode too.
tmux set-option -t "$SESSION" status-format[1] "" >/dev/null 2>&1 || true

# Escape is a panic button: no prefix, no confirmation.
tmux bind-key -T root   Escape kill-session >/dev/null 2>&1 || true
tmux bind-key -T prefix Escape kill-session >/dev/null 2>&1 || true
tmux bind-key -n        Escape kill-session >/dev/null 2>&1 || true

# Focus the console LAST. tmux leaves focus on whatever pane was touched
# last, and the splits above end on a square — so without this you attach
# into an 18px pane and cannot type anything useful.
tmux select-pane -t "$CONSOLE" >/dev/null 2>&1 || true

read -r vw vh vx vy < <(tmux display-message -p -t "$CONSOLE" \
  '#{pane_width} #{pane_height} #{pane_left} #{pane_top}')
NP=$(tmux list-panes -t "$SESSION" | wc -l)

cat <<EOF

🛸 [Nest] $NP panes    window ${COLS}x${ROWS}

    console  ${vw}x${vh}  — $(( vw * 100 / COLS ))% of the width
    squares  ${W4}x${BAND} x8      ${SIDE} wide  (${NCOL_L} left · ${NCOL_R} right)

    moving   Ctrl-b then an ARROW key  (or Ctrl-b n / Ctrl-b <)
    leave    Escape   (kills the dashboard)
    detach   Ctrl-b d

EOF

tmux attach -t "$SESSION" 2>/dev/null || {
  echo "    no TTY here; running in the background. Attach with:"
  echo "      tmux attach -t $SESSION"
  exit 0
}