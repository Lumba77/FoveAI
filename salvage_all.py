import json
import glob

files = set()
for path in glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl"):
    try:
        with open(path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'tool_calls' in data:
                        for tc in data['tool_calls']:
                            name = tc.get('name')
                            if name in ('write_to_file', 'replace_file_content'):
                                args = tc.get('args', {})
                                target = args.get('TargetFile', '')
                                files.add(target)
                except Exception as e:
                    pass
    except Exception as e:
        pass

for f in sorted(list(files)):
    print(f)
