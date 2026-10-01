import sys

sys.path.append(r"c:\Users\lumba\Program\FoveAI-lite\backend\Cognition")
try:
    import compagent

    print(f"OLLAMA_HOST in compagent: {getattr(compagent, 'OLLAMA_HOST', 'NOT FOUND')}")
except Exception as e:
    print(f"Error: {e}")
