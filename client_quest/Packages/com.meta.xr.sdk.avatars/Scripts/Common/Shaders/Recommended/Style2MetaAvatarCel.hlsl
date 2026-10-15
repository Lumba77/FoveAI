// @generated
// @codegen-command : fbpython arvr/libraries/avatar/Integration/Tools/generate_esf_shaders.py
// ESF generates shaders for different platforms using source shaders from fbsource/arvr/libraries/avatar/Tools/esf.
// To learn more about how to make shader changes with ESF, read the wiki: https://www.internalfb.com/wiki/RL/Avatars/Avatar_SDK/Teams/Perf_+_Visuals/Avatar_Rendering/Extensible_Shader_Framework_(ESF)_Preprocessor/
// Builtin macros by shpp
#define GLSL_LANG 1
#define HLSL_LANG 2
#define SPARKSL_LANG 3
#define GLES_LANG 4
#define VAR_ID_NOTX -2
#define VAR_ID_CUR 0
#define VAR_ID VAR_ID_CUR
#define APFX_VAR
#define __SL_LANG__ HLSL_LANG
#define HOST_CONFIG UNITY_CONFIG_GENERIC
#ifdef UNITY_PIPELINE_URP

    #pragma multi_compile_instancing

    // Per vertex is faster than per pixel, and almost indistinguishable for our purpose
    #define USE_SH_PER_VERTEX

    // This is the URP pass so set this define to activate OvrUnityGlobalIllumination headers
    #define USING_URP

    // URP includes
    // Some apps like to include their own versions of Core.hlsl and UnityInstancing.hlsl before this.
#ifndef UNIVERSAL_PIPELINE_CORE_INCLUDED
    #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
    #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/UnityInstancing.hlsl"
#endif
    #include "../../../ShaderUtils/OvrUnityLightsURP.hlsl"
    #include "../../../ShaderUtils/OvrUnityGlobalIlluminationURP.hlsl"

#else

    // Per vertex is faster than per pixel, and almost indistinguishable for our purpose
    #define LIGHTPROBE_SH 1

    // Built-in rendering includes
    #include "UnityCG.cginc"
    #include "UnityLightingCommon.cginc"
    #include "UnityStandardInput.cginc"
    #include "../../../ShaderUtils/OvrUnityGlobalIlluminationBuiltIn.hlsl"

#endif

// VERTEX COLORS: activate this to transmit lo-fi model vert colors or sub mesh information in the alpha channel
#define HAS_VERTEX_COLOR_half4

// Include app-specific dependencies
// App specific declarations that have to happen before the exported Library shader
// If your app needs its own declarations, rename this file with your app's name and place them here.
// This file should persist across succesive integrations.

// Keyword Definitions

// Scoped Variables (Uniforms)

#include "../../../ShaderUtils/AvatarCustom.cginc"

#ifdef SKIN_ON
#ifndef DEC_bool_enableSkin
 #define DEC_bool_enableSkin
 static const bool enableSkin = true;
 #endif
#else
#ifndef DEC_bool_enableSkin
 #define DEC_bool_enableSkin
 static const bool enableSkin = false;
 #endif
#endif

#ifdef EYE_GLINTS_ON
#ifndef DEC_bool_enableEyeGlint
 #define DEC_bool_enableEyeGlint
 static const bool enableEyeGlint = true;
 #endif
#else
#ifndef DEC_bool_enableEyeGlint
 #define DEC_bool_enableEyeGlint
 static const bool enableEyeGlint = false;
 #endif
#endif

half4 getVertexInClipSpace(half3 pos) {
    #ifdef USING_URP
        return mul(UNITY_MATRIX_VP, mul(UNITY_MATRIX_M, half4 (pos,1.0)));
    #else
        return UnityObjectToClipPos(pos);
    #endif
}

#ifdef USING_URP
struct VertexInput {
    half2 uv0;
    half2 uv1;
};

half4 VertexGIForward(VertexInput v, half3 posWorld, half3 normalWorld){
      return half4(SampleSHVertex(normalWorld), 1.0);
}
#endif

// Maximum Number of lights for this host target.
#ifndef MAX_LIGHT_COUNT
  // Majority of VR apps use one light source. For more, define this in your version of app_variants.hlsl.
  #define MAX_LIGHT_COUNT 1
#endif
// avatar_struct_utils.vert.glsl

struct avatar_AvatarVertexInput {
    half4 position;
    half3 normal;
    half3 tangent;
    half2 texcoord0;
    half2 texcoord1;
    half2 texcoord2;
    half4 color;
    half4 ormt;
    half3 ambient;
};

struct avatar_VertexOutput {
    half4 positionInClipSpace;
    half3 positionInWorldSpace;
    half3 normal;
    half3 tangent;
    half2 texcoord0;
    half2 texcoord1;
    half2 texcoord2;
    half4 color;
};

struct avatar_Transforms {
    half4x4 viewProjectionMatrix;
    half4x4 modelMatrix;
};
// eof avatar_struct_utils.vert.glsl
// Start of include: avatar_struct_utils.frag.glsl

 struct avatar_Light {
    half3 direction_normalized;
    half3 color;
    half intensity;

    // sine of the angle from the light's center axis to the outside of the cone
    half areaLightAngleSin;
    half3 directional_light_color;
};

 struct avatar_HairMaterial {
    half3 subsurface_color;
    half3 specular_color_factor;
    half specular_shift_intensity;
    half specular_white_intensity;
    half specular_white_roughness;
    half specular_color_intensity;
    half specular_color_offset;
    half specular_color_roughness;
    half anisotropic_intensity;
    half normal_intensity;
    half ao_intensity;
    half flow_sample;
    half flow_angle;
    half shift;
    half blend;
    half aniso_blend;
};

 struct avatar_Material {
    half3 base_color;
    half alpha;
    half alpha_coverage;
    half metallic;

    half properties_occlusion;
    half screenspace_occlusion;
    half combined_occlusion;
    half roughness;
    half thickness;
    half3 IBLBrdf;
    half3 f0;
    half f90;
    half exposure;
    half intensity;

#ifdef BLOCK_MATERIAL_SYSTEM
    int submesh_index;
#endif

};

 struct avatar_Geometry {

    half3 positionInClipSpace;

    half3 positionInWorldSpace;
    half3 normal;
    half3 unperturbedNormal;
    half3 tangent;
    half3 bitangent;
    half2 texcoord_0;

    half4 color;
    half4 ormt;

    half3 worldViewDir;
    half curvature;
};

 struct avatar_AmbientLighting {
    half3 diffuse;
    half3 specular;
};

 struct avatar_FragmentInput {

    avatar_Geometry geometry;
    avatar_Material material;
    int lightsCount;
    avatar_Light lights[MAX_LIGHT_COUNT];
    half3 ambient_color;
    half3 SHCoeff0;
    half3 SHCoeff1;
    half3 SHCoeff2;
    half3 SHCoeff3;
    half3 SHCoeff4;
    half3 SHCoeff5;
    half3 SHCoeff6;
    half3 SHCoeff7;
    half3 SHCoeff8;
};

 struct avatar_FragmentOutput {
    half4 color;

    uint alphaCoverage;

};

// End of include: avatar_struct_utils.frag.glsl
// submesh_utils.frag.glsl

// NOTE: these are only enumerated here for backwards compatibility with the
//       style 1 sub-mesh inclusion system.
static const half avatar_SUBMESH_TYPE_NONE      = 0.0    / 256.0;
static const half avatar_SUBMESH_TYPE_OUTFIT    = 1.0    / 256.0;
static const half avatar_SUBMESH_TYPE_BODY      = 2.0    / 256.0;
static const half avatar_SUBMESH_TYPE_HEAD      = 4.0    / 256.0;
static const half avatar_SUBMESH_TYPE_HAIR      = 8.0    / 256.0;
static const half avatar_SUBMESH_TYPE_EYEBROW   = 16.0   / 256.0;
static const half avatar_SUBMESH_TYPE_L_EYE     = 32.0   / 256.0;
static const half avatar_SUBMESH_TYPE_R_EYE     = 64.0   / 256.0;
static const half avatar_SUBMESH_TYPE_LASHES    = 128.0  / 256.0;
static const half avatar_SUBMESH_TYPE_FACIALHAIR= 256.0  / 256.0;
static const half avatar_SUBMESH_TYPE_HEADWEAR  = 512.0  / 256.0;
static const half avatar_SUBMESH_TYPE_EARRINGS  = 1024.0 / 256.0;

static const half avatar_SUBMESH_TYPE_BUFFER= (0.5 / 256.0);

bool avatar_WithinSubmeshRange(half idChannel, half lowBound, half highBound) {
    bool condition = ((idChannel > (lowBound - avatar_SUBMESH_TYPE_BUFFER)) &&
                        (idChannel < (highBound + avatar_SUBMESH_TYPE_BUFFER)));
    return condition;
}

bool avatar_IsSubmeshType(half idChannel, half subMeshType) {
    return avatar_WithinSubmeshRange(idChannel, subMeshType, subMeshType);
}

int _DebugColorsCount = 19;
float4 _DebugColors[19];
float _DebugColorsFloat[19 * 4];

float4 avatar_GetVectorFromFloatArray(int index) {
  int offset = index * 4;

#ifdef BLOCK_MATERIAL_SYSTEM
  float4 returnVal = float4(

    _DebugColorsFloat[offset + 0],
    _DebugColorsFloat[offset + 1],
    _DebugColorsFloat[offset + 2],
    _DebugColorsFloat[offset + 3]);

#else
  float mono = float(index % 16) * 16.0 / 256.0;
  float4 returnVal = float4(mono,mono,mono,1.0);
#endif
   return returnVal;
}

#ifdef DEBUG_MODE_ON

half3 SubMeshIdToColor(half subMeshId)
{
    half3 returnColor = half3(0.0, 0.0, 0.0);

    int iId = int(subMeshId * 255.0 + avatar_SUBMESH_TYPE_BUFFER);
    iId = iId % _DebugColorsCount;
    returnColor = half3(avatar_GetVectorFromFloatArray(iId).rgb);

    return returnColor;
}

#endif

// eof submesh_utils.frag.glsl
// material_type_utils.frag.glsl

#ifdef BLOCK_MATERIAL_SYSTEM
static const half avatar_MATERIAL_OFFSET_INVALID   = -1.0;

// Flexible Material System hashing algorithm.
// This is a base 3 mod 32768 simple algorithm as shown below
// To generate your own hashes for debugging, please see:
// https://docs.google.com/spreadsheets/d/1-yQV4YhIRRVn_H1Q6qU4ya3jGvf44ISzv3vuyyTqHOA/edit?usp=sharing
// This algorithm matches an algorithm implemented in the Avatar SDK.
// It is used to fill the material ID floating point buffer.
// We use this hash to contain existing techniques as well as add
// new techniques in the future, by changing ONLY the shader and SDK.
// Along the way the neither the SDK nor integrations should hard-code
// any enumerations for these identifiers, in a data-driven effort.

#define MATERIAL_HASH_BASE 3
#define MATERIAL_HASH_MOD 32768
#define MATERIAL_HASH_LETTER(X,Y) ( MATERIAL_HASH_BASE * (X) + (Y))
#define H(X,Y) MATERIAL_HASH_LETTER(X,Y)

#define MATERIAL_HASH_1(a) (a)
#define MATERIAL_HASH_2(a,b) (H(a,b) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_3(a,b,c) (H(H(a,b),c) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_4(a,b,c,d) (H(H(H(a,b),c),d) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_5(a,b,c,d,e) (H(H(H(H(a,b),c),d),e) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_6(a,b,c,d,e,f) (H(H(H(H(H(a,b),c),d),e),f) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_7(a,b,c,d,e,f,g) (H(H(H(H(H(H(a,b),c),d),e),f),g) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_8(a,b,c,d,e,f,g,h) (H(H(H(H(H(H(H(a,b),c),d),e),f),g),h) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_9(a,b,c,d,e,f,g,h,i) (H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_10(a,b,c,d,e,f,g,h,i,j) (H(H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i),j) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_11(a,b,c,d,e,f,g,h,i,j,k) (H(H(H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i),j),k) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_12(a,b,c,d,e,f,g,h,i,j,k,l) (H(H(H(H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i),j),k),l) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_13(a,b,c,d,e,f,g,h,i,j,k,l,m) (H(H(H(H(H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i),j),k),l),m) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_14(a,b,c,d,e,f,g,h,i,j,k,l,m,n) (H(H(H(H(H(H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i),j),k),l),m),n) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_15(a,b,c,d,e,f,g,h,i,j,k,l,m,n,o) (H(H(H(H(H(H(H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i),j),k),l),m),n),o) % MATERIAL_HASH_MOD)
#define MATERIAL_HASH_16(a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p) (H(H(H(H(H(H(H(H(H(H(H(H(H(H(H(a,b),c),d),e),f),g),h),i),j),k),l),m),n),o),p) % MATERIAL_HASH_MOD)

// These values are the ASCII symbol for the letter - the ASCII code for space ' ' (actually 95 in decimal)
// This way it can easily be recalculated in C code.

#define _0_  0
#define _1_  1
#define _2_  2
#define _3_  3
#define _4_  4
#define _5_  5
#define _6_  6
#define _7_  7
#define _8_  8
#define _9_  9
#define _sp 47
#define _a_ 49
#define _b_ 50
#define _c_ 51
#define _d_ 52
#define _e_ 53
#define _f_ 54
#define _g_ 55
#define _h_ 56
#define _i_ 57
#define _j_ 58
#define _k_ 59
#define _l_ 60
#define _m_ 61
#define _n_ 62
#define _o_ 63
#define _p_ 64
#define _q_ 65
#define _r_ 66
#define _s_ 67
#define _t_ 68
#define _u_ 69
#define _v_ 70
#define _w_ 71
#define _x_ 72
#define _y_ 73
#define _z_ 74

static const half avatar_MATERIAL_TYPE_EYE             = half(MATERIAL_HASH_3(_e_, _y_, _e_));
static const half avatar_MATERIAL_TYPE_SKIN             = half(MATERIAL_HASH_4(_s_, _k_, _i_, _n_));
static const half avatar_MATERIAL_TYPE_HAIR             = half(MATERIAL_HASH_4(_h_, _a_, _i_, _r_));
// for backwards compatibility and proof of concept
static const half avatar_MATERIAL_TYPE_FACIAL_HAIR      = half(MATERIAL_HASH_11(_f_, _a_, _c_, _i_, _a_, _l_, _sp, _h_, _a_, _i_, _r_));

#else
static const half avatar_MATERIAL_TYPE_CLOTHES     = 1.0   / 255.0;
static const half avatar_MATERIAL_TYPE_EYE         = 2.0   / 255.0;
static const half avatar_MATERIAL_TYPE_SKIN        = 3.0   / 255.0;
static const half avatar_MATERIAL_TYPE_HAIR        = 4.0   / 255.0;
static const half avatar_MATERIAL_TYPE_FACIAL_HAIR = 5.0   / 255.0;
#endif // BLOCK_MATERIAL_SYSTEM

static const half avatar_MATERIAL_TYPE_BUFFER      = 0.5   / 255.0;

#ifdef BLOCK_MATERIAL_SYSTEM

float _SubMeshIdentification[64];   // A hash of the MATERIAL_TYPE associated with each submesh
float _SubMeshParameterOffsets[64]; // The offset of each submesh extension into the _SubMeshParameterData array
float _SubMeshParameterData[128];   // A contigious collection of all the material extension parameter data

int _SubMeshIdCount = 0;     // Number of sub-meshes loaded for this mesh

#ifndef MAX_MATERIAL_IDS_PER_SUBMESH
// Maximum number for _IdSlotsPerSubmesh below
#define MAX_MATERIAL_IDS_PER_SUBMESH 1
#endif
int _IdSlotsPerSubmesh = 1;  // Set by render program to match the _SubMeshIdentification array
                             // A stride for the _SubMeshIdentification array above
                             // This number will allow to have multiple extensions per submesh, at a great cost

half avatar_GetParameterFloat(int ExtensionOffset, int ParameterOffset) {

  return half(_SubMeshParameterData[ExtensionOffset + ParameterOffset]);

}

half3 avatar_GetParameterFloat3(int ExtensionOffset, int ParameterOffset) {

  return half3(_SubMeshParameterData[ExtensionOffset + ParameterOffset],
    _SubMeshParameterData[ExtensionOffset + ParameterOffset + 1],
    _SubMeshParameterData[ExtensionOffset + ParameterOffset + 2] );

}

half4 avatar_GetParameterFloat4(int ExtensionOffset, int ParameterOffset) {

  return half4(_SubMeshParameterData[ExtensionOffset + ParameterOffset],
    _SubMeshParameterData[ExtensionOffset + ParameterOffset + 1],
    _SubMeshParameterData[ExtensionOffset + ParameterOffset + 2],
    _SubMeshParameterData[ExtensionOffset + ParameterOffset + 3] );

}

#endif // BLOCK_MATERIAL_SYSTEM

bool avatar_WithinMaterialRange(half idChannel, half lowBound, half highBound) {
  bool condition = ((idChannel > (lowBound - avatar_MATERIAL_TYPE_BUFFER)) &&
                    (idChannel < (highBound + avatar_MATERIAL_TYPE_BUFFER)));
  return condition;
}

bool avatar_IsMaterialType(int idChannel, int materialTypeID) {
  return int(idChannel) == int(materialTypeID);
}

bool avatar_IsMaterialType(half idChannel, half materialTypeID) {
#ifdef BLOCK_MATERIAL_SYSTEM
  return avatar_IsMaterialType(int(idChannel), int(materialTypeID));
#else
  return avatar_WithinMaterialRange(idChannel, materialTypeID, materialTypeID);
#endif
}

bool avatar_UseEyeGlint(half idChannel) {
  return avatar_IsMaterialType(idChannel, avatar_MATERIAL_TYPE_EYE);
}

bool avatar_UseSkin(half idChannel) {
  return avatar_IsMaterialType(idChannel, avatar_MATERIAL_TYPE_SKIN);
}

bool avatar_UseHeadHair(half idChannel) {
  return avatar_IsMaterialType(idChannel, avatar_MATERIAL_TYPE_HAIR);
}

bool avatar_UseFacialHair(half idChannel) {
  return avatar_IsMaterialType(idChannel, avatar_MATERIAL_TYPE_FACIAL_HAIR);
}

#ifdef BLOCK_MATERIAL_SYSTEM

int avatar_HasParameterOffset(int idSubMesh, int materialTypeCode) {
#if (MAX_MATERIAL_IDS_PER_SUBMESH > 1)

  int subMeshOffset = idSubMesh * _IdSlotsPerSubmesh;
  for (int slot = 0; slot < _IdSlotsPerSubmesh; slot++)
  {
    int index = subMeshOffset + slot;

    half materialType = half(_SubMeshIdentification[index]);

    if (avatar_IsMaterialType(materialType, half(materialTypeCode)))
    {

      return int(_SubMeshParameterOffsets[index]); // conversion from float to int is critical

    }
  }
  return int(avatar_MATERIAL_OFFSET_INVALID);
#else
  int index = idSubMesh;

  half materialType = half(_SubMeshIdentification[index]);
  if (avatar_IsMaterialType(materialType, half(materialTypeCode)))
  {
    return int(_SubMeshParameterOffsets[index]); // conversion from float to int is critical
  }

  return int(avatar_MATERIAL_OFFSET_INVALID);
#endif
}

bool avatar_HasParameterization(int idSubMesh, int materialTypeCode) {
  int parameterOffset = avatar_HasParameterOffset(idSubMesh, materialTypeCode);
    if (parameterOffset != int(avatar_MATERIAL_OFFSET_INVALID))
      return true;
  return false;
}

#endif // BLOCK_MATERIAL_SYSTEM

#ifdef DEBUG_MODE_ON

#ifdef BLOCK_MATERIAL_SYSTEM
half3 SubMeshIdToMaterialTypeColor(int subMeshId)
{
    half3 returnColor = half3(0.2, 0.2, 0.2);;
    if (avatar_HasParameterization(subMeshId, int(avatar_MATERIAL_TYPE_EYE))) {
    returnColor = half3(0.9, 0.9, 0.9);
    }
    if (avatar_HasParameterization(subMeshId, int(avatar_MATERIAL_TYPE_SKIN))) {
    returnColor = half3(0.65, 0.50, 0.50);
    }
    if (avatar_HasParameterization(subMeshId, int(avatar_MATERIAL_TYPE_HAIR))) {
    returnColor = half3(0.345, 0.27, 0.11);
    }
    if (avatar_HasParameterization(subMeshId, int(avatar_MATERIAL_TYPE_FACIAL_HAIR))) {
    returnColor = half3(0.2, 0.1, 0.05);
    }
    return returnColor;
}
#else
half3 MaterialTypeToColor(half materialType)
{
    half3 returnColor = half3(0.2, 0.2, 0.2);;
    returnColor = half3(1.0,0.0,1.0);
    if (avatar_IsMaterialType(materialType, avatar_MATERIAL_TYPE_CLOTHES)) {
    returnColor = half3(0.2,0.2,0.2);
    }
    if (avatar_IsMaterialType(materialType, avatar_MATERIAL_TYPE_EYE)) {
    returnColor = half3(0.9,0.9,0.9);
    }
    if (avatar_IsMaterialType(materialType, avatar_MATERIAL_TYPE_SKIN)) {
    returnColor = half3(0.65,0.50,0.50);
    }
    if (avatar_IsMaterialType(materialType, avatar_MATERIAL_TYPE_HAIR)) {
    returnColor = half3(0.345,0.27,0.11);
    }
    if (avatar_IsMaterialType(materialType, avatar_MATERIAL_TYPE_FACIAL_HAIR)) {
    returnColor = half3(0.2,0.1,0.05);
    }
    return returnColor;
}
#endif

#endif

// eof material_type_utils.frag.glsl
// color_utils.frag.glsl
static const half GAMMA = 2.2;
static const half INV_GAMMA = 1.0 / GAMMA;

// Tone Mapping
// linear sRGB => XYZ => D65_2_D60 => AP1 => RRT_SAT
static const half3x3 ACESInputMat = half3x3(
  0.59719, 0.07600, 0.02840,
  0.35458, 0.90834, 0.13383,
  0.04823, 0.01566, 0.83777
);

// ODT_SAT => XYZ => D60_2_D65 => linear sRGB
static const half3x3 ACESOutputMat = half3x3(
  1.60475, -0.10208, -0.00327,
  -0.53108, 1.10813, -0.07276,
  -0.07367, -0.00605, 1.07602
);

// https://github.com/tobspr/GLSL-Color-Spaces/blob/master/ColorSpaces.inc.glsl
static const half3x3 RGB_2_CIE = half3x3(
  0.49000, 0.31000, 0.20000,
  0.17697, 0.81240, 0.01063,
  0.00000, 0.01000, 0.99000
);

static const half3x3 CIE_2_RGB = half3x3(
  2.36461385, -0.89654057, -0.46807328,
  -0.51516621, 1.4264081, 0.0887581,
  0.0052037, -0.01440816, 1.00920446
);

static const half3x3 RGB_2_XYZ = half3x3(
  0.4124564, 0.2126729, 0.0193339,
  0.3575761, 0.7151522, 0.1191920,
  0.1804375, 0.0721750, 0.9503041
);

static const half3x3 XYZ_2_RGB = half3x3(
  3.2404542, -0.9692660, 0.0556434,
  -1.5371385, 1.8760108, -0.2040259,
  -0.4985314, 0.0415560, 1.0572252
);

// -----------------------------------------------------------------------------------
// ACES filmic tone map approximation
// see https://github.com/TheRealMJP/BakingLab/blob/master/BakingLab/ACES.hlsl
half3 RRTAndODTFit(half3 color) {
    half3 a = color * (color + 0.0245786) - 0.000090537;
    half3 b = color * (0.983729 * color + 0.4329510) + 0.238081;
    return a / b;
}

// perceptual sRGB to linearsRGB  approximation
// see http://chilliant.blogspot.com/2012/08/srgb-approximations-for-hlsl.html
 half4 SRGBtoLINEAR(half4 srgbIn) {
  return half4(pow(srgbIn.rgb, half3(GAMMA, GAMMA, GAMMA)), srgbIn.a);
}

 half3 SRGBtoLINEAR(half3 srgbIn) {
  return pow(max(srgbIn.rgb, half3(0.0, 0.0, 0.0)), half3(GAMMA, GAMMA, GAMMA));
}

// linear sRGB to perceptual sRGB approximation
// see http://chilliant.blogspot.com/2012/08/srgb-approximations-for-hlsl.html
 half4 LINEARtoSRGB(half4 color) {
  return half4(pow(color.rgb, half3(INV_GAMMA, INV_GAMMA, INV_GAMMA)), color.a);
}

 half3 LINEARtoSRGB(half3 color) {
  return pow(max(color.rgb, half3(0.0, 0.0, 0.0)), half3(INV_GAMMA, INV_GAMMA, INV_GAMMA));
}

 half LINEARtoSRGB(half color) {
  return pow(color, INV_GAMMA);
}

#ifdef DEBUG_MODE_ON
// Hue sat and value are all in range [0,1]
half3 RGBtoHSV(half3 rgb)
{
    half4 K = half4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    half4 p = (lerp((half4(rgb.bg, K.wz)), (half4(rgb.gb, K.xy)), (step(rgb.b, rgb.g))));
    half4 q = (lerp((half4(p.xyw, rgb.r)), (half4(rgb.r, p.yzx)), (step(p.x, rgb.r))));
    half d = q.x - min(q.w, q.y);
    half e = 1.0e-10;
    return half3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

half3 HSVtoRGB(half3 hsv)
{
    half4 K = half4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    half3 p = abs(frac((hsv.xxx + K.xyz)) * 6.0 - K.www);
    return hsv.z * (lerp((K.xxx), (clamp(p - K.xxx, 0.0, 1.0)), (hsv.y)));
}

// Converts a color from linear RGB to XYZ space
half3 rgb_to_xyz(half3 rgb) {
  return mul(rgb, RGB_2_XYZ);
}

// Converts a color from XYZ to linear RGB space
half3 xyz_to_rgb(half3 xyz) {
  return mul(xyz, XYZ_2_RGB);
}

// Converts a color from linear RGB to XYZ space
half3 rgb_to_cie(half3 rgb) {
  return mul(rgb, RGB_2_CIE);
}

// Converts a color from XYZ to linear RGB space
half3 cie_to_rgb(half3 xyz) {
  return mul(xyz, CIE_2_RGB);
}
#endif

half4 ConvertInputColorSpaceToLinear(half4 unknownInput)
{
#ifdef UNITY_COLORSPACE_GAMMA

  return SRGBtoLINEAR(unknownInput);
#else

  return unknownInput;
#endif
}

half3 ConvertOutputColorSpaceFromSRGB(half3 srgbInput)
{
#ifdef UNITY_COLORSPACE_GAMMA
  return srgbInput;
#else
  return SRGBtoLINEAR(srgbInput);
#endif
}

half3 ConvertOutputColorSpaceFromLinear(half3 linearInput)
{
#ifdef UNITY_COLORSPACE_GAMMA
  return LINEARtoSRGB(linearInput);
#else
  return linearInput;
#endif
}

// StaticSelectMaterialMode functions are available to enable FastLoad avatars.
// Upon defining MATERIAL_MODE_VERTEX, colors/properties will be read from vertex attributes
// instead of textures. This allows for a fast and compact avatar model, although less detailed.

half4 StaticSelectMaterialModeColor(sampler2D texSampler, half2 texCoords, half4 vertexColor) {
#if defined(MATERIAL_MODE_VERTEX)
  return vertexColor;
#else
  half4 colorSample = tex2D(texSampler, texCoords);

  return ConvertInputColorSpaceToLinear(colorSample);
#endif
}

half4 StaticSelectMaterialModeProperty(sampler2D texSampler, half2 texCoords, half4 vertexColor, half bias) {
#if defined(MATERIAL_MODE_VERTEX)
  return vertexColor;
#else
  return tex2Dlod(texSampler, half4(texCoords, 0.0, bias));
#endif
}

// eof color_utils.frag.glsl
// combined_common_utils.frag.glsl
uniform sampler2D u_BaseColorSampler;
uniform sampler2D u_MetallicRoughnessSampler;
uniform sampler2D u_NormalSampler;

#ifdef SSS_CURVATURE
uniform half2 u_SSSCurvatureScaleBias;
#endif

uniform half u_Exposure;

uniform half u_NormalScale;

uniform half u_EyeGlintFactor;
uniform half u_EyeGlintColorFactor;

uniform half3 u_HairSubsurfaceColor;
uniform half3 u_HairSpecularColorFactor;
uniform half u_HairSpecularShiftIntensity;
uniform half u_HairSpecularWhiteIntensity;
uniform half u_HairSpecularColorIntensity;
uniform half u_HairSpecularColorOffset;
uniform half u_HairRoughness;
uniform half u_HairColorRoughness;
uniform half u_HairAnisotropicIntensity;
uniform half u_HairSpecularNormalIntensity;
uniform half u_HairDiffusedIntensity;

uniform half3 u_FacialHairSubsurfaceColor;
uniform half3 u_FacialHairSpecularColorFactor;
uniform half u_FacialHairSpecularShiftIntensity;
uniform half u_FacialHairSpecularWhiteIntensity;
uniform half u_FacialHairSpecularColorIntensity;
uniform half u_FacialHairSpecularColorOffset;
uniform half u_FacialHairRoughness;
uniform half u_FacialHairColorRoughness;
uniform half u_FacialHairAnisotropicIntensity;
uniform half u_FacialHairSpecularNormalIntensity;
uniform half u_FacialHairDiffusedIntensity;

uniform half u_RimLightIntensity;
uniform half u_RimLightBias;
uniform half3 u_RimLightColor;
uniform half u_RimLightTransition;
uniform half u_RimLightStartPosition;
uniform half u_RimLightEndPosition;

uniform half u_IsRightEye = 0.0;
uniform half3 u_EyeGlintLightColor = half3(1.0, 1.0, 1.0);

uniform half3 u_EmissiveColor;
uniform int u_EmissiveUseBaseColor;
uniform half u_EmissivePulseFrequency;
// specific to the IBL implementation, could they be moved to ambient_image_based.frag.sca ?
uniform samplerCUBE LambertianEnvSampler;
uniform samplerCUBE GGXEnvSampler;
// specific to the VertexGI implementation, could they be moved to ambient_vertex_gi.frag.sca ?
uniform sampler2D _ICMap;  // NOTE: VertexGI only uses this in the case of Normal mapping. Else it uses l1 from the vert shader.
uniform samplerCUBE _ReflectionCubeMap; // Same old map, different name

static const half3 u_EyeGlintRightDirectionOffset = half3(0.25, 0.25, 0.0);
static const half3 u_EyeGlintLeftDirectionOffset = half3(0.25, 0.25, 0.0);
static const half u_EyeGlintExponential = 2000.0;
static const half u_EyeGlintIntensity = 10.0;

static const half SSSIBLMultiplier = 0.333;
static const half increaseOcclusion =  0.4;
// The cosine of the angle lighting should contribute (wrap)
// past 90 degrees (where light would normally stop contributing)
// Ex. for a value of -.15 means wrapping 8.629 degrees past 90 degrees
// cos( 8.629) = -0.15
static const half SSSWrapAngle = -0.65;
static const half diffuseWrapAngle = -0.15;
static const half f0 = 0.04;
static const half eyeGlintMultiplier = 0.025;

// eof combined_common_utils.frag.glsl
// Forward declaration of app-specific functions:

void AppSpecificPreManipulation(inout avatar_FragmentInput i);
void AppSpecificFragmentComponentManipulation(avatar_FragmentInput i, inout float3 punctualSpecular, inout float3 punctualDiffuse, inout float3 ambientSpecular, inout float3 ambientDiffuse);
void AppSpecificPostManipulation(avatar_FragmentInput i, inout avatar_FragmentOutput o);
// pbr.vert.glsl

avatar_VertexOutput avatar_computeVertex(avatar_AvatarVertexInput i, avatar_Transforms transforms) {
    avatar_VertexOutput vout;
    half4 pos = mul(i.position, transforms.modelMatrix);
    half3 worldPos = half3(pos.xyz) / pos.w;
    vout.positionInClipSpace = mul(pos, transforms.viewProjectionMatrix);
    vout.positionInWorldSpace = worldPos;
    vout.normal = normalize(mul(i.normal, ((half3x3)(transforms.modelMatrix))));
    vout.texcoord0 = i.texcoord0;
    vout.texcoord1 = i.texcoord1;
    vout.texcoord2 = i.texcoord2;
    vout.color = i.color;
    vout.tangent = normalize(mul(i.tangent, ((half3x3)(transforms.modelMatrix))));

    return vout;
}
// unity.vert.glsl

// Options flags
// NOTE: For now in Unity these remain commented in the Vert shader.
// We do not yet have a way of using them in the vert shader and redefining them in the frag...

// Global Options vert

#ifndef DEC_bool_useSkinning
 #define DEC_bool_useSkinning
 static const bool useSkinning = false;
 #endif

uniform half4x4 u_ViewProjectionMatrix;
uniform half4x4 u_ModelMatrix;

static half4 a_Position;    // should be POSITION in Unity
static half4 a_Normal;      // should be NORMAL in Unity
static half4 a_Tangent;     // should be TANGENT in Unity
static uint a_vertexID;    // should be SV_VertexID in Unity
static half2 a_UV1;
static half2 a_UV2;
static half2 a_UV3;
static half4 a_Color;
static half4 a_ORMT;

 half4 _output_FragColor;
static half4 v_Vertex;
static float3 v_WorldPos;
static half3 v_Normal;
static float4 v_Tangent;
static float2 v_UVCoord1;
static half2 v_UVCoord2;
static half2 v_UVCoord3;
static half4 v_Color;
static half4 v_ORMT;
// per-vertex ambient value calculated with spherical harmonics
static half3 v_SH;

// eof unity.vert.glsl
// This is to fix the "redefinition of 'UnityDisplayOrientationPreTransform'" issue. The "HLSLSupport.cginc" and
// the "com.unity.render-pipelines.core/ShaderLibrary/API/Vulkan.hlsl" (which included in "com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl")
// can't be both included in 2021.3.30f1 or later version because they both define UnityDisplayOrientationPreTransform. In 2021.3.29f1 it is ok because
// "Vulkan.hlsl" in 2021.3.29f1 doesn't define UnityDisplayOrientationPreTransform.
// The fix is removing HLSLSupport.cginc here. The HLSLSupport.cginc is only needed for the UNITY_INITIALIZE_OUTPUT. So, I copied the
// UNITY_INITIALIZE_OUTPUT define to here.
// #include <HLSLSupport.cginc>
#ifndef UNITY_INITIALIZE_OUTPUT
    #if defined(UNITY_COMPILER_HLSL) || defined(SHADER_API_PSSL) || defined(UNITY_COMPILER_HLSLCC)
        #define UNITY_INITIALIZE_OUTPUT(type,name) name = (type)0;
    #else
        #define UNITY_INITIALIZE_OUTPUT(type,name)
    #endif
#endif

// Mapping of variables to shader semantics.

struct AvatarVertexInput
{
    half4 a_Color : COLOR;
    half4 a_ORMT : TEXCOORD1;
    half4 a_Normal : NORMAL;
    half4 a_Position : POSITION;
    half4 a_Tangent : TANGENT;
    half2 a_UV1 : TEXCOORD0;
    half2 a_UV2 : TEXCOORD3;
    half2 a_UV3 : TEXCOORD2;
    uint a_vertexID : SV_VertexID;

    UNITY_VERTEX_INPUT_INSTANCE_ID

};

struct VertexToFragment
{
    half4 v_Color : COLOR;
    half4 v_ORMT : TEXCOORD6;

    half3 v_Normal : TEXCOORD3;
    float4 v_Tangent : TEXCOORD4;
    float2 v_UVCoord1 : TEXCOORD0;
    half2 v_UVCoord2 : TEXCOORD1;
    half2 v_UVCoord3 : TEXCOORD2;
    half4 v_Vertex : SV_POSITION;
    float3 v_WorldPos : TEXCOORD5;
    half3 v_SH : TEXCOORD7;

    UNITY_VERTEX_OUTPUT_STEREO

};

// Forward declaration to be implemented by the calling app.
void AppSpecificVertexPostManipulation(AvatarVertexInput i, inout VertexToFragment o);

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
  VertexInput vertexInput;
  vertexInput.uv0 = a_UV1;
  vertexInput.uv1 = a_UV2;

  vin.ambient = VertexGIForward(vertexInput, vin.position.rgb, vin.normal).rgb;
  vin.texcoord0 = a_UV1;
  vin.texcoord1 = a_UV2;
  vin.texcoord2 = a_UV3;
  vin.ormt = a_ORMT.rgba;
  vin.color.a = a_Color.a;
#if MATERIAL_MODE_VERTEX
  vin.color.rgb = SRGBtoLINEAR(a_Color.rgb); // vertex color are stored in s_rgb, convert to linear.
#else
  vin.color.rgb = a_Color.rgb; // Vertex colors are only used in MODE_VERTEX, skip conversion for speed.
#endif
  avatar_Transforms transforms;
  transforms.viewProjectionMatrix = UNITY_MATRIX_VP;
  transforms.modelMatrix = unity_ObjectToWorld;

  // common vertex stuff:
  // skip the vout structure, since it doesn't understand VR
  // APFX(VertexOutput) vout = APFX(computeVertex)(vin, transforms);
  v_UVCoord1 = vin.texcoord0;
  v_UVCoord2 = vin.texcoord1;
  v_UVCoord3 = vin.texcoord2;
  v_Color = vin.color.rgba;
  v_ORMT = vin.ormt.rgba;
  v_SH = vin.ambient;

  // replacement for UnityObjectToClipPos
  //  v_Vertex = (vin.position * unity_ObjectToWorld) * UNITY_MATRIX_VP;
  v_Vertex = getVertexInClipSpace(vin.position.xyz/vin.position.w);

  // replacement for o.worldPos = mul(unity_ObjectToWorld, vertexData.position).xyz;
  half4 worldPos = mul(unity_ObjectToWorld, vin.position);
  v_WorldPos = worldPos.xyz / worldPos.w;

  v_Normal = normalize((mul(half4(vin.normal.xyz, 0.0), unity_WorldToObject)).xyz);
  v_Tangent = normalize(mul(half4(vin.tangent.xyz, 0.0), unity_WorldToObject));

}

VertexToFragment Vertex_main_instancing(AvatarVertexInput stage_input)
{

    a_Position = stage_input.a_Position;
    a_Normal = stage_input.a_Normal;
    a_Tangent = stage_input.a_Tangent;
    a_vertexID = stage_input.a_vertexID;
    a_UV1 = stage_input.a_UV1;
    a_UV2 = stage_input.a_UV2;
    a_UV3 = stage_input.a_UV3;
    a_Color = stage_input.a_Color;
    a_ORMT = stage_input.a_ORMT;
    VertexToFragment stage_output;

    UNITY_SETUP_INSTANCE_ID(stage_input);
    UNITY_INITIALIZE_OUTPUT(VertexToFragment, stage_output);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(stage_output);
    vert_Vertex_main();
    // measure to distinguish left of avatar from right
    v_ORMT.w = a_Position.x;
    stage_output.v_Vertex = v_Vertex;
    stage_output.v_WorldPos = v_WorldPos;
    stage_output.v_Normal = v_Normal;
    stage_output.v_Tangent = v_Tangent;
    stage_output.v_UVCoord1 = v_UVCoord1;
    stage_output.v_UVCoord2 = v_UVCoord2;
    stage_output.v_UVCoord3 = v_UVCoord3;
    stage_output.v_Color = v_Color;
    stage_output.v_ORMT = v_ORMT;
    stage_output.v_SH = v_SH;

    AppSpecificVertexPostManipulation(stage_input, stage_output);

    return stage_output;
}
// UNITY VERT CONFIG LOADED

// eof pbr.vert.glsl
// unity.frag.glsl
// utils.frag.glsl

#if !defined(M_PI)
static const float M_PI = 3.141592653589793f;
#endif
#if !defined(EPSILON)
static const float EPSILON = 0.001;
#endif
static const float M_PI_2 = 2.0f * M_PI;
static const float INV_M_PI = 1.0f / M_PI;
static const float PI_OVER_180 = M_PI/180.0;

static const half M_PI_HALF = 3.141592653589793;
static const half INV_M_PI_HALF = 1.0 / M_PI_HALF;
static const half M_PI_2_HALF = 2.0 * M_PI_HALF;
static const half PI_OVER_180_HALF = M_PI_HALF/180.0;
static const half EPSILON_HALF = 0.001;

static const half c_MinReflectance = 0.04;
static const half3 SubSurfaceScatterValue = half3(1.0, 0.3, 0.2);

half3 sampleTexCube(samplerCUBE cube, half3 normal) {

  return half3(texCUBE(cube, normal).rgb);

}

half3 sampleTexCube(samplerCUBE cube, half3 normal, half mip) {

  half4 normalWithLOD = half4(normal, mip);
  return half3(texCUBElod(cube, normalWithLOD).rgb);

}

 half computeNdotV(half3 normal, half3 world_view_dir){
    return saturate(dot(normal, world_view_dir));
}

 half3 computeViewDir(half3 camera, half3 position) {
  return normalize(position - camera);
}

 half3 reflection(half3 normal, half3 world_view_dir) {
  return world_view_dir - 2.0 * normal * dot(world_view_dir, normal);
}

 half deg2rad(half angle) {
  return angle * PI_OVER_180_HALF;
}

 half luminance(half3 rgb) {
  return dot(rgb, half3(0.2126, 0.7152, 0.0722));
}

half3 ConvertOutputColorSpaceFromSRGB(half3 srgbInput);
half3 ConvertOutputColorSpaceFromLinear(half3 linearInput);

half inverselerp(half a, half b, half v) {
  return (v-a)/(b-a);
}

half  getBias(half time,half bias)
{
   return (time / ((((0.0/bias) - 2.0)*(1.0 - time))+1.0));
}

half getGain(half time,half gain)
{
  if(time < -1.5)
    return getBias(time * 1.0, gain)/2.0;
  else
    return getBias(time * 1.0 - 1.0, 1.0 - gain) / 2.0 + 0.5;
}

 half is_less_than (half a, half b) {
    return 1.0 - step(b, a);
}

 half is_greater_than(half a, half b) {
    return 1.0 - step(a, b);
}

 half is_equal(half a, half b) {
    return step(a, b) * step(b, a);
}

 half is_less_than_or_equal(half a, half b) {
    return step(a, b);
}

 half is_greater_than_or_equal(half a, half b) {
    return step(b, a);
}

// This function is NOT an and for minfloats, it's an and for ones and zeroes (trues and falses)
// We're using it to combine logical statements (using the above functions)
// because AR Engine shaders see a significant slow down on if statements
 half and(half a, half b) {
    return a * b;
}

// eof utils.frag.glsl
// alpha_coverage_utils.frag.glsl

// create MSAA sample mask from alpha value for to emulate transparency
// used by DithercoverageFromMaskMSAA4(), don't call this function
// for 4x MSAA, also works for more MSAA but at same quality, FFR friendly
// @param alpha 0..1
uint avatar_alphaToCoverage(half alpha) {
    // can be optimized futher
    uint Coverage = 0u; // 0x00;
    if (alpha > (0.0 / 4.0)) Coverage = 136u; // 0x88;
    if (alpha > (1.0 / 4.0)) Coverage = 153u; // 0x99;
    if (alpha > (2.0 / 4.0)) Coverage = 221u; // 0xDD;
    if (alpha > (3.0 / 4.0)) Coverage = 255u; // 0xFF;
    return Coverage;
}

// see https://developer.oculus.com/blog/tech-note-shader-snippets-for-efficient-2d-dithering
half avatar_dither17b(half2 svPosition, half frameIndexMod4) {
    half3 k0 = half3(2.0, 7.0, 23.0);
    half Ret = dot(half3(svPosition, frameIndexMod4), k0 / 17.0);
    return frac((Ret));
}

// create MSAA sample mask from alpha value for to emulate transparency,
// for 4x MSAA,  can show artifacts with FFR
// @param alpha 0..1, outside range should behave the same as saturate(alpha)
// @param svPos xy from SV_Position
// @param true: with per pixel dither, false: few shades
uint avatar_coverageFromMaskMSAA4(half alpha, half2 svPos, bool dither) {
    // using a constant in the parameters means the dynamic branch (if) gets compiled out,
    if (dither) {
        // the pattern is not animated over time, no extra perf cost
        half frameIndexMod4 = 0.0;
        // /4: to have the dithering happening with less visual impact as 4
        //     shades are already implemented with MSAA subsample rejection.
        // -=: subtraction because the function coverageFromMaskMSAA4() shows visuals
        //     effect >0 and we want to have some pixels not have effect depending on dithering.
        alpha -= (avatar_dither17b(svPos, frameIndexMod4) / 4.0);
    }
    else {
        // no dithering, no FFR artifacts with Quest
        alpha -= (0.5 / 4.0);
    }
    return avatar_alphaToCoverage(alpha);
}

uint avatar_calculateAlphaCoverage(avatar_FragmentInput i, half3 positionInScreenSpace) {
    #ifdef HAS_ALPHA_TO_COVERAGE_ON
    return avatar_coverageFromMaskMSAA4(i.material.alpha, positionInScreenSpace.xy, true);
    #else
    return 255u;
    #endif
}

// eof alpha_coverage_utils.frag.glsl
// UNITY SPECIFIC START
// All these Unity specific functions are intended to be sanitized, then replaced with :

// Options flags:
// NOTE: These should naturally exist in uncombined rendering.
// In combined rendering they're filtered by the subMeshID/vertex color alpha.

// Global Options frag:

#ifndef DEC_bool_useSubmesh
 #define DEC_bool_useSubmesh
 static const bool useSubmesh = false;
 #endif

// Local Options (per Primitive/Material):
#ifndef DEC_bool_enableSkin
 #define DEC_bool_enableSkin
 static const bool enableSkin = false;
 #endif
#ifndef DEC_bool_enableEyeGlint
 #define DEC_bool_enableEyeGlint
 static const bool enableEyeGlint = false;
 #endif
#ifndef DEC_bool_enableHair
 #define DEC_bool_enableHair
 static const bool enableHair = false;
 #endif

// Output semantics

struct FragmentOutput
{
  half4 _output_FragColor : COLOR0; // Should be target0 if multiple outputs. Maybe use TARGET0 always.
};

// Unity Specific Functions
// If compiled in a non internal unity environment, define this stub functions

uniform int u_MipCount; // must be manually set by the IBL lighting system to the mip count of the diffuse Lambertian sampler cubemap

// UNITY SPECIFIC END

#ifdef DEBUG_MODE_ON
uniform int Debug;
static const int debugMode = Debug;
#endif

uniform int u_lightCount;

// eof unity.frag.glsl
// unityGI.frag.glsl

void InitializeSHCoeffs(inout avatar_FragmentInput i)
{
  i.SHCoeff0 = half3(unity_SHAr.w, unity_SHAg.w, unity_SHAb.w);
  i.SHCoeff1 = half3(unity_SHAr.y, unity_SHAg.y, unity_SHAb.y);
  i.SHCoeff2 = half3(unity_SHAr.z, unity_SHAg.z, unity_SHAb.z);
  i.SHCoeff3 = half3(unity_SHAr.x, unity_SHAg.x, unity_SHAb.x);

  i.SHCoeff4 = half3(0.0, 0.0, 0.0);
  i.SHCoeff5 = half3(0.0, 0.0, 0.0);
  i.SHCoeff6 = half3(0.0, 0.0, 0.0);
  i.SHCoeff7 = half3(0.0, 0.0, 0.0);
  i.SHCoeff8 = half3(0.0, 0.0, 0.0);

  #if !defined(UNITY_PIPELINE_URP) && UNITY_LIGHT_PROBE_PROXY_VOLUME
  if (unity_ProbeVolumeParams.x == 1.0)
  {
    half3 worldPos = i.geometry.positionInWorldSpace;

      const half transformToLocal = unity_ProbeVolumeParams.y;
      const half texelSizeX = unity_ProbeVolumeParams.z;

      half3 position = (transformToLocal == 1.0f) ? mul(half4(worldPos, 1.0), unity_ProbeVolumeWorldToObject).xyz : worldPos;
      half3 texCoord = (position - unity_ProbeVolumeMin.xyz) * unity_ProbeVolumeSizeInv.xyz;
      texCoord.x = texCoord.x * 0.25f;

      half texCoordX = clamp(texCoord.x, 0.5 * texelSizeX, 0.25 - 0.5 * texelSizeX);

      texCoord.x = texCoordX;
      half4 SHAr = UNITY_SAMPLE_TEX3D_SAMPLER(unity_ProbeVolumeSH, unity_ProbeVolumeSH, texCoord);
      texCoord.x = texCoordX + 0.25f;
      half4 SHAg = UNITY_SAMPLE_TEX3D_SAMPLER(unity_ProbeVolumeSH, unity_ProbeVolumeSH, texCoord);
      texCoord.x = texCoordX + 0.5f;
      half4 SHAb = UNITY_SAMPLE_TEX3D_SAMPLER(unity_ProbeVolumeSH, unity_ProbeVolumeSH, texCoord);

    i.SHCoeff0 = half3(SHAr.w, SHAg.w, SHAb.w);
    i.SHCoeff1 = half3(SHAr.y, SHAg.y, SHAb.y);
    i.SHCoeff2 = half3(SHAr.z, SHAg.z, SHAb.z);
    i.SHCoeff3 = half3(SHAr.x, SHAg.x, SHAb.x);
  }

  #endif
}

// eof unityGI.frag.glsl
// unity_data.glsl

half2 safeNormalize(half2 value) {
    return value * rsqrt(max(EPSILON_HALF, dot(value, value)));
}

half3 safeNormalize(half3 value) {
    return value * rsqrt(max(EPSILON_HALF, dot(value, value)));
}

half4 safeNormalize(half4 value) {
    return value * rsqrt(max(EPSILON_HALF, dot(value, value)));
}

 half3 applyExposure(half3 value, half exposure) {
    value = max(half3(0.0, 0.0, 0.0), value);
    value *= exp2((exposure));
    return value;
}

half getIntensity() {
    return half(u_Exposure);
}
half getExposure() {
    return 0.0;
}

half getLod(half roughness) {
    half mipCount = 1.0 * half(u_MipCount);
    return clamp(roughness * (mipCount), 0.0, mipCount);
}

half4 getVertexColor() {
    return v_Color;
}

#ifndef BLOCK_MATERIAL_SYSTEM
half getMaterialType() {
    half materialType = getVertexColor().a;
    return materialType;
}
#endif

int getSubMeshIndex() {
    return (int)(getVertexColor().a * 255.0 + avatar_SUBMESH_TYPE_BUFFER);
}

float3 getWorldPosition() {
    return v_WorldPos;
}

half3 getClipPosition() {
    return v_Vertex.xyz;
}

float2 getTexcoord0() {
    return v_UVCoord1;
}

half3 getUnperturbedNormal() {
    return normalize(v_Normal);
}

half3 getTangent() {
    return normalize(v_Tangent.xyz);
}

half4 getVertexORMT() {
    return v_ORMT;
}

half3 getAmbientColor() {
    return v_SH;
}

half4x4 getObjectToWorldMatrix() {
    return unity_ObjectToWorld;
}

half3x3 getWorldToObjectMatrix() {
    return half3x3(unity_WorldToObject[0].xyz, unity_WorldToObject[1].xyz, unity_WorldToObject[2].xyz);
}

half3x3 getViewMatrix() {
    return half3x3(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0);
}

half3 getLightDirection() {

    #ifdef USING_URP
    return  GetMainLight().direction;
    #else
    return _WorldSpaceLightPos0;
    #endif

}

int getLightCount() {
    if(any(getLightDirection())) {
        #ifdef USING_URP
        return GetAdditionalLightsCount() + 1;
        #else
        return 1;
        #endif
    } else {
        return 0;
    }

}

half3 getLightColor() {

    #ifdef USING_URP
    return _MainLightColor.rgb;
    #else
    return  _LightColor0;
    #endif

}

OvrLight getAdditionalLight(int idx, half3 worldPos){
#ifdef USING_URP
    return OvrGetAdditionalLight(idx, worldPos);
#else
    OvrLight dummy;
    return dummy;
#endif
}

void fillInLightData(inout avatar_FragmentInput i) {
    i.lights[0].intensity = 1.0;
    i.lights[0].direction_normalized = normalize(getLightDirection());
    i.lights[0].color = getLightColor();
    i.lights[0].directional_light_color = (i.lights[0].color) * (1.0/u_Exposure) * INV_M_PI;
    i.lights[0].areaLightAngleSin = 0.174108138;

#if MAX_LIGHT_COUNT > 1
    for(int idx = 1; idx < MAX_LIGHT_COUNT; idx++) {
        if(idx < getLightCount()) {
            OvrLight ovrLight = getAdditionalLight(idx, v_WorldPos);
            avatar_Light avatarLight;
            avatarLight.direction_normalized = normalize(ovrLight.direction);
            avatarLight.intensity = 1.0;
            avatarLight.color = ovrLight.color;
            avatarLight.directional_light_color = (avatarLight.color) * (1.0/u_Exposure) * INV_M_PI;
            avatarLight.areaLightAngleSin = 0.174108138;
            i.lights[idx] = avatarLight;
        }
    }
#endif
}

half getEnvironmentMapMultiplier() {
    return 1.0;
}

half3 getWorldViewDir() {
    return normalize(_WorldSpaceCameraPos - getWorldPosition());
}

half3x3 getEnvironmentRotation() {
    return half3x3(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0);
}

half4 sampleBaseColor(half2 uv, half4 color) {
    return StaticSelectMaterialModeColor(u_BaseColorSampler, uv, color);
}

half4 sampleMetallicRoughness(half2 uv, half4 ormt) {
    return StaticSelectMaterialModeColor(u_MetallicRoughnessSampler, uv, ormt);
}

half2 sampleNormalMap(half2 uv) {
    #if defined(SHADER_API_D3D11) || (defined (SHADER_API_VULKAN) && !defined(UNITY_PLATFORM_ANDROID))
    // BC3 or BC5 compression is 2 channel in x and y
    half2 sampledXY = tex2D(u_NormalSampler, uv).xy; // Begin sample in the normalized space [0,1]
    #else
    // ASTC compression is 2 channel with rrrg swizzle, sample y and w
    half2 sampledXY = tex2D(u_NormalSampler, uv).yw; // Begin sample in the normalized space [0,1]
    #endif
    return sampledXY;
}

half3 getShadingNormal(half2 uv, half3 tangent, half3 bitangent, half3 unperturbedNormal) {
    half2 sampledXY = sampleNormalMap(uv);
    sampledXY.y = 1.0 - sampledXY.y; // Invert y axis on all normal perturbations, empirically correct on 6/24/24
    sampledXY = 2.0 * sampledXY - 1.0;  // Expand sample to vector space [-1,1].
    half3 shadingNormal = half3(sampledXY, sqrt(1.0 - dot(sampledXY, sampledXY)));
    return normalize(mul(shadingNormal, half3x3(tangent, bitangent, unperturbedNormal)));
}

half3 getEyeGlintLightColor() {
    return u_EyeGlintLightColor;
}

bool isRightEye(half ormtW) {
    return (ormtW > 0.0);
}

half getCurvature(half2 uv) {
    #if defined(SSS_CURVATURE)
    return (uv.x / 10.0) * u_SSSCurvatureScaleBias.x + u_SSSCurvatureScaleBias.y;
    #else
    return 0.0;
    #endif
}

half getCombinedOcclusion(half properties_occlusion, half ormtX, bool isAnyHair) {
    if(isAnyHair) {
        return ormtX;
    } else{
        return properties_occlusion;
    }
}

float avatar_getTime() {

    return _Time.y;
}
// EOF unity_data.glsl
// SH_utils.frag.glsl

#ifdef SSS_CURVATURE

half3 computeSSSApproximation(half NdotL, half curvature) {
  half c = clamp(curvature, 0.0, 1.0);
  static const half3 a0 = half3(-0.00808314, 0.0835151, 0.0920432);
  static const half3 a1 = half3(0.355864, 0.418737, 0.407632);
  static const half3 a2 = half3(0.0241138, -0.0446712, -0.0382355);
  static const half3 a3 = half3(0.622981, 0.562233, 0.546097);
  static const half3 a4 = half3(-0.915144, -0.366103, -0.207718);
  static const half3 a5 = half3(0.9084, 0.315669, 0.167824);
  half3 t = half3(NdotL, NdotL, NdotL) * (a0 * c + a1) + (a2 * c + a3);
  half3 fade = clamp(a4 * c +a5, 0.0, 1.0);
  return (t * t * t * fade) + clamp(NdotL, 0.0, 1.0) * (half3(1.0, 1.0, 1.0) - fade);
}
#endif

 half3 evalSHIrradiance(avatar_FragmentInput i, half3 N) {

  const half c0 = 0.282095 * 3.1415;
  const half c1 = 0.488603 * 2.09435;
  const half c20m = 0.315392 * 3.0 * 0.785398;
  const half c20b = 0.315392 * 0.785398;
  const half c22 = 0.546274 * 0.785398;
  const half c2x = 1.092548 * 0.785398;
  half x = N.x;
  half y = N.y;
  half z = N.z;
  half xsq =  x*x;
  half ysq =  y*y;
  half zsq =  z*z;

  half3 col =  (i.SHCoeff0 * c0)
            + (i.SHCoeff1 * (c1 * y))
            + (i.SHCoeff2 * (c1 * z))
            + (i.SHCoeff3 * (c1 * x))
            + (i.SHCoeff4 * (c2x * x * y))
            + (i.SHCoeff5 * (c2x * y * z))
            + (i.SHCoeff6 * (c20m * zsq-c20b))
            + (i.SHCoeff7 * (c2x * x * z))
            + (i.SHCoeff8 * (c22 * (xsq-ysq)));

  col = max(half3(0.0, 0.0, 0.0), col);
  col *= exp2(half(i.material.exposure));

  return half3(col);

}

half3 zh1PolynomialApproximation(half curvature) {
  half3 ZH1;
  half x1  = curvature;
  half x2 = x1 * x1;
  half x3 = x2 * x1;

  ZH1.g = x2 * -0.03049119   + (x1 * -0.00234933    + 0.64157382);
  ZH1.b = x2 * -0.0137731528 + (x1 * 0.000875828145 + 0.641376033);

  ZH1.r = x3 * 0.29126806   + (x2 * -0.3900409 + (x1 * -0.11944291 + 0.6474976));

  return ZH1;
}

void twoZHPolynomialApproximation(half curvature, out half3 ZH1, out half3 ZH2) {

  half x1  = curvature;
  half x2 = x1 * x1;
  half x3 = x2 * x1;

  ZH1.g = x2 * -0.03049119   + (x1 * -0.00234933    + 0.64157382);
  ZH1.b = x2 * -0.0137731528 + (x1 * 0.000875828145 + 0.641376033);
  ZH2.g = x2 * -0.02154172   + (x1 * -0.00689284    + 0.18230826);
  ZH2.b = x2 * -0.0134045    + (x1 * -0.00076553    + 0.18184449);

  ZH1.r = x3 * 0.29126806   + (x2 * -0.3900409 + (x1 * -0.11944291 + 0.6474976));
  ZH2.r = x3 * 0.04313884   + (x2 * 0.0343144  + (x1 * -0.16377994  + 0.18806706));

}

 half3 evalSHIrradiance_SH4(avatar_FragmentInput i, half3 N) {

  const half c0 = 0.282095 * 3.1415;
  const half c1 = 0.488603 * 2.09435;
  half x = N.x;
  half y = N.y;
  half z = N.z;

  half3 col =  (i.SHCoeff0 * c0)
            + (i.SHCoeff1 * (c1 * y))
            + (i.SHCoeff2 * (c1 * z))
            + (i.SHCoeff3 * (c1 * x));

  col = max(half3(0.0, 0.0, 0.0), col);
  col *= exp2(half(i.material.exposure));

  return half3(col);

}

#ifdef SSS_CURVATURE

 half3 evalSHIrradianceSSS(avatar_FragmentInput i, half3 N, half curvature ) {
  curvature = clamp(curvature,0.0,1.0);
  half3 ZH0 = half3(1.0,1.0,1.0);

  half3 ZH1 = half3(0.0, 0.0, 0.0);
  half3 ZH2 = half3(0.0, 0.0, 0.0);
  twoZHPolynomialApproximation(curvature, ZH1, ZH2);

  half3 c0 = 0.282095 * ZH0;
  half3 c1 = 0.488603 * ZH1;
  half3 c20m = 0.315392 * 3.0 * ZH2;
  half3 c20b = 0.315392 * ZH2;
  half3 c22 = 0.546274 * ZH2;
  half3 c2x = 1.092548 * ZH2;
  half x = N.x;
  half y = N.y;
  half z = N.z;
  half xsq =  x*x;
  half ysq =  y*y;
  half zsq =  z*z;

  half3 col =  (i.SHCoeff0 * c0)
            + (i.SHCoeff1 * (c1 * y))
            + (i.SHCoeff2 * (c1 * z))
            + (i.SHCoeff3 * (c1 * x))
            + (i.SHCoeff4 * (c2x * x * y))
            + (i.SHCoeff5  * (c2x * y * z))
            + (i.SHCoeff6 * (c20m * zsq-c20b))
            + (i.SHCoeff7 * (c2x * x * z))
            + (i.SHCoeff8 * (c22 * (xsq-ysq)));

  col = max(half3(0.0, 0.0, 0.0), col);
  col *= exp2(half(i.material.exposure));
  return col* 3.14159;
}

 half3 evalSHIrradianceSSS_SH4(avatar_FragmentInput i, half3 N, half curvature ) {

  half3 ZH1 = zh1PolynomialApproximation(curvature);

  half3 c0 = half3(0.282095,0.282095,0.282095);
  half3 c1 = 0.488603 * ZH1;
  half x = N.x;
  half y = N.y;
  half z = N.z;

  half3 col =  (i.SHCoeff0  * c0)
            + (i.SHCoeff1 * (c1 * y))
            + (i.SHCoeff2 * (c1 * z))
            + (i.SHCoeff3 * (c1 * x));

  col = max(half3(0.0, 0.0, 0.0), col);
  col *= exp2(half(i.material.exposure));
    return col* 3.14159;
}

#endif
// Start of debug_utils.glsl

#ifdef DEBUG_MODE_ON
 const half3 SHADER_ERROR_COLOR = half3(1.0, 0.0, 1.0);
// These debug outputs should match the ones in GltfGLPBRShaders
// https://fburl.com/code/1m6zt8qq
static const int debug_None = 0;
static const int debug_BaseColorSRGB = 1;
static const int debug_BaseColorLinear = 2;
static const int debug_Alpha = 3;
static const int debug_PropertiesOcclusion = 4;
static const int debug_Metallic = 5;
static const int debug_Roughness = 6;
static const int debug_Thickness = 7;
static const int debug_Normal = 8;
static const int debug_NormalGeometry = 9;
static const int debug_NormalWorld = 10;
static const int debug_Tangent = 11;
static const int debug_Bitangent = 12;
static const int debug_F0 = 13;
static const int debug_EmissiveSrgb = 14;
static const int debug_EmissiveLinear = 15;
static const int debug_SpecularSrgb = 16;
static const int debug_DiffuseSrgb = 17;
static const int debug_ClearcoatSrgb = 18;
static const int debug_SheenSrgb = 19;
static const int debug_TransmissionSrgb = 20;
static const int debug_IBL = 21;
static const int debug_IBLDiffuse = 22;
static const int debug_IBLSpecular = 23;
static const int debug_IBLBrdf = 24;
static const int debug_Punctual = 25;
static const int debug_PunctualDiffuse = 26;
static const int debug_PunctualSpecular = 27;
static const int debug_Anisotropy = 28;
static const int debug_AnisotropyDirection = 29;
static const int debug_AnisotropyTangent = 30;
static const int debug_AnisotropyBitangent = 31;
static const int debug_View = 32;
static const int debug_SubsurfaceScattering = 33;
static const int debug_ScreenspaceOcclusion = 34;
static const int debug_SSSCurvature = 35;
static const int debug_SSSCurvaturePunctual = 36;
static const int debug_SSSCurvatureAmbient = 37;
static const int debug_TexCoord0 = 38;
static const int debug_TexCoord1 = 39;
static const int debug_SHIrradiance = 40;
static const int debug_Submeshes = 41;
static const int debug_MaterialType = 42;
static const int debug_Shadows_Light_0 = 43;
static const int debug_NoTonemap = 44;
static const int debug_CombinedOcclusion = 45;
static const int debug_Shadows_Light_1 = 46;
static const int debug_Shadows_Light_2 = 47;
static const int debug_Shadows_Light_3 = 48;

// Forward define of the Ambient SSS function:
half3 computeIndirectSubsurfaceContributionSH(avatar_FragmentInput i);

 half3 outputDebugColor(int mode, avatar_FragmentInput i, half3 punctualDiffuse, half3 punctualSpecular, half3 ambientDiffuse, half3 ambientSpecular, half3 ambientSubsurfaceScatterContribution, half3 punctualSubsurfaceScatterContribution, half3 rimLight, half3 preTonemap , bool isAnyHair, half hairFlowSample, bool isSkin) {
    half3 finalColor = half3(0.0, 0.0, 0.0);
    finalColor = SHADER_ERROR_COLOR; // the color magenta denotes a bad debugger or one that hasn't been written yet
    bool bColourIsHDRLinear = false;
    bool bColourIsLinear = false;
        if (mode == debug_BaseColorSRGB) {
          finalColor =  (i.material.base_color.rgb);
        }
        if (mode == debug_BaseColorLinear) {
          finalColor.rgb =   LINEARtoSRGB(i.material.base_color.rgb);
        }
        if (mode == debug_Alpha) {
          finalColor.rgb =  half3(i.material.alpha, i.material.alpha, i.material.alpha);
        }
        if (mode == debug_PropertiesOcclusion) {
          finalColor.rgb =  half3(i.material.properties_occlusion, i.material.properties_occlusion, i.material.properties_occlusion);
        }
        if (mode == debug_Roughness) {

          finalColor.rgb = ConvertOutputColorSpaceFromSRGB(half3(i.material.roughness, i.material.roughness, i.material.roughness));
          if (isAnyHair)
          {
              finalColor.rgb = ConvertOutputColorSpaceFromSRGB(half3(hairFlowSample, hairFlowSample, hairFlowSample));
          }

        }
        if (mode == debug_Metallic) {

          finalColor.rgb = ConvertOutputColorSpaceFromSRGB(half3(i.material.metallic, i.material.metallic, i.material.metallic));

        }
        if (mode == debug_Thickness) {
          finalColor.rgb =  half3(i.material.thickness, i.material.thickness, i.material.thickness);
        }
        if (mode == debug_Normal) {
          finalColor.rgb = half3(i.geometry.normal) * 0.5 + 0.5;
        }
        if (mode == debug_NormalGeometry) {
          finalColor.rgb = half3(i.geometry.unperturbedNormal) * 0.5 + 0.5;
        }
        if (mode == debug_NormalWorld) {
          finalColor.rgb = half3(i.geometry.normal) * 0.5 + 0.5;
        }
        if (mode == debug_Tangent) {
          finalColor.rgb = half3(i.geometry.tangent) * 0.5 + 0.5;
        }
        if (mode == debug_Bitangent) {
          finalColor.rgb = half3(i.geometry.bitangent) * 0.5 + 0.5;
        }
        if (mode == debug_F0) {
        finalColor.rgb = i.material.f0;
        }
        if (mode == debug_EmissiveSrgb) {

          finalColor.rgb = SHADER_ERROR_COLOR;

        }
        if (mode == debug_EmissiveLinear) {

          finalColor.rgb = SHADER_ERROR_COLOR;

        }
        if (mode == debug_SpecularSrgb) {
          finalColor.rgb =  punctualSpecular + ambientSpecular;
        }
        if (mode == debug_DiffuseSrgb) {
          finalColor.rgb = (punctualDiffuse + ambientDiffuse);
        }
        if (mode == debug_ClearcoatSrgb) {
          finalColor.rgb = SHADER_ERROR_COLOR;
        }
        if (mode == debug_SheenSrgb) {
          finalColor.rgb = SHADER_ERROR_COLOR;
        }
        if (mode == debug_TransmissionSrgb) {
          finalColor.rgb = SHADER_ERROR_COLOR;
        }
        if (mode == debug_IBL) {
          finalColor.rgb = ambientSpecular + ambientDiffuse;
          bColourIsHDRLinear = true;
        }
        if (mode == debug_IBLDiffuse) {
          finalColor.rgb = ambientDiffuse;
          bColourIsHDRLinear = true;
        }
        if (mode == debug_IBLSpecular) {
          finalColor.rgb = ambientSpecular;
        }
        if (mode == debug_IBLBrdf) {
          finalColor.rgb = SHADER_ERROR_COLOR;
        }
        if (mode == debug_Punctual) {
          finalColor.rgb = punctualDiffuse + punctualSpecular;
          bColourIsHDRLinear = true;
        }
        if (mode == debug_PunctualDiffuse) {
          finalColor.rgb = punctualDiffuse;
          bColourIsHDRLinear = true;
        }
        if (mode == debug_PunctualSpecular) {
          finalColor.rgb = punctualSpecular;
          bColourIsHDRLinear = true;
        }
        if (mode == debug_Anisotropy) {

          finalColor.rgb = SHADER_ERROR_COLOR;

        }
        if (mode == debug_AnisotropyDirection) {
          finalColor.rgb = SHADER_ERROR_COLOR;
        }
        if (mode == debug_AnisotropyTangent) {

          finalColor.rgb = SHADER_ERROR_COLOR;

        }
        if (mode == debug_AnisotropyBitangent) {
          finalColor.rgb = SHADER_ERROR_COLOR;
        }
        if (mode == debug_View) {
          finalColor.rgb = half3(i.geometry.worldViewDir);
        }
        if (mode == debug_SubsurfaceScattering) {
          finalColor.rgb = ambientSubsurfaceScatterContribution + punctualSubsurfaceScatterContribution;
          bColourIsHDRLinear = true;
        }
        if (mode == debug_ScreenspaceOcclusion) {

        }
        if (mode == debug_SSSCurvature) {

          if (isSkin)
          {

            finalColor.rgb = half3(i.geometry.curvature,i.geometry.curvature,i.geometry.curvature);
            finalColor = LINEARtoSRGB(finalColor);

          }

        }

        if (mode == debug_SSSCurvatureAmbient || mode == debug_SSSCurvaturePunctual) {
        #ifdef SSS_CURVATURE

          half2 uvCurvatureLUT;

          avatar_Light light = i.lights[0];
          half3 surfacePointToLightDir = light.direction_normalized;
          half NdotL = dot(i.geometry.normal, surfacePointToLightDir);
          uvCurvatureLUT = half2(NdotL * 0.5 + 0.5, i.geometry.curvature);
          if (mode == debug_SSSCurvatureAmbient) {

            if (isSkin)
            {

              finalColor.rgb = computeIndirectSubsurfaceContributionSH(i);

            }

          }

          if (mode == debug_SSSCurvaturePunctual) {

            if (isSkin)
            {

            finalColor.rgb = computeSSSApproximation(half(NdotL), i.geometry.curvature);

            }

            bColourIsHDRLinear = true;
          }

       #endif
        }

        if (mode == debug_TexCoord0) {
          finalColor.rgb = half3(i.geometry.texcoord_0.x, i.geometry.texcoord_0.y, 0.0);
        }
        if (mode == debug_TexCoord1) {

        }
        if (mode == debug_SHIrradiance) {

      }

        if (mode == debug_Submeshes) {

            half subMeshId = i.material.alpha;
            finalColor.rgb = SubMeshIdToColor(subMeshId);

        }

        if (mode == debug_MaterialType) {
    #ifdef BLOCK_MATERIAL_SYSTEM
          finalColor.rgb = SubMeshIdToMaterialTypeColor(int(getVertexColor().a * 255.0 + avatar_SUBMESH_TYPE_BUFFER));
    #else
          half materialType = getMaterialType();
          finalColor.rgb = MaterialTypeToColor(materialType);
    #endif
        }

        if(bColourIsHDRLinear) {

          finalColor = LINEARtoSRGB(finalColor);
        } else if (bColourIsLinear) {
          finalColor = LINEARtoSRGB(finalColor);
        }

        if (mode == debug_NoTonemap) {

        }
        if (mode == debug_CombinedOcclusion) {
          finalColor.rgb = half3(i.material.combined_occlusion, i.material.combined_occlusion, i.material.combined_occlusion);
        }
        return finalColor;
}

#endif

// EOF debug_utils.glsl
  half3 avatar_computeAmbientDiffuseLighting(avatar_FragmentInput i, half3 normal) {
    half3 diffuse = half3(0.0, 0.0, 0.0);
    half3 specular_contribution = half3(0.0, 0.0, 0.0);
    OvrGetUnityDiffuseGlobalIllumination(i.lights[0].color, -i.lights[0].direction_normalized, i.geometry.positionInWorldSpace, i.geometry.worldViewDir,
      1.0, i.ambient_color, 1.0 - i.material.roughness, i.material.metallic, i.material.combined_occlusion, i.material.base_color, normal, specular_contribution, diffuse);
    return diffuse;
  }

  half3 avatar_computeAmbientDiffuseLighting(avatar_FragmentInput i) {
    return avatar_computeAmbientDiffuseLighting(i, i.geometry.normal);
  }

  half3 avatar_computeAmbientSpecularLighting(avatar_FragmentInput i, half3 specular_contribution, half3 normal, half roughness) {
    half3 diffuse = half3(0.0, 0.0, 0.0);
    half3 specular = half3(0.0, 0.0, 0.0);
    half metallic = i.material.metallic;
    OvrGetUnityGlobalIllumination(i.lights[0].color, -i.lights[0].direction_normalized, i.geometry.positionInWorldSpace, i.geometry.worldViewDir,
      1.0, i.ambient_color, 1.0 - roughness, metallic, i.material.combined_occlusion, i.material.base_color, normal, specular_contribution, diffuse, specular);
    return specular;
  }

  avatar_AmbientLighting avatar_computeAmbientLighting(avatar_FragmentInput i, half3 specular_contribution) {
    avatar_AmbientLighting ambient;
    ambient.diffuse = avatar_computeAmbientDiffuseLighting(i);
    ambient.specular = avatar_computeAmbientSpecularLighting(i, specular_contribution,  i.geometry.normal, i.material.roughness);
    return ambient;
  }
#ifdef BLOCK_MATERIAL_SYSTEM
// Block Parameter Offsets for the FB_materials_skin extension
// [Extension currently has no parameters for all have been optimized out! Use extension offset 0 to activate.]
#endif // BLOCK_MATERIAL_SYSTEM
// hemisphere_normal_offset_utils.frag.glsl
 struct avatar_HemisphereNormalOffsets {
    half3 nn;
    half3 bb;
    half3 tt;
    half3 lv1;
    half3 lv2;
    half3 lv3;
};

 avatar_HemisphereNormalOffsets avatar_computeHemisphereNormalOffsets(avatar_FragmentInput i) {
    avatar_HemisphereNormalOffsets hno;
    half3 worldNormal = i.geometry.normal;
    half3 worldUp = half3(0.0, 1.0, 0.0);
    half3 worldTangent = cross(worldUp, worldNormal);
    half3 worldBitangent = cross(worldNormal, worldTangent);

    hno.nn = ((worldNormal * 0.7071));
    hno.tt = ((worldTangent * (0.7071 * 0.5)));
    hno.bb = ((worldBitangent * (0.7071 * 0.866)));

    hno.lv1 = (hno.nn + hno.tt * 2.0);
    hno.lv2 = (hno.nn + hno.bb - hno.tt);
    hno.lv3 = (hno.nn - hno.bb - hno.tt);
    return hno;
}
// eof hemisphere_normal_offset_utils.frag.glsl
#ifdef SSS_CURVATURE
half3 computeIndirectSubsurfaceContributionSH(avatar_FragmentInput i ) {

  half3 rotatedNormal  = i.geometry.normal;

  half3 color = half3(evalSHIrradianceSSS(i, rotatedNormal, i.geometry.curvature ));

  return color;
}

#endif

 half3 avatar_computeIndirectSubsurfaceContribution(avatar_FragmentInput i, avatar_HairMaterial hairMaterial , bool isAnyHair, bool isSkin)
{

#ifdef SSS_CURVATURE
#define ZH_SSS_AMBIENT_LIGHTING_COMBINED
#else
#undef ZH_SSS_AMBIENT_LIGHTING_COMBINED
#endif

#ifdef ZH_SSS_AMBIENT_LIGHTING_COMBINED
if (isSkin) {
    half3 color = computeIndirectSubsurfaceContributionSH(i );
    return color * getIntensity() * i.material.combined_occlusion;
} else  // submesh is hair
#endif
{

    half3 ibl_diffuse4 = half3(saturate(avatar_computeAmbientDiffuseLighting(i, i.geometry.normal)));

    ibl_diffuse4 *= i.material.combined_occlusion;
    return (ibl_diffuse4) * i.material.intensity;
}
}
    // https://knarkowicz.wordpress.com/2014/12/27/analytical-dfg-term-for-ibl/
    // This function approximates the DFG term for a BRDF using the uncorrelated Smith visibility function.
    // Our shader is using height-correlated Smith visibility, so this polynomial isn't exactly right
    // but it's close. In the near future we'd switch to a LUT computed with our BRDF or derive
    // a correct analytical approximation
     half3 avatar_computeSpecularEnvironmentBrdf( half3 specularColor, half gloss, half NdotV)
    {
        half x = gloss;
        half y = NdotV;
        half b1 = -0.1688;
        half b2 = 1.895;
        half b3 = 0.9903;
        half b4 = -4.853;
        half b5 = 8.404;
        half b6 = -5.069;
        half bias = saturate( min( b1 * x + b2 * x * x, b3 + b4 * y + b5 * y * y + b6 * y * y * y ) );
        half d0 = 0.6045;
        half d1 = 1.699;
        half d2 = -0.5228;
        half d3 = -3.603;
        half d4 = 1.404;
        half d5 = 0.1939;
        half d6 = 2.661;
        half delta = saturate( d0 + d1 * x + d2 * y + d3 * x * x + d4 * x * y + d5 * y * y + d6 * x * x * x );
        half scale = delta - bias;
        bias *= saturate( 50.0 * specularColor.y );
        return specularColor * scale + bias;
    }
// Lambertian diffuse implementation. May replace this with Burley diffuse BRDF later
 half3 avatar_computeDiffuseIrradiance(half3 directional_light_color, half NdotL, half3 DFGTerm) {
        // A colored tint appears when using the DFGTerm as a minfloat3 of RGB values, as a result of having fractional metallic
        // values. This is technically correct, but visually incorrect because the real world doesn't have
        // fractional metallic values, so it's distracting. To prevent tinting we're averaging the DFGTerm's RGB values
        // and using that value for energy conservation.
        half refractedLightValue = 1.0 - ((DFGTerm.x + DFGTerm.y + DFGTerm.z) / 3.0);
        half3 refractedLight = half3(refractedLightValue, refractedLightValue, refractedLightValue);

            NdotL = saturate(NdotL);
            return (NdotL * refractedLight * directional_light_color);

    }
half3 fresnelSchlickGGX(half VdotH, half3 f0) {

      // This adjustment is applied on platforms lacking shadow support which have relatively uncontrolled camera and lighting.
      // On these platforms distracting specular highlights can appear on surfaces facing away from the light (which would
      // be in shadow if self-shadowing was used). This is exacerbated by the Fresnel term, which is strongest in this case so we
      // clamp it here (admittedly non-physical but the lack of self-shadowing is even more non-physical). Note that on these
      // platforms we also apply an additional adjustment factor to the light intensity - see the definition of mainLightLoop().
      const half fresnelClampThreshold = 0.5;
      VdotH = max(VdotH, fresnelClampThreshold);

      half theta = 1.0 - VdotH;
      theta *= theta * theta * theta * theta;
      half3 fresnel = f0 + (half3(1.0, 1.0, 1.0) - f0) * theta;
      return fresnel;
}

//  Eric Heitz, Understanding Masking Shadow Function in Microfacet-Based BRDF
// https://jcgt.org/published/0003/02/03/paper.pdf
// This is the Smith height-correlated shadow-masking function for GGX
// This code is from the SIGGRAPH 2014 presentation "Moving Frostbite to Physically Based Rendering"
// This function computes the visibility term, which is the shadow-masking
// contribution divided by (4.0 * NdotL * NdotV).
half visibilityTermGGX(half NdotL, half alphaG, half NdotV) {
      // Using EPSILON here to prevent a divide by zero, as this function goes to infinity.

      // Additional optimization/approximation via
      // https://google.github.io/filament/Filament.html#citation-hammon17
      // We use a relatively large epsilon value here to avoid not just divides by zero but
      // also bright sparkles that occur on silhouette edges when dividing by small numbers.
      return 0.5 / max(0.05, (lerp((2.0 * NdotL * NdotV), (NdotL + NdotV), (alphaG))));

}

half microfacetDistributionGGX(half NdotHHalf, half alphaGHalf) {
      float NdotH = float(NdotHHalf);
      float alphaG = float(alphaGHalf);
      float alphaGPow2 = alphaG * alphaG;
      float denominator = NdotH * NdotH * (alphaGPow2 - 1.0) + 1.0;

      // Max with DENOMINATOR_EPSILON to make sure the denominator won't be zero. Can't use the global EPSILON becaue
      // its value is too big (0.001) which caused issues like T215164780.
      static const float DENOMINATOR_EPSILON = 1e-10;
      denominator = max(denominator, DENOMINATOR_EPSILON);

      // The divide by pi for the NDF is already in directional_light_color
      return half(alphaGPow2 / (denominator * denominator));
}

 half3 avatar_computeSpecular (half3 L, half3 normal, half3 viewDir,  half3 f0, half NdotL, half NdotV, half alphaG, half3 directional_light_color) {
      half3 H = normalize((L + viewDir));
      half VdotH = saturate(dot(viewDir, H));
      half NdotH = saturate(dot(normal, H));
      NdotL = saturate(NdotL);
      half3 fresnel = fresnelSchlickGGX(VdotH, f0);
      half alphaGPow2 = alphaG * alphaG;
      half3 NxH = cross(normal, H);
      half distribution = microfacetDistributionGGX(1.0 - dot(NxH, NxH), alphaG);
      const half minfloating_pt_max = 55500.0;
      distribution = min(minfloating_pt_max, distribution);
      half visibilityTerm = visibilityTermGGX(NdotL, alphaG, NdotV);
      half3 specTerm = fresnel * distribution * visibilityTerm;
      return specTerm * NdotL * directional_light_color;
}
#ifdef BLOCK_MATERIAL_SYSTEM
// Block Parameter Offsets for the FB_materials_eye extension
// [Extension currently has no parameters for all have been optimized out! Use extension offset 0 to activate.]
#endif // BLOCK_MATERIAL_SYSTEM

void avatar_calculateEyeGlint(half3 V, avatar_FragmentInput i, inout half3 punctualSpecular, inout half3 glintSpecular ) {
    half3 direction = half3(u_EyeGlintLeftDirectionOffset);
    if(isRightEye(i.geometry.ormt.w)) {
        direction = half3(u_EyeGlintRightDirectionOffset);
    }
    half3 worldUp = half3(0.0, 1.0, 0.0);
    V += (direction.y * worldUp) + direction.x * cross(V, worldUp);
    half3 H = normalize(V);

    half unperturbedNdotH = half((dot(i.geometry.unperturbedNormal, H)));
    half intensityNg = pow(saturate(unperturbedNdotH), half(u_EyeGlintExponential)) * half(u_EyeGlintIntensity);
    glintSpecular += intensityNg * half3(getEyeGlintLightColor());
}
 half3 avatar_addRimLight(avatar_FragmentInput i, half3 rimLight, half aoIntensity ){
    half angle = atan2((half(i.geometry.normal.x)), (half(i.geometry.normal.y)));
    half gradient = angle / M_PI_2_HALF + 0.5;
    half multiplier = smoothstep(half(u_RimLightStartPosition), half(u_RimLightStartPosition) + half(u_RimLightTransition), gradient);
    multiplier *= smoothstep(half(u_RimLightEndPosition), half(u_RimLightEndPosition) - half(u_RimLightTransition), gradient);
    half bias = max(half(u_RimLightBias), EPSILON_HALF);
    half fresnel = pow(1.0 - saturate(half(computeNdotV(i.geometry.normal, i.geometry.worldViewDir))), 1.0/bias);
    fresnel *= multiplier;
    fresnel *= half(u_RimLightIntensity);

    fresnel *= aoIntensity;

    half3 rimLightColor = half3(u_RimLightColor);
    // desaturate the base_color by taking the square root
    rimLightColor = sqrt(i.material.base_color);
    return  rimLightColor * fresnel * rimLight ;

}
#ifdef BLOCK_MATERIAL_SYSTEM
// Block Parameter Offsets for the FB_materials_hair extension
static const int OFFSET_HAIR_ANISOTROPIC_INTENSITY = 0;
static const int OFFSET_HAIR_COLOR_ROUGHNESS = 1;
static const int OFFSET_HAIR_DIFFUSED_INTENSITY = 2;
static const int OFFSET_HAIR_ROUGHNESS = 3;
static const int OFFSET_HAIR_SCATTER_INTENSITY = 4;
static const int OFFSET_HAIR_SPECULAR_COLOR_FACTOR = 5;
static const int OFFSET_HAIR_SPECULAR_COLOR_INTENSITY = 8;
static const int OFFSET_HAIR_SPECULAR_COLOR_OFFSET = 9;
static const int OFFSET_HAIR_SPECULAR_GLINT = 10;
static const int OFFSET_HAIR_SPECULAR_NORMAL_INTENSITY = 11;
static const int OFFSET_HAIR_SPECULAR_SHIFT_INTENSITY = 12;
static const int OFFSET_HAIR_SPECULAR_WHITE_INTENSITY = 13;
static const int OFFSET_HAIR_SUBSURFACE_COLOR = 14;
#endif // BLOCK_MATERIAL_SYSTEM

void updateHairMaterial(inout avatar_FragmentInput i, inout avatar_HairMaterial hairMaterial, half4 ormtSample) {
  hairMaterial.ao_intensity = ormtSample.r;

  hairMaterial.flow_sample = i.geometry.ormt.g;

  half flowAngleOffset = 0.25;

  hairMaterial.flow_angle = ((1.0 - hairMaterial.flow_sample) - flowAngleOffset) * M_PI_2_HALF;
  hairMaterial.shift = half(ormtSample.b);
  hairMaterial.blend = clamp(half(ormtSample.a) * 2.0, 0.0, 1.0);
  hairMaterial.aniso_blend = clamp((half(ormtSample.a) - 0.5) * 2.0, 0.0, 1.0);

  i.material.roughness = 0.40;
  i.material.metallic = 0.0;
  i.material.properties_occlusion = 1.0;

  i.geometry.normal = (lerp((i.geometry.unperturbedNormal), (i.geometry.normal), (half(hairMaterial.blend))));

}

 half avatar_computeSpecularHighlight(half anisotropicIntensity, half roughness, half3 L, half3 E, half3 N, half3 tangent, half3 bitangent, half offset) {
    half3 H = E + L;
    half spec = 0.0;
    half kexp = 1.0 / (roughness * roughness + EPSILON_HALF);
    // "Bend" the normal towards the bitangent
    N = normalize(N +  bitangent * offset);
    half3 anisotropicH = normalize(H - dot(H, tangent) * tangent);
    H = normalize((lerp((normalize(H)), (anisotropicH), (anisotropicIntensity))));
    half kspec = dot(N, H);
    spec = pow(max(0.0, kspec), kexp);
    return half(spec);
  }

  half3 avatar_getHairTangent(avatar_FragmentInput i, inout avatar_HairMaterial hairMaterial) {
    half2 flow = half2(cos(hairMaterial.flow_angle), sin(hairMaterial.flow_angle));
    half3 hairTangent = i.geometry.tangent.xyz * flow.x + i.geometry.bitangent * flow.y;
    return normalize(hairTangent);
  }

  half3 avatar_computeHairSpecular(avatar_FragmentInput i, inout avatar_HairMaterial hairMaterial, half3 lightVector_normalized, half cosFactor, half3x3 hairCoordinateSystem, half anisotropicBlend ) {
    half3 normal = hairCoordinateSystem[0];
    half3 hairTangent = hairCoordinateSystem[1];
    half3 bitangent = hairCoordinateSystem[2];
    half3 E = i.geometry.worldViewDir;
    half3 L = half3(lightVector_normalized);
    half anisotropy = (lerp((0.0), (hairMaterial.anisotropic_intensity), (anisotropicBlend)));
    half localOffset = hairMaterial.specular_shift_intensity * (hairMaterial.shift - 0.5) * anisotropicBlend;
    half specWhite = avatar_computeSpecularHighlight(anisotropy, hairMaterial.specular_white_roughness, L, E, normal,
                    bitangent, hairTangent, localOffset) *  hairMaterial.specular_white_intensity;

    half specColor = avatar_computeSpecularHighlight(anisotropy,  hairMaterial.specular_color_roughness, L, E, normal,
                    bitangent, hairTangent, hairMaterial.specular_color_offset + localOffset) * hairMaterial.specular_color_intensity;
    half3 hairSpec = half3(specWhite, specWhite, specWhite) + (hairMaterial.specular_color_factor * specColor);
    return hairSpec * (hairMaterial.ao_intensity * cosFactor);
  }

   half3 avatar_blendPunctualSpecularWithHair(half3 punctualSpec, half3 hairPunctualSpec, half hairBlend) {
    return (lerp((punctualSpec), (hairPunctualSpec), (hairBlend)));
  }
// Start of include: cel.frag.glsl
// zero_struct_utils.frag.glsl
avatar_Geometry avatar_zeroGeometry() {
  avatar_Geometry geometry;
  geometry.positionInWorldSpace = half3(0.0, 0.0, 0.0);
  geometry.positionInClipSpace = half3(0.0, 0.0, 0.0);
  geometry.normal = half3(0.0, 0.0, 0.0);
  geometry.unperturbedNormal = half3(0.0, 0.0, 0.0);
  geometry.tangent = half3(0.0, 0.0, 0.0);
  geometry.bitangent = half3(0.0, 0.0, 0.0);
  geometry.texcoord_0 = half2(0.0, 0.0);

  geometry.color = half4(0.0, 0.0, 0.0, 0.0);
  geometry.ormt = half4(0.0, 0.0, 0.0, 0.0);
  geometry.worldViewDir = half3(0.0, 0.0, 0.0);
  geometry.curvature = 0.0;
  return geometry;
}

avatar_HairMaterial avatar_zeroHairMaterial() {
  avatar_HairMaterial material;
  material.subsurface_color = half3(0.0, 0.0, 0.0);
  material.specular_color_factor = half3(0.0, 0.0, 0.0);
  material.specular_shift_intensity = 0.0;
  material.specular_white_intensity = 0.0;
  material.specular_white_roughness = 0.0;
  material.specular_color_intensity = 0.0;
  material.specular_color_offset = 0.0;
  material.specular_color_roughness = 0.0;
  material.anisotropic_intensity = 0.0;
  material.normal_intensity = 0.0;
  material.ao_intensity = 0.0;
  material.flow_sample = 0.0;
  material.flow_angle = 0.0;
  material.shift = 0.0;
  material.blend = 0.0;
  material.aniso_blend = 0.0;
  return material;
}

avatar_Material avatar_zeroMaterial() {
  avatar_Material material;
  material.base_color = half3(0.0, 0.0, 0.0);
  material.alpha = 0.0;
  material.alpha_coverage = 1.0;
  material.metallic = 0.0;

  material.properties_occlusion = 1.0;
  material.screenspace_occlusion = 1.0;
  material.combined_occlusion = 1.0;
  material.roughness = 0.0;
  material.thickness = 0.0;
  material.IBLBrdf = half3(0.0, 0.0, 0.0);
  material.f0 = half3(0.0, 0.0, 0.0);
  material.f90 = 0.0;
  material.exposure = 0.0;
  material.intensity = 1.0;

#ifdef BLOCK_MATERIAL_SYSTEM
  material.submesh_index = 0;
#endif

  return material;
}

avatar_Light avatar_zeroLight() {
  avatar_Light light;
  light.direction_normalized = half3(0.0, 0.0, 1.0);
  light.color = half3(0.0, 0.0, 0.0);
  light.intensity = 0.0;

  light.areaLightAngleSin = 0.0;
  light.directional_light_color = half3(0.0, 0.0, 0.0);
  return light;
}

avatar_FragmentInput avatar_zeroFragmentInput(int maxLightCount) {
  avatar_FragmentInput i;

  i.geometry = avatar_zeroGeometry();
  i.material = avatar_zeroMaterial();
  i.lightsCount = 1;
  #if MAX_LIGHT_COUNT > 1
  for(int idx = 0; idx < maxLightCount; idx++) {
     i.lights[idx] = avatar_zeroLight();
  }
  #else
    i.lights[0] = avatar_zeroLight();
  #endif
  i.ambient_color = half3(0.0, 0.0, 0.0);
  i.SHCoeff0 = half3(0.0, 0.0, 0.0);
  i.SHCoeff1 = half3(0.0, 0.0, 0.0);
  i.SHCoeff2 = half3(0.0, 0.0, 0.0);
  i.SHCoeff3 = half3(0.0, 0.0, 0.0);
  i.SHCoeff4 = half3(0.0, 0.0, 0.0);
  i.SHCoeff5 = half3(0.0, 0.0, 0.0);
  i.SHCoeff6 = half3(0.0, 0.0, 0.0);
  i.SHCoeff7 = half3(0.0, 0.0, 0.0);
  i.SHCoeff8 = half3(0.0, 0.0, 0.0);
  return i;
}

avatar_FragmentOutput avatar_zeroFragmentOutput() {
  avatar_FragmentOutput o;

  o.color = half4(0.0, 0.0, 0.0,0.0);
  o.alphaCoverage = 255u;

  return o;
}

// eof zero_struct_utils.frag.glsl
void frag_Fragment_main () {

  avatar_FragmentInput i = avatar_zeroFragmentInput(MAX_LIGHT_COUNT);

  avatar_FragmentOutput o = avatar_zeroFragmentOutput();

  i.lightsCount = getLightCount();
  i.material.intensity = max(getIntensity(), EPSILON_HALF);
  i.material.exposure = getExposure();

  fillInLightData(i);

  i.geometry.texcoord_0 = half2(getTexcoord0());
  i.geometry.unperturbedNormal = getUnperturbedNormal();
  i.geometry.tangent = getTangent();
  i.geometry.bitangent = normalize(cross(i.geometry.unperturbedNormal, i.geometry.tangent));
  i.geometry.normal = i.geometry.unperturbedNormal;
#ifdef HAS_NORMAL_MAP_ON
  i.geometry.normal = getShadingNormal(i.geometry.texcoord_0, i.geometry.tangent, i.geometry.bitangent, i.geometry.unperturbedNormal);
#endif
  i.geometry.worldViewDir = getWorldViewDir();
  half4 baseColor = sampleBaseColor(i.geometry.texcoord_0, i.geometry.color);
  i.material.base_color = baseColor.rgb;

  // Allow the integrating application to do extra operations on the fragment shader input:
  AppSpecificPreManipulation(i);

  half3 finalColor = half3(0.0, 0.0, 0.0);
  half numMatCaps = 4.0;

  // Determine matcap index to use based on ambient diffuse lighting
  half3 ambientDiffuse = avatar_computeAmbientDiffuseLighting(i);
  half luminanceVal = luminance(ambientDiffuse);
  half matCapIndex = numMatCaps - 1.0 - (step(0.25, luminanceVal) + step(0.5, luminanceVal) + step(0.75, luminanceVal));

  // Apply matcap sampled with normal and view vectors for cel shadow bands
  half3 refVector = half3(0.0, 1.0, 0.0);
  half3 orthogonalVector = cross(i.geometry.worldViewDir, refVector);
  half2 matCapUV = half2((dot(orthogonalVector, i.geometry.normal) * 0.5 + 0.5 + matCapIndex) / numMatCaps, -dot(refVector, i.geometry.normal) * 0.5 + 0.5);
  half4 matCap = sampleMetallicRoughness(matCapUV, i.geometry.ormt);
  finalColor = matCap.rgb * i.material.base_color.rgb;

  half3 preTonemap = finalColor;

  // compute the alpha coverage at the end to match the alpha for this pixel

  o.alphaCoverage = avatar_calculateAlphaCoverage(i, i.geometry.positionInClipSpace);

  o.color.rgb = half3(finalColor);
  o.color.a = 1.0;

  // Allow the integrating application to do extra operations
  AppSpecificPostManipulation(i, o);

  // color space correction:
  // In Unity the final output is governed by UNITY_COLORSPACE_GAMMA, so call this function
  // If the integrating engine does not need this, we can just return the rgb from the input,
  // but this is the unity.frag.sca, so We assume that it is being used.
  finalColor.rgb = ConvertOutputColorSpaceFromLinear(o.color.rgb);
  _output_FragColor = half4(finalColor, o.color.a);

}

// End of include: cel.frag.glsl
FragmentOutput Fragment_main(VertexToFragment stage_input)
{
  v_Vertex = stage_input.v_Vertex;
  v_WorldPos = stage_input.v_WorldPos;
  v_Normal = stage_input.v_Normal;
  v_Tangent = stage_input.v_Tangent;
  v_UVCoord1 = stage_input.v_UVCoord1;
  v_UVCoord2 = stage_input.v_UVCoord2;
  v_UVCoord3 = stage_input.v_UVCoord3;
  v_Color = stage_input.v_Color;
  v_ORMT = stage_input.v_ORMT;
  v_SH = stage_input.v_SH;
  frag_Fragment_main();
  FragmentOutput stage_output;
  stage_output._output_FragColor = _output_FragColor;
  return stage_output;
}
