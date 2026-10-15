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

using UnityEngine;

/// @file OvrAvatarManager_Textures.cs

namespace Oculus.Avatar2
{
    public partial class OvrAvatarManager
    {
        private const int TEXTURE_SETTINGS_INSPECTOR_ORDER = 256;

        [Header("Avatar Texture Settings", order = TEXTURE_SETTINGS_INSPECTOR_ORDER)]

        [SerializeField]
        [Tooltip("Texture Filter Mode used for Avatar textures." +
                 "\nTrilinear is highest quality with excellent performance." +
                 "\nBilinear may produce artifacts at certain distances." +
                 "\nPoint is primarily for stylistic usage.")]
        private FilterMode _filterMode = OvrAvatarImage.DEFAULT_FILTER_MODE;

        [SerializeField]
        [Tooltip("Anisotropic filtering level used for Avatar textures. Higher values are more expensive to render." +
                 "\n0 is off regardless of project Quality settings" +
                 "\n1 is off unless forced on via project Quality settings")]
        [Range(0, 16)]
        private int _anisoLevel = OvrAvatarImage.DEFAULT_ANISO_LEVEL;

        public FilterMode TextureFilterMode => _filterMode;
        public int TextureAnisoLevel => _anisoLevel;
    }
}
