import requests, base64

with open("/home/lumba/FoveAI/Frontend/multigate/public/foveai-logo-light.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

payload = {
    "model": "meta/llama-3.2-90b-vision-instruct",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What does this image depict? Describe the mood and shapes."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]
        }
    ],
    "max_tokens": 128
}

headers = {
    "Authorization": "Bearer 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",
    "Content-Type": "application/json"
}

resp = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=payload, headers=headers)
print("Status:", resp.status_code)
if resp.status_code == 200:
    print(resp.json()['choices'][0]['message']['content'])
else:
    print(resp.text)
