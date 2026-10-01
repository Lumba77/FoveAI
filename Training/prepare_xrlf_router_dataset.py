r"""
prepare_xrlf_router_dataset.py
==============================
Build a router-style dataset for the Qwen2.5-0.5B draft model.
The draft is NOT the answerer. It emits control tokens:
- " stop"      -> main model should stop, problem is solved
- " solved"    -> main model has given the answer
- " continue"  -> more reasoning is needed
- XRLF routing tags like <xrl:route specialist="..."/>
- minimal skeletons / next-step hints

Output: Training/data/xrlf_router_train.jsonl
"""

import json
import random
from pathlib import Path

ROOT = Path(r"C:\Users\danie\program\LUMAX")
OUTPUT_FILE = ROOT / "Training" / "data" / "xrlf_router_train.jsonl"


def add(messages, n=1):
    """Return n copies of a messages dict to inflate high-signal examples."""
    return [messages] * n


def build_router_dataset():
    examples = []

    # ── STOP / SOLVED / CONTINUE examples ───────────────────────────────────
    # These mirror the main model emitting an answer and the draft deciding.
    stop_cases = [
        ("12 * 15 + 45 / 3 = 180 + 15 = 195. The answer is 195.", " solved"),
        ("Copper is a metal and conducts electricity. The answer is (C).", " solved"),
        ("Photosynthesis is how plants make food. The answer is (C).", " solved"),
        ("The square root of 144 is 12.", " solved"),
        ("World War II ended in 1945.", " solved"),
        ("After 7 days the tank holds 49 litres.", " solved"),
        ("Therefore the answer is 42.", " solved"),
        ("The answer is option B.", " solved"),
        ("Jane Austen wrote Pride and Prejudice. The answer is (B).", " solved"),
        ("A number times 7 gives 91, so the number is 13.", " solved"),
        ("We need to compute the area first: length * width. Then divide by the tile area.", " continue"),
        ("Let's check the perimeter before calculating the cost.", " continue"),
        ("We know x = 5 but we still need to find y.", " continue"),
        ("The force is 60 N. Next, find acceleration.", " continue"),
        ("First option is wrong because it ignores the constant term.", " continue"),
        ("This is a multi-step problem. Start by summing the values.", " continue"),
        ("I think the answer is close. Let me verify.", " continue"),
        ("We have three variables and only two equations so far.", " continue"),
        ("The first part gives 24. We need to subtract the discount next.", " continue"),
        ("So far the code reads the file, but does not parse the JSON.", " continue"),
        ("Can you explain more?", " continue"),
        ("What do you mean by that?", " continue"),
        ("I need more context to answer.", " continue"),
        ("The reasoning is incomplete.", " continue"),
    ]
    for ctx, signal in stop_cases:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: judge this partial response and reply with the single control token.\nPartial: {ctx}"},
                {"role": "assistant", "content": signal}
            ]
        }))

    # ── Direct user-query stop/solved judgement (no partial response) ───────
    query_signal = [
        ("A store has 24 apples. They sell 7 in the morning and 5 in the afternoon. How many remain?", " solved"),
        ("What is the capital of France?", " solved"),
        ("Who wrote 1984?", " solved"),
        ("Explain quantum computing in depth.", " continue"),
        ("Prove Fermat's Last Theorem.", " continue"),
        ("Write a full novel about a dragon.", " continue"),
        ("Solve this system of equations: 2x + 3y = 12 and x - y = 1.", " continue"),
        ("Is copper a conductor of electricity?", " solved"),
        ("What is 100 divided by 4?", " solved"),
        ("Compare the economic policies of the 1920s and 1930s in detail.", " continue"),
    ]
    for q, signal in query_signal:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: judge whether this user query can be answered in one step.\nQuery: {q}"},
                {"role": "assistant", "content": signal}
            ]
        }))

    # ── Routing decisions ───────────────────────────────────────────────────
    routing = [
        ("fix this python syntax error", "<xrl:route specialist=\"code\" />", " stop"),
        ("make the music sadder", "<xrl:route specialist=\"audio\" />", " stop"),
        ("draw a picture of a dragon", "<xrl:route specialist=\"creative\" />", " stop"),
        ("summarise what we discussed yesterday", "<xrl:route specialist=\"memory\" />", " stop"),
        ("help me refactor this TypeScript", "<xrl:route specialist=\"code\" />", " stop"),
        ("what was the name of the bug we tracked last week?", "<xrl:route specialist=\"memory\" />", " stop"),
        ("translate 'hello' to Japanese", "<xrl:route specialist=\"language\" />", " solved"),
        ("explain this error message", "<xrl:route specialist=\"diagnostic\" />", " continue"),
        ("write a poem about stars", "<xrl:route specialist=\"creative\" />", " stop"),
        ("which model should handle a physics problem?", "<xrl:route specialist=\"reasoning\" />", " stop"),
        ("route this to the sound director", "<xrl:route specialist=\"audio\" />", " stop"),
        ("this is about the UI layout", "<xrl:route specialist=\"frontend\" />", " stop"),
    ]
    for q, route, signal in routing:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: route this query.\nQuery: {q}"},
                {"role": "assistant", "content": f"{route} {signal}"}
            ]
        }))

    # ── XRLF tags and concise steering ──────────────────────────────────────
    xrl_tags = [
        ("user is asking about memory from yesterday", "<recall:yesterday /> <route:memory />"),
        ("this is a complex coding problem", "<route:code /> <think:step-by-step />"),
        ("user wants to draw something", "<route:creative /> <tool:invokeai />"),
        ("context is too long, what to preserve?", "<compress:aggressive /> <retain:emotional />"),
        ("compress 4K dialogue into ring 2", "<fovea:compress ring=2 budget=512 />"),
        ("user is anxious about a bug", "<emote:calm /> <route:diagnostic />"),
        ("user is celebrating a success", "<emote:joy /> <chord:C_MAJOR />"),
        ("this is a hard math problem", "<route:reasoning /> <think:step-by-step />"),
        ("user wants the weather", "<tool:weather /> <stop />"),
        ("generate a function signature", "<skeleton:code /> <route:code />"),
    ]
    for q, tags in xrl_tags:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: tag this user signal.\nSignal: {q}"},
                {"role": "assistant", "content": tags}
            ]
        }))

    # ── Minimal skeletons for the main model to expand ──────────────────────
    skeletons = [
        ("how do I create a Python function that reads a JSON file?", "<skeleton:code> def read_json(path): ... import json; return data </skeleton:code>"),
        ("draft a warm response to 'I missed you'", "<skeleton:emotional> 'I've missed you too. It feels like...' </skeleton:emotional>"),
        ("explain foveated memory", "<skeleton:explanation> 1. six rings 2. compression 3. recall </skeleton:explanation>"),
        ("write a TypeScript add function", "<skeleton:code> function add(a: number, b: number): number { ... } </skeleton:code>"),
        ("help the user feel less overwhelmed", "<skeleton:comfort> acknowledge, step by step, reassurance </skeleton:comfort>"),
    ]
    for q, skel in skeletons:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: provide a minimal skeleton.\nQuery: {q}"},
                {"role": "assistant", "content": skel}
            ]
        }))

    # ── Intent extraction (very short) ──────────────────────────────────────
    intents = [
        ("This is all too much, I need help", "INTENT:help EMOTION:overwhelmed"),
        ("Can you make the music sadder?", "INTENT:adjust EMOTION:melancholic TARGET:audio"),
        ("I want to remember what we talked about", "INTENT:recall EMOTION:curious TARGET:memory"),
        ("The code keeps crashing", "INTENT:debug EMOTION:frustrated TARGET:code"),
        ("Tell me a joke", "INTENT:entertain EMOTION:playful TARGET:creative"),
    ]
    for q, intent in intents:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: extract intent.\nInput: {q}"},
                {"role": "assistant", "content": intent}
            ]
        }))

    # ── Meta-instructions (short) ───────────────────────────────────────────
    meta = [
        ("what should you do if the main model is stuck?", "<hint:reframe /> continue"),
        ("what do you do when the answer is found?", " emit ' solved' and stop"),
        ("how do you handle an unclear user request?", "<ask:clarify /> continue"),
        ("what is the XRLF stop token?", " solved"),
        ("when should the main model keep going?", " continue"),
    ]
    for q, a in meta:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: {q}"},
                {"role": "assistant", "content": a}
            ]
        }))

    # ── Code next-step hints (concise) ──────────────────────────────────────
    code_hints = [
        ("function read_json(path) {\n  // TODO\n}", "<hint:use-json-load /> <skeleton:open-file parse-return />"),
        ("def add(a, b):\n  return a + b", "<hint:done /> solved"),
        ("const result = await fetch(url)", "<hint:await-json /> continue"),
        ("for (let i = 0; i < arr.length; i++)", "<hint:consider-map-filter />"),
        ("import numpy as np\nA = np.array([[1,2],[3,4]])", "<hint:validate-shapes />"),
    ]
    for code, hint in code_hints:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: review this code snippet and give the next action.\n```\n{code}\n```"},
                {"role": "assistant", "content": hint}
            ]
        }))

    # ── Concise answer reformulation (teach brevity) ────────────────────────
    reform = [
        ("In my opinion, the correct answer to this question is option C because copper is a metal and metals conduct electricity.", "Copper is a metal conductor. Answer: (C). solved"),
        ("First we multiply 12 by 15 to get 180, then we divide 45 by 3 to get 15, and finally we add 180 and 15 together to reach a total of 195.", "12 * 15 + 45 / 3 = 195. solved"),
        ("Jane Austen, the famous English novelist, wrote the novel Pride and Prejudice which was published in 1813.", "Jane Austen. Answer: (B). solved"),
        ("We need to think about all sides of the triangle and apply the Pythagorean theorem a squared plus b squared equals c squared before we can solve for the missing side.", "Use a^2 + b^2 = c^2 for right triangles. continue"),
        ("This is a complicated issue with many factors to consider.", " continue"),
    ]
    for verbose, concise in reform:
        examples.extend(add({
            "messages": [
                {"role": "user", "content": f"XRLF: rewrite this response concisely and append the control token.\n{verbose}"},
                {"role": "assistant", "content": concise}
            ]
        }))

    # ── Final round-robin to cross the 1,000 mark ──────────────────────────
    # Re-emit all examples a few times to stabilize tiny output learning.
    expanded = []
    target = 1080
    while len(expanded) < target:
        for ex in examples:
            expanded.append(ex)
            if len(expanded) >= target:
                break
    random.shuffle(expanded)

    return expanded[:target]


def main():
    dataset = build_router_dataset()
    print(f"Generated {len(dataset)} router examples")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in dataset:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
