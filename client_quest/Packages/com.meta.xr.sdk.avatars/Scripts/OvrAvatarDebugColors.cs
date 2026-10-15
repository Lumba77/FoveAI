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

using System.Diagnostics;
using UnityEngine;

// ReSharper disable once InvalidXmlDocComment
/**
 * @file OvrAvatarRenderable.cs
 */
namespace Oculus.Avatar2
{

    public static class OvrAvatarDebugColors
    {
        private static Vector4[] varray = new[]
        {
                    new Vector4(1.0f, 0.0f, 0.0f, 1.0f), // red
                    new Vector4(1.0f, 0.5f, 0.0f, 1.0f), // orange
                    new Vector4(1.0f, 1.0f, 0.0f, 1.0f), // yellow
                    new Vector4(0.0f, 1.0f, 0.0f, 1.0f), // green
                    new Vector4(0.0f, 0.0f, 1.0f, 1.0f), // blue
                    new Vector4(0.5f, 0.0f, 1.0f, 1.0f), // violet
                    new Vector4(0.5f, 0.0f, 0.0f, 1.0f), // dark red
                    new Vector4(0.5f, 0.25f, 0.0f, 1.0f), // dark orange
                    new Vector4(0.5f, 0.5f, 0.0f, 1.0f), // dark yellow
                    new Vector4(0.0f, 0.5f, 0.0f, 1.0f), // dark green
                    new Vector4(0.0f, 0.0f, 0.5f, 1.0f), // dark blue
                    new Vector4(0.25f, 0.0f, 0.5f, 1.0f), // dark violet
                    new Vector4(0.25f, 0.0f, 0.0f, 1.0f), // dark dark red
                    new Vector4(0.25f, 0.125f, 0.0f, 1.0f), // dark dark orange
                    new Vector4(0.25f, 0.25f, 0.0f, 1.0f), // dark dark yellow
                    new Vector4(0.0f, 0.25f, 0.0f, 1.0f), // dark dark green
                    new Vector4(0.0f, 0.0f, 0.25f, 1.0f), // dark dark blue
                    new Vector4(0.125f, 0.0f, 0.25f, 1.0f), // dark dark violet

                    new Vector4(1.0f, 1.0f, 1.0f, 1.0f) // white
        };

        [Conditional("DEVELOPMENT_BUILD")]
        public static void ApplyVectorArrayToMaterial(Material mat)
        {
            mat.SetVectorArray("_DebugColors", varray);
            mat.SetInt("_DebugColorsCount", varray.Length);
        }

        private static float[] farray = new[]
        {
                1.0f, 0.0f, 0.0f, 1.0f, // red
                1.0f, 0.5f, 0.0f, 1.0f, // orange
                1.0f, 1.0f, 0.0f, 1.0f, // yellow
                0.0f, 1.0f, 0.0f, 1.0f, // green
                0.0f, 0.0f, 1.0f, 1.0f, // blue
                0.5f, 0.0f, 1.0f, 1.0f, // violet
                0.5f, 0.0f, 0.0f, 1.0f, // dark red
                0.5f, 0.25f, 0.0f, 1.0f, // dark orange
                0.5f, 0.5f, 0.0f, 1.0f, // dark yellow
                0.0f, 0.5f, 0.0f, 1.0f, // dark green
                0.0f, 0.0f, 0.5f, 1.0f, // dark blue
                0.25f, 0.0f, 0.5f, 1.0f, // dark violet
                0.25f, 0.0f, 0.0f, 1.0f, // dark dark red
                0.25f, 0.125f, 0.0f, 1.0f, // dark dark orange
                0.25f, 0.25f, 0.0f, 1.0f, // dark dark yellow
                0.0f, 0.25f, 0.0f, 1.0f, // dark dark green
                0.0f, 0.0f, 0.25f, 1.0f, // dark dark blue
                0.125f, 0.0f, 0.25f, 1.0f, // dark dark violet
                1.0f, 1.0f, 1.0f, 1.0f // white
        };

        public static void ApplyFloatArrayToGlobal()
        {
            Shader.SetGlobalFloatArray("_DebugColorsFloat", farray);
            Shader.SetGlobalInt("_DebugColorsCount", farray.Length / 4);
        }

        // NOTE: The following two functions allow us to test the float arrays per material
        // However they add memory on a per avatar basis. So it's better to use the global version.
        [Conditional("DEVELOPMENT_BUILD")]
        public static void ApplyFloatArrayToMaterial(Material mat)
        {
            mat.SetFloatArray("_DebugColorsFloat", farray);
            mat.SetInt("_DebugColorsCount", farray.Length / 4);
        }

        [Conditional("DEVELOPMENT_BUILD")]
        public static void DeepCopyFloatArrays(Material destMat, Material srcMat)
        {
            destMat.SetFloatArray("_DebugColorsFloat", srcMat.GetFloatArray("_DebugColorsFloat"));
            destMat.SetInt("_DebugColorsCount", farray.Length / 4);
        }
    }
}
