import sys, re, os

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

# Let's slice the file right after `css = generate_css(theme_data)`
slice_point = content.find("    css = generate_css(theme_data)")
if slice_point == -1:
    print("Could not find slice point!")
    sys.exit(1)

# Find the end of that line
slice_point = content.find("\n", slice_point) + 1

new_tail = """
    import uuid
    uid = uuid.uuid4().hex[:8]
    out_file = os.path.join(THEME_DIR, f"foveai-{name}-{uid}.css")
    with open(out_file, "w") as f:
        f.write(css)
    print(f"\\n✅ Saved unique raw theme bundle to: {out_file}")
    
    # We output the JSON structure as well so ThemeMachineTab.tsx can parse it via regex and auto-apply!
    # ThemeMachineTab.tsx looks for: const jsonMatch = fullText.match(/\\{[\\s\\S]*\\}/);
    # So we must print the raw JSON to stdout at the very end!
    print("\\n" + json.dumps(theme_data, indent=2))
    print(f"\\n✅ Multigate UI applied the theme dynamically via CSS root injection.")

if __name__ == "__main__":
    main()
"""

# Replace everything after the css generation
content = content[:slice_point] + new_tail

with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
    f.write(content)
print("Tail patched successfully!")
