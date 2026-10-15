#ifndef OVR_OUTPUT_BUFFER_COMPUTE_INCLUDED
#define OVR_OUTPUT_BUFFER_COMPUTE_INCLUDED

#include "../../../ShaderUtils/OvrDecodeUtils.cginc"
#include "../../../ShaderUtils/OvrDecodeFormats.cginc"

#include "OvrApplyMorphsAndSkinningParams.cginc"

//////////////////////////////////////////////////////
// Output
//////////////////////////////////////////////////////

void StoreVertexNormal(
  uint output_buffer_start_address,
  in float3 normal,
  uint output_index)
{
  // Normalize on store
  const uint address = mad(output_index, globalParams.frenetOutputDataStride, output_buffer_start_address);
  float3 normalized = normalize(normal.xyz);

  UNITY_BRANCH switch (globalParams.frenetOutputDataFormat) {
    case OVR_FORMAT_SNORM_10_10_10_2: {
      OvrStoreUint(
        globalParams.frenetOutputBuffer,
        address,
        OvrPackSnorm4x10_10_10_2(float4(normalized, 0.0)));
    }
    break;
    default:
      // Error
      break;
  }
}

void StoreVertexTangent(
  uint output_buffer_start_address,
  in float4 tangent,
  uint output_index)
{
  // Normalize on store
  const uint address = mad(output_index, globalParams.frenetOutputDataStride, output_buffer_start_address);
  float3 normalized = normalize(tangent.xyz);

  UNITY_BRANCH switch (globalParams.frenetOutputDataFormat) {
    case OVR_FORMAT_SNORM_10_10_10_2: {
      OvrStoreUint(
        globalParams.frenetOutputBuffer,
        address,
        OvrPackSnorm4x10_10_10_2(float4(normalized, tangent.w)));
    }
    break;
    default:
      // Error
      break;
  }
}

void StoreVertexPositionFloat4x32(
  uint output_buffer_start_address,
  in float4 position,
  uint output_index)
{
  const uint address = mad(output_index, globalParams.positionOutputDataStride, output_buffer_start_address);
  const uint4 packed_data = asuint(position);

  OvrStoreUint4(globalParams.positionOutputBuffer, address, packed_data);
}

void StoreVertexPositionHalf4x16(
  uint output_buffer_start_address,
  in float4 position,
  uint output_index)
{
  const uint address = mad(output_index, globalParams.positionOutputDataStride, output_buffer_start_address);
  const uint2 packed_data = uint2(OvrPackHalf2x16(position.xy), OvrPackHalf2x16(position.zw));

  OvrStoreUint2(globalParams.positionOutputBuffer, address, packed_data);
}

void StoreVertexPositionUnorm4x16(
    uint output_buffer_start_address,
    in float4 position,
    in float3 position_bias,
    in float3 position_scale,
    uint output_index) {
  const uint address = mad(output_index, globalParams.positionOutputDataStride, output_buffer_start_address);

  // Normalize to 0 -> 1 but given the bias and scale
  // ASSUMPTION: Assuming the position_bias and position_scale will be large enough
  // to place in the range 0 -> 1
  float4 normalized = float4((position.xyz + position_bias) * position_scale, position.w);
  const uint2 packed_data = uint2(OvrPackUnorm2x16(normalized.xy), OvrPackUnorm2x16(normalized.zw));

  OvrStoreUint2(globalParams.positionOutputBuffer, address, packed_data);
}

void StoreVertexPositionUnorm4x8(
    uint output_buffer_start_address,
    in float4 position,
    in float3 position_bias,
    in float3 position_scale,
    uint output_index) {
  const uint address = mad(output_index, globalParams.positionOutputDataStride, output_buffer_start_address);

  // Normalize to 0 -> 1 but given the offset and scale
  // ASSUMPTION: Assuming the position_offset and position_scale will be large enough
  // to place in the range 0 -> 1
  const float4 normalized = float4((position.xyz + position_bias) * position_scale, position.w);
  const uint packed_data = OvrPackUnorm4x8(normalized);

  OvrStoreUint(globalParams.positionOutputBuffer, address, packed_data);
}

uint CalculatePositionOutputIndex(
    uint vertex_output_index,
    uint num_slices_per_attribute,
    uint output_slice) {
  return vertex_output_index * num_slices_per_attribute + output_slice;
}

uint CalculateNormalOutputIndex(
    uint vertex_output_index,
    uint num_slices_per_attribute,
    uint output_slice,
    bool has_tangents) {
  // *2 if interleaving tangent
  return (has_tangents ? 2u : 1u) * vertex_output_index * num_slices_per_attribute + output_slice;
}

void StoreVertexPosition(
    uint output_buffer_start_address,
    float3 position_bias,
    float3 position_scale,
    in float4 position,
    uint output_index) {
  UNITY_BRANCH switch (globalParams.positionOutputDataFormat) {
    case OVR_FORMAT_FLOAT_32:
      StoreVertexPositionFloat4x32(
          output_buffer_start_address,
          position,
          output_index);
      break;
    case OVR_FORMAT_HALF_16:
      StoreVertexPositionHalf4x16(
          output_buffer_start_address,
          position,
          output_index);
      break;
    case OVR_FORMAT_UNORM_16:
      StoreVertexPositionUnorm4x16(
          output_buffer_start_address,
          position,
          position_bias,
          position_scale,
          output_index);
      break;
    case OVR_FORMAT_UNORM_8:
      StoreVertexPositionUnorm4x8(
          output_buffer_start_address,
          position,
          position_bias,
          position_scale,
          output_index);
      break;
    default:
      // Error
      break;
  }
}

// Compiler should hopefully optimize out any potential branches due to static const bool values,
// and otherwise, branches should be based on uniform parameters passed in which
// should make their just the branch and not cause diverging branches across workgroups
// Compiler should also optimize out unused parameters
void StoreVertexOutput(
    uint position_output_buffer_start_address,
    uint frenet_output_buffer_start_address,
    float3 position_bias,
    float3 position_scale,
    in float4 position,
    in float3 normal,
    in float4 tangent,
    uint vertex_output_index,
    uint output_slice) {
  const uint pos_output_index = CalculatePositionOutputIndex(
      vertex_output_index,
      globalParams.numOutputSlicesPerAttribute,
      output_slice);
  const uint norm_output_index = CalculateNormalOutputIndex(
      vertex_output_index,
      globalParams.numOutputSlicesPerAttribute,
      output_slice,
      globalParams.applyTangents);

  StoreVertexPosition(
      position_output_buffer_start_address,
      position_bias,
      position_scale,
      position,
      pos_output_index);

  StoreVertexNormal(
      frenet_output_buffer_start_address,
      normal,
      norm_output_index);

  if (globalParams.applyTangents) {
    const int tangent_output_index = norm_output_index + globalParams.numOutputSlicesPerAttribute;

    StoreVertexTangent(
        frenet_output_buffer_start_address,
        tangent,
        tangent_output_index);
  }
}

#endif
