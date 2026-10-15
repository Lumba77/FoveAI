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
using System.Runtime.InteropServices;

using UnityEngine;

namespace Oculus.Avatar2.Experimental
{
    using ovrAvatar2Result = Avatar2.CAPI.ovrAvatar2Result;
    using ovrAvatar2EntityId = Avatar2.CAPI.ovrAvatar2EntityId;

#pragma warning disable IDE1006 // Naming Styles
    public static partial class CAPI
    {
        private const string entityInternalLogScope = "entityInternalCAPI";

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate bool ovrAvatar2Entity_SynchronousEventCallback(
            IntPtr owner, ovrAvatar2EntityId entityId, ovrAvatar2EventId eventId);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        internal delegate bool ovrAvatar2Entity_SynchronousEventCallbackWithPayload(
            IntPtr owner,
            ovrAvatar2EntityId entityId,
            in ovrAvatar2EventDefinition eventDef,
            in ovrAvatar2DataView payload);

        /// Send event to an entity
        /// \param entity Id of entity of which to send the event to
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if unknown entity handle is passed.
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_SendEvent(ovrAvatar2EntityId entityId, ovrAvatar2EventId eventId
            , bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_SendEvent(entityId, eventId).EnsureEventSendSuccess(
                "ovrAvatar2Entity_SendEvent", entityInternalLogScope
                , new ovrAvatar2EventDefinition(eventId, ovrAvatar2EventPayloadId_Void)
                , suppressNotFoundWarning);
        }

        /// Send event to an entity with payload matching `eventDef`
        /// \param entity Id of entity which will receive the event.
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result BadParameter if unknown entity or eventId is passed.
        /// \return result InvalidData if unexpected or invalid payload data is detected.
        /// \return result BufferMisaligned if payload does not have the correct alignment for `eventDef`.
        /// \return result Unsupported if the provided payload type does not match event registration.
        /// \return result Unknown if a payload is not able to be formed with the given parameters.
        internal static bool OvrAvatar2Entity_SendEventWithPayload(
            ovrAvatar2EntityId entityId,
            in ovrAvatar2EventDefinition eventDef,
            in ovrAvatar2DataView payload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_SendEventWithPayload(entityId, in eventDef, in payload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_SendEventWithPayload", entityInternalLogScope
                    , in eventDef
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a string payload.
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithStringPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            string stringPayload,
            bool suppressNotFoundWarning = false)
        {
            // TODO: Using C# `System.String` for this results in a large amount of GC thrash
            return ovrAvatar2Entity_Experimental_SendEventWithStringPayload(entityId, eventId, stringPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithStringPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.String))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a float payload.
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithFloatPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            float floatPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithFloatPayload(entityId, eventId, floatPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithFloatPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2PrimitiveTypeId.Float))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a bool payload.
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        public static bool OvrAvatar2Entity_Experimental_SendEventWithBoolPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            bool boolPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithBoolPayload(entityId, eventId, boolPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithBoolPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2PrimitiveTypeId.Bool))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a vec2 payload.
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithVec2fPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Avatar2.CAPI.ovrAvatar2Vector2f vec2fPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithVec2fPayload(entityId, eventId, vec2fPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithVec2fPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Vector2f))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a vec3 payload.
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithVec3fPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Avatar2.CAPI.ovrAvatar2Vector3f vec3fPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithVec3fPayload(entityId, eventId, vec3fPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithVec3fPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Vector3f))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a vec4 payload.
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool ovrAvatar2Entity_Experimental_SendEventWithVec4fPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Avatar2.CAPI.ovrAvatar2Vector4f vec4fPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithVec4fPayload(entityId, eventId, vec4fPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithVec4fPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Vector4f))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a quaternion payload.
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool ovrAvatar2Entity_Experimental_SendEventWithQuatfPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Avatar2.CAPI.ovrAvatar2Quatf quatPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithQuatfPayload(entityId, eventId, quatPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithQuatfPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Quatf))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a position payload.
        /// NOTE: Applies coordinate space conversions, if configured
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithPositionPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Vector3 positionPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithPositionPayload(entityId, eventId, positionPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithPositionPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Vector3f))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with an orientation payload.
        /// NOTE: Applies coordinate space conversions, if configured
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithOrientationPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Quaternion orientationPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithOrientationPayload(entityId, eventId, orientationPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithOrientationPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Quatf))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a scale payload.
        /// NOTE: Applies coordinate space conversions, if configured
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithScalePayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Vector3 scalePayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithScalePayload(entityId, eventId, scalePayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithScalePayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Vector3f))
                    , suppressNotFoundWarning);
        }

        /// Send an event to an entity with a transform payload.
        /// NOTE: Applies coordinate space conversions, if configured
        /// Experimental and unsupported.
        /// \param id of the entity the event is sent to
        /// \param id of the event being sent
        /// \param payload
        /// \param suppressNotFoundWarning do not log `NotFound` case (ie: unhandled event is expected for this call)
        /// \return result Unsupported if the entity doesn't support receiving events
        /// \return result BadParameter if an event with the given id could not be created
        /// \return result NotFound if the event was not handled (no listener in current state)
        public static bool OvrAvatar2Entity_Experimental_SendEventWithTransformPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            in Avatar2.CAPI.ovrAvatar2Transform transformPayload,
            bool suppressNotFoundWarning = false)
        {
            return ovrAvatar2Entity_Experimental_SendEventWithTransformPayload(entityId, eventId, transformPayload)
                .EnsureEventSendSuccess("ovrAvatar2Entity_Experimental_SendEventWithTransformPayload", entityInternalLogScope
                    , new ovrAvatar2EventDefinition(eventId, new ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId.Transform))
                    , suppressNotFoundWarning);
        }

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_SendEvent(ovrAvatar2EntityId entityId, ovrAvatar2EventId eventId);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_SendEventWithPayload(
          ovrAvatar2EntityId entityId,
          in ovrAvatar2EventDefinition eventDef,
          in ovrAvatar2DataView payload);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithStringPayload(
          ovrAvatar2EntityId entityId,
          ovrAvatar2EventId eventId,
          string stringPayload);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithFloatPayload(
          ovrAvatar2EntityId entityId,
          ovrAvatar2EventId eventId,
          float floatPayload);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithBoolPayload(
          ovrAvatar2EntityId entityId,
          ovrAvatar2EventId eventId,
          bool boolPayload);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithVec2fPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Vector2f vec2fPayload);

        // Send an event to an entity with a vec3 payload.
        // Experimental and unsupported.
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithVec3fPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Vector3f vec3fPayload);

        // Send an event to an entity with a vec4 payload.
        // Experimental and unsupported.
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithVec4fPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Vector4f vec4fPayload);

        // Send an event to an entity with a quaternion payload.
        // Experimental and unsupported.
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithQuatfPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Quatf quatPayload);

        // Send an event to an entity with a position payload.
        // NOTE: Applies coordinate space conversions, if configured
        // Experimental and unsupported.
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithPositionPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Vector3f positionPayload);

        // Send an event to an entity with an orientation payload.
        // NOTE: Applies coordinate space conversions, if configured
        // Experimental and unsupported.
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithOrientationPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Quatf orientationPayload);

        // Send an event to an entity with a scale payload.
        // NOTE: Applies coordinate space conversions, if configured
        // Experimental and unsupported.
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithScalePayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Vector3f scalePayload);

        // Send an event to an entity with a transform payload.
        // NOTE: Applies coordinate space conversions, if configured
        // Experimental and unsupported.
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SendEventWithTransformPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            Avatar2.CAPI.ovrAvatar2Transform transformPayload);

        /// Subscribe to an event.
        /// \param entityId Id of entity of which to set the callback for.
        /// \param eventId Id of event to subscibe to.
        /// \param callback Function to call when the event is fired on this Entity.
        /// \param owner The owner of this subscription; used to unsubscribe later.
        /// \return result BadParameter if unknown entity handle is passed.
        ///
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SubscribeToEvent(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            ovrAvatar2Entity_SynchronousEventCallback callback,
            IntPtr owner);

        /// Subscribe to an entity event with payload.
        /// \param entityId Id of entity of which to set the callback for.
        /// \param eventId Id of event to subscibe to.
        /// \param callback Function to call when the event is fired on this Entity.
        /// \param owner The owner of this subscription; used to unsubscribe later.
        /// \return result BadParameter if unknown entity handle is passed.
        ///
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_SubscribeToEventWithPayload(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventId eventId,
            ovrAvatar2Entity_SynchronousEventCallbackWithPayload callback,
            IntPtr owner);

        // Unsubscribe all events from `entity` which have the provided `owner`
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_Experimental_UnsubscribeAllEvents(
            ovrAvatar2EntityId entityId, IntPtr owner);

        ///  Get event definitions registered for a specific Entity
        /// \param entityId - entity being inspected
        /// \param definitions - output array which will contain event definitions
        /// \param definitionsCapacity - maximum capacity of definitions output array (eventDef instances)
        /// \param totalDefinitions - output variable recording unique event definitions on `entityId`
        ///     NOTE: May be greater than `definitionsCapacity`
        /// \return ovrAvatar2Result_Success if all event definitions fit into `definitions`
        ///         ovrAvatar2Result_BufferTooSmall if `definitionsCapacity` was not large enough
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern unsafe ovrAvatar2Result ovrAvatarXEntity_GetEventDefinitions(
            ovrAvatar2EntityId entityId,
            ovrAvatar2EventDefinition* definitions,
            uint definitionsCapacity,
            uint* totalDefinitions);

        public enum ovrAvatar2AbstractPoseJoints : Int32
        {
            ovrAvatar2AbstractPoseJoints_HandGripLeft = 0,
            ovrAvatar2AbstractPoseJoints_HandGripRight = 1,
            ovrAvatar2AbstractPoseJoints_Count = 2
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2AbstractPose
        {
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = (int)Experimental.CAPI.ovrAvatar2AbstractPoseJoints.ovrAvatar2AbstractPoseJoints_Count)]
            public Avatar2.CAPI.ovrAvatar2Transform[] transforms;
        };

        public static bool OvrAvatar2Entity_GetAbstractPose(
            ovrAvatar2EntityId entityId,
            out ovrAvatar2AbstractPose outPose,
            UnityEngine.Object? context = null)
        {
            return ovrAvatar2Entity_GetAbstractPose(entityId, out outPose).
                EnsureSuccess("ovrAvatar2Entity_GetAbstractPose", entityInternalLogScope, context);
        }

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_GetAbstractPose(
          ovrAvatar2EntityId entityId,
          out ovrAvatar2AbstractPose outPose);
    }
#pragma warning restore IDE1006 // Naming Styles
}

namespace Oculus.Avatar2
{
    using EXPERIMENTAL_CAPI = Oculus.Avatar2.Experimental.CAPI;

    public static class OvrAvatarEventCAPIHelpers
    {
        public static bool EnsureEventSendSuccess(
            this CAPI.ovrAvatar2Result result, string msgContext, string logScope
            , Experimental.BehaviorSystem.BaseEventController controller
            , bool suppressNotFoundWarning, UnityEngine.Object? unityObject = null)
        {
            // If not found, and we are suppressing notFoundWarnings - don't log
            if (suppressNotFoundWarning && result == CAPI.ovrAvatar2Result.NotFound)
            {
                return false;
            }
            // If we received a Avatar CAPI error - log
            if (!result.IsSuccess())
            {
                result.LogError($"{msgContext}(\"{controller.Name}\", {controller.PayloadName})", logScope, unityObject);
                return false;
            }

            return true;
        }

        public static bool EnsureEventSendSuccess(
            this CAPI.ovrAvatar2Result result, string msgContext, string logScope
            , in Experimental.CAPI.ovrAvatar2EventDefinition eventDefinition
            , bool suppressNotFoundWarning, UnityEngine.Object? unityObject = null)
        {
            // If not found, and we are suppressing notFoundWarnings - don't log
            if (suppressNotFoundWarning && result == CAPI.ovrAvatar2Result.NotFound)
            {
                return false;
            }
            // If we received a Avatar CAPI error - log
            if (!result.IsSuccess())
            {
                result.LogError(
                    $"{msgContext}(\"{EXPERIMENTAL_CAPI.OvrAvatar2Event_GetName(eventDefinition.eventId)}\", {EXPERIMENTAL_CAPI.OvrAvatar2Event_GetPayloadTypeName(in eventDefinition.payloadId)})"
                    , logScope, unityObject);
                return false;
            }

            return true;
        }
    }
}
