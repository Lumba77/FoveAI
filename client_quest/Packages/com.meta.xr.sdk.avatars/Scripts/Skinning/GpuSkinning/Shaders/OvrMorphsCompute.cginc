#ifndef OVR_MORPHS_COMPUTE_INCLUDED
#define OVR_MORPHS_COMPUTE_INCLUDED

#include "OvrMorphsComputeParams.cginc"

void OvrApplyCompactMorphsNoTangents(
    in OvrCompactMorphsParams params,
    inout float4 position,
    inout float3 normal)
{
  UNITY_BRANCH switch (globalParams.morphDeltasDataFormat) {
    case OVR_FORMAT_FLOAT_32: {
      OvrApplyCompactMorphsNoTangentsCheckMorphIndexFormatDeltasF32(params, position, normal);
    } break;
    case OVR_FORMAT_SNORM_10_10_10_2: {
      OvrApplyCompactMorphsNoTangentsCheckMorphIndexFormatDeltasSnorm10(params, position, normal);
    } break;
    default:
      break;
  }
}

void OvrApplyCompactMorphsWithTangents(
    in OvrCompactMorphsParams params,
    in OvrCompactMorphsTangentParams tanParams,
    inout float4 position,
    inout float3 normal,
    inout float4 tangent)
{
  UNITY_BRANCH switch (globalParams.morphDeltasDataFormat) {
    case OVR_FORMAT_FLOAT_32: {
      OvrApplyCompactMorphsCheckMorphIndexFormatDeltasF32(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_SNORM_10_10_10_2: {
      OvrApplyCompactMorphsCheckMorphIndexFormatDeltasSnorm10(params, tanParams, position, normal, tangent);
    } break;
    default:
      break;
  }
}

#endif
