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

namespace Oculus.Skinning.GpuSkinning
{
    public static class OvrGpuSkinningUtils
    {
        public static int getTextureHeightToFitVertexInfo(
            int numVerts,
            int rowsPerVert,
            int texWidth)
        {
            int texHeight = numVerts / texWidth;

            if (texWidth * texHeight < numVerts)
            {
                ++texHeight;
            }

            return texHeight * rowsPerVert;
        }

        public static Vector2Int findOptimalTextureDimensions(
            int numVerts,
            int rowsPerVert,
            uint maxTexSize)
        {
            int texWidth = numVerts;
            if (numVerts > maxTexSize)
            {
                // Divide by 2 until under maxWidth
                bool originallyOdd = (numVerts & 1) != 0;
                while (texWidth > maxTexSize)
                {
                    texWidth >>= 1;
                }

                // See if needs an additional texel if the original had odd number of verts, but
                // check for edge max where that would spill over max width
                if (texWidth == maxTexSize && originallyOdd)
                {
                    texWidth >>= 1;
                }

                texWidth += (originallyOdd ? 1 : 0);
            }

            return new Vector2Int(
                texWidth, getTextureHeightToFitVertexInfo(numVerts, rowsPerVert, texWidth));
        }

        public static Vector2Int findIndirectionTextureSize(
            int numVerts,
            int numAttribs)
        {
            return findOptimalTextureDimensions(numVerts, numAttribs, MAX_TEXTURE_DIMENSION);
        }

        public static Vector2Int findMorphTargetCombinerSize(
            int numAffectedVerts,
            int numAttribs)
        {
            Vector2Int dimensions = findOptimalTextureDimensions(numAffectedVerts, 1, MAX_TEXTURE_DIMENSION);

            // Make sure there is room for 1 "unaffected verts" texel. Since all blocks
            // added are rectangular in their definition (even if all texels in the rectangle are not used).
            // So the additional texel (1x1 rectangle) for the unaffected verts will need
            // to be an extra row

            // Take attribute count into affect and additional row if needed
            dimensions.y = (dimensions.y * numAttribs) + 1;

            return dimensions;
        }

        public const uint MAX_TEXTURE_DIMENSION = 512U;
    }
} // namespace Oculus.Skinning.GpuSkinning
