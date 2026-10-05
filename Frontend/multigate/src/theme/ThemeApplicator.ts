/**
 * ThemeApplicator.ts
 * ─────────────────────────────────────────────────────────────────────────
 * Takes a fully-parsed Master Webdesigner JSON theme object and applies
 * EVERY aspect to the live DOM: background imagery, glass panels, layout
 * restructuring, animation classes, Web Audio click sounds, ambient loops,
 * and CSS variable injection.
 *
 * Called after ThemeMachineTab receives the streaming JSON from theme_api.py.
 */

// ── Types ──────────────────────────────────────────────────────────────────
export interface ThemeAudioSpec {
  ambient_loop_prompt: string;
  ui_clicks: string; // e.g. "heavy metallic clank"
}

export interface ThemeUIStructure {
  menu_position: 'left' | 'right' | 'bottom' | 'top' | 'floating-center';
  border_radius: string;
  glass_opacity: number;
  shadow_intensity: 'soft' | 'medium' | 'hard' | 'glowing';
  light_angle: string;
  time_of_day_sync: boolean;
  animation_style: 'fluid-spring' | 'snap' | 'breathe' | 'drift';
  ornamentation: 'minimal' | 'cyber-lines' | 'baroque-tech' | 'glowing-edges';
}

export interface MasterTheme {
  theme_name: string;
  fv_accent: string;
  fv_accent_2: string;
  fv_ok: string;
  fv_warn: string;
  fv_danger: string;
  background_prompt: string;
  background_image_url?: string;  // filled in after generation
  generative_audio?: ThemeAudioSpec;
  functional_aspects?: string;
  ui_structure: ThemeUIStructure;
}

// ── Web Audio Engine ───────────────────────────────────────────────────────
let audioCtx: AudioContext | null = null;
let ambientSource: AudioBufferSourceNode | null = null;
let ambientGain: GainNode | null = null;

function getAudioCtx(): AudioContext {
  if (!audioCtx) audioCtx = new AudioContext();
  return audioCtx;
}

/**
 * Plays a procedural click sound based on the theme's ui_clicks description.
 * Pure Web Audio — no external files needed.
 */
export function playClickSound(style: string = 'glass tap') {
  const ctx = getAudioCtx();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const filter = ctx.createBiquadFilter();

  // Tune click character from theme description
  const isMetallic = /metal|clank|steel|forge/.test(style.toLowerCase());
  const isGlass = /glass|crystal|chime|tap/.test(style.toLowerCase());

  osc.type = isMetallic ? 'sawtooth' : 'sine';
  osc.frequency.setValueAtTime(isMetallic ? 180 : 880, ctx.currentTime);
  osc.frequency.exponentialRampToValueAtTime(isMetallic ? 40 : 220, ctx.currentTime + 0.12);

  filter.type = 'bandpass';
  filter.frequency.value = isGlass ? 2400 : 600;
  filter.Q.value = isGlass ? 8 : 3;

  gain.gain.setValueAtTime(0.35, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + (isMetallic ? 0.18 : 0.08));

  osc.connect(filter);
  filter.connect(gain);
  gain.connect(ctx.destination);

  osc.start(ctx.currentTime);
  osc.stop(ctx.currentTime + 0.2);
}

/**
 * Generates a procedural ambient drone based on the theme's audio prompt.
 * Reads keywords and selects appropriate frequencies/waveforms.
 */
export function startAmbientLoop(prompt: string) {
  stopAmbientLoop();
  const ctx = getAudioCtx();

  const isDark = /dark|deep|subterranean|void|abyss/.test(prompt);
  const isCosmic = /cosmic|space|stellar|nebula/.test(prompt);
  const isIndustrial = /industrial|mechanical|forge|steam/.test(prompt);

  ambientGain = ctx.createGain();
  ambientGain.gain.setValueAtTime(0, ctx.currentTime);
  ambientGain.gain.linearRampToValueAtTime(0.12, ctx.currentTime + 3);

  const masterFilter = ctx.createBiquadFilter();
  masterFilter.type = 'lowpass';
  masterFilter.frequency.value = isDark ? 400 : isCosmic ? 800 : 600;

  // Layer 1: Sub-bass drone
  const drone = ctx.createOscillator();
  drone.type = 'sine';
  drone.frequency.value = isDark ? 42 : isCosmic ? 55 : 65;
  const droneGain = ctx.createGain();
  droneGain.gain.value = 0.6;
  drone.connect(droneGain);
  droneGain.connect(masterFilter);

  // Layer 2: Mid harmonic
  const mid = ctx.createOscillator();
  mid.type = 'triangle';
  mid.frequency.value = drone.frequency.value * (isIndustrial ? 3 : 4);
  const midGain = ctx.createGain();
  midGain.gain.value = 0.15;
  mid.connect(midGain);
  midGain.connect(masterFilter);

  // Layer 3: Noise texture (industrial static / cosmic hiss)
  const bufSize = ctx.sampleRate * 2;
  const noiseBuffer = ctx.createBuffer(1, bufSize, ctx.sampleRate);
  const data = noiseBuffer.getChannelData(0);
  for (let i = 0; i < bufSize; i++) data[i] = (Math.random() * 2 - 1) * 0.08;
  const noiseSource = ctx.createBufferSource();
  noiseSource.buffer = noiseBuffer;
  noiseSource.loop = true;
  const noiseFilter = ctx.createBiquadFilter();
  noiseFilter.type = isIndustrial ? 'bandpass' : 'highpass';
  noiseFilter.frequency.value = isIndustrial ? 800 : 4000;
  noiseSource.connect(noiseFilter);
  noiseFilter.connect(masterFilter);

  masterFilter.connect(ambientGain!);
  ambientGain!.connect(ctx.destination);

  drone.start();
  mid.start();
  noiseSource.start();

  ambientSource = drone; // track for stopping
}

export function stopAmbientLoop() {
  if (ambientGain) {
    ambientGain.gain.linearRampToValueAtTime(0, (audioCtx?.currentTime ?? 0) + 1.5);
  }
  setTimeout(() => {
    try { ambientSource?.stop(); } catch (e) {}
  }, 1600);
}

// ── CSS Variable Injection ─────────────────────────────────────────────────
function injectThemeVariables(theme: MasterTheme) {
  const s = theme.ui_structure;
  const root = document.documentElement;

  // Core palette
  root.style.setProperty('--fv-accent', theme.fv_accent);
  root.style.setProperty('--fv-accent-2', theme.fv_accent_2);
  root.style.setProperty('--fv-ok', theme.fv_ok);
  root.style.setProperty('--fv-warn', theme.fv_warn);
  root.style.setProperty('--fv-danger', theme.fv_danger);
  root.style.setProperty('--fv-accent-dim', theme.fv_accent + '22');
  root.style.setProperty('--fv-violet-dim', theme.fv_accent_2 + '22');

  // Structure
  root.style.setProperty('--fv-radius', s.border_radius);
  root.style.setProperty('--fv-light-angle', s.light_angle);
  root.style.setProperty('--fv-animation-style', s.animation_style);
  root.style.setProperty('--fv-ornamentation', s.ornamentation);

  // Glass surfaces built from opacity
  const op = s.glass_opacity;
  root.style.setProperty('--fv-surface', `rgba(148, 163, 184, ${op})`);
  root.style.setProperty('--fv-surface-2', `rgba(148, 163, 184, ${op + 0.06})`);
  root.style.setProperty('--fv-glass-top', `linear-gradient(${s.light_angle}, rgba(255,255,255,${op * 0.25}), rgba(255,255,255,${op * 0.07}))`);
  root.style.setProperty('--fv-glass-card', `linear-gradient(${s.light_angle}, rgba(255,255,255,${op * 0.15}), rgba(255,255,255,${op * 0.04}))`);
  root.style.setProperty('--fv-border', `rgba(148, 163, 184, ${op * 0.4})`);
  root.style.setProperty('--fv-border-strong', `rgba(148, 163, 184, ${op * 0.8})`);

  // Shadow intensity
  const shadowMap = {
    soft: `0 4px 24px rgba(0,0,0,0.3), var(--fv-inset-hi)`,
    medium: `0 8px 32px rgba(0,0,0,0.5), var(--fv-inset-hi)`,
    hard: `0 12px 48px rgba(0,0,0,0.8), var(--fv-inset-hi)`,
    glowing: `0 0 40px ${theme.fv_accent}55, 0 12px 48px rgba(0,0,0,0.8), var(--fv-inset-hi)`,
  };
  root.style.setProperty('--fv-shadow', shadowMap[s.shadow_intensity]);
  root.style.setProperty('--fv-inset-hi', `inset 0 1px 0 rgba(255,255,255,0.09)`);
  root.style.setProperty('--fv-inset-press', `inset 0 2px 6px rgba(0,0,0,0.45)`);
}

// ── Background Image ───────────────────────────────────────────────────────
function applyBackgroundImage(url: string) {
  const body = document.body;
  body.style.backgroundImage = `url('${url}')`;
  body.style.backgroundSize = 'cover';
  body.style.backgroundPosition = 'center';
  body.style.backgroundAttachment = 'fixed';
}

// ── Glassmorphic Panel Injection ───────────────────────────────────────────
function injectGlassStyles(theme: MasterTheme) {
  const existing = document.getElementById('foveai-glass-injection');
  if (existing) existing.remove();

  const s = theme.ui_structure;
  const op = s.glass_opacity;
  const blur = '8px'; // Forced down from 24px to prevent GPU/browser render freezes
  const accent = theme.fv_accent;
  const isGlowing = s.shadow_intensity === 'glowing';

  const css = `
    /* ── MASTER WEBDESIGNER: ${theme.theme_name} ── */

    /* Full-page atmospheric background overlay */
    #root::before {
      content: '';
      position: fixed; inset: 0; z-index: -1;
      background: linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.85) 100%);
      pointer-events: none;
    }

    /* Sidebar glass panel */
    .sidebar {
      background: rgba(0,0,0,${0.4 + op * 0.4}) !important;
      -webkit-backdrop-filter: blur(${blur}) saturate(180%) !important;
      backdrop-filter: blur(${blur}) saturate(180%) !important;
      border-right: 1px solid ${accent}33 !important;
      box-shadow: ${isGlowing ? `4px 0 40px ${accent}22` : '4px 0 20px rgba(0,0,0,0.5)'} !important;
    }

    /* Top header glass */
    .chat-header {
      background: rgba(0,0,0,${0.35 + op * 0.35}) !important;
      -webkit-backdrop-filter: blur(${blur}) !important;
      backdrop-filter: blur(${blur}) !important;
      border-bottom: 1px solid ${accent}44 !important;
    }

    /* Main content area */
    .main-content {
      background: transparent !important;
    }

    /* Ornamentation: glowing accent line along sidebar top */
    .sidebar::after {
      content: '';
      position: absolute; top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, ${accent}, ${theme.fv_accent_2}, transparent);
      opacity: ${isGlowing ? 0.9 : 0.4};
    }

    /* Nav item hover glow */
    .nav-item:hover, .nav-item.active {
      background: ${accent}18 !important;
      border-left: 2px solid ${accent} !important;
      box-shadow: ${isGlowing ? `inset 0 0 20px ${accent}22` : 'none'} !important;
    }

    /* Input fields */
    input, textarea {
      background: rgba(0,0,0,0.4) !important;
      border: 1px solid ${accent}44 !important;
      backdrop-filter: blur(8px) !important;
    }
    input:focus, textarea:focus {
      border-color: ${accent}99 !important;
      box-shadow: 0 0 0 2px ${accent}22 !important;
    }

    /* Buttons */
    button:not(:disabled) {
      transition: all 0.2s ease !important;
    }
    button:not(:disabled):hover {
      box-shadow: 0 0 20px ${accent}44 !important;
      transform: translateY(-1px) !important;
    }

    /* Animation: breathe */
    ${s.animation_style === 'breathe' ? `
    .sidebar-brand, .chat-header h3 {
      animation: fv-breathe 4s ease-in-out infinite;
    }
    @keyframes fv-breathe {
      0%, 100% { opacity: 1; text-shadow: 0 0 8px ${accent}66; }
      50% { opacity: 0.75; text-shadow: 0 0 24px ${accent}cc; }
    }` : ''}

    /* Animation: drift — subtle background pan */
    ${s.animation_style === 'drift' ? `
    body {
      animation: fv-drift 30s ease-in-out infinite alternate;
    }
    @keyframes fv-drift {
      0% { background-position: 50% 50%; }
      100% { background-position: 55% 45%; }
    }` : ''}

    /* Ornamentation: cyber-lines */
    ${s.ornamentation === 'cyber-lines' ? `
    .sidebar::before {
      content: '';
      position: absolute; inset: 0;
      background: repeating-linear-gradient(
        0deg, transparent, transparent 40px,
        ${accent}08 40px, ${accent}08 41px
      );
      pointer-events: none;
    }` : ''}

    /* Ornamentation: glowing-edges */
    ${s.ornamentation === 'glowing-edges' ? `
    .sidebar, .chat-header {
      box-shadow: 0 0 30px ${accent}33, inset 0 0 30px rgba(0,0,0,0.3) !important;
    }` : ''}

    /* Scrollbars */
    ::-webkit-scrollbar { width: 4px; background: transparent; }
    ::-webkit-scrollbar-thumb { background: ${accent}55; border-radius: 2px; }
    ::-webkit-scrollbar-thumb:hover { background: ${accent}99; }
  `;

  const style = document.createElement('style');
  style.id = 'foveai-glass-injection';
  style.textContent = css;
  document.head.appendChild(style);
}

// ── Time-of-Day Light Sync ─────────────────────────────────────────────────
let timeOfDayInterval: ReturnType<typeof setInterval> | null = null;

function startTimeOfDaySync() {
  stopTimeOfDaySync();
  const update = () => {
    const now = new Date();
    const hours = now.getHours() + now.getMinutes() / 60;
    // Map 0-24h to 0-360deg. Dawn ~6h = 90deg, Noon ~12h = 180deg, Dusk ~18h = 270deg
    const angle = Math.round((hours / 24) * 360);
    document.documentElement.style.setProperty('--fv-light-angle', `${angle}deg`);
  };
  update();
  timeOfDayInterval = setInterval(update, 60_000); // update every minute
}

function stopTimeOfDaySync() {
  if (timeOfDayInterval) { clearInterval(timeOfDayInterval); timeOfDayInterval = null; }
}

// ── Click Sound Wiring ─────────────────────────────────────────────────────
let clickStyle = 'glass tap';
let clickListenerAttached = false;

function attachClickSounds(style: string) {
  clickStyle = style;
  if (!clickListenerAttached) {
    document.addEventListener('click', () => playClickSound(clickStyle));
    clickListenerAttached = true;
  }
}

// ── MAIN APPLICATOR ────────────────────────────────────────────────────────
export async function applyMasterTheme(theme: MasterTheme, options = { sound: true }) {
  console.log(`🎨 Applying theme: ${theme.theme_name}`);

  // 1. CSS variables
  injectThemeVariables(theme);

  // 2. Full glassmorphic panel injection
  injectGlassStyles(theme);

  // 3. Background image (if already generated) or request generation
  if (theme.background_image_url) {
    applyBackgroundImage(theme.background_image_url);
  } else if (theme.background_prompt) {
    // Request image generation from creative_service.py
    try {
      const res = await fetch('/api/dream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: theme.background_prompt,
          negative_prompt: 'blurry, low quality, text, watermark, cartoon',
          width: 1920, height: 1080,
          steps: 28, cfg_scale: 7.5,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.image_url) {
          applyBackgroundImage(data.image_url);
          theme.background_image_url = data.image_url;
        }
      }
    } catch (err) {
      console.warn('Background image generation unavailable:', err);
    }
  }

  // 4. Time-of-day sync
  if (theme.ui_structure.time_of_day_sync) {
    startTimeOfDaySync();
  } else {
    stopTimeOfDaySync();
  }

  // 5. Audio
  if (options.sound && theme.generative_audio) {
    attachClickSounds(theme.generative_audio.ui_clicks);
    startAmbientLoop(theme.generative_audio.ambient_loop_prompt);
  }

  // 6. Announce
  console.log(`✅ Theme "${theme.theme_name}" fully applied.`);
  return theme;
}
