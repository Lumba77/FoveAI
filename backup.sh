#!/usr/bin/env bash
#
# backup.sh — Sovereign local snapshot backup for FoveAI Linux environment.
# Creates a dated .tar.gz snapshot into backups/ respecting .backupignore.
#

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${REPO_DIR}/backups"
IGNORE_FILE="${REPO_DIR}/.backupignore"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
ARCHIVE_NAME="foveai-backup-${TIMESTAMP}.tar.gz"
TARGET="${BACKUP_DIR}/${ARCHIVE_NAME}"

mkdir -p "${BACKUP_DIR}"

echo "=================================================="
echo " Starting FoveAI sovereign safety backup"
echo " Target: ${TARGET}"
echo "=================================================="

EXCLUDE_ARGS=()
if [ -f "${IGNORE_FILE}" ]; then
    EXCLUDE_ARGS+=(--exclude-from="${IGNORE_FILE}")
fi

EXCLUDE_ARGS+=(--exclude="./backups" --exclude="backups" --exclude="*/backups/*")

cd "${REPO_DIR}"

tar --wildcards --wildcards-match-slash -czf "${TARGET}" "${EXCLUDE_ARGS[@]}" .

SIZE_MB="$(du -m "${TARGET}" | cut -f1)"

echo "=================================================="
echo " Backup successfully created!"
echo " File: ${TARGET}"
echo " Size: ${SIZE_MB} MB"
echo "=================================================="
