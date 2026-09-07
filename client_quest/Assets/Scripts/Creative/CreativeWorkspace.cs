using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using FoveAI.IPC;

namespace FoveAI.Creative
{
    /// <summary>
    /// Creative Workspace — collaborative creative tools for you and Alice.
    ///
    /// Modes:
    ///   1. Sketch — 3D drawing/painting in the air with controller
    ///   2. Build — place blocks/shapes collaboratively
    ///   3. Code — live code editor visible in VR, Alice can contribute
    ///   4. Music Jam — Alice controls ambient music while you create
    ///
    /// Alice can:
    ///   • Suggest ideas via chat → they appear as text in the workspace
    ///   • Spawn objects via motor events
    ///   • Change music mood based on creative flow
    ///   • Generate code snippets visible on the code panel
    /// </summary>
    public class CreativeWorkspace : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient webSocketClient;
        [SerializeField] private AmbientMusicPlayer musicPlayer;
        [SerializeField] private SceneManipulator sceneManipulator;

        [Header("Sketch Settings")]
        public Material lineMaterial;
        public float lineWidth = 0.01f;
        public Color drawColor = new Color(0.3f, 0.7f, 1f, 1f);
        public float minDrawDistance = 0.02f;

        [Header("Code Panel")]
        [SerializeField] private TMP_Text codeDisplay;
        [SerializeField] private Canvas codeCanvas;

        // ── State ──
        public enum CreativeMode { Sketch, Build, Code, MusicJam }
        public CreativeMode CurrentMode { get; private set; } = CreativeMode.Sketch;

        // Sketch state
        private bool _isDrawing;
        private LineRenderer _currentLine;
        private List<Vector3> _currentPoints = new List<Vector3>();
        private List<GameObject> _allLines = new List<GameObject>();
        private Color _currentColor;

        // Color palette
        private readonly Color[] _palette = {
            new Color(0.3f, 0.7f, 1f, 1f),   // Blue
            new Color(1f, 0.3f, 0.5f, 1f),   // Pink
            new Color(0.3f, 1f, 0.5f, 1f),   // Green
            new Color(1f, 0.8f, 0.2f, 1f),   // Yellow
            new Color(0.8f, 0.3f, 1f, 1f),   // Purple
            new Color(1f, 0.4f, 0.2f, 1f),   // Orange
            Color.white,
        };
        private int _colorIndex = 0;

        // Code state
        private readonly StringBuilder _codeBuffer = new StringBuilder();
        private int _maxCodeLines = 50;

        // Ideas/suggestions from Alice
        private readonly List<string> _ideas = new List<string>();

        private void Awake()
        {
            _currentColor = drawColor;
            if (webSocketClient == null)
                webSocketClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (musicPlayer == null)
                musicPlayer = FindAnyObjectByType<AmbientMusicPlayer>();
            if (sceneManipulator == null)
                sceneManipulator = FindAnyObjectByType<SceneManipulator>();
        }

        private void OnEnable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnChatTextReceived += OnAliceResponse;
                webSocketClient.OnRawMessageReceived += OnRawMessage;
            }
        }

        private void OnDisable()
        {
            if (webSocketClient != null)
            {
                webSocketClient.OnChatTextReceived -= OnAliceResponse;
                webSocketClient.OnRawMessageReceived -= OnRawMessage;
            }
        }

        private void Update()
        {
            switch (CurrentMode)
            {
                case CreativeMode.Sketch:
                    HandleSketchInput();
                    break;
                case CreativeMode.Build:
                    // SceneManipulator handles this
                    break;
                case CreativeMode.Code:
                    // Code panel visible, Alice can push code
                    break;
                case CreativeMode.MusicJam:
                    HandleMusicJamInput();
                    break;
            }

            // Mode switching with Y button
            if (OVRInput.GetDown(OVRInput.Button.Four, OVRInput.Controller.LTouch))
            {
                CycleMode();
            }

            // Color cycling with X button (sketch mode)
            if (CurrentMode == CreativeMode.Sketch && OVRInput.GetDown(OVRInput.Button.Three, OVRInput.Controller.LTouch))
            {
                CycleColor();
            }

            // Clear sketch with B button
            if (CurrentMode == CreativeMode.Sketch && OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch))
            {
                ClearSketch();
            }
        }

        // ── Mode Management ──

        public void SetMode(CreativeMode mode)
        {
            CurrentMode = mode;
            StopDrawing();

            switch (mode)
            {
                case CreativeMode.Sketch:
                    if (codeCanvas != null) codeCanvas.enabled = false;
                    Debug.Log("[Creative] Mode: Sketch — draw in the air with trigger");
                    break;
                case CreativeMode.Build:
                    if (codeCanvas != null) codeCanvas.enabled = false;
                    Debug.Log("[Creative] Mode: Build — use SceneManipulator controls");
                    break;
                case CreativeMode.Code:
                    if (codeCanvas != null) codeCanvas.enabled = true;
                    Debug.Log("[Creative] Mode: Code — Alice can contribute code");
                    break;
                case CreativeMode.MusicJam:
                    if (codeCanvas != null) codeCanvas.enabled = false;
                    if (musicPlayer != null) musicPlayer.Play();
                    Debug.Log("[Creative] Mode: Music Jam — A/X to change mood");
                    break;
            }
        }

        private void CycleMode()
        {
            CurrentMode = (CreativeMode)(((int)CurrentMode + 1) % 4);
            SetMode(CurrentMode);
        }

        // ── Sketch Mode ──

        private void HandleSketchInput()
        {
            bool trigger = OVRInput.Get(OVRInput.Axis1D.PrimaryIndexTrigger, OVRInput.Controller.RTouch) > 0.5f;
            Transform hand = GetHandTransform(OVRInput.Controller.RTouch);

            if (trigger && hand != null)
            {
                if (!_isDrawing)
                {
                    StartDrawing(hand.position);
                }

                AddPoint(hand.position);
            }
            else if (_isDrawing)
            {
                StopDrawing();
            }
        }

        private void StartDrawing(Vector3 startPos)
        {
            _isDrawing = true;
            _currentPoints.Clear();
            _currentPoints.Add(startPos);

            GameObject lineObj = new GameObject($"Sketch_{_allLines.Count}");
            _currentLine = lineObj.AddComponent<LineRenderer>();
            _currentLine.material = lineMaterial != null ? lineMaterial : new Material(Shader.Find("Sprites/Default"));
            _currentLine.startColor = _currentColor;
            _currentLine.endColor = _currentColor;
            _currentLine.startWidth = lineWidth;
            _currentLine.endWidth = lineWidth;
            _currentLine.positionCount = 1;
            _currentLine.SetPosition(0, startPos);
            _currentLine.useWorldSpace = true;

            _allLines.Add(lineObj);
        }

        private void AddPoint(Vector3 point)
        {
            if (_currentLine == null) return;

            // Only add if far enough from last point
            if (_currentPoints.Count > 0 && Vector3.Distance(_currentPoints[_currentPoints.Count - 1], point) < minDrawDistance)
                return;

            _currentPoints.Add(point);
            _currentLine.positionCount = _currentPoints.Count;
            _currentLine.SetPosition(_currentPoints.Count - 1, point);
        }

        private void StopDrawing()
        {
            _isDrawing = false;
            _currentLine = null;
        }

        private void ClearSketch()
        {
            foreach (var line in _allLines)
            {
                if (line != null) Destroy(line);
            }
            _allLines.Clear();
            Debug.Log("[Creative] Sketch cleared");
        }

        private void CycleColor()
        {
            _colorIndex = (_colorIndex + 1) % _palette.Length;
            _currentColor = _palette[_colorIndex];
            Debug.Log($"[Creative] Color: {_currentColor}");
        }

        // ── Music Jam Mode ──

        private void HandleMusicJamInput()
        {
            // A button: cycle mood
            if (OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
            {
                string[] moods = { "ambient", "calm", "happy", "focused", "energetic" };
                int idx = System.Array.IndexOf(moods, musicPlayer?.GetCurrentMood() ?? "ambient");
                idx = (idx + 1) % moods.Length;
                musicPlayer?.SetMood(moods[idx]);
                Debug.Log($"[Creative] Music mood: {moods[idx]}");
            }

            // B button: next track
            if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch))
            {
                musicPlayer?.NextTrack();
            }

            // Right stick up/down: volume
            Vector2 stick = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.RTouch);
            if (Mathf.Abs(stick.y) > 0.3f)
            {
                float vol = musicPlayer.volume + stick.y * Time.deltaTime * 0.5f;
                musicPlayer.SetVolume(Mathf.Clamp01(vol));
            }
        }

        // ── Alice Integration ──

        private void OnAliceResponse(string text)
        {
            // Alice can suggest creative ideas
            // If she says "let's try" or "how about" — add to ideas
            string lower = text.ToLowerInvariant();
            if (lower.Contains("let's try") || lower.Contains("how about") || lower.Contains("what if") || lower.Contains("idea"))
            {
                _ideas.Add(text);
                Debug.Log($"[Creative] Alice idea: {text}");
            }

            // Alice can change music mood based on conversation
            if (musicPlayer != null)
            {
                if (lower.Contains("relaxing") || lower.Contains("calm down")) musicPlayer.SetMood("calm");
                else if (lower.Contains("exciting") || lower.Contains("energetic")) musicPlayer.SetMood("energetic");
                else if (lower.Contains("focus") || lower.Contains("concentrate")) musicPlayer.SetMood("focused");
                else if (lower.Contains("happy") || lower.Contains("fun")) musicPlayer.SetMood("happy");
            }
        }

        private void OnRawMessage(string json)
        {
            // Alice can push code to the code panel
            if (json.Contains("\"creative.code\""))
            {
                string code = ExtractField(json, "code");
                if (!string.IsNullOrEmpty(code) && CurrentMode == CreativeMode.Code)
                {
                    AppendCode(code);
                }
            }

            // Alice can spawn objects
            if (json.Contains("\"creative.spawn\""))
            {
                string typeStr = ExtractField(json, "type");
                if (sceneManipulator != null && System.Enum.TryParse<PrimitiveType>(typeStr, true, out var type))
                {
                    // Parse position from payload
                    Vector3 pos = Camera.main != null
                        ? Camera.main.transform.position + Camera.main.transform.forward * 1.5f
                        : Vector3.zero;
                    sceneManipulator.SpawnAt(type, pos);
                }
            }
        }

        // ── Code Panel ──

        public void AppendCode(string code)
        {
            _codeBuffer.AppendLine(code);
            var lines = _codeBuffer.ToString().Split('\n');
            if (lines.Length > _maxCodeLines)
            {
                _codeBuffer.Clear();
                for (int i = lines.Length - _maxCodeLines; i < lines.Length; i++)
                    _codeBuffer.AppendLine(lines[i]);
            }

            if (codeDisplay != null)
                codeDisplay.text = _codeBuffer.ToString();
        }

        public void ClearCode()
        {
            _codeBuffer.Clear();
            if (codeDisplay != null) codeDisplay.text = "";
        }

        // ── Helpers ──

        private Transform GetHandTransform(OVRInput.Controller controller)
        {
            if (_tempTransform == null)
                _tempTransform = new GameObject("TempHand").transform;

            _tempTransform.position = OVRInput.GetLocalControllerPosition(controller);
            _tempTransform.rotation = OVRInput.GetLocalControllerRotation(controller);
            return _tempTransform;
        }

        private Transform _tempTransform;

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

        public void AddIdea(string idea) => _ideas.Add(idea);
        public List<string> GetIdeas() => _ideas;
        public int SketchCount => _allLines.Count;
    }
}
