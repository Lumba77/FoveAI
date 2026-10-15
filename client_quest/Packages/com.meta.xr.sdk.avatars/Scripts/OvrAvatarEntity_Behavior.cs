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

using Oculus.Avatar2.Experimental;
using System.Collections.Generic;
using UnityEngine;

namespace Oculus.Avatar2
{
    public partial class OvrAvatarEntity
    {
        private static readonly HashSet<string> _loadedZipFiles = new HashSet<string>();

        public bool BehaviorSystemEnabled { get; private set; } = false;
        public string MainBehaviorName { get; private set; }

        /// <summary>
        /// Load specific behavior zip file
        /// </summary>
        /// <param name="zipPath">The full path of the zip file</param>
        /// <returns>True if load is successful. False otherwise.</returns>
        public bool LoadBehaviorZip(string zipPath)
        {
            if (_loadedZipFiles.Contains(zipPath))
            {
                return true;
            }

            if (BehaviorSystem.LoadBehaviorZip(this, zipPath))
            {
                _loadedZipFiles.Add(zipPath);
                return true;
            }

            return false;
        }

        public bool BehaviorSystemExists()
        {
            return HasAllFeatures(BehaviorSystem.BehaviorSystemFeatureFlag);
        }

        public bool EnableBehaviorSystem(bool enableSystem)
        {
            if (enableSystem == BehaviorSystemEnabled ||
                BehaviorSystem.EnableBehaviorSystem(this, enableSystem))
            {
                BehaviorSystemEnabled = enableSystem;
                return true;
            }
            return false;
        }

        public bool SetMainBehavior(string behaviorName)
        {
            if (MainBehaviorName == behaviorName ||
                BehaviorSystem.SetMainBehavior(this, behaviorName))
            {
                MainBehaviorName = behaviorName;
                return true;
            }
            return false;
        }

        public bool SetOutputPose(string outputPoseName, CAPI.ovrAvatar2EntityViewFlags viewFlags)
        {
            return BehaviorSystem.SetOutputPose(this, viewFlags, outputPoseName);
        }

        public bool SendEvent(BehaviorSystem.EventController ev)
        {
            return BehaviorSystem.SendEvent(this, ev);
        }

        public bool SendEvent<TPrimitivePayload>(BehaviorSystem.EventController<TPrimitivePayload> ev,
            TPrimitivePayload payload)
            where TPrimitivePayload : unmanaged
        {
            return BehaviorSystem.SendEvent(this, ev, payload);
        }

        public bool SendEventWithStringPayload(BehaviorSystem.BaseEventController ev, string stringPayload)
        {
            return BehaviorSystem.SendEventWithStringPayload(this, ev, stringPayload);
        }

        public bool SendEventWithFloatPayload(BehaviorSystem.BaseEventController ev, float floatPayload)
        {
            return BehaviorSystem.SendEventWithFloatPayload(this, ev, floatPayload);
        }

        public bool SendEventWithOrientationPayload(BehaviorSystem.BaseEventController ev, in Quaternion orientationPayload)
        {
            return BehaviorSystem.SendEventWithOrientationPayload(this, ev, in orientationPayload);
        }

        public bool SendEventWithPositionPayload(BehaviorSystem.BaseEventController ev, in Vector3 positionPayload)
        {
            return BehaviorSystem.SendEventWithPositionPayload(this, ev, in positionPayload);
        }

        public bool SendEventWithQuatfPayload(BehaviorSystem.BaseEventController ev, in CAPI.ovrAvatar2Quatf quatPayload)
        {
            return BehaviorSystem.SendEventWithQuatfPayload(this, ev, in quatPayload);
        }

        public bool SendEventWithVec3fPayload(BehaviorSystem.BaseEventController ev, in CAPI.ovrAvatar2Vector3f vec3fPayload)
        {
            return BehaviorSystem.SendEventWithVec3fPayload(this, ev, in vec3fPayload);
        }

        public bool SendEventWithTransformPayload(BehaviorSystem.BaseEventController ev, in CAPI.ovrAvatar2Transform transformPayload)
        {
            return BehaviorSystem.SendEventWithTransformPayload(this, ev, in transformPayload);
        }

        private void TeardownEntityBehavior()
        {
            MainBehaviorName = null;
        }

        internal static void TeardownEntityAnimation()
        {
            _loadedZipFiles.Clear();
        }
    }
}
