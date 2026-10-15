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

#if UNITY_IOS

using System.IO;
using UnityEditor;
using UnityEditor.iOS.Xcode;
using UnityEditor.Callbacks;

namespace Oculus.Avatar2
{
    public class AvatarSDK_iOS_PostProcess
    {


        private static readonly string[] xcFrameworksPaths =
        {
            "Oculus/Avatar2/Plugins/iOS/",
            "Internal/Plugins/iOS/"
        };

        private const string BuildPhaseName = "iOS Post Process";

        [PostProcessBuild]
        public static void OnPostprocessBuild(BuildTarget buildTarget, string pathToBuiltProject)
        {
            var projectPath = PBXProject.GetPBXProjectPath(pathToBuiltProject);
            var project = new PBXProject();
            project.ReadFromString(File.ReadAllText(projectPath));

            // Disable bitcode for Unity Framework
            var frameworkTarget = project.GetUnityFrameworkTargetGuid();
            project.SetBuildProperty(frameworkTarget, "ENABLE_BITCODE", "NO");

            var projectSettings = project.WriteToString();
            File.WriteAllText(projectPath, projectSettings);



            XcodeXCFrameworkHelper.AddXCFrameworksToXcodeProject(pathToBuiltProject, xcFrameworksPaths, BuildPhaseName);
        }
    }
}

#endif
