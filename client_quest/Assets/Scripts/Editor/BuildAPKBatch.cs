using UnityEditor;
using UnityEngine;
using System.IO;
using System.Linq;
using System.Reflection;

public class BuildAPKBatch
{
    public static void Build()
    {
        Debug.Log("[BuildAPKBatch] Configuring Player Settings for Quest 3...");

        PlayerSettings.companyName = "FoveAI";
        PlayerSettings.productName = "AliceVR";
        // 2026-10-09: bumped from com.foveai.alicevr. The Quest still holds an alicevr signed with
        // the ORIGINAL pre-migration key; keystore/alicevr.keystore was minted 2026-10-09 01:14, so
        // every build is a signature mismatch and the install is refused as "conflicts with an
        // existing package" — no amount of re-signing can match that lost key. A new package id
        // installs as a separate app alongside the old one.
        PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android, "com.foveai.alicevr2");

        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel32;
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;

        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        PlayerSettings.Android.forceInternetPermission = true;

        // ── Deterministic signing (2026-10-09) ─────────────────────────────────
        // One dedicated keystore for every build — the install conflict the user
        // hit ("something already installed in the way") came from builds made
        // with different debug keys (machine migration). Release-signed with a
        // fixed key: upgrades install cleanly over prior installs, forever.
        string projectRoot0 = Directory.GetParent(Application.dataPath).FullName;
        string ksPath = Path.Combine(projectRoot0, "keystore", "alicevr.keystore");
        if (File.Exists(ksPath))
        {
            // 2026-10-09: useCustomKeystore is the flag Unity actually gates signing on. Setting
            // keystoreName/pass/alias via script does NOT set it — Unity only auto-sets it when a
            // keystore is chosen through the Inspector. With it false, Unity silently ignored every
            // value above and debug-signed the APK ("CN=Android Debug"), which is what caused the
            // install conflict on the Quest.
            PlayerSettings.Android.useCustomKeystore = true;
            PlayerSettings.Android.keystoreName = ksPath;
            PlayerSettings.Android.keystorePass = "foveai-alicevr";
            PlayerSettings.Android.keyaliasName = "alicevr";
            PlayerSettings.Android.keyaliasPass = "foveai-alicevr";
            Debug.Log($"[BuildAPKBatch] Release keystore wired (useCustomKeystore=true): {ksPath}");
        }
        else
        {
            Debug.LogWarning("[BuildAPKBatch] keystore/alicevr.keystore missing — falling back to debug signing");
        }

        // Disable managed stripping to prevent IL2CPP from stripping Jint and other third-party assemblies
        PlayerSettings.SetManagedStrippingLevel(UnityEditor.Build.NamedBuildTarget.Android, ManagedStrippingLevel.Disabled);
        Debug.Log("[BuildAPKBatch] Set managed stripping level to Disabled for Android");

        // Fix OpenXR + Meta XR settings before building
        Debug.Log("[BuildAPKBatch] Applying Meta XR / OpenXR fixes...");
        FixMetaXRSettings.FixAll();

        // Enable Meta Quest Session feature via reflection
        EnableMetaQuestSessionFeature();

        // Regenerate the FoveAI scene from scratch (headless scene creation)
        Debug.Log("[BuildAPKBatch] Generating FoveAI scene via AutoSceneBuilder...");
        FoveAI.Editor.AutoSceneBuilder.BuildScene();

        // Wire all 17 experiences, HUD, and game systems into the scene before building
        Debug.Log("[BuildAPKBatch] Auto-wiring all 17 experiences and HUD into FoveAI scene...");
        FoveAI.Editor.AutoWireExperiences.WireAll();

        // Reimport OpenXR settings to ensure changes take effect
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

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

    /// <summary>
    /// Enables the "Meta Quest: Session" OpenXR feature via reflection.
    /// This feature is required by the Meta XR OpenXR package but may not be
    /// enabled by default, especially on fresh installations.
    /// </summary>
    private static void EnableMetaQuestSessionFeature()
    {
        var openXRSettingsType = System.Type.GetType("UnityEngine.XR.OpenXR.OpenXRSettings, Unity.XR.OpenXR");
        if (openXRSettingsType == null)
        {
            Debug.LogWarning("[BuildAPKBatch] OpenXRSettings type not found");
            return;
        }

        var getSettingsMethod = openXRSettingsType.GetMethod("GetSettingsForBuildTargetGroup", BindingFlags.Public | BindingFlags.Static);
        if (getSettingsMethod == null) return;

        var androidSettings = getSettingsMethod.Invoke(null, new object[] { BuildTargetGroup.Android });
        if (androidSettings == null) return;

        // Get all features (not just interaction features) and enable Meta Quest ones
        var getFeaturesMethod = openXRSettingsType.GetMethods()
            .FirstOrDefault(m => m.Name == "GetFeatures" && m.IsGenericMethod);
        if (getFeaturesMethod == null) return;

        // Try the base OpenXRFeature type to get ALL features
        var featureBaseType = System.Type.GetType("UnityEngine.XR.OpenXR.Features.OpenXRFeature, Unity.XR.OpenXR");
        if (featureBaseType == null) return;

        var genericGetFeatures = getFeaturesMethod.MakeGenericMethod(featureBaseType);
        var features = (System.Collections.IEnumerable)genericGetFeatures.Invoke(androidSettings, null);

        int enabledCount = 0;
        foreach (var feature in features)
        {
            var featureType = feature.GetType();
            var nameProp = featureType.GetProperty("nameUi");
            var enabledProp = featureType.GetProperty("enabled");
            var nameVal = nameProp?.GetValue(feature) as string ?? featureType.Name;
            var enabledVal = enabledProp?.GetValue(feature) as bool? ?? false;

            // Enable Meta Quest Session and other Meta Quest features
            string typeName = featureType.Name;
            string nameLower = (nameVal ?? "").ToLower();

            // Enable Meta Quest features (but NOT the deprecated OculusQuestFeature)
            if (typeName.Contains("MetaQuest") || typeName.Contains("QuestSession") ||
                nameLower.Contains("meta quest") ||
                typeName.Contains("OculusTouch") || typeName.Contains("MetaAim") ||
                typeName.Contains("BoundaryVisibility") || typeName.Contains("Colocation"))
            {
                if (enabledProp != null && !(bool)enabledProp.GetValue(feature))
                {
                    enabledProp.SetValue(feature, true);
                    Debug.Log($"[BuildAPKBatch] ENABLED: {nameVal} ({typeName})");
                    enabledCount++;
                }
            }

            // Explicitly DISABLE the deprecated OculusQuestFeature
            if (typeName == "OculusQuestFeature")
            {
                if (enabledProp != null && (bool)enabledProp.GetValue(feature))
                {
                    enabledProp.SetValue(feature, false);
                    Debug.Log($"[BuildAPKBatch] DISABLED (deprecated): {nameVal} ({typeName})");
                }
            }

            Debug.Log($"[BuildAPKBatch] Feature: {nameVal} ({typeName}) = {enabledVal}");
        }

        Debug.Log($"[BuildAPKBatch] Enabled {enabledCount} Meta Quest features");

        // Mark settings dirty
        EditorUtility.SetDirty(androidSettings as UnityEngine.Object);
    }
}
