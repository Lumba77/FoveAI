import json
import os


def check_file(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    print(f"\n--- {path} ---")
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            for session_id, history in data.items():
                print(f"\nSession: {session_id}")
                if isinstance(history, str):
                    try:
                        history = json.loads(history)
                    except Exception as e:
                        print(f"  Error parsing nested string: {e}")
                        continue
                print(f"  Total turns: {len(history)}")
                # Print last 5 turns
                for turn in history[-10:]:
                    print(
                        f"    {turn.get('role', 'unknown')}: {turn.get('content', '')}"
                    )
        except Exception as e:
            print(f"  Error loading file: {e}")


check_file(r"C:\Users\lumba\Program\FoveAI\sessions.json")
check_file(r"C:\Users\lumba\Program\FoveAI\backend\Cognition\sessions.json")
