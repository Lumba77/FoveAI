import json
import glob
import os

files = {}
for path in glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl"):
    with open(path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'tool_calls' in data:
                    for tc in data['tool_calls']:
                        name = tc.get('function', {}).get('name')
                        if name in ('write_to_file', 'replace_file_content', 'multi_replace_file_content'):
                            args = tc.get('function', {}).get('arguments')
                            if not args: continue
                            try:
                                args = json.loads(args)
                            except:
                                continue
                            target = args.get('TargetFile')
                            if target and 'Frontend/multigate' in target:
                                if name == 'write_to_file':
                                    files[target] = args.get('CodeContent', '')
                                elif name == 'replace_file_content':
                                    # Very basic heuristic: just save the replacement chunks to see what they were working on
                                    content = files.get(target, '') + "\n--- REPLACE ---\n" + args.get('ReplacementContent', '')
                                    files[target] = content
            except:
                pass

os.makedirs('Archive/salvaged_frontend', exist_ok=True)
for k, v in files.items():
    basename = os.path.basename(k)
    with open(os.path.join('Archive/salvaged_frontend', basename), 'w') as f:
        f.write(v)

print("Salvaged:", list(files.keys()))
