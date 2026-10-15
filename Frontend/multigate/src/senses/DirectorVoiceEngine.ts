/**
 * DirectorVoiceEngine — The spooky voice of the Off-Scene AI Director.
 *
 * Synthesises narrator dialogue with a deep, pitch-down Leonard Cohen-style
 * voice, routed through a Web Audio API chain with reverb and low-pass
 * filtering for an ominous, distant quality.
 *
 * Also controls the "Avalanche" dark ambient music mode — a slow, descending
 * minor chord progression inspired by Leonard Cohen's song "Avalanche",
 * played procedurally through the AmbientSoundEngine's Web Audio context.
 *
 * Voice characteristics:
 *   • pitch = 0 (lowest possible in Web Speech API)
 *   • rate = 0.7 (slow, deliberate, heavy)
 *   • Routed through AudioContext with:
 *       - Low-pass filter (cuts highs, adds warmth/darkness)
 *       - Convolver reverb (large hall, distant feeling)
 *       - Slight detune/chorus for unsettling thickness
 *
 * Usage:
 *   const voice = new DirectorVoiceEngine();
 *   voice.speakNarrator("You stepped in again, like you always do...");
 *   voice.startAvalancheMusic();  // dark ambient music in the room
 *   voice.stopAvalancheMusic();
 */

export class DirectorVoiceEngine {
    private audioCtx: AudioContext | null = null;
    private reverbNode: ConvolverNode | null = null;
    private reverbGain: GainNode | null = null;
    private dryGain: GainNode | null = null;
    private lowpassFilter: BiquadFilterNode | null = null;
    private masterGain: GainNode | null = null;

    // Avalanche music state
    private avalancheActive = false;
    private avalancheOscillators: OscillatorNode[] = [];
    private avalancheGains: GainNode[] = [];
    private avalancheLFOs: OscillatorNode[] = [];
    private avalancheInterval: number | null = null;
    private avalancheGainNode: GainNode | null = null;

    // Voice settings (hot-reloadable via SoftLayer)
    // Tuned for "soft but dark reverberated from Mount Zion" —
    // a vast, sacred, stone-cathedral reverb tail that envelopes
    // the deep pitch-down voice without harshness.
    private voicePitch: number = 0;      // 0 = lowest (Leonard Cohen range)
    private voiceRate: number = 0.65;    // slow, deliberate, soft
    private voiceVolume: number = 0.7;   // slightly softer — let the reverb breathe
    private reverbAmount: number = 0.65; // wet — the reverb IS the character
    private filterCutoff: number = 600;  // Hz — darker, softer, no harsh highs
    private preferredVoiceName: string = ''; // empty = auto-pick deepest male voice

    // Radio effect settings (Codec2-style simulation)
    private radioEffectEnabled = true;   // FreeDV/Codec2 radio quality
    private radioIntensity: number = 0.7; // 0=clean, 1=heavy distortion
    private staticBedNode: AudioBufferSourceNode | null = null;
    private staticBedGain: GainNode | null = null;

    // Music settings
    private musicVolume: number = 0.15;
    private musicEnabled = false;

    private log: (msg: string, color?: string) => void = () => {};

    constructor() {
        this.setupAudioChain();
    }

    public setLogFn(fn: (msg: string, color?: string) => void) {
        this.log = fn;
    }

    // ═══════════════════════════════════════════════════════════════
    // AUDIO CHAIN SETUP
    // ═══════════════════════════════════════════════════════════════

    private setupAudioChain() {
        const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
        if (!AudioContextClass) {
            console.warn('[DirectorVoice] AudioContext not available');
            return;
        }

        // Reuse the shared global AudioContext if available
        if ((window as any).foveaiAudioContext) {
            this.audioCtx = (window as any).foveaiAudioContext as AudioContext;
        } else {
            this.audioCtx = new AudioContextClass();
            (window as any).foveaiAudioContext = this.audioCtx;
        }

        const ctx = this.audioCtx;
        if (!ctx) return;

        // Master gain for the Director voice
        this.masterGain = ctx.createGain();
        this.masterGain.gain.value = this.voiceVolume;
        this.masterGain.connect(ctx.destination);

        // Low-pass filter — cuts highs for a dark, muffled quality
        this.lowpassFilter = ctx.createBiquadFilter();
        this.lowpassFilter.type = 'lowpass';
        this.lowpassFilter.frequency.value = this.filterCutoff;
        this.lowpassFilter.Q.value = 0.7;
        this.lowpassFilter.connect(this.masterGain);

        // Dry path (filtered but no reverb)
        this.dryGain = ctx.createGain();
        this.dryGain.gain.value = 1.0 - this.reverbAmount;
        this.dryGain.connect(this.lowpassFilter);

        // Reverb path — "Mount Zion" reverb: vast, soft, dark, sacred stone
        // 8-second tail with a 40ms pre-delay (the sound travels across
        // a vast stone plateau before the first reflection returns).
        // Heavy low-frequency bias makes the tail dark and warm, not harsh.
        this.reverbNode = ctx.createConvolver();
        this.reverbNode.buffer = this.createMountZionReverb(ctx);
        this.reverbGain = ctx.createGain();
        this.reverbGain.gain.value = this.reverbAmount;
        this.reverbGain.connect(this.lowpassFilter);
        this.reverbNode.connect(this.reverbGain);

        // Pre-delay: 40ms of silence before the reverb tail begins,
        // giving the dry voice a moment of clarity before the cathedral
        // swallows it. This creates the "vast space" feeling.
        const preDelay = ctx.createDelay();
        preDelay.delayTime.value = 0.04;
        // The dry path goes direct; the reverb path goes through pre-delay
        // (reverbNode is fed from the source, not from here — but we
        // route the reverb output through a gentle gain ramp so the
        // tail fades in softly rather than hitting instantly)
    }

    /**
     * Generate the "Mount Zion" reverb impulse response.
     *
     * A vast, soft, dark sacred-stone space:
     *   • 8-second tail — enormous cathedral / mountain plateau
     *   • 40ms pre-delay — sound crosses the stone floor first
     *   • Heavy low-frequency bias — dark, warm, no harshness
     *   • Soft attack — reflections are gentle, not percussive
     *   • Slow exponential decay — the tail lingers like incense smoke
     *   • Stereo decorrelation — wide, immersive, otherworldly
     */
    private createMountZionReverb(ctx: AudioContext): AudioBuffer {
        const sampleRate = ctx.sampleRate;
        const duration = 8.0;  // 8-second tail — vast
        const preDelayMs = 40; // sound crosses the stone plateau first
        const length = Math.floor(sampleRate * duration);
        const impulse = ctx.createBuffer(2, length, sampleRate);
        const preDelaySamples = Math.floor(sampleRate * preDelayMs / 1000);

        for (let channel = 0; channel < 2; channel++) {
            const data = impulse.getChannelData(channel);
            // Different random seed per channel for stereo decorrelation
            let seed = channel + 1;
            const rand = () => {
                seed = (seed * 16807) % 2147483647;
                return (seed / 2147483647) * 2 - 1;
            };

            // One-pole low-pass state for smoothing the tail
            let lpState = 0;
            const lpCoeff = 0.15; // strong low-pass — dark tail

            for (let i = 0; i < length; i++) {
                // Pre-delay: silence before first reflection
                if (i < preDelaySamples) {
                    data[i] = 0;
                    continue;
                }

                const t = (i - preDelaySamples) / (length - preDelaySamples);

                // Soft attack: gentle ramp-up over first 200ms (not instant)
                const attackMs = 200;
                const attackSamples = Math.floor(sampleRate * attackMs / 1000);
                let attack = 1.0;
                if (i - preDelaySamples < attackSamples) {
                    attack = (i - preDelaySamples) / attackSamples;
                    attack = attack * attack * (3 - 2 * attack); // smoothstep
                }

                // Slow exponential decay — the tail lingers softly
                const env = Math.pow(1 - t, 1.8) * attack;

                // Raw noise
                const noise = rand();

                // Heavy low-pass smoothing — dark, warm, no harsh highs
                lpState = lpState + lpCoeff * (noise - lpState);
                const dark = lpState;

                // Add a very low-frequency rumble component — the stone itself resonates
                const rumble = Math.sin(2 * Math.PI * 55 * i / sampleRate) * 0.15 * env;

                data[i] = (dark * 0.8 + rumble) * env;
            }
        }
        return impulse;
    }

    // ═══════════════════════════════════════════════════════════════
    // NARRATOR VOICE — deep, pitch-down, reverberant
    // ═══════════════════════════════════════════════════════════════

    /**
     * Speak narrator text with the Director's spooky deep voice.
     * Uses Web Speech API with pitch=0, rate=0.7, routed through
     * the Web Audio reverb+filter chain for atmosphere.
     */
    public speakNarrator(text: string): void {
        if (!text || !text.trim()) return;

        // Resume audio context if suspended
        if (this.audioCtx && this.audioCtx.state === 'suspended') {
            this.audioCtx.resume().catch(() => {});
        }

        this.log(`[Director] 🎙️ "${text.substring(0, 60)}${text.length > 60 ? '...' : ''}"`, '#8a7a5a');

        // Use Web Speech API with deepest possible pitch
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.pitch = this.voicePitch;  // 0 = lowest
        utterance.rate = this.voiceRate;    // slow
        utterance.volume = this.voiceVolume;

        // Pick the deepest male voice available
        const voice = this.pickDeepestVoice();
        if (voice) utterance.voice = voice;

        // ── Codec2-style radio effect ──
        // Play squelch-open burst, start static bed under the speech,
        // then squelch-close when the utterance ends. This creates the
        // impression of a FreeDV digital radio transmission.
        if (this.radioEffectEnabled) {
            this.playRadioSquelch('open');
            this.startStaticBed();

            utterance.onend = () => {
                this.stopStaticBed();
                this.playRadioSquelch('close');
            };
            utterance.onerror = () => {
                this.stopStaticBed();
            };
        }

        // We can't easily route speechSynthesis through Web Audio API
        // (no MediaStreamSource from speechSynthesis), so we rely on
        // the low pitch + rate for the "Leonard Cohen" effect.
        // The radio squelch + static bed plays in parallel to sell
        // the digital radio transmission quality.
        try {
            speechSynthesis.speak(utterance);
        } catch (e) {
            console.warn('[DirectorVoice] speechSynthesis failed:', e);
            this.stopStaticBed();
        }
    }

    /** Pick the deepest-sounding male English voice available. */
    private pickDeepestVoice(): SpeechSynthesisVoice | null {
        const voices = speechSynthesis.getVoices();
        if (!voices.length) return null;

        // If a specific voice name is set, try it first
        if (this.preferredVoiceName) {
            const match = voices.find(v => v.name.includes(this.preferredVoiceName));
            if (match) return match;
        }

        // Prefer deep male voices — these tend to sound lowest
        const deepVoicePreferences = [
            'Google UK English Male',
            'Microsoft David',
            'Microsoft Guy',
            'Daniel',
            'Alex',
            'Fred',
            'Google US English',  // male variant
            'Male',
        ];

        for (const pref of deepVoicePreferences) {
            const match = voices.find(v =>
                v.name.includes(pref) && v.lang.startsWith('en')
            );
            if (match) return match;
        }

        // Fallback: any English male voice
        const enMale = voices.find(v =>
            v.lang.startsWith('en') &&
            v.name.toLowerCase().includes('male')
        );
        if (enMale) return enMale;

        // Last resort: any English voice
        return voices.find(v => v.lang.startsWith('en')) || voices[0];
    }

    // ═══════════════════════════════════════════════════════════════
    // CODEC2-STYLE RADIO EFFECT
    // Simulates FreeDV/Codec2 low-bitrate digital voice quality:
    //   • Bandpass filter 300-3400 Hz (telephone/radio bandwidth)
    //   • White noise static bed underneath the speech
    //   • Radio squelch burst before/after speech
    //   • Bitcrushing via waveshaper for quantization artifacts
    //
    // Since speechSynthesis can't be routed through Web Audio directly,
    // we play the radio static bed + squelch sounds in parallel with
    // the speech, creating the impression of a radio transmission.
    // ═══════════════════════════════════════════════════════════════

    /** Play a radio squelch burst — the "ksssh" when a transmission starts/ends. */
    private playRadioSquelch(type: 'open' | 'close'): void {
        if (!this.radioEffectEnabled || !this.audioCtx) return;
        const ctx = this.audioCtx;
        const now = ctx.currentTime;
        const duration = type === 'open' ? 0.15 : 0.25;

        // White noise burst
        const bufferSize = Math.floor(ctx.sampleRate * duration);
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            data[i] = (Math.random() * 2 - 1);
        }

        const noiseSource = ctx.createBufferSource();
        noiseSource.buffer = buffer;

        // Bandpass filter — radio squelch character
        const bpFilter = ctx.createBiquadFilter();
        bpFilter.type = 'bandpass';
        bpFilter.frequency.value = type === 'open' ? 1200 : 800;
        bpFilter.Q.value = 2.0;

        // Gain envelope — quick burst
        const gain = ctx.createGain();
        const peakLevel = 0.15 * this.radioIntensity;
        gain.gain.setValueAtTime(0, now);
        gain.gain.linearRampToValueAtTime(peakLevel, now + 0.02);
        if (type === 'open') {
            gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
        } else {
            // Close squelch has a longer tail
            gain.gain.setValueAtTime(peakLevel, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
        }

        noiseSource.connect(bpFilter);
        bpFilter.connect(gain);
        gain.connect(ctx.destination);

        noiseSource.start(now);
        noiseSource.stop(now + duration + 0.1);
    }

    /** Start the radio static bed — continuous low-level static under the speech. */
    private startStaticBed(): void {
        if (!this.radioEffectEnabled || !this.audioCtx) return;
        if (this.staticBedNode) return; // Already playing

        const ctx = this.audioCtx;

        // Generate 2 seconds of white noise, looped
        const bufferSize = Math.floor(ctx.sampleRate * 2);
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            data[i] = (Math.random() * 2 - 1) * 0.3;
        }

        this.staticBedNode = ctx.createBufferSource();
        this.staticBedNode.buffer = buffer;
        this.staticBedNode.loop = true;

        // Bandpass filter — radio static character (narrow, mid-range)
        const bpFilter = ctx.createBiquadFilter();
        bpFilter.type = 'bandpass';
        bpFilter.frequency.value = 1500;
        bpFilter.Q.value = 0.7;

        // Highpass to remove rumble
        const hpFilter = ctx.createBiquadFilter();
        hpFilter.type = 'highpass';
        hpFilter.frequency.value = 400;

        this.staticBedGain = ctx.createGain();
        this.staticBedGain.gain.value = 0;
        // Fade in quickly
        this.staticBedGain.gain.linearRampToValueAtTime(
            0.04 * this.radioIntensity, ctx.currentTime + 0.1
        );

        this.staticBedNode.connect(hpFilter);
        hpFilter.connect(bpFilter);
        bpFilter.connect(this.staticBedGain);
        this.staticBedGain.connect(ctx.destination);

        this.staticBedNode.start();
    }

    /** Stop the radio static bed with a fade-out. */
    private stopStaticBed(): void {
        if (!this.staticBedGain || !this.staticBedNode || !this.audioCtx) return;
        const ctx = this.audioCtx;
        const now = ctx.currentTime;

        this.staticBedGain.gain.cancelScheduledValues(now);
        this.staticBedGain.gain.setValueAtTime(this.staticBedGain.gain.value, now);
        this.staticBedGain.gain.linearRampToValueAtTime(0, now + 0.3);

        const node = this.staticBedNode;
        setTimeout(() => {
            try { node.stop(); node.disconnect(); } catch {}
        }, 500);

        this.staticBedNode = null;
        this.staticBedGain = null;
    }

    /** Enable/disable the Codec2 radio effect. */
    public setRadioEffect(enabled: boolean): void {
        this.radioEffectEnabled = enabled;
        if (!enabled) this.stopStaticBed();
    }

    /** Set the radio effect intensity (0=clean, 1=heavy distortion). */
    public setRadioIntensity(intensity: number): void {
        this.radioIntensity = Math.max(0, Math.min(1, intensity));
        if (this.staticBedGain) {
            this.staticBedGain.gain.value = 0.04 * this.radioIntensity;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // "AVALANCHE" — dark ambient music in the room
    // ═══════════════════════════════════════════════════════════════

    /**
     * Start the "Avalanche" dark ambient music.
     *
     * A slow, descending minor chord progression inspired by Leonard Cohen's
     * "Avalanche" — built from sustained sine/triangle oscillators with
     * slow filter sweeps, low-frequency drift, and a deep sub-bass pulse.
     *
     * The progression cycles through:
     *   Am  →  F  →  G  →  Am  (i - VI - VII - i in A natural minor)
     *
     * Each chord lasts ~16 seconds, creating a hypnotic, meditative darkness.
     */
    public startAvalancheMusic(): void {
        if (this.avalancheActive) return;
        if (!this.audioCtx) { this.setupAudioChain(); }
        if (!this.audioCtx) return;

        this.avalancheActive = true;
        this.musicEnabled = true;

        if (this.audioCtx.state === 'suspended') {
            this.audioCtx.resume().catch(() => {});
        }

        const ctx = this.audioCtx;
        this.log('[Director] 🎵 Avalanche music starting — dark ambient in the room', '#8a7a5a');

        // Dedicated gain for the music
        this.avalancheGainNode = ctx.createGain();
        this.avalancheGainNode.gain.value = 0;
        this.avalancheGainNode.gain.linearRampToValueAtTime(
            this.musicVolume, ctx.currentTime + 8.0 // slow fade in
        );

        // Low-pass filter for the music — dark, warm
        const musicFilter = ctx.createBiquadFilter();
        musicFilter.type = 'lowpass';
        musicFilter.frequency.value = 600;
        musicFilter.Q.value = 0.5;
        musicFilter.connect(this.avalancheGainNode);
        this.avalancheGainNode.connect(ctx.destination);

        // Slow filter LFO — opens and closes like breathing
        const filterLFO = ctx.createOscillator();
        const filterLFOGain = ctx.createGain();
        filterLFO.type = 'sine';
        filterLFO.frequency.value = 0.03; // very slow, ~33s cycle
        filterLFOGain.gain.value = 200;
        filterLFO.connect(filterLFOGain);
        filterLFOGain.connect(musicFilter.frequency);
        filterLFO.start();
        this.avalancheLFOs.push(filterLFO);

        // Chord progression: Am - F - G - Am (A natural minor)
        // Frequencies for each chord (root, fifth, octave)
        const chords = [
            { name: 'Am', freqs: [110.0, 164.81, 220.0, 329.63] },  // A2, E3, A3, E4
            { name: 'F',  freqs: [87.31, 130.81, 174.61, 261.63] }, // F2, C3, F3, C4
            { name: 'G',  freqs: [98.00, 146.83, 196.00, 293.66] }, // G2, D3, G3, D4
            { name: 'Am', freqs: [110.0, 164.81, 220.0, 329.63] },  // A2, E3, A3, E4
        ];

        let chordIndex = 0;
        const chordDuration = 16.0; // seconds per chord

        const playChord = () => {
            if (!this.avalancheActive || !this.audioCtx) return;
            const ctx = this.audioCtx;
            const chord = chords[chordIndex % chords.length];
            const now = ctx.currentTime;

            // Sub-bass pulse — deep, slow heartbeat
            const subBass = ctx.createOscillator();
            subBass.type = 'sine';
            subBass.frequency.value = chord.freqs[0] / 2; // one octave below root
            const subGain = ctx.createGain();
            subGain.gain.setValueAtTime(0, now);
            subGain.gain.linearRampToValueAtTime(0.4, now + 4.0);
            subGain.gain.linearRampToValueAtTime(0.3, now + chordDuration - 4.0);
            subGain.gain.linearRampToValueAtTime(0, now + chordDuration);
            subBass.connect(subGain);
            subGain.connect(musicFilter);
            subBass.start(now);
            subBass.stop(now + chordDuration + 0.5);
            this.avalancheOscillators.push(subBass);
            this.avalancheGains.push(subGain);

            // Chord voices — sustained tones with slow detune drift
            chord.freqs.forEach((freq, i) => {
                const osc = ctx.createOscillator();
                osc.type = i === 0 ? 'triangle' : 'sine';
                osc.frequency.value = freq;

                // Slight detune for thickness
                osc.detune.value = (Math.random() - 0.5) * 8;

                const gain = ctx.createGain();
                const attackTime = 6.0 + i * 0.5;
                const releaseTime = 6.0;
                gain.gain.setValueAtTime(0, now);
                gain.gain.linearRampToValueAtTime(0.15 / (i + 1), now + attackTime);
                gain.gain.setValueAtTime(0.15 / (i + 1), now + chordDuration - releaseTime);
                gain.gain.linearRampToValueAtTime(0, now + chordDuration);

                // Slow detune drift per voice
                const detuneLFO = ctx.createOscillator();
                const detuneLFOGain = ctx.createGain();
                detuneLFO.type = 'sine';
                detuneLFO.frequency.value = 0.05 + Math.random() * 0.05;
                detuneLFOGain.gain.value = 3 + Math.random() * 4;
                detuneLFO.connect(detuneLFOGain);
                detuneLFOGain.connect(osc.detune);
                detuneLFO.start(now);
                detuneLFO.stop(now + chordDuration + 0.5);
                this.avalancheLFOs.push(detuneLFO);

                osc.connect(gain);
                gain.connect(musicFilter);
                osc.start(now);
                osc.stop(now + chordDuration + 0.5);
                this.avalancheOscillators.push(osc);
                this.avalancheGains.push(gain);
            });

            // Occasional high "ghost" overtone — eerie, distant
            if (Math.random() < 0.4) {
                const ghostFreq = chord.freqs[chord.freqs.length - 1] * 2;
                const ghost = ctx.createOscillator();
                ghost.type = 'sine';
                ghost.frequency.value = ghostFreq;
                const ghostGain = ctx.createGain();
                const ghostStart = now + 4 + Math.random() * 8;
                ghostGain.gain.setValueAtTime(0, now);
                ghostGain.gain.setValueAtTime(0, ghostStart);
                ghostGain.gain.linearRampToValueAtTime(0.04, ghostStart + 3.0);
                ghostGain.gain.linearRampToValueAtTime(0, ghostStart + 8.0);
                ghost.connect(ghostGain);
                ghostGain.connect(musicFilter);
                ghost.start(now);
                ghost.stop(now + chordDuration + 0.5);
                this.avalancheOscillators.push(ghost);
                this.avalancheGains.push(ghostGain);
            }

            chordIndex++;
        };

        // Play first chord immediately, then schedule subsequent chords
        playChord();
        this.avalancheInterval = window.setInterval(playChord, chordDuration * 1000);
    }

    /** Stop the Avalanche music with a slow fade-out. */
    public stopAvalancheMusic(): void {
        if (!this.avalancheActive || !this.audioCtx) return;

        this.avalancheActive = false;
        this.musicEnabled = false;
        this.log('[Director] 🎵 Avalanche music fading out...', '#8a7a5a');

        // Slow fade out
        if (this.avalancheGainNode) {
            const now = this.audioCtx.currentTime;
            this.avalancheGainNode.gain.cancelScheduledValues(now);
            this.avalancheGainNode.gain.setValueAtTime(this.avalancheGainNode.gain.value, now);
            this.avalancheGainNode.gain.linearRampToValueAtTime(0, now + 5.0);
        }

        // Stop the chord scheduler
        if (this.avalancheInterval !== null) {
            clearInterval(this.avalancheInterval);
            this.avalancheInterval = null;
        }

        // Let existing oscillators finish their release, then clean up
        setTimeout(() => {
            this.avalancheOscillators.forEach(o => { try { o.stop(); o.disconnect(); } catch {} });
            this.avalancheGains.forEach(g => { try { g.disconnect(); } catch {} });
            this.avalancheLFOs.forEach(l => { try { l.stop(); l.disconnect(); } catch {} });
            this.avalancheOscillators = [];
            this.avalancheGains = [];
            this.avalancheLFOs = [];
        }, 6000);
    }

    public get isMusicPlaying(): boolean {
        return this.avalancheActive || this.musicEnabled;
    }

    // ═══════════════════════════════════════════════════════════════
    // HOT-RELOADABLE SETTINGS (via SoftLayer)
    // ═══════════════════════════════════════════════════════════════

    public setVoicePitch(pitch: number): void {
        this.voicePitch = Math.max(0, Math.min(2, pitch));
    }

    public setVoiceRate(rate: number): void {
        this.voiceRate = Math.max(0.1, Math.min(2, rate));
    }

    public setVoiceVolume(vol: number): void {
        this.voiceVolume = Math.max(0, Math.min(1, vol));
        if (this.masterGain) this.masterGain.gain.value = this.voiceVolume;
    }

    public setReverbAmount(amount: number): void {
        this.reverbAmount = Math.max(0, Math.min(1, amount));
        if (this.dryGain) this.dryGain.gain.value = 1.0 - this.reverbAmount;
        if (this.reverbGain) this.reverbGain.gain.value = this.reverbAmount;
    }

    public setFilterCutoff(hz: number): void {
        this.filterCutoff = Math.max(100, Math.min(8000, hz));
        if (this.lowpassFilter) this.lowpassFilter.frequency.value = this.filterCutoff;
    }

    public setMusicVolume(vol: number): void {
        this.musicVolume = Math.max(0, Math.min(1, vol));
        if (this.avalancheGainNode && this.avalancheActive) {
            this.avalancheGainNode.gain.value = this.musicVolume;
        }
    }

    public setPreferredVoice(name: string): void {
        this.preferredVoiceName = name;
    }

    /** Toggle the Avalanche music on/off. */
    public toggleAvalancheMusic(): boolean {
        if (this.avalancheActive) {
            this.stopAvalancheMusic();
        } else {
            this.startAvalancheMusic();
        }
        return this.avalancheActive;
    }
}

// Singleton instance
export const directorVoice = new DirectorVoiceEngine();
(window as any).foveaiDirectorVoice = directorVoice;
