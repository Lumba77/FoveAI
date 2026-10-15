#ifndef OVR_AVATAR_MOTION_VECTORS_COMMON_INCLUDED
#define OVR_AVATAR_MOTION_VECTORS_COMMON_INCLUDED

// This is a copy of "MotionVectorsCommon.hlsl" found in the Unity 6 URP fork for Application Spacewarp
// with some different function names to avoid collision.
// Yes, it isn't great to have copies floating around, but we can't guarantee
// that adopters of the Meta Avatars SDK will necessarily have the
// Unity 6 URP fork for Application Spacewarp installed (yet)

#if UNITY_VERSION >= 60000000

#include "Packages/com.unity.render-pipelines.core/ShaderLibrary/FoveatedRendering.hlsl"

// This is required to avoid artifacts ("gaps" in the _MotionVectorTexture) on some platform
void OvrAvatarApplyMotionVectorZBias(inout float4 positionCS)
{
    #if defined(UNITY_REVERSED_Z)
    positionCS.z -= unity_MotionVectorsParams.z * positionCS.w;
    #else
    positionCS.z += unity_MotionVectorsParams.z * positionCS.w;
    #endif
}

float2 OvrAvatarCalcNdcMotionVectorFromCsPositions(float4 posCS, float4 prevPosCS)
{
    // Note: unity_MotionVectorsParams.y is 0 is forceNoMotion is enabled
    bool forceNoMotion = unity_MotionVectorsParams.y == 0.0;
    if (forceNoMotion)
        return float2(0.0, 0.0);

    // Non-uniform raster needs to keep the posNDC values in float to avoid additional conversions
    // since uv remap functions use floats
    float2 posNDC = posCS.xy * rcp(posCS.w);
    float2 prevPosNDC = prevPosCS.xy * rcp(prevPosCS.w);

    float2 velocity;
    #if defined(SUPPORTS_FOVEATED_RENDERING_NON_UNIFORM_RASTER)
    UNITY_BRANCH if (_FOVEATED_RENDERING_NON_UNIFORM_RASTER)
    {
        // Convert velocity from NDC space (-1..1) to screen UV 0..1 space since FoveatedRendering remap needs that range.
        float2 posUV = RemapFoveatedRenderingResolve(posNDC * 0.5 + 0.5);
        float2 prevPosUV = RemapFoveatedRenderingPrevFrameLinearToNonUniform(prevPosNDC * 0.5 + 0.5);

        // Calculate forward velocity
        velocity = (posUV - prevPosUV);
        #if UNITY_UV_STARTS_AT_TOP
        velocity.y = -velocity.y;
        #endif
    }
    else
    #endif
    {
        // Calculate forward velocity
        velocity = (posNDC.xy - prevPosNDC.xy);
        #if UNITY_UV_STARTS_AT_TOP
        velocity.y = -velocity.y;
        #endif

        // Convert velocity from NDC space (-1..1) to UV 0..1 space
        // Note: It doesn't mean we don't have negative values, we store negative or positive offset in UV space.
        // Note: ((posNDC * 0.5 + 0.5) - (prevPosNDC * 0.5 + 0.5)) = (velocity * 0.5)
        velocity.xy *= 0.5;
    }

    return velocity;
}

// Same as CalcNdcMotionVectorFromCsPositions but returns vec3 ndc space motion vector.
// Also Application SpaceWarp does not support non-uniform foveated rendering so the relevant foveated rendering code is not in this variant.
float3 OvrAvatarCalcAswNdcMotionVectorFromCsPositions(float4 posCS, float4 prevPosCS)
{
    float3 posNDC = posCS.xyz * rcp(posCS.w);
    float3 prevPosNDC = prevPosCS.xyz * rcp(prevPosCS.w);

    float3 velocity;
    // Calculate forward velocity
    velocity = (posNDC.xyz - prevPosNDC.xyz);

    return velocity;
}

#endif // #if UNITY_VERSION >= 60000000

#endif
