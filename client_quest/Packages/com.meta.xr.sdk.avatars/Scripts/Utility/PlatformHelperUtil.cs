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
using UnityEngine;

namespace Oculus.Avatar2
{
    public static class PlatformHelperUtils
    {
        private const string DefaultScope = "ovrAvatar2.platformUtils";

        public static class AndroidSysProperties
        {
            public static readonly string ExperimentalFeatures = "persist.avatar.perf_test.expfeatures";
        }

        public static string GetAndroidSysProp(string propName, string logScope = DefaultScope)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                var sysprops = new AndroidJavaClass("android.os.SystemProperties");
                var val = sysprops.CallStatic<string>("get", propName);
                OvrAvatarLog.LogInfo($"System property {propName} = {val}", logScope);
                return val;
            }
            catch (System.Exception e)
            {
                OvrAvatarLog.LogError($"An exception occured while reading system property: {e}", logScope);
            }
#endif
            return string.Empty;
        }

        public static int GetAndroidIntSysProp(string propName, int defaultValue, string logScope = DefaultScope)
        {
            var value = defaultValue;
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                value = int.Parse(GetAndroidSysProp(propName, logScope));
            }
            catch (System.FormatException)
            {
                OvrAvatarLog.LogError($"Unable to parse {propName}", logScope);
            }
#endif
            return value;
        }

    }
}
