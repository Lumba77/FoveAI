import json

with open(
    r"C:\Users\danie\.gemini\antigravity-ide\brain\ce39d03f-c724-42b2-9f95-1762180328cd\.system_generated\logs\transcript.jsonl",
    "r",
    encoding="utf-8",
) as f:
    for line in f:
        data = json.loads(line)
        idx = data.get("step_index")
        if idx and 1045 <= idx <= 1065:
            print(f"Step {idx} [{data.get('type')}]:")
            if "tool_calls" in data:
                print("  Tool calls:", data["tool_calls"])
            if data.get("content"):
                print("  Content:", data["content"][:300])
