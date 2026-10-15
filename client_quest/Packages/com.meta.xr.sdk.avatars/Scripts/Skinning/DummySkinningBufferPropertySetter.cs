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
using UnityEngine;

namespace Oculus.Skinning
{
    // This class is required to workaround a bug/feature? when using Vulkan. If there are
    // ByteAddressBuffers or StructuredBuffers that exist in the shader (even if not used at runtime), they
    // must have their buffers set with something. This also causes issues with the Unity Editor that can't
    // be worked around here.
    internal class DummySkinningBufferPropertySetter : IDisposable
    {
        private static AttributePropertyIds _propertyIds = default;

        private ComputeBuffer _dummyBuffer;

        // Dummy buffers method
        public DummySkinningBufferPropertySetter()
        {
            CheckPropertyIdInit();

            _dummyBuffer = new ComputeBuffer(1, sizeof(uint));
        }

        public void SetComputeSkinningBuffersInMatBlock(MaterialPropertyBlock matBlock)
        {
            matBlock.SetBuffer(_propertyIds.ComputeSkinnerPositionBuffer, _dummyBuffer);
            matBlock.SetBuffer(_propertyIds.ComputeSkinnerFrenetBuffer, _dummyBuffer);
        }

        public void Dispose()
        {
            _dummyBuffer.Dispose();
        }

        private static void CheckPropertyIdInit()
        {
            if (!_propertyIds.IsValid)
            {
                _propertyIds = new AttributePropertyIds(AttributePropertyIds.InitMethod.PropertyToId);
            }
        }

        //////////////////////////
        // AttributePropertyIds //
        //////////////////////////
        private struct AttributePropertyIds
        {
            public readonly int ComputeSkinnerPositionBuffer;
            public readonly int ComputeSkinnerFrenetBuffer;

            // These will both be 0 if default initialized, otherwise they are guaranteed unique
            public bool IsValid => ComputeSkinnerPositionBuffer != ComputeSkinnerFrenetBuffer;

            public enum InitMethod { PropertyToId }
            public AttributePropertyIds(InitMethod initMethod)
            {
                ComputeSkinnerPositionBuffer = Shader.PropertyToID("_OvrPositionBuffer");
                ComputeSkinnerFrenetBuffer = Shader.PropertyToID("_OvrFrenetBuffer");
            }
        }
    }
}
