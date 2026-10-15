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
    ///     Base class for C# code to supply input tracking data for avatar entities
    /// </summary>
    public abstract class OvrAvatarInputTrackingProviderBase : OvrAvatarCallbackContextBase,
        IOvrAvatarInputTrackingDelegate
    {
        private OvrAvatarInputTrackingState _state;
        public OvrAvatarInputTrackingState State => _state;

        internal CAPI.ovrAvatar2InputTrackingContext Context { get; }

        public abstract bool GetInputTrackingState(out OvrAvatarInputTrackingState inputTrackingState);

        protected OvrAvatarInputTrackingProviderBase()
        {
            var context = new CAPI.ovrAvatar2InputTrackingContext();
            {
                context.context = new IntPtr(id);
                context.inputTrackingCallback = InputTrackingCallback;
            }
            Context = context;
        }

        [MonoPInvokeCallback(typeof(CAPI.InputTrackingCallback))]
        private static bool InputTrackingCallback(out CAPI.ovrAvatar2InputTrackingState inputTrackingState,
            IntPtr userContext)
        {
            try
            {
                var inputContext = GetInstance<OvrAvatarInputTrackingProviderBase>(userContext);
                if (inputContext != null &&
                    inputContext.GetInputTrackingState(out inputContext._state))
                {
                    inputTrackingState = inputContext._state.ToNative();
                    return true;
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
