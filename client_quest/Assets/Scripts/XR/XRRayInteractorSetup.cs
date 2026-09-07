using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using UnityEngine.XR.Interaction.Toolkit;
using UnityEngine.XR.Interaction.Toolkit.Interactors;
using UnityEngine.XR.Interaction.Toolkit.Interactors.Visuals;
using UnityEngine.XR.Interaction.Toolkit.UI;
using FoveAI.DebugOverlay;

namespace FoveAI.XR
{
    /// <summary>
    /// Runtime auto-setup for XR Interaction Toolkit ray interactors.
    /// Replaces the temporary controller cubes with proper XRRayInteractor components
    /// that can interact with world-space UI canvases via TrackedDeviceGraphicRaycaster.
    ///
    /// This script:
    ///   1. Ensures an XRInteractionManager exists in the scene.
    ///   2. Ensures an EventSystem with XRUIInputModule exists.
    ///   3. Upgrades the ChatCanvas to use TrackedDeviceGraphicRaycaster.
    ///   4. Creates XRRayInteractor + XRInteractorLineVisual on each controller transform.
    ///   5. Uses device-based XRController as input bridge for select/activate.
    ///
    /// Designed to be called from XRRigFixer after controller visuals are created.
    /// </summary>
    public class XRRayInteractorSetup : MonoBehaviour
    {

        private static bool _setupComplete = false;

        /// <summary>
        /// Call this once after the XR rig and controller objects exist.
        /// leftController and rightController are the GameObjects whose transform
        /// is driven by XR input device position/rotation.
        /// </summary>
        public void SetupRayInteractors(GameObject leftController, GameObject rightController)
        {
            if (_setupComplete)
            {
                QuestDebugOverlay.Log("[XRRaySetup] Already complete — skipping");
                return;
            }

            QuestDebugOverlay.Log("[XRRaySetup] Starting XRI ray interactor setup...");

            EnsureInteractionManager();
            EnsureEventSystemWithXRInputModule();
            UpgradeCanvasRaycasters();

            SetupSingleRay(leftController, isLeft: true);
            SetupSingleRay(rightController, isLeft: false);

            _setupComplete = true;
            QuestDebugOverlay.Log("[XRRaySetup] XRI ray interactors ready on both controllers");
        }

        private void EnsureInteractionManager()
        {
            var manager = FindAnyObjectByType<XRInteractionManager>();
            if (manager == null)
            {
                var obj = new GameObject("XRInteractionManager");
                manager = obj.AddComponent<XRInteractionManager>();
                QuestDebugOverlay.Log("[XRRaySetup] Created XRInteractionManager");
            }
        }

        private void EnsureEventSystemWithXRInputModule()
        {
            var eventSystem = FindAnyObjectByType<EventSystem>();
            if (eventSystem == null)
            {
                var obj = new GameObject("EventSystem");
                eventSystem = obj.AddComponent<EventSystem>();
                QuestDebugOverlay.Log("[XRRaySetup] Created EventSystem");
            }

            // Replace any existing input module with XRUIInputModule
            var xrModule = eventSystem.GetComponent<XRUIInputModule>();

            if (xrModule == null)
            {
                // Remove StandaloneInputModule if present (legacy input system)
                var standalone = eventSystem.GetComponent<StandaloneInputModule>();
                if (standalone != null)
                {
                    Destroy(standalone);
                    QuestDebugOverlay.Log("[XRRaySetup] Removed StandaloneInputModule");
                }

                // Remove InputSystemUIInputModule if present (input system package)
                var inputSystemModule = eventSystem.GetComponent<UnityEngine.InputSystem.UI.InputSystemUIInputModule>();
                if (inputSystemModule != null)
                {
                    Destroy(inputSystemModule);
                    QuestDebugOverlay.Log("[XRRaySetup] Removed InputSystemUIInputModule");
                }

                xrModule = eventSystem.gameObject.AddComponent<XRUIInputModule>();
                QuestDebugOverlay.Log("[XRRaySetup] Added XRUIInputModule to EventSystem");
            }
        }

        private void UpgradeCanvasRaycasters()
        {
            var canvases = FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            int upgraded = 0;
            foreach (var canvas in canvases)
            {
                if (canvas.renderMode != RenderMode.WorldSpace) continue;

                // Remove old GraphicRaycaster if present
                var oldRaycaster = canvas.GetComponent<GraphicRaycaster>();
                var trackedRaycaster = canvas.GetComponent<TrackedDeviceGraphicRaycaster>();

                if (trackedRaycaster == null)
                {
                    if (oldRaycaster != null) Destroy(oldRaycaster);
                    trackedRaycaster = canvas.gameObject.AddComponent<TrackedDeviceGraphicRaycaster>();
                    upgraded++;
                    QuestDebugOverlay.Log($"[XRRaySetup] Upgraded canvas '{canvas.name}' to TrackedDeviceGraphicRaycaster");
                }
            }
            QuestDebugOverlay.Log($"[XRRaySetup] Upgraded {upgraded} canvas(es)");
        }

        private void SetupSingleRay(GameObject controllerObj, bool isLeft)
        {
            if (controllerObj == null)
            {
                QuestDebugOverlay.LogWarning($"[XRRaySetup] {(isLeft ? "Left" : "Right")} controller object is null — skipping ray setup");
                return;
            }

            string handName = isLeft ? "Left" : "Right";

            // Remove the old custom XRControllerRayPointer if present (the custom ray visual + manual raycast)
            var oldPointer = controllerObj.GetComponent<XRControllerRayPointer>();
            if (oldPointer != null)
            {
                Destroy(oldPointer);
                QuestDebugOverlay.Log($"[XRRaySetup] Removed old XRControllerRayPointer on {handName}");
            }

            // Remove the temporary cube visual child
            var cubeChild = controllerObj.transform.Find("Cube");
            if (cubeChild != null)
            {
                Destroy(cubeChild.gameObject);
                QuestDebugOverlay.Log($"[XRRaySetup] Removed temp cube visual on {handName}");
            }

            // Add XRRayInteractor
            var rayInteractor = controllerObj.GetComponent<XRRayInteractor>();
            if (rayInteractor == null)
            {
                rayInteractor = controllerObj.AddComponent<XRRayInteractor>();
            }

            rayInteractor.handedness = isLeft ? InteractorHandedness.Left : InteractorHandedness.Right;
            rayInteractor.enableUIInteraction = true;
            rayInteractor.maxRaycastDistance = 10f;

            // Add LineRenderer if not present (XRRayInteractor needs it for raycast visualization)
            var lineRenderer = controllerObj.GetComponent<LineRenderer>();
            if (lineRenderer == null)
            {
                lineRenderer = controllerObj.AddComponent<LineRenderer>();
                lineRenderer.startWidth = 0.005f;
                lineRenderer.endWidth = 0.003f;
                lineRenderer.material = new Material(Shader.Find("Sprites/Default") ?? Shader.Find("Unlit/Color"));
                lineRenderer.material.color = isLeft
                    ? new Color(0.2f, 0.7f, 1.0f, 0.85f)
                    : new Color(1.0f, 0.5f, 0.2f, 0.85f);
                lineRenderer.useWorldSpace = true;
                lineRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                lineRenderer.receiveShadows = false;
            }

            // Add XRInteractorLineVisual for proper ray rendering
            var lineVisual = controllerObj.GetComponent<XRInteractorLineVisual>();
            if (lineVisual == null)
            {
                lineVisual = controllerObj.AddComponent<XRInteractorLineVisual>();
            }
            lineVisual.lineWidth = 0.005f;
            lineVisual.reticle = null;
            lineVisual.validColorGradient = new Gradient
            {
                colorKeys = new[]
                {
                    new GradientColorKey(isLeft ? new Color(0.2f, 0.7f, 1.0f, 0.85f) : new Color(1.0f, 0.5f, 0.2f, 0.85f), 0f),
                    new GradientColorKey(isLeft ? new Color(0.2f, 0.7f, 1.0f, 0.4f) : new Color(1.0f, 0.5f, 0.2f, 0.4f), 1f),
                },
                alphaKeys = new[]
                {
                    new GradientAlphaKey(0.85f, 0f),
                    new GradientAlphaKey(0.4f, 1f),
                }
            };
            lineVisual.invalidColorGradient = new Gradient
            {
                colorKeys = new[]
                {
                    new GradientColorKey(new Color(1f, 0.3f, 0.3f, 0.6f), 0f),
                    new GradientColorKey(new Color(1f, 0.3f, 0.3f, 0.3f), 1f),
                },
                alphaKeys = new[]
                {
                    new GradientAlphaKey(0.6f, 0f),
                    new GradientAlphaKey(0.3f, 1f),
                }
            };

            // Setup input — try action-based first, fall back to device-based
            SetupInteractorInput(controllerObj, rayInteractor, isLeft);

            QuestDebugOverlay.Log($"[XRRaySetup] {handName} ray interactor configured with UI interaction");
        }

        private void SetupInteractorInput(GameObject controllerObj, XRRayInteractor rayInteractor, bool isLeft)
        {
            // Try to find or create an action-based XRController for input
            // XRI 3.x deprecated XRController but still supports it via "Input Compatibility Mode"
            // We use the action-based XRController as a bridge since we don't have a pre-built InputActionAsset

            var controllerType = System.Type.GetType("UnityEngine.XR.Interaction.Toolkit.XRController, Unity.XR.Interaction.Toolkit");
            if (controllerType != null)
            {
                // Check if one already exists
                var existingController = controllerObj.GetComponent(controllerType);
                if (existingController == null)
                {
                    existingController = controllerObj.AddComponent(controllerType);
                }

                // Set the controller node via reflection
                var nodeField = controllerType.GetField("m_ControllerNode");
                if (nodeField != null)
                {
                    var node = isLeft ? UnityEngine.XR.XRNode.LeftHand : UnityEngine.XR.XRNode.RightHand;
                    nodeField.SetValue(existingController, node);
                }

                QuestDebugOverlay.Log($"[XRRaySetup] {(isLeft ? "Left" : "Right")} using device-based XRController bridge");
            }
            else
            {
                QuestDebugOverlay.LogWarning($"[XRRaySetup] XRController type not found — interactor will need manual input wiring");
            }
        }
    }
}
