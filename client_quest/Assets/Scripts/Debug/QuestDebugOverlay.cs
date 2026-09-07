using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR;

namespace FoveAI.DebugOverlay
{
    /// <summary>
    /// On-screen debug overlay for Quest 3 — uses TextMesh (3D text) which has
    /// a built-in font that works on Android without any font asset loading.
    /// Shows a colored status cube (green=OK, yellow=warning, red=error).
    /// Panel is VERTICAL, facing the camera.
    /// </summary>
    public class QuestDebugOverlay : MonoBehaviour
    {
        private static QuestDebugOverlay _instance;
        private static readonly List<string> _logs = new List<string>();
        private static readonly int _maxLogs = 18;
        private TextMesh _textMesh;
        private Transform _rootTransform;
        private static Color _statusColor = Color.green;
        private static GameObject _statusCube;
        private static bool _overlayVisible = false; // Hidden by default — shown on error or env flag
        private static bool _hasError = false;

        public static void Log(string msg)
        {
            _logs.Add($"[{System.DateTime.Now:HH:mm:ss}] {msg}");
            if (_logs.Count > _maxLogs) _logs.RemoveAt(0);
            UpdateDisplay();
        }

        public static void LogError(string msg)
        {
            _logs.Add($"[{System.DateTime.Now:HH:mm:ss}] ERR: {msg}");
            if (_logs.Count > _maxLogs) _logs.RemoveAt(0);
            _statusColor = Color.red;
            _hasError = true;
            if (!_overlayVisible) { _overlayVisible = true; SetOverlayActive(true); }
            UpdateDisplay();
            UpdateStatusCube();
        }

        public static void LogWarning(string msg)
        {
            _logs.Add($"[{System.DateTime.Now:HH:mm:ss}] WRN: {msg}");
            if (_logs.Count > _maxLogs) _logs.RemoveAt(0);
            if (_statusColor != Color.red) _statusColor = Color.yellow;
            UpdateDisplay();
            UpdateStatusCube();
        }

        private void Awake()
        {
            if (_instance != null && _instance != this) { Destroy(gameObject); return; }
            _instance = this;
            DontDestroyOnLoad(gameObject);
            CreateOverlay();
        }

        private void CreateOverlay()
        {
            // Root transform — everything is a child of this
            _rootTransform = transform;

            // Check env flag to force-show overlay (for debugging)
            // On Quest, env vars aren't available, so we check a build-time flag instead
            #if FOVEAI_DEBUG_OVERLAY
            _overlayVisible = true;
            #endif

            // === Status Cube (always visible, no font needed) ===
            _statusCube = GameObject.CreatePrimitive(PrimitiveType.Cube);
            _statusCube.name = "StatusCube";
            _statusCube.transform.SetParent(_rootTransform, false);
            _statusCube.transform.localScale = new Vector3(0.08f, 0.08f, 0.08f);
            _statusCube.transform.localPosition = new Vector3(0, 0.55f, -0.02f);
            Destroy(_statusCube.GetComponent<BoxCollider>());
            var cubeRenderer = _statusCube.GetComponent<MeshRenderer>();
            cubeRenderer.material = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            cubeRenderer.material.color = _statusColor;

            // === Background quad (VERTICAL, facing -Z toward camera) ===
            // Use a Quad instead of Plane — Quad is vertical by default
            var bgObj = GameObject.CreatePrimitive(PrimitiveType.Quad);
            bgObj.name = "DebugBG";
            bgObj.transform.SetParent(_rootTransform, false);
            bgObj.transform.localScale = new Vector3(1.2f, 0.8f, 1f);
            bgObj.transform.localPosition = new Vector3(0, 0, 0.05f);
            Destroy(bgObj.GetComponent<MeshCollider>());
            var bgRenderer = bgObj.GetComponent<MeshRenderer>();
            bgRenderer.material = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            bgRenderer.material.color = new Color(0.02f, 0.02f, 0.02f);

            // === TextMesh (3D text — built-in font, works on Android) ===
            // Quad faces -Z by default, so text should also face -Z (no rotation needed)
            var textObj = new GameObject("DebugText");
            textObj.transform.SetParent(_rootTransform, false);
            textObj.transform.localPosition = new Vector3(-0.55f, 0.35f, 0.04f);
            textObj.transform.localRotation = Quaternion.identity; // Face -Z (toward camera)
            textObj.transform.localScale = new Vector3(0.015f, 0.015f, 0.015f);
            _textMesh = textObj.AddComponent<TextMesh>();
            _textMesh.fontSize = 48;
            _textMesh.color = Color.white;
            _textMesh.anchor = TextAnchor.UpperLeft;
            _textMesh.alignment = TextAlignment.Left;
            _textMesh.characterSize = 0.3f;
            _textMesh.tabSize = 4;
            _textMesh.lineSpacing = 1.2f;

            // Initial logs
            Log("=== FOVEAI DEBUG ===");
            Log("Overlay init OK");
            Log($"Dev: {SystemInfo.deviceModel}");
            Log($"VR: {UnityEngine.XR.XRSettings.isDeviceActive}");
            Log($"XR: {UnityEngine.XR.XRSettings.loadedDeviceName}");
            Log("=== COMPONENTS ===");

            UpdateDisplay();
            SetOverlayActive(_overlayVisible);
        }

        private static void SetOverlayActive(bool active)
        {
            if (_instance == null || _instance._rootTransform == null) return;
            _instance._rootTransform.gameObject.SetActive(active);
        }

        private static void UpdateDisplay()
        {
            if (_instance == null || _instance._textMesh == null) return;
            _instance._textMesh.text = string.Join("\n", _logs);
        }

        private static void UpdateStatusCube()
        {
            if (_statusCube == null) return;
            var r = _statusCube.GetComponent<MeshRenderer>();
            if (r != null) r.material.color = _statusColor;
        }

        private void Update()
        {
            CheckRuntimeToggle();
            if (!_overlayVisible || _rootTransform == null || Camera.main == null) return;
            // Follow camera at fixed distance, always facing
            Vector3 targetPos = Camera.main.transform.position + Camera.main.transform.forward * 2.1f - Camera.main.transform.right * 1.15f + Camera.main.transform.up * 0.15f;
            _rootTransform.position = Vector3.Lerp(_rootTransform.position, targetPos, Time.deltaTime * 3f);
            // Make the panel face the camera (Z axis points away from camera)
            _rootTransform.rotation = Quaternion.LookRotation(_rootTransform.position - Camera.main.transform.position);
        }

        private void OnEnable()
        {
            Application.logMessageReceived += HandleUnityLog;
        }

        private void OnDisable()
        {
            Application.logMessageReceived -= HandleUnityLog;
        }

        private void HandleUnityLog(string logString, string stackTrace, LogType type)
        {
            if (type == LogType.Error || type == LogType.Exception)
            {
                string shortMsg = logString.Length > 120 ? logString.Substring(0, 120) + "..." : logString;
                LogError(shortMsg);
            }
        }

        // Runtime toggle: press both controller triggers simultaneously to show/hide overlay
        private bool _leftTrigger;
        private bool _rightTrigger;
        private bool _toggleCooldown;
        private void CheckRuntimeToggle()
        {
            var leftDevs = new System.Collections.Generic.List<InputDevice>();
            var rightDevs = new System.Collections.Generic.List<InputDevice>();
            InputDevices.GetDevicesWithCharacteristics(InputDeviceCharacteristics.Left | InputDeviceCharacteristics.Controller, leftDevs);
            InputDevices.GetDevicesWithCharacteristics(InputDeviceCharacteristics.Right | InputDeviceCharacteristics.Controller, rightDevs);

            bool leftPressed = false, rightPressed = false;
            if (leftDevs.Count > 0 && leftDevs[0].TryGetFeatureValue(CommonUsages.triggerButton, out bool l)) leftPressed = l;
            if (rightDevs.Count > 0 && rightDevs[0].TryGetFeatureValue(CommonUsages.triggerButton, out bool r)) rightPressed = r;

            if (leftPressed && rightPressed && !_toggleCooldown)
            {
                _overlayVisible = !_overlayVisible;
                SetOverlayActive(_overlayVisible);
                _toggleCooldown = true;
            }
            if (!leftPressed || !rightPressed) _toggleCooldown = false;
        }
    }
}
