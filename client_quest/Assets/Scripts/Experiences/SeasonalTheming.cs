using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;
using FoveAI.Creative;

namespace FoveAI.Experiences
{
    /// <summary>
    /// Seasonal Theming — the VR environment changes with the real-world seasons.
    ///
    /// Automatically detects the current season and transforms the room:
    ///   • Winter   — snow particles, cool blue lighting, frost on surfaces,
    ///                 bare trees, fireplace warmth, breath mist
    ///   • Spring   — cherry blossoms, bright green buds, birdsong, warm light,
    ///                 rain showers, growing things
    ///   • Summer   — golden light, warm colors, sun rays, insects, lush green,
    ///                 heat shimmer, long shadows
    ///   • Autumn   — falling leaves, orange/red/gold palette, misty mornings,
    ///                 cozy amber light, harvest objects, wind
    ///
    /// Holidays overlay on top of seasons:
    ///   • Christmas   — tree, lights, gifts, bells
    ///   • Halloween   — pumpkins, fog, orange/purple, cobwebs
    ///   • New Year    — fireworks, confetti, countdown
    ///   • Valentine's — hearts, pink/red, petals
    ///   • Easter      — eggs, pastels, spring flowers
    ///   • Thanksgiving — warm harvest, autumn leaves, gratitude
    ///
    /// Alice acknowledges the season in her behavior and comments.
    /// Seasons can also be manually overridden ("make it winter").
    /// </summary>
    public class SeasonalTheming : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private AmbientMusicPlayer musicPlayer;
        [SerializeField] private Transform aliceTransform;

        [Header("Settings")]
        public bool autoDetectSeason = false;
        public bool autoDetectHoliday = false;
        public float seasonalCommentInterval = 300f;  // every 5 min
        public float particleDensity = 1f;

        // ── Seasons ──
        public enum Season
        {
            Spring,
            Summer,
            Autumn,
            Winter,
        }

        // ── Holidays ──
        public enum Holiday
        {
            None,
            Christmas,
            Halloween,
            NewYear,
            Valentines,
            Easter,
            Thanksgiving,
            Birthday,
        }

        [Header("Birthday")]
        public int birthdayMonth = 2;   // February
        public int birthdayDay = 17;
        public bool birthdayAwarenessEnabled = true;
        public float birthdayCommentInterval = 3600f;  // check every hour
        public int birthdayAdvanceDays = 7;  // start mentioning it a week before

        public Season CurrentSeason { get; private set; }
        public Holiday CurrentHoliday { get; private set; }
        public bool IsThemed { get; private set; }
        public bool IsBirthdayToday { get; private set; }
        public bool IsBirthdayWeek { get; private set; }
        public int DaysUntilBirthday { get; private set; }

        // ── State ──
        private readonly List<GameObject> _themedObjects = new();
        private readonly List<Light> _themedLights = new();
        private ParticleSystem _seasonalParticles;
        private Color _originalAmbient;
        private float _originalLightIntensity;
        private Light _mainLight;
        private float _commentTimer;
        private Season _lastCommentSeason;
        private float _birthdayTimer;
        private bool _birthdayMentionedToday;
        private bool _birthdayCelebrated;

        // ── Season Definitions ──
        private static readonly (string name, Color ambient, Color fog, float fogDensity,
            float lightIntensity, Color lightColor, string musicMood,
            string[] aliceLines)[] SeasonDefs =
        {
            // Spring
            (
                "Spring", new Color(0.7f, 0.85f, 0.6f, 1f), new Color(0.6f, 0.8f, 0.5f, 1f),
                0.01f, 1.0f, new Color(1f, 0.95f, 0.8f, 1f), "calm",
                new[] { "spring is here... everything is growing", "i love the new buds", "the air smells like rain and flowers", "birds are back", "everything feels alive again" }
            ),
            // Summer
            (
                "Summer", new Color(1f, 0.9f, 0.6f, 1f), new Color(0.9f, 0.85f, 0.5f, 1f),
                0.005f, 1.4f, new Color(1f, 0.85f, 0.5f, 1f), "energetic",
                new[] { "the light is so golden", "perfect summer day", "i can feel the warmth", "long shadows, lazy afternoon", "everything is lush and green" }
            ),
            // Autumn
            (
                "Autumn", new Color(0.8f, 0.5f, 0.25f, 1f), new Color(0.7f, 0.4f, 0.2f, 1f),
                0.02f, 0.8f, new Color(1f, 0.6f, 0.3f, 1f), "calm",
                new[] { "the leaves are turning", "autumn light is the best light", "i can smell the earth", "everything is gold and red", "the wind has a chill now" }
            ),
            // Winter
            (
                "Winter", new Color(0.6f, 0.7f, 0.85f, 1f), new Color(0.5f, 0.6f, 0.75f, 1f),
                0.03f, 0.6f, new Color(0.8f, 0.9f, 1f, 1f), "calm",
                new[] { "it's cold... stay close", "snow makes everything quiet", "i love the blue winter light", "breath mist... we're alive", "the world is monochrome" }
            ),
        };

        // ── Holiday Definitions ──
        private static readonly (string name, Color primary, Color secondary,
            string[] aliceLines, System.Action<SeasonalTheming> decorate)[] HolidayDefs =
        {
            // None
            ("None", Color.white, Color.white, new string[0], null),
            // Christmas
            (
                "Christmas", new Color(0.1f, 0.6f, 0.2f), new Color(0.8f, 0.1f, 0.1f),
                new[] { "merry christmas...", "the tree is beautiful", "i feel warm inside", "lights in the dark... i love it", "best time of year" },
                self => self.DecorateChristmas()
            ),
            // Halloween
            (
                "Halloween", new Color(0.9f, 0.5f, 0f), new Color(0.5f, 0f, 0.6f),
                new[] { "happy halloween...", "the fog is creeping in", "i see pumpkins... spooky", "something's watching us", "i like the dark tonight" },
                self => self.DecorateHalloween()
            ),
            // New Year
            (
                "New Year", new Color(0.8f, 0.8f, 0.9f), new Color(1f, 0.8f, 0.2f),
                new[] { "happy new year...", "new beginnings", "the countdown... i'm excited", "what will this year bring?", "cheers to us" },
                self => self.DecorateNewYear()
            ),
            // Valentine's
            (
                "Valentine's", new Color(1f, 0.3f, 0.5f), new Color(0.9f, 0.6f, 0.7f),
                new[] { "happy valentine's...", "i love this day", "hearts everywhere... fitting", "you're my favorite person", "love is in the air" },
                self => self.DecorateValentines()
            ),
            // Easter
            (
                "Easter", new Color(0.8f, 0.9f, 1f), new Color(1f, 0.9f, 0.7f),
                new[] { "happy easter...", "pastels everywhere", "i found an egg!", "spring and renewal", "the colors are so soft" },
                self => self.DecorateEaster()
            ),
            // Thanksgiving
            (
                "Thanksgiving", new Color(0.7f, 0.4f, 0.15f), new Color(0.9f, 0.6f, 0.2f),
                new[] { "happy thanksgiving...", "i'm grateful for this", "warmth and gratitude", "the harvest table looks beautiful", "what are you thankful for?" },
                self => self.DecorateThanksgiving()
            ),
            // Birthday — the user's special day
            (
                "Birthday", new Color(1f, 0.8f, 0.9f), new Color(0.9f, 0.7f, 1f),
                new[] { "happy birthday...", "i'm so glad you were born", "this is your day. our day", "i made something for you... i hope you like it", "another year of you. that's worth celebrating" },
                self => self.DecorateBirthday()
            ),
        };

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            _mainLight = FindAnyObjectByType<Light>();
            if (_mainLight != null) _originalLightIntensity = _mainLight.intensity;
            _originalAmbient = RenderSettings.ambientLight;
        }

        private void Start()
        {
            if (autoDetectSeason || autoDetectHoliday)
            {
                DetectSeasonAndHoliday();
                ApplyTheme();
            }
        }

        // ── Detection ──

        private void DetectSeasonAndHoliday()
        {
            var now = System.DateTime.Now;
            int month = now.Month;
            int day = now.Day;

            // Northern hemisphere seasons
            CurrentSeason = month switch
            {
                3 or 4 or 5 => Season.Spring,
                6 or 7 or 8 => Season.Summer,
                9 or 10 or 11 => Season.Autumn,
                _ => Season.Winter,
            };

            // Holiday detection
            CurrentHoliday = Holiday.None;
            if (autoDetectHoliday)
            {
                if (month == 12 && day >= 20) CurrentHoliday = Holiday.Christmas;
                else if (month == 12 && day >= 31) CurrentHoliday = Holiday.NewYear;
                else if (month == 1 && day <= 3) CurrentHoliday = Holiday.NewYear;
                else if (month == 10 && day >= 25) CurrentHoliday = Holiday.Halloween;
                else if (month == 2 && day >= 13 && day <= 15) CurrentHoliday = Holiday.Valentines;
                else if (month == 3 && day >= 25 && day <= 31) CurrentHoliday = Holiday.Easter;
                else if (month == 11 && day >= 20 && day <= 28) CurrentHoliday = Holiday.Thanksgiving;
                // Birthday takes priority over everything
                if (birthdayAwarenessEnabled && month == birthdayMonth && day == birthdayDay)
                    CurrentHoliday = Holiday.Birthday;
            }

            // Birthday awareness — calculate days until and flags
            UpdateBirthdayAwareness(month, day);

            Debug.Log($"[Seasonal] Detected: {CurrentSeason}, Holiday: {CurrentHoliday}");
        }

        // ── Birthday Awareness ──

        private void UpdateBirthdayAwareness(int currentMonth, int currentDay)
        {
            var now = System.DateTime.Now;
            var birthday = new System.DateTime(now.Year, birthdayMonth, birthdayDay);
            if (birthday < now) birthday = birthday.AddYears(1);  // next occurrence

            DaysUntilBirthday = (int)(birthday - now).TotalDays;
            IsBirthdayToday = currentMonth == birthdayMonth && currentDay == birthdayDay;
            IsBirthdayWeek = DaysUntilBirthday <= birthdayAdvanceDays && DaysUntilBirthday >= 0;

            Debug.Log($"[Seasonal] Birthday awareness: daysUntil={DaysUntilBirthday}, " +
                      $"isToday={IsBirthdayToday}, isWeek={IsBirthdayWeek}");
        }

        private void Update()
        {
            if (!IsThemed) return;

            _commentTimer += Time.deltaTime;
            if (_commentTimer >= seasonalCommentInterval)
            {
                _commentTimer = 0f + Random.Range(-60f, 120f);
                if (CurrentSeason != _lastCommentSeason || Random.value < 0.3f)
                {
                    AliceSeasonalComment();
                    _lastCommentSeason = CurrentSeason;
                }
            }

            // Birthday awareness — Alice mentions the approaching birthday
            if (birthdayAwarenessEnabled && !_birthdayMentionedToday)
            {
                _birthdayTimer += Time.deltaTime;
                if (_birthdayTimer >= birthdayCommentInterval)
                {
                    _birthdayTimer = 0f;
                    CheckBirthdayMention();
                }
            }
        }

        private void CheckBirthdayMention()
        {
            if (IsBirthdayToday && !_birthdayCelebrated)
            {
                _birthdayCelebrated = true;
                _birthdayMentionedToday = true;
                AliceSay("happy birthday. i've been waiting for this day.");
                AliceSay("i'm so glad you were born. i'm so glad we're here, together, on this day.");
                // The Director should trigger a birthday celebration
                NotifyDirectorBirthday();
            }
            else if (IsBirthdayWeek && DaysUntilBirthday > 0)
            {
                _birthdayMentionedToday = true;
                string mention = DaysUntilBirthday switch
                {
                    1 => "tomorrow's your birthday. i can barely wait.",
                    2 => "two days until your birthday. i'm already excited.",
                    3 => "three days... your birthday is so close.",
                    4 => "four days until your birthday. i've been thinking about it.",
                    5 => "five more days. your birthday is coming.",
                    6 => "six days until your birthday. i marked the calendar.",
                    7 => "a week until your birthday. i wanted to be the first to mention it.",
                    _ => $"only {DaysUntilBirthday} days until your birthday. i'm counting.",
                };
                AliceSay(mention);
            }
        }

        private void NotifyDirectorBirthday()
        {
            if (wsClient != null)
            {
                var payload = new SeasonalPayload
                {
                    type = "seasonal.birthday",
                    text = "birthday today",
                    season = CurrentSeason.ToString(),
                    holiday = "Birthday",
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        private void DecorateBirthday()
        {
            Vector3 center = GetRoomCenter();

            // Balloons — lots of them
            for (int i = 0; i < 15; i++)
            {
                var balloon = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                balloon.transform.position = center + new Vector3(
                    Random.Range(-2.5f, 2.5f), Random.Range(1.5f, 2.8f), Random.Range(-2.5f, 2.5f));
                balloon.transform.localScale = new Vector3(0.15f, 0.2f, 0.15f);
                var mat = new Material(Shader.Find("Standard"));
                mat.color = Color.HSVToRGB(Random.value, 0.7f, 0.95f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", mat.color * 0.5f);
                balloon.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(balloon);
                StartCoroutine(FloatHeart(balloon.transform));  // gentle float
            }

            // String lights
            var light = SpawnLight(center + Vector3.up * 2f, new Color(1f, 0.8f, 0.9f), 1.5f, 8f);
            _themedLights.Add(light);

            // Confetti particles
            _seasonalParticles = SpawnParticles(center + Vector3.up * 2f, 150,
                Color.HSVToRGB(Random.value, 1f, 1f), 0.04f, 4f, 0.5f);

            // A single candle — intimate, personal
            var candle = SpawnLight(center + new Vector3(0, 0.6f, 0.5f),
                new Color(1f, 0.7f, 0.3f), 1f, 2f);
            _themedLights.Add(candle);
            StartCoroutine(FireFlicker(candle));

            // A small gift box on the table
            var gift = GameObject.CreatePrimitive(PrimitiveType.Cube);
            gift.transform.position = center + new Vector3(0, 0.5f, 0.5f);
            gift.transform.localScale = new Vector3(0.2f, 0.2f, 0.2f);
            var gMat = new Material(Shader.Find("Standard"));
            gMat.color = new Color(0.8f, 0.2f, 0.4f);
            gMat.EnableKeyword("_EMISSION");
            gMat.SetColor("_EmissionColor", new Color(0.4f, 0.1f, 0.2f) * 0.5f);
            gift.GetComponent<Renderer>().material = gMat;
            _themedObjects.Add(gift);

            // Ribbon on the gift
            var ribbonV = GameObject.CreatePrimitive(PrimitiveType.Cube);
            ribbonV.transform.SetParent(gift.transform, false);
            ribbonV.transform.localScale = new Vector3(0.22f, 0.02f, 0.02f);
            var rMat = new Material(Shader.Find("Standard"));
            rMat.color = new Color(0.9f, 0.8f, 0.2f);
            rMat.EnableKeyword("_EMISSION");
            rMat.SetColor("_EmissionColor", new Color(0.9f, 0.8f, 0.2f) * 0.5f);
            ribbonV.GetComponent<Renderer>().material = rMat;

            var ribbonH = GameObject.CreatePrimitive(PrimitiveType.Cube);
            ribbonH.transform.SetParent(gift.transform, false);
            ribbonH.transform.localScale = new Vector3(0.02f, 0.22f, 0.02f);
            ribbonH.GetComponent<Renderer>().material = rMat;
        }

        // ── Apply Theme ──

        public void ApplyTheme()
        {
            ClearTheme();
            IsThemed = true;

            int sIdx = (int)CurrentSeason;
            var sDef = SeasonDefs[sIdx];

            // Lighting
            RenderSettings.ambientLight = sDef.ambient;
            if (sDef.fogDensity > 0)
            {
                RenderSettings.fog = true;
                RenderSettings.fogColor = sDef.fog;
                RenderSettings.fogDensity = sDef.fogDensity;
            }
            if (_mainLight != null)
            {
                _mainLight.intensity = sDef.lightIntensity;
                _mainLight.color = sDef.lightColor;
            }

            // Seasonal particles
            switch (CurrentSeason)
            {
                case Season.Spring: CreateSpringParticles(); break;
                case Season.Summer: CreateSummerParticles(); break;
                case Season.Autumn: CreateAutumnParticles(); break;
                case Season.Winter: CreateWinterParticles(); break;
            }

            // Seasonal objects
            switch (CurrentSeason)
            {
                case Season.Spring: DecorateSpring(); break;
                case Season.Summer: DecorateSummer(); break;
                case Season.Autumn: DecorateAutumn(); break;
                case Season.Winter: DecorateWinter(); break;
            }

            // Music
            if (musicPlayer != null) musicPlayer.SetMood(sDef.musicMood);

            // Holiday overlay
            if (CurrentHoliday != Holiday.None)
            {
                int hIdx = (int)CurrentHoliday;
                var hDef = HolidayDefs[hIdx];
                hDef.decorate?.Invoke(this);
            }

            // Alice's opening comment
            StartCoroutine(AliceSeasonalOpening(sDef.name, CurrentHoliday != Holiday.None ? HolidayDefs[(int)CurrentHoliday].name : null));

            Debug.Log($"[Seasonal] Applied: {sDef.name} + {CurrentHoliday}");
        }

        public void ClearTheme()
        {
            IsThemed = false;

            foreach (var obj in _themedObjects) if (obj != null) Destroy(obj);
            _themedObjects.Clear();
            foreach (var light in _themedLights) if (light != null) Destroy(light.gameObject);
            _themedLights.Clear();
            if (_seasonalParticles != null) { _seasonalParticles.Stop(); Destroy(_seasonalParticles.gameObject); _seasonalParticles = null; }

            RenderSettings.ambientLight = _originalAmbient;
            RenderSettings.fog = false;
            if (_mainLight != null) _mainLight.intensity = _originalLightIntensity;
        }

        // ── Seasonal Decorations ──

        private void DecorateSpring()
        {
            Vector3 center = GetRoomCenter();
            // Cherry blossom trees
            for (int i = 0; i < 3; i++)
            {
                float angle = (i / 3f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 4f, 0, Mathf.Sin(angle) * 4f);
                _themedObjects.Add(CreateBlossomTree(pos));
            }
            // Bird sounds would go here (audio source)
        }

        private void DecorateSummer()
        {
            Vector3 center = GetRoomCenter();
            // Sun rays — warm directional light
            var sun = new GameObject("SummerSun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.9f, 0.6f);
            sun.intensity = 0.5f;
            sun.transform.rotation = Quaternion.Euler(45, 30, 0);
            _themedLights.Add(sun);
            // Lush green ground patches
            for (int i = 0; i < 5; i++)
            {
                var patch = GameObject.CreatePrimitive(PrimitiveType.Plane);
                patch.transform.position = center + new Vector3(Random.Range(-3f, 3f), -0.01f, Random.Range(-3f, 3f));
                patch.transform.localScale = Vector3.one * 0.5f;
                var mat = new Material(Shader.Find("Standard"));
                mat.color = new Color(0.2f, 0.6f, 0.15f);
                patch.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(patch);
            }
        }

        private void DecorateAutumn()
        {
            Vector3 center = GetRoomCenter();
            // Autumn trees with colored leaves
            for (int i = 0; i < 4; i++)
            {
                float angle = (i / 4f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 3.5f, 0, Mathf.Sin(angle) * 3.5f);
                _themedObjects.Add(CreateAutumnTree(pos));
            }
            // Fallen leaves on ground
            for (int i = 0; i < 15; i++)
            {
                var leaf = GameObject.CreatePrimitive(PrimitiveType.Quad);
                leaf.transform.position = center + new Vector3(Random.Range(-3f, 3f), 0.01f, Random.Range(-3f, 3f));
                leaf.transform.rotation = Quaternion.Euler(90, Random.Range(0, 360), 0);
                leaf.transform.localScale = Vector3.one * 0.1f;
                var mat = new Material(Shader.Find("Standard"));
                mat.color = Color.HSVToRGB(Random.Range(0.02f, 0.12f), 0.8f, 0.7f);
                leaf.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(leaf);
            }
        }

        private void DecorateWinter()
        {
            Vector3 center = GetRoomCenter();
            // Bare trees
            for (int i = 0; i < 3; i++)
            {
                float angle = (i / 3f) * Mathf.PI * 2f;
                Vector3 pos = center + new Vector3(Mathf.Cos(angle) * 4f, 0, Mathf.Sin(angle) * 4f);
                _themedObjects.Add(CreateBareTree(pos));
            }
            // Snow on ground
            var snow = GameObject.CreatePrimitive(PrimitiveType.Plane);
            snow.transform.position = center + Vector3.down * 0.01f;
            snow.transform.localScale = new Vector3(3f, 1f, 3f);
            var sMat = new Material(Shader.Find("Standard"));
            sMat.color = new Color(0.9f, 0.92f, 0.95f);
            snow.GetComponent<Renderer>().material = sMat;
            _themedObjects.Add(snow);
            // Fireplace warmth
            var fire = SpawnLight(center + new Vector3(-2f, 0.5f, -1f), new Color(1f, 0.5f, 0.2f), 2f, 4f);
            _themedLights.Add(fire);
            StartCoroutine(FireFlicker(fire));
        }

        // ── Holiday Decorations ──

        private void DecorateChristmas()
        {
            Vector3 center = GetRoomCenter();
            // Christmas tree
            var tree = new GameObject("ChristmasTree");
            tree.transform.position = center + new Vector3(0, 0, -2f);
            for (int i = 0; i < 4; i++)
            {
                var cone = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                cone.transform.SetParent(tree.transform, false);
                cone.transform.localPosition = new Vector3(0, i * 0.3f, 0);
                cone.transform.localScale = new Vector3(0.8f - i * 0.15f, 0.4f, 0.8f - i * 0.15f);
                var mat = new Material(Shader.Find("Standard"));
                mat.color = new Color(0.05f, 0.3f, 0.1f);
                cone.GetComponent<Renderer>().material = mat;
            }
            // Lights on tree
            for (int i = 0; i < 20; i++)
            {
                var light = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                light.transform.SetParent(tree.transform, false);
                light.transform.localPosition = new Vector3(
                    Random.Range(-0.5f, 0.5f), Random.Range(0.1f, 1.3f), Random.Range(-0.5f, 0.5f));
                light.transform.localScale = Vector3.one * 0.04f;
                var mat = new Material(Shader.Find("Standard"));
                Color c = Color.HSVToRGB(Random.Range(0f, 1f), 1f, 1f);
                mat.color = c;
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", c * 3f);
                light.GetComponent<Renderer>().material = mat;
            }
            _themedObjects.Add(tree);

            // String lights around the room
            var stringLight = SpawnLight(center + Vector3.up * 2f, new Color(1f, 0.9f, 0.7f), 1f, 8f);
            _themedLights.Add(stringLight);
        }

        private void DecorateHalloween()
        {
            Vector3 center = GetRoomCenter();
            // Pumpkins
            for (int i = 0; i < 4; i++)
            {
                var pumpkin = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                pumpkin.transform.position = center + new Vector3(
                    Random.Range(-2f, 2f), 0.15f, Random.Range(-2f, 2f));
                pumpkin.transform.localScale = new Vector3(0.3f, 0.25f, 0.3f);
                var mat = new Material(Shader.Find("Standard"));
                mat.color = new Color(0.9f, 0.4f, 0.05f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", new Color(0.5f, 0.2f, 0f) * 2f);
                pumpkin.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(pumpkin);
            }
            // Fog
            _seasonalParticles = SpawnParticles(center, 100, new Color(0.2f, 0.1f, 0.3f, 0.3f), 0.5f, 5f, 0.2f);
            // Eerie purple light
            var eerie = SpawnLight(center + Vector3.up * 2f, new Color(0.5f, 0f, 0.7f), 0.5f, 6f);
            _themedLights.Add(eerie);
        }

        private void DecorateNewYear()
        {
            Vector3 center = GetRoomCenter();
            // Fireworks particles
            _seasonalParticles = SpawnParticles(center + Vector3.up * 3f, 200, Color.white, 0.05f, 6f, 5f);
            // Gold and silver streamers
            for (int i = 0; i < 10; i++)
            {
                var streamer = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                streamer.transform.position = center + new Vector3(
                    Random.Range(-3f, 3f), Random.Range(1f, 3f), Random.Range(-3f, 3f));
                streamer.transform.localScale = new Vector3(0.02f, Random.Range(0.3f, 0.8f), 0.02f);
                var mat = new Material(Shader.Find("Standard"));
                mat.color = i % 2 == 0 ? new Color(1f, 0.8f, 0.2f) : new Color(0.8f, 0.8f, 0.9f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", mat.color * 2f);
                streamer.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(streamer);
            }
        }

        private void DecorateValentines()
        {
            Vector3 center = GetRoomCenter();
            // Floating hearts
            for (int i = 0; i < 12; i++)
            {
                var heart = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                heart.transform.position = center + new Vector3(
                    Random.Range(-2f, 2f), Random.Range(1f, 2.5f), Random.Range(-2f, 2f));
                heart.transform.localScale = Vector3.one * 0.08f;
                var mat = new Material(Shader.Find("Standard"));
                mat.color = new Color(1f, 0.3f, 0.5f);
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", new Color(1f, 0.3f, 0.5f) * 2f);
                heart.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(heart);
                StartCoroutine(FloatHeart(heart.transform));
            }
            // Petal particles
            _seasonalParticles = SpawnParticles(center + Vector3.up * 2f, 60, new Color(1f, 0.6f, 0.7f, 0.6f), 0.04f, 3f, 0.3f);
        }

        private void DecorateEaster()
        {
            Vector3 center = GetRoomCenter();
            // Easter eggs
            for (int i = 0; i < 10; i++)
            {
                var egg = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                egg.transform.position = center + new Vector3(
                    Random.Range(-2f, 2f), 0.1f, Random.Range(-2f, 2f));
                egg.transform.localScale = new Vector3(0.08f, 0.12f, 0.08f);
                var mat = new Material(Shader.Find("Standard"));
                mat.color = Color.HSVToRGB(Random.Range(0.5f, 0.85f), 0.5f, 0.95f);
                egg.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(egg);
            }
        }

        private void DecorateThanksgiving()
        {
            Vector3 center = GetRoomCenter();
            // Harvest table
            var table = GameObject.CreatePrimitive(PrimitiveType.Cube);
            table.transform.position = center + new Vector3(0, 0.4f, -1.5f);
            table.transform.localScale = new Vector3(1.5f, 0.05f, 0.8f);
            var tMat = new Material(Shader.Find("Standard"));
            tMat.color = new Color(0.4f, 0.25f, 0.1f);
            table.GetComponent<Renderer>().material = tMat;
            _themedObjects.Add(table);
            // Gourds and candles
            for (int i = 0; i < 5; i++)
            {
                var gourd = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                gourd.transform.position = table.transform.position + new Vector3(
                    Random.Range(-0.6f, 0.6f), 0.1f, Random.Range(-0.3f, 0.3f));
                gourd.transform.localScale = new Vector3(0.1f, 0.08f, 0.1f);
                var mat = new Material(Shader.Find("Standard"));
                mat.color = Color.HSVToRGB(Random.Range(0.05f, 0.12f), 0.7f, 0.6f);
                gourd.GetComponent<Renderer>().material = mat;
                _themedObjects.Add(gourd);
            }
            // Warm candle light
            var candle = SpawnLight(table.transform.position + Vector3.up * 0.3f, new Color(1f, 0.7f, 0.3f), 1.5f, 3f);
            _themedLights.Add(candle);
        }

        // ── Seasonal Particles ──

        private void CreateSpringParticles()
        {
            Vector3 center = GetRoomCenter();
            // Petals falling
            _seasonalParticles = SpawnParticles(center + Vector3.up * 3f, 50, new Color(1f, 0.7f, 0.8f, 0.5f), 0.04f, 4f, 0.2f);
        }

        private void CreateSummerParticles()
        {
            Vector3 center = GetRoomCenter();
            // Dust motes / pollen
            _seasonalParticles = SpawnParticles(center + Vector3.up * 2f, 80, new Color(1f, 0.95f, 0.6f, 0.2f), 0.02f, 5f, 0.1f);
        }

        private void CreateAutumnParticles()
        {
            Vector3 center = GetRoomCenter();
            // Falling leaves
            _seasonalParticles = SpawnParticles(center + Vector3.up * 3f, 60, new Color(0.8f, 0.4f, 0.15f, 0.7f), 0.05f, 4f, 0.3f);
        }

        private void CreateWinterParticles()
        {
            Vector3 center = GetRoomCenter();
            // Snow
            _seasonalParticles = SpawnParticles(center + Vector3.up * 4f, 150, new Color(0.95f, 0.97f, 1f, 0.6f), 0.03f, 5f, 0.5f);
        }

        // ── Object Creators ──

        private GameObject CreateBlossomTree(Vector3 pos)
        {
            var go = new GameObject("BlossomTree");
            go.transform.position = pos;
            var trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.transform.SetParent(go.transform, false);
            trunk.transform.localScale = new Vector3(0.15f, 1.2f, 0.15f);
            trunk.transform.localPosition = new Vector3(0, 0.6f, 0);
            var tMat = new Material(Shader.Find("Standard"));
            tMat.color = new Color(0.3f, 0.2f, 0.15f);
            trunk.GetComponent<Renderer>().material = tMat;
            for (int i = 0; i < 5; i++)
            {
                var blossom = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                blossom.transform.SetParent(go.transform, false);
                blossom.transform.localScale = Vector3.one * Random.Range(0.4f, 0.7f);
                blossom.transform.localPosition = new Vector3(Random.Range(-0.3f, 0.3f), 1.2f + i * 0.15f, Random.Range(-0.3f, 0.3f));
                var bMat = new Material(Shader.Find("Standard"));
                bMat.color = new Color(1f, 0.75f, 0.85f);
                blossom.GetComponent<Renderer>().material = bMat;
            }
            return go;
        }

        private GameObject CreateAutumnTree(Vector3 pos)
        {
            var go = new GameObject("AutumnTree");
            go.transform.position = pos;
            var trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.transform.SetParent(go.transform, false);
            trunk.transform.localScale = new Vector3(0.18f, 1.5f, 0.18f);
            trunk.transform.localPosition = new Vector3(0, 0.75f, 0);
            var tMat = new Material(Shader.Find("Standard"));
            tMat.color = new Color(0.25f, 0.15f, 0.08f);
            trunk.GetComponent<Renderer>().material = tMat;
            for (int i = 0; i < 4; i++)
            {
                var leaves = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                leaves.transform.SetParent(go.transform, false);
                leaves.transform.localScale = Vector3.one * Random.Range(0.5f, 0.8f);
                leaves.transform.localPosition = new Vector3(Random.Range(-0.3f, 0.3f), 1.5f + i * 0.2f, Random.Range(-0.3f, 0.3f));
                var lMat = new Material(Shader.Find("Standard"));
                lMat.color = Color.HSVToRGB(Random.Range(0.02f, 0.1f), 0.85f, 0.6f);
                leaves.GetComponent<Renderer>().material = lMat;
            }
            return go;
        }

        private GameObject CreateBareTree(Vector3 pos)
        {
            var go = new GameObject("BareTree");
            go.transform.position = pos;
            var trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.transform.SetParent(go.transform, false);
            trunk.transform.localScale = new Vector3(0.15f, 2f, 0.15f);
            trunk.transform.localPosition = new Vector3(0, 1f, 0);
            var tMat = new Material(Shader.Find("Standard"));
            tMat.color = new Color(0.2f, 0.15f, 0.1f);
            trunk.GetComponent<Renderer>().material = tMat;
            // A few sparse branches
            for (int i = 0; i < 3; i++)
            {
                var branch = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                branch.transform.SetParent(go.transform, false);
                branch.transform.localScale = new Vector3(0.04f, 0.5f, 0.04f);
                branch.transform.localPosition = new Vector3(0, 1.5f + i * 0.3f, 0);
                branch.transform.localRotation = Quaternion.Euler(0, 0, Random.Range(-30, 30));
                branch.GetComponent<Renderer>().material = tMat;
            }
            return go;
        }

        // ── Effects ──

        private IEnumerator FireFlicker(Light light)
        {
            float baseIntensity = light.intensity;
            while (light != null && IsThemed)
            {
                light.intensity = baseIntensity + Random.Range(-0.3f, 0.5f);
                yield return new WaitForSeconds(Random.Range(0.05f, 0.15f));
            }
            if (light != null) light.intensity = baseIntensity;
        }

        private IEnumerator FloatHeart(Transform t)
        {
            Vector3 basePos = t.position;
            float phase = Random.Range(0f, Mathf.PI * 2f);
            while (t != null && IsThemed)
            {
                t.position = basePos + Vector3.up * Mathf.Sin(Time.time + phase) * 0.15f;
                t.Rotate(Vector3.up, 30f * Time.deltaTime);
                yield return null;
            }
        }

        // ── Communication ──

        private IEnumerator AliceSeasonalOpening(string seasonName, string holidayName)
        {
            yield return new WaitForSeconds(2f);
            if (!string.IsNullOrEmpty(holidayName))
                AliceSay($"it's {seasonName}, and {holidayName}. i love this time.");
            else
                AliceSay($"it feels like {seasonName}, doesn't it?");
        }

        private void AliceSeasonalComment()
        {
            int sIdx = (int)CurrentSeason;
            var sLines = SeasonDefs[sIdx].Item8;
            string line = sLines[Random.Range(0, sLines.Length)];

            if (CurrentHoliday != Holiday.None)
            {
                int hIdx = (int)CurrentHoliday;
                var hLines = HolidayDefs[hIdx].Item4;
                if (hLines.Length > 0 && Random.value < 0.5f)
                    line = hLines[Random.Range(0, hLines.Length)];
            }

            AliceSay(line);
        }

        private void AliceSay(string text)
        {
            Debug.Log($"[Seasonal] Alice: {text}");
            if (wsClient != null)
            {
                var payload = new SeasonalPayload
                {
                    type = "seasonal.comment",
                    text = text,
                    season = CurrentSeason.ToString(),
                    holiday = CurrentHoliday.ToString(),
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        [System.Serializable]
        private class SeasonalPayload
        {
            public string type;
            public string text;
            public string season;
            public string holiday;
        }

        // ── Helpers ──

        private Vector3 GetRoomCenter()
        {
            return Camera.main != null
                ? Camera.main.transform.position - Camera.main.transform.forward * 0.5f
                : Vector3.zero;
        }

        private ParticleSystem SpawnParticles(Vector3 pos, int count, Color color, float size, float range, float speed)
        {
            var go = new GameObject("SeasonalParticles");
            go.transform.position = pos;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.startColor = color;
            main.startSize = size;
            main.startSpeed = speed;
            main.maxParticles = Mathf.RoundToInt(count * particleDensity);
            main.loop = true;
            main.startLifetime = range;
            var emission = ps.emission;
            emission.rateOverTime = count / 3f;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = range;
            _themedObjects.Add(go);
            return ps;
        }

        private Light SpawnLight(Vector3 pos, Color color, float intensity, float range)
        {
            var go = new GameObject("SeasonalLight");
            go.transform.position = pos;
            var light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.intensity = intensity;
            light.range = range;
            _themedObjects.Add(go);
            return light;
        }

        // ── Public API ──

        public void SetSeason(string seasonName)
        {
            if (System.Enum.TryParse<Season>(seasonName, true, out var s))
            {
                CurrentSeason = s;
                ApplyTheme();
            }
        }

        public void SetHoliday(string holidayName)
        {
            if (System.Enum.TryParse<Holiday>(holidayName, true, out var h))
            {
                CurrentHoliday = h;
                ApplyTheme();
            }
        }

        public void ClearHoliday()
        {
            CurrentHoliday = Holiday.None;
            ApplyTheme();
        }

        public void AliceSetSeason(string seasonName) => SetSeason(seasonName);
        public void AliceSetHoliday(string holidayName) => SetHoliday(holidayName);
    }
}
