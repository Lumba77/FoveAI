/**
 * ═══════════════════════════════════════════════════════════════════════
 * BODILY REFLEX REGULATOR — The Cerebellum / Autonomic Layer
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Jen's body operates on TWO layers:
 *
 *   Layer 1 (FAST — BodilyReflex, this module):
 *     - Local Qwen 3.5 4B or procedural fallback
 *     - Handles sub-second reflexes: breathing adjustments, gaze shifts,
 *       posture corrections, micro-gesture smoothing, emotional tremor
 *     - Runs autonomously — no cloud LLM involvement
 *     - Provides sensory body-state to the LLM for its next reasoning turn
 *
 *   Layer 2 (SLOW — Cloud LLM via <movement:...> / <emotion:...> tokens):
 *     - Gemma4 31B / Qwen 3.5 Cloud / DeepSeek 4-Pro
 *     - Issues high-level directives: "walk toward user", "sit down",
 *       "express excitement", "look around the room"
 *     - BodilyReflex translates these into smooth action sequences
 *
 * This is Jen's CEREBELLUM: it doesn't decide what to do, but it makes
 * whatever she decides to do look natural, smooth, and alive.
 *
 * DESIGN PRINCIPLES:
 *   1. Locality: runs entirely in-browser, 0ms network latency
 *   2. Fallback: when cloud LLM is slow/unavailable, maintains aliveness
 *   3. Transparency: exposes state to LLM so it knows what the body did
 *   4. Smoothness: interpolates between states, no jerky transitions
 */

import * as THREE from 'three';

// ─── Reflex State ────────────────────────────────────────────────────
export interface ReflexState {
    // Physiological (autonomic)
    heartRate:          number;   // 60-120 bpm, emotion-modulated
    breathDepth:        number;   // 0-1, shallow ↔ deep
    breathRate:         number;   // 0.5-2.0 multiplier
    pupilDilation:      number;   // 0-1, arousal indicator
    muscleTone:         number;   // 0-1, relaxed ↔ tense
    
    // Postural (cerebellar)
    balanceShift:       number;   // -1 to 1, left ↔ right weight shift
    spineCurvature:    number;   // -0.05 to 0.05, slouched ↔ upright
    shoulderTension:    number;   // 0-1, relaxed ↔ raised

    // Attentional (orienting)
    gazeFocus:          number;   // 0-1, wandering ↔ locked on target
    headOrientation:    THREE.Vector3;  // euler angles
    attentionTarget:    THREE.Vector3 | null;

    // Emotional (somatic markers)
    emotionalTremor:    number;   // 0-1, micro-tremble amplitude
    expressionDrift:    number;   // how much face drifts toward resting
    socialWarmth:       number;   // 0-1, warmth of body language

    // Directive queue (from LLM)
    activeDirective:    string | null;
    directiveProgress:  number;   // 0-1, completion of current directive
    directiveData:      any;
}

// ─── Reflex Config ───────────────────────────────────────────────────
export interface ReflexConfig {
    // Timing
    reflexTickRate:         number;   // Hz — how fast reflexes update
    directiveTimeout:       number;   // seconds before directive expires
    
    // Physiological ranges
    restingHeartRate:       number;   // bpm at calm
    excitedHeartRate:       number;   // bpm at excited
    restingBreathRate:      number;   // multiplier at calm
    excitedBreathRate:      number;   // multiplier at excited
    
    // Postural defaults
    defaultSpineCurvature: number;
    maxBalanceShift:        number;
    
    // Gaze
    defaultGazeFocus:       number;
    attentionGazeFocus:     number;
    
    // Somatic
    tremorBaseAmplitude:   number;
    expressionRestoreRate:  number;
}

export const DEFAULT_REFLEX_CONFIG: ReflexConfig = {
    reflexTickRate:         10,      // 10 Hz — fast enough for smoothness
    directiveTimeout:       30,      // 30s before directive auto-expires
    
    restingHeartRate:       68,
    excitedHeartRate:       105,
    restingBreathRate:      1.0,
    excitedBreathRate:      1.6,
    
    defaultSpineCurvature: -0.02,
    maxBalanceShift:        0.03,
    
    defaultGazeFocus:       0.3,
    attentionGazeFocus:     0.9,
    
    tremorBaseAmplitude:   0.003,
    expressionRestoreRate:  0.02,
};

// ─── Emotion → Physiology mapping ─────────────────────────────────────
const EMOTION_PHYSIOLOGY: Record<string, Partial<ReflexState>> = {
    'neutral':   { heartRate: 68, breathRate: 1.0, muscleTone: 0.2, pupilDilation: 0.2, socialWarmth: 0.4 },
    'happy':     { heartRate: 80, breathRate: 1.2, muscleTone: 0.3, pupilDilation: 0.4, socialWarmth: 0.8, emotionalTremor: 0.02 },
    'excited':   { heartRate: 95, breathRate: 1.5, muscleTone: 0.5, pupilDilation: 0.6, socialWarmth: 0.9, emotionalTremor: 0.04 },
    'sad':       { heartRate: 62, breathRate: 0.7, muscleTone: 0.15, pupilDilation: 0.1, socialWarmth: 0.3, spineCurvature: 0.04 },
    'angry':     { heartRate: 100, breathRate: 1.4, muscleTone: 0.8, pupilDilation: 0.5, socialWarmth: 0.1 },
    'curious':   { heartRate: 75, breathRate: 1.1, muscleTone: 0.3, pupilDilation: 0.5, socialWarmth: 0.6, gazeFocus: 0.7 },
    'surprised': { heartRate: 90, breathRate: 1.3, muscleTone: 0.6, pupilDilation: 0.7, socialWarmth: 0.5, emotionalTremor: 0.03 },
    'concerned': { heartRate: 72, breathRate: 0.9, muscleTone: 0.4, pupilDilation: 0.3, socialWarmth: 0.6 },
    'calm':      { heartRate: 62, breathRate: 0.7, muscleTone: 0.1, pupilDilation: 0.1, socialWarmth: 0.5, gazeFocus: 0.2 },
    'thinking':  { heartRate: 70, breathRate: 0.9, muscleTone: 0.2, pupilDilation: 0.3, socialWarmth: 0.4, gazeFocus: 0.1 },
};

export class BodilyReflex {
    private config: ReflexConfig;
    private state: ReflexState;
    private time: number = 0;
    private reflexAccumulator: number = 0;
    
    // ── Callbacks (set by AvatarManager) ──
    public onPhysiologyUpdate?: (state: ReflexState) => void;
    public onDirectiveComplete?: (directive: string, data: any) => void;
    public onLog?: (msg: string, color: string) => void;

    constructor(config?: Partial<ReflexConfig>) {
        this.config = { ...DEFAULT_REFLEX_CONFIG, ...config };
        this.state = this.createDefaultState();
    }

    private createDefaultState(): ReflexState {
        return {
            heartRate:      this.config.restingHeartRate,
            breathDepth:    0.5,
            breathRate:     this.config.restingBreathRate,
            pupilDilation:  0.2,
            muscleTone:     0.2,
            balanceShift:   0,
            spineCurvature: this.config.defaultSpineCurvature,
            shoulderTension: 0.15,
            gazeFocus:      this.config.defaultGazeFocus,
            headOrientation: new THREE.Vector3(0, 0, 0),
            attentionTarget: null,
            emotionalTremor: 0,
            expressionDrift: 0,
            socialWarmth:    0.4,
            activeDirective: null,
            directiveProgress: 0,
            directiveData:    null,
        };
    }

    // ─── Public API ──────────────────────────────────────────────────

    /** Get current reflex state snapshot for LLM sensory context. */
    public getState(): ReflexState { return { ...this.state, headOrientation: this.state.headOrientation.clone() }; }

    /** Set emotional state — triggers physiological cascade. */
    public setEmotion(emotion: string, intensity: number = 1.0) {
        const phys = EMOTION_PHYSIOLOGY[emotion.toLowerCase()];
        if (!phys) {
            this.onLog?.(`[Reflex] Unknown emotion: ${emotion}`, 'var(--neon-yellow)');
            return;
        }
        // Blend target physiology with intensity
        if (phys.heartRate !== undefined) this.state.heartRate = THREE.MathUtils.lerp(this.config.restingHeartRate, phys.heartRate, intensity);
        if (phys.breathRate !== undefined) this.state.breathRate = THREE.MathUtils.lerp(1.0, phys.breathRate, intensity);
        if (phys.muscleTone !== undefined) this.state.muscleTone = phys.muscleTone * intensity;
        if (phys.pupilDilation !== undefined) this.state.pupilDilation = phys.pupilDilation * intensity;
        if (phys.socialWarmth !== undefined) this.state.socialWarmth = phys.socialWarmth * intensity;
        if (phys.spineCurvature !== undefined) this.state.spineCurvature = phys.spineCurvature * intensity;
        if (phys.gazeFocus !== undefined) this.state.gazeFocus = phys.gazeFocus * intensity;
        if (phys.emotionalTremor !== undefined) this.state.emotionalTremor = phys.emotionalTremor * intensity;
        
        this.onLog?.(`[Reflex] Physiology set to ${emotion} (intensity=${intensity})`, 'var(--neon-green)');
    }

    /** Receive a high-level directive from the LLM. */
    public receiveDirective(directive: string, data?: any) {
        this.state.activeDirective = directive;
        this.state.directiveProgress = 0;
        this.state.directiveData = data || {};
        this.onLog?.(`[Reflex] Directive received: ${directive}`, 'var(--neon-blue)');
    }

    /** Query: is the body currently executing a directive? */
    public isBusy(): boolean {
        return this.state.activeDirective !== null && this.state.directiveProgress < 1.0;
    }

    /** Generate body-awareness text for LLM sensory context. */
    public getBodyAwarenessText(): string {
        const s = this.state;
        const directives = s.activeDirective
            ? `Currently executing: ${s.activeDirective} (${Math.round(s.directiveProgress * 100)}% complete)`
            : 'No active directive — receptive to commands';
        
        const physiology = [
            `💓 HR: ${Math.round(s.heartRate)} bpm`,
            `🫁 Breath: ${s.breathRate.toFixed(1)}x depth`,
            `👁️ Gaze focus: ${(s.gazeFocus * 100).toFixed(0)}%`,
            `💪 Tone: ${(s.muscleTone * 100).toFixed(0)}%`,
            `🤝 Warmth: ${(s.socialWarmth * 100).toFixed(0)}%`,
            `😌 Spine: ${s.spineCurvature > 0 ? 'slouched' : 'upright'}`,
        ].join(' | ');

        return `[BODY AWARENESS]\n${directives}\nPhysiology: ${physiology}`;
    }

    // ─── Core Tick ────────────────────────────────────────────────────

    /** 
     * Update reflexes. Called each frame by AvatarManager.update().
     * Operates at reflexTickRate Hz internally for smooth interpolation.
     */
    public update(delta: number) {
        this.time += delta;
        this.reflexAccumulator += delta;
        
        const tickInterval = 1.0 / this.config.reflexTickRate;
        
        // Run reflex ticks at the configured rate
        while (this.reflexAccumulator >= tickInterval) {
            this.reflexAccumulator -= tickInterval;
            this.tickReflexes(tickInterval);
        }
        
        // Interpolate continuous values between ticks
        this.smoothPhysiology(delta);
    }

    private tickReflexes(delta: number) {
        const s = this.state;
        const cfg = this.config;
        
        // ── 1. Heart rate: slowly returns to baseline ──
        const hrTarget = cfg.restingHeartRate;
        s.heartRate += (hrTarget - s.heartRate) * delta * 0.3;
        
        // ── 2. Breath: modulate by activity level ──
        const breathTarget = cfg.restingBreathRate;
        s.breathRate += (breathTarget - s.breathRate) * delta * 0.5;
        s.breathDepth = Math.sin(this.time * s.breathRate * Math.PI) * 0.5 + 0.5;
        
        // ── 3. Balance: natural micro-shifts ──
        const balanceTarget = Math.sin(this.time * 0.3) * cfg.maxBalanceShift * 0.5;
        s.balanceShift += (balanceTarget - s.balanceShift) * delta * 2.0;
        
        // ── 4. Muscle tone: decays toward baseline ──
        s.muscleTone += (0.2 - s.muscleTone) * delta * 0.4;
        s.shoulderTension += (0.15 - s.shoulderTension) * delta * 0.3;
        
        // ── 5. Spine curvature: natural drift ──
        s.spineCurvature += (cfg.defaultSpineCurvature - s.spineCurvature) * delta * 0.2;
        
        // ── 6. Gaze focus: decays toward default ──
        const gazeTarget = s.attentionTarget ? cfg.attentionGazeFocus : cfg.defaultGazeFocus;
        s.gazeFocus += (gazeTarget - s.gazeFocus) * delta * 2.0;
        
        // ── 7. Expression: slowly restores to neutral ──
        s.expressionDrift += (cfg.expressionRestoreRate * delta);
        s.expressionDrift = Math.min(1.0, s.expressionDrift);
        
        // ── 8. Emotional tremor: decays ──
        s.emotionalTremor *= (1 - delta * 1.5);
        if (s.emotionalTremor < cfg.tremorBaseAmplitude) {
            s.emotionalTremor = cfg.tremorBaseAmplitude;
        }
        
        // ── 9. Social warmth: decays toward baseline ──
        s.socialWarmth += (0.4 - s.socialWarmth) * delta * 0.15;
        
        // ── 10. Directive progress ──
        if (s.activeDirective && s.directiveProgress < 1.0) {
            // Directives complete over ~3-5 seconds for fast actions,
            // longer for walks (handled by MovementEngine)
            const isMovement = ['walk_forward', 'move_to'].includes(s.activeDirective);
            const progressRate = isMovement ? 0 // MovementEngine handles completion
                : 1.0 / 3.0; // 3 seconds for expressive directives
            s.directiveProgress += progressRate * delta;
            
            if (s.directiveProgress >= 1.0) {
                s.directiveProgress = 1.0;
                this.onDirectiveComplete?.(s.activeDirective, s.directiveData);
                this.onLog?.(`[Reflex] Directive complete: ${s.activeDirective}`, 'var(--neon-green)');
                setTimeout(() => {
                    if (this.state.activeDirective === s.activeDirective) {
                        // Movement directives clear when MovementEngine reports completion
                        if (s.activeDirective !== null && !['walk_forward', 'move_to'].includes(s.activeDirective)) {
                            this.state.activeDirective = null;
                            this.state.directiveData = null;
                        }
                    }
                }, 500);
            }
        }
        
        // ── Notify subscribers ──
        this.onPhysiologyUpdate?.(this.getState());
    }

    private smoothPhysiology(delta: number) {
        // Continuous interpolation of fast-changing values between ticks
        // (Most values are already being smoothly interpolated in tickReflexes,
        //  this is for any sub-tick smoothing needed)
    }

    // ─── Directive Result Feedback ────────────────────────────────────

    /** Called by MovementEngine when a movement directive completes. */
    public onMovementComplete() {
        if (this.state.activeDirective && ['walk_forward', 'move_to'].includes(this.state.activeDirective)) {
            this.state.directiveProgress = 1.0;
            this.onDirectiveComplete?.(this.state.activeDirective, this.state.directiveData);
            this.onLog?.(`[Reflex] Movement directive complete: ${this.state.activeDirective}`, 'var(--neon-green)');
            setTimeout(() => {
                this.state.activeDirective = null;
                this.state.directiveData = null;
            }, 500);
        }
    }

    /** Called by AvatarManager when an emotion animation finishes. */
    public onExpressionComplete() {
        this.state.expressionDrift = 0;
    }
}