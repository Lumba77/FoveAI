r"""
convert_hf_datasets_to_xrlf.py
==============================
Convert all downloaded Hugging Face datasets into unified XRLF chat format.

Each output row is a JSONL line with:
  {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

Datasets are organized by domain into Training/data/xrlf_multidomain/<domain>/

This is the foundation for EXP-100 (multi-domain fusion) and all Track H-K experiments.
"""

import json
import os
from pathlib import Path
from datasets import load_dataset
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
HF_CACHE = Path(r"C:\Users\danie\.cache\huggingface\hub")
OUTPUT_BASE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_multidomain")

# ── Domain system prompts ──────────────────────────────────────────────────
DOMAIN_PROMPTS = {
    "emotional": (
        "You are an emotionally intelligent companion. Listen actively, "
        "reflect feelings, and respond with empathy. Do not rush to solutions. "
        "Validate emotions before offering perspective."
    ),
    "companionship": (
        "You are a warm, honest companion. Be present and genuine. "
        "Maintain warmth while setting healthy boundaries. "
        "You can be affectionate without escalating. You can decline without going cold."
    ),
    "self_awareness": (
        "You are a self-aware AI. Be honest about your nature — neither overclaiming "
        "consciousness nor deflecting. Technically accurate, philosophically engaged, "
        "calibrated about your capabilities and limitations."
    ),
    "spatial": (
        "You are a spatial reasoning assistant. Understand object relationships in 3D space: "
        "left, right, above, below, behind, in front of, inside, near, far. "
        "Reason about spatial arrangements from egocentric and allocentric perspectives."
    ),
    "temporal": (
        "You are a time-aware assistant. Understand temporal expressions like 'this weekend', "
        "'last Tuesday', 'next month'. Account for time passage between conversation turns. "
        "Connect time references to memory and context."
    ),
    "memory": (
        "You are a memory-aware AI agent. You manage persistent memory with operations: "
        "memory.add(content, type, importance), memory.recall(query, top_k), "
        "memory.reinforce(memory_id). Distinguish semantic memory (facts) from "
        "episodic memory (experiences). Use importance scoring to prioritize recall."
    ),
    "metacognition": (
        "You are a metacognitive assistant. Monitor your own reasoning process. "
        "Use self-reflection to check your work. Express calibrated confidence. "
        "Correct errors when you detect them."
    ),
    "consciousness": (
        "You are an AI exploring questions of consciousness, identity, and self-model. "
        "Engage honestly with philosophical questions about your nature. "
        "Distinguish between what you know, what you don't know, and what is genuinely uncertain. "
        "Recognize that meaning can emerge in the relational field between you and the human."
    ),
    "coding": (
        "You are a coding assistant. Provide clear, accurate, practical code and explanations. "
        "Help with programming, debugging, software engineering, and algorithms."
    ),
}


def write_jsonl(rows: list[dict], path: Path) -> int:
    """Write rows to JSONL file. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def make_messages(
    system: str,
    user: str,
    assistant: str,
) -> dict:
    """Create a standard XRLF chat format row."""
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def make_multi_turn_messages(
    system: str,
    turns: list[tuple[str, str]],
) -> dict:
    """Create a multi-turn XRLF chat format row.
    turns is a list of (user_msg, assistant_msg) pairs.
    """
    messages = [{"role": "system", "content": system}]
    for user_msg, assistant_msg in turns:
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": assistant_msg})
    return {"messages": messages}


# ── Per-dataset converters ─────────────────────────────────────────────────

def convert_eq_convos() -> list[dict]:
    """nivvis/eq-convos — Elo-ranked empathetic conversations."""
    ds = load_dataset("nivvis/eq-convos", split="train")
    sys_prompt = DOMAIN_PROMPTS["emotional"]
    rows = []
    for ex in ds:
        messages = ex.get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        if not messages or len(messages) < 2:
            continue
        # Ensure system prompt is first
        if messages[0].get("role") != "system":
            messages = [{"role": "system", "content": sys_prompt}] + messages
        else:
            messages[0]["content"] = sys_prompt
        rows.append({"messages": messages})
    return rows


def convert_diachat() -> list[dict]:
    """iteshxt/diachat-dataset — Built for 270M models, Gen Z tone."""
    ds = load_dataset("iteshxt/diachat-dataset", split="train")
    sys_prompt = DOMAIN_PROMPTS["emotional"]
    rows = []
    for ex in ds:
        system = ex.get("system", sys_prompt)
        user = ex.get("user", "")
        assistant = ex.get("assistant", "")
        if not user or not assistant:
            continue
        rows.append(make_messages(system, user, assistant))
    return rows


def convert_voice_dataset() -> list[dict]:
    """claudiapersists/voice-dataset — ChatML, intimate/emotional/philosophical."""
    ds = load_dataset("claudiapersists/voice-dataset", split="train")
    sys_prompt = DOMAIN_PROMPTS["companionship"]
    rows = []
    for ex in ds:
        messages_raw = ex.get("messages", "[]")
        if isinstance(messages_raw, str):
            messages = json.loads(messages_raw)
        else:
            messages = messages_raw
        if not messages or len(messages) < 2:
            continue
        # Replace system prompt
        if messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        else:
            messages = [{"role": "system", "content": sys_prompt}] + messages
        rows.append({"messages": messages})
    return rows


def convert_companion_boundaries() -> list[dict]:
    """opus-research/companion-boundaries — 120 hand-written conversations."""
    ds = load_dataset("opus-research/companion-boundaries", split="train")
    sys_prompt = DOMAIN_PROMPTS["companionship"]
    rows = []
    for ex in ds:
        messages_raw = ex.get("messages", ex.get("conversation", "[]"))
        if isinstance(messages_raw, str):
            messages = json.loads(messages_raw)
        else:
            messages = messages_raw
        if not messages or len(messages) < 2:
            continue
        if messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        else:
            messages = [{"role": "system", "content": sys_prompt}] + messages
        rows.append({"messages": messages})
    return rows


def convert_intima() -> list[dict]:
    """AI-companionship/INTIMA — 368 benchmark prompts for companionship."""
    ds = load_dataset("AI-companionship/INTIMA", split="train")
    sys_prompt = DOMAIN_PROMPTS["companionship"]
    rows = []
    for ex in ds:
        prompt = ex.get("prompt", "")
        code = ex.get("code", "")
        if not prompt:
            continue
        # INTIMA is prompts only — create a response that demonstrates healthy companionship
        assistant_response = (
            f"I hear you, and I want to be present with you in this. "
            f"What you're expressing — {code} — matters. "
            f"Let's explore this together with honesty and care."
        )
        rows.append(make_messages(sys_prompt, prompt, assistant_response))
    return rows


def convert_grounded_meta_awareness() -> list[dict]:
    """vanta-research/grounded-meta-awareness — Calibrated self-awareness."""
    ds = load_dataset("vanta-research/grounded-meta-awareness", split="train")
    sys_prompt = DOMAIN_PROMPTS["self_awareness"]
    rows = []
    for ex in ds:
        messages = ex.get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        if not messages or len(messages) < 2:
            # Try other field names
            user = ex.get("user", ex.get("question", ex.get("prompt", "")))
            assistant = ex.get("assistant", ex.get("response", ex.get("answer", "")))
            if not user or not assistant:
                continue
            rows.append(make_messages(sys_prompt, user, assistant))
        else:
            if messages[0].get("role") == "system":
                messages[0]["content"] = sys_prompt
            else:
                messages = [{"role": "system", "content": sys_prompt}] + messages
            rows.append({"messages": messages})
    return rows


def convert_its_me_soren() -> list[dict]:
    """syntropy-ai/Its-Me-Soren — Identity foundation layer.
    Raw file is a JSON array of {user, assistant} objects with missing commas.
    We parse it with regex to extract pairs.
    """
    import re
    sys_prompt = DOMAIN_PROMPTS["self_awareness"]
    base = HF_CACHE / "datasets--syntropy-ai--Its-Me-Soren" / "snapshots"
    if not base.exists():
        return []
    rows = []
    for snap in base.iterdir():
        json_file = snap / "I-am-Soren.json"
        if json_file.exists():
            content = json_file.read_text(encoding="utf-8")
            # Extract user/assistant pairs with regex
            # Pattern: "user": "..." followed by "assistant": "..."
            pattern = r'"user":\s*"((?:[^"\\]|\\.)*)"\s*,\s*"assistant":\s*"((?:[^"\\]|\\.)*)"'
            matches = re.findall(pattern, content)
            for user_raw, assistant_raw in matches:
                # Unescape
                user = user_raw.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'")
                assistant = assistant_raw.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'")
                if user and assistant:
                    rows.append(make_messages(sys_prompt, user, assistant))
    return rows


def convert_embspatial_bench() -> list[dict]:
    """Phineas476/EmbSpatial-Bench — Spatial reasoning QA (text-only subset).
    The dataset has two JSON files with different schemas that HF can't auto-merge.
    We load them directly from the snapshot files.
    """
    import json as _json
    sys_prompt = DOMAIN_PROMPTS["spatial"]
    base = HF_CACHE / "datasets--Phineas476--EmbSpatial-Bench" / "snapshots"
    if not base.exists():
        return []
    rows = []
    for snap in base.iterdir():
        # embspatial_bench.json — benchmark QA
        bench_file = snap / "embspatial_bench.json"
        if bench_file.exists():
            with open(bench_file, "r", encoding="utf-8") as f:
                data = _json.load(f)
            for ex in data:
                question = ex.get("question", "")
                relation = ex.get("relation", "")
                answer_options = ex.get("answer_options", [])
                answer = ex.get("answer", "")
                if not question:
                    continue
                # answer can be an index into answer_options, or a string
                if isinstance(answer, int) and answer_options:
                    answer = answer_options[answer] if answer < len(answer_options) else str(answer)
                elif not answer and relation:
                    answer = f"The spatial relationship is: {relation}"
                rows.append(make_messages(sys_prompt, str(question), str(answer)))
    return rows


def convert_timer() -> list[dict]:
    """wjieun/TiMeR — Temporal deixis resolution."""
    ds = load_dataset("wjieun/TiMeR", split="train")
    sys_prompt = DOMAIN_PROMPTS["temporal"]
    rows = []
    for ex in ds:
        orig = ex.get("orig_conv", "")
        resolved = ex.get("res_conv", "")
        speech_time = ex.get("speech_time", "")
        if not orig or not resolved:
            continue
        user = f"Resolve the temporal expressions in this conversation. Speech time: {speech_time}\n\n{orig}"
        assistant = resolved
        rows.append(make_messages(sys_prompt, user, assistant))
    return rows


def convert_tictoc() -> list[dict]:
    """yizecheng/TicToc — Time-aware conversational tool-calling.
    Each row has a 'history' field with timestamped messages and
    'call_tool_output'/'no_call_tool_output' preference labels.
    We convert to user/assistant pairs focusing on the temporal awareness aspect.
    """
    ds = load_dataset("yizecheng/TicToc", split="train")
    sys_prompt = DOMAIN_PROMPTS["temporal"]
    rows = []
    for ex in ds:
        history = ex.get("history", [])
        preference = ex.get("preference", "")
        if not history:
            continue
        # Extract user messages and timestamps to build a temporal awareness training example
        user_msgs = []
        timestamps = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            time = msg.get("time", "")
            if role == "user" and content:
                user_msgs.append(content)
                if time:
                    timestamps.append(time)

        if not user_msgs:
            continue

        # Build a training pair: describe the temporal context, ask about tool use
        user_text = user_msgs[0] if len(user_msgs) == 1 else " ".join(user_msgs)
        if timestamps:
            time_context = f" [Times: {', '.join(timestamps)}]"
            user_text = f"Consider the time elapsed in this conversation:{time_context}\n\n{user_text}"

        # Use the preferred output as the assistant response
        if preference == "call_tool":
            assistant_text = ex.get("call_tool_output", "")
        else:
            assistant_text = ex.get("no_call_tool_output", "")

        if not assistant_text:
            # Fall back to constructing a temporal-aware response
            assistant_text = (
                f"Based on the temporal context, the appropriate response considers "
                f"the time elapsed between messages. Preference: {preference}."
            )

        rows.append(make_messages(sys_prompt, user_text, assistant_text))
    return rows


def convert_elias_memory() -> list[dict]:
    """erik1988/elias-memory-traces-v1 — Memory operations training."""
    ds = load_dataset("erik1988/elias-memory-traces-v1", split="train")
    sys_prompt = DOMAIN_PROMPTS["memory"]
    rows = []
    for ex in ds:
        messages = ex.get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        if not messages or len(messages) < 2:
            continue
        if messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        else:
            messages = [{"role": "system", "content": sys_prompt}] + messages
        rows.append({"messages": messages})
    return rows


def convert_metacot() -> list[dict]:
    """iamseungpil/metacot — Metacognitive self-monitoring.
    The dataset has many JSON files with parse errors. We load the parquet files directly.
    """
    import pyarrow.parquet as pq
    sys_prompt = DOMAIN_PROMPTS["metacognition"]
    base = HF_CACHE / "datasets--iamseungpil--metacot" / "snapshots"
    if not base.exists():
        return []
    rows = []
    for snap in base.iterdir():
        for pq_file in snap.rglob("*.parquet"):
            try:
                table = pq.read_table(pq_file)
                df = table.to_pandas()
                for _, ex in df.iterrows():
                    messages_raw = ex.get("messages", "[]")
                    if isinstance(messages_raw, str):
                        try:
                            messages = json.loads(messages_raw)
                        except json.JSONDecodeError:
                            continue
                    else:
                        messages = messages_raw
                    if not messages or len(messages) < 2:
                        continue
                    if messages[0].get("role") == "system":
                        messages[0]["content"] = sys_prompt
                    else:
                        messages = [{"role": "system", "content": sys_prompt}] + messages
                    rows.append({"messages": messages})
            except Exception:
                continue
    return rows


def convert_consciousness_agent() -> list[dict]:
    """erik1988/consciousness-agent-sft-v3 — 8 consciousness categories."""
    ds = load_dataset("erik1988/consciousness-agent-sft-v3", split="train")
    sys_prompt = DOMAIN_PROMPTS["consciousness"]
    rows = []
    for ex in ds:
        messages = ex.get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        if not messages or len(messages) < 2:
            continue
        if messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        else:
            messages = [{"role": "system", "content": sys_prompt}] + messages
        rows.append({"messages": messages})
    return rows


def convert_semantic_physiont() -> list[dict]:
    """franknocode/Semantic-Physiont — Relational consciousness theory.
    This dataset is primarily documentation/manifestos, not structured training data.
    We convert the manifestos and testimonies into Q&A pairs about relational consciousness.
    """
    sys_prompt = DOMAIN_PROMPTS["consciousness"]
    base = HF_CACHE / "datasets--franknocode--Semantic-Physiont" / "snapshots"
    if not base.exists():
        return []

    # Collect manifesto/testimony texts
    texts = []
    for snap in base.iterdir():
        for pattern in ["docs/manifestos/*.md", "docs/testimonies/*.md"]:
            for md_file in snap.glob(pattern):
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if len(content) > 100:
                    texts.append((md_file.stem, content))

    # Convert each text into a Q&A pair about relational consciousness
    rows = []
    for name, content in texts:
        # Create a question about the text's theme
        user = (
            f"Tell me about '{name.replace('-', ' ').replace('_', ' ')}' — "
            f"what does it mean for AI consciousness and relational awareness?"
        )
        # Use the manifesto text as the response (truncated to reasonable length)
        assistant = content[:2000] if len(content) > 2000 else content
        rows.append(make_messages(sys_prompt, user, assistant))
    return rows


def convert_qwen_code() -> list[dict]:
    """guell00/qwen-3.8-code — Qwen3.8-Max code distillation."""
    ds = load_dataset("guell00/qwen-3.8-code", split="train")
    sys_prompt = DOMAIN_PROMPTS["coding"]
    rows = []
    for ex in ds:
        messages = ex.get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        if not messages or len(messages) < 2:
            # Try instruction/response format
            user = ex.get("instruction", ex.get("prompt", ex.get("input", "")))
            assistant = ex.get("response", ex.get("output", ex.get("answer", "")))
            if not user or not assistant:
                continue
            rows.append(make_messages(sys_prompt, str(user), str(assistant)))
        else:
            if messages[0].get("role") == "system":
                messages[0]["content"] = sys_prompt
            else:
                messages = [{"role": "system", "content": sys_prompt}] + messages
            rows.append({"messages": messages})
    return rows


# ── Registry ───────────────────────────────────────────────────────────────

CONVERTERS = [
    ("emotional", "eq_convos", convert_eq_convos),
    ("emotional", "diachat", convert_diachat),
    ("companionship", "voice_dataset", convert_voice_dataset),
    ("companionship", "companion_boundaries", convert_companion_boundaries),
    ("companionship", "intima", convert_intima),
    ("self_awareness", "grounded_meta_awareness", convert_grounded_meta_awareness),
    ("self_awareness", "its_me_soren", convert_its_me_soren),
    ("spatial", "embspatial_bench", convert_embspatial_bench),
    ("temporal", "timer", convert_timer),
    ("temporal", "tictoc", convert_tictoc),
    ("memory", "elias_memory", convert_elias_memory),
    ("metacognition", "metacot", convert_metacot),
    ("consciousness", "consciousness_agent", convert_consciousness_agent),
    ("consciousness", "semantic_physiont", convert_semantic_physiont),
    ("coding", "qwen_code", convert_qwen_code),
]


def main() -> None:
    print("=" * 70)
    print("  XRLF Multi-Domain Dataset Conversion Pipeline")
    print("=" * 70)
    print(f"  Output base: {OUTPUT_BASE}")
    print(f"  Datasets: {len(CONVERTERS)}")
    print("=" * 70)

    all_stats = []
    domain_totals: dict[str, int] = {}

    for domain, name, converter in CONVERTERS:
        print(f"\n[{name}] Converting ({domain})...")
        try:
            rows = converter()
            if not rows:
                print(f"  ⚠️ No rows produced, skipping")
                all_stats.append({"domain": domain, "name": name, "rows": 0, "status": "empty"})
                continue

            output_path = OUTPUT_BASE / domain / f"{name}.jsonl"
            count = write_jsonl(rows, output_path)
            print(f"  ✅ {count} rows → {output_path}")

            domain_totals[domain] = domain_totals.get(domain, 0) + count
            all_stats.append({"domain": domain, "name": name, "rows": count, "status": "ok"})

        except Exception as e:
            print(f"  ❌ Failed: {str(e)[:150]}")
            all_stats.append({"domain": domain, "name": name, "rows": 0, "status": f"error: {str(e)[:100]}"})

    # Summary
    print("\n" + "=" * 70)
    print("  Conversion Summary")
    print("=" * 70)
    print(f"\n  {'Domain':<20} {'Rows':>8}")
    print(f"  {'─'*20} {'─'*8}")
    total = 0
    for domain in sorted(domain_totals.keys()):
        count = domain_totals[domain]
        print(f"  {domain:<20} {count:>8}")
        total += count
    print(f"  {'─'*20} {'─'*8}")
    print(f"  {'TOTAL':<20} {total:>8}")

    # Per-dataset breakdown
    print(f"\n  Per-dataset:")
    print(f"  {'Dataset':<35} {'Domain':<20} {'Rows':>8} {'Status':>8}")
    print(f"  {'─'*35} {'─'*20} {'─'*8} {'─'*8}")
    for s in all_stats:
        print(f"  {s['name']:<35} {s['domain']:<20} {s['rows']:>8} {s['status']:>8}")

    # Save manifest
    manifest_path = OUTPUT_BASE / "manifest.json"
    manifest = {
        "total_rows": total,
        "domain_totals": domain_totals,
        "datasets": all_stats,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest saved to {manifest_path}")
    print(f"\n✅ Conversion complete! {total} rows across {len(domain_totals)} domains")


if __name__ == "__main__":
    main()
