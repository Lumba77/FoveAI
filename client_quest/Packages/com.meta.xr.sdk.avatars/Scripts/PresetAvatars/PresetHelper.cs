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
using System.IO;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

using Oculus.Avatar2.Experimental;

namespace Oculus.Avatar2
{
    public static class PresetHelper
    {
        // TODO: T201305191
        public enum PresetQualityType
        {
            Standard = 0,
            Light = 1,
        };

        // TODO: T201305191
        private enum PresetType
        {
            Quest = 0,
            Quest_Light = 1,
            Rift = 2,
            Rift_Light = 3
        }

        public static int numPresets = 33;

        public static int numPresetQualityTypes = Enum.GetNames(typeof(PresetQualityType)).Length;

        public const string unpackagedPresetPrefix = "PresetAvatars";

        public const string unpackagedPresetDirRegex = unpackagedPresetPrefix + "*";

        public const string presetExtension = ".glb";

        public static readonly string sampleAssetsPath = AssetsPathFinderHelper.GetSampleAssetsAssetsPath();

        public static readonly string presetSelectionAssetName = "PresetSelectionAsset.asset";

        public static readonly string presetSelectionAssetPath = Path.Combine("Assets", "Resources", presetSelectionAssetName);

        public static readonly string presetUnpackagedDirectory = Path.Combine(sampleAssetsPath, "SampleAssetsUnzipped");

        public static readonly string presetPackagedDirectory = Path.Combine(sampleAssetsPath, "SampleAssets");

        public static bool PresetDirectoryExists()
        {
            return Directory.Exists(presetUnpackagedDirectory);
        }

        public static void UpdatePresetsCount()
        {
            string[] presetDirectoryPaths = Directory.GetDirectories(presetUnpackagedDirectory, $"{unpackagedPresetDirRegex}");

            // Heristically assume number of presets is the same across all directories
            if (presetDirectoryPaths.Length > 0)
            {
                string[] presetFilePaths = Directory.GetFiles(presetDirectoryPaths[0], $"*{presetExtension}");
                if (presetFilePaths.Length != numPresets)
                {
                    Debug.Log($"Updating preset count, found {presetFilePaths.Length} presets");
                }
                numPresets = presetFilePaths.Length;
            }
        }

        public static List<string> GetSelectedGlbs(bool[] qualitySelection, bool[] avatarSelection)
        {
            List<string> selectedGlbs = new List<string>();
            List<PresetType> presetTypeSelection = GetPresetTypes(qualitySelection);
            foreach (PresetType presetType in presetTypeSelection)
            {
                for (int i = 0; i < avatarSelection.Length; i++)
                {
                    if (avatarSelection[i])
                    {
                        selectedGlbs.Add(GetPresetFileName(presetType, i));
                    }
                }
            }
            return selectedGlbs;
        }

        public static bool CheckIfPresetsPackaged()
        {
            if (Directory.Exists(presetPackagedDirectory))
            {
                var files = Directory.GetFiles(presetPackagedDirectory);
                if (files.Length > 0)
                {
                    return true;
                }
            }
            return false;
        }

#if UNITY_EDITOR
        [MenuItem("MetaAvatarsSDK/Assets/Sample Assets/Package Presets")]
        public static void PackagePresetsDefaultSelection()
        {
            PresetPackager.PackagePresetsInDirectory(PresetPackager.DefaultSourceDestPaths, true, true, new[] { ".meta" });
        }
#endif //!UNITY_EDITOR

        private static List<PresetType> GetPresetTypes(bool[] qualitySelection)
        {
            List<PresetType> presetTypes = new List<PresetType>();
            foreach (PresetQualityType type in Enum.GetValues(typeof(PresetQualityType)))
            {
                if (qualitySelection[(int)type])
                {
                    // TODO: T201305191
                    switch (type)
                    {
                        case PresetQualityType.Standard:
                            presetTypes.Add(PresetType.Quest);
                            presetTypes.Add(PresetType.Rift);
                            break;
                        case PresetQualityType.Light:
                            presetTypes.Add(PresetType.Quest_Light);
                            presetTypes.Add(PresetType.Rift_Light);
                            break;
                    }
                }
            }
            return presetTypes;
        }

        private static string GetPresetFileName(PresetType zipType, int avatarIndex)
        {
            return $"{avatarIndex}_{zipType.ToString().ToLower()}{presetExtension}";
        }
    }
}
