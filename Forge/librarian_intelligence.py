"""Librarian Intelligence Extraction Module"""
import asyncio, json, logging, re, time, hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class IntelligenceExtract:
    session_id: str
    timestamp: float = field(default_factory=time.time)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    files_touched: List[Dict[str, Any]] = field(default_factory=list)
    insights: List[Dict[str, Any]] = field(default_factory=list)
    errors_encountered: List[Dict[str, Any]] = field(default_factory=list)
    user_preferences: List[Dict[str, Any]] = field(default_factory=list)
    project_state: Dict[str, Any] = field(default_factory=dict)
    tokens_at_extraction: int = 0
    compression_ratio: float = 0.0
    
    def to_dict(self): return asdict(self)
@dataclass
class ContextFingerprint:
    session_id: str
    timestamp: float = field(default_factory=time.time)
    decision_count: int = 0
    file_count: int = 0
    insight_count: int = 0
    error_count: int = 0
    preference_count: int = 0
    topics: List[str] = field(default_factory=list)
    state_hash: str = ""
    key_files: List[str] = field(default_factory=list)
    key_decisions: List[str] = field(default_factory=list)
    
    def to_dict(self): return asdict(self)
    def to_json(self): return json.dumps(self.to_dict(), indent=2)
    def compact_string(self):
        return f"FP[{self.session_id[:8]}] D:{self.decision_count} F:{self.file_count} I:{self.insight_count} E:{self.error_count} T:[{','.join(self.topics[:3])}]"
class PatternMatchers:
    DECISION_PATTERNS = [
        r"(?:decided|decision|chose|chosen|opted|will|shall|plan to)\s+(?:to\s+)?([^.]+)",
        r"(?:implementing|implement|using|going with)\s+([^.]+)",
        r"(?:selected|selecting)\s+([^.]+)",
        r"(?:approach|strategy|solution)\s*:?\s+([^.]+)",
        r"let\s+\'s\s+([^.]+)", r"we\s+(?:should|will|need to)\s+([^.]+)",
        r"agreed\s+(?:to|on)\s+([^.]+)", r"(settle[ds]\s+on\s+[^.]+)",
    ]
    FILE_PATTERNS = [
        r"(?:file|path)\s+[`\']?([^`\'\n]+\.(?:py|js|ts|json|yaml|yml|md|txt))[`\']?",
        r"(?:created|modified|edited|updated|deleted)\s+[`\']?([^`\'\n]+\.(?:py|js|ts|json|yaml|yml|md|txt))[`\']?",
        r"(?:writing|wrote|reading|read)\s+(?:to|from)?\s+[`\']?([^`\'\n]+\.(?:py|js|ts|json|yaml|yml|md|txt))[`\']?",
        r"`([^`]+\.(?:py|js|ts|json|yaml|yml|md|txt))`",
    ]
    INSIGHT_PATTERNS = [
        r"(?:realized|realizing|understood|understanding)\s+(?:that\s+)?([^.]+)",
        r"(?:insight|learning|discovered|found)\s*:?\s+([^.]+)",
        r"(?:notably|importantly|significantly)\s+([^.]+)",
        r"(?:this means|this implies|it follows)\s+(?:that\s+)?([^.]+)",
        r"(?:key takeaway|main point)\s*:?\s+([^.]+)",
    ]
    ERROR_PATTERNS = [
        r"(?:error|exception|failed|failure)\s*:?\s+([^.]+)",
        r"(?:bug|issue|problem)\s*:?\s+([^.]+)",
        r"(?:fix|fixed|solved|resolved|workaround)\s+(?:for|to)?\s*:?\s+([^.]+)",
        r"(?:solution|resolution)\s*:?\s+([^.]+)",
        r"(?:caused by|root cause)\s*:?\s+([^.]+)",
    ]
    PREFERENCE_PATTERNS = [
        r"(?:prefer|preference|liked|like|want|wants)\s+(?:to\s+)?([^.]+)",
        r"(?:would rather|rather than)\s+([^.]+)",
        r"(?:style|format|structure)\s*:?\s+([^.]+)",
        r"(?:typically|usually|generally)\s+(?:use|do|prefer)\s+([^.]+)",
        r"(?:don\'t|do not|never)\s+(?:want|like)\s+([^.]+)",
    ]
    PROJECT_STATE_PATTERNS = [
        r"(?:current|current status|state)\s*:?\s+([^.]+)",
        r"(?:progress|milestone|checkpoint)\s*:?\s+([^.]+)",
        r"(?:completed|done|finished)\s*:?\s+([^.]+)",
        r"(?:pending|todo|next|upcoming)\s*:?\s+([^.]+)",
    ]
    
    @classmethod
    def compile_patterns(cls):
        return {
            "decisions": [re.compile(p, re.IGNORECASE) for p in cls.DECISION_PATTERNS],
            "files": [re.compile(p, re.IGNORECASE) for p in cls.FILE_PATTERNS],
            "insights": [re.compile(p, re.IGNORECASE) for p in cls.INSIGHT_PATTERNS],
            "errors": [re.compile(p, re.IGNORECASE) for p in cls.ERROR_PATTERNS],
            "preferences": [re.compile(p, re.IGNORECASE) for p in cls.PREFERENCE_PATTERNS],
            "project_state": [re.compile(p, re.IGNORECASE) for p in cls.PROJECT_STATE_PATTERNS],
        }

class LibrarianIntelligence:
    def __init__(self, data_dir=None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path.home() / ".foveai" / "librarian"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.extracts_dir = self.data_dir / "extracts"
        self.fingerprints_dir = self.data_dir / "fingerprints"
        self.sessions_dir = self.data_dir / "sessions"
        for d in [self.extracts_dir, self.fingerprints_dir, self.sessions_dir]:
            d.mkdir(exist_ok=True)
        self.patterns = PatternMatchers.compile_patterns()
        self._recent_extracts = {}
        self._fingerprints = {}
        self._event_handlers = {}
        self._stats = {
            "extractions_count": 0, "total_decisions_extracted": 0,
            "total_files_tracked": 0, "total_errors_captured": 0,
            "total_insights_found": 0,
        }
        self.mesh_bus = None
        logger.info(f"LibrarianIntelligence initialized at {self.data_dir}")

    def connect_mesh_bus(self, mesh_bus_instance):
        self.mesh_bus = mesh_bus_instance
        self._register_event_handlers()
        logger.info("Connected to mesh bus")

    def _register_event_handlers(self):
        if not self.mesh_bus:
            return
        event_types = [
            "context.trim_start", "context.trim_complete",
            "session.start", "session.end",
            "file.operation", "error.occurred", "decision.made",
        ]
        for event_type in event_types:
            self.mesh_bus.subscribe(event_type, self._handle_mesh_event)

    def _handle_mesh_event(self, event_type, data):
        handlers = {
            "context.trim_start": self._on_trim_start,
            "context.trim_complete": self._on_trim_complete,
            "session.start": self._on_session_start,
            "session.end": self._on_session_end,
            "file.operation": self._on_file_operation,
            "error.occurred": self._on_error_occurred,
            "decision.made": self._on_decision_made,
        }
        handler = handlers.get(event_type)
        if handler:
            handler(data)

    def _on_trim_start(self, data):
        session_id = data.get("session_id", "unknown")
        self.extract_intelligence(session_id, data.get("context", ""), data.get("current_tokens", 0))

    def _on_trim_complete(self, data):
        session_id = data.get("session_id", "unknown")
        if session_id in self._fingerprints:
            logger.info(f"Context trim complete for {session_id}: {data.get('tokens_after', 0)} tokens")

    def _on_session_start(self, data):
        logger.info(f"Session started: {data.get('session_id', 'unknown')}")

    def _on_session_end(self, data):
        session_id = data.get("session_id", "unknown")
        if session_id in self._recent_extracts:
            self._persist_extract(self._recent_extracts[session_id])
            logger.info(f"Session ended, intelligence persisted: {session_id}")

    def _on_file_operation(self, data):
        session_id = data.get("session_id", "unknown")
        if session_id in self._recent_extracts:
            self._recent_extracts[session_id].files_touched.append({
                "path": data.get("file_path", ""),
                "operation": data.get("operation", "unknown"),
                "timestamp": time.time(),
            })

    def _on_error_occurred(self, data):
        session_id = data.get("session_id", "unknown")
        if session_id in self._recent_extracts:
            self._recent_extracts[session_id].errors_encountered.append({
                "error": data.get("error", ""),
                "solution": data.get("solution", ""),
                "timestamp": time.time(),
            })

    def _on_decision_made(self, data):
        session_id = data.get("session_id", "unknown")
        if session_id in self._recent_extracts:
            self._recent_extracts[session_id].decisions.append({
                "decision": data.get("decision", ""),
                "rationale": data.get("rationale", ""),
                "timestamp": time.time(),
            })

    def extract_intelligence(self, session_id, context, current_tokens=0):
        extract = IntelligenceExtract(
            session_id=session_id, timestamp=time.time(),
            tokens_at_extraction=current_tokens
        )
        extract.decisions = self._detect_decisions(context)
        extract.files_touched = self._detect_files(context)
        extract.insights = self._detect_insights(context)
        extract.errors_encountered = self._detect_errors(context)
        extract.user_preferences = self._detect_preferences(context)
        extract.project_state = self._detect_project_state(context)
        self._recent_extracts[session_id] = extract
        fingerprint = self._create_fingerprint(extract, context)
        self._fingerprints[session_id] = fingerprint
        self._stats["extractions_count"] += 1
        self._stats["total_decisions_extracted"] += len(extract.decisions)
        self._stats["total_files_tracked"] += len(extract.files_touched)
        self._stats["total_errors_captured"] += len(extract.errors_encountered)
        self._stats["total_insights_found"] += len(extract.insights)
        self._persist_extract(extract)
        self._persist_fingerprint(fingerprint)
        if self.mesh_bus:
            self.mesh_bus.publish("intelligence.extracted", {
                "session_id": session_id, "decision_count": len(extract.decisions),
                "file_count": len(extract.files_touched), "insight_count": len(extract.insights),
                "error_count": len(extract.errors_encountered),
            })
        logger.info(f"Extracted intelligence for {session_id}: {len(extract.decisions)} decisions, "
                    f"{len(extract.files_touched)} files, {len(extract.insights)} insights")
        return extract

    def _detect_decisions(self, context):
        decisions, seen = [], set()
        for pattern in self.patterns["decisions"]:
            for match in pattern.finditer(context):
                text = match.group(1).strip() if match.lastindex else match.group(0)
                if text.lower() not in seen:
                    seen.add(text.lower())
                    decisions.append({"text": text, "confidence": "high" if "decided" in match.group(0).lower() else "medium", "source": "pattern_match", "position": match.start()})
        return decisions

    def _detect_files(self, context):
        files, seen = [], set()
        for pattern in self.patterns["files"]:
            for match in pattern.finditer(context):
                file_path = match.group(1).strip() if match.lastindex else match.group(0)
                file_path = file_path.strip("`\'\"")
                if file_path.lower() not in seen:
                    seen.add(file_path.lower())
                    match_text = match.group(0).lower()
                    operation = "referenced"
                    if any(w in match_text for w in ["created", "create", "wrote", "write"]): operation = "created"
                    elif any(w in match_text for w in ["modified", "edited", "updated"]): operation = "modified"
                    elif any(w in match_text for w in ["deleted", "removed"]): operation = "deleted"
                    elif any(w in match_text for w in ["read", "reading"]): operation = "read"
                    files.append({"path": file_path, "operation": operation, "confidence": "high", "source": "pattern_match", "position": match.start()})
        return files

    def _detect_insights(self, context):
        insights, seen = [], set()
        for pattern in self.patterns["insights"]:
            for match in pattern.finditer(context):
                text = match.group(1).strip() if match.lastindex else match.group(0)
                if text.lower() not in seen and len(text) > 10:
                    seen.add(text.lower())
                    insights.append({"text": text, "type": "insight", "confidence": "high" if "realized" in match.group(0).lower() else "medium", "source": "pattern_match", "position": match.start()})
        return insights

    def _detect_errors(self, context):
        errors, seen = [], set()
        for pattern in self.patterns["errors"]:
            for match in pattern.finditer(context):
                text = match.group(1).strip() if match.lastindex else match.group(0)
                if text.lower() not in seen:
                    seen.add(text.lower())
                    match_text = match.group(0).lower()
                    error_type = "error"
                    if any(w in match_text for w in ["fix", "fixed", "solved", "solution"]): error_type = "solution"
                    elif any(w in match_text for w in ["caused by", "root cause"]): error_type = "root_cause"
                    errors.append({"text": text, "type": error_type, "confidence": "high", "source": "pattern_match", "position": match.start()})
        return errors

    def _detect_preferences(self, context):
        preferences, seen = [], set()
        for pattern in self.patterns["preferences"]:
            for match in pattern.finditer(context):
                text = match.group(1).strip() if match.lastindex else match.group(0)
                if text.lower() not in seen and len(text) > 5:
                    seen.add(text.lower())
                    preferences.append({"text": text, "confidence": "medium", "source": "pattern_match", "position": match.start()})
        return preferences

    def _detect_project_state(self, context):
        state = {"completed_items": [], "pending_items": [], "current_focus": None}
        for pattern in self.patterns["project_state"]:
            for match in pattern.finditer(context):
                text = match.group(1).strip() if match.lastindex else match.group(0)
                match_text = match.group(0).lower()
                if any(w in match_text for w in ["completed", "done", "finished"]): state["completed_items"].append(text)
                elif any(w in match_text for w in ["pending", "todo", "next", "upcoming"]): state["pending_items"].append(text)
                elif "current" in match_text: state["current_focus"] = text
        return state

    def _create_fingerprint(self, extract, context):
        words = re.findall(r"\b[a-zA-Z]{4,}\b", context.lower())
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
        common_words = {"this", "that", "with", "from", "they", "have", "were", "been", "their", "would"}
        topics = [w for w, c in sorted(word_freq.items(), key=lambda x: -x[1]) if w not in common_words][:10]
        key_files = [f["path"] for f in extract.files_touched[:5]]
        key_decisions = [d["text"][:50] + "..." if len(d["text"]) > 50 else d["text"] for d in extract.decisions[:3]]
        state_hash = hashlib.md5(context.encode()).hexdigest()[:16]
        return ContextFingerprint(
            session_id=extract.session_id, timestamp=extract.timestamp,
            decision_count=len(extract.decisions), file_count=len(extract.files_touched),
            insight_count=len(extract.insights), error_count=len(extract.errors_encountered),
            preference_count=len(extract.user_preferences), topics=topics,
            state_hash=state_hash, key_files=key_files, key_decisions=key_decisions,
        )

    def _persist_extract(self, extract):
        filepath = self.extracts_dir / f"{extract.session_id}_{int(extract.timestamp)}.json"
        try:
            with open(filepath, "w") as f:
                f.write(extract.to_json())
        except Exception as e:
            logger.error(f"Failed to persist extract: {e}")

    def _persist_fingerprint(self, fingerprint):
        filepath = self.fingerprints_dir / f"{fingerprint.session_id}_{int(fingerprint.timestamp)}.json"
        try:
            with open(filepath, "w") as f:
                f.write(fingerprint.to_json())
        except Exception as e:
            logger.error(f"Failed to persist fingerprint: {e}")

    # Query Methods for Librarian Window
    def get_session_intelligence(self, session_id):
        if session_id in self._recent_extracts:
            return self._recent_extracts[session_id]
        try:
            files = list(self.extracts_dir.glob(f"{session_id}_*.json"))
            if files:
                latest = max(files, key=lambda p: p.stat().st_mtime)
                with open(latest, "r") as f:
                    return IntelligenceExtract(**json.load(f))
        except Exception as e:
            logger.error(f"Failed to load session intelligence: {e}")
        return None

    def get_compression_stats(self):
        return {
            **self._stats,
            "fingerprints_in_memory": len(self._fingerprints),
            "extracts_in_memory": len(self._recent_extracts),
            "data_directory": str(self.data_dir),
            "estimated_compression_ratio": 0.01 if self._fingerprints else 0.0,
            "patterns_loaded": {k: len(v) for k, v in self.patterns.items()}
        }

    def search_intelligence(self, query, session_id=None):
        results = []
        extracts = [self._recent_extracts[session_id]] if session_id and session_id in self._recent_extracts else list(self._recent_extracts.values())
        query_lower = query.lower()
        for extract in extracts:
            for decision in extract.decisions:
                if query_lower in decision.get("text", "").lower():
                    results.append({"type": "decision", "session_id": extract.session_id, "data": decision})
            for file in extract.files_touched:
                if query_lower in file.get("path", "").lower():
                    results.append({"type": "file", "session_id": extract.session_id, "data": file})
            for insight in extract.insights:
                if query_lower in insight.get("text", "").lower():
                    results.append({"type": "insight", "session_id": extract.session_id, "data": insight})
            for error in extract.errors_encountered:
                if query_lower in error.get("text", "").lower():
                    results.append({"type": "error", "session_id": extract.session_id, "data": error})
        return results

    def get_recent_fingerprints(self, count=10):
        return sorted(self._fingerprints.values(), key=lambda fp: fp.timestamp, reverse=True)[:count]

    def get_all_session_ids(self):
        return list(self._recent_extracts.keys())

    def clear_session(self, session_id):
        if session_id in self._recent_extracts:
            del self._recent_extracts[session_id]
        if session_id in self._fingerprints:
            del self._fingerprints[session_id]
        logger.info(f"Cleared intelligence for session: {session_id}")

# Global Singleton
librarian = LibrarianIntelligence()

# Convenience Functions
def extract_intelligence(session_id, context, current_tokens=0):
    return librarian.extract_intelligence(session_id, context, current_tokens)

def get_session_intelligence(session_id):
    return librarian.get_session_intelligence(session_id)

def get_compression_stats():
    return librarian.get_compression_stats()

def search_intelligence(query, session_id=None):
    return librarian.search_intelligence(query, session_id)

# Async Support
async def extract_intelligence_async(session_id, context, current_tokens=0):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, librarian.extract_intelligence, session_id, context, current_tokens)

# Main (for testing)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_context = """
    We decided to use JSON format for configuration files.
    I've modified the config.yaml file to include new settings.
    The user prefers dark mode for the interface.
    I realized that the current approach won't scale well.
    We encountered an error in the database connection.
    The fix was to increase the connection timeout.
    Current status: Authentication module is completed.
    Next: Work on the user dashboard.
    """
    
    extract = librarian.extract_intelligence("test_session_001", test_context, 500)
    
    print("\n" + "="*60)
    print("INTELLIGENCE EXTRACTION RESULTS")
    print("="*60)
    print(f"\nSession ID: {extract.session_id}")
    print(f"Timestamp: {datetime.fromtimestamp(extract.timestamp)}")
    print(f"Tokens at extraction: {extract.tokens_at_extraction}")
    
    print(f"\n--- Decisions ({len(extract.decisions)}) ---")
    for i, d in enumerate(extract.decisions, 1):
        print(f"{i}. {d['text']} (confidence: {d['confidence']})")
    
    print(f"\n--- Files Touched ({len(extract.files_touched)}) ---")
    for i, f in enumerate(extract.files_touched, 1):
        print(f"{i}. {f['path']} ({f['operation']})")
    
    print(f"\n--- Insights ({len(extract.insights)}) ---")
    for i, ins in enumerate(extract.insights, 1):
        print(f"{i}. {ins['text']}")
    
    print(f"\n--- Errors/Solutions ({len(extract.errors_encountered)}) ---")
    for i, e in enumerate(extract.errors_encountered, 1):
        print(f"{i}. [{e['type']}] {e['text']}")
    
    print(f"\n--- User Preferences ({len(extract.user_preferences)}) ---")
    for i, p in enumerate(extract.user_preferences, 1):
        print(f"{i}. {p['text']}")
    
    print(f"\n--- Project State ---")
    print(f"Completed: {extract.project_state.get('completed_items', [])}")
    print(f"Pending: {extract.project_state.get('pending_items', [])}")
    print(f"Current Focus: {extract.project_state.get('current_focus')}")
    
    fp = librarian.get_recent_fingerprints(1)[0]
    print(f"\n--- Context Fingerprint ---")
    print(fp.compact_string())
    print(f"Topics: {fp.topics[:5]}")
    
    stats = librarian.get_compression_stats()
    print(f"\n--- Compression Stats ---")
    print(json.dumps(stats, indent=2, default=str))
    
    print("\n" + "="*60)
    print("Librarian Intelligence Test Complete")
    print("="*60)
