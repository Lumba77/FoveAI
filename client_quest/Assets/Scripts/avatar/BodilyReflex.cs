using UnityEngine;

namespace FoveAI.Avatar
{
    /// <summary>
    /// BodilyReflex — Ported from Frontend/XR_Vessel/src/avatar/BodilyReflex.ts
    /// The Cerebellum / Autonomic Layer for the VRM avatar.
    ///
    /// Handles sub-second reflexes: breathing, gaze shifts, posture corrections,
    /// micro-gesture smoothing, emotional tremor. Runs autonomously — no LLM needed.
    /// Provides sensory body-state to the LLM for its next reasoning turn.
    /// </summary>
    public class BodilyReflex : MonoBehaviour
    {
        // ── Reflex State ──
        [System.Serializable]
        public struct ReflexState
        {
            // Physiological (autonomic)
            [Range(60f, 120f)] public float heartRate;        // bpm, emotion-modulated
            [Range(0f, 1f)] public float breathDepth;         // 0-1, shallow ↔ deep
            public float breathRate;                          // 0.5-2.0 multiplier
            [Range(0f, 1f)] public float pupilDilation;       // arousal indicator
            [Range(0f, 1f)] public float muscleTone;          // relaxed ↔ tense

            // Postural (cerebellar)
            [Range(-1f, 1f)] public float balanceShift;       // left ↔ right weight shift
            public float spineCurvature;                      // -0.05 to 0.05, slouched ↔ upright
            [Range(0f, 1f)] public float shoulderTension;     // relaxed ↔ raised

            // Attentional (orienting)
            [Range(0f, 1f)] public float gazeFocus;           // wandering ↔ locked on target
            public Vector3 headOrientation;                   // euler angles
            public Vector3? attentionTarget;                  // world position or null

            // Emotional (somatic markers)
            [Range(0f, 1f)] public float emotionalTremor;     // micro-tremble amplitude
            [Range(0f, 1f)] public float expressionDrift;     // how much face drifts toward resting
            [Range(0f, 1f)] public float socialWarmth;        // warmth of body language

            // Directive queue (from LLM)
            public string activeDirective;                    // null = idle
            [Range(0f, 1f)] public float directiveProgress;   // completion of current directive
        }

        // ── Reflex Config ──
        [System.Serializable]
        public struct ReflexConfig
        {
            [Range(5f, 30f)] public float reflexTickRate;     // Hz
            public float directiveTimeout;                    // seconds

            public float restingHeartRate;
            public float excitedHeartRate;
            public float restingBreathRate;
            public float excitedBreathRate;

            public float defaultSpineCurvature;
            public float maxBalanceShift;

            public float defaultGazeFocus;
            public float attentionGazeFocus;

            public float tremorBaseAmplitude;
            public float expressionRestoreRate;
        }

        [Header("Reflex Config")]
        public ReflexConfig config = new()
        {
            reflexTickRate = 10f,
            directiveTimeout = 30f,
            restingHeartRate = 68f,
            excitedHeartRate = 105f,
            restingBreathRate = 1.0f,
            excitedBreathRate = 1.6f,
            defaultSpineCurvature = -0.02f,
            maxBalanceShift = 0.03f,
            defaultGazeFocus = 0.3f,
            attentionGazeFocus = 0.9f,
            tremorBaseAmplitude = 0.003f,
            expressionRestoreRate = 0.02f,
        };

        [Header("Current State (Read-only)")]
        public ReflexState state;

        // ── Callbacks ──
        public System.Action<ReflexState> onPhysiologyUpdate;
        public System.Action<string> onDirectiveComplete;

        // ── Internal ──
        private float _time;
        private float _reflexAccumulator;
        private float _directiveClearTimer;

        // ── Emotion → Physiology mapping ──
        private struct EmotionPhysio
        {
            public float? heartRate, breathRate, muscleTone, pupilDilation, socialWarmth;
            public float? spineCurvature, gazeFocus, emotionalTremor;
        }

        private static readonly System.Collections.Generic.Dictionary<string, EmotionPhysio> EMOTION_PHYSIOLOGY = new()
        {
            { "neutral",   new EmotionPhysio { heartRate = 68f, breathRate = 1.0f, muscleTone = 0.2f, pupilDilation = 0.2f, socialWarmth = 0.4f } },
            { "happy",     new EmotionPhysio { heartRate = 80f, breathRate = 1.2f, muscleTone = 0.3f, pupilDilation = 0.4f, socialWarmth = 0.8f, emotionalTremor = 0.02f } },
            { "excited",   new EmotionPhysio { heartRate = 95f, breathRate = 1.5f, muscleTone = 0.5f, pupilDilation = 0.6f, socialWarmth = 0.9f, emotionalTremor = 0.04f } },
            { "sad",       new EmotionPhysio { heartRate = 62f, breathRate = 0.7f, muscleTone = 0.15f, pupilDilation = 0.1f, socialWarmth = 0.3f, spineCurvature = 0.04f } },
            { "angry",     new EmotionPhysio { heartRate = 100f, breathRate = 1.4f, muscleTone = 0.8f, pupilDilation = 0.5f, socialWarmth = 0.1f } },
            { "curious",   new EmotionPhysio { heartRate = 75f, breathRate = 1.1f, muscleTone = 0.3f, pupilDilation = 0.5f, socialWarmth = 0.6f, gazeFocus = 0.7f } },
            { "surprised", new EmotionPhysio { heartRate = 90f, breathRate = 1.3f, muscleTone = 0.6f, pupilDilation = 0.7f, socialWarmth = 0.5f, emotionalTremor = 0.03f } },
            { "concerned", new EmotionPhysio { heartRate = 72f, breathRate = 0.9f, muscleTone = 0.4f, pupilDilation = 0.3f, socialWarmth = 0.6f } },
            { "calm",      new EmotionPhysio { heartRate = 62f, breathRate = 0.7f, muscleTone = 0.1f, pupilDilation = 0.1f, socialWarmth = 0.5f, gazeFocus = 0.2f } },
            { "thinking",  new EmotionPhysio { heartRate = 70f, breathRate = 0.9f, muscleTone = 0.2f, pupilDilation = 0.3f, socialWarmth = 0.4f, gazeFocus = 0.1f } },
        };

        private void Awake()
        {
            state = CreateDefaultState();
        }

        private ReflexState CreateDefaultState()
        {
            return new ReflexState
            {
                heartRate = config.restingHeartRate,
                breathDepth = 0.5f,
                breathRate = config.restingBreathRate,
                pupilDilation = 0.2f,
                muscleTone = 0.2f,
                balanceShift = 0f,
                spineCurvature = config.defaultSpineCurvature,
                shoulderTension = 0.15f,
                gazeFocus = config.defaultGazeFocus,
                headOrientation = Vector3.zero,
                attentionTarget = null,
                emotionalTremor = 0f,
                expressionDrift = 0f,
                socialWarmth = 0.4f,
                activeDirective = null,
                directiveProgress = 0f,
            };
        }

        // ── Public API ──

        /// <summary>Get current reflex state snapshot.</summary>
        public ReflexState GetState() => state;

        /// <summary>Set emotional state — triggers physiological cascade.</summary>
        public void SetEmotion(string emotion, float intensity = 1.0f)
        {
            if (!EMOTION_PHYSIOLOGY.TryGetValue(emotion.ToLower(), out var phys))
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Reflex] Unknown emotion: {emotion}");
                return;
            }

            if (phys.heartRate.HasValue) state.heartRate = Mathf.Lerp(config.restingHeartRate, phys.heartRate.Value, intensity);
            if (phys.breathRate.HasValue) state.breathRate = Mathf.Lerp(1.0f, phys.breathRate.Value, intensity);
            if (phys.muscleTone.HasValue) state.muscleTone = phys.muscleTone.Value * intensity;
            if (phys.pupilDilation.HasValue) state.pupilDilation = phys.pupilDilation.Value * intensity;
            if (phys.socialWarmth.HasValue) state.socialWarmth = phys.socialWarmth.Value * intensity;
            if (phys.spineCurvature.HasValue) state.spineCurvature = phys.spineCurvature.Value * intensity;
            if (phys.gazeFocus.HasValue) state.gazeFocus = phys.gazeFocus.Value * intensity;
            if (phys.emotionalTremor.HasValue) state.emotionalTremor = phys.emotionalTremor.Value * intensity;

            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Reflex] Physiology set to {emotion} (intensity={intensity})");
        }

        /// <summary>Receive a high-level directive from the LLM.</summary>
        public void ReceiveDirective(string directive, object data = null)
        {
            state.activeDirective = directive;
            state.directiveProgress = 0f;
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Reflex] Directive received: {directive}");
        }

        /// <summary>Is the body currently executing a directive?</summary>
        public bool IsBusy() => !string.IsNullOrEmpty(state.activeDirective) && state.directiveProgress < 1.0f;

        /// <summary>Generate body-awareness text for LLM sensory context.</summary>
        public string GetBodyAwarenessText()
        {
            string directives = !string.IsNullOrEmpty(state.activeDirective)
                ? $"Currently executing: {state.activeDirective} ({Mathf.RoundToInt(state.directiveProgress * 100)}% complete)"
                : "No active directive — receptive to commands";

            string physiology = $"HR: {Mathf.RoundToInt(state.heartRate)} bpm | " +
                $"Breath: {state.breathRate:F1}x | " +
                $"Gaze: {(state.gazeFocus * 100):F0}% | " +
                $"Tone: {(state.muscleTone * 100):F0}% | " +
                $"Warmth: {(state.socialWarmth * 100):F0}% | " +
                $"Spine: {(state.spineCurvature > 0 ? "slouched" : "upright")}";

            return $"[BODY AWARENESS]\n{directives}\nPhysiology: {physiology}";
        }

        // ── Core Tick ──

        private void Update()
        {
            float delta = Time.deltaTime;
            _time += delta;
            _reflexAccumulator += delta;

            float tickInterval = 1.0f / config.reflexTickRate;

            while (_reflexAccumulator >= tickInterval)
            {
                _reflexAccumulator -= tickInterval;
                TickReflexes(tickInterval);
            }

            // Directive clear timer
            if (_directiveClearTimer > 0f)
            {
                _directiveClearTimer -= delta;
                if (_directiveClearTimer <= 0f)
                {
                    state.activeDirective = null;
                }
            }
        }

        private void TickReflexes(float delta)
        {
            var s = state;
            var cfg = config;

            // 1. Heart rate: slowly returns to baseline
            s.heartRate += (cfg.restingHeartRate - s.heartRate) * delta * 0.3f;

            // 2. Breath: modulate by activity level
            s.breathRate += (cfg.restingBreathRate - s.breathRate) * delta * 0.5f;
            s.breathDepth = Mathf.Sin(_time * s.breathRate * Mathf.PI) * 0.5f + 0.5f;

            // 3. Balance: natural micro-shifts
            float balanceTarget = Mathf.Sin(_time * 0.3f) * cfg.maxBalanceShift * 0.5f;
            s.balanceShift += (balanceTarget - s.balanceShift) * delta * 2.0f;

            // 4. Muscle tone: decays toward baseline
            s.muscleTone += (0.2f - s.muscleTone) * delta * 0.4f;
            s.shoulderTension += (0.15f - s.shoulderTension) * delta * 0.3f;

            // 5. Spine curvature: natural drift
            s.spineCurvature += (cfg.defaultSpineCurvature - s.spineCurvature) * delta * 0.2f;

            // 6. Gaze focus: decays toward default
            float gazeTarget = s.attentionTarget.HasValue ? cfg.attentionGazeFocus : cfg.defaultGazeFocus;
            s.gazeFocus += (gazeTarget - s.gazeFocus) * delta * 2.0f;

            // 7. Expression: slowly restores to neutral
            s.expressionDrift += cfg.expressionRestoreRate * delta;
            s.expressionDrift = Mathf.Min(1.0f, s.expressionDrift);

            // 8. Emotional tremor: decays
            s.emotionalTremor *= (1f - delta * 1.5f);
            if (s.emotionalTremor < cfg.tremorBaseAmplitude)
                s.emotionalTremor = cfg.tremorBaseAmplitude;

            // 9. Social warmth: decays toward baseline
            s.socialWarmth += (0.4f - s.socialWarmth) * delta * 0.15f;

            // 10. Directive progress
            if (!string.IsNullOrEmpty(s.activeDirective) && s.directiveProgress < 1.0f)
            {
                bool isMovement = s.activeDirective == "walk_forward" || s.activeDirective == "move_to";
                float progressRate = isMovement ? 0f : 1.0f / 3.0f; // 3s for expressive directives
                s.directiveProgress += progressRate * delta;

                if (s.directiveProgress >= 1.0f)
                {
                    s.directiveProgress = 1.0f;
                    onDirectiveComplete?.Invoke(s.activeDirective);
                    FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Reflex] Directive complete: {s.activeDirective}");

                    if (!isMovement)
                        _directiveClearTimer = 0.5f; // Clear after 500ms
                }
            }

            state = s;
            onPhysiologyUpdate?.Invoke(state);
        }

        // ── Directive Result Feedback ──

        /// <summary>Called by AvatarPuppetDriver/MovementEngine when a movement completes.</summary>
        public void OnMovementComplete()
        {
            if (!string.IsNullOrEmpty(state.activeDirective) &&
                (state.activeDirective == "walk_forward" || state.activeDirective == "move_to"))
            {
                state.directiveProgress = 1.0f;
                onDirectiveComplete?.Invoke(state.activeDirective);
                FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[Reflex] Movement directive complete: {state.activeDirective}");
                _directiveClearTimer = 0.5f;
            }
        }

        /// <summary>Called when an emotion animation finishes.</summary>
        public void OnExpressionComplete()
        {
            state.expressionDrift = 0f;
        }

        /// <summary>Set attention target for gaze focus.</summary>
        public void SetAttentionTarget(Vector3? target)
        {
            state.attentionTarget = target;
        }
    }
}
