#!/usr/bin/env python3
"""
XRL MCP Bridge — Python interface for XRL pipeline

Calls xrl.cjs as subprocess, returns JSON results.
Provides functions for loading, expanding, searching, and getting stats on XRL files.

Usage:
    from xrl_mcp_bridge import load_xrl, expand_xrl, search_xrl, get_xrl_stats

    # Load an XRB file
    data = load_xrl("service.xrb")

    # Expand a specific block
    block = expand_xrl("service.py", "fn authenticate")

    # Search across XRL files
    results = search_xrl(["./src"], "UserService")

    # Get statistics
    stats = get_xrl_stats("service.py", depth=2)
"""

import json
import subprocess
from pathlib import Path
from typing import Any

# ─── Path Configuration ───────────────────────────────────────────

# Path to the xrl.cjs CLI
XRL_CLI = Path(__file__).parent / "xrl.cjs"
XRS_CLI = Path(__file__).parent / "xrs.cjs"

# ─── Subprocess Helper ────────────────────────────────────────────


def _run_xrl(args: list[str], timeout: int = 30) -> dict[str, Any]:
    """
    Run xrl.cjs with given arguments and parse JSON output.

    Args:
        args: List of command-line arguments
        timeout: Timeout in seconds (default: 30)

    Returns:
        Parsed JSON result as dictionary

    Raises:
        RuntimeError: If the subprocess fails or returns invalid JSON
    """
    cmd = ["node", str(XRL_CLI)] + args

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=True
        )

        # Parse JSON from stdout
        output = result.stdout.strip()
        if not output:
            return {"error": "No output from xrl.cjs"}

        return json.loads(output)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"xrl.cjs timed out after {timeout}s")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"xrl.cjs failed: {error_msg}")

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse xrl.cjs output: {e}\nOutput: {output}")


def _run_xrs(args: list[str], timeout: int = 30) -> dict[str, Any]:
    """
    Run xrs.cjs with given arguments and parse JSON output.

    Args:
        args: List of command-line arguments
        timeout: Timeout in seconds (default: 30)

    Returns:
        Parsed JSON result as dictionary
    """
    cmd = ["node", str(XRS_CLI)] + args

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=True
        )

        output = result.stdout.strip()
        if not output:
            return {"error": "No output from xrs.cjs"}

        return json.loads(output)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"xrs.cjs timed out after {timeout}s")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"xrs.cjs failed: {error_msg}")

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse xrs.cjs output: {e}")


# ─── Public API ──────────────────────────────────────────────────


def load_xrl(filepath: str | Path, depth: int = 2) -> dict[str, Any]:
    """
    Load an XRL file (source or XRB binary) and return parsed data.

    Args:
        filepath: Path to source file or .xrb binary
        depth: Skeletonization depth (0-3, default: 2)

    Returns:
        Dictionary with file metadata, skeleton, tokens, and blocks

    Examples:
        >>> data = load_xrl("service.py", depth=2)
        >>> print(data["skeleton"]["tokens"])
        849
    """
    filepath = str(filepath)

    # Check if it's an XRB binary
    if filepath.endswith(".xrb"):
        return _run_xrl([filepath, "--validate", "--json"])

    # It's a source file — run full pipeline
    return _run_xrl([filepath, "--depth", str(depth), "--json"])


def expand_xrl(
    filepath: str | Path, block_name: str, depth: int = 2
) -> dict[str, Any]:
    """
    Expand a specific block (function/class) from a source file.

    Args:
        filepath: Path to source file
        block_name: Name of the block to expand (e.g., "fn authenticate")
        depth: Skeletonization depth (0-3, default: 2)

    Returns:
        Dictionary with expanded block content

    Examples:
        >>> block = expand_xrl("service.py", "fn authenticate")
        >>> print(block["expansion"]["content"])
    """
    filepath = str(filepath)
    return _run_xrl([filepath, "--depth", str(depth), "--expand", block_name, "--json"])


def search_xrl(
    directories: list[str | Path], query: str, depth: int = 2
) -> list[dict[str, Any]]:
    """
    Search across multiple XRL files for matching content.

    Args:
        directories: List of directory paths to search
        query: Search query (function name, class name, etc.)
        depth: Skeletonization depth (0-3, default: 2)

    Returns:
        List of matching results with file info and context

    Examples:
        >>> results = search_xrl(["./src"], "UserService")
        >>> for r in results:
        ...     print(f"{r['file']}: {r['block']}")
    """
    results = []
    source_extensions = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".cjs",
        ".mjs",
        ".go",
        ".rs",
        ".java",
        ".cs",
        ".kt",
        ".swift",
        ".html",
        ".css",
        ".scss",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".rb",
        ".php",
        ".lua",
        ".sh",
        ".bat",
        ".ps1",
    }

    skip_dirs = {
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        ".idea",
        ".vscode",
        "dist",
        "build",
        ".logs",
        "archive",
        "chroma_db",
        "kuzu_db",
        "Data",
        "storage",
        "models",
    }

    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            continue

        for filepath in dir_path.rglob("*"):
            if filepath.suffix.lower() not in source_extensions:
                continue
            if any(part in skip_dirs for part in filepath.parts):
                continue

            try:
                data = load_xrl(filepath, depth)

                # Check blocks for matches
                for block in data.get("blocks", []):
                    if query.lower() in block.get("name", "").lower():
                        results.append(
                            {
                                "file": str(filepath),
                                "block": block["name"],
                                "type": block.get("type", "unknown"),
                                "signature": block.get("signature", ""),
                                "token_count": block.get("tokenCount", 0),
                            }
                        )

                # Also check skeleton content
                skeleton = data.get("skeleton", {}).get("content", "")
                if query.lower() in skeleton.lower():
                    # Add file-level match if not already found
                    if not any(r["file"] == str(filepath) for r in results):
                        results.append(
                            {
                                "file": str(filepath),
                                "block": "(content match)",
                                "type": "file",
                                "signature": "",
                                "token_count": data.get("skeleton", {}).get(
                                    "tokens", 0
                                ),
                            }
                        )

            except (RuntimeError, json.JSONDecodeError):
                continue

    return results


def get_xrl_stats(filepath: str | Path, depth: int = 2) -> dict[str, Any]:
    """
    Get token statistics for a file.

    Args:
        filepath: Path to source file
        depth: Skeletonization depth (0-3, default: 2)

    Returns:
        Dictionary with token statistics

    Examples:
        >>> stats = get_xrl_stats("service.py", depth=2)
        >>> print(f"Original: {stats['originalTokens']}, Skeleton: {stats['skeletonTokens']}")
    """
    filepath = str(filepath)
    return _run_xrl([filepath, "--depth", str(depth), "--stats"])


def skeletonize(filepath: str | Path, depth: int = 2) -> dict[str, Any]:
    """
    Generate XRS skeleton for a file (using xrs.cjs directly).

    Args:
        filepath: Path to source file
        depth: Skeletonization depth (0-3, default: 2)

    Returns:
        Dictionary with skeleton data

    Examples:
        >>> skel = skeletonize("service.py", depth=2)
        >>> print(skel["skeleton"]["content"])
    """
    filepath = str(filepath)
    return _run_xrs([filepath, "--depth", str(depth), "--json"])


def enforce_budget(
    filepath: str | Path, budget: int, depth: int = 2
) -> dict[str, Any]:
    """
    Enforce a token budget on a file.

    Args:
        filepath: Path to source file
        budget: Maximum token count
        depth: Starting skeletonization depth (0-3, default: 2)

    Returns:
        Dictionary with budget enforcement results

    Examples:
        >>> result = enforce_budget("service.py", 500)
        >>> print(f"Selected depth: {result['budget']['depthName']}")
    """
    filepath = str(filepath)
    return _run_xrl(
        [filepath, "--depth", str(depth), "--budget", str(budget), "--json"]
    )


def convert_to_xrb(
    filepath: str | Path, output_path: str | Path, depth: int = 2
) -> dict[str, Any]:
    """
    Convert a source file to XRB binary format.

    Args:
        filepath: Path to source file
        output_path: Path for output .xrb file
        depth: Skeletonization depth (0-3, default: 2)

    Returns:
        Dictionary with conversion results

    Examples:
        >>> result = convert_to_xrb("service.py", "service.xrb")
        >>> print(f"Written {result['binary']['size']} bytes")
    """
    filepath = str(filepath)
    output_path = str(output_path)
    return _run_xrl(
        [filepath, "--depth", str(depth), "--output", output_path, "--json"]
    )


def convert_from_xrb(xrb_path: str | Path, depth: int = 2) -> str:
    """
    Convert XRB binary back to text.

    Args:
        xrb_path: Path to .xrb file
        depth: Depth level for filtering (0-3, default: 2)

    Returns:
        Reconstructed text

    Examples:
        >>> text = convert_from_xrb("service.xrb")
        >>> print(text[:200])
    """
    xrb_path = str(xrb_path)
    result = _run_xrl([xrb_path, "--to-text", "--depth", str(depth), "--json"])
    return result.get("text", "")


# ─── CLI Mode ─────────────────────────────────────────────────────


def main():
    """CLI entry point for the MCP bridge."""
    import argparse

    parser = argparse.ArgumentParser(
        description="XRL MCP Bridge — Python interface for XRL pipeline"
    )
    parser.add_argument(
        "filepath", nargs="?", help="Path to source file or .xrb binary"
    )
    parser.add_argument(
        "--depth", type=int, default=2, help="Skeletonization depth (0-3)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--stats", action="store_true", help="Show token statistics only"
    )
    parser.add_argument("--expand", metavar="NAME", help="Expand a specific block")
    parser.add_argument("--budget", type=int, help="Enforce token budget")
    parser.add_argument("--output", metavar="PATH", help="Write XRB binary to file")
    parser.add_argument(
        "--to-text", action="store_true", help="Convert XRB binary back to text"
    )
    parser.add_argument("--search", metavar="QUERY", help="Search across directories")
    parser.add_argument(
        "--dirs", nargs="+", metavar="DIR", help="Directories to search"
    )

    args = parser.parse_args()

    if args.search:
        # Search mode
        dirs = args.dirs or ["."]
        results = search_xrl(dirs, args.search, args.depth)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\n🔍 Search results for '{args.search}':")
            for r in results:
                print(f"   {r['file']}: {r['block']} ({r['type']})")
        return

    if not args.filepath:
        parser.print_help()
        return

    if args.to_text:
        text = convert_from_xrb(args.filepath, args.depth)
        print(text)
        return

    if args.stats:
        stats = get_xrl_stats(args.filepath, args.depth)
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(f"\n📊 XRL Statistics for {args.filepath}:")
            print(f"   Original tokens: {stats.get('originalTokens', 'N/A')}")
            print(f"   Skeleton tokens: {stats.get('skeletonTokens', 'N/A')}")
            print(f"   Reduction:       {stats.get('textReduction', 'N/A')}")
            print(f"   Binary bytes:    {stats.get('binaryBytes', 'N/A')}")
            print(f"   Binary tokens:   {stats.get('binaryTokens', 'N/A')}")
            print(f"   Blocks:          {stats.get('blockCount', 'N/A')}")
        return

    if args.expand:
        result = expand_xrl(args.filepath, args.expand, args.depth)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n🔍 Expanded Block: {args.expand}")
            print(result.get("expansion", {}).get("content", "Not found"))
        return

    if args.budget:
        result = enforce_budget(args.filepath, args.budget, args.depth)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            budget_info = result.get("budget", {})
            print(f"\n💰 Budget Enforcement for {args.filepath}:")
            print(f"   Target:       {budget_info.get('target', 'N/A')} tokens")
            print(
                f"   Selected:     {budget_info.get('depthName', 'N/A')} (depth {budget_info.get('selectedDepth', 'N/A')})"
            )
            print(f"   Token count:  {budget_info.get('tokenCount', 'N/A')}")
            print(
                f"   Within budget: {'✓' if budget_info.get('withinBudget') else '✗'}"
            )
        return

    if args.output:
        result = convert_to_xrb(args.filepath, args.output, args.depth)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(
                f"Written {result.get('binary', {}).get('size', 0)} bytes to {args.output}"
            )
        return

    # Default: load and display
    result = load_xrl(args.filepath, args.depth)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n📁 XRL Load: {args.filepath}")
        print(f"   Depth: {result.get('depth', 'N/A')}")
        print(f"   Original tokens: {result.get('original', {}).get('tokens', 'N/A')}")
        print(f"   Skeleton tokens: {result.get('skeleton', {}).get('tokens', 'N/A')}")
        print(f"   Binary tokens:   {result.get('binary', {}).get('tokens', 'N/A')}")
        print(
            f"   Binary size:     {result.get('binary', {}).get('size', 'N/A')} bytes"
        )
        print(f"   Blocks:          {len(result.get('blocks', []))}")


if __name__ == "__main__":
    main()
