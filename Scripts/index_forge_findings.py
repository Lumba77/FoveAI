#!/usr/bin/env python3
"""Forge Meaningful Saves — Update FEATURE_INVENTORY.md"""
import json, re
from pathlib import Path

REPO = Path(__file__).parent.parent
REPORTS = REPO / ".logs" / "discovery_reports"
INVENTORY = REPO / "FEATURE_INVENTORY.md"

CATEGORY_MAP = {
    "frontend/Mouth": ("2. Unified XR Vessel", "A"),
    "frontend/Physical_Interface": ("2. Unified XR Vessel", "A"),
    "frontend/XR_Vessel": ("2. Unified XR Vessel", "A"),
    "backend/Cognition": ("3. Backend", "A"),
    "backend/Memory": ("3. Backend", "A"),
    "Forge": ("7. Ops & scripts", "B"),
}

SKIP_PATTERNS = ["__", "test_", "mock_", "temp_", "@", "node_modules", "BaseModel", "Request", "Response", "Config"]
REQUIRED_MARKERS = ["/api/", "/chat", "/voice", "/stt", "/tts", "/soul", "/memory", "/auth", "/swarm", "/dream", "/code", "/dev", "/mouth", "/monetize", "/consent", "/creativity", "/forge"]

def find_latest():
    files = sorted(REPORTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def is_meaningful(f):
    name, source, ftype = f.get("name", ""), f.get("source_file", ""), f.get("feature_type", "")
    if ftype not in ["endpoint", "service", "class"]:
        return False
    if any(p in name for p in SKIP_PATTERNS):
        return False
    if not any(m in source.lower() or m in name.lower() for m in REQUIRED_MARKERS):
        return False
    return True

def get_category(source):
    for prefix, (cat, tier) in CATEGORY_MAP.items():
        if prefix in source:
            return cat, tier
    return None, None

def format_row(feat):
    name, source = feat.get("name", ""), feat.get("source_file", "")
    cat, tier = get_category(source)
    if not cat:
        return None, None
    desc = feat.get("description", "").replace("Python class", "").replace("FastAPI endpoint", "").strip("` ")
    notes = f"`{source}` — {desc}" if desc else f"`{source}`"
    return cat, f"| `{name}` | **{tier}** | {notes} |"

def update_inventory(features):
    content = INVENTORY.read_text(encoding="utf-8") if INVENTORY.exists() else ""
    added = 0
    
    for feat in features:
        cat, row = format_row(feat)
        if not row or feat.get("name") in content:
            continue
        
        # Find section
        pattern = rf"##\s*{re.escape(cat)}.*?\n\n"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            continue
        
        section = content[:match.end()]
        lines = section.rstrip().split("\n")
        
        # Find insert position after table separator
        for i in range(len(lines)-1, -1, -1):
            if "|" in lines[i] and "---" in lines[i]:
                insert_pos = len("\n".join(lines[:i+1])) + 1
                break
        else:
            insert_pos = match.end()
        
        content = content[:insert_pos] + row + "\n" + content[insert_pos:]
        added += 1
        print(f"  + {cat}: {feat.get('name')}")
    
    if added:
        INVENTORY.write_text(content, encoding="utf-8")
    print(f"\nIndexed {added} new meaningful saves")

if __name__ == "__main__":
    r = find_latest()
    if not r:
        print("No reports")
        exit(1)
    
    data = json.loads(r.read_text())
    worthy = [f for f in data.get("new_features", []) if is_meaningful(f)]
    print(f"Found {len(worthy)} meaningful saves from {r.name}\n")
    update_inventory(worthy)
