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
using System.Collections.Generic;

using UnityEngine;

using STANDARD_CAPI = Oculus.Avatar2.CAPI;
using EXPERIMENTAL_CAPI = Oculus.Avatar2.Experimental.CAPI;
// ReSharper disable RedundantDefaultMemberInitializer

namespace Oculus.Avatar2.Experimental
{
    public static partial class BehaviorSystem
    {
        public abstract class BaseEventController
        {
            protected virtual string LogScope => "BaseEventController";

            private readonly CAPI.ovrAvatar2EventDefinition _definition;

            internal ref readonly CAPI.ovrAvatar2EventDefinition Definition => ref _definition;

            public bool IsValid => _definition.IsValid();

            public string Name
            {
                get
                {
                    if (_nameCache == null && !CAPI.OvrAvatar2Event_GetName(_definition.eventId, out _nameCache))
                    {
                        OvrAvatarLog.LogError($"Fetching the event name for event with id {EventId} failed.", LogScope);
                        // `OvrAvatar2Event_GetName` may write out a partial name if the name is very long,
                        // but at least that is _a_ string?
                    }

                    return _nameCache;
                }
            }

            public string PayloadName
            {
                get
                {
                    if (_payloadNameCache == null && !CAPI.OvrAvatar2Event_GetPayloadTypeName(PayloadID, out _payloadNameCache))
                    {
                        OvrAvatarLog.LogError($"Fetching the payload name for payload with id {PayloadID} failed.", logScope);
                        // `OvrAvatar2Event_GetPayloadTypeName` may write out a partial name if the name is very long,
                        // but at least that is _a_ string?
                    }

                    return _payloadNameCache;
                }
            }

            // ReSharper disable once MemberCanBePrivate.Global
            public CAPI.ovrAvatar2EventId EventId => Definition.eventId;
            // ReSharper disable once MemberCanBePrivate.Global
            public ref readonly CAPI.ovrAvatar2EventPayloadId PayloadID => ref Definition.payloadId;

            protected BaseEventController(in CAPI.ovrAvatar2EventDefinition eventDefinition)
            {
                _definition = eventDefinition;
            }

            private string? _nameCache = null;
            private string? _payloadNameCache = null;
        }

        public class EventController : BaseEventController
        {
            protected override string LogScope => "EventController";

            private EventController(in CAPI.ovrAvatar2EventDefinition eventDefinition) : base(in eventDefinition)
            {
            }

            private static EventController? s_invalidCached = null;
            // ReSharper disable once MemberCanBePrivate.Global
            public static EventController Invalid =>
                s_invalidCached ??= new EventController(in CAPI.ovrAvatar2EventDefinition_Invalid);

            public static EventController Register(string name)
            {
                var id = GetEventId(name);
                var eventDefinition = new CAPI.ovrAvatar2EventDefinition
                (
                    id,
                    CAPI.ovrAvatar2EventPayloadId_Void
                );
                return CAPI.OvrAvatar2Event_RegisterEventDefinition(in eventDefinition)
                    // ReSharper disable once HeapView.ObjectAllocation.Evident
                    ? new EventController(in eventDefinition)
                    : Invalid;
            }

            public static EventController RegisterWithStringPayload(string name)
            {
                var id = GetEventId(name);
                var eventDefinition = new CAPI.ovrAvatar2EventDefinition
                (
                    id,
                    CAPI.ovrAvatar2EventPayloadId_Void
                );
                // Note: Because of issues with strings this isn't actually registering it.
                //       The event needs to already be in SDKReg (event_definitions.json)
                // ReSharper disable once HeapView.ObjectAllocation.Evident
                return new EventController(in eventDefinition);
            }

            [Obsolete("Use EventController<T> instead, which now handles experimental payload types", false)]
            public static EventController RegisterWithExperimentalPayloadType<TExperimentalPayload>(string name)
                where TExperimentalPayload : unmanaged
            {
                var eventId = GetEventId(name);
                if (!eventId.IsValid())
                {
                    return Invalid;
                }
                var experimentalPayloadTypeId = GetExperimentalPayloadTypeId<TExperimentalPayload>();
                var payloadId = new CAPI.ovrAvatar2EventPayloadId(experimentalPayloadTypeId);
                var eventDefinition = new CAPI.ovrAvatar2EventDefinition
                (
                    eventId,
                    payloadId
                );
                return CAPI.OvrAvatar2Event_RegisterEventDefinition(in eventDefinition)
                    ? new EventController(in eventDefinition)
                    : Invalid;
            }

            private static CAPI.ovrAvatar2ExperimentalEventPayloadTypeId GetExperimentalPayloadTypeId<TExperimentalPayload>()
                where TExperimentalPayload : unmanaged
            {
                return EventControllerHelpers.LookupExperimentalPayloadTypeId<TExperimentalPayload>();
            }
        }

        public class EventController<TPayload> : BaseEventController where TPayload : unmanaged
        {
            // ReSharper disable once StaticMemberInGenericType
            private static string? s_logScopeCache = null;
            protected override string LogScope => s_logScopeCache ??= $"EventController<{typeof(TPayload).Name}>";

            private static EventController<TPayload>? s_invalidCache = null;
            // ReSharper disable once MemberCanBePrivate.Global
            public static EventController<TPayload> Invalid =>
                s_invalidCache ??= new EventController<TPayload>(in CAPI.ovrAvatar2EventDefinition_Invalid);

            private EventController(in CAPI.ovrAvatar2EventDefinition eventDefinition) : base(in eventDefinition) { }

            public static EventController<TPayload> Register(string name, bool allowAlreadyExists = false)
            {
                var id = GetEventId(name);
                if (!id.IsValid())
                {
                    return Invalid;
                }

                ref readonly var payloadId = ref GetPayloadId();
                Debug.Assert(payloadId.IsValid);
                return Register(id, in payloadId, allowAlreadyExists);
            }

            private static EventController<TPayload> Register(CAPI.ovrAvatar2EventId id,
                in CAPI.ovrAvatar2EventPayloadId payloadId, bool allowAlreadyExists = false)
            {
                var eventDefinition = new CAPI.ovrAvatar2EventDefinition
                (
                    id,
                    payloadId
                );
                return CAPI.OvrAvatar2Event_RegisterEventDefinition(in eventDefinition, allowAlreadyExists)
                    ? new EventController<TPayload>(in eventDefinition)
                    : Invalid;
            }

            // ReSharper disable once StaticMemberInGenericType
            private static CAPI.ovrAvatar2EventPayloadId s_payloadIdCache = default;
            private static ref readonly CAPI.ovrAvatar2EventPayloadId GetPayloadId()
            {
                // Check if cached value is within valid range, otherwise it is not yet cached
                // Handle signed/unsigned storage for typeId
                if (!s_payloadIdCache.IsValid)
                {
                    bool wasFound = EventControllerHelpers.LookupPayloadId<TPayload>(out s_payloadIdCache);
                    if (!wasFound || !s_payloadIdCache.IsValid)
                    {
                        OvrAvatarLog.LogError(
                            $"Unable to find valid payloadId for type {typeof(TPayload).Name}, attempting generic payloadId"
                            , logScope);

                        // mark a "valid" payload to avoid infinite lookup attempts - use "SdkCpp" payload, it _might_ work :X
                        s_payloadIdCache = new CAPI.ovrAvatar2EventPayloadId(
                            (CAPI.ovrAvatar2EventPayloadTypeId)UInt16.MaxValue
                            , (CAPI.ovrAvatar2EventPayloadDomainId)4 /* SdkCpp domain id */);
                    }
                }
                return ref s_payloadIdCache;
            }
        }

        private static class EventControllerHelpers
        {
            private const string LOG_SCOPE = "EventControllerHelpers";

            // TODO: Support CAPI.ovrAvatar2PrimitiveTypeId.Bit
            private static Dictionary<Type, CAPI.ovrAvatar2EventPayloadId>? s_typeLookup = null;
            public static bool
                LookupPayloadId<TPrimitivePayload>(out CAPI.ovrAvatar2EventPayloadId payloadId, bool errorIfNotFound = true)
                where TPrimitivePayload : unmanaged
            {
                if (s_typeLookup == null)
                {
                    const int typeCount = (int)CAPI.ovrAvatar2PrimitiveTypeId.Count
                                           + ((int)CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Count - 1 /* invalid */);

                    // ReSharper disable once HeapView.ObjectAllocation.Evident
                    var lookupBuilder = new Dictionary<Type, CAPI.ovrAvatar2EventPayloadId>(typeCount)
                    {
                        { typeof(bool), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Bool) },
                        { typeof(char), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Char) },
                        { typeof(sbyte), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Int8) },
                        { typeof(byte), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Uint8) },
                        { typeof(short), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Int16) },
                        { typeof(ushort), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Uint16) },
                        { typeof(Int32), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Int32) },
                        { typeof(UInt32), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Uint32) },
                        { typeof(Int64), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Int64) },
                        { typeof(UInt64), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Uint64) },
                        { typeof(float), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Float) },
                        { typeof(double), new CAPI.ovrAvatar2EventPayloadId(CAPI.ovrAvatar2PrimitiveTypeId.Double) }
                    };

                    // append experimental types - kind of jank for now to support the old API without too much duplicate code
                    foreach (var kvp in FetchExperimentalTypeLookup())
                    {
                        lookupBuilder.Add(kvp.Key, new CAPI.ovrAvatar2EventPayloadId(kvp.Value));
                    }

                    s_typeLookup = lookupBuilder;
                }

                var wasFound = s_typeLookup.TryGetValue(typeof(TPrimitivePayload), out payloadId);
                if (!wasFound && errorIfNotFound)
                {
                    OvrAvatarLog.LogError(
                        $"Type '{typeof(TPrimitivePayload)}' is not a primitive type or not supported. " +
                        "Default to void payload type", LOG_SCOPE);
                }
                return wasFound;
            }

            private static Dictionary<Type, CAPI.ovrAvatar2ExperimentalEventPayloadTypeId>? s_experimentalTypeLookup = null;
            private static Dictionary<Type, CAPI.ovrAvatar2ExperimentalEventPayloadTypeId> FetchExperimentalTypeLookup()
            {
                const int experimentalTypeCount
                    = (int)CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Count - 1 /* invalid */;
                // create on demand
                // ReSharper disable once HeapView.ObjectAllocation.Evident
                return s_experimentalTypeLookup
                    ??= new Dictionary<Type, CAPI.ovrAvatar2ExperimentalEventPayloadTypeId>(experimentalTypeCount)
                {
                    {
                        typeof(STANDARD_CAPI.ovrAvatar2Vector2f)
                        , CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Vector2f
                    },
                    {
                        typeof(STANDARD_CAPI.ovrAvatar2Vector3f)
                        , CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Vector3f
                    },
                    { typeof(STANDARD_CAPI.ovrAvatar2Vector4f), CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Vector4f },
                    { typeof(STANDARD_CAPI.ovrAvatar2Quatf), CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Quatf },
                    { typeof(STANDARD_CAPI.ovrAvatar2Transform), CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Transform },
                    { typeof(STANDARD_CAPI.ovrAvatar2Matrix4f), CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.Matrix4f },
                    { typeof(string), CAPI.ovrAvatar2ExperimentalEventPayloadTypeId.String }
                };
            }

            public static CAPI.ovrAvatar2ExperimentalEventPayloadTypeId
                LookupExperimentalPayloadTypeId<TExperimentalPayload>(bool errorIfNotFound = true)
                where TExperimentalPayload : unmanaged
            {
                if (!FetchExperimentalTypeLookup()
                        .TryGetValue(typeof(TExperimentalPayload), out var experimentalTypeId) && errorIfNotFound)
                {
                    OvrAvatarLog.LogError(
                        $"Type '{typeof(TExperimentalPayload)}' is not an experimental payload type or not supported. " +
                        "Defaulting to invalid payload type", LOG_SCOPE);
                }
                return experimentalTypeId;
            }
        }
    }
}
