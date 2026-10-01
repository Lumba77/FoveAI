"""
memory/membrane_engine.py — In-Process Foveated Memory Engine
=============================================================
An in-process, zero-proxy adaptation of the Foveated Memory system.
All memory computation happens inside the XRLF runtime — no network calls.

6-Ring Foveated Architecture:
  Ring 0: identity    — persistent model persona / system context
  Ring 1: task        — current task / goal framing
  Ring 2: recent      — last 8 turns (verbatim)
  Ring 3: working     — last 32 turns (compressed)
  Ring 4: background  — last 128 turns (heavily compressed)
  Ring 5: archive     — long-term semantic summaries (TF-IDF retrieved)

The SQLite DB is extracted from the XRLF file at load time and
optionally re-packed back into the XRLF file at session end.
"""

import json
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any

from memory.tfidf_store import TFIDFStore

# ── Database schema ───────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    turn_index  INTEGER NOT NULL,
    timestamp   REAL    NOT NULL,
    tags        TEXT    DEFAULT '[]',
    ring        INTEGER DEFAULT 2,
    ring_label  TEXT    DEFAULT 'recent'
);

CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    ring        INTEGER NOT NULL,
    ring_label  TEXT    DEFAULT 'recent',
    timestamp   REAL    NOT NULL,
    turn_start  INTEGER NOT NULL,
    turn_end    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS identity (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, turn_index);
CREATE INDEX IF NOT EXISTS idx_turns_ring ON turns(session_id, ring);
CREATE INDEX IF NOT EXISTS idx_summaries_session ON summaries(session_id, ring);
"""


class MembraneEngine:
    """
    In-process foveated memory engine.
    Extracts from XRLF at load, runs zero-network, re-packs on close.
    """

    def __init__(
        self,
        db_path: str,
        session_id: str = "default",
        token_budget: int = 2048,
        ring_config: dict | None = None,
    ):
        self.db_path = str(db_path)
        self.session_id = session_id
        self.token_budget = token_budget
        self.ring_config = ring_config or _default_ring_config()
        self._db: sqlite3.Connection | None = None
        self._tfidf = TFIDFStore()
        self._turn_index = 0
        self._loaded = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def load(self) -> "MembraneEngine":
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_file), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._ensure_ring_columns()
        self._db.commit()

        # Load existing turns into TF-IDF index
        rows = self._db.execute(
            "SELECT id, content FROM turns WHERE session_id=?", (self.session_id,)
        ).fetchall()
        for row in rows:
            self._tfidf.index(str(row["id"]), row["content"])

        # Set turn_index
        row = self._db.execute(
            "SELECT MAX(turn_index) as mx FROM turns WHERE session_id=?",
            (self.session_id,),
        ).fetchone()
        self._turn_index = (row["mx"] or 0) + 1
        self._loaded = True
        print(
            f"  MembraneEngine loaded: {self.db_path}  (session={self.session_id}, turns={self._turn_index})"
        )
        return self

    def close(self):
        if self._db:
            self._db.close()
        self._loaded = False

    # ── Memory store ──────────────────────────────────────────────────────────

    def store_turn(
        self,
        role: str,
        content: str,
        tags: list[str] | None = None,
        ring_id: int | None = None,
        ring_label: str | None = None,
    ) -> int:
        """Store one conversation turn. Returns the turn id."""
        self._require_loaded()
        if ring_id is None:
            ring_id = 2
        ring_id = int(ring_id)
        ring_label = ring_label or self.ring_label_for_id(ring_id)
        now = time.time()
        tags_json = json.dumps(tags or [])
        cur = self._db.execute(
            """INSERT INTO turns (session_id, role, content, turn_index, timestamp, tags, ring, ring_label)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.session_id,
                role,
                content,
                self._turn_index,
                now,
                tags_json,
                ring_id,
                ring_label,
            ),
        )
        self._db.commit()
        turn_id = cur.lastrowid
        self._tfidf.index(str(turn_id), content)
        self._turn_index += 1
        return turn_id

    def set_identity(self, key: str, value: str):
        """Persist identity/persona data (ring 0)."""
        self._db.execute(
            "INSERT OR REPLACE INTO identity (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        self._db.commit()

    def get_identity(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT value FROM identity WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def semantic_search(self, query: str, top_k: int = 5) -> list[dict]:
        """TF-IDF semantic search over stored turns."""
        self._require_loaded()
        hits = self._tfidf.search(query, top_k)
        results = []
        for doc_id, score in hits:
            row = self._db.execute(
                "SELECT role, content, turn_index, timestamp FROM turns WHERE id=?",
                (int(doc_id),),
            ).fetchone()
            if row:
                results.append(
                    {
                        "role": row["role"],
                        "content": row["content"],
                        "turn_index": row["turn_index"],
                        "score": score,
                    }
                )
        return results

    def get_recent_turns(self, n: int = 8) -> list[dict]:
        """Get the last n turns (ring 2 — recent verbatim)."""
        rows = self._db.execute(
            """SELECT role, content, turn_index FROM turns
               WHERE session_id=?
               ORDER BY turn_index DESC LIMIT ?""",
            (self.session_id, n),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_by_ring(self, ring_id: int, limit: int | None = None) -> list[dict]:
        """Return all turns in a specific ring, optionally limited."""
        self._require_loaded()
        ring_id = int(ring_id)
        query = (
            "SELECT * FROM turns WHERE session_id=? AND ring=? ORDER BY turn_index ASC"
        )
        params: list[Any] = [self.session_id, ring_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = self._db.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def ring_label_for_id(ring_id: int) -> str:
        labels = ["identity", "task", "recent", "working", "background", "archive"]
        idx = int(ring_id)
        if 0 <= idx < len(labels):
            return labels[idx]
        return "recent"

    # ── Foveated ring block ───────────────────────────────────────────────────

    def weave_context(
        self,
        current_query: str,
        token_budget: int | None = None,
    ) -> str:
        """
        Build the 6-ring foveated context block to inject before generation.
        Returns a formatted string ready for system prompt injection.

        Memory is formatted as discrete background notes — NOT as dialogue —
        so the model treats it as context rather than continuing the pattern.
        """
        self._require_loaded()
        budget = token_budget or self.token_budget
        rings: list[str] = []

        # Ring 0 — Identity
        identity_val = self.get_identity("system_context") or ""
        if identity_val:
            rings.append(f"[Identity] {identity_val}")

        # Ring 2 — Recent (last 6 turns, compressed to key points)
        recent = self.get_recent_turns(6)
        if recent:
            recent_parts = []
            for t in recent:
                role = t["role"]
                content = _truncate(t["content"], 150)
                # Format as context notes, not dialogue
                if role == "user":
                    recent_parts.append(f'- User previously said: "{content}"')
                else:
                    recent_parts.append(
                        f'- Assistant previously responded: "{content}"'
                    )
            rings.append("[Recent context]\n" + "\n".join(recent_parts))

        # Ring 5 — Archive (TF-IDF recall against current query)
        if current_query:
            recalled = self.semantic_search(current_query, top_k=3)
            if recalled:
                recall_parts = []
                for r in recalled:
                    content = _truncate(r["content"], 120)
                    recall_parts.append(f'- "{content}"')
                rings.append("[Recalled from memory]\n" + "\n".join(recall_parts))

        if not rings:
            return ""

        block = "\n\n".join(rings)
        # Rough token budget enforcement (4 chars ≈ 1 token)
        max_chars = budget * 4
        if len(block) > max_chars:
            block = block[:max_chars] + "\n...[truncated by memory budget]"

        # Wrap as background context — explicitly tell the model this is
        # reference material, not conversation to continue
        return f"<background_memory>\n{block}\n</background_memory>\n[Note: The above is background context from previous sessions. Do not continue or repeat it. Respond only to the current user message.]"

    def get_serializable_snapshot(self) -> bytes:
        """
        Serialize the current DB + TF-IDF index for re-packing into XRLF.
        Returns bytes in the XRL_MEMORY_DATA layout:
          [4B sqlite_len][sqlite][tfidf_bytes]
        """
        # Flush and get DB bytes
        self._db.commit()
        sqlite_bytes = Path(self.db_path).read_bytes()
        tfidf_bytes = self._tfidf.serialize()
        return struct.pack("<I", len(sqlite_bytes)) + sqlite_bytes + tfidf_bytes

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_loaded(self):
        if not self._loaded:
            raise RuntimeError("MembraneEngine not loaded — call .load() first")

    def _ensure_ring_columns(self):
        cols = self._db.execute("PRAGMA table_info(turns)").fetchall()
        col_names = {row[1] for row in cols}
        if "ring_label" not in col_names:
            self._db.execute(
                "ALTER TABLE turns ADD COLUMN ring_label TEXT DEFAULT 'recent'"
            )
        summary_cols = self._db.execute("PRAGMA table_info(summaries)").fetchall()
        summary_names = {row[1] for row in summary_cols}
        if "ring_label" not in summary_names:
            self._db.execute(
                "ALTER TABLE summaries ADD COLUMN ring_label TEXT DEFAULT 'recent'"
            )


# ── Ring config default ───────────────────────────────────────────────────────


def _default_ring_config() -> dict:
    return {
        "ring_0": {"label": "identity", "max_tokens": 128, "ttl_turns": None},
        "ring_1": {"label": "task", "max_tokens": 256, "ttl_turns": None},
        "ring_2": {"label": "recent", "max_tokens": 512, "ttl_turns": 8},
        "ring_3": {"label": "working", "max_tokens": 512, "ttl_turns": 32},
        "ring_4": {"label": "background", "max_tokens": 384, "ttl_turns": 128},
        "ring_5": {"label": "archive", "max_tokens": 256, "ttl_turns": None},
    }


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"
