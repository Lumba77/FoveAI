#!/usr/bin/env bash
#
# foveai-backup.sh — Mount Disk5, sync FoveAI + audio/FX config, unmount.
#
# The disk is only mounted for the duration of the backup and is always
# unmounted afterwards (via trap), so the backup storage stays offline
# during normal operation.
#
# Additive sync (no --delete): files removed from the source are NOT
# removed from the backup — nothing on Disk5 is ever deleted by this script.
#
set -u

DEV="/dev/sdd1"
MNT="/media/lumba/Disk5"
DEST="$MNT/Backups"
LOG="$HOME/.local/state/foveai-backup.log"

mkdir -p "$(dirname "$LOG")"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

cleanup() {
    if mountpoint -q "$MNT"; then
        udisksctl unmount -b "$DEV" >>"$LOG" 2>&1 \
            && log "Disk5 unmounted" \
            || log "WARNING: unmount of $DEV failed"
    fi
}
trap cleanup EXIT

log "=== Backup started ==="

if ! mountpoint -q "$MNT"; then
    if ! udisksctl mount -b "$DEV" >>"$LOG" 2>&1; then
        log "ERROR: could not mount $DEV — aborting"
        exit 1
    fi
    log "Disk5 mounted at $MNT"
fi

mkdir -p "$DEST"

# Exclusions live in the repo's .backupignore (ported from backup.ps1).
# rsync -a is incremental by nature: after the first full sync only changed
# files are copied — timestamps/size are compared, unchanged files are skipped.
IGNORE_FILE="$HOME/FoveAI/.backupignore"

run_rsync() {
    rsync -a --human-readable --itemize-changes \
        ${IGNORE_FILE:+--exclude-from="$IGNORE_FILE"} \
        "$@" >>"$LOG" 2>&1
}

run_rsync "$HOME/FoveAI/"          "$DEST/FoveAI/"
RC_FOVEAI=$?

# NTFS can't hold names with ':' (ISO-timestamp dirs) — tar them into a
# single archive instead, so memory snapshots survive intact.
SHADOW_DIR="$HOME/FoveAI/foveated-memory/memory_data/shadow-context"
if [ -d "$SHADOW_DIR" ]; then
    tar -czf "$DEST/shadow-context.tar.gz" -C "$HOME/FoveAI/foveated-memory/memory_data" \
        shadow-context >>"$LOG" 2>&1 \
        && log "shadow-context archived (tar) — NTFS-safe" \
        || log "WARNING: shadow-context tar failed"
fi
run_rsync "$HOME/.local/bin/"      "$DEST/local-bin/"
RC_BIN=$?
run_rsync "$HOME/.config/pipewire/" "$DEST/pipewire-config/"
RC_PW=$?

if [ $RC_FOVEAI -eq 0 ] && [ $RC_BIN -eq 0 ] && [ $RC_PW -eq 0 ]; then
    log "=== Backup finished OK ==="
    exit 0
else
    log "=== Backup finished with errors (foveai=$RC_FOVEAI bin=$RC_BIN pipewire=$RC_PW) ==="
    exit 2
fi
