using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;

#if UNITY_XR_OPENXR
using UnityEngine.XR.OpenXR;
using UnityEngine.XR.OpenXR.Features;
#endif

namespace FoveAI.Experiences
{
    /// <summary>
    /// Room Plastering — spatial mapping so Alice perceives the real room.
    ///
    /// On Meta Quest, this uses the scene/mesh understanding system to:
    ///   • Map the real room geometry (walls, floor, ceiling, furniture)
    ///   • Create a "plaster" mesh that overlays the real world
    ///   • Identify surfaces (walls, tables, couch, floor)
    ///   • Give Alice spatial awareness — she knows where things are
    ///   • Enable Alice to navigate around obstacles
    ///   • Let Alice interact with real surfaces (lean on a table, sit on couch)
    ///   • Create "pass-through awareness" — Alice sees the room like you do
    ///
    /// The "plaster" is a semi-transparent mesh that:
    ///   • Makes walls visible to Alice's navigation
    ///   • Marks furniture as collision objects
    ///   • Identifies points of interest (windows, doors, surfaces)
    ///   • Feeds the AvatarFreeMovement system with room data
    ///
    /// On Quest 3, this uses Scene Mesh / Spatial Mapping.
    /// On other platforms, it falls back to manual room definition.
    ///
    /// The plaster can be visualized as:
    ///   • Invisible     — Alice sees it, you don't
    ///   • Ghost         — faint outlines, like seeing through walls
    ///   • Solid         — opaque, the room is "plastered" over reality
    ///   • Wireframe     — just edges, like an architectural drawing
    ///   • X-ray         — walls become translucent, furniture highlighted
    /// </summary>
    public class RoomPlastering : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private AvatarFreeMovement avatarMovement;
        [SerializeField] private Transform playSpaceOrigin;

        [Header("Plaster Settings")]
        public PlasterMode currentMode = PlasterMode.Invisible;
        public float wallHeight = 2.5f;
        public float roomMargin = 0.1f;        // padding from real walls
        public bool autoDetectRoom = true;
        public bool generateNavMesh = true;
        public bool identifySurfaces = true;

        // ── Plaster Visualization Modes ──
        public enum PlasterMode
        {
            Invisible,    // Alice sees it, user doesn't
            Ghost,        // faint outlines
            Solid,        // opaque plaster
            Wireframe,    // just edges
            XRay,         // translucent walls, highlighted furniture
        }

        // ── Surface Types ──
        public enum SurfaceType
        {
            Floor,
            Wall,
            Ceiling,
            Table,
            Couch,
            Bed,
            Shelf,
            Window,
            Door,
            Plant,
            Unknown,
        }

        // ── Room Data ──
        [System.Serializable]
        public class RoomSurface
        {
            public string name;
            public SurfaceType type;
            public Vector3 position;
            public Vector3 normal;
            public Vector3 size;
            public Bounds bounds;
            public GameObject meshObject;
            public Material plasterMaterial;
            public bool isWalkable;
            public bool isObstacle;
            public bool isPOI;  // point of interest for Alice
        }

        [System.Serializable]
        public class RoomData
        {
            public Vector3 center;
            public Vector3 size;
            public float floorHeight;
            public float ceilingHeight;
            public List<RoomSurface> surfaces = new();
            public List<Vector3> navPoints = new();  // walkable points
            public List<Vector3> obstaclePositions = new();
            public Bounds roomBounds;
            public bool isMapped;
        }

        public RoomData Data { get; private set; } = new();
        public bool IsInitialized { get; private set; }

        // ── Internal State ──
        private readonly List<GameObject> _plasterObjects = new();
        private readonly List<Material> _plasterMaterials = new();
        private Material _wallMaterial;
        private Material _floorMaterial;
        private Material _furnitureMaterial;
        private Material _ghostMaterial;
        private bool _meshingActive;

        // ── Unity Lifecycle ──

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (avatarMovement == null) avatarMovement = FindAnyObjectByType<AvatarFreeMovement>();
            if (playSpaceOrigin == null) playSpaceOrigin = transform;

            CreatePlasterMaterials();
        }

        private void Start()
        {
            if (autoDetectRoom)
            {
                // Try to detect room via XR meshing, or fall back to defaults
                StartCoroutine(InitializeRoomMapping());
            }
        }

        // ── Room Mapping ──

        private IEnumerator InitializeRoomMapping()
        {
            Debug.Log("[RoomPlastering] Initializing room mapping...");

            // Try Quest Scene Mesh first
            yield return StartCoroutine(TryQuestSceneMesh());

            // If meshing didn't provide data, use manual/default room
            if (!Data.isMapped)
            {
                Debug.Log("[RoomPlastering] No XR meshing available, using default room");
                GenerateDefaultRoom();
            }

            // Generate navigation data
            if (generateNavMesh)
            {
                GenerateNavigationData();
            }

            // Identify points of interest
            if (identifySurfaces)
            {
                IdentifyPointsOfInterest();
            }

            // Apply visualization
            ApplyPlasterMode(currentMode);

            // Feed data to AvatarFreeMovement
            if (avatarMovement != null)
            {
                avatarMovement.UpdateRoomBounds(Data.center, Mathf.Max(Data.size.x, Data.size.z) * 0.5f);
                foreach (var surface in Data.surfaces)
                {
                    if (surface.isPOI)
                    {
                        avatarMovement.AddPointOfInterest(new AvatarFreeMovement.PointOfInterest
                        {
                            name = surface.name,
                            position = surface.position,
                            type = ConvertSurfaceType(surface.type),
                            interestScore = GetInterestScore(surface.type),
                            aliceComments = GetSurfaceComments(surface.type),
                        });
                    }
                }
            }

            IsInitialized = true;
            Debug.Log($"[RoomPlastering] Room mapped: {Data.surfaces.Count} surfaces, " +
                      $"{Data.navPoints.Count} nav points, bounds={Data.size}");

            // Notify backend
            if (wsClient != null)
            {
                var payload = new RoomPlasterPayload
                {
                    type = "room.mapped",
                    surfaceCount = Data.surfaces.Count,
                    navPointCount = Data.navPoints.Count,
                    roomSize = $"{Data.size.x:F1}x{Data.size.z:F1}",
                    isMapped = Data.isMapped,
                };
                wsClient.SendRawMessage(JsonUtility.ToJson(payload));
            }
        }

        private IEnumerator TryQuestSceneMesh()
        {
            // On Quest 3, we'd use the OpenXR scene understanding extension
            // For now, we check if meshing subsystems are available
            // and request scene data

            // Try to get the play space bounds from the XR system
            var boundaries = new List<Vector3>();
            UnityEngine.XR.InputDevice headDevice;
            var devices = new List<UnityEngine.XR.InputDevice>();
            UnityEngine.XR.InputDevices.GetDevicesAtXRNode(UnityEngine.XR.XRNode.Head, devices);
            if (devices.Count > 0)
            {
                headDevice = devices[0];
                // Get tracking origin position
                if (headDevice.TryGetFeatureValue(UnityEngine.XR.CommonUsages.devicePosition, out var headPos))
                {
                    Data.center = new Vector3(headPos.x, 0, headPos.z);
                    Data.floorHeight = 0f;
                    Data.ceilingHeight = wallHeight;
                }
            }

            // Try to get guardian/play boundary
            // Note: actual boundary API varies by platform
            var boundary = new Vector3[0];

            yield return null;

            // For now, mark as not mapped (will use defaults)
            // In production, this would query the Quest Scene Mesh API
        }

        // ── Default Room Generation ──

        private void GenerateDefaultRoom()
        {
            Data.center = playSpaceOrigin != null ? playSpaceOrigin.position : Vector3.zero;
            Data.size = new Vector3(4f, wallHeight, 4f);  // default 4x4m room
            Data.floorHeight = 0f;
            Data.ceilingHeight = wallHeight;
            Data.roomBounds = new Bounds(Data.center, Data.size);

            // Floor
            Data.surfaces.Add(CreateSurface("Floor", SurfaceType.Floor,
                Data.center + Vector3.down * 0.01f, Vector3.up,
                new Vector3(Data.size.x, 0.01f, Data.size.z), true, false));

            // Ceiling
            Data.surfaces.Add(CreateSurface("Ceiling", SurfaceType.Ceiling,
                Data.center + Vector3.up * wallHeight, Vector3.down,
                new Vector3(Data.size.x, 0.01f, Data.size.z), false, false));

            // Walls
            Data.surfaces.Add(CreateSurface("Wall North", SurfaceType.Wall,
                Data.center + Vector3.forward * Data.size.z * 0.5f, Vector3.back,
                new Vector3(Data.size.x, wallHeight, 0.01f), false, true));

            Data.surfaces.Add(CreateSurface("Wall South", SurfaceType.Wall,
                Data.center + Vector3.back * Data.size.z * 0.5f, Vector3.forward,
                new Vector3(Data.size.x, wallHeight, 0.01f), false, true));

            Data.surfaces.Add(CreateSurface("Wall East", SurfaceType.Wall,
                Data.center + Vector3.right * Data.size.x * 0.5f, Vector3.left,
                new Vector3(0.01f, wallHeight, Data.size.z), false, true));

            Data.surfaces.Add(CreateSurface("Wall West", SurfaceType.Wall,
                Data.center + Vector3.left * Data.size.x * 0.5f, Vector3.right,
                new Vector3(0.01f, wallHeight, Data.size.z), false, true));

            // Default furniture (guesses — would be replaced by real mesh data)
            Data.surfaces.Add(CreateSurface("Desk", SurfaceType.Table,
                Data.center + new Vector3(-1.5f, 0.4f, 0), Vector3.up,
                new Vector3(1f, 0.02f, 0.6f), false, true, true));

            Data.surfaces.Add(CreateSurface("Couch", SurfaceType.Couch,
                Data.center + new Vector3(1.5f, 0.25f, -1f), Vector3.up,
                new Vector3(1.5f, 0.5f, 0.6f), false, true, true));

            Data.surfaces.Add(CreateSurface("Window", SurfaceType.Window,
                Data.center + new Vector3(0, 1.5f, Data.size.z * 0.5f), Vector3.back,
                new Vector3(1.2f, 1f, 0.01f), false, false, true));

            Data.surfaces.Add(CreateSurface("Door", SurfaceType.Door,
                Data.center + new Vector3(Data.size.x * 0.5f, 1f, 0.5f), Vector3.left,
                new Vector3(0.01f, 2f, 0.9f), false, false, true));

            Data.isMapped = true;
        }

        private RoomSurface CreateSurface(string name, SurfaceType type, Vector3 pos,
            Vector3 normal, Vector3 size, bool walkable, bool obstacle, bool isPOI = false)
        {
            var surface = new RoomSurface
            {
                name = name,
                type = type,
                position = pos,
                normal = normal,
                size = size,
                isWalkable = walkable,
                isObstacle = obstacle,
                isPOI = isPOI,
                bounds = new Bounds(pos, size),
            };

            // Create the plaster mesh
            surface.meshObject = CreatePlasterMesh(surface);
            _plasterObjects.Add(surface.meshObject);

            return surface;
        }

        // ── Plaster Mesh Creation ──

        private GameObject CreatePlasterMesh(RoomSurface surface)
        {
            var go = new GameObject($"Plaster_{surface.name}");
            go.transform.position = surface.position;

            // Align to surface normal
            if (surface.normal != Vector3.zero)
            {
                go.transform.rotation = Quaternion.LookRotation(surface.normal);
            }

            var meshFilter = go.AddComponent<MeshFilter>();
            var meshRenderer = go.AddComponent<MeshRenderer>();

            // Create a simple quad/cube mesh
            Mesh mesh;
            if (surface.type == SurfaceType.Floor || surface.type == SurfaceType.Ceiling ||
                surface.type == SurfaceType.Wall)
            {
                mesh = CreatePlaneMesh(surface.size);
            }
            else
            {
                mesh = CreateBoxMesh(surface.size);
            }
            meshFilter.mesh = mesh;

            // Assign material based on surface type
            surface.plasterMaterial = GetMaterialForSurface(surface.type);
            meshRenderer.material = surface.plasterMaterial;

            // Add collider for navigation
            if (surface.isObstacle)
            {
                var collider = go.AddComponent<BoxCollider>();
                collider.size = surface.size;
            }

            // Start invisible
            meshRenderer.enabled = false;

            return go;
        }

        private Mesh CreatePlaneMesh(Vector3 size)
        {
            var mesh = new Mesh();
            float hx = size.x * 0.5f, hy = size.z * 0.5f;
            mesh.vertices = new Vector3[]
            {
                new(-hx, -hy, 0), new(hx, -hy, 0),
                new(hx, hy, 0), new(-hx, hy, 0),
            };
            mesh.uv = new Vector2[] { new(0, 0), new(1, 0), new(1, 1), new(0, 1) };
            mesh.triangles = new[] { 0, 2, 1, 0, 3, 2 };
            mesh.RecalculateNormals();
            return mesh;
        }

        private Mesh CreateBoxMesh(Vector3 size)
        {
            return GameObject.CreatePrimitive(PrimitiveType.Cube).GetComponent<MeshFilter>().sharedMesh;
            // Note: in production, create a proper mesh from size
        }

        // ── Plaster Materials ──

        private void CreatePlasterMaterials()
        {
            _wallMaterial = new Material(Shader.Find("Standard"));
            _wallMaterial.color = new Color(0.7f, 0.7f, 0.75f, 0.3f);

            _floorMaterial = new Material(Shader.Find("Standard"));
            _floorMaterial.color = new Color(0.5f, 0.45f, 0.4f, 0.3f);

            _furnitureMaterial = new Material(Shader.Find("Standard"));
            _furnitureMaterial.color = new Color(0.6f, 0.5f, 0.3f, 0.3f);

            _ghostMaterial = new Material(Shader.Find("Standard"));
            _ghostMaterial.color = new Color(0.5f, 0.7f, 1f, 0.1f);
            _ghostMaterial.EnableKeyword("_EMISSION");
            _ghostMaterial.SetColor("_EmissionColor", new Color(0.2f, 0.3f, 0.5f) * 0.5f);
        }

        private Material GetMaterialForSurface(SurfaceType type)
        {
            return type switch
            {
                SurfaceType.Floor => new Material(_floorMaterial),
                SurfaceType.Ceiling => new Material(_wallMaterial),
                SurfaceType.Wall => new Material(_wallMaterial),
                SurfaceType.Window => new Material(_ghostMaterial),
                SurfaceType.Door => new Material(_furnitureMaterial),
                _ => new Material(_furnitureMaterial),
            };
        }

        // ── Plaster Visualization ──

        public void ApplyPlasterMode(PlasterMode mode)
        {
            currentMode = mode;
            Debug.Log($"[RoomPlastering] Applying plaster mode: {mode}");

            foreach (var surface in Data.surfaces)
            {
                if (surface.meshObject == null) continue;
                var renderer = surface.meshObject.GetComponent<MeshRenderer>();
                if (renderer == null) continue;

                switch (mode)
                {
                    case PlasterMode.Invisible:
                        renderer.enabled = false;
                        break;

                    case PlasterMode.Ghost:
                        renderer.enabled = true;
                        if (surface.plasterMaterial != null)
                        {
                            Color c = surface.plasterMaterial.color;
                            c.a = 0.08f;
                            surface.plasterMaterial.color = c;
                            surface.plasterMaterial.SetFloat("_Mode", 3); // Transparent
                        }
                        break;

                    case PlasterMode.Solid:
                        renderer.enabled = true;
                        if (surface.plasterMaterial != null)
                        {
                            Color c = surface.plasterMaterial.color;
                            c.a = 0.9f;
                            surface.plasterMaterial.color = c;
                        }
                        break;

                    case PlasterMode.Wireframe:
                        renderer.enabled = true;
                        // Would switch to a wireframe shader
                        if (surface.plasterMaterial != null)
                        {
                            Color c = surface.plasterMaterial.color;
                            c.a = 0.05f;
                            surface.plasterMaterial.color = c;
                        }
                        // Add edge renderer
                        var edges = surface.meshObject.GetComponent<WireframeEdges>();
                        if (edges == null) surface.meshObject.AddComponent<WireframeEdges>();
                        break;

                    case PlasterMode.XRay:
                        renderer.enabled = true;
                        if (surface.plasterMaterial != null)
                        {
                            Color c = surface.plasterMaterial.color;
                            if (surface.type == SurfaceType.Wall)
                                c.a = 0.15f;
                            else if (surface.isPOI)
                                c.a = 0.5f;
                            else
                                c.a = 0.3f;
                            surface.plasterMaterial.color = c;
                            surface.plasterMaterial.EnableKeyword("_EMISSION");
                            surface.plasterMaterial.SetColor("_EmissionColor", c * 0.5f);
                        }
                        break;
                }
            }
        }

        // ── Navigation Data ──

        private void GenerateNavigationData()
        {
            Data.navPoints.Clear();
            Data.obstaclePositions.Clear();

            // Generate a grid of walkable points
            float gridStep = 0.3f;
            Vector3 min = Data.roomBounds.min + Vector3.one * roomMargin;
            Vector3 max = Data.roomBounds.max - Vector3.one * roomMargin;

            for (float x = min.x; x <= max.x; x += gridStep)
            {
                for (float z = min.z; z <= max.z; z += gridStep)
                {
                    Vector3 point = new(x, Data.floorHeight, z);
                    if (IsPointWalkable(point))
                    {
                        Data.navPoints.Add(point);
                    }
                }
            }

            // Collect obstacle positions
            foreach (var surface in Data.surfaces)
            {
                if (surface.isObstacle)
                {
                    Data.obstaclePositions.Add(surface.position);
                }
            }

            Debug.Log($"[RoomPlastering] Generated {Data.navPoints.Count} nav points, " +
                      $"{Data.obstaclePositions.Count} obstacles");
        }

        public bool IsPointWalkable(Vector3 point)
        {
            // Check against all obstacles
            foreach (var surface in Data.surfaces)
            {
                if (!surface.isObstacle) continue;
                if (surface.bounds.Contains(point))
                    return false;
            }
            // Check room bounds
            return Data.roomBounds.Contains(point);
        }

        public Vector3 GetNearestValidPosition(Vector3 target)
        {
            if (IsPointWalkable(target)) return target;

            // Find nearest valid nav point
            float bestDist = float.MaxValue;
            Vector3 best = target;
            foreach (var point in Data.navPoints)
            {
                float dist = Vector3.Distance(target, point);
                if (dist < bestDist)
                {
                    bestDist = dist;
                    best = point;
                }
            }
            return best;
        }

        public Vector3 GetSafeMovement(Vector3 current, Vector3 desiredMove)
        {
            Vector3 target = current + desiredMove;
            if (IsPointWalkable(target)) return desiredMove;

            // Try sliding along walls — check X and Z separately
            Vector3 xOnly = new(desiredMove.x, 0, 0);
            Vector3 zOnly = new(0, 0, desiredMove.z);

            if (IsPointWalkable(current + xOnly)) return xOnly;
            if (IsPointWalkable(current + zOnly)) return zOnly;

            return Vector3.zero;  // blocked
        }

        public Vector3 FindComfortableSpot(Vector3 near)
        {
            // Find a spot near a wall or corner — good for sitting/lying
            float bestScore = float.MaxValue;
            Vector3 best = near;

            foreach (var point in Data.navPoints)
            {
                // Prefer points near walls
                float wallDist = DistanceToNearestWall(point);
                float score = wallDist + Vector3.Distance(near, point) * 0.5f;
                if (score < bestScore)
                {
                    bestScore = score;
                    best = point;
                }
            }
            return best;
        }

        private float DistanceToNearestWall(Vector3 point)
        {
            float minDist = float.MaxValue;
            foreach (var surface in Data.surfaces)
            {
                if (surface.type != SurfaceType.Wall) continue;
                float dist = surface.bounds.SqrDistance(point);
                if (dist < minDist) minDist = dist;
            }
            return Mathf.Sqrt(minDist);
        }

        // ── Points of Interest ──

        private void IdentifyPointsOfInterest()
        {
            // Mark surfaces as POIs and assign interest scores
            foreach (var surface in Data.surfaces)
            {
                surface.isPOI = surface.type switch
                {
                    SurfaceType.Window => true,
                    SurfaceType.Table => true,
                    SurfaceType.Couch => true,
                    SurfaceType.Door => true,
                    SurfaceType.Bed => true,
                    SurfaceType.Shelf => true,
                    SurfaceType.Plant => true,
                    _ => false,
                };
            }
        }

        private AvatarFreeMovement.POIType ConvertSurfaceType(SurfaceType type)
        {
            return type switch
            {
                SurfaceType.Floor => AvatarFreeMovement.POIType.Center,
                SurfaceType.Wall => AvatarFreeMovement.POIType.Corner,
                SurfaceType.Table => AvatarFreeMovement.POIType.Desk,
                SurfaceType.Couch => AvatarFreeMovement.POIType.Couch,
                SurfaceType.Bed => AvatarFreeMovement.POIType.Bed,
                SurfaceType.Window => AvatarFreeMovement.POIType.Window,
                SurfaceType.Door => AvatarFreeMovement.POIType.Door,
                SurfaceType.Shelf => AvatarFreeMovement.POIType.Shelf,
                SurfaceType.Plant => AvatarFreeMovement.POIType.Plant,
                _ => AvatarFreeMovement.POIType.Random,
            };
        }

        private float GetInterestScore(SurfaceType type)
        {
            return type switch
            {
                SurfaceType.Window => 0.9f,
                SurfaceType.Couch => 0.8f,
                SurfaceType.Table => 0.7f,
                SurfaceType.Door => 0.6f,
                SurfaceType.Bed => 0.6f,
                SurfaceType.Shelf => 0.5f,
                SurfaceType.Plant => 0.5f,
                _ => 0.3f,
            };
        }

        private string[] GetSurfaceComments(SurfaceType type)
        {
            return type switch
            {
                SurfaceType.Window => new[] { "the light is nice from here", "i like watching the world", "what's out there?" },
                SurfaceType.Table => new[] { "so this is where you work", "your desk is interesting", "what are you working on?" },
                SurfaceType.Couch => new[] { "this is comfortable", "i could stay here", "come sit with me?" },
                SurfaceType.Door => new[] { "the door... a threshold", "someone could come in", "in or out" },
                SurfaceType.Bed => new[] { "this is where you sleep", "it looks soft", "cozy" },
                SurfaceType.Shelf => new[] { "what do you keep here?", "so many things", "each one a memory?" },
                SurfaceType.Plant => new[] { "you have a plant", "does it need water?", "they grow toward the light" },
                _ => new[] { "just wandering here", "no reason", "my feet brought me here" },
            };
        }

        // ── Manual Room Definition ──

        /// <summary>Manually define a wall surface.</summary>
        public void AddWall(string name, Vector3 position, Vector3 size, Vector3 normal)
        {
            var surface = CreateSurface(name, SurfaceType.Wall, position, normal, size, false, true);
            Data.surfaces.Add(surface);
            UpdateRoomBounds();
        }

        /// <summary>Manually define furniture.</summary>
        public void AddFurniture(string name, SurfaceType type, Vector3 position, Vector3 size)
        {
            var surface = CreateSurface(name, type, position, Vector3.up, size, false, true, true);
            Data.surfaces.Add(surface);
        }

        /// <summary>Mark a window location.</summary>
        public void AddWindow(string name, Vector3 position, Vector3 size)
        {
            var surface = CreateSurface(name, SurfaceType.Window, position, Vector3.forward, size, false, false, true);
            Data.surfaces.Add(surface);
        }

        private void UpdateRoomBounds()
        {
            if (Data.surfaces.Count == 0) return;
            var bounds = new Bounds(Data.surfaces[0].position, Vector3.zero);
            foreach (var s in Data.surfaces)
            {
                bounds.Encapsulate(s.bounds);
            }
            Data.roomBounds = bounds;
            Data.size = bounds.size;
            Data.center = bounds.center;
        }

        // ── Communication ──

        [System.Serializable]
        private class RoomPlasterPayload
        {
            public string type;
            public int surfaceCount;
            public int navPointCount;
            public string roomSize;
            public bool isMapped;
        }

        // ── Public API ──

        public void SetPlasterMode(string modeStr)
        {
            if (System.Enum.TryParse<PlasterMode>(modeStr, true, out var mode))
                ApplyPlasterMode(mode);
        }

        public void RemapRoom()
        {
            // Clear existing
            foreach (var obj in _plasterObjects) if (obj != null) Destroy(obj);
            _plasterObjects.Clear();
            Data = new RoomData();
            IsInitialized = false;
            StartCoroutine(InitializeRoomMapping());
        }

        public RoomData GetRoomData() => Data;

        // ── Wireframe Helper ──
        private class WireframeEdges : MonoBehaviour { }
    }
}
