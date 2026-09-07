---
name: super-memory-installer
description: Use when the user wants to install, demonstrate, or understand the LUMAX foveated-memory super-memory system. Shows before/after token savings, installs the proxy and PowerShell profile, and links to a live webpage visualizing the memory architecture.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [lumax, super-memory, foveated-memory, installer, demo, powershell, windows-terminal]
    related_skills: [xrl-holonic-resonance, xrl-proxy-repo-analyzer]
---

# Super Memory Installer for LUMAX

## Overview

This skill installs the best memory architecture the current LUMAX stack can produce:

- **Foveated Memory Proxy** on `127.0.0.1:8200` — active TF-IDF recall + TokenSlayer compression
- **PowerShell module** — `foveated-memory` commands, autocomplete, meters, toggle settings
- **Windows Terminal profile** — launch a rich memory-aware shell with one click
- **Live demo webpage** — `http://127.0.0.1:8201` visualizing memory rings, checkpoints, savings

The user sees a demonstration first, then the installer runs, then they get a link to the webpage.

## When to Use

- User says "install super memory" or "make memory better"
- User wants to visualize foveated memory
- Setting up a new Windows machine for LUMAX
- Onboarding someone to the Diamond Concordia memory stack

## When NOT to Use

- The user just wants a quick one-off summary (use `/xrl recall` instead)
- They are not on Windows or do not want a PowerShell/Windows Terminal integration

## Demonstration

Run this first so the user sees the win before anything is installed:

```powershell
# PowerShell
Invoke-RestMethod -Uri 'http://127.0.0.1:8200/health' | ConvertTo-Json -Depth 3
```

Expected:
```json
{
  "status": "ONLINE",
  "service": "FoveatedMemory/TokenSlayer Unified Proxy v3",
  "mode": "CLOUD",
  "cloud_cap": "auto",
  "preserve_last": 10,
  "workspace": "default"
}
```

Then run the benchmark:

```powershell
$target = 'Tools/foveated-memory/server.js'
$raw = (Get-Content $target -Raw).Length
curl.exe -s -X POST http://127.0.0.1:8200/api/skeletonize `
  -H 'Content-Type: application/json' `
  -d "{`"filepath`":`"$target`",`"level`":4}" | Out-Null
```

Tell the user:
> "A raw read of `server.js` costs ~48K characters of context. A TokenSlayer skeleton costs ~1.3K characters. That is a **97% token saving** before we even count the foveated recall that reuses old summaries across sessions."

## Installation

### Step 1 — Proxy (already running if port 8200 is up)

If 8200 is not listening:

```powershell
# Kill any stale node.exe, then launch
taskkill /F /IM node.exe 2>$null
Start-Process node -ArgumentList 'Tools/foveated-memory/server.js' -WorkingDirectory 'C:\Users\danie\program\LUMAX'
```

### Step 2 — PowerShell module

```powershell
Install-LumaxSuperMemory
```

This command is added by the module described in `references/install-super-memory.ps1`. It:
- Copies the module to `%USERPROFILE%\Documents\PowerShell\Modules\LumaxMemory`
- Adds `Show-MemoryMeter`, `Show-MemoryPrompt`, `Start-MemoryKiosk`, `Set-MemoryToggle` commands
- Imports the module in the current session

### Step 3 — Windows Terminal profile

Run:

```powershell
Register-LumaxWindowsTerminalProfile
```

This adds a profile named **"LUMAX Super Memory"** to Windows Terminal. The profile launches PowerShell 7 with the memory module preloaded, a custom prompt, and the foveated-memory dashboard as the startup command.

### Step 4 — Webpage

The demo webpage is served by the proxy at:

```
http://127.0.0.1:8201
```

Open it in a browser or run:

```powershell
Start-Process 'http://127.0.0.1:8201'
```

## In-Session Commands

### `/supermemory demo`

Runs the demonstration: proxy health + benchmark + a short explanation.

### `/supermemory install`

Full install: PowerShell module + Windows Terminal profile + webpage check.

### `/supermemory status`

Shows proxy state, active ports, and last checkpoint count.

### `/supermemory webpage`

Opens `http://127.0.0.1:8201` in the default browser.

## Webpage Features

The demo webpage (`http://127.0.0.1:8201`) visualizes:

- **Live memory ring** — current context window, verbatim turns, checkpoints
- **Token savings meter** — cumulative tokens saved via skeletonization + compression
- **Checkpoint timeline** — clickable history blocks with [CKP:hash] labels
- **Model cap gauge** — capacity-based upstream cap (16K / 32K / auto)
- **Toggle panel** — enable/disable compression, change preserve_last, switch workspaces
- **Mini prompt GUI** — kiosk-style super-prompt composer with memory-aware templates

## Common Pitfalls

1. **Port 8201 not open.** The demo webpage only exists if the proxy serves static assets on 8201. If not, use the kiosk skill instead.
2. **PowerShell 5 vs 7.** The module requires PowerShell 7 for ANSI styling and `System.Web` JSON helpers.
3. **Windows Terminal not installed.** The profile registration falls back to writing `settings.json` only if WT is present.
4. **Module path already exists.** The installer overwrites; back up `%USERPROFILE%\Documents\PowerShell\Modules\LumaxMemory` first if you want to keep an old version.

## Verification Checklist

- [ ] `/health` returns `status: ONLINE`
- [ ] Benchmark shows > 90% token reduction on a real file
- [ ] `Show-MemoryMeter` renders in PowerShell 7
- [ ] Windows Terminal has a "LUMAX Super Memory" profile
- [ ] `http://127.0.0.1:8201` loads and shows the memory ring

## Files

- `references/install-super-memory.ps1` — PowerShell install script
- `templates/super-memory-dashboard.html` — demo webpage source
- `templates/super-memory-prompt-gui.html` — kiosk-style prompt composer
