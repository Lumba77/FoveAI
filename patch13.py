import re

with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "r") as f:
    content = f.read()

old_regex = """      const jsonMatch = fullText.match(/\\{[\\s\\S]*\\}/);
      if (jsonMatch) {
        try {
          const parsed = JSON.parse(jsonMatch[0]) as MasterTheme;
          setTerminalOutput(prev => [...prev, '', '🚀 Applying generated theme to UI...']);
          await handleThemeClick(parsed);
        } catch { /* JSON not parseable, that's fine */ }
      }"""

new_regex = """      if (fullText.includes("___FOVEAI_THEME_JSON_START___")) {
        try {
          const jsonStr = fullText.split("___FOVEAI_THEME_JSON_START___")[1];
          const parsed = JSON.parse(jsonStr) as MasterTheme;
          setTerminalOutput(prev => [...prev, '', '🚀 Applying generated theme to UI...']);
          await handleThemeClick(parsed);
        } catch (e) {
          console.error("JSON parse failed:", e);
        }
      }"""

if old_regex in content:
    content = content.replace(old_regex, new_regex)
    with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "w") as f:
        f.write(content)
    print("Patched ThemeMachineTab.tsx!")
else:
    print("Could not find regex in TSX")
