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

using UnityEngine;

namespace Oculus.Avatar2
{
    public partial class OvrAvatarEntity : MonoBehaviour
    {
        [Obsolete("Deprecated, please refer to documentation")]
        internal bool SetCustomWristOffset(CAPI.ovrAvatar2Side side, in CAPI.ovrAvatar2Transform offset)
        {
            return CAPI.OvrAvatar2_SetCustomWristOffset(entityId, side, in offset, this);
        }

        internal bool SetCustomHandSkeleton(CAPI.ovrAvatar2Side side, in CAPI.ovrAvatar2TrackingBodySkeleton cSkel)
        {
            return CAPI.OvrAvatar2_SetCustomHandSkeleton(entityId, side, in cSkel, this);
        }

        internal bool SetCustomHandPose(CAPI.ovrAvatar2Side side, in CAPI.ovrAvatar2TrackingBodyPose cPose)
        {
            return CAPI.OvrAvatar2_SetCustomHandPose(entityId, side, in cPose, this);
        }

        internal bool ClearCustomHandPose(CAPI.ovrAvatar2Side side)
        {
            return CAPI.OvrAvatar2_ClearCustomHandPose(entityId, side, this);
        }
    }

    public static partial class CAPI
    {
        private const string handPoseScope = "handPose";

        internal static bool
        OvrAvatar2_SetCustomWristOffset(
            ovrAvatar2EntityId entityId,
            ovrAvatar2Side side,
            in ovrAvatar2Transform offset,
            OvrAvatarEntity context)
        {
            return ovrAvatar2_SetCustomWristOffset(entityId, side, in offset)
                .EnsureSuccess("ovrAvatar2_SetCustomWristOffset", handPoseScope, context);
        }

        internal static bool
            OvrAvatar2_SetCustomHandSkeleton(
                ovrAvatar2EntityId entityId,
                ovrAvatar2Side side,
                in ovrAvatar2TrackingBodySkeleton skeleton,
                OvrAvatarEntity context)
        {
            return ovrAvatar2_SetCustomHandSkeleton(entityId, side, in skeleton)
                .EnsureSuccess("ovrAvatar2_SetCustomHandSkeleton", handPoseScope, context);
        }

        internal static bool
            OvrAvatar2_SetCustomHandPose(
                ovrAvatar2EntityId entityId,
                ovrAvatar2Side side,
                in ovrAvatar2TrackingBodyPose pose,
                OvrAvatarEntity context)
        {
            return ovrAvatar2_SetCustomHandPose(entityId, side, in pose)
                .EnsureSuccess("ovrAvatar2_SetCustomHandPose", handPoseScope, context);
        }



        internal static bool OvrAvatar2_ClearCustomHandPose(ovrAvatar2EntityId entityId,
                ovrAvatar2Side side,
                OvrAvatarEntity context)
        {
            return ovrAvatar2_ClearCustomHandPose(entityId, side)
                .EnsureSuccess("ovrAvatar2_ClearCustomHandPose", handPoseScope, context);
        }
    }
}
