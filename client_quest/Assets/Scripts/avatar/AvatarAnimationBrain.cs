using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace FoveAI.Avatar
{
    /// <summary>
    /// AvatarAnimationBrain — Autonomous animation controller ported from the
    /// 3D_Avatar_Chatbot frontend (LumaxIntegrationLayer.js + BehaviorEngine.js +
    /// EmotionEngine.js + ProceduralAnimator.js + AnimationBlendController.js).
    ///
    /// This is the avatar's "inner life". It is NOT a clip player. It is a living
    /// state machine that:
    ///
    ///   1. Maintains persistent internal DRIVES (curiosity, restlessness, socialNeed,
    ///      energy, expressiveness) that fluctuate over time
    ///   2. Runs a BEHAVIOR STATE MACHINE (CALM_IDLE, SOCIAL_TURN, CURIOUS_STEP,
    ///      WANDER_NEARBY, EMOTIONAL_BURST, RETURNING_HOME, RESTING)
    ///   3. Runs a 4-STATE CYCLE (idle → slow_burn → dream) that changes the avatar's
    ///      mood and gesture patterns over minutes
    ///   4. Makes AUTONOMOUS DECISIONS every few seconds based on drives — the avatar
    ///      wanders, turns toward the user, fidgets, and emotes on its own
    ///   5. Maps LLM emotions to STATE CHANGES, not direct clip commands
    ///   6. Plays MICRO-GESTURES (nod, tilt, look_away, blink, breath_shift) layered
    ///      on top of base animations
    ///   7. Has a CONVERSATION STATE (IDLE, LISTENING, THINKING, SPEAKING, MICRO_IDLE)
    ///      that coordinates gaze, nodding, and attention
    ///
    /// Ported from:
    ///   - LumaxIntegrationLayer.js (59KB) — drives, 4-state, autonomous decisions
    ///   - BehaviorEngine.js (21KB) — conversation state machine
    ///   - EmotionEngine.js (8KB) — emotion analysis (simplified for Unity)
    ///   - ProceduralAnimator.js (40KB) — breathing, gaze, modes
    ///   - AnimationBlendController.js (8KB) — crossfade logic
    ///
    /// Architecture:
    ///   LLM → CognitiveRouter → AvatarAnimationBrain (state update)
    ///                                    ↓
    ///              VRMAAnimationLoader (clip playback)
    ///              AvatarPuppetDriver  (procedural locomotion / T-pose fix)
    ///              AvatarBlendshapeDriver (facial expressions)
    /// </summary>
    public class AvatarAnimationBrain : MonoBehaviour
    {
        // ════════════════════════════════════════════════════════════════
        // BEHAVIOR STATES (ported from LumaxIntegrationLayer.BEHAVIOR_STATES)
        // ════════════════════════════════════════════════════════════════

        public enum BehaviorState
        {
            CalmIdle,       // Default. Breathing, micro-gestures, head tracking
            SocialTurn,     // Turning toward user. Warm attention.
            CuriousStep,    // 1-2 short steps toward something interesting
            WanderNearby,   // Short walk nearby, then return home
            EmotionalBurst, // Animation triggered by AI emotion output
            ReturningHome,  // Smooth walk back to home position
            Resting,        // Deep idle, very minimal motion
        }

        // ════════════════════════════════════════════════════════════════
        // CONVERSATION STATES (ported from BehaviorEngine.State)
        // ════════════════════════════════════════════════════════════════

        public enum ConversationState
        {
            Idle,       // Default resting state
            Listening,  // User mic is active — attentive, slight nod
            Thinking,   // Waiting for LLM response — gaze drift, head tilt
            Speaking,   // TTS is playing — lip-sync, emotion, eye contact
            MicroIdle,  // Prolonged idle — micro-expressions, gaze wander
        }

        // ════════════════════════════════════════════════════════════════
        // 4-STATE SYSTEM (ported from LumaxIntegrationLayer 4-State)
        // ════════════════════════════════════════════════════════════════

        public enum FourStateMode
        {
            Idle,       // Default calm idle — subtle breathing
            SlowBurn,   // Low-energy simmer — emotion builds gradually
            Dreaming,   // Dream-like — random gestures, emotional flickers
        }

        // ════════════════════════════════════════════════════════════════
        // DRIVES — the avatar's internal motivations
        // (ported from LumaxIntegrationLayer.drives)
        // ════════════════════════════════════════════════════════════════

        [System.Serializable]
        public class Drives
        {
            [Range(0f, 1f)] public float curiosity = 0.3f;       // Desire to explore
            [Range(0f, 1f)] public float restlessness = 0.1f;    // Buildup when idle too long
            [Range(0f, 1f)] public float socialNeed = 0.5f;      // Desire for interaction
            [Range(0f, 1f)] public float energy = 1.0f;          // Depletes with activity, recovers at rest
            [Range(0f, 1f)] public float expressiveness = 0.5f;  // Urge to emote/gesture
        }

        // ════════════════════════════════════════════════════════════════
        // MICRO-GESTURE REGISTRY (ported from LumaxIntegrationLayer.MICRO_GESTURES)
        // ════════════════════════════════════════════════════════════════

        public enum MicroGestureCategory
        {
            Idle,       // nod, tilt, look_away, blink, breath_shift, weight_shift
            Social,     // nod, tilt, smile, eyebrow_raise
            Curious,    // double_take, look_away, tilt, lean_forward
            Emphatic,   // head_shake, shoulder_shrug, hand_gesture, point
        }

        private static readonly Dictionary<MicroGestureCategory, string[]> MicroGestures =
            new Dictionary<MicroGestureCategory, string[]>
            {
                { MicroGestureCategory.Idle,      new[] { "nod", "tilt", "lookaround", "blink", "relax", "vrma_07" } },
                { MicroGestureCategory.Social,    new[] { "nod", "relax", "vrma_02", "vrma_05" } },
                { MicroGestureCategory.Curious,   new[] { "lookaround", "tilt", "vrma_03", "vrma_04" } },
                { MicroGestureCategory.Emphatic,  new[] { "vrma_01", "vrma_06", "clapping" } },
            };

        // ════════════════════════════════════════════════════════════════
        // EMOTION → VRM MAP (ported from LumaxIntegrationLayer.EMOTION_VRM_MAP)
        // ════════════════════════════════════════════════════════════════

        private static readonly Dictionary<string, string> EmotionVrmMap =
            new Dictionary<string, string>
            {
                { "joy", "happy" }, { "happy", "happy" }, { "excited", "happy" },
                { "love", "happy" },
                { "anger", "angry" }, { "angry", "angry" }, { "frustrated", "angry" },
                { "sorrow", "sad" }, { "sad", "sad" }, { "depressed", "sad" },
                { "fun", "relaxed" }, { "relaxed", "relaxed" }, { "calm", "relaxed" },
                { "peaceful", "relaxed" }, { "tired", "relaxed" },
                { "surprise", "surprised" }, { "surprised", "surprised" },
                { "shocked", "surprised" }, { "confused", "surprised" },
                { "neutral", "neutral" }, { "thinking", "neutral" },
            };

        // ════════════════════════════════════════════════════════════════
        // CONFIG (ported from LumaxIntegrationLayer.DEFAULT_MOVEMENT_CONFIG)
        // ════════════════════════════════════════════════════════════════

        [Header("Movement Config")]
        [SerializeField] private float walkSpeed = 1.0f;
        [SerializeField] private float turnSpeed = 2.0f;
        [SerializeField] private float maxWanderDistance = 3.0f;
        [SerializeField] private float preferredStepDistance = 0.8f;
        [SerializeField] private float approachDistance = 1.2f;
        [SerializeField] private float returnHomeDelay = 8.0f;
        [SerializeField] private float minStateDuration = 3.0f;
        [SerializeField] private float decisionInterval = 4.0f;
        [Range(0f, 1f)] [SerializeField] private float idleMicroGestureChance = 0.3f;
        [SerializeField] private float idleBreathVariation = 0.15f;
        [SerializeField] private float idleSwayAmount = 0.02f;
        [SerializeField] private float homeDriftStrength = 0.3f;
        [SerializeField] private float homeDriftThreshold = 1.5f;
        [SerializeField] private float curiosityBaseline = 0.2f;
        [SerializeField] private float restlessnessThreshold = 15.0f;
        [SerializeField] private float socialNeedRate = 0.02f;
        [Range(0f, 1f)] [SerializeField] private float spontaneity = 0.05f;
        [SerializeField] private float expressivenessDecay = 0.01f;
        [SerializeField] private float energyRecoveryRate = 0.05f;
        [SerializeField] private float energyDrainRate = 0.1f;

        [Header("4-State System Config")]
        [SerializeField] private float deepIdleBreathRate = 0.001f;
        [SerializeField] private float slowBurnEmotionBuildRate = 0.02f;
        [SerializeField] private float dreamStateInterval = 8.0f;
        [SerializeField] private float fourStateCycleInterval = 30.0f;

        [Header("Conversation Config")]
        [SerializeField] private float microIdleTimeout = 12.0f; // Seconds before IDLE → MICRO_IDLE

        [Header("Gaze Config")]
        [Range(0f, 1f)] [SerializeField] private float gazeAtUserProbability = 0.7f;
        [SerializeField] private Vector2 gazeHoldDuration = new Vector2(2f, 6f);
        [SerializeField] private float gazeLerpSpeed = 6f;

        [Header("References")]
        [SerializeField] private VRMAAnimationLoader vrmaLoader;
        [SerializeField] private AvatarBlendshapeDriver blendshapeDriver;
        [SerializeField] private AvatarPuppetDriver puppetDriver;
        [SerializeField] private Animator animator;

        [Header("Current State (Debug)")]
        public BehaviorState behaviorState = BehaviorState.CalmIdle;
        public ConversationState conversationState = ConversationState.Idle;
        public FourStateMode fourStateMode = FourStateMode.Idle;
        public Drives drives = new Drives();

        // ── Internal State ──────────────────────────────────────────────

        private float _stateTimer;
        private float _emotionTimer;
        private string _currentEmotion = "neutral";
        private float _emotionIntensity;

        private Vector3 _homePosition;
        private Vector3 _currentPosition;
        private float _currentRotation;
        private Vector3 _moveTarget;
        private bool _isWalking;
        private bool _isTurning;
        private float _turnTarget;

        private float _decisionTimer;
        private float _fourStateTimer;
        private float _slowBurnIntensity;
        private float _dreamGestureTimer;

        // Gaze
        private float _gazeYaw, _gazePitch;
        private float _gazeTargetYaw, _gazeTargetPitch;
        private float _nextGazeChangeTime;
        private Transform _gazeTarget;
        private Camera _userCamera;
        private Quaternion _initialHeadLocalRot;
        private bool _hasHeadRot;

        // Conversation state
        private float _conversationStateTime;
        private float _nextMicroExprTime;
        private float _nodPhase;
        private float _thinkGazePhase;
        private bool _emotionApplied;

        // Micro-gesture queue
        private readonly Queue<string> _gestureQueue = new Queue<string>();
        private string _currentGesture;
        private float _gestureTimer;

        // Available idle / gesture animations
        private readonly string[] _idleAnimations = { "relax", "waiting-standard", "vrma_02", "vrma_05", "vrma_06" };
        private readonly string[] _gestureAnimations = { "vrma_01", "vrma_03", "vrma_04", "vrma_07", "lookaround" };

        // ════════════════════════════════════════════════════════════════
        // LIFECYCLE
        // ════════════════════════════════════════════════════════════════

        private void Awake()
        {
            if (vrmaLoader == null) vrmaLoader = GetComponentInChildren<VRMAAnimationLoader>();
            if (blendshapeDriver == null) blendshapeDriver = GetComponentInChildren<AvatarBlendshapeDriver>();
            if (puppetDriver == null) puppetDriver = GetComponentInChildren<AvatarPuppetDriver>();
            if (animator == null) animator = GetComponentInChildren<Animator>();
        }

        private void Start()
        {
            _homePosition = transform.position;
            _currentPosition = _homePosition;
            _currentRotation = transform.rotation.eulerAngles.y;

            _userCamera = Camera.main;

            StartCoroutine(AutonomousLoop());
        }

        private void Update()
        {
            float dt = Time.deltaTime;

            _stateTimer += dt;
            _conversationStateTime += dt;
            _emotionTimer = Mathf.Max(0f, _emotionTimer - dt);

            // Update drives
            UpdateDrives(dt);

            // Decay transient emotions
            if (_emotionTimer <= 0f && _currentEmotion != "neutral")
            {
                SetEmotion("neutral", 0f);
            }

            // Update 4-state system
            UpdateFourStateSystem(dt);

            // Update conversation state machine
            UpdateConversationState(dt);

            // Update gaze
            UpdateGaze(dt);

            // Update movement
            UpdateMovement(dt);

            // Update micro-gestures
            UpdateMicroGestures(dt);
        }

        // ════════════════════════════════════════════════════════════════
        // DRIVES (ported from LumaxIntegrationLayer._updateDrives)
        // ════════════════════════════════════════════════════════════════

        private void UpdateDrives(float dt)
        {
            // Energy recovery when idle
            if (behaviorState == BehaviorState.CalmIdle || behaviorState == BehaviorState.Resting)
            {
                drives.energy = Mathf.Min(1f, drives.energy + energyRecoveryRate * dt);
            }

            // Social need decay when alone
            drives.socialNeed = Mathf.Max(0f, drives.socialNeed - socialNeedRate * dt);

            // Expressiveness decay
            drives.expressiveness = Mathf.Max(0f, drives.expressiveness - expressivenessDecay * dt);

            // Restlessness builds when idle too long
            if (behaviorState == BehaviorState.CalmIdle && _stateTimer > restlessnessThreshold)
            {
                drives.restlessness = Mathf.Min(1f, drives.restlessness + dt * 0.02f);
            }
            else
            {
                drives.restlessness = Mathf.Max(0f, drives.restlessness - dt * 0.01f);
            }

            // Curiosity slowly drifts toward baseline
            drives.curiosity = Mathf.MoveTowards(drives.curiosity, curiosityBaseline, dt * 0.01f);
        }

        // ════════════════════════════════════════════════════════════════
        // 4-STATE SYSTEM (ported from LumaxIntegrationLayer._updateFourStateSystem)
        // ════════════════════════════════════════════════════════════════

        private void UpdateFourStateSystem(float dt)
        {
            _fourStateTimer += dt;

            if (_fourStateTimer >= fourStateCycleInterval)
            {
                _fourStateTimer = 0f;
                // Cycle: Idle → SlowBurn → Dreaming → Idle
                switch (fourStateMode)
                {
                    case FourStateMode.Idle:     fourStateMode = FourStateMode.SlowBurn; break;
                    case FourStateMode.SlowBurn: fourStateMode = FourStateMode.Dreaming; break;
                    case FourStateMode.Dreaming: fourStateMode = FourStateMode.Idle; break;
                }
                Debug.Log($"[AvatarBrain] 4-State mode: {fourStateMode}");
            }

            switch (fourStateMode)
            {
                case FourStateMode.Idle:
                    // Subtle breathing variation — handled by PuppetDriver
                    break;

                case FourStateMode.SlowBurn:
                    // Emotion builds gradually
                    _slowBurnIntensity = Mathf.Min(1f, _slowBurnIntensity + slowBurnEmotionBuildRate * dt);

                    if (_slowBurnIntensity > 0.3f && _slowBurnIntensity < 0.6f)
                    {
                        if (_currentEmotion != "thinking")
                            SetEmotion("thinking", _slowBurnIntensity * 0.5f);
                    }
                    else if (_slowBurnIntensity >= 0.6f && _slowBurnIntensity < 0.8f)
                    {
                        if (_currentEmotion != "surprised")
                            SetEmotion("surprised", _slowBurnIntensity * 0.4f);
                    }
                    else if (_slowBurnIntensity >= 0.8f)
                    {
                        if (_currentEmotion != "happy")
                            SetEmotion("happy", _slowBurnIntensity * 0.3f);
                    }

                    // Occasional curious gestures
                    if (Random.value < 0.3f * dt)
                    {
                        QueueMicroGesture(GetRandomGesture(MicroGestureCategory.Curious));
                    }
                    break;

                case FourStateMode.Dreaming:
                    // Dream-like — random gestures, emotional flickers, gaze shifts
                    _dreamGestureTimer += dt;
                    if (_dreamGestureTimer >= dreamStateInterval)
                    {
                        _dreamGestureTimer = 0f;

                        // Random emotional flicker
                        string[] dreamEmotions = { "happy", "surprised", "thinking", "neutral" };
                        string flicker = dreamEmotions[Random.Range(0, dreamEmotions.Length)];
                        SetEmotion(flicker, 0.3f + Random.value * 0.4f);

                        // Random micro-gesture
                        string[] dreamGestures = { "nod", "tilt", "lookaround", "relax", "vrma_07" };
                        QueueMicroGesture(dreamGestures[Random.Range(0, dreamGestures.Length)]);

                        // Random gaze shift
                        if (Random.value < 0.3f)
                        {
                            _gazeTargetYaw = (Random.value - 0.5f) * 0.5f;
                            _gazeTargetPitch = (Random.value - 0.5f) * 0.3f;
                        }
                    }
                    break;
            }
        }

        // ════════════════════════════════════════════════════════════════
        // AUTONOMOUS DECISION SYSTEM
        // (ported from LumaxIntegrationLayer._autonomousDecision)
        // ════════════════════════════════════════════════════════════════

        private IEnumerator AutonomousLoop()
        {
            while (enabled)
            {
                // Wait for VRMA loader to be ready
                if (vrmaLoader == null)
                {
                    yield return new WaitForSeconds(1f);
                    continue;
                }

                // Run autonomous decision at decisionInterval
                _decisionTimer += decisionInterval;
                if (_decisionTimer >= decisionInterval)
                {
                    _decisionTimer = 0f;
                    AutonomousDecision();
                }

                yield return new WaitForSeconds(decisionInterval);
            }
        }

        /// <summary>
        /// The core autonomous decision function. This is what makes the avatar
        /// feel alive — she decides what to do on her own based on internal drives.
        /// </summary>
        private void AutonomousDecision()
        {
            // Don't override active commands
            if (_isWalking || _isTurning) return;
            if (conversationState == ConversationState.Speaking ||
                conversationState == ConversationState.Thinking) return;

            // ── Drive-based state transitions ──

            // Restlessness → wander
            if (drives.restlessness > 0.7f && drives.energy > 0.3f)
            {
                TransitionTo(BehaviorState.WanderNearby);
                PickRandomWanderTarget();
                Debug.Log("[AvatarBrain] Autonomous: wander (restless)");
                return;
            }

            // Low social need → turn toward user
            if (drives.socialNeed < 0.3f && _userCamera != null)
            {
                TransitionTo(BehaviorState.SocialTurn);
                TurnToward(_userCamera.transform.position);
                Debug.Log("[AvatarBrain] Autonomous: turn to user (social need)");
                return;
            }

            // High expressiveness → emotional burst
            if (drives.expressiveness > 0.6f && drives.energy > 0.5f)
            {
                TransitionTo(BehaviorState.EmotionalBurst);
                string[] emotions = { "happy", "joy", "excited", "relaxed" };
                SetEmotion(emotions[Random.Range(0, emotions.Length)], 0.8f);
                QueueMicroGesture(GetRandomGesture(MicroGestureCategory.Emphatic));
                drives.expressiveness = 0.2f;
                Debug.Log("[AvatarBrain] Autonomous: emotional burst");
                return;
            }

            // High curiosity → curious step
            if (drives.curiosity > 0.6f && drives.energy > 0.4f)
            {
                TransitionTo(BehaviorState.CuriousStep);
                PickRandomWanderTarget(0.5f);
                QueueMicroGesture(GetRandomGesture(MicroGestureCategory.Curious));
                drives.curiosity = 0.2f;
                Debug.Log("[AvatarBrain] Autonomous: curious step");
                return;
            }

            // Low energy → rest
            if (drives.energy < 0.2f)
            {
                TransitionTo(BehaviorState.Resting);
                if (vrmaLoader != null) vrmaLoader.CrossFade("sleepy", 1f);
                Debug.Log("[AvatarBrain] Autonomous: resting (low energy)");
                return;
            }

            // ── Spontaneous micro-gestures ──
            if (Random.value < spontaneity)
            {
                QueueMicroGesture(GetRandomGesture(MicroGestureCategory.Idle));
            }

            // ── Spontaneous emotion flickers ──
            if (Random.value < 0.1f && _currentEmotion == "neutral")
            {
                string[] flickers = { "happy", "thinking", "surprised" };
                SetEmotion(flickers[Random.Range(0, flickers.Length)], 0.3f);
            }

            // ── Return home if too far ──
            if (behaviorState == BehaviorState.CalmIdle || behaviorState == BehaviorState.Resting)
            {
                float distToHome = Vector3.Distance(_currentPosition, _homePosition);
                if (distToHome > homeDriftThreshold * 1.5f)
                {
                    TransitionTo(BehaviorState.ReturningHome);
                    CommandReturnHome();
                    Debug.Log("[AvatarBrain] Autonomous: returning home");
                }
            }
        }

        // ════════════════════════════════════════════════════════════════
        // BEHAVIOR STATE MACHINE
        // (ported from LumaxIntegrationLayer.transitionTo)
        // ════════════════════════════════════════════════════════════════

        public void TransitionTo(BehaviorState newState)
        {
            if (behaviorState == newState) return;
            var oldState = behaviorState;
            behaviorState = newState;
            _stateTimer = 0f;
            Debug.Log($"[AvatarBrain] Behavior: {oldState} → {newState}");

            // State-specific entry actions
            switch (newState)
            {
                case BehaviorState.CalmIdle:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("relax", 0.5f);
                    break;

                case BehaviorState.Resting:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("sleepy", 1f);
                    break;

                case BehaviorState.WanderNearby:
                case BehaviorState.CuriousStep:
                    // PuppetDriver handles walk animation
                    break;

                case BehaviorState.ReturningHome:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("vrma_02", 0.5f);
                    break;
            }
        }

        /// <summary>
        /// Reaction when poked or pointed at by user controller ray.
        /// </summary>
        public void Poke()
        {
            TransitionTo(BehaviorState.SocialTurn);
            SetEmotion("happy", 1.5f);
        }

        // ════════════════════════════════════════════════════════════════
        // CONVERSATION STATE MACHINE
        // (ported from BehaviorEngine.js)
        // ════════════════════════════════════════════════════════════════

        private void UpdateConversationState(float dt)
        {
            switch (conversationState)
            {
                case ConversationState.Idle:
                    if (_conversationStateTime > microIdleTimeout)
                    {
                        SetConversationState(ConversationState.MicroIdle);
                    }
                    break;

                case ConversationState.Listening:
                    // Periodic subtle nod
                    _nodPhase += dt;
                    if (_nodPhase > 2.5f + Random.value * 1.5f)
                    {
                        _nodPhase = 0f;
                        _gazeTargetPitch = -0.08f;
                        StartCoroutine(ResetGazePitchAfterDelay(0.3f));
                    }
                    break;

                case ConversationState.Thinking:
                    // Animated gaze: look up-left, then drift back
                    _thinkGazePhase += dt;
                    if (_thinkGazePhase < 1.5f)
                    {
                        _gazeTargetYaw = -0.25f;
                        _gazeTargetPitch = 0.18f;
                    }
                    else if (_thinkGazePhase < 3.0f)
                    {
                        float progress = (_thinkGazePhase - 1.5f) / 1.5f;
                        _gazeTargetYaw = -0.25f * (1 - progress);
                        _gazeTargetPitch = 0.18f * (1 - progress);
                    }
                    else
                    {
                        _thinkGazePhase = 0f;
                    }
                    break;

                case ConversationState.Speaking:
                    // Gaze stays on user, lip-sync handled by TTS
                    break;

                case ConversationState.MicroIdle:
                    // Slow gaze wander
                    if (Random.value < dt * 0.17f) // ~every 6 seconds
                    {
                        _gazeTargetYaw = (Random.value - 0.5f) * 0.25f;
                        _gazeTargetPitch = (Random.value - 0.5f) * 0.15f;
                    }

                    // Micro-expressions
                    _nextMicroExprTime -= dt;
                    if (_nextMicroExprTime <= 0f)
                    {
                        TriggerMicroExpression();
                        _nextMicroExprTime = 5f + Random.value * 6f;
                    }
                    break;
            }
        }

        public void SetConversationState(ConversationState newState)
        {
            if (conversationState == newState) return;
            var oldState = conversationState;
            conversationState = newState;
            _conversationStateTime = 0f;
            _emotionApplied = false;
            Debug.Log($"[AvatarBrain] Conversation: {oldState} → {newState}");

            switch (newState)
            {
                case ConversationState.Idle:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("relax", 0.5f);
                    _gazeTargetYaw = 0f;
                    _gazeTargetPitch = 0f;
                    _nextMicroExprTime = 5f + Random.value * 4f;
                    break;

                case ConversationState.Listening:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("relax", 0.3f);
                    _gazeTargetYaw = 0f;
                    _gazeTargetPitch = 0f;
                    _nodPhase = 0f;
                    // Subtle attentive expression
                    if (blendshapeDriver != null) blendshapeDriver.ApplyEmotion("happy", 0.12f);
                    break;

                case ConversationState.Thinking:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("thinking", 0.3f);
                    _thinkGazePhase = 0f;
                    _gazeTargetYaw = -0.25f;
                    _gazeTargetPitch = 0.2f;
                    break;

                case ConversationState.Speaking:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("vrma_04", 0.3f);
                    _gazeTargetYaw = 0f;
                    _gazeTargetPitch = 0f;
                    break;

                case ConversationState.MicroIdle:
                    if (vrmaLoader != null) vrmaLoader.CrossFade("waiting-standard", 0.5f);
                    _nextMicroExprTime = 3f + Random.value * 3f;
                    break;
            }
        }

        /// <summary>
        /// Called when the user sends a message (transition to THINKING).
        /// </summary>
        public void OnUserMessage()
        {
            if (conversationState != ConversationState.Speaking)
            {
                SetConversationState(ConversationState.Thinking);
            }
        }

        /// <summary>
        /// Called when the LLM responds (transition to SPEAKING).
        /// </summary>
        public void OnBotResponse(string text, string emotion = null, float intensity = 1.0f)
        {
            if (!_emotionApplied)
            {
                _emotionApplied = true;
                if (!string.IsNullOrEmpty(emotion))
                {
                    SetEmotion(emotion, intensity);
                }
            }
            SetConversationState(ConversationState.Speaking);
        }

        /// <summary>
        /// Called when TTS finishes (transition back to IDLE).
        /// </summary>
        public void OnSpeechEnd()
        {
            SetEmotion("neutral", 0f);
            SetConversationState(ConversationState.Idle);
        }

        /// <summary>
        /// Called when the microphone activates.
        /// </summary>
        public void OnListeningStart()
        {
            SetConversationState(ConversationState.Listening);
        }

        /// <summary>
        /// Called when the microphone deactivates.
        /// </summary>
        public void OnListeningEnd()
        {
            if (conversationState == ConversationState.Listening)
            {
                SetConversationState(ConversationState.Idle);
            }
        }

        // ════════════════════════════════════════════════════════════════
        // EMOTION SYSTEM
        // (ported from LumaxIntegrationLayer.setEmotion + EmotionEngine)
        // ════════════════════════════════════════════════════════════════

        /// <summary>
        /// Set the avatar's emotional state. Called by CognitiveRouter when
        /// [EMOTION: "..."] is received from the LLM.
        /// Updates internal state + facial blendshapes + body animation.
        /// </summary>
        public void SetEmotion(string emotion, float intensity = 1.0f)
        {
            emotion = emotion.ToLowerInvariant().Trim();
            intensity = Mathf.Clamp01(intensity);

            // Prevent frame-loop spam
            if (_currentEmotion == emotion && Mathf.Abs(_emotionIntensity - intensity) < 0.01f)
            {
                _emotionTimer = 5f;
                return;
            }

            _currentEmotion = emotion;
            _emotionIntensity = intensity;
            _emotionTimer = 5f;

            // Map to VRM expression
            string vrmEmotion = EmotionVrmMap.TryGetValue(emotion, out var mapped) ? mapped : "neutral";

            // Apply facial blendshape
            if (blendshapeDriver != null)
            {
                blendshapeDriver.ApplyEmotion(vrmEmotion, intensity);
            }

            // Choose body animation based on emotion + current state
            if (conversationState != ConversationState.Speaking &&
                conversationState != ConversationState.Thinking)
            {
                ChooseAnimationFromEmotion(emotion, intensity);
            }

            // Boost expressiveness drive
            drives.expressiveness = Mathf.Min(1f, drives.expressiveness + intensity * 0.3f);

            Debug.Log($"[AvatarBrain] Emotion: {emotion} ({intensity:F2}) → VRM:{vrmEmotion}");
        }

        /// <summary>
        /// Apply emotion state from LLM directive. This is the main entry point
        /// called by CognitiveRouter.
        /// </summary>
        public void ApplyEmotionState(string emotion, float intensity = 1.0f)
        {
            SetEmotion(emotion, intensity);
        }

        /// <summary>
        /// Choose a body animation based on the current emotion.
        /// </summary>
        private void ChooseAnimationFromEmotion(string emotion, float intensity)
        {
            if (vrmaLoader == null) return;

            string clip = null;
            switch (emotion)
            {
                case "happy":
                case "joy":
                case "excited":
                case "love":
                    clip = intensity > 0.6f ? "vrma_01" : "relax";
                    break;
                case "sad":
                case "sorrow":
                case "depressed":
                    clip = "sad";
                    break;
                case "angry":
                case "anger":
                case "frustrated":
                    clip = "angry";
                    break;
                case "surprised":
                case "surprise":
                case "shocked":
                case "confused":
                    clip = "surprised";
                    break;
                case "relaxed":
                case "calm":
                case "peaceful":
                case "fun":
                    clip = "relax";
                    break;
                case "tired":
                case "sleepy":
                    clip = "sleepy";
                    break;
                case "thinking":
                    clip = "thinking";
                    break;
                case "neutral":
                    clip = _idleAnimations[Random.Range(0, _idleAnimations.Length)];
                    break;
            }

            if (clip != null)
            {
                vrmaLoader.CrossFade(clip, 0.5f);
            }
        }

        // ════════════════════════════════════════════════════════════════
        // MICRO-GESTURE SYSTEM
        // (ported from LumaxIntegrationLayer.queueMicroGesture)
        // ════════════════════════════════════════════════════════════════

        public void QueueMicroGesture(string gesture)
        {
            _gestureQueue.Enqueue(gesture);
            Debug.Log($"[AvatarBrain] Queued gesture: {gesture}");
        }

        public void PlayGesture(string gesture)
        {
            gesture = gesture.ToLowerInvariant().Trim();

            // Direct VRMA match
            if (vrmaLoader != null && vrmaLoader.CrossFade(gesture, 0.3f))
            {
                TransitionTo(BehaviorState.EmotionalBurst);
                Debug.Log($"[AvatarBrain] Playing gesture: {gesture}");
                return;
            }

            // Common gesture name mapping
            var gestureMap = new Dictionary<string, string>
            {
                { "wave", "goodbye" }, { "waving", "goodbye" },
                { "clap", "clapping" }, { "clapping", "clapping" },
                { "bow", "vrma_03" },
                { "think", "thinking" }, { "thinking", "thinking" },
                { "shrug", "vrma_07" },
                { "dance", "vrma_01" },
                { "jump", "jump" },
                { "nod", "vrma_02" },
                { "tilt", "vrma_05" },
                { "look_around", "lookaround" }, { "lookaround", "lookaround" },
            };

            if (gestureMap.TryGetValue(gesture, out var clipName))
            {
                if (vrmaLoader != null && vrmaLoader.CrossFade(clipName, 0.3f))
                {
                    TransitionTo(BehaviorState.EmotionalBurst);
                    Debug.Log($"[AvatarBrain] Mapped gesture: {gesture} → {clipName}");
                }
            }
        }

        private void UpdateMicroGestures(float dt)
        {
            if (_currentGesture != null)
            {
                _gestureTimer -= dt;
                if (_gestureTimer <= 0f)
                {
                    _currentGesture = null;
                    // Return to idle after gesture
                    if (behaviorState == BehaviorState.EmotionalBurst)
                    {
                        TransitionTo(BehaviorState.CalmIdle);
                    }
                }
                return;
            }

            if (_gestureQueue.Count > 0)
            {
                _currentGesture = _gestureQueue.Dequeue();
                _gestureTimer = 2f; // Gesture duration

                if (vrmaLoader != null)
                {
                    vrmaLoader.CrossFade(_currentGesture, 0.3f);
                }
                Debug.Log($"[AvatarBrain] Playing queued gesture: {_currentGesture}");
            }
        }

        private string GetRandomGesture(MicroGestureCategory category)
        {
            var pool = MicroGestures[category];
            return pool[Random.Range(0, pool.Length)];
        }

        private void TriggerMicroExpression()
        {
            // Pick a random micro-expression
            var micros = new[]
            {
                (expr: "happy", value: 0.12f),
                (expr: "surprised", value: 0.08f),
                (expr: "relaxed", value: 0.1f),
            };

            var micro = micros[Random.Range(0, micros.Length)];
            if (blendshapeDriver != null)
            {
                blendshapeDriver.ApplyEmotion(micro.expr, micro.value);
            }

            // Reset after a short delay
            StartCoroutine(ResetMicroExpressionAfterDelay(0.9f, micro.expr));
        }

        // ════════════════════════════════════════════════════════════════
        // GAZE SYSTEM
        // (ported from BehaviorEngine._updateGaze)
        // ════════════════════════════════════════════════════════════════

        private void UpdateGaze(float dt)
        {
            // Change gaze target periodically
            if (Time.time > _nextGazeChangeTime)
            {
                if (_userCamera != null && Random.value < gazeAtUserProbability)
                {
                    _gazeTarget = _userCamera.transform;
                }
                else
                {
                    _gazeTarget = null;
                    _gazeTargetYaw = (Random.value - 0.5f) * 0.4f;
                    _gazeTargetPitch = (Random.value - 0.5f) * 0.2f;
                }
                _nextGazeChangeTime = Time.time + Random.Range(gazeHoldDuration.x, gazeHoldDuration.y);
            }

            // Resolve user camera dynamically if null
            if (_userCamera == null) _userCamera = Camera.main;

            // If gazing at user, compute yaw/pitch toward camera
            if (_gazeTarget != null && _userCamera != null)
            {
                Vector3 dir = _userCamera.transform.position - transform.position;
                dir.y = 0;
                if (dir.magnitude > 0.01f)
                {
                    float angle = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg - _currentRotation;
                    _gazeTargetYaw = Mathf.Clamp(angle / 60f, -1f, 1f) * 0.45f;
                }

                float dy = _userCamera.transform.position.y - (transform.position.y + 1.2f);
                _gazeTargetPitch = Mathf.Clamp(dy / 2.0f, -0.3f, 0.3f);
            }

            // Smooth lerp toward target
            float speed = gazeLerpSpeed * dt;
            _gazeYaw = Mathf.Lerp(_gazeYaw, _gazeTargetYaw, speed);
            _gazePitch = Mathf.Lerp(_gazePitch, _gazeTargetPitch, speed);
        }

        private void LateUpdate()
        {
            // Apply gaze to head bone in LateUpdate AFTER Mecanim pose evaluation
            if (animator != null && animator.isHuman)
            {
                Transform head = animator.GetBoneTransform(HumanBodyBones.Head);
                if (head != null)
                {
                    if (!_hasHeadRot)
                    {
                        _initialHeadLocalRot = head.localRotation;
                        _hasHeadRot = true;
                    }
                    head.localRotation = _initialHeadLocalRot * Quaternion.Euler(_gazePitch * 25f, _gazeYaw * 45f, 0f);
                }
            }
        }

        public Transform GetGazeTarget() => _gazeTarget;

        // ════════════════════════════════════════════════════════════════
        // MOVEMENT SYSTEM
        // (ported from LumaxIntegrationLayer._updateMovement)
        // ════════════════════════════════════════════════════════════════

        public void CommandMoveTo(Vector3 target)
        {
            _moveTarget = target;
            _isWalking = true;
            TransitionTo(BehaviorState.WanderNearby);
        }

        public void CommandReturnHome()
        {
            CommandMoveTo(_homePosition);
            TransitionTo(BehaviorState.ReturningHome);
        }

        public void WalkForward(float meters)
        {
            Vector3 forward = transform.forward * meters;
            CommandMoveTo(_currentPosition + forward);
        }

        private void UpdateMovement(float dt)
        {
            if (!_isWalking) return;

            Vector3 toTarget = _moveTarget - _currentPosition;
            toTarget.y = 0;
            float dist = toTarget.magnitude;

            if (dist < 0.05f)
            {
                // Arrived
                _isWalking = false;
                _currentPosition = _moveTarget;
                transform.position = _currentPosition;

                if (behaviorState == BehaviorState.WanderNearby ||
                    behaviorState == BehaviorState.CuriousStep)
                {
                    TransitionTo(BehaviorState.CalmIdle);
                }
                else if (behaviorState == BehaviorState.ReturningHome)
                {
                    TransitionTo(BehaviorState.CalmIdle);
                }
                return;
            }

            // Move toward target
            Vector3 dir = toTarget.normalized;
            _currentPosition += dir * walkSpeed * dt;
            transform.position = _currentPosition;

            // Turn toward movement direction
            float targetRot = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;
            float rotDiff = Mathf.DeltaAngle(_currentRotation, targetRot);
            _currentRotation += Mathf.Clamp(rotDiff, -turnSpeed * dt * 60f, turnSpeed * dt * 60f);
            transform.rotation = Quaternion.Euler(0, _currentRotation, 0);
        }

        private void PickRandomWanderTarget(float? radius = null)
        {
            float r = radius ?? maxWanderDistance;
            float angle = Random.value * Mathf.PI * 2f;
            float distance = 0.5f + Random.value * (r - 0.5f);
            Vector3 target = _homePosition + new Vector3(
                Mathf.Cos(angle) * distance, 0, Mathf.Sin(angle) * distance);
            CommandMoveTo(target);
        }

        private void TurnToward(Vector3 target)
        {
            Vector3 dir = target - _currentPosition;
            dir.y = 0;
            if (dir.magnitude < 0.01f) return;
            _turnTarget = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;
            _isTurning = true;
        }

        // ════════════════════════════════════════════════════════════════
        // HELPERS
        // ════════════════════════════════════════════════════════════════

        private IEnumerator ResetGazePitchAfterDelay(float delay)
        {
            yield return new WaitForSeconds(delay);
            _gazeTargetPitch = 0f;
        }

        private IEnumerator ResetMicroExpressionAfterDelay(float delay, string expr)
        {
            yield return new WaitForSeconds(delay);
            if (blendshapeDriver != null && _currentEmotion == "neutral")
            {
                blendshapeDriver.ApplyEmotion(expr, 0f);
            }
        }

        /// <summary>
        /// Get a human-readable state summary for debugging.
        /// </summary>
        public string GetStateSummary()
        {
            return $"Behavior: {behaviorState} | Conversation: {conversationState} | " +
                   $"4-State: {fourStateMode} | Emotion: {_currentEmotion} ({_emotionIntensity:F2}) | " +
                   $"Drives: cur={drives.curiosity:F2} rest={drives.restlessness:F2} " +
                   $"soc={drives.socialNeed:F2} eng={drives.energy:F2} exp={drives.expressiveness:F2} | " +
                   $"Anim: {vrmaLoader?.GetCurrentAnimation() ?? "none"}";
        }
    }
}
