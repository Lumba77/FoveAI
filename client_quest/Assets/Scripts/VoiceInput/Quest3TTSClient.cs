using System;
using System.Collections.Concurrent;
using System.Text;
using UnityEngine;
using NativeWebSocket;

namespace Lumax.Quest3Bridge
{
    [RequireComponent(typeof(AudioSource))]
    public class Quest3TTSClient : MonoBehaviour
    {
        [Header("WebSocket Connection")]
        [Tooltip("WebSocket URL of the unified WS server. Overridden by AppConfig.json at startup.")]
        public string TtsServerUrl = "ws://192.168.8.100:8403/ws";

        [Header("TTS Settings")]
        public string DefaultVoice = "af_bella";
        [Range(0.5f, 2.0f)]
        public float DefaultSpeed = 1.0f;

        [Header("Audio Playback")]
        public int ServerSampleRate = 24000;
        public float BufferSeconds = 5.0f;

        [Header("Lip-Sync")]
        public bool EnableLipSync = true;
        [Range(0f, 0.99f)]
        public float VisemeSmoothing = 0.7f;
        public float AmplitudeThreshold = 0.01f;
        
        [Tooltip("Reference to the VRM Blendshape proxy or Animator to receive Visemes")]
        public GameObject AvatarRoot;

        public const int VISEME_COUNT = 15;

        public event Action OnTTSConnected;
        public event Action<string> OnTTSError;
        public event Action OnTTSStart;
        public event Action<int> OnTTSEnd;

        private WebSocket _ws;
        private AudioSource _audioSource;
        private bool _isConnected;

        private AudioClip _streamClip;
        private float[] _streamBuffer;
        private int _streamBufferSize;
        private int _writePos;
        private bool _isPlaying;

        private readonly ConcurrentQueue<float[]> _audioQueue = new ConcurrentQueue<float[]>();
        private readonly float[] _currentVisemes = new float[VISEME_COUNT];
        private readonly float[] _targetVisemes = new float[VISEME_COUNT];

        private float _currentAmplitude;
        private float _smoothedAmplitude;

        private void Awake()
        {
            _audioSource = GetComponent<AudioSource>();
            _audioSource.loop = true;
            _audioSource.playOnAwake = false;

            _streamBufferSize = Mathf.CeilToInt(ServerSampleRate * BufferSeconds);
            _streamBuffer = new float[_streamBufferSize];
            _streamClip = AudioClip.Create("TTS_Stream", _streamBufferSize, 1, ServerSampleRate, false);
            _audioSource.clip = _streamClip;
        }

        private System.Action<string> _onChatTextReceived;

        private async void Start()
        {
            await FoveAI.Config.ConfigLoader.LoadConfigAsync();
            var settings = FoveAI.Config.ConfigLoader.Settings;
            TtsServerUrl = $"ws://{settings.serverIp}:{settings.wsPort}/ws";
            Debug.Log($"[Quest3TTSClient] Target TTS URL: {TtsServerUrl} (unified WebSocket)");
            
            // Auto connect
            await ConnectAsync();
            
            // Listen to FoveAI IPC for speech commands
            var ipcClient = FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            var cognitiveRouter = FindAnyObjectByType<CognitiveRouter>();
            if (ipcClient != null && cognitiveRouter == null)
            {
                _onChatTextReceived = text => Speak(text);
                ipcClient.OnChatTextReceived += _onChatTextReceived;
            }
        }

        private void OnDisable()
        {
            _ = DisconnectAsync();
            var ipcClient = FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            if (ipcClient != null && _onChatTextReceived != null)
            {
                ipcClient.OnChatTextReceived -= _onChatTextReceived;
            }
        }

        private void Update()
        {
            if (_ws != null)
            {
#if !UNITY_WEBGL || UNITY_EDITOR
                _ws.DispatchMessageQueue();
#endif
            }

            ProcessAudioQueue();

            if (EnableLipSync)
            {
                UpdateLipSync();
            }

            SmoothVisemes();
        }

        public void Speak(string text)
        {
            if (!_isConnected || _ws == null || _ws.State != WebSocketState.Open) return;
            if (string.IsNullOrEmpty(text)) return;

            string json = JsonUtility.ToJson(new SpeakRequest
            {
                type = "speak",
                text = text,
                voice = DefaultVoice,
                speed = DefaultSpeed
            });

            _ = _ws.SendText(json);
        }

        public void StopSpeaking()
        {
            if (_ws != null && _ws.State == WebSocketState.Open)
            {
                _ = _ws.SendText("{\"type\":\"stop\"}");
            }
            _isPlaying = false;
            while (_audioQueue.TryDequeue(out _)) { }
        }

        public async System.Threading.Tasks.Task ConnectAsync()
        {
            if (_ws != null && (_ws.State == WebSocketState.Open || _ws.State == WebSocketState.Connecting))
                return;

            try
            {
                _ws = new WebSocket(TtsServerUrl);
                _ws.OnOpen += OnWsOpen;
                _ws.OnMessage += OnWsMessage;
                _ws.OnError += OnWsError;
                _ws.OnClose += OnWsClose;

                await _ws.Connect();
            }
            catch (Exception ex)
            {
                OnTTSError?.Invoke($"connect: {ex.Message}");
            }
        }

        public async System.Threading.Tasks.Task DisconnectAsync()
        {
            _isPlaying = false;
            if (_ws != null && _ws.State == WebSocketState.Open)
            {
                try { await _ws.Close(); } catch { }
            }
        }

        private void OnWsOpen()
        {
            _ = _ws.SendText($"{{\"type\":\"config\",\"sample_rate\":{ServerSampleRate}}}");
        }

        private void OnWsMessage(byte[] data)
        {
            if (data.Length > 0 && data[0] == 0x7B) // '{'
            {
                string json = Encoding.UTF8.GetString(data);
                ParseServerMessage(json);
            }
            else
            {
                EnqueueAudioData(data);
            }
        }

        private void OnWsError(string errorMsg)
        {
            OnTTSError?.Invoke($"ws: {errorMsg}");
        }

        private void OnWsClose(WebSocketCloseCode code)
        {
            _isConnected = false;
            _isPlaying = false;
        }

        private void ParseServerMessage(string json)
        {
            try
            {
                var msg = JsonUtility.FromJson<TtsMessage>(json);
                if (msg == null) return;

                switch (msg.type)
                {
                    case "ready":
                        _isConnected = true;
                        OnTTSConnected?.Invoke();
                        break;
                    case "start":
                        _isPlaying = true;
                        if (msg.sample_rate > 0) ServerSampleRate = msg.sample_rate;
                        OnTTSStart?.Invoke();
                        break;
                    case "end":
                        _isPlaying = false;
                        OnTTSEnd?.Invoke(msg.duration_ms);
                        break;
                    case "error":
                        OnTTSError?.Invoke(msg.message ?? "unknown");
                        break;
                }
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[TTS] Failed to parse message: {ex.Message}");
            }
        }

        private void EnqueueAudioData(byte[] pcmBytes)
        {
            if (pcmBytes.Length < 2) return;
            int sampleCount = pcmBytes.Length / 2;
            float[] samples = new float[sampleCount];

            for (int i = 0; i < sampleCount; i++)
            {
                short val = (short)(pcmBytes[i * 2] | (pcmBytes[i * 2 + 1] << 8));
                samples[i] = val / 32768f;
            }
            _audioQueue.Enqueue(samples);
        }

        private void ProcessAudioQueue()
        {
            while (_audioQueue.TryDequeue(out float[] samples))
            {
                int samplesToWrite = Mathf.Min(samples.Length, _streamBufferSize - _writePos);
                Array.Copy(samples, 0, _streamBuffer, _writePos, samplesToWrite);

                if (samplesToWrite < samples.Length)
                {
                    int remaining = samples.Length - samplesToWrite;
                    Array.Copy(samples, samplesToWrite, _streamBuffer, 0, remaining);
                }

                _writePos = (_writePos + samples.Length) % _streamBufferSize;

                if (!_audioSource.isPlaying && _isPlaying)
                {
                    _streamClip.SetData(_streamBuffer, 0);
                    _audioSource.Play();
                }
            }

            if (_audioSource.isPlaying)
            {
                _streamClip.SetData(_streamBuffer, 0);
            }
        }

        private void UpdateLipSync()
        {
            if (!_audioSource.isPlaying)
            {
                for (int i = 0; i < VISEME_COUNT; i++) _targetVisemes[i] = 0f;
                _smoothedAmplitude = Mathf.Lerp(_smoothedAmplitude, 0f, 0.1f);
                ApplyVisemesToAvatar();
                return;
            }

            int currentPos = _audioSource.timeSamples;
            int windowSize = 512;
            float[] window = new float[windowSize];

            for (int i = 0; i < windowSize; i++)
            {
                int idx = (currentPos + i) % _streamBufferSize;
                window[i] = _streamBuffer[idx];
            }

            float sumSquares = 0f;
            for (int i = 0; i < windowSize; i++) sumSquares += window[i] * window[i];
            
            float rms = Mathf.Sqrt(sumSquares / windowSize);
            _currentAmplitude = Mathf.Clamp01(rms * 3f);
            _smoothedAmplitude = Mathf.Lerp(_smoothedAmplitude, _currentAmplitude, 0.15f);

            if (_smoothedAmplitude < AmplitudeThreshold)
            {
                for (int i = 0; i < VISEME_COUNT; i++) _targetVisemes[i] *= 0.8f;
                ApplyVisemesToAvatar();
                return;
            }

            int zeroCrossings = 0;
            for (int i = 1; i < windowSize; i++)
            {
                if ((window[i] >= 0f && window[i - 1] < 0f) || (window[i] < 0f && window[i - 1] >= 0f))
                {
                    zeroCrossings++;
                }
            }
            float zcr = (float)zeroCrossings / windowSize;

            float lowEnergy = 0f, midEnergy = 0f, highEnergy = 0f;
            int bandSize = windowSize / 3;
            for (int i = 0; i < windowSize; i++)
            {
                float energy = window[i] * window[i];
                if (i < bandSize) lowEnergy += energy;
                else if (i < bandSize * 2) midEnergy += energy;
                else highEnergy += energy;
            }
            float totalEnergy = lowEnergy + midEnergy + highEnergy + 1e-8f;
            float lowRatio = lowEnergy / totalEnergy;
            float midRatio = midEnergy / totalEnergy;
            float highRatio = highEnergy / totalEnergy;

            Array.Clear(_targetVisemes, 0, VISEME_COUNT);
            float amp = _smoothedAmplitude;

            _targetVisemes[10] = lowRatio * amp * 1.2f;
            _targetVisemes[13] = lowRatio * amp * 0.8f;
            _targetVisemes[14] = lowRatio * amp * 0.6f;
            _targetVisemes[11] = midRatio * amp * 1.0f;
            _targetVisemes[12] = midRatio * amp * 0.7f;
            _targetVisemes[7] = highRatio * amp * 1.3f;
            _targetVisemes[2] = highRatio * amp * 0.9f;
            _targetVisemes[6] = highRatio * amp * 0.7f;
            _targetVisemes[3] = highRatio * amp * 0.5f;
            _targetVisemes[1] = zcr * amp * 0.6f;
            _targetVisemes[4] = zcr * amp * 0.5f;
            _targetVisemes[5] = zcr * amp * 0.4f;
            _targetVisemes[8] = zcr * amp * 0.3f;
            _targetVisemes[9] = (1f - zcr) * amp * 0.4f;

            float maxViseme = 0f;
            for (int i = 0; i < VISEME_COUNT; i++)
            {
                if (_targetVisemes[i] > maxViseme) maxViseme = _targetVisemes[i];
            }
            if (maxViseme > 1f)
            {
                float norm = 1f / maxViseme;
                for (int i = 0; i < VISEME_COUNT; i++) _targetVisemes[i] *= norm;
            }

            ApplyVisemesToAvatar();
        }

        private void SmoothVisemes()
        {
            float lerpFactor = 1f - VisemeSmoothing;
            for (int i = 0; i < VISEME_COUNT; i++)
            {
                _currentVisemes[i] = Mathf.Lerp(_currentVisemes[i], _targetVisemes[i], lerpFactor * Time.deltaTime * 60f);
            }
        }

        private void ApplyVisemesToAvatar()
        {
            if (AvatarRoot != null)
            {
                // Hook into VRM Blendshape proxy here (A, I, U, E, O)
                var proxy = AvatarRoot.GetComponentInChildren<VRM.VRMBlendShapeProxy>();
                if (proxy != null)
                {
                    // Map Oculus visemes to Japanese vowels (A I U E O)
                    proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.A), _currentVisemes[10]); // aa
                    proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.I), _currentVisemes[12]); // ih
                    proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.U), _currentVisemes[14]); // ou
                    proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.E), _currentVisemes[11]); // E
                    proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.O), _currentVisemes[13]); // oh
                }
            }
        }

        [Serializable]
        private class SpeakRequest
        {
            public string type;
            public string text;
            public string voice;
            public float speed;
        }

        [Serializable]
        private class TtsMessage
        {
            public string type;
            public int sample_rate;
            public int duration_ms;
            public string message;
        }
    }
}
