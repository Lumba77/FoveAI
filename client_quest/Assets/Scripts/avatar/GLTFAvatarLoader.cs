using System;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using UniGLTF;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Loads a raw GLTF/GLB file at runtime and places it in the scene.
    /// Used for testing generic models instead of VRM.
    /// </summary>
    public class GLTFAvatarLoader : MonoBehaviour
    {
        [Header("GLTF File")]
        [Tooltip("Filename of the .gltf or .glb file inside StreamingAssets")]
        [SerializeField] private string gltfFileName = "gltf/1747e962a44a46f3b8919e45afe4d05d/scene.gltf";

        [Header("Spawn")]
        [SerializeField] private Vector3 spawnPosition = new Vector3(0f, 0f, 2f);
        [SerializeField] private Vector3 spawnRotation = Vector3.zero;

        /// <summary>
        /// Loaded avatar root GameObject (null until loaded).
        /// </summary>
        public GameObject Avatar { get; private set; }
        private RuntimeGltfInstance _instance;

        private async void Start()
        {
            if (!string.IsNullOrEmpty(gltfFileName))
            {
                string fullPath = Path.Combine(Application.streamingAssetsPath, gltfFileName);
                await LoadGltf(fullPath);
            }
        }

        public async Task<GameObject> LoadGltf(string filePath)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            string folderName = Path.GetFileNameWithoutExtension(Path.GetDirectoryName(filePath));
            if (string.IsNullOrEmpty(folderName)) folderName = "model";
            
            string persistentDir = Path.Combine(Application.persistentDataPath, "extracted_gltfs", folderName);
            if (!Directory.Exists(persistentDir)) Directory.CreateDirectory(persistentDir);
            
            string persistentPath = Path.Combine(persistentDir, Path.GetFileName(filePath));
            
            if (!File.Exists(persistentPath))
            {
                string gltfText = "";
                using (UnityEngine.Networking.UnityWebRequest uwr = UnityEngine.Networking.UnityWebRequest.Get(filePath))
                {
                    var op = uwr.SendWebRequest();
                    while (!op.isDone) await Task.Yield();

                    if (uwr.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                    {
                        gltfText = uwr.downloadHandler.text;
                        File.WriteAllText(persistentPath, gltfText);
                    }
                    else
                    {
                        Debug.LogError($"[GLTFAvatarLoader] Failed to read GLTF from APK: {uwr.error}");
                        return null;
                    }
                }

                if (filePath.EndsWith(".gltf", StringComparison.OrdinalIgnoreCase))
                {
                    var matches = System.Text.RegularExpressions.Regex.Matches(gltfText, "\"uri\"\\s*:\\s*\"([^\"]+)\"");
                    string baseUri = filePath.Substring(0, filePath.LastIndexOf('/'));
                    
                    foreach (System.Text.RegularExpressions.Match match in matches)
                    {
                        string uri = match.Groups[1].Value;
                        if (uri.StartsWith("data:")) continue;

                        string depUrl = baseUri + "/" + uri;
                        string depDest = Path.Combine(persistentDir, uri);
                        string depDestDir = Path.GetDirectoryName(depDest);
                        
                        if (!Directory.Exists(depDestDir)) Directory.CreateDirectory(depDestDir);

                        using (UnityEngine.Networking.UnityWebRequest depUwr = UnityEngine.Networking.UnityWebRequest.Get(depUrl))
                        {
                            var depOp = depUwr.SendWebRequest();
                            while (!depOp.isDone) await Task.Yield();
                            
                            if (depUwr.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                            {
                                File.WriteAllBytes(depDest, depUwr.downloadHandler.data);
                            }
                        }
                    }
                }
            }
            filePath = persistentPath;
#else
            if (!File.Exists(filePath))
            {
                Debug.LogError($"[GLTFAvatarLoader] File not found: {filePath}");
                return null;
            }
#endif

            try
            {
                // Load the GLTF instance using UniGLTF
                _instance = await GltfUtility.LoadAsync(filePath);
                if (_instance != null)
                {
                    // UniGLTF uses Root for the main gameobject
                    Avatar = _instance.Root;
                    _instance.ShowMeshes();
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[GLTFAvatarLoader] GLTF load failed: {ex.Message}");
            }

            if (Avatar == null)
            {
                Debug.LogWarning("[GLTFAvatarLoader] Could not load GLTF — falling back to placeholder.");
                Avatar = CreatePlaceholder();
            }

            Avatar.name = Path.GetFileNameWithoutExtension(filePath);
            
            // Find the main camera to spawn in front of it
            Camera mainCam = Camera.main;
            if (mainCam != null)
            {
                Vector3 forward = mainCam.transform.forward;
                forward.y = 0; // Keep it level on the floor
                forward.Normalize();
                
                Avatar.transform.position = mainCam.transform.position + (forward * 1.5f);
                Avatar.transform.position = new Vector3(Avatar.transform.position.x, 0f, Avatar.transform.position.z); // Snap to floor
                
                // Rotate to face the camera
                Avatar.transform.LookAt(new Vector3(mainCam.transform.position.x, Avatar.transform.position.y, mainCam.transform.position.z));
            }
            else
            {
                Avatar.transform.SetParent(transform, false);
                Avatar.transform.localPosition = spawnPosition;
                Avatar.transform.localEulerAngles = spawnRotation;
            }

            // Attach FoveAI drivers dynamically
            // For standard GLTFs, blendshapes won't map automatically, but we attach it safely.
            var blendshapeDriver = Avatar.AddComponent<FoveAI.Avatar.AvatarBlendshapeDriver>();
            var puppetDriver = Avatar.AddComponent<FoveAI.Avatar.AvatarPuppetDriver>();
            var speaker = Avatar.AddComponent<FoveAI.Audio.AvatarVoice>();
            
            // Add IK Controller for procedural head/neck gaze
            var ikController = Avatar.AddComponent<AvatarIKController>();

            // Find WebSocket IPC and hook up events
            var wsClient = UnityEngine.Object.FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            if (wsClient != null)
            {
                wsClient.OnEmotionReceived += blendshapeDriver.ApplyEmotion;
                wsClient.OnMotorActionReceived += puppetDriver.HandleMotorAction;
                Debug.Log("[GLTFAvatarLoader] Successfully wired GLTF Avatar to FoveAIWebSocketClient!");
            }
            else
            {
                Debug.LogWarning("[GLTFAvatarLoader] FoveAIWebSocketClient not found! Avatar will not receive backend animations.");
            }

            Debug.Log($"[GLTFAvatarLoader] Loaded GLTF avatar: {Avatar.name}");
            return Avatar;
        }

        private GameObject CreatePlaceholder()
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            go.name = "AvatarPlaceholder";
            Camera mainCam = Camera.main;
            if (mainCam != null)
            {
                Vector3 forward = mainCam.transform.forward;
                forward.y = 0;
                forward.Normalize();
                go.transform.position = mainCam.transform.position + (forward * 1.5f);
                go.transform.position = new Vector3(go.transform.position.x, 1f, go.transform.position.z);
            }
            go.transform.localScale = new Vector3(0.5f, 1f, 0.5f);
            return go;
        }
        
        private void OnDestroy()
        {
            if (_instance != null)
            {
                _instance.Dispose();
                _instance = null;
            }
        }
    }
}
