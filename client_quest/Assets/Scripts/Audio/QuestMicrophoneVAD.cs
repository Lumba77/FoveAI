using System;
using System.IO;
using System.Text;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
#if UNITY_ANDROID
using UnityEngine.Android;
#endif

namespace FoveAI.Audio
{
    /// <summary>
    /// QuestMicrophoneVAD — Automatic Voice Activity Detection on Meta Quest 3.
    /// Continuously monitors the headset microphone, detects when the user begins speaking,
    /// buffers the audio, and automatically transcribes via Ears STT (:8001) upon silence.
    /// Automatically mutes while the avatar is speaking to prevent acoustic feedback loops.
    /// </summary>
    public class QuestMicrophoneVAD : MonoBehaviour
    {
        [Header("VAD Sensitivity")]
        [Tooltip("RMS audio amplitude threshold to detect speech start.")]
        [SerializeField] private float speechThreshold = 0.008f;

        [Tooltip("Seconds of silence after speaking to consider utterance finished.")]
        [SerializeField] private float silenceDuration = 0.45f;

        [Tooltip("Minimum utterance duration in seconds to filter out mouth clicks/coughs.")]
        [SerializeField] private float minSpeechDuration = 0.15f;

        [Tooltip("Maximum utterance duration in seconds before forcing transcription.")]
        [SerializeField] private float maxSpeechDuration = 12.0f;

        [Header("Audio Settings")]
        [SerializeField] private int sampleRate = 16000;
        [SerializeField] private int recordingBufferSeconds = 10;

        [Header("Dependencies")]
        [SerializeField] private AvatarVoice avatarVoice;
        public FoveAI.IPC.FoveAIWebSocketClient webSocketClient;
        [SerializeField] private FoveAI.UI.SpatialUIManager uiManager;
        [SerializeField] private FoveAI.UI.UserHUD hud;

        public bool IsUserSpeaking { get; private set; }
        public float CurrentRms { get; private set; }
        public float CurrentRMS => CurrentRms;
        public bool IsRecordingSpeech => _isRecordingSpeech;

        private AudioClip _micClip;
        private string _micDevice;
        private int _lastSamplePos;
        private bool _isRecordingSpeech;
        private float _speechTimer;
        private float _silenceTimer;
        private List<float> _recordedSamples = new List<float>();
        private string _sttUrl;

        private void Start()
        {
            StartCoroutine(InitVADRoutine());
        }

        private IEnumerator InitVADRoutine()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (!Permission.HasUserAuthorizedPermission(Permission.Microphone))
            {
                Permission.RequestUserPermission(Permission.Microphone);
                float waitTimer = 0f;
                while (!Permission.HasUserAuthorizedPermission(Permission.Microphone) && waitTimer < 10f)
                {
                    yield return new WaitForSeconds(0.5f);
                    waitTimer += 0.5f;
                }
            }
#endif
            yield return new WaitForSeconds(0.5f);

            var configTask = FoveAI.Config.ConfigLoader.LoadConfigAsync();
            while (!configTask.IsCompleted) yield return null;
            var settings = FoveAI.Config.ConfigLoader.Settings;
            if (settings != null)
            {
                _sttUrl = $"http://{settings.serverIp}:{settings.wsPort}/stt";
            }

            if (avatarVoice == null) avatarVoice = FindAnyObjectByType<AvatarVoice>();
            if (webSocketClient == null) webSocketClient = FindAnyObjectByType<FoveAI.IPC.FoveAIWebSocketClient>();
            if (uiManager == null) uiManager = FindAnyObjectByType<FoveAI.UI.SpatialUIManager>();

            // Retry until microphone is successfully acquired
            int retries = 0;
            while (_micClip == null && retries < 15)
            {
                StartMicrophone();
                if (_micClip != null) break;
                retries++;
                yield return new WaitForSeconds(1.0f);
            }
        }

        private void StartMicrophone()
        {
            if (Microphone.devices.Length == 0)
            {
                Debug.LogWarning("[QuestMicrophoneVAD] No microphone found on device yet.");
                return;
            }

            _micDevice = Microphone.devices[0];
            try
            {
                _micClip = Microphone.Start(_micDevice, true, recordingBufferSeconds, sampleRate);
                _lastSamplePos = 0;
                Debug.Log($"[QuestMicrophoneVAD] Started listening on '{_micDevice}' ({sampleRate} Hz)");
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[QuestMicrophoneVAD] Could not start mic '{_micDevice}': {ex.Message}");
            }
        }

        private void Update()
        {
            if (_micClip == null || string.IsNullOrEmpty(_micDevice)) return;

            // Duck VAD when Avatar is actively speaking to prevent echo
            if (avatarVoice != null && avatarVoice.IsSpeaking)
            {
                if (_isRecordingSpeech)
                {
                    CancelRecording();
                }
                return;
            }

            int currentPos = Microphone.GetPosition(_micDevice);
            if (currentPos < 0 || currentPos == _lastSamplePos) return;

            // Calculate chunk length
            int sampleCount = currentPos - _lastSamplePos;
            if (sampleCount < 0)
            {
                // Circular wrap
                sampleCount = (_micClip.samples - _lastSamplePos) + currentPos;
            }

            if (sampleCount <= 0) return;

            float[] chunk = new float[sampleCount];
            _micClip.GetData(chunk, _lastSamplePos);
            _lastSamplePos = currentPos;

            // Compute RMS
            float sum = 0f;
            for (int i = 0; i < chunk.Length; i++)
            {
                sum += chunk[i] * chunk[i];
            }
            CurrentRms = Mathf.Sqrt(sum / chunk.Length);

            // VAD State Machine
            if (CurrentRms >= speechThreshold)
            {
                if (!_isRecordingSpeech)
                {
                    _isRecordingSpeech = true;
                    IsUserSpeaking = true;
                    _speechTimer = 0f;
                    _silenceTimer = 0f;
                    _recordedSamples.Clear();
                    Debug.Log("[QuestMicrophoneVAD] Speech started...");
                    if (uiManager != null) uiManager.SetDictation(true);
                    if (hud == null) hud = FindAnyObjectByType<FoveAI.UI.UserHUD>();
                    if (hud != null) hud.SetListening(true);

                    // Interrupt TTS — stop Alice's voice when user starts speaking
                    if (webSocketClient != null)
                        webSocketClient.StopTTS();
                }

                _silenceTimer = 0f;
                _speechTimer += Time.deltaTime;
                _recordedSamples.AddRange(chunk);

                if (_speechTimer >= maxSpeechDuration)
                {
                    EndSpeechAndTranscribe();
                }
            }
            else if (_isRecordingSpeech)
            {
                _speechTimer += Time.deltaTime;
                _silenceTimer += Time.deltaTime;
                _recordedSamples.AddRange(chunk);

                if (_silenceTimer >= silenceDuration)
                {
                    EndSpeechAndTranscribe();
                }
            }
        }

        private void EndSpeechAndTranscribe()
        {
            _isRecordingSpeech = false;
            IsUserSpeaking = false;
            if (uiManager != null) uiManager.SetDictation(false);
            if (hud != null) hud.SetListening(false);

            if (_speechTimer < minSpeechDuration || _recordedSamples.Count == 0)
            {
                Debug.Log("[QuestMicrophoneVAD] Speech too short, ignoring click.");
                _recordedSamples.Clear();
                return;
            }

            Debug.Log($"[QuestMicrophoneVAD] Speech ended ({_speechTimer:F1}s, {_recordedSamples.Count} samples). Transcribing...");
            float[] finalSamples = _recordedSamples.ToArray();
            _recordedSamples.Clear();

            StartCoroutine(SendAudioToEarsSTT(finalSamples));
        }

        public void ToggleManualRecording()
        {
            if (_isRecordingSpeech)
            {
                EndSpeechAndTranscribe();
            }
            else
            {
                StartManualRecording();
            }
        }

        public void StartManualRecording()
        {
            _isRecordingSpeech = true;
            IsUserSpeaking = true;
            _speechTimer = 0f;
            _silenceTimer = 0f;
            _recordedSamples.Clear();
            Debug.Log("[QuestMicrophoneVAD] Manual recording started via Dictate button");
            if (uiManager != null) uiManager.SetDictation(true);
        }

        private void CancelRecording()
        {
            _isRecordingSpeech = false;
            IsUserSpeaking = false;
            _recordedSamples.Clear();
            if (uiManager != null) uiManager.SetDictation(false);
        }

        private IEnumerator SendAudioToEarsSTT(float[] samples)
        {
            byte[] wavBytes = EncodeToWav(samples, sampleRate, 1);
            string base64Wav = Convert.ToBase64String(wavBytes);

            // 1. Direct WebSocket IPC: send audio event over open socket (Port 8403)
            if (webSocketClient != null && webSocketClient.IsConnected)
            {
                Debug.Log("[QuestMicrophoneVAD] Streaming audio over WebSocket IPC :8403...");
                webSocketClient.SendEvent("audio", $"{{\"audio_base64\":\"{base64Wav}\",\"format\":\"wav\"}}");
                
                // Immediately trigger Alice's thinking state in AvatarAnimationBrain
                var brain = FindAnyObjectByType<FoveAI.Avatar.AvatarAnimationBrain>();
                if (brain != null) brain.OnUserMessage();
                yield break;
            }

            // 2. HTTP Fallback to Diamond Concordia Ears STT (Port 8001)
            string serverIp = FoveAI.Config.ConfigLoader.Settings != null ? FoveAI.Config.ConfigLoader.Settings.serverIp : "192.168.8.100";
            string fallbackUrl = $"http://{serverIp}:8001/stt";
            string jsonPayload = $"{{\"audio_base64\":\"{base64Wav}\"}}";
            using (UnityWebRequest req = new UnityWebRequest(fallbackUrl, "POST"))
            {
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonPayload);
                req.uploadHandler = new UploadHandlerRaw(bodyRaw);
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");

                yield return req.SendWebRequest();

                if (req.result == UnityWebRequest.Result.Success)
                {
                    string responseText = req.downloadHandler.text;
                    Debug.Log($"[QuestMicrophoneVAD] STT Response: {responseText}");

                    string transcribedText = ExtractTextField(responseText);
                    if (!string.IsNullOrWhiteSpace(transcribedText))
                    {
                        Debug.Log($"[QuestMicrophoneVAD] Transcribed: \"{transcribedText}\"");
                        if (uiManager != null)
                        {
                            var input = uiManager.GetComponentInChildren<TMPro.TMP_InputField>();
                            if (input != null) input.text = transcribedText;
                        }
                        if (webSocketClient != null)
                        {
                            webSocketClient.SendChatMessage(transcribedText);
                        }
                    }
                }
                else
                {
                    Debug.LogWarning($"[QuestMicrophoneVAD] STT fallback failed ({req.responseCode}): {req.error}");
                }
            }
        }

        private string ExtractTextField(string json)
        {
            int idx = json.IndexOf("\"text\"");
            if (idx < 0) idx = json.IndexOf("\"transcription\"");
            if (idx >= 0)
            {
                int colon = json.IndexOf(':', idx);
                int firstQuote = json.IndexOf('\"', colon + 1);
                int secondQuote = json.IndexOf('\"', firstQuote + 1);
                if (firstQuote >= 0 && secondQuote > firstQuote)
                {
                    return json.Substring(firstQuote + 1, secondQuote - firstQuote - 1);
                }
            }
            return null;
        }

        private byte[] EncodeToWav(float[] samples, int hz, int channels)
        {
            using (MemoryStream stream = new MemoryStream())
            using (BinaryWriter writer = new BinaryWriter(stream))
            {
                int byteRate = hz * channels * 2;
                int dataLength = samples.Length * 2;

                // RIFF chunk header
                writer.Write(Encoding.ASCII.GetBytes("RIFF"));
                writer.Write(36 + dataLength);
                writer.Write(Encoding.ASCII.GetBytes("WAVE"));

                // fmt sub-chunk
                writer.Write(Encoding.ASCII.GetBytes("fmt "));
                writer.Write(16); // Subchunk1Size for PCM
                writer.Write((short)1); // AudioFormat: 1 = PCM
                writer.Write((short)channels);
                writer.Write(hz);
                writer.Write(byteRate);
                writer.Write((short)(channels * 2)); // BlockAlign
                writer.Write((short)16); // BitsPerSample

                // data sub-chunk
                writer.Write(Encoding.ASCII.GetBytes("data"));
                writer.Write(dataLength);

                for (int i = 0; i < samples.Length; i++)
                {
                    short sampleInt = (short)Mathf.Clamp(samples[i] * 32767f, -32768f, 32767f);
                    writer.Write(sampleInt);
                }

                return stream.ToArray();
            }
        }
    }
}
