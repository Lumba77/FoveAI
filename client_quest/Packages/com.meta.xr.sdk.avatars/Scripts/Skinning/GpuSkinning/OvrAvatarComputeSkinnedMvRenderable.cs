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
     * but not at every frame. Instead, it interpolates between
     * frames, reducing the performance overhead of skinning
     * when there are lots of avatars. It is used when the skinning configuration
     * is set to SkinningConfig.OVR_UNITY_GPU_COMPUTE, , motion smoothing
     * is *not* enabled, and "App Space Warp" is enabled in the GPU skinning configuration.
     *
     * @see OvrAvatarSkinnedRenderable
     * @see OvrAvatarComputeSkinnedRenderable
     * @see OvrGpuSkinningConfiguration.SupportApplicationSpacewarp
     */
    public class OvrAvatarComputeSkinnedMvRenderable : OvrAvatarComputeSkinnedRenderableBase
    {
        protected override int NumAnimationFramesBeforeValidData => 1;
        protected override string LogScope => nameof(OvrAvatarComputeSkinnedMvRenderable);

        // Only need 2 single output frames (one for current frame, one for previous frame)
        internal override OvrComputeUtils.MaxOutputFrames MeshAnimatorOutputFrames =>
            OvrComputeUtils.MaxOutputFrames.TWO;

        // Only 1 "animation frame" is required for this renderable's animation frames to be valid (not interpolating)
        private bool _hasValidPreviousRenderFrame;

        private SkinningOutputFrame _prevRenderWriteDest = SkinningOutputFrame.FrameZero;

        protected override void OnAnimationEnabledChanged(bool isNowEnabled)
        {
            if (isNowEnabled)
            {
                NumValidAnimationFrames = 0;
                AnimatorWriteDestination = SkinningOutputFrame.FrameOne;
            }
        }

        protected virtual void OnEnable()
        {
            // Reset the previous render frame slice and render frame count
            _hasValidPreviousRenderFrame = false;
            _prevRenderWriteDest = AnimatorWriteDestination;
        }

        internal override void AnimationFramePreUpdate()
        {
            // ASSUMPTION: This call will always be followed by calls to update morphs and/or skinning.
            // With that assumption, new data will be written by the morph target combiner and/or skinner, so there
            // will be valid data at end of frame.
            IncrementValidAnimationFramesIfNeeded();

            AnimatorWriteDestination = GetNextOutputFrame(AnimatorWriteDestination, MeshAnimatorOutputFrames);
        }

        internal override void RenderFrameUpdate()
        {
            // Need at least 1 "previous render frame"
            if (!_hasValidPreviousRenderFrame)
            {
                // Not enough render frames, just make the motion vectors "previous frame" the same
                // as the current one
                _prevRenderWriteDest = AnimatorWriteDestination;
                _hasValidPreviousRenderFrame = true;
            }

            SetRenderFrameOutputSlices();

            // Update "previous frame" value for next frame
            _prevRenderWriteDest = AnimatorWriteDestination;
        }

        private void SetRenderFrameOutputSlices()
        {
            rendererComponent.GetPropertyBlock(MatBlock);

            MatBlock.SetInt(PropIds.AttributeOutputLatestAnimFrameEntryOffset, (int)AnimatorWriteDestination);
            MatBlock.SetInt(PropIds.AttributeOutputPrevRenderFrameLatestAnimFrameOffset, (int)_prevRenderWriteDest);

            rendererComponent.SetPropertyBlock(MatBlock);
        }
    }
}
