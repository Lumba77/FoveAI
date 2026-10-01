import pathlib

p = pathlib.Path(r"C:\Users\danie\AppData\Local\hermes\config.yaml")
t = p.read_text(encoding="utf-8")

# Bug 4: api_key_env should be an env var NAME, not the literal key
old_key = "<REDACTED-OLD-KEY>"
new_key = "OLLAMA_API_KEY"

count = t.count(old_key)
print(f"Found {count} occurrences of literal API key in api_key_env")

if count > 0:
    t = t.replace(old_key, new_key)
    p.write_text(t, encoding="utf-8")
    print(f"Replaced {count} occurrences with 'OLLAMA_API_KEY'")
else:
    print("No matches found — file may already be fixed")

print("Done.")
