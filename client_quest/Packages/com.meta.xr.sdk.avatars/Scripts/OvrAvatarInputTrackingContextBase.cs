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

using AOT;
using System;

namespace Oculus.Avatar2
{
    public abstract class OvrAvatarInputTrackingContextBase : OvrAvatarCallbackContextBase
    {
        private OvrAvatarInputTrackingState _inputTrackingState = new OvrAvatarInputTrackingState();
        internal CAPI.ovrAvatar2InputTrackingContext Context { get; }

        protected OvrAvatarInputTrackingContextBase()
        {
            var context = new CAPI.ovrAvatar2InputTrackingContext
            {
                context = new IntPtr(id),
                inputTrackingCallback = InputTrackingCallback,
            };
            Context = context;
        }

        protected abstract bool GetInputTrackingState(out OvrAvatarInputTrackingState inputTrackingState);

        [MonoPInvokeCallback(typeof(CAPI.InputTrackingCallback))]
        private static bool InputTrackingCallback(out CAPI.ovrAvatar2InputTrackingState inputTrackingState, IntPtr userContext)
        {
            try
            {
                var context = GetInstance<OvrAvatarInputTrackingContextBase>(userContext);
                if (context != null)
                {
                    if (context.GetInputTrackingState(out context._inputTrackingState))
                    {
                        inputTrackingState = context._inputTrackingState.ToNative();
                        return true;
                    }
                }
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogError(e.ToString());
            }

            inputTrackingState = default;
            return false;
        }
    }
}
