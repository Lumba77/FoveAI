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
using System.IO;
using UnityEngine;

namespace Oculus.Avatar2.Experimental
{
    /// <summary>
    /// This class contains helper methods for locating unpackaged behaviors in a project,
    /// and generates packages for each one, if necessary. An unpackaged behavior is a
    /// collection of directories and files, with the name of its root directory ending in
    /// ".behavior". A packaged behavior is simply a zip archive of the unpackaged behavior.
    /// </summary>
    public class BehaviorPackager
    {
        private const string unpackagedBehaviorDirRegex = "*.behavior";
        private const string packagedBehaviorExtension = ".zip";

        // The default array of paths to search for unpackaged behaviors, and the
        // corresponding destination paths the packaged behaviors will be written out to.
        public static readonly Tuple<string, string>[] DefaultSourceDestPaths = {
             new Tuple<string, string>(
                 Path.Combine(AssetsPathFinderHelper.GetCoreAssetsPath(), "BehaviorAssets"), // Source path
                 Path.Combine(Application.streamingAssetsPath, "BehaviorAssets") // Dest path
                 ),
        };

        /// <summary>
        /// Searches through the specified directory for any unpackaged behaviors, and
        /// creates packages for each one. Packages are only created if no package exists,
        /// or if one or more files in the behavior has been modified more recently than
        /// the package. If a behavior is found in a subdirectory of the search directory,
        /// the resulting package will be created in a subdirectory of the output
        /// directory with the same relative path.
        /// </summary>
        /// <param name="sourceDestPaths">Array of Tuples, where the first item is the source
        /// path to search for unpackaged behaviors, and the second item is the destination
        /// path the packaged behaviors will be written out to</param>
        /// <param name="searchSubdirectories">When true, this method will seach all
        /// subdirectories for unpackaged behaviors</param>
        /// <param name="forceRepackage">When true, this method will ignore the timestamp
        /// of any existing packages, and will automatically repackage all behaviors</param>
        /// <param name="excludedFileExtensions">Do not package any files with these extensions</param>
        public static void PackageBehaviorsInDirectory(Tuple<string, string>[] sourceDestPaths, bool searchSubdirectories = true, bool forceRepackage = false, string[]? excludedFileExtensions = null)
        {
            AssetsPackagerHelper.PackageFilesInDirectory(sourceDestPaths, unpackagedBehaviorDirRegex, packagedBehaviorExtension, searchSubdirectories, forceRepackage, excludedFileExtensions);
        }

    }
}
