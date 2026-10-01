"""
Terminal Librarian - Terminal Output Intelligence System
=========================================================

A terminal history management system that intelligently summarizes,
patterns, and provides voice-like suggestions for command-line workflows.

Author: FoveAI Forge
Version: 1.0.0
"""

import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any


class OutputType(Enum):
    """Classification of terminal output types."""

    COMMAND = auto()
    SUCCESS_OUTPUT = auto()
    ERROR_OUTPUT = auto()
    FILE_LISTING = auto()
    BUILD_OUTPUT = auto()
    STACK_TRACE = auto()
    INTERACTIVE_PROMPT = auto()
    NOISE = auto()
    VALUABLE = auto()


class RetentionPolicy(Enum):
    """How long different output types should be retained."""

    KEEP_FULL = "keep_full"  # Keep complete output
    KEEP_SUMMARY = "keep_summary"  # Keep only summary
    ARCHIVE = "archive"  # Archive with metadata
    DISCARD = "discard"  # Remove entirely


@dataclass
class CommandSegment:
    """A single command/response segment from terminal history."""

    timestamp: float
    command: str
    output: str
    output_type: OutputType
    exit_code: int | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    segment_hash: str = field(default="")

    def __post_init__(self):
        if not self.segment_hash:
            self.segment_hash = hashlib.md5(
                f"{self.command}:{self.timestamp}".encode()
            ).hexdigest()[:12]

    @property
    def is_successful(self) -> bool:
        return self.exit_code == 0 or self.exit_code is None

    @property
    def is_error(self) -> bool:
        return self.exit_code is not None and self.exit_code != 0

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "output_type": self.output_type.name,
            "is_successful": self.is_successful,
            "is_error": self.is_error,
        }


@dataclass
class Pattern:
    """Discovered command pattern or workflow."""

    pattern_type: str  # "sequence", "error_recovery", "workflow", "habit"
    commands: list[str]
    frequency: int
    confidence: float
    last_seen: float
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompressionRule:
    """Rule for compressing terminal output."""

    name: str
    pattern: re.Pattern
    output_type: OutputType
    retention: RetentionPolicy
    summarizer: Callable[[str], str] | None = None


class SmartSummarization:
    """Intelligent summarization engine for terminal output."""

    NOISE_PATTERNS = [
        r"^\s*$",
        r"^(Microsoft Windows|Copyright|\(c\))",
        r"^PS\s+",
        r"^[\s\-]+$",
    ]
    FILE_LISTING_PATTERNS = [
        r"^\s*Mode\s+LastWriteTime",
        r"^d[\-rwx]{9}\s+",
        r"^\-[\-rwx]{9}\s+",
        r"^\s+Directory:\s+",
        r"^\s+\d+\s+\w+\s+\d+\s+",
    ]
    BUILD_PATTERNS = [
        r"(?:Building|Compiling|Processing)\s+",
        r"\[\s*\d+%\s*\]",
        r"\d+\s+errors?\s*,\s*\d+\s+warnings?",
        r"^\s*==>\s+",
        r"^\s*--->\s+",
    ]
    ERROR_PATTERNS = [
        r"(?:Error|Exception|Fatal|Failed):\s*",
        r"Traceback\s+\(most\s+recent\s+call\s+last\)",
        r'^\s+File\s+"[^"]+",\s+line\s+\d+',
        r"(?:command\s+not\s+found|cannot\s+find)",
        r"(?:Permission\s+denied|Access\s+is\s+denied)",
    ]
    SUCCESS_PATTERNS = [
        r"(?:Successfully|Done|Complete|Finished)",
        r"(?:OK|SUCCESS|PASSED)\b",
    ]

    def __init__(self):
        self.rules: list[CompressionRule] = []
        self._compile_rules()

    def _compile_rules(self):
        self.rules.append(
            CompressionRule(
                name="file_listing",
                pattern=re.compile("|".join(self.FILE_LISTING_PATTERNS), re.IGNORECASE),
                output_type=OutputType.FILE_LISTING,
                retention=RetentionPolicy.DISCARD,
                summarizer=lambda x: "[File listing removed - regeneratable]",
            )
        )
        self.rules.append(
            CompressionRule(
                name="build_output",
                pattern=re.compile("|".join(self.BUILD_PATTERNS), re.IGNORECASE),
                output_type=OutputType.BUILD_OUTPUT,
                retention=RetentionPolicy.KEEP_SUMMARY,
                summarizer=self._summarize_build_output,
            )
        )
        self.rules.append(
            CompressionRule(
                name="stack_trace",
                pattern=re.compile("|".join(self.ERROR_PATTERNS), re.IGNORECASE),
                output_type=OutputType.STACK_TRACE,
                retention=RetentionPolicy.ARCHIVE,
                summarizer=self._summarize_stack_trace,
            )
        )
        self.rules.append(
            CompressionRule(
                name="noise",
                pattern=re.compile("|".join(self.NOISE_PATTERNS)),
                output_type=OutputType.NOISE,
                retention=RetentionPolicy.DISCARD,
                summarizer=lambda x: "",
            )
        )

    def classify_output(self, command: str, output: str) -> OutputType:
        """Classify terminal output by type."""
        for rule in self.rules:
            if rule.pattern.search(output) and rule.output_type == OutputType.NOISE:
                return OutputType.NOISE

        file_listing_indicators = ["ls -", "dir", "Get-ChildItem", "tree"]
        if any(cmd in command.lower() for cmd in file_listing_indicators):
            return OutputType.FILE_LISTING

        build_commands = [
            "build",
            "compile",
            "make",
            "npm run",
            "cargo build",
            "go build",
        ]
        if any(cmd in command.lower() for cmd in build_commands):
            return OutputType.BUILD_OUTPUT

        for rule in self.rules:
            if rule.output_type == OutputType.STACK_TRACE:
                if rule.pattern.search(output):
                    return OutputType.STACK_TRACE

        for pattern in self.SUCCESS_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return OutputType.SUCCESS_OUTPUT

        for pattern in self.ERROR_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return OutputType.ERROR_OUTPUT

        return OutputType.VALUABLE if output.strip() else OutputType.NOISE

    def _summarize_build_output(self, output: str) -> str:
        """Extract key information from build output."""
        lines = output.strip().split("\n")
        final_status, error_count, warning_count = "Unknown", 0, 0

        for line in lines:
            if re.search(r"(?:error|failed|fail)\s*[:\(]", line, re.IGNORECASE):
                error_count += 1
            if re.search(r"warning", line, re.IGNORECASE):
                warning_count += 1
            if re.search(r"(?:success|complete|done|built)\s*$", line, re.IGNORECASE):
                final_status = "Success"

        if error_count > 0:
            final_status = f"Failed ({error_count} errors, {warning_count} warnings)"
        elif final_status == "Unknown":
            final_status = "Completed"
        return f"[Build: {final_status}]"

    def _summarize_stack_trace(self, output: str) -> str:
        """Extract error type and key information from stack trace."""
        lines = output.strip().split("\n")
        error_type, error_message = "Unknown Error", ""
        relevant_file, line_number = "", ""

        for line in lines:
            if ":" in line and error_type == "Unknown Error":
                parts = line.split(":", 1)
                error_type = parts[0].strip()
                error_message = parts[1].strip() if len(parts) > 1 else ""
            match = re.search(r'File\s+"([^"]+)",\s+line\s+(\d+)', line)
            if match:
                relevant_file, line_number = match.group(1), match.group(2)
                break

        summary = f"[{error_type}"
        if relevant_file:
            summary += f" at {Path(relevant_file).name}:{line_number}"
        summary += "]"
        if error_message:
            summary += f" {error_message[:100]}"
        return summary

    def compress_segment(self, segment: CommandSegment) -> CommandSegment:
        """Apply intelligent compression to a segment."""
        retention = RetentionPolicy.KEEP_FULL
        for rule in self.rules:
            if rule.output_type == segment.output_type:
                retention = rule.retention
                break

        if retention == RetentionPolicy.DISCARD:
            compressed_output = "[Content discarded - regeneratable]"
        elif retention == RetentionPolicy.KEEP_SUMMARY:
            compressed_output = (
                segment.output[:200] + "..."
                if len(segment.output) > 200
                else segment.output
            )
            for rule in self.rules:
                if rule.output_type == segment.output_type and rule.summarizer:
                    compressed_output = rule.summarizer(segment.output)
                    break
        elif retention == RetentionPolicy.ARCHIVE:
            compressed_output = (
                segment.output[:500] + "..."
                if len(segment.output) > 500
                else segment.output
            )
            for rule in self.rules:
                if rule.output_type == segment.output_type and rule.summarizer:
                    compressed_output = rule.summarizer(segment.output)
                    break
        else:
            compressed_output = segment.output

        return CommandSegment(
            timestamp=segment.timestamp,
            command=segment.command,
            output=compressed_output,
            output_type=segment.output_type,
            exit_code=segment.exit_code,
            duration_ms=segment.duration_ms,
            metadata={
                **segment.metadata,
                "original_length": len(segment.output),
                "compressed": True,
            },
        )


class PatternExtractor:
    """Extracts patterns and workflows from terminal history."""

    def __init__(self, min_frequency: int = 3):
        self.min_frequency = min_frequency
        self.command_sequences: dict[tuple[str, ...], int] = defaultdict(int)
        self.error_recovery_pairs: dict[str, list[str]] = defaultdict(list)
        self.command_frequency: dict[str, int] = defaultdict(int)
        self.error_frequency: dict[str, int] = defaultdict(int)
        self.successful_fixes: dict[str, str] = {}
        self._last_commands: list[str] = []
        self._last_error: str | None = None

    def feed_segment(self, segment: CommandSegment):
        """Process a new segment for pattern extraction."""
        cmd = segment.command.strip()
        if not cmd:
            return

        self.command_frequency[cmd] += 1
        self._last_commands.append(cmd)
        if len(self._last_commands) > 3:
            self._last_commands.pop(0)

        if len(self._last_commands) >= 2:
            seq = tuple(self._last_commands[-2:])
            self.command_sequences[seq] += 1
        if len(self._last_commands) >= 3:
            seq = tuple(self._last_commands[-3:])
            self.command_sequences[seq] += 1

        if segment.is_error:
            self.error_frequency[cmd] += 1
            self._last_error = cmd
        elif self._last_error and segment.is_successful:
            self.error_recovery_pairs[self._last_error].append(cmd)
            fixes = self.error_recovery_pairs[self._last_error]
            if fixes:
                most_common = max(set(fixes), key=fixes.count)
                self.successful_fixes[self._last_error] = most_common
            self._last_error = None

    def extract_patterns(self) -> list[Pattern]:
        """Extract all discovered patterns."""
        patterns = []

        for seq, freq in self.command_sequences.items():
            if freq >= self.min_frequency:
                patterns.append(
                    Pattern(
                        pattern_type="sequence",
                        commands=list(seq),
                        frequency=freq,
                        confidence=min(freq / 10, 0.95),
                        last_seen=time.time(),
                        context={"type": "command_chain"},
                    )
                )

        for error_cmd, fixes in self.error_recovery_pairs.items():
            if len(fixes) >= self.min_frequency:
                most_common = max(set(fixes), key=fixes.count)
                patterns.append(
                    Pattern(
                        pattern_type="error_recovery",
                        commands=[error_cmd, most_common],
                        frequency=fixes.count(most_common),
                        confidence=min(len(fixes) / 10, 0.9),
                        last_seen=time.time(),
                        context={"error": error_cmd, "fix": most_common},
                    )
                )

        for cmd, freq in self.command_frequency.items():
            if freq >= self.min_frequency * 2:
                patterns.append(
                    Pattern(
                        pattern_type="habit",
                        commands=[cmd],
                        frequency=freq,
                        confidence=min(freq / 20, 0.95),
                        last_seen=time.time(),
                        context={"category": "frequent_command"},
                    )
                )

        return sorted(patterns, key=lambda p: p.confidence, reverse=True)

    def get_suggestions(self) -> list[str]:
        """Generate voice-like suggestions based on patterns."""
        suggestions = []
        patterns = self.extract_patterns()

        if self._last_commands:
            last_cmd = self._last_commands[-1]
            common_follows = [
                (p.commands[1], p.frequency)
                for p in patterns
                if p.pattern_type == "sequence"
                and len(p.commands) >= 2
                and p.commands[0] == last_cmd
            ]

            if common_follows:
                common_follows.sort(key=lambda x: x[1], reverse=True)
                suggestions.append(
                    f"After '{last_cmd}', you often run '{common_follows[0][0]}'. "
                    f"Consider: {common_follows[0][0]}"
                )

        for cmd, freq in self.error_frequency.items():
            if freq >= 3:
                if cmd in self.successful_fixes:
                    suggestions.append(
                        f"Command '{cmd}' has failed {freq} times. "
                        f"Consider running: {self.successful_fixes[cmd]}"
                    )
                else:
                    suggestions.append(
                        f"Command '{cmd}' has failed {freq} times. You might want to check your approach."
                    )

        for p in patterns:
            if p.pattern_type == "sequence" and len(p.commands) >= 3:
                if self._last_commands == list(p.commands[:2]):
                    suggestions.append(
                        f"You often follow this with '{p.commands[2]}'. Complete the workflow: {p.commands[2]}"
                    )

        return suggestions


class TerminalBuffer:
    """Main terminal buffer that captures, segments, and manages terminal output."""

    def __init__(
        self,
        max_segments: int = 1000,
        hot_segments: int = 50,
        archive_path: str | None = None,
    ):
        self.max_segments = max_segments
        self.hot_segments = hot_segments
        self.archive_path = Path(archive_path) if archive_path else None

        self.segments: list[CommandSegment] = []
        self.archive: list[CommandSegment] = []
        self.summarizer = SmartSummarization()
        self.pattern_extractor = PatternExtractor()

        self._current_command: str | None = None
        self._current_output: list[str] = []
        self._command_start_time: float | None = None
        self._lock = threading.Lock()

        if self.archive_path and self.archive_path.exists():
            self._load_archive()

    def start_command(self, command: str):
        """Signal start of a new command."""
        if self._current_command:
            self.finish_command()

        self._current_command = command.strip()
        self._current_output = []
        self._command_start_time = time.time()

    def append_output(self, output: str):
        """Append output to current command."""
        self._current_output.append(output)

    def finish_command(self, exit_code: int | None = None):
        """Finish current command and store segment."""
        if not self._current_command:
            return

        full_output = "".join(self._current_output)
        duration = (
            (time.time() - self._command_start_time) * 1000
            if self._command_start_time
            else None
        )

        output_type = self.summarizer.classify_output(
            self._current_command, full_output
        )

        segment = CommandSegment(
            timestamp=time.time(),
            command=self._current_command,
            output=full_output,
            output_type=output_type,
            exit_code=exit_code,
            duration_ms=duration,
        )

        self.pattern_extractor.feed_segment(segment)

        with self._lock:
            self.segments.append(segment)
            self._compress_history()
            self._archive_segments()

        self._current_command = None
        self._current_output = []
        self._command_start_time = None

        return segment

    def _compress_history(self):
        """Compress older segments based on retention policy."""
        if len(self.segments) <= self.hot_segments:
            return

        for i in range(len(self.segments) - self.hot_segments):
            if not self.segments[i].metadata.get("compressed"):
                self.segments[i] = self.summarizer.compress_segment(self.segments[i])

    def _archive_segments(self):
        """Move oldest segments to archive if exceeding max."""
        while len(self.segments) > self.max_segments:
            oldest = self.segments.pop(0)
            if oldest.is_error and oldest.output_type == OutputType.STACK_TRACE:
                self.archive.append(oldest)
            if len(self.archive) >= 100 and self.archive_path:
                self._save_archive()

    def _save_archive(self):
        """Save archive to disk."""
        if not self.archive_path:
            return
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_data = {
            "timestamp": time.time(),
            "segments": [s.to_dict() for s in self.archive],
        }
        with open(self.archive_path, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, indent=2)

    def _load_archive(self):
        """Load archive from disk."""
        try:
            with open(self.archive_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"Loaded {len(data.get('segments', []))} archived segments")
        except Exception as e:
            print(f"Could not load archive: {e}")

    def query(self, query_type: str, **kwargs) -> list[dict]:
        """Query the terminal history."""
        results = []

        if query_type == "command":
            pattern = kwargs.get("pattern", "").lower()
            results = [
                s.to_dict() for s in self.segments if pattern in s.command.lower()
            ]

        elif query_type == "error":
            error_type = kwargs.get("type", "").lower()
            results = [
                s.to_dict()
                for s in self.segments
                if s.is_error and (not error_type or error_type in s.output.lower())
            ]

        elif query_type == "fix":
            error_cmd = kwargs.get("error", "")
            if error_cmd in self.pattern_extractor.successful_fixes:
                fix_cmd = self.pattern_extractor.successful_fixes[error_cmd]
                results = [{"error": error_cmd, "fix": fix_cmd}]

        elif query_type == "pattern":
            patterns = self.pattern_extractor.extract_patterns()
            results = [p.to_dict() for p in patterns[: kwargs.get("limit", 10)]]

        elif query_type == "recent":
            limit = kwargs.get("limit", 10)
            results = [s.to_dict() for s in self.segments[-limit:]]

        return results

    def get_suggestions(self) -> list[str]:
        """Get voice-like suggestions."""
        return self.pattern_extractor.get_suggestions()

    def get_summary(self) -> dict:
        """Get summary of terminal history."""
        return {
            "total_segments": len(self.segments),
            "archived_segments": len(self.archive),
            "error_count": sum(1 for s in self.segments if s.is_error),
            "success_count": sum(1 for s in self.segments if s.is_successful),
            "patterns_discovered": len(self.pattern_extractor.extract_patterns()),
            "frequent_commands": sorted(
                self.pattern_extractor.command_frequency.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5],
        }

    def export_history(self, format: str = "json") -> str:
        """Export terminal history to various formats."""
        if format == "json":
            return json.dumps(
                {
                    "segments": [s.to_dict() for s in self.segments],
                    "summary": self.get_summary(),
                },
                indent=2,
            )
        elif format == "markdown":
            lines = ["# Terminal History\n"]
            for s in self.segments:
                lines.append(
                    f"## {datetime.fromtimestamp(s.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
                )
                lines.append(f"**Command:** `{s.command}`")
                lines.append(
                    f"**Result:** {'✓ Success' if s.is_successful else '✗ Error'}"
                )
                lines.append(f"```\n{s.output[:500]}\n```\n")
            return "\n".join(lines)
        return str(self.segments)


class MeshBusPublisher:
    """Publishes terminal events to a mesh message bus."""

    def __init__(self, bus_endpoint: str | None = None):
        self.bus_endpoint = bus_endpoint
        self.enabled = bus_endpoint is not None

    def publish_segment(self, segment: CommandSegment):
        if not self.enabled:
            return
        message = {
            "type": "terminal_segment",
            "timestamp": segment.timestamp,
            "command": segment.command,
            "success": segment.is_successful,
            "output_type": segment.output_type.name,
            "hash": segment.segment_hash,
        }
        print(f"[MESH BUS] Publishing: {message['command'][:50]}...")

    def publish_suggestion(self, suggestion: str):
        if not self.enabled:
            return
        message = {
            "type": "terminal_suggestion",
            "timestamp": time.time(),
            "suggestion": suggestion,
        }
        print(f"[MESH BUS] Suggestion: {suggestion[:80]}...")


class TerminalLibrarian:
    """Main interface for the Terminal Librarian system."""

    def __init__(
        self,
        archive_path: str | None = None,
        mesh_bus_endpoint: str | None = None,
    ):
        self.buffer = TerminalBuffer(archive_path=archive_path)
        self.mesh = MeshBusPublisher(mesh_bus_endpoint)
        self._voice_enabled = True

    def capture_command(self, command: str):
        self.buffer.start_command(command)

    def capture_output(self, output: str):
        self.buffer.append_output(output)

    def complete_command(self, exit_code: int = 0):
        segment = self.buffer.finish_command(exit_code)
        if segment:
            self.mesh.publish_segment(segment)
        if self._voice_enabled:
            for suggestion in self.buffer.get_suggestions()[-3:]:
                self.mesh.publish_suggestion(suggestion)
                print(f"📚 Librarian: {suggestion}")

    def speak(self, message: str):
        print(f"📚 Terminal Librarian: {message}")

    def ask(self, question: str) -> list[dict]:
        question = question.lower()
        if "command that fixed" in question or "fix for" in question:
            match = re.search(r"(?:fixed|fix for)\s+(\S+)", question)
            if match:
                return self.buffer.query("fix", error=match.group(1))
        elif "failed" in question or "error" in question:
            return self.buffer.query("error")
        elif "recent" in question:
            return self.buffer.query("recent", limit=10)
        elif "pattern" in question or "often" in question:
            return self.buffer.query("pattern")
        else:
            return self.buffer.query("command", pattern=question)
        return []

    def get_report(self) -> str:
        summary = self.buffer.get_summary()
        patterns = self.buffer.query("pattern", limit=5)
        report = [
            "=" * 60,
            "TERMINAL LIBRARIAN REPORT",
            "=" * 60,
            "",
            f"Total Commands: {summary['total_segments']}",
            f"Successful: {summary['success_count']}",
            f"Errors: {summary['error_count']}",
            f"Patterns Discovered: {summary['patterns_discovered']}",
            "",
        ]
        if summary["frequent_commands"]:
            report.append("Top Commands:")
            for cmd, freq in summary["frequent_commands"]:
                report.append(f"  {freq}x: {cmd[:50]}")
        if patterns:
            report.append("")
            report.append("Discovered Patterns:")
            for p in patterns[:5]:
                if p["pattern_type"] == "sequence":
                    report.append(f"  → {' → '.join(p['commands'])}")
                elif p["pattern_type"] == "error_recovery":
                    report.append(f"  ⚠ {p['commands'][0]} → ✓ {p['commands'][1]}")
        report.append("=" * 60)
        return "\n".join(report)


# =============================================================================
# POWERSHELL INTEGRATION
# =============================================================================

POWERSHELL_PROFILE_ADDON = """
# Terminal Librarian Integration
$env:TERMINAL_LIBRARIAN_PATH = "C:\\Users\\lumba\\Program\\FoveAI\\Forge\\terminal_librarian.py"

function Invoke-LibrarianWrappedExpression {
    param([string]$Command)
    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fff"
    $commandJson = @{type="command_start"; timestamp=$timestamp; command=$Command; pwd=$PWD.Path} | ConvertTo-Json -Compress
    $commandJson | Out-File -Append -FilePath "$env:TEMP\\terminal_librarian_input.jsonl"
    try {
        $output = Invoke-Expression $Command 2>&1
        $exitCode = $LASTEXITCODE; if (-not $exitCode) { $exitCode = 0 }
        $completionJson = @{type="command_complete"; timestamp=(Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fff"); command=$Command; exit_code=$exitCode; output=($output | Out-String)} | ConvertTo-Json -Compress
        $completionJson | Out-File -Append -FilePath "$env:TEMP\\terminal_librarian_input.jsonl"
        return $output
    }
    catch {
        $errorJson = @{type="command_error"; timestamp=(Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fff"); command=$Command; error=$_.Exception.Message} | ConvertTo-Json -Compress
        $errorJson | Out-File -Append -FilePath "$env:TEMP\\terminal_librarian_input.jsonl"
        throw
    }
}

$CommandsToTrack = @('git', 'npm', 'docker', 'python', 'pip', 'cargo', 'go')
foreach ($cmd in $CommandsToTrack) {
    Invoke-Expression "function Librarian-Wrap-$cmd { param([Parameter(ValueFromRemainingArguments=\\$true)]\\$Args) \\$cmdLine = \"$cmd \\$(\\$Args -join ' ')\"; Invoke-LibrarianWrappedExpression -Command \\$cmdLine }; Set-Alias -Name $cmd -Value Librarian-Wrap-$cmd -Option AllScope -Force"
}

function Ask-Librarian { param([string]$Question); python -c "from terminal_librarian import TerminalLibrarian; lib = TerminalLibrarian(); print(lib.ask('$Question'))" }
Set-Alias -Name "ask" -Value Ask-Librarian
Write-Host "📚 Terminal Librarian loaded. Type 'ask \"<question>\"' to query history."
"""


def generate_powershell_profile():
    """Generate PowerShell profile integration code."""
    return POWERSHELL_PROFILE_ADDON


# =============================================================================
# EXAMPLE AND DEMONSTRATION
# =============================================================================


def run_demonstration():
    """Demonstrate the Terminal Librarian with simulated terminal output."""
    print("=" * 70)
    print("TERMINAL LIBRARIAN DEMONSTRATION")
    print("=" * 70)
    print("\nSimulating terminal session with various command types...\n")

    librarian = TerminalLibrarian(
        archive_path=os.path.join(
            os.getenv("FoveAI_REPO_ROOT", os.path.dirname(os.path.dirname(__file__))),
            "Forge",
            ".logs",
            "terminal_archive.json",
        )
    )

    session = [
        {
            "command": "ls -la",
            "output": "total 128\ndrwxr-xr-x 5 user user 4096 Jan 15 10:00 .\n-rw-r--r-- 1 user user 2204 Jan 15 10:00 README.md\n-rw-r--r-- 1 user user 1532 Jan 15 09:45 setup.py",
            "exit_code": 0,
        },
        {
            "command": "npm run build",
            "output": "> project@1.0.0 build\n> webpack --mode production\n\nBuilding for production...\nasset main.js 245 KiB\n[0] ./src/index.js 2.34 KiB\nwebpack compiled successfully in 3421ms\nBuild completed.",
            "exit_code": 0,
        },
        {
            "command": "git push origin main",
            "output": "To https://github.com/user/repo.git\n ! [rejected] main -> main (fetch first)\nerror: failed to push some refs\nhint: Updates were rejected...",
            "exit_code": 1,
        },
        {
            "command": "git pull origin main --rebase",
            "output": "remote: Enumerating objects: 5\nFrom https://github.com/user/repo\nSuccessfully rebased.",
            "exit_code": 0,
        },
        {
            "command": "python run_tests.py",
            "output": "Traceback (most recent call last):\n  File \"run_tests.py\", line 15\n    response = api.get('/users')\nAttributeError: 'NoneType' object has no attribute 'get'\nSystemExit: 1",
            "exit_code": 1,
        },
        {
            "command": "python run_tests.py",
            "output": ".........\n----------------------------------------------------------------------\nRan 45 tests in 0.342s\n\nOK",
            "exit_code": 0,
        },
        {
            "command": "docker build -t myapp:latest .",
            "output": 'Sending build context...\nStep 1/8 : FROM python:3.10-slim\n ---> a1b2c3d4e5f6\nStep 8/8 : CMD ["python", "app.py"]\nSuccessfully built myapp\nSuccessfully tagged myapp:latest',
            "exit_code": 0,
        },
        {"command": "pwd", "output": "/home/user/project\n", "exit_code": 0},
    ]

    for i, cmd_data in enumerate(session, 1):
        print(f"\n{'─' * 70}")
        print(f"Command {i}: {cmd_data['command']}")
        print(f"{'─' * 70}")

        librarian.capture_command(cmd_data["command"])
        librarian.capture_output(cmd_data["output"])
        librarian.complete_command(cmd_data["exit_code"])

        recent = librarian.buffer.query("recent", limit=1)[0]
        print(f"Stored as: {recent['output_type']}")
        print(f"Original length: {len(cmd_data['output'])} chars")
        print(f"Compressed to: {len(recent['output'])} chars")
        print(f"Content: {recent['output'][:150]}...")

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(librarian.get_report())

    print("\n" + "=" * 70)
    print("DISCOVERED PATTERNS")
    print("=" * 70)
    patterns = librarian.buffer.query("pattern")
    for p in patterns[:5]:
        print(f"\nType: {p['pattern_type']}")
        print(f"Commands: {' → '.join(p['commands'])}")
        print(f"Frequency: {p['frequency']}, Confidence: {p['confidence']:.2f}")

    print("\n" + "=" * 70)
    print("LIBRARIAN SUGGESTIONS")
    print("=" * 70)
    for suggestion in librarian.buffer.get_suggestions():
        librarian.speak(suggestion)

    print("\n" + "=" * 70)
    print("QUERY API DEMONSTRATIONS")
    print("=" * 70)

    print("\n❓ Query: 'what was that command that fixed git push?'")
    results = librarian.ask("what was that command that fixed git push")
    print(f"✓ Found fix: {results}")

    print("\n❓ Query: 'show recent errors'")
    results = librarian.ask("show recent errors")
    print(f"✓ Found {len(results)} error(s)")
    for r in results[:2]:
        print(f"  - {r['command']}: {r['output_type']}")

    print("\n" + "=" * 70)
    print("COMPRESSION STATISTICS")
    print("=" * 70)
    total_original = sum(len(cmd["output"]) for cmd in session)
    total_stored = sum(len(s.output) for s in librarian.buffer.segments)
    ratio = total_original / max(total_stored, 1)
    print(f"Original output size: {total_original:,} chars")
    print(f"Stored size: {total_stored:,} chars")
    print(f"Compression ratio: {ratio:.1f}x")

    print("\n" + "=" * 70)
    print("EXPORTED HISTORY (first 500 chars)")
    print("=" * 70)
    print(librarian.buffer.export_history("json")[:500])

    return librarian


if __name__ == "__main__":
    librarian = run_demonstration()

    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print("\nTo integrate with PowerShell, add the following to your profile:")
    print("\n" + generate_powershell_profile())
