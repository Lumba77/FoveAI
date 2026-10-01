import os

skeleton = "repo-principia.md"
ignore = ".tokenslayer-ignore"

sk_size = os.path.getsize(skeleton)
sk_lines = len(open(skeleton).readlines())

ig_size = os.path.getsize(ignore)
ig_patterns = sum(1 for l in open(ignore) if l.strip() and not l.startswith("#"))

print(f"repo-principia.md: {sk_size} bytes, {sk_lines} lines")
print(f".tokenslayer-ignore: {ig_size} bytes, {ig_patterns} active patterns")
print(f"Estimated tokens (bytes/4): ~{sk_size // 4}")
