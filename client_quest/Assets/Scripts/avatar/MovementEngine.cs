using System;
using System.Collections.Generic;
using UnityEngine;

namespace FoveAI.Avatar
{
    /// <summary>
    /// MovementEngine — Ported from Frontend/XR_Vessel/src/avatar/MovementEngine.ts
    /// Natural Locomotion & Behavior Core for the VRM avatar.
    ///
    /// Replaces raw impulse-based wandering with natural, purposeful behavior patterns.
    /// The avatar can still move, walk, express, and self-puppeteer — but movements are
    /// grounded, intentional, and feel like a living person choosing to be present.
    ///
    /// DESIGN PRINCIPLES:
    ///   1. "Calm Presence" — Mostly idle, breathing, micro-gestures
    ///   2. "Purposeful Movement" — When she moves, it's short and meaningful
    ///   3. "Home Drift" — She always gently returns to her home position
    ///   4. "Emotion-Driven" — AI emotions drive body language, not random urges
    ///   5. "Natural Transitions" — Smooth acceleration, deceleration, turn-then-walk
    ///
    /// BEHAVIOR STATES:
    ///   - CalmIdle:       Default. Breathing, micro-gestures, head tracking
    ///   - SocialTurn:     Turning toward user. Warm attention.
    ///   - CuriousStep:    1-2 short steps toward something interesting
    ///   - WanderNearby:   Short walk nearby, then return home
    ///   - EmotionalBurst: Animation triggered by AI emotion output
    ///   - ReturningHome:  Smooth walk back to home position
    ///   - Resting:        Deep idle, very minimal motion
    ///
    /// Complements AvatarFreeMovement (follow mode) and AvatarPuppetDriver (steering).
    /// Does NOT take over when puppet steering is active.
    /// </summary>
    public class MovementEngine : MonoBehaviour
    {
        // ── Behavior States ──
        public enum BehaviorState
        {
            CalmIdle,
            SocialTurn,
            CuriousStep,
            WanderNearby,
            EmotionalBurst,
            ReturningHome,
            Resting
        }

        // ── Movement Config ──
        [System.Serializable]
        public struct MovementConfig
        {
            [Header("Timing")]
            public float decisionInterval;      // Seconds between autonomous decisions
            public float minStateDuration;      // Minimum time in any state before transitioning
            public float returnHomeDelay;       // Seconds to wait before drifting home after movement

            [Header("Movement")]
            public float walkSpeed;             // Units per second when walking
            public float slowWalkSpeed;         // Slower, more natural pace
            public float turnSpeed;             // Radians per second for smooth turning
            public float maxWanderDistance;     // Max meters from home position
            public float preferredStepDistance; // Typical short step distance
            public float approachDistance;      // How close to approach user-facing direction

            [Header("Idle Behavior")]
            [Range(0f, 1f)] public float idleMicroGestureChance;
            public float idleBreathVariation;
            public float idleSwayAmount;

            [Header("Home Drift")]
            [Range(0f, 1f)] public float homeDriftStrength;
            public float homeDriftThreshold;

            [Header("Drives")]
            public float curiosityBaseline;
            public float restlessnessThreshold;
            public float socialNeedRate;
            [Range(0f, 1f)] public float spontaneity;
            public float expressivenessDecay;
            public float energyRecoveryRate;
            public float energyDrainRate;
        }

        [Header("Movement Config")]
        public MovementConfig config = new()
        {
            decisionInterval = 7.0f,
            minStateDuration = 3.0f,
            returnHomeDelay = 5.0f,
            walkSpeed = 1.0f,
            slowWalkSpeed = 0.5f,
            turnSpeed = 2.0f,
            maxWanderDistance = 2.0f,
            preferredStepDistance = 0.8f,
            approachDistance = 1.0f,
            idleMicroGestureChance = 0.08f,
            idleBreathVariation = 0.03f,
            idleSwayAmount = 0.015f,
            homeDriftStrength = 0.6f,
            homeDriftThreshold = 0.5f,
            curiosityBaseline = 0.12f,
            restlessnessThreshold = 25.0f,
            socialNeedRate = 0.008f,
            spontaneity = 0.06f,
            expressivenessDecay = 0.04f,
            energyRecoveryRate = 0.06f,
            energyDrainRate = 0.04f,
        };

        // ── Drive State ──
        [System.Serializable]
        public struct DriveState
        {
            [Range(0f, 1f)] public float curiosity;      // Urge to investigate
            [Range(0f, 1f)] public float social;         // Need for connection
            [Range(0f, 1f)] public float restlessness;   // Urge to move (kept very low)
            [Range(0f, 1f)] public float expressiveness; // Urge to show emotion
            [Range(0f, 1f)] public float energy;         // Available activity capacity
        }

        [Header("Current Drives (Read-only)")]
        public DriveState drives = new()
        {
            curiosity = 0.15f,
            social = 0.25f,
            restlessness = 0.02f,
            expressiveness = 0.35f,
            energy = 0.85f,
        };

        // ── Awareness State ──
        [System.Serializable]
        public struct AwarenessState
        {
            public float timeSinceLastInteraction;
            public float timeSinceLastMove;
            public float timeInSameEmotion;
            public float timeInCurrentState;
            public string currentActivity;
            public float lastDecision;
        }

        [Header("Current Awareness (Read-only)")]
        public AwarenessState awareness;

        [Header("Current State (Read-only)")]
        public BehaviorState behaviorState = BehaviorState.CalmIdle;
        public string emotionalState = "neutral";
        [Range(0f, 1f)] public float emotionalIntensity;

        // ── Spatial ──
        [Header("Spatial")]
        public Vector3 homePosition = new(0f, 0f, -2.0f);
        public bool autonomousMode = true;

        // ── Private state ──
        private Vector3? _moveTarget;
        private Vector3? _intentionalGoal;
        private float _intentionalExpiry;
        private bool _isWalking;
        private bool _isReturningHome;
        private float _returnHomeTimer;
        private bool _returnHomeScheduled;

        // ── Callbacks ──
        public Action<string, bool, float> onPlayCategory;       // (category, loop, fadeTime)
        public Action<string> onTriggerMicroGesture;             // (gesture name)
        public Action<Vector3> onSetDestination;                 // (target position)
        public Action<float> onWalkForwardCommand;               // (distance)
        public Action<string> onSetEmotionalState;               // (emotion)
        public Action<string, bool, Vector3> onBodyFeedback;     // (message, arrived, position)

        // ── Emotion → Animation Mapping ──
        private static readonly Dictionary<string, string> EMOTION_ANIM_MAP = new()
        {
            { "happy", "Happy" }, { "excited", "Happy" },
            { "sad", "Sad" }, { "concerned", "Sad" },
            { "angry", "Angry" }, { "surprised", "Surprised" },
            { "curious", "Thinking" }, { "thinking", "Thinking" },
            { "neutral", "Idle" }, { "relaxed", "Idle" }, { "calm", "Idle" },
            { "playful", "Dance" }, { "grateful", "Happy" },
            { "love", "Social" }, { "affection", "Social" },
            { "bored", "Idle" }, { "anxious", "Thinking" },
        };

        // ── Micro-gesture pools ──
        private static readonly string[] IDLE_GESTURES    = { "nod", "tilt", "look_away", "double_take" };
        private static readonly string[] SOCIAL_GESTURES  = { "nod", "tilt" };
        private static readonly string[] CURIOUS_GESTURES = { "double_take", "look_away", "tilt" };

        private static readonly string[] STRONG_EMOTIONS = { "happy", "excited", "sad", "angry" };
        private static readonly string[] EXPRESSIVE_EMOTIONS = { "happy", "excited", "curious", "angry" };

        // ── Public API ──

        public Vector3 GetHomePosition() => homePosition;
        public void SetHomePosition(Vector3 pos) => homePosition = pos;
        public BehaviorState GetState() => behaviorState;
        public DriveState GetDrives() => drives;
        public bool IsMoving() => _isWalking || _moveTarget.HasValue;
        public Vector3? GetMoveTarget() => _moveTarget;
        public float GetWalkSpeed() => _isReturningHome ? config.slowWalkSpeed : config.walkSpeed;

        public void SetDestination(Vector3 target)
        {
            _moveTarget = target;
            _intentionalGoal = target;
            _intentionalExpiry = Time.time + 10f;
            _isReturningHome = false;
        }

        /// <summary>Called when AI emotion is detected.</summary>
        public void SetEmotion(string emotion, float intensity = 1.0f)
        {
            emotionalState = emotion.ToLower();
            emotionalIntensity = intensity;
            awareness.timeInSameEmotion = 0f;

            if (Array.IndexOf(STRONG_EMOTIONS, emotionalState) >= 0)
                TransitionTo(BehaviorState.EmotionalBurst);
        }

        /// <summary>Called when user interacts — satisfies social need.</summary>
        public void OnUserInteraction()
        {
            awareness.timeSinceLastInteraction = 0f;
            drives.social *= 0.3f;
        }

        /// <summary>Called by AI MOVE_TO command — intentional navigation.</summary>
        public void CommandMoveTo(Vector3 target)
        {
            _moveTarget = target;
            _isReturningHome = false;
            _intentionalGoal = target;
            _intentionalExpiry = Time.time + 10f;
            awareness.timeSinceLastMove = 0f;
        }

        /// <summary>Called by AI WALK_FORWARD command.</summary>
        public void CommandWalkForward(Vector3 target)
        {
            _moveTarget = target;
            _isReturningHome = false;
            _intentionalGoal = target;
            _intentionalExpiry = Time.time + 10f;
            awareness.timeSinceLastMove = 0f;
        }

        /// <summary>Called by steering mode — manual control overrides autonomous movement.</summary>
        public void SetSteeringActive(bool active)
        {
            if (active)
            {
                _moveTarget = null;
                _isWalking = false;
                _isReturningHome = false;
                _intentionalGoal = null;
                _intentionalExpiry = 0f;
                TransitionTo(BehaviorState.CalmIdle);
            }
        }

        /// <summary>Set social relationship-appropriate mode.</summary>
        public void SetSocialMode(string mode)
        {
            switch (mode)
            {
                case "coexist":
                    config.spontaneity = 0.02f;
                    config.socialNeedRate = 0.003f;
                    drives.curiosity = 0.08f;
                    drives.restlessness = 0.01f;
                    break;
                case "cowork":
                    config.spontaneity = 0.04f;
                    config.socialNeedRate = 0.005f;
                    drives.curiosity = 0.1f;
                    break;
                case "coop":
                    config.spontaneity = 0.08f;
                    config.socialNeedRate = 0.01f;
                    drives.curiosity = 0.2f;
                    drives.expressiveness = 0.4f;
                    break;
                case "rest":
                    config.spontaneity = 0.02f;
                    config.socialNeedRate = 0.003f;
                    drives.energy = 0.4f;
                    drives.restlessness = 0f;
                    emotionalState = "calm";
                    break;
                case "follow":
                    config.spontaneity = 0.03f;
                    drives.curiosity = 0.5f;
                    break;
                case "intimate":
                    config.spontaneity = 0.04f;
                    config.socialNeedRate = 0.015f;
                    drives.social = 0.8f;
                    drives.expressiveness = 0.6f;
                    break;
            }
        }

        /// <summary>Get the animation category for the current emotional state.</summary>
        public string GetEmotionAnimation() =>
            EMOTION_ANIM_MAP.TryGetValue(emotionalState, out var anim) ? anim : "Idle";

        // ── Core Update Loop ──

        /// <summary>
        /// Returns per-frame velocity, target rotation, animation category, and micro-gesture.
        /// Call this from the avatar controller's Update/LateUpdate.
        /// </summary>
        public struct MovementOutput
        {
            public Vector3 velocity;
            public Quaternion? targetRotation;
            public string animationCategory;
            public string microGesture;
        }

        public MovementOutput UpdateEngine(float delta, Vector3 currentPosition, Vector3? cameraPosition = null)
        {
            // Update drives and awareness
            UpdateDrives(delta);
            awareness.timeSinceLastInteraction += delta;
            awareness.timeSinceLastMove += delta;
            awareness.timeInSameEmotion += delta;
            awareness.timeInCurrentState += delta;

            // Check for movement completion
            if (_moveTarget.HasValue)
            {
                float dist = Vector3.Distance(currentPosition, _moveTarget.Value);
                if (dist < 0.15f)
                {
                    _moveTarget = null;
                    _isWalking = false;
                    awareness.timeSinceLastMove = 0f;

                    if (_intentionalGoal.HasValue)
                    {
                        _intentionalGoal = null;
                        _intentionalExpiry = 0f;
                        DispatchArrivalFeedback();
                    }
                }
                else if (_intentionalGoal.HasValue && Time.time > _intentionalExpiry)
                {
                    _moveTarget = null;
                    _isWalking = false;
                    _intentionalGoal = null;
                    _intentionalExpiry = 0f;
                    DispatchFailureFeedback("Movement timed out. I couldn't reach the destination (possibly blocked).");
                }
            }

            // Home drift (gentle)
            Vector3 homeDriftForce = Vector3.zero;
            float distFromHome = Vector3.Distance(currentPosition, homePosition);
            if (!_moveTarget.HasValue && !_intentionalGoal.HasValue &&
                distFromHome > config.maxWanderDistance * 0.8f)
            {
                Vector3 driftDir = homePosition - currentPosition;
                driftDir.y = 0f;
                if (driftDir.sqrMagnitude > 0.001f)
                {
                    driftDir.Normalize();
                    homeDriftForce = driftDir * (0.15f * delta);
                }
            }

            // Autonomous household presence
            awareness.lastDecision += delta;
            string animationCategory = null;
            string microGesture = null;

            bool idleLongEnough = awareness.lastDecision >= config.decisionInterval;
            bool noIntentionalGoal = !_intentionalGoal.HasValue && !_moveTarget.HasValue;
            bool minStateElapsed = awareness.timeInCurrentState >= config.minStateDuration;

            if (autonomousMode && idleLongEnough && noIntentionalGoal && minStateElapsed)
            {
                var decision = MakeDecision(cameraPosition);
                awareness.lastDecision = 0f;
                if (!string.IsNullOrEmpty(decision.animation))
                    animationCategory = decision.animation;
                if (!string.IsNullOrEmpty(decision.gesture))
                    microGesture = decision.gesture;
            }

            // Handle scheduled return home
            if (_returnHomeScheduled)
            {
                _returnHomeTimer -= delta;
                if (_returnHomeTimer <= 0f)
                {
                    _returnHomeScheduled = false;
                    StartReturnHome();
                }
            }

            // Compute velocity toward move target
            Vector3 velocity = Vector3.zero;
            Quaternion? targetRotation = null;

            if (_moveTarget.HasValue)
            {
                Vector3 dir = _moveTarget.Value - currentPosition;
                dir.y = 0f;
                float dist = dir.magnitude;
                if (dist > 0.15f)
                {
                    float speed = _isReturningHome ? config.slowWalkSpeed : config.walkSpeed;
                    velocity = dir.normalized * speed;
                    targetRotation = Quaternion.LookRotation(dir.normalized);
                }
            }
            else if (homeDriftForce.sqrMagnitude > 0.0001f)
            {
                velocity = homeDriftForce * (delta * 0.5f);
                _isWalking = false;
            }
            else
            {
                _isWalking = false;
            }

            _isWalking = velocity.magnitude > 0.05f;

            // Face user when idle
            if (!_moveTarget.HasValue && !_isWalking && cameraPosition.HasValue)
            {
                Vector3 toCamera = cameraPosition.Value - currentPosition;
                toCamera.y = 0f;
                if (toCamera.sqrMagnitude > 0.04f)
                {
                    toCamera.Normalize();
                    targetRotation = Quaternion.LookRotation(toCamera);
                }
            }

            return new MovementOutput
            {
                velocity = velocity,
                targetRotation = targetRotation,
                animationCategory = animationCategory,
                microGesture = microGesture
            };
        }

        // ── Drive Dynamics ──

        private void UpdateDrives(float delta)
        {
            var cfg = config;

            // Curiosity: gently drifts toward baseline
            drives.curiosity += (cfg.curiosityBaseline - drives.curiosity) * delta * 0.1f;
            drives.curiosity += awareness.timeSinceLastInteraction * 0.003f * delta;
            drives.curiosity = Mathf.Clamp01(drives.curiosity);

            // Social: slowly rises
            drives.social += cfg.socialNeedRate * delta;
            drives.social = Mathf.Min(1.0f, drives.social);

            // Restlessness: VERY slow rise only after long stillness
            if (awareness.timeSinceLastMove > cfg.restlessnessThreshold)
                drives.restlessness += delta * 0.006f;
            else
                drives.restlessness -= delta * 0.1f;
            drives.restlessness = Mathf.Clamp01(drives.restlessness);

            // Expressiveness: emotional states fuel it
            if (Array.IndexOf(EXPRESSIVE_EMOTIONS, emotionalState) >= 0)
                drives.expressiveness += delta * 0.05f;
            else
                drives.expressiveness -= cfg.expressivenessDecay * delta;
            drives.expressiveness = Mathf.Clamp01(drives.expressiveness);

            // Energy: drained by movement, restored by rest
            if (_isWalking || behaviorState == BehaviorState.WanderNearby)
                drives.energy -= cfg.energyDrainRate * delta;
            else
                drives.energy += cfg.energyRecoveryRate * delta;
            drives.energy = Mathf.Clamp(drives.energy, 0.1f, 1.0f);
        }

        // ── Decision Engine ──

        private struct DecisionResult
        {
            public string animation;
            public string gesture;
        }

        private DecisionResult MakeDecision(Vector3? cameraPosition)
        {
            var cfg = config;

            if (_intentionalGoal.HasValue && Time.time < _intentionalExpiry)
                return default;

            // Spontaneity: rare micro-gesture without state change
            if (UnityEngine.Random.value < cfg.spontaneity)
            {
                return new DecisionResult { gesture = IDLE_GESTURES[UnityEngine.Random.Range(0, IDLE_GESTURES.Length)] };
            }

            // Rank priorities: Social > Express > Rest > Explore > Move
            var urgencies = new Dictionary<string, float>
            {
                { "social",  drives.social * drives.energy * 1.5f },
                { "express", drives.expressiveness * drives.energy * 1.2f },
                { "rest",    (1f - drives.energy) * 1.3f },
                { "explore", drives.curiosity * drives.energy * 0.5f },
                { "move",    drives.restlessness * drives.energy * 0.3f },
            };

            // Strong emotion overrides
            if (Array.IndexOf(STRONG_EMOTIONS, emotionalState) >= 0 && awareness.timeInSameEmotion < 8f)
                urgencies["express"] *= 2.0f;

            // Find highest priority
            float maxUrgency = 0f;
            string action = "idle";
            foreach (var kvp in urgencies)
            {
                if (kvp.Value > maxUrgency) { maxUrgency = kvp.Value; action = kvp.Key; }
            }

            switch (action)
            {
                case "social":
                    drives.social *= 0.3f;
                    TransitionTo(BehaviorState.SocialTurn);
                    return new DecisionResult { gesture = "nod" };

                case "express":
                    {
                        string[] exprs = { "happy", "curious", "thinking", "surprised" };
                        string emotion = exprs[UnityEngine.Random.Range(0, exprs.Length)];
                        drives.expressiveness *= 0.4f;
                        awareness.timeInSameEmotion = 0f;
                        TransitionTo(BehaviorState.EmotionalBurst);
                        return new DecisionResult { animation = EMOTION_ANIM_MAP.GetValueOrDefault(emotion, "Idle") };
                    }

                case "explore":
                    {
                        float angle = UnityEngine.Random.Range(0f, Mathf.PI * 2f);
                        float dist = 0.5f + UnityEngine.Random.Range(0f, cfg.preferredStepDistance);
                        Vector3 target = new(
                            homePosition.x + Mathf.Cos(angle) * dist,
                            homePosition.y,
                            homePosition.z + Mathf.Sin(angle) * dist
                        );
                        _moveTarget = target;
                        _isReturningHome = false;
                        drives.curiosity *= 0.5f;
                        awareness.timeSinceLastMove = 0f;
                        TransitionTo(BehaviorState.CuriousStep);
                        return new DecisionResult { animation = "Walk" };
                    }

                case "move":
                    {
                        float angle = UnityEngine.Random.Range(0f, Mathf.PI * 2f);
                        float dist = 0.5f + UnityEngine.Random.Range(0f, 1.0f);
                        Vector3 target = new(
                            homePosition.x + Mathf.Cos(angle) * dist,
                            homePosition.y,
                            homePosition.z + Mathf.Sin(angle) * dist
                        );
                        _moveTarget = target;
                        _isReturningHome = false;
                        drives.restlessness *= 0.3f;
                        awareness.timeSinceLastMove = 0f;
                        TransitionTo(BehaviorState.WanderNearby);
                        return new DecisionResult { animation = "Walk" };
                    }

                case "rest":
                    TransitionTo(BehaviorState.Resting);
                    return new DecisionResult { gesture = "tilt", animation = "Idle" };

                default:
                    if (UnityEngine.Random.value > 0.7f)
                        return new DecisionResult { gesture = IDLE_GESTURES[UnityEngine.Random.Range(0, IDLE_GESTURES.Length)] };
                    TransitionTo(BehaviorState.CalmIdle);
                    return default;
            }
        }

        // ── State Transitions ──

        private void TransitionTo(BehaviorState newState)
        {
            if (behaviorState == newState) return;
            var oldState = behaviorState;
            behaviorState = newState;
            awareness.timeInCurrentState = 0f;

            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Movement] {oldState} -> {newState}");

            // Schedule return home after wander states
            if (newState == BehaviorState.WanderNearby || newState == BehaviorState.CuriousStep)
            {
                _returnHomeScheduled = true;
                _returnHomeTimer = config.returnHomeDelay;
            }
        }

        private void StartReturnHome()
        {
            if (_moveTarget.HasValue) return;
            _moveTarget = homePosition;
            _isReturningHome = true;
            TransitionTo(BehaviorState.ReturningHome);
        }

        // ── Feedback ──

        private void DispatchArrivalFeedback()
        {
            onBodyFeedback?.Invoke("Successfully arrived at intended destination.", true, homePosition);
            FoveAI.DebugOverlay.QuestDebugOverlay.Log("[Movement] Navigation target reached (feedback sent).");
        }

        private void DispatchFailureFeedback(string reason)
        {
            onBodyFeedback?.Invoke($"Failed to arrive: {reason}", false, homePosition);
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Movement] Navigation failed: {reason}");
        }

        // ── Config hot-reload ──

        public void UpdateConfig(MovementConfig partial) => config = partial;
        public MovementConfig GetConfig() => config;

        /// <summary>Diagnostic status string for HUD/debug overlay.</summary>
        public string GetStatusText()
        {
            return $"State: {behaviorState} | Emotion: {emotionalState} | " +
                   $"Walking: {_isWalking} | Returning: {_isReturningHome} | " +
                   $"Energy: {drives.energy:F2} | Social: {drives.social:F2} | " +
                   $"Curiosity: {drives.curiosity:F2}";
        }
    }
}
