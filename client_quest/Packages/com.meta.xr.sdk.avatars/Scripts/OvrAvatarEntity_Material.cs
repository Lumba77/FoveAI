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
using UnityEngine;

namespace Oculus.Avatar2
{

    public partial class OvrAvatarEntity : MonoBehaviour
    {
        private static int? _debugTintId = null;
        private static int DEBUG_TINT_ID => _debugTintId ??= Shader.PropertyToID("_DebugTint");

        private OvrAvatarMaterial _material = null;
        public OvrAvatarMaterial Material
        {
            get => _material;
            set
            {
                _material = value;
                ApplyMaterial();
            }
        }

        /**
         * Applies the shader, keywords and material properties from
         * OvrAvatarEntity.material to all the renderables associated
         * with this avatar.
         */
        public void ApplyMaterial()
        {
            foreach (var meshNodeKVP in _meshNodes)
            {
                foreach (var primRenderable in meshNodeKVP.Value)
                {
                    var renderable = primRenderable.renderable;
                    if (!renderable) { continue; }
                    _material.Apply(renderable);
                }
            }
        }

        public void SetSharedMaterialProperties(Action<UnityEngine.Material> callback)
        {
            // TODO: This will not cover all future renderables
            // Each primitive has its own property block so callback has to be called once per primitive
            // TODO: Check if there's a way around this

            foreach (var meshNodeKVP in _meshNodes)
            {
                foreach (var primRenderable in meshNodeKVP.Value)
                {
                    var renderable = primRenderable.renderable;
                    if (!renderable) { continue; }
                    var rend = renderable.rendererComponent;
                    callback(rend.sharedMaterial);
                }
            }
        }

        private void UpdateAvatarLodColor()
        {
#if UNITY_EDITOR
            if (AvatarLOD.Level > -1 && AvatarLODManager.Instance.debug.displayLODColors)
            {
                _material.SetKeyword("DEBUG_TINT", true);
                _material.SetColor(DEBUG_TINT_ID, AvatarLODManager.LOD_COLORS[AvatarLOD.overrideLOD ? AvatarLOD.overrideLevel : AvatarLOD.Level]);
            }
            else
            {
                _material.SetKeyword("DEBUG_TINT", true);
                _material.SetColor(DEBUG_TINT_ID, Color.white);
            }
            ApplyMaterial();
#endif // UNITY_EDITOR
        }

        /***
         * Applies the current material state (keywords, shader, properties)
         * to the given renderable. This function should be called whenever a
         * new renderable is added.
         */
        internal void ConfigureRenderableMaterial(OvrAvatarRenderable renderable)
        {
            if (!renderable) { return; }
            _material.Apply(renderable);
        }
    }
}
