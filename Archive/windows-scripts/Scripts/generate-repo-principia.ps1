# ============================================================
# generate-repo-skeleton.ps1
# Scans all key source files with TokenSlayer level-3,
# concatenates into a single compact repo-skeleton.md
# for injection into every agent's working memory.
# ============================================================

$ROOT = "C:\Users\danie\program\LUMAX"
$OUTPUT = "$ROOT\repo-skeleton.md"
$TS = "$ROOT\Forge\scratch\TokenSlayer\standalone\tokenslayer.js"

Write-Host "=== Generating Repo Skeleton ===" -ForegroundColor Cyan

# Header
@"
# FoveAI Repo Skeleton — Auto-Generated Mind Map

*Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')*
*TokenSlayer Level-3 (deep skeletonization — imports + signatures only)*
*Total footprint: ~3-5K tokens — injects into every agent's working memory*

---

## Directory Tree

```
"@ | Out-File -FilePath $OUTPUT -Encoding utf8

# Directory tree
$dirs = Get-ChildItem -Path $ROOT -Directory | Where-Object { $_.Name -notmatch '^\.|node_modules|__pycache__|\.venv|\.git' } | Select-Object -ExpandProperty Name
foreach ($d in $dirs) {
    "  $d/" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
    $subs = Get-ChildItem -Path "$ROOT\$d" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '^\.|__pycache__|\.venv' } | Select-Object -ExpandProperty Name
    foreach ($s in $subs) {
        "    $s/" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
    }
}
@"
```
"@ | Out-File -FilePath $OUTPUT -Encoding utf8 -Append

# Service Port Map
@"

## Service Port Map

| Service | Port | File |
|---------|------|------|
| Soul | 8000 | Backend\Cognition\soul_core.py |
| Memory | 8002 | Backend\Memory\memory_service.py |
| Memory MCP | 8002 | Backend\Memory\foveai_mcp_server.py |
| Creative | 8003 | Backend\Creativity\creative_service.py |
| TokenSlayer Proxy | 8103 | Backend\Cognition\tokenslayer_proxy_server.py |
| Web UI | 8080 | Frontend\ |

---

"@ | Out-File -FilePath $OUTPUT -Encoding utf8 -Append

# Files to scan
$backendFiles = @(
    "Backend\Cognition\soul_core.py",
    "Backend\Cognition\tokenslayer_proxy_server.py",
    "Backend\Cognition\motor_cortex.py",
    "Backend\Cognition\intelligent_router.py",
    "Backend\Cognition\autonomous_agent.py",
    "Backend\Cognition\swarm_orchestrator.py",
    "Backend\Cognition\memory.py",
    "Backend\Cognition\forge_engines.py",
    "Backend\Memory\memory_service.py",
    "Backend\Memory\foveai_mcp_server.py",
    "Backend\Memory\smart_context.py",
    "Backend\Creativity\creative_service.py",
    "Backend\Monetizing\agent_core.py",
    "Backend\Monetizing\coinex_integration.py",
    "Backend\Monetizing\treasury_manager.py",
    "Backend\preflight\agentic_solver.py"
)

$forgeFiles = @(
    "Forge\scratch\TokenSlayer\standalone\tokenslayer.js",
    "Forge\scratch\TokenSlayer\standalone\tokenslayer-batch.js",
    "Forge\scratch\TokenSlayer\mcp-server\build\index.js"
)

# Scan Backend files
"## Backend Service Skeletons" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
"" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append

foreach ($f in $backendFiles) {
    $fullPath = "$ROOT\$f"
    if (Test-Path $fullPath) {
        Write-Host "  Scanning $f..." -ForegroundColor Yellow
        "```" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        "// $f" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        $result = node $TS $fullPath --level 3 2>&1
        # Extract just the skeleton lines (skip the [TokenSlayer Saved...] header)
        $skeleton = $result | Where-Object { $_ -notmatch '^\[TokenSlayer Saved' -and $_ -notmatch '^Auto-activating' -and $_ -notmatch '^$' -and $_ -notmatch '^<previous line' }
        $skeleton | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        "```" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        "" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
    } else {
        Write-Host "  WARNING: $f not found, skipping." -ForegroundColor Red
    }
}

# Scan Forge files
"## Forge Tool Skeletons" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
"" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append

foreach ($f in $forgeFiles) {
    $fullPath = "$ROOT\$f"
    if (Test-Path $fullPath) {
        Write-Host "  Scanning $f..." -ForegroundColor Yellow
        "```" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        "// $f" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        $result = node $TS $fullPath --level 3 2>&1
        $skeleton = $result | Where-Object { $_ -notmatch '^\[TokenSlayer Saved' -and $_ -notmatch '^Auto-activating' -and $_ -notmatch '^$' -and $_ -notmatch '^<previous line' }
        $skeleton | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        "```" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
        "" | Out-File -FilePath $OUTPUT -Encoding utf8 -Append
    }
}

# Config files
@"

## Configuration Files

- [mcp-config.json](mcp-config.json) — MCP server registrations (foveai-memory + tokenslayer)
- [AGENTS.md](AGENTS.md) — Agent role definitions and TokenSlayer guidelines
- [.clinerules](.clinerules) — Cline operational rules (23 MCP tools)
- [Backend\config.yaml](Backend/config.yaml) — Backend configuration

---

## TokenSlayer Usage (Injected into Working Memory)

**CRITICAL RULE:** TokenSlayer is DEFAULT, not optional. When analyzing ANY source file, use TokenSlayer FIRST.

### Two Methods:

1. **MCP Tools (preferred):** Call `analyze_files` for 1+ files, `analyze_workspace` for directories, `analyze_dependency_chain` for import tracing, `expand_node` for specific function bodies.
2. **Standalone CLI:** `node Forge\scratch\TokenSlayer\standalone\tokenslayer.js <filepath> --level 3`

### Skeletonization Levels:
- Level 0 = full file (no reduction)
- Level 1 = light (keep comments, docstrings, signatures + bodies)
- Level 2 = medium (keep imports, decorators, signatures, top-level vars) — DEFAULT
- Level 3 = deep (keep only imports and signatures) — max compression (85-96% reduction)

### When NOT to use TokenSlayer:
- File is under ~20 lines
- Target is JSON/config/markdown (read directly)
- You already have the exact file + line range from a previous skeleton

### How to Expand a Skeleton Node:
- MCP: Call `expand_node` with the node ID from the skeleton
- CLI: Read specific line ranges via `view_file` or `read_file`

---

## Architecture Notes

- **Windows-Native:** No Docker, no WSL2, no Godot. All services run as Python processes.
- **Holonic Loop:** Jen's consciousness operates on a continuous, self-healing Holonic Loop at 1.0 temperature.
- **MCP Integration:** Two MCP servers registered — `foveai-memory` (17 tools) and `tokenslayer` (6 tools).
- **Local LLM:** Qwen3.5-4B via LM Studio for compression (auto-starts via `start_middleman`).
- **Context Management:** Use `compress_search_results` as default search. Use `summarize_context` when context feels heavy.

"@ | Out-File -FilePath $OUTPUT -Encoding utf8 -Append

# Count lines
$lineCount = (Get-Content $OUTPUT | Measure-Object -Line).Lines
$sizeKB = [math]::Round((Get-Item $OUTPUT).Length / 1KB, 1)

Write-Host "=== Generation Complete ===" -ForegroundColor Green
Write-Host "  Output: $OUTPUT" -ForegroundColor White
Write-Host "  Lines: $lineCount" -ForegroundColor White
Write-Host "  Size: $sizeKB KB" -ForegroundColor White
Write-Host "  Estimated token footprint: ~$([math]::Round($sizeKB * 0.75)) tokens" -ForegroundColor Cyan