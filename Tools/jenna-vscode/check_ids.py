import re

with open(r'c:\Users\danie\program\LUMAX\Tools\jenna-vscode\src\webview\chat.html', 'r', encoding='utf-8') as f:
    text = f.read()

html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', text))

script_match = re.search(r'<script nonce="\{\{NONCE\}\}">(.*?)</script>', text, re.DOTALL)
script = script_match.group(1)
script_ids = set(re.findall(r"getElementById\([\"']([^\"']+)[\"']\)", script))

missing = script_ids - html_ids
print('IDs referenced in JS but MISSING from HTML:')
for m in sorted(missing):
    print(' -', m)

print('\nAll HTML IDs:')
for h in sorted(html_ids):
    print(' +', h)
