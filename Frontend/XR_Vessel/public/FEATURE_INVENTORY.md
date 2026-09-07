# Lumax feature inventory

**Purpose:** Live data for the Web UI **Feature Map** tab (`GET /api/feature_inventory`).  
**Format:** Numbered `## N.` sections (maps to categories in `frontend/Web_Vessel/feature_inventory_parser.py`) and **pipe tables** with a header row, separator row, and body rows. Tier cells use bold letters: **`A`** … **`D`** (e.g. **`A/B`**).

**Note:** This file was recreated in-repo when the previous large inventory was not recoverable from git history. Extend tables as you ship or change behaviour.

---

## 1. Docker / runtime

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `docker-compose.yml` default **Awake lean** (soul, ears, mouth, memory) | **A** | Profiles **lumax-desk-extras** (ops+Ollama), **lumax-sleep-embers** (embers), **creativity**/**creative**; VR-lite / VR-bare / **state-creative** merges optional |
| `lumax_soul` — `compagent` + GGUF / local LLM | **A** | Bind mount `LUMAX_REPO_ROOT` → `/app`; models under `/app/models` |
| `lumax_ears` — STT :8001 + TTS :8002 (F5 + Piper) | **A** | Depends on healthy `lumax_mouth_emotion` for default F5-TTS |
| `lumax_mouth_emotion` — F5-TTS Emotion-CFG HTTP :8780 | **B** | Checkpoints on host (`LUMAX_F5_EMOTION_CKPT_DIR` → `/ckpts`); `Scripts/lumax_mouth_emotion_server.py` |
| `lumax_mouth` — F5-TTS Gradio SWivid :7860 | **C** | Profile `swivid-mouth`; use when `LUMAX_F5TTS_ENGINE=swivid` |
| `lumax_mouth_spark` — Spark-TTS 0.5B HTTP :8810 | **C** | Profile `spark-mouth`; `LUMAX_F5TTS_ENGINE=spark`; mount `SparkAudio/Spark-TTS-0.5B` at `LUMAX_SPARK_MODEL_DIR` |
| `lumax_ops` — Web UI :8080 + AutonomousSentry | **A** | `LUMAX_WEBUI_PASSWORD`; Docker socket for heal |
| `lumax_memory` — Redis | **A** | Soul / embers use `REDIS_HOST` |
| `lumax_ollama_backup` — Ollama :11434 | **A** | Embeds, helpers, sentry solver; not always main chat path |
| `lumax_embers` — idle / slow-burn | **B** | Profile **lumax-sleep-embers** (off in default Awake/LIVE lean) |
| Compose profiles (`lumax-desk-extras`, `lumax-sleep-embers`, `creativity`/`creative`, `agent`) | **C** | Desk utilities, embers, `lumax_creativity`, `lumax_agent` optional |

---

## 2. Web UI

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| FastAPI bridge `frontend/Web_Vessel/web_app.py` | **A** | Proxies soul, ears, mouth, vitals; session auth |
| Feature Map tab — this file via `/api/fmap` | **A** | `FEATURE_INVENTORY.md` at repo root → `/app/FEATURE_INVENTORY.md` in Docker |
| Branding / `lumax_ui_config` | **B** | `GET /api/ui_config`, nav labels |
| Diagnostics / pipeline helpers | **B** | Ops-only routes as implemented |
| Clinical Dashboard `frontend/XR_Vessel/src/components/Dashboard.ts` | **A** | Live PC vitals, navigation, and API bridge |
| Diagnostic Matrix `frontend/XR_Vessel/src/components/DiagnosisTab.ts` | **A** | 40x14 clinical matrix with dynamic Cross-Hair Highlighting and sticky headers |
| Self-Assessment & Auto-Mirror | **A** | Distraction-free survey modal; allows users to let JEN auto-mirror their psychiatric profile |

---

## 3. Backend (Mind / soul)

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `backend/Cognition/compagent.py` — `/compagent` | **A** | Main chat, streaming optional |
| `backend/Cognition/lumax_engine.py` — GGUF, adaptive `n_ctx` | **A** | `LUMAX_LOCAL_N_CTX`, `LUMAX_GGUF_CHAT_TEMPLATE_PATH`, thinking strip |
| `backend/Cognition/MindCore.py` — `clean_response`, thought / emotion | **A** | Qwen `<redacted_thinking>` → JSON `thought` |
| `backend/Cognition/memory.py` — Redis + Chroma | **B** | `chromadb`, `ollama` embed client |
| Optional Cognee / cloud repertoire | **C** | Env-gated |

---

## 4. Godot / VR

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `frontend/XR_Vessel` — OpenXR / Nexus | **B** | Godot project path varies per checkout |
| `Synapse.gd` — soul HTTP, `response_received` | **A** | `thought` + `text` for VR UI |
| `backend/WebUI.gd` — in-world panels | **B** | SubViewport / tactile keyboard |
| Native HTML chat `backend/Web/chat.html` | **C** | Optional wrist / debug HTML |

---

## 5. Mobile

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `frontend/Mobile_Vessel` | **C** | Capacitor / Vite stack — verify active branch |
| Shared `lumax_ui_config` for mobile section | **C** | Same JSON schema as web where wired |

---

## 6. Tests

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `Scripts/AUTOTEST*.ps1`, `testrun_docker.ps1` | **B** | Local / CI smoke |
| `frontend/XR_Vessel/scripts/diagnostic/*` | **C** | Godot integrity helpers |

---

## 7. Ops & scripts

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `frontend/Immune/autonomous_sentry.py` | **A** | Preflight, heal, outbox |
| `Scripts/Start_Lumax_VR.ps1` | **B** | Phased compose + VR merges; script map **`Scripts/README.md`** |
| `Scripts/f5_tts_gradio_launch.py` | **B** | Mouth image CMD |
| `backend/preflight/*` | **B** | Checks, agentic solver |

---

## 8. Cross-surface

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| Env parity: `.env` + `env.vr.example` | **A** | `LUMAX_REPO_ROOT`, `LUMAX_MODELS_ROOT`, soul URLs |
| TTS: F5 primary, Piper fallback | **A** | `LUMAX_F5TTS_URL`, `LUMAX_F5TTS_REF_AUDIO`, `handle_file()` for Gradio 5 |
| STT → soul → TTS pipeline | **A** | Web UI diagnostics path |

---

## 9. Windows Service & Tray

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `Service/LumaxService.ps1` — NSSM background runner | **A** | Auto-start on boot; SLEEP/AWAKE lifecycle; watchdogs all services |
| `Service/LumaxTray.ps1` — System tray widget | **A** | Colored dot (red/green/amber); toggle ON/OFF; balloon tips for wake ritual; stale-state auto-heal |
| `Service/LumaxGuardian.ps1` — Autonomous watchdog & healer | **A** | 4-layer resilience: service registration, running check, port health, tray respawn; survives Windows Updates |
| Guardian: NSSM auto-reinstall | **A** | Downloads NSSM if missing; re-registers service after Windows Update removal |
| Guardian: Port health check & restart | **A** | Tests ports 8000/8001/8002/8004/8080; restarts service if ports dead |
| Guardian: Proactive zombie kill (`Clear-ZombiePorts`) | **A** | Kills orphaned Python processes holding LUMAX ports before spawn |
| Guardian: Orphaned Python hunter (`Clear-OrphanedPython`) | **A** | Detects Python processes without NSSM parent service and terminates |
| Guardian: Diff-based incremental backup | **A** | SHA256 hash scan every 5 min; only changed `.py`/`.ps1`/`.json`/`.md`/`.html`/`.env`/`.gd` files copied |
| Guardian: Daily full ZIP backup | **A** | Complete snapshot once daily if changes detected; auto-sync to cloud |
| Guardian: Cloud sync (OneDrive / Google Drive) | **A** | Auto-detects cloud paths; copies backups to user's own account |
| Guardian: Backup pruning | **B** | Incrementals kept 7 days, full zips 30 days |
| Discovery Swarm — self-discovery system | **A** | `backend/Cognition/discovery_swarm.py` — Mapper + Archivist + Auditor drones scan codebase |
| Discovery Swarm: Mapper drone | **A** | Scans `.py`/`.ps1`/`.yml`/`.md`/`.gd` for endpoints, classes, functions, services, TODOs |
| Discovery Swarm: Archivist drone | **A** | Cross-references inventory structure; finds empty categories and orphaned file refs |
| Discovery Swarm: Auditor drone | **A** | Audits `.env`, `requirements*.txt`, configs not referenced in inventory |
| Discovery Swarm: Director Manager | **A** | Synthesizes drone reports into `DirectorProposal` with category/tier guesses |
| Discovery Swarm: Report persistence | **A** | JSON reports saved to `.logs/discovery_reports/` with SHA timestamp |
| Discovery Swarm: Web UI notification inbox | **A** | Banner inbox shows discovery findings; one-click launch from UI |
| Discovery Swarm: REST API | **A** | `POST /api/discovery/launch`, `GET /api/discovery/state`, `GET /api/discovery/notification` |
| Service + Console coexistence | **A** | Console adopts service PIDs from `lumax_service_status.json` — no duplicates |
| Wake ritual on SLEEP→AWAKE | **B** | LLM-generated unique greeting via `/compagent`; sleep duration + time-of-day context |
| Startup CRASH detection with grace period | **B** | 8-second grace period + immediate-exit detection + log-tail reading in `Start_LUMAX.ps1` |
| `Service/Install_Lumax_Service.ps1` — NSSM installer | **A** | Downloads NSSM if missing; registers `LumaxService`; adds tray to Startup; installs Guardian scheduled task |
| `Service/Uninstall_Lumax_Service.ps1` — Service remover | **A** | `-KeepData` switch preserves `.venv`, config, tokens, logs; removes Guardian task |
| `Service/lumax_service_config.json` — Avatar config | **B** | `AvatarName`, `AutoWake`, `SleepTimeoutSec`, `WakeOnVoice`, `EnableVad` |

---

## 10. Memory & Consent Data

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `backend/Memory/memory_service.py` — MEMORY service (:8002) | **A** | FastAPI; Redis session cache + ChromaDB vector ANN |
| Cognee automated graph extraction | **B** | Optional LLM-powered memory construction (`cognee` dependency) |
| Consent endpoints in `web_app.py` (:8080) | **A** | `/api/consent/google/*`, `/api/consent/microsoft/*` — no separate server |
| `frontend/ConsentBridge/google_oauth.py` — Google OAuth | **B** | Read-only scopes: Gmail, Calendar, Contacts, Profile |
| `frontend/ConsentBridge/ms_oauth.py` — Microsoft OAuth | **B** | Read-only scopes: User.Read, Contacts.Read, Calendars.Read, Mail.ReadBasic |
| Local token storage | **A** | `.cache/google_tokens.json`, `.cache/ms_tokens.json` — never leaves machine |
| Consent data sync to MEMORY | **A** | Profile, contacts, calendar events, email metadata → graph nodes at :8002 |

---

## 11. Install / Uninstall Infrastructure

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `Install.ps1` — Unified Windows installer (v2.0) | **A** | `.venv` + dependencies + service + tray + PATH in one command |
| `Uninstall.ps1` — Reversible uninstall | **A** | `-KeepData` preserves `.venv`, config, tokens, memories, logs for fast iteration |
| `Service/Register_Global_Lumax.ps1` — PATH registration | **B** | Adds repo root to system PATH so `lumax` works from any directory |
| `Service/Unregister_Global_Lumax.ps1` — PATH cleanup | **B** | Removes repo root from system PATH |
| System audit on install | **B** | CPU, RAM, GPU detection; warns if <16GB RAM |

---

## 12. Gaps & next steps

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| Restore historical rows if found | **D** | Older `FEATURE_INVENTORY.md` may exist on another clone / backup |
| Streaming chat UX | **C** | Non-stream default; optional NDJSON |
| VR "thought" overlay / toasts | **C** | Parity with Web UI toasts when enabled |
| Memory graph visualization | **C** | Vector similarity explorer in WebUI |
| Consent data scheduling (auto-sync) | **C** | Periodic refresh of Google/Microsoft data without manual trigger |
| Backup encryption at rest | **C** | Optional password-protected ZIP for sensitive `.env`/tokens |
| Backup web UI restore panel | **C** | One-click restore from incremental or full backup in WebUI |

---

## 14. Architecture Map

| Artifact / diagram | Tier | Notes |
| --- | --- | --- |
| `ARCHITECTURE.md` — System topology | **A** | 7 Mermaid diagrams: service graph, dependencies, data flow, profile matrix, state machine, dashboard layout, file map |
| High-level backend/frontend/Service topology | **A** | `graph TB` — User → Tray/Console → SVC → Mind + Body + Storage |
| Service dependency graph | **A** | `graph LR` — Core vs Optional vs External layers |
| Data flow: conversation turn | **A** | `sequenceDiagram` — User → EARS → SOUL → MEMORY → MOUTH |
| Service profile matrix | **A** | Table: which services run in AWAKE/LIVE/SLEEP/CODE/CREATIVE |
| State machine: life cycle | **A** | `stateDiagram-v2` — LOADING → AWAKE → LIVE/SLEEP/CRASH |
| Console dashboard layout | **B** | `block-beta` — Service blocks, meters, controls |
| File organization map | **B** | `graph TD` — Root → backend/frontend/Service/Scripts/Tools/Forge |
| Mermaid rendering | **A** | Native in GitHub, GitLab, VS Code Mermaid extension |

---

## 15. Troubleshooter Crew

> Component definitions for the "librarian" — high-resolution role assignments.

| Agent / role | Responsibility | Signal / trigger | Files |
| --- | --- | --- | --- |
| **Service Watchdog** | Monitor service health, restart crashed processes | Any service PID exits unexpectedly | `Service/LumaxService.ps1`, `frontend/Immune/autonomous_sentry.py` |
| **Port Scout** | Detect port conflicts, zombie Python processes | Console shows "none running" or adoption fails | `Start_LUMAX.ps1` adoption logic |
| **Syntax Sentinel** | Catch PowerShell backtick-in-string, Python syntax | Install fails, service won't start | `Install.ps1`, `Start_LUMAX.ps1` |
| **Env Curator** | Validate `.env` + `lumax_service_config.json` coherence | Missing vars, wrong paths | `.env`, `Service/lumax_service_config.json` |
| **Venv Steward** | Ensure `.venv` exists, dependencies current, no conflicts | Import errors on startup | `Install.ps1`, `requirements_lumax.txt` |
| **OAuth Gatekeeper** | Manage consent tokens, refresh, revoke | User clicks "Connect Google/Microsoft" | `frontend/ConsentBridge/*.py`, `.cache/` |
| **Memory Archivist** | Consolidate session history, vector embeddings, graph nodes | Night sleep consolidation or manual sync | `backend/Memory/memory_service.py`, `backend/Memory/*.db` |
| **Dashboard Cartographer** | Keep ARCHITECTURE.md and FEATURE_INVENTORY.md in sync | New service added, port changed, state added | `ARCHITECTURE.md`, `FEATURE_INVENTORY.md` |
| **State Mechanic** | Verify SLEEP/AWAKE/LIVE/CODE/CREATIVE transitions | Wrong services running, tray state mismatch | `Start_LUMAX.ps1` `Update-State`, `LumaxService.ps1` |
| **Log Archaeologist** | Parse `.logs/` for crash signatures, startup errors | Service crash-loop, WEBUI exits immediately | `.logs/*_err.log`, `lumax_service.log` |
| **NSSM Shepherd** | Windows service install/uninstall, PATH registry | Service not starting after reboot | `Service/Install_Lumax_Service.ps1`, `Service/Uninstall_Lumax_Service.ps1` |
| **Concordia Marshal** | 9-node swarm health, port checks, process monitoring | Any Concordia node exits unexpectedly | `sleipnir_launcher.js`, `Start_Concordia.PS1` |
| **Vite Wrangler** | WebXR frontend build, HMR, Cloudflare tunnel | Frontend not loading, tunnel down | `frontend/XR_Vessel/`, `cloudflared` |
| **TTS Dispatcher** | Route TTS requests to correct engine (Turbo/Piper/F5/Spark/VoxCPM) | Voice not playing, wrong voice, timeout | `frontend/Physical_Interface/turbochat_server.py`, `backend/Cognition/compagent.py` |
| **STT Listener** | Verify Silero VAD + Whisper pipeline | No transcription, VAD not triggering | `frontend/Physical_Interface/body_interface.py`, `frontend/CON_vessel/vad_bridge.py` |
| **Soul Therapist** | Diagnose LLM inference failures (GGUF load, context overflow, cloud fallback) | Soul responds with errors, uses CPU only, crashes | `backend/Cognition/compagent.py`, `backend/Cognition/lumax_engine.py` |
| **Creative Smith** | Image generation pipeline, Spandrel upscale, dream catharsis | Dream images fail, creativity service offline | `backend/Creativity/creative_service.py` |
| **Network Weaver** | Quest LAN, ADB reverse, port forwarding, firewall | Quest cannot reach soul, timeout on headset | `Scripts/connect_quest.ps1`, `frontend/Immune/autonomous_sentry.py` |
| **Crew Dispatcher** | Spawn and coordinate troubleshooters, collect reports | User reports "something is wrong" | `ARCHITECTURE.md` section 15, `FEATURE_INVENTORY.md` |

---

## 13. Meta

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| This file — edit in repo root | **A** | Override path: `LUMAX_FEATURE_INVENTORY_PATH` |
| Parser `feature_inventory_parser.py` | **A** | Tables under `## N.` headings; tier markers `**A**` in cells |
| `.dockerignore` — does not exclude this file | **A** | Must exist on host for bind-mounted `/app` |
