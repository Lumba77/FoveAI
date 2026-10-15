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
using System.Collections.Generic;

using Oculus.Skinning.GpuSkinning;

using Unity.Collections;

using UnityEngine;
using UnityEngine.Profiling;

namespace Oculus.Avatar2
{
    public sealed class OvrAvatarComputeSkinnedPrimitive : IDisposable
    {
        internal OvrAvatarComputeSkinnedPrimitive(
            CAPI.ovrAvatar2CompactSkinningDataId compactSkinningId,
            in NativeArray<UInt16> meshIndices,
            Action failureCallback,
            Action compactSkinningDataLoadedCallback,
            Action<bool> finishCallback)
        {
            InitStaticMaps();

            _externalMeshIndices = meshIndices;

            _finishCallback = finishCallback;
            _failureCallback = failureCallback;
            _compactSkinningDataLoadedCallback = compactSkinningDataLoadedCallback;
            _compactSkinningId = compactSkinningId;

            Debug.Assert(compactSkinningId != CAPI.ovrAvatar2CompactSkinningDataId.Invalid);

            Debug.Assert(_vertexBufferInfos != null);

            // See if vertex buffer already exists for ID
            if (_vertexBufferInfos!.TryGetValue(compactSkinningId, out var vbInfo))
            {
                // A "VertexBufferInfo" exists for the ID, but it's possible that
                // the created "vertex buffer" is no longer used and is invalid
                if (vbInfo.TryGetCreatedBuffer(out var buffer))
                {
                    // OvrAvatarComputeSkinningVertexBuffer still exists
                    SetAndRetainVertexBuffer(buffer, vbInfo);

                    // Only need to build the mapping of "compact skinning index" to
                    // "mesh index"
                    _buildHandle = OvrTime.Slice(GenerateMeshToCompactSkinningIndices());
                    return;
                }
            }
            else
            {
                vbInfo = new VertexBufferInfo();
                _vertexBufferInfos[compactSkinningId] = vbInfo;
            }

            // At this point, a "VertexBufferInfo" exists in the dictionary
            // for the compact skinning ID
            _isWaitingForVertexBuffer = true;
            vbInfo.CreateBuilderIfNeededAndAddPendingLoad(this, compactSkinningId);

            // Wait for the construction
            _buildHandle = OvrTime.Slice(WaitForVertexBufferBuild());
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
                if (_buildHandle.IsValid)
                {
                    _buildHandle.Cancel();
                }

                // Dispose of managed resources
            }
            else
            {
                if (_buildHandle.IsValid)
                {
                    OvrAvatarLog.LogError("Build buffers slice still valid when finalized", LOG_SCOPE);

                    // Prevent OvrTime from stalling
                    _buildHandle.EmergencyShutdown();
                }
            }

            // Dispose of unmanaged resources
            _meshAndCompactSkinningIndices.Reset();

            // Remove this as a pending load of the "VertexBufferInfos" (if it exists)
            Debug.Assert(_vertexBufferInfos != null);
            if (_vertexBufferInfos!.TryGetValue(_compactSkinningId, out var vbInfo))
            {
                // Release the buffer (does not necessarily dispose of it if
                // other primitives are using it)
                if (_vertexBuffer != null)
                {
                    vbInfo.ReleaseBuffer();
                }
                vbInfo.RemovePendingLoad(this);

                // Check if the "VertexBufferInfo" should be removed from the static
                // dictionary
                RemoveVertexBufferInfoFromMappingIfAble(vbInfo);
            }


            _finishCallback = null;
            _failureCallback = null;
            _compactSkinningDataLoadedCallback = null;
        }

        ~OvrAvatarComputeSkinnedPrimitive()
        {
            Dispose(false);
        }

        private IEnumerator<OvrTime.SliceStep> WaitForVertexBufferBuild()
        {
            while (_isWaitingForVertexBuffer)
            {
                yield return OvrTime.SliceStep.Defer;
            }

            // Clear out builder if it is still in the vertex buffer info
            DisposeBuilder();

            // Also time slice the next call
            IEnumerator<OvrTime.SliceStep> task = GenerateMeshToCompactSkinningIndices();
            while (task.MoveNext())
            {
                yield return task.Current;
            }
        }

        private static void InitStaticMaps()
        {
            if (_staticMapsInitialized) return;

            _vertexBufferInfos = new Dictionary<CAPI.ovrAvatar2CompactSkinningDataId, VertexBufferInfo>();
            _staticMapsInitialized = true;
        }

        private void SetAndRetainVertexBuffer(in OvrAvatarComputeSkinningVertexBuffer? buffer, in VertexBufferInfo vbInfo)
        {
            _vertexBuffer = buffer;
            vbInfo.RetainBuffer();
        }

        private void OnVertexBufferCreated(in OvrAvatarComputeSkinningVertexBuffer buffer, in VertexBufferInfo vbInfo)
        {
            SetAndRetainVertexBuffer(buffer, vbInfo);

            _isWaitingForVertexBuffer = false;
        }

        private void OnVertexBufferBuildFailed()
        {
            _isWaitingForVertexBuffer = false;
            _failureCallback?.Invoke();
            _failureCallback = null;
            _buildHandle.Clear();
        }

        private void OnVertexBufferBuildFreeCompactSkinning()
        {
            _isWaitingForVertexBuffer = false;
            _compactSkinningDataLoadedCallback?.Invoke();
            _compactSkinningDataLoadedCallback = null;
        }

        private void DisposeBuilder()
        {
            Debug.Assert(_vertexBufferInfos != null);
            if (_vertexBufferInfos!.TryGetValue(_compactSkinningId, out var vbInfo))
            {
                vbInfo.DisposeBuilder();
            }
        }

        private void RemoveVertexBufferInfoFromMappingIfAble(in VertexBufferInfo vbInfo)
        {
            // Check if the "VertexBufferInfo" should be removed from the static
            // dictionary
            if (!vbInfo.HasPendingLoads && !vbInfo.HasBuffer)
            {
                // No vertex buffer has been made, nothing is waiting for the vertex buffer
                // to be created. Cancel the building of the vertex buffer since it is no longer needed,
                // and remove this "vertex buffer info" from the bookkeeping
                vbInfo.DisposeBuilder();
                Debug.Assert(_vertexBufferInfos != null);
                _vertexBufferInfos!.Remove(_compactSkinningId);
            }
        }

        private IEnumerator<OvrTime.SliceStep> GenerateMeshToCompactSkinningIndices()
        {
            Debug.Assert(_vertexBuffer != null);

            var indexFormat = _vertexBuffer!.VertexIndexFormatAndStride.dataFormat;

            // Based on the format, treat the byte array as an array of another type
            switch (indexFormat)
            {
                case CAPI.ovrAvatar2DataFormat.U32:
                {
                    var reinterpreted = _vertexBuffer.CompactSkinningToOrigIndex.Reinterpret<UInt32Wrapper>(sizeof(byte));
                    return GetCompactSkinningAndMeshIndex(reinterpreted);
                }
                case CAPI.ovrAvatar2DataFormat.U16:
                {
                    var reinterpreted =
                        _vertexBuffer.CompactSkinningToOrigIndex.Reinterpret<UInt16Wrapper>(sizeof(byte));
                    return GetCompactSkinningAndMeshIndex(reinterpreted);
                }
                case CAPI.ovrAvatar2DataFormat.U8:
                {
                    var reinterpreted =
                        _vertexBuffer.CompactSkinningToOrigIndex.Reinterpret<UInt8Wrapper>(sizeof(byte));
                    return GetCompactSkinningAndMeshIndex(reinterpreted);
                }
                default:
                {
                    OvrAvatarLog.LogWarning(
                        $"Unhandled compact skinning vertex index data format {indexFormat}");

                    // Treat as uint8
                    var reinterpreted =
                        _vertexBuffer.CompactSkinningToOrigIndex.Reinterpret<UInt8Wrapper>(sizeof(byte));
                    return GetCompactSkinningAndMeshIndex(reinterpreted);
                }
            }
        }

        private IEnumerator<OvrTime.SliceStep> GetCompactSkinningAndMeshIndex<T>(
            NativeArray<T> compactSkinningToMeshIndex) where T : unmanaged, IConvertibleTo<UInt32>
        {
            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

            NativeArray<VertexIndices> result = default;
            var uniqueIndicesTask = OvrAvatarManager.Instance.EnqueueLoadingTask(() =>
            {
                // In an effort to increase GPU performance, at the cost
                // of additional loading time spent here, we need to find the unique indices
                // in the mesh's "index buffer" to not have the skinner skin vertices
                // which are unused. Additionally, for GPU perf reasons, the skinner
                // should be fed vertices in "compact skinning index" order.

                // Start by populating a boolean array to indicate if the "mesh index" is
                // found in the mesh's index buffer. This call is time sliced.

                var hasIndex = new NativeArray<bool>(compactSkinningToMeshIndex.Length, Allocator.TempJob);
                int numUniqueIndices = 0;

                CheckForUniqueIndices(_externalMeshIndices, ref hasIndex, ref numUniqueIndices);

                // Now, given the mapping of "compact skinning index" -> "mesh index"
                // and the list of "mesh index" that we care about, populate
                // a mapping between the indices, in compact skinning index order, of
                // just the mesh indices that we care about.

                result = new NativeArray<VertexIndices>(
                    numUniqueIndices,
                    Allocator.Persistent,
                    NativeArrayOptions.UninitializedMemory);
                int resultIndex = 0;

                PopulateVertexIndicesArray(compactSkinningToMeshIndex, hasIndex, ref result, ref resultIndex);

                hasIndex.Reset();
            });

            while (!uniqueIndicesTask.IsCompleted)
            {
                yield return OvrTime.SliceStep.Defer;
            }

            _meshAndCompactSkinningIndices = result;
            CallAndClearFinishCallback();
        }

        // Go through the mesh's "index buffer"
        // setting a boolean for if a given index is present
        // in the "index buffer" and tracking the number
        // of unique indices
        private static void CheckForUniqueIndices(
            in NativeArray<UInt16> meshIndices,
            ref NativeArray<bool> hasIndex,
            ref int numUniqueIndices)
        {
            Profiler.BeginSample("OvrAvatarComputeSkinnedPrimitive::CheckForUniqueIndices");

            unsafe
            {
                // Use C# unsafe pointers to avoid NativeArray indexer overhead, and treat the bools as bytes to avoid branching.
                var indicesPtr = meshIndices.GetPtr();
                var hasIndexPtr = (byte*)hasIndex.GetPtr();
                for (int i = 0; i < meshIndices.Length; i++)
                {
                    var meshIndex = indicesPtr[i];
                    numUniqueIndices += 1 - hasIndexPtr[meshIndex];
                    hasIndexPtr[meshIndex] = 1;
                }
            }

            Profiler.EndSample();
        }

        // Given a mapping of "compact skinning index -> mesh index"
        // and a boolean array indicating which "mesh index" is in use,
        // populate an array of <VertexIndices> to serve
        // as the mapping of compact skinning index -> mesh index
        // for the unique indices, but in compact skinning index order
        private static void PopulateVertexIndicesArray<T>(
            in NativeArray<T> compactSkinningToMeshIndex,
            in NativeArray<bool> hasMeshIndex,
            ref NativeArray<VertexIndices> result,
            ref int currentResultIndex) where T : unmanaged, IConvertibleTo<UInt32>
        {

            Profiler.BeginSample("OvrAvatarComputeSkinnedPrimitive::PopulateVertexIndicesArray");

            unsafe
            {
                // Use C# unsafe pointers to avoid NativeArray indexer overhead
                var indicesPtr = compactSkinningToMeshIndex.GetPtr();
                var hasIndexPtr = hasMeshIndex.GetPtr();
                var resultPtr = result.GetPtr();

                for (var cIndex = 0; cIndex < compactSkinningToMeshIndex.Length; cIndex++)
                {
                    // Grab "mesh index" for the given "compact skinning index"
                    var meshIndex = indicesPtr[cIndex].Convert();

                    // See if the "mesh index" was present in the mesh's index buffer
                    if (hasIndexPtr[meshIndex])
                    {
                        resultPtr[currentResultIndex++] = new VertexIndices
                        {
                            compactSkinningIndex = (uint)cIndex,
                            outputBufferIndex = meshIndex,
                        };
                    }
                }
            }

            Profiler.EndSample();
        }

        private void CallAndClearFinishCallback()
        {
            _finishCallback?.Invoke(_vertexBuffer is { HasTangents: true });
            _finishCallback = null;

            _buildHandle.Clear();
        }

        private const string LOG_SCOPE = nameof(OvrAvatarComputeSkinnedPrimitive);

        #region Properties

        public bool IsLoading => _buildHandle.IsValid;
        internal OvrAvatarComputeSkinningVertexBuffer? VertexBuffer => _vertexBuffer;

        internal NativeArray<VertexIndices> MeshAndCompactSkinningIndices => _meshAndCompactSkinningIndices;

        #endregion

        #region Fields

        private OvrTime.SliceHandle _buildHandle;
        private bool _isWaitingForVertexBuffer;

        private OvrAvatarComputeSkinningVertexBuffer? _vertexBuffer;
        private NativeArray<VertexIndices> _meshAndCompactSkinningIndices;

        // This is not owned. Up to caller of this to manage lifecycle
        private NativeArray<UInt16> _externalMeshIndices;

        private Action? _failureCallback;
        private Action? _compactSkinningDataLoadedCallback;
        private Action<bool>? _finishCallback;

        private readonly CAPI.ovrAvatar2CompactSkinningDataId _compactSkinningId;

        #endregion

        #region Static Fields

        private static Dictionary<CAPI.ovrAvatar2CompactSkinningDataId, VertexBufferInfo>? _vertexBufferInfos;

        private static bool _staticMapsInitialized = false;

        #endregion

        #region Nested Types

        internal struct VertexIndices
        {
            public uint compactSkinningIndex; // Index in the compact skinning vertex buffer
            public uint outputBufferIndex; // Index into the mesh output buffer
        }

        private interface IConvertibleTo<T> where T : unmanaged { T Convert(); }

        private struct UInt32Wrapper : IConvertibleTo<UInt32>
        {
            private UInt32 _myValue;
            public UInt32Wrapper(UInt32 myValue)
            {
                _myValue = myValue;
            }
            public uint Convert()
            {
                return _myValue;
            }
        }

        private struct UInt16Wrapper : IConvertibleTo<UInt32>
        {
            private UInt16 _myValue;
            public UInt16Wrapper(UInt16 myValue)
            {
                _myValue = myValue;
            }
            public uint Convert()
            {
                return _myValue;
            }
        }

        private struct UInt8Wrapper : IConvertibleTo<UInt32>
        {
            private byte _myValue;
            public UInt8Wrapper(byte myValue)
            {
                _myValue = myValue;
            }
            public uint Convert()
            {
                return _myValue;
            }
        }

        private class VertexBufferInfo
        {
            private WeakReference<OvrAvatarComputeSkinningVertexBuffer>? _createdBuffer;
            private OvrAvatarComputeSkinningVertexBufferBuilder? _currentBuilder;
            private List<OvrAvatarComputeSkinnedPrimitive>? _pendingLoads;

            private int _bufferRetainCount = 0;

            public bool HasBuffer
            {
                get
                {
                    if (_createdBuffer == null)
                    {
                        return false;
                    }

                    return _createdBuffer.TryGetTarget(out _);
                }
            }

            public bool HasPendingLoads => _pendingLoads?.Count > 0;

            public bool TryGetCreatedBuffer(out OvrAvatarComputeSkinningVertexBuffer? buffer)
            {
                if (_createdBuffer == null)
                {
                    buffer = null;
                    return false;
                }

                return _createdBuffer.TryGetTarget(out buffer);
            }

            public void CreateBuilderIfNeededAndAddPendingLoad(
                OvrAvatarComputeSkinnedPrimitive pending,
                CAPI.ovrAvatar2CompactSkinningDataId id)
            {
                // Check if new builder needs to be kicked off
                if (_currentBuilder == null || !_currentBuilder.IsLoading)
                {
                    _currentBuilder = new OvrAvatarComputeSkinningVertexBufferBuilder(
                        id,
                        OnVertexBufferBuildFailure,
                        OnCompactSkinningDataFinishedFailure,
                        OnVertexBufferCreation);
                }

                _pendingLoads ??= new List<OvrAvatarComputeSkinnedPrimitive>(1);
                _pendingLoads.Add(pending);
            }

            public void RetainBuffer()
            {
                _bufferRetainCount += 1;
            }

            public void ReleaseBuffer()
            {
                _bufferRetainCount -= 1;

                if (_bufferRetainCount <= 0)
                {
                    if (TryGetCreatedBuffer(out var buff))
                    {
                        buff!.Dispose();
                    }
                    _createdBuffer = null;
                }
            }

            public void DisposeBuilder()
            {
                _currentBuilder?.Dispose();
                _currentBuilder = null;
            }

            public void RemovePendingLoad(OvrAvatarComputeSkinnedPrimitive pending)
            {
                _pendingLoads?.Remove(pending);
            }

            private void OnVertexBufferBuildFailure()
            {
                // Notify pending loads of failure
                if (_pendingLoads == null)
                {
                    return;
                }

                // It's possible that the "pending load" callback
                // may try to remove it from the private field
                // while iterating. To avoid, clear out the private field
                // and move into a temporary list to dispatch callbacks from
                var listenersToDispatchTo = _pendingLoads;
                _pendingLoads = new List<OvrAvatarComputeSkinnedPrimitive>();

                foreach (var load in listenersToDispatchTo)
                {
                    load.OnVertexBufferBuildFailed();
                }
            }

            private IEnumerator<OvrTime.SliceStep> OnVertexBufferCreation(OvrAvatarComputeSkinningVertexBuffer buffer)
            {
                _createdBuffer = new WeakReference<OvrAvatarComputeSkinningVertexBuffer>(buffer);

                // Notify pending loads of success

                // If there are no pending loads, then whatever was potentially waiting
                // for this vertex buffer to be built is no longer waiting, in that scenario,
                // free the buffer
                if (!HasPendingLoads)
                {
                    buffer.Dispose();
                    _createdBuffer = null;
                    yield return OvrTime.SliceStep.Cancel;
                }

                Debug.Assert(_pendingLoads != null);

                // It's possible that the "pending load" callback
                // may try to remove it from the private field
                // while iterating. To avoid, clear out the private field
                // and move into a temporary list to dispatch callbacks from
                var listenersToDispatchTo = _pendingLoads!;
                _pendingLoads = new List<OvrAvatarComputeSkinnedPrimitive>();

                foreach (var load in listenersToDispatchTo)
                {
                    if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                    load.OnVertexBufferCreated(buffer, this);
                }
            }

            private void OnCompactSkinningDataFinishedFailure()
            {
                // Notify pending loads that the compact skinning data is no longer needed
                if (_pendingLoads == null)
                {
                    return;
                }

                foreach (var load in _pendingLoads)
                {
                    load.OnVertexBufferBuildFreeCompactSkinning();
                }
            }
        }

        #endregion
    } // end class OvrAvatarComputeSkinnedPrimitive
} // end namespace
