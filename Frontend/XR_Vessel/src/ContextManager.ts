/**
 * ContextManager - Authoritative State Orchestrator for FoveAI OMEGA_371+
 * Manages runtime modes (XR, Mobile, Web, HUD, Menu, Voice) based on URL parameters.
 */

export type LumaxMode = 'web' | 'mobile' | 'xr' | 'ar' | 'hud' | 'menu' | 'voice' | 'quest' | 'qu';
export type LumaxUnit = 'de' | 'mo' | 'vr' | 'xr' | 'qu' | 'q3';

export class ContextManager {
    private mode: LumaxMode = 'web';
    private unit: LumaxUnit = 'de';
    private params: URLSearchParams;

    constructor() {
        this.params = new URLSearchParams(window.location.search);
        this.initMode();
    }

    public checkVersionBuster() {
        const revision = (window as any).LINK_REVISION || "OMEGA_511";
        const activeVersion = revision.replace('OMEGA_', '');
        const vParam = this.params.get('v');
        if (vParam !== activeVersion) {
            console.log(`[Cache Buster] Outdated version detected in URL (Got: ${vParam}, Expected: ${activeVersion}). Disabling auto-reload to prevent loops.`);
            
            // Programmatic Cache Eviction: clear Cache Storage API caches
            if (window.caches) {
                window.caches.keys().then((keys) => {
                    keys.forEach(key => {
                        window.caches.delete(key);
                        console.log(`[Cache Buster] Evicted cache storage key: ${key}`);
                    });
                }).catch(() => {});
            }
            
            // Programmatic Service Worker unregistration
            if (navigator.serviceWorker) {
                navigator.serviceWorker.getRegistrations().then((registrations) => {
                    registrations.forEach(reg => {
                        reg.unregister();
                        console.log(`[Cache Buster] Unregistered service worker: ${reg}`);
                    });
                }).catch(() => {});
            }
            
            // Clear session storage to discard stale dyn-cached states
            try {
                window.sessionStorage.clear();
            } catch {}
            
            // this.params.set('v', activeVersion);
            // window.location.search = this.params.toString();
        }
    }

    private initMode() {
        const mParam = (this.params.get('mode') || this.params.get('m'))?.toLowerCase();
        const uParam = (this.params.get('unit') || this.params.get('u'))?.toLowerCase();
        const aParam = (this.params.get('audio') || this.params.get('a'))?.toLowerCase();
        const ua = navigator.userAgent.toLowerCase();

        // 1. Resolve physical device/unit (u or unit parameter)
        if (uParam) {
            if (uParam === 'mo' || uParam === 'mob' || uParam === 'mobile' || uParam === 'phone') {
                this.unit = 'mo';
            } else if (uParam === 'de' || uParam === 'desk' || uParam === 'desktop' || uParam === 'web' || uParam === 'pc') {
                this.unit = 'de';
            } else if (uParam === 'vr' || uParam === 'virtualreality' || uParam === 'virtual_reality') {
                this.unit = 'vr';
            } else if (uParam === 'qu' || uParam === 'quest' || uParam === 'q2') {
                this.unit = 'qu';
            } else if (uParam === 'q3' || uParam === 'quest3' || uParam === 'pro') {
                this.unit = 'q3';
            } else if (uParam === 'xr' || uParam === 'extendedreality' || uParam === 'passthrough') {
                this.unit = 'xr';
            }
        } else {
            // Auto-detect unit from User-Agent
            const isMobileUA = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(ua);
            const isQuest = ua.includes('oculusbrowser');

            if (isQuest) {
                this.unit = 'q3';
            } else if (isMobileUA || window.innerWidth < 500) {
                this.unit = 'mo';
            } else {
                this.unit = 'de';
            }
        }

        // 2. Resolve layout/vessel mode (m or mode parameter)
        if (mParam) {
            if (mParam === 'me' || mParam === 'menu' || mParam === 'menuonly' || mParam === 'chat') {
                this.mode = 'menu';
            } else if (mParam === 'qu' || mParam === 'quest' || mParam === 'q3') {
                this.mode = 'qu';
            } else if (mParam === 'de' || mParam === 'web' || mParam === 'desk' || mParam === 'desktop' || mParam === 'avatar') {
                this.mode = 'web';
            } else if (mParam === 'mo' || mParam === 'mob' || mParam === 'mobile') {
                this.mode = 'mobile';
            } else if (mParam === 'xr' || mParam === 'vr' || mParam === '3d') {
                this.mode = 'xr';
            } else if (mParam === 'ar' || mParam === 'passthrough' || mParam === 'see_through') {
                this.mode = 'ar';
            } else if (mParam === 'hud' || mParam === 'overlay') {
                this.mode = 'hud';
            } else if (mParam === 'vo' || mParam === 'voice' || mParam === 'vocal' || mParam === 'audio' || mParam === 'top' || mParam === 'topbar' || mParam === 'minimal') {
                this.mode = 'voice';
            } else {
                this.mode = this.getDefaultModeForUnit(this.unit);
            }
        } else {
            if (uParam === 'qu' || uParam === 'q3' || uParam === 'quest') {
                this.mode = 'qu';
            } else {
                this.mode = this.getDefaultModeForUnit(this.unit);
            }
        }

        console.log(`[CONTEXT] Operating Unit: ${this.unit.toUpperCase()} | Layout Mode: ${this.mode.toUpperCase()} (Params: m=${mParam || 'none'}, u=${uParam || 'none'})`);
        
        // Add classes for styling flexibility
        document.body.classList.add(`unit-${this.unit}`);
        document.body.classList.add(`mode-${this.mode}`);
        
        if (this.mode === 'mobile' || this.mode === 'menu' || this.mode === 'hud' || this.mode === 'voice') {
            document.documentElement.style.setProperty('--dashboard-width', '100vw');
            document.documentElement.style.setProperty('--dashboard-max-width', '100%');
        }
    }

    private getDefaultModeForUnit(unit: LumaxUnit): LumaxMode {
        switch (unit) {
            case 'mo': return 'mobile';
            case 'de': return 'web';
            case 'qu':
            case 'q3': return 'qu';
            case 'vr':
            case 'xr': return 'xr';
        }
    }

    public getMode(): LumaxMode {
        return this.mode;
    }

    public getUnit(): LumaxUnit {
        return this.unit;
    }

    public isMobile(): boolean {
        return this.mode === 'mobile';
    }

    public isXR(): boolean {
        return this.mode === 'xr';
    }

    public isHUD(): boolean {
        return this.mode === 'hud';
    }

    public isMenu(): boolean {
        return this.mode === 'menu';
    }

    public isVoice(): boolean {
        return this.mode === 'voice';
    }

    public isVRUnit(): boolean {
        return this.unit === 'vr' || this.unit === 'xr';
    }

    /**
     * Optimization: Should we start the heavy 3D engine?
     * We skip 3D in HUD, Voice, and Menu modes to save VRAM and CPU resource.
     */
    public shouldInit3D(): boolean {
        return this.mode !== 'hud' && this.mode !== 'voice' && this.mode !== 'menu';
    }

    /**
     * Parse the 'components' or 'c' parameter to filter layout components dynamically
     */
    public getVisibleTabs(): string[] | null {
        const cParam = this.params.get('components') || this.params.get('c');
        if (!cParam) return null;
        
        const codes = cParam.split(',');
        const map: { [key: string]: string } = {
            'co': 'cognition',
            'di': 'diagnosis',
            'diag': 'diagnosis',
            'pr': 'profile',
            'ne': 'neural',
            'nu': 'nucleus',
            'sw': 'swarm',
            'ag': 'agency',
            'dr': 'dreamscape',
            'mh': 'modelhub',
            'ch': 'chronicle',
            'mo': 'monetizing',
            'vm': 'webvm',
            'vi': 'vision',
            'br': 'branding',
            'vc': 'videochat',
            'as': 'avatarstudio',
            'dt': 'devtools',
            'fm': 'featuremap',
            'se': 'settings'
        };
        
        return codes.map(code => map[code.trim().toLowerCase()]).filter(Boolean);
    }

    /**
     * Get target tab from URL if present, falling back to first visible tab
     */
    public getInitialTab(): string {
        const target = this.params.get('tab') || this.params.get('t') || 'cognition';
        const visible = this.getVisibleTabs();
        if (visible) {
            if (visible.includes(target)) return target;
            return visible[0] || 'cognition';
        }
        return target;
    }

    /**
     * Get version from URL (for tracking)
     */
    public getVersion(): string {
        return this.params.get('v') || 'UNKNOWN';
    }
}

export const contextManager = new ContextManager();
