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

#nullable disable

// If logs enabled, always enable special case handling for now
#define OVRAVATAR_HANDLE_SPECIAL_CASE

// Assert throw is only active when every mechanism for asserts is enabled
// By default, all of these conditions fail
#if OVRAVATAR_ASSERT_ENABLE_CONDITIONAL && OVRAVATAR_ASSERT_FORCE_ENABLE && UNITY_ASSERTIONS
#define OVRAVATAR_ASSERT_THROW
#endif

using System;
using System.Collections.Generic;

using Oculus.Avatar2.Experimental;

using Unity.Profiling;
using Unity.Profiling.LowLevel;

using UnityEngine;

using CAPIStringEncoding = System.Text.UTF8Encoding;

using Conditional = System.Diagnostics.ConditionalAttribute;

namespace Oculus.Avatar2
{
    public static class OvrAvatarLog
    {
        public enum ELogLevel : sbyte
        {
            [HideInInspector]
            Silent = -1,

            Verbose = 0,
            Debug = 1,
            Info = 2,
            Warn = 3,
            Error = 4
        }

        public static ELogLevel logLevel = default;

        // If LogFilterDelegate returns `false`, log will be discarded
        public delegate bool LogFilterDelegate(ELogLevel level);
        public delegate void LogDelegate(ELogLevel level, string scope, string msg);

        public static event LogFilterDelegate CustomFilter = null;
        public static event LogDelegate CustomLogger = null;

        public delegate void UILogListenerDelegate(ELogLevel level, string msg, string prefix);
        public static event UILogListenerDelegate UILogListener = null;


        public const bool enabled =
#if !OVRAVATAR_LOG_ENABLE_CONDITIONAL || OVRAVATAR_LOG_FORCE_ENABLE
            true;
#else
            false;
#endif

        // When Logging Conditional is enabled, logs will default to off
        // - this enables them when conditionals are active
        public const string OVRAVATAR_LOG_FORCE_ENABLE = "OVRAVATAR_LOG_FORCE_ENABLE";
        // Analagous to `OVRAVATAR_LOG_FORCE_ENABLE` but for verbose logs
        public const string OVRAVATAR_LOG_VERBOSE_FORCE_ENABLE = "OVRAVATAR_LOG_VERBOSE_FORCE_ENABLE";
        // Analagous to `OVRAVATAR_LOG_FORCE_ENABLE` but for asserts
        public const string OVRAVATAR_ASSERT_FORCE_ENABLE = "OVRAVATAR_ASSERT_FORCE_ENABLE";

        internal static ELogLevel GetLogLevel(CAPI.ovrAvatar2LogLevel priority)
        {
            switch (priority)
            {
                case CAPI.ovrAvatar2LogLevel.Unknown:
                    return ELogLevel.Info;
                case CAPI.ovrAvatar2LogLevel.Default:
                    return ELogLevel.Info;
                case CAPI.ovrAvatar2LogLevel.Verbose:
                    return ELogLevel.Verbose;
                case CAPI.ovrAvatar2LogLevel.Debug:
                    return ELogLevel.Debug;
                case CAPI.ovrAvatar2LogLevel.Info:
                    return ELogLevel.Info;
                case CAPI.ovrAvatar2LogLevel.Warn:
                    return ELogLevel.Warn;
                case CAPI.ovrAvatar2LogLevel.Failure:
                    return ELogLevel.Error;
                case CAPI.ovrAvatar2LogLevel.Error:
                    return ELogLevel.Error;
                case CAPI.ovrAvatar2LogLevel.Fatal:
                    return ELogLevel.Error;
                case CAPI.ovrAvatar2LogLevel.Silent:
                    return ELogLevel.Silent;
                default:
                    throw new ArgumentOutOfRangeException(nameof(priority), priority, null);
            }
        }

        internal static LogType GetLogType(ELogLevel level)
        {
            switch (level)
            {
                case ELogLevel.Verbose: return LogType.Log;
                case ELogLevel.Debug: return LogType.Log;
                case ELogLevel.Info: return LogType.Log;
                case ELogLevel.Warn: return LogType.Warning;
                case ELogLevel.Error: return LogType.Error;
                default: return LogType.Exception;
            }
        }


        // TODO: Unify conversion encoder management once D45777434 lands
        private static CAPIStringEncoding _utf8EncoderCache = null;

        private static CAPIStringEncoding _CAPIEncoder => _utf8EncoderCache ??= new System.Text.UTF8Encoding(false, false);

        private static ProfilerMarker? logCallbackMarker_ = default;
        private static ProfilerMarker LogCallbackMarker => logCallbackMarker_
            ??= new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.NativeCallback, "OvrAvatarLog::LogCallBack", MarkerFlags.ScriptInvoke);

        [AOT.MonoPInvokeCallback(typeof(CAPI.LoggingViewDelegate))]
        internal static unsafe void LogCallBack(
            CAPI.ovrAvatar2LogLevel priority, Experimental.CAPI.ovrAvatar2StringView msgView, void* context)
        {
            Debug.Assert(priority != CAPI.ovrAvatar2LogLevel.Silent); // Silent logs shouldn't invoke this callback at all
            using var callbackScope = LogCallbackMarker.Auto();

            var level = GetLogLevel(priority);
            if (CustomFilter != null && !CustomFilter(level))
            {
                return;
            }
            if (CustomLogger == null)
            {
                if (level < logLevel) { return; }

                var unityLogger = Debug.unityLogger;
                if (!unityLogger.logEnabled) { return; }

                var logType = GetLogType(level);
                if (!unityLogger.IsLogTypeAllowed(logType)) { return; }
            }

            string msg = msgView.ToString();

            bool specialCase = false;
            HandleSpecialCaseLogs(msg, ref specialCase);
            if (!specialCase)
            {
                Log(level, msg, "native", OvrAvatarManager.Instance, false);
            }
        }

        private static Dictionary<string, string> _scopeStringCache = null;
        internal static string GetScopePrefix(string scope)
        {
            var scopeString = "[ovrAvatar2]";
            if (!String.IsNullOrEmpty(scope))
            {
                _scopeStringCache ??= new Dictionary<string, string>();
                if (!_scopeStringCache.TryGetValue(scope, out scopeString))
                {
                    scopeString = $"[ovrAvatar2 {scope}]";
                    _scopeStringCache.Add(scope, scopeString);
                }
            }
            return scopeString;
        }


        private static ProfilerMarker? logMarker_ = default;
        private static ProfilerMarker LogMarker => logMarker_
            ??= new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.AppCallback, "OvrAvatarLog::Log", MarkerFlags.ScriptInvoke);

        private static ProfilerMarker? customLoggerMarker_ = default;
        private static ProfilerMarker CustomLoggerMarker => customLoggerMarker_
            ??= new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.AppCallback, "AppCustomLogger", MarkerFlags.Script);

#if OVRAVATAR_LOG_ENABLE_CONDITIONAL
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#endif
        public static void Log(
            ELogLevel level, string msg, string scope = StringHelpers.EmptyString,
            UnityEngine.Object context = null, bool checkCustomFilter = true)
        {
            Debug.Assert(level > ELogLevel.Silent, "Attempted to log with level `Silent`");

            if (CustomLogger != null)
            {
                using var customLoggerScope = CustomLoggerMarker.Auto();

                if (!checkCustomFilter || CustomFilter == null || CustomFilter(level))
                {
                    CustomLogger(level, scope, msg);
                }
            }
            else if (level >= logLevel)
            {
                using var logMarker = LogMarker.Auto();

                string prefix = GetScopePrefix(scope);
                if (level >= ELogLevel.Error)
                {
                    Debug.LogError($"{prefix} {msg}", context);
                }
                else if (level >= ELogLevel.Warn)
                {
                    Debug.LogWarning($"{prefix} {msg}", context);
                }
                else if (level >= ELogLevel.Info)
                {
                    Debug.Log($"{prefix} {msg}", context);
                }
                else if (level >= ELogLevel.Debug)
                {
                    Debug.Log($"{prefix}[Debug] {msg}", context);
                }
                else if (level > ELogLevel.Silent)
                {
                    Debug.Log($"{prefix}[Verbose] {msg}", context);
                }
                UILogListener?.Invoke(level, msg, prefix);
            }
        }

        // Unless forced on, `Verbose` logs by default are only printed in `UNITY_EDITOR` builds
        // Unfortunately `DEVELOPER_BUILD` is required for profiling, where typically we want logs off
        // To enable `Verbose` logs in packaged builds, use `OVRAVATAR_LOG_ENABLE_CONDITIONAL` + `OVRAVATAR_LOG_FORCE_ENABLE`
        // via Menu `"MetaAvatarsSDK/Debug/Enable Verbose Logs"`
#if OVRAVATAR_LOG_ENABLE_CONDITIONAL && !OVRAVATAR_LOG_FORCE_ENABLE
// if LOG conditional is enabled, it can also disable Verbose
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#elif OVRAVATAR_LOG_VERBOSE_ENABLE_CONDITIONAL || !UNITY_EDITOR
        // if VERBOSE conditional OR outside of editor, verbose must be forced on (off by default)
        [Conditional(OVRAVATAR_LOG_VERBOSE_FORCE_ENABLE)]
#endif // OVRAVATAR_LOG_ENABLE_CONDITIONAL
        public static void LogVerbose(string msg, string scope = "", UnityEngine.Object context = null)
        {
            Log(ELogLevel.Verbose, msg, scope, context);
        }

#if OVRAVATAR_LOG_ENABLE_CONDITIONAL
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#endif
        public static void LogDebug(string msg, string scope = "", UnityEngine.Object context = null)
        {
            Log(ELogLevel.Debug, msg, scope, context);
        }

#if OVRAVATAR_LOG_ENABLE_CONDITIONAL
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#endif
        public static void LogInfo(string msg, string scope = "", UnityEngine.Object context = null)
        {
            Log(ELogLevel.Info, msg, scope, context);
        }

#if OVRAVATAR_LOG_ENABLE_CONDITIONAL
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#endif
        public static void LogWarning(string msg, string scope = "", UnityEngine.Object context = null)
        {
            Log(ELogLevel.Warn, msg, scope, context);
        }

#if OVRAVATAR_LOG_ENABLE_CONDITIONAL
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#endif
        public static void LogError(string msg, string scope = "", UnityEngine.Object context = null)
        {
            Log(ELogLevel.Error, msg, scope, context);
        }

#if OVRAVATAR_LOG_ENABLE_CONDITIONAL
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#endif
        public static void LogException(string operationName, Exception exception, string scope = "", UnityEngine.Object context = null)
        {
            LogError(
                $"Exception during operation ({operationName}) - exception:({exception})\n Trace: ({exception.StackTrace})",
                scope, context);
        }

        public const string DEFAULT_ASSERT_MESSAGE = "condition false";
        public const string DEFAULT_ASSERT_SCOPE = "OvrAssert";
#if OVRAVATAR_LOG_ENABLE_CONDITIONAL
        [Conditional(OVRAVATAR_LOG_FORCE_ENABLE)]
#endif
        public static void LogAssert(string message = DEFAULT_ASSERT_MESSAGE, string scope = DEFAULT_ASSERT_SCOPE, UnityEngine.Object context = null)
        {
            LogError($"Assertion failed: {message ?? DEFAULT_ASSERT_MESSAGE} - trace {Environment.StackTrace}", scope ?? DEFAULT_ASSERT_SCOPE, context);
            Debug.Assert(false, $"ASSERT FAILED - [ovrAvatar2 {scope}] - {message}", context);

            // Do not enable OVRAVATAR_ASSERT_THROW unless you want failure (ie: testing)
            // - This will lead to catastrophic failure in many places in some applications
            // -- In theory, those are the real logical failures.
#if OVRAVATAR_ASSERT_THROW
            throw new InvalidOperationException(message);
#endif
        }

        public static void LogAllocationFailure(string operationName, string scope, UnityEngine.Object context = null)
        {
            // TODO: Keep a preallocated buffer for stringBuilding here?
            // For now, at least running OOM in a method named `LogAllocationFailure` should be more obvious than before
            GC.Collect();
            LogError($"Allocation failure detected during {operationName}", scope, context);
        }

#if OVRAVATAR_ASSERT_ENABLE_CONDITIONAL || !UNITY_ASSERTIONS
        [Conditional(OVRAVATAR_ASSERT_FORCE_ENABLE)]
#endif
        internal static void Assert(bool condition, string scope = DEFAULT_ASSERT_SCOPE, UnityEngine.Object context = null)
        {
            AssertConstMessage(condition, "condition false", scope, context);
        }

#if OVRAVATAR_ASSERT_ENABLE_CONDITIONAL || !UNITY_ASSERTIONS
        [Conditional(OVRAVATAR_ASSERT_FORCE_ENABLE)]
#endif
        internal static void AssertConstMessage(bool condition, string message = null, string scope = DEFAULT_ASSERT_SCOPE, UnityEngine.Object context = null)
        {
            if (!condition)
            {
                LogAssert(message, scope, context);
            }
        }

        public delegate string AssertStaticMessageBuilder();
#if OVRAVATAR_ASSERT_ENABLE_CONDITIONAL || !UNITY_ASSERTIONS
        [Conditional(OVRAVATAR_ASSERT_FORCE_ENABLE)]
#endif
        internal static void AssertStaticBuilder(bool condition, AssertStaticMessageBuilder builder, string scope = DEFAULT_ASSERT_SCOPE, UnityEngine.Object context = null)
        {
            if (!condition)
            {
                LogAssert(builder(), scope, context);
            }
        }

        public delegate string AssertMessageBuilder<T>(in T param);
#if OVRAVATAR_ASSERT_ENABLE_CONDITIONAL || !UNITY_ASSERTIONS
        [Conditional(OVRAVATAR_ASSERT_FORCE_ENABLE)]
#endif
        internal static void AssertParam<T>(bool condition, in T buildParams, AssertMessageBuilder<T> builder
            , string scope = DEFAULT_ASSERT_SCOPE, UnityEngine.Object context = null)
        {
            // Should be a static method, otherwise wrap in conditional to avoid alloc
            Debug.Assert(builder.Target == null, "Instanced builder passed to AssertParam");
            if (!condition)
            {
                LogAssert(builder(in buildParams), scope, context);
            }
        }

        public delegate string AssertMessageBuilder<T0, T1>(in T0 param0, in T1 param1);
#if OVRAVATAR_ASSERT_ENABLE_CONDITIONAL || !UNITY_ASSERTIONS
        [Conditional(OVRAVATAR_ASSERT_FORCE_ENABLE)]
#endif
        internal static void AssertTwoParams<T0, T1>(bool condition, in T0 buildParam0, in T1 buildParam1, AssertMessageBuilder<T0, T1> builder
            , string scope = DEFAULT_ASSERT_SCOPE, UnityEngine.Object context = null)
        {
            // Should be a static method, otherwise wrap in conditional to avoid alloc
            Debug.Assert(builder.Target == null, "Instanced builder passed to AssertTwoParams");
            if (!condition)
            {
                LogAssert(builder(in buildParam0, in buildParam1), scope, context);
            }
        }

        public delegate string AssertLessThanMessageBuilder<T>(in T lhs, in T rhs);
#if OVRAVATAR_ASSERT_ENABLE_CONDITIONAL || !UNITY_ASSERTIONS
        [Conditional(OVRAVATAR_ASSERT_FORCE_ENABLE)]
#endif
        internal static void AssertLessThan(int lesser, int greater, AssertLessThanMessageBuilder<int> builder
            , string scope = DEFAULT_ASSERT_SCOPE, UnityEngine.Object context = null)
        {
            // Should be a static method, otherwise wrap in conditional to avoid alloc
            Debug.Assert(builder.Target == null);
            if (lesser >= greater)
            {
                LogAssert(builder(in lesser, in greater), scope, context);
            }
        }

        // HACK: TODO: Remove everything below here before release
        // Down-ranking specific native logs that often spam

        private const string _bodyApiMsg =
            "failed 'ovrBody_GetPose(context_, pose)' with 'An unknown error has occurred'(65537)";

        private const string gltfAttributeMsg =
            "gltfmeshprimitiveitem::Skipping vertex attribute in glTF mesh primitive:";

        private const string _ovrPluginInitMsg =
            "tracking::OVRPlugin not initialized";

        private const string _renderMsg =
            "Render::Could not find node LOD00_combined_1stPerson_geometry to re-root";


        [Conditional("OVRAVATAR_HANDLE_SPECIAL_CASE")]
        private static void HandleSpecialCaseLogs(string message, ref bool handled)
        {
            const StringComparison comparisonType = StringComparison.OrdinalIgnoreCase;

            handled = false;

            if (message.Contains(gltfAttributeMsg, comparisonType)
                || message.Contains(_ovrPluginInitMsg, comparisonType)
                || message.Contains(_renderMsg, comparisonType))
            {
                LogVerbose(message, "native");
                handled = true;
            }
            else if (message.Contains(_bodyApiMsg, comparisonType))
            {
                LogVerbose(
                    "tracking::Tracking failed 'ovrBody_GetPose(context_, pose)' with a bad input pose. Reusing pose from last frame",
                    "native");
                handled = true;
            }
        }
    }
}
