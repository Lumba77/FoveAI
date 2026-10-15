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
    public static class TestHelpers
    {
        /* Determines whether the current execution is within an editor test runner
            BE EXTREMELY CAREFUL WITH THIS! IT IS HACKY!! DO NOT USE IT TO "FIX" YOUR TESTS!!!
            Reasonable use case could be - disabling spammy warning logs during test runs, or avoiding certain Unity APIs */
#if UNITY_EDITOR
        public static bool isRunningAnEditorTest
        {
            get
            {
                if (s_isTestRunnerCache == 0)
                {
                    // adapted from https://forum.unity.com/threads/preprocessor-define-set-when-running-in-testrunner.1348145/
                    s_isTestRunnerCache = Environment.StackTrace.Contains("UnityEngine.TestRunner") ? 1 : -1;
                }
                return s_isTestRunnerCache > 0;
            }
        }
        // ReSharper disable once RedundantDefaultMemberInitializer
        private static int s_isTestRunnerCache = 0;
#else // !UNITY_EDITOR
        public const bool isRunningAnEditorTest = false;
#endif
    }
}
