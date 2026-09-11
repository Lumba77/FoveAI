using UnityEngine;
using UnityEngine.XR;
using UnityEngine.XR.ARFoundation;
using FoveAI.DebugOverlay;

namespace FoveAI.XR
{
    /// <summary>
    /// Runtime fixer for OpenXR + ARFoundation based XR rig (Quest 3).
    /// Does NOT use OVRManager (conflicts with OpenXR).
    /// Handles passthrough, controller tracking, and camera setup.
    /// </summary>
    public class XRRigFixer : MonoBehaviour
    {
        private void Awake()
        {
            // Fix ALL cameras immediately at Awake — before first render — so passthrough shows
            FixAllCamerasForPassthrough();
        }

        private void Start()
        {
            QuestDebugOverlay.Log("[XRRigFixer] Starting (OpenXR mode)...");
            LogXRStatus();
            FixPassthrough();
            FixControllers();
            FindChatPanel();
        }

        /// <summary>
        /// Fix all cameras in the scene for passthrough — set clear flags to SolidColor
        /// with transparent black so the ARCameraBackground can render the passthrough feed.
        /// Done in Awake() before any rendering occurs.
        /// </summary>
        private void FixAllCamerasForPassthrough()
        {
            var cameras = FindObjectsByType<Camera>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (var cam in cameras)
            {
                // Skip cameras that are depth-only or don't-clear (overlay cameras)
                if (cam.clearFlags == CameraClearFlags.Depth || cam.clearFlags == CameraClearFlags.Nothing)
                    continue;

                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0, 0, 0, 0);
                QuestDebugOverlay.Log($"[XRRigFixer] Fixed camera '{cam.name}' clearFlags=SolidColor, bg=transparent");
            }
        }

        private void LogXRStatus()
        {
            QuestDebugOverlay.Log($"[XRRigFixer] XR active: {XRSettings.isDeviceActive}");
            QuestDebugOverlay.Log($"[XRRigFixer] XR device: {XRSettings.loadedDeviceName}");

            // List all XR input devices
            var inputDevices = new System.Collections.Generic.List<InputDevice>();
            InputDevices.GetDevices(inputDevices);
            QuestDebugOverlay.Log($"[XRRigFixer] Found {inputDevices.Count} XR input devices:");
            foreach (var dev in inputDevices)
            {
                QuestDebugOverlay.Log($"  - {dev.name} [{dev.characteristics}]");
            }
        }

        private void FixPassthrough()
        {
            // ARFoundation passthrough: check for ARCameraManager + ARCameraBackground
            var cam = Camera.main;
            if (cam == null)
            {
                QuestDebugOverlay.LogError("[XRRigFixer] No main camera!");
                return;
            }

            var arCamManager = cam.GetComponent<ARCameraManager>();
            var arCamBackground = cam.GetComponent<ARCameraBackground>();

            QuestDebugOverlay.Log($"[XRRigFixer] ARCameraManager: {(arCamManager != null ? "present" : "MISSING")}");
            QuestDebugOverlay.Log($"[XRRigFixer] ARCameraBackground: {(arCamBackground != null ? "present" : "MISSING")}");

            // Check for ARSession
            var arSession = FindAnyObjectByType<ARSession>();
            QuestDebugOverlay.Log($"[XRRigFixer] ARSession: {(arSession != null ? "present" : "MISSING")}");

            if (arSession == null)
            {
                QuestDebugOverlay.Log("[XRRigFixer] Adding ARSession");
                var sessionObj = new GameObject("ARSession");
                sessionObj.AddComponent<ARSession>();
            }

            // Check for ARInputManager
            var arInput = FindAnyObjectByType<ARInputManager>();
            QuestDebugOverlay.Log($"[XRRigFixer] ARInputManager: {(arInput != null ? "present" : "MISSING")}");

            // Make camera background transparent so passthrough shows through
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0, 0, 0, 0);
            QuestDebugOverlay.Log("[XRRigFixer] Camera set to transparent background for passthrough");
        }

        private void FixControllers()
        {
            // Get controller devices
            var leftControllers = new System.Collections.Generic.List<InputDevice>();
            var rightControllers = new System.Collections.Generic.List<InputDevice>();
            InputDevices.GetDevicesWithCharacteristics(InputDeviceCharacteristics.Left | InputDeviceCharacteristics.Controller, leftControllers);
            InputDevices.GetDevicesWithCharacteristics(InputDeviceCharacteristics.Right | InputDeviceCharacteristics.Controller, rightControllers);

            QuestDebugOverlay.Log($"[XRRigFixer] Left controllers: {leftControllers.Count}");
            QuestDebugOverlay.Log($"[XRRigFixer] Right controllers: {rightControllers.Count}");

            // Create controller anchors (tracked transforms only — no cube visuals)
            CreateControllerAnchor("LeftController", InputDeviceCharacteristics.Left);
            CreateControllerAnchor("RightController", InputDeviceCharacteristics.Right);

            // Setup XR Interaction Toolkit ray interactors for UI interaction
            var raySetup = gameObject.GetComponent<XRRayInteractorSetup>() ?? gameObject.AddComponent<XRRayInteractorSetup>();
            raySetup.SetupRayInteractors(_leftControllerObj, _rightControllerObj);

            // Automatically attach Quest Microphone VAD for continuous hands-free voice conversations
            if (GetComponent<FoveAI.Audio.QuestMicrophoneVAD>() == null)
            {
                gameObject.AddComponent<FoveAI.Audio.QuestMicrophoneVAD>();
            }

            // Auto-display chat panel in front of user on startup
            Invoke(nameof(ShowInitialChatPanel), 1.5f);
        }

        private void ShowInitialChatPanel()
        {
            if (_chatPanel != null)
            {
                SetChatVisible(true);
            }
        }

        private GameObject _leftControllerObj;
        private GameObject _rightControllerObj;
        private InputDevice _leftDevice;
        private InputDevice _rightDevice;
        private GameObject _chatPanel;
        private bool _leftTogglePressed;

        private void FindChatPanel()
        {
            var transforms = FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (var candidate in transforms)
            {
                if (candidate.name != "ChatCanvas" || !candidate.gameObject.scene.IsValid()) continue;
                _chatPanel = candidate.gameObject;
                var oldToggle = _chatPanel.GetComponent<FoveAI.UI.XRPanelToggle>();
                if (oldToggle != null) oldToggle.enabled = false;

                // Ensure ChatCanvas has BoxCollider so XR ray interactors can hit it for 3D interaction
                var rect = _chatPanel.GetComponent<RectTransform>();
                var col = _chatPanel.GetComponent<BoxCollider>() ?? _chatPanel.AddComponent<BoxCollider>();
                if (rect != null)
                {
                    col.size = new Vector3(Mathf.Max(rect.rect.width, 2f), Mathf.Max(rect.rect.height, 1.5f), 0.05f);
                }

                _chatPanel.SetActive(false);
                QuestDebugOverlay.Log("[XRRigFixer] Chat panel ready — press left X or Y");
                return;
            }
            QuestDebugOverlay.LogWarning("[XRRigFixer] ChatCanvas not found");
        }

        private void CreateControllerAnchor(string name, InputDeviceCharacteristics characteristics)
        {
            var obj = new GameObject(name);
            obj.transform.SetParent(transform, false);

            if (characteristics.HasFlag(InputDeviceCharacteristics.Left))
            {
                _leftControllerObj = obj;
                var wand = obj.AddComponent<XRHapticWand>();
                wand.hand = XRHapticWand.WandHand.Left;
            }
            else
            {
                _rightControllerObj = obj;
                var wand = obj.AddComponent<XRHapticWand>();
                wand.hand = XRHapticWand.WandHand.Right;
            }

            // Ensure XR IDE HUD exists in scene
            if (FindAnyObjectByType<FoveAI.UI.XRIDEHud>() == null)
            {
                var hudObj = new GameObject("XR_IDE_HUD");
                hudObj.AddComponent<FoveAI.UI.XRIDEHud>();
            }

            QuestDebugOverlay.Log($"[XRRigFixer] Created {name} anchor (XRI ray interactor will be attached)");
        }

        private void Update()
        {
            // Refresh controller / hand devices if not connected
            if (!_leftDevice.isValid)
            {
                var leftDevs = new System.Collections.Generic.List<InputDevice>();
                InputDevices.GetDevicesWithCharacteristics(InputDeviceCharacteristics.Left, leftDevs);
                if (leftDevs.Count > 0) _leftDevice = leftDevs[0];
            }
            if (!_rightDevice.isValid)
            {
                var rightDevs = new System.Collections.Generic.List<InputDevice>();
                InputDevices.GetDevicesWithCharacteristics(InputDeviceCharacteristics.Right, rightDevs);
                if (rightDevs.Count > 0) _rightDevice = rightDevs[0];
            }

            // Update controller positions
            UpdateControllerPose(_leftDevice, _leftControllerObj);
            UpdateControllerPose(_rightDevice, _rightControllerObj);
            UpdateChatToggle();
        }

        private void UpdateChatToggle()
        {
            if (_chatPanel == null) return;

            // 1. Check InputDevices (Left Menu button or secondary)
            bool menuPressed = false;
            if (_leftDevice.isValid)
            {
                if (_leftDevice.TryGetFeatureValue(CommonUsages.menuButton, out bool menu) && menu) menuPressed = true;
            }

            // 2. Check OVRInput fallback (Left Menu / Start button, or thumbstick click)
            if (OVRInput.GetDown(OVRInput.Button.Start) || OVRInput.GetDown(OVRInput.RawButton.Start))
            {
                menuPressed = true;
            }

            if (menuPressed && !_leftTogglePressed)
            {
                SetChatVisible(!_chatPanel.activeSelf);
            }
            _leftTogglePressed = menuPressed;
        }

        private void SetChatVisible(bool visible)
        {
            if (!visible)
            {
                _chatPanel.SetActive(false);
                FoveAI.UI.XRIDEHud.FlashNotification("Chat Panel Hidden (Left Menu to reopen)", 2f);
                return;
            }

            var cam = Camera.main;
            if (cam != null)
            {
                Vector3 forward = cam.transform.forward;
                forward.y = 0f;
                if (forward.sqrMagnitude < 0.001f) forward = Vector3.forward;
                forward.Normalize();
                Vector3 right = cam.transform.right;
                right.y = 0f;
                right.Normalize();

                // Position panel 1.2m away, offset 35 deg to the left (leaving center completely open for Alice)
                Vector3 panelPosition = cam.transform.position + forward * 1.2f - right * 0.75f + Vector3.up * 0.05f;
                _chatPanel.transform.position = panelPosition;
                _chatPanel.transform.rotation = Quaternion.LookRotation(
                    (panelPosition - cam.transform.position).normalized, Vector3.up);
            }

            _chatPanel.SetActive(true);
            FoveAI.UI.XRIDEHud.FlashNotification("Chat Panel Opened", 2f);
            var ui = _chatPanel.GetComponent<FoveAI.UI.SpatialUIManager>();
            if (ui != null) ui.ActivateInput();
        }

        private void UpdateControllerPose(InputDevice device, GameObject controllerObj)
        {
            if (controllerObj == null || !device.isValid) return;

            if (device.TryGetFeatureValue(CommonUsages.devicePosition, out Vector3 pos))
            {
                controllerObj.transform.localPosition = pos;
            }

            if (device.TryGetFeatureValue(CommonUsages.deviceRotation, out Quaternion rot))
            {
                controllerObj.transform.localRotation = rot;
            }
        }
    }
}
