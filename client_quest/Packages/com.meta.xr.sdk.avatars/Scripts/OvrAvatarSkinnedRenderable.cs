/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * Licensed under the Oculus SDK License Agreement (the "License");
 * you may not use the Oculus SDK except in compliance with the License,
 * which is provided at the time of installation or download, or which
 * otherwise accompanies this software in either electronic or hard copy form.
 *
 * You may obtain a copy of the License at
 *
 * https://developer.oculus.com/licenses/oculussdk/
 *
 * Unless required by applicable law or agreed to in writing, the Oculus SDK
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


#nullable disable

#define OVR_AVATAR_PRIMITIVE_HACK_BOUNDING_BOX

using System;
using Oculus.Avatar2;
using UnityEngine;
using UnityEngine.Profiling;

/// @file OvrAvatarSkinnedRenderable.cs

public abstract class OvrAvatarSkinnedRenderable : OvrAvatarRenderable
{
    /**
     * Component that encapsulates the meshes of a skinned avatar.
     * This component can only be added to game objects that
     * have a Unity Mesh, a Mesh filter and a SkinnedRenderer.
     *
     * In addition to vertex positions, texture coordinates and
     * colors, a vertex in a skinned mesh can be driven by up
     * to 4 bones in the avatar skeleton. Each frame the transforms
     * of these bones are multiplied by the vertex weights for
     * the bone and applied to compute the final vertex position.
     * This can be done by Unity on the CPU or the GPU, or by
     * the Avatar SDK using the GPU. Different variations of this
     * class are provided to allow you to select which implementation
     * best suits your application.
     *
     * @see OvrAvatarPrimitive
     * @see ApplyMeshPrimitive
     * @see OvrAvatarUnitySkinnedRenderable
     */

    /// Designates whether this renderable animations are enabled or not.
    private bool _isAnimationEnabled = true;
    public bool IsAnimationEnabled
    {
        get => _isAnimationEnabled;
        internal set
        {
            if (_isAnimationEnabled != value)
            {
                _isAnimationEnabled = value;
                OnAnimationEnabledChanged(_isAnimationEnabled);
            }
        }
    }

    protected override void Awake()
    {
        base.Awake();
        CheckPropertyIdInit();
    }

    protected internal override void ApplyMeshPrimitive(OvrAvatarPrimitive primitive)
    {
        CheckDefaultRenderer();

        base.ApplyMeshPrimitive(primitive);
        SetAnimationDataValidityForRenderer();
    }

    ///
    /// Apply the given bone transforms from the avatar skeleton
    /// to the Unity skinned mesh renderer.
    /// @param bones    Array of Transforms for the skeleton bones.
    ///                 These must be in the order the Unity SkinnedRenderer expects.
    ///
    public abstract void ApplySkeleton(Transform[] bones);

    public virtual void UpdateSkinningOrigin(in CAPI.ovrAvatar2Transform skinningOrigin)
    {
        // Default implementation is just to apply to transform
        transform.ApplyOvrTransform(skinningOrigin);
    }

    // Invoked when `IsAnimationEnabled` changes.
    protected abstract void OnAnimationEnabledChanged(bool isNowEnabled);
    internal abstract void AnimationFramePreUpdate();
    internal abstract bool AnimationFrameUpdate(
        bool updateJoints,
        bool updateMorphs,
        CAPI.ovrAvatar2EntityId entityId,
        CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId);

    internal abstract void RenderFrameUpdate();

    internal static bool FetchMorphTargetWeights(
        CAPI.ovrAvatar2EntityId entityId,
        CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId,
        IntPtr bufferPtr,
        UInt32 bufferSize,
        string logScope)
    {
        Profiler.BeginSample("GetMorphTargetWeights");
        var success = CAPI.ovrAvatar2Render_GetMorphTargetWeights(
            entityId,
            primitiveInstanceId,
            bufferPtr,
            bufferSize).EnsureSuccess("Error fetching morph target weights.", logScope);
        Profiler.EndSample();

        return success;
    }

    internal static bool FetchJointMatrices(
        CAPI.ovrAvatar2EntityId entityId,
        CAPI.ovrAvatar2PrimitiveRenderInstanceID primitiveInstanceId,
        IntPtr bufferPtr,
        UInt32 bufferSize,
        bool interleaveNormals,
        string logScope)
    {
        Profiler.BeginSample("GetSkinTransforms");
        var success =
            CAPI.ovrAvatar2Render_GetSkinTransforms(
                entityId,
                primitiveInstanceId,
                bufferPtr,
                bufferSize,
                interleaveNormals).EnsureSuccess("Error fetching skin transforms", logScope);
        Profiler.EndSample();

        return success;
    }


    protected abstract int NumAnimationFramesBeforeValidData { get; }
    private bool _isAnimationDataCompletelyValid = false;
    internal bool IsAnimationDataCompletelyValid
    {
        get => _isAnimationDataCompletelyValid;
        private set
        {
            bool valChanged = _isAnimationDataCompletelyValid != value;
            _isAnimationDataCompletelyValid = value;

            SetAnimationDataValidityForRenderer();

            if (value && valChanged)
            {
                // Safely raise the event for all subscribers
                AnimationDataComplete?.Invoke(this);
            }
        }
    }

    private int _numValidAnimationFrames;
    protected int NumValidAnimationFrames
    {
        get => _numValidAnimationFrames;
        set
        {
            _numValidAnimationFrames = value;
            IsAnimationDataCompletelyValid = value >= NumAnimationFramesBeforeValidData;
        }
    }

    internal delegate void AnimationDataCompletionHandler(OvrAvatarSkinnedRenderable sender);
    internal event AnimationDataCompletionHandler AnimationDataComplete;

    protected void IncrementValidAnimationFramesIfNeeded()
    {
        if (NumValidAnimationFrames < NumAnimationFramesBeforeValidData)
        {
            NumValidAnimationFrames++;
        }
    }

    private void SetAnimationDataValidityForRenderer()
    {
        if (rendererComponent != null)
        {
            rendererComponent.GetPropertyBlock(MatBlock);
            SetAnimationDataValidityInMaterialBlock(MatBlock);
            rendererComponent.SetPropertyBlock(MatBlock);
        }
    }

    private void SetAnimationDataValidityInMaterialBlock(MaterialPropertyBlock block)
    {
        block.SetInt(IsSkinnerOutputValidPropID, IsAnimationDataCompletelyValid ? 1 : 0);
    }

    private static int IsSkinnerOutputValidPropID => _propertyIds.IS_SKINNER_OUTPUT_VALID_PROP_ID;
    private struct AttributePropertyIds
    {
        public readonly int IS_SKINNER_OUTPUT_VALID_PROP_ID;

        public bool IsValid => IS_SKINNER_OUTPUT_VALID_PROP_ID != 0;

        public enum InitMethod { PropertyToId }
        public AttributePropertyIds(InitMethod initMethod)
        {
            IS_SKINNER_OUTPUT_VALID_PROP_ID = Shader.PropertyToID("u_IsExternalAttributeSourceValid");
        }
    }

    private static AttributePropertyIds _propertyIds = default;

    private static void CheckPropertyIdInit()
    {
        if (!_propertyIds.IsValid)
        {
            _propertyIds = new AttributePropertyIds(AttributePropertyIds.InitMethod.PropertyToId);
        }
    }
}
