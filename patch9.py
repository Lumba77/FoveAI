import sys, re

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

# I need to insert the VLM call before ask_llm_for_theme, and modify ask_llm_for_theme to take `image_description`.
# Actually, I'll just rewrite ask_llm_for_theme entirely to include it.

new_func = """
def ask_llm_for_theme(colors: List[str], image_path: str) -> dict:
    import time
    import base64
    headers = {
        "Authorization": "Bearer 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",
        "Content-Type": "application/json"
    }
    
    print("\\n👁️ [VLM IMAGE ANALYST] Extracting structural poetry and mood from the uploaded image...", flush=True)
    time.sleep(0.5)
    
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
            
        vlm_payload = {
            "model": "meta/llama-3.2-90b-vision-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image in a highly poetic, architectural way. Focus on the raw shapes, the mood, the light, the underlying motif, and what elements could inspire a high-tech diffused webpage theme. Keep it to 3 dense sentences."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                    ]
                }
            ],
            "max_tokens": 250,
            "stream": True
        }
        
        image_description = ""
        resp_vlm = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", json=vlm_payload, headers=headers, stream=True)
        for line in resp_vlm.iter_lines():
            if line and line.startswith(b"data: ") and not line.startswith(b"data: [DONE]"):
                try:
                    data = json.loads(line[6:])
                    if "choices" in data and len(data["choices"]) > 0:
                        delta = data["choices"][0].get("delta", {})
                        if "content" in delta:
                            chunk = delta["content"]
                            image_description += chunk
                            sys.stdout.write(chunk)
                            sys.stdout.flush()
                except: pass
    except Exception as e:
        image_description = f"Image analysis failed: {e}. Assume an abstract, surreal inspiration."
        print(image_description)
        
    print("\\n\\n🤖 [VISIONARY EXPERT] Interpreting the Analyst's visual poetry into a UI concept...", flush=True)
    time.sleep(0.5)
    
    pitch_prompt = f"We extracted these dominant colors: {', '.join(colors)}. The Image Analyst provided this breakdown of the reference motif:\\n\\"{image_description}\\"\\n\\nPitch a wild, highly detailed UI design concept. Break down the elements from the original motif into a themed graphical webpage (e.g. if the image had clouds, they become soft glowing borders, etc). Describe the vibe, materials, and layout. Keep it to 4 sentences."
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
    time.sleep(0.5)
    
    critique_prompt = f"The Visionary pitched this UI concept based on a visual motif:\\n{pitch_text}\\nCritique this harshly. Focus on usability, contrast, CSS feasibility, and user comfort. Argue about how to balance the artistic abstraction with deterministic UI principles. Keep it to 3 sentences."
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

# Replace ask_llm_for_theme
idx_start = content.find("def ask_llm_for_theme(colors: List[str]) -> dict:")
idx_prompt = content.find("    prompt = f", idx_start)

content = content[:idx_start] + new_func + content[idx_prompt:]
# Fix main() call to pass image_path
content = content.replace("theme_data = ask_llm_for_theme(colors_hex)", "theme_data = ask_llm_for_theme(colors_hex, args.image_path)")

with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
    f.write(content)
print("Patched successfully")
