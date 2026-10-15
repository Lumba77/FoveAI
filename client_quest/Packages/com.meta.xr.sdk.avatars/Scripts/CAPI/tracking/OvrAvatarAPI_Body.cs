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

namespace Oculus.Avatar2
{
    public static partial class CAPI
    {
        enum ovrAvatar2HandTrackingBoneId : Int32
        {
            Invalid = -1,

            Start = 0,
            LeftHandThumbTrapezium = Start + 0,
            LeftHandThumbMeta = Start + 1,
            LeftHandThumbProximal = Start + 2,
            LeftHandThumbDistal = Start + 3,
            LeftHandIndexProximal = Start + 4,
            LeftHandIndexIntermediate = Start + 5,
            LeftHandIndexDistal = Start + 6,
            LeftHandMiddleProximal = Start + 7,
            LeftHandMiddleIntermediate = Start + 8,
            LeftHandMiddleDistal = Start + 9,
            LeftHandRingProximal = Start + 10,
            LeftHandRingIntermediate = Start + 11,
            LeftHandRingDistal = Start + 12,
            LeftHandPinkyMeta = Start + 13,
            LeftHandPinkyProximal = Start + 14,
            LeftHandPinkyIntermediate = Start + 15,
            LeftHandPinkyDistal = Start + 16,
            RightHandThumbTrapezium = Start + 17,
            RightHandThumbMeta = Start + 18,
            RightHandThumbProximal = Start + 19,
            RightHandThumbDistal = Start + 20,
            RightHandIndexProximal = Start + 21,
            RightHandIndexIntermediate = Start + 22,
            RightHandIndexDistal = Start + 23,
            RightHandMiddleProximal = Start + 24,
            RightHandMiddleIntermediate = Start + 25,
            RightHandMiddleDistal = Start + 26,
            RightHandRingProximal = Start + 27,
            RightHandRingIntermediate = Start + 28,
            RightHandRingDistal = Start + 29,
            RightHandPinkyMeta = Start + 30,
            RightHandPinkyProximal = Start + 31,
            RightHandPinkyIntermediate = Start + 32,
            RightHandPinkyDistal = Start + 33,
            Count = Start + 34,
        }

        internal const int MaxHandBones = (int)ovrAvatar2HandTrackingBoneId.Count;

        // TODO: Convert to unsafe fixed arrays
        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2HandTrackingState
        {
            public ovrAvatar2Transform wristPosLeft;
            public ovrAvatar2Transform wristPosRight;

            public ovrAvatar2Quatf boneRotation0;
            public ovrAvatar2Quatf boneRotation1;
            public ovrAvatar2Quatf boneRotation2;
            public ovrAvatar2Quatf boneRotation3;
            public ovrAvatar2Quatf boneRotation4;
            public ovrAvatar2Quatf boneRotation5;
            public ovrAvatar2Quatf boneRotation6;
            public ovrAvatar2Quatf boneRotation7;
            public ovrAvatar2Quatf boneRotation8;
            public ovrAvatar2Quatf boneRotation9;
            public ovrAvatar2Quatf boneRotation10;
            public ovrAvatar2Quatf boneRotation11;
            public ovrAvatar2Quatf boneRotation12;
            public ovrAvatar2Quatf boneRotation13;
            public ovrAvatar2Quatf boneRotation14;
            public ovrAvatar2Quatf boneRotation15;
            public ovrAvatar2Quatf boneRotation16;
            public ovrAvatar2Quatf boneRotation17;
            public ovrAvatar2Quatf boneRotation18;
            public ovrAvatar2Quatf boneRotation19;
            public ovrAvatar2Quatf boneRotation20;
            public ovrAvatar2Quatf boneRotation21;
            public ovrAvatar2Quatf boneRotation22;
            public ovrAvatar2Quatf boneRotation23;
            public ovrAvatar2Quatf boneRotation24;
            public ovrAvatar2Quatf boneRotation25;
            public ovrAvatar2Quatf boneRotation26;
            public ovrAvatar2Quatf boneRotation27;
            public ovrAvatar2Quatf boneRotation28;
            public ovrAvatar2Quatf boneRotation29;
            public ovrAvatar2Quatf boneRotation30;
            public ovrAvatar2Quatf boneRotation31;
            public ovrAvatar2Quatf boneRotation32;
            public ovrAvatar2Quatf boneRotation33;

            public float handScaleLeft;
            public float handScaleRight;
            [MarshalAs(UnmanagedType.U1)] public bool isTrackedLeft;
            [MarshalAs(UnmanagedType.U1)] public bool isTrackedRight;
            [MarshalAs(UnmanagedType.U1)] public bool isConfidentLeft;
            [MarshalAs(UnmanagedType.U1)] public bool isConfidentRight;
        }

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate bool HandStateCallback(out ovrAvatar2HandTrackingState skeleton, IntPtr userContext);

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2HandTrackingDataContext
        {
            public ovrAvatar2HandTrackingDataContext(IntPtr context, HandStateCallback handTrackingCallback)
            {
                this.context = context;
                this.handTrackingCallback = handTrackingCallback;
            }

            public IntPtr context;
            public HandStateCallback handTrackingCallback;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct ovrAvatar2HandTrackingDataContextNative
        {
            public IntPtr context;
            public IntPtr handTrackingCallback;
        }

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        [return: MarshalAs(UnmanagedType.U1)]
        internal delegate bool InputControlCallback(out ovrAvatar2InputControlState inputControlState, IntPtr userContext);

        [StructLayout(LayoutKind.Sequential)]
        internal struct ovrAvatar2InputControlContext
        {
            public IntPtr context;
            public InputControlCallback inputControlCallback;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct ovrAvatar2InputControlContextNative
        {
            public IntPtr context;
            public IntPtr inputControlCallback;
        }

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        [return: MarshalAs(UnmanagedType.U1)]
        internal delegate bool InputTrackingCallback(out ovrAvatar2InputTrackingState inputTrackingState, IntPtr userContext);

        [StructLayout(LayoutKind.Sequential)]
        internal struct ovrAvatar2InputTrackingContext
        {
            public IntPtr context;
            public InputTrackingCallback inputTrackingCallback;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct ovrAvatar2InputTrackingContextNative
        {
            public IntPtr context;
            public IntPtr inputTrackingCallback;
        }

        public enum ovrAvatar2BodyMarkerTypes : Int32
        {
            Hmd,
            LeftController,
            RightController,
            LeftHand,
            RightHand,
        }

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [Flags]
        public enum ovrAvatar2BodyProviderCreateFlags : Int32
        {
            /// Use body provider with default settings.
            None = 0,

            /// When set, the body context will run in a background thread.
            RunAsync = 1 << 0,

            /// Enable hip lock in the body solver.
            EnableHipLock = 1 << 1,

            /// Enable hands only mode in the body solver.
            EnableHandsOnly = 1 << 2,

            /// Enable legacy upper bodyapi solver.
            EnableLegacyUpperBody = 1 << 3
        }

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_CreateProvider(
            ovrAvatar2BodyProviderCreateFlags flags, out IntPtr bodyTrackingContext);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_DestroyProvider(IntPtr bodyTrackingContext);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_SetOffset(
            IntPtr bodyTrackingContext,
            ovrAvatar2BodyMarkerTypes type,
            in ovrAvatar2Transform inputTransforms);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_RestartTracking(IntPtr bodyTrackingContext);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_SetHandTrackingContext(IntPtr bodyTrackingContext,
            in ovrAvatar2HandTrackingDataContext handContext);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl,
            EntryPoint = "ovrAvatar2Body_SetHandTrackingContext")]
        internal static extern ovrAvatar2Result ovrAvatar2Body_SetHandTrackingContextNative(
            IntPtr bodyTrackingContext, in ovrAvatar2HandTrackingDataContextNative handContext);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_SetInputControlContext(IntPtr bodyTrackingContext, in ovrAvatar2InputControlContext context);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, EntryPoint = "ovrAvatar2Body_SetInputControlContext")]
        internal static extern ovrAvatar2Result ovrAvatar2Body_SetInputControlContextNative(IntPtr bodyTrackingContext, in ovrAvatar2InputControlContextNative context);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_SetInputTrackingContext(IntPtr bodyTrackingContext, in ovrAvatar2InputTrackingContext context);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, EntryPoint = "ovrAvatar2Body_SetInputTrackingContext")]
        internal static extern ovrAvatar2Result ovrAvatar2Body_SetInputTrackingContextNative(IntPtr bodyTrackingContext, in ovrAvatar2InputTrackingContextNative context);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Body_InitializeDataContext(
            IntPtr bodyTrackingContext, out ovrAvatar2TrackingDataContext dataContext);

        [Obsolete("ovrAvatar2Body functions are deprecated, AvatarSDK by default runs its own body solving given tracking information provided to InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance", false)]
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl,
            EntryPoint = "ovrAvatar2Body_InitializeDataContext")]
        internal static extern ovrAvatar2Result ovrAvatar2Body_InitializeDataContextNative(
            IntPtr bodyTrackingContext, out ovrAvatar2TrackingDataContextNative dataContext);
    }
}
