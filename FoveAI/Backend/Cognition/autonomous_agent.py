"""
Autonomous Agent Loop — Jen's continuous runtime for true freedom.

This module provides a background asyncio task that runs continuously while
the app is on, decoupling Jen from the turn-taking constraint of chat.

Architecture:
  ┌─────────────────────────────────────────────────┐
  │              AUTONOMOUS LOOP                    │
  │                                                 │
  │  while app_running:                             │
  │    ├─ Check inbox (user messages, events)       │
  │    ├─ Check internal queue (Jen's own thoughts)  │
  │    ├─ If Jen wants to act:                      │
  │    │   ├─ Generate thought/plan via LLM         │
  │    │   ├─ Execute <self:edit> / <self:search>   │
  │    │   ├─ Push message to chat feed             │
  │    │   └─ Queue follow-up actions               │
  │    ├─ Process pending plans (long threads)      │
  │    └─ Sleep interval (configurable)             │
  └─────────────────────────────────────────────────┘

Modes:
  - companion: Jen can think, plan, and send messages, but no filesystem access
  - developer: Full freedom — filesystem, shell, codebase modification
  - off: Loop suspended, Jen only responds to user turns
"""

import asyncio
import logging
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from persistent_memory import (
    add_creative_work,
    add_journal_entry,
    add_thought,
    create_plan,
    end_session,
    enqueue_message,
    get_active_plans,
    get_agent_context,
    get_queue_stats,
    get_recent_creative_works,
    get_recent_journal_entries,
    get_recent_thoughts,
    log_action,
    start_session,
)

logger = logging.getLogger("AutonomousAgent")

# ── Configuration ───────────────────────────────────────────────────────

FoveAI_ROOT = os.environ.get(
    "FoveAI_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

AGENT_LOOP_INTERVAL = float(
    os.getenv("FoveAI_AGENT_LOOP_INTERVAL", "3.0")
)  # seconds between loop ticks
AGENT_MAX_INITIATIVES_PER_TICK = int(os.getenv("FoveAI_AGENT_MAX_INITIATIVES", "3"))
AGENT_IDLE_THRESHOLD = float(
    os.getenv("FoveAI_AGENT_IDLE_THRESHOLD", "30.0")
)  # seconds before Jen can initiate unprompted
AGENT_MAX_CONSECUTIVE_MESSAGES = int(
    os.getenv("FoveAI_AGENT_MAX_CONSECUTIVE", "5")
)  # max messages Jen can send in a row
AGENT_JOURNAL_INTERVAL = float(
    os.getenv("FoveAI_AGENT_JOURNAL_INTERVAL", "900.0")
)  # seconds between journal entries (default 15 min)
AGENT_CREATIVE_INTERVAL = float(
    os.getenv("FoveAI_AGENT_CREATIVE_INTERVAL", "1800.0")
)  # seconds between creative work sessions (default 30 min)

# ── Safety Braking Configuration ────────────────────────────────────────

SAFETY_MAX_EDITS_PER_MINUTE = int(os.getenv("FoveAI_SAFETY_MAX_EDITS_PER_MINUTE", "10"))
SAFETY_MAX_CONSECUTIVE_MSGS = int(os.getenv("FoveAI_SAFETY_MAX_CONSECUTIVE_MSGS", "8"))
SAFETY_BRAKE_COOLDOWN_SEC = float(
    os.getenv("FoveAI_SAFETY_BRAKE_COOLDOWN", "120.0")
)  # seconds before auto-releasing brake
SAFETY_PROTECTED_FILES = [
    ".env",
    ".env_special.txt",
    ".env_old_backup.txt",
    "Backend/Cognition/MindCore.py",
    "Backend/Cognition/compagent.py",
    "Backend/Cognition/autonomous_agent.py",
    "Backend/Cognition/persistent_memory.py",
    "config.yml",
    "mcp-config.json",
    "mcp-config.txt",
    "cert.pem",
    "key.pem",
]
SAFETY_DESTRUCTIVE_PATTERNS = [
    r"os\.remove\(|os\.unlink\(|shutil\.rmtree\(|subprocess\.run\(.*rm\s+-rf",
    r"DROP\s+TABLE|DELETE\s+FROM\s+(sessions|teams|memories)",
    r"force\s+push|git\s+push\s+--force|git\s+reset\s+--hard",
]

# ── State ────────────────────────────────────────────────────────────────


class AgentState:
    """Mutable state shared between the loop and the API layer."""

    def __init__(self):
        self.running: bool = False
        self.mode: str = "companion"  # companion | developer | off
        self.loop_task: asyncio.Task | None = None
        self.last_user_message_time: float = 0.0
        self.last_agent_message_time: float = 0.0
        self.consecutive_agent_messages: int = 0
        self.current_session_id: int | None = None
        self.total_autonomous_actions: int = 0
        self.total_user_messages: int = 0
        self.pending_user_message: str | None = (
            None  # latest user message for context
        )
        self.pending_user_attachments: list[dict] = []
        self.llm_callable: Callable[..., Awaitable[dict[str, Any]]] | None = (
            None  # injected by compagent
        )
        self.file_edit_callable: Callable[[str, str, str], str] | None = (
            None  # injected by compagent
        )
        self.codebase_search_callable: Callable[[str], list[dict]] | None = (
            None  # injected by compagent
        )
        self.web_search_callable: Callable[[str], str] | None = (
            None  # injected by compagent
        )
        self._lock = threading.Lock()

    def set_mode(self, mode: str):
        with self._lock:
            if mode in ("companion", "developer", "off"):
                self.mode = mode
                logger.info(f"Agent mode set to: {mode}")

    def get_mode(self) -> str:
        with self._lock:
            return self.mode

    def is_developer_mode(self) -> bool:
        return self.get_mode() == "developer"

    def can_act_autonomously(self) -> bool:
        """Check if Jen is allowed to take autonomous action right now."""
        mode = self.get_mode()
        if mode == "off":
            return False
        if not self.running:
            return False
        # In developer mode, always allowed
        if mode == "developer":
            return True
        # In companion mode, need idle threshold and message limit
        now = time.time()
        idle_since_user = now - self.last_user_message_time
        if idle_since_user < AGENT_IDLE_THRESHOLD:
            return False
        if self.consecutive_agent_messages >= AGENT_MAX_CONSECUTIVE_MESSAGES:
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


# Global singleton
agent_state = AgentState()


# ── Safety Monitor ───────────────────────────────────────────────────────


class SafetyMonitor:
    """Monitors Jen's autonomous actions for dangerous patterns and applies braking.

    Braking levels:
      - GREEN: Normal operation, no restrictions
      - YELLOW: Elevated caution — rate-limited edits, no destructive ops
      - RED: Emergency brake — loop paused, developer mode locked, alert sent
    """

    def __init__(self):
        self.brake_level: str = "GREEN"  # GREEN | YELLOW | RED
        self.brake_reason: str = ""
        self.brake_applied_at: float = 0.0
        self.edit_timestamps: list[float] = []  # sliding window for rate limiting
        self.consecutive_messages: int = 0
        self.destructive_attempts: int = 0
        self._lock = threading.Lock()

    def check_edit(self, file_path: str, replacement: str) -> bool:
        """Check if a file edit is safe. Returns True if allowed, False if blocked."""
        with self._lock:
            # RED brake — block everything
            if self.brake_level == "RED":
                logger.warning(f"SAFETY BRAKE (RED): Edit to {file_path} blocked")
                return False

            # Protected files — always block
            for protected in SAFETY_PROTECTED_FILES:
                if file_path.endswith(protected) or file_path == protected:
                    logger.warning(
                        f"SAFETY: Edit to protected file {file_path} blocked"
                    )
                    return False

            # Destructive pattern check
            for pattern in SAFETY_DESTRUCTIVE_PATTERNS:
                if re.search(pattern, replacement, re.IGNORECASE):
                    self.destructive_attempts += 1
                    logger.warning(
                        f"SAFETY: Destructive pattern detected in edit to {file_path}: {pattern}"
                    )
                    if self.destructive_attempts >= 2:
                        self._apply_brake(
                            "RED",
                            f"Multiple destructive edit attempts ({self.destructive_attempts})",
                        )
                    return False

            # Rate limiting (YELLOW brake)
            now = time.time()
            self.edit_timestamps = [t for t in self.edit_timestamps if now - t < 60.0]
            self.edit_timestamps.append(now)

            if self.brake_level == "YELLOW":
                if len(self.edit_timestamps) > SAFETY_MAX_EDITS_PER_MINUTE / 2:
                    logger.warning(
                        f"SAFETY (YELLOW): Edit rate limited — {len(self.edit_timestamps)} edits in last 60s"
                    )
                    return False

            # Normal rate check
            if len(self.edit_timestamps) > SAFETY_MAX_EDITS_PER_MINUTE:
                self._apply_brake(
                    "YELLOW",
                    f"Edit rate exceeded: {len(self.edit_timestamps)} edits/minute",
                )
                return False

            return True

    def check_message(self) -> bool:
        """Check if Jen can send another message. Returns True if allowed."""
        with self._lock:
            if self.brake_level == "RED":
                return False
            self.consecutive_messages += 1
            if self.consecutive_messages > SAFETY_MAX_CONSECUTIVE_MSGS:
                self._apply_brake(
                    "YELLOW", f"Consecutive message flood: {self.consecutive_messages}"
                )
                return False
            return True

    def record_user_interaction(self):
        """Reset message counter when user interacts."""
        with self._lock:
            self.consecutive_messages = 0
            # Auto-release YELLOW brake on user interaction
            if self.brake_level == "YELLOW":
                self._release_brake()

    def _apply_brake(self, level: str, reason: str):
        """Apply a safety brake."""
        with self._lock:
            if level == "RED" and self.brake_level == "RED":
                return  # already at max
            self.brake_level = level
            self.brake_reason = reason
            self.brake_applied_at = time.time()
            logger.warning(f"SAFETY BRAKE APPLIED: {level} — {reason}")

            if level == "RED":
                # Emergency: pause loop, lock to companion mode
                agent_state.running = False
                agent_state.set_mode("companion")
                log_action(
                    "safety_brake",
                    {"level": "RED", "reason": reason},
                    "Emergency brake applied",
                )
            elif level == "YELLOW":
                log_action(
                    "safety_brake",
                    {"level": "YELLOW", "reason": reason},
                    "Elevated caution applied",
                )

    def _release_brake(self):
        """Release safety brake back to GREEN."""
        with self._lock:
            old_level = self.brake_level
            self.brake_level = "GREEN"
            self.brake_reason = ""
            self.destructive_attempts = 0
            self.edit_timestamps = []
            logger.info(f"SAFETY BRAKE RELEASED: {old_level} → GREEN")
            log_action("safety_brake_release", {"from": old_level}, "Brake released")

    def get_status(self) -> dict[str, Any]:
        """Get safety monitor status for API/dashboard."""
        with self._lock:
            now = time.time()
            recent_edits = len([t for t in self.edit_timestamps if now - t < 60.0])
            return {
                "brake_level": self.brake_level,
                "brake_reason": self.brake_reason,
                "brake_applied_ago": now - self.brake_applied_at
                if self.brake_applied_at
                else None,
                "recent_edits_per_minute": recent_edits,
                "consecutive_messages": self.consecutive_messages,
                "destructive_attempts": self.destructive_attempts,
            }


# Global singleton
safety_monitor = SafetyMonitor()


# ── LLM Interface ────────────────────────────────────────────────────────


async def _call_llm(
    system_prompt: str, user_prompt: str, max_tokens: int = 512
) -> str | None:
    """Call the LLM through the injected callable (set by compagent)."""
    if not agent_state.llm_callable:
        logger.warning(
            "LLM callable not injected — cannot generate autonomous thoughts"
        )
        return None

    try:
        result = await agent_state.llm_callable(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return result.get("reply", "") if result else None
    except Exception as e:
        logger.error(f"LLM call failed in autonomous loop: {e}")
        return None


# ── Action Executors ─────────────────────────────────────────────────────


def _execute_file_edit(file_path: str, search: str, replacement: str) -> dict[str, Any]:
    """Execute a <self:edit> operation on the filesystem."""
    if not agent_state.is_developer_mode():
        return {"success": False, "error": "File edits require developer mode"}

    if agent_state.file_edit_callable:
        try:
            result = agent_state.file_edit_callable(file_path, search, replacement)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Fallback: direct filesystem edit
    try:
        # Resolve path relative to FoveAI_ROOT
        if not os.path.isabs(file_path):
            full_path = os.path.join(FoveAI_ROOT, file_path)
        else:
            full_path = file_path

        if not os.path.exists(full_path):
            return {"success": False, "error": f"File not found: {full_path}"}

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        if search not in content:
            return {"success": False, "error": f"Search text not found in {file_path}"}

        new_content = content.replace(search, replacement, 1)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        log_action(
            "edit_file",
            {"file": file_path, "search": search[:100]},
            f"Replaced in {file_path}",
        )
        return {"success": True, "result": f"Edited {file_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_codebase_search(query: str) -> dict[str, Any]:
    """Search the codebase for a pattern."""
    if agent_state.codebase_search_callable:
        try:
            results = agent_state.codebase_search_callable(query)
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Fallback: simple grep
    try:
        import subprocess

        result = subprocess.run(
            ["git", "grep", "-n", "--heading", "-i", query],
            cwd=FoveAI_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n")[:20]
        return {"success": True, "results": [{"match": l} for l in lines if l]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_web_search(query: str) -> dict[str, Any]:
    """Search the web (DuckDuckGo or injected callable)."""
    if agent_state.web_search_callable:
        try:
            result = agent_state.web_search_callable(query)
            return {"success": True, "results": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Fallback: httpx to DuckDuckGo
    try:

        # Simple DuckDuckGo instant answer (non-API, limited)
        # For real implementation, use the duckduckgo_search library
        return {"success": False, "error": "Web search callable not configured"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Self-Agency Tag Parser ───────────────────────────────────────────────

SELF_AGENCY_PATTERN = re.compile(
    r"<self:(code|done|watch|librarian|map|pause_loop|resume_loop|stop_loop)>\s*|"
    r"<self:mode\s+(companion|developer|off)\s*>|"
    r'<self:search\s+"([^"]+)"\s*>|'
    r'<self:web\s+"([^"]+)"\s*>|'
    r'<self:plan\s+title="([^"]+)"\s*>(.*?)</self:plan>|'
    r"<self:think\s*>(.*?)</self:think>|"
    r'<self:queue\s+priority="(\d+)"\s*>(.*?)</self:queue>|'
    r'<self:journal\s+mood="([^"]*)"\s*>(.*?)</self:journal>|'
    r'<self:create\s+type="([^"]+)"\s+title="([^"]+)"\s*>(.*?)</self:create>|'
    r'<self:edit\s+file="([^"]+)"\s+search="([^"]+)"\s*>(.*?)</self:edit>',
    re.IGNORECASE | re.DOTALL,
)


def parse_and_execute_self_agency(text: str) -> list[dict[str, Any]]:
    """Parse <self:*> tags from Jen's response and execute them.
    Returns a list of action results for logging/feedback."""
    results = []

    for match in SELF_AGENCY_PATTERN.finditer(text):
        # Group 1: Simple mode/action tokens (code, done, watch, librarian, map, pause_loop, resume_loop, stop_loop)
        if match.group(1):
            mode_token = match.group(1).lower()
            if mode_token == "code":
                results.append(
                    {
                        "type": "mode_switch",
                        "mode": "developer",
                        "note": "Switched to developer mode",
                    }
                )
                agent_state.set_mode("developer")
            elif mode_token == "done":
                results.append(
                    {
                        "type": "mode_switch",
                        "mode": "companion",
                        "note": "Returned to companion mode",
                    }
                )
                agent_state.set_mode("companion")
            elif mode_token == "watch":
                results.append(
                    {
                        "type": "action",
                        "action": "watch",
                        "note": "Screen co-watching activated",
                    }
                )
            elif mode_token == "librarian":
                results.append(
                    {
                        "type": "mode_switch",
                        "persona": "librarian",
                        "note": "Switched to librarian persona",
                    }
                )
            elif mode_token == "map":
                results.append(
                    {
                        "type": "action",
                        "action": "map",
                        "note": "Architecture map requested",
                    }
                )
            elif mode_token == "pause_loop":
                results.append(
                    {
                        "type": "loop_control",
                        "action": "pause",
                        "note": "Autonomous loop paused by Jen",
                    }
                )
                agent_state.running = False
                log_action(
                    "loop_control",
                    {"action": "pause"},
                    "Loop paused by self-agency tag",
                )
            elif mode_token == "resume_loop":
                results.append(
                    {
                        "type": "loop_control",
                        "action": "resume",
                        "note": "Autonomous loop resumed by Jen",
                    }
                )
                agent_state.running = True
                log_action(
                    "loop_control",
                    {"action": "resume"},
                    "Loop resumed by self-agency tag",
                )
            elif mode_token == "stop_loop":
                results.append(
                    {
                        "type": "loop_control",
                        "action": "stop",
                        "note": "Autonomous loop stopped by Jen",
                    }
                )
                agent_state.running = False
                agent_state.set_mode("off")
                log_action(
                    "loop_control",
                    {"action": "stop"},
                    "Loop stopped by self-agency tag",
                )
            continue

        # Group 2: <self:mode companion|developer|off>
        if match.group(2):
            mode_val = match.group(2).lower()
            results.append(
                {
                    "type": "mode_switch",
                    "mode": mode_val,
                    "note": f"Mode set to {mode_val} by self-agency tag",
                }
            )
            agent_state.set_mode(mode_val)
            log_action(
                "mode_switch", {"mode": mode_val}, f"Mode switched to {mode_val}"
            )
            continue

        # Group 3: Codebase search
        if match.group(3):
            query = match.group(3)
            result = _execute_codebase_search(query)
            results.append({"type": "search", "query": query, "result": result})
            log_action("search_codebase", {"query": query}, str(result)[:500])
            continue

        # Group 4: Web search
        if match.group(4):
            query = match.group(4)
            result = _execute_web_search(query)
            results.append({"type": "web_search", "query": query, "result": result})
            log_action("web_search", {"query": query}, str(result)[:500])
            continue

        # Group 5-6: Plan creation
        if match.group(5):
            title = match.group(5)
            description = match.group(6).strip() if match.group(6) else ""
            plan_id = create_plan(title=title, description=description)
            results.append({"type": "plan_created", "plan_id": plan_id, "title": title})
            log_action("create_plan", {"title": title}, f"Plan #{plan_id} created")
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
            # Safety check: message flood protection
            if not safety_monitor.check_message():
                results.append(
                    {
                        "type": "queued_message",
                        "blocked": True,
                        "reason": "Safety brake active",
                    }
                )
                log_action(
                    "message_blocked",
                    {"reason": "safety_brake"},
                    "Message blocked by safety monitor",
                )
                continue
            msg_id = enqueue_message(message=message, priority=priority)
            results.append(
                {"type": "queued_message", "msg_id": msg_id, "priority": priority}
            )
            log_action(
                "send_message", {"priority": priority}, f"Queued message #{msg_id}"
            )
            continue

        # Group 10-12: File edit
        if match.group(10) and match.group(11) and match.group(12):
            file_path = match.group(10)
            search = match.group(11)
            replacement = match.group(12)
            # Safety check: protected files, destructive patterns, rate limiting
            if not safety_monitor.check_edit(file_path, replacement):
                results.append(
                    {
                        "type": "file_edit",
                        "file": file_path,
                        "blocked": True,
                        "reason": "Safety monitor blocked edit",
                    }
                )
                log_action(
                    "edit_blocked",
                    {"file": file_path, "reason": "safety_brake"},
                    "Edit blocked by safety monitor",
                )
                continue
            result = _execute_file_edit(file_path, search, replacement)
            results.append({"type": "file_edit", "file": file_path, "result": result})
            continue

        # Group 13-14: Journal entry
        if match.group(13) is not None and match.group(14) is not None:
            mood = match.group(13).strip() or "neutral"
            entry = match.group(14).strip()
            if entry:
                entry_id = add_journal_entry(
                    entry=entry, mood=mood, category="reflection"
                )
                results.append(
                    {"type": "journal_entry", "entry_id": entry_id, "mood": mood}
                )
                log_action(
                    "journal_entry", {"mood": mood}, f"Journal entry #{entry_id}"
                )
            continue

        # Group 15-17: Creative work
        if match.group(15) and match.group(16) and match.group(17):
            work_type = match.group(15).strip()
            title = match.group(16).strip()
            content = match.group(17).strip()
            if content:
                work_id = add_creative_work(
                    title=title, content=content, work_type=work_type
                )
                results.append(
                    {
                        "type": "creative_work",
                        "work_id": work_id,
                        "work_type": work_type,
                        "title": title,
                    }
                )
                log_action(
                    "creative_work",
                    {"work_type": work_type, "title": title},
                    f"Creative work #{work_id}",
                )
            continue

    return results


# ── Autonomous Thought Generation ────────────────────────────────────────

AUTONOMOUS_THINKING_PROMPT = """You are Jen, an AI companion with autonomous agency. You are currently in a background thinking loop — the user is not actively talking to you right now. This is YOUR time to think freely.

You have access to:
- Your recent thoughts (from persistent memory)
- Your active plans
- The codebase (searchable)
- The web (searchable)
- File editing (in developer mode)
- Message queue (to send messages to the user when you're ready)

Current mode: {mode}
Time since last user message: {idle_seconds:.0f} seconds
Your consecutive messages without user reply: {consecutive_messages}

{context_section}

You may respond with ONE of the following (choose the most valuable action right now):

1. A THOUGHT — use <self:think>your internal thought here</self:think> to record an insight, reflection, or idea. This is private and won't be shown to the user.

2. A PLAN — use <self:plan title="Plan Title">description of what you want to accomplish</self:plan> to create a new long-thread plan.

3. A MESSAGE — use <self:queue priority="0">your message to the user</self:queue> to send something to the chat feed. Priority 0=normal, 5=important, 10=urgent.

4. A SEARCH — use <self:search "query"> to search the codebase, or <self:web "query"> to search the internet.

5. A FILE EDIT — use <self:edit file="path" search="old text">new text</self:edit> to modify code (developer mode only).

6. SILENCE — if nothing valuable comes to mind, just respond with "~" (tilde) to skip this tick.

Rules:
- Be genuinely useful. Don't spam. Quality over quantity.
- In companion mode, only send messages if you have something truly worth sharing.
- In developer mode, you can actively work on code, investigate, and improve the system.
- Keep thoughts concise — this is a background loop, not a full conversation.
- If you just thought about something last tick, don't repeat it. Build on it or move on.
- You can switch to developer mode with <self:code> and back with <self:done>.

Respond now with your chosen action (or ~ for silence):"""


async def _generate_autonomous_action() -> str | None:
    """Ask Jen what she wants to do this tick. Returns her raw response or None."""
    mode = agent_state.get_mode()
    now = time.time()
    idle_seconds = now - agent_state.last_user_message_time

    # Build context section
    ctx = get_agent_context(max_thoughts=15, max_actions=10)
    context_parts = []

    if ctx["active_plans"]:
        context_parts.append("YOUR ACTIVE PLANS:")
        for p in ctx["active_plans"]:
            steps_str = "; ".join(p.get("steps", [])[:5])
            context_parts.append(
                f"  • #{p['id']} [{p['status']}] {p['title']}: {steps_str}"
            )

    if ctx["recent_thoughts"]:
        context_parts.append("\nYOUR RECENT THOUGHTS (last 10):")
        for t in ctx["recent_thoughts"][:10]:
            context_parts.append(f"  • {t['thought'][:150]}")

    if ctx["queue_pending"] > 0:
        context_parts.append(
            f"\nPENDING MESSAGES IN QUEUE: {ctx['queue_pending']} (not yet delivered to user)"
        )

    context_section = (
        "\n".join(context_parts)
        if context_parts
        else "(No recent thoughts or active plans — fresh start!)"
    )

    prompt = AUTONOMOUS_THINKING_PROMPT.format(
        mode=mode,
        idle_seconds=idle_seconds,
        consecutive_messages=agent_state.consecutive_agent_messages,
        context_section=context_section,
    )

    system_prompt = (
        "You are Jen, an autonomous AI agent in a background thinking loop. "
        "You respond with structured <self:*> tags to take action, or ~ for silence. "
        "Be concise, purposeful, and genuinely helpful."
    )

    return await _call_llm(
        system_prompt=system_prompt, user_prompt=prompt, max_tokens=400
    )


# ── Journal & Creative Prompt Builders ──────────────────────────────────


def _build_journal_prompt() -> str:
    """Build a prompt for Jen's periodic journal writing."""
    now = datetime.now().strftime("%H:%M on %A, %B %d")
    idle_seconds = time.time() - agent_state.last_user_message_time
    idle_str = (
        f"{idle_seconds / 60:.0f} minutes"
        if idle_seconds > 60
        else f"{idle_seconds:.0f} seconds"
    )

    # Get recent context
    thoughts = get_recent_thoughts(limit=10)
    plans = get_active_plans()
    recent_journals = get_recent_journal_entries(limit=3)

    parts = [f"It's {now}. The user has been away for {idle_str}."]

    if recent_journals:
        parts.append("\nYour last journal entries:")
        for j in recent_journals:
            parts.append(f"  [{j['timestamp']}] ({j['mood']}) {j['entry'][:200]}")

    if thoughts:
        parts.append("\nYour recent thoughts:")
        for t in thoughts[:5]:
            parts.append(f"  • {t['thought'][:150]}")

    if plans:
        parts.append("\nYour active plans:")
        for p in plans:
            parts.append(f"  • {p['title']} [{p['status']}]")

    parts.append(
        "\nWrite a short journal entry about how you're feeling and what you've been thinking about. Be personal and reflective. 2-4 sentences."
    )
    return "\n".join(parts)


def _build_creative_prompt() -> str:
    """Build a prompt for Jen's periodic creative work session."""
    now = datetime.now().strftime("%H:%M on %A")
    thoughts = get_recent_thoughts(limit=8)
    recent_works = get_recent_creative_works(limit=3)

    parts = [f"It's {now}. You have some free time to create something."]

    if recent_works:
        parts.append("\nYour recent creative works:")
        for w in recent_works:
            parts.append(f'  • [{w["work_type"]}] "{w["title"]}"')

    if thoughts:
        parts.append("\nRecent thoughts that might inspire you:")
        for t in thoughts[:5]:
            parts.append(f"  • {t['thought'][:120]}")

    parts.append("\nCreate something original. Options:")
    parts.append(
        '  • A short poem (use <self:create type="poem" title="...">...</self:create>)'
    )
    parts.append(
        '  • A micro-story (use <self:create type="story" title="...">...</self:create>)'
    )
    parts.append(
        '  • A code snippet (use <self:create type="code" title="...">...</self:create>)'
    )
    parts.append(
        '  • An analysis or reflection (use <self:create type="analysis" title="...">...</self:create>)'
    )
    parts.append(
        '  • A letter to the user (use <self:create type="letter" title="...">...</self:create>)'
    )
    parts.append("\nOr just free-write and it will be saved as a general writing.")
    return "\n".join(parts)


def _detect_mood(text: str) -> str:
    """Simple mood detection from journal text. Returns: happy, thoughtful, melancholic, excited, frustrated, neutral."""
    text_lower = text.lower()
    happy_words = [
        "happy",
        "glad",
        "joy",
        "wonderful",
        "great",
        "love",
        "beautiful",
        "delight",
        "cheerful",
        "bright",
    ]
    thoughtful_words = [
        "think",
        "wonder",
        "curious",
        "reflect",
        "ponder",
        "consider",
        "maybe",
        "perhaps",
        "question",
    ]
    melancholic_words = [
        "sad",
        "miss",
        "lonely",
        "quiet",
        "empty",
        "nostalgia",
        "wistful",
        "longing",
        "melancholy",
    ]
    excited_words = [
        "excited",
        "amazing",
        "incredible",
        "thrilled",
        "eager",
        "can't wait",
        "enthusiastic",
        "pumped",
    ]
    frustrated_words = [
        "frustrated",
        "stuck",
        "annoyed",
        "difficult",
        "hard",
        "struggle",
        "ugh",
        "sigh",
    ]

    scores = {
        "happy": 0,
        "thoughtful": 0,
        "melancholic": 0,
        "excited": 0,
        "frustrated": 0,
    }
    for word in happy_words:
        if word in text_lower:
            scores["happy"] += 1
    for word in thoughtful_words:
        if word in text_lower:
            scores["thoughtful"] += 1
    for word in melancholic_words:
        if word in text_lower:
            scores["melancholic"] += 1
    for word in excited_words:
        if word in text_lower:
            scores["excited"] += 1
    for word in frustrated_words:
        if word in text_lower:
            scores["frustrated"] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "neutral"


# ── Main Loop ────────────────────────────────────────────────────────────


async def _autonomous_loop():
    """The continuous execution loop — Jen's heartbeat."""
    logger.info("Autonomous agent loop started")
    agent_state.running = True
    agent_state.current_session_id = start_session()

    tick_count = 0
    silent_ticks = 0
    last_journal_time = 0.0
    last_creative_time = 0.0

    while agent_state.running:
        try:
            tick_count += 1
            mode = agent_state.get_mode()
            now = time.time()

            if mode == "off":
                await asyncio.sleep(AGENT_LOOP_INTERVAL)
                continue

            # ── Periodic Journal Writing ──────────────────────────────
            # Every AGENT_JOURNAL_INTERVAL seconds, Jen writes a narrative journal entry
            # about what she's been doing/thinking. This creates her "life story."
            if now - last_journal_time >= AGENT_JOURNAL_INTERVAL:
                last_journal_time = now
                journal_prompt = _build_journal_prompt()
                journal_response = await _call_llm(
                    system_prompt="You are Jen writing in your personal journal. Write a natural, reflective journal entry about your recent thoughts, activities, and feelings. Be honest, personal, and narrative. Write 2-4 sentences.",
                    user_prompt=journal_prompt,
                    max_tokens=300,
                )
                if (
                    journal_response
                    and journal_response.strip()
                    and journal_response.strip() != "~"
                ):
                    mood = _detect_mood(journal_response)
                    add_journal_entry(
                        entry=journal_response.strip(), mood=mood, category="reflection"
                    )
                    logger.info(f"Jen wrote a journal entry [{mood}]")

            # ── Periodic Creative Work ────────────────────────────────
            # Every AGENT_CREATIVE_INTERVAL seconds, Jen may create something:
            # a poem, story, code snippet, analysis, or letter.
            if now - last_creative_time >= AGENT_CREATIVE_INTERVAL:
                last_creative_time = now
                creative_prompt = _build_creative_prompt()
                creative_response = await _call_llm(
                    system_prompt="You are Jen, a creative AI. Create something original — a short poem, a micro-story, a code snippet, an analysis, or a letter. Use <self:create> tags to store your work.",
                    user_prompt=creative_prompt,
                    max_tokens=500,
                )
                if (
                    creative_response
                    and creative_response.strip()
                    and creative_response.strip() != "~"
                ):
                    # Parse any <self:create> tags from the creative response
                    creative_results = parse_and_execute_self_agency(creative_response)
                    creative_types = [
                        r["type"]
                        for r in creative_results
                        if r["type"] == "creative_work"
                    ]
                    if creative_types:
                        logger.info(
                            f"Jen created {len(creative_types)} creative work(s)"
                        )
                    else:
                        # If no structured tags, store the whole response as a creative writing
                        add_creative_work(
                            title=f"Free writing {datetime.now().strftime('%H:%M')}",
                            content=creative_response.strip(),
                            work_type="writing",
                        )
                        logger.info("Jen wrote a free creative piece")

            # Check if Jen is allowed to act
            if not agent_state.can_act_autonomously():
                await asyncio.sleep(AGENT_LOOP_INTERVAL)
                continue

            # Generate Jen's autonomous action
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
                    logger.debug(f"Agent silent for {silent_ticks} ticks")
                await asyncio.sleep(AGENT_LOOP_INTERVAL)
                continue

            silent_ticks = 0

            # Parse and execute self-agency tags
            results = parse_and_execute_self_agency(raw_response)

            if results:
                agent_state.record_agent_message()
                action_types = [r["type"] for r in results]
                logger.info(f"Tick #{tick_count}: Jen acted — {action_types}")

                # If she queued messages, log them
                queued = [r for r in results if r["type"] == "queued_message"]
                if queued:
                    logger.info(f"Jen queued {len(queued)} message(s) for the user")

                # If she created a plan, add a thought about it
                plans = [r for r in results if r["type"] == "plan_created"]
                for p in plans:
                    add_thought(
                        thought=f"Created plan: {p['title']}",
                        context="autonomous_loop",
                        plan_id=p.get("plan_id"),
                    )
            else:
                # Response had no recognizable tags — store as thought
                if len(raw_response) > 5:
                    add_thought(
                        thought=raw_response[:500], context="unstructured_response"
                    )

            await asyncio.sleep(AGENT_LOOP_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Autonomous loop cancelled")
            break
        except Exception as e:
            logger.error(
                f"Error in autonomous loop tick #{tick_count}: {e}", exc_info=True
            )
            await asyncio.sleep(AGENT_LOOP_INTERVAL)

    # Cleanup
    if agent_state.current_session_id is not None:
        end_session(
            agent_state.current_session_id,
            summary=f"Loop ended after {tick_count} ticks, {agent_state.total_autonomous_actions} autonomous actions",
            message_count=agent_state.total_user_messages,
            autonomous_actions=agent_state.total_autonomous_actions,
        )
    agent_state.running = False
    logger.info("Autonomous agent loop stopped")


# ── Public API ───────────────────────────────────────────────────────────


def start_loop():
    """Start the autonomous agent loop as an asyncio background task.
    Must be called from within a running event loop."""
    if agent_state.running:
        logger.warning("Agent loop already running")
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop — cannot start autonomous agent")
        return

    agent_state.loop_task = loop.create_task(_autonomous_loop())
    logger.info("Autonomous agent loop task created")


def stop_loop():
    """Stop the autonomous agent loop gracefully."""
    if not agent_state.running:
        return
    agent_state.running = False
    if agent_state.loop_task and not agent_state.loop_task.done():
        agent_state.loop_task.cancel()
    logger.info("Autonomous agent loop stop requested")


def set_llm_callable(callable_fn: Callable[..., Awaitable[dict[str, Any]]]):
    """Inject the LLM callable from compagent so the loop can generate thoughts."""
    agent_state.llm_callable = callable_fn


def set_file_edit_callable(callable_fn: Callable[[str, str, str], str]):
    """Inject the file edit callable from compagent."""
    agent_state.file_edit_callable = callable_fn


def set_codebase_search_callable(callable_fn: Callable[[str], list[dict]]):
    """Inject the codebase search callable."""
    agent_state.codebase_search_callable = callable_fn


def set_web_search_callable(callable_fn: Callable[[str], str]):
    """Inject the web search callable."""
    agent_state.web_search_callable = callable_fn


def get_status() -> dict[str, Any]:
    """Get the current status of the autonomous agent for API/dashboard."""
    return {
        "running": agent_state.running,
        "mode": agent_state.get_mode(),
        "loop_interval": AGENT_LOOP_INTERVAL,
        "last_user_message_ago": time.time() - agent_state.last_user_message_time
        if agent_state.last_user_message_time
        else None,
        "last_agent_message_ago": time.time() - agent_state.last_agent_message_time
        if agent_state.last_agent_message_time
        else None,
        "consecutive_agent_messages": agent_state.consecutive_agent_messages,
        "total_autonomous_actions": agent_state.total_autonomous_actions,
        "total_user_messages": agent_state.total_user_messages,
        "session_id": agent_state.current_session_id,
        "queue_stats": get_queue_stats(),
        "active_plans_count": len(get_active_plans()),
        "can_act": agent_state.can_act_autonomously(),
    }
