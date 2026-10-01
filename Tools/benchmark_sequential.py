import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

RESULTS_FILE = (
    Path(__file__).parent / "foveated-memory" / "public" / "benchmark_results.json"
)

# --- Datasets ---
GSM8K_LITE = [
    {
        "q": "A store has 24 apples. They sell 7 in the morning and 5 in the afternoon. How many remain?",
        "a": "12",
    },
    {"q": "Tom saves $15 every week. How much will he save in 8 weeks?", "a": "120"},
    {
        "q": "A recipe needs 3 cups of flour per loaf. How many cups for 7 loaves?",
        "a": "21",
    },
    {
        "q": "A taxi charges $2.50 base + $0.75 per km. What is the fare for 6 km?",
        "a": "7.00",
    },
    {
        "q": "If 15% of a class of 40 students are absent, how many are present?",
        "a": "34",
    },
]

ARC_LITE = [
    {
        "q": "What is the chemical symbol for water? (A) WA (B) H2O (C) CO2 (D) O2",
        "a": "B",
    },
    {
        "q": "What force keeps planets in orbit? (A) magnetism (B) friction (C) gravity (D) tension",
        "a": "C",
    },
    {
        "q": "Which organ pumps blood through the body? (A) lungs (B) liver (C) kidney (D) heart",
        "a": "D",
    },
    {
        "q": "Sound travels fastest through: (A) vacuum (B) air (C) water (D) steel",
        "a": "D",
    },
    {
        "q": "What is the powerhouse of the cell? (A) nucleus (B) ribosome (C) mitochondria (D) vacuole",
        "a": "C",
    },
]

COHERENCE_TURNS = [
    {
        "role": "user",
        "content": "My name is Alex and I am a marine biologist studying coral reefs.",
    },
    {
        "role": "assistant",
        "content": "That's fascinating! What aspect of reefs do you focus on?",
    },
    {
        "role": "user",
        "content": "I study bleaching events and their links to ocean temperature.",
    },
    {
        "role": "user",
        "content": "Can you summarise what you know about me and my work so far?",
    },
]


# --- Helper logic ---
def extract_answer(text: str, expected: str) -> str:
    text = text.strip()
    if len(expected) == 1 and expected.upper() in "ABCD":
        for pattern in [
            r"\bthe answer is[:\s]+([A-D])\b",
            r"\banswer[:\s]+([A-D])\b",
            r"\(([A-D])\)",
            r"^([A-D])[.)]\s",
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        m = re.search(r"\b([A-D])\b", text)
        if m:
            return m.group(1).upper()
        return text[:1].upper()

    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if nums:
        expected_clean = expected.replace(",", "").replace("$", "").strip()
        for n in nums:
            if n == expected_clean or n.rstrip("0").rstrip(
                "."
            ) == expected_clean.rstrip("0").rstrip("."):
                return n
        return nums[0]
    return text[:40]


def is_correct(predicted: str, expected: str) -> bool:
    p = predicted.strip().lower().rstrip(".").replace(",", "").replace("$", "")
    e = expected.strip().lower().rstrip(".").replace(",", "").replace("$", "")
    if p == e:
        return True
    try:
        return abs(float(p) - float(e)) < 0.05
    except ValueError:
        pass
    return False


# --- Network logic ---
class LLMClient:
    def __init__(self, url: str, model_id: str):
        self.url = url
        self.model_id = model_id

    def chat(self, messages: list) -> str:
        data = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.1,
            "stream": False,
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[error: {e}]"


# --- Test Tracks ---
def run_mcq_track(client: LLMClient, name: str, data: list):
    correct = 0
    total_time = 0.0
    for item in data:
        t0 = time.perf_counter()
        resp = client.chat(
            [
                {
                    "role": "system",
                    "content": "Think step by step. Give a concise final answer at the end. For multiple choice questions, state the letter clearly.",
                },
                {"role": "user", "content": item["q"]},
            ]
        )
        t1 = time.perf_counter()
        total_time += t1 - t0
        predicted = extract_answer(resp, item["a"])
        if is_correct(predicted, item["a"]):
            correct += 1

    return {
        "track": name,
        "accuracy": round(correct / len(data) * 100, 1) if len(data) > 0 else 0,
        "avg_latency_ms": round((total_time / len(data)) * 1000)
        if len(data) > 0
        else 0,
    }


def run_coherence_track(client: LLMClient):
    t0 = time.perf_counter()
    resp = client.chat(COHERENCE_TURNS)
    t1 = time.perf_counter()

    resp_lower = resp.lower()
    checks = [
        "alex" in resp_lower,
        any(w in resp_lower for w in ["marine", "biologist", "biology"]),
        any(w in resp_lower for w in ["bleach", "temperature", "ocean", "warm"]),
    ]
    score = sum(checks)

    return {
        "track": "Coherence",
        "accuracy": round(score / len(checks) * 100, 1),
        "avg_latency_ms": round((t1 - t0) * 1000),
    }


def main():
    parser = argparse.ArgumentParser(description="Run successive benchmarks.")
    parser.add_argument(
        "--name",
        required=True,
        help="Name of the model (e.g. 'XRLF 4B' or 'Qwen 4B Base')",
    )
    parser.add_argument(
        "--url", required=True, help="API endpoint for chat completions"
    )
    parser.add_argument(
        "--model_id",
        required=False,
        default="xrlf",
        help="The strict model ID string to send in the JSON payload (required by strict servers like LM Studio)",
    )
    args = parser.parse_args()

    print(
        f"Benchmarking model: {args.name} at {args.url} with model_id: {args.model_id}"
    )
    print("This may take a minute depending on your hardware...")

    client = LLMClient(args.url, args.model_id)

    tracks = [
        run_mcq_track(client, "Math Reasoning", GSM8K_LITE),
        run_mcq_track(client, "Science Reasoning", ARC_LITE),
        run_coherence_track(client),
    ]

    overall_acc = round(sum(t["accuracy"] for t in tracks) / len(tracks), 1)
    overall_lat = round(sum(t["avg_latency_ms"] for t in tracks) / len(tracks))

    result_entry = {
        "model": args.name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_accuracy": overall_acc,
        "overall_latency_ms": overall_lat,
        "tracks": tracks,
    }

    existing_data = []
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            pass

    existing_data = [d for d in existing_data if d["model"] != args.name]
    existing_data.append(result_entry)

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2)

    print(f"\nDone! Overall Accuracy: {overall_acc}%, Avg Latency: {overall_lat}ms")
    print(f"Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
