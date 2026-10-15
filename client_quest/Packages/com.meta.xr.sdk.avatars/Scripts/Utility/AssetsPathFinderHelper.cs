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

using System.IO;
using UnityEngine;

namespace Oculus.Avatar2
{
    public static class AssetsPathFinderHelper
    {
        public static readonly string coreAssetsPackageName = "com.meta.xr.sdk.avatars";
        public static readonly string sampleAssetsPackageName = "com.meta.xr.sdk.avatars.sample.assets";
        private static readonly string logScope = "assetfinder";

        public static string GetCoreAssetsPackagePath()
        {
            return Path.Combine("Packages", coreAssetsPackageName, "CoreAssets");
        }

        public static string GetCoreAssetsAssetsPath()
        {
            return Path.Combine(Application.dataPath, "Oculus", "Avatar2", "CoreAssets");
        }

        public static string GetCoreAssetsPath()
        {
            // This works if we have core unity integration package project as a dependency.
            string path = Directory.Exists(GetCoreAssetsPackagePath()) ? GetCoreAssetsPackagePath() : GetCoreAssetsAssetsPath();

            if (!Directory.Exists(path))
            {
                // This should never happen, as this class exists in the same package as the core assets.
                OvrAvatarLog.LogError($"Avatar core assets path was requested but the path doesn't exist", logScope);
            }

            return Path.GetFullPath(path);
        }

        public static string GetSampleAssetsPackagePath()
        {
            return Path.Combine("Packages", sampleAssetsPackageName, "SampleAssets");
        }

        public static string GetSampleAssetsAssetsPath()
        {
            return Path.Combine(Application.dataPath, "Oculus", "Avatar2_SampleAssets", "SampleAssets");
        }

        public static string GetSampleAssetsPath()
        {
            // This works if we have sample assets package as a dependency.
            string path = Directory.Exists(GetSampleAssetsPackagePath()) ? GetSampleAssetsPackagePath() : GetSampleAssetsAssetsPath();
            if (!Directory.Exists(path))

            {
                // This can happen because this class exists in a separate package from SampleAssets.
                OvrAvatarLog.LogWarning($"Avatar sample assets path was requested but the path doesn't exist. This likely means that you're missing the {sampleAssetsPackageName} package. " +
                    "You can install it via AvatarSDK > Assets > Sample Assets > Import Sample Assets Package " +
                    "or by searching for it and importing it from package manager under Window > Package Manager", logScope);
            }

            return Path.GetFullPath(path);
        }
    }
}
