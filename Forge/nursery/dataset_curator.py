"""
Dataset Curator for Forge Nursery
Scans local HF cache for downloaded datasets, validates formats,
and prepares them for Unsloth fine-tuning.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

HF_HUB = os.path.expandvars(
    os.environ.get("HF_HOME", "C:/Users/danie/.cache/huggingface")
)
HUB_DIR = os.path.join(HF_HUB, "hub")


class DatasetInfo:
    """Metadata about a discovered dataset."""

    def __init__(self, name: str, local_path: str, format_hint: str = "unknown"):
        self.name = name
        self.local_path = local_path
        self.format_hint = format_hint
        self.num_files = 0
        self.size_mb = 0.0
        self.valid = False
        self.error = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "local_path": self.local_path,
            "format": self.format_hint,
            "num_files": self.num_files,
            "size_mb": round(self.size_mb, 2),
            "valid": self.valid,
            "error": self.error,
        }


def scan_local_datasets() -> list[DatasetInfo]:
    """Scan the HF hub cache for all downloaded datasets."""
    datasets = []
    if not os.path.isdir(HUB_DIR):
        logger.warning(f"HF hub directory not found: {HUB_DIR}")
        return datasets

    for entry in os.listdir(HUB_DIR):
        if not entry.startswith("datasets--"):
            continue

        # Parse name from directory: datasets--org--repo
        parts = entry.replace("datasets--", "").split("--")
        if len(parts) >= 2:
            name = f"{parts[0]}/{parts[1]}"
        else:
            name = parts[0]

        local_path = os.path.join(HUB_DIR, entry)
        ds = DatasetInfo(name=name, local_path=local_path)
        _analyze_dataset(ds)
        datasets.append(ds)

    return datasets


def _analyze_dataset(ds: DatasetInfo) -> None:
    """Analyze a dataset directory: count files, detect format, check validity."""
    try:
        total_size = 0
        file_count = 0
        formats_found = set()

        for root, dirs, files in os.walk(ds.local_path):
            # Skip blobs and .cache
            dirs[:] = [d for d in dirs if d not in ("blobs", ".cache")]
            for f in files:
                fp = os.path.join(root, f)
                try:
                    size = os.path.getsize(fp)
                    total_size += size
                    file_count += 1
                except OSError:
                    continue

                ext = f.lower()
                if ext.endswith(".jsonl") or ext.endswith(".json"):
                    formats_found.add("jsonl")
                elif ext.endswith(".parquet"):
                    formats_found.add("parquet")
                elif ext.endswith(".arrow"):
                    formats_found.add("arrow")
                elif ext.endswith(".csv"):
                    formats_found.add("csv")
                elif ext.endswith(".txt"):
                    formats_found.add("text")

        ds.num_files = file_count
        ds.size_mb = total_size / (1024 * 1024)

        # Determine format
        if "parquet" in formats_found:
            ds.format_hint = "parquet"
        elif "arrow" in formats_found:
            ds.format_hint = "arrow"
        elif "jsonl" in formats_found:
            ds.format_hint = "jsonl"
        elif "csv" in formats_found:
            ds.format_hint = "csv"
        elif "text" in formats_found:
            ds.format_hint = "text"

        ds.valid = file_count > 0
    except Exception as e:
        ds.error = str(e)
        ds.valid = False


def load_dataset_for_training(
    ds_info: DatasetInfo,
    max_samples: int = 5000,
    text_field: str = "text",
) -> list[dict]:
    """
    Load a dataset into a list of {text: str} dicts suitable for Unsloth training.
    Handles multiple formats: parquet, jsonl, json, csv.
    """
    samples = []
    try:
        for root, dirs, files in os.walk(ds_info.local_path):
            dirs[:] = [d for d in dirs if d not in ("blobs", ".cache")]
            for f in files:
                if len(samples) >= max_samples:
                    break
                fp = os.path.join(root, f)
                ext = f.lower()

                try:
                    if ext.endswith(".parquet"):
                        samples.extend(
                            _read_parquet(fp, max_samples - len(samples), text_field)
                        )
                    elif ext.endswith(".jsonl"):
                        samples.extend(
                            _read_jsonl(fp, max_samples - len(samples), text_field)
                        )
                    elif ext.endswith(".json") and not f.startswith("."):
                        samples.extend(
                            _read_json(fp, max_samples - len(samples), text_field)
                        )
                    elif ext.endswith(".csv"):
                        samples.extend(
                            _read_csv(fp, max_samples - len(samples), text_field)
                        )
                except Exception as e:
                    logger.debug(f"Skipping {fp}: {e}")
                    continue

            if len(samples) >= max_samples:
                break

    except Exception as e:
        logger.error(f"Failed to load dataset {ds_info.name}: {e}")

    logger.info(f"Loaded {len(samples)} samples from {ds_info.name}")
    return samples


def _read_parquet(path: str, limit: int, text_field: str) -> list[dict]:
    """Read parquet files into text samples."""
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(path)
        df = table.to_pandas()
        samples = []
        for _, row in df.head(limit).iterrows():
            text = _extract_text(row, text_field)
            if text:
                samples.append({"text": text})
        return samples
    except ImportError:
        logger.warning("pyarrow not installed, skipping parquet: " + path)
        return []


def _read_jsonl(path: str, limit: int, text_field: str) -> list[dict]:
    """Read JSONL files into text samples."""
    samples = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= limit:
                break
            try:
                obj = json.loads(line.strip())
                text = _extract_text(obj, text_field)
                if text:
                    samples.append({"text": text})
            except json.JSONDecodeError:
                continue
    return samples


def _read_json(path: str, limit: int, text_field: str) -> list[dict]:
    """Read JSON files (single object or array) into text samples."""
    samples = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return samples

    if isinstance(data, list):
        for obj in data[:limit]:
            text = _extract_text(obj, text_field)
            if text:
                samples.append({"text": text})
    elif isinstance(data, dict):
        text = _extract_text(data, text_field)
        if text:
            samples.append({"text": text})
    return samples


def _read_csv(path: str, limit: int, text_field: str) -> list[dict]:
    """Read CSV files into text samples."""
    import csv

    samples = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            text = _extract_text(row, text_field)
            if text:
                samples.append({"text": text})
    return samples


def _extract_text(obj: dict, preferred_field: str = "text") -> str | None:
    """
    Extract text content from a dataset row, trying multiple common field names.
    Handles chat-formatted data (messages array), instruction/response pairs, etc.
    """
    # Direct text field
    if preferred_field in obj and isinstance(obj[preferred_field], str):
        return obj[preferred_field].strip()

    # Chat format: messages array
    if "messages" in obj and isinstance(obj["messages"], list):
        parts = []
        for msg in obj["messages"]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content:
                parts.append(f"{role}: {content}")
        if parts:
            return "\n".join(parts)

    # Conversation format
    if "conversations" in obj and isinstance(obj["conversations"], list):
        parts = []
        for turn in obj["conversations"]:
            for role in ("from", "value"):
                if role in turn:
                    parts.append(
                        f"{turn.get('from', 'unknown')}: {turn.get('value', '')}"
                    )
        if parts:
            return "\n".join(parts)

    # Instruction/response format
    if "instruction" in obj and "output" in obj:
        inst = obj.get("instruction", "")
        out = obj.get("output", "")
        if inst and out:
            return f"Instruction: {inst}\nResponse: {out}"

    # Question/answer format
    if "question" in obj and "answer" in obj:
        return f"Q: {obj['question']}\nA: {obj['answer']}"

    # Prompt/completion format
    if "prompt" in obj and "completion" in obj:
        return f"Prompt: {obj['prompt']}\nCompletion: {obj['completion']}"

    # Fallback: try common text fields
    for field in ("content", "body", "passage", "sentence", "dialogue", "story"):
        if field in obj and isinstance(obj[field], str):
            return obj[field].strip()

    return None


def get_dataset_summary() -> list[dict]:
    """Get a summary of all locally available datasets for the WebUI."""
    datasets = scan_local_datasets()
    return [ds.to_dict() for ds in datasets]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    datasets = scan_local_datasets()
    print(f"\nFound {len(datasets)} datasets in HF cache:\n")
    for ds in datasets:
        status = "✓" if ds.valid else "✗"
        print(f"  {status} {ds.name}")
        print(
            f"    Format: {ds.format_hint}, Files: {ds.num_files}, Size: {ds.size_mb:.1f} MB"
        )
        if ds.error:
            print(f"    Error: {ds.error}")
    print()
