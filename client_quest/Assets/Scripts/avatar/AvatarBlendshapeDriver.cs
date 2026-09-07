using System.Collections.Generic;
using UnityEngine;
using VRM;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Drives VRM 0.x avatar facial expressions (blendshapes) and visemes from IPC events.
    /// Receives emotion + intensity from FoveAIWebSocketClient and maps them
    /// to the corresponding BlendShapeKey on the VRMBlendShapeProxy.
    /// </summary>
    public class AvatarBlendshapeDriver : MonoBehaviour
    {
        [Header("VRM Avatar")]
        [Tooltip("The VRM BlendShapeProxy to drive. If left null, it will search for one in child objects.")]
        [SerializeField] private VRMBlendShapeProxy blendShapeProxy;

        [Header("Smoothing")]
        [Tooltip("How fast expression weights lerp toward target (0 = instant).")]
        [SerializeField] private float lerpSpeed = 8f;

        [Tooltip("Expressions return to 0 when no emotion is received for this many seconds.")]
        [SerializeField] private float emotionDecayTime = 5f;

        // Current target weights keyed by BlendShapeKey
        private readonly Dictionary<BlendShapeKey, float> _targetWeights = new Dictionary<BlendShapeKey, float>();
        private float _lastEmotionTime;
        private bool _isDecaying;

        // ─────────────────────────────────────────────────────────────
        //  Public API
        // ─────────────────────────────────────────────────────────────

        /// <summary>
        /// Apply an emotion with a normalized intensity (0–1).
        /// </summary>
        public void ApplyEmotion(string emotion, float intensity)
        {
            EnsureBlendShapeProxy();
            if (blendShapeProxy == null) return;

            BlendShapeKey key = ResolveBlendShapeKey(emotion);

            float weight = Mathf.Clamp01(intensity);

            _targetWeights.Clear();
            _targetWeights[key] = weight;

            _lastEmotionTime = Time.time;
            _isDecaying = false;
        }

        /// <summary>
        /// Drive a viseme expression by name (lip-sync).
        /// </summary>
        public void SetVisemeWeight(string visemeName, float weight)
        {
            EnsureBlendShapeProxy();
            if (blendShapeProxy == null) return;

            BlendShapeKey key = ResolveBlendShapeKey(visemeName);
            blendShapeProxy.ImmediatelySetValue(key, Mathf.Clamp01(weight));
        }

        /// <summary>
        /// Reset all tracked emotion weights to zero.
        /// </summary>
        public void ClearEmotion()
        {
            _targetWeights.Clear();
            _isDecaying = true;
        }

        // ─────────────────────────────────────────────────────────────
        //  Unity lifecycle
        // ─────────────────────────────────────────────────────────────

        private void Update()
        {
            EnsureBlendShapeProxy();
            if (blendShapeProxy == null) return;

            if (!_isDecaying && _targetWeights.Count > 0 && Time.time - _lastEmotionTime > emotionDecayTime)
            {
                _isDecaying = true;
            }

            if (_isDecaying)
            {
                var keys = new List<BlendShapeKey>(_targetWeights.Keys);
                foreach (var key in keys)
                {
                    _targetWeights[key] = Mathf.Lerp(_targetWeights[key], 0f, Time.deltaTime * lerpSpeed);
                    if (_targetWeights[key] < 0.005f)
                    {
                        blendShapeProxy.ImmediatelySetValue(key, 0f);
                        _targetWeights.Remove(key);
                    }
                }
                if (_targetWeights.Count == 0)
                    _isDecaying = false;
            }

            foreach (var kvp in _targetWeights)
            {
                float current = blendShapeProxy.GetValue(kvp.Key);
                float target = kvp.Value;
                if (lerpSpeed <= 0f)
                {
                    blendShapeProxy.ImmediatelySetValue(kvp.Key, target);
                }
                else
                {
                    float smoothed = Mathf.Lerp(current, target, Time.deltaTime * lerpSpeed);
                    blendShapeProxy.ImmediatelySetValue(kvp.Key, smoothed);
                }
            }
        }

        // ─────────────────────────────────────────────────────────────
        //  Helpers
        // ─────────────────────────────────────────────────────────────

        private void EnsureBlendShapeProxy()
        {
            if (blendShapeProxy == null)
            {
                blendShapeProxy = GetComponentInChildren<VRMBlendShapeProxy>();
            }
        }

        private BlendShapeKey ResolveBlendShapeKey(string emotion)
        {
            if (string.IsNullOrEmpty(emotion)) return default;
            string e = emotion.ToLowerInvariant().Trim();
            switch (e)
            {
                case "joy":
                case "happy":
                case "happiness":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.Joy);
                case "sad":
                case "sadness":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.Sorrow);
                case "angry":
                case "anger":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.Angry);
                case "surprise":
                case "surprised":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.Fun);
                case "fear":
                case "afraid":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.Fun);
                case "disgust":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.Angry);
                case "neutral":
                case "calm":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.Neutral);
                
                // Visemes (A, I, U, E, O)
                case "aa":
                case "a":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.A);
                case "ih":
                case "i":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.I);
                case "ou":
                case "u":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.U);
                case "ee":
                case "e":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.E);
                case "oh":
                case "o":
                    return BlendShapeKey.CreateFromPreset(BlendShapePreset.O);

                default:
                    return BlendShapeKey.CreateUnknown(emotion);
            }
        }
    }
}