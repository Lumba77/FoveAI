import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """   - "shadow_intensity": "soft" | "medium" | "hard" | "glowing"
   - "light_angle": e.g., "135deg" for the inset highlight direction.
   - "time_of_day_sync": true | false (Whether the light angle and shadows should physically move across the UI, mirroring the real-world time of day).
   - "animation_style": "fluid-spring" | "snap" | "breathe" | "drift"
   - "ornamentation": "minimal" | "cyber-lines" | "baroque-tech" | "glowing-edges"

Respond ONLY with raw JSON, no markdown blocks, no thinking text.
"""

new_block = """   - "shadow_intensity": "soft" | "medium" | "hard" | "glowing"
   - "light_angle": e.g., "135deg" for the inset highlight direction.
   - "time_of_day_sync": true | false (Whether the light angle and shadows should physically move across the UI, mirroring the real-world time of day).
   - "animation_style": "fluid-spring" | "snap" | "breathe" | "drift"
   - "ornamentation": "minimal" | "cyber-lines" | "baroque-tech" | "glowing-edges"
8. "requested_assets": An array of specific image generation prompts for UI "glue" materials. Each object should have:
   - "name": e.g., "corner-frame", "glass-decal", "repeating-rust-texture"
   - "prompt": The highly detailed image generation prompt for this material.
   - "make_transparent": true/false (Whether the background should be removed to make it a transparent overlay decal).
9. "requested_scripts": An array of tactile physics/logic scripts required to make the UI breathe. Each object should have:
   - "name": e.g., "cursor_reflex_lighting.js", "heavy_inertia_menu.js"
   - "description": A highly detailed prompt for the SoftLayer Coder describing exactly the physics, event listeners, and CSS variable injections needed for this script.

Respond ONLY with raw JSON, no markdown blocks, no thinking text.
"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched Master Builder prompt!")
else:
    print("Could not find block")
