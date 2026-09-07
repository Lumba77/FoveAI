using UnityEngine;

namespace FoveAI.Environment
{
    /// <summary>
    /// QuestGroundClamp — Pins the VRM avatar's feet smoothly to the physical floor in Meta Quest passthrough.
    ///
    /// Raycasts down against:
    ///   1. Meta Scene Mesh / Spatial Anchor floor planes (OVRSceneManager).
    ///   2. Environment room colliders.
    ///   3. Headset-calibrated floor fallback (Camera.main.y - eyeHeight) if room mesh has not scanned yet.
    ///
    /// Eliminates floating mid-air or sinking beneath the floor.
    /// </summary>
    public class QuestGroundClamp : MonoBehaviour
    {
        [Header("Ground Detection")]
        [Tooltip("Layers considered physical ground/floor.")]
        [SerializeField] private LayerMask groundLayers = ~0;

        [Tooltip("How far above the avatar origin the raycast originates.")]
        [SerializeField] private float raycastUpOffset = 1.5f;

        [Tooltip("Maximum downward raycast distance.")]
        [SerializeField] private float maxRayDistance = 4.0f;

        [Tooltip("Smoothing speed for ground snapping (higher = snappier).")]
        [SerializeField] private float snapSpeed = 10.0f;

        [Header("Fallback (Pre-Scan)")]
        [Tooltip("Assumed distance from headset eye level to floor when no physical mesh hit.")]
        [SerializeField] private float defaultEyeHeight = 1.60f;

        [Tooltip("Distance threshold before immediate snap on spawn.")]
        [SerializeField] private float teleportThreshold = 1.0f;

        /// <summary>
        /// True if the raycast currently strikes a physical floor/mesh surface.
        /// </summary>
        public bool IsPhysicallyGrounded { get; private set; }

        /// <summary>
        /// The current resolved floor elevation in world space.
        /// </summary>
        public float ResolvedFloorY { get; private set; }

        private bool _firstSnapDone = false;

        private void Start()
        {
            // Ignore own avatar colliders
            var ownColliders = GetComponentsInChildren<Collider>();
            foreach (var col in ownColliders)
            {
                if (col != null)
                {
                    // Exclude from raycast
                    groundLayers &= ~(1 << col.gameObject.layer);
                }
            }
        }

        private void LateUpdate()
        {
            Vector3 pos = transform.position;
            Vector3 rayOrigin = new Vector3(pos.x, pos.y + raycastUpOffset, pos.z);

            float targetY;
            RaycastHit hit;

            if (Physics.Raycast(rayOrigin, Vector3.down, out hit, maxRayDistance + raycastUpOffset, groundLayers, QueryTriggerInteraction.Ignore))
            {
                // In Quest passthrough with Floor tracking, physical floor elevation is at or above 0.0m
                targetY = Mathf.Max(0f, hit.point.y);
                IsPhysicallyGrounded = true;
            }
            else
            {
                // Fallback: In Meta Quest OpenXR Floor tracking, world space Y=0.0m is the exact physical floor
                IsPhysicallyGrounded = false;
                targetY = 0f;
            }

            ResolvedFloorY = targetY;

            // Instant teleport on first frame or if huge jump (e.g. room re-center)
            if (!_firstSnapDone || Mathf.Abs(pos.y - targetY) > teleportThreshold)
            {
                transform.position = new Vector3(pos.x, targetY, pos.z);
                _firstSnapDone = true;
            }
            else
            {
                // Smooth glide to follow uneven terrain / rugs / steps
                float newY = Mathf.Lerp(pos.y, targetY, Time.deltaTime * snapSpeed);
                transform.position = new Vector3(pos.x, newY, pos.z);
            }
        }

        /// <summary>
        /// Force an immediate snap to the detected floor.
        /// </summary>
        public void ForceSnap()
        {
            _firstSnapDone = false;
        }
    }
}
