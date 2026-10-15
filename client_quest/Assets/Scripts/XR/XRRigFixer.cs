using UnityEngine;
using UnityEngine.XR;
using UnityEngine.XR.ARFoundation;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.XR;
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
            // 2026-10-09: XRSettings and InputDevices are legacy (UnityEngine.InputLegacyModule,
            // not installed in this project) — replaced with XRGeneralSettings + InputSystem.
            bool xrActive = false;
            string loaderName = "(none)";
            try
            {
                var managerType = System.Type.GetType(
                    "UnityEngine.XR.Management.XRGeneralSettings, Unity.XR.Management");
                if (managerType != null)
                {
                    var instanceProp = managerType.GetProperty("Instance",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    var instance = instanceProp?.GetValue(null);
                    var mgrField = managerType.GetField("Manager");
                    var mgr = mgrField?.GetValue(instance);
                    if (mgr != null)
                    {
                        var loaderProp = mgr.GetType().GetProperty("activeLoader");
                        var loader = loaderProp?.GetValue(mgr);
                        if (loader != null)
                        {
                            xrActive = true;
                            loaderName = loader.GetType().GetProperty("name")?.GetValue(loader)?.ToString() ?? "(unnamed)";
                        }
                    }
                }
            }
            catch (System.Exception e) { QuestDebugOverlay.Log($"[XRRigFixer] XR status probe failed: {e.Message}"); }
            QuestDebugOverlay.Log($"[XRRigFixer] XR active: {xrActive}");
            QuestDebugOverlay.Log($"[XRRigFixer] XR loader: {loaderName}");

            // List all XR controllers via the new Input System
            var controllers = new System.Collections.Generic.List<UnityEngine.InputSystem.XR.XRController>();
            foreach (var d in UnityEngine.InputSystem.InputSystem.devices)
            {
                if (d is UnityEngine.InputSystem.XR.XRController c) controllers.Add(c);
            }
            QuestDebugOverlay.Log($"[XRRigFixer] Found {controllers.Count} XR controllers:");
            foreach (var ctrl in controllers)
            {
                QuestDebugOverlay.Log($"  - {ctrl.name}");
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
            // 2026-10-09: the legacy InputDevices/InputDeviceCharacteristics API was dead here —
            // this project runs the NEW Input System (and UnityEngine.InputLegacyModule is not
            // installed), so GetDevicesWithCharacteristics always returned an empty list, the
            // anchors were never driven by controller poses, and XRRayInteractorSetup received
            // static objects: no hands, no rays, nothing clickable. Switched to InputAction-based
            // pose binding, matching AutoSceneBuilder's TrackedPoseDriver setup.
            QuestDebugOverlay.Log("[XRRigFixer] Controllers: using new Input System pose actions");

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

            // Attach CleanSceneBoot — hides all panels at boot, manages panel toggles
            if (GetComponent<FoveAI.XR.CleanSceneBoot>() == null)
            {
                gameObject.AddComponent<FoveAI.XR.CleanSceneBoot>();
            }
        }

        private GameObject _leftControllerObj;
        private GameObject _rightControllerObj;

        private void FindChatPanel()
        {
            // Ensure ChatCanvas has BoxCollider so XR ray interactors can hit it for 3D interaction
            var transforms = FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (var candidate in transforms)
            {
                if (candidate.name != "ChatCanvas" || !candidate.gameObject.scene.IsValid()) continue;
                var chatPanel = candidate.gameObject;
                var oldToggle = chatPanel.GetComponent<FoveAI.UI.XRPanelToggle>();
                if (oldToggle != null) oldToggle.enabled = false;

                var rect = chatPanel.GetComponent<RectTransform>();
                var col = chatPanel.GetComponent<BoxCollider>() ?? chatPanel.AddComponent<BoxCollider>();
                if (rect != null)
                {
                    col.size = new Vector3(Mathf.Max(rect.rect.width, 2f), Mathf.Max(rect.rect.height, 1.5f), 0.05f);
                }

                QuestDebugOverlay.Log("[XRRigFixer] Chat panel collider ready");
                return;
            }
        }

        private void CreateControllerAnchor(string name, InputDeviceCharacteristics characteristics)
        {
            var obj = new GameObject(name);
            obj.transform.SetParent(transform, false);

            bool isLeft = characteristics.HasFlag(InputDeviceCharacteristics.Left);

            // New Input System pose binding — this is what actually moves the anchor.
            var posAction = new InputAction(
                name: isLeft ? "LeftControllerPose" : "RightControllerPose",
                type: InputActionType.Value,
                binding: isLeft ? "<XRController>{LeftHand}/devicePosition" : "<XRController>{RightHand}/devicePosition");
            var rotAction = new InputAction(
                name: isLeft ? "LeftControllerRot" : "RightControllerRot",
                type: InputActionType.Value,
                binding: isLeft ? "<XRController>{LeftHand}/deviceRotation" : "<XRController>{RightHand}/deviceRotation");
            posAction.Enable();
            rotAction.Enable();

            if (isLeft)
            {
                _leftControllerObj = obj;
                _leftPoseAction = posAction;
                _leftRotAction = rotAction;
                var wand = obj.AddComponent<XRHapticWand>();
                wand.hand = XRHapticWand.WandHand.Left;
            }
            else
            {
                _rightControllerObj = obj;
                _rightPoseAction = posAction;
                _rightRotAction = rotAction;
                var wand = obj.AddComponent<XRHapticWand>();
                wand.hand = XRHapticWand.WandHand.Right;
            }

            // Add a forward-pointing ray pointer for 3D/avatar interaction
            // This ensures the ray points standard forward from the controller
            var rayPointer = obj.GetComponent<XRControllerRayPointer>();
            if (rayPointer == null)
            {
                rayPointer = obj.AddComponent<XRControllerRayPointer>();
                rayPointer.hand = isLeft
                    ? XRControllerRayPointer.ControllerHand.Left
                    : XRControllerRayPointer.ControllerHand.Right;
            }

            // Ensure XR IDE HUD exists in scene
            if (FindAnyObjectByType<FoveAI.UI.XRIDEHud>() == null)
            {
                var hudObj = new GameObject("XR_IDE_HUD");
                hudObj.AddComponent<FoveAI.UI.XRIDEHud>();
            }

            QuestDebugOverlay.Log($"[XRRigFixer] Created {name} anchor with forward ray pointer");
        }

        private void Update()
        {
            // New Input System: read the bound pose actions and drive the anchors directly.
            // Referencing <XRController>{LeftHand}/{RightHand}/devicePosition|deviceRotation is what
            // makes the anchors actually track the headset's controllers.
            UpdateControllerPose(_leftPoseAction, _rightPoseAction, _leftRotAction, _rightRotAction,
                                 _leftControllerObj, _rightControllerObj);
        }

        private InputAction _leftPoseAction;
        private InputAction _rightPoseAction;
        private InputAction _leftRotAction;
        private InputAction _rightRotAction;

        private static void UpdateControllerPose(
            InputAction leftPos, InputAction rightPos, InputAction leftRot, InputAction rightRot,
            GameObject leftObj, GameObject rightObj)
        {
            ApplyPose(leftObj, leftPos, leftRot);
            ApplyPose(rightObj, rightPos, rightRot);
        }

        private static void ApplyPose(GameObject target, InputAction posAction, InputAction rotAction)
        {
            if (target == null || posAction == null || rotAction == null) return;
            if (!posAction.enabled || !rotAction.enabled) return;

            if (posAction.ReadValue<Vector3>() is Vector3 pos) target.transform.localPosition = pos;
            if (rotAction.ReadValue<Quaternion>() is Quaternion rot) target.transform.localRotation = rot;
        }
    }
}
