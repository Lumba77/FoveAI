# FoveAI Memory Service
# Wraps Redis + ChromaDB persistence. Standalone microservice.
# Runs standalone so the SOUL can adopt existing memory processes via HTTP.
# Port: 8002

import os
import sys
import json
import time
import asyncio
import hashlib
from typing import List, Dict, Optional, Any
from datetime import datetime
from contextlib import asynccontextmanager

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Cognition"))

try:
    from fastapi import FastAPI, HTTPException
    from uvicorn import Config, Server
except ImportError:
    print("ERROR: fastapi/uvicorn not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)

try:
    import redis
except ImportError:
    redis = None

try:
    import chromadb
except ImportError:
    chromadb = None

KUZU_AVAILABLE = False

# --- Config ---
REDIS_HOST = os.getenv("FoveAI_REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("FoveAI_REDIS_PORT", "6379"))
CHROMA_PATH = os.getenv("FoveAI_CHROMA_PATH", os.path.join(os.path.dirname(__file__), "chroma_db"))
IDENTITY = os.getenv("FoveAI_IDENTITY", "jen")

# --- State ---
_redis_client = None
_chroma_client = None
_chroma_collection = None

def _get_redis():
    global _redis_client
    if _redis_client is None and redis:
        try:
            _redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=1, decode_responses=True)
            _redis_client.ping()
        except Exception as e:
            print(f"Redis unavailable: {e}")
            _redis_client = None
    return _redis_client

def _get_chroma():
    global _chroma_client, _chroma_collection
    if _chroma_client is None and chromadb:
        try:
            _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
            _chroma_collection = _chroma_client.get_or_create_collection(name=f"foveai_{IDENTITY}")
        except Exception as e:
            print(f"Chroma unavailable: {e}")
            _chroma_client = None
    return _chroma_collection

# Kuzu is deprecated and disabled in this version
def _get_kuzu():
    return None

def _init_kuzu_schema():
    pass

# --- Core Operations ---

def _memory_id(content: str, timestamp: float) -> str:
    return hashlib.sha256(f"{content}:{timestamp}".encode()).hexdigest()[:16]

def store_memory(content: str, role: str = "assistant", session_id: str = "default", topics: List[str] = None, importance: float = 0.5):
    ts = time.time()
    mem_id = _memory_id(content, ts)

    # Redis
    r = _get_redis()
    if r:
        key = f"foveai:{IDENTITY}:session:{session_id}"
        entry = json.dumps({"id": mem_id, "role": role, "content": content, "timestamp": ts, "importance": importance})
        try:
            r.lpush(key, entry)
            r.ltrim(key, 0, 1999)  # keep last 2000
        except Exception as e:
            print(f"Redis store error: {e}")

    # Chroma
    col = _get_chroma()
    if col:
        try:
            col.add(
                ids=[mem_id],
                documents=[content],
                metadatas=[{"role": role, "timestamp": ts, "session": session_id, "importance": importance}]
            )
        except Exception as e:
            print(f"Chroma store error: {e}")

    return {"id": mem_id, "stored": True, "layers": ["redis" if r else None, "chroma" if col else None, None]}

def search_similar(query: str, n: int = 5, session_id: str = None):
    results = []
    col = _get_chroma()
    if col:
        try:
            where_filter = {"session": session_id} if session_id else None
            r = col.query(query_texts=[query], n_results=n, where=where_filter)
            for i, doc in enumerate(r.get("documents", [[]])[0]):
                meta = r.get("metadatas", [[]])[0][i] if r.get("metadatas") else {}
                dist = r.get("distances", [[]])[0][i] if r.get("distances") else 0
                results.append({
                    "source": "chroma",
                    "content": doc,
                    "role": meta.get("role", "unknown"),
                    "distance": dist,
                    "timestamp": meta.get("timestamp")
                })
        except Exception as e:
            print(f"Chroma search error: {e}")

    return sorted(results, key=lambda x: x.get("distance", 0) or 0)[:n]

def get_session_history(session_id: str = "default", limit: int = 50):
    r = _get_redis()
    if r:
        try:
            key = f"foveai:{IDENTITY}:session:{session_id}"
            items = r.lrange(key, 0, limit - 1)
            return [json.loads(x) for x in items]
        except Exception as e:
            print(f"Redis history error: {e}")
    return []

def consolidate_sessions():
    """Night-time consolidation: Kuzu graph layer deprecated."""
    return {"consolidated": False, "reason": "kuzu deprecated"}

# --- FastAPI App ---

app = FastAPI(title="FoveAI Memory Service", version="1.0")

@app.post("/store")
async def api_store(request: Dict[str, Any]):
    result = store_memory(
        content=request.get("content", ""),
        role=request.get("role", "assistant"),
        session_id=request.get("session_id", "default"),
        topics=request.get("topics", []),
        importance=request.get("importance", 0.5)
    )
    return result

@app.post("/search")
async def api_search(request: Dict[str, Any]):
    results = search_similar(
        query=request.get("query", ""),
        n=request.get("n", 5),
        session_id=request.get("session_id")
    )
    return {"results": results, "count": len(results)}

@app.get("/history/{session_id}")
async def api_history(session_id: str, limit: int = 50):
    return {"session": session_id, "entries": get_session_history(session_id, limit)}

@app.post("/consolidate")
async def api_consolidate():
    return consolidate_sessions()

@app.get("/health")
async def api_health():
    layers = {
        "redis": _get_redis() is not None,
        "chroma": _get_chroma() is not None,
        "kuzu": False
    }
    return {"status": "ok", "identity": IDENTITY, "layers": layers}

if __name__ == "__main__":
    port = int(os.getenv("FoveAI_MEMORY_PORT", "8002"))
    host = os.getenv("FoveAI_MEMORY_HOST", "0.0.0.0")
    print(f"FoveAI Memory Service starting on {host}:{port}")
    print(f"Layers: Redis={REDIS_HOST}:{REDIS_PORT}, Chroma={CHROMA_PATH}")
    asyncio.run(Server(Config(app, host=host, port=port, log_level="info")).serve())