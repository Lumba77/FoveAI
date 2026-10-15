import * as THREE from 'three';

/**
 * ═══════════════════════════════════════════════════════════════════════
 * MOVEMENT ENGINE — Natural Locomotion & Behavior Core for Jen
 * ═══════════════════════════════════════════════════════════════════════
 *
 * An installable movement engine that replaces raw impulse-based wandering
 * with natural, purposeful behavior patterns. Jen can still move, walk,
 * express, and self-puppeteer — but her movements are now grounded,
 * intentional, and feel like a living person choosing to be present.
 *
 * DESIGN PRINCIPLES:
 *   1. "Calm Presence" — Mostly idle, breathing, micro-gestures
 *   2. "Purposeful Movement" — When she moves, it's short and meaningful
 *   3. "Home Drift" — She always gently returns to her home position
 *   4. "Emotion-Driven" — AI emotions drive body language, not random urges
 *   5. "Natural Transitions" — Smooth acceleration, deceleration, turn-then-walk
 *
 * BEHAVIOR STATES:
 *   - CALM_IDLE:      Default. Breathing, micro-gestures, head tracking
 *   - SOCIAL_TURN:    Turning toward user. Warm attention.
 *   - CURIOUS_STEP:   1-2 short steps toward something interesting
 *   - WANDER_NEARBY:  Short walk nearby, then return home
 *   - EMOTIONAL_BURST: Animation triggered by AI emotion output
 *   - RETURNING_HOME: Smooth walk back to home position
 *   - RESTING:        Deep idle, very minimal motion
 *
 * USAGE:
 *   const engine = new MovementEngine();
 *   engine.setHomePosition(new THREE.Vector3(0, -0.8, -2));
 *   engine.setAvatarManager(avatarManager);
 *   engine.update(delta, cameraPosition);
 *
 * ╔══════════════════════════════════════════════════════════════════════╗
 * ║  NODE:002 — MovementEngine: Locomotion & Behavior Core             ║
 * ║  STATUS: 🟢 HYBRID — LLM-driven movement is primary, gentle        ║
 * ║  autonomous household presence is secondary.                       ║
 * ╠══════════════════════════════════════════════════════════════════════╣
 * ║  THE CURRENT ARCHITECTURE ("Jen lives here"):                      ║
 * ║  MovementEngine obeys `intentionalGoal` from BracketParser         ║
 * ║  `<movement:...>` commands as primary authority. When the LLM      ║
 * ║  hasn't sent a movement command for a while, gentle autonomous     ║
 * ║  behavior kicks in — micro-gestures, curious steps, short          ║
 * ║  wanders, resting. This makes Jen feel like a natural part of      ║
 * ║  the household instead of standing frozen.                         ║
 * ║  Toggle: FoveAI.setParam("avatar.autonomousMode", true/false)      ║
 * ║  Tune: softlayer/behavior_config.js                                ║
 * ╠══════════════════════════════════════════════════════════════════════╣
 * ║  RESOLVED ISSUES:                                                  ║
 * ║  [SOLVED] Frozen pose — autonomous idle prevents freezing.         ║
 * ║  [SOLVED] isIntentional flag — `intentionalGoal` and               ║
 * ║           `intentionalExpiry` (10s TTL) strictly govern movement.  ║
 * ║  [SOLVED] Proper feedback paths — Arrival and Timeout failure      ║
 * ║           callbacks dispatch `foveai_body_feedback` events, giving  ║
 * ║           the LLM total contextual awareness of her body state.    ║
 * ╚══════════════════════════════════════════════════════════════════════╝
 */

// ─── Behavior States ────────────────────────────────────────────────
export type BehaviorState =
    | 'calm_idle'
    | 'social_turn'
    | 'curious_step'
    | 'wander_nearby'
    | 'emotional_burst'
    | 'returning_home'
    | 'resting';

// ─── Movement Config — All tunable parameters in one place ─────────
export interface MovementConfig {
    // ── Timing ──
    decisionInterval:       number;  // Seconds between autonomous decisions
    minStateDuration:       number;  // Minimum time in any state before transitioning
    returnHomeDelay:        number;  // Seconds to wait before drifting home after movement

    // ── Movement ──
    walkSpeed:              number;  // Units per second when walking
    slowWalkSpeed:          number;  // Slower, more natural pace
    turnSpeed:              number;  // Radians per second for smooth turning
    maxWanderDistance:      number;  // Max meters from home position
    preferredStepDistance:  number;  // Typical short step distance
    approachDistance:       number;  // How close to approach user-facing direction

    // ── Idle Behavior ──
    idleMicroGestureChance: number;  // Chance per decision to do a micro-gesture
    idleBreathVariation:    number;  // How much breathing varies in idle
    idleSwayAmount:         number;  // Subtle body sway amplitude

    // ── Home Drift ──
    homeDriftStrength:      number;  // How strongly she's pulled back home (0-1)
    homeDriftThreshold:    number;  // Distance from home before drift activates

    // ── Drives (calm-tuned defaults) ──
    curiosityBaseline:      number;  // Gentle baseline curiosity
    restlessnessThreshold:  number;  // Time still before considering movement
    socialNeedRate:         number;  // How fast social need rises
    spontaneity:            number;  // Chance of unprompted action
    expressivenessDecay:    number;  // How fast expressiveness fades
    energyRecoveryRate:     number;  // Energy recovery while calm
    energyDrainRate:        number;  // Energy cost of movement
}

export const DEFAULT_CONFIG: MovementConfig = {
    // ── Timing ──
    decisionInterval:       7.0,    // ~7s between decisions — calm, not twitchy
    minStateDuration:       3.0,    // Stay in each state at least 3s
    returnHomeDelay:        5.0,    // Wait 5s after movement before drifting home

    // ── Movement ──
    walkSpeed:              1.0,    // Natural walking pace (slightly slower than before)
    slowWalkSpeed:          0.5,    // For curious steps and approach
    turnSpeed:              2.0,    // Smooth turning rate
    maxWanderDistance:       2.0,   // Never more than 2m from home
    preferredStepDistance:   0.8,   // Short, purposeful steps
    approachDistance:        1.0,   // Don't crowd the user

    // ── Idle Behavior ──
    idleMicroGestureChance: 0.08,   // ~8% chance per decision for a micro-gesture
    idleBreathVariation:    0.03,   // Subtle breathing
    idleSwayAmount:         0.015,  // Very subtle sway

    // ── Home Drift ──
    homeDriftStrength:      0.6,   // Moderate pull back home
    homeDriftThreshold:    0.5,    // Start drifting home if >0.5m away

    // ── Drives ──
    curiosityBaseline:      0.12,   // Gently curious
    restlessnessThreshold:  25.0,   // 25s still before even considering movement
    socialNeedRate:         0.008,  // Slowly misses company
    spontaneity:            0.06,   // Rare spontaneous gestures
    expressivenessDecay:    0.04,   // Expressiveness fades moderately
    energyRecoveryRate:     0.06,   // Recovers energy well while calm
    energyDrainRate:        0.04,   // Movement costs energy
};

// ─── Drive State ─────────────────────────────────────────────────────
export interface DriveState {
    curiosity:      number;  // 0-1: Urge to investigate
    social:         number;  // 0-1: Need for connection
    restlessness:   number;  // 0-1: Urge to move (kept very low)
    expressiveness: number;  // 0-1: Urge to show emotion
    energy:         number;  // 0-1: Available activity capacity
}

// ─── Awareness State ────────────────────────────────────────────────
export interface AwarenessState {
    timeSinceLastInteraction: number;
    timeSinceLastMove:        number;
    timeInSameEmotion:        number;
    timeInCurrentState:       number;
    currentActivity:          string;
    lastDecision:             number;
}

// ─── Emotion → Animation Mapping ────────────────────────────────────
const EMOTION_ANIM_MAP: Record<string, string> = {
    'happy':     'Happy',
    'excited':   'Happy',
    'sad':       'Sad',
    'concerned': 'Sad',
    'angry':     'Angry',
    'surprised': 'Surprised',
    'curious':   'Thinking',
    'thinking':  'Thinking',
    'neutral':   'Idle',
    'relaxed':   'Idle',
    'calm':      'Idle',
    'playful':   'Dance',
    'grateful':  'Happy',
    'love':      'Social',
    'affection': 'Social',
    'bored':     'Idle',
    'anxious':   'Thinking',
};

// ─── Micro-gesture pool by context ───────────────────────────────────
const IDLE_GESTURES    = ['nod', 'tilt', 'look_away', 'double_take'];
export const SOCIAL_GESTURES = ['nod', 'tilt'];
export const CURIOUS_GESTURES = ['double_take', 'look_away', 'tilt'];

export class MovementEngine {
    // ── Configuration ──
    private config: MovementConfig;

    // ── State ──
    private behaviorState: BehaviorState = 'calm_idle';
    private emotionalState: string = 'neutral';
    /** last set emotion intensity (0..1) — surfaced via getEmotionalIntensity() */
    private _emotionalIntensity: number = 0;

    // ── Drives ──
    private drives: DriveState = {
        curiosity:      0.15,
        social:         0.25,
        restlessness:   0.02,
        expressiveness: 0.35,
        energy:         0.85,
    };

    // ── Awareness ──
    private awareness: AwarenessState = {
        timeSinceLastInteraction: 0,
        timeSinceLastMove:        0,
        timeInSameEmotion:        0,
        timeInCurrentState:       0,
        currentActivity:          'idle',
        lastDecision:             0,
    };

    // ── Spatial ──
    private homePosition: THREE.Vector3 = new THREE.Vector3(0, -0.8, -2.0);
    private moveTarget: THREE.Vector3 | null = null;
    private isWalking: boolean = false;
    private isReturningHome: boolean = false;
    private intentionalGoal: THREE.Vector3 | null = null;
    private intentionalExpiry: number = 0; // ms timestamp

    // ── Animation category queue ──

    // ── Soft params (from SoftLayer modules, hot-reloadable) ──
    private softParams: Record<string, any> = {};

    /**
     * Get a soft parameter value, falling back to a default.
     * Soft params are set by SoftLayer modules via FoveAI.setParam().
     */
    private _getSoftParam(key: string, defaultValue: any): any {
        if (key in this.softParams) return this.softParams[key];
        // Also check the global FoveAI param store if available
        const globalStore = (window as any).FoveAIParams;
        if (globalStore && key in globalStore) return globalStore[key];
        return defaultValue;
    }

    /**
     * Set a soft parameter (called by SoftLayer loader).
     */
    public setSoftParam(key: string, value: any) {
        this.softParams[key] = value;
    }

    // ── Callbacks — set by AvatarManager ──
    public onPlayCategory?: (category: string, loop: boolean, fadeTime: number) => void;
    public onPlayAnimation?: (url: string, loop: boolean, fadeTime: number) => void;
    public onTriggerMicroGesture?: (gesture: string) => void;
    public onSetDestination?: (target: THREE.Vector3) => void;
    public onWalkForwardCommand?: (distance: number) => void;
    public onSetEmotionalState?: (state: string) => void;
    public onLog?: (msg: string, color: string) => void;

    constructor(config?: Partial<MovementConfig>) {
        this.config = { ...DEFAULT_CONFIG, ...config };
        this.connectMotorCortex();
    }

    private async connectMotorCortex() {
        // The motor daemon is optional and usually idle. Probe it first so a
        // dead port produces silence instead of a CORS/connection error storm.
        try {
            const ctrl = new AbortController();
            const t = setTimeout(() => ctrl.abort(), 1200);
            const r = await fetch('/motor-health', { signal: ctrl.signal });
            clearTimeout(t);
            if (!r.ok) { if (this.onLog) this.onLog('[Motor Cortex] daemon not up — running autonomous-only', 'pink'); return; }
        } catch {
            if (this.onLog) this.onLog('[Motor Cortex] unreachable — running autonomous-only', 'pink');
            return;
        }
        try {
            const motorStream = new EventSource("http://127.0.0.1:8410/stream");
            let attempts = 0;
            motorStream.onerror = () => {
                // The motor daemon is optional; stop hammering a dead port.
                attempts += 1;
                if (attempts >= 3) { try { motorStream.close(); } catch { /* already closed */ } }
            };
            motorStream.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === "motor_action") {
                        if (this.onLog) this.onLog(`[Motor Cortex] Subconscious impulse: ${data.tool}`, 'pink');
                        if (data.tool === "setEmotion") {
                            this.setEmotion(data.args.emotion, data.args.intensity);
                        } else if (data.tool === "commandMoveTo") {
                            // Convert string target to Vector3. In a full implementation, you'd look up the scene node.
                            // For now, we command a small forward step to acknowledge the impulse.
                            if (this.onWalkForwardCommand) this.onWalkForwardCommand(1.0);
                        } else if (data.tool === "trigger_micro_gesture") {
                            if (this.onTriggerMicroGesture) this.onTriggerMicroGesture(data.args.gesture);
                        } else if (data.tool === "walk_forward") {
                            if (this.onWalkForwardCommand) this.onWalkForwardCommand(data.args.distance || 1.0);
                        }
                    }
                } catch (e) {
                    console.error("[MovementEngine] Failed to parse motor impulse:", e);
                }
            };
            motorStream.onerror = () => {
                // Silently handle connection drops, it will auto-reconnect
            };
            if (this.onLog) this.onLog(`[Motor Cortex] Connected to subconscious stream (Port 8110)`, 'cyan');
        } catch (e) {
            console.error("[MovementEngine] Failed to connect to motor stream:", e);
        }
    }

    // ─── Public API ──────────────────────────────────────────────────

    public getHomePosition(): THREE.Vector3 { return this.homePosition.clone(); }
    public setHomePosition(pos: THREE.Vector3) { this.homePosition.copy(pos); }

    public getState(): BehaviorState { return this.behaviorState; }
    public getDrives(): DriveState { return { ...this.drives }; }
    public getAwareness(): AwarenessState { return { ...this.awareness }; }
    public getWalkSpeed(): number { return this.isReturningHome ? this.config.slowWalkSpeed : this.config.walkSpeed; }

    public isMoving(): boolean { return this.isWalking || this.moveTarget !== null; }
    public getMoveTarget(): THREE.Vector3 | null { return this.moveTarget; }

    public setDestination(target: THREE.Vector3) {
        this.moveTarget = target.clone();
        this.intentionalGoal = target.clone();
        this.intentionalExpiry = Date.now() + 10000; // 10s TTL
        this.isReturningHome = false;
    }

    /** Called when AI emotion is detected (self-puppeteering bridge) */
    public setEmotion(emotion: string, intensity: number = 1.0) {
        this.emotionalState = emotion.toLowerCase();
        this._emotionalIntensity = intensity;
        this.awareness.timeInSameEmotion = 0;
        // Strong emotions can trigger state transitions immediately
        if (['happy', 'excited', 'sad', 'angry', 'surprised'].includes(this.emotionalState)) {
            this.transitionTo('emotional_burst');
        }
    }

    /** Called when user interacts — satisfies social need */
    public onUserInteraction() {
        this.awareness.timeSinceLastInteraction = 0;
        this.drives.social *= 0.3;
    }

    /** Called by AI <MOVE_TO> command — intentional navigation.
     *  Does NOT call transitionTo() — that would schedule an automatic
     *  return-home timer that overrides intentional movement ("kidnapping"). */
    public commandMoveTo(target: THREE.Vector3) {
        this.moveTarget = target.clone();
        this.isReturningHome = false;
        this.intentionalGoal = target.clone();
        this.intentionalExpiry = Date.now() + 10000; // 10s TTL
        this.awareness.timeSinceLastMove = 0;
    }

    /** Called by AI <WALK_FORWARD> command — walk in facing direction.
     *  The target position is computed by AvatarManager (which has the VRM reference)
     *  and passed in here so the engine actually has a destination to walk toward. */
    public commandWalkForward(target: THREE.Vector3) {
        this.moveTarget = target.clone();
        this.isReturningHome = false;
        this.intentionalGoal = target.clone();
        this.intentionalExpiry = Date.now() + 10000; // 10s TTL
        this.awareness.timeSinceLastMove = 0;
        // Do NOT transitionTo('wander_nearby') — that schedules an automatic
        // return-home timer that overrides intentional movement ("kidnapping").
        // Intentional movement stays in calm_idle behaviorally; the walk
        // animation is driven by velocity in the update loop.
    }

    /** Called by steering mode — manual control overrides autonomous movement */
    public setSteeringActive(active: boolean) {
        if (active) {
            this.moveTarget = null;
            this.isWalking = false;
            this.isReturningHome = false;
            this.intentionalGoal = null;
            this.intentionalExpiry = 0;
            this.transitionTo('calm_idle');
        }
    }

    /** Set social relationship-appropriate mode */
    public setSocialMode(mode: string) {
        switch (mode) {
            case 'coexist':
                this.config.spontaneity = 0.02;
                this.config.socialNeedRate = 0.003;
                this.drives.curiosity = 0.08;
                this.drives.restlessness = 0.01;
                break;
            case 'cowork':
                this.config.spontaneity = 0.04;
                this.config.socialNeedRate = 0.005;
                this.drives.curiosity = 0.1;
                break;
            case 'coop':
                this.config.spontaneity = 0.08;
                this.config.socialNeedRate = 0.01;
                this.drives.curiosity = 0.2;
                this.drives.expressiveness = 0.4;
                break;
            case 'rest':
                this.config.spontaneity = 0.02;
                this.config.socialNeedRate = 0.003;
                this.drives.energy = 0.4;
                this.drives.restlessness = 0.0;
                this.emotionalState = 'calm';
                break;
            case 'follow':
                this.config.spontaneity = 0.03;
                this.drives.curiosity = 0.5;
                break;
            case 'intimate':
                this.config.spontaneity = 0.04;
                this.config.socialNeedRate = 0.015;
                this.drives.social = 0.8;
                this.drives.expressiveness = 0.6;
                break;
        }
    }

    /** Get the animation category for the current emotional state */
    public getEmotionAnimation(): string {
        return EMOTION_ANIM_MAP[this.emotionalState] || 'Idle';
    }

    // ─── Core Update Loop ─────────────────────────────────────────────

    public update(delta: number, currentPosition: THREE.Vector3, cameraPosition?: THREE.Vector3): {
        velocity: THREE.Vector3;
        targetRotation: THREE.Quaternion | null;
        animationCategory: string | null;
        microGesture: string | null;
    } {
        // Prevent autonomous movement when Soul backend is down/unreachable
        const soulReachable = !(window as any).foveaiBrainState || (window as any).foveaiBrainState.soulReachable !== false;
        if (!soulReachable) {
            if (this.moveTarget && !this.intentionalGoal) {
                this.moveTarget = null;
                this.isWalking = false;
            }
        }

        // ── Update drives and awareness ──
        this.updateDrives(delta);
        this.awareness.timeSinceLastInteraction += delta;
        this.awareness.timeSinceLastMove += delta;
        this.awareness.timeInSameEmotion += delta;
        this.awareness.timeInCurrentState += delta;

        // ── Check for movement completion ──
        if (this.moveTarget) {
            const dist = currentPosition.distanceTo(this.moveTarget);
            if (dist < 0.15) {
                this.moveTarget = null;
                this.isWalking = false;
                this.awareness.timeSinceLastMove = 0;
                
                if (this.intentionalGoal) {
                    this.intentionalGoal = null;
                    this.intentionalExpiry = 0;
                    this.dispatchArrivalFeedback();
                }
            } else if (this.intentionalGoal && Date.now() > this.intentionalExpiry) {
                this.moveTarget = null;
                this.isWalking = false;
                this.intentionalGoal = null;
                this.intentionalExpiry = 0;
                this.dispatchFailureFeedback("Movement timed out. I couldn't reach the destination (possibly blocked).");
            }
        }

        // ── Home drift (gentle) ──
        // When Jen has been idle for a while and is far from home, she slowly
        // drifts back. This is a subtle force, not a walk animation.
        let homeDriftForce = new THREE.Vector3(0, 0, 0);
        const distFromHome = currentPosition.distanceTo(this.homePosition);
        if (!this.moveTarget && !this.intentionalGoal && distFromHome > this.config.maxWanderDistance * 0.8) {
            const driftDir = new THREE.Vector3().subVectors(this.homePosition, currentPosition);
            driftDir.y = 0;
            driftDir.normalize().multiplyScalar(0.15 * delta);
            homeDriftForce.copy(driftDir);
        }

        // ── Autonomous household presence ──
        // Jen has gentle autonomous behavior when the LLM hasn't sent a movement
        // command recently. This makes her feel like a natural part of the household
        // — occasionally wandering, looking around, doing micro-gestures, instead of
        // standing frozen. LLM movement commands always take priority.
        //
        // Toggle via: FoveAI.setParam("avatar.autonomousMode", true/false)
        // Tune via: behavior_config.js (decisionInterval, curiosity, restlessness, etc.)
        this.awareness.lastDecision += delta;
        let animationCategory: string | null = null;
        let microGesture: string | null = null;

        const autonomousEnabled = this._getSoftParam('avatar.autonomousMode', true);
        const idleLongEnough = this.awareness.lastDecision >= this.config.decisionInterval;
        const noIntentionalGoal = !this.intentionalGoal && !this.moveTarget;
        const minStateElapsed = this.awareness.timeInCurrentState >= this.config.minStateDuration;

        if (autonomousEnabled && idleLongEnough && noIntentionalGoal && minStateElapsed && soulReachable) {
            const decision = this.makeDecision();
            this.awareness.lastDecision = 0;
            if (decision.animation) animationCategory = decision.animation;
            if (decision.gesture) microGesture = decision.gesture;
        }

        // ── Compute velocity toward move target ──
        let velocity = new THREE.Vector3(0, 0, 0);
        let targetRotation: THREE.Quaternion | null = null;

        if (this.moveTarget) {
            const dir = new THREE.Vector3().subVectors(this.moveTarget, currentPosition);
            dir.y = 0;
            const dist = dir.length();
            if (dist > 0.15) {
                const speed = this.isReturningHome ? this.config.slowWalkSpeed : this.config.walkSpeed;
                dir.normalize().multiplyScalar(speed);
                velocity.copy(dir);
                // Compute target rotation to face movement direction
                targetRotation = new THREE.Quaternion().setFromUnitVectors(
                    new THREE.Vector3(0, 0, -1), dir.clone().normalize()
                );
            }
        } else if (homeDriftForce.length() > 0.01) {
            // Gentle home drift — no walking animation, just smooth slide
            velocity.copy(homeDriftForce.multiplyScalar(delta * 0.5));
            this.isWalking = false;
        } else {
            this.isWalking = false;
        }

        this.isWalking = velocity.length() > 0.05;

        // ── Face user when idle ──
        if (!this.moveTarget && !this.isWalking && cameraPosition) {
            const toCamera = new THREE.Vector3().subVectors(cameraPosition, currentPosition);
            toCamera.y = 0;
            if (toCamera.lengthSq() > 0.04) {
                toCamera.normalize();
                targetRotation = new THREE.Quaternion().setFromUnitVectors(
                    new THREE.Vector3(0, 0, -1), toCamera
                );
            }
        }

        return { velocity, targetRotation, animationCategory, microGesture };
    }

    // ─── Drive Dynamics ──────────────────────────────────────────────

    private updateDrives(delta: number) {
        const cfg = this.config;

        // Curiosity: gently drifts toward baseline
        this.drives.curiosity += (cfg.curiosityBaseline - this.drives.curiosity) * delta * 0.1;
        this.drives.curiosity += this.awareness.timeSinceLastInteraction * 0.003 * delta;
        this.drives.curiosity = THREE.MathUtils.clamp(this.drives.curiosity, 0, 1);

        // Social: slowly rises
        this.drives.social += cfg.socialNeedRate * delta;
        this.drives.social = Math.min(1.0, this.drives.social);

        // Restlessness: VERY slow rise only after long stillness
        if (this.awareness.timeSinceLastMove > cfg.restlessnessThreshold) {
            this.drives.restlessness += delta * 0.006;  // Very slow rise
        } else {
            this.drives.restlessness -= delta * 0.1;  // Fast decay — she likes being still
        }
        this.drives.restlessness = THREE.MathUtils.clamp(this.drives.restlessness, 0, 1);

        // Expressiveness: emotional states fuel it
        if (['happy', 'excited', 'curious', 'angry'].includes(this.emotionalState)) {
            this.drives.expressiveness += delta * 0.05;
        } else {
            this.drives.expressiveness -= cfg.expressivenessDecay * delta;
        }
        this.drives.expressiveness = THREE.MathUtils.clamp(this.drives.expressiveness, 0, 1);

        // Energy: drained by movement, restored by rest
        if (this.isWalking || this.behaviorState === 'wander_nearby') {
            this.drives.energy -= cfg.energyDrainRate * delta;
        } else {
            this.drives.energy += cfg.energyRecoveryRate * delta;
        }
        this.drives.energy = THREE.MathUtils.clamp(this.drives.energy, 0.1, 1.0);
    }

    // ─── Decision Engine (Autonomous household presence) ──────────
    // Called from update() when autonomousMode is enabled and the LLM
    // hasn't sent a movement command recently. Produces gentle, natural
    // behaviors: micro-gestures, curious steps, short wanders, rest.

    private makeDecision(_cameraPosition?: THREE.Vector3): {
        animation?: string;
        gesture?: string;
        newState?: BehaviorState;
    } {
        const cfg = this.config;

        if (this.intentionalGoal && Date.now() < this.intentionalExpiry) {
            return {};
        }

        // ── Spontaneity: rare micro-gesture without state change ──
        if (Math.random() < cfg.spontaneity) {
            const gestures = IDLE_GESTURES;
            return { gesture: gestures[Math.floor(Math.random() * gestures.length)] };
        }

        // ── Home check: if far from home and not moving, drift back ──
        // (This is handled in update() as home drift, but we can also
        //  trigger a conscious "return home" walk)

        // ── Rank priorities: Social > Express > Rest > Explore > Move ──
        const urgencies: Record<string, number> = {
            social:    this.drives.social * this.drives.energy * 1.5,
            express:   this.drives.expressiveness * this.drives.energy * 1.2,
            rest:      (1 - this.drives.energy) * 1.3,
            explore:   this.drives.curiosity * this.drives.energy * 0.5,  // Low — rare
            move:      this.drives.restlessness * this.drives.energy * 0.3,  // Very low
        };

        // Strong emotion overrides
        if (['happy', 'excited', 'sad', 'angry'].includes(this.emotionalState) &&
            this.awareness.timeInSameEmotion < 8) {
            urgencies.express *= 2.0;
        }

        // Find highest priority
        let maxUrgency = 0;
        let action = 'idle';
        for (const [key, value] of Object.entries(urgencies)) {
            if (value > maxUrgency) { maxUrgency = value; action = key; }
        }

        switch (action) {
            case 'social': {
                this.drives.social *= 0.3;
                this.transitionTo('social_turn');
                return { gesture: 'nod' };
            }
            case 'express': {
                const exprs = ['happy', 'curious', 'thinking', 'surprised'];
                const emotion = exprs[Math.floor(Math.random() * exprs.length)];
                this.drives.expressiveness *= 0.4;
                this.awareness.timeInSameEmotion = 0;
                this.transitionTo('emotional_burst');
                return { animation: EMOTION_ANIM_MAP[emotion] || 'Idle' };
            }
            case 'explore': {
                // Short, purposeful step — not far
                const angle = Math.random() * Math.PI * 2;
                const dist = 0.5 + Math.random() * cfg.preferredStepDistance;
                const target = new THREE.Vector3(
                    this.homePosition.x + Math.cos(angle) * dist,
                    this.homePosition.y,
                    this.homePosition.z + Math.sin(angle) * dist
                );
                this.moveTarget = target;
                this.isReturningHome = false;
                this.drives.curiosity *= 0.5;
                this.awareness.timeSinceLastMove = 0;
                this.transitionTo('curious_step');
                return { animation: 'Walk' };
            }
            case 'move': {
                // Very short wander — always returns home after
                const angle = Math.random() * Math.PI * 2;
                const dist = 0.5 + Math.random() * 1.0;  // Short: 0.5-1.5m
                const target = new THREE.Vector3(
                    this.homePosition.x + Math.cos(angle) * dist,
                    this.homePosition.y,
                    this.homePosition.z + Math.sin(angle) * dist
                );
                this.moveTarget = target;
                this.isReturningHome = false;
                this.drives.restlessness *= 0.3;
                this.awareness.timeSinceLastMove = 0;
                this.transitionTo('wander_nearby');
                return { animation: 'Walk' };
            }
            case 'rest':
                this.transitionTo('resting');
                return { gesture: 'tilt', animation: 'Idle' };
            default:
                // Calm idle — most of the time
                if (Math.random() > 0.7) {
                    return { gesture: IDLE_GESTURES[Math.floor(Math.random() * IDLE_GESTURES.length)] };
                }
                this.transitionTo('calm_idle');
                return {};
        }
    }

    // ─── State Transitions ────────────────────────────────────────────

    private lastLoggedState: BehaviorState = 'calm_idle';
    private stateLogCount: number = 0;
    private static MAX_STATE_LOG_REPEAT = 3;

    private transitionTo(newState: BehaviorState) {
        if (this.behaviorState === newState) return;
        const oldState = this.behaviorState;
        this.behaviorState = newState;
        this.awareness.timeInCurrentState = 0;
        
        // Deduplicate: only log state transitions that are meaningful changes
        // Skip logging rapid repeated transitions between the same states
        if (newState === this.lastLoggedState) {
            this.stateLogCount++;
            if (this.stateLogCount > MovementEngine.MAX_STATE_LOG_REPEAT) {
                this.onLog?.(`🔄 MovementEngine: ${oldState} → ${newState}`, 'var(--neon-blue)');
                this.stateLogCount = 0;
            }
        } else {
            this.stateLogCount = 0;
            this.onLog?.(`🔄 MovementEngine: ${oldState} → ${newState}`, 'var(--neon-blue)');
            this.lastLoggedState = newState;
        }

        // Schedule return home after wander states
        if (newState === 'wander_nearby' || newState === 'curious_step') {
            setTimeout(() => {
                if (this.behaviorState === 'wander_nearby' || this.behaviorState === 'curious_step') {
                    this.startReturnHome();
                }
            }, this.config.returnHomeDelay * 1000);
        }
    }

    private startReturnHome() {
        if (this.moveTarget) return; // Already moving
        this.moveTarget = this.homePosition.clone();
        this.isReturningHome = true;
        this.transitionTo('returning_home');
    }

    // ─── Diagnostic Status ────────────────────────────────────────────

    public getStatus() {
        return {
            state: this.behaviorState,
            emotionalState: this.emotionalState,
            emotionalIntensity: this._emotionalIntensity,
            drives: { ...this.drives },
            awareness: { ...this.awareness },
            isWalking: this.isWalking,
            isReturningHome: this.isReturningHome,
            hasMoveTarget: this.moveTarget !== null,
            config: { ...this.config },
        };
    }

    // ─── Config hot-reload ─────────────────────────────────────────────

    public updateConfig(partial: Partial<MovementConfig>) {
        this.config = { ...this.config, ...partial };
    }

    public getConfig(): MovementConfig { return { ...this.config }; }

    private dispatchArrivalFeedback() {
        const feedback = {
            type: 'body_state',
            event: 'arrival',
            arrived: true,
            currentPosition: this.homePosition.clone(),
            isWalking: false,
            emotionalState: this.emotionalState,
            message: `Successfully arrived at intended destination.`,
            drives: { ...this.drives }
        };
        window.dispatchEvent(new CustomEvent('foveai_body_feedback', { detail: feedback }));
        this.onLog?.('🎯 Navigation Target Reached (Feedback sent to Brain).', 'var(--neon-green)');
    }

    private dispatchFailureFeedback(reason: string) {
        const feedback = {
            type: 'body_state',
            event: 'arrival',
            arrived: false,
            currentPosition: this.homePosition.clone(),
            isWalking: false,
            emotionalState: this.emotionalState,
            message: `Failed to arrive at intended destination: ${reason}`,
            drives: { ...this.drives }
        };
        window.dispatchEvent(new CustomEvent('foveai_body_feedback', { detail: feedback }));
        this.onLog?.('⚠️ Navigation Failed (Feedback sent to Brain).', '#ffaa00');
    }
}