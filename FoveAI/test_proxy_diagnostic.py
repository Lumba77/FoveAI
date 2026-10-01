import json
import time

import requests

PROXY_URL = "http://127.0.0.1:8400/v1/chat/completions"

print("==================================================")
print("  FoveAI Diagnostic: Foveated Memory Proxy Test")
print("==================================================")

payload = {
    "model": "moq-quants-latest",  # It will map to the proxy's active upstream model
    "messages": [
        {
            "role": "system",
            "content": "You are Jen, testing your new dual-brain architecture.",
        },
        {
            "role": "user",
            "content": "Jen, are you awake? How does your new cognitive routing system feel?",
        },
    ],
    "temperature": 0.7,
    "max_tokens": 150,
}

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer test_diagnostic_agent",  # Passes a workspace ID to the proxy
}

try:
    print(f"Sending test ping to {PROXY_URL}...")
    start = time.time()
    response = requests.post(PROXY_URL, json=payload, headers=headers, timeout=120)
    end = time.time()

    print(f"\nStatus Code: {response.status_code}")
    print(f"Response Time: {end - start:.2f} seconds")

    if response.status_code == 200:
        data = response.json()
        print("\n✅ SUCCESS: The proxy responded!")
        print("-" * 50)
        print(json.dumps(data, indent=2))
        print("-" * 50)
        print(f"\nModel used by proxy: {data.get('model', 'Unknown')}")
    else:
        print("\n❌ ERROR: Proxy returned an error.")
        print(response.text)

except Exception as e:
    print("\n❌ CRITICAL FAILURE: Could not reach the proxy.")
    print(f"Exception: {e}")
    print("Is the Foveated Memory Proxy running?")
