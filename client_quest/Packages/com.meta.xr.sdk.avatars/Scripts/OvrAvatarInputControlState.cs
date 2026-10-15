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
    public struct OvrAvatarControllerState
    {
        public CAPI.ovrAvatar2Button buttonMask;
        public CAPI.ovrAvatar2Touch touchMask;
        public float joystickX;
        public float joystickY;
        public float indexTrigger;
        public float handTrigger;
        public bool isActive;
        public bool isVisible;
    }

    public struct OvrAvatarInputControlState
    {
        public CAPI.ovrAvatar2ControllerType type;
        public OvrAvatarControllerState leftControllerState;
        public OvrAvatarControllerState rightControllerState;

        #region Native Conversions
        private CAPI.ovrAvatar2ControllerState ToNative(in OvrAvatarControllerState controller)
        {
            return new CAPI.ovrAvatar2ControllerState
            {
                buttonMask = controller.buttonMask,
                touchMask = controller.touchMask,
                joystickX = controller.joystickX,
                joystickY = controller.joystickY,
                indexTrigger = controller.indexTrigger,
                handTrigger = controller.handTrigger,
            };
        }

        internal CAPI.ovrAvatar2InputControlState ToNative()
        {
            return new CAPI.ovrAvatar2InputControlState
            {
                type = type,
                leftControllerState = ToNative(leftControllerState),
                rightControllerState = ToNative(rightControllerState),
            };
        }

        private void FromNative(in CAPI.ovrAvatar2ControllerState nativeController, ref OvrAvatarControllerState controller)
        {
            controller.buttonMask = nativeController.buttonMask;
            controller.touchMask = nativeController.touchMask;
            controller.joystickX = nativeController.joystickX;
            controller.joystickY = nativeController.joystickY;
            controller.indexTrigger = nativeController.indexTrigger;
            controller.handTrigger = nativeController.handTrigger;
        }

        internal void FromNative(ref CAPI.ovrAvatar2InputControlState native)
        {
            type = native.type;
            FromNative(native.leftControllerState, ref leftControllerState);
            FromNative(native.rightControllerState, ref rightControllerState);
        }
        #endregion
    }
}
