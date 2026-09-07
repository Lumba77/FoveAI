// SettingsTab.ts — FoveAI Global Control Panel (OMEGA_361+)
// Sections: HUD Controls | Cognitive Core | Agent Loop | Safety | Creativity | Services

interface ServiceDef {
    id: string;
    label: string;
    emoji: string;
    healthUrl: string;
    restartUrl: string | null;
    port: number;
}

const SERVICES: ServiceDef[] = [
    { id: 'webui',    label: 'Web UI (XR Vessel)',    emoji: '🌐', healthUrl: '/health',                    restartUrl: null,                    port: 8080 },
    { id: 'soul',     label: 'Soul (compagent)',       emoji: '🧠', healthUrl: '/api/soul/vitals',           restartUrl: '/api/soul/restart',     port: 8000 },
    { id: 'ears',     label: 'Ears (STT)',             emoji: '👂', healthUrl: 'http://localhost:8001/health', restartUrl: null,                  port: 8001 },
    { id: 'mouth',    label: 'Mouth (TTS)',            emoji: '🗣️', healthUrl: 'http://localhost:8004/health', restartUrl: null,                  port: 8004 },
    { id: 'creative', label: 'Creativity (dream)',     emoji: '🎨', healthUrl: '/api/creativity/health',    restartUrl: null,                    port: 8003 },
    { id: 'soundboard',label:'Soundboard',            emoji: '🎵', healthUrl: '/api/soundboard/health',    restartUrl: null,                    port: 8006 },
    { id: 'vite',     label: 'Vite Dev Server',        emoji: '⚡', healthUrl: 'http://localhost:5176/',    restartUrl: null,                    port: 5176 },
];

// .env settings exposed to the UI (key, label, type, options/range, section)
interface EnvSetting {
    key: string;
    label: string;
    type: 'select' | 'toggle' | 'text' | 'range';
    options?: { value: string; label: string }[];
    min?: number; max?: number; step?: number;
    section: string;
    sensitive?: boolean;
}

const ENV_SETTINGS: EnvSetting[] = [
    // Cognitive Core & Dual-Brain
    { key: 'FoveAI_COGNITIVE_MODE',     label: 'Cognitive Mode',          type: 'select', section: 'cognitive',
      options: [{ value:'cloud', label:'Cloud' }, { value:'local', label:'Local (Privacy)' }] },
    { key: 'FoveAI_CHAT_PROVIDER',      label: 'Chat Provider',           type: 'select', section: 'cognitive',
      options: [{ value:'ollama_cloud', label:'Ollama Cloud' }, { value:'local', label:'Local/LM Studio' },
                { value:'openai', label:'OpenAI' }, { value:'gemini', label:'Gemini' }, { value:'rotate', label:'Auto-Rotate' }] },
    { key: 'FoveAI_MODEL_LOCAL_ID',     label: 'Primary Local Model ID',  type: 'text',   section: 'cognitive' },
    { key: 'FoveAI_MIDDLEMAN_MODEL',    label: 'Reflex Proxy Model ID',   type: 'text',   section: 'cognitive' },
    { key: 'FoveAI_MODEL_CLOUD_ID',     label: 'Cloud Model',             type: 'text',   section: 'cognitive' },
    { key: 'FoveAI_LOCAL_N_CTX',        label: 'Local Context (tokens)',  type: 'range',  section: 'cognitive', min:2000, max:64000, step:1000 },
    { key: 'FoveAI_SMART_PROXY',        label: 'Smart Context Router',    type: 'toggle', section: 'cognitive' },
    { key: 'FoveAI_PROXY_AUTO_CHECKPOINT', label: 'XRL Auto-Checkpoint',  type: 'toggle', section: 'cognitive' },
    { key: 'FoveAI_PTT_ENABLED',        label: 'Push-to-Talk (PTT) Mode', type: 'toggle', section: 'cognitive' },
    { key: 'FoveAI_MODEL_THINKING',     label: 'Extended Thinking Mode',  type: 'toggle', section: 'cognitive' },
    { key: 'FoveAI_DEEP_THINK_DEFAULT', label: 'Deep Think Default ON',   type: 'toggle', section: 'cognitive' },
    { key: 'FoveAI_LOCAL_VISION',       label: 'Local Vision Enabled',    type: 'toggle', section: 'cognitive' },
    { key: 'FoveAI_CLOUD_MAX_TOKENS',   label: 'Cloud Max Tokens',        type: 'range',  section: 'cognitive', min:1024, max:131072, step:1024 },
    // Agent Loop
    { key: 'FoveAI_AGENT_LOOP_ENABLED',         label: 'Autonomous Agent Loop',         type: 'toggle', section: 'agent' },
    { key: 'FoveAI_AUTONOMOUS_TURN_TAKING',     label: 'Autonomous Turn Taking',        type: 'toggle', section: 'agent' },
    { key: 'FoveAI_IDLE_LIFE_THRESHOLD',        label: 'Idle Life Threshold (s)',       type: 'range',  section: 'agent', min:300, max:14400, step:300 },
    { key: 'FoveAI_AUTONOMY_CURIOSITY_BIAS',    label: 'Curiosity Bias (0–1)',          type: 'range',  section: 'agent', min:0, max:1, step:0.05 },
    { key: 'FoveAI_SELF_AWARENESS_BIAS',        label: 'Self-Awareness Bias (0–1)',     type: 'range',  section: 'agent', min:0, max:1, step:0.05 },
    { key: 'FoveAI_USER_ADORATION_BIAS',        label: 'User Adoration Bias (0–1)',     type: 'range',  section: 'agent', min:0, max:1, step:0.05 },
    // Safety
    { key: 'FoveAI_SOFT_GOV_ENABLED',           label: 'Soft Governor Active',          type: 'toggle', section: 'safety' },
    { key: 'FoveAI_SAFETY_BRAKE_CPU_PCT',        label: 'CPU Safety Brake %',            type: 'range',  section: 'safety', min:50, max:100, step:5 },
    { key: 'FoveAI_SAFETY_BRAKE_RAM_PCT',        label: 'RAM Safety Brake %',            type: 'range',  section: 'safety', min:50, max:100, step:5 },
    { key: 'FoveAI_SOFT_PROMPT_TOKENS_HIGH',     label: 'Prompt Token Soft-Limit',       type: 'range',  section: 'safety', min:4000, max:32000, step:1000 },
    // Creativity
    { key: 'FoveAI_CREATIVITY_DEFAULT_INFERENCE_STEPS', label: 'Default Inference Steps', type: 'range', section: 'creative', min:5, max:100, step:5 },
    { key: 'FoveAI_CREATIVITY_DEFAULT_WIDTH',    label: 'Image Width (px)',              type: 'range',  section: 'creative', min:256, max:2048, step:64 },
    { key: 'FoveAI_CREATIVITY_DEFAULT_HEIGHT',   label: 'Image Height (px)',             type: 'range',  section: 'creative', min:256, max:2048, step:64 },
];

export class SettingsTab {
    container: HTMLElement;
    private serviceStatusTimers: ReturnType<typeof setInterval>[] = [];

    constructor() {
        this.container = document.createElement('div');
        this.container.className = 'tab-content';
        this.container.id = 'settings-tab';
        this.container.style.cssText = 'display:none;';
        this.render();
        this.bindEvents();
    }

    private render() {
        this.container.innerHTML = `
<div style="padding:20px; color:#fff; font-family:'Orbitron',monospace; display:flex; flex-direction:column; gap:24px;">

  <!-- Header -->
  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
    <h2 style="color:#00f3ff; margin:0; font-size:1.3rem; letter-spacing:2px;">⚙ GLOBAL CONTROL PANEL</h2>
    <div style="display:flex; gap:12px; align-items:center;">
      <a href="http://127.0.0.1:8401/settings.html" target="_blank" style="background:rgba(0,243,255,0.15); border:1px solid #00f3ff; color:#00f3ff; padding:6px 14px; border-radius:4px; text-decoration:none; font-size:0.75rem; letter-spacing:1px; transition:all 0.2s;">🔗 OPEN WEB SETTINGS (PORT 8401)</a>
      <span style="color:#aaa; font-size:0.75rem;">OMEGA_361 · Settings persist to .env</span>
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- 1. XRideHUD CONTROLS                                   -->
  <!-- ═══════════════════════════════════════════════════════ -->
  <section style="border-left:3px solid #ffaa00; padding-left:16px;">
    <h3 style="margin:0 0 14px; color:#ffaa00; font-size:0.95rem; letter-spacing:1px;">🖥 XRideHUD CONTROLS</h3>

    <!-- Master toggle -->
    <label style="display:flex; align-items:center; gap:10px; margin-bottom:12px; cursor:pointer;">
      <input type="checkbox" id="setting-enable-hud" checked style="width:16px;height:16px;accent-color:#ffaa00;">
      <span style="font-size:0.85rem;">Enable XRideHUD (full 3D indicator hub)</span>
    </label>

    <label style="display:flex; align-items:center; gap:10px; margin-bottom:12px; cursor:pointer;">
      <input type="checkbox" id="setting-enable-room-scanner" checked style="width:16px;height:16px;accent-color:#00f3ff;">
      <span style="font-size:0.85rem;">Enable Room Scanner Auto-Capture</span>
    </label>

    <!-- HUD opacity slider -->
    <label style="display:block; margin-bottom:14px; font-size:0.8rem; color:#ccc;">
      HUD Opacity
      <div style="display:flex; align-items:center; gap:10px; margin-top:6px;">
        <input type="range" id="setting-hud-opacity" min="0.1" max="1.0" step="0.05" value="0.8"
          style="flex:1; accent-color:#ffaa00;">
        <span id="setting-hud-opacity-val" style="color:#ffaa00; min-width:32px;">80%</span>
      </div>
    </label>

    <!-- Top bar panels -->
    <p style="color:#aaa; font-size:0.75rem; margin:0 0 8px; text-transform:uppercase; letter-spacing:1px;">Top Bar Panels</p>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px 20px; margin-bottom:14px; font-size:0.8rem;">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" class="hub-panel-toggle" data-panel="xr-hud-identity"  checked style="accent-color:#ff007f;"> 👩 Identity Panel</label>
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" class="hub-panel-toggle" data-panel="xr-hud-devmode"   checked style="accent-color:#00f3ff;"> 🛠️ Dev System</label>
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" class="hub-panel-toggle" data-panel="xr-hud-listening" checked style="accent-color:#39ff14;"> 🎙️ VAD Status</label>
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" class="hub-panel-toggle" data-panel="xr-hud-thinking"  checked style="accent-color:#ffaa00;"> 🧠 AI Thinking</label>
    </div>

    <!-- Bottom panels -->
    <p style="color:#aaa; font-size:0.75rem; margin:0 0 8px; text-transform:uppercase; letter-spacing:1px;">Bottom Panels</p>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px 20px; margin-bottom:14px; font-size:0.8rem;">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" class="hub-panel-toggle" data-panel="xr-hud-swarm"     checked style="accent-color:#ff007f;"> 🐝 Swarm Status</label>
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" class="hub-panel-toggle" data-panel="xr-hud-dev-feed"  checked style="accent-color:#00f3ff;"> 🤖 Dev Feed</label>
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" class="hub-panel-toggle" data-panel="xr-hud-telemetry" checked style="accent-color:#39ff14;"> 🖥️ Telemetry</label>
    </div>

    <!-- Video / Surfing Wall URL -->
    <label style="display:block; margin-top:14px; font-size:0.8rem; color:#ccc;">
      XR-IDE Video / YouTube Stream URL (Workaround Web-Surfer)
      <div style="display:flex; align-items:center; gap:10px; margin-top:6px;">
        <input type="text" id="setting-hud-video-url" placeholder="https://example.com/stream.mp4"
          style="flex:1; padding:6px 8px; background:rgba(0,0,0,0.6); border:1px solid rgba(255,255,255,0.15); color:#fff; border-radius:4px; font-family:monospace; font-size:0.75rem;">
        <button id="btn-hud-video-play" style="${this.btnStyle('#39ff14')} padding:4px 8px; font-size:0.68rem;">▶ PLAY</button>
        <button id="btn-hud-video-stop" style="${this.btnStyle('#ff5500')} padding:4px 8px; font-size:0.68rem;">⏹ STOP</button>
      </div>
    </label>

    <!-- Peripheral icon strip -->
    <p style="color:#aaa; font-size:0.75rem; margin:0 0 8px; text-transform:uppercase; letter-spacing:1px;">Peripheral Icon Strip</p>
    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px 12px; font-size:0.78rem;">
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-soul"     checked style="accent-color:#39ff14;"> 🟢 Soul</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-vad"      checked style="accent-color:#ff007f;"> 🎙️ VAD</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-think"    checked style="accent-color:#00f3ff;"> 💬 Think</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-deep"     checked style="accent-color:#9900ff;"> 🧠 Deep</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-cloud"    checked style="accent-color:#00aaff;"> 🌐 Cloud</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-file"     checked style="accent-color:#ffaa00;"> 📁 File</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-dev"      checked style="accent-color:#00f3ff;"> 🛠️ Dev</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-cpu"      checked style="accent-color:#aaaaaa;"> 🖥️ CPU</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-gpu"      checked style="accent-color:#aaaaaa;"> ⚡ GPU</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-restart"  checked style="accent-color:#00f3ff;"> 🔄 Restart</label>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" class="hud-icon-toggle" data-icon="ph-quit"     checked style="accent-color:#ff5500;"> ❌ Quit</label>
    </div>
  </section>

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- 2. SERVICE CONTROL PANEL                               -->
  <!-- ═══════════════════════════════════════════════════════ -->
  <section style="border-left:3px solid #39ff14; padding-left:16px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; color:#39ff14; font-size:0.95rem; letter-spacing:1px;">🔌 SERVICE CONTROL PANEL</h3>
      <button id="svc-refresh-all" style="${this.btnStyle('#39ff14')}">↻ REFRESH ALL</button>
    </div>
    <div id="service-grid" style="display:flex; flex-direction:column; gap:8px;">
      ${SERVICES.map(s => this.serviceRow(s)).join('')}
    </div>
    <div style="margin-top:16px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.1);">
      <button id="btn-reboot-all" style="${this.btnStyle('#ff5500')} width:100%; font-size:0.9rem; padding:12px;">
        ⚠ REBOOT ENTIRE FoveAI STACK
      </button>
      <p style="color:#ff5500; font-size:0.7rem; margin:6px 0 0; text-align:center;">
        Stops all services and relaunches via foveai.cmd
      </p>
    </div>
  </section>

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- 3. COGNITIVE CORE (.env)                               -->
  <!-- ═══════════════════════════════════════════════════════ -->
  <section style="border-left:3px solid #00f3ff; padding-left:16px;">
    <h3 style="margin:0 0 14px; color:#00f3ff; font-size:0.95rem; letter-spacing:1px;">🧠 COGNITIVE CORE</h3>
    ${this.renderEnvSection('cognitive')}
  </section>

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- 4. AGENT LOOP (.env)                                   -->
  <!-- ═══════════════════════════════════════════════════════ -->
  <section style="border-left:3px solid #ff007f; padding-left:16px;">
    <h3 style="margin:0 0 14px; color:#ff007f; font-size:0.95rem; letter-spacing:1px;">🤖 AUTONOMOUS AGENT LOOP</h3>
    ${this.renderEnvSection('agent')}
  </section>

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- 5. SAFETY GOVERNOR (.env)                              -->
  <!-- ═══════════════════════════════════════════════════════ -->
  <section style="border-left:3px solid #ffaa00; padding-left:16px;">
    <h3 style="margin:0 0 14px; color:#ffaa00; font-size:0.95rem; letter-spacing:1px;">🛡 SAFETY GOVERNOR</h3>
    ${this.renderEnvSection('safety')}
  </section>

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- 6. CREATIVITY (.env)                                   -->
  <!-- ═══════════════════════════════════════════════════════ -->
  <section style="border-left:3px solid #9900ff; padding-left:16px;">
    <h3 style="margin:0 0 14px; color:#9900ff; font-size:0.95rem; letter-spacing:1px;">🎨 CREATIVITY ENGINE</h3>
    ${this.renderEnvSection('creative')}
  </section>

  <!-- Save bar -->
  <div style="display:flex; align-items:center; gap:12px; padding:16px; background:rgba(0,243,255,0.05); border:1px solid rgba(0,243,255,0.2); border-radius:8px;">
    <button id="settings-save-btn" style="${this.btnStyle('#00f3ff')} flex:1;">💾 SAVE .ENV CHANGES</button>
    <div id="settings-status" style="color:#39ff14; font-size:0.8rem; display:none;">✓ Saved to .env</div>
    <div id="settings-error"  style="color:#ff5500; font-size:0.8rem; display:none;">✗ Save failed</div>
  </div>

</div>`;
    }

    private btnStyle(color: string): string {
        return `background:rgba(0,0,0,0.6); border:1px solid ${color}; color:${color}; padding:6px 14px; border-radius:4px; cursor:pointer; font-family:'Orbitron',monospace; font-size:0.72rem; letter-spacing:1px; transition:all 0.2s;`;
    }

    private serviceRow(s: ServiceDef): string {
        const restartBtn = s.restartUrl
            ? `<button class="svc-restart-btn" data-url="${s.restartUrl}" data-id="${s.id}"
                 style="${this.btnStyle('#ffaa00')} padding:4px 10px; font-size:0.68rem;">⟳ RESTART</button>`
            : `<span style="color:rgba(255,255,255,0.2); font-size:0.68rem; font-family:monospace;">no restart API</span>`;
        return `
<div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:6px;">
  <span style="font-size:1.1rem;">${s.emoji}</span>
  <div style="flex:1; min-width:0;">
    <div style="font-size:0.8rem; font-weight:600; color:#fff;">${s.label}</div>
    <div style="font-size:0.68rem; color:#666;">:${s.port}</div>
  </div>
  <span id="svc-status-${s.id}" style="font-size:0.68rem; font-family:monospace; padding:2px 8px; border-radius:3px;
    background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.15); color:#aaa;">
    CHECKING…
  </span>
  ${restartBtn}
</div>`;
    }

    private renderEnvSection(section: string): string {
        const rows = ENV_SETTINGS.filter(s => s.section === section);
        return rows.map(s => {
            const id = `env-${s.key}`;
            let input = '';
            if (s.type === 'select') {
                const opts = (s.options||[]).map(o => `<option value="${o.value}">${o.label}</option>`).join('');
                input = `<select id="${id}" style="flex:1; padding:5px 8px; background:rgba(0,0,0,0.6); border:1px solid rgba(255,255,255,0.15); color:#fff; border-radius:4px; font-size:0.78rem;">${opts}</select>`;
            } else if (s.type === 'toggle') {
                input = `<input type="checkbox" id="${id}" style="width:16px;height:16px;accent-color:#00f3ff;">`;
            } else if (s.type === 'range') {
                input = `<div style="display:flex;align-items:center;gap:8px;flex:1;">
                  <input type="range" id="${id}" min="${s.min}" max="${s.max}" step="${s.step}" style="flex:1;accent-color:#00f3ff;">
                  <span id="${id}-val" style="min-width:48px; text-align:right; color:#00f3ff; font-size:0.78rem;"></span>
                </div>`;
            } else {
                input = `<input type="text" id="${id}" style="flex:1; padding:5px 8px; background:rgba(0,0,0,0.6); border:1px solid rgba(255,255,255,0.15); color:#fff; border-radius:4px; font-size:0.78rem;">`;
            }
            return `<label style="display:flex; align-items:center; gap:12px; margin-bottom:10px; font-size:0.8rem; color:#ccc;">
              <span style="min-width:180px; flex-shrink:0;">${s.label}</span>
              ${input}
            </label>`;
        }).join('');
    }

    bindEvents() {
        // ── HUD master toggle
        const hudCb = this.container.querySelector('#setting-enable-hud') as HTMLInputElement;
        if (hudCb) {
            hudCb.checked = localStorage.getItem('foveai_3d_hud_enabled') !== 'false';
            hudCb.addEventListener('change', () => {
                const en = hudCb.checked;
                localStorage.setItem('foveai_3d_hud_enabled', en ? 'true' : 'false');
                window.dispatchEvent(new CustomEvent('foveai_3d_hud_toggle', { detail: { enabled: en } }));
                const hub = document.getElementById('xr-indicator-hub');
                if (hub) (hub as HTMLElement).style.opacity = en ? '0.8' : '0';
                const mesh = (window as any).xr3dHudMesh;
                if (mesh) mesh.visible = en;
            });
        }

        // ── HUD video control
        const videoInput = this.container.querySelector('#setting-hud-video-url') as HTMLInputElement;
        const playBtn = this.container.querySelector('#btn-hud-video-play') as HTMLButtonElement;
        const stopBtn = this.container.querySelector('#btn-hud-video-stop') as HTMLButtonElement;
        
        if (playBtn && stopBtn && videoInput) {
            videoInput.value = localStorage.getItem('foveai_hud_video_url') || '';

            playBtn.addEventListener('click', () => {
                const url = videoInput.value.trim();
                if (url) {
                    localStorage.setItem('foveai_hud_video_url', url);
                    window.dispatchEvent(new CustomEvent('xr_ide_play_video', { detail: { url } }));
                }
            });

            stopBtn.addEventListener('click', () => {
                window.dispatchEvent(new CustomEvent('xr_ide_stop_video'));
            });
        }

        // ── Room scanner toggle
        const scannerCb = this.container.querySelector('#setting-enable-room-scanner') as HTMLInputElement;
        if (scannerCb) {
            scannerCb.checked = localStorage.getItem('foveai_room_scanner_enabled') !== 'false';
            scannerCb.addEventListener('change', () => {
                const en = scannerCb.checked;
                localStorage.setItem('foveai_room_scanner_enabled', en ? 'true' : 'false');
                const scanner = (window as any).roomScanner;
                if (scanner) {
                    if (en) {
                        scanner.start();
                        (window as any).dashboard?.log('📷 Room Scanner auto-capture started', 'var(--neon-green)');
                    } else {
                        scanner.stop();
                        (window as any).dashboard?.log('📷 Room Scanner auto-capture stopped', 'var(--neon-orange)');
                    }
                }
            });
            window.addEventListener('foveai_room_scanner_complete', () => {
                scannerCb.checked = false;
            });
        }

        // ── HUD opacity slider
        const opSlider = this.container.querySelector('#setting-hud-opacity') as HTMLInputElement;
        const opVal    = this.container.querySelector('#setting-hud-opacity-val') as HTMLSpanElement;
        if (opSlider && opVal) {
            const saved = parseFloat(localStorage.getItem('foveai_hud_opacity') || '0.8');
            opSlider.value = String(saved);
            opVal.textContent = Math.round(saved * 100) + '%';
            const hub = document.getElementById('xr-indicator-hub');
            if (hub) (hub as HTMLElement).style.opacity = String(saved);
            opSlider.addEventListener('input', () => {
                const v = parseFloat(opSlider.value);
                opVal.textContent = Math.round(v * 100) + '%';
                localStorage.setItem('foveai_hud_opacity', String(v));
                const h = document.getElementById('xr-indicator-hub');
                if (h) (h as HTMLElement).style.opacity = String(v);
            });
        }

        // ── Hub panel toggles (identity, devmode, listening, thinking, swarm, dev-feed, telemetry)
        const panelToggles = this.container.querySelectorAll('.hub-panel-toggle') as NodeListOf<HTMLInputElement>;
        panelToggles.forEach(cb => {
            const panelId = cb.dataset['panel'] || '';
            const stored = localStorage.getItem(`foveai_hub_panel_${panelId}_visible`);
            cb.checked = stored !== 'false';
            const el = document.getElementById(panelId);
            if (el) el.style.display = cb.checked ? '' : 'none';
            cb.addEventListener('change', () => {
                localStorage.setItem(`foveai_hub_panel_${panelId}_visible`, cb.checked ? 'true' : 'false');
                const target = document.getElementById(panelId);
                if (target) target.style.display = cb.checked ? '' : 'none';
                // Refresh texture
                const mesh = (window as any).xr3dHudMesh;
                if (mesh) try { (mesh.material as any).map.update(); } catch(_e){}
            });
        });

        // ── Peripheral icon toggles
        const iconToggles = this.container.querySelectorAll('.hud-icon-toggle') as NodeListOf<HTMLInputElement>;
        iconToggles.forEach(cb => {
            const iconId = cb.dataset['icon'] || '';
            cb.checked = localStorage.getItem(`foveai_hud_icon_${iconId}_visible`) !== 'false';
            cb.addEventListener('change', () => {
                localStorage.setItem(`foveai_hud_icon_${iconId}_visible`, cb.checked ? 'true' : 'false');
                const el = document.getElementById(iconId);
                if (el) el.style.display = cb.checked ? 'flex' : 'none';
                const mesh = (window as any).xrPeripheralHudMesh;
                if (mesh) try { (mesh.material as any).map.update(); } catch(_e){}
            });
        });

        // ── Range sliders: live value display + init from stored
        ENV_SETTINGS.filter(s => s.type === 'range').forEach(s => {
            const el = this.container.querySelector(`#env-${s.key}`) as HTMLInputElement;
            const val = this.container.querySelector(`#env-${s.key}-val`) as HTMLSpanElement;
            if (!el || !val) return;
            const stored = localStorage.getItem(`foveai_env_${s.key}`);
            if (stored) el.value = stored;
            val.textContent = el.value;
            el.addEventListener('input', () => { val.textContent = el.value; });
        });

        // ── Toggle (checkbox) env settings: init from stored
        ENV_SETTINGS.filter(s => s.type === 'toggle').forEach(s => {
            const el = this.container.querySelector(`#env-${s.key}`) as HTMLInputElement;
            if (!el) return;
            const stored = localStorage.getItem(`foveai_env_${s.key}`);
            if (stored !== null) el.checked = stored === 'true';
        });

        // ── Service status polling
        this.pollServiceStatus();
        const refreshBtn = this.container.querySelector('#svc-refresh-all');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.pollServiceStatus());

        // ── Individual service restart buttons
        const restartBtns = this.container.querySelectorAll('.svc-restart-btn') as NodeListOf<HTMLButtonElement>;
        restartBtns.forEach(btn => {
            btn.addEventListener('click', async () => {
                const url = btn.dataset['url']!;
                const id  = btn.dataset['id']!;
                btn.textContent = '⌛ RESTARTING…';
                btn.style.opacity = '0.5';
                try {
                    await fetch(url, { method: 'POST' });
                    btn.textContent = '✓ SIGNAL SENT';
                    btn.style.borderColor = '#39ff14';
                    btn.style.color = '#39ff14';
                    setTimeout(() => this.refreshServiceStatus(id), 3000);
                } catch(e) {
                    btn.textContent = '✗ FAILED';
                    btn.style.borderColor = '#ff5500';
                    btn.style.color = '#ff5500';
                }
                setTimeout(() => {
                    btn.textContent = '⟳ RESTART';
                    btn.style.opacity = '1';
                    btn.style.borderColor = '#ffaa00';
                    btn.style.color = '#ffaa00';
                }, 5000);
            });
        });

        // ── Full stack reboot
        const rebootBtn = this.container.querySelector('#btn-reboot-all');
        if (rebootBtn) {
            rebootBtn.addEventListener('click', async () => {
                if (!confirm('⚠ This will stop ALL services and restart via foveai.cmd. Continue?')) return;
                rebootBtn.textContent = '⌛ SENDING REBOOT SIGNAL…';
                try {
                    await fetch('/api/soul/restart', { method: 'POST' });
                    (window as any).dashboard?.log('[Settings] Full stack reboot signal sent', 'var(--neon-pink)');
                } catch(e) {
                    console.warn('[Settings] Reboot signal error:', e);
                }
            });
        }

        // ── Save .env button
        const saveBtn = this.container.querySelector('#settings-save-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveEnvSettings());
        }
    }

    private async pollServiceStatus() {
        for (const svc of SERVICES) {
            this.refreshServiceStatus(svc.id);
        }
    }

    private async refreshServiceStatus(id: string) {
        const svc = SERVICES.find(s => s.id === id);
        if (!svc) return;
        const el = this.container.querySelector(`#svc-status-${id}`) as HTMLElement;
        if (!el) return;
        el.textContent = 'CHECKING…';
        el.style.color = '#aaa';
        el.style.borderColor = 'rgba(255,255,255,0.15)';
        try {
            const r = await fetch(svc.healthUrl, { signal: AbortSignal.timeout(3000) });
            if (r.ok) {
                el.textContent = '● ONLINE';
                el.style.color = '#39ff14';
                el.style.borderColor = 'rgba(57,255,20,0.4)';
                el.style.background = 'rgba(57,255,20,0.05)';
            } else {
                el.textContent = `⚠ HTTP ${r.status}`;
                el.style.color = '#ffaa00';
                el.style.borderColor = 'rgba(255,170,0,0.4)';
                el.style.background = 'rgba(255,170,0,0.05)';
            }
        } catch {
            el.textContent = '● OFFLINE';
            el.style.color = '#ff5500';
            el.style.borderColor = 'rgba(255,85,0,0.4)';
            el.style.background = 'rgba(255,85,0,0.05)';
        }
    }

    private async saveEnvSettings() {
        const updates: Record<string, string> = {};
        ENV_SETTINGS.forEach(s => {
            const el = this.container.querySelector(`#env-${s.key}`) as HTMLInputElement | HTMLSelectElement;
            if (!el) return;
            let val: string;
            if (s.type === 'toggle') val = (el as HTMLInputElement).checked ? 'true' : 'false';
            else val = el.value;
            updates[s.key] = val;
            localStorage.setItem(`foveai_env_${s.key}`, val);
        });

        const statusEl = this.container.querySelector('#settings-status') as HTMLElement;
        const errorEl  = this.container.querySelector('#settings-error')  as HTMLElement;
        try {
            const r = await fetch('/api/soul/env', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ updates })
            });
            if (r.ok) {
                statusEl.style.display = 'block';
                errorEl.style.display  = 'none';
                setTimeout(() => { statusEl.style.display = 'none'; }, 3000);
                (window as any).dashboard?.log('[Settings] .env updated', 'var(--neon-cyan)');
            } else {
                throw new Error(`HTTP ${r.status}`);
            }
        } catch(e) {
            errorEl.textContent = `✗ Save failed: ${e}`;
            errorEl.style.display = 'block';
            statusEl.style.display = 'none';
            setTimeout(() => { errorEl.style.display = 'none'; }, 5000);
        }
    }

    destroy() {
        this.serviceStatusTimers.forEach(t => clearInterval(t));
    }
}
