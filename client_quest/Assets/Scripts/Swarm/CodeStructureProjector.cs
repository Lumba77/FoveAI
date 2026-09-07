using System.Collections.Generic;
using UnityEngine;

namespace FoveAI.Swarm
{
    public class CodeStructureProjector : MonoBehaviour
    {
        [Header("Settings")]
        public int nodeCount = 15;
        public float radius = 1.0f;
        public Color nodeColor = new Color(0.2f, 0.8f, 1.0f, 0.8f);
        public Color lineColor = new Color(0.2f, 0.8f, 1.0f, 0.3f);

        private List<GameObject> _nodes = new List<GameObject>();
        private GameObject _structureRoot;

        private void Start()
        {
            GenerateStructure();
        }

        public void GenerateStructure()
        {
            if (_structureRoot != null)
            {
                Destroy(_structureRoot);
                _nodes.Clear();
            }

            _structureRoot = new GameObject("CodeStructureRoot");
            _structureRoot.transform.SetParent(this.transform, false);

            Material nodeMat = new Material(Shader.Find("Standard"));
            nodeMat.color = nodeColor;
            nodeMat.EnableKeyword("_EMISSION");
            nodeMat.SetColor("_EmissionColor", nodeColor * 1.5f);

            Material lineMat = new Material(Shader.Find("Sprites/Default"));

            // 1. Generate Nodes (Files / Functions)
            for (int i = 0; i < nodeCount; i++)
            {
                GameObject node = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                node.name = $"CodeNode_{i}";
                node.transform.SetParent(_structureRoot.transform, false);
                
                // Random position within a spherical volume
                Vector3 pos = Random.insideUnitSphere * radius;
                node.transform.localPosition = pos;
                node.transform.localScale = Vector3.one * Random.Range(0.05f, 0.15f);
                
                node.GetComponent<Renderer>().material = nodeMat;
                
                // Remove collider to not interfere with NavMesh or physics grab unnecessarily
                Destroy(node.GetComponent<Collider>());
                
                _nodes.Add(node);
            }

            // 2. Generate Edges (Dependencies)
            for (int i = 0; i < _nodes.Count; i++)
            {
                // Connect each node to 1-3 other random nodes to form a web
                int connections = Random.Range(1, 4);
                for (int c = 0; c < connections; c++)
                {
                    int targetIdx = Random.Range(0, _nodes.Count);
                    if (targetIdx == i) continue;

                    GameObject lineObj = new GameObject($"Edge_{i}_{targetIdx}");
                    lineObj.transform.SetParent(_structureRoot.transform, false);
                    
                    LineRenderer lr = lineObj.AddComponent<LineRenderer>();
                    lr.material = lineMat;
                    lr.startColor = lineColor;
                    lr.endColor = lineColor;
                    lr.startWidth = 0.01f;
                    lr.endWidth = 0.01f;
                    lr.positionCount = 2;
                    lr.SetPosition(0, _nodes[i].transform.position);
                    lr.SetPosition(1, _nodes[targetIdx].transform.position);
                    lr.useWorldSpace = true;
                }
            }
        }

        public Vector3 GetRandomNodePosition()
        {
            if (_nodes.Count == 0) return this.transform.position;
            return _nodes[Random.Range(0, _nodes.Count)].transform.position;
        }

        private void Update()
        {
            // Gently rotate the entire structure
            if (_structureRoot != null)
            {
                _structureRoot.transform.Rotate(Vector3.up, 5f * Time.deltaTime);
            }
        }
    }
}
