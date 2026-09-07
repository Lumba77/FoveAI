using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using FoveAI.IPC;

// =============================================================================
//  TerminalIDE  -  Vibe Coder Glassboard
//  Layout: Left 50% = Live Code | Right-top = File Manager | Right-bot = Status
//  Controls: Y/B button = toggle | Edit button at bottom = keyboard mode stub
//
//  SCALE NOTE:
//    Canvas sizeDelta = (2000, 3000) canvas-units
//    localScale       = 0.001f
//    => Physical size = 2 m wide x 3 m tall in world space
//    fontSize 32 canvas-units => 32 mm char height => legible from 2-3 m
// =============================================================================

namespace FoveAI.UI
{
    public class TerminalIDE : MonoBehaviour
    {
        [Header("Dependencies")]
        public FoveAIWebSocketClient wsClient;

        [Header("Positioning")]
        [Tooltip("Distance in front of origin the glassboard floats (metres)")]
        public float boardDepth = 4.0f;
        [Tooltip("Vertical offset of board BOTTOM from world Y=0 (metres). 0 = floor.")]
        public float floorOffset = 0.08f;
        public float smoothSpeed = 2.5f;

        // -- Internal UI refs --
        private GameObject _canvasObj;
        private Text _codeText;
        private Text _fileListText;
        private Text _themeStatusText;
        private Button _editModeBtn;
        private Text _editModeBtnLabel;
        private bool _isVisible = false;
        private bool _editModeActive = false;

        // -- Palette --
        private readonly Color _cyan     = new Color(0.00f, 0.90f, 1.00f, 1.0f);
        private readonly Color _green    = new Color(0.20f, 1.00f, 0.50f, 1.0f);
        private readonly Color _dimWhite = new Color(1.00f, 1.00f, 1.00f, 0.85f);
        private readonly Color _panelBg  = new Color(0.08f, 0.08f, 0.12f, 0.72f);
        private readonly Color _editActive   = new Color(0.63f, 0.13f, 0.94f, 0.9f);
        private readonly Color _editInactive = new Color(0.10f, 0.10f, 0.14f, 0.9f);

        // -- Data --
        private readonly List<string> _codeLines   = new List<string>();
        private readonly List<string> _fileLines   = new List<string>();
        private readonly List<string> _statusLines = new List<string>();
        private const int MaxCodeLines   = 40;
        private const int MaxFileLines   = 20;
        private const int MaxStatusLines = 15;

        // =====================================================================
        //  Lifecycle
        // =====================================================================
        private void Awake()
        {
            if (wsClient == null)
                wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            BuildCanvas();
        }

        private void OnEnable()
        {
            if (wsClient != null) wsClient.OnRawMessageReceived += HandleMessage;
        }

        private void OnDisable()
        {
            if (wsClient != null) wsClient.OnRawMessageReceived -= HandleMessage;
        }

        // =====================================================================
        //  Canvas Construction
        // =====================================================================
        private void BuildCanvas()
        {
            _canvasObj = new GameObject("TerminalIDECanvas");
            _canvasObj.transform.SetParent(this.transform, false);

            Canvas canvas = _canvasObj.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            _canvasObj.AddComponent<GraphicRaycaster>();

            // 1 canvas-unit = 1 mm in world space (scale 0.001)
            const float CANVAS_W = 2000f;
            const float CANVAS_H = 3000f;
            const float SCALE    = 0.001f;

            RectTransform rect = _canvasObj.GetComponent<RectTransform>();
            rect.sizeDelta = new Vector2(CANVAS_W, CANVAS_H);
            rect.pivot = new Vector2(0.5f, 0f); // pivot at bottom-centre

            _canvasObj.transform.localScale = Vector3.one * SCALE;
            _canvasObj.transform.localPosition = new Vector3(
                0f,
                floorOffset / SCALE,
                boardDepth  / SCALE
            );

            // CanvasScaler: ConstantPixelSize so Unity never overrides fontSize
            var scaler = _canvasObj.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ConstantPixelSize;
            scaler.scaleFactor = 1f;

            Image bg = _canvasObj.AddComponent<Image>();
            bg.color = new Color(0.05f, 0.05f, 0.08f, 0.15f);

            // Left 50%: Code Viewer
            GameObject leftPane = MakePanel("CodeViewer",
                _canvasObj.transform,
                new Vector2(0f,    0f), new Vector2(0.5f, 1f));

            // Right-top 60%: File Manager
            GameObject rightTop = MakePanel("FileManager",
                _canvasObj.transform,
                new Vector2(0.51f, 0.38f), new Vector2(1f, 1f));

            // Right-bottom 40%: Theme / Status
            GameObject rightBot = MakePanel("ThemeStatus",
                _canvasObj.transform,
                new Vector2(0.51f, 0f), new Vector2(1f, 0.37f));

            // Font sizes in canvas-units (= mm at 0.001 scale)
            _codeText        = MakeText("CodeText",        leftPane.transform,  _cyan,     32);
            _fileListText    = MakeText("FileListText",    rightTop.transform,  _dimWhite, 30);
            _themeStatusText = MakeText("ThemeStatusText", rightBot.transform,  _green,    28);

            _codeText.text =
                "<color=#00E8FF>VIBE CODER - LIVE CODE VIEW</color>\n" +
                "<color=#888888>// Waiting for Alicechan to push changes...</color>\n" +
                "// AI is your pair programmer.\n" +
                "// Code appears here in real-time.\n";

            _fileListText.text =
                "FILE MANAGER\n" +
                "----------------------------\n" +
                "  AutoSceneBuilder.cs\n" +
                "  TerminalIDE.cs\n" +
                "  AvatarIKController.cs\n" +
                "  Quest3TTSClient.cs\n" +
                "  Quest3STTClient.cs\n" +
                "  AvatarPuppetDriver.cs\n\n" +
                "<color=#888888>(Laser-point to open - WIP)</color>";

            _themeStatusText.text =
                "<color=#33FF80>THEMES / STATUS</color>\n" +
                "------------------\n" +
                "  [*] LUMAX Cyan\n" +
                "  [ ] Midnight Purple\n" +
                "  [ ] Ghost White\n\n" +
                "<color=#888888>AI Status: Idle</color>";

            BuildEditButton(_canvasObj.transform);
            _canvasObj.SetActive(_isVisible);
        }

        // =====================================================================
        //  UI Helpers
        // =====================================================================
        private GameObject MakePanel(string name, Transform parent,
                                     Vector2 anchorMin, Vector2 anchorMax)
        {
            GameObject go = new GameObject(name);
            go.transform.SetParent(parent, false);

            RectTransform r = go.AddComponent<RectTransform>();
            r.anchorMin = anchorMin;
            r.anchorMax = anchorMax;
            r.offsetMin = new Vector2( 12,  12);
            r.offsetMax = new Vector2(-12, -12);

            Image img = go.AddComponent<Image>();
            img.color = _panelBg;

            Outline o = go.AddComponent<Outline>();
            o.effectColor    = new Color(_cyan.r, _cyan.g, _cyan.b, 0.35f);
            o.effectDistance = new Vector2(3, -3);

            return go;
        }

        private Text MakeText(string name, Transform parent, Color color, int fontSize)
        {
            GameObject go = new GameObject(name);
            go.transform.SetParent(parent, false);

            RectTransform r = go.AddComponent<RectTransform>();
            r.anchorMin = Vector2.zero;
            r.anchorMax = Vector2.one;
            r.offsetMin = new Vector2(30, 30);
            r.offsetMax = new Vector2(-30, -30);

            Text t = go.AddComponent<Text>();
            t.font                 = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            t.color                = color;
            t.fontSize             = fontSize;
            t.lineSpacing          = 1.3f;
            t.alignment            = TextAnchor.UpperLeft;
            t.supportRichText      = true;
            t.resizeTextForBestFit = false; // CRITICAL: prevents Unity overriding fontSize
            return t;
        }

        private void BuildEditButton(Transform canvasParent)
        {
            GameObject btnGo = new GameObject("EditModeButton");
            btnGo.transform.SetParent(canvasParent, false);

            RectTransform r = btnGo.AddComponent<RectTransform>();
            r.anchorMin = new Vector2(0.25f, 0f);
            r.anchorMax = new Vector2(0.75f, 0f);
            r.pivot     = new Vector2(0.5f, 0f);
            r.offsetMin = new Vector2(0,  20);
            r.offsetMax = new Vector2(0, 150);

            Image img = btnGo.AddComponent<Image>();
            img.color = _editInactive;

            _editModeBtn = btnGo.AddComponent<Button>();
            _editModeBtn.onClick.AddListener(ToggleEditMode);

            GameObject lblGo = new GameObject("Label");
            lblGo.transform.SetParent(btnGo.transform, false);
            RectTransform lr = lblGo.AddComponent<RectTransform>();
            lr.anchorMin = Vector2.zero;
            lr.anchorMax = Vector2.one;

            _editModeBtnLabel = lblGo.AddComponent<Text>();
            _editModeBtnLabel.font                 = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            _editModeBtnLabel.text                 = "REQUEST EDIT MODE";
            _editModeBtnLabel.fontSize             = 28;
            _editModeBtnLabel.color                = _dimWhite;
            _editModeBtnLabel.alignment            = TextAnchor.MiddleCenter;
            _editModeBtnLabel.resizeTextForBestFit = false;
        }

        // =====================================================================
        //  Update
        // =====================================================================
        private void Update()
        {
            if (OVRInput.GetDown(OVRInput.Button.Four) ||
                OVRInput.GetDown(OVRInput.Button.SecondaryThumbstick))
            {
                _isVisible = !_isVisible;
                _canvasObj.SetActive(_isVisible);
            }

            // Yaw-only billboard: board stays perfectly vertical
            if (_isVisible && Camera.main != null)
            {
                Vector3 dir = _canvasObj.transform.position - Camera.main.transform.position;
                dir.y = 0f;
                if (dir.sqrMagnitude > 0.01f)
                {
                    Quaternion target = Quaternion.LookRotation(dir);
                    _canvasObj.transform.rotation = Quaternion.Slerp(
                        _canvasObj.transform.rotation, target, Time.deltaTime * smoothSpeed);
                }
            }
        }

        // =====================================================================
        //  Edit Mode
        // =====================================================================
        private void ToggleEditMode()
        {
            _editModeActive = !_editModeActive;

            if (_editModeBtn != null)
            {
                var c = _editModeBtn.colors;
                c.normalColor    = _editModeActive ? _editActive : _editInactive;
                _editModeBtn.colors = c;
            }

            if (_editModeBtnLabel != null)
                _editModeBtnLabel.text = _editModeActive
                    ? "EDIT MODE ACTIVE  (tap again to exit)"
                    : "REQUEST EDIT MODE";

            // TODO: wire OVR virtual keyboard or Meta system keyboard
            Debug.Log($"[TerminalIDE] Edit mode => {_editModeActive}");
        }

        // =====================================================================
        //  WebSocket message routing
        // =====================================================================
        private void HandleMessage(string raw)
        {
            if (!raw.Contains("\"event\":")) return;

            if (raw.Contains("\"log\"") || raw.Contains("\"code\""))
                PushCodeLine(raw);
            else if (raw.Contains("\"file\""))
                PushFileLine(raw);
            else if (raw.Contains("\"chat\"") || raw.Contains("\"think\""))
                PushStatusLine(raw);
        }

        private void PushCodeLine(string line)
        {
            if (_codeLines.Count >= MaxCodeLines) _codeLines.RemoveAt(0);
            _codeLines.Add(Trim(line, 90));
            if (_codeText != null) _codeText.text = string.Join("\n", _codeLines);
        }

        private void PushFileLine(string line)
        {
            if (_fileLines.Count >= MaxFileLines) _fileLines.RemoveAt(0);
            _fileLines.Add("  " + Trim(line, 50));
            if (_fileListText != null)
                _fileListText.text = "FILE MANAGER\n----------------------------\n" +
                                     string.Join("\n", _fileLines);
        }

        private void PushStatusLine(string line)
        {
            if (_statusLines.Count >= MaxStatusLines) _statusLines.RemoveAt(0);
            _statusLines.Add(Trim(line, 60));
            if (_themeStatusText != null)
                _themeStatusText.text = "<color=#33FF80>AI STATUS</color>\n------------------\n" +
                                        string.Join("\n", _statusLines);
        }

        private static string Trim(string s, int max) =>
            s.Length > max ? s.Substring(0, max) + "..." : s;
    }
}
