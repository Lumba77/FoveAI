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

namespace Oculus.Avatar2
{
    /// <summary>
    ///    Hand tracking provider that allows to forward input tracking through a managed delegate
    /// </summary>
    public class OvrAvatarHandTrackingDelegatedProvider : OvrAvatarHandTrackingPoseProviderBase
    {
        private readonly IOvrAvatarHandTrackingDelegate _handTrackingDelegate;

        public OvrAvatarHandTrackingDelegatedProvider(IOvrAvatarHandTrackingDelegate forwardedHandTrackingDelegate)
        {
            _handTrackingDelegate = forwardedHandTrackingDelegate;
        }

        public override bool GetHandData(OvrAvatarTrackingHandsState handTrackingState)
        {
            {
                if (_handTrackingDelegate == null)
                {
                    handTrackingState = default;
                    return false;
                }

                return _handTrackingDelegate.GetHandData(handTrackingState);
            }
        }
    }
}
