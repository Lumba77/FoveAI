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

using Oculus.Avatar2;
using System.Collections.Generic;
using UnityEngine;

namespace Oculus.Avatar2
{
    /// <summary>
    /// EyePose behavior that enables eye tracking through OVRPlugin.
    /// </summary>
    public class OvrAvatarEyeTrackingBehaviorOvrPlugin : OvrAvatarEyePoseBehavior
    {
        private OvrAvatarEyePoseProviderBase _eyePoseProvider;
        private static readonly CAPI.ovrAvatar2Platform[] s_eyeTrackingEnabledPlatforms = { CAPI.ovrAvatar2Platform.QuestPro, CAPI.ovrAvatar2Platform.PC };

        public override OvrAvatarEyePoseProviderBase EyePoseProvider
        {
            get
            {
                InitializeEyePoseProvider();

                return _eyePoseProvider;
            }
        }

        private void InitializeEyePoseProvider()
        {
            if (_eyePoseProvider != null || OvrAvatarManager.Instance == null)
            {
                return;
            }

            // Check for unsupported Eye Tracking platforms
            if (!s_eyeTrackingEnabledPlatforms.Contains(OvrAvatarManager.Instance.Platform))
            {
                return;
            }

            // check for Link connection
            if (OvrAvatarManager.Instance.Platform == CAPI.ovrAvatar2Platform.PC && !OvrAvatarUtility.IsHeadsetActive())
            {
                return;
            }

            OvrAvatarManager.Instance.RequestEyeTrackingPermission();

            if (OvrAvatarManager.Instance.OvrPluginEyePoseProvider != null)
            {
                OvrAvatarLog.LogInfo("Eye tracking service available");
                _eyePoseProvider = OvrAvatarManager.Instance.OvrPluginEyePoseProvider;
            }
            else
            {
                OvrAvatarLog.LogWarning("Eye tracking service unavailable");
            }
        }
    }
}
