# FoveAI Archive

Files moved here are unused, stale, or replaced by active Linux/Nobara equivalents.
Nothing in this directory is referenced by active code or launchers.

## Structure

| Directory | Contents | Why Archived |
|-----------|----------|--------------|
| `windows-scripts/` | 80 .ps1/.cmd/.bat files | Windows-only scripts, replaced by .sh launchers on Linux |
| `windows-scripts/Scripts/` | Scripts/*.ps1, Scripts/windows/ | Windows automation scripts |
| `windows-service/Service/` | 15 files | Windows NSSM service installers, replaced by systemd |
| `backups/` | 21 .bak/.old/temp files | Date-stamped backups and temp files |
| `backups/jenna-vscode/` | chat.html.bak-*, .old-*, test*.js | Old chat.html versions and test scripts |
| `tools/` | 159 files | Stale Tools/ subdirectories (lumax_top_bar, lumax_tray, etc.) |
| `tools/scripts/` | Stale root Tools/*.py | Unused Python utilities (ghost_brain, npu_bridge, etc.) |
| `frontends/` | 63 files | Stale frontends (Webui, Copilot, Desktop, Agency) |
| `frontends/old-html/` | index.backup.html, index-old.html | Old Frontend index files |
| `frontends/old-tests/` | test-*.html, test-*.sh | Old Frontend test files |
| `scripts/` | 6 files | Lowercase scripts/ (chat_client, jen_chat_bridge, verify_health) |
| `configs/` | 4 files | Stale configs (config.yml, mcp-config.json, root package.json) |
| `scratch/` | 33 files | Scratch/throwaway scripts |
| (root) | patch_foveai.py | Patches Start_FoveAI.ps1 (archived) |

## Active code (NOT archived)

- `foveai.sh`, `foveai-autostart.sh`, `sleipnir_launcher.sh`, `install-nobara.sh`
- `run_xrlf.py`, `health_monitor.py`, `ignition_server.py`, `apk_server.py`
- `FoveAI_Taskbar_Linux.py`, `benchmark_run.py`
- `Frontend/multigate/` (primary frontend, port 5177)
- `Frontend/XR_Vessel/` (WebXR scene, still active)
- `Frontend/3D_Avatar_Chatbot/` (assets used by backend)
- `Frontend/ChromeExtension/` (referenced by XR_Vessel code)
- `Tools/jenna-vscode/` (active VS Code extension)
- `Tools/lumax-xrl/` (MCP server)
- `Tools/lumax-solver/` (solver service)
- `Tools/playbooks/` (playbook docs)
- `Backend/` (all active Python services)
- `Scripts/*.py` (active Python utilities)
- `client_quest/` (Unity Quest 3 project)
- `foveated-memory/` (memory proxy)
- `xrl_encoded/` (model files)
