import json
import glob

written_files = set()
for path in glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl") + glob.glob("/home/lumba/.gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl"):
    try:
        with open(path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'tool_calls' in data:
                        for tc in data['tool_calls']:
                            name = tc.get('function', {}).get('name')
                            if name in ('write_to_file', 'replace_file_content'):
                                args = tc.get('function', {}).get('arguments', '{}')
                                try:
                                    args_dict = json.loads(args)
                                    target = args_dict.get('TargetFile', '')
                                    if 'theme' in target.lower():
                                        written_files.add(target)
                                        print(f"Written: {target}")
                                except:
                                    pass
                except Exception as e:
                    pass
    except Exception as e:
        pass
