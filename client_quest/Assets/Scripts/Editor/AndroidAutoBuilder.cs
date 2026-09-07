using UnityEditor;
using UnityEngine;
using System.IO;

public class AndroidAutoBuilder
{
    [MenuItem("Spatial Machine/Configure and Build APK")]
    public static void ConfigureAndBuild()
    {
        Debug.Log("[AutoBuilder] Configuring Player Settings for Quest 3...");

        // 1. Force the correct Android build settings
        PlayerSettings.companyName = "FoveAI";
        PlayerSettings.productName = "AliceVR";
        PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android, "com.foveai.alicevr");

        // Quest 3 requirements
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel32;
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        
        // Networking Permissions for Local WebSockets (Crucial for APK!)
        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        PlayerSettings.Android.forceInternetPermission = true;
        
        // 2. Use the known scene path — the real scene with XR rig, avatar, and IPC
        // AutoSceneBuilder writes to Assets/Scenes/FoveAI.unity — that's the one to build
        string scenePath = "Assets/Scenes/FoveAI.unity";
        if (!System.IO.File.Exists(System.IO.Path.Combine(Application.dataPath, "..", scenePath)))
        {
            // Fallback: try the Samples scene
            scenePath = "Assets/Samples/Scenes/FoveAI.unity";
        }
        if (!System.IO.File.Exists(System.IO.Path.Combine(Application.dataPath, "..", scenePath)))
        {
            // Last resort: grab the current scene
            var currentScene = UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
            scenePath = currentScene.path;
            if (string.IsNullOrEmpty(scenePath))
            {
                Debug.LogError("[AutoBuilder] No valid scene found!");
                return;
            }
        }

        string[] scenes = { scenePath };
        
        // 3. Build to the main project folder
        string projectRoot = Directory.GetParent(Application.dataPath).FullName;
        string buildPath = Path.Combine(projectRoot, "AliceVR.apk");

        Debug.Log($"[AutoBuilder] Starting Android Build to: {buildPath}");

        // 4. Trigger the build
        var report = BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.Android, BuildOptions.None);

        if (report.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded)
        {
            Debug.Log($"[AutoBuilder] BUILD SUCCESSFUL! Saved to: {buildPath}");
            if (!Application.isBatchMode)
            {
                try { EditorUtility.DisplayDialog("Build Success", $"APK successfully built to:\n{buildPath}", "Awesome"); }
                catch { Debug.Log("[AutoBuilder] (dialog suppressed — too many window handles)"); }
                try { EditorUtility.RevealInFinder(buildPath); } catch { }
            }
        }
        else
        {
            Debug.LogError("[AutoBuilder] BUILD FAILED! Check console for errors.");
            if (!Application.isBatchMode)
            {
                EditorUtility.DisplayDialog("Build Failed", "The build failed. Check the Unity Console for errors.", "OK");
            }
        }
    }
}
