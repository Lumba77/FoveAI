import json
import glob

tools = set()
for path in glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl"):
    with open(path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'tool_calls' in data:
                    for tc in data['tool_calls']:
                        tools.add(tc.get('function', {}).get('name'))
            except:
                pass
print(tools)
