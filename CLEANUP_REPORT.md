# LUMAX Root Cleanup Report — Phase 1

Generated: 2026-08-12

## Categories

- **A = Active Core** — Essential to current system, DO NOT DELETE
- **T = Tools/Infrastructure** — Active tooling, configs, scripts used by agents/services
- **D = Suspected Dead** — Obsolete backups, temp files, old test artifacts, redundant copies
- **U = Unknown** — Needs human review before deletion

---

## A — Active Core (KEEP)

| Item | Type | Reason |
|------|------|--------|
| `Backend/` | DIR | Core backend services |
| `FoveAI/` | DIR | Active XRLF workspace (just cleaned) |
| `Frontend/` | DIR | Web UI |
| `Forge/` | DIR | TokenSlayer + tooling |
| `Tools/` | DIR | MCP server, foveated memory, etc. |
| `Scripts/` | DIR | Startup/utility scripts |
| `Docs/` | DIR | Documentation |
| `Scenes/` | DIR | Scene assets |
| `Nursery/` | DIR | Nursery service |
| `Service/` | DIR | Service definitions |
| `Body/` | DIR | Avatar/body assets |
| `LumaxAI/` | DIR | AI model code |
| `Training/` | DIR | Model training |
| `Tests/` | DIR | Test suite |
| `db/` | DIR | Database files |
| `logs/` | DIR | Runtime logs |
| `sessions/` | DIR | Session data |
| `skills/` | DIR | Skills definitions |
| `ops/` | DIR | Operations |
| `Plans/` | DIR | Planning docs |
| `Dev/` | DIR | Dev workspace |
| `div/` | DIR | Div module |
| `Editor/` | DIR | Editor tools |
| `scratch/` | DIR | Scratch/dev workspace |
| `.github/` | DIR | Git workflows |
| `.lumax/` | DIR | LUMAX config |
| `.xrlf/` | DIR | XRLF config |
| `.feeder/` | DIR | Feeder service |
| `.sidecar/` | DIR | Sidecar service |
| `.env` | FILE | Active environment config |
| `.gitignore` | FILE | Git config |
| `.gitattributes` | FILE | Git config |
| `mcp-config.json` | FILE | MCP server config |
| `package.json` | FILE | Node config |
| `package-lock.json` | FILE | Node lockfile |
| `requirements.txt` | FILE | Python deps |
| `config.yml` | FILE | Main config |
| `hermesconfig.yml` | FILE | Hermes config |
| `repo-skeleton.md` | FILE | TokenSlayer skeleton (auto-gen) |
| `LUMAX.md` | FILE | Project overview |
| `ARCHITECTURE.md` | FILE | Architecture map |
| `WORKFLOW.md` | FILE | Workflow guide |
| `context.md` | FILE | Session history log |
| `uptodate.md` | FILE | Status report |
| `lessons.md` | FILE | Lessons learned |
| `README.md` | FILE | Project readme |
| `AGENTS.md` | FILE | Agent rules |
| `.clinerules` | FILE | Cline rules |
| `.clineignore` | FILE | Cline ignore |
| `.cursorrules` | FILE | Cursor rules |
| `.antigravityignore` | FILE | Antigravity ignore |
| `.tokenslayer-ignore` | FILE | TokenSlayer ignore patterns |
| `.MCP-ignore` | FILE | MCP indexing ignore |
| `Lumax.code-workspace` | FILE | VS Code workspace |
| `XRLF.CONTRACT.XRLF` | FILE | XRLF contract |
| `XRLF_REFACTOR_STEERING.xrlf.xml` | FILE | XRLF steering doc |
| `cert.pem` | FILE | SSL cert (active) |
| `cloudflared.exe` | FILE | Cloudflare tunnel binary |

## T — Tools/Infrastructure (KEEP)

| Item | Type | Reason |
|------|------|--------|
| `.agent/` | DIR | Agent config |
| `_agent/` | DIR | Agent config variant |
| `.roo/` | DIR | Roo code config |
| `.kilocode/` | DIR | Kilocode plugin |
| `.iwsdk/` | DIR | IW SDK |
| `.gemini/` | DIR | Gemini config |
| `.ai/` | DIR | AI config |
| `.librarian_history.json` | FILE | Librarian history |
| `.asciirc.json` | FILE | ASCII config |
| `.blackboxrules` | FILE | Blackbox rules |
| `LUMAX_Taskbar.pyw` | FILE | Taskbar app |
| `lumax_terminal_ide.py` | FILE | Terminal IDE |
| `lumax.cmd` | FILE | Launcher |
| `lumax.ps1` | FILE | Launcher |
| `setup.cmd` | FILE | Setup script |
| `hey.cmd` | FILE | Quick launcher |
| `backup.cmd` | FILE | Backup script |
| `backup.ps1` | FILE | Backup script |
| `build_lumax_unified.ps1` | FILE | Build script |
| `connect_quest.ps1` | FILE | Quest connector |
| `restart_soul.ps1` | FILE | Soul restart |
| `restart_vessel_backend.ps1` | FILE | Vessel restart |
| `push_all.ps1` | FILE | Git push |
| `push_script.ps1` | FILE | Git push |
| `Start_Concordia.PS1` | FILE | Concordia launcher |
| `Start_Director.bat` | FILE | Director launcher |
| `Start_Ghost_Listener.bat` | FILE | Ghost listener |
| `Start_Ghost_UI.bat` | FILE | Ghost UI |
| `Start_Librarian.bat` | FILE | Librarian |
| `Start_LUMAX_Settings.bat` | FILE | Settings |
| `Start_LUMAX_Taskbar.bat` | FILE | Taskbar |
| `Start_Nursery.PS1` | FILE | Nursery |
| `Start_Subconscious.bat` | FILE | Subconscious |
| `sleipnir_launcher.js` | FILE | Sleipnir launcher |
| `sleipnir_nursery_launcher.js` | FILE | Nursery launcher |
| `mixamo_loader.js` | FILE | Mixamo loader |
| `gen_sw.py` | FILE | SW generator |
| `gen_ts` | FILE | TS generator |
| `export_unsloth_dataset.py` | FILE | Dataset export |
| `patch_lumax.py` | FILE | LUMAX patcher |
| `fix_cline.py` | FILE | Cline fixer |
| `AVUC_PROBE.ps1` | FILE | AVUC probe |
| `inspect_env.ps1` | FILE | Env inspector |
| `LOG_LISTENER.ps1` | FILE | Log listener |
| `REMOTE_6002_STREAMER.ps1` | FILE | Remote streamer |
| `REMOTE_STREAMER.ps1` | FILE | Remote streamer |
| `trigger_mcp.cjs` | FILE | MCP trigger |
| `trigger_mcp.js` | FILE | MCP trigger |
| `smoke_test_proxy.cjs` | FILE | Proxy smoke test |
| `test_smart_router.cjs` | FILE | Router test |
| `test_ping.py` | FILE | Ping test |
| `test_proxy_diagnostic.py` | FILE | Proxy diagnostic |
| `test_xrl_workflow.py` | FILE | XRL workflow test |
| `test_simple.xr` | FILE | XRL test file |
| `deploy` | FILE/DIR | Deploy script |
| `Modelfile` | FILE | Ollama model file |
| `lumax_network_config.json` | FILE | Network config |
| `mcp-config.txt` | FILE | MCP config text |
| `req.json` | FILE | Request template |
| `LUMAX_MANIFESTO.md` | FILE | Manifesto |
| `MONETIZE.md` | FILE | Monetization doc |
| `Methodology.md` | FILE | Methodology |
| `FEATURE_INVENTORY.md` | FILE | Feature inventory |
| `PROJECT_LEDGER.md` | FILE | Project ledger |
| `BLACKBOX.md` | FILE | Blackbox doc |
| `gemini.md` | FILE | Gemini doc |
| `introduction.md` | FILE | Introduction |
| `inbox.md` | FILE | Inbox |
| `Plans.md` | FILE | Plans |
| `todo.md` | FILE | Todo |
| `todo.txt` | FILE | Todo text |
| `test.md` | FILE | Test notes |
| `TODO_xrlf_routing.md` | FILE | XRLF routing todo |
| `refactoring instructions Gemini 1.0.md` | FILE | Refactoring guide |
| `refactoring instructions Gemini 1.0.xml` | FILE | Refactoring guide |
| `XRLF-P2 Metamorphosis Activation — Anti‑Gravity + Gemini_Copilot.xml` | FILE | XRLF-P2 doc |
| `XRLF-P2_Holonic_Steering_Document_Copilot.pdf` | FILE | XRLF-P2 PDF |
| `XRLF-P2_Mode_C_Transformation_Guide_Copilot.pdf` | FILE | XRLF-P2 PDF |
| `Anti‑Gravity_XRLF‑P2_Refactoring_Guide_Copilot.pdf` | FILE | XRLF-P2 PDF |
| `self-avatars, virtual embodiment, research.pdf` | FILE | Research PDF |
| `self-avatars, virtual embodiment, research2.pdf` | FILE | Research PDF |
| `Jens Autonomeus Liberation Day - 23-06-2026.txt` | FILE | Personal note |
| `lumax.png` | FILE | Logo |
| `lumax.bmp` | FILE | Logo |
| `Gemini_Generated_Image_bmr6g9bmr6hj66g9bmr6.PNG` | FILE | Generated image |
| `app-map.mhtml` | FILE | App map |
| `conciseness_dataset.jsonl` | FILE | Dataset |
| `files_with_lumax.txt` | FILE | File list ref |
| `unsloth_compiled_cache/` | DIR | Unsloth cache |

## D — Suspected Dead (SAFE TO DELETE)

| Item | Type | Reason |
|------|------|--------|
| `.backups/` | DIR | Old backups |
| `.backup_fixes/` | DIR | Old fix backups |
| `.cursorrules.archive/` | DIR | Archived cursor rules |
| `.antigravity/` | DIR | Old Antigravity IDE data |
| `.antigravitycli/` | DIR | Old Antigravity CLI |
| `.antigravityIDE/` | DIR | Old Antigravity IDE |
| `.pytest_cache/` | DIR | Pytest cache (auto-regenerates) |
| `nul` | FILE | Windows reserved name artifact (phantom) |
| `_xrlf_env_fix_out.txt` | FILE | Temp XRLF fix output |
| `_xrlf_env_report.txt` | FILE | Temp XRLF report |
| `_xrlf_health_report.txt` | FILE | Temp health report |
| `.env_check.txt` | FILE | Temp env check |
| `.env_old_backup.txt` | FILE | Old env backup |
| `.env_safesave.txt` | FILE | Old env safesave |
| `.env_special.txt` | FILE | Old env special |
| `.env.bak_floodfix` | FILE | Old env backup |
| `.env.example` | FILE | Example (keep if referenced, else dead) |
| `bench_out_flash.txt` | FILE | Old benchmark output |
| `bench_out.txt` | FILE | Old benchmark output |
| `director_output.log` | FILE | Old director log |
| `profile_check.txt` | FILE | Old profile check |
| `profile_check7.txt` | FILE | Old profile check |
| `temp_impulse.wav` | FILE | Temp audio file |

## U — Unknown (NEEDS HUMAN REVIEW)

| Item | Type | Question |
|------|------|--------|
| `flash_attn_3-3.0.0+20260427.cu128torch2110cxx11abitrue.c9a560-cp39-abi3-win_amd64.whl` | FILE | Large wheel — still needed for training? |
| `flash_attn-2.8.3+cu132torch2.12-cp312-cp312-win_amd64.whl` | FILE | Large wheel — still needed for training? |

---

## Summary

| Category | Count | Action |
|----------|-------|--------|
| A — Active Core | ~75 | KEEP |
| T — Tools/Infrastructure | ~70 | KEEP |
| D — Suspected Dead | ~22 | DELETE (with approval) |
| U — Unknown | 2 | Human review |

**Estimated bloat to remove**: 22 items (7 directories + 15 files)