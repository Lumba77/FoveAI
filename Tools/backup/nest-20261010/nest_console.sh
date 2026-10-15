#!/usr/bin/env bash
#
# nest_console.sh — the command that runs in the nest's centre pane.
#
# Two jobs:
#
#  1. Present the FoveAI console (FoveAI_Console.py) as the default, so
#     attaching to the dashboard gives you the menu, not a bare prompt.
#
#  2. If that menu exits — or cannot start — drop to a normal shell
#     instead of ending the pane. A pane whose command exits takes the
#     whole tmux session down with it, which loses the dashboard, so the
#     shell is the floor: this command never returns.
#
# The shell prompt is prefixed to show you are inside the nest. That is
# cosmetic, but it is the thing that stops "did my nest just start a
# nest?" confusion.

VENV_PY="$1"
CONSOLE_PY="$2"

# ── prompt ──────────────────────────────────────────────────────────
# Deliberately short. On an overscanning TV the tail of the line is
# cropped, and a long path prompt is exactly what gets cut — so you cannot
# see the end of the command you are typing. Keep it to a few columns.
#
#   foveai〉          short
#   〉NEST            with the working directory (still ~12 cols)
#   ~                bare, when NEST_BARE_PROMPT=1
if [ -n "${NEST_BARE_PROMPT:-}" ]; then
  PS1='〉 '
else
  PS1='\[\033[1;36m\]foveai\[\033[0m〉\[\033[2m\]\W\[\033[0m\] '
fi
export PS1

banner() {
  printf '\033[1;36m┌─ foveai nest console ─────────────────────\033[0m\n'
  printf '\033[2m  Ctrl-b n / Ctrl-b <   move between the 13 panes\033[0m\n'
  printf '\033[2m  Ctrl-b d              detach (dashboard keeps running)\033[0m\n'
  printf '\033[2m  %-22s \033[0m\n' "$*"
  printf '\033[2m  NEST_DEPTH=%s — `foveai --nest` here is refused.\033[0m\n' "${NEST_DEPTH:-0}"
  printf '\033[1;36m└───────────────────────────────────────────\033[0m\n\n'
}

# ── run the menu, then fall through to a shell ──────────────────────
if [ -f "$CONSOLE_PY" ] && [ -x "$VENV_PY" ]; then
  "$VENV_PY" "$CONSOLE_PY" "$@"
  banner "FoveAI console exited — dropped to a shell."
else
  banner "FoveAI_Console.py or the venv is missing — shell only."
fi

exec bash -l