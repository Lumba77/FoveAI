import sys, re

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

# We need to replace the single ask_llm_for_theme call with a tandem loop
old_block = """def ask_llm_for_theme(colors: list) -> dict:"""

new_block = """import time

def ask_llm_for_theme(colors: list) -> dict:
    headers = {
        "Authorization": "Bearer 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",
        "Content-Type": "application/json"
    }

    # Step 1: The Visionary Pitch
    print("\n[VISIONARY] Analyzing colors... let me pitch a concept.")
    sys.stdout.flush()
    pitch_prompt = f"We have these dominant colors from an image: {', '.join(colors)}. Pitch a wild, highly detailed UI design concept. Describe the vibe, the materials (glass, metal, etc), and the layout. Keep it to 3 sentences."
    payload1 = {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "messages": [{"role": "system", "content": "You are a wild visionary designer."}, {"role": "user", "content": pitch_prompt}],
        "temperature": 0.9, "stream": True
    }
    
    pitch_text = ""
    resp1 = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=payload1, headers=headers, stream=True)
    for line in resp1.iter_lines():
        if line and line.startswith(b"data: "):
            try:
                data = json.loads(line[6:])
                if "choices" in data and len(data["choices"]) > 0:
                    delta = data["choices"][0].get("delta", {})
                    if "content" in delta:
                        chunk = delta["content"]
                        pitch_text += chunk
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
            except: pass
    
    print("\n\n[CRITIC] Reviewing the Visionary's pitch...")
    sys.stdout.flush()
    time.sleep(1)
    
    critique_prompt = f"The Visionary pitched this UI concept:\n{pitch_text}\nCritique this harshly. Focus on usability, contrast, and CSS feasibility. Keep it to 2 sentences."
    payload2 = {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "messages": [{"role": "system", "content": "You are a harsh but brilliant UX critic."}, {"role": "user", "content": critique_prompt}],
        "temperature": 0.7, "stream": True
    }
    
    critique_text = ""
    resp2 = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=payload2, headers=headers, stream=True)
    for line in resp2.iter_lines():
        if line and line.startswith(b"data: "):
            try:
                data = json.loads(line[6:])
                if "choices" in data and len(data["choices"]) > 0:
                    delta = data["choices"][0].get("delta", {})
                    if "content" in delta:
                        chunk = delta["content"]
                        critique_text += chunk
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
            except: pass

    print("\n\n[MASTER BUILDER] Synthesizing final JSON blueprint...")
    sys.stdout.flush()
    time.sleep(1)
"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find block")
