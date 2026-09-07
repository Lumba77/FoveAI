using UnityEditor;
using UnityEngine;
using System.IO;

public class BuildAPKBatch
{
    public static void Build()
    {
        Debug.Log("[BuildAPKBatch] Configuring Player Settings for Quest 3...");

        PlayerSettings.companyName = "FoveAI";
        PlayerSettings.productName = "AliceVR";
        PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android, "com.foveai.alicevr");

        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel32;
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;

        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        PlayerSettings.Android.forceInternetPermission = true;

        string scenePath = "Assets/Scenes/FoveAI.unity";
        string projectRoot = Directory.GetParent(Application.dataPath).FullName;
        string fullScenePath = Path.Combine(projectRoot, scenePath);

        if (!File.Exists(fullScenePath))
        {
            Debug.LogError($"[BuildAPKBatch] Scene not found: {fullScenePath}");
            EditorApplication.Exit(1);
            return;
        }

        string[] scenes = { scenePath };
        string buildPath = Path.Combine(projectRoot, "AliceVR.apk");

        Debug.Log($"[BuildAPKBatch] Building APK to: {buildPath}");

        var report = BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.Android, BuildOptions.None);

        if (report.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded)
        {
            Debug.Log($"[BuildAPKBatch] BUILD SUCCESSFUL! Saved to: {buildPath}");
            EditorApplication.Exit(0);
        }
        else
        {
            Debug.LogError($"[BuildAPKBatch] BUILD FAILED! Result: {report.summary.result}");
            Debug.LogError($"[BuildAPKBatch] Total errors: {report.summary.totalErrors}, Total warnings: {report.summary.totalWarnings}");
            EditorApplication.Exit(1);
        }
    }
}
