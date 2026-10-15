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
using Unity.Collections;

namespace Oculus.Avatar2.Experimental
{
#pragma warning disable IDE1006 // Naming Styles
    using ovrAvatar2Result = Avatar2.CAPI.ovrAvatar2Result;

    public static partial class CAPI
    {
        private const string eventsInternalLogScope = "eventsInternalCAPI";

        /// Get the id of an event given its name
        /// \param name of the event
        /// \param (out) corresponding id
        /// \return result code
        internal static bool OvrAvatar2Event_GetEventId(
            ovrAvatar2StringView eventNameView, out ovrAvatar2EventId eventId)
        {
            return ovrAvatar2Event_GetEventId(in eventNameView, out eventId).EnsureSuccess(
                "ovrAvatar2Event_GetEventId", eventsInternalLogScope);
        }

        /// Get the name of an event given its id
        /// \param id of the event
        /// \param (out) corresponding name
        /// \return result code
        public static bool OvrAvatar2Event_GetName(ovrAvatar2EventId eventId, out string eventName)
        {
            const int FIXED_CAPACITY = 256;
            const int MAX_NUM_RETRIES = 4;
            unsafe
            {
                var stackBuffer = stackalloc byte[FIXED_CAPACITY];
                var buffer = new ovrAvatar2StringBuffer(stackBuffer, FIXED_CAPACITY);

                var result = ovrAvatar2Event_GetName(eventId, ref buffer);
                if (result == ovrAvatar2Result.BufferTooSmall)
                {
                    uint capacity = FIXED_CAPACITY;
                    for (var retry = 0; retry < MAX_NUM_RETRIES && result == ovrAvatar2Result.BufferTooSmall; retry++)
                    {
                        capacity *= 2;
                        var managedBuffer = new NativeArray<byte>((int)capacity, Allocator.Temp);
                        buffer = new ovrAvatar2StringBuffer(managedBuffer.GetPtr(), capacity);
                        result = ovrAvatar2Event_GetName(eventId, ref buffer);
                    }
                }

                eventName = buffer.AllocateManagedString();

                return result.EnsureSuccess("ovrAvatar2Event_GetName", eventsInternalLogScope);
            }
        }

        public static bool OvrAvatar2Event_GetPayloadTypeName(in ovrAvatar2EventPayloadId payloadId, out string payloadName)
        {
            const int FIXED_CAPACITY = 256;

            ovrAvatar2Result result;
            unsafe
            {
                var stackBuffer = stackalloc byte[FIXED_CAPACITY];
                var buffer = new ovrAvatar2StringBuffer(stackBuffer, FIXED_CAPACITY);

                result = ovrAvatar2Event_GetPayloadTypeName(payloadId, ref buffer);
                payloadName = buffer.AllocateManagedString();
            }
            return result.EnsureSuccess("ovrAvatar2Event_GetPayloadTypeName", eventsInternalLogScope);
        }

        public static string OvrAvatar2Event_GetName(ovrAvatar2EventId eventId)
        {
            if (!OvrAvatar2Event_GetName(eventId, out var name))
            {
                return "error_fetching_event_name";
            }

            return name;
        }

        public static string OvrAvatar2Event_GetPayloadTypeName(in ovrAvatar2EventPayloadId payloadId)
        {
            if (!OvrAvatar2Event_GetPayloadTypeName(in payloadId, out var name))
            {
                return "error_fetching_payload_name";
            }

            return name;
        }

        /// Get payloadId for a `ovrAvatar2PrimitiveTypeId`
        /// \param primitiveId of the event
        /// \param (out) corresponding payload id
        /// \return true
        public static bool OvrAvatar2Event_PayloadIdForPrimitive(ovrAvatar2PrimitiveTypeId primitiveId,
            out ovrAvatar2EventPayloadId outPayloadId)
        {
            outPayloadId = ovrAvatar2EventDefinition_Invalid.payloadId;
            return ovrAvatar2Event_PayloadIdForPrimitive(primitiveId, out outPayloadId)
                .EnsureSuccess("ovrAvatar2Event_PayloadIdForPrimitive");
        }

        // Attempt to register the provided `ovrAvatar2EventDefinition`
        public static bool OvrAvatar2Event_RegisterEventDefinition(
            in ovrAvatar2EventDefinition eventDefinition,
            bool allowAlreadyExists = false, UnityEngine.Object? unityContext = null)
        {
            var result = ovrAvatar2Event_RegisterEventDefinition(in eventDefinition);
            bool success;
            if (allowAlreadyExists)
            {
                success = result.EnsureSuccessOrLogVerbose(ovrAvatar2Result.AlreadyExists,
                    "EventDefinitions only need to be registered once",
                    "ovrAvatar2Event_RegisterEventDefinition", eventsInternalLogScope, unityContext);
            }
            else
            {
                success = result.EnsureSuccessOrWarning(ovrAvatar2Result.AlreadyExists,
                    "EventDefinitions only need to be registered once",
                    "ovrAvatar2Event_RegisterEventDefinition", eventsInternalLogScope, unityContext);
            }
            return success;
        }

        // Attempt to register the provided `ovrAvatar2EventDefinition`
        // with controls provided for how to handle (log) the `AlreadyExists` case
        public static bool OvrAvatar2Event_RegisterEventDefinition(
            in ovrAvatar2EventDefinition eventDefinition,
            OvrAvatarLog.ELogLevel alreadyExistLevel, UnityEngine.Object? unityContext = null)
        {
            var result = ovrAvatar2Event_RegisterEventDefinition(in eventDefinition);
            bool success;
            if (result == ovrAvatar2Result.AlreadyExists)
            {
                success = true;

                if (alreadyExistLevel >= OvrAvatarLog.ELogLevel.Verbose)
                {
                    OvrAvatarLog.Log(alreadyExistLevel,
                        $"EventDefinition already exists for event {OvrAvatar2Event_GetName(eventDefinition.eventId)}",
                        eventsInternalLogScope, unityContext);
                }
            }
            else
            {
                success = result.EnsureSuccess("ovrAvatar2Event_RegisterEventDefinition",
                    eventsInternalLogScope, unityContext);
            }
            return success;
        }

        // Subscribe provided `callback` to be invoked when `eventDefinition` is sent by the global event manager
        internal static bool OvrAvatar2Event_Experimental_SubscribeToEventWithPayload(
            in ovrAvatar2EventDefinition eventDefinition,
            IntPtr owner,
            ovrAvatar2Event_SynchronousEventCallbackWithPayload callback)
        {
            return ovrAvatar2Event_Experimental_SubscribeToEventWithPayload(
                in eventDefinition, owner, callback).EnsureSuccess(
                    "ovrAvatar2Event_Experimental_SubscribeToEventWithPayload", eventsInternalLogScope);
        }

        internal static bool OvrAvatar2Event_Experimental_UnsubscribeFromEvent(
            ovrAvatar2EventId eventId,
            IntPtr owner)
        {
            return ovrAvatar2Event_Experimental_UnsubscribeFromEvent(eventId, owner)
                .EnsureSuccess("ovrAvatar2Event_Experimental_UnsubscribeFromEvent", eventsInternalLogScope);
        }

        public enum ovrAvatar2EventId : UInt64
        {
            Invalid = 0,
        }

        /// Identifies the specific (32bit) integer `typeId` used with a known
        /// `ovrAvatar2EventPayloadDomainId`
        public enum ovrAvatar2EventPayloadTypeId : Int32
        {
            Invalid = 0,
        }

        /// Identifies the (32bit) integer `typeId` for non-primitive types
        public enum ovrAvatar2ExperimentalEventPayloadTypeId : Int32
        {
            Invalid = 0,

            Vector2f = 1,
            Vector3f = 2,
            Vector4f = 3,
            Quatf = 4,
            Transform = 5,
            Matrix4f = 6,
            String = 7,

            Count = 8
        }

        /// Identifies the specific (32bit) integer `domainId` used with a known
        /// `ovrAvatar2EventPayloadTypeId`
        public enum ovrAvatar2EventPayloadDomainId : Int32
        {
            Invalid = 0,
        }

        /// Uniquely identifies any supported payload (64bit) integer `payloadId`, used with a known
        /// `ovrAvatar2EventDefinition`
        [StructLayout(LayoutKind.Sequential)]
        public readonly struct ovrAvatar2EventPayloadId
        {
            public ovrAvatar2EventPayloadId(
                ovrAvatar2EventPayloadTypeId typeId_, ovrAvatar2EventPayloadDomainId domainId_)
            {
                typeId = typeId_;
                domainId = domainId_;
            }

            public ovrAvatar2EventPayloadId(ovrAvatar2PrimitiveTypeId primitiveTypeId)
            {
                if (!OvrAvatar2Event_PayloadIdForPrimitive(primitiveTypeId, out this))
                {
                    this = default;
                }
            }

            public ovrAvatar2EventPayloadId(ovrAvatar2ExperimentalEventPayloadTypeId experimentalTypeId)
            {
                if (experimentalTypeId != ovrAvatar2ExperimentalEventPayloadTypeId.Invalid)
                {
                    typeId = (CAPI.ovrAvatar2EventPayloadTypeId)experimentalTypeId;
                    domainId = (CAPI.ovrAvatar2EventPayloadDomainId)4; // SdkCpp domain id - see T165630247
                }
                else
                {
                    this = default;
                }
            }

            public bool IsValid => typeId.IsValid() && domainId.IsValid();
            public bool IsVoid => typeId == ovrAvatar2EventPayloadTypeId.Invalid && domainId.IsValid();

            public bool IsValidOrVoid => domainId.IsValid();

            public readonly ovrAvatar2EventPayloadTypeId typeId;
            public readonly ovrAvatar2EventPayloadDomainId domainId;
        }

        public static readonly ovrAvatar2EventPayloadId ovrAvatar2EventPayloadId_Invalid = default;
        public static ovrAvatar2EventPayloadId ovrAvatar2EventPayloadId_Void
            => new ovrAvatar2EventPayloadId(ovrAvatar2PrimitiveTypeId.Void);

        /// Uniquely pair a known (64bit) integer `eventId` with a known (64bit) integer `payloadId`
        [StructLayout(LayoutKind.Sequential)]
        public readonly struct ovrAvatar2EventDefinition
        {
            public ovrAvatar2EventDefinition(ovrAvatar2EventId eventId_, ovrAvatar2EventPayloadId payloadId_)
            {
                eventId = eventId_;
                payloadId = payloadId_;
            }

            public readonly ovrAvatar2EventId eventId;
            public readonly ovrAvatar2EventPayloadId payloadId;
        }

        public static readonly ovrAvatar2EventDefinition ovrAvatar2EventDefinition_Invalid = default;

        public enum ovrAvatar2PrimitiveTypeId : Int32
        {
            Void = 0, // This almost always indicates an error
            Bit = 1,
            Bool = 2,
            Char = 3,
            Int8 = 4,
            Uint8 = 5,
            Int16 = 6,
            Uint16 = 7,
            Int32 = 8,
            Uint32 = 9,
            Int64 = 10,
            Uint64 = 11,
            Float = 12,
            Double = 13,

            Count = 14,
        }

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern ovrAvatar2Result
          ovrAvatar2Event_PayloadIdForPrimitive(ovrAvatar2PrimitiveTypeId primitiveId,
            out ovrAvatar2EventPayloadId outPayloadId);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern ovrAvatar2Result ovrAvatar2Event_GetEventId(
          in ovrAvatar2StringView eventNameView, out ovrAvatar2EventId eventId);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Event_GetName(
            ovrAvatar2EventId eventId, ref ovrAvatar2StringBuffer name);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Event_GetPayloadTypeName(
            ovrAvatar2EventPayloadId payloadId, ref ovrAvatar2StringBuffer name);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Event_RegisterEventDefinition(
            in ovrAvatar2EventDefinition eventDefinition);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        internal delegate bool ovrAvatar2Event_SynchronousEventCallbackWithPayload(
            IntPtr owner,
            in ovrAvatar2EventDefinition eventDef,
            in ovrAvatar2DataView payload);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2Event_Experimental_SubscribeToEventWithPayload(
            in ovrAvatar2EventDefinition eventDefinition,
            IntPtr owner,
            ovrAvatar2Event_SynchronousEventCallbackWithPayload callback);

        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern ovrAvatar2Result ovrAvatar2Event_Experimental_UnsubscribeFromEvent(
            ovrAvatar2EventId eventId,
            IntPtr owner);
    }

    public static class OvrAvatarAPI_EventsInternal_Extensions
    {
        public static bool IsValid(this CAPI.ovrAvatar2EventId eventId)
            => eventId != CAPI.ovrAvatar2EventId.Invalid;

        public static bool IsValid(this CAPI.ovrAvatar2EventPayloadTypeId payloadTypeId)
            => payloadTypeId != CAPI.ovrAvatar2EventPayloadTypeId.Invalid;

        public static bool IsValid(this CAPI.ovrAvatar2EventPayloadDomainId domainId)
            => domainId != CAPI.ovrAvatar2EventPayloadDomainId.Invalid;

        public static bool IsValid(this in CAPI.ovrAvatar2EventDefinition eventDefinition)
            => eventDefinition.eventId.IsValid() && eventDefinition.payloadId.IsValidOrVoid;
    }
#pragma warning restore IDE1006 // Naming Styles
}
