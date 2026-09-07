using UnityEngine;
using UnityEditor;
using FoveAI.DebugOverlay;

namespace FoveAI.Editor
{
    /// <summary>
    /// Adds QuestDebugOverlay and XRRigFixer to the existing scene if they're missing.
    /// Run via menu: Spatial Machine > Add Debug + XR Fixers to Scene
    /// </summary>
    public static class AddDebugToScene
    {
        [MenuItem("Spatial Machine/Add Debug + XR Fixers to Scene")]
        public static void Add()
        {
            var root = GameObject.Find("SpatialMachineRoot");
            if (root == null)
            {
                Debug.LogWarning("[AddDebug] SpatialMachineRoot not found — adding to scene root");
                root = new GameObject("SpatialMachineRoot");
            }

            // Add QuestDebugOverlay if not present
            if (Object.FindAnyObjectByType<QuestDebugOverlay>() == null)
            {
                var debugObj = new GameObject("QuestDebugOverlay");
                debugObj.transform.SetParent(root.transform, false);
                debugObj.AddComponent<QuestDebugOverlay>();
                Debug.Log("[AddDebug] Added QuestDebugOverlay");
            }
            else
            {
                Debug.Log("[AddDebug] QuestDebugOverlay already exists");
            }

            // Add XRRigFixer if not present
            var xrFixerType = System.Type.GetType("FoveAI.XR.XRRigFixer, FoveAI.Runtime");
            if (xrFixerType != null && Object.FindAnyObjectByType(xrFixerType) == null)
            {
                var xrObj = new GameObject("XRRigFixer");
                xrObj.transform.SetParent(root.transform, false);
                xrObj.AddComponent(xrFixerType);
                Debug.Log("[AddDebug] Added XRRigFixer");
            }
            else if (xrFixerType == null)
            {
                Debug.LogWarning("[AddDebug] XRRigFixer type not found — assembly may not be compiled");
            }
            else
            {
                Debug.Log("[AddDebug] XRRigFixer already exists");
            }

            // Mark scene as dirty so it saves
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene());

            Debug.Log("[AddDebug] Done! Save the scene and rebuild.");
            EditorUtility.DisplayDialog("Debug + XR Fixers Added",
                "QuestDebugOverlay and XRRigFixer have been added to the scene.\n\n" +
                "Save the scene (Ctrl+S) then rebuild: Spatial Machine > Configure and Build APK",
                "OK");
        }
    }
}
