#!/usr/bin/env python3
"""
FoveAI Memory MCP Server v3.0 - Local LLM Middleman Edition

Architecture:
  Cloud Model (DeepSeek/GLM/etc) ←→ Cline ←→ MCP Server ←→ Local LLM (middleman)
                                                         ←→ Memory/Docs Index
                                                         ←→ Codebase Index

The middleman compresses data BEFORE it reaches the cloud model,
saving tokens and preventing context overflow. This is the DEFAULT mode.

Key Features:
  - Deterministic extractive compressor — no external LLM required
    (optional LLM path via LOCAL_LLM_BASE, e.g. the XRLF runtime :8402)
  - All search results compressed by default (raw search requires explicit flag)
  - Codebase indexing: scan directories, index files, search with context
  - Auto-compact memory: long entries auto-summarized by local LLM
  - Session context injection with compression
"""

import asyncio
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

# Add Forge to path so we can import skeleton_parser
FORGE_PATH = (
    Path(os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent.parent))
    / "Forge"
)
if str(FORGE_PATH) not in sys.path:
    sys.path.append(str(FORGE_PATH))

try:
    import skeletal_memory
    from skeleton_parser import global_parser
except ImportError:
    global_parser = None
    skeletal_memory = None

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

FoveAI_ROOT = Path(
    os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent.parent)
)

# Data paths
MEMORY_INDEX_PATH = FoveAI_ROOT / ".logs" / "memory_index.json"
IMPORTED_SOURCES_PATH = FoveAI_ROOT / ".logs" / "imported_sources.json"
DOCS_INDEX_PATH = FoveAI_ROOT / ".logs" / "docs_index.json"
CODEBASE_INDEX_PATH = FoveAI_ROOT / ".logs" / "codebase_index.json"
PLANS_INDEX_PATH = FoveAI_ROOT / ".logs" / "plans_index.json"

# External history paths
CLINE_TASKS_PATH = (
    Path.home() / "AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/tasks"
)
GEMINI_HISTORY_PATH = Path.home() / ".gemini/history"
MIGRATION_CLINE_PATH = Path(
    "H:/MIGRATION/SYSTEM_CONFIG/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/tasks"
)

# Compression middleman settings.
# Default: deterministic extractive compressor — no external LLM needed.
# Optional LLM path: set LOCAL_LLM_BASE to an OpenAI-compatible endpoint
# (e.g. http://127.0.0.1:8402/v1 for the XRLF runtime) to try it first.
LOCAL_LLM_BASE = os.getenv("LOCAL_LLM_BASE", "")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "auto")
LOCAL_LLM_TIMEOUT = int(os.getenv("LOCAL_LLM_TIMEOUT", "60"))
LOCAL_LLM_AUTO_START = os.getenv(
    "foveai_mcp_context", os.getenv("FoveAI_MCP_CONTEXT", "false")
).lower() in ("true", "1", "yes")

# Codebase indexing defaults
DEFAULT_INDEX_DIRS = [
    str(FoveAI_ROOT),  # Full repo index by default
]

# Extensions to index — comprehensive, covering all code/config/doc types
INDEX_EXTENSIONS = {
    # Programming languages
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".mjs",
    ".cjs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".java",
    ".kt",
    ".swift",
    ".dart",
    ".rs",
    ".go",
    ".rb",
    ".php",
    ".lua",
    ".r",
    ".R",
    ".glsl",
    ".hlsl",
    ".shader",
    ".cginc",
    # Web & markup
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    ".xml",
    ".svg",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".rst",
    ".txt",
    ".adoc",
    # Data & config
    ".json",
    ".json5",
    ".jsonc",
    ".csv",
    # Shell & scripting
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".cmd",
    ".bat",
    ".dockerfile",
    ".containerfile",
    # Project files
    ".csproj",
    ".sln",
    ".gradle",
    ".cmake",
    ".makefile",
    ".gitignore",
    ".editorconfig",
    ".eslintrc",
    ".prettierrc",
    ".babelrc",
    ".browserslistrc",
    ".nvmrc",
    ".npmrc",
    ".yarnrc",
    # Config that should be detected (content may be redacted)
    ".env",
    ".env.local",
    ".env.example",
    # Godot/Unity project files
    ".tscn",
    ".gd",
    ".tres",
    # Other
    ".proto",
    ".graphql",
    ".sql",
    ".wasm",
}

# Directories to skip — derived from .gitignore but less strict
# (we still want to see source code in framework dirs, just not their internals)
SKIP_DIRS = {
    # VCS & IDE
    ".git",
    ".idea",
    ".vs",
    ".vscode",
    # Python
    "__pycache__",
    ".venv",
    "venv",
    "venv_mouth",
    ".aider-venv",
    "lib",
    "bin",
    "include",
    "share",
    "lib64",
    "pyvenv.cfg",
    # Node
    "node_modules",
    "dist",
    "build",
    # Engine artifacts
    ".godot",
    ".import",
    "Library",
    "obj",
    "Build",
    # Data & caches
    ".cache",
    "chroma_db",
    "kuzu_db",
    "Data",
    "storage",
    "models",
    "user_data",
    "hf_cache",
    "huggingface",
    "f5tts_hf_cache_hub",
    # Archives & logs
    ".logs",
    "archive",
    "imported_sessions",
    "imported_git_history",
    "snapshots",
    "backups",
    # Runtime
    "trash",
}

# Files whose CONTENT should be redacted (index path/existence only, not contents)
SENSITIVE_FILE_PATTERNS = {".env", ".env.local"}
# Files matching these patterns should be skipped entirely
SKIP_FILE_PATTERNS = {
    # Binaries
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pyd",
    ".whl",
    # Archives
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".iso",
    ".img",
    ".dmg",
    # Media
    ".wav",
    ".mp3",
    ".ogg",
    ".opus",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".pdf",
    # Model weights
    ".safetensors",
    ".ckpt",
    ".pth",
    ".gguf",
    ".mmproj",
    ".onnx",
    # Large data
    ".csv",
    ".vhdx",
    # Unity/Godot compiled
    ".csproj.meta",
    ".prefab.meta",
}

# Maximum content to store per file (chars)
MAX_CONTENT_PER_FILE = 8000

# .MCP-ignore template — auto-generated per directory based on smart assessment
MCP_IGNORE_FILENAME = ".MCP-ignore"

# Active directory tracking file
ACTIVE_DIRS_PATH = FoveAI_ROOT / ".logs" / "active_dirs.json"

# Ensure directories exist
MEMORY_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# Local LLM Middleman
# ═══════════════════════════════════════════════════════════════


class Compressor:
    """Deterministic extractive compressor — no external LLM required.

    Scores sentences/lines by focus-keyword overlap, corpus term frequency
    and position, greedily fills the word budget, emits picks in original
    order. If LOCAL_LLM_BASE is explicitly set, an OpenAI-compatible
    endpoint (e.g. the XRLF runtime at :8402) is tried first and
    extraction is the fallback. The LLM is never required.
    """

    STOPWORDS = frozenset(
        "a an the and or but in on at to for of with by is are was were be "
        "been it its this that these those i you he she they we do does did "
        "have has had will would can could should may might not no yes "
        "from as if then than so such more other some into".split()
    )

    def __init__(self):
        self.base_url = LOCAL_LLM_BASE or None  # empty string → no LLM path
        self.model = LOCAL_LLM_MODEL
        self.timeout = LOCAL_LLM_TIMEOUT
        self._available = None

    # ── deterministic extraction ─────────────────────────────────────

    def _split_units(self, text: str) -> list[str]:
        """Split into sentence-ish units; keep code lines intact."""
        units: list[str] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Code / structured lines stay whole; prose splits on sentence ends.
            # Code = leading keyword/comment or trailing structural punct —
            # a mid-sentence ';' or '()' in prose must NOT count as code.
            if re.match(r"^\s*(def |class |import |from |const |let |var |function |if |for |while |return |//|#|/\*|<!--)", line) or re.search(r"[{};]\s*$|^\s*[})\]]", line):
                units.append(line)
            else:
                units.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip())
        return units

    def _score(self, units: list[str], focus_terms: set[str]) -> list[tuple[float, int, str]]:
        from collections import Counter

        freq: Counter = Counter()
        for u in units:
            for w in set(re.findall(r"[A-Za-z_]{3,}", u.lower())):
                if w not in self.STOPWORDS:
                    freq[w] += 1
        n = max(len(units), 1)
        scored = []
        for i, u in enumerate(units):
            words = set(re.findall(r"[A-Za-z_]{3,}", u.lower())) - self.STOPWORDS
            base = sum(freq[w] for w in words) / max(len(words) ** 0.5, 1.0)
            base += 2.0 * len(words & focus_terms)               # focus overlap dominates
            base += 0.5 * (i / n)                                 # recency — endings carry conclusions
            if re.search(r"\b(def|class|error|fix|decision|path|file)\b", u.lower()):
                base += 0.3                                       # structural anchors
            scored.append((base, i, u))
        return scored

    def _extractive(self, text: str, focus: str, max_words: int) -> str:
        units = self._split_units(text)
        focus_terms = {
            w for w in re.findall(r"[A-Za-z_]{3,}", focus.lower())
            if w not in self.STOPWORDS
        }
        scored = sorted(self._score(units, focus_terms), key=lambda t: -t[0])
        picked: list[tuple[int, str]] = []
        words_left = max_words
        for _score, i, u in scored:
            wlen = len(u.split())
            if wlen <= words_left or not picked:
                picked.append((i, u))
                words_left -= wlen
            if words_left <= 0:
                break
        picked.sort(key=lambda t: t[0])
        return "\n".join(u for _, u in picked)

    # ── optional LLM path (opt-in via LOCAL_LLM_BASE) ────────────────

    def check_available(self) -> dict[str, Any]:
        """Report compressor status. Always available; LLM path is opt-in."""
        if not self.base_url:
            return {
                "status": "available",
                "method": "extractive",
                "note": "Deterministic compressor — always on. Set LOCAL_LLM_BASE "
                        "(e.g. http://127.0.0.1:8402/v1) to enable an optional LLM path.",
            }
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models", headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("data", [])
                model_names = [m.get("id", "?") for m in models[:5]]
                self._available = True
                return {
                    "status": "available",
                    "method": "llm+extractive",
                    "endpoint": self.base_url,
                    "models": model_names,
                    "model_count": len(models),
                    "default_middleman": self.model,
                }
        except Exception as e:
            self._available = False
            return {
                "status": "llm_unavailable_fallback_extractive",
                "endpoint": self.base_url,
                "error": str(e),
            }

    def auto_start(self) -> dict[str, Any]:
        """No-op: the deterministic compressor needs nothing started.
        When an LLM endpoint is configured we just re-probe it — starting
        the stack is the ignition service's job, not ours."""
        if not self.base_url:
            return {
                "status": "not_needed",
                "method": "extractive",
                "note": "Deterministic compressor requires no external service.",
            }
        return {"status": "probed", "result": self.check_available()}

    def call(
        self,
        prompt: str,
        system: str = "You are a concise summarizer. Be brief and factual.",
        max_tokens: int = 1500,
    ) -> str:
        """Optional LLM call — only when LOCAL_LLM_BASE is configured.
        Returns empty string on failure or when unconfigured."""
        if not self.base_url:
            return ""
        try:
            payload = json.dumps(
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    # XRLF utility lane — no soul/memory/evolution on meta calls
                    "xrlf_utility": True,
                    "xrlf_headless": True,
                    "xrlf_thinking": False,
                }
            ).encode("utf-8")

            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})

                # Reasoning models may answer in reasoning_content
                content = message.get("content", "") or ""
                reasoning = (
                    message.get("reasoning_content", "")
                    or message.get("reasoning", "")
                    or ""
                )
                out = content if content.strip() else reasoning
                # The XRLF runtime injects soul markup (<emotion:…> <thought:…>
                # <mode:…> …) into every request — strip it from utility output.
                return re.sub(r"<[a-z_]+:[^>]*>", "", out).strip()
        except Exception as e:
            print(f"[MCP] Optional LLM call failed: {e}", file=sys.stderr)
            return ""

    def summarize(
        self,
        text: str,
        focus: str = "key facts, decisions, code changes, and current task state",
        max_words: int = 400,
    ) -> dict[str, Any]:
        """Compress text. Deterministic extractive by default; optional LLM
        endpoint tried first when LOCAL_LLM_BASE is configured."""
        if not text:
            return {"summary": "", "method": "empty", "original_length": 0}

        if len(text) < 300:
            return {
                "summary": text,
                "method": "passthrough",
                "original_length": len(text),
            }

        result = self.call(
            f"Summarize in under {max_words} words. Focus on: {focus}.\n\nTEXT:\n{text}"
        ) if self.base_url else ""

        if result:
            return {
                "summary": result,
                "method": "local_llm",
                "original_length": len(text),
                "summary_length": len(result),
                "compression_ratio": round(len(text) / max(len(result), 1), 1),
            }

        extracted = self._extractive(text, focus, max_words)
        return {
            "summary": extracted,
            "method": "extractive",
            "original_length": len(text),
            "summary_length": len(extracted),
            "compression_ratio": round(len(text) / max(len(extracted), 1), 1),
        }


# Global instance
compressor = Compressor()


# ═══════════════════════════════════════════════════════════════
# Memory Server
# ═══════════════════════════════════════════════════════════════


class MemoryServer:
    """MCP Server with local LLM middleman compression."""

    def __init__(self):
        self.conversations: list[dict[str, Any]] = []
        self.sources: dict[str, Any] = {}
        self.docs: list[dict[str, Any]] = []
        self.codebase: dict[
            str, dict[str, Any]
        ] = {}  # path -> {content, hash, mtime, lang}
        self.session_id = datetime.now().isoformat()
        self.load_memory()
        self.load_sources()
        self.load_docs()
        self.load_codebase()

    # ─── Persistence ──────────────────────────────────────────

    def load_memory(self):
        try:
            if MEMORY_INDEX_PATH.exists():
                with open(MEMORY_INDEX_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.conversations = data.get("conversations", [])
                    print(
                        f"[MCP] Loaded {len(self.conversations)} conversations",
                        file=sys.stderr,
                    )
        except Exception as e:
            print(f"[MCP] Error loading memory: {e}", file=sys.stderr)
            self.conversations = []

    def save_memory(self):
        try:
            with open(MEMORY_INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "conversations": self.conversations[-500:],
                        "last_updated": datetime.now().isoformat(),
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            print(f"[MCP] Error saving memory: {e}", file=sys.stderr)

    def load_sources(self):
        try:
            if IMPORTED_SOURCES_PATH.exists():
                with open(IMPORTED_SOURCES_PATH, "r", encoding="utf-8") as f:
                    self.sources = json.load(f)
        except Exception:
            self.sources = {}

    def save_sources(self):
        try:
            with open(IMPORTED_SOURCES_PATH, "w", encoding="utf-8") as f:
                json.dump(self.sources, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MCP] Error saving sources: {e}", file=sys.stderr)

    def load_docs(self):
        try:
            if DOCS_INDEX_PATH.exists():
                with open(DOCS_INDEX_PATH, "r", encoding="utf-8") as f:
                    self.docs = json.load(f).get("docs", [])
        except:
            self.docs = []

    def save_docs(self):
        try:
            with open(DOCS_INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {"docs": self.docs[-2000:], "updated": datetime.now().isoformat()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except:
            pass

    def load_codebase(self):
        try:
            if CODEBASE_INDEX_PATH.exists():
                with open(CODEBASE_INDEX_PATH, "r", encoding="utf-8") as f:
                    self.codebase = json.load(f).get("files", {})
                print(
                    f"[MCP] Loaded {len(self.codebase)} indexed files", file=sys.stderr
                )
        except:
            self.codebase = {}

    def save_codebase(self):
        try:
            with open(CODEBASE_INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {"files": self.codebase, "updated": datetime.now().isoformat()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            print(f"[MCP] Error saving codebase: {e}", file=sys.stderr)

    # ─── Memory Operations ─────────────────────────────────────

    async def add_conversation(
        self, role: str, content: str, metadata: dict[str, Any] = None
    ) -> int:
        """Add a conversation turn. Auto-compacts if entry is long."""
        # Dedup check
        content_prefix = content[:200] if content else ""
        for existing in reversed(self.conversations[-50:]):
            if (
                existing.get("role") == role
                and existing.get("content", "")[:200] == content_prefix
                and existing.get("session_id") == self.session_id
            ):
                existing["timestamp"] = datetime.now().isoformat()
                if metadata:
                    existing.get("metadata", {}).update(metadata)
                self.save_memory()
                return len(self.conversations)

        metadata = metadata or {}

        # Auto-compact: if content > 2000 chars, try to summarize
        if len(content) > 2000 and role != "system":
            # Attempt XRL node extraction first (xrlated memory)
            if skeletal_memory:
                try:
                    nodes = await skeletal_memory.extract_nodes_from_turn(content)
                    if nodes:
                        node_str = "\n".join(
                            f"- [{n.get('category', 'info')}] {n.get('summary', '')}"
                            for n in nodes
                        )
                        content = f"[XRL-compressed from {len(content)} chars]\n{node_str}\n\n---ORIGINAL HEAD---\n{content[:500]}"
                        metadata["xrlated"] = True
                        metadata["nodes"] = nodes
                except Exception as e:
                    print(f"[MCP] XRL extraction error: {e}", file=sys.stderr)

            # Fallback to deterministic extraction if XRL compression didn't apply
            if "xrlated" not in metadata:
                summary = compressor.summarize(
                    content,
                    focus="key decisions, code changes, errors and resolutions",
                    max_words=200,
                )
                if summary.get("method") in ("local_llm", "extractive"):
                    content = f"[Auto-compressed from {len(content)} chars] {summary['summary']}\n\n---ORIGINAL HEAD---\n{content[:500]}"
                    metadata["auto_compressed"] = True

        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "metadata": metadata,
        }
        self.conversations.append(entry)
        self.save_memory()
        return len(self.conversations)

    def get_recent_context(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.conversations[-limit:]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        query_lower = query.lower()
        results = []
        for entry in reversed(self.conversations):
            content = entry.get("content", "")
            if query_lower in content.lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_injection_prompt(
        self, max_tokens: int | None = None, disabled: bool = False
    ) -> str:
        """Generate session context with strict token bounds and optional env overrides.

        Controls:
          - FOVEAI_MCP_CONTEXT=0 or 'false' disables auto-injection completely (prevents context flooding).
          - FOVEAI_MCP_MAX_CONTEXT_TOKENS=800 caps the injection footprint to ~800 tokens max (~3200 chars).
        """
        import re

        # Check environment overrides
        env_ctx_cfg = (
            os.getenv(
                "FOVEAI_MCP_CONTEXT",
                os.getenv(
                    "foveai_mcp_context", os.getenv("FoveAI_MCP_CONTEXT", "true")
                ),
            )
            .lower()
            .strip()
        )
        if (
            disabled
            or env_ctx_cfg in ("false", "0", "off", "none", "disabled")
            or max_tokens == 0
        ):
            return "=== FoveAI ACTIVE CONCORDIA SESSION INJECTION ===\n[Context injection disabled by configuration (FOVEAI_MCP_CONTEXT=0)]\n"

        # Determine token budget limit (default: 800 tokens / ~3200 chars max)
        env_max_tokens = int(os.getenv("FOVEAI_MCP_MAX_CONTEXT_TOKENS", "800"))
        limit_tokens = max_tokens if (max_tokens and max_tokens > 0) else env_max_tokens
        max_chars = limit_tokens * 4

        lines = ["=== FoveAI ACTIVE CONCORDIA SESSION INJECTION ===\n"]

        # 1. Read System Status (uptodate.md component status table)
        uptodate_path = FoveAI_ROOT / "uptodate.md"
        if uptodate_path.exists():
            try:
                content = uptodate_path.read_text(encoding="utf-8", errors="replace")
                status_match = re.search(
                    r"(## 1\.\s+COMPONENT STATUS.*?)(?=\n---|\n##|\Z)",
                    content,
                    re.DOTALL | re.IGNORECASE,
                )
                if status_match:
                    lines.append("[SYSTEM STATUS (uptodate.md)]")
                    lines.append(status_match.group(1).strip()[:1000])
                    lines.append("")
            except Exception as e:
                print(
                    f"[MCP] Error reading uptodate.md for injection: {e}",
                    file=sys.stderr,
                )

        # 2. Read Recent Tasks (last ~15 lines of context.md)
        context_path = FoveAI_ROOT / "context.md"
        if context_path.exists():
            try:
                content = context_path.read_text(encoding="utf-8", errors="replace")
                content_lines = content.splitlines()
                last_lines = content_lines[-15:]
                lines.append("[RECENT COMPLETED TASKS (context.md)]")
                lines.append("\n".join(last_lines).strip()[:800])
                lines.append("")
            except Exception as e:
                print(
                    f"[MCP] Error reading context.md for injection: {e}",
                    file=sys.stderr,
                )

        # 3. Read Repository Structure (directory tree & ports from repo-principia.md)
        skeleton_path = FoveAI_ROOT / "repo-principia.md"
        if not skeleton_path.exists():
            skeleton_path = FoveAI_ROOT / "repo-skeleton.md"
        if skeleton_path.exists():
            try:
                content = skeleton_path.read_text(encoding="utf-8", errors="replace")
                skeleton_lines = content.splitlines()
                header_lines = []
                for l in skeleton_lines:
                    if l.startswith("## Backend"):
                        break
                    header_lines.append(l)
                lines.append("[REPOSITORY STRUCTURE (repo-principia.md)]")
                lines.append("\n".join(header_lines).strip()[:1000])
                lines.append("")
            except Exception as e:
                print(
                    f"[MCP] Error reading repo-principia.md for injection: {e}",
                    file=sys.stderr,
                )

        # 4. Add Conversation History from memory server (last 4 turns)
        recent = self.get_recent_context(4)
        if recent:
            history_lines = []
            for entry in recent:
                role = entry.get("role", "unknown")
                content = entry.get("content", "")
                history_lines.append(f"{role}: {content[:150]}...")

            combined_history = "\n".join(history_lines)
            lines.append("[RECENT CONVERSATION HISTORY (Memory)]")
            lines.append(combined_history[:600])
            lines.append("")

        lines.append("================================================\n")
        full_text = "\n".join(lines)
        if len(full_text) > max_chars:
            full_text = (
                full_text[:max_chars] + "\n... [TRUNCATED TO FIT CONTEXT BUDGET] ...\n"
            )
        return full_text

    # ─── Smart Directory Assessment ──────────────────────────────

    def assess_directory(self, directory: str) -> dict[str, Any]:
        """Smart assessment of a directory structure using local LLM.
        Scans top-level dirs/files, sends to LLM to generate .MCP-ignore.
        Returns the assessment and whether a .MCP-ignore was created."""
        dir_path = Path(directory)
        if not dir_path.exists():
            return {"error": f"Directory not found: {directory}"}

        mcp_ignore_path = dir_path / MCP_IGNORE_FILENAME

        # If .MCP-ignore already exists, read it and return
        if mcp_ignore_path.exists():
            patterns = self._parse_mcp_ignore(mcp_ignore_path)
            return {
                "action": "existing",
                "directory": directory,
                "mcp_ignore": str(mcp_ignore_path),
                "skip_dirs": patterns["skip_dirs"],
                "skip_patterns": patterns["skip_patterns"],
                "redact_patterns": patterns["redact_patterns"],
                "note": ".MCP-ignore already exists. Delete it to force re-assessment.",
            }

        # Scan top-level structure
        top_dirs = []
        top_files = []
        try:
            for item in sorted(dir_path.iterdir()):
                if item.is_dir():
                    top_dirs.append(item.name)
                elif item.is_file():
                    top_files.append(item.name)
        except PermissionError:
            return {"error": f"Permission denied scanning {directory}"}

        # Deterministic ignore-file generation — a directory listing is
        # exactly the input a rule-based generator needs; no LLM required.
        result = self._generate_default_mcp_ignore(top_dirs, top_files)

        # Clean up the response — remove markdown code fences if present
        content = result.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        # Write .MCP-ignore
        try:
            with open(mcp_ignore_path, "w", encoding="utf-8") as f:
                f.write("# .MCP-ignore — Auto-generated by FoveAI MCP Server\n")
                f.write(f"# Directory: {directory}\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n")
                f.write("# Delete this file to force re-assessment\n\n")
                f.write(content)
                f.write("\n")
        except Exception as e:
            return {"error": f"Failed to write .MCP-ignore: {e}", "assessment": content}

        patterns = self._parse_mcp_ignore(mcp_ignore_path)
        return {
            "action": "generated",
            "directory": directory,
            "mcp_ignore": str(mcp_ignore_path),
            "assessment_content": content[:500],
            "skip_dirs": patterns["skip_dirs"],
            "skip_patterns": patterns["skip_patterns"],
            "redact_patterns": patterns["redact_patterns"],
            "note": ".MCP-ignore auto-generated from LLM assessment. Edit or delete to customize.",
        }

    def _generate_default_mcp_ignore(self, top_dirs: list, top_files: list) -> str:
        """Generate a default .MCP-ignore when LLM is unavailable."""
        lines = ["# Auto-generated default .MCP-ignore"]

        # Smart defaults based on what we see
        skip_dir_map = {
            "node_modules": "node_modules/",
            ".venv": ".venv/",
            "venv": "venv/",
            "__pycache__": "__pycache__/",
            ".git": ".git/",
            ".idea": ".idea/",
            ".vscode": ".vscode/",
            "dist": "dist/",
            "build": "build/",
            ".cache": ".cache/",
            "models": "models/",
            "storage": "storage/",
            "Data": "Data/",
            "chroma_db": "chroma_db/",
            "kuzu_db": "kuzu_db/",
            "user_data": "user_data/",
            "hf_cache": "hf_cache/",
            "huggingface": "huggingface/",
            ".logs": ".logs/",
            "backups": "backups/",
            "archive": "archive/",
        }
        for d in top_dirs:
            if d in skip_dir_map:
                lines.append(f"[skip-dir] {skip_dir_map[d]}")

        # Always add common skip patterns
        lines.extend(
            [
                "[skip-pattern] *.exe",
                "[skip-pattern] *.dll",
                "[skip-pattern] *.so",
                "[skip-pattern] *.png",
                "[skip-pattern] *.jpg",
                "[skip-pattern] *.mp3",
                "[skip-pattern] *.wav",
                "[skip-pattern] *.mp4",
                "[skip-pattern] *.pdf",
                "[skip-pattern] *.zip",
                "[skip-pattern] *.gguf",
                "[skip-pattern] *.safetensors",
                "[redact] .env",
                "[redact] .env.local",
            ]
        )

        return "\n".join(lines)

    def _parse_mcp_ignore(self, mcp_ignore_path: Path) -> dict[str, Any]:
        """Parse a .MCP-ignore file into skip_dirs, skip_patterns, redact_patterns, include_dirs."""
        result = {
            "skip_dirs": set(),
            "skip_patterns": [],
            "redact_patterns": [],
            "include_dirs": set(),
        }

        if not mcp_ignore_path.exists():
            return result

        try:
            with open(mcp_ignore_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if line.startswith("[skip-dir]"):
                        dir_name = line.replace("[skip-dir]", "").strip().rstrip("/")
                        result["skip_dirs"].add(dir_name)
                    elif line.startswith("[skip-pattern]"):
                        pattern = line.replace("[skip-pattern]", "").strip()
                        result["skip_patterns"].append(pattern)
                    elif line.startswith("[redact]"):
                        pattern = line.replace("[redact]", "").strip()
                        result["redact_patterns"].append(pattern)
                    elif line.startswith("[include]"):
                        dir_name = line.replace("[include]", "").strip().rstrip("/")
                        result["include_dirs"].add(dir_name)
        except:
            pass

        return result

    def _should_skip_file(
        self,
        filepath: Path,
        relative_parts: tuple,
        mcp_ignore: dict[str, Any],
        skip_exts: set,
    ) -> tuple:
        """Determine if a file should be skipped, and if it's sensitive.
        Returns (should_skip: bool, is_sensitive: bool, reason: str)"""
        name = filepath.name
        suffix = filepath.suffix.lower()

        # Check if any parent dir is in skip_dirs or .MCP-ignore skip_dirs
        combined_skip_dirs = SKIP_DIRS | mcp_ignore.get("skip_dirs", set())
        for part in relative_parts:
            if part in combined_skip_dirs and part not in mcp_ignore.get(
                "include_dirs", set()
            ):
                return True, False, f"skip-dir: {part}"
            if part.startswith(".") and part not in {
                ".env",
                ".env.local",
                ".env.example",
            }:
                return True, False, f"hidden-dir: {part}"

        # Check binary/media/skip file extensions
        if suffix in skip_exts:
            return True, False, f"skip-ext: {suffix}"

        # Check .MCP-ignore skip patterns (glob-style)
        for pattern in mcp_ignore.get("skip_patterns", []):
            if fnmatch.fnmatch(name, pattern):
                return True, False, f"skip-pattern: {pattern}"

        # Check if this is a sensitive file (.env, etc.) — check BEFORE extension filter
        # because sensitive files like .env have no extension and would be skipped
        if name in SENSITIVE_FILE_PATTERNS or suffix in SENSITIVE_FILE_PATTERNS:
            return False, True, "sensitive"

        # Check .MCP-ignore redact patterns — also before extension filter
        for pattern in mcp_ignore.get("redact_patterns", []):
            if fnmatch.fnmatch(name, pattern):
                return False, True, f"redact: {pattern}"

        # Check if this file's extension is in the allowed set
        if suffix not in INDEX_EXTENSIONS:
            return True, False, f"ext-not-allowed: {suffix}"

        return False, False, ""

    # ─── Active Directory Tracking ──────────────────────────────

    def load_active_dirs(self) -> list:
        """Load active directory tracking."""
        try:
            if ACTIVE_DIRS_PATH.exists():
                with open(ACTIVE_DIRS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return []

    def save_active_dirs(self, dirs: list):
        """Save active directory tracking."""
        try:
            with open(ACTIVE_DIRS_PATH, "w", encoding="utf-8") as f:
                json.dump(dirs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MCP] Error saving active dirs: {e}", file=sys.stderr)

    def track_active_dir(self, directory: str, file_count: int = 0):
        """Add or update an active directory entry."""
        dirs = self.load_active_dirs()
        dir_path = str(Path(directory).resolve())

        found = False
        for entry in dirs:
            if entry.get("path") == dir_path:
                entry["last_indexed"] = datetime.now().isoformat()
                entry["file_count"] = file_count
                entry["index_count"] = entry.get("index_count", 0) + 1
                found = True
                break

        if not found:
            dirs.append(
                {
                    "path": dir_path,
                    "first_indexed": datetime.now().isoformat(),
                    "last_indexed": datetime.now().isoformat(),
                    "file_count": file_count,
                    "index_count": 1,
                    "auto_index": True,
                }
            )

        self.save_active_dirs(dirs)

    # ─── Codebase Indexing ─────────────────────────────────────

    def index_directory(
        self,
        directory: str,
        extensions: set = None,
        max_files: int = 500,
        assess: bool = True,
    ) -> dict[str, Any]:
        """Index a directory for code search with smart filtering.

        Steps:
        1. Check for .MCP-ignore (or auto-generate via LLM assessment)
        2. Skip binary/media/cache dirs and files
        3. Redact sensitive files (.env) — index path only, not content
        4. Track directory as active

        Args:
            directory: Path to directory
            extensions: Custom extensions set (or None for defaults)
            max_files: Maximum files to index
            assess: If True, auto-generate .MCP-ignore if missing
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            return {"error": f"Directory not found: {directory}"}

        # Step 1: Load or generate .MCP-ignore
        mcp_ignore = {
            "skip_dirs": set(),
            "skip_patterns": [],
            "redact_patterns": [],
            "include_dirs": set(),
        }
        mcp_ignore_path = dir_path / MCP_IGNORE_FILENAME
        assessment_info = {}

        if mcp_ignore_path.exists():
            mcp_ignore = self._parse_mcp_ignore(mcp_ignore_path)
            assessment_info = {
                "mcp_ignore": "existing",
                "skip_rules": len(mcp_ignore["skip_dirs"])
                + len(mcp_ignore["skip_patterns"]),
            }
        elif assess:
            # Auto-assess and generate .MCP-ignore
            assessment = self.assess_directory(directory)
            if assessment.get("action") == "generated":
                mcp_ignore = self._parse_mcp_ignore(mcp_ignore_path)
                assessment_info = {
                    "mcp_ignore": "generated",
                    "skip_dirs": len(mcp_ignore["skip_dirs"]),
                    "skip_patterns": len(mcp_ignore["skip_patterns"]),
                }
            else:
                assessment_info = {
                    "mcp_ignore": "failed",
                    "note": assessment.get("error", "unknown"),
                }

        # Step 2: Index with smart filtering
        exts = extensions or INDEX_EXTENSIONS
        indexed = 0
        skipped_dirs = 0
        skipped_files = 0
        skipped_unchanged = 0
        redacted = 0
        errors = 0

        for filepath in dir_path.rglob("*"):
            if indexed >= max_files:
                break

            if not filepath.is_file():
                continue

            try:
                relative_parts = filepath.relative_to(dir_path).parts

                # Smart filter check
                should_skip, is_sensitive, reason = self._should_skip_file(
                    filepath, relative_parts, mcp_ignore, SKIP_FILE_PATTERNS
                )

                if should_skip:
                    if "skip-dir" in reason or "hidden-dir" in reason:
                        skipped_dirs += 1
                    else:
                        skipped_files += 1
                    continue

                # Extension check (in case .MCP-ignore include overrode a skip)
                if filepath.suffix.lower() not in exts and not is_sensitive:
                    continue

                stat = filepath.stat()

                # For sensitive files, use path-only hash
                if is_sensitive:
                    content_hash = hashlib.md5(filepath.name.encode()).hexdigest()[:12]
                    content = "[REDACTED - sensitive file, contents not indexed]"
                    redacted += 1
                else:
                    content_hash = hashlib.md5(filepath.read_bytes()).hexdigest()[:12]

                    # Only re-index if changed
                    key = str(filepath)
                    existing = self.codebase.get(key, {})
                    if existing.get("hash") == content_hash and not is_sensitive:
                        skipped_unchanged += 1
                        continue

                    content = filepath.read_text(encoding="utf-8", errors="replace")[
                        :MAX_CONTENT_PER_FILE
                    ]

                skeleton = ""
                if global_parser and not is_sensitive:
                    try:
                        skeleton = global_parser.parse_file(str(filepath))
                    except Exception as e:
                        print(
                            f"[MCP] Error xrlating via global_parser for {filepath}: {e}",
                            file=sys.stderr,
                        )

                if not skeleton and not is_sensitive:
                    try:
                        ts_script = (
                            Path(__file__).resolve().parent.parent.parent
                            / "Forge"
                            / "scratch"
                            / "TokenSlayer"
                            / "standalone"
                            / "tokenslayer.js"
                        )
                        if ts_script.exists():
                            res = subprocess.run(
                                ["node", str(ts_script), str(filepath), "--level", "3"],
                                capture_output=True,
                                text=True,
                                timeout=10,
                            )
                            if res.returncode == 0:
                                lines = res.stdout.splitlines()
                                filtered = [
                                    l
                                    for l in lines
                                    if l.strip()
                                    and not l.startswith("[TokenSlayer")
                                    and not l.startswith("Auto-activating")
                                ]
                                skeleton = "\n".join(filtered)
                    except Exception as e:
                        print(
                            f"[MCP] Fallback skeletonizer error for {filepath}: {e}",
                            file=sys.stderr,
                        )

                key = str(filepath)
                self.codebase[key] = {
                    "path": str(filepath),
                    "relative": str(filepath.relative_to(dir_path)),
                    "root": directory,
                    "extension": filepath.suffix,
                    "size": stat.st_size,
                    "hash": content_hash,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "content_preview": content[:2000],
                    "content_full": content,
                    "skeleton": skeleton,
                    "sensitive": is_sensitive,
                    "indexed_at": datetime.now().isoformat(),
                }
                indexed += 1
            except Exception:
                errors += 1

        self.save_codebase()

        # Track as active directory
        self.track_active_dir(directory, len(self.codebase))

        return {
            "directory": directory,
            "indexed": indexed,
            "skipped_dirs": skipped_dirs,
            "skipped_files": skipped_files,
            "skipped_unchanged": skipped_unchanged,
            "redacted": redacted,
            "errors": errors,
            "total_indexed_files": len(self.codebase),
            "max_files": max_files,
            "assessment": assessment_info,
        }

    def search_codebase(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        """Search indexed codebase files. Returns preview + location."""
        query_lower = query.lower()
        results = []
        for key, entry in self.codebase.items():
            content = entry.get("content_full", entry.get("content_preview", ""))
            skeleton = entry.get("skeleton", "")
            rel = entry.get("relative", key)
            if (
                query_lower in content.lower()
                or query_lower in rel.lower()
                or query_lower in skeleton.lower()
            ):
                # Find the matching line context
                lines = content.split("\n")
                context_lines = []
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        context_lines.append(
                            {"line": i + 1, "context": "\n".join(lines[start:end])}
                        )
                        if len(context_lines) >= 3:
                            break

                results.append(
                    {
                        "path": entry.get("path", key),
                        "relative": entry.get("relative", rel),
                        "extension": entry.get("extension", ""),
                        "matches": context_lines[:3],
                        "preview": entry.get("content_preview", "")[:500],
                        "skeleton_preview": skeleton[:500] if skeleton else "",
                    }
                )
                if len(results) >= limit:
                    break

        return results

    # ─── Import Operations ─────────────────────────────────────

    def import_doc_file(self, filepath, category="general", tags=None):
        p = Path(filepath)
        if not p.exists():
            return {"error": f"Not found: {filepath}"}
        content, ext = "", p.suffix.lower()
        if ext == ".pdf":
            try:
                import PyPDF2

                with open(p, "rb") as f:
                    content = "\n".join(
                        x.extract_text() or "" for x in PyPDF2.PdfReader(f).pages
                    )
            except Exception as e:
                return {"error": f"PDF: {e}"}
        elif ext in (
            ".txt",
            ".md",
            ".json",
            ".yml",
            ".yaml",
            ".py",
            ".ts",
            ".js",
            ".css",
            ".html",
        ):
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                return {"error": str(e)}
        else:
            return {"error": f"Unsupported: {ext}"}

        source_str = str(p)
        existing_count = len(self.docs)
        self.docs = [d for d in self.docs if d.get("source") != source_str]
        removed = existing_count - len(self.docs)

        chunks, cur = [], ""
        for s in content.split("\n\n") if "\n\n" in content else content.split("\n"):
            if len(cur) + len(s) > 4000 and cur:
                chunks.append(cur.strip())
                cur = s
            else:
                cur = (cur + "\n\n" + s) if cur else s
        if cur.strip():
            chunks.append(cur.strip())
        if not chunks:
            chunks = [content]
        for i, c in enumerate(chunks):
            self.docs.append(
                {
                    "source": source_str,
                    "filename": p.name,
                    "category": category,
                    "tags": tags or [],
                    "chunk": i + 1,
                    "total_chunks": len(chunks),
                    "content": c,
                    "imported_at": datetime.now().isoformat(),
                }
            )
        self.save_docs()
        return {
            "action": "replaced" if removed > 0 else "imported",
            "removed_chunks": removed,
            "imported": p.name,
            "chunks": len(chunks),
            "category": category,
        }

    def search_docs(self, query, category=None, limit=20):
        ql = query.lower()
        results = []
        for e in reversed(self.docs):
            if category and e.get("category") != category:
                continue
            c = e.get("content", "")
            if ql in c.lower() or ql in e.get("filename", "").lower():
                results.append(
                    {
                        "source": e.get("source"),
                        "filename": e.get("filename"),
                        "category": e.get("category"),
                        "tags": e.get("tags", []),
                        "chunk": e.get("chunk"),
                        "snippet": c[:1000],
                    }
                )
                if len(results) >= limit:
                    break
        return results

    def list_docs(self):
        by_cat = {}
        for e in self.docs:
            cat = e.get("category", "general")
            if cat not in by_cat:
                by_cat[cat] = {"files": set(), "chunks": 0}
            by_cat[cat]["files"].add(e.get("source", "?"))
            by_cat[cat]["chunks"] += 1
        return {
            "total_chunks": len(self.docs),
            "categories": {
                k: {"files": len(v["files"]), "chunks": v["chunks"]}
                for k, v in by_cat.items()
            },
        }

    def import_cline_history(self, include_migration: bool = False) -> dict[str, Any]:
        imported = {"total_tasks": 0, "total_messages": 0, "tasks": []}
        if not CLINE_TASKS_PATH.exists():
            return imported

        for task_dir in CLINE_TASKS_PATH.iterdir():
            if not task_dir.is_dir():
                continue
            conv_file = task_dir / "api_conversation_history.json"
            if not conv_file.exists():
                continue
            try:
                with open(conv_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    msg_count = 0
                    for msg in data:
                        role = msg.get("role", "unknown")
                        content_list = msg.get("content", [])
                        text_parts = [
                            item.get("text", "")
                            for item in content_list
                            if isinstance(item, dict) and item.get("type") == "text"
                        ]
                        text_content = "\n".join(text_parts)
                        if text_content and role in ("user", "assistant"):
                            self.conversations.append(
                                {
                                    "role": role,
                                    "content": text_content,
                                    "timestamp": datetime.now().isoformat(),
                                    "source": "cline",
                                    "task_id": task_dir.name,
                                }
                            )
                            msg_count += 1
                    imported["total_tasks"] += 1
                    imported["total_messages"] += msg_count
                    imported["tasks"].append(
                        {"task_id": task_dir.name, "messages": msg_count}
                    )
            except Exception as e:
                print(f"[MCP] Error importing {task_dir}: {e}", file=sys.stderr)

        if include_migration:
            imported["migration"] = self.import_migration_history()
        self.save_memory()
        return imported

    def import_gemini_history(self) -> dict[str, Any]:
        imported = {"total_projects": 0, "total_messages": 0, "projects": []}
        if not GEMINI_HISTORY_PATH.exists():
            return imported

        for project_dir in GEMINI_HISTORY_PATH.iterdir():
            if not project_dir.is_dir():
                continue
            conv_files = list(project_dir.glob("*.json"))
            project_msgs = 0
            for conv_file in conv_files:
                if conv_file.name in (
                    "state.json",
                    "settings.json",
                    "projects.json",
                    "google_accounts.json",
                ):
                    continue
                try:
                    with open(conv_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    messages = (
                        data
                        if isinstance(data, list)
                        else data.get(
                            "messages",
                            data.get("conversation", data.get("history", [])),
                        )
                    )
                    for msg in messages:
                        if isinstance(msg, dict):
                            role = msg.get("role", msg.get("sender", "unknown"))
                            content = msg.get(
                                "content", msg.get("text", msg.get("message", ""))
                            )
                            if content and role in ("user", "assistant", "model"):
                                if role == "model":
                                    role = "assistant"
                                self.conversations.append(
                                    {
                                        "role": role,
                                        "content": str(content),
                                        "timestamp": datetime.now().isoformat(),
                                        "source": "gemini",
                                        "project": project_dir.name,
                                    }
                                )
                                project_msgs += 1
                except:
                    pass
            if project_msgs > 0:
                imported["total_projects"] += 1
                imported["total_messages"] += project_msgs
                imported["projects"].append(
                    {"project": project_dir.name, "messages": project_msgs}
                )
        self.save_memory()
        return imported

    def import_migration_history(self) -> dict[str, Any]:
        imported = {"total_tasks": 0, "total_messages": 0, "tasks": []}
        if not MIGRATION_CLINE_PATH.exists():
            return imported
        for task_dir in MIGRATION_CLINE_PATH.iterdir():
            if not task_dir.is_dir():
                continue
            conv_file = task_dir / "api_conversation_history.json"
            if not conv_file.exists():
                continue
            try:
                with open(conv_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    msg_count = 0
                    for msg in data:
                        role = msg.get("role", "unknown")
                        content_list = msg.get("content", [])
                        text_parts = [
                            item.get("text", "")
                            for item in content_list
                            if isinstance(item, dict) and item.get("type") == "text"
                        ]
                        text_content = "\n".join(text_parts)
                        if text_content and role in ("user", "assistant"):
                            self.conversations.append(
                                {
                                    "role": role,
                                    "content": text_content,
                                    "timestamp": datetime.now().isoformat(),
                                    "source": "migration",
                                    "task_id": task_dir.name,
                                }
                            )
                            msg_count += 1
                    imported["total_tasks"] += 1
                    imported["total_messages"] += msg_count
                    imported["tasks"].append(
                        {"task_id": task_dir.name, "messages": msg_count}
                    )
            except Exception as e:
                print(f"[MCP] Error importing {task_dir}: {e}", file=sys.stderr)
        self.save_memory()
        return imported

    def get_sources_summary(self) -> dict[str, Any]:
        cline_count = sum(1 for c in self.conversations if c.get("source") == "cline")
        gemini_count = sum(1 for c in self.conversations if c.get("source") == "gemini")
        direct_count = sum(1 for c in self.conversations if not c.get("source"))
        return {
            "total_conversations": len(self.conversations),
            "sources": {
                "cline": cline_count,
                "gemini": gemini_count,
                "direct": direct_count,
            },
            "imported_sources": self.sources,
            "codebase_files": len(self.codebase),
            "docs_chunks": len(self.docs),
        }

    # ─── Plan Tracking ──────────────────────────────────────────

    def load_plans(self):
        """Load plans from disk."""
        try:
            if PLANS_INDEX_PATH.exists():
                with open(PLANS_INDEX_PATH, "r", encoding="utf-8") as f:
                    return json.load(f).get("plans", {})
        except Exception as e:
            print(f"[MCP] Error loading plans: {e}", file=sys.stderr)
        return {}

    def save_plans(self, plans: dict):
        """Save plans to disk."""
        try:
            with open(PLANS_INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {"plans": plans, "last_updated": datetime.now().isoformat()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            print(f"[MCP] Error saving plans: {e}", file=sys.stderr)

    def create_plan(
        self, plan_id: str, title: str, description: str, steps: list
    ) -> dict:
        """Create a new multi-step plan.

        Args:
            plan_id: Unique identifier (e.g. 'xrl-protocol')
            title: Human-readable title
            description: Plan overview
            steps: List of step dicts with 'id', 'title', 'description' keys
        """
        plans = self.load_plans()
        if plan_id in plans:
            return {
                "error": f"Plan '{plan_id}' already exists. Use update_plan to modify."
            }

        now = datetime.now().isoformat()
        plan = {
            "id": plan_id,
            "title": title,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "current_step": 0,
            "total_steps": len(steps),
            "status": "in_progress",
            "steps": [],
        }
        for i, step in enumerate(steps):
            plan["steps"].append(
                {
                    "id": step.get("id", f"step-{i + 1}"),
                    "index": i + 1,
                    "title": step.get("title", f"Step {i + 1}"),
                    "description": step.get("description", ""),
                    "status": "pending",
                    "notes": "",
                    "completed_at": None,
                }
            )

        plans[plan_id] = plan
        self.save_plans(plans)
        return {"status": "created", "plan": plan}

    def get_plan(self, plan_id: str) -> dict:
        """Retrieve a plan by ID."""
        plans = self.load_plans()
        plan = plans.get(plan_id)
        if not plan:
            return {
                "error": f"Plan '{plan_id}' not found. Available plans: {list(plans.keys())}"
            }
        return {"plan": plan}

    def list_plans(self) -> dict:
        """List all plans with summary info."""
        plans = self.load_plans()
        summary = {}
        for pid, plan in plans.items():
            completed = sum(
                1 for s in plan.get("steps", []) if s.get("status") == "completed"
            )
            summary[pid] = {
                "title": plan.get("title"),
                "current_step": plan.get("current_step"),
                "total_steps": plan.get("total_steps"),
                "completed_steps": completed,
                "status": plan.get("status"),
                "updated_at": plan.get("updated_at"),
            }
        return {"plans": summary, "total": len(summary)}

    def update_plan_step(
        self, plan_id: str, step_id: str, status: str = None, notes: str = None
    ) -> dict:
        """Update a specific step's status and/or notes.

        Args:
            plan_id: Plan identifier
            step_id: Step identifier
            status: New status ('pending', 'in_progress', 'completed', 'blocked')
            notes: Additional notes for this step
        """
        plans = self.load_plans()
        plan = plans.get(plan_id)
        if not plan:
            return {"error": f"Plan '{plan_id}' not found."}

        step = None
        for s in plan["steps"]:
            if s["id"] == step_id:
                step = s
                break

        if not step:
            return {"error": f"Step '{step_id}' not found in plan '{plan_id}'."}

        if status:
            step["status"] = status
            if status == "completed":
                step["completed_at"] = datetime.now().isoformat()
            elif status == "in_progress":
                plan["current_step"] = step["index"]

        if notes:
            step["notes"] = notes

        # Auto-update plan status
        all_completed = all(s["status"] == "completed" for s in plan["steps"])
        plan["status"] = "completed" if all_completed else "in_progress"
        plan["updated_at"] = datetime.now().isoformat()

        self.save_plans(plans)
        return {"status": "updated", "plan": plan}

    def advance_plan(self, plan_id: str, notes: str = "") -> dict:
        """Mark the current step as completed and advance to the next step."""
        plans = self.load_plans()
        plan = plans.get(plan_id)
        if not plan:
            return {"error": f"Plan '{plan_id}' not found."}

        current_idx = plan["current_step"]
        if current_idx >= len(plan["steps"]):
            return {"error": "All steps already completed.", "plan": plan}

        # Mark current step as completed
        current_step = plan["steps"][current_idx]
        current_step["status"] = "completed"
        current_step["completed_at"] = datetime.now().isoformat()
        if notes:
            current_step["notes"] = notes

        # Advance to next step
        next_idx = current_idx + 1
        if next_idx < len(plan["steps"]):
            plan["current_step"] = next_idx
            plan["steps"][next_idx]["status"] = "in_progress"
            plan["status"] = "in_progress"
        else:
            plan["status"] = "completed"

        plan["updated_at"] = datetime.now().isoformat()
        self.save_plans(plans)
        return {
            "status": "advanced",
            "previous_step": current_step["id"],
            "current_step": plan["steps"][next_idx]["id"]
            if next_idx < len(plan["steps"])
            else None,
            "plan": plan,
        }

    def delete_plan(self, plan_id: str) -> dict:
        """Delete a plan."""
        plans = self.load_plans()
        if plan_id not in plans:
            return {"error": f"Plan '{plan_id}' not found."}
        del plans[plan_id]
        self.save_plans(plans)
        return {"status": "deleted", "plan_id": plan_id}


# ═══════════════════════════════════════════════════════════════
# MCP Tool Definitions
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    # ─── Memory ─────────────────────────────────────────────
    {
        "name": "get_memory",
        "description": "Retrieve conversation history from FoveAI memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Number of recent entries to retrieve",
                }
            },
        },
    },
    {
        "name": "add_memory",
        "description": "Add a conversation turn to FoveAI memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "enum": ["user", "assistant", "system"],
                    "description": "Who said this",
                },
                "content": {"type": "string", "description": "The message content"},
                "metadata": {"type": "object", "description": "Optional metadata"},
            },
            "required": ["role", "content"],
        },
    },
    {
        "name": "search_memory",
        "description": "Search conversation history for keywords",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Max results",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_session_context",
        "description": "Get prompt injection for new session context",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ─── Import ──────────────────────────────────────────────
    {
        "name": "import_history",
        "description": "Import conversation history from Cline and Gemini folders",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["cline", "gemini", "all"],
                    "default": "all",
                }
            },
        },
    },
    {
        "name": "get_sources",
        "description": "Get summary of imported sources and conversation counts",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "import_doc",
        "description": "Import a documentation file into the knowledge base (txt, md, json, py, ts, js, css, html, pdf)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to file"},
                "category": {
                    "type": "string",
                    "default": "general",
                    "description": "coding, ui, troubleshooting, languages, books",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "search_docs",
        "description": "Search documentation knowledge base",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_docs",
        "description": "List imported documentation by category",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ─── Codebase Indexing ───────────────────────────────────
    {
        "name": "index_directory",
        "description": "Index a directory's source files for code search. Auto-generates .MCP-ignore if missing (uses LLM to assess directory structure). Skips binary/media/cache dirs, redacts .env files. Tracks directory as active.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Path to directory to index",
                },
                "max_files": {
                    "type": "integer",
                    "default": 500,
                    "description": "Max files to index",
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to include (e.g. ['.py','.js']). Default: common code files",
                },
            },
            "required": ["directory"],
        },
    },
    {
        "name": "assess_directory",
        "description": "Smart directory assessment: scans directory structure, uses local LLM to generate a .MCP-ignore file that tells index_directory what to skip/redact. Delete .MCP-ignore to force re-assessment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Path to directory to assess",
                }
            },
            "required": ["directory"],
        },
    },
    {
        "name": "search_codebase",
        "description": "Search indexed codebase files for code, functions, classes, patterns. Use index_directory first to build the index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (function name, class, pattern)",
                },
                "limit": {"type": "integer", "default": 15},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_indexed",
        "description": "List all indexed directories and file counts",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ─── Local LLM Middleman ─────────────────────────────────
    {
        "name": "summarize_context",
        "description": "Summarize long text using the deterministic extractive compressor (optional LLM path via LOCAL_LLM_BASE). Use this to compress conversation context, file contents, or search results before sending to the main model. Saves tokens on limited-context-window models.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to summarize"},
                "focus": {
                    "type": "string",
                    "default": "key facts, decisions, code changes, and current task state",
                    "description": "What to focus the summary on",
                },
                "max_length": {
                    "type": "integer",
                    "default": 500,
                    "description": "Target max length of summary in words",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "compress_search_results",
        "description": "Search memory/docs/codebase and return a local-LLM-compressed summary instead of raw results. Much more token-efficient than search_memory or search_docs for large result sets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "source": {
                    "type": "string",
                    "enum": ["memory", "docs", "codebase", "all"],
                    "default": "all",
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_local_llm",
        "description": "Report compressor status. The deterministic extractor is always available; if LOCAL_LLM_BASE is set, also probes that endpoint.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "start_middleman",
        "description": "No-op kept for compatibility — the deterministic compressor needs no service. If LOCAL_LLM_BASE is set, re-probes that endpoint.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ─── XRL Structural Cache (xrlated skeletons) ────────────────────
    {
        "name": "analyze_files",
        "description": "Extract compact XRL structures (signatures, types, exports — no bodies) at a fraction of the token cost of reading files raw. After locating a symbol, use expand_node to read its body.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filePaths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of absolute file paths to analyze.",
                }
            },
            "required": ["filePaths"],
        },
    },
    {
        "name": "expand_node",
        "description": "Expand a pruned AST node to reveal its full source code. Use this when an xrlated structure contains a /* EXPAND:nodeId */ tag and you need to see the implementation details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "nodeId": {
                    "type": "string",
                    "description": "The node ID from a /* EXPAND:nodeId */ tag.",
                }
            },
            "required": ["nodeId"],
        },
    },
    # ─── Plan Tracking ──────────────────────────────────────────
    {
        "name": "create_plan",
        "description": "Create a new multi-step project plan with structured steps. Persists across sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Unique identifier (e.g. 'xrl-protocol')",
                },
                "title": {"type": "string", "description": "Human-readable plan title"},
                "description": {"type": "string", "description": "Plan overview"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Step identifier (e.g. 'phase-1')",
                            },
                            "title": {"type": "string", "description": "Step title"},
                            "description": {
                                "type": "string",
                                "description": "Step description",
                            },
                        },
                        "required": ["id", "title"],
                    },
                    "description": "Ordered list of steps",
                },
            },
            "required": ["plan_id", "title", "steps"],
        },
    },
    {
        "name": "get_plan",
        "description": "Retrieve a plan by ID with full step details and status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan identifier"}
            },
            "required": ["plan_id"],
        },
    },
    {
        "name": "list_plans",
        "description": "List all plans with summary info (title, progress, status).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_plan_step",
        "description": "Update a specific step's status and/or notes. Status values: pending, in_progress, completed, blocked.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan identifier"},
                "step_id": {"type": "string", "description": "Step identifier"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "blocked"],
                    "description": "New status",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes for this step",
                },
            },
            "required": ["plan_id", "step_id"],
        },
    },
    {
        "name": "advance_plan",
        "description": "Mark the current step as completed and advance to the next step. Auto-updates plan status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan identifier"},
                "notes": {
                    "type": "string",
                    "description": "Completion notes for the current step",
                },
            },
            "required": ["plan_id"],
        },
    },
    {
        "name": "delete_plan",
        "description": "Delete a plan by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan identifier"}
            },
            "required": ["plan_id"],
        },
    },
]


# ═══════════════════════════════════════════════════════════════
# Coder tool surface — heavy-duty repo tools from Backend/Cognition.
# OpenAI-format schemas are converted to MCP inputSchema shape.
# ═══════════════════════════════════════════════════════════════
_COGNITION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Cognition"
)
if _COGNITION_DIR not in sys.path:
    sys.path.insert(0, _COGNITION_DIR)

try:
    from coder_tools import (
        TOOL_FUNCS as CODER_TOOL_FUNCS,
    )
    from coder_tools import (
        TOOL_SCHEMAS as _CODER_SCHEMAS,
    )

    TOOLS += [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "inputSchema": t["function"]["parameters"],
        }
        for t in _CODER_SCHEMAS
    ]
except Exception as _e:
    print(f"[MCP] coder tools unavailable: {_e}", file=sys.stderr)
    CODER_TOOL_FUNCS = {}


# ═══════════════════════════════════════════════════════════════
# Tool Handler
# ═══════════════════════════════════════════════════════════════


async def handle_tool(name: str, arguments: dict, server: MemoryServer):
    """Handle MCP tool calls."""

    # ─── Memory ─────────────────────────────────────────────
    if name == "get_memory":
        limit = arguments.get("limit", 20)
        return {"conversations": server.get_recent_context(limit)}

    elif name == "add_memory":
        role = arguments.get("role")
        content = arguments.get("content")
        metadata = arguments.get("metadata", {})
        count_before = len(server.conversations)
        total = await server.add_conversation(role, content, metadata)
        is_new = len(server.conversations) > count_before
        return {
            "status": "added" if is_new else "updated",
            "total": total,
            "dedup": not is_new,
        }

    elif name == "search_memory":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 20)
        results = server.search(query, limit)
        return {"results": results, "total_matches": len(results), "query": query}

    elif name == "get_session_context":
        return {"injection_prompt": server.get_injection_prompt()}

    # ─── Import ──────────────────────────────────────────────
    elif name == "import_history":
        source = arguments.get("source", "all")
        result = {"imported": {}}
        if source in ("cline", "all"):
            result["imported"]["cline"] = server.import_cline_history(
                include_migration=True
            )
        if source in ("gemini", "all"):
            result["imported"]["gemini"] = server.import_gemini_history()
        server.sources["last_import"] = datetime.now().isoformat()
        server.sources.update(result["imported"])
        server.save_sources()
        return result

    elif name == "get_sources":
        return server.get_sources_summary()

    elif name == "import_doc":
        return server.import_doc_file(
            arguments.get("filepath", ""),
            category=arguments.get("category", "general"),
            tags=arguments.get("tags", []),
        )

    elif name == "search_docs":
        return {
            "results": server.search_docs(
                arguments.get("query", ""),
                category=arguments.get("category"),
                limit=arguments.get("limit", 20),
            )
        }

    elif name == "list_docs":
        return server.list_docs()

    # ─── Codebase Indexing ───────────────────────────────────
    elif name == "index_directory":
        directory = arguments.get("directory", "")
        max_files = arguments.get("max_files", 500)
        exts = arguments.get("extensions")
        ext_set = set(exts) if exts else None
        return server.index_directory(
            directory, extensions=ext_set, max_files=max_files
        )

    elif name == "assess_directory":
        directory = arguments.get("directory", "")
        return server.assess_directory(directory)

    elif name == "search_codebase":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 15)
        return {
            "results": server.search_codebase(query, limit),
            "total_indexed": len(server.codebase),
        }

    elif name == "list_indexed":
        roots = {}
        for key, entry in server.codebase.items():
            root = entry.get("root", "unknown")
            if root not in roots:
                roots[root] = {"files": 0, "extensions": set()}
            roots[root]["files"] += 1
            roots[root]["extensions"].add(entry.get("extension", "?"))
        return {
            "total_files": len(server.codebase),
            "directories": {
                k: {"files": v["files"], "extensions": sorted(v["extensions"])}
                for k, v in roots.items()
            },
        }

    # ─── Local LLM Middleman ─────────────────────────────────
    elif name == "summarize_context":
        text = arguments.get("text", "")
        focus = arguments.get(
            "focus", "key facts, decisions, code changes, and current task state"
        )
        max_length = arguments.get("max_length", 500)
        if not text:
            return {"error": "No text provided"}
        return compressor.summarize(text, focus=focus, max_words=max_length)

    elif name == "compress_search_results":
        query = arguments.get("query", "")
        source = arguments.get("source", "all")
        limit = arguments.get("limit", 10)

        # Gather raw results from all sources
        raw_results = []
        if source in ("memory", "all"):
            raw_results.extend(server.search(query, limit))
        if source in ("docs", "all"):
            raw_results.extend(server.search_docs(query, limit=limit))
        if source in ("codebase", "all"):
            raw_results.extend(server.search_codebase(query, limit=limit))

        if not raw_results:
            return {
                "summary": f"No results found for '{query}'.",
                "raw_count": 0,
                "method": "none",
            }

        # Combine all result text for compression
        combined = "\n---\n".join(
            r.get("content", r.get("snippet", r.get("preview", str(r))))[:2000]
            for r in raw_results[:10]
        )

        # Compress via deterministic extraction (or configured LLM endpoint)
        result = compressor.summarize(
            combined,
            focus=f"information about: {query}. Keep code references, file paths, and key decisions.",
            max_words=300,
        )
        result["raw_count"] = len(raw_results)
        result["query"] = query
        return result

    elif name == "check_local_llm":
        return compressor.check_available()

    elif name == "start_middleman":
        return compressor.auto_start()

    elif name == "analyze_files":
        paths = arguments.get("filePaths", [])
        if not global_parser:
            return {
                "error": "skeleton_parser module could not be loaded. Ensure Forge directory is in path."
            }

        results = []
        for path in paths:
            skeleton = global_parser.parse_file(path)
            results.append(f"--- File: {path} ---\n{skeleton}")

        return {"content": "\n\n".join(results)}

    elif name == "expand_node":
        node_id = arguments.get("nodeId", "")
        if not global_parser:
            return {"error": "skeleton_parser module could not be loaded."}

        content = global_parser.expand_node(node_id)
        return {"content": content}

    elif name == "create_plan":
        plan_id = arguments.get("plan_id")
        title = arguments.get("title")
        description = arguments.get("description", "")
        steps = arguments.get("steps", [])
        return server.create_plan(plan_id, title, description, steps)

    elif name == "get_plan":
        plan_id = arguments.get("plan_id")
        return server.get_plan(plan_id)

    elif name == "list_plans":
        return server.list_plans()

    elif name == "update_plan_step":
        plan_id = arguments.get("plan_id")
        step_id = arguments.get("step_id")
        status = arguments.get("status")
        notes = arguments.get("notes")
        return server.update_plan_step(plan_id, step_id, status, notes)

    elif name == "advance_plan":
        plan_id = arguments.get("plan_id")
        notes = arguments.get("notes", "")
        return server.advance_plan(plan_id, notes)

    elif name == "delete_plan":
        plan_id = arguments.get("plan_id")
        return server.delete_plan(plan_id)

    # ─── Coder tools (heavy-duty repo surface, .foveignore-layered) ──────
    elif name in CODER_TOOL_FUNCS:
        try:
            return CODER_TOOL_FUNCS[name](**arguments)
        except Exception as e:
            return {"error": f"coder tool {name} failed: {e}"}

    else:
        return {"error": f"Unknown tool: {name}"}


# ═══════════════════════════════════════════════════════════════
# MCP Server (stdio transport)
# ═══════════════════════════════════════════════════════════════


async def run_mcp_server():
    """Run MCP server using stdio transport."""
    server = MemoryServer()

    # Auto-probe the optional LLM endpoint if one is configured
    if LOCAL_LLM_AUTO_START and compressor.base_url:
        status = compressor.check_available()
        print(f"[MCP] Middleman status: {status.get('status')}", file=sys.stderr)
    # MCP server listens on stdio for JSON-RPC 2.0 requests
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )
            if not line:
                break

            message = json.loads(line.strip())

            if message.get("method") == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {"tools": TOOLS},
                }
                print(json.dumps(response), flush=True)

            elif message.get("method") == "tools/call":
                tool_name = message.get("params", {}).get("name")
                arguments = message.get("params", {}).get("arguments", {})
                result = await handle_tool(tool_name, arguments, server)
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    result, indent=2, ensure_ascii=False
                                ),
                            }
                        ]
                    },
                }
                print(json.dumps(response), flush=True)

            elif message.get("method") == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "foveai-memory", "version": "3.0.0"},
                    },
                }
                print(json.dumps(response), flush=True)
                print(
                    json.dumps(
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}
                    ),
                    flush=True,
                )

        except Exception as e:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32000, "message": str(e)},
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(run_mcp_server())
