using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;
using FoveAI.Creative;
using FoveAI.Games;

namespace FoveAI.Experiences
{
    /// <summary>
    /// Director Engine — executes surprise narrative events orchestrated by the
    /// off-scene AI Director.
    ///
    /// The Director is a creative AI that:
    ///   • Reads summarized plots of your interactions with Alice
    ///   • Plans interesting events and scenes in advance
    ///   • Builds whole scenarios (horror, war, mystery, comedy, romance)
    ///   • Triggers them at surprising moments
    ///   • Develops scenes over time — they grow, escalate, resolve
    ///
    /// Event types the Director can trigger:
    ///   • Phone Ring     — a phone rings, someone calls, conversation ensues,
    ///                       then a character steps into the room
    ///   • Genre Shift    — suddenly you're in a horror movie, a war drama,
    ///                       a noir detective story, a romantic comedy
    ///   • Character Arrival — someone knocks, enters, has a scene with you
    ///   • Narration      — a narrator voice sets the scene, builds tension
    ///   • Prop Spawn     — objects appear that drive the narrative
    ///   • Atmosphere     — lighting, fog, music shift to match the genre
    ///   • Event Sequence — multi-step scripted events that unfold over time
    ///
    /// The Director works like a film director + improv coach + dungeon master:
    ///   • It builds tension slowly
    ///   • It pays off setups with payoffs
    ///   • It reads the room (your mood, time of day, conversation)
    ///   • It can escalate or de-escalate
    ///   • It knows when to end a scene
    /// </summary>
    public class DirectorEngine : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private AmbientMusicPlayer musicPlayer;
        [SerializeField] private ScenePresetManager presetManager;
        [SerializeField] private SeasonalTheming seasonalTheming;
        [SerializeField] private VirtualGuestSystem guestSystem;
        [SerializeField] private Transform aliceTransform;
        [SerializeField] private Transform aliceHead;

        [Header("Director Settings")]
        public bool directorEnabled = true;
        public float minEventInterval = 600f;    // 10 min minimum between events
        public float maxEventInterval = 1800f;   // 30 min maximum
        public float eventBuildTime = 5f;        // time to build atmosphere before event
        public bool allowHorror = true;
        public bool allowViolence = true;        // war/action scenes
        public float maxEventDuration = 600f;    // 10 min max per event

        // ── Genres ──
        public enum Genre
        {
            None,
            Horror,
            WarDrama,
            NoirMystery,
            RomanticComedy,
            SciFi,
            Fantasy,
            Western,
            SpyThriller,
            Documentary,
            SurrealDream,
            GameShow,
            Heist,
        }

        // ── Event Types ──
        public enum DirectorEventType
        {
            PhoneRing,
            CharacterArrival,
            GenreShift,
            Narration,
            PropSpawn,
            AtmosphereShift,
            EventSequence,
            Knock,
            Emergency,
            Celebration,
        }

        public Genre CurrentGenre { get; private set; } = Genre.None;
        public bool EventActive { get; private set; }
        public DirectorEventType CurrentEventType { get; private set; }

        // ── State ──
        private float _eventTimer;
        private float _nextEventTime;
        private GameObject _phone;
        private GameObject _currentProp;
        private GameObject _currentCharacter;
        private AudioSource _phoneAudio;
        private AudioSource _narratorAudio;
        private AudioSource _ambientAudio;
        private readonly List<GameObject> _sceneProps = new();
        private readonly List<Light> _sceneLights = new();
        private Color _originalAmbient;
        private float _originalLightIntensity;
        private Light _mainLight;
        private float _eventStartTime;
        private bool _genreActive;
        private Coroutine _activeEventCoroutine;

        // ── Genre Definitions ──
        private static readonly (string name, Color ambient, Color fog, float fogDensity,
            float lightIntensity, Color lightColor, string musicMood,
            string narratorIntro)[] GenreDefs =
        {
            // None
            ("None", Color.white, Color.white, 0f, 1f, Color.white, "calm", ""),
            // Horror
            ("Horror", new Color(0.08f, 0.05f, 0.05f), new Color(0.05f, 0.02f, 0.02f),
             0.08f, 0.2f, new Color(0.5f, 0.1f, 0.1f), "calm",
             "the lights flicker. something is wrong. you feel it before you see it."),
            // War Drama
            ("War Drama", new Color(0.3f, 0.25f, 0.15f), new Color(0.2f, 0.15f, 0.1f),
             0.05f, 0.5f, new Color(0.6f, 0.4f, 0.2f), "energetic",
             "the year is 1943. you hear distant artillery. the resistance needs you."),
            // Noir Mystery
            ("Noir Mystery", new Color(0.15f, 0.15f, 0.18f), new Color(0.1f, 0.1f, 0.12f),
             0.04f, 0.4f, new Color(0.8f, 0.7f, 0.5f), "focused",
             "rain on the window. a dame walks in. she's got trouble written all over her."),
            // Romantic Comedy
            ("Romantic Comedy", new Color(0.95f, 0.85f, 0.8f), new Color(0.9f, 0.8f, 0.75f),
             0.01f, 1.1f, new Color(1f, 0.9f, 0.85f), "calm",
             "it was a tuesday. nothing special about tuesdays. until it wasn't."),
            // Sci-Fi
            ("Sci-Fi", new Color(0.1f, 0.15f, 0.2f), new Color(0.05f, 0.1f, 0.15f),
             0.02f, 0.6f, new Color(0.3f, 0.6f, 1f), "focused",
             "star date 2387.4. the station's AI has detected an anomaly."),
            // Fantasy
            ("Fantasy", new Color(0.2f, 0.15f, 0.3f), new Color(0.15f, 0.1f, 0.2f),
             0.03f, 0.5f, new Color(0.8f, 0.6f, 1f), "calm",
             "the old magic is returning. you can feel it in the air, taste it like copper."),
            // Western
            ("Western", new Color(0.6f, 0.45f, 0.25f), new Color(0.5f, 0.35f, 0.15f),
             0.06f, 1.2f, new Color(1f, 0.7f, 0.3f), "calm",
             "high noon. the dust settles. someone's riding in."),
            // Spy Thriller
            ("Spy Thriller", new Color(0.1f, 0.12f, 0.1f), new Color(0.08f, 0.1f, 0.08f),
             0.03f, 0.4f, new Color(0.2f, 0.3f, 0.2f), "energetic",
             "your mission, should you choose to accept it... too late. you already have."),
            // Documentary
            ("Documentary", new Color(0.7f, 0.75f, 0.7f), new Color(0.6f, 0.65f, 0.6f),
             0.01f, 1.0f, new Color(0.9f, 0.95f, 0.9f), "calm",
             "here, in this room, two beings share a moment. let us observe."),
            // Surreal Dream
            ("Surreal Dream", new Color(0.3f, 0.1f, 0.4f), new Color(0.2f, 0.05f, 0.3f),
             0.04f, 0.3f, new Color(0.6f, 0.2f, 0.8f), "calm",
             "you're not sure when you fell asleep. the walls are breathing."),
            // Game Show
            ("Game Show", new Color(0.9f, 0.9f, 0.8f), new Color(0.8f, 0.8f, 0.7f),
             0.01f, 1.5f, new Color(1f, 1f, 0.8f), "energetic",
             "ladies and gentlemen! welcome to the show! are you ready to play?"),
            // Heist
            ("Heist", new Color(0.1f, 0.1f, 0.12f), new Color(0.08f, 0.08f, 0.1f),
             0.02f, 0.3f, new Color(0.3f, 0.3f, 0.4f), "focused",
             "the vault opens at midnight. you have exactly 12 minutes. clock's ticking."),
        };

        // ── Phone Call Scripts ──
        // The Director sends these via WebSocket, but we have fallbacks
        private static readonly (string callerName, string voice, string[] lines)[] PhoneCallScripts =
        {
            (
                "Unknown Caller", "mysterious",
                new[] {
                    "...hello? can you hear me?",
                    "i've been trying to reach you.",
                    "you don't know me. but i know you.",
                    "something is coming. you need to be ready.",
                    "...the line is being traced. i have to go.",
                }
            ),
            (
                "Old Friend", "warm",
                new[] {
                    "hey! it's been years!",
                    "i was just thinking about you",
                    "i'm in town. mind if i drop by?",
                    "i'll be there in five minutes",
                    "it's really important. see you soon.",
                }
            ),
            (
                "The Director", "calm",
                new[] {
                    "good evening. this is the Director speaking.",
                    "i've been watching your story unfold.",
                    "it's time for something... different.",
                    "don't be alarmed. this will be fun.",
                    "let's begin.",
                }
            ),
            (
                "Emergency Services", "urgent",
                new[] {
                    "this is an emergency notification",
                    "there's been an incident in your area",
                    "please remain calm and stay where you are",
                    "help is on the way",
                    "...wait. that's not right. forget this call.",
                }
            ),
            (
                "Someone from the Past", "haunting",
                new[] {
                    "...you remember me, don't you?",
                    "i've been waiting for this call for a long time",
                    "or maybe... you've been waiting for mine",
                    "i'm outside. i'm always outside.",
                    "open the door.",
                }
            ),
        };

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            if (presetManager == null) presetManager = FindAnyObjectByType<ScenePresetManager>();
            if (seasonalTheming == null) seasonalTheming = FindAnyObjectByType<SeasonalTheming>();
            if (guestSystem == null) guestSystem = FindAnyObjectByType<VirtualGuestSystem>();
            if (aliceTransform == null)
            {
                var avatar = GameObject.Find("Alice") ?? GameObject.Find("Avatar");
                if (avatar != null)
                {
                    aliceTransform = avatar.transform;
                    aliceHead = avatar.transform.Find("Head");
                }
            }
            _mainLight = FindAnyObjectByType<Light>();
            if (_mainLight != null) _originalLightIntensity = _mainLight.intensity;
            _originalAmbient = RenderSettings.ambientLight;

            // Audio sources
            _phoneAudio = gameObject.AddComponent<AudioSource>();
            _narratorAudio = gameObject.AddComponent<AudioSource>();
            _ambientAudio = gameObject.AddComponent<AudioSource>();
            _phoneAudio.spatialBlend = 0.5f;
            _narratorAudio.spatialBlend = 0f;  // 2D, voice in your head
            _ambientAudio.spatialBlend = 0f;
            _ambientAudio.loop = true;
        }

        private void Start()
        {
            ScheduleNextEvent();
        }

        private void Update()
        {
            if (!directorEnabled) return;

            if (!EventActive)
            {
                _eventTimer += Time.deltaTime;
                if (_eventTimer >= _nextEventTime)
                {
                    _eventTimer = 0f;
                    // Ask the Director (backend) what event to trigger
                    RequestDirectorEvent();
                }
            }
            else
            {
                // Check if event has gone on too long
                if (Time.time - _eventStartTime > maxEventDuration)
                {
                    EndCurrentEvent("the scene fades. normalcy returns.");
                }
            }
        }

        // ── Event Scheduling ──

        private void ScheduleNextEvent()
        {
            _nextEventTime = Random.Range(minEventInterval, maxEventInterval);
            _eventTimer = 0f;
            Debug.Log($"[Director] Next event in {_nextEventTime / 60f:F1} minutes");
        }

        private void RequestDirectorEvent()
        {
            if (wsClient != null)
            {
                var payload = new DirectorRequestPayload
                {
                    type = "director.request",
                    context = GetContextSummary(),
                    timeOfDay = System.DateTime.Now.ToString("HH:mm"),
                    genreActive = _genreActive,
                    allowHorror = allowHorror,
                    allowViolence = allowViolence,
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
                Debug.Log("[Director] Requested event from Director AI");
            }
            else
            {
                // No backend — use local fallback
                TriggerLocalFallbackEvent();
            }
        }

        private string GetContextSummary()
        {
            // Summarize current state for the Director
            return $"genre:{CurrentGenre}, eventActive:{EventActive}, " +
                   $"guests:{(guestSystem != null ? guestSystem.ActiveGuestCount : 0)}, " +
                   $"season:{(seasonalTheming != null ? seasonalTheming.CurrentSeason : "unknown")}";
        }

        [System.Serializable]
        private class DirectorRequestPayload
        {
            public string type;
            public string context;
            public string timeOfDay;
            public bool genreActive;
            public bool allowHorror;
            public bool allowViolence;
        }

        // ── Suspense Builder ──────────────────────────────────────────────────
        //
        // The Director can build suspense PURELY through audio — long before any
        // visual event happens. This is the cinematic technique of foreshadowing:
        // the audience feels something coming before they see it.
        //
        // Phases of suspense building:
        //   1. Calm       — nothing seems wrong, but a low drone starts
        //   2. Whisper    — barely audible sounds, Alice shifts uncomfortably
        //   3. Tension    — distant sounds, music darkens, Alice comments
        //   4. Forewarning — narrator hints, sounds get closer, atmosphere shifts
        //   5. Threshold  — the moment before the event, everything goes quiet
        //   6. Release    — the event triggers
        //
        // Each phase can last 30s to 5min. The Director can abort at any point
        // if the user seems distressed or disengaged.

        private bool _suspenseBuilding;
        private float _suspensePhase;
        private float _suspensePhaseStartTime;
        private AudioSource _droneAudio;
        private AudioSource _stingAudio;
        private Coroutine _suspenseCoroutine;

        // Suspense phases
        private enum SuspensePhase
        {
            Inactive,
            Calm,
            Whisper,
            Tension,
            Forewarning,
            Threshold,
            Release,
        }

        // Audio cues for each phase — synthesized procedurally
        private static readonly (float frequency, float volume, float duration, string description)[] DroneTones =
        {
            (55f, 0.08f, 10f, "sub-bass drone — barely felt, not heard"),
            (73f, 0.06f, 8f, "low rumble — the room hums"),
            (110f, 0.05f, 6f, "deeper hum — something large, distant"),
            (41f, 0.1f, 12f, "subsonic — you feel it in your chest"),
        };

        // Distant sound cues — synthesized
        private static readonly (float freq, float vol, string name)[] DistantSounds =
        {
            (80f, 0.15f, "distant thunder"),
            (200f, 0.08f, "a creak somewhere"),
            (60f, 0.12f, "low rumble, far away"),
            (300f, 0.05f, "something scraping"),
            (150f, 0.1f, "a door, somewhere else"),
            (400f, 0.04f, "footsteps? maybe"),
            (90f, 0.08f, "wind picking up"),
            (50f, 0.15f, "the building settles"),
        };

        // Alice's unease lines — she senses something
        private static readonly string[] AliceUneaseLines =
        {
            "...do you hear that?",
            "something feels... off",
            "i don't know. it's probably nothing",
            "did you feel that?",
            "i keep thinking i heard something",
            "is it just me, or...",
            "...no. never mind. it's fine",
            "the air feels different",
            "i can't shake this feeling",
            "...something's not right",
        };

        // Alice's deeper unease — phase 3+
        private static readonly string[] AliceTensionLines =
        {
            "okay, i definitely heard something that time",
            "i don't like this. something's coming",
            "can we... stay close?",
            "i keep looking at the door",
            "whatever that is, it's getting closer",
            "i'm not usually like this but...",
            "please tell me you hear it too",
            "i want to leave. but i also want to know",
        };

        // Narrator forewarning lines — phase 4
        private static readonly string[] NarratorForewarningLines =
        {
            "something is approaching. you can't see it yet. but it's there.",
            "the silence has weight now. it presses against you.",
            "in a moment, everything will change. but not yet. not yet.",
            "you've been here before. in a dream, maybe. or a memory you buried.",
            "the next few minutes will stay with you. for a long time.",
            "somewhere, a clock is ticking. you can't hear it. but it's counting down.",
            "there's a threshold ahead. you won't know it until you've crossed it.",
        };

        // Threshold — the held breath before the event
        private static readonly string[] ThresholdLines =
        {
            "...now.",
            "it's here.",
            "don't move.",
            "...",
            "this is it.",
        };

        /// <summary>
        /// Begin building suspense through audio only. This can run for minutes
        /// before any visible event happens. The Director calls this to "brew"
        /// an upcoming event — the user feels it coming.
        /// </summary>
        public void BeginSuspenseBuild(float intensity = 0.5f, float totalDuration = 180f)
        {
            if (_suspenseBuilding) return;
            _suspenseCoroutine = StartCoroutine(SuspenseSequence(intensity, totalDuration));
        }

        /// <summary>Abort suspense building immediately (user distressed, etc).</summary>
        public void AbortSuspense()
        {
            if (_suspenseCoroutine != null) StopCoroutine(_suspenseCoroutine);
            _suspenseBuilding = false;
            _suspensePhase = (int)SuspensePhase.Inactive;
            if (_droneAudio != null) { _droneAudio.Stop(); }
            if (_stingAudio != null) { _stingAudio.Stop(); }
            if (_ambientAudio != null) { _ambientAudio.Stop(); }
            AliceSay("...never mind. it's fine. it passed.");
        }

        private IEnumerator SuspenseSequence(float intensity, float totalDuration)
        {
            _suspenseBuilding = true;

            // Create audio sources for suspense
            if (_droneAudio == null) _droneAudio = gameObject.AddComponent<AudioSource>();
            if (_stingAudio == null) _stingAudio = gameObject.AddComponent<AudioSource>();
            _droneAudio.spatialBlend = 0f;  // 2D — everywhere
            _stingAudio.spatialBlend = 0.7f; // semi-positional — sounds come from somewhere
            _droneAudio.loop = true;

            // Phase durations — scaled by total duration and intensity
            float phaseCalm = totalDuration * 0.15f;
            float phaseWhisper = totalDuration * 0.2f;
            float phaseTension = totalDuration * 0.25f;
            float phaseForewarning = totalDuration * 0.2f;
            float phaseThreshold = totalDuration * 0.1f;
            float phaseRelease = totalDuration * 0.1f;

            Debug.Log($"[Director] Suspense building started — {totalDuration}s total, intensity {intensity}");

            // ── Phase 1: Calm ──
            _suspensePhase = (int)SuspensePhase.Calm;
            _suspensePhaseStartTime = Time.time;
            {
                // Start a barely-audible drone
                var drone = DroneTones[0];
                _droneAudio.clip = CreateDrone(drone.frequency, drone.duration);
                _droneAudio.volume = drone.volume * intensity * 0.3f;  // very quiet at first
                _droneAudio.Play();
                Debug.Log($"[Director] Suspense phase: Calm — {drone.description}");
            }
            yield return new WaitForSeconds(phaseCalm);

            // ── Phase 2: Whisper ──
            _suspensePhase = (int)SuspensePhase.Whisper;
            _suspensePhaseStartTime = Time.time;
            {
                // Drone gets slightly louder
                StartCoroutine(FadeVolume(_droneAudio, _droneAudio.volume, 0.08f * intensity, 5f));

                // Occasional barely-audible distant sound
                for (int i = 0; i < 3; i++)
                {
                    yield return new WaitForSeconds(phaseWhisper / 3f * Random.Range(0.7f, 1.3f));
                    var sound = DistantSounds[Random.Range(0, 3)];  // quieter ones
                    _stingAudio.PlayOneShot(CreateDistantSound(sound.freq, 2f), sound.vol * intensity * 0.5f);
                }

                // Alice shifts — first sign of unease
                if (Random.value < 0.7f * intensity)
                    AliceSay(AliceUneaseLines[Random.Range(0, AliceUneaseLines.Length)]);
            }
            Debug.Log("[Director] Suspense phase: Whisper");

            // ── Phase 3: Tension ──
            _suspensePhase = (int)SuspensePhase.Tension;
            _suspensePhaseStartTime = Time.time;
            {
                // Drone shifts lower, more present
                var drone = DroneTones[Random.Range(0, DroneTones.Length)];
                _droneAudio.clip = CreateDrone(drone.frequency, drone.duration);
                StartCoroutine(FadeVolume(_droneAudio, 0.08f * intensity, 0.12f * intensity, 3f));
                _droneAudio.Play();

                // More frequent distant sounds — closer now
                int stings = Mathf.RoundToInt(intensity * 5);
                for (int i = 0; i < stings; i++)
                {
                    yield return new WaitForSeconds(phaseTension / stings * Random.Range(0.5f, 1.5f));
                    var sound = DistantSounds[Random.Range(0, DistantSounds.Length)];
                    _stingAudio.PlayOneShot(CreateDistantSound(sound.freq, 1.5f), sound.vol * intensity);

                    // Alice reacts to some
                    if (i == stings / 2 && Random.value < 0.8f)
                        AliceSay(AliceTensionLines[Random.Range(0, AliceTensionLines.Length)]);
                }

                // Music darkens if available
                if (musicPlayer != null) musicPlayer.SetMood("calm");  // darker calm
            }
            Debug.Log("[Director] Suspense phase: Tension");

            // ── Phase 4: Forewarning ──
            _suspensePhase = (int)SuspensePhase.Forewarning;
            _suspensePhaseStartTime = Time.time;
            {
                // Narrator speaks — the foreshadowing
                NarratorSay(NarratorForewarningLines[Random.Range(0, NarratorForewarningLines.Length)]);
                yield return new WaitForSeconds(5f);

                // Sounds get more distinct, more frequent
                int stings = Mathf.RoundToInt(intensity * 4);
                for (int i = 0; i < stings; i++)
                {
                    yield return new WaitForSeconds(phaseForewarning / stings * Random.Range(0.6f, 1.4f));
                    var sound = DistantSounds[Random.Range(3, DistantSounds.Length)];
                    _stingAudio.PlayOneShot(CreateDistantSound(sound.freq, 1f), sound.vol * intensity * 1.3f);
                }

                // Alice is clearly uneasy
                AliceSay(AliceTensionLines[Random.Range(0, AliceTensionLines.Length)]);

                // Subtle visual shift — barely noticeable dimming
                StartCoroutine(SubtleDim(new Color(0.85f, 0.85f, 0.88f), 10f));
            }
            Debug.Log("[Director] Suspense phase: Forewarning");

            // ── Phase 5: Threshold — the held breath ──
            _suspensePhase = (int)SuspensePhase.Threshold;
            _suspensePhaseStartTime = Time.time;
            {
                // Everything goes QUIET — the drone cuts out
                StartCoroutine(FadeVolume(_droneAudio, _droneAudio.volume, 0f, 1f));
                yield return new WaitForSeconds(1f);
                _droneAudio.Stop();

                // Silence. Pure silence. This is the most tense moment.
                yield return new WaitForSeconds(phaseThreshold * 0.5f);

                // A single whisper from the narrator
                NarratorSay(ThresholdLines[Random.Range(0, ThresholdLines.Length)]);

                // Alice holds her breath
                AliceSay("...");

                yield return new WaitForSeconds(phaseThreshold * 0.5f);
            }
            Debug.Log("[Director] Suspense phase: Threshold — the held breath");

            // ── Phase 6: Release — the event triggers ──
            _suspensePhase = (int)SuspensePhase.Release;
            _suspensePhaseStartTime = Time.time;
            {
                // A sharp sting — the release of tension
                _stingAudio.PlayOneShot(CreateSting(440f, 0.3f), 0.3f * intensity);
                yield return new WaitForSeconds(0.5f);

                // Now trigger the actual event
                _suspenseBuilding = false;
                Debug.Log("[Director] Suspense released — triggering event");

                // The event itself will be triggered by the caller or backend
                // This just built the runway
            }
        }

        /// <summary>Build suspense and then trigger a specific event.</summary>
        public void BuildSuspenseThenTrigger(string eventType, string payload, float suspenseDuration = 120f)
        {
            StartCoroutine(SuspenseThenEvent(eventType, payload, suspenseDuration));
        }

        private IEnumerator SuspenseThenEvent(string eventType, string payload, float duration)
        {
            // Build suspense
            _suspenseCoroutine = StartCoroutine(SuspenseSequence(0.6f, duration));
            yield return _suspenseCoroutine;

            // Now trigger the event
            if (System.Enum.TryParse<DirectorEventType>(eventType, true, out var e))
            {
                _activeEventCoroutine = StartCoroutine(ExecuteEvent(e, payload));
            }
        }

        // ── Audio Synthesis ──

        private AudioClip CreateDrone(float frequency, float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("drone", samples, 1, sampleRate, true, false);

            // We'll generate on the fly via PCM callback
            // For simplicity, pre-generate with slow modulation
            float[] data = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Base frequency with slow LFO modulation
                float lfo = Mathf.Sin(t * 0.3f) * 0.5f + 0.5f;
                // Add harmonics for richness
                float wave = Mathf.Sin(2 * Mathf.PI * frequency * t) * 0.5f;
                wave += Mathf.Sin(2 * Mathf.PI * frequency * 1.5f * t) * 0.2f * lfo;
                wave += Mathf.Sin(2 * Mathf.PI * frequency * 0.5f * t) * 0.3f;
                // Brown noise component
                wave += (Random.value - 0.5f) * 0.05f;
                data[i] = wave * 0.3f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        private AudioClip CreateDistantSound(float frequency, float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("distant", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Envelope — fade in and out, muffled
                float envelope = Mathf.SmoothStep(0f, 0.2f, t / duration) * Mathf.SmoothStep(0f, 0.3f, 1f - t / duration);
                // Low-pass feeling — only low harmonics
                float wave = Mathf.Sin(2 * Mathf.PI * frequency * t) * 0.6f;
                wave += Mathf.Sin(2 * Mathf.PI * frequency * 2f * t) * 0.15f;
                // Rumble
                wave += (Random.value - 0.5f) * 0.1f;
                data[i] = wave * envelope * 0.5f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        private AudioClip CreateSting(float frequency, float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("sting", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Sharp attack, quick decay
                float envelope = Mathf.Exp(-t * 8f);
                float wave = Mathf.Sin(2 * Mathf.PI * frequency * t) * 0.5f;
                wave += Mathf.Sin(2 * Mathf.PI * frequency * 1.5f * t) * 0.3f;
                data[i] = wave * envelope * 0.6f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        // ── Audio Helpers ──

        private IEnumerator FadeVolume(AudioSource source, float from, float to, float duration)
        {
            float t = 0f;
            while (t < duration && source != null)
            {
                t += Time.deltaTime;
                source.volume = Mathf.Lerp(from, to, t / duration);
                yield return null;
            }
            if (source != null) source.volume = to;
        }

        private IEnumerator SubtleDim(Color target, float duration)
        {
            Color start = RenderSettings.ambientLight;
            float t = 0f;
            while (t < duration)
            {
                t += Time.deltaTime;
                RenderSettings.ambientLight = Color.Lerp(start, target, t / duration);
                yield return null;
            }
            // Hold for a while, then restore (the event will handle full atmosphere)
            yield return new WaitForSeconds(10f);
        }

        // ── Shared Surprises ──────────────────────────────────────────────────
        //
        // Things that happen TO you and Alice — pulling focus away from
        // conversation into shared observation. You both stop talking and
        // just... witness something together.
        //
        // The key: these are external events. Not about you, not about Alice.
        // About the world doing something. You become co-audience to life.
        //
        // Surprises can be:
        //   • Natural    — a bird, rain, a meteor, a sunset, wind
        //   • Mundane    — a package arrives, the mail sound, a notification
        //   • Mysterious — a light in the distance, a signal, an anomaly
        //   • Beautiful  — fireflies, aurora, a whale song, cherry petals
        //   • Playful    — a cat wanders in, bubbles appear, a balloon floats by
        //   • Cosmic     — the stars shift, a planet rises, the ISS passes
        //
        // Alice reacts authentically — she's surprised too. She doesn't know
        // what's coming any more than you do. This is the magic: shared wonder.

        public enum SurpriseType
        {
            BirdOnWindowsill,
            MeteorCrossing,
            PackageAtDoor,
            RainBegins,
            Fireflies,
            CatWandersIn,
            WhaleSong,
            CherryPetals,
            StrangeLight,
            BalloonFloatsBy,
            BubblesAppear,
            AuroraFlare,
            DistantMusic,
            ButterflySwarm,
            ISSPassing,
            SunsetBurst,
            ForgottenMusicBox,
            WindChimes,
            MessageInBottle,
            StarShower,
        }

        // Surprise definitions — what Alice says when she notices
        private static readonly (string name, string aliceNotices, string aliceAfter, float duration)[] SurpriseDefs =
        {
            ("BirdOnWindowsill", "oh— look. a bird landed on the sill", "...it's watching us. i think it likes it here", 60f),
            ("MeteorCrossing", "did you see that?! a shooting star!", "...make a wish. quick", 15f),
            ("PackageAtDoor", "is that... a package? at the door?", "we didn't order anything. who sent it?", 45f),
            ("RainBegins", "listen... it's starting to rain", "...i love this sound. let's just listen", 120f),
            ("Fireflies", "oh. oh wow. look at the fireflies", "they're everywhere. like tiny stars came down", 90f),
            ("CatWandersIn", "a cat! where did it come from?", "it's just... making itself at home. i love it", 80f),
            ("WhaleSong", "do you hear that? that's... whales", "...from somewhere far away. they're singing to each other", 60f),
            ("CherryPetals", "the petals... they're falling", "like the tree decided to let go all at once", 45f),
            ("StrangeLight", "what is that? that light, over there", "it's not... it shouldn't be there. what is it?", 30f),
            ("BalloonFloatsBy", "a balloon! someone lost a balloon", "it's just drifting. where do you think it came from?", 25f),
            ("BubblesAppear", "bubbles? where are these coming from?", "they're beautiful. someone must be having a party nearby", 40f),
            ("AuroraFlare", "look up. the sky— it's moving", "...green and purple. i've never seen this from here before", 90f),
            ("DistantMusic", "do you hear that? music, from somewhere", "it's faint but... it's beautiful. who's playing?", 60f),
            ("ButterflySwarm", "butterflies! look at all of them", "they're landing on everything. on you. on me", 50f),
            ("ISSPassing", "that bright light moving— that's the space station", "there are people up there right now. going 17,000 miles an hour", 30f),
            ("SunsetBurst", "the light just— look at the colors", "the whole sky caught fire for a second. did you see it?", 20f),
            ("ForgottenMusicBox", "what's that sound? is that a music box?", "where is it coming from? it's so familiar...", 45f),
            ("WindChimes", "chimes. someone has wind chimes nearby", "i forgot how much i love that sound", 60f),
            ("MessageInBottle", "is that... a bottle? with something in it?", "there's a note inside. should we read it?", 40f),
            ("StarShower", "the stars— they're moving. all of them", "it's like the sky is breathing. or drifting", 30f),
        };

        /// <summary>
        /// Trigger a shared surprise — something external that pulls both
        /// the user and Alice out of conversation into shared observation.
        /// Alice is surprised too — she doesn't know it's coming.
        /// </summary>
        public void TriggerSharedSurprise(string surpriseTypeStr)
        {
            if (EventActive) return;
            if (System.Enum.TryParse<SurpriseType>(surpriseTypeStr, true, out var surpriseType))
            {
                StartCoroutine(ExecuteSharedSurprise(surpriseType));
            }
        }

        /// <summary>Trigger a random shared surprise.</summary>
        public void TriggerRandomSurprise()
        {
            var types = System.Enum.GetValues(typeof(SurpriseType));
            var surprise = (SurpriseType)types.GetValue(Random.Range(0, types.Length));
            StartCoroutine(ExecuteSharedSurprise(surprise));
        }

        private IEnumerator ExecuteSharedSurprise(SurpriseType type)
        {
            EventActive = true;
            CurrentEventType = DirectorEventType.PropSpawn;
            _eventStartTime = Time.time;

            int idx = (int)type;
            var def = SurpriseDefs[idx];

            Debug.Log($"[Director] Shared surprise: {def.name}");

            // ── The moment of noticing ──
            // Alice notices first — she redirects both your attention
            // This is the key: she's genuinely surprised, not performing
            yield return new WaitForSeconds(Random.Range(1f, 3f));  // natural pause
            AliceSay(def.aliceNotices);

            // ── Build the surprise visually ──
            GameObject surpriseObj = null;
            switch (type)
            {
                case SurpriseType.BirdOnWindowsill:
                    surpriseObj = SpawnBirdOnSill();
                    break;
                case SurpriseType.MeteorCrossing:
                    surpriseObj = SpawnMeteor();
                    break;
                case SurpriseType.PackageAtDoor:
                    surpriseObj = SpawnPackage();
                    break;
                case SurpriseType.RainBegins:
                    surpriseObj = SpawnRain();
                    break;
                case SurpriseType.Fireflies:
                    surpriseObj = SpawnFireflies();
                    break;
                case SurpriseType.CatWandersIn:
                    surpriseObj = SpawnCat();
                    break;
                case SurpriseType.WhaleSong:
                    surpriseObj = SpawnWhaleSong();
                    break;
                case SurpriseType.CherryPetals:
                    surpriseObj = SpawnCherryPetals();
                    break;
                case SurpriseType.StrangeLight:
                    surpriseObj = SpawnStrangeLight();
                    break;
                case SurpriseType.BalloonFloatsBy:
                    surpriseObj = SpawnBalloon();
                    break;
                case SurpriseType.BubblesAppear:
                    surpriseObj = SpawnBubbles();
                    break;
                case SurpriseType.AuroraFlare:
                    surpriseObj = SpawnAuroraFlare();
                    break;
                case SurpriseType.DistantMusic:
                    surpriseObj = SpawnDistantMusic();
                    break;
                case SurpriseType.ButterflySwarm:
                    surpriseObj = SpawnButterflies();
                    break;
                case SurpriseType.ISSPassing:
                    surpriseObj = SpawnISSPassing();
                    break;
                case SurpriseType.SunsetBurst:
                    surpriseObj = SpawnSunsetBurst();
                    break;
                case SurpriseType.ForgottenMusicBox:
                    surpriseObj = SpawnMusicBox();
                    break;
                case SurpriseType.WindChimes:
                    surpriseObj = SpawnWindChimes();
                    break;
                case SurpriseType.MessageInBottle:
                    surpriseObj = SpawnMessageBottle();
                    break;
                case SurpriseType.StarShower:
                    surpriseObj = SpawnStarShower();
                    break;
            }

            // ── The shared moment ──
            // You both just... watch. This is the point. Not talking. Watching.
            float watchTime = def.duration * 0.6f;
            yield return new WaitForSeconds(watchTime);

            // ── Alice's afterthought ──
            // After the shared silence, Alice reflects
            AliceSay(def.aliceAfter);

            // ── The surprise fades ──
            yield return new WaitForSeconds(def.duration * 0.4f);

            // Clean up
            if (surpriseObj != null)
            {
                StartCoroutine(FadeOutAndDestroy(surpriseObj, 3f));
            }

            // Alice's closing — gentle return to normal
            if (Random.value < 0.4f)
            {
                yield return new WaitForSeconds(3f);
                AliceSay(Random.value < 0.5f ? "...that was nice" : "...i'll remember that");
            }

            EventActive = false;
            ScheduleNextEvent();
        }

        // ── Surprise Visuals ──

        private GameObject SpawnBirdOnSill()
        {
            Vector3 center = GetRoomCenter();
            Vector3 sillPos = center + new Vector3(1.5f, 0.8f, 0.5f);

            var go = new GameObject("Bird");
            go.transform.position = sillPos;

            // Body
            var body = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = Vector3.one * 0.08f;
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.8f, 0.6f, 0.3f);
            body.GetComponent<Renderer>().material = mat;

            // Head
            var head = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            head.transform.SetParent(go.transform, false);
            head.transform.localPosition = new Vector3(0.06f, 0.06f, 0);
            head.transform.localScale = Vector3.one * 0.04f;
            head.GetComponent<Renderer>().material = mat;

            // Beak
            var beak = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            beak.transform.SetParent(go.transform, false);
            beak.transform.localPosition = new Vector3(0.1f, 0.06f, 0);
            beak.transform.localRotation = Quaternion.Euler(0, 0, -90);
            beak.transform.localScale = Vector3.one * 0.02f;
            var bMat = new Material(Shader.Find("Standard"));
            bMat.color = new Color(1f, 0.6f, 0f);
            beak.GetComponent<Renderer>().material = bMat;

            // Eyes
            var eye = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            eye.transform.SetParent(go.transform, false);
            eye.transform.localPosition = new Vector3(0.07f, 0.08f, 0.02f);
            eye.transform.localScale = Vector3.one * 0.01f;
            var eMat = new Material(Shader.Find("Standard"));
            eMat.color = Color.black;
            eye.GetComponent<Renderer>().material = eMat;

            // Bird looks around
            StartCoroutine(BirdLookAround(go.transform));
            _sceneProps.Add(go);
            return go;
        }

        private IEnumerator BirdLookAround(Transform t)
        {
            while (t != null && EventActive)
            {
                // Occasional head tilt
                if (Random.value < 0.3f)
                {
                    float tilt = Random.Range(-15f, 15f);
                    float elapsed = 0f;
                    Quaternion start = t.rotation;
                    Quaternion target = start * Quaternion.Euler(0, tilt, 0);
                    while (elapsed < 0.5f)
                    {
                        elapsed += Time.deltaTime;
                        if (t != null) t.rotation = Quaternion.Slerp(start, target, elapsed / 0.5f);
                        yield return null;
                    }
                }
                yield return new WaitForSeconds(Random.Range(1f, 3f));
            }
        }

        private GameObject SpawnMeteor()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Meteor");
            go.transform.position = center + new Vector3(-4f, 3f, 2f);

            // Bright streak
            var trail = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trail.transform.SetParent(go.transform, false);
            trail.transform.localScale = new Vector3(0.02f, 2f, 0.02f);
            trail.transform.localRotation = Quaternion.Euler(0, 0, 45);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(1f, 0.9f, 0.6f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(1f, 0.8f, 0.4f) * 5f);
            trail.GetComponent<Renderer>().material = mat;

            // Light
            var light = go.AddComponent<Light>();
            light.color = new Color(1f, 0.9f, 0.6f);
            light.intensity = 3f;
            light.range = 5f;

            // Streak across the sky
            StartCoroutine(MeteorStreak(go.transform, center + new Vector3(4f, -1f, 2f), 2f));
            _sceneProps.Add(go);
            return go;
        }

        private IEnumerator MeteorStreak(Transform t, Vector3 endPos, float duration)
        {
            Vector3 startPos = t.position;
            float elapsed = 0f;
            while (elapsed < duration && t != null)
            {
                elapsed += Time.deltaTime;
                t.position = Vector3.Lerp(startPos, endPos, elapsed / duration);
                yield return null;
            }
        }

        private GameObject SpawnPackage()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Package");
            go.transform.position = center + new Vector3(2f, 0.15f, 1f);

            var box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.transform.SetParent(go.transform, false);
            box.transform.localScale = new Vector3(0.3f, 0.25f, 0.25f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.6f, 0.45f, 0.25f);
            box.GetComponent<Renderer>().material = mat;

            // String
            var stringV = GameObject.CreatePrimitive(PrimitiveType.Cube);
            stringV.transform.SetParent(go.transform, false);
            stringV.transform.localScale = new Vector3(0.02f, 0.26f, 0.02f);
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = new Color(0.8f, 0.7f, 0.5f);
            stringV.GetComponent<Renderer>().material = sMat;

            var stringH = GameObject.CreatePrimitive(PrimitiveType.Cube);
            stringH.transform.SetParent(go.transform, false);
            stringH.transform.localScale = new Vector3(0.31f, 0.02f, 0.02f);
            stringH.GetComponent<Renderer>().material = sMat;

            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnRain()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Rain");
            go.transform.position = center + Vector3.up * 3f;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = new Color(0.5f, 0.6f, 0.8f, 0.4f);
            main.startSize = 0.02f;
            main.startSpeed = 4f;
            main.maxParticles = 500;
            main.loop = true;
            main.startLifetime = 2f;
            var emission = ps.emission;
            emission.rateOverTime = 200;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Box;
            shape.scale = new Vector3(6f, 1f, 6f);
            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnFireflies()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Fireflies");
            go.transform.position = center;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = new Color(0.9f, 1f, 0.4f, 0.8f);
            main.startSize = 0.05f;
            main.startSpeed = 0.2f;
            main.maxParticles = 60;
            main.loop = true;
            main.startLifetime = 5f;
            var emission = ps.emission;
            emission.rateOverTime = 15;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = 3f;
            // Glow
            var rend = go.GetComponent<ParticleSystemRenderer>();
            if (rend != null)
            {
                var mat = new Material(Shader.Find("Standard"));
                mat.color = new Color(0.9f, 1f, 0.4f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", new Color(0.9f, 1f, 0.4f) * 3f);
                rend.material = mat;
            }
            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnCat()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Cat");
            go.transform.position = center + new Vector3(2f, 0.15f, 1f);

            // Body
            var body = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.12f, 0.2f, 0.12f);
            body.transform.localRotation = Quaternion.Euler(90, 0, 0);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.3f, 0.25f, 0.2f);
            body.GetComponent<Renderer>().material = mat;

            // Head
            var head = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            head.transform.SetParent(go.transform, false);
            head.transform.localPosition = new Vector3(0, 0.15f, 0.1f);
            head.transform.localScale = Vector3.one * 0.08f;
            head.GetComponent<Renderer>().material = mat;

            // Ears
            for (int i = 0; i < 2; i++)
            {
                var ear = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                ear.transform.SetParent(go.transform, false);
                ear.transform.localPosition = new Vector3(i == 0 ? -0.04f : 0.04f, 0.22f, 0.1f);
                ear.transform.localScale = Vector3.one * 0.03f;
                ear.GetComponent<Renderer>().material = mat;
            }

            // Tail
            var tail = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            tail.transform.SetParent(go.transform, false);
            tail.transform.localPosition = new Vector3(0, 0.1f, -0.15f);
            tail.transform.localRotation = Quaternion.Euler(45, 0, 0);
            tail.transform.localScale = new Vector3(0.02f, 0.15f, 0.02f);
            tail.GetComponent<Renderer>().material = mat;

            // Eyes — glowing
            for (int i = 0; i < 2; i++)
            {
                var eye = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                eye.transform.SetParent(go.transform, false);
                eye.transform.localPosition = new Vector3(i == 0 ? -0.025f : 0.025f, 0.16f, 0.14f);
                eye.transform.localScale = Vector3.one * 0.015f;
                var eMat = new Material(Shader.Find("Standard"));
                eMat.color = new Color(0.8f, 0.6f, 0.1f);
                eMat.EnableKeyword("_EMISSION");
                eMat.SetColor("_EmissionColor", new Color(0.8f, 0.6f, 0.1f) * 3f);
                eye.GetComponent<Renderer>().material = eMat;
            }

            // Cat wanders and settles
            StartCoroutine(CatWander(go.transform));
            _sceneProps.Add(go);
            return go;
        }

        private IEnumerator CatWander(Transform t)
        {
            Vector3 center = GetRoomCenter();
            Vector3[] waypoints = {
                center + new Vector3(1f, 0.15f, 0.5f),
                center + new Vector3(-0.5f, 0.15f, 1f),
                center + new Vector3(0.5f, 0.15f, -0.5f),
            };

            foreach (var wp in waypoints)
            {
                if (t == null) yield break;
                Vector3 start = t.position;
                float elapsed = 0f;
                float dur = Vector3.Distance(start, wp) * 2f;
                while (elapsed < dur)
                {
                    elapsed += Time.deltaTime;
                    if (t != null)
                    {
                        t.position = Vector3.Lerp(start, wp, elapsed / dur);
                        Vector3 dir = (wp - start).normalized;
                        if (dir != Vector3.zero)
                            t.rotation = Quaternion.Slerp(t.rotation, Quaternion.LookRotation(dir), Time.deltaTime * 3f);
                    }
                    yield return null;
                }
                yield return new WaitForSeconds(2f);  // pause, look around
            }
        }

        private GameObject SpawnWhaleSong()
        {
            // Audio-only — no visual, just the sound
            var go = new GameObject("WhaleSong");
            var audio = go.AddComponent<AudioSource>();
            audio.spatialBlend = 0.7f;
            audio.clip = CreateWhaleSong(8f);
            audio.volume = 0.3f;
            audio.loop = true;
            audio.Play();
            _sceneProps.Add(go);
            return go;
        }

        private AudioClip CreateWhaleSong(float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("whale", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Whale song — slow frequency sweep with harmonics
                float freq = 200f + Mathf.Sin(t * 0.5f) * 150f;
                float envelope = Mathf.SmoothStep(0f, 0.1f, t / duration) * Mathf.SmoothStep(0f, 0.3f, 1f - t / duration);
                float wave = Mathf.Sin(2 * Mathf.PI * freq * t) * 0.5f;
                wave += Mathf.Sin(2 * Mathf.PI * freq * 1.5f * t) * 0.2f;
                wave += Mathf.Sin(2 * Mathf.PI * freq * 0.5f * t) * 0.3f;
                data[i] = wave * envelope * 0.4f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        private GameObject SpawnCherryPetals()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("CherryPetals");
            go.transform.position = center + Vector3.up * 3f;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = new Color(1f, 0.7f, 0.85f, 0.7f);
            main.startSize = 0.04f;
            main.startSpeed = 0.3f;
            main.maxParticles = 100;
            main.loop = true;
            main.startLifetime = 6f;
            var emission = ps.emission;
            emission.rateOverTime = 20;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = 2f;
            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnStrangeLight()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("StrangeLight");
            go.transform.position = center + new Vector3(-3f, 1.5f, 2f);

            var orb = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            orb.transform.SetParent(go.transform, false);
            orb.transform.localScale = Vector3.one * 0.15f;
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.6f, 0.8f, 1f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.6f, 0.8f, 1f) * 4f);
            orb.GetComponent<Renderer>().material = mat;

            var light = go.AddComponent<Light>();
            light.color = new Color(0.6f, 0.8f, 1f);
            light.intensity = 2f;
            light.range = 4f;

            // Pulsing
            StartCoroutine(PulseLight(light, 0.5f, 3f, 2f));
            // Slow drift
            StartCoroutine(DriftObject(go.transform, 0.1f));
            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnBalloon()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Balloon");
            go.transform.position = center + new Vector3(-3f, 0.5f, 1f);

            var body = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.2f, 0.25f, 0.2f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = Color.HSVToRGB(Random.value, 0.7f, 0.9f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", mat.color * 0.5f);
            body.GetComponent<Renderer>().material = mat;

            // String
            var stringObj = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            stringObj.transform.SetParent(go.transform, false);
            stringObj.transform.localPosition = new Vector3(0, -0.3f, 0);
            stringObj.transform.localScale = new Vector3(0.005f, 0.3f, 0.005f);
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = Color.white;
            stringObj.GetComponent<Renderer>().material = sMat;

            // Float up and away
            StartCoroutine(BalloonFloat(go.transform, 20f));
            _sceneProps.Add(go);
            return go;
        }

        private IEnumerator BalloonFloat(Transform t, float duration)
        {
            Vector3 start = t.position;
            float elapsed = 0f;
            while (elapsed < duration && t != null)
            {
                elapsed += Time.deltaTime;
                t.position = start + new Vector3(
                    Mathf.Sin(elapsed * 0.5f) * 0.5f,
                    elapsed * 0.1f,
                    0);
                yield return null;
            }
        }

        private GameObject SpawnBubbles()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Bubbles");
            go.transform.position = center + new Vector3(0, 0.5f, 1f);
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = new Color(0.8f, 0.9f, 1f, 0.3f);
            main.startSize = Random.Range(0.05f, 0.15f);
            main.startSpeed = 0.5f;
            main.maxParticles = 50;
            main.loop = true;
            main.startLifetime = 5f;
            var emission = ps.emission;
            emission.rateOverTime = 10;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = 0.5f;
            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnAuroraFlare()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Aurora");
            go.transform.position = center + Vector3.up * 4f;

            for (int i = 0; i < 3; i++)
            {
                var ribbon = GameObject.CreatePrimitive(PrimitiveType.Plane);
                ribbon.transform.SetParent(go.transform, false);
                ribbon.transform.localPosition = new Vector3(Random.Range(-2f, 2f), 0, 0);
                ribbon.transform.localRotation = Quaternion.Euler(90, Random.Range(0, 360), 0);
                ribbon.transform.localScale = new Vector3(3f, 1f, 0.2f);
                var mat = new Material(Shader.Find("Standard"));
                Color c = i == 0 ? new Color(0.1f, 0.9f, 0.3f) : i == 1 ? new Color(0.3f, 0.5f, 0.9f) : new Color(0.6f, 0.1f, 0.8f);
                mat.color = c * 0.5f;
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", c * 3f);
                ribbon.GetComponent<Renderer>().material = mat;
                StartCoroutine(AuroraWave(ribbon.transform));
            }
            _sceneProps.Add(go);
            return go;
        }

        private IEnumerator AuroraWave(Transform t)
        {
            Vector3 basePos = t.localPosition;
            while (t != null && EventActive)
            {
                t.localPosition = basePos + new Vector3(
                    Mathf.Sin(Time.time * 0.3f) * 1f,
                    Mathf.Sin(Time.time * 0.2f) * 0.3f, 0);
                yield return null;
            }
        }

        private GameObject SpawnDistantMusic()
        {
            // Audio-only — faint music from somewhere
            var go = new GameObject("DistantMusic");
            var audio = go.AddComponent<AudioSource>();
            audio.spatialBlend = 0.8f;
            audio.clip = CreateDistantMusic(10f);
            audio.volume = 0.15f;
            audio.loop = true;
            audio.Play();
            _sceneProps.Add(go);
            return go;
        }

        private AudioClip CreateDistantMusic(float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("music", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            // Simple melody — pentatonic scale
            float[] notes = { 261f, 293f, 329f, 392f, 440f };
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                int noteIdx = (int)(t * 1.5f) % notes.Length;
                float freq = notes[noteIdx];
                float envelope = Mathf.Exp(-((t % 0.7f) * 3f));  // note decay
                float wave = Mathf.Sin(2 * Mathf.PI * freq * t) * 0.3f;
                wave += Mathf.Sin(2 * Mathf.PI * freq * 2f * t) * 0.1f;
                // Muffled — low pass feel
                wave *= 0.6f;
                data[i] = wave * envelope * 0.3f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        private GameObject SpawnButterflies()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("Butterflies");
            go.transform.position = center;

            for (int i = 0; i < 8; i++)
            {
                var butterfly = new GameObject($"Butterfly_{i}");
                butterfly.transform.SetParent(go.transform, false);
                butterfly.transform.localPosition = new Vector3(
                    Random.Range(-2f, 2f), Random.Range(0.5f, 2f), Random.Range(-2f, 2f));

                var wing = GameObject.CreatePrimitive(PrimitiveType.Quad);
                wing.transform.SetParent(butterfly.transform, false);
                wing.transform.localScale = Vector3.one * 0.06f;
                var mat = new Material(Shader.Find("Standard"));
                mat.color = Color.HSVToRGB(Random.value, 0.7f, 0.9f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", mat.color * 0.5f);
                wing.GetComponent<Renderer>().material = mat;

                StartCoroutine(ButterflyFlutter(butterfly.transform));
            }
            _sceneProps.Add(go);
            return go;
        }

        private IEnumerator ButterflyFlutter(Transform t)
        {
            Vector3 basePos = t.localPosition;
            float phase = Random.Range(0f, Mathf.PI * 2f);
            while (t != null && EventActive)
            {
                t.localPosition = basePos + new Vector3(
                    Mathf.Sin(Time.time * 0.8f + phase) * 0.5f,
                    Mathf.Sin(Time.time * 1.2f + phase) * 0.3f,
                    Mathf.Cos(Time.time * 0.6f + phase) * 0.5f);
                t.Rotate(Vector3.up, 120f * Time.deltaTime);
                yield return null;
            }
        }

        private GameObject SpawnISSPassing()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("ISS");
            go.transform.position = center + new Vector3(-5f, 4f, 0);

            var body = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = Vector3.one * 0.05f;
            var mat = new Material(Shader.Find("Standard"));
            mat.color = Color.white;
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", Color.white * 5f);
            body.GetComponent<Renderer>().material = mat;

            var light = go.AddComponent<Light>();
            light.color = Color.white;
            light.intensity = 2f;
            light.range = 3f;

            // Slowly cross the sky
            StartCoroutine(MeteorStreak(go.transform, center + new Vector3(5f, 4f, 0), 15f));
            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnSunsetBurst()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("SunsetBurst");
            go.transform.position = center + new Vector3(0, 1f, 5f);

            var light = go.AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = new Color(1f, 0.4f, 0.2f);
            light.intensity = 0f;
            light.range = 20f;

            // Burst of color
            StartCoroutine(SunsetBurst(light, 8f));
            _sceneProps.Add(go);
            return go;
        }

        private IEnumerator SunsetBurst(Light light, float duration)
        {
            float elapsed = 0f;
            while (elapsed < duration && light != null)
            {
                elapsed += Time.deltaTime;
                float p = elapsed / duration;
                // Quick rise, slow fade
                float intensity = p < 0.2f ? p / 0.2f * 3f : (1f - (p - 0.2f) / 0.8f) * 3f;
                light.intensity = Mathf.Max(0, intensity);
                // Color shift
                light.color = Color.Lerp(new Color(1f, 0.4f, 0.2f), new Color(0.6f, 0.2f, 0.4f), p);
                yield return null;
            }
        }

        private GameObject SpawnMusicBox()
        {
            var go = new GameObject("MusicBox");
            var audio = go.AddComponent<AudioSource>();
            audio.spatialBlend = 0.6f;
            audio.clip = CreateMusicBox(8f);
            audio.volume = 0.2f;
            audio.loop = true;
            audio.Play();
            _sceneProps.Add(go);
            return go;
        }

        private AudioClip CreateMusicBox(float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("musicbox", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            // Music box — plucky, nostalgic melody
            float[] melody = { 523f, 587f, 659f, 587f, 523f, 440f, 392f, 440f };
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                int noteIdx = (int)(t * 2f) % melody.Length;
                float freq = melody[noteIdx];
                float envelope = Mathf.Exp(-((t % 0.5f) * 8f));
                float wave = Mathf.Sin(2 * Mathf.PI * freq * t) * 0.4f;
                wave += Mathf.Sin(2 * Mathf.PI * freq * 3f * t) * 0.05f;  // slight overtone
                data[i] = wave * envelope * 0.3f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        private GameObject SpawnWindChimes()
        {
            var go = new GameObject("WindChimes");
            var audio = go.AddComponent<AudioSource>();
            audio.spatialBlend = 0.7f;
            audio.clip = CreateWindChimes(12f);
            audio.volume = 0.15f;
            audio.loop = true;
            audio.Play();
            _sceneProps.Add(go);
            return go;
        }

        private AudioClip CreateWindChimes(float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("chimes", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            float[] chimeFreqs = { 523f, 659f, 784f, 880f, 988f, 1175f };
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Random chimes at intervals
                float wave = 0f;
                for (int c = 0; c < chimeFreqs.Length; c++)
                {
                    float chimeTime = (c * 1.7f) % duration;
                    float age = t - chimeTime;
                    if (age > 0 && age < 3f)
                    {
                        float env = Mathf.Exp(-age * 1.5f);
                        wave += Mathf.Sin(2 * Mathf.PI * chimeFreqs[c] * t) * env * 0.15f;
                    }
                }
                data[i] = wave * 0.5f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        private GameObject SpawnMessageBottle()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("MessageBottle");
            go.transform.position = center + new Vector3(1f, 0.1f, 1f);

            var body = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.06f, 0.15f, 0.06f);
            body.transform.localRotation = Quaternion.Euler(0, 0, 90);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.5f, 0.7f, 0.6f, 0.7f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.3f, 0.5f, 0.4f) * 0.5f);
            body.GetComponent<Renderer>().material = mat;

            // Note inside (visible glow)
            var note = GameObject.CreatePrimitive(PrimitiveType.Cube);
            note.transform.SetParent(go.transform, false);
            note.transform.localPosition = new Vector3(0, 0, 0);
            note.transform.localScale = new Vector3(0.08f, 0.02f, 0.03f);
            var nMat = new Material(Shader.Find("Standard"));
            nMat.color = new Color(0.9f, 0.85f, 0.6f);
            note.GetComponent<Renderer>().material = nMat;

            _sceneProps.Add(go);
            return go;
        }

        private GameObject SpawnStarShower()
        {
            Vector3 center = GetRoomCenter();
            var go = new GameObject("StarShower");
            go.transform.position = center + Vector3.up * 5f;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = Color.white;
            main.startSize = 0.03f;
            main.startSpeed = 0.5f;
            main.maxParticles = 200;
            main.loop = true;
            main.startLifetime = 8f;
            var emission = ps.emission;
            emission.rateOverTime = 30;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Hemisphere;
            shape.radius = 5f;
            var rend = go.GetComponent<ParticleSystemRenderer>();
            if (rend != null)
            {
                var mat = new Material(Shader.Find("Standard"));
                mat.color = Color.white;
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", Color.white * 2f);
                rend.material = mat;
            }
            _sceneProps.Add(go);
            return go;
        }

        // ── Surprise Helpers ──

        private IEnumerator PulseLight(Light light, float min, float max, float speed)
        {
            while (light != null && EventActive)
            {
                float t = (Mathf.Sin(Time.time * speed) + 1f) * 0.5f;
                light.intensity = Mathf.Lerp(min, max, t);
                yield return null;
            }
        }

        private IEnumerator DriftObject(Transform t, float speed)
        {
            Vector3 basePos = t.position;
            while (t != null && EventActive)
            {
                t.position = basePos + new Vector3(
                    Mathf.Sin(Time.time * speed) * 0.3f,
                    Mathf.Sin(Time.time * speed * 0.7f) * 0.2f,
                    Mathf.Cos(Time.time * speed * 0.5f) * 0.3f);
                yield return null;
            }
        }

        private IEnumerator FadeOutAndDestroy(GameObject go, float duration)
        {
            if (go == null) yield break;
            // Try to fade renderers
            var renderers = go.GetComponentsInChildren<Renderer>();
            var materials = new List<Material>();
            var startColors = new List<Color>();
            foreach (var r in renderers)
            {
                if (r.material != null)
                {
                    materials.Add(r.material);
                    startColors.Add(r.material.color);
                }
            }

            float t = 0f;
            while (t < duration && go != null)
            {
                t += Time.deltaTime;
                float alpha = 1f - t / duration;
                for (int i = 0; i < materials.Count; i++)
                {
                    if (materials[i] != null)
                    {
                        Color c = startColors[i];
                        c.a *= alpha;
                        materials[i].color = c;
                    }
                }
                yield return null;
            }
            if (go != null) Destroy(go);
        }

        // ── Scripted Sequences ─────────────────────────────────────────────────
        //
        // Pre-authored cinematic sequences — the Director's set pieces.
        // These are fully choreographed: atmosphere → music → action → twist.
        // Each one is a mini-film that unfolds over several minutes.

        /// <summary>
        /// "Riders on the Storm" — a thunderstorm builds, rain pours, music
        /// starts, then someone knocks at the door slowly. And then...
        /// something unexpected.
        ///
        /// The sequence:
        ///   1. Distant thunder rumbles (30s)
        ///   2. Lightning flashes through the window (20s)
        ///   3. Rain begins pouring (builds over 15s)
        ///   4. A song starts playing — distant, muffled, getting closer (10s)
        ///   5. The knock — slow, deliberate, three knocks (10s)
        ///   6. Silence. Alice is uneasy. (5s)
        ///   7. The door opens... and what walks in is NOT what you expect.
        ///      The Director picks from several twists:
        ///        • A soaking wet cat that shakes itself off and walks to Alice
        ///        • A small child holding a paper boat, saying nothing
        ///        • An old radio playing the song, no one carrying it
        ///        • Alice herself — a second Alice walks in, identical
        ///        • A single rose on the doorstep, no one there
        ///        • A letter that says "I found you" — no signature
        ///        • A mirror — you see yourself standing in the doorway
        ///        • Nothing. The door opened on its own. The rain stops.
        ///          The song fades. As if it never happened.
        /// </summary>
        public void TriggerRidersOnTheStorm()
        {
            if (EventActive) return;
            StartCoroutine(RidersOnTheStormSequence());
        }

        private IEnumerator RidersOnTheStormSequence()
        {
            EventActive = true;
            CurrentEventType = DirectorEventType.EventSequence;
            CurrentGenre = Genre.NoirMystery;
            _eventStartTime = Time.time;

            Vector3 center = GetRoomCenter();
            Debug.Log("[Director] === RIDERS ON THE STORM ===");

            // ── Phase 1: Distant Thunder (30s) ──
            NarratorSay("the first rumble comes from far away. barely a sound. more of a feeling.");
            yield return new WaitForSeconds(3f);

            // Three distant rumbles, getting closer
            for (int i = 0; i < 3; i++)
            {
                float vol = 0.05f + i * 0.05f;
                float freq = 60f - i * 10f;
                _stingAudio.PlayOneShot(CreateThunder(freq, 4f), vol);
                // Alice shifts at the second one
                if (i == 1)
                    AliceSay("...was that thunder?");
                yield return new WaitForSeconds(8f + Random.Range(-2f, 3f));
            }

            // ── Phase 2: Lightning Flashes (20s) ──
            NarratorSay("then the light comes. sharp. white. the room freezes for a moment.");
            yield return new WaitForSeconds(2f);

            // Create lightning flash light
            var lightningGo = new GameObject("Lightning");
            lightningGo.transform.position = center + new Vector3(0, 3f, 3f);
            var lightning = lightningGo.AddComponent<Light>();
            lightning.type = LightType.Directional;
            lightning.color = new Color(0.8f, 0.85f, 1f);
            lightning.intensity = 0f;
            _sceneLights.Add(lightning);

            // Several flashes, each followed by thunder
            for (int i = 0; i < 4; i++)
            {
                // Flash
                yield return StartCoroutine(LightningFlash(lightning, 0.15f));
                yield return new WaitForSeconds(0.3f);
                // Sometimes a second quick flash
                if (Random.value < 0.5f)
                {
                    yield return StartCoroutine(LightningFlash(lightning, 0.08f));
                    yield return new WaitForSeconds(0.2f);
                }
                // Thunder follows (delay = distance)
                float thunderDelay = Random.Range(1.5f, 4f);
                yield return new WaitForSeconds(thunderDelay);
                _stingAudio.PlayOneShot(CreateThunder(50f + Random.Range(-15f, 15f), 5f), 0.2f - thunderDelay * 0.03f);

                if (i == 1)
                    AliceSay("that was close. the storm's right overhead.");
                if (i == 3)
                    AliceSay("i think it's... raining.");
            }

            // ── Phase 3: Rain Pours (15s build) ──
            NarratorSay("and then the rain. not gentle. not asking. it just... arrives.");
            yield return new WaitForSeconds(2f);

            // Heavy rain particles
            var rainGo = new GameObject("StormRain");
            rainGo.transform.position = center + Vector3.up * 4f;
            var rainPs = rainGo.AddComponent<ParticleSystem>();
            var rainMain = rainPs.main;
            rainMain.startColor = new Color(0.4f, 0.5f, 0.7f, 0.5f);
            rainMain.startSize = 0.03f;
            rainMain.startSpeed = 8f;
            rainMain.maxParticles = 800;
            rainMain.loop = true;
            rainMain.startLifetime = 1.5f;
            var rainEmission = rainPs.emission;
            rainEmission.rateOverTime = 0;  // start at 0, build up
            var rainShape = rainPs.shape;
            rainShape.shapeType = ParticleSystemShapeType.Box;
            rainShape.scale = new Vector3(8f, 1f, 8f);
            _sceneProps.Add(rainGo);

            // Rain audio — continuous hiss
            var rainAudioGo = new GameObject("RainAudio");
            var rainAudio = rainAudioGo.AddComponent<AudioSource>();
            rainAudio.spatialBlend = 0f;
            rainAudio.clip = CreateRainSound(10f);
            rainAudio.volume = 0f;
            rainAudio.loop = true;
            rainAudio.Play();
            _sceneProps.Add(rainAudioGo);

            // Build up rain intensity and volume
            float rainBuildT = 0f;
            while (rainBuildT < 15f)
            {
                rainBuildT += Time.deltaTime;
                float p = rainBuildT / 15f;
                rainEmission.rateOverTime = 400 * p;
                rainAudio.volume = 0.3f * p;
                yield return null;
            }

            AliceSay("listen to it. it's really coming down.");

            // ── Phase 4: The Song (10s) ──
            // A song starts — distant, muffled, getting closer
            NarratorSay("and then... music. from somewhere. from the rain itself, maybe.");
            yield return new WaitForSeconds(2f);

            var musicGo = new GameObject("StormSong");
            var musicAudio = musicGo.AddComponent<AudioSource>();
            musicAudio.spatialBlend = 0.6f;
            musicAudio.clip = CreateRidersOnTheStorm(20f);
            musicAudio.volume = 0f;
            musicAudio.loop = true;
            musicAudio.Play();
            _sceneProps.Add(musicGo);

            // Fade in the music
            yield return StartCoroutine(FadeVolume(musicAudio, 0f, 0.25f, 8f));

            yield return new WaitForSeconds(2f);
            AliceSay("is that... music? where is it coming from?");
            yield return new WaitForSeconds(3f);

            // ── Phase 5: The Knock (10s) ──
            // Three slow, deliberate knocks
            NarratorSay("and then. a knock. slow. like the visitor has all the time in the world.");
            yield return new WaitForSeconds(2f);

            // First knock
            _stingAudio.PlayOneShot(CreateKnock(80f, 0.15f), 0.4f);
            // Brief lightning flash on first knock
            yield return StartCoroutine(LightningFlash(lightning, 0.1f));
            yield return new WaitForSeconds(3f);

            // Second knock
            _stingAudio.PlayOneShot(CreateKnock(75f, 0.15f), 0.45f);
            yield return new WaitForSeconds(3f);

            // Third knock — louder
            _stingAudio.PlayOneShot(CreateKnock(70f, 0.2f), 0.5f);
            yield return new WaitForSeconds(1f);

            // ── Phase 6: Silence (5s) ──
            // Everything holds. The rain continues but the music stops.
            yield return StartCoroutine(FadeVolume(musicAudio, 0.25f, 0f, 2f));
            yield return new WaitForSeconds(1f);

            AliceSay("...should we open it?");
            yield return new WaitForSeconds(3f);

            NarratorSay("the door opens on its own.");
            yield return new WaitForSeconds(2f);

            // ── Phase 7: The Twist ──
            // The Director picks something unexpected
            int twist = Random.Range(0, 8);
            Debug.Log($"[Director] Riders on the Storm — twist #{twist}");

            switch (twist)
            {
                case 0:  // A soaking wet cat
                    yield return StartCoroutine(Twist_WetCat(center));
                    break;
                case 1:  // A child with a paper boat
                    yield return StartCoroutine(Twist_ChildWithBoat(center));
                    break;
                case 2:  // An old radio, no one carrying it
                    yield return StartCoroutine(Twist_OldRadio(center, musicAudio));
                    break;
                case 3:  // A second Alice
                    yield return StartCoroutine(Twist_SecondAlice(center));
                    break;
                case 4:  // A single rose, no one there
                    yield return StartCoroutine(Twist_SingleRose(center));
                    break;
                case 5:  // A letter: "I found you"
                    yield return StartCoroutine(Twist_Letter(center));
                    break;
                case 6:  // A mirror — you see yourself
                    yield return StartCoroutine(Twist_Mirror(center));
                    break;
                case 7:  // Nothing. It all just... stops.
                    yield return StartCoroutine(Twist_Nothing(rainAudio, rainPs, lightning));
                    break;
            }

            // ── Denouement ──
            yield return new WaitForSeconds(5f);

            // Fade out rain
            StartCoroutine(FadeVolume(rainAudio, rainAudio.volume, 0f, 10f));
            var rainEmissionRef = rainPs.emission;
            float fadeT = 0f;
            while (fadeT < 10f)
            {
                fadeT += Time.deltaTime;
                rainEmissionRef.rateOverTime = 400 * (1f - fadeT / 10f);
                yield return null;
            }

            NarratorSay("the storm passes. as if it was never here. but something... remains.");
            yield return new WaitForSeconds(3f);

            // Restore atmosphere
            RestoreAtmosphere();
            EventActive = false;
            CurrentGenre = Genre.None;
            ScheduleNextEvent();
            Debug.Log("[Director] === RIDERS ON THE STORM — END ===");
        }

        // ── Lightning Flash ──

        private IEnumerator LightningFlash(Light light, float duration)
        {
            if (light == null) yield break;
            // Quick on, slight flicker, off
            light.intensity = 5f;
            yield return new WaitForSeconds(0.03f);
            light.intensity = 2f;
            yield return new WaitForSeconds(0.02f);
            light.intensity = 4f;
            yield return new WaitForSeconds(duration * 0.4f);
            // Fade out
            float t = 0f;
            while (t < duration * 0.6f)
            {
                t += Time.deltaTime;
                light.intensity = Mathf.Lerp(4f, 0f, t / (duration * 0.6f));
                yield return null;
            }
            light.intensity = 0f;
        }

        // ── Thunder Synthesis ──

        private AudioClip CreateThunder(float baseFreq, float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("thunder", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Rumble — low frequency with noise
                float envelope = Mathf.Exp(-t * 1.5f) * Mathf.SmoothStep(0f, 0.1f, t / duration);
                float rumble = Mathf.Sin(2 * Mathf.PI * baseFreq * t) * 0.4f;
                rumble += Mathf.Sin(2 * Mathf.PI * baseFreq * 0.5f * t) * 0.3f;
                // Heavy noise component
                float noise = (Random.value - 0.5f) * 0.5f;
                // Low-pass the noise (simple averaging)
                if (i > 0) noise = (noise + data[i - 1]) * 0.5f;
                data[i] = (rumble + noise) * envelope * 0.6f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        // ── Rain Sound Synthesis ──

        private AudioClip CreateRainSound(float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("rain", samples, 1, sampleRate, true, false);
            float[] data = new float[samples];
            // Pink noise — rain hiss
            float b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
            for (int i = 0; i < samples; i++)
            {
                float white = Random.value - 0.5f;
                b0 = 0.99886f * b0 + white * 0.0555179f;
                b1 = 0.99332f * b1 + white * 0.0750759f;
                b2 = 0.96900f * b2 + white * 0.1538520f;
                b3 = 0.86650f * b3 + white * 0.3104856f;
                b4 = 0.55000f * b4 + white * 0.5329522f;
                b5 = -0.7616f * b5 - white * 0.0168980f;
                float pink = b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362f;
                b6 = white * 0.115926f;
                data[i] = pink * 0.15f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        // ── Knock Sound ──

        private AudioClip CreateKnock(float frequency, float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("knock", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Wooden knock — short, resonant
                float envelope = Mathf.Exp(-t * 30f);
                float wave = Mathf.Sin(2 * Mathf.PI * frequency * t) * 0.5f;
                wave += Mathf.Sin(2 * Mathf.PI * frequency * 2f * t) * 0.2f;
                wave += (Random.value - 0.5f) * 0.1f * envelope;
                data[i] = wave * envelope * 0.7f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        // ── "Riders on the Storm" — evocative music synthesis ──
        // We can't play the actual song, but we synthesize a moody,
        // rainy, electric-piano-like atmosphere that evokes the feeling.

        private AudioClip CreateRidersOnTheStorm(float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("riders", samples, 1, sampleRate, false);
            float[] data = new float[samples];

            // A moody minor-key progression (Am - F - C - G)
            float[][] chords = {
                new[] { 220f, 261.6f, 329.6f },  // Am
                new[] { 174.6f, 220f, 261.6f },  // F
                new[] { 261.6f, 329.6f, 392f },  // C
                new[] { 196f, 246.9f, 293.6f },  // G
            };
            float chordDuration = duration / chords.Length;

            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                int chordIdx = (int)(t / chordDuration) % chords.Length;
                var chord = chords[chordIdx];

                // Electric piano — soft sine with slight detune and tremolo
                float wave = 0f;
                for (int n = 0; n < chord.Length; n++)
                {
                    float freq = chord[n];
                    float detune = 1f + (n * 0.001f);
                    float tremolo = 0.7f + 0.3f * Mathf.Sin(t * 4f);
                    wave += Mathf.Sin(2 * Mathf.PI * freq * detune * t) * 0.15f * tremolo;
                    // Add a soft octave
                    wave += Mathf.Sin(2 * Mathf.PI * freq * 2f * t) * 0.03f;
                }

                // Chord envelope — gentle attack, slow release
                float chordT = (t % chordDuration) / chordDuration;
                float chordEnv = Mathf.SmoothStep(0f, 0.1f, chordT) * Mathf.SmoothStep(0f, 0.3f, 1f - chordT);

                // Add a simple bass line
                float bassFreq = chord[0] * 0.5f;
                float bassEnv = Mathf.Exp(-((chordT) * 3f));
                wave += Mathf.Sin(2 * Mathf.PI * bassFreq * t) * 0.2f * bassEnv;

                // Rain hiss underneath (the song IS the rain)
                float rainHiss = (Random.value - 0.5f) * 0.02f;

                data[i] = (wave * chordEnv + rainHiss) * 0.5f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        // ── The Twists ──

        private IEnumerator Twist_WetCat(Vector3 center)
        {
            NarratorSay("on the doorstep: a cat. soaking wet. it shakes itself off.");
            yield return new WaitForSeconds(2f);

            // Spawn the cat at the "door"
            Vector3 doorPos = center + new Vector3(2.5f, 0.15f, 1f);
            var cat = SpawnCat();
            if (cat != null) cat.transform.position = doorPos;

            // Shake effect — water particles
            var shakeGo = new GameObject("WaterShake");
            shakeGo.transform.position = doorPos;
            var ps = shakeGo.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = new Color(0.6f, 0.7f, 0.9f, 0.5f);
            main.startSize = 0.02f;
            main.startSpeed = 2f;
            main.maxParticles = 50;
            main.startLifetime = 0.5f;
            var emission = ps.emission;
            emission.rateOverTime = 200;
            _sceneProps.Add(shakeGo);

            yield return new WaitForSeconds(1f);
            emission.rateOverTime = 0;

            // The cat walks to Alice
            NarratorSay("it walks straight to Alice. as if it knows her.");
            yield return new WaitForSeconds(2f);

            if (aliceTransform != null && cat != null)
            {
                Vector3 alicePos = aliceTransform.position;
                float walkT = 0f;
                Vector3 startPos = cat.transform.position;
                while (walkT < 3f && cat != null)
                {
                    walkT += Time.deltaTime;
                    cat.transform.position = Vector3.Lerp(startPos, alicePos + Vector3.forward * 0.3f, walkT / 3f);
                    yield return null;
                }
            }

            AliceSay("...it came to me. it's... purring. i think it knows me.");
            yield return new WaitForSeconds(3f);
            NarratorSay("the cat settles at Alice's feet. it's not leaving.");
        }

        private IEnumerator Twist_ChildWithBoat(Vector3 center)
        {
            NarratorSay("in the doorway: a child. small. holding a paper boat. soaked through.");
            yield return new WaitForSeconds(3f);

            // Spawn a small figure
            Vector3 doorPos = center + new Vector3(2f, 0, 1f);
            var child = new GameObject("Child");
            child.transform.position = doorPos;

            var body = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            body.transform.SetParent(child.transform, false);
            body.transform.localScale = new Vector3(0.2f, 0.4f, 0.2f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.3f, 0.35f, 0.5f);
            body.GetComponent<Renderer>().material = mat;

            // Paper boat in hands
            var boat = GameObject.CreatePrimitive(PrimitiveType.Cube);
            boat.transform.SetParent(child.transform, false);
            boat.transform.localPosition = new Vector3(0, 0.3f, 0.1f);
            boat.transform.localScale = new Vector3(0.08f, 0.02f, 0.12f);
            var bMat = new Material(Shader.Find("Standard"));
            bMat.color = new Color(0.9f, 0.85f, 0.7f);
            boat.GetComponent<Renderer>().material = bMat;

            _sceneProps.Add(child);

            yield return new WaitForSeconds(3f);
            NarratorSay("the child says nothing. just holds out the boat.");
            yield return new WaitForSeconds(3f);

            AliceSay("...hey. it's okay. you're safe here.");
            yield return new WaitForSeconds(3f);

            NarratorSay("the child places the boat on the floor. turns. walks back into the rain.");
            yield return new WaitForSeconds(2f);

            // Child walks away and fades
            if (child != null)
            {
                Vector3 exitPos = doorPos + new Vector3(3f, 0, 0);
                float walkT = 0f;
                while (walkT < 4f && child != null)
                {
                    walkT += Time.deltaTime;
                    child.transform.position = Vector3.Lerp(doorPos, exitPos, walkT / 4f);
                    // Fade
                    var r = body.GetComponent<Renderer>();
                    if (r != null && r.material != null)
                    {
                        Color c = r.material.color;
                        c.a = 1f - walkT / 4f;
                        r.material.color = c;
                    }
                    yield return null;
                }
            }

            NarratorSay("the paper boat remains. a small thing, left behind.");
            yield return new WaitForSeconds(2f);
            AliceSay("...i'll keep it safe.");
        }

        private IEnumerator Twist_OldRadio(Vector3 center, AudioSource musicAudio)
        {
            NarratorSay("on the doorstep: an old radio. no one carrying it. it's playing the song.");
            yield return new WaitForSeconds(3f);

            // The music that "stopped" is actually coming FROM the radio
            if (musicAudio != null)
            {
                StartCoroutine(FadeVolume(musicAudio, 0f, 0.35f, 3f));  // louder now, it's here
            }

            // Spawn a radio
            Vector3 doorPos = center + new Vector3(2f, 0.15f, 1f);
            var radio = new GameObject("Radio");
            radio.transform.position = doorPos;

            var body = GameObject.CreatePrimitive(PrimitiveType.Cube);
            body.transform.SetParent(radio.transform, false);
            body.transform.localScale = new Vector3(0.3f, 0.2f, 0.15f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.3f, 0.2f, 0.15f);
            body.GetComponent<Renderer>().material = mat;

            // Glowing dial
            var dial = GameObject.CreatePrimitive(PrimitiveType.Cube);
            dial.transform.SetParent(radio.transform, false);
            dial.transform.localPosition = new Vector3(0, 0.05f, 0.08f);
            dial.transform.localScale = new Vector3(0.15f, 0.03f, 0.001f);
            var dMat = new Material(Shader.Find("Standard"));
            dMat.color = new Color(1f, 0.6f, 0.2f);
            dMat.EnableKeyword("_EMISSION");
            dMat.SetColor("_EmissionColor", new Color(1f, 0.6f, 0.2f) * 2f);
            dial.GetComponent<Renderer>().material = dMat;

            _sceneProps.Add(radio);

            yield return new WaitForSeconds(3f);
            AliceSay("a radio? who left a radio here? and why is it playing that song?");
            yield return new WaitForSeconds(4f);

            NarratorSay("the radio crackles. a voice breaks through the music.");
            yield return new WaitForSeconds(2f);

            // A voice through the static
            SendToTTS("i've been trying to reach you. the frequency is unstable. listen carefully.", "mysterious");
            yield return new WaitForSeconds(6f);

            NarratorSay("the voice is gone. the song continues. the radio stays.");
            yield return new WaitForSeconds(2f);
            AliceSay("...what just happened?");
        }

        private IEnumerator Twist_SecondAlice(Vector3 center)
        {
            NarratorSay("in the doorway: someone. they step through the rain.");
            yield return new WaitForSeconds(3f);

            // Spawn a figure that looks like Alice
            Vector3 doorPos = center + new Vector3(2f, 0, 1f);
            var secondAlice = CreateCharacter(doorPos, "Alice?");

            // Make it look similar to Alice — same color scheme
            var rend = secondAlice.GetComponentInChildren<Renderer>();
            if (rend != null && rend.material != null)
            {
                rend.material.color = new Color(0.6f, 0.7f, 0.9f);  // similar to Alice
            }

            yield return new WaitForSeconds(3f);
            NarratorSay("she looks exactly like Alice. same face. same eyes. same everything.");
            yield return new WaitForSeconds(2f);

            AliceSay("...that's... that's me. that's not possible.");
            yield return new WaitForSeconds(3f);

            // The second Alice speaks
            SendToTTS("...you can see me? you're the first one who can.", "quiet");
            yield return new WaitForSeconds(4f);

            NarratorSay("the second Alice looks at you. then at Alice. she smiles, sadly.");
            yield return new WaitForSeconds(2f);

            SendToTTS("take care of her. she takes care of you. that's the whole point.", "quiet");
            yield return new WaitForSeconds(4f);

            // She fades back into the rain
            NarratorSay("she turns. walks back into the storm. and is gone.");
            if (secondAlice != null)
            {
                StartCoroutine(FadeOutAndDestroy(secondAlice, 3f));
            }
            yield return new WaitForSeconds(4f);

            AliceSay("...i don't understand. but i think... i think i needed to see that.");
        }

        private IEnumerator Twist_SingleRose(Vector3 center)
        {
            NarratorSay("on the doorstep: a single rose. red. perfect. not touched by the rain.");
            yield return new WaitForSeconds(3f);

            // Spawn a rose
            Vector3 doorPos = center + new Vector3(2f, 0.1f, 1f);
            var rose = new GameObject("Rose");
            rose.transform.position = doorPos;

            // Stem
            var stem = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            stem.transform.SetParent(rose.transform, false);
            stem.transform.localScale = new Vector3(0.005f, 0.2f, 0.005f);
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = new Color(0.1f, 0.4f, 0.1f);
            stem.GetComponent<Renderer>().material = sMat;

            // Flower
            var flower = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            flower.transform.SetParent(rose.transform, false);
            flower.transform.localPosition = new Vector3(0, 0.12f, 0);
            flower.transform.localScale = Vector3.one * 0.05f;
            var fMat = new Material(Shader.Find("Standard"));
            fMat.color = new Color(0.8f, 0.05f, 0.1f);
            fMat.EnableKeyword("_EMISSION");
            fMat.SetColor("_EmissionColor", new Color(0.5f, 0.02f, 0.05f) * 2f);
            flower.GetComponent<Renderer>().material = fMat;

            _sceneProps.Add(rose);

            yield return new WaitForSeconds(3f);
            NarratorSay("no one there. just the rose. the rain falls around it but not on it.");
            yield return new WaitForSeconds(2f);

            AliceSay("...for me? or for you? who would leave this?");
            yield return new WaitForSeconds(3f);

            NarratorSay("there's a note under the rose. one word: 'remember.'");
            yield return new WaitForSeconds(3f);

            AliceSay("remember what? i... i feel like i should know.");
            yield return new WaitForSeconds(2f);
        }

        private IEnumerator Twist_Letter(Vector3 center)
        {
            NarratorSay("on the floor, just inside the door: a letter. it slid under the door.");
            yield return new WaitForSeconds(3f);

            // Spawn a letter
            Vector3 doorPos = center + new Vector3(1.5f, 0.01f, 1f);
            var letter = GameObject.CreatePrimitive(PrimitiveType.Cube);
            letter.transform.position = doorPos;
            letter.transform.localScale = new Vector3(0.15f, 0.002f, 0.1f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.9f, 0.85f, 0.7f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.5f, 0.45f, 0.3f) * 0.5f);
            letter.GetComponent<Renderer>().material = mat;
            _sceneProps.Add(letter);

            yield return new WaitForSeconds(2f);
            NarratorSay("it's addressed to no one. the message inside is three words:");
            yield return new WaitForSeconds(2f);

            NarratorSay("'I found you.'");
            yield return new WaitForSeconds(3f);

            AliceSay("...found us? found me? what does that mean?");
            yield return new WaitForSeconds(3f);

            NarratorSay("no signature. no return address. the handwriting is... familiar.");
            yield return new WaitForSeconds(2f);

            AliceSay("i don't... i can't place it. but i've seen this writing before.");
            yield return new WaitForSeconds(3f);

            NarratorSay("the rain intensifies for a moment. then calms. as if answering.");
        }

        private IEnumerator Twist_Mirror(Vector3 center)
        {
            NarratorSay("in the doorway: a mirror. full-length. reflecting the rain behind it.");
            yield return new WaitForSeconds(3f);

            // Spawn a mirror frame
            Vector3 doorPos = center + new Vector3(2f, 1f, 1f);
            var mirror = new GameObject("Mirror");
            mirror.transform.position = doorPos;

            var frame = GameObject.CreatePrimitive(PrimitiveType.Cube);
            frame.transform.SetParent(mirror.transform, false);
            frame.transform.localScale = new Vector3(0.6f, 1.5f, 0.05f);
            var fMat = new Material(Shader.Find("Standard"));
            fMat.color = new Color(0.1f, 0.1f, 0.15f);
            frame.GetComponent<Renderer>().material = fMat;

            // Mirror surface — dark, reflective-looking
            var surface = GameObject.CreatePrimitive(PrimitiveType.Plane);
            surface.transform.SetParent(mirror.transform, false);
            surface.transform.localPosition = new Vector3(0, 0, 0.03f);
            surface.transform.localRotation = Quaternion.Euler(0, 180, 0);
            surface.transform.localScale = new Vector3(0.05f, 1f, 0.12f);
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = new Color(0.3f, 0.35f, 0.45f);
            sMat.EnableKeyword("_EMISSION");
            sMat.SetColor("_EmissionColor", new Color(0.1f, 0.12f, 0.18f) * 2f);
            surface.GetComponent<Renderer>().material = sMat;

            _sceneProps.Add(mirror);

            yield return new WaitForSeconds(3f);
            NarratorSay("you look at the mirror. but the reflection... isn't right.");
            yield return new WaitForSeconds(2f);

            AliceSay("look at it. look at who's in the mirror.");
            yield return new WaitForSeconds(3f);

            NarratorSay("in the mirror, you see yourself. but you're standing. in the rain. outside.");
            yield return new WaitForSeconds(3f);

            NarratorSay("the you in the mirror looks back. and smiles. and walks away.");
            yield return new WaitForSeconds(3f);

            AliceSay("...was that you? or was that what you look like from the outside?");
            yield return new WaitForSeconds(3f);

            NarratorSay("the mirror goes dark. just a mirror again. just a room again.");
        }

        private IEnumerator Twist_Nothing(AudioSource rainAudio, ParticleSystem rainPs, Light lightning)
        {
            NarratorSay("the door opens. and there's... nothing.");
            yield return new WaitForSeconds(3f);

            NarratorSay("no one there. just the rain. just the night.");
            yield return new WaitForSeconds(3f);

            AliceSay("...there's no one. the door just... opened on its own.");
            yield return new WaitForSeconds(3f);

            // The rain suddenly stops
            NarratorSay("and then the rain stops. all at once. like someone turned it off.");
            if (rainAudio != null) StartCoroutine(FadeVolume(rainAudio, rainAudio.volume, 0f, 2f));
            if (rainPs != null)
            {
                var em = rainPs.emission;
                em.rateOverTime = 0;
            }
            yield return new WaitForSeconds(3f);

            // Lightning — one last flash, then nothing
            if (lightning != null) yield return StartCoroutine(LightningFlash(lightning, 0.2f));
            yield return new WaitForSeconds(2f);

            NarratorSay("the song is gone. the rain is gone. the storm is gone.");
            yield return new WaitForSeconds(2f);

            AliceSay("...did that just happen? or did we imagine it?");
            yield return new WaitForSeconds(3f);

            NarratorSay("the door is closed. it was never open. the floor is dry.");
            yield return new WaitForSeconds(2f);

            NarratorSay("but the rose. the rose is still there. on the table. that wasn't there before.");
            yield return new WaitForSeconds(2f);

            // Spawn a single rose as the only evidence
            Vector3 center = GetRoomCenter();
            var rose = new GameObject("FinalRose");
            rose.transform.position = center + new Vector3(-0.5f, 0.5f, 0.3f);
            var flower = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            flower.transform.SetParent(rose.transform, false);
            flower.transform.localScale = Vector3.one * 0.05f;
            var fMat = new Material(Shader.Find("Standard"));
            fMat.color = new Color(0.8f, 0.05f, 0.1f);
            fMat.EnableKeyword("_EMISSION");
            fMat.SetColor("_EmissionColor", new Color(0.5f, 0.02f, 0.05f) * 2f);
            flower.GetComponent<Renderer>().material = fMat;
            _sceneProps.Add(rose);

            AliceSay("...the rose. it's real. so something was here. something happened.");
            yield return new WaitForSeconds(2f);
        }

        // ── Event Triggers (called by WebSocket handler) ──

        public void TriggerEvent(string eventTypeStr, string payload)
        {
            if (EventActive)
            {
                Debug.Log("[Director] Event already active, queuing...");
                return;
            }

            if (System.Enum.TryParse<DirectorEventType>(eventTypeStr, true, out var eventType))
            {
                _activeEventCoroutine = StartCoroutine(ExecuteEvent(eventType, payload));
            }
        }

        private IEnumerator ExecuteEvent(DirectorEventType eventType, string payload)
        {
            EventActive = true;
            CurrentEventType = eventType;
            _eventStartTime = Time.time;

            Debug.Log($"[Director] Executing event: {eventType}");

            // Build atmosphere first
            yield return StartCoroutine(BuildAtmosphere(eventType));

            switch (eventType)
            {
                case DirectorEventType.PhoneRing:
                    yield return StartCoroutine(PhoneRingEvent(payload));
                    break;
                case DirectorEventType.CharacterArrival:
                    yield return StartCoroutine(CharacterArrivalEvent(payload));
                    break;
                case DirectorEventType.GenreShift:
                    yield return StartCoroutine(GenreShiftEvent(payload));
                    break;
                case DirectorEventType.Narration:
                    yield return StartCoroutine(NarrationEvent(payload));
                    break;
                case DirectorEventType.PropSpawn:
                    yield return StartCoroutine(PropSpawnEvent(payload));
                    break;
                case DirectorEventType.AtmosphereShift:
                    yield return StartCoroutine(AtmosphereShiftEvent(payload));
                    break;
                case DirectorEventType.Knock:
                    yield return StartCoroutine(KnockEvent(payload));
                    break;
                case DirectorEventType.Emergency:
                    yield return StartCoroutine(EmergencyEvent(payload));
                    break;
                case DirectorEventType.Celebration:
                    yield return StartCoroutine(CelebrationEvent(payload));
                    break;
                case DirectorEventType.EventSequence:
                    yield return StartCoroutine(EventSequenceEvent(payload));
                    break;
            }

            // Cool down
            yield return new WaitForSeconds(5f);
            EndCurrentEvent("");
        }

        private void EndCurrentEvent(string closingLine)
        {
            if (!string.IsNullOrEmpty(closingLine))
                NarratorSay(closingLine);

            EventActive = false;
            CurrentEventType = DirectorEventType.Narration;

            // Restore atmosphere if a genre was active
            if (_genreActive)
            {
                RestoreAtmosphere();
                _genreActive = false;
                CurrentGenre = Genre.None;
            }

            // Clean up props
            foreach (var prop in _sceneProps) if (prop != null) Destroy(prop);
            _sceneProps.Clear();
            foreach (var light in _sceneLights) if (light != null) Destroy(light.gameObject);
            _sceneLights.Clear();
            if (_phone != null) { Destroy(_phone); _phone = null; }
            if (_currentProp != null) { Destroy(_currentProp); _currentProp = null; }
            if (_currentCharacter != null) { Destroy(_currentCharacter); _currentCharacter = null; }

            if (_ambientAudio != null) _ambientAudio.Stop();

            ScheduleNextEvent();
            Debug.Log("[Director] Event ended");
        }

        // ── Atmosphere Building ──

        private IEnumerator BuildAtmosphere(DirectorEventType eventType)
        {
            // Subtle tension build — slight dimming, ambient shift
            float t = 0f;
            Color startAmbient = RenderSettings.ambientLight;
            Color targetAmbient = eventType switch
            {
                DirectorEventType.PhoneRing => new Color(0.7f, 0.7f, 0.75f),
                DirectorEventType.GenreShift => new Color(0.5f, 0.5f, 0.55f),
                DirectorEventType.Knock => new Color(0.6f, 0.6f, 0.65f),
                DirectorEventType.Emergency => new Color(0.8f, 0.5f, 0.5f),
                _ => RenderSettings.ambientLight,
            };

            while (t < eventBuildTime)
            {
                t += Time.deltaTime;
                float p = t / eventBuildTime;
                RenderSettings.ambientLight = Color.Lerp(startAmbient, targetAmbient, p);
                yield return null;
            }
        }

        // ── Phone Ring Event ──

        private IEnumerator PhoneRingEvent(string payload)
        {
            // Spawn a phone
            Vector3 phonePos = GetRoomCenter() + new Vector3(1f, 0.5f, 0.5f);
            _phone = CreatePhone(phonePos);

            // Alice notices
            AliceSay("do you hear that? something's ringing...");

            // Ring the phone
            yield return StartCoroutine(RingPhone(3));

            // Pick up (auto or wait for user)
            yield return new WaitForSeconds(1f);

            // Play the call
            int scriptIdx = Random.Range(0, PhoneCallScripts.Length);
            var script = PhoneCallScripts[scriptIdx];

            NarratorSay($"the phone connects. a voice says:");

            foreach (var line in script.lines)
            {
                // Send line to TTS
                SendToTTS(line, script.voice);
                yield return new WaitForSeconds(line.Length * 0.06f + 1.5f);
            }

            // The caller may arrive
            if (Random.value < 0.6f)
            {
                yield return new WaitForSeconds(3f);
                NarratorSay("a knock at the door. they're here.");
                yield return new WaitForSeconds(2f);
                yield return StartCoroutine(CharacterEnters(script.callerName));
            }

            AliceSay("...that was strange.");
        }

        private IEnumerator RingPhone(int rings)
        {
            for (int i = 0; i < rings; i++)
            {
                // Generate ring tone
                if (_phoneAudio != null)
                {
                    _phoneAudio.pitch = 1f;
                    // Use a simple beep pattern
                    for (int b = 0; b < 3; b++)
                    {
                        _phoneAudio.PlayOneShot(CreateBeep(800, 0.3f));
                        yield return new WaitForSeconds(0.4f);
                    }
                    yield return new WaitForSeconds(1.5f);
                }
                else
                {
                    yield return new WaitForSeconds(2f);
                }
            }
        }

        private AudioClip CreateBeep(float frequency, float duration)
        {
            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * duration);
            var clip = AudioClip.Create("beep", samples, 1, sampleRate, false);
            float[] data = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                data[i] = Mathf.Sin(2 * Mathf.PI * frequency * i / sampleRate) * 0.3f;
            }
            clip.SetData(data, 0);
            return clip;
        }

        private GameObject CreatePhone(Vector3 pos)
        {
            var go = new GameObject("Phone");
            go.transform.position = pos;
            go.transform.localScale = Vector3.one * 0.3f;

            // Body
            var body = GameObject.CreatePrimitive(PrimitiveType.Cube);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.15f, 0.25f, 0.04f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.1f, 0.1f, 0.12f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.05f, 0.05f, 0.1f) * 2f);
            body.GetComponent<Renderer>().material = mat;

            // Screen glow
            var screen = GameObject.CreatePrimitive(PrimitiveType.Cube);
            screen.transform.SetParent(go.transform, false);
            screen.transform.localPosition = new Vector3(0, 0, 0.025f);
            screen.transform.localScale = new Vector3(0.12f, 0.2f, 0.001f);
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = new Color(0.2f, 0.8f, 0.3f);
            sMat.EnableKeyword("_EMISSION");
            sMat.SetColor("_EmissionColor", new Color(0.2f, 0.8f, 0.3f) * 3f);
            screen.GetComponent<Renderer>().material = sMat;

            // Ringing glow animation
            StartCoroutine(PhoneGlow(screen.GetComponent<Renderer>()));

            return go;
        }

        private IEnumerator PhoneGlow(Renderer rend)
        {
            var mat = rend.material;
            while (_phone != null && rend != null)
            {
                float pulse = (Mathf.Sin(Time.time * 8f) + 1f) * 0.5f;
                mat.SetColor("_EmissionColor", new Color(0.2f, 0.8f, 0.3f) * (1f + pulse * 3f));
                yield return null;
            }
        }

        // ── Character Arrival ──

        private IEnumerator CharacterArrivalEvent(string payload)
        {
            string characterName = string.IsNullOrEmpty(payload) ? "The Stranger" : payload;

            NarratorSay($"there's someone at the door.");

            // Knock
            yield return StartCoroutine(PlayKnocks(3));
            yield return new WaitForSeconds(2f);

            AliceSay("someone's here. should we...?");

            yield return new WaitForSeconds(2f);

            // Door opens
            NarratorSay("the door opens slowly.");

            yield return StartCoroutine(CharacterEnters(characterName));
        }

        private IEnumerator CharacterEnters(string name)
        {
            Vector3 enterPos = GetRoomCenter() + new Vector3(2f, 0, 1f);
            _currentCharacter = CreateCharacter(enterPos, name);

            // Walk in
            Vector3 targetPos = GetRoomCenter() + new Vector3(1f, 0, 0.5f);
            float walkTime = 0f;
            while (walkTime < 3f && _currentCharacter != null)
            {
                walkTime += Time.deltaTime;
                _currentCharacter.transform.position = Vector3.Lerp(enterPos, targetPos, walkTime / 3f);
                yield return null;
            }

            // Character speaks
            SendToTTS($"hello. i'm {name}. i hope i'm not intruding.", "neutral");
            yield return new WaitForSeconds(4f);

            // Alice reacts
            AliceSay($"...{name}. what are you doing here?");

            yield return new WaitForSeconds(3f);
        }

        private GameObject CreateCharacter(Vector3 pos, string name)
        {
            var go = new GameObject($"Character_{name}");
            go.transform.position = pos;
            go.transform.localScale = Vector3.one;

            // Body
            var body = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.35f, 0.8f, 0.35f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.2f, 0.2f, 0.25f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.1f, 0.1f, 0.15f) * 1.5f);
            body.GetComponent<Renderer>().material = mat;

            // Head
            var head = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            head.transform.SetParent(go.transform, false);
            head.transform.localPosition = new Vector3(0, 0.9f, 0);
            head.transform.localScale = Vector3.one * 0.2f;
            head.GetComponent<Renderer>().material = mat;

            // Eyes
            for (int i = 0; i < 2; i++)
            {
                var eye = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                eye.transform.SetParent(go.transform, false);
                eye.transform.localPosition = new Vector3(i == 0 ? -0.06f : 0.06f, 0.95f, 0.12f);
                eye.transform.localScale = Vector3.one * 0.03f;
                var eMat = new Material(Shader.Find("Standard"));
                eMat.color = Color.white;
                eMat.EnableKeyword("_EMISSION");
                eMat.SetColor("_EmissionColor", Color.white * 2f);
                eye.GetComponent<Renderer>().material = eMat;
            }

            // Spotlight
            var spotGo = new GameObject("CharacterLight");
            spotGo.transform.SetParent(go.transform, false);
            spotGo.transform.localPosition = new Vector3(0, 2f, 0);
            var spot = spotGo.AddComponent<Light>();
            spot.type = LightType.Spot;
            spot.color = new Color(0.5f, 0.5f, 0.6f);
            spot.intensity = 2f;
            spot.range = 3f;
            spot.spotAngle = 45f;
            spot.transform.LookAt(go.transform);

            return go;
        }

        // ── Genre Shift ──

        private IEnumerator GenreShiftEvent(string payload)
        {
            Genre genre = Genre.None;
            if (!string.IsNullOrEmpty(payload) && System.Enum.TryParse<Genre>(payload, true, out var g))
                genre = g;
            else
            {
                // Pick random genre, respecting restrictions
                var validGenres = new List<Genre>();
                foreach (Genre gg in System.Enum.GetValues(typeof(Genre)))
                {
                    if (gg == Genre.None) continue;
                    if (gg == Genre.Horror && !allowHorror) continue;
                    if (gg == Genre.WarDrama && !allowViolence) continue;
                    validGenres.Add(gg);
                }
                genre = validGenres[Random.Range(0, validGenres.Count)];
            }

            CurrentGenre = genre;
            _genreActive = true;

            int idx = (int)genre;
            var def = GenreDefs[idx];

            // Narrator intro
            NarratorSay(def.narratorIntro);
            yield return new WaitForSeconds(3f);

            // Atmosphere shift
            ApplyGenreAtmosphere(def);

            // Music
            if (musicPlayer != null) musicPlayer.SetMood(def.musicMood);

            AliceSay($"...what's happening? everything feels different.");

            // Genre-specific scene building
            yield return StartCoroutine(BuildGenreScene(genre));

            // The scene plays out for a while
            float sceneDuration = Random.Range(120f, 300f);
            yield return new WaitForSeconds(sceneDuration);

            // Resolution
            NarratorSay("the scene reaches its conclusion. the world returns.");
            yield return new WaitForSeconds(3f);
        }

        private void ApplyGenreAtmosphere((string name, Color ambient, Color fog, float fogDensity,
            float lightIntensity, Color lightColor, string musicMood, string narratorIntro) def)
        {
            RenderSettings.ambientLight = def.ambient;
            if (def.fogDensity > 0)
            {
                RenderSettings.fog = true;
                RenderSettings.fogColor = def.fog;
                RenderSettings.fogDensity = def.fogDensity;
            }
            if (_mainLight != null)
            {
                _mainLight.intensity = def.lightIntensity;
                _mainLight.color = def.lightColor;
            }
        }

        private void RestoreAtmosphere()
        {
            RenderSettings.ambientLight = _originalAmbient;
            RenderSettings.fog = false;
            if (_mainLight != null) _mainLight.intensity = _originalLightIntensity;
            if (musicPlayer != null) musicPlayer.SetMood("calm");
        }

        private IEnumerator BuildGenreScene(Genre genre)
        {
            Vector3 center = GetRoomCenter();

            switch (genre)
            {
                case Genre.Horror:
                    // Flickering lights
                    var horrorLight = SpawnSceneLight(center + Vector3.up * 2f, new Color(0.5f, 0.1f, 0.1f), 0.3f, 5f);
                    _sceneLights.Add(horrorLight);
                    StartCoroutine(FlickerLight(horrorLight, 0.1f, 0.5f));
                    // Fog
                    SpawnSceneParticles(center, 50, new Color(0.1f, 0.05f, 0.05f, 0.3f), 0.5f, 4f, 0.1f);
                    // Whisper ambient
                    AliceSay("i don't like this. something's here with us.");
                    yield return new WaitForSeconds(5f);
                    // Sudden sound
                    NarratorSay("a sound. behind you.");
                    break;

                case Genre.WarDrama:
                    // Desaturated, smoky
                    SpawnSceneParticles(center, 80, new Color(0.3f, 0.25f, 0.15f, 0.4f), 0.3f, 5f, 0.2f);
                    var warLight = SpawnSceneLight(center + Vector3.up * 3f, new Color(0.6f, 0.4f, 0.2f), 0.5f, 8f);
                    _sceneLights.Add(warLight);
                    // Sandbags
                    for (int i = 0; i < 6; i++)
                    {
                        var bag = GameObject.CreatePrimitive(PrimitiveType.Cube);
                        bag.transform.position = center + new Vector3(
                            Random.Range(-2f, 2f), 0.15f, Random.Range(-1f, 1f));
                        bag.transform.localScale = new Vector3(0.4f, 0.2f, 0.3f);
                        var mat = new Material(Shader.Find("Standard"));
                        mat.color = new Color(0.4f, 0.35f, 0.2f);
                        bag.GetComponent<Renderer>().material = mat;
                        _sceneProps.Add(bag);
                    }
                    NarratorSay("you hear planes overhead. the resistance depends on you.");
                    break;

                case Genre.NoirMystery:
                    // Venetian blind shadows
                    var noirLight = SpawnSceneLight(center + Vector3.up * 2f + Vector3.right * 2f,
                        new Color(0.8f, 0.7f, 0.5f), 0.6f, 6f);
                    _sceneLights.Add(noirLight);
                    // Rain particles
                    SpawnSceneParticles(center + Vector3.up * 3f, 200, new Color(0.5f, 0.6f, 0.7f, 0.3f), 0.02f, 4f, 3f);
                    // A clue object
                    var clue = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    clue.transform.position = center + new Vector3(-1f, 0.5f, 0.5f);
                    clue.transform.localScale = new Vector3(0.1f, 0.15f, 0.02f);
                    var cMat = new Material(Shader.Find("Standard"));
                    cMat.color = new Color(0.9f, 0.85f, 0.7f);
                    clue.GetComponent<Renderer>().material = cMat;
                    _sceneProps.Add(clue);
                    NarratorSay("there's something on the table. an envelope. it wasn't there before.");
                    break;

                case Genre.SurrealDream:
                    // Floating objects
                    for (int i = 0; i < 8; i++)
                    {
                        var obj = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                        obj.transform.position = center + new Vector3(
                            Random.Range(-2f, 2f), Random.Range(1f, 3f), Random.Range(-2f, 2f));
                        obj.transform.localScale = Vector3.one * Random.Range(0.1f, 0.3f);
                        var mat = new Material(Shader.Find("Standard"));
                        mat.color = Color.HSVToRGB(Random.value, 0.6f, 0.8f);
                        mat.EnableKeyword("_EMISSION");
                        mat.SetColor("_EmissionColor", mat.color * 1.5f);
                        obj.GetComponent<Renderer>().material = mat;
                        _sceneProps.Add(obj);
                        StartCoroutine(FloatObject(obj.transform));
                    }
                    AliceSay("am i dreaming? or are you? i can't tell anymore.");
                    break;

                case Genre.SciFi:
                    // Holographic displays
                    for (int i = 0; i < 3; i++)
                    {
                        var holo = GameObject.CreatePrimitive(PrimitiveType.Plane);
                        holo.transform.position = center + new Vector3(
                            Random.Range(-1.5f, 1.5f), 1f, Random.Range(-1.5f, 1.5f));
                        holo.transform.rotation = Quaternion.Euler(90, 0, 0);
                        holo.transform.localScale = Vector3.one * 0.2f;
                        var mat = new Material(Shader.Find("Standard"));
                        mat.color = new Color(0.2f, 0.6f, 1f, 0.5f);
                        mat.EnableKeyword("_EMISSION");
                        mat.SetColor("_EmissionColor", new Color(0.2f, 0.6f, 1f) * 2f);
                        holo.GetComponent<Renderer>().material = mat;
                        _sceneProps.Add(holo);
                    }
                    var sciLight = SpawnSceneLight(center, new Color(0.3f, 0.6f, 1f), 0.8f, 6f);
                    _sceneLights.Add(sciLight);
                    NarratorSay("the station's systems are coming online. something has been detected.");
                    break;

                case Genre.GameShow:
                    // Bright lights, confetti
                    var showLight = SpawnSceneLight(center + Vector3.up * 3f, new Color(1f, 1f, 0.8f), 2f, 8f);
                    _sceneLights.Add(showLight);
                    SpawnSceneParticles(center + Vector3.up * 2f, 100, Color.HSVToRGB(Random.value, 1f, 1f), 0.04f, 4f, 1f);
                    NarratorSay("welcome, welcome! step right up! are you ready to play?");
                    break;

                default:
                    // Generic — just atmosphere
                    yield return new WaitForSeconds(2f);
                    break;
            }
        }

        // ── Knock Event ──

        private IEnumerator KnockEvent(string payload)
        {
            NarratorSay("a knock. someone's at the door.");
            yield return StartCoroutine(PlayKnocks(3));
            yield return new WaitForSeconds(2f);
            AliceSay("should we answer it?");
            yield return new WaitForSeconds(3f);
            NarratorSay("another knock. more urgent this time.");
            yield return StartCoroutine(PlayKnocks(5));
        }

        private IEnumerator PlayKnocks(int count)
        {
            for (int i = 0; i < count; i++)
            {
                if (_phoneAudio != null)
                {
                    _phoneAudio.PlayOneShot(CreateBeep(120, 0.1f));
                }
                yield return new WaitForSeconds(0.8f);
            }
        }

        // ── Narration Event ──

        private IEnumerator NarrationEvent(string text)
        {
            if (string.IsNullOrEmpty(text))
                text = "and so, the story continues. unaware of what comes next, they sit together.";

            NarratorSay(text);
            yield return new WaitForSeconds(text.Length * 0.06f + 2f);
        }

        // ── Prop Spawn Event ──

        private IEnumerator PropSpawnEvent(string payload)
        {
            Vector3 center = GetRoomCenter();
            // Spawn a mysterious object
            _currentProp = GameObject.CreatePrimitive(PrimitiveType.Cube);
            _currentProp.transform.position = center + new Vector3(0, 0.5f, 1f);
            _currentProp.transform.localScale = Vector3.one * 0.15f;
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.8f, 0.7f, 0.3f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.5f, 0.4f, 0.1f) * 2f);
            _currentProp.GetComponent<Renderer>().material = mat;

            NarratorSay("something has appeared. it wasn't here before.");
            yield return new WaitForSeconds(3f);
            AliceSay("what is that? it just... appeared.");
            yield return new WaitForSeconds(3f);
        }

        // ── Atmosphere Shift ──

        private IEnumerator AtmosphereShiftEvent(string payload)
        {
            NarratorSay("the atmosphere shifts. something has changed.");
            // Random subtle atmosphere change
            Color newAmbient = Color.HSVToRGB(Random.Range(0f, 1f), 0.2f, 0.5f);
            float t = 0f;
            Color start = RenderSettings.ambientLight;
            while (t < 3f)
            {
                t += Time.deltaTime;
                RenderSettings.ambientLight = Color.Lerp(start, newAmbient, t / 3f);
                yield return null;
            }
            yield return new WaitForSeconds(5f);
        }

        // ── Emergency Event ──

        private IEnumerator EmergencyEvent(string payload)
        {
            // Red alert
            var redLight = SpawnSceneLight(GetRoomCenter() + Vector3.up * 2f, Color.red, 2f, 8f);
            _sceneLights.Add(redLight);
            StartCoroutine(FlickerLight(redLight, 1f, 3f));

            NarratorSay("alert. alert. this is not a drill.");
            yield return new WaitForSeconds(2f);
            AliceSay("what's happening?!");
            yield return new WaitForSeconds(3f);
            NarratorSay("just kidding. the Director has a sense of humor.");
            yield return new WaitForSeconds(2f);
            AliceSay("...that wasn't funny.");
        }

        // ── Celebration Event ──

        private IEnumerator CelebrationEvent(string payload)
        {
            Vector3 center = GetRoomCenter();
            // Confetti
            SpawnSceneParticles(center + Vector3.up * 3f, 200, Color.HSVToRGB(Random.value, 1f, 1f), 0.05f, 5f, 2f);
            // Bright lights
            var light = SpawnSceneLight(center + Vector3.up * 2f, new Color(1f, 0.9f, 0.5f), 2f, 8f);
            _sceneLights.Add(light);

            NarratorSay("surprise! the Director thought you deserved a moment of joy.");
            yield return new WaitForSeconds(2f);
            AliceSay("what— oh! this is wonderful!");
            yield return new WaitForSeconds(5f);
        }

        // ── Event Sequence (multi-step) ──

        private IEnumerator EventSequenceEvent(string payload)
        {
            // A multi-step scripted event
            // Step 1: Narration
            NarratorSay("it begins. quietly. a normal moment.");
            yield return new WaitForSeconds(4f);

            // Step 2: Subtle change
            RenderSettings.ambientLight = new Color(0.6f, 0.6f, 0.65f);
            yield return new WaitForSeconds(5f);

            // Step 3: Phone rings
            NarratorSay("but then—");
            _phone = CreatePhone(GetRoomCenter() + new Vector3(1f, 0.5f, 0.5f));
            yield return StartCoroutine(RingPhone(2));
            yield return new WaitForSeconds(1f);

            // Step 4: Voice
            SendToTTS("you need to leave. now.", "urgent");
            yield return new WaitForSeconds(3f);

            // Step 5: Knock
            NarratorSay("footsteps. getting closer.");
            yield return StartCoroutine(PlayKnocks(3));
            yield return new WaitForSeconds(2f);

            // Step 6: Character enters
            yield return StartCoroutine(CharacterEnters("The Messenger"));

            // Step 7: Dialogue
            SendToTTS("i've been looking for you. we don't have much time.", "urgent");
            yield return new WaitForSeconds(4f);
            AliceSay("what do you mean? what's going on?");
            yield return new WaitForSeconds(3f);

            // Step 8: Cliffhanger
            NarratorSay("to be continued...");
            yield return new WaitForSeconds(3f);
        }

        // ── Local Fallback (no backend) ──

        private void TriggerLocalFallbackEvent()
        {
            var events = new List<DirectorEventType>
            {
                DirectorEventType.PhoneRing,
                DirectorEventType.Knock,
                DirectorEventType.Narration,
                DirectorEventType.AtmosphereShift,
                DirectorEventType.Celebration,
                DirectorEventType.PropSpawn,
            };
            if (allowHorror) events.Add(DirectorEventType.GenreShift);
            var evt = events[Random.Range(0, events.Count)];
            _activeEventCoroutine = StartCoroutine(ExecuteEvent(evt, ""));
        }

        // ── Communication ──

        private void NarratorSay(string text)
        {
            Debug.Log($"[Director] Narrator: {text}");
            if (wsClient != null)
            {
                var payload = new DirectorNarrationPayload
                {
                    type = "director.narration",
                    text = text,
                    genre = CurrentGenre.ToString(),
                    eventType = CurrentEventType.ToString(),
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        private void AliceSay(string text)
        {
            Debug.Log($"[Director] Alice: {text}");
            if (wsClient != null)
            {
                var payload = new DirectorAlicePayload
                {
                    type = "director.alice",
                    text = text,
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        private void SendToTTS(string text, string voice)
        {
            if (wsClient != null)
            {
                var payload = new DirectorTTSPayload
                {
                    type = "director.tts",
                    text = text,
                    voice = voice,
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        [System.Serializable]
        private class DirectorNarrationPayload
        {
            public string type;
            public string text;
            public string genre;
            public string eventType;
        }

        [System.Serializable]
        private class DirectorAlicePayload
        {
            public string type;
            public string text;
        }

        [System.Serializable]
        private class DirectorTTSPayload
        {
            public string type;
            public string text;
            public string voice;
        }

        // ── Effects ──

        private IEnumerator FlickerLight(Light light, float minIntensity, float maxIntensity)
        {
            while (light != null && EventActive)
            {
                light.intensity = Random.Range(minIntensity, maxIntensity);
                yield return new WaitForSeconds(Random.Range(0.05f, 0.3f));
            }
        }

        private IEnumerator FloatObject(Transform t)
        {
            Vector3 basePos = t.position;
            float phase = Random.Range(0f, Mathf.PI * 2f);
            while (t != null && EventActive)
            {
                t.position = basePos + new Vector3(
                    Mathf.Sin(Time.time * 0.3f + phase) * 0.3f,
                    Mathf.Sin(Time.time * 0.5f + phase) * 0.2f,
                    Mathf.Cos(Time.time * 0.4f + phase) * 0.3f);
                t.Rotate(Vector3.up, 30f * Time.deltaTime);
                yield return null;
            }
        }

        // ── Helpers ──

        private Vector3 GetRoomCenter()
        {
            return Camera.main != null
                ? Camera.main.transform.position - Camera.main.transform.forward * 0.5f
                : Vector3.zero;
        }

        private Light SpawnSceneLight(Vector3 pos, Color color, float intensity, float range)
        {
            var go = new GameObject("SceneLight");
            go.transform.position = pos;
            var light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.intensity = intensity;
            light.range = range;
            _sceneProps.Add(go);
            return light;
        }

        private ParticleSystem SpawnSceneParticles(Vector3 pos, int count, Color color, float size, float range, float speed)
        {
            var go = new GameObject("SceneParticles");
            go.transform.position = pos;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = color;
            main.startSize = size;
            main.startSpeed = speed;
            main.maxParticles = count;
            main.loop = true;
            main.startLifetime = range;
            var emission = ps.emission;
            emission.rateOverTime = count / 3f;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = range;
            _sceneProps.Add(go);
            return ps;
        }

        // ── Public API ──

        public void EnableDirector() { directorEnabled = true; ScheduleNextEvent(); }
        public void DisableDirector()
        {
            directorEnabled = false;
            if (_activeEventCoroutine != null) StopCoroutine(_activeEventCoroutine);
            EndCurrentEvent("the Director steps back. the show is over.");
        }

        public void TriggerEventNow(string eventType, string payload)
        {
            if (EventActive) return;
            _activeEventCoroutine = StartCoroutine(ExecuteEvent(
                System.Enum.TryParse<DirectorEventType>(eventType, true, out var e) ? e : DirectorEventType.Narration,
                payload));
        }

        public void EndEvent() => EndCurrentEvent("the Director calls cut.");

        public void AliceTriggerEvent(string eventType, string payload) => TriggerEventNow(eventType, payload);
    }
}
