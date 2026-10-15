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

using UnityEngine;

namespace Oculus.Skinning.GpuSkinning
{
    internal class OvrComputeMeshAnimatorShader : IDisposable
    {
        public struct InitParams
        {
            public bool hasMorphTargets;
            public bool hasTangents;
            public OvrComputeUtils.MaxOutputFrames numOutputSlices;

            public ComputeBuffer vertexBuffer;
            public ComputeBuffer perInstanceHeaderBuffer;
            public ComputeBuffer positionOutputBuffer;
            public ComputeBuffer frenetOutputBuffer;

            public int vertexInfoOffset;
            public int meshInstanceMetaDataOfset;

            public OvrAvatarComputeSkinningVertexBuffer.DataFormatsAndStrides vertexBufferFormatsAndStrides;

            public OvrComputeUtils.DataFormatAndStride positionOutputBufferDataFormatAndStride;

            // NOTE: Assuming uniform scaling, so no separate normal transform needed
            public bool applyAdditionalTransform;
            public Matrix4x4 clientSpaceTransform;
        }

        public struct DynamicParams
        {
            public ComputeBuffer MutableBufferRef;
            public int MutableOffset;
            public int MutableFrameStrideBytes;
            public int MutableBufferFrameIndex;
        }

        // Skinning quality can change at runtime
        public OvrSkinningTypes.SkinningQuality SkinningQuality
        {
            get => _skinningQuality;
            set
            {
                _skinningQuality = value;
            }
        }

        public OvrComputeMeshAnimatorShader(ComputeShader shader, in InitParams initParams)
        {
            Debug.Assert(shader != null);

            // Duplicate shader
            _shader = shader;

            CheckPropertyIdInit();
            GetShaderKernelAndThreadsPerWorkgroup();

            _initParams = initParams;
            _dynamicParams = new DynamicParams();
        }

        private void ReleaseUnmanagedResources()
        {
        }

        public void Dispose()
        {
            ReleaseUnmanagedResources();
            GC.SuppressFinalize(this);
        }

        ~OvrComputeMeshAnimatorShader()
        {
            // Run on main thread
            OvrTime.PostCleanupToUnityMainThread(ReleaseUnmanagedResources);
        }

        public void Dispatch(int startIndex, int numVerts)
        {
            // Set shader properties and keywords
            UpdateStaticShaderKeywords(_initParams);
            SetShaderProperties(_initParams);

            // Since there is currently only a single shared instance of
            // the compute buffer due to Unity memory issues (might have to work around)
            // the "dynamic" data will need to be updated as well
            SetShaderDynamicParameters();

            CalculateWorkGroupsAndDispatch(startIndex, numVerts);
        }

        public void UpdateDynamicParameters(DynamicParams dynamicParams)
        {
            _dynamicParams = dynamicParams;
        }

        private void SetShaderDynamicParameters()
        {
            _shader.SetBuffer(_shaderKernel, _propertyIds.MutableBufferPropId, _dynamicParams.MutableBufferRef);
            _shader.SetInt(_propertyIds.MutableBufferFramePropId, _dynamicParams.MutableBufferFrameIndex);
            _shader.SetInt(_propertyIds.MutableFrameStrideBytesPropId, _dynamicParams.MutableFrameStrideBytes);
            _shader.SetInt(_propertyIds.DispatchMutableOffsetPropId, _dynamicParams.MutableOffset);
        }

        private void CalculateWorkGroupsAndDispatch(int startIndex, int numVerts)
        {
            var numVertsPerWorkGroup = _threadsPerWorkGroup;
            var numWorkGroups = (numVerts + numVertsPerWorkGroup - 1) / numVertsPerWorkGroup;

            var dispatchEndIndex = startIndex + numVerts - 1;

            SetPerDispatchShaderProperties(startIndex, dispatchEndIndex);
            _shader.Dispatch(_shaderKernel, numWorkGroups, 1, 1);
        }

        private void GetShaderKernelAndThreadsPerWorkgroup()
        {
            _shaderKernel = 0;
            int optimalThreadGroupSize = SystemInfo.computeSubGroupSize;

            if (optimalThreadGroupSize == 32 && _shader.HasKernel(KERNEL_NAME_32))
            {
                _shaderKernel = _shader.FindKernel(KERNEL_NAME_32);
            }
            else if (optimalThreadGroupSize == 64 && _shader.HasKernel(KERNEL_NAME_64))
            {
                _shaderKernel = _shader.FindKernel(KERNEL_NAME_64);
            }
            else
            {
                OvrAvatarLog.LogWarning("Error finding compute shader kernel, using default compute kernel", LOG_SCOPE);
            }
            _shader.GetKernelThreadGroupSizes(_shaderKernel, out var threadGroupSizeU, out _, out _);
            _threadsPerWorkGroup = (int)threadGroupSizeU;
        }

        private void UpdateStaticShaderKeywords(in InitParams initParams)
        {
            if (initParams.hasTangents)
            {
                _shader.EnableKeyword(HAS_TANGENTS_KEYWORD);
            }
            else
            {
                _shader.DisableKeyword(HAS_TANGENTS_KEYWORD);
            }

            if (initParams.hasMorphTargets)
            {
                var format = initParams.vertexBufferFormatsAndStrides.morphIndices.dataFormat;
                switch (format)
                {
                    case CAPI.ovrAvatar2DataFormat.U16:
                        _shader.EnableKeyword(MORPH_INDEX_FORMAT_UINT16_KEYWORD);
                        break;
                    case CAPI.ovrAvatar2DataFormat.U8:
                        _shader.DisableKeyword(MORPH_INDEX_FORMAT_UINT16_KEYWORD);
                        break;
                    default:
                        OvrAvatarLog.LogError($"Unsupported morph index format {format}", LOG_SCOPE);
                        _shader.DisableKeyword(MORPH_INDEX_FORMAT_UINT16_KEYWORD);
                        break;
                }

                format = initParams.vertexBufferFormatsAndStrides.nextEntryIndices.dataFormat;
                switch (format)
                {
                    case CAPI.ovrAvatar2DataFormat.U32:
                        _shader.EnableKeyword(NEXT_ENTRY_FORMAT_UINT32_KEYWORD);
                        _shader.DisableKeyword(NEXT_ENTRY_FORMAT_UINT16_KEYWORD);
                        break;
                    case CAPI.ovrAvatar2DataFormat.U16:
                        _shader.DisableKeyword(NEXT_ENTRY_FORMAT_UINT32_KEYWORD);
                        _shader.EnableKeyword(NEXT_ENTRY_FORMAT_UINT16_KEYWORD);
                        break;
                    case CAPI.ovrAvatar2DataFormat.U8:
                        _shader.DisableKeyword(NEXT_ENTRY_FORMAT_UINT32_KEYWORD);
                        _shader.DisableKeyword(NEXT_ENTRY_FORMAT_UINT16_KEYWORD);
                        break;
                    default:
                        OvrAvatarLog.LogError($"Unsupported next entry format {format}", LOG_SCOPE);
                        _shader.DisableKeyword(NEXT_ENTRY_FORMAT_UINT32_KEYWORD);
                        _shader.DisableKeyword(NEXT_ENTRY_FORMAT_UINT16_KEYWORD);
                        break;
                }

                format = initParams.vertexBufferFormatsAndStrides.morphDeltas.dataFormat;
                switch (format)
                {
                    case CAPI.ovrAvatar2DataFormat.Snorm10_10_10_2:
                        _shader.EnableKeyword(MORPH_DELTA_FORMAT_SNORM10_KEYWORD);
                        break;
                    case CAPI.ovrAvatar2DataFormat.F32:
                        _shader.DisableKeyword(MORPH_DELTA_FORMAT_SNORM10_KEYWORD);
                        break;
                    default:
                        _shader.DisableKeyword(MORPH_DELTA_FORMAT_SNORM10_KEYWORD);
                        OvrAvatarLog.LogError($"Unsupported morph delta format {format}", LOG_SCOPE);
                        break;
                }
            }
        }

        private void SetShaderProperties(in InitParams initParams)
        {
            _shader.SetBuffer(_shaderKernel, _propertyIds.VertexBufferPropId, initParams.vertexBuffer);
            _shader.SetBuffer(_shaderKernel, _propertyIds.PerInstanceHeaderBufferPropId, initParams.perInstanceHeaderBuffer);
            _shader.SetBuffer(_shaderKernel, _propertyIds.PositionOutputBufferPropId, initParams.positionOutputBuffer);
            _shader.SetBuffer(_shaderKernel, _propertyIds.FrenetOutputBufferPropId, initParams.frenetOutputBuffer);

            _shader.SetInt(_propertyIds.VertexInfoOffsetPropId, initParams.vertexInfoOffset);
            _shader.SetInt(_propertyIds.MeshInstanceMetaDataOffsetPropId, initParams.meshInstanceMetaDataOfset);

            _shader.SetInt(
                _propertyIds.VertexPositionDataFormatPropId,
                (int)OvrComputeUtils.GetDataFormatShaderPropertyValue(
                    initParams.vertexBufferFormatsAndStrides.vertexPositions.dataFormat));
            _shader.SetInt(
                _propertyIds.VertexPositionDataStridePropId,
                initParams.vertexBufferFormatsAndStrides.vertexPositions.strideBytes);

            _shader.SetInt(
                _propertyIds.VertexNormalDataFormatPropId,
                (int)OvrComputeUtils.GetDataFormatShaderPropertyValue(
                    initParams.vertexBufferFormatsAndStrides.vertexNormals.dataFormat));
            _shader.SetInt(
                _propertyIds.VertexNormalDataStridePropId,
                initParams.vertexBufferFormatsAndStrides.vertexNormals.strideBytes);

            _shader.SetInt(
                _propertyIds.JointIndicesDataFormatPropId,
                (int)OvrComputeUtils.GetDataFormatShaderPropertyValue(
                    initParams.vertexBufferFormatsAndStrides.jointIndices.dataFormat));
            _shader.SetInt(
                _propertyIds.JointIndicesDataStridePropId,
                initParams.vertexBufferFormatsAndStrides.jointIndices.strideBytes);

            _shader.SetInt(
                _propertyIds.JointWeightsDataFormatPropId,
                (int)OvrComputeUtils.GetDataFormatShaderPropertyValue(
                    initParams.vertexBufferFormatsAndStrides.jointWeights.dataFormat));
            _shader.SetInt(
                _propertyIds.JointWeightsDataStridePropId,
                initParams.vertexBufferFormatsAndStrides.jointWeights.strideBytes);

            _shader.SetInt(
                _propertyIds.PositionOutputDataFormatPropId,
                (int)OvrComputeUtils.GetDataFormatShaderPropertyValue(
                    initParams.positionOutputBufferDataFormatAndStride.dataFormat));
            _shader.SetInt(
                _propertyIds.PositionOutputDataStridePropId,
                initParams.positionOutputBufferDataFormatAndStride.strideBytes);

            _shader.SetBool(
                _propertyIds.ApplyAdditionalTransformPropId,
                initParams.applyAdditionalTransform);
            _shader.SetMatrix(_propertyIds.OutputTransformPropId, initParams.clientSpaceTransform);

            // See if bitangent sign needs to be flipped or not
            // TODO: T146363567 - verify this logic
            Vector4 v = initParams.clientSpaceTransform * Vector4.one;
            float temp = v.x * v.y * v.z;
            _shader.SetFloat(_propertyIds.OutputTransformBitangentSignFactorPropId, temp < 0.0f ? -1.0f : 1.0f);

            // Set output slice count
            switch (initParams.numOutputSlices)
            {
                case OvrComputeUtils.MaxOutputFrames.ONE:
                    _shader.SetInt(_propertyIds.NumOutputEntriesPerVertPropId, 1);
                    break;
                case OvrComputeUtils.MaxOutputFrames.TWO:
                    _shader.SetInt(_propertyIds.NumOutputEntriesPerVertPropId, 2);
                    break;
                case OvrComputeUtils.MaxOutputFrames.THREE:
                    _shader.SetInt(_propertyIds.NumOutputEntriesPerVertPropId, 3);
                    break;
                case OvrComputeUtils.MaxOutputFrames.INVALID:
                default:
                    OvrAvatarLog.LogError("Unhandled number of output frames, using 1", LOG_SCOPE);
                    _shader.SetInt(_propertyIds.NumOutputEntriesPerVertPropId, 1);
                    break;
            }

            // Skinning max joints per vert
            switch (SkinningQuality)
            {
                case OvrSkinningTypes.SkinningQuality.Bone1:
                    _shader.SetInt(_propertyIds.MaxJointsPerVertPropId, 1);
                    break;
                case OvrSkinningTypes.SkinningQuality.Bone2:
                    _shader.SetInt(_propertyIds.MaxJointsPerVertPropId, 2);
                    break;
                case OvrSkinningTypes.SkinningQuality.Bone4:
                    _shader.SetInt(_propertyIds.MaxJointsPerVertPropId, 4);
                    break;
                case OvrSkinningTypes.SkinningQuality.Invalid:
                default:
                    _shader.SetInt(_propertyIds.MaxJointsPerVertPropId, 0);
                    break;
            }

            // Optional parameters
            if (initParams.hasTangents)
            {
                _shader.SetInt(
                    _propertyIds.VertexTangentDataFormatPropId,
                    (int)OvrComputeUtils.GetDataFormatShaderPropertyValue(
                        initParams.vertexBufferFormatsAndStrides.vertexTangents.dataFormat));
                _shader.SetInt(
                    _propertyIds.VertexTangentDataStridePropId,
                    initParams.vertexBufferFormatsAndStrides.vertexTangents.strideBytes);
            }

            if (initParams.hasMorphTargets)
            {
                _shader.SetInt(
                    _propertyIds.MorphTargetDeltasDataStridePropId,
                    initParams.vertexBufferFormatsAndStrides.morphDeltas.strideBytes);
            }
        }

        private void SetPerDispatchShaderProperties(int dispatchStartVertIndex, int dispatchEndVertIndex)
        {
            _shader.SetInt(_propertyIds.DispatchVertStartIndexPropId, dispatchStartVertIndex);
            _shader.SetInt(_propertyIds.DispatchVertEndIndexPropId, dispatchEndVertIndex);
        }

        private static void CheckPropertyIdInit()
        {
            if (!_propertyIds.IsValid)
            {
                _propertyIds = new ComputePropertyIds(ComputePropertyIds.InitMethod.PropertyToId);
            }
        }

        private readonly struct ComputePropertyIds
        {
            public readonly int VertexBufferPropId;
            public readonly int PerInstanceHeaderBufferPropId;
            public readonly int MutableBufferPropId;
            public readonly int MutableBufferFramePropId;
            public readonly int PositionOutputBufferPropId;
            public readonly int FrenetOutputBufferPropId;

            public readonly int VertexInfoOffsetPropId;
            public readonly int MutableFrameStrideBytesPropId;
            public readonly int MeshInstanceMetaDataOffsetPropId;

            public readonly int DispatchMutableOffsetPropId;
            public readonly int DispatchVertStartIndexPropId;
            public readonly int DispatchVertEndIndexPropId;

            public readonly int VertexPositionDataFormatPropId;
            public readonly int VertexNormalDataFormatPropId;
            public readonly int VertexTangentDataFormatPropId;
            public readonly int JointWeightsDataFormatPropId;
            public readonly int JointIndicesDataFormatPropId;
            public readonly int PositionOutputDataFormatPropId;

            public readonly int VertexPositionDataStridePropId;
            public readonly int VertexNormalDataStridePropId;
            public readonly int VertexTangentDataStridePropId;
            public readonly int JointWeightsDataStridePropId;
            public readonly int JointIndicesDataStridePropId;
            public readonly int MorphTargetDeltasDataStridePropId;
            public readonly int PositionOutputDataStridePropId;

            public readonly int NumOutputEntriesPerVertPropId;
            public readonly int MaxJointsPerVertPropId;

            public readonly int ApplyAdditionalTransformPropId;
            public readonly int OutputTransformPropId;
            public readonly int OutputTransformBitangentSignFactorPropId;

            // These will both be 0 if default initialized, otherwise they are guaranteed unique
            public bool IsValid => VertexBufferPropId != PerInstanceHeaderBufferPropId;

            public enum InitMethod
            {
                PropertyToId
            }

            public ComputePropertyIds(InitMethod initMethod)
            {
                VertexBufferPropId = Shader.PropertyToID("_VertexBuffer");
                PerInstanceHeaderBufferPropId = Shader.PropertyToID("_PerInstanceHeaderBuffer");
                MutableBufferPropId = Shader.PropertyToID("_MutableBuffer");
                MutableBufferFramePropId = Shader.PropertyToID("_MutableBufferFrameIndex");
                PositionOutputBufferPropId = Shader.PropertyToID("_PositionOutputBuffer");
                FrenetOutputBufferPropId = Shader.PropertyToID("_FrenetOutputBuffer");

                VertexInfoOffsetPropId = Shader.PropertyToID("_VertexInfoOffsetBytes");
                MutableFrameStrideBytesPropId = Shader.PropertyToID("_MutableFrameStrideBytes");
                MeshInstanceMetaDataOffsetPropId = Shader.PropertyToID("_MeshInstanceMetaDataOffset");

                DispatchMutableOffsetPropId = Shader.PropertyToID("_DispatchMutableOffset");
                DispatchVertStartIndexPropId = Shader.PropertyToID("_DispatchStartVertIndex");
                DispatchVertEndIndexPropId = Shader.PropertyToID("_DispatchEndVertIndex");

                VertexPositionDataFormatPropId = Shader.PropertyToID("_VertexPositionsDataFormat");
                VertexNormalDataFormatPropId = Shader.PropertyToID("_VertexNormalsDataFormat");
                VertexTangentDataFormatPropId = Shader.PropertyToID("_VertexTangentsDataFormat");
                JointWeightsDataFormatPropId = Shader.PropertyToID("_JointWeightsDataFormat");
                JointIndicesDataFormatPropId = Shader.PropertyToID("_JointIndicesDataFormat");
                PositionOutputDataFormatPropId = Shader.PropertyToID("_PositionOutputBufferDataFormat");

                NumOutputEntriesPerVertPropId = Shader.PropertyToID("_NumOutputEntriesPerVert");
                MaxJointsPerVertPropId = Shader.PropertyToID("_MaxJointsPerVert");

                VertexPositionDataStridePropId = Shader.PropertyToID("_VertexPositionsDataStride");
                VertexNormalDataStridePropId = Shader.PropertyToID("_VertexNormalsDataStride");
                VertexTangentDataStridePropId = Shader.PropertyToID("_VertexTangentsDataStride");
                JointWeightsDataStridePropId = Shader.PropertyToID("_JointWeightsDataStride");
                JointIndicesDataStridePropId = Shader.PropertyToID("_JointIndicesDataStride");
                MorphTargetDeltasDataStridePropId = Shader.PropertyToID("_MorphDeltasDataStride");
                PositionOutputDataStridePropId = Shader.PropertyToID("_PositionOutputBufferDataStride");

                ApplyAdditionalTransformPropId = Shader.PropertyToID("_ApplyAdditionalTransform");
                OutputTransformPropId = Shader.PropertyToID("_OutputTransform");
                OutputTransformBitangentSignFactorPropId = Shader.PropertyToID("_OutputTransformBitangentSignFactor");
            }
        }

        #region Private Consts and Fields

        private static ComputePropertyIds _propertyIds = default;

        private const string LOG_SCOPE = "OvrComputeMeshAnimatorShader";

        private const string KERNEL_NAME_64 = "CSMain64";
        private const string KERNEL_NAME_32 = "CSMain32";

        private const string HAS_TANGENTS_KEYWORD = "OVR_HAS_TANGENTS";

        private const string MORPH_INDEX_FORMAT_UINT16_KEYWORD = "OVR_MORPH_INDEX_FORMAT_UINT16";

        private const string NEXT_ENTRY_FORMAT_UINT16_KEYWORD = "OVR_NEXT_ENTRY_FORMAT_UINT16";
        private const string NEXT_ENTRY_FORMAT_UINT32_KEYWORD = "OVR_NEXT_ENTRY_FORMAT_UINT32";

        private const string MORPH_DELTA_FORMAT_SNORM10_KEYWORD = "OVR_MORPH_DELTA_FORMAT_SNORM10";

        private OvrSkinningTypes.SkinningQuality _skinningQuality;

        private readonly ComputeShader _shader;
        private int _shaderKernel;
        private int _threadsPerWorkGroup;

        private readonly InitParams _initParams;
        private DynamicParams _dynamicParams;

        #endregion
    }
}
