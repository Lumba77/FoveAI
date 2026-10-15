with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "r") as f:
    content = f.read()

# Remove the await applyMasterTheme call from handleThemeClick since the WebSocket handles it now
content = content.replace("          await handleThemeClick(parsed);", "          // WebSocket handles the CSS application now\n          await handleThemeClick(parsed);")

with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "w") as f:
    f.write(content)
