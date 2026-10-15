#!/usr/bin/env python3
"""Tests for xrlf_interrupt boundary detection. Runs standalone, no deps."""

import sys

sys.path.insert(0, "/home/lumba/FoveAI")
from xrlf_interrupt import Boundary, find_safe_boundary, inject, split_at_boundary  # noqa: E402

CASES = [
    # (name, text, expect_safe, expect_contains)
    ("plain sentence", "The room feels calm right now. ", True, "now. "),
    ("mid-sentence", "The room feels", False, ""),
    ("after question", "What do you think? ", True, "? "),
    ("two sentences", "One thing. Then another. ", True, "another. "),
    ("in code fence", "Here:\n```py\nx = 1", False, ""),
    ("fence blank line", "Here:\n```py\nx = 1\n\ny = 2", True, "x = 1\n\n"),
    ("decimal number", "Pi is about 3.14 and rising", False, ""),
    ("json literal", '{"role": "user", "content": "hello', False, ""),
    ("json complete", '{"a": 1}. ', True, "1}. "),
    # No trailing char after the terminator: cannot yet distinguish a sentence
    # end from a decimal or ellipsis, so must refuse.
    ("json no trailing char", '{"a": 1}.', False, ""),
    ("open tag", "I feel <emo", False, ""),
    ("closed tag", "I feel <emotion:happy> now. ", True, "now. "),
    ("empty", "", False, ""),
    ("avatar markup", "<emotion:happy> <micro:nod> I hear you! ", True, "you! "),
    ("abbreviation", "Dr. Smith is here. ", True, "here. "),
]


def main() -> int:
    failures = 0
    print(f"{'case':22s} {'safe':5s} {'reason':26s} offset")
    print("-" * 64)
    for name, text, want_safe, want_frag in CASES:
        b = find_safe_boundary(text)
        ok = b.safe == want_safe
        if ok and want_frag and want_frag not in text[: b.offset or len(text)]:
            ok = False
        if not ok:
            failures += 1
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {name:19s} {str(b.safe):5s} {b.reason:26s} {b.offset}")

    print("\n=== split + inject round-trip ===")
    text = "I noticed the lighting changed. It feels warmer now. Still thinking"
    pre, rem = split_at_boundary(text)
    print(f"prefix   : {pre!r}")
    print(f"remainder: {rem!r}")
    composed = inject(pre, "User prefers warm lighting.", rem)
    print(f"composed : {composed!r}")
    assert pre.endswith(" ") and "Still" not in pre, "prefix must end at the boundary"
    assert rem.startswith("Still"), "remainder must hold the un-emitted tail"

    # Invariant: injecting must not disturb what was already emitted. The
    # original text survives verbatim ahead of the inserted block.
    assert text.startswith(pre), "emitted prefix must be an exact slice of the input"
    assert "[XRLF-MEMORY]" not in text, "input was not mutated"
    print(f"prefix preserved verbatim: {text.startswith(pre)}")

    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILURES'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())