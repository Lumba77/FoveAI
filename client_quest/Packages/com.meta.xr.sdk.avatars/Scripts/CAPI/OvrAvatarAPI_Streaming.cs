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

using Unity.Collections;

using UnityEngine;

namespace Oculus.Avatar2
{
    public static partial class CAPI
    {
        private const string StreamingCapiLogScope = "OvrAvatarAPI_Streaming";

        //-----------------------------------------------------------------
        //
        // State
        //
        //

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2StreamingPlaybackState
        {
            public UInt32 numSamples; // Number of samples in the playback buffer
            public float interpolationBlendWeight; // Interpolation blend between the oldest 2 samples
            public UInt64 oldestSampleTime; // Time in microseconds of the oldest sample
            public UInt64 latestSampleTime; // Time in microseconds of the newest sample
            public UInt64 remoteTime; ///< Time in microseconds of the remote time (for snapshot playback)
            public UInt64 localTime; ///< Time in microseconds of local time (for snapshot playback)
            public UInt64 recordingPlaybackTime; ///< Time in microseconds of recordingPlayback time (for recording playback)
            [MarshalAs(UnmanagedType.U1)]
            public bool poseValid; ///< Whether the playback pose is valid
            public UInt64 playbackTime; ///< Time in microseconds that we are ultimately sampling the stream at that
                                        ///< determines the interpolationBlendWeight
        }

        //-----------------------------------------------------------------
        //
        // Record
        //
        //

        public enum ovrAvatar2StreamLOD : Int32
        {
            Full, // Full avatar state with lossless compression
            High, // Full avatar state with lossy compression
            Medium, // Partial avatar state with lossy compression
            Low, // Minimal avatar state with lossy compression
        }
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_RecordStart(ovrAvatar2EntityId entityId);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_RecordStop(ovrAvatar2EntityId entityId);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_RecordSnapshot(ovrAvatar2EntityId entityId);

        public static unsafe bool OvrAvatar2Streaming_SerializeRecording(
            ovrAvatar2EntityId entityId, ovrAvatar2StreamLOD lod, byte* destinationPtr, ref UInt64 bytes)
        {
            return ovrAvatar2Streaming_SerializeRecording(entityId, lod, destinationPtr, ref bytes)
                .EnsureSuccess("ovrAvatar2Streaming_SerializeRecording", StreamingCapiLogScope);
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static unsafe extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_SerializeRecording(
            ovrAvatar2EntityId entityId, ovrAvatar2StreamLOD lod, byte* destinationPtr, ref UInt64 bytes);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_GetRecordingSize(
            ovrAvatar2EntityId entityId, ovrAvatar2StreamLOD lod, out UInt64 bytes);

        //-----------------------------------------------------------------
        //
        // Playback
        //
        //

        public enum DeserializationResult
        {
            UnknownError = -1,
            Success = 0,
            DeserializationPending = 1,
            PlaybackDisabled = 2,
            BufferTooSmall = 3,
            InvalidData = 4,
            SkeletonMismatch = 5,
            EntityNotReady = 6,
        }

        public static DeserializationResult OvrAvatar2Streaming_DeserializeRecording_WithResult(
            ovrAvatar2EntityId entityId, in NativeArray<byte> sourceBuffer, UnityEngine.Object? context = null)
        {
            unsafe
            {
                return OvrAvatar2Streaming_DeserializeRecording_WithResult(
                    entityId, sourceBuffer.GetPtr(), sourceBuffer.GetBufferSize(), context);
            }
        }

        public static DeserializationResult OvrAvatar2Streaming_DeserializeRecording_WithResult(
            ovrAvatar2EntityId entityId, byte[] sourceBuffer, UnityEngine.Object? context = null)
        {
            unsafe
            {
                fixed (byte* sourceBytes = sourceBuffer)
                {
                    return OvrAvatar2Streaming_DeserializeRecording_WithResult(
                        entityId, sourceBytes, (UInt64)sourceBuffer.Length, context);
                }
            }
        }

        public static unsafe DeserializationResult OvrAvatar2Streaming_DeserializeRecording_WithResult(
            ovrAvatar2EntityId entityId, byte* sourceBuffer, UInt64 bytes, UnityEngine.Object? context = null)
        {
            Debug.Assert(entityId != ovrAvatar2EntityId.Invalid);
            Debug.Assert(sourceBuffer != null);
            Debug.Assert(bytes > 0);

            var result = ovrAvatar2Streaming_DeserializeRecording(entityId, sourceBuffer, bytes);
            switch (result)
            {
                case ovrAvatar2Result.Success:
                    return DeserializationResult.Success;

                case ovrAvatar2Result.DeserializationPending:
                    return DeserializationResult.DeserializationPending;
                case ovrAvatar2Result.NotFound:
                    return DeserializationResult.PlaybackDisabled;
                case ovrAvatar2Result.BufferTooSmall:
                    return DeserializationResult.BufferTooSmall;
                case ovrAvatar2Result.InvalidData:
                    return DeserializationResult.InvalidData;
                case ovrAvatar2Result.SkeletonMismatch:
                    return DeserializationResult.SkeletonMismatch;

                default:
                    return DeserializationResult.UnknownError;
            }
        }

        public static bool OvrAvatar2Streaming_DeserializeRecording(
            ovrAvatar2EntityId entityId, in NativeArray<byte> sourceBuffer, UnityEngine.Object? context = null)
        {
            unsafe
            {
                return OvrAvatar2Streaming_DeserializeRecording(
                    entityId, sourceBuffer.GetPtr(), sourceBuffer.GetBufferSize(), context);
            }
        }


        public static bool OvrAvatar2Streaming_DeserializeRecording(
            ovrAvatar2EntityId entityId, byte[] sourceBuffer, UnityEngine.Object? context = null)
        {
            unsafe
            {
                fixed (byte* sourceBytes = sourceBuffer)
                {
                    return OvrAvatar2Streaming_DeserializeRecording(
                        entityId, sourceBytes, (UInt64)sourceBuffer.Length, context);
                }
            }
        }

        public static unsafe bool OvrAvatar2Streaming_DeserializeRecording(
            ovrAvatar2EntityId entityId, byte* sourceBuffer, UInt64 bytes, UnityEngine.Object? context = null)
        {
            var result = OvrAvatar2Streaming_DeserializeRecording_WithResult(entityId, sourceBuffer, bytes, context);
            switch (result)
            {
                case DeserializationResult.Success: break;

                case DeserializationResult.DeserializationPending:
                    OvrAvatarLog.LogVerbose(
                        "ovrAvatar2Streaming_DeserializeRecording: DeserializationPending (skeleton is not loaded?)"
                        , StreamingCapiLogScope, context);
                    break;

                default:
                    OvrAvatarLog.LogError($"ovrAvatar2Streaming_DeserializeRecording: failed with result ({result})"
                        , StreamingCapiLogScope, context);
                    break;

            }
            return result == DeserializationResult.Success;
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_PlaybackStart(ovrAvatar2EntityId entityId);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_PlaybackStop(ovrAvatar2EntityId entityId);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_SetPlaybackTimeDelay(
            ovrAvatar2EntityId entityId, float delaySeconds);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_SetAutoPlaybackTimeDelay(
            ovrAvatar2EntityId entityId);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Streaming_GetPlaybackState(
            ovrAvatar2EntityId entityId, out ovrAvatar2StreamingPlaybackState playbackState);

        //-----------------------------------------------------------------
        //
        // Dll Bindings
        //
        //

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern unsafe CAPI.ovrAvatar2Result ovrAvatar2Streaming_DeserializeRecording(
            ovrAvatar2EntityId entityId, byte* sourceBuffer, UInt64 bytes);
    }
}
