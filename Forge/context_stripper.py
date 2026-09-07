"""
Context Stripper — Tiered noise-removal for Cline message history.

Removes deterministic noise (thinking blocks, duplicate reads, system
prompt repeats) via fast regex. No LLM needed — runs in microseconds.

Tier 1 rules (regex, instant):
  1. Strip <thinking>...</thinking> → [thought]
  2. Deduplicate repeated file reads (same path+range within window)
  3. Strip repeated system prompt after first occurrence
  4. Truncate bloated tool results for known large files
  5. Collapse repeated identical tool errors

Tier 2: Always preserve (never touched):
  - Last N full turns (preserves working memory)
  - File paths, diffs, error messages
  - Tool call names and arguments
  - User instructions

Tier 3 (checkpoint): Accepts assistant-generated summary that replaces
older history with a compact progress block + last few raw turns.
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple, Set

# ── Constants ───────────────────────────────────────────────────────

LARGE_FILES = {
    "xr_app.py", "compagent.py", "MindCore.py", "cloud_repertoire.py",
    "main.ts", "Dashboard.ts", "AgencyTab.ts", "AvatarManager.ts",
    "VideoChat.ts", "ContextManager.ts",
}

CHARS_PER_TOKEN = 4

_tiktoken_encoder = None
_tiktoken_failed = False


# ── Helpers ─────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Accurate token estimate using tiktoken if available, falling back to char // 4."""
    global _tiktoken_encoder, _tiktoken_failed
    if not _tiktoken_failed and _tiktoken_encoder is None:
        try:
            import tiktoken
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_failed = True

    if _tiktoken_encoder is not None:
        try:
            return len(_tiktoken_encoder.encode(text, disallowed_special=()))
        except Exception:
            pass

    return max(1, len(text) // CHARS_PER_TOKEN)


def extract_file_path(text: str) -> Optional[str]:
    """Extract a file path from tool result or message content."""
    m = re.search(
        r'([A-Za-z]:[\\/][^\s,"\']+|[a-zA-Z0-9_/.-]+\.(?:py|ts|js|json|md|xml|kt|html|css))',
        text
    )
    return m.group(1) if m else None


def extract_line_range(text: str) -> Optional[Tuple[int, int]]:
    """Extract start_line/end_line from a read_files or editor result."""
    m = re.search(r'start_line[:\s=]+(\d+).*?end_line[:\s=]+(\d+)', text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m2 = re.search(r'[Ll]ines?\s+(\d+)\s*[-–to]+\s*(\d+)', text)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)))
    return None


def strip_thinking(content: str) -> str:
    """Remove <thinking> blocks, replace with brief marker."""
    pattern = re.compile(r'<thinking>.*?</thinking>', re.DOTALL)
    if pattern.search(content):
        return pattern.sub('[thought]', content).strip()
    return content


# ── ContextStripper Class ───────────────────────────────────────────

class ContextStripper:
    """Applies Tier 1 & 2 rules to message arrays."""

    def __init__(
        self,
        preserve_last: int = 5,
        large_files=None,
        max_system_prompt_repeats: int = 1,
    ):
        self.preserve_last = preserve_last
        self.large_files = large_files or LARGE_FILES
        self.max_system_prompt_repeats = max_system_prompt_repeats
        self._seen_file_ranges: set = set()
        self._system_prompt_count: int = 0
        self._checkpoint_active: bool = False
        self._checkpoint_summary = None
        self._stats = {
            "thinking_stripped": 0,
            "reads_deduped": 0,
            "system_prompts_stripped": 0,
            "checkpoints_applied": 0,
            "tokens_before": 0,
            "tokens_after": 0,
        }

    def strip_messages(self, messages):
        """Apply all Tier 1 stripping rules to a message array."""
        # CRITICAL: Reset per-call state to prevent cross-call leakage.
        # Without this, _system_prompt_count and _seen_file_ranges accumulate
        # across calls, causing system prompts and file re-reads to be silently
        # dropped on every invocation after the first.
        self._system_prompt_count = 0
        self._seen_file_ranges = set()

        # 1. Background node extraction & context recycling
        self._extract_and_recycle_background(messages)
        
        # 2. Prune verified turns (context recycling pruning)
        # DISABLED by default — replacing real conversation turns with
        # "[recycled context node]" placeholders destroys crucial context
        # (user instructions, error details, file references) while leaving
        # token count high, causing models to lose direction.
        if os.environ.get("FoveAI_ENABLE_TURN_PRUNING", "0") == "1":
            messages = self._prune_verified_turns(messages)

        total_before = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        if self._checkpoint_active and self._checkpoint_summary:
            messages = self._apply_checkpoint(messages)
        total_msgs = len(messages)
        preserve_from = max(0, total_msgs - self.preserve_last)

        stripped = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Always preserve last N messages untouched
            if i >= preserve_from:
                stripped.append(msg)
                continue

            # System prompt dedup
            if role == "system":
                self._system_prompt_count += 1
                if self._system_prompt_count > self.max_system_prompt_repeats:
                    self._stats["system_prompts_stripped"] += 1
                    continue

            if not content or not str(content).strip():
                continue

            content_str = str(content)

            # Strip thinking blocks
            if role == "assistant" and "<thinking>" in content_str.lower():
                content_str = strip_thinking(content_str)
                self._stats["thinking_stripped"] += 1

            # Dedup large file reads in tool results
            if role == "user":
                fp = extract_file_path(content_str)
                if fp and any(lf in fp for lf in self.large_files):
                    lr = extract_line_range(content_str)
                    if lr:
                        rk = f"{fp}:{lr[0]}:{lr[1]}"
                        if rk in self._seen_file_ranges:
                            self._stats["reads_deduped"] += 1
                            nm = dict(msg)
                            nm["content"] = f"[re-read] {fp}:{lr[0]}-{lr[1]} - already seen, skipped"
                            stripped.append(nm)
                            continue
                        self._seen_file_ranges.add(rk)

            nm = dict(msg)
            nm["content"] = content_str
            stripped.append(nm)

        # Inject checkpoint system message if active
        if self._checkpoint_active and self._checkpoint_summary:
            ckpt_msg = {
                "role": "system",
                "content": (
                    f"[CONTEXT CHECKPOINT] Prior conversation summarized. "
                    f"Last {self.preserve_last} turns preserved.\n\n"
                    f"{self._checkpoint_summary}"
                ),
            }
            at = 1 if (stripped and stripped[0].get("role") == "system") else 0
            stripped.insert(at, ckpt_msg)

        # Inject [SKELETAL CONTEXT INDEX]
        try:
            import skeletal_memory
            skeletal_index = skeletal_memory.build_skeletal_index()
            if skeletal_index:
                idx_msg = {
                    "role": "system",
                    "content": skeletal_index
                }
                at = 1 if (stripped and stripped[0].get("role") == "system") else 0
                stripped.insert(at, idx_msg)
        except Exception:
            pass

        total_after = sum(estimate_tokens(str(m.get("content", ""))) for m in stripped)
        self._stats["tokens_before"] += total_before
        self._stats["tokens_after"] += total_after
        return stripped

    def apply_checkpoint(self, summary: str) -> None:
        self._checkpoint_active = True
        self._checkpoint_summary = summary
        self._stats["checkpoints_applied"] += 1

    def clear_checkpoint(self) -> None:
        self._checkpoint_active = False
        self._checkpoint_summary = None

    def get_stats(self):
        saved = self._stats["tokens_before"] - self._stats["tokens_after"]
        ratio = (1 - self._stats["tokens_after"] / max(1, self._stats["tokens_before"])) * 100 if self._stats["tokens_before"] > 0 else 0
        return {**self._stats, "tokens_saved": saved, "compression_pct": round(ratio, 1), "checkpoint_active": self._checkpoint_active}

    def _score_turn_value(self, msg: Dict[str, Any]) -> int:
        """Scores a message for its semantic retention value."""
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        score = 0
        
        # 1. Always keep system prompts
        if role == "system":
            return 1000
            
        # 2. Check for explicit preserve markers
        if any(marker in content for marker in ["[KEEP]", "[PRESERVE]", "[IMPORTANT]"]):
            return 1000
            
        # 3. Detect categories
        has_file_ref = bool(re.search(r'([A-Za-z]:[\\/][^\s,"\']+|[a-zA-Z0-9_/.-]+\.(?:py|ts|js|json|md|xml|kt|html|css))', content))
        has_code_edit = "```" in content or "<edit_file>" in content
        has_error = any(err in content.lower() for err in ["traceback", "error", "exception", "failed", "stderr:"])
        
        # 4. Check if user role is actually a tool output
        is_tool_response = False
        if role == "user":
            tool_patterns = [
                r"Path .*? is protected",
                r"Tool Output:",
                r"Command .*? executed",
                r"\[read_file\]",
                r"\[write_file\]",
                r"\[grep_search\]",
                r"\[run_command\]",
                r"STDOUT:",
                r"STDERR:",
                r"failed to get URL",
                r"Encountered error in step execution"
            ]
            for pat in tool_patterns:
                if re.search(pat, content):
                    is_tool_response = True
                    break
                    
        # 5. Score based on role and classification
        if is_tool_response:
            # Tool responses: only preserve if they are errors/failures
            if has_error:
                score += 60
        else:
            if has_file_ref:
                score += 50
            if has_code_edit:
                score += 40
            if has_error:
                score += 60
            if role == "user":
                # Direct user input prompt
                score += 200
                
        return score

    def _apply_checkpoint(self, messages):
        if not messages:
            return messages
        pc = min(self.preserve_last, len(messages))
        preserved = messages[-pc:] if pc > 0 else []
        
        # Extract exceptions from the discarded history via semantic scoring
        discarded = messages[:-pc] if pc > 0 else messages
        
        # Score and preserve high-value messages, keeping chronological order
        scored_discarded = [(self._score_turn_value(msg), i, msg) for i, msg in enumerate(discarded)]
        exceptions = [msg for score, i, msg in scored_discarded if score >= 50]
                
        ckpt = {
            "role": "user",
            "content": (
                f"[CONVERSATION CHECKPOINT] History before last {pc} "
                f"messages summarized:\n\n{self._checkpoint_summary}"
            ),
        }
        
        # Merge system and direct user exceptions before the checkpoint, then the last turns
        return exceptions + [ckpt] + preserved

    def _extract_and_recycle_background(self, messages):
        """Asynchronously extract and recycle nodes from new turns in the background.

        RATE-LIMITED: Only processes at most 1 new turn per call to prevent
        cascading LLM calls that cause OOM.
        """
        import asyncio
        import hashlib
        import time
        try:
            import skeletal_memory
        except ImportError:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            import skeletal_memory

        if not hasattr(self, "_processed_turn_hashes"):
            self._processed_turn_hashes = set()
        if not hasattr(self, "_last_bg_extract_time"):
            self._last_bg_extract_time = 0.0

        # Rate limit: only process once every 30 seconds
        now = time.time()
        if now - self._last_bg_extract_time < 30.0:
            return None
        self._last_bg_extract_time = now

        # Only process the FIRST unprocessed turn to avoid OOM cascade
        for idx in range(len(messages) - 1):
            m1 = messages[idx]
            m2 = messages[idx + 1]
            if m1.get("role") == "user" and m2.get("role") == "assistant":
                u_text = str(m1.get("content", "")).strip()
                a_text = str(m2.get("content", "")).strip()
                if u_text and a_text and "[re-read]" not in u_text and "[recycled" not in u_text:
                    turn_id = f"user: {u_text}\nassistant: {a_text}"
                    turn_hash = hashlib.sha256(turn_id.encode("utf-8")).hexdigest()
                    if turn_hash not in self._processed_turn_hashes:
                        # Only process this single turn
                        async def process_single_turn():
                            try:
                                nodes = await skeletal_memory.extract_nodes_from_turn(turn_id)
                                if nodes:
                                    skeletal_memory.consolidate_nodes(nodes, turn_id)
                                self._processed_turn_hashes.add(turn_hash)
                            except Exception:
                                pass

                        try:
                            loop = asyncio.get_running_loop()
                            return loop.create_task(process_single_turn())
                        except RuntimeError:
                            pass
                        break  # only process one turn per call

        return None

    def _prune_verified_turns(self, messages):
        """Replace raw text of double-verified turns with placeholders to recycle context."""
        try:
            import skeletal_memory
        except ImportError:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            import skeletal_memory

        total_msgs = len(messages)
        preserve_from = max(0, total_msgs - self.preserve_last)

        pruned_messages = []
        skip_next = False
        for idx in range(total_msgs):
            if skip_next:
                skip_next = False
                continue

            msg = messages[idx]
            role = msg.get("role")

            if (role == "user" and 
                idx < total_msgs - 1 and 
                messages[idx+1].get("role") == "assistant" and
                idx < preserve_from):
                
                u_text = str(msg.get("content", "")).strip()
                a_text = str(messages[idx+1].get("content", "")).strip()
                turn_text = f"user: {u_text}\nassistant: {a_text}"

                if skeletal_memory.should_prune_turn(turn_text):
                    pm_user = dict(msg)
                    pm_user["content"] = "[recycled context node]"
                    pm_assistant = dict(messages[idx+1])
                    pm_assistant["content"] = "[recycled details]"

                    pruned_messages.append(pm_user)
                    pruned_messages.append(pm_assistant)
                    skip_next = True
                    continue

            pruned_messages.append(msg)

        return pruned_messages
