#ifndef OVR_AVATAR_MOTION_VECTORS_CORE_INCLUDED
#define OVR_AVATAR_MOTION_VECTORS_CORE_INCLUDED

#if UNITY_VERSION >= 60000000

#include "OvrAvatarMotionVectorsCoreUnity6.hlsl"

#else

#include "UnityCG.cginc"
#include "AvatarCustomTypes.cginc"
#include "OvrAvatarMotionVectorsPosition.hlsl"

float4x4 unity_MatrixPreviousM;

#if defined(UNITY_STEREO_INSTANCING_ENABLED) || defined(UNITY_STEREO_MULTIVIEW_ENABLED)
float4x4 unity_StereoMatrixPrevVP[2];
#define unity_MatrixPrevVP unity_StereoMatrixPrevVP[unity_StereoEyeIndex]
#else
float4x4 unity_MatrixPrevVP;
#endif

struct OvrMotionVectorsVertex
{
  OVR_VERTEX_POSITION_FIELD
  float3 previousPositionOS : TEXCOORD4; // Needs to be TEXCOORD4 to be auto populated by Unity
  OVR_VERTEX_VERT_ID_FIELD
  uint instanceID : SV_InstanceID;
  //UNITY_VERTEX_INPUT_INSTANCE_ID
};

struct OvrMotionVectorsVaryings
{
  float4 positionCS : SV_POSITION;
  float4 curPositionCS : TEXCOORD0;
  float4 prevPositionCS : TEXCOORD1;
  UNITY_VERTEX_OUTPUT_STEREO
};

OvrMotionVectorsVaryings OvrMotionVectorsVertProgram(OvrMotionVectorsVertex input)
{
  UNITY_SETUP_INSTANCE_ID(input);
  OvrMotionVectorsVaryings output;
  UNITY_INITIALIZE_OUTPUT(OvrMotionVectorsVaryings, output);
  UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

  // Pull from vertex buffer
  float3 currentPos = OVR_GET_VERTEX_POSITION_FIELD(input).xyz;
  float3 prevPos = input.previousPositionOS;
  const uint vertexId = OVR_GET_VERTEX_VERT_ID_FIELD(input);

  OvrMotionVectorsGetPositions(vertexId, currentPos, prevPos);

  output.positionCS = UnityObjectToClipPos(currentPos);
  output.curPositionCS = output.positionCS;
  float3 prevPosWorld = mul(unity_MatrixPreviousM, float4(prevPos, 1.0f)).xyz;
  output.prevPositionCS = mul(unity_MatrixPrevVP, float4(prevPosWorld, 1.0));

  return output;
}

half4 OvrMotionVectorsFragProgram(OvrMotionVectorsVaryings IN) : SV_Target
{
  float currW = IN.curPositionCS.w;
  float prevW = IN.prevPositionCS.w;

#if SHADER_API_GLES || SHADER_API_GLES3
  const float nearestZ = 0.2f;
  // Clamp both current and previous positions to clip plane
  currW = max(nearestZ, currW);
  prevW = max(nearestZ, prevW);
#endif

  float3 screenPos = IN.curPositionCS.xyz / currW;
  float3 screenPosPrev = IN.prevPositionCS.xyz / prevW;

  half4 color = half4(screenPos - screenPosPrev, 0.0f);
#if SHADER_API_GLES || SHADER_API_GLES3
  // For GLES, the z channel contains the depth.
  color.z = nearestZ / currW;
#endif
  return color;
}

#endif // #if UNITY_VERSION >= 60000000

#endif // OVR_AVATAR_MOTION_VECTORS_CORE_INCLUDED
