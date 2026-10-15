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

using UnityEngine;
using System;
using System.Threading;
using Unity.Collections.LowLevel.Unsafe;

using static Oculus.Avatar2.CAPI;
using Unity.Collections;

// ReSharper disable once InvalidXmlDocComment
/**
 * @file OvrAvatarSubMeshIdentification.cs
 */
namespace Oculus.Avatar2
{
    public static class OvrAvatarSubMeshIdentification
    {
        private const string subMeshIdLogScope = "ovrAvatarSubMeshId";

        public static uint MAX_NUMBER_EXTENSION_SLOTS_PER_SUBMESH = 1;
        public static uint MAX_NUMBER_SUBMESHES_PER_MATERIAL = 32;
        public static uint MAX_NUMBER_EXTENSIONS_PER_MATERIAL = MAX_NUMBER_EXTENSION_SLOTS_PER_SUBMESH * MAX_NUMBER_SUBMESHES_PER_MATERIAL;
        public static uint MAX_NUMBER_PARAMETERS_PER_MATERIAL = 256;

        public static void ApplyArraysToMaterial(Material mat, CancellationToken ct, ovrAvatar2Id primitiveId)
        {
            ct.ThrowIfCancellationRequested();

            float[] types = new float[MAX_NUMBER_EXTENSIONS_PER_MATERIAL];
            float[] offsets = new float[MAX_NUMBER_EXTENSIONS_PER_MATERIAL];
            float[] parameters = new float[MAX_NUMBER_PARAMETERS_PER_MATERIAL];

            int countExtensionArrayFilled = ExtractMaterialDataFromSdk(ct, primitiveId, ref types, ref offsets, ref parameters);

            mat.SetFloatArray("_SubMeshIdentification", types);
            mat.SetFloatArray("_SubMeshParameterOffsets", offsets);
            mat.SetFloatArray("_SubMeshParameterData", parameters);
            mat.SetInt("_SubMeshIdCount", countExtensionArrayFilled);
            mat.SetInt("_IdSlotsPerSubmesh", (int)MAX_NUMBER_EXTENSION_SLOTS_PER_SUBMESH);
        }

        private static int ExtractMaterialDataFromSdk(CancellationToken ct, ovrAvatar2Id primitiveId, ref float[] types, ref float[] offsets, ref float[] parameters)
        {
            ct.ThrowIfCancellationRequested();
            var floatStride = (UInt32)UnsafeUtility.SizeOf<float>();
            var typesBuffer =
                new NativeArray<float>((int)MAX_NUMBER_EXTENSIONS_PER_MATERIAL, _nativeAllocator, _nativeArrayInit);
            var offsetsBuffer =
                new NativeArray<float>((int)MAX_NUMBER_EXTENSIONS_PER_MATERIAL, _nativeAllocator, _nativeArrayInit);
            var parametersBuffer =
                new NativeArray<float>((int)MAX_NUMBER_PARAMETERS_PER_MATERIAL, _nativeAllocator, _nativeArrayInit);
            UInt32 subMeshCount = 0;
            UInt32 parameterBufferSize = 0;

            try
            {
                IntPtr typesPtr = typesBuffer.GetIntPtr();
                IntPtr offsetsPtr = offsetsBuffer.GetIntPtr();
                IntPtr parametersPtr = parametersBuffer.GetIntPtr();

                if (typesPtr == IntPtr.Zero || offsetsPtr == IntPtr.Zero || parametersPtr == IntPtr.Zero)
                {
                    OvrAvatarLog.LogError(
                        "ERROR: Null buffer allocated for input during `ExtractMaterialDataFromSdk` - aborting",
                        subMeshIdLogScope);
                    return -1;
                }

                var typesBufferSize = typesBuffer.GetBufferSize(floatStride);
                var offsetsBufferSize = offsetsBuffer.GetBufferSize(floatStride);

                var result = CAPI.OvrAvatar2Primitive_GetMaterialBuffers(
                    primitiveId, typesBuffer, offsetsBuffer, parametersBuffer,
                    MAX_NUMBER_EXTENSION_SLOTS_PER_SUBMESH,
                    out subMeshCount,
                    MAX_NUMBER_EXTENSIONS_PER_MATERIAL,
                    out parameterBufferSize);
                ct.ThrowIfCancellationRequested();
                if (!result)
                {
                    OvrAvatarLog.LogError(
                        "ERROR: Avatar SDK encountered an error while filling material parameter arrays.",
                        subMeshIdLogScope);
                }
                ct.ThrowIfCancellationRequested();

                using (var typesSrc =
                       new NativeArray<float>((int)MAX_NUMBER_EXTENSIONS_PER_MATERIAL, _nativeAllocator, _nativeArrayInit))
                {
                    unsafe
                    {
                        var srcPtr = typesSrc.GetPtr();
                        // Check for allocation failure
                        if (srcPtr == null)
                        {
                            OvrAvatarLog.LogError(
                                "ERROR: Null types buffer allocated for output during `ExtractMaterialDataFromSdk` - aborting",
                                subMeshIdLogScope);
                            return -1;
                        }
                        var typesBufferPtr = typesBuffer.GetPtr();
                        for (int i = 0; i < MAX_NUMBER_EXTENSIONS_PER_MATERIAL; ++i)
                        {
                            srcPtr[i] = typesBufferPtr[i]; // should it be ref typesBufferPtr[i] ?
                        }
                    }
                    ct.ThrowIfCancellationRequested();
                    types = typesSrc.ToArray();
                }

                using (var offsetsSrc =
                       new NativeArray<float>((int)MAX_NUMBER_EXTENSIONS_PER_MATERIAL, _nativeAllocator, _nativeArrayInit))
                {
                    unsafe
                    {
                        var srcPtr = offsetsSrc.GetPtr();
                        // Check for allocation failure
                        if (srcPtr == null)
                        {
                            OvrAvatarLog.LogError(
                                "ERROR: Null offsets buffer allocated for output during `ExtractMaterialDataFromSdk` - aborting",
                                subMeshIdLogScope);
                            return -1;
                        }
                        var offsetsBufferPtr = offsetsBuffer.GetPtr();
                        for (int i = 0; i < MAX_NUMBER_EXTENSIONS_PER_MATERIAL; ++i)
                        {
                            srcPtr[i] = offsetsBufferPtr[i]; // should it be ref offsetsBufferPtr[i] ?
                        }
                    }
                    ct.ThrowIfCancellationRequested();
                    offsets = offsetsSrc.ToArray();
                }

                using (var parametersSrc =
                       new NativeArray<float>((int)MAX_NUMBER_PARAMETERS_PER_MATERIAL, _nativeAllocator, _nativeArrayInit))
                {
                    unsafe
                    {
                        var srcPtr = parametersSrc.GetPtr();
                        // Check for allocation failure
                        if (srcPtr == null)
                        {
                            OvrAvatarLog.LogError(
                                "ERROR: Null parameters buffer allocated for output during `ExtractMaterialDataFromSdk` - aborting",
                                subMeshIdLogScope);
                            return -1;
                        }
                        var parametersBufferPtr = parametersBuffer.GetPtr();
                        for (int i = 0; i < MAX_NUMBER_PARAMETERS_PER_MATERIAL; ++i)
                        {
                            srcPtr[i] = parametersBufferPtr[i]; // should it be ref parametersBufferPtr[i] ?
                        }
                    }
                    ct.ThrowIfCancellationRequested();
                    parameters = parametersSrc.ToArray();
                }

            }
            finally
            {
                typesBuffer.Dispose();
                offsetsBuffer.Dispose();
                parametersBuffer.Dispose();
            }

            return (int)subMeshCount;
        }

        public static void DeepCopyFloatArrays(Material destMat, Material srcMat)
        {
            float[] farray = srcMat.GetFloatArray("_SubMeshIdentification");
            if (farray != null)
            {
                destMat.SetFloatArray("_SubMeshIdentification", farray);
            }

            farray = srcMat.GetFloatArray("_SubMeshParameterOffsets");
            if (farray != null)
            {
                destMat.SetFloatArray("_SubMeshParameterOffsets", farray);
            }

            farray = srcMat.GetFloatArray("_SubMeshParameterData");
            if (farray != null)
            {
                destMat.SetFloatArray("_SubMeshParameterData", farray);
            }

            if (srcMat.HasProperty("_SubMeshIdCount") && srcMat.HasProperty("_IdSlotsPerSubmesh"))
            {
                int count = srcMat.GetInt("_SubMeshIdCount");
                destMat.SetInt("_SubMeshIdCount", count);
                destMat.SetInt("_IdSlotsPerSubmesh", (int)MAX_NUMBER_EXTENSION_SLOTS_PER_SUBMESH);
            }
        }

        private const Allocator _nativeAllocator = Allocator.Persistent;
        private const NativeArrayOptions _nativeArrayInit = NativeArrayOptions.UninitializedMemory;
    }
}
