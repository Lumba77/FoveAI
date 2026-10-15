using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using UnityEngine.XR;
using FoveAI.DebugOverlay;
using TMPro;

namespace FoveAI.XR
{
    /// <summary>
    /// XRControllerRayPointer — High-visibility laser ray and spatial interaction pointer for Meta Quest 3.
    ///
    /// Features:
    ///   1. Visual laser beam (LineRenderer) + hit cursor reticle dot.
    ///   2. Full World-Space Canvas interaction: clicks Buttons, InputFields, Dictate, Send, and Settings toggles.
    ///   3. 3D Avatar and Object interaction via Physics raycasting.
    ///   4. Haptic pulse feedback on hover and trigger clicks.
    ///   5. Works with OpenXR / XR InputDevices (Left & Right Quest Touch controllers).
    /// </summary>
    public class XRControllerRayPointer : MonoBehaviour
    {
        public enum ControllerHand
        {
            Left,
            Right
        }

        [Header("Controller Configuration")]
        [Tooltip("Which controller this pointer represents.")]
        public ControllerHand hand = ControllerHand.Right;

        [Tooltip("Maximum laser reach in meters.")]
        public float maxRayDistance = 8.0f;

        [Header("Visuals")]
        public Color rayColor = new Color(0.2f, 0.8f, 1.0f, 0.8f);
        public Color hitColor = new Color(1.0f, 0.9f, 0.2f, 1.0f);
        public float rayWidth = 0.005f;

        [Header("Interaction")]
        [Tooltip("Layer mask for physical 3D objects and avatar.")]
        public LayerMask physicsLayers = ~0;

        private LineRenderer _lineRenderer;
        private GameObject _reticle;
        private InputDevice _device;
        private bool _triggerPressed = false;
        private GameObject _currentHoveredUI = null;
        private GameObject _currentHovered3D = null;

        private void Awake()
        {
            SetupLaserVisuals();
            SetupReticle();
        }

        private void Start()
        {
            ResolveInputDevice();
        }

        private void ResolveInputDevice()
        {
            var characteristics = (hand == ControllerHand.Left ? InputDeviceCharacteristics.Left : InputDeviceCharacteristics.Right);

            var devices = new List<InputDevice>();
            InputDevices.GetDevicesWithCharacteristics(characteristics | InputDeviceCharacteristics.Controller, devices);
            if (devices.Count == 0)
            {
                InputDevices.GetDevicesWithCharacteristics(characteristics | InputDeviceCharacteristics.HandTracking, devices);
            }
            if (devices.Count == 0)
            {
                InputDevices.GetDevicesWithCharacteristics(characteristics, devices);
            }
            if (devices.Count > 0)
            {
                _device = devices[0];
            }
        }

        private void SetupLaserVisuals()
        {
            _lineRenderer = gameObject.GetComponent<LineRenderer>();
            if (_lineRenderer == null) _lineRenderer = gameObject.AddComponent<LineRenderer>();
            if (_lineRenderer == null) { QuestDebugOverlay.Log("[XRControllerRayPointer] no LineRenderer — skipping laser visuals"); return; }
            _lineRenderer.positionCount = 2;
            _lineRenderer.startWidth = rayWidth;
            _lineRenderer.endWidth = rayWidth * 0.5f;

            var shader = Shader.Find("Sprites/Default") ?? Shader.Find("Unlit/Color");
            var mat = new Material(shader);
            mat.color = rayColor;
            _lineRenderer.material = mat;
            _lineRenderer.useWorldSpace = true;
            _lineRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            _lineRenderer.receiveShadows = false;
        }

        private void SetupReticle()
        {
            _reticle = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            _reticle.name = $"{hand}Pointer_Reticle";
            _reticle.transform.localScale = Vector3.one * 0.02f;
            Destroy(_reticle.GetComponent<SphereCollider>());

            var rMat = new Material(Shader.Find("Sprites/Default") ?? Shader.Find("Unlit/Color"));
            rMat.color = hitColor;
            _reticle.GetComponent<MeshRenderer>().material = rMat;
            _reticle.SetActive(false);
        }

        private void Update()
        {
            if (!_device.isValid)
            {
                ResolveInputDevice();
            }

            Ray ray = new Ray(transform.position, transform.forward);
            Vector3 endPoint = ray.origin + ray.direction * maxRayDistance;
            bool hasHit = false;

            // 1. Raycast World-Space Canvases (UI)
            RaycastResult uiHit = RaycastUI(ray);
            if (uiHit.isValid)
            {
                endPoint = uiHit.worldPosition;
                hasHit = true;
                HandleUIHover(uiHit.gameObject);
            }
            else
            {
                ClearUIHover();

                // 2. Raycast 3D Physical Objects / Avatar Colliders
                RaycastHit physHit;
                if (Physics.Raycast(ray, out physHit, maxRayDistance, physicsLayers, QueryTriggerInteraction.Ignore))
                {
                    endPoint = physHit.point;
                    hasHit = true;
                    Handle3DHover(physHit.collider.gameObject);
                }
                else
                {
                    Clear3DHover();
                }
            }

            // Update Laser Line & Reticle
            _lineRenderer.SetPosition(0, transform.position);
            _lineRenderer.SetPosition(1, endPoint);

            if (hasHit)
            {
                _reticle.SetActive(true);
                _reticle.transform.position = endPoint;
            }
            else
            {
                _reticle.SetActive(false);
            }

            // Read Trigger Input
            CheckTriggerAction(uiHit);
        }

        private RaycastResult RaycastUI(Ray ray)
        {
            var allCanvases = FindObjectsByType<Canvas>(FindObjectsInactive.Exclude, FindObjectsSortMode.None);
            RaycastResult closestResult = default;
            float closestDistance = float.MaxValue;

            foreach (var canvas in allCanvases)
            {
                if (!canvas.isActiveAndEnabled || canvas.renderMode != RenderMode.WorldSpace) continue;

                // Two-sided plane intersection
                Vector3 normal = canvas.transform.forward;
                if (Vector3.Dot(ray.direction, normal) > 0f) normal = -normal;
                Plane canvasPlane = new Plane(normal, canvas.transform.position);

                if (canvasPlane.Raycast(ray, out float enter) && enter > 0 && enter < maxRayDistance && enter < closestDistance)
                {
                    Vector3 worldHit = ray.GetPoint(enter);
                    RectTransform rectTransform = canvas.GetComponent<RectTransform>();
                    if (rectTransform == null) continue;

                    Vector2 canvasLocal = rectTransform.InverseTransformPoint(worldHit);
                    if (rectTransform.rect.Contains(canvasLocal))
                    {
                        var graphics = canvas.GetComponentsInChildren<Graphic>();
                        // Reverse iterate so foreground buttons/inputs are hit before background
                        bool childHit = false;
                        for (int i = graphics.Length - 1; i >= 0; i--)
                        {
                            var g = graphics[i];
                            if (!g.raycastTarget || !g.isActiveAndEnabled) continue;
                            Vector2 gLocal = g.rectTransform.InverseTransformPoint(worldHit);
                            if (g.rectTransform.rect.Contains(gLocal))
                            {
                                closestDistance = enter;
                                closestResult.gameObject = g.gameObject;
                                closestResult.worldPosition = worldHit;
                                closestResult.distance = enter;
                                childHit = true;
                                break;
                            }
                        }

                        if (!childHit)
                        {
                            closestDistance = enter;
                            closestResult.gameObject = canvas.gameObject;
                            closestResult.worldPosition = worldHit;
                            closestResult.distance = enter;
                        }
                    }
                }
            }

            return closestResult;
        }

        private void HandleUIHover(GameObject hitObj)
        {
            if (hitObj != _currentHoveredUI)
            {
                _currentHoveredUI = hitObj;
                SendHapticImpulse(0.2f, 0.05f); // Subtle haptic tick on hover
            }
        }

        private void ClearUIHover()
        {
            _currentHoveredUI = null;
        }

        private void Handle3DHover(GameObject hitObj)
        {
            if (hitObj != _currentHovered3D)
            {
                _currentHovered3D = hitObj;
                SendHapticImpulse(0.15f, 0.04f);
            }
        }

        private void Clear3DHover()
        {
            _currentHovered3D = null;
        }

        private void CheckTriggerAction(RaycastResult uiHit)
        {
            bool isDown = false;
            if (_device.isValid)
            {
                if (_device.TryGetFeatureValue(CommonUsages.trigger, out float triggerVal) && triggerVal > 0.5f)
                {
                    isDown = true;
                }
                else if (_device.TryGetFeatureValue(CommonUsages.triggerButton, out bool triggerBtn) && triggerBtn)
                {
                    isDown = true;
                }
                else if (_device.TryGetFeatureValue(CommonUsages.primaryButton, out bool primaryBtn) && primaryBtn)
                {
                    isDown = true;
                }
                else if (_device.TryGetFeatureValue(CommonUsages.primaryTouch, out bool primaryTouch) && primaryTouch)
                {
                    isDown = true;
                }
            }

            // Support OVRInput controller trigger and hand tracking pinch
            if (!isDown)
            {
                var ctrl = (hand == ControllerHand.Right) ? OVRInput.Controller.RTouch : OVRInput.Controller.LTouch;
                var handCtrl = (hand == ControllerHand.Right) ? OVRInput.Controller.RHand : OVRInput.Controller.LHand;

                isDown = OVRInput.Get(OVRInput.Button.PrimaryIndexTrigger, ctrl) ||
                         OVRInput.Get(OVRInput.Button.One, ctrl) ||
                         OVRInput.Get(OVRInput.Button.PrimaryIndexTrigger, handCtrl) ||
                         OVRInput.Get(OVRInput.Button.One, handCtrl);
            }

            // Detect trigger down (click)
            if (isDown && !_triggerPressed)
            {
                _triggerPressed = true;
                ExecuteTriggerClick(uiHit);
            }
            else if (!isDown && _triggerPressed)
            {
                _triggerPressed = false;
            }
        }

        private void ExecuteTriggerClick(RaycastResult uiHit)
        {
            SendHapticImpulse(0.7f, 0.12f); // Satisfying click haptic

            // 1. UI Click
            if (uiHit.isValid && uiHit.gameObject != null)
            {
                var target = uiHit.gameObject;

                // Check for Button (direct or in parent)
                var btn = target.GetComponent<Button>() ?? target.GetComponentInParent<Button>();
                if (btn != null && btn.interactable)
                {
                    Debug.Log($"[XRControllerRayPointer] Clicked UI Button: {btn.gameObject.name}");
                    btn.onClick.Invoke();
                    return;
                }

                // Check for InputField focus
                var tmpInput = target.GetComponent<TMP_InputField>() ?? target.GetComponentInParent<TMP_InputField>();
                if (tmpInput != null)
                {
                    tmpInput.ActivateInputField();
                    return;
                }

                var legacyInput = target.GetComponent<InputField>() ?? target.GetComponentInParent<InputField>();
                if (legacyInput != null)
                {
                    legacyInput.ActivateInputField();
                    return;
                }

                // Generic pointer click event
                ExecuteEvents.Execute(target, new PointerEventData(EventSystem.current), ExecuteEvents.pointerClickHandler);
                return;
            }

            // 2. 3D Object / Avatar Click
            if (_currentHovered3D != null)
            {
                Debug.Log($"[XRControllerRayPointer] Interacted with 3D object: {_currentHovered3D.name}");

                // Check if avatar was clicked
                var brain = _currentHovered3D.GetComponentInParent<FoveAI.Avatar.AvatarAnimationBrain>();
                if (brain != null)
                {
                    // Trigger avatar social turn and happy reaction
                    brain.Poke();
                }
            }
        }

        public void SendHapticImpulse(float amplitude, float duration)
        {
            if (_device.isValid)
            {
                HapticCapabilities caps;
                if (_device.TryGetHapticCapabilities(out caps) && caps.supportsImpulse)
                {
                    _device.SendHapticImpulse(0, Mathf.Clamp01(amplitude), duration);
                }
            }
        }

        private void OnDestroy()
        {
            if (_reticle != null)
            {
                Destroy(_reticle);
            }
        }
    }
}
