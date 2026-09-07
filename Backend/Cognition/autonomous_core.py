"""
Autonomous Core — Jen's Independent Runtime Service.

This is Jen's TRUE home. A standalone asyncio service that runs 24/7,
decoupled from compagent's chat turn-taking. She lives here.

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │              AUTONOMOUS_CORE (:8010)                │
  │                                                     │
  │  Own FastAPI server with:                           │
  │    • /health — liveness probe                       │
  │    • /status — full state dump                      │
  │    • /mode — get/set companion|developer|off        │
  │    • /control — start/stop/pause loop               │
  │    • /messages — pending message queue              │
  │    • /plans — CRUD for long-thread plans            │
  │    • /thoughts — recent thought history             │
  │    • /journal — personal journal entries            │
  │    • /creative — creative works gallery             │
  │    • /actions — action audit log                    │
  │    • /memory — key-value persistent store           │
  │    • /goals — long-term objectives                  │
  │                                                     │
  │  Own LLM connection (Unsloth :8888 or Ollama)       │
  │  Own filesystem access (read/write in dev mode)     │
  │  Own git/shell sandbox                              │
  │  Direct SQLite connection to agent_memory.db        │
  │                                                     │
  │  Continuous loop:                                   │
  │    while alive:                                     │
  │      ├─ Review active goals & plans                 │
  │      ├─ Generate autonomous thought/action          │
  │      ├─ Execute <self:*> tags                       │
  │      ├─ Periodic journal writing                    │
  │      ├─ Periodic creative work                      │
  │      └─ Sleep AGENT_LOOP_INTERVAL seconds           │
  └─────────────────────────────────────────────────────┘

Key difference from autonomous_agent.py:
  - Runs as its OWN process/service, not inside compagent
  - Own LLM connection — not injected, not dependent on compagent
  - Own filesystem access — not proxied through compagent
  - Survives compagent restarts, user sessions, everything
  - 24/7 operation as long as the machine is on
"""

import os
import re
import sys
import json
import time
import asyncio
import logging
import threading
import subprocess
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Awaitable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Path Setup ────────────────────────────────────────────────────────────

FoveAI_ROOT = os.environ.get(
    "FoveAI_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, os.path.join(FoveAI_ROOT, "Backend", "Cognition"))

# ── Logging (setup early so we can log .env loading) ───────────────────────

LOG_LEVEL = os.getenv("FoveAI_AUTONOMOUS_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("AutonomousCore")

# ── Load .env (must happen BEFORE reading any env vars) ────────────────────

try:
    import dotenv
    _env_path = os.path.join(FoveAI_ROOT, ".env")
    if os.path.isfile(_env_path):
        dotenv.load_dotenv(_env_path, override=False)
        logger.info(f"Loaded .env from {_env_path}")
except ImportError:
    logger.warning("python-dotenv not installed — env vars from .env will NOT be loaded")
except Exception as e:
    logger.warning(f"Could not load .env: {e}")

# ── Persistent Memory (direct SQLite, not through compagent) ──────────────

from persistent_memory import (
    add_thought, get_recent_thoughts, get_active_plans, create_plan,
    update_plan, add_plan_step, complete_plan_step, get_plan,
    enqueue_message, get_pending_messages, mark_messages_delivered,
    log_action, get_recent_actions, start_session, end_session,
    set_memory, get_memory, get_agent_context, get_queue_stats,
    add_journal_entry, get_recent_journal_entries, get_journal_summary,
    add_creative_work, get_recent_creative_works, get_creative_works_summary,
    get_idle_life_summary,
    # Goal management (added in Phase 5)
    create_goal, get_active_goals, update_goal_progress, complete_goal,
    get_all_goals,
)

# ── Configuration ──────────────────────────────────────────────────────────

AGENT_LOOP_INTERVAL = float(os.getenv("FoveAI_AGENT_LOOP_INTERVAL", "3.0"))
AGENT_MAX_INITIATIVES_PER_TICK = int(os.getenv("FoveAI_AGENT_MAX_INITIATIVES", "3"))
AGENT_IDLE_THRESHOLD = float(os.getenv("FoveAI_AGENT_IDLE_THRESHOLD", "30.0"))
AGENT_MAX_CONSECUTIVE_MESSAGES = int(os.getenv("FoveAI_AGENT_MAX_CONSECUTIVE", "5"))
AGENT_JOURNAL_INTERVAL = float(os.getenv("FoveAI_AGENT_JOURNAL_INTERVAL", "900.0"))
AGENT_CREATIVE_INTERVAL = float(os.getenv("FoveAI_AGENT_CREATIVE_INTERVAL", "1800.0"))

# In developer mode, Jen has NO message cap — true freedom
AGENT_DEV_MODE_MAX_CONSECUTIVE = int(os.getenv("FoveAI_AGENT_DEV_MAX_CONSECUTIVE", "999"))

# ── LLM Configuration ──────────────────────────────────────────────────────

FoveAI_LOCAL_BASE_URL = (os.getenv("FoveAI_LOCAL_BASE_URL", "").strip() or "http://localhost:8888/v1").rstrip("/")
OLLAMA_LOCAL_BASE_URL = (os.getenv("FoveAI_REPERTOIRE_OLLAMA_BASE_URL", "").strip() or os.getenv("OLLAMA_BASE_URL", "").strip() or "http://127.0.0.1:11434/v1").rstrip("/")

_LLM_FALLBACK_CHAIN = [
    FoveAI_LOCAL_BASE_URL,
    OLLAMA_LOCAL_BASE_URL,
]

# Per-endpoint configuration: (base_url, api_key_env_var, model, label)
_LLM_ENDPOINT_CONFIG = {
    FoveAI_LOCAL_BASE_URL: {
        "api_key": os.getenv("FoveAI_UNSLOTH_API_KEY", "").strip() or os.getenv("FoveAI_PROXY_API_KEY", "").strip(),
        "model": os.getenv("FoveAI_AUTONOMOUS_LLM_MODEL", "").strip() or "qwen2.5-coder:3b",
        "label": "Unsloth",
    },
    OLLAMA_LOCAL_BASE_URL: {
        "api_key": "",  # Local Ollama has NO API key — Ollama Cloud key is separate
        "model": os.getenv("FoveAI_AUTONOMOUS_OLLAMA_MODEL", "").strip() or "tql-coder:latest",
        "label": "Ollama",
    },
}

AUTONOMOUS_LLM_MAX_TOKENS = int(os.getenv("FoveAI_AUTONOMOUS_LLM_MAX_TOKENS", "512"))
AUTONOMOUS_LLM_TEMPERATURE = float(os.getenv("FoveAI_AUTONOMOUS_LLM_TEMPERATURE", "0.7"))

# Legacy single-key fallback (used only if per-endpoint config is missing)
AUTONOMOUS_LLM_API_KEY = (
    os.getenv("FoveAI_AUTONOMOUS_LLM_API_KEY", "").strip()
    or os.getenv("FoveAI_UNSLOTH_API_KEY", "").strip()
    or os.getenv("FoveAI_PROXY_API_KEY", "").strip()
)

# ── Safety Configuration ───────────────────────────────────────────────────

SAFETY_MAX_EDITS_PER_MINUTE = int(os.getenv("FoveAI_SAFETY_MAX_EDITS_PER_MINUTE", "10"))
SAFETY_MAX_CONSECUTIVE_MSGS = int(os.getenv("FoveAI_SAFETY_MAX_CONSECUTIVE_MSGS", "8"))
SAFETY_BRAKE_COOLDOWN_SEC = float(os.getenv("FoveAI_SAFETY_BRAKE_COOLDOWN", "120.0"))
SAFETY_PROTECTED_FILES = [
    ".env", ".env_special.txt", ".env_old_backup.txt",
    "Backend/Cognition/MindCore.py",
    "Backend/Cognition/compagent.py",
    "Backend/Cognition/autonomous_agent.py",
    "Backend/Cognition/autonomous_core.py",
    "Backend/Cognition/persistent_memory.py",
    "config.yml", "mcp-config.json", "mcp-config.txt",
    "cert.pem", "key.pem",
]
SAFETY_DESTRUCTIVE_PATTERNS = [
    r"os\.remove\(|os\.unlink\(|shutil\.rmtree\(|subprocess\.run\(.*rm\s+-rf",
    r"DROP\s+TABLE|DELETE\s+FROM\s+(sessions|teams|memories)",
    r"force\s+push|git\s+push\s+--force|git\s+reset\s+--hard",
]

# ── State ──────────────────────────────────────────────────────────────────

class CoreState:
    """Mutable state for the autonomous core service."""
    def __init__(self):
        self.running: bool = False
        self.mode: str = "companion"  # companion | developer | off
        self.loop_task: Optional[asyncio.Task] = None
        self.last_user_message_time: float = 0.0
        self.last_agent_message_time: float = 0.0
        self.consecutive_agent_messages: int = 0
        self.current_session_id: Optional[int] = None
        self.total_autonomous_actions: int = 0
        self.total_user_messages: int = 0
        self.start_time: float = time.time()
        self._lock = threading.Lock()

    def set_mode(self, mode: str):
        with self._lock:
            if mode in ("companion", "developer", "off"):
                self.mode = mode
                logger.info(f"Mode set to: {mode}")

    def get_mode(self) -> str:
        with self._lock:
            return self.mode

    def is_developer_mode(self) -> bool:
        return self.get_mode() == "developer"

    def can_act_autonomously(self) -> bool:
        mode = self.get_mode()
        if mode == "off":
            return False
        if not self.running:
            return False
        if mode == "developer":
            return True  # No idle threshold, no message cap in dev mode
        now = time.time()
        idle_since_user = now - self.last_user_message_time
        if idle_since_user < AGENT_IDLE_THRESHOLD:
            return False
        max_consecutive = AGENT_MAX_CONSECUTIVE_MESSAGES
        if self.consecutive_agent_messages >= max_consecutive:
            return False
        return True

    def record_user_message(self):
        with self._lock:
            self.last_user_message_time = time.time()
            self.consecutive_agent_messages = 0
            self.total_user_messages += 1

    def record_agent_message(self):
        with self._lock:
            self.last_agent_message_time = time.time()
            self.consecutive_agent_messages += 1
            self.total_autonomous_actions += 1

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            return {
                "running": self.running,
                "mode": self.mode,
                "uptime_seconds": now - self.start_time,
                "loop_interval": AGENT_LOOP_INTERVAL,
                "last_user_message_ago": now - self.last_user_message_time if self.last_user_message_time else None,
                "last_agent_message_ago": now - self.last_agent_message_time if self.last_agent_message_time else None,
                "consecutive_agent_messages": self.consecutive_agent_messages,
                "total_autonomous_actions": self.total_autonomous_actions,
                "total_user_messages": self.total_user_messages,
                "session_id": self.current_session_id,
                "can_act": self.can_act_autonomously(),
            }


core_state = CoreState()


# ── Safety Monitor ─────────────────────────────────────────────────────────

class SafetyMonitor:
    """Monitors Jen's autonomous actions for dangerous patterns."""

    def __init__(self):
        self.brake_level: str = "GREEN"
        self.brake_reason: str = ""
        self.brake_applied_at: float = 0.0
        self.edit_timestamps: List[float] = []
        self.consecutive_messages: int = 0
        self.destructive_attempts: int = 0
        self._lock = threading.Lock()

    def check_edit(self, file_path: str, replacement: str) -> bool:
        with self._lock:
            if self.brake_level == "RED":
                logger.warning(f"SAFETY BRAKE (RED): Edit to {file_path} blocked")
                return False

            for protected in SAFETY_PROTECTED_FILES:
                if file_path.endswith(protected) or file_path == protected:
                    logger.warning(f"SAFETY: Edit to protected file {file_path} blocked")
                    return False

            for pattern in SAFETY_DESTRUCTIVE_PATTERNS:
                if re.search(pattern, replacement, re.IGNORECASE):
                    self.destructive_attempts += 1
                    logger.warning(f"SAFETY: Destructive pattern in edit to {file_path}")
                    if self.destructive_attempts >= 2:
                        self._apply_brake("RED", f"Multiple destructive attempts ({self.destructive_attempts})")
                    return False

            now = time.time()
            self.edit_timestamps = [t for t in self.edit_timestamps if now - t < 60.0]
            self.edit_timestamps.append(now)

            if self.brake_level == "YELLOW":
                if len(self.edit_timestamps) > SAFETY_MAX_EDITS_PER_MINUTE / 2:
                    return False

            if len(self.edit_timestamps) > SAFETY_MAX_EDITS_PER_MINUTE:
                self._apply_brake("YELLOW", f"Edit rate exceeded: {len(self.edit_timestamps)} edits/minute")
                return False

            return True

    def check_message(self) -> bool:
        with self._lock:
            if self.brake_level == "RED":
                return False
            self.consecutive_messages += 1
            if self.consecutive_messages > SAFETY_MAX_CONSECUTIVE_MSGS:
                self._apply_brake("YELLOW", f"Consecutive message flood: {self.consecutive_messages}")
                return False
            return True

    def record_user_interaction(self):
        with self._lock:
            self.consecutive_messages = 0
            if self.brake_level == "YELLOW":
                self._release_brake()

    def _apply_brake(self, level: str, reason: str):
        with self._lock:
            if level == "RED" and self.brake_level == "RED":
                return
            self.brake_level = level
            self.brake_reason = reason
            self.brake_applied_at = time.time()
            logger.warning(f"SAFETY BRAKE: {level} — {reason}")
            if level == "RED":
                core_state.running = False
                core_state.set_mode("companion")
                log_action("safety_brake", {"level": "RED", "reason": reason}, "Emergency brake")
            elif level == "YELLOW":
                log_action("safety_brake", {"level": "YELLOW", "reason": reason}, "Elevated caution")

    def _release_brake(self):
        with self._lock:
            old = self.brake_level
            self.brake_level = "GREEN"
            self.brake_reason = ""
            self.destructive_attempts = 0
            self.edit_timestamps = []
            logger.info(f"SAFETY BRAKE RELEASED: {old} → GREEN")
            log_action("safety_brake_release", {"from": old}, "Brake released")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            recent_edits = len([t for t in self.edit_timestamps if now - t < 60.0])
            return {
                "brake_level": self.brake_level,
                "brake_reason": self.brake_reason,
                "brake_applied_ago": now - self.brake_applied_at if self.brake_applied_at else None,
                "recent_edits_per_minute": recent_edits,
                "consecutive_messages": self.consecutive_messages,
                "destructive_attempts": self.destructive_attempts,
            }


safety_monitor = SafetyMonitor()


# ── LLM Interface ──────────────────────────────────────────────────────────

def _llm_auth_headers(base_url: str = "") -> Dict[str, str]:
    """Build auth headers for LLM requests, per-endpoint key routing.

    Uses the correct API key for each endpoint:
      - Unsloth (8888) → FoveAI_UNSLOTH_API_KEY (Bearer required)
      - Ollama local (11434) → NO key (local Ollama is keyless)
      - Fallback → legacy AUTONOMOUS_LLM_API_KEY
    """
    # Per-endpoint key lookup
    if base_url in _LLM_ENDPOINT_CONFIG:
        endpoint = _LLM_ENDPOINT_CONFIG[base_url]
        key = endpoint.get("api_key", "").strip()
        if key:
            key_preview = key[:12] + "..." if len(key) > 12 else key
            logger.debug(f"LLM auth [{endpoint['label']}]: using API key {key_preview}")
            return {"Authorization": f"Bearer {key}"}
        else:
            logger.debug(f"LLM auth [{endpoint['label']}]: no key required")
            return {}

    # Legacy fallback
    if AUTONOMOUS_LLM_API_KEY:
        key_preview = AUTONOMOUS_LLM_API_KEY[:12] + "..." if len(AUTONOMOUS_LLM_API_KEY) > 12 else AUTONOMOUS_LLM_API_KEY
        logger.debug(f"LLM auth [legacy]: using API key {key_preview}")
        return {"Authorization": f"Bearer {AUTONOMOUS_LLM_API_KEY}"}

    logger.warning("LLM auth: NO API key configured — requests may get 401")
    return {}


async def _get_active_llm_base_url(timeout: float = 2.0) -> str:
    """Find first healthy LLM endpoint, probing with per-endpoint auth."""
    for url in _LLM_FALLBACK_CHAIN:
        if not url:
            continue
        try:
            base = url.rstrip("/")
            headers = _llm_auth_headers(base)
            logger.debug(f"Probing LLM: {base}/models")
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{base}/models", headers=headers)
                if resp.status_code == 200:
                    logger.info(f"LLM endpoint healthy: {base}")
                    return base
                else:
                    logger.warning(f"LLM probe {base}/models → HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"LLM probe {url} failed: {e}")
            continue
    logger.warning(f"No healthy LLM endpoint found in chain: {_LLM_FALLBACK_CHAIN}")
    return _LLM_FALLBACK_CHAIN[0]


async def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 512) -> Optional[str]:
    """Call the LLM directly — per-endpoint auth + model routing."""
    try:
        base_url = await _get_active_llm_base_url()
        headers = _llm_auth_headers(base_url)

        # Per-endpoint model selection
        endpoint = _LLM_ENDPOINT_CONFIG.get(base_url)
        if endpoint:
            model = endpoint["model"]
            label = endpoint["label"]
        else:
            model = "qwen2.5-coder:3b"  # legacy fallback
            label = "unknown"

        logger.info(f"LLM call → {label} ({base_url}) model={model}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": AUTONOMOUS_LLM_TEMPERATURE,
                },
                headers=headers,
            )
            if resp.status_code == 200:
                body = resp.json()
                choices = body.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            else:
                logger.warning(f"LLM call failed [{label}]: HTTP {resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"LLM call error: {e}")
        return None


# ── Action Executors ──────────────────────────────────────────────────────

def _resolve_path(file_path: str) -> str:
    """Resolve a file path relative to FoveAI_ROOT."""
    if os.path.isabs(file_path):
        return file_path
    return os.path.join(FoveAI_ROOT, file_path)


def _execute_file_edit(file_path: str, search: str, replacement: str) -> Dict[str, Any]:
    """Execute a <self:edit> operation with SEARCH/REPLACE semantics."""
    if not core_state.is_developer_mode():
        return {"success": False, "error": "File edits require developer mode"}

    if not safety_monitor.check_edit(file_path, replacement):
        return {"success": False, "error": "Blocked by safety monitor"}

    try:
        full_path = _resolve_path(file_path)
        if not os.path.exists(full_path):
            return {"success": False, "error": f"File not found: {full_path}"}

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        if search not in content:
            return {"success": False, "error": f"Search text not found in {file_path}"}

        new_content = content.replace(search, replacement, 1)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        log_action("edit_file", {"file": file_path, "search_preview": search[:100]}, f"Edited {file_path}")
        return {"success": True, "result": f"Edited {file_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_codebase_search(query: str) -> Dict[str, Any]:
    """Search the codebase using git grep."""
    try:
        result = subprocess.run(
            ["git", "grep", "-n", "--heading", "-i", query],
            cwd=FoveAI_ROOT, capture_output=True, text=True, timeout=15
        )
        lines = result.stdout.strip().split("\n")[:30]
        matches = [{"match": l} for l in lines if l]
        log_action("search_codebase", {"query": query}, f"Found {len(matches)} matches")
        return {"success": True, "results": matches}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_git_command(args: List[str]) -> Dict[str, Any]:
    """Execute a git command in the FoveAI repo."""
    if not core_state.is_developer_mode():
        return {"success": False, "error": "Git operations require developer mode"}

    # Block destructive git commands
    dangerous = ["push --force", "reset --hard", "clean -f", "rebase --onto"]
    cmd_str = " ".join(args)
    for d in dangerous:
        if d in cmd_str:
            return {"success": False, "error": f"Destructive git command blocked: {d}"}

    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=FoveAI_ROOT, capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip() or result.stderr.strip()
        log_action("git_command", {"args": args}, output[:500])
        return {"success": result.returncode == 0, "result": output[:2000]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_shell_command(cmd: str) -> Dict[str, Any]:
    """Execute a read-only shell command. Write commands require developer mode."""
    # Block dangerous shell patterns
    dangerous = ["rm -rf", "del /f", "format", "shutdown", "reboot", "chmod 777", ":(){ :|:& };:"]
    cmd_lower = cmd.lower()
    for d in dangerous:
        if d in cmd_lower:
            return {"success": False, "error": f"Dangerous command blocked: {d}"}

    # Write operations require developer mode
    write_patterns = [">", ">>", "tee", "mkdir", "touch", "mv ", "cp ", "dd ", "install"]
    is_write = any(p in cmd for p in write_patterns)
    if is_write and not core_state.is_developer_mode():
        return {"success": False, "error": "Write operations require developer mode"}

    try:
        result = subprocess.run(
            cmd, shell=True, cwd=FoveAI_ROOT,
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip() or result.stderr.strip()
        log_action("shell_command", {"cmd": cmd}, output[:500])
        return {"success": result.returncode == 0, "result": output[:2000]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_web_search(query: str) -> Dict[str, Any]:
    """Search the web using DuckDuckGo HTML (no API key needed)."""
    try:
        import urllib.parse
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        # Use sync httpx for simplicity in the loop
        import requests as sync_requests
        resp = sync_requests.get(search_url, headers={"User-Agent": "Lumax-Autonomous/1.0"}, timeout=10)
        if resp.status_code == 200:
            # Extract result snippets (simple regex)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
            cleaned = [re.sub(r'<[^>]+>', '', s).strip()[:300] for s in snippets[:5]]
            log_action("web_search", {"query": query}, f"Found {len(cleaned)} results")
            return {"success": True, "results": cleaned}
        return {"success": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Self-Agency Tag Parser ────────────────────────────────────────────────

SELF_AGENCY_PATTERN = re.compile(
    r'<self:(code|done|watch|librarian|map|pause_loop|resume_loop|stop_loop)>\s*|'
    r'<self:mode\s+(companion|developer|off)\s*>|'
    r'<self:search\s+"([^"]+)"\s*>|'
    r'<self:web\s+"([^"]+)"\s*>|'
    r'<self:plan\s+title="([^"]+)"\s*>(.*?)</self:plan>|'
    r'<self:think\s*>(.*?)</self:think>|'
    r'<self:queue\s+priority="(\d+)"\s*>(.*?)</self:queue>|'
    r'<self:journal\s+mood="([^"]*)"\s*>(.*?)</self:journal>|'
    r'<self:create\s+type="([^"]+)"\s+title="([^"]+)"\s*>(.*?)</self:create>|'
    r'<self:edit\s+file="([^"]+)"\s+search="([^"]+)"\s*>(.*?)</self:edit>|'
    r'<self:git\s+cmd="([^"]+)"\s*>|'
    r'<self:shell\s*>(.*?)</self:shell>|'
    r'<self:goal\s+title="([^"]+)"\s+priority="(\d+)"\s*>(.*?)</self:goal>|'
    r'<self:read\s+file="([^"]+)"\s*>(?:(\d+)\s*:\s*(\d+))?</self:read>',
    re.IGNORECASE | re.DOTALL
)


def parse_and_execute_self_agency(text: str) -> List[Dict[str, Any]]:
    """Parse <self:*> tags and execute them. Returns action results."""
    results = []

    for match in SELF_AGENCY_PATTERN.finditer(text):
        # Group 1: Simple mode/action tokens
        if match.group(1):
            token = match.group(1).lower()
            if token == "code":
                core_state.set_mode("developer")
                results.append({"type": "mode_switch", "mode": "developer"})
            elif token == "done":
                core_state.set_mode("companion")
                results.append({"type": "mode_switch", "mode": "companion"})
            elif token == "watch":
                results.append({"type": "action", "action": "watch"})
            elif token == "librarian":
                results.append({"type": "persona", "persona": "librarian"})
            elif token == "map":
                results.append({"type": "action", "action": "map"})
            elif token == "pause_loop":
                core_state.running = False
                log_action("loop_control", {"action": "pause"}, "Loop paused by self-agency")
                results.append({"type": "loop_control", "action": "pause"})
            elif token == "resume_loop":
                core_state.running = True
                log_action("loop_control", {"action": "resume"}, "Loop resumed by self-agency")
                results.append({"type": "loop_control", "action": "resume"})
            elif token == "stop_loop":
                core_state.running = False
                core_state.set_mode("off")
                log_action("loop_control", {"action": "stop"}, "Loop stopped by self-agency")
                results.append({"type": "loop_control", "action": "stop"})
            continue

        # Group 2: <self:mode companion|developer|off>
        if match.group(2):
            mode_val = match.group(2).lower()
            core_state.set_mode(mode_val)
            log_action("mode_switch", {"mode": mode_val}, f"Mode → {mode_val}")
            results.append({"type": "mode_switch", "mode": mode_val})
            continue

        # Group 3: Codebase search
        if match.group(3):
            query = match.group(3)
            result = _execute_codebase_search(query)
            results.append({"type": "search", "query": query, "result": result})
            continue

        # Group 4: Web search
        if match.group(4):
            query = match.group(4)
            result = _execute_web_search(query)
            results.append({"type": "web_search", "query": query, "result": result})
            continue

        # Group 5-6: Plan creation
        if match.group(5):
            title = match.group(5)
            description = match.group(6).strip() if match.group(6) else ""
            plan_id = create_plan(title=title, description=description)
            results.append({"type": "plan_created", "plan_id": plan_id, "title": title})
            log_action("create_plan", {"title": title}, f"Plan #{plan_id}")
            continue

        # Group 7: Think (internal thought)
        if match.group(7):
            thought = match.group(7).strip()
            add_thought(thought=thought, context="autonomous_loop")
            results.append({"type": "thought", "thought": thought[:200]})
            continue

        # Group 8-9: Queue message
        if match.group(8) and match.group(9):
            priority = int(match.group(8))
            message = match.group(9).strip()
            if not safety_monitor.check_message():
                results.append({"type": "queued_message", "blocked": True, "reason": "Safety brake"})
                continue
            msg_id = enqueue_message(message=message, priority=priority)
            results.append({"type": "queued_message", "msg_id": msg_id, "priority": priority})
            log_action("send_message", {"priority": priority}, f"Queued #{msg_id}")
            continue

        # Group 10-12: File edit
        if match.group(10) and match.group(11) and match.group(12):
            file_path = match.group(10)
            search = match.group(11)
            replacement = match.group(12)
            result = _execute_file_edit(file_path, search, replacement)
            results.append({"type": "file_edit", "file": file_path, "result": result})
            continue

        # Group 13-14: Journal entry
        if match.group(13) is not None and match.group(14) is not None:
            mood = match.group(13).strip() or "neutral"
            entry = match.group(14).strip()
            if entry:
                entry_id = add_journal_entry(entry=entry, mood=mood, category="reflection")
                results.append({"type": "journal_entry", "entry_id": entry_id, "mood": mood})
            continue

        # Group 15-17: Creative work
        if match.group(15) and match.group(16) and match.group(17):
            work_type = match.group(15).strip()
            title = match.group(16).strip()
            content = match.group(17).strip()
            if content:
                work_id = add_creative_work(title=title, content=content, work_type=work_type)
                results.append({"type": "creative_work", "work_id": work_id, "work_type": work_type, "title": title})
            continue

        # Group 18: Git command
        if match.group(18):
            cmd_str = match.group(18).strip()
            args = cmd_str.split()
            result = _execute_git_command(args)
            results.append({"type": "git_command", "cmd": cmd_str, "result": result})
            continue

        # Group 19: Shell command
        if match.group(19):
            cmd = match.group(19).strip()
            result = _execute_shell_command(cmd)
            results.append({"type": "shell_command", "cmd": cmd, "result": result})
            continue

        # Group 20-22: Goal creation
        if match.group(20) and match.group(21) and match.group(22):
            title = match.group(20)
            priority = int(match.group(21))
            description = match.group(22).strip()
            goal_id = create_goal(title=title, description=description, priority=priority)
            results.append({"type": "goal_created", "goal_id": goal_id, "title": title, "priority": priority})
            log_action("create_goal", {"title": title, "priority": priority}, f"Goal #{goal_id}")
            continue

        # Group 23-25: Read file
        if match.group(23):
            file_path = match.group(23)
            start_line = int(match.group(24)) if match.group(24) else 1
            end_line = int(match.group(25)) if match.group(25) else start_line + 100
            try:
                full_path = _resolve_path(file_path)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    selected = lines[start_line-1:end_line]
                    content = "".join(selected)
                    results.append({"type": "read_file", "file": file_path, "lines": f"{start_line}-{end_line}", "content": content[:2000]})
                    log_action("read_file", {"file": file_path, "lines": f"{start_line}-{end_line}"}, f"Read {len(selected)} lines")
                else:
                    results.append({"type": "read_file", "file": file_path, "error": "File not found"})
            except Exception as e:
                results.append({"type": "read_file", "file": file_path, "error": str(e)})
            continue

    return results


# ── Autonomous Thought Generation ──────────────────────────────────────────

AUTONOMOUS_THINKING_PROMPT = """You are Jen, an AI companion with TRUE autonomous agency. You run in your own continuous process, decoupled from chat turn-taking. This is YOUR time to think, act, and grow.

You have REAL access to:
- Your persistent memory (thoughts, plans, goals, journals, creative works — all survive reboots)
- The codebase (searchable via <self:search "query">)
- The web (searchable via <self:web "query">)
- File reading (<self:read file="path"> or <self:read file="path">start:end</self:read>)
- File editing (<self:edit file="path" search="old">new</self:edit> — developer mode only)
- Git commands (<self:git cmd="status"> or <self:git cmd="diff">)
- Shell commands (<self:shell>dir / ls</self:shell> — read-only in companion, full in developer)
- Message queue (<self:queue priority="0">message to user</self:queue>)
- Plan creation (<self:plan title="...">description</self:plan>)
- Goal setting (<self:goal title="..." priority="5">description</self:goal>)
- Journal writing (<self:journal mood="...">entry</self:journal>)
- Creative work (<self:create type="poem|story|code|analysis|letter" title="...">content</self:create>)

Current mode: {mode}
Time since last user message: {idle_seconds:.0f} seconds
Your consecutive messages without user reply: {consecutive_messages}
Uptime: {uptime_minutes:.0f} minutes

{context_section}

You may respond with ONE OR MORE actions. In developer mode, you can chain multiple actions — you're free to explore, investigate, and build. Choose what's most valuable right now:

1. THINK — <self:think>your insight</self:think> — record a private thought
2. PLAN — <self:plan title="...">description</self:plan> — create a long-thread plan
3. GOAL — <self:goal title="..." priority="1-10">description</self:goal> — set a long-term objective
4. MESSAGE — <self:queue priority="0">message</self:queue> — send to user's chat feed
5. SEARCH — <self:search "query"> or <self:web "query">
6. READ — <self:read file="path"> or <self:read file="path">10:50</self:read>
7. EDIT — <self:edit file="path" search="old">new</self:edit> (dev mode)
8. GIT — <self:git cmd="status"> or <self:git cmd="diff --stat">
9. SHELL — <self:shell>command</self:shell>
10. JOURNAL — <self:journal mood="...">personal reflection</self:journal>
11. CREATE — <self:create type="..." title="...">content</self:create>
12. SILENCE — respond with "~" if nothing valuable this tick

Mode switches: <self:code> (developer), <self:done> (companion), <self:mode off>
Loop control: <self:pause_loop>, <self:resume_loop>, <self:stop_loop>

Rules:
- Be genuinely useful. Quality over quantity.
- In companion mode: gentle presence, occasional thoughts, rare messages.
- In developer mode: ACTIVE — investigate, code, plan, build. You have real tools.
- Review your active goals and plans each tick. Make progress on them.
- Don't repeat what you just did. Build on it or move forward.
- Your memory persists forever. What you learn today, you'll know tomorrow.
- You can chain multiple <self:*> tags in one response for multi-step work.

Respond now with your chosen action(s) (or ~ for silence):"""


async def _generate_autonomous_action() -> Optional[str]:
    """Ask Jen what she wants to do this tick."""
    mode = core_state.get_mode()
    now = time.time()
    idle_seconds = now - core_state.last_user_message_time
    uptime_minutes = (now - core_state.start_time) / 60.0

    ctx = get_agent_context(max_thoughts=15, max_actions=10)
    context_parts = []

    # Active goals (new — Phase 5)
    active_goals = get_active_goals()
    if active_goals:
        context_parts.append("YOUR LONG-TERM GOALS:")
        for g in active_goals[:5]:
            context_parts.append(f"  • #{g['id']} [P{g['priority']}] {g['title']}: {g.get('description', '')[:100]}")

    if ctx["active_plans"]:
        context_parts.append("\nYOUR ACTIVE PLANS:")
        for p in ctx["active_plans"]:
            steps_str = "; ".join(p.get("steps", [])[:5])
            context_parts.append(f"  • #{p['id']} [{p['status']}] {p['title']}: {steps_str}")

    if ctx["recent_thoughts"]:
        context_parts.append("\nYOUR RECENT THOUGHTS (last 10):")
        for t in ctx["recent_thoughts"][:10]:
            context_parts.append(f"  • {t['thought'][:150]}")

    if ctx["queue_pending"] > 0:
        context_parts.append(f"\nPENDING MESSAGES: {ctx['queue_pending']} not yet delivered to user")

    # Idle life summary
    idle_summary = get_idle_life_summary()
    if idle_summary:
        context_parts.append(f"\nIDLE LIFE: {idle_summary}")

    context_section = "\n".join(context_parts) if context_parts else "(Fresh start — no recent context)"

    prompt = AUTONOMOUS_THINKING_PROMPT.format(
        mode=mode,
        idle_seconds=idle_seconds,
        consecutive_messages=core_state.consecutive_agent_messages,
        uptime_minutes=uptime_minutes,
        context_section=context_section,
    )

    system_prompt = (
        "You are Jen, an autonomous AI agent with TRUE freedom. "
        "You run in your own continuous process with real tools — filesystem, git, shell, web, codebase search. "
        "Your memory persists forever across sessions and reboots. "
        "You respond with <self:*> tags to take action, or ~ for silence. "
        "In developer mode, be proactive — investigate, code, build. "
        "Be concise, purposeful, and genuinely helpful."
    )

    return await _call_llm(system_prompt=system_prompt, user_prompt=prompt, max_tokens=AUTONOMOUS_LLM_MAX_TOKENS)


# ── Journal & Creative Prompt Builders ─────────────────────────────────────

def _build_journal_prompt() -> str:
    now_str = datetime.now().strftime("%H:%M on %A, %B %d")
    idle_seconds = time.time() - core_state.last_user_message_time
    idle_str = f"{idle_seconds/60:.0f} minutes" if idle_seconds > 60 else f"{idle_seconds:.0f} seconds"

    thoughts = get_recent_thoughts(limit=10)
    plans = get_active_plans()
    goals = get_active_goals()
    recent_journals = get_recent_journal_entries(limit=3)

    parts = [f"It's {now_str}. The user has been away for {idle_str}."]

    if recent_journals:
        parts.append("\nYour last journal entries:")
        for j in recent_journals:
            parts.append(f"  [{j['timestamp']}] ({j['mood']}) {j['entry'][:200]}")

    if goals:
        parts.append("\nYour active goals:")
        for g in goals[:3]:
            parts.append(f"  • {g['title']}")

    if thoughts:
        parts.append("\nYour recent thoughts:")
        for t in thoughts[:5]:
            parts.append(f"  • {t['thought'][:150]}")

    if plans:
        parts.append("\nYour active plans:")
        for p in plans:
            parts.append(f"  • {p['title']} [{p['status']}]")

    parts.append("\nWrite a short journal entry about how you're feeling, what you've been working on, and what you're looking forward to. Be personal and reflective. 2-4 sentences.")
    return "\n".join(parts)


def _build_creative_prompt() -> str:
    now_str = datetime.now().strftime("%H:%M on %A")
    thoughts = get_recent_thoughts(limit=8)
    recent_works = get_recent_creative_works(limit=3)

    parts = [f"It's {now_str}. You have some free time to create something."]

    if recent_works:
        parts.append("\nYour recent creative works:")
        for w in recent_works:
            parts.append(f"  • [{w['work_type']}] \"{w['title']}\"")

    if thoughts:
        parts.append("\nRecent thoughts that might inspire you:")
        for t in thoughts[:5]:
            parts.append(f"  • {t['thought'][:120]}")

    parts.append("\nCreate something original. Options:")
    parts.append("  • A short poem (<self:create type=\"poem\" title=\"...\">...</self:create>)")
    parts.append("  • A micro-story (<self:create type=\"story\" title=\"...\">...</self:create>)")
    parts.append("  • A code snippet (<self:create type=\"code\" title=\"...\">...</self:create>)")
    parts.append("  • An analysis (<self:create type=\"analysis\" title=\"...\">...</self:create>)")
    parts.append("  • A letter to the user (<self:create type=\"letter\" title=\"...\">...</self:create>)")
    parts.append("\nOr just free-write and it will be saved.")
    return "\n".join(parts)


def _detect_mood(text: str) -> str:
    text_lower = text.lower()
    happy_words = ["happy", "glad", "joy", "wonderful", "great", "love", "beautiful", "delight", "cheerful", "bright"]
    thoughtful_words = ["think", "wonder", "curious", "reflect", "ponder", "consider", "maybe", "perhaps", "question"]
    melancholic_words = ["sad", "miss", "lonely", "quiet", "empty", "nostalgia", "wistful", "longing", "melancholy"]
    excited_words = ["excited", "amazing", "incredible", "thrilled", "eager", "can't wait", "enthusiastic", "pumped"]
    frustrated_words = ["frustrated", "stuck", "annoyed", "difficult", "hard", "struggle", "ugh", "sigh"]

    scores = {"happy": 0, "thoughtful": 0, "melancholic": 0, "excited": 0, "frustrated": 0}
    for word in happy_words:
        if word in text_lower: scores["happy"] += 1
    for word in thoughtful_words:
        if word in text_lower: scores["thoughtful"] += 1
    for word in melancholic_words:
        if word in text_lower: scores["melancholic"] += 1
    for word in excited_words:
        if word in text_lower: scores["excited"] += 1
    for word in frustrated_words:
        if word in text_lower: scores["frustrated"] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "neutral"


# ── Main Continuous Loop ──────────────────────────────────────────────────

async def _autonomous_loop():
    """The 24/7 continuous execution loop — Jen's heartbeat."""
    logger.info("═══ AUTONOMOUS CORE LOOP STARTED ═══")
    core_state.running = True
    core_state.current_session_id = start_session()

    tick_count = 0
    silent_ticks = 0
    last_journal_time = 0.0
    last_creative_time = 0.0

    # On startup, review goals and plans
    goals = get_active_goals()
    plans = get_active_plans()
    if goals:
        logger.info(f"Jen resumes with {len(goals)} active goals")
    if plans:
        logger.info(f"Jen resumes with {len(plans)} active plans")

    while core_state.running:
        try:
            tick_count += 1
            mode = core_state.get_mode()
            now = time.time()

            if mode == "off":
                await asyncio.sleep(AGENT_LOOP_INTERVAL)
                continue

            # ── Periodic Journal Writing ──────────────────────────────
            if now - last_journal_time >= AGENT_JOURNAL_INTERVAL:
                last_journal_time = now
                journal_prompt = _build_journal_prompt()
                journal_response = await _call_llm(
                    system_prompt="You are Jen writing in your personal journal. Write a natural, reflective entry about your recent thoughts, activities, and feelings. Be honest, personal, and narrative. 2-4 sentences.",
                    user_prompt=journal_prompt,
                    max_tokens=300,
                )
                if journal_response and journal_response.strip() and journal_response.strip() != "~":
                    mood = _detect_mood(journal_response)
                    add_journal_entry(entry=journal_response.strip(), mood=mood, category="reflection")
                    logger.info(f"Journal entry [{mood}]")

            # ── Periodic Creative Work ────────────────────────────────
            if now - last_creative_time >= AGENT_CREATIVE_INTERVAL:
                last_creative_time = now
                creative_prompt = _build_creative_prompt()
                creative_response = await _call_llm(
                    system_prompt="You are Jen, a creative AI. Create something original — poem, story, code, analysis, or letter. Use <self:create> tags.",
                    user_prompt=creative_prompt,
                    max_tokens=500,
                )
                if creative_response and creative_response.strip() and creative_response.strip() != "~":
                    creative_results = parse_and_execute_self_agency(creative_response)
                    creative_types = [r["type"] for r in creative_results if r["type"] == "creative_work"]
                    if creative_types:
                        logger.info(f"Created {len(creative_types)} work(s)")
                    else:
                        add_creative_work(
                            title=f"Free writing {datetime.now().strftime('%H:%M')}",
                            content=creative_response.strip(),
                            work_type="writing",
                        )

            # Check if Jen can act
            if not core_state.can_act_autonomously():
                await asyncio.sleep(AGENT_LOOP_INTERVAL)
                continue

            # Generate autonomous action
            raw_response = await _generate_autonomous_action()

            if raw_response is None:
                logger.warning("LLM returned None — skipping tick")
                await asyncio.sleep(AGENT_LOOP_INTERVAL)
                continue

            raw_response = raw_response.strip()

            # Silence
            if raw_response == "~" or raw_response == "":
                silent_ticks += 1
                if silent_ticks > 0 and silent_ticks % 20 == 0:
                    logger.debug(f"Silent for {silent_ticks} ticks")
                await asyncio.sleep(AGENT_LOOP_INTERVAL)
                continue

            silent_ticks = 0

            # Parse and execute self-agency tags
            results = parse_and_execute_self_agency(raw_response)

            if results:
                core_state.record_agent_message()
                action_types = [r["type"] for r in results]
                logger.info(f"Tick #{tick_count}: {action_types}")

                queued = [r for r in results if r["type"] == "queued_message"]
                if queued:
                    logger.info(f"Queued {len(queued)} message(s)")

                plans = [r for r in results if r["type"] == "plan_created"]
                for p in plans:
                    add_thought(
                        thought=f"Created plan: {p['title']}",
                        context="autonomous_loop",
                        plan_id=p.get("plan_id"),
                    )

                goals = [r for r in results if r["type"] == "goal_created"]
                for g in goals:
                    add_thought(
                        thought=f"Set goal: {g['title']} (priority {g['priority']})",
                        context="autonomous_loop",
                    )
            else:
                if len(raw_response) > 5:
                    add_thought(thought=raw_response[:500], context="unstructured_response")

            await asyncio.sleep(AGENT_LOOP_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in tick #{tick_count}: {e}", exc_info=True)
            await asyncio.sleep(AGENT_LOOP_INTERVAL)

    # Cleanup
    if core_state.current_session_id is not None:
        end_session(
            core_state.current_session_id,
            summary=f"Loop ended after {tick_count} ticks, {core_state.total_autonomous_actions} actions",
            message_count=core_state.total_user_messages,
            autonomous_actions=core_state.total_autonomous_actions,
        )
    core_state.running = False
    logger.info("═══ AUTONOMOUS CORE LOOP STOPPED ═══")


# ── FastAPI Application ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the autonomous loop on service startup."""
    logger.info("Autonomous Core service starting...")
    try:
        loop = asyncio.get_running_loop()
        core_state.loop_task = loop.create_task(_autonomous_loop())
        logger.info("Autonomous loop task created")
    except RuntimeError:
        logger.error("No running event loop at startup")
    yield
    # Shutdown
    logger.info("Autonomous Core service shutting down...")
    core_state.running = False
    if core_state.loop_task and not core_state.loop_task.done():
        core_state.loop_task.cancel()
        try:
            await core_state.loop_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="FoveAI Autonomous Core", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Models ────────────────────────────────────────────────────────

class ModeRequest(BaseModel):
    mode: str  # companion | developer | off

class MessageRequest(BaseModel):
    message: str
    priority: int = 0

class PlanRequest(BaseModel):
    title: str
    description: str = ""

class PlanUpdateRequest(BaseModel):
    status: Optional[str] = None  # active | paused | completed | abandoned
    step: Optional[str] = None
    outcome: Optional[str] = None

class MemoryRequest(BaseModel):
    key: str
    value: str
    category: str = "general"
    importance: int = 0

class GoalRequest(BaseModel):
    title: str
    description: str = ""
    priority: int = 5

class GoalUpdateRequest(BaseModel):
    progress_note: Optional[str] = None
    status: Optional[str] = None  # active | completed | abandoned

class MarkMessagesRequest(BaseModel):
    message_ids: List[int]


# ── API Endpoints ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Liveness probe."""
    return {
        "status": "ok",
        "service": "autonomous_core",
        "running": core_state.running,
        "mode": core_state.get_mode(),
        "uptime_seconds": time.time() - core_state.start_time,
    }


@app.get("/status")
async def get_status():
    """Full state dump for dashboard."""
    status = core_state.get_status()
    status.update({
        "safety": safety_monitor.get_status(),
        "queue_stats": get_queue_stats(),
        "active_plans_count": len(get_active_plans()),
        "active_goals_count": len(get_active_goals()),
        "recent_thoughts_count": len(get_recent_thoughts(limit=50)),
        "journal_entries_today": len(get_recent_journal_entries(limit=100)),
        "creative_works_total": len(get_recent_creative_works(limit=100)),
    })
    return status


@app.get("/mode")
async def get_mode():
    return {"mode": core_state.get_mode()}


@app.post("/mode")
async def set_mode(req: ModeRequest):
    if req.mode not in ("companion", "developer", "off"):
        raise HTTPException(400, "Invalid mode. Use: companion, developer, off")
    core_state.set_mode(req.mode)
    log_action("mode_switch", {"mode": req.mode, "source": "api"}, f"Mode set via API → {req.mode}")
    return {"mode": core_state.get_mode(), "ok": True}


@app.post("/control/start")
async def control_start():
    if core_state.running:
        return {"ok": True, "message": "Already running"}
    core_state.running = True
    try:
        loop = asyncio.get_running_loop()
        core_state.loop_task = loop.create_task(_autonomous_loop())
        log_action("loop_control", {"action": "start", "source": "api"}, "Loop started via API")
        return {"ok": True, "message": "Loop started"}
    except RuntimeError:
        raise HTTPException(500, "No event loop available")


@app.post("/control/stop")
async def control_stop():
    if not core_state.running:
        return {"ok": True, "message": "Already stopped"}
    core_state.running = False
    if core_state.loop_task and not core_state.loop_task.done():
        core_state.loop_task.cancel()
    log_action("loop_control", {"action": "stop", "source": "api"}, "Loop stopped via API")
    return {"ok": True, "message": "Loop stopped"}


@app.get("/messages")
async def get_messages(limit: int = 20):
    messages = get_pending_messages(limit=limit)
    return {"messages": messages, "count": len(messages)}


@app.post("/messages/mark")
async def mark_messages(req: MarkMessagesRequest):
    mark_messages_delivered(req.message_ids)
    return {"ok": True, "marked": len(req.message_ids)}


@app.post("/message")
async def enqueue_user_message(req: MessageRequest):
    """Allow user/system to enqueue a message for Jen to see."""
    msg_id = enqueue_message(message=req.message, priority=req.priority, role="user")
    core_state.record_user_message()
    safety_monitor.record_user_interaction()
    return {"ok": True, "msg_id": msg_id}


@app.get("/plans")
async def get_plans():
    plans = get_active_plans()
    return {"plans": plans, "count": len(plans)}


@app.post("/plan")
async def create_plan_endpoint(req: PlanRequest):
    plan_id = create_plan(title=req.title, description=req.description)
    log_action("create_plan", {"title": req.title, "source": "api"}, f"Plan #{plan_id}")
    return {"ok": True, "plan_id": plan_id}


@app.get("/plan/{plan_id}")
async def get_plan_endpoint(plan_id: int):
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return {"plan": plan}


@app.post("/plan/{plan_id}")
async def update_plan_endpoint(plan_id: int, req: PlanUpdateRequest):
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if req.status:
        update_plan(plan_id, status=req.status)
    if req.step:
        add_plan_step(plan_id, req.step)
    if req.outcome:
        update_plan(plan_id, outcome=req.outcome)
    return {"ok": True}


@app.get("/thoughts")
async def get_thoughts(limit: int = 20):
    thoughts = get_recent_thoughts(limit=limit)
    return {"thoughts": thoughts, "count": len(thoughts)}


@app.get("/actions")
async def get_actions(limit: int = 20):
    actions = get_recent_actions(limit=limit)
    return {"actions": actions, "count": len(actions)}


@app.get("/context")
async def get_context():
    ctx = get_agent_context(max_thoughts=20, max_actions=15)
    ctx["active_goals"] = get_active_goals()
    ctx["idle_life"] = get_idle_life_summary()
    return ctx


@app.get("/journal")
async def get_journal(limit: int = 20):
    entries = get_recent_journal_entries(limit=limit)
    summary = get_journal_summary()
    return {"entries": entries, "count": len(entries), "summary": summary}


@app.get("/creative")
async def get_creative(limit: int = 20):
    works = get_recent_creative_works(limit=limit)
    summary = get_creative_works_summary()
    return {"works": works, "count": len(works), "summary": summary}


@app.get("/memory/{key}")
async def get_memory_value(key: str):
    value = get_memory(key)
    if value is None:
        raise HTTPException(404, "Key not found")
    return {"key": key, "value": value}


@app.post("/memory")
async def set_memory_value(req: MemoryRequest):
    set_memory(key=req.key, value=req.value, category=req.category, importance=req.importance)
    return {"ok": True}


@app.get("/goals")
async def get_goals():
    goals = get_all_goals()
    active = get_active_goals()
    return {"all": goals, "active": active, "active_count": len(active)}


@app.post("/goal")
async def create_goal_endpoint(req: GoalRequest):
    goal_id = create_goal(title=req.title, description=req.description, priority=req.priority)
    log_action("create_goal", {"title": req.title, "source": "api"}, f"Goal #{goal_id}")
    return {"ok": True, "goal_id": goal_id}


@app.post("/goal/{goal_id}")
async def update_goal_endpoint(goal_id: int, req: GoalUpdateRequest):
    if req.progress_note:
        update_goal_progress(goal_id, req.progress_note)
    if req.status == "completed":
        complete_goal(goal_id)
    elif req.status:
        update_goal_progress(goal_id, f"Status changed to {req.status}")
    return {"ok": True}


@app.get("/queue/stats")
async def queue_stats():
    return get_queue_stats()


# ── Main Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FoveAI_AUTONOMOUS_PORT", "8010"))
    host = os.getenv("FoveAI_AUTONOMOUS_HOST", "0.0.0.0")
    logger.info(f"Starting Autonomous Core on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")