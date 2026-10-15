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

// TODO: This should be based on a build flag.

using System;
using System.Runtime.InteropServices;
using UnityEngine.Assertions;

namespace Oculus.Avatar2
{
    public static partial class CAPI
    {
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern bool ovrAvatarXLivePerf_FrameBegin();
        public static bool OvrAvatarXLivePerf_FrameBegin()
        {
#if AVATAR2_LIVEPERF
            return ovrAvatarXLivePerf_FrameBegin();
#else // ^^^ AVATAR2_LIVEPERF / !AVATAR2_LIVEPERF vvv
            return false;
#endif // !AVATAR2_LIVEPERF
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern void ovrAvatarXLivePerf_FrameEnd();
        public static void OvrAvatarXLivePerf_FrameEnd()
        {
#if AVATAR2_LIVEPERF
            ovrAvatarXLivePerf_FrameEnd();
#endif // AVATAR2_LIVEPERF
        }

#if AVATAR2_LIVEPERF
        internal struct OvrAvatarXLivePerf_FrameSentry : IDisposable
        {
            private readonly bool inside_;
            public OvrAvatarXLivePerf_FrameSentry(bool unused)
            {
                inside_ = OvrAvatarXLivePerf_FrameBegin();
            }
            public void Dispose()
            {
                if (inside_)
                {
                    OvrAvatarXLivePerf_FrameEnd();
                }
            }
        }
#endif // AVATAR2_LIVEPERF

#if AVATAR2_LIVEPERF
        internal static OvrAvatarXLivePerf_FrameSentry? OvrAvatarXLivePerf_Frame()
        {
            return new OvrAvatarXLivePerf_FrameSentry(true);
        }
#else // ^^^ AVATAR2_LIVEPERF / !AVATAR2_LIVEPERF vvv
        public static IDisposable? OvrAvatarXLivePerf_Frame()
        {
            return null;
        }
#endif // !AVATAR2_LIVEPERF


        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern bool ovrAvatarXLivePerf_StepBegin();
        public static bool OvrAvatarXLivePerf_StepBegin()
        {
#if AVATAR2_LIVEPERF
            return ovrAvatarXLivePerf_StepBegin();
#else // ^^^ AVATAR2_LIVEPERF / !AVATAR2_LIVEPERF vvv
            return false;
#endif // !AVATAR2_LIVEPERF
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern void ovrAvatarXLivePerf_StepEnd();
        public static void OvrAvatarXLivePerf_StepEnd()
        {
#if AVATAR2_LIVEPERF
            ovrAvatarXLivePerf_StepEnd();
#endif // AVATAR2_LIVEPERF
        }

#if AVATAR2_LIVEPERF
        internal struct OvrAvatarXLivePerf_StepSentry : IDisposable
        {
            private readonly bool inside_;
            public OvrAvatarXLivePerf_StepSentry(bool unused)
            {
                inside_ = OvrAvatarXLivePerf_StepBegin();
            }
            public void Dispose()
            {
                if (inside_)
                {
                    OvrAvatarXLivePerf_StepEnd();
                }
            }
        }
#endif // AVATAR2_LIVEPERF

        public static IDisposable? OvrAvatarXLivePerf_Step()
        {
#if AVATAR2_LIVEPERF
            return new OvrAvatarXLivePerf_StepSentry(true);
#else // ^^^ AVATAR2_LIVEPERF / !AVATAR2_LIVEPERF vvv
            return null;
#endif // !AVATAR2_LIVEPERF
        }

        public enum ovrAvatarXLivePerf_UnitySectionID : Int32
        {
            Entity_PreUpdate,
            Entity_Update,
            Entity_ActiveRenderUpdate,
            Entity_OnActiveRender,
            Entity_BroadcastAnimationPreUpdate,
            Entity_BroadcastAnimationUpdate,
            Entity_AnimationFrameUpdates,
            Skinned_Compute_AnimationFrameUpdate,
            Skinned_Gpu_AnimationFrameUpdate,
            Skinned_Unity_AnimationFrameUpdate,
            Entity_SamplePrimitivesSkinningOrigin,
            Entity_SamplePrimitivesSkinningOrigin_Alloc,
            Entity_SamplePrimitivesSkinningOrigin_ApplyTransforms,
            Entity_UpdateSkeletonTransforms,
            Entity_MonitorJoints,
            Entity_MonitorJoints_Notify,
            Entity_PerFrameRenderUpdate,
            Entity_Attachables_OnUpdate,
            SkinningController,
            SkinningController_Combine,
            SkinningController_Skinner,
            SkinningController_Animator,
            GazeTarget,
            LODManager,
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern Int32 ovrAvatarXLivePerf_MarkerBegin(ovrAvatarXLivePerf_UnitySectionID sectionId);
        public static Int32 OvrAvatarXLivePerf_MarkerBegin(ovrAvatarXLivePerf_UnitySectionID sectionId)
        {
#if AVATAR2_LIVEPERF
            return ovrAvatarXLivePerf_MarkerBegin(sectionId);
#else // ^^^ AVATAR2_LIVEPERF / !AVATAR2_LIVEPERF vvv
            return -1;
#endif // !AVATAR2_LIVEPERF
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern void ovrAvatarXLivePerf_MarkerEnd(Int32 markerId);
        public static void OvrAvatarXLivePerf_MarkerEnd(Int32 markerId)
        {
#if AVATAR2_LIVEPERF
            ovrAvatarXLivePerf_MarkerEnd(markerId);
#endif // AVATAR2_LIVEPERF
        }

#if AVATAR2_LIVEPERF
        internal struct OvrAvatarXLivePerf_MarkerSentry : IDisposable
        {
            private readonly Int32 markerId_;
            public OvrAvatarXLivePerf_MarkerSentry(ovrAvatarXLivePerf_UnitySectionID sectionId)
            {
                markerId_ = OvrAvatarXLivePerf_MarkerBegin(sectionId);
            }
            public void Dispose()
            {
                if (markerId_ >= 0)
                {
                    OvrAvatarXLivePerf_MarkerEnd(markerId_);
                }
            }
        }
#endif // AVATAR2_LIVEPERF

#if AVATAR2_LIVEPERF
        internal static OvrAvatarXLivePerf_MarkerSentry? OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID sectionId)
        {
            return new OvrAvatarXLivePerf_MarkerSentry(sectionId);
        }
#else // ^^^ AVATAR2_LIVEPERF / !AVATAR2_LIVEPERF vvv
        public static IDisposable? OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID sectionId)
        {
            return null;
        }
#endif // !AVATAR2_LIVEPERF
    }
}
