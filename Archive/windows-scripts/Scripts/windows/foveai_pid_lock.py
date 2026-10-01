"""
FoveAI PID Lock — prevents duplicate service processes.

Usage:
    from foveai_pid_lock import acquire_lock, release_lock

    if not acquire_lock("kokoro_tts"):
        print("Another Kokoro TTS instance is already running. Exiting.")
        sys.exit(0)

    # ... service code ...

    release_lock("kokoro_tts")  # optional, auto-released on exit

Locks are stored in %TEMP%/foveai_locks/<name>.pid
Stale locks (PID no longer alive) are automatically reclaimed.
"""

import os
from pathlib import Path

import psutil

LOCK_DIR = Path(os.environ.get("TEMP", "/tmp")) / "foveai_locks"


def _lock_path(name: str) -> Path:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    return LOCK_DIR / f"{name}.pid"


def _is_pid_alive(pid: int) -> bool:
    try:
        return (
            psutil.pid_exists(pid)
            and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        )
    except Exception:
        return False


def _pid_matches_name(pid: int, expected: str) -> bool:
    """Check if the PID's command line contains the expected keyword."""
    try:
        p = psutil.Process(pid)
        cmdline = " ".join(p.cmdline()).lower()
        return expected.lower() in cmdline
    except Exception:
        return False


def acquire_lock(name: str, check_keyword: str | None = None) -> bool:
    """Try to acquire a named lock. Returns True if acquired, False if another instance holds it."""
    path = _lock_path(name)
    keyword = check_keyword or name

    # Check for existing lock
    if path.exists():
        try:
            old_pid = int(path.read_text().strip())
            if _is_pid_alive(old_pid) and _pid_matches_name(old_pid, keyword):
                # Another live instance is running
                return False
            # Stale lock — reclaim it
        except (ValueError, OSError):
            pass  # Corrupt lock file — reclaim

    # Write our PID
    try:
        path.write_text(str(os.getpid()))
        return True
    except OSError:
        return False


def release_lock(name: str) -> None:
    """Release a named lock."""
    path = _lock_path(name)
    try:
        if path.exists():
            pid = path.read_text().strip()
            if pid == str(os.getpid()):
                path.unlink()
    except OSError:
        pass


def check_lock(name: str, check_keyword: str | None = None) -> int | None:
    """Check if a named service is running. Returns the PID if running, None otherwise."""
    path = _lock_path(name)
    keyword = check_keyword or name
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
        if _is_pid_alive(pid) and _pid_matches_name(pid, keyword):
            return pid
    except (ValueError, OSError):
        pass
    return None
