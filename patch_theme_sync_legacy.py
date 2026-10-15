with open("/home/lumba/FoveAI/theme/theme_sync.js", "r") as f:
    content = f.read()

legacy_injection = """
        // 1.5 Legacy / Older FoveAI Web Variables (for settings.css and kiosk)
        root.style.setProperty('--bg', theme.fv_bg_dark);
        root.style.setProperty('--panel', theme.fv_bg_panel);
        root.style.setProperty('--text', theme.fv_text_main);
        root.style.setProperty('--muted', theme.fv_text_muted);
        root.style.setProperty('--accent', theme.fv_accent);
        root.style.setProperty('--accent-pink', theme.fv_accent_2);
        root.style.setProperty('--success', theme.fv_warn); // usually a green/warm
        root.style.setProperty('--warning', theme.fv_warn);
        root.style.setProperty('--danger', theme.fv_danger);
        root.style.setProperty('--border', theme.fv_accent + '44');
"""

if "// 2. Glassmorphic Overlays" in content and "1.5 Legacy" not in content:
    content = content.replace("// 2. Glassmorphic Overlays", legacy_injection + "\n        // 2. Glassmorphic Overlays")
    with open("/home/lumba/FoveAI/theme/theme_sync.js", "w") as f:
        f.write(content)
    print("Injected legacy CSS variable aliasing!")
else:
    print("Could not find injection point")
