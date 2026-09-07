import re

with open(r'c:\Users\danie\program\LUMAX\Tools\jenna-vscode\src\webview\chat.html', 'r', encoding='utf-8') as f:
    text = f.read()

script_match = re.search(r'<script nonce="{{NONCE}}">(.*?)</script>', text, re.DOTALL)
if not script_match:
    print("No script block found")
    exit(1)

script = script_match.group(1)

used_vars = set(re.findall(r'\$[a-zA-Z0-9_]+', script))
declared_vars = set(re.findall(r'(?:const|let|var)\s+(\$[a-zA-Z0-9_]+)', script))

# Also functions, parameters, catch vars, and loop vars
func_params = set(re.findall(r'\(([^)]*)\)', script))
for p_group in func_params:
    for p in re.findall(r'\$[a-zA-Z0-9_]+', p_group):
        declared_vars.add(p)

undeclared = used_vars - declared_vars
print("Undeclared $ variables used in script:")
for v in sorted(list(undeclared)):
    print(" -", v)
