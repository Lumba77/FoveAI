# LUMAX Windows Service

Runs LUMAX in the background from Windows boot — no console needed. Listens, talks, sleeps, wakes. Controlled from a system tray widget.

## Files

| File | Purpose |
|------|---------|
| `LumaxService.ps1` | Headless service runner — starts at boot, watchdogs services |
| `LumaxTray.ps1` | System tray widget — green/red dot, toggle ON/OFF, stale-state auto-heal |
| `LumaxGuardian.ps1` | Autonomous watchdog — 4-layer resilience + diff backup + cloud sync |
| `lumax_service_config.json` | Avatar name, auto-wake, sleep timeout |
| `Install_Lumax_Service.ps1` | One-click installer (Admin required) |
| `Uninstall_Lumax_Service.ps1` | Clean removal (Admin required) |
| `Register_Global_Lumax.ps1` | Add `lumax` to system PATH |
| `Unregister_Global_Lumax.ps1` | Remove `lumax` from PATH |

## Quick Start

```powershell
# 1. Open PowerShell as Administrator
# 2. Install EVERYTHING (venv + service + tray + global command)
cd C:\Users\lumba\Program\LUMAX-lite
.\Install.ps1 -Auto -InstallService -RegisterGlobal
```

This will:
- Audit your system (CPU, RAM, GPU)
- Create a local Python `.venv` and install all dependencies (PyTorch, FastAPI, ChromaDB, Kuzu, Redis, etc.)
- Create `.env` configuration
- Install the Windows background service + system tray widget
- Register `lumax` as a global command

### Full Install Options

```powershell
# Just dependencies (no service)
.\Install.ps1 -Auto

# Install with service but no global command
.\Install.ps1 -Auto -InstallService

# Full install + Docker build
.\Install.ps1 -Auto -InstallService -RegisterGlobal -Build
```

### Optional: Service-only install (skip .venv)

```powershell
# If you already have a working .venv:
.\Service\Install_Lumax_Service.ps1
```

## Interactive Console + Service Coexistence

When you run `Start_LUMAX.ps1` (or type `lumax` if globally registered), the console will:

1. **Check** if the background service is already running
2. **If yes** — adopt the service's processes into the console dashboard. Meters display CPU/RAM/GPU/VRAM as normal. No duplicate processes spawned.
3. **If no** — start services directly, as before.

This means you can:
- Leave the service running 24/7 in the background
- Open `lumax` anytime to see the full dashboard with live meters
- Close the console — services keep running
- The tray widget always controls the master state

## Tray Widget

After login you'll see a dot in the system tray:

- **Red dot** = LUMAX off
- **Green dot** = LUMAX on, active
- **Amber dot** = LUMAX on, sleeping

**Click** the dot to toggle ON/OFF. **Right-click** for menu:
- Turn ON / Turn OFF
- Wake (from sleep)
- Open Console (full dashboard)
- Open Logs
- Quit Tray

## Config

Edit `Service\lumax_service_config.json`:

```json
{
  "AvatarName": "Jen",
  "AutoWake": true,
  "SleepTimeoutSec": 300,
  "WakeOnVoice": true,
  "EnableVad": true
}
```

- `AvatarName` — shown in tray text
- `AutoWake` — start services immediately at boot
- `SleepTimeoutSec` — seconds of silence before sleep
- `WakeOnVoice` — wake from sleep when voice detected
- `EnableVad` — run Silero VAD voice bridge

## How It Works

```
[Windows Boot]
    ↓
[NSSM] → starts LumaxService.ps1 (as LocalSystem service)
    ↓
[LumaxService] → starts SOUL, EARS, MOUTH, VAD bridge
    ↓
[User Login] → Startup folder runs LumaxTray.ps1
    ↓
[Tray] ← reads .logs\lumax_service_status.json
[Tray] → writes commands to .logs\lumax_service_cmd.txt
    ↓
[Service] ← reads commands, toggles state
```

## Service Lifecycle

- **AWAKE** → All services running, VAD listening
- **SLEEP** → After `SleepTimeoutSec` of inactivity. Services thinned, VAD stays listening for wake word
- **OFF** → All services stopped. Tray dot is red.

## User Consent Data Bridge (WebUI Port 8080)

LUMAX can **optionally and explicitly** enrich her memory with consented user data from Google and Microsoft. **No data is collected without explicit OAuth consent.** No third-party servers involved — tokens stored locally in `.cache/`.

The consent endpoints are built into the existing **WebUI** (`frontend/Web_Vessel/web_app.py` on port `8080`). No separate server is required.

**How it works:**
1. Tray widget → `Connect Data...` → `Google` or `Microsoft`
2. Browser opens `http://127.0.0.1:8080/api/consent/google/auth` (or `/microsoft/auth`)
3. Browser opens the platform's official OAuth consent screen
4. User approves specific read-only scopes (contacts, calendar, email metadata)
5. Redirect hits the local `:8080/api/consent/*/callback` endpoint (never leaves your machine)
6. Data syncs directly to MEMORY service (`:8002`) as graph nodes

**Scopes requested (read-only, no write access):**
- **Google**: `gmail.readonly`, `calendar.readonly`, `contacts.readonly`, `userinfo.profile`
- **Microsoft**: `User.Read`, `Contacts.Read`, `Calendars.Read`, `Mail.ReadBasic`

**What gets stored:**
- Profile (name, photo URL)
- Contacts (names, emails — not message content)
- Calendar events (subjects, times, locations)
- Email metadata only (subject, from, date — **no body content**)

**Privacy guarantees:**
- Tokens stored locally in `.cache/google_tokens.json` and `.cache/ms_tokens.json`
- Raw backups saved to `Data/Consent/` as dated JSON files
- No cloud service receives this data — everything stays on your machine
- Disconnect anytime via tray → data deleted immediately

**Files:**
- `frontend/Web_Vessel/web_app.py` — Hosts `/api/consent/*` endpoints
- `frontend/ConsentBridge/google_oauth.py` — Google OAuth handler
- `frontend/ConsentBridge/ms_oauth.py` — Microsoft OAuth handler

**API Endpoints (port 8080):**
- `GET /api/consent/status` — Show current connection status
- `GET /api/consent/google/auth` — Start Google OAuth flow
- `GET /api/consent/google/callback?code=...` — Google OAuth callback + sync
- `GET /api/consent/microsoft/auth` — Start Microsoft OAuth flow
- `GET /api/consent/microsoft/callback?code=...` — Microsoft OAuth callback + sync
- `POST /api/consent/sync` — Manually trigger data sync
- `GET /api/consent/google/disconnect` — Revoke + delete Google tokens
- `GET /api/consent/microsoft/disconnect` — Revoke + delete Microsoft tokens

## Memory Service (Port 8002)

The MEMORY service runs as a standalone FastAPI server wrapping:

| Layer | Backend | Purpose |
|-------|---------|---------|
| Session cache | Redis (or JSON fallback) | Recent conversation history per session |
| Vector search | ChromaDB | Semantic similarity search over past dialogues |
| Knowledge graph | Kuzu (optional) | Graph relationships between memories, topics, and importance scores |

**Endpoints:**
- `POST /store` — Save a memory with optional topics and importance
- `POST /search` — Semantic search across Chroma + Kuzu graph
- `GET /history/{session_id}` — Retrieve recent session entries from Redis
- `POST /consolidate` — Night-time graph consolidation (high-importance linking)
- `GET /health` — Layer status (redis, chroma, kuzu booleans)

**Dependencies:** `pip install fastapi uvicorn redis chromadb kuzu`

The SOUL (`compagent.py`) can query MEMORY via HTTP at `http://127.0.0.1:8002` for persistent context across sessions.

## Uninstall

Everything is reversible. You can uninstall and reinstall as many times as you want.

```powershell
# Full clean uninstall (removes service, tray, .venv, config, tokens, memories, logs)
.\Uninstall.ps1 -Auto

# Keep all data — just remove services (fast for re-testing)
.\Uninstall.ps1 -Auto -KeepData

# Alternative: service-only uninstall
.\Service\Uninstall_Lumax_Service.ps1 -Auto
```

### What gets preserved with `-KeepData`

- `.venv/` — Python environment (reinstall skips dependency download)
- `.env` — Configuration
- `Service/lumax_service_config.json` — Avatar name, sleep timeout
- `.cache/` — OAuth tokens (Google/Microsoft)
- `Data/Consent/` — Raw consent data backups
- `backend/Memory/*.db` — ChromaDB/Kuzu databases
- `.logs/` — All logs

This lets you iterate quickly: uninstall with `-KeepData`, tweak something, reinstall with `-Auto`, and be back in seconds.

## Logs

- `.logs\lumax_service.log` — Service events
- `.logs\lumax_service_nssm.log` — NSSM stdout
- `.logs\lumax_service_nssm_err.log` — NSSM stderr
- `.logs\*_out.log` / `.logs\*_err.log` — Individual service logs

## Guardian Watchdog (`LumaxGuardian.ps1`)

The Guardian is an autonomous resilience layer that runs every 5 minutes via Windows Task Scheduler. It ensures LUMAX survives Windows Updates, service crashes, and port deadlocks without manual intervention.

### What the Guardian Does (4 Layers)

| Layer | Check | Action if Failing |
|-------|-------|-------------------|
| 1 | Service registration exists | Re-installs NSSM + re-registers `LumaxService` |
| 2 | Service is running | Starts service |
| 3 | Core ports respond (8000/8001/8002/8004/8080) | Restarts service (kills zombie Python processes) |
| 4 | Tray widget process exists | Respawns `LumaxTray.ps1` |

**Guardian now has 2 new weapons:**

- **`Clear-ZombiePorts()`** — Before checking port health, Guardian kills any orphaned Python process holding a LUMAX port (8000/8001/8002/8004/8080). Only kills processes with LUMAX signatures (compagent, uvicorn, web_app, etc.), never random Python.
- **`Clear-OrphanedPython()`** — Hunts Python processes that reference LUMAX in their command line but have no NSSM parent service. These are the true "zombies" from crashed previous sessions.

---

## Service Zombie Prevention (`LumaxService.ps1`)

The service itself now has built-in port pre-clearing and interpreter consistency:

### `Get-LumaxPython()` — Interpreter Resolution

The service explicitly resolves which Python to use, preventing the `.venv` vs `uv` Python mixup that caused today's crash:

| Priority | Path | When Used |
|----------|------|-----------|
| 1 | `.venv\Scripts\python.exe` | Always preferred if exists |
| 2 | `uv`-installed python (`AppData\Roaming\uv\python\...`) | Fallback when `.venv` missing |
| 3 | System `python.exe` | Last resort |

The chosen interpreter is logged on every service startup.

### `Clear-PortOccupant()` — Port Pre-Clear

Before spawning any service, the service checks if the target port is occupied. If it is, and the occupant is a LUMAX zombie Python process, it kills it, waits 2 seconds, and verifies the port is free before proceeding. If the port is still blocked, it logs `PORT_BLOCKED` and skips the spawn (rather than crashing silently).

This prevents the `WinError 10048` "Only one usage of each socket address" crash that was killing all services today.

---

## Guardian Files

| File | Purpose |
|------|---------|
| `Service/LumaxGuardian.ps1` | Main watchdog script |
| `.logs/lumax_guardian.log` | Guardian events |
| `.logs/lumax_guardian_state.json` | Heal count, install attempts, last run |

### Guardian Installation

The Guardian is automatically installed when you run `Service\Install_Lumax_Service.ps1` (or root `Install.ps1 -InstallService`). It creates:

- **Task Name:** `LumaxGuardian`
- **Trigger:** At boot + every 5 minutes repeating
- **User:** SYSTEM (highest privileges)
- **Hidden:** Yes (no window)

To verify it's installed:
```powershell
Get-ScheduledTask -TaskName "LumaxGuardian"
```

To run manually (for testing):
```powershell
.\Service\LumaxGuardian.ps1
```

---

## Backup System (Built into Guardian)

Every time the Guardian runs (every 5 minutes), it also checks if any tracked source files have changed. If they have, it performs backups — **automatically and silently**.

### Backup Strategy

| Type | Frequency | What | Where |
|------|-----------|------|-------|
| **Incremental** | Every 5 min (if changed) | Only changed files by SHA256 diff | `%USERPROFILE%\LUMAX-Backups\incremental\` |
| **Full ZIP** | Once daily (if changed) | Complete snapshot of all tracked files | `%USERPROFILE%\LUMAX-Backups\full\` |
| **Cloud Sync** | After each backup | Copies to OneDrive / Google Drive | Your own cloud account |

### What Gets Backed Up

**Included:** `.ps1`, `.py`, `.json`, `.md`, `.html`, `.env`, `.yml`, `.txt`, `.cmd`, `.gd`, `.css`, `.js`

**Excluded:** `.logs/`, `.venv/`, `__pycache__/`, `node_modules/`, `.git/`, model files (`.gguf`, `.vrm`), media (`.wav`, `.png`, `.jpg`), archives (`.zip`), databases (`.db`)

### Backup Files

| File | Purpose |
|------|---------|
| `.logs/lumax_backup.log` | Backup events and stats |
| `.logs/lumax_backup_state.json` | SHA256 hashes for diff tracking |
| `%USERPROFILE%\LUMAX-Backups\incremental\<timestamp>\` | Changed files with folder structure preserved |
| `%USERPROFILE%\LUMAX-Backups\full\lumax_full_<date>.zip` | Daily full snapshot |

### Cloud Sync

The Guardian auto-detects your cloud storage:

- **OneDrive**: Checks `OneDrive`, `OneDriveConsumer`, `OneDriveCommercial` environment variables
- **Google Drive**: Checks `%USERPROFILE%\Google Drive` and `%USERPROFILE%\My Drive`

Backups are copied to a `LUMAX-Backups` subfolder inside your cloud drive. **No third-party APIs or credentials required** — it uses the local sync folders you already have.

### Retention

- **Incremental backups**: Kept for 7 days, then auto-pruned
- **Full ZIP backups**: Kept for 30 days, then auto-pruned

### Reconstruct from Scripts Alone

The incremental backup preserves the exact folder structure of the repo. To reconstruct LUMAX from backup:

1. Start with the most recent **full ZIP** as base
2. Overlay incremental folders in chronological order
3. Your `.env`, config, and code are restored — no git needed

---

## Discovery Swarm (Self-Discovery System)

The **Discovery Swarm** is an autonomous codebase exploration system that finds unindexed features and proposes inventory updates. It runs as a separate swarm module alongside the existing Drone Swarm problem solvers.

### Architecture

| Drone | Role | What It Scans |
|-------|------|---------------|
| **Mapper** | Codebase scanner | `.py` (endpoints, classes, TODOs), `.ps1` (functions), `.yml`/`.yaml` (Docker services), `.md`/`.gd` (docs/scripts) |
| **Archivist** | Inventory cross-referencer | Empty categories, orphaned file references, missing indexed files |
| **Auditor** | Config auditor | `.env` files, `requirements*.txt`, configs not in inventory |
| **Director** | Report synthesizer | Deduplicates, guesses categories/tiers, builds `DirectorProposal` |

### How It Works

1. **Launch** — `POST /api/discovery/launch` with `duration_minutes` (5–120)
2. **Phase 1** — Director loads `FEATURE_INVENTORY.md` via `feature_inventory_parser.py`
3. **Phase 2** — Mapper, Archivist, and Auditor run concurrently as `asyncio` tasks
4. **Phase 3** — Director synthesizes reports, deduplicates by `(file+name+type)`, guesses category/tier
5. **Phase 4** — Report persisted as JSON to `.logs/discovery_reports/<timestamp>_<mission_id>.json`

### REST API Endpoints (port 8080)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/discovery/state` | GET | Live drone positions, progress %, mission status |
| `/api/discovery/launch` | POST | Launch discovery mission `{duration_minutes: 30}` |
| `/api/discovery/reports` | GET | List persisted reports (newest first, limit=20) |
| `/api/discovery/notification` | GET | Latest report formatted as banner notification |

### Web UI Notification Inbox

The banner's right-side card is now a **📬 INBOX** instead of "SYSTEM INFO":

- **Badge** — Red bubble showing notification count; pulses when unread
- **Dropdown** — Click to see discovery reports with title, summary, timestamp
- **REFRESH** — Polls `/api/discovery/notification` for latest
- **🔭 DISCOVER** — One-click launch of a new discovery mission
- **Click a notification** — Routes to FEATURE MAP tab with "Stubs & placeholders" preset

### Files

| File | Purpose |
|------|---------|
| `backend/Cognition/discovery_swarm.py` | Discovery swarm engine — drones, Director, persistence |
| `frontend/Web_Vessel/web_app.py` | REST endpoints for discovery |
| `frontend/Web_Vessel/index.html` | Notification inbox UI (CSS + JavaScript) |
| `.logs/discovery_reports/` | Persisted JSON reports |

### Launching from Web UI

1. Open the Web UI (`http://127.0.0.1:8080`)
2. Click **📬 INBOX** in the top banner
3. Click **🔭 DISCOVER** to launch a 30-minute scan
4. Wait for badge to update (polls every 60s, or click REFRESH)
5. Click the notification → routes to FEATURE MAP tab

---

## Troubleshooting

**Service won't start**
```powershell
sc.exe query LumaxService
Get-Content .logs\lumax_service_nssm_err.log -Tail 20
```

**Tray not showing**
- Check if tray is in overflow menu (click ^ in taskbar)
- Run manually: `powershell -WindowStyle Hidden -File Service\LumaxTray.ps1`

**Voice not waking**
- Check `.logs\vad_bridge_err.log`
- Ensure microphone is not muted in Windows Privacy settings

**Guardian not running**
```powershell
# Check if scheduled task exists
Get-ScheduledTask -TaskName "LumaxGuardian"

# Check latest guardian log
Get-Content .logs\lumax_guardian.log -Tail 20

# Run manually to see live output
.\Service\LumaxGuardian.ps1
```

**Backups not syncing to cloud**
- Verify OneDrive/Google Drive desktop app is running and signed in
- Check `.logs\lumax_backup.log` for cloud path detection messages
- Manual test: `Test-Path $env:OneDrive` or `Test-Path "$env:USERPROFILE\Google Drive"`
