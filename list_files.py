import json
import glob

targets = set()
for path in glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl"):
    with open(path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'tool_calls' in data:
                    for tc in data['tool_calls']:
                        name = tc.get('function', {}).get('name')
                        if name in ('write_to_file', 'replace_file_content'):
                            args = json.loads(tc.get('function', {}).get('arguments', '{}'))
                            target = args.get('TargetFile', '')
                            targets.add(f"{path.split('/')[-3]} - {target}")
            except:
                pass
for t in targets:
    if 'multigate' in t.lower():
        print(t)
