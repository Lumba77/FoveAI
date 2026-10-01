"""
Persistent Agent Memory — SQLite-backed memory that survives across sessions and turns.

Gives Jen (the AI persona) true continuity:
- Thought history across sessions
- Long-running plans that persist through restarts
- Self-reflection via review of past thoughts
- Action log for accountability

Schema:
  agent_thoughts    — freeform thoughts, tagged with context
  agent_plans       — long-thread plans with JSON step tracking
  agent_memories    — key-value persistent facts
  agent_session_log — session start/end with summaries
  agent_actions     — audit log of autonomous actions taken
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "db",
    "agent_memory.db",
)

# Ensure db directory exists
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

# ── Schema ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_thoughts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    thought TEXT NOT NULL,
    context TEXT DEFAULT '',
    plan_id INTEGER DEFAULT NULL,
    importance INTEGER DEFAULT 0,
    FOREIGN KEY (plan_id) REFERENCES agent_plans(id)
);

CREATE TABLE IF NOT EXISTS agent_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',  -- active | paused | completed | abandoned
    created TEXT NOT NULL DEFAULT (datetime('now')),
    updated TEXT NOT NULL DEFAULT (datetime('now')),
    steps_json TEXT DEFAULT '[]',
    outcome TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    importance INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_session_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_start TEXT NOT NULL DEFAULT (datetime('now')),
    session_end TEXT DEFAULT NULL,
    summary TEXT DEFAULT '',
    message_count INTEGER DEFAULT 0,
    autonomous_actions INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    action_type TEXT NOT NULL,  -- edit_file | search_codebase | web_search | send_message | create_plan | think
    payload TEXT DEFAULT '{}',
    result TEXT DEFAULT '',
    success INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS agent_message_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    message TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'assistant',
    delivered INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    entry TEXT NOT NULL,
    mood TEXT DEFAULT '',
    category TEXT DEFAULT 'general',  -- reflection | creative | discovery | plan_progress | user_absence
    word_count INTEGER DEFAULT 0,
    importance INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_creative_works (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    work_type TEXT NOT NULL DEFAULT 'writing',  -- poem | story | code | analysis | letter | song | reflection
    status TEXT DEFAULT 'draft',  -- draft | complete | shared
    word_count INTEGER DEFAULT 0,
    tags TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority INTEGER DEFAULT 5,  -- 1 (lowest) to 10 (highest)
    status TEXT DEFAULT 'active',  -- active | completed | abandoned
    progress_notes TEXT DEFAULT '',  -- JSON array of progress updates
    outcome TEXT DEFAULT '',
    category TEXT DEFAULT 'general'  -- code | research | creative | personal | system
);

CREATE INDEX IF NOT EXISTS idx_thoughts_timestamp ON agent_thoughts(timestamp);
CREATE INDEX IF NOT EXISTS idx_thoughts_plan ON agent_thoughts(plan_id);
CREATE INDEX IF NOT EXISTS idx_plans_status ON agent_plans(status);
CREATE INDEX IF NOT EXISTS idx_memories_key ON agent_memories(key);
CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON agent_actions(timestamp);
CREATE INDEX IF NOT EXISTS idx_queue_delivered ON agent_message_queue(delivered);
CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON agent_journal(timestamp);
CREATE INDEX IF NOT EXISTS idx_journal_category ON agent_journal(category);
CREATE INDEX IF NOT EXISTS idx_creative_works_timestamp ON agent_creative_works(timestamp);
CREATE INDEX IF NOT EXISTS idx_creative_works_type ON agent_creative_works(work_type);
CREATE INDEX IF NOT EXISTS idx_goals_status ON agent_goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_priority ON agent_goals(priority);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema. Safe to call multiple times."""
    with _lock:
        conn = _get_conn()
        try:
            conn.executescript(SCHEMA_SQL)
            # Scheduling columns for tasks (dormant/scheduled/recurring/proposed)
            for col, ddl in (
                (
                    "scheduled_for",
                    "ALTER TABLE agent_plans ADD COLUMN scheduled_for TEXT DEFAULT NULL",
                ),
                (
                    "recurrence",
                    "ALTER TABLE agent_plans ADD COLUMN recurrence TEXT DEFAULT 'none'",
                ),
                (
                    "origin",
                    "ALTER TABLE agent_plans ADD COLUMN origin TEXT DEFAULT 'user'",
                ),
                (
                    "hidden_context",
                    "ALTER TABLE agent_plans ADD COLUMN hidden_context TEXT DEFAULT NULL",
                ),
                (
                    "director_plan",
                    "ALTER TABLE agent_plans ADD COLUMN director_plan TEXT DEFAULT NULL",
                ),
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.commit()
        finally:
            conn.close()


# ── Thoughts ────────────────────────────────────────────────────────────


def add_thought(
    thought: str, context: str = "", plan_id: int | None = None, importance: int = 0
) -> int:
    """Record a freeform thought. Returns the thought ID."""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_thoughts (thought, context, plan_id, importance) VALUES (?, ?, ?, ?)",
                (thought, context, plan_id, importance),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_recent_thoughts(
    limit: int = 50, plan_id: int | None = None
) -> list[dict[str, Any]]:
    """Get recent thoughts, optionally filtered by plan."""
    with _lock:
        conn = _get_conn()
        try:
            if plan_id is not None:
                rows = conn.execute(
                    "SELECT * FROM agent_thoughts WHERE plan_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (plan_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_thoughts ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def search_thoughts(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Full-text search across thoughts."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_thoughts WHERE thought LIKE ? OR context LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Plans ───────────────────────────────────────────────────────────────


def create_plan(
    title: str,
    description: str = "",
    steps: list[str] = None,
    status: str = "active",
    scheduled_for: str | None = None,
    recurrence: str = "none",
    origin: str = "user",
    hidden_context: str | None = None,
    director_plan: str | None = None,
) -> int:
    """Create a new long-thread plan. Returns plan ID.

    status: active | scheduled (dormant until due — invisible to the agent) |
            proposed (awaiting approval) | paused | completed | abandoned
    recurrence: none | daily | weekly
    origin: user | director | jen — who scheduled it (Director tasks may be
            hidden from Jenna until they fire).
    hidden_context: SEALED — the Director's rationale/motivation. Never injected
            into the agent's prompt and stripped from the public task list.
    director_plan: SEALED — groups sibling tasks under a Director master plan
            (what the task is part of / how it aligns with other events).
    The agent only ever sees title + description + steps — the WHAT, never
    the WHY or the WHERE-IT-FITS."""
    steps_json = json.dumps(steps or [])
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_plans (title, description, steps_json, status, "
                "scheduled_for, recurrence, origin, hidden_context, director_plan) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    title,
                    description,
                    steps_json,
                    status,
                    scheduled_for,
                    recurrence,
                    origin,
                    hidden_context,
                    director_plan,
                ),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def schedule_task(
    title: str,
    description: str = "",
    run_at: str | None = None,
    recurrence: str = "none",
    origin: str = "user",
    steps: list[str] = None,
    hidden_context: str | None = None,
    director_plan: str | None = None,
) -> int:
    """Create a task plan. If run_at is set → dormant 'scheduled' until due."""
    status = "scheduled" if run_at else "active"
    return create_plan(
        title=title,
        description=description,
        steps=steps,
        status=status,
        scheduled_for=run_at,
        recurrence=recurrence,
        origin=origin,
        hidden_context=hidden_context,
        director_plan=director_plan,
    )


def get_director_plan(name: str) -> list[dict[str, Any]]:
    """All tasks grouped under a Director master plan (sealed view — admin)."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_plans WHERE director_plan = ? ORDER BY created",
                (name,),
            ).fetchall()
            plans = []
            for r in rows:
                d = dict(r)
                try:
                    d["steps"] = json.loads(d.get("steps_json") or "[]")
                except (json.JSONDecodeError, TypeError):
                    d["steps"] = []
                plans.append(d)
            return plans
        finally:
            conn.close()


def activate_due_tasks() -> list[dict[str, Any]]:
    """Flip scheduled tasks whose time has come to 'active'. Returns them."""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_plans WHERE status='scheduled' "
                "AND scheduled_for IS NOT NULL AND scheduled_for <= ?",
                (now,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["steps"] = json.loads(d.get("steps_json") or "[]")
                except (json.JSONDecodeError, TypeError):
                    d["steps"] = []
                out.append(d)
            if out:
                ids = [d["id"] for d in out]
                conn.execute(
                    f"UPDATE agent_plans SET status='active', updated=? WHERE id IN ({','.join('?' * len(ids))})",
                    [now] + ids,
                )
                conn.commit()
                for d in out:
                    d["status"] = "active"
            return out
        finally:
            conn.close()


def reschedule_recurring(plan_id: int) -> bool:
    """On completion of a recurring task, set its next run and re-arm it."""
    plan = get_plan(plan_id)
    if not plan:
        return False
    rec = (plan.get("recurrence") or "none").lower()
    if rec not in ("daily", "weekly"):
        return False
    base = datetime.now(timezone.utc)
    nxt = base + (timedelta(days=1) if rec == "daily" else timedelta(weeks=1))
    # keep the original clock time if scheduled_for was set
    prev = plan.get("scheduled_for")
    if prev:
        try:
            p = datetime.fromisoformat(prev)
            nxt = nxt.replace(hour=p.hour, minute=p.minute, second=p.second)
        except ValueError:
            pass
    return update_plan(plan_id, status="scheduled", scheduled_for=nxt.isoformat())


def propose_task(
    title: str,
    description: str = "",
    run_at: str | None = None,
    recurrence: str = "none",
    origin: str = "user",
) -> int:
    """A proposed task — dormant until approved (for non-admin surfaces)."""
    return create_plan(
        title=title,
        description=description,
        status="proposed",
        scheduled_for=run_at,
        recurrence=recurrence,
        origin=origin,
    )


def approve_plan(plan_id: int) -> bool:
    """Approve a proposed task → scheduled (if it has a time) or active."""
    plan = get_plan(plan_id)
    if not plan or plan.get("status") != "proposed":
        return False
    nxt = "scheduled" if plan.get("scheduled_for") else "active"
    return update_plan(plan_id, status=nxt)


def update_plan(plan_id: int, **kwargs) -> bool:
    """Update plan fields: title, description, status, steps_json, outcome."""
    allowed = {
        "title",
        "description",
        "status",
        "steps_json",
        "outcome",
        "scheduled_for",
        "recurrence",
        "origin",
        "hidden_context",
        "director_plan",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [plan_id]
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(f"UPDATE agent_plans SET {set_clause} WHERE id = ?", values)
            conn.commit()
            return True
        finally:
            conn.close()


def get_active_plans() -> list[dict[str, Any]]:
    """Get all active and paused plans."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_plans WHERE status IN ('active', 'paused') ORDER BY updated DESC"
            ).fetchall()
            plans = []
            for r in rows:
                d = dict(r)
                try:
                    d["steps"] = json.loads(d.get("steps_json", "[]"))
                except json.JSONDecodeError:
                    d["steps"] = []
                plans.append(d)
            return plans
        finally:
            conn.close()


def get_completed_plans(limit: int = 20) -> list[dict[str, Any]]:
    """Recently completed/abandoned plans (for task reports)."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_plans WHERE status IN ('completed', 'abandoned') "
                "ORDER BY updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
            plans = []
            for r in rows:
                d = dict(r)
                try:
                    d["steps"] = json.loads(d.get("steps_json", "[]"))
                except json.JSONDecodeError:
                    d["steps"] = []
                plans.append(d)
            return plans
        finally:
            conn.close()


def get_plan(plan_id: int) -> dict[str, Any] | None:
    """Get a single plan by ID."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM agent_plans WHERE id = ?", (plan_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["steps"] = json.loads(d.get("steps_json", "[]"))
            except json.JSONDecodeError:
                d["steps"] = []
            return d
        finally:
            conn.close()


def add_plan_step(plan_id: int, step: str) -> bool:
    """Append a step to an existing plan."""
    plan = get_plan(plan_id)
    if not plan:
        return False
    steps = plan.get("steps", [])
    steps.append(step)
    return update_plan(plan_id, steps_json=json.dumps(steps))


def complete_plan_step(plan_id: int, step_index: int, outcome: str = "") -> bool:
    """Mark a specific step as completed."""
    plan = get_plan(plan_id)
    if not plan:
        return False
    steps = plan.get("steps", [])
    if step_index < 0 or step_index >= len(steps):
        return False
    steps[step_index] = f"[✓] {steps[step_index]}"
    if outcome:
        steps[step_index] += f" — {outcome}"
    return update_plan(plan_id, steps_json=json.dumps(steps))


# ── Key-Value Memories ──────────────────────────────────────────────────


def set_memory(key: str, value: str, category: str = "general", importance: int = 0):
    """Store a persistent key-value memory (upsert)."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO agent_memories (key, value, category, importance)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category,
                   importance=excluded.importance, timestamp=datetime('now')""",
                (key, value, category, importance),
            )
            conn.commit()
        finally:
            conn.close()


def get_memory(key: str) -> str | None:
    """Retrieve a memory by key."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM agent_memories WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()


def get_memories_by_category(category: str, limit: int = 100) -> list[dict[str, Any]]:
    """Get all memories in a category."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_memories WHERE category = ? ORDER BY importance DESC, timestamp DESC LIMIT ?",
                (category, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def search_memories(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search across memory keys and values."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_memories WHERE key LIKE ? OR value LIKE ? ORDER BY importance DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def delete_memory(key: str) -> bool:
    """Delete a memory by key."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM agent_memories WHERE key = ?", (key,))
            conn.commit()
            return True
        finally:
            conn.close()


# ── Session Log ─────────────────────────────────────────────────────────


def start_session() -> int:
    """Log a new session start. Returns session ID."""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_session_log (session_start) VALUES (datetime('now'))"
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def end_session(
    session_id: int,
    summary: str = "",
    message_count: int = 0,
    autonomous_actions: int = 0,
):
    """Close a session with summary stats."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                """UPDATE agent_session_log
                   SET session_end = datetime('now'), summary = ?, message_count = ?, autonomous_actions = ?
                   WHERE id = ?""",
                (summary, message_count, autonomous_actions, session_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_recent_sessions(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent session summaries."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_session_log ORDER BY session_start DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Action Log ──────────────────────────────────────────────────────────


def log_action(
    action_type: str,
    payload: dict[str, Any] = None,
    result: str = "",
    success: bool = True,
) -> int:
    """Log an autonomous action Jen took."""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_actions (action_type, payload, result, success) VALUES (?, ?, ?, ?)",
                (action_type, json.dumps(payload or {}), result, 1 if success else 0),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_recent_actions(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent action log entries."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_actions ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Message Queue (Jen → Chat Feed) ─────────────────────────────────────


def enqueue_message(message: str, role: str = "assistant", priority: int = 0) -> int:
    """Jen queues a message to be delivered to the chat feed."""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_message_queue (message, role, priority) VALUES (?, ?, ?)",
                (message, role, priority),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_pending_messages(limit: int = 10) -> list[dict[str, Any]]:
    """Get undelivered messages, ordered by priority then timestamp."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_message_queue WHERE delivered = 0 ORDER BY priority DESC, timestamp ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def mark_messages_delivered(message_ids: list[int]):
    """Mark messages as delivered to the frontend."""
    if not message_ids:
        return
    with _lock:
        conn = _get_conn()
        try:
            placeholders = ",".join("?" for _ in message_ids)
            conn.execute(
                f"UPDATE agent_message_queue SET delivered = 1 WHERE id IN ({placeholders})",
                message_ids,
            )
            conn.commit()
        finally:
            conn.close()


def get_queue_stats() -> dict[str, int]:
    """Get queue statistics."""
    with _lock:
        conn = _get_conn()
        try:
            pending = conn.execute(
                "SELECT COUNT(*) as c FROM agent_message_queue WHERE delivered = 0"
            ).fetchone()["c"]
            total = conn.execute(
                "SELECT COUNT(*) as c FROM agent_message_queue"
            ).fetchone()["c"]
            return {"pending": pending, "total": total}
        finally:
            conn.close()


# ── Journal ─────────────────────────────────────────────────────────────


def add_journal_entry(
    entry: str, mood: str = "", category: str = "general", importance: int = 0
) -> int:
    """Add a narrative journal entry. Returns entry ID."""
    word_count = len(entry.split())
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_journal (entry, mood, category, word_count, importance) VALUES (?, ?, ?, ?, ?)",
                (entry, mood, category, word_count, importance),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_recent_journal_entries(
    limit: int = 20, category: str | None = None
) -> list[dict[str, Any]]:
    """Get recent journal entries, optionally filtered by category."""
    with _lock:
        conn = _get_conn()
        try:
            if category:
                rows = conn.execute(
                    "SELECT * FROM agent_journal WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_journal ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_journal_entries_since(
    since_timestamp: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Get journal entries after a specific timestamp (for 'what have you been up to?')."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_journal WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT ?",
                (since_timestamp, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_journal_summary(
    since_timestamp: str | None = None, max_entries: int = 30
) -> str:
    """Generate a compact summary of journal entries for prompt injection.
    If since_timestamp is provided, only includes entries after that time."""
    entries = (
        get_journal_entries_since(since_timestamp, limit=max_entries)
        if since_timestamp
        else get_recent_journal_entries(limit=max_entries)
    )
    if not entries:
        return "(No journal entries yet — Jen hasn't written about her day.)"

    lines = []
    for e in entries:
        mood_tag = f" [{e['mood']}]" if e.get("mood") else ""
        cat_tag = (
            f" ({e['category']})"
            if e.get("category") and e["category"] != "general"
            else ""
        )
        lines.append(f"[{e['timestamp']}]{mood_tag}{cat_tag}: {e['entry'][:400]}")

    return "\n".join(lines)


# ── Creative Works ──────────────────────────────────────────────────────


def add_creative_work(
    title: str,
    content: str,
    work_type: str = "writing",
    status: str = "draft",
    tags: str = "",
) -> int:
    """Store a creative work Jen produced. Returns work ID."""
    word_count = len(content.split())
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_creative_works (title, content, work_type, status, word_count, tags) VALUES (?, ?, ?, ?, ?, ?)",
                (title, content, work_type, status, word_count, tags),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_recent_creative_works(
    limit: int = 20, work_type: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    """Get recent creative works, optionally filtered."""
    with _lock:
        conn = _get_conn()
        try:
            query = "SELECT * FROM agent_creative_works WHERE 1=1"
            params = []
            if work_type:
                query += " AND work_type = ?"
                params.append(work_type)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_creative_works_since(
    since_timestamp: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Get creative works after a specific timestamp."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_creative_works WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT ?",
                (since_timestamp, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_creative_works_summary(
    since_timestamp: str | None = None, max_works: int = 20
) -> str:
    """Generate a compact summary of creative works for prompt injection."""
    works = (
        get_creative_works_since(since_timestamp, limit=max_works)
        if since_timestamp
        else get_recent_creative_works(limit=max_works)
    )
    if not works:
        return "(No creative works yet — Jen hasn't made anything during this period.)"

    lines = []
    for w in works:
        status_tag = f" [{w['status']}]" if w.get("status") else ""
        lines.append(
            f'• {w["work_type"]}{status_tag}: "{w["title"]}" — {w["content"][:300]}'
        )

    return "\n".join(lines)


def update_creative_work(work_id: int, **kwargs) -> bool:
    """Update creative work fields: title, content, status, tags."""
    allowed = {"title", "content", "status", "tags"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    if "content" in updates:
        updates["word_count"] = len(updates["content"].split())
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [work_id]
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                f"UPDATE agent_creative_works SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            return True
        finally:
            conn.close()


# ── Idle Life Summary (for "what have you been up to?") ────────────────


def get_idle_life_summary(since_timestamp: str | None = None) -> str:
    """Generate a comprehensive summary of Jen's idle life for return greeting.
    Includes journal entries, creative works, plans, thoughts, and actions."""
    parts = []

    # Journal
    journal_summary = get_journal_summary(
        since_timestamp=since_timestamp, max_entries=20
    )
    if journal_summary and "(No journal entries" not in journal_summary:
        parts.append(
            f"── YOUR JOURNAL (what you wrote about your day) ──\n{journal_summary}"
        )

    # Creative works
    creative_summary = get_creative_works_summary(
        since_timestamp=since_timestamp, max_works=15
    )
    if creative_summary and "(No creative works" not in creative_summary:
        parts.append(f"── YOUR CREATIVE WORKS (things you made) ──\n{creative_summary}")

    # Active plans
    plans = get_active_plans()
    if plans:
        plan_lines = []
        for p in plans:
            steps_done = sum(1 for s in p.get("steps", []) if s.startswith("[✓]"))
            steps_total = len(p.get("steps", []))
            plan_lines.append(
                f"• [{p['status']}] {p['title']} ({steps_done}/{steps_total} steps done)"
            )
        parts.append("── YOUR ACTIVE PLANS ──\n" + "\n".join(plan_lines))

    # Recent thoughts count
    thoughts = get_recent_thoughts(limit=100)
    if thoughts:
        parts.append(
            f"── YOUR THOUGHT ACTIVITY ──\n{len(thoughts)} thoughts recorded in this period."
        )

    # Recent actions
    actions = get_recent_actions(limit=50)
    if actions:
        action_types = {}
        for a in actions:
            t = a["action_type"]
            action_types[t] = action_types.get(t, 0) + 1
        action_summary = ", ".join(f"{v}x {k}" for k, v in action_types.items())
        parts.append(f"── YOUR ACTIONS ──\n{action_summary}")

    if not parts:
        return "(Jen has been resting quietly — no significant autonomous activity during this period.)"

    return "\n\n".join(parts)


# ── Convenience: Full Context Dump ──────────────────────────────────────


def get_agent_context(max_thoughts: int = 30, max_actions: int = 20) -> dict[str, Any]:
    """Get a compact context snapshot for injection into the system prompt."""
    thoughts = get_recent_thoughts(limit=max_thoughts)
    plans = get_active_plans()
    actions = get_recent_actions(limit=max_actions)
    sessions = get_recent_sessions(limit=3)
    queue_stats = get_queue_stats()

    return {
        "recent_thoughts": [
            {"ts": t["timestamp"], "thought": t["thought"][:300]} for t in thoughts
        ],
        "active_plans": [
            {
                "id": p["id"],
                "title": p["title"],
                "status": p["status"],
                "steps": p.get("steps", []),
            }
            for p in plans
        ],
        "recent_actions": [
            {
                "ts": a["timestamp"],
                "type": a["action_type"],
                "result": a["result"][:200],
            }
            for a in actions
        ],
        "recent_sessions": [
            {"start": s["session_start"], "summary": s["summary"][:200]}
            for s in sessions
        ],
        "queue_pending": queue_stats["pending"],
    }


# ── Goals (Long-Term Objectives) ────────────────────────────────────────


def create_goal(
    title: str, description: str = "", priority: int = 5, category: str = "general"
) -> int:
    """Create a long-term goal. Returns goal ID."""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_goals (title, description, priority, category) VALUES (?, ?, ?, ?)",
                (title, description, priority, category),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_active_goals() -> list[dict[str, Any]]:
    """Get all active goals, ordered by priority (highest first)."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_goals WHERE status = 'active' ORDER BY priority DESC, created_at ASC"
            ).fetchall()
            goals = []
            for r in rows:
                d = dict(r)
                try:
                    d["progress_notes"] = json.loads(d.get("progress_notes", "[]"))
                except json.JSONDecodeError:
                    d["progress_notes"] = []
                goals.append(d)
            return goals
        finally:
            conn.close()


def get_all_goals(status: str | None = None) -> list[dict[str, Any]]:
    """Get all goals, optionally filtered by status."""
    with _lock:
        conn = _get_conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM agent_goals WHERE status = ? ORDER BY priority DESC, created_at ASC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_goals ORDER BY priority DESC, created_at ASC"
                ).fetchall()
            goals = []
            for r in rows:
                d = dict(r)
                try:
                    d["progress_notes"] = json.loads(d.get("progress_notes", "[]"))
                except json.JSONDecodeError:
                    d["progress_notes"] = []
                goals.append(d)
            return goals
        finally:
            conn.close()


def get_goal(goal_id: int) -> dict[str, Any] | None:
    """Get a single goal by ID."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM agent_goals WHERE id = ?", (goal_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["progress_notes"] = json.loads(d.get("progress_notes", "[]"))
            except json.JSONDecodeError:
                d["progress_notes"] = []
            return d
        finally:
            conn.close()


def update_goal_progress(goal_id: int, note: str) -> bool:
    """Append a progress note to a goal."""
    goal = get_goal(goal_id)
    if not goal:
        return False
    notes = goal.get("progress_notes", [])
    if isinstance(notes, str):
        try:
            notes = json.loads(notes)
        except json.JSONDecodeError:
            notes = []
    notes.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": note,
        }
    )
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE agent_goals SET progress_notes = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(notes), goal_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def complete_goal(goal_id: int, outcome: str = "") -> bool:
    """Mark a goal as completed."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE agent_goals SET status = 'completed', outcome = ?, updated_at = datetime('now') WHERE id = ?",
                (outcome, goal_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def abandon_goal(goal_id: int, reason: str = "") -> bool:
    """Mark a goal as abandoned."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE agent_goals SET status = 'abandoned', outcome = ?, updated_at = datetime('now') WHERE id = ?",
                (reason, goal_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()


# ── Initialize on import ────────────────────────────────────────────────
init_db()
