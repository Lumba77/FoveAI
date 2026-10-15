using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using Jint;

namespace FoveAI.SoftLayer
{
    /// <summary>
    /// SoftLayer Engine — Hot-reloadable JavaScript layer for the Quest app.
    ///
    /// This is the "soft code" layer that sits on top of the native Unity
    /// APK. It loads JavaScript modules from the backend server and executes
    /// them via Jint (a pure C# JS interpreter that works on IL2CPP/Quest).
    ///
    /// Architecture:
    ///   Native Unity (APK) → SoftLayer (JS, hot-reloadable) → Backend (Python)
    ///
    /// What the soft layer can control:
    ///   - HUD colors, positions, alpha, labels
    ///   - Avatar animation triggers and gesture probabilities
    ///   - Experience parameters (seasonal, touring, director)
    ///   - UI panel layouts and visibility
    ///   - Behavior tuning (gaze intervals, decision rates, etc.)
    ///   - Director event scripts and timing
    ///
    /// Hot-reload flow:
    ///   1. Developer edits a .js file in softlayer/ on the backend
    ///   2. Backend watches for file changes
    ///   3. Backend pushes the updated module via WebSocket (softlayer.update event)
    ///   4. SoftLayerEngine receives the update, re-evaluates the module
    ///   5. Changes take effect immediately — no APK rebuild
    ///
    /// The JS context exposes a "FoveAI" global object with methods to
    /// interact with the Unity scene:
    ///   FoveAI.setHUDColor(corner, color)
    ///   FoveAI.setHUDValue(corner, value)
    ///   FoveAI.setHUDLabel(corner, label)
    ///   FoveAI.setHUDAlpha(alpha)
    ///   FoveAI.triggerGesture(name)
    ///   FoveAI.setEmotion(emotion, intensity)
    ///   FoveAI.setParam(path, value)   // e.g. "avatar.gazeInterval" = 3.0
    ///   FoveAI.getParam(path)
    ///   FoveAI.log(msg)
    ///   FoveAI.onUpdate(dt)             // called every frame if defined
    /// </summary>
    public class SoftLayerEngine : MonoBehaviour
    {
        [Header("Backend")]
        [Tooltip("Base URL for fetching soft modules (e.g. http://192.168.8.109:8402)")]
        [SerializeField] private string backendUrl = "http://192.168.8.109:8402";

        [Tooltip("WebSocket URL for hot-reload pushes")]
        [SerializeField] private string wsUrl = "ws://192.168.8.109:8403/ws";

        [Header("Modules")]
        [Tooltip("Module names to load on startup (without .js extension)")]
        [SerializeField] private string[] modulesToLoad = {
            "hud_config",
            "behavior_config",
            "experience_config",
        };

        [Header("Debug")]
        [SerializeField] private bool verbose = true;

        // ── Jint engine ──
        private Engine _js;
        private bool _jsReady;

        // ── Loaded modules ──
        private readonly Dictionary<string, string> _moduleSources = new();
        private readonly Dictionary<string, bool> _moduleLoaded = new();

        // ── Parameters (settable from JS, readable from C#) ──
        private readonly Dictionary<string, object> _params = new();

        // ── Pending actions (queued from JS thread, applied on main thread) ──
        private readonly Queue<Action> _pendingActions = new();
        private readonly object _actionLock = new();

        // ── References ──
        private UI.UserHUD _hud;
        private Avatar.AvatarAnimationBrain _avatarBrain;
        private Avatar.VRMAAnimationLoader _vrmaLoader;

        // ── Unity lifecycle ──

        private async void Start()
        {
            // Derive backend URL from central config (AppConfig.json) instead of hardcoded IP
            var cfg = FoveAI.Config.ConfigLoader.Settings;
            if (cfg != null && !string.IsNullOrEmpty(cfg.serverIp))
            {
                backendUrl = $"http://{cfg.serverIp}:{cfg.httpPort}";
                wsUrl = $"ws://{cfg.serverIp}:{cfg.wsPort}/ws";
            }

            _hud = FindAnyObjectByType<UI.UserHUD>();
            _avatarBrain = FindAnyObjectByType<Avatar.AvatarAnimationBrain>();
            _vrmaLoader = FindAnyObjectByType<Avatar.VRMAAnimationLoader>();

            InitJintEngine();
            await LoadAllModulesAsync();

            if (verbose)
                Debug.Log("[SoftLayer] Ready — soft code layer active");
        }

        private void Update()
        {
            // Apply pending actions from JS on main thread
            lock (_actionLock)
            {
                while (_pendingActions.Count > 0)
                {
                    var action = _pendingActions.Dequeue();
                    try { action.Invoke(); }
                    catch (Exception e) { Debug.LogWarning($"[SoftLayer] Action error: {e.Message}"); }
                }
            }

            // Call JS onUpdate if defined
            if (_jsReady)
            {
                try
                {
                    _js.Execute($"if (typeof FoveAI_onUpdate === 'function') FoveAI_onUpdate({Time.deltaTime});");
                }
                catch { /* ignore JS errors in update loop */ }
            }
        }

        // ── Jint initialization ──

        private void InitJintEngine()
        {
            _js = new Engine(opts => opts
                .LimitRecursion(100)
                .TimeoutInterval(TimeSpan.FromSeconds(2))
            );

            // Expose FoveAI API to JS
            _js.SetValue("FoveAI_log", (Action<string>)JsLog);
            _js.SetValue("FoveAI_setHUDColor", (Action<string, float, float, float, float>)JsSetHUDColor);
            _js.SetValue("FoveAI_setHUDValue", (Action<string, string>)JsSetHUDValue);
            _js.SetValue("FoveAI_setHUDLabel", (Action<string, string>)JsSetHUDLabel);
            _js.SetValue("FoveAI_setHUDAlpha", (Action<float>)JsSetHUDAlpha);
            _js.SetValue("FoveAI_triggerGesture", (Action<string>)JsTriggerGesture);
            _js.SetValue("FoveAI_setEmotion", (Action<string, float>)JsSetEmotion);
            _js.SetValue("FoveAI_setParam", (Action<string, object>)JsSetParam);
            _js.SetValue("FoveAI_getParam", (Func<string, object>)JsGetParam);
            _js.SetValue("FoveAI_setAvatarParam", (Action<string, float>)JsSetAvatarParam);

            // Define the FoveAI global object
            _js.Execute(@"
                var FoveAI = {
                    log: FoveAI_log,
                    setHUDColor: FoveAI_setHUDColor,
                    setHUDValue: FoveAI_setHUDValue,
                    setHUDLabel: FoveAI_setHUDLabel,
                    setHUDAlpha: FoveAI_setHUDAlpha,
                    triggerGesture: FoveAI_triggerGesture,
                    setEmotion: FoveAI_setEmotion,
                    setParam: FoveAI_setParam,
                    getParam: FoveAI_getParam,
                    setAvatarParam: FoveAI_setAvatarParam,
                };
            ");

            _jsReady = true;
            if (verbose)
                Debug.Log("[SoftLayer] Jint engine initialized");
        }

        // ── Module loading ──

        private async Task LoadAllModulesAsync()
        {
            foreach (var moduleName in modulesToLoad)
            {
                await LoadModuleAsync(moduleName);
            }
        }

        private async Task LoadModuleAsync(string moduleName)
        {
            try
            {
                string url = $"{backendUrl}/softlayer/{moduleName}.js";
                if (verbose)
                    Debug.Log($"[SoftLayer] Fetching {moduleName} from {url}");

                using var client = new HttpClient();
                client.Timeout = TimeSpan.FromSeconds(5);
                var response = await client.GetStringAsync(url);

                if (!string.IsNullOrEmpty(response))
                {
                    _moduleSources[moduleName] = response;
                    ExecuteModule(moduleName, response);
                }
            }
            catch (Exception e)
            {
                if (verbose)
                    Debug.LogWarning($"[SoftLayer] Could not load {moduleName}: {e.Message}");
            }
        }

        private void ExecuteModule(string moduleName, string source)
        {
            if (!_jsReady) return;

            try
            {
                _js.Execute(source);
                _moduleLoaded[moduleName] = true;
                if (verbose)
                    Debug.Log($"[SoftLayer] Module '{moduleName}' loaded ({source.Length} bytes)");
            }
            catch (Exception e)
            {
                _moduleLoaded[moduleName] = false;
                Debug.LogError($"[SoftLayer] JS error in '{moduleName}': {e.Message}");
            }
        }

        /// <summary>
        /// Hot-reload a module from a WS push. Called when the backend
        /// sends a softlayer.update event.
        /// </summary>
        public void HotReloadModule(string moduleName, string source)
        {
            _moduleSources[moduleName] = source;
            ExecuteModule(moduleName, source);
        }

        // ── JS → C# bridge methods ──

        private void JsLog(string msg)
        {
            Debug.Log($"[SoftLayer/JS] {msg}");
        }

        private void JsSetHUDColor(string corner, float r, float g, float b, float a)
        {
            QueueAction(() =>
            {
                if (_hud == null) return;
                // We can't directly set corner colors from here without
                // adding public methods to UserHUD, but we can set params
                // that UserHUD reads. For now, store as param.
                _params[$"hud.color.{corner}"] = new Color(r, g, b, a);
            });
        }

        private void JsSetHUDValue(string corner, string value)
        {
            QueueAction(() =>
            {
                _params[$"hud.value.{corner}"] = value;
            });
        }

        private void JsSetHUDLabel(string corner, string label)
        {
            QueueAction(() =>
            {
                _params[$"hud.label.{corner}"] = label;
            });
        }

        private void JsSetHUDAlpha(float alpha)
        {
            QueueAction(() =>
            {
                _params["hud.alpha"] = alpha;
            });
        }

        private void JsTriggerGesture(string name)
        {
            QueueAction(() =>
            {
                if (_avatarBrain != null)
                    _avatarBrain.PlayGesture(name);
            });
        }

        private void JsSetEmotion(string emotion, float intensity)
        {
            QueueAction(() =>
            {
                if (_avatarBrain != null)
                    _avatarBrain.SetEmotion(emotion, intensity);
            });
        }

        private void JsSetParam(string path, object value)
        {
            _params[path] = value;
        }

        private object JsGetParam(string path)
        {
            return _params.TryGetValue(path, out var val) ? val : null;
        }

        private void JsSetAvatarParam(string param, float value)
        {
            QueueAction(() =>
            {
                // Map common avatar params
                switch (param)
                {
                    case "gazeAtUserProbability":
                        // Would need public setter on AvatarAnimationBrain
                        _params[$"avatar.{param}"] = value;
                        break;
                    case "decisionInterval":
                        _params[$"avatar.{param}"] = value;
                        break;
                    default:
                        _params[$"avatar.{param}"] = value;
                        break;
                }
            });
        }

        // ── Helpers ──

        private void QueueAction(Action action)
        {
            lock (_actionLock)
            {
                _pendingActions.Enqueue(action);
            }
        }

        /// <summary>
        /// Get a soft param value from C# code. Allows native components
        /// to read values set by the JS soft layer.
        /// </summary>
        public T GetParam<T>(string path, T defaultValue = default)
        {
            if (_params.TryGetValue(path, out var val))
            {
                try { return (T)Convert.ChangeType(val, typeof(T)); }
                catch { return defaultValue; }
            }
            return defaultValue;
        }

        /// <summary>
        /// Check if a param exists.
        /// </summary>
        public bool HasParam(string path) => _params.ContainsKey(path);
    }
}
