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

using Oculus.Avatar2;
using UnityEngine;

public class AttachableSocket : MonoBehaviour
{
    private const float CANONICAL_SCALE_MINIMUM = 0.0001f;

    [Tooltip("Required. The Unique Name of the attachable socket. The name must be unique to the owning OvrAvatarEntity.")]
    public string SocketName;

    [Tooltip("Required. The Joint Type to attach this socket too. Note: The same Critical Joint must be exposed on the attached OvrAvatarEntity")]
    public CAPI.ovrAvatar2JointType JointType;

    [Tooltip("Required. Local Position of the socket, relative to the Critical Joint. Note: The axis is different from Unity")]
    public Vector3 Position;

    [Tooltip("Required. Local Rotation relative to the Critical Joint's rotation")]
    public Vector3 EulerAngles;

    [Tooltip("Optional. Scaling applied uniformly to the attached object, regardless of Avatar size.")]
    public Vector3 BaseScale = Vector3.one;

    [Tooltip("Optional. In meters. Scales the object in relation to the Avatar size. Only active if set over 0.0001f")]
    public float Width;

    [Tooltip("Optional. In meters. Scales the object in relation to the Avatar size. Only active if set over 0.0001f")]
    public float Depth;

    [Tooltip("Optional. In meters. Scales the object in relation to the Avatar size. Only active if set over 0.0001f")]
    public float Height;

    public bool ScaleGameObject = false;

    public OvrAvatarSocketDefinition Socket { get; private set; }

    private void Start()
    {
        var ovrAvatarEntity = GetComponent<OvrAvatarEntity>();
        if (ovrAvatarEntity == null)
        {
            return;
        }

        Socket = ovrAvatarEntity.CreateSocket(SocketName,
            JointType,
            Position,
            EulerAngles,
            BaseScale,
            Width > CANONICAL_SCALE_MINIMUM ? Width : null,
            Depth > CANONICAL_SCALE_MINIMUM ? Depth : null,
            Height > CANONICAL_SCALE_MINIMUM ? Height : null,
            true,
            ScaleGameObject);
    }
}
