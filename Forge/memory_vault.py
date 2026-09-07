"""
Memory Vault — Persistent Cross-Session Memory (Tier 4).
Keyword-indexed JSON store. v1 has no embeddings dependency.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from mesh_bus import mesh_bus, MeshEvent

logger = logging.getLogger("forge.memory_vault")


class MemoryVault:
    """Persistent memory store for cross-session context."""
    
    MAX_ENTRIES = 10000
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vault_file = self.data_dir / "memory_vault.jsonl"
        self._entries: List[Dict] = []
        self._load_vault()
        self._setup_handlers()
    
    def _setup_handlers(self):
        mesh_bus.subscribe("checkpoint_created", self._on_checkpoint)
        mesh_bus.subscribe("session_started", self._on_session_started)
    
    def store(self, entry_type: str, content: str, session_id: str,
              file_path: Optional[str] = None, metadata: Dict = None) -> None:
        entry = {
            "id": f"{session_id}_{int(time.time() * 1000)}",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "content": content[:5000],
            "file_path": file_path,
            "metadata": metadata or {}
        }
        self._entries.append(entry)
        self._append_to_file(entry)
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-int(self.MAX_ENTRIES * 0.8):]
    
    def query(self, entry_type: str = None, since_days: int = 30, limit: int = 5) -> List[Dict]:
        results = []
        for entry in reversed(self._entries):
            if entry_type and entry["type"] != entry_type:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results
    
    def get_session_context(self, current_session_id: str, limit: int = 3) -> str:
        results = [e for e in self._entries if e["session_id"] != current_session_id][-limit:]
        if not results:
            return ""
        lines = ["## Past Session Context", ""]
        for entry in results:
            lines.append(f"**{entry['type']}** ({entry['timestamp'][:10]}): {entry['content'][:200]}")
        return "\n".join(lines)
    
    def _load_vault(self) -> None:
        if not self.vault_file.exists():
            return
        try:
            with open(self.vault_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            self._entries.append(json.loads(line))
                        except:
                            pass
            logger.info(f"Loaded {len(self._entries)} entries from vault")
        except Exception as e:
            logger.error(f"Failed to load vault: {e}")
    
    def _append_to_file(self, entry: Dict) -> None:
        try:
            with open(self.vault_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to append: {e}")
    
    def _on_checkpoint(self, event: MeshEvent) -> None:
        if event.session_id:
            data = event.data
            content = f"Checkpoint: {data.get('tokens_before', 0)} -> {data.get('tokens_after', 0)} tokens"
            self.store("checkpoint", content, event.session_id, metadata=data)
    
    def _on_session_started(self, event: MeshEvent) -> None:
        if event.session_id:
            content = f"Session started: {event.data.get('model', 'unknown')}"
            self.store("session_started", content, event.session_id, metadata=event.data)
    
    def record_file_edit(self, session_id: str, file_path: str, description: str) -> None:
        self.store("file_edit", description, session_id, file_path)
    
    def record_decision(self, session_id: str, decision: str, context: str = "") -> None:
        self.store("decision", f"Decision: {decision}\nContext: {context}", session_id)


memory_vault = MemoryVault()
