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
    /// <summary>
    /// Data needed to drive face tracking of an avatar.
    /// </summary>
    public sealed class OvrAvatarFacePose
    {
        public readonly float[] expressionWeights = new float[(int)CAPI.ovrAvatar2FaceExpression.Count];
        public readonly float[] expressionConfidence = new float[(int)CAPI.ovrAvatar2FaceExpression.Count];
        public Int64 sampleTimeNS;

        internal static CAPI.ovrAvatar2FacePose GenerateEmptyNativePose()
        {
            var native = new CAPI.ovrAvatar2FacePose();
            native.expressionWeights = new float[(int)CAPI.ovrAvatar2FaceExpression.Count];
            native.expressionConfidence = new float[(int)CAPI.ovrAvatar2FaceExpression.Count];
            return native;
        }

        #region Native Conversions
        internal CAPI.ovrAvatar2FacePose ToNative()
        {
            CAPI.ovrAvatar2FacePose native = GenerateEmptyNativePose();
            for (var i = 0; i < expressionWeights.Length; i++)
            {
                native.expressionWeights[i] = expressionWeights[i];
            }

            for (var i = 0; i < expressionConfidence.Length; i++)
            {
                native.expressionConfidence[i] = expressionConfidence[i];
            }

            return native;
        }

        internal void FromNative(in CAPI.ovrAvatar2FacePose native)
        {
            for (var i = 0; i < expressionWeights.Length; i++)
            {
                expressionWeights[i] = native.expressionWeights[i];
            }

            for (var i = 0; i < expressionConfidence.Length; i++)
            {
                expressionConfidence[i] = native.expressionConfidence[i];
            }
        }
        #endregion
    }
}
