"""Check distillation progress and report status."""
import json, os, time

progress_file = "Training/.distill_progress.json"
report_file = "phoenix_teacher_report.md"
dataset_file = "phoenix_teacher_dataset.jsonl"

# Check progress
if os.path.exists(progress_file):
    with open(progress_file) as f:
        progress = json.load(f)
    completed = progress.get("completed", [])
    total = progress.get("total", 0)
    print(f"=== Distillation Progress ===")
    print(f"Completed: {len(completed)}/{total}")
    print(f"Last completed: {completed[-1] if completed else 'N/A'}")
    print(f"Progress file: {progress_file} ({os.path.getsize(progress_file)} bytes)")
else:
    print("No progress file found")

# Check report
if os.path.exists(report_file):
    with open(report_file) as f:
        content = f.read()
    lines = content.strip().split('\n')
    print(f"\n=== Report: {report_file} ===")
    print(f"Size: {os.path.getsize(report_file)} bytes, {len(lines)} lines")
    # Show last 10 lines
    print("Last 10 lines:")
    for line in lines[-10:]:
        print(f"  {line}")
else:
    print(f"\nNo report file found ({report_file})")

# Check dataset
if os.path.exists(dataset_file):
    with open(dataset_file) as f:
        entries = [line for line in f if line.strip()]
    print(f"\n=== Dataset: {dataset_file} ===")
    print(f"Entries: {len(entries)}")
    print(f"Size: {os.path.getsize(dataset_file)} bytes")
    if entries:
        last = json.loads(entries[-1])
        print(f"Last entry: {last.get('file', 'N/A')} (quality: {last.get('quality', 'N/A')})")
else:
    print(f"\nNo dataset file found ({dataset_file})")

# Check running processes
print(f"\n=== System ===")
print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Active terminals: Check Terminal 8 for distillation progress")