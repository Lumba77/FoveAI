"""Extract TS modules from deploy, base64-encode them, generate new deploy."""
import os, base64, re

DEPLOY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'deploy')

with open(DEPLOY_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the modules dict content - find each r'''...''' block
# Pattern: "ModuleName.ts": r'''...''',
modules = {}
pattern = r'"([^"]+\.ts)":\s*r\'\'\'(.*?)\'\'\''
matches = re.findall(pattern, content, re.DOTALL)

for name, ts_content in matches:
    # Strip leading newline
    ts_content = ts_content.lstrip('\n')
    modules[name] = ts_content
    print(f"Extracted {name}: {len(ts_content)} chars")

# Generate new deploy file
new_deploy = '''"""Deploy WebSearch.ts, CommsBridge.ts, VoiceClone.ts, GameController.ts"""
import os, base64

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'Frontend', 'XR_Vessel', 'src', 'senses')

modules_b64 = {
'''

for name, ts_content in modules.items():
    b64 = base64.b64encode(ts_content.encode('utf-8')).decode('ascii')
    # Split into 120-char lines for readability
    lines = [f'    "{name}": (']
    for i in range(0, len(b64), 120):
        chunk = b64[i:i+120]
        lines.append(f'        "{chunk}"')
    lines[-1] = lines[-1] + '),'
    new_deploy += '\n'.join(lines) + '\n'

new_deploy += '''}

os.makedirs(BASE, exist_ok=True)

for fn, b64_content in modules_b64.items():
    fp = os.path.join(BASE, fn)
    try:
        content = base64.b64decode(b64_content)
        with open(fp, 'wb') as f:
            f.write(content)
        size = os.path.getsize(fp)
        print(f'  OK {fn}: {size} bytes')
    except Exception as e:
        print(f'  FAIL {fn}: {e}')

print(f'\\nAll {len(modules_b64)} modules deployed.')
'''

# Write new deploy
new_path = DEPLOY_PATH
with open(new_path, 'w', encoding='utf-8') as f:
    f.write(new_deploy)

print(f"\nWrote new deploy: {new_path}")
print(f"Size: {os.path.getsize(new_path)} bytes")