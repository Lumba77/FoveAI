#!/usr/bin/env python3
"""
self-edit-rollback.py — inspect and roll back FoveAI self-edits.

Every <self:edit>/<self:codedit> the agent applies snapshots the file's
original content first (journal: Backend/data/self_edits/edits.jsonl).
This tool lists those edits and restores files — deliberately standalone,
no Brain imports, so it works even if the backend is broken.

    self-edit-rollback.py --list            # show journal
    self-edit-rollback.py --undo            # roll back most recent edit
    self-edit-rollback.py --undo <edit_id>  # roll back a specific edit
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOURNAL = os.path.join(ROOT, "Backend", "data", "self_edits", "edits.jsonl")


def _load():
    if not os.path.exists(JOURNAL):
        return []
    with open(JOURNAL, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _save(entries):
    with open(JOURNAL, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in entries)


def list_edits():
    entries = _load()
    if not entries:
        print("No self-edits recorded yet.")
        return
    for e in entries:
        mark = " [ROLLED BACK]" if e.get("rolled_back") else ""
        print(
            f"{e['id']}  {e['ts'][:19]}  {e.get('actor', 'self'):10}  {e['file']}{mark}"
        )


def undo(edit_id=None):
    entries = _load()
    target = (
        next((e for e in entries if e.get("id") == edit_id), None)
        if edit_id
        else next((e for e in reversed(entries) if not e.get("rolled_back")), None)
    )
    if not target:
        sys.exit(f"No matching edit{': ' + edit_id if edit_id else ''}.")
    if target.get("rolled_back"):
        sys.exit(f"Edit {target['id']} was already rolled back.")
    if not os.path.exists(target["snapshot"]):
        sys.exit(f"Snapshot file missing for {target['id']}.")
    full = os.path.join(ROOT, target["file"])
    with open(target["snapshot"], "rb") as src, open(full, "wb") as dst:
        dst.write(src.read())
    target["rolled_back"] = True
    _save(entries)
    print(f"Rolled back {target['file']} to pre-edit state ({target['id']}).")


def main():
    ap = argparse.ArgumentParser(description="Roll back FoveAI self-edits")
    ap.add_argument("--list", action="store_true", help="list recorded self-edits")
    ap.add_argument(
        "--undo",
        nargs="?",
        const="",
        metavar="EDIT_ID",
        help="roll back most recent edit, or a specific edit id",
    )
    args = ap.parse_args()

    if args.list:
        list_edits()
    elif args.undo is not None:
        undo(args.undo or None)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
