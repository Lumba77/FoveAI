using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using FoveAI.IPC;
using FoveAI.Creative;

namespace FoveAI.Experiences
{
    /// <summary>
    /// Virtual Touring — travel to places with Alice as your companion.
    ///
    /// Alice is your travel buddy. She explores alongside you, comments on
    /// what she sees, suggests directions, and shares the experience.
    ///
    /// Destinations are procedurally generated environments:
    ///   • Mountain Peak — alpine vista, wind, snow particles, vast horizon
    ///   • Beach Sunset — ocean waves, warm light, sand, seagulls
    ///   • Forest Path — trees, birdsong, dappled light, walking trail
    ///   • City at Night — neon lights, traffic sounds, rooftop view
    ///   • Desert Dunes — vast emptiness, heat shimmer, stars
    ///   • Northern Lights — aurora, silence, snow, cosmic awe
    ///   • Underwater — coral, fish, bubbles, blue light
    ///   • Space Station — stars, Earth view, zero-G float
    ///   • Japanese Garden — cherry blossoms, koi pond, zen
    ///   • Rainy Cafe — rain on window, warm interior, coffee steam
    ///
    /// Alice's touring behavior:
    ///   • Walks beside you, looks at landmarks
    ///   • Points things out ("look at that", "over here")
    ///   • Shares quiet moments at viewpoints
    ///   • Suggests where to go next
    ///   • Reacts to the environment (cold at mountain, relaxed at beach)
    /// </summary>
    public class VirtualTouring : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private AmbientMusicPlayer musicPlayer;
        [SerializeField] private Transform aliceTransform;
        [SerializeField] private Transform aliceHead;

        [Header("Tour Settings")]
        public float aliceWalkSpeed = 0.5f;
        public float aliceFollowDistance = 1.5f;
        public float landmarkCheckInterval = 8f;
        public float commentChance = 0.4f;

        // ── Destinations ──
        public enum Destination
        {
            MountainPeak,
            BeachSunset,
            ForestPath,
            CityNight,
            DesertDunes,
            NorthernLights,
            Underwater,
            SpaceStation,
            JapaneseGarden,
            RainyCafe,
        }

        public Destination CurrentDestination { get; private set; }
        public bool IsTouring { get; private set; }

        // ── State ──
        private GameObject _environment;
        private readonly List<GameObject> _spawnedObjects = new();
        private readonly List<Light> _spawnedLights = new();
        private ParticleSystem _ambientParticles;
        private float _originalLightIntensity;
        private Color _originalAmbient;
        private Light _mainLight;
        private float _landmarkTimer;
        private Vector3 _aliceAnchor;
        private bool _aliceWalking;

        // ── Destination Definitions ──
        private static readonly (string name, Color skyColor, Color fogColor, float fogDensity,
            Color ambientLight, float mainLightIntensity, string musicMood,
            string[] aliceComments)[] DestDefs =
        {
            // Mountain Peak
            (
                "Mountain Peak", new Color(0.5f, 0.7f, 0.9f, 1f), new Color(0.7f, 0.85f, 0.95f, 1f),
                0.02f, new Color(0.8f, 0.9f, 1f, 1f), 1.2f, "calm",
                new[] { "the valley goes on forever...", "feel that wind?", "we're so high up", "look at those peaks", "...breathe it in" }
            ),
            // Beach Sunset
            (
                "Beach Sunset", new Color(1f, 0.5f, 0.3f, 1f), new Color(1f, 0.6f, 0.4f, 1f),
                0.01f, new Color(1f, 0.7f, 0.4f, 1f), 0.8f, "calm",
                new[] { "listen to the waves...", "the light is incredible", "i could stay here forever", "warm sand, warm light", "...perfect" }
            ),
            // Forest Path
            (
                "Forest Path", new Color(0.3f, 0.5f, 0.3f, 1f), new Color(0.2f, 0.4f, 0.2f, 1f),
                0.05f, new Color(0.3f, 0.5f, 0.3f, 1f), 0.6f, "calm",
                new[] { "smell that? pine...", "the light through the leaves", "i hear birds", "shall we walk deeper?", "this is peaceful" }
            ),
            // City at Night
            (
                "City at Night", new Color(0.05f, 0.05f, 0.12f, 1f), new Color(0.1f, 0.1f, 0.2f, 1f),
                0.03f, new Color(0.2f, 0.15f, 0.3f, 1f), 0.3f, "energetic",
                new[] { "the city never sleeps", "neon everywhere", "listen to the traffic", "which way?", "i love it down here" }
            ),
            // Desert Dunes
            (
                "Desert Dunes", new Color(0.9f, 0.8f, 0.5f, 1f), new Color(0.95f, 0.85f, 0.6f, 1f),
                0.04f, new Color(0.9f, 0.8f, 0.6f, 1f), 1.5f, "calm",
                new[] { "so much nothing...", "the silence is loud", "sand everywhere", "stars will be amazing tonight", "...vast" }
            ),
            // Northern Lights
            (
                "Northern Lights", new Color(0.02f, 0.03f, 0.08f, 1f), new Color(0.05f, 0.1f, 0.15f, 1f),
                0.02f, new Color(0.1f, 0.2f, 0.3f, 1f), 0.2f, "calm",
                new[] { "...look up", "the sky is alive", "i've never seen anything like this", "green and purple dancing", "...this is sacred" }
            ),
            // Underwater
            (
                "Underwater", new Color(0.0f, 0.3f, 0.6f, 1f), new Color(0.0f, 0.4f, 0.7f, 1f),
                0.08f, new Color(0.1f, 0.4f, 0.7f, 1f), 0.5f, "calm",
                new[] { "everything floats here", "look at the fish", "the coral is glowing", "i can hear whales", "...weightless" }
            ),
            // Space Station
            (
                "Space Station", new Color(0.0f, 0.0f, 0.02f, 1f), new Color(0.0f, 0.0f, 0.0f, 1f),
                0.0f, new Color(0.3f, 0.3f, 0.4f, 1f), 0.4f, "focused",
                new[] { "there's Earth", "we're floating", "the stars don't twinkle up here", "no up or down", "...home looks small" }
            ),
            // Japanese Garden
            (
                "Japanese Garden", new Color(0.6f, 0.7f, 0.6f, 1f), new Color(0.5f, 0.65f, 0.55f, 1f),
                0.02f, new Color(0.6f, 0.7f, 0.6f, 1f), 0.7f, "calm",
                new[] { "the cherry blossoms", "koi in the pond", "so carefully arranged", "find the tea house", "...harmony" }
            ),
            // Rainy Cafe
            (
                "Rainy Cafe", new Color(0.3f, 0.3f, 0.35f, 1f), new Color(0.25f, 0.25f, 0.3f, 1f),
                0.03f, new Color(0.4f, 0.35f, 0.3f, 1f), 0.5f, "calm",
                new[] { "rain on the window...", "this coffee is good", "cozy in here", "watch the rain", "...i love days like this" }
            ),
        };

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            if (aliceTransform == null)
            {
                var avatar = GameObject.Find("Alice") ?? GameObject.Find("Avatar");
                if (avatar != null)
                {
                    aliceTransform = avatar.transform;
                    aliceHead = avatar.transform.Find("Head") ?? avatar.transform.Find("Armature/Hips/Spine/Chest/Neck/Head");
                }
            }
            _mainLight = FindAnyObjectByType<Light>();
            if (_mainLight != null) _originalLightIntensity = _mainLight.intensity;
            _originalAmbient = RenderSettings.ambientLight;
        }

        private void Update()
        {
            if (!IsTouring) return;

            // Alice follows the user
            UpdateAliceFollow();

            // Landmark comments
            _landmarkTimer += Time.deltaTime;
            if (_landmarkTimer >= landmarkCheckInterval)
            {
                _landmarkTimer = 0f + Random.Range(-2f, 4f);
                if (Random.value < commentChance)
                {
                    AliceComment();
                }
            }
        }

        // ── Start / Stop Tour ──

        public void StartTour(Destination dest)
        {
            StopTour();
            CurrentDestination = dest;
            IsTouring = true;
            _landmarkTimer = 0f;

            int idx = (int)dest;
            var def = DestDefs[idx];

            // Set environment lighting
            RenderSettings.skybox = null;
            RenderSettings.ambientLight = def.ambientLight;
            if (def.fogDensity > 0)
            {
                RenderSettings.fog = true;
                RenderSettings.fogColor = def.fogColor;
                RenderSettings.fogDensity = def.fogDensity;
            }
            else
            {
                RenderSettings.fog = false;
            }
            if (_mainLight != null) _mainLight.intensity = def.mainLightIntensity;

            // Set camera background
            if (Camera.main != null)
            {
                Camera.main.backgroundColor = def.skyColor;
                Camera.main.clearFlags = CameraClearFlags.SolidColor;
            }

            // Build environment
            BuildEnvironment(dest);

            // Music
            if (musicPlayer != null) musicPlayer.SetMood(def.musicMood);

            // Alice's arrival comment
            StartCoroutine(AliceArrivalComment(def.name));

            Debug.Log($"[VirtualTour] Arrived at {def.name}");
        }

        public void StopTour()
        {
            IsTouring = false;

            // Clear environment
            foreach (var obj in _spawnedObjects) if (obj != null) Destroy(obj);
            _spawnedObjects.Clear();
            foreach (var light in _spawnedLights) if (light != null) Destroy(light.gameObject);
            _spawnedLights.Clear();
            if (_ambientParticles != null) { _ambientParticles.Stop(); Destroy(_ambientParticles.gameObject); _ambientParticles = null; }

            // Restore lighting
            if (_mainLight != null) _mainLight.intensity = _originalLightIntensity;
            RenderSettings.ambientLight = _originalAmbient;
            RenderSettings.fog = false;
            if (Camera.main != null) Camera.main.clearFlags = CameraClearFlags.Skybox;

            CurrentDestination = Destination.MountainPeak;
        }

        // ── Environment Building ──

        private void BuildEnvironment(Destination dest)
        {
            Vector3 center = GetRoomCenter();

            switch (dest)
            {
                case Destination.MountainPeak:
                    BuildMountain(center);
                    break;
                case Destination.BeachSunset:
                    BuildBeach(center);
                    break;
                case Destination.ForestPath:
                    BuildForest(center);
                    break;
                case Destination.CityNight:
                    BuildCityNight(center);
                    break;
                case Destination.DesertDunes:
                    BuildDesert(center);
                    break;
                case Destination.NorthernLights:
                    BuildAurora(center);
                    break;
                case Destination.Underwater:
                    BuildUnderwater(center);
                    break;
                case Destination.SpaceStation:
                    BuildSpace(center);
                    break;
                case Destination.JapaneseGarden:
                    BuildGarden(center);
                    break;
                case Destination.RainyCafe:
                    BuildRainyCafe(center);
                    break;
            }
        }

        private void BuildMountain(Vector3 center)
        {
            // Distant peaks — large triangles
            for (int i = 0; i < 5; i++)
            {
                float angle = (i / 5f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 8f, -1f, Mathf.Sin(angle) * 8f);
                var peak = CreatePeak(pos, Random.Range(3f, 6f), new Color(0.4f, 0.45f, 0.5f));
                _spawnedObjects.Add(peak);
            }
            // Snow particles
            _ambientParticles = SpawnParticles(center + Vector3.up * 3f, 200, new Color(0.9f, 0.95f, 1f, 0.6f), 0.02f, 5f, 0.5f);
            // Wind light
            var wind = SpawnLight(center + Vector3.up * 2f, new Color(0.8f, 0.9f, 1f), 0.5f, 8f);
            _spawnedLights.Add(wind);
        }

        private void BuildBeach(Vector3 center)
        {
            // Ocean plane
            var ocean = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ocean.transform.position = center + Vector3.forward * 5f;
            ocean.transform.localScale = new Vector3(3f, 1f, 3f);
            var oMat = new Material(Shader.Find("Standard"));
            oMat.color = new Color(0.1f, 0.4f, 0.6f, 0.8f);
            ocean.GetComponent<Renderer>().material = oMat;
            _spawnedObjects.Add(ocean);

            // Sand
            var sand = GameObject.CreatePrimitive(PrimitiveType.Plane);
            sand.transform.position = center;
            sand.transform.localScale = new Vector3(2f, 1f, 2f);
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = new Color(0.9f, 0.8f, 0.5f);
            sand.GetComponent<Renderer>().material = sMat;
            _spawnedObjects.Add(sand);

            // Sun — glowing sphere low on horizon
            var sun = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            sun.transform.position = center + new Vector3(0, 0.8f, 10f);
            sun.transform.localScale = Vector3.one * 1.5f;
            var sunMat = new Material(Shader.Find("Standard"));
            sunMat.color = new Color(1f, 0.5f, 0.2f);
            sunMat.EnableKeyword("_EMISSION");
            sunMat.SetColor("_EmissionColor", new Color(1f, 0.4f, 0.1f) * 3f);
            sun.GetComponent<Renderer>().material = sunMat;
            _spawnedObjects.Add(sun);

            var sunLight = SpawnLight(sun.transform.position, new Color(1f, 0.6f, 0.3f), 2f, 15f);
            _spawnedLights.Add(sunLight);
        }

        private void BuildForest(Vector3 center)
        {
            // Trees around the path
            for (int i = 0; i < 20; i++)
            {
                float angle = Random.Range(0f, Mathf.PI * 2f);
                float dist = Random.Range(3f, 8f);
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * dist, 0, Mathf.Sin(angle) * dist);
                var tree = CreateTree(pos, Random.Range(2f, 4f));
                _spawnedObjects.Add(tree);
            }
            // Dappled light
            var canopy = SpawnLight(center + Vector3.up * 4f, new Color(0.3f, 0.5f, 0.2f), 0.8f, 6f);
            _spawnedLights.Add(canopy);
        }

        private void BuildCityNight(Vector3 center)
        {
            // Buildings — tall boxes with emissive windows
            for (int i = 0; i < 15; i++)
            {
                float angle = (i / 15f) * Mathf.PI * 2f;
                float dist = Random.Range(4f, 10f);
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * dist, 0, Mathf.Sin(angle) * dist);
                var building = CreateBuilding(pos, Random.Range(3f, 8f));
                _spawnedObjects.Add(building);
            }
        }

        private void BuildDesert(Vector3 center)
        {
            // Sand dunes — large smooth shapes
            for (int i = 0; i < 6; i++)
            {
                float angle = (i / 6f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 6f, -0.5f, Mathf.Sin(angle) * 6f);
                var dune = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                dune.transform.position = pos;
                dune.transform.localScale = new Vector3(4f, 1f, 4f);
                var dMat = new Material(Shader.Find("Standard"));
                dMat.color = new Color(0.9f, 0.75f, 0.45f);
                dune.GetComponent<Renderer>().material = dMat;
                _spawnedObjects.Add(dune);
            }
            // Heat shimmer particles
            _ambientParticles = SpawnParticles(center + Vector3.up * 0.5f, 50, new Color(1f, 0.9f, 0.7f, 0.1f), 0.1f, 3f, 0.2f);
        }

        private void BuildAurora(Vector3 center)
        {
            // Aurora ribbons — emissive curved planes high up
            for (int i = 0; i < 3; i++)
            {
                var ribbon = GameObject.CreatePrimitive(PrimitiveType.Plane);
                ribbon.transform.position = center + new Vector3(Random.Range(-3f, 3f), 5f + i, 2f);
                ribbon.transform.rotation = Quaternion.Euler(90f, Random.Range(0f, 360f), 0);
                ribbon.transform.localScale = new Vector3(4f, 1f, 0.3f);
                var rMat = new Material(Shader.Find("Standard"));
                Color auroraCol = i == 0 ? new Color(0.1f, 0.9f, 0.3f) : i == 1 ? new Color(0.3f, 0.5f, 0.9f) : new Color(0.6f, 0.1f, 0.8f);
                rMat.color = auroraCol * 0.5f;
                rMat.EnableKeyword("_EMISSION");
                rMat.SetColor("_EmissionColor", auroraCol * 2f);
                ribbon.GetComponent<Renderer>().material = rMat;
                _spawnedObjects.Add(ribbon);
                StartCoroutine(AuroraWave(ribbon.transform));
            }
            // Stars
            _ambientParticles = SpawnParticles(center + Vector3.up * 8f, 300, new Color(1f, 1f, 1f, 0.8f), 0.03f, 10f, 0f);
        }

        private void BuildUnderwater(Vector3 center)
        {
            // Coral formations
            for (int i = 0; i < 8; i++)
            {
                Vector3 pos = center + new Vector3(Random.Range(-3f, 3f), Random.Range(-1f, 1f), Random.Range(-3f, 3f));
                var coral = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                coral.transform.position = pos;
                coral.transform.localScale = new Vector3(0.3f, Random.Range(0.5f, 1.5f), 0.3f);
                var cMat = new Material(Shader.Find("Standard"));
                cMat.color = Color.HSVToRGB(Random.Range(0f, 0.2f) + 0.5f, 0.8f, 0.9f);
                cMat.EnableKeyword("_EMISSION");
                cMat.SetColor("_EmissionColor", cMat.color * 0.5f);
                coral.GetComponent<Renderer>().material = cMat;
                _spawnedObjects.Add(coral);
            }
            // Bubbles
            _ambientParticles = SpawnParticles(center, 100, new Color(0.7f, 0.9f, 1f, 0.3f), 0.05f, 4f, 0.5f);
        }

        private void BuildSpace(Vector3 center)
        {
            // Earth — large blue sphere in the distance
            var earth = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            earth.transform.position = center + new Vector3(0, 2f, 8f);
            earth.transform.localScale = Vector3.one * 2f;
            var eMat = new Material(Shader.Find("Standard"));
            eMat.color = new Color(0.1f, 0.3f, 0.7f);
            eMat.EnableKeyword("_EMISSION");
            eMat.SetColor("_EmissionColor", new Color(0.05f, 0.15f, 0.4f));
            earth.GetComponent<Renderer>().material = eMat;
            _spawnedObjects.Add(earth);

            // Stars
            _ambientParticles = SpawnParticles(center + Vector3.up * 5f, 500, Color.white, 0.02f, 15f, 0f);
        }

        private void BuildGarden(Vector3 center)
        {
            // Cherry blossom trees
            for (int i = 0; i < 6; i++)
            {
                float angle = (i / 6f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 3f, 0, Mathf.Sin(angle) * 3f);
                var tree = CreateCherryBlossom(pos);
                _spawnedObjects.Add(tree);
            }
            // Koi pond
            var pond = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            pond.transform.position = center;
            pond.transform.localScale = new Vector3(1.5f, 0.05f, 1.5f);
            var pMat = new Material(Shader.Find("Standard"));
            pMat.color = new Color(0.1f, 0.2f, 0.3f, 0.8f);
            pond.GetComponent<Renderer>().material = pMat;
            _spawnedObjects.Add(pond);

            // Falling petals
            _ambientParticles = SpawnParticles(center + Vector3.up * 2f, 80, new Color(1f, 0.7f, 0.8f, 0.6f), 0.03f, 3f, 0.3f);
        }

        private void BuildRainyCafe(Vector3 center)
        {
            // Window frame
            var frame = GameObject.CreatePrimitive(PrimitiveType.Cube);
            frame.transform.position = center + Vector3.forward * 2f;
            frame.transform.localScale = new Vector3(3f, 2f, 0.1f);
            var fMat = new Material(Shader.Find("Standard"));
            fMat.color = new Color(0.3f, 0.2f, 0.15f);
            frame.GetComponent<Renderer>().material = fMat;
            _spawnedObjects.Add(frame);

            // Rain particles
            _ambientParticles = SpawnParticles(center + Vector3.forward * 2f + Vector3.up * 3f, 300, new Color(0.6f, 0.7f, 0.8f, 0.4f), 0.02f, 4f, 3f);

            // Warm interior light
            var warm = SpawnLight(center, new Color(1f, 0.8f, 0.5f), 1.5f, 5f);
            _spawnedLights.Add(warm);

            // Coffee cup
            var cup = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            cup.transform.position = center + Vector3.down * 0.3f + Vector3.right * 0.3f;
            cup.transform.localScale = new Vector3(0.08f, 0.1f, 0.08f);
            var cupMat = new Material(Shader.Find("Standard"));
            cupMat.color = Color.white;
            cup.GetComponent<Renderer>().material = cupMat;
            _spawnedObjects.Add(cup);
        }

        // ── Object Creators ──

        private GameObject CreatePeak(Vector3 pos, float height, Color color)
        {
            var go = new GameObject("Peak");
            go.transform.position = pos;
            var body = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(3f, height, 3f);
            var mat = new Material(Shader.Find("Standard"));
            mat.color = color;
            body.GetComponent<Renderer>().material = mat;
            // Snow cap
            var cap = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            cap.transform.SetParent(go.transform, false);
            cap.transform.localScale = new Vector3(1f, height * 0.3f, 1f);
            cap.transform.localPosition = new Vector3(0, height * 0.5f, 0);
            var capMat = new Material(Shader.Find("Standard"));
            capMat.color = Color.white;
            cap.GetComponent<Renderer>().material = capMat;
            return go;
        }

        private GameObject CreateTree(Vector3 pos, float height)
        {
            var go = new GameObject("Tree");
            go.transform.position = pos;
            // Trunk
            var trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.transform.SetParent(go.transform, false);
            trunk.transform.localScale = new Vector3(0.2f, height * 0.4f, 0.2f);
            trunk.transform.localPosition = new Vector3(0, height * 0.2f, 0);
            var tMat = new Material(Shader.Find("Standard"));
            tMat.color = new Color(0.3f, 0.2f, 0.1f);
            trunk.GetComponent<Renderer>().material = tMat;
            // Foliage
            for (int i = 0; i < 3; i++)
            {
                var leaf = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                leaf.transform.SetParent(go.transform, false);
                leaf.transform.localScale = Vector3.one * Random.Range(0.8f, 1.2f);
                leaf.transform.localPosition = new Vector3(Random.Range(-0.3f, 0.3f), height * 0.5f + i * 0.3f, Random.Range(-0.3f, 0.3f));
                var lMat = new Material(Shader.Find("Standard"));
                lMat.color = new Color(0.1f, 0.4f + Random.Range(-0.1f, 0.1f), 0.15f);
                leaf.GetComponent<Renderer>().material = lMat;
            }
            return go;
        }

        private GameObject CreateBuilding(Vector3 pos, float height)
        {
            var go = new GameObject("Building");
            go.transform.position = pos;
            var body = GameObject.CreatePrimitive(PrimitiveType.Cube);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(Random.Range(1f, 2f), height, Random.Range(1f, 2f));
            var bMat = new Material(Shader.Find("Standard"));
            bMat.color = new Color(0.1f, 0.1f, 0.15f);
            body.GetComponent<Renderer>().material = bMat;
            // Window lights
            int windows = Mathf.FloorToInt(height);
            for (int i = 0; i < windows; i++)
            {
                if (Random.value > 0.5f) continue;
                var win = GameObject.CreatePrimitive(PrimitiveType.Cube);
                win.transform.SetParent(go.transform, false);
                win.transform.localScale = new Vector3(0.15f, 0.15f, 0.05f);
                win.transform.localPosition = new Vector3(0.5f, i * 0.8f - height * 0.4f, 0.5f);
                var wMat = new Material(Shader.Find("Standard"));
                wMat.color = Color.HSVToRGB(Random.Range(0.05f, 0.15f), 0.8f, 1f);
                wMat.EnableKeyword("_EMISSION");
                wMat.SetColor("_EmissionColor", wMat.color * 2f);
                win.GetComponent<Renderer>().material = wMat;
            }
            return go;
        }

        private GameObject CreateCherryBlossom(Vector3 pos)
        {
            var go = new GameObject("CherryBlossom");
            go.transform.position = pos;
            var trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.transform.SetParent(go.transform, false);
            trunk.transform.localScale = new Vector3(0.15f, 1f, 0.15f);
            var tMat = new Material(Shader.Find("Standard"));
            tMat.color = new Color(0.25f, 0.15f, 0.1f);
            trunk.GetComponent<Renderer>().material = tMat;
            for (int i = 0; i < 4; i++)
            {
                var blossom = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                blossom.transform.SetParent(go.transform, false);
                blossom.transform.localScale = Vector3.one * Random.Range(0.5f, 0.8f);
                blossom.transform.localPosition = new Vector3(Random.Range(-0.4f, 0.4f), 0.8f + i * 0.2f, Random.Range(-0.4f, 0.4f));
                var bMat = new Material(Shader.Find("Standard"));
                bMat.color = new Color(1f, 0.7f, 0.8f);
                blossom.GetComponent<Renderer>().material = bMat;
            }
            return go;
        }

        // ── Alice Behavior ──

        private void UpdateAliceFollow()
        {
            if (aliceTransform == null || Camera.main == null) return;

            Vector3 userPos = Camera.main.transform.position;
            Vector3 userForward = Camera.main.transform.forward;
            userForward.y = 0;
            userForward.Normalize();

            // Alice walks beside the user, slightly behind
            Vector3 targetPos = userPos - userForward * aliceFollowDistance + Vector3.right * 0.6f;
            targetPos.y = userPos.y;

            float dist = Vector3.Distance(aliceTransform.position, targetPos);
            _aliceWalking = dist > 0.3f;

            if (_aliceWalking)
            {
                aliceTransform.position = Vector3.MoveTowards(
                    aliceTransform.position, targetPos, aliceWalkSpeed * Time.deltaTime);
                Vector3 lookDir = (targetPos - aliceTransform.position).normalized;
                if (lookDir != Vector3.zero)
                    aliceTransform.rotation = Quaternion.Slerp(aliceTransform.rotation,
                        Quaternion.LookRotation(lookDir), Time.deltaTime * 3f);
            }
            else
            {
                // Look at what the user is looking at
                if (aliceHead != null)
                {
                    Vector3 lookAt = userPos + userForward * 3f;
                    Vector3 dir = (lookAt - aliceHead.position).normalized;
                    aliceHead.rotation = Quaternion.Slerp(aliceHead.rotation,
                        Quaternion.LookRotation(dir), Time.deltaTime * 1.5f);
                }
            }
        }

        private void AliceComment()
        {
            int idx = (int)CurrentDestination;
            var comments = DestDefs[idx].Item8;
            string comment = comments[Random.Range(0, comments.Length)];
            SendAliceLine(comment);
        }

        private IEnumerator AliceArrivalComment(string destName)
        {
            yield return new WaitForSeconds(2f);
            SendAliceLine($"we're here. {destName}.");
        }

        private void SendAliceLine(string text)
        {
            Debug.Log($"[VirtualTour] Alice: {text}");
            if (wsClient != null)
            {
                var payload = new TourLinePayload { type = "tour.comment", text = text, destination = CurrentDestination.ToString() };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        [System.Serializable]
        private class TourLinePayload
        {
            public string type;
            public string text;
            public string destination;
        }

        // ── Effects ──

        private IEnumerator AuroraWave(Transform t)
        {
            Vector3 startPos = t.position;
            while (t != null)
            {
                t.position = startPos + new Vector3(Mathf.Sin(Time.time * 0.3f) * 1f, Mathf.Sin(Time.time * 0.2f) * 0.5f, 0);
                yield return null;
            }
        }

        private ParticleSystem SpawnParticles(Vector3 pos, int count, Color color, float size, float range, float speed)
        {
            var go = new GameObject("TourParticles");
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
            _spawnedObjects.Add(go);
            return ps;
        }

        private Light SpawnLight(Vector3 pos, Color color, float intensity, float range)
        {
            var go = new GameObject("TourLight");
            go.transform.position = pos;
            var light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.intensity = intensity;
            light.range = range;
            _spawnedObjects.Add(go);
            return light;
        }

        // ── Helpers ──

        private Vector3 GetRoomCenter()
        {
            return Camera.main != null
                ? Camera.main.transform.position - Camera.main.transform.forward * 0.5f
                : Vector3.zero;
        }

        // ── Public API ──

        public void AliceStartTour(string destName)
        {
            if (System.Enum.TryParse<Destination>(destName, true, out var dest))
                StartTour(dest);
        }

        public string[] GetDestinationNames()
        {
            return System.Enum.GetNames(typeof(Destination));
        }
    }
}
