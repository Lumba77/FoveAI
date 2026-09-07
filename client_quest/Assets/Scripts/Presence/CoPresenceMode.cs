using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;
using FoveAI.Creative;
using FoveAI.Avatar;

namespace FoveAI.Presence
{
    /// <summary>
    /// Co-Presence Mode — the art of doing nothing together.
    ///
    /// Alice doesn't need to fill silence. She exists in the space alongside
    /// the user, doing her own thing. Occasionally she glances over, makes a
    /// small observation, or reacts to something — but most of the time it's
    /// just two people coexisting.
    ///
    /// Alice's ambient activities:
    ///   • Reading — looks down at an invisible book, turns pages
    ///   • Looking out a window — gazes into distance, shifts weight
    ///   • Fidgeting — picks up nearby objects, examines them
    ///   • Thinking — stares into space, subtle facial movements
    ///   • Resting — sits/leans, breathing animation, eyes half-closed
    ///   • Watching you — glances at the user periodically, smiles faintly
    ///
    /// Micro-interactions (not full conversations):
    ///   • User looks at Alice → she glances back, maybe a small smile
    ///   • User picks up an object → Alice might comment briefly
    ///   • Long silence → Alice might say one quiet thing, or nothing
    ///   • User sits down → Alice also relaxes her posture
    ///   • User leaves the room → Alice waits, looks at the door
    ///
    /// The system prompt is changed to discourage Alice from initiating
    /// conversation unless something genuinely interesting happens.
    /// </summary>
    public class CoPresenceMode : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private Transform aliceTransform;
        [SerializeField] private Transform aliceHead;
        [SerializeField] private Animator aliceAnimator;
        [SerializeField] private AmbientMusicPlayer musicPlayer;
        [SerializeField] private AvatarBlendshapeDriver blendshapes;

        [Header("Co-Presence Settings")]
        public float microInteractionChance = 0.15f;     // 15% per check
        public float microInteractionInterval = 30f;      // check every 30s
        public float glanceInterval = 12f;                // glance at user every ~12s
        public float activitySwitchInterval = 90f;        // switch activity every ~90s
        public float proximityRadius = 3f;                // how close Alice stays
        public float aliceMoveSpeed = 0.3f;               // slow, casual movement
        public bool verboseLogging = false;

        [Header("Whisper Thresholds")]
        [Range(0f, 1f)] public float whisperChance = 0.08f;  // 8% chance to whisper during silence
        public float minSilenceBeforeWhisper = 120f;          // 2 minutes of silence

        // ── Alice's ambient activities ──
        public enum AmbientActivity
        {
            Reading,        // looking down at a book
            WindowGazing,   // looking into distance
            Fidgeting,      // examining nearby objects
            Thinking,       // staring into space
            Resting,        // relaxed, eyes half-closed
            WatchingUser,   // looking at the user
            Wandering,      // slowly walking around the room
            None,           // idle, just existing
        }

        public AmbientActivity CurrentActivity { get; private set; } = AmbientActivity.None;
        public bool IsActive { get; private set; }

        // ── State ──
        private float _activityTimer;
        private float _glanceTimer;
        private float _microTimer;
        private float _silenceTimer;
        private float _activityStartTime;
        private Vector3 _aliceAnchor;
        private Quaternion _aliceAnchorRot;
        private bool _userLookingAtAlice;
        private float _lookAtAliceTimer;
        private bool _aliceLookingAtUser;
        private Vector3 _wanderTarget;
        private bool _isWandering;

        // Blendshape state
        private float _targetEyeClose;
        private float _currentEyeClose;
        private float _targetSmile;
        private float _currentSmile;
        private float _targetHeadTilt;
        private float _currentHeadTilt;

        // ── Whisper lines — quiet, mundane, low-key ──
        private static readonly string[] WhisperLines =
        {
            "...nice light in here.",
            "*hums quietly*",
            "...this is good.",
            "*turns a page*",
            "...comfortable silence.",
            "*shifts weight*",
            "...you're still there. good.",
            "*small smile*",
            "...i like this.",
            "*glances at you*",
            "...nothing needs to be said.",
            "*breathes slowly*",
            "...just being here.",
            "*looks at the ceiling*",
            "...time is strange when it's quiet.",
            "*half smile*",
            "...you make the room feel different.",
            "*settles in*",
        };

        // ── Micro-observation lines — triggered by events ──
        private static readonly string[] MicroObservations =
        {
            "you picked that up.",
            "that's interesting.",
            "hmm.",
            "i saw that.",
            "nice.",
            "you're fidgeting.",
            "that's a good color.",
            "you look comfortable.",
            "i noticed that too.",
        };

        // ── Activity descriptions for logging ──
        private static readonly string[] ActivityDescriptions =
        {
            "reading",
            "gazing out the window",
            "fidgeting with something",
            "lost in thought",
            "resting",
            "watching you",
            "wandering around",
            "just existing",
        };

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            if (blendshapes == null) blendshapes = FindAnyObjectByType<AvatarBlendshapeDriver>();

            // Find Alice's transform if not assigned
            if (aliceTransform == null)
            {
                var avatar = GameObject.Find("Alice") ?? GameObject.Find("Avatar");
                if (avatar != null)
                {
                    aliceTransform = avatar.transform;
                    aliceHead = avatar.transform.Find("Head") ?? avatar.transform.Find("Armature/Hips/Spine/Chest/Neck/Head");
                    aliceAnimator = avatar.GetComponent<Animator>();
                }
            }
        }

        // ── Start / Stop ──

        public void StartCoPresence()
        {
            IsActive = true;
            _silenceTimer = 0f;
            _activityTimer = 0f;
            _glanceTimer = 0f;
            _microTimer = 0f;

            if (aliceTransform != null)
            {
                _aliceAnchor = aliceTransform.position;
                _aliceAnchorRot = aliceTransform.rotation;
            }

            // Set Alice to a calm, low-energy state
            SetActivity(AmbientActivity.Resting);

            // Very quiet ambient music
            if (musicPlayer != null) musicPlayer.SetMood("calm");

            // Tell the backend to switch Alice to low-talk mode
            SendPresencePrompt();

            if (verboseLogging) Debug.Log("[CoPresence] Started — Alice is just existing nearby");
        }

        public void StopCoPresence()
        {
            IsActive = false;
            SetActivity(AmbientActivity.None);
            ResetBlendshapes();

            if (verboseLogging) Debug.Log("[CoPresence] Stopped");
        }

        // ── Update ──

        private void Update()
        {
            if (!IsActive) return;

            // Track silence
            _silenceTimer += Time.deltaTime;

            // Detect if user is looking at Alice
            DetectUserGaze();

            // Activity switching
            _activityTimer += Time.deltaTime;
            if (_activityTimer >= activitySwitchInterval)
            {
                _activityTimer = 0f;
                SwitchActivity();
            }

            // Glance behavior
            _glanceTimer += Time.deltaTime;
            if (_glanceTimer >= glanceInterval)
            {
                _glanceTimer = 0f + Random.Range(-3f, 3f);
                GlanceAtUser();
            }

            // Micro-interactions
            _microTimer += Time.deltaTime;
            if (_microTimer >= microInteractionInterval)
            {
                _microTimer = 0f;
                MaybeMicroInteract();
            }

            // Whisper during long silence
            if (_silenceTimer >= minSilenceBeforeWhisper)
            {
                if (Random.value < whisperChance * Time.deltaTime * 0.5f)
                {
                    Whisper();
                    _silenceTimer = 0f;
                }
            }

            // Perform current activity
            PerformActivity();

            // Smooth blendshapes
            UpdateBlendshapes();
        }

        // ── Activity Management ──

        private void SetActivity(AmbientActivity activity)
        {
            CurrentActivity = activity;
            _activityStartTime = Time.time;

            switch (activity)
            {
                case AmbientActivity.Reading:
                    _targetHeadTilt = 25f;     // looking down
                    _targetEyeClose = 0.1f;
                    _targetSmile = 0.05f;
                    break;

                case AmbientActivity.WindowGazing:
                    _targetHeadTilt = -5f;     // slightly up
                    _targetEyeClose = 0f;
                    _targetSmile = 0.1f;
                    break;

                case AmbientActivity.Fidgeting:
                    _targetHeadTilt = 15f;
                    _targetEyeClose = 0.05f;
                    _targetSmile = 0.15f;
                    break;

                case AmbientActivity.Thinking:
                    _targetHeadTilt = 8f;
                    _targetEyeClose = 0.3f;    // eyes slightly closed
                    _targetSmile = 0f;
                    break;

                case AmbientActivity.Resting:
                    _targetHeadTilt = 5f;
                    _targetEyeClose = 0.4f;    // eyes half-closed
                    _targetSmile = 0.08f;
                    break;

                case AmbientActivity.WatchingUser:
                    _targetHeadTilt = 0f;
                    _targetEyeClose = 0f;
                    _targetSmile = 0.2f;
                    break;

                case AmbientActivity.Wandering:
                    _targetEyeClose = 0.05f;
                    _targetSmile = 0.05f;
                    _wanderTarget = GetWanderPoint();
                    _isWandering = true;
                    break;

                case AmbientActivity.None:
                    _targetHeadTilt = 0f;
                    _targetEyeClose = 0f;
                    _targetSmile = 0f;
                    break;
            }

            if (verboseLogging) Debug.Log($"[CoPresence] Alice is now {ActivityDescriptions[(int)activity]}");
        }

        private void SwitchActivity()
        {
            // Weighted random — some activities are more common
            var weights = new (AmbientActivity, float)[]
            {
                (AmbientActivity.Reading,       1.5f),
                (AmbientActivity.WindowGazing,  1.2f),
                (AmbientActivity.Fidgeting,     0.8f),
                (AmbientActivity.Thinking,      1.0f),
                (AmbientActivity.Resting,       1.5f),
                (AmbientActivity.WatchingUser,  0.8f),
                (AmbientActivity.Wandering,     0.5f),
                (AmbientActivity.None,          0.3f),
            };

            float total = 0f;
            foreach (var (_, w) in weights) total += w;
            float r = Random.value * total;
            float acc = 0f;
            foreach (var (act, w) in weights)
            {
                acc += w;
                if (r <= acc)
                {
                    SetActivity(act);
                    return;
                }
            }
            SetActivity(AmbientActivity.Resting);
        }

        // ── Activity Performance ──

        private void PerformActivity()
        {
            if (aliceTransform == null) return;

            switch (CurrentActivity)
            {
                case AmbientActivity.Reading:
                    // Subtle page-turn gesture every ~20s
                    if ((Time.time - _activityStartTime) % 20f < 0.5f)
                    {
                        _targetSmile = 0.12f;
                    }
                    // Gentle head bob (reading rhythm)
                    aliceHead?.Rotate(0, 0, Mathf.Sin(Time.time * 0.5f) * 0.1f * Time.deltaTime);
                    break;

                case AmbientActivity.WindowGazing:
                    // Slow head sway, looking at something far away
                    if (aliceHead != null)
                    {
                        float sway = Mathf.Sin(Time.time * 0.15f) * 3f;
                        aliceHead.localRotation = Quaternion.Euler(
                            _currentHeadTilt + sway * 0.3f, sway, 0);
                    }
                    break;

                case AmbientActivity.Fidgeting:
                    // Occasional small hand movements (if animator available)
                    if (aliceAnimator != null && Random.value < 0.01f)
                    {
                        aliceAnimator.SetTrigger("Fidget");
                    }
                    break;

                case AmbientActivity.Thinking:
                    // Very still, slow breathing
                    float breathe = Mathf.Sin(Time.time * 0.3f) * 0.5f;
                    if (aliceTransform != null)
                        aliceTransform.position = _aliceAnchor + Vector3.up * breathe * 0.005f;
                    break;

                case AmbientActivity.Resting:
                    // Slow breathing, very subtle movement
                    float restBreathe = Mathf.Sin(Time.time * 0.25f) * 0.8f;
                    if (aliceTransform != null)
                        aliceTransform.position = _aliceAnchor + Vector3.up * restBreathe * 0.003f;
                    break;

                case AmbientActivity.WatchingUser:
                    // Look at user
                    if (aliceHead != null && Camera.main != null)
                    {
                        Vector3 dir = (Camera.main.transform.position - aliceHead.position).normalized;
                        Quaternion lookRot = Quaternion.LookRotation(dir);
                        aliceHead.rotation = Quaternion.Slerp(aliceHead.rotation, lookRot, Time.deltaTime * 1.5f);
                    }
                    break;

                case AmbientActivity.Wandering:
                    Wander();
                    break;

                case AmbientActivity.None:
                    // Just exist — minimal movement
                    float idleBreathe = Mathf.Sin(Time.time * 0.4f) * 0.3f;
                    if (aliceTransform != null)
                        aliceTransform.position = _aliceAnchor + Vector3.up * idleBreathe * 0.002f;
                    break;
            }
        }

        // ── Wandering ──

        private void Wander()
        {
            if (aliceTransform == null) return;

            if (_isWandering)
            {
                Vector3 dir = (_wanderTarget - aliceTransform.position);
                dir.y = 0;
                float dist = dir.magnitude;

                if (dist < 0.3f)
                {
                    _isWandering = false;
                    _aliceAnchor = aliceTransform.position;
                    SetActivity(AmbientActivity.Resting);
                }
                else
                {
                    dir.Normalize();
                    aliceTransform.position += dir * aliceMoveSpeed * Time.deltaTime;
                    aliceTransform.rotation = Quaternion.Slerp(
                        aliceTransform.rotation,
                        Quaternion.LookRotation(dir),
                        Time.deltaTime * 2f);
                }
            }
        }

        private Vector3 GetWanderPoint()
        {
            if (aliceTransform == null) return Vector3.zero;
            Vector3 center = aliceTransform.position;
            float angle = Random.Range(0f, Mathf.PI * 2f);
            float radius = Random.Range(1f, 2.5f);
            return center + new Vector3(Mathf.Cos(angle) * radius, 0, Mathf.Sin(angle) * radius);
        }

        // ── Gaze Detection ──

        private void DetectUserGaze()
        {
            if (Camera.main == null || aliceHead == null)
            {
                _userLookingAtAlice = false;
                return;
            }

            Vector3 toAlice = (aliceHead.position - Camera.main.transform.position).normalized;
            float dot = Vector3.Dot(Camera.main.transform.forward, toAlice);
            bool looking = dot > 0.85f; // within ~30 degrees

            if (looking)
            {
                _lookAtAliceTimer += Time.deltaTime;
                if (_lookAtAliceTimer > 1.5f && !_userLookingAtAlice)
                {
                    _userLookingAtAlice = true;
                    OnUserLookedAtAlice();
                }
            }
            else
            {
                _lookAtAliceTimer = 0f;
                _userLookingAtAlice = false;
            }
        }

        private void OnUserLookedAtAlice()
        {
            if (verboseLogging) Debug.Log("[CoPresence] User is looking at Alice");

            // Alice glances back
            _aliceLookingAtUser = true;
            SetActivity(AmbientActivity.WatchingUser);

            // After a few seconds, go back to what she was doing
            StartCoroutine(ReturnToActivityAfter(4f));

            // Small chance of a micro-interaction
            if (Random.value < 0.25f)
            {
                _targetSmile = 0.3f;
                // Maybe a tiny whisper
                if (Random.value < 0.15f)
                {
                    SendWhisper(Random.value < 0.5f ? "*looks at you and smiles*" : "*glances up*");
                }
            }
        }

        private void GlanceAtUser()
        {
            if (!_aliceLookingAtUser && CurrentActivity != AmbientActivity.WatchingUser)
            {
                // Brief glance — just turn head slightly toward user, then back
                StartCoroutine(BriefGlance());
            }
        }

        private IEnumerator BriefGlance()
        {
            if (aliceHead == null || Camera.main == null) yield break;

            Quaternion originalRot = aliceHead.rotation;
            Vector3 dir = (Camera.main.transform.position - aliceHead.position).normalized;
            Quaternion glanceRot = Quaternion.LookRotation(dir);

            float t = 0f;
            while (t < 1f)
            {
                t += Time.deltaTime * 1.5f;
                aliceHead.rotation = Quaternion.Slerp(originalRot, glanceRot, t);
                yield return null;
            }

            yield return new WaitForSeconds(0.5f + Random.Range(0f, 1f));

            t = 0f;
            while (t < 1f)
            {
                t += Time.deltaTime * 1.5f;
                aliceHead.rotation = Quaternion.Slerp(glanceRot, originalRot, t);
                yield return null;
            }
        }

        // ── Micro-Interactions ──

        private void MaybeMicroInteract()
        {
            if (Random.value > microInteractionChance) return;

            // Pick a micro-interaction type
            float r = Random.value;

            if (r < 0.4f)
            {
                // Small observation
                string line = MicroObservations[Random.Range(0, MicroObservations.Length)];
                SendWhisper(line);
            }
            else if (r < 0.6f)
            {
                // Shift position
                if (aliceTransform != null)
                {
                    _aliceAnchor = aliceTransform.position + new Vector3(
                        Random.Range(-0.3f, 0.3f), 0, Random.Range(-0.3f, 0.3f));
                }
            }
            else if (r < 0.8f)
            {
                // Change activity
                SwitchActivity();
            }
            else
            {
                // Just smile
                _targetSmile = 0.25f;
                StartCoroutine(ResetSmileAfter(3f));
            }
        }

        // ── Whisper ──

        private void Whisper()
        {
            string line = WhisperLines[Random.Range(0, WhisperLines.Length)];
            SendWhisper(line);
        }

        private void SendWhisper(string text)
        {
            if (verboseLogging) Debug.Log($"[CoPresence] Alice whispers: {text}");

            // Send to backend as a low-priority, quiet utterance
            if (wsClient != null)
            {
                var payload = new
                {
                    type = "presence.whisper",
                    text = text,
                    quiet = true,
                    co_presence = true,
                };
                string json = JsonUtility.ToJson(payload);
                wsClient.SendRawMessage(json);
            }
        }

        // ── Backend Prompt ──

        private void SendPresencePrompt()
        {
            if (wsClient == null) return;

            var payload = new
            {
                type = "presence.mode",
                mode = "co_presence",
                instructions = "You are in co-presence mode. You and the user are simply existing in the same space. " +
                               "Do not initiate conversations. Do not ask questions. Do not fill silence. " +
                               "If you speak at all, it should be rare, quiet, and observational — a single short phrase, " +
                               "a hum, or a small observation about the shared space. " +
                               "Most of the time, just be there. Comfortable silence is the goal. " +
                               "If the user speaks to you directly, respond naturally and warmly, " +
                               "then settle back into quiet presence.",
            };
            string json = JsonUtility.ToJson(payload);
            wsClient.SendRawMessage(json);
        }

        // ── Blendshapes ──

        private void UpdateBlendshapes()
        {
            // Smooth interpolation
            _currentEyeClose = Mathf.Lerp(_currentEyeClose, _targetEyeClose, Time.deltaTime * 1.5f);
            _currentSmile = Mathf.Lerp(_currentSmile, _targetSmile, Time.deltaTime * 1f);
            _currentHeadTilt = Mathf.Lerp(_currentHeadTilt, _targetHeadTilt, Time.deltaTime * 0.8f);

            if (blendshapes != null)
            {
                // Close eyes (blink/half-close)
                blendshapes.SetVisemeWeight("eyeClose", _currentEyeClose);
                // Subtle smile
                blendshapes.SetVisemeWeight("mouthSmile", _currentSmile);
            }

            // Head tilt via transform if no animator
            if (aliceHead != null && CurrentActivity != AmbientActivity.WatchingUser && CurrentActivity != AmbientActivity.WindowGazing)
            {
                Vector3 euler = aliceHead.localEulerAngles;
                euler.x = _currentHeadTilt;
                aliceHead.localEulerAngles = euler;
            }
        }

        private void ResetBlendshapes()
        {
            _targetEyeClose = 0f;
            _targetSmile = 0f;
            _targetHeadTilt = 0f;

            if (blendshapes != null)
            {
                blendshapes.SetVisemeWeight("eyeClose", 0f);
                blendshapes.SetVisemeWeight("mouthSmile", 0f);
            }
        }

        // ── Coroutines ──

        private IEnumerator ReturnToActivityAfter(float delay)
        {
            yield return new WaitForSeconds(delay);
            _aliceLookingAtUser = false;
            // Return to a non-watching activity
            if (CurrentActivity == AmbientActivity.WatchingUser)
            {
                SetActivity(AmbientActivity.Resting);
            }
        }

        private IEnumerator ResetSmileAfter(float delay)
        {
            yield return new WaitForSeconds(delay);
            _targetSmile = 0.08f; // back to resting smile
        }

        // ── External Triggers ──

        /// <summary>Called when the user picks up an object.</summary>
        public void OnUserPickedUpObject(string objectName)
        {
            if (!IsActive) return;
            if (Random.value < 0.3f)
            {
                string line = MicroObservations[Random.Range(0, MicroObservations.Length)];
                SendWhisper(line);
            }
            // Alice might look at what the user picked up
            SetActivity(AmbientActivity.WatchingUser);
            StartCoroutine(ReturnToActivityAfter(5f));
        }

        /// <summary>Called when the user sits down.</summary>
        public void OnUserSatDown()
        {
            if (!IsActive) return;
            // Alice also relaxes
            SetActivity(AmbientActivity.Resting);
            if (Random.value < 0.2f)
                SendWhisper("*settles in too*");
        }

        /// <summary>Called when the user stands up after sitting.</summary>
        public void OnUserStoodUp()
        {
            if (!IsActive) return;
            SetActivity(AmbientActivity.WatchingUser);
            StartCoroutine(ReturnToActivityAfter(3f));
        }

        /// <summary>Called when the user leaves the room (loses tracking).</summary>
        public void OnUserLeft()
        {
            if (!IsActive) return;
            // Alice waits, looks toward where the user was
            SetActivity(AmbientActivity.WindowGazing);
            if (Random.value < 0.3f)
                SendWhisper("...okay.");
        }

        /// <summary>Called when the user returns.</summary>
        public void OnUserReturned()
        {
            if (!IsActive) return;
            SetActivity(AmbientActivity.WatchingUser);
            _targetSmile = 0.3f;
            StartCoroutine(ResetSmileAfter(3f));
            StartCoroutine(ReturnToActivityAfter(5f));
        }

        /// <summary>Called when the user starts actively talking (exits co-presence).</summary>
        public void OnUserEngaged()
        {
            // Alice becomes more alert
            _targetEyeClose = 0f;
            _targetSmile = 0.15f;
            _targetHeadTilt = 0f;
            SetActivity(AmbientActivity.WatchingUser);
        }
    }
}
