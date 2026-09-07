using UnityEngine;
using System.Net.Sockets;
using System.Text;
using System;
using FoveAI.Config;

namespace FoveAI.IPC
{
    /// <summary>
    /// Sends a Wake-On-LAN style UDP packet to the PC backend on startup.
    /// Triggers the wake_listener.py script to boot up the Spatial Machine stack.
    /// </summary>
    public class BackendWakeClient : MonoBehaviour
    {
        [Tooltip("The UDP Port configured in the PC's wake_listener.py")]
        public int wakePort = 9999;
        
        [Tooltip("The wake profile to trigger (e.g. WAKE_SPATIAL, WAKE_FULL)")]
        public string wakeCommand = "WAKE_SPATIAL";

        private void Start()
        {
            // Read the PC's IP address dynamically from the ConfigLoader
            if (ConfigLoader.Settings == null)
            {
                _ = ConfigLoader.LoadConfigAsync();
                Debug.LogWarning("[BackendWakeClient] Config not loaded yet. Wake signal might fail if IP is not default.");
            }
            
            string targetIp = ConfigLoader.Settings.serverIp;
            if (string.IsNullOrEmpty(targetIp) || targetIp == "127.0.0.1")
            {
                Debug.LogWarning("[BackendWakeClient] Invalid PC IP address configured. Cannot send wake signal.");
                return;
            }

            SendWakeSignal(targetIp);
        }

        private void SendWakeSignal(string ipAddress)
        {
            UdpClient udpClient = new UdpClient();
            try
            {
                byte[] data = Encoding.UTF8.GetBytes(wakeCommand);
                udpClient.Send(data, data.Length, ipAddress, wakePort);
                Debug.Log($"[BackendWakeClient] Sent '{wakeCommand}' to {ipAddress}:{wakePort}");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[BackendWakeClient] Failed to send wake signal: {ex.Message}");
            }
            finally
            {
                udpClient.Close();
            }
        }
    }
}
