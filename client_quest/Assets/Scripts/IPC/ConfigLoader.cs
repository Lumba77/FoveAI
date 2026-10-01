using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace FoveAI.Config
{
    [System.Serializable]
    public class AppSettings
    {
        public string serverIp = "192.168.8.100";
        public int wsPort = 8403;              // WebSocket IPC — chat, TTS, STT, motor, animation
        public int httpPort = 8402;            // XRLF HTTP API (/v1/chat, /v1/audio, /api/camera, /api/web)
        public int soulPort = 8405;            // Soul/Compagent API (/api/environment, /api/soul, persona, tasks)
        public int memoryPort = 8400;          // Memory proxy / backend HTTP
        public int chatRelayPort = 8407;       // 4-Way XR Chat Relay
        public string avatarModel = "Alicechan.vrm";
    }

    public static class ConfigLoader
    {
        public static AppSettings Settings { get; private set; } = new AppSettings();
        public static bool IsLoaded { get; private set; } = false;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        public static async void LoadConfigOnStartup()
        {
            await LoadConfigAsync();
        }

        public static async Task LoadConfigAsync()
        {
            if (IsLoaded) return;

            // On Android, check persistentDataPath first (user-saved settings override)
            string persistentPath = Path.Combine(Application.persistentDataPath, "AppConfig.json");
            string configPath = Path.Combine(Application.streamingAssetsPath, "AppConfig.json");
            string json = "";

#if UNITY_ANDROID && !UNITY_EDITOR
            // Try persistentDataPath first (saved by AppSettingsPanel)
            try
            {
                if (File.Exists(persistentPath))
                {
                    json = File.ReadAllText(persistentPath);
                    Debug.Log($"[ConfigLoader] Loaded config from persistentDataPath: {persistentPath}");
                }
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[ConfigLoader] Could not read persistent config: {e.Message}");
            }

            // Fall back to StreamingAssets if no persistent config
            if (string.IsNullOrEmpty(json))
            {
                using (UnityWebRequest uwr = UnityWebRequest.Get(configPath))
                {
                    var operation = uwr.SendWebRequest();
                    while (!operation.isDone) await Task.Yield();

                    if (uwr.result == UnityWebRequest.Result.Success)
                    {
                        json = uwr.downloadHandler.text;
                    }
                    else
                    {
                        Debug.LogWarning($"[ConfigLoader] Failed to load AppConfig.json from APK: {uwr.error}. Using default settings.");
                    }
                }
            }
#else
            if (File.Exists(persistentPath))
            {
                json = File.ReadAllText(persistentPath);
                Debug.Log($"[ConfigLoader] Loaded config from persistentDataPath: {persistentPath}");
            }
            else if (File.Exists(configPath))
            {
                json = File.ReadAllText(configPath);
            }
            else
            {
                Debug.LogWarning($"[ConfigLoader] AppConfig.json not found at {configPath}. Using defaults.");
            }
#endif

            if (!string.IsNullOrEmpty(json))
            {
                try
                {
                    Settings = JsonUtility.FromJson<AppSettings>(json);
                    Debug.Log($"[ConfigLoader] Successfully loaded config. IP: {Settings.serverIp}, WS Port: {Settings.wsPort}");
                }
                catch (System.Exception ex)
                {
                    Debug.LogError($"[ConfigLoader] Failed to parse AppConfig.json: {ex.Message}");
                }
            }

            IsLoaded = true;
        }
    }
}

