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


#nullable enable

using System;

using UnityEngine;

using System.Diagnostics.CodeAnalysis;

// ReSharper disable InconsistentNaming
// ReSharper disable RedundantDefaultMemberInitializer

// ReSharper disable once InvalidXmlDocComment
/// @file OvrAvatarShaderManagerBase.cs

namespace Oculus.Avatar2
{
    public static class OvrAvatarShaderManager
    {
        // The intent here is for each shader "type" to have it's own shader configuration.
        // Possible shader types are "combined", "separate", "eyes", "hair", "transparent".
        // We need to know, first from the "material" specification in the GLTF, and second
        // from the parts metadata in GLTF meshes/primitives, what shader model to use...
        public enum ShaderType
        {
            Default,
            SolidColor,
            FastLoad,
            Cel,

            [InspectorName(null)]
            Count
        }

        ///
        /// Determine the shader type from material properties.
        /// @param materialName name of the material.
        /// @param hasMetallic  true if the material is metallic.
        /// @param hasSpecular  true if the material has specular reflections.
        /// @return shader type to use.
        /// @see GetConfiguration
        ///
        public static ShaderType DetermineConfiguration(string materialName, bool hasMetallic, bool hasSpecular, bool hasTextures, bool useCelShading)
        {
            // TODO: look at the texture inputs for a material to determine if they are a texture array or not.
            // This presents a difficult situation because we need to know information about the textures before
            // determining the shader type to begin synthesis of the material. It may require an extra call to
            // OvrAvatarLibrary.MakeTexture() or something equivalent.
            if (useCelShading)
            {
                return ShaderType.Cel;
            }
            if (!hasTextures)
            {
                return ShaderType.FastLoad;
            }
            if (hasMetallic || hasSpecular)
            {
                return ShaderType.Default;
            }
            return ShaderType.SolidColor;
        }
    }

    ///
    /// Maintains a list of shader configurations containing
    /// material properties and texture names for the various types
    /// of shading performed on the avatar.
    /// There are several distinct shader types (eye, skin, hair, emissive, ...)
    /// each with their own shader configuration. The shader manager suggests
    /// the shader used to synthesize a material based off these configurations.
    /// @see OvrAvatarShaderConfiguration
    /// @see OvrAvatarShaderManagerSingle
    /// @see OvrAvatarShaderManagerMultiple
    ///

    public abstract class OvrAvatarShaderManagerBase : MonoBehaviour
    {
        /// Gets the number of shader types.
        public const int ShaderTypeCount = (int)OvrAvatarShaderManager.ShaderType.Count;

        /// True if initialized, else false.
        public bool Initialized { get; private set; } = false;

        ///
        /// Get the shader configuration for the given shader type.
        /// @param type shader type to get configuration for.
        /// @return shader configuration for the input type, null if none specified.
        /// @see ShaderType
        ///
        public OvrAvatarShaderConfiguration GetConfiguration(OvrAvatarShaderManager.ShaderType type)
        {
            // This should be unnecessary due to the `OnValidate` hooks, but leaving it in for now
            _AssignConfigurations();
            _AutoGenerateMissingShaderConfigurations();

            // ReSharper disable once Unity.PerformanceCriticalCodeInvocation
            return _FindConfiguration(type);
        }

        protected abstract OvrAvatarShaderConfiguration _FindConfiguration(OvrAvatarShaderManager.ShaderType type);

        protected void OnEnable()
        {
            Initialize();
        }

        protected void OnDisable()
        {
            Shutdown();
        }

        ///
        /// Initialize the shader manager.
        ///
        private void Initialize()
        {
            _AssignConfigurations();
            _AutoGenerateMissingShaderConfigurations();

            Initialized = DoInitialization();
        }
        protected abstract bool DoInitialization();

        ///
        /// Shutdown the shader manager.
        ///
        private void Shutdown()
        {
            Initialized = false;
        }


        ///
        /// Handle manually assigned shader configurations, ie: from inspector UI
        ///
        protected abstract void _AssignConfigurations();
        ///
        /// Automatically generate shader configurations.
        /// Creates a @ref OvrAvatarShaderConfiguration ScriptableObject
        /// for one or more shaders.
        ///
        protected abstract void _AutoGenerateMissingShaderConfigurations();

        protected static void InitializeAutoGeneratedConfiguration([NotNull] ref OvrAvatarShaderConfiguration? configuration)
        {
            if (configuration != null) { return; }

            configuration = ScriptableObject.CreateInstance<OvrAvatarShaderConfiguration>();

            configuration.Shader = Shader.Find("Standard");

            configuration.NameTextureParameter_baseColorTexture = "_MainTex";
            configuration.NameTextureParameter_diffuseTexture = "_MainTex";
            configuration.NameTextureParameter_metallicRoughnessTexture = "_MetallicGlossMap";
            configuration.NameTextureParameter_specularGlossiness = "_Specular";
            configuration.NameTextureParameter_normalTexture = "_BumpMap";
            configuration.NameTextureParameter_occlusionTexture = "_OcclusionMap";
            configuration.NameTextureParameter_emissiveTexture = "_EmissiveMap";
            configuration.NameTextureParameter_flowTexture = "_FlowMap";

            configuration.NameColorParameter_BaseColorFactor = "_Color";
            configuration.NameColorParameter_DiffuseFactor = "_Diffuse";
        }

        public int GetDefaultShaderIdentifier()
        {
            // ReSharper disable once Unity.PerformanceCriticalCodeInvocation
            var shaderName = GetConfiguration(OvrAvatarShaderManager.ShaderType.Default).Shader.name;
            if (shaderName == null)
            {
                // ReSharper disable once Unity.PerformanceCriticalCodeInvocation
                OvrAvatarLog.LogWarning("OvrAvatarShaderManagerBase unable to determine shader identifier.");
                return (int)OvrAvatarShaderNameUtils.KnownShader.ErrorDeterminingShader;
            }

            var shaderIdentifier = OvrAvatarShaderNameUtils.GetShaderIdentifier(shaderName);
            return shaderIdentifier;
        }


#if UNITY_EDITOR
        protected void OnValidate()
        {
            _AssignConfigurations();
            _AutoGenerateMissingShaderConfigurations();
        }
#endif // UNITY_EDITOR
    }
}
