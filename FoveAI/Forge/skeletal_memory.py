import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger("forge.skeletal_memory")

# Load dotenv from workspace root
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.isfile(_env_path):
    try:
        import dotenv

        dotenv.load_dotenv(_env_path, override=False)
    except ImportError:
        pass

OLLAMA_HOST = (os.getenv("OLLAMA_HOST", "").strip() or "http://localhost:11434").rstrip(
    "/"
)
SMOLLM_HELPER_MODEL = os.getenv("SMOLLM_HELPER_MODEL", "").strip() or "smollm2:latest"
LMSTUDIO_URL = (
    os.getenv("LMSTUDIO_URL", "").strip() or "http://localhost:8888"
).rstrip("/")
LMSTUDIO_MAIN_MODEL = os.getenv("LMSTUDIO_MAIN_MODEL", "").strip() or "qwen2.5-coder:3b"

UNSLOTH_URL = (
    os.getenv(
        "FoveAI_UNSLOTH_BASE_URL",
        os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1"),
    )
    .strip()
    .rstrip("/")
)
UNSLOTH_MODEL = os.getenv(
    "FoveAI_MODEL_LOCAL_ID", "unsloth/Qwen3.5-4B-MTP-GGUF"
).strip()

# InMemory vault for skeletal nodes to keep it fast
# Structures: list of dicts. Keys: node_id, category, summary, confidence, raw_sources
_skeletal_nodes: list[dict[str, Any]] = []
_node_counter = 0


def get_node_id() -> str:
    global _node_counter
    _node_counter += 1
    return f"NODE:{_node_counter:03d}"


def clear_memory():
    global _skeletal_nodes, _node_counter
    _skeletal_nodes = []
    _node_counter = 0


def get_active_nodes() -> list[dict[str, Any]]:
    return _skeletal_nodes


def get_node_by_id(node_id: str) -> dict[str, Any] | None:
    for node in _skeletal_nodes:
        if node["node_id"] == node_id:
            return node
    return None


def jaccard_similarity(s1: str, s2: str) -> float:
    """Compute Jaccard similarity of two strings based on lowercase word sets."""
    w1 = set(re.findall(r"\b[a-z0-9_-]+\b", s1.lower()))
    w2 = set(re.findall(r"\b[a-z0-9_-]+\b", s2.lower()))
    if not w1 or not w2:
        return 0.0
    return len(w1.intersection(w2)) / len(w1.union(w2))


async def query_local_llm(prompt: str) -> str:
    """Query local LLM (Unsloth, Ollama, or LM Studio) to perform extraction."""
    import httpx

    # 1. Attempt Unsloth first (since it is the active local engine)
    try:
        url = f"{UNSLOTH_URL.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={
                    "model": UNSLOTH_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 256,
                },
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.debug("Unsloth query failed: %s", e)

    # 2. Attempt Ollama
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": SMOLLM_HELPER_MODEL, "prompt": prompt, "stream": False},
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
    except Exception as e:
        logger.debug("Ollama query failed: %s", e)

    # 3. Fallback to LM Studio
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{LMSTUDIO_URL}/v1/chat/completions",
                json={
                    "model": LMSTUDIO_MAIN_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 256,
                },
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.debug("LM Studio query failed: %s", e)

    return ""


async def extract_nodes_from_turn(turn_text: str) -> list[dict[str, Any]]:
    """Use the local model to extract structural memory nodes from a turn."""
    if not turn_text.strip():
        return []

    prompt = f"""You are a knowledge extraction engine.
Analyze the following conversation turn and extract key structural nodes.
Extract:
- decisions (e.g., choice of libraries, architectural changes)
- resolved_bugs (bugs that were fixed)
- codebase_changes (files modified and why)
- user_preferences (explicit requests or habits)

Provide output ONLY as a valid JSON array of objects, where each object has:
- "category": "decision" | "codebase" | "bug" | "preference"
- "summary": A very brief, 1-sentence description (max 15 words).

Do not include any thinking tags, introduction, markdown blocks, or explanation. Output raw JSON.

Turn:
{turn_text}
"""
    raw_response = await query_local_llm(prompt)
    if not raw_response:
        return []

    # Clean JSON format (sometimes models wrap in ```json ... ```)
    clean_json = raw_response
    if "```json" in clean_json:
        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_json:
        clean_json = clean_json.split("```")[1].split("```")[0].strip()

    try:
        extracted = json.loads(clean_json)
        if isinstance(extracted, list):
            return [
                {
                    "category": item.get("category", "decision"),
                    "summary": item.get("summary", "").strip(),
                }
                for item in extracted
                if item.get("summary")
            ]
    except Exception as e:
        logger.warning("Failed to parse extracted JSON: %s (Raw: %s)", e, raw_response)
        # Try a regex recovery for simple cases
        recovered = []
        matches = re.findall(
            r'"category":\s*"([^"]+)",\s*"summary":\s*"([^"]+)"', clean_json
        )
        for cat, summ in matches:
            recovered.append({"category": cat, "summary": summ})
        return recovered

    return []


def recycle_node(node: dict[str, Any], session_id: str = "default_session"):
    """Recycle a verified node to the persistent memory vault."""
    try:
        from memory_vault import memory_vault

        content = f"[{node['node_id']}] ({node['category'].upper()}) {node['summary']}"
        context = "\nSources:\n" + "\n".join(node["raw_sources"])
        memory_vault.store(
            entry_type="recycled_context",
            content=f"{content}\n{context}",
            session_id=session_id,
            metadata={
                "node_id": node["node_id"],
                "category": node["category"],
                "confidence": node["confidence"],
            },
        )
        logger.info(f"Recycled {node['node_id']} to Memory Vault")
    except Exception as e:
        logger.warning("Failed to recycle node: %s", e)


def consolidate_nodes(
    new_nodes: list[dict[str, Any]],
    turn_raw_text: str,
    similarity_threshold: float = 0.5,
) -> list[str]:
    """
    Consolidate new nodes with existing nodes.
    Returns a list of node_ids that were verified/reinforced.
    """
    reinforced_ids = []

    for new_node in new_nodes:
        summary = new_node["summary"]
        category = new_node["category"]

        # Check if it matches any existing node
        matched = False
        for existing in _skeletal_nodes:
            if existing["category"] == category:
                sim = jaccard_similarity(existing["summary"], summary)
                if sim >= similarity_threshold:
                    # Semantic overlap! Merge them
                    existing["confidence"] += 1
                    # Keep the longer summary
                    if len(summary) > len(existing["summary"]):
                        existing["summary"] = summary
                    if turn_raw_text not in existing["raw_sources"]:
                        existing["raw_sources"].append(turn_raw_text)

                    # Recycle node when double verified
                    if existing["confidence"] == 2:
                        recycle_node(existing)

                    reinforced_ids.append(existing["node_id"])
                    matched = True
                    break

        if not matched:
            # Create a new node
            node_id = get_node_id()
            _skeletal_nodes.append(
                {
                    "node_id": node_id,
                    "category": category,
                    "summary": summary,
                    "confidence": 1,
                    "raw_sources": [turn_raw_text],
                }
            )
            reinforced_ids.append(node_id)

    return reinforced_ids


def build_skeletal_index() -> str:
    """Build the [SKELETAL CONTEXT INDEX] block for system prompt injection."""
    if not _skeletal_nodes:
        return ""

    lines = ["[SKELETAL CONTEXT INDEX]"]
    for node in _skeletal_nodes:
        # Show category and confidence
        lines.append(
            f"  - [{node['node_id']}] ({node['category'].upper()}, confidence: {node['confidence']}) {node['summary']}"
        )
    return "\n".join(lines)


def should_prune_turn(turn_raw_text: str, prune_threshold: int = 3) -> bool:
    """
    Check if a turn's raw text can be pruned because all derived nodes
    have achieved confidence >= prune_threshold.
    """
    derived_nodes = []
    for node in _skeletal_nodes:
        if turn_raw_text in node["raw_sources"]:
            derived_nodes.append(node)

    if not derived_nodes:
        return False

    # All derived nodes must be verified (confidence >= prune_threshold)
    return all(node["confidence"] >= prune_threshold for node in derived_nodes)
