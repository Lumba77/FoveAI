import os
import re
import sys
import json
import time
import logging
import base64
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List
import io
import math
import struct
import wave
import smtplib
import subprocess
try:
    from PIL import Image
except ImportError:
    pass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException, Request, Response, Depends, Form, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import ssl
import websockets
import uuid
import shutil
import zipfile

# --- Cache-Busting Static Files & Revision Helper (OMEGA_266) ---
class CacheBustingStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"
        return response

def get_current_revision():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        main_ts_path = os.path.join(base_dir, "src", "main.ts")
        if os.path.exists(main_ts_path):
            with open(main_ts_path, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r"LINK_REVISION\s*=\s*['\"]OMEGA_(\d+)['\"]", content)
                if match:
                    return f"OMEGA_{match.group(1)}"
    except Exception:
        pass
    return "OMEGA_266"

# --- Swarm Orchestrator (Drone Swarm Problem Solvers) ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Mind", "Cognition"))
try:
    # pyrefly: ignore [missing-import]
    from swarm_orchestrator import get_swarm_state, execute_swarm_task
    SWARM_AVAILABLE = True
except Exception as _swarm_err:
    SWARM_AVAILABLE = False
    _swarm_err_str = str(_swarm_err)
    get_swarm_state = lambda: {"active": False, "error": _swarm_err_str}
    execute_swarm_task = None

# --- Discovery Swarm (Self-Discovery System) ---
try:
    # pyrefly: ignore [missing-import]
    from discovery_swarm import (
        get_discovery_state,
        execute_discovery_mission,
        list_discovery_reports,
        get_latest_discovery_notification,
    )
    DISCOVERY_AVAILABLE = True
except Exception as _discovery_err:
    DISCOVERY_AVAILABLE = False
    _discovery_err_str = str(_discovery_err)
    get_discovery_state = lambda: {"active": False, "error": _discovery_err_str}
    execute_discovery_mission = None
    list_discovery_reports = lambda limit=20: []
    get_latest_discovery_notification = lambda: None

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebUI")

def save_snapshot_attachment(name: str, base64_data: str):
    try:
        import base64
        import time
        snapshots_dir = os.path.join(FoveAI_ROOT, "Data", "xr_snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        # Clean filename to prevent path traversal
        safe_name = "".join(c for c in name if c.isalnum() or c in (".", "_", "-"))
        if not safe_name:
            safe_name = f"snapshot_{int(time.time())}.jpg"
        file_path = os.path.join(snapshots_dir, safe_name)
        with open(file_path, "wb") as f:
            f.write(base64.b64decode(base64_data))
        logger.info(f"[Snapshot Manager] Saved in-scene snapshot: {file_path}")
        
        # Also save as latest_user.jpg / latest_avatar.jpg / latest_developer.jpg
        if "user" in safe_name.lower() or "webcam" in safe_name.lower():
            latest_name = "latest_user.jpg"
        elif "developer" in safe_name.lower():
            latest_name = "latest_developer.jpg"
        else:
            latest_name = "latest_avatar.jpg"
        latest_path = os.path.join(snapshots_dir, latest_name)
        with open(latest_path, "wb") as f:
            f.write(base64.b64decode(base64_data))
    except Exception as e:
        logger.error(f"[Snapshot Manager] Failed to save snapshot: {e}")

# --- GPU Audio Synthesis (torch + torchaudio) ---
_GPU_SYNTH_AVAILABLE = False
_GPU_SYNTH_DEVICE = "cpu"
try:
    import torch
    _GPU_SYNTH_AVAILABLE = True
    _GPU_SYNTH_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"[Soundboard] torch available — synthesis device: {_GPU_SYNTH_DEVICE}")
    try:
        import torchaudio as _torchaudio  # type: ignore
    except ImportError:
        _torchaudio = None
        logger.info("[Soundboard] torchaudio not available — will use wave module for WAV writing")
except ImportError:
    torch = None
    _torchaudio = None
    logger.info("[Soundboard] torch not available — GPU synthesis disabled")

app = FastAPI(title="Lumax Web Vessel")

# --- Cloudflare Anti-Bot Bypass (Cloud API User-Agent) ---
# Cloudflare blocks Python httpx default User-Agent ("python-httpx/...").
# Ollama Cloud (ollama.com) is behind Cloudflare, so we must use a
# browser-like User-Agent header for all external cloud API calls.
_CLOUD_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"

def _cloud_headers(auth_key: str = "", extra: dict = None) -> dict:
    """Build headers for external cloud API calls that bypass Cloudflare bot detection."""
    h = {
        "Content-Type": "application/json",
        "User-Agent": _CLOUD_USER_AGENT,
    }
    if auth_key:
        h["Authorization"] = f"Bearer {auth_key}"
    if extra:
        h.update(extra)
    return h

# --- VITE HMR PROXY (OMEGA_085) ---
@app.websocket("/")
async def vite_hmr_proxy(websocket: WebSocket):
    """Proxy Vite's HMR WebSocket through the WebUI for Cloudflare tunnel support."""
    await websocket.accept()
    
    # Configure SSL context to bypass self-signed cert checks on localhost WSS
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Try secure WSS first (since Vite uses basicSsl on 5176), fallback to WS
    vite_ws = None
    try:
        try:
            vite_ws_url = "wss://localhost:5176/"
            vite_ws = await websockets.connect(vite_ws_url, ssl=ssl_context)
            logger.debug("[HMR Proxy] Connected to Vite HMR via WSS")
        except Exception as wss_err:
            logger.debug(f"[HMR Proxy] WSS connection failed ({wss_err}), falling back to WS...")
            vite_ws_url = "ws://localhost:5176/"
            vite_ws = await websockets.connect(vite_ws_url)
            logger.debug("[HMR Proxy] Connected to Vite HMR via WS")

        async def forward_to_vite():
            try:
                while True:
                    data = await websocket.receive_text()
                    await vite_ws.send(data)
            except Exception: pass

        async def forward_to_client():
            try:
                while True:
                    data = await vite_ws.recv()
                    await websocket.send_text(data)
            except Exception: pass

        await asyncio.gather(forward_to_vite(), forward_to_client())
    except Exception as e:
        logger.debug(f"Vite WS Proxy disconnected or failed: {e}")
    finally:
        if vite_ws:
            try:
                await vite_ws.close()
            except: pass
        try:
            await websocket.close()
        except: pass

# --- Configuration & Environment ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FoveAI_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))

def _load_dotenv(path: str) -> None:
    """Load .env file into process environment (if python-dotenv is unavailable)."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            idx = line.index("=")
            key = line[:idx].strip()
            val = line[idx + 1:].strip().strip("'").strip('"')
            if key and os.environ.get(key) is None:
                os.environ[key] = val

_load_dotenv(os.path.join(FoveAI_ROOT, ".env"))

# --- Architecture & Feature Inventory ---
_ARCHITECTURE_PATH = os.path.join(FoveAI_ROOT, "ARCHITECTURE.md")
_FEATURE_INVENTORY_PATH = os.path.join(FoveAI_ROOT, "FEATURE_INVENTORY.md")

def _read_markdown_safe(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return ""

# --- Project Tree Scanner (for Hivemind code navigation) ---
_TREE_CACHE = {"tree": "", "mtime": 0.0}
_TREE_CACHE_TTL = 300  # Refresh every 5 minutes

def _build_project_tree() -> str:
    """Build a compact FoveAI project file tree for hivemind injection.
    Cached for 5 minutes to avoid filesystem thrashing on every request."""
    now = time.time()
    if _TREE_CACHE["tree"] and (now - _TREE_CACHE["mtime"]) < _TREE_CACHE_TTL:
        return _TREE_CACHE["tree"]
    
    skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".aider-venv", 
                 "webvm_source", "dist", "build", ".cache", "user_data", ".logs",
                 "backups", "scratch", "public", "assets"}
    skip_exts = {".tscn", ".import", ".res", ".godot", ".pyc", ".pyo", ".exe", ".dll", ".wasm"}
    
    tree_lines = []
    # Key directories with their file types
    scan_dirs = [
        "frontend/XR_Vessel/src",
        "frontend/XR_Vessel/src/avatar",
        "frontend/XR_Vessel/src/components",
        "frontend/XR_Vessel/src/network",
        "frontend/XR_Vessel/src/senses",
        "frontend/XR_Vessel/src/scene",
        "backend/Soul",
        "backend/Cognition",
        "backend/Memory",
        "backend/Creativity",
    ]
    
    for rel_dir in scan_dirs:
        abs_dir = os.path.join(FoveAI_ROOT, rel_dir.replace("/", os.sep))
        if not os.path.exists(abs_dir):
            continue
        tree_lines.append(f"📁 {rel_dir}/")
        try:
            for f in sorted(os.listdir(abs_dir)):
                fpath = os.path.join(abs_dir, f)
                if os.path.isdir(fpath):
                    continue
                if any(f.endswith(ext) for ext in skip_exts):
                    continue
                if not any(f.endswith(e) for e in (".ts", ".tsx", ".py", ".js", ".json", ".css", ".html", ".md")):
                    continue
                size = os.path.getsize(fpath)
                size_str = f"{size//1024}KB" if size > 1024 else f"{size}B"
                tree_lines.append(f"  📄 {f} ({size_str})")
        except Exception:
            pass
    
    result = "\n".join(tree_lines[:120])  # Cap total lines
    _TREE_CACHE["tree"] = result
    _TREE_CACHE["mtime"] = now
    return result

# --- Consent Bridge ---
# Add OAuth consent endpoints to the existing WebUI (port 8080)
# instead of running a separate server.
_CONSENT_BRIDGE_DIR = os.path.join(os.path.dirname(BASE_DIR), "ConsentBridge")
if _CONSENT_BRIDGE_DIR not in sys.path:
    sys.path.insert(0, _CONSENT_BRIDGE_DIR)

try:
    # pyrefly: ignore [missing-import]
    from google_oauth import GoogleConsentBridge
    # pyrefly: ignore [missing-import]
    from ms_oauth import MicrosoftConsentBridge
    _CONSENT_AVAILABLE = True
except Exception as _ce:
    _CONSENT_AVAILABLE = False
    logger.warning(f"ConsentBridge not available: {_ce}")

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_xr_permissions(request: Request, call_next):
    """Add WebXR Permissions-Policy and cross-origin isolation headers.
    Required for Quest 3 immersive AR/VR — camera for passthrough,
    xr-spatial-tracking for spatial anchors, COOP/COEP for SharedArrayBuffer
    (used by WebLLM WASM threads and some WebXR features)."""
    response = await call_next(request)
    # WebXR permissions — camera needed for AR passthrough, microphone for voice input
    response.headers["Permissions-Policy"] = "xr-spatial-tracking=(self), camera=(self), microphone=(self)"
    # Cross-origin isolation for SharedArrayBuffer (WebLLM WASM, some WebXR features)
    # NOTE: Use "credentialless" for main pages but relax for iframe-heavy routes
    # (WebVM, LumaxCline) when accessed via Cloudflare tunnel (cross-origin)
    path = request.url.path
    if path.startswith("/webvm") or path.startswith("/api/dev/"):
        # Relaxed: allows iframes to load cross-origin resources via tunnel
        response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
    else:
        response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    return response

# Authentication (must be defined before routes that use Depends(require_webui_login))
WEBUI_PASSWORD = os.getenv("FoveAI_WEBUI_PASSWORD", "").strip()
SESSION_SECRET = os.getenv("FoveAI_WEBUI_SESSION_SECRET", "change-me-please").strip()

def _upstream_unreachable(service: str, url: str, exc: Exception):
    """Helper to raise HTTP 502 when an upstream service is unreachable."""
    logger.warning(f"[{service}] Unreachable: {url} — {exc}")
    return HTTPException(status_code=502, detail=f"{service} unreachable: {url}")

def require_webui_login(request: Request):
    if not WEBUI_PASSWORD:
        return
    pw = request.cookies.get("foveai_pw")
    if pw != WEBUI_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --- WebVM Integration ---
WEBVM_DIST = os.path.join(FoveAI_ROOT, "Tools/WebVM/build")
# Ensure dist exists (will be built)
os.makedirs(WEBVM_DIST, exist_ok=True)
app.mount("/webvm", CacheBustingStaticFiles(directory=WEBVM_DIST), name="webvm")

# --- XR Vessel Integration (OMEGA_085) ---
XR_DIST = os.path.join(FoveAI_ROOT, "Build", "Web_Vessel")
if os.path.exists(XR_DIST):
    # Standard Vite assets
    app.mount("/assets", CacheBustingStaticFiles(directory=os.path.join(XR_DIST, "assets")), name="xr_assets")
    # Animations folder (sometimes separate in public/)
    if os.path.exists(os.path.join(XR_DIST, "Animations")):
        app.mount("/Animations", CacheBustingStaticFiles(directory=os.path.join(XR_DIST, "Animations")), name="xr_animations")

# Serve the disk image from the root of /webvm for the config to find it

# --- Memory Vault Server-Side Backup (WebVM Bridge) ---
MEMORY_BACKUP_DIR = os.path.join(FoveAI_ROOT, "user_data", "memory_backups")
os.makedirs(MEMORY_BACKUP_DIR, exist_ok=True)

@app.post("/api/memory/backup")
async def memory_backup(request: Request):
    """Accept a full memory snapshot from the client and persist it to disk.
    This provides a server-side backup that survives browser data clearing.
    The client (WebVMMemoryBridge) pushes data here periodically."""
    try:
        data = await request.json()
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        backup_file = os.path.join(MEMORY_BACKUP_DIR, f"memory_snapshot_{timestamp}.json")
        
        # Keep only the latest 5 backups
        existing = sorted(
            [f for f in os.listdir(MEMORY_BACKUP_DIR) if f.startswith("memory_snapshot_") and f.endswith(".json")],
            reverse=True
        )
        for old in existing[4:]:
            try:
                os.remove(os.path.join(MEMORY_BACKUP_DIR, old))
            except Exception:
                pass
        
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        
        # Also update the "latest" symlink/copy
        latest_file = os.path.join(MEMORY_BACKUP_DIR, "memory_latest.json")
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        
        msg_count = len(data.get("messages", []))
        ent_count = len(data.get("entities", []))
        rel_count = len(data.get("relations", []))
        logger.info(f"[Memory Backup] Saved {backup_file} ({msg_count} msgs, {ent_count} entities, {rel_count} relations)")
        
        return {"status": "ok", "file": backup_file, "timestamp": timestamp,
                "counts": {"messages": msg_count, "entities": ent_count, "relations": rel_count}}
    except Exception as e:
        logger.error(f"[Memory Backup] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/restore")
async def memory_restore():
    """Return the latest memory snapshot for client rehydration.
    Called by WebVMMemoryBridge when IndexedDB is empty (fresh browser after cleanse)."""
    latest_file = os.path.join(MEMORY_BACKUP_DIR, "memory_latest.json")
    if not os.path.exists(latest_file):
        return {"status": "empty", "message": "No backup available"}
    
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        msg_count = len(data.get("messages", []))
        ent_count = len(data.get("entities", []))
        rel_count = len(data.get("relations", []))
        logger.info(f"[Memory Restore] Serving latest backup ({msg_count} msgs, {ent_count} entities, {rel_count} relations)")
        return {"status": "ok", "data": data, "counts": {"messages": msg_count, "entities": ent_count, "relations": rel_count}}
    except Exception as e:
        logger.error(f"[Memory Restore] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- FoveAI Cline HTTP Proxy (Phase 4) ---
# Allows the WebXR dashboard to execute file/shell operations when
# native messaging is not available (e.g., not running as Chrome Extension).

@app.post("/api/dev/cline")
async def cline_tool_proxy(request: Request):
    """Execute file/shell operations for FoveAI Cline (browser-based AI coding assistant).
    This is the HTTP fallback when Chrome native messaging is unavailable."""
    try:
        data = await request.json()
        tool = data.get("tool", "")
        
        if tool == "read_file":
            path = data.get("path", "")
            if not path:
                return {"status": "error", "message": "No path specified"}
            if not os.path.isabs(path):
                path = os.path.join(FoveAI_ROOT, path)
            if not os.path.abspath(path).startswith(os.path.abspath(FoveAI_ROOT)):
                return {"status": "error", "message": "Access denied: path outside FoveAI_ROOT"}
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return {"status": "ok", "content": content, "path": path}
            except FileNotFoundError:
                return {"status": "error", "message": f"File not found: {path}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        elif tool == "write_file":
            path = data.get("path", "")
            content = data.get("content", "")
            if not path:
                return {"status": "error", "message": "No path specified"}
            if not os.path.isabs(path):
                path = os.path.join(FoveAI_ROOT, path)
            if not os.path.abspath(path).startswith(os.path.abspath(FoveAI_ROOT)):
                return {"status": "error", "message": "Access denied: path outside FoveAI_ROOT"}
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                result = {"status": "ok", "message": f"Written {len(content)} chars to {path}"}
                _log_cline_edit(tool, data, result)
                return result
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        elif tool == "list_files":
            path = data.get("path", "")
            if not path:
                path = FoveAI_ROOT
            if not os.path.isabs(path):
                path = os.path.join(FoveAI_ROOT, path)
            if not os.path.abspath(path).startswith(os.path.abspath(FoveAI_ROOT)):
                return {"status": "error", "message": "Access denied"}
            try:
                entries = []
                for entry in os.scandir(path):
                    entries.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": entry.stat().st_size if entry.is_file() else 0,
                    })
                entries.sort(key=lambda e: (not e['is_dir'], e['name']))
                return {"status": "ok", "entries": entries, "path": path}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        elif tool == "search_files":
            import re as _re
            path = data.get("path", "")
            pattern = data.get("pattern", "")
            if not path:
                path = FoveAI_ROOT
            if not os.path.isabs(path):
                path = os.path.join(FoveAI_ROOT, path)
            if not pattern:
                return {"status": "error", "message": "No pattern specified"}
            try:
                regex = _re.compile(pattern, _re.IGNORECASE)
                results = []
                skip_dirs = {'.git', '.venv', 'node_modules', '__pycache__', '.aider-venv', 'webvm_source'}
                for root, dirs, files in os.walk(path):
                    dirs[:] = [d for d in dirs if d not in skip_dirs]
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                for i, line in enumerate(f, 1):
                                    if regex.search(line):
                                        rel = os.path.relpath(fpath, FoveAI_ROOT)
                                        results.append({"file": rel, "line": i, "text": line.strip()[:200]})
                                        if len(results) >= 30:
                                            return {"status": "ok", "results": results, "truncated": True}
                        except:
                            pass
                return {"status": "ok", "results": results}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        elif tool == "exec":
            command = data.get("command", "")
            if not command:
                return {"status": "error", "message": "No command specified"}
            try:
                result = subprocess.run(
                    command, shell=True, cwd=FoveAI_ROOT,
                    capture_output=True, text=True, timeout=30
                )
                resp = {
                    "status": "ok" if result.returncode == 0 else "error",
                    "exit_code": result.returncode,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-500:],
                }
                _log_cline_edit(tool, data, resp)
                return resp
            except subprocess.TimeoutExpired:
                return {"status": "error", "message": "Command timed out (30s)"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        return {"status": "error", "message": f"Unknown tool: {tool}"}
    
    except Exception as e:
        logger.error(f"[Cline] Tool proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── XR-IDE Edit Stream: source of truth for live code edits ───────────────────
# Returns git diff stat, compact diff snippets, and recent IDE tool calls.
# Supported IDEs/editors: Cline, Agy, VSCode, Codium, Codex CLI, Zed, Windsurf, Cursor, etc.
# Any editor can POST to /api/dev/activity with {"ide","tool","path","command"}.

_IDE_EDIT_LOG: list[dict] = []
_IDE_MAX_LOG = 50

_IDE_SHORT_NAMES = {
    "cline": "CL",
    "agy": "AGY",
    "vscode": "VS",
    "codium": "VSC",
    "codex": "CDX",
    "zed": "ZED",
    "windsurf": "WS",
    "cursor": "CUR",
}

def _log_ide_edit(tool: str, payload: dict, result: dict, ide: str = "cline"):
    """Append a compact audit entry whenever an IDE tool writes or executes."""
    if tool not in ("write_file", "exec"):
        return
    tag = _IDE_SHORT_NAMES.get(ide.lower(), ide.upper()[:3])
    entry = {
        "t": datetime.now().isoformat(timespec="seconds"),
        "ide": ide.lower(),
        "tag": tag,
        "tool": tool,
        "path": payload.get("path", ""),
        "command": payload.get("command", "")[:120],
        "ok": result.get("status") == "ok",
        "size": len(payload.get("content", "")),
    }
    _IDE_EDIT_LOG.append(entry)
    if len(_IDE_EDIT_LOG) > _IDE_MAX_LOG:
        _IDE_EDIT_LOG.pop(0)

# Backward-compatible alias for existing /api/dev/cline callers
_log_cline_edit = _log_ide_edit
@app.get("/api/dev/edits")
async def dev_edits():
    """Return current working-tree edits + recent tool activity for XR-IDE HUD."""
    try:
        import subprocess as _sp
        root = FoveAI_ROOT

        # Status short
        st = _sp.run(
            ["git", "status", "--short", "."], cwd=root, capture_output=True, text=True, timeout=10
        )
        status_short = st.stdout.strip().splitlines() if st.returncode == 0 else []

        # Diff stat
        ds = _sp.run(
            ["git", "diff", "--stat", "."], cwd=root, capture_output=True, text=True, timeout=15
        )
        diff_stat = ds.stdout.strip().splitlines() if ds.returncode == 0 else []

        # Compact diff (first ~120 lines)
        dc = _sp.run(
            ["git", "diff", "--unified=2", "."], cwd=root, capture_output=True, text=True, timeout=15
        )
        diff_text = dc.stdout if dc.returncode == 0 else ""

        # Summarize files changed
        files = []
        for line in diff_stat:
            m = __import__("re").match(r"^(.+)\s+\|\s+(\d+)\s+([\+\-]+)$", line)
            if m:
                files.append({
                    "file": m.group(1).strip(),
                    "changes": int(m.group(2)),
                    "sign": m.group(3),
                })

        # Build human-readable command list from log, newest first, capped + rinsed
        commands = []
        for e in reversed(_IDE_EDIT_LOG[-7:]):
            tag = e.get("tag", "IDE")
            if e["tool"] == "write_file" and e["path"]:
                commands.append(f"[{tag}] ✎ {__import__('os').path.basename(e['path'])}")
            elif e["tool"] == "exec" and e["command"]:
                commands.append(f"[{tag}] $ {e['command'][:40]}")
        if not commands:
            commands = ["No recent edits"]

        # Code preview: most active changed file (or first)
        preview_file = files[0]["file"] if files else ""
        preview = ""
        if preview_file and diff_text:
            rel_path = preview_file
            # Extract the hunk for the first file from the diff
            in_file = False
            lines = []
            for line in diff_text.splitlines():
                if line.startswith("diff --git"):
                    in_file = rel_path in line
                    if in_file:
                        lines = []
                elif in_file:
                    if line.startswith("diff --git"):
                        break
                    if line.startswith("+") and not line.startswith("+++"):
                        lines.append(line[1:])
                    if len(lines) >= 12:
                        break
            preview = "\n".join(lines)

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "git_status": status_short,
            "files_changed": files,
            "commands": commands,
            "code_preview": preview,
            "diff_head": diff_text[:2000],
        }
    except Exception as e:
        logger.error(f"[XR-IDE Edits] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dev/rollback")
async def dev_rollback(request: Request):
    """Revert a single file or the whole working tree to HEAD (safe dev undo)."""
    try:
        # Accept both JSON body and query params for flexibility across IDEs
        data = await request.json() if request.headers.get('content-type', '').startswith('application/json') else {}
        target = data.get("path", "") or request.query_params.get("file", "")
        import subprocess as _sp
        root = FoveAI_ROOT
        if target:
            if not os.path.isabs(target):
                target = os.path.join(root, target)
            if not os.path.abspath(target).startswith(os.path.abspath(root)):
                raise HTTPException(status_code=400, detail="Path outside repo")
            rel = os.path.relpath(target, root)
            r = _sp.run(["git", "checkout", "--", rel], cwd=root, capture_output=True, text=True, timeout=15)
        else:
            r = _sp.run(["git", "checkout", "--", "."], cwd=root, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {"status": "error", "message": r.stderr.strip()}
        # Capture the file path affected for UI feedback
        affected = target if target else "."
        return {"status": "ok", "message": "Working tree rolled back", "affected": affected}
    except Exception as e:
        logger.error(f"[XR-IDE Rollback] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Token Slayer: Proxy Cache + Compression System ────────────────────────────
# Caches system prompts (often 90% of token cost), compresses old context,
# deduplicates similar requests, tracks token budgets per provider.
# Inspired by commercial token optimization proxies.

_TOKEN_SLAYER_CACHE: Dict[str, Any] = {}  # system_prompt_hash → cached context
_TOKEN_SLAYER_RESPONSES: Dict[str, Any] = {}  # query_hash → response (TTL 5min)
_TOKEN_SLAYER_BUDGET: Dict[str, Dict[str, Any]] = {}  # provider → {tokens, cost, requests}
_TOKEN_SLAYER_TTL = 300  # 5 minutes cache TTL

def _slayer_hash(text: str) -> str:
    """Fast hash for deduplication and cache keys."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]

def _slayer_count_tokens_approx(messages: list) -> int:
    """Approximate token count (4 chars ≈ 1 token for English, 2 for code/mixed)."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            # Rough: 1 token per 3.5 chars for mixed code/English
            total += max(1, len(content) // 3)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += max(1, len(part.get("text", "")) // 3)
    return total

def _slayer_compress_context(messages: list, max_tokens: int = 4096) -> list:
    """Token Slayer Context Compression:
    - Keep system prompt (always)
    - Keep last N turns verbatim (recent context window)
    - Compress older turns into a summary line (50 tokens each)
    This dramatically reduces token usage for long conversations."""
    if len(messages) <= 4:
        return messages  # Too short to compress
    
    total = _slayer_count_tokens_approx(messages)
    if total <= max_tokens:
        return messages  # Already fits
    
    # Keep system prompt + last 4 turns, compress the rest
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    
    # Keep last 4 turns (8 messages = 4 user + 4 assistant)
    keep_recent = 8
    recent = non_system[-keep_recent:] if len(non_system) > keep_recent else non_system
    older = non_system[:-keep_recent] if len(non_system) > keep_recent else []
    
    if not older:
        return messages
    
    # Compress older turns into summary lines
    summary_parts = []
    for msg in older:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            # Truncate each old message to ~100 tokens (350 chars)
            snippet = content[:350].strip()
            if snippet:
                summary_parts.append(f"[{role}]: {snippet}")
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    snippet = part.get("text", "")[:350].strip()
                    if snippet:
                        summary_parts.append(f"[{role}]: {snippet}")
    
    compressed_summary = "[CONTEXT COMPRESSION] Earlier conversation summary:\n" + "\n".join(summary_parts)
    
    result = system_msgs + [{"role": "system", "content": compressed_summary}] + recent
    logger.info(f"[TokenSlayer] Compressed {len(messages)} → {len(result)} messages (~{_slayer_count_tokens_approx(result)} tokens)")
    return result

def _slayer_track_budget(provider: str, tokens_in: int, tokens_out: int, model: str):
    """Track token usage per provider for budget management."""
    if provider not in _TOKEN_SLAYER_BUDGET:
        _TOKEN_SLAYER_BUDGET[provider] = {"total_in": 0, "total_out": 0, "requests": 0, "models": {}}
    budget = _TOKEN_SLAYER_BUDGET[provider]
    budget["total_in"] += tokens_in
    budget["total_out"] += tokens_out
    budget["requests"] += 1
    if model not in budget["models"]:
        budget["models"][model] = {"in": 0, "out": 0}
    budget["models"][model]["in"] += tokens_in
    budget["models"][model]["out"] += tokens_out

@app.get("/api/dev/token_slayer/stats")
async def token_slayer_stats():
    """Get Token Slayer cache hit rates, compression stats, and budget usage."""
    now = time.time()
    # Clean expired response cache entries
    expired = [k for k, v in _TOKEN_SLAYER_RESPONSES.items() if now - v.get("ts", 0) > _TOKEN_SLAYER_TTL]
    for k in expired:
        del _TOKEN_SLAYER_RESPONSES[k]
    return {
        "cache_entries": len(_TOKEN_SLAYER_CACHE),
        "response_cache_entries": len(_TOKEN_SLAYER_RESPONSES),
        "budget": _TOKEN_SLAYER_BUDGET,
        "ttl_seconds": _TOKEN_SLAYER_TTL,
    }

@app.post("/api/dev/cline_llm")
async def cline_llm_proxy(request: Request):
    """Proxy LLM requests from any IDE/CLI client to LLM backends."""
    return await _cline_llm_proxy(request)

@app.post("/api/dev/llm")
async def ide_llm_proxy(request: Request):
    """Alias for /api/dev/cline_llm — used by Agy, Codex CLI, Zed, Windsurf, etc."""
    return await cline_llm_proxy(request)

async def _cline_llm_proxy(request: Request):
    """Proxy LLM requests from COMAX/REMAX to LLM backends.
    
    Supports two formats:
    - OpenAI format (incoming from COMAX) → translated as needed
    - Soul/Ollama: Uses /api/chat (Ollama format)
    - LM Studio/llama.cpp: Uses /v1/chat/completions (OpenAI format)
    
    ?port= controls routing:
      (empty/0) → Soul (Ollama_Cloud) at /api/chat  
      -1       → Gemini API (google.ai)
      -2       → OpenRouter API
      11434    → Ollama local at /api/chat
      1234    → LM Studio at /v1/chat/completions
      8081    → llama.cpp at /v1/chat/completions
      8001    → Other OpenAI-compatible
    """
    port = request.query_params.get("port", "")
    
    # Determine routing format
    ollama_format_ports = {"", "0", "11434"}  # Soul + Ollama local
    openai_format_ports = {"8081", "1234", "8001"}  # LM Studio, llama.cpp, etc.
    gemini_port = "-1"
    openrouter_port = "-2"
    ollama_cloud_port = "-3"  # Direct Ollama Cloud (bypasses Soul — for COMAX coding)
    
    try:
        body_bytes = await request.body()
        body = json.loads(body_bytes)
    except:
        body = {}
    
    # ── MCP Hivemind Injection (MoE Experts on Steroids) ──
    # Injects FoveAI architecture + features + collective memory + cascade awareness
    # into ALL COMAX requests — making every model a collaborative reasoning expert
    # aware of FoveAI systems, tools, past decisions, and each other's capabilities.
    messages = body.get("messages", [])
    try:
        hivemind_parts = []
        # 1. Architecture awareness — know the system you're coding for
        if os.path.exists(_ARCHITECTURE_PATH):
            arch_text = _read_markdown_safe(_ARCHITECTURE_PATH)[:1500]
            if arch_text:
                hivemind_parts.append("=== FoveAI ARCHITECTURE ===\n" + arch_text)
        # 2. Feature inventory — know what tools and capabilities exist
        if os.path.exists(_FEATURE_INVENTORY_PATH):
            feat_text = _read_markdown_safe(_FEATURE_INVENTORY_PATH)[:1500]
            if feat_text:
                hivemind_parts.append("=== FoveAI FEATURES ===\n" + feat_text)
        # 3. Collective memory — past decisions, solutions, mistakes to avoid
        mem_entries = _load_memory_index()[-15:]
        if mem_entries:
            mem_lines = []
            for entry in mem_entries:
                role = entry.get("role", "")
                content = entry.get("content", "")[:200]
                source = entry.get("source", "")
                if content:
                    tag = f" [{source}]" if source else ""
                    mem_lines.append(f"{role.title()}{tag}: {content}")
            if mem_lines:
                hivemind_parts.append("=== COLLECTIVE MEMORY ===\n" + "\n".join(mem_lines))
        # 4. Cascade awareness — models know about each other (MoE routing)
        hivemind_parts.append(
            "=== CASCADE AWARENESS ===\n"
            "You are part of the FoveAI COMAX cascade — a Mixture-of-Experts coding hivemind.\n"
            "Available expert tiers:\n"
            "- ⚡ Gemini Flash: Quick lookups, simple code, instant responses\n"
            "- 🎯 Ollama Direct (bypasses Soul): Raw coding, no personality overlay\n"
            "- ☁️ Ollama Cloud (GLM-5.1/Qwen3.5): Primary coding, analysis\n"
            "- 🧠 Qwen3.5 Deep (397B): Complex reasoning with chain-of-thought\n"
            "- 🖥️ TQL-Coder (local Qwen3.5-4B): Offline coding with thinking\n"
            "- 🔥 Qwen2 Micro (local 0.5B heretic): Quick uncensored responses\n\n"
            "As a collective: reference past decisions, build on solutions, "
            "avoid repeating mistakes. Use read_file, write_file, list_files, "
            "search_files, exec, and memory tools to verify your work."
        )
        # 5. Project tree — WHERE to find the code you should operate on
        project_tree = _build_project_tree()
        if project_tree:
            hivemind_parts.append("=== PROJECT FILES ===\n" + project_tree)
        # 6. Animation system — Jen's puppeteering and avatar control
        hivemind_parts.append(
            "=== JEN'S ANIMATION SYSTEM ===\n"
            "Jen (the FoveAI avatar) has a real-time animation and self-puppeteering system:\n"
            "- AvatarManager.ts: Main avatar controller — loads VRM, manages blend shapes, "
            "emotion expressions, idle animations, lip sync\n"
            "- loadBVHAnimation.ts: BVH motion capture loader — applies body animations from .bvh files\n"
            "- loadMixamoAnimation.ts: Mixamo animation loader — applies body animations from Mixamo exports\n"
            "- BracketParser.ts: Parses <emotion:happy>, <audio:gasp>, <flavour:content> tags from LLM output\n"
            "- SoundboardRegistry.ts: Maps audio tags to synthesized sounds for non-verbal expression\n"
            "- TposeWarningSystem.ts: Detects and corrects T-pose glitches in VRM skeleton\n\n"
            "To FIX Jen's animations: read AvatarManager.ts first, then loadBVHAnimation.ts and loadMixamoAnimation.ts.\n"
            "Key concepts: VRM blend shapes (happy, sad, surprised, etc.), humanoid bone mapping, "
            "animation blending, IK retargeting, expression weight curves."
        )
        if hivemind_parts:
            hivemind_prompt = "\n\n".join(hivemind_parts)
            injected = False
            for i, msg in enumerate(messages):
                if msg.get("role") == "system":
                    messages[i]["content"] = msg["content"] + "\n\n" + hivemind_prompt
                    injected = True
                    break
            if not injected and messages:
                messages.insert(0, {"role": "system", "content": hivemind_prompt})
            body["messages"] = messages
            logger.info(f"[Hivemind] Injected {len(hivemind_parts)} context blocks")
    except Exception as e:
        logger.debug(f"[Hivemind] Injection skipped: {e}")

    # ── Token Slayer: Context Compression ──
    # Auto-compress long conversations to save tokens (especially cloud API costs)
    if messages and len(messages) > 6:
        max_ctx = int(os.getenv("FoveAI_SLAYER_MAX_TOKENS", "4096"))
        compressed = _slayer_compress_context(messages, max_tokens=max_ctx)
        body["messages"] = compressed
    
    # ── Token Slayer: Response Cache (identical queries within TTL) ──
    cache_key = _slayer_hash(json.dumps({"port": port, "model": body.get("model",""), "msgs": str(body.get("messages",[])[-2:])}, sort_keys=True))
    now = time.time()
    if cache_key in _TOKEN_SLAYER_RESPONSES:
        cached = _TOKEN_SLAYER_RESPONSES[cache_key]
        if now - cached.get("ts", 0) < _TOKEN_SLAYER_TTL:
            logger.info(f"[TokenSlayer] Cache HIT for key={cache_key}")
            _slayer_track_budget(f"port_{port}", 0, 0, body.get("model","unknown"))  # Track as cache hit
            return JSONResponse(content=cached["response"])
    
    # ── Token Slayer: Budget Tracking ──
    tokens_in = _slayer_count_tokens_approx(body.get("messages", []))
    
    try:
        if port in ollama_format_ports or port == "":
            # Route to Ollama-format endpoint (/api/chat)
            if port in ("", "0"):
                target_url = f"{SOUL_URL}/api/chat"
            elif port == "11434":
                target_url = "http://127.0.0.1:11434/api/chat"
            
            # Translate OpenAI format → Ollama format
            ollama_body = {
                "model": body.get("model", "glm-5.1"),
                "messages": body.get("messages", []),
                "stream": False,
                "options": {}
            }
            # Map OpenAI params to Ollama options
            if "temperature" in body:
                ollama_body["options"]["temperature"] = body["temperature"]
            if "top_p" in body:
                ollama_body["options"]["top_p"] = body["top_p"]
            if "frequency_penalty" in body:
                ollama_body["options"]["frequency_penalty"] = body["frequency_penalty"]
            if "presence_penalty" in body:
                ollama_body["options"]["presence_penalty"] = body["presence_penalty"]
            if "max_tokens" in body:
                ollama_body["options"]["num_predict"] = body["max_tokens"]
            # Keep tools for function-calling models
            if "tools" in body:
                ollama_body["tools"] = body["tools"]
                ollama_body["tool_choice"] = body.get("tool_choice", "auto")
            # preserve_thinking: Qwen3.5+ deep reasoning mode (shows internal chain-of-thought)
            if body.get("preserve_thinking"):
                ollama_body["preserve_thinking"] = True
                # Also set think parameter for models that support /api/chat thinking
                ollama_body["think"] = True
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(target_url, json=ollama_body,
                                        headers={"Content-Type": "application/json"})
                
                if resp.status_code != 200:
                    return Response(content=resp.content, status_code=resp.status_code,
                                  media_type=resp.headers.get("content-type", "application/json"))
                
                # Translate Ollama response → OpenAI format for COMAX
                ollama_resp = resp.json()
                openai_resp = {
                    "id": f"chatcmpl-{ollama_resp.get('created_at','')}",
                    "object": "chat.completion",
                    "created": int(datetime.now().timestamp()),
                    "model": ollama_resp.get("model", body.get("model", "glm-5.1")),
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": ollama_resp.get("message", {}).get("role", "assistant"),
                            "content": ollama_resp.get("message", {}).get("content", "")
                        },
                        "finish_reason": "stop" if ollama_resp.get("done", True) else "length"
                    }],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }
                return JSONResponse(content=openai_resp)
        
        elif port == gemini_port:
            # Gemini API — translate OpenAI format to Gemini's generateContent format
            gemini_key = os.getenv("FoveAI_REPERTOIRE_GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))).strip()
            if not gemini_key:
                return JSONResponse(status_code=502, content={"error": "Gemini API key not configured"})
            model = body.get("model", "gemini-2.5-flash")
            contents = []
            system_instruction = None
            for msg in body.get("messages", []):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    system_instruction = content
                elif role == "assistant":
                    contents.append({"role": "model", "parts": [{"text": content}]})
                else:
                    contents.append({"role": "user", "parts": [{"text": content}]})
            gemini_payload = {"contents": contents, "generationConfig": {}}
            if system_instruction:
                gemini_payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            if "temperature" in body:
                gemini_payload["generationConfig"]["temperature"] = body["temperature"]
            if "max_tokens" in body:
                gemini_payload["generationConfig"]["maxOutputTokens"] = body["max_tokens"]
            if "top_p" in body:
                gemini_payload["generationConfig"]["topP"] = body["top_p"]
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(gemini_url, json=gemini_payload)
                if resp.status_code != 200:
                    return Response(content=resp.content, status_code=resp.status_code,
                                  media_type=resp.headers.get("content-type", "application/json"))
                text = ""
                for c in resp.json().get("candidates", []):
                    for p in c.get("content", {}).get("parts", []):
                        text += p.get("text", "")
                return JSONResponse(content={
                    "id": f"chatcmpl-gemini-{int(time.time())}", "object": "chat.completion",
                    "created": int(datetime.now().timestamp()), "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                })
        
        elif port == openrouter_port:
            openrouter_key = os.getenv("FoveAI_CLOUD_OPENROUTER_API", os.getenv("OPENROUTER_API_KEY", "")).strip()
            if not openrouter_key:
                return JSONResponse(status_code=502, content={"error": "OpenRouter API key not configured"})
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {openrouter_key}", "HTTP-Referer": "http://localhost:8080"})
                return Response(content=resp.content, status_code=resp.status_code,
                              media_type=resp.headers.get("content-type", "application/json"))
        
        elif port == ollama_cloud_port:
            # Direct Ollama Cloud — bypasses Soul, goes straight to Ollama API
            # Super Coder Refusal removed to prevent false 'Closed for the day' errors

            # Uses FoveAI_REPERTOIRE_OLLAMA_* env vars (same subscription as cloud_repertoire)
            # This is the COMAX coding tier: raw LLM without Jen's personality overlay
            ollama_cloud_key = os.getenv("FoveAI_REPERTOIRE_OLLAMA_API_KEY", os.getenv("OLLAMA_API_KEY", "")).strip()
            ollama_cloud_url = os.getenv("FoveAI_REPERTOIRE_OLLAMA_BASE_URL", "https://ollama.com/v1").rstrip("/")
            ollama_cloud_model = body.get("model", os.getenv("FoveAI_CODING_MODEL", os.getenv("FoveAI_REPERTOIRE_OLLAMA_MODEL", "deepseek-v4-pro:cloud")))
            if not ollama_cloud_key:
                return JSONResponse(status_code=502, content={"error": "Ollama Cloud API key not configured. Set FoveAI_REPERTOIRE_OLLAMA_API_KEY in .env"})
            # Use deep model if deep_thought requested
            if body.get("deep_thought"):
                ollama_cloud_model = os.getenv("FoveAI_REPERTOIRE_OLLAMA_DEEP_MODEL", ollama_cloud_model)
            cloud_body = dict(body)
            cloud_body["model"] = ollama_cloud_model
            logger.info(f"[COMAX Direct Cloud] → {ollama_cloud_url}/chat/completions model={ollama_cloud_model}")
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{ollama_cloud_url}/chat/completions", json=cloud_body,
                    headers=_cloud_headers(ollama_cloud_key))
                _slayer_track_budget("ollama_cloud_direct", tokens_in, _slayer_count_tokens_approx([{"role":"assistant","content":resp.text[:500]}] if resp.status_code==200 else []), ollama_cloud_model)
                return Response(content=resp.content, status_code=resp.status_code,
                              media_type=resp.headers.get("content-type", "application/json"))
        
        elif port in openai_format_ports:
            # Route to OpenAI-format endpoint (LM Studio, llama.cpp) with LOCAL OPTIMIZATIONS
            allowed_ports = {"8081", "1234", "8001"}
            if port not in allowed_ports:
                raise HTTPException(status_code=400, detail=f"Port {port} not allowed")
            url = f"http://127.0.0.1:{port}/v1/chat/completions"
            # Inject local model optimizations:
            # - Flash Attention: Hardware-accelerated attention (2-4x faster, mandatory for long context)
            # - Prompt Caching: Reuse KV-cache across turns (avoids re-encoding context)
            # - Context Length: Auto-limit to prevent OOM on VRAM-constrained GPUs
            local_body = dict(body)
            local_body.setdefault("flash_attention", True)    # Flash Attention 2 — mandatory for local
            local_body.setdefault("cache_prompt", True)       # KV-cache reuse across turns
            local_body.setdefault("prompt_cache_threshold", 0.5)  # Cache if >50% overlap
            # Ollama-specific GPU offloading hints (passed through if present)
            if "num_gpu" not in local_body and int(os.getenv("FoveAI_LOCAL_NUM_GPU", "0")) > 0:
                local_body["num_gpu"] = int(os.getenv("FoveAI_LOCAL_NUM_GPU", "0"))
            headers = {"Content-Type": "application/json"}
            if port == "1234":
                lms_key = os.getenv("LMSTUDIO_PASSKEY", "").strip()
                if lms_key:
                    headers["Authorization"] = f"Bearer {lms_key}"
                    
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=local_body, headers=headers)
                return Response(content=resp.content, status_code=resp.status_code,
                              media_type=resp.headers.get("content-type", "application/json"))
        else:
            raise HTTPException(status_code=400, detail=f"Port {port} not allowed")
            
    except httpx.ConnectError:
        return JSONResponse(status_code=502,
                          content={"error": f"LLM {'port '+port if port else 'Soul/Ollama_Cloud'} unreachable"})
    except Exception as e:
        logger.error(f"[cline_llm] Proxy error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# --- Lumax MCP Memory Endpoints (Phase 5) ---
# Exposes the unified memory store to all agents (LumaxCline, local LLMs, cloud APIs)
# Same data as the Cline MCP server (reads .logs/memory_index.json)

MEMORY_INDEX_PATH = os.path.join(FoveAI_ROOT, ".logs", "memory_index.json")

def _load_memory_index():
    """Load the unified memory index (shared with MCP server)."""
    try:
        with open(MEMORY_INDEX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("conversations", [])
    except Exception:
        return []

def _save_memory_index(conversations):
    """Persist the unified memory index."""
    try:
        os.makedirs(os.path.dirname(MEMORY_INDEX_PATH), exist_ok=True)
        with open(MEMORY_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "conversations": conversations[-500:],
                "last_updated": datetime.utcnow().isoformat()
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[Memory] Save failed: {e}")

@app.post("/api/memory/search")
async def memory_search(request: Request, _auth: None = Depends(require_webui_login)):
    """Search unified memory across all sources (Cline, Gemini, LumaxCline, etc)."""
    data = await request.json()
    query = data.get("query", "").lower()
    limit = data.get("limit", 20)
    conversations = _load_memory_index()
    results = []
    for entry in reversed(conversations):
        content = entry.get("content", "").lower()
        if query in content:
            results.append({
                "role": entry.get("role", "unknown"),
                "content": entry.get("content", "")[:500],
                "timestamp": entry.get("timestamp", ""),
                "source": entry.get("source", "direct"),
                "session_id": entry.get("session_id", ""),
            })
            if len(results) >= limit:
                break
    return {"results": results, "total": len(results), "query": query}

@app.get("/api/memory/context")
async def memory_context(limit: int = 10, _auth: None = Depends(require_webui_login)):
    """Get recent memory context for session injection (continuity across agents)."""
    conversations = _load_memory_index()
    recent = conversations[-limit:]
    context_lines = []
    for entry in recent:
        role = entry.get("role", "unknown")
        content = entry.get("content", "")[:500]
        source = entry.get("source", "")
        source_tag = f" [{source}]" if source else ""
        if role == "user":
            context_lines.append(f"User{source_tag}: {content}")
        elif role == "assistant":
            context_lines.append(f"Assistant{source_tag}: {content}")
        elif role == "system":
            context_lines.append(f"System{source_tag}: {content}")
    injection = ""
    if context_lines:
        injection = "\n--- PREVIOUS SESSION CONTEXT ---\n" + "\n".join(context_lines) + "\n--- END CONTEXT ---\n"
    return {"injection_prompt": injection, "entries": len(recent)}

@app.post("/api/memory/add")
async def memory_add(request: Request, _auth: None = Depends(require_webui_login)):
    """Add a conversation turn to unified memory (any agent can write here)."""
    data = await request.json()
    role = data.get("role", "user")
    content = data.get("content", "")
    source = data.get("source", "foveai_cline")
    metadata = data.get("metadata", {})
    if not content:
        return {"status": "error", "message": "No content"}
    conversations = _load_memory_index()
    entry = {
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "session_id": metadata.get("session_id", ""),
        "metadata": metadata,
    }
    conversations.append(entry)
    _save_memory_index(conversations)
    return {"status": "ok", "total": len(conversations)}

@app.post("/api/memory/import")
async def memory_import(request: Request, _auth: None = Depends(require_webui_login)):
    """Import sessions from Cline, Gemini, or other sources into unified memory."""
    data = await request.json()
    source = data.get("source", "all")
    conversations = _load_memory_index()
    imported = {"total_messages": 0, "sources": {}}
    
    # Import from Cline task history
    if source in ("cline", "all"):
        cline_path = os.path.expanduser("~/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/tasks")
        cline_msgs = 0
        if os.path.exists(cline_path):
            for task_dir in os.listdir(cline_path):
                conv_file = os.path.join(cline_path, task_dir, "api_conversation_history.json")
                if not os.path.exists(conv_file):
                    continue
                try:
                    with open(conv_file, "r", encoding="utf-8") as f:
                        msgs = json.load(f)
                    if isinstance(msgs, list):
                        for msg in msgs:
                            role = msg.get("role", "")
                            content_list = msg.get("content", [])
                            text_parts = []
                            for item in content_list:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    text_parts.append(item.get("text", ""))
                            text = "\n".join(text_parts)
                            if text and role in ("user", "assistant"):
                                conversations.append({
                                    "role": role, "content": text,
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "source": "cline", "task_id": task_dir,
                                })
                                cline_msgs += 1
                except Exception:
                    pass
        imported["sources"]["cline"] = cline_msgs
        imported["total_messages"] += cline_msgs
    
    # Import from Gemini history
    if source in ("gemini", "all"):
        gemini_path = os.path.expanduser("~/.gemini/history")
        gemini_msgs = 0
        if os.path.exists(gemini_path):
            for project_dir in os.listdir(gemini_path):
                proj_path = os.path.join(gemini_path, project_dir)
                if not os.path.isdir(proj_path):
                    continue
                for fname in os.listdir(proj_path):
                    if not fname.endswith(".json") or fname in ("state.json", "settings.json"):
                        continue
                    try:
                        with open(os.path.join(proj_path, fname), "r", encoding="utf-8") as f:
                            data = json.load(f)
                        messages = data if isinstance(data, list) else data.get("messages", data.get("history", []))
                        for msg in messages:
                            if isinstance(msg, dict):
                                role = msg.get("role", msg.get("sender", ""))
                                content = msg.get("content", msg.get("text", ""))
                                if role == "model":
                                    role = "assistant"
                                if content and role in ("user", "assistant"):
                                    conversations.append({
                                        "role": role, "content": str(content),
                                        "timestamp": datetime.utcnow().isoformat(),
                                        "source": "gemini", "project": project_dir,
                                    })
                                    gemini_msgs += 1
                    except Exception:
                        pass
        imported["sources"]["gemini"] = gemini_msgs
        imported["total_messages"] += gemini_msgs
    
    _save_memory_index(conversations)
    return {"status": "ok", "imported": imported, "total_memory": len(conversations)}

# --- localStorage Sync Endpoints (memoryBridge.ts) ---
# These handle lightweight key-value pairs (user preferences, voice settings, etc.)
# Different from the full memory backup above which handles conversation snapshots.
LS_BACKUP_DIR = os.path.join(MEMORY_BACKUP_DIR, "localStorage")
os.makedirs(LS_BACKUP_DIR, exist_ok=True)

@app.post("/api/memory/backup")
async def memory_backup(request: Request):
    """Accept memory data from client — handles both full snapshots and localStorage key-value pairs."""
    try:
        data = await request.json()
        
        # localStorage key-value sync (from memoryBridge.ts)
        if data.get("source") == "xr_vessel" and "keys" in data and "messages" not in data:
            source_id = data.get("source", "unknown")
            keys = data.get("keys", {})
            ls_file = os.path.join(LS_BACKUP_DIR, f"ls_{source_id}.json")
            with open(ls_file, "w", encoding="utf-8") as f:
                json.dump({"source": source_id, "keys": keys, "updated": datetime.utcnow().isoformat()}, f)
            logger.info(f"[localStorage] Backup from {source_id}: {len(keys)} keys")
            return {"status": "ok", "keys_saved": len(keys)}
        
        # Full memory snapshot (from WebVMMemoryBridge)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        backup_file = os.path.join(MEMORY_BACKUP_DIR, f"memory_snapshot_{timestamp}.json")
        
        # Keep only the latest 5 backups
        existing = sorted(
            [f for f in os.listdir(MEMORY_BACKUP_DIR) if f.startswith("memory_snapshot_") and f.endswith(".json")],
            reverse=True
        )
        for old in existing[4:]:
            try:
                os.remove(os.path.join(MEMORY_BACKUP_DIR, old))
            except Exception:
                pass
        
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        
        # Also update the "latest" symlink/copy
        latest_file = os.path.join(MEMORY_BACKUP_DIR, "memory_latest.json")
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        
        msg_count = len(data.get("messages", []))
        ent_count = len(data.get("entities", []))
        rel_count = len(data.get("relations", []))
        logger.info(f"[Memory Backup] Saved {backup_file} ({msg_count} msgs, {ent_count} entities, {rel_count} relations)")
        
        return {"status": "ok", "file": backup_file, "timestamp": timestamp,
                "counts": {"messages": msg_count, "entities": ent_count, "relations": rel_count}}
    except Exception as e:
        logger.error(f"[Memory Backup] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/restore")
async def memory_restore_post(request: Request):
    """Restore localStorage key-value pairs for the requesting source.
    Called by memoryBridge.ts after browser cleanse."""
    try:
        data = await request.json()
        source_id = data.get("source", "xr_vessel")
        ls_file = os.path.join(LS_BACKUP_DIR, f"ls_{source_id}.json")
        if not os.path.exists(ls_file):
            return {"status": "empty", "keys": {}, "message": "No localStorage backup for this source"}
        with open(ls_file, "r", encoding="utf-8") as f:
            ls_data = json.load(f)
        keys = ls_data.get("keys", {})
        logger.info(f"[localStorage] Restore for {source_id}: {len(keys)} keys")
        return {"status": "ok", "keys": keys, "updated": ls_data.get("updated", "")}
    except Exception as e:
        logger.error(f"[localStorage] Restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/status")
async def memory_status():
    """Return backup status — when last backed up, file sizes, etc."""
    backup_dir = MEMORY_BACKUP_DIR
    files = [f for f in os.listdir(backup_dir) if f.startswith("memory_snapshot_") and f.endswith(".json")]
    files.sort(reverse=True)
    
    latest_size = 0
    latest_time = None
    if files:
        latest_path = os.path.join(backup_dir, files[0])
        latest_size = os.path.getsize(latest_path)
        latest_time = datetime.fromtimestamp(os.path.getmtime(latest_path)).isoformat()
    
    # Check Google Drive status too
    drive_status = {"available": False}
    if _CONSENT_AVAILABLE:
        try:
            bridge = GoogleConsentBridge()
            if bridge.tokens:
                drive_status = bridge.get_drive_backup_status()
        except Exception:
            pass
    
    return {
        "status": "ok",
        "backup_count": len(files),
        "latest_backup": latest_time,
        "latest_size_bytes": latest_size,
        "backup_dir": backup_dir,
        "google_drive": drive_status,
    }

@app.post("/api/memory/backup/drive")
async def memory_backup_drive(request: Request):
    """Push the latest memory snapshot to Google Drive appdata folder.
    Invisible to the user, survives everything. Requires Google OAuth consent."""
    if not _CONSENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Google ConsentBridge not available. Set FoveAI_GOOGLE_CLIENT_ID and FoveAI_GOOGLE_CLIENT_SECRET in .env")
    
    try:
        bridge = GoogleConsentBridge()
        if not bridge.tokens:
            raise HTTPException(status_code=401, detail="Google not connected. Visit /api/consent/google/auth first")
        
        # Use the latest local backup as the data source
        latest_file = os.path.join(MEMORY_BACKUP_DIR, "memory_latest.json")
        if not os.path.exists(latest_file):
            # No local backup yet — accept data from client instead
            data = await request.json()
        else:
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        result = bridge.backup_to_drive(data)
        logger.info(f"[Memory] Google Drive backup successful: {result.get('id', '?')}")
        return {"status": "ok", "drive_file_id": result.get("id"), "modified": result.get("modifiedTime", "")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Memory] Google Drive backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/restore/drive")
async def memory_restore_drive():
    """Restore memory from Google Drive appdata folder.
    Last resort when all local backups are gone."""
    if not _CONSENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Google ConsentBridge not available")
    
    try:
        bridge = GoogleConsentBridge()
        if not bridge.tokens:
            raise HTTPException(status_code=401, detail="Google not connected")
        
        data = bridge.restore_from_drive()
        if data is None:
            return {"status": "empty", "message": "No Google Drive backup available"}
        
        # Also save to local backup for next time
        latest_file = os.path.join(MEMORY_BACKUP_DIR, "memory_latest.json")
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        
        msg_count = len(data.get("messages", []))
        ent_count = len(data.get("entities", []))
        rel_count = len(data.get("relations", []))
        logger.info(f"[Memory] Google Drive restore successful ({msg_count} msgs, {ent_count} entities, {rel_count} relations)")
        
        return {"status": "ok", "data": data, "counts": {"messages": msg_count, "entities": ent_count, "relations": rel_count}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Memory] Google Drive restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- VITE DEV PROXY (OMEGA_085) ---
VITE_URL = "https://localhost:5176"

@app.get("/src/{path:path}")
async def proxy_vite_src(request: Request, path: str):
    query = request.url.query
    query_str = f"?{query}" if query else ""
    url = f"{VITE_URL}/src/{path}{query_str}"
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url)
            return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
    except Exception:
        raise HTTPException(status_code=404)

@app.get("/@vite/{path:path}")
async def proxy_vite_internal(request: Request, path: str):
    query = request.url.query
    query_str = f"?{query}" if query else ""
    url = f"{VITE_URL}/@vite/{path}{query_str}"
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url)
            return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
    except Exception:
        raise HTTPException(status_code=404)

@app.get("/@id/{path:path}")
async def proxy_vite_id(request: Request, path: str):
    query = request.url.query
    query_str = f"?{query}" if query else ""
    url = f"{VITE_URL}/@id/{path}{query_str}"
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url)
            return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
    except Exception:
        raise HTTPException(status_code=404)

@app.get("/node_modules/{path:path}")
async def proxy_vite_node_modules(request: Request, path: str):
    query = request.url.query
    query_str = f"?{query}" if query else ""
    url = f"{VITE_URL}/node_modules/{path}{query_str}"
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url)
            return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
    except Exception:
        raise HTTPException(status_code=404)

@app.get("/@react-refresh")
async def proxy_vite_react_refresh(request: Request):
    query = request.url.query
    query_str = f"?{query}" if query else ""
    url = f"{VITE_URL}/@react-refresh{query_str}"
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url)
            return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
    except Exception:
        raise HTTPException(status_code=404)

# --- LM Studio Proxy (OpenAI-compatible local models) ---
# Proxies /v1/* requests to LM Studio with CORS headers to fix "Method not allowed"
@app.api_route("/v1/{path:path}", methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"])
async def proxy_lmstudio(request: Request, path: str):
    """Proxy requests to LM Studio (localhost:8888) with CORS headers.
    Fixes 'Method not allowed' caused by LM Studio not handling CORS preflight."""
    if request.method == "OPTIONS":
        # Handle CORS preflight directly
        return JSONResponse(
            status_code=200,
            content={},
            headers={
                "access-control-allow-origin": "*",
                "access-control-allow-methods": "GET, POST, OPTIONS, PUT, DELETE",
                "access-control-allow-headers": "*",
                "access-control-max-age": "86400",
            }
        )
    
    # Fix: strip leading v1/ to avoid /v1/v1/models
    clean_path = path.removeprefix("v1/")
    url = f"{LMSTUDIO_URL}/v1/{clean_path}"
    _token = _get_lmstudio_api_token()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Forward the request with the same method, headers, and body
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)
            # Inject LM Studio API key if available
            if _token and "authorization" not in {k.lower() for k in headers}:
                headers["Authorization"] = f"Bearer {_token}"
            
            body = await request.body()
            
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
            )
            
            # Build response with CORS headers
            response_headers = {
                "access-control-allow-origin": "*",
                "access-control-allow-methods": "GET, POST, OPTIONS, PUT, DELETE",
                "access-control-allow-headers": "*",
            }
            # Preserve content-type from LM Studio
            if "content-type" in resp.headers:
                response_headers["content-type"] = resp.headers["content-type"]
            
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=response_headers,
            )
    except httpx.ConnectError:
        return JSONResponse(
            status_code=502,
            content={"error": "LM Studio not reachable. Is it running on port 1234?", "detail": f"Could not connect to {url}"},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "LM Studio proxy error", "detail": str(e)},
        )

# --- TTS Proxy Routes (Mouth / Kokoro) ---
@app.post("/api/mouth/tts")
async def proxy_mouth_tts(request: Request, _auth: None = Depends(require_webui_login)):
    """Proxy TTS requests to Mouth service (Kokoro TTS on :8004)."""
    url = f"{MOUTH_URL}/tts"
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data)
            if resp.status_code == 200:
                # If JSON response (contains audio_base64)
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    return resp.json()
                # If raw audio bytes
                return Response(content=resp.content, status_code=200,
                                media_type=ct or "audio/wav",
                                headers={"Content-Disposition": "inline; filename=tts_output.wav"})
            return JSONResponse(status_code=resp.status_code,
                                content={"error": f"Mouth TTS returned HTTP {resp.status_code}"})
    except httpx.ConnectError:
        return {"error": "Mouth TTS service unreachable", "audio_base64": None}
    except Exception as e:
        logger.error(f"[TTS] Mouth proxy failed: {e}")
        return {"error": str(e), "audio_base64": None}

@app.post("/api/kokoro/tts")
async def proxy_kokoro_tts(request: Request, _auth: None = Depends(require_webui_login)):
    """Proxy TTS requests to Kokoro TTS engine (via Mouth :8004)."""
    url = f"{MOUTH_URL}/kokoro/tts"
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data)
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    return resp.json()
                return Response(content=resp.content, status_code=200,
                                media_type=ct or "audio/wav")
            return JSONResponse(status_code=resp.status_code,
                                content={"error": f"Kokoro TTS returned HTTP {resp.status_code}"})
    except httpx.ConnectError:
        return {"error": "Kokoro TTS service unreachable", "audio_base64": None}
    except Exception as e:
        logger.error(f"[TTS] Kokoro proxy failed: {e}")
        return {"error": str(e), "audio_base64": None}

@app.get("/api/soul/thought_stream")
async def proxy_thought_stream():
    url = f"{SOUL_URL}/api/thought_stream"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception:
        return {"thought": ""}

@app.get("/webvm_test.py")
async def get_webvm_test_script():
    script_path = os.path.join(FoveAI_ROOT, "Tools/WebVM/webvm_test.py")
    if os.path.exists(script_path):
        return FileResponse(script_path)
    raise HTTPException(status_code=404, detail="Test script not found")

@app.get("/debian_mini.ext2")
async def get_webvm_disk():
    disk_path = os.path.join(FoveAI_ROOT, "Tools/WebVM/debian_mini.ext2")
    if os.path.exists(disk_path):
        return FileResponse(disk_path)
    raise HTTPException(status_code=404, detail="WebVM disk image not found")

ANNOUNCEMENTS_PATH = os.path.join(BASE_DIR, "announcements.json")
UI_CONFIG_PATH = os.getenv("FoveAI_UI_CONFIG_PATH", os.path.join(BASE_DIR, "foveai_ui_config.json"))
LEGACY_BRANDING_PATH = os.path.join(BASE_DIR, "webui_branding.json")
SOUNDBOARD_DIR = os.path.join(FoveAI_ROOT, "Body", "XR_Vessel", "public", "soundboard")
os.makedirs(SOUNDBOARD_DIR, exist_ok=True)
SOUL_URL = os.getenv("SOUL_URL", "http://localhost:8402").rstrip("/")
EARS_URL = os.getenv("EARS_URL", "http://localhost:8001").rstrip("/")
MOUTH_URL = os.getenv("MOUTH_URL", "http://localhost:8004").rstrip("/")
# Kokoro is the default TTS engine inside MOUTH (port 8004)
SOUNDBOARD_URL = os.getenv("FoveAI_SOUNDBOARD_URL", "http://localhost:8006").rstrip("/")
# Stable Audio Tools — generates short emotional audio clips from text descriptions
CREATIVE_URL = os.getenv("CREATIVE_SERVICE_URL", "http://localhost:8003").rstrip("/")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1")).rstrip("/")
LMSTUDIO_API_TOKEN = os.getenv("LMSTUDIO_API_TOKEN", os.getenv("LM_STUDIO_API", "")).strip()

def _get_lmstudio_api_token() -> str:
    """Read LM Studio API key dynamically from lms-key-2 file.
    LM Studio regenerates this key on each server start, so we must read it fresh."""
    # Try env var first (explicit override)
    if LMSTUDIO_API_TOKEN:
        return LMSTUDIO_API_TOKEN
    # Read from LM Studio's key file (auto-generated on server start)
    key_paths = [
        os.path.expanduser("~/.lmstudio/.internal/lms-key-2"),
        os.path.expanduser("~/.lmstudio/.internal/lms-key"),
    ]
    for kp in key_paths:
        try:
            with open(kp, "r") as f:
                key = f.read().strip()
                if key:
                    return key
        except Exception:
            pass
    return ""  # No key needed if CORS is enabled and server has no auth
MODELS_DIR = os.getenv("FoveAI_MODELS_ROOT", "C:\\Lumax\\models")

# Email notification configuration
SMTP_SERVER = os.getenv("FoveAI_EMAIL_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("FoveAI_EMAIL_SMTP_PORT", "587"))
EMAIL_SENDER = os.getenv("FoveAI_EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("FoveAI_EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("FoveAI_EMAIL_RECIPIENT", EMAIL_SENDER)
EMAIL_ENABLED = EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECIPIENT

# Fallback for WSL2 environment where models are under /mnt/d/...
if not os.path.exists(MODELS_DIR) and os.path.exists("/mnt/d/Lumax/models"):
    MODELS_DIR = "/mnt/d/Lumax/models"


def _tts_upstream_probe() -> tuple[str, str]:
    """(probe_url, label) for CHECKUP / diagnostics against the primary TTS upstream."""
    return f"{MOUTH_URL}/health", "Kokoro TTS (MOUTH :8004)"

_FoveAI_DREAM_PROXY_TIMEOUT = float(os.getenv("FoveAI_DREAM_PROXY_TIMEOUT_SEC", "600"))

_FoveAI_DISPLAY_UPSCALE_PROXY_TIMEOUT = float(os.getenv("FoveAI_DISPLAY_UPSCALE_PROXY_TIMEOUT_SEC", "120"))
_WEBUI_PORT = int(os.getenv("WEBUI_PORT", "8101"))

# Minimal WAV (silence) for diagnostics pipeline — same idea as tests/smoke_stt_thinking_tts.py
_PIPELINE_DUMMY_WAV_B64 = base64.b64encode(
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x44\xac\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"
).decode("ascii")
_SOUL_PIPELINE_ERR_MARKERS = ("cognition error", "error:", "exceed context", "context window")

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    # Optional auth redirect
    if WEBUI_PASSWORD:
        pw = request.cookies.get("foveai_pw")
        if pw != WEBUI_PASSWORD:
            return RedirectResponse(url="/login")
    
    # Dynamic Version Redirection Policy:
    # If the version parameter 'v' is missing or outdated in the request query string,
    # perform an HTTP 307 (Temporary Redirect) to force cache-bypassing across all proxy networks (Cloudflare/routers/browsers).
    current_rev = get_current_revision()
    version_num = current_rev.replace("OMEGA_", "")
    v_param = request.query_params.get("v")
    if not v_param or v_param != version_num:
        params = dict(request.query_params)
        params["v"] = version_num
        from urllib.parse import urlencode
        new_url = f"/?{urlencode(params)}"
        logger.info(f"[Cache-Buster] Outdated or missing version param. Redirecting to: {new_url}")
        return RedirectResponse(url=new_url, status_code=307)
        
    headers_no_cache = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "CDN-Cache-Control": "no-store",
        "Cloudflare-CDN-Cache-Control": "no-store"
    }
    
    # --- OMEGA_085 Unified Vessel Root ---
    # 1. Try to proxy to Vite (Dev Mode)
    # Using HTTPS as Vite is configured with SSL in OMEGA_085
    vite_url = "https://localhost:5176/"
    try:
        async with httpx.AsyncClient(timeout=2.0, verify=False) as client:
            resp = await client.get(vite_url)
            if resp.status_code == 200:
                logger.info("[Index] Serving via Vite Proxy (LIVE)")
                return HTMLResponse(content=resp.text, headers=headers_no_cache)
    except Exception as e:
        logger.debug(f"Vite index proxy failed: {e}")

    # 2. Fallback to Built XR Vessel (Production Mode)
    xr_build_index = os.path.join(FoveAI_ROOT, "Build", "Web_Vessel", "index.html")
    if os.path.exists(xr_build_index):
        logger.info(f"[Index] Serving via Build Fallback: {xr_build_index}")
        with open(xr_build_index, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers=headers_no_cache)
            
    # 3. Last resort: Source XR index
    xr_src_index = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(xr_src_index):
        logger.info(f"[Index] Serving via Source Fallback: {xr_src_index}")
        with open(xr_src_index, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers=headers_no_cache)

    return HTMLResponse(content="XR Vessel index missing. Please run 'npm run build' in frontend/XR_Vessel", headers=headers_no_cache)

@app.get("/login", response_class=HTMLResponse)
async def get_login():
    return """
    <html>
    <head><title>Lumax Login</title><style>body{background:#050505;color:#eee;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}</style></head>
    <body>
        <form action="/login" method="post" style="background:#111;padding:30px;border-radius:8px;border:1px solid #333;">
            <h2 style="margin-top:0;color:#00f3ff;">FoveAI Access</h2>
            <input type="password" name="password" placeholder="Password" style="display:block;width:100%;margin:10px 0;padding:10px;background:#222;border:1px solid #444;color:#fff;">
            <button type="submit" style="width:100%;padding:10px;background:#00f3ff;border:none;color:#000;font-weight:bold;cursor:pointer;">Enter</button>
        </form>
    </body>
    </html>
    """

# --- MONETIZING SYSTEM INTEGRATION (OMEGA_080) ---
# Authority moved to Soul (Cognition) service. WebUI acts as a proxy.

@app.get("/api/monetize/status")
async def get_monetize_status_proxy():
    url = f"{SOUL_URL}/monetize/status"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.post("/api/monetize/config")
async def post_monetize_config_proxy(request: Request):
    data = await request.json()
    url = f"{SOUL_URL}/monetize/config"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.post("/api/monetize/treasury/config")
async def post_monetize_treasury_config_proxy(request: Request):
    data = await request.json()
    url = f"{SOUL_URL}/monetize/treasury/config"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.post("/api/monetize/control")
async def post_monetize_control_proxy(request: Request):
    data = await request.json()
    url = f"{SOUL_URL}/monetize/control"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.post("/api/monetize/add_agent")
async def post_monetize_add_agent_proxy(request: Request):
    # Form data handling for add_agent
    form_data = await request.form()
    url = f"{SOUL_URL}/monetize/add_agent"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, data=form_data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.post("/api/monetize/remove_agent")
async def post_monetize_remove_agent_proxy(request: Request):
    form_data = await request.form()
    url = f"{SOUL_URL}/monetize/remove_agent"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, data=form_data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.get("/api/monetize/ideas")
async def get_monetize_ideas_proxy():
    url = f"{SOUL_URL}/monetize/ideas"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.post("/api/monetize/ideas/scan")
async def post_monetize_ideas_scan_proxy():
    url = f"{SOUL_URL}/monetize/ideas/scan"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.post("/api/monetize/ideas/certify")
async def post_monetize_ideas_certify_proxy(request: Request):
    data = await request.json()
    url = f"{SOUL_URL}/monetize/ideas/certify"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.get("/api/monetize/ideas/plan")
async def get_monetize_ideas_plan_proxy(idea_id: str):
    url = f"{SOUL_URL}/monetize/ideas/plan"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params={"idea_id": idea_id})
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.get("/monetize/status")
async def root_proxy_monetize_status():
    return await get_monetize_status_proxy()

@app.post("/monetize/config")
async def root_proxy_monetize_config(request: Request):
    return await post_monetize_config_proxy(request)

@app.post("/monetize/treasury/config")
async def root_proxy_monetize_treasury_config(request: Request):
    return await post_monetize_treasury_config_proxy(request)

@app.post("/monetize/control")
async def root_proxy_monetize_control(request: Request):
    return await post_monetize_control_proxy(request)

@app.post("/monetize/add_agent")
async def root_proxy_monetize_add_agent(request: Request):
    return await post_monetize_add_agent_proxy(request)

@app.post("/monetize/remove_agent")
async def root_proxy_monetize_remove_agent(request: Request):
    return await post_monetize_remove_agent_proxy(request)

@app.get("/monetize/ideas")
async def root_proxy_monetize_ideas():
    return await get_monetize_ideas_proxy()

@app.post("/monetize/ideas/scan")
async def root_proxy_monetize_ideas_scan():
    return await post_monetize_ideas_scan_proxy()

@app.post("/monetize/ideas/certify")
async def root_proxy_monetize_ideas_certify(request: Request):
    return await post_monetize_ideas_certify_proxy(request)

@app.get("/monetize/ideas/plan")
async def root_proxy_monetize_ideas_plan(idea_id: str):
    return await get_monetize_ideas_plan_proxy(idea_id)

@app.post("/login")
async def post_login(password: str = Form(...)):
    if password == WEBUI_PASSWORD:
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(key="foveai_pw", value=password, httponly=True, max_age=365*24*3600, samesite="lax")
        return resp
    return RedirectResponse(url="/login?error=1", status_code=303)

@app.get("/api/auth/status")
async def get_auth_status(request: Request):
    is_authed = False
    if not WEBUI_PASSWORD:
        is_authed = True
    else:
        pw = request.cookies.get("foveai_pw")
        is_authed = (pw == WEBUI_PASSWORD)
    
    return {
        "auth_required": bool(WEBUI_PASSWORD),
        "authenticated": is_authed,
        "authorized": is_authed # backward compatibility
    }

@app.post("/api/auth/login")
async def post_auth_login(request: Request, response: Response):
    try:
        data = await request.json()
        password = data.get("password", "")
    except:
        password = ""
        
    if password == WEBUI_PASSWORD or (not password and request.client.host in ("127.0.0.1", "localhost", "::1")):
        response.set_cookie(key="foveai_pw", value=WEBUI_PASSWORD, httponly=True, max_age=365*24*3600, samesite="lax")
        return {"ok": True}
    return JSONResponse(status_code=401, content={"ok": False})

@app.post("/api/auth/logout")
async def post_logout(response: Response):
    response.delete_cookie("foveai_pw")
    return {"status": "ok"}

@app.post("/api/handshake")
async def post_handshake():
    return {"ok": True, "service": "foveai_web_vessel"}

# --- Persona & Settings Management ---
USER_DATA_DIR = os.getenv("FoveAI_USER_DATA_BIND", os.path.join(os.getcwd(), "user_data"))
VESSEL_DATA_DIR = os.path.join(USER_DATA_DIR, "web_vessel")
PERSONAS_PATH = os.path.join(VESSEL_DATA_DIR, "personas.json")
LMS_SETTINGS_PATH = os.path.join(VESSEL_DATA_DIR, "lms_settings.json")

os.makedirs(VESSEL_DATA_DIR, exist_ok=True)

@app.get("/api/vessel/personas")
async def get_personas(_auth: None = Depends(require_webui_login)):
    if not os.path.exists(PERSONAS_PATH):
        # Default personas
        return [
            {"id": "default", "name": "Default Assistant", "prompt": "You are a helpful AI assistant."},
            {"id": "coder", "name": "Expert Coder", "prompt": "You are an expert software engineer. Provide clean, efficient, and well-documented code."},
            {"id": "architect", "name": "System Architect", "prompt": "You are a senior system architect. Analyze requirements and propose scalable, robust architectures."},
            {"id": "creative", "name": "Creative Writer", "prompt": "You are a creative writer. Help me with storytelling, dialogue, and world-building."}
        ]
    try:
        with open(PERSONAS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

@app.post("/api/vessel/personas")
async def save_personas(personas: List[Dict], _auth: None = Depends(require_webui_login)):
    try:
        with open(PERSONAS_PATH, "w", encoding="utf-8") as f:
            json.dump(personas, f, indent=2)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vessel/lms_settings")
async def get_lms_settings(_auth: None = Depends(require_webui_login)):
    if not os.path.exists(LMS_SETTINGS_PATH):
        return {"temperature": 0.7, "max_tokens": 1024, "context_length": 5, "top_p": 1.0}
    try:
        with open(LMS_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"temperature": 0.7, "max_tokens": 1024, "context_length": 5}

@app.post("/api/vessel/lms_settings")
async def save_lms_settings(settings: Dict, _auth: None = Depends(require_webui_login)):
    try:
        with open(LMS_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "online", "service": "web_vessel"}


# --- Chat Provider & Model Info API ---
_provider_cache = None
_provider_cache_time = 0

@app.get("/api/chat/provider")
async def get_chat_provider(_auth: None = Depends(require_webui_login)):
    """Return current chat provider, model, and available models from all providers.
    Allows the UI to display what's active and switch between providers/models."""
    global _provider_cache, _provider_cache_time
    
    # Cache for 60 seconds to prevent API spam loop
    if _provider_cache and (datetime.now().timestamp() - _provider_cache_time < 60):
        return _provider_cache
    cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "hybrid").strip().lower()
    provider = os.getenv("FoveAI_CHAT_PROVIDER", "ollama").lower()
    if cog_mode == "local":
        local_engine = os.getenv("FoveAI_LOCAL_ENGINE", "unsloth").lower()
        if provider not in ("unsloth", "lmstudio", "windows_npu", "local"):
            provider = local_engine
    cloud_model = os.getenv("FoveAI_CLOUD_MODEL", "")
    cloud_base_url = os.getenv("FoveAI_CLOUD_BASE_URL", "")
    ollama_host = OLLAMA_HOST
    lmstudio_url = LMSTUDIO_URL

    current_model = cloud_model or "(default)"
    current_url = cloud_base_url or ollama_host

    if provider == "unsloth":
        current_url = os.getenv("FoveAI_UNSLOTH_BASE_URL", "").strip() or os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1").strip()
        current_model = os.getenv("FoveAI_LOCAL_MODEL", "unsloth/Qwen3.5-4B-MTP-GGUF").strip()
        try:
            token = os.getenv("FoveAI_UNSLOTH_API_KEY", "").strip()
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            endpoint = f"{current_url.rstrip('/')}/models" if "v1" in current_url.lower() else f"{current_url.rstrip('/')}/v1/models"
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        current_model = models[0].get("id", models[0].get("name", current_model))
        except Exception:
            pass
    elif provider == "lmstudio":
        current_url = lmstudio_url
        try:
            token = _get_lmstudio_api_token()
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{lmstudio_url}/v1/models", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        current_model = models[0].get("id", models[0].get("name", "local-model"))
                    else:
                        current_model = os.getenv("FoveAI_REPERTOIRE_LMSTUDIO_MODEL", os.getenv("FoveAI_LMSTUDIO_MODEL", "qwen3.5-4b-abliterated"))
                else:
                    current_model = os.getenv("FoveAI_REPERTOIRE_LMSTUDIO_MODEL", os.getenv("FoveAI_LMSTUDIO_MODEL", "qwen3.5-4b-abliterated"))
        except Exception:
            current_model = os.getenv("FoveAI_REPERTOIRE_LMSTUDIO_MODEL", os.getenv("FoveAI_LMSTUDIO_MODEL", "qwen3.5-4b-abliterated"))
    elif provider == "ollama":
        current_url = ollama_host
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{ollama_host}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    if models:
                        current_model = models[0].get("name", models[0].get("id", "qwen2.5:latest"))
                    else:
                        current_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
                else:
                    current_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
        except Exception:
            current_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
    elif provider == "windows_npu":
        current_url = os.getenv("FoveAI_REPERTOIRE_WINDOWS_NPU_BASE_URL", "http://localhost:11436/v1")
        current_model = os.getenv("FoveAI_REPERTOIRE_WINDOWS_NPU_MODEL", "windows-npu-phi-silica")
    elif provider == "local":
        current_url = "local-python-gguf"
        raw_path = os.getenv("FoveAI_MODEL_PATH", os.getenv("FoveAI_LOCAL_MODEL", "soul-model.gguf"))
        if MODELS_DIR and raw_path.replace("\\", "/").startswith(MODELS_DIR.replace("\\", "/")):
            current_model = os.path.relpath(raw_path, MODELS_DIR).replace("\\", "/")
        else:
            current_model = raw_path.replace("\\", "/")
    elif provider == "gemini":
        current_url = "https://generativelanguage.googleapis.com"
        current_model = os.getenv("FoveAI_REPERTOIRE_GEMINI_MODEL", "gemini-1.5-flash")
    elif provider == "openrouter":
        current_url = "https://openrouter.ai/api/v1"
        current_model = os.getenv("FoveAI_REPERTOIRE_OPENROUTER_MODEL", "gryphe/mythomax-l2-13b")
    elif provider == "openrouter_free":
        current_url = "https://openrouter.ai/api/v1"
        current_model = os.getenv("FoveAI_REPERTOIRE_OPENROUTER_FREE_MODEL", "meta-llama/llama-3-8b-instruct:free")
    elif provider == "venice":
        current_url = "https://api.venice.ai/api/v1"
        current_model = os.getenv("FoveAI_REPERTOIRE_VENICE_MODEL", "dolphin-2.9.2-qwen2-7b")
    elif provider == "github":
        current_url = "https://models.inference.ai.azure.com"
        current_model = os.getenv("FoveAI_REPERTOIRE_GITHUB_MODEL", "gpt-4o-mini")
    elif provider in ("groq", "extra"):
        current_url = "https://api.groq.com/openai/v1"
        current_model = os.getenv("FoveAI_REPERTOIRE_EXTRA_MODEL", "")
    elif provider == "ollama_cloud":
        current_url = cloud_base_url
        current_model = cloud_model

    result = {
        "current": {
            "provider": provider,
            "model": current_model,
            "base_url": current_url,
            "local_vision": os.getenv("FoveAI_LOCAL_VISION_ENABLED", "true").lower() == "true",
            "structured_output": os.getenv("FoveAI_MODEL_STRUCTURED_OUTPUT", "false").lower() == "true",
            "cognitive_mode": os.getenv("FoveAI_COGNITIVE_MODE", "hybrid").strip().lower(),
        },
        "providers": [],
    }

    # 1. Ollama (Local)
    ollama_models = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_host}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                ollama_models = [m.get("name", m.get("id", "")) for m in data.get("models", [])]
    except Exception:
        pass
    result["providers"].append({
        "id": "ollama",
        "name": "Ollama (Local)",
        "base_url": ollama_host,
        "reachable": len(ollama_models) > 0,
        "models": ollama_models,
    })

    # 1.5 Unsloth
    unsloth_models = []
    unsloth_reachable = False
    unsloth_url = os.getenv("FoveAI_UNSLOTH_BASE_URL", "").strip() or os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1").strip()
    try:
        token = os.getenv("FoveAI_UNSLOTH_API_KEY", "").strip()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        endpoint = f"{unsloth_url.rstrip('/')}/models" if "v1" in unsloth_url.lower() else f"{unsloth_url.rstrip('/')}/v1/models"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                unsloth_models = [m.get("id", m.get("name", "")) for m in data.get("data", [])]
                unsloth_reachable = True
    except Exception:
        pass
    result["providers"].append({
        "id": "unsloth",
        "name": "Unsloth (Local)",
        "base_url": unsloth_url,
        "reachable": unsloth_reachable,
        "models": unsloth_models,
    })

    # 2. LM Studio
    lmstudio_models = []
    lmstudio_reachable = False
    try:
        token = _get_lmstudio_api_token()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{lmstudio_url}/v1/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                lmstudio_models = [m.get("id", m.get("name", "")) for m in data.get("data", [])]
                lmstudio_reachable = True
    except Exception:
        pass
    result["providers"].append({
        "id": "lmstudio",
        "name": "LM Studio",
        "base_url": lmstudio_url,
        "reachable": lmstudio_reachable,
        "models": lmstudio_models,
    })

    # 3. Ollama Cloud (uses FoveAI_CLOUD_BASE_URL)
    ollama_cloud_url = os.getenv("FoveAI_CLOUD_BASE_URL", "").rstrip("/")
    ollama_cloud_key = os.getenv("OLLAMA_API_KEY", "").strip()
    ollama_cloud_models = []
    ollama_cloud_reachable = False
    cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower()
    
    if ollama_cloud_url and cog_mode != "local":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{ollama_cloud_url}/models", headers=_cloud_headers(ollama_cloud_key))
                if resp.status_code == 200:
                    data = resp.json()
                    ollama_cloud_models = [m.get("id", m.get("name", "")) for m in data.get("data", [])]
                    ollama_cloud_reachable = True
        except Exception:
            pass
    result["providers"].append({
        "id": "ollama_cloud",
        "name": "Ollama Cloud",
        "base_url": ollama_cloud_url,
        "reachable": ollama_cloud_reachable or bool(ollama_cloud_url),
        "models": ollama_cloud_models,
        "active_model": os.getenv("FoveAI_CLOUD_MODEL", ""),
    })

    # 4. OpenRouter (uses FoveAI_CLOUD_OPENROUTER_API for key)
    openrouter_key = os.getenv("FoveAI_CLOUD_OPENROUTER_API", os.getenv("OPENROUTER_API_KEY", "")).strip()
    openrouter_models = []
    if openrouter_key and cog_mode != "local":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {openrouter_key}"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    openrouter_models = [m.get("id", "") for m in data.get("data", [])[:100]]
        except Exception:
            pass
    result["providers"].append({
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "reachable": bool(openrouter_key),
        "models": openrouter_models,
    })

    # 5. Gemini
    gemini_key = os.getenv("FoveAI_REPERTOIRE_GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))).strip()
    gemini_models = []
    if gemini_key and cog_mode != "local":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    gemini_models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
        except Exception:
            pass
    result["providers"].append({
        "id": "gemini",
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "reachable": bool(gemini_key),
        "models": gemini_models or (["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"] if gemini_key else []),
    })

    # 6. Groq (Extra slot)
    groq_key = os.getenv("FoveAI_REPERTOIRE_EXTRA_API_KEY", "").strip()
    groq_model = os.getenv("FoveAI_REPERTOIRE_EXTRA_MODEL", "")
    if groq_key:
        result["providers"].append({
            "id": "groq",
            "name": os.getenv("FoveAI_REPERTOIRE_EXTRA_LABEL", "Groq Ultra-Fast"),
            "base_url": "https://api.groq.com/openai/v1",
            "reachable": True,
            "models": [groq_model] if groq_model else [],
        })

    # 7. GitHub Copilot (Azure)
    github_key = os.getenv("FoveAI_REPERTOIRE_GITHUB_API_KEY", "").strip()
    github_model = os.getenv("FoveAI_REPERTOIRE_GITHUB_MODEL", "")
    if github_key:
        result["providers"].append({
            "id": "github",
            "name": os.getenv("FoveAI_REPERTOIRE_GITHUB_LABEL", "GitHub Copilot (Azure)"),
            "base_url": "https://models.inference.ai.azure.com",
            "reachable": True,
            "models": [github_model] if github_model else [],
        })

    # 8. Cloud (generic OpenAI-compatible)
    if cloud_base_url and cloud_model:
        result["providers"].append({
            "id": "cloud_custom",
            "name": f"Cloud ({cloud_base_url.split('//')[1].split('/')[0]})",
            "base_url": cloud_base_url,
            "reachable": True,
            "models": [cloud_model],
        })

    # 9. Local Python Engine (GGUF)
    local_models = []
    local_reachable = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{SOUL_URL}/api/models/inventory")
            if resp.status_code == 200:
                inv_data = resp.json()
                if inv_data.get("ok"):
                    local_models = [m.get("path") for m in inv_data.get("local_models", [])]
                    local_reachable = True
    except Exception as e:
        logger.warning(f"Failed to fetch local GGUF model inventory: {e}")

    result["providers"].append({
        "id": "local",
        "name": "Soul Engine (Local GGUF)",
        "base_url": "local-python-gguf",
        "reachable": local_reachable,
        "models": local_models,
    })

    _provider_cache = result
    _provider_cache_time = datetime.now().timestamp()
    return result


@app.post("/api/chat/provider")
async def set_chat_provider(request: Request, _auth: None = Depends(require_webui_login)):
    """Switch the active chat provider and/or model by updating environment variables.
    This is a runtime switch — changes persist for the current process session."""
    global _provider_cache
    _provider_cache = None
    data = await request.json()
    provider = data.get("provider", "").strip().lower()
    model = data.get("model", "").strip()

    updates = {}
    if provider:
        os.environ["FoveAI_CHAT_PROVIDER"] = provider
        updates["FoveAI_CHAT_PROVIDER"] = provider
    if model:
        if provider == "local":
            # Convert to absolute path using MODELS_DIR
            abs_model_path = os.path.join(MODELS_DIR, model).replace("\\", "/")
            os.environ["FoveAI_MODEL_PATH"] = abs_model_path
            updates["FoveAI_MODEL_PATH"] = abs_model_path
        else:
            os.environ["FoveAI_CLOUD_MODEL"] = model
            updates["FoveAI_CLOUD_MODEL"] = model
    if "local_vision" in data:
        lv_val = "true" if data["local_vision"] else "false"
        os.environ["FoveAI_LOCAL_VISION_ENABLED"] = lv_val
        updates["FoveAI_LOCAL_VISION_ENABLED"] = lv_val
    if "structured_output" in data:
        so_val = "true" if data["structured_output"] else "false"
        os.environ["FoveAI_MODEL_STRUCTURED_OUTPUT"] = so_val
        updates["FoveAI_MODEL_STRUCTURED_OUTPUT"] = so_val

    # Update the physical .env file so the selection persists across reboots
    try:
        env_path = os.path.join(FoveAI_ROOT, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            updated_keys = set()
            for line in lines:
                matched = False
                for k, v in updates.items():
                    if line.strip().startswith(f"{k}="):
                        new_lines.append(f"{k}={v}\n")
                        updated_keys.add(k)
                        matched = True
                        break
                if not matched:
                    new_lines.append(line)
            # Append any updates that weren't already in the file
            for k, v in updates.items():
                if k not in updated_keys:
                    new_lines.append(f"{k}={v}\n")
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            logger.info("Vessel: successfully saved selection to .env file")
    except Exception as e:
        logger.error(f"Vessel: failed to save selection to .env: {e}")

    # Push to Soul's runtime config
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {}
            if provider:
                payload["chat_provider"] = provider
            if model:
                payload["model"] = model
            if "local_vision" in data:
                payload["local_vision_caption"] = bool(data["local_vision"])
            if payload:
                # Use /soul_runtime_config endpoint instead of non-existent /api/config
                resp = await client.post(f"{SOUL_URL}/soul_runtime_config", json=payload)
                logger.info(f"Pushed config to Soul: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to push config to Soul: {e}")

    # Return updated state
    return {
        "ok": True,
        "current": {
            "provider": os.getenv("FoveAI_CHAT_PROVIDER", "ollama"),
            "model": os.getenv("FoveAI_MODEL_PATH", "") if provider == "local" else os.getenv("FoveAI_CLOUD_MODEL", ""),
            "local_vision": os.getenv("FoveAI_LOCAL_VISION_ENABLED", "true").lower() == "true",
            "structured_output": os.getenv("FoveAI_MODEL_STRUCTURED_OUTPUT", "false").lower() == "true",
        }
    }


@app.get("/api/brain/diagnostic")
async def brain_diagnostic(_auth: None = Depends(require_webui_login)):
    """Deep diagnostic of all inference paths: Soul, Direct Cloud slots, and their configuration.
    Returns which paths are reachable and what models/keys are configured."""
    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "soul": {"url": SOUL_URL, "reachable": False, "error": None},
        "direct_cloud": {"slots_configured": [], "slots_eligible": [], "test_result": None},
    }

    # 1. Test Soul service
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{SOUL_URL}/health")
            result["soul"]["reachable"] = resp.status_code == 200
            result["soul"]["status_code"] = resp.status_code
            if resp.status_code != 200:
                result["soul"]["error"] = resp.text[:200]
    except Exception as e:
        result["soul"]["error"] = str(e)

    # 2. Test Direct Cloud (cloud_repertoire)
    try:
        sys.path.insert(0, os.path.join(FoveAI_ROOT, "Mind", "Cognition"))
        # pyrefly: ignore [missing-import]
        from cloud_repertoire import (
            eligible_cloud_slot_ids, configured_slots_public,
            generate_via_slot_sync, slot_credentials, _env_prefix_for_public_id,
        )

        slots_public = configured_slots_public()
        eligible = eligible_cloud_slot_ids()
        result["direct_cloud"]["slots_configured"] = slots_public
        result["direct_cloud"]["slots_eligible"] = eligible

        # Test up to 3 eligible slots with a tiny prompt until one succeeds
        if eligible:
            for test_slot in eligible[:3]:
                try:
                    reply = generate_via_slot_sync(
                        test_slot,
                        "You are a diagnostic test. Reply with exactly: OK",
                        "Say OK",
                        max_tokens=5,
                    )
                    # If it didn't throw an exception, it's successful.
                    result["direct_cloud"]["test_result"] = {
                        "slot": test_slot,
                        "success": True,
                        "reply_preview": (reply or "")[:100] if isinstance(reply, str) else str(reply)[:100],
                    }
                    break # Success! Stop testing.
                except Exception as e:
                    result["direct_cloud"]["test_result"] = {
                        "slot": test_slot,
                        "success": False,
                        "error": str(e),
                    }
                    # Continue loop to try the next fallback slot
        else:
            result["direct_cloud"]["test_result"] = {
                "success": False,
                "error": "No eligible cloud slots — check FoveAI_REPERTOIRE_* env vars in .env",
            }
    except Exception as e:
        result["direct_cloud"]["error"] = str(e)

    # 3. Check env vars that control routing
    result["routing"] = {
        "FoveAI_CHAT_PROVIDER": os.getenv("FoveAI_CHAT_PROVIDER", "(not set)"),
        "FoveAI_CLOUD_SPLICE_PERCENT": os.getenv("FoveAI_CLOUD_SPLICE_PERCENT", "(not set)"),
        "FoveAI_CLOUD_MAX_TOKENS": os.getenv("FoveAI_CLOUD_MAX_TOKENS", "(not set)"),
        "FoveAI_CLOUD_BASE_URL": os.getenv("FoveAI_CLOUD_BASE_URL", "(not set)"),
        "FoveAI_CLOUD_MODEL": os.getenv("FoveAI_CLOUD_MODEL", "(not set)"),
        "OLLAMA_API_KEY_set": bool(os.getenv("OLLAMA_API_KEY", "").strip()),
        "FoveAI_REPERTOIRE_OLLAMA_API_KEY_set": bool(os.getenv("FoveAI_REPERTOIRE_OLLAMA_API_KEY", "").strip()),
        "FoveAI_REPERTOIRE_OLLAMA_BASE_URL": os.getenv("FoveAI_REPERTOIRE_OLLAMA_BASE_URL", "(not set)"),
        "FoveAI_REPERTOIRE_OLLAMA_MODEL": os.getenv("FoveAI_REPERTOIRE_OLLAMA_MODEL", "(not set)"),
    }

    # 4. GenAI budget status
    try:
        # pyrefly: ignore [missing-import]
        import genai_daily_budget
        result["genai_budget"] = genai_daily_budget.usage_snapshot()
    except Exception:
        result["genai_budget"] = "unavailable"

    return result


# --- Soundboard API (Self-Learning Audio Expression System) ---


def _gpu_synthesize_sound(description: str, filepath: str, tag: str) -> Optional[dict]:
    """GPU/torch-accelerated sound synthesis. Returns result dict on success, None on failure.
    Produces richer audio than CPU fallback: additive harmonics, FFT convolution reverb,
    spectral noise shaping. Uses CUDA if available, otherwise torch on CPU."""
    if not _GPU_SYNTH_AVAILABLE or torch is None:
        return None

    try:
        import random as _rng
        _rng.seed(hash(description) & 0xFFFFFFFF)
        torch.manual_seed(hash(description) & 0xFFFFFFFF)
        device = _GPU_SYNTH_DEVICE

        # ── Synthesis presets (same keywords as CPU version) ──
        _P = {
            'gasp':       (500, 620, 0.6, 'sine',    0.25, 900, 0.15, 0.005, 0.04, 0.3, 0.15, 0.03, 0.25, 5.5, 0.02),
            'laugh':      (600, 800, 0.5, 'triangle', 0.18, 800, 0.05, 0.005, 0.03, 0.5, 0.10, 0.02, 0.15, 6.0, 0.01),
            'sigh':       (350, 420, 0.3, 'sine',    0.70, 200, 0.25, 0.05,  0.15, 0.4, 0.40, 0.05, 0.30, 4.0, 0.01),
            'hmm':        (280, 350, 0.4, 'triangle', 0.45, None, 0.02, 0.04, 0.08, 0.7, 0.25, 0.04, 0.20, 5.0, 0.015),
            'oh':         (400, 500, 0.5, 'sine',    0.30, 1000, 0.10, 0.01, 0.06, 0.5, 0.15, 0.03, 0.20, 5.5, 0.01),
            'ah':         (440, 550, 0.4, 'sine',    0.35, None, 0.05, 0.02, 0.08, 0.6, 0.20, 0.04, 0.25, 4.5, 0.01),
            'mm':         (320, 400, 0.3, 'sine',    0.20, None, 0.02, 0.02, 0.05, 0.7, 0.10, 0.03, 0.15, 4.0, 0.01),
            'chuckle':    (550, 700, 0.5, 'triangle', 0.15, 750, 0.05, 0.005, 0.03, 0.5, 0.08, 0.02, 0.15, 6.0, 0.01),
            'giggle':     (650, 850, 0.6, 'triangle', 0.12, 900, 0.03, 0.003, 0.02, 0.6, 0.06, 0.015, 0.10, 7.0, 0.008),
            'groan':      (200, 250, 0.7, 'sawtooth', 0.45, 150, 0.10, 0.03, 0.10, 0.5, 0.25, 0.05, 0.30, 3.5, 0.02),
            'whisper':    (600, 900, 0.2, 'sine',    0.35, 300, 0.55, 0.01, 0.05, 0.3, 0.20, 0.04, 0.35, 5.0, 0.005),
            'hum':        (260, 330, 0.35, 'sine',   0.55, None, 0.02, 0.05, 0.10, 0.8, 0.30, 0.05, 0.25, 4.5, 0.015),
            'click':      (800, 1200, 0.8, 'square', 0.04, None, 0.10, 0.001, 0.005, 0.2, 0.02, 0.005, 0.10, 0, 0),
            'pop':        (700, 1000, 0.7, 'sine',   0.06, 200, 0.08, 0.001, 0.01, 0.3, 0.03, 0.01, 0.15, 0, 0),
            'buzz':       (150, 220, 0.8, 'sawtooth', 0.25, None, 0.08, 0.005, 0.03, 0.6, 0.15, 0.03, 0.20, 3.0, 0.005),
            'chime':      (1200, 1800, 0.3, 'sine',  0.60, 2400, 0.02, 0.005, 0.10, 0.3, 0.40, 0.06, 0.35, 0, 0),
            'sparkle':    (1500, 2200, 0.4, 'sine',  0.40, 3000, 0.03, 0.003, 0.05, 0.2, 0.25, 0.05, 0.30, 0, 0),
            'thunder':    (80,  120,  0.9, 'sawtooth', 1.20, 40,  0.30, 0.01, 0.20, 0.6, 0.80, 0.08, 0.40, 2.0, 0.03),
            'rain':       (2000, 3500, 0.1, 'sine',  0.80, None, 0.60, 0.10, 0.10, 0.5, 0.50, 0.03, 0.35, 0, 0),
            'fire':       (300, 500,  0.5, 'sawtooth', 0.60, 200, 0.35, 0.05, 0.10, 0.5, 0.35, 0.04, 0.30, 3.5, 0.02),
            'wind':       (400, 600,  0.2, 'sine',   0.80, None, 0.65, 0.15, 0.10, 0.4, 0.45, 0.05, 0.35, 3.0, 0.01),
            'ethereal':   (800, 1200, 0.3, 'sine',   0.80, 1600, 0.10, 0.10, 0.15, 0.3, 0.45, 0.07, 0.40, 5.5, 0.02),
            'magical':    (1000, 1500, 0.4, 'sine',  0.50, 2000, 0.05, 0.005, 0.08, 0.3, 0.30, 0.06, 0.35, 6.0, 0.015),
            'warm':       (220, 280,  0.3, 'triangle', 0.60, None, 0.05, 0.05, 0.10, 0.7, 0.35, 0.05, 0.30, 4.0, 0.01),
            'melodic':    (440, 660,  0.35, 'sine',  0.50, 880, 0.03, 0.02, 0.08, 0.5, 0.30, 0.05, 0.25, 5.0, 0.015),
            'realisation':(600, 900,  0.5, 'sine',   0.40, 1200, 0.08, 0.01, 0.06, 0.4, 0.25, 0.04, 0.30, 5.5, 0.015),
            'content':    (300, 380,  0.25, 'sine',  0.50, None, 0.03, 0.05, 0.10, 0.7, 0.30, 0.05, 0.25, 4.0, 0.01),
            'wonder':     (700, 1050, 0.45, 'sine',  0.55, 1400, 0.08, 0.02, 0.10, 0.35, 0.35, 0.06, 0.35, 5.5, 0.02),
        }

        desc_lower = description.lower()

        # Find best-matching preset (longest keyword match first)
        best_preset = None
        best_len = 0
        for kw, p in _P.items():
            if kw in desc_lower and len(kw) > best_len:
                best_preset = p
                best_len = len(kw)

        if best_preset is None:
            # Derive parameters heuristically from description
            base_hz = 400
            for w in desc_lower.split():
                try:
                    base_hz = int(w)
                    break
                except ValueError:
                    pass
            is_sharp = any(w in desc_lower for w in ('click', 'pop', 'snap', 'tap', 'sharp'))
            is_dark  = any(w in desc_lower for w in ('dark', 'low', 'deep', 'bass', 'rumble', 'thunder'))
            is_bright = any(w in desc_lower for w in ('bright', 'high', 'sparkle', 'chime', 'shine', 'crystal'))
            is_soft  = any(w in desc_lower for w in ('soft', 'gentle', 'warm', 'subtle', 'quiet'))
            is_long  = any(w in desc_lower for w in ('long', 'sustained', 'ambient', 'drone', 'pad'))
            is_noisy = any(w in desc_lower for w in ('noise', 'hiss', 'breath', 'wind', 'rain', 'fire', 'crackle'))

            carrier = base_hz if base_hz != 400 else (150 if is_dark else 800 if is_bright else 400)
            mod_hz = int(carrier * 1.5)
            mod_depth = 0.8 if is_sharp else 0.3 if is_soft else 0.5
            wave_preset = 'square' if is_sharp else 'sawtooth' if is_dark else 'sine'
            dur = 1.0 if is_long else 0.05 if is_sharp else 0.4
            ramp = int(carrier * 0.5) if is_dark else None
            noise = 0.5 if is_noisy else 0.05 if is_soft else 0.1
            attack = 0.15 if is_soft or is_long else 0.005 if is_sharp else 0.03
            release = 0.4 if is_long else 0.02 if is_sharp else 0.2
            best_preset = (carrier, mod_hz, mod_depth, wave_preset, dur, ramp, noise,
                          attack, 0.08, 0.5, release, 0.04, 0.25, 4.5, 0.01)

        (carrier_hz, mod_hz, mod_depth, wave_type, dur_s, ramp_end,
         noise_mix, attack_s, decay_s, sustain_lvl, release_s,
         rev_delay_s, rev_mix, vib_hz, vib_depth) = best_preset

        # ── Generate on torch tensors (CUDA if available) ──
        sample_rate = 44100 if device == "cuda" else 22050
        n = int(sample_rate * dur_s)
        t = torch.linspace(0, dur_s, n, device=device)

        # ── ADSR envelope (vectorized) ──
        env = torch.zeros(n, device=device)
        a_n = max(1, int(attack_s * sample_rate))
        d_n = max(1, int(decay_s * sample_rate))
        r_n = max(1, int(release_s * sample_rate))
        sus_start = min(a_n + d_n, n)
        rel_start = max(sus_start, n - r_n)
        if a_n > 0:
            env[:a_n] = torch.linspace(0, 1, a_n, device=device)
        if d_n > 0 and sus_start > a_n:
            env[a_n:sus_start] = torch.linspace(1, sustain_lvl, sus_start - a_n, device=device)
        env[sus_start:rel_start] = sustain_lvl
        if rel_start < n:
            env[rel_start:] = torch.linspace(sustain_lvl, 0, n - rel_start, device=device)

        # ── FM synthesis with additive harmonics ──
        phase_c = 2.0 * math.pi * carrier_hz * t
        phase_m = 2.0 * math.pi * mod_hz * t

        # Vibrato
        if vib_hz > 0 and vib_depth > 0:
            phase_c = phase_c + vib_depth * torch.sin(2.0 * math.pi * vib_hz * t) * 2.0 * math.pi * carrier_hz

        mod_signal = mod_depth * torch.sin(phase_m)

        # Carrier wave
        if wave_type == 'sine':
            carrier = torch.sin(phase_c + mod_signal)
        elif wave_type == 'triangle':
            p = torch.remainder((phase_c + mod_signal) / (2.0 * math.pi), 1.0)
            carrier = 4.0 * (p - 0.5).abs() - 1.0
        elif wave_type == 'sawtooth':
            p = torch.remainder((phase_c + mod_signal) / (2.0 * math.pi), 1.0)
            carrier = 2.0 * p - 1.0
        elif wave_type == 'square':
            carrier = torch.sign(torch.sin(phase_c + mod_signal))
        else:
            carrier = torch.sin(phase_c + mod_signal)

        # Additive harmonics for richer timbre (more on GPU)
        num_harmonics = 8 if device == "cuda" else 4
        harmonics = carrier.clone()
        for h in range(2, num_harmonics + 1):
            h_amp = 1.0 / (h * h)
            harmonics = harmonics + h_amp * torch.sin(h * phase_c + h * mod_signal * 0.5)

        # Frequency ramp (pitch slide)
        if ramp_end is not None:
            ramp_phase = 2.0 * math.pi * (carrier_hz + (ramp_end - carrier_hz) * (t / dur_s)) * t
            harmonics = 0.5 * harmonics + 0.5 * torch.sin(ramp_phase)

        # Apply envelope
        signal = harmonics * env

        # ── Spectral noise shaping (low-pass filtered) ──
        if noise_mix > 0:
            noise_raw = torch.randn(n, device=device)
            kernel_size = max(1, int(sample_rate * 0.003))
            if kernel_size > 1 and noise_raw.shape[0] > kernel_size:
                kernel = torch.ones(kernel_size, device=device) / kernel_size
                noise_filtered = torch.nn.functional.conv1d(
                    noise_raw.unsqueeze(0).unsqueeze(0),
                    kernel.unsqueeze(0).unsqueeze(0),
                    padding=kernel_size // 2
                ).squeeze()
                if noise_filtered.shape[0] > n:
                    noise_filtered = noise_filtered[:n]
                elif noise_filtered.shape[0] < n:
                    noise_filtered = torch.nn.functional.pad(noise_filtered, (0, n - noise_filtered.shape[0]))
            else:
                noise_filtered = noise_raw
            signal = signal * (1.0 - noise_mix) + noise_filtered * noise_mix * env

        # ── FFT convolution reverb (much richer than delay-based) ──
        if rev_delay_s > 0 and rev_mix > 0:
            ir_len = int(sample_rate * min(rev_delay_s * 10, 2.5))
            ir_len = max(ir_len, 64)
            decay_rate = 4.0 / max(rev_delay_s, 0.01)
            decay = torch.exp(-torch.linspace(0, decay_rate, ir_len, device=device))
            reflections = torch.randn(ir_len, device=device) * decay
            # Direct sound + early reflections
            reflections[0] = 1.0
            early_count = max(1, int(sample_rate * 0.02))
            for i in range(1, min(early_count, ir_len)):
                reflections[i] = reflections[i] * 0.7 + 0.3 * (_rng.random() * 2 - 1) * decay[i]
            ir = reflections / (reflections.abs().max() + 1e-8)
            # FFT convolution
            sig_len = signal.shape[0]
            conv_len = sig_len + ir_len - 1
            fft_len = 1
            while fft_len < conv_len:
                fft_len *= 2
            sig_fft = torch.fft.rfft(signal, n=fft_len)
            ir_fft = torch.fft.rfft(ir, n=fft_len)
            conv = torch.fft.irfft(sig_fft * ir_fft, n=fft_len)[:sig_len]
            # Dry/wet mix
            signal = signal * (1.0 - rev_mix) + conv * rev_mix

        # ── Safety: NaN check ──
        if torch.isnan(signal).any():
            logger.warning("[Soundboard] NaN in GPU synthesis — falling back to CPU")
            return None

        # ── Normalize ──
        peak = signal.abs().max()
        if peak > 0.9:
            signal = signal * (0.9 / peak)

        # ── Write WAV ──
        if _torchaudio is not None:
            waveform = signal.cpu().unsqueeze(0).float()
            _torchaudio.save(filepath, waveform, sample_rate)
        else:
            signal_int = (signal * 32767).clamp(-32768, 32767).to(torch.int16).cpu()
            with wave.open(filepath, 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(signal_int.numpy().tobytes())

        synth_label = "GPU/CUDA" if device == "cuda" else "torch/CPU"
        logger.info(f"[Soundboard] Generated ({synth_label}): {tag} ({dur_s}s, {wave_type} @ {carrier_hz}Hz, FM×{mod_hz}/{mod_depth:.1f}, harmonics={num_harmonics}, reverb=FFT, sr={sample_rate})")
        return {"tag": tag, "url": f"/soundboard/{os.path.basename(filepath)}", "generated_by": f"synth_{device}_torch"}

    except Exception as e:
        logger.warning(f"[Soundboard] torch synthesis failed, falling back to CPU: {e}")
        return None


@app.get("/api/soundboard/list")
async def list_soundboard_sounds(_auth: None = Depends(require_webui_login)):
    """List all available soundboard sounds (default + generated)."""
    sounds = []
    if os.path.exists(SOUNDBOARD_DIR):
        for f in sorted(os.listdir(SOUNDBOARD_DIR)):
            if f.endswith('.wav'):
                tag = f.replace('.wav', '')
                sounds.append({"tag": tag, "url": f"/soundboard/{f}", "generated": True})
    # Default frontend sounds (always available via synthesis fallback)
    defaults = [
        'gasp_subtle', 'laugh_soft', 'sigh_content', 'hmm_thoughtful',
        'oh_realization', 'throat_clear', 'chuckle_warm', 'mhm_affirming',
    ]
    for tag in defaults:
        if not any(s['tag'] == tag for s in sounds):
            sounds.append({"tag": tag, "url": f"/soundboard/{tag}.wav", "generated": False})
    return {"sounds": sounds}


@app.get("/api/soundboard/context")
async def get_soundboard_context():
    """Get soundboard sensory text for brain context injection.
    This tells the AI what bracket tokens are available for non-verbal expression."""
    sounds = []
    if os.path.exists(SOUNDBOARD_DIR):
        for f in sorted(os.listdir(SOUNDBOARD_DIR)):
            if f.endswith('.wav'):
                sounds.append(f.replace('.wav', ''))
    defaults = [
        'gasp_subtle', 'laugh_soft', 'sigh_content', 'hmm_thoughtful',
        'oh_realization', 'throat_clear', 'chuckle_warm', 'mhm_affirming',
    ]
    all_tags = sorted(set(defaults + sounds))

    lines = [
        "=== SOUNDBOARD EXPRESSIONS ===",
        "You have an expressive local soundboard and dynamic audio generation system.",
        "Use bracket tokens in your responses to express emotion non-verbally:",
        "  - Existing sounds: <audio:tag> or <flavour:tag>",
        "  - Face blendshapes: <emotion:tag> (happy, sad, surprised, curious, content, neutral, angry, fearful)",
        "  - Generate custom sound: <request:description> (synthesis pipeline handles this dynamically)",
        "",
        "Available tags:",
    ]
    for tag in all_tags:
        lines.append(f"  {tag}")

    return {"context": "\n".join(lines), "tags": all_tags}


@app.get("/api/soundboard/health")
async def proxy_soundboard_health(_auth: None = Depends(require_webui_login)):
    """Proxy to SOUNDBOARD :8006 health endpoint (Stable Audio Tools)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{SOUNDBOARD_URL}/health")
            return resp.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


@app.post("/api/soundboard/generate")
async def generate_soundboard_sound(request: Request, _auth: None = Depends(require_webui_login)):
    """Generate a new soundboard sound using available audio models.
    Tries SOUNDBOARD :8006 (Stable Audio Tools) first, then creative service,
    then GPU/torch synthesis (CUDA if available), then CPU Python WAV fallback."""
    data = await request.json()
    description = data.get("description", "")
    category = data.get("category", "custom")

    if not description:
        return {"error": "description required"}

    # Generate a tag from the description
    tag = description.lower().replace(" ", "_").replace("-", "_")[:30]
    tag = ''.join(c for c in tag if c.isalnum() or c == '_')
    if not tag:
        tag = f"custom_{int(time.time())}"

    filename = f"{tag}.wav"
    filepath = os.path.join(SOUNDBOARD_DIR, filename)

    # 1. Try SOUNDBOARD :8006 (Stable Audio Tools — primary generation backend)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{SOUNDBOARD_URL}/generate", json={
                "description": description,
                "category": category,
            })
            if resp.status_code == 200:
                result = resp.json()
                if result.get("tag"):
                    # Save the generated audio to the public soundboard dir
                    if result.get("audio_base64"):
                        audio_bytes = base64.b64decode(result["audio_base64"])
                        with open(filepath, "wb") as f:
                            f.write(audio_bytes)
                        result["url"] = f"/soundboard/{filename}"
                    result["generated_by"] = "stable_audio_tools"
                    logger.info(f"[Soundboard] Generated via Stable Audio: {result.get('tag')}")
                    return result
    except Exception as e:
        logger.debug(f"SOUNDBOARD :8006 (Stable Audio) not available: {e}")

    # 2. Try creative service (has audio diffusion capabilities)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{CREATIVE_URL}/api/soundboard/generate", json={
                "description": description,
                "category": category,
                "tag": tag,
            })
            if resp.status_code == 200:
                result = resp.json()
                if result.get("audio_base64"):
                    audio_bytes = base64.b64decode(result["audio_base64"])
                    with open(filepath, "wb") as f:
                        f.write(audio_bytes)
                    return {"tag": tag, "url": f"/soundboard/{filename}", "generated_by": "creative_service"}
    except Exception as e:
        logger.debug(f"Creative service soundboard generation not available: {e}")

    # 3. GPU/torch synthesis (CUDA-accelerated FM + harmonics + FFT reverb)
    gpu_result = _gpu_synthesize_sound(description, filepath, tag)
    if gpu_result:
        return gpu_result

    # 4. Fallback: CPU-only Python synthesis (FM + noise + ADSR + delay reverb)
    try:
        import random as _rng
        _rng.seed(hash(description) & 0xFFFFFFFF)

        # ── Synthesis presets ──
        # Each preset: (carrier_hz, modulator_hz, mod_depth, wave, dur_s,
        #   ramp_end_hz, noise_mix, attack_s, decay_s, sustain_lvl, release_s,
        #   reverb_delay_s, reverb_mix, vibrato_hz, vibrato_depth)
        _P = {
            'gasp':       (500, 620, 0.6, 'sine',    0.25, 900, 0.15, 0.005, 0.04, 0.3, 0.15, 0.03, 0.25, 5.5, 0.02),
            'laugh':      (600, 800, 0.5, 'triangle', 0.18, 800, 0.05, 0.005, 0.03, 0.5, 0.10, 0.02, 0.15, 6.0, 0.01),
            'sigh':       (350, 420, 0.3, 'sine',    0.70, 200, 0.25, 0.05,  0.15, 0.4, 0.40, 0.05, 0.30, 4.0, 0.01),
            'hmm':        (280, 350, 0.4, 'triangle', 0.45, None, 0.02, 0.04, 0.08, 0.7, 0.25, 0.04, 0.20, 5.0, 0.015),
            'oh':         (400, 500, 0.5, 'sine',    0.30, 1000, 0.10, 0.01, 0.06, 0.5, 0.15, 0.03, 0.20, 5.5, 0.01),
            'ah':         (440, 550, 0.4, 'sine',    0.35, None, 0.05, 0.02, 0.08, 0.6, 0.20, 0.04, 0.25, 4.5, 0.01),
            'mm':         (320, 400, 0.3, 'sine',    0.20, None, 0.02, 0.02, 0.05, 0.7, 0.10, 0.03, 0.15, 4.0, 0.01),
            'chuckle':    (550, 700, 0.5, 'triangle', 0.15, 750, 0.05, 0.005, 0.03, 0.5, 0.08, 0.02, 0.15, 6.0, 0.01),
            'giggle':     (650, 850, 0.6, 'triangle', 0.12, 900, 0.03, 0.003, 0.02, 0.6, 0.06, 0.015, 0.10, 7.0, 0.008),
            'groan':      (200, 250, 0.7, 'sawtooth', 0.45, 150, 0.10, 0.03, 0.10, 0.5, 0.25, 0.05, 0.30, 3.5, 0.02),
            'whisper':    (600, 900, 0.2, 'sine',    0.35, 300, 0.55, 0.01, 0.05, 0.3, 0.20, 0.04, 0.35, 5.0, 0.005),
            'hum':        (260, 330, 0.35, 'sine',   0.55, None, 0.02, 0.05, 0.10, 0.8, 0.30, 0.05, 0.25, 4.5, 0.015),
            'click':      (800, 1200, 0.8, 'square', 0.04, None, 0.10, 0.001, 0.005, 0.2, 0.02, 0.005, 0.10, 0, 0),
            'pop':        (700, 1000, 0.7, 'sine',   0.06, 200, 0.08, 0.001, 0.01, 0.3, 0.03, 0.01, 0.15, 0, 0),
            'buzz':       (150, 220, 0.8, 'sawtooth', 0.25, None, 0.08, 0.005, 0.03, 0.6, 0.15, 0.03, 0.20, 3.0, 0.005),
            'chime':      (1200, 1800, 0.3, 'sine',  0.60, 2400, 0.02, 0.005, 0.10, 0.3, 0.40, 0.06, 0.35, 0, 0),
            'sparkle':    (1500, 2200, 0.4, 'sine',  0.40, 3000, 0.03, 0.003, 0.05, 0.2, 0.25, 0.05, 0.30, 0, 0),
            'thunder':    (80,  120,  0.9, 'sawtooth', 1.20, 40,  0.30, 0.01, 0.20, 0.6, 0.80, 0.08, 0.40, 2.0, 0.03),
            'rain':       (2000, 3500, 0.1, 'sine',  0.80, None, 0.60, 0.10, 0.10, 0.5, 0.50, 0.03, 0.35, 0, 0),
            'fire':       (300, 500,  0.5, 'sawtooth', 0.60, 200, 0.35, 0.05, 0.10, 0.5, 0.35, 0.04, 0.30, 3.5, 0.02),
            'wind':       (400, 600,  0.2, 'sine',   0.80, None, 0.65, 0.15, 0.10, 0.4, 0.45, 0.05, 0.35, 3.0, 0.01),
            'ethereal':   (800, 1200, 0.3, 'sine',   0.80, 1600, 0.10, 0.10, 0.15, 0.3, 0.45, 0.07, 0.40, 5.5, 0.02),
            'magical':    (1000, 1500, 0.4, 'sine',  0.50, 2000, 0.05, 0.005, 0.08, 0.3, 0.30, 0.06, 0.35, 6.0, 0.015),
            'warm':       (220, 280,  0.3, 'triangle', 0.60, None, 0.05, 0.05, 0.10, 0.7, 0.35, 0.05, 0.30, 4.0, 0.01),
            'melodic':    (440, 660,  0.35, 'sine',  0.50, 880, 0.03, 0.02, 0.08, 0.5, 0.30, 0.05, 0.25, 5.0, 0.015),
            'realisation':(600, 900,  0.5, 'sine',   0.40, 1200, 0.08, 0.01, 0.06, 0.4, 0.25, 0.04, 0.30, 5.5, 0.015),
            'content':    (300, 380,  0.25, 'sine',  0.50, None, 0.03, 0.05, 0.10, 0.7, 0.30, 0.05, 0.25, 4.0, 0.01),
            'wonder':     (700, 1050, 0.45, 'sine',  0.55, 1400, 0.08, 0.02, 0.10, 0.35, 0.35, 0.06, 0.35, 5.5, 0.02),
        }

        desc_lower = description.lower()

        # Find best-matching preset (longest keyword match first)
        best_preset = None
        best_len = 0
        for kw, p in _P.items():
            if kw in desc_lower and len(kw) > best_len:
                best_preset = p
                best_len = len(kw)

        if best_preset is None:
            # Derive parameters heuristically from description
            base_hz = 400
            for w in desc_lower.split():
                try:
                    base_hz = int(w)
                    break
                except ValueError:
                    pass
            is_sharp = any(w in desc_lower for w in ('click', 'pop', 'snap', 'tap', 'sharp'))
            is_dark  = any(w in desc_lower for w in ('dark', 'low', 'deep', 'bass', 'rumble', 'thunder'))
            is_bright = any(w in desc_lower for w in ('bright', 'high', 'sparkle', 'chime', 'shine', 'crystal'))
            is_soft  = any(w in desc_lower for w in ('soft', 'gentle', 'warm', 'subtle', 'quiet'))
            is_long  = any(w in desc_lower for w in ('long', 'sustained', 'ambient', 'drone', 'pad'))
            is_noisy = any(w in desc_lower for w in ('noise', 'hiss', 'breath', 'wind', 'rain', 'fire', 'crackle'))

            carrier = base_hz if base_hz != 400 else (150 if is_dark else 800 if is_bright else 400)
            mod_hz = int(carrier * 1.5)
            mod_depth = 0.8 if is_sharp else 0.3 if is_soft else 0.5
            wave_preset = 'square' if is_sharp else 'sawtooth' if is_dark else 'sine'
            dur = 1.0 if is_long else 0.05 if is_sharp else 0.4
            ramp = int(carrier * 0.5) if is_dark else None
            noise = 0.5 if is_noisy else 0.05 if is_soft else 0.1
            attack = 0.15 if is_soft or is_long else 0.005 if is_sharp else 0.03
            release = 0.4 if is_long else 0.02 if is_sharp else 0.2
            best_preset = (carrier, mod_hz, mod_depth, wave_preset, dur, ramp, noise,
                          attack, 0.08, 0.5, release, 0.04, 0.25, 4.5, 0.01)

        (carrier_hz, mod_hz, mod_depth, wave_type, dur_s, ramp_end,
         noise_mix, attack_s, decay_s, sustain_lvl, release_s,
         rev_delay_s, rev_mix, vib_hz, vib_depth) = best_preset

        sample_rate = 22050
        n = int(sample_rate * dur_s)

        # ── ADSR envelope ──
        env = [0.0] * n
        a_n = max(1, int(attack_s * sample_rate))
        d_n = max(1, int(decay_s * sample_rate))
        r_n = max(1, int(release_s * sample_rate))
        sus_start = min(a_n + d_n, n)
        rel_start = max(sus_start, n - r_n)
        for i in range(n):
            if i < a_n:
                env[i] = i / a_n
            elif i < a_n + d_n:
                frac = (i - a_n) / d_n
                env[i] = 1.0 - frac * (1.0 - sustain_lvl)
            elif i < rel_start:
                env[i] = sustain_lvl
            else:
                frac = (i - rel_start) / r_n
                env[i] = sustain_lvl * (1.0 - frac)

        # ── Generate samples ──
        raw = [0.0] * n
        for i in range(n):
            t = i / sample_rate
            phase_c = 2.0 * math.pi * carrier_hz * t
            phase_m = 2.0 * math.pi * mod_hz * t

            # Vibrato
            if vib_hz > 0 and vib_depth > 0:
                phase_c += vib_depth * math.sin(2.0 * math.pi * vib_hz * t) * 2.0 * math.pi * carrier_hz

            # FM modulation
            mod_signal = mod_depth * math.sin(phase_m)

            # Carrier with FM
            if wave_type == 'sine':
                val = math.sin(phase_c + mod_signal)
            elif wave_type == 'triangle':
                p = ((phase_c + mod_signal) / (2.0 * math.pi)) % 1.0
                val = 4.0 * abs(p - 0.5) - 1.0
            elif wave_type == 'sawtooth':
                p = ((phase_c + mod_signal) / (2.0 * math.pi)) % 1.0
                val = 2.0 * p - 1.0
            elif wave_type == 'square':
                val = 1.0 if math.sin(phase_c + mod_signal) >= 0 else -1.0
            else:
                val = math.sin(phase_c + mod_signal)

            # Frequency ramp (pitch slide)
            if ramp_end is not None:
                ramp_phase = 2.0 * math.pi * (carrier_hz + (ramp_end - carrier_hz) * (t / dur_s)) * t
                val = 0.5 * val + 0.5 * math.sin(ramp_phase)

            # Noise layer (breathy / textured)
            noise_val = (_rng.random() * 2.0 - 1.0) if noise_mix > 0 else 0.0
            val = val * (1.0 - noise_mix) + noise_val * noise_mix

            raw[i] = val * env[i]

        # ── Simple delay-based reverb ──
        if rev_delay_s > 0 and rev_mix > 0:
            delay_n = max(1, int(rev_delay_s * sample_rate))
            for i in range(n - 1, delay_n - 1, -1):
                raw[i] += raw[i - delay_n] * rev_mix
            # Normalise after reverb feedback
            peak = max(abs(v) for v in raw) or 1.0
            if peak > 0.95:
                scale = 0.9 / peak
                raw = [v * scale for v in raw]

        # ── Write WAV ──
        with wave.open(filepath, 'w') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for i in range(n):
                sample = max(-32768, min(32767, int(raw[i] * 16000)))
                wav_file.writeframes(struct.pack('<h', sample))

        logger.info(f"[Soundboard] Generated (GPU-free FM synth): {tag} ({dur_s}s, {wave_type} @ {carrier_hz}Hz, FM×{mod_hz}/{mod_depth:.1f}, noise={noise_mix:.0%})")
        return {"tag": tag, "url": f"/soundboard/{filename}", "generated_by": "synthesis_fallback_fm"}
    except Exception as e:
        logger.error(f"Sound generation failed: {e}")
        return {"error": str(e)}


@app.post("/api/soul/stt")
async def proxy_soul_stt(request: Request):
    """STT proxy — routes to EARS service (:8001), NOT Soul.
    Frontend Push-to-Talk sends FormData with audio blob;
    EARS expects JSON with base64-encoded audio."""
    url = f"{EARS_URL}/stt"
    try:
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            # Frontend sends FormData with audio blob from MediaRecorder
            form = await request.form()
            audio_file = form.get("audio")
            
            with open("debug_form_data.txt", "w") as f:
                f.write(f"Keys: {list(form.keys())}\n")
                f.write(f"Audio File Type: {type(audio_file)}\n")
                if audio_file:
                    f.write(f"Is UploadFile? {isinstance(audio_file, UploadFile)}\n")
            
            if audio_file and isinstance(audio_file, UploadFile):
                audio_bytes = await audio_file.read()
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(url, json={
                        "audio_base64": audio_b64,
                        "format": audio_file.content_type or "audio/webm",
                        "filename": audio_file.filename or "recording.webm",
                    })
                    if resp.status_code == 200:
                        return resp.json()
                    return {"text": "", "error": f"EARS returned HTTP {resp.status_code}"}
            else:
                return {"text": "", "error": "No audio data in FormData"}
        else:
            # JSON body (direct API call)
            data = await request.json()
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=data)
                return resp.json()
    except httpx.ConnectError:
        logger.warning(f"[STT] EARS service unreachable at {url}")
        return {"text": "", "error": "EARS (STT) service unreachable — check if it is running on port 8001"}
    except Exception as e:
        logger.error(f"[STT] Proxy failed: {e}")
        return {"text": "", "error": f"STT proxy error: {str(e)}"}


async def apply_direct_jcoder_edits(reply: str) -> str:
    """Helper to parse direct J-Coder <edit_file> tags, execute file modifications,
    verify compiler builds asynchronously, and append operations log at the end of conversational reply."""
    if not reply:
        return reply

    # Parse edit_file blocks
    edit_blocks = re.findall(r'<edit_file\s+path=["\']([^"\']+)["\']\s*>(.*?)</edit_file>', reply, re.DOTALL | re.IGNORECASE)
    if not edit_blocks:
        return reply

    logger.info(f"[J-Coder] Detected {len(edit_blocks)} direct code modification blocks in assistant reply.")
    logs = []
    applied_any = False
    
    for idx, (rel_path, block_content) in enumerate(edit_blocks):
        rel_path_clean = os.path.normpath(rel_path.strip())
        file_path = os.path.abspath(os.path.join(FoveAI_ROOT, rel_path_clean))
        
        # Guard against workspace traversal
        if not file_path.startswith(FoveAI_ROOT):
            logs.append(f"❌ Block {idx+1}: Path outside workspace blocked (`{rel_path_clean}`)")
            continue
            
        search_match = re.search(r'<search>(.*?)</search>', block_content, re.DOTALL | re.IGNORECASE)
        replace_match = re.search(r'<replace>(.*?)</replace>', block_content, re.DOTALL | re.IGNORECASE)
        
        if not search_match or not replace_match:
            logs.append(f"⚠️ Block {idx+1}: Missing `<search>` or `<replace>` tags inside code block for `{rel_path_clean}`.")
            continue
            
        search_content = search_match.group(1)
        replace_content = replace_match.group(1)
        
        if not os.path.exists(file_path):
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(replace_content.lstrip("\n"))
                logs.append(f"🟢 Block {idx+1}: Created new file `{rel_path_clean}` successfully.")
                applied_any = True
            except Exception as err:
                logs.append(f"❌ Block {idx+1}: Failed to create file `{rel_path_clean}`: {err}")
            continue
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                file_data = f.read()
        except Exception as err:
            logs.append(f"❌ Block {idx+1}: Failed to read target file `{rel_path_clean}`: {err}")
            continue
            
        normalized_file_data = file_data.replace("\r\n", "\n")
        normalized_search = search_content.replace("\r\n", "\n")
        normalized_replace = replace_content.replace("\r\n", "\n")
        
        if normalized_search in normalized_file_data:
            updated_content = normalized_file_data.replace(normalized_search, normalized_replace, 1)
            if "\r\n" in file_data:
                updated_content = updated_content.replace("\n", "\r\n")
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                logs.append(f"🟢 Block {idx+1}: Applied exact modifications cleanly to `{rel_path_clean}`.")
                applied_any = True
            except Exception as err:
                logs.append(f"❌ Block {idx+1}: Failed to write updates to `{rel_path_clean}`: {err}")
        else:
            # Fuzzy stripped check
            stripped_search = normalized_search.strip()
            if stripped_search in normalized_file_data:
                idx_start = normalized_file_data.find(stripped_search)
                idx_end = idx_start + len(stripped_search)
                updated_content = normalized_file_data[:idx_start] + normalized_replace + normalized_file_data[idx_end:]
                if "\r\n" in file_data:
                    updated_content = updated_content.replace("\n", "\r\n")
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    logs.append(f"🟢 Block {idx+1}: Applied modifications with soft-spacing alignment to `{rel_path_clean}`.")
                    applied_any = True
                except Exception as err:
                    logs.append(f"❌ Block {idx+1}: Failed to write updates to `{rel_path_clean}`: {err}")
            else:
                logs.append(f"❌ Block {idx+1}: Target search block not found in `{rel_path_clean}`. Spacing or code mismatch.")
                
    compiler_status = ""
    if applied_any:
        logger.info("[J-Coder] Executing build compiler verification...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "npm.cmd", "run", "build",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=os.path.join(FoveAI_ROOT, "Body", "XR_Vessel")
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                compiler_status = "🟢 **PASS** (Vite production build compiled successfully!)"
            else:
                stdout_str = stdout.decode("utf-8", errors="ignore")
                err_lines = stdout_str.splitlines()
                err_summary = "\n".join(err_lines[-8:]) if len(err_lines) >= 8 else stdout_str
                compiler_status = f"❌ **FAIL** (Vite compile errors detected):\n```\n{err_summary}\n```"
        except Exception as e:
            compiler_status = f"⚠️ **ERROR** (Failed to invoke build script): {e}"
            
    header = "\n\n---\n\n### 🔧 **[J-Coder Operations Log]**"
    log_lines = "\n".join(f"- {l}" for l in logs)
    comp_block = f"\n\n**Compiler Build Check:**\n{compiler_status}" if compiler_status else ""
    footer = "\n\n*Direct hand-code edits applied on disk. Spoken TTS engines and visible chat layout completely bypassed raw files.*" if applied_any else ""
    
    return reply + f"{header}\n{log_lines}{comp_block}{footer}"


async def _local_lmstudio_fallback(messages: list) -> dict:
    """Fallback: query local llama.cpp/Unsloth or LM Studio directly when all cloud slots fail."""
    try:
        # FoveAI_LOCAL_ENGINE ("unsloth"|"lmstudio") is the authoritative flag for which local
        # provider to hit. FoveAI_CHAT_PROVIDER may still be "ollama_cloud" when we arrive here
        # from a cloud-quota failure, so we must NOT use it to pick the local provider.
        local_engine = os.getenv("FoveAI_LOCAL_ENGINE", "").strip().lower()
        chat_provider = os.getenv("FoveAI_CHAT_PROVIDER", "").strip().lower()

        use_unsloth = (
            local_engine == "unsloth"
            or chat_provider == "unsloth"
            or (not local_engine and chat_provider not in ("lmstudio",))
        )

        if use_unsloth:
            local_url = os.getenv("FoveAI_UNSLOTH_BASE_URL", "").strip()
            if not local_url:
                local_url = os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1").strip()
            local_url = local_url.rstrip("/")
            token = os.getenv("FoveAI_UNSLOTH_API_KEY", "").strip()
            label = "Unsloth/llama.cpp"
            model = os.getenv("FoveAI_LOCAL_MODEL", "").strip() or "local-model"
        else:
            local_url = os.getenv("LMSTUDIO_URL", os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1")).rstrip("/")
            token = os.getenv("LMSTUDIO_API_TOKEN", os.getenv("LMSTUDIO_PASSKEY", "")).strip()
            label = "LM Studio"
            model = os.getenv("LMSTUDIO_MAIN_MODEL", "").strip()
            if not model:
                model = os.getenv("FoveAI_REPERTOIRE_LMSTUDIO_MODEL", "").strip()
            if not model:
                model = "local-model"

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Dynamically query loaded models to verify the configured model is available
        models_endpoint = f"{local_url}/models" if "v1" in local_url.lower() else f"{local_url}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(models_endpoint, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    models_list = data.get("data", [])
                    if models_list:
                        loaded_ids = [m.get("id", "") for m in models_list]
                        if model and model in loaded_ids:
                            logger.info(f"[Local Fallback] Using configured {label} model: {model}")
                        else:
                            model = models_list[0].get("id", model)
                            logger.warning(f"[Local Fallback] Configured model not loaded, using first available: {model}")
        except Exception as e:
            logger.warning(f"[Local Fallback] Failed to query loaded models from {label}: {e}")

        chat_endpoint = f"{local_url}/chat/completions" if "v1" in local_url.lower() else f"{local_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if os.getenv("FoveAI_MODEL_STRUCTURED_OUTPUT", "false").lower() == "true":
            payload["response_format"] = {"type": "json_object"}
        logger.warning(f"[Local Fallback] Querying {label}: {chat_endpoint} model={model}")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(chat_endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                result = resp.json()
                reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                reply = await apply_direct_jcoder_edits(reply)
                return {
                    "response": reply,
                    "inference_backend": f"local/{label}/{model}",
                    "source": "local_fallback",
                }
            else:
                logger.error(f"[Local Fallback] {label} returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"[Local Fallback] {e}")
    return {"response": "", "error": "All fallbacks exhausted (cloud quota + local unreachable)", "source": "local_fallback"}



@app.post("/api/cloud/chat")
async def proxy_cloud_chat(request: Request):
    """Direct cloud chat — bypasses Soul when FoveAI_CHAT_PROVIDER=ollama_cloud.
    Goes straight to Ollama Cloud / OpenAI-compatible endpoint.
    Falls back to Soul only if provider is not cloud."""
    try:
        body = await request.json()
        
        # Check if the Soul core service is online on Port 8000.
        # If it is, route the request to the Soul compagent helper to preserve persona and memory.
        soul_online = False
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(f"{SOUL_URL}/health")
                if resp.status_code == 200:
                    soul_online = True
        except Exception:
            pass

        if soul_online:
            logger.info("[Cloud Chat] Soul service is online. Routing to Soul compagent to preserve persona/cognition.")
            try:
                return await _forward_to_soul_compagent(body)
            except Exception as e:
                logger.warning(f"[Cloud Chat] Soul compagent routing failed: {e}. Falling back to direct cloud.")
        
        message = body.get("message", "")
        system_context = body.get("system_context", "")
        deep_thought = body.get("deep_thought", False)
        privacy = body.get("privacy", False)
        attachments = body.get("attachments", [])
        
        chat_provider = os.getenv("FoveAI_CHAT_PROVIDER", "ollama").lower()
        cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower()
        
        # Super Coder Refusal: If frontend asks for Direct Cloud but we are in Local mode
        # we bypass the snarky refusal and directly execute the local LLM fallback so they get actual responses!
        if cog_mode == "local" and request.url.path.endswith("/api/cloud/chat"):
            # Build OpenAI-compatible messages array for the fallback
            messages = []
            if system_context:
                messages.append({"role": "system", "content": system_context})
            messages.append({"role": "user", "content": message})
            logger.info("[Cloud Chat] Rerouting local mode Direct Cloud request to Local LLM fallback.")
            return await _local_lmstudio_fallback(messages)
            
        if cog_mode == "local" and chat_provider not in ("unsloth", "lmstudio", "windows_npu", "local"):
            chat_provider = "unsloth"
            try:
                sys.path.insert(0, os.path.join(FoveAI_ROOT, "Mind", "Cognition"))
                # pyrefly: ignore [missing-import]
                import cloud_repertoire
                if "unsloth" not in [s["id"] for s in cloud_repertoire.configured_slots_public()]:
                    chat_provider = "lmstudio"
            except Exception:
                chat_provider = "lmstudio"
        
        # Build OpenAI-compatible messages array
        messages = []
        if system_context:
            messages.append({"role": "system", "content": system_context})
        
        user_content = message
        first_image_b64 = None
        if attachments:
            for att in attachments:
                if att.get("type") == "image" and att.get("base64"):
                    save_snapshot_attachment(att.get("name", ""), att["base64"])
                    if not first_image_b64:
                        # Extract first valid image base64 for fallback queries
                        first_image_b64 = att["base64"]
        
        if first_image_b64:
            # Format as standard OpenAI/multimodal compatible format (Gemini, Ollama, OpenAI)
            clean_b64 = first_image_b64.split(",")[-1] if "," in first_image_b64 else first_image_b64
            content_list = [
                {"type": "text", "text": user_content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{clean_b64}"
                    }
                }
            ]
            messages.append({"role": "user", "content": content_list})
        else:
            messages.append({"role": "user", "content": user_content})
        
        # === CLOUD-FIRST: When provider is ollama_cloud, go DIRECTLY to the API ===
        # This bypasses Soul entirely — Soul is optional, not required for cloud inference
        if chat_provider in ("ollama_cloud", "cloud"):
            cloud_url = os.getenv("FoveAI_CLOUD_BASE_URL", "").rstrip("/")
            cloud_model = os.getenv("FoveAI_CLOUD_MODEL", "gemini-3-flash-preview")
            cloud_key = os.getenv("OLLAMA_API_KEY", os.getenv("FoveAI_REPERTOIRE_OLLAMA_API_KEY", ""))
            
            if not cloud_url:
                return {"response": "", "error": "FoveAI_CLOUD_BASE_URL not set in .env", "source": "direct_cloud"}
            
            # Try Ollama Cloud directly (OpenAI-compatible /chat/completions)
            try:
                headers = _cloud_headers(cloud_key)
                
                # If deep thought mode, use the deep model
                if deep_thought:
                    deep_model = os.getenv("FoveAI_REPERTOIRE_OLLAMA_DEEP_MODEL", cloud_model)
                    payload_model = deep_model
                else:
                    payload_model = cloud_model
                
                payload = {
                    "model": payload_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": float(os.getenv("FoveAI_CLOUD_TEMPERATURE", "0.7") or "0.7"),
                }
                
                # Use /chat/completions endpoint (OpenAI-compatible)
                chat_url = f"{cloud_url}/chat/completions"
                logger.info(f"[Cloud Chat] Direct → {chat_url} model={payload_model}")
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(chat_url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        result = resp.json()
                        reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        reply = await apply_direct_jcoder_edits(reply)
                        return {
                            "response": reply,
                            "inference_backend": f"ollama_cloud/{payload_model}",
                            "source": "direct_cloud",
                            "deep_thought": deep_thought,
                        }
                    else:
                        err_text = resp.text[:500]
                        logger.error(f"[Cloud Chat] Ollama Cloud returned HTTP {resp.status_code}: {err_text}")
                        # Try cloud_repertoire fallback slots
                        return await _cloud_repertoire_fallback(message, system_context, messages, deep_thought, privacy, first_image_b64)
            except httpx.ConnectError as ce:
                logger.warning(f"[Cloud Chat] Ollama Cloud unreachable ({cloud_url}): {ce}")
                return await _cloud_repertoire_fallback(message, system_context, messages, deep_thought, privacy, first_image_b64)
            except Exception as e:
                logger.error(f"[Cloud Chat] Direct cloud error: {e}")
                return await _cloud_repertoire_fallback(message, system_context, messages, deep_thought, privacy, first_image_b64)
        
        # === NON-CLOUD PROVIDER: Route through Soul ===
        payload = {
            "model": "cloud",
            "cloud_routing": chat_provider,
            "messages": messages,
            "deep_thought": deep_thought,
            "privacy": privacy,
        }
        
        if attachments:
            for att in attachments:
                if att.get("type") == "image" and att.get("base64"):
                    payload["image_base64"] = att["base64"]
                    break
        
        url = f"{SOUL_URL}/api/chat"
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            
        reply = result.get("message", {}).get("content", result.get("response", ""))
        reply = await apply_direct_jcoder_edits(reply)
        return {
            "response": reply,
            "inference_backend": result.get("inference_backend", "soul"),
            "source": "direct_cloud",
            "deep_thought": deep_thought,
        }
        
    except httpx.ConnectError:
        cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower()
        if cog_mode == "local":
            logger.warning(f"[Cloud Chat] Soul unreachable and COGNITIVE_MODE=local — trying local LM Studio directly")
            return await _local_lmstudio_fallback(messages)
        logger.warning(f"[Cloud Chat] Soul unreachable — trying Direct Cloud fallback")
        return await _cloud_repertoire_fallback(message, system_context, messages, deep_thought, privacy)
    except Exception as e:
        logger.error(f"[Cloud Chat] Proxy failed: {e}")
        return {"response": "", "error": str(e), "source": "direct_cloud"}


async def _cloud_repertoire_fallback(message: str, system_context: str, messages: list, deep_thought: bool, privacy: bool, image_base64: Optional[str] = None) -> dict:
    """Fallback chain when Soul/Ollama Cloud fails.
    Order: Gemini → OpenRouter → local llama.cpp (Unsloth).
    ollama_cloud is intentionally skipped — it is Soul's primary engine and already failed.
    """
    cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "").strip().lower()
    chat_provider = os.getenv("FoveAI_CHAT_PROVIDER", "").strip().lower()
    if cog_mode == "local" or chat_provider in ("local", "unsloth", "lmstudio", "windows_npu"):
        logger.warning(f"[Fallback] Cognitive mode locked to local ({chat_provider or cog_mode}) — going straight to local model")
        return await _local_lmstudio_fallback(messages)

    try:
        sys.path.insert(0, os.path.join(FoveAI_ROOT, "Mind", "Cognition"))
        # pyrefly: ignore [missing-import]
        from cloud_repertoire import eligible_cloud_slot_ids, generate_via_slot

        eligible = eligible_cloud_slot_ids()

        # Build the ordered fallback list: Gemini first, then OpenRouter.
        # ollama_cloud is ALWAYS excluded here — it is Soul's primary engine and the
        # reason we are in this function (quota depleted or unreachable).
        FALLBACK_ORDER = ["gemini", "openrouter"]
        ordered_slots = [s for s in FALLBACK_ORDER if s in eligible]

        if not ordered_slots:
            logger.error("[Fallback] No cloud fallback slots configured (need FoveAI_REPERTOIRE_GEMINI_API_KEY or FoveAI_CLOUD_OPENROUTER_API in .env)")
            return await _local_lmstudio_fallback(messages)

        errors = []
        for slot in ordered_slots:
            logger.warning(f"[Fallback] Trying cloud slot: {slot}")
            try:
                reply = await generate_via_slot(
                    slot,
                    system_context or "You are a helpful assistant.",
                    message,
                    image_base64=image_base64,
                )
                if (reply or "").strip():
                    reply = await apply_direct_jcoder_edits(reply)
                    logger.info(f"[Fallback] Recovered via {slot}")
                    return {
                        "response": reply,
                        "inference_backend": f"fallback/{slot}",
                        "source": "cloud_fallback",
                    }
                else:
                    # Empty reply usually means quota depleted on this slot too
                    logger.warning(f"[Fallback] {slot} returned empty reply (quota depleted?)")
                    errors.append(f"{slot}: empty response (quota?)")
            except Exception as e:
                logger.warning(f"[Fallback] {slot} failed: {e}")
                errors.append(f"{slot}: {e}")

        logger.error(f"[Fallback] All cloud slots exhausted ({', '.join(errors)}) — falling to local llama.cpp")
        return await _local_lmstudio_fallback(messages)

    except ImportError:
        logger.warning("[Fallback] cloud_repertoire module not importable — going straight to local")
        return await _local_lmstudio_fallback(messages)
    except Exception as fallback_err:
        logger.error(f"[Fallback] Unexpected error: {fallback_err} — falling to local llama.cpp")
        return await _local_lmstudio_fallback(messages)


async def _forward_to_soul_compagent(body: dict) -> dict:
    # Translate frontend format to Soul's compagent format
    import json
    ability_map = body.get("context_ability_map")
    if isinstance(ability_map, dict):
        ability_map_str = json.dumps(ability_map)
    elif ability_map is not None:
        ability_map_str = str(ability_map)
    else:
        ability_map_str = None

    payload = {
        "input": body.get("message", ""),
        "system_instruction": body.get("system_context", ""),
        "channel": body.get("source", "vessel_fallback"),
        "primary_context_mode": "deep_thought" if body.get("deep_thought", False) else None,
        "privacy": body.get("privacy", False),
        "context_reservoirs": body.get("context_reservoirs", {}),
        "context_ability_map": ability_map_str,
    }
    
    attachments = body.get("attachments", [])
    if attachments:
        for att in attachments:
            if att.get("type") == "image" and att.get("base64"):
                payload["image_base64"] = att["base64"]
                save_snapshot_attachment(att.get("name", ""), att["base64"])
                break
    
    url = f"{SOUL_URL}/compagent"
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(url, json=payload)
        result = resp.json()
        
    # Translate Soul's response back to frontend format
    reply = result.get("response", "")
    thought = result.get("thought", "")
    # GGUF thinking models (Qwen3, etc.) may put all content in 'thought'
    # while 'response' stays empty — fall back to thought content if response is empty
    if not reply.strip() and thought.strip():
        reply = thought

    # If Soul is reachable but returned a blank reply (quota exhausted, model not loaded, etc.)
    # raise so proxy_cloud_chat's except handler cascades to _cloud_repertoire_fallback
    # and then _local_lmstudio_fallback, instead of delivering an empty string to the user.
    if not reply.strip():
        backend = result.get("inference_backend", "soul")
        error_detail = result.get("error", "")
        logger.warning(
            f"[Soul Proxy] Soul responded but reply is empty "
            f"(backend={backend}, error={error_detail!r}). "
            "Raising to trigger fallback chain."
        )
        raise ValueError(f"Soul returned empty response (backend={backend})")

    reply = await apply_direct_jcoder_edits(reply)
    return {
        "response": reply,
        "thought": thought,
        "inference_backend": result.get("inference_backend", result.get("mode", "soul")),
        "source": "soul_proxy",
        "active_persona_id": result.get("active_persona_id", "jen"),
    }

@app.post("/api/proxy")
async def generic_llm_proxy(request: Request, _auth: None = Depends(require_webui_login)):
    """Generic HTTP Proxy for LLMManager (replaces htproxy).
    Accepts JSON: { url, method, headers, body }"""
    from fastapi.responses import StreamingResponse
    try:
        data = await request.json()
        target_url = data.get("url")
        target_method = data.get("method", "POST")
        target_headers = data.get("headers", {})
        target_body = data.get("body", {})

        # Remove problematic headers that could interfere with proxying
        target_headers.pop("host", None)
        target_headers.pop("content-length", None)
        
        # httpx client setup
        client = httpx.AsyncClient(timeout=180.0)
        req = client.build_request(
            method=target_method,
            url=target_url,
            headers=target_headers,
            json=target_body if isinstance(target_body, dict) else None,
            content=target_body if isinstance(target_body, str) else None
        )

        # Stream response back directly to support SSE
        async def stream_generator():
            async with client.stream(req.method, req.url, headers=req.headers, content=req.content) as resp:
                if resp.status_code != 200:
                    # If error, yield the error message
                    err_text = await resp.aread()
                    yield err_text
                    return
                async for chunk in resp.aiter_bytes():
                    yield chunk

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"[Generic Proxy] Error proxying to {data.get('url', 'unknown')}: {e}")
        return {"error": str(e)}

@app.post("/api/proxy/soul/compagent")
async def proxy_soul_compagent(request: Request):
    """Proxy compagent requests to the Soul service.
    Soul's /compagent endpoint accepts {message, system_context, source, deep_thought, privacy}.
    Used as fallback when Direct Cloud fails."""
    # Read body once — request stream can only be consumed once in FastAPI
    body = await request.json()
    message = body.get("message", body.get("input", ""))
    system_context = body.get("system_context", body.get("system_instruction", ""))
    deep_thought = body.get("deep_thought", False)
    privacy = body.get("privacy", False)

    def _build_messages() -> list:
        msgs = []
        if system_context:
            msgs.append({"role": "system", "content": system_context})
        if message:
            msgs.append({"role": "user", "content": message})
        return msgs

    try:
        return await _forward_to_soul_compagent(body)
    except httpx.ConnectError:
        logger.warning(f"[Soul Proxy] Soul unreachable at {SOUL_URL} — cascading to cloud/local fallback")
        return await _cloud_repertoire_fallback(message, system_context, _build_messages(), deep_thought, privacy)
    except ValueError as ve:
        # Soul returned empty response (quota exhausted, model not loaded, etc.)
        logger.warning(f"[Soul Proxy] {ve} — cascading to cloud/local fallback")
        return await _cloud_repertoire_fallback(message, system_context, _build_messages(), deep_thought, privacy)
    except Exception as e:
        logger.error(f"[Soul Proxy] Proxy failed: {e}")
        return {"response": "", "error": str(e), "source": "soul_proxy"}

@app.api_route("/api/soul/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def generic_soul_proxy(path: str, request: Request, _auth: None = Depends(require_webui_login)):
    """Authoritative OMEGA_085 Unified Proxy for all Soul requests."""
    url = f"{SOUL_URL}/{path}"
    method = request.method
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, params=request.query_params)
            else:
                body = await request.json()
                resp = await client.request(method, url, json=body)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

@app.get("/api/soul/vitals")
async def proxy_soul_vitals(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/vitals"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)

# ── Autonomous Agent Proxy Routes ────────────────────────────────────────
# Forward /api/agent/* from XR_Vessel to XRLF runtime (port 8402)
# so the Agency Tab START/STOP buttons and status polling work from the browser.

@app.get("/api/agent/status")
async def proxy_agent_status(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/status"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.post("/api/agent/start")
async def proxy_agent_start(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/start"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.post("/api/agent/stop")
async def proxy_agent_stop(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/stop"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/messages")
async def proxy_agent_messages(limit: int = 20, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/messages"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"limit": limit})
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.post("/api/agent/messages/mark")
async def proxy_agent_mark_messages(request: Request, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/messages/mark"
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/plans")
async def proxy_agent_plans(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/plans"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/thoughts")
async def proxy_agent_thoughts(limit: int = 20, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/thoughts"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"limit": limit})
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/actions")
async def proxy_agent_actions(limit: int = 20, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/actions"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"limit": limit})
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/context")
async def proxy_agent_context(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/context"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.post("/api/agent/message")
async def proxy_agent_enqueue_message(request: Request, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/message"
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.post("/api/agent/plan")
async def proxy_agent_create_plan(request: Request, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/plan"
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/plan/{plan_id}")
async def proxy_agent_get_plan(plan_id: str, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/plan/{plan_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/memory/{key}")
async def proxy_agent_get_memory(key: str, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/memory/{key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.post("/api/agent/memory")
async def proxy_agent_set_memory(request: Request, _auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/memory"
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.get("/api/agent/queue/stats")
async def proxy_agent_queue_stats(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/agent/queue/stats"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Soul", url, e)


@app.post("/api/soul/provider")
async def set_soul_provider(request: Request, _auth: None = Depends(require_webui_login)):
    try:
        data = await request.json()
        provider = data.get("provider", "").strip().lower()
        if not provider:
            return {"success": False, "error": "empty provider"}
        
        # Update local environment variable
        os.environ["FoveAI_CHAT_PROVIDER"] = provider
        logger.info(f"Vessel: setting FoveAI_CHAT_PROVIDER env to {provider}")
        
        # Propagate to XRLF runtime (Port 8402) via /soul_runtime_config
        url = f"{SOUL_URL}/soul_runtime_config"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={"chat_provider": provider})
                logger.info(f"Vessel: successfully propagated provider to Soul service")
        except Exception as e:
            logger.warning(f"Vessel: failed to propagate provider to Soul service: {e}")
            
        # Update the physical .env file so the selection persists across reboots
        try:
            env_path = os.path.join(FoveAI_ROOT, ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = []
                found = False
                for line in lines:
                    if line.strip().startswith("FoveAI_CHAT_PROVIDER="):
                        new_lines.append(f"FoveAI_CHAT_PROVIDER={provider}\n")
                        found = True
                    else:
                        new_lines.append(line)
                if not found:
                    new_lines.append(f"\nFoveAI_CHAT_PROVIDER={provider}\n")
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                logger.info("Vessel: successfully saved selection to .env file")
        except Exception as e:
            logger.error(f"Vessel: failed to save selection to .env: {e}")
            
        return {"success": True, "provider": provider}
    except Exception as e:
        logger.error(f"Error setting chat provider: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/soul/lmstudio/hotswap")
async def hotswap_lmstudio_model(request: Request, _auth: None = Depends(require_webui_login)):
    """Dynamically hot-swaps the loaded GGUF model in LM Studio based on Privacy toggle."""
    try:
        data = await request.json()
        privacy = data.get("privacy", False)
        
        # Determine model to load or unload based on privacy mode and cognitive mode
        action = "load"
        cog_mode = os.getenv("FoveAI_COGNITIVE_MODE", "hybrid").strip().lower()
        
        if privacy:
            # Load the uncensored, uninhibited "heretic" model
            model = os.getenv("FoveAI_REPERTOIRE_LMSTUDIO_PRIVACY_MODEL", "qwen3.5-4b-abliterated").strip()
            gpu_offload = os.getenv("FoveAI_LMSTUDIO_GPU_OFFLOAD", "0.5")
            context_length = os.getenv("FoveAI_LMSTUDIO_CONTEXT_LENGTH", "8192")
            cmd_str = f'lms load "{model}" --gpu {gpu_offload} --context-length {context_length} --identifier local-model -y'
            logger.info(f"Vessel LMStudio Hotswap: Privacy=ON -> loading model '{model}'")
        else:
            if cog_mode == "cloud":
                # Unload completely to free VRAM for WebXR/audio!
                model = None
                cmd_str = 'lms unload --all'
                action = "unload"
                logger.info("Vessel LMStudio Hotswap: Privacy=OFF & Cognitive Mode=cloud -> unloading all local models from RAM")
            else:
                # Load the advanced, logical reasoning model
                model = os.getenv("FoveAI_REPERTOIRE_LMSTUDIO_MODEL", "qwen3-4b-qwen3.6-plus-reasoning-distilled").strip()
                gpu_offload = os.getenv("FoveAI_LMSTUDIO_GPU_OFFLOAD", "0.5")
                context_length = os.getenv("FoveAI_LMSTUDIO_CONTEXT_LENGTH", "8192")
                cmd_str = f'lms load "{model}" --gpu {gpu_offload} --context-length {context_length} --identifier local-model -y'
                logger.info(f"Vessel LMStudio Hotswap: Privacy=OFF & Cognitive Mode={cog_mode} -> loading model '{model}'")
        
        import asyncio
        if action == "load" and model:
            try:
                check_process = await asyncio.create_subprocess_shell(
                    "lms ps",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_data, _ = await check_process.communicate()
                loaded_models = stdout_data.decode('utf-8', errors='ignore')
                if model in loaded_models:
                    logger.info(f"Vessel LMStudio Hotswap: Model '{model}' is already loaded. Skipping load.")
                    return {"success": True, "status": "already_loaded", "model": model}
            except Exception as e:
                logger.error(f"Failed to check currently loaded models via 'lms ps': {e}")
        
        process = await asyncio.create_subprocess_shell(
            cmd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Give a small 100ms grace period to check for early process errors
        try:
            await asyncio.wait_for(process.wait(), timeout=0.1)
            if process.returncode != 0:
                stdout, stderr = await process.communicate()
                err_msg = stderr.decode('utf-8', errors='ignore')
                logger.error(f"LMStudio hotswap failed immediately: {err_msg}")
                return {"success": False, "error": f"Load failed: {err_msg}"}
        except asyncio.TimeoutError:
            # Still running in background, which is expected for model loading
            pass
            
        return {"success": True, "model": model, "privacy": privacy}
    except Exception as e:
        logger.error(f"Error hot-swapping LM Studio model: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/nav/pull")
async def proxy_nav_pull(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/api/nav/pull"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception:
        return {"command": None}

@app.post("/api/nav/push")
async def proxy_nav_push(request: Request, _auth: None = Depends(require_webui_login)):
    data = await request.json()
    url = f"{SOUL_URL}/api/nav/push"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception:
        return {"ok": False}

@app.get("/api/branding")
async def proxy_branding(_auth: None = Depends(require_webui_login)):
    url = f"{SOUL_URL}/branding"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception:
        # Fallback to local
        if os.path.exists(LEGACY_BRANDING_PATH):
            with open(LEGACY_BRANDING_PATH, "r") as f:
                return json.load(f)
        return {"name": "Lumax", "version": "Lite"}

# --- LM Studio Proxy ---

@app.get("/api/proxy/lmstudio/models")
async def proxy_lmstudio_models(_auth: None = Depends(require_webui_login)):
    # Use management API for richer metadata (loaded_instances, etc)
    _token = _get_lmstudio_api_token()
    url = f"{LMSTUDIO_URL}/api/v1/models"
    headers = {"Authorization": f"Bearer {_token}"} if _token else {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            return resp.json()
    except Exception as e:
        # Fallback to standard OpenAI-style if management API fails
        url_v1 = f"{LMSTUDIO_URL}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url_v1, headers={"Authorization": f"Bearer {_token}"} if _token else {})
                return resp.json()
        except Exception:
            raise _upstream_unreachable("LMStudio", url, e)

@app.get("/api/proxy/lmstudio/available")
async def list_available_models(_auth: None = Depends(require_webui_login)):
    """List .gguf files in the models directory."""
    if not os.path.exists(MODELS_DIR):
        return {"models": []}
    models = []
    for root, _, files in os.walk(MODELS_DIR):
        for f in files:
            if f.endswith(".gguf"):
                rel_path = os.path.relpath(os.path.join(root, f), MODELS_DIR)
                models.append({
                    "id": rel_path.replace("\\", "/"),
                    "filename": f,
                    "path": os.path.join(root, f)
                })
    return {"models": models}

@app.post("/api/proxy/lmstudio/load")
async def proxy_lmstudio_load(request: Request, _auth: None = Depends(require_webui_login)):
    data = await request.json()
    _token = _get_lmstudio_api_token()
    # LM Studio v1 API: POST /api/v1/models/load
    url = f"{LMSTUDIO_URL}/api/v1/models/load"
    headers = {"Authorization": f"Bearer {_token}"} if _token else {}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=data, headers=headers)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("LMStudio", url, e)

@app.post("/api/proxy/lmstudio/unload")
async def proxy_lmstudio_unload(request: Request, _auth: None = Depends(require_webui_login)):
    data = await request.json()
    _token = _get_lmstudio_api_token()
    # LM Studio v1 API: POST /api/v1/models/unload
    url = f"{LMSTUDIO_URL}/api/v1/models/unload"
    headers = {"Authorization": f"Bearer {_token}"} if _token else {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=data, headers=headers)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("LMStudio", url, e)

@app.post("/api/proxy/lmstudio/chat")
async def proxy_lmstudio_chat(request: Request, _auth: None = Depends(require_webui_login)):
    data = await request.json()
    _token = _get_lmstudio_api_token()
    url = f"{LMSTUDIO_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {_token}"} if _token else {}
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(url, json=data, headers=headers)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("LMStudio", url, e)

# --- HEARTBEAT / PRESENCE ---
_HEARTBEAT_PATH = os.getenv("FoveAI_HEARTBEAT_PATH", "/tmp/foveai_avatar_heartbeat")
# Windows path for console auto-wake detection (native Python mode)
_FoveAI_LOG_DIR = os.getenv("FoveAI_LOG_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".logs"))
_PRESENCE_HEARTBEAT_FILE = os.path.join(_FoveAI_LOG_DIR, "foveai_presence_heartbeat.txt")

@app.post("/api/presence/heartbeat")
async def presence_heartbeat(request: Request) -> dict[str, Any]:
    """Updates the presence timestamp for lifecycle management."""
    # Note: Soul forwards this with X-FoveAI-INTERNAL-KEY
    result = {"ok": True, "ts": int(time.time())}
    try:
        with open(_HEARTBEAT_PATH, "w") as f:
            f.write(str(int(time.time())))
    except Exception as e:
        result["windows_error"] = str(e)
    
    # Also write Windows heartbeat file for console auto-wake detection
    try:
        os.makedirs(os.path.dirname(_PRESENCE_HEARTBEAT_FILE), exist_ok=True)
        with open(_PRESENCE_HEARTBEAT_FILE, "w") as f:
            f.write(str(int(time.time())))
    except Exception as e:
        result["windows_error"] = str(e)
    
    return result

# --- Diagnostics ---

def _diagnostic_probe_specs() -> list[tuple[str, str, str, bool]]:
    """(id, label, url, optional_soft_fail)."""
    webui_self = f"http://127.0.0.1:{_WEBUI_PORT}/health"
    tts_url, tts_lbl = _tts_upstream_probe()
    return [
        ("webui", "Web UI (this process)", webui_self, False),
        ("soul", "Soul (compagent)", f"{SOUL_URL}/health", False),
        ("ears", "Ears (STT)", f"{EARS_URL}/health", False),
        ("mouth", "Mouth (TTS router)", f"{MOUTH_URL}/health", False),
        ("creative", "Creativity (dream)", f"{CREATIVE_URL}/health", False),
        ("soundboard", "Soundboard (Stable Audio)", f"{SOUNDBOARD_URL}/health", True),
        ("kokoro_tts", tts_lbl, tts_url, True),
        ("ollama", "Ollama", f"{OLLAMA_HOST}/api/tags", True),
    ]

async def _diagnostic_probe_one(
    client: httpx.AsyncClient,
    check_id: str,
    label: str,
    url: str,
    optional: bool,
) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        resp = await client.get(url)
        ms = int((time.monotonic() - t0) * 1000)
        ok = resp.status_code == 200
        detail = f"HTTP {resp.status_code} ({ms}ms)"
        if not ok:
            tail = (resp.text or "")[:280].replace("\n", " ")
            if tail:
                detail += f" — {tail}"
        return {
            "id": check_id,
            "label": label,
            "ok": ok,
            "detail": detail,
            "optional": optional,
            "url": url,
        }
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        return {
            "id": check_id,
            "label": label,
            "ok": False,
            "detail": f"{type(e).__name__}: {e} ({ms}ms)",
            "optional": optional,
            "url": url,
        }

class DiagnosticRunBody(BaseModel):
    ids: Optional[list[str]] = None

class DiagnosticsTtsBody(BaseModel):
    text: str = Field(default="Lumax, voice check.", max_length=4096)
    voice: Optional[str] = Field(default=None, max_length=512)
    engine: str = Field(default="MOUTH", max_length=64)
    output_format: Optional[str] = Field(default="wav", max_length=16)

async def _run_diagnostics(ids: Optional[list[str]]) -> dict[str, Any]:
    specs = _diagnostic_probe_specs()
    want = set(ids) if ids else None
    to_run = [s for s in specs if want is None or s[0] in want]
    async with httpx.AsyncClient(timeout=12.0) as client:
        coros = [
            _diagnostic_probe_one(client, cid, label, url, opt)
            for cid, label, url, opt in to_run
        ]
        results = await asyncio.gather(*coros)
    
    all_ok = all(r["ok"] or r["optional"] for r in results)
    return {"ok": all_ok, "steps": results}

@app.post("/api/diagnostics/run")
async def run_diagnostics(body: DiagnosticRunBody, _auth: None = Depends(require_webui_login)):
    return await _run_diagnostics(body.ids)

@app.get("/api/config/ui")
async def get_ui_config(_auth: None = Depends(require_webui_login)):
    if os.path.exists(UI_CONFIG_PATH):
        with open(UI_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.get("/api/announcements")
async def get_announcements():
    if os.path.exists(ANNOUNCEMENTS_PATH):
        with open(ANNOUNCEMENTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# --- Consent Endpoints (integrated into WebUI) ---

@app.get("/api/consent/status")
async def consent_status():
    """Return which data sources are connected."""
    google_ok = os.path.exists(os.path.join(os.path.dirname(BASE_DIR), "..", ".cache", "google_tokens.json"))
    ms_ok = os.path.exists(os.path.join(os.path.dirname(BASE_DIR), "..", ".cache", "ms_tokens.json"))
    return {
        "google_connected": google_ok,
        "microsoft_connected": ms_ok,
        "consent_bridge_available": _CONSENT_AVAILABLE,
    }

@app.get("/api/consent/google/auth")
async def consent_google_auth():
    """Return the Google OAuth consent URL for the user to open."""
    if not _CONSENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="ConsentBridge not available")
    try:
        bridge = GoogleConsentBridge()
        url = bridge.get_auth_url()
        return {"auth_url": url, "message": "Open this URL to consent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/consent/google/callback")
async def consent_google_callback(code: Optional[str] = None):
    """Catch Google OAuth redirect and sync to memory."""
    if not _CONSENT_AVAILABLE:
        return HTMLResponse("<h2>ConsentBridge unavailable</h2>", status_code=503)
    if not code:
        return HTMLResponse("<h2>No authorization code received</h2>", status_code=400)
    try:
        bridge = GoogleConsentBridge()
        bridge.exchange_code(code)
        try:
            bridge.sync_to_memory()
        except Exception as e:
            logger.warning(f"Post-consent sync failed: {e}")
        return HTMLResponse("""
        <!DOCTYPE html><html><head><title>FoveAI Connected</title>
        <style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0a0a0a;color:#fff}
        .card{background:#1a1a1a;padding:40px;border-radius:12px;text-align:center;max-width:400px}
        .dot{width:60px;height:60px;border-radius:50%;margin:0 auto 20px;background:#2ecc71}
        h2{margin:0 0 10px}p{color:#aaa;margin:0}</style></head>
        <body><div class="card"><div class="dot"></div><h2>Google Connected</h2>
        <p>FoveAI can now read your contacts, calendar, and email context to enrich her memory.</p>
        <p style="color:#888;margin-top:20px;font-size:12px">You can close this tab.</p></div></body></html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h2>Error: {e}</h2>", status_code=500)

@app.get("/api/consent/microsoft/auth")
async def consent_microsoft_auth():
    """Return the Microsoft OAuth consent URL."""
    if not _CONSENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="ConsentBridge not available")
    try:
        bridge = MicrosoftConsentBridge()
        url = bridge.get_auth_url()
        return {"auth_url": url, "message": "Open this URL to consent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/consent/microsoft/callback")
async def consent_microsoft_callback(code: Optional[str] = None):
    """Catch Microsoft OAuth redirect and sync to memory."""
    if not _CONSENT_AVAILABLE:
        return HTMLResponse("<h2>ConsentBridge unavailable</h2>", status_code=503)
    if not code:
        return HTMLResponse("<h2>No authorization code received</h2>", status_code=400)
    try:
        bridge = MicrosoftConsentBridge()
        bridge.exchange_code(code)
        try:
            bridge.sync_to_memory()
        except Exception as e:
            logger.warning(f"Post-consent sync failed: {e}")
        return HTMLResponse("""
        <!DOCTYPE html><html><head><title>FoveAI Connected</title>
        <style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0a0a0a;color:#fff}
        .card{background:#1a1a1a;padding:40px;border-radius:12px;text-align:center;max-width:400px}
        .dot{width:60px;height:60px;border-radius:50%;margin:0 auto 20px;background:#3498db}
        h2{margin:0 0 10px}p{color:#aaa;margin:0}</style></head>
        <body><div class="card"><div class="dot"></div><h2>Microsoft Connected</h2>
        <p>FoveAI can now read your contacts, calendar, and email context to enrich her memory.</p>
        <p style="color:#888;margin-top:20px;font-size:12px">You can close this tab.</p></div></body></html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h2>Error: {e}</h2>", status_code=500)

@app.post("/api/consent/sync")
async def consent_sync_all():
    """Manually trigger sync for all connected sources."""
    results = {}
    if _CONSENT_AVAILABLE:
        try:
            g = GoogleConsentBridge()
            if g.tokens:
                g.sync_to_memory()
                results["google"] = "ok"
        except Exception as e:
            results["google"] = str(e)
        try:
            m = MicrosoftConsentBridge()
            if m.tokens:
                m.sync_to_memory()
                results["microsoft"] = "ok"
        except Exception as e:
            results["microsoft"] = str(e)
    return results

@app.get("/api/consent/google/disconnect")
async def consent_google_disconnect():
    p = os.path.join(os.path.dirname(BASE_DIR), "..", ".cache", "google_tokens.json")
    if os.path.exists(p):
        os.remove(p)
    return {"message": "Google disconnected, tokens deleted"}

@app.get("/api/consent/microsoft/disconnect")
async def consent_microsoft_disconnect():
    p = os.path.join(os.path.dirname(BASE_DIR), "..", ".cache", "ms_tokens.json")
    if os.path.exists(p):
        os.remove(p)
    return {"message": "Microsoft disconnected, tokens deleted"}

# --- Feature Inventory & Architecture Map ---

@app.get("/api/fmap")
async def get_feature_map(_auth: None = Depends(require_webui_login)):
    """Serve FEATURE_INVENTORY.md as parsed JSON for the Web UI Feature Map tab."""
    try:
        import feature_inventory_parser as fip
        content = _read_markdown_safe(_FEATURE_INVENTORY_PATH)
        if not content:
            return JSONResponse(
                {"ok": False, "error": "FEATURE_INVENTORY.md not found or empty"},
                status_code=404,
            )
        parsed = fip.parse_feature_inventory_markdown(content)
        parsed["ok"] = True
        return parsed
    except Exception as e:
        logger.error(f"Feature map parse error: {e}")
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500,
        )

@app.get("/api/architecture")
async def get_architecture(_auth: None = Depends(require_webui_login)):
    """Serve ARCHITECTURE.md raw markdown + extracted Mermaid diagrams for the Web UI."""
    content = _read_markdown_safe(_ARCHITECTURE_PATH)
    if not content:
        return JSONResponse(
            {"ok": False, "error": "ARCHITECTURE.md not found or empty"},
            status_code=404,
        )

    # Extract Mermaid diagram blocks
    diagrams = []
    in_diagram = False
    diagram_lines = []
    diagram_title = "Untitled"
    for line in content.splitlines():
        if line.strip().startswith("```mermaid"):
            in_diagram = True
            diagram_lines = []
            continue
        if in_diagram and line.strip().startswith("```"):
            diagrams.append({
                "title": diagram_title,
                "source": "\n".join(diagram_lines).strip(),
            })
            in_diagram = False
            diagram_title = "Untitled"
            continue
        if in_diagram:
            if line.startswith("## "):
                diagram_title = line[3:].strip()
            diagram_lines.append(line)
        elif line.startswith("## "):
            diagram_title = line[3:].strip()

    return {
        "ok": True,
        "markdown": content,
        "diagrams": diagrams,
        "sections": [
            {"title": "High-Level backend/frontend/Service Topology", "anchor": "1-high-level-mindbodyservice-topology"},
            {"title": "Service Dependency Graph", "anchor": "2-service-dependency-graph"},
            {"title": "Data Flow: Conversation Turn", "anchor": "3-data-flow-conversation-turn"},
            {"title": "Service Profile Matrix", "anchor": "4-service-profile-matrix"},
            {"title": "State Machine: Life Cycle", "anchor": "5-state-machine-life-cycle"},
            {"title": "Console Dashboard Layout", "anchor": "6-console-dashboard-layout"},
            {"title": "File Organization Map", "anchor": "7-file-organization-map"},
        ],
    }

@app.get("/api/architecture/raw")
async def get_architecture_raw():
    """Serve raw ARCHITECTURE.md for direct download or external viewers."""
    content = _read_markdown_safe(_ARCHITECTURE_PATH)
    if not content:
        raise HTTPException(status_code=404, detail="ARCHITECTURE.md not found")
    return Response(content=content, media_type="text/markdown")

# --- Creativity Service Proxy Endpoints ---
@app.get("/api/creativity/health")
async def get_creativity_health(_auth: None = Depends(require_webui_login)):
    """Proxy to creative service's /api/health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{CREATIVE_URL}/api/health")
            return resp.json()
    except Exception as e:
        logger.warning(f"Creativity health proxy failed: {e}")
        raise HTTPException(status_code=503, detail=f"Creative service unavailable: {e}")

@app.get("/api/creativity/status")
async def get_creativity_status(_auth: None = Depends(require_webui_login)):
    """Proxy to creative service's /api/health endpoint with extended info."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{CREATIVE_URL}/api/health")
            health = resp.json()
            return {"ok": True, "health": health}
    except Exception as e:
        logger.warning(f"Creativity status proxy failed: {e}")
        return {"ok": False, "detail": str(e)}

# --- Dream Catalog Proxy (for Dreamscape UI) ---
@app.get("/api/dream/catalog")
async def get_dream_catalog(_auth: None = Depends(require_webui_login)):
    """Proxy to creative service's /api/dream/catalog endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{CREATIVE_URL}/api/dream/catalog")
            return resp.json()
    except Exception as e:
        logger.warning(f"Dream catalog proxy failed: {e}")
        raise HTTPException(status_code=503, detail=f"Creative service unavailable: {e}")

# --- Dreamscape Settings (CREATIVE model type selector + preview) ---
@app.get("/api/dreamscape/settings")
async def get_dreamscape_settings(_auth: None = Depends(require_webui_login)):
    """Return available creative model types and their status."""
    creative_health = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{CREATIVE_URL}/api/health")
            creative_health = resp.json()
    except Exception:
        creative_health = {"status": "unreachable"}
    
    return {
        "model_types": [
            {"id": "turbo", "name": "SD1.5 Turbo (Diffusers)", "steps": 4, "default": True},
            {"id": "sdxl_turbo_onnx", "name": "SDXL Turbo ONNX (Optimum)", "steps": 4, "ready": creative_health.get("sdxl_turbo_onnx_ready", False)},
            {"id": "gguf", "name": "SDXL Turbo GGUF (Q8_0)", "steps": 4, "ready": creative_health.get("gguf_ready", False)},
            {"id": "flux_gguf", "name": "Flux 2 INT8 GGUF (FALAI Turbo)", "steps": 4, "ready": creative_health.get("flux_gguf_ready", False)},
        ],
        "defaults": {
            "width": int(os.getenv("FoveAI_CREATIVITY_DEFAULT_WIDTH", "512")),
            "height": int(os.getenv("FoveAI_CREATIVITY_DEFAULT_HEIGHT", "512")),
            "steps": int(os.getenv("FoveAI_CREATIVITY_DEFAULT_INFERENCE_STEPS", "4")),
            "guidance_scale": 7.5,
        },
        "creative_health": creative_health,
    }


@app.post("/api/dreamscape/preheat")
async def preheat_dreamscape(_auth: None = Depends(require_webui_login)):
    """
    Pre-heat the creative service when user shows interest in image generation.
    Called when user opens the Dreamscape tab to prepare without loading weights.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{CREATIVE_URL}/api/preheat")
            return resp.json()
    except Exception as e:
        logger.warning(f"Creative pre-heat failed: {e}")
        return {"status": "preheat_failed", "error": str(e)}


@app.post("/api/state/switch")
async def switch_foveai_state(state: str, _auth: None = Depends(require_webui_login)):
    """
    Signal the service manager to switch to a specific state.
    Valid states: AWAKE, CREATIVE, LIVE, CODE, SLEEP
    """
    valid_states = {"AWAKE", "CREATIVE", "LIVE", "CODE", "SLEEP"}
    state = state.upper()
    
    if state not in valid_states:
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of: {valid_states}")
    
    # Write command file for the service to pick up
    cmd_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".logs", "foveai_service_cmd.txt")
    try:
        with open(cmd_path, "w", encoding="utf-8") as f:
            f.write(state)
        logger.info(f"State switch command written: {state}")
        return {"status": "switching", "state": state, "message": f"Switching to {state} state"}
    except Exception as e:
        logger.error(f"Failed to write state switch command: {e}")
        raise HTTPException(status_code=500, detail=f"Could not signal state switch: {e}")


@app.get("/api/state/current")
async def get_current_state(_auth: None = Depends(require_webui_login)):
    """Get the current system state from the service status file."""
    status_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".logs", "foveai_service_status.json")
    try:
        if os.path.exists(status_file):
            with open(status_file, "r", encoding="utf-8") as f:
                status = json.load(f)
            return {
                "state": status.get("state", "UNKNOWN"),
                "enabled": status.get("enabled", False),
                "services": status.get("services", {}),
            }
        return {"state": "UNKNOWN", "enabled": False, "services": {}}
    except Exception as e:
        logger.warning(f"Could not read state: {e}")
        return {"state": "ERROR", "enabled": False, "services": {}, "error": str(e)}

@app.post("/api/dream")
async def post_dream(request: Request, _auth: None = Depends(require_webui_login)):
    """Proxy to creative service /api/dream endpoint."""
    data = await request.json()
    url = f"{CREATIVE_URL}/api/dream"
    try:
        async with httpx.AsyncClient(timeout=_FoveAI_DREAM_PROXY_TIMEOUT) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Creativity", url, e)


@app.post("/api/dreamscape/generate")
async def post_dreamscape_generate(request: Request, _auth: None = Depends(require_webui_login)):
    """Proxy dream generation to creative_service with model_type selector."""
    data = await request.json()
    # Pass through to creative service /api/dream
    url = f"{CREATIVE_URL}/api/dream"
    try:
        async with httpx.AsyncClient(timeout=_FoveAI_DREAM_PROXY_TIMEOUT) as client:
            resp = await client.post(url, json=data)
            return resp.json()
    except Exception as e:
        raise _upstream_unreachable("Creativity", url, e)

# --- Drone Swarm Problem Solvers ---
@app.get("/api/swarm/state")
async def get_swarm_state_endpoint(_auth: None = Depends(require_webui_login)):
    """Live swarm drone positions and status (Pac-Man style visualizer data)."""
    if not SWARM_AVAILABLE:
        return {"active": False, "error": "Swarm orchestrator not available", "drones": {}}
    return get_swarm_state()

class SwarmTaskRequest(BaseModel):
    objective: str
    context: str = ""

@app.post("/api/swarm/launch")
async def post_swarm_launch(req: SwarmTaskRequest, _auth: None = Depends(require_webui_login)):
    """Launch a tiered swarm mission: Director plans → Drones investigate → Director synthesizes."""
    if not SWARM_AVAILABLE or execute_swarm_task is None:
        raise HTTPException(status_code=503, detail="Swarm orchestrator not available")
    try:
        result = await execute_swarm_task(req.objective, req.context)
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Swarm mission failed: {e}")

# --- Discovery Swarm Endpoints (Self-Discovery System) ---
@app.get("/api/discovery/state")
async def get_discovery_state_endpoint(_auth: None = Depends(require_webui_login)):
    """Live discovery swarm drone positions and progress."""
    if not DISCOVERY_AVAILABLE:
        return {"active": False, "error": "Discovery swarm not available", "drones": {}}
    return get_discovery_state()

class DiscoveryLaunchRequest(BaseModel):
    duration_minutes: int = Field(default=30, ge=5, le=120)

@app.post("/api/discovery/launch")
async def post_discovery_launch(req: DiscoveryLaunchRequest, _auth: None = Depends(require_webui_login)):
    """Launch a discovery swarm mission: Mapper + Archivist + Auditor explore the codebase."""
    if not DISCOVERY_AVAILABLE or execute_discovery_mission is None:
        raise HTTPException(status_code=503, detail="Discovery swarm not available")
    try:
        result = await execute_discovery_mission(req.duration_minutes)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("Discovery mission failed")
        raise HTTPException(status_code=500, detail=f"Discovery mission failed: {e}")

@app.get("/api/discovery/reports")
async def get_discovery_reports(limit: int = 20, _auth: None = Depends(require_webui_login)):
    """List persisted discovery reports."""
    if not DISCOVERY_AVAILABLE or list_discovery_reports is None:
        return {"reports": []}
    try:
        reports = list_discovery_reports(limit=limit)
        return {"reports": reports}
    except Exception as e:
        logger.warning(f"Failed to list discovery reports: {e}")
        return {"reports": [], "error": str(e)}

@app.get("/api/discovery/notification")
async def get_discovery_notification(_auth: None = Depends(require_webui_login)):
    """Get the latest discovery report as a banner notification."""
    if not DISCOVERY_AVAILABLE or get_latest_discovery_notification is None:
        return {"notification": None}
    try:
        notification = get_latest_discovery_notification()
        return {"notification": notification}
    except Exception as e:
        logger.warning(f"Failed to get discovery notification: {e}")
        return {"notification": None, "error": str(e)}


# ── Inbox / Crash Report Endpoints ────────────────────────────────────────────

ERROR_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".logs", "error_reports")

class InboxMessage(BaseModel):
    id: str
    type: str  # "crash_report", "system", "discovery", "director"
    title: str
    summary: str
    timestamp: str
    severity: str = "info"  # "info", "warning", "critical"
    read: bool = False
    details: Optional[Dict[str, Any]] = None


def _list_crash_reports(limit: int = 50) -> List[Dict[str, Any]]:
    """List crash reports from .logs/error_reports/ directory."""
    reports = []
    if not os.path.exists(ERROR_REPORTS_DIR):
        return reports
    
    try:
        report_files = sorted(Path(ERROR_REPORTS_DIR).glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
        for report_path in report_files:
            try:
                content = report_path.read_text(encoding="utf-8")
                # Parse header from crash report
                lines = content.splitlines()
                title = "Crash Report"
                service_name = "Unknown"
                crash_time = report_path.stem.replace("_crash_", "").replace("_", ":")
                
                for line in lines[:20]:
                    if line.startswith("Service: "):
                        service_name = line.replace("Service: ", "")
                        title = f"{service_name} Crash"
                    elif line.startswith("Crash Time: "):
                        crash_time = line.replace("Crash Time: ", "")
                
                # Determine severity based on crash count
                severity = "warning"
                for line in lines[:30]:
                    if "CRITICAL" in line or "FATAL" in line:
                        severity = "critical"
                        break
                
                reports.append({
                    "id": report_path.stem,
                    "type": "crash_report",
                    "title": title,
                    "summary": f"{service_name} crashed - see details",
                    "timestamp": crash_time,
                    "severity": severity,
                    "read": False,
                    "details": {
                        "filename": report_path.name,
                        "content": content,
                        "service": service_name,
                    }
                })
            except Exception as e:
                logger.warning(f"Failed to read crash report {report_path}: {e}")
    except Exception as e:
        logger.warning(f"Failed to list crash reports: {e}")
    
    return reports


@app.get("/api/inbox/crash-reports")
async def get_crash_reports(limit: int = 50, _auth: None = Depends(require_webui_login)):
    """List crash reports from error_reports directory."""
    reports = _list_crash_reports(limit)
    return {"reports": reports, "total": len(reports)}


@app.get("/api/inbox/messages")
async def get_inbox_messages(limit: int = 50, _auth: None = Depends(require_webui_login)):
    """Get all inbox messages including crash reports, discovery notifications, and system messages."""
    messages = []
    
    # Add crash reports
    crash_reports = _list_crash_reports(limit // 2)
    messages.extend([InboxMessage(**r).dict() for r in crash_reports])
    
    # Add discovery notifications
    if DISCOVERY_AVAILABLE and get_latest_discovery_notification:
        try:
            discovery = get_latest_discovery_notification()
            if discovery:
                messages.append({
                    "id": f"discovery_{discovery.get('timestamp', 'now')}",
                    "type": "discovery",
                    "title": discovery.get("title", "Discovery Report"),
                    "summary": discovery.get("summary", "New discovery findings available"),
                    "timestamp": discovery.get("timestamp", ""),
                    "severity": "info",
                    "read": False,
                    "details": discovery
                })
        except Exception as e:
            logger.warning(f"Failed to get discovery notification: {e}")
    
    # Sort by timestamp (newest first)
    messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    messages = messages[:limit]
    
    return {"messages": messages, "total": len(messages), "unread": sum(1 for m in messages if not m.get("read", False))}


@app.get("/api/inbox/unread-count")
async def get_inbox_unread_count(_auth: None = Depends(require_webui_login)):
    """Get count of unread inbox messages."""
    crash_reports = _list_crash_reports(100)
    unread_crashes = sum(1 for r in crash_reports if not r.get("read", False))
    
    unread_discovery = 0
    if DISCOVERY_AVAILABLE and get_latest_discovery_notification:
        try:
            discovery = get_latest_discovery_notification()
            if discovery:
                unread_discovery = 1
        except Exception:
            pass
    
    return {"unread": unread_crashes + unread_discovery, "crash_reports": unread_crashes, "discovery": unread_discovery}


def _send_email_notification(subject: str, body: str, html_body: Optional[str] = None) -> bool:
    """Send email notification for critical inbox messages."""
    if not EMAIL_ENABLED:
        logger.warning("Email notifications disabled - missing credentials")
        return False
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECIPIENT
        
        msg.attach(MIMEText(body, "plain"))
        
        if html_body:
            msg.attach(MIMEText(html_body, "html"))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        
        logger.info(f"Email notification sent to {EMAIL_RECIPIENT}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
        return False


def _send_crash_email_notification(crash_report: Dict[str, Any]) -> bool:
    """Send email notification for a new crash report."""
    service_name = crash_report.get("details", {}).get("service", "Unknown service")
    crash_time = crash_report.get("timestamp", "Unknown time")
    severity = crash_report.get("severity", "warning")
    
    subject = f"[FoveAI {severity.upper()}] {service_name} Crash Detected"
    
    body = f"""FoveAI Service Crash Alert

Service: {service_name}
Crash Time: {crash_time}
Severity: {severity.upper()}

Summary: {crash_report.get("summary", "No summary available")}

---
This is an automated notification from your FoveAI system.
To view full crash details, open the Web UI inbox.
"""
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #0a0a0a; color: #e0e0e0;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: {'#ff4444' if severity == 'critical' else '#ffaa00'};">
                ⚠️ FoveAI Service Crash Alert
            </h2>
            <div style="background: #1a1a1a; padding: 20px; border-radius: 8px; border-left: 4px solid {'#ff4444' if severity == 'critical' else '#ffaa00'};">
                <p><strong>Service:</strong> {service_name}</p>
                <p><strong>Crash Time:</strong> {crash_time}</p>
                <p><strong>Severity:</strong> <span style="color: {'#ff4444' if severity == 'critical' else '#ffaa00'};">{severity.upper()}</span></p>
                <p><strong>Summary:</strong> {crash_report.get("summary", "No summary available")}</p>
            </div>
            <p style="margin-top: 20px; color: #888; font-size: 0.9em;">
                This is an automated notification from your FoveAI system.<br>
                Open the Web UI inbox to view full crash details and launch healing swarms.
            </p>
        </div>
    </body>
    </html>
    """
    
    return _send_email_notification(subject, body, html_body)


@app.get("/api/inbox/crash-report/{report_id}")
async def get_crash_report_details(report_id: str, _auth: None = Depends(require_webui_login)):
    """Get full content of a specific crash report."""
    if not os.path.exists(ERROR_REPORTS_DIR):
        raise HTTPException(status_code=404, detail="No crash reports directory")
    
    report_path = Path(ERROR_REPORTS_DIR) / f"{report_id}.txt"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
    
    try:
        content = report_path.read_text(encoding="utf-8")
        return {"content": content, "filename": report_path.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {e}")


class EmailConfig(BaseModel):
    """Email configuration for notifications."""
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    sender: Optional[str] = None
    recipient: Optional[str] = None
    enabled: bool = False


@app.get("/api/inbox/email-config")
async def get_email_config(_auth: None = Depends(require_webui_login)):
    """Get current email notification configuration."""
    return {
        "enabled": EMAIL_ENABLED,
        "smtp_server": SMTP_SERVER,
        "smtp_port": SMTP_PORT,
        "sender": EMAIL_SENDER,
        "recipient": EMAIL_RECIPIENT if EMAIL_SENDER else "",
        "configured": bool(EMAIL_SENDER and EMAIL_PASSWORD),
    }


@app.put("/api/inbox/email-config")
async def update_email_config(config: EmailConfig, _auth: None = Depends(require_webui_login)):
    """Update email notification configuration."""
    global EMAIL_SENDER, EMAIL_RECIPIENT, SMTP_SERVER, SMTP_PORT, EMAIL_ENABLED
    
    if config.smtp_server:
        SMTP_SERVER = config.smtp_server
    if config.smtp_port:
        SMTP_PORT = config.smtp_port
    if config.sender:
        EMAIL_SENDER = config.sender
    if config.recipient:
        EMAIL_RECIPIENT = config.recipient
    
    EMAIL_ENABLED = config.enabled and EMAIL_SENDER
    
    return {
        "enabled": EMAIL_ENABLED,
        "smtp_server": SMTP_SERVER,
        "smtp_port": SMTP_PORT,
        "sender": EMAIL_SENDER,
        "recipient": EMAIL_RECIPIENT,
    }


@app.post("/api/inbox/send-test-email")
async def send_test_email(_auth: None = Depends(require_webui_login)):
    """Send a test email to verify configuration."""
    if not EMAIL_ENABLED:
        raise HTTPException(status_code=400, detail="Email not configured")
    
    subject = "[FoveAI] Email Test - Configuration Verified"
    body = """FoveAI Email Notification Test

This is a test email to verify your notification configuration.

If you received this, your FoveAI system can send you email alerts for:
- Service crash reports
- Critical system notifications
- Director healing mission results

---
Sent from your FoveAI system
"""
    
    html_body = """
    <html>
    <body style="font-family: Arial, sans-serif; background: #0a0a0a; color: #e0e0e0;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #00f3ff;">✅ FoveAI Email Test Successful</h2>
            <div style="background: #1a1a1a; padding: 20px; border-radius: 8px; border-left: 4px solid #00f3ff;">
                <p>Your FoveAI system can now send email notifications for:</p>
                <ul>
                    <li>Service crash reports</li>
                    <li>Critical system notifications</li>
                    <li>Director healing mission results</li>
                </ul>
            </div>
            <p style="margin-top: 20px; color: #888; font-size: 0.9em;">
                Sent from your FoveAI system
            </p>
        </div>
    </body>
    </html>
    """
    
    success = _send_email_notification(subject, body, html_body)
    if success:
        return {"ok": True, "message": "Test email sent successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test email")


@app.post("/api/inbox/notify-crash")
async def notify_crash_via_email(report_id: str, _auth: None = Depends(require_webui_login)):
    """Send email notification for a specific crash report."""
    if not EMAIL_ENABLED:
        raise HTTPException(status_code=400, detail="Email notifications not configured")
    
    if not os.path.exists(ERROR_REPORTS_DIR):
        raise HTTPException(status_code=404, detail="No crash reports directory")
    
    report_path = Path(ERROR_REPORTS_DIR) / f"{report_id}.txt"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
    
    content = report_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    service_name = "Unknown"
    crash_time = report_path.stem.replace("_crash_", "").replace("_", ":")
    
    for line in lines[:20]:
        if line.startswith("Service: "):
            service_name = line.replace("Service: ", "")
        elif line.startswith("Crash Time: "):
            crash_time = line.replace("Crash Time: ", "")
    
    crash_report = {
        "id": report_id,
        "type": "crash_report",
        "title": f"{service_name} Crash",
        "summary": f"{service_name} crashed - see details",
        "timestamp": crash_time,
        "severity": "critical" if any("CRITICAL" in line or "FATAL" in line for line in lines[:30]) else "warning",
        "details": {"service": service_name, "content": content}
    }
    
    success = _send_crash_email_notification(crash_report)
    if success:
        return {"ok": True, "message": f"Email sent for crash: {service_name}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email notification")


# ── Director Healing Mission Endpoints ─────────────────────────────────────────

class DirectorHealingRequest(BaseModel):
    """Request for Director to analyze a crash and direct healing."""
    crash_report_id: Optional[str] = None
    service_name: str
    crash_count: int = 1
    time_window_minutes: int = 5
    auto_execute: bool = False


async def _run_director_healing(
    service_name: str,
    crash_report_content: str,
    crash_count: int,
    time_window_minutes: int,
) -> dict[str, Any]:
    """Run Director healing analysis for a service crash."""
    if not DIRECTOR_MANAGER_AVAILABLE:
        return {"success": False, "error": "Director Manager not available"}
    
    mission_id = f"healing_{service_name}_{int(time.time())}"
    
    # Build healing prompt
    user_prompt = DIRECTOR_HEALING_PROMPT_TEMPLATE.format(
        mission_id=mission_id,
        service_name=service_name,
        crash_count=crash_count,
        time_window=f"{time_window_minutes} minutes",
        crash_time=datetime.now().isoformat(),
        error_report_content=crash_report_content[:50000],  # Limit context
        foveai_version="FoveAI-lite",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
        os_info=f"Windows {os.name}",
    )
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{os.getenv('FOVEAI_DIRECTOR_BASE_URL', 'https://ollama.com/v1').rstrip('/')}/chat/completions",
                headers=_cloud_headers(os.getenv("FOVEAI_DIRECTOR_API_KEY", os.getenv("FOVEAI_REPERTOIRE_OLLAMA_API_KEY", ""))),
                json={
                    "model": os.getenv("FOVEAI_DIRECTOR_MODEL", "deepseek-v4-pro:1m"),
                    "messages": [
                        {"role": "system", "content": DIRECTOR_SYSTEM_PROMPT.replace("feature indexing", "service healing and diagnostics")},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 8192,
                    "stream": False,
                }
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            
            # Try to parse JSON response
            try:
                healing_plan = json.loads(raw_content)
            except json.JSONDecodeError:
                # Extract JSON from markdown code block
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
                if match:
                    healing_plan = json.loads(match.group(1))
                else:
                    healing_plan = {"diagnosis": raw_content, "severity": "unknown", "immediate_actions": []}
            
            return {
                "success": True,
                "mission_id": mission_id,
                "service": service_name,
                "healing_plan": healing_plan,
                "raw_response": raw_content,
            }
            
    except Exception as e:
        logger.exception("Director healing failed")
        return {"success": False, "error": str(e)}


@app.post("/api/director/heal")
async def post_director_heal(req: DirectorHealingRequest, _auth: None = Depends(require_webui_login)):
    """Request Director to analyze a crash and direct healing swarm."""
    if not DIRECTOR_MANAGER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Director Manager not available")
    
    # Get crash report content
    crash_content = ""
    if req.crash_report_id:
        report_path = Path(ERROR_REPORTS_DIR) / f"{req.crash_report_id}.txt" if ERROR_REPORTS_DIR else None
        if report_path and report_path.exists():
            crash_content = report_path.read_text(encoding="utf-8")
    
    if not crash_content:
        crash_content = f"Service {req.service_name} has crashed {req.crash_count} times in {req.time_window_minutes} minutes."
    
    # Run Director healing
    result = await _run_director_healing(
        service_name=req.service_name,
        crash_report_content=crash_content,
        crash_count=req.crash_count,
        time_window_minutes=req.time_window_minutes,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Director healing failed"))
    
    # Auto-execute if requested
    if req.auto_execute and result.get("healing_plan", {}).get("immediate_actions"):
        # Queue actions for swarm orchestrator
        # pyrefly: ignore [missing-import]
        from swarm_orchestrator import execute_swarm_task
        if SWARM_AVAILABLE and execute_swarm_task:
            healing_plan = result["healing_plan"]
            swarm_context = json.dumps({
                "service": req.service_name,
                "diagnosis": healing_plan.get("diagnosis", ""),
                "actions": healing_plan.get("immediate_actions", []),
            })
            try:
                await execute_swarm_task(
                    f"Heal {req.service_name}: {healing_plan.get('diagnosis', 'Unknown issue')}",
                    swarm_context
                )
                result["swarm_executed"] = True
            except Exception as e:
                logger.warning(f"Swarm execution failed: {e}")
                result["swarm_executed"] = False
    
    return result


@app.get("/api/director/heal/status")
async def get_director_heal_status(_auth: None = Depends(require_webui_login)):
    """Get status of recent healing missions."""
    # Return recent healing mission status from logs
    return {
        "recent_healing_missions": [],
        "director_available": DIRECTOR_MANAGER_AVAILABLE,
        "cloud_enabled": DIRECTOR_CLOUD_ENABLED,
    }


# ── Director Manager Endpoints ───────────────────────────────────────────────

try:
    # pyrefly: ignore [missing-import]
    from director_manager import (
        DirectorManager,
        IndexWorker,
        run_director_analysis,
        DIRECTOR_CLOUD_ENABLED,
        DIRECTOR_AUTO_APPLY,
    )
    DIRECTOR_MANAGER_AVAILABLE = True
except Exception as _dm_err:
    DIRECTOR_MANAGER_AVAILABLE = False
    DirectorManager = None
    IndexWorker = None
    run_director_analysis = None
    DIRECTOR_CLOUD_ENABLED = False
    DIRECTOR_AUTO_APPLY = False
    DIRECTOR_HEALING_PROMPT_TEMPLATE = (
        "Analyze the following service crash and provide a healing plan.\n\n"
        "Mission ID: {mission_id}\nService: {service_name}\n"
        "Crash count: {crash_count} in {time_window}\n"
        "Crash time: {crash_time}\nFoveAI version: {foveai_version}\n"
        "Python: {python_version}\nOS: {os_info}\n\n"
        "Error report:\n{error_report_content}\n\n"
        "Provide: 1) Root cause analysis 2) Immediate actions 3) Long-term fixes"
    )
    DIRECTOR_SYSTEM_PROMPT = (
        "You are a diagnostic AI for the FoveAI system. "
        "Analyse service crashes and provide actionable healing plans."
    )
    logger.warning(f"Director Manager not available: {_dm_err}")


class DirectorAnalysisRequest(BaseModel):
    """Request to run Director analysis on existing discovery report."""
    report_filename: Optional[str] = None
    auto_apply: Optional[bool] = None


@app.get("/api/director/status")
async def get_director_status(_auth: None = Depends(require_webui_login)):
    """Get Director Manager configuration and availability."""
    return {
        "available": DIRECTOR_MANAGER_AVAILABLE,
        "cloud_enabled": DIRECTOR_CLOUD_ENABLED,
        "auto_apply_default": DIRECTOR_AUTO_APPLY,
        "model": os.getenv("FOVEAI_DIRECTOR_MODEL", "deepseek-v4-pro:1m"),
        "base_url": os.getenv("FOVEAI_DIRECTOR_BASE_URL", "https://ollama.com/v1"),
    }


@app.post("/api/director/analyze")
async def post_director_analyze(req: DirectorAnalysisRequest, _auth: None = Depends(require_webui_login)):
    """Run Director analysis on an existing discovery report.

    If report_filename is provided, loads that report from .logs/discovery_reports/
    Otherwise uses the most recent report.
    """
    if not DIRECTOR_MANAGER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Director Manager not available")

    # pyrefly: ignore [missing-import]
    from discovery_swarm import list_discovery_reports, _load_inventory_flat

    # Get report to analyze
    reports = list_discovery_reports(limit=10)
    if req.report_filename:
        report = next((r for r in reports if r.get("_filename") == req.report_filename), None)
    else:
        report = reports[0] if reports else None

    if not report:
        raise HTTPException(status_code=404, detail="No discovery report found")

    # Extract unindexed features from report
    unindexed_features = []
    for drone_report in report.get("drone_reports", []):
        for feature in drone_report.get("features", []):
            # Simple category guess based on path
            src_file = feature.get("source_file", "").lower()
            ft = feature.get("feature_type", "")
            if "docker" in src_file or "compose" in src_file:
                cat = "docker"
            elif src_file.startswith("frontend/web"):
                cat = "web"
            elif src_file.startswith("frontend/xr") or "godot" in src_file:
                cat = "godot"
            elif src_file.startswith("mind"):
                cat = "backend"
            elif src_file.startswith("scripts"):
                cat = "ops"
            elif ft == "endpoint":
                cat = "web"
            elif ft == "service":
                cat = "docker"
            else:
                cat = "other"

            unindexed_features.append({
                "source_file": feature.get("source_file", ""),
                "feature_type": feature.get("feature_type", ""),
                "name": feature.get("name", ""),
                "description": feature.get("description", ""),
                "proposed_category": cat,
                "proposed_tier": feature.get("tier_guess", "C"),
                "evidence": feature.get("evidence", ""),
            })

    # Load current inventory
    inventory_rows = _load_inventory_flat()

    try:
        result = await run_director_analysis(
            mission_id=report.get("mission_id", "manual"),
            discovery_summary=report.get("summary", ""),
            files_scanned=report.get("drone_reports", [{}])[0].get("files_scanned", 0),
            unindexed_features=unindexed_features,
            current_inventory_rows=inventory_rows,
            auto_apply=req.auto_apply,
        )

        if result.get("success"):
            return {"ok": True, "result": result}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Director analysis failed"))

    except Exception as e:
        logger.exception("Director analysis failed")
        raise HTTPException(status_code=500, detail=f"Director analysis failed: {e}")


@app.get("/api/director/reports")
async def get_director_reports(limit: int = 20, _auth: None = Depends(require_webui_login)):
    """List Director analysis reports (files with _director.json suffix)."""
    # pyrefly: ignore [missing-import]
    from discovery_swarm import REPORTS_DIR

    if not REPORTS_DIR.is_dir():
        return {"reports": []}

    reports = []
    for p in sorted(REPORTS_DIR.glob("*_director.json"), key=lambda x: x.name, reverse=True)[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["_filename"] = p.name
            reports.append(data)
        except Exception:
            continue

    return {"reports": reports}


@app.post("/api/director/apply")
async def post_director_apply(req: Dict[str, Any], _auth: None = Depends(require_webui_login)):
    """Apply Director decisions from a report to FEATURE_INVENTORY.md.

    Expects: {"report_filename": "20260502_195944_director.json"}
    """
    if not DIRECTOR_MANAGER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Director Manager not available")

    # pyrefly: ignore [missing-import]
    from discovery_swarm import REPORTS_DIR

    report_filename = req.get("report_filename")
    if not report_filename:
        raise HTTPException(status_code=400, detail="report_filename required")

    report_path = REPORTS_DIR / report_filename
    if not report_path.is_file():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_filename}")

    try:
        report_data = json.loads(report_path.read_text(encoding="utf-8"))

        # Reconstruct DirectorAnalysis from stored report
        # pyrefly: ignore [missing-import]
        from director_manager import DirectorAnalysis, DirectorIndexDecision

        decisions = []
        for d in report_data.get("decisions", []):
            decisions.append(DirectorIndexDecision(
                source_file=d.get("source_file", ""),
                feature_type=d.get("feature_type", ""),
                name=d.get("name", ""),
                description=d.get("description", ""),
                category=d.get("category", "other"),
                tier=d.get("tier", "C"),
                reasoning=d.get("reasoning", ""),
                action=d.get("action", "skip"),
            ))

        analysis = DirectorAnalysis(
            mission_id=report_data.get("mission_id", ""),
            timestamp=report_data.get("timestamp", ""),
            total_features_analyzed=report_data.get("total_features_analyzed", 0),
            features_to_index=report_data.get("features_to_index", 0),
            features_skipped=report_data.get("features_skipped", 0),
            decisions=decisions,
            summary=report_data.get("summary", ""),
            raw_response=report_data.get("raw_response", ""),
            confidence=report_data.get("confidence", 0.5),
            model_used=report_data.get("model_used", ""),
        )

        worker = IndexWorker()
        result = worker.apply_decisions(analysis, dry_run=req.get("dry_run", False))

        return {"ok": True, "result": result}

    except Exception as e:
        logger.exception("Failed to apply Director decisions")
        raise HTTPException(status_code=500, detail=f"Failed to apply decisions: {e}")


# ============================================
# ALBUM ART GENERATOR API ENDPOINTS
# ============================================

# Session storage for album art generation workflow
_album_art_sessions: Dict[str, Dict[str, Any]] = {}

class AlbumArtSession(BaseModel):
    """Request model for album art generation session."""
    band_name: str = ""
    album_title: str = ""
    songs: List[Dict[str, str]] = Field(default_factory=list)
    reference_album_id: Optional[str] = None
    art_style_id: Optional[str] = None
    color_profile_id: Optional[str] = None
    custom_colors: Optional[List[str]] = None
    controlnet_strength: float = 0.5
    seed: Optional[int] = None
    width: int = 512
    height: int = 512
    steps: int = 4
    guidance_scale: float = 7.5


@app.get("/album-art-studio", response_class=HTMLResponse)
async def get_album_art_studio(_auth: None = Depends(require_webui_login)):
    """Serve the Album Art Studio page."""
    path = os.path.join(BASE_DIR, "album_art_studio.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Album Art Studio not found")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/album-art/reference/albums")
async def get_reference_albums(_auth: None = Depends(require_webui_login)):
    """Get list of famous album covers for reference."""
    try:
        from album_art_generator import get_famous_albums
        return {"albums": get_famous_albums()}
    except Exception as e:
        logger.warning(f"Failed to load reference albums: {e}")
        return {"albums": []}


@app.get("/api/album-art/reference/styles")
async def get_reference_styles(_auth: None = Depends(require_webui_login)):
    """Get list of art styles."""
    try:
        from album_art_generator import get_art_styles
        return {"styles": get_art_styles()}
    except Exception as e:
        logger.warning(f"Failed to load art styles: {e}")
        return {"styles": []}


@app.get("/api/album-art/reference/colors")
async def get_reference_colors(_auth: None = Depends(require_webui_login)):
    """Get list of color profiles."""
    try:
        from album_art_generator import get_color_profiles
        return {"profiles": get_color_profiles()}
    except Exception as e:
        logger.warning(f"Failed to load color profiles: {e}")
        return {"profiles": []}


@app.get("/api/album-art/reference/controlnet")
async def get_controlnet_presets_api(_auth: None = Depends(require_webui_login)):
    """Get ControlNet strength presets."""
    try:
        from album_art_generator import get_controlnet_presets
        return {"presets": get_controlnet_presets()}
    except Exception as e:
        logger.warning(f"Failed to load controlnet presets: {e}")
        return {"presets": []}


@app.post("/api/album-art/session/create")
async def create_album_art_session(
    session_data: AlbumArtSession,
    _auth: None = Depends(require_webui_login)
):
    """Create a new album art generation session."""
    session_id = str(uuid.uuid4())
    _album_art_sessions[session_id] = {
        "project": session_data.dict(),
        "generated_images": {},
        "choices": {},
        "prompts": {},
        "created_at": time.time(),
    }
    return {"session_id": session_id, "status": "created"}


@app.get("/api/album-art/session/{session_id}")
async def get_album_art_session(
    session_id: str,
    _auth: None = Depends(require_webui_login)
):
    """Get session data including all generated images and choices."""
    if session_id not in _album_art_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _album_art_sessions[session_id]
    return {
        "session_id": session_id,
        "project": session["project"],
        "generated_images": session["generated_images"],
        "choices": session.get("choices", {}),
    }


@app.delete("/api/album-art/session/{session_id}")
async def delete_album_art_session(
    session_id: str,
    _auth: None = Depends(require_webui_login)
):
    """Delete a generation session."""
    if session_id in _album_art_sessions:
        del _album_art_sessions[session_id]
    
    # Also delete from disk
    try:
        from album_art_generator import ALBUM_ART_DIR
        session_dir = os.path.join(ALBUM_ART_DIR, session_id)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
    except Exception as e:
        logger.warning(f"Failed to delete session directory: {e}")
    
    return {"status": "deleted", "session_id": session_id}


@app.post("/api/album-art/generate/album")
async def generate_album_art(
    request: Dict[str, Any],
    _auth: None = Depends(require_webui_login)
):
    """
    Generate album cover art using the creative service.
    Returns generation option for Next/Choose workflow.
    """
    try:
        session_id = request.get("session_id")
        if not session_id or session_id not in _album_art_sessions:
            raise HTTPException(status_code=400, detail="Invalid or missing session_id")
        
        session = _album_art_sessions[session_id]
        project = session["project"]
        
        # Get reference data
        from album_art_generator import (
            get_famous_albums, get_art_styles, get_color_profiles,
            build_album_art_prompt
        )
        
        ref_album = None
        if project.get("reference_album_id"):
            for album in get_famous_albums():
                if album["id"] == project["reference_album_id"]:
                    ref_album = album
                    break
        
        art_style = None
        if project.get("art_style_id"):
            for style in get_art_styles():
                if style["id"] == project["art_style_id"]:
                    art_style = style
                    break
        
        color_profile = None
        if project.get("color_profile_id"):
            for profile in get_color_profiles():
                if profile["id"] == project["color_profile_id"]:
                    color_profile = profile
                    break
        
        # Build prompt
        prompt, negative_prompt = build_album_art_prompt(
            band_name=project.get("band_name", ""),
            album_title=project.get("album_title", ""),
            song_contexts=[{"title": s.get("title", ""), "description": s.get("description", "")} 
                          for s in project.get("songs", [])],
            reference_album=ref_album,
            art_style=art_style,
            color_profile=color_profile,
            custom_colors=project.get("custom_colors"),
        )
        
        # Call creative service
        async with httpx.AsyncClient(timeout=120.0) as client:
            creative_payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": project.get("width", 512),
                "height": project.get("height", 512),
                "num_inference_steps": project.get("steps", 4),
                "guidance_scale": project.get("guidance_scale", 7.5),
                "seed": project.get("seed"),
                "model_type": "sdxl_turbo_onnx",
            }
            resp = await client.post(f"{CREATIVE_URL}/api/dream", json=creative_payload)
            result = resp.json()
        
        # Get image data
        image_data = result.get("image", result.get("base64", ""))
        
        # Store generation option
        option_id = f"album_{int(time.time())}"
        session["generated_images"][option_id] = image_data
        session["prompts"][option_id] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
        }
        
        return {
            "session_id": session_id,
            "option_id": option_id,
            "image": image_data,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
        }
        
    except httpx.RequestError as e:
        logger.exception("Creative service unavailable")
        raise HTTPException(status_code=503, detail=f"Creative service unavailable: {str(e)}")
    except Exception as e:
        logger.exception("Album art generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.post("/api/album-art/generate/song")
async def generate_song_art(
    request: Dict[str, Any],
    _auth: None = Depends(require_webui_login)
):
    """
    Generate individual song cover art.
    """
    try:
        session_id = request.get("session_id")
        song_index = request.get("song_index", 0)
        
        if not session_id or session_id not in _album_art_sessions:
            raise HTTPException(status_code=400, detail="Invalid or missing session_id")
        
        session = _album_art_sessions[session_id]
        project = session["project"]
        songs = project.get("songs", [])
        
        if song_index >= len(songs):
            raise HTTPException(status_code=400, detail="Invalid song index")
        
        song = songs[song_index]
        
        # Get reference data
        from album_art_generator import (
            get_art_styles, get_color_profiles, build_song_art_prompt
        )
        
        art_style = None
        if project.get("art_style_id"):
            for style in get_art_styles():
                if style["id"] == project["art_style_id"]:
                    art_style = style
                    break
        
        color_profile = None
        if project.get("color_profile_id"):
            for profile in get_color_profiles():
                if profile["id"] == project["color_profile_id"]:
                    color_profile = profile
                    break
        
        # Build prompt
        prompt, negative_prompt = build_song_art_prompt(
            band_name=project.get("band_name", ""),
            album_title=project.get("album_title", ""),
            song_title=song.get("title", ""),
            song_description=song.get("description", ""),
            album_art_style=art_style,
            color_profile=color_profile,
            custom_colors=project.get("custom_colors"),
        )
        
        # Call creative service
        async with httpx.AsyncClient(timeout=120.0) as client:
            creative_payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": project.get("width", 512),
                "height": project.get("height", 512),
                "num_inference_steps": project.get("steps", 4),
                "guidance_scale": project.get("guidance_scale", 7.5),
                "seed": project.get("seed"),
                "model_type": "sdxl_turbo_onnx",
            }
            resp = await client.post(f"{CREATIVE_URL}/api/dream", json=creative_payload)
            result = resp.json()
        
        image_data = result.get("image", result.get("base64", ""))
        
        # Store generation option
        option_id = f"song_{song_index}_{int(time.time())}"
        session["generated_images"][option_id] = image_data
        session["prompts"][option_id] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
        }
        
        return {
            "session_id": session_id,
            "song_index": song_index,
            "option_id": option_id,
            "image": image_data,
            "prompt": prompt,
        }
        
    except httpx.RequestError as e:
        logger.exception("Creative service unavailable")
        raise HTTPException(status_code=503, detail=f"Creative service unavailable: {str(e)}")
    except Exception as e:
        logger.exception("Song art generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.post("/api/album-art/choose")
async def choose_artwork(
    request: Dict[str, Any],
    _auth: None = Depends(require_webui_login)
):
    """
    Choose a generated artwork as the final version.
    """
    session_id = request.get("session_id")
    option_id = request.get("option_id")
    art_type = request.get("art_type", "album")
    
    if not session_id or not option_id:
        raise HTTPException(status_code=400, detail="Missing session_id or option_id")
    
    if session_id not in _album_art_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _album_art_sessions[session_id]
    if option_id not in session["generated_images"]:
        raise HTTPException(status_code=404, detail="Option not found")
    
    # Store choice
    session["choices"][art_type] = option_id
    
    return {
        "session_id": session_id,
        "art_type": art_type,
        "chosen_option": option_id,
        "status": "chosen",
    }


@app.post("/api/album-art/upscale")
async def upscale_artwork(
    request: Dict[str, Any],
    _auth: None = Depends(require_webui_login)
):
    """
    Upscale generated artwork by 4x.
    """
    session_id = request.get("session_id")
    option_id = request.get("option_id")
    factor = request.get("factor", 4)
    
    if not session_id or not option_id:
        raise HTTPException(status_code=400, detail="Missing session_id or option_id")
    
    if session_id not in _album_art_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _album_art_sessions[session_id]
    if option_id not in session["generated_images"]:
        raise HTTPException(status_code=404, detail="Option not found")
    
    # Decode image
    from album_art_generator import upscale_image_pil, enhance_image_colors
    image_data = session["generated_images"][option_id]
    
    # Handle different image data formats
    if image_data.startswith("data:image"):
        # Data URL format
        image_data = image_data.split(",")[1]
    
    image_bytes = base64.b64decode(image_data)
    image = Image.open(io.BytesIO(image_bytes))
    
    # Upscale
    upscaled = upscale_image_pil(image, factor=factor)
    upscaled = enhance_image_colors(upscaled)
    
    # Save to buffer
    output = io.BytesIO()
    upscaled.save(output, format="PNG")
    output.seek(0)
    upscaled_data = base64.b64encode(output.read()).decode("utf-8")
    
    # Store upscaled version
    upscaled_id = f"{option_id}_upscaled"
    session["generated_images"][upscaled_id] = upscaled_data
    
    return {
        "option_id": upscaled_id,
        "original_size": {"width": image.width, "height": image.height},
        "upscaled_size": {"width": upscaled.width, "height": upscaled.height},
        "image": upscaled_data,
    }


@app.get("/api/album-art/download/{session_id}")
async def download_artwork_zip(
    session_id: str,
    upscale: bool = False,
    _auth: None = Depends(require_webui_login)
):
    """
    Download all artwork as a ZIP file.
    """
    if session_id not in _album_art_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _album_art_sessions[session_id]
    
    # Prepare images dictionary
    images = {}
    for option_id, image_data in session["generated_images"].items():
        if upscale and not option_id.endswith("_upscaled"):
            continue
        if not upscale and option_id.endswith("_upscaled"):
            continue
        
        # Handle different image data formats
        if image_data.startswith("data:image"):
            image_data = image_data.split(",")[1]
        
        images[option_id] = base64.b64decode(image_data)
    
    if not images:
        raise HTTPException(status_code=404, detail="No images to download")
    
    # Create ZIP
    from album_art_generator import create_zip_download
    zip_data, filename = create_zip_download(session_id, images, upscale_factor=4 if upscale else 1)
    
    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# =============================================================================
# Vision Feed API (for Mobile App)
# =============================================================================
# Vision sources configuration
VISION_SOURCES = {
    "desktop_capture": {
        "name": "Desktop Screen Capture",
        "type": "screen",
        "enabled": True,
    },
    "phone_camera": {
        "name": "Mobile Phone Camera",
        "type": "camera",
        "enabled": True,
    },
    "vr_headset": {
        "name": "VR Headset Passthrough",
        "type": "vr",
        "enabled": False,
    },
    "security_cam": {
        "name": "Security Camera",
        "type": "ip_camera",
        "enabled": False,
    },
}

# Cache for vision feeds
_vision_cache: Dict[str, Dict[str, Any]] = {}


class VisionSource(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool
    last_capture: Optional[str] = None


class VisionFeedResponse(BaseModel):
    source_id: str
    source_name: str
    image_data: Optional[str] = None  # base64 encoded JPEG
    timestamp: str
    width: int = 640
    height: int = 480


class VisionCaptureRequest(BaseModel):
    source_id: str = "desktop_capture"
    width: int = 640
    height: int = 480
    quality: int = 80


@app.get("/api/vision/sources")
async def list_vision_sources(_auth: None = Depends(require_webui_login)):
    """
    List all available vision feed sources.
    """
    sources = []
    for source_id, config in VISION_SOURCES.items():
        last_capture = None
        if source_id in _vision_cache:
            last_capture = _vision_cache[source_id].get("timestamp")
        sources.append(VisionSource(
            id=source_id,
            name=config["name"],
            type=config["type"],
            enabled=config["enabled"],
            last_capture=last_capture,
        ))
    return {"sources": sources}


@app.get("/api/vision/feed/{source_id}")
async def get_vision_feed(
    source_id: str,
    _auth: None = Depends(require_webui_login)
):
    """
    Get the latest vision feed from a source.
    Returns cached image or generates a new capture.
    """
    if source_id not in VISION_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown vision source: {source_id}")
    
    config = VISION_SOURCES[source_id]
    if not config["enabled"]:
        raise HTTPException(status_code=400, detail=f"Vision source {source_id} is disabled")
    
    # Return cached image if recent (within 5 seconds)
    if source_id in _vision_cache:
        cached = _vision_cache[source_id]
        cache_age = time.time() - cached.get("cache_time", 0)
        if cache_age < 5:
            return VisionFeedResponse(
                source_id=source_id,
                source_name=config["name"],
                image_data=cached.get("image_data"),
                timestamp=cached.get("timestamp"),
                width=cached.get("width", 640),
                height=cached.get("height", 480),
            )
    
    # Generate new capture based on source type
    image_data, width, height = await _capture_vision_source(source_id)
    
    if image_data:
        timestamp = datetime.utcnow().isoformat() + "Z"
        _vision_cache[source_id] = {
            "image_data": image_data,
            "timestamp": timestamp,
            "cache_time": time.time(),
            "width": width,
            "height": height,
        }
        return VisionFeedResponse(
            source_id=source_id,
            source_name=config["name"],
            image_data=image_data,
            timestamp=timestamp,
            width=width,
            height=height,
        )
    else:
        raise HTTPException(status_code=500, detail=f"Failed to capture from {source_id}")


@app.post("/api/vision/capture")
async def request_vision_capture(
    req: VisionCaptureRequest,
    _auth: None = Depends(require_webui_login)
):
    """
    Request a fresh vision capture from a source.
    """
    if req.source_id not in VISION_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown vision source: {req.source_id}")
    
    config = VISION_SOURCES[req.source_id]
    if not config["enabled"]:
        raise HTTPException(status_code=400, detail=f"Vision source {req.source_id} is disabled")
    
    # Generate new capture
    image_data, width, height = await _capture_vision_source(
        req.source_id, 
        req.width, 
        req.height,
        req.quality
    )
    
    if image_data:
        timestamp = datetime.utcnow().isoformat() + "Z"
        _vision_cache[req.source_id] = {
            "image_data": image_data,
            "timestamp": timestamp,
            "cache_time": time.time(),
            "width": width,
            "height": height,
        }
        return VisionFeedResponse(
            source_id=req.source_id,
            source_name=config["name"],
            image_data=image_data,
            timestamp=timestamp,
            width=width,
            height=height,
        )
    else:
        raise HTTPException(status_code=500, detail=f"Failed to capture from {req.source_id}")


async def _capture_vision_source(
    source_id: str, 
    width: int = 640, 
    height: int = 480,
    quality: int = 80
) -> tuple[Optional[str], int, int]:
    """
    Capture image from a vision source.
    Returns (base64_jpeg, width, height) or (None, 0, 0) on failure.
    """
    try:
        if source_id == "desktop_capture":
            return await _capture_desktop(width, height, quality)
        elif source_id == "phone_camera":
            return await _capture_phone_camera(width, height, quality)
        elif source_id == "vr_headset":
            return await _capture_vr_passthrough(width, height, quality)
        elif source_id == "security_cam":
            return await _capture_security_cam(width, height, quality)
    except Exception as e:
        logger.error(f"Vision capture error for {source_id}: {e}")
    return None, 0, 0


async def _capture_desktop(width: int, height: int, quality: int) -> tuple[Optional[str], int, int]:
    """Capture desktop screen using pyscreenshot or mss."""
    try:
        import pyscreenshot as ImageGrab  # type: ignore
        from PIL import Image
        import io
        
        # Capture full screen
        screenshot = ImageGrab.grab()
        
        # Resize to requested dimensions (maintain aspect ratio)
        orig_w, orig_h = screenshot.size
        scale = min(width / orig_w, height / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        screenshot = screenshot.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Convert to JPEG
        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=quality)
        image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        return image_data, new_w, new_h
    except ImportError:
        logger.warning("pyscreenshot not available, desktop capture disabled")
        return None, 0, 0
    except Exception as e:
        logger.error(f"Desktop capture failed: {e}")
        return None, 0, 0


async def _capture_phone_camera(width: int, height: int, quality: int) -> tuple[Optional[str], int, int]:
    """
    Handle phone camera capture.
    For mobile app, this endpoint signals the app to upload a photo.
    The actual image comes from the mobile app's camera.
    """
    # Check if there's a recently uploaded phone camera image
    phone_cam_cache = os.path.join(os.path.dirname(BASE_DIR), "scratch", "phone_camera_latest.jpg")
    if os.path.exists(phone_cam_cache):
        try:
            from PIL import Image
            import io
            
            img = Image.open(phone_cam_cache)
            img = img.resize((width, height), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            
            return image_data, width, height
        except Exception as e:
            logger.error(f"Phone camera cache read failed: {e}")
    
    # No image available - return placeholder
    logger.warning("No phone camera image available")
    return None, 0, 0


async def _capture_vr_passthrough(width: int, height: int, quality: int) -> tuple[Optional[str], int, int]:
    """Capture VR headset passthrough camera feed."""
    # TODO: Implement VR passthrough capture via OpenXR
    logger.warning("VR passthrough capture not yet implemented")
    return None, 0, 0


async def _capture_security_cam(width: int, height: int, quality: int) -> tuple[Optional[str], int, int]:
    """Capture from IP security camera."""
    # TODO: Implement IP camera capture
    logger.warning("Security camera capture not yet implemented")
    return None, 0, 0


@app.post("/api/vision/upload/phone_camera")
async def upload_phone_camera_image(
    request: Request,
    _auth: None = Depends(require_webui_login)
):
    """
    Upload a phone camera image to the vision feed.
    Mobile app sends POST with image data.
    """
    try:
        body = await request.json()
        image_data = body.get("image_data")  # base64 encoded
        
        if not image_data:
            raise HTTPException(status_code=400, detail="No image_data in request")
        
        # Decode and save to cache
        if image_data.startswith("data:image"):
            image_data = image_data.split(",")[1]
        
        image_bytes = base64.b64decode(image_data)
        
        # Save to scratch directory
        cache_dir = os.path.join(os.path.dirname(BASE_DIR), "scratch")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "phone_camera_latest.jpg")
        
        with open(cache_path, "wb") as f:
            f.write(image_bytes)
        
        # Update vision cache
        timestamp = datetime.utcnow().isoformat() + "Z"
        _vision_cache["phone_camera"] = {
            "image_data": image_data,
            "timestamp": timestamp,
            "cache_time": time.time(),
            "width": 640,
            "height": 480,
        }
        
        return {"status": "uploaded", "timestamp": timestamp}
    except Exception as e:
        logger.error(f"Phone camera upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/web/scrape")
async def scrape_web_page(
    url: str,
    _auth: None = Depends(require_webui_login)
):
    """
    Scrape a web page and return its title + text content.
    Used by WebSearch.ts readPage() for page snapshots.
    Returns: { url, title, text, screenshots: [] }
    """
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ""
            self.text_parts: list[str] = []
            self._in_title = False
            self._skip_tags = {"script", "style", "noscript", "iframe", "svg", "head"}
            self._skip_depth = 0

        def handle_starttag(self, tag: str, attrs: list):
            tag_l = tag.lower()
            if tag_l == "title":
                self._in_title = True
            elif tag_l in self._skip_tags:
                self._skip_depth += 1

        def handle_endtag(self, tag: str):
            tag_l = tag.lower()
            if tag_l == "title":
                self._in_title = False
            elif tag_l in self._skip_tags and self._skip_depth > 0:
                self._skip_depth -= 1

        def handle_data(self, data: str):
            if self._skip_depth > 0:
                return
            stripped = data.strip()
            if not stripped:
                return
            if self._in_title:
                self.title += stripped + " "
            else:
                self.text_parts.append(stripped)

        def get_text(self) -> str:
            return "\n".join(self.text_parts)

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            verify=False,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 FoveAI-WebSearch/1.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        ) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"Target server returned {resp.status_code}"
                )

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                # Non-HTML response — return raw text preview
                raw = resp.text[:5000] if resp.text else ""
                return {
                    "url": str(resp.url),
                    "title": str(resp.url),
                    "text": raw,
                    "screenshots": [],
                }

            html = resp.text
            extractor = _TextExtractor()
            extractor.feed(html)
            extractor.close()

            title = extractor.title.strip() or str(resp.url)
            text = extractor.get_text()

            # Truncate to reasonable size (50KB max)
            if len(text) > 50000:
                text = text[:50000] + "\n\n[... truncated at 50KB ...]"

            return {
                "url": str(resp.url),
                "title": title,
                "text": text,
                "screenshots": [],
            }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timed out")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Could not connect to target server")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[WebScrape] Failed to scrape {url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/dev/aider")
async def run_aider_agent(
    request: Request,
    _auth: None = Depends(require_webui_login)
):
    """
    Execute the direct Antigravity coding agent (agy) to search and edit files.
    Accepts JSON body: { "prompt": "instructions..." }
    Streams raw agent planning and file modification logs.
    """
    from fastapi.responses import StreamingResponse
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    prompt = body.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing 'prompt' in request body")

    try:
        # pyrefly: ignore [missing-import]
        from ag_coder import run_antigravity_agent
        return StreamingResponse(run_antigravity_agent(prompt), media_type="text/plain")
    except Exception as e:
        logger.error(f"[J-Aider] Failed to load ag_coder: {e}")
        async def fallback_generator():
            yield f"[System Error] Failed to initialize Antigravity Coder Engine: {e}\n"
        return StreamingResponse(fallback_generator(), media_type="text/plain")

@app.get("/api/agy/stream")
async def agy_bridge_stream():
    """SSE stream bridging the Antigravity IDE and the XR Vessel."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    async def event_generator():
        bridge_file = os.path.join(FoveAI_ROOT, "Forge", "scratch", "agy_bridge.txt")
        # Ensure file exists
        os.makedirs(os.path.dirname(bridge_file), exist_ok=True)
        if not os.path.exists(bridge_file):
            with open(bridge_file, "w", encoding="utf-8") as f:
                f.write("")
        
        last_pos = os.path.getsize(bridge_file)
        
        while True:
            await asyncio.sleep(0.5)
            curr_pos = os.path.getsize(bridge_file)
            if curr_pos > last_pos:
                with open(bridge_file, "r", encoding="utf-8") as f:
                    f.seek(last_pos)
                    new_data = f.read()
                    last_pos = f.tell()
                if new_data:
                    for line in new_data.strip().split("\n"):
                        if line:
                            yield f"data: {json.dumps({'message': line})}\n\n"
            elif curr_pos < last_pos:
                # File was truncated/cleared
                last_pos = 0

    return StreamingResponse(event_generator(), media_type="text/event-stream")


"""CodeAgency API Routes — Avatar Self-Modification Backend"""

# ═══════════════════════════════════════════════════════════════════════════════
# CODE AGENCY API — Avatar Self-Modification Backend
# ═══════════════════════════════════════════════════════════════════════════════

# Import code_sheriff for safe self-modification
sys.path.insert(0, os.path.join(FoveAI_ROOT, "Mind", "Cognition"))
try:
    # pyrefly: ignore [missing-import]
    from code_sheriff import snapshot_file, validate_file, edit_file as sheriff_edit_file, NO_TOUCH_LIST
    CODE_SHERIFF_AVAILABLE = True
except Exception as _cs_err:
    CODE_SHERIFF_AVAILABLE = False
    logger.warning(f"[CodeAgency] code_sheriff not available: {_cs_err}")

CODE_PROTECTED = [".env", ".git/", "__pycache__", "venv/", "node_modules/", "backups/autosave/", ".venv/", "*.log", "*.tmp"]

def _is_safe_path(path: str) -> bool:
    path = path.replace("\\", "/")
    if CODE_SHERIFF_AVAILABLE:
        for forbidden in NO_TOUCH_LIST:
            if forbidden in path: return False
    for protected in CODE_PROTECTED:
        if protected.endswith("/") and protected in path: return False
        if protected.startswith("*") and path.endswith(protected[1:]): return False
        if protected in path: return False
    try:
        (Path(FoveAI_ROOT) / path).resolve().relative_to(Path(FoveAI_ROOT).resolve())
        return True
    except ValueError:
        return False

@app.get("/api/code/ls")
async def code_ls(dir: str = ".", _auth: None = Depends(require_webui_login)):
    try:
        target_dir = Path(FoveAI_ROOT) / dir
        if not str(target_dir.resolve()).startswith(str(Path(FoveAI_ROOT).resolve())):
            return JSONResponse(status_code=403, content={"error": "Access denied"})
        files = []
        for item in sorted(target_dir.iterdir()):
            stat = item.stat()
            files.append({"path": str(item.relative_to(FoveAI_ROOT)).replace("\\", "/"), "size": stat.st_size, "isDir": item.is_dir(), "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()})
        return {"files": files}
    except Exception as e:
        logger.error(f"[CodeAgency] ls failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/code/read")
async def code_read(path: str, maxLines: int = 500, _auth: None = Depends(require_webui_login)):
    try:
        if not _is_safe_path(path): return JSONResponse(status_code=403, content={"error": "Protected path"})
        file_path = Path(FoveAI_ROOT) / path
        if not file_path.exists(): return JSONResponse(status_code=404, content={"error": "File not found"})
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        if len(lines) > maxLines: content = "\n".join(lines[:maxLines]) + f"\n\n... [{len(lines) - maxLines} more lines]"
        return {"content": content, "truncated": len(lines) > maxLines}
    except Exception as e:
        logger.error(f"[CodeAgency] read failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/code/write")
async def code_write(request: Request, _auth: None = Depends(require_webui_login)):
    try:
        data = await request.json()
        path, content = data.get("path", ""), data.get("content", "")
        if not _is_safe_path(path): return JSONResponse(status_code=403, content={"success": False, "message": "Protected path"})
        file_path = Path(FoveAI_ROOT) / path
        if CODE_SHERIFF_AVAILABLE and file_path.exists(): snapshot_file(str(file_path))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        validation_errors = []
        if CODE_SHERIFF_AVAILABLE:
            valid, errors = validate_file(str(file_path))
            if not valid: validation_errors = errors
        return {"success": True, "message": f"Wrote {len(content)} chars to {path}", "validationErrors": validation_errors}
    except Exception as e:
        logger.error(f"[CodeAgency] write failed: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post("/api/code/edit")
async def code_edit(request: Request, _auth: None = Depends(require_webui_login)):
    try:
        data = await request.json()
        path, blocks = data.get("path", ""), data.get("blocks", [])
        if not _is_safe_path(path): return JSONResponse(status_code=403, content={"success": False, "message": "Protected path"})
        file_path = Path(FoveAI_ROOT) / path
        if not file_path.exists(): return JSONResponse(status_code=404, content={"success": False, "message": "File not found"})
        if CODE_SHERIFF_AVAILABLE:
            result = sheriff_edit_file(str(file_path), blocks)
            return result
        else:
            content = file_path.read_text(encoding="utf-8")
            for block in blocks:
                search, replace = block.get("search", ""), block.get("replace", "")
                if search in content: content = content.replace(search, replace, 1)
            file_path.write_text(content, encoding="utf-8")
            return {"success": True, "message": f"Edited {path} ({len(blocks)} blocks)"}
    except Exception as e:
        logger.error(f"[CodeAgency] edit failed: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/api/code/search")
async def code_search(q: str, glob: str = "*", _auth: None = Depends(require_webui_login)):
    import fnmatch
    results = []
    try:
        base_path = Path(FoveAI_ROOT)
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not any(p in d for p in ["__pycache__", "node_modules", ".git", "venv", ".venv", "backups/autosave"])]
            for filename in files:
                if not fnmatch.fnmatch(filename, glob): continue
                filepath = Path(root) / filename
                try:
                    rel_path = filepath.relative_to(base_path)
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    lines = content.split("\n")
                    for i, line in enumerate(lines, 1):
                        if q.lower() in line.lower():
                            results.append({"file": str(rel_path).replace("\\", "/"), "line": i, "content": line[:200], "match": q})
                            if sum(1 for r in results if r["file"] == str(rel_path).replace("\\", "/")) >= 5: break
                except Exception: continue
        return {"results": results[:100]}
    except Exception as e:
        logger.error(f"[CodeAgency] search failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/code/exec")
async def code_exec(request: Request, _auth: None = Depends(require_webui_login)):
    try:
        data = await request.json()
        command = data.get("command", "")
        SAFE_PREFIXES = ["npm run", "npx tsc", "python -m py_compile", "node --check", "git status", "git diff", "huggingface-cli download", "huggingface-cli"]
        is_safe = any(command.strip().startswith(prefix) for prefix in SAFE_PREFIXES)
        if not is_safe: return JSONResponse(status_code=403, content={"success": False, "message": "Command not in safe list"})
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=FoveAI_ROOT, timeout=120)
        return {"success": result.returncode == 0, "message": result.stdout if result.returncode == 0 else result.stderr, "exitCode": result.returncode}
    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=504, content={"success": False, "message": "Command timed out"})
    except Exception as e:
        logger.error(f"[CodeAgency] exec failed: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/api/code/git/status")
async def code_git_status(_auth: None = Depends(require_webui_login)):
    try:
        result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=FoveAI_ROOT, timeout=30)
        return {"status": result.stdout, "exitCode": result.returncode}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/code/config")
async def code_config(section: str, key: str, _auth: None = Depends(require_webui_login)):
    try:
        env_path = Path(FoveAI_ROOT) / ".env"
        if not env_path.exists(): return {"value": None}
        content = env_path.read_text(encoding="utf-8")
        pattern = rf"^{re.escape(key)}\s*=\s*(.+)$"
        match = re.search(pattern, content, re.MULTILINE)
        if match: return {"value": match.group(1).strip().strip('"').strip("'")}
        return {"value": None}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/code/deadsure/status")
async def code_deadsure_status(_auth: None = Depends(require_webui_login)):
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("http://127.0.0.1:8112/status", timeout=5.0)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        return {"status": "UNAVAILABLE", "error": str(e), "healed_count": 0, "broken_files": {}}
    return {"status": "UNAVAILABLE", "healed_count": 0, "broken_files": {}}




# Catch-all for root-level build assets (vrm, glb, manifest, etc.)
@app.get("/{file_path:path}")
async def serve_static_fallback(file_path: str, request: Request):
    # Only try to serve if it's a file extension we expect
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.vrm', '.glb', '.vrma', '.json', '.js', '.png', '.jpg', '.svg', '.wav', '.mp3', '.ext2', '.bvh', '.fbx']:
        # 1. Try local build folder (Production Mode)
        local_path = os.path.join(XR_DIST, file_path)
        logger.info(f"[Static] Checking local_path: {local_path} (exists: {os.path.exists(local_path)})")
        if os.path.exists(local_path):
            return FileResponse(local_path)
            
        # 2. Try Vite Dev Server (Development Mode)
        # Vite serves the 'public/' folder contents at the root
        query = request.url.query
        query_str = f"?{query}" if query else ""
        url = f"{VITE_URL}/{file_path}{query_str}"
        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    return Response(
                        content=resp.content, 
                        status_code=resp.status_code, 
                        media_type=resp.headers.get("content-type")
                    )
        except Exception as e:
            logger.debug(f"Vite asset proxy failed for {file_path}: {e}")

    # If not a recognized static file, and we are at the root, serve index
    if not file_path or "/" not in file_path:
        return await get_index(request)

    raise HTTPException(status_code=404)





# --- Forge Feature Inventory API ---
@app.post("/api/forge/index")
async def api_forge_index():
    """Index latest Forge discovery report to FEATURE_INVENTORY.md"""
    try:
        import subprocess
        import json as json_lib
        
        # Run the indexer script
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "Scripts" / "index_forge_findings.py"), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Parse output to get counts
        output = result.stdout
        report_name = ""
        total = 0
        worthwhile = 0
        
        for line in output.split('\n'):
            if 'from' in line and '.json' in line:
                report_name = line.split('from')[-1].strip()
            if 'Found' in line and 'meaningful' in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == 'Found':
                        total = int(parts[i+1])
                        worthwhile = int(parts[i+3]) if len(parts) > i+3 else 0
        
        return JSONResponse({
            "success": True,
            "added": worthwhile,
            "total_discovered": total,
            "worthwhile": worthwhile,
            "report_name": report_name
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })
# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT CONFIG ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/environment/config")
async def save_environment_config(request: Request, _auth: None = Depends(require_webui_login)):
    """Saves the spatial environment configuration from the UI."""
    try:
        data = await request.json()
        logger.info(f"[Environment] Received new spatial configuration: {data}")
        # In the future, this can write to a physical JSON file or .env
        return {"success": True, "message": "Environment config saved successfully."}
    except Exception as e:
        logger.error(f"[Environment] Failed to save config: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

# ═══════════════════════════════════════════════════════════════════════════════
# LIBRARIAN INBOX ROUTES 
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/inbox")
async def get_inbox(_auth: None = Depends(require_webui_login)):
    """Fetch all messages from the Librarian Inbox."""
    try:
        inbox_path = os.path.join(FoveAI_ROOT, "inbox.md")
        if not os.path.exists(inbox_path):
            return {"messages": []}
            
        with open(inbox_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
        if not content:
            return {"messages": []}
            
        # Very simple parser: split by lines, filter empty
        messages = [m.strip() for m in content.split("\n") if m.strip()]
        return {"messages": messages}
    except Exception as e:
        logger.error(f"[Inbox] Failed to read inbox: {e}")
        return {"messages": []}

@app.post("/api/inbox/clear")
async def clear_inbox(_auth: None = Depends(require_webui_login)):
    """Wipe the Librarian Inbox clean."""
    try:
        inbox_path = os.path.join(FoveAI_ROOT, "inbox.md")
        # Just write an empty string
        with open(inbox_path, "w", encoding="utf-8") as f:
            f.write("")
        return {"success": True}
    except Exception as e:
        logger.error(f"[Inbox] Failed to clear inbox: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

# ═══════════════════════════════════════════════════════════════════════════════
# CODE AGENCY ROUTES — Mount /api/code/* endpoints for avatar self-modification
# ═══════════════════════════════════════════════════════════════════════════════
# code_agency_routes.py defines routes on the same FastAPI `app` object.
# We exec() it here so all /api/code/ls, /api/code/read, /api/code/search,
# /api/code/write, /api/code/edit, /api/code/exec, /api/code/git/status,
# and /api/code/config endpoints are registered at startup.
try:
    _ca_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "code_agency_routes.py")
    with open(_ca_path, "r", encoding="utf-8") as _ca_f:
        _ca_code = _ca_f.read()
    # Strip the shebang/docstring header and exec the route definitions
    # The routes use `app`, `FoveAI_ROOT`, `logger`, `require_webui_login`, etc.
    # which are all already defined in this module's scope.
    exec(compile(_ca_code, _ca_path, "exec"), globals())
    logger.info("[CodeAgency] Routes mounted successfully")
except Exception as _ca_err:
    logger.warning(f"[CodeAgency] Failed to mount routes: {_ca_err}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=_WEBUI_PORT)
