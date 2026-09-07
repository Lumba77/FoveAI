using UnityEngine;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Bridges TTS speech events and STT listening events to the
    /// AvatarAnimationBrain, so the brain knows when the avatar is
    /// speaking vs. listening vs. idle.
    ///
    /// This enables the full conversation state machine:
    ///   IDLE → LISTENING (mic starts) → THINKING (message sent)
    ///   → SPEAKING (TTS starts) → IDLE (TTS ends)
    /// </summary>
    public class TTSConversationBridge : MonoBehaviour
    {
        [SerializeField] private Lumax.Quest3Bridge.Quest3TTSClient ttsClient;
        [SerializeField] private Lumax.Quest3Bridge.Quest3STTClient sttClient;
        [SerializeField] private AvatarAnimationBrain brain;

        private void Start()
        {
            if (ttsClient == null)
                ttsClient = GetComponentInChildren<Lumax.Quest3Bridge.Quest3TTSClient>();
            if (sttClient == null)
                sttClient = GetComponentInChildren<Lumax.Quest3Bridge.Quest3STTClient>();
            if (brain == null)
                brain = GetComponentInChildren<AvatarAnimationBrain>();

            if (ttsClient != null)
            {
                ttsClient.OnTTSStart += OnTTSStart;
                ttsClient.OnTTSEnd += OnTTSEnd;
                Debug.Log("[TTSConversationBridge] Wired TTS events");
            }

            if (sttClient != null)
            {
                sttClient.OnListeningStart += OnListeningStart;
                sttClient.OnListeningEnd += OnListeningEnd;
                Debug.Log("[TTSConversationBridge] Wired STT events");
            }
        }

        public void SetBrain(AvatarAnimationBrain animationBrain)
        {
            brain = animationBrain;
        }

        private void OnDestroy()
        {
            if (ttsClient != null)
            {
                ttsClient.OnTTSStart -= OnTTSStart;
                ttsClient.OnTTSEnd -= OnTTSEnd;
            }
            if (sttClient != null)
            {
                sttClient.OnListeningStart -= OnListeningStart;
                sttClient.OnListeningEnd -= OnListeningEnd;
            }
        }

        // ── TTS Events ──

        private void OnTTSStart()
        {
            if (sttClient != null) sttClient.PauseCapture();
            if (brain != null && brain.conversationState != AvatarAnimationBrain.ConversationState.Speaking)
            {
                brain.SetConversationState(AvatarAnimationBrain.ConversationState.Speaking);
            }
        }

        private void OnTTSEnd(int durationMs)
        {
            if (brain != null)
            {
                brain.OnSpeechEnd();
            }
            if (sttClient != null) sttClient.ResumeCapture();
        }

        // ── STT Events ──

        private void OnListeningStart()
        {
            if (brain != null)
            {
                brain.OnListeningStart();
            }
        }

        private void OnListeningEnd()
        {
            if (brain != null)
            {
                brain.OnListeningEnd();
            }
        }
    }
}
