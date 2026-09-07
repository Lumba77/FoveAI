"""The Librarian's Voice - A vocal, personality-driven intelligence service.

This module gives the Librarian a DISTINCT VOICE - like a wise but gossipy
archivist who knows secrets about the codebase and warns developers.
"""

import json
import logging
import random
import time
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set
from enum import Enum, auto

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMERATIONS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

class VoiceTone(Enum):
    GOSSIP = auto()
    WARNING = auto()
    WISDOM = auto()
    MYSTERY = auto()
    CELEBRATION = auto()
    MELANCHOLY = auto()


class RumorType(Enum):
    FILE_HISTORY = auto()
    PATTERN_DETECTED = auto()
    WARNING_SIGN = auto()
    PAST_FAILURE = auto()
    HIDDEN_CONNECTION = auto()
    SESSION_GHOST = auto()


# The Librarian's vocabulary
LIBRARIAN_PHRASES = {
    "openers": ["*adjusts spectacles*", "*shuffles papers*", "*looks up from ancient tome*",
                "*whispers from the shadows*", "*clears throat dramatically*",
                "*dusts off a well-worn ledger*", "*peers over reading glasses*",
                "*rustles through yellowed scrolls*"],
    "rumor_starters": ["Rumors say...", "Whispers from the archive suggest...",
                       "I've heard tell that...", "The old records indicate...",
                       "Word among the scrolls is...", "Between you and me...",
                       "The archives murmur that...", "A hushed voice mentioned..."],
    "warning_starters": ["Beware...", "A word of caution...", "Take heed...",
                         "Mind the shadows...", "Watch your step...", "Danger lurks...",
                         "Heed this warning...", "Tread carefully..."],
    "wisdom_starters": ["A wise developer once noted...", "The archives suggest...",
                        "Ancient wisdom teaches us...", "From the annals of experience...",
                        "The seasoned scribes recommend...", "Time-tested knowledge reveals...",
                        "The elders of code have spoken..."],
    "mystery_starters": ["Curious... very curious...", "Something stirs in the depths...",
                         "The patterns align in strange ways...", "There's more here than meets the eye...",
                         "The threads connect in unexpected fashion...", "Shadows lengthen where they shouldn't..."],
    "celebration_phrases": ["Splendid!", "Marvelous achievement!", "The archives shall remember this!",
                            "A triumph worthy of record!", "Bravo! The ledger grows brighter!",
                            "Victory is etched in the eternal logs!"],
    "file_references": ["This file bears the scars of many edits...", "I've seen this one before...",
                        "The history of this file is... complicated.", "This one's been touched by many hands...",
                        "Ah yes, a frequent visitor to the archives...", "This file has stories to tell..."],
    "pattern_phrases": ["I've seen this pattern before...", "History repeats itself, doesn't it?",
                        "This reminds me of a session long past...", "The echoes are unmistakable...",
                        "Deja vu whispers through the codebase...", "A familiar rhythm plays out..."],
    "closing_remarks": ["Shall I keep watching?", "I'll be here, cataloging...", "The archives never sleep.",
                        "I'll update the ledgers.", "Consider it noted.", "Another entry for the books."],
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Achievement:
    id: str
    session_id: str
    timestamp: float
    title: str
    description: str
    category: str
    files_involved: List[str] = field(default_factory=list)
    significance: int = 1
    def to_dict(self): return asdict(self)
    def formatted_time(self): return datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")


@dataclass
class SessionSnapshot:
    turn_number: int
    timestamp: float
    files_active: List[str]
    decisions_made: List[str]
    warnings_issued: List[str]
    context_size: int
    def to_dict(self): return asdict(self)


@dataclass
class VoiceMessage:
    id: str
    timestamp: float
    tone: VoiceTone
    category: str
    content: str
    context: Dict[str, Any] = field(default_factory=dict)
    displayed: bool = False
    def to_dict(self): return asdict(self)
    
    def to_ui_format(self):
        icons = {VoiceTone.GOSSIP: "💬", VoiceTone.WARNING: "⚠️", VoiceTone.WISDOM: "📜",
                 VoiceTone.MYSTERY: "🔮", VoiceTone.CELEBRATION: "🎉", VoiceTone.MELANCHOLY: "🥀"}
        colors = {VoiceTone.GOSSIP: "#8B7355", VoiceTone.WARNING: "#FF6B35", VoiceTone.WISDOM: "#4A90D9",
                  VoiceTone.MYSTERY: "#9B59B6", VoiceTone.CELEBRATION: "#27AE60", VoiceTone.MELANCHOLY: "#7F8C8D"}
        return {"id": self.id, "timestamp": self.timestamp,
                "formatted_time": datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S"),
                "tone": self.tone.name, "category": self.category, "content": self.content,
                "icon": icons.get(self.tone, "📚"), "color": colors.get(self.tone, "#5D4E37"),
                "displayed": self.displayed}


@dataclass
class PatternWarning:
    pattern_name: str
    description: str
    files_involved: List[str]
    historical_occurrences: int
    last_seen: float
    severity: str
    def to_dict(self): return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# RUMORS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class RumorsEngine:
    """Generates gossip, warnings, and wisdom based on session data."""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path.home() / ".foveai" / "librarian" / "voice"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.rumors_history: List[Dict[str, Any]] = []
        self.pattern_memory: Dict[str, int] = {}
    
    def generate_file_rumor(self, file_path: str, operation: str = "modified") -> VoiceMessage:
        opener = random.choice(LIBRARIAN_PHRASES["openers"])
        starter = random.choice(LIBRARIAN_PHRASES["rumor_starters"])
        file_ref = random.choice(LIBRARIAN_PHRASES["file_references"])
        trouble_indicators = ["config", "main", "index", "app", "core", "base"]
        is_troublesome = any(ind in file_path.lower() for ind in trouble_indicators)
        if is_troublesome:
            content = f"{opener} {starter} *{file_path}* is being {operation}. {file_ref} This one has seen many battles."
        else:
            content = f"{opener} {starter} someone is {operation} *{file_path}*. {file_ref}"
        return VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.GOSSIP,
            category="file_activity", content=content, context={"file_path": file_path, "operation": operation})
    
    def generate_pattern_rumor(self, pattern_name: str, context: Dict[str, Any]) -> VoiceMessage:
        opener, starter = random.choice(LIBRARIAN_PHRASES["openers"]), random.choice(LIBRARIAN_PHRASES["pattern_phrases"])
        count = self.pattern_memory.get(pattern_name, 0) + 1
        self.pattern_memory[pattern_name] = count
        if count > 3:
            content = f"{opener} {starter} This '{pattern_name}' pattern has appeared {count} times. The archives grow heavy..."
        else:
            content = f"{opener} {starter} I detect a '{pattern_name}' pattern forming. Curious..."
        return VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.MYSTERY,
            category="pattern_detected", content=content, context={"pattern": pattern_name, "occurrences": count, **context})
    
    def generate_warning_rumor(self, issue_type: str, details: Dict[str, Any]) -> VoiceMessage:
        opener, starter = random.choice(LIBRARIAN_PHRASES["openers"]), random.choice(LIBRARIAN_PHRASES["warning_starters"])
        warnings = {"large_refactor": "Many files tremble at such sweeping changes...",
            "multiple_configs": "Configuration files modified in clusters. It ended in tears last time...",
            "circular_imports": "The import web grows tangled. Beware circular dependencies...",
            "untested_changes": "Files change but tests remain silent. Tragedies born of such haste...",
            "concurrent_edits": "Multiple core files stir at once. Like rebuilding a ship in stormy seas...",
            "context_bloat": "The session grows long. Soon context must be trimmed and wisdom lost..."}
        warning_text = warnings.get(issue_type, f"Something feels amiss with {issue_type}...")
        return VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.WARNING,
            category="warning", content=f"{opener} {starter} {warning_text}", context={"issue_type": issue_type, **details})
    
    def generate_wisdom_rumor(self, topic: str, past_sessions: List[str]) -> VoiceMessage:
        opener, starter = random.choice(LIBRARIAN_PHRASES["openers"]), random.choice(LIBRARIAN_PHRASES["wisdom_starters"])
        wisdom = {"testing": "Testing before code grows proud. Pride before segmentation fault.",
            "refactoring": "Small steps preserve the path. Grand refactorings bring grand confusions.",
            "documentation": "Code tells how, comments tell why. Both needed for the journey.",
            "dependencies": "Beware silently updating dependencies. Today's convenience, tomorrow's pain.",
            "async": "Async code is a spider's web - beautiful whole, but one wrong thread brings collapse.",
            "api_design": "An API is a promise. Breaking changes break trust. Version wisely."}
        wisdom_text = wisdom.get(topic, f"Experience with '{topic}' teaches patience.")
        session_refs = f" (I recall {', '.join(past_sessions[:2])}... hard lessons)" if past_sessions else ""
        return VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.WISDOM,
            category="wisdom", content=f"{opener} {starter} {wisdom_text}{session_refs}",
            context={"topic": topic, "past_sessions": past_sessions})
    
    def generate_historical_rumor(self, session_id: str, related_work: List[Dict[str, Any]]) -> VoiceMessage:
        opener = random.choice(LIBRARIAN_PHRASES["openers"])
        if related_work:
            desc = related_work[0].get('description', 'related work was done')
            content = f"{opener} Whispers from session *{session_id[:8]}*... {desc}. The echoes may guide you."
        else:
            content = f"{opener} I searched for session *{session_id[:8]}*... but time obscured those records."
        return VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.MYSTERY,
            category="historical_lookup", content=content, context={"session_id": session_id, "related_work": related_work})
    
    def _generate_id(self) -> str:
        return hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════════════════
# ACHIEVEMENT LOGGER
# ═══════════════════════════════════════════════════════════════════════════════

class AchievementLogger:
    """Tracks accomplishments per session with timestamps."""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path.home() / ".foveai" / "librarian" / "achievements"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session_achievements: Dict[str, List[Achievement]] = {}
        self._load_achievements()
    
    def _load_achievements(self):
        for file in self.data_dir.glob("*.json"):
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    sid = data.get("session_id")
                    if sid:
                        self.session_achievements[sid] = [Achievement(**a) for a in data.get("achievements", [])]
            except Exception as e:
                logger.warning(f"Could not load {file}: {e}")
    
    def log_achievement(self, session_id: str, title: str, description: str,
                        category: str = "general", files_involved: Optional[List[str]] = None,
                        significance: int = 1) -> Achievement:
        achievement = Achievement(
            id=hashlib.md5(f"{session_id}{time.time()}".encode()).hexdigest()[:12],
            session_id=session_id, timestamp=time.time(), title=title,
            description=description, category=category,
            files_involved=files_involved or [], significance=significance
        )
        if session_id not in self.session_achievements:
            self.session_achievements[session_id] = []
        self.session_achievements[session_id].append(achievement)
        self._persist_session(session_id)
        logger.info(f"Achievement logged: {title}")
        return achievement
    
    def _persist_session(self, session_id: str):
        filepath = self.data_dir / f"{session_id}.json"
        try:
            with open(filepath, "w") as f:
                json.dump({"session_id": session_id,
                    "achievements": [a.to_dict() for a in self.session_achievements[session_id]]}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist: {e}")
    
    def get_session_achievements(self, session_id: str) -> List[Achievement]:
        return self.session_achievements.get(session_id, [])
    
    def get_recent_achievements(self, count: int = 10) -> List[Achievement]:
        all_achievements = []
        for achievements in self.session_achievements.values():
            all_achievements.extend(achievements)
        return sorted(all_achievements, key=lambda a: a.timestamp, reverse=True)[:count]


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORICAL LOOKUP
# ═══════════════════════════════════════════════════════════════════════════════

class HistoricalLookup:
    """Searches past sessions for related work."""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path.home() / ".foveai" / "librarian"
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def find_related_sessions(self, file_path: str, timeframe_days: int = 30) -> List[Dict[str, Any]]:
        related = []
        cutoff = time.time() - (timeframe_days * 24 * 60 * 60)
        extracts_dir = self.data_dir / "extracts"
        if not extracts_dir.exists():
            return related
        for file in extracts_dir.glob("*.json"):
            try:
                stat = file.stat()
                if stat.st_mtime < cutoff:
                    continue
                with open(file, "r") as f:
                    data = json.load(f)
                    files_touched = data.get("files_touched", [])
                    for ft in files_touched:
                        if file_path in ft.get("path", ""):
                            related.append({"session_id": data.get("session_id"),
                                "timestamp": data.get("timestamp"),
                                "operation": ft.get("operation"),
                                "description": f"File was {ft.get('operation')}"})
                            break
            except Exception:
                continue
        return sorted(related, key=lambda x: x.get("timestamp", 0), reverse=True)
    
    def find_similar_patterns(self, current_files: List[str]) -> List[Dict[str, Any]]:
        similar = []
        extracts_dir = self.data_dir / "extracts"
        if not extracts_dir.exists() or not current_files:
            return similar
        for file in extracts_dir.glob("*.json"):
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    session_files = [ft.get("path", "") for ft in data.get("files_touched", [])]
                    overlap = set(current_files) & set(session_files)
                    if len(overlap) >= 2:
                        similar.append({"session_id": data.get("session_id"),
                            "timestamp": data.get("timestamp"),
                            "common_files": list(overlap), "match_strength": len(overlap)})
            except Exception:
                continue
        return sorted(similar, key=lambda x: x["match_strength"], reverse=True)[:5]
    
    def get_session_legacy(self, session_id: str) -> Optional[Dict[str, Any]]:
        extracts_dir = self.data_dir / "extracts"
        if not extracts_dir.exists():
            return None
        for file in extracts_dir.glob(f"{session_id}_*.json"):
            try:
                with open(file, "r") as f:
                    return json.load(f)
            except Exception:
                continue
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# TURN COMMENTARY
# ═══════════════════════════════════════════════════════════════════════════════

class TurnCommentary:
    """Every N turns, outputs 'rumors' about current session state."""
    
    def __init__(self, turn_interval: int = 5):
        self.turn_interval = turn_interval
        self.current_turn = 0
        self.session_snapshots: List[SessionSnapshot] = []
        self.last_commentary_turn = 0
        self.detected_patterns: Set[str] = set()
    
    def record_turn(self, files_active: List[str], decisions_made: List[str], context_size: int) -> Optional[SessionSnapshot]:
        self.current_turn += 1
        snapshot = SessionSnapshot(
            turn_number=self.current_turn, timestamp=time.time(),
            files_active=files_active, decisions_made=decisions_made,
            warnings_issued=[], context_size=context_size
        )
        self.session_snapshots.append(snapshot)
        return snapshot
    
    def should_comment(self) -> bool:
        return self.current_turn - self.last_commentary_turn >= self.turn_interval
    
    def generate_commentary(self, session_id: str) -> List[VoiceMessage]:
        self.last_commentary_turn = self.current_turn
        messages = []
        if not self.session_snapshots:
            return messages
        recent = self.session_snapshots[-self.turn_interval:]
        all_files = set()
        all_decisions = []
        for snap in recent:
            all_files.update(snap.files_active)
            all_decisions.extend(snap.decisions_made)
        if len(all_files) > 5:
            messages.append(self._generate_file_chatter(list(all_files)[:5]))
        if len(all_decisions) > 2:
            messages.append(self._generate_decision_pattern(all_decisions))
        if self._detect_concurrent_edits(recent):
            messages.append(self._generate_concurrent_warning())
        if self._detect_context_growth(recent):
            messages.append(self._generate_context_warning())
        return messages
    
    def _generate_file_chatter(self, files: List[str]) -> VoiceMessage:
        opener, starter = random.choice(LIBRARIAN_PHRASES["openers"]), random.choice(LIBRARIAN_PHRASES["rumor_starters"])
        if len(files) == 1:
            content = f"{opener} {starter} *{files[0]}* keeps you company. A loyal companion."
        else:
            file_list = ", ".join([f"*{f}*" for f in files[:3]])
            if len(files) > 3:
                file_list += f" and {len(files) - 3} others"
            content = f"{opener} {starter} you dance with {file_list} this turn. Busy fingers make busy archives..."
        return VoiceMessage(
            id=hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12], timestamp=time.time(),
            tone=VoiceTone.GOSSIP, category="turn_commentary", content=content, context={"files": files})
    
    def _generate_decision_pattern(self, decisions: List[str]) -> VoiceMessage:
        opener = random.choice(LIBRARIAN_PHRASES["openers"])
        content = f"{opener} {len(decisions)} decisions in recent turns. The path becomes clearer... or more complicated."
        return VoiceMessage(
            id=hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12], timestamp=time.time(),
            tone=VoiceTone.MYSTERY, category="turn_commentary", content=content, context={"decisions": decisions})
    
    def _generate_concurrent_warning(self) -> VoiceMessage:
        opener, starter = random.choice(LIBRARIAN_PHRASES["openers"]), random.choice(LIBRARIAN_PHRASES["warning_starters"])
        content = f"{opener} {starter} Many files stir simultaneously. Like conducting an orchestra - one wrong note..."
        return VoiceMessage(
            id=hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12], timestamp=time.time(),
            tone=VoiceTone.WARNING, category="turn_warning", content=content, context={})
    
    def _generate_context_warning(self) -> VoiceMessage:
        opener, starter = random.choice(LIBRARIAN_PHRASES["openers"]), random.choice(LIBRARIAN_PHRASES["warning_starters"])
        content = f"{opener} {starter} The conversation grows long. Soon, the trimmers will come. Preserve what matters..."
        return VoiceMessage(
            id=hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12], timestamp=time.time(),
            tone=VoiceTone.WARNING, category="context_warning", content=content, context={})
    
    def _detect_concurrent_edits(self, snapshots: List[SessionSnapshot]) -> bool:
        all_files = set()
        for snap in snapshots:
            all_files.update(snap.files_active)
        return len(all_files) > 8
    
    def _detect_context_growth(self, snapshots: List[SessionSnapshot]) -> bool:
        if len(snapshots) < 2:
            return False
        sizes = [s.context_size for s in snapshots]
        return sizes[-1] > sizes[0] * 1.5 if sizes[0] > 0 else False


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT PRESERVATION ADVISOR
# ═══════════════════════════════════════════════════════════════════════════════

class ContextPreservationAdvisor:
    """Warns before context trim with specific suggestions."""
    
    def __init__(self):
        self.critical_items: List[Dict[str, Any]] = []
        self.suggestions_cache: Dict[str, List[str]] = {}
    
    def analyze_before_trim(self, session_id: str, context: str, decisions: List[Dict], files: List[Dict]) -> VoiceMessage:
        opener = random.choice(LIBRARIAN_PHRASES["openers"])
        critical_decisions = [d for d in decisions if d.get("confidence") == "high"]
        critical_files = [f for f in files if f.get("operation") in ["created", "modified"]]
        suggestions = []
        if critical_decisions:
            suggestions.append(f"Document {len(critical_decisions)} key decision(s) in session notes")
        if critical_files:
            file_names = [f.get("path", "").split("/")[-1] for f in critical_files[:3]]
            suggestions.append(f"Ensure recent changes to {', '.join(file_names)} are saved")
        suggestions.append("Consider summarizing current progress before trim")
        if len(context) > 50000:
            suggestions.append("Large context detected - consider starting fresh session soon")
        content = f"{opener} The trimmers approach! Before context is trimmed, I suggest:\n"
        for i, sug in enumerate(suggestions, 1):
            content += f"  {i}. {sug}\n"
        content += "\n*The archives remember, but the active memory fades...*"
        return VoiceMessage(
            id=hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12], timestamp=time.time(),
            tone=VoiceTone.WARNING, category="trim_warning", content=content,
            context={"session_id": session_id, "suggestions": suggestions,
                     "critical_decisions": len(critical_decisions), "critical_files": len(critical_files)})
    
    def get_preservation_summary(self, session_id: str) -> Dict[str, Any]:
        return {"session_id": session_id, "timestamp": time.time(),
            "recommendations": ["Export current intelligence before trim",
                "Document key decisions in external notes", "Save file state snapshots", "Consider session checkpoint"],
            "auto_actions": ["Intelligence extract will be saved automatically",
                "Fingerprint will be persisted to disk", "Session achievements logged"]}


# ═══════════════════════════════════════════════════════════════════════════════
# VOICE OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

class VoiceOutput:
    """Structured format for UI display."""
    
    def __init__(self, max_history: int = 100):
        self.messages: List[VoiceMessage] = []
        self.max_history = max_history
        self.display_callbacks: List[Callable] = []
    
    def add_message(self, message: VoiceMessage):
        self.messages.append(message)
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
        for callback in self.display_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Display callback error: {e}")
    
    def register_display_callback(self, callback: Callable):
        self.display_callbacks.append(callback)
    
    def get_recent_messages(self, count: int = 10, tone: Optional[VoiceTone] = None) -> List[Dict[str, Any]]:
        filtered = self.messages
        if tone:
            filtered = [m for m in filtered if m.tone == tone]
        return [m.to_ui_format() for m in filtered[-count:]]
    
    def get_unread_messages(self) -> List[Dict[str, Any]]:
        unread = [m for m in self.messages if not m.displayed]
        for m in unread:
            m.displayed = True
        return [m.to_ui_format() for m in unread]
    
    def format_for_terminal(self, message: VoiceMessage) -> str:
        ui = message.to_ui_format()
        return f"{ui['icon']} [{ui['formatted_time']}] {ui['content']}"
    
    def format_for_web(self, message: VoiceMessage) -> Dict[str, Any]:
        ui = message.to_ui_format()
        return {**ui, "html": f'<div class="librarian-message" style="color: {ui["color"]}">'
                f'<span class="icon">{ui["icon"]}</span> '
                f'<span class="time">{ui["formatted_time"]}</span> '
                f'<span class="content">{ui["content"]}</span></div>'}


# ═══════════════════════════════════════════════════════════════════════════════
# THE LIBRARIAN VOICE - MAIN CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class LibrarianVoice:
    """The complete vocal personality of the Librarian."""
    
    def __init__(self, data_dir: Optional[Path] = None, turn_interval: int = 5):
        self.data_dir = data_dir or Path.home() / ".foveai" / "librarian"
        self.session_id: Optional[str] = None
        self.rumors = RumorsEngine(self.data_dir)
        self.achievements = AchievementLogger(self.data_dir / "achievements")
        self.history = HistoricalLookup(self.data_dir)
        self.commentary = TurnCommentary(turn_interval)
        self.advisor = ContextPreservationAdvisor()
        self.output = VoiceOutput()
        self.current_files: Set[str] = set()
        self.current_decisions: List[str] = []
        self.session_start_time: float = 0
        logger.info("The Librarian's Voice has awakened...")
    
    def begin_session(self, session_id: str):
        self.session_id = session_id
        self.session_start_time = time.time()
        self.current_files.clear()
        self.current_decisions.clear()
        welcome = VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.WISDOM,
            category="session_start",
            content=f"*dusts off ledger* The archives welcome you, session *{session_id[:8]}*. I shall watch...",
            context={"session_id": session_id})
        self.output.add_message(welcome)
    
    def end_session(self, session_id: str):
        duration = time.time() - self.session_start_time if self.session_start_time else 0
        achievements = self.achievements.get_session_achievements(session_id)
        farewell = VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.WISDOM,
            category="session_end",
            content=f"*closes ledger* Session *{session_id[:8]}* complete. {len(achievements)} achievements over {duration/60:.1f}m.",
            context={"session_id": session_id, "duration": duration, "achievements": len(achievements)})
        self.output.add_message(farewell)
        self.session_id = None
    
    def record_file_activity(self, session_id: str, file_path: str, operation: str = "modified"):
        self.current_files.add(file_path)

    def record_file_activity(self, session_id: str, file_path: str, operation: str = "modified"):
        self.current_files.add(file_path)
        rumor = self.rumors.generate_file_rumor(file_path, operation)
        self.output.add_message(rumor)
        self._check_file_patterns(file_path)
    
    def record_decision(self, session_id: str, decision_text: str):
        self.current_decisions.append(decision_text)
        if any(w in decision_text.lower() for w in ["refactor", "architecture", "design", "approach"]):
            msg = VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.WISDOM,
                category="significant_decision",
                content=f"*makes a note* A significant choice: '{decision_text[:50]}...' The codebase will remember.",
                context={"decision": decision_text})
            self.output.add_message(msg)
    
    def record_turn(self, context_size: int = 0):
        self.commentary.record_turn(files_active=list(self.current_files),
            decisions_made=self.current_decisions, context_size=context_size)
        if self.commentary.should_comment():
            messages = self.commentary.generate_commentary(self.session_id or "unknown")
            for msg in messages:
                self.output.add_message(msg)
    
    def warn_of_trim(self, session_id: str, context: str, decisions=None, files=None):
        decisions = decisions or []
        files = files or []
        warning = self.advisor.analyze_before_trim(session_id, context, decisions, files)
        self.output.add_message(warning)
        return warning
    
    def celebrate(self, session_id: str, title: str, description: str, significance: int = 1):
        achievement = self.achievements.log_achievement(session_id, title, description,
            files_involved=list(self.current_files), significance=significance)
        celebration = VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.CELEBRATION,
            category="achievement",
            content=f"{random.choice(LIBRARIAN_PHRASES['celebration_phrases'])} {title}: {description}",
            context={"achievement": achievement.to_dict()})
        self.output.add_message(celebration)
        return achievement
    
    def share_wisdom(self, topic: str):
        related = self.history.find_related_sessions("*")
        session_ids = [r["session_id"][:8] for r in related[:3]]
        wisdom = self.rumors.generate_wisdom_rumor(topic, session_ids)
        self.output.add_message(wisdom)
        return wisdom
    
    def search_history(self, query: str):
        related = self.history.find_related_sessions(query)
        messages = []
        if related:
            for match in related[:3]:
                rumor = self.rumors.generate_historical_rumor(match["session_id"], [match])
                messages.append(rumor)
                self.output.add_message(rumor)
        else:
            msg = VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=VoiceTone.MELANCHOLY,
                category="history_search",
                content=f"*searches dusty tomes* Alas, no records of '{query}' exist. New ground?",
                context={"query": query})
            messages.append(msg)
            self.output.add_message(msg)
        return messages
    
    def get_messages(self, unread_only: bool = False, tone=None):
        return self.output.get_unread_messages() if unread_only else self.output.get_recent_messages(tone=tone)
    
    def speak(self, content: str, tone: VoiceTone = VoiceTone.GOSSIP):
        msg = VoiceMessage(id=self._generate_id(), timestamp=time.time(), tone=tone,
            category="direct", content=content, context={})
        self.output.add_message(msg)
        return msg
    
    def warn(self, content: str):
        return self.speak(f"{random.choice(LIBRARIAN_PHRASES['warning_starters'])} {content}", VoiceTone.WARNING)
    
    def advise(self, content: str):
        return self.speak(f"{random.choice(LIBRARIAN_PHRASES['wisdom_starters'])} {content}", VoiceTone.WISDOM)
    
    def _check_file_patterns(self, file_path: str):
        is_config = "config" in file_path.lower()
        has_core = any(f for f in self.current_files if any(c in f.lower() for c in ["main", "core", "app", "index"]))
        if is_config and has_core:
            warning = self.rumors.generate_warning_rumor("multiple_configs", {"files": list(self.current_files)})
            self.output.add_message(warning)
    
    def get_stats(self):
        return {"total_messages": len(self.output.messages),
            "messages_by_tone": {tone.name: len([m for m in self.output.messages if m.tone == tone]) for tone in VoiceTone},
            "total_achievements": sum(len(a) for a in self.achievements.session_achievements.values()),
            "sessions_tracked": len(self.achievements.session_achievements), "data_directory": str(self.data_dir)}

    def _generate_id(self) -> str:
        return hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:12]

# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS & GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

# Global singleton for easy access
librarian_voice = LibrarianVoice()


def speak(content: str, tone: VoiceTone = VoiceTone.GOSSIP):
    """Make the Librarian speak."""
    return librarian_voice.speak(content, tone)


def warn(content: str):
    """Issue a warning."""
    return librarian_voice.warn(content)


def advise(content: str):
    """Offer advice."""
    return librarian_voice.advise(content)


def celebrate(session_id: str, title: str, description: str, significance: int = 1):
    """Celebrate an achievement."""
    return librarian_voice.celebrate(session_id, title, description, significance)


def begin_session(session_id: str):
    """Begin a new session."""
    return librarian_voice.begin_session(session_id)


def end_session(session_id: str):
    """End the current session."""
    return librarian_voice.end_session(session_id)


def get_messages(unread_only: bool = False):
    """Get recent messages."""
    return librarian_voice.get_messages(unread_only=unread_only)


# ═══════════════════════════════════════════════════════════════════════════════
# EXAMPLE OUTPUT - THE LIBRARIAN IN ACTION
# ═══════════════════════════════════════════════════════════════════════════════

EXAMPLE_OUTPUT = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    📚 THE LIBRARIAN SPEAKS 📚                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣

🎬 SCENE: Starting a new development session...

📜 [09:15:32] *dusts off a fresh ledger* The archives welcome you, session 
             *a7f3e2d9*. I shall watch and remember...

🎬 SCENE: Modifying configuration files...

💬 [09:16:45] *shuffles papers* Rumors say... *config.py* is being modified. 
             This file bears the scars of many edits... This one has seen many 
             battles - tread carefully, friend.

⚠️ [09:16:45] *clears throat dramatically* Beware... Configuration files are 
              being modified in clusters. Last time I saw this dance, it ended 
              in tears...

🎬 SCENE: Working on multiple files...

💬 [09:18:12] *looks up from ancient tome* Whispers from the archive suggest... 
             you dance with *config.py*, *main.py*, *utils.py* and 2 others this 
             turn. Busy fingers make busy archives...

🎬 SCENE: Making a key architectural decision...

📜 [09:20:33] *makes a note in the margin* A significant choice: 'We shall adopt 
              the microservices architecture...' The codebase will remember this.

🎬 SCENE: Every 5th turn commentary...

🔮 [09:25:01] *peers over reading glasses* I've seen this pattern before... This 
             'file_cluster_modification' pattern has appeared 5 times now. The 
             archives grow heavy with such repetition...

⚠️ [09:25:01] *rustles through yellowed scrolls* Watch your step... Many files 
              stir simultaneously. Like conducting an orchestra - one wrong note...

⚠️ [09:25:01] *whispers from the shadows* Take heed... The conversation grows 
              long. Soon, the trimmers will come. Preserve what matters...

🎬 SCENE: Warning before context trim...

⚠️ [09:30:15] *dusts off a well-worn ledger* The trimmers approach! Before context 
              is trimmed, I suggest:
                1. Document 3 key decision(s) in session notes
                2. Ensure recent changes to config.py, main.py, utils.py are saved
                3. Consider summarizing current progress before trim
                4. Large context detected - consider starting fresh session soon
              
              *The archives remember, but the active memory fades...*

🎬 SCENE: Searching for historical context...

🔮 [09:35:22] *adjusts spectacles* Whispers from session *b9c2a1f4*... related 
              work on config refactoring was done here. The echoes may guide you.

🎬 SCENE: Celebrating a major achievement...

🎉 [09:45:18] Splendid! Fixed critical database bug: "Race condition in async 
              connection pool resolved with proper locking mechanism"

🎬 SCENE: The Librarian offers wisdom...

📜 [09:50:42] *searches through ancient tomes* Ancient wisdom teaches us... 
              Async code is like a spider's web - beautiful when viewed whole, 
              but one wrong thread brings collapse. (I recall sessions d4e7f2a1, 
              a9b3c5d8... lessons learned the hard way)

🎬 SCENE: Session ending...
📜 [10:15:00] *closes the ledger with a satisfied sigh* Session *a7f3e2d9* 
              complete. 7 achievement(s) recorded over 59.5 minutes. Until we 
              meet again...

╠══════════════════════════════════════════════════════════════════════════════╣
║                         UI DISPLAY FORMAT                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣

{
  "id": "a1b2c3d4e5f6",
  "timestamp": 1704067200.0,
  "formatted_time": "09:15:32",
  "tone": "WISDOM",
  "category": "session_start",
  "content": "*dusts off a fresh ledger* The archives welcome you...",
  "icon": "📜",
  "color": "#4A90D9",
  "displayed": false
}

╚══════════════════════════════════════════════════════════════════════════════╝
"""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN - DEMONSTRATION
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print(EXAMPLE_OUTPUT)
    
    print("\n" + "="*80)
    print("LIVE DEMONSTRATION")
    print("="*80 + "\n")
    
    # Create a fresh instance for demo
    demo_librarian = LibrarianVoice(turn_interval=3)
    
    # Simulate a session
    session_id = f"demo_{int(time.time())}"
    demo_librarian.begin_session(session_id)
    
    # Simulate file activity
    print("\n--- Recording File Activity ---")
    demo_librarian.record_file_activity(session_id, "config.py", "modified")
    time.sleep(0.1)
    demo_librarian.record_file_activity(session_id, "main.py", "modified")
    time.sleep(0.1)
    
    # Get and display messages
    messages = demo_librarian.get_messages()
    for msg in messages:
        print(f"\n{msg['icon']} [{msg['formatted_time']}] [{msg['tone']}]")
        print(f"   {msg['content']}")
    
    # Simulate turns
    print("\n--- Simulating Turns ---")
    for turn in range(1, 6):
        print(f"\n  Turn {turn}:")
        demo_librarian.current_files.add(f"file_{turn}.py")
        demo_librarian.record_turn(context_size=10000 * turn)
        new_messages = demo_librarian.get_messages(unread_only=True)
        for msg in new_messages:
            print(f"    {msg['icon']} {msg['content'][:80]}...")
    
    # Simulate a decision
    demo_librarian.record_decision(session_id, "We shall adopt the Repository pattern for data access")
    
    # Simulate trim warning
    print("\n--- Trim Warning ---")
    trim_warning = demo_librarian.warn_of_trim(session_id, "Large context content here...")
    print(f"\n{trim_warning.to_ui_format()['icon']} {trim_warning.content}")
    
    # Celebrate achievement
    print("\n--- Achievement ---")
    demo_librarian.celebrate(session_id, "Implemented core feature", "Repository pattern successfully integrated", significance=4)
    
    # Get all recent messages
    print("\n--- All Recent Messages ---")
    all_messages = demo_librarian.get_messages()
    for msg in all_messages:
        print(f"\n{msg['icon']} [{msg['tone']}] {msg['content'][:100]}...")
    
    # End session
    demo_librarian.end_session(session_id)
    
    # Show stats
    print("\n--- Librarian Stats ---")
    stats = demo_librarian.get_stats()
    print(json.dumps(stats, indent=2))
    
    print("\n" + "="*80)
    print("The Librarian's Voice demonstration complete.")
    print("="*80)

