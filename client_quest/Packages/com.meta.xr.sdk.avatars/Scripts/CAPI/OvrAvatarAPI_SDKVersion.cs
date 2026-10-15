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

// Note: This file contains SDKVersionInfo that returns the version of the Avatar SDK that is currently being used.
// Actual version is defined in OvrAvatarAPI_SDKVersionInfo.cs. If the file doesn't exist, it will fall back to default version.

using System;
using System.Runtime.InteropServices;
using System.Reflection;

namespace Oculus.Avatar2
{
    public static partial class AvatarSDKVersion { }

    [StructLayout(LayoutKind.Sequential)]
    public struct FBVersionNumber
    {
        public UInt32 releaseVersion;
        public UInt32 hotfixVersion;
        public UInt32 experimentationVersion;
        public UInt32 betaVersion;
        public UInt32 alphaVersion;

        public override string ToString()
        {
            return $"{releaseVersion}.{hotfixVersion}.{experimentationVersion}.{betaVersion}.{alphaVersion}";
        }
    };

    public static class SDKVersionInfo
    {
        public const UInt32 AVATAR2_RELEASE_VERSION = 0;
        public const UInt32 AVATAR2_HOTFIX_VERSION = 0;
        public const UInt32 AVATAR2_EXPERIMENTATION_VERSION = 0;
        public const UInt32 AVATAR2_BETA_VERSION = 0;
        public const UInt32 AVATAR2_ALPHA_VERSION = 0;

        static public FBVersionNumber CurrentVersion()
        {
            MethodInfo method = typeof(AvatarSDKVersion).GetMethod("CurrentVersion", BindingFlags.Static | BindingFlags.Public);
            if (method != null)
            {
                object result = method.Invoke(null, null);
                if (result is FBVersionNumber versionNumber)
                {
                    OvrAvatarLog.LogInfo("Using version: " + versionNumber.ToString());
                    return versionNumber;
                }
            }

            FBVersionNumber defaultVersionNumber;
            defaultVersionNumber.releaseVersion = AVATAR2_RELEASE_VERSION;
            defaultVersionNumber.hotfixVersion = AVATAR2_HOTFIX_VERSION;
            defaultVersionNumber.experimentationVersion = AVATAR2_EXPERIMENTATION_VERSION;
            defaultVersionNumber.betaVersion = AVATAR2_BETA_VERSION;
            defaultVersionNumber.alphaVersion = AVATAR2_ALPHA_VERSION;

            OvrAvatarLog.LogInfo("Using default version: " + defaultVersionNumber.ToString());
            return defaultVersionNumber;
        }
    }
}
