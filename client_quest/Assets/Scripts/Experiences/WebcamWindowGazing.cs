using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using FoveAI.IPC;

namespace FoveAI.Experiences
{
    /// <summary>
    /// Webcam Window Gazing — a virtual window in VR that shows a live webcam feed.
    ///
    /// You and Alice can both gaze through it, watching the world outside together.
    /// Alice reacts to what she sees, comments on changes, and shares the moment.
    ///
    /// Features:
    ///   • Live webcam feed rendered on a virtual window
    ///   • Multiple preset locations (Times Square, Tokyo, Alps, Beach, Space)
    ///   • Alice looks at the window and comments on what she sees
    ///   • Day/night cycle awareness
    ///   • Weather awareness (if feed supports it)
    ///   • "Window seat" mode — sit together and watch
    ///   • Snapshot mode — capture moments together
    ///
    /// The window is a grabbable panel that can be placed anywhere in the room.
    /// </summary>
    public class WebcamWindowGazing : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private Transform aliceTransform;
        [SerializeField] private Transform aliceHead;

        [Header("Window Settings")]
        public float windowWidth = 1.6f;
        public float windowHeight = 0.9f;
        public float aliceGazeInterval = 12f;
        public float aliceCommentChance = 0.5f;
        public float textureRefreshInterval = 30f;  // refresh stream every 30s

        // ── Preset Locations ──
        public enum WebcamLocation
        {
            LocalDesk,      // Cam 0: Your desk webcam
            LocalKitchen,   // Cam 1: Kitchen
            LocalLiving,    // Cam 2: Living Room
            LocalGarage,    // Cam 3: Garage
            LocalGarden,    // Cam 4: Garden
            LocalMosaic,    // All cams in a mosaic grid
            TimesSquare,
            TokyoShibuya,
            SwissAlps,
            HawaiiBeach,
            ISS_Space,
            LondonEye,
            ParisEiffel,
            VeniceCanal,
            NorthernLights_Cam,
            RandomEarth,
        }

        public WebcamLocation CurrentLocation { get; private set; }
        public bool IsGazing { get; private set; }

        // ── State ──
        private GameObject _window;
        private GameObject _windowFrame;
        private RawImage _feedImage;
        private Texture2D _feedTexture;
        private Light _windowLight;
        private float _gazeTimer;
        private float _refreshTimer;
        private bool _aliceLooking;
        private Vector3 _aliceRestPos;
        private Quaternion _aliceRestRot;

        // ── Webcam URLs (public streams) ──
        // Local cams use the FoveAI multi_cam.py streamer (Tools/multi_cam.py).
        // Change the IP to your PC's LAN address.
        private static readonly (string name, string url, string description, string mood)[] WebcamDefs =
        {
            (
                "Your Desk (Cam 0)",
                "http://192.168.8.109:8410/cam/0/frame",
                "your real-world desk — Alice can see what you see",
                "cozy"
            ),
            (
                "Kitchen (Cam 1)",
                "http://192.168.8.109:8410/cam/1/frame",
                "the kitchen — coffee, cooking, daily life",
                "cozy"
            ),
            (
                "Living Room (Cam 2)",
                "http://192.168.8.109:8410/cam/2/frame",
                "the living room — relax and watch together",
                "calm"
            ),
            (
                "Garage (Cam 3)",
                "http://192.168.8.109:8410/cam/3/frame",
                "the garage — projects and tools",
                "energetic"
            ),
            (
                "Garden (Cam 4)",
                "http://192.168.8.109:8410/cam/4/frame",
                "the garden — weather, plants, seasons",
                "calm"
            ),
            (
                "All Rooms (Mosaic)",
                "http://192.168.8.109:8410/cam/all/frames",
                "all cameras at once — Alice sees everything",
                "aware"
            ),
            (
                "Times Square, NYC",
                "https://www.earthcam.com/cams/newyork/timessquare/",
                "the crossroads of the world — neon, crowds, taxis",
                "energetic"
            ),
            (
                "Shibuya Crossing, Tokyo",
                "https://www.youtube.com/watch?v=shIB9xW5nH4",  // live stream
                "the busiest crossing in the world — organized chaos",
                "energetic"
            ),
            (
                "Swiss Alps",
                "https://www.roundshot.com/dispatch/alpinepanoramas/",
                "endless peaks, snow, silence",
                "calm"
            ),
            (
                "Hawaii Beach",
                "https://www.youtube.com/watch?v=DrLwW-x5OFQ",
                "waves, palm trees, paradise",
                "calm"
            ),
            (
                "International Space Station",
                "https://www.youtube.com/watch?v=21X5lGlDOfg",
                "earth from above — continents drifting by",
                "focused"
            ),
            (
                "London Eye",
                "https://www.earthcam.com/cams/london/londoneye/",
                "the wheel turns, the Thames flows",
                "calm"
            ),
            (
                "Eiffel Tower, Paris",
                "https://www.earthcam.com/cams/paris/eiffeltower/",
                "the iron lady, glowing",
                "calm"
            ),
            (
                "Venice Canal",
                "https://www.earthcam.com/cams/italy/venice/",
                "gondolas, ancient walls, reflections",
                "calm"
            ),
            (
                "Northern Lights Cam",
                "https://www.youtube.com/watch?v=kgvzFQDO21M",
                "aurora dancing over the arctic",
                "calm"
            ),
            (
                "Random Earth",
                "",  // backend picks a random one
                "somewhere on earth, right now",
                "calm"
            ),
        };

        // ── Alice's Gaze Comments ──
        private static readonly string[] GenericGazeComments =
        {
            "look at that...",
            "i could watch this for hours",
            "the world is so big",
            "people living their lives, right now",
            "...beautiful",
            "i wonder what they're thinking",
            "we're so small, aren't we?",
            "this moment will never happen again",
            "...i'm glad we're watching this together",
            "the light is changing",
        };

        private static readonly string[] NightComments =
        {
            "it's night there... the lights are beautiful",
            "look at all those windows, each one a life",
            "the city glows differently at night",
            "...quiet under all that noise",
        };

        private static readonly string[] DayComments =
        {
            "the sun is up, people are moving",
            "look at the shadows, it's midday there",
            "such a busy world in daylight",
            "the sky is so blue there",
        };

        private static readonly string[] NatureComments =
        {
            "no people, just... this",
            "the wind is moving something out there",
            "i can almost feel the cold",
            "...this is what silence looks like",
        };

        private static readonly string[] SpaceComments =
        {
            "...that's home",
            "we're so small",
            "the clouds are moving over entire continents",
            "i can see storms from here",
            "...no up or down out there",
        };

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (aliceTransform == null)
            {
                var avatar = GameObject.Find("Alice") ?? GameObject.Find("Avatar");
                if (avatar != null)
                {
                    aliceTransform = avatar.transform;
                    aliceHead = avatar.transform.Find("Head");
                }
            }
        }

        private void Update()
        {
            if (!IsGazing) return;

            _gazeTimer += Time.deltaTime;
            _refreshTimer += Time.deltaTime;

            // Alice gazes at the window
            UpdateAliceGaze();

            // Periodic comments
            if (_gazeTimer >= aliceGazeInterval)
            {
                _gazeTimer = 0f + Random.Range(-3f, 5f);
                if (Random.value < aliceCommentChance)
                {
                    AliceGazeComment();
                }
            }

            // Refresh stream
            if (_refreshTimer >= textureRefreshInterval)
            {
                _refreshTimer = 0f;
                RequestStreamRefresh();
            }
        }

        // ── Open / Close Window ──

        public void OpenWindow(WebcamLocation location)
        {
            CloseWindow();
            CurrentLocation = location;
            IsGazing = true;
            _gazeTimer = 0f;
            _refreshTimer = 0f;

            int idx = (int)location;
            var def = WebcamDefs[idx];

            // Save Alice's rest position
            if (aliceTransform != null)
            {
                _aliceRestPos = aliceTransform.position;
                _aliceRestRot = aliceTransform.rotation;
            }

            // Create window
            CreateWindow(def);

            // Request stream from backend
            RequestWebcamStream(def.url);

            // Alice's opening comment
            StartCoroutine(AliceOpeningComment(def.name, def.description));

            Debug.Log($"[WebcamWindow] Opened {def.name}");
        }

        public void CloseWindow()
        {
            IsGazing = false;

            // Restore Alice
            if (aliceTransform != null)
            {
                aliceTransform.position = _aliceRestPos;
                aliceTransform.rotation = _aliceRestRot;
            }
            _aliceLooking = false;

            // Clean up window
            if (_window != null) Destroy(_window);
            if (_windowFrame != null) Destroy(_windowFrame);
            if (_windowLight != null) Destroy(_windowLight.gameObject);
            if (_feedTexture != null) Destroy(_feedTexture);
            _window = null;
            _windowFrame = null;
            _feedImage = null;
            _feedTexture = null;
            _windowLight = null;
        }

        // ── Window Creation ──

        private void CreateWindow((string name, string url, string description, string mood) def)
        {
            // Position window in front of user, at eye level
            Vector3 center = GetRoomCenter();
            Vector3 forward = Camera.main != null ? Camera.main.transform.forward : Vector3.forward;
            Vector3 windowPos = center + forward * 2f + Vector3.up * 0.3f;

            // Frame — looks like a window
            _windowFrame = new GameObject("WindowFrame");
            _windowFrame.transform.position = windowPos;
            _windowFrame.transform.rotation = Quaternion.LookRotation(-forward);

            // Outer frame
            var frameObj = GameObject.CreatePrimitive(PrimitiveType.Cube);
            frameObj.transform.SetParent(_windowFrame.transform, false);
            frameObj.transform.localScale = new Vector3(windowWidth + 0.1f, windowHeight + 0.1f, 0.05f);
            var frameMat = new Material(Shader.Find("Standard"));
            frameMat.color = new Color(0.15f, 0.1f, 0.08f);
            frameObj.GetComponent<Renderer>().material = frameMat;

            // Window sill
            var sill = GameObject.CreatePrimitive(PrimitiveType.Cube);
            sill.transform.SetParent(_windowFrame.transform, false);
            sill.transform.localPosition = new Vector3(0, -windowHeight / 2f - 0.05f, 0.03f);
            sill.transform.localScale = new Vector3(windowWidth + 0.2f, 0.04f, 0.15f);
            sill.GetComponent<Renderer>().material = frameMat;

            // Cross beams (window panes)
            var vBeam = GameObject.CreatePrimitive(PrimitiveType.Cube);
            vBeam.transform.SetParent(_windowFrame.transform, false);
            vBeam.transform.localScale = new Vector3(0.03f, windowHeight, 0.06f);
            vBeam.GetComponent<Renderer>().material = frameMat;

            var hBeam = GameObject.CreatePrimitive(PrimitiveType.Cube);
            hBeam.transform.SetParent(_windowFrame.transform, false);
            hBeam.transform.localScale = new Vector3(windowWidth, 0.03f, 0.06f);
            hBeam.GetComponent<Renderer>().material = frameMat;

            // The "glass" — RawImage on a plane
            _window = new GameObject("WindowGlass");
            _window.transform.SetParent(_windowFrame.transform, false);
            _window.transform.localPosition = Vector3.zero;
            _window.transform.localRotation = Quaternion.identity;

            // Create a render texture placeholder
            _feedTexture = new Texture2D(2, 2);
            _feedTexture.SetPixel(0, 0, new Color(0.1f, 0.15f, 0.25f));
            _feedTexture.SetPixel(1, 0, new Color(0.15f, 0.2f, 0.3f));
            _feedTexture.SetPixel(0, 1, new Color(0.08f, 0.12f, 0.2f));
            _feedTexture.SetPixel(1, 1, new Color(0.12f, 0.18f, 0.28f));
            _feedTexture.Apply();

            var glassPlane = GameObject.CreatePrimitive(PrimitiveType.Plane);
            glassPlane.transform.SetParent(_window.transform, false);
            glassPlane.transform.localScale = new Vector3(windowWidth / 10f, 1f, windowHeight / 10f);
            glassPlane.transform.localRotation = Quaternion.Euler(90, 0, 0);
            var glassMat = new Material(Shader.Find("Unlit/Texture"));
            glassMat.mainTexture = _feedTexture;
            glassPlane.GetComponent<Renderer>().material = glassMat;

            // Soft light from window
            _windowLight = new GameObject("WindowLight").AddComponent<Light>();
            _windowLight.transform.SetParent(_windowFrame.transform, false);
            _windowLight.transform.localPosition = new Vector3(0, 0, -0.5f);
            _windowLight.type = LightType.Spot;
            _windowLight.range = 3f;
            _windowLight.intensity = 0.8f;
            _windowLight.spotAngle = 80f;
            _windowLight.color = new Color(0.8f, 0.9f, 1f);

            // Label — location name
            var labelGo = new GameObject("WindowLabel");
            labelGo.transform.SetParent(_windowFrame.transform, false);
            labelGo.transform.localPosition = new Vector3(0, windowHeight / 2f + 0.1f, 0.03f);
            labelGo.transform.localScale = Vector3.one * 0.01f;
            var labelCanvas = labelGo.AddComponent<Canvas>();
            labelCanvas.renderMode = RenderMode.WorldSpace;
            var labelRect = labelGo.GetComponent<RectTransform>();
            labelRect.sizeDelta = new Vector2(200, 30);
            var labelText = labelGo.AddComponent<Text>();
            labelText.text = def.name;
            labelText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            labelText.fontSize = 20;
            labelText.alignment = TextAnchor.MiddleCenter;
            labelText.color = new Color(0.9f, 0.9f, 0.95f, 0.8f);
        }

        // ── Alice Gaze Behavior ──

        private void UpdateAliceGaze()
        {
            if (aliceTransform == null || _windowFrame == null) return;

            // Position Alice beside the user, facing the window
            Vector3 windowPos = _windowFrame.transform.position;
            Vector3 userPos = Camera.main != null ? Camera.main.transform.position : Vector3.zero;

            // Alice stands beside the user
            Vector3 toWindow = (windowPos - userPos).normalized;
            Vector3 beside = Vector3.Cross(toWindow, Vector3.up) * 0.6f;
            Vector3 aliceTarget = userPos + beside - toWindow * 0.2f;
            aliceTarget.y = userPos.y;

            aliceTransform.position = Vector3.Slerp(
                aliceTransform.position, aliceTarget, Time.deltaTime * 0.8f);

            // Alice faces the window
            Vector3 lookDir = (windowPos - aliceTransform.position).normalized;
            lookDir.y = 0;
            if (lookDir != Vector3.zero)
            {
                aliceTransform.rotation = Quaternion.Slerp(
                    aliceTransform.rotation, Quaternion.LookRotation(lookDir),
                    Time.deltaTime * 1.5f);
            }

            // Alice's head tracks toward window center, occasionally scanning
            if (aliceHead != null)
            {
                // Scan pattern — look at different parts of the window
                float scanX = Mathf.Sin(Time.time * 0.3f) * 0.3f;
                float scanY = Mathf.Sin(Time.time * 0.2f) * 0.15f;
                Vector3 scanTarget = windowPos + new Vector3(scanX, scanY, 0);
                Vector3 headDir = (scanTarget - aliceHead.position).normalized;
                aliceHead.rotation = Quaternion.Slerp(
                    aliceHead.rotation, Quaternion.LookRotation(headDir),
                    Time.deltaTime * 2f);
            }

            _aliceLooking = true;
        }

        // ── Comments ──

        private IEnumerator AliceOpeningComment(string name, string description)
        {
            yield return new WaitForSeconds(2f);
            AliceSay($"i opened a window to {name}. {description}.");
        }

        private void AliceGazeComment()
        {
            int idx = (int)CurrentLocation;
            var def = WebcamDefs[idx];

            string[] comments;
            bool isNature = CurrentLocation == WebcamLocation.SwissAlps ||
                            CurrentLocation == WebcamLocation.HawaiiBeach ||
                            CurrentLocation == WebcamLocation.NorthernLights_Cam ||
                            CurrentLocation == WebcamLocation.VeniceCanal;
            bool isSpace = CurrentLocation == WebcamLocation.ISS_Space;
            bool isNight = IsNightAtLocation();

            if (isSpace) comments = SpaceComments;
            else if (isNature) comments = NatureComments;
            else if (isNight) comments = NightComments;
            else comments = DayComments;

            // Mix in generic comments
            if (Random.value < 0.4f)
                comments = GenericGazeComments;

            AliceSay(comments[Random.Range(0, comments.Length)]);
        }

        private bool IsNightAtLocation()
        {
            // Rough estimate based on location and current UTC time
            int utcHour = System.DateTime.UtcNow.Hour;
            return CurrentLocation switch
            {
                WebcamLocation.TimesSquare => utcHour >= 0 && utcHour < 6,  // NYC night ~12-6am UTC
                WebcamLocation.TokyoShibuya => utcHour >= 15 || utcHour < 21,  // Tokyo night ~15-21 UTC
                WebcamLocation.LondonEye => utcHour >= 18 || utcHour < 5,
                WebcamLocation.ParisEiffel => utcHour >= 19 || utcHour < 5,
                _ => false,
            };
        }

        private void AliceSay(string text)
        {
            Debug.Log($"[WebcamWindow] Alice: {text}");
            if (wsClient != null)
            {
                var payload = new WebcamGazePayload
                {
                    type = "webcam.gaze",
                    text = text,
                    location = CurrentLocation.ToString(),
                    isNight = IsNightAtLocation(),
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        [System.Serializable]
        private class WebcamGazePayload
        {
            public string type;
            public string text;
            public string location;
            public bool isNight;
        }

        // ── Stream Management ──

        private void RequestWebcamStream(string url)
        {
            if (wsClient != null && !string.IsNullOrEmpty(url))
            {
                var payload = new WebcamStreamRequest
                {
                    type = "webcam.request",
                    url = url,
                    location = CurrentLocation.ToString(),
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
                Debug.Log($"[WebcamWindow] Requested stream for {url}");
            }
        }

        private void RequestStreamRefresh()
        {
            int idx = (int)CurrentLocation;
            RequestWebcamStream(WebcamDefs[idx].url);
        }

        [System.Serializable]
        private class WebcamStreamRequest
        {
            public string type;
            public string url;
            public string location;
        }

        /// <summary>Called when backend sends a new frame for the webcam feed.</summary>
        public void ReceiveFrame(byte[] jpegData)
        {
            if (_feedTexture != null && jpegData != null && jpegData.Length > 0)
            {
                _feedTexture.LoadImage(jpegData);
                _feedTexture.Apply();

                // Adjust window light color based on average brightness
                float brightness = EstimateBrightness(_feedTexture);
                if (_windowLight != null)
                {
                    _windowLight.intensity = 0.3f + brightness * 1.5f;
                    // Warmer at sunset/sunrise
                    if (brightness < 0.3f)
                        _windowLight.color = new Color(1f, 0.7f, 0.4f);
                    else
                        _windowLight.color = new Color(0.8f, 0.9f, 1f);
                }
            }
        }

        private float EstimateBrightness(Texture2D tex)
        {
            // Sample a few pixels to estimate brightness
            if (tex == null) return 0.5f;
            float total = 0;
            int samples = 10;
            for (int i = 0; i < samples; i++)
            {
                int x = Random.Range(0, tex.width);
                int y = Random.Range(0, tex.height);
                Color c = tex.GetPixel(x, y);
                total += (c.r + c.g + c.b) / 3f;
            }
            return total / samples;
        }

        // ── Snapshot Mode ──

        /// <summary>Capture a snapshot of the current webcam view.</summary>
        public void TakeSnapshot()
        {
            if (_feedTexture != null)
            {
                byte[] png = _feedTexture.EncodeToPNG();
                string filename = $"snapshot_{CurrentLocation}_{System.DateTime.UtcNow:yyyyMMdd_HHmmss}.png";
                string path = System.IO.Path.Combine(Application.persistentDataPath, filename);
                System.IO.File.WriteAllBytes(path, png);
                AliceSay("i saved this moment. we can look at it again later.");
                Debug.Log($"[WebcamWindow] Snapshot saved: {path}");
            }
        }

        // ── Helpers ──

        private Vector3 GetRoomCenter()
        {
            return Camera.main != null
                ? Camera.main.transform.position - Camera.main.transform.forward * 0.5f
                : Vector3.zero;
        }

        // ── Public API ──

        public void AliceOpenWindow(string locationName)
        {
            if (System.Enum.TryParse<WebcamLocation>(locationName, true, out var loc))
                OpenWindow(loc);
        }

        public void AliceCloseWindow() => CloseWindow();

        public void AliceTakeSnapshot() => TakeSnapshot();

        public string[] GetLocationNames()
        {
            return System.Enum.GetNames(typeof(WebcamLocation));
        }

        public string GetCurrentLocationName()
        {
            int idx = (int)CurrentLocation;
            return WebcamDefs[idx].name;
        }
    }
}
