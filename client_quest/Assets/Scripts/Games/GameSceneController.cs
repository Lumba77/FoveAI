using UnityEngine;
using UnityEngine.UI;
using TMPro;
using FoveAI.IPC;
using FoveAI.UI;

namespace FoveAI.Games
{
    /// <summary>
    /// Game & Scene Controller Panel — grabbable VR panel to launch games
    /// and apply scene presets. Alice can also trigger these via WebSocket.
    /// </summary>
    [RequireComponent(typeof(Canvas))]
    public class GameSceneController : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private VRGameEngine gameEngine;
        [SerializeField] private ScenePresetManager presetManager;
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private FoveAI.Presence.CoPresenceMode coPresence;

        [Header("Panel")]
        [Range(0f, 1f)] public float panelAlpha = 0.95f;
        public float panelWidth = 600f;
        public float panelHeight = 700f;

        private Canvas _canvas;
        private CanvasGroup _canvasGroup;
        private TMP_FontAsset _font;
        private TMP_Text _statusText;

        private void Awake()
        {
            _font = TMP_Settings.defaultFontAsset;
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

            if (gameEngine == null) gameEngine = FindAnyObjectByType<VRGameEngine>();
            if (presetManager == null) presetManager = FindAnyObjectByType<ScenePresetManager>();
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (coPresence == null) coPresence = FindAnyObjectByType<FoveAI.Presence.CoPresenceMode>();

            BuildUI();

            if (wsClient != null)
                wsClient.OnRawMessageReceived += OnRawMessage;
        }

        private void OnDestroy()
        {
            if (wsClient != null)
                wsClient.OnRawMessageReceived -= OnRawMessage;
        }

        private void OnRawMessage(string json)
        {
            if (json.Contains("\"game.start\""))
            {
                string mode = ExtractField(json, "mode");
                if (!string.IsNullOrEmpty(mode) && gameEngine != null)
                {
                    if (System.Enum.TryParse<VRGameEngine.GameMode>(mode, true, out var gm))
                        gameEngine.StartGame(gm);
                }
            }
            else if (json.Contains("\"game.stop\""))
            {
                gameEngine?.StopGame();
            }
            else if (json.Contains("\"scene.preset\""))
            {
                string preset = ExtractField(json, "preset");
                if (!string.IsNullOrEmpty(preset) && presetManager != null)
                    presetManager.AliceApplyPreset(preset);
            }
            else if (json.Contains("\"scene.clear\""))
            {
                presetManager?.ClearPreset();
            }
        }

        private void BuildUI()
        {
            // Background
            var bgGo = new GameObject("Bg");
            bgGo.transform.SetParent(transform, false);
            var bgImg = bgGo.AddComponent<Image>();
            bgImg.color = new Color(0.04f, 0.06f, 0.10f, 0.95f);
            var bgRt = bgGo.GetComponent<RectTransform>();
            bgRt.anchorMin = Vector2.zero;
            bgRt.anchorMax = Vector2.one;
            bgRt.offsetMin = Vector2.zero;
            bgRt.offsetMax = Vector2.zero;

            // Title
            var titleGo = new GameObject("Title");
            titleGo.transform.SetParent(transform, false);
            var titleImg = titleGo.AddComponent<Image>();
            titleImg.color = new Color(0.08f, 0.12f, 0.18f, 1f);
            var titleRt = titleGo.GetComponent<RectTransform>();
            titleRt.anchorMin = new Vector2(0, 1);
            titleRt.anchorMax = new Vector2(1, 1);
            titleRt.sizeDelta = new Vector2(0, 44f);
            titleRt.offsetMin = Vector2.zero;
            titleRt.offsetMax = Vector2.zero;

            var titleText = titleGo.AddComponent<TextMeshProUGUI>();
            titleText.font = _font;
            titleText.fontSize = 22;
            titleText.color = new Color(0.3f, 0.7f, 1f, 1f);
            titleText.text = "🎮 GAMES & SCENES";
            titleText.alignment = TextAlignmentOptions.Center;

            // Content
            float y = -60f;

            // Games section
            y = AddSectionHeader("GAMES", y);
            y = AddButton("Monster Hunt", "Shoot monsters from walls!", y, () => gameEngine?.StartGame(VRGameEngine.GameMode.MonsterHunt), new Color(0.5f, 0.1f, 0.1f, 1f));
            y = AddButton("Target Practice", "Hit floating targets", y, () => gameEngine?.StartGame(VRGameEngine.GameMode.TargetPractice), new Color(0.1f, 0.3f, 0.5f, 1f));
            y = AddButton("Companion Mode", "Spawn friendly characters", y, () => gameEngine?.StartGame(VRGameEngine.GameMode.CharacterCompanion), new Color(0.1f, 0.4f, 0.2f, 1f));
            y = AddButton("Stop Game", "End current game", y, () => gameEngine?.StopGame(), new Color(0.3f, 0.15f, 0.15f, 1f));

            y -= 10f;

            // Scene presets section
            y = AddSectionHeader("SCENE PRESETS", y);
            y = AddButton("❤ Romance", "Candles, petals, soft music", y, () => presetManager?.ApplyPreset(ScenePresetManager.Preset.Romance), new Color(0.5f, 0.15f, 0.25f, 1f));
            y = AddButton("🎬 Movie Night", "Big screen, dim lights, popcorn", y, () => presetManager?.ApplyPreset(ScenePresetManager.Preset.MovieNight), new Color(0.15f, 0.1f, 0.25f, 1f));
            y = AddButton("🏠 Cozy Home", "Fireplace, lamp, plants", y, () => presetManager?.ApplyPreset(ScenePresetManager.Preset.CozyHome), new Color(0.4f, 0.25f, 0.1f, 1f));
            y = AddButton("✨ Tidy Room", "Clean organized overlay", y, () => presetManager?.ApplyPreset(ScenePresetManager.Preset.TidyRoom), new Color(0.2f, 0.25f, 0.3f, 1f));
            y = AddButton("🎉 Party", "Colorful lights, confetti", y, () => presetManager?.ApplyPreset(ScenePresetManager.Preset.Party), new Color(0.4f, 0.1f, 0.5f, 1f));
            y = AddButton("🧘 Zen Garden", "Floating orbs, calm vibes", y, () => presetManager?.ApplyPreset(ScenePresetManager.Preset.ZenGarden), new Color(0.15f, 0.3f, 0.25f, 1f));
            y = AddButton("💼 Workspace", "Bright, focused, tools", y, () => presetManager?.ApplyPreset(ScenePresetManager.Preset.Workspace), new Color(0.25f, 0.3f, 0.35f, 1f));
            y = AddButton("Clear Scene", "Remove all preset objects", y, () => presetManager?.ClearPreset(), new Color(0.2f, 0.2f, 0.2f, 1f));

            y -= 10f;

            // Co-presence section
            y = AddSectionHeader("COMPANIONSHIP", y);
            y = AddButton("🤍 Just Be Here", "Co-presence mode — quiet, mundane, together", y, () => coPresence?.StartCoPresence(), new Color(0.15f, 0.2f, 0.3f, 1f));
            y = AddButton("💬 Talk Again", "Exit co-presence, back to normal", y, () => coPresence?.StopCoPresence(), new Color(0.2f, 0.25f, 0.2f, 1f));

            // Status
            var statusGo = new GameObject("Status");
            statusGo.transform.SetParent(transform, false);
            _statusText = statusGo.AddComponent<TextMeshProUGUI>();
            _statusText.font = _font;
            _statusText.fontSize = 14;
            _statusText.color = new Color(0.6f, 0.65f, 0.75f, 1f);
            _statusText.alignment = TextAlignmentOptions.Center;
            var statusRt = statusGo.GetComponent<RectTransform>();
            statusRt.anchorMin = new Vector2(0, 0);
            statusRt.anchorMax = new Vector2(1, 0);
            statusRt.sizeDelta = new Vector2(0, 30f);
            statusRt.anchoredPosition = new Vector2(0, 8f);
        }

        private float AddSectionHeader(string title, float y)
        {
            var go = new GameObject($"Section_{title}");
            go.transform.SetParent(transform, false);
            var txt = go.AddComponent<TextMeshProUGUI>();
            txt.font = _font;
            txt.fontSize = 18;
            txt.color = new Color(0.3f, 0.7f, 1f, 1f);
            txt.text = title;
            txt.alignment = TextAlignmentOptions.Left;
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 1);
            rt.anchorMax = new Vector2(1, 1);
            rt.sizeDelta = new Vector2(-20f, 28f);
            rt.anchoredPosition = new Vector2(10f, y);
            return y - 36f;
        }

        private float AddButton(string label, string subtitle, float y, System.Action onClick, Color color)
        {
            var go = new GameObject($"Btn_{label}");
            go.transform.SetParent(transform, false);
            var img = go.AddComponent<Image>();
            img.color = color;
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;
            btn.onClick.AddListener(() => { onClick?.Invoke(); UpdateStatus(); });

            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 1);
            rt.anchorMax = new Vector2(1, 1);
            rt.sizeDelta = new Vector2(-20f, 44f);
            rt.anchoredPosition = new Vector2(10f, y);

            var labelGo = new GameObject("Label");
            labelGo.transform.SetParent(go.transform, false);
            var labelTxt = labelGo.AddComponent<TextMeshProUGUI>();
            labelTxt.font = _font;
            labelTxt.fontSize = 16;
            labelTxt.color = Color.white;
            labelTxt.text = label;
            labelTxt.alignment = TextAlignmentOptions.Left;
            var labelRt = labelGo.GetComponent<RectTransform>();
            labelRt.anchorMin = new Vector2(0, 0.5f);
            labelRt.anchorMax = new Vector2(0.6f, 0.5f);
            labelRt.sizeDelta = new Vector2(0, 24f);
            labelRt.offsetMin = new Vector2(12, 0);
            labelRt.offsetMax = Vector2.zero;
            labelRt.anchoredPosition = new Vector2(0, 4f);

            var subGo = new GameObject("Sub");
            subGo.transform.SetParent(go.transform, false);
            var subTxt = subGo.AddComponent<TextMeshProUGUI>();
            subTxt.font = _font;
            subTxt.fontSize = 12;
            subTxt.color = new Color(1, 1, 1, 0.6f);
            subTxt.text = subtitle;
            subTxt.alignment = TextAlignmentOptions.Right;
            var subRt = subGo.GetComponent<RectTransform>();
            subRt.anchorMin = new Vector2(0.5f, 0.5f);
            subRt.anchorMax = new Vector2(1, 0.5f);
            subRt.sizeDelta = new Vector2(0, 20f);
            subRt.offsetMax = new Vector2(-12, 0);
            subRt.anchoredPosition = new Vector2(0, -2f);

            return y - 50f;
        }

        private void UpdateStatus()
        {
            if (_statusText == null) return;
            string game = gameEngine != null && gameEngine.IsActive ? gameEngine.CurrentMode.ToString() : "None";
            string preset = presetManager != null ? presetManager.CurrentPreset.ToString() : "None";
            string presence = coPresence != null && coPresence.IsActive ? "Co-presence" : "Normal";
            _statusText.text = $"Game: {game}  |  Scene: {preset}  |  {presence}";
        }

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
    }
}
