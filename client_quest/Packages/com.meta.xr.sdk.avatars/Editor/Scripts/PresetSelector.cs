/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * Licensed under the Oculus SDK License Agreement (the "License");
 * you may not use the Oculus SDK except in compliance with the License,
 * which is provided at the time of installation or download, or which
 * otherwise accompanies this software in either electronic or hard copy form.
 *
 * You may obtain a copy of the License at
 *
 * https://developer.oculus.com/licenses/oculussdk/
 *
 * Unless required by applicable law or agreed to in writing, the Oculus SDK
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#nullable enable

using System;
using System.Collections.Generic;
using Oculus.Avatar2.Experimental;
using UnityEditor;
using UnityEngine;

namespace Oculus.Avatar2
{
    public class AvatarPresetSelector : ScriptableObject
    {

        public static string PresetPopupKey = "FirstTimePresetPopupShown";

        public static string UniquePresetPopupKey = Application.dataPath + "_" + PresetPopupKey;

        public static string UnzippedPresetChecksumKey = "UnzippedPresetCheckSum";

        public static void RepackageWithPresetSelections(bool[] qualitySelection, bool[] avatarSelection)
        {
            IReadOnlyCollection<string> selectedGlbs = PresetHelper.GetSelectedGlbs(qualitySelection, avatarSelection);
            // Always force repackage after presets have been selected
            PresetPackager.PackagePresetsInDirectory(PresetPackager.DefaultSourceDestPaths, true, true, new[] { ".meta" }, selectedGlbs);

            PresetSelectionInfo presetInfo = ScriptableObject.CreateInstance<PresetSelectionInfo>();
            presetInfo.qualitySelection = qualitySelection;
            presetInfo.avatarSelection = avatarSelection;
            AssetDatabase.CreateAsset(presetInfo, PresetHelper.presetSelectionAssetPath);
        }

        [MenuItem("MetaAvatarsSDK/Assets/Sample Assets/Preset Selector")]
        public static void Reselect()
        {
            AvatarPresetSelectorPopupDialog.ShowWindow();
        }
    }

    [InitializeOnLoad]
    public class AvatarPresetSelectorTrigger
    {
        static AvatarPresetSelectorTrigger()
        {
            if (!SessionState.GetBool("PresetSelectionWindowRanOnce", false))
            {
                EditorApplication.update += RunOnce;
            }
        }

        static void RunOnce()
        {
            if (!EditorPrefs.GetBool(AvatarPresetSelector.UniquePresetPopupKey))
            {
                AvatarPresetConfigurePopupDialog.ShowWindow();
                SetDefaultPresetIncludes();
            }
            else if (StreamingAssetsHelper.HasDirectoryUpdated(PresetHelper.presetUnpackagedDirectory, AvatarPresetSelector.UnzippedPresetChecksumKey, true))
            {
                Debug.Log("Detected changes to unpackaged presets, displaying popup for reselection");
                AvatarPresetConfigurePopupDialog.ShowWindow();
                SetDefaultPresetIncludes();
            }
            else
            {
                Debug.Log("Preset already selected, you can reselect from: MetaAvatarsSDK/Assets/Sample Assets/Preset Selector");
            }
            SessionState.SetBool("PresetSelectionWindowRanOnce", true);
            EditorApplication.update -= RunOnce;
        }

        private static void SetDefaultPresetIncludes()
        {
            for (int i = 0; i < PresetHelper.numPresetQualityTypes; i++)
            {
                PresetHelper.PresetQualityType preset = (PresetHelper.PresetQualityType)Enum.ToObject(typeof(PresetHelper.PresetQualityType), i);
                string presetName = Enum.GetName(typeof(PresetHelper.PresetQualityType), preset);
                EditorPrefs.SetBool(presetName, true);
            }
        }
    }

    public class AvatarPresetConfigurePopupDialog : EditorWindow
    {
        private static AvatarPresetConfigurePopupDialog? _instance;

        public static void ShowWindow()
        {
            if (_instance)
            {
                return;
            }

            EditorApplication.quitting += Quit;
            float width = 500;
            float height = 280;
            float x = (EditorGUIUtility.GetMainWindowPosition().center.x - width / 2.0f);
            float y = 100;
            var window = GetWindow(typeof(AvatarPresetConfigurePopupDialog), true, "[Optional] Configure Meta Avatars SDK Sample Assets", true);
            window.position = new Rect(x, y, width, height);
        }

        private void OnEnable()
        {
            _instance = this;
        }

        static void Quit()
        {
            if (_instance != null)
            {
                _instance.Close();
            }
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField(
                "By default the Avatar SDK includes a set of on-disk avatars that will increase the size of your build. \n\n" +
                "These assets include preset avatars used in the Meta Avatars SDK examples. " +
                "These presets are most comonly used to provide an avatar to someone that might not have an avatar asociated with their account " +
                "or as avatar representations for NPCs in your app.\n\n" +
                "Note, you can also configure preset selections from menu:\n" +
                "MetaAvatarsSDK > Assets > Sample Assets > Preset Selector\n",
                EditorStyles.wordWrappedLabel);

            using (new GUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Include All (Do not show again)"))
                {
                    if (_instance != null)
                    {
                        // No longer display pop-up after selection, it can manually be opened from menu options.
                        EditorPrefs.SetBool(AvatarPresetSelector.UniquePresetPopupKey, true);
                        _instance.Close();
                    }
                    EditorApplication.quitting -= Quit;
                }
                GUILayout.Space(10);
                if (GUILayout.Button("Configure"))
                {
                    AvatarPresetSelector.Reselect();
                    if (_instance != null)
                    {
                        // No longer display pop-up after selection, it can manually be opened from menu options.
                        EditorPrefs.SetBool(AvatarPresetSelector.UniquePresetPopupKey, true);
                        _instance.Close();
                    }
                    EditorApplication.quitting -= Quit;
                }
            }
        }
    }

    public class AvatarPresetSelectorPopupDialog : EditorWindow
    {
        private static AvatarPresetSelectorPopupDialog? _instance;

        private static bool[] qualitySelection = new bool[PresetHelper.numPresetQualityTypes];

        private static bool[] avatarSelection = new bool[PresetHelper.numPresets];

        private static bool style2AvatarSelection = true;
        private Vector2 _scrollPos;

        public static void ShowWindow()
        {
            if (_instance)
            {
                return;
            }
            // All presets are selected by default
            if (System.IO.File.Exists(PresetHelper.presetSelectionAssetPath))
            {
                PresetSelectionInfo presetSelection = AssetDatabase.LoadAssetAtPath<PresetSelectionInfo>(PresetHelper.presetSelectionAssetPath);
                if (presetSelection != null)
                {
                    qualitySelection = presetSelection.qualitySelection!;
                    avatarSelection = presetSelection.avatarSelection!;
                }
            }
            else
            {
                Array.Fill(qualitySelection, true);
                Array.Fill(avatarSelection, true);
            }

            EditorApplication.quitting += Quit;
            float width = 500;
            float height = 500;
            float x = (EditorGUIUtility.GetMainWindowPosition().center.x - width / 2.0f);
            float y = 100;
            var window = GetWindow(typeof(AvatarPresetSelectorPopupDialog), true, "[Optional] Select Meta Avatars SDK Sample Assets", true);
            window.position = new Rect(x, y, width, height);

            // Only display the pop-up dialog the first time Unity is opened. After, it can manually be opened from menu options.
            EditorPrefs.SetBool(AvatarPresetSelector.UniquePresetPopupKey, true);
        }

        private void OnEnable()
        {
            _instance = this;
        }

        static void Quit()
        {
            if (_instance != null)
            {
                _instance.Close();
            }
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField(
                "Select which Meta Avatars SDK Sample Assets to include in your app\n\n" +
                "These assets include preset avatars used in the Meta Avatars SDK examples. " +
                "These presets are most comonly used to provide an avatar to someone that might not have an avatar asociated with their account " +
                "or as avatar representations for NPCs in your app.\n\n" +
                "Note: Importing these assets will increase the size of your final app.",
                EditorStyles.wordWrappedLabel);
            GUILayout.Space(10);

            GUIStyle titleStyle = new GUIStyle();
            titleStyle.fontStyle = FontStyle.Bold;
            titleStyle.fontSize = 14;
            titleStyle.normal.textColor = Color.white;

            EditorGUILayout.LabelField("Presets:", titleStyle);
            EditorGUI.indentLevel++;
            {
                EditorGUILayout.BeginHorizontal();
                EditorGUILayout.LabelField("Quality Options:");
                {
                    if (GUILayout.Button("Select All"))
                    {
                        Array.Fill(qualitySelection, true);
                    }
                    GUILayout.Space(10);
                    if (GUILayout.Button("Deselect All"))
                    {
                        Array.Fill(qualitySelection, false);
                    }
                }
                EditorGUILayout.EndHorizontal();

                EditorGUI.indentLevel++;
                {
                    for (int i = 0; i < qualitySelection.Length; i++)
                    {
                        PresetHelper.PresetQualityType preset = (PresetHelper.PresetQualityType)Enum.ToObject(typeof(PresetHelper.PresetQualityType), i);
                        string presetName = Enum.GetName(typeof(PresetHelper.PresetQualityType), preset);
                        qualitySelection[i] = EditorGUILayout.Toggle(presetName, qualitySelection[i]);
                    }
                }
                EditorGUI.indentLevel--;

                GUILayout.Space(20);
                EditorGUILayout.BeginHorizontal();
                EditorGUILayout.LabelField("Avatar Options:");
                {
                    if (GUILayout.Button("Select All"))
                    {
                        Array.Fill(avatarSelection, true);
                    }
                    GUILayout.Space(10);
                    if (GUILayout.Button("Deselect All"))
                    {
                        Array.Fill(avatarSelection, false);
                    }
                }
                EditorGUILayout.EndHorizontal();

                _scrollPos = EditorGUILayout.BeginScrollView(_scrollPos);
                EditorGUI.indentLevel++;
                for (int i = 0; i < PresetHelper.numPresets; i++)
                {
                    EditorGUILayout.BeginHorizontal();
                    avatarSelection[i] = EditorGUILayout.Toggle(i.ToString(), avatarSelection[i]);

                    if (++i < PresetHelper.numPresets)
                    {
                        GUILayout.FlexibleSpace();
                        avatarSelection[i] = EditorGUILayout.Toggle(i.ToString(), avatarSelection[i]);
                    }

                    EditorGUILayout.EndHorizontal();
                }
                EditorGUI.indentLevel--;
                EditorGUILayout.EndScrollView();

                GUILayout.Space(20);
            }
            EditorGUI.indentLevel--;

            using (new GUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Confirm"))
                {
                    if (_instance != null)
                    {
                        _instance.Close();
                    }
                    AvatarPresetSelector.RepackageWithPresetSelections(qualitySelection, avatarSelection);
                    EditorApplication.quitting -= Quit;
                }
            }

            if (!AllPresetSelected() || !style2AvatarSelection)
            {
                EditorGUILayout.BeginVertical();
                GUIStyle warningStyle = new GUIStyle(EditorStyles.boldLabel)
                {
                    normal =
                    {
                        textColor = Color.yellow
                    },
                    wordWrap = true
                };
                EditorGUILayout.LabelField("WARNING: Some avatar presets are not selected. Some sample scenes may not function correctly.", warningStyle);
                EditorGUILayout.EndVertical();
            }
            else
            {
                EditorGUILayout.LabelField("All avatars selected, sample scenes will function as expected.");
            }

            GUILayout.Space(20);
        }

        private bool AllPresetSelected()
        {
            return !(Array.IndexOf(avatarSelection, false) >= 0);
        }
    }
}
