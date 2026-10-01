import re

path = r"C:\Users\danie\.antigravity-ide\extensions\papillon.papillon-ai-1.1.1-universal\dist\extension.js"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

providers = re.findall(r'apiProvider:"([^"]+)"', text)
print("apiProviders found in extension:", set(providers))

# Look for openai-compatible or custom base url keywords
for term in [
    "baseUrl",
    "openAiBaseUrl",
    "openAiApiKey",
    "openAiModelId",
    "openai-compatible",
    "nvidia",
]:
    print(f"{term} in bundle:", term.lower() in text.lower())
