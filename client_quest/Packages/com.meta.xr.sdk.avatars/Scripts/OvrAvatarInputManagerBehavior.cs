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
using UnityEngine.Events;

/**
 * @file OvrAvatarInputManagerBehavior.cs
 */

namespace Oculus.Avatar2
{
    /**
     * MonoBehaviour which holds a body tracking context so it can be referenced in the inspector.
     * @see OvrAvatarBodyTrackingContextBase
     */
    public abstract class OvrAvatarInputManagerBehavior : MonoBehaviour
    {
        /**
         * Get the input control implementation.
         * Subclasses must implement a getter for this property.
         * @see OvrAvatarInputControlProviderBase
         */
        public virtual OvrAvatarInputControlProviderBase? InputControlProvider => null;

        /**
         * Get the input tracking implementation.
         * Subclasses must implement a getter for this property.
         * @see OvrAvatarInputTrackingProviderBase
         */
        public abstract OvrAvatarInputTrackingProviderBase? InputTrackingProvider { get; }

        /**
         * Get the body tracking implementation.
         * Subclasses must implement a getter for this property.
         * @see OvrAvatarBodyTrackingContextBase
         */
        public abstract OvrAvatarBodyTrackingContextBase? BodyTrackingContext { get; }

        /**
         * Get the body tracking implementation.
         * Subclasses must implement a getter for this property.
         * @see OvrAvatarBodyTrackingContextBase
         */
        [Obsolete("TrackingContext was renamed to BodyTrackingContext", false)]
        public OvrAvatarBodyTrackingContextBase? TrackingContext => BodyTrackingContext;

        /**
         * Get the hand tracking implementation.
         * Subclasses must implement a getter for this property.
         * @see OvrAvatarHandTrackingPoseProviderBase
         */
        public abstract OvrAvatarHandTrackingPoseProviderBase? HandTrackingProvider { get; }

        /**
         * Classes implementing <see cref="OvrAvatarInputManagerBehavior" /> must trigger this event whenever
         * <see cref="BodyTrackingContext" /> is modified.
         */
        public BodyTrackingContextStateEvent OnBodyTrackingContextContextChanged { get; } =
            new();

        public class BodyTrackingContextStateEvent : UnityEvent<OvrAvatarInputManagerBehavior>
        {
        }
    }
}
