
path = r"C:\Users\danie\.antigravity-ide\extensions\papillon.papillon-ai-1.1.1-universal\dist\extension.js"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Find apiProvider definition or enum
pos = text.find("openAiBaseUrl")
while pos != -1:
    snippet = text[max(0, pos - 100) : min(len(text), pos + 200)]
    print("--- SNIPPET ---")
    print(snippet)
    pos = text.find("openAiBaseUrl", pos + 200)
