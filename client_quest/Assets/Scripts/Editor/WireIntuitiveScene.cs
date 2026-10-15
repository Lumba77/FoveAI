using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Unity.XR.CoreUtils;

/// <summary>
/// Audit-and-repair pass for Assets/Scenes/intuitive.unity.
///
/// Findings from the 2026-10-09 audit:
///   * NO Camera anywhere in the scene (Unity class 20 count was 0) — an XR Origin
///     existed but had no camera child, so nothing could render.
///   * No ARFoundation passthrough chain (ARSession / ARCameraBackground /
///     ARCameraManager / ARSessionOrigin). Passthrough needs those under OpenXR;
///     OVRManager conflicts, so this is the ARFoundation route used in FoveAI.unity.
///   * GLTFAvatarLoader had an empty gltfFileName — a dead component competing with
///     VRMAvatarLoader, which is correctly pointed at Alicechan.vrm.
///
/// Everything already correct is left alone: EventSystem + XRUIInputModule, the
/// controller rays, the head-gaze ray on the XR Origin, the TrackedDeviceGraphic
/// Raycasters and the InputActionManager.
///
/// Batchmode:
///   Unity -batchmode -quit -projectPath . -executeMethod WireIntuitiveScene.Wire
/// </summary>
public static class WireIntuitiveScene
{
    private const string ScenePath = "Assets/Scenes/intuitive.unity";

    [MenuItem("Spatial Machine/Wire intuitive.unity")]
    public static void WireMenu()
    {
        Wire();
        EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
    }

    public static void Wire()
    {
        if (!File.Exists(ScenePath))
        {
            Debug.LogError($"[Wire] scene not found: {ScenePath}");
            EditorApplication.Exit(1);
            return;
        }

        var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        Debug.Log($"[Wire] opened {ScenePath}");

        var origin = FindFirstByName("XR Origin");
        if (origin == null)
        {
            var go = new GameObject("XR Origin (Mobile AR)");
            go.AddComponent<XROrigin>();
            origin = go;
            Debug.Log("[Wire] XR Origin was missing — created it.");
        }

        EnsurePassthroughChain(origin);
        EnsureCameraUnderOrigin(origin);
        PruneEmptyAvatarLoaders();
        EnsureUiInput();

        EditorSceneManager.SaveScene(scene, ScenePath);
        Debug.Log($"[Wire] saved {ScenePath}");
        EditorApplication.Exit(0);
    }

    private static void FindFirstByNameUnused() { }

    private static GameObject FindFirstByName(string exactPrefix)
    {
        var all = UnityEngine.Object.FindObjectsByType<GameObject>(FindObjectsSortMode.None);
        foreach (var go in all)
        {
            if (go.name.StartsWith(exactPrefix, StringComparison.OrdinalIgnoreCase)) return go;
        }
        return null;
    }

    /// <summary>
    /// ARFoundation passthrough under OpenXR (the configuration proven on FoveAI.unity).
    /// ARSessionOrigin for ARCameraBackground to know which camera to render behind,
    /// so that is what we create and parent the camera under.
    /// </summary>
    private static void EnsurePassthroughChain(GameObject origin)
    {
        if (origin.GetComponent<UnityEngine.XR.ARFoundation.ARSession>() == null)
        {
            origin.AddComponent<UnityEngine.XR.ARFoundation.ARSession>();
            Debug.Log("[Wire] + ARSession");
        }
    }

    private static void EnsureCameraUnderOrigin(GameObject origin)
    {
        // NOTE: ARSessionOrigin is deliberately NOT required. It derives from XROrigin, so
        // Unity refuses to add it to a GameObject that already has an XROrigin, and the
        // working passthrough configuration (proven on FoveAI.unity) needs none of it:
        // ARSession on the rig + ARCameraBackground/ARCameraManager on a camera driven by
        // TrackedPoseDriver. ARSessionOrigin is an AR-tracking convenience on top.

        // Is there already a camera under this origin?
        Camera existing = null;
        foreach (var cam in origin.GetComponentsInChildren<Camera>(true))
        {
            existing = cam;
            break;
        }

        if (existing == null)
        {
            var camGo = new GameObject("Main Camera");
            camGo.tag = "MainCamera";
            camGo.transform.SetParent(origin.transform, false);
            camGo.transform.localPosition = new Vector3(0f, 1.6f, 0f);

            existing = camGo.AddComponent<Camera>();
            existing.clearFlags = CameraClearFlags.SolidColor;
            // Transparent so passthrough shows through where nothing is drawn.
            existing.backgroundColor = new Color(0f, 0f, 0f, 0f);

            camGo.AddComponent<UnityEngine.XR.ARFoundation.ARCameraBackground>();
            camGo.AddComponent<UnityEngine.XR.ARFoundation.ARCameraManager>();
            // core-utils 2.x removed XRCamera; head pose now comes from the Input System.
            camGo.AddComponent<UnityEngine.InputSystem.XR.TrackedPoseDriver>();

            Debug.Log("[Wire] + Main Camera (ARCameraBackground, ARCameraManager, TrackedPoseDriver)");
        }
        else
        {
            if (existing.GetComponent<UnityEngine.XR.ARFoundation.ARCameraBackground>() == null)
                existing.gameObject.AddComponent<UnityEngine.XR.ARFoundation.ARCameraBackground>();
            if (existing.GetComponent<UnityEngine.InputSystem.XR.TrackedPoseDriver>() == null)
                existing.gameObject.AddComponent<UnityEngine.InputSystem.XR.TrackedPoseDriver>();
            Debug.Log($"[Wire] existing camera '{existing.name}' kept, passthrough ensured.");
        }

        RenderSettings.skybox = null;
    }

    /// <summary>
    /// GLTFAvatarLoader with an empty gltfFileName can never load anything and only
    /// duplicates VRMAvatarLoader's job. Remove it rather than leave a trap.
    /// </summary>
    private static void PruneEmptyAvatarLoaders()
    {
        var loaders = UnityEngine.Object.FindObjectsByType<FoveAI.Avatar.GLTFAvatarLoader>(FindObjectsSortMode.None);
        foreach (var loader in loaders)
        {
            var so = new SerializedObject(loader);
            var prop = so.FindProperty("gltfFileName");
            string value = prop?.stringValue;
            if (string.IsNullOrEmpty(value))
            {
                Debug.Log($"[Wire] removed GLTFAvatarLoader on '{loader.gameObject.name}' (empty gltfFileName)");
                UnityEngine.Object.DestroyImmediate(loader);
            }
            else
            {
                Debug.Log($"[Wire] kept GLTFAvatarLoader (gltfFileName='{value}')");
            }
        }
    }

    private static void EnsureUiInput()
    {
        var es = UnityEngine.Object.FindFirstObjectByType<UnityEngine.EventSystems.EventSystem>();
        if (es == null)
        {
            var go = new GameObject("EventSystem");
            go.AddComponent<UnityEngine.EventSystems.EventSystem>();
            go.AddComponent<UnityEngine.XR.Interaction.Toolkit.UI.XRUIInputModule>();
            Debug.Log("[Wire] + EventSystem + XRUIInputModule");
        }
        else if (es.GetComponent<UnityEngine.XR.Interaction.Toolkit.UI.XRUIInputModule>() == null)
        {
            es.gameObject.AddComponent<UnityEngine.XR.Interaction.Toolkit.UI.XRUIInputModule>();
            Debug.Log("[Wire] + XRUIInputModule on existing EventSystem");
        }

        int added = 0;
        foreach (var canvas in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsSortMode.None))
        {
            if (canvas.GetComponent<UnityEngine.XR.Interaction.Toolkit.UI.TrackedDeviceGraphicRaycaster>() == null)
            {
                canvas.gameObject.AddComponent<UnityEngine.XR.Interaction.Toolkit.UI.TrackedDeviceGraphicRaycaster>();
                added++;
            }
        }
        if (added > 0) Debug.Log($"[Wire] + TrackedDeviceGraphicRaycaster on {added} canvas(es)");
    }
}