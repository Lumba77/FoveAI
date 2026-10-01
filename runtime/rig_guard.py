"""
runtime/rig_guard.py — FoveAI Rig & Bloat Guardian
===================================================
Proactive watchdog and mitigation system for resource-constrained rigs (e.g., 8-16 GB RAM).
Monitors:
  1. Language Server Bloat: Tracks language_server_windows_x64.exe and VS Code language workers.
     Triggers warnings if Working Set RAM > 1.2 GB or Virtual Memory > 12 GB.
     Provides 1-click clean kill/respawn.
  2. Workspace Ignore Safeguards: Audits .antigravityignore and searchMaxWorkspaceFileCount,
     auto-injecting exclusions for massive directories (client_quest, Library, PackageCache, Temp).
  3. Unity Engine & Zombie Worker Watchdog: Detects orphaned UnityShaderCompiler.exe and
     UnityCrashHandler64.exe left running after Unity closes, plus stale lockfiles / bloated Temp.
  4. System RAM Telemetry: Reads physical RAM via GlobalMemoryStatusEx and identifies
     top RAM consumers if system memory exceeds 85%.
  5. Alert Cooldown: Throttles toast notifications (default 10 minutes) to avoid annoyance.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

# ctypes is Windows-only; guard the import
if os.name == "nt":
    import ctypes

FOVEAI_DIR = Path(__file__).resolve().parent.parent
LUMAX_DIR = FOVEAI_DIR.parent
CLIENT_QUEST_DIR = FOVEAI_DIR / "client_quest"

# Cross-platform Antigravity IDE settings path
if os.name == "nt":
    ANTIGRAVITY_SETTINGS_PATH = Path(
        os.path.expanduser(r"~\AppData\Roaming\Antigravity IDE\User\settings.json")
    )
else:
    ANTIGRAVITY_SETTINGS_PATH = Path(
        os.path.expanduser("~/.config/Antigravity IDE/User/settings.json")
    )

# Crucial ignore patterns for game engines and ML monorepos
CRITICAL_IGNORE_PATTERNS = [
    "client_quest/**",
    "**/Library/**",
    "**/PackageCache/**",
    "**/Bee/**",
    "**/Temp/**",
    "**/ArtifactDB/**",
    "**/*.meta",
    "**/*.asset",
    "outputs/**",
    "Training/**",
    "Nursery/**",
    "venv/**",
    "**/venv/**",
    "node_modules/**",
]

if os.name == "nt":

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]


class RigGuard:
    """Watchdog and mitigation manager for system and process bloat."""

    def __init__(self, cooldown_seconds: int = 600):
        self.cooldown_seconds = cooldown_seconds
        self._last_alert_times: dict[str, float] = {}

    # ── System RAM Telemetry ───────────────────────────────────────────────
    def get_system_ram(self) -> dict[str, Any]:
        """Query physical RAM. Uses /proc/meminfo on Linux, GlobalMemoryStatusEx on Windows."""
        if os.name != "nt":
            try:
                with open("/proc/meminfo", "r") as f:
                    lines = f.readlines()
                info = {}
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        info[parts[0].rstrip(":")] = int(parts[1]) * 1024  # kB to bytes
                total_gb = info.get("MemTotal", 0) / (1024**3)
                avail_gb = info.get("MemAvailable", info.get("MemFree", 0)) / (1024**3)
                used_gb = max(0.0, total_gb - avail_gb)
                percent = int((used_gb / total_gb * 100) if total_gb > 0 else 0)
                return {
                    "total_gb": round(total_gb, 1),
                    "used_gb": round(used_gb, 1),
                    "avail_gb": round(avail_gb, 1),
                    "percent": percent,
                    "is_critical": percent >= 88 or avail_gb < 1.5,
                    "is_warning": percent >= 80 or avail_gb < 2.5,
                }
            except Exception as e:
                return {
                    "total_gb": 16.0,
                    "used_gb": 8.0,
                    "avail_gb": 8.0,
                    "percent": 50,
                    "is_critical": False,
                    "is_warning": False,
                    "error": str(e),
                }
        # Windows
        try:
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_gb = stat.ullTotalPhys / (1024**3)
            avail_gb = stat.ullAvailPhys / (1024**3)
            used_gb = max(0.0, total_gb - avail_gb)
            percent = int(stat.dwMemoryLoad)
            return {
                "total_gb": round(total_gb, 1),
                "used_gb": round(used_gb, 1),
                "avail_gb": round(avail_gb, 1),
                "percent": percent,
                "is_critical": percent >= 88 or avail_gb < 1.5,
                "is_warning": percent >= 80 or avail_gb < 2.5,
            }
        except Exception as e:
            return {
                "total_gb": 16.0,
                "used_gb": 8.0,
                "avail_gb": 8.0,
                "percent": 50,
                "is_critical": False,
                "is_warning": False,
                "error": str(e),
            }

    # ── Language Server Watchdog ───────────────────────────────────────────
    def get_language_server_status(self) -> dict[str, Any]:
        """
        Query running language server process metrics.
        On Linux: uses ps/pgrep. On Windows: uses PowerShell.
        Returns PID, RAM (MB), and health tier.
        """
        if os.name != "nt":
            return self._get_language_server_status_linux()
        return self._get_language_server_status_windows()

    def _get_language_server_status_linux(self) -> dict[str, Any]:
        """Linux: find language server / LSP / copilot processes via ps."""
        try:
            # Search for common language server process names
            out = subprocess.check_output(
                ["ps", "aux", "--sort=-rss"], text=True, timeout=5
            )
            target_names = [
                "language_server",
                "languageserver",
                "lsp",
                "copilot",
                "tsserver",
                "pyright",
                "pylance",
                "rust-analyzer",
                "clangd",
                "gopls",
                "jdtls",
            ]
            for line in out.splitlines()[1:]:  # skip header
                parts = line.split(None, 10)
                if len(parts) < 11:
                    continue
                cmd = parts[10].lower()
                if any(name in cmd for name in target_names):
                    pid = int(parts[1])
                    rss_kb = int(parts[5]) if len(parts) > 5 else 0
                    ram_mb = rss_kb // 1024
                    vmem_kb = int(parts[4]) if len(parts) > 4 else 0
                    vmem_mb = vmem_kb // 1024

                    if ram_mb >= 2000 or vmem_mb >= 15000:
                        tier = "CRITICAL"
                        status_text = (
                            f"🔴 Language Server: {ram_mb} MB (Runaway Indexing!)"
                        )
                    elif ram_mb >= 1000 or vmem_mb >= 10000:
                        tier = "WARNING"
                        status_text = f"🟠 Language Server: {ram_mb} MB (Elevated RAM)"
                    else:
                        tier = "HEALTHY"
                        status_text = f"🟢 Language Server: {ram_mb} MB (Healthy)"

                    return {
                        "running": True,
                        "pid": pid,
                        "ram_mb": ram_mb,
                        "vmem_mb": vmem_mb,
                        "tier": tier,
                        "status_text": status_text,
                    }
            return {
                "running": False,
                "pid": None,
                "ram_mb": 0,
                "vmem_mb": 0,
                "tier": "INACTIVE",
                "status_text": "⚪ Language Server: Not Running",
            }
        except Exception as e:
            return {
                "running": False,
                "pid": None,
                "ram_mb": 0,
                "vmem_mb": 0,
                "tier": "UNKNOWN",
                "status_text": f"⚪ Language Server: Query Error ({e})",
            }

    def _get_language_server_status_windows(self) -> dict[str, Any]:
        """Windows: query via PowerShell."""
        ps_cmd = (
            'Get-Process -Name "*language_server*" -ErrorAction SilentlyContinue | '
            "Select-Object -First 1 Id, ProcessName, WorkingSet64, VirtualMemorySize64 | "
            "ConvertTo-Json -Compress"
        )
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=0x08000000,
            )
            out = res.stdout.strip()
            if not out or out == "null":
                return {
                    "running": False,
                    "pid": None,
                    "ram_mb": 0,
                    "vmem_mb": 0,
                    "tier": "INACTIVE",
                    "status_text": "⚪ Language Server: Not Running",
                }

            data = json.loads(out)
            pid = data.get("Id")
            ram_mb = int(data.get("WorkingSet64", 0) / (1024 * 1024))
            vmem_mb = int(data.get("VirtualMemorySize64", 0) / (1024 * 1024))

            # Health classification
            if ram_mb >= 2000 or vmem_mb >= 15000:
                tier = "CRITICAL"
                status_text = f"🔴 Language Server: {ram_mb} MB (Runaway Indexing!)"
            elif ram_mb >= 1000 or vmem_mb >= 10000:
                tier = "WARNING"
                status_text = f"🟠 Language Server: {ram_mb} MB (Elevated RAM)"
            else:
                tier = "HEALTHY"
                status_text = f"🟢 Language Server: {ram_mb} MB (Healthy)"

            return {
                "running": True,
                "pid": pid,
                "ram_mb": ram_mb,
                "vmem_mb": vmem_mb,
                "tier": tier,
                "status_text": status_text,
            }
        except Exception as e:
            return {
                "running": False,
                "pid": None,
                "ram_mb": 0,
                "vmem_mb": 0,
                "tier": "UNKNOWN",
                "status_text": f"⚪ Language Server: Query Error ({e})",
            }

    def get_language_server_guidance(self) -> dict[str, str]:
        """
        Safe advice for resetting Language Server without killing Antigravity IDE.
        """
        return {
            "title": "Safe Antigravity Reset",
            "message": (
                "Do NOT force-kill language_server_windows_x64 directly — it severs the IDE's IPC socket!\n"
                "To reset memory safely:\n"
                "1. In Antigravity IDE, press Ctrl+Shift+P\n"
                "2. Type 'Developer: Reload Window' and press Enter\n"
                "Or simply restart Antigravity IDE cleanly."
            ),
        }

    # ── Memory Proxy Watchdog ──────────────────────────────────────────────
    def get_memory_proxy_status(self) -> dict[str, Any]:
        """
        Query running Port 8400 backend process metrics.
        Returns PID, RAM (MB), and health tier.
        """
        if os.name != "nt":
            return self._get_memory_proxy_status_linux()
        return self._get_memory_proxy_status_windows()

    def _get_memory_proxy_status_linux(self) -> dict[str, Any]:
        """Linux: find process on port 8400 via ss, then read /proc RSS."""
        try:
            out = subprocess.check_output(
                ["ss", "-tlnp", "sport = :8400"], text=True, timeout=3
            )
            pid = None
            for line in out.splitlines():
                if "pid=" in line:
                    pid_str = line.split("pid=")[1].split(",")[0].split(")")[0].strip()
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        break
            if not pid:
                return {
                    "running": False,
                    "pid": None,
                    "ram_mb": 0,
                    "tier": "INACTIVE",
                    "status_text": "⚪ Memory Proxy: Offline",
                }
            # Read RSS from /proc
            try:
                stat = open(f"/proc/{pid}/statm").read().split()
                rss_pages = int(stat[1])
                ram_mb = rss_pages * 4096 // (1024 * 1024)  # pages to MB
            except Exception:
                ram_mb = 0

            if ram_mb >= 800:
                tier = "CRITICAL"
                status_text = f"🔴 Memory Proxy: {ram_mb} MB (Memory Pressure!)"
            elif ram_mb >= 400:
                tier = "WARNING"
                status_text = f"🟠 Memory Proxy: {ram_mb} MB (Elevated RAM)"
            else:
                tier = "HEALTHY"
                status_text = f"🟢 Memory Proxy: {ram_mb} MB (Healthy)"

            return {
                "running": True,
                "pid": pid,
                "ram_mb": ram_mb,
                "tier": tier,
                "status_text": status_text,
            }
        except Exception as e:
            return {
                "running": False,
                "pid": None,
                "ram_mb": 0,
                "tier": "UNKNOWN",
                "status_text": f"⚪ Memory Proxy: Query Error ({e})",
            }

    def _get_memory_proxy_status_windows(self) -> dict[str, Any]:
        """Windows: query via PowerShell."""
        ps_cmd = (
            "$conn = Get-NetTCPConnection -LocalPort 8400 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 OwningProcess; "
            "if ($conn -and $conn.OwningProcess) { "
            "  Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue | "
            "  Select-Object Id, ProcessName, WorkingSet64, VirtualMemorySize64 | ConvertTo-Json -Compress "
            '} else { "null" }'
        )
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=0x08000000,
            )
            out = res.stdout.strip()
            if not out or out == "null":
                return {
                    "running": False,
                    "pid": None,
                    "ram_mb": 0,
                    "tier": "INACTIVE",
                    "status_text": "⚪ Memory Proxy: Offline",
                }

            data = json.loads(out)
            pid = data.get("Id")
            ram_mb = int(data.get("WorkingSet64", 0) / (1024 * 1024))

            if ram_mb >= 800:
                tier = "CRITICAL"
                status_text = f"🔴 Memory Proxy: {ram_mb} MB (Memory Pressure!)"
            elif ram_mb >= 400:
                tier = "WARNING"
                status_text = f"🟠 Memory Proxy: {ram_mb} MB (Elevated RAM)"
            else:
                tier = "HEALTHY"
                status_text = f"🟢 Memory Proxy: {ram_mb} MB (Healthy)"

            return {
                "running": True,
                "pid": pid,
                "ram_mb": ram_mb,
                "tier": tier,
                "status_text": status_text,
            }
        except Exception as e:
            return {
                "running": False,
                "pid": None,
                "ram_mb": 0,
                "tier": "UNKNOWN",
                "status_text": f"⚪ Memory Proxy: Query Error ({e})",
            }

    # ── Runaway Git & Worker Hunter ─────────────────────────────────────────
    def kill_runaway_git_processes(self, min_mb: int = 250) -> tuple[int, int, str]:
        """
        Detect and terminate orphaned git processes that consume huge RAM.
        Returns: (killed_count, freed_mb, message)
        """
        if os.name != "nt":
            return self._kill_runaway_git_linux(min_mb)
        return self._kill_runaway_git_windows(min_mb)

    def _kill_runaway_git_linux(self, min_mb: int) -> tuple[int, int, str]:
        """Linux: use ps to find git processes over min_mb RSS."""
        killed = 0
        freed = 0
        try:
            out = subprocess.check_output(
                ["ps", "aux", "--sort=-rss"], text=True, timeout=5
            )
            for line in out.splitlines()[1:]:
                parts = line.split(None, 10)
                if len(parts) < 11:
                    continue
                cmd = parts[10]
                if not cmd.startswith("git"):
                    continue
                rss_kb = int(parts[5]) if len(parts) > 5 else 0
                ram_mb = rss_kb // 1024
                if ram_mb >= min_mb:
                    pid = int(parts[1])
                    try:
                        os.kill(pid, __import__("signal").SIGTERM)
                        killed += 1
                        freed += ram_mb
                    except Exception:
                        pass
            if killed > 0:
                return (
                    killed,
                    freed,
                    f"Terminated {killed} runaway git process(es), liberating ~{freed} MB RAM!",
                )
            return 0, 0, "No runaway git processes detected (all < 250MB)."
        except Exception as e:
            return 0, 0, f"Error killing runaway git processes: {e}"

    def _kill_runaway_git_windows(self, min_mb: int) -> tuple[int, int, str]:
        """Windows: use PowerShell."""
        ps_cmd = (
            f"Get-Process -Name 'git' -ErrorAction SilentlyContinue | "
            f"Where-Object {{ ($_.WorkingSet64 / 1MB) -ge {min_mb} }} | "
            f"Select-Object Id, ProcessName, WorkingSet64 | "
            f"ConvertTo-Json -Compress"
        )
        killed_count = 0
        freed_mb = 0
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=0x08000000,
            )
            raw = res.stdout.strip()
            if not raw or raw == "null":
                return 0, 0, "No runaway git processes detected (all < 250MB)."

            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]

            for item in data:
                pid = item.get("Id")
                ws_mb = int(item.get("WorkingSet64", 0) / (1024 * 1024))
                if pid:
                    k = subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        text=True,
                        creationflags=0x08000000,
                    )
                    if k.returncode == 0:
                        killed_count += 1
                        freed_mb += ws_mb

            if killed_count > 0:
                msg = f"Terminated {killed_count} runaway git process(es), liberating ~{freed_mb} MB RAM!"
            else:
                msg = "No processes could be terminated."
            return killed_count, freed_mb, msg
        except Exception as e:
            return 0, 0, f"Error killing runaway git processes: {e}"

    # ── Unity & Zombie Process Watchdog ─────────────────────────────────────
    def get_unity_status(self) -> dict[str, Any]:
        """
        Check for Unity Editor processes and orphaned background workers.
        On Linux: uses pgrep/ps. On Windows: uses PowerShell.
        """
        if os.name != "nt":
            return self._get_unity_status_linux()
        return self._get_unity_status_windows()

    def _get_unity_status_linux(self) -> dict[str, Any]:
        """Linux: check for Unity Editor and shader compiler processes."""
        try:
            # Check for Unity Editor (Unity.x86_64 or Unity)
            unity_pids = []
            shader_pids = []
            crash_pids = []

            try:
                out = subprocess.check_output(
                    ["pgrep", "-f", "Unity"], text=True, timeout=3
                )
                unity_pids = []
                for p in out.strip().splitlines():
                    if not p.strip().isdigit():
                        continue
                    try:
                        with open(f"/proc/{p}/cmdline", "r") as cmd_f:
                            cmdline = cmd_f.read().replace("\x00", " ")
                        if "UnityShader" not in cmdline:
                            unity_pids.append(int(p))
                    except (FileNotFoundError, PermissionError):
                        continue
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

            try:
                out = subprocess.check_output(
                    ["pgrep", "-f", "UnityShaderCompiler"], text=True, timeout=3
                )
                shader_pids = [
                    int(p) for p in out.strip().splitlines() if p.strip().isdigit()
                ]
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

            try:
                out = subprocess.check_output(
                    ["pgrep", "-f", "UnityCrashHandler"], text=True, timeout=3
                )
                crash_pids = [
                    int(p) for p in out.strip().splitlines() if p.strip().isdigit()
                ]
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

            unity_running = len(unity_pids) > 0
            shader_workers = len(shader_pids)
            crash_handlers = len(crash_pids)

            lockfile = CLIENT_QUEST_DIR / "Temp" / "UnityLockfile"
            has_stale_lock = (not unity_running) and lockfile.exists()

            zombies = 0
            if not unity_running:
                zombies = shader_workers + crash_handlers
            elif shader_workers > 16:
                zombies = shader_workers - 8

            if zombies > 0 or has_stale_lock:
                status_text = f"⚠️ Unity: {zombies} Zombie Worker(s)"
                if has_stale_lock:
                    status_text += " + Stale Lockfile"
                tier = "WARNING"
            elif unity_running:
                status_text = f"🟢 Unity: Active ({shader_workers} shader workers)"
                tier = "HEALTHY"
            else:
                status_text = "⚪ Unity: Idle (Clean)"
                tier = "HEALTHY"

            return {
                "unity_running": unity_running,
                "shader_workers": shader_workers,
                "crash_handlers": crash_handlers,
                "zombies": zombies,
                "has_stale_lock": has_stale_lock,
                "shader_pids": shader_pids,
                "crash_pids": crash_pids,
                "tier": tier,
                "status_text": status_text,
            }
        except Exception as e:
            return {
                "unity_running": False,
                "zombies": 0,
                "tier": "UNKNOWN",
                "status_text": f"⚪ Unity: Query Error ({e})",
            }

    def _get_unity_status_windows(self) -> dict[str, Any]:
        """Windows: query via PowerShell."""
        ps_cmd = (
            '$u = @(Get-Process -Name "Unity" -ErrorAction SilentlyContinue); '
            '$s = @(Get-Process -Name "*UnityShaderCompiler*" -ErrorAction SilentlyContinue); '
            '$c = @(Get-Process -Name "*UnityCrashHandler*" -ErrorAction SilentlyContinue); '
            "[PSCustomObject]@{ "
            "  UnityRunning = ($u.Count -gt 0); "
            "  UnityCount = $u.Count; "
            "  ShaderWorkers = $s.Count; "
            "  CrashHandlers = $c.Count; "
            "  ShaderPids = @($s | Select-Object -ExpandProperty Id); "
            "  CrashPids = @($c | Select-Object -ExpandProperty Id); "
            "} | ConvertTo-Json -Compress"
        )
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=0x08000000,
            )
            data = json.loads(res.stdout.strip())
            unity_running = bool(data.get("UnityRunning"))
            shader_workers = int(data.get("ShaderWorkers", 0))
            crash_handlers = int(data.get("CrashHandlers", 0))
            shader_pids = data.get("ShaderPids", [])
            crash_pids = data.get("CrashPids", [])

            # Check for stale lockfile
            lockfile = CLIENT_QUEST_DIR / "Temp" / "UnityLockfile"
            has_stale_lock = (not unity_running) and lockfile.exists()

            # Zombie workers: workers running while Unity.exe is NOT running
            zombies = 0
            if not unity_running:
                zombies = shader_workers + crash_handlers
            elif shader_workers > 16:  # abnormally high worker pool
                zombies = shader_workers - 8

            if zombies > 0 or has_stale_lock:
                status_text = f"⚠️ Unity: {zombies} Zombie Worker(s)"
                if has_stale_lock:
                    status_text += " + Stale Lockfile"
                tier = "WARNING"
            elif unity_running:
                status_text = f"🟢 Unity: Active ({shader_workers} shader workers)"
                tier = "HEALTHY"
            else:
                status_text = "⚪ Unity: Idle (Clean)"
                tier = "HEALTHY"

            return {
                "unity_running": unity_running,
                "shader_workers": shader_workers,
                "crash_handlers": crash_handlers,
                "zombies": zombies,
                "has_stale_lock": has_stale_lock,
                "shader_pids": shader_pids,
                "crash_pids": crash_pids,
                "tier": tier,
                "status_text": status_text,
            }
        except Exception as e:
            return {
                "unity_running": False,
                "zombies": 0,
                "tier": "UNKNOWN",
                "status_text": f"⚪ Unity: Query Error ({e})",
            }

    def kill_zombie_unity_workers(self) -> tuple[int, str]:
        """Kill orphaned Unity shader compiler and crash handler instances."""
        killed = 0
        try:
            if os.name != "nt":
                # Linux: use pkill
                for pattern in ["UnityShaderCompiler", "UnityCrashHandler"]:
                    try:
                        subprocess.run(
                            ["pkill", "-f", pattern], capture_output=True, timeout=3
                        )
                        killed += 1
                    except Exception:
                        pass
            else:
                # Windows: taskkill
                for proc in ["UnityShaderCompiler.exe", "UnityCrashHandler64.exe"]:
                    r = subprocess.run(
                        ["taskkill", "/F", "/IM", proc],
                        capture_output=True,
                        text=True,
                        creationflags=0x08000000,
                    )
                    if r.returncode == 0:
                        killed += 1
            # Clean stale lockfile if Unity is not running
            st = self.get_unity_status()
            if not st.get("unity_running"):
                lockfile = CLIENT_QUEST_DIR / "Temp" / "UnityLockfile"
                if lockfile.exists():
                    try:
                        lockfile.unlink(missing_ok=True)
                    except Exception:
                        pass
            return killed, f"Terminated {killed} zombie worker process group(s)."
        except Exception as e:
            return killed, str(e)

    def clean_unity_temp(self) -> tuple[bool, str]:
        """Clean client_quest/Temp directory safely if Unity is closed."""
        st = self.get_unity_status()
        if st.get("unity_running"):
            return False, "Cannot clean Temp while Unity Editor is running."

        temp_dir = CLIENT_QUEST_DIR / "Temp"
        if not temp_dir.exists():
            return True, "Temp directory is already empty/clean."

        try:
            import shutil

            # Remove all items inside Temp rather than deleting root Temp dir
            freed_count = 0
            for item in temp_dir.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink(missing_ok=True)
                        freed_count += 1
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                        freed_count += 1
                except Exception:
                    pass
            return True, f"Cleaned {freed_count} temporary Unity cache items."
        except Exception as e:
            return False, f"Failed to clean Temp: {e}"

    # ── Workspace Ignore & Search Cap Safeguards ────────────────────────────
    def check_workspace_ignores(self) -> dict[str, Any]:
        """
        Verify that .antigravityignore has essential exclusions and IDE file count cap is set.
        """
        ignore_file = LUMAX_DIR / ".antigravityignore"
        foveai_ignore = FOVEAI_DIR / ".antigravityignore"

        missing_lumax = []
        if not ignore_file.exists():
            missing_lumax = list(CRITICAL_IGNORE_PATTERNS)
        else:
            try:
                content = ignore_file.read_text(encoding="utf-8", errors="ignore")
                for p in CRITICAL_IGNORE_PATTERNS:
                    if p.split("/**")[0] not in content:
                        missing_lumax.append(p)
            except Exception:
                missing_lumax = list(CRITICAL_IGNORE_PATTERNS)

        # Check searchMaxWorkspaceFileCount in Antigravity settings
        cap_status = "OK"
        current_cap = 5000
        if ANTIGRAVITY_SETTINGS_PATH.exists():
            try:
                settings_data = json.loads(
                    ANTIGRAVITY_SETTINGS_PATH.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                )
                current_cap = settings_data.get(
                    "antigravity.searchMaxWorkspaceFileCount", 5000
                )
                if current_cap > 300:
                    cap_status = "UNCAPPED"
            except Exception:
                cap_status = "ERROR"

        is_healthy = len(missing_lumax) == 0 and cap_status == "OK"
        if is_healthy:
            status_text = f"✅ Workspace Ignores: Protected (Cap {current_cap})"
        else:
            issues = []
            if missing_lumax:
                issues.append(f"{len(missing_lumax)} Missing Patterns")
            if cap_status == "UNCAPPED":
                issues.append(f"Cap is {current_cap} (Recommend <= 200)")
            status_text = f"⚠️ Workspace Ignores: {', '.join(issues)}"

        return {
            "healthy": is_healthy,
            "missing_patterns": missing_lumax,
            "current_cap": current_cap,
            "cap_status": cap_status,
            "status_text": status_text,
        }

    def fix_workspace_ignores(self) -> tuple[bool, str]:
        """
        Auto-inject required ignore patterns to .antigravityignore and cap searchMaxWorkspaceFileCount.
        """
        changes = []
        # 1. Update LUMAX/.antigravityignore
        for target_path in [
            LUMAX_DIR / ".antigravityignore",
            FOVEAI_DIR / ".antigravityignore",
        ]:
            existing = ""
            if target_path.exists():
                try:
                    existing = target_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    existing = ""

            lines_to_add = []
            for pat in CRITICAL_IGNORE_PATTERNS:
                base = pat.split("/**")[0]
                if base not in existing:
                    lines_to_add.append(pat)

            if lines_to_add:
                new_content = (
                    existing.rstrip()
                    + "\n\n# Rig Guard Auto-Protection\n"
                    + "\n".join(lines_to_add)
                    + "\n"
                )
                target_path.write_text(new_content, encoding="utf-8")
                changes.append(
                    f"Injected {len(lines_to_add)} patterns into {target_path.name}"
                )

        # 2. Update Antigravity IDE settings.json (both User and Workspace)
        for s_path in [
            ANTIGRAVITY_SETTINGS_PATH,
            FOVEAI_DIR / ".vscode" / "settings.json",
            LUMAX_DIR / ".vscode" / "settings.json",
        ]:
            if s_path.exists():
                try:
                    raw = s_path.read_text(encoding="utf-8", errors="ignore")
                    settings_data = json.loads(raw)
                    if (
                        settings_data.get(
                            "antigravity.searchMaxWorkspaceFileCount", 5000
                        )
                        > 200
                    ):
                        settings_data["antigravity.searchMaxWorkspaceFileCount"] = 200
                        s_path.write_text(
                            json.dumps(settings_data, indent=4), encoding="utf-8"
                        )
                        changes.append(
                            f"Capped searchMaxWorkspaceFileCount to 200 in {s_path.name}"
                        )
                except Exception as e:
                    changes.append(f"Could not update {s_path.name}: {e}")

        if not changes:
            return True, "Workspace ignores and file search caps are already optimal."
        return True, " | ".join(changes)

    # ── Top RAM Consumers ──────────────────────────────────────────────────
    def get_top_ram_consumers(self, limit: int = 4) -> list[dict[str, Any]]:
        """Identify processes consuming the most RAM."""
        if os.name != "nt":
            return self._get_top_ram_consumers_linux(limit)
        return self._get_top_ram_consumers_windows(limit)

    def _get_top_ram_consumers_linux(self, limit: int) -> list[dict[str, Any]]:
        """Linux: use ps to find top RAM consumers."""
        try:
            out = subprocess.check_output(
                ["ps", "aux", "--sort=-rss"], text=True, timeout=5
            )
            results = []
            for line in out.splitlines()[1:]:  # skip header
                parts = line.split(None, 10)
                if len(parts) < 11:
                    continue
                pid = int(parts[1])
                rss_kb = int(parts[5]) if len(parts) > 5 else 0
                ram_mb = rss_kb // 1024
                # Extract process name from command
                cmd = parts[10]
                name = cmd.split()[0] if cmd.split() else "unknown"
                name = os.path.basename(name)
                results.append({"id": pid, "name": name, "ram_mb": ram_mb})
                if len(results) >= limit:
                    break
            return results
        except Exception:
            return []

    def _get_top_ram_consumers_windows(self, limit: int) -> list[dict[str, Any]]:
        """Windows: use PowerShell."""
        ps_cmd = (
            f"Get-Process | Sort-Object -Descending WorkingSet64 | "
            f"Select-Object -First {limit} Id, ProcessName, WorkingSet64 | "
            f"ConvertTo-Json -Compress"
        )
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=0x08000000,
            )
            raw = res.stdout.strip()
            if not raw:
                return []
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            results = []
            for p in data:
                mb = int(p.get("WorkingSet64", 0) / (1024 * 1024))
                results.append(
                    {
                        "id": p.get("Id"),
                        "name": p.get("ProcessName"),
                        "ram_mb": mb,
                    }
                )
            return results
        except Exception:
            return []

    # ── Audit & Notification Cooldown ──────────────────────────────────────
    def audit_and_alert(self, notify_fn) -> list[str]:
        """
        Runs comprehensive bloat checks and sends throttled notifications.
        Returns a list of dispatched alert messages.
        """
        now = time.time()
        dispatched = []

        # Check 1: Language Server Bloat (Non-destructive guidance)
        ls_status = self.get_language_server_status()
        if ls_status.get("tier") == "CRITICAL":
            last_t = self._last_alert_times.get("ls", 0)
            if now - last_t > self.cooldown_seconds:
                self._last_alert_times["ls"] = now
                msg = (
                    f"⚠️ Antigravity Language Server RAM is elevated: {ls_status['ram_mb']} MB.\n"
                    f"Safely reload without crash: In Antigravity, press Ctrl+Shift+P ➔ 'Developer: Reload Window'."
                )
                notify_fn(msg, "FoveAI Rig Guardian")
                dispatched.append(msg)

        # Check 2: Runaway Git Process Bloat
        try:
            g_count = 0
            g_sum_mb = 0
            if os.name != "nt":
                git_out = subprocess.check_output(
                    ["ps", "aux", "--sort=-rss"], text=True, timeout=5
                )
                for line in git_out.splitlines()[1:]:
                    parts = line.split(None, 10)
                    if len(parts) < 11 or not parts[10].startswith("git"):
                        continue
                    rss_kb = int(parts[5]) if len(parts) > 5 else 0
                    ram_mb = rss_kb // 1024
                    if ram_mb >= 400:
                        g_count += 1
                        g_sum_mb += ram_mb
            else:
                ps_git = (
                    "Get-Process -Name 'git' -ErrorAction SilentlyContinue | "
                    "Where-Object { ($_.WorkingSet64 / 1MB) -ge 400 } | "
                    "Measure-Object -Property WorkingSet64 -Sum | "
                    "Select-Object Count, Sum | ConvertTo-Json -Compress"
                )
                g_res = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", ps_git],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=0x08000000,
                )
                if g_res.stdout.strip() and g_res.stdout.strip() != "null":
                    g_data = json.loads(g_res.stdout.strip())
                    g_count = g_data.get("Count", 0)
                    g_sum_mb = int((g_data.get("Sum") or 0) / (1024 * 1024))

            if g_count > 0:
                last_t = self._last_alert_times.get("git_runaway", 0)
                if now - last_t > self.cooldown_seconds:
                    self._last_alert_times["git_runaway"] = now
                    msg = (
                        f"⚠️ Detected {g_count} runaway git task(s) consuming ~{g_sum_mb} MB RAM!\n"
                        f"Open tray ➔ 'Rig & Bloat Guardian' ➔ 'Kill Runaway Git Tasks' to reclaim memory."
                    )
                    notify_fn(msg, "FoveAI Rig Guardian")
                    dispatched.append(msg)
        except Exception:
            pass

        # Check 3: Unity Zombie Workers
        unity_status = self.get_unity_status()
        if unity_status.get("zombies", 0) > 0:
            last_t = self._last_alert_times.get("unity_zombies", 0)
            if now - last_t > self.cooldown_seconds:
                self._last_alert_times["unity_zombies"] = now
                msg = (
                    f"⚠️ Detected {unity_status['zombies']} orphaned Unity background worker(s).\n"
                    f"Open tray ➔ 'Rig & Bloat Guardian' ➔ 'Kill Zombie Unity Workers'."
                )
                notify_fn(msg, "FoveAI Rig Guardian")
                dispatched.append(msg)

        # Check 3: System RAM Exhaustion
        ram_status = self.get_system_ram()
        if ram_status.get("is_critical"):
            last_t = self._last_alert_times.get("ram_critical", 0)
            if now - last_t > self.cooldown_seconds:
                self._last_alert_times["ram_critical"] = now
                top = self.get_top_ram_consumers(3)
                top_str = ", ".join([f"{p['name']} ({p['ram_mb']}MB)" for p in top])
                msg = (
                    f"🚨 Physical RAM Critical: {ram_status['percent']}% used ({ram_status['avail_gb']} GB free)!\n"
                    f"Top consumers: {top_str}."
                )
                notify_fn(msg, "FoveAI Rig Guardian")
                dispatched.append(msg)

        # Check 4: Node.js Foveated Memory Proxy Bloat
        proxy_status = self.get_memory_proxy_status()
        if proxy_status.get("tier") == "CRITICAL":
            last_t = self._last_alert_times.get("memory_proxy", 0)
            if now - last_t > self.cooldown_seconds:
                self._last_alert_times["memory_proxy"] = now
                msg = (
                    f"⚠️ Foveated Memory Proxy RAM is critical: {proxy_status['ram_mb']} MB.\n"
                    f"Open tray ➔ 'Restart Memory Proxy (8400)' to flush caches cleanly."
                )
                notify_fn(msg, "FoveAI Rig Guardian")
                dispatched.append(msg)

        return dispatched
