using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using TMPro;
using FoveAI.Creative;

namespace FoveAI.Games
{
    /// <summary>
    /// Scene Preset Manager — transforms the VR room into different atmospheres.
    ///
    /// Presets:
    ///   1. Romance   — warm candlelight, rose petals, soft music, dim lighting
    ///   2. Movie Night — big screen, dim lights, popcorn, ambient film score
    ///   3. Cozy Home  — fireplace, warm lamp, plants, comfy vibes
    ///   4. Tidy Room  — scans real room, creates clean organized overlay
    ///   5. Party      — colorful lights, confetti, upbeat music
    ///   6. Zen Garden — peaceful, floating particles, calm music
    ///   7. Workspace  — bright, focused, tools arranged
    ///
    /// Each preset spawns virtual objects into the real room (MR style),
    /// changes lighting, and sets the music mood.
    /// </summary>
    public class ScenePresetManager : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private AmbientMusicPlayer musicPlayer;
        [SerializeField] private VRGameEngine gameEngine;
        [SerializeField] private FoveAI.IPC.FoveAIWebSocketClient wsClient;

        [Header("Lighting")]
        [SerializeField] private Light mainLight;
        [Tooltip("Directional/ambient light that we dim for presets.")]
        [Range(0f, 1f)] public float defaultLightIntensity = 1f;

        [Header("Materials")]
        [SerializeField] private Material candleMat;
        [SerializeField] private Material lampMat;
        [SerializeField] private Material screenMat;

        // ── State ──
        public enum Preset { None, Romance, MovieNight, CozyHome, TidyRoom, Party, ZenGarden, Workspace }
        public Preset CurrentPreset { get; private set; } = Preset.None;

        private readonly List<GameObject> _spawnedObjects = new List<GameObject>();
        private readonly List<Light> _spawnedLights = new List<Light>();
        private float _originalLightIntensity;
        private Color _originalAmbient;
        private ParticleSystem _activeParticles;

        // Preset colors
        private static readonly Color RomanceColor = new Color(1f, 0.4f, 0.5f, 1f);
        private static readonly Color MovieColor = new Color(0.1f, 0.1f, 0.15f, 1f);
        private static readonly Color CozyColor = new Color(1f, 0.7f, 0.3f, 1f);
        private static readonly Color PartyColor = new Color(0.8f, 0.2f, 1f, 1f);
        private static readonly Color ZenColor = new Color(0.5f, 0.8f, 0.7f, 1f);
        private static readonly Color WorkColor = new Color(0.9f, 0.95f, 1f, 1f);

        private void Awake()
        {
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            if (gameEngine == null) gameEngine = FindAnyObjectByType<VRGameEngine>();
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();

            if (mainLight == null)
            {
                mainLight = FindAnyObjectByType<Light>();
            }
            if (mainLight != null) _originalLightIntensity = mainLight.intensity;
            _originalAmbient = RenderSettings.ambientLight;
        }

        // ── Preset Application ──

        public void ApplyPreset(Preset preset)
        {
            ClearPreset();
            CurrentPreset = preset;

            switch (preset)
            {
                case Preset.Romance: ApplyRomance(); break;
                case Preset.MovieNight: ApplyMovieNight(); break;
                case Preset.CozyHome: ApplyCozyHome(); break;
                case Preset.TidyRoom: ApplyTidyRoom(); break;
                case Preset.Party: ApplyParty(); break;
                case Preset.ZenGarden: ApplyZenGarden(); break;
                case Preset.Workspace: ApplyWorkspace(); break;
            }

            Debug.Log($"[ScenePreset] Applied: {preset}");
        }

        public void ClearPreset()
        {
            // Remove spawned objects
            foreach (var obj in _spawnedObjects)
            {
                if (obj != null) Destroy(obj);
            }
            _spawnedObjects.Clear();

            // Remove spawned lights
            foreach (var light in _spawnedLights)
            {
                if (light != null) Destroy(light.gameObject);
            }
            _spawnedLights.Clear();

            // Stop particles
            if (_activeParticles != null)
            {
                _activeParticles.Stop();
                Destroy(_activeParticles.gameObject);
                _activeParticles = null;
            }

            // Restore lighting
            if (mainLight != null) mainLight.intensity = _originalLightIntensity;
            RenderSettings.ambientLight = _originalAmbient;

            CurrentPreset = Preset.None;
        }

        // ── Preset: Romance ──

        private void ApplyRomance()
        {
            // Dim lighting, warm tones
            SetLighting(0.2f, RomanceColor * 0.3f);

            // Spawn candles around the room
            Vector3 center = GetRoomCenter();
            for (int i = 0; i < 6; i++)
            {
                float angle = (i / 6f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 1.5f, 0.8f, Mathf.Sin(angle) * 1.5f);
                SpawnCandle(pos);
            }

            // Rose petals on floor (red particles)
            SpawnParticles(center + Vector3.up * 0.1f, 200, new Color(0.9f, 0.1f, 0.2f, 0.8f), 0.02f, 2f, 0.5f);

            // Soft music
            if (musicPlayer != null) musicPlayer.SetMood("calm");

            // Warm point light above center
            SpawnPointLight(center + Vector3.up * 2f, RomanceColor, 2f, 5f);
        }

        // ── Preset: Movie Night ──

        private void ApplyMovieNight()
        {
            // Very dim lighting
            SetLighting(0.05f, MovieColor);

            // Big screen in front of player
            Vector3 center = GetRoomCenter();
            Vector3 forward = Camera.main != null ? Camera.main.transform.forward : Vector3.forward;
            Vector3 screenPos = center + forward * 2f;
            SpawnScreen(screenPos, Quaternion.LookRotation(-forward), 2f, 1.1f);

            // Dim ambient light behind
            SpawnPointLight(center - forward * 1f, new Color(0.1f, 0.1f, 0.2f), 0.5f, 3f);

            // Popcorn bucket (small cylinder)
            Vector3 popcornPos = center + forward * 0.8f + Vector3.right * 0.3f;
            SpawnPopcorn(popcornPos);

            // Focused music
            if (musicPlayer != null) musicPlayer.SetMood("focused");
        }

        // ── Preset: Cozy Home ──

        private void ApplyCozyHome()
        {
            // Warm, medium lighting
            SetLighting(0.4f, CozyColor * 0.4f);

            Vector3 center = GetRoomCenter();

            // Fireplace
            SpawnFireplace(center + Vector3.back * 1.5f + Vector3.up * 0.3f);

            // Warm lamp
            SpawnLamp(center + Vector3.right * 1.2f + Vector3.up * 1.2f, CozyColor);

            // Plants (green spheres on floor)
            for (int i = 0; i < 3; i++)
            {
                Vector3 pos = center + new Vector3(Random.Range(-2f, 2f), 0f, Random.Range(-2f, 2f));
                SpawnPlant(pos);
            }

            // Calm music
            if (musicPlayer != null) musicPlayer.SetMood("calm");
        }

        // ── Preset: Tidy Room ──

        private void ApplyTidyRoom()
        {
            // Bright clean lighting
            SetLighting(0.7f, new Color(0.9f, 0.95f, 1f, 1f) * 0.5f);

            Vector3 center = GetRoomCenter();

            // Create a "tidy overlay" — clean geometric shelves
            SpawnTidyShelves(center + Vector3.left * 1.5f + Vector3.up * 1f);
            SpawnTidyShelves(center + Vector3.right * 1.5f + Vector3.up * 1f);

            // Floating "organization" particles (clean white)
            SpawnParticles(center + Vector3.up * 1.5f, 50, new Color(0.9f, 0.95f, 1f, 0.3f), 0.03f, 3f, 1f);

            // Focused music
            if (musicPlayer != null) musicPlayer.SetMood("focused");
        }

        // ── Preset: Party ──

        private void ApplyParty()
        {
            // Dark with colorful lights
            SetLighting(0.1f, PartyColor * 0.2f);

            Vector3 center = GetRoomCenter();

            // Colorful spinning lights
            for (int i = 0; i < 4; i++)
            {
                float angle = (i / 4f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 2f, 2.5f, Mathf.Sin(angle) * 2f);
                Color color = Color.HSVToRGB(i / 4f, 1f, 1f);
                var light = SpawnPointLight(pos, color, 3f, 6f);
                StartCoroutine(SpinLight(light, color));
            }

            // Confetti particles
            SpawnParticles(center + Vector3.up * 2.5f, 300, Color.white, 0.03f, 5f, 2f, true);

            // Energetic music
            if (musicPlayer != null) musicPlayer.SetMood("energetic");
        }

        // ── Preset: Zen Garden ──

        private void ApplyZenGarden()
        {
            // Soft green-blue lighting
            SetLighting(0.3f, ZenColor * 0.3f);

            Vector3 center = GetRoomCenter();

            // Floating zen particles (slow, calming)
            SpawnParticles(center + Vector3.up * 1.5f, 80, ZenColor * 0.5f, 0.04f, 4f, 0.3f);

            // Soft glowing orbs
            for (int i = 0; i < 3; i++)
            {
                Vector3 pos = center + new Vector3(Random.Range(-1.5f, 1.5f), Random.Range(0.5f, 2f), Random.Range(-1.5f, 1.5f));
                SpawnZenOrb(pos);
            }

            // Calm music
            if (musicPlayer != null) musicPlayer.SetMood("calm");
        }

        // ── Preset: Workspace ──

        private void ApplyWorkspace()
        {
            // Bright, cool lighting
            SetLighting(0.8f, WorkColor * 0.5f);

            Vector3 center = GetRoomCenter();

            // Desk lamp
            SpawnLamp(center + Vector3.up * 1.5f, WorkColor);

            // Focused music
            if (musicPlayer != null) musicPlayer.SetMood("focused");
        }

        // ── Object Spawners ──

        private GameObject SpawnCandle(Vector3 pos)
        {
            var go = new GameObject("Candle");
            go.transform.position = pos;

            // Candle body
            var body = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            body.transform.SetParent(go.transform, false);
            body.transform.localScale = new Vector3(0.05f, 0.15f, 0.05f);
            var bodyRend = body.GetComponent<Renderer>();
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.9f, 0.85f, 0.7f);
            bodyRend.material = mat;

            // Flame
            var flame = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            flame.transform.SetParent(go.transform, false);
            flame.transform.localScale = Vector3.one * 0.04f;
            flame.transform.localPosition = new Vector3(0, 0.12f, 0);
            var flameRend = flame.GetComponent<Renderer>();
            var flameMat = new Material(Shader.Find("Standard"));
            flameMat.color = new Color(1f, 0.6f, 0.1f);
            flameMat.EnableKeyword("_EMISSION");
            flameMat.SetColor("_EmissionColor", new Color(1f, 0.5f, 0.1f) * 3f);
            flameRend.material = flameMat;

            // Candle light
            var light = flame.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = new Color(1f, 0.7f, 0.3f);
            light.range = 1.5f;
            light.intensity = 1.5f;

            // Flicker animation
            StartCoroutine(FlickerLight(light, flame.transform));

            _spawnedObjects.Add(go);
            return go;
        }

        private GameObject SpawnScreen(Vector3 pos, Quaternion rot, float width, float height)
        {
            var go = new GameObject("MovieScreen");
            go.transform.position = pos;
            go.transform.rotation = rot;

            // Screen frame
            var frame = GameObject.CreatePrimitive(PrimitiveType.Cube);
            frame.transform.SetParent(go.transform, false);
            frame.transform.localScale = new Vector3(width + 0.1f, height + 0.1f, 0.05f);
            var frameRend = frame.GetComponent<Renderer>();
            var frameMat = new Material(Shader.Find("Standard"));
            frameMat.color = new Color(0.05f, 0.05f, 0.05f);
            frameRend.material = frameMat;

            // Screen surface (emissive)
            var screen = GameObject.CreatePrimitive(PrimitiveType.Cube);
            screen.transform.SetParent(go.transform, false);
            screen.transform.localScale = new Vector3(width, height, 0.06f);
            screen.transform.localPosition = new Vector3(0, 0, -0.01f);
            var screenRend = screen.GetComponent<Renderer>();
            var screenMat = new Material(Shader.Find("Standard"));
            screenMat.color = new Color(0.1f, 0.1f, 0.15f);
            screenMat.EnableKeyword("_EMISSION");
            screenMat.SetColor("_EmissionColor", new Color(0.05f, 0.05f, 0.1f));
            screenRend.material = screenMat;

            _spawnedObjects.Add(go);
            return go;
        }

        private GameObject SpawnPopcorn(Vector3 pos)
        {
            var go = new GameObject("Popcorn");
            go.transform.position = pos;

            var bucket = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            bucket.transform.SetParent(go.transform, false);
            bucket.transform.localScale = new Vector3(0.12f, 0.15f, 0.12f);
            var rend = bucket.GetComponent<Renderer>();
            var mat = new Material(Shader.Find("Standard"));
            mat.color = new Color(0.9f, 0.2f, 0.1f);
            rend.material = mat;

            // Popcorn on top (white spheres)
            for (int i = 0; i < 8; i++)
            {
                var kernel = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                kernel.transform.SetParent(go.transform, false);
                kernel.transform.localScale = Vector3.one * 0.03f;
                kernel.transform.localPosition = new Vector3(
                    Random.Range(-0.08f, 0.08f), 0.15f, Random.Range(-0.08f, 0.08f));
                var kRend = kernel.GetComponent<Renderer>();
                var kMat = new Material(Shader.Find("Standard"));
                kMat.color = new Color(1f, 0.95f, 0.8f);
                kRend.material = kMat;
            }

            _spawnedObjects.Add(go);
            return go;
        }

        private GameObject SpawnFireplace(Vector3 pos)
        {
            var go = new GameObject("Fireplace");
            go.transform.position = pos;

            // Mantle
            var mantle = GameObject.CreatePrimitive(PrimitiveType.Cube);
            mantle.transform.SetParent(go.transform, false);
            mantle.transform.localScale = new Vector3(0.8f, 0.6f, 0.3f);
            var mRend = mantle.GetComponent<Renderer>();
            var mMat = new Material(Shader.Find("Standard"));
            mMat.color = new Color(0.3f, 0.15f, 0.08f);
            mRend.material = mMat;

            // Fire glow
            var fire = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            fire.transform.SetParent(go.transform, false);
            fire.transform.localScale = new Vector3(0.3f, 0.15f, 0.1f);
            fire.transform.localPosition = new Vector3(0, -0.1f, 0.1f);
            var fRend = fire.GetComponent<Renderer>();
            var fMat = new Material(Shader.Find("Standard"));
            fMat.color = new Color(1f, 0.4f, 0.05f);
            fMat.EnableKeyword("_EMISSION");
            fMat.SetColor("_EmissionColor", new Color(1f, 0.3f, 0.05f) * 3f);
            fRend.material = fMat;

            // Fire light
            var light = fire.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = new Color(1f, 0.5f, 0.2f);
            light.range = 3f;
            light.intensity = 3f;
            StartCoroutine(FlickerLight(light, fire.transform));

            // Fire particles
            SpawnParticles(pos + Vector3.up * 0.2f, 100, new Color(1f, 0.3f, 0.05f, 0.6f), 0.03f, 0.5f, 0.3f);

            _spawnedObjects.Add(go);
            return go;
        }

        private GameObject SpawnLamp(Vector3 pos, Color color)
        {
            var go = new GameObject("Lamp");
            go.transform.position = pos;

            // Lamp shade
            var shade = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            shade.transform.SetParent(go.transform, false);
            shade.transform.localScale = new Vector3(0.15f, 0.12f, 0.15f);
            var sRend = shade.GetComponent<Renderer>();
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = color;
            sMat.EnableKeyword("_EMISSION");
            sMat.SetColor("_EmissionColor", color * 1.5f);
            sRend.material = sMat;

            // Lamp light
            var light = shade.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.range = 4f;
            light.intensity = 2f;

            _spawnedObjects.Add(go);
            _spawnedLights.Add(light);
            return go;
        }

        private GameObject SpawnPlant(Vector3 pos)
        {
            var go = new GameObject("Plant");
            go.transform.position = pos;

            // Pot
            var pot = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            pot.transform.SetParent(go.transform, false);
            pot.transform.localScale = new Vector3(0.12f, 0.1f, 0.12f);
            var pRend = pot.GetComponent<Renderer>();
            var pMat = new Material(Shader.Find("Standard"));
            pMat.color = new Color(0.4f, 0.25f, 0.15f);
            pRend.material = pMat;

            // Foliage
            for (int i = 0; i < 5; i++)
            {
                var leaf = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                leaf.transform.SetParent(go.transform, false);
                leaf.transform.localScale = Vector3.one * Random.Range(0.08f, 0.15f);
                leaf.transform.localPosition = new Vector3(
                    Random.Range(-0.1f, 0.1f), Random.Range(0.1f, 0.3f), Random.Range(-0.1f, 0.1f));
                var lRend = leaf.GetComponent<Renderer>();
                var lMat = new Material(Shader.Find("Standard"));
                lMat.color = new Color(0.1f, 0.5f + Random.Range(-0.1f, 0.1f), 0.15f);
                lRend.material = lMat;
            }

            _spawnedObjects.Add(go);
            return go;
        }

        private GameObject SpawnTidyShelves(Vector3 pos)
        {
            var go = new GameObject("TidyShelf");
            go.transform.position = pos;

            // Shelf board
            var board = GameObject.CreatePrimitive(PrimitiveType.Cube);
            board.transform.SetParent(go.transform, false);
            board.transform.localScale = new Vector3(1f, 0.04f, 0.2f);
            var bRend = board.GetComponent<Renderer>();
            var bMat = new Material(Shader.Find("Standard"));
            bMat.color = new Color(0.6f, 0.55f, 0.5f);
            bRend.material = bMat;

            // Neatly arranged items
            for (int i = 0; i < 5; i++)
            {
                var item = GameObject.CreatePrimitive(i % 2 == 0 ? PrimitiveType.Cube : PrimitiveType.Cylinder);
                item.transform.SetParent(go.transform, false);
                item.transform.localScale = new Vector3(0.1f, 0.15f, 0.1f);
                item.transform.localPosition = new Vector3(-0.4f + i * 0.2f, 0.1f, 0);
                var iRend = item.GetComponent<Renderer>();
                var iMat = new Material(Shader.Find("Standard"));
                iMat.color = new Color(0.7f, 0.7f, 0.75f);
                iRend.material = iMat;
            }

            _spawnedObjects.Add(go);
            return go;
        }

        private GameObject SpawnZenOrb(Vector3 pos)
        {
            var go = new GameObject("ZenOrb");
            go.transform.position = pos;

            var orb = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            orb.transform.SetParent(go.transform, false);
            orb.transform.localScale = Vector3.one * 0.15f;
            var rend = orb.GetComponent<Renderer>();
            var mat = new Material(Shader.Find("Standard"));
            mat.color = ZenColor;
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", ZenColor * 0.5f);
            rend.material = mat;

            // Gentle floating animation
            StartCoroutine(FloatOrb(go.transform, Random.Range(0.5f, 1.5f)));

            _spawnedObjects.Add(go);
            return go;
        }

        // ── Particle System ──

        private ParticleSystem SpawnParticles(Vector3 pos, int count, Color color, float size, float range, float speed, bool colorful = false)
        {
            var go = new GameObject("Particles");
            go.transform.position = pos;
            var ps = go.AddComponent<ParticleSystem>();

            var main = ps.main;
            main.startColor = color;
            main.startSize = size;
            main.startSpeed = speed;
            main.maxParticles = count;
            main.loop = true;
            main.duration = 5f;
            main.startLifetime = range;

            var emission = ps.emission;
            emission.rateOverTime = count / 3f;

            var shape = ps.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = range;

            if (colorful)
            {
                var colorOverLifetime = ps.colorOverLifetime;
                colorOverLifetime.enabled = true;
                var grad = new Gradient();
                grad.SetKeys(
                    new[] { new GradientColorKey(Color.red, 0f), new GradientColorKey(Color.yellow, 0.3f), new GradientColorKey(Color.green, 0.6f), new GradientColorKey(Color.blue, 1f) },
                    new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0f, 1f) }
                );
                colorOverLifetime.color = grad;
            }

            _spawnedObjects.Add(go);
            _activeParticles = ps;
            return ps;
        }

        // ── Lighting ──

        private void SetLighting(float intensity, Color ambient)
        {
            if (mainLight != null) mainLight.intensity = _originalLightIntensity * intensity;
            RenderSettings.ambientLight = ambient;
        }

        private Light SpawnPointLight(Vector3 pos, Color color, float intensity, float range)
        {
            var go = new GameObject("PresetLight");
            go.transform.position = pos;
            var light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.intensity = intensity;
            light.range = range;
            _spawnedObjects.Add(go);
            _spawnedLights.Add(light);
            return light;
        }

        // ── Animations ──

        private IEnumerator FlickerLight(Light light, Transform flame)
        {
            float baseIntensity = light.intensity;
            while (light != null && light.gameObject != null)
            {
                light.intensity = baseIntensity + Random.Range(-0.3f, 0.4f) * baseIntensity;
                if (flame != null)
                    flame.localScale = Vector3.one * (1f + Random.Range(-0.1f, 0.15f));
                yield return new WaitForSeconds(Random.Range(0.05f, 0.15f));
            }
        }

        private IEnumerator SpinLight(Light light, Color baseColor)
        {
            while (light != null)
            {
                float h, s, v;
                Color.RGBToHSV(baseColor, out h, out s, out v);
                h = (h + Time.deltaTime * 0.2f) % 1f;
                light.color = Color.HSVToRGB(h, s, v);
                yield return null;
            }
        }

        private IEnumerator FloatOrb(Transform orb, float amplitude)
        {
            Vector3 startPos = orb.position;
            float offset = Random.Range(0f, Mathf.PI * 2f);
            while (orb != null)
            {
                orb.position = startPos + Vector3.up * Mathf.Sin(Time.time + offset) * amplitude * 0.2f;
                orb.Rotate(Vector3.up, 30f * Time.deltaTime);
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

        // ── Alice Integration ──

        /// <summary>Alice can trigger a preset via WebSocket.</summary>
        public void AliceApplyPreset(string presetName)
        {
            if (System.Enum.TryParse<Preset>(presetName, true, out var preset))
            {
                ApplyPreset(preset);
            }
        }
    }
}
