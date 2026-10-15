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

using Oculus.Avatar2.Experimental;

namespace Oculus.Avatar2
{
    public static class OvrAvatarEntitlement
    {
        private const string logScope = "entitlement";

        private static string[] s_accessTokens = null;
        // ReSharper disable once HeapView.ObjectAllocation.Evident
        private static string[] AccessTokens => s_accessTokens ??= new string[(int)CAPI.ovrAvatar2Graph.Count];

        private static bool IsValid(CAPI.ovrAvatar2Graph graph)
            => CAPI.ovrAvatar2Graph.First <= graph && graph <= CAPI.ovrAvatar2Graph.Last;

        private static int GetIndex(CAPI.ovrAvatar2Graph graph) => (int)graph - (int)CAPI.ovrAvatar2Graph.First;

        public static void SetAccessToken(string token, CAPI.ovrAvatar2Graph graph = CAPI.ovrAvatar2Graph.Oculus)
        {
            if (CAPI.OvrAvatar2_UpdateAccessTokenForGraph(token, graph))
            {
                AccessTokens[GetIndex(graph)] = token;
            }
        }

        public static void ResendAccessToken(CAPI.ovrAvatar2Graph graph = CAPI.ovrAvatar2Graph.Oculus)
        {
            if (!AccessTokenIsValid(graph))
            {
                OvrAvatarLog.LogError(
                    $"Cannot resend access token when there is no valid token for graph {graph}.", logScope);
                return;
            }
            SetAccessToken(AccessTokens[GetIndex(graph)], graph);
        }


        public static bool AccessTokenIsValid(CAPI.ovrAvatar2Graph graph = CAPI.ovrAvatar2Graph.Oculus)
            => IsValid(graph) && !String.IsNullOrEmpty(AccessTokens[GetIndex(graph)]);
    }
}
