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
using Oculus.Avatar2;

using Unity.Collections;

using UnityEngine;

namespace Oculus.Skinning.GpuSkinning
{
    /**
     * Class representing the "VertexBuffer" used in compute shader based skinning.
     * A "VertexBuffer" can be shared across many different instances of a mesh/primitive
     *
     * NOTE:
     * What is wanted here ideally is that there would be a way to call
     * tell when there are no more references to the ComputeBuffer
     * besides this class and then Dispose of it. Sort of like RefCountDisposable
     * in one of the reactive .NET stuff. Until then, this will just dispose in the finalizer
     * so it will always dispose one garbage collection cycle late. Not the worst thing.
     */
    public sealed class OvrAvatarComputeSkinningVertexBuffer : IDisposable
    {
        internal ComputeBuffer Buffer => _buffer;
        internal NativeArray<byte> CompactSkinningToOrigIndex => _compactSkinningToOrigIndex;

        internal OvrComputeUtils.DataFormatAndStride VertexIndexFormatAndStride { get; }

        public int NumMorphedVerts => _numMorphedVerts;
        public bool HasTangents => _hasTangents;

        internal struct DataFormatsAndStrides
        {
            public OvrComputeUtils.DataFormatAndStride vertexPositions;
            public OvrComputeUtils.DataFormatAndStride vertexNormals;
            public OvrComputeUtils.DataFormatAndStride vertexTangents;
            public OvrComputeUtils.DataFormatAndStride morphDeltas;
            public OvrComputeUtils.DataFormatAndStride jointIndices;
            public OvrComputeUtils.DataFormatAndStride jointWeights;
            public OvrComputeUtils.DataFormatAndStride morphIndices;
            public OvrComputeUtils.DataFormatAndStride nextEntryIndices;
        }

        internal DataFormatsAndStrides FormatsAndStrides { get; }

        internal bool IsDataInClientSpace { get; }
        internal Matrix4x4 ClientSpaceTransform { get; }

        // Takes ownership of compactSkinningInverseReorderBuffer
        internal OvrAvatarComputeSkinningVertexBuffer(
            ComputeBuffer buffer,
            NativeArray<byte> compactSkinningReorderBuffer,
            OvrComputeUtils.DataFormatAndStride vertexIndexFormatAndStride,
            DataFormatsAndStrides formatsAndStrides,
            int numMorphedVerts,
            bool hasTangents,
            bool isDataInClientSpace,
            Matrix4x4 clientSpaceTransform)
        {
            _buffer = buffer;
            _compactSkinningToOrigIndex = compactSkinningReorderBuffer;
            VertexIndexFormatAndStride = vertexIndexFormatAndStride;

            FormatsAndStrides = formatsAndStrides;
            _numMorphedVerts = numMorphedVerts;
            _hasTangents = hasTangents;

            IsDataInClientSpace = isDataInClientSpace;
            ClientSpaceTransform = clientSpaceTransform;
        }

        ~OvrAvatarComputeSkinningVertexBuffer()
        {
            Dispose(false);
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
                _buffer.Release();
                _compactSkinningToOrigIndex.Reset();
            }
        }

        private readonly ComputeBuffer _buffer;
        private NativeArray<byte> _compactSkinningToOrigIndex;

        private readonly int _numMorphedVerts;
        private readonly bool _hasTangents;
    }
}
