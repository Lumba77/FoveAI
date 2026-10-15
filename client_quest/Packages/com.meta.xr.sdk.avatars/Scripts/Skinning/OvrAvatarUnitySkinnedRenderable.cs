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
using System.Runtime.InteropServices;

using Oculus.Avatar2;

using Unity.Collections;

using UnityEngine;

using static Oculus.Avatar2.CAPI;

/// @file OvrAvatarUnitySkinnedRenderable.cs

namespace Oculus.Skinning
{
    /**
     * Component that encapsulates the meshes of a skinned avatar.
     * This component implements skinning using Unity.
     * It is used when the skinning configuration is set
     * to *SkinningConfig.UNITY*.
     *
     * @see OvrAvatarSkinnedRenderable
     * @see OvrAvatarGpuSkinnedRenderable
     * @see OvrAvatarEntity.SkinningConfig
     */
    public class OvrAvatarUnitySkinnedRenderable : OvrAvatarSkinnedRenderable
    {
        // Unity skinning animation data is "always valid"
        protected override int NumAnimationFramesBeforeValidData => 0;

        [SerializeField]
        [Tooltip("Configuration to override SkinQuality, otherwise indicates which Quality was selected for this LOD")]
        private SkinQuality _skinQuality = SkinQuality.Auto;

        public SkinQuality SkinQuality
        {
            get => _skinQuality;
            set
            {
                if (_skinQuality != value)
                {
                    _skinQuality = value;
                    UpdateSkinQuality();
                }
            }
        }
        private void UpdateSkinQuality()
        {
            if (_hasValidSkinnedRenderer)
            {
                SkinnedRenderer.quality = _skinQuality;
            }
        }

        private SkinnedMeshRenderer _skinnedRenderer;
        private SkinnedMeshRenderer SkinnedRenderer
        {
            get => _skinnedRenderer;
            set
            {
                if (_skinnedRenderer != value)
                {
                    _skinnedRenderer = value;
                    _hasValidSkinnedRenderer = _skinnedRenderer != null;
                }
            }
        }

        private DummySkinningBufferPropertySetter _dummyBufferSetter;

        private NativeArray<float> _morphWeightsArray;

        protected override void Awake()
        {
            base.Awake();

            _dummyBufferSetter = new DummySkinningBufferPropertySetter();
            NumValidAnimationFrames = 0;
        }

        protected override void AddDefaultRenderer()
        {
            SkinnedRenderer = AddRenderer<SkinnedMeshRenderer>();
        }

        protected internal override void ApplyMeshPrimitive(OvrAvatarPrimitive primitive)
        {
            base.ApplyMeshPrimitive(primitive);

            if (_skinQuality == SkinQuality.Auto)
            {
                _skinQuality = QualityForLODIndex(primitive.HighestQualityLODIndex);
            }

            if (_hasValidSkinnedRenderer)
            {
                SkinnedRenderer.sharedMesh = MyMesh;
                SkinnedRenderer.quality = _skinQuality;
            }

            var morphCount = primitive.morphTargetCount;
            if (morphCount > 0)
            {
                _morphWeightsArray = new NativeArray<float>((int)morphCount, Allocator.Persistent);
                CacheMorphUpdateAbility();
            }

            rendererComponent.GetPropertyBlock(MatBlock);
            _dummyBufferSetter.SetComputeSkinningBuffersInMatBlock(MatBlock);
            rendererComponent.SetPropertyBlock(MatBlock);
        }

        public override void ApplySkeleton(Transform[] bones)
        {
            if (_hasValidSkinnedRenderer && SkinnedRenderer.sharedMesh)
            {
                SkinnedRenderer.rootBone = transform;
                SkinnedRenderer.bones = bones;

                // This must be set after SkinnedMeshRenderer.bones to prevent a "Bones do not match bindpose" error
                SkinnedRenderer.localBounds = AppliedPrimitive.hasBounds ? AppliedPrimitive.mesh.bounds : FixedBounds;
            }
            else
            {
                OvrAvatarLog.LogError("Had no shared mesh to apply skeleton to!");
            }
        }


        private void UpdateMorphTargets(CAPI.ovrAvatar2EntityId entityId, CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
        {
            if (!_canUpdateMorphs)
            {
                return;
            }

            // _canUpdateMorphs check above should handle validity checks
            var success = FetchMorphTargetWeights(
                entityId,
                primitiveInstanceId,
                _morphWeightsArray.GetIntPtr(),
                _morphWeightsArray.GetBufferSize(), logScope);

            if (success)
            {
                // Use pointers here to avoid NativeArray [] operator overhead
                unsafe
                {
                    var weightsPtr = _morphWeightsArray.GetPtr();
                    for (int morphTargetIndex = 0; morphTargetIndex < _morphWeightsArray.Length; ++morphTargetIndex)
                    {
                        SkinnedRenderer.SetBlendShapeWeight(morphTargetIndex, *weightsPtr++);
                    }
                }
            }
        }

        private bool UpdateJointMatrices()
        {
            // No-op
            // TODO: Update transforms here
            return false;
        }

        protected override void OnAnimationEnabledChanged(bool isNowEnabled)
        {
            // Intentionally empty
        }

        internal override void AnimationFramePreUpdate()
        {
            // Intentionally empty
        }

        internal override bool AnimationFrameUpdate(
            bool updateJoints,
            bool updateMorphs,
            CAPI.ovrAvatar2EntityId entityId,
            CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
        {
            using var livePerfMarker = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Skinned_Unity_AnimationFrameUpdate);
            bool jointsUpdated = false;
            if (updateJoints)
            {
                jointsUpdated = UpdateJointMatrices();
            }

            if (updateMorphs)
            {
                UpdateMorphTargets(entityId, primitiveInstanceId);
            }

            return jointsUpdated;
        }

        internal override void RenderFrameUpdate()
        {
            // Intentionally empty
        }

        private static SkinQuality QualityForLODIndex(uint lodIndex)
        {
            return OvrAvatarManager.Instance.GetUnitySkinQualityForLODIndex(lodIndex);
        }

        protected override void Dispose(bool isMainThread)
        {
            SkinnedRenderer = null;
            _dummyBufferSetter?.Dispose();

            if (isMainThread)
            {
                _morphWeightsArray.Reset();
            }

            base.Dispose(isMainThread);
        }

        private void CacheMorphUpdateAbility()
        {
            _canUpdateMorphs = _hasValidSkinnedRenderer && _morphWeightsArray.IsCreated;
        }


        // TODO: FixedBounds should definitely be removed ASAP
        private static Bounds FixedBounds
            => new Bounds(new Vector3(0f, 0.5f, 0.0f), new Vector3(2.0f, 2.0f, 2.0f));

        private bool _hasValidSkinnedRenderer;
        private bool _canUpdateMorphs;

#if UNITY_EDITOR
        protected virtual void OnValidate()
        {
            UpdateSkinQuality();
        }
#endif
    }
}
