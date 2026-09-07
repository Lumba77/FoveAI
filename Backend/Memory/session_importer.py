#!/usr/bin/env python3
"""
FoveAI Session Importer & Summarizer

Imports previous conversation sessions and summarizes them using FoveAI LLM
for storage in both local JSON memory and Cognee knowledge graph.

Features:
- Import from VS Code Cline history files
- Import from CON Vessel history
- Summarize sessions using Soul (compagent) LLM
- Store in Cognee graph for semantic search
- Structured memory with tags and categories
"""
import os
import sys
import json
import re
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# FoveAI paths
FoveAI_ROOT = Path(os.getenv("FoveAI_ROOT", "/home/lumba/FoveAI-lite"))
CLINE_MEMORY_PATH = FoveAI_ROOT / ".logs" / "cline_memory.json"
CON_HISTORY_PATH = FoveAI_ROOT / "frontend/CON_vessel" / "con_history.json"
SESSION_SUMMARIES_PATH = FoveAI_ROOT / ".logs" / "session_summaries.json"
COGNEE_IMPORT_PATH = FoveAI_ROOT / ".logs" / "cognee_import_queue.jsonl"

# Cognee config
COGNEE_BASE_URL = os.getenv("FoveAI_COGNEE_BASE_URL", "http://localhost:8402")
COGNEE_ENABLED = os.getenv("FoveAI_COGNEE_ENABLED", "false").lower() in ("1", "true", "yes")
COGNEE_DATASET = os.getenv("FoveAI_COGNEE_DATASET", "foveai_sessions")
COGNEE_API_KEY = os.getenv("FoveAI_COGNEE_API_KEY", "")

# Soul LLM config
SOUL_URL = os.getenv("SOUL_URL", "http://localhost:8402").rstrip("/")


class SessionImporter:
    """Import and summarize conversation sessions."""
    
    def __init__(self):
        self.sessions = []
        self.summaries = []
        self.load_existing_summaries()
    
    def load_existing_summaries(self):
        """Load previously created summaries."""
        try:
            if SESSION_SUMMARIES_PATH.exists():
                with open(SESSION_SUMMARIES_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.summaries = data.get("summaries", [])
                    print(f"Loaded {len(self.summaries)} existing summaries", file=sys.stderr)
        except Exception as e:
            print(f"Error loading summaries: {e}", file=sys.stderr)
    
    def save_summaries(self):
        """Persist summaries to disk."""
        try:
            with open(SESSION_SUMMARIES_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "summaries": self.summaries,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving summaries: {e}", file=sys.stderr)
    
    def import_cline_history(self, cline_history_dir: Optional[Path] = None) -> List[Dict]:
        """
        Import VS Code Cline conversation history.
        Looks for JSON files in typical Cline storage locations.
        """
        imported = []
        
        # Common Cline history locations (including WSL2 VSCode Server)
        search_paths = [
            Path.home() / ".vscode-server" / "data" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "tasks",
            Path.home() / ".vscode" / "extensions" / "saoudrizwan.claude-dev" / "history",
            Path.home() / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "history",
            FoveAI_ROOT / ".logs" / "cline_history",
        ]
        
        if cline_history_dir:
            search_paths.insert(0, cline_history_dir)
        
        for search_path in search_paths:
            if not search_path.exists():
                continue
            
            print(f"Scanning Cline history: {search_path}", file=sys.stderr)
            
            # Search recursively for conversation files
            for task_dir in search_path.iterdir():
                if not task_dir.is_dir():
                    continue
                
                # Look for api_conversation_history.json and ui_messages.json
                for conv_file in task_dir.glob("*.json"):
                    try:
                        with open(conv_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        messages = []
                        
                        # Handle different Cline file formats
                        if isinstance(data, list):
                            # Data is directly a list of messages
                            messages = data
                        elif isinstance(data, dict):
                            # Data is a dict with message arrays
                            messages = (
                                data.get("messages", []) or 
                                data.get("conversation", []) or 
                                data.get("history", []) or
                                data.get("api_conversation_history", []) or
                                data.get("ui_messages", []) or
                                data.get("context_history", [])
                            )
                        
                        if messages:
                            session = {
                                "source": "cline",
                                "file": str(conv_file),
                                "task_id": task_dir.name,
                                "timestamp": data.get("timestamp", conv_file.stat().st_mtime) if isinstance(data, dict) else conv_file.stat().st_mtime,
                                "messages": messages,
                                "raw_data": data if isinstance(data, dict) else {}
                            }
                            imported.append(session)
                            print(f"  Imported: {task_dir.name}/{conv_file.name} ({len(messages)} messages)", file=sys.stderr)
                    except Exception as e:
                        print(f"  Error reading {conv_file}: {e}", file=sys.stderr)
        
        print(f"Imported {len(imported)} Cline sessions", file=sys.stderr)
        return imported
    
    def import_con_vessel_history(self) -> List[Dict]:
        """Import CON Vessel conversation history."""
        imported = []
        
        if not CON_HISTORY_PATH.exists():
            print("CON Vessel history not found", file=sys.stderr)
            return imported
        
        try:
            with open(CON_HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            if history:
                session = {
                    "source": "con_vessel",
                    "file": str(CON_HISTORY_PATH),
                    "timestamp": datetime.now().isoformat(),
                    "messages": history
                }
                imported.append(session)
                print(f"Imported CON Vessel history ({len(history)} messages)", file=sys.stderr)
        except Exception as e:
            print(f"Error reading CON Vessel history: {e}", file=sys.stderr)
        
        return imported
    
    def summarize_session(self, session: Dict, use_llm: bool = True) -> Dict:
        """
        Summarize a conversation session.
        
        Uses FoveAI LLM (Soul) to extract:
        - Main topics discussed
        - Key decisions/actions taken
        - Code changes or files modified
        - Problems solved
        - Follow-up tasks
        """
        messages = session.get("messages", [])
        if not messages:
            return {"error": "No messages to summarize"}
        
        # Build conversation text
        conv_text = self._messages_to_text(messages)
        
        # Use LLM for summarization
        if use_llm:
            summary = self._llm_summarize(conv_text)
        else:
            summary = self._extractive_summary(messages)
        
        # Add metadata
        summary["session_id"] = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.summaries)}"
        summary["source"] = session.get("source", "unknown")
        summary["message_count"] = len(messages)
        summary["created_at"] = datetime.now().isoformat()
        
        # Extract tags
        summary["tags"] = self._extract_tags(summary)
        
        self.summaries.append(summary)
        self.save_summaries()
        
        return summary
    
    def _messages_to_text(self, messages: List[Dict]) -> str:
        """Convert message list to text format."""
        lines = []
        for msg in messages[-50:]:  # Last 50 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "") or msg.get("text", "")
            if isinstance(content, list):
                # Handle multimodal content
                content = " ".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )
            if content:
                lines.append(f"{role}: {content[:500]}")  # Truncate long messages
        return "\n\n".join(lines)
    
    def _llm_summarize(self, conversation: str) -> Dict:
        """Use Soul LLM to generate structured summary."""
        prompt = f"""Analyze this conversation session and provide a structured summary:

{conversation}

Respond with ONLY valid JSON in this format:
{{
    "title": "Brief session title",
    "topics": ["topic1", "topic2"],
    "summary": "2-3 sentence overview of what was accomplished",
    "decisions": ["key decision 1", "key decision 2"],
    "actions_taken": ["action 1", "action 2"],
    "files_modified": ["file1.py", "file2.js"],
    "problems_solved": ["problem description"],
    "follow_up_tasks": ["task 1", "task 2"],
    "technical_details": "Any important technical context",
    "category": "coding|planning|debugging|architecture|creative|other"
}}
"""
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(f"{SOUL_URL}/compagent", json={
                    "input": prompt,
                    "session_id": "session_summarizer",
                    "skip_features": True
                })
                
                if resp.status_code == 200:
                    response_text = resp.json().get("response", "")
                    # Extract JSON from response
                    json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                    
            return self._extractive_summary([])
        except Exception as e:
            print(f"LLM summarization error: {e}", file=sys.stderr)
            return self._extractive_summary([])
    
    def _extractive_summary(self, messages: List[Dict]) -> Dict:
        """Fallback extractive summary without LLM."""
        topics = set()
        for msg in messages:
            content = msg.get("content", "") or ""
            # Extract file references
            for match in re.findall(r'[\w./-]+\.(py|js|ts|json|md|sh|ps1|cmd)', content):
                topics.add(f"file:{match}")
            # Extract code blocks
            if '```' in content:
                topics.add("code_discussion")
        
        return {
            "title": f"Session {len(self.summaries) + 1}",
            "topics": list(topics)[:10],
            "summary": "Session summary (extractive mode)",
            "decisions": [],
            "actions_taken": [],
            "files_modified": [],
            "problems_solved": [],
            "follow_up_tasks": [],
            "technical_details": "",
            "category": "other"
        }
    
    def _extract_tags(self, summary: Dict) -> List[str]:
        """Extract searchable tags from summary."""
        tags = []
        
        # Add category
        category = summary.get("category", "other")
        tags.append(f"category:{category}")
        
        # Add topics
        for topic in summary.get("topics", [])[:5]:
            tags.append(f"topic:{topic}")
        
        # Add source
        tags.append(f"source:{summary.get('source', 'unknown')}")
        
        # Add files as tags
        for f in summary.get("files_modified", [])[:5]:
            tags.append(f"file:{f}")
        
        return tags
    
    def export_to_cognee(self, summary: Dict) -> bool:
        """
        Export summary to Cognee knowledge graph.
        Posts to Cognee ingest endpoint for graph indexing.
        """
        if not COGNEE_ENABLED:
            print("Cognee not enabled, skipping export", file=sys.stderr)
            return False
        
        # Prepare document for Cognee
        document = {
            "id": summary.get("session_id"),
            "title": summary.get("title", "Untitled Session"),
            "content": self._summary_to_text(summary),
            "metadata": {
                "source": summary.get("source"),
                "category": summary.get("category"),
                "tags": summary.get("tags", []),
                "created_at": summary.get("created_at")
            }
        }
        
        # Queue for Cognee import
        try:
            with open(COGNEE_IMPORT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(document) + "\n")
        except Exception as e:
            print(f"Error queuing for Cognee: {e}", file=sys.stderr)
            return False
        
        # Try direct ingest if Cognee is available
        try:
            headers = {"Content-Type": "application/json"}
            if COGNEE_API_KEY:
                headers["X-Api-Key"] = COGNEE_API_KEY
            
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{COGNEE_BASE_URL}/api/v1/documents",
                    json=document,
                    headers=headers
                )
                
                if resp.status_code in (200, 201, 202):
                    print(f"Exported to Cognee: {summary.get('session_id')}", file=sys.stderr)
                    return True
                else:
                    print(f"Cognee ingest failed: {resp.status_code}", file=sys.stderr)
                    return False
                    
        except Exception as e:
            print(f"Cognee export error: {e}", file=sys.stderr)
            return False
    
    def _summary_to_text(self, summary: Dict) -> str:
        """Convert summary to text for Cognee storage."""
        lines = [
            f"Title: {summary.get('title', 'Untitled')}",
            f"Category: {summary.get('category', 'other')}",
            f"Summary: {summary.get('summary', '')}",
        ]
        
        if summary.get("topics"):
            lines.append(f"Topics: {', '.join(summary['topics'])}")
        
        if summary.get("decisions"):
            lines.append(f"Decisions: {'; '.join(summary['decisions'])}")
        
        if summary.get("actions_taken"):
            lines.append(f"Actions: {'; '.join(summary['actions_taken'])}")
        
        if summary.get("technical_details"):
            lines.append(f"Technical: {summary['technical_details']}")
        
        return "\n".join(lines)
    
    def search_summaries(self, query: str) -> List[Dict]:
        """Search summaries by keyword."""
        query_lower = query.lower()
        results = []
        
        for summary in self.summaries:
            # Search in all fields
            text = json.dumps(summary).lower()
            if query_lower in text:
                results.append(summary)
        
        return results


def main():
    """CLI entry point for session importer."""
    import argparse
    
    parser = argparse.ArgumentParser(description="FoveAI Session Importer")
    parser.add_argument("--import-cline", action="store_true", help="Import Cline history")
    parser.add_argument("--import-con", action="store_true", help="Import CON Vessel history")
    parser.add_argument("--summarize", action="store_true", help="Summarize imported sessions")
    parser.add_argument("--export-cognee", action="store_true", help="Export to Cognee")
    parser.add_argument("--search", type=str, help="Search summaries")
    parser.add_argument("--list", action="store_true", help="List all summaries")
    
    args = parser.parse_args()
    
    importer = SessionImporter()
    
    if args.import_cline:
        sessions = importer.import_cline_history()
        print(f"Imported {len(sessions)} Cline sessions")
    
    if args.import_con:
        sessions = importer.import_con_vessel_history()
        print(f"Imported {len(sessions)} CON Vessel sessions")
    
    if args.summarize:
        # Summarize all un-summarized sessions
        print("Summarization requires running FoveAI services")
    
    if args.search:
        results = importer.search_summaries(args.search)
        for r in results:
            print(f"\n{r.get('session_id')}: {r.get('title')}")
            print(f"  Topics: {', '.join(r.get('topics', [])[:5])}")
    
    if args.list:
        for s in importer.summaries:
            print(f"{s.get('session_id')}: {s.get('title')} [{s.get('category')}]")
    
    if args.export_cognee:
        for summary in importer.summaries:
            importer.export_to_cognee(summary)


if __name__ == "__main__":
    main()