using System;
using System.Collections.Generic;
using UnityEngine;
using Jint;

namespace FoveAI.SoftLayer
{
    /// <summary>
    /// SoftModule System — modular, hot-reloadable environment control.
    ///
    /// Each module controls one aspect of the VR environment:
    ///   • ChameleonModule  — surfaces change color/material/pattern dynamically
    ///   • ClothingModule   — avatar outfits, accessories, material swaps
    ///   • PlasterModule    — wall/furniture appearance (wraps RoomPlastering)
    ///   • LightingModule   — lights, color temperature, intensity, mood
    ///   • ParticleModule   — snow, rain, leaves, fireflies, petals, dust
    ///   • AudioModule      — ambient sounds, music, stings, volume
    ///   • WeatherModule    — drives environment from real weather data
    ///   • PropModule       — spawn/move/remove furniture and objects
    ///   • SkyModule        — skybox, time of day, clouds, stars
    ///
    /// Modules are JS files in softlayer/modules/ that define:
    ///   module.onLoad()      — called when module is loaded
    ///   module.onUpdate(dt)  — called every frame
    ///   module.onUnload()    — called when module is unloaded
    ///
    /// The JS context gets access to the FoveAI API + module-specific
    /// APIs (e.g. FoveAI.chameleon.setColor, FoveAI.clothing.setOutfit).
    ///
    /// Modules can be enabled/disabled at runtime via WS events.
    /// </summary>
    public class SoftModuleSystem : MonoBehaviour
    {
        [Header("Backend")]
        [SerializeField] private string backendUrl = "http://192.168.8.100:8402";
        [SerializeField] private string wsUrl = "ws://192.168.8.100:8403/ws";

        [Header("Default Modules")]
        [SerializeField] private string[] defaultModules = {
            "chameleon",
            "clothing",
            "lighting",
            "particles",
            "sky",
            "wall",
        };

        [Header("Debug")]
        [SerializeField] private bool verbose = true;

        // ── Module state ──
        public class ModuleState
        {
            public string name;
            public string source;
            public bool enabled;
            public bool loaded;
            public float lastUpdate;
        }

        private readonly Dictionary<string, ModuleState> _modules = new();
        private Engine _js;
        private bool _jsReady;
        private SoftLayerEngine _softLayer;

        // ── Module controllers (set from JS, applied in Update) ──
        private readonly Queue<Action> _pendingActions = new();
        private readonly object _actionLock = new();

        // ── References ──
        private Transform _avatarTransform;
        private Renderer[] _avatarRenderers;
        private Light[] _sceneLights;
        private Transform _playSpace;
        private Experiences.DynamicWallEmergence _wallEmergence;

        // ── Chameleon state ──
        private readonly Dictionary<string, Color> _surfaceColors = new();
        private readonly Dictionary<string, float> _surfaceAlphas = new();
        private float _chameleonTransitionSpeed = 2f;

        // ── Clothing state ──
        private string _currentOutfit = "default";
        private readonly Dictionary<string, Color> _clothingColors = new();
        private float _clothingMetallic = 0f;
        private float _clothingSmoothness = 0.5f;

        // ── Lighting state ──
        private Color _ambientColor = new(0.5f, 0.5f, 0.5f, 1f);
        private float _ambientIntensity = 0.6f;
        private Color _keyLightColor = Color.white;
        private float _keyLightIntensity = 0.8f;

        // ── Particle state ──
        private readonly Dictionary<string, bool> _particleEnabled = new();
        private readonly Dictionary<string, float> _particleDensity = new();

        // ── Sky state ──
        private Color _skyColor = new(0.3f, 0.5f, 0.8f);
        private Color _horizonColor = new(0.6f, 0.7f, 0.9f);
        private float _timeOfDay = 12f; // 0-24

        // ── Unity lifecycle ──

        private async void Start()
        {
            _softLayer = FindAnyObjectByType<SoftLayerEngine>();
            _avatarTransform = GameObject.FindGameObjectWithTag("Avatar")?.transform;
            if (_avatarTransform == null)
            {
                var loader = FindAnyObjectByType<Avatar.VRMAvatarLoader>();
                if (loader != null) _avatarTransform = loader.transform;
            }

            _playSpace = GameObject.FindGameObjectWithTag("PlaySpace")?.transform;
            if (_playSpace == null) _playSpace = transform;

            // Cache avatar renderers for clothing/chameleon
            if (_avatarTransform != null)
            {
                _avatarRenderers = _avatarTransform.GetComponentsInChildren<Renderer>(true);
            }

            // Cache scene lights
            _sceneLights = FindObjectsByType<Light>(FindObjectsSortMode.None);

            // Cache wall emergence
            _wallEmergence = FindAnyObjectByType<Experiences.DynamicWallEmergence>();

            InitJint();
            await LoadDefaultModulesAsync();

            if (verbose)
                Debug.Log("[SoftModule] Ready — modular environment control active");
        }

        private void Update()
        {
            // Apply pending actions
            lock (_actionLock)
            {
                while (_pendingActions.Count > 0)
                {
                    try { _pendingActions.Dequeue().Invoke(); }
                    catch (Exception e) { Debug.LogWarning($"[SoftModule] Action: {e.Message}"); }
                }
            }

            // Call module onUpdate for each enabled module
            if (_jsReady)
            {
                foreach (var kvp in _modules)
                {
                    if (!kvp.Value.enabled || !kvp.Value.loaded) continue;
                    try
                    {
                        _js.Execute($"if (typeof {kvp.Key}_onUpdate === 'function') {kvp.Key}_onUpdate({Time.deltaTime});");
                    }
                    catch { /* ignore */ }
                }
            }

            // Apply chameleon transitions
            ApplyChameleon();
            // Apply lighting
            ApplyLighting();
        }

        // ── Jint init ──

        private void InitJint()
        {
            _js = new Engine(opts => opts
                .LimitRecursion(100)
                .TimeoutInterval(TimeSpan.FromSeconds(1))
            );

            // ── Chameleon API ──
            _js.SetValue("chameleon_setColor", (Action<string, float, float, float, float>)JsChameleonSetColor);
            _js.SetValue("chameleon_setAlpha", (Action<string, float>)JsChameleonSetAlpha);
            _js.SetValue("chameleon_setTransitionSpeed", (Action<float>)JsChameleonSetTransitionSpeed);
            _js.SetValue("chameleon_pulse", (Action<string, float, float>)JsChameleonPulse);

            // ── Clothing API ──
            _js.SetValue("clothing_setOutfit", (Action<string>)JsClothingSetOutfit);
            _js.SetValue("clothing_setColor", (Action<string, float, float, float>)JsClothingSetColor);
            _js.SetValue("clothing_setMetallic", (Action<float>)JsClothingSetMetallic);
            _js.SetValue("clothing_setSmoothness", (Action<float>)JsClothingSetSmoothness);
            _js.SetValue("clothing_setEmission", (Action<float, float, float, float>)JsClothingSetEmission);

            // ── Lighting API ──
            _js.SetValue("lighting_setAmbient", (Action<float, float, float, float>)JsLightingSetAmbient);
            _js.SetValue("lighting_setKeyLight", (Action<float, float, float, float>)JsLightingSetKeyLight);
            _js.SetValue("lighting_setMood", (Action<string>)JsLightingSetMood);

            // ── Particle API ──
            _js.SetValue("particles_enable", (Action<string, bool>)JsParticlesEnable);
            _js.SetValue("particles_setDensity", (Action<string, float>)JsParticlesSetDensity);

            // ── Sky API ──
            _js.SetValue("sky_setColor", (Action<float, float, float>)JsSkySetColor);
            _js.SetValue("sky_setHorizon", (Action<float, float, float>)JsSkySetHorizon);
            _js.SetValue("sky_setTimeOfDay", (Action<float>)JsSkySetTimeOfDay);

            // ── Wall API (dynamic wall emergence) ──
            _js.SetValue("wall_emerge", (Action<float, float, float, float>)JsWallEmerge);
            _js.SetValue("wall_dissolve", (Action)JsWallDissolve);
            _js.SetValue("wall_setColor", (Action<float, float, float>)JsWallSetColor);
            _js.SetValue("wall_setShake", (Action<float>)JsWallSetShake);

            // ── General ──
            _js.SetValue("foveai_log", (Action<string>)JsLog);
            _js.SetValue("foveai_getParam", (Func<string, object>)JsGetParam);

            // Define module API objects
            _js.Execute(@"
                var FoveAI = FoveAI || {};
                FoveAI.log = foveai_log;
                FoveAI.getParam = foveai_getParam;

                FoveAI.chameleon = {
                    setColor: chameleon_setColor,
                    setAlpha: chameleon_setAlpha,
                    setTransitionSpeed: chameleon_setTransitionSpeed,
                    pulse: chameleon_pulse,
                };

                FoveAI.clothing = {
                    setOutfit: clothing_setOutfit,
                    setColor: clothing_setColor,
                    setMetallic: clothing_setMetallic,
                    setSmoothness: clothing_setSmoothness,
                    setEmission: clothing_setEmission,
                };

                FoveAI.lighting = {
                    setAmbient: lighting_setAmbient,
                    setKeyLight: lighting_setKeyLight,
                    setMood: lighting_setMood,
                };

                FoveAI.particles = {
                    enable: particles_enable,
                    setDensity: particles_setDensity,
                };

                FoveAI.sky = {
                    setColor: sky_setColor,
                    setHorizon: sky_setHorizon,
                    setTimeOfDay: sky_setTimeOfDay,
                };

                FoveAI.wall = {
                    emerge: wall_emerge,
                    dissolve: wall_dissolve,
                    setColor: wall_setColor,
                    setShake: wall_setShake,
                };
            ");

            _jsReady = true;
        }

        // ── Module loading ──

        private async System.Threading.Tasks.Task LoadDefaultModulesAsync()
        {
            using var client = new System.Net.Http.HttpClient();
            client.Timeout = TimeSpan.FromSeconds(5);

            foreach (var moduleName in defaultModules)
            {
                try
                {
                    string url = $"{backendUrl}/softlayer/modules/{moduleName}.js";
                    var source = await client.GetStringAsync(url);
                    LoadModule(moduleName, source);
                }
                catch (Exception e)
                {
                    if (verbose)
                        Debug.LogWarning($"[SoftModule] Could not load {moduleName}: {e.Message}");
                }
            }
        }

        public void LoadModule(string name, string source)
        {
            if (!_jsReady) return;

            var state = new ModuleState { name = name, source = source, enabled = true, loaded = false };
            _modules[name] = state;

            try
            {
                _js.Execute(source);
                state.loaded = true;

                // Call onLoad if defined
                _js.Execute($"if (typeof {name}_onLoad === 'function') {name}_onLoad();");

                if (verbose)
                    Debug.Log($"[SoftModule] Loaded: {name} ({source.Length} bytes)");
            }
            catch (Exception e)
            {
                Debug.LogError($"[SoftModule] JS error in {name}: {e.Message}");
            }
        }

        public void UnloadModule(string name)
        {
            if (!_modules.TryGetValue(name, out var state)) return;

            try
            {
                _js.Execute($"if (typeof {name}_onUnload === 'function') {name}_onUnload();");
            }
            catch { }

            state.enabled = false;
            state.loaded = false;
            if (verbose)
                Debug.Log($"[SoftModule] Unloaded: {name}");
        }

        public void EnableModule(string name)
        {
            if (_modules.TryGetValue(name, out var state))
            {
                state.enabled = true;
                if (verbose) Debug.Log($"[SoftModule] Enabled: {name}");
            }
        }

        public void DisableModule(string name)
        {
            if (_modules.TryGetValue(name, out var state))
            {
                state.enabled = false;
                if (verbose) Debug.Log($"[SoftModule] Disabled: {name}");
            }
        }

        public void HotReloadModule(string name, string source)
        {
            UnloadModule(name);
            LoadModule(name, source);
        }

        // ── JS → C# bridge: Chameleon ──

        private void JsChameleonSetColor(string surface, float r, float g, float b, float a)
        {
            QueueAction(() => { _surfaceColors[surface] = new Color(r, g, b, a); });
        }

        private void JsChameleonSetAlpha(string surface, float alpha)
        {
            QueueAction(() => { _surfaceAlphas[surface] = alpha; });
        }

        private void JsChameleonSetTransitionSpeed(float speed)
        {
            QueueAction(() => { _chameleonTransitionSpeed = speed; });
        }

        private void JsChameleonPulse(string surface, float frequency, float amplitude)
        {
            QueueAction(() =>
            {
                // Pulse the surface color brightness
                if (_surfaceColors.TryGetValue(surface, out var baseColor))
                {
                    float pulse = 1f + amplitude * Mathf.Sin(Time.time * frequency);
                    _surfaceColors[surface] = new Color(
                        baseColor.r * pulse, baseColor.g * pulse, baseColor.b * pulse, baseColor.a
                    );
                }
            });
        }

        // ── JS → C# bridge: Clothing ──

        private void JsClothingSetOutfit(string outfit)
        {
            QueueAction(() =>
            {
                _currentOutfit = outfit;
                ApplyClothing();
                if (verbose) Debug.Log($"[SoftModule] Outfit: {outfit}");
            });
        }

        private void JsClothingSetColor(string part, float r, float g, float b)
        {
            QueueAction(() => { _clothingColors[part] = new Color(r, g, b); ApplyClothing(); });
        }

        private void JsClothingSetMetallic(float m)
        {
            QueueAction(() => { _clothingMetallic = m; ApplyClothing(); });
        }

        private void JsClothingSetSmoothness(float s)
        {
            QueueAction(() => { _clothingSmoothness = s; ApplyClothing(); });
        }

        private void JsClothingSetEmission(float r, float g, float b, float intensity)
        {
            QueueAction(() =>
            {
                if (_avatarRenderers == null) return;
                foreach (var rend in _avatarRenderers)
                {
                    if (rend == null) continue;
                    foreach (var mat in rend.materials)
                    {
                        if (mat == null) continue;
                        mat.SetColor("_EmissionColor", new Color(r, g, b) * intensity);
                        if (mat.HasProperty("_EmissionEnabled"))
                            mat.EnableKeyword("_EMISSION");
                    }
                }
            });
        }

        // ── JS → C# bridge: Lighting ──

        private void JsLightingSetAmbient(float r, float g, float b, float intensity)
        {
            QueueAction(() =>
            {
                _ambientColor = new Color(r, g, b);
                _ambientIntensity = intensity;
            });
        }

        private void JsLightingSetKeyLight(float r, float g, float b, float intensity)
        {
            QueueAction(() =>
            {
                _keyLightColor = new Color(r, g, b);
                _keyLightIntensity = intensity;
            });
        }

        private void JsLightingSetMood(string mood)
        {
            QueueAction(() =>
            {
                switch (mood.ToLowerInvariant())
                {
                    case "warm":
                        _ambientColor = new Color(0.6f, 0.5f, 0.4f);
                        _keyLightColor = new Color(1f, 0.85f, 0.7f);
                        _keyLightIntensity = 0.7f;
                        _ambientIntensity = 0.5f;
                        break;
                    case "cool":
                        _ambientColor = new Color(0.4f, 0.5f, 0.6f);
                        _keyLightColor = new Color(0.7f, 0.8f, 1f);
                        _keyLightIntensity = 0.6f;
                        _ambientIntensity = 0.5f;
                        break;
                    case "dramatic":
                        _ambientColor = new Color(0.2f, 0.2f, 0.25f);
                        _keyLightColor = new Color(1f, 0.9f, 0.8f);
                        _keyLightIntensity = 1.2f;
                        _ambientIntensity = 0.2f;
                        break;
                    case "dreamy":
                        _ambientColor = new Color(0.5f, 0.4f, 0.6f);
                        _keyLightColor = new Color(0.9f, 0.8f, 1f);
                        _keyLightIntensity = 0.5f;
                        _ambientIntensity = 0.6f;
                        break;
                    case "energetic":
                        _ambientColor = new Color(0.5f, 0.55f, 0.4f);
                        _keyLightColor = new Color(1f, 1f, 0.9f);
                        _keyLightIntensity = 1.0f;
                        _ambientIntensity = 0.7f;
                        break;
                    case "cozy":
                        _ambientColor = new Color(0.5f, 0.4f, 0.3f);
                        _keyLightColor = new Color(1f, 0.8f, 0.6f);
                        _keyLightIntensity = 0.6f;
                        _ambientIntensity = 0.6f;
                        break;
                }
                if (verbose) Debug.Log($"[SoftModule] Lighting mood: {mood}");
            });
        }

        // ── JS → C# bridge: Particles ──

        private void JsParticlesEnable(string type, bool enabled)
        {
            QueueAction(() => { _particleEnabled[type] = enabled; });
        }

        private void JsParticlesSetDensity(string type, float density)
        {
            QueueAction(() => { _particleDensity[type] = density; });
        }

        // ── JS → C# bridge: Sky ──

        private void JsSkySetColor(float r, float g, float b)
        {
            QueueAction(() => { _skyColor = new Color(r, g, b); });
        }

        private void JsSkySetHorizon(float r, float g, float b)
        {
            QueueAction(() => { _horizonColor = new Color(r, g, b); });
        }

        private void JsSkySetTimeOfDay(float hour)
        {
            QueueAction(() => { _timeOfDay = Mathf.Clamp(hour, 0f, 24f); });
        }

        // ── JS → C# bridge: Wall ──

        private void JsWallEmerge(float dirX, float dirZ, float height, float speed)
        {
            QueueAction(() => { _wallEmergence?.JsEmerge(dirX, dirZ, height, speed); });
        }

        private void JsWallDissolve()
        {
            QueueAction(() => { _wallEmergence?.JsDissolve(); });
        }

        private void JsWallSetColor(float r, float g, float b)
        {
            QueueAction(() => { _wallEmergence?.JsSetWallColor(r, g, b); });
        }

        private void JsWallSetShake(float intensity)
        {
            QueueAction(() => { _wallEmergence?.JsSetShakeIntensity(intensity); });
        }

        // ── JS → C# bridge: General ──

        private void JsLog(string msg) => Debug.Log($"[SoftModule/JS] {msg}");
        private object JsGetParam(string path) => _softLayer?.GetParam<object>(path);

        // ── Apply functions (run on main thread in Update) ──

        private void ApplyChameleon()
        {
            if (_avatarRenderers == null) return;
            foreach (var kvp in _surfaceColors)
            {
                // For now, apply to avatar materials by name match
                // In a full implementation, this would map to named surfaces
                // (walls, floor, furniture, etc.)
            }
        }

        private void ApplyClothing()
        {
            if (_avatarRenderers == null) return;

            foreach (var rend in _avatarRenderers)
            {
                if (rend == null) continue;
                foreach (var mat in rend.materials)
                {
                    if (mat == null) continue;

                    // Apply clothing colors by material name
                    foreach (var colorKvp in _clothingColors)
                    {
                        if (mat.name.ToLowerInvariant().Contains(colorKvp.Key.ToLowerInvariant()))
                        {
                            mat.color = colorKvp.Value;
                        }
                    }

                    // Apply metallic/smoothness
                    if (mat.HasProperty("_Metallic"))
                        mat.SetFloat("_Metallic", _clothingMetallic);
                    if (mat.HasProperty("_Smoothness"))
                        mat.SetFloat("_Smoothness", _clothingSmoothness);
                    if (mat.HasProperty("_Glossiness"))
                        mat.SetFloat("_Glossiness", _clothingSmoothness);
                }
            }
        }

        private void ApplyLighting()
        {
            // Ambient light
            RenderSettings.ambientLight = Color.Lerp(
                RenderSettings.ambientLight, _ambientColor * _ambientIntensity,
                Time.deltaTime * 2f
            );

            // Key light (first directional light)
            if (_sceneLights != null)
            {
                foreach (var light in _sceneLights)
                {
                    if (light == null || light.type != LightType.Directional) continue;
                    light.color = Color.Lerp(light.color, _keyLightColor, Time.deltaTime * 2f);
                    light.intensity = Mathf.Lerp(light.intensity, _keyLightIntensity, Time.deltaTime * 2f);
                    break; // only first directional
                }
            }
        }

        // ── Helpers ──

        private void QueueAction(Action action)
        {
            lock (_actionLock) { _pendingActions.Enqueue(action); }
        }

        public List<string> GetLoadedModules()
        {
            var result = new List<string>();
            foreach (var kvp in _modules)
            {
                if (kvp.Value.loaded && kvp.Value.enabled)
                    result.Add(kvp.Value.name);
            }
            return result;
        }
    }
}
