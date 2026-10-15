import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_tail = """    # So we must print the raw JSON to stdout at the very end!
    print("\\n___FOVEAI_THEME_JSON_START___\\n" + json.dumps(theme_data, indent=2))
    print(f"\\n✅ Multigate UI applied the theme dynamically via CSS root injection.")

if __name__ == "__main__":
    main()"""

new_tail = """    # So we must print the raw JSON to stdout at the very end!
    print("\\n✅ Multigate UI applying the theme dynamically via CSS root injection.")
    print("\\n___FOVEAI_THEME_JSON_START___\\n" + json.dumps(theme_data, indent=2))

if __name__ == "__main__":
    main()"""

if old_tail in content:
    content = content.replace(old_tail, new_tail)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Fixed trailing garbage bug!")
else:
    print("Could not find tail")
