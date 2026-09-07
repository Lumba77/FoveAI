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
class AmbientSoundEngine {
    constructor() {
        this.ctx = null;
        this.masterGain = null;
        this.ambientGain = null;
        this.uiGain = null;
        this.musicGain = null;
        this.echoGain = null;
        this.musicDelay = null;
        this.musicFeedback = null;
        this._fadeGain = null;

        this.activeAmbients = new Map();
        this.musicInterval = null;
        this.isRunning = false;

        // Heartbeat references for modulation
        this.heartbeatFundamental = null;
        this.heartbeatHarmonics = [];
        this.heartbeatGains = [];

        // Volume levels (0-1)
        this.ambientVolume = 0.067;
        this.uiVolume = 0.084;
        this.musicVolume = 0.028;
        this.echoVolume = 0.042;

        this._backendAlive = true;
        this._backendFailCount = 0;
        this._backendCheckInterval = null;
        this._delegatedToTopBar = false;

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

        // Backend health check — fade out audio if server dies
        this._backendCheckInterval = setInterval(async () => {
            let topBarAlive = false;
            try {
                // Check local TopBar (if running, it handles background audio)
                const tbResp = await fetch('http://127.0.0.1:19847/status', { signal: AbortSignal.timeout(1500) });
                if (tbResp.ok) {
                    const tbData = await tbResp.json();
                    topBarAlive = true;
                    this._backendAlive = tbData.alive !== false;
                    return;
                }
            } catch (_) {}

            if (!topBarAlive && this._delegatedToTopBar) {
                console.log('[Ambient] TopBar lost — taking back background audio');
                this._delegatedToTopBar = false;
                if (!this.isRunning) {
                    this.start();
                }
            }

            try {
                // Check Soul backend directly via relative path
                const resp = await fetch('/api/health-proxy/8000', { signal: AbortSignal.timeout(2000) });
                const data = await resp.json();
                if (data.ok) {
                    this._backendAlive = true;
                    this._backendFailCount = 0;
                } else {
                    this._backendFailCount++;
                }
            } catch (_) {
                this._backendFailCount++;
            }

            if (this._backendFailCount >= 3) {
                this._backendAlive = false;
            }

            if (!this._backendAlive && this._fadeGain && this.ctx) {
                this._fadeGain.gain.setValueAtTime(this._fadeGain.gain.value, this.ctx.currentTime);
                this._fadeGain.gain.linearRampToValueAtTime(0, this.ctx.currentTime + 5);
            } else if (this._backendAlive && this._fadeGain && this.ctx && this.isRunning) {
                this._fadeGain.gain.setValueAtTime(this._fadeGain.gain.value, this.ctx.currentTime);
                this._fadeGain.gain.linearRampToValueAtTime(1, this.ctx.currentTime + 5);
            }
        }, 4000);

        // Listen for avatar emotion changes to morph the soundscape's harmonic heartbeat
        window.addEventListener('avatar-emotion-changed', (e) => {
            if (e.detail && e.detail.emotion) {
                this.setEmotionalChord(e.detail.emotion);
            }
        });
    }

    ensureContext() {
        if (!this.ctx) {
            let activeCtx = window.foveaiAudioContext;
            if (!activeCtx) {
                activeCtx = new (window.AudioContext || window.webkitAudioContext)();
                window.foveaiAudioContext = activeCtx;
            }
            this.ctx = activeCtx;

            const ctx = activeCtx;
            const masterGain = ctx.createGain();
            masterGain.gain.value = 1.0;
            masterGain.connect(ctx.destination);
            this.masterGain = masterGain;

            const _fadeGain = ctx.createGain();
            _fadeGain.gain.value = 0;
            _fadeGain.connect(masterGain);
            this._fadeGain = _fadeGain;

            const ambientGain = ctx.createGain();
            ambientGain.gain.value = this.ambientVolume;
            ambientGain.connect(_fadeGain);
            this.ambientGain = ambientGain;

            const uiGain = ctx.createGain();
            uiGain.gain.value = this.uiVolume;
            uiGain.connect(masterGain);
            this.uiGain = uiGain;

            const musicGain = ctx.createGain();
            musicGain.gain.value = this.musicVolume;
            musicGain.connect(_fadeGain);
            this.musicGain = musicGain;

            const musicDelay = ctx.createDelay(2.0);
            musicDelay.delayTime.value = 0.6;
            const musicFeedback = ctx.createGain();
            musicFeedback.gain.value = 0.45;

            musicDelay.connect(musicFeedback);
            musicFeedback.connect(musicDelay);
            musicDelay.connect(musicGain);
            this.musicDelay = musicDelay;
            this.musicFeedback = musicFeedback;

            const echoGain = ctx.createGain();
            echoGain.gain.value = this.echoVolume;
            echoGain.connect(_fadeGain);
            this.echoGain = echoGain;
        }
        if (this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
        return this.ctx;
    }

    startUISoundsOnly() {
        this.ensureContext();
        this.attachUISounds();
        console.log('[Ambient] UI sounds only (background delegated to TopBar)');
    }

    start() {
        if (this.isRunning) return;
        this.isRunning = true;
        this.ensureContext();

        this._fadeGain.gain.setValueAtTime(this._fadeGain.gain.value, this.ctx.currentTime);
        this._fadeGain.gain.linearRampToValueAtTime(1, this.ctx.currentTime + 5);

        this.startWindAmbient();
        this.startDeepHum();
        this.startGenerativeMusic();
        this.startHarmonicHeartbeat();
        this.attachUISounds();
        console.log('[Ambient] Sound engine started (5s fade-in)');
    }

    stop() {
        this.isRunning = false;
        const ctx = this.ctx;
        if (ctx && this._fadeGain) {
            this._fadeGain.gain.setValueAtTime(this._fadeGain.gain.value, ctx.currentTime);
            this._fadeGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 5);
            setTimeout(() => {
                for (const [name, layer] of this.activeAmbients) {
                    for (const src of layer.sources) {
                        try { src.stop(); } catch (_) {}
                    }
                }
                this.activeAmbients.clear();
            }, 5500);
        } else {
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

    startHarmonicHeartbeat() {
        const ctx = this.ensureContext();
        if (this.heartbeatFundamental) return;

        const masterGain = ctx.createGain();
        masterGain.gain.value = 0.08; // slightly louder for richer chords

        // Add a warm lowpass filter so triangle waves sound like a lush pad
        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 600; // roll off harsh highs
        filter.connect(masterGain);
        masterGain.connect(this.ambientGain);

        this.heartbeatFundamental = ctx.createOscillator();
        this.heartbeatFundamental.type = 'sine'; // keep fundamental deep and pure
        this.heartbeatFundamental.frequency.value = 110;

        const fundGain = ctx.createGain();
        fundGain.gain.value = 0.5;
        this.heartbeatFundamental.connect(fundGain);
        fundGain.connect(filter);
        this.heartbeatFundamental.start();

        for (let i = 0; i < 4; i++) {
            const osc = ctx.createOscillator();
            osc.type = 'triangle'; // triangle gives beautiful warm overtones for chords
            osc.frequency.value = 110;
            const gain = ctx.createGain();
            gain.gain.value = 0;
            osc.connect(gain);
            gain.connect(filter);
            osc.start();
            this.heartbeatHarmonics.push(osc);
            this.heartbeatGains.push(gain);
        }

        this.activeAmbients.set('heartbeat', {
            sources: [this.heartbeatFundamental, ...this.heartbeatHarmonics],
            gains: [fundGain, ...this.heartbeatGains, masterGain]
        });

        this.setEmotionalChord('neutral');
    }

    setEmotionalChord(emotion) {
        if (!this.heartbeatFundamental) return;
        const ctx = this.ensureContext();
        const now = ctx.currentTime;
        const transitionTime = 6.0;

        // Expanded ratios for beautiful, rich pad chords spread across octaves
        let targetChord = [1.498]; // Default: pure fifth

        switch(String(emotion || '').toLowerCase()) {
            case 'neutral': 
                // A minor 9 (A, C, E, B) spread out: root=1.0, minor 3rd up an octave=2.378, perfect 5th=1.498, major 9th=2.245
                targetChord = [1.498, 2.0, 2.378, 2.245]; break;
            case 'calm': 
                // A major add9 (lush, peaceful)
                targetChord = [1.498, 2.0, 2.520, 2.245]; break;
            case 'happy': 
                // A major 7 (bright, uplifted)
                targetChord = [1.260, 1.498, 1.888, 2.520]; break;
            case 'curious': 
                // Lydian chord (A major with #11)
                targetChord = [1.498, 2.0, 2.828, 2.520]; break;
            case 'sad':
            case 'concerned': 
                // A minor (darker, close harmony)
                targetChord = [1.189, 1.498, 2.0, 2.378]; break;
            case 'excited': 
                // Suspended 4th moving to 5th (A, D, E, A)
                targetChord = [1.333, 1.498, 2.0, 2.666]; break;
            case 'alert':
            case 'angry': 
                // Diminished / dissonant
                targetChord = [1.414, 1.189, 2.828, 2.378]; break;
            default: 
                targetChord = [1.498, 2.0, 2.378, 2.245]; break;
        }

        for (let i = 0; i < 4; i++) {
            const osc = this.heartbeatHarmonics[i];
            const gain = this.heartbeatGains[i];

            if (i < targetChord.length) {
                osc.frequency.setTargetAtTime(110 * targetChord[i], now, transitionTime / 3);
                gain.gain.setTargetAtTime(0.2 / targetChord.length, now, transitionTime / 3);
            } else {
                gain.gain.setTargetAtTime(0.0001, now, transitionTime / 3);
            }
        }
    }

    startWindAmbient() {
        const ctx = this.ensureContext();
        const bufferSize = 10 * ctx.sampleRate;
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);

        let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
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

        const fadeLen = Math.floor(0.5 * ctx.sampleRate);
        for (let i = 0; i < fadeLen; i++) {
            const t = i / fadeLen;
            const endIdx = bufferSize - fadeLen + i;
            data[i] = data[i] * t + data[endIdx] * (1 - t);
        }

        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.loop = true;

        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 400;
        filter.Q.value = 0.5;

        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.type = 'sine';
        lfo.frequency.value = 0.08;
        lfoGain.gain.value = 200;
        lfo.connect(lfoGain);
        lfoGain.connect(filter.frequency);

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(1, ctx.currentTime + 3);

        source.connect(filter);
        filter.connect(gain);
        gain.connect(this.ambientGain);

        source.start(0);
        lfo.start(0);

        this.activeAmbients.set('wind', { sources: [source, lfo], gains: [gain] });
    }

    startDeepHum() {
        const ctx = this.ensureContext();

        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = 55;

        const osc2 = ctx.createOscillator();
        osc2.type = 'sine';
        osc2.frequency.value = 82.5;

        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.type = 'sine';
        lfo.frequency.value = 0.03;
        lfoGain.gain.value = 0.5;
        lfo.connect(lfoGain);
        lfoGain.connect(osc.frequency);
        lfoGain.connect(osc2.frequency);

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.255, ctx.currentTime + 5);

        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 120;
        filter.Q.value = 1;

        osc.connect(filter);
        osc2.connect(filter);
        filter.connect(gain);
        gain.connect(this.ambientGain);

        osc.start(0);
        osc2.start(0);
        lfo.start(0);

        this.activeAmbients.set('hum', { sources: [osc, osc2, lfo], gains: [gain] });
    }

    startGenerativeMusic() {
        const ctx = this.ensureContext();

        const scale = [
            523.25, 587.33, 659.26, 783.99, 880.00,
            1046.50, 1174.66, 1318.51, 1567.98, 1760.00,
            2093.00
        ];

        const playChimeNote = () => {
            if (!this.isRunning || !this.musicGain) return;

            const freq = scale[Math.floor(Math.random() * scale.length)];

            const osc1 = ctx.createOscillator();
            const gain1 = ctx.createGain();

            const osc2 = ctx.createOscillator();
            const gain2 = ctx.createGain();

            const osc3 = ctx.createOscillator();
            const gain3 = ctx.createGain();

            osc1.type = 'sine';
            osc1.frequency.value = freq * (0.998 + Math.random() * 0.004);

            osc2.type = 'sine';
            osc2.frequency.value = freq * 2.76 * (0.997 + Math.random() * 0.006);

            osc3.type = 'sine';
            osc3.frequency.value = freq * 5.40 * (0.996 + Math.random() * 0.008);

            const baseVol = 0.04 + Math.random() * 0.05;

            gain1.gain.setValueAtTime(0, ctx.currentTime);
            gain1.gain.linearRampToValueAtTime(baseVol, ctx.currentTime + 0.05);
            gain1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 5.0);

            gain2.gain.setValueAtTime(0, ctx.currentTime);
            gain2.gain.linearRampToValueAtTime(baseVol * 0.35, ctx.currentTime + 0.015);
            gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);

            gain3.gain.setValueAtTime(0, ctx.currentTime);
            gain3.gain.linearRampToValueAtTime(baseVol * 0.15, ctx.currentTime + 0.01);
            gain3.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);

            osc1.connect(gain1);
            gain1.connect(this.musicGain);
            if (this.musicDelay) gain1.connect(this.musicDelay);

            osc2.connect(gain2);
            gain2.connect(this.musicGain);
            if (this.musicDelay) gain2.connect(this.musicDelay);

            osc3.connect(gain3);
            gain3.connect(this.musicGain);
            if (this.musicDelay) gain3.connect(this.musicDelay);

            const now = ctx.currentTime;
            osc1.start(now);
            osc1.stop(now + 5.5);

            osc2.start(now);
            osc2.stop(now + 1.2);

            osc3.start(now);
            osc3.stop(now + 0.6);
        };

        const scheduleNext = () => {
            if (!this.isRunning) return;
            playChimeNote();
            const nextDelay = 4000 + Math.random() * 6000;
            this.musicInterval = setTimeout(scheduleNext, nextDelay);
        };
        scheduleNext();
    }

    attachUISounds() {
        document.addEventListener('click', (e) => {
            const target = e.target;
            if (target instanceof HTMLElement && (target.tagName === 'BUTTON' || target.closest('button') || target.tagName === 'INPUT')) {
                this.playClick();
            }
        });

        document.addEventListener('mouseenter', (e) => {
            const target = e.target;
            if (target instanceof HTMLElement && (target.tagName === 'BUTTON' || target.closest('.nav-item') || target.closest('.sub-item'))) {
                this.playHover();
            }
        }, { passive: true });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                this.playClick();
            }
        });
    }

    playClick() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        const chimeNotes = [523.25, 587.33, 659.26, 783.99, 880.00, 1046.50];
        const freq = chimeNotes[Math.floor(Math.random() * chimeNotes.length)];

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.value = freq;
        osc.frequency.value *= (0.998 + Math.random() * 0.004);

        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.15, ctx.currentTime + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);

        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 2200;
        filter.Q.value = 0.5;

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

    playHover() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        const chimeNotes = [659.26, 783.99, 880.00];
        const freq = chimeNotes[Math.floor(Math.random() * chimeNotes.length)];

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.value = freq;

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

    playTransition() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

        const notes = [523.25, 659.26, 783.99];
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

    playMessageReceived() {
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

    playMessageSent() {
        const ctx = this.ensureContext();
        if (!this.uiGain) return;

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

    playJenEcho(text) {
        const ctx = this.ensureContext();
        if (!this.echoGain) return;

        const words = String(text || '').split(/\s+/).slice(0, 4);
        const baseFreq = 220;

        words.forEach((word, i) => {
            const delay = 0.5 + i * 0.6;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const filter = ctx.createBiquadFilter();

            osc.type = 'sine';
            osc.frequency.value = baseFreq + (word.length * 10) + Math.random() * 30;

            filter.type = 'bandpass';
            filter.frequency.value = 600 + Math.random() * 200;
            filter.Q.value = 5;

            gain.gain.setValueAtTime(0, ctx.currentTime + delay);
            gain.gain.linearRampToValueAtTime(0.15, ctx.currentTime + delay + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 1.5);

            osc.connect(filter);
            filter.connect(gain);
            gain.connect(this.echoGain);
            osc.start(ctx.currentTime + delay);
            osc.stop(ctx.currentTime + delay + 1.6);
        });
    }

    playChime() {
        const ctx = this.ensureContext();
        if (!this.ambientGain) return;

        const chimeFreq = 523.25 + Math.random() * 200;

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.value = chimeFreq;
        osc.frequency.value *= (0.997 + Math.random() * 0.006);

        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.025, ctx.currentTime + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 5);

        const distanceFilter = ctx.createBiquadFilter();
        distanceFilter.type = 'lowpass';
        distanceFilter.frequency.value = 1200;
        distanceFilter.Q.value = 0.3;

        const delay1 = ctx.createDelay(1.0);
        delay1.delayTime.value = 0.25;
        const delayGain1 = ctx.createGain();
        delayGain1.gain.value = 0.1;

        osc.connect(gain);
        gain.connect(distanceFilter);
        distanceFilter.connect(this.ambientGain);
        distanceFilter.connect(delay1);
        delay1.connect(delayGain1);
        delayGain1.connect(this.ambientGain);

        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 5.5);

        osc.onended = () => {
            try { delay1.disconnect(); } catch (_) {}
            try { delayGain1.disconnect(); } catch (_) {}
            try { distanceFilter.disconnect(); } catch (_) {}
        };
    }

    setAmbientVolume(v) {
        this.ambientVolume = v;
        if (this.ambientGain) this.ambientGain.gain.value = v;
    }

    setUIVolume(v) {
        this.uiVolume = v;
        if (this.uiGain) this.uiGain.gain.value = v;
    }

    setMusicVolume(v) {
        this.musicVolume = v;
        if (this.musicGain) this.musicGain.gain.value = v;
    }

    setEchoVolume(v) {
        this.echoVolume = v;
        if (this.echoGain) this.echoGain.gain.value = v;
    }

    setMasterMute(mute) {
        if (this.masterGain) {
            this.masterGain.gain.value = mute ? 0 : 1;
        }
    }
}

window.NEXUS_AMBIENT_SOUND_ENGINE = new AmbientSoundEngine();
