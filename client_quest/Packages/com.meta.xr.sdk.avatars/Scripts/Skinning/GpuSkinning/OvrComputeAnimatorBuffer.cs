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
using Unity.Collections.LowLevel.Unsafe;

using UnityEngine;

namespace Oculus.Skinning.GpuSkinning
{
    internal class OvrComputeAnimatorBuffer : IDisposable
    {
        public ComputeBuffer HeaderBuffer => _headerBuffer;

        public int VertexInfosOffset { get; }

        public int perFrameMutableOffset => _perFrameMutableOffset;

        public int MeshInstanceMetaDataOffset => _meshInstanceMetaDataOffset;

        public OvrComputeAnimatorBuffer(
            in NativeArray<OvrAvatarComputeSkinnedPrimitive.VertexIndices> vertIndices,
            int numJointMatrices,
            int numMorphTargetWeights,
            int vertexBufferMetaDataOffsetBytes,
            int positionOutputOffsetBytes,
            Vector3 positionOutputBias,
            Vector3 positionOutputScale,
            int frenetOutputOffsetBytes)
        {
            // Data layout for "per instance" data
            // Header / Static section. These live in _headerBuffer.
            // [An array of "VertexInfo"] -> one for each vertex.
            // [a single mesh_instance_meta_data] -> Since there is only 1 mesh instance (currently)
            // Mutable / Dynamic section. These get pushed to SkinningController.MutableBuffer every frame if the current instance is getting skinned.
            // [output_slice as uint] -> output slice
            // [numJointMatrices float4x4] -> An array joint matrices
            // [numMorphTargetWeights floats] -> An array of morph target weights

            // Calculate the necessary offset/sizes
            _skinningControllerRef = OvrAvatarManager.Instance.SkinningController;

            var meshInstanceMetaDataSize = UnsafeUtility.SizeOf<MeshInstanceMetaData>();
            var vertexInfoDataSize = UnsafeUtility.SizeOf<VertexInfo>();

            var sizeOfVertexInfos = vertIndices.Length * vertexInfoDataSize;
            var sizeOfMeshInstanceMetaDatas = meshInstanceMetaDataSize;
            var sizeOfJointMatrices = numJointMatrices * OvrAvatarSkinningController.JOINT_MATRIX_STRIDE_BYTES;
            var sizeOfMorphTargetWeights = numMorphTargetWeights * OvrAvatarSkinningController.MORPH_WEIGHT_STRIDE_BYTES;
            var sizeOfOutputSlice = OUTPUT_SLICE_STRIDE_BYTES;

            VertexInfosOffset = VERTEX_INFO_DATA_OFFSET;
            var meshInstanceMetaDataOffset = VertexInfosOffset + sizeOfVertexInfos;
            _meshInstanceMetaDataOffset = meshInstanceMetaDataOffset;

            var outputSliceOffset = MUTABLE_DATA_OFFSET;
            var jointMatricesOffset = outputSliceOffset + sizeOfOutputSlice;
            var morphTargetWeightsOffset = jointMatricesOffset + sizeOfJointMatrices;

            // The mutable sections will be the parts of the buffer that can potentially change (joint matrices, morph weights, write destination
            var staticSectionSize = sizeOfVertexInfos + sizeOfMeshInstanceMetaDatas;
            var mutableSize = sizeOfJointMatrices + sizeOfMorphTargetWeights + sizeOfOutputSlice;

            // The header is static therefore create a header buffer that live in GPU only memory.
            _headerBuffer = OvrComputeUtils.CreateRawComputeBuffer((uint)staticSectionSize);

            // Now write static data and initial data to the header buffer
            NativeArray<byte> stagingHeaderBuffer = new NativeArray<byte>(staticSectionSize, Allocator.Temp);

            /////////////////////////////////////////////////////////////////////////////////////////////////
            // First, create an array of "VertexInfos" which will be at the beginning of the per instance
            // data buffer.
            // Then create single MeshInstanceMetaData
            var vertexInfos = stagingHeaderBuffer.GetSubArray(VertexInfosOffset, sizeOfVertexInfos).Reinterpret<VertexInfo>(sizeof(byte));

            // Write out the "vertex infos"
            InitializeVertexInfos(vertIndices, (uint)meshInstanceMetaDataOffset, ref vertexInfos);

            ////////////////////////////////////////////////////////////////////////////////////////////////////
            // Now write out the single MeshInstanceMetaData
            var meshInstanceData = stagingHeaderBuffer.GetSubArray(meshInstanceMetaDataOffset, sizeOfMeshInstanceMetaDatas).Reinterpret<MeshInstanceMetaData>(sizeof(byte));
            unsafe
            {
                var metaDataPtr = meshInstanceData.GetPtr();
                metaDataPtr->vertexBufferMetaDataOffsetBytes = (uint)vertexBufferMetaDataOffsetBytes;
                metaDataPtr->morphTargetWeightsOffsetBytes = (uint)morphTargetWeightsOffset;
                metaDataPtr->jointMatricesOffsetBytes = (uint)jointMatricesOffset;
                metaDataPtr->outputPositionsOffsetBytes = (uint)positionOutputOffsetBytes;
                metaDataPtr->outputFrenetOffsetBytes = (uint)frenetOutputOffsetBytes;
                metaDataPtr->outputSliceOffsetBytes = (uint)outputSliceOffset;
                metaDataPtr->vertexOutputPositionBias = positionOutputBias;
                metaDataPtr->vertexOutputPositionScale = positionOutputScale;
            }

            // Update gpu buffer and clean up the staging buffer
            _headerBuffer.SetData(stagingHeaderBuffer);
            stagingHeaderBuffer.Dispose();

            _mutableSize = mutableSize;
            // Now create the "mutator" for the mutable part of the per instance buffer.
            if (numJointMatrices > 0)
            {
                if (numMorphTargetWeights > 0)
                {
                    // Joints and morphs
                    _bufferMutator = new MorphAndJointsMutator(
                        outputSliceOffset,
                        sizeOfOutputSlice,
                        jointMatricesOffset,
                        sizeOfJointMatrices,
                        morphTargetWeightsOffset,
                        sizeOfMorphTargetWeights);
                }
                else
                {
                    // joints only
                    _bufferMutator = new JointsOnlyMutator(
                        outputSliceOffset,
                        sizeOfOutputSlice,
                        jointMatricesOffset,
                        sizeOfJointMatrices);
                }
            }
            else
            {
                // Morphs only
                _bufferMutator = new MorphsOnlyMutator(
                    outputSliceOffset,
                    sizeOfOutputSlice,
                    morphTargetWeightsOffset,
                    sizeOfMorphTargetWeights);
            }
        }

        public bool FrameUpdate(
            bool updateJoints,
            bool updateMorphs,
            SkinningOutputFrame outputSlice,
            CAPI.ovrAvatar2EntityId entityId,
            CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
        {
            var mutableBufferArray = _skinningControllerRef.PushMutable(_mutableSize, out _perFrameMutableOffset);

            bool jointsUpdated = _bufferMutator.PopulateMutableSection(
                ref mutableBufferArray,
                updateJoints,
                updateMorphs,
                outputSlice,
                entityId,
                primitiveInstanceId);

            return jointsUpdated;
        }

        public virtual void Dispose()
        {
            _headerBuffer.Dispose();
            _headerBuffer = null;
            _bufferMutator = null;
        }

        private void InitializeVertexInfos(
            in NativeArray<OvrAvatarComputeSkinnedPrimitive.VertexIndices> vertIndices,
            UInt32 meshInstanceMetaDataOffset,
            ref NativeArray<VertexInfo> vertexInfos)
        {
            unsafe
            {
                var vertexInfoPtr = vertexInfos.GetPtr();
                var vertIndexPtr = vertIndices.GetPtr();

                for (int index = 0; index < vertIndices.Length; ++index)
                {
                    vertexInfoPtr->vertexBufferIndex = vertIndexPtr->compactSkinningIndex;
                    vertexInfoPtr->outputBufferIndex = vertIndexPtr->outputBufferIndex;

                    vertexInfoPtr++;
                    vertIndexPtr++;
                }
            }
        }

        private const int OUTPUT_SLICE_STRIDE_BYTES = sizeof(UInt32); // a single 32-bit int

        private const int VERTEX_INFO_DATA_OFFSET = 0; // always 0 (no batching)
        private const int MUTABLE_DATA_OFFSET = 0; // Mutable data now gets pushed to the compaction buffer per frame. Always 0.

        [StructLayout(LayoutKind.Sequential)]
        private struct MeshInstanceMetaData
        {
            // Make sure this matches the shader
            public uint vertexBufferMetaDataOffsetBytes;
            public uint morphTargetWeightsOffsetBytes;
            public uint jointMatricesOffsetBytes;
            public uint outputPositionsOffsetBytes;
            public uint outputFrenetOffsetBytes;
            public uint outputSliceOffsetBytes;

            public Vector3 vertexOutputPositionBias;
            public Vector3 vertexOutputPositionScale;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct VertexInfo
        {
            // Make sure this matches the shader
            public uint vertexBufferIndex; // Index in the vertex buffer
            public uint outputBufferIndex; // Index into the output buffer
        }

        private struct JointsMutator
        {
            private readonly int _offset;
            private readonly int _size;

            public JointsMutator(int offset, int size)
            {
                _offset = offset;
                _size = size;
            }

            public bool PopulateJointMatricesBuffer(
                ref NativeArray<byte> mutableSection,
                CAPI.ovrAvatar2EntityId entityId,
                CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
            {
                const bool INTERLEAVE_NORMALS = false;

                var jointsSection = mutableSection.GetSubArray(_offset, _size);
                return OvrAvatarSkinnedRenderable.FetchJointMatrices(
                    entityId,
                    primitiveInstanceId,
                    jointsSection.GetIntPtr(),
                    jointsSection.GetBufferSize(),
                    INTERLEAVE_NORMALS,
                    LOG_SCOPE);
            }
        }

        private struct MorphsMutator
        {
            private readonly int _offset;
            private readonly int _size;

            public MorphsMutator(int offset, int size)
            {
                _offset = offset;
                _size = size;
            }

            public void PopulateMorphWeightsBuffer(
                ref NativeArray<byte> mutableSection,
                CAPI.ovrAvatar2EntityId entityId,
                CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
            {
                var weights = mutableSection.GetSubArray(_offset, _size);
                OvrAvatarSkinnedRenderable.FetchMorphTargetWeights(
                    entityId,
                    primitiveInstanceId,
                    weights.GetIntPtr(),
                    weights.GetBufferSize(),
                    LOG_SCOPE);
            }
        }

        private struct OutputSliceMutator
        {
            private readonly int _offset;
            private readonly int _size;

            public OutputSliceMutator(int offset, int size)
            {
                _offset = offset;
                _size = size;
            }

            public void PopulateOutputSliceBuffer(ref NativeArray<byte> mutableSection, SkinningOutputFrame outputSlice)
            {
                var sliceInBuffer = mutableSection.GetSubArray(_offset, _size).Reinterpret<UInt32>(sizeof(byte));

                unsafe
                {
                    *(sliceInBuffer.GetPtr()) = (UInt32)outputSlice;
                }
            }
        }

        private abstract class BufferMutator
        {
            protected OutputSliceMutator SliceMutator { get; private set; }

            protected BufferMutator(int sliceOffset, int sliceSize)
            {
                SliceMutator = new OutputSliceMutator(sliceOffset, sliceSize);
            }


            // Returns true if joints are updated.
            public abstract bool PopulateMutableSection(
                ref NativeArray<byte> mutableSection,
                bool updateJoints,
                bool updateMorphs,
                SkinningOutputFrame outputSlice,
                CAPI.ovrAvatar2EntityId entityId,
                CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId);
        }

        private class MorphAndJointsMutator : BufferMutator
        {
            public MorphAndJointsMutator(
                int sliceOffset,
                int sliceSize,
                int matsOffset,
                int matsSize,
                int weightsOffset,
                int weightsSize) : base(sliceOffset, sliceSize)
            {
                _jointsMutator = new JointsMutator(matsOffset, matsSize);
                _morphsMutator = new MorphsMutator(weightsOffset, weightsSize);
            }


            public override bool PopulateMutableSection(
                ref NativeArray<byte> mutableSection,
                bool updateJoints,
                bool updateMorphs,
                SkinningOutputFrame outputSlice,
                CAPI.ovrAvatar2EntityId entityId,
                CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
            {
                SliceMutator.PopulateOutputSliceBuffer(ref mutableSection, outputSlice);

                bool jointsUpdated = false;
                if (updateJoints)
                {
                    jointsUpdated = _jointsMutator.PopulateJointMatricesBuffer(ref mutableSection, entityId, primitiveInstanceId);
                }

                if (updateMorphs)
                {
                    _morphsMutator.PopulateMorphWeightsBuffer(ref mutableSection, entityId, primitiveInstanceId);
                }

                return jointsUpdated;
            }

            private readonly JointsMutator _jointsMutator;
            private readonly MorphsMutator _morphsMutator;
        }

        private class MorphsOnlyMutator : BufferMutator
        {
            public MorphsOnlyMutator(
                int sliceOffset,
                int sliceSize,
                int weightsOffset,
                int weightsSize) : base(sliceOffset, sliceSize)
            {
                _morphsMutator = new MorphsMutator(weightsOffset, weightsSize);
            }


            public override bool PopulateMutableSection(
                ref NativeArray<byte> mutableSection,
                bool updateJoints,
                bool updateMorphs,
                SkinningOutputFrame outputSlice,
                CAPI.ovrAvatar2EntityId entityId,
                CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
            {
                SliceMutator.PopulateOutputSliceBuffer(ref mutableSection, outputSlice);

                if (updateMorphs)
                {
                    _morphsMutator.PopulateMorphWeightsBuffer(ref mutableSection, entityId, primitiveInstanceId);
                }

                return false;
            }

            private readonly MorphsMutator _morphsMutator;
        }

        private class JointsOnlyMutator : BufferMutator
        {
            public JointsOnlyMutator(
                int sliceOffset,
                int sliceSize,
                int matsOffset,
                int matsSize) : base(sliceOffset, sliceSize)
            {
                _jointsMutator = new JointsMutator(matsOffset, matsSize);
            }


            public override bool PopulateMutableSection(
                ref NativeArray<byte> mutableSection,
                bool updateJoints,
                bool updateMorphs,
                SkinningOutputFrame outputSlice,
                CAPI.ovrAvatar2EntityId entityId,
                CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId)
            {
                SliceMutator.PopulateOutputSliceBuffer(ref mutableSection, outputSlice);

                bool jointsUpdated = false;
                if (updateJoints)
                {
                    jointsUpdated = _jointsMutator.PopulateJointMatricesBuffer(ref mutableSection, entityId, primitiveInstanceId);
                }

                return jointsUpdated;
            }

            private readonly JointsMutator _jointsMutator;
            private readonly MorphsMutator _morphsMutator;
        }

        private const string LOG_SCOPE = "OvrComputeAnimatorBuffer";

        private BufferMutator _bufferMutator;

        private ComputeBuffer _headerBuffer;
        private int _mutableSize;
        private int _perFrameMutableOffset;
        private int _meshInstanceMetaDataOffset;
        private OvrAvatarSkinningController _skinningControllerRef;
    } // end class OvrComputeAnimatorBuffer
}
