using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;
using FoveAI.Config;

namespace Lumax.Quest3Bridge
{
    [System.Serializable]
    public class XRLFMessage
    {
        public string role;
        public string content;
    }

    [System.Serializable]
    public class XRLFPayload
    {
        public string model = "foveated-proxy";
        public List<XRLFMessage> messages;
        public float temperature = 0.7f;
    }

    [System.Serializable]
    public class XRLFResponseChoice
    {
        public XRLFMessage message;
    }

    [System.Serializable]
    public class XRLFResponse
    {
        public List<XRLFResponseChoice> choices;
    }

    /// <summary>
    /// Bypasses the soul_core.py middleware entirely.
    /// Talks directly to the XRLF model or Foveated Proxy via REST.
    /// Manages its own conversation history locally in the headset.
    /// </summary>
    public class DirectXRLFClient : MonoBehaviour
    {
        [Header("Connection")]
        [Tooltip("8402 = XRLF inference runtime (/v1/chat/completions); 8400 = foveated-memory proxy")]
        public int targetPort = 8402;

        [Header("Context")]
        [Tooltip("System prompt injected as the first message.")]
        [TextArea(3, 5)]
        public string systemPrompt = "You are a spatial AI avatar. Output [GESTURE: \"wave\"] or [EMOTION: \"happy\"] tags natively in your responses.";

        public event Action<string> OnChatTextReceived;
        public event Action OnRequestStarted;
        public event Action OnRequestFinished;

        private List<XRLFMessage> _history = new List<XRLFMessage>();
        private string _serverUrl;

        private void Start()
        {
            if (ConfigLoader.Settings == null)
            {
                _ = ConfigLoader.LoadConfigAsync();
            }

            string ip = ConfigLoader.Settings != null ? ConfigLoader.Settings.serverIp : "192.168.8.109";
            _serverUrl = $"http://{ip}:{targetPort}/v1/chat/completions";
            Debug.Log($"[DirectXRLFClient] Initialized routing to: {_serverUrl}");

            // Inject System Prompt
            _history.Add(new XRLFMessage { role = "system", content = systemPrompt });
        }

        public async void SendPromptAsync(string userText)
        {
            if (string.IsNullOrWhiteSpace(userText)) return;

            Debug.Log($"[DirectXRLFClient] Sending prompt: {userText}");
            _history.Add(new XRLFMessage { role = "user", content = userText });

            OnRequestStarted?.Invoke();

            XRLFPayload payload = new XRLFPayload
            {
                messages = _history
            };

            string jsonBody = JsonUtility.ToJson(payload);

            using (UnityWebRequest request = new UnityWebRequest(_serverUrl, "POST"))
            {
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonBody);
                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                // Optional: Authorization header if required by the proxy for Agent Identification
                request.SetRequestHeader("Authorization", "Bearer lumax_spatial_client");

                var operation = request.SendWebRequest();

                while (!operation.isDone)
                {
                    await Task.Yield();
                }

                if (request.result == UnityWebRequest.Result.Success)
                {
                    string responseJson = request.downloadHandler.text;
                    try
                    {
                        var responseData = JsonUtility.FromJson<XRLFResponse>(responseJson);
                        if (responseData.choices != null && responseData.choices.Count > 0)
                        {
                            string aiText = responseData.choices[0].message.content;
                            Debug.Log($"[DirectXRLFClient] Received AI Response: {aiText}");
                            
                            // Save to history
                            _history.Add(new XRLFMessage { role = "assistant", content = aiText });

                            // Fire event for CognitiveRouter and TTS to pick up
                            OnChatTextReceived?.Invoke(aiText);
                        }
                    }
                    catch (Exception ex)
                    {
                        Debug.LogError($"[DirectXRLFClient] Parse Error: {ex.Message}\nRaw: {responseJson}");
                    }
                }
                else
                {
                    Debug.LogError($"[DirectXRLFClient] HTTP Error: {request.error}\nURL: {_serverUrl}");
                }
            }

            OnRequestFinished?.Invoke();
        }

        /// <summary>
        /// Clears the headset's local conversation history.
        /// </summary>
        public void ClearHistory()
        {
            _history.Clear();
            _history.Add(new XRLFMessage { role = "system", content = systemPrompt });
            Debug.Log("[DirectXRLFClient] History cleared.");
        }
    }
}
