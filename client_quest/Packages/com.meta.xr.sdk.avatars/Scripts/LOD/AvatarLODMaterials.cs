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
using System.IO;
using UnityEngine;
#if UNITY_EDITOR
using UnityEditor;

#endif


namespace Oculus.Avatar2
{
    public class AvatarLODMaterials
    {
#if UNITY_EDITOR
        // TODO: Move these materials into the Avatar SDK and reference them there:
        public static readonly string AVATAR_LOD_MATERIAL_PATH = "Assets/Package/AvatarAssetsSrc/Res/LOD/Materials/";
#endif

#if UNITY_EDITOR
        private static Material? lodNoneMaterial_ = null;
        public static Material? LodNoneMaterial
        {
            get
            {
                if (lodNoneMaterial_ == null)
                {
                    lodNoneMaterial_ = GetOrCreateLODMaterial(AVATAR_LOD_MATERIAL_PATH + "LODNoneMaterial.mat", Color.white);
                }
                return lodNoneMaterial_;
            }
        }
#else
        public readonly static Material? LodNoneMaterial = null;
#endif

#if UNITY_EDITOR
        private static Material? lodOutOfRangeMaterial_ = null;

        public static Material? LodOutOfRangeMaterial
        {
            get
            {
                if (lodOutOfRangeMaterial_ == null)
                {
                    lodOutOfRangeMaterial_ =
                      GetOrCreateLODMaterial(AVATAR_LOD_MATERIAL_PATH + "LODOutOfRangeMaterial.mat", Color.white);
                }
                return lodOutOfRangeMaterial_;
            }
        }
#else
        public readonly static Material? LodOutOfRangeMaterial = null;
#endif

        private static List<Material>? lodMaterials_ = null;

        public static List<Material>? LodMaterials
        {
            get
            {
#if UNITY_EDITOR
                if (lodMaterials_ == null)
                {
                    lodMaterials_ = new List<Material>();
                    for (int i = 0; i < AvatarLODManager.LOD_COLORS.Length; i++)
                    {
                        Material? mat = GetOrCreateLODMaterial(AVATAR_LOD_MATERIAL_PATH + "LOD" + i + "Material.mat",
                          AvatarLODManager.LOD_COLORS[i]);
                        if (mat is not null)
                        {
                            lodMaterials_.Add(mat);
                        }
                    }
                }
#endif
                return lodMaterials_;
            }
        }

        private static Material? GetOrCreateLODMaterial(string materialPath, Color color)
        {
            Material? lodMaterial = null;
#if UNITY_EDITOR
            if (File.Exists(materialPath))
            {
                lodMaterial = AssetDatabase.LoadAssetAtPath(materialPath, typeof(Material)) as Material;
                if (lodMaterial is not null)
                {
                    Color col = lodMaterial.GetColor("_Color");
                    if (col != color)
                    {
                        lodMaterial.SetColor("_Color", color);
                    }
                }
            }
#endif
            return lodMaterial;
        }
    }
}
