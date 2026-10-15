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

using System;
using System.IO;
using System.Runtime.InteropServices;

using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;
using UnityEngine;
using UnityEngine.Assertions;
using UnityEngine.Networking;

using STANDARD_CAPI = Oculus.Avatar2.CAPI;
using EXPERIMENTAL_CAPI = Oculus.Avatar2.Experimental.CAPI;

namespace Oculus.Avatar2.Experimental
{
    public static partial class BehaviorSystem
    {
        private const string logScope = "behaviorSystem";

        public static STANDARD_CAPI.ovrAvatar2EntityFeatures BehaviorSystemFeatureFlag { get; } =
          (STANDARD_CAPI.ovrAvatar2EntityFeatures)ExperimentalEntityFeatureFlag.BehaviorSystem;

        public static bool EnableBehaviorSystem(OvrAvatarEntity avatarEntity, bool enabled)
        {
            return EXPERIMENTAL_CAPI
              .ovrAvatar2Behavior_SetBehaviorSystemEnabled(avatarEntity.internalEntityId, enabled)
              .EnsureSuccess("ovrAvatar2Behavior_SetBehaviorSystemEnabled");
        }

        public static bool SetMainBehavior(OvrAvatarEntity avatarEntity, string behaviorName)
        {
            return EXPERIMENTAL_CAPI.ovrAvatar2Behavior_SetMainBehavior(avatarEntity.internalEntityId, behaviorName)
              .EnsureSuccess("ovrAvatar2Behavior_SetMainBehavior");
        }

        public static bool SetOutputPose(OvrAvatarEntity avatarEntity,
          STANDARD_CAPI.ovrAvatar2EntityViewFlags viewFlags,
          string outputPoseName)
        {
            return EXPERIMENTAL_CAPI
              .ovrAvatar2Behavior_SetOutputPose(avatarEntity.internalEntityId, viewFlags, outputPoseName)
              .EnsureSuccess();
        }

        public static bool UnloadBehavior(OvrAvatarEntity avatarEntity, string path)
        {
            var name = Path.GetFileName(path);
            // TODO: The `OvrAvatar2Entity_UnloadUri` command does currently not work as expected.
            return name != null && STANDARD_CAPI.OvrAvatar2Entity_UnloadUri(avatarEntity.internalEntityId, name);
        }

        // TODO: To be removed after CAPI zip loading limitation is addressed
        public static bool LoadBehaviorZip(OvrAvatarEntity avatarEntity, string path)
        {
            var loadingRequest = UnityWebRequest.Get(path);
            loadingRequest.SendWebRequest();

            // TODO: This is not how the async request should be handled.
            while (!loadingRequest.isDone)
            {
                if (loadingRequest.result != UnityWebRequest.Result.InProgress
                    && loadingRequest.result != UnityWebRequest.Result.Success)
                {
                    break;
                }
            }

            if (loadingRequest.result != UnityWebRequest.Result.Success)
            {
                OvrAvatarLog.LogError($"Loading of behavior zip from path '{path}' failed. {loadingRequest.error}");
                return false;
            }

            Assert.IsTrue(loadingRequest.isDone);
            var data = loadingRequest.downloadHandler.data;
            var name = Path.GetFileName(path);
            var handle = GCHandle.Alloc(data, GCHandleType.Pinned);
            var res = STANDARD_CAPI.OvrAvatar2Entity_LoadMemory(
              avatarEntity.internalEntityId,
              handle.AddrOfPinnedObject(),
              (uint)data.Length, name,
              out _);
            handle.Free();
            return res.IsSuccess();
        }

        private static bool CheckEventController(OvrAvatarEntity entity, BaseEventController eventController)
        {
            bool result = eventController.IsValid;
            if (!result)
            {
                OvrAvatarLog.LogError($"Attempted to `SendEvent` using invalid controller {eventController.Name}", logScope, entity);
            }
            return result;
        }

        public static bool SendEvent(OvrAvatarEntity avatarEntity, EventController eventController, bool suppressNotFoundWarning = false)
        {
            return CheckEventController(avatarEntity, eventController) &&
                   CAPI.OvrAvatar2Entity_SendEvent(avatarEntity.internalEntityId, eventController.Definition.eventId, suppressNotFoundWarning);
        }

        public static bool SendEvent<TPrimitivePayload>(OvrAvatarEntity entity, EventController<TPrimitivePayload> eventController,
            TPrimitivePayload payload, bool suppressNotFoundWarning = false)
            where TPrimitivePayload : unmanaged
        {
            unsafe
            {
                return SendEvent(entity, eventController, &payload, suppressNotFoundWarning);
            }
        }

        public static unsafe bool SendEvent<TPrimitivePayload>(OvrAvatarEntity entity, EventController<TPrimitivePayload> ev,
            TPrimitivePayload* payload, bool suppressNotFoundWarning = false)
            where TPrimitivePayload : unmanaged
        {
            Debug.Assert(typeof(TPrimitivePayload).IsPrimitive, "Attempted to send non primitive payload!");

            var dataView =
                new CAPI.ovrAvatar2DataView(payload, (UIntPtr)UnsafeUtility.SizeOf<TPrimitivePayload>());
            return CAPI.OvrAvatar2Entity_SendEventWithPayload(entity.internalEntityId,
                in ev.Definition,
                in dataView,
                suppressNotFoundWarning);
        }

        // TODO: This is currently untested
        public static bool SendEventWithStringPayload(OvrAvatarEntity avatarEntity, BaseEventController eventController,
            string stringPayload, bool suppressNotFoundWarning = false)
        {
#if false
            unsafe
            {
                fixed (char* payload = stringPayload)
                {
                    var dataView =
                        new CAPI.ovrAvatar2DataView((void*)payload, (UIntPtr)stringPayload.Length);
                    var eventDefinition = ev.Definition;
                    return CAPI.OvrAvatar2Entity_SendEventWithPayload(avatarEntity.internalEntityId,
                        in ev.Definition,
                        in dataView,
                        suppressNotFoundWarning);
                }
            }
#else

            return CheckEventController(avatarEntity, eventController) &&
                   EXPERIMENTAL_CAPI.OvrAvatar2Entity_Experimental_SendEventWithStringPayload(avatarEntity.internalEntityId,
                    eventController.Definition.eventId, stringPayload, suppressNotFoundWarning);
#endif
        }

        public static bool SendEventWithFloatPayload(OvrAvatarEntity avatarEntity, BaseEventController eventController,
            float floatPayload, bool suppressNotFoundWarning = false)
        {
            return CheckEventController(avatarEntity, eventController) &&
                   EXPERIMENTAL_CAPI.OvrAvatar2Entity_Experimental_SendEventWithFloatPayload(
                    avatarEntity.internalEntityId, eventController.Definition.eventId,
                    floatPayload, suppressNotFoundWarning);
        }

        public static bool SendEventWithOrientationPayload(OvrAvatarEntity avatarEntity, BaseEventController eventController,
            in Quaternion orientationPayload, bool suppressNotFoundWarning = false)
        {
            return CheckEventController(avatarEntity, eventController) &&
                   EXPERIMENTAL_CAPI.OvrAvatar2Entity_Experimental_SendEventWithOrientationPayload(
                    avatarEntity.internalEntityId, eventController.Definition.eventId,
                    in orientationPayload, suppressNotFoundWarning);
        }

        public static bool SendEventWithPositionPayload(OvrAvatarEntity avatarEntity, BaseEventController eventController,
            in Vector3 positionPayload, bool suppressNotFoundWarning = false)
        {
            return CheckEventController(avatarEntity, eventController) &&
                   EXPERIMENTAL_CAPI.OvrAvatar2Entity_Experimental_SendEventWithPositionPayload(
                    avatarEntity.internalEntityId, eventController.Definition.eventId,
                    in positionPayload, suppressNotFoundWarning);
        }

        public static bool SendEventWithQuatfPayload(OvrAvatarEntity avatarEntity, BaseEventController eventController,
          in Avatar2.CAPI.ovrAvatar2Quatf quatPayload, bool suppressNotFoundWarning = false)
        {
            return CheckEventController(avatarEntity, eventController) &&
                   EXPERIMENTAL_CAPI.ovrAvatar2Entity_Experimental_SendEventWithQuatfPayload(
                    avatarEntity.internalEntityId, eventController.Definition.eventId,
                    in quatPayload, suppressNotFoundWarning);
        }

        public static bool SendEventWithVec3fPayload(OvrAvatarEntity avatarEntity, BaseEventController eventController,
          in Avatar2.CAPI.ovrAvatar2Vector3f vec3fPayload, bool suppressNotFoundWarning = false)
        {
            return CheckEventController(avatarEntity, eventController) &&
                   EXPERIMENTAL_CAPI.OvrAvatar2Entity_Experimental_SendEventWithVec3fPayload(
                avatarEntity.internalEntityId, eventController.Definition.eventId,
                in vec3fPayload, suppressNotFoundWarning);
        }

        public static bool SendEventWithTransformPayload(OvrAvatarEntity avatarEntity, BaseEventController eventController,
            in Avatar2.CAPI.ovrAvatar2Transform transformPayload, bool suppressNotFoundWarning = false)
        {
            return CheckEventController(avatarEntity, eventController) &&
                   EXPERIMENTAL_CAPI.OvrAvatar2Entity_Experimental_SendEventWithTransformPayload(
                    avatarEntity.internalEntityId, eventController.Definition.eventId,
                    in transformPayload, suppressNotFoundWarning);
        }

        internal static EXPERIMENTAL_CAPI.ovrAvatar2EventId GetEventId(string eventName)
        {
            using var eventNameView = new StringHelpers.StringViewAllocHandle(eventName, Allocator.Temp);
            if (!EXPERIMENTAL_CAPI.OvrAvatar2Event_GetEventId(eventNameView.StringView, out var eventId))
            {
                OvrAvatarLog.LogError($"Unable to query eventId for eventName {eventName}", logScope);
                return CAPI.ovrAvatar2EventId.Invalid;
            }

            return eventId;
        }

        public static CAPI.ovrAvatar2EventDefinition[] GetEventDefinitions(string behaviorName)
        {
            unsafe
            {
                var behaviorNameCapi = new StringHelpers.StringViewAllocHandle(behaviorName, Allocator.Temp);
                uint numDefinitions = 0;
                var result =
                    CAPI.ovrAvatarXBehavior_GetEventDefinitions(behaviorNameCapi.StringView, null, 0, &numDefinitions);
                if (result != Avatar2.CAPI.ovrAvatar2Result.BufferTooSmall)
                {
                    return result.EnsureSuccess("OvrAvatarXBehavior_GetEventDefinitions", logScope)
                        ? Array.Empty<CAPI.ovrAvatar2EventDefinition>()
                        : null;
                }

                var definitions = new CAPI.ovrAvatar2EventDefinition[numDefinitions];
                fixed (CAPI.ovrAvatar2EventDefinition* definitionsPtr = definitions)
                {
                    return CAPI.ovrAvatarXBehavior_GetEventDefinitions(behaviorNameCapi.StringView, definitionsPtr,
                            numDefinitions, &numDefinitions)
                        .EnsureSuccess("OvrAvatarXBehavior_GetEventDefinitions", logScope)
                        ? definitions
                        : null;
                }
            }
        }
    }
}
