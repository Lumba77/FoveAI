import os
import urllib.request

base_url = "https://raw.githubusercontent.com/endel/NativeWebSocket/master/src/NativeWebSocket/"
files = ["WebSocket.cs", "IWebSocket.cs"]
out_dir = "FoveAI/client_quest/Assets/Scripts/NativeWebSocket"
os.makedirs(out_dir, exist_ok=True)

for file in files:
    url = base_url + file
    out_file = os.path.join(out_dir, file)
    print(f"Fetching {url}...")
    try:
        with urllib.request.urlopen(url) as response:
            code = response.read().decode("utf-8")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"Successfully downloaded {file}")
    except Exception as e:
        print(f"Error downloading {file}: {e}")
