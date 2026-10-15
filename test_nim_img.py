import requests, json

headers = {
    "Authorization": "Bearer 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",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

payload = {
    "model": "stabilityai/stable-diffusion-3-medium",
    "prompt": "A beautiful futuristic UI dashboard mockup, glassmorphism, dark mode",
    "response_format": "url"
}

resp = requests.post("https://integrate.api.nvidia.com/v1/images/generations", json=payload, headers=headers)
print("Status:", resp.status_code)
if resp.status_code == 200:
    print("Success")
else:
    print(resp.text)
