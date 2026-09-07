#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CODE SHERIFF — Safe Self-Augmentation Guardian                        ║
║  ────────────────────────────────────────────────────────────────────  ║
║  When Lumax modifies her own code via <edit_file> tags or J-Aider,     ║
║  this module ensures:                                                  ║
║  1. Pre-edit snapshots are saved to backups/autosave                   ║
║  2. Syntax validation (TypeScript / Python compile) after edits        ║
║  3. Automatic rollback on failure                                      ║
║  4. Restoration commands exposed to the LLM via MCP tools              ║
╚══════════════════════════════════════════════════════════════════════════╝

Design principle: Jen should be free to modify herself extensively,
but NEVER to a degree she can't recover from. This is her safety net.
"""

import os
import shutil
import subprocess
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger("code_sheriff")

# ── Constants ──────────────────────────────────────────────────────────
BACKUP_ROOT = Path(__file__).parent.parent / "backups" / "autosave"
BACKUP_INDEX = BACKUP_ROOT / "index.json"

# Extensions we know how to validate
VALIDATORS: Dict[str, List[str]] = {
    ".ts": ["npx", "tsc", "--noEmit"],
    ".tsx": ["npx", "tsc", "--noEmit"],
    ".js": ["node", "--check"],
    ".py": ["python", "-m", "py_compile"],
}

# Files we should NEVER modify (safety-critical)
NO_TOUCH_LIST = [
    "backend/Cognition/code_sheriff.py",  # This file — self-protection
    "backups/autosave/",               # Backup directory
    ".env",                            # Secrets
    ".git/",                           # Version control
]

def _ensure_dirs():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    if not BACKUP_INDEX.exists():
        BACKUP_INDEX.write_text("{}")

def _load_index() -> dict:
    _ensure_dirs()
    try:
        return json.loads(BACKUP_INDEX.read_text())
    except:
        return {}

def _save_index(idx: dict):
    _ensure_dirs()
    BACKUP_INDEX.write_text(json.dumps(idx, indent=2))

def snapshot(filepath: str) -> Optional[str]:
    """
    Create a backup snapshot of a file before editing.
    Returns snapshot ID or None if file doesn't exist.
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"[Sheriff] Cannot snapshot — file not found: {filepath}")
        return None
    
    # Check no-touch list
    for forbidden in NO_TOUCH_LIST:
        if str(path).replace("\\", "/").startswith(forbidden.replace("\\", "/")):
            logger.error(f"[Sheriff] REFUSING to snapshot protected file: {filepath}")
            return None
    
    content = path.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()[:16]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_id = f"{path.stem}_{timestamp}_{file_hash}"
    
    # Save backup
    backup_path = BACKUP_ROOT / snapshot_id
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    
    # Update index
    idx = _load_index()
    idx[snapshot_id] = {
        "original": str(path),
        "timestamp": timestamp,
        "hash": file_hash,
        "size": len(content),
    }
    _save_index(idx)
    
    logger.info(f"[Sheriff] 📸 Snapshot saved: {snapshot_id} ({len(content)} bytes)")
    return snapshot_id

def validate(filepath: str) -> Tuple[bool, str]:
    """
    Run syntax validation on a file after editing.
    Returns (success, error_message).
    """
    path = Path(filepath)
    ext = path.suffix.lower()
    
    if ext not in VALIDATORS:
        logger.info(f"[Sheriff] No validator for {ext}, skipping validation")
        return True, ""
    
    cmd = list(VALIDATORS[ext])
    # For npx tsc, we need project context
    if ext in (".ts", ".tsx"):
        project_dir = find_project_root(path)
        if project_dir:
            cmd = ["npx", "tsc", "--project", str(project_dir), "--noEmit"]
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=30,
            cwd=str(path.parent)
        )
        if result.returncode == 0:
            logger.info(f"[Sheriff] ✅ Validation passed: {filepath}")
            return True, ""
        else:
            err = result.stderr or result.stdout
            logger.error(f"[Sheriff] ❌ Validation failed for {filepath}:\n{err[:500]}")
            return False, err[:2000]
    except subprocess.TimeoutExpired:
        return False, "Validation timed out after 30s"
    except Exception as e:
        return False, str(e)

def rollback(snapshot_id: str) -> bool:
    """
    Restore a file from a snapshot. Returns True on success.
    """
    idx = _load_index()
    if snapshot_id not in idx:
        logger.error(f"[Sheriff] Snapshot not found: {snapshot_id}")
        return False
    
    info = idx[snapshot_id]
    original = Path(info["original"])
    backup = BACKUP_ROOT / snapshot_id
    
    if not backup.exists():
        logger.error(f"[Sheriff] Backup file missing: {backup}")
        return False
    
    # Restore
    shutil.copy2(backup, original)
    logger.info(f"[Sheriff] 🔄 Rolled back: {original} → snapshot {snapshot_id}")
    return True

def guard_edit(filepath: str, new_content: str) -> Dict:
    """
    Safe edit wrapper: snapshot → write → validate → rollback on failure.
    Returns {"success": bool, "snapshot_id": str, "error": str}.
    """
    sid = snapshot(filepath)
    if sid is None:
        return {"success": False, "snapshot_id": "", "error": "Snapshot failed"}
    
    path = Path(filepath)
    try:
        path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return {"success": False, "snapshot_id": sid, "error": f"Write failed: {e}"}
    
    ok, err = validate(filepath)
    if not ok:
        # Auto-rollback on validation failure
        rollback(sid)
        return {"success": False, "snapshot_id": sid, "error": err}
    
    return {"success": True, "snapshot_id": sid, "error": ""}

def list_snapshots(limit: int = 20) -> List[Dict]:
    """List recent snapshots for the LLM to inspect/restore."""
    idx = _load_index()
    items = sorted(idx.items(), key=lambda x: x[1]["timestamp"], reverse=True)[:limit]
    return [{"id": k, **v} for k, v in items]

def find_project_root(filepath: Path) -> Optional[Path]:
    """Walk up directories to find tsconfig.json or package.json."""
    current = filepath.parent
    for _ in range(5):
        if (current / "tsconfig.json").exists():
            return current
        if (current / "package.json").exists():
            return current
        current = current.parent
    return None

def get_edit_safety_report() -> str:
    """
    Generate a status report for the LLM so it knows:
    1. How many snapshots exist
    2. What files were recently modified
    3. How to restore if something broke
    """
    idx = _load_index()
    if not idx:
        return "[SHERIFF] No snapshots yet. System is clean."
    
    recent = sorted(idx.items(), key=lambda x: x[1]["timestamp"], reverse=True)[:5]
    lines = ["[SHERIFF STATUS]"]
    lines.append(f"  Snapshots stored: {len(idx)}")
    lines.append(f"  Recent edits:")
    for sid, info in recent:
        lines.append(f"    {info['timestamp']} — {info['original']} ({info['size']}B)")
    lines.append(f"  To restore: call rollback('{recent[0][0]}') if last edit broke something.")
    return "\n".join(lines)

def edit_file(filepath: str, blocks: List[Dict[str, str]]) -> Dict:
    """
    Apply search/replace blocks to a file safely: snapshot -> edit -> validate -> rollback.
    """
    sid = snapshot(filepath)
    if sid is None:
        return {"success": False, "message": "Snapshot failed before edit"}
    
    path = Path(filepath)
    try:
        content = path.read_text(encoding="utf-8")
        for block in blocks:
            search = block.get("search", "")
            replace = block.get("replace", "")
            if not search:
                continue
            if search not in content:
                rollback(sid)
                return {"success": False, "message": f"Search block not found: {search}"}
            content = content.replace(search, replace, 1)
        path.write_text(content, encoding="utf-8")
    except Exception as e:
        rollback(sid)
        return {"success": False, "message": f"Edit write failed: {e}"}
        
    ok, err = validate(filepath)
    if not ok:
        rollback(sid)
        return {"success": False, "message": f"Validation failed: {err}"}
        
    return {"success": True, "message": f"Edited {filepath} successfully", "snapshot_id": sid}

# Aliases for external integration compatibility
snapshot_file = snapshot
validate_file = validate