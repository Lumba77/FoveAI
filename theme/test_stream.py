import requests, json

payload = {
    "model": "nvidia/nemotron-3-super-120b-a12b",
    "messages": [
        {"role": "system", "content": "You are the FoveAI Master Webdesigner."},
        {"role": "user", "content": "Just say hello world."}
    ],
    "temperature": 0.7,
    "stream": True
}
headers = {
    "Authorization": "Bearer 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",
    "Content-Type": "application/json"
}

resp = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=payload, headers=headers, stream=True)
for line in resp.iter_lines():
    if line:
        print(line.decode('utf-8'))
