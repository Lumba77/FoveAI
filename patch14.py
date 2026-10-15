import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """            if start != -1 and end != 0:
                return json.loads(content[start:end])
    except Exception as e:
        print(f"LLM failure: {e}")"""

new_block = """            if start != -1 and end != 0:
                return json.loads(content[start:end])
            else:
                raise ValueError("No JSON block found in response")
    except Exception as e:
        print(f"LLM failure: {e}")"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched Master Builder fallback!")
else:
    print("Could not find block")
