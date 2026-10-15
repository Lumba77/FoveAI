import json
import glob

for path in glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl"):
    with open(path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'tool_calls' in data and len(data['tool_calls']) > 0:
                    print(json.dumps(data['tool_calls'][0])[:200])
                    exit(0)
            except:
                pass
