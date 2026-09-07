using System;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;

namespace FoveAI.Swarm
{
    public class SwarmVisualizer : MonoBehaviour
    {
        [Header("Dependencies")]
        public FoveAIWebSocketClient wsClient;
        public CodeStructureProjector projector;

        [Header("Swarm Settings")]
        public Color agentColor = new Color(1.0f, 0.2f, 0.8f, 1.0f); // Magenta/Pink for active agents
        public float agentSpeed = 2.0f;
        public int maxAgents = 30;

        private Dictionary<string, SwarmAgent> _agents = new Dictionary<string, SwarmAgent>();
        private Material _agentMat;

        private class SwarmAgent
        {
            public GameObject go;
            public Vector3 targetPos;
            public float speed;
        }

        [Serializable]
        private class SwarmPayload
        {
            public string agent_id;
            public string action; // "heal", "code", "inspect"
            public string target_node; 
        }

        private void Awake()
        {
            if (wsClient == null) wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            if (projector == null) projector = FindAnyObjectByType<CodeStructureProjector>();

            _agentMat = new Material(Shader.Find("Standard"));
            _agentMat.color = agentColor;
            _agentMat.EnableKeyword("_EMISSION");
            _agentMat.SetColor("_EmissionColor", agentColor * 2.0f);
        }

        private void OnEnable()
        {
            if (wsClient != null) wsClient.OnRawMessageReceived += HandleMessage;
        }

        private void OnDisable()
        {
            if (wsClient != null) wsClient.OnRawMessageReceived -= HandleMessage;
        }

        private void HandleMessage(string message)
        {
            string eventType = ExtractStringField(message, "event");
            if (eventType == "swarm.task_update" || eventType == "agent.move")
            {
                string payloadStr = ExtractStringField(message, "payload", true);
                if (!string.IsNullOrEmpty(payloadStr))
                {
                    try
                    {
                        SwarmPayload payload = JsonUtility.FromJson<SwarmPayload>(payloadStr);
                        UpdateAgent(payload);
                    }
                    catch (Exception e)
                    {
                        Debug.LogWarning($"[SwarmVisualizer] Failed to parse payload: {e.Message}");
                    }
                }
            }
        }

        private void UpdateAgent(SwarmPayload data)
        {
            if (string.IsNullOrEmpty(data.agent_id)) return;

            if (!_agents.ContainsKey(data.agent_id))
            {
                if (_agents.Count >= maxAgents) return; // Cap visual agents

                GameObject obj = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                obj.name = $"SwarmAgent_{data.agent_id}";
                obj.transform.SetParent(this.transform, false);
                obj.transform.localScale = Vector3.one * 0.05f; // Very small dots
                
                Destroy(obj.GetComponent<Collider>());
                obj.GetComponent<Renderer>().material = _agentMat;

                TrailRenderer trail = obj.AddComponent<TrailRenderer>();
                trail.time = 0.5f;
                trail.startWidth = 0.02f;
                trail.endWidth = 0.0f;
                trail.material = new Material(Shader.Find("Sprites/Default"));
                trail.startColor = agentColor;
                trail.endColor = new Color(agentColor.r, agentColor.g, agentColor.b, 0f);

                // Start at a random node
                obj.transform.position = projector != null ? projector.GetRandomNodePosition() : Vector3.zero;

                _agents[data.agent_id] = new SwarmAgent
                {
                    go = obj,
                    targetPos = obj.transform.position,
                    speed = UnityEngine.Random.Range(agentSpeed * 0.8f, agentSpeed * 1.2f)
                };
            }

            // Assign new target node position
            if (projector != null)
            {
                _agents[data.agent_id].targetPos = projector.GetRandomNodePosition();
            }
        }

        private void Update()
        {
            foreach (var kvp in _agents)
            {
                SwarmAgent agent = kvp.Value;
                if (agent.go != null)
                {
                    agent.go.transform.position = Vector3.MoveTowards(
                        agent.go.transform.position, 
                        agent.targetPos, 
                        agent.speed * Time.deltaTime
                    );

                    // If reached target, maybe pick a new random one if they are "healing"
                    if (Vector3.Distance(agent.go.transform.position, agent.targetPos) < 0.01f)
                    {
                         if (projector != null && UnityEngine.Random.value > 0.95f) // occasional random wandering
                         {
                             agent.targetPos = projector.GetRandomNodePosition();
                         }
                    }
                }
            }
        }

        private string ExtractStringField(string json, string fieldName, bool isObject = false)
        {
            string search = "\"" + fieldName + "\":";
            int idx = json.IndexOf(search);
            if (idx == -1) return null;

            int valStart = idx + search.Length;
            while (valStart < json.Length && (json[valStart] == ' ' || json[valStart] == '\t')) valStart++;

            if (isObject)
            {
                if (json[valStart] == '{')
                {
                    int openCount = 0;
                    for (int i = valStart; i < json.Length; i++)
                    {
                        if (json[i] == '{') openCount++;
                        else if (json[i] == '}')
                        {
                            openCount--;
                            if (openCount == 0) return json.Substring(valStart, i - valStart + 1);
                        }
                    }
                }
                return null;
            }

            if (json[valStart] == '"')
            {
                valStart++;
                int valEnd = json.IndexOf("\"", valStart);
                if (valEnd != -1) return json.Substring(valStart, valEnd - valStart);
            }
            return null;
        }
    }
}
