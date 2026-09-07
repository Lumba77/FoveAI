using UnityEngine;
using UnityEngine.UI;
using System.Collections;
using UnityEngine.Networking;

namespace FoveAI.IPC
{
    /// <summary>
    /// Receives a video stream (MJPEG/Frames) from the user's phone web camera 
    /// via the Foveated Memory/Lumax backend, rendering it inside the Booth.
    /// </summary>
    public class WebcamReceiver : MonoBehaviour
    {
        public RawImage videoScreen;
        public string streamUrl;
        private Texture2D webcamTexture;

        async void Start()
        {
            await FoveAI.Config.ConfigLoader.LoadConfigAsync();
            var settings = FoveAI.Config.ConfigLoader.Settings;
            
            streamUrl = $"http://{settings.serverIp}:{settings.httpPort}/api/camera/stream";
            Debug.Log($"[WebcamReceiver] Loaded Eyes config URL: {streamUrl}");

            webcamTexture = new Texture2D(2, 2, TextureFormat.RGB24, false);
            if (videoScreen != null)
            {
                videoScreen.texture = webcamTexture;
            }
            StartCoroutine(ReceiveStream());
        }

        private IEnumerator ReceiveStream()
        {
            Debug.Log("[WebcamReceiver] Connecting to phone webcam stream at " + streamUrl);
            
            using (UnityWebRequest uwr = UnityWebRequest.Get(streamUrl))
            {
                uwr.downloadHandler = new WebcamStreamHandler(webcamTexture);
                yield return uwr.SendWebRequest();
                
                if (uwr.result != UnityWebRequest.Result.Success)
                {
                    Debug.LogWarning("[WebcamReceiver] Error receiving stream (is phone connected?): " + uwr.error);
                }
            }
        }
    }

    /// <summary>
    /// Custom DownloadHandler to intercept bytes and look for JPEG frames.
    /// Proof-of-concept for the Face-to-Face booth.
    /// </summary>
    public class WebcamStreamHandler : DownloadHandlerScript
    {
        private Texture2D targetTexture;
        private byte[] jpegBuffer = new byte[1024 * 1024]; // 1MB buffer
        private int bufferIndex = 0;

        public WebcamStreamHandler(Texture2D tex) : base(new byte[65536])
        {
            targetTexture = tex;
        }

        protected override bool ReceiveData(byte[] data, int dataLength)
        {
            if (data == null || dataLength == 0) return true;

            System.Buffer.BlockCopy(data, 0, jpegBuffer, bufferIndex, dataLength);
            bufferIndex += dataLength;

            // Simple heuristic: if buffer exceeds 50KB, attempt to load frame
            // In a production app, parse SOI/EOI markers for precise MJPEG extraction.
            if (bufferIndex > 50000) 
            {
                byte[] frame = new byte[bufferIndex];
                System.Buffer.BlockCopy(jpegBuffer, 0, frame, 0, bufferIndex);
                
                targetTexture.LoadImage(frame); 
                targetTexture.Apply();
                
                bufferIndex = 0; // Reset for next frame
            }

            return true;
        }
    }
}
