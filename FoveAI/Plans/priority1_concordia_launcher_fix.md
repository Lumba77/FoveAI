# Priority 1: Fix Concordia Launcher — Implementation Plan

## Current State

### What `Start_Concordia.PS1` → `sleipnir_launcher.js` launches:
| Node | Service | Port | Status |
|------|---------|------|--------|
| 1 | TokenSlayer (smart_context) | 8103 | ✅ Works |
| 2 | MCP Server | 8101 | ✅ Works |
| 3 | Core Solver | 8102 | ✅ Works |
| 4 | Stardust Neural | 8109 | ✅ Works |
| 5 | Motor Cortex | 8110 | ❌ `motor_daemon.py` MISSING |

### What `Start_LUMAX.ps1` launches (LEGACY — to be deprecated):
| Service | Port | Notes |
|---------|------|-------|
| SOUL (compagent.py) | 8000 | Sovereign Core — NOT in Concordia |
| MEMORY | 8005 | |
| MOUTH (TTS) | 8004 | External path `F:\Lumax\Models\...` |
| EARS (STT) | 8001 | |
| VITE | 5176 | `cmd.exe /c npm run dev` |
| XR_VESSEL (xr_app.py) | 8080 | API proxy |
| CREATIVE | 8003 | |
| SOUNDBOARD | 8006 | |
| TOPBAR | — | |
| AUTONOMOUS | — | |
| SMART_CONTEXT | 8103 | DUPLICATE of Concordia Node 1 |
| BOOKKEEPER | — | |
| TUNNEL (cloudflared) | — | |

### What's MISSING from BOTH launchers:
- `motor_daemon.py` — referenced by sleipnir but doesn't exist
- `motor_cortex.py` exists (88 lines, 4 tool schemas) but is completely orphaned

---

## Implementation Steps

### Step 1: Create `Backend/Cognition/motor_daemon.py`

A minimal FastAPI service on port 8110 that:
- Imports `motor_cortex.py`'s `get_motor_tools_schema()` and `format_sse_motor_event()`
- Provides endpoints:
  - `GET /health` — health check
  - `GET /motor/tools` — returns the 4 OpenAI-compatible tool schemas
  - `POST /motor/execute` — accepts `{tool_name, arguments}`, returns SSE-formatted event
  - `GET /motor/stream` — SSE stream endpoint for real-time motor events
- Runs via uvicorn on port 8110

```python
# motor_daemon.py — Minimal FastAPI wrapper for motor_cortex.py
# Launched by sleipnir_launcher.js as Node 5 (MOTOR-CORTEX-8110)

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor_cortex import get_motor_tools_schema, format_sse_motor_event
import asyncio
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="LUMAX Motor Cortex")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class MotorExecuteRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


@app.get("/health")
async def health():
    return {"status": "online", "service": "motor_cortex", "port": 8110}


@app.get("/motor/tools")
async def get_tools():
    return {"tools": get_motor_tools_schema()}


@app.post("/motor/execute")
async def execute_motor(req: MotorExecuteRequest):
    valid_tools = {t["function"]["name"] for t in get_motor_tools_schema()}
    if req.tool_name not in valid_tools:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {req.tool_name}")
    sse_event = format_sse_motor_event(req.tool_name, req.arguments)
    return {"sse_event": sse_event, "tool": req.tool_name, "args": req.arguments}


@app.get("/motor/stream")
async def motor_stream():
    async def event_generator():
        yield {"event": "connected", "data": "Motor Cortex SSE stream active"}

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8110)
```

### Step 2: Update `sleipnir_launcher.js`

Add 3 new worker nodes and fix the Motor Cortex node:

**Node 5 (FIX):** Change from `python Backend/Cognition/motor_daemon.py` to `python -m uvicorn Backend.Cognition.motor_daemon:app --port 8110 --host 127.0.0.1`

**Node 6 (NEW):** Sovereign Core on port 8000
```javascript
new SwarmWorkerNode(
    "SOVEREIGN-CORE-8000",
    "python",
    ["-m", "uvicorn", "Backend.Cognition.compagent:app", "--port", "8000", "--host", "127.0.0.1"]
)
```

**Node 7 (NEW):** XR Vessel API Proxy on port 8080
```javascript
new SwarmWorkerNode(
    "XR-VESSEL-8080",
    "python",
    ["-m", "uvicorn", "Frontend.XR_Vessel.xr_app:app", "--port", "8080", "--host", "127.0.0.1"]
)
```

**Node 8 (NEW):** Vite Dev Server on port 5176
```javascript
new SwarmWorkerNode(
    "VITE-DEV-5176",
    "cmd.exe",
    ["/c", "npm run dev"],
    { cwd: path.join(LUMAX_ROOT, "Frontend", "XR_Vessel") }
)
```

### Step 3: Deprecate `Start_LUMAX.ps1`

Rename to `Start_LUMAX.ps1.deprecated` with a header comment:
```powershell
# DEPRECATED — Use Start_Concordia.PS1 instead
# This file is kept for reference. The Diamond Concordia launcher
# now handles all service orchestration via sleipnir_launcher.js.
```

### Step 4: Add cloudflared tunnel to Concordia

Add Node 9 for the cloudflared tunnel:
```javascript
new SwarmWorkerNode(
    "CLOUDFLARED-TUNNEL",
    path.join(LUMAX_ROOT, "cloudflared.exe"),
    ["tunnel", "--config", "config.yml", "run"]
)
```

---

## Services NOT moved to Concordia (stay manual or in deprecated launcher):

| Service | Reason |
|---------|--------|
| MOUTH (TTS) | External path `F:\Lumax\Models\...` — machine-specific |
| EARS (STT) | Machine-specific hardware |
| CREATIVE | Optional, can be started on demand |
| SOUNDBOARD | Optional |
| TOPBAR | Optional UI tool |
| AUTONOMOUS | Optional agent |
| BOOKKEEPER | Optional monetization |
| MEMORY (8005) | Separate service, can be added later |

---

## Final Concordia Fleet (after changes):

| Node | Service | Port | Command |
|------|---------|------|---------|
| 1 | TokenSlayer | 8103 | `uvicorn smart_context:app --port 8103` |
| 2 | MCP Server | 8101 | `python lumax_mcp_server.py` |
| 3 | Core Solver | 8102 | `node lumax-solver.js` |
| 4 | Stardust | 8109 | `uvicorn stardust_encoder:app --port 8109` |
| 5 | Motor Cortex | 8110 | `uvicorn motor_daemon:app --port 8110` |
| 6 | Sovereign Core | 8000 | `uvicorn compagent:app --port 8000` |
| 7 | XR Vessel | 8080 | `uvicorn xr_app:app --port 8080` |
| 8 | Vite Dev | 5176 | `cmd.exe /c npm run dev` |
| 9 | Cloudflare Tunnel | — | `cloudflared tunnel run` |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| `compagent.py` may not work with `uvicorn Backend.Cognition.compagent:app` | Verify the FastAPI `app` object is at module level |
| `xr_app.py` may have issues with uvicorn module path | Test the import path `Frontend.XR_Vessel.xr_app:app` |
| Vite dev server may need `npm install` first | Document prerequisite |
| Port conflicts with existing services | Concordia watchdog already handles .env changes |
| `sse_starlette` dependency for motor_daemon.py | Add to requirements or use simple async generator |