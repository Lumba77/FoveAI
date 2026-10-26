"""XRL-Bridge/1.0 — Concurrency-Safe SQLite Persistent Storage with TTL.

Provides idempotent storage, replay tracking, and task lifecycle management.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from bridge.schema import BridgeTaskRecord, CapabilityType, IntentType, TaskStatus


class BridgeStore:
    def __init__(self, db_path: str = "/home/lumba/FoveAI/user_data/bridge_store.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nonces (
                    nonce TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    seen_at INTEGER NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    result_json TEXT,
                    error TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nonces_timestamp ON nonces(timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_expires_at ON tasks(expires_at);")
            conn.commit()

    def record_nonce_and_message(self, nonce: str, message_id: str, timestamp: int, ttl_seconds: int = 300) -> bool:
        """Atomically checks and records nonce & message_id. Returns False if replayed."""
        now = int(time.time())
        self.cleanup_expired(ttl_seconds)

        with self._lock, self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO nonces (nonce, message_id, timestamp, seen_at) VALUES (?, ?, ?, ?)",
                    (nonce, message_id, timestamp, now)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def save_task(self, task: BridgeTaskRecord):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tasks 
                (task_id, message_id, intent, capability, payload_json, status, created_at, expires_at, result_json, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_id,
                task.message_id,
                task.intent.value,
                task.capability.value,
                json.dumps(task.payload),
                task.status.value,
                task.created_at,
                task.expires_at,
                json.dumps(task.result) if task.result is not None else None,
                task.error
            ))
            conn.commit()

    def get_task(self, task_id: str) -> Optional[BridgeTaskRecord]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                return None
            return BridgeTaskRecord(
                task_id=row["task_id"],
                message_id=row["message_id"],
                intent=IntentType(row["intent"]),
                capability=CapabilityType(row["capability"]),
                payload=json.loads(row["payload_json"]),
                status=TaskStatus(row["status"]),
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                result=json.loads(row["result_json"]) if row["result_json"] else None,
                error=row["error"]
            )

    def update_task_status(self, task_id: str, status: TaskStatus, result: Optional[Dict] = None, error: Optional[str] = None):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                UPDATE tasks
                SET status = ?, result_json = ?, error = ?
                WHERE task_id = ?
            """, (
                status.value,
                json.dumps(result) if result is not None else None,
                error,
                task_id
            ))
            conn.commit()

    def cleanup_expired(self, ttl_seconds: int = 300):
        now = int(time.time())
        cutoff = now - ttl_seconds
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM nonces WHERE seen_at < ?", (cutoff,))
            conn.execute("UPDATE tasks SET status = ? WHERE expires_at < ? AND status = ?", 
                         (TaskStatus.FAILED.value, now, TaskStatus.PENDING_APPROVAL.value))
            conn.commit()
