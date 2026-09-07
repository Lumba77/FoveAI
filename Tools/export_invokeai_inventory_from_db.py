#!/usr/bin/env python3
"""
Export InvokeAI's SQLite model registry to tools/invokeai_models_inventory.csv.

After you import or install models in InvokeAI, run this so Lumax can merge
ControlNet + Spandrel entries via backend/Creativity/invokeai_catalog_bridge.py
(FoveAI_INVOKEAI_MODELS_CSV / FoveAI_INVOKEAI_MODELS_ROOT).

Examples:
  python tools/export_invokeai_inventory_from_db.py
  python tools/export_invokeai_inventory_from_db.py --db "C:/InvokeAI/databases/invokeai.db" \\
      --models-root "C:/InvokeAI/models" --out tools/invokeai_models_inventory.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CSV_FIELDS = [
    "id",
    "name",
    "type",
    "base",
    "format",
    "path_relative_models",
    "path_absolute",
    "on_disk",
    "source",
    "source_type",
    "description",
]


def _norm(p: str) -> str:
    return os.path.normpath(os.path.expandvars(os.path.expanduser(p.strip())))


def _is_abs_path(p: str) -> bool:
    if not p:
        return False
    p2 = p.replace("/", os.sep)
    if len(p2) >= 2 and p2[1] == ":":
        return True
    return p2.startswith(os.sep)


def _resolve_model_path(models_root: str, path_field: str) -> str:
    raw = (path_field or "").strip().replace("\\", "/")
    if not raw:
        return ""
    raw_os = raw.replace("/", os.sep)
    if _is_abs_path(raw_os):
        return _norm(raw_os)
    return _norm(os.path.join(models_root, raw_os))


def _default_models_root() -> Optional[str]:
    for key in ("FoveAI_INVOKEAI_MODELS_HOST", "FoveAI_INVOKEAI_MODELS_ROOT"):
        v = os.getenv(key, "").strip()
        if v and os.path.isdir(_norm(v)):
            return _norm(v)
    for c in (
        Path.home() / "Program" / "InvokeAI" / "models",
        Path.home() / "InvokeAI" / "models",
    ):
        if c.is_dir():
            return str(c.resolve())
    return None


def _default_db(models_root: str) -> str:
    parent = Path(models_root).resolve().parent
    return str(parent / "databases" / "invokeai.db")


def _legacy_model_config_rows(conn: sqlite3.Connection) -> List[Tuple[str, Dict[str, Any]]]:
    """InvokeAI 3.x-style flat table, if present."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='model_config'"
    )
    if not cur.fetchone():
        return []
    rows = []
    cur = conn.execute("SELECT * FROM model_config")
    colnames = [d[0] for d in cur.description]
    for tup in cur.fetchall():
        rec = dict(zip(colnames, tup))
        mid = str(rec.get("id") or rec.get("key") or "").strip()
        if not mid:
            continue
        cfg = {k: rec[k] for k in rec if k not in ("id", "key")}
        rows.append((mid, cfg))
    return rows


def _modern_models_rows(conn: sqlite3.Connection) -> List[Tuple[str, Dict[str, Any]]]:
    cur = conn.execute("SELECT id, config FROM models")
    out: List[Tuple[str, Dict[str, Any]]] = []
    for mid, cfg_json in cur.fetchall():
        try:
            cfg = json.loads(cfg_json)
        except json.JSONDecodeError:
            continue
        out.append((str(mid), cfg))
    return out


def export_rows(models_root: str, rows: List[Tuple[str, Dict[str, Any]]]) -> List[Dict[str, str]]:
    mr = _norm(models_root)
    out: List[Dict[str, str]] = []
    for mid, cfg in rows:
        path_field = str(cfg.get("path") or "").strip()
        resolved = _resolve_model_path(mr, path_field)
        rel_models = ""
        abs_out = ""
        if resolved:
            abs_out = resolved
            try:
                common = os.path.commonpath([_norm(resolved), mr])
            except ValueError:
                common = ""
            if common == mr:
                rel_models = os.path.relpath(resolved, mr)
            elif not _is_abs_path(path_field):
                rel_models = path_field.replace("/", os.sep)
            else:
                rel_models = ""

        on_disk = bool(resolved) and (os.path.isfile(resolved) or os.path.isdir(resolved))
        name = str(cfg.get("name") or mid).strip()
        desc = str(cfg.get("description") or "").strip()
        out.append(
            {
                "id": mid,
                "name": name,
                "type": str(cfg.get("type") or "").strip(),
                "base": str(cfg.get("base") or "").strip(),
                "format": str(cfg.get("format") or "").strip(),
                "path_relative_models": rel_models,
                "path_absolute": abs_out,
                "on_disk": "True" if on_disk else "False",
                "source": str(cfg.get("source") or "").strip(),
                "source_type": str(cfg.get("source_type") or "").strip(),
                "description": desc,
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Export InvokeAI models table to Lumax inventory CSV.")
    ap.add_argument(
        "--models-root",
        default="",
        help="InvokeAI models directory (folder containing UUID subfolders). "
        "Default: FoveAI_INVOKEAI_MODELS_HOST / FoveAI_INVOKEAI_MODELS_ROOT or ~/Program/InvokeAI/models.",
    )
    ap.add_argument(
        "--db",
        default="",
        help="Path to invokeai.db. Default: <parent of models-root>/databases/invokeai.db",
    )
    ap.add_argument(
        "--out",
        default="",
        help="Output CSV path. Default: repo tools/invokeai_models_inventory.csv",
    )
    args = ap.parse_args()

    models_root = _norm(args.models_root) if args.models_root.strip() else _default_models_root()
    if not models_root or not os.path.isdir(models_root):
        print("Could not resolve InvokeAI models directory. Set --models-root or FoveAI_INVOKEAI_MODELS_HOST.", file=sys.stderr)
        return 2

    db_path = _norm(args.db) if args.db.strip() else _default_db(models_root)
    if not os.path.isfile(db_path):
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    out_path = Path(_norm(args.out)) if args.out.strip() else repo_root / "tools" / "invokeai_models_inventory.csv"

    conn = sqlite3.connect(db_path)
    try:
        rows = _modern_models_rows(conn)
        if not rows:
            rows = _legacy_model_config_rows(conn)
    finally:
        conn.close()

    if not rows:
        print("No model rows found in database.", file=sys.stderr)
        return 3

    csv_rows = export_rows(models_root, rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in csv_rows:
            w.writerow(r)

    on = sum(1 for r in csv_rows if r["on_disk"] == "True")
    print(f"Wrote {len(csv_rows)} rows ({on} on_disk) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
