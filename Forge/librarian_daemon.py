"""
Continuous Librarian Daemon (librarian_daemon.py)
Monitors terminal command streams, runs periodic codebase mapping audits,
and acts as the ACTIVE LOCAL GUARDIAN — first responder for system errors.

Guardian role:
  1. Health-check system every 30s (duplicate processes, memory hogs, port conflicts)
  2. System memory pressure detection — proactive cleansing BEFORE freeze
  3. Stutter detection — timing watchdog catches system choking
  4. Freeze-cause rapport — analyzes what happened before a hard reset
  5. Check Knowledge Base for known fixes → apply instantly (free, zero latency)
  6. Escalate to foveai-solver (HTTP :8113) only when KB can't handle it
  7. Log all actions to ~/.foveai/guardian.log
"""

import asyncio
import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from mesh_bus import mesh_bus

logger = logging.getLogger("forge.librarian_daemon")

# Root directory
REPO_ROOT = Path(os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent))

# ─── Guardian Constants ─────────────────────────────────────────────────────────
GUARDIAN_LOG = Path(os.path.expanduser("~/.foveai/guardian.log"))
KB_PATH = Path(os.path.expanduser("~/.foveai/solutions.json"))
SOLVER_URL = "http://127.0.0.1:8113/solve/apply"
HEALTH_INTERVAL = 30  # seconds between health checks
MEMORY_WARN_MB = 8000  # warn if any process exceeds this
MEMORY_CRITICAL_MB = 12000  # kill if any process exceeds this
DUPLICATE_THRESHOLD = 3  # warn if more than N copies of same process

# System memory pressure thresholds (total RAM %)
SYSTEM_RAM_WARN_PCT = 85  # warn + start logging pressure
SYSTEM_RAM_CRITICAL_PCT = 92  # proactive cleansing — kill biggest offenders
SYSTEM_RAM_EMERGENCY_PCT = 97  # emergency — kill ALL non-essential processes

# Stutter detection
STUTTER_THRESHOLD_MULTIPLIER = (
    2.5  # if loop takes >2.5x HEALTH_INTERVAL, system is stuttering
)
STUTTER_CONSECUTIVE_THRESHOLD = 3  # 3 consecutive stutters = emergency cleanse

# Services we expect to be running (port → name)
EXPECTED_SERVICES = {
    8000: "Soul",
    8002: "Memory",
    8003: "Creative",
    8009: "Cognee-KG",
    8080: "WebUI",
    8113: "Lumax-Solver",
}

# Processes that compete for GPU — only ONE should run at a time
GPU_COMPETITORS = [
    "llama-server.exe",
    "lm studio.exe",
    "ollama.exe",
    "koboldcpp.exe",
    "unsloth",
    "python.*unsloth",
]

# Processes that are safe to kill in emergency (non-Windows-critical)
EMERGENCY_KILL_LIST = [
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "discord.exe",
    "slack.exe",
    "teams.exe",
    "spotify.exe",
    "code.exe",  # VS Code — user can reopen
    "lm studio.exe",
    "ollama.exe",
    "llama-server.exe",
    "koboldcpp.exe",
    "python.exe",
    "python3.exe",
]


# ─── Guardian Logging ──────────────────────────────────────────────────────────
def guardian_log(level: str, message: str, details: dict = None):
    """Write a structured log entry to the guardian log."""
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "message": message,
    }
    if details:
        entry["details"] = details
    try:
        GUARDIAN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(GUARDIAN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    if level == "ERROR":
        logger.error(f"🛡️ [Guardian] {message}")
    elif level == "WARN":
        logger.warning(f"🛡️ [Guardian] {message}")
    else:
        logger.info(f"🛡️ [Guardian] {message}")


# ─── System Health Checks ──────────────────────────────────────────────────────
def get_process_list():
    """Get a list of running processes with memory info. Windows-native."""
    procs = []
    try:
        # tasklist CSV: ImageName,PID,SessionName,Session#,MemUsage
        output = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"], encoding="utf-8", errors="ignore"
        )
        for line in output.strip().split("\n"):
            parts = line.replace('"', "").split(",")
            if len(parts) >= 5:
                name = parts[0].strip()
                pid = parts[1].strip()
                mem_str = parts[4].strip().replace(" K", "").replace(".", "")
                try:
                    mem_kb = int(mem_str.replace(",", ""))
                except ValueError:
                    mem_kb = 0
                procs.append(
                    {
                        "name": name,
                        "pid": pid,
                        "mem_mb": round(mem_kb / 1024, 1),
                    }
                )
    except Exception as e:
        guardian_log("ERROR", f"Failed to get process list: {e}")
    return procs


def check_port(port: int) -> bool:
    """Check if a port is in use. Returns True if something is listening."""
    try:
        output = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"], encoding="utf-8", errors="ignore"
        )
        for line in output.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                return True
    except Exception:
        pass
    return False


def check_health() -> list:
    """
    Run all health checks. Returns a list of Issue dicts:
    { "type": str, "severity": "warn"|"critical", "message": str, "auto_fix": str|None }
    """
    issues = []
    procs = get_process_list()
    if not procs:
        return issues

    # 1. Duplicate Python services
    python_procs = [
        p for p in procs if p["name"].lower() in ("python.exe", "python3.exe", "python")
    ]
    if len(python_procs) > DUPLICATE_THRESHOLD:
        total_mem = sum(p["mem_mb"] for p in python_procs)
        issues.append(
            {
                "type": "duplicate_python",
                "severity": "critical" if total_mem > MEMORY_CRITICAL_MB else "warn",
                "message": f"{len(python_procs)} Python processes using {total_mem:.0f}MB RAM — possible duplicate services",
                "auto_fix": "kill_duplicate_python",
                "details": {"count": len(python_procs), "total_mem_mb": total_mem},
            }
        )

    # 2. Memory hogs
    for p in procs:
        if p["mem_mb"] > MEMORY_CRITICAL_MB:
            issues.append(
                {
                    "type": "memory_critical",
                    "severity": "critical",
                    "message": f"{p['name']} (PID {p['pid']}) using {p['mem_mb']:.0f}MB — exceeds critical threshold",
                    "auto_fix": "kill_process",
                    "details": {
                        "name": p["name"],
                        "pid": p["pid"],
                        "mem_mb": p["mem_mb"],
                    },
                }
            )
        elif p["mem_mb"] > MEMORY_WARN_MB:
            issues.append(
                {
                    "type": "memory_warn",
                    "severity": "warn",
                    "message": f"{p['name']} (PID {p['pid']}) using {p['mem_mb']:.0f}MB — high memory usage",
                    "auto_fix": None,
                    "details": {
                        "name": p["name"],
                        "pid": p["pid"],
                        "mem_mb": p["mem_mb"],
                    },
                }
            )

    # 3. GPU competitor conflicts (multiple LLM runtimes)
    gpu_procs = []
    for p in procs:
        name_lower = p["name"].lower()
        for competitor in GPU_COMPETITORS:
            import re

            if re.search(competitor, name_lower):
                gpu_procs.append(p)
                break
    if len(gpu_procs) > 1:
        names = [p["name"] for p in gpu_procs]
        issues.append(
            {
                "type": "gpu_conflict",
                "severity": "critical",
                "message": f"Multiple GPU competitors running: {', '.join(names)} — VRAM contention",
                "auto_fix": "kill_gpu_competitors",
                "details": {
                    "processes": [
                        {"name": p["name"], "pid": p["pid"]} for p in gpu_procs
                    ]
                },
            }
        )

    # 4. Expected services down
    for port, name in EXPECTED_SERVICES.items():
        if not check_port(port):
            issues.append(
                {
                    "type": "service_down",
                    "severity": "warn",
                    "message": f"Expected service '{name}' not listening on port {port}",
                    "auto_fix": None,  # foveai-solver handles service restarts
                    "details": {"service": name, "port": port},
                }
            )

    return issues


# ─── System Memory Pressure Detection ───────────────────────────────────────────
def get_system_ram() -> dict:
    """
    Get total system RAM usage via Windows wmic.
    Returns { total_mb, free_mb, used_mb, used_pct } or None on failure.
    """
    try:
        # Get total visible memory
        output = subprocess.check_output(
            [
                "wmic",
                "OS",
                "get",
                "TotalVisibleMemorySize,FreePhysicalMemory",
                "/Value",
            ],
            encoding="utf-8",
            errors="ignore",
        )
        total_kb = 0
        free_kb = 0
        for line in output.strip().split("\n"):
            line = line.strip()
            if line.startswith("TotalVisibleMemorySize="):
                total_kb = int(line.split("=")[1])
            elif line.startswith("FreePhysicalMemory="):
                free_kb = int(line.split("=")[1])

        if total_kb > 0:
            used_kb = total_kb - free_kb
            return {
                "total_mb": round(total_kb / 1024, 1),
                "free_mb": round(free_kb / 1024, 1),
                "used_mb": round(used_kb / 1024, 1),
                "used_pct": round((used_kb / total_kb) * 100, 1),
            }
    except Exception as e:
        guardian_log("WARN", f"Failed to get system RAM: {e}")
    return None


def check_memory_pressure() -> dict | None:
    """
    Check system-wide memory pressure.
    Returns { level, ram, top_offenders } if pressure detected, None if healthy.
    """
    ram = get_system_ram()
    if not ram:
        return None

    used_pct = ram["used_pct"]

    if used_pct < SYSTEM_RAM_WARN_PCT:
        return None  # Healthy

    # Determine pressure level
    if used_pct >= SYSTEM_RAM_EMERGENCY_PCT:
        level = "emergency"
    elif used_pct >= SYSTEM_RAM_CRITICAL_PCT:
        level = "critical"
    else:
        level = "warn"

    # Get top memory offenders
    procs = get_process_list()
    top_offenders = sorted(procs, key=lambda p: p["mem_mb"], reverse=True)[:5]

    return {
        "level": level,
        "ram": ram,
        "top_offenders": top_offenders,
    }


def emergency_cleanse(level: str, top_offenders: list) -> int:
    """
    Kill non-essential processes to free memory.
    - 'warn': just log, no action
    - 'critical': kill top 3 non-essential offenders
    - 'emergency': kill ALL non-essential processes
    Returns number of processes killed.
    """
    killed = 0

    if level == "warn":
        guardian_log(
            "WARN",
            f"System RAM at {get_system_ram()['used_pct'] if get_system_ram() else '?'}% — "
            f"top offenders: {', '.join(f'{p['name']}({p['mem_mb']:.0f}MB)' for p in top_offenders[:3])}",
        )
        return 0

    if level == "critical":
        # Kill top 3 non-essential offenders
        targets = []
        for p in top_offenders:
            name_lower = p["name"].lower()
            for kill_pattern in EMERGENCY_KILL_LIST:
                import re

                if re.search(
                    kill_pattern.replace(".exe", "").replace(".", "\\."), name_lower
                ):
                    targets.append(p)
                    break
            if len(targets) >= 3:
                break

        guardian_log(
            "ERROR",
            f"🚨 CRITICAL memory pressure ({get_system_ram()['used_pct'] if get_system_ram() else '?'}%) — "
            f"killing top offenders: {[t['name'] for t in targets]}",
        )

    elif level == "emergency":
        # Kill ALL non-essential processes
        procs = get_process_list()
        targets = []
        for p in procs:
            name_lower = p["name"].lower()
            for kill_pattern in EMERGENCY_KILL_LIST:
                import re

                if re.search(
                    kill_pattern.replace(".exe", "").replace(".", "\\."), name_lower
                ):
                    targets.append(p)
                    break

        guardian_log(
            "ERROR",
            f"🆘 EMERGENCY memory pressure ({get_system_ram()['used_pct'] if get_system_ram() else '?'}%) — "
            f"killing ALL non-essential processes ({len(targets)} targets)",
        )

    for p in targets:
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", p["pid"]], capture_output=True, timeout=10
            )
            guardian_log(
                "INFO",
                f"Emergency cleanse: killed {p['name']} (PID {p['pid']}, {p['mem_mb']}MB)",
            )
            killed += 1
        except Exception as e:
            guardian_log("ERROR", f"Emergency cleanse failed for PID {p['pid']}: {e}")

    return killed


# ─── Stutter Detection ─────────────────────────────────────────────────────────
_stutter_state = {
    "consecutive_stutters": 0,
    "last_loop_start": 0,
    "last_loop_duration": 0,
    "max_loop_duration": 0,
}


def detect_stutter(loop_start: float, loop_end: float) -> str | None:
    """
    Detect if the guardian loop is stuttering (taking too long).
    Returns 'stutter', 'severe_stutter', or None.
    """
    duration = loop_end - loop_start
    _stutter_state["last_loop_duration"] = duration
    _stutter_state["max_loop_duration"] = max(
        _stutter_state["max_loop_duration"], duration
    )

    threshold = HEALTH_INTERVAL * STUTTER_THRESHOLD_MULTIPLIER

    if duration > threshold * 2:
        _stutter_state["consecutive_stutters"] += 1
        return "severe_stutter"
    elif duration > threshold:
        _stutter_state["consecutive_stutters"] += 1
        return "stutter"
    else:
        _stutter_state["consecutive_stutters"] = max(
            0, _stutter_state["consecutive_stutters"] - 1
        )
        return None


# ─── Freeze-Cause Rapport ──────────────────────────────────────────────────────
def generate_freeze_rapport() -> dict:
    """
    On startup, check Windows Event Log for unexpected shutdowns
    and analyze what was happening before the crash.
    Returns a rapport dict with findings.
    """
    rapport = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "unexpected_shutdowns": [],
        "last_guardian_state": None,
        "suspected_cause": "unknown",
    }

    # 1. Check Windows Event Log for unexpected shutdowns (Event ID 6008)
    try:
        output = subprocess.check_output(
            [
                "wevtutil",
                "qe",
                "System",
                "/q:*[System[EventID=6008]]",
                "/c:3",
                "/rd:true",
                "/f:text",
            ],
            encoding="utf-8",
            errors="ignore",
            timeout=15,
        )
        # Parse dates from the output
        import re

        dates = re.findall(r"Date:\s*(.+)", output)
        for d in dates[:3]:
            rapport["unexpected_shutdowns"].append(d.strip())
    except Exception:
        pass  # wevtutil may not be available or timeout

    # 2. Check last guardian log entries before shutdown
    if GUARDIAN_LOG.exists():
        try:
            lines = []
            with open(GUARDIAN_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    lines.append(line.strip())
            # Get last 20 entries
            last_entries = []
            for line in lines[-20:]:
                try:
                    last_entries.append(json.loads(line))
                except Exception:
                    pass
            if last_entries:
                rapport["last_guardian_state"] = last_entries

                # Analyze for patterns
                error_count = sum(1 for e in last_entries if e.get("level") == "ERROR")
                warn_count = sum(1 for e in last_entries if e.get("level") == "WARN")
                memory_issues = sum(
                    1
                    for e in last_entries
                    if "memory" in e.get("message", "").lower()
                    or "RAM" in e.get("message", "")
                )

                if error_count >= 3:
                    rapport["suspected_cause"] = (
                        f"Multiple errors ({error_count}) before shutdown"
                    )
                elif memory_issues >= 2:
                    rapport["suspected_cause"] = (
                        f"Memory pressure ({memory_issues} memory warnings)"
                    )
                elif warn_count >= 5:
                    rapport["suspected_cause"] = f"Cascading warnings ({warn_count})"
                else:
                    rapport["suspected_cause"] = (
                        "No clear pattern — possible external cause or GPU hang"
                    )
        except Exception:
            pass

    # 3. Check current system state
    ram = get_system_ram()
    if ram:
        rapport["current_ram"] = ram

    procs = get_process_list()
    python_count = sum(
        1 for p in procs if p["name"].lower() in ("python.exe", "python3.exe", "python")
    )
    gpu_count = sum(
        1
        for p in procs
        if any(
            c in p["name"].lower()
            for c in ["llama", "ollama", "lm studio", "kobold", "unsloth"]
        )
    )
    rapport["current_state"] = {
        "total_processes": len(procs),
        "python_processes": python_count,
        "gpu_processes": gpu_count,
        "total_process_mem_mb": round(sum(p["mem_mb"] for p in procs), 1),
    }

    return rapport


def print_freeze_rapport(rapport: dict):
    """Print a human-readable freeze rapport to the log."""
    guardian_log("INFO", "=" * 60)
    guardian_log("INFO", "🔍 FREEZE-CAUSE RAPPORT")
    guardian_log("INFO", "=" * 60)

    if rapport["unexpected_shutdowns"]:
        guardian_log(
            "INFO",
            f"Recent unexpected shutdowns: {len(rapport['unexpected_shutdowns'])}",
        )
        for d in rapport["unexpected_shutdowns"][:3]:
            guardian_log("INFO", f"  • {d}")

    guardian_log("INFO", f"Suspected cause: {rapport['suspected_cause']}")

    if rapport.get("current_ram"):
        r = rapport["current_ram"]
        guardian_log(
            "INFO",
            f"Current RAM: {r['used_mb']:.0f}MB / {r['total_mb']:.0f}MB ({r['used_pct']}%)",
        )

    if rapport.get("current_state"):
        s = rapport["current_state"]
        guardian_log(
            "INFO",
            f"Current state: {s['total_processes']} processes, "
            f"{s['python_processes']} Python, {s['gpu_processes']} GPU, "
            f"{s['total_process_mem_mb']:.0f}MB total",
        )

    if rapport.get("last_guardian_state"):
        guardian_log(
            "INFO",
            f"Last guardian entries before shutdown ({len(rapport['last_guardian_state'])} entries):",
        )
        for entry in rapport["last_guardian_state"][-5:]:
            guardian_log(
                "INFO",
                f"  [{entry.get('level', '?')}] {entry.get('message', '')[:120]}",
            )

    guardian_log("INFO", "=" * 60)


# ─── Knowledge Base Lookup ─────────────────────────────────────────────────────
def query_kb(error_text: str) -> dict | None:
    """
    Check the local knowledge base for a known fix.
    Returns the solution dict if found, None otherwise.
    """
    if not KB_PATH.exists():
        return None
    try:
        data = json.loads(KB_PATH.read_text(encoding="utf-8"))
        solutions = data.get("solutions", [])
        if not solutions:
            return None

        err_lower = error_text.lower()
        best = None
        best_score = 0

        for sol in solutions:
            pattern = sol.get("pattern", "").lower()
            if not pattern:
                continue
            # Exact substring match = highest confidence
            if pattern in err_lower:
                score = 1.0
            else:
                # Token overlap
                pat_tokens = set(pattern.split())
                err_tokens = set(err_lower.split())
                if not pat_tokens:
                    continue
                hits = sum(1 for t in pat_tokens if t in err_tokens)
                score = hits / len(pat_tokens)

            if score > best_score and score >= 0.80:
                best_score = score
                best = sol

        if best:
            guardian_log(
                "INFO",
                f"KB match found (score: {best_score:.0%}): {best.get('description', '')[:100]}",
            )
            return best
    except Exception as e:
        guardian_log("WARN", f"KB lookup failed: {e}")
    return None


# ─── Auto-Fix Actions ──────────────────────────────────────────────────────────
def apply_auto_fix(issue: dict) -> bool:
    """
    Apply a simple, safe auto-fix for known issue types.
    Returns True if the fix was applied successfully.
    """
    fix_type = issue.get("auto_fix")
    if not fix_type:
        return False

    if fix_type == "kill_duplicate_python":
        # Kill all but the newest Python processes (keep the most recently started ones)
        try:
            procs = get_process_list()
            python_procs = [
                p
                for p in procs
                if p["name"].lower() in ("python.exe", "python3.exe", "python")
            ]
            if len(python_procs) <= DUPLICATE_THRESHOLD:
                return False
            # Sort by PID (higher PID = newer on Windows) — keep the last DUPLICATE_THRESHOLD
            python_procs.sort(key=lambda p: int(p["pid"]))
            to_kill = python_procs[:-DUPLICATE_THRESHOLD]
            for p in to_kill:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", p["pid"]],
                        capture_output=True,
                        timeout=10,
                    )
                    guardian_log(
                        "INFO",
                        f"Killed duplicate Python process: {p['name']} (PID {p['pid']}, {p['mem_mb']}MB)",
                    )
                except Exception as e:
                    guardian_log("ERROR", f"Failed to kill PID {p['pid']}: {e}")
            return True
        except Exception as e:
            guardian_log("ERROR", f"Auto-fix kill_duplicate_python failed: {e}")
            return False

    elif fix_type == "kill_process":
        pid = issue.get("details", {}).get("pid")
        if pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                )
                guardian_log("INFO", f"Killed memory hog: PID {pid}")
                return True
            except Exception as e:
                guardian_log("ERROR", f"Failed to kill PID {pid}: {e}")
        return False

    elif fix_type == "kill_gpu_competitors":
        # Kill all GPU competitors except the one using the most memory (assumed primary)
        details = issue.get("details", {}).get("processes", [])
        if len(details) <= 1:
            return False
        # Keep the one with highest memory usage
        details.sort(
            key=lambda p: p.get("mem_mb", 0) if isinstance(p, dict) else 0, reverse=True
        )
        to_kill = details[1:]  # kill all except the biggest
        for p in to_kill:
            pid = p.get("pid") if isinstance(p, dict) else None
            name = p.get("name", "unknown") if isinstance(p, dict) else str(p)
            if pid:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        timeout=10,
                    )
                    guardian_log("INFO", f"Killed GPU competitor: {name} (PID {pid})")
                except Exception as e:
                    guardian_log("ERROR", f"Failed to kill GPU competitor {name}: {e}")
        return True

    return False


# ─── Escalation to Lumax-Solver ────────────────────────────────────────────────
def escalate_to_solver(error_text: str, issues: list = None) -> bool:
    """
    POST the error to foveai-solver's /solve/apply endpoint.
    Returns True if the solver accepted the request.
    """
    payload = json.dumps(
        {
            "error": error_text,
            "source": "librarian_guardian",
            "issues": issues or [],
        }
    ).encode("utf-8")

    try:
        req = urllib.request.Request(
            SOLVER_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                guardian_log("INFO", "Escalated to foveai-solver — accepted")
                return True
            else:
                guardian_log("WARN", f"Escalation to solver returned {resp.status}")
                return False
    except urllib.error.URLError as e:
        guardian_log(
            "WARN", f"Lumax-solver not reachable on :8113 — is it running? ({e.reason})"
        )
        return False
    except Exception as e:
        guardian_log("ERROR", f"Escalation failed: {e}")
        return False


# ─── Active Guardian Loop ──────────────────────────────────────────────────────
async def guardian_loop():
    """
    The active guardian — runs every HEALTH_INTERVAL seconds.
    0. System memory pressure — proactive cleansing BEFORE freeze
    1. Process health checks (duplicates, memory hogs, GPU conflicts, services)
    2. Stutter detection — timing watchdog on the loop itself
    3. For each issue: try KB → try auto-fix → escalate to solver
    """
    await asyncio.sleep(10)  # Let other daemons start first
    guardian_log("INFO", "🛡️ Active Guardian armed — monitoring system health every 30s")
    guardian_log(
        "INFO",
        f"   RAM thresholds: warn={SYSTEM_RAM_WARN_PCT}% critical={SYSTEM_RAM_CRITICAL_PCT}% emergency={SYSTEM_RAM_EMERGENCY_PCT}%",
    )
    guardian_log(
        "INFO",
        f"   Stutter detection: {STUTTER_THRESHOLD_MULTIPLIER}x interval, {STUTTER_CONSECUTIVE_THRESHOLD} consecutive = emergency",
    )

    while True:
        loop_start = time.time()
        try:
            # ── Priority 0: System Memory Pressure (BEFORE process checks) ──
            pressure = check_memory_pressure()
            if pressure:
                level = pressure["level"]
                ram = pressure["ram"]
                top = pressure["top_offenders"]

                guardian_log(
                    "ERROR" if level in ("critical", "emergency") else "WARN",
                    f"System RAM pressure [{level.upper()}]: {ram['used_pct']}% used "
                    f"({ram['used_mb']:.0f}MB / {ram['total_mb']:.0f}MB)",
                )

                if level in ("critical", "emergency"):
                    killed = emergency_cleanse(level, top)
                    if killed > 0:
                        guardian_log(
                            "INFO",
                            f"Emergency cleanse: killed {killed} process(es) to free memory",
                        )
                        await asyncio.sleep(2)
                        new_ram = get_system_ram()
                        if new_ram:
                            guardian_log(
                                "INFO",
                                f"Post-cleanse RAM: {new_ram['used_pct']}% "
                                f"({new_ram['free_mb']:.0f}MB free)",
                            )

            # ── Priority 1: Process Health Checks ──
            issues = check_health()

            if issues:
                criticals = [i for i in issues if i["severity"] == "critical"]
                warnings = [i for i in issues if i["severity"] == "warn"]

                if criticals:
                    guardian_log(
                        "ERROR",
                        f"Guardian detected {len(criticals)} critical issue(s), {len(warnings)} warning(s)",
                    )

                for issue in issues:
                    msg = issue["message"]

                    # Step 1: Check Knowledge Base
                    kb_solution = query_kb(msg)
                    if kb_solution:
                        guardian_log("INFO", f"KB fix available for: {msg[:100]}")
                        if issue.get("auto_fix"):
                            fixed = apply_auto_fix(issue)
                            if fixed:
                                guardian_log("INFO", f"Auto-fixed: {msg[:100]}")
                                continue

                    # Step 2: Try auto-fix for known patterns
                    if issue.get("auto_fix"):
                        fixed = apply_auto_fix(issue)
                        if fixed:
                            guardian_log(
                                "INFO", f"Auto-fixed (no KB needed): {msg[:100]}"
                            )
                            continue

                    # Step 3: Escalate to foveai-solver for complex issues
                    if issue["severity"] == "critical":
                        error_context = f"Guardian detected: {msg}\n"
                        if issue.get("details"):
                            error_context += (
                                f"Details: {json.dumps(issue['details'])}\n"
                            )
                        if kb_solution:
                            error_context += (
                                f"KB suggestion: {kb_solution.get('description', '')}\n"
                            )

                        escalate_to_solver(error_context, [issue])

                if warnings and not criticals:
                    for w in warnings:
                        guardian_log("WARN", w["message"])

            # ── Priority 2: Stutter Detection ──
            loop_end = time.time()
            stutter = detect_stutter(loop_start, loop_end)
            if stutter:
                guardian_log(
                    "ERROR" if stutter == "severe_stutter" else "WARN",
                    f"Guardian loop {stutter}: took {loop_end - loop_start:.1f}s "
                    f"(threshold: {HEALTH_INTERVAL * STUTTER_THRESHOLD_MULTIPLIER:.0f}s, "
                    f"consecutive: {_stutter_state['consecutive_stutters']})",
                )

                if (
                    _stutter_state["consecutive_stutters"]
                    >= STUTTER_CONSECUTIVE_THRESHOLD
                ):
                    guardian_log(
                        "ERROR",
                        f"🆘 {_stutter_state['consecutive_stutters']} consecutive stutters — "
                        f"system is choking! Emergency cleanse triggered.",
                    )
                    ram = get_system_ram()
                    if ram:
                        guardian_log(
                            "ERROR", f"Pre-cleanse RAM: {ram['used_pct']}% used"
                        )
                    procs = get_process_list()
                    top = sorted(procs, key=lambda p: p["mem_mb"], reverse=True)[:10]
                    killed = emergency_cleanse("emergency", top)
                    guardian_log(
                        "INFO",
                        f"Stutter emergency cleanse: killed {killed} process(es)",
                    )
                    _stutter_state["consecutive_stutters"] = 0

            # Mesh bus: publish health summary
            mesh_bus.publish_simple(
                "guardian.health_check",
                {
                    "issues_found": len(issues),
                    "critical": sum(1 for i in issues if i["severity"] == "critical"),
                    "warnings": sum(1 for i in issues if i["severity"] == "warn"),
                    "memory_pressure": pressure["level"] if pressure else "healthy",
                    "stutter": stutter,
                    "loop_duration_s": round(loop_end - loop_start, 1),
                },
            )

        except Exception as e:
            guardian_log("ERROR", f"Guardian loop error: {e}")

        await asyncio.sleep(HEALTH_INTERVAL)


# ─── Terminal Log Tailing (unchanged) ──────────────────────────────────────────
async def tail_terminal_logs():
    """Tail the terminal log file and feed it into TerminalLibrarian."""
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
    log_file = Path(temp_dir) / "terminal_librarian_input.jsonl"

    logger.info(f"Librarian: Waiting for terminal log file at {log_file}...")
    while not log_file.exists():
        await asyncio.sleep(2)

    logger.info(f"Librarian: Tailing terminal logs from {log_file}")

    # Import TerminalLibrarian dynamically
    import sys

    forge_dir = REPO_ROOT / "Forge"
    if str(forge_dir) not in sys.path:
        sys.path.insert(0, str(forge_dir))

    from terminal_librarian import TerminalLibrarian

    lib = TerminalLibrarian(
        archive_path=str(forge_dir / ".logs" / "terminal_archive.json")
    )

    # Open and tail the file
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        # Seek to the end of the file to only process new commands
        f.seek(0, 2)

        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.5)
                continue

            try:
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                event = json.loads(line_stripped)
                ev_type = event.get("type")
                cmd = event.get("command", "")

                if ev_type == "command_start":
                    lib.capture_command(cmd)
                    mesh_bus.publish_simple("terminal.command_start", {"command": cmd})
                    logger.info(f"Librarian: Command started: {cmd}")

                elif ev_type == "command_complete":
                    output = event.get("output", "")
                    exit_code = event.get("exit_code", 0)
                    lib.capture_output(output)
                    lib.complete_command(exit_code)

                    # Generate a clean summary of output
                    summary = output[:200] + "..." if len(output) > 200 else output
                    mesh_bus.publish_simple(
                        "terminal.command_complete",
                        {
                            "command": cmd,
                            "exit_code": exit_code,
                            "output_summary": summary,
                        },
                    )
                    logger.info(f"Librarian: Command completed ({exit_code}): {cmd}")

                elif ev_type == "command_error":
                    error_msg = event.get("error", "")
                    lib.capture_output(f"Error: {error_msg}")
                    lib.complete_command(1)
                    mesh_bus.publish_simple(
                        "terminal.command_error", {"command": cmd, "error": error_msg}
                    )
                    logger.warning(f"Librarian: Command failed: {cmd} - {error_msg}")

            except Exception as e:
                logger.warning(f"Librarian: Error tailing line: {e}")


async def periodic_discovery():
    """Periodically execute discovery swarm sweeps to map newly added classes/endpoints.
    Runs once on first startup, then once per week thereafter."""
    # Ensure backend/Cognition is in path
    import sys

    cog_dir = REPO_ROOT / "Mind" / "Cognition"
    if str(cog_dir) not in sys.path:
        sys.path.insert(0, str(cog_dir))

    # pyrefly: ignore [missing-import]
    from discovery_swarm import execute_discovery_mission

    # State file to track last discovery run
    state_file = REPO_ROOT / ".logs" / "discovery_state.json"
    WEEK_SECONDS = 7 * 24 * 3600  # 604800 seconds

    # Wait 30 seconds after startup for stabilization
    await asyncio.sleep(30)

    while True:
        try:
            # Check if we should run based on last run time
            should_run = True
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                    last_run = state.get("last_discovery_ts", 0)
                    elapsed = time.time() - last_run
                    if elapsed < WEEK_SECONDS:
                        remaining_h = (WEEK_SECONDS - elapsed) / 3600
                        logger.info(
                            f"Librarian: Skipping discovery sweep — last run was {elapsed / 3600:.1f}h ago "
                            f"(next run in {remaining_h:.1f}h)"
                        )
                        should_run = False
                except Exception:
                    should_run = True  # Corrupt state → run

            if should_run:
                logger.info("Librarian: Running weekly codebase discovery sweep...")
                result = await execute_discovery_mission(
                    duration_minutes=5, use_director=False, auto_apply=False
                )
                logger.info(
                    f"Librarian: Discovery sweep complete. Result: {result.get('summary', 'No summary')}"
                )

                # Persist timestamp
                state_file.parent.mkdir(parents=True, exist_ok=True)
                state_file.write_text(
                    json.dumps(
                        {
                            "last_discovery_ts": time.time(),
                            "last_discovery_iso": datetime.utcnow().isoformat() + "Z",
                            "last_result_summary": result.get("summary", "")[:200],
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        except Exception as e:
            logger.error(f"Librarian: Periodic discovery sweep failed: {e}")

        # Check every hour whether it's time for the next weekly run
        await asyncio.sleep(3600)


async def start_librarian_daemon():
    """Start all background daemon tasks including the active guardian."""
    logger.info("Librarian Daemon: Starting background threads...")

    # Generate freeze-cause rapport on startup (analyzes what happened before last shutdown)
    try:
        rapport = generate_freeze_rapport()
        print_freeze_rapport(rapport)
    except Exception as e:
        logger.warning(f"Librarian: Could not generate freeze rapport: {e}")

    asyncio.create_task(tail_terminal_logs())
    asyncio.create_task(periodic_discovery())
    asyncio.create_task(guardian_loop())  # 🛡️ Active guardian
