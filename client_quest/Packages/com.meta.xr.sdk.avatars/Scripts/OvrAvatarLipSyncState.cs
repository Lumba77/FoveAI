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

/// @file OvrAvatarLipSyncState.cs

namespace Oculus.Avatar2
{
    /**
     * Collects the viseme weights for avatar lip motion and
     * converts to and from C# and C++ native versions.
     * @see ovrAvatar2Viseme
     */
    public sealed class OvrAvatarLipSyncState
    {
        /**
         * How hard the avatar is laughing???
         */
        public float laughterScore;

        /**
         * Array of viseme weights.
         * @see CAPI.ovrAvatar2Viseme
         */
        public readonly float[] visemes = new float[(int)CAPI.ovrAvatar2Viseme.Count];

        #region Native Conversions
        /**
         * Creates a new native lip tracking state from this C# instance.
         * @see CAPI.ovrAvatar2LipSyncState
         * @see FromNative
         */
        internal CAPI.ovrAvatar2LipSyncState ToNative()
        {
            var native = new CAPI.ovrAvatar2LipSyncState
            {
                laughterScore = laughterScore,
            };
            unsafe
            {
                for (var i = 0; i < visemes.Length; i++)
                {
                    native.visemes[i] = visemes[i];
                }
            }

            return native;
        }

        /**
         * Copies the given native lip tracking state to this C# instance.
         * @see CAPI.ovrAvatar2LipSyncState
         * @see ToNative
         */
        internal void FromNative(ref CAPI.ovrAvatar2LipSyncState native)
        {
            unsafe
            {
                for (var i = 0; i < visemes.Length; i++)
                {
                    visemes[i] = native.visemes[i];
                }
            }

            laughterScore = native.laughterScore;
        }
        #endregion
    }
}
