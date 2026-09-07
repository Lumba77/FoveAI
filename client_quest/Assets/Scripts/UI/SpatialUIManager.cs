using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using TMPro;
using FoveAI.IPC;

namespace FoveAI.UI
{
    /// <summary>
    /// Manages a World Space Canvas chat + settings panel that displays incoming
    /// chat text from FoveAIWebSocketClient.OnChatTextReceived and allows the user
    /// to type messages using the Meta Quest 3 system keyboard.
    ///
    /// The settings overlay is a child panel toggled by a button or controller input.
    /// Subscribes automatically in Awake(), unsubscribes in OnDestroy().
    /// Uses only UnityEngine.UI (legacy InputField + Text) — no external packages required.
    /// The InputField will automatically invoke the Meta Quest 3 system keyboard on focus.
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class SpatialUIManager : MonoBehaviour
    {
        [Header("References")]
        [Tooltip("The FoveAIWebSocketClient whose OnChatTextReceived event drives this panel.")]
        [SerializeField] private FoveAIWebSocketClient webSocketClient;

        [Tooltip("Text component that renders the chat transcript.")]
        [SerializeField] private TMP_Text chatText;

        [Tooltip("Input field where the user types messages.")]
        [SerializeField] private TMP_InputField messageInputField;

        [Tooltip("Button that sends the typed message.")]
        [SerializeField] private Button sendButton;

        [Tooltip("Button that toggles the settings overlay panel.")]
        [SerializeField] private Button settingsToggleButton;

        [Tooltip("Settings overlay panel GameObject (toggled on/off).")]
        [SerializeField] private GameObject settingsPanel;

        [Tooltip("InputField for WebSocket URL in settings panel.")]
        [SerializeField] private InputField wsUrlInputField;

        [Tooltip("Button to apply settings.")]
        [SerializeField] private Button applySettingsButton;

        [Tooltip("Button to close settings.")]
        [SerializeField] private Button closeSettingsButton;

        [Header("Advanced Settings (XR Vessel Port)")]
        [SerializeField] private InputField systemPromptInput;
        [SerializeField] private InputField modelSelectInput;
        [SerializeField] private InputField ttsVoiceInput;

        [Header("Display")]
        [Tooltip("Optional ScrollRect. If assigned, enables infinite scrolling chat. If null, falls back to maxLines.")]
        [SerializeField] private ScrollRect chatScrollRect;
        [Tooltip("Maximum number of lines kept visible before older lines are trimmed.")]
        [SerializeField] private int maxLines = 12;

        [Tooltip("Seconds to fade the panel in/out. 0 = instant.")]
        [SerializeField] private float fadeDuration = 0.3f;

        [Tooltip("If true, the panel CanvasGroup alpha fades in when the first message arrives.")]
        [SerializeField] private bool fadeOnFirstMessage = true;

        [Header("Formatting")]
        [Tooltip("Prefix prepended to every incoming chat line.")]
        [SerializeField] private string prefix = "FoveAI: ";

        [Tooltip("If true, timestamps are prepended to each line.")]
        [SerializeField] private bool showTimestamps = false;

        // ─────────────────────────────────────────────────────────────
        //  Internal state
        // ─────────────────────────────────────────────────────────────

        private readonly StringBuilder _lineBuffer = new StringBuilder();
        private CanvasGroup _canvasGroup;
        private bool _firstMessageReceived;
        private Coroutine _fadeCoroutine;
        private bool _settingsVisible;
        private Lumax.Quest3Bridge.Quest3STTClient _sttClient;
        private Button _dictateButton;
        private TMP_Text _dictateLabel;
        private bool _dictating;

        // ─────────────────────────────────────────────────────────────
        //  Unity lifecycle
        // ─────────────────────────────────────────────────────────────

        private void Awake()
        {
            // Cache or add a CanvasGroup for fading
            _canvasGroup = GetComponent<CanvasGroup>();
            if (_canvasGroup == null)
            {
                _canvasGroup = gameObject.AddComponent<CanvasGroup>();
            }

            // Add grabbable behavior so the panel can be moved with grip/fist
            if (GetComponent<GrabbablePanel>() == null)
            {
                gameObject.AddComponent<GrabbablePanel>();
            }

            // Start hidden if fade-on-first-message is enabled
            if (fadeOnFirstMessage)
            {
                _canvasGroup.alpha = 0f;
            }

            EnsureRuntimeChatUi();

            if (webSocketClient == null)
            {
                Debug.LogWarning("[SpatialUI] No webSocketClient assigned — searching scene for one.");
                webSocketClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            }

            if (webSocketClient == null)
            {
                Debug.LogError("[SpatialUI] No FoveAIWebSocketClient found. Panel will not receive messages.");
            }

            if (chatText == null)
            {
                Debug.LogError("[SpatialUI] Chat text could not be created.");
            }

            _sttClient = FindAnyObjectByType<Lumax.Quest3Bridge.Quest3STTClient>();

            // Wire up input field and buttons
            if (messageInputField != null)
            {
                messageInputField.onEndEdit.AddListener(OnMessageInputEndEdit);
            }

            if (sendButton != null)
            {
                sendButton.onClick.AddListener(OnSendButtonClicked);
            }

            if (_dictateButton != null)
            {
                _dictateButton.onClick.AddListener(ToggleDictation);
            }

            if (settingsToggleButton != null)
            {
                settingsToggleButton.onClick.AddListener(ToggleSettings);
            }

            if (applySettingsButton != null)
            {
                applySettingsButton.onClick.AddListener(OnApplySettings);
            }

            if (closeSettingsButton != null)
            {
                closeSettingsButton.onClick.AddListener(HideSettings);
            }

            // Settings panel starts hidden
            if (settingsPanel != null)
            {
                settingsPanel.SetActive(false);
                _settingsVisible = false;
            }
        }

        private void OnEnable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnChatTextReceived += HandleChatTextReceived;
                webSocketClient.OnErrorReceived += HandleErrorReceived;
                webSocketClient.OnSettingsToggle += ToggleSettings;
            }
            if (_sttClient != null)
            {
                _sttClient.OnFinalTranscript += HandleDictationTranscript;
            }
        }

        private void OnDisable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnChatTextReceived -= HandleChatTextReceived;
                webSocketClient.OnErrorReceived -= HandleErrorReceived;
                webSocketClient.OnSettingsToggle -= ToggleSettings;
            }
            if (_sttClient != null)
            {
                _sttClient.OnFinalTranscript -= HandleDictationTranscript;
            }
            SetDictation(false);
        }

        private void OnDestroy()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnChatTextReceived -= HandleChatTextReceived;
                webSocketClient.OnErrorReceived -= HandleErrorReceived;
                webSocketClient.OnSettingsToggle -= ToggleSettings;
            }
        }

        private void EnsureRuntimeChatUi()
        {
            var font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");

            chatText = GetComponentInChildren<TMP_Text>(true);
            if (chatText == null)
            {
                var oldText = transform.Find("Scroll View/Viewport/Content/ChatText");
                if (oldText != null) oldText.gameObject.SetActive(false);

                var textObject = new GameObject("ChatTranscript", typeof(RectTransform));
                textObject.transform.SetParent(transform, false);
                chatText = textObject.AddComponent<TextMeshProUGUI>();
                chatText.font = font;
                chatText.fontSize = 28f;
                chatText.color = Color.white;
                chatText.richText = true;
                chatText.alignment = TextAlignmentOptions.BottomLeft;
                chatText.enableWordWrapping = true;
                var textRect = chatText.rectTransform;
                textRect.anchorMin = new Vector2(0.05f, 0.24f);
                textRect.anchorMax = new Vector2(0.95f, 0.94f);
                textRect.offsetMin = Vector2.zero;
                textRect.offsetMax = Vector2.zero;
            }

            messageInputField = GetComponentInChildren<TMP_InputField>(true);
            if (messageInputField == null)
            {
                var inputObject = new GameObject("MessageInput", typeof(RectTransform));
                inputObject.transform.SetParent(transform, false);
                var inputImage = inputObject.AddComponent<Image>();
                inputImage.color = new Color(0.06f, 0.07f, 0.1f, 1f);
                var inputRect = inputObject.GetComponent<RectTransform>();
                inputRect.anchorMin = new Vector2(0.05f, 0.05f);
                inputRect.anchorMax = new Vector2(0.61f, 0.18f);
                inputRect.offsetMin = Vector2.zero;
                inputRect.offsetMax = Vector2.zero;

                messageInputField = inputObject.AddComponent<TMP_InputField>();
                messageInputField.targetGraphic = inputImage;
                messageInputField.lineType = TMP_InputField.LineType.MultiLineSubmit;
                messageInputField.shouldHideMobileInput = false;

                var viewportObject = new GameObject("Text Area", typeof(RectTransform), typeof(RectMask2D));
                viewportObject.transform.SetParent(inputObject.transform, false);
                var viewportRect = viewportObject.GetComponent<RectTransform>();
                viewportRect.anchorMin = Vector2.zero;
                viewportRect.anchorMax = Vector2.one;
                viewportRect.offsetMin = new Vector2(14f, 8f);
                viewportRect.offsetMax = new Vector2(-14f, -8f);
                messageInputField.textViewport = viewportRect;

                var inputTextObject = new GameObject("Text", typeof(RectTransform));
                inputTextObject.transform.SetParent(viewportObject.transform, false);
                var inputText = inputTextObject.AddComponent<TextMeshProUGUI>();
                inputText.font = font;
                inputText.fontSize = 28f;
                inputText.color = Color.white;
                inputText.alignment = TextAlignmentOptions.MidlineLeft;
                inputText.rectTransform.anchorMin = Vector2.zero;
                inputText.rectTransform.anchorMax = Vector2.one;
                inputText.rectTransform.offsetMin = Vector2.zero;
                inputText.rectTransform.offsetMax = Vector2.zero;
                messageInputField.textComponent = inputText;

                var placeholderObject = new GameObject("Placeholder", typeof(RectTransform));
                placeholderObject.transform.SetParent(viewportObject.transform, false);
                var placeholder = placeholderObject.AddComponent<TextMeshProUGUI>();
                placeholder.font = font;
                placeholder.fontSize = 26f;
                placeholder.color = new Color(1f, 1f, 1f, 0.45f);
                placeholder.text = "Type a message to Lumax...";
                placeholder.alignment = TextAlignmentOptions.MidlineLeft;
                placeholder.rectTransform.anchorMin = Vector2.zero;
                placeholder.rectTransform.anchorMax = Vector2.one;
                placeholder.rectTransform.offsetMin = Vector2.zero;
                placeholder.rectTransform.offsetMax = Vector2.zero;
                messageInputField.placeholder = placeholder;
            }

            if (_dictateButton == null)
            {
                var dictateObject = new GameObject("DictateButton", typeof(RectTransform));
                dictateObject.transform.SetParent(transform, false);
                var dictateImage = dictateObject.AddComponent<Image>();
                dictateImage.color = new Color(0.2f, 0.22f, 0.28f, 1f);
                _dictateButton = dictateObject.AddComponent<Button>();
                _dictateButton.targetGraphic = dictateImage;
                _dictateButton.onClick.AddListener(ToggleDictation);
                var dictateRect = dictateObject.GetComponent<RectTransform>();
                dictateRect.anchorMin = new Vector2(0.63f, 0.05f);
                dictateRect.anchorMax = new Vector2(0.79f, 0.18f);
                dictateRect.offsetMin = Vector2.zero;
                dictateRect.offsetMax = Vector2.zero;

                var dictateLabelObject = new GameObject("Label", typeof(RectTransform));
                dictateLabelObject.transform.SetParent(dictateObject.transform, false);
                _dictateLabel = dictateLabelObject.AddComponent<TextMeshProUGUI>();
                _dictateLabel.font = font;
                _dictateLabel.fontSize = 24f;
                _dictateLabel.color = Color.white;
                _dictateLabel.text = "DICTATE";
                _dictateLabel.alignment = TextAlignmentOptions.Center;
                _dictateLabel.rectTransform.anchorMin = Vector2.zero;
                _dictateLabel.rectTransform.anchorMax = Vector2.one;
                _dictateLabel.rectTransform.offsetMin = Vector2.zero;
                _dictateLabel.rectTransform.offsetMax = Vector2.zero;
            }

            if (sendButton == null)
            {
                var buttonObject = new GameObject("SendButton", typeof(RectTransform));
                buttonObject.transform.SetParent(transform, false);
                var buttonImage = buttonObject.AddComponent<Image>();
                buttonImage.color = new Color(0f, 0.65f, 0.75f, 1f);
                sendButton = buttonObject.AddComponent<Button>();
                sendButton.targetGraphic = buttonImage;
                sendButton.onClick.AddListener(OnSendButtonClicked);
                var buttonRect = buttonObject.GetComponent<RectTransform>();
                buttonRect.anchorMin = new Vector2(0.81f, 0.05f);
                buttonRect.anchorMax = new Vector2(0.95f, 0.18f);
                buttonRect.offsetMin = Vector2.zero;
                buttonRect.offsetMax = Vector2.zero;

                var labelObject = new GameObject("Label", typeof(RectTransform));
                labelObject.transform.SetParent(buttonObject.transform, false);
                var label = labelObject.AddComponent<TextMeshProUGUI>();
                label.font = font;
                label.fontSize = 28f;
                label.color = Color.white;
                label.text = "SEND";
                label.alignment = TextAlignmentOptions.Center;
                label.rectTransform.anchorMin = Vector2.zero;
                label.rectTransform.anchorMax = Vector2.one;
                label.rectTransform.offsetMin = Vector2.zero;
                label.rectTransform.offsetMax = Vector2.zero;
            }

            if (EventSystem.current == null)
            {
                var eventSystemObject = new GameObject("EventSystem");
                eventSystemObject.AddComponent<EventSystem>();
                eventSystemObject.AddComponent<InputSystemUIInputModule>();
            }
        }

        public void ActivateInput()
        {
            if (_canvasGroup != null)
            {
                _canvasGroup.alpha = 1f;
                _canvasGroup.interactable = true;
                _canvasGroup.blocksRaycasts = true;
            }
            if (messageInputField == null) return;
            messageInputField.Select();
            messageInputField.ActivateInputField();
        }

        private void ToggleDictation()
        {
            var vad = FindAnyObjectByType<FoveAI.Audio.QuestMicrophoneVAD>();
            if (vad != null)
            {
                vad.ToggleManualRecording();
            }
            else
            {
                SetDictation(!_dictating);
            }
        }

        public void SetDictation(bool enabled)
        {
            _dictating = enabled;
            if (_sttClient != null) _sttClient.SetManualDictationMode(_dictating);
            if (_dictateLabel != null) _dictateLabel.text = _dictating ? "STOP" : "DICTATE";
            if (_dictateButton != null && _dictateButton.targetGraphic is Image image)
            {
                image.color = _dictating
                    ? new Color(0.75f, 0.18f, 0.2f, 1f)
                    : new Color(0.2f, 0.22f, 0.28f, 1f);
            }
            if (_dictating) ActivateInput();
        }

        private void HandleDictationTranscript(string text, int segment)
        {
            if (!_dictating || messageInputField == null || string.IsNullOrWhiteSpace(text)) return;
            if (IsSendVoiceCommand(text))
            {
                OnSendButtonClicked();
                return;
            }
            string separator = string.IsNullOrWhiteSpace(messageInputField.text) ? string.Empty : " ";
            messageInputField.text += separator + text.Trim();
            messageInputField.caretPosition = messageInputField.text.Length;
        }

        private static bool IsSendVoiceCommand(string text)
        {
            string command = text.Trim().ToLowerInvariant().TrimEnd('.', '!', '?');
            command = command.Replace(",", string.Empty);
            while (command.Contains("  ")) command = command.Replace("  ", " ");
            return command == "send message" ||
                   command == "lumax send" ||
                   command == "lumax send message" ||
                   command == "hey lumax send message" ||
                   command == "okay lumax send message" ||
                   command == "ai send" ||
                   command == "ai send message" ||
                   command == "hey ai send message";
        }

        // ─────────────────────────────────────────────────────────────
        //  Input handling — Meta Quest 3 system keyboard
        // ─────────────────────────────────────────────────────────────

        /// <summary>
        /// Called when the user presses Enter on the InputField.
        /// The InputField automatically invokes the Quest 3 system keyboard on focus.
        /// </summary>
        private void OnMessageInputEndEdit(string text)
        {
            // On Quest 3, the keyboard "Enter" triggers onEndEdit.
            // Only send if there's actual text.
            if (!string.IsNullOrEmpty(text))
            {
                SendUserMessage(text);
            }
        }

        private void OnSendButtonClicked()
        {
            if (messageInputField != null && !string.IsNullOrEmpty(messageInputField.text))
            {
                SendUserMessage(messageInputField.text);
            }
        }

        /// <summary>
        /// Send a chat message to the backend via the WebSocket client.
        /// </summary>
        private void SendUserMessage(string text)
        {
            if (string.IsNullOrEmpty(text))
                return;

            // Display the user's message locally using Rich Text bubble formatting
            string userLine = BuildLine($"<color=#00ffff><b>You:</b></color> {text}");
            AppendLine(userLine);
            if (chatText != null)
                chatText.text = _lineBuffer.ToString();

            // Send to backend
            if (webSocketClient != null)
            {
                webSocketClient.SendChatMessage(text);
            }
            SetDictation(false);

            // Clear the input field
            if (messageInputField != null)
            {
                messageInputField.text = string.Empty;
                // Re-activate for continued typing
                messageInputField.ActivateInputField();
            }

            // Fade in if needed
            if (fadeOnFirstMessage && !_firstMessageReceived)
            {
                _firstMessageReceived = true;
                FadeIn();
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  Settings panel
        // ─────────────────────────────────────────────────────────────

        /// <summary>
        /// Toggle the in-scene settings overlay panel.
        /// Can be bound to a Quest 3 controller button (e.g. Menu button).
        /// </summary>
        public void ToggleSettings()
        {
            if (settingsPanel == null)
                return;

            _settingsVisible = !_settingsVisible;
            settingsPanel.SetActive(_settingsVisible);
            Debug.Log($"[SpatialUI] Settings panel {(_settingsVisible ? "opened" : "closed")}");
        }

        /// <summary>
        /// Show the settings panel.
        /// </summary>
        public void ShowSettings()
        {
            if (settingsPanel != null)
            {
                _settingsVisible = true;
                settingsPanel.SetActive(true);
            }
        }

        /// <summary>
        /// Hide the settings panel.
        /// </summary>
        public void HideSettings()
        {
            if (settingsPanel != null)
            {
                _settingsVisible = false;
                settingsPanel.SetActive(false);
            }
        }

        /// <summary>
        /// Apply settings from the settings panel input fields.
        /// </summary>
        private void OnApplySettings()
        {
            if (wsUrlInputField != null && webSocketClient != null)
            {
                string newUrl = wsUrlInputField.text.Trim();
                if (!string.IsNullOrEmpty(newUrl))
                {
                    webSocketClient.SetServerUrl(newUrl);
                }
            }

            // Send XR Vessel expanded settings to backend via JSON payload
            string prompt = systemPromptInput != null ? systemPromptInput.text : "";
            string model = modelSelectInput != null ? modelSelectInput.text : "";
            string voice = ttsVoiceInput != null ? ttsVoiceInput.text : "";

            string settingsPayload = $"{{\"system_prompt\":\"{prompt}\",\"model\":\"{model}\",\"voice\":\"{voice}\"}}";
            if (webSocketClient != null)
            {
                webSocketClient.SendEvent("settings.update", settingsPayload);
            }

            DisplayMessage($"<color=#aaaaaa><i>Settings applied.</i></color>");
            HideSettings();
        }

        // ─────────────────────────────────────────────────────────────
        //  Event handlers
        // ─────────────────────────────────────────────────────────────

        private void HandleErrorReceived(string error)
        {
            if (chatText == null || string.IsNullOrEmpty(error))
            {
                return;
            }

            string line = BuildLine($"[ERROR] {error}");
            Debug.LogWarning($"[SpatialUI] Backend error displayed: {error}");

            if (chatText.text.Length > 0)
            {
                chatText.text += "\n";
            }
            chatText.text += line;
        }

        public void AppendAgentMessage(string text) => HandleChatTextReceived(text);

        private void HandleChatTextReceived(string text)
        {
            if (chatText == null || string.IsNullOrEmpty(text))
            {
                return;
            }

            // Build the formatted AI line
            string line = BuildLine($"<color=#00ff55><b>FoveAI:</b></color> {text}");

            // Append to the buffer and trim to maxLines (if no ScrollRect)
            AppendLine(line);

            // Update the UI text
            chatText.text = _lineBuffer.ToString();

            // Auto-scroll to bottom if using a ScrollRect
            if (chatScrollRect != null)
            {
                Canvas.ForceUpdateCanvases();
                chatScrollRect.verticalNormalizedPosition = 0f;
            }

            // Fade in on first message
            if (fadeOnFirstMessage && !_firstMessageReceived)
            {
                _firstMessageReceived = true;
                FadeIn();
            }

            Debug.Log($"[SpatialUI] Chat panel updated: {line}");
        }

        // ─────────────────────────────────────────────────────────────
        //  Public API
        // ─────────────────────────────────────────────────────────────

        /// <summary>
        /// Manually push a line to the chat panel (bypasses the WebSocket event).
        /// </summary>
        public void DisplayMessage(string text)
        {
            HandleChatTextReceived(text);
        }

        /// <summary>
        /// Clear all text from the chat panel.
        /// </summary>
        public void Clear()
        {
            _lineBuffer.Clear();
            if (chatText != null)
            {
                chatText.text = string.Empty;
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  Internal helpers
        // ─────────────────────────────────────────────────────────────

        private string BuildLine(string text)
        {
            if (showTimestamps)
            {
                return $"[{System.DateTime.Now:HH:mm:ss}] {prefix}{text}";
            }
            return $"{prefix}{text}";
        }

        private void AppendLine(string line)
        {
            _lineBuffer.AppendLine(line);
            _lineBuffer.AppendLine(); // extra spacing between bubbles

            // Only trim if we don't have a ScrollRect (XR Vessel infinite scroll)
            if (chatScrollRect == null)
            {
                var lines = _lineBuffer.ToString().Split('\n');
                if (lines.Length > maxLines)
                {
                    _lineBuffer.Clear();
                    for (int i = lines.Length - maxLines; i < lines.Length; i++)
                    {
                        if (i > lines.Length - maxLines)
                            _lineBuffer.AppendLine();
                        _lineBuffer.Append(lines[i]);
                    }
                }
            }
        }

        private void FadeIn()
        {
            if (_fadeCoroutine != null)
                StopCoroutine(_fadeCoroutine);
            _fadeCoroutine = StartCoroutine(FadeCoroutine(_canvasGroup.alpha, 1f, fadeDuration));
        }

        private void FadeOut()
        {
            if (_fadeCoroutine != null)
                StopCoroutine(_fadeCoroutine);
            _fadeCoroutine = StartCoroutine(FadeCoroutine(_canvasGroup.alpha, 0f, fadeDuration));
        }

        private IEnumerator FadeCoroutine(float from, float to, float duration)
        {
            if (duration <= 0f)
            {
                _canvasGroup.alpha = to;
                yield break;
            }

            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                _canvasGroup.alpha = Mathf.Lerp(from, to, elapsed / duration);
                yield return null;
            }
            _canvasGroup.alpha = to;
        }
    }
}