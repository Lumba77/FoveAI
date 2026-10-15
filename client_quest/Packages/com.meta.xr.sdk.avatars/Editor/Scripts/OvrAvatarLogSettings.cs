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

using UnityEditor;

namespace Oculus.Avatar2
{
    public static class OvrLogSettings
    {
        private const string OVRAVATAR_LOG_VERBOSE_ENABLE_CONDITIONAL = "OVRAVATAR_LOG_VERBOSE_ENABLE_CONDITIONAL";
        private const string OVRAVATAR_LOG_ENABLE_CONDITIONAL = "OVRAVATAR_LOG_ENABLE_CONDITIONAL";
        private const string OVRAVATAR_ASSERT_ENABLE_CONDITIONAL = "OVRAVATAR_ASSERT_ENABLE_CONDITIONAL";


        [MenuItem("MetaAvatarsSDK/Debug/Enable Verbose Logs (Packaged Builds)")]
        private static void EnableVerbose()
        {
            SetVerboseLogsEnabled(true);
        }
        [MenuItem("MetaAvatarsSDK/Debug/Enable Verbose Logs (Packaged Builds)", true)]
        private static bool CheckIfEnableVerboseIsValid()
        {
            return AreAnyLogsEnabled() && AreVerboseLogsDisabled();
        }

        [MenuItem("MetaAvatarsSDK/Debug/Disable Verbose Logs")]
        private static void DisableVerbose()
        {
            SetVerboseLogsEnabled(false);
        }
        [MenuItem("MetaAvatarsSDK/Debug/Disable Verbose Logs", true)]
        private static bool CheckIfDisableVerboseIsValid()
        {
            return AreAnyLogsEnabled() && AreVerboseLogsEnabled();
        }

        [MenuItem("MetaAvatarsSDK/Debug/Enable Logs")]
        private static void EnableLogs()
        {
            SetLogsEnabled(true);
        }
        [MenuItem("MetaAvatarsSDK/Debug/Enable Logs", true)]
        private static bool CheckIfEnableLogsIsValid()
        {
            return AreAnyLogsDisabled();
        }

        [MenuItem("MetaAvatarsSDK/Debug/Disable Logs")]
        private static void DisableLogs()
        {
            SetLogsEnabled(false);
        }
        [MenuItem("MetaAvatarsSDK/Debug/Disable Logs", true)]
        private static bool CheckIfDisableLogsIsValid()
        {
            return AreAnyLogsEnabled();
        }

        [MenuItem("MetaAvatarsSDK/Debug/Enable Asserts")]
        private static void EnableAsserts()
        {
            SetAssertsEnabled(true);
        }
        [MenuItem("MetaAvatarsSDK/Debug/Enable Asserts", true)]
        private static bool CheckIfEnableAssertsIsValid()
        {
            return AreAnyAssertsDisabled();
        }

        [MenuItem("MetaAvatarsSDK/Debug/Disable Asserts")]
        private static void DisableAsserts()
        {
            SetAssertsEnabled(false);
        }
        [MenuItem("MetaAvatarsSDK/Debug/Disable Asserts", true)]
        private static bool CheckIfDisableAssertsIsValid()
        {
            return AreAnyAssertsEnabled();
        }

        private static void SetVerboseLogsEnabled(bool enableLogs)
        {
            ConfigureDefines(OVRAVATAR_LOG_VERBOSE_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_LOG_VERBOSE_FORCE_ENABLE, enableLogs);
        }
        private static void SetLogsEnabled(bool enableLogs)
        {
            ConfigureDefines(OVRAVATAR_LOG_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_LOG_FORCE_ENABLE, enableLogs);
        }
        private static void SetAssertsEnabled(bool enableAsserts)
        {
            ConfigureDefines(OVRAVATAR_ASSERT_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_ASSERT_FORCE_ENABLE, enableAsserts);
        }

        private static void ConfigureDefines(string enableConditional, string forceEnableDefine, bool enableLogs)
        {
            var logChange = enableLogs ? "enabling" : "disabling";
            var conditionalDefineWithSemicolon = enableConditional + ';';
            var forceEnableDefineWithSemicolon = forceEnableDefine + ';';
            foreach (BuildTargetGroup target in Enum.GetValues(typeof(BuildTargetGroup)))
            {
                if (!IsAvatarTarget(target)) { continue; }

                bool definesDidChange = false;

                var defines = PlayerSettings.GetScriptingDefineSymbolsForGroup(target);
                if (!defines.Contains(enableConditional))
                {
                    UnityEngine.Debug.LogWarning($"Enabling conditional logging for {Enum.GetName(typeof(BuildTargetGroup), target)}");

                    defines = conditionalDefineWithSemicolon + defines;
                    definesDidChange = true;
                }

                if (defines.Contains(forceEnableDefine) != enableLogs)
                {
                    UnityEngine.Debug.Log($"Updating log settings for {Enum.GetName(typeof(BuildTargetGroup), target)} - {logChange}");

                    if (enableLogs)
                    {
                        defines = forceEnableDefineWithSemicolon + defines;
                    }
                    else
                    {
                        defines = defines.Replace(forceEnableDefineWithSemicolon, string.Empty);
                        defines = defines.Replace(forceEnableDefine, string.Empty);
                    }
                    definesDidChange = true;
                }

                if (definesDidChange)
                {
                    PlayerSettings.SetScriptingDefineSymbolsForGroup(target, defines);
                }
            }
        }

        private static bool AreVerboseLogsEnabled()
            => AreSymbolsEnabled(OVRAVATAR_LOG_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_LOG_VERBOSE_FORCE_ENABLE);
        private static bool AreVerboseLogsDisabled()
            => AreSymbolsDisabled(OVRAVATAR_LOG_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_LOG_VERBOSE_FORCE_ENABLE);

        private static bool AreAnyLogsEnabled()
            => AreSymbolsEnabled(OVRAVATAR_LOG_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_LOG_FORCE_ENABLE);
        private static bool AreAnyLogsDisabled()
            => AreSymbolsDisabled(OVRAVATAR_LOG_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_LOG_FORCE_ENABLE);

        private static bool AreAnyAssertsEnabled()
            => AreSymbolsEnabled(OVRAVATAR_ASSERT_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_ASSERT_FORCE_ENABLE);
        private static bool AreAnyAssertsDisabled()
            => AreSymbolsDisabled(OVRAVATAR_ASSERT_ENABLE_CONDITIONAL, OvrAvatarLog.OVRAVATAR_ASSERT_FORCE_ENABLE);


        private static bool AreSymbolsEnabled(string enableConditional, string forceEnable)
            => !IsDefineSetOnAnyPlatform(enableConditional) || IsDefineSetOnAllPlatforms(forceEnable);

        private static bool AreSymbolsDisabled(string enableConditional, string forceEnable)
            => IsDefineSetOnAnyPlatform(enableConditional) && !IsDefineSetOnAllPlatforms(forceEnable);

        private static readonly BuildTargetGroup[] SupportedPlatforms =
        {
                BuildTargetGroup.Standalone,
                BuildTargetGroup.Android,
                BuildTargetGroup.iOS,
        };
        private static bool IsAvatarTarget(BuildTargetGroup target) => SupportedPlatforms.Contains(target);

        private static bool IsDefineSetOnAnyPlatform(string define) => IsDefineSet(define, true);
        private static bool IsDefineSetOnAllPlatforms(string define) => IsDefineSet(define, false);
        private static bool IsDefineSet(string define, bool matchAnyPlatform)
        {
            foreach (BuildTargetGroup target in Enum.GetValues(typeof(BuildTargetGroup)))
            {
                if (!IsAvatarTarget(target)) { continue; }

                var defines = PlayerSettings.GetScriptingDefineSymbolsForGroup(target);
                if (defines.Contains(define) == matchAnyPlatform)
                {
                    return matchAnyPlatform;
                }
            }
            return !matchAnyPlatform;
        }
    }
}
