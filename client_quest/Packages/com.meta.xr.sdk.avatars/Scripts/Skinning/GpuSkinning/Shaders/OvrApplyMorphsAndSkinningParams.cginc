#ifndef OVR_APPLY_MORPHS_AND_SKINNING_PARAMS_INCLUDED
#define OVR_APPLY_MORPHS_AND_SKINNING_PARAMS_INCLUDED

#include <HLSLSupport.cginc>
#include "../../../ShaderUtils/OvrDecodeFormats.cginc"

////////////////////////////////////////////
/// Uniforms and Buffers
////////////////////////////////////////////

// TODO*: Layout diagram
ByteAddressBuffer _VertexBuffer; // "Bag of Bytes" (really bag of dwords)
ByteAddressBuffer _PerInstanceHeaderBuffer; // "Bag of Bytes" (really bag of dwords)
ByteAddressBuffer _MutableBuffer; // "Bag of Bytes" (really bag of dwords)
RWByteAddressBuffer _PositionOutputBuffer; // "Bag of Bytes" (really bag of dwords)
RWByteAddressBuffer _FrenetOutputBuffer; // "Bag of Bytes" (really bag of dwords)

int _MutableFrameStrideBytes;
int _VertexInfoOffsetBytes;
int _MeshInstanceMetaDataOffset;
int _DispatchMutableOffset;
int _DispatchStartVertIndex;
int _DispatchEndVertIndex;

// Using these below instead of #ifdefs to decrease variants (at the cost of
// a "static" branch each). There would be too large of
// an explosion of variants
int _VertexPositionsDataFormat;
int _VertexNormalsDataFormat;
int _VertexTangentsDataFormat;
int _JointIndicesDataFormat;
int _JointWeightsDataFormat;
int _PositionOutputBufferDataFormat;

int _VertexPositionsDataStride;
int _VertexNormalsDataStride;
int _VertexTangentsDataStride;
int _JointIndicesDataStride;
int _JointWeightsDataStride;
int _MorphDeltasDataStride;
int _PositionOutputBufferDataStride;

int _NumOutputEntriesPerVert;
int _MaxJointsPerVert;

int _MutableBufferFrameIndex;

int _ApplyAdditionalTransform;

// TODO*: Move output transform bigtangent factor and output transform
// to the "Per instance buffer" as they are per instance data
float _OutputTransformBitangentSignFactor = 1.0;
float4x4 _OutputTransform;

struct OvrApplyMorphsAndSkinningParams {
  /////////////////
  // Buffers
  /////////////////
  ByteAddressBuffer vertexBuffer; // "Bag of Bytes" (really bag of dwords)
  ByteAddressBuffer perInstanceHeaderBuffer; // "Bag of Bytes" (really bag of dwords)
  ByteAddressBuffer mutableBuffer; // "Bag of Bytes" (really bag of dwords)
  RWByteAddressBuffer positionOutputBuffer; // "Bag of Bytes" (really bag of dwords)
  RWByteAddressBuffer frenetOutputBuffer; // "Bag of Bytes" (really bag of dwords)

  /////////////////
  // Dispatch related bookkeeping
  /////////////////
  uint mutableFrameStrideBytes;
  uint meshInstanceMetaDataOffset;
  uint dispatchMutableOffset;
  uint dispatchStartVertIndex;
  uint dispatchEndVertIndex;
  uint vertexInfoOffsetBytes;

  /////////////////
  // Data formats and strides
  /////////////////
  int vertexPositionsDataFormat;
  uint vertexPositionsDataStride;
  int vertexNormalsDataFormat;
  uint vertexNormalsDataStride;
  int vertexTangentsDataFormat;
  uint vertexTangentsDataStride;

  int jointIndicesDataFormat;
  uint jointIndicesDataStride;
  int jointWeightsDataFormat;
  uint jointWeightsDataStride;

  int morphIndexDataFormat;
  uint morphIndexDataStride;
  int morphWeightsDataFormat;
  uint morphWeightsDataStride;
  int morphDeltasDataFormat;
  uint morphDeltasDataStride;
  int nextEntryIndexDataFormat;
  uint nextEntryIndexDataStride;

  int positionOutputDataFormat;
  uint positionOutputDataStride;
  int frenetOutputDataFormat;
  uint frenetOutputDataStride;

  /////////////////
  // "Feature Flags"
  /////////////////
  bool applyAdditionalTransform;
  bool applyTangents;

  uint numOutputSlicesPerAttribute;
  uint maxJointsPerVert;

  /////////////////
  // Misc.
  /////////////////
  uint mutableBufferFrameIndex;

  float outputTransformBitangentSignFactor;
  float4x4 outputTransform;
};

int OvrGetMorphWeightsFormat() {
  return OVR_FORMAT_FLOAT_32;
}

uint OvrGetMorphWeightsStride() {
  // TODO*: Have strides passed in from CPU
  // instead of hardcoding here
  UNITY_BRANCH switch (OvrGetMorphWeightsFormat()) {
    case OVR_FORMAT_FLOAT_32:
      return 4u;
    default:
      // Unhandled, error
      return 0u;
  }
}

int OvrGetMorphDeltasFormat() {
  #if defined(OVR_MORPH_DELTA_FORMAT_SNORM10)
    return OVR_FORMAT_SNORM_10_10_10_2;
  #else
    return OVR_FORMAT_FLOAT_32;
  #endif
}

uint OvrGetMorphDeltasStride() {
  return _MorphDeltasDataStride;
}

int OvrGetMorphIndexFormat() {
  #if defined(OVR_MORPH_INDEX_FORMAT_UINT16)
    return OVR_FORMAT_UINT_16;
  #else
    return OVR_FORMAT_UINT_8;
  #endif
}

uint OvrGetMorphIndexStride() {
  // TODO*: Have strides passed in from CPU
  // instead of hardcoding here
  UNITY_BRANCH switch (OvrGetMorphIndexFormat()) {
    case OVR_FORMAT_UINT_16:
      return 2u;
    case OVR_FORMAT_UINT_8:
      return 1u;
    default:
      // Unhandled, error
      return 0u;
  }
}

int OvrGetNextEntryFormat() {
  #if defined(OVR_NEXT_ENTRY_FORMAT_UINT16)
    return OVR_FORMAT_UINT_16;
#elif defined(OVR_NEXT_ENTRY_FORMAT_UINT32)
    return OVR_FORMAT_UINT_32;
#else
    return OVR_FORMAT_UINT_8;
#endif

}

uint OvrGetNextEntryStride() {
  // TODO*: Have strides passed in from CPU
  // instead of hardcoding here
  UNITY_BRANCH switch (OvrGetNextEntryFormat()) {
    case OVR_FORMAT_UINT_32:
      return 4u;
    case OVR_FORMAT_UINT_16:
      return 2u;
    case OVR_FORMAT_UINT_8:
      return 1u;
    default:
      // Unhandled, error
      return 0u;
  }
}

uint OvrGetMaxJointsPerVert() {
  static const uint kMaxSupportedJointsPerVert = 4u;

  return min(_MaxJointsPerVert, kMaxSupportedJointsPerVert);
}

bool OvrGetApplyTangents() {
  #if defined(OVR_HAS_TANGENTS)
    return true;
  #else
    return false;
  #endif
}

uint OvrGetNumOutputSlicesPerAttribute() {
  return _NumOutputEntriesPerVert;
}

int OvrGetFrenetOutputFormat() {
  return OVR_FORMAT_SNORM_10_10_10_2;
}

uint OvrGetFrenetOutputStride() {
  // TODO*: Have strides passed in from CPU
  // instead of hardcoding here
  UNITY_BRANCH switch (OvrGetFrenetOutputFormat()) {
    case OVR_FORMAT_SNORM_10_10_10_2:
      return 4u;
    default:
      // Unhandled, error
      return 0u;
  }
}

int OvrGetVertexPositionDataFormat() {
  return _VertexPositionsDataFormat;
}

uint OvrGetVertexPositionDataStride() {
  return _VertexPositionsDataStride;
}

int OvrGetVertexNormalDataFormat() {
  return _VertexNormalsDataFormat;
}

uint OvrGetVertexNormalDataStride() {
  return _VertexNormalsDataStride;
}

int OvrGetVertexTangentDataFormat() {
  return _VertexTangentsDataFormat;
}

uint OvrGetVertexTangentDataStride() {
 return _VertexNormalsDataStride;
}

OvrApplyMorphsAndSkinningParams CreateComputeShaderParams() {
  OvrApplyMorphsAndSkinningParams result;

  result.vertexBuffer = _VertexBuffer;
  result.perInstanceHeaderBuffer = _PerInstanceHeaderBuffer;
  result.mutableBuffer = _MutableBuffer;
  result.positionOutputBuffer = _PositionOutputBuffer;
  result.frenetOutputBuffer = _FrenetOutputBuffer;

  result.mutableFrameStrideBytes = _MutableFrameStrideBytes;
  result.meshInstanceMetaDataOffset = _MeshInstanceMetaDataOffset;
  result.dispatchMutableOffset =  _DispatchMutableOffset;
  result.dispatchStartVertIndex = _DispatchStartVertIndex;
  result.dispatchEndVertIndex = _DispatchEndVertIndex;
  result.vertexInfoOffsetBytes = _VertexInfoOffsetBytes;

  result.vertexPositionsDataFormat = OvrGetVertexPositionDataFormat();
  result.vertexPositionsDataStride = OvrGetVertexPositionDataStride();
  result.vertexNormalsDataFormat = OvrGetVertexNormalDataFormat();
  result.vertexNormalsDataStride = OvrGetVertexNormalDataStride();
  result.vertexTangentsDataFormat = OvrGetVertexTangentDataFormat();
  result.vertexTangentsDataStride = OvrGetVertexTangentDataStride();

  result.jointIndicesDataFormat = _JointIndicesDataFormat;
  result.jointIndicesDataStride = _JointIndicesDataStride;

  result.jointWeightsDataFormat = _JointWeightsDataFormat;
  result.jointWeightsDataStride = _JointWeightsDataStride;

  result.morphIndexDataFormat = OvrGetMorphIndexFormat();
  result.morphIndexDataStride = OvrGetMorphIndexStride();

  result.morphWeightsDataFormat = OvrGetMorphWeightsFormat();
  result.morphWeightsDataStride = OvrGetMorphWeightsStride();

  result.morphDeltasDataFormat = OvrGetMorphDeltasFormat();
  result.morphDeltasDataStride = OvrGetMorphDeltasStride();

  result.nextEntryIndexDataFormat = OvrGetNextEntryFormat();
  result.nextEntryIndexDataStride = OvrGetNextEntryStride();

  result.positionOutputDataFormat = _PositionOutputBufferDataFormat;
  result.positionOutputDataStride = _PositionOutputBufferDataStride;

  result.frenetOutputDataFormat = OvrGetFrenetOutputFormat();
  result.frenetOutputDataStride = OvrGetFrenetOutputStride();

  result.applyAdditionalTransform = _ApplyAdditionalTransform > 0;
  result.applyTangents = OvrGetApplyTangents();
  result.numOutputSlicesPerAttribute = OvrGetNumOutputSlicesPerAttribute();
  result.maxJointsPerVert = OvrGetMaxJointsPerVert();
  result.mutableBufferFrameIndex = _MutableBufferFrameIndex;

  result.outputTransformBitangentSignFactor = _OutputTransformBitangentSignFactor;
  result.outputTransform = _OutputTransform;

  return result;
}

static const OvrApplyMorphsAndSkinningParams globalParams = CreateComputeShaderParams();

#endif // OVR_APPLY_MORPHS_AND_SKINNING_PARAMS_INCLUDED
