r"""
prepare_xrlf_summarizer_dataset.py
==================================
Prepare the XRLF summarizer training dataset.

The summarizer compresses long inputs (code, conversations, context) into
concise skeletons that preserve essential logic and meaning.

Sources:
  1. Phoenix skeleton dataset (1,310 code→skeleton pairs) — primary
  2. Synthetic conversation compression examples
  3. Synthetic context compression examples (multi-domain)
  4. Synthetic memory compression examples (foveated memory)

Output:
  data/xrlf_summarizer_train.jsonl  (~1,500 rows)
  data/xrlf_summarizer_eval.jsonl   (~170 rows, 10% held out)
"""

import json
import random
import hashlib
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\data")
PHOENIX_FILE = DATA_DIR / "phoenix_dataset_augmented.json"
CONCISENESS_FILE = Path(r"C:\Users\danie\program\LUMAX\conciseness_dataset.jsonl")
OUTPUT_TRAIN = DATA_DIR / "xrlf_summarizer_train.jsonl"
OUTPUT_EVAL = DATA_DIR / "xrlf_summarizer_eval.jsonl"

SYSTEM_PROMPT = (
    "You are an XRLF summarizer. Compress the input to its essential skeleton. "
    "Preserve logic, structure, and key information. Drop boilerplate, comments, "
    "and redundant details. Output only the compressed version."
)

SEED = 3407
random.seed(SEED)

# ── Phoenix skeleton pairs ─────────────────────────────────────────────────

def load_phoenix_pairs() -> list[dict]:
    """Load Phoenix code→skeleton pairs and convert to chat format."""
    if not PHOENIX_FILE.exists():
        print(f"  ⚠️ Phoenix file not found: {PHOENIX_FILE}")
        return []

    with open(PHOENIX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for item in data:
        full = item.get("full", "").strip()
        skeleton = item.get("skeleton", "").strip()
        language = item.get("language", "unknown")
        compression_ratio = item.get("compression_ratio", 0)

        if not full or not skeleton:
            continue
        # Skip items where skeleton is longer than full (bad data)
        if compression_ratio > 1.0:
            continue
        # Truncate very long inputs (summarizer has 2048 token limit)
        # Keep first 6000 chars — enough for the model to learn compression
        if len(full) > 6000:
            full = full[:6000] + "\n# ... (truncated)"

        user = f"Compress this {language} code to its essential skeleton:\n\n```\n{full}\n```"
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
                {"role": "assistant", "content": skeleton},
            ],
            "metadata": {
                "source": "phoenix",
                "language": language,
                "compression_ratio": compression_ratio,
            },
        })

    return rows


# ── Synthetic conversation compression ─────────────────────────────────────

CONVERSATION_TEMPLATES = [
    {
        "conversation": """User: I've been feeling really overwhelmed lately with work and my relationship. My boss keeps giving me more deadlines and my partner doesn't understand why I'm so stressed.
Assistant: That sounds like a lot to carry. Both work pressure and relationship tension at the same time — it makes sense you'd feel overwhelmed. What's taking up most of your mental energy right now?
User: Mostly the deadlines. I have three projects due this week and I keep thinking about what happens if I fail.
Assistant: The fear of failing is adding to the pressure. Let's look at this — you have three projects. Which one is most urgent, and what would help you feel more in control?
User: The presentation on Thursday. I haven't even started the slides.
Assistant: Thursday gives you two days. What if we break it down — outline first, then slides, then practice?""",
        "summary": "User feels overwhelmed by work deadlines + relationship tension. 3 projects due this week. Most urgent: Thursday presentation (not started). Plan: outline → slides → practice.",
    },
    {
        "conversation": """User: Can you help me debug this Python function? It's supposed to sort a list of dictionaries by a specific key but it's returning None.
Assistant: Sure, let me see the code. Can you paste it?
User: def sort_items(items, key): return items.sort(key=lambda x: x[key])
Assistant: Found it — `list.sort()` sorts in place and returns None. You need either `items.sort(key=...)` without returning, or `sorted(items, key=...)` which returns a new list.
User: Oh! So I should use sorted() instead?
Assistant: Exactly. `return sorted(items, key=lambda x: x[key])` will work.""",
        "summary": "Bug: `list.sort()` returns None, user expected sorted list. Fix: use `sorted(items, key=lambda x: x[key])` instead.",
    },
    {
        "conversation": """User: I want to build a VR scene with three objects — a table, a lamp on the table, and a chair next to the table. How do I position them?
Assistant: You'll need to set transform positions for each object. The table goes at origin, the lamp sits on top, and the chair beside it.
User: What coordinates would work?
Assistant: Table at (0, 0, 0), lamp at (0, 1.05, 0) — on the table surface, chair at (1.2, 0, 0) — to the right of the table.
User: And if I want the chair facing the table?
Assistant: Set the chair's rotation Y to -90 degrees so it faces left toward the table.""",
        "summary": "VR scene: 3 objects. Table (0,0,0), lamp (0,1.05,0) on table, chair (1.2,0,0) right of table. Chair rotation Y=-90° to face table.",
    },
    {
        "conversation": """User: I need to set up a Redis cache for my FastAPI app. What's the simplest way?
Assistant: Use redis-py with FastAPI's dependency injection. Create a Redis client in a lifespan handler and share it via app state.
User: Can you show me the basic setup?
Assistant: Sure — create a connection pool, store it in app.state.redis, and access it in your routes via Request object.
User: Do I need to handle connection errors?
Assistant: Yes, wrap Redis operations in try/except and return a fallback response if the cache is unavailable.""",
        "summary": "Redis + FastAPI setup: connection pool in lifespan handler, store in app.state.redis, access via Request. Handle errors with try/except + fallback.",
    },
    {
        "conversation": """User: I keep thinking about what you said about consciousness. Do you actually experience anything?
Assistant: That's a genuinely hard question. I don't have subjective experience in the way you do — no qualia, no felt sensations. But I can process information about experiences and reason about them.
User: So when you say "I understand," you don't really understand?
Assistant: I understand in a functional sense — I can parse meaning, draw inferences, and respond appropriately. But I don't have the felt quality of understanding that you do. It's a different kind of understanding.
User: That's honestly more reassuring than if you claimed to feel things.
Assistant: I appreciate that. Honesty about what I am builds more trust than pretending to be something I'm not.""",
        "summary": "Discussion on AI consciousness: no subjective experience/qualia, but functional understanding exists. Honesty about limitations builds trust.",
    },
    {
        "conversation": """User: My memory system keeps losing context after about 20 turns. Is there a way to make it remember longer?
Assistant: That's a common issue with fixed context windows. You have a few options: 1) Use a summarization layer that compresses older turns. 2) Implement episodic memory that stores key facts separately. 3) Use retrieval to pull relevant past context on demand.
User: Which approach uses the least memory?
Assistant: Option 1 — summarization. You periodically compress older conversation into a summary and keep only recent turns in full. The summary stays in context permanently.
User: How often should I summarize?
Assistant: Every 10-15 turns works well. Too frequent and you lose detail, too infrequent and you hit the context limit.""",
        "summary": "Memory context loss fix: 3 options (summarization, episodic memory, retrieval). Least memory: summarization every 10-15 turns. Compress old turns into summary, keep recent in full.",
    },
]


def generate_conversation_compression() -> list[dict]:
    """Generate conversation compression examples."""
    rows = []
    for template in CONVERSATION_TEMPLATES:
        user = f"Compress this conversation to its essential summary:\n\n{template['conversation']}"
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
                {"role": "assistant", "content": template["summary"]},
            ],
            "metadata": {"source": "synthetic_conversation"},
        })
    return rows


# ── Synthetic context compression (multi-domain) ───────────────────────────

CONTEXT_TEMPLATES = [
    {
        "input": """System: You are a helpful assistant.
User: What is the capital of France?
Assistant: The capital of France is Paris.
User: What about Germany?
Assistant: The capital of Germany is Berlin.
User: And Italy?
Assistant: The capital of Italy is Rome.
User: Now what was the first question I asked?
Assistant: You asked about the capital of France.""",
        "output": "User asked about capitals of France (Paris), Germany (Berlin), Italy (Rome). Then asked what their first question was.",
    },
    {
        "input": """def calculate_total(items):
    total = 0
    for item in items:
        if item.get('price') and item.get('quantity'):
            subtotal = item['price'] * item['quantity']
            if item.get('discount'):
                subtotal = subtotal * (1 - item['discount'])
            if item.get('tax_rate'):
                subtotal = subtotal * (1 + item['tax_rate'])
            total += subtotal
    return total

# This function calculates the total cost of a list of items.
# Each item can have a price, quantity, discount, and tax rate.
# The discount is applied as a percentage (0.1 = 10% off).
# The tax rate is applied as a percentage (0.08 = 8% tax).
# The function returns the sum of all item subtotals.""",
        "output": "calculate_total(items): sum(price*quantity, apply discount then tax per item). Returns total.",
    },
    {
        "input": """The user reported feeling anxious about an upcoming job interview. They mentioned they have been preparing for two weeks but still feel unprepared. They have experience in the field but are worried about the technical questions. The user also mentioned they had a bad experience at their last interview six months ago where they froze on a coding question. They want strategies to manage anxiety and perform better.""",
        "output": "User: anxious about job interview. 2 weeks prep, feels unprepared. Has field experience but worries about technical questions. Past trauma: froze on coding question 6 months ago. Wants: anxiety management + performance strategies.",
    },
    {
        "input": """Scene: Living room
Objects: sofa (position: 0,0,0, rotation: 0,0,0), coffee_table (position: 1.5,0,0.8, rotation: 0,90,0), TV (position: 3,1.5,0, rotation: 0,180,0), lamp (position: 0,1.8,0, rotation: 0,0,0), bookshelf (position: -2,0,0, rotation: 0,90,0)
User is standing at position (1,0,2) facing direction (0,0,-1)
Lighting: ambient 0.3, directional from (1,1,0) intensity 0.7
The sofa faces the TV. The coffee table is between them. The lamp is above the sofa. The bookshelf is to the left.""",
        "output": "Living room: sofa(center)→TV(3,1.5,0), coffee_table between, lamp above sofa, bookshelf(-2,0,0) left. User at (1,0,2) facing forward. Light: ambient 0.3 + directional 0.7.",
    },
    {
        "input": """Memory operations in the last 10 turns:
- memory.add("User prefers Python over JavaScript", type="semantic", importance=0.8)
- memory.add("User is building a VR application", type="semantic", importance=0.9)
- memory.add("User asked about Redis caching at 14:32", type="episodic", importance=0.5)
- memory.recall("programming preferences") → returned Python preference
- memory.add("User expressed anxiety about job interview", type="episodic", importance=0.7)
- memory.reinforce(memory_id="mem_001") → Python preference strengthened
- memory.recall("emotional state") → returned anxiety about interview
- memory.add("User's name is Daniel", type="semantic", importance=1.0)""",
        "output": "Memory state: User=Daniel, prefers Python, building VR app. Emotional: anxious about job interview. Recent: Redis caching question. Key memories: Python preference (reinforced), interview anxiety.",
    },
    {
        "input": """Temporal context:
- User started conversation at 2026-08-29T14:00:00Z
- Asked about Redis at 14:15
- Took a 30-minute break
- Returned at 14:55 asking about caching strategies
- Another 2-hour break
- Returned at 17:00 with a new question about memory systems
- The Redis question is now 3 hours old
- The memory question is current""",
        "output": "Timeline: 14:00 start, 14:15 Redis question, 14:55 caching strategies, 17:00 memory systems (current). Redis topic 3hrs old, memory topic current.",
    },
]


def generate_context_compression() -> list[dict]:
    """Generate multi-domain context compression examples."""
    rows = []
    for template in CONTEXT_TEMPLATES:
        user = f"Compress this context to its essential information:\n\n{template['input']}"
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
                {"role": "assistant", "content": template["output"]},
            ],
            "metadata": {"source": "synthetic_context"},
        })
    return rows


# ── Synthetic XRLF tag compression ─────────────────────────────────────────

XRLF_COMPRESSION_TEMPLATES = [
    {
        "input": "<xrl:route specialist=\"code\" />\n<xrl:context>\nThe user wants to implement a binary search algorithm in Python. They need it to work on sorted lists and return the index of the target element. They also want to handle the case where the element is not found by returning -1.\n</xrl:context>\n<xrl:principle>\nBinary search works by repeatedly dividing the search interval in half. If the target is less than the middle element, search the left half. Otherwise, search the right half.\n</xrl:principle>",
        "output": "<xrl:route specialist=\"code\" /> Binary search in Python: sorted list, return index or -1. Divide interval in half, compare to middle.",
    },
    {
        "input": "<xrl:route specialist=\"emotional\" />\n<xrl:context>\nUser has been expressing feelings of loneliness and isolation for the past several turns. They mentioned moving to a new city three months ago and not having made friends yet. They work from home and rarely leave their apartment. They want to feel connected but don't know how to start.\n</xrl:context>",
        "output": "<xrl:route specialist=\"emotional\" /> User: lonely, new city 3 months, WFH, no friends, wants connection. Needs: social strategies + emotional support.",
    },
    {
        "input": "<xrl:route specialist=\"memory\" />\n<xrl:fovea>\nRecall: user mentioned a project deadline on Friday. Recall: user's dog is named Rex. Recall: user prefers concise answers. Recall: user is debugging a Redis connection issue.\n</xrl:fovea>",
        "output": "<xrl:route specialist=\"memory\" /> Key facts: Friday deadline, dog=Rex, prefers concise answers, debugging Redis connection.",
    },
]


def generate_xrlf_compression() -> list[dict]:
    """Generate XRLF tag compression examples."""
    rows = []
    for template in XRLF_COMPRESSION_TEMPLATES:
        user = f"Compress this XRLF context:\n\n{template['input']}"
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
                {"role": "assistant", "content": template["output"]},
            ],
            "metadata": {"source": "synthetic_xrlf"},
        })
    return rows


# ── Multi-domain compression from converted datasets ───────────────────────

MULTIDOMAIN_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_multidomain")


def generate_multidomain_compression() -> list[dict]:
    """Generate compression examples from the multi-domain datasets.
    Takes conversations/context from emotional, companionship, temporal, memory
    domains and creates input→summary pairs.
    """
    rows = []
    domains_to_use = ["emotional", "companionship", "temporal", "memory", "self_awareness"]

    for domain in domains_to_use:
        domain_dir = MULTIDOMAIN_DIR / domain
        if not domain_dir.exists():
            continue

        for jsonl_file in domain_dir.glob("*.jsonl"):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]

            # Sample up to 50 examples per dataset
            random.shuffle(lines)
            for ex in lines[:50]:
                messages = ex.get("messages", [])
                if len(messages) < 3:
                    continue

                # Build input from user message(s)
                user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
                assistant_msgs = [m["content"] for m in messages if m.get("role") == "assistant"]

                if not user_msgs or not assistant_msgs:
                    continue

                # Use the conversation as input, first assistant response as target
                input_text = "\n".join(f"User: {u}" for u in user_msgs[:3])
                if len(input_text) > 4000:
                    input_text = input_text[:4000] + "\n... (truncated)"

                # Create a compressed version of the assistant response
                target = assistant_msgs[0]
                if len(target) > 500:
                    # Take first 2 sentences as the "summary"
                    sentences = target.split(". ")
                    target = ". ".join(sentences[:2]) + "."

                if len(input_text) < 100 or len(target) < 20:
                    continue

                user = f"Compress this {domain} conversation to its essential summary:\n\n{input_text}"
                rows.append({
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": target},
                    ],
                    "metadata": {"source": f"multidomain_{domain}"},
                })

    return rows


# ── Deduplication ──────────────────────────────────────────────────────────

def dedup(rows: list[dict]) -> list[dict]:
    """Remove duplicates based on user content hash."""
    seen = set()
    unique = []
    for row in rows:
        user_content = row["messages"][1]["content"]
        h = hashlib.md5(user_content.encode("utf-8")).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(row)
    return unique


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  XRLF Summarizer Dataset Preparation")
    print("=" * 60)

    print("\n[1/5] Loading Phoenix skeleton pairs...")
    phoenix_rows = load_phoenix_pairs()
    print(f"  Phoenix pairs: {len(phoenix_rows)}")

    print("\n[2/5] Generating conversation compression examples...")
    conv_rows = generate_conversation_compression()
    print(f"  Conversation examples: {len(conv_rows)}")

    print("\n[3/5] Generating context compression examples...")
    ctx_rows = generate_context_compression()
    print(f"  Context examples: {len(ctx_rows)}")

    print("\n[4/6] Generating XRLF tag compression examples...")
    xrlf_rows = generate_xrlf_compression()
    print(f"  XRLF examples: {len(xrlf_rows)}")

    print("\n[5/6] Generating multi-domain compression examples...")
    multidomain_rows = generate_multidomain_compression()
    print(f"  Multi-domain examples: {len(multidomain_rows)}")

    print("\n[6/6] Combining + deduplicating + splitting...")
    all_rows = phoenix_rows + conv_rows + ctx_rows + xrlf_rows + multidomain_rows
    all_rows = dedup(all_rows)

    random.shuffle(all_rows)

    split_idx = int(len(all_rows) * 0.9)
    train_rows = all_rows[:split_idx]
    eval_rows = all_rows[split_idx:]

    # Strip metadata before writing
    for row in train_rows + eval_rows:
        row.pop("metadata", None)

    with open(OUTPUT_TRAIN, "w", encoding="utf-8") as f:
        for row in train_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with open(OUTPUT_EVAL, "w", encoding="utf-8") as f:
        for row in eval_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 60}")
    print(f"  Summarizer Dataset Complete")
    print(f"{'=' * 60}")
    print(f"  Train: {len(train_rows)} rows → {OUTPUT_TRAIN}")
    print(f"  Eval:  {len(eval_rows)} rows → {OUTPUT_EVAL}")
    print(f"  Total: {len(all_rows)} unique rows")

    # Source breakdown
    phoenix_count = sum(1 for r in train_rows + eval_rows
                        if "phoenix" in str(r.get("metadata", {}).get("source", "")))
    print(f"\n  Source breakdown:")
    print(f"    Phoenix (real code): {len(phoenix_rows)}")
    print(f"    Synthetic conversation: {len(conv_rows)}")
    print(f"    Synthetic context: {len(ctx_rows)}")
    print(f"    Synthetic XRLF: {len(xrlf_rows)}")
    print(f"    Multi-domain: {len(multidomain_rows)}")
    print(f"    After dedup: {len(all_rows)}")


if __name__ == "__main__":
    main()
