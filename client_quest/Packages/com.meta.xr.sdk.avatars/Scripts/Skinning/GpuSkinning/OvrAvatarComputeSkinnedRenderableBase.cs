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

using Oculus.Avatar2;

using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;

using UnityEngine;
using UnityEngine.Profiling;

using static Oculus.Avatar2.CAPI;

namespace Oculus.Skinning.GpuSkinning
{
    public abstract class OvrAvatarComputeSkinnedRenderableBase : OvrAvatarSkinnedRenderable
    {
        protected abstract string LogScope { get; }
        internal abstract OvrComputeUtils.MaxOutputFrames MeshAnimatorOutputFrames { get; }

        protected override VertexFetchMode VertexFetchType => VertexFetchMode.ExternalBuffers;

        // Specifies the skinning quality (many bones per vertex).
        public OvrSkinningTypes.SkinningQuality SkinningQuality
        {
            get => _skinningQuality;
            set
            {
                if (_skinningQuality != value)
                {
                    _skinningQuality = value;
                    UpdateSkinningQuality();
                }
            }
        }

        private protected SkinningOutputFrame AnimatorWriteDestination { get; set; } =
            SkinningOutputFrame.FrameZero;

        private OvrComputeMeshAnimator _meshAnimator;
        internal OvrComputeMeshAnimator MeshAnimator => _meshAnimator;

        // This is technically configurable, but mostly just for debugging
        [SerializeField]
        [Tooltip(
            "Configuration to override SkinningQuality, otherwise indicates which Quality was selected for this LOD")]
        private OvrSkinningTypes.SkinningQuality _skinningQuality = OvrSkinningTypes.SkinningQuality.Invalid;

        private static PropertyIds _propertyIds = default;
        protected static PropertyIds PropIds => _propertyIds;

        private static void CheckPropertyIdInit()
        {
            if (!_propertyIds.IsValid)
            {
                _propertyIds = new PropertyIds(PropertyIds.InitMethod.PropertyToId);
            }
        }

        protected override void Awake()
        {
            base.Awake();
            CheckPropertyIdInit();
        }

        protected override void Dispose(bool isMainThread)
        {
            if (isMainThread)
            {
                DestroyGpuSkinningObjects();
            }
            else
            {
                OvrAvatarLog.LogError(
                    $"{nameof(OvrAvatarComputeSkinnedRenderable)} was disposed not on main thread, memory has been leaked.",
                    LogScope);
            }

            _meshAnimator = null;

            base.Dispose(isMainThread);
        }

        private void DestroyGpuSkinningObjects()
        {
            MeshAnimator?.Dispose();
            _meshAnimator = null;
        }

        private void UpdateSkinningQuality()
        {
            if (MeshAnimator != null)
            {
                MeshAnimator.SkinningQuality = _skinningQuality;
            }
        }

        protected internal override void ApplyMeshPrimitive(OvrAvatarPrimitive primitive)
        {
            // The base call adds a mesh filter already and material
            base.ApplyMeshPrimitive(primitive);

            try
            {
                if (_skinningQuality == OvrSkinningTypes.SkinningQuality.Invalid)
                {
                    _skinningQuality =
                        GpuSkinningConfiguration.Instance.GetQualityForLOD(primitive.HighestQualityLODIndex);
                }

                AddGpuSkinningObjects(primitive);
                ApplyGpuSkinningMaterial();
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogError($"Exception applying primitive ({primitive}) - {e}", LogScope, this);
            }
        }

        private void ApplyGpuSkinningMaterial()
        {
            rendererComponent.GetPropertyBlock(MatBlock);

            ComputeBuffer positionBuffer = null;
            ComputeBuffer frenetBuffer = null;

            var positionScale = Vector3.one;
            var positionBias = Vector3.zero;
            var posDataFormat = OvrComputeUtils.ShaderFormatValue.FLOAT;

            if (MeshAnimator != null)
            {
                var animatorOutputScale = MeshAnimator.PositionOutputScale;
                Debug.Assert(animatorOutputScale.x > 0.0f && animatorOutputScale.y > 0.0f && animatorOutputScale.z > 0.0f);

                positionBuffer = MeshAnimator.GetPositionOutputBuffer();
                frenetBuffer = MeshAnimator.GetFrenetOutputBuffer();

                positionScale = new Vector3(1.0f / animatorOutputScale.x, 1.0f / animatorOutputScale.y, 1.0f / animatorOutputScale.z);
                positionBias = -1.0f * MeshAnimator.PositionOutputBias;

                posDataFormat =
                    OvrComputeUtils.GetDataFormatShaderPropertyValue(
                        MeshAnimator.PositionOutputFormatAndStride.dataFormat);
            }

            MatBlock.SetBuffer(_propertyIds.PositionOutputBufferPropId, positionBuffer);
            MatBlock.SetBuffer(_propertyIds.FrenetOutputBufferPropId, frenetBuffer);
            MatBlock.SetVector(_propertyIds.PositionScalePropId, positionScale);
            MatBlock.SetVector(_propertyIds.PositionBiasPropId, positionBias);

            MatBlock.SetInt(_propertyIds.PositionDataFormatPropId, (int)posDataFormat);

            MatBlock.SetInt(_propertyIds.NumOutputEntriesPerAttributePropId, (int)MeshAnimatorOutputFrames);

            Debug.Assert(
                positionBuffer != null,
                "No position buffer for compute skinning, avatars may not be able to move.");
            Debug.Assert(
                frenetBuffer != null,
                "No frenet buffer for compute skinning, avatars may not be able to move.");

            rendererComponent.SetPropertyBlock(MatBlock);
        }

        public override void ApplySkeleton(Transform[] bones)
        {
            // No-op
        }

        internal override bool AnimationFrameUpdate(
            bool updateJoints,
            bool updateMorphs,
            CAPI.ovrAvatar2EntityId entityId,
            CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
        {
            using var livePerfMarker = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Skinned_Compute_AnimationFrameUpdate);
            bool jointsUpdated = false;
            if (MeshAnimator != null)
            {
                jointsUpdated = MeshAnimator.UpdateAnimationData(
                    updateJoints,
                    updateMorphs,
                    entityId,
                    primitiveInstanceId,
                    AnimatorWriteDestination);
                OvrAvatarManager.Instance.SkinningController.AddActivateComputeAnimator(MeshAnimator);
            }

            return jointsUpdated;
        }


        private void AddGpuSkinningObjects(OvrAvatarPrimitive primitive)
        {
            // For now, just create source textures at runtime
            // TODO*: The texture creation should really be part of pipeline
            // and part of the input files from SDK and should be handled via
            // native plugin, but, for now, create via C#
            if (MyMesh)
            {
                var gpuSkinningConfig = GpuSkinningConfiguration.Instance;

                int numMorphTargets = (int)primitive.morphTargetCount;
                int numJoints = primitive.joints.Length;

                // Before we begin, check to see if we already have a skinner/morph target system set up:
                Debug.Assert(MeshAnimator == null, "Only one compute animator system can be created for Renderable.");
                if (primitive.computePrimitive == null || primitive.computePrimitive.VertexBuffer == null)
                {
                    OvrAvatarLog.LogWarning("Found null or invalid compute primitive", LogScope);
                    return;
                }

                if (gpuSkinningConfig.MorphAndSkinningComputeShader == null)
                {
                    OvrAvatarLog.LogError("Found null compute shader for compute skinning. Please specify a compute shader to use in the GPU skinning configuration.", LogScope);
                    return;
                }

                _meshAnimator = new OvrComputeMeshAnimator(
                    primitive.shortName,
                    gpuSkinningConfig.MorphAndSkinningComputeShader,
                    (int)primitive.meshVertexCount,
                    numMorphTargets,
                    numJoints,
                    primitive.computePrimitive,
                    gpuSkinningConfig,
                    HasTangents,
                    MeshAnimatorOutputFrames,
                    SkinningQuality);
            } // if has mesh
        }

        internal static SkinningOutputFrame GetNextOutputFrame(
            SkinningOutputFrame current,
            OvrComputeUtils.MaxOutputFrames maxFrames)
        {
            return (SkinningOutputFrame)(((int)current + 1) % (int)maxFrames);
        }

#if UNITY_EDITOR
        void OnDrawGizmosSelected()
        {
            Gizmos.color = Color.magenta;
            if (MyMeshFilter != null)
            {
                Mesh m = MyMeshFilter.sharedMesh;
                if (m != null)
                {
                    Gizmos.matrix = MyMeshFilter.transform.localToWorldMatrix;
                    Gizmos.DrawWireCube(m.bounds.center, m.bounds.size);
                }
            }
        }

        protected void OnValidate()
        {
            UpdateSkinningQuality();
        }
#endif

        protected readonly struct PropertyIds
        {
            public readonly int PositionOutputBufferPropId;
            public readonly int FrenetOutputBufferPropId;
            public readonly int PositionScalePropId;
            public readonly int PositionBiasPropId;
            public readonly int PositionDataFormatPropId;
            public readonly int AttributeLerpValuePropId;

            public readonly int NumOutputEntriesPerAttributePropId;

            public readonly int AttributeOutputLatestAnimFrameEntryOffset;
            public readonly int AttributeOutputPrevAnimFrameEntryOffset;

            public readonly int AttributeOutputPrevRenderFrameLatestAnimFrameOffset;
            public readonly int AttributeOutputPrevRenderFramePrevAnimFrameOffset;
            public readonly int AttributePrevRenderFrameLerpValuePropId;

            // This will be 0 if default initialized, otherwise they are guaranteed unique
            public bool IsValid => FrenetOutputBufferPropId != PositionOutputBufferPropId;

            public enum InitMethod
            {
                PropertyToId
            }

            public PropertyIds(InitMethod initMethod)
            {
                PositionOutputBufferPropId = Shader.PropertyToID("_OvrPositionBuffer");
                FrenetOutputBufferPropId = Shader.PropertyToID("_OvrFrenetBuffer");

                PositionScalePropId = Shader.PropertyToID("_OvrPositionScale");
                PositionBiasPropId = Shader.PropertyToID("_OvrPositionBias");
                PositionDataFormatPropId = Shader.PropertyToID("_OvrPositionDataFormat");

                AttributeLerpValuePropId = Shader.PropertyToID("_OvrAttributeInterpolationValue");

                AttributeOutputLatestAnimFrameEntryOffset =
                    Shader.PropertyToID("_OvrAttributeOutputLatestAnimFrameEntryOffset");
                AttributeOutputPrevAnimFrameEntryOffset =
                    Shader.PropertyToID("_OvrAttributeOutputPrevAnimFrameEntryOffset");

                NumOutputEntriesPerAttributePropId = Shader.PropertyToID("_OvrNumOutputEntriesPerAttribute");

                // Motion vectors (application spacewarp) related properties
                AttributeOutputPrevRenderFrameLatestAnimFrameOffset =
                    Shader.PropertyToID("_OvrAttributeOutputPrevRenderFrameLatestAnimFrameOffset");
                AttributeOutputPrevRenderFramePrevAnimFrameOffset =
                    Shader.PropertyToID("_OvrAttributeOutputPrevRenderFramePrevAnimFrameOffset");
                AttributePrevRenderFrameLerpValuePropId = Shader.PropertyToID("_OvrPrevRenderFrameInterpolationValue");
            }
        }
    }
}
