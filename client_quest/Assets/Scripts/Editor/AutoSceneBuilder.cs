#pragma warning disable CS0618
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.XR;
using FoveAI.IPC;
using FoveAI.Avatar;
using FoveAI.UI;

namespace FoveAI.Editor
{
    /// <summary>
    /// Companion scene builder for Quest 3 mixed reality passthrough.
    ///
    /// Builds a scene with:
    ///   • XR camera rig with passthrough (transparent background)
    ///   • VRM avatar (loaded at runtime, faces the user at 1.5m)
    ///   • Voice pipeline: STT (mic → text) + TTS (text → speech) + lip sync
    ///   • WebSocket client connecting to the FoveAI backend
    ///   • Emotion/gesture routing (avatar reacts to chat responses)
    ///   • Room scanning via OVRSceneManager → sends geometry to backend
    ///   • Room plastering: Quest camera frames → backend → stitched texture on walls
    ///   • Vision grabber: avatar can "see" through Quest cameras
    ///   • NavMesh over physical furniture for avatar navigation
    ///   • Dark chat panel (black bg, white text) toggled by left controller X button
    ///   • Settings overlay (WebSocket URL, voice, model, system prompt)
    /// </summary>
    public static class AutoSceneBuilder
    {
        private const string ScenePath = "Assets/Scenes/FoveAI.unity";

        [MenuItem("Spatial Machine/Build Scene %#b")]
        public static void BuildScene()
        {
            // --- Create the new scene FIRST so objects aren't destroyed by NewSceneMode.Single ---
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // --- Root ---
            var root = new GameObject("SpatialMachineRoot");

            // --- WebSocket Client ---
            var wsObj = new GameObject("FoveAIWebSocketClient");
            wsObj.transform.SetParent(root.transform, false);
            var wsClient = wsObj.AddComponent<FoveAIWebSocketClient>();

            // --- Standard OpenXR Camera Rig (passthrough via ARFoundation) ---
            var cameraRig = new GameObject("XR_CameraRig");
            cameraRig.transform.SetParent(root.transform, false);

            // ARSession is required for ARFoundation passthrough to work
            cameraRig.AddComponent<UnityEngine.XR.ARFoundation.ARSession>();

            var camObj = new GameObject("Main Camera");
            camObj.transform.SetParent(cameraRig.transform, false);
            Camera cam = camObj.AddComponent<Camera>();
            cam.tag = "MainCamera";

            // Transparent background so passthrough shows through
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0f, 0f, 0f, 0f);
            RenderSettings.skybox = null;

            // ARCameraBackground renders the Quest camera feed (passthrough) behind everything.
            // This is the OpenXR way to do passthrough (OVRManager conflicts with OpenXR).
            camObj.AddComponent<UnityEngine.XR.ARFoundation.ARCameraBackground>();
            camObj.AddComponent<UnityEngine.XR.ARFoundation.ARCameraManager>();

            // HMD head tracking
            camObj.AddComponent<FoveAI.Environment.HMDTracker>();
            ConfigureTrackedPoseDriver(camObj);

            // --- Room Scanning & Plastering (disabled at startup, enabled after app loads) ---
            // OVRSceneManager scans the physical room (walls, floor, furniture) via Quest Scene API.
            // RoomScanner extracts bounding boxes and sends geometry to the backend.
            // RoomPlasterClient downloads a stitched camera texture and applies it to room meshes.
            // These are DISABLED at startup to prevent blocking app initialization.
            // They will be enabled by a separate manager script after the first frame renders.
            var roomObj = new GameObject("RoomManager");
            roomObj.transform.SetParent(root.transform, false);

            // Add OVRSceneManager (Meta Quest Scene API for room geometry) — disabled at start
            var ovrSceneMgr = roomObj.AddComponent<OVRSceneManager>();
            ovrSceneMgr.enabled = false;

            // Add NavMeshSurface so the avatar can navigate around physical furniture — disabled at start
            // Use reflection to add the component by type name (Unity.AI.Navigation may not resolve at compile time)
            var navSurfaceType = System.Type.GetType("Unity.AI.Navigation.NavMeshSurface, Unity.AI.Navigation");
            if (navSurfaceType != null)
            {
                var navSurface = roomObj.AddComponent(navSurfaceType);
                // collectObjects = CollectObjects.Children (enum value 1 in Unity.AI.Navigation)
                var collectField = navSurfaceType.GetField("collectObjects");
                if (collectField != null)
                {
                    var collectEnumType = collectField.FieldType;
                    var childrenValue = System.Enum.Parse(collectEnumType, "Children");
                    collectField.SetValue(navSurface, childrenValue);
                }
                // Disable at start — RoomManagerEnabler will enable it after delay
                var enabledProp = navSurfaceType.GetProperty("enabled");
                if (enabledProp != null) enabledProp.SetValue(navSurface, false);
            }
            else
            {
                Debug.LogWarning("[AutoSceneBuilder] NavMeshSurface type not found — Unity.AI.Navigation package may be missing");
            }

            // RoomScanner sends geometry to backend via WebSocket — disabled at start
            var roomScanner = roomObj.AddComponent<FoveAI.Environment.RoomScanner>();
            roomScanner.enabled = false;
            var roomScannerSer = new SerializedObject(roomScanner);
            SetSerializedRef(roomScannerSer, "wsClient", wsClient);
            roomScannerSer.ApplyModifiedProperties();

            // RoomPlasterClient applies stitched camera texture to room walls — disabled at start
            var roomPlaster = roomObj.AddComponent<FoveAI.Environment.RoomPlasterClient>();
            roomPlaster.enabled = false;

            // RoomManagerEnabler enables all room components after a 3-second delay
            roomObj.AddComponent<FoveAI.Environment.RoomManagerEnabler>();

            // --- Vision Grabber (avatar can "see" through Quest cameras) ---
            var visionGrabber = wsObj.AddComponent<FoveAI.Senses.VisionGrabber>();
            var visSer = new SerializedObject(visionGrabber);
            SetSerializedRef(visSer, "wsClient", wsClient);
            SetSerializedRef(visSer, "userCamera", cam);
            visSer.ApplyModifiedProperties();

            // --- Voice pipeline: STT (your voice → text) + TTS (text → speech) ---
            var stt = wsObj.AddComponent<Lumax.Quest3Bridge.Quest3STTClient>();
            var tts = wsObj.AddComponent<Lumax.Quest3Bridge.Quest3TTSClient>();
            var cognitiveRouter = wsObj.AddComponent<Lumax.Quest3Bridge.CognitiveRouter>();

            // --- Avatar Container ---
            // The companion stands 1.5m in front of you, facing you
            var avatarContainer = new GameObject("AvatarContainer");
            avatarContainer.transform.SetParent(root.transform, false);
            avatarContainer.transform.position = new Vector3(0, 0, 1.5f);
            avatarContainer.transform.rotation = Quaternion.Euler(0f, 180f, 0f); // Face the user

            var avatarLoader = avatarContainer.AddComponent<VRMAvatarLoader>();
            var blendshapeDriver = avatarContainer.AddComponent<AvatarBlendshapeDriver>();
            var puppetDriver = avatarContainer.AddComponent<AvatarPuppetDriver>();
            var avatarMovement = avatarContainer.AddComponent<FoveAI.Avatar.AvatarMovement>();
            var vrmaAnimationLoader = avatarContainer.AddComponent<FoveAI.Avatar.VRMAAnimationLoader>();
            var animationBrain = avatarContainer.AddComponent<FoveAI.Avatar.AvatarAnimationBrain>();

            // Wire avatar movement to WebSocket
            var movementSer = new SerializedObject(avatarMovement);
            SetSerializedRef(movementSer, "wsClient", wsClient);
            movementSer.ApplyModifiedProperties();

            // Wire blendshape driver + animation brain into WebSocket client
            var wsSer = new SerializedObject(wsClient);
            var blendshapeProp = wsSer.FindProperty("avatarBlendshapeDriver");
            if (blendshapeProp != null)
            {
                blendshapeProp.objectReferenceValue = blendshapeDriver;
            }
            var brainProp = wsSer.FindProperty("animationBrain");
            if (brainProp != null)
            {
                brainProp.objectReferenceValue = animationBrain;
            }
            wsSer.ApplyModifiedProperties();

            // Wire avatar root to TTS (for lip sync) and CognitiveRouter (for gestures)
            var ttsSer = new SerializedObject(tts);
            var avatarRootPropTts = ttsSer.FindProperty("AvatarRoot");
            if (avatarRootPropTts != null)
            {
                avatarRootPropTts.objectReferenceValue = avatarContainer;
            }
            ttsSer.ApplyModifiedProperties();

            // Wire TTS/STT events to the AnimationBrain (conversation state machine)
            // OnTTSStart → SPEAKING, OnTTSEnd → IDLE
            // OnListeningStart → LISTENING, OnListeningEnd → IDLE
            var ttsEventBridge = avatarContainer.AddComponent<FoveAI.Avatar.TTSConversationBridge>();
            var ttsBridgeSer = new SerializedObject(ttsEventBridge);
            SetSerializedRef(ttsBridgeSer, "ttsClient", tts);
            SetSerializedRef(ttsBridgeSer, "sttClient", stt);
            SetSerializedRef(ttsBridgeSer, "brain", animationBrain);
            ttsBridgeSer.ApplyModifiedProperties();

            var routerSer = new SerializedObject(cognitiveRouter);
            var avatarRootPropRouter = routerSer.FindProperty("AvatarRoot");
            if (avatarRootPropRouter != null)
            {
                avatarRootPropRouter.objectReferenceValue = avatarContainer;
                routerSer.ApplyModifiedProperties();
            }

            // --- Lighting (so the avatar is lit in passthrough) ---
            var lightObj = new GameObject("DirectionalLight");
            lightObj.transform.SetParent(root.transform, false);
            var light = lightObj.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.0f;
            light.shadows = LightShadows.Soft;

            // --- Dark Chat Panel + Settings (toggled by left controller X button) ---
            GenerateChatCanvas();
            // Wire XRPanelToggle to the chat canvas
            var chatCanvas = GameObject.Find("ChatCanvas");
            if (chatCanvas != null)
            {
                var xrToggle = root.GetComponent<XRPanelToggle>();
                if (xrToggle == null)
                {
                    xrToggle = root.AddComponent<XRPanelToggle>();
                }
                var xrToggleSer = new SerializedObject(xrToggle);
                SetSerializedRef(xrToggleSer, "chatPanel", chatCanvas);
                SetSerializedRef(xrToggleSer, "xrCamera", cam);
                xrToggleSer.ApplyModifiedProperties();
                chatCanvas.SetActive(false); // Start hidden
            }

            // --- Debug Overlay (visible in headset, since ADB may not be available) ---
            var debugObj = new GameObject("QuestDebugOverlay");
            debugObj.transform.SetParent(root.transform, false);
            debugObj.AddComponent<FoveAI.DebugOverlay.QuestDebugOverlay>();

            // --- XR Rig Fixer (adds controllers + passthrough at runtime) ---
            var xrFixerObj = new GameObject("XRRigFixer");
            xrFixerObj.transform.SetParent(root.transform, false);
            xrFixerObj.AddComponent<FoveAI.XR.XRRigFixer>();

            // --- Save scene ---
            if (!AssetDatabase.IsValidFolder("Assets/Scenes"))
            {
                AssetDatabase.CreateFolder("Assets", "Scenes");
            }

            EditorSceneManager.SaveScene(scene, ScenePath);
            Debug.Log("[Spatial Machine] Scene built and saved to " + ScenePath);

            // --- Update Build Settings so this scene is the one that gets built into the APK ---
            var buildScenes = new EditorBuildSettingsScene[]
            {
                new EditorBuildSettingsScene(ScenePath, true)
            };
            EditorBuildSettings.scenes = buildScenes;
            Debug.Log("[Spatial Machine] Build Settings updated — APK will now build from " + ScenePath);
        }
        /// <summary>
        /// Attaches a UnityEngine.InputSystem.XR.TrackedPoseDriver to the supplied
        /// camera GameObject and wires its position/rotation inputs to the XR HMD
        /// center-eye pose via the OpenXR action layout.
        ///
        /// This is the canonical fix for the Quest "headlock" symptom: without a
        /// TrackedPoseDriver the camera transform is never updated from the HMD,
        /// so the rendered view stays frozen regardless of headset movement.
        /// </summary>
        /// <param name="cameraObj">GameObject that carries the Main Camera.</param>
        private static void ConfigureTrackedPoseDriver(GameObject cameraObj)
        {
            // Prefer the InputSystem-based TrackedPoseDriver (Unity 6 / OpenXR 1.16+).
            // Fall back to the legacy UnityEngine.SpatialTracking.TrackedPoseDriver
            // if the InputSystem variant is unavailable in the current project.
            Component driver = null;

            try
            {
                // AddComponent returns the concrete component type when the type is known
                // at compile time. We use the InputSystem variant directly because the
                // project depends on com.unity.inputsystem (see manifest.json).
                driver = cameraObj.AddComponent<UnityEngine.InputSystem.XR.TrackedPoseDriver>();
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning("[AutoSceneBuilder] InputSystem TrackedPoseDriver unavailable, falling back to legacy driver. " + ex.Message);
            }

            if (driver is UnityEngine.InputSystem.XR.TrackedPoseDriver inputSystemDriver)
            {
                // Bind position + rotation to the XR HMD center-eye OpenXR actions.
                // <XRHMD>/centerEyePosition and <XRHMD>/centerEyeRotation are the
                // canonical InputSystem layouts generated by the OpenXR backend.
                inputSystemDriver.positionInput =
                    new InputActionProperty(
                        new InputAction(
                            name: "XR HMD Position",
                            type: InputActionType.Value,
                            binding: "<XRHMD>/centerEyePosition",
                            interactions: string.Empty,
                            processors: string.Empty,
                            expectedControlType: "Vector3"));

                inputSystemDriver.rotationInput =
                    new InputActionProperty(
                        new InputAction(
                            name: "XR HMD Rotation",
                            type: InputActionType.Value,
                            binding: "<XRHMD>/centerEyeRotation",
                            interactions: string.Empty,
                            processors: string.Empty,
                            expectedControlType: "Quaternion"));

                // Tracking type: full 6-DOF (position + rotation) for Quest 3.
                inputSystemDriver.trackingType = UnityEngine.InputSystem.XR.TrackedPoseDriver.TrackingType.RotationAndPosition;

                // Update mode: update before rendering AND before the game logic update
                // to minimise latency and avoid jitter on Quest.
                inputSystemDriver.updateType = UnityEngine.InputSystem.XR.TrackedPoseDriver.UpdateType.UpdateAndBeforeRender;

                Debug.Log("[AutoSceneBuilder] InputSystem TrackedPoseDriver attached and bound to <XRHMD>/centerEyePosition|Rotation.");
            }
            else if (driver != null)
            {
                // Legacy fallback path — set via SerializedObject so we don't need a
                // hard reference to UnityEngine.SpatialTracking at compile time.
                var driverSer = new SerializedObject(driver);
                var posInputProp = driverSer.FindProperty("m_PositionInput");
                var rotInputProp = driverSer.FindProperty("m_RotationInput");
                var trackingTypeProp = driverSer.FindProperty("m_TrackingType");
                var updateTypeProp = driverSer.FindProperty("m_UpdateType");

                if (posInputProp != null)
                {
                    posInputProp.stringValue = "<XRHMD>/centerEyePosition";
                }
                if (rotInputProp != null)
                {
                    rotInputProp.stringValue = "<XRHMD>/centerEyeRotation";
                }
                if (trackingTypeProp != null)
                {
                    // RotationAndPosition = 0 in the legacy enum.
                    trackingTypeProp.enumValueIndex = 0;
                }
                if (updateTypeProp != null)
                {
                    // UpdateAndBeforeRender = 2 in the legacy enum.
                    updateTypeProp.enumValueIndex = 2;
                }
                driverSer.ApplyModifiedProperties();

                Debug.Log("[AutoSceneBuilder] Legacy TrackedPoseDriver attached and bound to <XRHMD>/centerEyePosition|Rotation.");
            }
            else
            {
                Debug.LogError("[AutoSceneBuilder] Failed to attach any TrackedPoseDriver. VR head tracking will not work.");
            }
        }


        private static void SetSerializedRef(SerializedObject so, string fieldName, Object reference)
        {
            var prop = so.FindProperty(fieldName);
            if (prop != null)
            {
                prop.objectReferenceValue = reference;
            }
            else
            {
                Debug.LogWarning($"[AutoSceneBuilder] Could not find serialized field: {fieldName}");
            }
        }

        /// <summary>
        [MenuItem("Spatial Machine/Generate XR Web Chat UI")]
        public static void GenerateChatCanvas()
        {
            var root = new GameObject("ChatCanvas");
            var canvas = root.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            var scaler = root.AddComponent<CanvasScaler>();
            scaler.dynamicPixelsPerUnit = 10;
            
            // Try to add XRI Raycaster for VR Rays, fallback to GraphicRaycaster
            var xriRaycasterType = System.Type.GetType("UnityEngine.XR.Interaction.Toolkit.UI.TrackedDeviceGraphicRaycaster, Unity.XR.Interaction.Toolkit");
            if (xriRaycasterType != null) {
                root.AddComponent(xriRaycasterType);
            } else {
                var ovrRaycasterType = System.Type.GetType("OVRRaycaster, Assembly-CSharp");
                if (ovrRaycasterType != null) root.AddComponent(ovrRaycasterType);
                else root.AddComponent<GraphicRaycaster>();
            }
            
            var rect = root.GetComponent<RectTransform>();
            rect.sizeDelta = new Vector2(800, 700);
            rect.localScale = new Vector3(0.002f, 0.002f, 0.002f);
            rect.position = new Vector3(0, 1.2f, 1.5f);

            // Background — dark/black panel
            var bgObj = new GameObject("Background");
            bgObj.transform.SetParent(root.transform, false);
            var bgImg = bgObj.AddComponent<Image>();
            bgImg.color = new Color(0.02f, 0.02f, 0.03f, 0.92f); // Near-black, slightly transparent
            var bgRect = bgObj.GetComponent<RectTransform>();
            bgRect.anchorMin = Vector2.zero; bgRect.anchorMax = Vector2.one;
            bgRect.sizeDelta = Vector2.zero;

            // Scroll View for Chat
            var scrollObj = new GameObject("Scroll View", typeof(RectTransform));
            scrollObj.transform.SetParent(root.transform, false);
            var scrollRect = scrollObj.AddComponent<ScrollRect>();
            var scrollRt = scrollObj.GetComponent<RectTransform>();
            scrollRt.anchorMin = new Vector2(0.05f, 0.3f);
            scrollRt.anchorMax = new Vector2(0.95f, 0.95f);
            scrollRt.sizeDelta = Vector2.zero;

            var viewportObj = new GameObject("Viewport", typeof(RectTransform));
            viewportObj.transform.SetParent(scrollObj.transform, false);
            var viewportMask = viewportObj.AddComponent<RectMask2D>();
            var viewportRt = viewportObj.GetComponent<RectTransform>();
            viewportRt.anchorMin = Vector2.zero; viewportRt.anchorMax = Vector2.one;
            viewportRt.sizeDelta = Vector2.zero;

            var contentObj = new GameObject("Content", typeof(RectTransform));
            contentObj.transform.SetParent(viewportObj.transform, false);
            var contentRt = contentObj.GetComponent<RectTransform>();
            contentRt.anchorMin = new Vector2(0, 1);
            contentRt.anchorMax = new Vector2(1, 1);
            contentRt.sizeDelta = new Vector2(0, 100);
            var contentLayout = contentObj.AddComponent<VerticalLayoutGroup>();
            contentLayout.childControlHeight = true;
            contentLayout.childForceExpandHeight = false;
            var contentFitter = contentObj.AddComponent<ContentSizeFitter>();
            contentFitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            var textObj = new GameObject("ChatText");
            textObj.transform.SetParent(contentObj.transform, false);
            var textComp = textObj.AddComponent<Text>();
            textComp.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            textComp.fontSize = 24;
            textComp.color = Color.white;
            textComp.supportRichText = true;
            var textFitter = textObj.AddComponent<ContentSizeFitter>();
            textFitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            scrollRect.viewport = viewportRt;
            scrollRect.content = contentRt;
            scrollRect.vertical = true;
            scrollRect.horizontal = false;

            // Helper to generate InputFields
            InputField CreateInput(string name, float yPos, string placeholderTxt) {
                var inputObj = new GameObject(name, typeof(RectTransform));
                inputObj.transform.SetParent(root.transform, false);
                var inputBg = inputObj.AddComponent<Image>();
                inputBg.color = new Color(0.08f, 0.08f, 0.1f, 1f); // Dark input field bg
                var inputRect = inputObj.GetComponent<RectTransform>();
                inputRect.anchorMin = new Vector2(0.05f, 0);
                inputRect.anchorMax = new Vector2(0.95f, 0);
                inputRect.pivot = new Vector2(0.5f, 0f); // Pivot at bottom so yPos pushes it up
                inputRect.sizeDelta = new Vector2(0, 45); // Height 45
                inputRect.anchoredPosition = new Vector2(0, yPos + 10); // Offset 10px from bottom

                var inputField = inputObj.AddComponent<InputField>();
                inputField.targetGraphic = inputBg; // Required for raycast clicks

                var txtObj = new GameObject("Text", typeof(RectTransform));
                txtObj.transform.SetParent(inputObj.transform, false);
                var txtComp = txtObj.AddComponent<Text>();
                txtComp.font = textComp.font;
                txtComp.fontSize = 20;
                txtComp.color = Color.white;
                txtComp.alignment = TextAnchor.MiddleLeft;
                var txtRect = txtObj.GetComponent<RectTransform>();
                txtRect.anchorMin = Vector2.zero; txtRect.anchorMax = Vector2.one;
                txtRect.sizeDelta = new Vector2(-20, -10); // Margins
                inputField.textComponent = txtComp;
                
                var phObj = new GameObject("Placeholder", typeof(RectTransform));
                phObj.transform.SetParent(inputObj.transform, false);
                var phComp = phObj.AddComponent<Text>();
                phComp.font = textComp.font;
                phComp.fontSize = 20;
                phComp.color = new Color(1, 1, 1, 0.5f);
                phComp.alignment = TextAnchor.MiddleLeft;
                phComp.text = placeholderTxt;
                var phRect = phObj.GetComponent<RectTransform>();
                phRect.anchorMin = Vector2.zero; phRect.anchorMax = Vector2.one;
                phRect.sizeDelta = new Vector2(-20, -10);
                inputField.placeholder = phComp;
                
                return inputField;
            }

            // Generate Settings Inputs stacked at the bottom
            var wsInput = CreateInput("WSUrlInput", 200, "WebSocket URL (ws://192.168.x.x:8403/ws)");
            var promptInput = CreateInput("PromptInput", 140, "System Prompt (e.g. You are a helpful AI)");
            var modelInput = CreateInput("ModelInput", 80, "Model (e.g. qwen4b)");
            var voiceInput = CreateInput("VoiceInput", 20, "Voice (e.g. af_heart)");

            // Manager
            var uiManager = root.AddComponent<SpatialUIManager>();
            var uiSer = new SerializedObject(uiManager);
            SetSerializedRef(uiSer, "chatText", textComp);
            SetSerializedRef(uiSer, "chatScrollRect", scrollRect);
            SetSerializedRef(uiSer, "wsUrlInputField", wsInput);
            SetSerializedRef(uiSer, "systemPromptInput", promptInput);
            SetSerializedRef(uiSer, "modelSelectInput", modelInput);
            SetSerializedRef(uiSer, "ttsVoiceInput", voiceInput);
            
            // Look for WebSocket
            var wsClient = UnityEngine.Object.FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            if (wsClient != null) {
                SetSerializedRef(uiSer, "webSocketClient", wsClient);
            }
            uiSer.ApplyModifiedProperties();

            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            Debug.Log("[Spatial Machine] Generated fully-wired Chat UI Canvas with InputFields.");
        }

        /// <summary>
        /// Adds the XRPanelToggle component to the existing scene's chat canvas.
        /// The chat panel will start HIDDEN and appear 2m in front of the user
        /// when they press the X button on the left Quest 3 controller (or Tab in Desktop mode).
        /// The avatar remains visible at start.
        /// </summary>
        [MenuItem("Spatial Machine/Add XR Panel Toggle")]
        public static void AddXRPanelToggle()
        {
            var chatCanvas = GameObject.Find("ChatCanvas");
            if (chatCanvas == null)
            {
                EditorUtility.DisplayDialog("Panel Not Found",
                    "No 'ChatCanvas' found in the current scene.\n" +
                    "Run 'Spatial Machine → Build Scene' first.", "OK");
                return;
            }

            // Find the main camera
            Camera cam = Camera.main;
            if (cam == null)
            {
                cam = UnityEngine.Object.FindAnyObjectByType<Camera>();
            }

            // Add or find XRPanelToggle
            var xrToggle = chatCanvas.GetComponent<XRPanelToggle>();
            if (xrToggle == null)
            {
                xrToggle = chatCanvas.AddComponent<XRPanelToggle>();
            }

            var xrToggleSer = new SerializedObject(xrToggle);
            SetSerializedRef(xrToggleSer, "chatPanel", chatCanvas);
            SetSerializedRef(xrToggleSer, "xrCamera", cam);
            xrToggleSer.ApplyModifiedProperties();

            // Hide the chat panel at start (XRPanelToggle also does this in Awake)
            chatCanvas.SetActive(false);

            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene());

            Debug.Log("[Spatial Machine] XRPanelToggle added. Panel starts hidden — press X button (Quest 3) or Tab (Desktop) to show it 2m in front of you.");
            EditorUtility.DisplayDialog("XR Panel Toggle Added",
                "XRPanelToggle component has been added to the ChatCanvas.\n\n" +
                "• Chat panel starts HIDDEN\n" +
                "• Press X button on left Quest 3 controller to toggle\n" +
                "• Press Tab in Desktop mode to toggle\n" +
                "• Panel appears 2m in front of the user at eye level\n" +
                "• Avatar remains visible at start\n\n" +
                "Scene saved.", "OK");
        }

        /// <summary>
        /// Adds a quit button (✕) to the top-right of the existing chat panel.
        /// The button quits the app on Quest 3 or stops play mode in the Editor.
        /// </summary>
        [MenuItem("Spatial Machine/Add Quit Button")]
        public static void AddQuitButton()
        {
            var chatBg = GameObject.Find("ChatCanvas/ChatBackground");
            if (chatBg == null)
            {
                EditorUtility.DisplayDialog("Panel Not Found",
                    "No 'ChatCanvas/ChatBackground' found in the current scene.\n" +
                    "Run 'Spatial Machine → Build Scene' first.", "OK");
                return;
            }

            // Check if quit button already exists
            var existingQuit = GameObject.Find("ChatCanvas/ChatBackground/QuitButton");
            if (existingQuit != null)
            {
                EditorUtility.DisplayDialog("Already Exists",
                    "QuitButton already exists in the scene.", "OK");
                return;
            }

            // Quit button (✕) — top-right corner, quits the app
            var quitBtnObj = new GameObject("QuitButton");
            quitBtnObj.transform.SetParent(chatBg.transform, false);
            var quitBtnImage = quitBtnObj.AddComponent<Image>();
            quitBtnImage.color = new Color(0.6f, 0.1f, 0.1f, 1f); // red
            var quitBtnRect = quitBtnObj.GetComponent<RectTransform>();
            quitBtnRect.anchorMin = new Vector2(0.9f, 0.88f);
            quitBtnRect.anchorMax = new Vector2(1f, 1f);
            quitBtnRect.offsetMin = new Vector2(-5, -5);
            quitBtnRect.offsetMax = new Vector2(-10, -5);
            var quitButton = quitBtnObj.AddComponent<Button>();
            quitButton.targetGraphic = quitBtnImage;
            var quitScript = quitBtnObj.AddComponent<QuitButton>();

            var quitBtnTextObj = new GameObject("Text");
            quitBtnTextObj.transform.SetParent(quitBtnObj.transform, false);
            var quitBtnText = quitBtnTextObj.AddComponent<Text>();
            quitBtnText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            quitBtnText.fontSize = 22;
            quitBtnText.color = Color.white;
            quitBtnText.alignment = TextAnchor.MiddleCenter;
            quitBtnText.text = "✕";
            var quitBtnTextRect = quitBtnTextObj.GetComponent<RectTransform>();
            quitBtnTextRect.anchorMin = Vector2.zero;
            quitBtnTextRect.anchorMax = Vector2.one;
            quitBtnTextRect.offsetMin = Vector2.zero;
            quitBtnTextRect.offsetMax = Vector2.zero;

            // Wire quit button click event
            var quitBtnEvent = new Button.ButtonClickedEvent();
            quitBtnEvent.AddListener(quitScript.QuitApp);
            quitButton.onClick = quitBtnEvent;

            // Shift settings button left if it exists
            var settingsBtn = GameObject.Find("ChatCanvas/ChatBackground/SettingsButton");
            if (settingsBtn != null)
            {
                var settingsRect = settingsBtn.GetComponent<RectTransform>();
                if (settingsRect != null)
                {
                    settingsRect.anchorMin = new Vector2(0.8f, 0.88f);
                    settingsRect.anchorMax = new Vector2(0.9f, 1f);
                    settingsRect.offsetMin = new Vector2(-5, -5);
                    settingsRect.offsetMax = new Vector2(-5, -5);
                }
            }

            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene());

            Debug.Log("[Spatial Machine] Quit button added to top-right of chat panel.");
            EditorUtility.DisplayDialog("Quit Button Added",
                "A red ✕ quit button has been added to the top-right of the chat panel.\n\n" +
                "• Click it to quit the app (Quest 3) or stop play mode (Editor)\n" +
                "• Settings button (⚙) shifted left to make room\n\n" +
                "Scene saved.", "OK");
        }

        /// <summary>
        /// Adds the BackendLauncher component to the existing scene.
        /// The backend server (Python) will start automatically when the scene plays.
        /// </summary>
        [MenuItem("Spatial Machine/Add Backend Launcher")]
        public static void AddBackendLauncher()
        {
            var root = GameObject.Find("SpatialMachineRoot");
            if (root == null)
            {
                root = new GameObject("SpatialMachineRoot");
            }

            // Check if BackendLauncher already exists
            var existing = GameObject.Find("SpatialMachineRoot/BackendLauncher");
            if (existing != null)
            {
                EditorUtility.DisplayDialog("Already Exists",
                    "BackendLauncher already exists in the scene.", "OK");
                return;
            }

            var backendObj = new GameObject("BackendLauncher");
            backendObj.transform.SetParent(root.transform, false);
            backendObj.AddComponent<BackendLauncher>();

            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene());

            Debug.Log("[Spatial Machine] BackendLauncher added — Python server starts at scene play.");
            EditorUtility.DisplayDialog("Backend Launcher Added",
                "BackendLauncher has been added to the scene.\n\n" +
                "• Python backend server starts automatically on scene play\n" +
                "• Server is killed on application quit\n" +
                "• Auto-detects Python from common locations\n" +
                "• Set pythonPath in inspector if auto-detect fails\n\n" +
                "Scene saved.", "OK");
        }

        [MenuItem("Spatial Machine/Connect to Backend")]
        public static void ConnectToBackend()
        {
            Debug.Log("[Spatial Machine] FoveAIWebSocketClient auto-connects on Start. Select the client GameObject to configure URL.");
            Selection.activeGameObject = GameObject.Find("SpatialMachineRoot/FoveAIWebSocketClient");
        }

        [MenuItem("Spatial Machine/About")]
        public static void About()
        {
            EditorUtility.DisplayDialog(
                "Spatial Machine — XRLF 3.0 Quest Builder",
                "XRLF 3.0 Spatial Machine Scene Builder v1.4\n\n" +
                "Menu Items:\n" +
                "• Build Scene (Ctrl+Shift+B)\n" +
                "• Add XR Panel Toggle — adds X-button toggle to existing scene\n" +
                "• Add Quit Button — adds ✕ quit button to existing scene\n" +
                "• Add Backend Launcher — auto-starts Python server at scene play\n" +
                "• Connect to Backend\n" +
                "• About\n\n" +
                "Scene Contents:\n" +
                "• XR Origin (Quest 3 passthrough)\n" +
                "• Alicechan.vrm avatar (visible at start)\n" +
                "• Chat panel (HIDDEN at start, press X button to show 2m in front)\n" +
                "• In-scene settings overlay panel\n" +
                "• Meta Quest 3 system keyboard support\n" +
                "• XRPanelToggle: X button (Quest 3) / Tab (Desktop)\n\n" +
                "Namespace: FoveAI.Editor",
                "OK");
        }
    }
}