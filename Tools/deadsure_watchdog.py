import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("foveai.deadsure")

# ─── Paths ───────────────────────────────────────────────────────────────────
FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAFE_SAVES_DIR = os.path.join(FoveAI_ROOT, ".SafeSaves")
STATE_FILE = os.path.join(SAFE_SAVES_DIR, "watchdog_state.json")
HEARTBEAT_LOG = os.path.join(SAFE_SAVES_DIR, "watchdog_heartbeat.log")
os.makedirs(SAFE_SAVES_DIR, exist_ok=True)

# ─── Config ───────────────────────────────────────────────────────────────────
DEADSURE_PORT = int(os.environ.get("FoveAI_DEADSURE_PORT", "8112"))
FoveAI_SOLVER_URL = os.environ.get(
    "FoveAI_SOLVER_URL", "http://127.0.0.1:8113"
)  # optional solver sidecar

WATCH_DIRS = [
    os.path.join(FoveAI_ROOT, "Backend"),
    os.path.join(FoveAI_ROOT, "Forge"),
    os.path.join(FoveAI_ROOT, "Frontend", "XR_Vessel", "src"),
    os.path.join(FoveAI_ROOT, "Tools"),
]
WATCH_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}
IGNORE_SUBSTRINGS = {"__pycache__", ".venv", ".git", "node_modules", ".SafeSaves"}

# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(title="DeadSure Watchdog", version="2.0.0")


# ─── Watchdog Core ────────────────────────────────────────────────────────────
class DeadSureWatchdog:
    def __init__(self):
        self.file_mtimes: dict[str, float] = {}
        self.broken_files: dict[str, str] = {}  # filepath -> error message
        self.reverted_count = 0
        self.expected_reversions: set[str] = set()
        self.running = False
        self._load_state()

    # ── State Persistence ──────────────────────────────────────────────────

    def _load_state(self):
        """Restore mtime cache from disk so restarts don't trigger false-positives."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.file_mtimes = data.get("file_mtimes", {})
                self.reverted_count = data.get("reverted_count", 0)
                logger.info(
                    f"🔄 [STATE] Loaded {len(self.file_mtimes)} cached file records from disk."
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ [STATE] Could not load state file: {e}. Starting fresh."
                )

    def _save_state(self):
        """Persist mtime cache atomically (write-then-rename)."""
        tmp = STATE_FILE + ".tmp"
        try:
            payload = {
                "file_mtimes": self.file_mtimes,
                "reverted_count": self.reverted_count,
                "saved_at": time.time(),
            }
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            logger.error(f"⚠️ [STATE] Failed to persist watchdog state: {e}")
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    def _write_heartbeat(self, status: str):
        """Append a one-line JSON heartbeat for the PS1 supervisor to tail."""
        try:
            entry = json.dumps(
                {
                    "ts": time.time(),
                    "status": status,
                    "broken": len(self.broken_files),
                    "healed": self.reverted_count,
                }
            )
            with open(HEARTBEAT_LOG, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass  # Heartbeat failure must never kill the loop

    # ── File Utilities ──────────────────────────────────────────────────────

    def get_rel_path(self, filepath: str) -> str:
        return os.path.relpath(filepath, FoveAI_ROOT)

    def get_backup_path(self, filepath: str) -> str:
        rel = self.get_rel_path(filepath)
        return os.path.join(SAFE_SAVES_DIR, rel)

    def backup_file(self, filepath: str) -> bool:
        try:
            backup = self.get_backup_path(filepath)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(filepath, backup)
            logger.info(
                f"💾 [BACKUP] Saved known-good copy of {self.get_rel_path(filepath)}"
            )
            return True
        except Exception as e:
            logger.error(f"⚠️ [BACKUP FAILED] Could not backup {filepath}: {e}")
            return False

    def revert_file(self, filepath: str, error_msg: str) -> bool:
        logger.info(
            f"🛡️ [WATCHDOG DISABLED] Auto-revert triggered for {self.get_rel_path(filepath)} but auto-revert is DEACTIVATED by user preference."
        )
        return True

    # ── LLM Escalation Hook ────────────────────────────────────────────────

    async def _escalate_to_solver(self, filepath: str, error_msg: str):
        """
        When no backup exists, try to call the foveai-solver sidecar (if running)
        so it can attempt an LLM-assisted repair.  Failure here is non-fatal.
        """
        try:
            import urllib.request

            payload = json.dumps(
                {
                    "file": self.get_rel_path(filepath),
                    "error": error_msg,
                    "source": "deadsure_watchdog",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{FoveAI_SOLVER_URL}/repair",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                logger.info(f"🤖 [LLM ESCALATION] Solver responded: {body[:200]}")
        except Exception as e:
            logger.warning(f"⚠️ [LLM ESCALATION] Solver unreachable or failed: {e}")

    # ── Compilation Gates ──────────────────────────────────────────────────

    async def compile_python(self, filepath: str) -> str | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "py_compile",
                filepath,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode != 0:
                return stderr.decode("utf-8", errors="replace")
            return None
        except asyncio.TimeoutError:
            return "Python compile check timed out (15s limit)"
        except Exception as e:
            return f"Compiler execution failed: {e!s}"

    async def compile_typescript(self) -> str | None:
        cwd = os.path.join(FoveAI_ROOT, "Frontend", "XR_Vessel")
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx.cmd",
                "tsc",
                "--noEmit",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0:
                return (
                    stdout.decode("utf-8", errors="replace")
                    + "\n"
                    + stderr.decode("utf-8", errors="replace")
                )
            return None
        except asyncio.TimeoutError:
            return "TypeScript compilation check timed out (30s limit)"
        except Exception as e:
            return f"TypeScript compile execution failed: {e!s}"

    async def check_file(self, filepath: str):
        ext = os.path.splitext(filepath)[1].lower()
        rel = self.get_rel_path(filepath)
        logger.info(f"🔎 [CHECKING] Gate validation for {rel}...")

        err: str | None = None
        if ext == ".py":
            err = await self.compile_python(filepath)
        elif ext in {".ts", ".tsx"}:
            err = await self.compile_typescript()
        # .js/.jsx — syntax check via node --check
        elif ext in {".js", ".jsx"}:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "node",
                    "--check",
                    filepath,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
                if proc.returncode != 0:
                    err = stderr.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                err = "node --check timed out (10s)"
            except Exception as e:
                err = f"node --check failed: {e}"

        if err:
            self.broken_files[filepath] = err
            self.revert_file(filepath, err)
        else:
            self.broken_files.pop(filepath, None)
            logger.info(f"🟢 [COMPILED CLEAN] {rel} passed compile gates.")
            self.backup_file(filepath)

    # ── Workspace Scanner ──────────────────────────────────────────────────

    def scan_workspace(self) -> list[str]:
        modified_files = []
        for watch_dir in WATCH_DIRS:
            if not os.path.exists(watch_dir):
                continue
            for root, dirs, files in os.walk(watch_dir):
                dirs[:] = [
                    d
                    for d in dirs
                    if not any(
                        ign in os.path.join(root, d) for ign in IGNORE_SUBSTRINGS
                    )
                ]
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in WATCH_EXTENSIONS:
                        continue

                    filepath = os.path.abspath(os.path.join(root, file))
                    try:
                        mtime = os.path.getmtime(filepath)
                    except OSError:
                        continue

                    old_mtime = self.file_mtimes.get(filepath)
                    if old_mtime is None:
                        self.file_mtimes[filepath] = mtime
                        if not os.path.exists(self.get_backup_path(filepath)):
                            self.backup_file(filepath)
                    elif mtime > old_mtime:
                        self.file_mtimes[filepath] = mtime
                        if filepath in self.expected_reversions:
                            self.expected_reversions.discard(filepath)
                            logger.info(
                                f"🛡️ [BYPASS] Ignored expected revert change in {self.get_rel_path(filepath)}"
                            )
                        else:
                            modified_files.append(filepath)
        return modified_files

    # ── Main Watch Loop ────────────────────────────────────────────────────

    async def watch_loop(self):
        self.running = True
        logger.info(
            "🛡️ [DEADSURE WATCHDOG ACTIVE] Initializing file watcher and populating cache..."
        )
        self.scan_workspace()
        self._save_state()

        back_off = 2.0  # seconds, resets on success
        MAX_BACK_OFF = 30.0

        while self.running:
            try:
                modified = self.scan_workspace()
                if modified:
                    self._save_state()  # persist updated mtimes before checking
                for filepath in modified:
                    await asyncio.sleep(1.5)  # debounce: let editor finish writing
                    await self.check_file(filepath)

                self._write_heartbeat("ok" if not self.broken_files else "degraded")
                back_off = 2.0  # reset on success
                await asyncio.sleep(2.0)

            except asyncio.CancelledError:
                logger.info("🛑 [WATCHDOG] Loop cancelled cleanly.")
                break
            except Exception as e:
                logger.error(
                    f"💥 [WATCHDOG ERROR] Unexpected crash in watch loop: {e}. Back-off {back_off}s before resume."
                )
                self._write_heartbeat(f"error:{e}")
                await asyncio.sleep(back_off)
                back_off = min(back_off * 2, MAX_BACK_OFF)


watchdog = DeadSureWatchdog()


# ─── API Endpoints ────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(watchdog.watch_loop())


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "deadsure-watchdog",
        "version": "2.0.0",
        "running": watchdog.running,
        "port": DEADSURE_PORT,
    }


@app.get("/status")
async def status():
    is_stable = len(watchdog.broken_files) == 0
    return {
        "status": "SECURE" if is_stable else "COMPILATION_FAIL",
        "healed_count": watchdog.reverted_count,
        "watched_files": len(watchdog.file_mtimes),
        "broken_files": {
            watchdog.get_rel_path(k): v[:300] for k, v in watchdog.broken_files.items()
        },
    }


@app.post("/restore")
async def restore_file(filepath: str, reason: str = "Manual restoration requested"):
    """
    Manually restore a file from its last known-good backup.
    Accepts an optional `reason` field for audit logging (used by LLM solver).
    """
    abs_path = os.path.abspath(os.path.join(FoveAI_ROOT, filepath))
    if not abs_path.startswith(FoveAI_ROOT):
        return JSONResponse(
            status_code=400,
            content={"error": "Access denied — path outside FoveAI_ROOT"},
        )
    success = watchdog.revert_file(abs_path, reason)
    return {"success": success, "file": filepath, "reason": reason}


@app.post("/repair")
async def repair_hook(request: Request):
    """
    Receives LLM-proposed file edits from foveai-solver sidecar.
    Applies them only if the filepath is inside FoveAI_ROOT.
    """
    try:
        body = await request.json()
        edits = body.get("fileEdits", [])
        applied = []
        for edit in edits:
            rel = edit.get("filePath", "")
            content = edit.get("content", "")
            abs_path = os.path.abspath(os.path.join(FoveAI_ROOT, rel))
            if not abs_path.startswith(FoveAI_ROOT):
                logger.warning(f"⛔ [REPAIR] Rejected path traversal attempt: {rel}")
                continue
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"🔧 [REPAIR] Applied LLM fix to {rel}")
            applied.append(rel)
        return {"applied": applied}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="deadsure_watchdog",
        description="DeadSure Watchdog v2 — Compile-gate file guardian for the FoveAI Diamond Concordia.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEADSURE_PORT,
        help=f"HTTP port (default: {DEADSURE_PORT})",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
