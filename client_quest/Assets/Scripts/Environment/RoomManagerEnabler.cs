using System.Collections;
using UnityEngine;

namespace FoveAI.Environment
{
    /// <summary>
    /// Enables the room scanning components (OVRSceneManager, RoomScanner, RoomPlasterClient, NavMeshSurface)
    /// after a short delay so they don't block app startup.
    /// The room scanning components are disabled in the scene builder to prevent them from
    /// hanging the app during initialization. This script enables them once the app is running.
    /// </summary>
    public class RoomManagerEnabler : MonoBehaviour
    {
        [Tooltip("Delay in seconds before enabling room scanning components.")]
        [SerializeField] private float enableDelay = 3f;

        private void Start()
        {
            StartCoroutine(EnableRoomComponentsAfterDelay());
        }

        private IEnumerator EnableRoomComponentsAfterDelay()
        {
            yield return new WaitForSeconds(enableDelay);

            Debug.Log("[RoomManagerEnabler] Enabling room scanning components...");

            // OVRSceneManager silently no-ops without an OVRManager instance.
            // OVRManager is safe alongside OpenXR — it only hosts OVRPlugin services
            // (Scene API, anchors) and does not drive tracking/rendering.
            if (OVRManager.instance == null)
            {
                gameObject.AddComponent<OVRManager>();
                Debug.Log("[RoomManagerEnabler] Created OVRManager (required by OVRSceneManager).");
            }

            var sceneManager = GetComponent<OVRSceneManager>();
            if (sceneManager != null)
            {
                sceneManager.enabled = true;
                Debug.Log("[RoomManagerEnabler] OVRSceneManager enabled.");
            }

            var roomScanner = GetComponent<RoomScanner>();
            if (roomScanner != null)
            {
                roomScanner.enabled = true;
                Debug.Log("[RoomManagerEnabler] RoomScanner enabled.");
            }

            var roomPlaster = GetComponent<RoomPlasterClient>();
            if (roomPlaster != null)
            {
                roomPlaster.enabled = true;
                Debug.Log("[RoomManagerEnabler] RoomPlasterClient enabled.");
            }

            // NavMeshSurface lives in the Unity.AI.Navigation package.
            // Use reflection to avoid a hard compile-time dependency —
            // if the package isn't resolved, the build still succeeds.
            var navSurface = GetComponent("NavMeshSurface");
            if (navSurface != null)
            {
                var enabledProp = navSurface.GetType().GetProperty("enabled");
                if (enabledProp != null)
                {
                    enabledProp.SetValue(navSurface, true);
                    Debug.Log("[RoomManagerEnabler] NavMeshSurface enabled.");
                }
            }
        }
    }
}
