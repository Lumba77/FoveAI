using System;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;

namespace FoveAI.Environment
{
    [Serializable]
    public class SpatialObjectData
    {
        public string id;
        public string label; // e.g. "WALL_FACE", "DESK", "COUCH"
        public Vector3 center;
        public Vector3 size;
        public Quaternion rotation;
    }

    [Serializable]
    public class RoomGeometryPayload
    {
        public string event_type = "spatial.room_geometry";
        public List<SpatialObjectData> objects = new List<SpatialObjectData>();
    }

    /// <summary>
    /// Scans the physical room geometry via Meta's OVRSceneManager.
    /// Extracts bounding boxes of walls, floors, tables, etc., and sends them
    /// to the backend to give Alicechan true spatial awareness.
    /// </summary>
    [RequireComponent(typeof(OVRSceneManager))]
    public class RoomScanner : MonoBehaviour
    {
        [Header("Dependencies")]
        [Tooltip("The main websocket client to send the geometry to.")]
        [SerializeField] private FoveAIWebSocketClient wsClient;

        private OVRSceneManager _sceneManager;

        private void Awake()
        {
            _sceneManager = GetComponent<OVRSceneManager>();

            if (wsClient == null)
            {
                wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            }
        }

        private void OnEnable()
        {
            if (_sceneManager != null)
            {
                _sceneManager.SceneModelLoadedSuccessfully += OnSceneModelLoaded;
            }
        }

        private void OnDisable()
        {
            if (_sceneManager != null)
            {
                _sceneManager.SceneModelLoadedSuccessfully -= OnSceneModelLoaded;
            }
        }

        private void OnSceneModelLoaded()
        {
            Debug.Log("[RoomScanner] Physical room model loaded. Scanning geometry...");
            ScanAndSendGeometry();
            
            // Build NavMesh for physical navigation (via reflection — NavMeshSurface
            // lives in Unity.AI.Navigation and may not resolve at compile time)
            var navSurface = GetComponent("NavMeshSurface");
            if (navSurface != null)
            {
                Debug.Log("[RoomScanner] Baking dynamic NavMesh over physical furniture...");
                var buildMethod = navSurface.GetType().GetMethod("BuildNavMesh", Type.EmptyTypes);
                if (buildMethod != null) buildMethod.Invoke(navSurface, null);
            }
        }

        public void ScanAndSendGeometry()
        {
            if (wsClient == null || !wsClient.isActiveAndEnabled)
            {
                Debug.LogWarning("[RoomScanner] WebSocket client is missing or inactive. Cannot send room geometry.");
                return;
            }

            var payload = new RoomGeometryPayload();
            var sceneAnchors = FindObjectsByType<OVRSceneAnchor>(FindObjectsInactive.Exclude);

            foreach (var anchor in sceneAnchors)
            {
                string label = "UNKNOWN";

                // Attempt to get semantic label if available (requires OVRSemanticClassification)
                var classification = anchor.GetComponent<OVRSemanticClassification>();
                if (classification != null && classification.Labels.Count > 0)
                {
                    label = classification.Labels[0];
                }

                // Get bounding box from mesh renderer
                var meshRenderer = anchor.GetComponentInChildren<MeshRenderer>();
                if (meshRenderer != null)
                {
                    Bounds bounds = meshRenderer.bounds;

                    var objData = new SpatialObjectData
                    {
                        id = anchor.Uuid.ToString(),
                        label = label,
                        center = bounds.center,
                        size = bounds.size,
                        rotation = anchor.transform.rotation
                    };

                    payload.objects.Add(objData);
                }
            }

            Debug.Log($"[RoomScanner] Extracted {payload.objects.Count} spatial objects. Sending to backend...");
            
            string json = JsonUtility.ToJson(payload);
            wsClient.SendEvent("spatial.room_geometry", json);
        }
    }
}
