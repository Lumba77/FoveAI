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
using System.Linq;
using System.IO.Compression;
using System.Collections.Generic;
using UnityEngine;

namespace Oculus.Avatar2
{
    /// <summary>
    /// This class contains helper methods for packaging unpackaged assets in a project, if necessary.
    /// An unpackaged asset is a collection of directories and files. This could apply to behavior
    /// assets, or preset Avatar glbs, which all need to be in a zip format before build. These methods
    /// will help generate and manage the packaging process.
    /// </summary>
    public class AssetsPackagerHelper
    {
        private static readonly string logScope = "AssetsPackager";

        /// <summary>
        /// Searches through the specified directory for any unpackaged files, and
        /// creates packages for each one. Packages are only created if no package exists,
        /// or if one or more files in the unpackaged directory has been modified more recently than
        /// the package. If a file is found in a subdirectory of the search directory,
        /// the resulting package will be created in a subdirectory of the output
        /// directory with the same relative path.
        /// </summary>
        /// <param name="sourceDestPaths">Array of Tuples, where the first item is the source
        /// path to search for unpackaged files, and the second item is the destination
        /// path the packaged files will be written out to</param>
        /// <param name="unpackagedRegex">String in regex format used to search for directories containing unzipped files
        /// </param>
        /// <param name="packagedExtension">String of the file extension of the packaged files
        /// to be created</param>
        /// <param name="searchSubdirectories">When true, this method will seach all
        /// subdirectories for unpackaged files</param>
        /// <param name="forceRepackage">When true, this method will ignore the timestamp
        /// of any existing packages, and will automatically repackage all files</param>
        /// <param name="excludedFileExtensions">Do not package any files with these extensions</param>
        public static void PackageFilesInDirectory(Tuple<string, string>[] sourceDestPaths, string unpackagedRegex, string packagedExtension = ".zip", bool searchSubdirectories = true, bool forceRepackage = false, string[]? excludedFileExtensions = null, IReadOnlyCollection<string>? fileSelection = null)
        {
            foreach (var sourceDestPath in sourceDestPaths)
            {
                // Verify that the search path exists. If it doesn't, skip it.
                if (!Directory.Exists(sourceDestPath.Item1))
                {
                    continue;
                }

                // If we are trying to selective package files, we need to repackage regardless of timestamp
                if (fileSelection != null)
                {
                    forceRepackage = true;
                }

                // Get all directories that end with the unpackaged extension
                string[] unpackagedFiles = Directory.GetDirectories(sourceDestPath.Item1, $"{unpackagedRegex}", searchSubdirectories ? SearchOption.AllDirectories : SearchOption.TopDirectoryOnly);

                foreach (string unpackagedFile in unpackagedFiles)
                {
                    // Get the relative path between the search directory and the unpackaged file so we can
                    // maintain that relative path for the package in the output directory.
                    string relativePath = Path.GetRelativePath(sourceDestPath.Item1, unpackagedFile);
                    string outputPath = Path.Combine(sourceDestPath.Item2, relativePath) + packagedExtension;

                    PackageFiles(unpackagedFile, outputPath, forceRepackage, excludedFileExtensions, fileSelection);
                }
            }
        }

        /// <summary>
        /// Creates a package for the specified files if a package doesn't already exist,
        /// or if any of the specified files has been modifed since the package was created.
        /// </summary>
        /// <param name="unpackagedDirectory">The path to the directory containing the unpackaged files</param>
        /// <param name="outputPath">The path to where the resulting package will be saved</param>
        /// <param name="forceRepackage">When true, this method will ignore the timestamp of
        /// an existing package, and will automatically repackage the files</param>
        /// <param name="excludedFileExtensions">File extension to exclude when packaging</param>
        private static void PackageFiles(string unpackagedDirectory, string outputPath, bool forceRepackage, string[]? excludedFileExtensions, IReadOnlyCollection<string>? fileSelection = null)
        {
            // Does a package (i.e., zip file) already exist?
            if (!File.Exists(outputPath))
            {
                // Existing package was not found.
                OvrAvatarLog.LogVerbose($"Existing package for {unpackagedDirectory} not found, creating new package", logScope);

                // Create the directory if it doesn't already exist.
                Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? string.Empty);
            }
            // Package already exists...
            else
            {
                // If force repackage is enabled, we'll repackage it regardless of timestamp.
                if (forceRepackage)
                {
                    OvrAvatarLog.LogVerbose($"Existing package for {unpackagedDirectory} was found; force repackage enabled, repackaging", logScope);
                }
                // Force repackage is not enabled; check the timestamp to see if it needs to be repackaged.
                else
                {
                    DateTime packageLastModified = File.GetLastWriteTime(outputPath);
                    DateTime fileLastModified = GetLastWriteTime(unpackagedDirectory, excludedFileExtensions);

                    // If the package was last modified more recently than the unpackaged files, we don't need to repackage it.
                    if (fileLastModified < packageLastModified)
                    {
                        OvrAvatarLog.LogVerbose($"Existing package for {unpackagedDirectory} was found with a newer timestamp, skipping repackage", logScope);
                        return;
                    }

                    OvrAvatarLog.LogVerbose($"Existing package for {unpackagedDirectory} was found to be out-of-date; repackaging", logScope);
                }

                // Clean up the existing package.
                File.Delete(outputPath);
            }

            if ((excludedFileExtensions != null) || (fileSelection != null))
            {
                // Filter out unwanted file extensions in the tmp directory, and
                // then zip up the tmp directory afterwards.
                string tmpDir = unpackagedDirectory + "_tmp";
                CopyDirectory(unpackagedDirectory, tmpDir, excludedFileExtensions, fileSelection);

                // Package the files.
                ZipFile.CreateFromDirectory(tmpDir, outputPath);
                Directory.Delete(tmpDir, recursive: true);
            }
            else
            {
                // Package the files.
                ZipFile.CreateFromDirectory(unpackagedDirectory, outputPath);
            }

            OvrAvatarLog.LogInfo($"Created package {outputPath}", logScope);
        }

        /// <summary>
        /// Recursively copy a directory
        /// </summary>
        /// <param name="sourcePath">Source directory to copy</param>
        /// <param name="outputPath">Output directory path</param>
        /// <param name="excludedExtensions">File extensions to exclude from copying</param>
        public static void CopyDirectory(string sourcePath, string outputPath, string[]? excludedExtensions = null, IReadOnlyCollection<string>? fileSelection = null)
        {
            if (Directory.Exists(outputPath))
            {
                Directory.Delete(outputPath, recursive: true);
            }

            Directory.CreateDirectory(outputPath);

            foreach (var file in Directory.GetFiles(sourcePath))
            {
                var fileExtension = Path.GetExtension(file);

                if ((excludedExtensions?.Contains(fileExtension) == true) || (fileSelection?.Contains(Path.GetFileName(file)) == false))
                {
                    continue;
                }

                File.Copy(file, Path.Combine(outputPath, Path.GetFileName(file)), true);
            }

            foreach (var subDirectory in Directory.GetDirectories(sourcePath))
            {
                CopyDirectory(subDirectory, Path.Combine(outputPath, Path.GetFileName(subDirectory)), excludedExtensions);
            }
        }

        /// <summary>
        /// Gets the time the most-recently written file in the specified directory was last modified.
        /// </summary>
        /// <param name="directoryPath">The path to the directory</param>
        /// <param name="excludedExtensions">The extensions of files we want to ignore when checking
        /// for the last modified time</param>
        /// <returns>The DateTime of the most recently modified file found in the specified directory</returns>
        public static DateTime GetLastWriteTime(string directoryPath, string[]? excludedExtensions = null)
        {
            DateTime lastWriteTime = DateTime.MinValue;

            try
            {
                FileInfo? fileInfo;

                // Get all files in the directory (including subdirectories), where the file does not have an
                // excluded extension, sort them by LastWriteTime in descending order, and the first result
                // will be the most-recently modified file.
                if (excludedExtensions != null)
                {
                    fileInfo = new DirectoryInfo(directoryPath).GetFiles("*", SearchOption.AllDirectories).Where(o => excludedExtensions?.Contains(o.Extension) == false).OrderByDescending(o => o.LastWriteTime).FirstOrDefault();
                }
                else
                {
                    fileInfo = new DirectoryInfo(directoryPath).GetFiles("*", SearchOption.AllDirectories).OrderByDescending(o => o.LastWriteTime).FirstOrDefault();
                }

                if (fileInfo != null)
                {
                    lastWriteTime = fileInfo.LastWriteTime;
                }
                else
                {
                    lastWriteTime = DateTime.Now;
                }
            }
            catch (Exception ex)
            {
                OvrAvatarLog.LogError($"Exception thrown while querying last write time for directory: {ex.Message}", logScope);
            }

            return lastWriteTime;
        }
    }
}
