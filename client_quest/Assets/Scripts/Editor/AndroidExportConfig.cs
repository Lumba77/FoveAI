#pragma warning disable CS0618
using UnityEditor;
using UnityEngine;

namespace FoveAI.Editor
{
    public static class AndroidExportConfig
    {
        [MenuItem("Spatial Machine/Configure Android APK Settings")]
        public static void ConfigureForQuest()
        {
            // Set architecture to ARM64 (Required for Meta Quest Store / App Lab)
            PlayerSettings.SetScriptingBackend(BuildTargetGroup.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;

            // Set Android SDK levels (Quest requires API 29+)
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel29;
            PlayerSettings.Android.targetSdkVersion = (AndroidSdkVersions)32; // API 32 is a safe target for Quest 3

            // Graphics
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, new[] { UnityEngine.Rendering.GraphicsDeviceType.OpenGLES3, UnityEngine.Rendering.GraphicsDeviceType.Vulkan });
            
            // Allow Unsafe Code (often needed for advanced XR or networking libraries)
            PlayerSettings.allowUnsafeCode = true;

            // Keystore: We can't auto-generate a keystore here easily, but we ensure development build is checked
            // so they don't get blocked by missing release keystores during iteration.
            EditorUserBuildSettings.development = true;

            Debug.Log("[Spatial Machine] Android APK Export Settings configured for Meta Quest!");
            EditorUtility.DisplayDialog("APK Settings Applied", 
                "Quest Android Build Settings have been applied:\n\n" +
                "• Scripting: IL2CPP\n" +
                "• Architecture: ARM64\n" +
                "• Min API: 29\n" +
                "• Color Space: Linear\n" +
                "• Allow Unsafe Code: True", 
                "OK");
        }
    }
}
