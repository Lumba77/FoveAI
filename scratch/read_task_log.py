import os

log_path = r"C:\Users\lumba\.gemini\antigravity-cli\brain\7d891572-6aa5-41cd-bee1-d131a09fe632\.system_generated\tasks\task-3183.log"

if not os.path.exists(log_path):
    print("Log not found")
else:
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    print(f"Total lines in task log: {len(lines)}")
    # Find lines containing Warning or TypeError
    for i, line in enumerate(lines):
        if "Warning" in line or "TypeError" in line or "ideas" in line:
            print(f"Line {i+1}: {line.strip()}")
