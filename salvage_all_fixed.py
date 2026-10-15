import json
import glob

files = set()
paths = glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl") + glob.glob("/home/lumba/.gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl")

for path in paths:
    try:
        with open(path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'tool_calls' in data:
                        for tc in data['tool_calls']:
                            name = tc.get('name')
                            if not name and 'function' in tc:
                                name = tc['function'].get('name')
                            if name in ('write_to_file', 'replace_file_content'):
                                target = ""
                                if 'args' in tc:
                                    target = tc['args'].get('TargetFile', '')
                                elif 'function' in tc and 'arguments' in tc['function']:
                                    args_str = tc['function']['arguments']
                                    try:
                                        args = json.loads(args_str)
                                        target = args.get('TargetFile', '')
                                    except:
                                        pass
                                if target:
                                    files.add(target)
                except Exception as e:
                    pass
    except Exception as e:
        pass

for f in sorted(list(files)):
    print(f)
