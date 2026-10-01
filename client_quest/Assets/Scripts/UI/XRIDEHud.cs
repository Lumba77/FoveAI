using System.Collections;
using UnityEngine;
using FoveAI.Audio;
using FoveAI.IPC;

namespace FoveAI.UI
{
    /// <summary>
    /// XR IDE HUD — Floating In-Headset HUD and Indicator Hub.
    /// Ensures the user is NEVER left in the dark by displaying:
    /// 1. Real-time RMS audio volume wave / level meter
    /// 2. Live speech recognition state ([LISTENING], [RECORDING], [TRANSCRIBING], [SPEAKING])
    /// 3. Central WebSocket and backend service indicators
    /// 4. Controller interaction shortcuts and snapshot confirmations
    /// </summary>
    public class XRIDEHud : MonoBehaviour
    {
        private static XRIDEHud _instance;
        public static XRIDEHud Instance => _instance;

        [Header("Positioning")]
        [Tooltip("Distance from user camera")]
        public float distance = 1.2f;
        [Tooltip("Downward vertical offset from gaze line — pushed down to not obscure avatar")]
        public float downOffset = 0.85f;
        [Tooltip("Smoothing speed")]
        public float followSpeed = 4.0f;

        private TextMesh _titleText;
        private TextMesh _vadMeterText;
        private TextMesh _statusText;
        private TextMesh _controlsText;
        private MeshRenderer _statusPillRenderer;

        private QuestMicrophoneVAD _vad;
        private FoveAIWebSocketClient _wsClient;
        private AvatarVoice _voice;

        private float _flashTimer = 0f;
        private string _flashMessage = "";

        public static void FlashNotification(string message, float duration = 3.0f)
        {
            if (_instance != null)
            {
                _instance._flashMessage = message;
                _instance._flashTimer = duration;
            }
        }

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }
            _instance = this;
            BuildHudVisuals();
        }

        private void Start()
        {
            _vad = FindAnyObjectByType<QuestMicrophoneVAD>();
            _wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            _voice = FindAnyObjectByType<AvatarVoice>();
        }

        private void BuildHudVisuals()
        {
            // Root HUD quad (80% transparent — subtle dark backing, doesn't obscure avatar)
            var bgObj = GameObject.CreatePrimitive(PrimitiveType.Quad);
            bgObj.name = "HudBackground";
            bgObj.transform.SetParent(transform, false);
            bgObj.transform.localScale = new Vector3(0.72f, 0.22f, 1f);
            Destroy(bgObj.GetComponent<Collider>());
            var bgMat = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            bgMat.color = new Color(0.02f, 0.05f, 0.10f, 0.20f); // 80% transparent
            bgObj.GetComponent<MeshRenderer>().material = bgMat;

            // Text backing strip — 30% transparent (70% opaque) so text stays readable
            var textBgObj = GameObject.CreatePrimitive(PrimitiveType.Quad);
            textBgObj.name = "TextBackground";
            textBgObj.transform.SetParent(transform, false);
            textBgObj.transform.localPosition = new Vector3(0f, 0f, 0.001f);
            textBgObj.transform.localScale = new Vector3(0.66f, 0.18f, 1f);
            Destroy(textBgObj.GetComponent<Collider>());
            var textBgMat = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            textBgMat.color = new Color(0.01f, 0.02f, 0.05f, 0.70f); // 30% transparent
            textBgObj.GetComponent<MeshRenderer>().material = textBgMat;

            // Status Indicator Pill (top right)
            var pillObj = GameObject.CreatePrimitive(PrimitiveType.Cube);
            pillObj.name = "StatusPill";
            pillObj.transform.SetParent(transform, false);
            pillObj.transform.localPosition = new Vector3(0.30f, 0.075f, -0.01f);
            pillObj.transform.localScale = new Vector3(0.04f, 0.02f, 0.01f);
            Destroy(pillObj.GetComponent<Collider>());
            _statusPillRenderer = pillObj.GetComponent<MeshRenderer>();
            _statusPillRenderer.material = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            _statusPillRenderer.material.color = Color.cyan;

            // Title line: "LUMAX // FOVEAI NEURAL HUD"
            var titleObj = new GameObject("TitleText");
            titleObj.transform.SetParent(transform, false);
            titleObj.transform.localPosition = new Vector3(-0.33f, 0.085f, -0.01f);
            titleObj.transform.localScale = Vector3.one * 0.007f;
            _titleText = titleObj.AddComponent<TextMesh>();
            _titleText.fontSize = 32;
            _titleText.color = new Color(0.3f, 0.85f, 1f);
            _titleText.text = "FOVEAI // ALICE NEURAL HUD";

            // VAD Audio Meter line (Center)
            var vadObj = new GameObject("VadMeterText");
            vadObj.transform.SetParent(transform, false);
            vadObj.transform.localPosition = new Vector3(-0.33f, 0.035f, -0.01f);
            vadObj.transform.localScale = Vector3.one * 0.0075f;
            _vadMeterText = vadObj.AddComponent<TextMesh>();
            _vadMeterText.fontSize = 32;
            _vadMeterText.color = Color.white;
            _vadMeterText.text = "MIC: [..........] IDLE";

            // Cognitive Status Line (Lower middle)
            var statusObj = new GameObject("StatusText");
            statusObj.transform.SetParent(transform, false);
            statusObj.transform.localPosition = new Vector3(-0.33f, -0.015f, -0.01f);
            statusObj.transform.localScale = Vector3.one * 0.0065f;
            _statusText = statusObj.AddComponent<TextMesh>();
            _statusText.fontSize = 28;
            _statusText.color = new Color(0.8f, 0.9f, 0.8f);
            _statusText.text = "SOUL: 8405 | MEMORY: 8400 | WEBSOCKET: 8403 | CHAT: 8407";

            // Controls Cheatsheet Line (Bottom)
            var controlsObj = new GameObject("ControlsText");
            controlsObj.transform.SetParent(transform, false);
            controlsObj.transform.localPosition = new Vector3(-0.33f, -0.065f, -0.01f);
            controlsObj.transform.localScale = Vector3.one * 0.0055f;
            _controlsText = controlsObj.AddComponent<TextMesh>();
            _controlsText.fontSize = 26;
            _controlsText.color = new Color(0.6f, 0.65f, 0.7f);
            _controlsText.text = "Right B: User Photo | Left Y: Alice POV Photo | Left Menu: Chat";
        }

        private void Update()
        {
            UpdatePosition();
            UpdateTelemetry();
        }

        private void UpdatePosition()
        {
            var cam = Camera.main;
            if (cam == null) return;

            Vector3 fwd = cam.transform.forward;
            fwd.y = 0;
            if (fwd.sqrMagnitude < 0.001f) fwd = Vector3.forward;
            fwd.Normalize();

            // Anchor below center gaze at set distance
            Vector3 targetPos = cam.transform.position + fwd * distance - Vector3.up * downOffset;
            transform.position = Vector3.Lerp(transform.position, targetPos, Time.deltaTime * followSpeed);

            // Always face the user's eyes
            Vector3 lookDir = transform.position - cam.transform.position;
            if (lookDir.sqrMagnitude > 0.001f)
            {
                transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(lookDir, Vector3.up), Time.deltaTime * followSpeed);
            }
        }

        private void UpdateTelemetry()
        {
            if (_vad == null) _vad = FindAnyObjectByType<QuestMicrophoneVAD>();
            if (_wsClient == null) _wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (_voice == null) _voice = FindAnyObjectByType<AvatarVoice>();

            // Handle flash banner (e.g. photo shutter or error)
            if (_flashTimer > 0f)
            {
                _flashTimer -= Time.deltaTime;
                _titleText.text = $"★ {_flashMessage.ToUpper()}";
                _titleText.color = Color.yellow;
            }
            else
            {
                _titleText.text = "FOVEAI // ALICE NEURAL HUD";
                _titleText.color = new Color(0.3f, 0.85f, 1f);
            }

            // Audio / VAD Meter calculation
            float rms = _vad != null ? _vad.CurrentRMS : 0f;
            bool isSpeaking = _voice != null && _voice.IsSpeaking;
            bool isRecording = _vad != null && _vad.IsRecordingSpeech;

            int totalBars = 12;
            int filledBars = Mathf.Clamp(Mathf.RoundToInt(rms * 150f), 0, totalBars);
            string meterBar = new string('|', filledBars) + new string('.', totalBars - filledBars);

            if (isSpeaking)
            {
                _vadMeterText.text = $"ALICE: [{meterBar}] SPEAKING...";
                _vadMeterText.color = new Color(1f, 0.4f, 0.9f); // Magenta
                _statusPillRenderer.material.color = new Color(1f, 0.4f, 0.9f);
            }
            else if (isRecording)
            {
                _vadMeterText.text = $"MIC:   [{meterBar}] RECORDING SPEECH";
                _vadMeterText.color = new Color(1f, 0.25f, 0.25f); // Red
                _statusPillRenderer.material.color = Color.red;
            }
            else
            {
                _vadMeterText.text = $"MIC:   [{meterBar}] LISTENING...";
                _vadMeterText.color = new Color(0.4f, 1f, 0.5f); // Green
                _statusPillRenderer.material.color = Color.green;
            }

            // Central WebSocket & Core status (8400 Cycle of Interaction)
            bool wsOk = _wsClient != null && _wsClient.IsConnected;
            string wsStatus = wsOk ? "ONLINE" : "CONNECTING...";
            int soulPort = FoveAI.Config.ConfigLoader.Settings != null ? FoveAI.Config.ConfigLoader.Settings.soulPort : 8405;
            int ipcPort = FoveAI.Config.ConfigLoader.Settings != null ? FoveAI.Config.ConfigLoader.Settings.wsPort : 8403;
            _statusText.text = $"SOUL:{soulPort} | MEMORY:8400 | WEBSOCKET:{ipcPort} [{wsStatus}]";
            _statusText.color = wsOk ? Color.white : new Color(1f, 0.7f, 0.2f);
        }
    }
}
