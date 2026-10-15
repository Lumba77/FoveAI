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

using System;
using System.Collections.Generic;

using Unity.Collections;
using Unity.IL2CPP.CompilerServices;
using UnityEngine;

using static Oculus.Avatar2.CAPI;

namespace Oculus.Avatar2
{
    public interface IInterpolationValueProvider
    {
        // Will return a value between 0.0 and 1.0 (inclusive)
        float GetRenderInterpolationValue();
    }

    // Partial class intended to encapsulate "avatar animation" related functionality.
    // Mainly related to "morph targets" and "skinning"
    public partial class OvrAvatarEntity
    {
        private EntityAnimatorBase _entityAnimator;
        private IInterpolationValueProvider _interpolationValueProvider;

        // Setting this to false allows disabling morph targets on remote avatars
        protected bool _isMorphTargetsEnabled = true;

        #region Entity Animators

        private abstract class EntityAnimatorBase
        {
            protected readonly OvrAvatarEntity Entity;

            protected EntityAnimatorBase(OvrAvatarEntity entity)
            {
                Entity = entity;
            }

            private readonly List<PrimitiveRenderData> _addNewAnimationFrameCache = new List<PrimitiveRenderData>();
            public virtual void AddNewAnimationFrame(
                float timestamp,
                float deltaTime,
                in CAPI.ovrAvatar2Pose entityPose,
                in CAPI.ovrAvatar2EntityRenderState renderState)
            {
                // If a remote avatar is playing back streaming packet, update pose and morph targets.
                var isPlayingStream = !Entity.IsLocal && Entity.GetStreamingPlaybackState().HasValue;

                bool skeletalAnimation = isPlayingStream || Entity.HasAnyFeatures(UPDATE_POSE_FEATURES);
                bool morphAnimation = isPlayingStream || Entity.HasAnyFeatures(UPDATE_MOPRHS_FEATURES);

                if (Entity._isMorphTargetsEnabled && (skeletalAnimation || morphAnimation) && Entity.ShouldRender())
                {
                    _addNewAnimationFrameCache.Clear();
                    Entity.BroadcastAnimationPreUpdate(_addNewAnimationFrameCache);

                    Entity.BroadcastAnimationUpdate(
                        skeletalAnimation,
                        morphAnimation,
                        entityPose,
                        renderState,
                        _addNewAnimationFrameCache);
                }

                Entity.MonitorJoints(in entityPose);
            }

            public abstract void UpdateAnimationTime(float deltaTime, bool isAllAnimationDataValid);
        }

        private sealed class EntityAnimatorMotionSmoothing : EntityAnimatorBase, IInterpolationValueProvider
        {
            // Currently using as a double buffering setup with only two frames, FrameA and FrameB
            // No pending frames are stored, as new frames come in before previous render frames are finished,
            // old frames are dropped
            private static readonly int NUM_ANIMATION_FRAMES = 2;

            private sealed class AnimationFrameInfo
            {
                public float Timestamp { get; private set; }

                public bool IsValid { get; private set; }

                public void UpdateValues(float time)
                {
                    Timestamp = time;
                    IsValid = true;
                }
            }

            // In this implementation, no pending frames are held, only  2 "animation frames"
            // are held on to
            private readonly AnimationFrameInfo[] _animationFrameInfo = new AnimationFrameInfo[NUM_ANIMATION_FRAMES];
            private float _latestAnimationFrameTime;
            private int _nextAnimationFrameIndex;

            private bool _hasTwoValidAnimationFrames;

            private float _interpolationValue;

            private int EarliestAnimationFrameIndex => _nextAnimationFrameIndex;
            private int LatestAnimationFrameIndex => 1 - _nextAnimationFrameIndex;

            public EntityAnimatorMotionSmoothing(OvrAvatarEntity entity) : base(entity)
            {
                for (int i = 0; i < _animationFrameInfo.Length; i++)
                {
                    _animationFrameInfo[i] = new AnimationFrameInfo();
                }
            }

            public float GetRenderInterpolationValue()
            {
                return _interpolationValue;
            }

            public override void AddNewAnimationFrame(
                float timestamp,
                float deltaTime,
                in CAPI.ovrAvatar2Pose entityPose,
                in CAPI.ovrAvatar2EntityRenderState renderState)
            {
                base.AddNewAnimationFrame(timestamp, deltaTime, entityPose, renderState);
                AddNewAnimationFrameTime(timestamp, deltaTime);
            }

            public override void UpdateAnimationTime(float deltaTime, bool isAllAnimationDataValid)
            {
                CalculateInterpolationValue(deltaTime, isAllAnimationDataValid);
            }

            private void AddNewAnimationFrameTime(float timestamp, float deltaTime)
            {
                // In this implementation, there are no historical/pending frames on top of the "render frames"
                // (the frames currently rendered/interpolated between).
                // Note the time of the frame to be added
                _animationFrameInfo[_nextAnimationFrameIndex].UpdateValues(timestamp);

                // Advance/ping pong frame index
                _nextAnimationFrameIndex =
                    1 - _nextAnimationFrameIndex; // due to there only being 2 frames, this will ping pong

                if (!_hasTwoValidAnimationFrames && _animationFrameInfo[1].IsValid)
                {
                    _hasTwoValidAnimationFrames = true;
                }

                if (_hasTwoValidAnimationFrames)
                {
                    var earliestFrame = _animationFrameInfo[EarliestAnimationFrameIndex];

                    // Fast forward/rewind render frame time to be the earliest frame's timestamp minus the delta.
                    // This has two effects:
                    // 1) If the frame generation frequency changes to be faster (i.e. frames at 0, 1, 1.5),
                    //    then this logic "fast forwards" the render time which may cause a jump in animation, but
                    //    keeps the "interpolation window" (the time that fake animation data is generated) to
                    //    be the smallest possible.
                    // 2) If the frame generate frequency slows down (i.e. frames at 0, 0.5, 2), then this logic
                    //    "rewinds" the render time which will cause the animation to not skip any of the animation
                    //    window
                    _latestAnimationFrameTime = earliestFrame.Timestamp - deltaTime;
                }
            }

            private void CalculateInterpolationValue(float delta, bool isAllAnimationDataValid)
            {
                // Can only advance if there are 2 or more valid render frames
                if (!_hasTwoValidAnimationFrames)
                {
                    _interpolationValue = 0.0f;
                    return;
                }

                _latestAnimationFrameTime += delta;

                // For "motion smoothing" any OvrAvatarSkinnedRenderable subclass that is going to be rendered,
                // ideally, will be rendered with "completely valid render data". Unfortunately that might not be
                // the case (at the moment, until LOD transitions happen differently).
                // The "joint monitoring" however is done on a per entity
                // basis (the renderables all share a common single skeleton).
                // For both the joint monitor and the renderables to all have the same interpolation value,
                // they will all pull from the same source/get passed the same value instead of calculating
                // it themselves (which will also save computation).
                // Given these facts, there needs to be some coupling so that the calculation of the interpolation
                // value knows if all of the renderables being rendered in a given frame have complete valid data.

                // If all renderables' data is completely valid, then interpolation value can be calculated as normal, otherwise, it will
                // be clamped to 1.0
                if (!isAllAnimationDataValid)
                {
                    // Not all skinned renderables have "completely valid animation data".
                    // Return 1.0 so that the renderables + joints are rendering their
                    // latest (and only guaranteed valid) animation frame
                    _interpolationValue = 1.0f;
                    return;
                }

                float t0 = _animationFrameInfo[EarliestAnimationFrameIndex].Timestamp;
                float t1 = _animationFrameInfo[LatestAnimationFrameIndex].Timestamp;

                // InverseLerp clamps to 0 to 1
                _interpolationValue = Mathf.InverseLerp(t0, t1, _latestAnimationFrameTime);
            }
        }

        private sealed class EntityAnimatorDefault : EntityAnimatorBase
        {
            public EntityAnimatorDefault(OvrAvatarEntity entity) : base(entity)
            {
            }

            public override void UpdateAnimationTime(float deltaTime, bool isAllAnimationDataValid)
            {
                // Intentionally empty
            }
        }

        #endregion

        #region Runtime

        public void SetMorphTargetsEnabled(bool morphTargetsEnabled)
        {
            _isMorphTargetsEnabled = morphTargetsEnabled;
        }

        // Loop over all skinned renderables, updating the "animation enabled" state and keeping track of which ones
        // are animation enabled
        private void AppendPrimitivesWithAnimationEnabled(List<PrimitiveRenderData> renderDataOut, List<OvrAvatarSkinnedRenderable> renderablesOut)
        {
            foreach (var primRenderables in _visiblePrimitiveRenderers)
            {
                if (primRenderables == null)
                {
                    continue;
                }
                foreach (var primRenderable in primRenderables)
                {
                    var skinnedRenderable = primRenderable.skinnedRenderable;
                    // TODO: Remove this expensive `GameObject.==` check
                    if (!primRenderable.hasSkinnedRenderable || !skinnedRenderable.enabled)
                    {
                        continue;
                    }

                    if (skinnedRenderable.IsAnimationEnabled)
                    {
                        // ASSUMPTION: renderDataOut is non-null
                        renderDataOut.Add(primRenderable);
                        renderablesOut.Add(skinnedRenderable);
                    }
                }
            }
        }

        private void SampleSkinningOrigin(in CAPI.ovrAvatar2PrimitiveRenderState primState,
            out CAPI.ovrAvatar2Transform skinningOrigin)
        {
            skinningOrigin = primState.skinningOrigin;

#if OVR_AVATAR_DISABLE_CLIENT_XFORM
            skinningOrigin.scale.z *= -1f;
            skinningOrigin = skinningOrigin.ConvertSpace();
#endif
        }

        private readonly List<OvrAvatarSkinnedRenderable> _broadcastAnimationPreUpdateCache
            = new List<OvrAvatarSkinnedRenderable>();

        private void BroadcastAnimationPreUpdate(List<PrimitiveRenderData> animationEnabledDataOut)
        {
            using var livePerfMarker = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Entity_BroadcastAnimationPreUpdate);
            // Due to the fact that calling AnimationFramePreUpdate may trigger
            // some LOD transitions which in turn, may alter the IsAnimationEnabled
            // value of a OvrAvatarSkinnedRenderable, call "animation pre frame" of
            // first and also double check the "animation enabled" status here before sending
            // the "AnimationFrameUpdate".

            // The expected size of the "_broadcastAnimationFrameStartCache" is in the order
            // of 1-10, so doing another loop over shouldn't be as costly as populating
            // the loop initially
            _broadcastAnimationPreUpdateCache.Clear();
            AppendPrimitivesWithAnimationEnabled(animationEnabledDataOut, _broadcastAnimationPreUpdateCache);

            foreach (var skinnedRenderable in _broadcastAnimationPreUpdateCache)
            {
                try
                {
                    // ASSUMPTION: AppendPrimitivesWithAnimationEnabled will handle checking for
                    // a skinned renderable, no null check needed here
                    skinnedRenderable.AnimationFramePreUpdate();
                }
                catch (Exception e)
                {
                    OvrAvatarLog.LogException("AnimationFramePreUpdate", e, logScope, this);
                }
            }

            // Loop over list again, removing skinned renderables that are no longer "animation enabled"
            // due to the "AnimationFramePreUpdate" call above
            for (int i = animationEnabledDataOut.Count - 1; i >= 0; i--)
            {
                if (!_broadcastAnimationPreUpdateCache[i].IsAnimationEnabled)
                {
                    animationEnabledDataOut.RemoveAt(i);
                }
            }
        }

        private void BroadcastAnimationUpdate(
            bool samplePose,
            bool sampleMorphTargets,
            in CAPI.ovrAvatar2Pose entityPose,
            in CAPI.ovrAvatar2EntityRenderState renderState,
            in List<PrimitiveRenderData> animatablePrimitives)
        {
            using var livePerfMarker = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Entity_BroadcastAnimationUpdate);

            // Are all SkinnedRenderables able to update without using Unity.Transform?
            bool needsFullTransformUpdate = false;
            {
                using var livePerfMarker_AnimationFrameUpdates = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Entity_AnimationFrameUpdates);
                foreach (var primRenderable in animatablePrimitives)
                {
                    var skinnedRenderable = primRenderable.skinnedRenderable;
                    Debug.Assert(skinnedRenderable != null);
                    Debug.Assert(skinnedRenderable.IsAnimationEnabled);

                    needsFullTransformUpdate |= !skinnedRenderable.AnimationFrameUpdate(
                        samplePose,
                        sampleMorphTargets,
                        entityId,
                        primRenderable.instanceId);
                }
            }

            if (samplePose)
            {
                SamplePrimitivesSkinningOrigin(renderState);

                OvrAvatarLog.AssertConstMessage(
                    entityPose.jointCount == SkeletonJointCount,
                    "entity pose does not match skeleton.",
                    logScope,
                    this);

                needsFullTransformUpdate |= (
                    _debugDrawing.drawSkelHierarchy ||
                    _debugDrawing.drawSkelHierarchyInGame ||
                    _debugDrawing.drawSkinTransformsInGame);

                // If JointMonitoring is enabled, it will update transforms
                if (_jointMonitor == null)
                {
                    using var livePerfMarker_UpdateSkeletonTransforms = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Entity_UpdateSkeletonTransforms);
                    if (needsFullTransformUpdate && _jointMonitor == null)
                    {
                        for (uint i = 0; i < entityPose.jointCount; ++i)
                        {
                            UpdateSkeletonTransformAtIndex(in entityPose, i);
                        }
                    }
                    else
                    {
                        foreach (var skeletonIdx in _unityUpdateJointIndices)
                        {
                            UpdateSkeletonTransformAtIndex(in entityPose, skeletonIdx);
                        }
                    }
                }
                else
                {
                    Debug.Assert(_unityUpdateJointIndices.Length == 0);
                }
            }
        }

        [Il2CppSetOption(Option.NullChecks, false)]
        private void SamplePrimitivesSkinningOrigin(in CAPI.ovrAvatar2EntityRenderState renderState)
        {
            // If Rendering_Prims is not enabled, there is nothing to do here
            if (!HasAnyFeatures(CAPI.ovrAvatar2EntityFeatures.Rendering_Prims)) { return; }
            // If there are 0 primitives, we already know all their origins :)
            if (renderState.primitiveCount == 0) { return; }
            using var livePerfMarker = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Entity_SamplePrimitivesSkinningOrigin);

            unsafe
            {
                uint primRSCount;
                uint primRSStride;
                CAPI.ovrAvatar2PrimitiveRenderState* primRS = CAPI.ovrAvatarXRender_GetPrimitiveRenderStates(entityId, out primRSCount, out primRSStride);
                if (primRSCount < renderState.primitiveCount)
                    return;
                for (uint i = 0; i < renderState.primitiveCount; ++i)
                {
                    if (_primitiveRenderables.ContainsKey(primRS->id))
                    {
                        foreach (PrimitiveRenderData primRend in _primitiveRenderables[primRS->id])
                        {
                            OvrAvatarSkinnedRenderable skinnedRenderable = primRend.skinnedRenderable;
                            if (skinnedRenderable is null)
                            {
                                // Non-skinned renderables just apply the transform
                                Transform transform = primRend.renderable.transform;
                                transform.ApplyOvrTransform(primRS->skinningOrigin);
                            }
                            else
                            {
                                // Otherwise call function on skinned renderable.
                                // Why does this needs to be called for all renderables
                                // but UpdateJointMatrices is only called on "visible renderers"?
                                // It would make sense if they were updated together
                                skinnedRenderable.UpdateSkinningOrigin(primRS->skinningOrigin);
                            }
                        }
                    }
                    primRS = (CAPI.ovrAvatar2PrimitiveRenderState*)((byte*)primRS + primRSStride);
                }
            } // end unsafe block
        }

        private void UpdateSkeletonTransformAtIndex(in CAPI.ovrAvatar2Pose entityPose, uint skeletonIdx)
        {
            var jointUnityTx = GetSkeletonTxByIndex(skeletonIdx);

            unsafe
            {
                CAPI.ovrAvatar2Transform* jointTransform = entityPose.localTransforms + skeletonIdx;
                if ((*jointTransform).IsNan()) return;

#if OVR_AVATAR_DISABLE_CLIENT_XFORM
                var jointParentIndex = entityPose.GetParentIndex(skeletonIdx);
                if (jointParentIndex != -1)
                {
                    jointUnityTx.ApplyOvrTransform(jointTransform);
                }
                else
                {
                    // HACK: Mirror rendering transforms across Z to fixup coordinate system errors
                    // Copy provided transform, we should not modify the source array
                    var flipScaleZ = *jointTransform;
                    flipScaleZ.scale.z = -flipScaleZ.scale.z;
                    jointUnityTx.ApplyOvrTransform(in flipScaleZ);
                }
#else
                jointUnityTx.ApplyOvrTransform(jointTransform);
#endif
            }
        }

        #endregion
    }
}
