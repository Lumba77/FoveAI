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

using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Oculus.Avatar2
{
    public class OvrAvatarShaderDeprecationManager
    {
        public static bool IsURPEnabled()
        {
#if UNITY_6000_0_OR_NEWER
            var renderPipeline = GraphicsSettings.defaultRenderPipeline;
#else // ^^^ UNITY_6000_0_OR_NEWER / !UNITY_6000_0_OR_NEWER vvv
            var renderPipeline = GraphicsSettings.renderPipelineAsset;
#endif // !UNITY_6000_0_OR_NEWER
            if (renderPipeline == null)
            {
                return false;
            }

            // Replace with the actual type name if different
            return renderPipeline.GetType().ToString().Contains("UniversalRenderPipelineAsset");
        }

        private HashSet<string> _shaderNamesRegistered = new HashSet<string>();

        private const string scope = "OvrAvatarShaderDeprecationManager";

        public void PrintDeprecationWarningIfNecessary(Shader shader)
        {
            var name = shader.name;

            // Register the shader name so we're not spamming the console multiple times when shader is accessed.
            if (!_shaderNamesRegistered.Contains(name))
            {
                _shaderNamesRegistered.Add(name);
                const string extraInfo =
                    "We recommend using 'Style-2-Avatar-Meta' shader. Use AvatarSdkManagerMeta prefab in your scene to use this shader.";

                if (!OvrAvatarShaderNameUtils.IsKnown(name))
                {
                    OvrAvatarLog.LogWarning($"Shader '{name}' is not known to the AvatarSDK. {extraInfo}", scope);
                    return;
                }

                if (IsURPEnabled() && !OvrAvatarShaderNameUtils.HasURPSupport(name))
                {
                    OvrAvatarLog.LogError($"Shader '{name}' does not support URP. {extraInfo}", scope);
                    return;
                }

                if (OvrAvatarShaderNameUtils.IsDeprecated(name))
                {
                    OvrAvatarLog.LogWarning($"Shader '{name}' has been deprecated. {extraInfo}", scope);
                    return;
                }

                if (OvrAvatarShaderNameUtils.IsReferenceOnly(name))
                {
                    OvrAvatarLog.LogWarning($"Shader '{name}' should be used for reference and debugging purposes only. {extraInfo}", scope);
                }
            }
        }
    }
}
