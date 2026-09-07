using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;
using System.Net.WebSockets;
using System.Threading;
using System.Text;
using System.Threading.Tasks;

namespace FoveAI.Senses
{
    [Serializable]
    public class VisionPayload
    {
        public string event_type;
        public string image_base64;
        public string perspective; // "user" or "avatar"
        public string direction; // "North", "South", "East", "West", "Up", "Down"
    }

    /// <summary>
    /// Grabs a frame from the designated camera (User or Avatar) 
    /// and sends it to the FoveAI Backend for analysis.
    /// </summary>
    public class VisionGrabber : MonoBehaviour
    {
        [Header("References")]
        [Tooltip("The main websocket client to send the image to.")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        
        [Tooltip("The camera representing the user's eyes (Main Camera)")]
        public Camera userCamera;
        
        [Tooltip("The camera representing the avatar's eyes (e.g. attached to her head bone)")]
        public Camera avatarCamera;

        [Header("Settings")]
        [Tooltip("Controller button to take a photo from User perspective (Default: Right B / Button Two)")]
        public OVRInput.Button takeUserPhotoButton = OVRInput.Button.Two;

        [Tooltip("Controller button to take a photo from Avatar perspective (Default: Left Y / Button Four)")]
        public OVRInput.Button takeAvatarPhotoButton = OVRInput.Button.Four;

        [Tooltip("Resolution to downsample the image for faster inference")]
        public int imageWidth = 512;
        public int imageHeight = 512;

        [Header("Continuous Vision")]
        public bool enableContinuousVision = false;
        [Tooltip("Seconds between frames in continuous mode")]
        public float captureInterval = 3.0f;

        private bool _isGrabbing = false;
        private Coroutine _continuousRoutine;

        private void OnEnable()
        {
            if (enableContinuousVision)
            {
                _continuousRoutine = StartCoroutine(ContinuousCaptureLoop());
            }
        }

        private void OnDisable()
        {
            if (_continuousRoutine != null)
            {
                StopCoroutine(_continuousRoutine);
                _continuousRoutine = null;
            }
        }

        private IEnumerator ContinuousCaptureLoop()
        {
            while (true)
            {
                yield return new WaitForSeconds(captureInterval);
                if (!_isGrabbing && userCamera != null)
                {
                    StartCoroutine(GrabFrameAndSend(userCamera, "user"));
                }
            }
        }

        private void Update()
        {
            if (wsClient == null)
            {
                wsClient = FindAnyObjectByType<FoveAIWebSocketClient>();
            }

            // Right B button -> User perspective snapshot (What you see)
            if (OVRInput.GetDown(takeUserPhotoButton))
            {
                if (!_isGrabbing && userCamera != null)
                {
                    StartCoroutine(GrabFrameAndSend(userCamera, "user"));
                }
            }

            // Left Y button -> Avatar perspective snapshot (What Alice sees from her head camera)
            if (OVRInput.GetDown(takeAvatarPhotoButton))
            {
                if (!_isGrabbing && avatarCamera != null)
                {
                    StartCoroutine(GrabFrameAndSend(avatarCamera, "avatar"));
                }
                else if (avatarCamera == null)
                {
                    FoveAI.DebugOverlay.QuestDebugOverlay.LogWarning("[Vision] Alice head camera not attached yet");
                }
            }
        }

        /// <summary>
        /// Public method to allow the backend to request a photo from the avatar's perspective.
        /// </summary>
        public void TakeAvatarPhoto()
        {
            if (!_isGrabbing && avatarCamera != null)
            {
                StartCoroutine(GrabFrameAndSend(avatarCamera, "avatar"));
            }
        }

        private IEnumerator GrabFrameAndSend(Camera cam, string perspective)
        {
            _isGrabbing = true;
            string label = perspective == "avatar" ? "Alice's Eyes" : "User View";
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"📸 Shutter: Captured {label} photo!");
            Debug.Log($"[VisionGrabber] Taking photo from {perspective} perspective ({label})...");

            // Haptic shutter click feedback
            var hapticController = perspective == "user" ? OVRInput.Controller.RTouch : OVRInput.Controller.LTouch;
            OVRInput.SetControllerVibration(0.6f, 0.6f, hapticController);

            // Create a render texture and render the camera to it
            RenderTexture rt = new RenderTexture(imageWidth, imageHeight, 24);
            var oldTarget = cam.targetTexture;
            var oldActive = RenderTexture.active;

            cam.targetTexture = rt;
            cam.Render();

            RenderTexture.active = rt;
            Texture2D tex = new Texture2D(imageWidth, imageHeight, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, imageWidth, imageHeight), 0, 0);
            tex.Apply();

            // Restore camera target
            cam.targetTexture = oldTarget;
            RenderTexture.active = oldActive;
            Destroy(rt);

            // Stop haptics after short shutter impulse
            yield return new WaitForSeconds(0.08f);
            OVRInput.SetControllerVibration(0f, 0f, hapticController);

            // Encode to JPG
            byte[] jpgBytes = tex.EncodeToJPG(75);
            Destroy(tex);

            string base64 = Convert.ToBase64String(jpgBytes);
            Debug.Log($"[VisionGrabber] Captured {jpgBytes.Length} bytes. Sending to backend...");

            // Calculate direction based on camera forward vector
            string CalculateDirection(Vector3 forward)
            {
                // Prioritize Up/Down if pitch is steep
                if (forward.y > 0.7f) return "Up";
                if (forward.y < -0.7f) return "Down";
                
                // Map the forward vector to the closest cardinal direction on the XZ plane
                forward.y = 0;
                forward.Normalize();
                
                // Assuming world Z is North, X is East
                float dotNorth = Vector3.Dot(forward, Vector3.forward);
                float dotSouth = Vector3.Dot(forward, Vector3.back);
                float dotEast = Vector3.Dot(forward, Vector3.right);
                float dotWest = Vector3.Dot(forward, Vector3.left);
                
                float maxDot = Mathf.Max(dotNorth, dotSouth, dotEast, dotWest);
                if (maxDot == dotNorth) return "North";
                if (maxDot == dotSouth) return "South";
                if (maxDot == dotEast) return "East";
                return "West";
            }
            
            string calculatedDirection = CalculateDirection(cam.transform.forward);

            // Send via WS using the proper event type (vision.frame)
            VisionPayload payload = new VisionPayload
            {
                event_type = "image",
                image_base64 = base64,
                perspective = perspective,
                direction = calculatedDirection
            };

            string json = JsonUtility.ToJson(payload);
            if (wsClient != null)
            {
                // Send the vision frame — the backend handles it and sends back
                // a chat.response with the description. No separate chat message needed.
                wsClient.SendEvent("vision.frame", json);
            }

            // Also POST the image to the plaster endpoint for spatial memory
            using (UnityEngine.Networking.UnityWebRequest www = new UnityEngine.Networking.UnityWebRequest("http://192.168.8.100:8402/api/environment/plaster_texture", "POST"))
            {
                byte[] jsonToSend = new System.Text.UTF8Encoding().GetBytes(json);
                www.uploadHandler = new UnityEngine.Networking.UploadHandlerRaw(jsonToSend);
                www.downloadHandler = new UnityEngine.Networking.DownloadHandlerBuffer();
                www.SetRequestHeader("Content-Type", "application/json");

                yield return www.SendWebRequest();

                if (www.result != UnityEngine.Networking.UnityWebRequest.Result.Success)
                {
                    Debug.LogError($"[VisionGrabber] Plaster upload failed: {www.error}");
                }
                else
                {
                    Debug.Log($"[VisionGrabber] Plaster upload success: {www.downloadHandler.text}");
                }
            }

            _isGrabbing = false;
            yield return null;
        }
    }
}
