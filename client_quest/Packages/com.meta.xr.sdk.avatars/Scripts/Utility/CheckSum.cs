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

using System.IO;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;

namespace Oculus.Avatar2
{
    /// <summary>
    /// This class contains utility methods to check if two files or directories are synchronized.
    /// By using the MD5 hash algorithm to calculate the checksum of individual files, we are able
    /// quickly compare if two files are different. This will be used in our Asset delivery pipeline
    /// for verifying if preset, behavior, and asset binaries need to be recopied into StreamingAssets.
    /// </summary>
    public class Checksum
    {

        public static BigInteger CalculateChecksum(string file)
        {
            if (!File.Exists(file))
            {
                throw new FileNotFoundException($"The file '{file}' does not exist.");
            }

            using (var md5 = MD5.Create())
            {
                using (var stream = File.OpenRead(file))
                {
                    byte[] checksum = md5.ComputeHash(stream);
                    return new BigInteger(checksum);
                }
            }
        }

        public static BigInteger CalculateChecksumRecursive(string rootDirectory)
        {
            using var md5 = MD5.Create();
            using var cs = new CryptoStream(Stream.Null, md5, CryptoStreamMode.Write);
            CalculateChecksumRecursiveInternal(rootDirectory, cs);
            cs.FlushFinalBlock();
            return new BigInteger(md5.Hash);
        }

        private static void CalculateChecksumRecursiveInternal(string directory, CryptoStream cs)
        {
            foreach (var fileFullPath in Directory.GetFiles(directory))
            {
                // Hash file path, because renames matter as well.
                var pathBytes = Encoding.UTF8.GetBytes(fileFullPath);
                cs.Write(pathBytes, 0, pathBytes.Length);
                // Hash file contents.
                using var stream = File.OpenRead(fileFullPath);
                stream.CopyTo(cs);
            }
            foreach (var subdirectory in Directory.GetDirectories(directory))
            {
                CalculateChecksumRecursiveInternal(subdirectory, cs);
            }
        }
    }
}
