using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using FoveAI.IPC;

namespace FoveAI.UI
{
    public class AIContextVisualizer : MonoBehaviour
    {
        [Header("Dependencies")]
        public FoveAIWebSocketClient wsClient;

        private GameObject _visualizerCanvas;
        private List<GameObject> _stars = new List<GameObject>();

        [Serializable]
        private class StarPayload
        {
            public string hash;
            public int grade; // 1 to 10
            public string summary;
        }

        private void Awake()
        {
            if (wsClient == null)
            {
                wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            }

            CreateCanvas();
        }

        private void CreateCanvas()
        {
            _visualizerCanvas = new GameObject("AIContextVisualizerCanvas");
            _visualizerCanvas.transform.SetParent(this.transform, false);
            _visualizerCanvas.transform.localPosition = new Vector3(0, 1.2f, 2.0f); // Floating higher up

            Canvas canvas = _visualizerCanvas.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            _visualizerCanvas.GetComponent<RectTransform>().sizeDelta = new Vector2(800, 400);
            _visualizerCanvas.transform.localScale = Vector3.one * 0.002f;
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
            string eventType = ExtractStringField(message, "event");
            if (eventType == "foveated.star" || eventType == "memory.compress_star")
            {
                string payloadStr = ExtractStringField(message, "payload", true);
                if (!string.IsNullOrEmpty(payloadStr))
                {
                    try
                    {
                        StarPayload payload = JsonUtility.FromJson<StarPayload>(payloadStr);
                        SpawnStar(payload);
                    }
                    catch (Exception e)
                    {
                        Debug.LogError($"[AIContextVisualizer] Failed to parse star payload: {e.Message}");
                    }
                }
            }
        }

        private void SpawnStar(StarPayload data)
        {
            GameObject starObj = new GameObject($"Star_{data.hash}");
            starObj.transform.SetParent(_visualizerCanvas.transform, false);

            // Random position within the canvas
            RectTransform rect = starObj.AddComponent<RectTransform>();
            rect.sizeDelta = new Vector2(20, 20);
            rect.localPosition = new Vector3(UnityEngine.Random.Range(-350f, 350f), UnityEngine.Random.Range(-150f, 150f), 0);

            Image img = starObj.AddComponent<Image>();
            img.color = GetColorForGrade(data.grade);

            _stars.Add(starObj);

            // Ensure we don't have too many stars cluttering the HUD
            if (_stars.Count > 50)
            {
                Destroy(_stars[0]);
                _stars.RemoveAt(0);
            }
        }

        private Color GetColorForGrade(int grade)
        {
            // 1 = Dim Blue/White, 10 = Bright Amber/Gold
            float t = Mathf.Clamp01((float)(grade - 1) / 9f);
            return Color.Lerp(new Color(0.6f, 0.8f, 1.0f, 0.5f), new Color(1.0f, 0.8f, 0.2f, 1.0f), t);
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
