import sys

with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "r") as f:
    content = f.read()

old_set = """    setTerminalOutput([
      `🎨 Applying: ${theme.theme_name}`,
      `🪟 Injecting glassmorphic panels...`,
      `💡 Setting light angle: ${theme.ui_structure.light_angle}`,
      `🌊 Animation style: ${theme.ui_structure.animation_style}`,
      `🔮 Ornamentation: ${theme.ui_structure.ornamentation}`,
      theme.ui_structure.time_of_day_sync ? `🕐 Time-of-day sync: ON` : '',
      soundEnabled ? `🎵 Starting ambient: ${theme.generative_audio?.ambient_loop_prompt}` : '🔇 Sound off — click 🔊 to enable',
      `⚡ Requesting background image from Stable Diffusion...`,
    ].filter(Boolean));"""

new_set = """    setTerminalOutput(prev => [
      ...prev,
      '',
      '================================================================================',
      `🎨 Applying: ${theme.theme_name}`,
      `🪟 Injecting glassmorphic panels...`,
      `💡 Setting light angle: ${theme.ui_structure.light_angle}`,
      `🌊 Animation style: ${theme.ui_structure.animation_style}`,
      `🔮 Ornamentation: ${theme.ui_structure.ornamentation}`,
      theme.ui_structure.time_of_day_sync ? `🕐 Time-of-day sync: ON` : '',
      soundEnabled ? `🎵 Starting ambient: ${theme.generative_audio?.ambient_loop_prompt}` : '🔇 Sound off — click 🔊 to enable',
      `⚡ Requesting background image from Stable Diffusion...`,
    ].filter(Boolean) as string[]);"""

if old_set in content:
    content = content.replace(old_set, new_set)
    with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "w") as f:
        f.write(content)
    print("Patched ThemeMachineTab.tsx to append instead of clear!")
else:
    print("Could not find setTerminalOutput block")
