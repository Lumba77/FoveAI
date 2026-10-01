import os

app_css = os.path.expanduser("~/FoveAI/Frontend/multigate/src/App.css")
with open(app_css, "r") as f:
    text = f.read()
# Replace default chat-header background with var(--bg-panel)
text = text.replace("background: rgba(10, 10, 14, 0.8);", "background: color-mix(in srgb, var(--bg-panel) 60%, transparent);")
with open(app_css, "w") as f:
    f.write(text)

themes_tab = os.path.expanduser("~/FoveAI/Frontend/multigate/src/components/tabs/ThemesTab.tsx")
with open(themes_tab, "r") as f:
    text2 = f.read()
# Remove hardcoded solid background from ThemesTab container
text2 = text2.replace("background: 'var(--bg-dark)'", "background: 'transparent'")
with open(themes_tab, "w") as f:
    f.write(text2)

