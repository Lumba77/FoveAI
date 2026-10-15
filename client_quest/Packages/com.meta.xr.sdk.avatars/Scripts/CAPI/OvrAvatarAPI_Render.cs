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
using System.Runtime.InteropServices;

namespace Oculus.Avatar2
{
    public static partial class CAPI
    {
        [StructLayout(LayoutKind.Sequential)]
        public unsafe readonly ref struct ovrAvatar2EntityRenderState
        {
            public readonly ovrAvatar2Transform rootTransform;
            public readonly UInt32 primitiveCount;
            public readonly ovrAvatar2HierarchyVersion hierarchyVersion; ///< see ovrAvatar2Entity_GetPose
            public readonly ovrAvatar2EntityRenderStateVersion allNodesVersion; ///< changes when allMeshNodes changes
            public readonly ovrAvatar2EntityRenderStateVersion visibleNodesVersion; ///< changes when visibleMeshNodes changes
            public readonly ovrAvatar2NodeId* allMeshNodes;
            public readonly ovrAvatar2NodeId* visibleMeshNodes;
            public readonly UInt32 allMeshNodesCount;
            public readonly UInt32 visibleMeshNodesCount;

            public ovrAvatar2NodeId GetAllMeshNodeAtIdx(UInt32 index)
            {
                if (index >= allMeshNodesCount)
                {

                    throw new ArgumentOutOfRangeException(
                        $"Index {index} is out of range of allMeshNodes array of size {allMeshNodesCount}");
                }

                unsafe
                {
                    return allMeshNodes[index];
                }
            }

            public ovrAvatar2NodeId GetVisibleMeshNodeAtIdx(UInt32 index)
            {
                if (index >= visibleMeshNodesCount)
                {

                    throw new ArgumentOutOfRangeException(
                        $"Index {index} is out of range of visibleMeshNodes array of size {visibleMeshNodesCount}");
                }

                unsafe
                {
                    return visibleMeshNodes[index];
                }
            }
        }

        public enum ovrAvatar2PrimitiveRenderInstanceID : Int32
        {
            Invalid = 0
        }

        // TODO: T177790998 - it is not safe for `ovrAvatar2PrimitiveRenderState` to be copied off the stack
        [StructLayout(LayoutKind.Sequential)]
        public readonly /*ref*/ struct ovrAvatar2PrimitiveRenderState
        {
            public readonly ovrAvatar2PrimitiveRenderInstanceID id; // unique id of the instance of the primitive to be rendered
            public readonly ovrAvatar2Id primitiveId; // primitive to be rendered
            public readonly ovrAvatar2NodeId meshNodeId;
            public readonly ovrAvatar2Transform localTransform; // local transform of this prim relative to root
            public readonly ovrAvatar2Transform worldTransform; // world transform of this prim
            public readonly ovrAvatar2Pose pose; // current pose
            public readonly UInt32 morphTargetCount; // number of blend shapes values
            public readonly ovrAvatar2Transform skinningOrigin; // root transform of the skinning matrices
        }

        // Query the render state for an entity
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Render_QueryRenderState(
            ovrAvatar2EntityId entityId, out ovrAvatar2EntityRenderState outState);

        // Query the render state for a primitive in an entity by index
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Render_GetPrimitiveRenderStateByIndex(
            ovrAvatar2EntityId entityId, UInt32 primitiveRenderStateIndex,
            out ovrAvatar2PrimitiveRenderState outState);

        // Query the render states for a primitive in an entity by index
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern unsafe CAPI.ovrAvatar2Result ovrAvatar2Render_GetPrimitiveRenderStatesByIndex(
            ovrAvatar2EntityId entityId, UInt32* primitiveRenderStateIndices,
            ovrAvatar2PrimitiveRenderState* outState,
            UInt32 numRenderStates);

        // Query the render states for a primitive in an entity by index
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern unsafe ovrAvatar2PrimitiveRenderState* ovrAvatarXRender_GetPrimitiveRenderStates(
            ovrAvatar2EntityId entityId,
            out UInt32 outCount,
            out UInt32 outStride);

        // Retrieve the skin transforms for a primitive render state
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Render_GetSkinTransforms(
            ovrAvatar2EntityId entityId, ovrAvatar2PrimitiveRenderInstanceID instanceId, /*ovrAvatar2Matrix4f[]*/ IntPtr skinTransforms, UInt32 bytes, bool interleaveNormalMatrices);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern CAPI.ovrAvatar2Result ovrAvatar2Render_GetMorphTargetWeights(
            ovrAvatar2EntityId entityId, ovrAvatar2PrimitiveRenderInstanceID instanceId, /*float[]*/ IntPtr morphTargetWeights, UInt32 bytes);
    }
}
