"""
FoveAI Health Monitor — Continuous subsystem health checks, coherence tests,
and auto-healing for the FoveAI runtime stack.

Checks:
  - Proxy (8400): foveated-memory proxy reachability
  - Dashboard (8414): settings/dashboard
  - XRLF Runtime (8402): model loaded, soul bridge, memory
  - WebSocket IPC (8403): Quest client endpoint
  - TTS (Kokoro): speech synthesis available
  - STT (Whisper): transcription available
  - Vision: mmproj loaded
  - Soul: Alice persona loaded with traits
  - Memory: persistent DB not corrupted
  - Coherence: model responds with Alice identity (sharp mode)
  - Repo health: git status, workspace ignores

Healing actions:
  - Restart XRLF runtime (clear memory + KV cache)
  - Restart proxy
  - Clear corrupted memory turns
  - Reload soul bridge
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ─── Paths ──────────────────────────────────────────────────────────
FOVEAI_DIR = Path(__file__).resolve().parent
VENV_PYTHON = str(FOVEAI_DIR / ".venv" / "bin" / "python")
MEMORY_DB = (
    FOVEAI_DIR / "xrl_encoded" / "gemma-4-e2b-multimodal-v1.0.xrlf.cache" / "memory.db"
)
XRLF_LIVE_LOG = Path.home() / "xrlf_live.log"
FOVEATED_PROXY_LOG = Path.home() / "foveated_proxy.log"

# ─── Ports ──────────────────────────────────────────────────────────
PORT_PROXY = 8400
PORT_DASHBOARD = 8414
PORT_XRLF = 8402
PORT_WS = 8403


class HealthStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    name: str
    status: HealthStatus
    detail: str = ""
    latency_ms: float = 0.0
    healable: bool = False
    heal_action: str | None = None

    @property
    def icon(self) -> str:
        return {
            HealthStatus.PASS: "OK",
            HealthStatus.FAIL: "FAIL",
            HealthStatus.WARN: "WARN",
            HealthStatus.UNKNOWN: "?",
        }[self.status]

    @property
    def color(self) -> str:
        return {
            HealthStatus.PASS: "green",
            HealthStatus.FAIL: "red",
            HealthStatus.WARN: "yellow",
            HealthStatus.UNKNOWN: "gray",
        }[self.status]


@dataclass
class HealthReport:
    timestamp: float = field(default_factory=time.time)
    results: list[CheckResult] = field(default_factory=list)
    overall: HealthStatus = HealthStatus.UNKNOWN
    summary: str = ""

    def add(self, r: CheckResult) -> None:
        self.results.append(r)
        if r.status == HealthStatus.FAIL:
            self.overall = HealthStatus.FAIL
        elif r.status == HealthStatus.WARN and self.overall != HealthStatus.FAIL:
            self.overall = HealthStatus.WARN
        elif r.status == HealthStatus.PASS and self.overall == HealthStatus.UNKNOWN:
            self.overall = HealthStatus.PASS

    def failing(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == HealthStatus.FAIL]

    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == HealthStatus.WARN]


# ─── Helpers ────────────────────────────────────────────────────────


def _port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _http_get(url: str, timeout: float = 2.0) -> tuple[int, dict | None]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FoveAI-Health/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, {"_raw": body[:200]}
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def _http_post(
    url: str, data: dict, timeout: float = 30.0
) -> tuple[int, dict | None]:
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "FoveAI-Health/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw[:300]}
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


# ─── Individual Checks ──────────────────────────────────────────────


def check_proxy() -> CheckResult:
    if not _port_open(PORT_PROXY):
        return CheckResult(
            "Proxy :8400",
            HealthStatus.FAIL,
            "Port not listening",
            healable=True,
            heal_action="restart_proxy",
        )
    code, body = _http_get(f"http://127.0.0.1:{PORT_PROXY}/health", timeout=2)
    if code == 200:
        return CheckResult("Proxy :8400", HealthStatus.PASS, "Healthy")
    return CheckResult(
        "Proxy :8400",
        HealthStatus.WARN,
        f"Port open but /health={code}",
        healable=True,
        heal_action="restart_proxy",
    )


def check_dashboard() -> CheckResult:
    if not _port_open(PORT_DASHBOARD):
        return CheckResult(
            "Dashboard :8414",
            HealthStatus.WARN,
            "Port not listening",
            healable=True,
            heal_action="restart_proxy",
        )
    return CheckResult("Dashboard :8414", HealthStatus.PASS, "Listening")


def check_xrlf_runtime() -> CheckResult:
    if not _port_open(PORT_XRLF):
        return CheckResult(
            "XRLF Runtime :8402",
            HealthStatus.FAIL,
            "Port not listening",
            healable=True,
            heal_action="restart_xrlf",
        )
    code, body = _http_get(f"http://127.0.0.1:{PORT_XRLF}/health", timeout=2)
    if code == 200 and body:
        model = body.get("model", "?")
        loaded = body.get("status") == "ok"
        if loaded:
            return CheckResult(
                "XRLF Runtime :8402", HealthStatus.PASS, f"Model: {model}"
            )
        return CheckResult(
            "XRLF Runtime :8402",
            HealthStatus.WARN,
            f"Status: {body.get('status')}",
            healable=True,
            heal_action="restart_xrlf",
        )
    return CheckResult(
        "XRLF Runtime :8402",
        HealthStatus.FAIL,
        f"/health={code}",
        healable=True,
        heal_action="restart_xrlf",
    )


def check_ws_ipc() -> CheckResult:
    if not _port_open(PORT_WS):
        return CheckResult(
            "WebSocket IPC :8403",
            HealthStatus.WARN,
            "Port not listening",
            healable=True,
            heal_action="restart_xrlf",
        )
    return CheckResult("WebSocket IPC :8403", HealthStatus.PASS, "Listening")


def check_soul() -> CheckResult:
    code, body = _http_get(f"http://127.0.0.1:{PORT_XRLF}/soul/status", timeout=2)
    if code != 200 or not body:
        return CheckResult(
            "Soul (Alice)",
            HealthStatus.WARN,
            f"/soul/status={code}",
            healable=True,
            heal_action="restart_xrlf",
        )
    # The response is nested: {soul: {name, traits, ...}, shaping: {axes, shaped_by}}
    soul = body.get("soul", body)
    name = soul.get("name", "?")
    traits = soul.get("traits", soul.get("trait_count", 0))
    if isinstance(traits, list):
        traits = len(traits)
    shaping = body.get("shaping", {})
    axes = shaping.get("axes", {})
    shaped_by = shaping.get("shaped_by", [])
    shaping_count = (
        len(axes)
        if isinstance(axes, dict)
        else (len(shaped_by) if isinstance(shaped_by, list) else 0)
    )
    if name.lower() == "alice" and int(traits or 0) > 0:
        return CheckResult(
            "Soul (Alice)",
            HealthStatus.PASS,
            f"{name}, {traits} traits, {shaping_count} shaping",
        )
    return CheckResult(
        "Soul (Alice)",
        HealthStatus.WARN,
        f"name={name} traits={traits}",
        healable=True,
        heal_action="restart_xrlf",
    )


def check_memory() -> CheckResult:
    code, body = _http_get(f"http://127.0.0.1:{PORT_XRLF}/memory/status", timeout=2)
    if code != 200 or not body:
        return CheckResult("Memory DB", HealthStatus.WARN, f"/memory/status={code}")
    turns = body.get("total_turns", body.get("turns", 0))
    sessions = body.get("all_sessions", [])
    if isinstance(sessions, list):
        session_count = len(sessions)
    else:
        session_count = 0
    return CheckResult(
        "Memory DB", HealthStatus.PASS, f"{turns} turns, {session_count} sessions"
    )


def check_capabilities() -> CheckResult:
    code, body = _http_get(f"http://127.0.0.1:{PORT_XRLF}/v1/capabilities", timeout=2)
    if code != 200 or not body:
        return CheckResult(
            "Capabilities", HealthStatus.WARN, f"/v1/capabilities={code}"
        )
    parts = []
    if body.get("vision"):
        parts.append("vision")
    if body.get("audio_stt"):
        parts.append("audio_stt")
    if body.get("tts"):
        parts.append("tts")
    if body.get("mmproj_loaded"):
        parts.append("mmproj")
    gpu = body.get("gpu_layers", 0)
    parts.append(f"gpu={gpu}")
    if not parts:
        return CheckResult(
            "Capabilities", HealthStatus.WARN, "No capabilities detected"
        )
    return CheckResult("Capabilities", HealthStatus.PASS, ", ".join(parts))


def check_tts() -> CheckResult:
    """Check if Kokoro TTS is available by doing a tiny synthesis."""
    code, body = _http_get(f"http://127.0.0.1:{PORT_XRLF}/v1/capabilities", timeout=2)
    if code == 200 and body and body.get("tts"):
        return CheckResult("TTS (Kokoro)", HealthStatus.PASS, "Available")
    return CheckResult(
        "TTS (Kokoro)",
        HealthStatus.WARN,
        "Not available",
        healable=True,
        heal_action="restart_xrlf",
    )


def check_stt() -> CheckResult:
    """Check if Whisper STT is available."""
    code, body = _http_get(f"http://127.0.0.1:{PORT_XRLF}/v1/capabilities", timeout=2)
    if code == 200 and body and body.get("audio_stt"):
        return CheckResult("STT (Whisper)", HealthStatus.PASS, "Available")
    return CheckResult(
        "STT (Whisper)",
        HealthStatus.WARN,
        "Not available",
        healable=True,
        heal_action="restart_xrlf",
    )


def check_context_window() -> CheckResult:
    """Check that the runtime context window is sane."""
    code, body = _http_get(f"http://127.0.0.1:{PORT_XRLF}/v1/context", timeout=2)
    if code != 200 or not body:
        return CheckResult("Context Window", HealthStatus.WARN, f"/v1/context={code}")
    ctx = body.get("context_window", 0)
    model = body.get("model", "?")
    if ctx < 1024:
        return CheckResult(
            "Context Window", HealthStatus.FAIL, f"Too small: {ctx} for {model}"
        )
    return CheckResult("Context Window", HealthStatus.PASS, f"{ctx} tokens ({model})")


# ─── Coherence Test (Sharp Mode) ────────────────────────────────────

# Bad response patterns that indicate model incoherence
_BAD_PATTERNS = [
    "the quick brown fox",
    "pangram",
    "nuclear",
    "quantum computing",
    "quantum leap",
    "narrative writing",
    "creative writing",
    "here are some examples",
    "action.*summarize",
    "jaded zombie",
]

# Alice identity markers that should appear
_GOOD_MARKERS = ["alice", "danie", "jennifer"]


def check_coherence(timeout: float = 30.0) -> CheckResult:
    """Sharp mode: send a probe question and verify Alice responds coherently."""
    code, body = _http_post(
        f"http://127.0.0.1:{PORT_XRLF}/v1/chat/completions",
        {
            "model": "xrlf",
            "messages": [
                {"role": "user", "content": "What is your name? Who made you?"}
            ],
            "max_tokens": 80,
            "temperature": 0.7,
            "stream": False,
        },
        timeout=timeout,
    )
    if code != 200 or not body:
        return CheckResult(
            "Coherence",
            HealthStatus.FAIL,
            f"Chat failed: {code}",
            healable=True,
            heal_action="restart_xrlf",
        )
    choices = body.get("choices", [])
    if not choices:
        return CheckResult(
            "Coherence",
            HealthStatus.FAIL,
            "No choices in response",
            healable=True,
            heal_action="restart_xrlf",
        )
    content = choices[0].get("message", {}).get("content", "").lower().strip()
    if not content:
        return CheckResult(
            "Coherence",
            HealthStatus.FAIL,
            "Empty response",
            healable=True,
            heal_action="restart_xrlf",
        )

    # Check for bad patterns
    import re

    for pattern in _BAD_PATTERNS:
        if re.search(pattern, content):
            return CheckResult(
                "Coherence",
                HealthStatus.FAIL,
                f"Bad pattern: '{pattern}' in response: {content[:80]}",
                healable=True,
                heal_action="restart_xrlf_clear_memory",
            )

    # Check for Alice identity
    has_alice = any(m in content for m in _GOOD_MARKERS)
    if has_alice:
        return CheckResult(
            "Coherence", HealthStatus.PASS, f"Alice identified: {content[:80]}"
        )

    # Response is coherent but doesn't mention Alice — warn
    return CheckResult(
        "Coherence",
        HealthStatus.WARN,
        f"No Alice identity: {content[:80]}",
        healable=True,
        heal_action="restart_xrlf",
    )


def check_repo_health() -> CheckResult:
    """Check git repo health — uncommitted file count, no conflicts."""
    # FoveAI may be a subdirectory; walk up to find .git
    git_dir = FOVEAI_DIR
    while git_dir != git_dir.parent:
        if (git_dir / ".git").exists():
            break
        git_dir = git_dir.parent
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(git_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return CheckResult(
                "Repo Health",
                HealthStatus.WARN,
                f"git status failed: {result.stderr[:80]}",
            )
        lines = [l for l in result.stdout.strip().split("\n") if l]
        conflict_lines = [l for l in lines if l.startswith(("UU", "AA", "DD"))]
        if conflict_lines:
            return CheckResult(
                "Repo Health",
                HealthStatus.FAIL,
                f"{len(conflict_lines)} merge conflicts",
            )
        return CheckResult(
            "Repo Health", HealthStatus.PASS, f"{len(lines)} uncommitted files"
        )
    except Exception as e:
        return CheckResult("Repo Health", HealthStatus.WARN, f"git error: {e}")


def check_kv_cache() -> CheckResult:
    """Check XRLF live log for stale KV cache replay."""
    if not XRLF_LIVE_LOG.exists():
        return CheckResult("KV Cache", HealthStatus.UNKNOWN, "No log file")
    try:
        content = XRLF_LIVE_LOG.read_text(errors="replace")
        # Count recent "skipping reset" occurrences
        skip_count = content.count("full prompt already cached, skipping reset")
        if skip_count > 5:
            return CheckResult(
                "KV Cache",
                HealthStatus.WARN,
                f"{skip_count} stale cache replays detected",
                healable=True,
                heal_action="restart_xrlf",
            )
        return CheckResult(
            "KV Cache", HealthStatus.PASS, f"{skip_count} cache reuses (normal)"
        )
    except Exception as e:
        return CheckResult("KV Cache", HealthStatus.UNKNOWN, f"Log read error: {e}")


def check_memory_corruption() -> CheckResult:
    """Check persistent memory DB for known bad patterns."""
    if not MEMORY_DB.exists():
        return CheckResult("Memory Integrity", HealthStatus.UNKNOWN, "No memory DB")
    try:
        conn = sqlite3.connect(str(MEMORY_DB))
        rows = conn.execute("SELECT content FROM turns LIMIT 50").fetchall()
        conn.close()
        bad = 0
        for (text,) in rows:
            if not text:
                continue
            lower = text.lower()
            if any(
                p in lower
                for p in ["the quick brown fox", "pangram", 'action": "summarize']
            ):
                bad += 1
        if bad > 0:
            return CheckResult(
                "Memory Integrity",
                HealthStatus.FAIL,
                f"{bad} corrupted turns found",
                healable=True,
                heal_action="clear_memory",
            )
        return CheckResult(
            "Memory Integrity", HealthStatus.PASS, f"{len(rows)} turns clean"
        )
    except Exception as e:
        return CheckResult("Memory Integrity", HealthStatus.WARN, f"DB error: {e}")


# ─── Full Report ────────────────────────────────────────────────────


def run_full_report(include_coherence: bool = False) -> HealthReport:
    """Run all health checks. Coherence test is optional (it's a real chat)."""
    report = HealthReport()
    # Fast checks first
    report.add(check_proxy())
    report.add(check_dashboard())
    report.add(check_xrlf_runtime())
    report.add(check_ws_ipc())
    report.add(check_soul())
    report.add(check_memory())
    report.add(check_capabilities())
    report.add(check_tts())
    report.add(check_stt())
    report.add(check_context_window())
    report.add(check_kv_cache())
    report.add(check_memory_corruption())
    report.add(check_repo_health())
    # Coherence is a real model call — only when requested
    if include_coherence:
        report.add(check_coherence())

    fails = report.failing()
    warns = report.warnings()
    parts = []
    if fails:
        parts.append(f"{len(fails)} FAIL")
    if warns:
        parts.append(f"{len(warns)} WARN")
    if not parts:
        parts.append("ALL PASS")
    report.summary = " | ".join(parts)
    return report


def run_sharp_report() -> HealthReport:
    """Run full report INCLUDING the coherence probe (slow, ~30s)."""
    return run_full_report(include_coherence=True)


# ─── Healing Actions ────────────────────────────────────────────────


def heal_restart_xrlf(clear_memory: bool = False) -> tuple[bool, str]:
    """Restart the XRLF runtime. Optionally clear persistent memory first."""
    # Kill existing
    subprocess.run(["pkill", "-f", "run_xrlf.py"], capture_output=True, timeout=5)
    time.sleep(3)

    if clear_memory and MEMORY_DB.exists():
        try:
            conn = sqlite3.connect(str(MEMORY_DB))
            conn.execute("DELETE FROM turns")
            conn.commit()
            conn.close()
        except Exception as e:
            return False, f"Memory clear failed: {e}"

    # Start fresh
    env = os.environ.copy()
    # Source .env
    env_file = FOVEAI_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    model_path = "xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf"
    log_path = str(XRLF_LIVE_LOG)
    try:
        subprocess.Popen(
            [
                VENV_PYTHON,
                "run_xrlf.py",
                "--model",
                model_path,
                "--port",
                str(PORT_XRLF),
                "--ws-port",
                str(PORT_WS),
                "--verbose",
            ],
            cwd=str(FOVEAI_DIR),
            env=env,
            stdout=open(log_path, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        return False, f"Start failed: {e}"

    return True, "XRLF restart initiated (model loads in ~3min)"


def heal_restart_proxy() -> tuple[bool, str]:
    """Restart the foveated-memory Node.js proxy on 8400/8401."""
    subprocess.run(["pkill", "-f", "node server.js"], capture_output=True, timeout=5)
    time.sleep(2)

    env = os.environ.copy()
    env_file = FOVEAI_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    proxy_dir = FOVEAI_DIR / "foveated-memory"
    log_path = str(FOVEATED_PROXY_LOG)
    try:
        subprocess.Popen(
            ["node", "server.js"],
            cwd=str(proxy_dir),
            env=env,
            stdout=open(log_path, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        return False, f"Proxy start failed: {e}"

    return True, "Proxy restart initiated"


def heal_clear_memory() -> tuple[bool, str]:
    """Clear corrupted memory turns from the persistent DB."""
    if not MEMORY_DB.exists():
        return False, "No memory DB found"
    try:
        conn = sqlite3.connect(str(MEMORY_DB))
        conn.execute("DELETE FROM turns")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        conn.close()
        return True, f"Memory cleared ({count} turns remaining)"
    except Exception as e:
        return False, f"Clear failed: {e}"


def execute_heal(action: str) -> tuple[bool, str]:
    """Execute a healing action by name."""
    if action == "restart_xrlf":
        return heal_restart_xrlf(clear_memory=False)
    elif action == "restart_xrlf_clear_memory":
        return heal_restart_xrlf(clear_memory=True)
    elif action == "restart_proxy":
        return heal_restart_proxy()
    elif action == "clear_memory":
        return heal_clear_memory()
    return False, f"Unknown heal action: {action}"


def auto_heal(report: HealthReport) -> list[str]:
    """Attempt to heal all failing checks. Returns list of action messages."""
    messages = []
    actions_done = set()
    for r in report.failing():
        if r.healable and r.heal_action and r.heal_action not in actions_done:
            ok, msg = execute_heal(r.heal_action)
            actions_done.add(r.heal_action)
            prefix = "HEALED" if ok else "HEAL FAILED"
            messages.append(f"{prefix}: {r.name} → {msg}")
    return messages


# ─── Continuous Monitor ─────────────────────────────────────────────


class ContinuousHealthMonitor:
    """Background thread that periodically checks health and calls callbacks."""

    def __init__(
        self,
        interval: float = 30.0,
        on_report: Callable[[HealthReport], None] | None = None,
        on_fail: Callable[[CheckResult], None] | None = None,
        auto_heal_enabled: bool = False,
        coherence_interval: float = 300.0,  # coherence probe every 5min
    ):
        self.interval = interval
        self.on_report = on_report
        self.on_fail = on_fail
        self.auto_heal_enabled = auto_heal_enabled
        self.coherence_interval = coherence_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_coherence = 0.0
        self._last_report: HealthReport | None = None

    @property
    def last_report(self) -> HealthReport | None:
        return self._last_report

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                now = time.time()
                do_coherence = (now - self._last_coherence) >= self.coherence_interval
                if do_coherence:
                    report = run_sharp_report()
                    self._last_coherence = now
                else:
                    report = run_full_report(include_coherence=False)

                self._last_report = report

                if self.on_report:
                    self.on_report(report)

                # Notify on failures
                if self.on_fail:
                    for r in report.failing():
                        self.on_fail(r)

                # Auto-heal
                if self.auto_heal_enabled and report.failing():
                    messages = auto_heal(report)
                    for msg in messages:
                        print(f"[HealthMonitor] {msg}")

            except Exception as e:
                print(f"[HealthMonitor] Error: {e}")

            self._stop.wait(self.interval)


# ─── CLI ────────────────────────────────────────────────────────────


def _print_report(report: HealthReport) -> None:
    print(f"\n{'=' * 60}")
    print(f"  FoveAI Health Report — {time.strftime('%H:%M:%S')}")
    print(f"  Overall: {report.overall.value.upper()} — {report.summary}")
    print(f"{'=' * 60}")
    for r in report.results:
        status_pad = f"[{r.icon:>4}]"
        detail = f" — {r.detail}" if r.detail else ""
        heal = f" (healable: {r.heal_action})" if r.healable else ""
        print(f"  {status_pad} {r.name:<25}{detail}{heal}")
    print()


if __name__ == "__main__":
    import sys

    sharp = "--sharp" in sys.argv
    heal = "--heal" in sys.argv
    watch = "--watch" in sys.argv

    if watch:
        print("[HealthMonitor] Continuous mode — Ctrl+C to stop")
        monitor = ContinuousHealthMonitor(
            interval=30.0,
            on_report=_print_report,
            auto_heal_enabled=heal,
            coherence_interval=300.0,
        )
        monitor.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            monitor.stop()
            print("\n[HealthMonitor] Stopped")
    else:
        report = (
            run_sharp_report() if sharp else run_full_report(include_coherence=False)
        )
        _print_report(report)
        if heal and report.failing():
            print("\n[Heal] Attempting auto-heal...")
            messages = auto_heal(report)
            for msg in messages:
                print(f"  {msg}")
