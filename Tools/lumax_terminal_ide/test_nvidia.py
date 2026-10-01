import os

import requests

url = "https://integrate.api.nvidia.com/v1/chat/completions"
api_key = os.environ.get("LUMAX_NVIDIA_API_KEY", "")

if not api_key:
    # Try loading from .env
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("LUMAX_NVIDIA_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

if not api_key:
    print("ERROR: No LUMAX_NVIDIA_API_KEY found in env or .env")
    exit(1)

print(f"API Key: {api_key[:15]}...{api_key[-5:]}")
print("Sending request to NVIDIA API (kimi-k3, reasoning_effort=low)...")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
}

payload = {
    "model": "moonshotai/kimi-k3",
    "messages": [
        {"role": "user", "content": "Say hello in one sentence. You are being tested."}
    ],
    "max_tokens": 100,
    "temperature": 1,
    "stream": False,
    "reasoning_effort": "low",
}

try:
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    print(f"Status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"Model: {data.get('model', '?')}")
        msg = data["choices"][0]["message"]

        if msg.get("reasoning_content"):
            reasoning = msg["reasoning_content"][:300]
            print(f"Reasoning: {reasoning}...")

        print(f"Answer: {msg['content']}")
        print(f"Usage: {data.get('usage', {})}")
    else:
        print(f"Error response: {resp.text[:500]}")

except Exception as e:
    print(f"Exception: {e}")
