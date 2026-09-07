using UnityEngine;

namespace FoveAI.Environment
{
    /// <summary>
    /// Drops an OVRSpatialAnchor to designate the "Face-to-Face Booth".
    /// Alicechan's navigation logic will use this anchor's coordinates 
    /// to walk over to the user.
    /// </summary>
    public class SpatialBoothAnchor : MonoBehaviour
    {
        public OVRSpatialAnchor boothAnchor;

        private void Start()
        {
            // Drop a spatial anchor exactly where this GameObject is placed.
            boothAnchor = gameObject.AddComponent<OVRSpatialAnchor>();
            Debug.Log("[SpatialBoothAnchor] Face-to-Face Booth anchor created at: " + transform.position);
        }
    }
}
