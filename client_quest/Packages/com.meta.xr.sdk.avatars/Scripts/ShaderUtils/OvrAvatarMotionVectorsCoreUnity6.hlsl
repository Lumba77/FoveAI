#ifndef OVR_AVATAR_MOTION_VECTORS_CORE_UNITY_6_INCLUDED
#define OVR_AVATAR_MOTION_VECTORS_CORE_UNITY_6_INCLUDED

#if UNITY_VERSION >= 60000000

#include "AvatarCustomTypes.cginc"
#include "OvrAvatarCommonVertexParams.hlsl"
#include "OvrAvatarMotionVectorsPosition.hlsl"

// This is essentially just a copy of "ObjectMotionVectors.hlsl"
// in the Oculus URP fork for Unity 6.0 with some avatar specific
// position loading code sprinkled in

// -------------------------------------
// Includes
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/UnityInput.hlsl"

#include "OvrAvatarMotionVectorsCommon.hlsl"


// -------------------------------------
// Structs
struct OvrMotionVectorsVertex
{
  OVR_VERTEX_POSITION_FIELD // Avatar specific code
  float3 positionOld          : TEXCOORD4; // Needs to be TEXCOORD4 to be auto populated by Unity
  OVR_VERTEX_VERT_ID_FIELD // Avatar specific code
  UNITY_VERTEX_INPUT_INSTANCE_ID
};

struct OvrMotionVectorsVaryings
{
  float4 positionCS                 : SV_POSITION;
  float4 positionCSNoJitter         : POSITION_CS_NO_JITTER;
  float4 previousPositionCSNoJitter : PREV_POSITION_CS_NO_JITTER;
  UNITY_VERTEX_INPUT_INSTANCE_ID
  UNITY_VERTEX_OUTPUT_STEREO
};


// This is a copy of the "meat" of the "MotionVectors" and "XRMotionVectors" vertex
// shader found in the Unity 6 URP fork for Application Spacewarp. Some code has been removed.
// Yes, it isn't great to have copies floating around, but we can't guarantee
// that adopters of the Meta Avatars SDK will necessarily have the
// Unity 6 URP fork for Application Spacewarp installed (yet)
OvrMotionVectorsVaryings OvrMotionVectorsVertProgram(OvrMotionVectorsVertex input)
{
  OvrMotionVectorsVaryings output = (OvrMotionVectorsVaryings)0;

  UNITY_SETUP_INSTANCE_ID(input);
  UNITY_TRANSFER_INSTANCE_ID(input, output);
  UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

  const uint vertexId = OVR_GET_VERTEX_VERT_ID_FIELD(input);
  float3 currentPos = OVR_GET_VERTEX_POSITION_FIELD(input).xyz;
  float3 prevPos = input.positionOld;

  prevPos = (unity_MotionVectorsParams.x == 1) ? prevPos : currentPos;
  OvrMotionVectorsGetPositions(vertexId, currentPos, prevPos);

  const VertexPositionInputs vertexInput = GetVertexPositionInputs(currentPos);

  output.positionCS = vertexInput.positionCS;
  output.positionCSNoJitter = mul(_NonJitteredViewProjMatrix, float4(vertexInput.positionWS, 1.0));
  output.previousPositionCSNoJitter = mul(_PrevViewProjMatrix, mul(UNITY_PREV_MATRIX_M, float4(prevPos, 1.0)));

#if !defined(APPLICATION_SPACE_WARP_MOTION)
  OvrAvatarApplyMotionVectorZBias(output.positionCS);
#endif

  return output;
}

float4 OvrMotionVectorsFragProgram(OvrMotionVectorsVaryings input) : SV_Target
{
  UNITY_SETUP_INSTANCE_ID(input);
  UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

#if SHADER_API_GLES || SHADER_API_GLES3
  // Clamp both current and previous positions to clip plane
  const float nearestZ = 0.2f;
  float currW = input.positionCSNoJitter.w;

  input.positionCSNoJitter.w = max(nearestZ, currW);
  input.previousPositionCSNoJitter.w = max(nearestZ, input.previousPositionCSNoJitter.w);
#endif


#if defined(APPLICATION_SPACE_WARP_MOTION)
  float4 color = float4(OvrAvatarCalcAswNdcMotionVectorFromCsPositions(input.positionCSNoJitter, input.previousPositionCSNoJitter), 1.0);
#else
  float4 color = float4(OvrAvatarCalcNdcMotionVectorFromCsPositions(input.positionCSNoJitter, input.previousPositionCSNoJitter), 0.0, 0.0);
#endif

#if SHADER_API_GLES || SHADER_API_GLES3
  // For GLES, the z channel contains the depth.
  color.z = nearestZ / currW;
#endif
  return color;
}

#endif // #if UNITY_VERSION >= 60000000

#endif // OVR_AVATAR_MOTION_VECTORS_CORE_UNITY_6_INCLUDED
