#!/usr/bin/env python3
"""Clean FEATURE_INVENTORY.md — Ultra-conservative, only remove obvious junk"""
import re
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).parent.parent
INVENTORY = REPO / "FEATURE_INVENTORY.md"
BACKUP = REPO / ".logs" / f"FEATURE_INVENTORY_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

# ONLY these patterns are removed (explicit junk)
JUNK_PATTERNS = [
    r'GET /src/{path:path}',      # Vite internal
    r'GET /@vite/{path:path}',    # Vite internal  
    r'GET /@id/{path:path}',      # Vite internal
    r'GET /@react-refresh',       # Vite internal
    r'GET /node_modules/{path:path}',  # Vite internal
]

def is_junk(line):
    """Check if line is explicit junk."""
    if not line.strip().startswith('|'):
        return False
    if '---' in line or 'Feature / capability' in line:
        return False
    for pattern in JUNK_PATTERNS:
        if pattern in line:
            return True
    return False

def clean_inventory(dry_run=True):
    if not INVENTORY.exists():
        print(f"ERROR: {INVENTORY} not found")
        return 0, 0
    
    if not dry_run:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(INVENTORY.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup: {BACKUP.name}\n")
    
    content = INVENTORY.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    cleaned = []
    removed = 0
    kept = 0
    
    for line in lines:
        if is_junk(line):
            removed += 1
            if dry_run:
                print(f"  - {line[:70]}...")
        else:
            cleaned.append(line)
            kept += 1
    
    if not dry_run:
        INVENTORY.write_text("\n".join(cleaned), encoding="utf-8")
    
    return kept, removed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    
    dry_run = not args.apply
    print(f"Cleaning {INVENTORY.name} ({'DRY RUN' if dry_run else 'APPLY'})\n")
    
    kept, removed = clean_inventory(dry_run)
    
    print(f"\nKept: {kept} | Removed: {removed}")
    
    if dry_run and removed > 0:
        print("\nApply with: python Scripts/clean_inventory.py --apply")
