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
using UnityEngine.Assertions;

namespace Oculus.Avatar2
{

    public static partial class CAPI
    {
        // Ease of use managed structure for registering an avatar with the LOD system.
        // At time of registration we'll make the struct below.
        public struct ovrAvatar2LODRegistration
        {
            public Int32 avatarId; // Caller defined identifier for the avatar instance
            public Int32[] lodWeights; // Weights of LODs and count
            public Int32 lodThreshold;  // Max lod level permitted
        };

        // What we supply to the runtime C API, from the above
        // Runtime copies data out of here, so there is no need for this data to be persistent
        [StructLayout(LayoutKind.Sequential)]
        private struct ovrAvatar2LODRegistrationNative
        {
            public Int32 avatarId; // Caller defined identifier for the avatar instance
            public IntPtr lodWeights; // Weights of LODs and count
            public Int32 lodWeightCount; // Weight count
            public Int32 lodThreshold;  // Max lod level permitted
        };

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2LODUpdate
        {
            public Int32 avatarId; // Caller defined identifier for the avatar instance
            [MarshalAs(UnmanagedType.U1)]
            public bool isPlayer;  // This avatar is the player
            [MarshalAs(UnmanagedType.U1)]
            public bool isCulled;  // This avatar has been culled by some visbility system
            public Int32 importanceScore; // User defined importance (eg distance from cam)
        };

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2LODInput
        {
            public Int32 avatarId; // Caller defined identifier for the avatar instance
            public Int32 minLod;
            public Int32 maxLod;
            public bool toProcess;
            public bool isCulled;
            public bool isPlayer;
            public ovrAvatar2Vector3f pos;
            public float scale;
            public Int32 triangleData0;
            public Int32 triangleData1;
            public Int32 triangleData2;
            public Int32 triangleData3;
            public Int32 triangleData4;
            public Int32 prevLOD;
            public Int32 assignedLOD;
            public Int32 wantedLOD;
            public float fracLOD;
            public Int32 lodImportance;
            public bool LODToggled;
            public bool cullToggled;
            public float importance;
            public float distance;
        };

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2LODCamera
        {
            public float twoOverFov; // = 2 / fieldOfView
            public float height;
            public ovrAvatar2Vector3f position;
            public ovrAvatar2Vector3f forward;
        };

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2LODParameters
        {
            public float dynamicLodWantedLogScale;
            public float updateImportanceUpdatePower;
            public float updateImportanceUpdateMult;
            public Int32 lodCountPerFrame;
            public Int32 geometryTriLimit;
            public Int32 numDynamicLevels;
            public Int32 maxActiveAvatars;
            public Int32 maxVerticesToSkin;
            public ovrAvatar2Vector4f cullingPlane0;
            public ovrAvatar2Vector4f cullingPlane1;
            public ovrAvatar2Vector4f cullingPlane2;
            public ovrAvatar2Vector4f cullingPlane3;
            public ovrAvatar2Vector4f cullingPlane4;
            public ovrAvatar2Vector4f cullingPlane5;
            public bool performCulling;
        };

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2LODStats
        {
            public Int32 numTrisRequested;
            public Int32 numTrisFitted;
            unsafe public fixed Int32 NumLODsRequested[5];
            unsafe public fixed Int32 NumLODsFitted[5];
        };


        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2LODResult
        {
            public Int32 avatarId; // Caller defined identifier for the avatar instance
            public Int32 assignedLOD; // LOD level assigned to this avatar
        };

        // Register / unregister / query avatar

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2LOD_UnregisterAvatar(Int32 id);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2LOD_AvatarRegistered(Int32 id);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, EntryPoint = "ovrAvatar2LOD_RegisterAvatar")]
        internal static extern ovrAvatar2Result ovrAvatar2LOD_RegisterAvatarNative(IntPtr recrord);

        internal static ovrAvatar2Result ovrAvatar2LOD_RegisterAvatar(ovrAvatar2LODRegistration record)
        {
            unsafe
            {
                fixed (Int32* weightPtr = record.lodWeights)
                {
                    ovrAvatar2LODRegistrationNative nativeRecord;
                    nativeRecord.avatarId = record.avatarId;
                    nativeRecord.lodWeights = (IntPtr)weightPtr;
                    nativeRecord.lodWeightCount = record.lodWeights.Length;
                    nativeRecord.lodThreshold = record.lodThreshold;

                    return ovrAvatar2LOD_RegisterAvatarNative(new IntPtr(&nativeRecord));
                }
            }
        }

        // Calculate LOD distribution

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern void ovrAvatar2LOD_SetDistribution(Int32 maxWeightValue, float exponent);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, EntryPoint = "ovrAvatar2LOD_GenerateDistribution")]
        unsafe internal static extern ovrAvatar2Result ovrAvatar2LOD_GenerateDistributionNative(
            Int32* weightDistribution,
            Int32 distributionCount,
            ovrAvatar2LODUpdate* lodUpdates,
            ovrAvatar2LODResult* lodResults,
            Int32 avatarCount,
            Int32* totalAssignedWeight);

        internal static ovrAvatar2Result ovrAvatar2LOD_GenerateDistribution(
            Int32[] weightDistribution,
            ovrAvatar2LODUpdate[] lodUpdates,
            ref ovrAvatar2LODResult[] lodResults,
            out Int32 totalAssignedWeightOut)
        {
            Assert.IsNotNull(lodResults);

            ovrAvatar2Result result;
            Int32 totalAssignedWeight;
            unsafe
            {
                fixed (Int32* weightDistributionPtr = weightDistribution)
                {
                    fixed (ovrAvatar2LODUpdate* updatesPtr = lodUpdates)
                    {
                        fixed (ovrAvatar2LODResult* resultsPtr = lodResults)
                        {
                            result = ovrAvatar2LOD_GenerateDistributionNative(
                                weightDistributionPtr,
                                weightDistribution.Length,
                                updatesPtr,
                                resultsPtr,
                                lodUpdates.Length,
                                &totalAssignedWeight);
                        }
                    }
                }
            }
            totalAssignedWeightOut = totalAssignedWeight;
            return result;
        }


        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, EntryPoint = "ovrAvatar2LOD_GenerateLodLevels")]
        unsafe internal static extern ovrAvatar2Result ovrAvatar2LOD_GenerateLodLevelsNative(
            ovrAvatar2LODParameters* lodParams,
            ovrAvatar2LODCamera* cameras,
            Int32 cameraCount,
            ovrAvatar2LODInput* lodInputs,
            Int32 avatarCount,
            out ovrAvatar2LODStats outStats);

        internal static ovrAvatar2Result ovrAvatar2LOD_GenerateLodLevels(
            ovrAvatar2LODParameters lodParams,
            ovrAvatar2LODCamera[] cameras,
            Int32 cameraCount,
            ovrAvatar2LODInput[] lodInputs,
            Int32 avatarCount,
            out ovrAvatar2LODStats stats)
        {
            ovrAvatar2Result result;
            unsafe
            {
                fixed (ovrAvatar2LODCamera* camerasP = cameras)
                {
                    fixed (ovrAvatar2LODInput* lodInputsP = lodInputs)
                    {
                        result = ovrAvatar2LOD_GenerateLodLevelsNative(
                                &lodParams,
                                camerasP,
                                cameraCount,
                                lodInputsP,
                                avatarCount,
                                out stats);

                    }
                }
            }
            return result;
        }

    }
}
