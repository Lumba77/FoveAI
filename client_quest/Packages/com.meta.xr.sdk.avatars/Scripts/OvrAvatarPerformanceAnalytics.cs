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

using System;
namespace Oculus.Avatar2
{
    public static class OvrAvatarPerformanceAnalytics
    {
        //:: Constants
        private const string logScope = "performance_analytics";

        private static byte[] toByteArray(string str, ref UInt32 size)
        {
            if (str == null)
            {
                size = 0;
                return null;
            }

            var bytes = System.Text.ASCIIEncoding.ASCII.GetBytes(str.ToCharArray());
            size = (UInt32)bytes.Length;
            return bytes;
        }

        public static bool enable(string testAppName, uint approxSampleCount = 0)
        {
            unsafe
            {
                UInt32 size = 0;
                var bytes = toByteArray(testAppName, ref size);
                fixed (byte* ptr = bytes)
                {
                }
            }

            return false;
        }


        public static bool updateMetric(Int32 metric, double value)
        {
            return false;
        }


        public static bool sendMetric(Int32 metric, double value, string comment = null, byte[] payload = null)
        {
            var payloadSize = payload == null ? 0 : (UInt32)payload.Length;
            UInt32 commentSize = 0;

            unsafe
            {
                var commentBytes = toByteArray(comment, ref commentSize);
                fixed (byte* commentPtr = commentBytes, payloadPtr = payload)
                {
                    return false;
                }
            }
        }


        public static void begin()
        {
        }

    }
}
