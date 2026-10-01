using UnityEngine;
using System;
using System.Collections;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

public class WonderPedalTracker : MonoBehaviour
{
    public enum PedalMode
    {
        KickDrum,           // Sends MIDI Note 36
        HiHat_Trigger,      // Sends MIDI Note 42
        HiHat_Continuous_CC, // Sends MIDI CC 4
        Hybrid_Spatial_LeftLeg // Dynamically switches based on X-axis (inward = Kick, outward = HiHat)
    }

    [Header("Bridge Configuration")]
    public string pcBridgeIp = "192.168.1.100";
    public int wsPort = 9006;

    [Header("Tracking Settings")]
    public PedalMode mode = PedalMode.KickDrum;
    public Transform trackedFoot;
    public float triggerCooldown = 0.15f;

    [Header("Hybrid Spatial Settings")]
    [Tooltip("The X-axis position that divides the virtual pedals. Outward (left) = HiHat, Inward (right) = Kick")]
    public float horizontalSwitchThreshold = -0.1f; // Negative X is typically left of center

    [Header("Thump Settings (For Kick/HiHat Trigger)")]
    public float minVelocity = 0.05f;
    public float kickThreshold = 0.05f;
    private float currentMaxVelocity = 0.15f; 

    [Header("Continuous Settings (For HiHat CC)")]
    public float lowestKneeHeight = 0.4f;   
    public float highestKneeHeight = 0.55f; 

    private float lastKickTime = 0f;
    private bool isFootDown = false;
    private float lastFootHeight;

    // WebSocket state
    private ClientWebSocket webSocket;
    private static ClientWebSocket sharedWebSocket; 

    async void Start()
    {
        if (trackedFoot != null)
            lastFootHeight = trackedFoot.position.y;

        if (sharedWebSocket == null || sharedWebSocket.State != WebSocketState.Open)
        {
            await ConnectToBridge();
        }
        else
        {
            webSocket = sharedWebSocket;
        }
    }

    async Task ConnectToBridge()
    {
        string wsUri = $"ws://{pcBridgeIp}:{wsPort}";
        sharedWebSocket = new ClientWebSocket();
        webSocket = sharedWebSocket;
        
        try
        {
            await webSocket.ConnectAsync(new Uri(wsUri), CancellationToken.None);
            Debug.Log("Connected to Wonder Pedal Bridge!");
            _ = ReceiveLoop();
        }
        catch (Exception e)
        {
            Debug.LogError($"Bridge connection failed: {e.Message}");
        }
    }

    void Update()
    {
        if (trackedFoot == null || webSocket == null || webSocket.State != WebSocketState.Open) return;

        float footHeight = trackedFoot.position.y;
        float footX = trackedFoot.localPosition.x; // Horizontal position relative to rig

        if (mode == PedalMode.Hybrid_Spatial_LeftLeg)
        {
            // Dynamic switching based on knee angling!
            if (footX < horizontalSwitchThreshold)
            {
                // Outward (Left) -> Hi-Hat Mode
                ProcessContinuousHiHat(footHeight);
            }
            else
            {
                // Inward (Right) -> Double Bass Mode
                ProcessHitTrigger(footHeight, isKick: true);
            }
        }
        else if (mode == PedalMode.HiHat_Continuous_CC)
        {
            ProcessContinuousHiHat(footHeight);
        }
        else
        {
            bool isKick = (mode == PedalMode.KickDrum);
            ProcessHitTrigger(footHeight, isKick);
        }
        
        lastFootHeight = footHeight;
    }

    void ProcessContinuousHiHat(float footHeight)
    {
        // Calculate where the knee is between lowest (closed) and highest (open)
        float normalizedHeight = Mathf.InverseLerp(lowestKneeHeight, highestKneeHeight, footHeight);
        
        // Convert to MIDI CC 4 (127 = closed at bottom, 0 = open at top)
        int ccValue = Mathf.RoundToInt(Mathf.Lerp(127, 0, normalizedHeight));
        
        // Send continuously (ideally we would only send when value changes to save bandwidth)
        SendMidi("cc", 4, ccValue);
    }

    void ProcessHitTrigger(float footHeight, bool isKick)
    {
        float velocityY = (lastFootHeight - footHeight) / Time.deltaTime; 
        currentMaxVelocity = Mathf.Max(0.15f, currentMaxVelocity - (0.01f * Time.deltaTime)); // Slow decay

        if (footHeight < kickThreshold && !isFootDown)
        {
            isFootDown = true;
            if (Time.time - lastKickTime > triggerCooldown)
            {
                if (velocityY > currentMaxVelocity) currentMaxVelocity = Mathf.Min(velocityY, 3.5f);

                float clampedVelocity = Mathf.Clamp(velocityY, minVelocity, currentMaxVelocity);
                float normalizedGradient = (clampedVelocity - minVelocity) / (currentMaxVelocity - minVelocity);
                int midiVelocity = Mathf.RoundToInt(Mathf.Lerp(30, 127, normalizedGradient));

                int note = isKick ? 36 : 42;
                SendMidi("note_on", note, midiVelocity);
                lastKickTime = Time.time;
            }
        }
        else if (footHeight >= kickThreshold)
        {
            isFootDown = false;
        }
    }

    async void SendMidi(string type, int identifier, int value)
    {
        if (webSocket.State == WebSocketState.Open)
        {
            // Example JSON: {"type": "note_on", "note": 36, "velocity": 127} or {"type": "cc", "cc": 4, "value": 64}
            string jsonMessage = type == "cc" 
                ? $"{{\"type\": \"cc\", \"cc\": {identifier}, \"value\": {value}}}"
                : $"{{\"type\": \"{type}\", \"note\": {identifier}, \"velocity\": {value}}}";
                
            byte[] bytes = Encoding.UTF8.GetBytes(jsonMessage);
            await webSocket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None);
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
        }
    }
}
