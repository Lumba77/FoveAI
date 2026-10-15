using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using FoveAI.IPC;

namespace FoveAI.UI
{
    /// <summary>
    /// FoveAI Peripheral HUD — animated, colorful, translucent metrics display
    /// that sits at the edges of the VR field of view.
    ///
    /// Design principles:
    ///   - Peripheral only: never obscures the avatar or center view
    ///   - Translucent: 15-30% alpha, soft gradients, no hard panels
    ///   - Animated: colors cycle, bars pulse, rings breathe
    ///   - Colorful: cyan/magenta/amber/green palette tied to pipeline stages
    ///   - Metrics: FPS, latency, VRAM, STT/TTS/AI activity, emotion, memory turns
    ///   - State-reactive: glows intensify during activity, dim when idle
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class UserHUD : MonoBehaviour
    {
        [Header("Positioning")]
        public float distance = 2.2f;
        public float smoothSpeed = 6f;

        [Header("Corner Glow")]
        [Range(0.08f, 0.35f)] public float cornerSize = 0.20f;
        [Range(0f, 1.0f)] public float peakAlpha = 0.75f;
        [Range(0f, 0.8f)] public float idlePeakAlpha = 0.40f;
        public float cyclePeriod = 16f;
        public float activityFadeDuration = 3f;

        [Header("Metrics Bar")]
        [Range(0f, 1.0f)] public float barAlpha = 0.55f;
        public float barPulseSpeed = 2f;

        [Header("Icons")]
        public float iconSize = 32f;
        public float numberSize = 18f;
        public float labelSize = 12f;
        [Range(0f, 1f)] public float iconAlpha = 0.85f;
        public float iconOffsetFromCorner = 50f;

        [Header("References")]
        public FoveAIWebSocketClient wsClient;

        // ── Corner palette — pipeline stage colors ──
        private static readonly Color[] Palette =
        {
            new Color(0.0f, 0.94f, 1.0f,  1f),   // cyan — connection
            new Color(0.85f, 0.15f, 0.85f, 1f),  // magenta — AI/thinking
            new Color(1.0f, 0.78f, 0.10f, 1f),   // amber — emotion
            new Color(0.30f, 0.95f, 0.45f, 1f),  // green — activity/voice
        };

        private enum Corner { TL, TR, BL, BR }

        private struct CornerData
        {
            public Image glow;
            public Text icon;
            public Text number;
            public Text label;
            public Button button;
            public Color baseColor;
            public System.Action onClick;
        }

        private readonly CornerData[] _corners = new CornerData[4];
        private Canvas _canvas;
        private CanvasGroup _canvasGroup;
        private Texture2D _radialTex;

        // ── Bottom metrics bar ──
        private Image _barBg;
        private readonly List<Image> _barSegments = new List<Image>();
        private readonly List<Text> _barLabels = new List<Text>();
        private const int BAR_SEGMENT_COUNT = 6;

        // ── Breathing ring (center-top, subtle) ──
        private Image _breathRing;
        private float _breathPhase;

        // ── State ──
        private float _fps;
        private float _fpsAccum;
        private int _fpsFrames;
        private bool _isConnected;
        private string _emotion = "neutral";
        private float _emotionIntensity;
        private bool _isSpeaking;
        private bool _isListening;
        private float _lastActivity;
        private int _latencyMs;
        private float _sttLevel, _ttsLevel, _aiLevel;
        private int _memoryTurns;
        private float _vramPct = 0.5f;
        private float _contextPct = 0.3f;

        private void Awake()
        {
            if (wsClient == null)
                wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();

            CreateRadialTexture();
            CreateCanvas();
            CreateCornerGlows();
            CreateBottomMetricsBar();
            CreateBreathRing();
            SubscribeEvents();
        }

        private void OnDestroy()
        {
            if (wsClient == null) return;
            wsClient.OnChatTextReceived -= OnChatActivity;
            wsClient.OnEmotionReceived -= OnEmotion;
            wsClient.OnAudioDataReceived -= OnTTSActivity;
            if (_radialTex != null) Destroy(_radialTex);
        }

        // ── Radial gradient texture ──

        private void CreateRadialTexture()
        {
            int size = 256;
            _radialTex = new Texture2D(size, size, TextureFormat.RGBA32, false);
            _radialTex.filterMode = FilterMode.Bilinear;
            var pixels = new Color32[size * size];

            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float nx = (float)x / size;
                    float ny = 1f - (float)y / size;
                    float dx = nx - 0f;
                    float dy = ny - 1f;
                    float dist = Mathf.Sqrt(dx * dx + dy * dy);
                    float a = Mathf.Clamp01(1f - dist);
                    a = a * a * (3f - 2f * a);
                    byte ab = (byte)(a * 255);
                    pixels[y * size + x] = new Color32(255, 255, 255, ab);
                }
            }
            _radialTex.SetPixels32(pixels);
            _radialTex.Apply();
        }

        // ── Ring texture for breathing ring ──

        private Texture2D _ringTex;
        private void CreateRingTexture()
        {
            int size = 128;
            _ringTex = new Texture2D(size, size, TextureFormat.RGBA32, false);
            _ringTex.filterMode = FilterMode.Bilinear;
            var pixels = new Color32[size * size];
            float cx = size * 0.5f, cy = size * 0.5f;
            float outerR = size * 0.45f;
            float innerR = size * 0.30f;

            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float dx = x - cx, dy = y - cy;
                    float d = Mathf.Sqrt(dx * dx + dy * dy);
                    float a = 0f;
                    if (d > innerR && d < outerR)
                    {
                        float t = (d - innerR) / (outerR - innerR);
                        // Bright at inner edge, fade outward
                        a = Mathf.Clamp01(1f - t);
                        a = a * a * (3f - 2f * a);
                    }
                    pixels[y * size + x] = new Color32(255, 255, 255, (byte)(a * 255));
                }
            }
            _ringTex.SetPixels32(pixels);
            _ringTex.Apply();
        }

        // ── Canvas ──

        private void CreateCanvas()
        {
            _canvas = GetComponent<Canvas>();
            if (_canvas == null)
                _canvas = gameObject.AddComponent<Canvas>();
            _canvas.renderMode = RenderMode.WorldSpace;

            var rt = GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(1000, 1000);
            rt.localScale = Vector3.one * 0.0012f;

            _canvasGroup = GetComponent<CanvasGroup>();
            if (_canvasGroup == null) _canvasGroup = gameObject.AddComponent<CanvasGroup>();
            _canvasGroup.blocksRaycasts = true;
            _canvasGroup.interactable = true;

            if (GetComponent<GraphicRaycaster>() == null)
                gameObject.AddComponent<GraphicRaycaster>();
        }

        // ── Corner glows ──

        private void CreateCornerGlows()
        {
            _corners[(int)Corner.TL] = CreateCorner("TL",
                new Vector2(-500f, 500f), new Vector2(0, 1),
                flipX: false, flipY: false,
                iconChar: "◉", label: "LINK",
                onClick: () => Debug.Log("[HUD] TL — connection"));

            _corners[(int)Corner.TR] = CreateCorner("TR",
                new Vector2(500f, 500f), new Vector2(1, 1),
                flipX: true, flipY: false,
                iconChar: "◆", label: "FPS",
                onClick: () => Debug.Log("[HUD] TR — performance"));

            _corners[(int)Corner.BL] = CreateCorner("BL",
                new Vector2(-500f, -500f), new Vector2(0, 0),
                flipX: false, flipY: true,
                iconChar: "✦", label: "MOOD",
                onClick: () => Debug.Log("[HUD] BL — emotion"));

            _corners[(int)Corner.BR] = CreateCorner("BR",
                new Vector2(500f, -500f), new Vector2(1, 0),
                flipX: true, flipY: true,
                iconChar: "≋", label: "FLOW",
                onClick: () => Debug.Log("[HUD] BR — activity"));
        }

        private CornerData CreateCorner(string name, Vector2 anchoredPos, Vector2 pivot,
                                         bool flipX, bool flipY, string iconChar,
                                         string label, System.Action onClick)
        {
            var cd = new CornerData { onClick = onClick };

            // ── Glow image ──
            var glowGo = new GameObject($"Glow_{name}");
            glowGo.transform.SetParent(_canvas.transform, false);
            var glowImg = glowGo.AddComponent<Image>();
            glowImg.sprite = Sprite.Create(_radialTex, new Rect(0, 0, 256, 256), Vector2.one * 0.5f);
            glowImg.type = Image.Type.Simple;
            glowImg.raycastTarget = true;

            Vector3 scale = Vector3.one;
            if (flipX) scale.x = -1;
            if (flipY) scale.y = -1;
            glowImg.transform.localScale = scale;

            var glowRt = glowGo.GetComponent<RectTransform>();
            glowRt.anchorMin = new Vector2(0.5f, 0.5f);
            glowRt.anchorMax = new Vector2(0.5f, 0.5f);
            glowRt.pivot = pivot;
            float gs = 1000f * cornerSize * 2f;
            glowRt.sizeDelta = new Vector2(gs, gs);
            glowRt.anchoredPosition = anchoredPos;

            cd.glow = glowImg;

            // ── Button ──
            cd.button = glowGo.AddComponent<Button>();
            cd.button.targetGraphic = glowImg;
            cd.button.onClick.AddListener(() => { onClick?.Invoke(); });

            // ── Icon ──
            var iconGo = new GameObject($"Icon_{name}");
            iconGo.transform.SetParent(glowGo.transform, false);
            cd.icon = iconGo.AddComponent<Text>();
            cd.icon.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            cd.icon.fontSize = (int)iconSize;
            cd.icon.fontStyle = FontStyle.Bold;
            cd.icon.alignment = TextAnchor.MiddleCenter;
            cd.icon.horizontalOverflow = HorizontalWrapMode.Overflow;
            cd.icon.verticalOverflow = VerticalWrapMode.Overflow;
            cd.icon.text = iconChar;
            cd.icon.raycastTarget = false;

            var iconRt = iconGo.GetComponent<RectTransform>();
            iconRt.anchorMin = pivot;
            iconRt.anchorMax = pivot;
            iconRt.pivot = new Vector2(0.5f, 0.5f);
            iconRt.anchoredPosition = new Vector2(
                pivot.x == 0 ? iconOffsetFromCorner : -iconOffsetFromCorner,
                pivot.y == 0 ? iconOffsetFromCorner : -iconOffsetFromCorner
            );
            iconRt.sizeDelta = new Vector2(iconSize * 2, iconSize * 2);

            // ── Number ──
            var numGo = new GameObject($"Num_{name}");
            numGo.transform.SetParent(glowGo.transform, false);
            cd.number = numGo.AddComponent<Text>();
            cd.number.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            cd.number.fontSize = (int)numberSize;
            cd.number.fontStyle = FontStyle.Bold;
            cd.number.alignment = TextAnchor.MiddleCenter;
            cd.number.horizontalOverflow = HorizontalWrapMode.Overflow;
            cd.number.verticalOverflow = VerticalWrapMode.Overflow;
            cd.number.text = "—";
            cd.number.raycastTarget = false;

            var numRt = numGo.GetComponent<RectTransform>();
            numRt.anchorMin = pivot;
            numRt.anchorMax = pivot;
            numRt.pivot = new Vector2(0.5f, 0.5f);
            float numYOffset = iconOffsetFromCorner + iconSize + 6f;
            numRt.anchoredPosition = new Vector2(
                pivot.x == 0 ? iconOffsetFromCorner : -iconOffsetFromCorner,
                pivot.y == 0 ? numYOffset : -numYOffset
            );
            numRt.sizeDelta = new Vector2(iconSize * 3, numberSize * 2);

            // ── Label (small text under number) ──
            var labelGo = new GameObject($"Label_{name}");
            labelGo.transform.SetParent(glowGo.transform, false);
            cd.label = labelGo.AddComponent<Text>();
            cd.label.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            cd.label.fontSize = (int)labelSize;
            cd.label.alignment = TextAnchor.MiddleCenter;
            cd.label.horizontalOverflow = HorizontalWrapMode.Overflow;
            cd.label.verticalOverflow = VerticalWrapMode.Overflow;
            cd.label.text = label;
            cd.label.raycastTarget = false;

            var labelRt = labelGo.GetComponent<RectTransform>();
            labelRt.anchorMin = pivot;
            labelRt.anchorMax = pivot;
            labelRt.pivot = new Vector2(0.5f, 0.5f);
            float labelYOffset = numYOffset + numberSize + 4f;
            labelRt.anchoredPosition = new Vector2(
                pivot.x == 0 ? iconOffsetFromCorner : -iconOffsetFromCorner,
                pivot.y == 0 ? labelYOffset : -labelYOffset
            );
            labelRt.sizeDelta = new Vector2(iconSize * 3, labelSize * 2);

            return cd;
        }

        // ── Bottom metrics bar — pipeline stage segments ──

        private void CreateBottomMetricsBar()
        {
            // Background strip
            var barGo = new GameObject("MetricsBar");
            barGo.transform.SetParent(_canvas.transform, false);
            _barBg = barGo.AddComponent<Image>();
            _barBg.color = new Color(0.02f, 0.04f, 0.08f, barAlpha);
            _barBg.raycastTarget = false;

            var barRt = barGo.GetComponent<RectTransform>();
            barRt.anchorMin = new Vector2(0.5f, 0f);
            barRt.anchorMax = new Vector2(0.5f, 0f);
            barRt.pivot = new Vector2(0.5f, 0f);
            barRt.sizeDelta = new Vector2(700f, 50f);
            barRt.anchoredPosition = new Vector2(0f, 20f);

            // Segment labels: STT | ROUTER | AI | TTS | VRAM | MEM
            string[] segLabels = { "STT", "ROUTER", "AI", "TTS", "VRAM", "MEM" };
            Color[] segColors =
            {
                new Color(0.3f, 0.95f, 0.45f),  // STT — green
                new Color(0.0f, 0.94f, 1.0f),   // ROUTER — cyan
                new Color(0.85f, 0.15f, 0.85f), // AI — magenta
                new Color(1.0f, 0.4f, 0.9f),    // TTS — pink
                new Color(1.0f, 0.78f, 0.10f),  // VRAM — amber
                new Color(0.5f, 0.7f, 1.0f),    // MEM — blue
            };

            float segWidth = 700f / BAR_SEGMENT_COUNT;
            for (int i = 0; i < BAR_SEGMENT_COUNT; i++)
            {
                // Segment fill bar
                var segGo = new GameObject($"Seg_{segLabels[i]}");
                segGo.transform.SetParent(barGo.transform, false);
                var segImg = segGo.AddComponent<Image>();
                segImg.color = segColors[i] * 0.3f; // dim base
                segImg.raycastTarget = false;

                var segRt = segGo.GetComponent<RectTransform>();
                segRt.anchorMin = new Vector2(0, 0.5f);
                segRt.anchorMax = new Vector2(0, 0.5f);
                segRt.pivot = new Vector2(0, 0.5f);
                segRt.sizeDelta = new Vector2(segWidth - 8f, 8f);
                segRt.anchoredPosition = new Vector2(i * segWidth + 4f, 8f);
                _barSegments.Add(segImg);

                // Segment label
                var labGo = new GameObject($"Lab_{segLabels[i]}");
                labGo.transform.SetParent(barGo.transform, false);
                var labText = labGo.AddComponent<Text>();
                labText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
                labText.fontSize = 11;
                labText.fontStyle = FontStyle.Bold;
                labText.alignment = TextAnchor.MiddleCenter;
                labText.color = segColors[i] * 0.8f;
                labText.text = segLabels[i];
                labText.raycastTarget = false;

                var labRt = labGo.GetComponent<RectTransform>();
                labRt.anchorMin = new Vector2(0, 0.5f);
                labRt.anchorMax = new Vector2(0, 0.5f);
                labRt.pivot = new Vector2(0.5f, 0.5f);
                labRt.sizeDelta = new Vector2(segWidth, 16f);
                labRt.anchoredPosition = new Vector2(i * segWidth + segWidth * 0.5f, -10f);
                _barLabels.Add(labText);
            }
        }

        // ── Breathing ring (subtle, center-top) ──

        private void CreateBreathRing()
        {
            CreateRingTexture();

            var ringGo = new GameObject("BreathRing");
            ringGo.transform.SetParent(_canvas.transform, false);
            _breathRing = ringGo.AddComponent<Image>();
            _breathRing.sprite = Sprite.Create(_ringTex, new Rect(0, 0, 128, 128), Vector2.one * 0.5f);
            _breathRing.type = Image.Type.Simple;
            _breathRing.raycastTarget = false;

            var ringRt = ringGo.GetComponent<RectTransform>();
            ringRt.anchorMin = new Vector2(0.5f, 1f);
            ringRt.anchorMax = new Vector2(0.5f, 1f);
            ringRt.pivot = new Vector2(0.5f, 0.5f);
            ringRt.sizeDelta = new Vector2(120f, 120f);
            ringRt.anchoredPosition = new Vector2(0f, -80f);
        }

        // ── Events ──

        private void SubscribeEvents()
        {
            if (wsClient == null) return;
            wsClient.OnChatTextReceived += OnChatActivity;
            wsClient.OnEmotionReceived += OnEmotion;
            wsClient.OnAudioDataReceived += OnTTSActivity;
        }

        private void OnChatActivity(string text) { _lastActivity = Time.time; _isSpeaking = true; _isListening = false; }
        private void OnEmotion(string emotion, float intensity) { _emotion = emotion; _emotionIntensity = intensity; _lastActivity = Time.time; }
        private void OnTTSActivity(byte[] audio) { _lastActivity = Time.time; _isSpeaking = true; }

        // ── Update ──

        private void Update()
        {
            // FPS
            _fpsAccum += Time.unscaledDeltaTime;
            _fpsFrames++;
            if (_fpsAccum >= 0.5f)
            {
                _fps = _fpsFrames / _fpsAccum;
                _fpsAccum = 0;
                _fpsFrames = 0;
            }

            if (wsClient != null)
                _isConnected = wsClient.IsConnected;

            // Activity fade
            float timeSinceActivity = Time.time - _lastActivity;
            bool isActive = timeSinceActivity < activityFadeDuration;
            float targetPeak = isActive ? peakAlpha : idlePeakAlpha;
            float currentPeak = Mathf.Lerp(GetCurrentPeak(), targetPeak, Time.deltaTime * 2f);

            // Color cycling
            float cycleT = (Time.time % cyclePeriod) / cyclePeriod;
            for (int i = 0; i < 4; i++)
            {
                float cornerPhase = (cycleT + i * 0.25f) % 1f;
                _corners[i].baseColor = SampleCycledColor(cornerPhase);
            }

            // Apply colors + alpha with pulse
            float pulse = isActive ? (0.85f + 0.15f * Mathf.Sin(Time.time * 4f)) : 1f;
            for (int i = 0; i < 4; i++)
            {
                if (_corners[i].glow != null)
                {
                    Color c = _corners[i].baseColor;
                    c.a = currentPeak * pulse;
                    _corners[i].glow.color = c;
                }

                Color iconCol = _corners[i].baseColor * 1.4f;
                iconCol.a = iconAlpha;
                if (_corners[i].icon != null) _corners[i].icon.color = iconCol;
                if (_corners[i].number != null) _corners[i].number.color = iconCol;
                if (_corners[i].label != null)
                {
                    Color labCol = _corners[i].baseColor * 0.6f;
                    labCol.a = iconAlpha * 0.7f;
                    _corners[i].label.color = labCol;
                }
            }

            // Update metrics
            UpdateMetrics();
            UpdateBottomBar();
            UpdateBreathRing();

            // Position canvas
            PositionCanvas();

            // Decay states
            if (timeSinceActivity > 2f) _isSpeaking = false;

            // Animate activity levels
            _sttLevel = Mathf.Lerp(_sttLevel, _isListening ? 0.8f : 0.05f, Time.deltaTime * 5f);
            _ttsLevel = Mathf.Lerp(_ttsLevel, _isSpeaking ? 0.7f : 0.03f, Time.deltaTime * 5f);
            _aiLevel  = Mathf.Lerp(_aiLevel,  _isSpeaking ? 0.6f : 0.04f, Time.deltaTime * 3f);
        }

        private Color SampleCycledColor(float phase)
        {
            float scaled = phase * 4f;
            int idx = Mathf.FloorToInt(scaled) % 4;
            int nextIdx = (idx + 1) % 4;
            float t = scaled - Mathf.Floor(scaled);
            t = t * t * (3f - 2f * t);
            return Color.Lerp(Palette[idx], Palette[nextIdx], t);
        }

        private float GetCurrentPeak()
        {
            if (_corners[0].glow == null) return idlePeakAlpha;
            return _corners[0].glow.color.a;
        }

        // ── Metrics per corner ──

        private void UpdateMetrics()
        {
            // TL: LINK — connection status + latency
            if (_corners[(int)Corner.TL].number != null)
            {
                _corners[(int)Corner.TL].number.text = _isConnected
                    ? (_latencyMs > 0 ? $"{_latencyMs}ms" : "ON")
                    : "OFF";
            }

            // TR: FPS
            if (_corners[(int)Corner.TR].number != null)
                _corners[(int)Corner.TR].number.text = $"{_fps:F0}";

            // BL: MOOD — emotion + intensity
            if (_corners[(int)Corner.BL].number != null)
            {
                if (_emotionIntensity > 0.01f)
                {
                    int pct = Mathf.RoundToInt(_emotionIntensity * 100f);
                    _corners[(int)Corner.BL].number.text = $"{_emotion.Substring(0, Mathf.Min(4, _emotion.Length)).ToUpper()} {pct}%";
                }
                else
                    _corners[(int)Corner.BL].number.text = "IDLE";
            }

            // BR: FLOW — combined pipeline activity
            if (_corners[(int)Corner.BR].number != null)
            {
                float combined = (_sttLevel + _ttsLevel + _aiLevel) / 3f;
                _corners[(int)Corner.BR].number.text = $"{Mathf.RoundToInt(combined * 100)}%";
            }
        }

        // ── Bottom bar — pipeline stage fills ──

        private void UpdateBottomBar()
        {
            // STT, ROUTER, AI, TTS, VRAM, MEM
            float[] levels =
            {
                _sttLevel,                              // STT
                _isSpeaking ? 0.4f : 0.1f,              // ROUTER (router always warm)
                _aiLevel,                               // AI
                _ttsLevel,                              // TTS
                _vramPct,                               // VRAM
                Mathf.Clamp01(_memoryTurns / 50f),      // MEM (turns / 50 as fill)
            };

            for (int i = 0; i < _barSegments.Count && i < levels.Length; i++)
            {
                float level = levels[i];
                float pulseAmt = level > 0.2f ? (0.8f + 0.2f * Mathf.Sin(Time.time * barPulseSpeed * 3f)) : 1f;
                Color c = _barSegments[i].color;
                // Brighten with level
                float brightness = 0.3f + level * 0.7f * pulseAmt;
                _barSegments[i].color = new Color(c.r, c.g, c.b, brightness * barAlpha * 2f);
                // Scale segment width by level
                var rt = _barSegments[i].rectTransform;
                float baseW = (700f / BAR_SEGMENT_COUNT) - 8f;
                rt.sizeDelta = new Vector2(baseW * Mathf.Max(0.1f, level), 8f);
            }

            // Update memory label with turn count
            if (_barLabels.Count >= 6)
                _barLabels[5].text = $"MEM {_memoryTurns}";
        }

        // ── Breathing ring animation ──

        private void UpdateBreathRing()
        {
            _breathPhase += Time.deltaTime * 0.8f;
            float breath = 0.5f + 0.5f * Mathf.Sin(_breathPhase);

            // Scale breathes
            float scale = 0.8f + breath * 0.4f;
            _breathRing.rectTransform.localScale = Vector3.one * scale;

            // Color shifts with emotion
            Color ringCol = EmotionToColor(_emotion);
            ringCol.a = 0.06f + breath * 0.08f;
            _breathRing.color = ringCol;
        }

        private Color EmotionToColor(string emotion)
        {
            switch (emotion.ToLowerInvariant())
            {
                case "happy":
                case "joy":
                case "excited":
                    return new Color(1f, 0.85f, 0.2f);
                case "angry":
                case "frustrated":
                    return new Color(1f, 0.2f, 0.2f);
                case "sad":
                case "sorrow":
                    return new Color(0.3f, 0.5f, 1f);
                case "surprised":
                case "shocked":
                    return new Color(1f, 0.5f, 1f);
                case "thinking":
                    return new Color(0.3f, 0.9f, 1f);
                case "relaxed":
                case "calm":
                    return new Color(0.3f, 0.95f, 0.45f);
                default:
                    return new Color(0.5f, 0.7f, 1f);
            }
        }

        // ── Canvas positioning ──

        private void PositionCanvas()
        {
            if (Camera.main == null || _canvas == null) return;
            Transform cam = Camera.main.transform;

            Vector3 forward = cam.forward;
            forward.y = 0;
            if (forward.sqrMagnitude < 0.01f) forward = cam.forward;
            forward.Normalize();

            Vector3 targetPos = cam.position + forward * distance;
            _canvas.transform.position = Vector3.Lerp(_canvas.transform.position, targetPos, Time.deltaTime * smoothSpeed);
            _canvas.transform.LookAt(cam);
            _canvas.transform.Rotate(0, 180, 0);
        }

        // ── Public API ──

        public void SetListening(bool listening)
        {
            _isListening = listening;
            if (listening) _lastActivity = Time.time;
        }

        public void SetLatency(int ms) => _latencyMs = ms;

        public void SetVRAM(float pct) => _vramPct = Mathf.Clamp01(pct);

        public void SetContextUsage(float pct) => _contextPct = Mathf.Clamp01(pct);

        public void SetMemoryTurns(int turns) => _memoryTurns = turns;

        public void UpdateContext(string context) { }
    }
}
