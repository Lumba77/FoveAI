import re

with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "r") as f:
    content = f.read()

# 1. Inject state hooks right after applying state
if "const [galleryThemes" not in content:
    old_state = "const [applying, setApplying] = useState(false);"
    new_state = """const [applying, setApplying] = useState(false);
  const [galleryThemes, setGalleryThemes] = useState<any[]>(THEMES);
  
  useEffect(() => {
    fetch('/api/themes')
      .then(res => res.json())
      .then(data => {
        if (data && data.themes) {
          setGalleryThemes(data.themes);
        }
      })
      .catch(err => console.error('Failed to load gallery', err));
  }, []);"""
    content = content.replace(old_state, new_state)

# 2. Fix the split error on description
old_text = "({prov ? prov.description.split(' ').slice(0, 5).join(' ') + '...' : 'System Placeholder'})"
new_text = "({prov && typeof prov.description === 'string' ? prov.description.split(' ').slice(0, 5).join(' ') + '...' : 'System Placeholder'})"
content = content.replace(old_text, new_text)

with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "w") as f:
    f.write(content)
print("Fixed missing states and undefined splits!")
