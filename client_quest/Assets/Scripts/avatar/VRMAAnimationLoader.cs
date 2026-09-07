using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UniGLTF;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Loads VRMA (VRM Animation) files at runtime from StreamingAssets and
    /// plays them on the avatar using the PlayableGraph API.
    ///
    /// VRMA clips are humanoid animation clips. They CANNOT be played through
    /// the legacy Animation component — they require the Animator's Avatar for
    /// muscle-space retargeting. This loader uses AnimationClipPlayable within
    /// a PlayableGraph connected to the Animator, which correctly retargets
    /// humanoid muscle curves to the VRM skeleton.
    ///
    /// Emotion → Animation mapping:
    ///   angry      → Angry.vrma
    ///   sad        → Sad.vrma
    ///   thinking   → Thinking.vrma
    ///   surprised  → Surprised.vrma
    ///   relax/idle → Relax.vrma
    ///   happy      → VRMA_01.vrma
    ///   goodbye    → Goodbye.vrma
    ///   clapping   → Clapping.vrma
    /// </summary>
    public class VRMAAnimationLoader : MonoBehaviour
    {
        [Tooltip("Directory in StreamingAssets containing .vrma files.")]
        [SerializeField] private string animationDirectory = "Animations";

        [Tooltip("The Animator component on the avatar.")]
        [SerializeField] private Animator targetAnimator;

        [Tooltip("Default idle animation to play on startup.")]
        [SerializeField] private string defaultAnimation = "Relax";

        // Loaded animation clips keyed by lowercase name (e.g. "angry" → clip)
        private readonly Dictionary<string, AnimationClip> _clips = new Dictionary<string, AnimationClip>();

        // PlayableGraph for runtime humanoid clip playback
        private PlayableGraph _graph;
        private AnimationClipPlayable _clipPlayable;
        private AnimationPlayableOutput _playableOutput;

        // Currently playing clip name
        private string _currentClip;
        private bool _currentClipLoops;
        private float _clipPlayTime;
        private float _clipDuration;

        // Emotion → VRMA file name mapping
        private static readonly Dictionary<string, string> EmotionMap = new Dictionary<string, string>
        {
            { "angry", "Angry.vrma" },
            { "sad", "Sad.vrma" },
            { "thinking", "Thinking.vrma" },
            { "surprised", "Surprised.vrma" },
            { "relax", "Relax.vrma" },
            { "idle", "Relax.vrma" },
            { "happy", "VRMA_01.vrma" },
            { "goodbye", "Goodbye.vrma" },
            { "clapping", "Clapping.vrma" },
            { "sleepy", "Sleepy.vrma" },
            { "blush", "Blush.vrma" },
            { "lookaround", "LookAround.vrma" },
            { "jump", "Jump.vrma" },
            { "waiting", "waiting-standard.vrma" },
        };

        private async void Start()
        {
            if (targetAnimator == null)
            {
                targetAnimator = GetComponentInChildren<Animator>();
            }

            // Wait a few frames for the VRM to fully load and the Animator to be configured
            for (int i = 0; i < 10 && targetAnimator == null; i++)
            {
                await Task.Yield();
                targetAnimator = GetComponentInChildren<Animator>();
            }

            // Initialize PlayableGraph for humanoid clip playback
            if (targetAnimator != null && targetAnimator.avatar != null)
            {
                // Keep the Animator enabled — it's needed for humanoid retargeting
                targetAnimator.enabled = true;
                targetAnimator.runtimeAnimatorController = null; // PlayableGraph drives directly

                _graph = PlayableGraph.Create("VRMAPlayback");
                _graph.SetTimeUpdateMode(DirectorUpdateMode.GameTime);

                _playableOutput = AnimationPlayableOutput.Create(_graph, "Animation", targetAnimator);

                // Create an empty playable as initial source
                _clipPlayable = AnimationClipPlayable.Create(_graph, null);
                _playableOutput.SetSourcePlayable(_clipPlayable);

                _graph.Play();
                Debug.Log("[VRMAAnimationLoader] PlayableGraph initialized for humanoid playback");
            }
            else
            {
                Debug.LogWarning($"[VRMAAnimationLoader] No humanoid Animator found (animator={targetAnimator != null}, avatar={targetAnimator?.avatar != null}) — VRMA body clips will not play. Only IK/blendshapes will work.");
            }

            await LoadAllAnimationsAsync();

            // Play default idle animation
            if (!string.IsNullOrEmpty(defaultAnimation) && _graph.IsValid())
            {
                PlayAnimation(defaultAnimation);
            }
        }

        /// <summary>
        /// Load all .vrma files from StreamingAssets/Animations into memory.
        /// On Android, StreamingAssets are inside the APK and must be read via UnityWebRequest.
        /// </summary>
        public async Task LoadAllAnimationsAsync()
        {
            string animPath = Path.Combine(Application.streamingAssetsPath, animationDirectory);

#if UNITY_ANDROID && !UNITY_EDITOR
            // On Android, StreamingAssets are inside the APK jar — we need UnityWebRequest to list files.
            // Since we can't enumerate files in a jar, we use a hardcoded list of expected VRMA files.
            string[] expectedFiles = {
                "Angry.vrma", "Sad.vrma", "Thinking.vrma", "Surprised.vrma", "Relax.vrma",
                "Goodbye.vrma", "Clapping.vrma", "Sleepy.vrma", "Blush.vrma",
                "LookAround.vrma", "Jump.vrma", "VRMA_01.vrma", "VRMA_02.vrma",
                "VRMA_03.vrma", "VRMA_04.vrma", "VRMA_05.vrma", "VRMA_06.vrma",
                "VRMA_07.vrma", "waiting-standard.vrma",
            };

            foreach (var fileName in expectedFiles)
            {
                string fileUrl = Application.streamingAssetsPath + "/Animations/" + fileName;
                byte[] bytes = await LoadFileAsync(fileUrl);
                if (bytes != null && bytes.Length > 0)
                {
                    string clipName = Path.GetFileNameWithoutExtension(fileName).ToLowerInvariant();
                    AnimationClip clip = await LoadVrmaClipAsync(bytes, clipName);
                    if (clip != null)
                    {
                        _clips[clipName] = clip;
                        Debug.Log($"[VRMAAnimationLoader] Loaded: {fileName} → '{clipName}' ({clip.length:F2}s)");
                    }
                }
            }
#else
            if (!Directory.Exists(animPath))
            {
                Debug.LogWarning($"[VRMAAnimationLoader] Animation directory not found: {animPath}");
                return;
            }

            var vrmaFiles = Directory.GetFiles(animPath, "*.vrma");
            Debug.Log($"[VRMAAnimationLoader] Found {vrmaFiles.Length} VRMA files in {animPath}");

            foreach (var filePath in vrmaFiles)
            {
                string fileName = Path.GetFileName(filePath);
                string clipName = Path.GetFileNameWithoutExtension(filePath).ToLowerInvariant();

                try
                {
                    byte[] bytes = File.ReadAllBytes(filePath);
                    AnimationClip clip = await LoadVrmaClipAsync(bytes, clipName);
                    if (clip != null)
                    {
                        _clips[clipName] = clip;
                        Debug.Log($"[VRMAAnimationLoader] Loaded: {fileName} → '{clipName}' ({clip.length:F2}s)");
                    }
                }
                catch (System.Exception ex)
                {
                    Debug.LogWarning($"[VRMAAnimationLoader] Failed to load {fileName}: {ex.Message}");
                }
            }
#endif
            Debug.Log($"[VRMAAnimationLoader] Total clips loaded: {_clips.Count}");
        }

        /// <summary>
        /// Load a file via UnityWebRequest (needed on Android where StreamingAssets are in the APK).
        /// </summary>
        private async Task<byte[]> LoadFileAsync(string url)
        {
            using (UnityEngine.Networking.UnityWebRequest uwr = UnityEngine.Networking.UnityWebRequest.Get(url))
            {
                var operation = uwr.SendWebRequest();
                while (!operation.isDone) await Task.Yield();

                if (uwr.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                {
                    return uwr.downloadHandler.data;
                }
                else
                {
                    Debug.LogWarning($"[VRMAAnimationLoader] Failed to load {url}: {uwr.error}");
                    return null;
                }
            }
        }

        /// <summary>
        /// Parse a VRMA (GLB) byte array and extract the first AnimationClip using UniGLTF.
        /// Clips are kept as humanoid (legacy = false) so the Animator can retarget them.
        /// </summary>
        private async Task<AnimationClip> LoadVrmaClipAsync(byte[] glbBytes, string clipName)
        {
            try
            {
                // VRMA files are GLB format — use GlbBinaryParser to parse
                var gltfData = new GlbBinaryParser(glbBytes, clipName).Parse();

                if (gltfData?.GLTF?.animations == null || gltfData.GLTF.animations.Count == 0)
                {
                    Debug.LogWarning($"[VRMAAnimationLoader] No animations found in {clipName}");
                    gltfData?.Dispose();
                    return null;
                }

                // Use ImporterContext with animation loading enabled
                var settings = new ImporterContextSettings(loadAnimation: true);
                var context = new ImporterContext(gltfData, settings: settings);

                // Use RuntimeOnlyAwaitCaller for proper async behavior on device
                var awaitCaller = new RuntimeOnlyAwaitCaller();
                var instance = await context.LoadAsync(awaitCaller);

                AnimationClip resultClip = null;
                if (context.AnimationClipFactory.LoadedClipKeys.Count > 0)
                {
                    var key = context.AnimationClipFactory.LoadedClipKeys[0];
                    resultClip = context.AnimationClipFactory.GetAnimationClip(key);
                    if (resultClip != null)
                    {
                        resultClip.name = clipName;
                        // Keep legacy = false so the Animator treats it as a humanoid clip
                        // and retargets muscle curves to the VRM skeleton.
                        resultClip.legacy = false;
                        bool isLoop = clipName.Contains("relax") || clipName.Contains("idle") || clipName.Contains("waiting");
                        if (isLoop)
                        {
                            // Set wrap mode for looping idle animations
                            resultClip.wrapMode = WrapMode.Loop;
                        }
                    }
                }

                // Transfer ownership so the clip survives context disposal
                context.TransferOwnership((k, obj) => { });

                // Clean up the geometry (we only need the animation clip, not the mesh)
                if (instance != null)
                {
                    Destroy(instance.gameObject);
                }

                return resultClip;
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[VRMAAnimationLoader] Failed to parse {clipName}: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Play an animation by name (case-insensitive).
        /// Uses the PlayableGraph to play the humanoid clip through the Animator.
        /// </summary>
        public bool PlayAnimation(string name)
        {
            string key = name.ToLowerInvariant();

            // Direct clip name match
            if (_clips.TryGetValue(key, out var clip))
            {
                PlayClipViaGraph(clip, key);
                return true;
            }

            // Emotion mapping
            if (EmotionMap.TryGetValue(key, out var fileName))
            {
                string clipKey = Path.GetFileNameWithoutExtension(fileName).ToLowerInvariant();
                if (_clips.TryGetValue(clipKey, out clip))
                {
                    PlayClipViaGraph(clip, clipKey);
                    Debug.Log($"[VRMAAnimationLoader] Playing emotion '{key}': {clipKey}");
                    return true;
                }
            }

            Debug.LogWarning($"[VRMAAnimationLoader] Animation not found: {name}");
            return false;
        }

        private void PlayClipViaGraph(AnimationClip clip, string clipKey)
        {
            if (!_graph.IsValid())
            {
                Debug.LogWarning("[VRMAAnimationLoader] PlayableGraph not valid — cannot play clip");
                return;
            }

            // Destroy the old clip playable and create a new one with the new clip
            if (_clipPlayable.IsValid())
            {
                _clipPlayable.Destroy();
            }

            _clipPlayable = AnimationClipPlayable.Create(_graph, clip);

            // Configure looping for idle/relax/waiting animations
            bool isLoop = clipKey.Contains("relax") || clipKey.Contains("idle") || clipKey.Contains("waiting");
            _clipPlayable.SetApplyFootIK(true);
            _clipPlayable.SetApplyPlayableIK(true);

            _playableOutput.SetSourcePlayable(_clipPlayable);
            _currentClip = clipKey;
            _currentClipLoops = isLoop;
            _clipPlayTime = 0f;
            _clipDuration = clip.length;

            Debug.Log($"[VRMAAnimationLoader] Playing: {clipKey} (humanoid, loop={isLoop}, duration={clip.length:F2}s)");
        }

        private void Update()
        {
            // Auto-return to idle for non-looping clips when they finish
            if (!_currentClipLoops && !string.IsNullOrEmpty(_currentClip) && _currentClip != "relax" && _currentClip != "idle")
            {
                _clipPlayTime += Time.deltaTime;
                if (_clipPlayTime >= _clipDuration)
                {
                    // Non-looping clip finished — return to idle
                    PlayAnimation("relax");
                }
            }
        }

        /// <summary>
        /// Play an emotion animation. Called by CognitiveRouter when [EMOTION: "angry"] is received.
        /// </summary>
        public bool PlayEmotion(string emotion)
        {
            return PlayAnimation(emotion);
        }

        /// <summary>
        /// Crossfade to a new animation over the specified duration.
        /// Uses PlayableGraph's built-in crossfade via AnimationMixerPlayable.
        /// </summary>
        public bool CrossFade(string name, float fadeLength = 0.3f)
        {
            // For simplicity, just play immediately — PlayableGraph crossfade requires
            // a mixer playable setup. Direct play is sufficient for emotion transitions.
            return PlayAnimation(name);
        }

        /// <summary>
        /// Stop all animations and return to the default idle pose.
        /// </summary>
        public void StopAll()
        {
            if (_clipPlayable.IsValid())
            {
                _clipPlayable.Destroy();
            }
            _currentClip = null;
        }

        /// <summary>
        /// Returns the name of the currently playing animation, or null if none.
        /// </summary>
        public string GetCurrentAnimation()
        {
            return _currentClip;
        }

        private void OnDestroy()
        {
            if (_graph.IsValid())
            {
                _graph.Destroy();
            }
        }
    }
}
