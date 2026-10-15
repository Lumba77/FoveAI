using System;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using UnityEngine;
using VRM;
using UniGLTF;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Loads a VRM avatar at runtime and places it in the scene.
    /// Default companion model: Alicechan.vrm (XRLF 3.0 Spatial Machine).
    /// Drop a .vrm file into StreamingAssets and assign the filename,
    /// or call LoadVrm(path) from another script.
    /// </summary>
    public class VRMAvatarLoader : MonoBehaviour
    {
        [Header("VRM File")]
        [Header("VRM File")]
        [Tooltip("Filename of the .vrm file inside StreamingAssets (e.g. \"Alicechan.vrm\", \"SchoolUniform.vrm\")")]
        [SerializeField] private string vrmFileName = "Alicechan.vrm";

        /// <summary>
        /// Optional pre-imported VRM prefab. When set, the model is instantiated from
        /// this prefab instead of parsing StreamingAssets at runtime.
        ///
        /// Why: UniVRM converts .vrm into a prefab at import time, so baking the model
        /// into the scene means Jen is a real object — visible in the editor, renderable
        /// headlessly, and instantiable without an async file read. Everything else
        /// (TposeWarningSystem, SoftModuleSystem) still reads Avatar, so this loader
        /// stays the single owner and nothing else needs to know.
        /// </summary>
        [Tooltip("Pre-imported VRM prefab. Wins over the StreamingAssets file when set.")]
        [SerializeField] private GameObject preImportedPrefab;

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
            // Ensure ConfigLoader has finished loading AppConfig.json (using UnityWebRequest on Android)
            await FoveAI.Config.ConfigLoader.LoadConfigAsync();
            var settings = FoveAI.Config.ConfigLoader.Settings;
            if (settings != null && !string.IsNullOrEmpty(settings.avatarModel))
            {
                vrmFileName = settings.avatarModel;
            }

            if (!string.IsNullOrEmpty(vrmFileName))
            {
                if (!await TryLoadVrm(vrmFileName))
                {
                    // Primary model failed — try vibrant fallbacks before legacy model
                    Debug.LogWarning($"[VRMAvatarLoader] Primary VRM '{vrmFileName}' failed. Trying fallbacks...");
                    var fallbacks = new[] { "Alicechan.vrm", "SchoolUniform.vrm", "avatar.vrm", "Large_pupils.vrm" };
                    foreach (var fallback in fallbacks)
                    {
                        if (fallback == vrmFileName) continue;
                        if (await TryLoadVrm(fallback)) break;
                    }
                }
            }
        }

        private string LoadAvatarConfigName()
        {
            try
            {
                string configPath = Path.Combine(Application.streamingAssetsPath, "AppConfig.json");
                if (File.Exists(configPath))
                {
                    string json = File.ReadAllText(configPath);
                    int idx = json.IndexOf("\"avatarModel\"");
                    if (idx >= 0)
                    {
                        int colon = json.IndexOf(':', idx);
                        int firstQuote = json.IndexOf('\"', colon + 1);
                        int secondQuote = json.IndexOf('\"', firstQuote + 1);
                        if (firstQuote >= 0 && secondQuote > firstQuote)
                        {
                            return json.Substring(firstQuote + 1, secondQuote - firstQuote - 1);
                        }
                    }
                }
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[VRMAvatarLoader] Could not read avatarModel from AppConfig.json: {e.Message}");
            }
            return null;
        }

        /// <summary>
        /// Switch to a new avatar model at runtime.
        /// </summary>
        public async Task<bool> SwitchAvatar(string newModelName)
        {
            if (string.IsNullOrEmpty(newModelName)) return false;

            if (_instance != null)
            {
                Destroy(_instance.gameObject);
                _instance = null;
                Avatar = null;
            }

            vrmFileName = newModelName;
            return await TryLoadVrm(newModelName);
        }

        private async Task<bool> TryLoadVrm(string fileName)
        {
            string fullPath = Path.Combine(Application.streamingAssetsPath, fileName);
#if UNITY_ANDROID && !UNITY_EDITOR
            // Android streaming assets are inside the APK/JAR; copy to persistentDataPath first.
            string persistentPath = Path.Combine(Application.persistentDataPath, fileName);
            if (!File.Exists(persistentPath) || new FileInfo(persistentPath).Length < 1000)
            {
                if (File.Exists(persistentPath)) File.Delete(persistentPath);
                using (UnityEngine.Networking.UnityWebRequest uwr = UnityEngine.Networking.UnityWebRequest.Get(fullPath))
                {
                    var operation = uwr.SendWebRequest();
                    while (!operation.isDone) await Task.Yield();

                    if (uwr.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                    {
                        File.WriteAllBytes(persistentPath, uwr.downloadHandler.data);
                        Debug.Log($"[VRMAvatarLoader] Copied {fileName} to persistentDataPath ({uwr.downloadHandler.data.Length} bytes)");
                    }
                    else
                    {
                        Debug.LogError($"[VRMAvatarLoader] Failed to copy VRM from streamingAssets: {uwr.error}");
                        return false;
                    }
                }
            }
            fullPath = persistentPath;
#endif
            var result = await LoadVrm(fullPath);
            return result != null;
        }

        /// <summary>
        /// Load a VRM file from an absolute path and instantiate it.
        /// Uses VrmUtility.LoadBytesAsync (UniVRM 0.131.1).
        /// </summary>
        public async Task<GameObject> LoadVrm(string filePath)
        {
            byte[] bytes = null;

#if UNITY_ANDROID && !UNITY_EDITOR
            // If the file has been copied to a normal filesystem path (persistentDataPath),
            // read it directly. Otherwise, use UnityWebRequest for jar:/asset paths.
            if (File.Exists(filePath))
            {
                if (new FileInfo(filePath).Length == 0)
                {
                    Debug.LogError($"[VRMAvatarLoader] File is empty: {filePath}");
                    return CreatePlaceholder();
                }
                bytes = File.ReadAllBytes(filePath);
            }
            else
            {
                using (UnityEngine.Networking.UnityWebRequest uwr = UnityEngine.Networking.UnityWebRequest.Get(filePath))
                {
                    var operation = uwr.SendWebRequest();
                    while (!operation.isDone) await Task.Yield();

                    if (uwr.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                        bytes = uwr.downloadHandler.data;
                    else
                    {
                        Debug.LogError($"[VRMAvatarLoader] UnityWebRequest failed to load VRM from APK: {uwr.error} at path: {filePath}");
                        return CreatePlaceholder();
                    }
                }
            }
#else
            if (!File.Exists(filePath))
            {
                Debug.LogError($"[VRMAvatarLoader] File not found: {filePath}");
                return CreatePlaceholder();
            }
            bytes = File.ReadAllBytes(filePath);
#endif

            if (bytes == null || bytes.Length == 0)
            {
                Debug.LogError("[VRMAvatarLoader] Loaded zero bytes.");
                return CreatePlaceholder();
            }

            // Use RuntimeOnlyAwaitCaller so Unity's main thread isn't blocked.
            var awaitCaller = new RuntimeOnlyAwaitCaller();

            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[VRMAvatarLoader] Loading VRM: {filePath} ({bytes.Length} bytes)");

            try
            {
                _instance = await VrmUtility.LoadBytesAsync(
                    filePath, bytes, awaitCaller,
                    materialGeneratorCallback: MaterialGenerator,
                    loadAnimation: true);
                FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[VRMAvatarLoader] VrmUtility.LoadBytesAsync SUCCESS");
            }
            catch (Exception ex)
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.LogError($"[VRMAvatarLoader] LoadBytesAsync FAILED: {ex.Message}");
                Debug.LogError($"[VRMAvatarLoader] VrmUtility.LoadBytesAsync FAILED: {ex.Message}\n{ex.StackTrace}");
            }

            if (_instance == null)
            {
                FoveAI.DebugOverlay.QuestDebugOverlay.LogError("[VRMAvatarLoader] _instance is null — VRM corrupt or shaders missing");
                Debug.LogError("[VRMAvatarLoader] _instance is null after load — VRM file may be corrupt or shaders missing. Creating placeholder.");
                return CreatePlaceholder();
            }

            Avatar = _instance.Root;
            _instance.EnableUpdateWhenOffscreen();
            _instance.ShowMeshes();

            Avatar.name = Path.GetFileNameWithoutExtension(filePath);
            Avatar.transform.SetParent(transform, true);
            // Scale avatar to natural VRM proportions (1.0 = ~1.6m tall for standard VRM)
            Avatar.transform.localScale = Vector3.one;

            // 2.0m in front of the user, facing them
            Camera mainCam = Camera.main;
            if (mainCam == null) mainCam = FindAnyObjectByType<Camera>();
            if (mainCam != null)
            {
                Vector3 forward = mainCam.transform.forward;
                forward.y = 0;
                if (forward.sqrMagnitude < 0.01f) forward = Vector3.forward;
                forward.Normalize();
                Avatar.transform.position = mainCam.transform.position + forward * 2.0f;
                Avatar.transform.position = new Vector3(Avatar.transform.position.x, 0f, Avatar.transform.position.z);
                Vector3 lookTarget = new Vector3(mainCam.transform.position.x, Avatar.transform.position.y, mainCam.transform.position.z);
                if ((lookTarget - Avatar.transform.position).sqrMagnitude > 0.01f)
                {
                    Avatar.transform.LookAt(lookTarget);
                }

                // ── Floor correction: measure avatar bounds and lift so feet touch the floor ──
                // VRM models have their origin at the hips, so y=0 puts legs underground.
                // Wait several frames for skinned mesh bounds to settle after scale change.
                for (int i = 0; i < 5; i++) await Task.Yield();
                var renderers = Avatar.GetComponentsInChildren<SkinnedMeshRenderer>();
                if (renderers.Length > 0)
                {
                    Bounds bounds = renderers[0].bounds;
                    foreach (var r in renderers)
                        bounds.Encapsulate(r.bounds);
                    float footY = bounds.min.y; // lowest point of the avatar in world space
                    if (footY < 0f)
                    {
                        Avatar.transform.position += new Vector3(0f, -footY + 0.01f, 0f);
                        FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[VRMAvatarLoader] Floor correction: lifted by {-footY + 0.01f:F3}m (feet were at {footY:F3})");
                    }
                }

                FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[VRMAvatarLoader] Avatar positioned at {Avatar.transform.position}, scale 1.0, facing camera");
            }
            else
            {
                Avatar.transform.SetParent(transform, false);
                Avatar.transform.localPosition = spawnPosition;
                Avatar.transform.localEulerAngles = spawnRotation;
            }

            // Attach FoveAI drivers
            var containerBlendshape = GetComponent<FoveAI.Avatar.AvatarBlendshapeDriver>();
            var containerPuppet = GetComponent<FoveAI.Avatar.AvatarPuppetDriver>();
            var containerVrma = GetComponent<FoveAI.Avatar.VRMAAnimationLoader>();
            var containerBrain = GetComponent<FoveAI.Avatar.AvatarAnimationBrain>();
            if (containerBlendshape != null) containerBlendshape.enabled = false;
            if (containerPuppet != null) containerPuppet.enabled = false;
            if (containerVrma != null) containerVrma.enabled = false;
            if (containerBrain != null) containerBrain.enabled = false;

            var blendshapeDriver = Avatar.GetComponent<FoveAI.Avatar.AvatarBlendshapeDriver>() ?? Avatar.AddComponent<FoveAI.Avatar.AvatarBlendshapeDriver>();
            var puppetDriver = Avatar.GetComponent<FoveAI.Avatar.AvatarPuppetDriver>() ?? Avatar.AddComponent<FoveAI.Avatar.AvatarPuppetDriver>();
            var vrmaLoader = Avatar.GetComponent<FoveAI.Avatar.VRMAAnimationLoader>() ?? Avatar.AddComponent<FoveAI.Avatar.VRMAAnimationLoader>();
            var animationBrain = Avatar.GetComponent<FoveAI.Avatar.AvatarAnimationBrain>() ?? Avatar.AddComponent<FoveAI.Avatar.AvatarAnimationBrain>();
            var groundClamp = Avatar.GetComponent<FoveAI.Environment.QuestGroundClamp>() ?? Avatar.AddComponent<FoveAI.Environment.QuestGroundClamp>();
            var voice = Avatar.GetComponent<FoveAI.Audio.AvatarVoice>() ?? Avatar.AddComponent<FoveAI.Audio.AvatarVoice>();
            var navAgent = Avatar.GetComponent<UnityEngine.AI.NavMeshAgent>() ?? Avatar.AddComponent<UnityEngine.AI.NavMeshAgent>();
            var movement = Avatar.GetComponent<FoveAI.Avatar.AvatarMovement>() ?? Avatar.AddComponent<FoveAI.Avatar.AvatarMovement>();

            // ── Ensure Animator has a humanoid Avatar for VRMA muscle-space retargeting ──
            // Without this, VRMA body animations silently fail — only IK/blendshapes work.
            var animator = Avatar.GetComponentInChildren<Animator>();
            if (animator != null && animator.avatar == null)
            {
                Debug.LogWarning("[VRMAvatarLoader] Animator has no humanoid Avatar — VRMA body animations will not play");
                FoveAI.DebugOverlay.QuestDebugOverlay.Log("[VRMAvatarLoader] WARNING: No humanoid Avatar on Animator — body animations disabled");
            }
            if (animator != null)
            {
                animator.runtimeAnimatorController = null; // Clear any controller — PlayableGraph drives directly
                FoveAI.DebugOverlay.QuestDebugOverlay.Log($"[VRMAvatarLoader] Animator ready: avatar={(animator.avatar != null ? "yes" : "NO")}, human={(animator.isHuman ? "yes" : "no")}");
            }

            // ── Mount Avatar Eyes (Head Camera) ──────────────────────
            Transform headBone = animator != null && animator.isHuman ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
            if (headBone == null) headBone = Avatar.transform.Find("Root/J_Bip_C_Hips/J_Bip_C_Spine/J_Bip_C_Chest/J_Bip_C_UpperChest/J_Bip_C_Neck/J_Bip_C_Head");

            Camera avatarCam = null;
            if (headBone != null)
            {
                var camObj = new GameObject("AvatarEyesCamera");
                camObj.transform.SetParent(headBone, false);
                camObj.transform.localPosition = new Vector3(0f, 0.08f, 0.12f); // Centered between eyes, pointing forward
                camObj.transform.localRotation = Quaternion.identity;
                avatarCam = camObj.AddComponent<Camera>();
                avatarCam.fieldOfView = 65f;
                avatarCam.nearClipPlane = 0.05f;
                avatarCam.farClipPlane = 50f;
                avatarCam.enabled = false; // Enabled on demand during snapshot capture
                Debug.Log("[VRMAvatarLoader] AvatarEyesCamera mounted on Alice's head bone.");
            }

            // Wire to VisionGrabber
            var visionGrabber = UnityEngine.Object.FindAnyObjectByType<FoveAI.Senses.VisionGrabber>();
            if (visionGrabber == null && Camera.main != null)
            {
                visionGrabber = Camera.main.transform.root.gameObject.AddComponent<FoveAI.Senses.VisionGrabber>();
            }
            if (visionGrabber != null)
            {
                if (avatarCam != null) visionGrabber.avatarCamera = avatarCam;
                visionGrabber.userCamera = Camera.main;
            }

            // Wire to Central WebSocket Client
            var wsClient = UnityEngine.Object.FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            if (wsClient != null)
            {
                wsClient.BindAvatar(blendshapeDriver, animationBrain);

                // Chat text is handled by SpatialUIManager (UI) and CognitiveRouter (TTS)
                // Don't double-subscribe here — that causes duplicate messages and double TTS

                // Wire emotion to VRMA animations and facial blendshapes
                wsClient.OnEmotionReceived += (emotion, intensity) =>
                {
                    if (vrmaLoader != null) vrmaLoader.PlayAnimation(emotion);
                    if (blendshapeDriver != null) blendshapeDriver.ApplyEmotion(emotion, intensity);
                };

                // Wire motor actions to locomotion/gestures
                wsClient.OnMotorActionReceived += puppetDriver.HandleMotorAction;

                Debug.Log("[VRMAvatarLoader] Fully wired Avatar, Voice, VRMA, Blendshapes, and UI to FoveAIWebSocketClient.");
            }
            else
            {
                Debug.LogWarning("[VRMAvatarLoader] FoveAIWebSocketClient not found. Avatar will not receive backend animations.");
            }

            var vad = UnityEngine.Object.FindAnyObjectByType<FoveAI.Audio.QuestMicrophoneVAD>();
            if (vad != null && wsClient != null)
            {
                vad.webSocketClient = wsClient;
            }

            var ttsClient = UnityEngine.Object.FindAnyObjectByType<Lumax.Quest3Bridge.Quest3TTSClient>();
            if (ttsClient != null) ttsClient.AvatarRoot = Avatar;

            var cognitiveRouter = UnityEngine.Object.FindAnyObjectByType<Lumax.Quest3Bridge.CognitiveRouter>();
            if (cognitiveRouter != null) cognitiveRouter.SetAvatarRoot(Avatar);

            var conversationBridge = UnityEngine.Object.FindAnyObjectByType<FoveAI.Avatar.TTSConversationBridge>();
            if (conversationBridge != null) conversationBridge.SetBrain(animationBrain);

            FoveAI.DebugOverlay.QuestDebugOverlay.Log("[VRMAvatarLoader] Animation and conversation drivers ready");
            Debug.Log($"[VRMAvatarLoader] Loaded VRM avatar: {Avatar.name}");
            return Avatar;
        }

        /// <summary>
        /// Material generator callback — tries MToon 1.0 if available, falls back to URP/Standard.
        /// </summary>
        private static IMaterialDescriptorGenerator MaterialGenerator(VRM.glTF_VRM_extensions vrm)
        {
            // BuiltInVrmMToonMaterialImporter handles MToon on Built-in RP;
            // UrpVrmMaterialDescriptorGenerator is used for URP.
            // If neither applies, VRMImporterContext falls back to standard materials.
            try
            {
                var urpType = System.Type.GetType("VRM.UrpVrmMaterialDescriptorGenerator, VRM");
                if (urpType != null)
                    return (IMaterialDescriptorGenerator)Activator.CreateInstance(urpType, vrm);
            }
            catch { }
            return new VRM.BuiltInVrmMaterialDescriptorGenerator(vrm);
        }

        /// <summary>
        /// Create a simple placeholder capsule when VRM fails.
        /// </summary>
        private GameObject CreatePlaceholder()
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            go.name = "AvatarPlaceholder";
            Camera mainCam = Camera.main;
            if (mainCam == null) mainCam = FindAnyObjectByType<Camera>();
            if (mainCam != null)
            {
                Vector3 forward = mainCam.transform.forward;
                forward.y = 0;
                if (forward.sqrMagnitude < 0.01f) forward = Vector3.forward;
                forward.Normalize();
                go.transform.position = mainCam.transform.position + forward * 1.5f;
                go.transform.position = new Vector3(go.transform.position.x, 1f, go.transform.position.z);
            }
            go.transform.localScale = new Vector3(0.5f, 1.0f, 0.5f);
            var renderer = go.GetComponent<MeshRenderer>();
            if (renderer != null) renderer.material.color = new Color(0.7f, 0.6f, 0.9f, 1f);
            Avatar = go;
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
