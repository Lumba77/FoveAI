#!/usr/bin/env python3
"""
Import FoveAI sessions from backend/Cognition/sessions.json to MCP memory
"""

import json
from pathlib import Path

# FoveAI paths
FoveAI_ROOT = Path(
    os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent)
)
SESSIONS_PATH = FoveAI_ROOT / "backend/Cognition/sessions.json"
MEMORY_INDEX_PATH = FoveAI_ROOT / ".logs" / "memory_index.json"


def load_sessions():
    """Load sessions from backend/Cognition/sessions.json"""
    if not SESSIONS_PATH.exists():
        print(f"Sessions file not found: {SESSIONS_PATH}")
        return []

    with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    sessions = []
    for session_id, messages in data.items():
        if isinstance(messages, str):
            messages = json.loads(messages)

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if content and role in ("user", "ai", "emotion"):
                # Map 'ai' to 'assistant'
                if role == "ai":
                    role = "assistant"

                sessions.append(
                    {
                        "role": role,
                        "content": content,
                        "source": "foveai_session",
                        "session_id": session_id,
                    }
                )

    return sessions


def load_memory():
    """Load existing memory index"""
    if not MEMORY_INDEX_PATH.exists():
        return []

    with open(MEMORY_INDEX_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("conversations", [])


def save_memory(conversations):
    """Save memory index"""
    MEMORY_INDEX_PATH.parent.mkdir(exist_ok=True)

    with open(MEMORY_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "conversations": conversations[-500:],  # Keep last 500
                "last_updated": "2026-05-12T12:58:00",
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def main():
    print("Loading FoveAI sessions...")
    sessions = load_sessions()
    session_count = len(set(s["session_id"] for s in sessions))
    print(f"Found {len(sessions)} messages in {session_count} sessions")

    print("Loading existing memory...")
    memory = load_memory()
    print(f"Existing memory has {len(memory)} conversations")

    # Add sessions to memory
    print("Importing sessions to memory...")
    memory.extend(sessions)

    # Save updated memory
    save_memory(memory)
    print(f"Memory now has {len(memory)} conversations")
    print("Import complete!")


if __name__ == "__main__":
    main()
