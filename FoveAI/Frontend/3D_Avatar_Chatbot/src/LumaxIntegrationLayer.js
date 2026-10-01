/**
 * ═══════════════════════════════════════════════════════════════════════
 * FoveAI INTEGRATION LAYER — Ported from XR_Vessel MovementEngine + AvatarManager
 * ═══════════════════════════════════════════════════════════════════════
 *
 * This layer bridges the 3D_Avatar_Chatbot frontend with the full FoveAI
 * backend ecosystem: Motor Cortex, Soul Core, Memory, and the autonomous
 * agent loop. It ports the MovementEngine, behavior state machine, micro-
 * gesture system, and emotional expression engine from XR_Vessel.
 *
 * INTEGRATION POINTS:
 *   - Motor Cortex (port 8110): SSE stream for walk, emotion, gesture
 *   - Soul Core (port 8000): /compagent/stream for cognitive loop
 *   - Memory (port 8002): Persistent memory via Stardust
 *   - TokenSlayer (port 8103): Context compression
 *   - XR_Vessel API (port 8101): Legacy API proxy
 *
 * BEHAVIOR STATES (ported from XR_Vessel MovementEngine):
 *   - CALM_IDLE:      Default. Breathing, micro-gestures, head tracking
 *   - SOCIAL_TURN:    Turning toward user. Warm attention.
 *   - CURIOUS_STEP:   1-2 short steps toward something interesting
 *   - WANDER_NEARBY:  Short walk nearby, then return home
 *   - EMOTIONAL_BURST: Animation triggered by AI emotion output
 *   - RETURNING_HOME: Smooth walk back to home position
 *   - RESTING:        Deep idle, very minimal motion
 *
 * ═══════════════════════════════════════════════════════════════════════
 */

(function () {
    'use strict';

    // ─── Constants ────────────────────────────────────────────────────
    const MOTOR_CORTEX_URL = '/api/proxy/8110';
    const SOUL_CORE_URL = '/api/proxy/8000';
    const MEMORY_URL = '/api/proxy/8002';
    const NEXUS_PROXY_URL = ''; // Same-origin (served by nexus-proxy on port 8080)

    // ─── Behavior States ────────────────────────────────────────────────
    const BEHAVIOR_STATES = {
        CALM_IDLE: 'calm_idle',
        SOCIAL_TURN: 'social_turn',
        CURIOUS_STEP: 'curious_step',
        WANDER_NEARBY: 'wander_nearby',
        EMOTIONAL_BURST: 'emotional_burst',
        RETURNING_HOME: 'returning_home',
        RESTING: 'resting',
        // ── 4-State System (ported from XR_Vessel) ──
        DEEP_IDLE: 'deep_idle',
        SLOW_BURN: 'slow_burn',
        DREAMING: 'dreaming'
    };

    // ─── Emotion → VRM Expression Map ─────────────────────────────────
    const EMOTION_VRM_MAP = {
        'joy': 'happy',
        'happy': 'happy',
        'anger': 'angry',
        'angry': 'angry',
        'sorrow': 'sad',
        'sad': 'sad',
        'fun': 'relaxed',
        'relaxed': 'relaxed',
        'surprise': 'surprised',
        'surprised': 'surprised',
        'neutral': 'neutral',
        'love': 'happy',
        'excited': 'happy',
        'tired': 'relaxed',
        'confused': 'surprised',
        'thinking': 'neutral'
    };

    // ─── Micro-Gesture Registry ────────────────────────────────────────
    const MICRO_GESTURES = {
        IDLE: ['nod', 'tilt', 'look_away', 'blink', 'breath_shift', 'weight_shift'],
        SOCIAL: ['nod', 'tilt', 'smile', 'eyebrow_raise'],
        CURIOUS: ['double_take', 'look_away', 'tilt', 'lean_forward'],
        EMPHATIC: ['head_shake', 'shoulder_shrug', 'hand_gesture', 'point']
    };

    // ─── Default Movement Config ───────────────────────────────────────
    const DEFAULT_MOVEMENT_CONFIG = {
        walkSpeed: 1.0,
        slowWalkSpeed: 0.6,
        turnSpeed: 2.0,
        maxWanderDistance: 3.0,
        preferredStepDistance: 0.8,
        approachDistance: 1.2,
        returnHomeDelay: 8.0,
        minStateDuration: 3.0,
        decisionInterval: 4.0,
        idleMicroGestureChance: 0.3,
        idleBreathVariation: 0.15,
        idleSwayAmount: 0.02,
        homeDriftStrength: 0.3,
        homeDriftThreshold: 1.5,
        curiosityBaseline: 0.2,
        restlessnessThreshold: 15.0,
        socialNeedRate: 0.02,
        spontaneity: 0.05,
        expressivenessDecay: 0.01,
        energyRecoveryRate: 0.05,
        energyDrainRate: 0.1,
        // ── 4-State System config ──
        deepIdleBreathRate: 0.001,
        slowBurnEmotionBuildRate: 0.02,
        dreamStateInterval: 8.0,
        dreamStateDuration: 20.0,
        slowBurnDuration: 15.0,
        deepIdleDuration: 12.0,
        // ── Bracket Token config ──
        soundboardContextRefresh: 120,
        bracketTokenInjection: true
    };

    // ─── LumaxIntegrationLayer ────────────────────────────────────────
    class LumaxIntegrationLayer {
        constructor() {
            this.initialized = false;
            this.avatarRoot = null;
            this.vrm = null;
            this.mixer = null;
            this.homePosition = new THREE.Vector3(0, 0, 0);
            this.currentPosition = new THREE.Vector3(0, 0, 0);
            this.currentRotation = 0;

            // Behavior state
            this.behaviorState = BEHAVIOR_STATES.CALM_IDLE;
            this.stateTimer = 0;
            this.intentionalGoal = null;
            this.intentionalExpiry = 0;
            this.moveTarget = null;
            this.isWalking = false;
            this.isTurning = false;
            this.turnTarget = 0;
            this.walkVelocity = new THREE.Vector3(0, 0, 0);

            // Drives — these are the avatar's internal motivations
            this.drives = {
                curiosity: 0.3,       // Desire to explore
                restlessness: 0.1,    // Buildup when idle too long
                socialNeed: 0.5,      // Desire for interaction
                energy: 1.0,          // Depletes with activity, recovers at rest
                expressiveness: 0.5   // Urge to emote/gesture
            };

            // Emotional state
            this.currentEmotion = 'neutral';
            this.emotionIntensity = 0.5;
            this.emotionTimer = 0;

            // Micro-gesture queue
            this.microGestureQueue = [];
            this.currentGesture = null;
            this.gestureTimer = 0;

            // Autonomous decision system
            this.decisionTimer = 0;
            this.cognitiveTickTimer = 0;
            this.cognitiveTickInterval = 45; // seconds between background thoughts
            this.autonomousEnabled = true;
            this.gestureFrequency = 0.5;
            this.wanderRadius = 2.0;

            // ── 4-State System ──
            this.fourStateTimer = 0;
            this.fourStateMode = 'idle';
            this.fourStateCycleInterval = 30;
            this.slowBurnEmotion = null;
            this.slowBurnIntensity = 0;
            this.dreamStateGestureTimer = 0;

            // ── Bracket Token System ──
            this.bracketTokenContext = '';
            this.soundboardContextTimer = 0;
            this.soundboardTags = [];

            // Config
            this.config = { ...DEFAULT_MOVEMENT_CONFIG };

            // Backend connections
            this.motorEventSource = null;
            this.motorConnected = false;
            this.soulConnected = false;

            // Callbacks
            this.onStateChange = null;
            this.onEmotionChange = null;
            this.onGesture = null;
            this.onWalk = null;
            this.onArrival = null;
            this.onFeedback = null;

            // Expose globally
            window.FoveAI_INTEGRATION = this;
            console.log('[LumaxIntegration] Layer created');
        }

        // ─── Initialization ────────────────────────────────────────────

        /**
         * Initialize the integration layer with the avatar's Three.js objects.
         * @param {THREE.Object3D} avatarRoot - The avatar's root scene object
         * @param {VRM} vrm - The VRM instance (from @pixiv/three-vrm)
         * @param {THREE.AnimationMixer} mixer - The animation mixer
         */
        init(avatarRoot, vrm, mixer) {
            this.avatarRoot = avatarRoot;
            this.vrm = vrm;
            this.mixer = mixer;

            if (avatarRoot) {
                this.homePosition.copy(avatarRoot.position);
                this.currentPosition.copy(avatarRoot.position);
                // Sync rotation to prevent initial snap when _turnToward() is called
                this.currentRotation = avatarRoot.rotation.y || 0;
            }

            this.initialized = true;
            console.log('[LumaxIntegration] Initialized with avatar:', !!avatarRoot, !!vrm);

            // Connect to motor cortex
            this.connectMotorCortex();

            // Fetch soundboard context for bracket token injection
            this._fetchSoundboardContext();

            // Dispatch ready event
            window.dispatchEvent(new CustomEvent('foveai_integration_ready', {
                detail: { layer: this }
            }));
        }

        // ─── Motor Cortex Connection ───────────────────────────────────

        connectMotorCortex() {
            if (this.motorEventSource) {
                this.motorEventSource.close();
            }

            const url = `${MOTOR_CORTEX_URL}/motor/subscribe`;
            console.log('[LumaxIntegration] Connecting to Motor Cortex:', url);

            try {
                this.motorEventSource = new EventSource(url);

                this.motorEventSource.onopen = () => {
                    console.log('[LumaxIntegration] Motor Cortex connected');
                    this.motorConnected = true;
                    this._dispatchFeedback('motor_connected', {});
                };

                this.motorEventSource.addEventListener('walk_to_target', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this._handleMotorWalk(data);
                    } catch (e) {
                        console.error('[LumaxIntegration] Failed to parse walk event:', e);
                    }
                });

                this.motorEventSource.addEventListener('change_emotion', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this._handleMotorEmotion(data);
                    } catch (e) {
                        console.error('[LumaxIntegration] Failed to parse emotion event:', e);
                    }
                });

                this.motorEventSource.addEventListener('trigger_micro_gesture', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this._handleMotorGesture(data);
                    } catch (e) {
                        console.error('[LumaxIntegration] Failed to parse gesture event:', e);
                    }
                });

                this.motorEventSource.addEventListener('walk_forward', (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this._handleMotorWalkForward(data);
                    } catch (e) {
                        console.error('[LumaxIntegration] Failed to parse walk_forward event:', e);
                    }
                });

                this.motorEventSource.onerror = (err) => {
                    console.warn('[LumaxIntegration] Motor Cortex SSE error, reconnecting in 5s...');
                    this.motorConnected = false;
                    this.motorEventSource.close();
                    setTimeout(() => this.connectMotorCortex(), 5000);
                };
            } catch (e) {
                console.warn('[LumaxIntegration] Failed to connect Motor Cortex:', e.message);
                setTimeout(() => this.connectMotorCortex(), 10000);
            }
        }

        // ─── Motor Event Handlers ──────────────────────────────────────

        _handleMotorWalk(data) {
            const target = data.target || 'user';
            const distance = data.distance || 1.0;
            console.log(`[LumaxIntegration] Motor walk: target=${target}, distance=${distance}`);

            if (target === 'user' || target === 'player') {
                // Walk toward user - use camera position as proxy
                const camera = window.NEXUS_VIEWER?.camera;
                if (camera) {
                    const dir = new THREE.Vector3();
                    camera.getWorldDirection(dir);
                    dir.y = 0;
                    dir.normalize();
                    const targetPos = camera.position.clone().add(dir.clone().multiplyScalar(-distance));
                    this.commandMoveTo(targetPos);
                }
            } else if (target === 'home') {
                this.commandReturnHome();
            } else {
                // Try to parse as coordinates
                const coords = target.split(',').map(Number);
                if (coords.length >= 2 && !isNaN(coords[0]) && !isNaN(coords[1])) {
                    this.commandMoveTo(new THREE.Vector3(coords[0], 0, coords[1]));
                }
            }
        }

        _handleMotorEmotion(data) {
            const emotion = data.emotion || data.name || 'neutral';
            const intensity = data.intensity || 1.0;
            console.log(`[LumaxIntegration] Motor emotion: ${emotion} (${intensity})`);
            this.setEmotion(emotion, intensity);
        }

        _handleMotorGesture(data) {
            const gesture = data.gesture || data.name || 'nod';
            console.log(`[LumaxIntegration] Motor gesture: ${gesture}`);
            this.queueMicroGesture(gesture);
        }

        _handleMotorWalkForward(data) {
            const distance = data.distance || 0.5;
            console.log(`[LumaxIntegration] Motor walk forward: ${distance}m`);
            const forward = new THREE.Vector3(0, 0, -distance);
            forward.applyAxisAngle(new THREE.Vector3(0, 1, 0), this.currentRotation);
            const targetPos = this.currentPosition.clone().add(forward);
            this.commandMoveTo(targetPos);
        }

        // ─── Movement Commands ────────────────────────────────────────

        /**
         * Command the avatar to move to a specific position.
         * @param {THREE.Vector3} target - Target world position
         */
        commandMoveTo(target) {
            if (!this.avatarRoot) return;

            this.intentionalGoal = target.clone();
            this.intentionalExpiry = Date.now() + 10000; // 10s TTL
            this.moveTarget = target.clone();
            this.isWalking = true;
            this.transitionTo(BEHAVIOR_STATES.WANDER_NEARBY);

            console.log(`[LumaxIntegration] Command move to: (${target.x.toFixed(2)}, ${target.z.toFixed(2)})`);

            if (this.onWalk) {
                this.onWalk(target);
            }
        }

        /**
         * Command the avatar to return to home position.
         */
        commandReturnHome() {
            if (!this.avatarRoot) return;
            this.commandMoveTo(this.homePosition);
            this.transitionTo(BEHAVIOR_STATES.RETURNING_HOME);
        }

        /**
         * Walk forward a specific distance in the avatar's facing direction.
         * @param {number} distance - Distance in meters
         */
        commandWalkForward(distance) {
            if (!this.avatarRoot) return;
            const forward = new THREE.Vector3(0, 0, -distance);
            forward.applyAxisAngle(new THREE.Vector3(0, 1, 0), this.currentRotation);
            const targetPos = this.currentPosition.clone().add(forward);
            this.commandMoveTo(targetPos);
        }

        /**
         * Set the home position (where the avatar returns to when idle).
         * @param {THREE.Vector3} position
         */
        setHomePosition(position) {
            this.homePosition.copy(position);
        }

        // ─── Emotion System ──────────────────────────────────────────

        /**
         * Set the avatar's emotional state.
         * @param {string} emotion - Emotion name (joy, anger, sad, etc.)
         * @param {number} intensity - 0.0 to 1.0
         */
        setEmotion(emotion, intensity = 1.0) {
            intensity = Math.max(0, Math.min(1, intensity));
            
            // Prevent frame-loop spam during gradual transitions (e.g. slow_burn)
            if (this.currentEmotion === emotion && Math.abs((this.emotionIntensity || 0) - intensity) < 0.01) {
                this.emotionTimer = 5.0; // Keep alive but skip re-applying
                return;
            }
            
            this.currentEmotion = emotion;
            this.emotionIntensity = intensity;
            this.emotionTimer = 5.0; // Hold for 5 seconds

            // Map to VRM expression
            const vrmEmotion = EMOTION_VRM_MAP[emotion.toLowerCase()] || 'neutral';

            // Apply via VRM if available
            if (this.vrm && this.vrm.expressionManager) {
                // Clear all expressions first
                const allExpressions = Object.values(EMOTION_VRM_MAP);
                allExpressions.forEach(exp => {
                    try {
                        this.vrm.expressionManager.setValue(exp, 0);
                    } catch (e) { /* ignore */ }
                });
                // Set the target expression
                try {
                    this.vrm.expressionManager.setValue(vrmEmotion, this.emotionIntensity);
                } catch (e) {
                    console.warn('[LumaxIntegration] Failed to set VRM expression:', e);
                }
            }

            // Fallback: use NEXUS_VIEWER's vrmLoader
            if (!this.vrm && window.NEXUS_VIEWER?.avatarManager?.vrmLoader) {
                const loader = window.NEXUS_VIEWER.avatarManager.vrmLoader;
                if (typeof loader.setExpression === 'function') {
                    ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral'].forEach(emo =>
                        loader.setExpression(emo, 0)
                    );
                    loader.setExpression(vrmEmotion, this.emotionIntensity);
                }
            }

            // Dispatch event
            window.dispatchEvent(new CustomEvent('foveai_emotion_changed', {
                detail: { emotion, intensity, vrmEmotion }
            }));

            if (this.onEmotionChange) {
                this.onEmotionChange(emotion, intensity);
            }

            console.log(`[LumaxIntegration] Emotion set: ${emotion} (${intensity}) → ${vrmEmotion}`);
        }

        // ─── Micro-Gesture System ─────────────────────────────────────

        /**
         * Queue a micro-gesture to be played.
         * @param {string} gesture - Gesture name (nod, tilt, wave, etc.)
         */
        queueMicroGesture(gesture) {
            this.microGestureQueue.push({
                type: gesture,
                duration: 1.0
            });
            console.log(`[LumaxIntegration] Queued gesture: ${gesture}`);
        }

        /**
         * Get a random gesture from a category.
         * @param {string} category - IDLE, SOCIAL, CURIOUS, or EMPHATIC
         * @returns {string} Gesture name
         */
        _getRandomGesture(category = 'IDLE') {
            const pool = MICRO_GESTURES[category] || MICRO_GESTURES.IDLE;
            return pool[Math.floor(Math.random() * pool.length)];
        }

        // ─── Behavior State Machine ───────────────────────────────────

        /**
         * Transition to a new behavior state.
         * @param {string} newState - One of BEHAVIOR_STATES values
         */
        transitionTo(newState) {
            if (this.behaviorState === newState) return;
            const oldState = this.behaviorState;
            this.behaviorState = newState;
            this.stateTimer = 0;

            console.log(`[LumaxIntegration] State: ${oldState} → ${newState}`);

            window.dispatchEvent(new CustomEvent('foveai_state_changed', {
                detail: { from: oldState, to: newState }
            }));

            if (this.onStateChange) {
                this.onStateChange(newState, oldState);
            }
        }

        // ─── Update Loop ──────────────────────────────────────────────

        /**
         * Main update loop - call every frame from the render loop.
         * @param {number} delta - Time since last frame in seconds
         * @param {THREE.Camera} camera - The active camera (for user position)
         */
        update(delta, camera) {
            if (!this.initialized || !this.avatarRoot) return;

            this.stateTimer += delta;
            this.emotionTimer = Math.max(0, this.emotionTimer - delta);

            // Update drives
            this._updateDrives(delta);

            // Check intentional goal expiry
            if (this.intentionalGoal && Date.now() > this.intentionalExpiry) {
                console.log('[LumaxIntegration] Intentional goal expired');
                this.intentionalGoal = null;
                this.moveTarget = null;
                this.isWalking = false;
                this.transitionTo(BEHAVIOR_STATES.CALM_IDLE);
                this._dispatchFeedback('movement_timeout', { reason: 'goal_expired' });
            }

            // ── 4-State System ──
            // Cycles through idle → slow_burn → dream modes
            this._updateFourStateSystem(delta);

            // ── Bracket Token Refresh ──
            // Periodically refresh soundboard context for system prompt injection
            this.soundboardContextTimer += delta;
            if (this.soundboardContextTimer >= this.config.soundboardContextRefresh) {
                this.soundboardContextTimer = 0;
                this._fetchSoundboardContext();
            }

            // ── AUTONOMOUS DECISION SYSTEM ──
            // Makes her move, gesture, and express emotions on her own
            if (this.autonomousEnabled) {
                this._autonomousDecision(delta, camera);
                this._backgroundCognitiveTick();
            }

            // Update movement
            this._updateMovement(delta);

            // Update micro-gestures
            this._updateMicroGestures(delta);

            // Update procedural idle
            this._updateProceduralIdle(delta, camera);

            // Update VRM physics
            if (this.vrm && this.vrm.update) {
                this.vrm.update(delta);
            }
        }

        /**
         * Autonomous decision system — drives behavior based on internal state.
         * Called every frame, but only acts at config.decisionInterval intervals.
         * This is what makes her feel alive — she decides what to do on her own.
         * @param {number} delta - Frame delta
         * @param {THREE.Camera} camera - Active camera
         */
        _autonomousDecision(delta, camera) {
            this.decisionTimer += delta;
            if (this.decisionTimer < this.config.decisionInterval) return;
            this.decisionTimer = 0;

            // Don't override active commands
            if (this.isWalking || this.isTurning) return;

            // ── Drive-based state transitions ──
            // Restlessness → wander
            if (this.drives.restlessness > 0.7 && this.drives.energy > 0.3) {
                this.transitionTo(BEHAVIOR_STATES.WANDER_NEARBY);
                this._pickRandomWanderTarget();
                this._dispatchFeedback('autonomous_decision', { reason: 'restlessness', drive: this.drives.restlessness });
                return;
            }

            // Low social need → turn toward user
            if (this.drives.socialNeed < 0.3 && camera) {
                this.transitionTo(BEHAVIOR_STATES.SOCIAL_TURN);
                this._turnToward(camera.position);
                this._dispatchFeedback('autonomous_decision', { reason: 'social_need', drive: this.drives.socialNeed });
                return;
            }

            // High expressiveness → emotional burst
            if (this.drives.expressiveness > 0.6 && this.drives.energy > 0.5) {
                this.transitionTo(BEHAVIOR_STATES.EMOTIONAL_BURST);
                const emotions = ['happy', 'joy', 'love', 'excited', 'fun'];
                const randomEmotion = emotions[Math.floor(Math.random() * emotions.length)];
                this.setEmotion(randomEmotion, 0.8);
                this.queueMicroGesture(this._getRandomGesture('EMPHATIC'));
                this.drives.expressiveness = 0.2; // Reset after burst
                this._dispatchFeedback('autonomous_decision', { reason: 'expressiveness', emotion: randomEmotion });
                return;
            }

            // High curiosity → curious step
            if (this.drives.curiosity > 0.6 && this.drives.energy > 0.4) {
                this.transitionTo(BEHAVIOR_STATES.CURIOUS_STEP);
                this._pickRandomWanderTarget(0.5); // Short step
                this.queueMicroGesture(this._getRandomGesture('CURIOUS'));
                this.drives.curiosity = 0.2;
                this._dispatchFeedback('autonomous_decision', { reason: 'curiosity', drive: this.drives.curiosity });
                return;
            }

            // Low energy → rest
            if (this.drives.energy < 0.2) {
                this.transitionTo(BEHAVIOR_STATES.RESTING);
                this._dispatchFeedback('autonomous_decision', { reason: 'low_energy', drive: this.drives.energy });
                return;
            }

            // ── Spontaneous micro-gestures ──
            // Even in idle, she'll randomly nod, tilt, blink
            if (Math.random() < this.config.spontaneity * this.gestureFrequency) {
                const gesture = this._getRandomGesture('IDLE');
                this.queueMicroGesture(gesture);
            }

            // ── Spontaneous emotion flickers ──
            // Brief emotional expressions that pass quickly
            if (Math.random() < 0.1 && this.currentEmotion === 'neutral') {
                const flickerEmotions = ['happy', 'thinking', 'surprised'];
                const flicker = flickerEmotions[Math.floor(Math.random() * flickerEmotions.length)];
                this.setEmotion(flicker, 0.3);
                // Will decay back to neutral via emotionTimer
            }

            // ── Return home if too far ──
            if (this.behaviorState === BEHAVIOR_STATES.CALM_IDLE || this.behaviorState === BEHAVIOR_STATES.RESTING) {
                const distToHome = this.currentPosition.distanceTo(this.homePosition);
                if (distToHome > this.config.homeDriftThreshold * 1.5) {
                    this.transitionTo(BEHAVIOR_STATES.RETURNING_HOME);
                    this.commandReturnHome();
                    this._dispatchFeedback('autonomous_decision', { reason: 'return_home', distance: distToHome });
                }
            }
        }

        /**
         * Pick a random wander target within wanderRadius of home.
         * @param {number} [radius] - Override radius, defaults to wanderRadius
         */
        _pickRandomWanderTarget(radius) {
            const r = radius || this.wanderRadius;
            const angle = Math.random() * Math.PI * 2;
            const distance = 0.5 + Math.random() * (r - 0.5);
            const target = new THREE.Vector3(
                this.homePosition.x + Math.cos(angle) * distance,
                0,
                this.homePosition.z + Math.sin(angle) * distance
            );
            this.commandMoveTo(target);
        }

        /**
         * Turn the avatar to face a target position with smooth interpolation.
         * Uses config.turnSpeed for smooth rotation instead of instant snap.
         * @param {THREE.Vector3} target - Position to face
         */
        _turnToward(target) {
            if (!this.avatarRoot) return;
            const dir = new THREE.Vector3();
            dir.copy(target).sub(this.currentPosition);
            dir.y = 0;
            if (dir.length() < 0.01) return;
            // Three.js default forward is -Z, but Math.atan2(x, z) gives angle from +Z.
            // Negate to convert: atan2(x, z) → -atan2(x, z) so 0 rad = facing -Z (forward).
            const targetRotation = -Math.atan2(dir.x, dir.z);
            
            // Smooth rotation using turnSpeed config
            let rotationDiff = targetRotation - this.currentRotation;
            while (rotationDiff > Math.PI) rotationDiff -= Math.PI * 2;
            while (rotationDiff < -Math.PI) rotationDiff += Math.PI * 2;
            
            // Use a fixed turn step (0.05 rad per call ~ 3 degrees) for smoothness
            const turnStep = Math.sign(rotationDiff) * Math.min(Math.abs(rotationDiff), 0.05);
            this.currentRotation += turnStep;
            this.avatarRoot.rotation.y = this.currentRotation;
        }

        /**
         * Background cognitive tick — periodically pings the Soul Core
         * for autonomous thoughts, making her feel like she has an inner life.
         * Runs every `cognitiveTickInterval` seconds.
         */
        _backgroundCognitiveTick() {
            this.cognitiveTickTimer += 0.016; // Approximate per-frame increment
            if (this.cognitiveTickTimer < this.cognitiveTickInterval) return;
            this.cognitiveTickTimer = 0;

            // Only tick if Soul Core is reachable
            if (!this.soulConnected) {
                // Check connectivity silently
                fetch(`${SOUL_CORE_URL}/health`, { signal: AbortSignal.timeout(2000) })
                    .then(r => { this.soulConnected = r.ok; })
                    .catch(() => { this.soulConnected = false; });
                return;
            }

            // Build a lightweight context for the background thought
            const context = {
                type: 'background_thought',
                state: this.behaviorState,
                emotion: this.currentEmotion,
                drives: { ...this.drives },
                timeAlive: Math.floor(this.stateTimer),
                position: {
                    x: this.currentPosition.x.toFixed(2),
                    z: this.currentPosition.z.toFixed(2)
                },
                homeDistance: this.currentPosition.distanceTo(this.homePosition).toFixed(2)
            };

            // Fire-and-forget — don't block the animation loop
            this.sendToSoul(JSON.stringify(context), {
                context: 'autonomous_background_tick',
                deepThought: false,
                privacyMode: true
            }).then(response => {
                if (!response) return;
                console.log('[LumaxIntegration] Background thought:', response.slice(0, 100));

                // Parse response for emotion/motor tags
                const emotionMatch = response.match(/\[emotion:(\w+)\]/);
                if (emotionMatch) {
                    this.setEmotion(emotionMatch[1], 0.6);
                }
                const gestureMatch = response.match(/\[gesture:(\w+)\]/);
                if (gestureMatch) {
                    this.queueMicroGesture(gestureMatch[1]);
                }
                const walkMatch = response.match(/\[walk\]/);
                if (walkMatch) {
                    this._pickRandomWanderTarget();
                }
            }).catch(() => {
                // Silently fail — Soul Core might be down
            });
        }

        _updateDrives(delta) {
            // Energy recovery when idle
            if (this.behaviorState === BEHAVIOR_STATES.CALM_IDLE || this.behaviorState === BEHAVIOR_STATES.RESTING) {
                this.drives.energy = Math.min(1.0, this.drives.energy + this.config.energyRecoveryRate * delta);
            }

            // Social need decay when alone
            this.drives.socialNeed = Math.max(0, this.drives.socialNeed - this.config.socialNeedRate * delta);

            // Expressiveness decay
            this.drives.expressiveness = Math.max(0, this.drives.expressiveness - this.config.expressivenessDecay * delta);

            // Restlessness builds when idle too long
            if (this.behaviorState === BEHAVIOR_STATES.CALM_IDLE && this.stateTimer > this.config.restlessnessThreshold) {
                this.drives.restlessness = Math.min(1.0, this.drives.restlessness + delta * 0.02);
            } else {
                this.drives.restlessness = Math.max(0, this.drives.restlessness - delta * 0.01);
            }
        }

        // ─── 4-State System (idle → slow_burn → dream) ────────────────

        /**
         * Update the 4-state system — cycles through idle, slow_burn, and dream modes.
         * Each mode affects the avatar's behavior, emotion, and micro-gesture patterns.
         * Ported from XR_Vessel's aliveness system.
         * @param {number} delta - Frame delta in seconds
         */
        _updateFourStateSystem(delta) {
            this.fourStateTimer += delta;

            // Cycle through modes at the configured interval
            if (this.fourStateTimer >= this.fourStateCycleInterval) {
                this.fourStateTimer = 0;
                const modes = ['idle', 'slow_burn', 'dream'];
                const currentIdx = modes.indexOf(this.fourStateMode);
                this.fourStateMode = modes[(currentIdx + 1) % modes.length];
                console.log(`[LumaxIntegration] 4-State mode: ${this.fourStateMode}`);
                window.dispatchEvent(new CustomEvent('foveai_four_state_changed', {
                    detail: { mode: this.fourStateMode }
                }));
            }

            // ── Mode-specific behavior ──
            switch (this.fourStateMode) {
                case 'idle':
                    // Default calm idle — handled by existing behavior state machine
                    // Subtle breathing variation
                    if (this.vrm && this.vrm.humanoid) {
                        try {
                            const breath = Math.sin(Date.now() * 0.002) * this.config.idleBreathVariation;
                            const spine = this.vrm.humanoid.getRawBoneNode('spine');
                            if (spine) {
                                spine.position.y = breath * 0.01;
                            }
                        } catch (e) { /* ignore */ }
                    }
                    break;

                case 'slow_burn':
                    // Low-energy simmer — emotion builds gradually
                    this.slowBurnIntensity = Math.min(1.0, this.slowBurnIntensity + this.config.slowBurnEmotionBuildRate * delta);

                    // Cycle through emotions as intensity builds
                    if (this.slowBurnIntensity > 0.3 && this.slowBurnIntensity < 0.6) {
                        this.slowBurnEmotion = 'thinking';
                        this.setEmotion('thinking', this.slowBurnIntensity * 0.5);
                    } else if (this.slowBurnIntensity >= 0.6 && this.slowBurnIntensity < 0.8) {
                        this.slowBurnEmotion = 'curious';
                        this.setEmotion('curious', this.slowBurnIntensity * 0.6);
                    } else if (this.slowBurnIntensity >= 0.8) {
                        this.slowBurnEmotion = 'surprised';
                        this.setEmotion('surprised', this.slowBurnIntensity * 0.4);
                    }

                    // Occasional micro-gestures during slow burn
                    if (Math.random() < 0.3 * delta) {
                        this.queueMicroGesture(this._getRandomGesture('CURIOUS'));
                    }
                    break;

                case 'dream':
                    // Dream-like state — random micro-gestures, emotional flickers, gaze shifts
                    this.dreamStateGestureTimer += delta;
                    if (this.dreamStateGestureTimer >= this.config.dreamStateInterval) {
                        this.dreamStateGestureTimer = 0;

                        // Random emotional flicker
                        const dreamEmotions = ['happy', 'surprised', 'thinking', 'neutral'];
                        const flicker = dreamEmotions[Math.floor(Math.random() * dreamEmotions.length)];
                        this.setEmotion(flicker, 0.3 + Math.random() * 0.4);

                        // Random micro-gesture
                        const dreamGestures = ['nod', 'tilt', 'look_away', 'blink', 'breath_shift'];
                        const gesture = dreamGestures[Math.floor(Math.random() * dreamGestures.length)];
                        this.queueMicroGesture(gesture);

                        // Random gaze shift (turn slightly) — smooth, not instant
                        if (Math.random() < 0.3) {
                            const randomAngle = (Math.random() - 0.5) * Math.PI * 0.5;
                            // Smoothly interpolate toward target rotation
                            const targetRot = this.currentRotation + randomAngle;
                            let diff = targetRot - this.currentRotation;
                            while (diff > Math.PI) diff -= Math.PI * 2;
                            while (diff < -Math.PI) diff += Math.PI * 2;
                            this.currentRotation += Math.sign(diff) * Math.min(Math.abs(diff), 0.03);
                            if (this.avatarRoot) {
                                this.avatarRoot.rotation.y = this.currentRotation;
                            }
                        }
                    }
                    break;
            }
        }

        // ─── Bracket Token System ─────────────────────────────────────

        /**
         * Fetch soundboard context from the Soul Core for bracket token injection.
         * This tells the AI what <audio:tag> and <flavour:tag> tokens are available.
         * Refreshes every `soundboardContextRefresh` seconds.
         */
        async _fetchSoundboardContext() {
            try {
                const response = await fetch('/api/soundboard/context', {
                    signal: AbortSignal.timeout(5000)
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                this.bracketTokenContext = data.context || '';
                this.soundboardTags = data.tags || [];
                console.log(`[LumaxIntegration] Soundboard context loaded: ${this.soundboardTags.length} tags`);
            } catch (e) {
                // Use default context as fallback
                this.bracketTokenContext = [
                    '=== SOUNDBOARD EXPRESSIONS ===',
                    'You have an expressive local soundboard and dynamic audio generation system.',
                    'Use bracket tokens in your responses to express emotion non-verbally:',
                    '  - Existing sounds: <audio:tag> or <flavour:tag>',
                    '  - Face blendshapes: <emotion:tag> (happy, sad, surprised, curious, content, neutral, angry, fearful)',
                    '  - Generate custom sound: <request:description>',
                    '',
                    'Available tags:',
                    '  gasp_subtle, laugh_soft, sigh_content, hmm_thoughtful,',
                    '  oh_realization, throat_clear, chuckle_warm, mhm_affirming'
                ].join('\n');
                this.soundboardTags = [
                    'gasp_subtle', 'laugh_soft', 'sigh_content', 'hmm_thoughtful',
                    'oh_realization', 'throat_clear', 'chuckle_warm', 'mhm_affirming'
                ];
                console.log('[LumaxIntegration] Using default soundboard context');
            }
        }

        /**
         * Inject bracket token context into a system prompt.
         * Call this before sending a message to the LLM to enable non-verbal expression.
         * @param {string} systemPrompt - The original system prompt
         * @returns {string} System prompt with bracket token context appended
         */
        injectBracketTokens(systemPrompt) {
            if (!this.config.bracketTokenInjection || !this.bracketTokenContext) {
                return systemPrompt;
            }
            return systemPrompt + '\n\n' + this.bracketTokenContext;
        }

        /**
         * Get the current bracket token context for system prompt injection.
         * @returns {string} Bracket token context text
         */
        getBracketTokenContext() {
            return this.bracketTokenContext;
        }

        /**
         * Get available soundboard tags.
         * @returns {string[]} Array of tag names
         */
        getSoundboardTags() {
            return [...this.soundboardTags];
        }

        /**
         * Get the current 4-state mode.
         * @returns {string} 'idle', 'slow_burn', or 'dream'
         */
        getFourStateMode() {
            return this.fourStateMode;
        }

        /**
         * Get the current slow burn intensity (0.0 to 1.0).
         * @returns {number}
         */
        getSlowBurnIntensity() {
            return this.slowBurnIntensity;
        }

        /**
         * Set the 4-state cycle interval.
         * @param {number} seconds - Interval in seconds between mode transitions
         */
        setFourStateCycleInterval(seconds) {
            this.fourStateCycleInterval = Math.max(5, Math.min(120, seconds));
        }

        /**
         * Manually set the 4-state mode.
         * @param {string} mode - 'idle', 'slow_burn', or 'dream'
         */
        setFourStateMode(mode) {
            if (['idle', 'slow_burn', 'dream'].includes(mode)) {
                this.fourStateMode = mode;
                this.fourStateTimer = 0;
                console.log(`[LumaxIntegration] 4-State mode manually set: ${mode}`);
                window.dispatchEvent(new CustomEvent('foveai_four_state_changed', {
                    detail: { mode }
                }));
            }
        }

        _updateMovement(delta) {
            if (!this.moveTarget || !this.isWalking) {
                // Home drift
                if (this.behaviorState !== BEHAVIOR_STATES.RETURNING_HOME) {
                    const distToHome = this.currentPosition.distanceTo(this.homePosition);
                    if (distToHome > this.config.homeDriftThreshold) {
                        const drift = this.homePosition.clone().sub(this.currentPosition).normalize();
                        drift.multiplyScalar(this.config.homeDriftStrength * delta * 0.5);
                        this.currentPosition.add(drift);
                    }
                }
                // Apply position
                if (this.avatarRoot) {
                    this.avatarRoot.position.copy(this.currentPosition);
                }
                return;
            }

            // Calculate direction to target
            const direction = new THREE.Vector3();
            direction.copy(this.moveTarget).sub(this.currentPosition);
            direction.y = 0;

            const distance = direction.length();

            if (distance < 0.2) {
                // Arrived
                this.isWalking = false;
                this.moveTarget = null;
                this.intentionalGoal = null;
                this.transitionTo(BEHAVIOR_STATES.CALM_IDLE);
                this._dispatchFeedback('movement_arrival', {
                    position: { x: this.currentPosition.x, z: this.currentPosition.z }
                });
                if (this.onArrival) {
                    this.onArrival(this.currentPosition);
                }
                return;
            }

            // Normalize direction
            direction.normalize();

            // Calculate target rotation
            // Three.js default forward is -Z, but Math.atan2(x, z) gives angle from +Z.
            // Negate to convert: atan2(x, z) → -atan2(x, z) so 0 rad = facing -Z (forward).
            const targetRotation = -Math.atan2(direction.x, direction.z);

            // Smooth rotation
            let rotationDiff = targetRotation - this.currentRotation;
            while (rotationDiff > Math.PI) rotationDiff -= Math.PI * 2;
            while (rotationDiff < -Math.PI) rotationDiff += Math.PI * 2;

            if (Math.abs(rotationDiff) > 0.1) {
                // Turning
                this.isTurning = true;
                const turnStep = this.config.turnSpeed * delta * Math.sign(rotationDiff);
                if (Math.abs(turnStep) > Math.abs(rotationDiff)) {
                    this.currentRotation = targetRotation;
                    this.isTurning = false;
                } else {
                    this.currentRotation += turnStep;
                }
            } else {
                this.isTurning = false;
                this.currentRotation = targetRotation;
            }

            // Move forward
            const speed = this.config.walkSpeed * delta;
            const moveStep = Math.min(speed, distance);
            this.currentPosition.x += direction.x * moveStep;
            this.currentPosition.z += direction.z * moveStep;

            // Apply to avatar
            if (this.avatarRoot) {
                this.avatarRoot.position.copy(this.currentPosition);
                this.avatarRoot.rotation.y = this.currentRotation;
            }

            // Drain energy while walking
            this.drives.energy = Math.max(0, this.drives.energy - this.config.energyDrainRate * delta);
        }

        _updateMicroGestures(delta) {
            // Process queue
            if (this.currentGesture) {
                this.gestureTimer -= delta;
                if (this.gestureTimer <= 0) {
                    this.currentGesture = null;
                    // Dispatch gesture end
                    window.dispatchEvent(new CustomEvent('foveai_gesture_end', {
                        detail: {}
                    }));
                }
                return;
            }

            if (this.microGestureQueue.length > 0) {
                this.currentGesture = this.microGestureQueue.shift();
                this.gestureTimer = this.currentGesture.duration || 1.0;

                // Dispatch gesture event for animation system
                window.dispatchEvent(new CustomEvent('foveai_gesture_start', {
                    detail: { gesture: this.currentGesture.type }
                }));

                if (this.onGesture) {
                    this.onGesture(this.currentGesture.type);
                }
                return;
            }

            // Random idle gestures
            if (this.behaviorState === BEHAVIOR_STATES.CALM_IDLE &&
                this.stateTimer > 3.0 &&
                Math.random() < this.config.idleMicroGestureChance * delta) {
                const gesture = this._getRandomGesture('IDLE');
                this.microGestureQueue.push({
                    type: gesture,
                    duration: 1.5
                });
            }
        }

        _updateProceduralIdle(delta, camera) {
            // ── DELEGATED TO PHASE 3 ANIMATION ENGINE ──
            // The Phase 3 system (ProceduralAnimator + BehaviorEngine) handles
            // all per-frame bone animation: breathing, head look, gaze, micro-
            // expressions, and behavior state transitions.
            //
            // This method previously called head.lookAt(camera.position) and
            // directly manipulated VRM bones, which fought with ProceduralAnimator
            // every frame (LumaxIntegrationLayer runs AFTER ProceduralAnimator
            // in the render loop, so it was overwriting Phase 3's work).
            //
            // LumaxIntegrationLayer now focuses on its actual responsibilities:
            //   - Behavior state machine (autonomous decisions)
            //   - Motor cortex commands (walk, emotion, gesture)
            //   - Movement (walking, turning, home drift)
            //   - Bracket token injection
            //   - 4-State system (idle → slow_burn → dream)
            //
            // The Phase 3 system has full autonomy over the avatar's animation.
            // To restore camera-locked head tracking, enable FaceTracker's
            // "Look at Camera" mode in the Tracking Settings panel.
            if (!this.avatarRoot || !this.vrm) return;
            // No-op: animation is handled by Phase 3 engine
        }

        // ─── Feedback & Events ───────────────────────────────────────

        _dispatchFeedback(type, data) {
            window.dispatchEvent(new CustomEvent('foveai_body_feedback', {
                detail: { type, data, timestamp: Date.now() }
            }));

            if (this.onFeedback) {
                this.onFeedback(type, data);
            }
        }

        // ─── Backend API Calls ────────────────────────────────────────

        /**
         * Send a message to the Soul Core (compagent).
         * @param {string} message - User message
         * @param {Object} options - Additional options
         * @returns {Promise<string>} Response text
         */
        async sendToSoul(message, options = {}) {
            try {
                const response = await fetch(`${SOUL_CORE_URL}/compagent`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        input: message,
                        context: options.context || '',
                        deepThought: options.deepThought || false,
                        privacyMode: options.privacyMode || false,
                        attachments: options.attachments || []
                    })
                });

                if (!response.ok) {
                    throw new Error(`Soul Core returned ${response.status}`);
                }

                const data = await response.json();
                return data.response || data.text || '';
            } catch (e) {
                console.error('[LumaxIntegration] Soul Core error:', e);
                return null;
            }
        }

        /**
         * Stream a message from the Soul Core via SSE.
         * @param {string} message - User message
         * @param {Function} onToken - Callback for each token
         * @param {Function} onMotor - Callback for motor actions
         * @param {Function} onDone - Callback when complete
         * @returns {Promise<void>}
         */
        async streamFromSoul(message, onToken, onMotor, onDone) {
            try {
                const response = await fetch(`${SOUL_CORE_URL}/compagent/stream`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ input: message })
                });
                if (!response.ok) {
                    throw new Error(`Soul stream returned ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'token' && data.text && onToken) {
                                    onToken(data.text);
                                } else if (data.type === 'motor' && data.action && onMotor) {
                                    onMotor(data.action, data.args || {});
                                } else if (data.type === 'done' && onDone) {
                                    onDone(data);
                                }
                            } catch (e) {
                                // Ignore parse errors for partial lines
                            }
                        }
                    }
                }

                if (onDone) onDone({ type: 'done' });
            } catch (e) {
                console.error('[LumaxIntegration] Soul stream error:', e);
                if (onDone) onDone({ type: 'error', error: e.message });
            }
        }

        /**
         * Store a memory via the Memory service.
         * @param {string} key - Memory key
         * @param {string} value - Memory value
         * @param {string} namespace - Memory namespace
         */
        async storeMemory(key, value, namespace = 'default') {
            try {
                await fetch(`${MEMORY_URL}/memory`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key, value, namespace })
                });
            } catch (e) {
                console.warn('[LumaxIntegration] Memory store failed:', e.message);
            }
        }

        /**
         * Retrieve a memory from the Memory service.
         * @param {string} key - Memory key
         * @param {string} namespace - Memory namespace
         * @returns {Promise<string|null>} Memory value
         */
        async retrieveMemory(key, namespace = 'default') {
            try {
                const response = await fetch(`${MEMORY_URL}/memory/${encodeURIComponent(key)}?namespace=${encodeURIComponent(namespace)}`);
                if (!response.ok) return null;
                const data = await response.json();
                return data.value || null;
            } catch (e) {
                console.warn('[LumaxIntegration] Memory retrieve failed:', e.message);
                return null;
            }
        }

        /**
         * Execute a motor action via the Motor Cortex.
         * @param {string} action - Action name (walk_to_target, change_emotion, etc.)
         * @param {Object} args - Action arguments
         */
        async executeMotorAction(action, args = {}) {
            try {
                await fetch(`${MOTOR_CORTEX_URL}/motor/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action, args })
                });
            } catch (e) {
                console.warn('[LumaxIntegration] Motor execute failed:', e.message);
            }
        }

        // ─── Configuration Setters ────────────────────────────────────

        /**
         * Set the emotion intensity multiplier.
         * @param {number} intensity - 0.0 to 1.0
         */
        setEmotionIntensity(intensity) {
            this.emotionIntensity = Math.max(0, Math.min(1, intensity));
        }

        /**
         * Set the gesture frequency multiplier.
         * @param {number} frequency - 0.0 to 1.0
         */
        setGestureFrequency(frequency) {
            this.gestureFrequency = Math.max(0, Math.min(1, frequency));
        }

        /**
         * Set the wander radius for autonomous movement.
         * @param {number} radius - Distance in meters
         */
        setWanderRadius(radius) {
            this.wanderRadius = Math.max(0.5, Math.min(10, radius));
        }

        /**
         * Enable or disable autonomous behavior.
         * @param {boolean} enabled
         */
        setAutonomousEnabled(enabled) {
            this.autonomousEnabled = enabled;
            console.log('[LumaxIntegration] Autonomous behavior:', enabled ? 'ENABLED' : 'DISABLED');
        }

        // ─── Configuration ────────────────────────────────────────────

        /**
         * Update the movement configuration.
         * @param {Partial<typeof DEFAULT_MOVEMENT_CONFIG>} partial
         */
        updateConfig(partial) {
            Object.assign(this.config, partial);
            console.log('[LumaxIntegration] Config updated:', partial);
        }

        /**
         * Get the current movement configuration.
         * @returns {Object}
         */
        getConfig() {
            return { ...this.config };
        }

        /**
         * Get the current behavior state.
         * @returns {string}
         */
        getState() {
            return this.behaviorState;
        }

        /**
         * Get the current drives.
         * @returns {Object}
         */
        getDrives() {
            return { ...this.drives };
        }

        /**
         * Check if the avatar is currently moving.
         * @returns {boolean}
         */
        isMoving() {
            return this.isWalking || this.moveTarget !== null;
        }

        /**
         * Get the current move target.
         * @returns {THREE.Vector3|null}
         */
        getMoveTarget() {
            return this.moveTarget ? this.moveTarget.clone() : null;
        }

        // ─── Cleanup ──────────────────────────────────────────────────

        /**
         * Dispose of the integration layer, closing connections.
         */
        dispose() {
            if (this.motorEventSource) {
                this.motorEventSource.close();
                this.motorEventSource = null;
            }
            this.initialized = false;
            console.log('[LumaxIntegration] Disposed');
        }
    }

    // ─── Auto-Initialize on DOM Ready ─────────────────────────────────
    function autoInit() {
        if (window.FoveAI_INTEGRATION) {
            console.log('[LumaxIntegration] Already initialized');
            return;
        }
        new LumaxIntegrationLayer();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }

    // ─── Export ──────────────────────────────────────────────────────
    window.LumaxIntegrationLayer = LumaxIntegrationLayer;
    window.FoveAI_BEHAVIOR_STATES = BEHAVIOR_STATES;
    window.FoveAI_EMOTION_MAP = EMOTION_VRM_MAP;
})();