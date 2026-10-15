
#ifdef UNITY_PIPELINE_URP
    #pragma multi_compile_instancing
    #define USING_URP
#ifndef UNIVERSAL_PIPELINE_CORE_INCLUDED
    #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
    #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/UnityInstancing.hlsl"
#endif
    #include "../../../ShaderUtils/OvrUnityLightsURP.hlsl"
    #include "../../../ShaderUtils/OvrUnityGlobalIlluminationURP.hlsl"
#else // else use built in rendering
    #include "UnityCG.cginc"
    #include "UnityLightingCommon.cginc"
    #include "UnityStandardInput.cginc"
    #include "../../../ShaderUtils/OvrUnityGlobalIlluminationBuiltIn.hlsl"
#endif

#include "../../../ShaderUtils/AvatarCustom.cginc"

half4 getVertexInClipSpace(half3 pos) {
    #ifdef USING_URP
        return mul(UNITY_MATRIX_VP, mul(UNITY_MATRIX_M, half4 (pos,1.0)));
    #else
        return UnityObjectToClipPos(pos);
    #endif
}

struct avatar_AvatarVertexInput {
    half4 position;
    half3 normal;
    half3 tangent;
};

struct avatar_VertexOutput {
    half4 positionInClipSpace;
    half3 positionInWorldSpace;
    half3 normal;
    half3 tangent;
};

struct avatar_Transforms {
    half4x4 viewProjectionMatrix;
    half4x4 modelMatrix;
};

avatar_VertexOutput avatar_computeVertex(avatar_AvatarVertexInput i, avatar_Transforms transforms) {
    avatar_VertexOutput vout;
    half4 pos = mul(i.position, transforms.modelMatrix);
    half3 worldPos = half3(pos.xyz) / pos.w;
    vout.positionInClipSpace = mul(pos, transforms.viewProjectionMatrix);
    vout.positionInWorldSpace = worldPos;
    vout.normal = normalize(mul(i.normal, ((half3x3)(transforms.modelMatrix))));
    vout.tangent = normalize(mul(i.tangent, ((half3x3)(transforms.modelMatrix))));
    return vout;
}

uniform half4x4 u_ViewProjectionMatrix;
uniform half4x4 u_ModelMatrix;

static half4 a_Position;
static half4 a_Normal;
static half4 a_Tangent;
static uint a_vertexID;

 half4 _output_FragColor;
static half4 v_Vertex;
static float3 v_WorldPos;

#ifndef UNITY_INITIALIZE_OUTPUT
    #if defined(UNITY_COMPILER_HLSL) || defined(SHADER_API_PSSL) || defined(UNITY_COMPILER_HLSLCC)
        #define UNITY_INITIALIZE_OUTPUT(type,name) name = (type)0;
    #else
        #define UNITY_INITIALIZE_OUTPUT(type,name)
    #endif
#endif


struct AvatarVertexInput
{
    half4 a_Normal : NORMAL;
    half4 a_Position : POSITION;
    half4 a_Tangent : TANGENT;
    uint a_vertexID : SV_VertexID;
    UNITY_VERTEX_INPUT_INSTANCE_ID
};

struct VertexToFragment
{
    half4 v_Vertex : SV_POSITION;
    float3 v_WorldPos : TEXCOORD5;
    UNITY_VERTEX_OUTPUT_STEREO

};

void vert_Vertex_main() {
  OvrVertexData ovrData = OvrCreateVertexData(
    half4(a_Position.xyz, 1.0),
    a_Normal.xyz,
    a_Tangent,
    a_vertexID
  );
  avatar_AvatarVertexInput vin;
  vin.position = ovrData.position;
  vin.normal = ovrData.normal;
  vin.tangent = ovrData.tangent.xyz;
  avatar_Transforms transforms;
  transforms.viewProjectionMatrix = UNITY_MATRIX_VP;
  transforms.modelMatrix = unity_ObjectToWorld;
  half4 pos = vin.position;
  pos.xyz += 0.003 * vin.normal.xyz;

  half4 worldPos = mul(unity_ObjectToWorld, pos);
  v_WorldPos = worldPos.xyz / worldPos.w;

  v_Vertex = getVertexInClipSpace(pos.xyz/pos.w);



}

VertexToFragment Vertex_main_instancing(AvatarVertexInput stage_input)
{
    a_Position = stage_input.a_Position;
    a_Normal = stage_input.a_Normal;
    a_Tangent = stage_input.a_Tangent;
    a_vertexID = stage_input.a_vertexID;
    VertexToFragment stage_output;

    UNITY_SETUP_INSTANCE_ID(stage_input);
    UNITY_INITIALIZE_OUTPUT(VertexToFragment, stage_output);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(stage_output);
    vert_Vertex_main();
    stage_output.v_Vertex = v_Vertex;
    stage_output.v_WorldPos = v_WorldPos;
    return stage_output;
}

struct FragmentOutput
{
  half4 _output_FragColor : COLOR0;
};

void frag_Fragment_main () {
     _output_FragColor = half4(0.0, 0.0, 0.0, 1.0);
}

FragmentOutput Fragment_main(VertexToFragment stage_input)
{
  v_Vertex = stage_input.v_Vertex;
  v_WorldPos = stage_input.v_WorldPos;
  frag_Fragment_main();
  FragmentOutput stage_output;
  stage_output._output_FragColor = _output_FragColor;
  return stage_output;
}
