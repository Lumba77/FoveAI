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

namespace Oculus.Avatar2.Experimental
{
    public static class BehaviorLegsEvent
    {
        private const string VELOCITY_EVENT_NAME = "locomotion_prototype_MovementVelocity";
        private const string ANGLE_EVENT_NAME = "locomotion_prototype_MovementAngle";
        private const string TRACKING_BLEND_UPPER_EVENT_NAME = "locomotion_prototype_TrackingUpperBlend";
        private const string ROOT_ROTATION_OFFSET_EVENT_NAME = "locomotion_prototype_RootRotationOffset";
        private const string LEFT_FOOT_ANGLE_EVENT_NAME = "locomotion_prototype_TargetLeftStepAngle";
        private const string RIGHT_FOOT_ANGLE_EVENT_NAME = "locomotion_prototype_TargetRightStepAngle";
        private const string LEFT_FOOT_BLEND_EVENT_NAME = "locomotion_prototype_LeftStepBlend";
        private const string RIGHT_FOOT_BLEND_EVENT_NAME = "locomotion_prototype_RightStepBlend";
        private const string TURNING_PHASE_EVENT_NAME = "locomotion_prototype_FootStepInputPhase";

        private static readonly BehaviorSystem.EventController<float> _velocityEvent =
            BehaviorSystem.EventController<float>.Register(VELOCITY_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _angleEvent =
            BehaviorSystem.EventController<float>.Register(ANGLE_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _trackingBlendUpperEvent =
            BehaviorSystem.EventController<float>.Register(TRACKING_BLEND_UPPER_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _rootRotationOffsetEvent =
            BehaviorSystem.EventController<float>.Register(ROOT_ROTATION_OFFSET_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _leftFootAngleEvent =
            BehaviorSystem.EventController<float>.Register(LEFT_FOOT_ANGLE_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _rightFootAngleEvent =
            BehaviorSystem.EventController<float>.Register(RIGHT_FOOT_ANGLE_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _leftFootBlendEvent =
            BehaviorSystem.EventController<float>.Register(LEFT_FOOT_BLEND_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _rightFootBlendEvent =
            BehaviorSystem.EventController<float>.Register(RIGHT_FOOT_BLEND_EVENT_NAME);

        private static readonly BehaviorSystem.EventController<float> _turningPhaseEvent =
            BehaviorSystem.EventController<float>.Register(TURNING_PHASE_EVENT_NAME);

        public static void Send(OvrAvatarEntity entity, EventParam param)
        {
            entity.SendEvent(_velocityEvent, param.Velocity);
            entity.SendEvent(_angleEvent, param.Angle);
            entity.SendEvent(_trackingBlendUpperEvent, param.TrackingBlendUpper);
            entity.SendEvent(_rootRotationOffsetEvent, param.RootRotationOffset);
            entity.SendEvent(_leftFootAngleEvent, param.LeftFootAngle);
            entity.SendEvent(_rightFootAngleEvent, param.RightFootAngle);
            entity.SendEvent(_leftFootBlendEvent, param.LeftFootBlend);
            entity.SendEvent(_rightFootBlendEvent, param.RightFootBlend);
            entity.SendEvent(_turningPhaseEvent, param.TurningPhase);
        }

        /// <summary>
        /// Encapsulate parameters needed for legs event
        /// </summary>
        public struct EventParam
        {
            public float Velocity;
            public float Angle;
            public float TrackingBlendUpper;
            public float RootRotationOffset;
            public float LeftFootAngle;
            public float RightFootAngle;
            public float LeftFootBlend;
            public float RightFootBlend;
            public float TurningPhase;
        }
    }
}
