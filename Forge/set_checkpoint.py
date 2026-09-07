import urllib.request, json

data = json.dumps({"summary": "Session: LumaxProxy setup running on 127.0.0.1:8102 between Cline IDE and Ollama Cloud (ollama.com/v1). Proxy strips context noise then forwards. Cline configured as OpenAI-Compatible provider with baseUrl=http://127.0.0.1:8102/v1, model=deepseek-v4-pro. Proxy confirmed working: HTTP 200. Checkpoint set to reduce token bloat."}).encode()

req = urllib.request.Request("http://127.0.0.1:8102/checkpoint", data=data, headers={"Content-Type": "application/json"}, method="POST")
resp = urllib.request.urlopen(req)
print(resp.status, resp.read().decode())
