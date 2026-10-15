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
using UnityEditor;
using UnityEngine;
using System.Numerics;

namespace Oculus.Avatar2
{
    public class StreamingAssetsHelper
    {
        public static void SynchronizeFolders(string source, string destination, string? sourceKey = null, string? destinationKey = null)
        {
            if (!File.Exists(source))
            {
                OvrAvatarLog.LogWarning("Trying to copy an asset that doesn't exist: "
                    + source
                    + ". Deleting the destination folder instead: "
                    + destination, nameof(StreamingAssetsHelper));
                DeleteFile(destination);
                return;
            }

            if (sourceKey != null)
            {
                UpdateEditorPrefsChecksum(source, sourceKey);
            }

            try
            {
                var destinationDirectory = Path.GetDirectoryName(destination);
                Directory.CreateDirectory(destinationDirectory ?? throw new InvalidOperationException("Bad destination file path"));
                File.Copy(source, destination, true);
            }
            catch (IOException e)
            {
                OvrAvatarLog.LogException($"Copy asset {source}", e, nameof(StreamingAssetsHelper));
            }

            if (destinationKey != null)
            {
                UpdateEditorPrefsChecksum(destination, destinationKey);
            }
        }

        public static bool HasFileUpdated(string path, string shortkey, bool updateCheckSum = false)
        {
            var uniqueKey = GetUniqueEditorPrefsKey(shortkey);
            if (File.Exists(path))
            {
                var currentCheckSum = Checksum.CalculateChecksum(path);

                // Assume the checkSum for a file will never be 0
                BigInteger previousCheckSum = BigInteger.Zero;

                // If there was a previous checksum and the file exists, compare checksums
                if (EditorPrefs.HasKey(uniqueKey))
                {
                    previousCheckSum = BigInteger.Parse(EditorPrefs.GetString(uniqueKey));
                }
                if (updateCheckSum)
                {
                    EditorPrefs.SetString(uniqueKey, currentCheckSum.ToString());
                }
                return currentCheckSum != previousCheckSum;
            }
            // Return true only if there is both no Editor Key and no directory
            return !EditorPrefs.HasKey(uniqueKey);
        }

        public static bool HasDirectoryUpdated(string path, string shortkey, bool updateCheckSum = false)
        {
            var uniqueKey = GetUniqueEditorPrefsKey(shortkey);
            if (Directory.Exists(path))
            {
                var currentCheckSum = Checksum.CalculateChecksumRecursive(path);

                // Assume the checkSum for a directory will never be 0
                BigInteger previousCheckSum = BigInteger.Zero;

                // If there was a previous checksum and the directory exists, compare checksums
                if (EditorPrefs.HasKey(uniqueKey))
                {
                    previousCheckSum = BigInteger.Parse(EditorPrefs.GetString(uniqueKey));
                }
                if (updateCheckSum)
                {
                    EditorPrefs.SetString(uniqueKey, currentCheckSum.ToString());
                }
                return currentCheckSum != previousCheckSum;
            }
            // Return true only if there is both no Editor Key and no directory
            return !EditorPrefs.HasKey(uniqueKey);
        }

        public static void UpdateEditorPrefsChecksum(string path, string shortkey)
        {
            var uniqueKey = GetUniqueEditorPrefsKey(shortkey);
            BigInteger currentCheckSum = Checksum.CalculateChecksum(path);
            EditorPrefs.SetString(uniqueKey, currentCheckSum.ToString());
        }

        public static string GetUniqueEditorPrefsKey(string shortKey)
        {
            return Application.dataPath + "_" + shortKey;
        }

        public static void DeleteFile(string path)
        {
            OvrAvatarLog.LogInfo($"Cleaning up old binaries: {path}", nameof(StreamingAssetsHelper));
            try
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                    File.Delete(path + ".meta");
                }
            }
            catch (IOException e)
            {
                OvrAvatarLog.LogException("Cleaning up old binaries: {path}", e, nameof(StreamingAssetsHelper));
            }
        }
    }
}
