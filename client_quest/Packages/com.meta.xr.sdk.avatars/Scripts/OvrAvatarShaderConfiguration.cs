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

using System;
using System.Collections.Generic;

using UnityEngine;
using UnityEngine.Rendering;

/// @file OvrAvatarShaderManagerBase.cs

namespace Oculus.Avatar2
{
    ///
    /// Contains material properties, shader keywords and texture map names
    /// for shading an avatar. You can have multiple instances of this class
    /// which apply to shading different parts of your avatar.
    /// @see OvrAvatarShaderManagerBase
    /// @see OvrAvatarShaderManagerSingle
    /// @see OvrAvatarShaderManagerMulti
    ///

    [CreateAssetMenu(fileName = "DefaultShaderConfiguration", menuName = "Facebook/Avatar/SDK/OvrAvatarShaderConfiguration", order = 1)]
    public class OvrAvatarShaderConfiguration : ScriptableObject
    {
        public Material Material;
        public Shader Shader;

        // Prefer to use the int id's instead of the strings when actually setting material params. Its a small perf win, <1us per call to mat.Set...().
        // It can add up if setting many params though. More important for dynamic params, config params tend to be static, so just saving a few us during load here.

        // These texture input names are based on what GLTF 2.0 has to offer,
        // regardless of what the specific implementation application uses
        public string NameTextureParameter_baseColorTexture = "_MainTex"; // for metallic roughness materials
        internal int IDTextureParameter_baseColorTexture;
        public string NameTextureParameter_diffuseTexture = "_MainTex";  // for specular glossy materials
        internal int IDTextureParameter_diffuseTexture;
        public string NameTextureParameter_metallicRoughnessTexture = "_MetallicGlossMap";
        internal int IDTextureParameter_metallicRoughnessTexture;
        public string NameTextureParameter_specularGlossiness = "_Specular";
        internal int IDTextureParameter_specularGlossiness;
        public string NameTextureParameter_normalTexture = "_BumpMap";
        internal int IDTextureParameter_normalTexture;
        public string NameTextureParameter_occlusionTexture = "_OcclusionMap";
        internal int IDTextureParameter_occlusionTexture;
        public string NameTextureParameter_emissiveTexture = "_EmissiveMap";
        internal int IDTextureParameter_emissiveTexture;
        public string NameTextureParameter_flowTexture = "_FlowMap";
        internal int IDTextureParameter_flowTexture;

        public string NameColorParameter_BaseColorFactor = "_Color";
        internal int IDColorParameter_BaseColorFactor;
        public bool UseColorParameter_BaseColorFactor = false;

        public string NameFloatParameter_MetallicFactor = "_Metallic";
        internal int IDFloatParameter_MetallicFactor;
        public bool UseFloatParameter_MetallicFactor = false;

        public string NameFloatParameter_RoughnessFactor = "_Roughness";
        internal int IDFloatParameter_RoughnessFactor;
        public bool UseFloatParameter_RoughnessFactor = false;

        public string NameColorParameter_DiffuseFactor = "_Diffuse";
        internal int IDColorParameter_DiffuseFactor;
        public bool UseColorParameter_DiffuseFactor = false;

        public string NameTextureParameter_SSSCurvatureTexture = "_SSSCurvatureLUT"; // for sub-surface scattering technique
        internal int IDTextureParameter_SSSCurvatureTexture;
        public Texture Texture_SSSCurvatureTexture;

        public string NameTextureParameter_SSSZHTexture = "_SSSZHLUT"; // for sub-surface scattering technique
        internal int IDTextureParameter_SSSZHTexture;
        public Texture Texture_SSSZHTexture;

        public string[] KeywordsEnumerations;
        public string[] KeywordsToEnable;
        // Cache the keywords, saves perf(load) when appying them to a material.
        private List<LocalKeyword> _keywords = new List<LocalKeyword>();
        private List<bool> _keywordEnabled = new List<bool>();

        public string[] NameFloatConstants;
        private List<int> _idFloatConstants = new List<int>();
        public float[] ValueFloatConstants;

        private LocalKeyword? _hasNormalKeyword = null;
        private int _hasNormalFloat;

        private LocalKeyword? _enableHairKeyword = null;
        private int _enableHairFloat;

        private LocalKeyword? _enableRimKeyword = null;
        private int _enableRimFloat;

        public OvrAvatarMaterialExtensionConfig ExtensionConfiguration;

        private OvrAvatarShaderDeprecationManager _deprecationManager = new OvrAvatarShaderDeprecationManager();

        public void OnEnable()
        {
            _keywords.Clear();
            _keywordEnabled.Clear();
            if (Shader != null && KeywordsEnumerations != null && KeywordsEnumerations.Length > 0)
            {
                foreach (var keyword in KeywordsEnumerations)
                {
                    var shaderKeyword = Shader.keywordSpace.FindKeyword(keyword);
                    if (shaderKeyword.isValid)
                    {
                        _keywords.Add(shaderKeyword);
                        _keywordEnabled.Add(Array.Exists(KeywordsToEnable, element => element.Equals(keyword)));
                    }
                }
            }

            _idFloatConstants.Clear();
            if (NameFloatConstants != null)
            {
                foreach (var name in NameFloatConstants)
                {
                    _idFloatConstants.Add(Shader.PropertyToID(name));
                }
            }

            IDTextureParameter_baseColorTexture = Shader.PropertyToID(NameTextureParameter_baseColorTexture);
            IDTextureParameter_diffuseTexture = Shader.PropertyToID(NameTextureParameter_diffuseTexture);
            IDTextureParameter_metallicRoughnessTexture = Shader.PropertyToID(NameTextureParameter_metallicRoughnessTexture);
            IDTextureParameter_specularGlossiness = Shader.PropertyToID(NameTextureParameter_specularGlossiness);
            IDTextureParameter_normalTexture = Shader.PropertyToID(NameTextureParameter_normalTexture);
            IDTextureParameter_occlusionTexture = Shader.PropertyToID(NameTextureParameter_occlusionTexture);
            IDTextureParameter_emissiveTexture = Shader.PropertyToID(NameTextureParameter_emissiveTexture);
            IDTextureParameter_flowTexture = Shader.PropertyToID(NameTextureParameter_flowTexture);
            IDColorParameter_BaseColorFactor = Shader.PropertyToID(NameColorParameter_BaseColorFactor);
            IDFloatParameter_MetallicFactor = Shader.PropertyToID(NameFloatParameter_MetallicFactor);
            IDFloatParameter_RoughnessFactor = Shader.PropertyToID(NameFloatParameter_RoughnessFactor);
            IDColorParameter_DiffuseFactor = Shader.PropertyToID(NameColorParameter_DiffuseFactor);
            IDTextureParameter_SSSCurvatureTexture = Shader.PropertyToID(NameTextureParameter_SSSCurvatureTexture);
            IDTextureParameter_SSSZHTexture = Shader.PropertyToID(NameTextureParameter_SSSZHTexture);

            if (Shader != null)
            {
                _hasNormalKeyword = Shader.keywordSpace.FindKeyword("HAS_NORMAL_MAP_ON");
                _hasNormalFloat = Shader.PropertyToID("HAS_NORMAL_MAP");

                _enableHairKeyword = Shader.keywordSpace.FindKeyword("ENABLE_HAIR_ON");
                _enableHairFloat = Shader.PropertyToID("ENABLE_HAIR");

                _enableRimKeyword = Shader.keywordSpace.FindKeyword("ENABLE_RIM_LIGHT_ON");
                _enableRimFloat = Shader.PropertyToID("ENABLE_RIM_LIGHT");
            }
        }

        public void ApplyKeywords(Material material)
        {
            for (int i = 0; i < _keywords.Count; i++)
            {
                material.SetKeyword(_keywords[i], _keywordEnabled[i]);
            }
        }

        public void ApplyFloatConstants(Material material)
        {
            if (ValueFloatConstants != null)
            {
                for (int i = 0; i < _idFloatConstants.Count && i < ValueFloatConstants.Length; i++)
                {
                    material.SetFloat(_idFloatConstants[i], ValueFloatConstants[i]);
                }
            }
        }

        public void RegisterShaderUsage()
        {
            _deprecationManager.PrintDeprecationWarningIfNecessary(Shader);
        }

        public void SetHasNormalMap(Material material, bool hasNormalMap)
        {
            if (_hasNormalKeyword.HasValue)
            {
                if (hasNormalMap)
                {
                    material.EnableKeyword(_hasNormalKeyword.Value);
                    material.SetFloat(_hasNormalFloat, 1.0f);
                }
                else
                {
                    material.DisableKeyword(_hasNormalKeyword.Value);
                    material.SetFloat(_hasNormalFloat, 0.0f);
                }
            }
        }

        public void SetHasHair(Material material, bool hasHair)
        {
            if (_enableHairKeyword.HasValue)
            {
                if (hasHair)
                {
                    material.EnableKeyword(_enableHairKeyword.Value);
                    material.SetFloat(_enableHairFloat, 1.0f);
                }
                else
                {
                    material.DisableKeyword(_enableHairKeyword.Value);
                    material.SetFloat(_enableHairFloat, 0.0f);
                }
            }
        }

        public void SetHasRim(Material material, bool hasRim)
        {
            if (_enableRimKeyword.HasValue)
            {
                if (hasRim)
                {
                    material.EnableKeyword(_enableRimKeyword.Value);
                    material.SetFloat(_enableRimFloat, 1.0f);
                }
                else
                {
                    material.DisableKeyword(_enableRimKeyword.Value);
                    material.SetFloat(_enableRimFloat, 0.0f);
                }
            }
        }
    }
}
