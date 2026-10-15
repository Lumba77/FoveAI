import requests, json

payload = {
    "model": "openai/gpt-oss-20b",
    "messages": [
        {"role": "system", "content": "You are the FoveAI Master Webdesigner."},
        {"role": "user", "content": "Testing. Return {\"hello\": \"world\"}"}
    ],
    "temperature": 0.7
}

resp = requests.post("http://127.0.0.1:8400/v1/chat/completions", json=payload, headers={"Authorization": "Bearer theme_engine"})
print("Status Code:", getattr(resp, 'status_code', 'none'))
print("Response:", resp.text)
