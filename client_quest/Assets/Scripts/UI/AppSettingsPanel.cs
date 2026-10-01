using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using FoveAI.IPC;
using FoveAI.Avatar;
using FoveAI.Creative;

namespace FoveAI.UI
{
    /// <summary>
    /// In-VR App Settings Panel — grabbable, semi-transparent.
    ///
    /// Sections:
    ///   1. Connection — server IP, WS port, HTTP port, reconnect
    ///   2. Avatar — model selection, lip sync toggle, emotion toggle
    ///   3. Audio — TTS volume, music volume, spatial audio toggle
    ///   4. Voice — STT sensitivity, interrupt toggle, VAD threshold
    ///   5. Creative — default sketch color, line width, spawn scale
    ///   6. HUD — corner panel opacity, show/hide toggle
    ///   7. System — restart backend, reset settings, debug log toggle
    ///
    /// Settings persist to StreamingAssets/AppConfig.json and PlayerPrefs.
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class AppSettingsPanel : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private UserHUD hud;
        [SerializeField] private AmbientMusicPlayer musicPlayer;

        [Header("Panel")]
        [Range(0f, 1f)] public float panelAlpha = 0.95f;
        public float panelWidth = 700f;
        public float panelHeight = 800f;

        // ── Internal ──
        private Canvas _canvas;
        private CanvasGroup _canvasGroup;
        private TMP_FontAsset _font;
        private ScrollRect _scrollRect;
        private TMP_Text _contentText;

        // Settings state (mirrors AppSettings + runtime prefs)
        private string _serverIp;
        private int _wsPort;
        private int _httpPort;
        private string _avatarModel;
        private float _ttsVolume = 1f;
        private float _musicVolume = 0.35f;
        private bool _lipSyncEnabled = true;
        private bool _emotionEnabled = true;
        private bool _interruptEnabled = true;
        private bool _spatialAudio = false;
        private float _vadSensitivity = 0.02f;
        private bool _hudVisible = true;
        private float _hudOpacity = 0.15f;
        private bool _debugLog = false;

        // Avatar model options
        private readonly string[] _avatarOptions = { "Alicechan.vrm", "avatar.vrm", "Large_pupils.vrm", "SchoolUniform.vrm" };
        private int _avatarIndex = 0;

        private void Awake()
        {
            _font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            if (_font == null) _font = TMP_Settings.defaultFontAsset;

            _canvas = GetComponent<Canvas>();
            _canvas.renderMode = RenderMode.WorldSpace;
            var rt = GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(panelWidth, panelHeight);
            rt.localScale = Vector3.one * 0.0015f;

            _canvasGroup = GetComponent<CanvasGroup>();
            if (_canvasGroup == null) _canvasGroup = gameObject.AddComponent<CanvasGroup>();
            _canvasGroup.alpha = panelAlpha;

            if (GetComponent<GrabbablePanel>() == null)
                gameObject.AddComponent<GrabbablePanel>();

            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (hud == null) hud = FindAnyObjectByType<UserHUD>();
            if (musicPlayer == null) musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();

            LoadSettings();
            BuildUI();
        }

        private void Start()
        {
            Camera cam = Camera.main;
            if (cam == null) cam = FindAnyObjectByType<Camera>();
            if (cam != null)
            {
                Vector3 fwd = cam.transform.forward;
                fwd.y = 0f;
                if (fwd.sqrMagnitude < 0.01f) fwd = Vector3.forward;
                fwd.Normalize();

                Vector3 right = cam.transform.right;
                right.y = 0f;
                right.Normalize();

                transform.position = cam.transform.position + fwd * 1.8f - right * 0.6f;
                transform.rotation = Quaternion.LookRotation(transform.position - cam.transform.position);
            }
        }

        // ── Settings Load/Save ──

        private void LoadSettings()
        {
            var s = Config.ConfigLoader.Settings;
            _serverIp = s.serverIp;
            _wsPort = s.wsPort;
            _httpPort = s.httpPort;
            _avatarModel = s.avatarModel;

            // Find avatar index
            for (int i = 0; i < _avatarOptions.Length; i++)
                if (_avatarOptions[i] == _avatarModel) { _avatarIndex = i; break; }

            // Runtime prefs
            _ttsVolume = PlayerPrefs.GetFloat("TTSVolume", 1f);
            _musicVolume = PlayerPrefs.GetFloat("MusicVolume", 0.35f);
            _lipSyncEnabled = PlayerPrefs.GetInt("LipSync", 1) == 1;
            _emotionEnabled = PlayerPrefs.GetInt("Emotion", 1) == 1;
            _interruptEnabled = PlayerPrefs.GetInt("Interrupt", 1) == 1;
            _spatialAudio = PlayerPrefs.GetInt("SpatialAudio", 0) == 1;
            _vadSensitivity = PlayerPrefs.GetFloat("VADSensitivity", 0.02f);
            _hudVisible = PlayerPrefs.GetInt("HUDVisible", 1) == 1;
            _hudOpacity = PlayerPrefs.GetFloat("HUDOpacity", 0.15f);
            _debugLog = PlayerPrefs.GetInt("DebugLog", 0) == 1;
        }

        private void SaveSettings()
        {
            // Save to PlayerPrefs
            PlayerPrefs.SetFloat("TTSVolume", _ttsVolume);
            PlayerPrefs.SetFloat("MusicVolume", _musicVolume);
            PlayerPrefs.SetInt("LipSync", _lipSyncEnabled ? 1 : 0);
            PlayerPrefs.SetInt("Emotion", _emotionEnabled ? 1 : 0);
            PlayerPrefs.SetInt("Interrupt", _interruptEnabled ? 1 : 0);
            PlayerPrefs.SetInt("SpatialAudio", _spatialAudio ? 1 : 0);
            PlayerPrefs.SetFloat("VADSensitivity", _vadSensitivity);
            PlayerPrefs.SetInt("HUDVisible", _hudVisible ? 1 : 0);
            PlayerPrefs.SetFloat("HUDOpacity", _hudOpacity);
            PlayerPrefs.SetInt("DebugLog", _debugLog ? 1 : 0);
            PlayerPrefs.Save();

            // Save config to AppConfig.json
            var settings = new Config.AppSettings
            {
                serverIp = _serverIp,
                wsPort = _wsPort,
                httpPort = _httpPort,
                soulPort = Config.ConfigLoader.Settings != null ? Config.ConfigLoader.Settings.soulPort : 8405,
                avatarModel = _avatarModel,
            };
            string json = JsonUtility.ToJson(settings, true);
            string path = Path.Combine(Application.streamingAssetsPath, "AppConfig.json");

#if !UNITY_ANDROID || UNITY_EDITOR
            File.WriteAllText(path, json);
            Debug.Log($"[Settings] Saved config to {path}");
#else
            // On Android, we can't write to StreamingAssets directly
            // Save to persistentDataPath and load from there on next startup
            string altPath = Path.Combine(Application.persistentDataPath, "AppConfig.json");
            File.WriteAllText(altPath, json);
            Debug.Log($"[Settings] Saved config to {altPath}");
#endif

            ApplySettings();
            RefreshDisplay();
        }

        private void ApplySettings()
        {
            // Apply TTS volume
            if (wsClient != null)
            {
                var audioSrc = wsClient.GetComponent<AudioSource>();
                if (audioSrc != null) audioSrc.volume = _ttsVolume;
            }

            // Apply music volume
            if (musicPlayer != null)
                musicPlayer.SetVolume(_musicVolume);

            // Apply HUD visibility
            if (hud != null)
                hud.gameObject.SetActive(_hudVisible);

            // Apply spatial audio
            if (wsClient != null)
            {
                var audioSrc = wsClient.GetComponent<AudioSource>();
                if (audioSrc != null) audioSrc.spatialBlend = _spatialAudio ? 1f : 0f;
            }
        }

        // ── UI Construction ──

        private void BuildUI()
        {
            // Background
            var bgGo = new GameObject("SettingsBg");
            bgGo.transform.SetParent(transform, false);
            var bgImg = bgGo.AddComponent<Image>();
            bgImg.color = new Color(0.04f, 0.06f, 0.10f, 0.95f);
            var bgRt = bgGo.GetComponent<RectTransform>();
            bgRt.anchorMin = Vector2.zero;
            bgRt.anchorMax = Vector2.one;
            bgRt.offsetMin = Vector2.zero;
            bgRt.offsetMax = Vector2.zero;

            // Title bar
            var titleGo = new GameObject("TitleBar");
            titleGo.transform.SetParent(transform, false);
            var titleImg = titleGo.AddComponent<Image>();
            titleImg.color = new Color(0.08f, 0.12f, 0.18f, 1f);
            var titleRt = titleGo.GetComponent<RectTransform>();
            titleRt.anchorMin = new Vector2(0, 1);
            titleRt.anchorMax = new Vector2(1, 1);
            titleRt.sizeDelta = new Vector2(0, 50f);
            titleRt.offsetMin = Vector2.zero;
            titleRt.offsetMax = Vector2.zero;

            var titleText = titleGo.AddComponent<TextMeshProUGUI>();
            titleText.font = _font;
            titleText.fontSize = 24;
            titleText.color = new Color(0.3f, 0.7f, 1f, 1f);
            titleText.text = "⚙  APP SETTINGS";
            titleText.alignment = TextAlignmentOptions.Center;
            var titleTextRt = titleText.GetComponent<RectTransform>();
            titleTextRt.anchorMin = Vector2.zero;
            titleTextRt.anchorMax = Vector2.one;
            titleTextRt.offsetMin = Vector2.zero;
            titleTextRt.offsetMax = Vector2.zero;

            // Scroll view
            CreateScroll();

            // Bottom bar with Save/Reset buttons
            CreateBottomBar();

            // Event system
            if (UnityEngine.EventSystems.EventSystem.current == null)
            {
                var es = new GameObject("EventSystem");
                es.AddComponent<UnityEngine.EventSystems.EventSystem>();
                es.AddComponent<UnityEngine.InputSystem.UI.InputSystemUIInputModule>();
            }

            RefreshDisplay();
        }

        private void CreateScroll()
        {
            var scrollGo = new GameObject("Scroll");
            scrollGo.transform.SetParent(transform, false);
            _scrollRect = scrollGo.AddComponent<ScrollRect>();
            var scrollRt = scrollGo.GetComponent<RectTransform>();
            scrollRt.anchorMin = new Vector2(0, 0.08f);
            scrollRt.anchorMax = new Vector2(1, 0.94f);
            scrollRt.offsetMin = Vector2.zero;
            scrollRt.offsetMax = Vector2.zero;

            var viewportGo = new GameObject("Viewport");
            viewportGo.transform.SetParent(scrollGo.transform, false);
            viewportGo.AddComponent<Image>().color = Color.clear;
            viewportGo.AddComponent<RectMask2D>();
            var vpRt = viewportGo.GetComponent<RectTransform>();
            vpRt.anchorMin = Vector2.zero;
            vpRt.anchorMax = Vector2.one;
            vpRt.offsetMin = Vector2.zero;
            vpRt.offsetMax = Vector2.zero;
            _scrollRect.viewport = vpRt;

            var contentGo = new GameObject("Content");
            contentGo.transform.SetParent(viewportGo.transform, false);
            _contentText = contentGo.AddComponent<TextMeshProUGUI>();
            _contentText.font = _font;
            _contentText.fontSize = 18;
            _contentText.color = new Color(0.88f, 0.92f, 0.98f, 1f);
            _contentText.richText = true;
            _contentText.alignment = TextAlignmentOptions.TopLeft;
            _contentText.enableWordWrapping = true;
            var contentRt = _contentText.GetComponent<RectTransform>();
            contentRt.anchorMin = new Vector2(0, 1);
            contentRt.anchorMax = new Vector2(1, 1);
            contentRt.pivot = new Vector2(0.5f, 1);
            contentRt.offsetMin = new Vector2(16, 0);
            contentRt.offsetMax = new Vector2(-16, 0);
            _scrollRect.content = contentRt;
        }

        private void CreateBottomBar()
        {
            var barGo = new GameObject("BottomBar");
            barGo.transform.SetParent(transform, false);
            var barImg = barGo.AddComponent<Image>();
            barImg.color = new Color(0.05f, 0.07f, 0.10f, 1f);
            var barRt = barGo.GetComponent<RectTransform>();
            barRt.anchorMin = new Vector2(0, 0);
            barRt.anchorMax = new Vector2(1, 0);
            barRt.sizeDelta = new Vector2(0, 56f);
            barRt.offsetMin = Vector2.zero;
            barRt.offsetMax = Vector2.zero;

            // Save button
            var saveBtn = CreateButton("Save", "SAVE", barGo.transform, new Vector2(40, 0), 120f, new Color(0.15f, 0.45f, 0.25f, 1f));
            saveBtn.onClick.AddListener(SaveSettings);

            // Reset button
            var resetBtn = CreateButton("Reset", "RESET", barGo.transform, new Vector2(180, 0), 120f, new Color(0.45f, 0.15f, 0.15f, 1f));
            resetBtn.onClick.AddListener(ResetSettings);

            // Reconnect button
            var reconnectBtn = CreateButton("Reconnect", "RECONNECT", barGo.transform, new Vector2(320, 0), 160f, new Color(0.15f, 0.25f, 0.45f, 1f));
            reconnectBtn.onClick.AddListener(Reconnect);

            // Close button
            var closeBtn = CreateButton("Close", "✕", barGo.transform, new Vector2(panelWidth - 70, 0), 50f, new Color(0.3f, 0.15f, 0.15f, 1f));
            closeBtn.onClick.AddListener(() => gameObject.SetActive(false));
        }

        private Button CreateButton(string name, string label, Transform parent, Vector2 pos, float width, Color color)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var img = go.AddComponent<Image>();
            img.color = color;
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;

            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 0.5f);
            rt.anchorMax = new Vector2(0, 0.5f);
            rt.sizeDelta = new Vector2(width, 40f);
            rt.anchoredPosition = pos;

            var labelGo = new GameObject("Label");
            labelGo.transform.SetParent(go.transform, false);
            var labelTxt = labelGo.AddComponent<TextMeshProUGUI>();
            labelTxt.font = _font;
            labelTxt.fontSize = 18;
            labelTxt.color = Color.white;
            labelTxt.text = label;
            labelTxt.alignment = TextAlignmentOptions.Center;
            var labelRt = labelGo.GetComponent<RectTransform>();
            labelRt.anchorMin = Vector2.zero;
            labelRt.anchorMax = Vector2.one;
            labelRt.offsetMin = Vector2.zero;
            labelRt.offsetMax = Vector2.zero;

            return btn;
        }

        // ── Display ──

        private void RefreshDisplay()
        {
            string connStatus = wsClient != null && wsClient.IsConnected ? "<color=#44ff88>●</color> Connected" : "<color=#ff4444>●</color> Disconnected";

            _contentText.text =
                // Connection
                $"<size=22><b>CONNECTION</b></size>  {connStatus}\n" +
                $"  Server IP:     <color=#44aaff>{_serverIp}</color>\n" +
                $"  WS Port:       <color=#44aaff>{_wsPort}</color>\n" +
                $"  HTTP Port:     <color=#44aaff>{_httpPort}</color>\n" +
                $"  [A] Edit IP  [B] Edit WS Port  [X] Edit HTTP Port\n\n" +

                // Avatar
                $"<size=22><b>AVATAR</b></size>\n" +
                $"  Model:         <color=#44aaff>{_avatarModel}</color>\n" +
                $"  Lip Sync:      {(_lipSyncEnabled ? "<color=#44ff88>ON</color>" : "<color=#ff4444>OFF</color>")}\n" +
                $"  Emotion:       {(_emotionEnabled ? "<color=#44ff88>ON</color>" : "<color=#ff4444>OFF</color>")}\n" +
                $"  [LStick] Cycle Avatar  [RStick Click] Toggle LipSync\n\n" +

                // Audio
                $"<size=22><b>AUDIO</b></size>\n" +
                $"  TTS Volume:    <color=#44aaff>{_ttsVolume:F2}</color>  [{BarString(_ttsVolume)}]\n" +
                $"  Music Volume:  <color=#44aaff>{_musicVolume:F2}</color>  [{BarString(_musicVolume)}]\n" +
                $"  Spatial Audio: {(_spatialAudio ? "<color=#44ff88>3D</color>" : "<color=#44aaff>2D</color>")}\n" +
                $"  [RStick Up/Down] TTS Volume  [LStick Up/Down] Music Volume\n" +
                $"  [RStick Click] Toggle Spatial Audio\n\n" +

                // Voice
                $"<size=22><b>VOICE</b></size>\n" +
                $"  Interrupt TTS: {(_interruptEnabled ? "<color=#44ff88>ON</color>" : "<color=#ff4444>OFF</color>")}\n" +
                $"  VAD Sensitivity: <color=#44aaff>{_vadSensitivity:F3}</color>\n" +
                $"  [LStick Click] Toggle Interrupt\n\n" +

                // Creative
                $"<size=22><b>CREATIVE</b></size>\n" +
                $"  Music Mood:    <color=#44aaff>{(musicPlayer != null ? musicPlayer.GetCurrentMood() : "N/A")}</color>\n" +
                $"  Music Playing: {(musicPlayer != null && musicPlayer.IsPlaying ? "<color=#44ff88>Yes</color>" : "<color=#888>No</color>")}\n\n" +

                // HUD
                $"<size=22><b>HUD</b></size>\n" +
                $"  Visible:       {(_hudVisible ? "<color=#44ff88>ON</color>" : "<color=#ff4444>OFF</color>")}\n" +
                $"  Idle Opacity:  <color=#44aaff>{_hudOpacity:F2}</color>\n" +
                $"  [Y] Toggle HUD  [Start] Toggle Settings\n\n" +

                // System
                $"<size=22><b>SYSTEM</b></size>\n" +
                $"  Debug Log:     {(_debugLog ? "<color=#44ff88>ON</color>" : "<color=#ff4444>OFF</color>")}\n" +
                $"  FPS:           <color=#44aaff>{1f / Time.deltaTime:F0}</color>\n" +
                $"  Device:        <color=#666>Quest 3</color>\n\n" +

                $"<size=16><i>Press SAVE to persist settings.\n" +
                $"Press RECONNECT to apply connection changes.</i></size>";
        }

        private string BarString(float value)
        {
            int bars = Mathf.RoundToInt(value * 10);
            string s = "";
            for (int i = 0; i < 10; i++) s += i < bars ? "▓" : "░";
            return s;
        }

        // ── Input Handling ──

        private void Update()
        {
            // Toggle settings panel with Start/Menu button
            if (OVRInput.GetDown(OVRInput.Button.Start))
            {
                gameObject.SetActive(!gameObject.activeSelf);
            }

            if (!gameObject.activeSelf) return;

            // A = Edit server IP (cycle through common IPs)
            if (OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
            {
                _serverIp = _serverIp == "192.168.8.100" ? "127.0.0.1" :
                            _serverIp == "127.0.0.1" ? "192.168.8.100" : "192.168.8.100";
                RefreshDisplay();
            }

            // B = Cycle WS port
            if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch))
            {
                _wsPort = _wsPort == 8403 ? 8400 : _wsPort == 8400 ? 8403 : 8403;
                RefreshDisplay();
            }

            // X = Cycle HTTP port
            if (OVRInput.GetDown(OVRInput.Button.Three, OVRInput.Controller.LTouch))
            {
                _httpPort = _httpPort == 8402 ? 8401 : _httpPort == 8401 ? 8402 : 8402;
                RefreshDisplay();
            }

            // Left stick = cycle avatar / music volume
            Vector2 lStick = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.LTouch);
            if (OVRInput.GetDown(OVRInput.Button.PrimaryThumbstick, OVRInput.Controller.LTouch))
            {
                // Click = cycle avatar
                _avatarIndex = (_avatarIndex + 1) % _avatarOptions.Length;
                _avatarModel = _avatarOptions[_avatarIndex];
                RefreshDisplay();
            }
            else if (Mathf.Abs(lStick.y) > 0.3f && Time.frameCount % 5 == 0)
            {
                _musicVolume = Mathf.Clamp01(_musicVolume + lStick.y * 0.02f);
                RefreshDisplay();
            }

            // Right stick = TTS volume
            Vector2 rStick = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.RTouch);
            if (OVRInput.GetDown(OVRInput.Button.PrimaryThumbstick, OVRInput.Controller.RTouch))
            {
                // Click = toggle spatial audio
                _spatialAudio = !_spatialAudio;
                RefreshDisplay();
            }
            else if (Mathf.Abs(rStick.y) > 0.3f && Time.frameCount % 5 == 0)
            {
                _ttsVolume = Mathf.Clamp01(_ttsVolume + rStick.y * 0.02f);
                RefreshDisplay();
            }

            // Y = Toggle HUD
            if (OVRInput.GetDown(OVRInput.Button.Four, OVRInput.Controller.LTouch))
            {
                _hudVisible = !_hudVisible;
                if (hud != null) hud.gameObject.SetActive(_hudVisible);
                RefreshDisplay();
            }

            // L trigger = Toggle lip sync
            if (OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.LTouch))
            {
                _lipSyncEnabled = !_lipSyncEnabled;
                RefreshDisplay();
            }

            // R grip = Toggle interrupt
            if (OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger, OVRInput.Controller.RTouch) > 0.5f &&
                OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
            {
                _interruptEnabled = !_interruptEnabled;
                RefreshDisplay();
            }

            // Auto-refresh FPS every second
            if (Time.frameCount % 60 == 0)
                RefreshDisplay();
        }

        // ── Actions ──

        private void ResetSettings()
        {
            _serverIp = "192.168.8.100";
            _wsPort = 8403;
            _httpPort = 8402;
            _avatarModel = "Alicechan.vrm";
            _avatarIndex = 0;
            _ttsVolume = 1f;
            _musicVolume = 0.35f;
            _lipSyncEnabled = true;
            _emotionEnabled = true;
            _interruptEnabled = true;
            _spatialAudio = false;
            _vadSensitivity = 0.02f;
            _hudVisible = true;
            _hudOpacity = 0.15f;
            _debugLog = false;

            PlayerPrefs.DeleteAll();
            SaveSettings();
            Debug.Log("[Settings] Reset to defaults");
        }

        private void Reconnect()
        {
            if (wsClient != null)
            {
                // Update config in memory
                Config.ConfigLoader.Settings.serverIp = _serverIp;
                Config.ConfigLoader.Settings.wsPort = _wsPort;
                Config.ConfigLoader.Settings.httpPort = _httpPort;
                Config.ConfigLoader.Settings.avatarModel = _avatarModel;

                // Trigger reconnect
                wsClient.SetServerUrl($"ws://{_serverIp}:{_wsPort}/ws");
                Debug.Log($"[Settings] Reconnecting to ws://{_serverIp}:{_wsPort}");
            }
            RefreshDisplay();
        }
    }
}
