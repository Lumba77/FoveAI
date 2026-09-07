using System.Collections.Generic;
using System.Diagnostics;
using UnityEngine;

namespace FoveAI.IPC
{
    /// <summary>
    /// Launches all FoveAI backend servers (Python) when the Unity scene starts.
    /// Servers:
    ///   1. FoveAI Backend + Media Proxy  — Backend/app/main.py     (port 8400)
    ///   2. XRLF Runtime HTTP API          — run_xrlf.py             (port 8402)
    ///   3. XRLF WebSocket IPC             — run_xrlf.py             (port 8403)
    /// All processes are killed on application quit.
    /// </summary>
    public class BackendLauncher : MonoBehaviour
    {
        [Header("Python Configuration")]
        [Tooltip("Path to the Python executable. Leave empty to auto-detect.")]
        [SerializeField] private string pythonPath = "";

        [Tooltip("Working directory for all backend processes (Backend/ folder).")]
        [SerializeField] private string workingDirectory = "";

        [Header("Server Toggles")]
        [Tooltip("Start the FoveAI backend server (port 8400).")]
        [SerializeField] private bool startMainServer = true;

        [Tooltip("Start the STT Whisper server (port 8011).")]
        [SerializeField] private bool startSTTServer = true;

        [Tooltip("Start the TTS Stream server (port 8012).")]
        [SerializeField] private bool startTTSServer = true;

        [Header("Startup")]
        [Tooltip("If true, starts all servers automatically on Awake. If false, call StartAllBackends() manually.")]
        [SerializeField] private bool autoStart = true;

        [Tooltip("If true, hides the console window on Windows.")]
        [SerializeField] private bool hideConsoleWindow = false;

        [Tooltip("Delay between starting each server (seconds) to avoid port conflicts.")]
        [SerializeField] private float startupDelay = 0.5f;

        private readonly List<Process> _processes = new List<Process>();
        private static readonly string[] ServerScripts = {
            "../../Backend/app/main.py",
            "../../Backend/stt_whisper_server.py",
            "../../Backend/tts_stream_server.py",
        };

        private void Awake()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            // On Quest, the backend runs on the PC — skip launching local Python processes.
            UnityEngine.Debug.Log("[BackendLauncher] Running on Android — skipping local backend launch. Connect to PC backend via WebSocket.");
            autoStart = false;
#endif
            if (autoStart)
            {
                StartAllBackends();
            }
        }

        private void OnApplicationQuit()
        {
            StopAllBackends();
        }

        private void OnDestroy()
        {
            StopAllBackends();
        }

        /// <summary>
        /// Start all enabled backend server processes.
        /// </summary>
        public void StartAllBackends()
        {
            StartCoroutine(StartBackendsCoroutine());
        }

        private System.Collections.IEnumerator StartBackendsCoroutine()
        {
            // Auto-detect Python if not specified
            string py = string.IsNullOrEmpty(pythonPath) ? FindPython() : pythonPath;
            if (string.IsNullOrEmpty(py))
            {
                UnityEngine.Debug.LogError("[BackendLauncher] Python not found. Set pythonPath in the inspector.");
                yield break;
            }

            // Resolve working directory (Backend/ folder)
            string workDir = string.IsNullOrEmpty(workingDirectory)
                ? System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "../../Backend"))
                : workingDirectory;

            if (!System.IO.Directory.Exists(workDir))
            {
                UnityEngine.Debug.LogError($"[BackendLauncher] Working directory not found: {workDir}");
                yield break;
            }

            // Server 1: Main XRLF WebSocket server
            if (startMainServer)
            {
                StartSingleServer(py, ServerScripts[0], workDir, "FoveAI Backend (8400)");
                yield return new WaitForSeconds(startupDelay);
            }

            // Server 2: STT Whisper server
            if (startSTTServer)
            {
                StartSingleServer(py, ServerScripts[1], workDir, "STT Whisper (8011)");
                yield return new WaitForSeconds(startupDelay);
            }

            // Server 3: TTS Stream server
            if (startTTSServer)
            {
                StartSingleServer(py, ServerScripts[2], workDir, "TTS Stream (8012)");
            }
        }

        private void StartSingleServer(string python, string scriptRelative, string workDir, string label)
        {
            string script = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, scriptRelative));
            if (!System.IO.File.Exists(script))
            {
                UnityEngine.Debug.LogWarning($"[BackendLauncher] Script not found: {script} — skipping {label}");
                return;
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = $"\"{script}\"",
                UseShellExecute = !hideConsoleWindow,
                CreateNoWindow = hideConsoleWindow,
                WorkingDirectory = workDir,
                RedirectStandardOutput = hideConsoleWindow,
                RedirectStandardError = hideConsoleWindow
            };

            try
            {
                var proc = Process.Start(startInfo);
                if (proc != null)
                {
                    _processes.Add(proc);
                    UnityEngine.Debug.Log($"[BackendLauncher] Started {label} — PID: {proc.Id} — {python} {script}");
                }
            }
            catch (System.Exception e)
            {
                UnityEngine.Debug.LogError($"[BackendLauncher] Failed to start {label}: {e.Message}");
            }
        }

        /// <summary>
        /// Stop all backend server processes.
        /// </summary>
        public void StopAllBackends()
        {
            foreach (var proc in _processes)
            {
                if (proc != null && !proc.HasExited)
                {
                    try
                    {
                        proc.Kill();
                        proc.WaitForExit(3000);
                    }
                    catch (System.Exception e)
                    {
                        UnityEngine.Debug.LogWarning($"[BackendLauncher] Error stopping process: {e.Message}");
                    }
                }
            }
            _processes.Clear();
            UnityEngine.Debug.Log("[BackendLauncher] All backend servers stopped.");
        }

        /// <summary>
        /// Try to find Python on the system.
        /// </summary>
        private static string FindPython()
        {
            string[] candidates = {
                "python",
                "python3",
                "py",
                @"C:\Python312\python.exe",
                @"C:\Python311\python.exe",
                @"C:\Python310\python.exe",
                @"C:\Users\danie\AppData\Local\Programs\Python\Python312\python.exe",
                @"C:\Users\danie\AppData\Local\Programs\Python\Python311\python.exe",
            };

            foreach (string candidate in candidates)
            {
                try
                {
                    var psi = new ProcessStartInfo
                    {
                        FileName = candidate,
                        Arguments = "--version",
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true
                    };
                    var proc = Process.Start(psi);
                    if (proc != null)
                    {
                        proc.WaitForExit(2000);
                        if (proc.ExitCode == 0)
                        {
                            return candidate;
                        }
                    }
                }
                catch
                {
                    // Try next candidate
                }
            }

            return null;
        }
    }
}