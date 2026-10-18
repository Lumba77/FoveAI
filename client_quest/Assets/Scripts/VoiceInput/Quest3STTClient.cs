using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Text;
using System.Threading;
using UnityEngine;
using NativeWebSocket;

namespace Lumax.Quest3Bridge
{
    [RequireComponent(typeof(AudioSource))]
    public class Quest3STTClient : MonoBehaviour
    {
        /// <summary>
        /// Standalone faster-whisper STT bridge (Backend/stt_whisper_server.py,
        /// foveai-stt.service). WebSocket path is /ws or /. Source of truth:
        /// STT_PORT in /home/lumba/FoveAI/.env and ARCHITECTURE.md's port map.
        /// </summary>
        public const int DefaultSttWsPort = 8401;

        /// <summary>Identifier used by the shared AudioSource claim table.</summary>
        private const string AudioRole = "stt";

        [Header("WebSocket Connection")]
        [Tooltip("EFFECTIVE STT WebSocket URL. Rebuilt at startup from AppConfig.json serverIp + SttPort. The STT service (Backend/stt_whisper_server.py, foveai-stt.service) is a STANDALONE faster-whisper bridge on :8401 path /ws — it is NOT the unified IPC/WebSocket on :8403.")]
        public string SttServerUrl = "";
        [Tooltip("Port of the standalone faster-whisper STT WebSocket bridge (foveai-stt.service). Matches STT_PORT in /home/lumba/FoveAI/.env.")]
        public int SttPort = 8401;

        [Header("Microphone Capture")]
        [Tooltip("Target sample rate sent to server (Hz). Quest 3 mic typically 48000, resampled to 16000.")]
        public int TargetSampleRate = 16000;
        [Tooltip("Recording buffer length in seconds.")]
        public float RecordingBufferSeconds = 1.0f;
        [Tooltip("Send chunk size in milliseconds.")]
        public int SendChunkMs = 200;

        [Header("Audio Routing")]
        [Tooltip("Play the mic back through the headset speakers. OFF by default — monitoring the mic through the speakers re-enters the STT model (acoustic feedback / echo) and desynchronises the transcript.")]
        public bool monitorMicToSpeakers = false;
        [Tooltip("Headset volume used ONLY when monitorMicToSpeakers is on.")]
        [Range(0f, 1f)] public float micMonitorVolume = 0.5f;

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
        private int _finalIndex;
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
            _audioSource = AcquireAudioSource(AudioRole);
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
            int sttPort = SttPort > 0 ? SttPort : DefaultSttWsPort;
            SttServerUrl = $"ws://{settings.serverIp}:{sttPort}/ws";
            Debug.Log($"[Quest3STTClient] STT URL: {SttServerUrl} (standalone faster-whisper bridge, foveai-stt.service)");
            if (settings.wsPort == sttPort)
            {
                Debug.LogWarning($"[Quest3STTClient] AppConfig wsPort ({settings.wsPort}) equals the STT port. " +
                                 "The unified IPC server does NOT speak the whisper STT protocol — set wsPort back to the IPC port.");
            }

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
            ReleaseMicSource();

            if (_ws != null && _ws.State == WebSocketState.Open)
            {
                try
                {
                    // "stop" on THIS server means "finalize the buffer and transcribe",
                    // not "stop the TTS" — safe to use before closing.
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
            // The STT bridge speaks ONLY: binary PCM16 frames + {start|stop|reset|ping}.
            // There is no "config" message — the old {"type":"config",...} was silently
            // ignored by the server (its handler falls through with no ack). "ping" is a
            // real control message that answers {"type":"pong"}, so it doubles as a
            // liveness probe. Server-side VAD drives utterance boundaries; we do NOT send
            // "start" here because that would pin is_recording and disable pre-roll trimming.
            _ = SendTextAsync("{\"type\":\"ping\"}");
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
            if (string.IsNullOrEmpty(json)) return;
            string trimmed = json.TrimStart();
            if (trimmed.Length == 0 || trimmed[0] != '{')
            {
                Debug.LogWarning($"[STT] Non-JSON frame ignored ({trimmed[0]}): {trimmed}");
                return;
            }

            SttMessage msg = null;
            try
            {
                msg = JsonUtility.FromJson<SttMessage>(trimmed);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[STT] Failed to parse message: {ex.Message}\n  raw: {trimmed}");
                return;
            }
            if (msg == null) return;

            // Tolerant field aliases: the bridge emits "text", but wrappers/proxies
            // have historically used "transcription" or "transcript".
            string text = !string.IsNullOrEmpty(msg.text) ? msg.text
                        : !string.IsNullOrEmpty(msg.transcription) ? msg.transcription
                        : msg.transcript;
            string type = msg.type;

            // No "type" at all but there is text → treat as a final transcript.
            if (string.IsNullOrEmpty(type))
            {
                if (!string.IsNullOrEmpty(text))
                {
                    Debug.Log($"[STT] Untyped frame treated as final transcript.");
                    HandleFinal(text, msg);
                }
                else
                {
                    Debug.LogWarning($"[STT] Untyped frame with no text ignored: {trimmed}");
                }
                return;
            }

            switch (type)
            {
                case "ready":
                    _serverSampleRate = msg.sample_rate > 0 ? msg.sample_rate : TargetSampleRate;
                    _isConnected = true;
                    Debug.Log($"[STT] Bridge ready (sample_rate={_serverSampleRate})");
                    OnConnected?.Invoke();
                    if (AutoStartOnEnable) StartRecording();
                    break;
                case "pong":
                    break;
                case "ack":
                    Debug.Log($"[STT] ack: {msg.status}");
                    break;
                case "speech_start":
                case "vad_start":
                case "listening":
                    _speechActive = true;
                    OnListeningStart?.Invoke();
                    break;
                case "speech_end":
                case "vad_end":
                case "stopped_speaking":
                    _speechActive = false;
                    OnListeningEnd?.Invoke();
                    break;
                case "partial":
                    OnPartialTranscript?.Invoke(text ?? "", msg.segment);
                    break;
                case "final":
                case "transcription":
                case "transcript":
                case "result":
                case "text":
                    HandleFinal(text, msg);
                    break;
                case "error":
                    OnError?.Invoke(!string.IsNullOrEmpty(msg.error) ? msg.error
                                  : !string.IsNullOrEmpty(msg.message) ? msg.message
                                  : "unknown");
                    break;
                default:
                    // Loudly surface protocol drift instead of failing silently again.
                    Debug.LogWarning($"[STT] Unknown message type \"{type}\" — backend protocol drift?\n  raw: {trimmed}");
                    break;
            }
        }

        private void HandleFinal(string text, SttMessage msg)
        {
            if (string.IsNullOrWhiteSpace(text)) return;
            // The bridge does not number utterances — keep a local monotonic index so
            // the int argument of OnFinalTranscript is a useful utterance counter.
            if (msg.segment > 0) _finalIndex = msg.segment;
            else _finalIndex++;
            OnFinalTranscript?.Invoke(text, _finalIndex);
            AppendTranscriptSegment(text);
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
            // Capture requires the clip to be PLAYED, but the playback must stay
            // silent: routing the mic to the headset speakers re-enters the STT
            // model (acoustic feedback) and desyncs the transcript.
            _audioSource.volume = monitorMicToSpeakers ? micMonitorVolume : 0f;
            _audioSource.mute = !monitorMicToSpeakers;
            _audioSource.spatialBlend = 0f;   // monitoring is never spatializer-relevant
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
            ReleaseMicSource();
            if (_isConnected)
            {
                // On the STT bridge "stop" = finalize + transcribe the buffered audio,
                // then clear it and drop the VAD latch — one message is enough (a
                // following "reset" would be redundant, and two fire-and-forget sends
                // can race). Pre-roll trimming resumes once the server clears the buffer.
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
                // "reset" drops the buffered audio AND re-arms the server VAD /
                // pre-roll trimming, so speech captured while paused is never
                // transcribed.
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
                // Re-arm the server buffer after a PauseCapture "reset".
                _ = SendTextAsync("{\"type\":\"start\"}");
            }
        }

        private void ReleaseMicSource()
        {
            if (_audioSource == null) return;
            _audioSource.Stop();
            _audioSource.clip = null;
        }

        private void OnDestroy()
        {
            if (_audioSource != null)
            {
                VoiceAudioSourceRegistry.Release(_audioSource);
                _audioSource = null;
            }
        }

        /// <summary>
        /// Resolves the AudioSource this client owns. Both Quest3STTClient and
        /// Quest3TTSClient are [RequireComponent(typeof(AudioSource))] and in
        /// FoveAI.unity they sit on the SAME GameObject, so GetComponent() would
        /// hand both of them the one shared instance — the STT mic clip would be
        /// assigned to it, and TTS would then "play" the mic. The claim table
        /// guarantees exactly one owner per AudioSource; a loser creates its own
        /// child GameObject + AudioSource.
        /// </summary>
        private AudioSource AcquireAudioSource(string role)
        {
            var existing = GetComponent<AudioSource>();
            if (existing != null && VoiceAudioSourceRegistry.TryClaim(existing, role))
            {
                return existing;
            }

            if (existing != null)
            {
                string owner = VoiceAudioSourceRegistry.OwnerOf(existing);
                Debug.LogWarning($"[Quest3STTClient] Shared AudioSource on '{name}' is already claimed by " +
                                 $"'{owner}' — creating a dedicated 'Audio_{role}' child so the mic never " +
                                 "collides with TTS playback.");
            }

            var host = new GameObject("Audio_" + role);
            host.transform.SetParent(transform, false);
            var dedicated = host.AddComponent<AudioSource>();
            dedicated.playOnAwake = false;
            dedicated.loop = false;
            VoiceAudioSourceRegistry.ForceClaim(dedicated, role);
            return dedicated;
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
            public string transcription;
            public string transcript;
            public int segment;
            public int sample_rate;
            public string status;
            public string message;
            public string error;
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

    /// <summary>
    /// Process-wide claim table that guarantees two <c>[RequireComponent(typeof(AudioSource))]</c>
    /// voice clients sharing one GameObject never resolve to the same AudioSource instance.
    /// Without it, Quest3STTClient assigns the mic clip to the shared source and
    /// Quest3TTSClient then "plays" the mic instead of the TTS stream.
    /// Static (not a MonoBehaviour) so no extra component type enters the scene/prefab set.
    /// </summary>
    public static class VoiceAudioSourceRegistry
    {
        private struct Claim
        {
            public AudioSource source;
            public string role;
        }

        private static readonly Dictionary<int, Claim> _claims = new Dictionary<int, Claim>();

        public static bool TryClaim(AudioSource source, string role)
        {
            if (source == null) return false;
            PurgeDestroyed();

            int id = source.GetInstanceID();
            if (_claims.TryGetValue(id, out Claim existing))
            {
                if (existing.source == null || existing.role == role)
                {
                    _claims[id] = new Claim { source = source, role = role };
                    return true;
                }
                return false;
            }

            _claims[id] = new Claim { source = source, role = role };
            return true;
        }

        public static void ForceClaim(AudioSource source, string role)
        {
            if (source == null) return;
            PurgeDestroyed();
            _claims[source.GetInstanceID()] = new Claim { source = source, role = role };
        }

        public static void Release(AudioSource source)
        {
            if (source == null) return;
            _claims.Remove(source.GetInstanceID());
        }

        public static string OwnerOf(AudioSource source)
        {
            if (source == null) return "none";
            PurgeDestroyed();
            return _claims.TryGetValue(source.GetInstanceID(), out Claim c) ? c.role : "unclaimed";
        }

        private static void PurgeDestroyed()
        {
            List<int> dead = null;
            foreach (var kv in _claims)
            {
                if (kv.Value.source == null)
                {
                    if (dead == null) dead = new List<int>();
                    dead.Add(kv.Key);
                }
            }
            if (dead == null) return;
            foreach (int id in dead) _claims.Remove(id);
        }
    }
}
