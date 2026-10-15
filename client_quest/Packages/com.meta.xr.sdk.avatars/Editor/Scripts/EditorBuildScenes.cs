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

using System.Collections.Generic;
using UnityEditor;

namespace Oculus.Avatar2
{
    /*
     * static helper function to get the currently enabled scenes in the build
     *
     * If OverrideScenes is set (ex. for a command line build, we use that instead of the Unity enabled scenes.
     *
     * Used by EditorBuildTools.cs
     */
    public static class EditorBuildScenes
    {
        public static List<string> OverrideScenes { get; } = new List<string>();

        public static string[] GetBuildScenes()
        {
            if (OverrideScenes.Count > 0)
            {
                return OverrideScenes.ToArray();
            }

            // Fall back to scenes from build settings
            var buildScenes = new List<string>();
            foreach (var scene in EditorBuildSettings.scenes)
            {
                if (scene.enabled)
                {
                    buildScenes.Add(scene.path);
                }
            }

            return buildScenes.ToArray();
        }
    }
}
