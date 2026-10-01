r"""
prepare_xrlf_coder_dataset.py
==============================
Prepare the XRLF coder MTP training dataset.

The coder model generates code with XRLF routing awareness — it can emit
XRLF tags inline, use memory operations, and follow XRL cognitive principles
while writing code.

Sources:
  1. qwen-3.8-code dataset (22,667 code instruction pairs) — primary
  2. Phoenix skeleton pairs (code → skeleton) — compression-aware coding
  3. Synthetic XRLF-tagged code examples — code with inline routing tags
  4. Multi-domain coding examples from Backend/Cognition/ — real project code

Output:
  data/xrlf_coder_train.jsonl  (~2,000 rows)
  data/xrlf_coder_eval.jsonl   (~220 rows, 10% held out)
"""

import json
import random
import hashlib
from pathlib import Path
from datasets import load_dataset
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\data")
MULTIDOMAIN_DIR = DATA_DIR / "xrlf_multidomain"
PHOENIX_FILE = DATA_DIR / "phoenix_dataset_augmented.json"
OUTPUT_TRAIN = DATA_DIR / "xrlf_coder_train.jsonl"
OUTPUT_EVAL = DATA_DIR / "xrlf_coder_eval.jsonl"

SYSTEM_PROMPT = (
    "You are an XRLF coder assistant. Generate clean, correct code. "
    "Use XRLF routing tags where appropriate: <xrl:route specialist=\"code\" /> "
    "for code tasks, <xrl:route specialist=\"memory\" /> for memory operations. "
    "Follow XRL principles: precision, step-by-step reasoning, test awareness."
)

SEED = 3407
random.seed(SEED)


# ── Source 1: qwen-3.8-code dataset ────────────────────────────────────────

def load_qwen_code() -> list[dict]:
    """Load code instruction pairs from the qwen-3.8-code dataset."""
    code_file = MULTIDOMAIN_DIR / "coding" / "qwen_code.jsonl"
    if not code_file.exists():
        print(f"  ⚠️ qwen_code.jsonl not found: {code_file}")
        return []

    rows = []
    with open(code_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ex = json.loads(line)
            messages = ex.get("messages", [])
            if len(messages) < 3:
                continue
            # Replace system prompt with XRLF coder prompt
            messages[0]["content"] = SYSTEM_PROMPT
            rows.append({"messages": messages, "metadata": {"source": "qwen_code"}})
    return rows


# ── Source 2: Phoenix skeleton pairs (code → skeleton) ─────────────────────

def load_phoenix_coding() -> list[dict]:
    """Load Phoenix code→skeleton pairs as compression-aware coding examples."""
    if not PHOENIX_FILE.exists():
        return []

    with open(PHOENIX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for item in data:
        full = item.get("full", "").strip()
        skeleton = item.get("skeleton", "").strip()
        language = item.get("language", "unknown")
        compression_ratio = item.get("compression_ratio", 0)

        if not full or not skeleton or compression_ratio > 1.0:
            continue
        if len(full) > 6000:
            full = full[:6000] + "\n# ... (truncated)"

        user = f"Compress this {language} code to its XRLF skeleton:\n\n```\n{full}\n```"
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
                {"role": "assistant", "content": skeleton},
            ],
            "metadata": {"source": "phoenix", "language": language},
        })
    return rows


# ── Source 3: Synthetic XRLF-tagged code examples ──────────────────────────

XRLF_CODE_TEMPLATES = [
    {
        "user": "Write a Python function that connects to Redis and caches a value with a TTL.",
        "assistant": (
            '<xrl:route specialist="code" />\n\n'
            '```python\n'
            'import redis\n'
            'import json\n'
            'from typing import Optional, Any\n'
            '\n'
            'def cache_with_ttl(\n'
            '    client: redis.Redis,\n'
            '    key: str,\n'
            '    value: Any,\n'
            '    ttl_seconds: int = 3600,\n'
            ') -> None:\n'
            '    """Cache a value in Redis with a TTL."""\n'
            '    serialized = json.dumps(value)\n'
            '    client.setex(key, ttl_seconds, serialized)\n'
            '\n'
            'def get_cached(\n'
            '    client: redis.Redis,\n'
            '    key: str,\n'
            ') -> Optional[Any]:\n'
            '    """Retrieve a cached value, returning None if expired."""\n'
            '    raw = client.get(key)\n'
            '    if raw is None:\n'
            '        return None\n'
            '    return json.loads(raw)\n'
            '```\n\n'
            '<xrl:principle>Cache operations should handle serialization and expiration transparently.</xrl:principle>'
        ),
    },
    {
        "user": "Create a FastAPI endpoint that accepts a VR scene description and stores it.",
        "assistant": (
            '<xrl:route specialist="code" />\n\n'
            '```python\n'
            'from fastapi import FastAPI, HTTPException\n'
            'from pydantic import BaseModel, Field\n'
            'from typing import List, Optional\n'
            'import uuid\n'
            '\n'
            'app = FastAPI()\n'
            '\n'
            'class VRObject(BaseModel):\n'
            '    name: str\n'
            '    position: List[float] = Field(..., min_items=3, max_items=3)\n'
            '    rotation: List[float] = Field(default=[0, 0, 0], min_items=3, max_items=3)\n'
            '    scale: List[float] = Field(default=[1, 1, 1], min_items=3, max_items=3)\n'
            '\n'
            'class VRScene(BaseModel):\n'
            '    name: str\n'
            '    objects: List[VRObject]\n'
            '    lighting: Optional[dict] = None\n'
            '\n'
            'scenes: dict[str, VRScene] = {}\n'
            '\n'
            '@app.post("/scene")\n'
            'async def create_scene(scene: VRScene):\n'
            '    scene_id = str(uuid.uuid4())\n'
            '    scenes[scene_id] = scene\n'
            '    return {"id": scene_id, "status": "created"}\n'
            '\n'
            '@app.get("/scene/{scene_id}")\n'
            'async def get_scene(scene_id: str):\n'
            '    if scene_id not in scenes:\n'
            '        raise HTTPException(status_code=404, detail="Scene not found")\n'
            '    return scenes[scene_id]\n'
            '```\n\n'
            '<xrl:principle>VR scenes are spatial graphs - validate positions and rotations at the schema level.</xrl:principle>'
        ),
    },
    {
        "user": "Write a memory management class for XRLF foveated memory.",
        "assistant": (
            '<xrl:route specialist="memory" />\n\n'
            '```python\n'
            'from dataclasses import dataclass, field\n'
            'from typing import Optional, List, Dict\n'
            'from datetime import datetime\n'
            'import heapq\n'
            '\n'
            '@dataclass\n'
            'class MemoryEntry:\n'
            '    id: str\n'
            '    content: str\n'
            '    memory_type: str  # "semantic" or "episodic"\n'
            '    importance: float  # 0.0 to 1.0\n'
            '    timestamp: datetime = field(default_factory=datetime.now)\n'
            '    access_count: int = 0\n'
            '    last_accessed: Optional[datetime] = None\n'
            '\n'
            'class FoveatedMemory:\n'
            '    def __init__(self, capacity: int = 1000):\n'
            '        self.capacity = capacity\n'
            '        self.memories: Dict[str, MemoryEntry] = {}\n'
            '        self._importance_heap: List[tuple[float, str]] = []\n'
            '\n'
            '    def add(self, entry: MemoryEntry) -> None:\n'
            '        if len(self.memories) >= self.capacity:\n'
            '            self._evict_least_important()\n'
            '        self.memories[entry.id] = entry\n'
            '        heapq.heappush(self._importance_heap, (entry.importance, entry.id))\n'
            '\n'
            '    def recall(self, query: str, top_k: int = 5) -> List[MemoryEntry]:\n'
            '        results = sorted(\n'
            '            self.memories.values(),\n'
            '            key=lambda m: (m.importance, m.access_count),\n'
            '            reverse=True,\n'
            '        )[:top_k]\n'
            '        for m in results:\n'
            '            m.access_count += 1\n'
            '            m.last_accessed = datetime.now()\n'
            '        return results\n'
            '\n'
            '    def reinforce(self, memory_id: str, boost: float = 0.1) -> None:\n'
            '        if memory_id in self.memories:\n'
            '            self.memories[memory_id].importance = min(\n'
            '                1.0, self.memories[memory_id].importance + boost\n'
            '            )\n'
            '\n'
            '    def _evict_least_important(self) -> None:\n'
            '        if not self._importance_heap:\n'
            '            return\n'
            '        _, least_id = heapq.heappop(self._importance_heap)\n'
            '        self.memories.pop(least_id, None)\n'
            '```\n\n'
            '<xrl:principle>Foveated memory prioritizes by importance + access frequency, not just recency.</xrl:principle>'
        ),
    },
    {
        "user": "Debug this code: my async function returns None instead of the result.",
        "assistant": (
            '<xrl:route specialist="code" />\n\n'
            'Common async pitfalls that cause None returns:\n\n'
            '1. Missing return in async function:\n'
            '```python\n'
            '# Bad - coroutine returns None\n'
            'async def fetch_data(url):\n'
            '    response = await client.get(url)\n'
            '    data = response.json()\n'
            '\n'
            '# Good - explicit return\n'
            'async def fetch_data(url):\n'
            '    response = await client.get(url)\n'
            '    return response.json()\n'
            '```\n\n'
            '2. Missing await:\n'
            '```python\n'
            '# Bad - returns coroutine object, not result\n'
            'result = fetch_data(url)\n'
            '\n'
            '# Good - awaits the coroutine\n'
            'result = await fetch_data(url)\n'
            '```\n\n'
            '<xrl:principle>Debug by tracing the return path - async adds invisible return None at the end.</xrl:principle>'
        ),
    },
    {
        "user": "Write a temporal awareness module that tracks time between conversation turns.",
        "assistant": (
            '<xrl:route specialist="code" />\n\n'
            '```python\n'
            'from datetime import datetime, timedelta\n'
            'from typing import List, Tuple, Optional\n'
            '\n'
            'class TemporalAwareness:\n'
            '    """Track time passage between conversation turns and resolve temporal deixis."""\n'
            '\n'
            '    def __init__(self):\n'
            '        self.turns: List[Tuple[datetime, str]] = []\n'
            '\n'
            '    def add_turn(self, content: str, timestamp: Optional[datetime] = None) -> None:\n'
            '        ts = timestamp or datetime.now()\n'
            '        self.turns.append((ts, content))\n'
            '\n'
            '    def time_since_last_turn(self) -> timedelta:\n'
            '        if len(self.turns) < 2:\n'
            '            return timedelta(0)\n'
            '        return self.turns[-1][0] - self.turns[-2][0]\n'
            '\n'
            '    def resolve_deixis(self, expression: str, now: datetime) -> Optional[datetime]:\n'
            '        """Resolve temporal expressions like this weekend, last Tuesday."""\n'
            '        expr = expression.lower().strip()\n'
            '        if expr == "this weekend":\n'
            '            days_until_saturday = (5 - now.weekday()) % 7\n'
            '            return now + timedelta(days=days_until_saturday)\n'
            '        elif expr == "last tuesday":\n'
            '            days_back = (now.weekday() - 1) % 7\n'
            '            return now - timedelta(days=days_back if days_back > 0 else 7)\n'
            '        elif expr == "next month":\n'
            '            if now.month == 12:\n'
            '                return datetime(now.year + 1, 1, 1)\n'
            '            return datetime(now.year, now.month + 1, 1)\n'
            '        return None\n'
            '\n'
            '    def is_context_stale(self, max_age: timedelta = timedelta(hours=1)) -> bool:\n'
            '        """Check if the oldest turn in context is too old to be relevant."""\n'
            '        if not self.turns:\n'
            '            return False\n'
            '        age = datetime.now() - self.turns[0][0]\n'
            '        return age > max_age\n'
            '```\n\n'
            '<xrl:principle>Temporal awareness = tracking elapsed time + resolving relative time references to absolute timestamps.</xrl:principle>'
        ),
    },
]


def generate_xrlf_code_examples() -> list[dict]:
    """Generate XRLF-tagged code examples."""
    rows = []
    for template in XRLF_CODE_TEMPLATES:
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": template["user"]},
                {"role": "assistant", "content": template["assistant"]},
            ],
            "metadata": {"source": "synthetic_xrlf_code"},
        })
    return rows


# ── Deduplication ──────────────────────────────────────────────────────────

def dedup(rows: list[dict]) -> list[dict]:
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
    print("  XRLF Coder MTP Dataset Preparation")
    print("=" * 60)

    print("\n[1/3] Loading qwen-3.8-code dataset...")
    code_rows = load_qwen_code()
    # Sample to keep dataset balanced — we don't want 22K code rows
    # overwhelming the other sources
    random.shuffle(code_rows)
    code_rows = code_rows[:800]
    print(f"  Code instruction pairs: {len(code_rows)} (sampled from {len(load_qwen_code()) if code_rows else 0})")

    print("\n[2/3] Loading Phoenix skeleton pairs...")
    phoenix_rows = load_phoenix_coding()
    random.shuffle(phoenix_rows)
    phoenix_rows = phoenix_rows[:500]
    print(f"  Phoenix pairs: {len(phoenix_rows)}")

    print("\n[3/3] Generating XRLF-tagged code examples...")
    xrlf_rows = generate_xrlf_code_examples()
    print(f"  XRLF examples: {len(xrlf_rows)}")

    print("\nCombining + deduplicating + splitting...")
    all_rows = code_rows + phoenix_rows + xrlf_rows
    all_rows = dedup(all_rows)
    random.shuffle(all_rows)

    split_idx = int(len(all_rows) * 0.9)
    train_rows = all_rows[:split_idx]
    eval_rows = all_rows[split_idx:]

    for row in train_rows + eval_rows:
        row.pop("metadata", None)

    with open(OUTPUT_TRAIN, "w", encoding="utf-8") as f:
        for row in train_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with open(OUTPUT_EVAL, "w", encoding="utf-8") as f:
        for row in eval_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 60}")
    print(f"  Coder MTP Dataset Complete")
    print(f"{'=' * 60}")
    print(f"  Train: {len(train_rows)} rows → {OUTPUT_TRAIN}")
    print(f"  Eval:  {len(eval_rows)} rows → {OUTPUT_EVAL}")
    print(f"  Total: {len(all_rows)} unique rows")
    print(f"\n  Source breakdown:")
    print(f"    qwen-3.8-code (sampled): {len(code_rows)}")
    print(f"    Phoenix skeletons: {len(phoenix_rows)}")
    print(f"    XRLF-tagged code: {len(xrlf_rows)}")
    print(f"    After dedup: {len(all_rows)}")


if __name__ == "__main__":
    main()
