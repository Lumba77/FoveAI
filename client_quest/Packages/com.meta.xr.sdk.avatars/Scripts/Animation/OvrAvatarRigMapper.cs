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

using System.Collections.Generic;
using UnityEngine;

namespace Oculus.Avatar2
{
    /// <summary>
    /// A mapper class that maps rt-rig v3 to rt-rig v5
    /// </summary>
    internal class OvrAvatarRigMapper
    {
        private Dictionary<string, Matrix4x4> _rt3ToRt5Map;

        internal OvrAvatarRigMapper(string rigJson)
        {
            _rt3ToRt5Map = DeserializeJointDeltaMatrices(rigJson);
        }

        internal IEnumerable<string> GetMappedJointNames()
        {
            return _rt3ToRt5Map.Keys;
        }

        internal bool TryGetTranformMatrix(string joint, out Matrix4x4 transformMatrix)
        {
            return _rt3ToRt5Map.TryGetValue(joint, out transformMatrix);
        }

        internal bool TryGetConvertedLocalMatrix(string jointName, Transform v3JointTransform, out Matrix4x4 convertedLocalMatrix)
        {
            if (!_rt3ToRt5Map.TryGetValue(jointName, out var transformMatrix))
            {
                convertedLocalMatrix = Matrix4x4.identity;
                return false;
            }

            convertedLocalMatrix = transformMatrix * Matrix4x4.TRS(v3JointTransform.localPosition, v3JointTransform.localRotation, v3JointTransform.localScale);
            return true;
        }

        internal static string SerializeJointDeltaMatrices(Dictionary<string, Matrix4x4> jointDeltas)
        {
            var jointDeltaArray = new List<JointDelta>();
            foreach (var jointDeltaEntry in jointDeltas)
            {
                jointDeltaArray.Add(new JointDelta { Name = jointDeltaEntry.Key, Delta = jointDeltaEntry.Value });
            }

            return JsonUtility.ToJson(new JointDeltaArray { Deltas = jointDeltaArray.ToArray() });
        }

        internal static Dictionary<string, Matrix4x4> DeserializeJointDeltaMatrices(string json)
        {
            var result = new Dictionary<string, Matrix4x4>();
            var jointDeltaArray = JsonUtility.FromJson<JointDeltaArray>(json);
            for (var i = 0; i < jointDeltaArray.Deltas?.Length; i++)
            {
                var entry = jointDeltaArray.Deltas![i];
                result.Add(entry.Name!, entry.Delta);
            }

            return result;
        }

        [System.Serializable]
        private class JointDelta
        {
            public string? Name;
            public Matrix4x4 Delta;
        }

        [System.Serializable]
        private class JointDeltaArray
        {
            public JointDelta[]? Deltas;
        }
    }
}
