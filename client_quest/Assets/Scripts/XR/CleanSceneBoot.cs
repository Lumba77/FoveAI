using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR;
using UnityEngine.XR.Hands;
using FoveAI.DebugOverlay;

namespace FoveAI.XR
{
    /// <summary>
    /// CleanSceneBoot — Master boot controller for a clean, minimal FoveAI XR experience.
    ///
    /// At boot:
    ///   - Hides ALL panels (chat, settings, HUD, browser, spatial, game controller, relay)
    ///   - Leaves only Alice (AvatarContainer) visible
    ///   - Starts instant VAD
    ///   - Ensures controller + hand rays point forward and are collidable
    ///
    /// Runtime controls:
    ///   - Left controller Menu button  → Toggle Settings panel
    ///   - Left hand pinch             → Toggle Settings panel
    ///   - Right controller Menu button → Toggle Chat panel
    ///   - Right hand pinch            → Toggle Chat panel
    ///   - Panels auto-position in front of user when opened
    ///   - Only one panel visible at a time
    /// </summary>
    public class CleanSceneBoot : MonoBehaviour
    {
        [Header("Panel References (auto-found if null)")]
        [SerializeField] private GameObject settingsPanel;
        [SerializeField] private GameObject chatPanel;
        [SerializeField] private GameObject avatarContainer;

        [Header("Debris Panels to Hide at Boot")]
        [SerializeField] private string[] debrisPanelNames = {
            "AppSettings_Panel",
            "AdvancedSpatial_Panel",
            "GameSceneController_Panel",
            "VRBrowser_Panel",
            "UserHUD_System",
            "ChatRelayPanel",
            // ChatCanvas is deliberately NOT debris: it is the app's primary
            // surface. Hiding it at boot left the headset showing pure
            // passthrough with nothing to interact with, and the panel's
            // authored local position (+Z) put it behind the camera anyway.
            // It is placed in front of the user at boot instead — see
            // ShowPrimarySurface().
        };

        [Header("Panel Positioning")]
        [SerializeField] private float panelDistance = 1.2f;
        [SerializeField] private float panelSideOffset = 0.6f;
        [SerializeField] private float panelHeight = 0.05f;
        [Header("WebUI Panel Placement")]
        [SerializeField] private float webPanelSideOffset = 0.72f;
        [SerializeField] private float webPanelHeight = -0.08f;

        [Header("Hand Pinch Detection")]
        [SerializeField] private float pinchThreshold = 0.8f;

        [Header("Web UI Panel")]
        [SerializeField] private string webUiBase = "http://192.168.8.109:5177";

        private FoveAI.UI.WebViewPanel webPanel;
        private string ChatUrl => webUiBase + "/chat";
        private string SettingsUrl => webUiBase + "/settings";

        // ── Input System paths ──────────────────────────────────────
        // This project ships the NEW Input System only (activeInputHandler: 1)
        // and UnityEngine.InputLegacyModule is not installed, so
        // InputDevices.GetDevicesWithCharacteristics always returned an empty
        // list: the menu-button and pinch toggles below could never fire and
        // the summoned panels were unreachable. Bind the same actions the
        // working XRRigFixer uses, on <XRController>{LeftHand|RightHand}.
        private UnityEngine.InputSystem.InputAction _leftMenuAction;
        private UnityEngine.InputSystem.InputAction _rightMenuAction;
        private UnityEngine.InputSystem.InputAction _leftGripAction;
        private UnityEngine.InputSystem.InputAction _rightGripAction;
        private bool _leftMenuPressed;
        private bool _rightMenuPressed;
        private bool _leftPinchActive;
        private bool _rightPinchActive;
        private GameObject _activePanel;
        private XRHandSubsystem _handSubsystem;
        private readonly List<XRHandSubsystem> _handSubsystems = new List<XRHandSubsystem>();
        private const float PinchDistanceMeters = 0.025f;

        private void Start()
        {
            QuestDebugOverlay.Log("[CleanSceneBoot] Booting clean scene...");

            FindAvatarContainer();
            FindPanels();
            HideAllPanelsAtBoot();
            ShowPrimarySurface();
            DisableSceneDressing();
            EnsureVAD();
            EnsureControllerRide();
            EnsureWebPanel();
            StartCoroutine(RecheckDressing());

            QuestDebugOverlay.Log("[CleanSceneBoot] Boot complete — Alice only. Left Menu/pinch → Settings. Right Menu/pinch → Chat.");
        }

        private void FindAvatarContainer()
        {
            if (avatarContainer == null)
            {
                var go = GameObject.Find("AvatarContainer");
                if (go != null)
                {
                    avatarContainer = go;
                    QuestDebugOverlay.Log("[CleanSceneBoot] AvatarContainer found");
                }
                else
                {
                    QuestDebugOverlay.LogWarning("[CleanSceneBoot] AvatarContainer not found!");
                }
            }
        }

        private void FindPanels()
        {
            // Find AppSettings_Panel (repurposed as our Settings panel)
            if (settingsPanel == null)
            {
                settingsPanel = FindInactive("AppSettings_Panel");
                if (settingsPanel == null)
                    settingsPanel = GameObject.Find("AppSettings_Panel");
            }

            // Find ChatCanvas
            if (chatPanel == null)
            {
                chatPanel = FindInactive("ChatCanvas");
                if (chatPanel == null)
                    chatPanel = GameObject.Find("ChatCanvas");
            }

            QuestDebugOverlay.Log($"[CleanSceneBoot] Settings panel: {(settingsPanel != null ? "found" : "NOT FOUND")}");
            QuestDebugOverlay.Log($"[CleanSceneBoot] Chat panel: {(chatPanel != null ? "found" : "NOT FOUND")}");
        }

        /// <summary>
        /// Find a GameObject even if it's inactive by searching all transforms.
        /// </summary>
        private GameObject FindInactive(string name)
        {
            var transforms = FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (var t in transforms)
            {
                if (t.name == name && t.gameObject.scene.IsValid())
                    return t.gameObject;
            }
            return null;
        }

        private void HideAllPanelsAtBoot()
        {
            QuestDebugOverlay.Log("[CleanSceneBoot] Hiding all panels at boot...");

            foreach (string panelName in debrisPanelNames)
            {
                var panel = FindInactive(panelName);
                if (panel != null)
                {
                    bool wasActive = panel.activeSelf;
                    panel.SetActive(false);
                    if (wasActive)
                        QuestDebugOverlay.Log($"[CleanSceneBoot] Hidden: {panelName}");
                }
            }

            _activePanel = null;
        }

        /// <summary>
        /// Put the chat surface in front of the user and show it, so the headset
        /// opens on something you can actually talk to instead of bare passthrough.
        /// The scene authors every canvas at +Z, which is BEHIND a camera looking
        /// down -Z, so it must be positioned, not merely activated.
        /// </summary>
        private void ShowPrimarySurface()
        {
            if (chatPanel == null)
            {
                QuestDebugOverlay.LogWarning("[CleanSceneBoot] No chat surface found to show");
                return;
            }

            PositionPanelInFront(chatPanel, 1f);   // chat sits right, Alice stays clear
            chatPanel.SetActive(true);
            _activePanel = chatPanel;

            var ui = chatPanel.GetComponent<FoveAI.UI.SpatialUIManager>();
            if (ui != null) ui.ActivateInput();

            QuestDebugOverlay.Log(
                $"[CleanSceneBoot] Primary chat surface shown at {chatPanel.transform.position}");
        }

        private void EnsureVAD()
        {
            // Ensure QuestMicrophoneVAD is attached and configured for instant response
            var vad = FindAnyObjectByType<FoveAI.Audio.QuestMicrophoneVAD>();
            if (vad == null)
            {
                var vadObj = new GameObject("QuestMicrophoneVAD");
                vad = vadObj.AddComponent<FoveAI.Audio.QuestMicrophoneVAD>();
                QuestDebugOverlay.Log("[CleanSceneBoot] Created QuestMicrophoneVAD");
            }

            // Configure for instant VAD via reflection (private fields)
            var vadType = vad.GetType();
            SetPrivateFloat(vadType, vad, "speechThreshold", 0.008f);
            SetPrivateFloat(vadType, vad, "silenceDuration", 0.45f);
            SetPrivateFloat(vadType, vad, "minSpeechDuration", 0.15f);
            SetPrivateFloat(vadType, vad, "maxSpeechDuration", 12.0f);

            QuestDebugOverlay.Log("[CleanSceneBoot] VAD configured for instant response (threshold=0.008, silence=0.45s, minSpeech=0.15s)");
        }

        /// <summary>
        /// The house controller ride — button mappings, doubles, grab/carry.
        /// One component, mounted at boot like the VAD.
        /// </summary>
        private void EnsureControllerRide()
        {
            var ride = FindAnyObjectByType<QuestControllerRide>();
            if (ride == null)
            {
                var rideObj = new GameObject("QuestControllerRide");
                ride = rideObj.AddComponent<QuestControllerRide>();
                QuestDebugOverlay.Log("[CleanSceneBoot] Mounted QuestControllerRide (Y/X/A/B + doubles + grab)");
            }
        }

        private void SetPrivateFloat(System.Type type, object obj, string fieldName, float value)
        {
            var field = type.GetField(fieldName, System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            if (field != null)
            {
                field.SetValue(obj, value);
            }
        }

        private void Update()
        {
            RefreshDevices();
            HandleInput();
        }

        private void RefreshDevices()
        {
            if (_leftMenuAction == null)
            {
                _leftMenuAction = Bind("<XRController>{LeftHand}/menuButton", UnityEngine.InputSystem.InputActionType.Button);
                _leftGripAction = Bind("<XRController>{LeftHand}/grip", UnityEngine.InputSystem.InputActionType.Value);
            }
            if (_rightMenuAction == null)
            {
                _rightMenuAction = Bind("<XRController>{RightHand}/menuButton", UnityEngine.InputSystem.InputActionType.Button);
                _rightGripAction = Bind("<XRController>{RightHand}/grip", UnityEngine.InputSystem.InputActionType.Value);
            }
        }

        private static UnityEngine.InputSystem.InputAction Bind(
            string path, UnityEngine.InputSystem.InputActionType type)
        {
            var action = new UnityEngine.InputSystem.InputAction(
                name: path, type: type, binding: path);
            action.Enable();
            return action;
        }

        private static bool Held(UnityEngine.InputSystem.InputAction action, float threshold)
        {
            if (action == null || !action.enabled) return false;
            return action.ReadValue<float>() >= threshold;
        }

        private void HandleInput()
        {
            // ─── Left Controller Menu Button → Settings Panel ─────────
            bool leftMenu = Held(_leftMenuAction, 0.5f);

            if (leftMenu && !_leftMenuPressed)
            {
                ToggleWebPanel(SettingsUrl, -1f, settingsPanel);
                QuestDebugOverlay.Log("[CleanSceneBoot] Left Menu → Settings toggle");
            }
            _leftMenuPressed = leftMenu;

            // ─── Right Controller Menu Button → Chat Panel ───────────
            bool rightMenu = Held(_rightMenuAction, 0.5f);

            if (rightMenu && !_rightMenuPressed)
            {
                ToggleWebPanel(ChatUrl, 1f, chatPanel);
                QuestDebugOverlay.Log("[CleanSceneBoot] Right Menu → Chat toggle");
            }
            _rightMenuPressed = rightMenu;

            // ─── Left Hand Pinch → Settings Panel ─────────────────────
            bool leftPinch = DetectPinch(rightHand: false);
            if (leftPinch && !_leftPinchActive)
            {
                ToggleWebPanel(SettingsUrl, -1f, settingsPanel);
                QuestDebugOverlay.Log("[CleanSceneBoot] Left pinch → Settings toggle");
            }
            _leftPinchActive = leftPinch;

            // ─── Right Hand Pinch → Chat Panel ────────────────────────
            bool rightPinch = DetectPinch(rightHand: true);
            if (rightPinch && !_rightPinchActive)
            {
                ToggleWebPanel(ChatUrl, 1f, chatPanel);
                QuestDebugOverlay.Log("[CleanSceneBoot] Right pinch → Chat toggle");
            }
            _rightPinchActive = rightPinch;
        }

        /// <summary>
        /// Spawn the single WebUI panel hidden — it only appears when the user
        /// summons it (left/right menu button or pinch).
        /// </summary>
        private void EnsureWebPanel()
        {
            var serverIp = FoveAI.Config.ConfigLoader.Settings != null
                ? FoveAI.Config.ConfigLoader.Settings.serverIp : null;
            if (!string.IsNullOrEmpty(serverIp))
                webUiBase = $"http://{serverIp}:5177";

            webPanel = FindAnyObjectByType<FoveAI.UI.WebViewPanel>();
            if (webPanel == null)
            {
                var obj = new GameObject("WebUIPanel");
                webPanel = obj.AddComponent<FoveAI.UI.WebViewPanel>();
            }
            webPanel.Navigate(ChatUrl);
            webPanel.SetVisible(false);
            QuestDebugOverlay.Log($"[CleanSceneBoot] WebUI panel spawned hidden → {ChatUrl}");
        }

        /// <summary>
        /// Sterile boot contract: no seasonal dressing, no preset dressing at
        /// startup. SeasonalTheming / ScenePresetManager / DirectorEngine stay
        /// invocable on demand (WS events, menus) — just never on by default.
        /// </summary>
        private void DisableSceneDressing()
        {
            var seasonal = FindAnyObjectByType<FoveAI.Experiences.SeasonalTheming>();
            if (seasonal != null)
            {
                seasonal.autoDetectSeason = false;
                seasonal.autoDetectHoliday = false;
                seasonal.ClearTheme();
                QuestDebugOverlay.Log("[CleanSceneBoot] Seasonal dressing off (still invocable on demand)");
            }

            var presets = FindAnyObjectByType<FoveAI.Games.ScenePresetManager>();
            if (presets != null && presets.CurrentPreset != FoveAI.Games.ScenePresetManager.Preset.None)
                presets.ClearPreset();
        }

        /// <summary>
        /// Second pass ~2s in, in case another Start() applied dressing after us.
        /// </summary>
        private IEnumerator RecheckDressing()
        {
            yield return new WaitForSeconds(2f);
            DisableSceneDressing();
        }

        /// <summary>
        /// Toggle the shared WebUI panel: closed → open on the requested page;
        /// open on same page → close; open on other page → switch page.
        /// Falls back to the native panel when no WebView (e.g. editor).
        /// </summary>
        private void ToggleWebPanel(string url, float sideDir, GameObject nativeFallback)
        {
            if (webPanel == null)
            {
                TogglePanel(nativeFallback);
                return;
            }

            if (webPanel.IsVisible && webPanel.CurrentUrl == url)
            {
                webPanel.SetVisible(false);
                _activePanel = null;
                return;
            }

            PositionPanelInFront(webPanel.gameObject, sideDir);
            webPanel.SetVisible(true);
            webPanel.Navigate(url);
            _activePanel = webPanel.gameObject;
        }

        /// <summary>
        /// Detect select gesture: controller trigger/grip OR hand-tracking pinch
        /// (thumb tip ↔ index tip distance) via the XR Hands subsystem.
        /// </summary>
        private bool DetectPinch(bool rightHand)
        {
            var grip = rightHand ? _rightGripAction : _leftGripAction;
            if (Held(grip, pinchThreshold))
                return true;
            return DetectHandPinch(rightHand);
        }

        /// <summary>
        /// True when the tracked hand's thumb tip and index tip are pinched together.
        /// </summary>
        private bool DetectHandPinch(bool right)
        {
            if (_handSubsystem == null || !_handSubsystem.running)
            {
                SubsystemManager.GetSubsystems(_handSubsystems);
                _handSubsystem = _handSubsystems.Count > 0 ? _handSubsystems[0] : null;
                if (_handSubsystem == null) return false;
            }

            var hand = right ? _handSubsystem.rightHand : _handSubsystem.leftHand;
            if (!hand.isTracked) return false;

            var tip = hand.GetJoint(XRHandJointID.IndexTip);
            var thumb = hand.GetJoint(XRHandJointID.ThumbTip);
            if (!tip.TryGetPose(out Pose tipPose) || !thumb.TryGetPose(out Pose thumbPose))
                return false;

            return Vector3.Distance(tipPose.position, thumbPose.position) < PinchDistanceMeters;
        }

        private void TogglePanel(GameObject panel)
        {
            if (panel == null) return;

            // If this panel is already active, hide it
            if (panel.activeSelf)
            {
                panel.SetActive(false);
                _activePanel = null;
                return;
            }

            // Hide the currently active panel (only one at a time)
            if (_activePanel != null && _activePanel != panel && _activePanel.activeSelf)
            {
                _activePanel.SetActive(false);
            }

            // Position panel in front of user
            PositionPanelInFront(panel);

            // Show the new panel
            panel.SetActive(true);
            _activePanel = panel;

            // Activate input if it has SpatialUIManager
            var ui = panel.GetComponent<FoveAI.UI.SpatialUIManager>();
            if (ui != null) ui.ActivateInput();
        }

        /// <summary>
        /// Position a panel in front of the user, offset to the side so Alice stays visible.
        /// Settings panel goes left, Chat panel goes right.
        /// </summary>
        private void PositionPanelInFront(GameObject panel)
        {
            // Settings → left side, Chat → right side
            float sideDir = (panel == settingsPanel) ? -1f : 1f;
            PositionPanelInFront(panel, sideDir);
        }

        private void PositionPanelInFront(GameObject panel, float sideDir)
        {
            var cam = Camera.main;
            if (cam == null) return;

            // WebUI panel sits further out to the side and slightly below eye
            // level so it never obscures Alice or the room view.
            bool isWeb = webPanel != null && panel == webPanel.gameObject;
            float side = isWeb ? webPanelSideOffset : panelSideOffset;
            float height = isWeb ? webPanelHeight : panelHeight;

            Vector3 forward = cam.transform.forward;
            forward.y = 0f;
            if (forward.sqrMagnitude < 0.001f) forward = Vector3.forward;
            forward.Normalize();

            Vector3 right = cam.transform.right;
            right.y = 0f;
            right.Normalize();

            Vector3 pos = cam.transform.position
                + forward * panelDistance
                + right * (side * sideDir)
                + Vector3.up * height;

            panel.transform.position = pos;
            panel.transform.rotation = Quaternion.LookRotation(
                (pos - cam.transform.position).normalized, Vector3.up);
        }
    }
}
