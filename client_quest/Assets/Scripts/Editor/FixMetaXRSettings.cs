using UnityEditor;
using UnityEngine;
using System.Linq;
using System.Reflection;

public static class FixMetaXRSettings
{
    [MenuItem("Spatial Machine/Fix All Meta XR + OpenXR Settings")]
    public static void FixAll()
    {
        Debug.Log("[FixMetaXR] Starting comprehensive fix...");

        // 1. Force reimport OpenXR settings so disk changes take effect
        var openXRSettingsPath = "Assets/XR/Settings/OpenXRPackageSettings.asset";
        var asset = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(openXRSettingsPath);
        if (asset != null)
        {
            Debug.Log("[FixMetaXR] Reimporting OpenXRPackageSettings.asset to reload API version changes...");
            AssetDatabase.ImportAsset(openXRSettingsPath, ImportAssetOptions.ForceUpdate);
        }

        // 1b. 2026-10-09: XR AUTO-START + loader for Android — the whole reason the
        // installed APK rendered pitch black: automatic XR loading/running was off
        // and no script started OpenXR at runtime. XRGeneralSettings drives the
        // same flags as Assets/XR/XRGeneralSettingsPerBuildTarget.asset but from
        // the build pipeline, so a fresh machine can never ship a dead build.
        try
        {
            var asmXR = System.AppDomain.CurrentDomain.GetAssemblies()
                .FirstOrDefault(a => a.GetName().Name == "Unity.XR.Management");
            if (asmXR != null)
            {
                var settingsType = asmXR.GetType("UnityEditor.XR.Management.XRGeneralSettingsPerBuildTarget", false);
                var editorType = asmXR.GetType("UnityEditor.XR.Management.XRGeneralSettings", false);
                if (settingsType != null && editorType != null)
                {
                    var instanceProp = settingsType.GetProperty("Instance");
                    var perTarget = instanceProp?.GetValue(null);
                    var settingsFor = settingsType.GetMethod("SettingsForBuildTarget",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    var androidTarget = UnityEditor.Build.NamedBuildTarget.Android;
                    var generalSettings = settingsFor?.Invoke(null, new object[] { androidTarget });
                    if (generalSettings != null)
                    {
                        var managerField = generalSettings.GetType().GetField("Manager");
                        var manager = managerField?.GetValue(generalSettings);
                        if (manager != null)
                        {
                            var autoLoad = manager.GetType().GetField("automaticLoading");
                            var autoRun = manager.GetType().GetField("automaticRunning");
                            autoLoad?.SetValue(manager, true);
                            autoRun?.SetValue(manager, true);
                            Debug.Log("[FixMetaXR] XR automaticLoading/Running = true (Android)");
                        }
                    }
                }
            }
        }
        catch (System.Exception e) { Debug.LogWarning($"[FixMetaXR] XR auto-start reflection failed: {e.Message}"); }

        // 2. Android SDK settings
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel32;
        PlayerSettings.Android.targetSdkVersion = (AndroidSdkVersions)0; // auto-detect
        Debug.Log("[FixMetaXR] Set Android SDK versions (min 32, target auto)");

        // 3. IL2CPP + ARM64
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        Debug.Log("[FixMetaXR] Set IL2CPP + ARM64");

        // 4. Install location + permissions
        PlayerSettings.Android.preferredInstallLocation = AndroidPreferredInstallLocation.Auto;
        PlayerSettings.Android.forceInternetPermission = true;
        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        Debug.Log("[FixMetaXR] Set install location, internet permission, insecure HTTP");

        // 5. Color space Linear (Required by Meta XR)
        PlayerSettings.colorSpace = ColorSpace.Linear;
        Debug.Log("[FixMetaXR] Set color space to Linear");

        // 6. Vulkan first for Android
        var apis = new UnityEngine.Rendering.GraphicsDeviceType[]
        {
            UnityEngine.Rendering.GraphicsDeviceType.Vulkan,
            UnityEngine.Rendering.GraphicsDeviceType.OpenGLES3,
        };
        PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, apis);
        Debug.Log("[FixMetaXR] Set Android graphics APIs: Vulkan, OpenGLES3");

        // 7. Graphics Jobs
        PlayerSettings.graphicsJobs = true;
        Debug.Log("[FixMetaXR] Enabled Graphics Jobs");

        // 8. Fix OpenXR Oculus Touch Controller Profile via reflection
        // The Meta XR validation code calls OpenXRSettings.GetSettingsForBuildTargetGroup(Android)
        // then GetFeature<OculusTouchControllerProfile>() which returns null if the feature
        // isn't properly deserialized. We force-enable it via the FeatureHelpers API.
        FixOpenXRFeatures();

        // 9. Save
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        Debug.Log("[FixMetaXR] === ALL FIXES APPLIED ===");
    }

    private static void FixOpenXRFeatures()
    {
        // Use reflection to access OpenXR settings and enable features
        var openXRSettingsType = System.Type.GetType("UnityEngine.XR.OpenXR.OpenXRSettings, Unity.XR.OpenXR");
        if (openXRSettingsType == null)
        {
            Debug.LogWarning("[FixMetaXR] OpenXRSettings type not found — OpenXR package may not be installed");
            return;
        }

        // Get settings for Android build target
        var getSettingsMethod = openXRSettingsType.GetMethod("GetSettingsForBuildTargetGroup", BindingFlags.Public | BindingFlags.Static);
        if (getSettingsMethod == null)
        {
            Debug.LogWarning("[FixMetaXR] GetSettingsForBuildTargetGroup method not found");
            return;
        }

        var androidSettings = getSettingsMethod.Invoke(null, new object[] { BuildTargetGroup.Android });
        if (androidSettings == null)
        {
            Debug.LogWarning("[FixMetaXR] Could not get OpenXR settings for Android");
            return;
        }

        Debug.Log($"[FixMetaXR] Got OpenXR settings for Android: {androidSettings.GetType().Name}");

        // Get all features of type OpenXRInteractionFeature
        var getFeaturesMethod = openXRSettingsType.GetMethods()
            .FirstOrDefault(m => m.Name == "GetFeatures" && m.IsGenericMethod);
        if (getFeaturesMethod == null)
        {
            Debug.LogWarning("[FixMetaXR] GetFeatures method not found");
            return;
        }

        var interactionFeatureType = System.Type.GetType("UnityEngine.XR.OpenXR.Features.OpenXRInteractionFeature, Unity.XR.OpenXR");
        if (interactionFeatureType == null)
        {
            Debug.LogWarning("[FixMetaXR] OpenXRInteractionFeature type not found");
            return;
        }

        var genericGetFeatures = getFeaturesMethod.MakeGenericMethod(interactionFeatureType);
        var features = (System.Collections.IEnumerable)genericGetFeatures.Invoke(androidSettings, null);

        int enabledCount = 0;
        int totalCount = 0;
        foreach (var feature in features)
        {
            totalCount++;
            var featureType = feature.GetType();
            var nameProp = featureType.GetProperty("nameUi");
            var enabledProp = featureType.GetProperty("enabled");
            var nameVal = nameProp?.GetValue(feature) as string ?? featureType.Name;
            var enabledVal = enabledProp?.GetValue(feature) as bool? ?? false;

            // Enable Oculus Touch Controller Profile
            if (featureType.Name == "OculusTouchControllerProfile")
            {
                if (enabledProp != null && !(bool)enabledProp.GetValue(feature))
                {
                    enabledProp.SetValue(feature, true);
                    Debug.Log($"[FixMetaXR] ENABLED: {nameVal} ({featureType.Name})");
                }
                enabledCount++;
            }

            // Also enable Oculus Touch Controller Proximity Profile
            if (featureType.Name == "OculusTouchControllerProximityProfile")
            {
                if (enabledProp != null && !(bool)enabledProp.GetValue(feature))
                {
                    enabledProp.SetValue(feature, true);
                    Debug.Log($"[FixMetaXR] ENABLED: {nameVal} ({featureType.Name})");
                }
                enabledCount++;
            }

            Debug.Log($"[FixMetaXR] Feature: {nameVal} ({featureType.Name}) = {enabledVal}");
        }

        Debug.Log($"[FixMetaXR] Found {totalCount} interaction features, enabled {enabledCount} Touch-related features");

        // Also try the typed GetFeature method for OculusTouchControllerProfile
        var touchProfileType = System.Type.GetType("UnityEngine.XR.OpenXR.Features.Interactions.OculusTouchControllerProfile, Unity.XR.OpenXR");
        if (touchProfileType != null)
        {
            // Use GetMethods and filter to avoid AmbiguousMatchException from multiple overloads
            var getFeatureMethod = openXRSettingsType.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .FirstOrDefault(m => m.Name == "GetFeature" && m.IsGenericMethod && m.GetParameters().Length == 0)
                ?.MakeGenericMethod(touchProfileType);
            if (getFeatureMethod != null)
            {
                var touchFeature = getFeatureMethod.Invoke(androidSettings, null);
                if (touchFeature != null)
                {
                    var enabledProp = touchProfileType.GetProperty("enabled");
                    if (enabledProp != null)
                    {
                        enabledProp.SetValue(touchFeature, true);
                        Debug.Log("[FixMetaXR] OculusTouchControllerProfile found and enabled via GetFeature<T>");
                    }
                }
                else
                {
                    Debug.LogWarning("[FixMetaXR] GetFeature<OculusTouchControllerProfile>() returned null — feature may not be registered");
                }
            }
        }

        // Refresh features via FeatureHelpers — 2026-10-09: NREs inside Unity's
        // RefreshAllFeatureInfo on a fresh machine (empty feature tables).
        // Cosmetic-only refresh: guard it so a clean install can still build.
        var featureHelpersType = System.Type.GetType("UnityEditor.XR.OpenXR.Features.FeatureHelpers, Unity.XR.OpenXR.Editor");
        if (featureHelpersType != null)
        {
            try
            {
                var refreshMethod = featureHelpersType.GetMethod("RefreshFeatures", BindingFlags.Public | BindingFlags.Static);
                if (refreshMethod != null)
                {
                    refreshMethod.Invoke(null, new object[] { BuildTargetGroup.Android });
                    Debug.Log("[FixMetaXR] Refreshed OpenXR features for Android");
                }
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[FixMetaXR] OpenXR feature refresh skipped: {e.InnerException?.Message ?? e.Message}");
            }
        }

        // Mark settings as dirty
        EditorUtility.SetDirty(androidSettings as UnityEngine.Object);
    }
}
