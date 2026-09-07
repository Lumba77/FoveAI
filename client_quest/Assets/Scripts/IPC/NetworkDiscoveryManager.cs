using System;
using System.Collections;
using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEngine;
using UnityEngine.UI;
using FoveAI.Config;

// =============================================================================
//  NetworkDiscoveryManager
//  
//  Problem: Quest 3 cannot shell-exec Windows processes. The user has to manually
//  start the Python backends on their PC before launching the APK.
//
//  Solution:
//  1. On startup, try to connect to the FoveAI backend (ws://IP:8403)
//  2. If it fails, show an in-VR status panel: "Backend not running on PC"
//  3. Send a UDP broadcast on port 9999 — a PC-side wake_listener.py picks this
//     up and auto-starts all 3 backend services (main.py, stt, tts)
//  4. Retry connection every 5s, hide panel when connected
//
//  PC side: run Backend/wake_listener.py once (add to Windows startup if desired)
// =============================================================================

namespace FoveAI.IPC
{
    public class NetworkDiscoveryManager : MonoBehaviour
    {
        [Header("Backend Detection")]
        public string BackendHost = "192.168.8.100";
        public int    BackendPort = 8403;
        [Tooltip("UDP port that wake_listener.py on the PC listens on")]
        public int    WakePort    = 9999;
        public float  RetryEverySeconds = 5f;

        // -- In-VR status overlay --
        private GameObject _statusPanel;
        private Text       _statusText;
        private bool       _backendReachable = false;
        private bool       _checking         = false;

        private void Start()
        {
            if (ConfigLoader.Settings != null)
            {
                BackendPort = ConfigLoader.Settings.wsPort;
                BackendHost = ConfigLoader.Settings.serverIp;
            }
            BuildStatusPanel();
            StartCoroutine(CheckAndWakeLoop());
        }

        // =====================================================================
        //  Connection check + wake broadcast loop
        // =====================================================================
        private IEnumerator CheckAndWakeLoop()
        {
            while (!_backendReachable)
            {
                if (!_checking)
                {
                    _checking = true;
                    yield return StartCoroutine(CheckBackend());
                    _checking = false;
                }

                if (!_backendReachable)
                {
                    BackendPort = ConfigLoader.Settings != null ? ConfigLoader.Settings.wsPort : 8403;
                    // Show overlay and send UDP wake
                    ShowStatus("FoveAI WebSocket backend not detected at\n" +
                               $"{ConfigLoader.Settings.serverIp}:{BackendPort}\n\n" +
                               "Start wake_listener.py on your PC,\nor start the backend manually.\n\n" +
                               "Retrying in 5s...");

                    SendUdpWake();
                    yield return new WaitForSeconds(RetryEverySeconds);
                }
            }
        }

        private IEnumerator CheckBackend()
        {
            bool connected = false;
            bool done = false;

            // Try a raw TCP connect to verify the port is open
            System.Threading.Tasks.Task.Run(() =>
            {
                try
                {
                    using var client = new TcpClient();
                    client.ReceiveTimeout = 2000;
                    client.SendTimeout    = 2000;
                    var result = client.BeginConnect(ConfigLoader.Settings.serverIp, BackendPort, null, null);
                    connected  = result.AsyncWaitHandle.WaitOne(2000);
                }
                catch { connected = false; }
                finally { done = true; }
            });

            yield return new WaitUntil(() => done);

            if (connected)
            {
                _backendReachable = true;
                HideStatus();
                Debug.Log($"[NetworkDiscovery] Backend reachable at {ConfigLoader.Settings.serverIp}:{BackendPort}");
            }
        }

        private void SendUdpWake()
        {
            try
            {
                using var udp = new UdpClient();
                udp.EnableBroadcast = true;
                byte[] data = Encoding.UTF8.GetBytes("{\"cmd\":\"wake\",\"client\":\"AliceVR_Quest3\"}");
                // Broadcast to subnet
                udp.Send(data, data.Length, new IPEndPoint(IPAddress.Broadcast, WakePort));
                Debug.Log($"[NetworkDiscovery] UDP wake broadcast sent on port {WakePort}");
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[NetworkDiscovery] UDP broadcast failed: {ex.Message}");
            }
        }

        // =====================================================================
        //  In-VR Status Overlay (world-space canvas, always visible)
        // =====================================================================
        private void BuildStatusPanel()
        {
            _statusPanel = new GameObject("NetworkStatusPanel");
            _statusPanel.transform.SetParent(transform, false);

            // Float in front of the user at eye level
            _statusPanel.transform.localPosition = new Vector3(0, 1.5f, 2.5f);

            Canvas c = _statusPanel.AddComponent<Canvas>();
            c.renderMode = RenderMode.WorldSpace;
            _statusPanel.AddComponent<UnityEngine.UI.GraphicRaycaster>();

            RectTransform r = _statusPanel.GetComponent<RectTransform>();
            r.sizeDelta = new Vector2(800, 400);
            r.pivot     = new Vector2(0.5f, 0.5f);
            _statusPanel.transform.localScale = Vector3.one * 0.001f;

            var scaler = _statusPanel.AddComponent<UnityEngine.UI.CanvasScaler>();
            scaler.uiScaleMode = UnityEngine.UI.CanvasScaler.ScaleMode.ConstantPixelSize;
            scaler.scaleFactor = 1f;

            // Background
            var bg = _statusPanel.AddComponent<Image>();
            bg.color = new Color(0.05f, 0.05f, 0.1f, 0.92f);

            // Text
            GameObject txtGo = new GameObject("StatusText");
            txtGo.transform.SetParent(_statusPanel.transform, false);
            RectTransform tr = txtGo.AddComponent<RectTransform>();
            tr.anchorMin = Vector2.zero;
            tr.anchorMax = Vector2.one;
            tr.offsetMin = new Vector2(30, 30);
            tr.offsetMax = new Vector2(-30, -30);

            _statusText = txtGo.AddComponent<Text>();
            _statusText.font                 = Resources.GetBuiltinResource<Font>("Arial.ttf");
            _statusText.fontSize             = 32;
            _statusText.color                = new Color(1f, 0.7f, 0.2f, 1f); // amber warning
            _statusText.alignment            = TextAnchor.MiddleCenter;
            _statusText.resizeTextForBestFit = false;
            _statusText.text                 = "Checking backend...";

            _statusPanel.SetActive(false);
        }

        private void ShowStatus(string msg)
        {
            if (_statusText != null) _statusText.text = msg;
            if (_statusPanel != null) _statusPanel.SetActive(true);

            // Face the user
            if (Camera.main != null)
            {
                Vector3 dir = _statusPanel.transform.position - Camera.main.transform.position;
                dir.y = 0;
                if (dir.sqrMagnitude > 0.01f)
                    _statusPanel.transform.rotation = Quaternion.LookRotation(dir);
            }
        }

        private void HideStatus()
        {
            if (_statusPanel != null) _statusPanel.SetActive(false);
        }
    }
}
