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
    public partial class OvrAvatarEntity : UnityEngine.MonoBehaviour
    {
        private CAPI.ovrAvatar2EntityId CreateNativeEntity(in CAPI.ovrAvatar2EntityCreateInfo info)
        {
            if (!info.IsValid)
            {
                OvrAvatarLog.LogWarning("Attempted to create entity with invalid info", logScope, this);
                return CAPI.ovrAvatar2EntityId.Invalid;
            }
            if (!CAPI.OvrAvatar2Entity_Create(in info, this, out var entityId))
            {
                OvrAvatarLog.LogError($"Failed to create entity on gameObject:`{name}`", logScope, this);
                return CAPI.ovrAvatar2EntityId.Invalid;
            }
            return entityId;
        }

        private bool DestroyNativeEntity()
        {
            if (entityId == CAPI.ovrAvatar2EntityId.Invalid)
            {
                OvrAvatarLog.LogWarning("Attempted to destroy entity with invalid ID", logScope, this);
                return false;
            }
            if (!CAPI.OvrAvatar2Entity_Destroy(entityId, this))
            {
                OvrAvatarLog.LogError($"Failed to destroy entity on gameObject:`{name}`", logScope, this);
                return false;
            }
            OvrAvatarLog.LogVerbose("Successfully destroyed native entity", logScope, this);
            entityId = CAPI.ovrAvatar2EntityId.Invalid;
            return true;
        }
    }

    public static partial class CAPI
    {
        private const string lifeCycleScope = "lifecycle";

        /// Create an entity, allocating memory
        /// \param info - configuration for new entity
        /// \param context - OvrAvatarEntity instance which will own this native entity
        /// \param newEntityId - native entityId of new entity, or `Invalid` if errors detected
        /// \return result code
        ///
        internal static bool OvrAvatar2Entity_Create(in ovrAvatar2EntityCreateInfo info, OvrAvatarEntity context
            , out ovrAvatar2EntityId newEntityId)
        {
            OvrAvatarLog.Assert(info.IsValid, lifeCycleScope, context);
            return ovrAvatar2Entity_Create(in info, out newEntityId)
                .EnsureSuccess("ovrAvatar2Entity_Create", lifeCycleScope, context);
        }

        /// Destroy an entity, releasing all related memory
        /// \param entity to destroy
        /// \return result code
        ///
        internal static bool OvrAvatar2Entity_Destroy(ovrAvatar2EntityId entityId, OvrAvatarEntity context)
        {
            OvrAvatarLog.Assert(entityId != ovrAvatar2EntityId.Invalid, lifeCycleScope, context);
            return ovrAvatar2Entity_Destroy(entityId)
                .EnsureSuccess("ovrAvatar2Entity_Destroy", lifeCycleScope, context);
        }
    }
}
