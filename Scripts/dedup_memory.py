#!/usr/bin/env python3
"""Deduplicate FoveAI memory_index.json — remove duplicate conversation entries."""

import json
import os
from datetime import datetime
from pathlib import Path

MEMORY_PATH = (
    Path(os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent))
    / ".logs"
    / "memory_index.json"
)

with open(MEMORY_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

convs = data.get("conversations", [])
before = len(convs)
print(f"Before: {before} entries")

# Dedup: keep most recent entry per role+content_prefix (200 chars)
seen = {}
unique = []
for entry in reversed(convs):
    role = entry.get("role", "")
    content = entry.get("content", "")
    prefix = content[:200] if content else ""
    key = f"{role}::{prefix}"
    if key not in seen:
        seen[key] = True
        unique.append(entry)

unique.reverse()
removed = before - len(unique)
print(f"After: {len(unique)} entries (removed {removed} duplicates)")

data["conversations"] = unique
data["last_updated"] = datetime.now().isoformat()
with open(MEMORY_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("Saved!")

# Also dedup docs_index.json
DOCS_PATH = (
    Path(os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent))
    / ".logs"
    / "docs_index.json"
)
if DOCS_PATH.exists():
    with open(DOCS_PATH, "r", encoding="utf-8") as f:
        docs_data = json.load(f)
    docs = docs_data.get("docs", [])
    before_docs = len(docs)
    # Dedup by source+chunk
    seen_docs = {}
    unique_docs = []
    for doc in docs:
        key = f"{doc.get('source', '')}::{doc.get('chunk', 0)}"
        if key not in seen_docs:
            seen_docs[key] = True
            unique_docs.append(doc)
    docs_data["docs"] = unique_docs
    docs_data["updated"] = datetime.now().isoformat()
    with open(DOCS_PATH, "w", encoding="utf-8") as f:
        json.dump(docs_data, f, indent=2, ensure_ascii=False)
    print(
        f"Docs: {before_docs} -> {len(unique_docs)} (removed {before_docs - len(unique_docs)} duplicates)"
    )
else:
    print("No docs_index.json found")
