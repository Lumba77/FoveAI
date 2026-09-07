using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;
using UnityEngine.Video;
using TMPro;

namespace FoveAI.UI
{
    /// <summary>
    /// VR Browser Panel — a grabbable world-space panel that can:
    ///   • Play movies (stream video from URL to RenderTexture)
    ///   • Play music (stream audio from URL)
    ///   • Browse websites (fetch + render simplified HTML)
    ///   • Show YouTube via backend proxy extraction
    ///
    /// Uses Unity's VideoPlayer for video, AudioSource for music,
    /// and TMP rich text for web content rendering.
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class VRBrowserPanel : MonoBehaviour
    {
        [Header("Panel Settings")]
        [SerializeField] private float panelWidth = 960f;
        [SerializeField] private float panelHeight = 540f; // 16:9
        [Range(0f, 1f)] public float panelAlpha = 0.95f;

        [Header("Video Settings")]
        [Tooltip("Video player for movie streaming.")]
        [SerializeField] private VideoPlayer videoPlayer;
        [Tooltip("RawImage that displays the video texture.")]
        [SerializeField] private RawImage videoDisplay;
        [Tooltip("AudioSource for video audio.")]
        [SerializeField] private AudioSource videoAudio;

        [Header("Music Settings")]
        [Tooltip("AudioSource for music streaming.")]
        [SerializeField] private AudioSource musicAudio;

        [Header("Colors")]
        [SerializeField] private Color bgColor = new Color(0.03f, 0.04f, 0.06f, 0.95f);
        [SerializeField] private Color barColor = new Color(0.05f, 0.07f, 0.10f, 1f);
        [SerializeField] private Color buttonColor = new Color(0.15f, 0.20f, 0.30f, 1f);
        [SerializeField] private Color buttonHoverColor = new Color(0.25f, 0.35f, 0.50f, 1f);
        [SerializeField] private Color textColor = new Color(0.88f, 0.92f, 0.98f, 1f);
        [SerializeField] private Color accentColor = new Color(0.3f, 0.7f, 1f, 1f);

        // ── Internal ──
        private Canvas _canvas;
        private CanvasGroup _canvasGroup;
        private TMP_FontAsset _font;

        // UI elements
        private TMP_Text _urlBar;
        private TMP_InputField _urlInput;
        private Button _backBtn, _playBtn, _stopBtn, _modeBtn;
        private TMP_Text _playLabel, _modeLabel;
        private RawImage _videoSurface;
        private TMP_Text _webContent;
        private ScrollRect _scrollRect;
        private Image _loadingIndicator;
        private Slider _progressBar;
        private TMP_Text _statusText;

        // State
        private enum Mode { Video, Music, Web }
        private Mode _currentMode = Mode.Web;
        private string _currentUrl = "";
        private RenderTexture _videoTexture;
        private bool _isPlaying;
        private bool _isPaused;

        // ── Lifecycle ──

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

            BuildUI();
            SetupVideoPlayer();
        }

        // ── UI Construction ──

        private void BuildUI()
        {
            // Background
            var bgGo = new GameObject("BrowserBg");
            bgGo.transform.SetParent(transform, false);
            var bgImg = bgGo.AddComponent<Image>();
            bgImg.color = bgColor;
            var bgRt = bgGo.GetComponent<RectTransform>();
            bgRt.anchorMin = Vector2.zero;
            bgRt.anchorMax = Vector2.one;
            bgRt.offsetMin = Vector2.zero;
            bgRt.offsetMax = Vector2.zero;

            // Top bar (URL + controls)
            CreateTopBar();

            // Content area
            CreateContentArea();

            // Bottom bar (status + progress)
            CreateBottomBar();

            // Event system
            if (UnityEngine.EventSystems.EventSystem.current == null)
            {
                var es = new GameObject("EventSystem");
                es.AddComponent<UnityEngine.EventSystems.EventSystem>();
                es.AddComponent<UnityEngine.InputSystem.UI.InputSystemUIInputModule>();
            }
        }

        private void CreateTopBar()
        {
            var barGo = new GameObject("TopBar");
            barGo.transform.SetParent(transform, false);
            var barImg = barGo.AddComponent<Image>();
            barImg.color = barColor;
            var barRt = barGo.GetComponent<RectTransform>();
            barRt.anchorMin = new Vector2(0, 1);
            barRt.anchorMax = new Vector2(1, 1);
            barRt.sizeDelta = new Vector2(0, 50f);
            barRt.offsetMin = Vector2.zero;
            barRt.offsetMax = Vector2.zero;

            // Back button
            _backBtn = CreateButton("Back", "◀", barGo.transform, new Vector2(10, 0), 40f);
            _backBtn.onClick.AddListener(OnBack);

            // URL input
            var urlGo = new GameObject("UrlInput");
            urlGo.transform.SetParent(barGo.transform, false);
            var urlImg = urlGo.AddComponent<Image>();
            urlImg.color = new Color(0.08f, 0.10f, 0.14f, 1f);
            var urlRt = urlGo.GetComponent<RectTransform>();
            urlRt.anchorMin = new Vector2(0, 0.5f);
            urlRt.anchorMax = new Vector2(1, 0.5f);
            urlRt.sizeDelta = new Vector2(-200f, 32f);
            urlRt.anchoredPosition = new Vector2(60f, 0);

            _urlInput = urlGo.AddComponent<TMP_InputField>();
            _urlInput.shouldHideMobileInput = false;
            _urlInput.lineType = TMP_InputField.LineType.SingleLine;

            var viewportGo = new GameObject("TextArea", typeof(RectTransform), typeof(RectMask2D));
            viewportGo.transform.SetParent(urlGo.transform, false);
            var viewportRt = viewportGo.GetComponent<RectTransform>();
            viewportRt.anchorMin = Vector2.zero;
            viewportRt.anchorMax = Vector2.one;
            viewportRt.offsetMin = new Vector2(8, 4);
            viewportRt.offsetMax = new Vector2(-8, -4);
            _urlInput.textViewport = viewportRt;

            var inputTextGo = new GameObject("Text");
            inputTextGo.transform.SetParent(viewportGo.transform, false);
            var inputText = inputTextGo.AddComponent<TextMeshProUGUI>();
            inputText.font = _font;
            inputText.fontSize = 18;
            inputText.color = textColor;
            inputText.alignment = TextAlignmentOptions.MidlineLeft;
            var inputTextRt = inputTextGo.GetComponent<RectTransform>();
            inputTextRt.anchorMin = Vector2.zero;
            inputTextRt.anchorMax = Vector2.one;
            inputTextRt.offsetMin = Vector2.zero;
            inputTextRt.offsetMax = Vector2.zero;
            _urlInput.textComponent = inputText;

            var placeholderGo = new GameObject("Placeholder");
            placeholderGo.transform.SetParent(viewportGo.transform, false);
            var placeholder = placeholderGo.AddComponent<TextMeshProUGUI>();
            placeholder.font = _font;
            placeholder.fontSize = 16;
            placeholder.color = new Color(1, 1, 1, 0.4f);
            placeholder.text = "Enter URL or search...";
            placeholder.alignment = TextAlignmentOptions.MidlineLeft;
            var phRt = placeholderGo.GetComponent<RectTransform>();
            phRt.anchorMin = Vector2.zero;
            phRt.anchorMax = Vector2.one;
            phRt.offsetMin = Vector2.zero;
            phRt.offsetMax = Vector2.zero;
            _urlInput.placeholder = placeholder;

            _urlInput.onEndEdit.AddListener(OnUrlSubmit);

            // Play/Pause button
            _playBtn = CreateButton("Play", "▶", barGo.transform, new Vector2(-110, 0), 40f);
            _playLabel = _playBtn.GetComponentInChildren<TextMeshProUGUI>();
            _playBtn.onClick.AddListener(OnPlayPause);

            // Mode toggle
            _modeBtn = CreateButton("Mode", "WEB", barGo.transform, new Vector2(-60, 0), 50f);
            _modeLabel = _modeBtn.GetComponentInChildren<TextMeshProUGUI>();
            _modeBtn.onClick.AddListener(CycleMode);

            // Bookmark bar — quick links to key pages
            CreateBookmarkBar();
        }

        private void CreateBookmarkBar()
        {
            var barGo = new GameObject("BookmarkBar");
            barGo.transform.SetParent(transform, false);
            var barImg = barGo.AddComponent<Image>();
            barImg.color = new Color(0.04f, 0.05f, 0.08f, 1f);
            var barRt = barGo.GetComponent<RectTransform>();
            barRt.anchorMin = new Vector2(0, 1);
            barRt.anchorMax = new Vector2(1, 1);
            barRt.sizeDelta = new Vector2(0, 36f);
            barRt.offsetMin = new Vector2(0, -86f);
            barRt.offsetMax = new Vector2(0, -50f);

            // Bookmarks: (label, url, mode)
            var bookmarks = new (string label, string url, Mode mode)[]
            {
                ("🧠 Memory", $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:8201/memory", Mode.Web),
                ("⚙ Settings", $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:8201/settings.html", Mode.Web),
                ("📊 Status", $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:8402/api/health", Mode.Web),
                ("🎬 YouTube", "https://www.youtube.com", Mode.Video),
                ("🎵 Music", "https://cdn.pixabay.com/audio/2024/03/15/audio_1f4e8d2e3f.mp3", Mode.Music),
            };

            float x = 10f;
            foreach (var bm in bookmarks)
            {
                var btn = CreateBookmarkButton(bm.label, barGo.transform, new Vector2(x, 0));
                string url = bm.url;
                Mode mode = bm.mode;
                btn.onClick.AddListener(() => OpenBookmark(url, mode));
                x += 130f;
            }
        }

        private Button CreateBookmarkButton(string label, Transform parent, Vector2 pos)
        {
            var go = new GameObject($"BM_{label}");
            go.transform.SetParent(parent, false);
            var img = go.AddComponent<Image>();
            img.color = new Color(0.10f, 0.14f, 0.22f, 1f);
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;

            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 0.5f);
            rt.anchorMax = new Vector2(0, 0.5f);
            rt.sizeDelta = new Vector2(120f, 28f);
            rt.anchoredPosition = pos;

            var labelGo = new GameObject("Label");
            labelGo.transform.SetParent(go.transform, false);
            var labelTxt = labelGo.AddComponent<TextMeshProUGUI>();
            labelTxt.font = _font;
            labelTxt.fontSize = 14;
            labelTxt.color = new Color(0.7f, 0.8f, 1f, 1f);
            labelTxt.text = label;
            labelTxt.alignment = TextAlignmentOptions.Center;
            var labelRt = labelGo.GetComponent<RectTransform>();
            labelRt.anchorMin = Vector2.zero;
            labelRt.anchorMax = Vector2.one;
            labelRt.offsetMin = Vector2.zero;
            labelRt.offsetMax = Vector2.zero;

            return btn;
        }

        private void OpenBookmark(string url, Mode mode)
        {
            _currentMode = mode;
            _modeLabel.text = mode.ToString().ToUpper();
            _currentUrl = url;
            if (_urlInput != null) _urlInput.text = url;
            NavigateToUrl(url);
        }

        private void CreateContentArea()
        {
            // Content container
            var contentGo = new GameObject("ContentArea");
            contentGo.transform.SetParent(transform, false);
            var contentRt = contentGo.GetComponent<RectTransform>();
            contentRt.anchorMin = new Vector2(0, 0.1f);
            contentRt.anchorMax = new Vector2(1, 0.89f);
            contentRt.offsetMin = Vector2.zero;
            contentRt.offsetMax = Vector2.zero;

            // Video surface (RawImage for video)
            var videoGo = new GameObject("VideoSurface");
            videoGo.transform.SetParent(contentGo.transform, false);
            _videoSurface = videoGo.AddComponent<RawImage>();
            _videoSurface.color = Color.black;
            _videoSurface.enabled = false;
            var videoRt = videoGo.GetComponent<RectTransform>();
            videoRt.anchorMin = Vector2.zero;
            videoRt.anchorMax = Vector2.one;
            videoRt.offsetMin = Vector2.zero;
            videoRt.offsetMax = Vector2.zero;

            // Web content scroll view
            var scrollGo = new GameObject("WebScroll");
            scrollGo.transform.SetParent(contentGo.transform, false);
            _scrollRect = scrollGo.AddComponent<ScrollRect>();
            var scrollRt = scrollGo.GetComponent<RectTransform>();
            scrollRt.anchorMin = Vector2.zero;
            scrollRt.anchorMax = Vector2.one;
            scrollRt.offsetMin = Vector2.zero;
            scrollRt.offsetMax = Vector2.zero;

            var scrollImg = scrollGo.AddComponent<Image>();
            scrollImg.color = new Color(0.02f, 0.03f, 0.05f, 0.5f);

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

            var textContentGo = new GameObject("WebText");
            textContentGo.transform.SetParent(viewportGo.transform, false);
            _webContent = textContentGo.AddComponent<TextMeshProUGUI>();
            _webContent.font = _font;
            _webContent.fontSize = 20;
            _webContent.color = textColor;
            _webContent.richText = true;
            _webContent.alignment = TextAlignmentOptions.TopLeft;
            _webContent.enableWordWrapping = true;
            var textRt = _webContent.GetComponent<RectTransform>();
            textRt.anchorMin = new Vector2(0, 1);
            textRt.anchorMax = new Vector2(1, 1);
            textRt.pivot = new Vector2(0.5f, 1);
            textRt.offsetMin = new Vector2(16, 0);
            textRt.offsetMax = new Vector2(-16, 0);
            _scrollRect.content = textRt;

            // Loading indicator
            var loadGo = new GameObject("Loading");
            loadGo.transform.SetParent(contentGo.transform, false);
            _loadingIndicator = loadGo.AddComponent<Image>();
            _loadingIndicator.color = new Color(accentColor.r, accentColor.g, accentColor.b, 0.8f);
            _loadingIndicator.enabled = false;
            var loadRt = loadGo.GetComponent<RectTransform>();
            loadRt.anchorMin = new Vector2(0.5f, 0.5f);
            loadRt.anchorMax = new Vector2(0.5f, 0.5f);
            loadRt.sizeDelta = new Vector2(200, 4);
            loadRt.anchoredPosition = Vector2.zero;
        }

        private void CreateBottomBar()
        {
            var barGo = new GameObject("BottomBar");
            barGo.transform.SetParent(transform, false);
            var barImg = barGo.AddComponent<Image>();
            barImg.color = barColor;
            var barRt = barGo.GetComponent<RectTransform>();
            barRt.anchorMin = new Vector2(0, 0);
            barRt.anchorMax = new Vector2(1, 0);
            barRt.sizeDelta = new Vector2(0, 36f);
            barRt.offsetMin = Vector2.zero;
            barRt.offsetMax = Vector2.zero;

            // Progress bar
            var progGo = new GameObject("Progress");
            progGo.transform.SetParent(barGo.transform, false);
            _progressBar = progGo.AddComponent<Slider>();
            _progressBar.interactable = false;
            var progRt = progGo.GetComponent<RectTransform>();
            progRt.anchorMin = new Vector2(0, 0.5f);
            progRt.anchorMax = new Vector2(1, 0.5f);
            progRt.sizeDelta = new Vector2(-160f, 8f);
            progRt.anchoredPosition = new Vector2(20f, 0);

            var fillGo = new GameObject("Fill");
            fillGo.transform.SetParent(progGo.transform, false);
            var fillImg = fillGo.AddComponent<Image>();
            fillImg.color = accentColor;
            _progressBar.targetGraphic = fillImg;
            _progressBar.fillRect = fillGo.GetComponent<RectTransform>();
            fillGo.GetComponent<RectTransform>().anchorMin = Vector2.zero;
            fillGo.GetComponent<RectTransform>().anchorMax = Vector2.one;
            fillGo.GetComponent<RectTransform>().offsetMin = Vector2.zero;
            fillGo.GetComponent<RectTransform>().offsetMax = Vector2.zero;

            // Status text
            var statusGo = new GameObject("Status");
            statusGo.transform.SetParent(barGo.transform, false);
            _statusText = statusGo.AddComponent<TextMeshProUGUI>();
            _statusText.font = _font;
            _statusText.fontSize = 14;
            _statusText.color = new Color(0.6f, 0.65f, 0.75f, 1f);
            _statusText.alignment = TextAlignmentOptions.Right;
            var statusRt = statusGo.GetComponent<RectTransform>();
            statusRt.anchorMin = new Vector2(1, 0.5f);
            statusRt.anchorMax = new Vector2(1, 0.5f);
            statusRt.sizeDelta = new Vector2(140, 20);
            statusRt.anchoredPosition = new Vector2(-10, 0);
            _statusText.text = "Ready";
        }

        private Button CreateButton(string name, string label, Transform parent, Vector2 pos, float width)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var img = go.AddComponent<Image>();
            img.color = buttonColor;
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;

            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 0.5f);
            rt.anchorMax = new Vector2(0, 0.5f);
            rt.sizeDelta = new Vector2(width, 36f);
            rt.anchoredPosition = pos;

            var labelGo = new GameObject("Label");
            labelGo.transform.SetParent(go.transform, false);
            var labelTxt = labelGo.AddComponent<TextMeshProUGUI>();
            labelTxt.font = _font;
            labelTxt.fontSize = 18;
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

        // ── Video Player Setup ──

        private void SetupVideoPlayer()
        {
            if (videoPlayer == null)
            {
                var vpGo = new GameObject("VideoPlayer");
                vpGo.transform.SetParent(transform);
                videoPlayer = vpGo.AddComponent<VideoPlayer>();
            }

            if (videoAudio == null)
            {
                videoAudio = videoPlayer.GetComponent<AudioSource>();
                if (videoAudio == null)
                    videoAudio = videoPlayer.gameObject.AddComponent<AudioSource>();
            }

            videoPlayer.playOnAwake = false;
            videoPlayer.loopPointReached += OnVideoEnd;
            videoPlayer.errorReceived += OnVideoError;
            videoPlayer.audioOutputMode = VideoAudioOutputMode.AudioSource;
            videoPlayer.SetTargetAudioSource(0, videoAudio);
            videoAudio.spatialBlend = 0f; // 2D audio
            videoAudio.loop = false;

            if (musicAudio == null)
            {
                var musicGo = new GameObject("MusicPlayer");
                musicGo.transform.SetParent(transform);
                musicAudio = musicGo.AddComponent<AudioSource>();
            }
            musicAudio.spatialBlend = 0f;
            musicAudio.loop = false;
        }

        // ── Event Handlers ──

        private void OnUrlSubmit(string url)
        {
            if (string.IsNullOrWhiteSpace(url)) return;

            // Auto-add protocol
            if (!url.StartsWith("http"))
                url = "https://" + url;

            _currentUrl = url;
            NavigateToUrl(url);
        }

        private void OnBack()
        {
            StopAll();
            _currentUrl = "";
            _webContent.text = "<size=28><b>Browser</b></size>\n<size=18><i>Enter a URL above to browse</i></size>";
            _videoSurface.enabled = false;
            _statusText.text = "Ready";
        }

        private void OnPlayPause()
        {
            if (_currentMode == Mode.Video)
            {
                if (videoPlayer != null)
                {
                    if (_isPaused)
                    {
                        videoPlayer.Play();
                        _isPaused = false;
                        _playLabel.text = "⏸";
                    }
                    else if (videoPlayer.isPlaying)
                    {
                        videoPlayer.Pause();
                        _isPaused = true;
                        _playLabel.text = "▶";
                    }
                    else
                    {
                        videoPlayer.Play();
                        _isPaused = false;
                        _playLabel.text = "⏸";
                    }
                }
            }
            else if (_currentMode == Mode.Music)
            {
                if (musicAudio != null)
                {
                    if (musicAudio.isPlaying)
                    {
                        musicAudio.Pause();
                        _playLabel.text = "▶";
                    }
                    else
                    {
                        musicAudio.UnPause();
                        if (!musicAudio.isPlaying) musicAudio.Play();
                        _playLabel.text = "⏸";
                    }
                }
            }
        }

        private void CycleMode()
        {
            StopAll();
            _currentMode = (Mode)(((int)_currentMode + 1) % 3);
            _modeLabel.text = _currentMode.ToString().ToUpper();
            _videoSurface.enabled = false;

            switch (_currentMode)
            {
                case Mode.Web:
                    _statusText.text = "Web mode";
                    break;
                case Mode.Video:
                    _statusText.text = "Video mode — enter video URL";
                    break;
                case Mode.Music:
                    _statusText.text = "Music mode — enter audio URL";
                    break;
            }
        }

        // ── Navigation ──

        private void NavigateToUrl(string url)
        {
            StopAll();
            ShowLoading(true);
            _statusText.text = "Loading...";

            switch (_currentMode)
            {
                case Mode.Web:
                    StartCoroutine(LoadWebPage(url));
                    break;
                case Mode.Video:
                    StartCoroutine(LoadVideo(url));
                    break;
                case Mode.Music:
                    StartCoroutine(LoadMusic(url));
                    break;
            }
        }

        // ── Web Page Loading ──

        private IEnumerator LoadWebPage(string url)
        {
            // Use backend proxy for CORS-free fetching
            string proxyUrl = $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:8402/api/web/fetch?url={UnityWebRequest.EscapeURL(url)}";

            using (UnityWebRequest req = UnityWebRequest.Get(proxyUrl))
            {
                req.timeout = 15;
                yield return req.SendWebRequest();

                ShowLoading(false);

                if (req.result == UnityWebRequest.Result.Success)
                {
                    string html = req.downloadHandler.text;
                    _webContent.text = ConvertHtmlToTmp(html);
                    _statusText.text = $"Loaded";
                }
                else
                {
                    _webContent.text = $"<color=#ff4444><b>Error:</b></color> {req.error}\n<size=16>URL: {url}</size>";
                    _statusText.text = "Error";
                }
            }
        }

        private IEnumerator LoadYouTube(string url)
        {
            // Extract video ID
            string videoId = "";
            if (url.Contains("watch?v="))
                videoId = url.Split("watch?v=")[1].Split('&')[0];
            else if (url.Contains("youtu.be/"))
                videoId = url.Split("youtu.be/")[1].Split('?')[0];

            if (string.IsNullOrEmpty(videoId))
            {
                _webContent.text = "<color=#ff4444>Could not parse YouTube URL</color>";
                _statusText.text = "Error";
                ShowLoading(false);
                yield break;
            }

            // Switch to video mode and try to load
            _currentMode = Mode.Video;
            _modeLabel.text = "VIDEO";

            // Try direct stream (may not work for all videos)
            string streamUrl = $"https://www.youtube.com/watch?v={videoId}";

            // For now, show info and suggest direct video URL
            _webContent.text = $"<size=24><b>YouTube Video</b></size>\n" +
                $"Video ID: <color=#44aaff>{videoId}</color>\n\n" +
                $"<size=18><i>YouTube requires backend proxy for direct streaming.\n" +
                $"Use the backend /api/youtube/stream endpoint.</i></size>";

            // Try loading via backend proxy (yt-dlp extraction)
            string proxyUrl = $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:8402/api/youtube/stream?id={videoId}";
            yield return StartCoroutine(LoadVideo(proxyUrl));
        }

        // ── Video Loading ──

        private IEnumerator LoadVideo(string url)
        {
            _videoSurface.enabled = true;
            _webContent.text = "";

            if (_videoTexture == null)
            {
                _videoTexture = new RenderTexture(1920, 1080, 0, RenderTextureFormat.ARGB32);
                _videoSurface.texture = _videoTexture;
            }

            videoPlayer.url = url;
            videoPlayer.targetTexture = _videoTexture;
            videoPlayer.Prepare();

            float timeout = 15f;
            float elapsed = 0f;
            while (!videoPlayer.isPrepared && elapsed < timeout)
            {
                elapsed += Time.deltaTime;
                _statusText.text = $"Buffering... {elapsed:F0}s";
                yield return null;
            }

            ShowLoading(false);

            if (videoPlayer.isPrepared)
            {
                videoPlayer.Play();
                _isPlaying = true;
                _isPaused = false;
                _playLabel.text = "⏸";
                _statusText.text = "Playing";
            }
            else
            {
                _statusText.text = "Failed to load video";
                _videoSurface.enabled = false;
            }
        }

        // ── Music Loading ──

        private IEnumerator LoadMusic(string url)
        {
            _videoSurface.enabled = false;
            _webContent.text = "<size=24><b>♪ Now Streaming</b></size>\n" +
                $"<size=18><i>{url}</i></size>";

            using (UnityWebRequest req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.UNKNOWN))
            {
                req.timeout = 20;
                yield return req.SendWebRequest();

                ShowLoading(false);

                if (req.result == UnityWebRequest.Result.Success)
                {
                    AudioClip clip = DownloadHandlerAudioClip.GetContent(req);
                    if (clip != null)
                    {
                        musicAudio.clip = clip;
                        musicAudio.Play();
                        _isPlaying = true;
                        _playLabel.text = "⏸";
                        _statusText.text = $"Playing {clip.length:F0}s";
                    }
                }
                else
                {
                    _webContent.text = $"<color=#ff4444><b>Audio Error:</b></color> {req.error}";
                    _statusText.text = "Error";
                }
            }
        }

        // ── Update ──

        private void Update()
        {
            // Update progress bar
            if (_currentMode == Mode.Video && videoPlayer != null && videoPlayer.isPlaying)
            {
                if (videoPlayer.length > 0)
                    _progressBar.value = (float)(videoPlayer.time / videoPlayer.length);
            }
            else if (_currentMode == Mode.Music && musicAudio != null && musicAudio.isPlaying)
            {
                if (musicAudio.clip != null && musicAudio.clip.length > 0)
                    _progressBar.value = musicAudio.time / musicAudio.clip.length;
            }
        }

        // ── Video Events ──

        private void OnVideoEnd(VideoPlayer vp)
        {
            _isPlaying = false;
            _playLabel.text = "▶";
            _statusText.text = "Ended";
            _progressBar.value = 0f;
        }

        private void OnVideoError(VideoPlayer vp, string error)
        {
            _statusText.text = $"Video error: {error}";
            ShowLoading(false);
        }

        // ── Helpers ──

        private void StopAll()
        {
            if (videoPlayer != null && videoPlayer.isPlaying)
                videoPlayer.Stop();
            if (musicAudio != null && musicAudio.isPlaying)
                musicAudio.Stop();
            _isPlaying = false;
            _isPaused = false;
            _playLabel.text = "▶";
            _progressBar.value = 0f;
        }

        private void ShowLoading(bool show)
        {
            if (_loadingIndicator != null)
                _loadingIndicator.enabled = show;
        }

        private string ConvertHtmlToTmp(string html)
        {
            if (string.IsNullOrEmpty(html)) return "";

            string result = html;

            // Headings
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<h1[^>]*>(.*?)</h1>", "<size=36><b>$1</b></size>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<h2[^>]*>(.*?)</h2>", "<size=30><b>$1</b></size>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<h3[^>]*>(.*?)</h3>", "<size=26><b>$1</b></size>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);

            // Formatting
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<b[^>]*>(.*?)</b>", "<b>$1</b>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<strong[^>]*>(.*?)</strong>", "<b>$1</b>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<i[^>]*>(.*?)</i>", "<i>$1</i>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<em[^>]*>(.*?)</em>", "<i>$1</i>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<u[^>]*>(.*?)</u>", "<u>$1</u>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);

            // Code
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<code[^>]*>(.*?)</code>", "<color=#88ccff>$1</color>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<pre[^>]*>(.*?)</pre>", "\n<color=#88ccff>$1</color>\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);

            // Links
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<a[^>]*href=[""']([^""']*)[""'][^>]*>(.*?)</a>", "<color=#44aaff><u>$2</u></color>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);

            // Line breaks
            result = result.Replace("<br>", "\n").Replace("<br/>", "\n").Replace("<br />", "\n");
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<p[^>]*>", "\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = result.Replace("</p>", "\n");
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<div[^>]*>", "\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = result.Replace("</div>", "\n");

            // Lists
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<li[^>]*>", "  • ", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            result = result.Replace("</li>", "\n");
            result = System.Text.RegularExpressions.Regex.Replace(result, @"</?[uo]l[^>]*>", "\n", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Strip scripts, styles, and remaining tags
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<script[^>]*>.*?</script>", "", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<style[^>]*>.*?</style>", "", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline);
            result = System.Text.RegularExpressions.Regex.Replace(result, @"<[^>]+>", "", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

            // Entities
            result = result.Replace("&nbsp;", " ").Replace("&amp;", "&").Replace("&lt;", "<").Replace("&gt;", ">").Replace("&quot;", "\"").Replace("&#39;", "'");

            // Clean up extra whitespace
            result = System.Text.RegularExpressions.Regex.Replace(result, @"\n{3,}", "\n\n");
            result = result.Trim();

            // Limit length to prevent TMP overflow
            if (result.Length > 8000)
                result = result.Substring(0, 8000) + "\n\n<i>... (truncated)</i>";

            return result;
        }

        private void OnDestroy()
        {
            if (_videoTexture != null)
            {
                _videoTexture.Release();
                Destroy(_videoTexture);
            }
        }
    }
}
