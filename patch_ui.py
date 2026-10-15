import re
import sys

with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "r") as f:
    content = f.read()

# 1. Add state for themes
state_injection = """  const [terminalOutput, setTerminalOutput] = useState<string[]>(['FoveAI Theme Machine — Awaiting Image Drop...']);
  
  // Gallery state
  const [galleryThemes, setGalleryThemes] = useState<any[]>(THEMES); // Default to hardcoded initially, then load from API
  
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

content = content.replace("  const [terminalOutput, setTerminalOutput] = useState<string[]>(['FoveAI Theme Machine — Awaiting Image Drop...']);", state_injection)

# 2. Replace the mapping over THEMES with mapping over galleryThemes
old_map = "{THEMES.map(theme => {"
new_map = "{galleryThemes.map(galleryItem => {\n          const theme = galleryItem.theme_data || galleryItem;\n          const prov = galleryItem.theme_data ? galleryItem : null;\n          const isPaused = prov && prov.status && prov.status.startsWith('paused');"
content = content.replace(old_map, new_map)

# 3. Replace the rendering of the item
old_item = """            <div key={theme.theme_name}
              onClick={() => handleThemeClick(theme)}
              onMouseEnter={() => setHoveredId(theme.theme_name)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                borderRadius: '10px', padding: '14px', cursor: applying ? 'wait' : 'pointer',
                border: isActive ? `1px solid ${theme.fv_accent}` : '1px solid var(--fv-border, rgba(255,255,255,0.08))',
                background: isActive
                  ? `linear-gradient(135deg, ${theme.fv_accent}18, ${theme.fv_accent_2}10)`
                  : isHovered ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.02)',
                boxShadow: isActive ? `0 0 20px ${theme.fv_accent}33` : 'none',
                transition: 'all 0.25s ease',
              }}
            >
              {/* Color swatch strip */}
              <div style={{ display: 'flex', gap: '5px', marginBottom: '10px', height: '32px' }}>
                {swatches.map((c, i) => (
                  <div key={i} style={{
                    flex: 1, borderRadius: '5px', background: c,
                    boxShadow: isActive ? `0 0 10px ${c}88` : 'none',
                    transition: 'box-shadow 0.3s ease',
                  }} />
                ))}
              </div>

              <div style={{ fontWeight: 700, fontSize: '0.9rem', marginBottom: '4px' }}>
                {isActive && <span style={{ color: theme.fv_accent, marginRight: '6px' }}>●</span>}
                {theme.theme_name}
              </div>

              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' }}>
                {[
                  theme.ui_structure.animation_style,
                  theme.ui_structure.ornamentation,
                  theme.ui_structure.shadow_intensity,
                  theme.ui_structure.time_of_day_sync ? '🕐 time-sync' : null,
                ].filter(Boolean).map((tag, i) => (
                  <span key={i} style={{
                    fontSize: '0.68rem', padding: '2px 7px', borderRadius: '4px',
                    background: isActive ? `${theme.fv_accent}22` : 'rgba(255,255,255,0.06)',
                    color: isActive ? theme.fv_accent : 'var(--fv-muted, #93a1b0)',
                    border: `1px solid ${isActive ? theme.fv_accent + '44' : 'transparent'}`,
                  }}>{tag}</span>
                ))}
              </div>

              {isActive && (
                <div style={{ fontSize: '0.72rem', color: theme.fv_accent, opacity: 0.9 }}>
                  ✓ Currently applied to UI
                </div>
              )}
            </div>"""

new_item = """            <div key={theme.theme_name}
              onClick={() => handleThemeClick(theme)}
              onMouseEnter={() => setHoveredId(theme.theme_name)}
              onMouseLeave={() => setHoveredId(null)}
              title={prov ? `Original Motif: ${prov.description}` : ''}
              style={{
                borderRadius: '8px', padding: '12px', cursor: applying ? 'wait' : 'pointer',
                border: isActive ? `1px solid ${theme.fv_accent}` : '1px solid var(--fv-border, rgba(255,255,255,0.08))',
                background: isActive
                  ? `linear-gradient(135deg, ${theme.fv_accent}18, ${theme.fv_accent_2}10)`
                  : isHovered ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.02)',
                boxShadow: isActive ? `0 0 20px ${theme.fv_accent}33` : 'none',
                transition: 'all 0.25s ease',
                display: 'flex', alignItems: 'center', gap: '16px'
              }}
            >
              {/* Nano-UI (Semantic Swatch) */}
              <div style={{
                width: '40px', height: '40px', minWidth: '40px',
                background: theme.fv_accent_2, // Outer background
                border: `1px solid ${theme.fv_accent}`, // Outer border
                borderRadius: '6px',
                position: 'relative',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: 'inset 0 0 10px rgba(0,0,0,0.5)'
              }}>
                {/* Inner panel / table */}
                <div style={{
                  width: '28px', height: '24px',
                  background: 'var(--fv-surface, rgba(0,0,0,0.5))',
                  border: `1px solid ${theme.fv_accent}88`,
                  borderRadius: '3px'
                }} />
                {/* Highlight/Button dot */}
                <div style={{
                  position: 'absolute', top: '5px', right: '5px',
                  width: '6px', height: '6px', borderRadius: '50%',
                  background: theme.fv_accent,
                  boxShadow: `0 0 5px ${theme.fv_accent}`
                }} />
              </div>

              {/* Texts */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div style={{ fontWeight: 700, fontSize: '0.95rem', color: isActive ? theme.fv_accent : '#fff' }}>
                  {theme.theme_name}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--fv-muted, #93a1b0)', marginTop: '2px', fontStyle: 'italic', opacity: 0.8 }}>
                  ({prov ? prov.description.split(' ').slice(0, 5).join(' ') + '...' : 'System Placeholder'})
                </div>
              </div>

              {/* Job State / Play-Pause */}
              {prov && (
                <div style={{ 
                  fontSize: '0.9rem', color: theme.fv_accent, opacity: isHovered ? 1 : 0.6,
                  transition: 'opacity 0.2s', padding: '4px'
                }}>
                  {isPaused ? (isHovered ? '►' : 'II') : ''}
                </div>
              )}
            </div>"""

content = content.replace(old_item, new_item)

with open("/home/lumba/FoveAI/Frontend/multigate/src/components/tabs/ThemeMachineTab.tsx", "w") as f:
    f.write(content)
print("Patched UI successfully")
