import json
import glob
for path in glob.glob("/home/lumba/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl") + glob.glob("/home/lumba/.gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl"):
    with open(path, 'r') as f:
        for line in f:
            if 'theme' in line.lower() and ('write_to_file' in line or 'replace_file_content' in line):
                print(f"Found theme work in: {path}")
                break
