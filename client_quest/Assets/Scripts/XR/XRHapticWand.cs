using System;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.Avatar;
using FoveAI.UI;

namespace FoveAI.XR
{
    /// <summary>
    /// XRHapticWand — Full port of Frontend/XR_Vessel/src/avatar/HapticWand.ts (HAPTIC WAND v2 — OMEGA_362)
    ///
    /// Lumax cyan glowing tube with elastic, jelly-like sway (spring physics).
    /// Extends TOWARDS the user's body (negative Z + arm-extension sleeve).
    /// Squishy rubber-friction sound via procedural Unity audio (no file needed).
    /// Precise VRM bone-sphere collision (no stutter from mesh raycasting).
    /// 80s romantic synth beat on first contact per session.
    /// </summary>
    public class XRHapticWand : MonoBehaviour
    {
        public enum WandHand { Left, Right }
        public WandHand hand = WandHand.Right;

        [Header("Wand Visuals")]
        public float wandLength = 0.52f;       // ROD_LEN — forward tip length (m)
        public float sleeveLength = 0.20f;     // SLEEVE_LEN — backward sleeve length (m)
        public float wandRadius = 0.012f;      // rod radius
        public Color wandColor = new Color(0f, 0.95f, 1f, 0.72f); // Lumax Cyan

        [Header("Spring Physics")]
        public float springK = 28f;            // stiffness (higher = stiffer)
        public float springDamping = 5.8f;    // damping (lower = more jelly wobble)
        public float maxTipDeflect = 0.18f;   // max tip displacement from rest (m)

        [Header("Audio")]
        public bool enableSquishSound = true;
        public bool enable80sBeat = true;
        [Range(0f, 1f)] public float squishVolume = 0.045f;
        [Range(0f, 1f)] public float beatVolume = 0.35f;

        // ── VRM body sphere colliders (bone + radius in metres) ──
        private struct BoneCollider
        {
            public HumanBodyBones bone;
            public float radius;
            public string zone;
        }

        private static readonly BoneCollider[] VRM_COLLIDERS = new BoneCollider[]
        {
            new() { bone = HumanBodyBones.Head,           radius = 0.12f,  zone = "head"     },
            new() { bone = HumanBodyBones.Neck,           radius = 0.065f, zone = "neck"     },
            new() { bone = HumanBodyBones.UpperChest,     radius = 0.16f,  zone = "chest"    },
            new() { bone = HumanBodyBones.Chest,          radius = 0.15f,  zone = "chest"    },
            new() { bone = HumanBodyBones.Spine,          radius = 0.12f,  zone = "waist"    },
            new() { bone = HumanBodyBones.Hips,           radius = 0.14f,  zone = "hips"     },
            new() { bone = HumanBodyBones.LeftShoulder,   radius = 0.07f,  zone = "shoulder" },
            new() { bone = HumanBodyBones.RightShoulder,  radius = 0.07f,  zone = "shoulder" },
            new() { bone = HumanBodyBones.LeftUpperArm,   radius = 0.055f, zone = "arm"      },
            new() { bone = HumanBodyBones.RightUpperArm,  radius = 0.055f, zone = "arm"      },
            new() { bone = HumanBodyBones.LeftLowerArm,   radius = 0.045f, zone = "arm"      },
            new() { bone = HumanBodyBones.RightLowerArm,  radius = 0.045f, zone = "arm"      },
            new() { bone = HumanBodyBones.LeftHand,       radius = 0.055f, zone = "hand"     },
            new() { bone = HumanBodyBones.RightHand,      radius = 0.055f, zone = "hand"     },
            new() { bone = HumanBodyBones.LeftUpperLeg,   radius = 0.085f, zone = "thigh"    },
            new() { bone = HumanBodyBones.RightUpperLeg,  radius = 0.085f, zone = "thigh"    },
            new() { bone = HumanBodyBones.LeftLowerLeg,   radius = 0.055f, zone = "leg"      },
            new() { bone = HumanBodyBones.RightLowerLeg,  radius = 0.055f, zone = "leg"      },
        };

        // ── Visual components ──
        private GameObject _wandRoot;
        private LineRenderer _rodLine;
        private LineRenderer _sleeveLine;
        private GameObject _tipGlow;
        private Light _tipLight;
        private Material _rodMaterial;
        private Material _sleeveMaterial;

        private bool _isWandActive = false;
        public bool IsWandActive => _isWandActive;

        // Double-click trigger detection
        private float _lastTriggerTime = 0f;
        private const float DoubleClickThreshold = 0.35f;

        // Spring physics state
        private Vector3 _restTip = Vector3.zero;     // world position of rigid tip
        private Vector3 _springTip = Vector3.zero;   // physics-displaced tip
        private Vector3 _springVel = Vector3.zero;   // velocity

        // Collision state
        private bool _isContacting = false;
        private float _contactPressure = 0f;         // smoothed 0–1
        private int _frame = 0;

        // Audio
        private AudioSource _squishSource;
        private bool _beat80sPlayed = false;

        // Avatar refs
        private AvatarBlendshapeDriver _blendshapeDriver;
        private Animator _avatarAnimator;
        private VRMAvatarLoader _avatarLoader;

        // ── Lifecycle ──

        private void Start()
        {
            BuildWandVisual();
            SetupAudio();
        }

        private void BuildWandVisual()
        {
            _wandRoot = new GameObject("HapticWandVisual");
            _wandRoot.transform.SetParent(transform, false);

            // Rod (pointing forward, -Z) — LineRenderer with 10 segments for jelly bend
            _rodLine = _wandRoot.AddComponent<LineRenderer>();
            _rodLine.useWorldSpace = false;
            _rodLine.positionCount = 10;
            _rodLine.startWidth = wandRadius * 2f;
            _rodLine.endWidth = wandRadius * 2.4f; // spherical squishy tip
            _rodMaterial = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            _rodMaterial.color = wandColor;
            _rodLine.material = _rodMaterial;

            // Sleeve (pointing backward toward arm, +Z)
            _sleeveLine = new GameObject("Sleeve").AddComponent<LineRenderer>();
            _sleeveLine.transform.SetParent(_wandRoot.transform, false);
            _sleeveLine.useWorldSpace = false;
            _sleeveLine.positionCount = 2;
            _sleeveLine.startWidth = wandRadius * 2.4f;
            _sleeveLine.endWidth = wandRadius * 3f;
            _sleeveMaterial = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            Color sleeveCol = wandColor;
            sleeveCol.a = 0.35f;
            _sleeveMaterial.color = sleeveCol;
            _sleeveLine.material = _sleeveMaterial;
            _sleeveLine.SetPosition(0, Vector3.zero);
            _sleeveLine.SetPosition(1, new Vector3(0, 0, sleeveLength));

            // Tip glow sphere
            _tipGlow = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            _tipGlow.transform.SetParent(_wandRoot.transform, false);
            _tipGlow.transform.localScale = Vector3.one * 0.036f;
            _tipGlow.transform.localPosition = new Vector3(0, 0, -wandLength);
            Destroy(_tipGlow.GetComponent<Collider>());
            var glowMat = new Material(Shader.Find("Unlit/Color") ?? Shader.Find("Standard"));
            glowMat.color = new Color(wandColor.r, wandColor.g, wandColor.b, 0.85f);
            _tipGlow.GetComponent<MeshRenderer>().material = glowMat;

            // Point light at tip
            _tipLight = _wandRoot.AddComponent<Light>();
            _tipLight.type = LightType.Point;
            _tipLight.color = wandColor;
            _tipLight.range = 0.8f;
            _tipLight.intensity = 0f;

            _wandRoot.SetActive(false);
        }

        private void SetupAudio()
        {
            _squishSource = gameObject.AddComponent<AudioSource>();
            _squishSource.loop = true;
            _squishSource.playOnAwake = false;
            _squishSource.spatialBlend = 1f; // 3D positional
            _squishSource.volume = squishVolume;
        }

        private void Update()
        {
            CheckTriggerToggle();

            if (_isWandActive)
            {
                UpdateSpringPhysics();
                OrientRodToTip();
                CheckAvatarCollision();
            }
        }

        // ── Double-click trigger toggle ──

        private void CheckTriggerToggle()
        {
            var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
            bool triggerDown = OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, controller);

            if (triggerDown)
            {
                float timeNow = Time.time;
                if (timeNow - _lastTriggerTime <= DoubleClickThreshold)
                {
                    ToggleWandMode();
                    _lastTriggerTime = 0f;
                }
                else
                {
                    _lastTriggerTime = timeNow;
                }
            }
        }

        public void ToggleWandMode()
        {
            _isWandActive = !_isWandActive;
            if (_wandRoot != null) _wandRoot.SetActive(_isWandActive);

            var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
            OVRInput.SetControllerVibration(0.8f, 0.8f, controller);
            Invoke(nameof(StopHaptics), 0.12f);

            if (_isWandActive)
            {
                // Seed spring tip at rigid position
                _restTip = transform.position + transform.forward * -wandLength;
                _springTip = _restTip;
                _springVel = Vector3.zero;
                _beat80sPlayed = false;
            }
            else
            {
                StopSquish();
            }

            string state = _isWandActive ? "ACTIVATED" : "DEACTIVATED";
            FoveAI.DebugOverlay.QuestDebugOverlay.Log($"🪄 Haptic Wand {state} ({hand})");
            XRIDEHud.FlashNotification($"🪄 HAPTIC WAND {state}", 2.5f);
        }

        private void StopHaptics()
        {
            var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
            OVRInput.SetControllerVibration(0f, 0f, controller);
        }

        // ── Spring physics tip sway ──

        private void UpdateSpringPhysics()
        {
            float dt = Mathf.Min(Time.deltaTime, 0.05f);

            // Calculate current rigid tip world position (forward = -Z in local)
            _restTip = transform.position + (transform.rotation * new Vector3(0, 0, -wandLength));

            // Spring: F = -k*(x - rest) - damping*vel
            Vector3 displacement = _springTip - _restTip;
            Vector3 springForce = -springK * displacement;
            Vector3 dampingForce = -springDamping * _springVel;
            Vector3 accel = springForce + dampingForce;

            _springVel += accel * dt;
            _springTip += _springVel * dt;

            // Clamp maximum deflection
            Vector3 disp = _springTip - _restTip;
            if (disp.magnitude > maxTipDeflect)
            {
                disp = disp.normalized * maxTipDeflect;
                _springTip = _restTip + disp;
            }
        }

        // ── Orient rod mesh to track spring tip ──

        private void OrientRodToTip()
        {
            Vector3 basePos = transform.position;
            Vector3 localTip = _springTip - basePos;
            // Convert to parent-local space
            Quaternion invParentQ = Quaternion.Inverse(transform.rotation);
            Vector3 localTipRel = invParentQ * localTip;

            float len = localTipRel.magnitude;
            if (len < 0.001f) return;
            Vector3 dir = localTipRel.normalized;

            // Compute curve points along the rubber stick (quadratic bezier jelly bend)
            Vector3 baseLocal = Vector3.zero;
            Vector3 targetTip = dir * len;

            for (int i = 0; i < 10; i++)
            {
                float t = i / 9f;
                Vector3 pt = Vector3.Lerp(baseLocal, targetTip, t) +
                    localTipRel * (Mathf.Sin(t * Mathf.PI) * 0.3f) * 0.01f; // subtle bend
                _rodLine.SetPosition(i, pt);
            }

            // Move tip glow to local tip
            if (_tipGlow != null)
                _tipGlow.transform.localPosition = targetTip;
            if (_tipLight != null)
                _tipLight.transform.localPosition = targetTip;
        }

        // ── Bone-sphere collision (no raycasting = no stutter) ──

        private void CheckAvatarCollision()
        {
            if (_avatarAnimator == null)
            {
                _avatarLoader = FindAnyObjectByType<VRMAvatarLoader>();
                if (_avatarLoader != null && _avatarLoader.Avatar != null)
                {
                    _avatarAnimator = _avatarLoader.Avatar.GetComponentInChildren<Animator>();
                    _blendshapeDriver = _avatarLoader.Avatar.GetComponent<AvatarBlendshapeDriver>();
                }
            }

            if (_avatarAnimator == null || !_avatarAnimator.isHuman) return;

            _frame++;

            string bestZone = "";
            float bestPressure = 0f;

            // Check collision every 2 frames for performance
            if (_frame % 2 == 0)
            {
                Vector3 tipWorld = _springTip;

                foreach (var col in VRM_COLLIDERS)
                {
                    Transform boneTransform = _avatarAnimator.GetBoneTransform(col.bone);
                    if (boneTransform == null) continue;

                    float dist = Vector3.Distance(tipWorld, boneTransform.position);
                    if (dist < col.radius)
                    {
                        // Pressure = how deep inside the sphere (0 at edge, 1 at centre)
                        float p = 1.0f - dist / col.radius;
                        if (p > bestPressure)
                        {
                            bestPressure = p;
                            bestZone = col.zone;
                        }
                    }
                }
            }

            // Process collision result
            if (bestPressure > 0.02f)
            {
                // Smooth pressure
                _contactPressure = Mathf.Lerp(_contactPressure, bestPressure, 0.25f);

                // Glow intensity responds to pressure
                if (_rodMaterial != null)
                {
                    Color c = _rodMaterial.color;
                    c.a = Mathf.Lerp(0.72f, 1f, _contactPressure);
                    _rodMaterial.color = c;
                }
                if (_tipLight != null)
                    _tipLight.intensity = 2.5f + _contactPressure * 6f;

                // Push-back resistance force on spring tip
                float pushBack = _contactPressure * 0.08f;
                Vector3 pushDir = transform.rotation * new Vector3(0, 0, 1); // +Z = toward controller
                _springVel += pushDir * pushBack;

                // Squish sound
                StartSquish();

                // Haptic vibration scaled by pressure
                FireHaptic(_contactPressure);

                if (!_isContacting)
                {
                    _isContacting = true;
                    Play80sBeat();
                    ApplyEmotion(bestZone, _contactPressure);
                }
                else if (_frame % 60 == 0)
                {
                    // Refresh zone every ~1s
                    ApplyEmotion(bestZone, _contactPressure);
                }
            }
            else
            {
                // Decay pressure
                _contactPressure = Mathf.Lerp(_contactPressure, 0f, 0.15f);

                if (_rodMaterial != null)
                {
                    Color c = _rodMaterial.color;
                    c.a = Mathf.Lerp(c.a, 0.72f, 0.1f);
                    _rodMaterial.color = c;
                }
                if (_tipLight != null)
                    _tipLight.intensity = Mathf.Lerp(_tipLight.intensity, 1.2f, 0.1f);

                if (_isContacting)
                {
                    _isContacting = false;
                    StopSquish();
                }
            }
        }

        // ── Emotion / blendshape reaction ──

        private void ApplyEmotion(string zone, float pressure)
        {
            if (_blendshapeDriver == null) return;

            // Different zones trigger different reactions
            float intensity = Mathf.Clamp01(pressure * 0.75f + 0.25f);

            switch (zone)
            {
                case "head":
                case "neck":
                    _blendshapeDriver.ApplyEmotion("surprised", intensity * 0.6f);
                    _blendshapeDriver.ApplyEmotion("happy", intensity * 0.4f);
                    break;
                case "chest":
                case "waist":
                case "hips":
                    _blendshapeDriver.ApplyEmotion("happy", intensity);
                    break;
                case "shoulder":
                case "arm":
                case "hand":
                    _blendshapeDriver.ApplyEmotion("happy", intensity * 0.7f);
                    break;
                case "thigh":
                case "leg":
                    _blendshapeDriver.ApplyEmotion("surprised", intensity * 0.5f);
                    break;
                default:
                    _blendshapeDriver.ApplyEmotion("happy", intensity * 0.5f);
                    break;
            }

            FoveAI.DebugOverlay.QuestDebugOverlay.Log(
                $"🪄 HapticWand contact: zone={zone}, pressure={pressure:F2}");
        }

        // ── Audio: Squish rubber-friction sound ──

        private void StartSquish()
        {
            if (!enableSquishSound || _squishSource == null) return;
            if (_squishSource.isPlaying) return;

            // Generate rubber-friction noise buffer
            int sampleRate = AudioSettings.outputSampleRate;
            int bufLen = sampleRate / 2; // 0.5s buffer
            float[] samples = new float[bufLen];
            for (int i = 0; i < bufLen; i++)
                samples[i] = UnityEngine.Random.Range(-1f, 1f);

            AudioClip clip = AudioClip.Create("squish", bufLen, 1, sampleRate, false);
            clip.SetData(samples, 0);
            _squishSource.clip = clip;
            _squishSource.volume = squishVolume;
            _squishSource.Play();
        }

        private void StopSquish()
        {
            if (_squishSource != null && _squishSource.isPlaying)
            {
                _squishSource.Stop();
            }
        }

        // ── Audio: 80s romantic synth beat (one-shot per session) ──

        private void Play80sBeat()
        {
            if (!enable80sBeat || _beat80sPlayed) return;
            _beat80sPlayed = true;

            // Play on a temporary AudioSource
            var beatObj = new GameObject("Beat80s");
            beatObj.transform.SetParent(transform, false);
            var src = beatObj.AddComponent<AudioSource>();
            src.spatialBlend = 0.5f;
            src.volume = beatVolume;

            StartCoroutine(Play80sBeatCoroutine(src, beatObj));
        }

        private System.Collections.IEnumerator Play80sBeatCoroutine(AudioSource src, GameObject beatObj)
        {
            int sampleRate = AudioSettings.outputSampleRate;
            float duration = 4.5f;
            int totalSamples = Mathf.FloorToInt(sampleRate * duration);
            float[] samples = new float[totalSamples];

            float t = 0f;
            int idx = 0;
            while (idx < totalSamples)
            {
                t = (float)idx / sampleRate;

                // Synth pad: warm detuned D minor → F chord (2 chords, 1.8s each)
                float pad = 0f;
                int chordIdx = t < 1.8f ? 0 : 1;
                float chordT = t - chordIdx * 1.8f;
                if (chordT < 2.4f)
                {
                    float[][] chords = { new[] { 146.83f, 174.61f, 220.0f }, new[] { 196.0f, 233.08f, 293.66f } };
                    foreach (float freq in chords[chordIdx])
                    {
                        float env = 0f;
                        if (chordT > 0.3f) env = Mathf.Lerp(0.08f, 0.05f, (chordT - 0.3f) / 1.1f);
                        else if (chordT > 0f) env = Mathf.Lerp(0f, 0.08f, chordT / 0.3f);
                        if (chordT > 1.4f) env = Mathf.Lerp(0.05f, 0f, (chordT - 1.4f) / 1.0f);
                        pad += Mathf.Sin(2f * Mathf.PI * freq * t) * env;
                    }
                }

                // 80s bass (sine)
                float bass = 0f;
                float[][] bassNotes = { new[] { 0f, 73.42f }, new[] { 0.5f, 73.42f }, new[] { 1f, 65.41f }, new[] { 1.5f, 73.42f }, new[] { 1.8f, 87.31f }, new[] { 2.3f, 65.41f }, new[] { 3f, 73.42f }, new[] { 3.5f, 65.41f } };
                foreach (var note in bassNotes)
                {
                    float noteT = t - note[0];
                    if (noteT >= 0f && noteT < 0.5f)
                    {
                        float env = noteT < 0.02f ? Mathf.Lerp(0f, 0.22f, noteT / 0.02f) :
                                    noteT < 0.15f ? Mathf.Lerp(0.22f, 0.10f, (noteT - 0.02f) / 0.13f) :
                                    Mathf.Lerp(0.10f, 0f, (noteT - 0.15f) / 0.35f);
                        bass += Mathf.Sin(2f * Mathf.PI * note[1] * t) * env;
                    }
                }

                // Gated snare (noise burst)
                float snare = 0f;
                float[] snareTimes = { 0.75f, 1.5f, 2.25f, 3.0f, 3.75f };
                foreach (float st in snareTimes)
                {
                    float sT = t - st;
                    if (sT >= 0f && sT < 0.18f)
                    {
                        float env = Mathf.Lerp(0.55f, 0f, sT / 0.08f);
                        snare += UnityEngine.Random.Range(-1f, 1f) * env;
                    }
                }

                // Hi-hat tick
                float hihat = 0f;
                float[] hatTimes = { 0f, 0.375f, 0.75f, 1.125f, 1.5f, 1.875f, 2.25f, 2.625f, 3.0f, 3.375f, 3.75f };
                foreach (float ht in hatTimes)
                {
                    float hT = t - ht;
                    if (hT >= 0f && hT < 0.04f)
                    {
                        float env = Mathf.Lerp(0.12f, 0f, hT / 0.04f);
                        hihat += UnityEngine.Random.Range(-1f, 1f) * env;
                    }
                }

                samples[idx] = (pad + bass + snare + hihat) * 0.3f;
                idx++;
            }

            AudioClip clip = AudioClip.Create("beat80s", totalSamples, 1, sampleRate, false);
            clip.SetData(samples, 0);
            src.clip = clip;
            src.Play();

            yield return new WaitForSeconds(duration + 0.5f);
            Destroy(beatObj);
        }

        // ── Haptic vibration scaled by pressure ──

        private void FireHaptic(float pressure)
        {
            var controller = hand == WandHand.Left ? OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
            float intensity = Mathf.Min(1f, pressure * 1.1f);
            OVRInput.SetControllerVibration(intensity * 0.4f, intensity * 0.3f, controller);
        }
    }
}
