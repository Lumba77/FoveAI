"""
Context Crystallizer — Tiered temporal compression for coding sessions.

Three compression levels, applied on a sliding scale based on recency:
  RECENT (last ~5 turns)  — 30% compression: preserve original wording, light trim
  MIDDLE (~5-20 turns)    — 60% compression: condense but keep key details and style
  OLD    (20+ turns)      — 90% compression: principles only, dense bullet points

The result is a single checkpoint that reads naturally: recent context flows
smoothly into condensed middle, which tapers into terse old-context bullets.

Importable by proxy_server_v2.py for auto-checkpoint. Also usable standalone via CLI.

USAGE:
  # Standalone CLI
  python Forge/context_crystallizer.py session_transcript.txt
  cat conversation.txt | python Forge/context_crystallizer.py

  # Imported by proxy
  from context_crystallizer import crystallize_messages, format_crystal

ENV VARS:
  FoveAI_LOCAL_BASE_URL  — local LLM endpoint (default http://localhost:8888/v1)
  FoveAI_MODEL_LOCAL_ID     — model to use
  FoveAI_UNSLOTH_API_KEY — API key for Unsloth (if required)
  FoveAI_CRYSTAL_RECENT_TURNS — turns to treat as recent (default 5)
  FoveAI_CRYSTAL_MIDDLE_TURNS — turns to treat as middle (default 15, i.e. turns 6-20)
"""

import json
import os
import sys
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Load .env from repo root
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.isfile(_env_path):
    try:
        import dotenv
        dotenv.load_dotenv(_env_path, override=False)
    except ImportError:
        pass

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("crystallizer")

# ── Config ────────────────────────────────────────────────────────────

LOCAL_BASE = os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1").rstrip("/")
LOCAL_MODEL = os.getenv("FoveAI_MODEL_LOCAL_ID", "unsloth/Qwen3.5-4B-MTP-GGUF").strip()
LOCAL_KEY = os.getenv("FoveAI_UNSLOTH_API_KEY", "").strip()

RECENT_TURNS = int(os.getenv("FoveAI_CRYSTAL_RECENT_TURNS", "5"))
MIDDLE_TURNS = int(os.getenv("FoveAI_CRYSTAL_MIDDLE_TURNS", "15"))

# ── Prompts ───────────────────────────────────────────────────────────

# Tier 1: RECENT — 30% compression, preserve wording
RECENT_SYSTEM = """You are a light editor. Your job is to lightly trim a recent conversation segment
while preserving the original wording, tone, and style as much as possible.

RULES:
- Keep the original speaker labels (user:/assistant:).
- Remove only truly redundant content: repeated greetings, "ok", "thanks", empty acknowledgments.
- Preserve ALL technical details, file paths, code references, error messages, and decisions.
- Preserve the original phrasing — do not paraphrase or summarize.
- If a message is already concise, leave it untouched.
- Output ONLY the trimmed transcript. No commentary, no markdown, no JSON."""

RECENT_USER = """Lightly trim this RECENT conversation segment. Preserve original wording and all technical details.

RECENT SEGMENT:
{segment}"""

# Tier 2: MIDDLE — 60% compression, condense but keep style
MIDDLE_SYSTEM = """You are a context condenser. Your job is to compress a middle portion of a coding
session conversation while preserving the key details and general style.

RULES:
- Condense each exchange into 1-2 lines while keeping the speaker labels (user:/assistant:).
- Preserve: what was asked, what was tried, what was decided, file paths, error types.
- Drop: verbose explanations, repeated content, tool output dumps, thinking blocks.
- Keep the conversational flow — it should still read like a dialogue, just denser.
- Output ONLY the condensed transcript. No commentary, no markdown, no JSON."""

MIDDLE_USER = """Condense this MIDDLE conversation segment. Keep key details and conversational flow.

MIDDLE SEGMENT:
{segment}"""

# Tier 3: OLD — 90% compression, principles only
OLD_SYSTEM = """You are a context distiller. Your job is to extract only the essential principles
from an old portion of a coding session conversation.

RULES:
- Output a bullet list of principles/facts only. No narrative, no dialogue format.
- Each bullet: one key fact, decision, or discovery from this segment.
- Format: "• fact or decision"
- Include: problems identified, solutions attempted (with result ✓/✗/~), files changed, decisions made.
- Exclude: greetings, process chatter, tool output, thinking, repeated content.
- Max 15 bullets. If there's less content, fewer bullets is fine.
- Output ONLY the bullet list. No commentary, no markdown headers, no JSON."""

OLD_USER = """Distill this OLD conversation segment into a bullet list of key principles and facts.

OLD SEGMENT:
{segment}"""

# ── Helpers ────────────────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    return max(1, len(str(text)) // 4)


def _count_turns(messages: List[Dict]) -> int:
    """Count user/assistant turn pairs in a message array."""
    turns = 0
    for i in range(len(messages) - 1):
        m1 = messages[i]
        m2 = messages[i + 1]
        if m1.get("role") == "user" and m2.get("role") == "assistant":
            turns += 1
    return turns


def _split_messages_by_recency(
    messages: List[Dict],
    recent_turns: int = None,
    middle_turns: int = None,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Split message array into recent, middle, and old segments by turn count.

    Returns (recent_messages, middle_messages, old_messages).
    Recent = last N turns, Middle = next M turns before that, Old = everything else.
    """
    recent_n = recent_turns or RECENT_TURNS
    middle_n = middle_turns or MIDDLE_TURNS

    # Walk backwards counting turn pairs
    total = len(messages)
    turn_boundaries = []  # indices where turn pairs start (user message index)

    for i in range(total - 1):
        m1 = messages[i]
        m2 = messages[i + 1]
        if m1.get("role") == "user" and m2.get("role") == "assistant":
            turn_boundaries.append(i)

    if not turn_boundaries:
        # No clear turns — treat all as recent
        return messages, [], []

    # Recent: last `recent_n` turns
    recent_start_idx = 0
    if len(turn_boundaries) >= recent_n:
        recent_start_idx = turn_boundaries[-recent_n]

    # Middle: the `middle_n` turns before recent
    middle_start_idx = 0
    remaining = turn_boundaries[:-recent_n] if len(turn_boundaries) > recent_n else []
    if len(remaining) >= middle_n:
        middle_start_idx = remaining[-middle_n]
    elif remaining:
        middle_start_idx = remaining[0]

    recent = messages[recent_start_idx:]
    middle = messages[middle_start_idx:recent_start_idx] if middle_start_idx < recent_start_idx else []
    old = messages[:middle_start_idx] if middle_start_idx > 0 else []

    return recent, middle, old


def _messages_to_text(messages: List[Dict], max_content_len: int = 500) -> str:
    """Convert message array to compact text, preserving role labels."""
    lines = []
    for msg in messages:
        role = msg.get("role", "?")
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if role == "system":
            if not lines:
                lines.append(f"system: {content[:200]}")
            continue
        if len(content) > max_content_len:
            content = content[:max_content_len] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 512) -> Optional[str]:
    """Call local LLM and return response text, or None on failure."""
    import httpx

    # Quick health check first — fail fast if LLM isn't running
    try:
        hc = httpx.get(f"{LOCAL_BASE}/models", timeout=2.0)
    except Exception:
        logger.warning(f"Local LLM at {LOCAL_BASE} not available — skipping LLM call")
        return None

    headers = {"Content-Type": "application/json"}
    if LOCAL_KEY:
        headers["Authorization"] = f"Bearer {LOCAL_KEY}"

    payload = {
        "model": LOCAL_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        resp = httpx.post(
            f"{LOCAL_BASE}/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return None


# ── Core API (importable) ─────────────────────────────────────────────


def crystallize_messages(
    messages: List[Dict],
    recent_turns: int = None,
    middle_turns: int = None,
) -> Optional[str]:
    """Crystallize a message array with tiered temporal compression.

    Splits messages into recent/middle/old zones and applies:
      Recent: 30% compression (light trim, preserve wording)
      Middle: 60% compression (condense, keep style)
      Old:    90% compression (principles only, bullet list)

    Returns a single formatted checkpoint string, or None on failure.
    """
    recent_n = recent_turns or RECENT_TURNS
    middle_n = middle_turns or MIDDLE_TURNS

    recent_msgs, middle_msgs, old_msgs = _split_messages_by_recency(
        messages, recent_n, middle_n
    )

    total_turns = _count_turns(messages)
    recent_turn_count = _count_turns(recent_msgs)
    middle_turn_count = _count_turns(middle_msgs)
    old_turn_count = _count_turns(old_msgs)

    logger.info(
        f"Crystallizing {total_turns} turns: "
        f"recent={recent_turn_count}, middle={middle_turn_count}, old={old_turn_count}"
    )

    parts = []

    # ── Tier 1: RECENT — 30% compression ──
    if recent_msgs:
        recent_text = _messages_to_text(recent_msgs, max_content_len=800)
        logger.info(f"  Recent: ~{estimate_tokens(recent_text)} tokens → light trim")
        trimmed = _call_llm(RECENT_SYSTEM, RECENT_USER.format(segment=recent_text), max_tokens=1024)
        if trimmed:
            parts.append(f"[RECENT — last {recent_turn_count} turns]\n{trimmed}")
        else:
            # Fallback: include raw recent messages
            parts.append(f"[RECENT — last {recent_turn_count} turns]\n{recent_text}")

    # ── Tier 2: MIDDLE — 60% compression ──
    if middle_msgs:
        middle_text = _messages_to_text(middle_msgs, max_content_len=400)
        logger.info(f"  Middle: ~{estimate_tokens(middle_text)} tokens → condense")
        condensed = _call_llm(MIDDLE_SYSTEM, MIDDLE_USER.format(segment=middle_text), max_tokens=768)
        if condensed:
            parts.append(f"[MIDDLE — turns {old_turn_count+1} to {old_turn_count+middle_turn_count}]\n{condensed}")
        else:
            parts.append(f"[MIDDLE — turns {old_turn_count+1} to {old_turn_count+middle_turn_count}]\n{middle_text}")

    # ── Tier 3: OLD — 90% compression ──
    if old_msgs:
        old_text = _messages_to_text(old_msgs, max_content_len=300)
        logger.info(f"  Old: ~{estimate_tokens(old_text)} tokens → principles only")
        distilled = _call_llm(OLD_SYSTEM, OLD_USER.format(segment=old_text), max_tokens=384)
        if distilled:
            parts.append(f"[OLD — first {old_turn_count} turns]\n{distilled}")
        else:
            parts.append(f"[OLD — first {old_turn_count} turns]\n{old_text}")

    if not parts:
        return None

    return "[SESSION CRYSTAL]\n\n" + "\n\n".join(parts)


# ── Legacy API (backward compat) ──────────────────────────────────────


def crystallize_text(
    transcript: str,
    mode: str = "light",
    model: str = None,
    base_url: str = None,
) -> Optional[str]:
    """Legacy single-pass crystallization. Prefer crystallize_messages() for tiered compression."""
    # For backward compatibility with old callers
    if mode == "full":
        system = """You are a context crystallizer. Extract the problem-solving chain:
1. INITIAL PROBLEM 2. ATTEMPTS (with ✓/✗/~) 3. RESOLUTION 4. SIDE PROBLEMS
5. KEY FILES 6. STATE (done/remaining). Output ONLY valid JSON."""
        user = f"Crystallize this transcript:\n\n{transcript[:6000]}"
        result = _call_llm(system, user, max_tokens=1024)
        if result:
            try:
                crystal = json.loads(result)
                return _format_full_crystal(crystal)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", result, re.DOTALL)
                if match:
                    try:
                        crystal = json.loads(match.group(0))
                        return _format_full_crystal(crystal)
                    except json.JSONDecodeError:
                        pass
                return f"[SESSION CRYSTAL]\n{result}"
        return None
    else:
        system = "Summarize this coding session in under 100 words. What was worked on, what was accomplished, what remains."
        user = f"Summarize:\n\n{transcript[:6000]}"
        result = _call_llm(system, user, max_tokens=256)
        return f"[SESSION SUMMARY]\n{result}" if result else None


def _format_full_crystal(crystal: Dict[str, Any]) -> str:
    """Format a full crystal dict into a checkpoint string."""
    lines = ["[SESSION CRYSTAL]"]
    if prob := crystal.get("initial_problem"):
        lines.append(f"Problem: {prob}")
    if attempts := crystal.get("attempts", []):
        lines.append("Attempts:")
        for a in attempts:
            symbol = {"worked": "✓", "failed": "✗", "partial": "~"}.get(a.get("result", ""), "?")
            lines.append(f"  {symbol} {a.get('approach', '?')} — {a.get('detail', '')}")
    if res := crystal.get("resolution"):
        lines.append(f"Resolution: {res}")
    if side := crystal.get("side_problems", []):
        lines.append("Side issues:")
        for s in side:
            lines.append(f"  • {s}")
    if files := crystal.get("key_files", []):
        lines.append("Files:")
        for f in files:
            lines.append(f"  • {f}")
    if state := crystal.get("state", {}):
        if done := state.get("done"):
            lines.append(f"Done: {done}")
        if remaining := state.get("remaining"):
            lines.append(f"Remaining: {remaining}")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Context Crystallizer — Tiered temporal compression for coding sessions",
    )
    parser.add_argument(
        "input", nargs="?",
        help="Transcript file path (or read from stdin if omitted)",
    )
    parser.add_argument(
        "--recent", type=int, default=RECENT_TURNS,
        help=f"Turns to treat as recent / 30%% compression (default: {RECENT_TURNS})",
    )
    parser.add_argument(
        "--middle", type=int, default=MIDDLE_TURNS,
        help=f"Turns to treat as middle / 60%% compression (default: {MIDDLE_TURNS})",
    )
    parser.add_argument(
        "--legacy", choices=["full", "light"],
        help="Use legacy single-pass mode instead of tiered compression",
    )

    args = parser.parse_args()

    # Read input
    if args.input:
        transcript = Path(args.input).read_text(encoding="utf-8", errors="ignore")
    else:
        if sys.stdin.isatty():
            print("Error: No input file and no stdin pipe.", file=sys.stderr)
            sys.exit(1)
        transcript = sys.stdin.read()

    if not transcript.strip():
        print("Error: Empty transcript.", file=sys.stderr)
        sys.exit(1)

    if args.legacy:
        result = crystallize_text(transcript, mode=args.legacy)
    else:
        # Convert text transcript to pseudo-messages for tiered compression
        lines = transcript.strip().split("\n")
        messages = []
        current_role = None
        current_content = []
        for line in lines:
            m = re.match(r"^(user|assistant|system|ai|human):\s*(.*)", line, re.IGNORECASE)
            if m:
                if current_role and current_content:
                    messages.append({"role": current_role, "content": "\n".join(current_content)})
                current_role = "assistant" if m.group(1).lower() == "ai" else m.group(1).lower()
                current_content = [m.group(2)]
            elif current_role:
                current_content.append(line)
        if current_role and current_content:
            messages.append({"role": current_role, "content": "\n".join(current_content)})

        if not messages:
            # Fallback: treat whole transcript as one message
            messages = [{"role": "user", "content": transcript}]

        result = crystallize_messages(messages, recent_turns=args.recent, middle_turns=args.middle)

    if result:
        print(result)
        print()
        print("─" * 50)
        print(f"Tokens in: ~{estimate_tokens(transcript)}")
        print(f"Tokens out: ~{estimate_tokens(result)}")
        comp = estimate_tokens(transcript) / max(1, estimate_tokens(result))
        print(f"Compression: {comp:.0f}x")
    else:
        print("[CRYSTALLIZATION FAILED]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
