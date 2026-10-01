"""
edit_layers.py — shared write-layer machinery for FoveAI self-development.

Single source of truth for:
  - .foveignore PROTECTED-layer classification (FORBIDDEN secrets stay
    hardcoded and can never be unlocked by the file)
  - pre-edit snapshots + the self-edit journal (rollback source of truth)
  - protected-layer proposals (architect review queue)

Pure functions — no agent state. Callers may pass a `log_fn(kind, data, msg)`
hook for their own action log (autonomous_agent passes log_action; the MCP
server passes None). Imported by autonomous_agent, coder_tools, and the
rollback CLI must stay standalone (it re-reads the journal directly).
"""

import fnmatch
import json
import logging
import os
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

FoveAI_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# ── Layered write permissions ─────────────────────────────────────────────
_SECRET_PAT = re.compile(
    r"\.env|secret|credential|id_rsa|id_dsa|\.pem$|\.key$|password|token|\.ssh|gnupg",
    re.IGNORECASE,
)
_FOVEIGNORE_PATH = os.path.join(FoveAI_ROOT, ".foveignore")
# Hardcoded protected floor — can never be removed by editing .foveignore.
_PROTECTED_FLOOR = (
    ".foveignore",
    "Backend/Cognition/autonomous_agent.py",
    "Backend/Cognition/coder_agent.py",
    "Backend/Cognition/edit_layers.py",
    "Backend/Cognition/coder_tools.py",
)
_foveignore_cache: dict[str, Any] = {"mtime": -1.0, "rules": []}


def _load_foveignore() -> list[tuple[bool, str]]:
    """Parse .foveignore → [(negated, pattern), ...]; cached by mtime."""
    try:
        mtime = os.path.getmtime(_FOVEIGNORE_PATH)
    except OSError:
        return []
    if mtime == _foveignore_cache["mtime"]:
        return _foveignore_cache["rules"]
    rules = []
    try:
        with open(_FOVEIGNORE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                neg = line.startswith("!")
                pat = line[1:] if neg else line
                if pat:
                    rules.append((neg, pat))
    except Exception as e:
        logger.warning(f"Could not parse .foveignore: {e}")
    _foveignore_cache["mtime"] = mtime
    _foveignore_cache["rules"] = rules
    return rules


def _foveignore_match(rel: str) -> bool:
    """True if rel is protected by .foveignore (last matching rule wins)."""
    protected = False
    for neg, pat in _load_foveignore():
        p = pat.rstrip("/")
        hit = (
            rel == p
            or rel.startswith(p + "/")
            or fnmatch.fnmatch(rel, p)
            or fnmatch.fnmatch(rel, p + "/*")
        )
        if hit:
            protected = not neg
    return protected


PROPOSALS_PATH = os.path.join(FoveAI_ROOT, "Backend", "data", "agent_proposals.jsonl")


def classify_edit_path(file_path: str) -> str:
    """Return 'FORBIDDEN' | 'PROTECTED' | 'OPEN' for a target path."""
    p = file_path.replace("\\", "/")
    if _SECRET_PAT.search(p):
        return "FORBIDDEN"
    full = p if os.path.isabs(p) else os.path.join(FoveAI_ROOT, p)
    full = os.path.normpath(full)
    root = os.path.normpath(FoveAI_ROOT)
    if not (full == root or full.startswith(root + os.sep)):
        return "PROTECTED"  # outside the repo — proposal only
    rel = os.path.relpath(full, root).replace("\\", "/")
    if rel in _PROTECTED_FLOOR or _foveignore_match(rel):
        return "PROTECTED"
    return "OPEN"


def file_edit_proposal(
    file_path: str, search: str, replacement: str, log_fn: Callable | None = None
) -> dict[str, Any]:
    """Queue a proposed edit for architect review instead of applying it."""
    try:
        os.makedirs(os.path.dirname(PROPOSALS_PATH), exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "file": file_path,
            "search": search,
            "replacement": replacement,
        }
        with open(PROPOSALS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        if log_fn:
            log_fn(
                "edit_proposal",
                {"file": file_path},
                f"Protected-layer edit filed as proposal in {PROPOSALS_PATH}",
            )
        return {
            "success": True,
            "proposed": True,
            "result": f"'{file_path}' is in a protected layer — filed as a proposal for review.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Self-edit rollback journal ────────────────────────────────────────────
SELF_EDITS_DIR = os.path.join(FoveAI_ROOT, "Backend", "data", "self_edits")
SELF_EDITS_JOURNAL = os.path.join(SELF_EDITS_DIR, "edits.jsonl")


def snapshot_before_edit(full_path: str, actor: str = "self") -> str | None:
    """Snapshot a file's pre-edit content and journal it. Returns edit id."""
    try:
        os.makedirs(SELF_EDITS_DIR, exist_ok=True)
        edit_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            + "_"
            + uuid.uuid4().hex[:6]
        )
        snap_path = os.path.join(SELF_EDITS_DIR, edit_id + ".orig")
        with open(full_path, "rb") as src, open(snap_path, "wb") as dst:
            dst.write(src.read())
        entry = {
            "id": edit_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "file": os.path.relpath(full_path, FoveAI_ROOT).replace("\\", "/"),
            "snapshot": snap_path,
            "actor": actor,
            "rolled_back": False,
        }
        with open(SELF_EDITS_JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return edit_id
    except Exception as e:
        logger.error(f"Edit snapshot failed for {full_path}: {e}")
        return None


def rollback_edit(
    edit_id: str | None = None, log_fn: Callable | None = None
) -> dict[str, Any]:
    """Restore a file from its pre-edit snapshot. No id → most recent edit."""
    try:
        if not os.path.exists(SELF_EDITS_JOURNAL):
            return {
                "success": False,
                "error": "No self-edit journal — nothing to roll back.",
            }
        entries = []
        with open(SELF_EDITS_JOURNAL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        target = None
        if edit_id:
            target = next((e for e in entries if e.get("id") == edit_id), None)
        else:
            target = next(
                (e for e in reversed(entries) if not e.get("rolled_back")), None
            )
        if not target:
            return {
                "success": False,
                "error": f"No matching edit{': ' + edit_id if edit_id else ''}.",
            }
        if target.get("rolled_back"):
            return {
                "success": False,
                "error": f"Edit {target['id']} was already rolled back.",
            }
        snap, rel = target["snapshot"], target["file"]
        full = os.path.join(FoveAI_ROOT, rel)
        if not os.path.exists(snap):
            return {"success": False, "error": f"Snapshot missing for {target['id']}"}
        with open(snap, "rb") as src, open(full, "wb") as dst:
            dst.write(src.read())
        target["rolled_back"] = True
        with open(SELF_EDITS_JOURNAL, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(e) + "\n" for e in entries)
        if log_fn:
            log_fn(
                "edit_rollback",
                {"id": target["id"], "file": rel},
                f"Rolled back self-edit {target['id']} on {rel}",
            )
        return {
            "success": True,
            "result": f"Rolled back {rel} to pre-edit state ({target['id']}).",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
