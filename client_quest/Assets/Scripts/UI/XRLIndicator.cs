using UnityEngine;
using UnityEngine.UI;
using System.Collections;
using FoveAI.IPC;

namespace FoveAI.UI
{
    /// <summary>
    /// Visually indicates when the LUMAX Backend is using the XRL Principia
    /// to fetch and "flesh out" a Shadow Memory.
    /// Creates its own world-space Canvas if none is provided.
    /// </summary>
    public class XRLIndicator : MonoBehaviour
    {
        [Header("Dependencies")]
        public FoveAIWebSocketClient webSocketClient;

        [Header("UI References")]
        public Canvas canvas;
        public Text indicatorText;
        public Image backgroundPanel;

        [Header("Settings")]
        public float displayDuration = 3.0f;
        public float pulseSpeed = 2.0f;

        private Coroutine _displayCoroutine;
        private CanvasGroup _canvasGroup;

        private void Awake()
        {
            // Auto-find websocket client if not assigned
            if (webSocketClient == null)
            {
                webSocketClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            }

            SetupUI();
        }

        private void SetupUI()
        {
            if (canvas == null)
            {
                // Create a floating world-space canvas
                GameObject canvasObj = new GameObject("XRL_IndicatorCanvas");
                canvasObj.transform.SetParent(this.transform, false);
                canvasObj.transform.localPosition = new Vector3(0, 1.8f, 1.5f); // High up, floating in front
                canvasObj.transform.localScale = Vector3.one * 0.005f;

                canvas = canvasObj.AddComponent<Canvas>();
                canvas.renderMode = RenderMode.WorldSpace;
                
                CanvasScaler scaler = canvasObj.AddComponent<CanvasScaler>();
                scaler.dynamicPixelsPerUnit = 10;

                _canvasGroup = canvasObj.AddComponent<CanvasGroup>();
                _canvasGroup.alpha = 0;

                // Create background panel
                GameObject bgObj = new GameObject("Background");
                bgObj.transform.SetParent(canvasObj.transform, false);
                backgroundPanel = bgObj.AddComponent<Image>();
                backgroundPanel.color = new Color(0.1f, 0.1f, 0.2f, 0.8f);
                RectTransform bgRect = bgObj.GetComponent<RectTransform>();
                bgRect.sizeDelta = new Vector2(400, 100);

                // Create Text
                GameObject textObj = new GameObject("Text");
                textObj.transform.SetParent(canvasObj.transform, false);
                indicatorText = textObj.AddComponent<Text>();
                indicatorText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
                indicatorText.color = new Color(0.4f, 0.8f, 1.0f, 1.0f); // Cyan
                indicatorText.fontSize = 24;
                indicatorText.alignment = TextAnchor.MiddleCenter;
                indicatorText.text = "Retrieving memories of the past...";
                
                RectTransform textRect = textObj.GetComponent<RectTransform>();
                textRect.sizeDelta = new Vector2(380, 80);
            }
            else
            {
                _canvasGroup = canvas.gameObject.GetComponent<CanvasGroup>();
                if (_canvasGroup == null)
                    _canvasGroup = canvas.gameObject.AddComponent<CanvasGroup>();
                _canvasGroup.alpha = 0;
            }
        }

        private void OnEnable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnXRLExpandReceived += HandleXRLExpand;
            }
        }

        private void OnDisable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnXRLExpandReceived -= HandleXRLExpand;
            }
        }

        private void Update()
        {
            // Make the canvas face the camera
            if (canvas != null && Camera.main != null)
            {
                canvas.transform.rotation = Quaternion.LookRotation(canvas.transform.position - Camera.main.transform.position);
            }
        }

        private void HandleXRLExpand(string hash)
        {
            if (indicatorText != null)
            {
                string[] poeticPhrases = new string[] 
                {
                    "Retrieving memories of the past...",
                    "Rebuilding what once was...",
                    "Reconnecting with a distant thought...",
                    "Gathering fragments of a lost memory...",
                    "Recalling the echoes of our past..."
                };
                
                // Pick a random poetic phrase
                string chosenPhrase = poeticPhrases[UnityEngine.Random.Range(0, poeticPhrases.Length)];
                indicatorText.text = chosenPhrase;
            }

            if (_displayCoroutine != null)
            {
                StopCoroutine(_displayCoroutine);
            }
            _displayCoroutine = StartCoroutine(DisplayAndPulseCoroutine());
        }

        private IEnumerator DisplayAndPulseCoroutine()
        {
            float elapsed = 0f;
            
            // Fade In
            while (_canvasGroup.alpha < 1f)
            {
                _canvasGroup.alpha += Time.deltaTime * 5f;
                yield return null;
            }
            _canvasGroup.alpha = 1f;

            // Pulse effect
            while (elapsed < displayDuration)
            {
                elapsed += Time.deltaTime;
                
                // Pulsing text color
                if (indicatorText != null)
                {
                    float pulse = (Mathf.Sin(elapsed * pulseSpeed * Mathf.PI * 2) + 1f) / 2f;
                    indicatorText.color = Color.Lerp(new Color(0.4f, 0.8f, 1.0f, 1.0f), Color.white, pulse);
                }
                
                yield return null;
            }

            // Fade Out
            while (_canvasGroup.alpha > 0f)
            {
                _canvasGroup.alpha -= Time.deltaTime * 3f;
                yield return null;
            }
            _canvasGroup.alpha = 0f;
        }
    }
}
