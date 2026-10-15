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

using AOT;
using System;

namespace Oculus.Avatar2
{
    ///
    /// C# wrapper around OvrBody stand alone solver
    ///
    [Obsolete("Please set the InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance instead. Additionally set the BodyTrackingContext property of OvrAvatarInputManagerBehavior to null.", false)]
    public sealed class OvrAvatarBodyTrackingContext : OvrAvatarBodyTrackingContextBase, IOvrAvatarNativeBodyTracking
    {
        private const string logScope = "BodyTrackingContext";

        private IntPtr _context;
        private IOvrAvatarHandTrackingDelegate _handTrackingDelegate;
        private IOvrAvatarInputTrackingDelegate _inputTrackingDelegate;
        private IOvrAvatarInputControlDelegate _inputControlDelegate;
        private readonly CAPI.ovrAvatar2TrackingDataContext? _callbacks;
        private readonly OvrAvatarTrackingHandsState _handState = new OvrAvatarTrackingHandsState();
        private OvrAvatarInputControlState _inputControlState = new OvrAvatarInputControlState();
        private OvrAvatarInputTrackingState _inputTrackingState = new OvrAvatarInputTrackingState();
        private readonly CAPI.ovrAvatar2TrackingDataContextNative _nativeContext;

        CAPI.ovrAvatar2TrackingDataContextNative IOvrAvatarNativeBodyTracking.NativeDataContext
        {
            get => _nativeContext;
        }

        public IntPtr BodyTrackingContextPtr => _context;

        public IOvrAvatarHandTrackingDelegate HandTrackingDelegate
        {
            get => _handTrackingDelegate;
            set
            {
                _handTrackingDelegate = value;
                OvrAvatarLog.LogError("OvrAvatarBodyTrackingContext is deprecated. Please set the HandTrackingProvider property of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance instead.");
            }
        }

        public IOvrAvatarInputTrackingDelegate InputTrackingDelegate
        {
            get => _inputTrackingDelegate;
            set
            {
                _inputTrackingDelegate = value;
                OvrAvatarLog.LogError("OvrAvatarBodyTrackingContext is deprecated. Please set the InputTrackingProvider property of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance instead.");
            }
        }

        public OvrAvatarInputTrackingState InputTrackingState { get => _inputTrackingState; }

        public IOvrAvatarInputControlDelegate InputControlDelegate
        {
            get => _inputControlDelegate;
            set
            {
                _inputControlDelegate = value;
                OvrAvatarLog.LogError("OvrAvatarBodyTrackingContext is deprecated. Please set the InputControlProvider property of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance instead.");
            }
        }

        public OvrAvatarInputControlState InputControlState { get => _inputControlState; }

        public static OvrAvatarBodyTrackingContext Create(bool runAsync, bool enableHipLock, bool enableHandsOnly = false, bool enableLegacyUpperBody = false)
        {
            OvrAvatarLog.LogError("OvrAvatarBodyTrackingContext is deprecated. Please set the InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance instead. Additionally set the BodyTrackingContext property of OvrAvatarInputManagerBehavior to null.");
            return null;
        }

        public void SetTransformOffset(CAPI.ovrAvatar2BodyMarkerTypes type, ref CAPI.ovrAvatar2Transform offset)
        {
        }

        /// Triggers a restart of body tracking, clearing out any information from previous frames.
        public bool RestartTracking()
        {
            return true;
        }

        private void ReleaseUnmanagedResources()
        {
            _context = IntPtr.Zero;
        }

        protected override void Dispose(bool disposing)
        {
            ReleaseUnmanagedResources();
            base.Dispose(disposing);
        }

        [MonoPInvokeCallback(typeof(CAPI.HandStateCallback))]
        private static bool HandTrackingCallback(out CAPI.ovrAvatar2HandTrackingState handsState, IntPtr context)
        {
            try
            {
                var bodyContext = GetInstance<OvrAvatarBodyTrackingContext>(context);
                if (bodyContext?._handTrackingDelegate != null &&
                    bodyContext._handTrackingDelegate.GetHandData(bodyContext._handState))
                {
                    handsState = bodyContext._handState.ToNative();
                    return true;
                }
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogError(e.ToString());
            }

            handsState = default;
            return false;
        }


        [MonoPInvokeCallback(typeof(CAPI.InputTrackingCallback))]
        private static bool InputTrackingCallback(out CAPI.ovrAvatar2InputTrackingState trackingState, IntPtr userContext)
        {
            try
            {
                var bodyContext = GetInstance<OvrAvatarBodyTrackingContext>(userContext);
                if (bodyContext?._inputTrackingDelegate != null &&
                    bodyContext._inputTrackingDelegate.GetInputTrackingState(out bodyContext._inputTrackingState))
                {
                    trackingState = bodyContext._inputTrackingState.ToNative();
                    return true;
                }
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogError(e.ToString());
            }

            trackingState = default;
            return false;
        }

        [MonoPInvokeCallback(typeof(CAPI.InputControlCallback))]
        private static bool InputControlCallback(out CAPI.ovrAvatar2InputControlState controlState, IntPtr userContext)
        {
            try
            {
                var bodyContext = GetInstance<OvrAvatarBodyTrackingContext>(userContext);
                if (bodyContext?._inputControlDelegate != null &&
                    bodyContext._inputControlDelegate.GetInputControlState(out bodyContext._inputControlState))
                {
                    controlState = bodyContext._inputControlState.ToNative();
                    return true;
                }
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogError(e.ToString());
            }

            controlState = default;
            return false;
        }

        // Provides a Body State by calling into the native Body Tracking implementation
        protected override bool GetBodyState(OvrAvatarTrackingBodyState bodyState)
        {
            if (_callbacks.HasValue)
            {
                var cb = _callbacks.Value;
                if (cb.bodyStateCallback(out var nativeBodyState, cb.context))
                {
                    bodyState.FromNative(ref nativeBodyState);
                    return true;
                }
            }
            return false;
        }

        // Provides a Tracking Skeleton by calling into the native Body Tracking implementation
        protected override bool GetBodySkeleton(ref OvrAvatarTrackingSkeleton skeleton)
        {
            if (_callbacks.HasValue)
            {
                var cb = _callbacks.Value;
                if (cb.bodySkeletonCallback != null)
                {
                    var native = skeleton.GetNative();
                    var result = cb.bodySkeletonCallback(ref native, cb.context);
                    skeleton.CopyFromNative(ref native);
                    return result;
                }

            }

            return false;
        }

        // Provides a Body Pose by calling into the native Body Tracking implementation
        protected override bool GetBodyPose(ref OvrAvatarTrackingPose pose)
        {
            if (_callbacks.HasValue)
            {
                var cb = _callbacks.Value;
                if (cb.bodyPoseCallback != null)
                {
                    var native = pose.GetNative();
                    var result = cb.bodyPoseCallback(ref native, cb.context);
                    pose.CopyFromNative(ref native);
                    return result;
                }
            }

            return false;
        }
    }
}
