"""
Codebase Pruning & Distillation Engine (pruner.py)
Scans FEATURE_INVENTORY.md for [OBSOLETE] features, distills their wisdom,
appends them to FoveAI.md, and moves the physical files to /archive/.
"""

import os
import re
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple

logger = logging.getLogger("forge.pruner")

# Resolve root path dynamically
REPO_ROOT = Path(os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent))
INVENTORY_PATH = REPO_ROOT / "FEATURE_INVENTORY.md"
FoveAI_MD_PATH = REPO_ROOT / "FoveAI.md"
ARCHIVE_ROOT = REPO_ROOT / "archive"

# Set up feature inventory parser path
import sys
xr_vessel = REPO_ROOT / "Frontend" / "XR_Vessel"
if str(xr_vessel) not in sys.path:
    sys.path.insert(0, str(xr_vessel))

# Whitelist of keywords/patterns that should NEVER be archived/pruned
PROTECTED_KEYWORDS = [
    "album_art",
    "creative",
    "creativity",
    "soundboard",
    "homecore",
    "home_core",
    "consent",
    "oauth",
    "profile",
    "blueprint",
    "weaver",
    "multivision",
    "spatial",
    "vessel",
    "budget",
    "ollama",
    "relay",
    "spandrel",
    "invokeai",
    "tokenslayer",
    "stardust",
    "concordia"
]

def is_protected(path_str: str) -> bool:
    """Check if the path matches protected keywords or is in protected directories."""
    path_lower = path_str.lower()
    for keyword in PROTECTED_KEYWORDS:
        if keyword in path_lower:
            return True
    return False


def get_obsolete_features() -> List[Dict[str, Any]]:
    """Parse inventory and find all rows marked [OBSOLETE]."""
    if not INVENTORY_PATH.exists():
        logger.error(f"Inventory file not found: {INVENTORY_PATH}")
        return []
    
    try:
        from feature_inventory_parser import parse_feature_inventory_markdown
        content = INVENTORY_PATH.read_text(encoding="utf-8")
        parsed = parse_feature_inventory_markdown(content)
        flat_rows = parsed.get("flat_rows", [])
        
        obsolete_rows = []
        for row in flat_rows:
            notes = row.get("notes", "")
            if "[OBSOLETE]" in notes.upper() or "OBSOLETE" in notes.upper():
                obsolete_rows.append(row)
        
        return obsolete_rows
    except Exception as e:
        logger.exception(f"Failed to parse obsolete features: {e}")
        return []

def extract_path_from_label(label: str) -> Tuple[str, bool]:
    """Extract path from label, stripping backticks and markdown formatting."""
    # Matches `path/to/file`
    m = re.search(r'`([^`]+)`', label)
    if m:
        return m.group(1).strip(), True
    
    # Fallback to standard path characters
    path_chars = r'[\w/\\.\-]+'
    m_path = re.search(path_chars, label)
    if m_path:
        return m_path.group(0).strip(), False
        
    return label.strip(), False

def distill_wisdom(file_path: Path) -> str:
    """Heuristic summarizer that extracts comments/docstrings to create a single-sentence technical truth."""
    name = file_path.name
    rel_path = file_path.relative_to(REPO_ROOT).as_posix()
    
    if file_path.is_dir():
        return f"Directory `{rel_path}` managed local caches and data schemas for retired subsystems."
        
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Retired legacy component `{rel_path}` was moved to archives."
        
    # Heuristics for Python docstring
    if file_path.suffix == ".py":
        # Look for triple quoted docstrings at the top
        m = re.search(r'^\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', content, re.DOTALL)
        if m:
            doc = m.group(1).strip().replace("\n", " ")
            sentences = [s.strip() for s in doc.split(".") if s.strip()]
            if sentences:
                return f"Module `{name}`: {sentences[0]}."
        
        # Look for leading comments
        comments = []
        for line in content.splitlines()[:15]:
            if line.strip().startswith("#"):
                comments.append(line.strip("#").strip())
        if comments:
            return f"Module `{name}`: {' '.join(comments[:2])}."
            
        return f"Module `{name}` provided internal operations and utility functions for system integration."

    # Heuristics for PowerShell
    elif file_path.suffix == ".ps1":
        # Look for help block or leading comments
        comments = []
        for line in content.splitlines()[:20]:
            if line.strip().startswith("#"):
                comments.append(line.strip("#").strip())
        if comments:
            return f"Script `{name}`: {' '.join(comments[:2])}."
        return f"Orchestration script `{name}` managed service configurations and process controls."

    # General file
    return f"Component `{name}` resolved local configuration parameters and operational states."

def append_wisdom_to_foveai_md(wisdom_line: str):
    """Append distilled wisdom to FoveAI.md under Historical Distillation Layer."""
    if not FoveAI_MD_PATH.exists():
        logger.error(f"FoveAI.md not found: {FoveAI_MD_PATH}")
        return
        
    content = FoveAI_MD_PATH.read_text(encoding="utf-8")
    
    section_header = "## Historical Distillation Layer"
    section_exists = section_header in content
    
    new_wisdom = f"- {wisdom_line}\n"
    
    if section_exists:
        # Insert bullet point under existing header
        pattern = rf"({re.escape(section_header)}[^\n]*\n(?:[^\n]*\n)*?)(?:\n\n|\n---|\Z)"
        match = re.search(pattern, content)
        if match:
            target = match.group(1)
            # Add line before end of section
            replacement = target + new_wisdom
            new_content = content.replace(target, replacement)
        else:
            new_content = content + f"\n{new_wisdom}"
    else:
        # Create new section at the end of the file
        new_content = content.rstrip() + f"\n\n## Historical Distillation Layer\n*Enduring truths distilled from archived legacy components.*\n\n{new_wisdom}"
        
    FoveAI_MD_PATH.write_text(new_content, encoding="utf-8")
    logger.info("Distilled wisdom appended to FoveAI.md")

def remove_from_inventory(label: str) -> bool:
    """Remove the obsolete row from FEATURE_INVENTORY.md."""
    if not INVENTORY_PATH.exists():
        return False
        
    content = INVENTORY_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    new_lines = []
    removed = False
    
    for line in lines:
        if line.strip().startswith("|") and label in line:
            logger.info(f"Removing inventory row: {line}")
            removed = True
            continue
        new_lines.append(line)
        
    if removed:
        INVENTORY_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        
    return removed

def run_prune(dry_run: bool = False) -> Dict[str, Any]:
    """Execute the pruning pipeline on all [OBSOLETE] features."""
    results = {
        "success": True,
        "dry_run": dry_run,
        "archived": [],
        "errors": []
    }
    
    obsolete_features = get_obsolete_features()
    if not obsolete_features:
        logger.info("No obsolete features found to prune.")
        return results
        
    for feature in obsolete_features:
        label = feature.get("label", "")
        notes = feature.get("notes", "")
        
        path_str, is_exact = extract_path_from_label(label)
        src_path = REPO_ROOT / path_str
        
        if is_protected(path_str):
            logger.warning(f"SKIPPING archiving for protected feature: {label} (resolved path: {src_path})")
            continue
            
        logger.info(f"Pruning candidate: {label} (resolved path: {src_path})")
        
        if not src_path.exists():
            # If path not found, we still remove it from inventory
            msg = f"Path {path_str} does not exist on disk, skipping physical move but cleaning inventory."
            logger.warning(msg)
            results["errors"].append(msg)
            if not dry_run:
                remove_from_inventory(label)
            continue
            
        try:
            # 1. Distill wisdom
            wisdom = distill_wisdom(src_path)
            
            # 2. Archive location
            dest_path = ARCHIVE_ROOT / path_str
            
            if dry_run:
                logger.info(f"[DRY RUN] Would archive {src_path} to {dest_path}")
                logger.info(f"[DRY RUN] Wisdom: {wisdom}")
                results["archived"].append({
                    "label": label,
                    "src": str(src_path),
                    "dest": str(dest_path),
                    "wisdom": wisdom
                })
                continue
                
            # Perform action
            # Create archive parent folder
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Append wisdom to FoveAI.md
            append_wisdom_to_foveai_md(wisdom)
            
            # Move physical file/folder
            if src_path.is_dir():
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(src_path, dest_path)
                shutil.rmtree(src_path)
            else:
                shutil.move(str(src_path), str(dest_path))
                
            # Update inventory
            remove_from_inventory(label)
            
            logger.info(f"Successfully archived {label}")
            results["archived"].append({
                "label": label,
                "src": str(src_path),
                "dest": str(dest_path),
                "wisdom": wisdom
            })
            
        except Exception as e:
            msg = f"Error pruning {label}: {e}"
            logger.exception(msg)
            results["errors"].append(msg)
            results["success"] = False
            
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pruner Command Line Interface")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry-run preview")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    res = run_prune(dry_run=args.dry_run)
    print(res)
