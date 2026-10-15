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
using System.Collections.Generic;
using System.Reflection;

namespace Oculus.Avatar2
{
    public static class OvrAvatarShaderNameUtils
    {
        public enum KnownShader
        {
            AvatarMeta = 0,
            AvatarMetaVertexGI = 1,
            AvatarLibrary = 2,
            AvatarHorizon = 3,
            AvatarHuman = 4,
            AvatarKhronos = 5,
            AvatarMobileBumpedSpecular = 6,
            AvatarMobileCustom = 7,
            AvatarMobileDiffuse = 8,
            AvatarMobileVertexLit = 9,
            AvatarStandard = 10,
            AvatarStyle2Meta = 11,
            AvatarStyle2MetaVertexGI = 12,

            ErrorDeterminingShader = 998,
            UnknownShader = 999,
        }

        private static Dictionary<KnownShader, string> KnownShaderEnumToString = new Dictionary<KnownShader, string>
        {
            {KnownShader.AvatarMeta, "Avatar/Meta"},
            {KnownShader.AvatarMetaVertexGI, "Avatar/MetaHorizonVertexGI"},
            {KnownShader.AvatarLibrary, "Avatar/Library"},
            {KnownShader.AvatarHorizon, "Avatar/Horizon"},
            {KnownShader.AvatarHuman, "Avatar/Human"},
            {KnownShader.AvatarKhronos, "Avatar/Khronos"},
            {KnownShader.AvatarMobileBumpedSpecular, "Avatar/Mobile/Bumped Specular"},
            {KnownShader.AvatarMobileCustom, "Avatar/Mobile/Custom"},
            {KnownShader.AvatarMobileDiffuse, "Avatar/Mobile/Diffuse"},
            {KnownShader.AvatarMobileVertexLit, "Avatar/Mobile/VertexLit"},
            {KnownShader.AvatarStandard, "Avatar/Standard"},
            {KnownShader.AvatarStyle2Meta, "Avatar/Style2Meta"},
            {KnownShader.AvatarStyle2MetaVertexGI, "Avatar/Style2MetaHorizonVertexGI"},
        };

        private static readonly HashSet<KnownShader> DeprecatedShaders = new HashSet<KnownShader>
        {
            KnownShader.AvatarLibrary,
            KnownShader.AvatarHorizon,
            KnownShader.AvatarHuman,
            KnownShader.AvatarKhronos,
        };

        private static readonly HashSet<KnownShader> ReferenceOnlyShaders = new HashSet<KnownShader>
        {
            KnownShader.AvatarMobileBumpedSpecular,
            KnownShader.AvatarMobileCustom,
            KnownShader.AvatarMobileDiffuse,
            KnownShader.AvatarMobileVertexLit,
            KnownShader.AvatarStandard,
        };

        private static readonly HashSet<KnownShader> ShadersWithNoURPSupport = new HashSet<KnownShader>
        {
            KnownShader.AvatarMobileBumpedSpecular,
            KnownShader.AvatarMobileCustom,
            KnownShader.AvatarMobileDiffuse,
            KnownShader.AvatarMobileVertexLit,
            KnownShader.AvatarStandard,
        };

        // should not use directly, even internally use GetShaderEnum which initializes this if it's not already initialized.
        private static Dictionary<string, KnownShader> KnownShaderStringToEnum = new Dictionary<string, KnownShader>();

        private static void InitializeKnownShaderStringToEnum()
        {
            if (KnownShaderStringToEnum.Count == 0)
            {
                foreach (KeyValuePair<KnownShader, string> pair in KnownShaderEnumToString)
                {
                    KnownShaderStringToEnum.Add(pair.Value, pair.Key);
                }
            }
        }

        private static string GetShaderName(KnownShader knownShader)
        {
            return KnownShaderEnumToString[knownShader];
        }

        private static KnownShader GetShaderEnum(string shaderName)
        {
            InitializeKnownShaderStringToEnum();
            if (!KnownShaderStringToEnum.ContainsKey(shaderName))
            {
                return KnownShader.UnknownShader;
            }

            return KnownShaderStringToEnum[shaderName];
        }

        public static int GetShaderIdentifier(string shaderName)
        {
            return (int)GetShaderEnum(shaderName);
        }

        public static bool IsKnown(string name)
        {
            return GetShaderEnum(name) != KnownShader.UnknownShader;
        }

        public static bool IsDeprecated(string name)
        {
            return DeprecatedShaders.Contains(GetShaderEnum(name));
        }

        public static bool IsReferenceOnly(string name)
        {
            return ReferenceOnlyShaders.Contains(GetShaderEnum(name));
        }

        public static bool HasURPSupport(string name)
        {
            return !ShadersWithNoURPSupport.Contains(GetShaderEnum(name));
        }
    }
}
