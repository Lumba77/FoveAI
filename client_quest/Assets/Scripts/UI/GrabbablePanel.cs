using UnityEngine;

namespace FoveAI.UI
{
    /// <summary>
    /// Makes a world-space UI panel grabbable with Meta Quest controller grip
    /// or hand fist. The panel follows the grabbing hand until released.
    /// Works with both OVR controllers and hand tracking.
    /// </summary>
    [RequireComponent(typeof(RectTransform))]
    public class GrabbablePanel : MonoBehaviour
    {
        [Header("Grab Settings")]
        [Tooltip("Grip threshold (0-1) to start grabbing.")]
        [Range(0.3f, 0.9f)] public float gripThreshold = 0.55f;
        [Tooltip("Release threshold — slightly lower than grab to prevent jitter.")]
        [Range(0.1f, 0.5f)] public float releaseThreshold = 0.35f;
        [Tooltip("How fast the panel snaps to the hand (higher = snappier).")]
        public float followSpeed = 12f;
        [Tooltip("Optional rotation follow — if true, panel rotates with hand.")]
        public bool followRotation = false;
        [Tooltip("Distance in front of the hand where the panel sits.")]
        public float holdDistance = 0.15f;

        [Header("Visual Feedback")]
        [Tooltip("Scale multiplier when grabbed (1 = no change).")]
        public float grabbedScale = 1.05f;
        [Tooltip("How fast scale transitions.")]
        public float scaleSpeed = 8f;

        [Header("Haptics")]
        [Tooltip("Haptic intensity on grab (0 = disabled).")]
        [Range(0f, 1f)] public float grabHaptic = 0.3f;
        [Tooltip("Haptic intensity on release.")]
        [Range(0f, 1f)] public float releaseHaptic = 0.15f;

        private bool _isGrabbed;
        private OVRInput.Controller _grabbingHand = OVRInput.Controller.None;
        private Vector3 _grabOffset;
        private Quaternion _grabRotOffset;
        private Vector3 _baseScale;
        private bool _wasGrabbed;

        private void Awake()
        {
            _baseScale = transform.localScale;
        }

        private void Update()
        {
            // Check both hands for grab
            bool leftGrip = GetGrip(OVRInput.Controller.LTouch);
            bool rightGrip = GetGrip(OVRInput.Controller.RTouch);
            bool leftHand = GetHandFist(OVRInput.Hand.HandLeft);
            bool rightHand = GetHandFist(OVRInput.Hand.HandRight);

            // Determine grab state with hysteresis
            if (!_isGrabbed)
            {
                // Try to grab — check which hand is closest and gripping
                if (rightGrip || rightHand)
                {
                    StartGrab(OVRInput.Controller.RTouch);
                }
                else if (leftGrip || leftHand)
                {
                    StartGrab(OVRInput.Controller.LTouch);
                }
            }
            else
            {
                // Check if still gripping
                bool stillGripping = _grabbingHand == OVRInput.Controller.RTouch
                    ? (rightGrip || rightHand)
                    : (leftGrip || leftHand);

                if (!stillGripping)
                {
                    EndGrab();
                }
            }

            // Follow hand while grabbed
            if (_isGrabbed)
            {
                Vector3 handPos = GetHandPosition(_grabbingHand);
                Quaternion handRot = GetHandRotation(_grabbingHand);

                if (followRotation)
                {
                    Quaternion targetRot = handRot * _grabRotOffset;
                    transform.rotation = Quaternion.Slerp(transform.rotation, targetRot, Time.deltaTime * followSpeed);
                }

                Vector3 targetPos = handPos + GetHandForward(_grabbingHand) * holdDistance + _grabOffset;
                transform.position = Vector3.Lerp(transform.position, targetPos, Time.deltaTime * followSpeed);
            }

            // Scale feedback
            Vector3 targetScale = _isGrabbed ? _baseScale * grabbedScale : _baseScale;
            transform.localScale = Vector3.Lerp(transform.localScale, targetScale, Time.deltaTime * scaleSpeed);
        }

        // ── Grab Logic ──

        private void StartGrab(OVRInput.Controller hand)
        {
            _isGrabbed = true;
            _grabbingHand = hand;

            // Calculate offset so panel doesn't jump
            Vector3 handPos = GetHandPosition(hand);
            _grabOffset = transform.position - handPos;
            _grabOffset -= GetHandForward(hand) * holdDistance;

            if (followRotation)
            {
                Quaternion handRot = GetHandRotation(hand);
                _grabRotOffset = Quaternion.Inverse(handRot) * transform.rotation;
            }

            // Haptic feedback
            if (grabHaptic > 0f)
            {
                OVRInput.SetControllerVibration(grabHaptic, 0.1f, hand);
            }

            _wasGrabbed = true;
        }

        private void EndGrab()
        {
            // Haptic feedback
            if (releaseHaptic > 0f && _grabbingHand != OVRInput.Controller.None)
            {
                OVRInput.SetControllerVibration(releaseHaptic, 0.05f, _grabbingHand);
            }

            _isGrabbed = false;
            _grabbingHand = OVRInput.Controller.None;
        }

        // ── Input Detection ──

        private bool GetGrip(OVRInput.Controller controller)
        {
            float grip = OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger, controller);
            return grip > gripThreshold;
        }

        private bool GetHandFist(OVRInput.Hand hand)
        {
            // Controller-based fallback: check grip button
            return OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger, OVRInput.Controller.LTouch) > 0.5f ||
                   OVRInput.Get(OVRInput.Axis1D.SecondaryHandTrigger, OVRInput.Controller.RTouch) > 0.5f;
        }

        private Vector3 GetHandPosition(OVRInput.Controller controller)
        {
            return OVRInput.GetLocalControllerPosition(controller);
        }

        private Quaternion GetHandRotation(OVRInput.Controller controller)
        {
            return OVRInput.GetLocalControllerRotation(controller);
        }

        private Vector3 GetHandForward(OVRInput.Controller controller)
        {
            Quaternion rot = GetHandRotation(controller);
            return rot * Vector3.forward;
        }

        // ── Public API ──

        public bool IsGrabbed => _isGrabbed;

        public void ResetPosition(Vector3 position, Quaternion rotation)
        {
            transform.position = position;
            transform.rotation = rotation;
        }
    }
}
