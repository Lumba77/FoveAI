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

//#define OVR_AVATAR_AUTO_DISABLE_SKINNING_MATRICES_WITH_UNITYSMR

using Oculus.Skinning;
using Oculus.Skinning.GpuSkinning;
using System;
using System.Collections.Generic;
using UnityEngine;

namespace Oculus.Avatar2
{
    public partial class OvrAvatarEntity : MonoBehaviour
    {
        // TODO: Move more rendering logic here

        public bool isStaticMesh => SkinningType == SkinningConfig.NONE;
        private bool UseGpuSkinning => SkinningType == SkinningConfig.OVR_GPU;
        private bool UseGpuMorphTargets => SkinningType == SkinningConfig.OVR_GPU;

        private bool UseComputeSkinning => SkinningType == SkinningConfig.OVR_COMPUTE;

        private bool UseMotionSmoothingRenderer => MotionSmoothingSettings == MotionSmoothingOptions.USE_CONFIG_SETTING ? GpuSkinningConfiguration.Instance.MotionSmoothing : MotionSmoothingSettings == MotionSmoothingOptions.FORCE_ON;

        private Transform _probeAnchor = null;

        /////////////////////////////////////////////////
        //:: Private Functions

        #region Config

        public enum SkinningConfig
        {
            DEFAULT = 0,
            NONE = 1,
            // Unity Built-In Skinning (slow, recommend use for debugging only)
            UNITY = 2,

            // Not Implemented
            OVR_CPU = 3,
            // GPU Skinning is deprecated in favor of Compute Skinning (faster, less memory)
            OVR_GPU = 4,
            // Recommended: Compute Skinning
            OVR_COMPUTE = 5,
        }

        // As of AvatarSDK v24, in order to simplify SkinningType used by avatars, this is set via the
        // SerializeField _skinningType in OvrAvatarManager. If you need to override a specific avatar
        // attach OvrAvatarSkinningOverride to Avatar. See SkinningTypesExample for details.
        protected SkinningConfig SkinningType = SkinningConfig.DEFAULT;

        private SkinningConfig _targetSkinningType = SkinningConfig.DEFAULT;

        private enum MotionSmoothingOptions
        {
            USE_CONFIG_SETTING,
            FORCE_ON,
            FORCE_OFF,
        }

        [Tooltip("Enable/disable motion smoothing for an individual OvrAvatarEntity. By default uses the setting specified in the GpuSkinningConfiguration.")]
        [SerializeField]
        private MotionSmoothingOptions MotionSmoothingSettings = MotionSmoothingOptions.USE_CONFIG_SETTING;

        [SerializeField]
        private bool _hidden = false;

        private bool UseAppSwRenderer => GpuSkinningConfiguration.Instance.SupportApplicationSpaceWarp;

        // TODO: This should be keyed by primitiveId instead of instance?
        private readonly Dictionary<OvrAvatarPrimitive, OvrAvatarSkinnedRenderable> _skinnedRenderables = new();

        public bool Hidden
        {
            get => _hidden;
            set
            {
                _hidden = value;
                SetActiveView(GetActiveView());
            }
        }

        // Called by CreateRenderable, setup skinning type based on primitive and configuration
        private OvrAvatarRenderable AddRenderableComponent(GameObject primitiveObject, OvrAvatarPrimitive primitive)
        {
            bool hasSkinningData = primitive.joints.Length > 0;
            SkinningType = hasSkinningData ? _targetSkinningType : SkinningConfig.NONE;

            var renderable = AddRenderableComponent(primitiveObject);

            if (!(_probeAnchor is null))
            {
                renderable.rendererComponent.probeAnchor = _probeAnchor;
            }

            renderable.ApplyMeshPrimitive(primitive);

            return renderable;
        }

        private OvrAvatarRenderable AddRenderableComponent(GameObject primitiveObject)
        {
            switch (SkinningType)
            {
                case SkinningConfig.DEFAULT:
                case SkinningConfig.UNITY:
                    return primitiveObject.AddComponent<OvrAvatarUnitySkinnedRenderable>();

                case SkinningConfig.OVR_GPU:
                    if (!UseMotionSmoothingRenderer)
                    {
                        if (!UseAppSwRenderer)
                        {
                            return primitiveObject.AddComponent<OvrAvatarGpuSkinnedRenderable>();
                        }

                        return primitiveObject.AddComponent<OvrAvatarGpuSkinnedMvRenderable>();
                    }
                    else
                    {
                        if (!UseAppSwRenderer)
                        {
                            var renderable = primitiveObject.AddComponent<OvrAvatarGpuInterpolatedSkinnedRenderable>();
                            renderable.InterpolationValueProvider = _interpolationValueProvider;

                            return renderable;
                        }
                        else
                        {
                            var renderable = primitiveObject.AddComponent<OvrAvatarGpuInterpolatedSkinnedMvRenderable>();
                            renderable.InterpolationValueProvider = _interpolationValueProvider;

                            return renderable;
                        }
                    }
                case SkinningConfig.OVR_COMPUTE:
                    if (!UseMotionSmoothingRenderer)
                    {
                        if (!UseAppSwRenderer)
                        {
                            return primitiveObject.AddComponent<OvrAvatarComputeSkinnedRenderable>();
                        }

                        return primitiveObject.AddComponent<OvrAvatarComputeSkinnedMvRenderable>();
                    }
                    else
                    {
                        if (!UseAppSwRenderer)
                        {
                            var renderable = primitiveObject.AddComponent<OvrAvatarComputeInterpolatedSkinnedRenderable>();
                            renderable.InterpolationValueProvider = _interpolationValueProvider;

                            return renderable;
                        }
                        else
                        {
                            var renderable = primitiveObject.AddComponent<OvrAvatarComputeInterpolatedSkinnedMvRenderable>();
                            renderable.InterpolationValueProvider = _interpolationValueProvider;

                            return renderable;
                        }
                    }
                case SkinningConfig.NONE:
                    return primitiveObject.AddComponent<OvrAvatarRenderable>();

                default:
                    throw new ArgumentException($"Invalid SkinningType: {(int)SkinningType}");

            }
        }


        private void ValidateSkinningType()
        {
            var skinningOverrideComponent = GetComponent<OvrAvatarSkinningOverride>();
            if (skinningOverrideComponent)
            {
                SkinningType = skinningOverrideComponent.skinningTypeOverride;
            }
            else
            {
                SkinningType = OvrAvatarManager.Instance.GetBestSupportedSkinningConfig();
            }

            var additionalInfo = "(you can enable this SkinningType in OvrAvatarManager => SkinningSettings => SkinningType)";

            // If requesting texture based skinning aka "Gpu skinning", check if there is support and assign a fallback
            if (SkinningType == SkinningConfig.OVR_GPU)
            {
                if (!OvrAvatarManager.Instance.OvrGPUSkinnerSupported)
                {
                    // Check if the system supports gpu skinning for better error messaging
                    if (!OvrAvatarManager.Instance.gpuSkinningShaderLevelSupported)
                    {
                        OvrAvatarLog.LogInfo("OvrGpuSkinning unsupported on this hardware. Attempting fallback to Unity skinning.", logScope, this);
                    }
                    else if (!TestHelpers.isRunningAnEditorTest)
                    {
                        OvrAvatarLog.LogWarning($"OvrGpuSkinning unsupported {additionalInfo}. Attempting fallback to Unity skinning.", logScope, this);
                    }

                    SkinningType = SkinningConfig.UNITY;
                }
            }

            // If requesting compute skinning and not supported, assign a fallback
            if (SkinningType == SkinningConfig.OVR_COMPUTE && !OvrAvatarManager.Instance.OvrComputeSkinnerSupported)
            {
                // Check if the system supports compute skinning for better error messaging
                if (!OvrAvatarManager.Instance.systemSupportsComputeSkinner)
                {
                    OvrAvatarLog.LogInfo("OvrComputeSkinner unsupported on this hardware, attempting fallback to Unity skinning.", logScope, this);
                }
                else if (!TestHelpers.isRunningAnEditorTest)
                {
                    OvrAvatarLog.LogWarning($"OvrComputeSkinner unsupported {additionalInfo}, attempting fallback to Unity skinning.", logScope, this);
                }

                SkinningType = SkinningConfig.UNITY;
            }

            if (SkinningType == SkinningConfig.UNITY && !OvrAvatarManager.Instance.UnitySMRSupported)
            {
                // See if other skinner types are supported
                if (OvrAvatarManager.Instance.OvrGPUSkinnerSupported)
                {
                    OvrAvatarLog.LogWarning("Unity skinning unsupported. Falling back to OvrGPU.", logScope, this);

                    SkinningType = SkinningConfig.OVR_GPU;
                }
                else if (OvrAvatarManager.Instance.OvrComputeSkinnerSupported)
                {

                    OvrAvatarLog.LogWarning($"Unity skinning unsupported {additionalInfo}. Falling back to OvrCompute.", logScope, this);

                    SkinningType = SkinningConfig.OVR_COMPUTE;
                }
                else
                {
                    OvrAvatarLog.LogError($"Unity skinning unsupported {additionalInfo} with no fallback. Using SkinningConfig.NONE.", logScope, this);
                    SkinningType = SkinningConfig.NONE;
                }
            }

            OvrAvatarLog.LogVerbose($"SkinningType of Avatar '{gameObject.name}' set to {SkinningType}", logScope, this);
            if (SkinningType == SkinningConfig.OVR_GPU)
            {
                OvrAvatarLog.LogWarning("Using OVR_GPU (deprecated) skinning. Consider using OVR_COMPUTE skinning by setting SkinningType in OvrAvatarManager.", logScope, this);
            }
            _targetSkinningType = SkinningType;
        }

        #endregion

        public void SetProbeAnchor(Transform anchor)
        {
            // TODO: Confirm this catches renderables added later
            _probeAnchor = anchor;

            foreach (var meshNodeKVP in _meshNodes)
            {
                foreach (var primRenderData in meshNodeKVP.Value)
                {
                    var renderable = primRenderData.renderable;
                    if (!renderable) { continue; }
                    var rend = renderable.rendererComponent;
                    rend.probeAnchor = anchor;
                }
            }
        }

        /**
         * Configures the material for this renderable
         * with the last known material state.
         */
        private void InitializeRenderable(OvrAvatarRenderable renderable)
        {
            renderable.entity.SetTarget(this);

            ConfigureRenderableMaterial(renderable);

            try { OnRenderableCreated(renderable); }
            catch (Exception e)
            {
                OvrAvatarLog.LogException("OnRenderableCreated", e, logScope, this);
            }
        }

        internal void TeardownRenderable(OvrAvatarRenderable renderable)
        {
            // Use member variable instead of getter since
            // getter always adds a new one
            if (_avatarLOD != null)
            {
                _avatarLOD.OnRenderableDisposed(renderable);
            }

            try { OnRenderableDisposed(renderable); }
            catch (Exception e)
            {
                OvrAvatarLog.LogException("OnRenderableDisposed", e, logScope, this);
            }
        }
    }
}
