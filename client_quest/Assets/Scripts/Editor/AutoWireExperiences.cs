using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Video;
using FoveAI.IPC;
using FoveAI.Avatar;
using FoveAI.UI;
using FoveAI.Creative;
using FoveAI.Games;
using FoveAI.Presence;
using FoveAI.Experiences;
using TMPro;

namespace FoveAI.Editor
{
    /// <summary>
    /// One-shot wirer: opens the existing FoveAI scene, attaches all 17 new
    /// experience/game/presence/creative/UI scripts to the right GameObjects,
    /// wires their [SerializeField] references, saves the scene.
    ///
    /// Menu: Spatial Machine / Wire All Experiences
    /// Batchmode:  AutoWireExperiences.WireAll()
    /// </summary>
    public static class AutoWireExperiences
    {
        private const string ScenePath = "Assets/Scenes/FoveAI.unity";

        [MenuItem("Spatial Machine/Wire All Experiences")]
        public static void WireAll()
        {
            Debug.Log("[AutoWire] Opening scene: " + ScenePath);
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);

            // ── Locate existing scene objects ──
            var root = GameObject.Find("SpatialMachineRoot");
            var wsObj = GameObject.Find("FoveAIWebSocketClient");
            var avatarContainer = GameObject.Find("AvatarContainer");
            var roomManager = GameObject.Find("RoomManager");
            var cameraRig = GameObject.Find("XR_CameraRig");
            var mainCam = GameObject.Find("Main Camera");
            var chatCanvas = GameObject.Find("ChatCanvas");

            if (root == null || wsObj == null || avatarContainer == null)
            {
                Debug.LogError("[AutoWire] Core scene objects missing! Expected SpatialMachineRoot, FoveAIWebSocketClient, AvatarContainer.");
                return;
            }

            var wsClient = wsObj.GetComponent<FoveAIWebSocketClient>();
            if (wsClient == null)
            {
                Debug.LogError("[AutoWire] FoveAIWebSocketClient component not found on FoveAIWebSocketClient GO.");
                return;
            }

            // Avatar transforms
            Transform aliceTransform = avatarContainer.transform;
            Transform aliceHead = mainCam != null ? mainCam.transform : aliceTransform;
            Animator aliceAnimator = avatarContainer.GetComponentInChildren<Animator>();
            CharacterController cc = avatarContainer.GetComponent<CharacterController>();
            AvatarBlendshapeDriver blendshapes = avatarContainer.GetComponent<AvatarBlendshapeDriver>();

            // ── 1. AmbientMusicPlayer (on root) ──
            var musicPlayer = root.GetComponent<AmbientMusicPlayer>();
            if (musicPlayer == null)
            {
                musicPlayer = root.AddComponent<AmbientMusicPlayer>();
                Debug.Log("[AutoWire] Added AmbientMusicPlayer to SpatialMachineRoot");
            }
            // musicPlayer only needs an AudioSource — add one if missing
            var musicSource = root.GetComponent<AudioSource>();
            if (musicSource == null)
            {
                musicSource = root.AddComponent<AudioSource>();
                musicSource.loop = true;
                musicSource.playOnAwake = false;
            }
            SetRef(musicPlayer, "musicSource", musicSource);

            // ── 2. VRGameEngine (on root) ──
            var gameEngine = root.GetComponent<VRGameEngine>();
            if (gameEngine == null)
            {
                gameEngine = root.AddComponent<VRGameEngine>();
                Debug.Log("[AutoWire] Added VRGameEngine to SpatialMachineRoot");
            }
            SetRef(gameEngine, "wsClient", wsClient);
            SetRef(gameEngine, "musicPlayer", musicPlayer);
            // Prefabs left null — VRGameEngine creates primitives at runtime if null

            // ── 3. ScenePresetManager (on root) ──
            var presetMgr = root.GetComponent<ScenePresetManager>();
            if (presetMgr == null)
            {
                presetMgr = root.AddComponent<ScenePresetManager>();
                Debug.Log("[AutoWire] Added ScenePresetManager to SpatialMachineRoot");
            }
            SetRef(presetMgr, "musicPlayer", musicPlayer);
            SetRef(presetMgr, "gameEngine", gameEngine);
            SetRef(presetMgr, "wsClient", wsClient);
            var mainLight = GameObject.Find("DirectionalLight");
            if (mainLight != null) SetRef(presetMgr, "mainLight", mainLight.GetComponent<Light>());
            // candleMat / lampMat / screenMat left null — presets handle gracefully

            // ── 4. VirtualGuestSystem (on root) ──
            var guestSystem = root.GetComponent<VirtualGuestSystem>();
            if (guestSystem == null)
            {
                guestSystem = root.AddComponent<VirtualGuestSystem>();
                Debug.Log("[AutoWire] Added VirtualGuestSystem to SpatialMachineRoot");
            }
            SetRef(guestSystem, "wsClient", wsClient);
            SetRef(guestSystem, "presetManager", presetMgr);
            SetRef(guestSystem, "musicPlayer", musicPlayer);
            SetRef(guestSystem, "gameEngine", gameEngine);

            // ── 5. SeasonalTheming (on root) ──
            var seasonal = root.GetComponent<SeasonalTheming>();
            if (seasonal == null)
            {
                seasonal = root.AddComponent<SeasonalTheming>();
                Debug.Log("[AutoWire] Added SeasonalTheming to SpatialMachineRoot");
            }
            SetRef(seasonal, "wsClient", wsClient);
            SetRef(seasonal, "musicPlayer", musicPlayer);
            SetRef(seasonal, "aliceTransform", aliceTransform);

            // ── 6. RoomPlastering (on RoomManager or root) ──
            var plasterHost = roomManager != null ? roomManager : root;
            var roomPlastering = plasterHost.GetComponent<RoomPlastering>();
            if (roomPlastering == null)
            {
                roomPlastering = plasterHost.AddComponent<RoomPlastering>();
                Debug.Log("[AutoWire] Added RoomPlastering to " + plasterHost.name);
            }
            SetRef(roomPlastering, "wsClient", wsClient);
            // avatarMovement wired below after we create it
            SetRef(roomPlastering, "playSpaceOrigin", root.transform);

            // ── 7. AvatarFreeMovement (on AvatarContainer) ──
            var avatarMovement = avatarContainer.GetComponent<AvatarFreeMovement>();
            if (avatarMovement == null)
            {
                avatarMovement = avatarContainer.AddComponent<AvatarFreeMovement>();
                Debug.Log("[AutoWire] Added AvatarFreeMovement to AvatarContainer");
            }
            SetRef(avatarMovement, "wsClient", wsClient);
            SetRef(avatarMovement, "aliceTransform", aliceTransform);
            SetRef(avatarMovement, "aliceHead", aliceHead);
            if (aliceAnimator != null) SetRef(avatarMovement, "aliceAnimator", aliceAnimator);
            if (cc != null) SetRef(avatarMovement, "characterController", cc);
            SetRef(avatarMovement, "roomPlastering", roomPlastering);

            // Now back-fill RoomPlastering → avatarMovement
            SetRef(roomPlastering, "avatarMovement", avatarMovement);

            // ── 8. VirtualTouring (on root) ──
            var touring = root.GetComponent<VirtualTouring>();
            if (touring == null)
            {
                touring = root.AddComponent<VirtualTouring>();
                Debug.Log("[AutoWire] Added VirtualTouring to SpatialMachineRoot");
            }
            SetRef(touring, "wsClient", wsClient);
            SetRef(touring, "musicPlayer", musicPlayer);
            SetRef(touring, "aliceTransform", aliceTransform);
            SetRef(touring, "aliceHead", aliceHead);

            // ── 9. CoOpGamingWithAlice (on root) ──
            var coOp = root.GetComponent<CoOpGamingWithAlice>();
            if (coOp == null)
            {
                coOp = root.AddComponent<CoOpGamingWithAlice>();
                Debug.Log("[AutoWire] Added CoOpGamingWithAlice to SpatialMachineRoot");
            }
            SetRef(coOp, "wsClient", wsClient);
            SetRef(coOp, "aliceTransform", aliceTransform);
            SetRef(coOp, "aliceHead", aliceHead);
            // aliceRightHand / aliceLeftHand — try to find controller transforms
            var rightHand = FindDeepChild(root.transform, "RightHand");
            var leftHand = FindDeepChild(root.transform, "LeftHand");
            if (rightHand != null) SetRef(coOp, "aliceRightHand", rightHand);
            if (leftHand != null) SetRef(coOp, "aliceLeftHand", leftHand);

            // ── 10. WebcamWindowGazing (on root) ──
            var webcam = root.GetComponent<WebcamWindowGazing>();
            if (webcam == null)
            {
                webcam = root.AddComponent<WebcamWindowGazing>();
                Debug.Log("[AutoWire] Added WebcamWindowGazing to SpatialMachineRoot");
            }
            SetRef(webcam, "wsClient", wsClient);
            SetRef(webcam, "aliceTransform", aliceTransform);
            SetRef(webcam, "aliceHead", aliceHead);

            // ── 11. CoPresenceMode (on root) ──
            var coPresence = root.GetComponent<CoPresenceMode>();
            if (coPresence == null)
            {
                coPresence = root.AddComponent<CoPresenceMode>();
                Debug.Log("[AutoWire] Added CoPresenceMode to SpatialMachineRoot");
            }
            SetRef(coPresence, "wsClient", wsClient);
            SetRef(coPresence, "aliceTransform", aliceTransform);
            SetRef(coPresence, "aliceHead", aliceHead);
            if (aliceAnimator != null) SetRef(coPresence, "aliceAnimator", aliceAnimator);
            SetRef(coPresence, "musicPlayer", musicPlayer);
            if (blendshapes != null) SetRef(coPresence, "blendshapes", blendshapes);

            // ── 12. GameSceneController (on root) ──
            var gameSceneCtrl = root.GetComponent<GameSceneController>();
            if (gameSceneCtrl == null)
            {
                gameSceneCtrl = root.AddComponent<GameSceneController>();
                Debug.Log("[AutoWire] Added GameSceneController to SpatialMachineRoot");
            }
            SetRef(gameSceneCtrl, "gameEngine", gameEngine);
            SetRef(gameSceneCtrl, "presetManager", presetMgr);
            SetRef(gameSceneCtrl, "wsClient", wsClient);
            SetRef(gameSceneCtrl, "coPresence", coPresence);

            // ── 13. DirectorEngine (on root) ──
            var director = root.GetComponent<DirectorEngine>();
            if (director == null)
            {
                director = root.AddComponent<DirectorEngine>();
                Debug.Log("[AutoWire] Added DirectorEngine to SpatialMachineRoot");
            }
            SetRef(director, "wsClient", wsClient);
            SetRef(director, "musicPlayer", musicPlayer);
            SetRef(director, "presetManager", presetMgr);
            SetRef(director, "seasonalTheming", seasonal);
            SetRef(director, "guestSystem", guestSystem);
            SetRef(director, "aliceTransform", aliceTransform);
            SetRef(director, "aliceHead", aliceHead);

            // ── 14. SceneManipulator (on root) ──
            var sceneManip = root.GetComponent<SceneManipulator>();
            if (sceneManip == null)
            {
                sceneManip = root.AddComponent<SceneManipulator>();
                Debug.Log("[AutoWire] Added SceneManipulator to SpatialMachineRoot");
            }

            // ── 15. CreativeWorkspace (on root) ──
            var creative = root.GetComponent<CreativeWorkspace>();
            if (creative == null)
            {
                creative = root.AddComponent<CreativeWorkspace>();
                Debug.Log("[AutoWire] Added CreativeWorkspace to SpatialMachineRoot");
            }
            SetRef(creative, "webSocketClient", wsClient);
            SetRef(creative, "musicPlayer", musicPlayer);
            SetRef(creative, "sceneManipulator", sceneManip);
            // codeDisplay / codeCanvas left null — CreativeWorkspace creates at runtime if null

            // ── 16. AppSettingsPanel (on root or ChatCanvas) ──
            var settingsPanel = root.GetComponent<AppSettingsPanel>();
            if (settingsPanel == null)
            {
                settingsPanel = root.AddComponent<AppSettingsPanel>();
                Debug.Log("[AutoWire] Added AppSettingsPanel to SpatialMachineRoot");
            }
            SetRef(settingsPanel, "wsClient", wsClient);
            var hud = root.GetComponent<UserHUD>();
            if (hud == null)
            {
                hud = root.AddComponent<UserHUD>();
                Debug.Log("[AutoWire] Added UserHUD to SpatialMachineRoot");
            }
            SetRef(settingsPanel, "hud", hud);
            SetRef(settingsPanel, "musicPlayer", musicPlayer);

            // ── 17. AdvancedSpatialPanel (on root) ──
            var advPanel = root.GetComponent<AdvancedSpatialPanel>();
            if (advPanel == null)
            {
                advPanel = root.AddComponent<AdvancedSpatialPanel>();
                Debug.Log("[AutoWire] Added AdvancedSpatialPanel to SpatialMachineRoot");
            }
            SetRef(advPanel, "webSocketClient", wsClient);

            // ── 18. GrabbablePanel (on root) ──
            var grabPanel = root.GetComponent<GrabbablePanel>();
            if (grabPanel == null)
            {
                grabPanel = root.AddComponent<GrabbablePanel>();
                Debug.Log("[AutoWire] Added GrabbablePanel to SpatialMachineRoot");
            }

            // ── 19. VRBrowserPanel (on root) ──
            var browserPanel = root.GetComponent<VRBrowserPanel>();
            if (browserPanel == null)
            {
                browserPanel = root.AddComponent<VRBrowserPanel>();
                Debug.Log("[AutoWire] Added VRBrowserPanel to SpatialMachineRoot");
            }
            // VRBrowserPanel has VideoPlayer / RawImage / AudioSource refs — it creates them at runtime if null

            // ── Save ──
            EditorSceneManager.SaveScene(scene, ScenePath);
            Debug.Log("[AutoWire] ✅ All 17+ experiences wired and scene saved to " + ScenePath);

            // Mark dirty so batchmode build picks it up
            EditorSceneManager.MarkSceneDirty(scene);
        }

        // ── Helpers ──

        private static void SetRef(Component comp, string fieldName, Object reference)
        {
            if (reference == null) return;
            var so = new SerializedObject(comp);
            var prop = so.FindProperty(fieldName);
            if (prop != null)
            {
                prop.objectReferenceValue = reference;
                so.ApplyModifiedProperties();
            }
            else
            {
                Debug.LogWarning($"[AutoWire] Field '{fieldName}' not found on {comp.GetType().Name}");
            }
        }

        private static Transform FindDeepChild(Transform parent, string name)
        {
            for (int i = 0; i < parent.childCount; i++)
            {
                var child = parent.GetChild(i);
                if (child.name == name) return child;
                var found = FindDeepChild(child, name);
                if (found != null) return found;
            }
            return null;
        }
    }
}
