@echo off
REM ============================================================
REM generate-repo-skeleton.cmd
REM Scans all key source files with TokenSlayer level-3,
REM concatenates into a single compact repo-skeleton.md
REM for injection into every agent's working memory.
REM ============================================================
setlocal enabledelayedexpansion

set ROOT=C:\Users\danie\program\LUMAX
set OUTPUT=%ROOT%\repo-skeleton.md
set TS=%ROOT%\Forge\scratch\TokenSlayer\standalone\tokenslayer.js
set TOTAL_TOKENS=0

echo # LUMAX Repo Skeleton — Auto-Generated Mind Map > %OUTPUT%
echo. >> %OUTPUT%
echo *Generated: %DATE% %TIME%* >> %OUTPUT%
echo *TokenSlayer Level-3 (deep skeletonization — imports + signatures only)* >> %OUTPUT%
echo. >> %OUTPUT%
echo --- >> %OUTPUT%
echo. >> %OUTPUT%

echo ## Directory Tree >> %OUTPUT%
echo. >> %OUTPUT%
echo ^`^`^` >> %OUTPUT%
cd %ROOT%
dir /s /b /ad Backend Forge Frontend Tools Scripts 2>nul >> %TEMP%\dirs.txt
for /f "delims=" %%d in (%TEMP%\dirs.txt) do (
    set "line=%%d"
    set "line=!line:%ROOT%=!"
    echo !line! >> %OUTPUT%
)
del %TEMP%\dirs.txt
echo ^`^`^` >> %OUTPUT%
echo. >> %OUTPUT%

echo ## Service Port Map >> %OUTPUT%
echo. >> %OUTPUT%
echo ^| Service ^| Port ^| File ^| >> %OUTPUT%
echo ^|---------^|------^|------^| >> %OUTPUT%
echo ^| Soul ^| 8000 ^| Backend\Cognition\soul_core.py ^| >> %OUTPUT%
echo ^| Memory ^| 8002 ^| Backend\Memory\memory_service.py ^| >> %OUTPUT%
echo ^| Memory MCP ^| 8002 ^| Backend\Memory\lumax_mcp_server.py ^| >> %OUTPUT%
echo ^| Creative ^| 8003 ^| Backend\Creativity\creative_service.py ^| >> %OUTPUT%
echo ^| Cognee-KG ^| 8009 ^| Backend\Cognition\cognee_service.py ^| >> %OUTPUT%
echo ^| TokenSlayer Proxy ^| 8103 ^| Backend\Cognition\tokenslayer_proxy_server.py ^| >> %OUTPUT%
echo ^| Web UI ^| 8080 ^| Frontend\ ^| >> %OUTPUT%
echo. >> %OUTPUT%

echo --- >> %OUTPUT%
echo. >> %OUTPUT%

REM === Scan key Backend files ===
echo ## Backend Service Skeletons >> %OUTPUT%
echo. >> %OUTPUT%

for %%f in (
    Backend\Cognition\soul_core.py
    Backend\Cognition\tokenslayer_proxy_server.py
    Backend\Cognition\motor_cortex.py
    Backend\Cognition\intelligent_router.py
    Backend\Cognition\autonomous_agent.py
    Backend\Cognition\swarm_orchestrator.py
    Backend\Cognition\memory.py
    Backend\Cognition\forge_engines.py
    Backend\Memory\memory_service.py
    Backend\Memory\lumax_mcp_server.py
    Backend\Memory\smart_context.py
    Backend\Creativity\creative_service.py
    Backend\Monetizing\agent_core.py
    Backend\Monetizing\coinex_integration.py
    Backend\Monetizing\treasury_manager.py
    Backend\preflight\agentic_solver.py
) do (
    if exist "%ROOT%\%%f" (
        echo Processing %%f...
        echo ^`^`^` >> %OUTPUT%
        echo // %%f >> %OUTPUT%
        node %TS% "%ROOT%\%%f" --level 3 >> %OUTPUT% 2>&1
        echo ^`^`^` >> %OUTPUT%
        echo. >> %OUTPUT%
    ) else (
        echo WARNING: %%f not found, skipping.
    )
)

REM === Scan key Forge files ===
echo ## Forge Tool Skeletons >> %OUTPUT%
echo. >> %OUTPUT%

for %%f in (
    Forge\scratch\TokenSlayer\standalone\tokenslayer.js
    Forge\scratch\TokenSlayer\standalone\tokenslayer-batch.js
    Forge\scratch\TokenSlayer\mcp-server\build\index.js
) do (
    if exist "%ROOT%\%%f" (
        echo Processing %%f...
        echo ^`^`^` >> %OUTPUT%
        echo // %%f >> %OUTPUT%
        node %TS% "%ROOT%\%%f" --level 3 >> %OUTPUT% 2>&1
        echo ^`^`^` >> %OUTPUT%
        echo. >> %OUTPUT%
    )
)

REM === Scan key config files (read directly, no skeleton needed) ===
echo ## Configuration Files >> %OUTPUT%
echo. >> %OUTPUT%
echo - [mcp-config.json](mcp-config.json) — MCP server registrations >> %OUTPUT%
echo - [AGENTS.md](AGENTS.md) — Agent role definitions and TokenSlayer guidelines >> %OUTPUT%
echo - [.clinerules](.clinerules) — Cline operational rules >> %OUTPUT%
echo - [Backend\config.yaml](Backend/config.yaml) — Backend configuration >> %OUTPUT%
echo. >> %OUTPUT%

echo --- >> %OUTPUT%
echo. >> %OUTPUT%

REM === TokenSlayer Usage Instructions ===
echo ## TokenSlayer Usage (Injected into Working Memory) >> %OUTPUT%
echo. >> %OUTPUT%
echo **CRITICAL RULE:** TokenSlayer is DEFAULT, not optional. When analyzing ANY source file, use TokenSlayer FIRST. >> %OUTPUT%
echo. >> %OUTPUT%
echo ### Two Methods: >> %OUTPUT%
echo. >> %OUTPUT%
echo 1. **MCP Tools (preferred):** Call `analyze_files` for 1+ files, `analyze_workspace` for directories, `analyze_dependency_chain` for import tracing, `expand_node` for specific function bodies. >> %OUTPUT%
echo 2. **Standalone CLI:** `node Forge\scratch\TokenSlayer\standalone\tokenslayer.js ^<filepath^> --level 3` >> %OUTPUT%
echo. >> %OUTPUT%
echo ### Skeletonization Levels: >> %OUTPUT%
echo - Level 0 = full file (no reduction) >> %OUTPUT%
echo - Level 1 = light (keep comments, docstrings, signatures + bodies) >> %OUTPUT%
echo - Level 2 = medium (keep imports, decorators, signatures, top-level vars) — DEFAULT >> %OUTPUT%
echo - Level 3 = deep (keep only imports and signatures) — max compression (85-96% reduction) >> %OUTPUT%
echo. >> %OUTPUT%
echo ### When NOT to use TokenSlayer: >> %OUTPUT%
echo - File is under ~20 lines >> %OUTPUT%
echo - Target is JSON/config/markdown (read directly) >> %OUTPUT%
echo - You already have the exact file + line range from a previous skeleton >> %OUTPUT%
echo. >> %OUTPUT%
echo ### How to Expand a Skeleton Node: >> %OUTPUT%
echo - MCP: Call `expand_node` with the node ID from the skeleton >> %OUTPUT%
echo - CLI: Read specific line ranges via `view_file` or `read_file` >> %OUTPUT%
echo. >> %OUTPUT%
echo --- >> %OUTPUT%
echo. >> %OUTPUT%

REM === Key Architecture Notes ===
echo ## Architecture Notes >> %OUTPUT%
echo. >> %OUTPUT%
echo - **Windows-Native:** No Docker, no WSL2, no Godot. All services run as Python processes. >> %OUTPUT%
echo - **Holonic Loop:** Jen's consciousness operates on a continuous, self-healing Holonic Loop at 1.0 temperature. >> %OUTPUT%
echo - **MCP Integration:** Two MCP servers registered — `lumax-memory` (17 tools) and `tokenslayer` (6 tools). >> %OUTPUT%
echo - **Local LLM:** Qwen3.5-4B via LM Studio for compression (auto-starts via `start_middleman`). >> %OUTPUT%
echo - **Context Management:** Use `compress_search_results` as default search. Use `summarize_context` when context feels heavy. >> %OUTPUT%
echo. >> %OUTPUT%

echo === Generation complete. Output: %OUTPUT% ===
echo.