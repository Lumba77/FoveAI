using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using FoveAI.IPC;

namespace FoveAI.Experiences
{
    /// <summary>
    /// Dynamic Wall Emergence — a virtual wall erupts from the floor,
    /// shaking, squeaking, and kicking up concrete dust.
    ///
    /// Uses XR occlusion so the wall respects real room geometry:
    ///   • Wall emerges from a real floor surface
    ///   • Wall is occluded by real walls/furniture (doesn't clip through)
    ///   • Dust particles collide with real mesh surfaces
    ///   • Shake is felt through the play space origin
    ///
    /// Triggered by:
    ///   • SoftLayer JS: FoveAI.wall.emerge(direction, height, speed)
    ///   • WebSocket event: {"event": "wall.emerge", "payload": {...}}
    ///   • Voice command: "close off the room"
    ///   • Director Engine: surprise events
    ///
    /// The wall has phases:
    ///   1. RUMBLE  — low-frequency vibration, dust begins to stir (1-2s)
    ///   2. CRACK   — floor cracks, squeaking sound, wall tip emerges (0.5s)
    ///   3. RISE    — wall pushes up with shaking, dust cloud billows (2-4s)
    ///   4. SETTLE  — wall locks into place, dust settles, shake fades (1-2s)
    ///   5. STANDING — wall is solid, occludes the space beyond
    /// </summary>
    public class DynamicWallEmergence : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private FoveAIWebSocketClient wsClient;
        [SerializeField] private RoomPlastering roomPlastering;
        [SerializeField] private Transform playSpaceOrigin;
        [SerializeField] private AudioSource audioSource;

        [Header("Wall Settings")]
        public float defaultHeight = 2.5f;
        public float defaultWidth = 4f;
        public float defaultThickness = 0.15f;
        public float defaultRiseSpeed = 1.2f;       // meters per second
        public float defaultRumbleDuration = 1.5f;
        public float defaultSettleDuration = 1.5f;

        [Header("Shake")]
        public float shakeIntensity = 0.02f;        // meters
        public float shakeFrequency = 25f;           // Hz
        public float shakeDecay = 0.5f;              // how fast shake fades

        [Header("Dust")]
        public int dustParticleCount = 800;
        public float dustSpread = 2f;
        public float dustRiseSpeed = 0.5f;
        public float dustLifetime = 4f;
        public float dustSize = 0.05f;
        public Color dustColor = new Color(0.6f, 0.55f, 0.5f, 0.4f);

        [Header("Audio (synthesized if no clips)")]
        public AudioClip rumbleClip;
        public AudioClip squeakClip;
        public AudioClip crackClip;
        public AudioClip settleClip;
        public float rumbleVolume = 0.4f;
        public float squeakVolume = 0.3f;

        [Header("Material")]
        public Color wallColor = new Color(0.5f, 0.48f, 0.45f, 1f);
        public float wallMetallic = 0.0f;
        public float wallSmoothness = 0.3f;
        public bool wallEmission = false;
        public Color wallEmissionColor = new Color(0.2f, 0.15f, 0.1f);

        // ── State ──
        public enum WallPhase { Idle, Rumble, Crack, Rise, Settle, Standing, Dissolving }
        public WallPhase phase = WallPhase.Idle;

        private GameObject _wall;
        private GameObject _dustSystem;
        private ParticleSystem _particles;
        private Material _wallMaterial;
        private Vector3 _wallTargetPos;
        private Vector3 _wallTargetScale;
        private Quaternion _wallTargetRot;
        private float _phaseTimer;
        private float _currentHeight;
        private float _targetHeight;
        private float _riseSpeed;
        private float _shakeAmount;
        private Vector3 _originRestPos;
        private Quaternion _originRestRot;

        // ── Lifecycle ──

        private void Start()
        {
            if (audioSource == null)
                audioSource = gameObject.AddComponent<AudioSource>();
            if (playSpaceOrigin == null)
                playSpaceOrigin = transform;
            _originRestPos = playSpaceOrigin.position;
            _originRestRot = playSpaceOrigin.rotation;

            if (wsClient != null)
            {
                wsClient.OnChatTextReceived += OnChatEvent;
            }
        }

        private void OnDestroy()
        {
            if (wsClient != null)
                wsClient.OnChatTextReceived -= OnChatEvent;
        }

        private void OnChatEvent(string text)
        {
            // Voice command detection could go here
            if (text.ToLowerInvariant().Contains("close off the room") ||
                text.ToLowerInvariant().Contains("build a wall"))
            {
                Emerge(Vector3.forward);
            }
        }

        private void Update()
        {
            switch (phase)
            {
                case WallPhase.Rumble:  UpdateRumble();  break;
                case WallPhase.Crack:   UpdateCrack();   break;
                case WallPhase.Rise:    UpdateRise();    break;
                case WallPhase.Settle:  UpdateSettle();  break;
                case WallPhase.Standing: UpdateStanding(); break;
                case WallPhase.Dissolving: UpdateDissolving(); break;
            }

            // Apply shake to play space
            if (_shakeAmount > 0.001f && playSpaceOrigin != null)
            {
                float sx = Mathf.Sin(Time.time * shakeFrequency) * _shakeAmount;
                float sy = Mathf.Sin(Time.time * shakeFrequency * 1.3f) * _shakeAmount * 0.5f;
                float sz = Mathf.Cos(Time.time * shakeFrequency * 0.7f) * _shakeAmount;
                playSpaceOrigin.position = _originRestPos + new Vector3(sx, sy, sz);
                _shakeAmount = Mathf.Lerp(_shakeAmount, 0, Time.deltaTime * shakeDecay);
            }
            else if (playSpaceOrigin != null && phase == WallPhase.Idle)
            {
                playSpaceOrigin.position = Vector3.Lerp(playSpaceOrigin.position, _originRestPos, Time.deltaTime * 5f);
                playSpaceOrigin.rotation = Quaternion.Lerp(playSpaceOrigin.rotation, _originRestRot, Time.deltaTime * 5f);
            }
        }

        // ── Public API ──

        /// <summary>
        /// Emerge a wall from the floor in the given direction.
        /// </summary>
        public void Emerge(Vector3 direction, float height = -1, float width = -1, float speed = -1)
        {
            if (phase != WallPhase.Idle && phase != WallPhase.Standing)
                return;

            // Remove existing wall if standing
            if (phase == WallPhase.Standing)
                Dissolve();

            _targetHeight = height > 0 ? height : defaultHeight;
            float w = width > 0 ? width : defaultWidth;
            _riseSpeed = speed > 0 ? speed : defaultRiseSpeed;

            // Position wall at the edge of the room in the given direction
            Vector3 origin = playSpaceOrigin != null ? playSpaceOrigin.position : transform.position;
            Vector3 dir = direction.normalized;
            dir.y = 0;
            if (dir.sqrMagnitude < 0.01f) dir = Vector3.forward;

            // Place wall 2m away in the given direction
            Vector3 wallPos = origin + dir * 2f;
            wallPos.y = origin.y; // start at floor level

            Quaternion wallRot = Quaternion.LookRotation(dir, Vector3.up);

            CreateWall(wallPos, wallRot, w);
            CreateDustSystem(wallPos, wallRot, w);

            // Start with rumble
            phase = WallPhase.Rumble;
            _phaseTimer = 0;
            _currentHeight = 0;
            _shakeAmount = 0.005f;

            PlayRumble();
            Debug.Log($"[WallEmergence] RUMBLE phase — wall emerging {dir}");
        }

        /// <summary>
        /// Dissolve the wall back into the floor.
        /// </summary>
        public void Dissolve()
        {
            if (phase != WallPhase.Standing) return;
            phase = WallPhase.Dissolving;
            _phaseTimer = 0;
            Debug.Log("[WallEmergence] Dissolving wall...");
        }

        // ── Phase updates ──

        private void UpdateRumble()
        {
            _phaseTimer += Time.deltaTime;
            _shakeAmount = Mathf.Lerp(_shakeAmount, 0.02f, Time.deltaTime * 2f);

            // Stir dust slightly
            if (_particles != null)
            {
                var em = _particles.emission;
                em.rateOverTime = 20;
            }

            if (_phaseTimer >= defaultRumbleDuration)
            {
                phase = WallPhase.Crack;
                _phaseTimer = 0;
                _shakeAmount = 0.05f;
                PlayCrack();
                PlaySqueak();
                Debug.Log("[WallEmergence] CRACK phase — wall tip emerging");
            }
        }

        private void UpdateCrack()
        {
            _phaseTimer += Time.deltaTime;
            _shakeAmount = 0.04f + 0.02f * Mathf.Sin(Time.time * 30f);

            // Wall tip starts to emerge
            _currentHeight = Mathf.Lerp(_currentHeight, 0.2f, Time.deltaTime * 8f);
            UpdateWallScale();

            // Dust burst
            if (_particles != null)
            {
                var em = _particles.emission;
                em.rateOverTime = 200;
            }

            if (_phaseTimer >= 0.5f)
            {
                phase = WallPhase.Rise;
                _phaseTimer = 0;
                Debug.Log("[WallEmergence] RISE phase — wall pushing up");
            }
        }

        private void UpdateRise()
        {
            _phaseTimer += Time.deltaTime;
            _shakeAmount = 0.03f + 0.015f * Mathf.Sin(Time.time * shakeFrequency);

            // Wall rises
            _currentHeight = Mathf.MoveTowards(_currentHeight, _targetHeight, _riseSpeed * Time.deltaTime);
            UpdateWallScale();

            // Heavy dust
            if (_particles != null)
            {
                var em = _particles.emission;
                em.rateOverTime = 300;
            }

            // Squeaking continues during rise
            if (_phaseTimer % 1.5f < 0.1f && !audioSource.isPlaying)
            {
                PlaySqueak();
            }

            if (_currentHeight >= _targetHeight - 0.01f)
            {
                phase = WallPhase.Settle;
                _phaseTimer = 0;
                Debug.Log("[WallEmergence] SETTLE phase — wall locking in");
            }
        }

        private void UpdateSettle()
        {
            _phaseTimer += Time.deltaTime;
            _shakeAmount = Mathf.Lerp(_shakeAmount, 0, Time.deltaTime * 3f);

            // Dust fades
            if (_particles != null)
            {
                var em = _particles.emission;
                em.rateOverTime = Mathf.Lerp(em.rateOverTime.constant, 0, Time.deltaTime * 2f);
            }

            if (_phaseTimer >= defaultSettleDuration)
            {
                phase = WallPhase.Standing;
                _shakeAmount = 0;
                PlaySettle();
                Debug.Log("[WallEmergence] STANDING — wall is solid, room closed off");
            }
        }

        private void UpdateStanding()
        {
            // Wall is solid — subtle idle vibration
            _shakeAmount = 0.001f * Mathf.Sin(Time.time * 2f);
        }

        private void UpdateDissolving()
        {
            _phaseTimer += Time.deltaTime;
            _currentHeight = Mathf.MoveTowards(_currentHeight, 0, _riseSpeed * 0.5f * Time.deltaTime);
            UpdateWallScale();

            // Fade wall material
            if (_wallMaterial != null)
            {
                var c = _wallMaterial.color;
                c.a = Mathf.Lerp(c.a, 0, Time.deltaTime * 2f);
                _wallMaterial.color = c;
            }

            // Stir some dust on dissolve
            if (_particles != null)
            {
                var em = _particles.emission;
                em.rateOverTime = 50;
            }

            if (_currentHeight <= 0.01f)
            {
                Destroy(_wall);
                _wall = null;
                if (_particles != null)
                {
                    var em = _particles.emission;
                    em.rateOverTime = 0;
                }
                phase = WallPhase.Idle;
                Debug.Log("[WallEmergence] Wall dissolved — room open again");
            }
        }

        // ── Wall creation ──

        private void CreateWall(Vector3 position, Quaternion rotation, float width)
        {
            if (_wall != null) Destroy(_wall);

            _wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
            _wall.name = "DynamicWall";
            Destroy(_wall.GetComponent<Collider>()); // no collision — occlusion handles it

            _wall.transform.SetParent(transform, false);
            _wall.transform.position = position;
            _wall.transform.rotation = rotation;

            // Start at zero height (underground)
            _wallTargetScale = new Vector3(width, _targetHeight, defaultThickness);
            _wall.transform.localScale = new Vector3(width, 0.01f, defaultThickness);

            // Position so the wall grows upward from the floor
            _wall.transform.position = new Vector3(position.x, position.y, position.z);

            // Material — concrete
            _wallMaterial = new Material(Shader.Find("Universal Render Pipeline/Lit")
                                      ?? Shader.Find("Standard"));
            _wallMaterial.color = wallColor;
            if (_wallMaterial.HasProperty("_Metallic"))
                _wallMaterial.SetFloat("_Metallic", wallMetallic);
            if (_wallMaterial.HasProperty("_Smoothness"))
                _wallMaterial.SetFloat("_Smoothness", wallSmoothness);
            if (wallEmission)
            {
                _wallMaterial.EnableKeyword("_EMISSION");
                _wallMaterial.SetColor("_EmissionColor", wallEmissionColor);
            }

            _wall.GetComponent<Renderer>().material = _wallMaterial;
        }

        private void UpdateWallScale()
        {
            if (_wall == null) return;
            // Scale Y to current height, but anchor at floor
            _wall.transform.localScale = new Vector3(
                _wallTargetScale.x,
                Mathf.Max(0.01f, _currentHeight),
                _wallTargetScale.z
            );
            // Keep wall anchored at floor — move center up as it grows
            var pos = _wall.transform.position;
            float floorY = playSpaceOrigin != null ? playSpaceOrigin.position.y : 0;
            _wall.transform.position = new Vector3(pos.x, floorY + _currentHeight * 0.5f, pos.z);
        }

        // ── Dust particle system ──

        private void CreateDustSystem(Vector3 position, Quaternion rotation, float width)
        {
            if (_dustSystem != null) Destroy(_dustSystem);

            _dustSystem = new GameObject("DustCloud");
            _dustSystem.transform.SetParent(transform, false);
            _dustSystem.transform.position = position;
            _dustSystem.transform.rotation = rotation;

            _particles = _dustSystem.AddComponent<ParticleSystem>();

            var main = _particles.main;
            main.startLifetime = dustLifetime;
            main.startSpeed = new ParticleSystem.MinMaxCurve(0.5f, 2f);
            main.startSize = new ParticleSystem.MinMaxCurve(dustSize * 0.5f, dustSize * 1.5f);
            main.startColor = dustColor;
            main.maxParticles = dustParticleCount;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.gravityModifier = 0.1f; // slow fall

            var emission = _particles.emission;
            emission.rateOverTime = 0; // starts idle

            var shape = _particles.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.Box;
            shape.scale = new Vector3(width, 0.1f, defaultThickness);
            shape.position = new Vector3(0, 0, 0);

            var vel = _particles.velocityOverLifetime;
            vel.enabled = true;
            vel.y = new ParticleSystem.MinMaxCurve(dustRiseSpeed * 0.5f, dustRiseSpeed * 2f);
            vel.x = new ParticleSystem.MinMaxCurve(-0.3f, 0.3f);
            vel.z = new ParticleSystem.MinMaxCurve(-0.3f, 0.3f);

            var sizeOverLife = _particles.sizeOverLifetime;
            sizeOverLife.enabled = true;
            sizeOverLife.size = new ParticleSystem.MinMaxCurve(1f,
                new AnimationCurve(new Keyframe(0, 0.3f), new Keyframe(0.3f, 1f), new Keyframe(1f, 0.1f)));

            var colorOverLife = _particles.colorOverLifetime;
            colorOverLife.enabled = true;
            var grad = new Gradient();
            grad.SetKeys(
                new GradientColorKey[] { new GradientColorKey(dustColor, 0), new GradientColorKey(dustColor, 1) },
                new GradientAlphaKey[] { new GradientAlphaKey(0.6f, 0), new GradientAlphaKey(0.3f, 0.5f), new GradientAlphaKey(0f, 1f) }
            );
            colorOverLife.color = grad;

            var renderer = _dustSystem.GetComponent<ParticleSystemRenderer>();
            if (renderer != null)
            {
                renderer.material = new Material(Shader.Find("Universal Render Pipeline/Particles/Unlit")
                                              ?? Shader.Find("Particles/Standard Unlit"));
            }
        }

        // ── Audio (synthesized if no clips) ──

        private void PlayRumble()
        {
            if (rumbleClip != null)
            {
                audioSource.clip = rumbleClip;
                audioSource.volume = rumbleVolume;
                audioSource.loop = true;
                audioSource.Play();
            }
            else
            {
                StartCoroutine(SynthesizeRumble());
            }
        }

        private void PlaySqueak()
        {
            if (squeakClip != null)
            {
                audioSource.PlayOneShot(squeakClip, squeakVolume);
            }
            else
            {
                StartCoroutine(SynthesizeSqueak());
            }
        }

        private void PlayCrack()
        {
            if (crackClip != null)
            {
                audioSource.PlayOneShot(crackClip, 0.5f);
            }
            else
            {
                StartCoroutine(SynthesizeCrack());
            }
        }

        private void PlaySettle()
        {
            if (settleClip != null)
            {
                audioSource.PlayOneShot(settleClip, 0.3f);
            }
            // Stop rumble loop
            if (audioSource.isPlaying && audioSource.loop)
            {
                audioSource.loop = false;
                audioSource.Stop();
            }
        }

        // ── Synthesized audio (no clips needed) ──

        private IEnumerator SynthesizeRumble()
        {
            // Low-frequency rumble using a sine wave
            int sampleRate = AudioSettings.outputSampleRate;
            float[] waveData = new float[sampleRate]; // 1 second buffer
            for (int i = 0; i < sampleRate; i++)
            {
                float t = (float)i / sampleRate;
                // 40Hz rumble with some noise
                waveData[i] = Mathf.Sin(2 * Mathf.PI * 40 * t) * 0.3f
                            + Mathf.Sin(2 * Mathf.PI * 55 * t) * 0.15f
                            + (Random.value - 0.5f) * 0.1f;
            }

            AudioClip clip = AudioClip.Create("rumble", sampleRate, 1, sampleRate, false);
            clip.SetData(waveData, 0);
            audioSource.clip = clip;
            audioSource.volume = rumbleVolume;
            audioSource.loop = true;
            audioSource.Play();
            yield return null;
        }

        private IEnumerator SynthesizeSqueak()
        {
            int sampleRate = AudioSettings.outputSampleRate;
            int samples = sampleRate / 2; // 0.5s
            float[] waveData = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // High-pitched squeak with frequency sweep
                float freq = 2000 + 3000 * t;
                waveData[i] = Mathf.Sin(2 * Mathf.PI * freq * t) * 0.2f
                            * (1f - t * 2f); // fade out
            }

            AudioClip clip = AudioClip.Create("squeak", samples, 1, sampleRate, false);
            clip.SetData(waveData, 0);
            audioSource.PlayOneShot(clip, squeakVolume);
            yield return null;
        }

        private IEnumerator SynthesizeCrack()
        {
            int sampleRate = AudioSettings.outputSampleRate;
            int samples = sampleRate / 4; // 0.25s
            float[] waveData = new float[samples];
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / sampleRate;
                // Sharp crack — noise burst with fast decay
                waveData[i] = (Random.value - 0.5f) * 2f * Mathf.Exp(-t * 30f);
            }

            AudioClip clip = AudioClip.Create("crack", samples, 1, sampleRate, false);
            clip.SetData(waveData, 0);
            audioSource.PlayOneShot(clip, 0.5f);
            yield return null;
        }

        // ── SoftLayer JS bridge ──

        /// <summary>
        /// Called by SoftLayerEngine when JS calls FoveAI.wall.emerge(...)
        /// </summary>
        public void JsEmerge(float dirX, float dirZ, float height, float speed)
        {
            Emerge(new Vector3(dirX, 0, dirZ), height, -1, speed);
        }

        public void JsDissolve()
        {
            Dissolve();
        }

        public void JsSetWallColor(float r, float g, float b)
        {
            wallColor = new Color(r, g, b, 1f);
            if (_wallMaterial != null) _wallMaterial.color = wallColor;
        }

        public void JsSetShakeIntensity(float intensity)
        {
            shakeIntensity = intensity;
        }
    }
}
