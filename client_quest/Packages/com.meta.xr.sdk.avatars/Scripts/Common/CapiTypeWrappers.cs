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
using System.Diagnostics.CodeAnalysis;

using Unity.Collections;
// ReSharper disable InconsistentNaming
// ReSharper disable MemberCanBePrivate.Global
// ReSharper disable BuiltInTypeReferenceStyle

namespace Oculus.Avatar2
{
    // Safe wrapper for `ovrAvatar2Pose` - copies values so it is safe to store, no GC allocs and MUST be `Dispose`d!
    public readonly struct OvrAvatarPose : IDisposable, IEquatable<OvrAvatarPose>
    {
        public readonly UInt32 jointCount;
        public readonly NativeArray<CAPI.ovrAvatar2Transform> localTransforms; // Array of ovrAvatar2Transforms
        public readonly NativeArray<CAPI.ovrAvatar2Transform> objectTransforms; // Array of ovrAvatar2Transforms relative to root
        public readonly NativeArray<Int32> parents; // Array of indexes such that `parentIndex = parents[childIndex]
        public readonly NativeArray<CAPI.ovrAvatar2NodeId> nodeIds; // Array of node ids

        public OvrAvatarPose(in CAPI.ovrAvatar2Pose nativePose, Allocator allocator = Allocator.Temp)
        {
            jointCount = nativePose.jointCount;

            if (jointCount > 0)
            {
                var intCount = (int)jointCount;
                localTransforms = new NativeArray<CAPI.ovrAvatar2Transform>(
                    intCount, allocator, NativeArrayOptions.UninitializedMemory);
                objectTransforms = new NativeArray<CAPI.ovrAvatar2Transform>(
                    intCount, allocator, NativeArrayOptions.UninitializedMemory);
                parents = new NativeArray<Int32>(
                    intCount, allocator, NativeArrayOptions.UninitializedMemory);
                nodeIds = nativePose.HasNodeIds ? new NativeArray<CAPI.ovrAvatar2NodeId>(
                    intCount, allocator, NativeArrayOptions.UninitializedMemory) : default;
                CopyFrom(in nativePose);
            }
            else
            {
                localTransforms = default;
                objectTransforms = default;
                parents = default;
                nodeIds = default;
            }
        }

        public void CopyFrom(in CAPI.ovrAvatar2Pose nativePose)
        {
            System.Diagnostics.Debug.Assert(localTransforms.Length == jointCount);
            System.Diagnostics.Debug.Assert(objectTransforms.Length == jointCount);
            System.Diagnostics.Debug.Assert(parents.Length == jointCount);
            System.Diagnostics.Debug.Assert(nodeIds.Length == 0 || nodeIds.Length == jointCount);
            unsafe
            {
                localTransforms.CopyFrom(nativePose.localTransforms, jointCount);
                objectTransforms.CopyFrom(nativePose.objectTransforms, jointCount);
                parents.CopyFrom(nativePose.parents, jointCount);
                nodeIds.TryCopyFrom(nativePose.nodeIds, jointCount);
            }
        }

        [SuppressMessage("ReSharper", "PossiblyImpureMethodCallOnReadonlyVariable")]
        public void Dispose()
        {
            // ReSharper disable once InvertIf
            if (jointCount > 0)
            {
                localTransforms.Dispose();
                objectTransforms.Dispose();
                parents.Dispose();
                if (nodeIds.IsCreated) { nodeIds.Dispose(); }
            }
        }

        public static bool operator ==(in OvrAvatarPose lhs, in OvrAvatarPose rhs)
        {
            if (lhs.jointCount != rhs.jointCount) { return false; }
            // range check is redundant, as the arrays can _only_ be initialized as the same size
            unsafe
            {
                var lhsLocals = lhs.localTransforms.GetPtr();
                var rhsLocals = rhs.localTransforms.GetPtr();
                var lhsObjects = lhs.objectTransforms.GetPtr();
                var rhsObjects = rhs.objectTransforms.GetPtr();
                var lhsParents = lhs.parents.GetPtr();
                var rhsParents = rhs.parents.GetPtr();
                var lhsNodes = lhs.nodeIds.GetPtr();
                var rhsNodes = rhs.nodeIds.GetPtr();
                for (var index = 0; index < lhs.jointCount; ++index)
                {
                    if (lhsLocals[index] != rhsLocals[index]
                        || lhsObjects[index] != rhsObjects[index]
                        || lhsParents[index] != rhsParents[index]
                        || lhsNodes[index] != rhsNodes[index])
                    {
                        return false;
                    }
                }
            }
            return true;
        }
        public static bool operator !=(OvrAvatarPose lhs, OvrAvatarPose rhs) => !(lhs == rhs);
        public bool Equals(OvrAvatarPose other) => this == other;
        public override bool Equals(object? obj) => obj is OvrAvatarPose other && Equals(other);
        public override int GetHashCode()
        {
            return HashCode.Combine(jointCount, localTransforms, objectTransforms, parents, nodeIds);
        }
    }

    // Managed wrapper for `ovrAvatar2Pose` - copies values so it is safe to store, one GC allocs and may be `Dispose`d
    public sealed class ManagedAvatarPose : IDisposable, IEquatable<ManagedAvatarPose>
    {
        public ManagedAvatarPose(in CAPI.ovrAvatar2Pose nativePose, Allocator allocator = Allocator.Temp)
        {
            if (nativePose.jointCount > 0)
            {
                _pose = new OvrAvatarPose(in nativePose, allocator);
            }
        }

        public ref readonly OvrAvatarPose Data => ref _pose;

        public void Dispose()
        {
            Reset();
            GC.SuppressFinalize(this);
        }

        ~ManagedAvatarPose()
        {
            Reset();
        }

        private void Reset()
        {
            _pose.Dispose();
            _pose = default;
        }

        private OvrAvatarPose _pose;

        public static bool operator ==(in ManagedAvatarPose lhs, in ManagedAvatarPose rhs) => lhs.Data == rhs.Data;
        public static bool operator !=(in ManagedAvatarPose lhs, in ManagedAvatarPose rhs) => !(lhs == rhs);
        public bool Equals(ManagedAvatarPose other) => this == other;
        public override bool Equals(object? obj) => obj is ManagedAvatarPose other && Equals(other);
        // ReSharper disable once NonReadonlyMemberInGetHashCode - `_pose`'s hashcode will change after dispose anyways
        public override int GetHashCode() => _pose.GetHashCode();
    }

    // Safe wrapper for `ovrAvatar2PrimitiveRenderState` - copies values so it is safe to store, no GC allocs and MUST be `Dispose`d!
    // NOTE: Currently lacks adequate test coverage, use with caution
    public readonly struct OvrAvatarPrimitiveRenderState : IDisposable, IEquatable<OvrAvatarPrimitiveRenderState>
    {
        public readonly CAPI.ovrAvatar2PrimitiveRenderInstanceID id; // unique id of the instance of the primitive to be rendered
        public readonly CAPI.ovrAvatar2Id primitiveId; // primitive to be rendered
        public readonly CAPI.ovrAvatar2NodeId meshNodeId;
        public readonly CAPI.ovrAvatar2Transform localTransform; // local transform of this prim relative to root
        public readonly CAPI.ovrAvatar2Transform worldTransform; // world transform of this prim
        public readonly OvrAvatarPose pose; // current pose
        public readonly UInt32 morphTargetCount; // number of blend shapes values
        public readonly CAPI.ovrAvatar2Transform skinningOrigin; // root transform of the skinning matrices

        public OvrAvatarPrimitiveRenderState(in CAPI.ovrAvatar2PrimitiveRenderState renderState, Allocator allocator = Allocator.Persistent)
        {
            id = renderState.id;
            primitiveId = renderState.primitiveId;
            meshNodeId = renderState.meshNodeId;
            localTransform = renderState.localTransform;
            worldTransform = renderState.worldTransform;
            pose = new OvrAvatarPose(in renderState.pose, allocator);
            morphTargetCount = renderState.morphTargetCount;
            skinningOrigin = renderState.skinningOrigin;
        }

        public void Dispose()
        {
            pose.Dispose();
        }

        public static bool operator ==(in OvrAvatarPrimitiveRenderState lhs, in OvrAvatarPrimitiveRenderState other)
        {
            return lhs.id == other.id && lhs.primitiveId == other.primitiveId && lhs.meshNodeId == other.meshNodeId &&
                   lhs.localTransform == other.localTransform && lhs.worldTransform == other.worldTransform &&
                   lhs.pose == other.pose && lhs.morphTargetCount == other.morphTargetCount &&
                   lhs.skinningOrigin == other.skinningOrigin;
        }
        public static bool operator !=(in OvrAvatarPrimitiveRenderState lhs, in OvrAvatarPrimitiveRenderState rhs)
            => !(lhs == rhs);
        public bool Equals(OvrAvatarPrimitiveRenderState other) => this == other;
        public override bool Equals(object? obj) => obj is OvrAvatarPrimitiveRenderState other && Equals(other);
        public override int GetHashCode()
        {
            return HashCode.Combine((int)id, (int)primitiveId, (int)meshNodeId, localTransform
                , worldTransform, pose, morphTargetCount, skinningOrigin);
        }
    }

    public static class CapiWrapperExtensions
    {
    }
}
