using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.XR;

namespace FoveAI.XR
{
    /// <summary>
    /// XR Thumbstick Locomotion for Quest 3 — using the new Input System.
    ///
    /// Left thumbstick  = smooth move (walk) in the direction you point
    /// Right thumbstick = snap turn (rotate left/right in increments)
    ///
    /// Uses InputAction with XR controller bindings (new Input System),
    /// not legacy InputDevice polling. Works with OpenXR + Meta Quest 3.
    ///
    /// The rig moves the CameraRig (this transform), so the player walks
    /// beyond their physical room space. Physical walking still works
    /// (room-scale tracking is unaffected).
    /// </summary>
    public class XRThumbstickLocomotion : MonoBehaviour
    {
        [Header("Move Settings (Left Stick)")]
        [Tooltip("Maximum move speed in meters per second.")]
        [SerializeField] private float moveSpeed = 1.5f;
        [Tooltip("Deadzone for the thumbstick — below this, no movement.")]
        [Range(0f, 0.5f)] [SerializeField] private float moveDeadzone = 0.15f;

        [Header("Turn Settings (Right Stick)")]
        [Tooltip("Snap turn angle in degrees.")]
        [SerializeField] private float snapTurnAngle = 30f;
        [Tooltip("Deadzone for the turn thumbstick.")]
        [Range(0f, 0.5f)] [SerializeField] private float turnDeadzone = 0.5f;
        [Tooltip("Cooldown between snap turns in seconds.")]
        [SerializeField] private float turnCooldown = 0.25f;

        [Header("Comfort")]
        [Tooltip("If true, movement direction follows the head gaze, not the rig forward.")]
        [SerializeField] private bool headGazeMovement = true;

        private InputAction _moveAction;
        private InputAction _turnAction;
        private float _lastTurnTime;
        private Camera _mainCamera;

        private void Awake()
        {
            // ── Create InputActions with XR controller bindings (new Input System) ──

            _moveAction = new InputAction(
                name: "XR Move",
                type: InputActionType.Value,
                binding: "<XRController>{LeftHand}/thumbstick",
                expectedControlType: "Vector2"
            );
            // Fallback binding for OpenXR-specific path
            _moveAction.AddBinding("<OpenXRController>{LeftHand}/Primary2DAxis");

            _turnAction = new InputAction(
                name: "XR Turn",
                type: InputActionType.Value,
                binding: "<XRController>{RightHand}/thumbstick",
                expectedControlType: "Vector2"
            );
            _turnAction.AddBinding("<OpenXRController>{RightHand}/Primary2DAxis");
        }

        private void OnEnable()
        {
            _moveAction.Enable();
            _turnAction.Enable();
        }

        private void OnDisable()
        {
            _moveAction.Disable();
            _turnAction.Disable();
        }

        private void Start()
        {
            _mainCamera = Camera.main;
        }

        private void Update()
        {
            UpdateMove();
            UpdateTurn();
        }

        // ── Smooth Move (Left Thumbstick) ──

        private void UpdateMove()
        {
            Vector2 stick = _moveAction.ReadValue<Vector2>();

            // Deadzone
            if (stick.magnitude < moveDeadzone) return;

            // Normalize after deadzone
            Vector2 input = stick.normalized * Mathf.Clamp01(stick.magnitude);

            // Direction: forward based on head or rig
            Vector3 forward;
            if (headGazeMovement && _mainCamera != null)
            {
                forward = _mainCamera.transform.forward;
            }
            else
            {
                forward = transform.forward;
            }
            forward.y = 0f;
            forward.Normalize();

            Vector3 right = _mainCamera != null ? _mainCamera.transform.right : transform.right;
            right.y = 0f;
            right.Normalize();

            // Combine: stick.y = forward/back, stick.x = strafe left/right
            Vector3 moveDir = (forward * input.y) + (right * input.x);
            if (moveDir.sqrMagnitude > 1f) moveDir.Normalize();

            // Move the rig
            Vector3 move = moveDir * moveSpeed * Time.deltaTime;
            transform.position += move;
        }

        // ── Snap Turn (Right Thumbstick) ──

        private void UpdateTurn()
        {
            Vector2 stick = _turnAction.ReadValue<Vector2>();

            // Deadzone
            if (Mathf.Abs(stick.x) < turnDeadzone) return;

            // Cooldown
            if (Time.time - _lastTurnTime < turnCooldown) return;

            // Snap turn
            float angle = stick.x > 0f ? snapTurnAngle : -snapTurnAngle;
            transform.Rotate(0f, angle, 0f);
            _lastTurnTime = Time.time;
        }

        // ── Public API ──

        /// <summary>Set the move speed at runtime (m/s).</summary>
        public void SetMoveSpeed(float speed) => moveSpeed = speed;

        /// <summary>Set the snap turn angle at runtime (degrees).</summary>
        public void SetSnapTurnAngle(float angle) => snapTurnAngle = angle;

        /// <summary>Toggle between head-gaze and rig-forward movement.</summary>
        public void SetHeadGazeMovement(bool enabled) => headGazeMovement = enabled;

        private void OnDestroy()
        {
            _moveAction?.Dispose();
            _turnAction?.Dispose();
        }
    }
}
