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
using System.Runtime.InteropServices;

namespace Oculus.Avatar2.Experimental
{
    using ovrAvatar2Id = Avatar2.CAPI.ovrAvatar2Id;

    public static partial class CAPI
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct ovrAvatar2AnimHierarchyAsset
        {
            public ovrAvatar2Id id; // asset id of the hierarchy
            public string name; // name of the hierarchy
            public UInt64 hash; // name of the hierarchy
            public UInt32 jointCount; // Number of joints in the joint hierarchy
            public IntPtr jointTransform; // Joint transforms
            public IntPtr jointParents; // joint parents
            public IntPtr jointNames; // joint names
            public UInt32 floatChannelCount; // number of float values
            public IntPtr floatChannelNames; // array of float value names
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct ovrAvatar2AnimClipAsset
        {
            public ovrAvatar2Id id; // asset id of the animation clip
            [MarshalAs(UnmanagedType.LPStr)]
            public IntPtr name; // name of the animation clip
            [MarshalAs(UnmanagedType.LPStr)]
            public IntPtr hierarchyName; // name of the animation hierarchy
            public UInt64 hierarchyHash; // hash of the animation hierarchy
            public Int32 hierarchyJointCount; // number of joints in the hierarchy
            public Int32 hierarchyFloatCount; // number of float channels in the hierarchy
            public Int32 numSamples; // number of samples (Duration = (numSamples - 1)*sampleDeltaTimeSecs)
            public float sampleDeltaTimeSecs; // sampleDeltaTime.
            [MarshalAs(UnmanagedType.U1)]
            public bool looping; // whether the animation is looping.
            [MarshalAs(UnmanagedType.U1)]
            public bool additive; // whether the animation is additive
        }
    }
}
