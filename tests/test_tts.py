import requests
import json

url = "http://localhost:8005/tts"
payload = {
    "text": "Hello, this is a test.",
    "speaker_id": "female_american1-lumba.wav"
}
headers = {
    'Content-Type': 'application/json'
}

try:
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Success! Received audio data.")
    else:
        print(f"Error: {response.text}")
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
