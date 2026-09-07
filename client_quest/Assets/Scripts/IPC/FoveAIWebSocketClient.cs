using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using FoveAI.Avatar;

namespace FoveAI.IPC
{
    /// <summary>
    /// Connects Quest 3 native APK to the FoveAI PC Backend via WebSocket.
    /// Handles automatic reconnection, sends chat.msg events, and parses
    /// incoming chat.response payloads (including emotion + intensity).
    /// </summary>
    public class FoveAIWebSocketClient : MonoBehaviour
    {
        [Header("Connection")]
        [Tooltip("The URI of the Python backend (loaded dynamically)")]
        [SerializeField] private string serverUrl = "ws://192.168.8.100:8403/ws";
        [Tooltip("Initial delay before first connection attempt (seconds). Gives the backend time to start.")]
        [SerializeField] private float initialConnectDelay = 3f;
        [SerializeField] private float reconnectDelay = 2f;
        [SerializeField] private float maxReconnectDelay = 30f;
        [SerializeField] private int maxReconnectAttempts = 0; // 0 = infinite

        [Header("Avatar & Emotion Settings")]
        [Tooltip("Reference to the AvatarBlendshapeDriver that receives emotion data.")]
        [SerializeField] private FoveAI.Avatar.AvatarBlendshapeDriver avatarBlendshapeDriver;

        [Tooltip("Reference to the AvatarAnimationBrain for conversation state management.")]
        [SerializeField] private FoveAI.Avatar.AvatarAnimationBrain animationBrain;

        /// <summary>Emitted when a chat.response with emotion is received.</summary>
        public event Action<string, float> OnEmotionReceived;

        /// <summary>Emitted when a chat.response text payload is received.</summary>
        public event Action<string> OnChatTextReceived;

        /// <summary>Emitted when a motor_action (puppeteering) is received.</summary>
        public event Action<string, string> OnMotorActionReceived;

        /// <summary>Emitted when a backend error event is received.</summary>
        public event Action<string> OnErrorReceived;

        /// <summary>Emitted when a settings.toggle broadcast is received from the backend.</summary>
        public event Action OnSettingsToggle;

        /// <summary>Emitted when the backend uses XRL Principia to fetch a shadow memory (fleshing out context).</summary>
        public event Action<string> OnXRLExpandReceived;

        public void BindAvatar(FoveAI.Avatar.AvatarBlendshapeDriver blendshapeDriver, FoveAI.Avatar.AvatarAnimationBrain brain)
        {
            avatarBlendshapeDriver = blendshapeDriver;
            animationBrain = brain;
        }

        /// <summary>Emitted when the backend reports its holonic resonance state (which gnists are alive).</summary>
        public event Action<string, bool> OnResonanceReceived;

        /// <summary>Emitted when raw TTS/speech audio bytes are received from backend.</summary>
        public event Action<byte[]> OnAudioDataReceived;

        /// <summary>Emitted for every raw JSON message received, primarily for the Terminal IDE.</summary>
        public event Action<string> OnRawMessageReceived;

        // ── Director events ──
        /// <summary>Emitted when the Director triggers a narrative event. Payload: {eventType, genre, characterName, narratorLines, dialogue, payload, duration}</summary>
        public event Action<string> OnDirectorEventReceived;
        /// <summary>Emitted when the Director starts building suspense (audio-only foreshadowing). Payload: {intensity, duration, eventType, genre}</summary>
        public event Action<string> OnDirectorSuspenseBuildReceived;
        /// <summary>Emitted at the suspense threshold — the held-breath moment before the event. Payload: {text}</summary>
        public event Action<string> OnDirectorSuspenseThresholdReceived;
        /// <summary>Emitted when the Director aborts suspense. Payload: {}</summary>
        public event Action OnDirectorSuspenseAbort;
        /// <summary>Emitted when the Director triggers a shared surprise. Payload: {surpriseType, timeOfDay, mood}</summary>
        public event Action<string> OnDirectorSurpriseReceived;
        /// <summary>Emitted when the Director triggers a named scripted sequence. Payload: {sequence}</summary>
        public event Action<string> OnDirectorSequenceReceived;
        /// <summary>Emitted when the narrator speaks. Payload: {text, genre, eventType}</summary>
        public event Action<string> OnDirectorNarrationReceived;
        /// <summary>Emitted when Alice should react to a Director event. Payload: {text}</summary>
        public event Action<string> OnDirectorAliceReceived;
        /// <summary>Emitted for Director-triggered TTS (character voices). Payload: {text, voice}</summary>
        public event Action<string, string> OnDirectorTTSReceived;
        /// <summary>Emitted when a seasonal comment or change occurs. Payload: {season, holiday, text}</summary>
        public event Action<string> OnSeasonalReceived;
        // ── Story Garden events ──
        /// <summary>Emitted when the Director plants a new story seed. Payload: {concept, source, stage}</summary>
        public event Action<string> OnGardenSeedReceived;
        /// <summary>Emitted when a story thread advances to a new beat (subtle foreshadowing). Payload: {threadTitle, beat, description, tension}</summary>
        public event Action<string> OnGardenBeatReceived;
        /// <summary>Emitted with the garden status. Payload: {totalSeeds, stages, activeThreads, readyToFruit, oldestSeedDays}</summary>
        public event Action<string> OnGardenStatusReceived;

        private FoveAIWebSocket _socket;
        public bool IsConnected => _socket != null && _socket.IsOpen;
        private float _currentReconnectDelay;
        private int _reconnectAttempts;
        private bool _intentionalClose;
        private bool _isConnecting;

        // ── TTS audio playback ──
        private AudioSource _ttsAudioSource;

        // ─────────────────────────────────────────────────────────────
        //  Unity lifecycle
        // ─────────────────────────────────────────────────────────────

        private void Awake()
        {
            // Auto-retrieve the component if not assigned in Inspector
            if (avatarBlendshapeDriver == null)
            {
                avatarBlendshapeDriver = GetComponent<FoveAI.Avatar.AvatarBlendshapeDriver>();

                if (avatarBlendshapeDriver == null)
                {
                    avatarBlendshapeDriver = FindAnyObjectByType<FoveAI.Avatar.AvatarBlendshapeDriver>();
                }
            }

            // Ensure we have an AudioSource for TTS playback
            _ttsAudioSource = GetComponent<AudioSource>();
            if (_ttsAudioSource == null)
            {
                _ttsAudioSource = gameObject.AddComponent<AudioSource>();
            }
            _ttsAudioSource.playOnAwake = false;
            _ttsAudioSource.loop = false;
            _ttsAudioSource.spatialBlend = 0.0f; // 2D — always audible regardless of position
        }

        private async void Start()
        {
            _currentReconnectDelay = reconnectDelay;

            // Wait for config to load from StreamingAssets
            await FoveAI.Config.ConfigLoader.LoadConfigAsync();
            var settings = FoveAI.Config.ConfigLoader.Settings;
            
            // Override inspector URL with config URL (unified WebSocket port)
            serverUrl = $"ws://{settings.serverIp}:{settings.wsPort}/ws";
            Debug.Log($"[FoveAIWebSocketClient] Loaded config URL: {serverUrl}");

            // Delay initial connection to give the BackendLauncher time to start the Python server
            Debug.Log($"[FoveAI] Waiting {initialConnectDelay:F1}s before connecting to {serverUrl}...");
            Invoke(nameof(Connect), initialConnectDelay);
        }

        private void OnApplicationQuit()
        {
            _intentionalClose = true;
            _socket?.Close();
        }

        private void OnDestroy()
        {
            _intentionalClose = true;
            _socket?.Close();
        }
        private void Update()
        {
#if ENABLE_INPUT_SYSTEM
            // Input System package: use Keyboard.current
            if (UnityEngine.InputSystem.Keyboard.current != null &&
                UnityEngine.InputSystem.Keyboard.current.spaceKey.wasPressedThisFrame)
            {
                SendChatMessage("Hello FoveAI! How are you feeling today?");
            }
#elif ENABLE_LEGACY_INPUT_MANAGER
            // Legacy Input Manager: use UnityEngine.Input
            if (Input.GetKeyDown(KeyCode.Space))
            {
                SendChatMessage("Hello FoveAI! How are you feeling today?");
            }
            if (Input.GetKeyDown(KeyCode.W))
            {
                // Simulate AI pushing joystick forward for 2 seconds
                string fakePayload = "{\"tool\": \"virtual_gamepad\", \"args\": {\"move_x\": 0.0, \"move_y\": 0.5, \"spin_x\": 0.0, \"duration\": 2.0}}";
                ParseIncomingPayload("{\"event\":\"motor_action\",\"payload\":" + fakePayload + "}");
            }
            if (Input.GetKeyDown(KeyCode.R))
            {
                // Simulate AI spinning right for 1.5 seconds
                string fakePayload = "{\"tool\": \"virtual_gamepad\", \"args\": {\"move_x\": 0.0, \"move_y\": 0.0, \"spin_x\": 1.0, \"duration\": 1.5}}";
                ParseIncomingPayload("{\"event\":\"motor_action\",\"payload\":" + fakePayload + "}");
            }
#endif
        }

        // ─────────────────────────────────────────────────────────────
        //  Connection management
        // ─────────────────────────────────────────────────────────────

        private async void Connect()
        {
            if (_isConnecting || (_socket != null && _socket.IsOpen)) return;
            _isConnecting = true;

            Debug.Log($"[FoveAI] Connecting to PC Backend at {serverUrl}...");

            try
            {
                _socket = new FoveAIWebSocket(new Uri(serverUrl));
                _socket.OnOpen += HandleSocketOpen;
                _socket.OnMessage += HandleSocketMessage;
                _socket.OnClose += HandleSocketClose;
                _socket.OnError += HandleSocketError;

                await _socket.Connect();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[FoveAI] Connection failed: {ex.Message}");
                ScheduleReconnect();
            }
            finally
            {
                _isConnecting = false;
            }
        }

        private void ScheduleReconnect()
        {
            if (_intentionalClose) return;
            if (maxReconnectAttempts > 0 && _reconnectAttempts >= maxReconnectAttempts)
            {
                Debug.LogError("[FoveAI] Max reconnect attempts reached. Giving up.");
                return;
            }

            _reconnectAttempts++;
            float delay = Mathf.Min(_currentReconnectDelay, maxReconnectDelay);
            _currentReconnectDelay *= 1.5f; // exponential backoff

            Debug.Log($"[FoveAI] Reconnecting in {delay:F1}s (attempt {_reconnectAttempts})...");
            PlayStatusTone(StatusTone.Reconnecting);
            Invoke(nameof(Connect), delay);
        }

        // ─────────────────────────────────────────────────────────────
        //  Socket callbacks
        // ─────────────────────────────────────────────────────────────

        private void HandleSocketOpen()
        {
            Debug.Log("[FoveAI] WebSocket connected.");
            _currentReconnectDelay = reconnectDelay;
            _reconnectAttempts = 0;
            PlayStatusTone(StatusTone.Connected);
        }

        private void HandleSocketMessage(byte[] data)
        {
            string json = Encoding.UTF8.GetString(data);
            OnRawMessageReceived?.Invoke(json);
            ParseIncomingPayload(json);
        }

        private void HandleSocketClose(ushort code, string reason)
        {
            Debug.LogWarning($"[FoveAI] WebSocket closed: {code} {reason}");
            PlayStatusTone(StatusTone.Disconnected);
            if (!_intentionalClose) ScheduleReconnect();
        }

        private void HandleSocketError(string errorMsg)
        {
            Debug.LogWarning($"[FoveAI] WebSocket error: {errorMsg}");
            PlayStatusTone(StatusTone.Error);
            // Trigger reconnect on error (server might not be ready yet)
            if (!_intentionalClose && !_isConnecting)
            {
                ScheduleReconnect();
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  Audio Status Tones — so you can hear connection state changes
        // ─────────────────────────────────────────────────────────────
        private enum StatusTone { Connected, Disconnected, Error, Reconnecting }
        private AudioSource _statusAudio;

        private void PlayStatusTone(StatusTone tone)
        {
            if (_statusAudio == null)
            {
                _statusAudio = gameObject.AddComponent<AudioSource>();
                _statusAudio.volume = 0.3f;
            }
            // Each tone is a distinct beep pattern: (freq, duration, delay)
            (float freq, float dur, float delay)[] pattern = tone switch
            {
                StatusTone.Connected    => new[] { (660f, 0.08f, 0f), (880f, 0.12f, 0.10f) },           // two rising beeps
                StatusTone.Disconnected => new[] { (440f, 0.15f, 0f), (330f, 0.20f, 0.18f) },          // two falling beeps
                StatusTone.Error        => new[] { (200f, 0.30f, 0f) },                                 // low buzz
                StatusTone.Reconnecting => new[] { (500f, 0.06f, 0f) },                                 // short blip
                _ => new[] { (440f, 0.1f, 0f) }
            };
            StartCoroutine(PlayToneSequence(pattern));
        }

        private System.Collections.IEnumerator PlayToneSequence((float freq, float dur, float delay)[] notes)
        {
            foreach (var (freq, dur, delay) in notes)
            {
                if (delay > 0f) yield return new WaitForSeconds(delay);
                int sampleRate = AudioSettings.outputSampleRate;
                int samples = (int)(sampleRate * dur);
                float[] data = new float[samples];
                for (int i = 0; i < samples; i++)
                {
                    data[i] = Mathf.Sin(2f * Mathf.PI * freq * i / sampleRate) * 0.5f;
                }
                var clip = AudioClip.Create("tone", samples, 1, sampleRate, false);
                clip.SetData(data, 0);
                _statusAudio.PlayOneShot(clip);
                yield return new WaitForSeconds(dur);
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  Outgoing events
        // ─────────────────────────────────────────────────────────────

        /// <summary>
        /// Send a raw event with a JSON payload to the backend.
        /// </summary>
        public void SendEvent(string eventName, string jsonPayload)
        {
            if (_socket == null || !_socket.IsOpen)
            {
                Debug.LogWarning("[FoveAI] Cannot send event — socket not open.");
                return;
            }

            string envelope = $"{{\"event\":\"{eventName}\",\"payload\":{jsonPayload}}}";
            _socket.SendString(envelope);
            Debug.Log($"[FoveAI] Sent event: {eventName}");
        }

        /// <summary>
        /// Ask the backend how it feels — queries holonic resonance state.
        /// Response comes back via OnResonanceReceived event.
        /// </summary>
        public void QueryResonance()
        {
            SendEvent("resonance", "{}");
        }

        /// <summary>
        /// Convenience wrapper: send a chat event with a user message.
        /// The backend IPCServer._handle_chat reads payload["text"] (not "message").
        /// </summary>
        public void SendChatMessage(string message)
        {
            string payload = $"{{\"text\":{JsonEscape(message)}}}";
            SendEvent("chat", payload);

            // Notify the brain that the user sent a message → THINKING
            if (animationBrain != null)
            {
                animationBrain.OnUserMessage();
            }
        }

        /// <summary>Send a raw JSON string over the WebSocket (no event wrapper).</summary>
        public void SendRawMessage(string json)
        {
            if (_socket == null || !_socket.IsOpen) return;
            _socket.SendString(json);
        }
        /// <summary>
        /// Update the server URL and reconnect.
        /// Called from the in-scene settings panel.
        /// </summary>
        public void SetServerUrl(string newUrl)
        {
            if (string.IsNullOrEmpty(newUrl)) return;
            serverUrl = newUrl.Trim();
            _intentionalClose = true;
            _socket?.Close();
            _socket = null;
            _intentionalClose = false;
            _reconnectAttempts = 0;
            _currentReconnectDelay = reconnectDelay;
            Connect();
        }


        // ─────────────────────────────────────────────────────────────
        //  Incoming payload parsing
        // ─────────────────────────────────────────────────────────────

        private void ParseIncomingPayload(string json)
        {
            if (string.IsNullOrWhiteSpace(json)) return;

            try
            {
                // Lightweight extraction without a full JSON parser dependency.
                string eventType = ExtractStringField(json, "event");
                string payloadJson = ExtractObjectField(json, "payload");

                if (string.IsNullOrEmpty(eventType))
                {
                    // If no "event" field, the entire message may BE the payload.
                    eventType = ExtractStringField(json, "type");
                    payloadJson = json;
                }

                if (eventType == "chat.response")
                {
                    HandleChatResponse(payloadJson);
                }
                else if (eventType == "error")
                {
                    string errorMsg = ExtractStringField(payloadJson, "message");
                    if (string.IsNullOrEmpty(errorMsg))
                        errorMsg = ExtractStringField(payloadJson, "error");
                    if (string.IsNullOrEmpty(errorMsg))
                        errorMsg = payloadJson;
                    Debug.LogError($"[FoveAI] Backend error: {errorMsg}");
                    OnErrorReceived?.Invoke(errorMsg);
                }
                else if (eventType == "motor_action")
                {
                    string tool = ExtractStringField(payloadJson, "tool");
                    string argsStr = ExtractObjectField(payloadJson, "args");
                    Debug.Log($"[FoveAI] Motor action received: {tool} -> {argsStr}");
                    OnMotorActionReceived?.Invoke(tool, argsStr);
                }
                else if (eventType == "settings.toggle")
                {
                    Debug.Log("[FoveAI] Settings toggle received from backend");
                    OnSettingsToggle?.Invoke();
                }
                else if (eventType == "xrl.expand")
                {
                    string hash = ExtractStringField(payloadJson, "hash");
                    Debug.Log($"[FoveAI] XRL Shadow Memory Expansion received for hash: {hash}");
                    OnXRLExpandReceived?.Invoke(hash);
                }
                else if (eventType == "resonance")
                {
                    string feeling = ExtractStringField(payloadJson, "feeling");
                    bool harmony = ExtractStringField(payloadJson, "harmony") == "true";
                    Debug.Log($"[FoveAI] Resonance: {feeling}");
                    OnResonanceReceived?.Invoke(feeling, harmony);
                }
                else if (eventType == "tts.response" || eventType == "audio")
                {
                    string audioB64 = ExtractStringField(payloadJson, "audio_base64");
                    if (!string.IsNullOrEmpty(audioB64))
                    {
                        try
                        {
                            byte[] audioBytes = Convert.FromBase64String(audioB64);
                            Debug.Log($"[FoveAI] Received audio event ({audioBytes.Length} bytes)");
                            OnAudioDataReceived?.Invoke(audioBytes);
                            PlayTtsAudio(audioBytes);
                        }
                        catch (Exception ex)
                        {
                            Debug.LogError($"[FoveAI] Failed to decode audio base64: {ex.Message}");
                        }
                    }
                }
                // ── Director events ──
                else if (eventType == "director.event")
                {
                    Debug.Log($"[FoveAI] Director event: {ExtractStringField(payloadJson, "eventType")}");
                    OnDirectorEventReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.suspense.build")
                {
                    Debug.Log("[FoveAI] Director suspense building...");
                    OnDirectorSuspenseBuildReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.suspense.threshold")
                {
                    Debug.Log("[FoveAI] Director suspense threshold");
                    OnDirectorSuspenseThresholdReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.suspense.abort")
                {
                    Debug.Log("[FoveAI] Director suspense aborted");
                    OnDirectorSuspenseAbort?.Invoke();
                }
                else if (eventType == "director.surprise")
                {
                    Debug.Log($"[FoveAI] Director surprise: {ExtractStringField(payloadJson, "surpriseType")}");
                    OnDirectorSurpriseReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.sequence")
                {
                    string seq = ExtractStringField(payloadJson, "sequence");
                    Debug.Log($"[FoveAI] Director sequence: {seq}");
                    OnDirectorSequenceReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.narration")
                {
                    OnDirectorNarrationReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.alice")
                {
                    OnDirectorAliceReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.tts")
                {
                    string text = ExtractStringField(payloadJson, "text");
                    string voice = ExtractStringField(payloadJson, "voice");
                    OnDirectorTTSReceived?.Invoke(text, voice);
                }
                else if (eventType == "seasonal.comment" || eventType == "seasonal.set")
                {
                    OnSeasonalReceived?.Invoke(payloadJson);
                }
                // ── Story Garden events ──
                else if (eventType == "director.garden.seed")
                {
                    Debug.Log($"[FoveAI] Garden seed planted: {ExtractStringField(payloadJson, "concept")}");
                    OnGardenSeedReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.garden.beat")
                {
                    Debug.Log($"[FoveAI] Garden beat: {ExtractStringField(payloadJson, "beat")}");
                    OnGardenBeatReceived?.Invoke(payloadJson);
                }
                else if (eventType == "director.garden.status")
                {
                    OnGardenStatusReceived?.Invoke(payloadJson);
                }
                else
                {
                    Debug.Log($"[FoveAI] Unhandled event type: {eventType}");
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[FoveAI] Failed to parse payload: {ex.Message}\nRaw: {json}");
            }
        }

        private void HandleChatResponse(string payloadJson)
        {
            string text = ExtractStringField(payloadJson, "text");
            string emotion = ExtractStringField(payloadJson, "emotion");
            float intensity = ExtractFloatField(payloadJson, "intensity");

            if (!string.IsNullOrEmpty(text))
            {
                OnChatTextReceived?.Invoke(text);
                Debug.Log($"[FoveAI] Chat text: {text}");
            }

            if (!string.IsNullOrEmpty(emotion))
            {
                OnEmotionReceived?.Invoke(emotion, intensity);

                // Route through the AnimationBrain — it manages state + animation
                if (animationBrain != null)
                {
                    animationBrain.OnBotResponse(text, emotion, intensity);
                }
                else if (avatarBlendshapeDriver != null)
                {
                    // Fallback: direct blendshape
                    avatarBlendshapeDriver.ApplyEmotion(emotion, intensity);
                }

                Debug.Log($"[FoveAI] Emotion: {emotion} @ {intensity:F2}");
            }
            else if (!string.IsNullOrEmpty(text) && animationBrain != null)
            {
                // Response without emotion tag — still transition to speaking
                animationBrain.OnBotResponse(text);
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  TTS Audio Playback
        // ─────────────────────────────────────────────────────────────

        /// <summary>
        /// Stop any currently playing TTS audio — used for interrupt handling.
        /// Called when the user starts speaking to allow natural conversation.
        /// </summary>
        public void StopTTS()
        {
            if (_ttsAudioSource != null && _ttsAudioSource.isPlaying)
            {
                _ttsAudioSource.Stop();
                Debug.Log("[FoveAI] TTS interrupted by user speech");
            }
            // Reset visemes
            if (avatarBlendshapeDriver != null)
            {
                avatarBlendshapeDriver.SetVisemeWeight("a", 0f);
                avatarBlendshapeDriver.SetVisemeWeight("i", 0f);
                avatarBlendshapeDriver.SetVisemeWeight("u", 0f);
                avatarBlendshapeDriver.SetVisemeWeight("e", 0f);
                avatarBlendshapeDriver.SetVisemeWeight("o", 0f);
            }
            StopAllCoroutines(); // Stop lip sync coroutine
        }

        private void PlayTtsAudio(byte[] wavBytes)
        {
            if (_ttsAudioSource == null || wavBytes == null || wavBytes.Length == 0) return;

            try
            {
                // Parse WAV header — find fmt and data chunks by scanning
                int sampleRate = 24000;
                int channels = 1;
                int bitsPerSample = 16;
                int dataOffset = 44;

                // Scan for "fmt " chunk
                for (int i = 0; i < wavBytes.Length - 8; i++)
                {
                    if (wavBytes[i] == (byte)'f' && wavBytes[i + 1] == (byte)'m' &&
                        wavBytes[i + 2] == (byte)'t' && wavBytes[i + 3] == (byte)' ')
                    {
                        int fmtOffset = i + 8;
                        channels = BitConverter.ToInt16(wavBytes, fmtOffset + 2);
                        sampleRate = BitConverter.ToInt32(wavBytes, fmtOffset + 4);
                        bitsPerSample = BitConverter.ToInt16(wavBytes, fmtOffset + 14);
                        break;
                    }
                }

                // Scan for "data" chunk
                for (int i = 12; i < wavBytes.Length - 8; i++)
                {
                    if (wavBytes[i] == (byte)'d' && wavBytes[i + 1] == (byte)'a' &&
                        wavBytes[i + 2] == (byte)'t' && wavBytes[i + 3] == (byte)'a')
                    {
                        dataOffset = i + 8;
                        break;
                    }
                }

                int bytesPerSample = bitsPerSample / 8;
                int dataBytes = wavBytes.Length - dataOffset;
                int sampleCount = dataBytes / (bytesPerSample * channels);
                float[] samples = new float[sampleCount];

                if (bitsPerSample == 16)
                {
                    for (int i = 0; i < sampleCount; i++)
                    {
                        short val = BitConverter.ToInt16(wavBytes, dataOffset + i * 2 * channels);
                        samples[i] = val / 32768f;
                    }
                }
                else if (bitsPerSample == 32)
                {
                    for (int i = 0; i < sampleCount; i++)
                    {
                        float val = BitConverter.ToSingle(wavBytes, dataOffset + i * 4 * channels);
                        samples[i] = val;
                    }
                }
                else if (bitsPerSample == 8)
                {
                    for (int i = 0; i < sampleCount; i++)
                    {
                        samples[i] = (wavBytes[dataOffset + i] - 128) / 128f;
                    }
                }

                AudioClip clip = AudioClip.Create("TTS_Response", sampleCount, 1, sampleRate, false);
                clip.SetData(samples, 0);
                if (_ttsAudioSource.clip != null) Destroy(_ttsAudioSource.clip);
                _ttsAudioSource.Stop();
                _ttsAudioSource.clip = clip;
                _ttsAudioSource.loop = false;
                _ttsAudioSource.Play();
                Debug.Log($"[FoveAI] Playing TTS audio: {sampleCount} samples at {sampleRate}Hz, {bitsPerSample}-bit, {channels}ch, offset={dataOffset}");

                // Start lip sync coroutine
                StartCoroutine(LipSyncCoroutine(clip));
            }
            catch (Exception ex)
            {
                Debug.LogError($"[FoveAI] TTS playback error: {ex.Message}");
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  Lip Sync — drive viseme blendshapes from audio amplitude
        // ─────────────────────────────────────────────────────────────

        private System.Collections.IEnumerator LipSyncCoroutine(AudioClip clip)
        {
            if (avatarBlendshapeDriver == null || clip == null)
                yield break;

            // Store the raw samples for amplitude analysis
            int totalSamples = clip.samples;
            float[] allSamples = new float[totalSamples];
            clip.GetData(allSamples, 0);

            // Viseme cycle — approximate mouth shapes
            string[] visemes = { "a", "i", "u", "e", "o" };
            int visemeIdx = 0;
            float visemeTimer = 0f;
            float visemeInterval = 0.08f; // Change viseme every 80ms

            int samplesPerFrame = (int)(clip.frequency * Time.deltaTime);
            if (samplesPerFrame < 1) samplesPerFrame = 256;
            int currentPos = 0;

            while (_ttsAudioSource != null && _ttsAudioSource.isPlaying && currentPos < totalSamples)
            {
                // Calculate RMS amplitude for this frame's chunk
                int chunkEnd = Mathf.Min(currentPos + samplesPerFrame, totalSamples);
                float sum = 0f;
                int count = 0;
                for (int i = currentPos; i < chunkEnd; i++)
                {
                    sum += allSamples[i] * allSamples[i];
                    count++;
                }
                float rms = count > 0 ? Mathf.Sqrt(sum / count) : 0f;

                // Map RMS to mouth open amount (0-1)
                float mouthOpen = Mathf.Clamp01(rms * 4f);

                // Cycle through visemes to simulate talking
                visemeTimer += Time.deltaTime;
                if (visemeTimer >= visemeInterval)
                {
                    visemeTimer = 0f;
                    visemeIdx = (visemeIdx + 1) % visemes.Length;
                }

                // Clear all visemes, then set current one
                foreach (string v in visemes)
                {
                    if (v != visemes[visemeIdx])
                        avatarBlendshapeDriver.SetVisemeWeight(v, 0f);
                }
                avatarBlendshapeDriver.SetVisemeWeight(visemes[visemeIdx], mouthOpen);

                currentPos += samplesPerFrame;
                yield return null;
            }

            // Reset all visemes when done
            foreach (string v in visemes)
            {
                avatarBlendshapeDriver.SetVisemeWeight(v, 0f);
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  Minimal JSON field extraction (no external dependency)
        // ─────────────────────────────────────────────────────────────

        private static string ExtractStringField(string json, string fieldName)
        {
            string key = "\"" + fieldName + "\"";
            int keyIdx = json.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (keyIdx < 0) return null;

            int colonIdx = json.IndexOf(':', keyIdx + key.Length);
            if (colonIdx < 0) return null;

            int valueStart = colonIdx + 1;
            // skip whitespace
            while (valueStart < json.Length && char.IsWhiteSpace(json[valueStart])) valueStart++;
            if (valueStart >= json.Length || json[valueStart] != '"') return null;

            valueStart++; // skip opening quote
            var sb = new StringBuilder();
            for (int i = valueStart; i < json.Length; i++)
            {
                char c = json[i];
                if (c == '\\' && i + 1 < json.Length)
                {
                    char next = json[i + 1];
                    switch (next)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 't': sb.Append('\t'); break;
                        case 'r': sb.Append('\r'); break;
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        default: sb.Append(next); break;
                    }
                    i++;
                }
                else if (c == '"')
                {
                    break;
                }
                else
                {
                    sb.Append(c);
                }
            }
            return sb.ToString();
        }

        private static float ExtractFloatField(string json, string fieldName)
        {
            string key = "\"" + fieldName + "\"";
            int keyIdx = json.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (keyIdx < 0) return 0f;

            int colonIdx = json.IndexOf(':', keyIdx + key.Length);
            if (colonIdx < 0) return 0f;

            int valueStart = colonIdx + 1;
            while (valueStart < json.Length && (char.IsWhiteSpace(json[valueStart]) || json[valueStart] == '"')) valueStart++;

            var sb = new StringBuilder();
            for (int i = valueStart; i < json.Length; i++)
            {
                char c = json[i];
                if (char.IsDigit(c) || c == '.' || c == '-' || c == '+' || c == 'e' || c == 'E')
                    sb.Append(c);
                else
                    break;
            }

            return float.TryParse(sb.ToString(), out float result) ? result : 0f;
        }

        private static string ExtractObjectField(string json, string fieldName)
        {
            string key = "\"" + fieldName + "\"";
            int keyIdx = json.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (keyIdx < 0) return json;

            int colonIdx = json.IndexOf(':', keyIdx + key.Length);
            if (colonIdx < 0) return json;

            int valueStart = colonIdx + 1;
            while (valueStart < json.Length && char.IsWhiteSpace(json[valueStart])) valueStart++;
            if (valueStart >= json.Length || json[valueStart] != '{') return json;

            int depth = 0;
            for (int i = valueStart; i < json.Length; i++)
            {
                if (json[i] == '{') depth++;
                else if (json[i] == '}')
                {
                    depth--;
                    if (depth == 0) return json.Substring(valueStart, i - valueStart + 1);
                }
            }
            return json;
        }

        private static string JsonEscape(string s)
        {
            if (string.IsNullOrEmpty(s)) return "\"\"";
            var sb = new StringBuilder(s.Length + 2);
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default: sb.Append(c); break;
                }
            }
            sb.Append('"');
            return sb.ToString();
        }
    }

    // ═══════════════════════════════════════════════════════════════
    //  Minimal WebSocket wrapper using Unity's NativeWebSocket pattern.
    //  Falls back to System.Net.WebSockets if NativeWebSocket is absent.
    // ═══════════════════════════════════════════════════════════════

    internal sealed class FoveAIWebSocket
    {
        public event Action OnOpen;
        public event Action<byte[]> OnMessage;
        public event Action<ushort, string> OnClose;
        public event Action<string> OnError;

        public bool IsOpen => _state == State.Open;

        private enum State { Idle, Connecting, Open, Closed }
        private State _state = State.Idle;

        private readonly Uri _uri;
        private System.Net.WebSockets.ClientWebSocket _ws;
        private CancellationTokenSource _cts;

        public FoveAIWebSocket(Uri uri) => _uri = uri;

        public async Task Connect()
        {
            _cts = new CancellationTokenSource();
            _ws = new System.Net.WebSockets.ClientWebSocket();
            _state = State.Connecting;

            try
            {
                await _ws.ConnectAsync(_uri, _cts.Token);
                _state = State.Open;
                OnOpen?.Invoke();
                _ = ReceiveLoop(_cts.Token);
            }
            catch (Exception ex)
            {
                _state = State.Closed;
                OnError?.Invoke(ex.Message);
            }
        }

        private async Task ReceiveLoop(CancellationToken ct)
        {
            var buffer = new ArraySegment<byte>(new byte[8192]);
            var messageBuffer = new System.Collections.Generic.List<byte>();

            try
            {
                while (_state == State.Open && !ct.IsCancellationRequested)
                {
                    System.Net.WebSockets.WebSocketReceiveResult result;
                    messageBuffer.Clear();

                    do
                    {
                        result = await _ws.ReceiveAsync(buffer, ct);
                        if (result.MessageType == System.Net.WebSockets.WebSocketMessageType.Close)
                        {
                            _state = State.Closed;
                            OnClose?.Invoke((ushort)result.CloseStatus, result.CloseStatusDescription);
                            return;
                        }
                        if (result.Count > 0)
                        {
                            var chunk = new byte[result.Count];
                            System.Array.Copy(buffer.Array, chunk, result.Count);
                            messageBuffer.AddRange(chunk);
                        }
                    }
                    while (!result.EndOfMessage);

                    if (messageBuffer.Count > 0)
                        OnMessage?.Invoke(messageBuffer.ToArray());
                }
            }
            catch (Exception ex)
            {
                if (_state != State.Closed)
                {
                    _state = State.Closed;
                    OnError?.Invoke(ex.Message);
                    OnClose?.Invoke(1006, ex.Message);
                }
            }
        }

        public void SendString(string text)
        {
            if (_state != State.Open || _ws == null) return;
            byte[] bytes = Encoding.UTF8.GetBytes(text);
            _ = _ws.SendAsync(new ArraySegment<byte>(bytes), System.Net.WebSockets.WebSocketMessageType.Text, true, _cts.Token);
        }

        public void Close()
        {
            _state = State.Closed;
            try { _cts?.Cancel(); } catch { }
            try { _ws?.Dispose(); } catch { }
        }
    }
}