/**
 * AmbientSoundEngine — atmospheric audio layer for the FoveAI vessel.
 *
 * Generates real-time ambient soundscapes, UI interaction sounds,
 * background drones, and "Jen echo" effects using Web Audio API synthesis.
 * No audio files required — everything is procedurally generated.
 *
 * Layers:
 *   1. AMBIENT — continuous loops (wind, rain, hum, drone)
 *   2. UI — click, hover, transition sounds on user interaction
 *   3. MUSIC — slow generative ambient music loop
 *   4. ECHO — distant filtered echo of Jen's voice when idle
 */
export class AmbientSoundEngine {
    private ctx: AudioContext | null = null;
    private masterGain: GainNode | null = null;
    private ambientGain: GainNode | null = null;
    private uiGain: GainNode | null = null;
    private musicGain: GainNode | null = null;
    private echoGain: GainNode | null = null;
    private musicDelay: DelayNode | null = null;
    private musicFeedback: GainNode | null = null;

    private activeAmbients: Map<string, { sources: AudioScheduledSourceNode[]; gains: GainNode[] }> = new Map();
    private musicInterval: ReturnType<typeof setInterval> | null = null;
    private isRunning: boolean = false;
    
    // Heartbeat references for modulation
    private heartbeatFundamental: OscillatorNode | null = null;
    private heartbeatHarmonics: OscillatorNode[] = [];
    private heartbeatGains: GainNode[] = [];

    // Volume levels (0-1) — reduced 30% for subtlety
    public ambientVolume: number = 0.067;  // Raised 20%
    public uiVolume: number = 0.084;
    public musicVolume: number = 0.028;
    public echoVolume: number = 0.042;

    private _backendAlive: boolean = true;
    private _backendFailCount: number = 0; // Debounce — need 3 consecutive failures before fading
    private _backendCheckInterval: ReturnType<typeof setInterval> | null = null;
    public _delegatedToTopBar: boolean = false;

    constructor() {
        // Wait for user gesture before initializing
        const init = () => {
            this.ensureContext();
            if (!this.isRunning && this.ctx && this.ctx.state === 'running') {
                this.start();
            }
        };
        document.addEventListener('click', init, { once: true });
        document.addEventListener('touchstart', init, { once: true });
        document.addEventListener('keydown', init, { once: true });

        // Backend health check — fade out audio if server dies (e.g. user runs `.\foveai` exit)
        // Also detects TopBar loss and takes back over background audio
        this._backendCheckInterval = setInterval(async () => {
            let topBarAlive = false;
            try {
                // Check TopBar first (if running, it handles background audio)
                const tbResp = await fetch('http://127.0.0.1:19847/status', { signal: AbortSignal.timeout(1500) });
                if (tbResp.ok) {
                    const tbData = await tbResp.json();
                    topBarAlive = true;
                    this._backendAlive = tbData.alive !== false;
                    return; // TopBar is running — let it govern audio
                }
            } catch (_) { /* TopBar not running */ }

            // TopBar disappeared — if we delegated to it, take back over
            if (!topBarAlive && this._delegatedToTopBar) {
                console.log('[Ambient] TopBar lost — taking back background audio');
                this._delegatedToTopBar = false;
                if (!this.isRunning) {
                    this.start(); // Start browser-side audio with 5s fade-in
                }
            }

            try {
                // Check Soul backend directly
                const resp = await fetch('/api/soul/vitals', { signal: AbortSignal.timeout(2000) });
                if (resp.ok) {
                    this._backendAlive = true;
                    this._backendFailCount = 0; // Reset on success
                } else {
                    this._backendFailCount++;
                }
            } catch (_) {
                this._backendFailCount++;
            }

            // Require 3 consecutive failures before declaring backend dead
            // (prevents brief network hiccups from killing audio)
            if (this._backendFailCount >= 3) {
                this._backendAlive = false;
            }

            // If backend is dead, fade out background audio over 5s
            if (!this._backendAlive && this._fadeGain && this.ctx) {
                this._fadeGain.gain.setValueAtTime(this._fadeGain.gain.value, this.ctx.currentTime);
                this._fadeGain.gain.linearRampToValueAtTime(0, this.ctx.currentTime + 5);
            } else if (this._backendAlive && this._fadeGain && this.ctx && this.isRunning) {
                this._fadeGain.gain.setValueAtTime(this._fadeGain.gain.value, this.ctx.currentTime);
                this._fadeGain.gain.linearRampToValueAtTime(1, this.ctx.currentTime + 5);
            }
        }, 4000); // Check every 4s
    }

    private ensureContext(): AudioContext {
        if (!this.ctx) {
            let activeCtx = (window as any).foveaiAudioContext;
            if (!activeCtx) {
                activeCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
                (window as any).foveaiAudioContext = activeCtx;
            }
            this.ctx = activeCtx;
            
            const ctx = activeCtx;
            const masterGain = ctx.createGain();
            masterGain.gain.value = 1.0;
            masterGain.connect(ctx.destination);
            this.masterGain = masterGain;

            // Master fade gain — 5s fade-in/fade-out for BACKGROUND soundscapes only
            // UI sounds bypass this for instant feedback (clicks, hovers shouldn't fade)
            const _fadeGain = ctx.createGain();
            _fadeGain.gain.value = 0; // Start silent, fade in on start()
            _fadeGain.connect(masterGain);
            this._fadeGain = _fadeGain;

            const ambientGain = ctx.createGain();
            ambientGain.gain.value = this.ambientVolume;
            ambientGain.connect(_fadeGain); // Fades with soundscape
            this.ambientGain = ambientGain;

            const uiGain = ctx.createGain();
            uiGain.gain.value = this.uiVolume;
            uiGain.connect(masterGain); // Direct — no fade, instant feedback
            this.uiGain = uiGain;

            const musicGain = ctx.createGain();
            musicGain.gain.value = this.musicVolume;
            musicGain.connect(_fadeGain); // Fades with soundscape
            this.musicGain = musicGain;

            // Persistent delay line for generative windchime music to prevent ticks/clicks
            const musicDelay = ctx.createDelay(2.0);
            musicDelay.delayTime.value = 0.6;
            const musicFeedback = ctx.createGain();
            musicFeedback.gain.value = 0.45; // Gentle feedback loop

            musicDelay.connect(musicFeedback);
            musicFeedback.connect(musicDelay); // Feedback loop
            musicDelay.connect(musicGain); // Send delay to master music gain
            this.musicDelay = musicDelay;
            this.musicFeedback = musicFeedback;

            const echoGain = ctx.createGain();
            echoGain.gain.value = this.echoVolume;
            echoGain.connect(_fadeGain); // Fades with soundscape
            this.echoGain = echoGain;
        }
        if (this.ctx!.state === 'suspended') {
            this.ctx!.resume();
        }
        return this.ctx!;
    }

    private _fadeGain: GainNode | null = null;

    /** Start only UI sounds (clicks, hovers) — no background audio.
     *  Used when TopBar handles background audio but browser handles instant UI feedback. */
    public startUISoundsOnly() {
        this.ensureContext();
        this.attachUISounds();
        console.log('[Ambient] UI sounds only (background delegated to TopBar)');
    }

    /** Start all ambient layers */
    public start() {
        if (this.isRunning) return;
        this.isRunning = true;
        this.ensureContext();

        // 5s fade-in for all soundscapes
        this._fadeGain!.gain.setValueAtTime(this._fadeGain!.gain.value, this.ctx!.currentTime);
        this._fadeGain!.gain.linearRampToValueAtTime(1, this.ctx!.currentTime + 5);

        this.startWindAmbient();
        this.startDeepHum();
        this.startGenerativeMusic();
        this.startHarmonicHeartbeat();
        this.attachUISounds();
        console.log('[Ambient] Sound engine started (5s fade-in)');
    }

    /** Stop all ambient layers with 5s fade-out */
    public stop() {
        this.isRunning = false;
        const ctx = this.ctx;
        // 5s fade-out before actually stopping
        if (ctx && this._fadeGain) {
            this._fadeGain.gain.setValueAtTime(this._fadeGain.gain.value, ctx.currentTime);
            this._fadeGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 5);
            // Actually stop sources after fade completes
            setTimeout(() => {
                for (const [name, layer] of this.activeAmbients) {
                    for (const src of layer.sources) {
                        try { src.stop(); } catch (_) {}
                    }
                }
                this.activeAmbients.clear();
            }, 5500);
        } else {
            // No context — stop immediately
            for (const [name, layer] of this.activeAmbients) {
                for (const src of layer.sources) {
                    try { src.stop(); } catch (_) {}
                }
            }
            this.activeAmbients.clear();
        }
        if (this.musicInterval) {
            clearTimeout(this.musicInterval);
            this.musicInterval = null;
        }
        this.heartbeatFundamental = null;
        this.heartbeatHarmonics = [];
        this.heartbeatGains = [];
        console.log('[Ambient] Sound engine stopping (5s fade-out)');
    }

    // ===== HARMONIC HEARTBEAT LAYER =====
    
    /** Start the Generative Harmonic Heartbeat (Musical Soul) */
    private startHarmonicHeartbeat() {
        const ctx = this.ensureContext();
        if (this.heartbeatFundamental) return;

        const masterGain = ctx.createGain();
        masterGain.gain.value = 0.05; // Sub-perceptual volume
        masterGain.connect(this.ambientGain!);

        // A2 - 110Hz Base existence pulse
        this.heartbeatFundamental = ctx.createOscillator();
        this.heartbeatFundamental.type = 'sine';
        this.heartbeatFundamental.frequency.value = 110;

        const fundGain = ctx.createGain();
        fundGain.gain.value = 0.5; // Always somewhat present
        this.heartbeatFundamental.connect(fundGain);
        fundGain.connect(masterGain);
        this.heartbeatFundamental.start();

        // Prepare 4 dynamic harmonics for chord extensions
        for (let i = 0; i < 4; i++) {
            const osc = ctx.createOscillator();
            osc.type = 'sine';
            osc.frequency.value = 110;
            const gain = ctx.createGain();
            gain.gain.value = 0; // Silent until chord demands it
            osc.connect(gain);
            gain.connect(masterGain);
            osc.start();
            this.heartbeatHarmonics.push(osc);
            this.heartbeatGains.push(gain);
        }
        
        this.activeAmbients.set('heartbeat', { 
            sources: [this.heartbeatFundamental, ...this.heartbeatHarmonics], 
            gains: [fundGain, ...this.heartbeatGains, masterGain]
        });
        
        // Init default calm
        this.setEmotionalChord('neutral');
    }

    /** Morph the Harmonic Heartbeat to match an emotional state */
    public setEmotionalChord(emotion: string) {
        if (!this.heartbeatFundamental) return;
        const ctx = this.ensureContext();
        const now = ctx.currentTime;
        const transitionTime = 6.0; // 6-second smooth glides

        // Ratios mapped to A2 (110Hz)
        let targetChord: number[] = [1.498]; // Default: Perfect 5th (Calm/Neutral)

        switch(emotion.toLowerCase()) {
            case 'neutral': targetChord = [1.498]; break; // open fifth
            case 'calm': targetChord = [1.333, 1.498]; break; // fourth and fifth
            case 'happy': targetChord = [1.260, 1.498]; break; // major triad
            case 'curious': targetChord = [1.260, 1.498, 1.888]; break; // major 7th chord
            case 'sad': 
            case 'concerned': targetChord = [1.189, 1.498]; break; // minor chord
            case 'excited': targetChord = [1.122, 1.498]; break; // suspended (major 2nd)
            case 'alert':
            case 'angry': targetChord = [1.414]; break; // tritone (dissonance)
            default: targetChord = [1.498]; break;
        }

        for (let i = 0; i < 4; i++) {
            const osc = this.heartbeatHarmonics[i];
            const gain = this.heartbeatGains[i];
            
            if (i < targetChord.length) {
                // Glide frequency
                osc.frequency.setTargetAtTime(110 * targetChord[i], now, transitionTime / 3);
                // Fade in harmonic
                gain.gain.setTargetAtTime(0.3 / targetChord.length, now, transitionTime / 3);
            } else {
                // Fade out unused harmonic
                gain.gain.setTargetAtTime(0.0001, now, transitionTime / 3);
            }
        }
    }

    // ===== AMBIENT LAYER =====

    /** Subtle wind — filtered noise with slow modulation (seamless loop) */
    private startWindAmbient() {
        const ctx = this.ensureContext();
        const bufferSize = 10 * ctx.sampleRate; // 10s buffer — long enough for seamless loop
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);

        // Pink noise (better than white for wind)
        // Use overlapping crossfade at loop boundary to avoid click
        let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
        // Save initial filter state for seamless crossfade
        for (let i = 0; i < bufferSize; i++) {
            const white = Math.random() * 2 - 1;
            b0 = 0.99886 * b0 + white * 0.0555179;
            b1 = 0.99332 * b1 + white * 0.0750759;
            b2 = 0.96900 * b2 + white * 0.1538520;
            b3 = 0.86650 * b3 + white * 0.3104856;
            b4 = 0.55000 * b4 + white * 0.5329522;
            b5 = -0.7616 * b5 - white * 0.0168980;
            data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.05;
            b6 = white * 0.115926;
        }
        // Crossfade last 0.5s into start to eliminate loop click
        const fadeLen = Math.floor(0.5 * ctx.sampleRate);
        for (let i = 0; i < fadeLen; i++) {
            const t = i / fadeLen; // 0→1
            const endIdx = bufferSize - fadeLen + i;
            data[i] = data[i] * t + data[endIdx] * (1 - t);
        }

        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.loop = true;

        // Low-pass filter for wind character
        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 400;
        filter.Q.value = 0.5;

        // Slow LFO modulation on filter frequency (gusts)
        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.type = 'sine';
        lfo.frequency.value = 0.08; // Very slow modulation
        lfoGain.gain.value = 200; // Modulation depth
        lfo.connect(lfoGain);
        lfoGain.connect(filter.frequency);

        // Volume envelope with slow fade-in
        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(1, ctx.currentTime + 3); // 3s fade-in

        source.connect(filter);
        filter.connect(gain);
        gain.connect(this.ambientGain!);

        source.start(0);
        lfo.start(0);

        this.activeAmbients.set('wind', { sources: [source, lfo], gains: [gain] });
    }

    /** Deep warm emotional synth pad — 5-octave chord progression that gives the vessel presence */
    private startDeepHum() {
        const ctx = this.ensureContext();

        // 5-Octave C Major 9 chord (C2, G2, E3, B3) instead of muffled 55Hz sub-bass
        const freqs = [130.81, 196.00, 329.63, 493.88];
        const oscs: OscillatorNode[] = [];
        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 1200; // Raised from 120Hz to 1200Hz so harmonics shine cleanly!
        filter.Q.value = 1;

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.08, ctx.currentTime + 5); // Clean, warm ambient level

        freqs.forEach(f => {
            const osc = ctx.createOscillator();
            osc.type = 'sine';
            osc.frequency.value = f;
            osc.connect(filter);
            osc.start(0);
            oscs.push(osc);
        });

        // Very slow detune drift for organic analog movement
        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.type = 'sine';
        lfo.frequency.value = 0.03;
        lfoGain.gain.value = 0.8;
        lfo.connect(lfoGain);
        oscs.forEach(o => lfoGain.connect(o.frequency));
        lfo.start(0);

        filter.connect(gain);
        gain.connect(this.ambientGain!);

        this.activeAmbients.set('hum', { sources: [...oscs, lfo], gains: [gain] });
    }

    // ===== MUSIC LAYER =====

    /** Generative ambient music — slow, delicate windchimes with zero-click persistent delay */
    private startGenerativeMusic() {
        const ctx = this.ensureContext();

        // High pentatonic scale for bright, delicate, spacey windchimes (C5-C7)
        const scale = [
            523.25, 587.33, 659.26, 783.99, 880.00,       // C5-A5
            1046.50, 1174.66, 1318.51, 1567.98, 1760.00,  // C6-A6
            2093.00                                       // C7
        ];

        const playChimeNote = () => {
            if (!this.isRunning || !this.musicGain) return;

            const freq = scale[Math.floor(Math.random() * scale.length)];
            
            // Create a multi-harmonic chime structure (fundamental + metallic overtones)
            const osc1 = ctx.createOscillator(); // Fundamental
            const gain1 = ctx.createGain();
            
            const osc2 = ctx.createOscillator(); // Overtone 1 (metallic)
            const gain2 = ctx.createGain();

            const osc3 = ctx.createOscillator(); // Overtone 2 (high sheen)
            const gain3 = ctx.createGain();

            osc1.type = 'sine';
            osc1.frequency.value = freq * (0.998 + Math.random() * 0.004); // Detuned fundamental
            
            osc2.type = 'sine';
            osc2.frequency.value = freq * 2.76 * (0.997 + Math.random() * 0.006);
            
            osc3.type = 'sine';
            osc3.frequency.value = freq * 5.40 * (0.996 + Math.random() * 0.008);

            const baseVol = 0.04 + Math.random() * 0.05;

            // Fundamental: gentle attack, long dreamy decay
            gain1.gain.setValueAtTime(0, ctx.currentTime);
            gain1.gain.linearRampToValueAtTime(baseVol, ctx.currentTime + 0.05);
            gain1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 5.0);

            // Overtone 1: fast attack, fast decay
            gain2.gain.setValueAtTime(0, ctx.currentTime);
            gain2.gain.linearRampToValueAtTime(baseVol * 0.35, ctx.currentTime + 0.015);
            gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);

            // Overtone 2: fast attack, very fast decay
            gain3.gain.setValueAtTime(0, ctx.currentTime);
            gain3.gain.linearRampToValueAtTime(baseVol * 0.15, ctx.currentTime + 0.01);
            gain3.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);

            // Connect everything to dry output and the persistent delay loop
            osc1.connect(gain1);
            gain1.connect(this.musicGain);
            if (this.musicDelay) gain1.connect(this.musicDelay);

            osc2.connect(gain2);
            gain2.connect(this.musicGain);
            if (this.musicDelay) gain2.connect(this.musicDelay);

            osc3.connect(gain3);
            gain3.connect(this.musicGain);
            if (this.musicDelay) gain3.connect(this.musicDelay);

            // Start/Stop scheduling
            const now = ctx.currentTime;
            osc1.start(now);
            osc1.stop(now + 5.5);

            osc2.start(now);
            osc2.stop(now + 1.2);

            osc3.start(now);
            osc3.stop(now + 0.6);
        };

        // Play a chime note every 4-10 seconds for a highly spacious, relaxed feel
        const scheduleNext = () => {
            if (!this.isRunning) return;
            playChimeNote();
            const nextDelay = 4000 + Math.random() * 6000;
            this.musicInterval = setTimeout(scheduleNext, nextDelay);
        };
        scheduleNext();
    }

    // ===== UI SOUND LAYER =====

    /** Attach UI interaction sounds to buttons and inputs */
    private attachUISounds() {
        // Click sound on any button press
        document.addEventListener('click', (e) => {
            const target = e.target;
            if (target instanceof HTMLElement && (target.tagName === 'BUTTON' || target.closest('button') || target.tagName === 'INPUT')) {
                this.playClick();
            }
        });

        // Subtle hover sound on buttons
        document.addEventListener('mouseenter', (e) => {
            const target = e.target;
            if (target instanceof HTMLElement && (target.tagName === 'BUTTON' || target.closest('.nav-item') || target.closest('.sub-item'))) {
                this.playHover();
            }
        }, { passive: true });

        // Keyboard press feedback
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                this.playClick();
            }
        });
    }

    /** UI click — gentle windchime ping (replaces harsh frequency sweep) */
    public playClick() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        // Random pentatonic note for variety — sounds like windchimes
        const chimeNotes = [523.25, 587.33, 659.26, 783.99, 880.00, 1046.50];
        const freq = chimeNotes[Math.floor(Math.random() * chimeNotes.length)];

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.value = freq;
        osc.frequency.value *= (0.998 + Math.random() * 0.004); // Slight detune

        // Soft attack, gentle decay — windchime character
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.15, ctx.currentTime + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);

        // Low-pass for distance/dreaminess
        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 2200;
        filter.Q.value = 0.5;

        // Short reverb tail via delay
        const delay = ctx.createDelay(0.5);
        delay.delayTime.value = 0.12;
        const delayGain = ctx.createGain();
        delayGain.gain.value = 0.2;

        osc.connect(gain);
        gain.connect(filter);
        filter.connect(this.uiGain);
        filter.connect(delay);
        delay.connect(delayGain);
        delayGain.connect(this.uiGain);

        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.7);

        osc.onended = () => {
            try { delay.disconnect(); } catch (_) {}
            try { delayGain.disconnect(); } catch (_) {}
            try { filter.disconnect(); } catch (_) {}
        };
    }

    /** UI hover — very soft distant chime whisper */
    public playHover() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        const chimeNotes = [659.26, 783.99, 880.00];
        const freq = chimeNotes[Math.floor(Math.random() * chimeNotes.length)];

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.value = freq;

        // Very soft — just a whisper of a chime
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.04, ctx.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);

        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 1800;

        osc.connect(gain);
        gain.connect(filter);
        filter.connect(this.uiGain);

        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.45);
    }

    /** Tab transition — ascending chime */
    public playTransition() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        const notes = [523.25, 659.26, 783.99]; // C5, E5, G5
        notes.forEach((freq, i) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const delay = i * 0.06;

            osc.type = 'sine';
            osc.frequency.value = freq;

            gain.gain.setValueAtTime(0, ctx.currentTime + delay);
            gain.gain.linearRampToValueAtTime(0.15, ctx.currentTime + delay + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.3);

            osc.connect(gain);
            if (this.uiGain) {
                gain.connect(this.uiGain);
            }
            osc.start(ctx.currentTime + delay);
            osc.stop(ctx.currentTime + delay + 0.35);
        });
    }

    /** Message received — soft notification tone */
    public playMessageReceived() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(660, ctx.currentTime + 0.1);

        gain.gain.setValueAtTime(0.12, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2);

        osc.connect(gain);
        gain.connect(this.uiGain);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.25);
    }

    /** Message sent — subtle outgoing whoosh */
    public playMessageSent() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        // White noise burst filtered through bandpass
        const bufferSize = ctx.sampleRate * 0.15;
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);
        }

        const source = ctx.createBufferSource();
        source.buffer = buffer;

        const filter = ctx.createBiquadFilter();
        filter.type = 'bandpass';
        filter.frequency.value = 2000;
        filter.Q.value = 2;

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);

        source.connect(filter);
        filter.connect(gain);
        gain.connect(this.uiGain);
        source.start(0);
    }

    // ===== ECHO LAYER =====

    /** Play a distant, filtered echo of Jen's voice — called after TTS finishes */
    public playJenEcho(text: string) {
        const ctx = this.ensureContext();
        if (!this.echoGain) return;

        // Create a haunting echo effect using oscillators that mimic speech rhythm
        const words = text.split(/\s+/).slice(0, 4); // Just first few words
        const baseFreq = 220;

        words.forEach((word, i) => {
            const delay = 0.5 + i * 0.6; // Staggered timing
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const filter = ctx.createBiquadFilter();

            osc.type = 'sine';
            // Vary frequency slightly per word for speech-like rhythm
            osc.frequency.value = baseFreq + (word.length * 10) + Math.random() * 30;

            filter.type = 'bandpass';
            filter.frequency.value = 600 + Math.random() * 200;
            filter.Q.value = 5;

            gain.gain.setValueAtTime(0, ctx.currentTime + delay);
            gain.gain.linearRampToValueAtTime(0.15, ctx.currentTime + delay + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 1.5);

            osc.connect(filter);
            filter.connect(gain);
            gain.connect(this.echoGain!);
            osc.start(ctx.currentTime + delay);
            osc.stop(ctx.currentTime + delay + 1.6);
        });
    }

    // ===== CHIME — distant, reverberated arrival / thought sound =====

    /** Play a distant, reverberated chime — used on boot and before inner monologue */
    public playChime() {
        const ctx = this.ensureContext();
        if (!this.ambientGain) return;

        // Single soft bell tone — gentle, ethereal, distant
        // One note only to avoid "honk" perception from stacked triad
        const chimeFreq = 523.25 + Math.random() * 200; // C5–A5, random each time

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.value = chimeFreq;
        osc.frequency.value *= (0.997 + Math.random() * 0.006);

        // Very soft attack, long ethereal decay — whisper, not honk
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.025, ctx.currentTime + 0.1);  // Much quieter
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 5); // Longer tail

        // Heavy low-pass — distance effect, removes harshness
        const distanceFilter = ctx.createBiquadFilter();
        distanceFilter.type = 'lowpass';
        distanceFilter.frequency.value = 1200;  // Lower cutoff = softer
        distanceFilter.Q.value = 0.3;

        // Single subtle reverb reflection
        const delay1 = ctx.createDelay(1.0);
        delay1.delayTime.value = 0.25;
        const delayGain1 = ctx.createGain();
        delayGain1.gain.value = 0.1;  // Very subtle

        osc.connect(gain);
        gain.connect(distanceFilter);
        distanceFilter.connect(this.ambientGain!);
        distanceFilter.connect(delay1);
        delay1.connect(delayGain1);
        delayGain1.connect(this.ambientGain!);

        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 5.5);

        osc.onended = () => {
            try { delay1.disconnect(); } catch (_) {}
            try { delayGain1.disconnect(); } catch (_) {}
            try { distanceFilter.disconnect(); } catch (_) {}
        };
    }

    // ===== VOLUME CONTROLS =====

    public setAmbientVolume(v: number) {
        this.ambientVolume = v;
        if (this.ambientGain) this.ambientGain.gain.value = v;
    }

    public setUIVolume(v: number) {
        this.uiVolume = v;
        if (this.uiGain) this.uiGain.gain.value = v;
    }

    public setMusicVolume(v: number) {
        this.musicVolume = v;
        if (this.musicGain) this.musicGain.gain.value = v;
    }

    public setEchoVolume(v: number) {
        this.echoVolume = v;
        if (this.echoGain) this.echoGain.gain.value = v;
    }

    public setMasterMute(mute: boolean) {
        if (this.masterGain) {
            this.masterGain.gain.value = mute ? 0 : 1;
        }
    }
}

export const ambientSoundEngine = new AmbientSoundEngine();