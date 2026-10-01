r"""
prepare_xrlf_router_eval.py
===========================
Generate a held-out evaluation set for the XRLF router.
All cases are distinct from the training set.

Output: Training/data/xrlf_router_eval.jsonl
"""

import json
from pathlib import Path

ROOT = Path(r"C:\Users\danie\program\LUMAX")
OUTPUT_FILE = ROOT / "Training" / "data" / "xrlf_router_eval.jsonl"


def build_eval():
    examples = [
        # Stop / solved
        ("XRLF: judge whether this user query can be answered in one step.\nQuery: What is the square root of 64?", "solved"),
        ("XRLF: judge whether this user query can be answered in one step.\nQuery: What is the chemical symbol for water?", "solved"),
        ("XRLF: judge whether this user query can be answered in one step.\nQuery: Who wrote Moby Dick?", "solved"),
        ("XRLF: judge whether this user query can be answered in one step.\nQuery: Write a complete operating system in Python.", "continue"),
        ("XRLF: judge whether this user query can be answered in one step.\nQuery: Explain the causes of World War I in detail.", "continue"),

        # Stop/solved on partial response
        ("XRLF: judge this partial response and reply with the single control token.\nPartial: 12 * 15 = 180.", "solved"),
        ("XRLF: judge this partial response and reply with the single control token.\nPartial: We still need to integrate over the bounds.", "continue"),
        ("XRLF: judge this partial response and reply with the single control token.\nPartial: The final probability is 0.85.", "solved"),
        ("XRLF: judge this partial response and reply with the single control token.\nPartial: First, calculate the derivative.", "continue"),
        ("XRLF: judge this partial response and reply with the single control token.\nPartial: The answer is option D.", "solved"),

        # Routing
        ("XRLF: route this query.\nQuery: help me debug a segfault in C++", "<xrl:route specialist=\"code\" />"),
        ("XRLF: route this query.\nQuery: what did we discuss yesterday?", "<xrl:route specialist=\"memory\" />"),
        ("XRLF: route this query.\nQuery: compose a song in minor key", "<xrl:route specialist=\"audio\" />"),
        ("XRLF: route this query.\nQuery: draw a robot in cyberpunk style", "<xrl:route specialist=\"creative\" />"),
        ("XRLF: route this query.\nQuery: convert this Japanese text to English", "<xrl:route specialist=\"language\" />"),
        ("XRLF: route this query.\nQuery: diagnose this TypeScript error", "<xrl:route specialist=\"diagnostic\" />"),
        ("XRLF: route this query.\nQuery: which specialist handles astrophysics?", "<xrl:route specialist=\"reasoning\" />"),
        ("XRLF: route this query.\nQuery: make this melody darker", "<xrl:route specialist=\"audio\" />"),
        ("XRLF: route this query.\nQuery: build a React component for a login form", "<xrl:route specialist=\"code\" />"),
        ("XRLF: route this query.\nQuery: write a haiku about autumn", "<xrl:route specialist=\"creative\" />"),

        # Concise reformulation
        ("XRLF: rewrite this response concisely and append the control token.\nThe capital of Japan is Tokyo, which is the largest city in the country.", "Tokyo is the capital of Japan. solved"),
        ("XRLF: rewrite this response concisely and append the control token.\nWe need to compute the area of the rectangle and then divide by the number of tiles.", "continue"),

        # XRLF tags
        ("XRLF: tag this user signal.\nSignal: user is asking about last week's bug", "<recall:last-week /> <route:memory />"),
        ("XRLF: tag this user signal.\nSignal: user is frustrated the build keeps failing", "<emote:calm /> <route:diagnostic />"),

        # Intent extraction
        ("XRLF: extract intent.\nInput: I can't remember where I saved that file.", "INTENT:recall EMOTION:confused TARGET:memory"),
        ("XRLF: extract intent.\nInput: Make the beat faster.", "INTENT:adjust EMOTION:excited TARGET:audio"),
    ]

    out = []
    for prompt, answer in examples:
        out.append({
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer}
            ]
        })
    return out


def main():
    data = build_eval()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in data:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Wrote {len(data)} eval examples to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
