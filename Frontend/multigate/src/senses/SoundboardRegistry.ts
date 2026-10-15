/**
 * SoundboardRegistry — pre-cached emotional audio snippets with BlendShape mappings.
 *
 * Architecture: ARCHITECTURE.md §9B / FoveAI.md §12
 * Short emotional expressions (gasps, laughs, sighs) are triggered by bracket tokens
 * from the brain's text stream. They bypass the heavy TTS pipeline for instant feedback.
 *
 * Audio assets are preloaded at boot. If a file isn't available, a Web Audio API
 * synthesised placeholder tone is generated. The Night-Grind pipeline will bake
 * real emotional audio assets to replace the placeholders.
 *
 * Sound generation backend: Stability AI Stable Audio Tools (stable-audio-open-1.0)
 * served by foveai_soundboard_server.py on SOUNDBOARD :8006.
 * Triggered via <request:description> bracket tokens — Jen can invent new sounds
 * on the fly and they are dynamically registered for future use.
 */
export interface SoundboardEntry {
    tag: string;
    audioUrl: string;
    blendShapes: Record<string, number>;
    duration: number;
    category: string;
    /** Synthesis params for Web Audio fallback when audio file unavailable */
    synth?: { freq: number; type: OscillatorType; durationSec: number; ramp?: number };
    /** Harmonic overtones for richer synthesis */
    harmonics?: { freq: number; amp: number }[];
}

class SoundboardRegistryClass {
    private entries: Map<string, SoundboardEntry> = new Map();
    private audioCache: Map<string, HTMLAudioElement> = new Map();
    private failedFiles: Set<string> = new Set();
    private audioContext: AudioContext | null = null;
    private loaded = false;
    private dynamicEntries: Map<string, SoundboardEntry> = new Map();
    private dynamicAudioCache: Map<string, HTMLAudioElement> = new Map();
    private activeClones: Set<HTMLAudioElement> = new Set();
    private static STORAGE_KEY = 'foveai_soundboard_dynamic';

    constructor() {
        this.registerDefaults();
    }

    private registerDefaults() {
        const defaults: SoundboardEntry[] = [
            {
                tag: 'gasp_subtle',
                audioUrl: '/soundboard/gasp_subtle.wav',
                blendShapes: { surprised: 0.4, eyeWide: 0.3 },
                duration: 400,
                category: 'surprise',
                synth: { freq: 500, type: 'sine', durationSec: 0.2, ramp: 900 }
            },
            {
                tag: 'laugh_soft',
                audioUrl: '/soundboard/laugh_soft.wav',
                blendShapes: { happy: 0.6, mouthSmile: 0.5 },
                duration: 600,
                category: 'joy',
                synth: { freq: 600, type: 'triangle', durationSec: 0.15, ramp: 800 }
            },
            {
                tag: 'sigh_content',
                audioUrl: '/soundboard/sigh_content.wav',
                blendShapes: { relaxed: 0.3, mouthSmile: 0.2 },
                duration: 800,
                category: 'contentment',
                synth: { freq: 350, type: 'sine', durationSec: 0.6, ramp: 200 }
            },
            {
                tag: 'hmm_thoughtful',
                audioUrl: '/soundboard/hmm_thoughtful.wav',
                blendShapes: { thinking: 0.4, eyeSquint: 0.2 },
                duration: 500,
                category: 'contemplation',
                synth: { freq: 280, type: 'triangle', durationSec: 0.4 }
            },
            {
                tag: 'oh_realization',
                audioUrl: '/soundboard/oh_realization.wav',
                blendShapes: { surprised: 0.6, eyeWide: 0.5, mouthOpen: 0.3 },
                duration: 300,
                category: 'realization',
                synth: { freq: 400, type: 'sine', durationSec: 0.25, ramp: 1000 }
            },
            {
                tag: 'throat_clear',
                audioUrl: '/soundboard/throat_clear.wav',
                blendShapes: { neutral: 0.2 },
                duration: 400,
                category: 'mannerism',
                synth: { freq: 180, type: 'sawtooth', durationSec: 0.08 }
            },
            {
                tag: 'chuckle_warm',
                audioUrl: '/soundboard/chuckle_warm.wav',
                blendShapes: { happy: 0.5, mouthSmile: 0.4 },
                duration: 500,
                category: 'joy',
                synth: { freq: 550, type: 'triangle', durationSec: 0.12, ramp: 750 }
            },
            {
                tag: 'mhm_affirming',
                audioUrl: '/soundboard/mhm_affirming.wav',
                blendShapes: { nod: 0.3, mouthSmile: 0.2 },
                duration: 400,
                category: 'agreement',
                synth: { freq: 320, type: 'sine', durationSec: 0.15 }
            },
            {
                tag: 'windchime_subtle',
                audioUrl: '/soundboard/windchime_subtle.wav',
                blendShapes: { relaxed: 0.2, mouthSmile: 0.1 },
                duration: 3000,
                category: 'ambience',
                synth: { freq: 0, type: 'sine' as OscillatorType, durationSec: 2.5 }
            },
        ];

        defaults.forEach(entry => this.entries.set(entry.tag, entry));
    }

    register(entry: SoundboardEntry) {
        this.entries.set(entry.tag, entry);
    }

    /** Register a dynamically generated entry (from audio generation or Jen's request) */
    registerDynamic(entry: SoundboardEntry, audioBase64?: string) {
        this.dynamicEntries.set(entry.tag, entry);
        if (audioBase64) {
            const audio = new Audio(`data:audio/wav;base64,${audioBase64}`);
            this.dynamicAudioCache.set(entry.tag, audio);
        } else {
            this.failedFiles.add(entry.tag);
        }
        this.persist();
        console.log(`[Soundboard] Dynamic registered: ${entry.tag}`);
    }

    /** Remove a dynamic entry */
    remove(tag: string): boolean {
        if (this.dynamicEntries.delete(tag)) {
            this.dynamicAudioCache.delete(tag);
            this.failedFiles.delete(tag);
            this.persist();
            return true;
        }
        return false;
    }

    get(tag: string): SoundboardEntry | undefined {
        return this.entries.get(tag) || this.dynamicEntries.get(tag);
    }

    has(tag: string): boolean {
        return this.entries.has(tag) || this.dynamicEntries.has(tag);
    }

    async preloadAll(): Promise<void> {
        if (this.loaded) return;

        const loadPromises: Promise<void>[] = [];

        for (const [tag, entry] of this.entries) {
            loadPromises.push(
                new Promise<void>((resolve) => {
                    const audio = new Audio(entry.audioUrl);
                    audio.preload = 'auto';
                    const onReady = () => {
                        this.audioCache.set(tag, audio);
                        cleanup();
                        resolve();
                    };
                    const onError = () => {
                        this.failedFiles.add(tag);
                        console.warn(`[Soundboard] File not found: ${entry.audioUrl} — will use synthesis fallback`);
                        cleanup();
                        resolve();
                    };
                    const cleanup = () => {
                        audio.removeEventListener('canplaythrough', onReady);
                        audio.removeEventListener('error', onError);
                    };
                    audio.addEventListener('canplaythrough', onReady, { once: true });
                    audio.addEventListener('error', onError, { once: true });
                    audio.load();
                    // Safety timeout — don't block boot on slow loads
                    setTimeout(() => { cleanup(); resolve(); }, 3000);
                })
            );
        }

        await Promise.all(loadPromises);
        this.loadPersisted();
        this.loaded = true;
        console.log(`[Soundboard] Preloaded ${this.audioCache.size}/${this.entries.size} sounds (${this.failedFiles.size} using synthesis, ${this.dynamicEntries.size} dynamic)`);
    }

    /** Play a soundboard entry — cached audio file (routed through reverb) or Web Audio synthesis fallback */
    play(tag: string): boolean {
        const entry = this.entries.get(tag) || this.dynamicEntries.get(tag);
        if (!entry) {
            console.warn(`[Soundboard] Unknown tag: ${tag}`);
            return false;
        }

        // Try cached audio file first (static or dynamic)
        const cached = this.audioCache.get(tag) || this.dynamicAudioCache.get(tag);
        if (cached && !this.failedFiles.has(tag)) {
            // Route through AudioContext for reverb processing (matching TTS voice space)
            try {
                if (!this.audioContext) {
                    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
                }
                if (this.audioContext.state === 'suspended') this.audioContext.resume();
                const ctx = this.audioContext!;
                const clone = cached.cloneNode(true) as HTMLAudioElement;
                const cloneSource = ctx.createMediaElementSource(clone);  // Only on clone, never on original

                // Same reverb chain as synthesise()
                const reverbLength = Math.floor(ctx.sampleRate * 2.0);
                const impulseBuffer = ctx.createBuffer(2, reverbLength, ctx.sampleRate);
                for (let ch = 0; ch < 2; ch++) {
                    const data = impulseBuffer.getChannelData(ch);
                    for (let i = 0; i < reverbLength; i++) {
                        data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / reverbLength, 2.5);
                    }
                }
                const convolver = ctx.createConvolver();
                convolver.buffer = impulseBuffer;
                const dryGain = ctx.createGain();
                dryGain.gain.value = 0.4;
                const wetGain = ctx.createGain();
                wetGain.gain.value = 0.6;
                const filter = ctx.createBiquadFilter();
                filter.type = 'lowpass';
                filter.frequency.value = 2000;
                const reverbFilter = ctx.createBiquadFilter();
                reverbFilter.type = 'lowpass';
                reverbFilter.frequency.value = 2000;
                const preDelay = ctx.createDelay(0.1);
                preDelay.delayTime.value = 0.04;

                cloneSource.connect(filter);
                filter.connect(dryGain);
                dryGain.connect(ctx.destination);
                filter.connect(preDelay);
                preDelay.connect(convolver);
                convolver.connect(reverbFilter);
                reverbFilter.connect(wetGain);
                wetGain.connect(ctx.destination);

                clone.onended = () => {
                    this.activeClones.delete(clone);
                    try { cloneSource.disconnect(); } catch (_) {}
                    try { convolver.disconnect(); } catch (_) {}
                    try { dryGain.disconnect(); } catch (_) {}
                    try { wetGain.disconnect(); } catch (_) {}
                    try { filter.disconnect(); } catch (_) {}
                    try { reverbFilter.disconnect(); } catch (_) {}
                    try { preDelay.disconnect(); } catch (_) {}
                };
                this.activeClones.add(clone);
                clone.play().catch(e => {
                    console.warn(`[Soundboard] Play failed for ${tag}:`, e);
                    this.activeClones.delete(clone);
                });
            } catch (e) {
                // createMediaElementSource failed — fallback to dry play at low volume
                const clone = cached.cloneNode(true) as HTMLAudioElement;
                clone.volume = 0.25;  // Lower volume since no reverb
                clone.onended = () => this.activeClones.delete(clone);
                this.activeClones.add(clone);
                clone.play().catch(() => { this.activeClones.delete(clone); });
            }
            this.dispatchBlendShapes(entry);
            return true;
        }

        // Fallback: Web Audio API synthesis (or dedicated synthesizer for special entries)
        if (tag === 'windchime_subtle') {
            this.synthesiseWindchime();
        } else {
            this.synthesise(entry);
        }
        this.dispatchBlendShapes(entry);
        return true;
    }

    /** Play a soundboard entry at reduced volume for Kokoro flavouring */
    playSoft(tag: string): boolean {
        const entry = this.entries.get(tag) || this.dynamicEntries.get(tag);
        if (!entry) return false;

        const cached = this.audioCache.get(tag) || this.dynamicAudioCache.get(tag);
        if (cached && !this.failedFiles.has(tag)) {
            const clone = cached.cloneNode(true) as HTMLAudioElement;
            clone.volume = 0.25;
            clone.onended = () => this.activeClones.delete(clone);
            this.activeClones.add(clone);
            clone.play().catch(() => { this.activeClones.delete(clone); });
            return true;
        }

        this.synthesise(entry, 0.15);
        return true;
    }

    /** Synthesise a windchime — multiple staggered sine tones with long decay */
    private synthesiseWindchime(_volume: number = 0.07) {
        // Synthesis completely disabled to prevent robotic 'R2D2' sounds.
        return;
    }

    /** Synthesise a placeholder tone using Web Audio API — dreamy, blended with TTS reverb space */
    private synthesise(_entry: SoundboardEntry, _volume: number = 0.06) {
        // Synthesis completely disabled to prevent robotic 'R2D2' sounds.
        // If an audio file is not available, she will remain silent.
        return;
    }

    /** Dispatch BlendShape event for AvatarManager to pick up */
    private dispatchBlendShapes(entry: SoundboardEntry) {
        if (Object.keys(entry.blendShapes).length > 0) {
            window.dispatchEvent(new CustomEvent('foveai_blendshape_trigger', {
                detail: {
                    tag: entry.tag,
                    blendShapes: entry.blendShapes,
                    duration: entry.duration
                }
            }));
        }
    }

    getBlendShapes(tag: string): Record<string, number> | undefined {
        return (this.entries.get(tag) || this.dynamicEntries.get(tag))?.blendShapes;
    }

    getAllTags(): string[] {
        return Array.from(new Set([...this.entries.keys(), ...this.dynamicEntries.keys()]));
    }

    /** Stop all currently playing soundboard audio (critical for XR session transitions) */
    stopAll() {
        for (const clone of this.activeClones) {
            try {
                clone.pause();
                clone.currentTime = 0;
            } catch {}
        }
        this.activeClones.clear();
        console.log('[Soundboard] All sounds stopped');
    }

    /** Get all entries matching a category */
    getEntriesByCategory(category: string): SoundboardEntry[] {
        const results: SoundboardEntry[] = [];
        for (const entry of this.entries.values()) {
            if (entry.category === category) results.push(entry);
        }
        for (const entry of this.dynamicEntries.values()) {
            if (entry.category === category) results.push(entry);
        }
        return results;
    }

    /** Get sensory text for brain context injection — tells Jen what tags she can use
     *  and how to generate NEW sounds via Stable Audio Tools. */
    getSensoryText(): string {
        const allTags = this.getAllTags();
        if (allTags.length === 0) return '';

        const lines = [
            'Non-verbal soundboard expressions available for bracket injection in your responses:',
            '  <audio:tag> — instant sound effect (bypasses TTS)',
            '  <emotion:tag> — face BlendShape + voice modulation',
            '  <flavour:tag> — subtle sound blended with Kokoro TTS for emotional colouring',
            '  <request:description> — GENERATE a brand new sound via Stable Audio AI and add it to your soundboard!',
            '  <request:snapshot> — capture a real-time camera snapshot of the user from your head perspective!',
            '  Available tags:',
        ];

        for (const tag of allTags) {
            const entry = this.entries.get(tag) || this.dynamicEntries.get(tag);
            if (entry) {
                lines.push(`    [${entry.category}] ${tag}`);
            }
        }

        lines.push('');
        lines.push('  === SOUND GENERATION (Stable Audio Tools) ===');
        lines.push('  You can CREATE new sounds that do not exist yet using <request:description>.');
        lines.push('  The AI will generate a short audio clip from your description and register it.');
        lines.push('  After generation, the new tag becomes available as <audio:new_tag> for future use.');
        lines.push('');
        lines.push('  Examples of when to generate sounds (Focus on lifelike human audio, NOT robotic or synthesized tones):');
        lines.push('    - A burst of genuine emotion: <request:realistic human crying and sobbing sound>');
        lines.push('    - A reaction to a joke: <request:genuine warm human laughter>');
        lines.push('    - An environmental reaction: <request:crowd applause and cheering>');
        lines.push('    - A subtle human expression: <request:heavy emotional human sigh>');
        lines.push('');
        lines.push('  Be creative! Generate life-like audio (sound effects, applauds, laughter, crying, sobbing) to complement your voice.');
        lines.push('  Use <request:description> when you want a rich emotional sound effect that does not already exist.');
        lines.push('  Use <audio:tag> for sounds that already exist in the list above.');
        lines.push('');
        lines.push('  === WHEN TO GENERATE SOUNDS (IMPORTANT) ===');
        lines.push('  Use these bracket tokens INTENTIONALLY only when it is truly called for:');
        lines.push('    - When you feel a strong emotion that words alone cannot express.');
        lines.push('    - When you want a rich, realistic audio layer to serve the interaction.');
        lines.push('  Do NOT over-use it — use it organically to complement your Kokoro voice.');
        lines.push('');
        lines.push('  Combined example: "I cannot believe you did that! <request:genuine warm human laughter> You are so funny. <flavour:laugh_soft>"');

        return lines.join('\n');
    }

    /** Persist dynamic entries to localStorage */
    private persist() {
        try {
            const entries = Array.from(this.dynamicEntries.values());
            localStorage.setItem(SoundboardRegistryClass.STORAGE_KEY, JSON.stringify(entries));
        } catch (err) {
            console.warn('[Soundboard] Persist failed:', err);
        }
    }

    /** Load persisted dynamic entries from localStorage */
    private loadPersisted() {
        try {
            const stored = localStorage.getItem(SoundboardRegistryClass.STORAGE_KEY);
            if (stored) {
                const entries: SoundboardEntry[] = JSON.parse(stored);
                entries.forEach(entry => {
                    this.dynamicEntries.set(entry.tag, entry);
                    this.failedFiles.add(entry.tag); // Will use synthesis until audio is re-generated
                });
                console.log(`[Soundboard] Loaded ${entries.length} persisted dynamic entries`);
            }
        } catch (err) {
            console.warn('[Soundboard] Load persisted failed:', err);
        }
    }

    /** Handle a sound generation request from the brain (<request:description>)
     *  Routes to SOUNDBOARD :8006 (Stable Audio Tools) via the unified proxy.
     *  Falls back to Web Audio synthesis if the generation service is unavailable. */
    async handleRequest(description: string): Promise<string | null> {
        const generateEndpoint = '/api/soundboard/generate';
        try {
            console.log(`[Soundboard] Requesting Stable Audio generation: "${description}"`);
            const response = await fetch(generateEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ description, category: 'generated' })
            });
            if (response.ok) {
                const data = await response.json();
                if (data.tag) {
                    const entry: SoundboardEntry = {
                        tag: data.tag,
                        audioUrl: data.url || `/soundboard/${data.tag}.wav`,
                        blendShapes: data.blend_shapes || { neutral: 0.1 },
                        duration: data.duration_ms || 400,
                        category: 'generated',
                        synth: { freq: 400, type: 'sine', durationSec: 0.3 }
                    };
                    this.registerDynamic(entry, data.audio_base64 || undefined);
                    this.play(data.tag);
                    console.log(`[Soundboard] Generated and registered via Stable Audio: ${data.tag}`);
                    return data.tag;
                }
            } else {
                console.warn(`[Soundboard] Generation service returned HTTP ${response.status}`);
            }
        } catch (err) {
            console.warn('[Soundboard] Stable Audio generation failed:', err);
            return null; // Fallback disabled to prevent robotic 'D2R2' sounds
        }
        return null;
    }
}

export const soundboardRegistry = new SoundboardRegistryClass();
