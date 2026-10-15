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
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using System.Text.RegularExpressions;

namespace Oculus.Avatar2.Experimental
{
    /// <summary>
    /// This class contains helper methods for locating unpackaged presets in a project,
    /// and generates packages for each one, if necessary. An unpackaged preset directory
    /// is a collection of directories and files, with the name of its root directory
    /// beginning with "PresetAvatars" or "Style2Avatars0" for style 2 Avatars. A packaged
    /// preset zip is simply a zip archive of the unpackaged presets.
    /// </summary>
    public class PresetPackager
    {
        private const string unpackagedPresetDirRegex = PresetHelper.unpackagedPresetPrefix + "*";

        private const string packagedPresetExtension = ".zip";

        // The default array of paths to search for unpackaged presets, and the
        // corresponding destination paths the packaged presets will be written out to.
        public static readonly Tuple<string, string>[] DefaultSourceDestPaths = {
             new (
                 PresetHelper.presetUnpackagedDirectory, // Source path
                 PresetHelper.presetPackagedDirectory // Dest path
                 ),
        };

        /// <summary>
        /// Searches through the specified directory for any unpackaged presets, and
        /// creates packages for each one. Packages are only created if no package exists,
        /// or if one or more files in the presets has been modified more recently than
        /// the package. If a preset is found in a subdirectory of the search directory,
        /// the resulting package will be created in a subdirectory of the output
        /// directory with the same relative path.
        /// </summary>
        /// <param name="sourceDestPaths">Array of Tuples, where the first item is the source
        /// path to search for unpackaged presets, and the second item is the destination
        /// path the packaged presets will be written out to</param>
        /// <param name="searchSubdirectories">When true, this method will seach all
        /// subdirectories for unpackaged presets</param>
        /// <param name="forceRepackage">When true, this method will ignore the timestamp
        /// of any existing packages, and will automatically repackage all presets</param>
        /// <param name="excludedFileExtensions">Do not package any files with these extensions</param>
        public static void PackagePresetsInDirectory(Tuple<string, string>[] sourceDestPaths, bool searchSubdirectories = true, bool forceRepackage = false, string[]? excludedFileExtensions = null, IReadOnlyCollection<string>? fileSelection = null)
        {
            AssetsPackagerHelper.PackageFilesInDirectory(sourceDestPaths, unpackagedPresetDirRegex, packagedPresetExtension, searchSubdirectories, forceRepackage, excludedFileExtensions, fileSelection);
        }
    }
}
