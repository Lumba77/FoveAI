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

using UnityEngine;

namespace Oculus.Avatar2
{
    /// <summary>
    /// MonoBehaviour that identifier the version of the rig
    /// </summary>
    public class OvrAvatarRigVersionIdentifier : MonoBehaviour
    {
        public RigVersion Version = RigVersion.V3;
    }

    public enum RigVersion
    {
        V3,
        V5,
    }
}
