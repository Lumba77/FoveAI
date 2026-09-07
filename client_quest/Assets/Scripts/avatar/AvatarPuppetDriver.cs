using System;
using System.Collections;
using UnityEngine;
using FoveAI.IPC;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Acts as the "Motor Cortex" for Alicechan.
    /// Listens for `motor_action` events from the FoveAIWebSocketClient
    /// and physically puppeteers the VRM avatar (locomotion, IK, gestures).
    /// </summary>
    public class AvatarPuppetDriver : MonoBehaviour
    {
        [Tooltip("The WebSocket client providing the motor commands.")]
        [SerializeField] private FoveAIWebSocketClient wsClient;

        [Tooltip("The blendshape driver for emotional changes.")]
        [SerializeField] private AvatarBlendshapeDriver blendshapeDriver;

        [Tooltip("The transform to move/rotate when walking.")]
        [SerializeField] private Transform avatarTransform;

        [Header("Locomotion Settings")]
        public float walkSpeed = 1.0f;
        public float rotationSpeed = 3.0f;

        private Vector3 _targetPosition;
        private Quaternion _targetRotation;
        private bool _isWalking = false;
        private bool _isWaypointWalking = false;

        private Animator _animator;
        private float _walkPhase = 0f;

        // --- AI Virtual Controller ---
        private Vector2 _aiVirtualMove = Vector2.zero;
        private Vector2 _aiVirtualSpin = Vector2.zero;
        private Coroutine _aiVirtualTimer;

        private void Awake()
        {
            if (avatarTransform == null)
            {
                avatarTransform = transform; // Default to this GameObject
            }

            if (blendshapeDriver == null)
            {
                blendshapeDriver = GetComponent<AvatarBlendshapeDriver>();
            }

            if (wsClient == null)
            {
                wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            }

            _targetPosition = avatarTransform.position;
            _targetRotation = avatarTransform.rotation;
        }

        private void OnEnable()
        {
            if (wsClient != null)
            {
                wsClient.OnMotorActionReceived += HandleMotorAction;
            }
        }

        private void OnDisable()
        {
            if (wsClient != null)
            {
                wsClient.OnMotorActionReceived -= HandleMotorAction;
            }
        }

        private void Update()
        {
            if (_isWaypointWalking)
            {
                // Smooth locomotion towards target
                avatarTransform.position = Vector3.MoveTowards(avatarTransform.position, _targetPosition, walkSpeed * Time.deltaTime);
                avatarTransform.rotation = Quaternion.Slerp(avatarTransform.rotation, _targetRotation, rotationSpeed * Time.deltaTime);

                _walkPhase += walkSpeed * Time.deltaTime * 5f; // Used for procedural animation

                if (Vector3.Distance(avatarTransform.position, _targetPosition) < 0.05f)
                {
                    _isWaypointWalking = false;
                }
            }
            // Walk phase is reset in HandleInputs if not walking.

            // --- Altitude Rescue System (disabled — conflicts with VRMAvatarLoader floor correction) ---
            // The VRMAvatarLoader now measures bounds and places feet on floor correctly.
            // This altitude rescue was fighting that correction and causing the avatar to sink.
            
            // --- Physics & Motor Inputs ---
            HandleInputs();
        }

        private bool _isPuppetSteeringActive = false;
        private float _lastGripTime = 0f;
        private const float GripDoubleThreshold = 0.35f;

        private void HandleInputs()
        {
            // Double-Grip: Toggle direct avatar steering mode
            bool gripDown = OVRInput.GetDown(OVRInput.Button.PrimaryHandTrigger) || OVRInput.GetDown(OVRInput.Button.SecondaryHandTrigger);
            if (gripDown)
            {
                float now = Time.time;
                if (now - _lastGripTime <= GripDoubleThreshold)
                {
                    _isPuppetSteeringActive = !_isPuppetSteeringActive;
                    _lastGripTime = 0f;

                    string state = _isPuppetSteeringActive ? "ACTIVATED" : "DEACTIVATED";
                    Debug.Log($"[AvatarPuppetDriver] Puppet Steering Mode {state}!");
                    FoveAI.UI.XRIDEHud.FlashNotification($"🎮 PUPPET STEERING {state}", 2.5f);
                    FoveAI.DebugOverlay.QuestDebugOverlay.Log($"🎮 Puppet Steering {state}");

                    OVRInput.SetControllerVibration(0.6f, 0.6f, OVRInput.Controller.All);
                    Invoke(nameof(StopSteeringHaptics), 0.15f);
                }
                else
                {
                    _lastGripTime = now;
                }
            }

            // Direct game-character steering with joystick
            Vector3 moveDir = Vector3.zero;

            if (_isPuppetSteeringActive)
            {
                Vector2 xrStick = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick);
                if (xrStick.sqrMagnitude < 0.05f)
                {
                    xrStick = OVRInput.Get(OVRInput.Axis2D.SecondaryThumbstick);
                }

                if (xrStick.sqrMagnitude > 0.05f && Camera.main != null)
                {
                    Vector3 camFwd = Camera.main.transform.forward;
                    camFwd.y = 0; camFwd.Normalize();
                    Vector3 camRight = Camera.main.transform.right;
                    camRight.y = 0; camRight.Normalize();

                    moveDir += camFwd * xrStick.y + camRight * xrStick.x;
                }
            }

            // AI Virtual Controller Input
            if (_aiVirtualMove.sqrMagnitude > 0.01f)
            {
                Vector3 aiFwd = avatarTransform.forward;
                aiFwd.y = 0; aiFwd.Normalize();
                Vector3 aiRight = avatarTransform.right;
                aiRight.y = 0; aiRight.Normalize();
                
                moveDir += aiFwd * _aiVirtualMove.y + aiRight * _aiVirtualMove.x;
            }

            // Spin Input
            if (Mathf.Abs(_aiVirtualSpin.x) > 0.05f)
            {
                avatarTransform.Rotate(Vector3.up, _aiVirtualSpin.x * rotationSpeed * 30f * Time.deltaTime);
            }

            bool joystickMoving = false;

            if (moveDir.sqrMagnitude > 0.001f)
            {
                avatarTransform.position += moveDir * walkSpeed * Time.deltaTime;
                
                // Only override rotation if AI is not manually spinning
                if (Mathf.Abs(_aiVirtualSpin.x) < 0.05f)
                {
                    avatarTransform.rotation = Quaternion.Slerp(avatarTransform.rotation, Quaternion.LookRotation(moveDir), Time.deltaTime * rotationSpeed);
                }
                
                joystickMoving = true;
                _walkPhase += walkSpeed * Time.deltaTime * 6f;
            }
            else if (Mathf.Abs(_aiVirtualSpin.x) > 0.05f)
            {
                // Spinning in place causes stepping
                joystickMoving = true;
                _walkPhase += (Mathf.Abs(_aiVirtualSpin.x) * walkSpeed * 0.5f) * Time.deltaTime * 6f;
            }

            // State management
            if (joystickMoving)
            {
                _isWaypointWalking = false;
                _isWalking = true;
            }
            else if (!_isWaypointWalking)
            {
                _isWalking = false;
                _walkPhase = 0f;
            }
        }

        private void StopSteeringHaptics()
        {
            OVRInput.SetControllerVibration(0f, 0f, OVRInput.Controller.All);
        }

        private void LateUpdate()
        {
            // --- Procedural Animation System (T-Pose Fix) ---
            // Only apply procedural arm/leg poses when no VRMA animation is playing.
            // Previously this only skipped for non-human avatars, which meant humanoid
            // VRM avatars had their VRMA animation overwritten every frame by procedural
            // bone rotations — causing the persistent T-pose.
            if (_animator == null)
            {
                _animator = GetComponentInChildren<Animator>();
            }

            var vrmaLoader = GetComponentInChildren<FoveAI.Avatar.VRMAAnimationLoader>();
            bool hasVrmaPlaying = vrmaLoader != null && !string.IsNullOrEmpty(vrmaLoader.GetCurrentAnimation());
            if (hasVrmaPlaying)
            {
                // VRMA is playing via PlayableGraph — let the Animator handle bone poses.
                // Do NOT override with procedural rotations.
                return;
            }

            if (_animator != null)
            {
                Transform leftArm = _animator.isHuman ? _animator.GetBoneTransform(HumanBodyBones.LeftUpperArm) : null;
                Transform rightArm = _animator.isHuman ? _animator.GetBoneTransform(HumanBodyBones.RightUpperArm) : null;
                Transform leftLeg = _animator.isHuman ? _animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg) : null;
                Transform rightLeg = _animator.isHuman ? _animator.GetBoneTransform(HumanBodyBones.RightUpperLeg) : null;

                // Fallback deep search if humanoid bone mapping isn't directly exposed
                if (leftArm == null) leftArm = FindDeepChild(transform, "LeftUpperArm") ?? FindDeepChild(transform, "J_Bip_L_UpperArm") ?? FindDeepChild(transform, "LeftArm");
                if (rightArm == null) rightArm = FindDeepChild(transform, "RightUpperArm") ?? FindDeepChild(transform, "J_Bip_R_UpperArm") ?? FindDeepChild(transform, "RightArm");
                if (leftLeg == null) leftLeg = FindDeepChild(transform, "LeftUpperLeg") ?? FindDeepChild(transform, "J_Bip_L_UpperLeg");
                if (rightLeg == null) rightLeg = FindDeepChild(transform, "RightUpperLeg") ?? FindDeepChild(transform, "J_Bip_R_UpperLeg");

                float armSwing = _isWalking ? Mathf.Sin(_walkPhase) * 30f : 0f;
                float legSwing = _isWalking ? Mathf.Sin(_walkPhase) * 30f : 0f;

                // Procedural resting arm posture & walk swing when no VRMA animation is playing
                if (!hasVrmaPlaying)
                {
                    float breathSway = Mathf.Sin(_walkPhase) * 1.5f;
                    if (leftArm != null)
                        leftArm.localRotation = Quaternion.Euler(10f + armSwing, breathSway, 70f);
                    if (rightArm != null)
                        rightArm.localRotation = Quaternion.Euler(10f - armSwing, -breathSway, -70f);
                    if (leftLeg != null && _isWalking)
                        leftLeg.localRotation = Quaternion.Euler(-legSwing, 0, 0);
                    if (rightLeg != null && _isWalking)
                        rightLeg.localRotation = Quaternion.Euler(legSwing, 0, 0);
                }
            }
        }

        public void HandleMotorAction(string toolName, string argsJson)
        {
            try
            {
                switch (toolName)
                {
                    case "virtual_gamepad":
                        float mx = ExtractFloatField(argsJson, "move_x");
                        float my = ExtractFloatField(argsJson, "move_y");
                        float sx = ExtractFloatField(argsJson, "spin_x");
                        float duration = ExtractFloatField(argsJson, "duration");
                        
                        _aiVirtualMove = new Vector2(mx, my);
                        _aiVirtualSpin = new Vector2(sx, 0f);
                        
                        if (duration <= 0f) duration = 0.5f; // fallback duration

                        if (_aiVirtualTimer != null) StopCoroutine(_aiVirtualTimer);
                        _aiVirtualTimer = StartCoroutine(ResetAIVirtualInputAfter(duration));
                        break;

                    case "walk_forward":
                        float distance = ExtractFloatField(argsJson, "distance");
                        if (distance > 0)
                        {
                            _targetPosition = avatarTransform.position + (avatarTransform.forward * distance);
                            _isWaypointWalking = true;
                            _isWalking = true;
                        }
                        break;

                    case "walk_to_target":
                        string targetName = ExtractStringField(argsJson, "target");
                        // In a real spatial mapping, we would look up the target's coordinates.
                        // For now, if the target is "user", walk towards the camera rig.
                        if (targetName.ToLower().Contains("user"))
                        {
                            Camera mainCam = Camera.main;
                            if (mainCam != null)
                            {
                                // Walk towards the user, stopping 1.5m away
                                Vector3 directionToUser = (mainCam.transform.position - avatarTransform.position);
                                directionToUser.y = 0; // keep it flat on the floor
                                float distToUser = directionToUser.magnitude;

                                if (distToUser > 1.5f)
                                {
                                    _targetPosition = avatarTransform.position + directionToUser.normalized * (distToUser - 1.5f);
                                    _targetRotation = Quaternion.LookRotation(directionToUser);
                                    _isWaypointWalking = true;
                                    _isWalking = true;
                                }
                            }
                        }
                        break;

                    case "change_emotion":
                        string emotion = ExtractStringField(argsJson, "emotion");
                        float intensity = ExtractFloatField(argsJson, "intensity");
                        if (blendshapeDriver != null)
                        {
                            blendshapeDriver.ApplyEmotion(emotion, intensity > 0 ? intensity : 1.0f);
                        }
                        break;

                    case "trigger_micro_gesture":
                        string gesture = ExtractStringField(argsJson, "gesture");
                        Debug.Log($"[AvatarPuppetDriver] Triggering micro-gesture: {gesture}");
                        // Route through VRMA loader for clip playback
                        var vrma = GetComponentInChildren<VRMAAnimationLoader>();
                        if (vrma != null)
                        {
                            // Map common gesture names to VRMA clips
                            var gestureMap = new System.Collections.Generic.Dictionary<string, string>
                            {
                                {"nod", "vrma_02"}, {"tilt", "vrma_05"}, {"shake", "vrma_06"},
                                {"look_away", "lookaround"}, {"bow", "vrma_03"},
                                {"wave", "goodbye"}, {"clap", "clapping"},
                                {"think", "thinking"}, {"shrug", "vrma_07"},
                                {"dance", "vrma_01"}, {"jump", "jump"},
                            };
                            string clip = gestureMap.TryGetValue(gesture, out var g) ? g : gesture;
                            vrma.CrossFade(clip, 0.3f);
                        }
                        break;

                    default:
                        Debug.LogWarning($"[AvatarPuppetDriver] Unknown motor action tool: {toolName}");
                        break;
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[AvatarPuppetDriver] Error handling motor action: {ex.Message}");
            }
        }

        private IEnumerator ResetAIVirtualInputAfter(float duration)
        {
            yield return new WaitForSeconds(duration);
            _aiVirtualMove = Vector2.zero;
            _aiVirtualSpin = Vector2.zero;
        }

        // --- Lightweight JSON extraction ---
        private static string ExtractStringField(string json, string fieldName)
        {
            string key = "\"" + fieldName + "\"";
            int keyIdx = json.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (keyIdx < 0) return "";
            int colonIdx = json.IndexOf(':', keyIdx + key.Length);
            if (colonIdx < 0) return "";
            int valueStart = colonIdx + 1;
            while (valueStart < json.Length && (char.IsWhiteSpace(json[valueStart]) || json[valueStart] == '\"')) valueStart++;
            int valueEnd = json.IndexOf('\"', valueStart);
            if (valueEnd < 0) return "";
            return json.Substring(valueStart, valueEnd - valueStart);
        }

        private static float ExtractFloatField(string json, string fieldName)
        {
            string key = "\"" + fieldName + "\"";
            int keyIdx = json.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (keyIdx < 0) return 0f;
            int colonIdx = json.IndexOf(':', keyIdx + key.Length);
            if (colonIdx < 0) return 0f;
            int valueStart = colonIdx + 1;
            while (valueStart < json.Length && (char.IsWhiteSpace(json[valueStart]) || json[valueStart] == '\"')) valueStart++;
            int valueEnd = valueStart;
            while (valueEnd < json.Length && (char.IsDigit(json[valueEnd]) || json[valueEnd] == '.' || json[valueEnd] == '-')) valueEnd++;
            // Culture-invariant parse — Quest may use comma as decimal separator
            if (float.TryParse(json.Substring(valueStart, valueEnd - valueStart),
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture,
                out float result))
            {
                return result;
            }
            return 0f;
        }

        private static Transform FindDeepChild(Transform parent, string name)
        {
            if (parent == null) return null;
            foreach (Transform child in parent)
            {
                if (child.name.Equals(name, StringComparison.OrdinalIgnoreCase) || child.name.Contains(name))
                    return child;
                var found = FindDeepChild(child, name);
                if (found != null) return found;
            }
            return null;
        }
    }
}
