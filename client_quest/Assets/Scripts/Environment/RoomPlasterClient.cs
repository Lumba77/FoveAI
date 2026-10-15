using UnityEngine;
using UnityEngine.Networking;
#pragma warning disable CS0618
using System.Collections;
using System.Collections.Generic;

namespace FoveAI.Environment
{
    [RequireComponent(typeof(OVRSceneManager))]
    public class RoomPlasterClient : MonoBehaviour
    {
        [Header("Backend Settings")]
        public string textureEndpoint = "http://192.168.8.109:8405/api/environment/plaster_texture"; // Overridden in Start
        public float refreshInterval = 5f;

        [Header("Materials")]
        public Material basePlasterMaterial; // Use Unlit/Texture

        [Header("Placeholder Room")]
        [Tooltip("Show a room-scale textured cube when no OVR scene anchors exist (room never scanned or deleted).")]
        public bool enablePlaceholderRoom = true;
        [Tooltip("Distance from the player to each placeholder wall (meters).")]
        public float placeholderRadius = 2.4f;
        [Tooltip("Placeholder wall quad size (meters).")]
        public float placeholderSize = 5f;
        [Tooltip("Seconds to wait for a room scan before deciding none exists.")]
        public float anchorGraceSeconds = 15f;
        [Tooltip("How often to re-check for scene anchors (seconds) — catches deleted rooms.")]
        public float anchorCheckInterval = 8f;
        [Tooltip("How long the room-scan notice stays visible (seconds).")]
        public float noticeDuration = 45f;

        private OVRSceneManager sceneManager;
        private Dictionary<string, Texture2D> directionTextures = new Dictionary<string, Texture2D>();
        private Dictionary<string, Material> directionMaterials = new Dictionary<string, Material>();
        private readonly string[] directions = { "North", "South", "East", "West", "Up", "Down" };

        // Outside Mode Objects
        private GameObject outsideCubeRoot;

        // Placeholder Room Objects (shown when no room scan exists)
        private GameObject placeholderRoomRoot;
        private GameObject scanNoticeRoot;
        private TextMesh scanNoticeText;
        private bool placeholderActive;
        private int noticeSerial;
        private Material untexturedMaterial;

        private void Awake()
        {
            sceneManager = GetComponent<OVRSceneManager>();
            
            if (basePlasterMaterial == null)
            {
                basePlasterMaterial = new Material(Shader.Find("Unlit/Texture"));
            }

            // Create unique materials for each direction
            foreach (string dir in directions)
            {
                directionMaterials[dir] = new Material(basePlasterMaterial);
            }

            // Neutral warm-gray for faces that never get captures (ceiling/floor —
            // VisionGrabber only tags cardinal yaw directions).
            untexturedMaterial = new Material(basePlasterMaterial);
            untexturedMaterial.color = new Color(0.45f, 0.42f, 0.38f, 1f);

            CreateOutsideCube();
            CreatePlaceholderRoom();
            CreateScanNotice();
        }

        private void OnEnable()
        {
            sceneManager.SceneModelLoadedSuccessfully += OnSceneModelLoaded;
        }

        private void OnDisable()
        {
            sceneManager.SceneModelLoadedSuccessfully -= OnSceneModelLoaded;
        }

        private void Start()
        {
            // Plaster textures are served by the soul service (compagent, :8405), not XRLF (:8402)
            int soulPort = FoveAI.Config.ConfigLoader.Settings != null ? FoveAI.Config.ConfigLoader.Settings.soulPort : 8405;
            textureEndpoint = $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:{soulPort}/api/environment/plaster_texture";
            StartCoroutine(PeriodicTextureFetch());
            StartCoroutine(AnchorWatchdog());
        }

        /// <summary>
        /// Periodically checks whether a Quest room scan exists (OVRSceneAnchors).
        /// Shows the placeholder room + scan notice when absent, hides both when a
        /// real room model is present. Handles rooms deleted at runtime.
        /// </summary>
        private IEnumerator AnchorWatchdog()
        {
            yield return new WaitForSeconds(anchorGraceSeconds);
            while (true)
            {
                int anchorCount = FindObjectsByType<OVRSceneAnchor>(FindObjectsInactive.Exclude).Length;
                SetPlaceholderActive(enablePlaceholderRoom && anchorCount == 0);
                yield return new WaitForSeconds(anchorCheckInterval);
            }
        }

        private void SetPlaceholderActive(bool active)
        {
            if (active == placeholderActive) return;
            placeholderActive = active;
            placeholderRoomRoot.SetActive(active);
            if (active)
            {
                PositionPlaceholderAtPlayer();
                ShowScanNotice();
                Debug.Log("[RoomPlasterClient] No room scan anchors — placeholder room active.");
            }
            else
            {
                scanNoticeRoot.SetActive(false);
                Debug.Log("[RoomPlasterClient] Room anchors found — real room plastering active.");
            }
        }

        private IEnumerator PeriodicTextureFetch()
        {
            while (true)
            {
                foreach (string dir in directions)
                {
                    yield return StartCoroutine(FetchDirectionTexture(dir));
                }
                
                ApplyTexturesToRoom();
                yield return new WaitForSeconds(refreshInterval);
            }
        }

        private IEnumerator FetchDirectionTexture(string direction)
        {
            string url = $"{textureEndpoint}/{direction}";
            using (UnityWebRequest uwr = UnityWebRequestTexture.GetTexture(url))
            {
                yield return uwr.SendWebRequest();

                if (uwr.result == UnityWebRequest.Result.Success)
                {
                    Texture2D tex = DownloadHandlerTexture.GetContent(uwr);
                    if (directionTextures.ContainsKey(direction) && directionTextures[direction] != null)
                    {
                        Destroy(directionTextures[direction]); // Prevent memory leak
                    }
                    directionTextures[direction] = tex;
                    
                    // Update material
                    directionMaterials[direction].mainTexture = tex;
                }
            }
        }

        private void OnSceneModelLoaded()
        {
            Debug.Log("[RoomPlasterClient] Room scene model loaded from Quest OS.");
            SetPlaceholderActive(false);
            ApplyTexturesToRoom();
        }

        private void ApplyTexturesToRoom()
        {
            // 1. Inside Mode: OVR Scene Anchors
            var sceneAnchors = FindObjectsByType<OVRSceneAnchor>(FindObjectsInactive.Exclude);
            int count = 0;

            foreach (var anchor in sceneAnchors)
            {
                var meshRenderer = anchor.GetComponentInChildren<MeshRenderer>();
                if (meshRenderer != null)
                {
                    // Calculate which direction this anchor is facing.
                    string mappedDir = DetermineAnchorDirection(anchor.transform);
                    
                    meshRenderer.sharedMaterial = directionMaterials[mappedDir];
                    meshRenderer.enabled = true; // Make them visible
                    count++;
                }
            }
        }

        private string DetermineAnchorDirection(Transform t)
        {
            // Meta OVR walls use Z as the normal facing INTO the room.
            // If the normal points East, that means it's a West wall (player looks West to see it).
            // Therefore mapped direction = -forward.
            Vector3 normal = t.forward;

            // Prioritize Up/Down if pitch is steep
            if (normal.y > 0.7f) return "Down";    // Normal points UP, so it's the floor. Wait, if normal points UP, looking DOWN sees it -> Down
            if (normal.y < -0.7f) return "Up";     // Normal points DOWN, looking UP sees it -> Up

            normal.y = 0;
            normal.Normalize();

            float dotNorth = Vector3.Dot(normal, Vector3.back);    // normal points South -> look North to see it
            float dotSouth = Vector3.Dot(normal, Vector3.forward); // normal points North -> look South
            float dotEast = Vector3.Dot(normal, Vector3.left);     // normal points West -> look East
            float dotWest = Vector3.Dot(normal, Vector3.right);    // normal points East -> look West

            float maxDot = Mathf.Max(dotNorth, dotSouth, dotEast, dotWest);
            if (maxDot == dotNorth) return "North";
            if (maxDot == dotSouth) return "South";
            if (maxDot == dotEast) return "East";
            return "West";
        }

        private void CreateOutsideCube()
        {
            outsideCubeRoot = new GameObject("OutsideEnvironmentCube");
            outsideCubeRoot.transform.SetParent(this.transform);

            float d = 50f; // 50 meters away
            float size = 100f; // 100x100 quads

            CreateQuad("North", new Vector3(0, 0, d), Quaternion.Euler(0, 180, 0), size);
            CreateQuad("South", new Vector3(0, 0, -d), Quaternion.Euler(0, 0, 0), size);
            CreateQuad("East", new Vector3(d, 0, 0), Quaternion.Euler(0, -90, 0), size);
            CreateQuad("West", new Vector3(-d, 0, 0), Quaternion.Euler(0, 90, 0), size);
            CreateQuad("Up", new Vector3(0, d, 0), Quaternion.Euler(90, 0, 0), size);
            CreateQuad("Down", new Vector3(0, -d, 0), Quaternion.Euler(-90, 0, 0), size);
        }

        private void CreateQuad(string dir, Vector3 pos, Quaternion rot, float scale)
        {
            GameObject quad = GameObject.CreatePrimitive(PrimitiveType.Quad);
            quad.name = "OutsideQuad_" + dir;
            quad.transform.SetParent(outsideCubeRoot.transform);
            quad.transform.localPosition = pos;
            quad.transform.localRotation = rot;
            quad.transform.localScale = new Vector3(scale, scale, 1);
            
            // Apply the specific directional material
            quad.GetComponent<MeshRenderer>().sharedMaterial = directionMaterials[dir];
        }

        // ── Placeholder Room (no room scan) ──────────────────────────────────

        /// <summary>
        /// Builds a room-scale inward-facing cube textured with the captured
        /// directional wall images. Shown only when no OVR scene anchors exist —
        /// i.e. the user never ran room setup or deleted the room model.
        /// </summary>
        private void CreatePlaceholderRoom()
        {
            placeholderRoomRoot = new GameObject("PlaceholderRoom");
            placeholderRoomRoot.transform.SetParent(this.transform);

            float r = placeholderRadius;
            float s = placeholderSize;
            // Cardinal walls reuse the directional capture materials; Up/Down get
            // the neutral material since yaw-based captures never produce them.
            CreateRoomQuad("North", new Vector3(0, 0, r), Quaternion.Euler(0, 180, 0), s, directionMaterials["North"]);
            CreateRoomQuad("South", new Vector3(0, 0, -r), Quaternion.Euler(0, 0, 0), s, directionMaterials["South"]);
            CreateRoomQuad("East", new Vector3(r, 0, 0), Quaternion.Euler(0, -90, 0), s, directionMaterials["East"]);
            CreateRoomQuad("West", new Vector3(-r, 0, 0), Quaternion.Euler(0, 90, 0), s, directionMaterials["West"]);
            CreateRoomQuad("Up", new Vector3(0, r, 0), Quaternion.Euler(90, 0, 0), s, untexturedMaterial);
            CreateRoomQuad("Down", new Vector3(0, -r * 0.6f, 0), Quaternion.Euler(-90, 0, 0), s, untexturedMaterial);

            placeholderRoomRoot.SetActive(false);
        }

        private void CreateRoomQuad(string dir, Vector3 pos, Quaternion rot, float scale, Material mat)
        {
            GameObject quad = GameObject.CreatePrimitive(PrimitiveType.Quad);
            quad.name = "PlaceholderQuad_" + dir;
            quad.transform.SetParent(placeholderRoomRoot.transform);
            quad.transform.localPosition = pos;
            quad.transform.localRotation = rot;
            quad.transform.localScale = new Vector3(scale, scale, 1);
            quad.GetComponent<MeshRenderer>().sharedMaterial = mat;
        }

        /// <summary>Centers the placeholder room on the player's current position.</summary>
        private void PositionPlaceholderAtPlayer()
        {
            Transform cam = Camera.main != null ? Camera.main.transform : null;
            if (cam != null)
            {
                // Center the room on the player; the floor sits r*0.6 below eye height
                placeholderRoomRoot.transform.position = cam.position;
            }
        }

        // ── Scan notice ───────────────────────────────────────────────────────

        /// <summary>
        /// Floating text panel telling the user how to create a real room scan.
        /// Fades out after noticeDuration seconds; reshown if the placeholder
        /// reactivates (e.g. the user deletes their room).
        /// </summary>
        private void CreateScanNotice()
        {
            scanNoticeRoot = new GameObject("RoomScanNotice");
            scanNoticeRoot.transform.SetParent(this.transform);

            var bg = GameObject.CreatePrimitive(PrimitiveType.Quad);
            bg.name = "NoticeBg";
            bg.transform.SetParent(scanNoticeRoot.transform, false);
            bg.transform.localScale = new Vector3(0.95f, 0.34f, 1f);
            var bgMat = new Material(Shader.Find("Unlit/Color"));
            bgMat.color = new Color(0.05f, 0.07f, 0.09f, 0.92f);
            bg.GetComponent<MeshRenderer>().sharedMaterial = bgMat;

            var textObj = new GameObject("NoticeText");
            textObj.transform.SetParent(scanNoticeRoot.transform, false);
            textObj.transform.localPosition = new Vector3(0, 0, -0.01f);
            textObj.transform.localScale = Vector3.one * 0.0065f;
            scanNoticeText = textObj.AddComponent<TextMesh>();
            scanNoticeText.fontSize = 40;
            scanNoticeText.anchor = TextAnchor.MiddleCenter;
            scanNoticeText.alignment = TextAlignment.Center;
            scanNoticeText.color = new Color(1f, 0.78f, 0.35f);
            scanNoticeText.text =
                "NO ROOM SCAN FOUND\n" +
                "Placeholder walls are showing.\n\n" +
                "Run Space Setup on the Quest:\n" +
                "Settings → Physical Space → Space Setup\n" +
                "(or Environment Mapping → Start Scan in the XR Vessel menu)";

            scanNoticeRoot.SetActive(false);
        }

        private void ShowScanNotice()
        {
            Transform cam = Camera.main != null ? Camera.main.transform : null;
            if (cam != null)
            {
                Vector3 fwd = cam.forward;
                fwd.y = 0;
                fwd.Normalize();
                if (fwd.sqrMagnitude < 0.01f) fwd = Vector3.forward;
                scanNoticeRoot.transform.position = cam.position + fwd * 1.6f;
                scanNoticeRoot.transform.rotation = Quaternion.LookRotation(fwd);
            }
            scanNoticeText.color = new Color(1f, 0.78f, 0.35f); // reset any prior fade
            scanNoticeRoot.SetActive(true);
            StartCoroutine(FadeNotice(++noticeSerial));
        }

        private IEnumerator FadeNotice(int serial)
        {
            yield return new WaitForSeconds(noticeDuration - 3f);
            if (!placeholderActive || serial != noticeSerial) yield break;
            // Fade text over the last 3 seconds
            float t = 0;
            Color baseColor = scanNoticeText.color;
            while (t < 3f && placeholderActive && serial == noticeSerial)
            {
                t += Time.deltaTime;
                var c = baseColor;
                c.a = Mathf.Lerp(1f, 0f, t / 3f);
                scanNoticeText.color = c;
                yield return null;
            }
            if (placeholderActive && serial == noticeSerial)
            {
                scanNoticeRoot.SetActive(false);
                scanNoticeText.color = baseColor; // restore for next activation
            }
        }
    }
}
