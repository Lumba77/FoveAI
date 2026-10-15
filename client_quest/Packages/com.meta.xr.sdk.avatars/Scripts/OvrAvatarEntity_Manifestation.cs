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

namespace Oculus.Avatar2
{
    public partial class OvrAvatarEntity
    {
        // TODO: Should probably be private/internal?
        public bool GetAvailableManifestationFlags(out UInt32 manifestationFlags)
        {
            return CAPI.ovrAvatar2Entity_GetAvailableManifestationFlags(entityId, out manifestationFlags)
                .EnsureSuccess("ovrAvatar2Entity_GetAvailableManifestationFlags", logScope, this);
        }

        // TODO: Should probably be private/internal?
        public bool GetManifestationFlags(out CAPI.ovrAvatar2EntityManifestationFlags manifestationFlags)
        {
            return CAPI.ovrAvatar2Entity_GetManifestationFlags(entityId, out manifestationFlags)
                .EnsureSuccess("ovrAvatar2Entity_GetAvailableManifestationFlags", logScope, this);
        }

        // TODO: Should probably be private/internal?
        public bool SetManifestationFlags(CAPI.ovrAvatar2EntityManifestationFlags manifestation)
        {
            return CAPI.ovrAvatar2Entity_SetManifestationFlags(entityId, manifestation)
                .EnsureSuccess("ovrAvatar2Entity_SetManifestationFlags", logScope, this);
        }
    }
}
