import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../Tools')))
try:
    import crypt_manager
except ImportError:
    crypt_manager = None
import json
import os
import time
from typing import List, Optional

# Local fallback when Redis is offline: persisted reference stills (base64) per session.
_REF_IMAGE_FALLBACK_PATH = os.getenv("FoveAI_REF_IMAGE_FALLBACK_PATH", "foveai_reference_images.json")

try:
    import chromadb
    _CHROMADB_AVAILABLE = True
except ImportError:
    _CHROMADB_AVAILABLE = False

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False



class ChatMessage:
    def __init__(self, role, content):
        self.role = role
        self.content = content

class ChatHistory:
    def __init__(self, messages):
        self.messages = messages

import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "db", "agent_memory.db")
_db_lock = threading.Lock()

class RedisMemory:
    def __init__(self, host="localhost", port=6379):
        self.use_redis = False
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with _db_lock:
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                # Create chat history table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON agent_chat_history(session_id);")
                
                # Create key-value store table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_key_value (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """)
                conn.commit()
            finally:
                conn.close()

    def _get_conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, key: str) -> Optional[str]:
        with _db_lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM agent_key_value WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    val = row[0]
                    if crypt_manager: val = crypt_manager.decrypt(val)
                    return val
                return None
            finally:
                conn.close()

    def set(self, key: str, value: str) -> None:
        with _db_lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO agent_key_value (key, value, updated_at) VALUES (?, ?, datetime('now')) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                    (key, crypt_manager.encrypt(value) if crypt_manager else value)
                )
                conn.commit()
            finally:
                conn.close()

    async def get_session_history(self, session_id: str) -> ChatHistory:
        with _db_lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT role, content FROM agent_chat_history WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                )
                rows = cursor.fetchall()
                return ChatHistory([ChatMessage(r[0], r[1]) for r in rows])
            finally:
                conn.close()

    async def clear_session_history(self, session_id: str) -> None:
        with _db_lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM agent_chat_history WHERE session_id = ?", (session_id,))
                conn.commit()
            finally:
                conn.close()

    async def add_message_to_session(self, session_id: str, role: str, content: str) -> None:
        with _db_lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO agent_chat_history (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, role, crypt_manager.encrypt(content) if crypt_manager else content)
                )
                conn.commit()
            finally:
                conn.close()

    def get_session_summary(self, session_id: str) -> str:
        raw = self.get(f"session_summary:{session_id}")
        return (raw or "").strip()

    def set_session_summary(self, session_id: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        max_chars = int(os.getenv("FoveAI_SESSION_SUMMARY_STORE_MAX_CHARS", "16000"))
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        self.set(f"session_summary:{session_id}", text)

    def _ref_redis_key(self, session_id: str) -> str:
        return f"foveai:ref_images:{session_id}"

    async def push_reference_image(
        self,
        session_id: str,
        b64: str,
        max_items: Optional[int] = None,
        max_b64_len: Optional[int] = None,
    ) -> None:
        max_items = max_items if max_items is not None else int(os.getenv("FoveAI_REF_IMAGE_MAX", "12"))
        max_b64_len = max_b64_len if max_b64_len is not None else int(os.getenv("FoveAI_REF_IMAGE_MAX_B64", "480000"))
        if not b64 or not isinstance(b64, str) or len(b64) < 64:
            return
        b64 = b64.strip()
        if len(b64) > max_b64_len:
            b64 = b64[:max_b64_len]
        
        key = self._ref_redis_key(session_id)
        raw_val = self.get(key)
        try:
            lst = json.loads(raw_val) if raw_val else []
            if not isinstance(lst, list):
                lst = []
        except Exception:
            lst = []
        lst.insert(0, b64)
        self.set(key, json.dumps(lst[:max_items]))

    def get_reference_images(self, session_id: str, limit: int = 4) -> List[str]:
        key = self._ref_redis_key(session_id)
        lim = max(1, min(int(limit), 24))
        raw_val = self.get(key)
        try:
            lst = json.loads(raw_val) if raw_val else []
            if not isinstance(lst, list):
                return []
            return [x for x in lst[:lim] if isinstance(x, str) and len(x) > 64]
        except Exception:
            return []

class VectorMemory:
    def __init__(
        self,
        llm_host: str,
        embed_model: str,
        collection_name: str = "experiential_long_term",
        local_engine=None,
    ):

        self.llm_host = llm_host
        self.embed_model = embed_model
        self.local_engine = local_engine
        self.chroma_client = None
        self.long_term = None
        self.lore_ledger = None

        if _CHROMADB_AVAILABLE:
            try:
                self.chroma_client = chromadb.Client()
                # --- LAYERED COLLECTIONS ---
                # 1. Experiential (Long-Term events)
                self.long_term = self.chroma_client.get_or_create_collection("long_term")
                # 2. Lore (Refined foundational knowledge)
                self.lore_ledger = self.chroma_client.get_or_create_collection("lore_ledger")
                provider = "LocalGGUF" if local_engine else "API"
                print(f"VectorMemory: Layered Architecture initialized ({provider}).")
            except Exception as e:
                print(f"VectorMemory: ChromaDB init failed, running without vector memory: {e}")
                self.chroma_client = None
        else:
            print("VectorMemory: chromadb not installed, running without vector memory.")


    async def refine_memory_layer(self, session_id: str, summary_text: str):
        """Allows Ratatosk to distill multiple experiential memories into a single Lore entry."""
        try:
            await self.add_memory(session_id, summary_text, collection="lore")
            print(f"Ratatosk: Distilled experience into foundational Lore for {session_id}.")
        except Exception as e:
            print(f"Memory Refinement Error: {e}")

    async def generate_embedding(self, text: str) -> list[float]:
        # 1. Try local engine first (Zero-Copy)
        if self.local_engine:
            emb = self.local_engine.embed(text)
            if emb: return emb
            
        # 2. Fallback to API
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.llm_host.rstrip('/')}/embeddings",
                    json={"model": self.embed_model, "input": text},
                    timeout=30.0
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", [{}])[0].get("embedding", [])
        except Exception as e:
            print(f"Error generating embedding (API fallback): {e}")
            return []


    async def add_memory(self, session_id: str, text: str, metadata: dict = None, collection: str = "long_term"):
        if not self.chroma_client or not self.long_term:
            return
        try:
            embedding = await self.generate_embedding(text)
            if not embedding: return

            target = self.lore_ledger if collection == "lore" else self.long_term
            if target is None: return
            
            if metadata is None: metadata = {}
            metadata["session_id"] = session_id
            metadata["text"] = text
            metadata["layer"] = collection

            doc_id = f"{session_id}-{collection}-{hash(text)}-{time.time()}"

            target.add(
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata],
                ids=[doc_id],
            )
            print(f"Memory [{collection.upper()}] added for {session_id}: {text[:50]}...")
        except Exception as e:
            print(f"Error adding memory: {e}")

    async def retrieve_memories(
        self,
        session_id: str,
        query_text: str,
        n_results: int = 5,
        include_lore: bool = True,
        lore_n_results: int = 2,
    ) -> list[dict]:
        if not self.chroma_client or not self.long_term:
            return []
        try:
            query_embedding = await self.generate_embedding(query_text)
            if not query_embedding: return []

            lore_k = max(0, int(lore_n_results))

            # 1. Search Long-Term Experiences
            results = self.long_term.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where={"session_id": session_id},
                include=["documents", "metadatas", "distances"],
            )

            retrieved = []
            if results and results["documents"]:
                for i in range(len(results["documents"][0])):
                    retrieved.append({"text": results["documents"][0][i], "layer": "long_term", "dist": results["distances"][0][i]})

            # 2. Search Refined Lore (Priority Knowledge)
            if include_lore and lore_k > 0 and self.lore_ledger:
                lore_res = self.lore_ledger.query(
                    query_embeddings=[query_embedding],
                    n_results=lore_k,
                    where={"session_id": session_id},
                    include=["documents", "metadatas", "distances"],
                )
                if lore_res and lore_res["documents"]:
                    for i in range(len(lore_res["documents"][0])):
                        retrieved.append({"text": lore_res["documents"][0][i], "layer": "lore", "dist": lore_res["distances"][0][i]})

            # Sort by distance (relevance)
            retrieved.sort(key=lambda x: x["dist"])
            return retrieved[:n_results]
        except Exception as e:
            print(f"Error retrieving memories: {e}")
            return []

    def clear_session_memories(self, session_id: str):
        if not self.chroma_client:
            return
        try:
            for coll in (self.long_term, self.lore_ledger):
                if coll:
                    coll.delete(where={"session_id": session_id})
            print(f"Cleared all vector memories for session {session_id}.")
        except Exception as e:
            print(f"Error clearing session memories from ChromaDB: {e}")
