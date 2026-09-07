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
        public string textureEndpoint = "http://192.168.8.100:8402/api/environment/plaster_texture"; // Overridden in Start
        public float refreshInterval = 5f;

        [Header("Materials")]
        public Material basePlasterMaterial; // Use Unlit/Texture

        private OVRSceneManager sceneManager;
        private Dictionary<string, Texture2D> directionTextures = new Dictionary<string, Texture2D>();
        private Dictionary<string, Material> directionMaterials = new Dictionary<string, Material>();
        private readonly string[] directions = { "North", "South", "East", "West", "Up", "Down" };

        // Outside Mode Objects
        private GameObject outsideCubeRoot;

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

            CreateOutsideCube();
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
            // Dynamically set endpoint using the central config IP and httpPort
            int soulPort = FoveAI.Config.ConfigLoader.Settings != null ? FoveAI.Config.ConfigLoader.Settings.httpPort : 8402;
            textureEndpoint = $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:{soulPort}/api/environment/plaster_texture";
            StartCoroutine(PeriodicTextureFetch());
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
    }
}
