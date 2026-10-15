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
using Oculus.Skinning.GpuSkinning;
using Unity.Collections;
using UnityEngine;
using UnityEngine.Profiling;

using static Oculus.Avatar2.CAPI;

namespace Oculus.Avatar2
{
    public sealed class OvrAvatarSkinningController : System.IDisposable
    {
        // Avoid skinning more avatars than technically feasible
        public const uint MaxGpuSkinnedAvatars = MaxSkinnedAvatarsPerFrame * 8;

        // Avoid skinning more avatars than GPU resources are preallocated for
        public const uint MaxSkinnedAvatarsPerFrame = 32;

        public const int JOINT_MATRIX_STRIDE_BYTES = 16 * sizeof(float);

        public const int MORPH_WEIGHT_STRIDE_BYTES = sizeof(float);

        // The maximum # of joints is measured to be 720, rounded to the next power of 2. Date: 3/10/2025
        private const uint DEFAULT_NUM_JOINTS = 1024;

        // The maximum # of morph targets is measured to be 692, rounded to the next power of 2. Date: 3/10/2025
        private const uint DEFAULT_NUM_MORPH_WEIGHTS = 1024;

        public const uint DEFAULT_MUTABLE_STRIDE_BYTES = DEFAULT_NUM_JOINTS * JOINT_MATRIX_STRIDE_BYTES + DEFAULT_NUM_MORPH_WEIGHTS * MORPH_WEIGHT_STRIDE_BYTES;

        public int MutableBufferFrameIndex => _currentFrameIndex;

        public int MutableFrameStrideBytes = (int)(MaxSkinnedAvatarsPerFrame * DEFAULT_MUTABLE_STRIDE_BYTES);

        // Only meaningful when using compute skinner.
        public ComputeBuffer MutableBuffer = null;

        private const int NumExpectedAvatars = 16;

        private readonly List<OvrGpuMorphTargetsCombiner> _activeCombinerList = new List<OvrGpuMorphTargetsCombiner>(NumExpectedAvatars);
        private readonly List<IOvrGpuSkinner> _activeSkinnerList = new List<IOvrGpuSkinner>(NumExpectedAvatars);
        private readonly List<OvrComputeMeshAnimator> _activeAnimators = new List<OvrComputeMeshAnimator>(NumExpectedAvatars);

        private NativeArray<byte> _stagingMutableBuffer;
        private int _perFrameMutableOffset = 0;
        private int _currentFrameIndex = 0;

        private OvrComputeBufferPool bufferPool = null;

        // usingGPUskinner and usingComputeSkinner controlls allocation for their respective resources.
        // These two flags should be mutually exclusive except for debug scenario
        public OvrAvatarSkinningController(bool usingGPUskinner, bool usingComputeSkinner)
        {
            if (usingGPUskinner && usingComputeSkinner)
            {
                OvrAvatarLog.LogWarning("GPU skinner and computer skinner should not be enabled at the same time except for debug purposes.");
            }

            if (usingGPUskinner)
            {
                bufferPool = new OvrComputeBufferPool();
            }

            if (usingComputeSkinner)
            {
                if (_stagingMutableBuffer.IsCreated)
                {
                    _stagingMutableBuffer.Dispose();
                }
                _stagingMutableBuffer = new NativeArray<byte>(MutableFrameStrideBytes, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
                MutableBuffer = OvrComputeUtils.CreateUnsynchronizedRawComputeBuffer((uint)(MutableFrameStrideBytes * GetNumDynamicFrames()));
            }
        }

        public NativeArray<byte> PushMutable(int mutableSize, out int mutableOffset)
        {
            int requiredSize = mutableSize + _perFrameMutableOffset;
            OvrAvatarLog.Assert(requiredSize >= 0 && requiredSize < Int32.MaxValue);

            if (requiredSize > MutableFrameStrideBytes)
            {
                OvrAvatarLog.LogWarning($"Mutable buffer overflow. This degrades performance. Please consider increasing DEFAULT_NUM_JOINTS and DEFAULT_NUM_MORPH_WEIGHTS. Current MutableFrameStrideBytes: {_stagingMutableBuffer.Length}, Required Size: {requiredSize}");
                while (MutableFrameStrideBytes < requiredSize)
                {
                    MutableFrameStrideBytes *= 2;
                }
                NativeArray<byte> newStagingMutableBuffer = new NativeArray<byte>(MutableFrameStrideBytes, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
                newStagingMutableBuffer.GetSubArray(0, _stagingMutableBuffer.Length).CopyFrom(_stagingMutableBuffer);
                _stagingMutableBuffer.Dispose();
                _stagingMutableBuffer = newStagingMutableBuffer;

                ComputeBuffer newMutableBuffer = OvrComputeUtils.CreateUnsynchronizedRawComputeBuffer((uint)(MutableFrameStrideBytes * GetNumDynamicFrames()));
                MutableBuffer.Dispose();
                MutableBuffer = newMutableBuffer;
            }

            mutableOffset = _perFrameMutableOffset;
            _perFrameMutableOffset += mutableSize;
            return _stagingMutableBuffer.GetSubArray(mutableOffset, mutableSize);
        }

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        private void UploadMutableFrame()
        {
            var buffer = MutableBuffer.BeginWrite<byte>(_currentFrameIndex * MutableFrameStrideBytes, _perFrameMutableOffset);
            buffer.CopyFrom(_stagingMutableBuffer.GetSubArray(0, _perFrameMutableOffset));
            MutableBuffer.EndWrite<byte>(_perFrameMutableOffset);
            _perFrameMutableOffset = 0;
        }

        private void Dispose(bool isMainThread)
        {
            bufferPool?.Dispose();
            MutableBuffer?.Dispose();
            MutableBuffer = null;
            if (_stagingMutableBuffer.IsCreated)
            {
                _stagingMutableBuffer.Dispose();
            }
        }

        ~OvrAvatarSkinningController()
        {
            Dispose(false);
        }

        internal void AddActiveCombiner(OvrGpuMorphTargetsCombiner combiner)
        {
            AddGpuSkinningElement(_activeCombinerList, combiner);
        }

        internal void AddActiveSkinner(IOvrGpuSkinner skinner)
        {
            AddGpuSkinningElement(_activeSkinnerList, skinner);
        }

        internal void AddActivateComputeAnimator(OvrComputeMeshAnimator meshAnimator)
        {
            AddGpuSkinningElement(_activeAnimators, meshAnimator);
        }

        // This behaviour is manually updated at a specific time during OvrAvatarManager::Update()
        // to prevent issues with Unity script update ordering
        internal void UpdateInternal()
        {
            Profiler.BeginSample("OvrAvatarSkinningController::UpdateInternal");
            using var livePerfMarker = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.SkinningController);

            if (_activeCombinerList.Count > 0)
            {
                Profiler.BeginSample("OvrAvatarSkinningController.CombinerCalls");
                using var livePerfMarker_Combine = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.SkinningController_Combine);
                foreach (var combiner in _activeCombinerList)
                {
                    combiner.CombineMorphTargetWithCurrentWeights();
                }
                _activeCombinerList.Clear();
                Profiler.EndSample(); // "OvrAvatarSkinningController.CombinerCalls"
            }

            if (_activeSkinnerList.Count > 0)
            {
                Profiler.BeginSample("OvrAvatarSkinningController.SkinnerCalls");
                using var livePerfMarker_Skinner = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.SkinningController_Skinner);
                foreach (var skinner in _activeSkinnerList)
                {
                    skinner.UpdateOutputTexture();
                }
                _activeSkinnerList.Clear();
                Profiler.EndSample(); // "OvrAvatarSkinningController.SkinnerCalls"
            }

            if (_activeAnimators.Count > 0)
            {
                Profiler.BeginSample("OvrAvatarSkinningController.AnimatorDispatches");
                using var livePerfMarker_Animator = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.SkinningController_Animator);
                UploadMutableFrame();
                foreach (var animator in _activeAnimators)
                {
                    animator.UpdateOutputs();
                }
                _activeAnimators.Clear();
                _currentFrameIndex = (_currentFrameIndex + 1) % GetNumDynamicFrames();
                Profiler.EndSample(); // "OvrAvatarSkinningController.AnimatorDispatches"
            }

            Profiler.EndSample();
        }

        private void AddGpuSkinningElement<T>(List<T> list, T element) where T : class
        {
            Debug.Assert(element != null);
            Debug.Assert(!list.Contains(element));
            list.Add(element);
        }

        internal void StartFrame()
        {
            bufferPool?.StartFrame();
        }

        internal void EndFrame()
        {
            bufferPool?.EndFrame();
        }

        internal OvrComputeBufferPool.EntryJoints GetNextEntryJoints()
        {
            return bufferPool.GetNextEntryJoints();
        }

        internal ComputeBuffer GetJointBuffer()
        {
            return bufferPool.GetJointBuffer();
        }

        internal ComputeBuffer GetWeightsBuffer()
        {
            return bufferPool.GetWeightsBuffer();
        }

        internal OvrComputeBufferPool.EntryWeights GetNextEntryWeights(int numMorphTargets)
        {
            return bufferPool.GetNextEntryWeights(numMorphTargets);
        }

        // 3 "should" be enough for VR(2 if using low latency mode).
        // use 4 just in case, might be needed in Editor. Increase if seeing really strange behavior
        // outside of VR. If not enough, you could be writing to memory that the GPU is actively using to render.
        // Could change to use a fence/something like that if a set number of "double/triple/quad buffering"
        // is insufficient or wasteful
        private const int NUM_DYNAMIC_FRAMES = 4;
        private const int NUM_DYNAMIC_FRAMES_FOR_BATCHMODE = 256;

        internal int GetNumDynamicFrames()
        {
            return Application.isBatchMode ? NUM_DYNAMIC_FRAMES_FOR_BATCHMODE : NUM_DYNAMIC_FRAMES;
        }
    }
}
