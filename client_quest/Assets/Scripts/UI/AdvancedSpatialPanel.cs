using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;
using TMPro;
using FoveAI.IPC;

namespace FoveAI.UI
{
    /// <summary>
    /// Advanced multi-mode spatial panel — grabbable, placeable in the room.
    /// Modes:
    ///   1. Chat — conversation transcript with Alice
    ///   2. Browser — renders HTML content served by the backend (rich text)
    ///   3. Dev — system diagnostics, logs, model info
    ///
    /// The backend can push HTML-like content (TMP rich text supported tags)
    /// to the panel via WebSocket events: panel.html, panel.dev, panel.chat
    ///
    /// Grip to grab/move. Tab buttons at top to switch modes.
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class AdvancedSpatialPanel : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient webSocketClient;

        [Header("Panel Settings")]
        [SerializeField] private float panelWidth = 800f;
        [SerializeField] private float panelHeight = 600f;
        [Range(0f, 1f)] public float panelAlpha = 0.92f;
        [SerializeField] private int fontSize = 22;

        [Header("Colors")]
        [SerializeField] private Color bgColor = new Color(0.04f, 0.06f, 0.10f, 0.92f);
        [SerializeField] private Color tabColor = new Color(0.12f, 0.15f, 0.22f, 1f);
        [SerializeField] private Color tabActiveColor = new Color(0.15f, 0.35f, 0.55f, 1f);
        [SerializeField] private Color textColor = new Color(0.88f, 0.92f, 0.98f, 1f);
        [SerializeField] private Color accentColor = new Color(0.3f, 0.7f, 1f, 1f);

        // ── Internal ──
        private Canvas _canvas;
        private CanvasGroup _canvasGroup;
        private TMP_FontAsset _font;
        private enum Mode { Chat, Browser, Dev }
        private Mode _currentMode = Mode.Chat;

        // UI elements
        private GameObject _tabBar;
        private Button _chatTab, _browserTab, _devTab;
        private Image _chatTabBg, _browserTabBg, _devTabBg;
        private TMP_Text _contentText;
        private ScrollRect _scrollRect;
        private Image _contentBg;

        // Chat state
        private readonly StringBuilder _chatBuffer = new StringBuilder();
        private int _maxChatLines = 30;

        // Browser state
        private string _currentUrl = "";
        private string _browserContent = "<size=28><b>Browser</b></size>\n<size=18><i>Grip to move panel. Tab to switch modes.</i></size>";

        // Dev state
        private string _devContent = "<size=28><b>System Diagnostics</b></size>\n<size=18>Waiting for backend...</size>";
        private float _devRefreshTimer = 0f;
        private float _devRefreshInterval = 5f;

        private void Awake()
        {
            _font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            if (_font == null)
                _font = TMP_Settings.defaultFontAsset;

            _canvas = GetComponent<Canvas>();
            _canvas.renderMode = RenderMode.WorldSpace;
            var rt = GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(panelWidth, panelHeight);
            rt.localScale = Vector3.one * 0.0015f;

            _canvasGroup = GetComponent<CanvasGroup>();
            if (_canvasGroup == null)
                _canvasGroup = gameObject.AddComponent<CanvasGroup>();
            _canvasGroup.alpha = panelAlpha;

            // Add grabbable behavior
            if (GetComponent<GrabbablePanel>() == null)
                gameObject.AddComponent<GrabbablePanel>();

            if (webSocketClient == null)
                webSocketClient = FindAnyObjectByType<FoveAIWebSocketClient>();

            BuildUI();
        }

        private void OnEnable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnChatTextReceived += OnChatReceived;
                webSocketClient.OnRawMessageReceived += OnRawMessage;
            }
        }

        private void OnDisable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnChatTextReceived -= OnChatReceived;
                webSocketClient.OnRawMessageReceived -= OnRawMessage;
            }
        }

        // ── UI Construction ──

        private void BuildUI()
        {
            // Background
            var bgGo = new GameObject("PanelBg");
            bgGo.transform.SetParent(transform, false);
            _contentBg = bgGo.AddComponent<Image>();
            _contentBg.color = bgColor;
            var bgRt = bgGo.GetComponent<RectTransform>();
            bgRt.anchorMin = Vector2.zero;
            bgRt.anchorMax = Vector2.one;
            bgRt.offsetMin = Vector2.zero;
            bgRt.offsetMax = Vector2.zero;

            // Tab bar
            _tabBar = new GameObject("TabBar");
            _tabBar.transform.SetParent(transform, false);
            var tabBarImg = _tabBar.AddComponent<Image>();
            tabBarImg.color = new Color(0.03f, 0.04f, 0.07f, 1f);
            var tabBarRt = _tabBar.GetComponent<RectTransform>();
            tabBarRt.anchorMin = new Vector2(0, 1);
            tabBarRt.anchorMax = new Vector2(1, 1);
            tabBarRt.sizeDelta = new Vector2(0, 50f);
            tabBarRt.offsetMin = Vector2.zero;
            tabBarRt.offsetMax = Vector2.zero;

            // Tab buttons
            _chatTab = CreateTabButton("ChatTab", "CHAT", 0, out _chatTabBg);
            _browserTab = CreateTabButton("BrowserTab", "BROWSER", 1, out _browserTabBg);
            _devTab = CreateTabButton("DevTab", "DEV", 2, out _devTabBg);

            _chatTab.onClick.AddListener(() => SwitchMode(Mode.Chat));
            _browserTab.onClick.AddListener(() => SwitchMode(Mode.Browser));
            _devTab.onClick.AddListener(() => SwitchMode(Mode.Dev));

            // Scroll view + content
            CreateScrollAndContent();

            // Event system
            if (UnityEngine.EventSystems.EventSystem.current == null)
            {
                var es = new GameObject("EventSystem");
                es.AddComponent<UnityEngine.EventSystems.EventSystem>();
                es.AddComponent<UnityEngine.InputSystem.UI.InputSystemUIInputModule>();
            }

            UpdateTabColors();
            UpdateContent();
        }

        private Button CreateTabButton(string name, string label, int index, out Image bg)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_tabBar.transform, false);
            bg = go.AddComponent<Image>();
            bg.color = tabColor;
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = bg;

            var rt = go.GetComponent<RectTransform>();
            float tabWidth = panelWidth / 3f;
            rt.anchorMin = new Vector2(0, 0);
            rt.anchorMax = new Vector2(0, 1);
            rt.sizeDelta = new Vector2(tabWidth - 4, 0);
            rt.anchoredPosition = new Vector2(index * tabWidth + 2, 0);

            var labelGo = new GameObject("Label");
            labelGo.transform.SetParent(go.transform, false);
            var labelTxt = labelGo.AddComponent<TextMeshProUGUI>();
            labelTxt.font = _font;
            labelTxt.fontSize = fontSize;
            labelTxt.color = textColor;
            labelTxt.text = label;
            labelTxt.alignment = TextAlignmentOptions.Center;
            var labelRt = labelGo.GetComponent<RectTransform>();
            labelRt.anchorMin = Vector2.zero;
            labelRt.anchorMax = Vector2.one;
            labelRt.offsetMin = Vector2.zero;
            labelRt.offsetMax = Vector2.zero;

            return btn;
        }

        private void CreateScrollAndContent()
        {
            // Scroll View
            var scrollGo = new GameObject("ScrollView");
            scrollGo.transform.SetParent(transform, false);
            _scrollRect = scrollGo.AddComponent<ScrollRect>();
            var scrollRt = scrollGo.GetComponent<RectTransform>();
            scrollRt.anchorMin = new Vector2(0, 0);
            scrollRt.anchorMax = new Vector2(1, 1);
            scrollRt.offsetMin = new Vector2(8, 8);
            scrollRt.offsetMax = new Vector2(-8, -58);

            var scrollImg = scrollGo.AddComponent<Image>();
            scrollImg.color = new Color(0.02f, 0.03f, 0.05f, 0.5f);

            // Viewport
            var viewportGo = new GameObject("Viewport");
            viewportGo.transform.SetParent(scrollGo.transform, false);
            var viewportImg = viewportGo.AddComponent<Image>();
            viewportImg.color = Color.clear;
            var viewportMask = viewportGo.AddComponent<RectMask2D>();
            var viewportRt = viewportGo.GetComponent<RectTransform>();
            viewportRt.anchorMin = Vector2.zero;
            viewportRt.anchorMax = Vector2.one;
            viewportRt.offsetMin = Vector2.zero;
            viewportRt.offsetMax = Vector2.zero;
            _scrollRect.viewport = viewportRt;

            // Content
            var contentGo = new GameObject("Content");
            contentGo.transform.SetParent(viewportGo.transform, false);
            _contentText = contentGo.AddComponent<TextMeshProUGUI>();
            _contentText.font = _font;
            _contentText.fontSize = fontSize;
            _contentText.color = textColor;
            _contentText.richText = true;
            _contentText.alignment = TextAlignmentOptions.TopLeft;
            _contentText.enableWordWrapping = true;
            var contentRt = contentGo.GetComponent<RectTransform>();
            contentRt.anchorMin = new Vector2(0, 1);
            contentRt.anchorMax = new Vector2(1, 1);
            contentRt.pivot = new Vector2(0.5f, 1);
            contentRt.offsetMin = new Vector2(12, 0);
            contentRt.offsetMax = new Vector2(-12, 0);
            _scrollRect.content = contentRt;

            // Auto-scroll to bottom
            _scrollRect.vertical = true;
            _scrollRect.horizontal = false;
            _scrollRect.scrollSensitivity = 20f;
        }

        // ── Mode Switching ──

        private void SwitchMode(Mode mode)
        {
            _currentMode = mode;
            UpdateTabColors();
            UpdateContent();
        }

        private void UpdateTabColors()
        {
            _chatTabBg.color = _currentMode == Mode.Chat ? tabActiveColor : tabColor;
            _browserTabBg.color = _currentMode == Mode.Browser ? tabActiveColor : tabColor;
            _devTabBg.color = _currentMode == Mode.Dev ? tabActiveColor : tabColor;
        }

        private void UpdateContent()
        {
            switch (_currentMode)
            {
                case Mode.Chat:
                    _contentText.text = _chatBuffer.ToString();
                    Canvas.ForceUpdateCanvases();
                    _scrollRect.verticalNormalizedPosition = 0f;
                    break;
                case Mode.Browser:
                    _contentText.text = _browserContent;
                    break;
                case Mode.Dev:
                    _contentText.text = _devContent;
                    break;
            }
        }

        // ── Event Handlers ──

        private void OnChatReceived(string text)
        {
            string line = $"<color=#00ffff><b>You:</b></color> {text}\n";
            // We don't have user messages here — only Alice's responses
            // The actual chat display is handled by SpatialUIManager
            // This is a secondary view
        }

        public void AppendChatLine(string speaker, string text)
        {
            string color = speaker == "Alice" ? "#ff88ff" : "#00ffff";
            string line = $"<color={color}><b>{speaker}:</b></color> {text}\n";
            _chatBuffer.Append(line);

            // Trim if too long
            var lines = _chatBuffer.ToString().Split('\n');
            if (lines.Length > _maxChatLines)
            {
                _chatBuffer.Clear();
                for (int i = lines.Length - _maxChatLines; i < lines.Length; i++)
                    _chatBuffer.AppendLine(lines[i]);
            }

            if (_currentMode == Mode.Chat)
                UpdateContent();
        }

        private void OnRawMessage(string json)
        {
            // Check for panel-specific events
            if (json.Contains("\"panel.html\""))
            {
                string html = ExtractField(json, "html");
                if (!string.IsNullOrEmpty(html))
                {
                    _browserContent = ConvertHtmlToTmp(html);
                    if (_currentMode == Mode.Browser) UpdateContent();
                }
            }
            else if (json.Contains("\"panel.dev\""))
            {
                string dev = ExtractField(json, "content");
                if (!string.IsNullOrEmpty(dev))
                {
                    _devContent = dev;
                    if (_currentMode == Mode.Dev) UpdateContent();
                }
            }
            else if (json.Contains("\"chat.response\""))
            {
                string text = ExtractField(json, "text");
                if (!string.IsNullOrEmpty(text))
                    AppendChatLine("Alice", text);
            }
        }

        // ── HTML to TMP Rich Text Conversion ──

        /// <summary>
        /// Convert basic HTML to TMP rich text tags.
        /// Supports: b, i, u, h1-h3, p, br, color, size, a, code, ul, li
        /// </summary>
        private string ConvertHtmlToTmp(string html)
        {
            if (string.IsNullOrEmpty(html)) return "";

            string result = html;

            // Headings
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<h1[^>]*>(.*?)</h1>", "<size=36><b>$1</b></size>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<h2[^>]*>(.*?)</h2>", "<size=30><b>$1</b></size>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<h3[^>]*>(.*?)</h3>", "<size=26><b>$1</b></size>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Bold, italic, underline
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<b[^>]*>(.*?)</b>", "<b>$1</b>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<strong[^>]*>(.*?)</strong>", "<b>$1</b>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<i[^>]*>(.*?)</i>", "<i>$1</i>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<em[^>]*>(.*?)</em>", "<i>$1</i>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<u[^>]*>(.*?)</u>", "<u>$1</u>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Code blocks
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<code[^>]*>(.*?)</code>", "<color=#88ccff><font=\"LiberationMono SDF\">$1</font></color>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<pre[^>]*>(.*?)</pre>", "<color=#88ccff><font=\"LiberationMono SDF\">$1</font></color>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);

            // Links — show as colored text (can't navigate in VR)
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<a[^>]*href=[""']([^""']*)[""'][^>]*>(.*?)</a>", "<color=#44aaff><u>$2</u></color> [$1]", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Color spans
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<span[^>]*color:\s*(#[0-9a-fA-F]{6})[^>]*>(.*?)</span>", "<color=$1>$2</color>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Size
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<span[^>]*font-size:\s*(\d+)px[^>]*>(.*?)</span>", "<size=$1>$2</size>", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Line breaks and paragraphs
            result = result.Replace("<br>", "\n").Replace("<br/>", "\n").Replace("<br />", "\n");
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<p[^>]*>", "\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = result.Replace("</p>", "\n");

            // List items
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<li[^>]*>", "  • ", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = result.Replace("</li>", "\n");
            result = System.Text.RegularExpressions.Regex.Replace(result, @"</?ul[^>]*>", "\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"</?ol[^>]*>", "\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Divs → newlines
            result = System.Text.RegularExpressions.Regex.Replace(result, @"</div>", "\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Strip remaining tags
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<[^>]+>", "", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Decode HTML entities
            result = result.Replace("&nbsp;", " ").Replace("&amp;", "&").Replace("&lt;", "<").Replace("&gt;", ">").Replace("&quot;", "\"");

            return result.Trim();
        }

        // ── Dev Mode ──

        private void Update()
        {
            if (_currentMode == Mode.Dev)
            {
                _devRefreshTimer += Time.deltaTime;
                if (_devRefreshTimer >= _devRefreshInterval)
                {
                    _devRefreshTimer = 0f;
                    RefreshDevInfo();
                }
            }
        }

        private void RefreshDevInfo()
        {
            if (webSocketClient == null) return;

            bool connected = webSocketClient.IsConnected;
            string status = connected ? "<color=#44ff88>ONLINE</color>" : "<color=#ff4444>OFFLINE</color>";

            _devContent = $"<size=30><b>System Diagnostics</b></size>\n\n" +
                $"<b>Backend:</b> {status}\n" +
                $"<b>WebSocket:</b> {(connected ? "Connected" : "Disconnected")}\n" +
                $"<b>STT:</b> faster-whisper (CPU)\n" +
                $"<b>TTS:</b> Kokoro-82M\n" +
                $"<b>Model:</b> Gemma-4-E2B (XRLF)\n" +
                $"<b>FPS:</b> {1f / Time.deltaTime:F0}\n" +
                $"\n<size=20><i>Auto-refresh every {_devRefreshInterval:F0}s</i></size>";

            UpdateContent();
        }

        // ── Browser Navigation ──

        public void NavigateTo(string url)
        {
            _currentUrl = url;
            StartCoroutine(FetchHtmlContent(url));
        }

        private IEnumerator FetchHtmlContent(string url)
        {
            _browserContent = $"<size=22><i>Loading {url}...</i></size>";
            UpdateContent();

            using (UnityWebRequest req = UnityWebRequest.Get(url))
            {
                yield return req.SendWebRequest();
                if (req.result == UnityWebRequest.Result.Success)
                {
                    _browserContent = ConvertHtmlToTmp(req.downloadHandler.text);
                }
                else
                {
                    _browserContent = $"<color=#ff4444><b>Error:</b></color> {req.error}";
                }
                UpdateContent();
            }
        }

        // ── Helpers ──

        private string ExtractField(string json, string field)
        {
            string key = "\"" + field + "\":\"";
            int idx = json.IndexOf(key);
            if (idx == -1) return null;
            int start = idx + key.Length;
            int end = json.IndexOf("\"", start);
            if (end == -1) return null;
            return json.Substring(start, end - start);
        }

        // ── Public API ──

        public void SetBrowserContent(string html)
        {
            _browserContent = ConvertHtmlToTmp(html);
            if (_currentMode == Mode.Browser) UpdateContent();
        }

        public void SetDevContent(string content)
        {
            _devContent = content;
            if (_currentMode == Mode.Dev) UpdateContent();
        }
    }
}
