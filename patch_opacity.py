import os

p = os.path.expanduser("~/FoveAI/Frontend/multigate/src/lib/uimThemes.ts")
with open(p, "r") as f:
    text = f.read()

# Replace the simple assignment with a check for bg-panel to enforce opacity
old_loop = """  Object.entries(ROLE_MAP).forEach(([role, cssVar]) => {
    const v = r[role];
    if (v) b.setProperty(cssVar, v);
  });"""

new_loop = """  Object.entries(ROLE_MAP).forEach(([role, cssVar]) => {
    const v = r[role];
    if (v) {
      if (cssVar === '--bg-panel' && (v.startsWith('#') || v.startsWith('rgb('))) {
        b.setProperty(cssVar, `color-mix(in srgb, ${v} 70%, transparent)`);
      } else {
        b.setProperty(cssVar, v);
      }
    }
  });"""

text = text.replace(old_loop, new_loop)

with open(p, "w") as f:
    f.write(text)
