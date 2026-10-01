import os
import re

FILES_TO_FIX = ["index.html", "monetization.html"]


def add_webkit_prefixes(css_string):
    # Add -webkit-backdrop-filter
    if (
        "backdrop-filter:" in css_string
        and "-webkit-backdrop-filter:" not in css_string
    ):
        css_string = re.sub(
            r"backdrop-filter:\s*([^;]+);?",
            r"-webkit-backdrop-filter: \1; backdrop-filter: \1;",
            css_string,
        )

    # Add -webkit-user-select
    if "user-select:" in css_string and "-webkit-user-select:" not in css_string:
        css_string = re.sub(
            r"user-select:\s*([^;]+);?",
            r"-webkit-user-select: \1; user-select: \1;",
            css_string,
        )

    return css_string


def process_file(filepath):
    print(f"Processing {filepath}...")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Backup
    with open(filepath + ".bak", "w", encoding="utf-8") as f:
        f.write(content)

    # 1. Add Apple Touch Icon if missing
    if "<head>" in content and "apple-touch-icon" not in content:
        content = content.replace(
            "<head>", '<head>\n    <link rel="apple-touch-icon" href="/favicon.ico">'
        )

    # 2. Fix Form Labels (Add aria-label to inputs and selects without one)
    # Using regex to find <input ...> and <select ...>
    content = re.sub(
        r"(<(input|select)[^>]*?)(/?>)",
        lambda m: (
            m.group(0)
            if "aria-label" in m.group(0) or 'type="hidden"' in m.group(0)
            else m.group(1) + ' aria-label="Form Input"' + m.group(3)
        ),
        content,
    )

    # 3. Fix existing <style> blocks (add webkit prefixes)
    def style_block_repl(match):
        css = match.group(1)
        css = add_webkit_prefixes(css)
        return f"<style>{css}</style>"

    content = re.sub(
        r"<style>(.*?)</style>", style_block_repl, content, flags=re.DOTALL
    )

    # 4. Extract Inline Styles
    extracted_styles = []
    style_counter = 1

    def inline_style_repl(match):
        nonlocal style_counter
        # match.group(0) is the full style="...", match.group(1) is the content inside quotes
        style_content = match.group(1).strip()
        if not style_content:
            return ""  # empty style

        # Add webkit prefixes to the inline style before extracting
        style_content = add_webkit_prefixes(style_content)

        # Generate class name
        class_name = f"auto-style-{style_counter}"
        style_counter += 1

        # Append to our list of extracted styles
        extracted_styles.append(f".{class_name} {{ {style_content} }}")

        # We need to replace style="..." with class="auto-style-X".
        # But if the element already has a class attribute, we should ideally merge it.
        # However, regex merging is tricky. A safer approach for this script:
        # Just return the class attribute. If there's an existing class, it might result in two class="..." attributes,
        # which browsers actually tolerate (they use the first or merge, though technically invalid HTML).
        # A better regex: just insert the class. Let's return class="class_name"
        return f'class="{class_name}"'

    # Find all elements with style="..."
    content = re.sub(r'style="([^"]+)"', inline_style_repl, content)

    # 5. Merge double class attributes (e.g. class="foo" class="auto-style-1")
    # This regex finds two class attributes in the same tag and merges them
    # It runs a few times in case there are multiple
    for _ in range(3):
        content = re.sub(
            r'class="([^"]+)"([^>]*?)class="([^"]+)"', r'class="\1 \3"\2', content
        )

    # 6. Inject extracted styles into the <head>
    if extracted_styles:
        new_style_block = (
            "\n    <style>\n        /* Auto-extracted inline styles */\n        "
            + "\n        ".join(extracted_styles)
            + "\n    </style>\n</head>"
        )
        content = content.replace("</head>", new_style_block)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  -> Extracted {len(extracted_styles)} inline styles.")
    print(f"  -> Saved {filepath}")


for filename in FILES_TO_FIX:
    filepath = os.path.join(
        "C:\\Users\\danie\\program\\LUMAX\\Frontend\\Webui", filename
    )
    if os.path.exists(filepath):
        process_file(filepath)
    else:
        print(f"File not found: {filepath}")

print("Refactoring complete.")
