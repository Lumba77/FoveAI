import sys, re

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

new_func = """def ask_llm_for_theme(colors: List[str]) -> dict:
    import time
    headers = {
        "Authorization": "Bearer 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",
        "Content-Type": "application/json"
    }

    print("\\n🤖 [VISIONARY EXPERT] Analyzing extracted color palette...", flush=True)
    time.sleep(1)
    
    pitch_prompt = f"We extracted these dominant colors from the user's uploaded image: {', '.join(colors)}. Pitch a wild, highly detailed UI design concept based on these colors. Describe the vibe, the materials (glass, metal, etc), and the layout. Keep it to 3 sentences."
    payload1 = {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "messages": [{"role": "system", "content": "You are a wild visionary UI designer."}, {"role": "user", "content": pitch_prompt}],
        "temperature": 0.9, "stream": True
    }
    
    pitch_text = ""
    try:
        resp1 = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=payload1, headers=headers, stream=True)
        for line in resp1.iter_lines():
            if line and line.startswith(b"data: ") and not line.startswith(b"data: [DONE]"):
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
    except Exception as e:
        print(f"\\nVisionary failed: {e}")

    print("\\n\\n🧐 [CRITIC EXPERT] Reviewing the Visionary's pitch for accessibility and contrast...", flush=True)
    time.sleep(1)
    
    critique_prompt = f"The Visionary pitched this UI concept:\\n{pitch_text}\\nCritique this harshly. Focus on usability, contrast, CSS feasibility, and user comfort. Keep it to 2 sentences."
    payload2 = {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "messages": [{"role": "system", "content": "You are a harsh but brilliant UX critic."}, {"role": "user", "content": critique_prompt}],
        "temperature": 0.7, "stream": True
    }
    
    critique_text = ""
    try:
        resp2 = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=payload2, headers=headers, stream=True)
        for line in resp2.iter_lines():
            if line and line.startswith(b"data: ") and not line.startswith(b"data: [DONE]"):
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
    except Exception as e:
        print(f"\\nCritic failed: {e}")

    print("\\n\\n👷 [MASTER BUILDER] Synthesizing final JSON blueprint from the MoE consensus...", flush=True)
    time.sleep(1)
"""

# Replace up to the prompt definition
idx_start = content.find("def ask_llm_for_theme(colors: List[str]) -> dict:")
idx_prompt = content.find("prompt = f", idx_start)

content = content[:idx_start] + new_func + content[idx_prompt:]
content = content.replace('We have extracted 4 dominant colors from the user\'s uploaded image', 'We have a design consensus from the MoE tandem:\\nVisionary: {pitch_text}\\nCritic: {critique_text}\\n\\nNow, based on this consensus, build a full aesthetic JSON blueprint.')

with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
    f.write(content)
print("Patched successfully!")
