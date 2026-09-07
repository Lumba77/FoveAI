import json
import os
try:
    import redis
    redis_available = True
except ImportError:
    redis_available = False

def export_to_unsloth():
    all_sessions = []
    
    # 1. Try Redis
    if redis_available:
        try:
            r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)
            r.ping()
            print("Connected to Redis. Extracting sessions...")
            for key in r.scan_iter("session:*"):
                data = r.get(key)
                if data:
                    try:
                        messages = json.loads(data)
                        if len(messages) > 1:
                            sharegpt_msgs = []
                            for msg in messages:
                                role = "user" if msg.get("role") == "user" else "assistant"
                                sharegpt_msgs.append({"from": role, "value": msg.get("content", "")})
                            all_sessions.append({"conversations": sharegpt_msgs})
                    except Exception as e:
                        print(f"Failed parsing key {key}: {e}")
        except Exception as e:
            print(f"Redis not available or failed: {e}")
            
    # 2. Try Fallback JSON
    fallback_path = "sessions.json"
    if os.path.exists(fallback_path):
        print(f"Extracting from {fallback_path}...")
        try:
            with open(fallback_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for sid, msgs_str in data.items():
                    if sid.startswith("session:"):
                        try:
                            messages = json.loads(msgs_str) if isinstance(msgs_str, str) else msgs_str
                            if len(messages) > 1:
                                sharegpt_msgs = []
                                for msg in messages:
                                    role = "user" if msg.get("role") == "user" else "assistant"
                                    sharegpt_msgs.append({"from": role, "value": msg.get("content", "")})
                                all_sessions.append({"conversations": sharegpt_msgs})
                        except Exception as e:
                            print(f"Failed parsing fallback key {sid}: {e}")
        except Exception as e:
            print(f"Failed reading {fallback_path}: {e}")

    if not all_sessions:
        print("No sessions found to export!")
        return

    output_file = "unsloth_dataset.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_sessions, f, indent=2, ensure_ascii=False)
    
    print(f"\nSuccess! Exported {len(all_sessions)} sessions to {output_file}.")
    print("You can now upload this file directly to Unsloth for fine-tuning!")

if __name__ == "__main__":
    export_to_unsloth()
