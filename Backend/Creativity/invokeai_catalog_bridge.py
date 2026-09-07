"""
Merge InvokeAI-style inventory (CSV export) into Lumax dream catalog entries.

Optional env:
  FoveAI_INVOKEAI_MODELS_CSV — path to invokeai_models_inventory.csv (default: repo tools/)
  FoveAI_INVOKEAI_MODELS_ROOT — InvokeAI models directory; used with path_relative_models when absolute paths differ by host.
  If unset, we try common locations (Docker /invokeai/models, ~/Program/InvokeAI/models, ~/InvokeAI/models).

After importing models in InvokeAI, refresh the CSV from its SQLite registry::

  python tools/export_invokeai_inventory_from_db.py --models-root <InvokeAI>/models [--db <InvokeAI>/databases/invokeai.db]
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Dict, List

_DEFAULT_TYPES_UPSCALE = frozenset({"spandrel_image_to_image"})


def merge_invoke_controlnets_enabled() -> bool:
    """Default: merge SD1.x ControlNet rows from CSV. Opt out with FoveAI_INVOKEAI_MERGE_CONTROLNETS=0|false."""

    v = os.getenv("FoveAI_INVOKEAI_MERGE_CONTROLNETS", "1").strip().lower()

    return v not in ("0", "false", "no", "off")


def effective_invoke_models_root() -> str:
    """
    Resolve InvokeAI models root: explicit env first, then well-known paths.
    In Docker, bind-mount the host InvokeAI models dir to /invokeai/models (see docker-compose).
    """
    raw = os.getenv("FoveAI_INVOKEAI_MODELS_ROOT", "").strip()
    if raw:
        return _norm_path(raw)
    candidates = [
        Path("/invokeai/models"),
        Path.home() / "Program" / "InvokeAI" / "models",
        Path.home() / "InvokeAI" / "models",
    ]
    for c in candidates:
        p = str(c)
        if p and os.path.isdir(p):
            return _norm_path(p)
    return ""


def _default_csv_path(creative_dir: str) -> str:
    repo_root = os.path.abspath(os.path.join(creative_dir, "..", "..", ".."))
    return os.path.join(repo_root, "tools", "invokeai_models_inventory.csv")


def _norm_path(p: str) -> str:
    return os.path.normpath(os.path.expandvars(os.path.expanduser(p.strip())))


def _resolve_row_checkpoint_path(
    row: Dict[str, str],
    invoke_root: str,
    *,
    expect_dir: bool = False,
) -> str:
    """Prefer path under FoveAI_INVOKEAI_MODELS_ROOT + relative path; then path_absolute."""
    rel = (row.get("path_relative_models") or "").strip()
    abs_csv = (row.get("path_absolute") or "").strip()
    candidates: List[str] = []
    if invoke_root and rel:
        rel_clean = rel.replace("\\\\", os.sep).replace("\\", os.sep).replace("/", os.sep)
        candidates.append(_norm_path(os.path.join(invoke_root, rel_clean)))
    if abs_csv:
        candidates.append(_norm_path(abs_csv))

    def ok(p: str) -> bool:
        if not p:
            return False
        return os.path.isdir(p) if expect_dir else os.path.isfile(p)

    for c in candidates:
        if ok(c):
            return c
    # Do not return a non-existent path: callers merge catalog entries and must not
    # store bogus paths (avoids os.path / diffusers / Spandrel errors on None-like paths).
    return ""


def _read_csv_rows(csv_path: str) -> List[Dict[str, str]]:
    if not csv_path or not os.path.isfile(csv_path):
        return []
    rows: List[Dict[str, str]] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def merge_invoke_upscalers_from_csv(
    base_upscalers: List[Dict[str, Any]],
    creative_dir: str,
) -> List[Dict[str, Any]]:
    """Append Spandrel upscalers from inventory CSV as catalog-shaped dicts."""
    csv_path = _norm_path(os.getenv("FoveAI_INVOKEAI_MODELS_CSV", "").strip() or _default_csv_path(creative_dir))
    invoke_root = effective_invoke_models_root()
    rows = _read_csv_rows(csv_path)
    if not rows:
        return list(base_upscalers)

    seen: set[str] = {str(u.get("id") or "") for u in base_upscalers}
    out: List[Dict[str, Any]] = list(base_upscalers)

    for row in rows:
        mtype = (row.get("type") or "").strip()
        if mtype not in _DEFAULT_TYPES_UPSCALE:
            continue
        uid = (row.get("id") or "").strip()
        name = (row.get("name") or uid or "upscaler").strip()
        if not uid:
            continue
        eid = f"invoke-upscale-{uid}"
        if eid in seen:
            continue
        resolved = _resolve_row_checkpoint_path(row, invoke_root, expect_dir=False)
        if not resolved or not os.path.isfile(resolved):
            continue
        ent: Dict[str, Any] = {
            "id": eid,
            "name": name,
            "backend": "spandrel",
            "scale": None,
            "path": resolved,
            "path_is_relative_to_imagen_root": False,
            "invoke_type": mtype,
            "invoke_uuid": uid,
            "source": "invokeai_inventory_csv",
            "description": (row.get("description") or "").strip(),
        }
        out.append(ent)
        seen.add(eid)

    return out


def merge_invoke_controlnets_from_csv(
    base_controlnets: List[Dict[str, Any]],
    creative_dir: str,
) -> List[Dict[str, Any]]:
    """
    Optional: add SD1.x ControlNet diffusers folders from CSV (same schema as foveai_imagen_catalog).
    Skips entries whose resolved path is not a directory or duplicates an existing id.
    """
    if not merge_invoke_controlnets_enabled():
        return list(base_controlnets)

    csv_path = _norm_path(os.getenv("FoveAI_INVOKEAI_MODELS_CSV", "").strip() or _default_csv_path(creative_dir))
    invoke_root = effective_invoke_models_root()
    rows = _read_csv_rows(csv_path)
    if not rows:
        return list(base_controlnets)

    seen: set[str] = {str(c.get("id") or "") for c in base_controlnets}
    out: List[Dict[str, Any]] = list(base_controlnets)

    for row in rows:
        mtype = (row.get("type") or "").strip()
        if mtype != "controlnet":
            continue
        base = (row.get("base") or "").strip().lower()
        if base not in ("sd-1", "sd_1", "sd1"):
            continue
        uid = (row.get("id") or "").strip()
        name = (row.get("name") or uid or "controlnet").strip()
        if not uid:
            continue
        eid = f"invoke-cn-{uid}"
        if eid in seen:
            continue
        resolved = _resolve_row_checkpoint_path(row, invoke_root, expect_dir=True)
        if not resolved or not os.path.isdir(resolved):
            continue
        fmt = (row.get("format") or "").strip().lower()
        if fmt != "diffusers":
            continue
        ent: Dict[str, Any] = {
            "id": eid,
            "name": name,
            "base": "sd-1",
            "type": "controlnet",
            "path": resolved,
            "path_is_relative_to_imagen_root": False,
            "preprocessor_default": "canny",
            "description": (row.get("description") or "").strip() or "Imported from InvokeAI inventory CSV.",
            "source": "invokeai_inventory_csv",
        }
        out.append(ent)
        seen.add(eid)

    return out
