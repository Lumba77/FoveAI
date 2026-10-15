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

using Oculus.Avatar2.Experimental;
using static Oculus.Avatar2.Experimental.CAPI;

using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;

using UnityEngine;

namespace Oculus.Avatar2
{
    public static partial class CAPI
    {
        public enum ovrAvatar2Graph : Int32
        {
            Invalid = 0,

            Meta = 1,
            Oculus = 2,
            [InspectorName(null)] First = Meta,
            [InspectorName(null)] Last = Oculus,

            [InspectorName(null)] Count = (Last - First) + 1,
        }

        public static readonly string UserAvatarConfigIds = "";

        /// Query to see if a user has an avatar on specific graph
        /// ovrAvatar2_RequestCallback is called when the request is fulfilled
        /// Request status:
        ///   ovrAvatar2Result_Success - request succeeded
        ///   ovrAvatar2Result_Unknown - error while querying user avatar status
        /// ovrAvatar2_GetRequestBool() result
        ///   true - user has an avatar
        ///   false - user does not have an avatar
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_GraphHasAvatar(UInt64 userID, ovrAvatar2Graph graph,
                out ovrAvatar2RequestId requestId, IntPtr userContext);

        internal static bool OvrAvatar2_GraphHasAvatar(UInt64 userID, ovrAvatar2Graph graph,
            out ovrAvatar2RequestId requestId, IntPtr userContext)
        {
            var result = ovrAvatar2_GraphHasAvatar(userID, graph, out requestId, userContext);
            if (result.EnsureSuccess("OvrAvatar2_GraphHasAvatar"))
            {
                return true;
            }
            requestId = ovrAvatar2RequestId.Invalid;
            return false;
        }

        /// Load assets described by a user's specification, plus an additional config id that maps to a backend specification to be merged with the users own
        /// Note: Only one user's assets may be on an entity at a time.
        /// Note: This can be called to load updated assets after ovrAvatar2_HasAvatarChanged returns true
        /// \param entity to load into
        /// \param userID to load from
        /// \param configId to merge with user config
        /// \param graph to load from
        /// \param loadSettings for this load
        /// \param (out) optional loadRequestID to retrieve status from ovrAvatar2Asset_GetLoadRequestInfo
        /// \return result code
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern unsafe ovrAvatar2Result ovrAvatar2Entity_Prototype_LoadUserWithConfigsFromGraph(
            ovrAvatar2EntityId entityId,
            UInt64 userID,
            ovrAvatar2StringView configIDs,
            ovrAvatar2Graph graph,
            ovrAvatar2EntityLoadSettings loadSettings,
            UInt32 settingsStructSize,
            out ovrAvatar2LoadRequestId loadRequestId);


        /// Load assets described by a user's specification.
        /// Note: Only one user's assets may be on an entity at a time.
        /// Note: This can be called to load updated assets after ovrAvatar2_HasAvatarChanged returns true
        /// \param entity to load into
        /// \param userID to load from
        /// \param graph to load from
        /// \param loadSettings for this load
        /// \param (out) optional loadRequestID to retrieve status from ovrAvatar2Asset_GetLoadRequestInfo
        /// \return result code
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Entity_LoadUserFromGraph(ovrAvatar2EntityId entityId,
            UInt64 userID, ovrAvatar2Graph graph, ovrAvatar2EntityLoadSettings loadSettings,
            out ovrAvatar2LoadRequestId loadRequestId);

        public static ovrAvatar2Result OvrAvatar2Entity_LoadUserFromGraph(ovrAvatar2EntityId entityId,
            UInt64 userID, ovrAvatar2Graph graph, out ovrAvatar2LoadRequestId loadRequestId)
        {
            var defaultLoadSettings = OvrAvatar2_GetLoadSettings();
            return ovrAvatar2Entity_LoadUserFromGraph(entityId, userID, graph, defaultLoadSettings, out loadRequestId);
        }

        internal static ovrAvatar2Result ovrAvatar2Entity_LoadUserFromGraphWithFilters_Impl(ovrAvatar2EntityId entityId,
            UInt64 userId, string configIDs, ovrAvatar2Graph graph, in ovrAvatar2EntityFilters loadFilters, bool prefetchOnly,
            bool validateCache, out ovrAvatar2LoadRequestId loadRequestId)
        {
            var loadSettings = OvrAvatar2_GetLoadSettings();
            loadSettings.loadFilters = loadFilters;
            loadSettings.prefetchOnly = prefetchOnly;
            loadSettings.validateCache = validateCache;
            if (configIDs.Length > 0 && configIDs != "0")
            {
                using var stringHandle = new StringHelpers.StringViewAllocHandle(configIDs, Allocator.Temp);
                var settingsStructSize = (UInt32)UnsafeUtility.SizeOf<ovrAvatar2EntityLoadSettings>();
                unsafe
                {
                    return ovrAvatar2Entity_Prototype_LoadUserWithConfigsFromGraph(entityId, userId, stringHandle.StringView, graph, loadSettings, settingsStructSize, out loadRequestId);
                }
            }
            else
            {
                return ovrAvatar2Entity_LoadUserFromGraph(entityId, userId, graph, loadSettings, out loadRequestId);
            }
        }

        [Obsolete("Use `OvrAvatar2Entity_LoadUserFromGraphWithFilters` instead!", false)]
        public static ovrAvatar2Result OvrAvatarEntity_LoadUserFromGraphWithFilters(ovrAvatar2EntityId entityId,
            UInt64 userId, ovrAvatar2Graph graph, in ovrAvatar2EntityFilters loadFilters,
            bool prefetchOnly, bool validateCache, out ovrAvatar2LoadRequestId loadRequestId)
        {
            return ovrAvatar2Entity_LoadUserFromGraphWithFilters_Impl(
                entityId, userId, UserAvatarConfigIds, graph, in loadFilters, prefetchOnly, validateCache, out loadRequestId);
        }

        public static ovrAvatar2Result OvrAvatar2Entity_LoadUserFromGraphWithFilters(ovrAvatar2EntityId entityId,
            UInt64 userId, ovrAvatar2Graph graph, in ovrAvatar2EntityFilters loadFilters, bool prefetchOnly,
            bool validateCache, out ovrAvatar2LoadRequestId loadRequestId)
        {
            return ovrAvatar2Entity_LoadUserFromGraphWithFilters_Impl(entityId, userId, UserAvatarConfigIds, graph, in loadFilters,
                prefetchOnly, validateCache, out loadRequestId);
        }

        internal static ovrAvatar2Result ovrAvatar2Entity_LoadUserFromGraphWithFiltersFast_Impl(ovrAvatar2EntityId entityId,
            UInt64 userId, string configIDs, ovrAvatar2Graph graph, in ovrAvatar2EntityFilters loadFilters, bool prefetchOnly,
            bool validateCache, out ovrAvatar2LoadRequestId loadRequestId)
        {
            var loadSettings = OvrAvatar2_GetFastLoadSettings();
            loadSettings.loadFilters.manifestationFlags = loadFilters.manifestationFlags;
            loadSettings.loadFilters.subMeshInclusionFlags = loadFilters.subMeshInclusionFlags;
            loadSettings.loadFilters.viewFlags = loadFilters.viewFlags;
            loadSettings.loadFilters.loadRigZipFromGlb = loadFilters.loadRigZipFromGlb;
            loadSettings.prefetchOnly = prefetchOnly;
            loadSettings.validateCache = validateCache;
            if (configIDs.Length > 0 && configIDs != "0")
            {
                using var stringHandle = new StringHelpers.StringViewAllocHandle(configIDs, Allocator.Temp);
                var settingsStructSize = (UInt32)UnsafeUtility.SizeOf<ovrAvatar2EntityLoadSettings>();
                unsafe
                {
                    return ovrAvatar2Entity_Prototype_LoadUserWithConfigsFromGraph(entityId, userId, stringHandle.StringView, graph, loadSettings, settingsStructSize, out loadRequestId);
                }
            }
            else
            {
                return ovrAvatar2Entity_LoadUserFromGraph(entityId, userId, graph, loadSettings, out loadRequestId);
            }
        }

        [Obsolete("Use `OvrAvatar2Entity_LoadUserFromGraphWithFiltersFast` instead!", false)]
        public static ovrAvatar2Result OvrAvatarEntity_LoadUserFromGraphWithFiltersFast(ovrAvatar2EntityId entityId,
            UInt64 userId, ovrAvatar2Graph graph, in ovrAvatar2EntityFilters loadFilters,
            bool prefetchOnly, bool validateCache, out ovrAvatar2LoadRequestId loadRequestId)
        {
            return ovrAvatar2Entity_LoadUserFromGraphWithFiltersFast_Impl(
                entityId, userId, UserAvatarConfigIds, graph, in loadFilters, prefetchOnly, validateCache, out loadRequestId);
        }

        public static ovrAvatar2Result OvrAvatar2Entity_LoadUserFromGraphWithFiltersFast(ovrAvatar2EntityId entityId,
            UInt64 userId, ovrAvatar2Graph graph, in ovrAvatar2EntityFilters loadFilters,
            bool prefetchOnly, bool validateCache, out ovrAvatar2LoadRequestId loadRequestId)
        {
            return ovrAvatar2Entity_LoadUserFromGraphWithFiltersFast_Impl(
                entityId, userId, UserAvatarConfigIds, graph, in loadFilters, prefetchOnly, validateCache, out loadRequestId);
        }


        /// Update the access token.  See ovr_User_GetAccessToken() in the Oculus Platform SDK.
        /// \param token the access token
        /// \param graph to associate token with
        /// Returns result codes:
        ///   ovrAvatar2Result_Success - token string was not null
        ///   ovrAvatar2Result_BadParameter - token is null
        ///   ovrAvatar2Result_NotInitialized - ovrAvatar2 is currently not initialized
        ///
        internal static bool OvrAvatar2_UpdateAccessTokenForGraph(string token, ovrAvatar2Graph graph)
        {
            using var stringHandle = new StringHelpers.StringViewAllocHandle(token, Allocator.Persistent);
            unsafe
            {
                return ovrAvatar2_UpdateAccessTokenForGraph(stringHandle.StringView.data, graph)
                    .EnsureSuccess("ovrAvatar2_UpdateAccessTokenForGraph", AvatarCapiLogScope);
            }
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern unsafe ovrAvatar2Result ovrAvatar2_UpdateAccessTokenForGraph(byte* token, ovrAvatar2Graph graph);
    }
}
