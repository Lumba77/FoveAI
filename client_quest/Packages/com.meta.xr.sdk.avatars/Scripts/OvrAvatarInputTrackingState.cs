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

namespace Oculus.Avatar2
{
    public struct OvrAvatarInputTrackingState
    {
        public bool headsetActive;
        public bool leftControllerActive;
        public bool rightControllerActive;
        public bool leftControllerVisible;
        public bool rightControllerVisible;
        public CAPI.ovrAvatar2Transform headset;
        public CAPI.ovrAvatar2Transform leftController;
        public CAPI.ovrAvatar2Transform rightController;

        #region Native Conversions
        internal CAPI.ovrAvatar2InputTrackingState ToNative()
        {
            return new CAPI.ovrAvatar2InputTrackingState
            {
                headsetActive = headsetActive,
                leftControllerActive = leftControllerActive,
                rightControllerActive = rightControllerActive,
                leftControllerVisible = leftControllerVisible,
                rightControllerVisible = rightControllerVisible,
                headset = headset,
                leftController = leftController,
                rightController = rightController,
            };
        }

        internal void FromNative(ref CAPI.ovrAvatar2InputTrackingState native)
        {
            headsetActive = native.headsetActive;
            leftControllerActive = native.leftControllerActive;
            rightControllerActive = native.rightControllerActive;
            leftControllerVisible = native.leftControllerVisible;
            rightControllerVisible = native.rightControllerVisible;
            headset = native.headset;
            leftController = native.leftController;
            rightController = native.rightController;
        }
        #endregion
    }
}
