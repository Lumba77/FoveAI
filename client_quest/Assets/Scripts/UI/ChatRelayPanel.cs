using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using FoveAI.Config;

namespace FoveAI.UI
{
    /// <summary>
    /// 4-Way XR Chat Relay Panel for Quest 3.
    ///
    /// Connects to the FoveAI chat relay WebSocket (port 8407) and displays
    /// a scrolling, color-coded chat panel showing messages from all 4
    /// participants: user, jen, devin, antigravity.
    ///
    /// The panel is a world-space Canvas that floats in front of the user.
    /// It auto-positions 2m ahead at eye level and billboards toward the camera.
    ///
    /// Toggle visibility by pressing Y on the right Quest 3 controller
    /// (or F2 in desktop mode).
    ///
    /// Messages can also be sent from the Quest via the input field.
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class ChatRelayPanel : MonoBehaviour
    {
        [Header("Connection")]
        [SerializeField] private float reconnectDelay = 3f;

        [Header("Panel Settings")]
        [SerializeField] private float panelWidth = 800f;
        [SerializeField] private float panelHeight = 600f;
        [Range(0f, 1f)] public float panelAlpha = 0.9f;
        [SerializeField] private int maxVisibleLines = 12;

        [Header("Colors (per speaker)")]
        [SerializeField] private Color userColor = new Color(1f, 1f, 1f, 1f);        // white
        [SerializeField] private Color jenColor = new Color(0.27f, 1f, 0.27f, 1f);   // green
        [SerializeField] private Color devinColor = new Color(0.27f, 0.53f, 1f, 1f); // blue
        [SerializeField] private Color antigravityColor = new Color(1f, 0.67f, 0.13f, 1f); // orange
        [SerializeField] private Color unknownColor = new Color(1f, 0.27f, 1f, 1f);  // magenta
        [SerializeField] private Color bgColor = new Color(0.02f, 0.02f, 0.08f, 0.9f);
        [SerializeField] private Color headerColor = new Color(0.05f, 0.07f, 0.12f, 1f);
        [SerializeField] private Color inputBgColor = new Color(0.05f, 0.07f, 0.12f, 1f);
        [SerializeField] private Color textColor = new Color(0.88f, 0.92f, 0.98f, 1f);

        [Header("Input")]
        [Tooltip("Key to toggle panel in desktop mode.")]
        [SerializeField] private KeyCode desktopToggleKey = KeyCode.F2;

        // ── Internal ──
        private Canvas _canvas;
        private CanvasGroup _canvasGroup;
        private TMP_FontAsset _font;
        private ScrollRect _scrollRect;
        private TMP_Text _messageText;
        private TMP_InputField _inputField;
        private Button _sendButton;
        private TMP_Text _statusLabel;

        private FoveAIChatWebSocket _ws;
        private bool _connected;
        private float _reconnectTimer;
        private readonly List<ChatMessage> _history = new List<ChatMessage>();
        private const int MaxHistory = 200;
        private string _relayUrl = "";

        private struct ChatMessage
        {
            public string from;
            public string text;
            public string time;
        }

        // ── Lifecycle ──

        private void Awake()
        {
            _font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            if (_font == null) _font = TMP_Settings.defaultFontAsset;

            _canvas = GetComponent<Canvas>();
            _canvas.renderMode = RenderMode.WorldSpace;
            _canvas.worldCamera = Camera.main;

            var rt = _canvas.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(panelWidth, panelHeight);
            rt.localScale = Vector3.one * 0.0015f;

            _canvasGroup = gameObject.GetComponent<CanvasGroup>();
            if (_canvasGroup == null) _canvasGroup = gameObject.AddComponent<CanvasGroup>();
            _canvasGroup.alpha = panelAlpha;
            _canvasGroup.interactable = true;
            _canvasGroup.blocksRaycasts = true;

            BuildUI();
        }

        private void Start()
        {
            // Build relay URL from config
            var settings = ConfigLoader.Settings;
            if (settings != null)
            {
                _relayUrl = $"ws://{settings.serverIp}:{settings.chatRelayPort}/ws";
            }
            else
            {
                _relayUrl = "ws://127.0.0.1:8407/ws";
            }

            Debug.Log($"[ChatRelayPanel] Connecting to {_relayUrl}");
            ConnectToRelay();

            // Auto-position floating in front of user at startup
            PositionInFrontOfUser();
        }

        private void Update()
        {
            // Desktop toggle (F2) and Quest 3 Y button
            bool togglePressed = Input.GetKeyDown(desktopToggleKey);
            try
            {
                if (OVRInput.GetDown(OVRInput.Button.Four) || OVRInput.GetDown(OVRInput.RawButton.Y))
                {
                    togglePressed = true;
                }
            }
            catch { }

            if (togglePressed)
            {
                TogglePanel();
            }

            // Reconnect if needed
            if (!_connected && _reconnectTimer > 0)
            {
                _reconnectTimer -= Time.deltaTime;
                if (_reconnectTimer <= 0)
                {
                    ConnectToRelay();
                }
            }

            // Billboard: face the camera (canvas +Z points away from camera so front faces user)
            if (_canvas.gameObject.activeSelf && Camera.main != null)
            {
                Vector3 lookDir = transform.position - Camera.main.transform.position;
                lookDir.y = 0f;
                if (lookDir.sqrMagnitude > 0.001f)
                {
                    transform.rotation = Quaternion.LookRotation(lookDir, Vector3.up);
                }
            }
        }

        private void OnDestroy()
        {
            _ws?.Close();
            _ws = null;
        }

        // ── UI Construction ──

        private void BuildUI()
        {
            var rt = _canvas.GetComponent<RectTransform>();

            // Background
            var bgGo = new GameObject("ChatBg");
            bgGo.transform.SetParent(rt, false);
            var bgImg = bgGo.AddComponent<Image>();
            bgImg.color = bgColor;
            var bgRt = bgGo.GetComponent<RectTransform>();
            bgRt.anchorMin = Vector2.zero;
            bgRt.anchorMax = Vector2.one;
            bgRt.offsetMin = Vector2.zero;
            bgRt.offsetMax = Vector2.zero;

            // Header
            var headerGo = new GameObject("Header");
            headerGo.transform.SetParent(rt, false);
            var headerImg = headerGo.AddComponent<Image>();
            headerImg.color = headerColor;
            var headerRt = headerGo.GetComponent<RectTransform>();
            headerRt.anchorMin = new Vector2(0, 1);
            headerRt.anchorMax = new Vector2(1, 1);
            headerRt.sizeDelta = new Vector2(0, 50);
            headerRt.anchoredPosition = Vector2.zero;

            var headerText = headerGo.AddComponent<TextMeshProUGUI>();
            headerText.text = "4-Way XR Chat";
            headerText.font = _font;
            headerText.fontSize = 24;
            headerText.alignment = TextAlignmentOptions.Center;
            headerText.color = textColor;
            var headerTextRt = headerText.GetComponent<RectTransform>();
            headerTextRt.offsetMin = new Vector2(10, 0);
            headerTextRt.offsetMax = new Vector2(-10, 0);

            // Status label (top-right)
            var statusGo = new GameObject("StatusLabel");
            statusGo.transform.SetParent(headerGo.transform, false);
            _statusLabel = statusGo.AddComponent<TextMeshProUGUI>();
            _statusLabel.font = _font;
            _statusLabel.fontSize = 16;
            _statusLabel.alignment = TextAlignmentOptions.Right;
            _statusLabel.color = new Color(0.5f, 0.5f, 0.5f, 1f);
            _statusLabel.text = "Connecting...";
            var statusRt = _statusLabel.GetComponent<RectTransform>();
            statusRt.anchorMin = new Vector2(0, 0);
            statusRt.anchorMax = new Vector2(1, 1);
            statusRt.offsetMin = new Vector2(-200, 0);
            statusRt.offsetMax = new Vector2(-10, 0);

            // Message scroll area
            var scrollGo = new GameObject("MessageScroll");
            scrollGo.transform.SetParent(rt, false);
            _scrollRect = scrollGo.AddComponent<ScrollRect>();
            _scrollRect.horizontal = false;
            _scrollRect.vertical = true;
            var scrollRt = scrollGo.GetComponent<RectTransform>();
            scrollRt.anchorMin = new Vector2(0, 0);
            scrollRt.anchorMax = new Vector2(1, 1);
            scrollRt.offsetMin = new Vector2(10, 60);
            scrollRt.offsetMax = new Vector2(-10, -55);

            // Scroll content
            var contentGo = new GameObject("Content");
            contentGo.transform.SetParent(scrollGo.transform, false);
            var contentRt = contentGo.AddComponent<RectTransform>();
            contentRt.anchorMin = new Vector2(0, 1);
            contentRt.anchorMax = Vector2.one;
            contentRt.pivot = new Vector2(0.5f, 1f);
            contentRt.sizeDelta = new Vector2(0, 0);

            // Message text (TMP rich text)
            _messageText = contentGo.AddComponent<TextMeshProUGUI>();
            _messageText.font = _font;
            _messageText.fontSize = 20;
            _messageText.richText = true;
            _messageText.alignment = TextAlignmentOptions.TopLeft;
            _messageText.color = textColor;
            _messageText.textWrappingMode = TextWrappingModes.Normal;
            var msgTextRt = _messageText.GetComponent<RectTransform>();
            msgTextRt.anchorMin = new Vector2(0, 1);
            msgTextRt.anchorMax = Vector2.one;
            msgTextRt.pivot = new Vector2(0.5f, 1f);
            msgTextRt.offsetMin = new Vector2(5, 0);
            msgTextRt.offsetMax = new Vector2(-5, 0);

            // ContentSizeFitter to auto-resize
            var fitter = contentGo.AddComponent<ContentSizeFitter>();
            fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            _scrollRect.content = contentRt;

            // Input field at the bottom
            var inputGo = new GameObject("InputArea");
            inputGo.transform.SetParent(rt, false);
            var inputImg = inputGo.AddComponent<Image>();
            inputImg.color = inputBgColor;
            var inputAreaRt = inputGo.GetComponent<RectTransform>();
            inputAreaRt.anchorMin = new Vector2(0, 0);
            inputAreaRt.anchorMax = new Vector2(1, 0);
            inputAreaRt.sizeDelta = new Vector2(0, 50);
            inputAreaRt.anchoredPosition = Vector2.zero;

            // Input field
            var inputFieldGo = new GameObject("InputField");
            inputFieldGo.transform.SetParent(inputGo.transform, false);
            _inputField = inputFieldGo.AddComponent<TMP_InputField>();
            _inputField.fontAsset = _font;
            _inputField.textComponent = inputFieldGo.GetComponent<TextMeshProUGUI>() ?? inputFieldGo.AddComponent<TextMeshProUGUI>();
            _inputField.textComponent.font = _font;
            _inputField.textComponent.fontSize = 20;
            _inputField.textComponent.color = textColor;
            var placeholder = inputFieldGo.AddComponent<TextMeshProUGUI>();
            placeholder.font = _font;
            placeholder.fontSize = 20;
            placeholder.text = "Type a message...";
            placeholder.color = new Color(0.5f, 0.5f, 0.5f, 0.5f);
            _inputField.placeholder = placeholder;
            var inputRt = _inputField.GetComponent<RectTransform>();
            inputRt.anchorMin = new Vector2(0, 0);
            inputRt.anchorMax = new Vector2(0.8f, 1);
            inputRt.offsetMin = new Vector2(10, 5);
            inputRt.offsetMax = new Vector2(-5, -5);

            // Send button
            var btnGo = new GameObject("SendButton");
            btnGo.transform.SetParent(inputGo.transform, false);
            _sendButton = btnGo.AddComponent<Button>();
            var btnImg = btnGo.AddComponent<Image>();
            btnImg.color = new Color(0.15f, 0.30f, 0.50f, 1f);
            var btnLabel = btnGo.AddComponent<TextMeshProUGUI>();
            btnLabel.font = _font;
            btnLabel.fontSize = 20;
            btnLabel.text = "Send";
            btnLabel.alignment = TextAlignmentOptions.Center;
            btnLabel.color = Color.white;
            var btnRt = btnGo.GetComponent<RectTransform>();
            btnRt.anchorMin = new Vector2(0.8f, 0);
            btnRt.anchorMax = new Vector2(1, 1);
            btnRt.offsetMin = new Vector2(5, 5);
            btnRt.offsetMax = new Vector2(-10, -5);

            _sendButton.onClick.AddListener(OnSendClicked);
            _inputField.onSubmit.AddListener((_) => OnSendClicked());
        }

        // ── WebSocket Connection ──

        private async void ConnectToRelay()
        {
            if (string.IsNullOrEmpty(_relayUrl)) return;

            try
            {
                _ws?.Close();
                _ws = new FoveAIChatWebSocket(new Uri(_relayUrl));
                _ws.OnOpen += OnWsOpen;
                _ws.OnMessage += OnWsMessage;
                _ws.OnClose += OnWsClose;
                _ws.OnError += OnWsError;

                await _ws.Connect();
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[ChatRelayPanel] Connection failed: {ex.Message}");
                ScheduleReconnect();
            }
        }

        private void OnWsOpen()
        {
            _connected = true;
            UpdateStatus("Connected", new Color(0.27f, 1f, 0.27f, 1f));
            Debug.Log("[ChatRelayPanel] Connected to relay");
        }

        private void OnWsMessage(byte[] data)
        {
            string json = Encoding.UTF8.GetString(data);
            try
            {
                var msg = JsonUtility.FromJson<RelayMessage>(json);

                if (msg.type == "history" && msg.messages != null)
                {
                    _history.Clear();
                    foreach (var m in msg.messages)
                    {
                        _history.Add(new ChatMessage { from = m.from, text = m.text, time = m.time });
                    }
                }
                else if (msg.type == "chat")
                {
                    _history.Add(new ChatMessage { from = msg.from, text = msg.text, time = msg.time });
                    while (_history.Count > MaxHistory) _history.RemoveAt(0);
                }

                RefreshMessages();
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[ChatRelayPanel] Parse error: {ex.Message}");
            }
        }

        private void OnWsClose(ushort code, string reason)
        {
            _connected = false;
            UpdateStatus("Disconnected", new Color(1f, 0.27f, 0.27f, 1f));
            ScheduleReconnect();
        }

        private void OnWsError(string error)
        {
            Debug.LogWarning($"[ChatRelayPanel] WS error: {error}");
        }

        private void ScheduleReconnect()
        {
            _reconnectTimer = reconnectDelay;
            UpdateStatus("Reconnecting...", new Color(1f, 0.67f, 0.13f, 1f));
        }

        // ── Messaging ──

        private void OnSendClicked()
        {
            if (_inputField == null) return;
            string text = _inputField.text.Trim();
            if (string.IsNullOrEmpty(text)) return;

            if (_ws != null && _ws.IsOpen)
            {
                string json = $"{{\"type\":\"chat\",\"from\":\"user\",\"text\":\"{EscapeJson(text)}\"}}";
                _ws.SendString(json);
                _inputField.text = "";
                _inputField.ActivateInputField();
            }
        }

        private void RefreshMessages()
        {
            if (_messageText == null) return;

            var sb = new StringBuilder();
            int start = Mathf.Max(0, _history.Count - maxVisibleLines);

            for (int i = start; i < _history.Count; i++)
            {
                var msg = _history[i];
                Color color = GetSpeakerColor(msg.from);
                string colorHex = ColorToHex(color);
                string speaker = msg.from ?? "unknown";
                string text = msg.text ?? "";

                // Truncate long messages
                if (text.Length > 80) text = text.Substring(0, 77) + "...";

                sb.Append($"<color=#{colorHex}><b>{speaker}:</b></color> {text}");
                if (i < _history.Count - 1) sb.AppendLine();
            }

            _messageText.text = sb.ToString();

            // Auto-scroll to bottom
            if (_scrollRect != null)
            {
                Canvas.ForceUpdateCanvases();
                _scrollRect.verticalNormalizedPosition = 0f;
            }
        }

        // ── Helpers ──

        private Color GetSpeakerColor(string speaker)
        {
            return speaker switch
            {
                "user" => userColor,
                "jen" => jenColor,
                "devin" => devinColor,
                "antigravity" => antigravityColor,
                _ => unknownColor,
            };
        }

        private static string ColorToHex(Color c)
        {
            int r = Mathf.RoundToInt(c.r * 255);
            int g = Mathf.RoundToInt(c.g * 255);
            int b = Mathf.RoundToInt(c.b * 255);
            return $"{r:X2}{g:X2}{b:X2}";
        }

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder();
            foreach (char ch in s)
            {
                switch (ch)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (ch < 0x20) sb.Append($"\\u{(int)ch:X4}");
                        else sb.Append(ch);
                        break;
                }
            }
            return sb.ToString();
        }

        private void UpdateStatus(string text, Color color)
        {
            if (_statusLabel != null)
            {
                _statusLabel.text = text;
                _statusLabel.color = color;
            }
        }

        /// <summary>Toggle panel visibility (called by input or external scripts).</summary>
        public void TogglePanel()
        {
            bool active = !_canvas.gameObject.activeSelf;
            _canvas.gameObject.SetActive(active);
            if (active && Camera.main != null)
            {
                PositionInFrontOfUser();
            }
        }

        private void PositionInFrontOfUser()
        {
            Camera cam = Camera.main;
            if (cam == null) cam = FindAnyObjectByType<Camera>();
            if (cam == null) return;

            Vector3 fwd = cam.transform.forward;
            fwd.y = 0f;
            if (fwd.sqrMagnitude < 0.01f) fwd = Vector3.forward;
            fwd.Normalize();

            Vector3 pos = cam.transform.position + fwd * 1.8f;
            pos.y = cam.transform.position.y;
            transform.position = pos;

            Vector3 lookDir = transform.position - cam.transform.position;
            lookDir.y = 0f;
            if (lookDir.sqrMagnitude > 0.001f)
            {
                transform.rotation = Quaternion.LookRotation(lookDir, Vector3.up);
            }
        }

        // ── JSON DTOs ──

        [System.Serializable]
        private class RelayMessage
        {
            public string type;
            public string from;
            public string text;
            public string time;
            public RelayHistoryItem[] messages;
        }

        [System.Serializable]
        private class RelayHistoryItem
        {
            public string type;
            public string from;
            public string text;
            public string time;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    //  Minimal WebSocket wrapper for the chat relay
    // ═══════════════════════════════════════════════════════════════

    internal sealed class FoveAIChatWebSocket
    {
        public event Action OnOpen;
        public event Action<byte[]> OnMessage;
        public event Action<ushort, string> OnClose;
        public event Action<string> OnError;

        public bool IsOpen => _state == State.Open;

        private enum State { Idle, Connecting, Open, Closed }
        private State _state = State.Idle;

        private readonly Uri _uri;
        private System.Net.WebSockets.ClientWebSocket _ws;
        private CancellationTokenSource _cts;

        public FoveAIChatWebSocket(Uri uri) => _uri = uri;

        public async Task Connect()
        {
            _cts = new CancellationTokenSource();
            _ws = new System.Net.WebSockets.ClientWebSocket();
            _state = State.Connecting;

            try
            {
                await _ws.ConnectAsync(_uri, _cts.Token);
                _state = State.Open;
                OnOpen?.Invoke();
                _ = ReceiveLoop(_cts.Token);
            }
            catch (Exception ex)
            {
                _state = State.Closed;
                OnError?.Invoke(ex.Message);
            }
        }

        private async Task ReceiveLoop(CancellationToken ct)
        {
            var buffer = new ArraySegment<byte>(new byte[8192]);
            var messageBuffer = new System.Collections.Generic.List<byte>();

            try
            {
                while (_state == State.Open && !ct.IsCancellationRequested)
                {
                    System.Net.WebSockets.WebSocketReceiveResult result;
                    messageBuffer.Clear();

                    do
                    {
                        result = await _ws.ReceiveAsync(buffer, ct);
                        if (result.MessageType == System.Net.WebSockets.WebSocketMessageType.Close)
                        {
                            _state = State.Closed;
                            OnClose?.Invoke((ushort)result.CloseStatus, result.CloseStatusDescription);
                            return;
                        }
                        if (result.Count > 0)
                        {
                            var chunk = new byte[result.Count];
                            System.Array.Copy(buffer.Array, chunk, result.Count);
                            messageBuffer.AddRange(chunk);
                        }
                    }
                    while (!result.EndOfMessage);

                    if (messageBuffer.Count > 0)
                        OnMessage?.Invoke(messageBuffer.ToArray());
                }
            }
            catch (Exception ex)
            {
                if (_state != State.Closed)
                {
                    _state = State.Closed;
                    OnError?.Invoke(ex.Message);
                    OnClose?.Invoke(1006, ex.Message);
                }
            }
        }

        public void SendString(string text)
        {
            if (_state != State.Open || _ws == null) return;
            byte[] bytes = Encoding.UTF8.GetBytes(text);
            _ = _ws.SendAsync(new ArraySegment<byte>(bytes), System.Net.WebSockets.WebSocketMessageType.Text, true, _cts.Token);
        }

        public void Close()
        {
            _state = State.Closed;
            try { _cts?.Cancel(); } catch { }
            try { _ws?.Dispose(); } catch { }
        }
    }
}
