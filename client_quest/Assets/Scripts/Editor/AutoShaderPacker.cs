using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using System.Linq;

[InitializeOnLoad]
public class AutoShaderPacker
{
    static AutoShaderPacker()
    {
        EditorApplication.delayCall += InjectShaders;
    }

    private static void InjectShaders()
    {
        var graphicsSettingsAsset = AssetDatabase.LoadAssetAtPath<GraphicsSettings>("ProjectSettings/GraphicsSettings.asset");
        if (graphicsSettingsAsset == null) return;

        SerializedObject graphicsSettings = new SerializedObject(graphicsSettingsAsset);
        SerializedProperty alwaysIncludedShaders = graphicsSettings.FindProperty("m_AlwaysIncludedShaders");

        string[] requiredShaders = new string[] 
        { 
            "VRM10/MToon10", 
            "Standard"
        };

        bool changed = false;

        foreach (string shaderName in requiredShaders)
        {
            Shader shader = Shader.Find(shaderName);
            if (shader == null) continue;

            bool alreadyIncluded = false;
            for (int i = 0; i < alwaysIncludedShaders.arraySize; i++)
            {
                var arrayElement = alwaysIncludedShaders.GetArrayElementAtIndex(i);
                if (arrayElement.objectReferenceValue == shader)
                {
                    alreadyIncluded = true;
                    break;
                }
            }

            if (!alreadyIncluded)
            {
                alwaysIncludedShaders.InsertArrayElementAtIndex(alwaysIncludedShaders.arraySize);
                var newElement = alwaysIncludedShaders.GetArrayElementAtIndex(alwaysIncludedShaders.arraySize - 1);
                newElement.objectReferenceValue = shader;
                changed = true;
                Debug.Log($"[AutoShaderPacker] Injected '{shaderName}' into Always Included Shaders so VRM can load on Android!");
            }
        }

        if (changed)
        {
            graphicsSettings.ApplyModifiedProperties();
            AssetDatabase.SaveAssets();
        }
    }
}
