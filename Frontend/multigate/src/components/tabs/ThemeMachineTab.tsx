import React, { useState, useEffect } from 'react';
import { applyMasterTheme, startAmbientLoop, stopAmbientLoop } from '../../theme/ThemeApplicator';
import type { MasterTheme } from '../../theme/ThemeApplicator';

// ── Hardcoded themes (will grow as user generates new ones via image drop) ──
const THEMES: MasterTheme[] = [
  {
    theme_name: 'Obsidian Glass Archive',
    fv_accent: '#6ab3d4',
    fv_accent_2: '#8a7fbc',
    fv_ok: '#19282c',
    fv_warn: '#a07a3a',
    fv_danger: '#8b2020',
    background_prompt: 'Epic hyper-detailed cinematic shot of an infinite subterranean library built from polished obsidian and dark carbon fiber. Intricate glowing geometric clockwork frames dominate the scene reflecting deep sapphire and muted violet light. Moody mysterious vast atmosphere with high-gloss reflections on wet-look glass surfaces and dynamic slow ambient light pulses. Volumetric lighting 8k hyper-detailed ornamentation.',
    generative_audio: {
      ambient_loop_prompt: 'low resonant synth pads, echoing water droplets, deep bass pulses, subterranean hum',
      ui_clicks: 'heavy metallic clank with glass resonance',
    },
    ui_structure: {
      menu_position: 'left',
      border_radius: '6px',
      glass_opacity: 0.18,
      shadow_intensity: 'glowing',
      light_angle: '135deg',
      time_of_day_sync: true,
      animation_style: 'breathe',
      ornamentation: 'baroque-tech',
    },
  },
  {
    theme_name: 'Celestial Nebula',
    fv_accent: '#5eead4',
    fv_accent_2: '#a78bfa',
    fv_ok: '#1a472a',
    fv_warn: '#e8b64c',
    fv_danger: '#ff4757',
    background_prompt: 'Breathtaking cinematic shot of a glowing nebula in deep space. Teal and violet cosmic clouds swirl around bright star clusters. Volumetric god rays pierce through gaseous formations. Hyper-detailed astro photography 8k, dramatic scale, luminous.',
    generative_audio: {
      ambient_loop_prompt: 'cosmic drone, ethereal pad, distant stellar wind, soft resonant hum',
      ui_clicks: 'light crystalline chime, airy tap',
    },
    ui_structure: {
      menu_position: 'left',
      border_radius: '12px',
      glass_opacity: 0.12,
      shadow_intensity: 'soft',
      light_angle: '45deg',
      time_of_day_sync: false,
      animation_style: 'drift',
      ornamentation: 'glowing-edges',
    },
  },
];

// ── Component ──────────────────────────────────────────────────────────────
export default function ThemeMachineTab() {
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [terminalOutput, setTerminalOutput] = useState<string[]>([]);
  const [activeThemeId, setActiveThemeId] = useState('Obsidian Glass Archive');
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [applying, setApplying] = useState(false);
  const [galleryThemes, setGalleryThemes] = useState<any[]>(THEMES);
  
  useEffect(() => {
    fetch('/api/themes')
      .then(res => {
        if (!res.ok) throw new Error(`themes HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (data && Array.isArray(data.themes)) {
          setGalleryThemes(data.themes);
        }
      })
      .catch(err => console.error('Failed to load gallery', err));
  }, []);

  // Auto-apply on mount — look up in galleryThemes (which /api/themes may
  // have replaced), fall back to the static THEMES entry.
  useEffect(() => {
    const theme = (galleryThemes.find(t => t.theme_name === activeThemeId) ||
                   THEMES.find(t => t.theme_name === activeThemeId)) as MasterTheme | undefined;
    if (theme) applyMasterTheme(theme, { sound: false }); // no sound until user enables
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleThemeClick = async (theme: MasterTheme) => {
    if (applying) return;
    setApplying(true);
    setActiveThemeId(theme.theme_name);
    
    // Broadcast to systemic FoveAI ecosystem
    try {
      fetch('/api/theme/set_active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(theme)
      });
    } catch (e) { console.error("Global theme push failed:", e); }

    setTerminalOutput(prev => [
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
    ].filter(Boolean) as string[]);
    
    try {
      const applied = await applyMasterTheme(theme, { sound: soundEnabled });
      setTerminalOutput(prev => [
        ...prev,
        applied.background_image_url
          ? `✅ Background image applied!`
          : `⚠️ Background generation unavailable (creative_service offline) — using gradient overlay`,
        ``,
        `✨ ${theme.theme_name} fully live.`,
      ]);
    } catch (e: any) {
      setTerminalOutput(prev => [...prev, `ERROR: ${e.message}`]);
    } finally {
      setApplying(false);
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) { setImageFile(file); setImagePreview(URL.createObjectURL(file)); }
  };

  const handleGenerate = async () => {
    if (!imageFile) return;
    setIsProcessing(true);
    setTerminalOutput(['🧠 Uploading image to Master Webdesigner (120K context)...']);
    const formData = new FormData();
    formData.append('file', imageFile);
    try {
      const res = await fetch('/api/theme/generate', { method: 'POST', body: formData });
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let fullText = '';
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value);
          fullText += chunk;
          setTerminalOutput(prev => [...prev, chunk]);
        }
      }
      // Try to parse the generated theme JSON and auto-apply it
      if (fullText.includes("___FOVEAI_THEME_JSON_START___")) {
        try {
          const jsonStr = fullText.split("___FOVEAI_THEME_JSON_START___")[1];
          const parsed = JSON.parse(jsonStr) as MasterTheme;
          setTerminalOutput(prev => [...prev, '', '🚀 Applying generated theme to UI...']);
          // WebSocket handles the CSS application now
          await handleThemeClick(parsed);
        } catch (e) {
          console.error("JSON parse failed:", e);
        }
      }
    } catch (err: any) {
      setTerminalOutput(prev => [...prev, `ERROR: ${err.message}`]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 300px',
      gridTemplateRows: 'auto 1fr',
      gap: '20px', padding: '24px',
      height: '100%', boxSizing: 'border-box',
      color: 'var(--fv-text, #e6edf3)',
    }}>

      {/* ── Header ── */}
      <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ fontSize: '2rem' }}>🎨</div>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.4rem', color: 'var(--fv-accent, #5eead4)', letterSpacing: '0.05em' }}>
              Master Webdesigner
            </h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--fv-muted, #93a1b0)', marginTop: '2px' }}>
              Drop image → AI plans → Glass panels · Background imagery · Sound · Animations applied live
            </div>
          </div>
        </div>

        {/* Sound toggle */}
        <button onClick={() => {
          const next = !soundEnabled;
          setSoundEnabled(next);
          if (!next) stopAmbientLoop();
          else {
            const theme = THEMES.find(t => t.theme_name === activeThemeId);
            if (theme?.generative_audio) startAmbientLoop(theme.generative_audio.ambient_loop_prompt);
          }
        }} style={{
          background: soundEnabled ? 'var(--fv-accent, #5eead4)' : 'rgba(255,255,255,0.07)',
          color: soundEnabled ? '#000' : 'var(--fv-muted, #93a1b0)',
          border: '1px solid var(--fv-border, rgba(255,255,255,0.1))',
          borderRadius: '8px', padding: '8px 16px',
          cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem',
          transition: 'all 0.2s ease',
        }}>
          {soundEnabled ? '🔊 Sound ON' : '🔇 Sound OFF'}
        </button>
      </div>

      {/* ── Left: Upload + Terminal ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minHeight: 0 }}>
        {/* Drop Zone */}
        <div
          onDragOver={e => e.preventDefault()} onDrop={handleFileDrop}
          onClick={() => document.getElementById('theme-upload')?.click()}
          style={{
            border: `2px dashed var(--fv-border-strong, rgba(255,255,255,0.2))`,
            borderRadius: '12px', padding: imagePreview ? '12px' : '28px',
            textAlign: 'center', background: 'var(--fv-surface, rgba(255,255,255,0.04))',
            cursor: 'pointer', transition: 'all 0.3s ease',
          }}
        >
          <input id="theme-upload" type="file" accept="image/*" style={{ display: 'none' }}
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) { setImageFile(file); setImagePreview(URL.createObjectURL(file)); }
            }}
          />
          {imagePreview
            ? <img src={imagePreview} alt="Preview" style={{ maxHeight: '130px', borderRadius: '8px', objectFit: 'cover' }} />
            : <>
                <div style={{ fontSize: '2.5rem', marginBottom: '8px' }}>🖼️</div>
                <div style={{ fontWeight: 600 }}>Drop a source image here</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--fv-muted, #93a1b0)', marginTop: '6px' }}>
                  AI extracts forms, textures, mood → builds Full Theme Blueprint
                </div>
              </>
          }
        </div>

        <button onClick={handleGenerate} disabled={!imageFile || isProcessing} style={{
          padding: '11px 20px',
          background: isProcessing || !imageFile ? 'rgba(255,255,255,0.06)' : 'var(--fv-accent, #5eead4)',
          color: isProcessing || !imageFile ? 'var(--fv-muted, #93a1b0)' : '#000',
          border: 'none', borderRadius: '8px', fontWeight: 'bold', fontSize: '0.95rem',
          cursor: isProcessing || !imageFile ? 'not-allowed' : 'pointer',
          transition: 'all 0.2s ease',
          boxShadow: !isProcessing && imageFile ? '0 0 20px var(--fv-accent, #5eead4)44' : 'none',
        }}>
          {isProcessing ? '⏳ Master Webdesigner thinking...' : '✨ Generate Theme Blueprint'}
        </button>

        {/* Terminal */}
        <div style={{
          flex: 1, minHeight: '200px',
          background: '#05070a',
          border: '1px solid var(--fv-border, rgba(255,255,255,0.08))',
          borderRadius: '10px', padding: '14px',
          fontFamily: 'monospace', fontSize: '0.82rem',
          overflowY: 'auto', color: '#a3b4c8',
          boxShadow: 'inset 0 4px 16px rgba(0,0,0,0.6)',
        }}>
          {terminalOutput.length === 0
            ? <div style={{ color: 'var(--fv-muted, #93a1b0)', fontStyle: 'italic' }}>
                Click a theme card → watch it apply live.<br/>
                Or drop an image and generate a brand new theme.
              </div>
            : terminalOutput.map((line, i) =>
                <div key={i} style={{
                  whiteSpace: 'pre-wrap',
                  color: line.startsWith('✅') ? '#4ade80'
                    : line.startsWith('❌') || line.startsWith('ERROR') ? '#f87171'
                    : line.startsWith('⚠️') ? '#fbbf24'
                    : '#a3b4c8'
                }}>{line}</div>
              )
          }
        </div>
      </div>

      {/* ── Right: Theme Gallery ── */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: '12px',
        overflowY: 'auto',
        background: 'var(--fv-surface, rgba(255,255,255,0.03))',
        border: '1px solid var(--fv-border-strong, rgba(255,255,255,0.1))',
        borderRadius: '12px', padding: '16px',
      }}>
        <h3 style={{ margin: '0 0 8px 0', fontSize: '0.85rem', letterSpacing: '0.12em',
          textTransform: 'uppercase', color: 'var(--fv-muted, #93a1b0)' }}>
          Theme Gallery
        </h3>

        {galleryThemes.map(galleryItem => {
          const theme = galleryItem.theme_data || galleryItem;
          const prov = galleryItem.theme_data ? galleryItem : null;
          const isPaused = prov && prov.status && prov.status.startsWith('paused');
          const isActive = theme.theme_name === activeThemeId;
          const isHovered = theme.theme_name === hoveredId;
          // Extract color swatches from palette — rendered as CSS in the card
          const swatches = [theme.fv_accent, theme.fv_accent_2, theme.fv_warn, theme.fv_danger];
          void swatches;
          return (
            <div key={theme.theme_name}
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
                  ({prov && typeof prov.description === 'string' ? prov.description.split(' ').slice(0, 5).join(' ') + '...' : 'System Placeholder'})
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
            </div>
          );
        })}

        {/* Add new slot */}
        <div style={{
          marginTop: '4px', padding: '12px',
          border: '1px dashed var(--fv-border, rgba(255,255,255,0.08))',
          borderRadius: '10px', textAlign: 'center',
          color: 'var(--fv-muted, #93a1b0)', fontSize: '0.78rem',
        }}>
          + Drop image → Generate Blueprint<br/>
          <span style={{ fontSize: '0.68rem', opacity: 0.6 }}>New card appears here automatically</span>
        </div>
      </div>
    </div>
  );
}
