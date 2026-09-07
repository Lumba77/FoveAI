using UnityEngine;
using UnityEditor;
using System.Reflection;
using System;

[InitializeOnLoad]
public class AutoFixScript
{
    static AutoFixScript()
    {
        EditorApplication.delayCall += RunFixes;
    }

    static void RunFixes()
    {
        if (EditorPrefs.GetBool("AutoFixRun_v2", false))
            return;
        
        bool fixesApplied = false;

        // 1. (Disabled) Delete BackendLauncher
        // We now want BackendLauncher to run so it can boot the TTS server!
        // var backendObj = GameObject.Find("BackendLauncher");
        // if (backendObj != null) { ... }

        // 2. Set App IDs via Reflection to bypass asmdef boundaries!
        try
        {
            // Find the Oculus.Platform assembly
            Assembly oculusAssembly = null;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                if (asm.GetName().Name == "Oculus.Platform")
                {
                    oculusAssembly = asm;
                    break;
                }
            }

            if (oculusAssembly != null)
            {
                Type settingsType = oculusAssembly.GetType("Oculus.Platform.PlatformSettings");
                if (settingsType != null)
                {
                    var appIdProp = settingsType.GetProperty("AppID", BindingFlags.Public | BindingFlags.Static);
                    var mobileAppIdProp = settingsType.GetProperty("MobileAppID", BindingFlags.Public | BindingFlags.Static);
                    
                    if (appIdProp != null) appIdProp.SetValue(null, "1234567890");
                    if (mobileAppIdProp != null) mobileAppIdProp.SetValue(null, "1234567890");

                    var instanceProp = settingsType.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static);
                    if (instanceProp != null)
                    {
                        var instance = instanceProp.GetValue(null);
                        if (instance != null)
                        {
                            EditorUtility.SetDirty((UnityEngine.Object)instance);
                            AssetDatabase.SaveAssets();
                            Debug.Log("✅ [AutoFix] Successfully set Meta Platform App ID to 1234567890 via Reflection.");
                            fixesApplied = true;
                        }
                    }
                }
            }
            else
            {
                Debug.LogWarning("[AutoFix] Could not find Oculus.Platform assembly via reflection.");
            }
        }
        catch (Exception ex)
        {
            Debug.LogError($"[AutoFix] Failed to set App ID via reflection: {ex.Message}");
        }

        if (fixesApplied)
        {
            EditorPrefs.SetBool("AutoFixRun_v2", true);
        }
    }
}
