/**
 * ═══════════════════════════════════════════════════════════════════════
 * SoftLayerLoader — Hot-reloadable JS module system for the XR_Vessel
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Fetches JS modules from the XRLF API (/softlayer/modules/{name}.js and
 * /softlayer/{config}.js) and executes them in a sandboxed FoveAI context.
 *
 * Modules can call:
 *   FoveAI.setParam(path, value)       — set a hot-reloadable parameter
 *   FoveAI.getParam(path)              — get a parameter
 *   FoveAI.log(msg)                    — log to console
 *   FoveAI.triggerGesture(name)        — trigger avatar gesture
 *   FoveAI.setEmotion(emotion, intensity) — set avatar emotion
 *   FoveAI.setHUDColor(corner, r, g, b, a) — set HUD corner color
 *   FoveAI.setHUDValue(corner, text)   — set HUD metric text
 *   FoveAI.setHUDLabel(corner, label)  — set HUD label
 *   FoveAI.setHUDAlpha(alpha)          — set HUD transparency
 *   FoveAI.chameleon.setColor(surface, r, g, b, a)
 *   FoveAI.clothing.setOutfit(name)
 *   FoveAI.clothing.setColor(part, r, g, b)
 *   FoveAI.lighting.setMood(mood)
 *   FoveAI.particles.enable(type, bool)
 *   FoveAI.particles.setDensity(type, density)
 *   FoveAI.sky.setColor(r, g, b)
 *   FoveAI.sky.setHorizon(r, g, b)
 *   FoveAI.sky.setTimeOfDay(hour)
 *   FoveAI.wall.emerge(dirX, dirZ, height, speed)
 *   FoveAI.wall.dissolve()
 *
 * Modules can define lifecycle hooks:
 *   function {moduleName}_onLoad()    — called when module is loaded
 *   function {moduleName}_onUpdate(dt) — called every frame
 *   function {moduleName}_onUnload()  — called when module is unloaded
 *
 * Usage:
 *   const loader = new SoftLayerLoader('http://127.0.0.1:8402');
 *   await loader.init();
 *   loader.startUpdateLoop();
 */

const API_BASE = 'http://127.0.0.1:8402';

// Global param store (accessible by MovementEngine and other systems)
declare global {
    interface Window {
        FoveAIParams?: Record<string, any>;
        FoveAIParamsListeners?: Record<string, ((value: any) => void)[]>;
    }
}

export class SoftLayerLoader {
    private apiBase: string;
    private loadedModules: Map<string, { onLoad?: () => void; onUpdate?: (dt: number) => void; onUnload?: () => void }> = new Map();
    private updateCallbacks: ((dt: number) => void)[] = [];
    private lastUpdateTime: number = 0;
    private initialized: boolean = false;

    // Module list to load (configs first, then modules)
    private readonly CONFIG_FILES = [
        'hud_config.js',
        'behavior_config.js',
        'experience_config.js',
    ];
    private readonly MODULE_FILES = [
        'lighting.js',
        'sky.js',
        'particles.js',
        'chameleon.js',
        'clothing.js',
        'wall.js',
        'chat_relay.js',
    ];

    constructor(apiBase: string = API_BASE) {
        this.apiBase = apiBase;
        // Initialize global param store
        if (!window.FoveAIParams) window.FoveAIParams = {};
        if (!window.FoveAIParamsListeners) window.FoveAIParamsListeners = {};
    }

    /**
     * Initialize the SoftLayer system — load all configs and modules.
     */
    public async init(): Promise<void> {
        if (this.initialized) return;

        console.log('[SoftLayer] Initializing — fetching modules from', this.apiBase);

        // Load config files first (they set params that modules may read)
        for (const file of this.CONFIG_FILES) {
            await this.loadConfig(file);
        }

        // Then load modules
        for (const file of this.MODULE_FILES) {
            await this.loadModule(file);
        }

        this.initialized = true;
        console.log('[SoftLayer] All modules loaded. Starting update loop.');
    }

    /**
     * Fetch and execute a config file from /softlayer/{name}.js
     */
    private async loadConfig(name: string): Promise<void> {
        try {
            const url = `${this.apiBase}/softlayer/${name}`;
            const resp = await fetch(url);
            if (!resp.ok) {
                console.warn(`[SoftLayer] Config ${name} not found (${resp.status})`);
                return;
            }
            const source = await resp.text();
            const foveAI = this.createFoveAIAPI(name.replace('.js', ''));
            // Execute in a sandboxed function scope
            const fn = new Function('FoveAI', source);
            fn(foveAI);
            console.log(`[SoftLayer] Config loaded: ${name}`);
        } catch (e) {
            console.warn(`[SoftLayer] Failed to load config ${name}:`, e);
        }
    }

    /**
     * Fetch and execute a module from /softlayer/modules/{name}.js
     * Extracts lifecycle hooks (onLoad, onUpdate, onUnload).
     */
    private async loadModule(name: string): Promise<void> {
        try {
            const url = `${this.apiBase}/softlayer/modules/${name}`;
            const resp = await fetch(url);
            if (!resp.ok) {
                console.warn(`[SoftLayer] Module ${name} not found (${resp.status})`);
                return;
            }
            const source = await resp.text();
            const moduleName = name.replace('.js', '');
            const foveAI = this.createFoveAIAPI(moduleName);

            // Execute the module source — it defines functions in its scope
            // We capture the lifecycle hooks by evaluating in a scope that
            // returns them
            const wrappedSource = `
                ${source}
                return {
                    onLoad: typeof ${moduleName}_onLoad === 'function' ? ${moduleName}_onLoad : undefined,
                    onUpdate: typeof ${moduleName}_onUpdate === 'function' ? ${moduleName}_onUpdate : undefined,
                    onUnload: typeof ${moduleName}_onUnload === 'function' ? ${moduleName}_onUnload : undefined,
                };
            `;
            const fn = new Function('FoveAI', wrappedSource);
            const hooks = fn(foveAI);

            this.loadedModules.set(moduleName, hooks);

            // Call onLoad
            if (hooks.onLoad) {
                try { hooks.onLoad(); } catch (e) { console.warn(`[SoftLayer] ${moduleName} onLoad error:`, e); }
            }

            // Register update callback
            if (hooks.onUpdate) {
                this.updateCallbacks.push(hooks.onUpdate);
            }

            console.log(`[SoftLayer] Module loaded: ${name}`);
        } catch (e) {
            console.warn(`[SoftLayer] Failed to load module ${name}:`, e);
        }
    }

    /**
     * Create the FoveAI API object that modules use to interact with the system.
     */
    private createFoveAIAPI(moduleName: string): any {
        const self = this;

        const FoveAI: any = {
            // ── Param system ──
            setParam(path: string, value: any) {
                window.FoveAIParams![path] = value;
                // Notify listeners
                const listeners = window.FoveAIParamsListeners?.[path];
                if (listeners) {
                    for (const cb of listeners) cb(value);
                }
            },
            getParam(path: string): any {
                return window.FoveAIParams![path];
            },
            log(msg: string) {
                console.log(`[SoftLayer/${moduleName}] ${msg}`);
            },

            // ── Avatar control ──
            triggerGesture(name: string) {
                window.dispatchEvent(new CustomEvent('foveai_animation_trigger', {
                    detail: { name, params: { loop: 'false', fade: '0.3' } }
                }));
            },
            setEmotion(emotion: string, intensity: number = 1.0) {
                window.dispatchEvent(new CustomEvent('foveai_emotion_trigger', {
                    detail: { emotion, intensity }
                }));
            },

            // ── HUD control ──
            setHUDColor(corner: string, r: number, g: number, b: number, a: number) {
                window.dispatchEvent(new CustomEvent('foveai_hud_color', {
                    detail: { corner, r, g, b, a }
                }));
            },
            setHUDValue(corner: string, text: string) {
                window.dispatchEvent(new CustomEvent('foveai_hud_value', {
                    detail: { corner, text }
                }));
            },
            setHUDLabel(corner: string, label: string) {
                window.dispatchEvent(new CustomEvent('foveai_hud_label', {
                    detail: { corner, label }
                }));
            },
            setHUDAlpha(alpha: number) {
                window.dispatchEvent(new CustomEvent('foveai_hud_alpha', {
                    detail: { alpha }
                }));
            },

            // ── Subsystem APIs (dispatch as events for the relevant systems) ──
            chameleon: {
                setColor(surface: string, r: number, g: number, b: number, a: number) {
                    window.dispatchEvent(new CustomEvent('foveai_chameleon_color', {
                        detail: { surface, r, g, b, a }
                    }));
                },
                setAlpha(surface: string, alpha: number) {
                    window.dispatchEvent(new CustomEvent('foveai_chameleon_alpha', {
                        detail: { surface, alpha }
                    }));
                },
                setTransitionSpeed(speed: number) {
                    FoveAI.setParam('chameleon.transitionSpeed', speed);
                },
                pulse(surface: string, freq: number, amp: number) {
                    window.dispatchEvent(new CustomEvent('foveai_chameleon_pulse', {
                        detail: { surface, freq, amp }
                    }));
                },
            },
            clothing: {
                setOutfit(name: string) {
                    window.dispatchEvent(new CustomEvent('foveai_clothing_outfit', {
                        detail: { name }
                    }));
                },
                setColor(part: string, r: number, g: number, b: number) {
                    window.dispatchEvent(new CustomEvent('foveai_clothing_color', {
                        detail: { part, r, g, b }
                    }));
                },
                setMetallic(m: number) {
                    window.dispatchEvent(new CustomEvent('foveai_clothing_metallic', {
                        detail: { metallic: m }
                    }));
                },
                setSmoothness(s: number) {
                    window.dispatchEvent(new CustomEvent('foveai_clothing_smoothness', {
                        detail: { smoothness: s }
                    }));
                },
                setEmission(r: number, g: number, b: number, i: number) {
                    window.dispatchEvent(new CustomEvent('foveai_clothing_emission', {
                        detail: { r, g, b, intensity: i }
                    }));
                },
            },
            lighting: {
                setAmbient(r: number, g: number, b: number, intensity: number) {
                    window.dispatchEvent(new CustomEvent('foveai_lighting_ambient', {
                        detail: { r, g, b, intensity }
                    }));
                },
                setKeyLight(r: number, g: number, b: number, intensity: number) {
                    window.dispatchEvent(new CustomEvent('foveai_lighting_key', {
                        detail: { r, g, b, intensity }
                    }));
                },
                setMood(mood: string) {
                    window.dispatchEvent(new CustomEvent('foveai_lighting_mood', {
                        detail: { mood }
                    }));
                },
            },
            particles: {
                enable(type: string, enabled: boolean) {
                    window.dispatchEvent(new CustomEvent('foveai_particles_enable', {
                        detail: { type, enabled }
                    }));
                },
                setDensity(type: string, density: number) {
                    window.dispatchEvent(new CustomEvent('foveai_particles_density', {
                        detail: { type, density }
                    }));
                },
            },
            sky: {
                setColor(r: number, g: number, b: number) {
                    window.dispatchEvent(new CustomEvent('foveai_sky_color', {
                        detail: { r, g, b }
                    }));
                },
                setHorizon(r: number, g: number, b: number) {
                    window.dispatchEvent(new CustomEvent('foveai_sky_horizon', {
                        detail: { r, g, b }
                    }));
                },
                setTimeOfDay(hour: number) {
                    window.dispatchEvent(new CustomEvent('foveai_sky_time', {
                        detail: { hour }
                    }));
                },
            },
            wall: {
                emerge(dirX: number, dirZ: number, height: number, speed: number) {
                    window.dispatchEvent(new CustomEvent('foveai_wall_emerge', {
                        detail: { dirX, dirZ, height, speed }
                    }));
                },
                dissolve() {
                    window.dispatchEvent(new CustomEvent('foveai_wall_dissolve'));
                },
                setColor(r: number, g: number, b: number) {
                    window.dispatchEvent(new CustomEvent('foveai_wall_color', {
                        detail: { r, g, b }
                    }));
                },
                setShake(intensity: number) {
                    window.dispatchEvent(new CustomEvent('foveai_wall_shake', {
                        detail: { intensity }
                    }));
                },
            },

            // ── Live webcam plaster (project room webcam onto scanned walls) ──
            webcamPlaster: {
                enable(enabled: boolean) {
                    const se = (window as any).spatialEnvironment;
                    if (se) se.setWebcamPlasterEnabled(enabled);
                },
                setOpacity(opacity: number) {
                    const se = (window as any).spatialEnvironment;
                    if (se) se.setWebcamPlasterOpacity(opacity);
                },
                setOrientation(orientation: 'portrait' | 'landscape') {
                    const se = (window as any).spatialEnvironment;
                    if (se) se.setWebcamOrientation(orientation);
                },
                getStatus() {
                    const se = (window as any).spatialEnvironment;
                    return se ? se.getWebcamPlasterStatus() : null;
                },
            },

            // ── "Be Jen" first-person POV mode ──
            jenPOV: {
                enable(enabled: boolean) {
                    (window as any).foveaiSetJenPov?.(enabled);
                },
                toggle() {
                    (window as any).foveaiToggleJenPov?.();
                },
                isActive() {
                    return !!(window as any).foveaiJenPovActive;
                },
            },

            // ── Director voice & Avalanche music ──
            director: {
                speak(text: string) {
                    (window as any).foveaiDirectorVoice?.speakNarrator(text);
                },
                startMusic() {
                    (window as any).foveaiDirectorVoice?.startAvalancheMusic();
                },
                stopMusic() {
                    (window as any).foveaiDirectorVoice?.stopAvalancheMusic();
                },
                toggleMusic() {
                    return (window as any).foveaiDirectorVoice?.toggleAvalancheMusic() || false;
                },
                setVoicePitch(pitch: number) {
                    (window as any).foveaiDirectorVoice?.setVoicePitch(pitch);
                },
                setVoiceRate(rate: number) {
                    (window as any).foveaiDirectorVoice?.setVoiceRate(rate);
                },
                setMusicVolume(vol: number) {
                    (window as any).foveaiDirectorVoice?.setMusicVolume(vol);
                },
                setRadioEffect(enabled: boolean) {
                    (window as any).foveaiDirectorVoice?.setRadioEffect(enabled);
                },
                setRadioIntensity(intensity: number) {
                    (window as any).foveaiDirectorVoice?.setRadioIntensity(intensity);
                },
            },
        };

        return FoveAI;
    }

    /**
     * Start the per-frame update loop for loaded modules.
     */
    public startUpdateLoop(): void {
        this.lastUpdateTime = performance.now();
        const loop = () => {
            const now = performance.now();
            const dt = (now - this.lastUpdateTime) / 1000;
            this.lastUpdateTime = now;

            for (const cb of this.updateCallbacks) {
                try { cb(dt); } catch (e) { /* silently skip module errors */ }
            }

            requestAnimationFrame(loop);
        };
        requestAnimationFrame(loop);
    }

    /**
     * Reload a single module (hot-reload).
     */
    public async reloadModule(name: string): Promise<void> {
        // Unload old version
        const old = this.loadedModules.get(name.replace('.js', ''));
        if (old?.onUnload) {
            try { old.onUnload(); } catch (e) { /* ignore */ }
        }
        // Remove from update callbacks
        if (old?.onUpdate) {
            this.updateCallbacks = this.updateCallbacks.filter(cb => cb !== old.onUpdate);
        }
        // Reload
        await this.loadModule(name);
    }

    /**
     * Reload a config file (hot-reload).
     */
    public async reloadConfig(name: string): Promise<void> {
        await this.loadConfig(name);
    }

    /**
     * Get the list of loaded module names.
     */
    public getLoadedModules(): string[] {
        return Array.from(this.loadedModules.keys());
    }
}
