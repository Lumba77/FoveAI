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
using AOT;

namespace Oculus.Avatar2
{
    /// <summary>
    /// Base class for C# code to supply face pose data for avatar entities
    /// </summary>
    public abstract class OvrAvatarFacePoseProviderBase : OvrAvatarCallbackContextBase
    {
        private readonly OvrAvatarFacePose _facePose = new OvrAvatarFacePose();
        internal CAPI.ovrAvatar2FacePoseProvider Provider { get; }

        protected OvrAvatarFacePoseProviderBase()
        {
            var provider = new CAPI.ovrAvatar2FacePoseProvider
            {
                provider = new IntPtr(id),
                facePoseCallback = FacePoseCallback
            };
            Provider = provider;
        }

        protected abstract bool GetFacePose(OvrAvatarFacePose facePose);

        [MonoPInvokeCallback(typeof(CAPI.FacePoseCallback))]
        private static bool FacePoseCallback(out CAPI.ovrAvatar2FacePose facePose, IntPtr userContext)
        {
            try
            {
                var provider = GetInstance<OvrAvatarFacePoseProviderBase>(userContext);
                if (provider != null)
                {
                    if (provider.GetFacePose(provider._facePose))
                    {
                        facePose = provider._facePose.ToNative();
                        return true;
                    }

                    facePose = OvrAvatarFacePose.GenerateEmptyNativePose();
                    return false;
                }
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogError(e.ToString());
            }

            facePose = default;
            return false;
        }
    }
}
