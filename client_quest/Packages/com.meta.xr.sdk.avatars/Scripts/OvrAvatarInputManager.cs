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
    /**
     * Base class for setting tracking input on an avatar entity.
     * Allows you to select which components to use for tracking in
     * the Unity Editor.
     * @see OvrAvatarBodyTrackingBehavior
     */
    public abstract class OvrAvatarInputManager : OvrAvatarInputManagerBehavior
    {
        [SerializeField, Tooltip("Selects the body tracking service")]
        protected OvrAvatarBodyTrackingMode _bodyTrackingMode = OvrAvatarBodyTrackingMode.None;
        protected OvrAvatarBodyTrackingMode _activeBodyTrackingMode = OvrAvatarBodyTrackingMode.None;

        [SerializeField, Tooltip("This adds one frame of latency to the body solver. In exchange saves some main thread CPU time")]
        [HideInInspector]
        [Obsolete("Async body solver no longer supported", false)]
        protected bool _useAsyncBodySolver;

        [SerializeField]
        [HideInInspector]
        [Obsolete("Hip lock no longer supported", false)]
        protected bool _enableHipLock;

        protected OvrAvatarInputControlProviderBase? _inputControlProvider;
        protected OvrAvatarInputTrackingProviderBase? _inputTrackingProvider;
        protected OvrAvatarHandTrackingPoseProviderBase? _handTrackingProvider;
        protected OvrAvatarBodyTrackingContextBase? _bodyTrackingContext;

        protected bool _trackingInitialized = false;

        /**
         * The current input control implementation. Gets the tracking information from sensors. Accessing the input
         * control context also initializes body tracking.
         * @see OvrAvatarInputControlProviderBase
         */
        public override OvrAvatarInputControlProviderBase? InputControlProvider
        {
            get
            {
                InitializeBodyTracking();

                return _inputControlProvider;
            }
        }

        /**
         * The current input tracking implementation. Gets the tracking information from sensors. Accessing the input
         * tracking context also initializes body tracking.
         * @see OvrAvatarInputTrackingProviderBase
         */
        public override OvrAvatarInputTrackingProviderBase? InputTrackingProvider
        {
            get
            {
                InitializeBodyTracking();

                InitializeInputTrackingProvider();

                return _inputTrackingProvider;
            }
        }

        /**
         * The current body tracking implementation.
         * Gets the body tracking information from sensors and applies it to the skeleton.
         * Accessing the body tracking context also initializes body tracking.
         * @see OvrAvatarBodyTrackingContextBase
         */
        public override OvrAvatarBodyTrackingContextBase? BodyTrackingContext
        {
            get
            {
                InitializeBodyTracking();
                return _bodyTrackingContext;
            }
        }

        /**
         * The current hand tracking implementation. Gets the tracking information. Accessing the hand
         * tracking context also initializes body tracking.
         * @see OvrAvatarHandTrackingPoseProviderBase
         */
        public override OvrAvatarHandTrackingPoseProviderBase? HandTrackingProvider
        {
            get
            {
                InitializeBodyTracking();

                InitializeHandTrackingProvider();

                return _handTrackingProvider;
            }
        }

        private void InitializeInputTrackingProvider()
        {
            if (!OvrAvatarManager.initialized || _inputTrackingProvider != null || OvrAvatarManager.Instance == null)
            {
                return;
            }

            if (OvrAvatarManager.Instance.OvrPluginInputTrackingProvider != null)
            {
                OvrAvatarLog.LogInfo("Input tracking service available");
                _inputTrackingProvider = OvrAvatarManager.Instance.OvrPluginInputTrackingProvider;
            }
            else
            {
                OvrAvatarLog.LogWarning("Input tracking service unavailable");
            }
        }

        protected void InitializeBodyTracking()
        {
            if (!OvrAvatarManager.initialized || ((_activeBodyTrackingMode == _bodyTrackingMode) && _trackingInitialized))
            {
                return;
            }

            _trackingInitialized = true;

            if (_bodyTrackingMode == OvrAvatarBodyTrackingMode.Standalone)
            {
                OvrAvatarLog.LogError("OvrAvatarBodyTrackingMode.Standalone is deprecated, please use OvrAvatarBodyTrackingMode.None instead and set the InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance.");
                _bodyTrackingContext = null;
            }
            else if (_bodyTrackingMode == OvrAvatarBodyTrackingMode.StandaloneLegacyUpperBody)
            {
                OvrAvatarLog.LogError("OvrAvatarBodyTrackingMode.StandaloneLegacyUpperBody is deprecated, please use OvrAvatarBodyTrackingMode.None instead and set the InputTrackingProvider, InputControlProvider, and HandTrackingProvider properties of the OvrAvatarInputManagerBehavior MonoBehavior on the OvrAvatarEntity prefab/instance.");
                _bodyTrackingContext = null;
            }
            else if (_bodyTrackingMode == OvrAvatarBodyTrackingMode.None)
            {
                _bodyTrackingContext = null;
            }

            _activeBodyTrackingMode = _bodyTrackingMode;
            OnTrackingInitialized();

            OnBodyTrackingContextContextChanged?.Invoke(this);
        }

        private void InitializeHandTrackingProvider()
        {
            if (!OvrAvatarManager.initialized || OvrAvatarManager.Instance == null)
            {
                return;
            }

            if (_handTrackingProvider == null)
            {
                if (OvrAvatarManager.Instance.OvrPluginHandTrackingPoseProvider != null)
                {
                    OvrAvatarLog.LogInfo("Hand tracking service available");
                    _handTrackingProvider = OvrAvatarManager.Instance.OvrPluginHandTrackingPoseProvider;
                }
                else
                {
                    OvrAvatarLog.LogWarning("Hand tracking service unavailable");
                }
            }
        }

        /**
         * Called from *InitializeTracking* to provide a way
         * for subclasses to creation and do platform specific tracking enablement.
         * The default implementation does nothing.
         */
        protected virtual void OnTrackingInitialized()
        {
        }

#if UNITY_EDITOR
        // This ensures that the tracking is reinitialized whenever the body tracking mode is changed in the Inspector.
        private void OnValidate()
        {
            if (Application.isPlaying) {
                InitializeBodyTracking();
            }
        }
#endif

        protected void OnDestroy()
        {
            OnDestroyCalled();

            _bodyTrackingContext?.Dispose();
            _bodyTrackingContext = null;
        }

        /**
         * Called from *OnDestroy* to provide a way
         * for subclasses to intercept destruction and
         * do their own cleanup.
         * The default implementation does nothing.
         */
        protected virtual void OnDestroyCalled()
        {
        }

        /**
         * Returns the position and orientation of the headset
         * and controllers in T-Pose.
         * Useful for initial calibration or testing.
         * @see CAPI.ovrAvatar2InputTransforms
         */
        protected OvrAvatarInputTrackingState GetTPose()
        {
            var transforms = new OvrAvatarInputTrackingState
            {
                headsetActive = true,
                leftControllerActive = true,
                rightControllerActive = true,
                leftControllerVisible = true,
                rightControllerVisible = true,
                headset =
                {
                    position = new CAPI.ovrAvatar2Vector3f() {x = 0, y = 1.6169891f, z = 0},
                    orientation = new CAPI.ovrAvatar2Quatf() {x = 0, y = 0, z = 0, w = -1f},
                    scale = new CAPI.ovrAvatar2Vector3f() {x = 1f, y = 1f, z = 1f}
                },
                leftController =
                {
                    position = new CAPI.ovrAvatar2Vector3f() {x = -0.79f, y = 1.37f, z = 0},
                    orientation =
                        new CAPI.ovrAvatar2Quatf() {x = 0, y = -0.70710678118f, z = 0, w = -0.70710678118f},
                    scale = new CAPI.ovrAvatar2Vector3f() {x = 1f, y = 1f, z = 1f}
                },
                rightController =
                {
                    position = new CAPI.ovrAvatar2Vector3f() {x = 0.79f, y = 1.37f, z = 0},
                    orientation = new CAPI.ovrAvatar2Quatf() {x = 0, y = 0.70710678118f, z = 0, w = -0.70710678118f},
                    scale = new CAPI.ovrAvatar2Vector3f() {x = 1f, y = 1f, z = 1f}
                }
            };

            return transforms;
        }
    }

    /**
     * Represents the modes used to provide body tracking information to AvatarSDK. By default
     * the standalone tracking service should be used.
     */
    public enum OvrAvatarBodyTrackingMode
    {
        // No tracking will be forwarded, if used.
        None = 0,

        // Represents the legacy standalone tracking service (BodyAPI), but solving just the hand pose (BodySolver will solve the body instead).
        Standalone = 1,


        // Represents the deprecated standalone tracking service (BodyAPI), please migrate to Standalone instead.
        StandaloneLegacyUpperBody = 3,

    };
}
