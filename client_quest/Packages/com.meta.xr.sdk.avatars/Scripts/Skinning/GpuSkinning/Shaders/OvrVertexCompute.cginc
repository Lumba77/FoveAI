#ifndef OVR_VERTEX_COMPUTE_INCLUDED
#define OVR_VERTEX_COMPUTE_INCLUDED

#include "../../../ShaderUtils/OvrDecodeUtils.cginc"
#include "../../../ShaderUtils/OvrDecodeFormats.cginc"

#include "OvrApplyMorphsAndSkinningParams.cginc"

struct Vertex {
  float4 position;
  float3 normal;
  uint4 jointIndices;
  float4 jointWeights;
  uint vertexBufferIndex;
  uint outputBufferIndex;
};

///////////////////////////////////////////////////
// Neutral Pose
///////////////////////////////////////////////////

float3 OvrDecodeNeutralPoseVec3(
  uint address,
  float3 bias,
  float3 scale,
  int format)
{
  // ASSUMPTION: required to be on 4 byte boundaries
  float3 result = 0.0;

  UNITY_BRANCH switch (format) {
    case OVR_FORMAT_FLOAT_32: {
      result = OvrUnpackFloat3x32(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_HALF_16: {
      result = OvrUnpackHalf3x16(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_UNORM_16: {
      result = OvrUnpackUnorm3x16(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_SNORM_16: {
      result = OvrUnpackSnorm3x16(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_SNORM_10_10_10_2: {
      result = OvrUnpackSnorm3x10_10_10_2(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_UNORM_8: {
      result = OvrUnpackUnorm3x8(globalParams.vertexBuffer, address);
    }
    break;
    default:
      break;
  }

  // Apply scale and bias
  result = mad(result, scale, bias);

  return result;
}

float4 OvrGetNeutralPosePosition(
    uint positions_start_address,
    float3 bias,
    float3 scale,
    uint vertex_index)
{
  const int format = globalParams.vertexPositionsDataFormat;
  const uint stride = globalParams.vertexPositionsDataStride;

  // ASSUMPTION: required to be on 4 byte boundaries
  float4 position = float4(0.0, 0.0, 0.0, 1.0);
  const uint address = mad(vertex_index, stride, positions_start_address);

  position.xyz = OvrDecodeNeutralPoseVec3(address, bias, scale, format);

  return position;
}

float3 OvrGetNeutralPoseNormal(
    uint normals_start_address,
    float3 bias,
    float3 scale,
    uint vertex_index) {
  const int format = globalParams.vertexNormalsDataFormat;
  const uint stride = globalParams.vertexNormalsDataStride;

  // ASSUMPTION: required to be on 4 byte boundaries
  const uint address = mad(vertex_index, stride, normals_start_address);

  float3 norm = OvrDecodeNeutralPoseVec3(address, bias, scale, format);
  norm = normalize(norm);

  return norm;
}

float4 OvrGetNeutralPoseTangent(
    uint tangents_start_address,
    float3 bias,
    float3 scale,
    uint vertex_index)
{
  const int format = globalParams.vertexTangentsDataFormat;
  const uint stride = globalParams.vertexTangentsDataStride;

  // ASSUMPTION: required to be on 4 byte boundaries
  const uint address = mad(vertex_index, stride, tangents_start_address);

  float4 tangent = 0.0;

  // ASSUMPTION: Even if tangent is encoded in a normalized format,
  // it will still be in the range [-1, 1] for signed normalized
  // formats and [0, 1] for unsigned normalized formats. No bias
  // and scale parameters are needed as they can be assumed based on format
  UNITY_BRANCH switch (format) {
    case OVR_FORMAT_FLOAT_32: {
      tangent = OvrUnpackFloat4x32(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_HALF_16: {
      tangent = OvrUnpackHalf4x16(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_UNORM_16: {
      tangent = OvrUnpackUnorm4x16(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_SNORM_16: {
      tangent = OvrUnpackSnorm4x16(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_SNORM_10_10_10_2: {
      tangent = OvrUnpackSnorm4x10_10_10_2(globalParams.vertexBuffer, address);
    }
    break;
    case OVR_FORMAT_UNORM_8: {
      tangent = OvrUnpackUnorm4x8(globalParams.vertexBuffer, address);
    }
    break;
    default:
      break;
  }

  // Apply scale and bias, then normalize
  tangent.xyz = mad(tangent.xyz, scale, bias);
  tangent.xyz = normalize(tangent.xyz);

  // Force tangent w to be -1 or 1 only. Treat any positive or zero value to mean "1"
  // and any negative value to mean "-1"
  tangent.w = tangent.w >= 0.0 ? 1.0 : -1.0;

  return tangent;
}

float4 OvrGetJointWeights(
    in ByteAddressBuffer data_buffer,
    uint joint_weights_address,
    uint vertex_index,
    int format,
    uint stride) {
  // ASSUMPTION: 4 weights per vertex
  float4 weights = float4(0.0, 0.0, 0.0, 0.0);

  UNITY_BRANCH switch (format) {
    case OVR_FORMAT_FLOAT_32:
      // 4 32-bit uints for 4 32-bit floats
      weights = OvrUnpackFloat4x32(
          data_buffer,
          mad(vertex_index, stride, joint_weights_address));
      break;
    case OVR_FORMAT_HALF_16:
      // 2 32-bit uints for 4 16 bit halfs
      weights = OvrUnpackHalf4x16(
          data_buffer,
          mad(vertex_index, stride, joint_weights_address));
      break;
    case OVR_FORMAT_UNORM_16:
      weights = OvrUnpackUnorm4x16(
          data_buffer,
          mad(vertex_index, stride, joint_weights_address));
      break;
    case OVR_FORMAT_UNORM_8:
      weights = OvrUnpackUnorm4x8(
          data_buffer,
          mad(vertex_index, stride, joint_weights_address));
      break;
    default:
      break;
  }

  return weights;
}

uint4 OvrGetJointIndices(
    in ByteAddressBuffer data_buffer,
    uint joint_indices_address,
    uint vertex_index,
    int format,
    uint stride) {
  // ASSUMPTION: 4 indices per vertex
  uint4 indices = uint4(0u, 0u, 0u, 0u);

  UNITY_BRANCH switch (format) {
    case OVR_FORMAT_UINT_16:
      indices = OvrUnpackUint4x16(
          data_buffer,
          mad(vertex_index, stride, joint_indices_address));
      break;
    case OVR_FORMAT_UINT_8:
      indices = OvrUnpackUint4x8(
          data_buffer,
          mad(vertex_index, stride, joint_indices_address));
      break;
    default:
      break;
  }

  return indices;
}

Vertex OvrGetVertexData(
    uint positionsOffsetBytes,
    float3 positionBias,
    float3 positionScale,
    float3 normalBias,
    float3 normalScale,
    uint normalsOffsetBytes,
    uint jointWeightsOffsetBytes,
    uint jointIndicesOffsetBytes,
    uint vertexBufferIndex,
    uint outputBufferIndex)
{
  Vertex vertex;

  vertex.position = OvrGetNeutralPosePosition(
      positionsOffsetBytes,
      positionBias.xyz,
      positionScale.xyz,
      vertexBufferIndex);
  vertex.normal = OvrGetNeutralPoseNormal(
      normalsOffsetBytes,
      normalBias,
      normalScale,
      vertexBufferIndex);

  const uint4 jointIndices = OvrGetJointIndices(
      globalParams.vertexBuffer,
      jointIndicesOffsetBytes,
      vertexBufferIndex,
      globalParams.jointIndicesDataFormat,
      globalParams.jointIndicesDataStride);

  vertex.jointWeights = OvrGetJointWeights(
      globalParams.vertexBuffer,
      jointWeightsOffsetBytes,
      vertexBufferIndex,
      globalParams.jointWeightsDataFormat,
      globalParams.jointWeightsDataStride);
  vertex.jointIndices = jointIndices;

  vertex.outputBufferIndex = outputBufferIndex;
  vertex.vertexBufferIndex = vertexBufferIndex;
  return vertex;
}

#endif
