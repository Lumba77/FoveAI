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

using Oculus.Avatar2;

namespace Oculus.Skinning.GpuSkinning
{
    /**
     * Component that encapsulates the meshes of a skinned avatar.
     * This component implements skinning using the Avatar SDK
     * and uses the GPU. It performs skinning on every avatar
     * at each frame. It is used when the skinning configuration
     * is set to SkinningConfig.OVR_UNITY_GPU_COMPUTE and motion smoothing
     * is *not* enabled in the GPU skinning configuration.
     *
     * @see OvrAvatarSkinnedRenderable
     * @see OvrAvatarComputeSkinnedRenderable
     * @see OvrGpuSkinningConfiguration.MotionSmoothing
     */
    public class OvrAvatarComputeSkinnedRenderable : OvrAvatarComputeSkinnedRenderableBase
    {
        protected override string LogScope => nameof(OvrAvatarComputeSkinnedRenderable);

        // Only need single frame of "animation/skinning data" before validity
        protected override int NumAnimationFramesBeforeValidData => 1;

        // Only need a single output frame
        internal override OvrComputeUtils.MaxOutputFrames MeshAnimatorOutputFrames =>
            OvrComputeUtils.MaxOutputFrames.ONE;

        protected override void OnAnimationEnabledChanged(bool isNowEnabled)
        {
            if (isNowEnabled)
            {
                NumValidAnimationFrames = 0;
            }
        }

        internal override void AnimationFramePreUpdate()
        {
            // ASSUMPTION: This call will always be followed by calls to update morphs and/or skinning.
            // With that assumption, new data will be written by the morph target combiner and/or skinner, so there
            // will be valid data at end of frame.
            IncrementValidAnimationFramesIfNeeded();
        }

        internal override void RenderFrameUpdate()
        {
            // Intentionally empty
        }
    }
}
