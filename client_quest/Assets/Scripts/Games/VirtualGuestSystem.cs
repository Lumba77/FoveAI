using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;
using FoveAI.Creative;

namespace FoveAI.Games
{
    /// <summary>
    /// Virtual Guest System — NPCs that arrive dramatically, have personalities,
    /// make scenes, and interact with the user and Alice.
    ///
    /// Guests can:
    ///   • Arrive with a dramatic entrance (door opens, fanfare, spotlight)
    ///   • Have distinct personalities (loud, shy, chaotic, mysterious, drunk)
    ///   • Make a scene — argue, dance, tell stories, cause trouble
    ///   • Interact with Alice (she reacts to them)
    ///   • Leave dramatically (storm out, fade away, get kicked out)
    ///   • Be summoned by name or randomly drop in
    ///
    /// Guest personalities:
    ///   • The Dramatist — over-the-top, theatrical entrances, monologues
    ///   • The Chaos Agent — breaks things, starts games, stirs up energy
    ///   • The Storyteller — arrives calm, tells a long tale, leaves peacefully
    ///   • The Party Animal — loud, brings music, dances, brings confetti
    ///   • The Mysterious Stranger — arrives in fog, speaks in riddles, vanishes
    ///   • The Rival — challenges you to a game/duel, competitive energy
    ///   • The Old Friend — warm arrival, nostalgic, settles in like co-presence
    /// </summary>
    public class VirtualGuestSystem : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private ScenePresetManager presetManager;
        [SerializeField] private AmbientMusicPlayer musicPlayer;
        [SerializeField] private VRGameEngine gameEngine;

        [Header("Guest Settings")]
        public float arrivalFanfareDuration = 4f;
        public float defaultGuestDuration = 180f;  // 3 minutes
        public int maxConcurrentGuests = 3;
        public float guestSpawnRadius = 2.5f;

        [Header("Visual")]
        public Material guestMatDramatist;
        public Material guestMatChaos;
        public Material guestMatStoryteller;
        public Material guestMatParty;
        public Material guestMatMysterious;
        public Material guestMatRival;
        public Material guestMatFriend;

        // ── Guest Types ──
        public enum GuestType
        {
            Dramatist,
            ChaosAgent,
            Storyteller,
            PartyAnimal,
            MysteriousStranger,
            Rival,
            OldFriend,
        }

        // ── Guest Instance ──
        public class Guest
        {
            public GameObject obj;
            public GuestType type;
            public string name;
            public Color color;
            public Material material;
            public float arrivalTime;
            public float duration;
            public float leaveTime;
            public bool hasLeft;
            public GuestState state;
            public float stateTimer;
            public Vector3 anchorPos;
            public Quaternion anchorRot;
            public Renderer renderer;
            public Light spotlight;
            public ParticleSystem aura;
        }

        public enum GuestState
        {
            Arriving,       // dramatic entrance
            MakingScene,    // active behavior
            Interacting,    // talking/reacting
            Leaving,        // exit animation
            Gone,
        }

        private readonly List<Guest> _guests = new List<Guest>();

        // ── Guest Definitions ──
        private static readonly (string name, Color color, string entranceLine, string[] sceneLines, string exitLine)[] GuestDefs =
        {
            // Dramatist
            (
                "The Dramatist",
                new Color(1f, 0.2f, 0.3f, 1f),
                "*BURSTS through the door* LADIES AND GENTLEMEN!",
                new[] {
                    "You won't BELIEVE what happened to me today!",
                    "This calls for a MONOLOGUE. *clears throat dramatically*",
                    "The world is a STAGE, and I am its LEAD!",
                    "*gestures wildly* And THEN, the dragon said—",
                },
                "*bows* Until we meet again! *exits with flourish*"
            ),
            // Chaos Agent
            (
                "The Chaos Agent",
                new Color(1f, 0.5f, 0f, 1f),
                "*kicks door open* HEY. Let's make this INTERESTING.",
                new[] {
                    "I brought CHAOS. You're welcome.",
                    "Who wants to play a game? No? TOO BAD.",
                    "*knocks something over* Oops. Was that important?",
                    "Let's spice things up! *spawns confetti*",
                },
                "*cackles* Same time next chaos? *vanishes in smoke*"
            ),
            // Storyteller
            (
                "The Storyteller",
                new Color(0.4f, 0.6f, 1f, 1f),
                "*enters quietly, sits down* ...I have a story for you.",
                new[] {
                    "Once, in a world not so different from this one...",
                    "The hero stood at the edge of everything...",
                    "...and that's when they realized the truth.",
                    "But that's a story for another time.",
                },
                "*stands slowly* ...the story ends here. For now. *fades*"
            ),
            // Party Animal
            (
                "The Party Animal",
                new Color(1f, 0.2f, 0.8f, 1f),
                "*slides in with music blasting* LET'S GOOOO!",
                new[] {
                    "I brought the VIBES! *dances*",
                    "This needs MORE confetti! *throws confetti*",
                    "Turn it UP! *starts a dance circle*",
                    "Who's ready to PARTY?!",
                },
                "*moonwalks out* Same time, same place! *drops mic*"
            ),
            // Mysterious Stranger
            (
                "The Stranger",
                new Color(0.5f, 0f, 0.8f, 1f),
                "*materializes from fog* ...I've been watching.",
                new[] {
                    "The answer you seek is closer than you think.",
                    "...you remind me of someone. Someone from before.",
                    "The walls remember more than you know.",
                    "...time is a circle. And you are at its center.",
                },
                "*steps backward into shadow* ...we will meet again. *dissolves*"
            ),
            // Rival
            (
                "The Rival",
                new Color(0.9f, 0.1f, 0.1f, 1f),
                "*struts in* So. You think you're the best here?",
                new[] {
                    "I challenge you. Right here, right now.",
                    "Let's see what you've got.",
                    "You're going DOWN. *cracks knuckles*",
                    "First to 10 points wins. Ready?",
                },
                "*grudgingly* ...not bad. Until next time. *walks out*"
            ),
            // Old Friend
            (
                "An Old Friend",
                new Color(0.3f, 0.9f, 0.5f, 1f),
                "*walks in warmly* Hey... it's been a while.",
                new[] {
                    "Remember that time? That was good.",
                    "You look well. The space suits you.",
                    "*sits down* ...it's nice to just be here again.",
                    "Some things don't need words, do they?",
                },
                "*hugs* Take care of yourself. *walks into the light*"
            ),
        };

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (presetManager == null) presetManager = FindAnyObjectByType<ScenePresetManager>();
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            if (gameEngine == null) gameEngine = FindAnyObjectByType<VRGameEngine>();
        }

        private void Update()
        {
            // Update all guests
            for (int i = _guests.Count - 1; i >= 0; i--)
            {
                var guest = _guests[i];
                if (guest.hasLeft)
                {
                    _guests.RemoveAt(i);
                    continue;
                }

                UpdateGuest(guest);
            }
        }

        // ── Summoning ──

        /// <summary>Summon a specific guest by type.</summary>
        public Guest SummonGuest(GuestType type, float duration = 0f)
        {
            if (_guests.Count >= maxConcurrentGuests) return null;
            if (duration <= 0f) duration = defaultGuestDuration;

            int idx = (int)type;
            var def = GuestDefs[idx];
            var guest = new Guest
            {
                type = type,
                name = def.name,
                color = def.color,
                duration = duration,
                arrivalTime = Time.time,
                leaveTime = Time.time + duration,
                state = GuestState.Arriving,
                stateTimer = 0f,
            };

            // Spawn position — from "the door" (room edge)
            Vector3 spawnPos = GetDoorPosition();
            guest.anchorPos = spawnPos;
            guest.anchorRot = Quaternion.LookRotation((GetRoomCenter() - spawnPos).normalized);

            // Create visual
            guest.obj = CreateGuestVisual(spawnPos, guest.anchorRot, guest);
            guest.renderer = guest.obj.GetComponentInChildren<Renderer>();

            // Dramatic entrance
            StartCoroutine(DramaticEntrance(guest));

            _guests.Add(guest);
            Debug.Log($"[VirtualGuest] {guest.name} has arrived!");
            return guest;
        }

        /// <summary>Summon a random guest.</summary>
        public Guest SummonRandomGuest()
        {
            var types = System.Enum.GetValues(typeof(GuestType));
            GuestType randomType = (GuestType)types.GetValue(Random.Range(0, types.Length));
            return SummonGuest(randomType);
        }

        /// <summary>Ask a guest to leave.</summary>
        public void DismissGuest(Guest guest)
        {
            if (guest == null || guest.hasLeft) return;
            guest.leaveTime = Time.time;
            guest.state = GuestState.Leaving;
        }

        /// <summary>Dismiss all guests.</summary>
        public void DismissAll()
        {
            foreach (var g in _guests)
            {
                if (!g.hasLeft)
                {
                    g.leaveTime = Time.time;
                    g.state = GuestState.Leaving;
                }
            }
        }

        // ── Dramatic Entrance ──

        private IEnumerator DramaticEntrance(Guest guest)
        {
            // Spotlight
            if (Camera.main != null)
            {
                var lightGo = new GameObject($"Spotlight_{guest.name}");
                lightGo.transform.position = guest.obj.transform.position + Vector3.up * 3f;
                guest.spotlight = lightGo.AddComponent<Light>();
                guest.spotlight.type = LightType.Spot;
                guest.spotlight.color = guest.color;
                guest.spotlight.range = 5f;
                guest.spotlight.intensity = 0f;
                guest.spotlight.spotAngle = 60f;
                guest.spotlight.transform.LookAt(guest.obj.transform);
            }

            // Fade in spotlight
            float t = 0f;
            while (t < 1f)
            {
                t += Time.deltaTime / arrivalFanfareDuration;
                if (guest.spotlight != null) guest.spotlight.intensity = Mathf.Lerp(0f, 3f, t);
                // Scale up guest
                if (guest.obj != null) guest.obj.transform.localScale = Vector3.Lerp(Vector3.zero, Vector3.one, t);
                yield return null;
            }

            // Entrance line
            int idx = (int)guest.type;
            SendGuestLine(guest, GuestDefs[idx].Item3);

            // Set music mood based on guest type
            if (musicPlayer != null)
            {
                switch (guest.type)
                {
                    case GuestType.PartyAnimal: musicPlayer.SetMood("energetic"); break;
                    case GuestType.Storyteller: musicPlayer.SetMood("calm"); break;
                    case GuestType.MysteriousStranger: musicPlayer.SetMood("calm"); break;
                    case GuestType.Rival: musicPlayer.SetMood("energetic"); break;
                    case GuestType.OldFriend: musicPlayer.SetMood("calm"); break;
                    case GuestType.Dramatist: musicPlayer.SetMood("focused"); break;
                    case GuestType.ChaosAgent: musicPlayer.SetMood("energetic"); break;
                }
            }

            // Rival starts a game
            if (guest.type == GuestType.Rival && gameEngine != null)
            {
                yield return new WaitForSeconds(3f);
                gameEngine.StartGame(VRGameEngine.GameMode.TargetPractice);
            }

            // Party Animal triggers party preset
            if (guest.type == GuestType.PartyAnimal && presetManager != null)
            {
                yield return new WaitForSeconds(2f);
                presetManager.ApplyPreset(ScenePresetManager.Preset.Party);
            }

            guest.state = GuestState.MakingScene;
            guest.stateTimer = 0f;
        }

        // ── Guest Behavior ──

        private void UpdateGuest(Guest guest)
        {
            guest.stateTimer += Time.deltaTime;

            switch (guest.state)
            {
                case GuestState.Arriving:
                    // Handled by coroutine
                    break;

                case GuestState.MakingScene:
                    // Periodic scene lines
                    if (guest.stateTimer > 15f + Random.Range(-5f, 10f))
                    {
                        guest.stateTimer = 0f;
                        int idx = (int)guest.type;
                        var lines = GuestDefs[idx].Item4;
                        string line = lines[Random.Range(0, lines.Length)];
                        SendGuestLine(guest, line);

                        // Personality-specific behaviors
                        PerformGuestBehavior(guest);
                    }

                    // Check if it's time to leave
                    if (Time.time >= guest.leaveTime)
                    {
                        guest.state = GuestState.Leaving;
                        guest.stateTimer = 0f;
                        int idx = (int)guest.type;
                        SendGuestLine(guest, GuestDefs[idx].Item5);
                    }
                    break;

                case GuestState.Leaving:
                    // Exit animation
                    if (guest.stateTimer > 3f)
                    {
                        StartCoroutine(ExitAnimation(guest));
                        guest.state = GuestState.Gone;
                    }
                    break;

                case GuestState.Gone:
                    guest.hasLeft = true;
                    break;
            }

            // Idle animation — gentle bobbing
            if (guest.obj != null && guest.state != GuestState.Arriving && guest.state != GuestState.Gone)
            {
                float bob = Mathf.Sin(Time.time * 1.5f + guest.arrivalTime) * 0.02f;
                guest.obj.transform.position = guest.anchorPos + Vector3.up * bob;

                // Face the user
                if (Camera.main != null)
                {
                    Vector3 dir = (Camera.main.transform.position - guest.obj.transform.position).normalized;
                    dir.y = 0;
                    guest.obj.transform.rotation = Quaternion.Slerp(
                        guest.obj.transform.rotation,
                        Quaternion.LookRotation(dir),
                        Time.deltaTime * 1.5f);
                }
            }
        }

        private void PerformGuestBehavior(Guest guest)
        {
            switch (guest.type)
            {
                case GuestType.ChaosAgent:
                    // Spawn confetti particles
                    SpawnConfetti(guest.obj.transform.position);
                    break;

                case GuestType.PartyAnimal:
                    // Dance animation — spin
                    if (guest.obj != null)
                        StartCoroutine(SpinDance(guest.obj.transform, 2f));
                    break;

                case GuestType.Dramatist:
                    // Big gesture — scale pulse
                    if (guest.obj != null)
                        StartCoroutine(GesturePulse(guest.obj.transform, 1.5f));
                    break;

                case GuestType.MysteriousStranger:
                    // Fog particles
                    SpawnFog(guest.obj.transform.position);
                    break;

                case GuestType.Rival:
                    // Challenge stance — lean forward
                    if (guest.obj != null)
                        StartCoroutine(LeanForward(guest.obj.transform, 1f));
                    break;

                case GuestType.Storyteller:
                    // Sit down gesture — lower position
                    guest.anchorPos = new Vector3(guest.anchorPos.x, guest.anchorPos.y - 0.3f, guest.anchorPos.z);
                    break;

                case GuestType.OldFriend:
                    // Warm glow pulse
                    if (guest.spotlight != null)
                        StartCoroutine(GlowPulse(guest.spotlight, 2f));
                    break;
            }
        }

        // ── Guest Visual ──

        private GameObject CreateGuestVisual(Vector3 pos, Quaternion rot, Guest guest)
        {
            var go = new GameObject($"Guest_{guest.name}");
            go.transform.position = pos;
            go.transform.rotation = rot;
            go.transform.localScale = Vector3.zero; // start invisible, scale up during entrance

            // Body — distinct shape per type
            PrimitiveType bodyType = guest.type switch
            {
                GuestType.Dramatist => PrimitiveType.Capsule,      // tall, dramatic
                GuestType.ChaosAgent => PrimitiveType.Cube,        // chaotic, angular
                GuestType.Storyteller => PrimitiveType.Sphere,     // round, soft
                GuestType.PartyAnimal => PrimitiveType.Cylinder,   // dancing form
                GuestType.MysteriousStranger => PrimitiveType.Sphere, // orb-like
                GuestType.Rival => PrimitiveType.Capsule,          // standing tall
                GuestType.OldFriend => PrimitiveType.Sphere,       // warm, round
                _ => PrimitiveType.Sphere,
            };

            var body = GameObject.CreatePrimitive(bodyType);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = guest.type == GuestType.Dramatist || guest.type == GuestType.Rival
                ? new Vector3(0.35f, 0.7f, 0.35f)
                : Vector3.one * 0.4f;

            var rend = body.GetComponent<Renderer>();
            var mat = new Material(Shader.Find("Standard"));
            mat.color = guest.color;
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", guest.color * 0.5f);
            rend.material = mat;
            guest.material = mat;

            // Eyes — two glowing dots
            for (int i = 0; i < 2; i++)
            {
                var eye = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                eye.transform.SetParent(go.transform, false);
                eye.transform.localScale = Vector3.one * 0.06f;
                eye.transform.localPosition = new Vector3(i == 0 ? -0.1f : 0.1f, 0.2f, 0.25f);
                var eyeRend = eye.GetComponent<Renderer>();
                var eyeMat = new Material(Shader.Find("Standard"));
                eyeMat.color = Color.white;
                eyeMat.EnableKeyword("_EMISSION");
                eyeMat.SetColor("_EmissionColor", guest.color * 2f);
                eyeRend.material = eyeMat;
            }

            // Collider for interaction
            var col = go.AddComponent<SphereCollider>();
            col.radius = 0.5f;

            return go;
        }

        // ── Exit Animation ──

        private IEnumerator ExitAnimation(Guest guest)
        {
            if (guest.obj == null) { guest.hasLeft = true; yield break; }

            // Fade out
            float t = 0f;
            Vector3 startScale = guest.obj.transform.localScale;
            Vector3 startPos = guest.obj.transform.position;

            while (t < 2f && guest.obj != null)
            {
                t += Time.deltaTime;
                float p = t / 2f;

                // Shrink
                guest.obj.transform.localScale = Vector3.Lerp(startScale, Vector3.zero, p);
                // Rise slightly
                guest.obj.transform.position = startPos + Vector3.up * p * 0.5f;
                // Spin
                guest.obj.transform.Rotate(Vector3.up, 360f * Time.deltaTime);

                // Fade spotlight
                if (guest.spotlight != null)
                    guest.spotlight.intensity = Mathf.Lerp(3f, 0f, p);

                // Fade material
                if (guest.material != null)
                {
                    Color c = guest.material.color;
                    c.a = 1f - p;
                    guest.material.color = c;
                }

                yield return null;
            }

            // Cleanup
            if (guest.spotlight != null) Destroy(guest.spotlight.gameObject);
            if (guest.aura != null) Destroy(guest.aura.gameObject);
            if (guest.obj != null) Destroy(guest.obj);
            guest.hasLeft = true;

            Debug.Log($"[VirtualGuest] {guest.name} has left.");
        }

        // ── Effects ──

        private void SpawnConfetti(Vector3 pos)
        {
            var go = new GameObject("Confetti");
            go.transform.position = pos + Vector3.up * 0.5f;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = Color.HSVToRGB(Random.value, 1f, 1f);
            main.startSize = 0.03f;
            main.startSpeed = 3f;
            main.maxParticles = 100;
            main.startLifetime = 2f;
            var emission = ps.emission;
            emission.rateOverTime = 50;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = 0.5f;
            Destroy(go, 3f);
        }

        private void SpawnFog(Vector3 pos)
        {
            var go = new GameObject("Fog");
            go.transform.position = pos;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = new Color(0.3f, 0f, 0.5f, 0.3f);
            main.startSize = 0.5f;
            main.startSpeed = 0.3f;
            main.maxParticles = 30;
            main.startLifetime = 3f;
            var emission = ps.emission;
            emission.rateOverTime = 10;
            Destroy(go, 4f);
        }

        // ── Animations ──

        private IEnumerator SpinDance(Transform t, float duration)
        {
            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                t.Rotate(Vector3.up, 360f * Time.deltaTime);
                t.position += Vector3.up * Mathf.Sin(elapsed * 8f) * 0.01f;
                yield return null;
            }
        }

        private IEnumerator GesturePulse(Transform t, float duration)
        {
            Vector3 baseScale = t.localScale;
            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float pulse = 1f + Mathf.Sin(elapsed * 6f) * 0.15f;
                t.localScale = baseScale * pulse;
                yield return null;
            }
            t.localScale = baseScale;
        }

        private IEnumerator LeanForward(Transform t, float duration)
        {
            Quaternion startRot = t.rotation;
            Quaternion leanRot = startRot * Quaternion.Euler(15f, 0, 0);
            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float p = Mathf.Sin(elapsed / duration * Mathf.PI);
                t.rotation = Quaternion.Slerp(startRot, leanRot, p);
                yield return null;
            }
            t.rotation = startRot;
        }

        private IEnumerator GlowPulse(Light light, float duration)
        {
            float baseIntensity = light.intensity;
            float elapsed = 0f;
            while (elapsed < duration && light != null)
            {
                elapsed += Time.deltaTime;
                light.intensity = baseIntensity + Mathf.Sin(elapsed * 3f) * 1f;
                yield return null;
            }
            if (light != null) light.intensity = baseIntensity;
        }

        // ── Communication ──

        private void SendGuestLine(Guest guest, string line)
        {
            Debug.Log($"[VirtualGuest] {guest.name}: {line}");

            if (wsClient != null)
            {
                var payload = new GuestLinePayload
                {
                    type = "guest.line",
                    guestName = guest.name,
                    guestType = guest.type.ToString(),
                    text = line,
                    color = $"#{ColorUtility.ToHtmlStringRGB(guest.color)}",
                };
                string json = JsonUtility.ToJson(payload);
                wsClient.SendRawMessage(json);
            }
        }

        [System.Serializable]
        private class GuestLinePayload
        {
            public string type;
            public string guestName;
            public string guestType;
            public string text;
            public string color;
        }

        // ── Helpers ──

        private Vector3 GetRoomCenter()
        {
            return Camera.main != null
                ? Camera.main.transform.position - Camera.main.transform.forward * 0.5f
                : Vector3.zero;
        }

        private Vector3 GetDoorPosition()
        {
            // Spawn from a room edge — simulating a door
            float angle = Random.Range(0f, 360f);
            Vector3 center = GetRoomCenter();
            Vector3 dir = new Vector3(Mathf.Cos(angle), 0, Mathf.Sin(angle));
            return center + dir * guestSpawnRadius + Vector3.up * 0.5f;
        }

        // ── Public API for Alice ──

        public void AliceSummonGuest(string typeName)
        {
            if (System.Enum.TryParse<GuestType>(typeName, true, out var type))
                SummonGuest(type);
        }

        public void AliceDismissAll() => DismissAll();

        public int ActiveGuestCount => _guests.Count;
    }
}
