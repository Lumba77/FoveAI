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

#if USING_XR_MANAGEMENT && (USING_XR_SDK_OCULUS || USING_XR_SDK_OPENXR) && !OVRPLUGIN_UNSUPPORTED_PLATFORM
#define USING_XR_SDK
#endif

using System.IO;
using UnityEditor;
using UnityEngine;

namespace Oculus.Avatar2
{
    /// <summary>
    /// This editor script adds a preprocess build step that copies the Avatars SDK Core Asset binaries into streaming assets
    /// that are required on the current target platform to the project's StreamingAssets folder
    /// Run this manually from the AvatarSDK2 > Streaming Assets menu.
    /// </summary>
    public class CoreAssetsMover
    {
        private static char s = Path.DirectorySeparatorChar;

        private static readonly string AvatarAssetsPackage = $"Oculus{s}OvrAvatar2Assets.avpkg";

        private static readonly string CoreAssetsSourceCheckSumKey = "OvrAvatar2AssetsAvpkgChecksum";

        private static readonly string CoreAssetsDestCheckSumKey = "OvrAvatar2AssetsZipChecksum";

        public static string GetStreamingAssetsZipPath()
        {
            return GetDestinationPath(AvatarAssetsPackage);
        }

        public static bool DoesAssetsZipNeedResync()
        {
            var sourcePath = GetSourcePath(AvatarAssetsPackage);
            var destinationPath = GetDestinationPath(AvatarAssetsPackage);

            return StreamingAssetsHelper.HasFileUpdated(sourcePath, CoreAssetsSourceCheckSumKey) || StreamingAssetsHelper.HasFileUpdated(destinationPath, CoreAssetsDestCheckSumKey);
        }

        public static bool DoesAssetsZipExist()
        {
            var destinationPath = GetDestinationPath(AvatarAssetsPackage);
            if (!File.Exists(destinationPath))
            {
                Debug.LogError("Could not find the Avatar2 assets at " + destinationPath);
            }
            return File.Exists(destinationPath);
        }

        public static bool DoesAssetsAvpkgExist()
        {
            var sourcePath = GetSourcePath(AvatarAssetsPackage);
            if (!File.Exists(sourcePath))
            {
                Debug.LogError("Could not find the Avatar2 assets at " + sourcePath);
            }
            return File.Exists(sourcePath);
        }

        // Needs to be public to allow automation to access it.
        [MenuItem("MetaAvatarsSDK/Assets/Core Assets/Copy Assets")]
        public static void CopyAssets()
        {
            OvrAvatarLog.LogInfo("Copying core Avatar2 assets to StreamingAssets",
                nameof(CoreAssetsMover));

            CopyFile(AvatarAssetsPackage);
            AssetDatabase.Refresh();
        }

        private static void CopyFile(string path)
        {
            var source = GetSourcePath(path);
            var destination = GetDestinationPath(path);
            StreamingAssetsHelper.SynchronizeFolders(source, destination, CoreAssetsSourceCheckSumKey, CoreAssetsDestCheckSumKey);
        }

        private static string GetSourcePath(string file)
        {
            return Path.Combine(AssetsPathFinderHelper.GetCoreAssetsPath(), file);
        }

        private static string GetDestinationPath(string file)
        {
            return Path.Combine(Application.streamingAssetsPath, Path.ChangeExtension(file, "zip"));
        }

        [InitializeOnLoad]
        private static class UpgradeCheck
        {
            static UpgradeCheck()
            {
                EditorApplication.update += RunOnce;
            }

            private static void RunOnce()
            {
                EditorApplication.update -= RunOnce;
                if (DoesAssetsZipNeedResync())
                {
                    CopyAssets();
                }
            }
        }
    }
}
