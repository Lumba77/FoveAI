"""
memory/membrane_engine.py — In-Process Foveated Memory Engine
=============================================================
An in-process, zero-proxy adaptation of the Foveated Memory system.
All memory computation happens inside the XRLF runtime — no network calls.

7-Ring Foveated Architecture:
  Ring 0: identity    — persistent model persona / system context
  Ring 1: task        — current task / goal framing
  Ring 2: recent      — last 8 turns (verbatim)
  Ring 3: working     — last 32 turns (compressed)
  Ring 4: background  — last 128 turns (heavily compressed)
  Ring 5: archive     — long-term semantic summaries (TF-IDF retrieved)
  Ring 7: constellation — interlinked concept conglomerates; memories that
                        were recalled together often enough crystallize into
                        named clusters (well-travelled thought patterns)

The SQLite DB is extracted from the XRLF file at load time and
optionally re-packed back into the XRLF file at session end.
"""

import json
import math
import os
import re
import sqlite3
import struct
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

-- Ring 7 substrate: co-recall edges. When turns are retrieved together in
-- one weave_context pass, their pairwise weight grows. Edges that pass a
-- traversal threshold crystallize into constellation rows below.
CREATE TABLE IF NOT EXISTS co_recall (
    a           INTEGER NOT NULL,
    b           INTEGER NOT NULL,
    weight      REAL    NOT NULL DEFAULT 1.0,
    updated_at  REAL    NOT NULL,
    PRIMARY KEY (a, b)
);

CREATE TABLE IF NOT EXISTS constellations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT    NOT NULL,
    members     TEXT    NOT NULL,   -- JSON array of turn ids
    weight      REAL    NOT NULL DEFAULT 0.0,
    touched     INTEGER NOT NULL DEFAULT 0,  -- loop-closing: times surfaced
    updated_at  REAL    NOT NULL
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
        ring_config: Optional[Dict] = None,
    ):
        self.db_path = str(db_path)
        self.session_id = session_id
        self.token_budget = token_budget
        self.ring_config = ring_config or _default_ring_config()
        self._db: Optional[sqlite3.Connection] = None
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
            "SELECT id, content FROM turns WHERE session_id=?",
            (self.session_id,)
        ).fetchall()
        for row in rows:
            self._tfidf.index(str(row["id"]), row["content"])

        # Set turn_index
        row = self._db.execute(
            "SELECT MAX(turn_index) as mx FROM turns WHERE session_id=?",
            (self.session_id,)
        ).fetchone()
        self._turn_index = (row["mx"] or 0) + 1
        self._loaded = True
        print(f"  MembraneEngine loaded: {self.db_path}  (session={self.session_id}, turns={self._turn_index})")
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
        tags: Optional[List[str]] = None,
        ring_id: Optional[int] = None,
        ring_label: Optional[str] = None,
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
            (self.session_id, role, content, self._turn_index, now, tags_json, ring_id, ring_label),
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
            (key, value, time.time())
        )
        self._db.commit()

    def get_identity(self, key: str) -> Optional[str]:
        row = self._db.execute(
            "SELECT value FROM identity WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def semantic_search(self, query: str, top_k: int = 5) -> List[Dict]:
        """TF-IDF semantic search over stored turns."""
        self._require_loaded()
        hits = self._tfidf.search(query, top_k)
        results = []
        for doc_id, score in hits:
            row = self._db.execute(
                "SELECT role, content, turn_index, timestamp FROM turns WHERE id=?",
                (int(doc_id),)
            ).fetchone()
            if row:
                results.append({
                    "role": row["role"],
                    "content": row["content"],
                    "turn_index": row["turn_index"],
                    "score": score,
                })
        return results

    # ── Ring 7: Constellations ─────────────────────────────────────────────
    # Co-recall graph. Every weave_context pass that recalls turns together
    # strengthens the edge between them. Edges that cross the traversal
    # threshold crystallize into constellation rows — named clusters of
    # interlinked memories representing well-travelled thought patterns.

    CONSTELLATION_MIN_EDGE = 3.0    # co-recalls before an edge is "travelled"
    CONSTELLATION_MIN_MEMBERS = 3   # smallest cluster worth crystallizing
    CONCLUSION_MIN_TOUCHED = 5      # surfaces before a cluster is "settled"

    def _traverse(self, turn_ids: List[int]) -> None:
        """Strengthen co-recall edges for a set of turns recalled together."""
        ids = sorted(set(int(t) for t in turn_ids))
        if len(ids) < 2:
            return
        now = time.time()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                self._db.execute(
                    """INSERT INTO co_recall (a, b, weight, updated_at)
                       VALUES (?, ?, 1.0, ?)
                       ON CONFLICT(a, b) DO UPDATE SET
                           weight = weight + 1.0, updated_at = ?""",
                    (a, b, now, now),
                )
        self._db.commit()
        self._crystallize()

    def _crystallize(self) -> None:
        """Cluster well-travelled co-recall edges into constellations.

        Greedy connected-components over edges with weight >= threshold.
        A constellation is updated (members + label + weight) rather than
        duplicated when its member set overlaps an existing one.
        """
        rows = self._db.execute(
            "SELECT a, b, weight FROM co_recall WHERE weight >= ?",
            (self.CONSTELLATION_MIN_EDGE,),
        ).fetchall()
        if not rows:
            return

        adjacency: Dict[int, set] = defaultdict(set)
        edge_weight: Dict[int, float] = defaultdict(float)
        for r in rows:
            adjacency[r["a"]].add(r["b"])
            adjacency[r["b"]].add(r["a"])
            edge_weight[r["a"]] += r["weight"]
            edge_weight[r["b"]] += r["weight"]

        seen: set = set()
        components: List[set] = []
        for node in adjacency:
            if node in seen:
                continue
            stack, comp = [node], set()
            while stack:
                n = stack.pop()
                if n in seen:
                    continue
                seen.add(n)
                comp.add(n)
                stack.extend(adjacency[n] - seen)
            if len(comp) >= self.CONSTELLATION_MIN_MEMBERS:
                components.append(comp)

        now = time.time()
        existing = {
            row["id"]: set(json.loads(row["members"]))
            for row in self._db.execute("SELECT id, members FROM constellations").fetchall()
        }
        for comp in components:
            member_ids = sorted(comp)
            weight = sum(edge_weight[m] for m in member_ids) / max(len(member_ids), 1)
            label = self._constellation_label(member_ids)
            # Merge into the existing constellation with the most overlap
            best_id, best_overlap = None, 0
            for cid, members in existing.items():
                overlap = len(members & comp)
                if overlap > best_overlap:
                    best_id, best_overlap = cid, overlap
            if best_id is not None and best_overlap >= 2:
                merged = sorted(set(member_ids) | existing[best_id])
                self._db.execute(
                    "UPDATE constellations SET label=?, members=?, weight=?, updated_at=? WHERE id=?",
                    (label, json.dumps(merged), weight, now, best_id),
                )
            else:
                self._db.execute(
                    "INSERT INTO constellations (label, members, weight, updated_at) VALUES (?, ?, ?, ?)",
                    (label, json.dumps(member_ids), weight, now),
                )
        self._db.commit()

    _STOPWORDS = {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is",
        "it", "that", "this", "you", "i", "we", "with", "at", "be", "as",
        "are", "was", "were", "have", "has", "not", "but", "what", "how",
    }

    def _constellation_label(self, member_ids: List[int]) -> str:
        """Label a constellation from the most common content terms."""
        q = "SELECT content FROM turns WHERE id IN (%s)" % ",".join(
            "?" * len(member_ids))
        words: Dict[str, int] = defaultdict(int)
        for row in self._db.execute(q, member_ids).fetchall():
            for w in re.findall(r"[a-zA-Z]{4,}", row["content"].lower()):
                if w not in self._STOPWORDS:
                    words[w] += 1
        top = [w for w, _ in sorted(words.items(), key=lambda kv: -kv[1])[:3]]
        return " / ".join(top) if top else "unnamed cluster"

    def _constellations_for(self, query: str, recalled_ids: List[int]) -> List[Dict]:
        """Constellations relevant to this turn: containing a recalled member,
        or whose label shares a term with the query.

        Each hit is a heuristic endpoint — it lands WITH content (the
        strongest member excerpt), not just a pointer. Surfacing a
        constellation bumps `touched`: the loop closes and reinforces.
        """
        rows = self._db.execute(
            "SELECT id, label, members, weight, touched FROM constellations ORDER BY weight DESC"
        ).fetchall()
        if not rows:
            return []
        q_terms = {w for w in re.findall(r"[a-zA-Z]{4,}", query.lower())
                   if w not in self._STOPWORDS}
        recalled = set(recalled_ids)
        hits = []
        for row in rows:
            members = set(json.loads(row["members"]))
            label_terms = set(row["label"].split(" / "))
            if (members & recalled) or (label_terms & q_terms):
                # endpoint: land on the cluster's strongest member
                excerpt = self._constellation_excerpt(row["id"], members)
                self._db.execute(
                    "UPDATE constellations SET touched = touched + 1 WHERE id=?",
                    (row["id"],),
                )
                touched = row["touched"] + 1
                hits.append({
                    "id": row["id"],
                    "label": row["label"],
                    "size": len(members),
                    "weight": round(row["weight"], 1),
                    "touched": touched,
                    "settled": touched >= self.CONCLUSION_MIN_TOUCHED,
                    "excerpt": excerpt,
                })
        if hits:
            self._db.commit()
        return hits[:4]

    def _constellation_excerpt(self, constellation_id: int, members: set) -> str:
        """Representative member excerpt — the constellation's core memory."""
        if not members:
            return ""
        # most-connected member = the densest part of the cluster
        q = ("SELECT a, b FROM co_recall WHERE a IN (%s) OR b IN (%s)"
             % (",".join("?" * len(members)), ",".join("?" * len(members))))
        degree: Dict[int, float] = defaultdict(float)
        for r in self._db.execute(q, list(members) + list(members)).fetchall():
            degree[r["a"]] += 1
            degree[r["b"]] += 1
        core = max(members, key=lambda m: degree.get(m, 0))
        row = self._db.execute(
            "SELECT content FROM turns WHERE id=?", (core,)).fetchone()
        return _truncate(row["content"], 100) if row else ""

    def get_root(self) -> Optional[Dict]:
        """The most-travelled constellation — the inward anchor (basing).

        What the persona keeps returning to. Injected near identity so the
        response roots itself in established self-patterns.
        """
        row = self._db.execute(
            "SELECT id, label, members, weight, touched FROM constellations "
            "ORDER BY weight DESC, touched DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "label": row["label"],
            "size": len(json.loads(row["members"])),
            "weight": row["weight"], "touched": row["touched"],
        }

    def expand_constellation(self, handle) -> Optional[Dict]:
        """Heuristic endpoint: resolve a constellation handle (id or label
        fragment) to its full member contents — the <zoom> target."""
        self._require_loaded()
        row = None
        if isinstance(handle, int) or (isinstance(handle, str) and handle.isdigit()):
            row = self._db.execute(
                "SELECT id, label, members FROM constellations WHERE id=?",
                (int(handle),)).fetchone()
        else:
            row = self._db.execute(
                "SELECT id, label, members FROM constellations WHERE label LIKE ?",
                (f"%{handle}%",)).fetchone()
        if not row:
            return None
        member_ids = json.loads(row["members"])
        q = "SELECT id, role, content, turn_index FROM turns WHERE id IN (%s)" % ",".join(
            "?" * len(member_ids))
        members = [dict(r) for r in self._db.execute(q, member_ids).fetchall()]
        return {"id": row["id"], "label": row["label"], "members": members}

    def get_constellations(self) -> List[Dict]:
        """All crystallized constellations, strongest first."""
        self._require_loaded()
        rows = self._db.execute(
            "SELECT id, label, members, weight, touched, updated_at FROM constellations ORDER BY weight DESC"
        ).fetchall()
        return [
            {"id": r["id"], "label": r["label"],
             "members": json.loads(r["members"]),
             "weight": r["weight"], "touched": r["touched"],
             "updated_at": r["updated_at"]}
            for r in rows
        ]

    def get_recent_turns(self, n: int = 8) -> List[Dict]:
        """Get the last n turns (ring 2 — recent verbatim)."""
        rows = self._db.execute(
            """SELECT role, content, turn_index FROM turns
               WHERE session_id=?
               ORDER BY turn_index DESC LIMIT ?""",
            (self.session_id, n)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_by_ring(self, ring_id: int, limit: Optional[int] = None) -> List[Dict]:
        """Return all turns in a specific ring, optionally limited."""
        self._require_loaded()
        ring_id = int(ring_id)
        query = "SELECT * FROM turns WHERE session_id=? AND ring=? ORDER BY turn_index ASC"
        params: List[Any] = [self.session_id, ring_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = self._db.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def ring_label_for_id(ring_id: int) -> str:
        labels = ["identity", "task", "recent", "working", "background",
                  "archive", "deep", "constellation"]
        idx = int(ring_id)
        if 0 <= idx < len(labels):
            return labels[idx]
        return "recent"

    # ── Foveated ring block ───────────────────────────────────────────────────

    def weave_context(
        self,
        current_query: str,
        token_budget: Optional[int] = None,
    ) -> str:
        """
        Build the 7-ring foveated context block to inject before generation.
        Returns a formatted string ready for system prompt injection.

        Memory is formatted as discrete background notes — NOT as dialogue —
        so the model treats it as context rather than continuing the pattern.
        """
        self._require_loaded()
        budget = token_budget or self.token_budget
        rings: List[str] = []

        # Ring 0 — Identity
        identity_val = self.get_identity("system_context") or ""
        if identity_val:
            rings.append(f"[Identity] {identity_val}")

        # Ring 7 root — inward anchor: the pattern she keeps returning to.
        # Injected beside identity so responses root in established self.
        root = self.get_root()
        if root:
            rings.append(
                f"[Root — familiar ground] \"{root['label']}\" "
                f"({root['size']} linked memories, {root['touched']}x revisited)"
            )

        # Ring 2 — Recent (last 6 turns, compressed to key points)
        recent = self.get_recent_turns(6)
        if recent:
            recent_parts = []
            for t in recent:
                role = t['role']
                content = _truncate(t['content'], 150)
                # Format as context notes, not dialogue
                if role == 'user':
                    recent_parts.append(f"- User previously said: \"{content}\"")
                else:
                    recent_parts.append(f"- Assistant previously responded: \"{content}\"")
            rings.append("[Recent context]\n" + "\n".join(recent_parts))

        # Ring 5 — Archive (TF-IDF recall against current query)
        recalled_ids: List[int] = []
        if current_query:
            recalled = self.semantic_search(current_query, top_k=3)
            if recalled:
                recall_parts = []
                for r in recalled:
                    content = _truncate(r['content'], 120)
                    recall_parts.append(f"- \"{content}\"")
                rings.append("[Recalled from memory]\n" + "\n".join(recall_parts))
                recalled_ids = [int(r["turn_index"]) for r in recalled]
                # resolve turn_index -> row id for co-recall edges
                id_rows = self._db.execute(
                    "SELECT id FROM turns WHERE session_id=? AND turn_index IN (%s)"
                    % ",".join("?" * len(recalled_ids)),
                    [self.session_id] + recalled_ids,
                ).fetchall()
                recalled_ids = [r["id"] for r in id_rows]
                self._traverse(recalled_ids)

        # Ring 7 — Constellations (heuristic endpoints: land with content)
        # Settled clusters (touched >= 5) promote to Conclusions: stated as
        # flat knowledge, not just pattern pointers. The deal is closed.
        if current_query:
            consts = self._constellations_for(current_query, recalled_ids)
            if consts:
                settled = [c for c in consts if c["settled"]]
                forming = [c for c in consts if not c["settled"]]
                if settled:
                    rings.append(
                        "[Conclusions — settled knowledge]\n" + "\n".join(
                            f"- {c['label']}: \"{c['excerpt']}\"" for c in settled
                        )
                    )
                if forming:
                    rings.append(
                        "[Constellations — well-travelled patterns you can expand via c:<id>]\n"
                        + "\n".join(
                            f"- c:{c['id']} \"{c['label']}\" — {c['size']} linked memories"
                            + (f" · core: \"{c['excerpt']}\"" if c.get("excerpt") else "")
                            for c in forming
                        )
                    )

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
            self._db.execute("ALTER TABLE turns ADD COLUMN ring_label TEXT DEFAULT 'recent'")
        summary_cols = self._db.execute("PRAGMA table_info(summaries)").fetchall()
        summary_names = {row[1] for row in summary_cols}
        if "ring_label" not in summary_names:
            self._db.execute("ALTER TABLE summaries ADD COLUMN ring_label TEXT DEFAULT 'recent'")
        const_cols = self._db.execute("PRAGMA table_info(constellations)").fetchall()
        if "touched" not in {row[1] for row in const_cols}:
            self._db.execute("ALTER TABLE constellations ADD COLUMN touched INTEGER DEFAULT 0")


# ── Ring config default ───────────────────────────────────────────────────────

def _default_ring_config() -> Dict:
    return {
        "ring_0": {"label": "identity",   "max_tokens": 128,  "ttl_turns": None},
        "ring_1": {"label": "task",       "max_tokens": 256,  "ttl_turns": None},
        "ring_2": {"label": "recent",     "max_tokens": 512,  "ttl_turns": 8},
        "ring_3": {"label": "working",    "max_tokens": 512,  "ttl_turns": 32},
        "ring_4": {"label": "background", "max_tokens": 384,  "ttl_turns": 128},
        "ring_5": {"label": "archive",    "max_tokens": 256,  "ttl_turns": None},
        "ring_7": {"label": "constellation", "max_tokens": 192, "ttl_turns": None},
    }


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"
