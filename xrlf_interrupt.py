#!/usr/bin/env python3
"""
xrlf_interrupt.py — safe-boundary injection points for the XRLF reflex.

Isolated build (XRLF_WS_REDESIGN.md §Decided.3). Not wired to anything.

The existing reflex path in
Tools/xrlf-model/foveated-memory/core/recall-interceptor.js aborts the moment
it sees a trigger token:

    body.destroy();   // truncates the in-flight answer

That is safe but destructive. Prefetch changes the ordering — memory is already
resolved before we need it — so the remaining question is *where* it is legal to
interrupt. This module answers only that, and is deliberately independent of the
runtime so it can be tested against captured output.

Rule: never inject where it can corrupt a unit the consumer is parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Unsafe(Enum):
    MID_SENTENCE = "mid_sentence"
    MID_WORD = "mid_word"
    IN_CODE_FENCE = "in_code_fence"
    IN_JSON = "in_json"
    IN_TAG = "in_tag"
    IN_TOOL_CALL = "in_tool_call"


@dataclass
class Boundary:
    safe: bool
    offset: int
    reason: str
    open_fence: bool = False
    hazards: list[Unsafe] = field(default_factory=list)


# A boundary is the end of a sentence: . ! ? or newline, plus optional closers.
SENTENCE_END = re.compile(r"[.!?][\"')\]]*\s|\n\n?")
FENCE = re.compile(r"```")
JSONISH = re.compile(r'[\{\[\"]\s*[:,]\s*$')
OPEN_TAG = re.compile(r"<[a-z_]+[^>]*$", re.I)
TOOL_CALL = re.compile(r"(?:<tool_call>|<function|<\|)", re.I)
TRAILING_WORD = re.compile(r"[A-Za-z0-9][\)\]\}\"'.,!?;:]*$")


def find_safe_boundary(text: str, *, allow_plain_newline: bool = False) -> Boundary:
    """Return the latest offset in `text` where injection cannot corrupt output.

    Walks candidate sentence terminators backwards and picks the first that is
    not inside a code fence, JSON literal, open tag or tool call.
    """
    if not text:
        return Boundary(False, 0, "empty", hazards=[Unsafe.MID_WORD])

    # Fence state at end of text, via parity — cheap and sufficient for streaming.
    open_fence = len(FENCE.findall(text)) % 2 == 1

    candidates = [m.end() for m in SENTENCE_END.finditer(text)]
    if open_fence:
        # Inside a code block: the only legal point is a blank line at column 0.
        candidates = [m.end() for m in re.finditer(r"\n\s*\n", text)] or [0]

    for off in reversed(candidates):
        head = text[:off]
        tail = text[off:]
        hazards: list[Unsafe] = []

        if open_fence and not re.search(r"\n\s*\n$", head):
            hazards.append(Unsafe.IN_CODE_FENCE)
        if JSONISH.search(head):
            hazards.append(Unsafe.IN_JSON)
        if OPEN_TAG.search(head):
            hazards.append(Unsafe.IN_TAG)
        if TOOL_CALL.search(head) and not TOOL_CALL.search(tail):
            hazards.append(Unsafe.IN_TOOL_CALL)
        # A terminator followed immediately by more word chars means we guessed
        # inside an abbreviation or a decimal ("3.14").
        if TRAILING_WORD.search(tail[:1] or "") and re.search(r"\d\.\d", text[max(0, off - 4) : off + 1]):
            hazards.append(Unsafe.MID_WORD)
        if not allow_plain_newline and tail.startswith("\n"):
            hazards.append(Unsafe.MID_SENTENCE)

        if not hazards:
            return Boundary(
                True,
                off,
                "sentence_end" if not open_fence else "blank_line_in_fence",
                open_fence=open_fence,
            )

    return Boundary(False, 0, "no_safe_boundary", open_fence=open_fence,
                    hazards=[Unsafe.MID_SENTENCE])


def split_at_boundary(text: str, *, allow_plain_newline: bool = False) -> tuple[str, str]:
    """(emittable_prefix, remainder) — emit only up to the safe cut."""
    b = find_safe_boundary(text, allow_plain_newline=allow_plain_newline)
    if not b.safe:
        return "", text
    return text[: b.offset], text[b.offset :]


def inject(prefix: str, memory: str, remainder: str, *, tag: str = "XRLF-MEMORY") -> str:
    """Compose emitted-so-far + memory + not-yet-emitted.

    Memory arrives as a bracketed block on its own line so a consumer parsing
    prose sees a paragraph break, never a spliced word.
    """
    block = f"\n\n[{tag}]\n{memory.strip()}\n\n"
    return prefix + block + remainder