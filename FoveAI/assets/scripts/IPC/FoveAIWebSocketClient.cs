using System;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

namespace FoveAI.IPC
{
    /// <summary>
    /// Connects Quest 3 native APK to the FoveAI PC Backend via WebSocket.
    /// </summary>
    public class FoveAIWebSocketClient : MonoBehaviour
    {
        [SerializeField] private string serverUrl = "ws://192.168.1.100:8000";

        private void Start()
        {
            Debug.Log($"[FoveAI] Connecting to PC Backend at {serverUrl}...");
            // Connection initialization logic
        }

        public void SendEvent(string eventName, string jsonPayload)
        {
            Debug.Log($"[FoveAI] Sending event: {eventName}");
        }
    }
}
