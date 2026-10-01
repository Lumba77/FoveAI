using UnityEngine;
using System;
using System.Collections;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

public class WonderPedalTracker : MonoBehaviour
{
    [Header("Bridge Configuration")]
    [Tooltip("IP Address of the PC running paradiddle_bridge.py")]
    public string pcBridgeIp = "192.168.1.100"; // CHANGE THIS to your PC's IP
    public int wsPort = 9006;

    [Header("Tracking Settings")]
    [Tooltip("The Transform representing the tracked foot (e.g., from Meta Movement SDK Leg Tracking)")]
    public Transform trackedFoot;
    
    [Tooltip("Height threshold below which a kick is triggered")]
    public float kickThreshold = 0.05f;
    
    [Tooltip("Cooldown in seconds between triggers to prevent double-kicks")]
    public float triggerCooldown = 0.15f;

    private float lastKickTime = 0f;
    private bool isFootDown = false;
    private ClientWebSocket webSocket;

    private float lastFootHeight;

    async void Start()
    {
        if (trackedFoot == null)
        {
            Debug.LogWarning("Wonder Pedal: No tracked foot assigned. Please assign a foot bone from the Meta Movement SDK.");
        }
        else
        {
            lastFootHeight = trackedFoot.position.y;
        }

        await ConnectToBridge();
    }

    async Task ConnectToBridge()
    {
        string wsUri = $"ws://{pcBridgeIp}:{wsPort}";
        webSocket = new ClientWebSocket();
        
        try
        {
            Debug.Log($"Connecting to Wonder Pedal Bridge at {wsUri}...");
            await webSocket.ConnectAsync(new Uri(wsUri), CancellationToken.None);
            Debug.Log("Connected successfully to Wonder Pedal Bridge!");
            
            // Start listening loop
            _ = ReceiveLoop();
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to connect to bridge: {e.Message}");
        }
    }

    void Update()
    {
        if (trackedFoot == null || webSocket == null || webSocket.State != WebSocketState.Open)
            return;

        float footHeight = trackedFoot.position.y;
        
        // Calculate downward velocity (meters per second)
        float velocityY = (lastFootHeight - footHeight) / Time.deltaTime; 

        // Check if foot crosses threshold downwards
        if (footHeight < kickThreshold && !isFootDown)
        {
            isFootDown = true;
            
            if (Time.time - lastKickTime > triggerCooldown)
            {
                // Map the physical downward velocity (e.g., 0.05 m/s to 0.15 m/s) to MIDI velocity (0 to 127)
                float minVelocity = 0.05f;
                float maxVelocity = 0.15f;
                float clampedVelocity = Mathf.Clamp(velocityY, minVelocity, maxVelocity);
                
                // Calculate gradient (0.0 to 1.0)
                float normalizedGradient = (clampedVelocity - minVelocity) / (maxVelocity - minVelocity);
                
                // Convert to MIDI velocity (0-127)
                int midiVelocity = Mathf.RoundToInt(Mathf.Lerp(30, 127, normalizedGradient));

                TriggerDrum("kick", midiVelocity);
                lastKickTime = Time.time;
            }
        }
        else if (footHeight >= kickThreshold)
        {
            isFootDown = false;
        }
        
        lastFootHeight = footHeight;
    }

    async void TriggerDrum(string type, int velocity)
    {
        if (webSocket.State == WebSocketState.Open)
        {
            string jsonMessage = $"{{\"trigger\": \"{type}\", \"velocity\": {velocity}}}";
            byte[] bytes = Encoding.UTF8.GetBytes(jsonMessage);
            await webSocket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None);
            Debug.Log($"Sent {type} trigger with MIDI velocity {velocity}.");
        }
    }

    async Task ReceiveLoop()
    {
        byte[] buffer = new byte[1024];
        while (webSocket.State == WebSocketState.Open)
        {
            var result = await webSocket.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
            if (result.MessageType == WebSocketMessageType.Close)
            {
                await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, string.Empty, CancellationToken.None);
            }
            else
            {
                string message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                Debug.Log($"Received from bridge: {message}");
            }
        }
    }

    async void OnApplicationQuit()
    {
        if (webSocket != null && webSocket.State == WebSocketState.Open)
        {
            await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "App closing", CancellationToken.None);
        }
    }
}
