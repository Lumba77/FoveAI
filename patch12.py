import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_print = '    print("\\n" + json.dumps(theme_data, indent=2))'
new_print = '    print("\\n___FOVEAI_THEME_JSON_START___\\n" + json.dumps(theme_data, indent=2))'

if old_print in content:
    content = content.replace(old_print, new_print)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched Python script!")
else:
    print("Could not find print statement in python")

