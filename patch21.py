import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """            content = resp.json()['choices'][0]['message']['content']
            # extract JSON safely
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end != 0:
                parsed = json.loads(content[start:end])
                return parsed
            else:
                raise ValueError("No JSON block found in LLM output.")
    except Exception as e:
        print(f"LLM failure: {e}")"""

new_block = """            content = resp.json()['choices'][0]['message']['content']
            # extract JSON safely
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end != 0:
                parsed = json.loads(content[start:end])
                parsed["_vlm_text"] = image_description
                parsed["_visionary_text"] = pitch_text
                parsed["_critic_text"] = critique_text
                return parsed
            else:
                raise ValueError("No JSON block found in LLM output.")
    except Exception as e:
        print(f"LLM failure: {e}")"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched return value!")
else:
    print("Could not find block 1")
