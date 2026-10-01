import os

p = os.path.expanduser("~/FoveAI/Frontend/multigate/src/lib/uimThemes.ts")
with open(p, "r") as f:
    text = f.read()

# Add id to interface
text = text.replace("name: string;", "id?: string;\n  name: string;")

# Add image setting to applyUiTheme
apply_insert = """  if (r.accent) {
    b.setProperty('--border-glass', `color-mix(in srgb, ${r.accent} 20%, transparent)`);
  }
  if (t.id) {
    b.setProperty('--bg-image-url', `url('/themes/${t.id}/bg_pattern.png')`);
  } else {
    b.removeProperty('--bg-image-url');
  }"""
text = text.replace("""  if (r.accent) {
    b.setProperty('--border-glass', `color-mix(in srgb, ${r.accent} 20%, transparent)`);
  }""", apply_insert)

# Add id assignment in fetchTheme
fetch_old = """export async function fetchTheme(id: string): Promise<UiTheme> {
  const r = await fetch(`/themes/${id}/theme.json`);
  return r.json();
}"""
fetch_new = """export async function fetchTheme(id: string): Promise<UiTheme> {
  const r = await fetch(`/themes/${id}/theme.json`);
  const data = await r.json();
  data.id = id;
  return data;
}"""
text = text.replace(fetch_old, fetch_new)

with open(p, "w") as f:
    f.write(text)
