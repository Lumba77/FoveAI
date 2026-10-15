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

namespace Oculus.Skinning.GpuSkinning
{
    internal sealed class OvrComputeMeshAnimator : IDisposable
    {
        private const string LOG_SCOPE = "OvrComputeMeshAnimator";

        private const int VERTEX_BUFFER_META_DATA_OFFSET = 0; // always 0 (no batching)
        private const int POSITION_OUTPUT_OFFSET = 0; // always 0 (no batching)
        private const int FRENET_OUTPUT_OFFSET = 0; // always 0 (no batching)

        public OvrSkinningTypes.SkinningQuality SkinningQuality
        {
            get => _quality;
            set
            {
                _quality = value;

                if (_shader != null)
                {
                    _shader.SkinningQuality = value;
                }
            }
        }

        private OvrSkinningTypes.SkinningQuality _quality;

        public OvrComputeMeshAnimator(
            string name,
            ComputeShader shader,
            int numMeshVerts,
            int numMorphTargets,
            int numJoints,
            OvrAvatarComputeSkinnedPrimitive gpuPrimitive,
            GpuSkinningConfiguration gpuSkinningConfiguration,
            bool hasTangents,
            OvrComputeUtils.MaxOutputFrames maxOutputFrames,
            OvrSkinningTypes.SkinningQuality skinningQuality)
        {
            Debug.Assert(shader != null);
            Debug.Assert(gpuPrimitive != null);
            Debug.Assert(gpuPrimitive.VertexBuffer != null);

            _numMeshVerts = numMeshVerts;
            _numVertsToUpdate = gpuPrimitive.MeshAndCompactSkinningIndices.Length;
            _numMorphTargetWeights = numMorphTargets;
            _numJointMatrices = numJoints;

            _vertexBuffer = gpuPrimitive.VertexBuffer;

            _hasMorphTargets = _vertexBuffer.NumMorphedVerts > 0;

            if (IsNormalizedFormat(gpuSkinningConfiguration.PositionOutputFormat))
            {
                var configurationNormalizationBias = gpuSkinningConfiguration.SkinningPositionOutputNormalizationBias;
                var configurationNormalizationScale = gpuSkinningConfiguration.SkinningPositionOutputNormalizationScale;

                Debug.Assert(configurationNormalizationScale > 0.0f);

                // The configuration specifies where the "center" is
                // and the scale of the "bounds". So the mesh animator's
                // scale and bias and the inverse of the configuration
                // settings.
                _positionOutputBias = new Vector3(
                    -configurationNormalizationBias,
                    -configurationNormalizationBias,
                    -configurationNormalizationBias);
                _positionOutputScale = new Vector3(
                    1.0f / configurationNormalizationScale,
                    1.0f / configurationNormalizationScale,
                    1.0f / configurationNormalizationScale);
            }
            else
            {
                _positionOutputBias = Vector3.zero;
                _positionOutputScale = Vector3.one;
            }

            var vertexInfosOffset = CreatePerInstanceBuffer(
                name,
                VERTEX_BUFFER_META_DATA_OFFSET,
                maxOutputFrames,
                gpuPrimitive.MeshAndCompactSkinningIndices);

            _positionDataFormatAndStride = GetOutputPositionDataFormat(gpuSkinningConfiguration.PositionOutputFormat);

            CreateOutputBuffers(name, hasTangents, maxOutputFrames);
            var shaderParams = new OvrComputeMeshAnimatorShader.InitParams
            {
                hasMorphTargets = _hasMorphTargets,
                hasTangents = hasTangents,
                numOutputSlices = maxOutputFrames,
                vertexBuffer = gpuPrimitive.VertexBuffer.Buffer,
                perInstanceHeaderBuffer = _perInstanceBuffer.HeaderBuffer,
                vertexInfoOffset = vertexInfosOffset,
                meshInstanceMetaDataOfset = _perInstanceBuffer.MeshInstanceMetaDataOffset,
                positionOutputBuffer = _positionOutputBuffer,
                frenetOutputBuffer = _frenetOutputBuffer,
                vertexBufferFormatsAndStrides = gpuPrimitive.VertexBuffer.FormatsAndStrides,
                positionOutputBufferDataFormatAndStride = _positionDataFormatAndStride,
                applyAdditionalTransform = !gpuPrimitive.VertexBuffer.IsDataInClientSpace,
                clientSpaceTransform = gpuPrimitive.VertexBuffer.ClientSpaceTransform,
            };
            _shader = new OvrComputeMeshAnimatorShader(shader, shaderParams);
            SkinningQuality = skinningQuality;
            UpdateOutputs();
        }

        public ComputeBuffer GetPositionOutputBuffer()
        {
            return _positionOutputBuffer;
        }

        public ComputeBuffer GetFrenetOutputBuffer()
        {
            return _frenetOutputBuffer;
        }

        public Vector3 PositionOutputScale => _positionOutputScale;

        public Vector3 PositionOutputBias => _positionOutputBias;

        public OvrComputeUtils.DataFormatAndStride PositionOutputFormatAndStride => _positionDataFormatAndStride;

        public void UpdateOutputs()
        {
            // Just a single dispatch (sacrifice some GPU time for saving CPU time)
            // Potentially do three dispatches if there are morphs and skinning and neither
            const int START_INDEX = 0;
            // MutableFrameStrideBytes and MutableBuffer needs to be set here since mutable buffer might grow due to overflow.
            var skinningControllerRef = OvrAvatarManager.Instance.SkinningController;
            var dynamicParams = new OvrComputeMeshAnimatorShader.DynamicParams
            {
                MutableBufferRef = skinningControllerRef.MutableBuffer,
                MutableBufferFrameIndex = skinningControllerRef.MutableBufferFrameIndex,
                MutableOffset = _perInstanceBuffer.perFrameMutableOffset,
                MutableFrameStrideBytes = skinningControllerRef.MutableFrameStrideBytes,
            };
            _shader.UpdateDynamicParameters(dynamicParams);
            _shader.Dispatch(START_INDEX, _numVertsToUpdate);
        }

        public bool UpdateAnimationData(
            bool updateJoints,
            bool updateMorphs,
            CAPI.ovrAvatar2EntityId entityId,
            CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId,
            SkinningOutputFrame writeDestination)
        {
            bool jointsUpdated = _perInstanceBuffer.FrameUpdate(
                updateJoints,
                updateMorphs,
                writeDestination,
                entityId,
                primitiveInstanceId);

            return jointsUpdated;
        }

        private bool IsNormalizedFormat(GpuSkinningConfiguration.PositionOutputDataFormat format)
        {
            switch (format)
            {
                case GpuSkinningConfiguration.PositionOutputDataFormat.Unorm16:
                    return true;
                case GpuSkinningConfiguration.PositionOutputDataFormat.Unorm8:
                    return true;
                default:
                    return false;
            }
        }

        private OvrComputeUtils.DataFormatAndStride GetOutputPositionDataFormat(
            GpuSkinningConfiguration.PositionOutputDataFormat format)
        {
            // Positions need to be vec4s (with the 1.0 in w component) and are expected
            // to be on 4 byte boundary
            switch (format)
            {
                case GpuSkinningConfiguration.PositionOutputDataFormat.Float:
                    return new OvrComputeUtils.DataFormatAndStride(
                        CAPI.ovrAvatar2DataFormat.F32,
                        UnsafeUtility.SizeOf<Vector4>());
                case GpuSkinningConfiguration.PositionOutputDataFormat.Half:
                    // Output expected to be on 4 byte boundary
                    return new OvrComputeUtils.DataFormatAndStride(
                        CAPI.ovrAvatar2DataFormat.F16,
                        (int)OvrComputeUtils.GetUintAlignedSize(4 * 2));
                case GpuSkinningConfiguration.PositionOutputDataFormat.Unorm16:
                    // Output expected to be on 4 byte boundary
                    return new OvrComputeUtils.DataFormatAndStride(
                        CAPI.ovrAvatar2DataFormat.Unorm16,
                        (int)OvrComputeUtils.GetUintAlignedSize(4 * 2));
                case GpuSkinningConfiguration.PositionOutputDataFormat.Unorm8:
                    // Output expected to be on 4 byte boundary
                    return new OvrComputeUtils.DataFormatAndStride(
                        CAPI.ovrAvatar2DataFormat.Unorm8,
                        (int)OvrComputeUtils.GetUintAlignedSize(4 * 1));
                default:
                    OvrAvatarLog.LogInfo("Unhandled output position format, using default", LOG_SCOPE);
                    return new OvrComputeUtils.DataFormatAndStride(
                        CAPI.ovrAvatar2DataFormat.F32,
                        UnsafeUtility.SizeOf<Vector4>());
            }
        }

        // Returns the "vertexInfoOffset"
        private int CreatePerInstanceBuffer(
            string name,
            int vertexBufferMetaDataOffsetBytes,
            OvrComputeUtils.MaxOutputFrames maxOutputFrames,
            in NativeArray<OvrAvatarComputeSkinnedPrimitive.VertexIndices> vertIndices)
        {
            _perInstanceBuffer = new OvrComputeAnimatorBuffer(
                vertIndices,
                _numJointMatrices,
                _numMorphTargetWeights,
                vertexBufferMetaDataOffsetBytes,
                POSITION_OUTPUT_OFFSET,
                _positionOutputBias,
                _positionOutputScale,
                FRENET_OUTPUT_OFFSET);

            return _perInstanceBuffer.VertexInfosOffset;
        }

        private void CreateOutputBuffers(string name, bool hasTangents, OvrComputeUtils.MaxOutputFrames maxOutputFrames)
        {
            const string POS_OUTPUT_SUFFIX = "PositionOutput";
            const string FRENET_OUTPUT_SUFFIX = "FrenetOutput";

            int numOutputSlices = (int)maxOutputFrames;
            _positionOutputBuffer = OvrComputeUtils.CreateRawComputeBuffer(
                GetPositionOutputBufferSize(_numMeshVerts, _positionDataFormatAndStride.strideBytes, numOutputSlices));
            _frenetOutputBuffer = OvrComputeUtils.CreateRawComputeBuffer(
                GetFrenetOutputBufferSize(_numMeshVerts, hasTangents, numOutputSlices));

            _positionOutputBuffer.name = $"{name}_{POS_OUTPUT_SUFFIX}";
            _frenetOutputBuffer.name = $"{name}_{FRENET_OUTPUT_SUFFIX}";
        }

        private static uint GetPositionOutputBufferSize(int numMeshVerts, int positionStrideBytes, int numOutputSlices)
        {
            return (uint)(positionStrideBytes * numMeshVerts * numOutputSlices);
        }

        private static uint GetFrenetOutputBufferSize(int numMeshVerts, bool hasTangents, int numOutputSlices)
        {
            const int FRENET_ATTRIBUTE_STRIDE_BYTES = 4; // only supporting 10-10-10-2 format for normal/tangents

            return (uint)(FRENET_ATTRIBUTE_STRIDE_BYTES * numMeshVerts * (hasTangents ? 2 : 1) * numOutputSlices);
        }

        // The number of vertices in the "Mesh" that this is associated with
        private readonly int _numMeshVerts;

        // The number of vertices of the "Mesh" that this animator will update.
        // If a mesh has an index buffer that doesn't use every vertex in the mesh,
        // then it is possible (likely even) that the _numVertsToUpdate will
        // be smaller than the _numMeshVerts;
        private readonly int _numVertsToUpdate;

        private readonly int _numMorphTargetWeights;
        private readonly int _numJointMatrices;

        private readonly bool _hasMorphTargets;

        private ComputeBuffer _positionOutputBuffer;
        private ComputeBuffer _frenetOutputBuffer;

        private OvrComputeAnimatorBuffer _perInstanceBuffer;

        private readonly Vector3 _positionOutputScale;
        private readonly Vector3 _positionOutputBias;
        private readonly OvrComputeUtils.DataFormatAndStride _positionDataFormatAndStride;

        private readonly OvrComputeMeshAnimatorShader _shader;

        private readonly OvrAvatarComputeSkinningVertexBuffer _vertexBuffer;

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        private void Dispose(bool isDispose)
        {
            if (isDispose)
            {
                _perInstanceBuffer?.Dispose();
                _positionOutputBuffer?.Dispose();
                _frenetOutputBuffer?.Dispose();
                _shader.Dispose();
            }
            else
            {
                if (_perInstanceBuffer != null || _positionOutputBuffer != null || _frenetOutputBuffer != null)
                    OvrAvatarLog.LogError($"OvrComputeMeshAnimator was not disposed before being destroyed", LOG_SCOPE);
            }

            _perInstanceBuffer = null;
            _positionOutputBuffer = null;
            _frenetOutputBuffer = null;
        }

        ~OvrComputeMeshAnimator()
        {
            Dispose(false);
        }
    }
}
