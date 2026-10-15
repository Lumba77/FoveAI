Shader "Avatar/Meta"
{
    Properties
    {
        // NOTE: This texture can be visualized in the Unity editor, just expand in inspector and manually change "Dimension" to "2D" on top line
        u_AttributeTexture("Vertex Attribute map", 3D) = "white" {}

        u_PropertyTexBias("Property Mip Bias (-1 to 1)", float) = 0

        [NoScaleOffset] u_NormalSampler("Normal map", 2D) = "bump" {}
        u_NormalScale("Normal map scale", Float) = 1.0
        u_NormalUVSet("Normal UV Set", Int) = 0

        [NoScaleOffset] u_EmissiveSampler("Emissive map", 2D) = "black" {}
        u_EmissiveSet("Emissive UV Set", Int) = 0
        u_EmissiveFactor("Emissive factor", Color) = (1, 1, 1, 1)

        [NoScaleOffset] u_OcclusionSampler("Occlusion map", 2D) = "white" {}
        u_OcclusionSet("Occlusion UV Set", Int) = 0
        u_OcclusionStrength("Occlusion scale", Float) = 1.0

        [NoScaleOffset] u_BaseColorSampler("Base Color", 2D) = "white" {}
        u_BaseColorUVSet("Base Color UV Set", Int) = 0

        u_BaseColorFactor("Base Color factor", Color) = (1, 1, 1, 1)

        [Header(Metallic Roughness Model)]

        [NoScaleOffset]  u_MetallicRoughnessSampler("Metallic Roughness", 2D) = "white" {}
        u_MetallicRoughnessUVSet("Metallic Roughness UV Set", Int) = 0

        u_MetallicFactor("Metallic Factor", Range(0, 2)) = 1.0
        u_RoughnessFactor("Roughness Factor", Range(0, 2)) = 1.0
        u_F0Factor("F0 Factor", Range(0, 2)) = 1.0
        u_OcclusionStrength("Occlusion Strength", Range(0, 2)) = 1.0
        u_ThicknessFactor("Thickness Factor", Range(0, 2)) = 1.0

        u_Exposure("Material Exposure", Range(0, 2)) = 1.0


        [Space]
        [Header(Variants)]

        [KeywordEnum(2 Light, 2 Standard, 2 Experimental, 1 Light, 1 Standard)] Style("Style", Float) = -1
        // The following proxies only serve to visualize the features for the style above. Real assignment happens in app_variants.hlsl.
        [KeywordProxy(EYE_GLINTS_ON, STYLE_1_LIGHT, STYLE_1_STANDARD, STYLE_2_STANDARD, STYLE_2_EXPERIMENTAL)] EyeGlints("Eye Glints", Float) = 1
        [KeywordProxy(SKIN_ON, STYLE_1_LIGHT, STYLE_1_STANDARD, STYLE_2_STANDARD, STYLE_2_EXPERIMENTAL)] Skin("Skin", Float) = 1
        [KeywordProxy(ENABLE_HAIR_ON, STYLE_1_STANDARD, STYLE_2_STANDARD, STYLE_2_EXPERIMENTAL)] EnableHair("Hair", Float) = 1
        [KeywordProxy(ENABLE_RIM_LIGHT_ON, STYLE_2_STANDARD, STYLE_2_EXPERIMENTAL)] EnableRimLight("Rim Light", Float) = 1
        [KeywordProxy(HAS_NORMAL_MAP_ON, STYLE_1_STANDARD, STYLE_2_STANDARD, STYLE_2_EXPERIMENTAL)] HasNormalMap("Normal Map", Float) = 1

        // DEBUG_MODES: Uncomment to use Debug modes, do not create a multi_compile for this, as it takes up permutations and memory. Instead static branch on DEBUG_NONE and the value of floating point uniform "Debug".
        [KeywordEnumWithToggle(DEBUG_MODE_ON, None, BaseColorSRGB, BaseColorLinear, Alpha, Occlusion, Metallic, Roughness, Thickness, Normal, NormalGeometry, NormalWorld, Tangent, Bitangent, F0, EmissiveSrgb, EmissiveLinear, SpecularSrgb, DiffuseSrgb, ClearcoatSrgb, SheenSrgb, TransmissionSrgb, Ambient, AmbientDiffuse, AmbientSpecular, IBLBrdf, Punctual, PunctualDiffuse, PunctualSpecular, Anisotropy, AnisotropyDirection, AnisotropyTangent, AnisotropyBitangent, View, SubsurfaceScattering, AmbientOcclusion, SSSCurvature, SSSCurvatureLUT, SSSCurvatureLUTUV, TexCoord0, TexCoord1, SHIrradiance, Submeshes, MaterialType, Shadows)] Debug("Debug Render", Float) = 0

        // MATERIAL_MODES: Uncomment to use Material modes, must match the multi_compile defined below
        [KeywordEnum(Texture, Vertex)] Material_Mode("Material Mode", Float) = 0

        // Cull mode (Off, Front, Back)
        [Enum(UnityEngine.Rendering.CullMode)] _Cull("Cull", Float) = 2

        [Space]
        [Header(Additional parameters)]

        [ShowIfKeyword(SKIN_ON)]
        u_SubsurfaceColor("Skin Sub-Surface Color", Color) = (1, 1, 1, 1)
        [ShowIfKeyword(SKIN_ON)]
        u_SkinORMFactor("Skin-only ORM Factor", Vector) = (1, 1, 1)

        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairSubsurfaceColor("Hair Sub-Surface Color", Color) = (1, 1, 1, 1)
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairSpecularColorFactor("Hair Specular Color Factor", Color) = (1, 1, 1, 1)
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairSpecularShiftIntensity("Hair Specular Shift Intensity", Range(-1,1)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairSpecularWhiteIntensity("Hair Specular White Intensity", Range(0,10)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairSpecularColorIntensity("Hair Specular Color Intensity", Range(0,10)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairSpecularColorOffset("Hair Specular Color Offset", Range(-1,1)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairRoughness("Hair Roughness", Range(0,1)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairColorRoughness("Hair Color Roughness", Range(0,1)) = .4
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairAnisotropicIntensity("Hair Anistropic Intensity", Range(-1,1)) = .5
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairSpecularNormalIntensity("Hair Specular Normal Intensity", Range(0,1)) = 1.
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_HairDiffusedIntensity("Hair Diffuse Intensity", Range(0,10)) = .25

        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairSubsurfaceColor("Facial Hair Sub-Surface Color", Color) = (1, 1, 1, 1)
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairSpecularColorFactor("Facial Hair Specular Color Factor", Color) = (1, 1, 1, 1)
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairSpecularShiftIntensity("Facial Hair Specular Shift Intensity", Range(-1,1)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairSpecularWhiteIntensity("Facial Hair Specular White Intensity", Range(0,10)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairSpecularColorIntensity("Facial Hair Specular Color Intensity", Range(0,10)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairSpecularColorOffset("Facial Hair Specular Color Offset", Range(-1,1)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairRoughness("Facial Hair Roughness", Range(0,1)) = .2
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairColorRoughness("Facial Hair Color Roughness", Range(0,1)) = .4
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairAnisotropicIntensity("Facial Hair Anistropic Intensity", Range(-1,1)) = .5
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairSpecularNormalIntensity("Facial Hair Specular Normal Intensity", Range(0,1)) = 1.
        [ShowIfKeyword(ENABLE_HAIR_ON)]
        u_FacialHairDiffusedIntensity("Facial Hair Diffuse Intensity", Range(0,10)) = .25

        [ShowIfKeyword(ENABLE_RIM_LIGHT_ON)]
        u_RimLightIntensity("Rim Light Intensity", Range(0,1)) = 0.0
        [ShowIfKeyword(ENABLE_RIM_LIGHT_ON)]
        u_RimLightBias("Rim Light Bias", Range(0.0,1.0)) = 0.5
        [ShowIfKeyword(ENABLE_RIM_LIGHT_ON)]
        u_RimLightColor("Rim Light Color", Color) = (1,1,1)
        [ShowIfKeyword(ENABLE_RIM_LIGHT_ON)]
        u_RimLightTransition("Rim Light Transition", Range(0,0.2)) = 0.2
        [ShowIfKeyword(ENABLE_RIM_LIGHT_ON)]
        u_RimLightStartPosition("Rim Light Start Position", Range(0,1)) = 0.5
        [ShowIfKeyword(ENABLE_RIM_LIGHT_ON)]
        u_RimLightEndPosition("Rim Light End Position", Range(0,1)) = 0.5

        [ShowIfKeyword(EYE_GLINTS_ON)]
        u_EyeGlintFactor("Eye Glint Factor", Range(0, 4.0)) = 2.0
        [ShowIfKeyword(EYE_GLINTS_ON)]
        u_EyeGlintColorFactor("Eye Glint Color Factor", Range(0, 1.0)) = 0.5


        // These should not exist here, since they should be in global shader scope and handeled by an external manager:
        //
        //u_DiffuseEnvSampler("IBL Diffuse Cubemap Texture", Cube) = "white" {}
        //u_MipCount("IBL Diffuse Texture Mip Count", Int) = 10
        //u_SpecularEnvSampler ("IBL Specular Cubemap Texture", Cube) = "white" {}
        //u_brdfLUT ("BRDF LUT Texture", 2D) = "Assets/Oculus/Avatar2/Example/Scenes/BRDF_LUT" {}
    }

    // Universal Render Pipeline (URP), shader target 5.0
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" }
        Pass
        {
            PackageRequirements
            {
              "com.unity.render-pipelines.universal" : "10.1.0"
            }
            Tags { "LightMode" = "UniversalForward" }

            HLSLPROGRAM
            #pragma editor_sync_compilation // avoid showing the "invalid" teal Unity shader during loading

            #pragma vertex Vertex_main_instancing
            #pragma fragment Fragment_main

            // 5.0 required for SV_Coverage, 3.5 required for SV_VertexID
            #pragma target 5.0

            #pragma shader_feature UNITY_PIPELINE_URP      // Works before Unity 2021
			      #define UNITY_PIPELINE_URP      // Works after Unity 2021

			      #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            #include_with_pragmas "app_specific/app_variants.hlsl"   // replace this with an app_specific declarations file
            #include "app_specific/app_declarations.hlsl"   // replace this with an app_specific declarations file
            #include_with_pragmas "MetaAvatarCore.hlsl"
            #include "app_specific/app_functions.hlsl"   // replace this with an app_specific functions file
            ENDHLSL
        }

        Pass
        {
            Name "MotionVectors"
            Tags{ "LightMode" = "MotionVectors"}
            Tags { "RenderType" = "Opaque" }

            HLSLPROGRAM

            #pragma target 3.5 // necessary for use of SV_VertexID
            #pragma multi_compile _ APPLICATION_SPACE_WARP_MOTION
            #pragma vertex OvrMotionVectorsVertProgram
            #pragma fragment OvrMotionVectorsFragProgram
            #include "../../../ShaderUtils/OvrAvatarMotionVectorsCore.hlsl"

            ENDHLSL
        }

        Pass
        {
            Name "XRMotionVectors"
            Tags { "LightMode" = "XRMotionVectors" }
            ColorMask RGBA

            // Stencil write for obj motion pixels
            Stencil
            {
                WriteMask 1
                Ref 1
                Comp Always
                Pass Replace
            }

            HLSLPROGRAM
            #define APPLICATION_SPACE_WARP_MOTION 1
            #pragma target 3.5 // necessary for use of SV_VertexID
            #pragma vertex OvrMotionVectorsVertProgram
            #pragma fragment OvrMotionVectorsFragProgram
            #include "../../../ShaderUtils/OvrAvatarMotionVectorsCore.hlsl"

            ENDHLSL
        }
    }

    // Unity Built-in Render Pipeline, shader target 5.0
    SubShader
    {
        Tags { "RenderPipeline" = "" "RenderType" = "Opaque" }
        LOD 100
        Cull[_Cull]

        // Single Light
        Pass
        {
            Tags { "LightMode" = "ForwardBase" }

            CGPROGRAM
            #pragma editor_sync_compilation // avoid showing the "invalid" teal Unity shader during loading

            #pragma vertex Vertex_main_instancing
            #pragma fragment Fragment_main

            // 5.0 required for SV_Coverage, 3.5 required for SV_VertexID
            #pragma target 5.0
            #include_with_pragmas "app_specific/app_variants.hlsl"   // replace this with an app_specific declarations file
            #include "app_specific/app_declarations.hlsl"   // replace this with an app_specific declarations file
            #include_with_pragmas "MetaAvatarCore.hlsl"
            #include "app_specific/app_functions.hlsl"   // replace this with an app_specific functions file
            ENDCG
        }

        // Up to 4 Additive Lights
        Pass
        {
            Tags { "LightMode" = "ForwardAdd" }
            Blend One One
            ZWrite Off

            CGPROGRAM
            #pragma editor_sync_compilation // avoid showing the "invalid" teal Unity shader during loading

            #pragma vertex Vertex_main_instancing
            #pragma fragment Fragment_main

            // 5.0 required for SV_Coverage, 3.5 required for SV_VertexID
            #pragma target 5.0
            #include_with_pragmas "app_specific/app_variants.hlsl"   // replace this with an app_specific declarations file
            #include "app_specific/app_declarations.hlsl"   // replace this with an app_specific declarations file
            #include_with_pragmas "MetaAvatarCore.hlsl"
            #include "app_specific/app_functions.hlsl"   // replace this with an app_specific functions file
            ENDCG
        }
    }

    // Universal Render Pipeline (URP), shader target 3.5 compatibility mode
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" }
        Pass
        {
            PackageRequirements
            {
              "com.unity.render-pipelines.universal" : "10.1.0"
            }
            Tags { "LightMode" = "UniversalForward" }

            HLSLPROGRAM
            #pragma editor_sync_compilation // avoid showing the "invalid" teal Unity shader during loading

            #pragma vertex Vertex_main_instancing
            #pragma fragment Fragment_main

            #pragma target 3.5

            #pragma shader_feature UNITY_PIPELINE_URP      // Works before Unity 2021
            #define UNITY_PIPELINE_URP      // Works after Unity 2021

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            #include_with_pragmas "app_specific/app_variants.hlsl"   // replace this with an app_specific declarations file
            #include "app_specific/app_declarations.hlsl"   // replace this with an app_specific declarations file
            #include_with_pragmas "MetaAvatarCore.hlsl"
            #include "app_specific/app_functions.hlsl"   // replace this with an app_specific functions file
            ENDHLSL
        }

        Pass
        {
            Name "MotionVectors"
            Tags{ "LightMode" = "MotionVectors"}
            Tags { "RenderType" = "Opaque" }

            HLSLPROGRAM

            #pragma target 3.5 // necessary for use of SV_VertexID
            #pragma multi_compile _ APPLICATION_SPACE_WARP_MOTION
            #pragma vertex OvrMotionVectorsVertProgram
            #pragma fragment OvrMotionVectorsFragProgram
            #include "../../../ShaderUtils/OvrAvatarMotionVectorsCore.hlsl"

            ENDHLSL
        }

        Pass
        {
            Name "XRMotionVectors"
            Tags { "LightMode" = "XRMotionVectors" }
            ColorMask RGBA

            // Stencil write for obj motion pixels
            Stencil
            {
                WriteMask 1
                Ref 1
                Comp Always
                Pass Replace
            }

            HLSLPROGRAM
            #define APPLICATION_SPACE_WARP_MOTION 1
            #pragma target 3.5 // necessary for use of SV_VertexID
            #pragma vertex OvrMotionVectorsVertProgram
            #pragma fragment OvrMotionVectorsFragProgram
            #include "../../../ShaderUtils/OvrAvatarMotionVectorsCore.hlsl"

            ENDHLSL
        }
    }

    // Unity Built-in Render Pipeline, shader target 3.5 compatibility mode
    SubShader
    {
        Tags { "RenderPipeline" = "" "RenderType" = "Opaque" }
        LOD 100
        Cull[_Cull]

        // Single Light
        Pass
        {
            Tags { "LightMode" = "ForwardBase" }

            CGPROGRAM
            #pragma editor_sync_compilation // avoid showing the "invalid" teal Unity shader during loading

            #pragma vertex Vertex_main_instancing
            #pragma fragment Fragment_main

            #pragma target 3.5
            #include_with_pragmas "app_specific/app_variants.hlsl"   // replace this with an app_specific declarations file
            #include "app_specific/app_declarations.hlsl"   // replace this with an app_specific declarations file
            #include_with_pragmas "MetaAvatarCore.hlsl"
            #include "app_specific/app_functions.hlsl"   // replace this with an app_specific functions file
            ENDCG
        }

        // Up to 4 Additive Lights
        Pass
        {
            Tags { "LightMode" = "ForwardAdd" }
            Blend One One
            ZWrite Off

            CGPROGRAM
            #pragma editor_sync_compilation // avoid showing the "invalid" teal Unity shader during loading

            #pragma vertex Vertex_main_instancing
            #pragma fragment Fragment_main

            #pragma target 3.5
            #include_with_pragmas "app_specific/app_variants.hlsl"   // replace this with an app_specific declarations file
            #include "app_specific/app_declarations.hlsl"   // replace this with an app_specific declarations file
            #include_with_pragmas "MetaAvatarCore.hlsl"
            #include "app_specific/app_functions.hlsl"   // replace this with an app_specific functions file
            ENDCG
        }
    }
}
