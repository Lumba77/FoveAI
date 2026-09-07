#!/usr/bin/env python3
"""
generate_repo_skeleton.py — OPTIMIZED for local models
Scans all key source files with TokenSlayer, produces a structural mind map
for injection into every agent's working memory.

Supports multiple tiers:
  --tier micro     (<500 tokens)  — tree + ports + one-line semantic summaries
  --tier standard  (~6.5K tokens) — imports + signatures (current default)
  --tier full      (~25K tokens)  — full file contents (no reduction)

Respects .tokenslayer-ignore for excluding noise files.

Also generates a Dependency Map section showing:
- Cross-file imports (who depends on what)
- Service-to-service communication (which port talks to which)
- API route mappings (endpoint → handler function)

Usage:
    python Scripts/generate_repo_skeleton.py [--tier micro|standard|full]
"""

import subprocess
import os
import fnmatch
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path("C:/Users/danie/program/LUMAX/FoveAI")
OUTPUT = ROOT / "repo-principia.md"
TS = ROOT / "Forge/scratch/TokenSlayer/standalone/tokenslayer.js"
IGNORE_FILE = ROOT / ".xrl-ignore"
if not IGNORE_FILE.exists():
    IGNORE_FILE = ROOT / ".tokenslayer-ignore"

# Parse CLI args
TIER = "standard"  # default
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--tier" and i + 1 < len(sys.argv[1:]):
        TIER = sys.argv[i + 2]
        if TIER not in ("micro", "standard", "full"):
            print(f"Error: --tier must be micro, standard, or full (got {TIER})")
            sys.exit(1)

# Map tier to TokenSlayer level
TIER_TO_LEVEL = {"micro": 4, "standard": 3, "full": 0}
TS_LEVEL = TIER_TO_LEVEL[TIER]


def load_ignore_patterns() -> list:
    """Load glob patterns from .tokenslayer-ignore file."""
    patterns = []
    if IGNORE_FILE.exists():
        for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def is_ignored(rel_path: str, patterns: list) -> bool:
    """Check if a relative path matches any ignore pattern."""
    rel_path = rel_path.replace("\\", "/")
    for pattern in patterns:
        p = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel_path, p):
            return True
        if p.endswith("/") and rel_path.startswith(p):
            return True
        if not p.endswith("/") and not p.endswith("*"):
            if rel_path.startswith(p + "/") or rel_path == p:
                return True
    return False


# All backend service files — organized by directory
BACKEND_FILES = [
    # Cognition (10 files)
    "Backend/Cognition/soul_core.py",
    "Backend/Cognition/tokenslayer_proxy_server.py",
    "Backend/Cognition/motor_cortex.py",
    "Backend/Cognition/intelligent_router.py",
    "Backend/Cognition/autonomous_agent.py",
    "Backend/Cognition/swarm_orchestrator.py",
    "Backend/Cognition/memory.py",
    "Backend/Cognition/ag_coder.py",
    "Backend/Cognition/visualize_architecture.py",
    "Backend/Cognition/visualize_relay.py",
    # Memory (7 files)
    "Backend/Memory/memory_service.py",
    "Backend/Memory/foveai_mcp_server.py",
    "Backend/Memory/smart_context.py",
    "Backend/Memory/import_foveai_sessions.py",
    "Backend/Memory/quantum_neuron.py",
    "Backend/Memory/session_importer.py",
    "Backend/Memory/stardust_encoder.py",
    # Creativity (4 files)
    "Backend/Creativity/creative_service.py",
    "Backend/Creativity/invokeai_catalog_bridge.py",
    "Backend/Creativity/spandrel_upscale.py",
    "Backend/Creativity/start_creative_with_env.py",
    # Monetizing (13 files)
    "Backend/Monetizing/agent_core.py",
    "Backend/Monetizing/coinex_integration.py",
    "Backend/Monetizing/treasury_manager.py",
    "Backend/Monetizing/agent_bookkeeper.py",
    "Backend/Monetizing/idea_engine.py",
    "Backend/Monetizing/machine_state.py",
    "Backend/Monetizing/mentor_analyzer.py",
    "Backend/Monetizing/migrate_to_sqlite.py",
    "Backend/Monetizing/monetizing_db.py",
    "Backend/Monetizing/paper_trading_engine.py",
    "Backend/Monetizing/run_monetizing_system.py",
    "Backend/Monetizing/security.py",
    "Backend/Monetizing/test_real_trading.py",
    # Preflight (3 files — skip __init__.py)
    "Backend/preflight/agentic_solver.py",
    "Backend/preflight/checks.py",
    "Backend/preflight/json_util.py",
]

FORGE_FILES = [
    "Forge/scratch/TokenSlayer/standalone/tokenslayer.js",
    "Forge/scratch/TokenSlayer/mcp-server/build/index.js",
]

# Service port map for dependency analysis
SERVICE_PORTS = {
    "soul_core.py": 8402,
    "memory_service.py": 8002,
    "foveai_mcp_server.py": 8002,
    "creative_service.py": 8003,
    "tokenslayer_proxy_server.py": 8103,
    "smart_context.py": 8104,
}

# Known API route patterns for route mapping
ROUTE_PATTERN = re.compile(r'@(?:app|router)\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']')
IMPORT_PATTERN = re.compile(r'from\s+([.\w]+)\s+import|import\s+([.\w]+)')
HTTP_PATTERN = re.compile(r'(?:httpx|requests|fetch|axios)\.(?:get|post|put|delete)\s*\(\s*["\'](?:http://)?127\.0\.0\.1:(\d+)')


def run_tokenslayer(filepath: Path) -> str:
    """Run TokenSlayer and return ONLY the skeleton lines (no headers/noise)."""
    try:
        result = subprocess.run(
            ["node", str(TS), str(filepath), "--level", str(TS_LEVEL)],
            capture_output=True, text=True, timeout=30,
        )
        lines = result.stdout.splitlines()
        filtered = [
            l for l in lines
            if l.strip()
            and not l.startswith("[TokenSlayer Saved")
            and not l.startswith("Auto-activating")
            and not l.startswith("<previous line")
            and not (l.strip().startswith("//") and "skeleton" in l.lower())
        ]
        return "\n".join(filtered)
    except Exception as e:
        return f"// ERROR: {e}"


def get_compact_tree(ignore_patterns: list) -> str:
    """Minimal directory tree — only key project dirs, respecting ignores."""
    key_dirs = [
        "Backend/Cognition/", "Backend/Memory/", "Backend/Creativity/",
        "Backend/Monetizing/", "Backend/preflight/",
        "Forge/scratch/TokenSlayer/", "Forge/scratch/TokenSlayer/mcp-server/",
        "Frontend/Web/", "Frontend/Webui/",
        "Scripts/", "Tools/", "Docs/", "Plans/", "tests/",
    ]
    filtered = [d for d in key_dirs if not is_ignored(d, ignore_patterns)]
    return "\n".join(f"  {d}" for d in filtered)


def extract_imports(filepath: Path) -> list:
    """Extract import statements from a file for dependency analysis."""
    imports = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        for match in IMPORT_PATTERN.finditer(content):
            imp = match.group(1) or match.group(2)
            if imp and not imp.startswith("__"):
                imports.append(imp)
    except Exception:
        pass
    return imports


def extract_routes(filepath: Path) -> list:
    """Extract API route definitions from a file."""
    routes = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        for match in ROUTE_PATTERN.finditer(content):
            routes.append(match.group(1))
    except Exception:
        pass
    return routes


def extract_http_calls(filepath: Path) -> list:
    """Extract HTTP calls to other services (port numbers)."""
    ports = set()
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        for match in HTTP_PATTERN.finditer(content):
            ports.add(int(match.group(1)))
    except Exception:
        pass
    return sorted(ports)


def extract_one_line_summary(filepath: Path) -> str:
    """Extract a one-line semantic summary from a file's first docstring or module doc."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        # Try to find module-level docstring
        doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if doc_match:
            summary = doc_match.group(1).strip().split('\n')[0][:120]
            return summary
        # Fallback: first comment
        comment_match = re.search(r'#\s*(.+)', content)
        if comment_match:
            return comment_match.group(1).strip()[:120]
    except Exception:
        pass
    return ""


def build_dependency_map(processed_files: dict) -> dict:
    """Build reverse dependency map: which files import which other files."""
    deps = {"imports": {}, "imported_by": {}}
    for rel_path, info in processed_files.items():
        file_imports = info.get("imports", [])
        deps["imports"][rel_path] = file_imports
        for imp in file_imports:
            if imp not in deps["imported_by"]:
                deps["imported_by"][imp] = []
            deps["imported_by"][imp].append(rel_path)
    return deps


def build_service_comm_map(processed_files: dict) -> list:
    """Build service-to-service communication map."""
    comms = []
    for rel_path, info in processed_files.items():
        source_service = Path(rel_path).name
        source_port = SERVICE_PORTS.get(source_service, "?")
        target_ports = info.get("http_calls", [])
        for target_port in target_ports:
            target_service = "?"
            for svc, port in SERVICE_PORTS.items():
                if port == target_port:
                    target_service = svc
                    break
            comms.append(f"  {source_service} ({source_port}) → {target_service} ({target_port})")
    return comms


def build_route_map(processed_files: dict) -> list:
    """Build API route map: endpoint → file."""
    routes = []
    for rel_path, info in processed_files.items():
        for route in info.get("routes", []):
            routes.append(f"  `{route}` → {rel_path}")
    return sorted(routes)


def generate_micro_skeleton(processed_files: dict, ignore_patterns: list) -> str:
    """Generate a micro-skeleton (<500 tokens) with tree + ports + one-line summaries."""
    lines = []
    lines.append("# FoveAI Micro-Skeleton")
    lines.append(f"*{datetime.now().strftime('%Y-%m-%d %H:%M')} | Tier: micro | .tokenslayer-ignore active*\n")

    # Tree
    lines.append("## Tree")
    lines.append(get_compact_tree(ignore_patterns))
    lines.append("")

    # Ports
    lines.append("## Ports")
    lines.append("Soul:8402 | Memory:8002 | MemoryMCP:8002 | Creative:8003 | TSProxy:8103 | WebUI:8080\n")

    # One-line file summaries
    lines.append("## Files")
    for rel_path in BACKEND_FILES + FORGE_FILES:
        if is_ignored(rel_path, ignore_patterns):
            continue
        full_path = ROOT / rel_path
        if full_path.exists():
            summary = extract_one_line_summary(full_path)
            port = SERVICE_PORTS.get(Path(rel_path).name, "")
            port_str = f" ({port})" if port else ""
            if summary:
                lines.append(f"  {rel_path}{port_str} — {summary}")
            else:
                # Fallback: count functions
                content = full_path.read_text(encoding="utf-8", errors="replace")
                func_count = len(re.findall(r'^(?:async\s+)?def\s+\w+|class\s+\w+', content, re.MULTILINE))
                lines.append(f"  {rel_path}{port_str} — {func_count} functions/classes")

    lines.append("")

    # Service communication (compact)
    lines.append("## Connections")
    service_comms = build_service_comm_map(processed_files)
    if service_comms:
        for line in service_comms:
            lines.append(line)
    else:
        lines.append("  (none detected)")

    lines.append("")

    # Key routes (compact — only show unique endpoints)
    lines.append("## Routes")
    route_map = build_route_map(processed_files)
    if route_map:
        for line in route_map:
            lines.append(line)
    else:
        lines.append("  (none detected)")

    lines.append("")

    # Architecture notes (ultra-compact)
    lines.append("## Arch")
    lines.append("- Win-Native | Holonic Loop 1.0T")
    lines.append("- MCP: foveai-memory(17) + tokenslayer(6) | LLM: Qwen3.5-4B")
    lines.append("- Context: compress_search_results default | summarize_context when heavy")
    lines.append("- Expand: use `expand_node` MCP tool or read specific line ranges")

    return "\n".join(lines)


def main():
    print(f"=== Generating Repo Skeleton (tier={TIER}, level={TS_LEVEL}) ===")

    # Load ignore patterns
    ignore_patterns = load_ignore_patterns()
    print(f"  Loaded {len(ignore_patterns)} ignore patterns from .tokenslayer-ignore")

    # Count how many files would be excluded
    all_files = BACKEND_FILES + FORGE_FILES
    excluded = [f for f in all_files if is_ignored(f, ignore_patterns)]
    if excluded:
        print(f"  Excluded by .tokenslayer-ignore: {len(excluded)} files")
        for f in excluded:
            print(f"    - {f}")

    # Collect dependency data from all files
    processed_files = {}
    for rel_path in all_files:
        if is_ignored(rel_path, ignore_patterns):
            continue
        full_path = ROOT / rel_path
        if full_path.exists():
            processed_files[rel_path] = {
                "imports": extract_imports(full_path),
                "routes": extract_routes(full_path),
                "http_calls": extract_http_calls(full_path),
            }

    # Build dependency, service comm, and route maps
    dep_map = build_dependency_map(processed_files)
    service_comms = build_service_comm_map(processed_files)
    route_map = build_route_map(processed_files)

    # MICRO TIER — completely different output format
    if TIER == "micro":
        output = generate_micro_skeleton(processed_files, ignore_patterns)
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        # STANDARD and FULL tiers use the existing format
        with open(OUTPUT, "w", encoding="utf-8") as f:
            # Ultra-compact header
            tier_name = {"standard": "L3", "full": "L0"}[TIER]
            f.write("# FoveAI Repo Skeleton\n")
            f.write(f"*{datetime.now().strftime('%Y-%m-%d %H:%M')} | TokenSlayer {tier_name} | .tokenslayer-ignore active*\n\n")

            # Maintenance section
            f.write("## Maintenance\n")
            f.write("Auto-generated by [`Scripts/generate_repo_skeleton.py`](Scripts/generate_repo_skeleton.py).\n")
            f.write("Edit [`.tokenslayer-ignore`](.tokenslayer-ignore) to exclude files. Regenerate:\n")
            f.write("```bash\npython Scripts/generate_repo_skeleton.py [--tier micro|standard|full]\n```\n\n")

            # Compact directory tree
            f.write("## Tree\n")
            f.write(get_compact_tree(ignore_patterns) + "\n\n")

            # Compact service map (single line per service)
            f.write("## Ports\n")
            f.write("Soul:8402 | Proxy:8400 | Dashboard:8401 | WS_IPC:8403 | Memory:8002 | MemoryMCP:8002 | Creative:8003 | TSProxy:8103 | WebUI:8080\n\n")

            # === DEPENDENCY MAP ===
            f.write("## Dependencies\n")
            f.write("### Service Communication\n")
            if service_comms:
                for line in service_comms:
                    f.write(line + "\n")
            else:
                f.write("  (none detected)\n")
            f.write("\n")

            f.write("### API Routes\n")
            if route_map:
                for line in route_map:
                    f.write(line + "\n")
            else:
                f.write("  (none detected)\n")
            f.write("\n")

            f.write("### Import Map (who imports what)\n")
            for rel_path, info in processed_files.items():
                imports = info.get("imports", [])
                if imports:
                    local_imports = [i for i in imports if "." in i or not i.islower()]
                    if local_imports:
                        f.write(f"  {rel_path} ← {', '.join(local_imports[:5])}\n")
            f.write("\n")

            # === SKELETONS ===
            f.write("## Backend\n")
            for rel_path in BACKEND_FILES:
                if is_ignored(rel_path, ignore_patterns):
                    print(f"  IGNORED: {rel_path} (matches .tokenslayer-ignore)")
                    continue
                full_path = ROOT / rel_path
                if full_path.exists():
                    print(f"  {rel_path}...")
                    skeleton = run_tokenslayer(full_path)
                    if skeleton.strip():
                        f.write(f"// {rel_path}\n{skeleton}\n\n")
                else:
                    print(f"  SKIP: {rel_path}")

            # Forge skeletons
            f.write("## Forge\n")
            for rel_path in FORGE_FILES:
                if is_ignored(rel_path, ignore_patterns):
                    print(f"  IGNORED: {rel_path} (matches .tokenslayer-ignore)")
                    continue
                full_path = ROOT / rel_path
                if full_path.exists():
                    print(f"  {rel_path}...")
                    skeleton = run_tokenslayer(full_path)
                    if skeleton.strip():
                        f.write(f"// {rel_path}\n{skeleton}\n\n")

            # Config links (minimal)
            f.write("## Config\n")
            f.write("- [mcp-config.json](mcp-config.json) | [AGENTS.md](AGENTS.md) | [.clinerules](.clinerules)\n\n")

            # Architecture notes (ultra-compact)
            f.write("## Arch\n")
            f.write("- Win-Native (no Docker/WSL2/Godot) | Holonic Loop 1.0T\n")
            f.write("- MCP: foveai-memory(17) + tokenslayer(6) | LLM: Qwen3.5-4B\n")
            f.write("- Context: compress_search_results default | summarize_context when heavy\n")

    # Stats
    line_count = len(open(OUTPUT, encoding="utf-8").readlines())
    size_kb = os.path.getsize(OUTPUT) / 1024
    est_tokens = int(size_kb * 1000 / 4)  # ~250 tokens/KB for code

    print("\n=== Generation Complete ===")
    print(f"  Output: {OUTPUT}")
    print(f"  Tier: {TIER}")
    print(f"  Lines: {line_count}")
    print(f"  Size: {size_kb:.1f} KB")
    print(f"  Estimated token footprint: ~{est_tokens} tokens")


if __name__ == "__main__":
    main()