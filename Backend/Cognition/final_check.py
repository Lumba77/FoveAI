import sys
import os
from pathlib import Path

def load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

load_dotenv(r'C:\Users\lumba\Program\FoveAI-lite\.env')

sys.path.append(r'c:\Users\lumba\Program\FoveAI-lite\backend\Cognition')

print("--- Environment Variables (after loading .env) ---")
print(f"FoveAI_LOCAL_BASE_URL: {os.getenv('FoveAI_LOCAL_BASE_URL', 'NOT SET')}")
print(f"FoveAI_CLOUD_BASE_URL: {os.getenv('FoveAI_CLOUD_BASE_URL', 'NOT SET')}")

try:
    import compagent
    print("\n--- compagent.py check ---")
    print(f"OLLAMA_HOST (fallback): {getattr(compagent, 'OLLAMA_HOST', 'NOT FOUND')}")
    print(f"FoveAI_LOCAL_BASE_URL: {getattr(compagent, 'FoveAI_LOCAL_BASE_URL', 'NOT FOUND')}")
    print(f"FoveAI_CLOUD_BASE_URL: {getattr(compagent, 'FoveAI_CLOUD_BASE_URL', 'NOT FOUND')}")
except Exception as e:
    print(f"compagent Error: {e}")

try:
    import slow_burn
    print("\n--- slow_burn.py check ---")
    import inspect
    sig = inspect.signature(slow_burn._ollama_generate)
    print(f"_ollama_generate signature: {sig}")
except Exception as e:
    print(f"slow_burn Error: {e}")
