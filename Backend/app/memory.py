"""SQLite FTS5 memory store — single-pass recall for the unified pipeline.

Stores conversation turns and knowledge fragments in an FTS5 virtual table
for sub-millisecond full-text search.  No external services required.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_DB_PATH = os.environ.get(
    "XRLF_MEMORY_DB",
    str(Path(__file__).resolve().parent.parent / "data" / "lumax_memory.db"),
)

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    """Open a thread-safe connection to the SQLite memory database."""
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_conn = _connect()
_initialized = False


def _init_db() -> None:
    """Create tables and FTS5 index if they don't exist."""
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT NOT NULL,          -- 'user' | 'assistant' | 'system' | 'knowledge'
                content   TEXT NOT NULL,
                metadata  TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                content,
                content='memory',
                content_rowid='id',
                tokenize='unicode61'
            );

            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
                INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, content) VALUES('delete', old.id, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, content) VALUES('delete', old.id, old.content);
                INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
            END;
            """
        )
        _conn.commit()
        _initialized = True


def store(role: str, content: str, metadata: dict[str, Any] | None = None) -> int:
    """Insert a memory row and return its rowid."""
    _init_db()
    meta = json.dumps(metadata or {})
    ts = time.time()
    with _lock:
        cur = _conn.execute(
            "INSERT INTO memory (role, content, metadata, created_at) VALUES (?, ?, ?, ?)",
            (role, content, meta, ts),
        )
        _conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Full-text search via FTS5. Returns ranked matches."""
    _init_db()
    # Escape FTS5 special characters by wrapping in double quotes
    safe = query.replace('"', '""')
    fts_query = f'"{safe}"'
    with _lock:
        rows = _conn.execute(
            """
            SELECT m.id, m.role, m.content, m.metadata, m.created_at,
                   bm25(memory_fts) AS rank
            FROM memory_fts
            JOIN memory m ON m.id = memory_fts.rowid
            WHERE memory_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def recent(limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent memory rows."""
    _init_db()
    with _lock:
        rows = _conn.execute(
            "SELECT id, role, content, metadata, created_at FROM memory ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def recall_context(query: str, limit: int = 5) -> str:
    """Return a compact context string from FTS5 recall for prompt injection."""
    results = search(query, limit=limit)
    if not results:
        return ""
    lines = []
    for r in results:
        lines.append(f"[{r['role']}] {r['content'][:200]}")
    return "\n".join(lines)


def close() -> None:
    """Close the database connection."""
    with _lock:
        _conn.close()
