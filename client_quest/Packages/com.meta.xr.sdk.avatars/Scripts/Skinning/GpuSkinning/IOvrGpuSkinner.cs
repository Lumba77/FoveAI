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

using Oculus.Avatar2;

using Unity.Collections;

using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace Oculus.Skinning.GpuSkinning
{
    internal abstract class IOvrGpuSkinner
    {
        public abstract GraphicsFormat GetOutputTexGraphicFormat();
        public abstract RenderTexture GetOutputTex();
        public abstract CAPI.ovrTextureLayoutResult GetLayoutInOutputTex(OvrSkinningTypes.Handle handle);
        public abstract void EnableBlockToRender(OvrSkinningTypes.Handle handle, SkinningOutputFrame outputFrame);
        public abstract void UpdateOutputTexture();
        public abstract bool HasJoints { get; }
        public abstract OvrAvatarSkinningController ParentController { get; set; }
        public abstract IntPtr GetJointTransformMatricesArray(OvrSkinningTypes.Handle handle);
        public abstract void Destroy();
    }
}
