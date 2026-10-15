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

// Due to Unity bug (fixed in version 2021.2), copy to a native array then copy native array to ComputeBuffer in one chunk
// (ComputeBuffer.SetData erases previously set data)
// https://issuetracker.unity3d.com/issues/partial-updates-of-computebuffer-slash-graphicsbuffer-using-setdata-dont-preserve-existing-data-when-using-opengl-es

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

using Oculus.Avatar2;

using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;

using UnityEngine;
using UnityEngine.Profiling;

namespace Oculus.Skinning.GpuSkinning
{
    // A load request
    internal class OvrAvatarComputeSkinningVertexBufferBuilder : IDisposable
    {
        private const string LOG_SCOPE = nameof(OvrAvatarComputeSkinningVertexBufferBuilder);

        public OvrAvatarComputeSkinningVertexBufferBuilder(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            Action failureCallback,
            Action compactSkinningDataLoadedCallback,
            Func<OvrAvatarComputeSkinningVertexBuffer, IEnumerator<OvrTime.SliceStep>> finishCallback)
        {
            Debug.Assert(id != CAPI.ovrAvatar2CompactSkinningDataId.Invalid);

            _buildSlice = OvrTime.Slice(
                BuildVertexBuffer(id, failureCallback, compactSkinningDataLoadedCallback, finishCallback));
        }

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        private void Dispose(bool isDispose)
        {
            if (isDispose)
            {
                if (_buildSlice.IsValid)
                {
                    _buildSlice.Cancel();
                }
            }
            else
            {
                if (_buildSlice.IsValid)
                {
                    OvrAvatarLog.LogError(
                        "OvrAvatarComputeSkinningVertexBufferBuilder slice still valid when finalized",
                        LOG_SCOPE);

                    // Prevent OvrTime from stalling
                    _buildSlice.EmergencyShutdown();
                }
            }
        }

        ~OvrAvatarComputeSkinningVertexBufferBuilder()
        {
            Dispose(false);
        }

        private void CopyVertBufferMetaData(ref VertexBufferMetaData metaData, ref NativeArray<byte> dataBuffer)
        {
            unsafe
            {
                UnsafeUtility.CopyStructureToPtr(ref metaData, dataBuffer.GetPtr());
            }
        }

        private IEnumerator<OvrTime.SliceStep> BuildVertexBuffer(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            Action failureCallback,
            Action compactSkinningDataLoadedCallback,
            Func<OvrAvatarComputeSkinningVertexBuffer, IEnumerator<OvrTime.SliceStep>> finishCallback)
        {
            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

            VertexBufferMetaData vertexBufferMetaData = new VertexBufferMetaData();

            OvrAvatarComputeSkinningVertexBuffer.DataFormatsAndStrides dataFormats =
                new OvrAvatarComputeSkinningVertexBuffer.DataFormatsAndStrides();

            CAPI.OvrAvatar2CompactSkinningMetaData apiMetaData = default;

            try
            {
                uint currentOffset = 0;

                bool success = true;
                CAPI.ovrAvatar2BufferMetaData posMetaData = default;
                CAPI.ovrAvatar2BufferMetaData normMetaData = default;
                CAPI.ovrAvatar2BufferMetaData tanMetaData = default;
                CAPI.ovrAvatar2BufferMetaData jWeightsMetaData = default;
                CAPI.ovrAvatar2BufferMetaData jIndicesMetaData = default;
                CAPI.ovrAvatar2BufferMetaData morphPosMetaData = default;
                CAPI.ovrAvatar2BufferMetaData morphNormMetaData = default;
                CAPI.ovrAvatar2BufferMetaData morphTanMetaData = default;
                CAPI.ovrAvatar2BufferMetaData morphIndicesMetaData = default;
                CAPI.ovrAvatar2BufferMetaData morphNextMetaData = default;
                CAPI.ovrAvatar2BufferMetaData morphNumMetaData = default;
                OvrComputeUtils.DataFormatAndStride posFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride normFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride tanFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride jWeightsFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride jIndicesFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride morphPosFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride morphNormFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride morphTanFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride morphIndicesFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride morphNextFormatAndStride = default;
                OvrComputeUtils.DataFormatAndStride morphNumFormatAndStride = default;

                bool haveTangents = false;
                bool haveJointWeights = false;
                bool haveJointIndices = false;
                bool haveMorphPositions = false;
                bool haveMorphNormals = false;
                bool haveMorphTangents = false;
                bool haveMorphIndices = false;
                bool haveMorphNexts = false;
                bool haveMorphNums = false;

                // Should probably have a bulk api for all the meta data, "only" takes ~100us as is though.
                Profiler.BeginSample("OvrAvatarComputeSkinningVertexBufferBuilder.GetMetaData");

                {
                    apiMetaData = CAPI.OvrCompactSkinningData_GetMetaData(id);

                    vertexBufferMetaData.numMorphedVerts = apiMetaData.numMorphedVerts;
                    vertexBufferMetaData.numSkinningOnlyVerts = apiMetaData.numJointsOnlyVerts;
                    currentOffset += (uint)UnsafeUtility.SizeOf<VertexBufferMetaData>();
                }

                {
                    success = GetPositionsMetaData(id, out posMetaData, out posFormatAndStride);

                    vertexBufferMetaData.positionsOffsetBytes = currentOffset;
                    dataFormats.vertexPositions = posFormatAndStride;
                    currentOffset += GetBufferSize(posMetaData, posFormatAndStride);
                }

                if (success)
                {
                    success = GetNormalsMetaData(id, out normMetaData, out normFormatAndStride);

                    vertexBufferMetaData.normalsOffsetBytes = currentOffset;
                    dataFormats.vertexNormals = normFormatAndStride;
                    currentOffset += GetBufferSize(normMetaData, normFormatAndStride);
                }

                if (success)
                {
                    success = GetTangentsMetaData(id, out tanMetaData, out tanFormatAndStride);
                    // optional
                    if (tanMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveTangents = true;
                        vertexBufferMetaData.tangentsOffsetBytes = currentOffset;
                        dataFormats.vertexTangents = tanFormatAndStride;
                        currentOffset += GetBufferSize(tanMetaData, tanFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetJointWeightsMetaData(id, out jWeightsMetaData, out jWeightsFormatAndStride);
                    // optional
                    if (jWeightsMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveJointWeights = true;
                        vertexBufferMetaData.jointWeightsOffsetBytes = currentOffset;
                        dataFormats.jointWeights = jWeightsFormatAndStride;
                        currentOffset += GetBufferSize(jWeightsMetaData, jWeightsFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetJointIndicesMetaData(id, out jIndicesMetaData, out jIndicesFormatAndStride);
                    // optional
                    if (jIndicesMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveJointIndices = true;
                        vertexBufferMetaData.jointIndicesOffsetBytes = currentOffset;
                        dataFormats.jointIndices = jIndicesFormatAndStride;
                        currentOffset += GetBufferSize(jIndicesMetaData, jIndicesFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetMorphPosMetaData(id, out morphPosMetaData, out morphPosFormatAndStride);
                    // optional
                    if (morphPosMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveMorphPositions = true;
                        vertexBufferMetaData.morphTargetPosDeltasOffsetBytes = currentOffset;

                        // ASSUMPTIONS: All morph deltas (pos, norm, tan) have the same format
                        dataFormats.morphDeltas = morphPosFormatAndStride;
                        currentOffset += GetBufferSize(morphPosMetaData, morphPosFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetMorphNormMetaData(id, out morphNormMetaData, out morphNormFormatAndStride);
                    // optional
                    if (morphNormMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveMorphNormals = true;
                        vertexBufferMetaData.morphTargetNormDeltasOffsetBytes = currentOffset;
                        currentOffset += GetBufferSize(morphNormMetaData, morphNormFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetMorphTanMetaData(id, out morphTanMetaData, out morphTanFormatAndStride);
                    // optional
                    if (morphTanMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveMorphTangents = true;
                        vertexBufferMetaData.morphTargetTanDeltasOffsetBytes = currentOffset;
                        currentOffset += GetBufferSize(morphTanMetaData, morphTanFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetMorphIndicesMetaData(id, out morphIndicesMetaData, out morphIndicesFormatAndStride);
                    // optional
                    if (morphIndicesMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveMorphIndices = true;
                        vertexBufferMetaData.morphTargetIndicesOffsetBytes = currentOffset;
                        dataFormats.morphIndices = morphIndicesFormatAndStride;
                        currentOffset += GetBufferSizeAligned(morphIndicesMetaData, morphIndicesFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetMorphNextMetaData(id, out morphNextMetaData, out morphNextFormatAndStride);
                    // optional
                    if (morphNextMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveMorphNexts = true;
                        vertexBufferMetaData.morphTargetNextEntriesOffsetBytes = currentOffset;
                        dataFormats.nextEntryIndices = morphNextFormatAndStride;
                        currentOffset += GetBufferSizeAligned(morphNextMetaData, morphNextFormatAndStride);
                    }
                }

                if (success)
                {
                    success = GetMorphNumsMetaData(id, out morphNumMetaData, out morphNumFormatAndStride);
                    // optional
                    if (morphNumMetaData.dataFormat != CAPI.ovrAvatar2DataFormat.Invalid)
                    {
                        haveMorphNums = true;
                        vertexBufferMetaData.numMorphsBufferOffsetBytes = currentOffset;
                        currentOffset += GetBufferSize(morphNumMetaData, morphNumFormatAndStride);
                    }
                }

                Profiler.EndSample();

                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

                Profiler.BeginSample("OvrAvatarComputeSkinningVertexBufferBuilder.CreateComputeSkinningVertexBuffer");
                var computeBuffer = OvrComputeUtils.CreateRawComputeBuffer(currentOffset);
                computeBuffer.name = $"ComputeSkinningVertexBuffer_{id}";
                Profiler.EndSample();

                string operationName;

                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

                // Unfortunately we have to make a copy. BeginWrite only provides a direct pointer to GPU memory on some platforms, like Quest, and PC's with resizable bar.
                // for other platforms, beginWrite provides a TempJob allocated native array. When that happens we only have 4 frames to call EndWrite, which is hard to 100% guarantee.
                // The only solution is to make a copy. Still faster than the old Unity api's, one copy instead of 2, and no involvement of unity render thread, and no opengl/vulkan calls.
                // If we can be sure that beginWrite is a direct pointer to GPU memory in future, can skip this copy.
                var dataBuffer = new NativeArray<byte>((int)OvrComputeUtils.GetUintAlignedSize(currentOffset), Allocator.Persistent, NativeArrayOptions.UninitializedMemory);

                NativeArray<byte> reorderBuffer = default;
                OvrComputeUtils.DataFormatAndStride vertexIndexDataFormatAndStride = default;

                var computeBufferLoadTask = OvrAvatarManager.Instance.EnqueueLoadingTask(() =>
                {
                    Profiler.BeginSample("OvrAvatarComputeSkinningVertexBufferBuilder.LoadComputeSkinningVertexBuffer");
                    if (success)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetPositions";

                        Profiler.BeginSample(operationName);
                        var neutralPos = dataBuffer.GetSubArray((int)vertexBufferMetaData.positionsOffsetBytes, (int)GetBufferSize(posMetaData, posFormatAndStride));
                        success = GetPositions(
                            id,
                            operationName,
                            posFormatAndStride,
                            ref neutralPos,
                            out var posOffset,
                            out var posScale);
                        vertexBufferMetaData.vertexInputPositionBias = posOffset;
                        vertexBufferMetaData.vertexInputPositionScale = posScale;
                        Profiler.EndSample();
                    }

                    if (success)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetNormals";
                        Profiler.BeginSample(operationName);
                        var neutralNorm = dataBuffer.GetSubArray((int)vertexBufferMetaData.normalsOffsetBytes, (int)GetBufferSize(normMetaData, normFormatAndStride));
                        success = GetNormals(id, operationName, normFormatAndStride, ref neutralNorm, out var normOffset, out var normScale);
                        vertexBufferMetaData.vertexInputNormalBias = normOffset;
                        vertexBufferMetaData.vertexInputNormalScale = normScale;
                        Profiler.EndSample();
                    }

                    if (success && haveTangents)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetTangents";
                        Profiler.BeginSample(operationName);
                        var neutralTan = dataBuffer.GetSubArray((int)vertexBufferMetaData.tangentsOffsetBytes, (int)GetBufferSize(tanMetaData, tanFormatAndStride));
                        success = GetTangents(id, operationName, tanFormatAndStride, ref neutralTan, out var tanOffset, out var tanScale);
                        vertexBufferMetaData.vertexInputTangentBias = tanOffset;
                        vertexBufferMetaData.vertexInputTangentScale = tanScale;
                        Profiler.EndSample();
                    }

                    if (success && haveJointWeights)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetJointWeights";
                        Profiler.BeginSample(operationName);
                        var jointWeights = dataBuffer.GetSubArray((int)vertexBufferMetaData.jointWeightsOffsetBytes, (int)GetBufferSize(jWeightsMetaData, jWeightsFormatAndStride));
                        success = GetJointWeights(id, operationName, jWeightsFormatAndStride, ref jointWeights);
                        Profiler.EndSample();
                    }

                    if (success && haveJointIndices)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetJointIndices";
                        Profiler.BeginSample(operationName);
                        var jointIndices = dataBuffer.GetSubArray((int)vertexBufferMetaData.jointIndicesOffsetBytes, (int)GetBufferSize(jIndicesMetaData, jIndicesFormatAndStride));
                        success = GetJointIndices(id, operationName, jIndicesFormatAndStride, ref jointIndices);
                        Profiler.EndSample();
                    }

                    if (success && haveMorphPositions)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetMorphPosDeltas";

                        Profiler.BeginSample(operationName);
                        var morphPos = dataBuffer.GetSubArray((int)vertexBufferMetaData.morphTargetPosDeltasOffsetBytes, (int)GetBufferSize(morphPosMetaData, morphPosFormatAndStride));
                        success = GetMorphPosDeltas(id, operationName, morphPosFormatAndStride, ref morphPos, out var morphRange);
                        vertexBufferMetaData.morphTargetsPosScale = morphRange;
                        Profiler.EndSample();
                    }

                    if (success && haveMorphNormals)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetMorphNormDeltas";

                        Profiler.BeginSample(operationName);
                        var morphNorm = dataBuffer.GetSubArray((int)vertexBufferMetaData.morphTargetNormDeltasOffsetBytes, (int)GetBufferSize(morphNormMetaData, morphNormFormatAndStride));
                        success = GetMorphNormDeltas(id, operationName, morphNormFormatAndStride, ref morphNorm, out var morphRange);
                        vertexBufferMetaData.morphTargetsNormScale = morphRange;
                        Profiler.EndSample();
                    }

                    if (success && haveMorphTangents)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetMorphTanDeltas";

                        Profiler.BeginSample(operationName);
                        var morphTan = dataBuffer.GetSubArray((int)vertexBufferMetaData.morphTargetTanDeltasOffsetBytes, (int)GetBufferSize(morphTanMetaData, morphTanFormatAndStride));
                        success = GetMorphTanDeltas(id, operationName, morphTanFormatAndStride, ref morphTan, out var morphRange);
                        vertexBufferMetaData.morphTargetsTanScale = morphRange;
                        Profiler.EndSample();
                    }

                    if (success && haveMorphIndices)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetMorphIndices";

                        Profiler.BeginSample(operationName);
                        var morphIndices = dataBuffer.GetSubArray((int)vertexBufferMetaData.morphTargetIndicesOffsetBytes, (int)GetBufferSizeAligned(morphIndicesMetaData, morphIndicesFormatAndStride));
                        success = GetMorphIndices(id, operationName, morphIndicesFormatAndStride, ref morphIndices);
                        Profiler.EndSample();
                    }

                    if (success && haveMorphNexts)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetMorphNextEntries";

                        Profiler.BeginSample(operationName);
                        var nextEntries = dataBuffer.GetSubArray((int)vertexBufferMetaData.morphTargetNextEntriesOffsetBytes, (int)GetBufferSizeAligned(morphNextMetaData, morphNextFormatAndStride));
                        success = GetMorphNextEntries(id, operationName, morphNextFormatAndStride, ref nextEntries);
                        Profiler.EndSample();
                    }

                    // Grab "num morphs buffer"
                    if (success && haveMorphNums)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetNumMorphsBuffer";

                        Profiler.BeginSample(operationName);
                        var numMorphsBuffer = dataBuffer.GetSubArray((int)vertexBufferMetaData.numMorphsBufferOffsetBytes, (int)GetBufferSize(morphNumMetaData, morphNumFormatAndStride));
                        success = GetNumMorphsBuffer(id, operationName, morphNumFormatAndStride, ref numMorphsBuffer);
                        Profiler.EndSample();
                    }

                    // copy the header last. Not ideal for write combine memory, should write data in order. But doesn't seem to be too big a deal, only breaking the rule once.
                    // could just change the compute shader so this structure is last instead of first.
                    CopyVertBufferMetaData(ref vertexBufferMetaData, ref dataBuffer);

                    // Grab "reorder buffer"
                    if (success)
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.GetCompactSkinningToVertexIndex";

                        Profiler.BeginSample(operationName);
                        success = GetReorderBuffer(
                            id,
                            operationName,
                            out reorderBuffer,
                            out vertexIndexDataFormatAndStride);
                        Profiler.EndSample();
                    }

                    Profiler.EndSample();
                });

                while (!computeBufferLoadTask.IsCompleted)
                {
                    // use wait instead of delay, so we can check every frame
                    yield return OvrTime.SliceStep.Wait;
                }

                computeBuffer.SetData(dataBuffer);
                dataBuffer.Dispose();

                compactSkinningDataLoadedCallback?.Invoke();

                if (success)
                {
                    if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

                    operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.CreateVertexBuffer";
                    Profiler.BeginSample(operationName);
                    var newBuffer = new OvrAvatarComputeSkinningVertexBuffer(
                        computeBuffer,
                        reorderBuffer,
                        vertexIndexDataFormatAndStride,
                        dataFormats,
                        (int)vertexBufferMetaData.numMorphedVerts,
                        haveTangents,
                        apiMetaData.isInClientCoordSpace != 0,
                        (Matrix4x4)apiMetaData.clientCoordSpaceTransform);
                    Profiler.EndSample();

                    // Slice the finish callback if needed
                    IEnumerator<OvrTime.SliceStep> finishCallbackSlice = finishCallback(newBuffer);
                    OvrTime.SliceStep step;
                    do
                    {
                        operationName = "OvrAvatarComputeSkinningVertexBufferBuilder.finishCallbackSlice";
                        Profiler.BeginSample(operationName);
                        step = finishCallbackSlice.MoveNext() ? finishCallbackSlice.Current : OvrTime.SliceStep.Cancel;
                        Profiler.EndSample();
                        if (step != OvrTime.SliceStep.Cancel)
                        {
                            yield return step;
                        }
                    } while (step != OvrTime.SliceStep.Cancel);
                }
                else
                {
                    reorderBuffer.Reset();
                    failureCallback?.Invoke();
                }
            }
            finally
            {
                // Mark loading as finished
                _buildSlice.Clear();
            }
        }

        private static uint GetBufferSize(in CAPI.ovrAvatar2BufferMetaData metaData,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            return (uint)(dataFormatAndStride.strideBytes * metaData.count);
        }

        private static uint GetBufferSizeAligned(in CAPI.ovrAvatar2BufferMetaData metaData,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            return OvrComputeUtils.GetUintAlignedSize((uint)(dataFormatAndStride.strideBytes * metaData.count));
        }

        private static bool GetPositionsMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetPositionsMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogError(
                    $"Could not find CompactSkinningData positions meta data for id {id}",
                    LOG_SCOPE);
                // Positions are required
                return false;
            }

            // Positions are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetNormalsMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetNormalsMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogError(
                    $"Could not find CompactSkinningData normals meta data for id {id}",
                    LOG_SCOPE);
                // Normals are required
                return false;
            }

            // Normals are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetTangentsMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetTangentsMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData tangents meta data for id {id}",
                    LOG_SCOPE);

                // Tangents are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            // Tangents are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetJointWeightsMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetJointWeightsMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData joint weights meta data for id {id}",
                    LOG_SCOPE);

                // joint weights are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            // joint weights are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetJointIndicesMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetJointIndicesMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData joint indices meta data for id {id}",
                    LOG_SCOPE);

                // joint indices are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            // joint indices are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetMorphPosMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetMorphPositionDeltasMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData morph position deltas meta data for id {id}",
                    LOG_SCOPE);

                // morph position deltas are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            // morph position deltas are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetMorphNormMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetMorphNormalDeltasMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData morph normal deltas meta data for id {id}",
                    LOG_SCOPE);

                // morph normal deltas are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            // morph normal deltas are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetMorphTanMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetMorphTangentDeltasMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData morph tangent deltas meta data for id {id}",
                    LOG_SCOPE);

                // morph tangent deltas are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            // morph tangent deltas are expected to start on uint (4 byte) boundaries. Force a stride
            // that is a multiple of that.
            var stride = OvrComputeUtils.GetUintAlignedSize(metaData.strideBytes);

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)stride);

            return true;
        }

        private static bool GetMorphIndicesMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetMorphIndicesMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData morph indices meta data for id {id}",
                    LOG_SCOPE);

                // morph indices are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)metaData.strideBytes);

            return true;
        }

        private static bool GetMorphNextMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetMorphNextEntriesMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData morph target next entries meta data for id {id}",
                    LOG_SCOPE);

                // morph target next entries are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)metaData.strideBytes);

            return true;
        }

        private static bool GetMorphNumsMetaData(CAPI.ovrAvatar2CompactSkinningDataId id, out CAPI.ovrAvatar2BufferMetaData metaData,
            out OvrComputeUtils.DataFormatAndStride dataFormatAndStride)
        {
            metaData = CAPI.OvrCompactSkinningData_GetNumMorphsBufferMetaData(id);
            dataFormatAndStride = default;

            if (!IsBufferValid(in metaData))
            {
                OvrAvatarLog.LogVerbose(
                    $"Could not find CompactSkinningData num morphs buffer  meta data for id {id}",
                    LOG_SCOPE);

                // num morphs buffer are optional, so just early exit here, but still return true to "keep going"
                return true;
            }

            dataFormatAndStride = new OvrComputeUtils.DataFormatAndStride(metaData.dataFormat, (int)metaData.strideBytes);

            return true;
        }

        private static bool GetPositions(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> positions,
            out CAPI.ovrAvatar2Vector3f normalizationOffset,
            out CAPI.ovrAvatar2Vector3f normalizationScale)
        {
            normalizationOffset = new CAPI.ovrAvatar2Vector3f();
            normalizationScale = new CAPI.ovrAvatar2Vector3f(1.0f, 1.0f, 1.0f);

            try
            {
                return CAPI.OvrCompactSkinningData_CopyPositions(
                    id,
                    positions,
                    (uint)dataFormatAndStride.strideBytes,
                    out normalizationOffset,
                    out normalizationScale);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetNormals(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> normals,
            out CAPI.ovrAvatar2Vector3f normalizationOffset,
            out CAPI.ovrAvatar2Vector3f normalizationScale)
        {
            normalizationOffset = new CAPI.ovrAvatar2Vector3f();
            normalizationScale = new CAPI.ovrAvatar2Vector3f(1.0f, 1.0f, 1.0f);

            try
            {
                return CAPI.OvrCompactSkinningData_CopyNormals(id, normals, (uint)dataFormatAndStride.strideBytes, out normalizationOffset, out normalizationScale);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetTangents(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> tangents,
            out CAPI.ovrAvatar2Vector3f normalizationOffset,
            out CAPI.ovrAvatar2Vector3f normalizationScale)
        {
            normalizationOffset = new CAPI.ovrAvatar2Vector3f();
            normalizationScale = new CAPI.ovrAvatar2Vector3f(1.0f, 1.0f, 1.0f);

            try
            {
                return CAPI.OvrCompactSkinningData_CopyTangents(id, tangents, (uint)dataFormatAndStride.strideBytes, out normalizationOffset, out normalizationScale);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetJointWeights(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> jointWeights)
        {
            try
            {
                return CAPI.OvrCompactSkinningData_CopyJointWeights(id, jointWeights, (uint)dataFormatAndStride.strideBytes);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetJointIndices(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> jointIndices)
        {
            try
            {
                return CAPI.OvrCompactSkinningData_CopyJointIndices(id, jointIndices, (uint)dataFormatAndStride.strideBytes);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetMorphPosDeltas(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> deltas,
            out CAPI.ovrAvatar2Vector3f normalizationScale)
        {
            normalizationScale = Vector3.one;

            try
            {
                return CAPI
                    .OvrCompactSkinningData_CopyMorphPositionDeltas(id, deltas, (uint)dataFormatAndStride.strideBytes, out _, out normalizationScale);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetMorphNormDeltas(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> deltas,
            out CAPI.ovrAvatar2Vector3f normalizationScale)
        {
            normalizationScale = Vector3.one;

            try
            {
                return CAPI
                    .OvrCompactSkinningData_CopyMorphNormalDeltas(id, deltas, (uint)dataFormatAndStride.strideBytes, out _, out normalizationScale);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetMorphTanDeltas(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> deltas,
            out CAPI.ovrAvatar2Vector3f normalizationScale)
        {
            normalizationScale = Vector3.one;

            try
            {
                return CAPI
                    .OvrCompactSkinningData_CopyMorphTangentDeltas(id, deltas, (uint)dataFormatAndStride.strideBytes, out _, out normalizationScale);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetMorphIndices(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> indices)
        {
            try
            {
                return CAPI.OvrCompactSkinningData_CopyMorphIndices(id, indices, (uint)dataFormatAndStride.strideBytes);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetMorphNextEntries(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> nextEntries)
        {
            try
            {
                return CAPI.OvrCompactSkinningData_CopyMorphNextEntries(id, nextEntries, (uint)dataFormatAndStride.strideBytes);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetInverseReorderBuffer(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            out NativeArray<byte> indices,
            out OvrComputeUtils.DataFormatAndStride formatAndStride)
        {
            indices = default;
            formatAndStride = default;

            try
            {
                var bufferMetaData = CAPI.OvrCompactSkinningData_GetVertexInverseReorderMetaData(id);

                if (!IsBufferValid(in bufferMetaData))
                {
                    OvrAvatarLog.LogInfo(
                        $"Could not find CompactSkinningData vertex inverse reorder meta data for id {id}",
                        LOG_SCOPE);

                    return false;
                }

                indices = new NativeArray<byte>(
                    (int)bufferMetaData.dataSizeBytes,
                    Allocator.Persistent,
                    NativeArrayOptions.UninitializedMemory);

                formatAndStride = new OvrComputeUtils.DataFormatAndStride(
                    bufferMetaData.dataFormat,
                    (int)bufferMetaData.strideBytes);

                return CAPI.OvrCompactSkinningData_CopyVertexInverseReorder(id, indices, bufferMetaData.strideBytes);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetReorderBuffer(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            out NativeArray<byte> indices,
            out OvrComputeUtils.DataFormatAndStride formatAndStride)
        {
            indices = default;
            formatAndStride = default;

            try
            {
                var bufferMetaData = CAPI.OvrCompactSkinningData_GetVertexReorderMetaData(id);

                if (!IsBufferValid(in bufferMetaData))
                {
                    OvrAvatarLog.LogInfo(
                        $"Could not find CompactSkinningData vertex reorder meta data for id {id}",
                        LOG_SCOPE);

                    return false;
                }

                indices = new NativeArray<byte>(
                    (int)bufferMetaData.dataSizeBytes,
                    Allocator.Persistent,
                    NativeArrayOptions.UninitializedMemory);

                formatAndStride = new OvrComputeUtils.DataFormatAndStride(
                    bufferMetaData.dataFormat,
                    (int)bufferMetaData.strideBytes);

                return CAPI.OvrCompactSkinningData_CopyVertexReorder(id, indices, bufferMetaData.strideBytes);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool GetNumMorphsBuffer(
            CAPI.ovrAvatar2CompactSkinningDataId id,
            string operationName,
            in OvrComputeUtils.DataFormatAndStride dataFormatAndStride,
            ref NativeArray<byte> numMorphs)
        {
            try
            {
                return CAPI.OvrCompactSkinningData_CopyNumMorphsBuffer(id, numMorphs, (uint)dataFormatAndStride.strideBytes);
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(operationName, e);
                return false;
            }
        }

        private static bool IsBufferValid(in CAPI.ovrAvatar2BufferMetaData metaData)
        {
            return metaData.count != 0;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct VertexBufferMetaData
        {
            public uint positionsOffsetBytes;
            public uint normalsOffsetBytes;
            public uint tangentsOffsetBytes;
            public uint jointWeightsOffsetBytes;

            public uint jointIndicesOffsetBytes;
            public uint morphTargetPosDeltasOffsetBytes;
            public uint morphTargetNormDeltasOffsetBytes;
            public uint morphTargetTanDeltasOffsetBytes;

            public uint morphTargetIndicesOffsetBytes;
            public uint morphTargetNextEntriesOffsetBytes;
            public uint numMorphsBufferOffsetBytes;

            public uint numMorphedVerts;
            public uint numSkinningOnlyVerts;

            public CAPI.ovrAvatar2Vector3f vertexInputPositionBias;
            public CAPI.ovrAvatar2Vector3f vertexInputPositionScale;
            public CAPI.ovrAvatar2Vector3f vertexInputNormalBias;
            public CAPI.ovrAvatar2Vector3f vertexInputNormalScale;
            public CAPI.ovrAvatar2Vector3f vertexInputTangentBias;
            public CAPI.ovrAvatar2Vector3f vertexInputTangentScale;

            public CAPI.ovrAvatar2Vector3f morphTargetsPosScale;
            public CAPI.ovrAvatar2Vector3f morphTargetsNormScale;
            public CAPI.ovrAvatar2Vector3f morphTargetsTanScale;
        };

        #region Properties

        public bool IsLoading => _buildSlice.IsValid;

        #endregion


        #region Fields

        private OvrTime.SliceHandle _buildSlice;

        #endregion
    }
}
