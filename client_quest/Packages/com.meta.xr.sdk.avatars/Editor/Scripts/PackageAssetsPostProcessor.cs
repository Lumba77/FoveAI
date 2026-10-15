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

using UnityEngine;
using UnityEditor;

using Oculus.Avatar2.Experimental;

namespace Oculus.Avatar2
{
#if UNITY_EDITOR
 [InitializeOnLoad]
    public class AvatarAssetsPackageCheckTrigger
    {
        static AvatarAssetsPackageCheckTrigger()
        {
            if (PresetHelper.CheckIfPresetsPackaged())
            {
                Debug.Log("Avatar Preset are already packaged.");
            }
            else
            {
                Debug.Log("Detected missing packaged presets, repackaging.");
                PresetHelper.PackagePresetsDefaultSelection();
            }

            CoreAssetsMover.CopyAssets();

            SessionState.SetBool("AvatarAssetsPackageCheckRanOnce", true);
        }
    }

    // Package Assets on Import
    public class PackageAssetsPostProcessor : AssetPostprocessor
    {
        private static bool PresetPathCheck(string filePath)
        {
            return (filePath.EndsWith(".glb") && filePath.Contains("SampleAssetsUnzipped"));
        }

        private static bool BehaviorAssetsPathCheck(string filePath)
        {
            return (filePath.EndsWith(".behavior") && filePath.Contains("BehaviorAssets"));
        }

        private static bool CoreAssetsZipPathCheck(string filePath)
        {
            return (filePath.EndsWith("OvrAvatar2Assets.zip") && filePath.Contains("CoreAssets/Oculus"));
        }

        private static void OnPostprocessAllAssets(string[] importedAssets, string[] deletedAssets, string[] movedAssets, string[] movedFromAssetPaths)
        {
            bool presetsPackaged = false;
            bool behaviorsPackaged = false;
            foreach (string assetPath in importedAssets)
            {
                if (BehaviorAssetsPathCheck(assetPath) && behaviorsPackaged == false) {
                    Debug.Log("Imported unpackaged behavior assets, packaging now.");
                    BehaviorPackager.PackageBehaviorsInDirectory(BehaviorPackager.DefaultSourceDestPaths, true, false, new[] { ".meta", ".editor" });
                    behaviorsPackaged = true;
                }
                else if (PresetPathCheck(assetPath) && presetsPackaged == false && PresetHelper.PresetDirectoryExists())
                {
                    PresetHelper.UpdatePresetsCount();
                    Debug.Log("Imported unpackaged Avatar presets, packaging now.");
                    PresetHelper.PackagePresetsDefaultSelection();
                    presetsPackaged = true;
                }
                else if (CoreAssetsZipPathCheck(assetPath))
                {
                    // We are no longer storing the Assets.zip in CoreAssets, it is instead stored as a .avpkg. Removing old Assets.zip.
                    StreamingAssetsHelper.DeleteFile(assetPath);
                }
            }

            // If the Streaming Assets zip file has been deleted, recopy and rename from CoreAssets
            if (CoreAssetsMover.DoesAssetsZipNeedResync())
            {
                Debug.Log("Detected changes to Core Assets binary, recopying...");
                CoreAssetsMover.CopyAssets();
            }
        }
    }

#endif //!UNITY_EDITOR
}
