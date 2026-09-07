using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Text;
using System.Threading;
using UnityEngine;
using NativeWebSocket;

namespace Lumax.Quest3Bridge
{
    [RequireComponent(typeof(AudioSource))]
    public class Quest3STTClient : MonoBehaviour
    {
        [Header("WebSocket Connection")]
        [Tooltip("WebSocket URL of the unified WS server. Leave empty to use AppConfig.json wsPort.")]
        public string SttServerUrl = "";

        [Header("Microphone Capture")]
        [Tooltip("Target sample rate sent to server (Hz). Quest 3 mic typically 48000, resampled to 16000.")]
        public int TargetSampleRate = 16000;
        [Tooltip("Recording buffer length in seconds.")]
        public float RecordingBufferSeconds = 1.0f;
        [Tooltip("Send chunk size in milliseconds.")]
        public int SendChunkMs = 200;

        [Header("Settings")]
        public string Language = "en";
        public bool AutoStartOnEnable = true;
        [Min(0.5f)] public float TurnCommitSilenceSeconds = 1.75f;

        // ── Events ──────────────────────────────────────────────────────
        public event Action<string, int> OnPartialTranscript;
        public event Action<string, int> OnFinalTranscript;
        public event Action OnConnected;
        public event Action<string> OnError;
        public event Action OnListeningStart;
        public event Action OnListeningEnd;

        // ── State ───────────────────────────────────────────────────────
        private WebSocket _ws;
        private AudioSource _audioSource;
        private string _micDevice;
        private bool _isRecording;
        private bool _isConnected;
        private bool _capturePaused;
        private bool _speechActive;
        private bool _turnPending;
        public bool ManualDictationMode { get; private set; }
        private float _lastFinalTranscriptTime;
        private readonly StringBuilder _pendingTranscript = new StringBuilder();
        private int _serverSampleRate = 16000;

        private float[] _micBuffer;
        private int _micBufferSize;
        private int _lastMicPos;
        private int _chunkSampleCount;

        private readonly ConcurrentQueue<byte[]> _sendQueue = new ConcurrentQueue<byte[]>();
        private Thread _sendThread;
        private volatile bool _running;

        private void Awake()
        {
            _audioSource = GetComponent<AudioSource>();
            _micBufferSize = Mathf.CeilToInt(TargetSampleRate * RecordingBufferSeconds);
            _chunkSampleCount = TargetSampleRate * SendChunkMs / 1000;
            _micBuffer = new float[_micBufferSize];
        }

        private bool _initialized = false;

        private void Start()
        {
            StartCoroutine(InitRoutine());
        }

        // Full init sequence as a proper IEnumerator - this is the ONLY correct way
        // to combine async config loading, coroutine-based permission request, and
        // async Connect() in a single ordered flow in Unity.
        private IEnumerator InitRoutine()
        {
            // 1. Load config (async Task wrapped into a coroutine yield)
            var loadTask = FoveAI.Config.ConfigLoader.LoadConfigAsync();
            yield return new WaitUntil(() => loadTask.IsCompleted);

            var settings = FoveAI.Config.ConfigLoader.Settings;
            SttServerUrl = $"ws://{settings.serverIp}:{settings.wsPort}/ws";
            Debug.Log($"[Quest3STTClient] STT URL: {SttServerUrl} (unified WebSocket)");

#if UNITY_ANDROID && !UNITY_EDITOR
            // 2. Request Android mic permission - MUST be in a coroutine, not async
            yield return StartCoroutine(RequestMicPermissionCoroutine());
#endif

            _initialized = true;

            // 3. Connect if auto-start enabled
            if (AutoStartOnEnable)
            {
                var connectTask = ConnectAsync();
                yield return new WaitUntil(() => connectTask.IsCompleted);
            }
        }

        private IEnumerator RequestMicPermissionCoroutine()
        {
            if (!Application.HasUserAuthorization(UserAuthorization.Microphone))
            {
                Debug.Log("[Quest3STTClient] Requesting microphone permission...");
                yield return Application.RequestUserAuthorization(UserAuthorization.Microphone);

                if (!Application.HasUserAuthorization(UserAuthorization.Microphone))
                {
                    Debug.LogError("[Quest3STTClient] Microphone permission DENIED.");
                    OnError?.Invoke("Microphone permission denied by user");
                    yield break;
                }
                Debug.Log("[Quest3STTClient] Microphone permission GRANTED.");
                yield return new WaitForSeconds(0.5f); // let Android finalize
            }
        }

        // OnEnable: reconnect ONLY if already initialized (handles scene reload / re-enable)
        private async void OnEnable()
        {
            if (_initialized && AutoStartOnEnable)
            {
                await ConnectAsync();
            }
        }

        private void OnDisable()
        {
            StopRecording();
            _ = DisconnectAsync();
        }

        private void Update()
        {
            if (_isRecording && _isConnected && !_capturePaused)
            {
                CaptureAndQueueAudio();
            }

            if (_ws != null)
            {
#if !UNITY_WEBGL || UNITY_EDITOR
                _ws.DispatchMessageQueue();
#endif
            }

            if (_turnPending && !ManualDictationMode && !_speechActive && !_capturePaused &&
                Time.unscaledTime - _lastFinalTranscriptTime >= TurnCommitSilenceSeconds)
            {
                CommitPendingTurn();
            }
        }

        public async System.Threading.Tasks.Task ConnectAsync()
        {
            if (_ws != null && (_ws.State == WebSocketState.Open || _ws.State == WebSocketState.Connecting))
                return;

            try
            {
                _ws = new WebSocket(SttServerUrl);
                _ws.OnOpen += OnWsOpen;
                _ws.OnMessage += OnWsMessage;
                _ws.OnError += OnWsError;
                _ws.OnClose += OnWsClose;

                await _ws.Connect();
            }
            catch (Exception ex)
            {
                OnError?.Invoke($"connect: {ex.Message}");
            }
        }

        public async System.Threading.Tasks.Task DisconnectAsync()
        {
            _running = false;
            _isRecording = false;

            if (_micDevice != null && Microphone.IsRecording(_micDevice))
            {
                Microphone.End(_micDevice);
            }

            if (_ws != null && _ws.State == WebSocketState.Open)
            {
                try
                {
                    await SendTextAsync("{\"type\":\"stop\"}");
                    await _ws.Close();
                }
                catch { /* ignore */ }
            }

            if (_sendThread != null && _sendThread.IsAlive)
            {
                _sendThread.Join(2000);
            }
        }

        private void OnWsOpen()
        {
            _ = SendTextAsync($"{{\"type\":\"config\",\"sample_rate\":{TargetSampleRate},\"language\":\"{Language}\"}}");
        }

        private void OnWsMessage(byte[] data)
        {
            string json = Encoding.UTF8.GetString(data);
            ParseServerMessage(json);
        }

        private void OnWsError(string errorMsg)
        {
            OnError?.Invoke($"ws: {errorMsg}");
        }

        private void OnWsClose(WebSocketCloseCode code)
        {
            _isConnected = false;
            _isRecording = false;
            _running = false;
        }

        private void ParseServerMessage(string json)
        {
            try
            {
                var msg = JsonUtility.FromJson<SttMessage>(json);
                if (msg == null) return;

                switch (msg.type)
                {
                    case "ready":
                        _serverSampleRate = msg.sample_rate > 0 ? msg.sample_rate : TargetSampleRate;
                        _isConnected = true;
                        OnConnected?.Invoke();
                        if (AutoStartOnEnable) StartRecording();
                        break;
                    case "speech_start":
                        _speechActive = true;
                        OnListeningStart?.Invoke();
                        break;
                    case "speech_end":
                        _speechActive = false;
                        OnListeningEnd?.Invoke();
                        break;
                    case "partial":
                        OnPartialTranscript?.Invoke(msg.text ?? "", msg.segment);
                        break;
                    case "final":
                        OnFinalTranscript?.Invoke(msg.text ?? "", msg.segment);
                        AppendTranscriptSegment(msg.text);
                        break;
                    case "error":
                        OnError?.Invoke(msg.message ?? "unknown");
                        break;
                }
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[STT] Failed to parse message: {ex.Message}\n  raw: {json}");
            }
        }

        private void AppendTranscriptSegment(string text)
        {
            if (ManualDictationMode || string.IsNullOrWhiteSpace(text)) return;
            if (_pendingTranscript.Length > 0) _pendingTranscript.Append(' ');
            _pendingTranscript.Append(text.Trim());
            _lastFinalTranscriptTime = Time.unscaledTime;
            _turnPending = true;
        }

        public void SetManualDictationMode(bool enabled)
        {
            ManualDictationMode = enabled;
            _pendingTranscript.Clear();
            _turnPending = false;
        }

        private void CommitPendingTurn()
        {
            string message = _pendingTranscript.ToString().Trim();
            _pendingTranscript.Clear();
            _turnPending = false;
            if (string.IsNullOrWhiteSpace(message)) return;

            var wsClient = FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            if (wsClient != null)
            {
                wsClient.SendChatMessage(message);
            }
        }

        public void StartRecording()
        {
            if (_isRecording) return;
            if (Microphone.devices.Length == 0)
            {
                OnError?.Invoke("No microphone device found");
                return;
            }

            _micDevice = Microphone.devices[0];
            _audioSource.clip = Microphone.Start(_micDevice, true, (int)RecordingBufferSeconds, TargetSampleRate);
            _audioSource.loop = true;
            _audioSource.Play();

            _lastMicPos = 0;
            _isRecording = true;
            _running = true;

            _sendThread = new Thread(SendLoop) { IsBackground = true, Name = "STT-SendLoop" };
            _sendThread.Start();
        }

        public void StopRecording()
        {
            _isRecording = false;
            if (_micDevice != null && Microphone.IsRecording(_micDevice))
            {
                Microphone.End(_micDevice);
            }
            if (_isConnected)
            {
                _ = SendTextAsync("{\"type\":\"stop\"}");
            }
            OnListeningEnd?.Invoke();
        }

        public void PauseCapture()
        {
            _capturePaused = true;
            while (_sendQueue.TryDequeue(out _)) { }
            if (_isConnected)
            {
                _ = SendTextAsync("{\"type\":\"reset\"}");
            }
            OnListeningEnd?.Invoke();
        }

        public void ResumeCapture()
        {
            bool wasRecording = _isRecording;
            if (!wasRecording) StartRecording();
            if (!_isRecording) return;
            _lastMicPos = Microphone.GetPosition(_micDevice);
            _capturePaused = false;
            if (_isConnected)
            {
                _ = SendTextAsync("{\"type\":\"start\"}");
            }
        }

        private void CaptureAndQueueAudio()
        {
            if (_audioSource == null || _audioSource.clip == null) return;
            int currentPos = Microphone.GetPosition(_micDevice);
            if (currentPos < 0) return;

            int samplesAvailable = AudioUtils.GetSampleDelta(_lastMicPos, currentPos, _micBufferSize);
            if (samplesAvailable < _chunkSampleCount) return;

            int samplesToRead = Mathf.Min(samplesAvailable, _chunkSampleCount);
            _audioSource.clip.GetData(_micBuffer, _lastMicPos);

            float[] chunk = new float[samplesToRead];
            Array.Copy(_micBuffer, 0, chunk, 0, samplesToRead);
            byte[] pcmBytes = AudioUtils.FloatToPCM16(chunk);
            _sendQueue.Enqueue(pcmBytes);

            _lastMicPos = (_lastMicPos + samplesToRead) % _micBufferSize;
        }

        private void SendLoop()
        {
            while (_running)
            {
                if (_ws == null || _ws.State != WebSocketState.Open)
                {
                    Thread.Sleep(50);
                    continue;
                }

                while (_sendQueue.TryDequeue(out byte[] pcmData))
                {
                    try
                    {
                        _ws.Send(pcmData).Wait(100);
                    }
                    catch (Exception ex)
                    {
                        Debug.LogWarning($"[STT] Send error: {ex.Message}");
                    }
                }
                Thread.Sleep(10);
            }
        }

        private async System.Threading.Tasks.Task SendTextAsync(string text)
        {
            if (_ws != null && _ws.State == WebSocketState.Open)
            {
                await _ws.SendText(text);
            }
        }

        [Serializable]
        private class SttMessage
        {
            public string type;
            public string text;
            public int segment;
            public int sample_rate;
            public string message;
        }
    }

    public static class AudioUtils
    {
        public static int GetSampleDelta(int lastPos, int currentPos, int bufferSize)
        {
            if (currentPos >= lastPos) return currentPos - lastPos;
            return bufferSize - lastPos + currentPos;
        }

        public static byte[] FloatToPCM16(float[] samples)
        {
            byte[] bytes = new byte[samples.Length * 2];
            for (int i = 0; i < samples.Length; i++)
            {
                float clamped = Mathf.Clamp(samples[i], -1f, 1f);
                short val = (short)(clamped * 32767f);
                bytes[i * 2] = (byte)(val & 0xFF);
                bytes[i * 2 + 1] = (byte)((val >> 8) & 0xFF);
            }
            return bytes;
        }
    }
}
