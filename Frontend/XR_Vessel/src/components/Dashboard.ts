import { localMemory } from '../network/LocalMemory';
import { localArtillery } from '../network/LocalArtillery';
import { VideoChat } from './VideoChat';
import { DiagnosisTab } from './DiagnosisTab';
import { MonetizingTab } from './MonetizingTab';
import { ModelHubTab } from './ModelHubTab';
import { AgencyTab } from './AgencyTab';
import { agentBridge } from '../network/AgentBridge';
import { DreamscapeTab } from './DreamscapeTab';
import { SwarmTab } from './SwarmTab';
import { NucleusTab } from './NucleusTab';
import { thoughtToast } from './ThoughtToast';
import { ProfileTab } from './ProfileTab';
import { ChronicleTab } from './ChronicleTab';
import { BrandingTab } from './BrandingTab';
import { VisionTab } from './VisionTab';
import { DevToolsTab } from './DevToolsTab';
import { FeatureMapTab } from './FeatureMapTab';
import { SettingsTab } from './SettingsTab';
import { TokenSlayerTab } from './TokenSlayerTab';
import { ForgeNurseryTab } from './ForgeNurseryTab';
import { EnvironmentMappingTab } from './EnvironmentMappingTab';
import { AvatarCamerasTab } from './AvatarCamerasTab';
import { EnvironmentManagementTab } from './EnvironmentManagementTab';
import { ControllersMappingTab } from './ControllersMappingTab';

import { contextManager } from '../ContextManager';
import { BracketParser } from '../senses/BracketParser';

export class Dashboard {
    private container: HTMLElement;
    public activeTab: string = 'cognition';
    public isVisible: boolean = true;
    public deepThought: boolean = false;
    public privacyMode: boolean = false;
    public showThoughtStream: boolean = true;
    public chatHistory: Array<{role: string, content: string, imageUrl?: string}> = [];
    public thoughtHistory: Array<{text: string, timestamp: number, sessionId: number}> = [];
    private currentSessionId: number = 1;
    public telemetryModel: string = 'local-model';
    public telemetryData: any = null;

    private attachedImageBase64: string | null = null;
    private vitalsFailCount: number = 0;
    private attachedImageType: string | null = null;
    private attachedImageName: string | null = null;
    private attachedImageDataUrl: string | null = null;
    public attachedFileContent: string | null = null;
    public attachedFileName: string | null = null;

    private VERSION = (window as any).LINK_REVISION?.replace('OMEGA_', '') || "266";
    public isExpanded: boolean = false;
    private isHidden: boolean = false;
    private meters: Record<string, HTMLElement> = {};

    constructor() {
        this.container = document.createElement('div');
        this.container.id = 'foveai-dashboard';
        this.container.classList.add(`mode-${contextManager.getMode()}`);
        
        (window as any).foveaiDashboard = this;
        window.name = "foveai";
        document.title = "FoveAI";
        this.applyStyles();
        this.render();
        this.setupInteractions();
        this.startRealTelemetry();
        this.startNavPolling();
        this.startThoughtPolling();
        this.startThoughtEventListener();
        this.initThinkingConfig();
        // Auto-start VAD listening after permissions are likely granted
        setTimeout(() => this.autoStartVAD(), 3000);
        
        // Auto-expand in mobile, menu, and HUD modes
        const currentMode = contextManager.getMode();
        if (currentMode === 'mobile' || currentMode === 'menu' || currentMode === 'hud') {
            setTimeout(() => this.toggle(true), 100);
        }

        // Create peripheral VAD indicator (small fixed overlay for XR/desktop)
        this.createVadIndicator();
    }

    private async startNavPolling() {
        let pollInterval = 2000;
        let pollTimer: ReturnType<typeof setInterval> | null = null;
        const MAX_INTERVAL = 30000;
        const MIN_INTERVAL = 2000;

        const schedule = () => {
            if (pollTimer) clearInterval(pollTimer);
            pollTimer = setInterval(poll, pollInterval);
        };

        const poll = async () => {
            try {
                // Poll through the Vite proxy to Soul — 1s timeout so it can't hang
                const response = await fetch('/api/soul/api/nav/pull', { signal: AbortSignal.timeout(1000) });
                if (!response.ok) {
                    pollInterval = Math.min(pollInterval * 2, MAX_INTERVAL);
                    schedule();
                    return;
                }
                const data = await response.json();
                if (data.command && data.command.action === 'navigate') {
                    console.log("[NAV] Received navigation command:", data.command.tab);
                    
                    let targetTab = data.command.tab;
                    // Map Top Bar 'classic' to Dashboard 'cognition'
                    if (targetTab === 'classic') targetTab = 'cognition';
                    
                    this.setActiveTab(targetTab);
                    
                    // Ensure dashboard is visible and expanded
                    if (this.isHidden) this.isHidden = false;
                    this.container.style.display = 'flex';
                    this.toggle(true);
                }
                // Success — reset to minimum interval
                if (pollInterval !== MIN_INTERVAL) {
                    pollInterval = MIN_INTERVAL;
                    schedule();
                }
            } catch (err) {
                // Fetch failed or timed out — back off
                pollInterval = Math.min(pollInterval * 2, MAX_INTERVAL);
                schedule();
            }
        };
        // Initial check and then interval
        setTimeout(poll, 1000);
        schedule();
    }

    private setupInteractions() {
        // 1. Hover to expand initially
        this.container.addEventListener('mouseenter', () => {
            this.toggle(true);
        });

        // 2. Click outside to close
        document.addEventListener('mousedown', (e) => {
            // Ignore synthetic VR clicks generated by HTMLMesh (they are not trusted system events)
            if (!e.isTrusted) return;
            // Fallback: Ignore VR clicks which are positioned offscreen at left: -10000px
            if (e.clientX < -1000) return;
            
            const target = e.target as HTMLElement;
            if (this.isExpanded && !this.container.contains(target)) {
                this.toggle(false);
            }
        });

        // 3. Logo Toggle
        const logo = this.container.querySelector('.handle-logo');
        logo?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        // 4. Permissions Grant Button click handler via delegation
        this.container.addEventListener('click', (e) => {
            const target = e.target as HTMLElement;
            if (target && target.id === 'btn-grant-permissions') {
                e.stopPropagation();
                this.requestPermissions();
            }
        });

        // Check permissions initially and periodically
        this.checkPermissions();
        setInterval(() => this.checkPermissions(), 4000);
    }

    private async checkPermissions() {
        const banner = this.container.querySelector('#permissions-banner') as HTMLElement;
        if (!banner) return;
        
        try {
            // Check microphone and camera status via Permissions API if available
            const micStatus = navigator.permissions && navigator.permissions.query 
                ? await navigator.permissions.query({ name: 'microphone' as any }).catch(() => null) 
                : null;
            const camStatus = navigator.permissions && navigator.permissions.query 
                ? await navigator.permissions.query({ name: 'camera' as any }).catch(() => null) 
                : null;
            
            const micGranted = micStatus ? micStatus.state === 'granted' : false;
            const camGranted = camStatus ? camStatus.state === 'granted' : false;
            
            const cachedMic = (window as any).foveaiCachedMicStream;
            const cachedCam = (window as any).foveaiPortalStream;
            
            const hasMic = micGranted || (cachedMic && cachedMic.active);
            const hasCam = camGranted || (cachedCam && cachedCam.active);
            
            if (hasMic && hasCam) {
                banner.style.display = 'none';
            } else {
                banner.style.display = 'flex';
                const label = banner.querySelector('.permission-label') as HTMLElement;
                if (label) {
                    if (!hasMic && !hasCam) {
                        label.textContent = '⚠️ MIC & CAMERA ACCESS REQUIRED';
                    } else if (!hasMic) {
                        label.textContent = '⚠️ MICROPHONE ACCESS REQUIRED';
                    } else {
                        label.textContent = '⚠️ WEBCAM / PORTAL ACCESS REQUIRED';
                    }
                }
            }
        } catch (e) {
            const cachedMic = (window as any).foveaiCachedMicStream;
            const cachedCam = (window as any).foveaiPortalStream;
            if (cachedMic && cachedCam) {
                banner.style.display = 'none';
            } else {
                banner.style.display = 'flex';
            }
        }
    }

    private async requestPermissions() {
        this.log('Requesting mic and camera permissions...', 'var(--neon-blue)');
        try {
            // 1. Microphone request
            const micStream = await navigator.mediaDevices.getUserMedia({ 
    audio: { 
        echoCancellation: true, 
        noiseSuppression: true, 
        autoGainControl: true 
    } 
});
            (window as any).foveaiCachedMicStream = micStream;
            this.log('[SYS] Microphone permission granted & stream pre-cached!', '#39ff14');

            // WORKAROUND: Keep mic stream active/alive in Chromium/Android/Oculus Browser
            try {
                const aud = new Audio();
                aud.srcObject = micStream;
                aud.muted = true;
                aud.play().catch(e => console.warn('[SYS] Workaround audio play failed:', e));
                (window as any).foveaiWorkaroundAudio = aud;
            } catch (err) {
                console.warn('[SYS] Workaround audio setup failed:', err);
            }
            
            // 2. Camera request
            const camStream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 360, facingMode: "user" }
            });
            (window as any).foveaiPortalStream = camStream;
            this.log('[SYS] Webcam permission granted & stream pre-cached!', '#39ff14');
            
            // Update portal video if active
            const videoEl = (window as any).foveaiPortalVideo || document.createElement('video');
            videoEl.srcObject = camStream;
            videoEl.autoplay = true;
            videoEl.playsInline = true;
            videoEl.muted = true;
            videoEl.loop = true;
            videoEl.play().catch(() => {});
            (window as any).foveaiPortalVideo = videoEl;
            
            this.checkPermissions();
        } catch (err) {
            this.log(`Permission request failed: ${err}`, '#ff007f');
            alert(`Could not acquire permissions: ${err}\n\nPlease click the address bar permissions icon to allow Microphone & Camera.`);
        }
    }

    private async startRealTelemetry() {
        const update = async () => {
            try {
                const response = await fetch('/api/soul/vitals', { signal: AbortSignal.timeout(4000) });
                if (!response.ok) throw new Error('Vitals fetch failed');
                const data = await response.json();
                this.telemetryData = data;
                this.vitalsFailCount = 0; // Reset fail counter on success
                if ((window as any).foveaiBrainState) {
                    (window as any).foveaiBrainState.soulReachable = true;
                }

                // Map API fields to meter names
                const mapping: Record<string, number> = {
                    'cpu': data.CPU_PCT,
                    'gpu': data.GPU_PCT,
                    'vram': data.VRAM_PCT,
                    'ram': data.RAM_PCT,
                    // Network & IO: Scale so 100% = 10MB/s (10240 KBps)
                    'in': (data.NET_IN_KBPS / 10240) * 100,
                    'out': (data.NET_OUT_KBPS / 10240) * 100,
                    'io-r': (data.IO_READ_KBPS / 10240) * 100,
                    'io-w': (data.IO_WRITE_KBPS / 10240) * 100,
                };

                Object.entries(mapping).forEach(([name, val]) => {
                    const el = this.meters[name];
                    if (el) {
                        const fill = el.querySelector('.meter-fill') as HTMLElement;
                        if (fill) {
                            // Ensure 5% minimum visibility so the bars don't disappear entirely
                            fill.style.height = `${Math.max(5, Math.min(95, val))}%`;
                        }
                    }
                });
            } catch (err) {
                console.warn('Telemetry offline:', err);
                this.vitalsFailCount++;
                // Only declare offline/crashed on 3 consecutive failures
                if (this.vitalsFailCount >= 3 && (window as any).foveaiBrainState) {
                    (window as any).foveaiBrainState.soulReachable = false;
                }
            }
            
            // Also fetch model/provider info dynamically
            this.updateActiveModelInfo();
        };

        update();
        setInterval(update, 5000); // 5 second intervals (OMEGA_079)
    }

    private async updateActiveModelInfo() {
        try {
            const response = await fetch('/api/chat/provider');
            if (!response.ok) throw new Error('Provider info fetch failed');
            const data = await response.json();
            
            const current = data.current || {};
            const providerId = current.provider || 'unknown';
            const fullModel = current.model || '(default)';
            
            // Find friendly name
            let friendlyName = providerId;
            const providerInfo = (data.providers || []).find((p: any) => p.id === providerId);
            if (providerInfo) friendlyName = providerInfo.name;

            // Get one-word provider name
            const providerWord = (() => {
                const pid = providerId.toLowerCase();
                if (pid.includes("unsloth")) return "Unsloth";
                if (pid.includes("ollama")) return "Ollama";
                if (pid.includes("lmstudio") || pid.includes("lm_studio")) return "LMStudio";
                if (pid.includes("openrouter")) return "OpenRouter";
                if (pid.includes("groq")) return "Groq";
                if (pid.includes("openai")) return "OpenAI";
                if (pid.includes("gemini")) return "Gemini";
                
                // Fallback
                const match = friendlyName.match(/[A-Za-z0-9]+/);
                return match ? match[0].charAt(0).toUpperCase() + match[0].slice(1) : friendlyName;
            })();

            // Get shortened model name + version
            const modelShort = (() => {
                if (!fullModel || fullModel === '(default)') return "Default";
                
                let baseName = fullModel;
                if (baseName.includes('/')) {
                    baseName = baseName.substring(baseName.lastIndexOf('/') + 1);
                }
                if (baseName.includes(':')) {
                    baseName = baseName.split(':')[0];
                }
                
                // Check known families
                const qwenMatch = baseName.match(/qwen[_-]?plus[_-]?(\d+(?:\.\d+)?)/i) || baseName.match(/qwen[_-]?(\d+(?:\.\d+)?)/i);
                if (qwenMatch) {
                    return `Qwen ${qwenMatch[1]}`;
                }
                if (/qwen/i.test(baseName)) {
                    const numMatch = baseName.match(/(\d+\.\d+|\d+)/);
                    return numMatch ? `Qwen ${numMatch[1]}` : "Qwen";
                }
                
                const llamaMatch = baseName.match(/llama[_-]?(\d+(?:\.\d+)?)/i);
                if (llamaMatch) {
                    return `Llama ${llamaMatch[1]}`;
                }
                if (/llama/i.test(baseName)) {
                    const numMatch = baseName.match(/(\d+\.\d+|\d+)/);
                    return numMatch ? `Llama ${numMatch[1]}` : "Llama";
                }
                
                const geminiMatch = baseName.match(/gemini[_-]?(\d+(?:\.\d+)?)/i);
                if (geminiMatch) {
                    return `Gemini ${geminiMatch[1]}`;
                }
                if (/gemini/i.test(baseName)) {
                    const numMatch = baseName.match(/(\d+\.\d+|\d+)/);
                    return numMatch ? `Gemini ${numMatch[1]}` : "Gemini";
                }
                
                const gptMatch = baseName.match(/gpt[_-]?(\d+[a-z0-9]*)/i);
                if (gptMatch) {
                    return `GPT ${gptMatch[1]}`;
                }
                if (/gpt/i.test(baseName)) {
                    return "GPT";
                }
                
                const claudeMatch = baseName.match(/claude[_-]?(\d+(?:\.\d+)?)/i);
                if (claudeMatch) {
                    return `Claude ${claudeMatch[1]}`;
                }
                if (/claude/i.test(baseName)) {
                    return "Claude";
                }

                const phiMatch = baseName.match(/phi[_-]?(\d+(?:\.\d+)?)/i);
                if (phiMatch) {
                    return `Phi ${phiMatch[1]}`;
                }

                // Default fallback: take first part and format
                let clean = baseName.replace(/[_-]/g, ' ');
                let words = clean.split(/\s+/).filter(Boolean);
                if (words.length > 0) {
                    let w0 = words[0].charAt(0).toUpperCase() + words[0].slice(1);
                    if (words.length > 1) {
                        let w1 = words[1];
                        if (/^\d/.test(w1) || w1.toLowerCase().endsWith('b')) {
                            return `${w0} ${w1}`;
                        }
                    }
                    return w0;
                }
                
                return baseName;
            })();

            const elProvider = this.container.querySelector('#tel-provider-name');
            const elModel = this.container.querySelector('#tel-model-name');
            const elShortcut = this.container.querySelector('#tel-model-hub-shortcut');

            if (elProvider) elProvider.textContent = providerWord;
            if (elModel) elModel.textContent = modelShort;
            if (elShortcut) {
                elShortcut.setAttribute('title', `Provider: ${friendlyName}\nModel: ${fullModel}\n\nClick to open Model Hub`);
            }
            this.telemetryModel = `${providerWord}/${modelShort}`;

            // Activate neural nodes based on cognitive_mode
            const cogMode = (current.cognitive_mode || 'hybrid').toLowerCase();
            const currentProviderId = current.provider || '';

            const nodeLocal = this.container.querySelector('#node-local');
            const nodeHybrid = this.container.querySelector('#node-hybrid');
            const nodeCloud = this.container.querySelector('#node-cloud');

            // Only one node active at a time, matching FoveAI_COGNITIVE_MODE
            if (nodeLocal) nodeLocal.classList.remove('active');
            if (nodeHybrid) nodeHybrid.classList.remove('active');
            if (nodeCloud) nodeCloud.classList.remove('active');

            if (cogMode === 'local' && nodeLocal) {
                nodeLocal.classList.add('active');
            } else if (cogMode === 'hybrid' && nodeHybrid) {
                nodeHybrid.classList.add('active');
            } else if (cogMode === 'cloud' && nodeCloud) {
                nodeCloud.classList.add('active');
            }
        } catch (err) {
            console.warn('[ModelInfo] Failed to fetch active model info:', err);
        }
    }

    public toggle(force?: boolean) {
        this.isExpanded = (force !== undefined) ? force : !this.isExpanded;
        if (this.isExpanded) {
            this.container.classList.add('expanded');
        } else {
            this.container.classList.remove('expanded');
        }
        window.dispatchEvent(new CustomEvent('foveai_dashboard_toggled', { detail: this.isExpanded }));
    }

    public setHidden(hidden: boolean) {
        this.isHidden = hidden;
        if (this.isHidden) {
            this.container.classList.add('hidden');
        } else {
            this.container.classList.remove('hidden');
        }
    }

    public toggleSleepMode() {
        const isSleeping = !(window as any).foveaiScreenOff;
        (window as any).foveaiScreenOff = isSleeping;
        
        let mask = document.getElementById('foveai-sleep-mask');
        if (isSleeping) {
            this.log('Screen Saver Active (OLED battery saver). Double-tap anywhere to wake.', 'var(--neon-blue)');
            if (!mask) {
                mask = document.createElement('div');
                mask.id = 'foveai-sleep-mask';
                mask.style.position = 'fixed';
                mask.style.top = '0';
                mask.style.left = '0';
                mask.style.width = '100vw';
                mask.style.height = '100vh';
                mask.style.background = '#000000';
                mask.style.zIndex = '999999';
                mask.style.cursor = 'pointer';
                mask.style.display = 'flex';
                mask.style.flexDirection = 'column';
                mask.style.justifyContent = 'center';
                mask.style.alignItems = 'center';
                
                // Add pulsing breathing dot
                const breathingDot = document.createElement('div');
                breathingDot.style.width = '12px';
                breathingDot.style.height = '12px';
                breathingDot.style.borderRadius = '50%';
                breathingDot.style.background = 'var(--neon-blue, #00f3ff)';
                breathingDot.style.boxShadow = '0 0 15px var(--neon-blue, #00f3ff)';
                breathingDot.style.animation = 'foveai-sleep-pulse 3s infinite ease-in-out';
                
                const breathingText = document.createElement('div');
                breathingText.style.color = '#303030';
                breathingText.style.fontFamily = "'Orbitron', sans-serif";
                breathingText.style.fontSize = '0.7rem';
                breathingText.style.marginTop = '15px';
                breathingText.style.letterSpacing = '1px';
                breathingText.textContent = 'JEN IS LISTENING';
                
                mask.appendChild(breathingDot);
                mask.appendChild(breathingText);
                
                // Wake on double-click/double-tap
                let lastTap = 0;
                const wakeHandler = (e: Event) => {
                    const now = Date.now();
                    if (now - lastTap < 300) {
                        e.stopPropagation();
                        e.preventDefault();
                        this.toggleSleepMode();
                    }
                    lastTap = now;
                };
                mask.addEventListener('click', wakeHandler);
                mask.addEventListener('touchstart', wakeHandler);
                
                document.body.appendChild(mask);
            } else {
                mask.style.display = 'flex';
            }
        } else {
            this.log('Vessel Link: System display active', 'var(--neon-green)');
            if (mask) {
                mask.style.display = 'none';
            }
        }
    }

    public log(msg: string, color?: string) {
        (window as any).log?.(msg, color);
    }

    public setNeuralState(node: 'local' | 'hybrid' | 'cloud', active: boolean) {
        const el = this.container.querySelector(`#node-${node}`) as HTMLElement;
        if (el) {
            if (active) el.classList.add('active');
            else el.classList.remove('active');
        }
    }

    public updateXRTelemetry(status: string, color: string = 'var(--neon-blue)') {
        const el = this.container.querySelector('#tel-xr') as HTMLElement;
        if (el) {
            el.innerHTML = `<span>XR</span>${status}`;
            el.style.color = color;
        }
    }

    public async loadInitialHistory() {
        try {
            const history = await localMemory.getRecentContext(20);
            const chatHistory = this.container.querySelector('#chat-history');
            if (chatHistory) {
                chatHistory.innerHTML = ''; // Clear loading state
               if (history && history.length > 0) {
                    history.forEach((msg: any) => {
                        if (msg.role !== 'system') {
                            this.addMessage(msg.role, msg.content, false, msg.imageUrl);
                        }
                    });
                    requestAnimationFrame(() => {
                        const chatHistory = this.container.querySelector('#chat-history');
                        if (chatHistory) {
                            chatHistory.scrollTop = chatHistory.scrollHeight;
                        }
                    });
                }
            }
        } catch (err) {
            console.warn('[Dashboard] Failed to load history:', err);
        }
    }

    private applyStyles() {
        const style = document.createElement('style');
        style.id = 'foveai-dashboard-styles';
        style.textContent = `
            :root {
                --neon-blue: #00f3ff;
                --neon-pink: #ff007f;
                --neon-green: #39ff14;
                --bg-dark: #02050a;
                --glass-bg: rgba(10, 15, 25, 0.82);
                --glass-blur: blur(15px);
                --border: rgba(0, 243, 255, 0.2);
                --transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }

            #foveai-dashboard {
                position: fixed;
                top: 0;
                right: 0;
                width: min(580px, 92vw);
                max-width: 100vw;
                height: 100vh;
                max-height: 100vh;
                background: var(--glass-bg);
                backdrop-filter: var(--glass-blur);
                border-left: 1px solid var(--border);
                color: #e0e0e0;
                font-family: 'Inter', sans-serif;

                display: flex;
                flex-direction: column;
                overflow: hidden;
                z-index: 1000;
                box-shadow: -10px 0 30px rgba(0, 0, 0, 0.5);
                pointer-events: auto;
                user-select: text !important;
                transition: transform 0.4s cubic-bezier(0.19, 1, 0.22, 1), background 0.3s ease;
                opacity: 1;
                visibility: visible;
                box-sizing: border-box;
                transform: translateX(calc(100% - 20px)); /* Collapse to 20px strip */
            }

            #foveai-dashboard.expanded {
                transform: translateX(0);
                background: rgba(10, 15, 25, 0.95);
                box-shadow: -20px 0 50px rgba(0, 0, 0, 0.8);
            }

            .dashboard-handle {
                position: absolute;
                top: 0;
                left: 0;
                width: 20px;
                height: 100%;
                background: rgba(0, 0, 0, 0.4);
                border-right: 1px solid rgba(0, 243, 255, 0.1);
                display: flex;
                flex-direction: column;
                align-items: center;
                z-index: 5;
                transition: opacity 0.3s;
            }

            #foveai-dashboard.expanded .dashboard-handle {
                opacity: 0.1;
                pointer-events: none;
            }

            .handle-logo {
                width: 20px;
                height: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                margin-bottom: 5px;
            }

            .meter-stack {
                flex: 1;
                width: 100%;
                display: flex;
                flex-direction: column;
                gap: 2px;
                padding: 2px 0;
            }

            .telemetry-meter {
                flex: 1;
                width: 100%;
                background: rgba(255, 255, 255, 0.05);
                position: relative;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                justify-content: flex-end;
            }

            .meter-fill {
                width: 100%;
                height: 30%;
                background: linear-gradient(to top, var(--neon-blue), var(--neon-pink), var(--neon-green));
                transition: height 0.8s cubic-bezier(0.4, 0, 0.2, 1);
                opacity: 0.6;
            }

            .meter-label {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%) rotate(-90deg);
                font-family: 'Share Tech Mono', monospace;
                font-size: 7px;
                color: #fff;
                white-space: nowrap;
                pointer-events: none;
                text-transform: uppercase;
                letter-spacing: 1px;
                opacity: 0.8;
                text-shadow: 1px 1px 2px #000;
            }

            #foveai-dashboard * {
                box-sizing: border-box;
                user-select: text !important;
            }

            #foveai-dashboard.mode-voice {
                width: 100vw;
                max-width: 100vw;
                transform: translateX(0);
                background: var(--bg-dark);
            }
            #foveai-dashboard.mode-voice .dashboard-handle {
                display: none;
            }

            #foveai-dashboard.mode-xr,
            #foveai-dashboard.mode-ar {
                position: fixed !important;
                top: 5vh !important;
                left: 10vw !important;
                width: 80vw !important;
                max-width: 80vw !important;
                height: 90vh !important;
                border-radius: 20px !important;
                border: 2px solid rgba(0, 243, 255, 0.4) !important;
                background: rgba(6, 10, 18, 0.94) !important;
                backdrop-filter: blur(20px) !important;
                box-shadow: 0 0 50px rgba(0, 243, 255, 0.3) !important;
                z-index: -100 !important;
                transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.3s ease, visibility 0.3s !important;
            }

            #foveai-dashboard.mode-xr.expanded,
            #foveai-dashboard.mode-ar.expanded {
                transform: scale(1) !important;
                opacity: 1 !important;
                visibility: visible !important;
            }
            
            body.unit-qu #foveai-dashboard,
            body.unit-q3 #foveai-dashboard,
            #foveai-dashboard.mode-qu,
            #foveai-dashboard.mode-quest {
                display: flex !important;
                position: fixed !important;
                left: -10000px !important;
                top: 0 !important;
                width: 1024px !important;
                height: 1024px !important;
                visibility: visible !important;
                opacity: 1 !important;
                pointer-events: auto !important;
                transform: none !important;
                /* Glassmorphic Gadget Upgrade */
                border-radius: 40px !important;
                border: 4px solid var(--neon-blue) !important;
                box-shadow: 0 0 60px rgba(0, 243, 255, 0.4), inset 0 0 40px rgba(0, 243, 255, 0.15) !important;
                background-color: rgba(6, 10, 18, 0.85) !important;
                background-image: 
                    radial-gradient(circle at top right, rgba(0, 243, 255, 0.15), transparent 50%),
                    radial-gradient(circle at bottom left, rgba(0, 243, 255, 0.1), transparent 50%),
                    linear-gradient(rgba(0, 243, 255, 0.05) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(0, 243, 255, 0.05) 1px, transparent 1px) !important;
                background-size: 100% 100%, 100% 100%, 30px 30px, 30px 30px !important;
            }

            #foveai-dashboard.mode-xr .dashboard-handle,
            #foveai-dashboard.mode-ar .dashboard-handle {
                display: none !important;
            }

            @keyframes foveai-sleep-pulse {
                0% { opacity: 0.1; transform: scale(0.9); }
                50% { opacity: 0.8; transform: scale(1.1); }
                100% { opacity: 0.1; transform: scale(0.9); }
            }

            @media (max-width: 480px) {
                #foveai-dashboard {
                    width: 100vw;
                    min-width: 100vw;
                }
                .branding-banner { height: 40px; padding: 0 10px; }
                .brand-site-name { font-size: 0.75rem; }
                .nav-tabs { height: 35px; }
                .nav-item { font-size: 0.5rem; letter-spacing: 0.5px; }
                .dashboard-content { padding: 15px; }
                .msg { font-size: 0.75rem; }
                .sub-item { padding: 10px 15px; font-size: 0.6rem; }
                .submenu { width: 150px; }
            }

            #foveai-dashboard.hidden {
                transform: translateX(100%);
                opacity: 0;
                visibility: hidden;
            }

            .branding-banner {
                padding: 10px 15px;
                background: rgba(0, 243, 255, 0.05);
                border-bottom: 1px solid var(--border);
                display: flex;
                justify-content: space-between;
                align-items: center;
                height: 45px;
                flex-shrink: 0;
            }

            .branding-left { display: flex; flex-direction: column; }
            .branding-right { display: flex; align-items: center; }

            .brand-site-name {
                font-family: 'Orbitron', sans-serif;
                font-size: 0.9rem;
                font-weight: 700;
                letter-spacing: 2px;
                color: var(--neon-blue);
                text-shadow: 0 0 8px rgba(0, 243, 255, 0.4);
            }

            .visualizer-bars { display: flex; gap: 2px; height: 12px; align-items: flex-end; }
            .vbar {
                width: 3px;
                background: var(--neon-blue);
                animation: vbar-pulse 1.2s infinite ease-in-out;
            }
            .vbar:nth-child(2) { animation-delay: 0.2s; height: 60%; }
            .vbar:nth-child(3) { animation-delay: 0.4s; height: 100%; }
            .vbar:nth-child(4) { animation-delay: 0.1s; height: 40%; }

            @keyframes vbar-pulse {
                0%, 100% { height: 30%; opacity: 0.4; }
                50% { height: 90%; opacity: 1; }
            }

            .brand-slogan { display: none; } 

            .telemetry-strip {
                display: flex;
                padding: 0 15px;
                background: rgba(0, 0, 0, 0.5);
                border-bottom: 1px solid var(--border);
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.6rem;
                height: 28px;
                color: var(--neon-blue);
                align-items: center;
                justify-content: flex-start;
                gap: 15px;
                flex-shrink: 0;
            }

            .tel-item { white-space: nowrap; display: flex; align-items: center; }
            .tel-item span { color: #fff; opacity: 0.5; margin-right: 4px; font-weight: normal; }

            #tel-model-hub-shortcut {
                cursor: pointer;
                transition: all 0.2s ease-in-out;
            }
            #tel-model-hub-shortcut:hover,
            #tel-model-hub-shortcut.hover {
                text-shadow: 0 0 6px var(--neon-blue);
                opacity: 1 !important;
            }
            #tel-model-hub-shortcut:hover #tel-model-name,
            #tel-model-hub-shortcut.hover #tel-model-name {
                text-shadow: 0 0 6px var(--neon-pink);
            }

            #xr-controller-status {
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0 4px;
                transition: all 0.2s ease-in-out;
            }
            #xr-controller-status:hover {
                text-shadow: 0 0 6px var(--neon-blue);
                background: rgba(0, 243, 255, 0.05);
            }

            .neural-nodes { 
                display: flex; 
                gap: 10px; 
                margin-left: auto; 
                align-items: center;
            }
            .node { display: flex; align-items: center; gap: 4px; opacity: 0.3; font-size: 0.55rem; }
            .node.active { opacity: 1; color: var(--neon-pink); }
            .node-dot { width: 5px; height: 5px; border-radius: 50%; background: #fff; }
            .node.active .node-dot { background: var(--neon-pink); box-shadow: 0 0 6px var(--neon-pink); }

            .nav-tabs {
                display: flex;
                background: rgba(0, 0, 0, 0.85);
                border-bottom: 1px solid var(--border);
                height: 40px;
                flex-shrink: 0;
            }

            .nav-item {
                flex: 1;
                position: relative;
                padding: 0;
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.6);
                font-family: 'Orbitron', sans-serif;
                font-size: 0.6rem;
                font-weight: 800;
                cursor: pointer;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                transition: var(--transition);
                display: flex;
                align-items: center;
                justify-content: center;
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }

            .nav-item:last-child { border-right: none; }

            .nav-item:hover,
            .nav-item.hover {
                background: rgba(0, 243, 255, 0.1);
                color: var(--neon-blue);
            }

            .nav-item.active-group {
                color: var(--neon-blue);
                box-shadow: inset 0 -2px 0 var(--neon-blue);
            }

            .nav-item:hover .submenu,
            .nav-item.hover .submenu {
                display: flex;
            }

            .submenu {
                position: absolute;
                top: 100%;
                left: 0;
                width: 180px;
                background: rgba(8, 12, 20, 0.98);
                border: 1px solid var(--border);
                display: none;
                flex-direction: column;
                z-index: 2000;
                box-shadow: 0 15px 40px rgba(0,0,0,0.9);
                backdrop-filter: blur(25px);
                padding: 4px 0;
            }

            .nav-item:nth-child(2) .submenu { left: 50%; transform: translateX(-50%); }
            .nav-item:nth-child(3) .submenu { left: auto; right: 0; }

            .sub-item {
                padding: 12px 18px;
                font-size: 0.65rem;
                font-family: 'Orbitron', sans-serif;
                font-weight: 600;
                color: rgba(255, 255, 255, 0.7);
                text-align: left;
                transition: all 0.2s;
                letter-spacing: 1px;
                text-transform: uppercase;
                border-left: 2px solid transparent;
            }

            .sub-item:hover,
            .sub-item.hover {
                background: rgba(0, 243, 255, 0.12);
                color: var(--neon-blue);
                border-left-color: var(--neon-blue);
                padding-left: 22px;
            }

            .sub-item.active {
                color: var(--neon-blue);
                background: rgba(0, 243, 255, 0.08);
                border-left-color: var(--neon-blue);
                font-weight: 800;
            }

            .sub-item.exit-menu-item:hover,
            .sub-item.exit-menu-item.hover {
                background: rgba(255, 0, 127, 0.15);
                color: var(--neon-pink) !important;
                border-left-color: var(--neon-pink);
                text-shadow: 0 0 8px rgba(255, 0, 127, 0.6);
            }

            .dashboard-content {
                flex: 1;
                min-height: 0;
                padding: 12px 16px;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                gap: 10px;
                background: radial-gradient(circle at 50% 0%, rgba(0, 243, 255, 0.05) 0%, transparent 70%);
            }

            .breadcrumb {
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.6rem;
                letter-spacing: 1px;
                opacity: 0.5;
                margin-bottom: 5px;
            }

            #chat-history {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 12px;
                overflow-y: auto;
                overflow-x: hidden;
                padding-right: 10px;
                width: 100%;
                box-sizing: border-box;
            }

            .msg {
                padding: 10px 14px;
                border-radius: 8px;
                font-size: 0.85rem;
                line-height: 1.4;
                position: relative;
                max-width: 90%;
                word-break: break-all;
                overflow-wrap: break-word;
                box-sizing: border-box;
            }

            .msg-text {
                white-space: pre-wrap;
                word-break: break-all;
                overflow-wrap: break-word;
                width: 100%;
                display: block;
            }

            .msg-user {
                padding: 10px 14px;
                border-radius: 8px;
                font-size: 0.85rem;
                line-height: 1.4;
                position: relative;
                max-width: 90%;
                align-self: flex-end;
                background: rgba(0, 243, 255, 0.08);
                border: 1px solid rgba(0, 243, 255, 0.2);
                border-right: 3px solid var(--neon-blue);
                word-break: break-all;
                overflow-wrap: break-word;
                box-sizing: border-box;
            }

            .msg-ai {
                padding: 10px 14px;
                border-radius: 8px;
                font-size: 0.85rem;
                line-height: 1.4;
                position: relative;
                max-width: 90%;
                align-self: flex-start;
                background: rgba(255, 0, 127, 0.05);
                border: 1px solid rgba(255, 0, 127, 0.15);
                border-left: 3px solid var(--neon-pink);
                word-break: break-all;
                overflow-wrap: break-word;
                box-sizing: border-box;
            }

            .sender-tag {
                font-family: 'Orbitron', sans-serif;
                font-size: 0.55rem;
                font-weight: 700;
                letter-spacing: 1px;
                margin-bottom: 4px;
                display: block;
                opacity: 0.7;
            }

            .msg-user .sender-tag { color: var(--neon-blue); }
            .msg-ai .sender-tag { color: var(--neon-pink); }

            ::-webkit-scrollbar { width: 4px; }
            ::-webkit-scrollbar-track { background: rgba(0,0,0,0.1); }
            ::-webkit-scrollbar-thumb { background: rgba(0, 243, 255, 0.2); border-radius: 2px; }
            ::-webkit-scrollbar-thumb:hover { background: rgba(0, 243, 255, 0.4); }

            .dashboard-footer {
                padding: 15px 20px;
                background: rgba(0, 0, 0, 0.4);
                border-top: 1px solid var(--border);
            }

            .input-wrapper {
                display: flex;
                gap: 10px;
                background: rgba(255,255,255,0.03);
                border: 1px solid var(--border);
                border-radius: 4px;
                padding: 5px;
            }

            #chat-input {
                flex: 1;
                background: transparent;
                border: none;
                color: #fff;
                padding: 8px 10px;
                font-family: 'Inter', sans-serif;
                font-size: 0.85rem;
                outline: none;
            }

            #chat-input::placeholder { color: rgba(255,255,255,0.2); }

            .btn-send {
                background: var(--neon-blue);
                color: #000;
                border: none;
                border-radius: 3px;
                padding: 0 15px;
                font-family: 'Orbitron', sans-serif;
                font-size: 0.6rem;
                font-weight: 700;
                cursor: pointer;
                transition: var(--transition);
            }

            .btn-send:hover {
                background: #fff;
                box-shadow: 0 0 15px var(--neon-blue);
            }

            .btn-attach {
                background: transparent;
                border: 1px solid var(--border);
                color: #fff;
                border-radius: 3px;
                padding: 0 10px;
                font-size: 1.1rem;
                cursor: pointer;
                transition: var(--transition);
            }

            .btn-attach:hover {
                background: rgba(0, 243, 255, 0.1);
                border-color: var(--neon-blue);
            }

            .btn-mic {
                background: transparent;
                border: 1px solid var(--border);
                color: #fff;
                border-radius: 3px;
                padding: 0 10px;
                font-size: 1.1rem;
                cursor: pointer;
                transition: var(--transition);
            }

            .btn-mic:hover {
                background: rgba(0, 243, 255, 0.1);
                border-color: var(--neon-blue);
            }

            .btn-mic.listening {
                background: rgba(255, 0, 127, 0.2);
                border-color: var(--neon-pink);
                color: var(--neon-pink);
                animation: pulse-mic 1.5s infinite;
            }

            .btn-deep {
                background: transparent;
                border: 1px solid var(--border);
                color: #fff;
                border-radius: 3px;
                padding: 0 10px;
                font-size: 1.1rem;
                cursor: pointer;
                transition: var(--transition);
            }

            .btn-deep:hover {
                background: rgba(147, 51, 234, 0.1);
                border-color: #9333ea;
            }

            .btn-thought {
                background: transparent;
                border: 1px solid var(--border);
                color: #fff;
                border-radius: 3px;
                padding: 0 10px;
                font-size: 1.1rem;
                cursor: pointer;
                transition: var(--transition);
            }

            .btn-thought:hover {
                background: rgba(0, 243, 255, 0.1);
                border-color: var(--neon-blue);
            }

            .btn-thought.active {
                background: rgba(0, 243, 255, 0.2);
                border-color: var(--neon-blue);
                color: var(--neon-blue);
                box-shadow: 0 0 10px var(--neon-blue);
            }

            .btn-privacy {
                background: transparent;
                border: 1px solid var(--border);
                color: #fff;
                border-radius: 3px;
                padding: 0 10px;
                font-size: 1.1rem;
                cursor: pointer;
                transition: var(--transition);
            }

            .btn-privacy:hover {
                background: rgba(147, 51, 234, 0.1);
                border-color: #9333ea;
            }

            .btn-privacy.active {
                background: rgba(147, 51, 234, 0.2);
                border-color: #9333ea;
                color: #9333ea;
                box-shadow: 0 0 12px rgba(147, 51, 234, 0.4);
                text-shadow: 0 0 8px rgba(147, 51, 234, 0.6);
                animation: pulse-privacy 1.5s infinite;
            }

            @keyframes pulse-privacy {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
            }

            .btn-deep.active {
                background: rgba(147, 51, 234, 0.2);
                border-color: #9333ea;
                color: #9333ea;
                box-shadow: 0 0 12px rgba(147, 51, 234, 0.4);
                text-shadow: 0 0 8px rgba(147, 51, 234, 0.6);
                animation: pulse-deep 1.5s infinite;
            }

            @keyframes pulse-deep {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
            }

            @keyframes pulse-mic {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }

            /* Virtual File Browser Modal Styles */
            .file-browser-modal {
                position: absolute;
                top: 5%;
                left: 5%;
                width: 90%;
                height: 90%;
                background: rgba(6, 10, 18, 0.96);
                backdrop-filter: blur(25px);
                border: 2px solid var(--neon-blue);
                border-radius: 12px;
                box-shadow: 0 0 40px rgba(0, 243, 255, 0.4);
                z-index: 10000;
                display: none;
                flex-direction: column;
                padding: 20px;
                box-sizing: border-box;
                color: #fff;
                font-family: 'Orbitron', sans-serif;
            }

            .file-browser-modal.show {
                display: flex;
            }

            .fb-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid rgba(0, 243, 255, 0.2);
                padding-bottom: 10px;
                margin-bottom: 15px;
            }

            .fb-title {
                font-size: 1.1rem;
                font-weight: 700;
                color: var(--neon-blue);
                letter-spacing: 1px;
            }

            .fb-close-btn {
                background: transparent;
                border: 1px solid var(--neon-pink);
                color: var(--neon-pink);
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 0.8rem;
                cursor: pointer;
                font-family: 'Orbitron', sans-serif;
                transition: var(--transition);
            }

            .fb-close-btn:hover {
                background: rgba(255, 0, 127, 0.15);
                box-shadow: 0 0 10px var(--neon-pink);
            }

            .fb-path-bar {
                display: flex;
                align-items: center;
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 8px 12px;
                font-family: monospace;
                font-size: 0.85rem;
                color: #a0a0a0;
                margin-bottom: 15px;
                overflow-x: auto;
                white-space: nowrap;
            }

            .fb-list {
                flex-grow: 1;
                overflow-y: auto;
                background: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                padding: 10px;
                display: flex;
                flex-direction: column;
                gap: 5px;
            }

            .fb-item {
                display: flex;
                align-items: center;
                padding: 8px 12px;
                border-radius: 4px;
                cursor: pointer;
                transition: background 0.2s ease;
                font-family: monospace;
                font-size: 0.9rem;
            }

            .fb-item:hover {
                background: rgba(0, 243, 255, 0.1);
            }

            .fb-item.selected {
                background: rgba(0, 243, 255, 0.2);
                border: 1px solid rgba(0, 243, 255, 0.4);
            }

            .fb-item-icon {
                margin-right: 12px;
                font-size: 1.1rem;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 20px;
            }

            .fb-item-name {
                flex-grow: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .fb-item-size {
                font-size: 0.75rem;
                color: #888;
                margin-left: 10px;
            }

            .fb-footer {
                display: flex;
                justify-content: flex-end;
                gap: 15px;
                margin-top: 15px;
                padding-top: 10px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }

            .fb-action-btn {
                background: var(--neon-blue);
                color: #000;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 0.8rem;
                font-weight: bold;
                cursor: pointer;
                font-family: 'Orbitron', sans-serif;
                transition: var(--transition);
            }

            .fb-action-btn:hover {
                background: #fff;
                box-shadow: 0 0 15px var(--neon-blue);
            }

            .fb-action-btn:disabled {
                background: #333;
                color: #666;
                cursor: not-allowed;
                box-shadow: none;
            }

            .log-entry {
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.7rem;
                padding: 4px 0;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                color: rgba(255,255,255,0.6);
            }
            .log-time { color: var(--neon-blue); margin-right: 10px; }

            .artillery-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                gap: 10px;
            }
            .artillery-card {
                background: rgba(255,255,255,0.03);
                border: 1px solid var(--border);
                padding: 15px;
                border-radius: 6px;
                text-align: center;
                cursor: pointer;
                transition: var(--transition);
                display: flex;
                flex-direction: column;
                justify-content: center;
                min-height: 120px;
            }
            .artillery-card:hover {
                background: rgba(0, 243, 255, 0.05);
                border-color: var(--neon-blue);
            }
            .artillery-icon { font-size: 1.5rem; margin-bottom: 10px; display: block; }
            .artillery-label { font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 1px; }

            .theology-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 15px;
            }
            .symbol-card {
                background: rgba(255,255,255,0.02);
                border: 1px solid rgba(0, 243, 255, 0.1);
                border-radius: 12px;
                padding: 15px;
                display: flex;
                flex-direction: column;
                align-items: center;
                transition: var(--transition);
                cursor: pointer;
            }
            .symbol-card:hover {
                background: rgba(0, 243, 255, 0.05);
                border-color: var(--neon-blue);
                transform: translateY(-2px);
            }
            .symbol-svg {
                width: 60px;
                height: 60px;
                margin-bottom: 10px;
            }
            .symbol-label {
                font-family: 'Orbitron', sans-serif;
                font-size: 0.6rem;
                letter-spacing: 1px;
                color: var(--neon-blue);
                text-align: center;
            }
            .symbol-desc {
                font-size: 0.55rem;
                opacity: 0.5;
                margin-top: 5px;
                text-align: center;
                line-height: 1.2;
            }

            #btn-enter-xr:hover {
                background: var(--neon-blue);
                color: #000;
                box-shadow: 0 0 10px var(--neon-blue);
            }

            #xr-entry-btn {
                position: fixed;
                bottom: 20px;
                left: 20px;
                width: 48px;
                height: 48px;
                background: rgba(0, 243, 255, 0.1);
                border: 1px solid var(--neon-blue);
                border-radius: 50%;
                display: none;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                z-index: 9999;
                transition: all 0.3s ease;
                box-shadow: 0 0 15px rgba(0, 243, 255, 0.2);
            }

            #xr-entry-btn:hover {
                background: rgba(0, 243, 255, 0.3);
                box-shadow: 0 0 25px rgba(0, 243, 255, 0.5);
                transform: scale(1.1);
            }

            #xr-entry-btn svg {
                width: 26px;
                height: 26px;
                fill: none;
                stroke: var(--neon-blue);
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            #xr-entry-btn .xr-label {
                position: absolute;
                bottom: -18px;
                left: 50%;
                transform: translateX(-50%);
                font-family: 'Orbitron', sans-serif;
                font-size: 0.45rem;
                letter-spacing: 1px;
                color: var(--neon-blue);
                white-space: nowrap;
                opacity: 0.7;
            }

            @keyframes xr-pulse {
                0%, 100% { box-shadow: 0 0 15px rgba(0, 243, 255, 0.2); }
                50% { box-shadow: 0 0 25px rgba(0, 243, 255, 0.5); }
            }

            #xr-entry-btn.xr-ready {
                display: flex;
                animation: xr-pulse 3s infinite;
            }

            #xr-entry-btn.xr-unavailable {
                display: flex;
                opacity: 0.3;
                cursor: not-allowed;
                animation: none;
            }

            #xr-entry-btn.xr-unavailable:hover {
                background: rgba(0, 243, 255, 0.1);
                box-shadow: none;
                transform: none;
            }

            #xr-entry-btn .xr-tooltip {
                position: absolute;
                bottom: 50px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0, 0, 0, 0.9);
                border: 1px solid var(--border);
                color: #fff;
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.6rem;
                padding: 6px 10px;
                border-radius: 4px;
                white-space: nowrap;
                pointer-events: none;
                opacity: 0;
                transition: opacity 0.2s;
                z-index: 10000;
            }

            #xr-entry-btn:hover .xr-tooltip {
                opacity: 1;
            }

            /* Minimalist / Voice-Only Mode (PC/Browser Optimized) */
            #foveai-dashboard.mode-voice {
                width: 100vw;
                max-width: 100vw;
                transform: translateX(0);
                background: var(--bg-dark);
            }
            #foveai-dashboard.mode-voice .dashboard-handle {
                display: none;
            }

            /* OLED Battery Saver Screen Saver Animation */
            @keyframes foveai-sleep-pulse {
                0% { opacity: 0.1; transform: scale(0.9); }
                50% { opacity: 0.8; transform: scale(1.1); }
                100% { opacity: 0.1; transform: scale(0.9); }
            }

            /* VR Optimization: hide headers, handles, and footer actions to maximize scroll space */
            #foveai-dashboard.mode-xr .branding-banner,
            #foveai-dashboard.mode-xr .dashboard-handle,
            #foveai-dashboard.mode-xr #footer-actions {
                display: none !important;
            }

            .btn-hud {
                background: transparent;
                border: 1px solid var(--border);
                color: #fff;
                border-radius: 3px;
                padding: 0 10px;
                font-size: 1.1rem;
                cursor: pointer;
                transition: var(--transition);
            }

            .btn-hud:hover {
                background: rgba(0, 243, 255, 0.1);
                border-color: var(--neon-blue);
            }

            .btn-hud.active {
                background: rgba(0, 243, 255, 0.2);
                border-color: var(--neon-blue);
                color: var(--neon-blue);
                box-shadow: 0 0 12px rgba(0, 243, 255, 0.4);
                text-shadow: 0 0 8px rgba(0, 243, 255, 0.6);
            }
        `;
        document.head.appendChild(style);
    }

    private render() {
        const version = (window as any).LINK_REVISION || 'v0.0.0';
        
        // Modular Component Visibility checks (c=co,di parameter)
        const visibleTabs = contextManager.getVisibleTabs();
        const isVisible = (tabId: string) => {
            if (!visibleTabs) return true;
            return visibleTabs.includes(tabId);
        };
        const tabStyle = (tabId: string) => isVisible(tabId) ? '' : 'display: none !important;';

        const hasVisibleIntel = isVisible('cognition') || isVisible('thoughts') || isVisible('profile') || isVisible('swarm') || isVisible('agency');
        const hasVisibleProd = isVisible('dreamscape') || isVisible('modelhub') || isVisible('chronicle') || isVisible('monetizing');
        const hasVisibleOps = isVisible('diagnosis') || isVisible('nucleus') || isVisible('vision') || isVisible('branding') || isVisible('webvm') || isVisible('videochat') || isVisible('settings') || isVisible('tokenslayer') || isVisible('forgenursery') || isVisible('envmapping') || isVisible('avatarcameras') || isVisible('envmanagement') || isVisible('controllers');
        const hasVisibleDev = isVisible('devtools') || isVisible('featuremap');

        const meterNames = ['cpu', 'gpu', 'vram', 'ram', 'in', 'out', 'io-r', 'io-w'];
        let metersHtml = '';
        meterNames.forEach(name => {
            metersHtml += `
                <div class="telemetry-meter" id="meter-${name}">
                    <div class="meter-fill"></div>
                    <div class="meter-label">${name}</div>
                </div>
            `;
        });

        this.container.innerHTML = `
            <div class="dashboard-handle">
                <div class="handle-logo">
                    <svg viewBox="0 0 50 50" style="width: 18px; height: 18px;">
                        <polygon points="25,15 37,36 13,36" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linejoin="round" opacity="0.8"/>
                        <circle cx="18" cy="20" r="3.2" fill="none" stroke="var(--neon-blue)" stroke-width="2.5"/>
                        <circle cx="32" cy="20" r="3.2" fill="none" stroke="var(--neon-blue)" stroke-width="2.5"/>
                        <path d="M 18,24 C 12,24 12,30 18,30 C 23,30 27,24 32,24 C 38,24 38,30 32,30 C 27,30 23,24 18,24 Z" fill="none" stroke="var(--neon-blue)" stroke-width="2.5"/>
                        <path d="M 15,34 C 25,39 35,34 35,34" fill="none" stroke="var(--neon-blue)" stroke-width="2.5" stroke-linecap="round"/>
                    </svg>
                </div>
                <div class="meter-stack">
                    ${metersHtml}
                </div>
            </div>
            <div class="branding-banner">
                <div class="branding-left" style="display: flex; flex-direction: row; align-items: center; gap: 15px;">
                    <svg viewBox="0 0 50 50" style="width: 32px; height: 32px; flex-shrink: 0;">
                        <polygon points="25,12 40,38 10,38" fill="none" stroke="#ffffff" stroke-width="2" stroke-linejoin="round" opacity="0.9" style="filter: drop-shadow(0 0 3px rgba(255,255,255,0.8));"/>
                        <circle cx="16" cy="18" r="4" fill="none" stroke="var(--neon-blue)" stroke-width="2.5" style="filter: drop-shadow(0 0 4px var(--neon-blue));"/>
                        <circle cx="34" cy="18" r="4" fill="none" stroke="var(--neon-blue)" stroke-width="2.5" style="filter: drop-shadow(0 0 4px var(--neon-blue));"/>
                        <path d="M 16,22 C 10,22 10,32 16,32 C 22,32 28,22 34,22 C 40,22 40,32 34,32 C 28,32 22,22 16,22 Z" fill="none" stroke="var(--neon-blue)" stroke-width="2.5" style="filter: drop-shadow(0 0 4px var(--neon-blue));"/>
                        <path d="M 12,38 C 25,44 38,38 38,38" fill="none" stroke="var(--neon-blue)" stroke-width="2.5" stroke-linecap="round" style="filter: drop-shadow(0 0 4px var(--neon-blue));"/>
                    </svg>
                    <svg viewBox="0 0 110 45" style="height: 28px; flex-shrink: 0; filter: drop-shadow(0 0 2px rgba(0,0,0,0.5));">
                        <defs>
                            <filter id="neon-glow-cyan" x="-50%" y="-50%" width="200%" height="200%">
                                <feGaussianBlur stdDeviation="1" result="blur1"/>
                                <feGaussianBlur stdDeviation="2" result="blur2"/>
                                <feMerge>
                                    <feMergeNode in="blur2"/>
                                    <feMergeNode in="blur1"/>
                                    <feMergeNode in="SourceGraphic"/>
                                </feMerge>
                            </filter>
                            <filter id="neon-glow-orange" x="-50%" y="-50%" width="200%" height="200%">
                                <feGaussianBlur stdDeviation="1" result="blur1"/>
                                <feGaussianBlur stdDeviation="2" result="blur2"/>
                                <feMerge>
                                    <feMergeNode in="blur2"/>
                                    <feMergeNode in="blur1"/>
                                    <feMergeNode in="SourceGraphic"/>
                                </feMerge>
                            </filter>
                            <filter id="neon-glow-yellow" x="-50%" y="-50%" width="200%" height="200%">
                                <feGaussianBlur stdDeviation="1.2" result="blur1"/>
                                <feMerge>
                                    <feMergeNode in="blur1"/>
                                    <feMergeNode in="SourceGraphic"/>
                                </feMerge>
                            </filter>
                            <filter id="neon-glow-pink" x="-50%" y="-50%" width="200%" height="200%">
                                <feGaussianBlur stdDeviation="1.2" result="blur1"/>
                                <feMerge>
                                    <feMergeNode in="blur1"/>
                                    <feMergeNode in="SourceGraphic"/>
                                </feMerge>
                            </filter>
                            <linearGradient id="grad-orange-red" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#ff4500"/>
                                <stop offset="100%" stop-color="#ff8c00"/>
                            </linearGradient>
                            <linearGradient id="grad-cyan-blue" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#00f3ff"/>
                                <stop offset="100%" stop-color="#0055ff"/>
                            </linearGradient>
                        </defs>
                        <!-- Neon Border Outline (Top-Left Orange) -->
                        <path d="M 6,12 C 6,5 12,5 24,5 L 62,5 C 72,5 78,10 78,20 L 78,22 C 78,22 82,20 88,20 C 98,20 104,25 104,35" fill="none" stroke="url(#grad-orange-red)" stroke-width="2" stroke-linecap="round" filter="url(#neon-glow-orange)"/>
                        <!-- Neon Border Outline (Bottom-Right Cyan) -->
                        <path d="M 6,12 L 6,34 C 6,39 12,41 24,41 L 88,41 C 98,41 104,36 104,26 L 104,26" fill="none" stroke="url(#grad-cyan-blue)" stroke-width="2" stroke-linecap="round" filter="url(#neon-glow-cyan)"/>
                        <!-- Letters -->
                        <line x1="12" y1="9" x2="12" y2="34" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" filter="url(#neon-glow-cyan)"/>
                        <path d="M 20,22 L 20,30 A 4,4 0 0,0 28,30 L 28,22" fill="none" stroke="#ffea00" stroke-width="2.2" stroke-linecap="round" filter="url(#neon-glow-yellow)"/>
                        <path d="M 36,34 L 36,22 A 3,3 0 0,1 42,22 L 42,34 M 42,22 A 3,3 0 0,1 48,22 L 48,34" fill="none" stroke="#adff2f" stroke-width="2.2" stroke-linecap="round" filter="url(#neon-glow-yellow)"/>
                        <path d="M 60,34 L 60,22 M 60,25 A 4,4 0 1,0 60,33" fill="none" stroke="#ff007f" stroke-width="2.2" stroke-linecap="round" filter="url(#neon-glow-pink)"/>
                        <line x1="70" y1="22" x2="80" y2="34" stroke="#00f3ff" stroke-width="2.2" stroke-linecap="round" filter="url(#neon-glow-cyan)"/>
                        <line x1="80" y1="22" x2="70" y2="34" stroke="#ff00ea" stroke-width="2.2" stroke-linecap="round" filter="url(#neon-glow-pink)"/>
                    </svg>
                    <div style="display: flex; flex-direction: column;">
                        <div class="brand-site-name" style="font-size: 0.55rem; opacity: 0.7; letter-spacing: 2px;">MATCHBOX // ${version}</div>
                        <div class="brand-slogan" style="font-size: 0.45rem; opacity: 0.5; letter-spacing: 1px;">Sovereign WebXR Vessel</div>
                    </div>
                </div>
                <div class="branding-right">
                    <div class="visualizer-bars">
                        <div class="vbar"></div>
                        <div class="vbar"></div>
                        <div class="vbar"></div>
                        <div class="vbar"></div>
                        <div class="vbar"></div>
                    </div>
                    <button id="btn-voice-speech-top" class="voice-toggle-btn active" title="Toggle Voice Output (Speech Playback ON/OFF)" style="margin-left: 10px; background: rgba(0, 243, 255, 0.15); border: 1px solid var(--neon-blue); color: var(--neon-blue); font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; padding: 3px 8px; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 4px; transition: all 0.2s; white-space: nowrap;">🔊 VOICE ON</button>
                </div>
            </div>
            <div id="permissions-banner" style="display:none; margin: 10px 15px 0; padding: 10px 12px; background: rgba(255, 170, 0, 0.1); border: 1px solid rgba(255, 170, 0, 0.4); border-radius: 4px; flex-direction: column; gap: 6px; font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: #ffaa00; text-shadow: 0 0 5px rgba(255, 170, 0, 0.2);">
                <div style="display:flex; justify-content:space-between; align-items:center; gap: 8px;">
                    <span class="permission-label" style="font-weight: 700; letter-spacing: 0.5px;">⚠️ PERMISSIONS REQUIRED FOR QUEST VR</span>
                    <button id="btn-grant-permissions" style="background:#ffaa00; color:#000; border:none; padding:3px 8px; font-family:'Orbitron'; font-weight:700; font-size:0.6rem; border-radius:2px; cursor:pointer; letter-spacing:1px; white-space:nowrap; box-shadow:0 0 8px rgba(255,170,0,0.3); transition: transform 0.2s;">GRANT ACCESS</button>
                </div>
                <div style="font-size:0.6rem; opacity:0.8; line-height:1.3; font-family:'Share Tech Mono';">
                    Quest standalone VR blocks camera/microphone access prompts inside immersive WebXR. You must click GRANT ACCESS in 2D mode first to avoid unexpected VR crashes!
                </div>
            </div>
            <div class="telemetry-strip">
                <div class="tel-item"><span>SYS</span>ONLINE</div>
                <div class="tel-item" id="tel-xr"><span>XR</span>DETECTING...</div>
                <div class="tel-item" id="tel-model-hub-shortcut" style="cursor: pointer; display: flex; align-items: center; transition: all 0.2s;" title="Active Cognitive Model. Click to open Model Hub.">
                    <span>AI</span>
                    <span id="tel-provider-name" style="color: #fff !important; opacity: 0.95 !important; font-weight: bold !important; margin-right: 3px;">Detecting</span>
                    <span style="color: var(--neon-blue); margin: 0 2px;">/</span>
                    <span id="tel-model-name" style="color: var(--neon-pink) !important; opacity: 0.95 !important;">...</span>
                </div>
                <div class="tel-item" id="xr-controller-status" style="cursor: pointer; display: flex; align-items: center; transition: all 0.2s; border: 1px solid transparent; border-radius: 3px; padding: 0 4px;" title="Connected WebXR Controllers">
                    <span>PAD</span>🎮 --
                </div>
                <div class="tel-item"><span>MEM</span>LOCAL/DEXIE</div>
                <div class="tel-item" id="tel-agent-status" style="cursor: pointer; display: flex; align-items: center; transition: all 0.2s;" title="Autonomous Agent Status. Click to open Agency Tools.">
                    <span>JEN</span><span id="tel-agent-state">—</span>
                </div>
                <div class="tel-item"><span>CORE</span><span id="tel-core-mode">HYBRID</span></div>
                <button id="btn-enter-xr" style="display:none; background:rgba(0,243,255,0.15); border:1px solid var(--neon-blue); color:var(--neon-blue); font-family:'Orbitron'; font-size:0.55rem; padding:2px 8px; cursor:pointer; border-radius:2px; letter-spacing:1px; text-transform:uppercase; transition:var(--transition);">ENTER XR</button>
                <div class="neural-nodes">
                    <div class="node" id="node-local"><div class="node-dot"></div>LOCAL</div>
                    <div class="node" id="node-hybrid"><div class="node-dot"></div>HYBRID</div>
                    <div class="node" id="node-cloud"><div class="node-dot"></div>CLOUD</div>
                </div>
            </div>
            <div class="nav-tabs">
                <div class="nav-item" id="nav-group-intel" style="${hasVisibleIntel ? '' : 'display: none !important;'}">
                    INTELLIGENCE
                    <div class="submenu">
                        <div class="sub-item ${this.activeTab === 'cognition' ? 'active' : ''}" data-tab="cognition" style="${tabStyle('cognition')}">Chat with Jen</div>
                        <div class="sub-item ${this.activeTab === 'thoughts' ? 'active' : ''}" data-tab="thoughts" style="${tabStyle('thoughts')}">Thoughts</div>
                        <div class="sub-item ${this.activeTab === 'profile' ? 'active' : ''}" data-tab="profile" style="${tabStyle('profile')}">Profile</div>
                        <div class="sub-item ${this.activeTab === 'swarm' ? 'active' : ''}" data-tab="swarm" style="${tabStyle('swarm')}">Swarm Drones</div>
                        <div class="sub-item ${this.activeTab === 'agency' ? 'active' : ''}" data-tab="agency" style="${tabStyle('agency')}">Agency Tools</div>
                        <div class="sub-item exit-menu-item" style="color: var(--neon-pink); border-top: 1px solid rgba(255, 0, 127, 0.2); margin-top: 4px;" data-action="exit">Exit Menu</div>
                    </div>
                </div>
                <div class="nav-item" id="nav-group-prod" style="${hasVisibleProd ? '' : 'display: none !important;'}">
                    PRODUCTION
                    <div class="submenu">
                        <div class="sub-item ${this.activeTab === 'dreamscape' ? 'active' : ''}" data-tab="dreamscape" style="${tabStyle('dreamscape')}">Dreamscape</div>
                        <div class="sub-item ${this.activeTab === 'modelhub' ? 'active' : ''}" data-tab="modelhub" style="${tabStyle('modelhub')}">Model Hub</div>
                        <div class="sub-item ${this.activeTab === 'chronicle' ? 'active' : ''}" data-tab="chronicle" style="${tabStyle('chronicle')}">Chronicle</div>
                        <div class="sub-item ${this.activeTab === 'monetizing' ? 'active' : ''}" data-tab="monetizing" style="${tabStyle('monetizing')}">Monetizing</div>
                    </div>
                </div>
                <div class="nav-item" id="nav-group-ops" style="${hasVisibleOps ? '' : 'display: none !important;'}">
                    OPERATIONS
                    <div class="submenu">
                        <div class="sub-item ${this.activeTab === 'diagnosis' ? 'active' : ''}" data-tab="diagnosis" style="${tabStyle('diagnosis')}">Diagnosis</div>
                        <div class="sub-item ${this.activeTab === 'nucleus' ? 'active' : ''}" data-tab="nucleus" style="${tabStyle('nucleus')}">Nucleus Matrix</div>
                        <div class="sub-item ${this.activeTab === 'vision' ? 'active' : ''}" data-tab="vision" style="${tabStyle('vision')}">Vision Senses</div>
                        <div class="sub-item ${this.activeTab === 'branding' ? 'active' : ''}" data-tab="branding" style="${tabStyle('branding')}">Branding Lab</div>
                        <div class="sub-item ${this.activeTab === 'webvm' ? 'active' : ''}" data-tab="webvm" style="${tabStyle('webvm')}">WebVM Terminal</div>
                        <div class="sub-item ${this.activeTab === 'videochat' ? 'active' : ''}" data-tab="videochat" style="${tabStyle('videochat')}">VideoChat</div>
                        <div class="sub-item ${this.activeTab === 'settings' ? 'active' : ''}" data-tab="settings" style="${tabStyle('settings')}">Settings</div>
                        <div class="sub-item ${this.activeTab === 'tokenslayer' ? 'active' : ''}" data-tab="tokenslayer" style="${tabStyle('tokenslayer')}">🧠 Foveated Memory</div>
                        <div class="sub-item ${this.activeTab === 'forgenursery' ? 'active' : ''}" data-tab="forgenursery" style="${tabStyle('forgenursery')}">🌱 Forge Nursery</div>
                        <div class="sub-item ${this.activeTab === 'forgeindex' ? 'active' : ''}" data-tab="forgeindex" style="${tabStyle('forgeindex')}">📋 Feature Inventory</div>
                        <div class="sub-item ${this.activeTab === 'envmapping' ? 'active' : ''}" data-tab="envmapping" style="${tabStyle('envmapping')}">🗺️ Env Mapping</div>
                        <div class="sub-item ${this.activeTab === 'avatarcameras' ? 'active' : ''}" data-tab="avatarcameras" style="${tabStyle('avatarcameras')}">📷 Avatar Cameras</div>
                        <div class="sub-item ${this.activeTab === 'envmanagement' ? 'active' : ''}" data-tab="envmanagement" style="${tabStyle('envmanagement')}">🏠 Env Management</div>
                        <div class="sub-item ${this.activeTab === 'controllers' ? 'active' : ''}" data-tab="controllers" style="${tabStyle('controllers')}">🎮 Controllers</div>
                    </div>
                </div>
                <div class="nav-item" id="nav-group-dev" style="${hasVisibleDev ? '' : 'display: none !important;'}">
                    🔧 DEV
                    <div class="submenu">
                        <div class="sub-item ${this.activeTab === 'devtools' ? 'active' : ''}" data-tab="devtools" style="${tabStyle('devtools')}">DevTools Console</div>
                        <div class="sub-item ${this.activeTab === 'featuremap' ? 'active' : ''}" data-tab="featuremap" style="${tabStyle('featuremap')}">Feature Map</div>
                    </div>
                </div>
            </div>
            <div class="dashboard-content">
                <div class="breadcrumb" id="breadcrumb-info">FoveAI MATCHBOX // ${this.activeTab.toUpperCase()}</div>
                <div id="tab-content-area" style="flex: 1; display: flex; flex-direction: column; min-height: 0; overflow-y: auto; overflow-x: hidden;">
                    <!-- Content injected here -->
                </div>
            </div>
            <div class="dashboard-footer" id="dashboard-footer">
                <div id="footer-actions" style="display:flex; gap:10px; margin-bottom:10px;">
                    <button id="btn-footer-reset" style="flex:1; background:rgba(255,0,127,0.1); border:1px solid var(--neon-pink); color:#fff; font-family:'Orbitron'; font-size:0.6rem; padding:8px; cursor:pointer; border-radius:4px; text-transform:uppercase; letter-spacing:1px;">🔄 RESET AVATAR</button>
                    <button id="btn-footer-sleep" style="flex:1; background:rgba(0,243,255,0.1); border:1px solid var(--neon-blue); color:#fff; font-family:'Orbitron'; font-size:0.6rem; padding:8px; cursor:pointer; border-radius:4px; text-transform:uppercase; letter-spacing:1px;">💤 SCREEN SAVER</button>
                    <button id="btn-footer-stream" style="flex:1; background:rgba(57,255,20,0.1); border:1px solid #39ff14; color:#fff; font-family:'Orbitron'; font-size:0.6rem; padding:8px; cursor:pointer; border-radius:4px; text-transform:uppercase; letter-spacing:1px;">📺 STREAM DESKTOP</button>
                </div>
                <div id="attachment-preview-container" style="display: none; align-items: center; padding: 5px 10px; background: rgba(0, 243, 255, 0.05); border: 1px dashed rgba(0, 243, 255, 0.3); border-radius: 8px; margin-bottom: 8px;">
                    <img id="attachment-preview-img" style="max-height: 40px; border-radius: 4px; border: 1px solid var(--neon-blue); margin-right: 10px;">
                    <span id="attachment-preview-name" style="font-size: 0.8rem; color: #a0a0a0; flex-grow: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"></span>
                    <button id="btn-remove-attachment" style="background: transparent; border: none; color: var(--neon-pink); cursor: pointer; font-size: 1.1rem; padding: 0 5px;">✕</button>
                </div>
                <div class="input-wrapper">
                    <button class="btn-attach" id="btn-attach" title="Attach Image">📎</button>
                    <input type="text" id="chat-input" placeholder="Initiate cognitive link..." autocomplete="off">
                    <button class="btn-mic" id="btn-mic" title="Voice Input Microphone">🎤</button>
                    <button class="btn-voice active" id="btn-voice-output" title="Toggle Voice Speech Output (Playback ON/OFF)">🔊</button>
                    <button class="btn-deep" id="btn-deep-thought" title="Deep Thought Mode (slower, deeper reasoning)">🧠</button>
                    <button class="btn-thought active" id="btn-thought-stream" title="Toggle Thought Stream Notices">💬</button>
                    <button class="btn-hud active" id="btn-hud-toggle" title="Toggle always-visible 3D HUD Indicators in VR">🖥️</button>
                    <button class="btn-privacy" id="btn-privacy" title="Privacy Mode (OpenRouter — no data logging)">🔒</button>
                    <button class="btn-send" id="btn-send">SEND</button>
                    <input type="file" id="file-attach-input" style="display: none;">
                </div>
            </div>
        `;

        const btnFooterReset = this.container.querySelector('#btn-footer-reset');
        btnFooterReset?.addEventListener('click', () => {
            if ((window as any).foveaiAvatar) {
                (window as any).foveaiAvatar.nuclearReset();
                this.log('Avatar System Reset Triggered', 'var(--neon-pink)');
            }
        });

        const btnFooterSleep = this.container.querySelector('#btn-footer-sleep');
        btnFooterSleep?.addEventListener('click', () => {
            this.toggleSleepMode();
        });

        const btnFooterStream = this.container.querySelector('#btn-footer-stream');
        btnFooterStream?.addEventListener('click', () => {
            window.dispatchEvent(new CustomEvent('foveai_start_desktop_stream'));
        });

        const sendBtn = this.container.querySelector('#btn-send');
        const chatInput = this.container.querySelector('#chat-input') as HTMLInputElement;
        const fileInput = this.container.querySelector('#file-attach-input') as HTMLInputElement;
        const btnAttach = this.container.querySelector('#btn-attach');
        const previewContainer = this.container.querySelector('#attachment-preview-container') as HTMLElement;
        const previewImg = this.container.querySelector('#attachment-preview-img') as HTMLImageElement;
        const previewName = this.container.querySelector('#attachment-preview-name') as HTMLElement;
        const btnRemoveAttachment = this.container.querySelector('#btn-remove-attachment');
        
        btnAttach?.addEventListener('click', () => {
            if ((window as any).xrSession) {
                // Open attachment options modal inside WebXR!
                this.openAttachmentOptions();
            } else {
                fileInput?.click();
            }
        });

        fileInput?.addEventListener('change', () => {
            const file = fileInput.files?.[0];
            if (file) {
                const isImage = file.type.startsWith('image/');
                const reader = new FileReader();
                reader.onload = (event) => {
                    const result = event.target?.result;
                    if (isImage) {
                        const dataUrl = result as string;
                        this.attachedImageDataUrl = dataUrl;
                        this.attachedImageBase64 = dataUrl.split(',')[1];
                        this.attachedImageType = file.type;
                        this.attachedImageName = file.name;
                        this.attachedFileContent = null;
                        this.attachedFileName = null;
                        
                        if (previewImg) {
                            previewImg.src = dataUrl;
                            previewImg.style.cursor = 'pointer';
                            previewImg.onclick = () => {
                                const overlay = document.createElement('div');
                                overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.9); z-index: 99999; display: flex; justify-content: center; align-items: center; cursor: zoom-out;';
                                const fullImg = document.createElement('img');
                                fullImg.src = dataUrl;
                                fullImg.style.cssText = 'max-width: 95%; max-height: 95%; object-fit: contain; border: 2px solid var(--neon-blue); box-shadow: 0 0 30px var(--neon-blue);';
                                overlay.appendChild(fullImg);
                                overlay.onclick = () => document.body.removeChild(overlay);
                                document.body.appendChild(overlay);
                            };
                        }
                    } else {
                        // Document / Text file
                        const textContent = result as string;
                        this.attachedFileContent = textContent;
                        this.attachedFileName = file.name;
                        this.attachedImageBase64 = null;
                        this.attachedImageType = null;
                        this.attachedImageName = null;
                        this.attachedImageDataUrl = null;
                        
                        if (previewImg) {
                            previewImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="%2300f3ff" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
                            previewImg.style.cursor = 'default';
                            previewImg.onclick = null;
                        }
                    }
                    if (previewName) {
                        previewName.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
                    }
                    if (previewContainer) previewContainer.style.display = 'flex';
                };
                
                if (isImage) {
                    reader.readAsDataURL(file);
                } else {
                    reader.readAsText(file);
                }
            }
        });

        const clearAttachment = () => {
            this.attachedImageBase64 = null;
            this.attachedImageType = null;
            this.attachedImageName = null;
            this.attachedImageDataUrl = null;
            this.attachedFileContent = null;
            this.attachedFileName = null;
            if (fileInput) fileInput.value = '';
            if (previewContainer) previewContainer.style.display = 'none';
        };

        btnRemoveAttachment?.addEventListener('click', (e) => {
            e.stopPropagation();
            clearAttachment();
        });

        const handleSend = () => {
            let text = chatInput.value.trim();
            if (text || this.attachedImageBase64 || this.attachedFileContent) {
                // If there's a text/document file attached, append it to the message text
                if (this.attachedFileContent && this.attachedFileName) {
                    const formattedAttachment = `\n\n[Attached Document: ${this.attachedFileName}]\n\`\`\`\n${this.attachedFileContent}\n\`\`\``;
                    text = text ? `${text}${formattedAttachment}` : formattedAttachment.trim();
                }
                
                const attachments = this.attachedImageBase64 ? [{
                    name: this.attachedImageName || `upload_${Date.now()}.png`,
                    type: 'image',
                    mediaType: this.attachedImageType || 'image/png',
                    base64: this.attachedImageBase64
                }] : undefined;
                
                this.onSendMessage(text, attachments, this.attachedImageDataUrl || undefined);
                chatInput.value = '';
                clearAttachment();
            }
        };

        sendBtn?.addEventListener('click', handleSend);
        chatInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleSend();
        });

        const btnMic = this.container.querySelector('#btn-mic');
        btnMic?.addEventListener('click', () => this.toggleListening());

        const btnVoiceTop = this.container.querySelector('#btn-voice-speech-top');
        btnVoiceTop?.addEventListener('click', () => this.toggleVoiceOutput());

        const btnVoiceInput = this.container.querySelector('#btn-voice-output');
        btnVoiceInput?.addEventListener('click', () => this.toggleVoiceOutput());

        const btnDeepThought = this.container.querySelector('#btn-deep-thought');
        btnDeepThought?.addEventListener('click', () => this.toggleDeepThought());

        const btnThoughtStream = this.container.querySelector('#btn-thought-stream');
        btnThoughtStream?.addEventListener('click', () => this.toggleThoughtStream());

        const btnHudToggle = this.container.querySelector('#btn-hud-toggle');
        btnHudToggle?.addEventListener('click', () => this.toggle3dHud());

        const btnPrivacy = this.container.querySelector('#btn-privacy');
        btnPrivacy?.addEventListener('click', () => this.togglePrivacyMode());

        // Add event listeners for nav tabs
        this.container.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const target = e.currentTarget as HTMLElement;
                const wasHover = target.classList.contains('hover');
                
                // Clear all hovers
                this.container.querySelectorAll('.nav-item').forEach(n => n.classList.remove('hover'));
                
                // Toggle this one
                if (!wasHover) {
                    target.classList.add('hover');
                }
            });
        });

        this.container.querySelectorAll('.sub-item').forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const target = e.currentTarget as HTMLElement;
                const tab = target.getAttribute('data-tab');
                if (tab) {
                    this.setActiveTab(tab);
                }
                const action = target.getAttribute('data-action');
                if (action === 'exit') {
                    this.toggle(false);
                }
                
                // Close all submenus after clicking an option
                this.container.querySelectorAll('.nav-item').forEach(n => n.classList.remove('hover'));
            });
        });

        // Click handler for telemetry strip AI shortcut to go to Model Hub
        const modelHubShortcut = this.container.querySelector('#tel-model-hub-shortcut');
        modelHubShortcut?.addEventListener('click', () => {
            this.setActiveTab('modelhub');
        });

        // Click handler for telemetry strip JEN status → navigate to Agency Tools
        const agentStatusEl = this.container.querySelector('#tel-agent-status');
        agentStatusEl?.addEventListener('click', () => {
            this.setActiveTab('agency');
        });

        this.updateContent();

        // Initialize meter references
        meterNames.forEach(name => {
            const el = this.container.querySelector(`#meter-${name}`) as HTMLElement;
            if (el) this.meters[name] = el;
        });

        // XR availability check and button wiring
        this.detectXR();

        // Asynchronously fetch and render model info in the telemetry strip
        this.updateActiveModelInfo();

        // Add XR entry button to document body (fixed position, bottom-left)
        if (!document.getElementById('xr-entry-btn')) {
            const xrBtn = document.createElement('div');
            xrBtn.id = 'xr-entry-btn';
            xrBtn.innerHTML = `
                <svg viewBox="0 0 24 24">
                    <path d="M2 10 L5 7 L9 10 L12 8 L15 10 L19 7 L22 10"/>
                    <path d="M2 10 L2 14 L5 17 L9 14 L2 10"/>
                    <path d="M22 10 L22 14 L19 17 L15 14 L22 10"/>
                    <circle cx="6" cy="12" r="2.5"/>
                    <circle cx="18" cy="12" r="2.5"/>
                    <line x1="8.5" y1="12" x2="15.5" y2="12"/>
                </svg>
                <span class="xr-label">ENTER XR</span>
                <span class="xr-tooltip">Checking XR...</span>
            `;
            xrBtn.classList.add('xr-unavailable');
            const xrTooltipInit = xrBtn.querySelector('.xr-tooltip');
            if (xrTooltipInit) xrTooltipInit.textContent = 'Detecting XR capabilities...';
            xrBtn.addEventListener('click', () => {
                this.log('Requesting XR session...', 'var(--neon-blue)');
                window.dispatchEvent(new CustomEvent('foveai_toggle_immersive', { detail: 'ar' }));
            });
            document.body.appendChild(xrBtn);
        }
    }

    private async detectXR() {
        const btnXR = this.container.querySelector('#btn-enter-xr') as HTMLElement;
        const telXR = this.container.querySelector('#tel-xr') as HTMLElement;
        const xrEntryBtn = document.getElementById('xr-entry-btn');
        const xrTooltip = xrEntryBtn?.querySelector('.xr-tooltip');

        const isSecure = window.isSecureContext;
        const hasXR = !!navigator.xr;
        const userAgent = navigator.userAgent;
        this.log(`XR Diagnostics: navigator.xr=${hasXR}, isSecureContext=${isSecure}, protocol=${location.protocol}, host=${location.host}`, 'var(--neon-blue)');
        this.log(`XR User-Agent: ${userAgent.substring(0, 120)}`, 'var(--neon-blue)');

        if (!navigator.xr && isSecure) {
            this.log('XR: navigator.xr missing on secure context — showing force override', '#ffaa00');
            
            if (telXR) telXR.innerHTML = '<span>XR</span>FORCE';
            if (btnXR) {
                btnXR.style.display = 'inline-flex';
                btnXR.textContent = 'FORCE XR';
                btnXR.style.borderColor = 'var(--neon-pink)';
                btnXR.addEventListener('click', () => {
                    this.log('Force-requesting XR session...', 'var(--neon-pink)');
                    window.dispatchEvent(new CustomEvent('foveai_toggle_immersive', { detail: 'ar' }));
                });
            }
            if (xrEntryBtn) {
                xrEntryBtn.classList.remove('xr-unavailable');
                xrEntryBtn.classList.add('xr-ready');
                xrEntryBtn.style.borderColor = 'var(--neon-pink)';
                const xrLabel = xrEntryBtn.querySelector('.xr-label');
                if (xrLabel) xrLabel.textContent = 'FORCE XR';
                if (xrTooltip) xrTooltip.textContent = 'WebXR API not detected. Click to force attempt (Quest 3 may still support XR).';
            }
            return;
        }

        if (!navigator.xr) {
            if (telXR) telXR.innerHTML = '<span>XR</span>NO HTTPS';
            if (xrEntryBtn) {
                xrEntryBtn.classList.remove('xr-ready');
                xrEntryBtn.classList.add('xr-unavailable');
                const xrLabel = xrEntryBtn.querySelector('.xr-label');
                if (xrLabel) xrLabel.textContent = 'NO XR';
            }
            if (xrTooltip) xrTooltip.textContent = 'WebXR requires HTTPS. Use https://foveai.1um6a.se';
            this.log(`XR unavailable: not secure context (protocol=${location.protocol})`, '#ff007f');
            return;
        }

        try {
            const arSupported = await navigator.xr.isSessionSupported('immersive-ar');
            const vrSupported = await navigator.xr.isSessionSupported('immersive-vr');

            if (arSupported || vrSupported) {
                const mode = arSupported ? 'ar' : 'vr';
                const label = arSupported ? 'ENTER XR' : 'ENTER VR';

                if (btnXR) {
                    btnXR.style.display = 'inline-flex';
                    btnXR.textContent = arSupported ? 'ENTER AR' : 'ENTER VR';
                    btnXR.addEventListener('click', () => {
                        this.log(`Requesting ${mode.toUpperCase()} session...`, 'var(--neon-blue)');
                        window.dispatchEvent(new CustomEvent('foveai_toggle_immersive', { detail: mode }));
                    });
                }

                if (xrEntryBtn) {
                    xrEntryBtn.classList.remove('xr-unavailable');
                    xrEntryBtn.classList.add('xr-ready');
                    const xrLabel = xrEntryBtn.querySelector('.xr-label');
                    if (xrLabel) xrLabel.textContent = label;
                }
                if (xrTooltip) xrTooltip.textContent = `Click to enter ${mode.toUpperCase()} mode`;

                if (telXR) telXR.innerHTML = `<span>XR</span>${arSupported ? 'AR' : 'VR'} READY`;
                this.log(`XR detected: ${arSupported ? 'AR' : 'VR'} available`, '#39ff14');
            } else {
                if (telXR) telXR.innerHTML = '<span>XR</span>DESKTOP';
                if (xrEntryBtn) {
                    xrEntryBtn.classList.add('xr-unavailable');
                    const xrLabel = xrEntryBtn.querySelector('.xr-label');
                    if (xrLabel) xrLabel.textContent = 'DESKTOP';
                }
                const xrUrl = window.location.href;
                if (xrTooltip) xrTooltip.textContent = `Open this URL in Quest 3 browser for XR: ${xrUrl}`;
                this.log('XR: Desktop mode — no immersive headset on this browser', 'var(--neon-blue)');
                this.log(`XR: For Quest 3 XR, open this URL in the Quest 3 native browser: ${xrUrl}`, '#ffaa00');
                this.log('XR: Remote desktop clients run the browser on the host PC — XR is only available in the headset browser', '#ffaa00');
            }
        } catch (e) {
            if (telXR) telXR.innerHTML = '<span>XR</span>ERROR';
            if (xrEntryBtn) {
                xrEntryBtn.classList.add('xr-unavailable');
                const xrLabel = xrEntryBtn.querySelector('.xr-label');
                if (xrLabel) xrLabel.textContent = 'XR ERR';
            }
            if (xrTooltip) xrTooltip.textContent = `XR detection error: ${e}`;
            this.log(`XR detection error: ${e}`, '#ff007f');
        }
    }

    private speechRecognition: any = null;
    public isListening: boolean = false;
    private mediaRecorder: MediaRecorder | null = null;
    private audioChunks: Blob[] = [];
    private discardAudio: boolean = false;
    private mediaStream: MediaStream | null = null;
    private useMediaRecorderSTT: boolean = false;
    private audioContext: AudioContext | null = null;
    private audioSourceNode: MediaStreamAudioSourceNode | null = null;
    private analyser: AnalyserNode | null = null;
    private vadInterval: any = null;

    public toggleListening() {
        if (this.isListening) {
            this.stopListening(true); // Discard recording on manual mute
        } else {
            this.startListening();
        }
    }

    public toggleDeepThought() {
        this.deepThought = !this.deepThought;
        const btnDeep = this.container.querySelector('#btn-deep-thought');
        const chatInput = this.container.querySelector('#chat-input') as HTMLInputElement;
        if (this.deepThought) {
            btnDeep?.classList.add('active');
            if (chatInput) chatInput.placeholder = 'Initiate deep cognitive link... 🧠';
            this.log('[BRN] Deep Thought ON -- cloud reasoning model', '#9333ea');
        } else {
            btnDeep?.classList.remove('active');
            if (chatInput) chatInput.placeholder = 'Initiate cognitive link...';
            this.log('Deep Thought OFF', '#ffaa00');
        }

        // Propagate deep thought toggle to backend
        fetch('/api/soul/deep_thought', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deep_thought: this.deepThought })
        }).catch(e => console.error('[XR] Failed to propagate deep thought toggle', e));
    }

    public toggleThoughtStream() {
        this.showThoughtStream = !this.showThoughtStream;
        const btnThought = this.container.querySelector('#btn-thought-stream');
        if (this.showThoughtStream) {
            btnThought?.classList.add('active');
            this.log('Thought Stream notices ON', 'var(--neon-blue)');
        } else {
            btnThought?.classList.remove('active');
            this.log('Thought Stream notices OFF', '#ffaa00');
            try {
                const toast = document.getElementById('thought-toast');
                if (toast) toast.classList.remove('show');
            } catch (e) {}
        }

        // Propagate thinking toggle to backend
        fetch('/api/soul/thinking', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ thinking: this.showThoughtStream })
        }).catch(e => console.error('[XR] Failed to propagate thinking toggle', e));
    }

    private initThinkingConfig() {
        fetch('/api/soul/thinking')
            .then(res => res.json())
            .then(data => {
                if (data && typeof data.thinking === 'boolean') {
                    this.showThoughtStream = data.thinking;
                    const btnThought = this.container.querySelector('#btn-thought-stream');
                    if (this.showThoughtStream) {
                        btnThought?.classList.add('active');
                    } else {
                        btnThought?.classList.remove('active');
                    }
                }
            })
            .catch(e => console.error('[XR] Failed to fetch initial thinking config', e));

        fetch('/api/soul/deep_thought')
            .then(res => res.json())
            .then(data => {
                if (data && typeof data.deep_thought === 'boolean') {
                    this.deepThought = data.deep_thought;
                    const btnDeep = this.container.querySelector('#btn-deep-thought');
                    const chatInput = this.container.querySelector('#chat-input') as HTMLInputElement;
                    if (this.deepThought) {
                        btnDeep?.classList.add('active');
                        if (chatInput) chatInput.placeholder = 'Initiate deep cognitive link... 🧠';
                    } else {
                        btnDeep?.classList.remove('active');
                        if (chatInput) chatInput.placeholder = 'Initiate cognitive link...';
                    }
                }
            })
            .catch(e => console.error('[XR] Failed to fetch initial deep thought config', e));

        const hudEnabled = localStorage.getItem('foveai_3d_hud_enabled') !== 'false';
        const btnHud = this.container.querySelector('#btn-hud-toggle');
        if (hudEnabled) {
            btnHud?.classList.add('active');
        } else {
            btnHud?.classList.remove('active');
        }
    }

    public toggle3dHud() {
        const enabled = localStorage.getItem('foveai_3d_hud_enabled') !== 'false';
        const nextState = !enabled;
        localStorage.setItem('foveai_3d_hud_enabled', nextState ? 'true' : 'false');
        
        const btnHud = this.container.querySelector('#btn-hud-toggle');
        if (nextState) {
            btnHud?.classList.add('active');
            this.log('3D HUD Indicators ON', 'var(--neon-blue)');
        } else {
            btnHud?.classList.remove('active');
            this.log('3D HUD Indicators OFF', '#ffaa00');
        }
        
        window.dispatchEvent(new CustomEvent('foveai_3d_hud_toggle', { detail: { enabled: nextState } }));
    }

    public async togglePrivacyMode() {
        this.privacyMode = !this.privacyMode;
        const btnPrivacy = this.container.querySelector('#btn-privacy');
        const chatInput = this.container.querySelector('#chat-input') as HTMLInputElement;
        if (this.privacyMode) {
            btnPrivacy?.classList.add('active');
            if (chatInput) chatInput.placeholder = '🔒 Privacy mode — LM Studio (Abliterated)';
            this.log('[PRV] Privacy Mode ON -- loading uncensored Abliterated brain...', '#9333ea');
        } else {
            btnPrivacy?.classList.remove('active');
            if (chatInput) chatInput.placeholder = 'Initiate cognitive link...';
            this.log('Privacy Mode OFF -- loading advanced Reasoning brain...', '#ffaa00');
        }

        try {
            const response = await fetch('/api/soul/lmstudio/hotswap', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ privacy: this.privacyMode })
            });
            if (response.ok) {
                const res = await response.json();
                if (res.success) {
                    this.log(`[HSwap] LM Studio dynamically loaded: ${res.model}`, '#39ff14');
                } else {
                    this.log(`[HSwap] Hot-swap failed: ${res.error}`, '#ff007f');
                }
            }
        } catch (e) {
            console.error('[HSwap] Failed to send hotswap request:', e);
        }
    }

    public startListening() {
        // Always use MediaRecorder + continuous VAD pipeline.
        // SpeechRecognition API is one-shot and breaks the continuous listening loop.
        this.useMediaRecorderSTT = true;
        this.startMediaRecorderSTT();
    }

    private async startMediaRecorderSTT() {
        try {
            const cachedStream = (window as any).foveaiCachedMicStream as MediaStream | null;
            if (cachedStream && cachedStream.active) {
                this.mediaStream = cachedStream;
                this.log('Using pre-cached microphone stream', 'var(--neon-blue)');
            } else {
                const isInXR = !!(window as any).xrSession;
                if (isInXR) {
                    this.log('⚠️ [VAD] Microphone stream is inactive or not cached. Access denied inside VR to prevent crash!', '#ffaa00');
                    this.log('⚠️ Please exit VR, grant microphone permissions on the desktop dashboard first, then re-enter.', '#ffaa00');
                    this.isListening = false;
                    this.updateVadIndicator();
                    const btnMic = this.container.querySelector('#btn-mic');
                    if (btnMic) btnMic.classList.remove('listening');
                    return;
                }
                this.mediaStream = await navigator.mediaDevices.getUserMedia({ 
                    audio: { 
                        echoCancellation: true, 
                        noiseSuppression: true, 
                        autoGainControl: true 
                    } 
                });

                // WORKAROUND: Keep mic stream active/alive in Chromium/Android/Oculus Browser
                try {
                    const aud = new Audio();
                    aud.srcObject = this.mediaStream;
                    aud.muted = true;
                    aud.play().catch(e => console.warn('[VAD-Fresh] Workaround audio play failed:', e));
                    (window as any).foveaiWorkaroundAudio = aud;
                } catch (err) {
                    console.warn('[VAD-Fresh] Workaround audio setup failed:', err);
                }
            }
            this.mediaRecorder = new MediaRecorder(this.mediaStream);
            this.audioChunks = [];
            const recordingStartTime = Date.now();

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                if (this.discardAudio) {
                    this.log('[VAD] Audio recording discarded (typed message or cancel)', 'var(--neon-blue)');
                    this.discardAudio = false; // Reset flag
                    return;
                }
                const recordingDurationMs = Date.now() - recordingStartTime;
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                // Guard: skip blobs that are too short or too small.
                // Whisper hallucinates ("you you you", "alright alright") on near-silent
                // or sub-second clips — reject them before they reach the backend.
                if (recordingDurationMs < 800 || audioBlob.size < 3000) {
                    this.log(`[VAD] Clip too short (${recordingDurationMs}ms, ${audioBlob.size}B) — skipping STT`, '#ffaa00');
                } else {
                    await this.transcribeViaSoul(audioBlob);
                }
                const cachedStream = (window as any).foveaiCachedMicStream as MediaStream | null;
                if (this.mediaStream && this.mediaStream !== cachedStream) {
                    this.mediaStream.getTracks().forEach(t => t.stop());
                }
                this.mediaStream = null;
            };

            this.mediaRecorder.start();
            this.isListening = true;
            this.updateVadIndicator();
            this.startVAD(this.mediaStream);
            const btnMic = this.container.querySelector('#btn-mic');
            if (btnMic) btnMic.classList.add('listening');
            this.log('[MIC] Listening (MediaRecorder + VAD)...', 'var(--neon-pink)');
        } catch (err) {
            this.log(`MediaRecorder STT failed: ${err}`, '#ff007f');
            this.isListening = false;
            this.updateVadIndicator();
        }
    }

    private async transcribeViaSoul(audioBlob: Blob) {
        try {
            const base64data = await new Promise<string>((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => {
                    const result = reader.result as string;
                    resolve(result.split(',')[1]);
                };
                reader.onerror = reject;
                reader.readAsDataURL(audioBlob);
            });

            const response = await fetch('/api/soul/stt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    audio_base64: base64data,
                    format: 'audio/webm',
                    filename: 'recording.webm'
                })
            });
            if (response.ok) {
                const data = await response.json();
                const transcript = data.text || data.transcript || '';
                if (transcript) {
                    this.log(`[MIC] Heard: "${transcript}"`, 'var(--neon-blue)');
                    const chatInput = this.container.querySelector('#chat-input') as HTMLInputElement;
                    if (chatInput) chatInput.value = transcript;
                    this.onSendMessage(transcript);
                } else if (data.error) {
                    this.log(`STT Proxy Error: ${data.error}`, '#ff007f');
                } else {
                    this.log('STT: No speech detected', '#ffaa00');
                }
            } else {
                this.log(`STT endpoint returned ${response.status}`, '#ff007f');
            }
        } catch (err) {
            this.log(`STT transcription failed: ${err}`, '#ff007f');
        }
        this.stopVAD();
        this.isListening = false;
        this.updateVadIndicator();
        const btnMic = this.container.querySelector('#btn-mic');
        if (btnMic) btnMic.classList.remove('listening');
    }

    public stopListening(discard: boolean = false) {
        this.stopVAD();
        if (discard) {
            this.discardAudio = true;
        }
        if (this.useMediaRecorderSTT) {
            if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                this.mediaRecorder.stop();
            }
        } else {
            if (this.speechRecognition) {
                this.speechRecognition.stop();
            }
            this.isListening = false;
            this.updateVadIndicator();
            const btnMic = this.container.querySelector('#btn-mic');
            if (btnMic) btnMic.classList.remove('listening');
        }
    }

    public toggleVoiceOutput(enable?: boolean) {
        const videoChat = (window as any).foveaiVideoChat;
        const current = videoChat ? videoChat.isVoiceOutputEnabled : (localStorage.getItem('foveai_voice_speech') !== 'false');
        const next = enable !== undefined ? enable : !current;
        if (videoChat) videoChat.isVoiceOutputEnabled = next;
        localStorage.setItem('foveai_voice_speech', String(next));

        const topBtn = this.container.querySelector('#btn-voice-speech-top') as HTMLButtonElement;
        const inputBtn = this.container.querySelector('#btn-voice-output') as HTMLButtonElement;

        if (topBtn) {
            topBtn.textContent = next ? '🔊 VOICE ON' : '🔇 VOICE OFF';
            topBtn.style.background = next ? 'rgba(0, 243, 255, 0.15)' : 'rgba(255, 0, 127, 0.15)';
            topBtn.style.borderColor = next ? 'var(--neon-blue)' : 'var(--neon-pink)';
            topBtn.style.color = next ? 'var(--neon-blue)' : 'var(--neon-pink)';
        }
        if (inputBtn) {
            inputBtn.textContent = next ? '🔊' : '🔇';
            inputBtn.style.borderColor = next ? 'var(--neon-blue)' : 'var(--neon-pink)';
            inputBtn.style.color = next ? 'var(--neon-blue)' : 'var(--neon-pink)';
            inputBtn.classList.toggle('active', next);
        }

        this.log(`Voice Speech Output: ${next ? 'ENABLED (🔊)' : 'DISABLED (🔇)'}`, next ? 'var(--neon-blue)' : 'var(--neon-pink)');
    }

    private onSendMessage: (text: string, attachments?: any[], imageUrl?: string) => void = () => {};

    public setOnSendMessage(callback: (text: string, attachments?: any[], imageUrl?: string) => void) {
        this.onSendMessage = callback;
    }

    public sendMessage(text: string) {
        this.onSendMessage(text);
    }

    private async renderTheologyTab(container: Element) {
        const entries = await localMemory.theology.toArray();

        let html = '<div class="theology-grid">';
        entries.forEach((s: any) => {
            const symbolId = s.symbolId || 0;
            const svg = this.getSymbolSVG(symbolId);
            html += `
                <div class="symbol-card" data-id="${s.id}">
                    <div class="symbol-svg">${svg}</div>
                    <div class="symbol-label">${s.symbolId ? `SYMBOL ${s.symbolId}` : 'CONCEPT'}</div>
                    <div class="symbol-desc">${s.concept}</div>
                </div>
            `;
        });
        html += '</div>';
        
        container.innerHTML = html;
        
        container.querySelectorAll('.symbol-card').forEach(card => {
            card.addEventListener('click', () => {
                const id = parseInt(card.getAttribute('data-id') || '0');
                const entry = entries.find((e: any) => e.id === id);
                if (entry) {
                    this.log(`Retrieving Concept: ${entry.concept}...`, "var(--neon-blue)");
                    window.alert(`${entry.concept}\n\n${entry.details}`);
                }
            });
        });
    }

    private getSymbolSVG(id: number): string {
        const color = "var(--neon-blue)";
        const glow = "filter: drop-shadow(0 0 5px var(--neon-blue))";
        
        switch(id) {
            case 8: return `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="10" stroke="${color}" fill="none" style="${glow}"/><line x1="50" y1="10" x2="50" y2="30" stroke="${color}"/><line x1="50" y1="70" x2="50" y2="90" stroke="${color}"/><line x1="10" y1="50" x2="30" y2="50" stroke="${color}"/><line x1="70" y1="50" x2="90" y2="50" stroke="${color}"/><line x1="22" y1="22" x2="35" y2="35" stroke="${color}"/><line x1="65" y1="65" x2="78" y2="78" stroke="${color}"/><line x1="22" y1="78" x2="35" y2="65" stroke="${color}"/><line x1="65" y1="35" x2="78" y2="22" stroke="${color}"/></svg>`;
            case 9: return `<svg viewBox="0 0 100 100"><path d="M50 85 C10 60 10 30 50 30 C90 30 90 60 50 85" stroke="${color}" fill="none" style="${glow}"/><circle cx="50" cy="45" r="15" stroke="${color}" fill="none" opacity="0.5"/></svg>`;
            case 10: return `<svg viewBox="0 0 100 100"><rect x="30" y="30" width="40" height="40" stroke="${color}" fill="none" style="${glow}" transform="rotate(45 50 50)"/><rect x="35" y="35" width="30" height="30" stroke="${color}" fill="none" opacity="0.5" transform="rotate(45 50 50)"/></svg>`;
            case 11: return `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" stroke="${color}" fill="none" style="${glow}"/><polygon points="50,20 80,70 20,70" stroke="${color}" fill="none"/><circle cx="50" cy="53" r="10" stroke="${color}" fill="none" opacity="0.6"/></svg>`;
            case 13: return `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="35" stroke="${color}" fill="none" stroke-dasharray="4 4" style="${glow}"/><path d="M20 50 Q50 10 80 50 Q50 90 20 50" stroke="${color}" fill="none" opacity="0.7"/><circle cx="50" cy="50" r="5" fill="${color}"/></svg>`;
            default: return `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="30" stroke="${color}" fill="none"/></svg>`;
        }
    }

    public setActiveTab(tab: string) {
        this.activeTab = tab;
        this.render();
    }

    private async updateContent() {
        const content = this.container.querySelector('#tab-content-area');
        const footer = this.container.querySelector('#dashboard-footer') as HTMLElement;
        if (!content) return;

        if (this.activeTab === 'cognition') {
            footer.style.display = 'block';
            if (!content.querySelector('#chat-history')) {
                content.innerHTML = '<div id="chat-history"></div>';
                this.loadInitialHistory();
            }
        } else if (this.activeTab === 'profile') {
            footer.style.display = 'none';
            ProfileTab.render(content as HTMLElement);
        } else if (this.activeTab === 'neural') {
            // Legacy route — redirect to profile
            footer.style.display = 'none';
            ProfileTab.render(content as HTMLElement);
        } else if (this.activeTab === 'chronicle') {
            footer.style.display = 'none';
            ChronicleTab.render(content as HTMLElement);
        } else if (this.activeTab === 'branding') {
            footer.style.display = 'none';
            await BrandingTab.render(content as HTMLElement);
        } else if (this.activeTab === 'vision') {
            footer.style.display = 'none';
            VisionTab.render(content as HTMLElement);
        } else if (this.activeTab === 'swarm') {
            footer.style.display = 'none';
            SwarmTab.render(content as HTMLElement);
        } else if (this.activeTab === 'nucleus') {
            footer.style.display = 'none';
            NucleusTab.render(content as HTMLElement);
        } else if (this.activeTab === 'dreamscape') {
            footer.style.display = 'none';
            DreamscapeTab.render(content as HTMLElement);
        } else if (this.activeTab === 'devtools') {
            footer.style.display = 'none';
            DevToolsTab.render(content as HTMLElement);
        } else if (this.activeTab === 'diagnosis') {
            footer.style.display = 'none';
            content.innerHTML = '<div class="breadcrumb">LOADING DIAGNOSTIC DATA...</div>';
            
            try {
                const response = await fetch('/diagnostic_data.json');
                const data = await response.json();
                
                DiagnosisTab.render(content as HTMLElement, data, async (results) => {
                    this.log('Transmitting assessment data to Hybrid Brain...', 'var(--neon-blue)');
                    
                    const consentCheckbox = document.querySelector('#consent-adaptive') as HTMLInputElement;
                    const hasConsent = consentCheckbox?.checked || false;

                    const summary = Object.entries(results).map(([k, v]: any) => `${k}: ${v.value} (${v.note || 'no detail'})`).join('\n');
                    const prompt = `[DIAGNOSTIC ASSESSMENT DATA - NUANCED PROFILING]\n${summary}\n\n[USER CONSENT FOR ADAPTIVE BEHAVIOR: ${hasConsent ? 'GRANTED' : 'DECLINED'}]\n\nFoveAI, please conduct a smart psychiatric assessment. Identify the "underlying signature" across these dimensions. ${hasConsent ? 'The user HAS CONSENTED to adaptive behavior. Please provide specific instructions on how you should adapt your persona and supportive style to best serve this profile.' : 'The user has DECLINED adaptive behavior; provide clinical analysis and support steps ONLY without changing your core persona.'} Cross-reference with your diagnostic matrix.`;
                    
                    this.setActiveTab('cognition');
                    this.onSendMessage(prompt);
                });
            } catch (err) {
                content.innerHTML = `<div class="breadcrumb" style="color:var(--neon-pink);">FAULT: ${err}</div>`;
            }
        } else if (this.activeTab === 'featuremap') {
            footer.style.display = 'none';
            FeatureMapTab.render(content as HTMLElement);
        } else if (this.activeTab === 'forgeindex') {
            footer.style.display = 'none';
            this.renderForgeIndex(content as HTMLElement);
        } else if (this.activeTab === 'modelhub') {
            footer.style.display = 'none';
            ModelHubTab.render(content as HTMLElement);
        } else if (this.activeTab === 'agency') {
            footer.style.display = 'none';
            AgencyTab.render(content as HTMLElement);
            // Start agent status polling for telemetry strip
            this.startAgentTelemetry();
        } else if (this.activeTab === 'monetizing') {
            footer.style.display = 'none';
            MonetizingTab.render(content as HTMLElement);
        } else if (this.activeTab === 'webvm') {
            footer.style.display = 'none';
            content.innerHTML = `
                <div class="breadcrumb">FOVEAI TERMINAL IDE // NATIVE_PYTHON_CONSOLE</div>
                <div style="flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden;">
                    <iframe src="http://${window.location.hostname}:8085" style="width:100%; height:100%; border:1px solid var(--border); border-radius:4px; background:#000;" sandbox="allow-scripts allow-same-origin allow-popups allow-forms"></iframe>
                </div>
            `;
        } else if (this.activeTab === 'videochat') {
            footer.style.display = 'none';
            content.innerHTML = `<div class="breadcrumb">VIDEO CHAT // SYSTEM_LINK</div>`;
        } else if (this.activeTab === 'social') {
            footer.style.display = 'none';
            content.innerHTML = `
                <div class="breadcrumb">SOCIAL // MULTIVERSE_BRIDGE</div>
                <div class="glass-card" style="padding:40px; text-align:center;">
                    <div style="font-size:3rem; margin-bottom:20px;">[NET]</div>
                    <div style="font-family:'Orbitron'; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">SOCIAL GATEWAY OFFLINE</div>
                    <div style="margin-top:15px; font-size:0.75rem; opacity:0.6; line-height:1.6;">Multiverse networking is disabled in OMEGA_085. Social features are restricted to local peer discovery and secure outbox protocols.</div>
                </div>
            `;
        } else if (this.activeTab === 'tokenslayer') {
            footer.style.display = 'none';
            TokenSlayerTab.render(content as HTMLElement);
        } else if (this.activeTab === 'forgenursery') {
            footer.style.display = 'none';
            ForgeNurseryTab.render(content as HTMLElement);
        } else if (this.activeTab === 'envmapping') {
            footer.style.display = 'none';
            EnvironmentMappingTab.render(content as HTMLElement);
        } else if (this.activeTab === 'avatarcameras') {
            footer.style.display = 'none';
            AvatarCamerasTab.render(content as HTMLElement);
        } else if (this.activeTab === 'envmanagement') {
            footer.style.display = 'none';
            EnvironmentManagementTab.render(content as HTMLElement);
        } else if (this.activeTab === 'controllers') {
            footer.style.display = 'none';
            ControllersMappingTab.render(content as HTMLElement);
        } else if (this.activeTab === 'settings') {
            footer.style.display = 'none';
            const settingsTab = new SettingsTab();
            settingsTab.container.style.display = 'block';
            content.innerHTML = '';
            content.appendChild(settingsTab.container);
        } else if (this.activeTab === 'thoughts') {
            footer.style.display = 'none';
            this.renderThoughtsTab(content as HTMLElement);
        }
    }

    private startThoughtEventListener() {
        window.addEventListener('foveai_thought_stream', ((e: CustomEvent) => {
            const thought = e.detail?.thought;
            if (thought) {
                this.addThought(thought);
            }
        }) as EventListener);
    }

    public addThought(text: string) {
        if (!text) return;
        const entry = {
            text,
            timestamp: Date.now(),
            sessionId: this.currentSessionId
        };
        this.thoughtHistory.push(entry);
        // Prune: keep only last 3 sessions
        this.pruneThoughtHistory();
        // If thoughts tab is active, re-render
        if (this.activeTab === 'thoughts') {
            const content = this.container.querySelector('#tab-content-area');
            if (content) this.renderThoughtsTab(content as HTMLElement);
        }
    }

    private pruneThoughtHistory() {
        const sessionIds = [...new Set(this.thoughtHistory.map(t => t.sessionId))].sort((a, b) => b - a);
        const keepSessions = sessionIds.slice(0, 3);
        this.thoughtHistory = this.thoughtHistory.filter(t => keepSessions.includes(t.sessionId));
    }

    private renderThoughtsTab(container: HTMLElement) {
        const thoughts = [...this.thoughtHistory].reverse(); // newest at bottom (reversed in display)
        
        let html = `
            <div class="breadcrumb">THOUGHTS // JEN'S COGNITIVE STREAM</div>
            <div style="display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border); margin-bottom: 10px;">
                <button id="btn-thoughts-clear-session" style="background: rgba(255,0,127,0.1); border: 1px solid var(--neon-pink); color: #fff; padding: 6px 12px; cursor: pointer; border-radius: 4px; font-family: 'Orbitron'; font-size: 0.6rem;">
                    🗑 CLEAR SESSION
                </button>
                <button id="btn-thoughts-new-session" style="background: rgba(0,243,255,0.1); border: 1px solid var(--neon-blue); color: #fff; padding: 6px 12px; cursor: pointer; border-radius: 4px; font-family: 'Orbitron'; font-size: 0.6rem;">
                    ➕ NEW SESSION
                </button>
            </div>
            <div id="thoughts-list" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px;">
        `;

        if (thoughts.length === 0) {
            html += `
                <div style="text-align: center; padding: 40px; opacity: 0.5;">
                    <div style="font-size: 2rem; margin-bottom: 10px;">🧠</div>
                    <div style="font-family: 'Orbitron'; font-size: 0.8rem; color: var(--neon-blue);">NO THOUGHTS RECORDED</div>
                    <div style="font-size: 0.7rem; margin-top: 8px;">Thoughts will appear here as Jen processes information</div>
                </div>
            `;
        } else {
            thoughts.forEach((t, i) => {
                const timeStr = new Date(t.timestamp).toLocaleTimeString();
                const sessionLabel = `S${t.sessionId}`;
                html += `
                    <div class="thought-entry" data-index="${thoughts.length - 1 - i}" style="
                        background: rgba(0, 243, 255, 0.03);
                        border: 1px solid rgba(0, 243, 255, 0.1);
                        border-left: 3px solid var(--neon-blue);
                        border-radius: 4px;
                        padding: 10px 12px;
                        font-family: 'Share Tech Mono', monospace;
                        font-size: 0.75rem;
                        color: rgba(255, 255, 255, 0.85);
                        line-height: 1.4;
                        position: relative;
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-family: 'Orbitron'; font-size: 0.5rem; color: var(--neon-blue); letter-spacing: 1px;">◆ ${sessionLabel} — ${timeStr}</span>
                            <div style="display: flex; gap: 6px;">
                                <button class="btn-thought-save" data-index="${thoughts.length - 1 - i}" title="Save to persistent memory" style="
                                    background: rgba(57,255,20,0.1); border: 1px solid rgba(57,255,20,0.3); color: #39ff14;
                                    font-size: 0.5rem; padding: 2px 6px; cursor: pointer; border-radius: 2px;
                                    font-family: 'Orbitron'; letter-spacing: 0.5px;
                                ">💾 SAVE</button>
                                <button class="btn-thought-delete" data-index="${thoughts.length - 1 - i}" title="Remove this thought" style="
                                    background: transparent; border: 1px solid rgba(255,0,127,0.3); color: var(--neon-pink);
                                    font-size: 0.6rem; padding: 2px 6px; cursor: pointer; border-radius: 2px;
                                ">✕</button>
                            </div>
                        </div>
                        <div style="white-space: pre-wrap; word-break: break-word;">${this.escapeHtml(t.text)}</div>
                    </div>
                `;
            });
        }

        html += '</div>';
        container.innerHTML = html;

        // Wire up delete buttons
        container.querySelectorAll('.btn-thought-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt((e.currentTarget as HTMLElement).getAttribute('data-index') || '0');
                this.thoughtHistory.splice(index, 1);
                this.renderThoughtsTab(container);
            });
        });

        // Wire up save buttons
        container.querySelectorAll('.btn-thought-save').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const index = parseInt((e.currentTarget as HTMLElement).getAttribute('data-index') || '0');
                const thought = this.thoughtHistory[index];
                if (thought) {
                    try {
                        await localMemory.addMessage({
                            role: 'system',
                            content: `[SAVED THOUGHT — S${thought.sessionId}] ${thought.text}`,
                            timestamp: Date.now()
                        });
                        this.log('💾 Thought saved to persistent memory', '#39ff14');
                        (e.currentTarget as HTMLElement).textContent = '✓ SAVED';
                        (e.currentTarget as HTMLElement).style.opacity = '0.5';
                    } catch (err) {
                        this.log(`Save failed: ${err}`, '#ff007f');
                    }
                }
            });
        });

        // Clear session button
        const btnClearSession = container.querySelector('#btn-thoughts-clear-session');
        btnClearSession?.addEventListener('click', () => {
            this.thoughtHistory = this.thoughtHistory.filter(t => t.sessionId !== this.currentSessionId);
            this.renderThoughtsTab(container);
            this.log('🗑 Current session thoughts cleared', 'var(--neon-pink)');
        });

        // New session button
        const btnNewSession = container.querySelector('#btn-thoughts-new-session');
        btnNewSession?.addEventListener('click', () => {
            this.currentSessionId++;
            this.log(`➕ New thought session started: S${this.currentSessionId}`, 'var(--neon-blue)');
            this.renderThoughtsTab(container);
        });
    }

    private escapeHtml(text: string): string {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    private autoStartVAD() {
        // Auto-start VAD if mic permissions are already granted and not already listening
        const cachedMic = (window as any).foveaiCachedMicStream as MediaStream | null;
        if (cachedMic && cachedMic.active && !this.isListening) {
            this.log('[VAD] Auto-starting voice detection...', 'var(--neon-blue)');
            this.startListening();
            return;
        }
        // In desktop mode, no cached mic exists yet — proactively request it
        if (!cachedMic && !this.isListening) {
            this.log('[VAD] No cached mic — requesting microphone access...', 'var(--neon-blue)');
            navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
                (window as any).foveaiCachedMicStream = stream;
                this.log('[VAD] Microphone acquired — auto-starting voice detection...', 'var(--neon-green)');
                this.startListening();
            }).catch((err) => {
                this.log(`[VAD] Microphone request denied: ${err.message}`, '#ffaa00');
            });
        }
    }

    private startThoughtPolling() {
        let lastThought = '';
        setInterval(async () => {
            try {
                const response = await fetch('/api/thought_stream', { signal: AbortSignal.timeout(1000) });
                if (response.ok) {
                    const data = await response.json();
                    if (data.thought && data.thought !== lastThought) {
                        if (this.showThoughtStream) {
                            thoughtToast.show(data.thought);
                        }
                        lastThought = data.thought;
                    }
                }
            } catch (err) {}
        }, 5000);
    }

    public addMessage(role: string, text: string, scroll: boolean = true, imageUrl?: string) {
        if (role === 'system') return;
        if (this.activeTab !== 'cognition') return;
        
        const chatHistory = this.container.querySelector('#chat-history');
        if (chatHistory) {
            const msgDiv = document.createElement('div');
            msgDiv.className = `msg msg-${role === 'user' ? 'user' : 'ai'}`;
            
            const tag = document.createElement('span');
            tag.className = 'sender-tag';
            tag.innerText = role === 'user' ? 'YOU' : 'JEN';
            
            const textDiv = document.createElement('div');
            textDiv.className = 'msg-text';
            textDiv.innerText = BracketParser.strip(text);
            
            if (imageUrl) {
                const img = document.createElement('img');
                img.src = imageUrl;
                img.className = 'chat-attached-image';
                img.style.cssText = 'width: 95%; max-height: 600px; object-fit: contain; border-radius: 8px; margin: 15px auto 5px auto; display: block; border: 1px solid var(--neon-blue); box-shadow: 0 0 10px rgba(0, 170, 255, 0.3); cursor: zoom-in;';
                img.onclick = () => {
                    const overlay = document.createElement('div');
                    overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.9); z-index: 99999; display: flex; justify-content: center; align-items: center; cursor: zoom-out;';
                    const fullImg = document.createElement('img');
                    fullImg.src = imageUrl;
                    fullImg.style.cssText = 'max-width: 95%; max-height: 95%; object-fit: contain; border: 2px solid var(--neon-blue); box-shadow: 0 0 30px var(--neon-blue);';
                    overlay.appendChild(fullImg);
                    overlay.onclick = () => document.body.removeChild(overlay);
                    document.body.appendChild(overlay);
                };
                textDiv.appendChild(img);
            }
            
            msgDiv.appendChild(tag);
            msgDiv.appendChild(textDiv);
            chatHistory.appendChild(msgDiv);
            if (scroll) {
                requestAnimationFrame(() => {
                    msgDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
                });
            }
        }
    }

    public getElement() {
        return this.container;
    }

    private vadIndicatorEl: HTMLElement | null = null;

    private createVadIndicator() {
        if (document.getElementById('foveai-vad-indicator')) return;
        const el = document.createElement('div');
        el.id = 'foveai-vad-indicator';
        el.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.2);
            z-index: 9999;
            pointer-events: none;
            transition: all 0.4s ease;
            box-shadow: 0 0 0px transparent;
        `;
        el.title = 'VAD: Standby';
        document.body.appendChild(el);
        this.vadIndicatorEl = el;
    }

    private updateVadIndicator() {
        if (!this.vadIndicatorEl) return;
        if (this.isListening) {
            this.vadIndicatorEl.style.background = 'rgba(57, 255, 20, 0.6)';
            this.vadIndicatorEl.style.borderColor = '#39ff14';
            this.vadIndicatorEl.style.boxShadow = '0 0 12px rgba(57, 255, 20, 0.5)';
            this.vadIndicatorEl.style.width = '16px';
            this.vadIndicatorEl.style.height = '16px';
            this.vadIndicatorEl.title = 'VAD: Listening';
        } else {
            this.vadIndicatorEl.style.background = 'rgba(255,255,255,0.15)';
            this.vadIndicatorEl.style.borderColor = 'rgba(255,255,255,0.2)';
            this.vadIndicatorEl.style.boxShadow = '0 0 0px transparent';
            this.vadIndicatorEl.style.width = '14px';
            this.vadIndicatorEl.style.height = '14px';
            this.vadIndicatorEl.title = 'VAD: Standby';
        }
    }

    private isUserEditing: boolean = false;
    private autoSendTimeout: any = null;

    private startVAD(stream: MediaStream) {
        try {
            this.stopVAD();

            const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
            if (!AudioContextClass) return;

            // Reuse a single, persistent AudioContext to prevent Chromium/Oculus autoplay blocks
            let ctx = (window as any).foveaiAudioContext;
            if (!ctx || ctx.state === 'closed') {
                ctx = new AudioContextClass();
                (window as any).foveaiAudioContext = ctx;
            }
            this.audioContext = ctx;

            // Ensure the shared context is running
            if (ctx.state === 'suspended') {
                ctx.resume().then(() => {
                    this.log('[VAD] Shared AudioContext resumed', 'var(--neon-green)');
                }).catch((err: any) => {
                    console.warn('[VAD] Shared AudioContext resume failed:', err);
                });
            }

            const source = ctx.createMediaStreamSource(stream);
            this.audioSourceNode = source;
            const analyserNode = ctx.createAnalyser();
            analyserNode.fftSize = 512;
            source.connect(analyserNode);
            this.analyser = analyserNode;

            const bufferLength = analyserNode.frequencyBinCount;
            const dataArray = new Float32Array(bufferLength);

            let hasSpoken = false;
            let silenceStart = 0;
            const SPEECH_THRESHOLD = 0.025;  // raised: 0.015 was triggering on ambient noise
            const SILENCE_THRESHOLD = 0.004;  // slightly tighter silence floor
            const SILENCE_DURATION_MS = 1200; // 1.2s silence + no edits → auto-send

            // Track editing state on chat input
            const chatInput = this.container.querySelector('#chat-input') as HTMLInputElement;
            if (chatInput) {
                chatInput.addEventListener('input', () => { this.isUserEditing = true; });
                chatInput.addEventListener('blur', () => { this.isUserEditing = false; });
                chatInput.addEventListener('focus', () => { this.isUserEditing = true; });
            }

            this.vadInterval = setInterval(() => {
                if (!this.analyser || !this.isListening) return;

                this.analyser!.getFloatTimeDomainData(dataArray);

                let sumSquares = 0;
                for (let i = 0; i < bufferLength; i++) {
                    sumSquares += dataArray[i] * dataArray[i];
                }
                const rms = Math.sqrt(sumSquares / bufferLength);

                if (rms > SPEECH_THRESHOLD) {
                    if (!hasSpoken) {
                        hasSpoken = true;
                        this.log('[VAD] Speech detected...', 'var(--neon-pink)');
                    }
                    silenceStart = 0;
                    if (this.autoSendTimeout) { clearTimeout(this.autoSendTimeout); this.autoSendTimeout = null; }
                } else if (rms < SILENCE_THRESHOLD && hasSpoken) {
                    if (silenceStart === 0) {
                        silenceStart = Date.now();
                    } else if (Date.now() - silenceStart > SILENCE_DURATION_MS) {
                        // Check if user is actively editing — if so, don't auto-send yet
                        if (this.isUserEditing) {
                            // Reset silence timer, keep listening while user edits
                            silenceStart = Date.now();
                            return;
                        }
                        this.log('[VAD] Silence + no edits. Auto-sending...', '#39ff14');
                        const ci = this.container.querySelector('#chat-input') as HTMLInputElement;
                        if (ci && ci.value.trim()) {
                            this.onSendMessage(ci.value.trim());
                            ci.value = '';
                        }
                        this.stopListening();
                    }
                } else if (hasSpoken) {
                    // Intermediate volume (between SILENCE_THRESHOLD and SPEECH_THRESHOLD)
                    // Keep the silence timer reset so quiet talking or pause-gaps don't trigger auto-send
                    silenceStart = 0;
                }
            }, 100);
        } catch (e) {
            console.warn('[VAD] Failed to initialize Web Audio VAD:', e);
        }
    }

    private stopVAD() {
        if (this.vadInterval) {
            clearInterval(this.vadInterval);
            this.vadInterval = null;
        }
        if (this.audioSourceNode) {
            try {
                this.audioSourceNode.disconnect();
            } catch (e) {}
            this.audioSourceNode = null;
        }
        if (this.analyser) {
            try {
                this.analyser.disconnect();
            } catch (e) {}
            this.analyser = null;
        }
        this.audioContext = null; // Simply dereference, keeping the shared context alive for reuse!
    }

    private async renderForgeIndex(container: HTMLElement): Promise<void> {
        container.innerHTML = `
            <div class="breadcrumb">📋 FORGE // FEATURE INVENTORY</div>
            <div class="glass-card" style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
                <div style="display: flex; gap: 10px; padding: 15px; border-bottom: 1px solid var(--border);">
                    <button id="btn-index-latest" style="background: rgba(0,243,255,0.1); border: 1px solid var(--neon-blue); color: #fff; padding: 8px 16px; cursor: pointer; border-radius: 4px; font-family: 'Orbitron'; font-size: 0.7rem;">
                        🔄 INDEX LATEST
                    </button>
                    <button id="btn-view-inventory" style="background: rgba(57,255,20,0.1); border: 1px solid #39ff14; color: #fff; padding: 8px 16px; cursor: pointer; border-radius: 4px; font-family: 'Orbitron'; font-size: 0.7rem;">
                        📖 VIEW INVENTORY
                    </button>
                </div>
                <div id="forge-status" style="padding: 15px; font-size: 0.8rem; color: var(--neon-blue);">
                    Ready to index Forge discoveries...
                </div>
                <div id="forge-content" style="flex: 1; overflow: auto; padding: 0 15px;">
                    <div style="text-align: center; padding: 40px; opacity: 0.6;">
                        <div style="font-size: 3rem; margin-bottom: 20px;">🔭</div>
                        <div style="font-family: 'Orbitron'; font-size: 0.9rem; color: var(--neon-blue);">
                            DISCOVERY SWARM READY
                        </div>
                        <div style="margin-top: 15px; font-size: 0.75rem; line-height: 1.6;">
                            Click "INDEX LATEST" to process the most recent discovery report<br>
                            and add meaningful features to FEATURE_INVENTORY.md
                        </div>
                    </div>
                </div>
            </div>
        `;

        const btnIndex = container.querySelector('#btn-index-latest') as HTMLButtonElement;
        const btnView = container.querySelector('#btn-view-inventory') as HTMLButtonElement;
        const status = container.querySelector('#forge-status') as HTMLElement;
        const content = container.querySelector('#forge-content') as HTMLElement;

        btnIndex?.addEventListener('click', async () => {
            status.innerHTML = '<span style="color: var(--neon-blue);">🔄 Indexing discoveries...</span>';
            try {
                const response = await fetch('/api/forge/index', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    status.innerHTML = `<span style="color: #39ff14;">✓ Indexed ${data.added} meaningful saves</span>`;
                    content.innerHTML = `
                        <div style="padding: 20px;">
                            <div style="font-family: 'Orbitron'; color: var(--neon-blue); margin-bottom: 15px;">
                                LAST DISCOVERY: ${data.report_name}
                            </div>
                            <div style="font-size: 0.75rem; opacity: 0.8;">
                                Total discovered: ${data.total_discovered} | 
                                Worthwhile: ${data.worthwhile} | 
                                Added: ${data.added}
                            </div>
                        </div>
                    `;
                } else {
                    status.innerHTML = `<span style="color: var(--neon-pink);">✗ ${data.error}</span>`;
                }
            } catch (err) {
                status.innerHTML = `<span style="color: var(--neon-pink);">✗ ${err}</span>`;
            }
        });

        btnView?.addEventListener('click', () => {
            window.open('/FEATURE_INVENTORY.md', '_blank');
        });
    }

    /** Poll agent status and update the telemetry strip JEN indicator */
    private startAgentTelemetry(): void {
        const stateEl = this.container.querySelector('#tel-agent-state') as HTMLElement;
        if (!stateEl) return;

        const update = async () => {
            try {
                const status = await agentBridge.getStatus();
                if (status.running) {
                    stateEl.textContent = 'ON';
                    stateEl.style.color = 'var(--neon-green)';
                    stateEl.style.textShadow = '0 0 6px var(--neon-green)';
                } else {
                    stateEl.textContent = '—';
                    stateEl.style.color = 'var(--neon-pink)';
                    stateEl.style.textShadow = 'none';
                }
            } catch {
                stateEl.textContent = '?';
                stateEl.style.color = '#ffaa00';
                stateEl.style.textShadow = 'none';
            }
        };

        update();
        // Poll every 5 seconds — lightweight, just for the strip indicator
        const interval = setInterval(update, 5000);

        // Store for cleanup (replaced on next setActiveTab call)
        (this as any)._agentTelemetryInterval = interval;
    }

    private currentBrowserPath: string = '';
    private selectedBrowserFile: string | null = null;

    public openAttachmentOptions() {
        let modal = this.container.querySelector('#attachment-options-modal') as HTMLElement;
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'attachment-options-modal';
            modal.style.cssText = `
                position: absolute;
                bottom: 60px;
                left: 10px;
                background: rgba(6, 10, 18, 0.98);
                backdrop-filter: blur(20px);
                border: 2px solid var(--neon-blue);
                border-radius: 8px;
                padding: 15px;
                display: none;
                flex-direction: column;
                gap: 10px;
                z-index: 10005;
                box-shadow: 0 0 25px rgba(0, 243, 255, 0.35);
                width: 260px;
                box-sizing: border-box;
                font-family: 'Orbitron', sans-serif;
            `;
            
            modal.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(0,243,255,0.2); padding-bottom:8px; margin-bottom:5px;">
                    <span style="font-size:0.75rem; color:var(--neon-blue); font-weight:bold; letter-spacing:1px;">ATTACH FILE</span>
                    <button class="fb-close-btn" id="att-opt-close" style="padding:2px 8px; font-size:0.7rem;">X</button>
                </div>
                <button class="fb-action-btn" id="att-opt-quest" style="text-align: left; background: rgba(0, 243, 255, 0.1); color: #fff; border: 1px solid var(--neon-blue); font-size:0.75rem; padding:8px 12px; display:flex; align-items:center; gap:8px;">📱 Quest Headset Storage</button>
                <button class="fb-action-btn" id="att-opt-host" style="text-align: left; background: rgba(147, 51, 234, 0.1); color: #fff; border: 1px solid #9333ea; font-size:0.75rem; padding:8px 12px; display:flex; align-items:center; gap:8px;">📁 Host PC Filesystem</button>
                <button class="fb-action-btn" id="att-opt-snap" style="text-align: left; background: rgba(255, 0, 127, 0.1); color: #fff; border: 1px solid var(--neon-pink); font-size:0.75rem; padding:8px 12px; display:flex; align-items:center; gap:8px;">📸 Viewpoint Snapshot</button>
            `;
            
            this.container.appendChild(modal);
            
            modal.querySelector('#att-opt-close')?.addEventListener('click', () => {
                modal.style.display = 'none';
                this.updateMeshUI();
            });
            
            modal.querySelector('#att-opt-quest')?.addEventListener('click', () => {
                modal.style.display = 'none';
                const fileInput = this.container.querySelector('#file-attach-input') as HTMLInputElement;
                fileInput?.click();
                this.updateMeshUI();
            });
            
            modal.querySelector('#att-opt-host')?.addEventListener('click', () => {
                modal.style.display = 'none';
                this.openFileBrowser('.');
            });
            
            modal.querySelector('#att-opt-snap')?.addEventListener('click', () => {
                modal.style.display = 'none';
                this.log('[XR] Capturing viewpoint snapshot...', 'var(--neon-blue)');
                window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'my snapshot' } }));
                this.updateMeshUI();
            });
        }
        
        modal.style.display = 'flex';
        this.updateMeshUI();
    }

    public openFileBrowser(startPath: string = '.') {
        let modal = this.container.querySelector('#file-browser-modal') as HTMLElement;
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'file-browser-modal';
            modal.className = 'file-browser-modal';
            this.container.appendChild(modal);
        }
        
        modal.classList.add('show');
        this.fetchFileList(startPath);
        this.updateMeshUI();
    }

    private updateMeshUI() {
        if ((window as any).holographicPanelMesh) {
            try {
                (window as any).holographicPanelMesh.material.map.update();
            } catch (e) {}
        }
    }

    private fetchFileList(path: string) {
        const modal = this.container.querySelector('#file-browser-modal') as HTMLElement;
        if (!modal) return;

        modal.innerHTML = `
            <div class="fb-header">
                <span class="fb-title">HOST FILE BROWSER (VR FALLBACK)</span>
                <button class="fb-close-btn" id="fb-close">CLOSE</button>
            </div>
            <div style="display:flex; justify-content:center; align-items:center; flex-grow:1; color:var(--neon-blue); font-family:monospace; font-size:0.9rem;">
                🔄 Scanning host filesystem...
            </div>
        `;
        
        // Bind close button during loading
        modal.querySelector('#fb-close')?.addEventListener('click', () => {
            modal.classList.remove('show');
            this.updateMeshUI();
        });

        this.updateMeshUI();

        const url = `/api/code/ls?dir=${encodeURIComponent(path)}`;
        fetch(url)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (data.error) {
                    this.renderBrowserError(data.error, path);
                } else {
                    this.currentBrowserPath = path;
                    this.selectedBrowserFile = null;
                    this.renderFileBrowser(data.files || [], path);
                }
            })
            .catch(err => {
                this.renderBrowserError(err.message, path);
            });
    }

    private renderBrowserError(errorMsg: string, path: string) {
        const modal = this.container.querySelector('#file-browser-modal') as HTMLElement;
        if (!modal) return;

        modal.innerHTML = `
            <div class="fb-header">
                <span class="fb-title">HOST FILE BROWSER (VR FALLBACK)</span>
                <button class="fb-close-btn" id="fb-close">CLOSE</button>
            </div>
            <div style="color:var(--neon-pink); margin-bottom:15px; font-family:monospace; font-size:0.9rem;">Error: ${errorMsg}</div>
            <div style="display:flex; gap:10px;">
                <button class="fb-action-btn" id="fb-retry">RETRY</button>
                <button class="fb-action-btn" id="fb-root">GO TO ROOT</button>
            </div>
        `;

        modal.querySelector('#fb-close')?.addEventListener('click', () => {
            modal.classList.remove('show');
            this.updateMeshUI();
        });
        modal.querySelector('#fb-retry')?.addEventListener('click', () => this.fetchFileList(path));
        modal.querySelector('#fb-root')?.addEventListener('click', () => this.fetchFileList('.'));
        this.updateMeshUI();
    }

    private renderFileBrowser(files: Array<any>, currentPath: string) {
        const modal = this.container.querySelector('#file-browser-modal') as HTMLElement;
        if (!modal) return;

        // Compute parent path
        let parentPath = '';
        if (currentPath && currentPath !== '.' && currentPath !== '/') {
            const parts = currentPath.split('/');
            parts.pop();
            parentPath = parts.join('/') || '.';
        }

        let itemsHtml = '';
        if (currentPath && currentPath !== '.' && currentPath !== '/') {
            itemsHtml += `
                <div class="fb-item" data-path="${parentPath}" data-dir="true">
                    <span class="fb-item-icon">📁</span>
                    <span class="fb-item-name" style="color: var(--neon-blue);">.. (Up one level)</span>
                </div>
            `;
        }

        files.forEach(f => {
            const icon = f.isDir ? '📁' : this.getFileIcon(f.path);
            const sizeStr = f.isDir ? '' : `(${(f.size / 1024).toFixed(1)} KB)`;
            const name = f.path.split('/').pop() || f.path;
            itemsHtml += `
                <div class="fb-item" data-path="${f.path}" data-dir="${f.isDir ? 'true' : 'false'}">
                    <span class="fb-item-icon">${icon}</span>
                    <span class="fb-item-name">${name}</span>
                    <span class="fb-item-size">${sizeStr}</span>
                </div>
            `;
        });

        modal.innerHTML = `
            <div class="fb-header">
                <span class="fb-title">HOST FILE BROWSER (VR FALLBACK)</span>
                <button class="fb-close-btn" id="fb-close">CLOSE</button>
            </div>
            <div class="fb-path-bar">Path: FoveAI_ROOT/${currentPath}</div>
            <div class="fb-list">
                ${itemsHtml || '<div style="text-align:center; padding:20px; opacity:0.5; font-family:monospace; font-size:0.85rem;">(Folder is empty)</div>'}
            </div>
            <div class="fb-footer">
                <button class="fb-close-btn" id="fb-snap" style="margin-right:auto; border-color:var(--neon-blue); color:var(--neon-blue);">📸 CAMERA SNAPSHOT</button>
                <button class="fb-action-btn" id="fb-select" disabled>SELECT FILE</button>
            </div>
        `;

        // Bind events
        modal.querySelector('#fb-close')?.addEventListener('click', () => {
            modal.classList.remove('show');
            this.updateMeshUI();
        });

        modal.querySelector('#fb-snap')?.addEventListener('click', () => {
            modal.classList.remove('show');
            this.log('[XR] Paperclip clicked in VR — capturing viewpoint snapshot...', 'var(--neon-blue)');
            window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'my snapshot' } }));
            this.updateMeshUI();
        });

        const selectBtn = modal.querySelector('#fb-select') as HTMLButtonElement;

        modal.querySelectorAll('.fb-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const target = e.currentTarget as HTMLElement;
                const path = target.getAttribute('data-path') || '';
                const isDir = target.getAttribute('data-dir') === 'true';

                if (isDir) {
                    this.fetchFileList(path);
                } else {
                    modal.querySelectorAll('.fb-item').forEach(i => i.classList.remove('selected'));
                    target.classList.add('selected');
                    this.selectedBrowserFile = path;
                    selectBtn.removeAttribute('disabled');
                    this.updateMeshUI();
                }
            });
        });

        selectBtn?.addEventListener('click', () => {
            if (this.selectedBrowserFile) {
                this.loadHostFile(this.selectedBrowserFile);
                modal.classList.remove('show');
                this.updateMeshUI();
            }
        });

        this.updateMeshUI();
    }

    private getFileIcon(filename: string): string {
        const ext = filename.split('.').pop()?.toLowerCase();
        if (!ext) return '📄';
        if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext)) return '🖼️';
        if (['json', 'js', 'ts', 'py', 'html', 'css', 'md', 'txt', 'csv', 'yaml', 'yml'].includes(ext)) return '📄';
        return '📦';
    }

    private loadHostFile(filePath: string) {
        const ext = filePath.split('.').pop()?.toLowerCase() || '';
        const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext);

        const previewContainer = this.container.querySelector('#attachment-preview-container') as HTMLElement;
        const previewImg = this.container.querySelector('#attachment-preview-img') as HTMLImageElement;
        const previewName = this.container.querySelector('#attachment-preview-name') as HTMLElement;

        if (isImage) {
            // Read image base64
            fetch(`/api/code/read_image?path=${encodeURIComponent(filePath)}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error) throw new Error(data.error);
                    this.attachedImageDataUrl = data.dataUrl;
                    this.attachedImageBase64 = data.base64;
                    this.attachedImageType = data.mime_type;
                    this.attachedImageName = data.name;
                    this.attachedFileContent = null;
                    this.attachedFileName = null;

                    if (previewImg) {
                        previewImg.src = data.dataUrl;
                        previewImg.style.cursor = 'pointer';
                        previewImg.onclick = () => {
                            const overlay = document.createElement('div');
                            overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.9); z-index: 99999; display: flex; justify-content: center; align-items: center; cursor: zoom-out;';
                            const fullImg = document.createElement('img');
                            fullImg.src = data.dataUrl;
                            fullImg.style.cssText = 'max-width: 95%; max-height: 95%; object-fit: contain; border: 2px solid var(--neon-blue); box-shadow: 0 0 30px var(--neon-blue);';
                            overlay.appendChild(fullImg);
                            overlay.onclick = () => document.body.removeChild(overlay);
                            document.body.appendChild(overlay);
                        };
                    }
                    if (previewName) {
                        previewName.textContent = `${data.name} (Host File)`;
                    }
                    if (previewContainer) previewContainer.style.display = 'flex';
                    this.updateMeshUI();
                })
                .catch(err => {
                    this.log(`[XR] Failed to load host image: ${err.message}`, 'var(--neon-pink)');
                });
        } else {
            // Read document as text
            fetch(`/api/code/read?path=${encodeURIComponent(filePath)}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error) throw new Error(data.error);
                    const filename = filePath.split('/').pop() || filePath;
                    this.attachedFileContent = data.content;
                    this.attachedFileName = filename;
                    this.attachedImageBase64 = null;
                    this.attachedImageType = null;
                    this.attachedImageName = null;
                    this.attachedImageDataUrl = null;

                    if (previewImg) {
                        previewImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="%2300f3ff" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
                        previewImg.style.cursor = 'default';
                        previewImg.onclick = null;
                    }
                    if (previewName) {
                        previewName.textContent = `${filename} (Host File)`;
                    }
                    if (previewContainer) previewContainer.style.display = 'flex';
                    this.updateMeshUI();
                })
                .catch(err => {
                    this.log(`[XR] Failed to load host document: ${err.message}`, 'var(--neon-pink)');
                });
        }
    }
}
