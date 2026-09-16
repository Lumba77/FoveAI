#!/usr/bin/env python3
"""
FoveAI Library Indexer & RAG Engine
==================================
Indexes books, encyclopedias, and theology/philosophy documents (TXT, MD, PDF)
into a persistent ChromaDB vector store using the local LLM embedding model.
"""

import os
import sys
import argparse
import json
import httpx
from pathlib import Path

# Try importing chromadb
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "db" / "library_vector_db"
DEFAULT_LIBRARY_DIR = PROJECT_ROOT / "Library"

# Load embedding config from .env or fallback
EMBED_URL = os.getenv("FoveAI_EMBEDDING_URL", "http://127.0.0.1:8888/v1/embeddings")
EMBED_MODEL = os.getenv("FoveAI_MODEL_EMBEDDING_ID", "nomic-embed-text:latest")

def get_embedding(text: str) -> list:
    """Get embedding vector from the local LLM server."""
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                EMBED_URL,
                json={"model": EMBED_MODEL, "input": text}
            )
            if resp.status_code == 200:
                return resp.json().get("data", [{}])[0].get("embedding", [])
    except Exception as e:
        # Fallback to local Ollama port if default fails
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    "http://127.0.0.1:11434/v1/embeddings",
                    json={"model": EMBED_MODEL, "input": text}
                )
                if resp.status_code == 200:
                    return resp.json().get("data", [{}])[0].get("embedding", [])
        except Exception:
            pass
        print(f"⚠️ Warning: Embedding generation failed: {e}", file=sys.stderr)
    return []

def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    step = chunk_size - chunk_overlap
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

def index_library(library_dir: Path):
    """Index all documents in the library directory."""
    if not CHROMADB_AVAILABLE:
        print("❌ Error: chromadb is not installed in the python environment.")
        return

    if not library_dir.exists():
        library_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created library directory at {library_dir}. Place your TXT, MD, or PDF files there and rerun.")
        return

    # Initialize persistent Chroma client
    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_or_create_collection("personal_library")

    print(f"📡 Scanning library: {library_dir}...")
    supported_extensions = {'.txt', '.md', '.html'}
    
    # Try including PDF parser if available
    has_pdf_reader = False
    pdf_lib = None
    try:
        import pypdf
        has_pdf_reader = True
        pdf_lib = "pypdf"
    except ImportError:
        try:
            import PyPDF2
            has_pdf_reader = True
            pdf_lib = "PyPDF2"
        except ImportError:
            pass

    files = [p for p in library_dir.rglob("*") if p.suffix.lower() in supported_extensions or (p.suffix.lower() == '.pdf' and has_pdf_reader)]
    if not files:
        print("ℹ️ No documents found to index. Add text, markdown, HTML, or PDF files to the directory.")
        return

    indexed_count = 0
    for file_path in files:
        rel_path = file_path.relative_to(library_dir)
        print(f"📄 Processing {rel_path}...")
        
        text = ""
        try:
            if file_path.suffix.lower() == '.pdf' and has_pdf_reader:
                with open(file_path, 'rb') as f:
                    if pdf_lib == "pypdf":
                        reader = pypdf.PdfReader(f)
                    else:
                        reader = PyPDF2.PdfReader(f)
                    text = " ".join([page.extract_text() or "" for page in reader.pages])
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                
                if file_path.suffix.lower() == '.html':
                    import re
                    # Strip script and style tags completely
                    text = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', ' ', text, flags=re.IGNORECASE)
                    text = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', ' ', text, flags=re.IGNORECASE)
                    # Strip remaining HTML tags
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()
        except Exception as fe:
            print(f"⚠️ Error reading {rel_path}: {fe}")
            continue

        chunks = chunk_text(text)
        if not chunks:
            continue

        print(f"   Splitting into {len(chunks)} chunks...")
        for idx, chunk in enumerate(chunks):
            embedding = get_embedding(chunk)
            if not embedding:
                print("   ❌ Failed to get embedding. Skipping chunk.")
                continue

            chunk_id = f"{rel_path.as_posix()}_{idx}"
            collection.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                metadatas=[{"source": rel_path.as_posix(), "chunk": idx}],
                documents=[chunk]
            )
        indexed_count += 1

    print(f"🎉 Successfully indexed {indexed_count} document(s).")

def query_library(query: str, n_results: int = 3) -> list:
    """Retrieve top matches for a query from the indexed library."""
    if not CHROMADB_AVAILABLE:
        return []

    if not DB_DIR.exists():
        return []

    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_or_create_collection("personal_library")
    
    query_emb = get_embedding(query)
    if not query_emb:
        return []

    results = collection.query(
        query_embeddings=[query_emb],
        n_results=n_results
    )
    
    matches = []
    if results and 'documents' in results and results['documents']:
        documents = results['documents'][0]
        metadatas = results['metadatas'][0] if 'metadatas' in results else []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            matches.append({
                "text": doc,
                "source": meta.get("source", "unknown"),
                "chunk": meta.get("chunk", 0)
            })
    return matches

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FoveAI Library RAG Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Index command
    index_parser = subparsers.add_parser("index", help="Index documents in the library")
    index_parser.add_argument("--dir", type=str, default=str(DEFAULT_LIBRARY_DIR), help="Directory to index")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search the indexed library")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument("-n", "--results", type=int, default=3, help="Number of results")

    args = parser.parse_args()

    if args.command == "index":
        index_library(Path(args.dir))
    elif args.command == "search":
        matches = query_library(args.query, args.results)
        if not matches:
            print("ℹ️ No matches found or vector database is empty.")
        else:
            print(f"\n📚 Found {len(matches)} matching passage(s):\n")
            for i, match in enumerate(matches, 1):
                print(f"[{i}] Source: {match['source']} (Chunk {match['chunk']})")
                print(f"---")
                print(match['text'])
                print(f"---\n")
