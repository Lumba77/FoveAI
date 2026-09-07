using System;
using UnityEngine;
using UnityEngine.AI;
using FoveAI.IPC;

namespace FoveAI.Avatar
{
    [RequireComponent(typeof(NavMeshAgent))]
    public class AvatarMovement : MonoBehaviour
    {
        [Header("Dependencies")]
        public FoveAIWebSocketClient wsClient;

        private NavMeshAgent _agent;

        [Serializable]
        private class WalkToPayload
        {
            public float x;
            public float y;
            public float z;
        }

        [Header("Autonomous Navigation")]
        [Tooltip("Allow the avatar to wander and explore the room autonomously.")]
        public bool autonomousWander = true;
        [Tooltip("Maximum wander distance from home/player (meters).")]
        public float wanderRadius = 2.2f;
        [Tooltip("Interval in seconds between autonomous navigation decisions.")]
        public float wanderInterval = 16f;

        private float _nextWanderTime = 5f;
        private Vector3 _homePosition;

        private void Awake()
        {
            _agent = GetComponent<NavMeshAgent>();
            if (_agent != null)
            {
                _agent.speed = 0.85f;
                _agent.angularSpeed = 140f;
                _agent.acceleration = 2.5f;
                _agent.stoppingDistance = 0.4f;
                _agent.radius = 0.25f;
                _agent.height = 1.6f;
            }

            if (wsClient == null)
            {
                wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            }

            _homePosition = transform.position;
            _nextWanderTime = Time.time + 8f;
        }

        private void Update()
        {
            if (!autonomousWander || _agent == null || !_agent.isActiveAndEnabled || !_agent.isOnNavMesh)
                return;

            if (Time.time >= _nextWanderTime)
            {
                _nextWanderTime = Time.time + wanderInterval + UnityEngine.Random.Range(-3f, 5f);
                WanderNearby();
            }
        }

        /// <summary>
        /// Sample a random reachable position on the scanned Quest room mesh and navigate there.
        /// </summary>
        public void WanderNearby()
        {
            if (_agent == null || !_agent.isActiveAndEnabled || !_agent.isOnNavMesh) return;

            Vector3 origin = _homePosition;
            Camera cam = Camera.main;
            if (cam != null)
            {
                // Wander near user, keeping at least 1.2m social distance
                origin = cam.transform.position;
            }

            Vector2 randomCircle = UnityEngine.Random.insideUnitCircle * wanderRadius;
            Vector3 randomTarget = origin + new Vector3(randomCircle.x, 0, randomCircle.y);

            NavMeshHit hit;
            if (NavMesh.SamplePosition(randomTarget, out hit, wanderRadius, NavMesh.AllAreas))
            {
                // Ensure not too close to the user's face
                if (cam != null && Vector3.Distance(hit.position, cam.transform.position) < 1.0f)
                {
                    return;
                }

                _agent.SetDestination(hit.position);
                Debug.Log($"[AvatarMovement] Autonomous wander to room mesh point: {hit.position}");
            }
        }

        private void OnEnable()
        {
            if (wsClient != null)
            {
                wsClient.OnRawMessageReceived += HandleMessage;
            }
        }

        private void OnDisable()
        {
            if (wsClient != null)
            {
                wsClient.OnRawMessageReceived -= HandleMessage;
            }
        }

        private void HandleMessage(string message)
        {
            // Parse event type
            string eventType = ExtractStringField(message, "event");
            if (string.IsNullOrEmpty(eventType) || eventType != "motor.walkTo")
            {
                return;
            }

            string payloadStr = ExtractStringField(message, "payload", true);
            if (!string.IsNullOrEmpty(payloadStr))
            {
                try
                {
                    WalkToPayload payload = JsonUtility.FromJson<WalkToPayload>(payloadStr);
                    Vector3 destination = new Vector3(payload.x, payload.y, payload.z);
                    
                    Debug.Log($"[AvatarMovement] Navigating to: {destination}");
                    _agent.SetDestination(destination);
                }
                catch (Exception e)
                {
                    Debug.LogError($"[AvatarMovement] Failed to parse walkTo payload: {e.Message}");
                }
            }
        }

        private string ExtractStringField(string json, string fieldName, bool isObject = false)
        {
            string search = "\"" + fieldName + "\":";
            int idx = json.IndexOf(search);
            if (idx == -1) return null;

            int valStart = idx + search.Length;
            // Skip spaces
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
                            if (openCount == 0)
                            {
                                return json.Substring(valStart, i - valStart + 1);
                            }
                        }
                    }
                }
                return null;
            }

            if (json[valStart] == '"')
            {
                valStart++;
                int valEnd = json.IndexOf("\"", valStart);
                if (valEnd != -1)
                {
                    return json.Substring(valStart, valEnd - valStart);
                }
            }
            return null;
        }
    }
}
