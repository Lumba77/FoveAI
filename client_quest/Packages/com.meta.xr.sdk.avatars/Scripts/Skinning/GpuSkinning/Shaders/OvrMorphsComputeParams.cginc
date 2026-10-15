#ifndef OVR_MORPHS_COMPUTE_PARAMS_INCLUDED
#define OVR_MORPHS_COMPUTE_PARAMS_INCLUDED

#include "../../../ShaderUtils/OvrDecodeUtils.cginc"
#include "../../../ShaderUtils/OvrDecodeFormats.cginc"
#include "OvrApplyMorphsAndSkinningParams.cginc"

groupshared uint _groupMaxNumMorphs = 0u;

struct OvrCompactMorphsParams {
  uint posDeltasStartAddress;
  uint normDeltasStartAddress;
  uint morphIndicesStartAddress;
  uint nextEntriesStartAddress;
  uint morphTargetWeightsStartAddress;
  uint vertIndex;

  float3 posScale;
  float3 normScale;
};

struct OvrCompactMorphsTangentParams {
  uint tanDeltasStartAddress;

  float3 tanScale;
};

struct OvrCompactMorphsVars {
  float3 posSum;
  float3 normSum;

  uint entryIndex;
};

struct OvrCompactMorphsTangentVars {
  float3 tanSum;
};

uint OvrGetNumMorphTargetsAffectingVertex(
  in uint numMorphsBufferStartAddress,
  in uint vertexIndex)
{
  uint byteOffset = numMorphsBufferStartAddress;
  byteOffset += globalParams.morphIndexDataStride * vertexIndex;

  // Any if statements done on static constant data (not from uniforms)
  // should be free and branching on a uniform shouldn't be that bad
  UNITY_BRANCH switch (globalParams.morphIndexDataFormat) {
    case OVR_FORMAT_UINT_16:
      return OvrUnpackUint1x16NonAligned(globalParams.vertexBuffer, byteOffset);
    case OVR_FORMAT_UINT_8:
      return OvrUnpackUint1x8NonAligned(globalParams.vertexBuffer, byteOffset);
    default:
      // Error?
      return 0;
  }
}

void OvrLoadMaxNumMorphsForGroup(in uint numMorphsForThisVert)
{
  // Compare with the maximum for the group
  GroupMemoryBarrierWithGroupSync();
  InterlockedMax(_groupMaxNumMorphs, numMorphsForThisVert);
  GroupMemoryBarrierWithGroupSync();
}

void OvrApplyAndScaleAccumulatedPositionAndNormal(
    inout float4 position,
    inout float3 normal,
    in OvrCompactMorphsParams params,
    in OvrCompactMorphsVars vars)
{
  position.xyz += params.posScale * vars.posSum;
  normal += params.normScale * vars.normSum;
  normal = normalize(normal);
}

void OvrApplyAndScaleAccumulatedTangent(
    inout float4 tangent,
    in OvrCompactMorphsTangentParams params,
    in OvrCompactMorphsTangentVars vars) {
  tangent.xyz += params.tanScale * vars.tanSum;
  tangent.xyz = normalize(tangent.xyz);
}

float OvrCompactMorphsGetMorphWeight(
    uint morphTargetIndex,
    in OvrCompactMorphsParams params) {
  const uint byteOffset =
    globalParams.morphWeightsDataStride * morphTargetIndex +
    params.morphTargetWeightsStartAddress;

  return OvrUnpackFloat1x32(globalParams.mutableBuffer, byteOffset);
}

OvrCompactMorphsVars GetInitialVars(OvrCompactMorphsParams params) {
  OvrCompactMorphsVars result;

  result.posSum = 0.0;
  result.normSum = 0.0;
  result.entryIndex = params.vertIndex;

  return result;
}

OvrCompactMorphsTangentVars GetInitialVars() {
  OvrCompactMorphsTangentVars result;

  result.tanSum = 0.0;

  return result;
}

// Using some other tools to generate functions instead of using macros for code generation

// <BEGIN CODE GENERATION>

///////////////////////////////////////////////////////////////////////////////////////////////
// Position Delta Functions
///////////////////////////////////////////////////////////////////////////////////////////////
float3 OvrCompactMorphsUnpackPositionDeltaF32(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.morphDeltasDataStride * vars.entryIndex + params.posDeltasStartAddress;

  return OvrUnpackFloat3x32(globalParams.vertexBuffer, byteOffset);
}

float3 OvrCompactMorphsUnpackPositionDeltaSnorm10(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.morphDeltasDataStride * vars.entryIndex + params.posDeltasStartAddress;

  return OvrUnpackSnorm3x10_10_10_2WithBonusScale(globalParams.vertexBuffer, byteOffset);
}

///////////////////////////////////////////////////////////////////////////////////////////////
// Normal Delta Functions
///////////////////////////////////////////////////////////////////////////////////////////////
float3 OvrCompactMorphsUnpackNormalDeltaF32(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.morphDeltasDataStride * vars.entryIndex + params.normDeltasStartAddress;

  return OvrUnpackFloat3x32(globalParams.vertexBuffer, byteOffset);
}

float3 OvrCompactMorphsUnpackNormalDeltaSnorm10(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.morphDeltasDataStride * vars.entryIndex + params.normDeltasStartAddress;

  return OvrUnpackSnorm3x10_10_10_2WithBonusScale(globalParams.vertexBuffer, byteOffset);
}

///////////////////////////////////////////////////////////////////////////////////////////////
// Tangent Delta Functions
///////////////////////////////////////////////////////////////////////////////////////////////

float3 OvrCompactMorphsUnpackTangentDeltaF32(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsTangentParams tanParams)
{
  const uint byteOffset = globalParams.morphDeltasDataStride * vars.entryIndex + tanParams.tanDeltasStartAddress;

  return OvrUnpackFloat3x32(globalParams.vertexBuffer, byteOffset);
}

float3 OvrCompactMorphsUnpackTangentDeltaSnorm10(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsTangentParams tanParams)
{
  const uint byteOffset = globalParams.morphDeltasDataStride * vars.entryIndex + tanParams.tanDeltasStartAddress;

  return OvrUnpackSnorm3x10_10_10_2WithBonusScale(globalParams.vertexBuffer, byteOffset);
}

///////////////////////////////////////////////////////////////////////////////////////////////
// Morph Index Functions
///////////////////////////////////////////////////////////////////////////////////////////////
uint OvrCompactMorphsGetMorphIndexUint16(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.morphIndexDataStride * vars.entryIndex + params.morphIndicesStartAddress;

  return OvrUnpackUint1x16NonAligned(globalParams.vertexBuffer, byteOffset);
}

uint OvrCompactMorphsGetMorphIndexUint8(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.morphIndexDataStride * vars.entryIndex + params.morphIndicesStartAddress;

  return OvrUnpackUint1x8NonAligned(globalParams.vertexBuffer, byteOffset);
}

///////////////////////////////////////////////////////////////////////////////////////////////
// Next Entry Index Functions
///////////////////////////////////////////////////////////////////////////////////////////////

uint OvrCompactMorphsGetNextEntryIndexUint32(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.nextEntryIndexDataStride * vars.entryIndex + params.nextEntriesStartAddress;

  return OvrLoadUint(globalParams.vertexBuffer, byteOffset);
}

uint OvrCompactMorphsGetNextEntryIndexUint16(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.nextEntryIndexDataStride * vars.entryIndex + params.nextEntriesStartAddress;

  return OvrUnpackUint1x16NonAligned(globalParams.vertexBuffer, byteOffset);
}

uint OvrCompactMorphsGetNextEntryIndexUint8(
  in OvrCompactMorphsVars vars,
  in OvrCompactMorphsParams params)
{
  const uint byteOffset = globalParams.nextEntryIndexDataStride * vars.entryIndex + params.nextEntriesStartAddress;

  return OvrUnpackUint1x8NonAligned(globalParams.vertexBuffer, byteOffset);
}

///////////////////////////////////////////////////////////////////////////////////////////////
// No Tangent Apply Morphs Functions
///////////////////////////////////////////////////////////////////////////////////////////////

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint16NextEntriesUint32(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint16NextEntriesUint16(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint16NextEntriesUint8(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint8NextEntriesUint32(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint8NextEntriesUint16(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint8NextEntriesUint8(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint16NextEntriesUint32(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint16NextEntriesUint16(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint16NextEntriesUint8(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint8NextEntriesUint32(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars    , params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint8NextEntriesUint16(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint8NextEntriesUint8(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);

    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);

    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }

  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
}

///////////////////////////////////////////////////////////////////////////////////////////////
// No Tangent Check Next Entry Format Functions
///////////////////////////////////////////////////////////////////////////////////////////////

// Expansion for DeltaSuffix = F32, MorphIndexSuffix = Uint16
void OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasF32MorphIndicesUint16(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint16NextEntriesUint32(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint16NextEntriesUint16(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint16NextEntriesUint8(params, position, normal);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = F32, MorphIndexSuffix = Uint8
void OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasF32MorphIndicesUint8(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint8NextEntriesUint32(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint8NextEntriesUint16(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsNoTangentsDeltasF32MorphIndicesUint8NextEntriesUint8(params, position, normal);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = Snorm10, MorphIndexSuffix = Uint16
void OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint16(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint16NextEntriesUint32(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint16NextEntriesUint16(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint16NextEntriesUint8(params, position, normal);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = Snorm10, MorphIndexSuffix = Uint8
void OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint8(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint8NextEntriesUint32(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint8NextEntriesUint16(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsNoTangentsDeltasSnorm10MorphIndicesUint8NextEntriesUint8(params, position, normal);
    } break;
    default:
      break;
  }
}

///////////////////////////////////////////////////////////////////////////////////////////////
// No Tangent Check Morph Index Format Functions
///////////////////////////////////////////////////////////////////////////////////////////////

// Expansion for DeltaSuffix = F32
void OvrApplyCompactMorphsNoTangentsCheckMorphIndexFormatDeltasF32(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  UNITY_BRANCH switch (globalParams.morphIndexDataFormat) {
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasF32MorphIndicesUint16(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasF32MorphIndicesUint8(params, position, normal);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = Snorm10, MorphIndexSuffix = Uint8
void OvrApplyCompactMorphsNoTangentsCheckMorphIndexFormatDeltasSnorm10(
  in OvrCompactMorphsParams params,
  inout float4 position,
  inout float3 normal)
{
  UNITY_BRANCH switch (globalParams.morphIndexDataFormat) {
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint16(params, position, normal);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsNoTangentsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint8(params, position, normal);
    } break;
    default:
      break;
  }
}

///////////////////////////////////////////////////////////////////////////////////////////////
// Apply Morphs Functions
///////////////////////////////////////////////////////////////////////////////////////////////

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsDeltasF32MorphIndicesUint16NextEntriesUint32(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaF32(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsDeltasF32MorphIndicesUint16NextEntriesUint16(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaF32(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsDeltasF32MorphIndicesUint16NextEntriesUint8(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaF32(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsDeltasF32MorphIndicesUint8NextEntriesUint32(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaF32(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsDeltasF32MorphIndicesUint8NextEntriesUint16(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaF32(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=F32, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsDeltasF32MorphIndicesUint8NextEntriesUint8(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaF32(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaF32(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaF32(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint16NextEntriesUint32(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaSnorm10(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint16NextEntriesUint16(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaSnorm10(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint16, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint16NextEntriesUint8(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint16(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaSnorm10(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint32
void OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint8NextEntriesUint32(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaSnorm10(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint32(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint16
void OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint8NextEntriesUint16(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaSnorm10(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint16(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

// Expansion for DeltaSuffix=Snorm10, MorphIndexSuffix=Uint8, NextEntrySuffix=Uint8
void OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint8NextEntriesUint8(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  OvrCompactMorphsVars vars = GetInitialVars(params);
  OvrCompactMorphsTangentVars tanVars = GetInitialVars();
  for (uint index = 0; index < _groupMaxNumMorphs; ++index) {
    const uint morphIndex = OvrCompactMorphsGetMorphIndexUint8(vars, params);
    const float weight = OvrCompactMorphsGetMorphWeight(morphIndex, params);
    const float3 posDelta = OvrCompactMorphsUnpackPositionDeltaSnorm10(vars, params);
    const float3 normDelta = OvrCompactMorphsUnpackNormalDeltaSnorm10(vars, params);
    const float3 tanDelta = OvrCompactMorphsUnpackTangentDeltaSnorm10(vars, tanParams);
    vars.posSum += weight * posDelta;
    vars.normSum += weight * normDelta;
    tanVars.tanSum += weight * tanDelta;
    vars.entryIndex = OvrCompactMorphsGetNextEntryIndexUint8(vars, params);
  }
  OvrApplyAndScaleAccumulatedPositionAndNormal(position, normal, params, vars);
  OvrApplyAndScaleAccumulatedTangent(tangent, tanParams, tanVars);
}

///////////////////////////////////////////////////////////////////////////////////////////////
// Check Next Entry Format Functions
///////////////////////////////////////////////////////////////////////////////////////////////

// Expansion for DeltaSuffix = F32, MorphIndexSuffix = Uint16
void OvrApplyCompactMorphsCheckNextEntryFormatDeltasF32MorphIndicesUint16(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsDeltasF32MorphIndicesUint16NextEntriesUint32(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsDeltasF32MorphIndicesUint16NextEntriesUint16(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsDeltasF32MorphIndicesUint16NextEntriesUint8(params, tanParams, position, normal, tangent);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = F32, MorphIndexSuffix = Uint8
void OvrApplyCompactMorphsCheckNextEntryFormatDeltasF32MorphIndicesUint8(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsDeltasF32MorphIndicesUint8NextEntriesUint32(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsDeltasF32MorphIndicesUint8NextEntriesUint16(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsDeltasF32MorphIndicesUint8NextEntriesUint8(params, tanParams, position, normal, tangent);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = Snorm10, MorphIndexSuffix = Uint16
void OvrApplyCompactMorphsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint16(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint16NextEntriesUint32(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint16NextEntriesUint16(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint16NextEntriesUint8(params, tanParams, position, normal, tangent);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = Snorm10, MorphIndexSuffix = Uint8
void OvrApplyCompactMorphsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint8(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  UNITY_BRANCH switch (globalParams.nextEntryIndexDataFormat) {
    case OVR_FORMAT_UINT_32: {
      OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint8NextEntriesUint32(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint8NextEntriesUint16(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsDeltasSnorm10MorphIndicesUint8NextEntriesUint8(params, tanParams, position, normal, tangent);
    } break;
    default:
      break;
  }
}

///////////////////////////////////////////////////////////////////////////////////////////////
// Check Morph Index Format Functions
///////////////////////////////////////////////////////////////////////////////////////////////

// Expansion for DeltaSuffix = F32
void OvrApplyCompactMorphsCheckMorphIndexFormatDeltasF32(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  UNITY_BRANCH switch (globalParams.morphIndexDataFormat) {
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsCheckNextEntryFormatDeltasF32MorphIndicesUint16(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsCheckNextEntryFormatDeltasF32MorphIndicesUint8(params, tanParams, position, normal, tangent);
    } break;
    default:
      break;
  }
}

// Expansion for DeltaSuffix = Snorm10, MorphIndexSuffix = Uint8
void OvrApplyCompactMorphsCheckMorphIndexFormatDeltasSnorm10(
  in OvrCompactMorphsParams params,
  in OvrCompactMorphsTangentParams tanParams,
  inout float4 position,
  inout float3 normal,
  inout float4 tangent)
{
  UNITY_BRANCH switch (globalParams.morphIndexDataFormat) {
    case OVR_FORMAT_UINT_16: {
      OvrApplyCompactMorphsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint16(params, tanParams, position, normal, tangent);
    } break;
    case OVR_FORMAT_UINT_8: {
      OvrApplyCompactMorphsCheckNextEntryFormatDeltasSnorm10MorphIndicesUint8(params, tanParams, position, normal, tangent);
    } break;
    default:
      break;
  }
}

// <END CODE GENERATION>

#endif
