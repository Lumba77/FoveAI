using UnityEngine;
using UnityEngine.UI;

namespace FoveAI.Creative
{
    /// <summary>
    /// Scene Manipulator — grab, move, rotate, scale, spawn, and delete objects
    /// in the VR room using controller interactions.
    ///
    /// Controls:
    ///   • Trigger + drag on object: Move it
    ///   • Grip + drag: Rotate (horizontal) / Scale (vertical)
    ///   • A button: Spawn primitive (cube, sphere, cylinder, plane)
    ///   • B button: Delete grabbed object
    ///   • X button: Cycle spawn type
    ///   • Y button: Toggle manipulator mode
    ///
    /// Works with both controllers. Right hand = primary manipulator.
    /// </summary>
    public class SceneManipulator : MonoBehaviour
    {
        [Header("Spawn Settings")]
        public PrimitiveType[] spawnableTypes = {
            PrimitiveType.Cube,
            PrimitiveType.Sphere,
            PrimitiveType.Cylinder,
            PrimitiveType.Plane,
            PrimitiveType.Capsule,
        };
        public Material defaultSpawnMaterial;
        public float spawnScale = 0.3f;
        public float spawnDistance = 1.5f;

        [Header("Manipulation")]
        public float rotateSensitivity = 90f;
        public float scaleSensitivity = 1.5f;
        public float minScale = 0.05f;
        public float maxScale = 10f;
        public float grabDistance = 0.5f;

        [Header("Visual Feedback")]
        public Material highlightMaterial;
        public Color spawnColor = new Color(0.3f, 0.7f, 1f, 0.8f);

        // State
        private int _currentSpawnIndex = 0;
        private GameObject _grabbedObject;
        private OVRInput.Controller _grabHand = OVRInput.Controller.None;
        private Vector3 _grabOffset;
        private Vector3 _lastHandPos;
        private float _initialGrabDistance;
        private Vector3 _initialScale;
        private Renderer _highlightedRenderer;
        private Material _originalMaterial;

        // Spawned objects registry
        private System.Collections.Generic.List<GameObject> _spawnedObjects = new System.Collections.Generic.List<GameObject>();

        private void Update()
        {
            // Handle spawning
            if (OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
            {
                SpawnPrimitive();
            }

            // Cycle spawn type
            if (OVRInput.GetDown(OVRInput.Button.Three, OVRInput.Controller.LTouch))
            {
                _currentSpawnIndex = (_currentSpawnIndex + 1) % spawnableTypes.Length;
            }

            // Handle grab/release
            HandleGrab();

            // Handle rotation/scale while grabbed
            if (_grabbedObject != null)
            {
                HandleTransform();
            }

            // Delete grabbed object
            if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch) && _grabbedObject != null)
            {
                DeleteGrabbed();
            }

            // Highlight object under raycast
            HighlightObjectUnderRay();
        }

        // ── Spawning ──

        private void SpawnPrimitive()
        {
            Transform hand = GetHandTransform(OVRInput.Controller.RTouch);
            if (hand == null) return;

            Vector3 spawnPos = hand.position + hand.forward * spawnDistance;
            PrimitiveType type = spawnableTypes[_currentSpawnIndex];

            GameObject obj = GameObject.CreatePrimitive(type);
            obj.name = $"Spawned_{type}_{_spawnedObjects.Count}";
            obj.transform.position = spawnPos;
            obj.transform.localScale = Vector3.one * spawnScale;

            if (defaultSpawnMaterial != null)
            {
                obj.GetComponent<Renderer>().material = defaultSpawnMaterial;
            }
            else
            {
                // Create a semi-transparent material
                var mat = new Material(Shader.Find("Standard"));
                mat.color = spawnColor;
                obj.GetComponent<Renderer>().material = mat;
            }

            // Add physics so objects can be placed naturally
            var col = obj.GetComponent<Collider>();
            if (col != null) col.enabled = true;

            _spawnedObjects.Add(obj);
            Debug.Log($"[SceneManipulator] Spawned {type} at {spawnPos}");
        }

        // ── Grab/Release ──

        private void HandleGrab()
        {
            bool rightTrigger = OVRInput.Get(OVRInput.Axis1D.PrimaryIndexTrigger, OVRInput.Controller.RTouch) > 0.5f;
            bool leftTrigger = OVRInput.Get(OVRInput.Axis1D.PrimaryIndexTrigger, OVRInput.Controller.LTouch) > 0.5f;

            if (_grabbedObject == null)
            {
                // Try to grab
                if (rightTrigger)
                {
                    TryGrabObject(OVRInput.Controller.RTouch);
                }
                else if (leftTrigger)
                {
                    TryGrabObject(OVRInput.Controller.LTouch);
                }
            }
            else
            {
                // Check if still grabbing
                bool stillGrabbing = _grabHand == OVRInput.Controller.RTouch ? rightTrigger : leftTrigger;
                if (!stillGrabbing)
                {
                    ReleaseGrab();
                }
            }
        }

        private void TryGrabObject(OVRInput.Controller hand)
        {
            Transform handTransform = GetHandTransform(hand);
            if (handTransform == null) return;

            // Raycast from hand forward
            Ray ray = new Ray(handTransform.position, handTransform.forward);
            if (Physics.Raycast(ray, out RaycastHit hit, grabDistance * 3f))
            {
                GameObject hitObj = hit.collider.gameObject;
                // Don't grab the avatar or UI
                if (hitObj.CompareTag("Avatar") || hitObj.CompareTag("UI") || hitObj.CompareTag("Player"))
                    return;

                _grabbedObject = hitObj;
                _grabHand = hand;
                _grabOffset = hitObj.transform.position - handTransform.position;
                _lastHandPos = handTransform.position;
                _initialGrabDistance = Vector3.Distance(handTransform.position, hitObj.transform.position);
                _initialScale = hitObj.transform.localScale;

                // Disable physics while grabbed
                var rb = hitObj.GetComponent<Rigidbody>();
                if (rb != null)
                {
                    rb.isKinematic = true;
                }

                Debug.Log($"[SceneManipulator] Grabbed: {hitObj.name}");
            }
        }

        private void ReleaseGrab()
        {
            if (_grabbedObject == null) return;

            // Re-enable physics
            var rb = _grabbedObject.GetComponent<Rigidbody>();
            if (rb != null)
            {
                rb.isKinematic = false;
            }

            Debug.Log($"[SceneManipulator] Released: {_grabbedObject.name}");
            _grabbedObject = null;
            _grabHand = OVRInput.Controller.None;
        }

        // ── Transform (Move/Rotate/Scale) ──

        private void HandleTransform()
        {
            Transform hand = GetHandTransform(_grabHand);
            if (hand == null || _grabbedObject == null) return;

            bool gripPressed = OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger, _grabHand) > 0.5f;

            if (gripPressed)
            {
                // Grip mode: rotate and scale
                Vector3 handDelta = hand.position - _lastHandPos;

                // Horizontal movement → rotate Y
                float rotateY = handDelta.x * rotateSensitivity;
                _grabbedObject.transform.Rotate(0, rotateY, 0, Space.World);

                // Vertical movement → scale
                float scaleDelta = -handDelta.y * scaleSensitivity * 0.01f;
                Vector3 newScale = _grabbedObject.transform.localScale + Vector3.one * scaleDelta;
                float clampedScale = Mathf.Clamp(newScale.x, minScale, maxScale);
                _grabbedObject.transform.localScale = Vector3.one * clampedScale;
            }
            else
            {
                // Trigger mode: move
                Vector3 targetPos = hand.position + _grabOffset;
                _grabbedObject.transform.position = Vector3.Lerp(
                    _grabbedObject.transform.position,
                    targetPos,
                    Time.deltaTime * 15f
                );
            }

            _lastHandPos = hand.position;
        }

        // ── Delete ──

        private void DeleteGrabbed()
        {
            if (_grabbedObject == null) return;

            string name = _grabbedObject.name;
            _spawnedObjects.Remove(_grabbedObject);
            Destroy(_grabbedObject);
            _grabbedObject = null;
            _grabHand = OVRInput.Controller.None;
            Debug.Log($"[SceneManipulator] Deleted: {name}");
        }

        // ── Highlight ──

        private void HighlightObjectUnderRay()
        {
            if (_grabbedObject != null)
            {
                ClearHighlight();
                return;
            }

            Transform hand = GetHandTransform(OVRInput.Controller.RTouch);
            if (hand == null) return;

            Ray ray = new Ray(hand.position, hand.forward);
            if (Physics.Raycast(ray, out RaycastHit hit, grabDistance * 3f))
            {
                var renderer = hit.collider.GetComponent<Renderer>();
                if (renderer != null && !hit.collider.CompareTag("Avatar") && !hit.collider.CompareTag("UI"))
                {
                    if (_highlightedRenderer != renderer)
                    {
                        ClearHighlight();
                        _highlightedRenderer = renderer;
                        _originalMaterial = renderer.material;
                        if (highlightMaterial != null)
                            renderer.material = highlightMaterial;
                    }
                }
                else
                {
                    ClearHighlight();
                }
            }
            else
            {
                ClearHighlight();
            }
        }

        private void ClearHighlight()
        {
            if (_highlightedRenderer != null && _originalMaterial != null)
            {
                _highlightedRenderer.material = _originalMaterial;
                _highlightedRenderer = null;
                _originalMaterial = null;
            }
        }

        // ── Helpers ──

        private Transform GetHandTransform(OVRInput.Controller controller)
        {
            // Fall back to controller pose
            Vector3 pos = OVRInput.GetLocalControllerPosition(controller);
            Quaternion rot = OVRInput.GetLocalControllerRotation(controller);

            // Create a temporary transform if needed
            if (_tempHandTransform == null)
            {
                var go = new GameObject("TempHandTransform");
                _tempHandTransform = go.transform;
            }

            _tempHandTransform.position = pos;
            _tempHandTransform.rotation = rot;
            return _tempHandTransform;
        }

        private Transform _tempHandTransform;

        // ── Public API (for Alice to control) ──

        public void SpawnAt(PrimitiveType type, Vector3 position, float scale = 0.3f)
        {
            GameObject obj = GameObject.CreatePrimitive(type);
            obj.name = $"AliceSpawn_{type}_{_spawnedObjects.Count}";
            obj.transform.position = position;
            obj.transform.localScale = Vector3.one * scale;

            if (defaultSpawnMaterial != null)
                obj.GetComponent<Renderer>().material = defaultSpawnMaterial;

            _spawnedObjects.Add(obj);
        }

        public void ClearAllSpawned()
        {
            foreach (var obj in _spawnedObjects)
            {
                if (obj != null) Destroy(obj);
            }
            _spawnedObjects.Clear();
        }

        public int SpawnedCount => _spawnedObjects.Count;
    }
}
