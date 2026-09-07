using UnityEngine;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using System;
using System.Collections.Concurrent;
using System.Text;
using FoveAI.Avatar;

namespace FoveAI.Audio
{
    [RequireComponent(typeof(AudioSource))]
    public class AvatarVoice : MonoBehaviour
    {
        [Tooltip("The TTS Server WebSocket URL")]
        public string websocketUrl = "ws://192.168.8.100:8401";
        public int sampleRate = 24000;
        
        private ClientWebSocket _ws;
        private AudioSource _audioSource;
        private ConcurrentQueue<float> _audioBuffer = new ConcurrentQueue<float>();
        
        private CancellationTokenSource _cts;

        async void Start()
        {
            await FoveAI.Config.ConfigLoader.LoadConfigAsync();
            var settings = FoveAI.Config.ConfigLoader.Settings;
            
            websocketUrl = $"ws://{settings.serverIp}:{settings.wsPort}";
            Debug.Log($"[AvatarVoice] Loaded TTS config URL: {websocketUrl}");

            _audioSource = GetComponent<AudioSource>();
            _audioSource.loop = true;
            // Create a procedural streaming AudioClip
            _audioSource.clip = AudioClip.Create("TTS_Stream", sampleRate * 2, 1, sampleRate, false);
            _audioSource.Play();
            
            _cts = new CancellationTokenSource();
            _ = ConnectAndReceiveAudio(_cts.Token);
        }

        async Task ConnectAndReceiveAudio(CancellationToken token)
        {
            while (!token.IsCancellationRequested)
            {
                try
                {
                    _ws = new ClientWebSocket();
                    await _ws.ConnectAsync(new Uri(websocketUrl), token);
                    Debug.Log("[LibrarianSpeaker] Connected to TTS WebSocket!");

                    byte[] buffer = new byte[8192];
                    while (_ws.State == WebSocketState.Open && !token.IsCancellationRequested)
                    {
                        var result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), token);
                        if (result.MessageType == WebSocketMessageType.Binary)
                        {
                            // Convert 16-bit PCM (Little Endian) bytes to floats [-1f, 1f]
                            for (int i = 0; i < result.Count; i += 2)
                            {
                                short sample = BitConverter.ToInt16(buffer, i);
                                _audioBuffer.Enqueue(sample / 32768f);
                            }
                        }
                    }
                }
                catch (Exception e)
                {
                    if (!token.IsCancellationRequested)
                    {
                        Debug.LogWarning($"[LibrarianSpeaker] WS Error: {e.Message}. Retrying in 2s...");
                        await Task.Delay(2000, token);
                    }
                }
            }
        }

        /// <summary>
        /// Call this method from the Cognitive Engine / FoveAIWebSocketClient to trigger TTS!
        /// </summary>
        public async void Speak(string text)
        {
            if (_ws != null && _ws.State == WebSocketState.Open)
            {
                // Note: The python server handles "voice" defaults natively
                string json = $"{{\"text\": \"{text}\"}}";
                byte[] bytes = Encoding.UTF8.GetBytes(json);
                await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
                Debug.Log($"[LibrarianSpeaker] Sent TTS request: {text}");
            }
            else
            {
                Debug.LogWarning("[LibrarianSpeaker] Cannot speak, TTS WebSocket is disconnected.");
            }
        }

        private float _currentRms = 0f;
        private float _targetMouthOpen = 0f;
        private float _smoothedMouthOpen = 0f;
        private FoveAI.Avatar.AvatarBlendshapeDriver _blendshapeDriver;

        /// <summary>True if the avatar is currently speaking audio (for VAD echo suppression).</summary>
        public bool IsSpeaking => _smoothedMouthOpen > 0.05f;

        private void Update()
        {
            if (_blendshapeDriver == null)
            {
                _blendshapeDriver = GetComponent<FoveAI.Avatar.AvatarBlendshapeDriver>() ?? GetComponentInParent<FoveAI.Avatar.AvatarBlendshapeDriver>() ?? GetComponentInChildren<FoveAI.Avatar.AvatarBlendshapeDriver>();
            }

            if (_blendshapeDriver != null)
            {
                _targetMouthOpen = Mathf.Clamp01(_currentRms * 14f);
                _smoothedMouthOpen = Mathf.Lerp(_smoothedMouthOpen, _targetMouthOpen, Time.deltaTime * 18f);

                if (_smoothedMouthOpen > 0.02f)
                {
                    _blendshapeDriver.SetVisemeWeight("a", _smoothedMouthOpen);
                }
                else
                {
                    _blendshapeDriver.SetVisemeWeight("a", 0f);
                }
            }
        }

        void OnAudioFilterRead(float[] data, int channels)
        {
            float sum = 0f;
            int count = 0;

            for (int i = 0; i < data.Length; i += channels)
            {
                if (_audioBuffer.TryDequeue(out float sample))
                {
                    for (int c = 0; c < channels; c++)
                    {
                        data[i + c] = sample;
                    }
                    sum += sample * sample;
                    count++;
                }
                else
                {
                    for (int c = 0; c < channels; c++)
                    {
                        data[i + c] = 0f;
                    }
                }
            }

            _currentRms = count > 0 ? Mathf.Sqrt(sum / count) : 0f;
        }

        void OnDestroy()
        {
            _cts?.Cancel();
            _ws?.Dispose();
        }
    }
}
