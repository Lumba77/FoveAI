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
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;
using Unity.Profiling;

using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Profiling;

using static Oculus.Avatar2.CAPI;

using ShaderType = Oculus.Avatar2.OvrAvatarShaderManager.ShaderType;

/// @file OvrAvatarPrimitive.cs

namespace Oculus.Avatar2
{
    /**
     * Encapsulates a mesh associated with an avatar asset.
     * Asynchronously loads the mesh and its material and
     * converts it to a Unity Mesh and Material.
     * A primitive may be shared across avatar levels of detail
     * and across avatar renderables.
     * @see OvrAvatarRenderable
     */
    public sealed class OvrAvatarPrimitive : OvrAvatarAsset<CAPI.ovrAvatar2Primitive>
    {
        private const string primitiveLogScope = "ovrAvatarPrimitive";
        //:: Internal

        private const int LOD_INVALID = -1;

        /// Name of the asset this mesh belongs to.
        /// The asset name is established when the asset is loaded.
        public override string assetName => shortName;

        /// Type of asset (e.e. "OvrAvatarPrimitive", "OvrAvatarImage")
        public override string typeName => primitiveLogScope;

        /// Name of this primitive.
        public readonly string name = null;

        ///
        /// Short name of this primitive.
        /// Defaults to the asset name.
        /// @see assetName
        ///
        public readonly string shortName = null;

        /// Unity Material used by this primitive.
        public Material material { get; private set; } = null;

        /// Unity Mesh used by this primitive.
        public Mesh mesh { get; private set; } = null;

        /// True if this primitive has a computed bounding volume.
        public bool hasBounds { get; private set; }

        /// Triangle and vertex counts for this primitive.
        public ref readonly AvatarLODCostData CostData => ref _costData;

        /// Gets the GPU skinning version of this primitive.
        public OvrAvatarGpuSkinnedPrimitive gpuPrimitive { get; private set; } = null;

        public OvrAvatarComputeSkinnedPrimitive computePrimitive { get; private set; }
#pragma warning disable CA2213 // Disposable fields should be disposed - it is, but the linter is confused
        private OvrAvatarGpuSkinnedPrimitiveBuilder gpuPrimitiveBuilder = null;
#pragma warning restore CA2213 // Disposable fields should be disposed

        ///
        /// Index of highest quality level of detail this primitive belongs to.
        /// One primitive may be used by more than one level of detail.
        /// This is the lowest set bit in @ref CAPI.ovrAvatar2EntityLODFlags provided from native SDK.
        ///
        public uint HighestQualityLODIndex => (uint)lod;

        ///
        /// LOD bit flags for this primitive.
        /// These flags indicate which levels of detail this primitive is used by.
        /// @see HighestQualityLODIndex
        ///
        public CAPI.ovrAvatar2EntityLODFlags lodFlags { get; private set; }

        ///
        /// Type of shader being used by this primitive.
        /// The shader type depends on what part of the avatar is being shaded.
        ///
        public ShaderType shaderType { get; private set; }

        private OvrAvatarShaderConfiguration _shaderConfig;

        // MeshInfo, only tracked for cleanup on cancellation
        private MeshInfo _meshInfo;

        // NOTE: Once this is initialized, it should not be "reset" even if the Primitive is disposed
        // Other systems may need to reference this data during shutdown, and it's a PITA if they each have to make copies
        private AvatarLODCostData _costData = default;

        // TODO: A primitive can technically belong to any number of LODs with gaps in between.
        private int lod = LOD_INVALID;

        // TODO: Make this debug only
        public Int32[] joints;

        ///
        /// Get which body parts of the avatar this primitive is used by.
        /// These are established when the primitive is loaded.
        ///
        public CAPI.ovrAvatar2EntityManifestationFlags manifestationFlags { get; private set; }

        ///
        /// Get which view(s) (first person, third person) this primitive applies to.
        /// These are established when the primitive is loaded.
        ///
        public CAPI.ovrAvatar2EntityViewFlags viewFlags { get; private set; }

        ///
        /// If the user wants only a subset of the mesh, as specified by
        /// indices, these flags will control which submeshes are included.
        /// NOTE: In the current implementation all verts are downloaded,
        /// but the indices referencing them are excluded.
        ///
        public CAPI.ovrAvatar2EntitySubMeshInclusionFlags subMeshInclusionFlags { get; private set; }

        ///
        /// If the user wants to lower the avatar quality for faster rendering, they can
        /// do that here.
        ///
        public CAPI.ovrAvatar2EntityQuality quality { get; private set; }

        /// True if this primitive has joints (is skinned).
        public bool HasJoints => JointCount > 0;

        /// True if this primitive has blend shapes (morph targets).
        public bool HasMorphs => morphTargetCount > 0;

        /// Number of joints affecting this primitive.
        public UInt32 JointCount => joints != null ? (uint)joints.Length : 0;

        /// Number of vertices in this primitive's mesh.
        public UInt32 meshVertexCount => _meshVertexCount;

        /// Number of vertices affected by morph targets.
        // TODO: Accurate count of vertices affected by morph targets
        // Assumes that if there are morph targets, all verts are affected by morphs
        public UInt32 morphVertexCount => HasMorphs ? meshVertexCount : 0;

        public UInt32 skinningCost => data.skinningCost;

        /// Number of triangles in this primitive.
        public UInt32 triCount { get; private set; }

        /// Number of morph targets affecting this primitive.
        public UInt32 morphTargetCount => _morphTargetCount;

        /// True if this primitive has tangents for each vertex.
        public bool hasTangents { get; private set; }

        /// True if this primitive has curvature for each vertex.
        public bool hasCurvature { get; private set; }

        /// True if this primitive was loaded with a normalmap.
        public bool hasNormalMap { get; private set; }

        /// True if this primitive has TexCoord2 data
        public OvrAvatarEntity.AvatarStyle primitiveStyle { get; set; }

        private UInt32 bufferVertexCount => _bufferVertexCount;

        /// True if this primitive has finished loading.
        public override bool isLoaded
        {
            get => base.isLoaded && meshLoaded && materialLoaded && gpuSkinningLoaded && computeSkinningLoaded;
        }

        // Indicates that this Primitive no longer needs access to CAPI asset data and the resource can be released
        internal bool hasCopiedAllResourceData =>
            !(_needsMeshData || _needsMorphData || _needsImageData || _needsCompactSkinningData);

        // Vertex count for the entire asset buffer, may include data for multiple primitives
        private UInt32 _bufferVertexCount = UInt32.MaxValue;

        // Vertex count for this mesh's primitive
        private UInt32 _meshVertexCount = UInt32.MaxValue;
        private UInt32 _morphTargetCount = UInt32.MaxValue;

        // Task thread completion checks
        private bool meshLoaded = false;
        private bool materialLoaded = false;
        private bool gpuSkinningLoaded = false;
        private bool computeSkinningLoaded = false;

        // Resource copy status
        private bool _needsMeshData = true;
        private bool _needsMorphData = true;
        private bool _needsImageData = true;
        private bool _needsCompactSkinningData = true;

        // TODO: Remove via better state management
        private bool _hasCancelled = false;

        // Cancellation token for Tasks
#pragma warning disable CA2213 // Disposable fields should be disposed -> It is, but the linter is confused
        private CancellationTokenSource _cancellationTokenSource = new CancellationTokenSource();
#pragma warning restore CA2213 // Disposable fields should be disposed

        // Async load coroutines for cancellation
        private OvrTime.SliceHandle _loadMeshAsyncSliceHandle;
        private OvrTime.SliceHandle _loadMaterialAsyncSliceHandle;

        [Flags]
        private enum VertexFormat : UInt32
        {
            VF_POSITION = 1,
            VF_NORMAL = 2,
            VF_TANGENT = 4,
            VF_COLOR = 8,
            VF_TEXCOORD0 = 16,
            VF_COLOR_ORMT = 32,
            VF_COLOR_CURVATURE = 64,
            VF_BONE_WEIGHTS = 128,
            VF_BONE_INDICES = 256,
        }

        // Unity 2022 requires skinned mesh attributes be on specific streams. We create separate NativeArrays and
        // strides for each stream.
        // Stream 0: Position, Normal, Tangent
        // Stream 1: Color, TexCoord0, TextCoord1, Curvature
        // Stream 2: BlendWeight, BlendIndices
        private const int VF_STREAM_COUNT = 3;

        // These aren't really necessary but make it clear which stream is being used and where.
        private const int VF_STREAM_0 = 0;
        private const int VF_STREAM_1 = 1;
        private const int VF_STREAM_2 = 2;

        private class ProfilerMarkers
        {
            public readonly ProfilerMarker GetTextureDataMarker;
            public readonly ProfilerMarker FindTextureDataMarker;
            public readonly ProfilerMarker PrepLoadMeshAsyncDataMarker;
            public readonly ProfilerMarker PrepLoadMaterialAsyncDataMarker;
            public readonly ProfilerMarker CreateMaterialMarker;
            public readonly ProfilerMarker SetupMaterialMarker;

            public ProfilerMarkers()
            {
                var categories = OvrAvatarProfilingUtils.AvatarCategories;
                GetTextureDataMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarPrimitive::Material_GetTexturesData");
                FindTextureDataMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarPrimitive::FindTexturesSlice");
                PrepLoadMeshAsyncDataMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarPrimitive::Prepare_LoadMeshAsync");
                PrepLoadMaterialAsyncDataMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarPrimitive::Prepare_LoadMaterialAsync");
                CreateMaterialMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarPrimitive::CreateMaterial");
                SetupMaterialMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarPrimitive::SetupMaterialMarker");
            }
        }
        private static ProfilerMarkers s_markers = null;

        private unsafe readonly struct VertexBufferFormat : IDisposable
        {
            public VertexBufferFormat(VertexFormat vertexFormat_, int vertexCount_
                , in VertexBufferStrides vertexStrides_
                , VertexAttributeDescriptor[] vertexLayout_, NativeArray<byte>[] vertexStreams_)
            {
                vertexFormat = vertexFormat_;
                vertexCount = vertexCount_;
                vertexStrides = vertexStrides_;
                vertexLayout = vertexLayout_;
                vertexStreams = vertexStreams_;
            }

            public readonly VertexFormat vertexFormat;
            public readonly Int32 vertexCount;

            public readonly VertexBufferStrides vertexStrides;
            public readonly VertexAttributeDescriptor[] vertexLayout;

            public readonly NativeArray<byte>[] vertexStreams;

            public struct VertexBufferStrides
            {
                private fixed int _lengths[VF_STREAM_COUNT];

                public ref int this[int idx] => ref _lengths[idx];
            }

            public void Dispose()
            {
                for (int idx = 0; idx < VF_STREAM_COUNT; ++idx)
                {
                    vertexStreams[idx].Reset();
                }
            }
        }
        private static int GetVertexStride(in VertexBufferFormat bufferFormat, int streamIndex)
        {
            unsafe
            {
                return bufferFormat.vertexStrides[streamIndex];
            }
        }

        // Data shared across threads
        private sealed class MeshInfo : IDisposable
        {
            public NativeArray<UInt16> triangles;

            private NativeArray<Vector3> verts_;

            // New vertex format.
            public VertexBufferFormat VertexBufferFormat;

            // NOTE: Held during GPUPrimitiveBuilding
            public ref readonly NativeArray<Vector3> verts => ref verts_;

            public void SetVertexBuffer(in NativeArray<Vector3> buffer)
            {
                verts_ = buffer;
                pendingMeshVerts_ = true;
            }

            // NOTE: Held during GPUPrimitiveBuilding
            private NativeArray<Vector3> normals_;

            public ref readonly NativeArray<Vector3> normals => ref normals_;

            public void SetNormalsBuffer(in NativeArray<Vector3> buffer)
            {
                normals_ = buffer;
                pendingMeshNormals_ = true;
            }

            // NOTE: Held during GPUPrimitiveBuilding
            private NativeArray<Vector4> tangents_;

            public ref readonly NativeArray<Vector4> tangents => ref tangents_;

            public void SetTangentsBuffer(in NativeArray<Vector4> buffer)
            {
                tangents_ = buffer;
                pendingMeshTangents_ = true;
                hasTangents = buffer.IsCreated && buffer.Length > 0;
            }

            public void SetTrianglesBuffer(in NativeArray<UInt16> tris)
            {
                pendingMeshTriangles_ = true;
                triangles = tris;
            }

            // This holds vertex colors, texture coordinates, vertex properties, and material type
            public NativeArray<byte> staticAttributes;
            public bool hasColors;
            public bool hasTextureCoords;
            public bool hasProperties;
            public bool hasCurvature;

            // Documentation for `SetBoneWeights(NativeArray)` is... lacking
            // - https://docs.unity3d.com/ScriptReference/Mesh.SetBoneWeights.html
            private BoneWeight[] boneWeights_;

            public ref readonly BoneWeight[] boneWeights => ref boneWeights_;

            public void SetBoneWeights(BoneWeight[] buffer)
            {
                boneWeights_ = buffer;
                pendingMeshBoneWeights_ = buffer != null && buffer.Length > 0;
            }

            // Skin
            // As of 2020.3, no NativeArray bindPoses setter
            public Matrix4x4[] bindPoses;

            // Track vertex count after verts has been freed
            public uint vertexCount { get; set; }
            public bool hasTangents { get; private set; }

            public void WillBuildGpuPrimitive()
            {
                pendingGpuPrimitive_ = true;
                pendingNeutralPoseTex_ = vertexCount > 0;
            }

            public void WillBuildComputePrimitive()
            {
                pendingComputePrimitive_ = true;
            }

            public void DidBuildGpuPrimitive()
            {
                pendingGpuPrimitive_ = false;
                if (CanResetVerts) { verts_.Reset(); }
                if (CanResetNormals) { normals_.Reset(); }
                if (CanResetTangents) { tangents_.Reset(); }
                if (CanResetBoneWeights) { boneWeights_ = null; }
            }

            public void FinishedBuildingComputePrimitive()
            {
                pendingComputePrimitive_ = false;

                // Compute primitive only uses the MeshInfo's
                // triangles
                if (CanResetTriangles) { triangles.Reset(); }
            }

            public void NeutralPoseTexComplete()
            {
                pendingNeutralPoseTex_ = false;
                if (CanResetVerts) { verts_.Reset(); }
                if (CanResetNormals) { normals_.Reset(); }
                if (CanResetTangents) { tangents_.Reset(); }
            }

            public void CancelledBuildPrimitives()
            {
                DidBuildGpuPrimitive();
                NeutralPoseTexComplete();
            }

            public void MeshVertsComplete()
            {
                pendingMeshVerts_ = false;
                if (CanResetVerts) { verts_.Reset(); }
            }

            public void MeshNormalsComplete()
            {
                pendingMeshNormals_ = false;
                if (CanResetNormals) { normals_.Reset(); }
            }

            public void MeshTangentsComplete()
            {
                pendingMeshTangents_ = false;
                if (CanResetTangents) { tangents_.Reset(); }
            }

            public void MeshBoneWeightsComplete()
            {
                pendingMeshBoneWeights_ = false;
                if (CanResetBoneWeights) { boneWeights_ = null; }
            }

            public void TrianglesAreSetOnMesh()
            {
                pendingMeshTriangles_ = false;
                if (CanResetTriangles) { triangles.Reset(); }
            }

            private bool CanResetVerts => !pendingGpuPrimitive_ && !pendingNeutralPoseTex_ && !pendingMeshVerts_;
            private bool CanResetNormals => !pendingGpuPrimitive_ && !pendingNeutralPoseTex_ && !pendingMeshNormals_;
            private bool CanResetTangents => !pendingGpuPrimitive_ && !pendingNeutralPoseTex_ && !pendingMeshTangents_;
            private bool CanResetBoneWeights => !pendingGpuPrimitive_ && !pendingMeshBoneWeights_;

            private bool CanResetTriangles => !pendingComputePrimitive_ && !pendingMeshTriangles_;

            private bool pendingMeshVerts_ = false;
            private bool pendingMeshTangents_ = false;
            private bool pendingMeshNormals_ = false;
            private bool pendingMeshBoneWeights_ = false;
            private bool pendingMeshTriangles_ = false;

            private bool pendingGpuPrimitive_ = false;
            private bool pendingComputePrimitive_ = false;

            private bool pendingNeutralPoseTex_ = false;

            public void Dispose()
            {
                Dispose(true);
                GC.SuppressFinalize(this);
            }

            private void Dispose(bool isDispose)
            {
                boneWeights_ = null;
                bindPoses = null;

                triangles.Reset();

                verts_.Reset();
                normals_.Reset();
                tangents_.Reset();

                staticAttributes.Reset();

                OvrAvatarLog.Assert(isDispose, primitiveLogScope);
            }

            ~MeshInfo()
            {
                OvrAvatarLog.LogError("Finalized MeshInfo", primitiveLogScope);
                Dispose(false);
            }
        }

        private class MaterialInfo
        {
            public CAPI.ovrAvatar2MaterialTexture[] texturesData = null;
            public CAPI.ovrAvatar2Image[] imageData = null;
            public bool hasMetallic = false;
            public bool useCelShading = false;
        }

        // TODO: Look into readonly struct, this doesn't appear to be shared across threads
        private struct MorphTargetInfo
        {
            public readonly string name;

            // TODO: Maybe make these NativeArrays too?
            public readonly Vector3[] targetPositions;
            public readonly Vector3[] targetNormals;
            public readonly Vector3[] targetTangents;

            public MorphTargetInfo(string nameIn, Vector3[] posIn, Vector3[] normIn, Vector3[] tanIn)
            {
                this.name = nameIn;
                this.targetPositions = posIn;
                this.targetNormals = normIn;
                this.targetTangents = tanIn;
            }
        }

        internal OvrAvatarPrimitive(OvrAvatarResourceLoader loader, in CAPI.ovrAvatar2Primitive primitive) : base(
            primitive.id, in primitive)
        {
            // Ensure profiling markers are initialized before they can possibly be used, avoiding static ctor overhead
            s_markers ??= new ProfilerMarkers();

            // TODO: Can we defer this until later as well?
            mesh = new Mesh();

            // Name

            unsafe
            {
                const int bufferSize = 1024;
                byte* nameBuffer = stackalloc byte[bufferSize];
                var result = CAPI.ovrAvatar2Asset_GetPrimitiveName(assetId, nameBuffer, bufferSize);
                if (result.IsSuccess())
                {
                    string meshPrimitiveName = Marshal.PtrToStringAnsi((IntPtr)nameBuffer);
                    if (!string.IsNullOrEmpty(meshPrimitiveName)) { name = meshPrimitiveName; }
                }
                else { OvrAvatarLog.LogWarning($"GetPrimitiveName {result}", primitiveLogScope); }
            }

            if (name == null) { name = "Mesh" + primitive.id; }

            mesh.name = name;
            shortName = name.Replace("Primitive", "p");
        }

        // Must *not* be called more than once
        private bool _startedLoad = false;

        internal IEnumerator<bool> StartLoad(OvrAvatarResourceLoader loader)
        {
            OvrAvatarLog.LogVerbose($"Starting primitive load for loader: {loader.resourceId}", primitiveLogScope);
            Debug.Assert(!_startedLoad);
            Debug.Assert(!_loadMeshAsyncSliceHandle.IsValid);
            Debug.Assert(!_loadMaterialAsyncSliceHandle.IsValid);

            _startedLoad = true;

            var vertCountResult =
                CAPI.ovrAvatar2VertexBuffer_GetVertexCount(data.vertexBufferId, out _bufferVertexCount);
            if (!vertCountResult.EnsureSuccess("ovrAvatar2VertexBuffer_GetVertexCount", primitiveLogScope))
            {
                _bufferVertexCount = 0;
                _needsMeshData = false;
            }

            var morphResult = CAPI.ovrAvatar2Result.Unknown;
            //primitives might not have a morph target
            if (data.morphTargetBufferId != CAPI.ovrAvatar2MorphTargetBufferId.Invalid)
            {
                morphResult =
                    CAPI.ovrAvatar2VertexBuffer_GetMorphTargetCount(data.morphTargetBufferId, out _morphTargetCount);
                //but if they do, then getting the count shouldn't fail
                morphResult.EnsureSuccess("ovrAvatar2VertexBuffer_GetMorphTargetCount", primitiveLogScope);
            }

            if (morphResult.IsFailure())
            {
                _morphTargetCount = 0;
                _needsMorphData = false;
            }

            _needsCompactSkinningData = _needsMeshData && OvrAvatarManager.Instance.OvrComputeSkinnerSupported;

            if (OvrTime.ShouldHold) { yield return false; }

            PrepareLoadMeshAsync();

            if (OvrTime.ShouldHold) { yield return false; }

            bool step = true;
            var prepMatStep = PrepareLoadMaterialAsync(loader);
            while (step)
            {
                {
                    using var prepMatScope = s_markers.PrepLoadMaterialAsyncDataMarker.Auto();
                    step = prepMatStep.MoveNext();
                }
                if (step) { yield return false; }
            }

            // there are additional flags which will be set before publicly reporting `isLoaded`
            base.isLoaded = true;
        }

        private bool _CanCleanupCancellationToken =>
            !_loadMeshAsyncSliceHandle.IsValid && !_loadMaterialAsyncSliceHandle.IsValid;

        private void _TryCleanupCancellationToken()
        {
            if (!_CanCleanupCancellationToken)
            {
                // Cancellation called while timesliced operations in progress
                return;
            }

            _cancellationTokenSource?.Dispose();
            _cancellationTokenSource = null;
        }

        private bool AreAllTasksCancelled()
        {
            bool allCancelled = true;

            for (int idx = 0; idx < _apiTasks.Count; ++idx)
            {
                Task task = _apiTasks[idx];
                if (task != null)
                {
                    if (task.IsCompleted)
                    {
                        task.Dispose();
                        task = null;
                    }
                    else
                    {
                        OvrAvatarLog.LogDebug(
                            $"Cancelled Task {task} is still running",
                            primitiveLogScope);
                        allCancelled = false;
                    }
                }
            }

            if (allCancelled && _apiTasks.Count > 0) { _apiTasks.Clear(); }

            if (_texturesDataTask != null)
            {
                if (_texturesDataTask.IsCompleted)
                {
                    _texturesDataTask.Dispose();
                    _texturesDataTask = null;
                }
                else
                {
                    OvrAvatarLog.LogError(
                        $"Cancelled Task {_texturesDataTask} is still running",
                        primitiveLogScope);
                    allCancelled = false;
                }
            }

            return allCancelled;
        }

        protected override void _ExecuteCancel()
        {
            OvrAvatarLog.Assert(!_hasCancelled, primitiveLogScope);
            // TODO: Remove this check, this should not be possible
            if (_hasCancelled)
            {
                OvrAvatarLog.LogError($"Double cancelled primitive {name}", primitiveLogScope);
                return;
            }
            // TODO: We can probably skip all of this if cancellation token is null
            _cancellationTokenSource?.Cancel();

            if (_loadMeshAsyncSliceHandle.IsValid)
            {
                OvrAvatarLog.LogDebug($"Stopping LoadMeshAsync slice {shortName}", primitiveLogScope);
                bool didCancel = _loadMeshAsyncSliceHandle.Cancel();
                OvrAvatarLog.Assert(didCancel, primitiveLogScope);
            }

            if (_loadMaterialAsyncSliceHandle.IsValid)
            {
                OvrAvatarLog.LogDebug($"Stopping LoadMaterialAsync slice {shortName}", primitiveLogScope);
                bool didCancel = _loadMaterialAsyncSliceHandle.Cancel();
                OvrAvatarLog.Assert(didCancel, primitiveLogScope);
            }
            if (AreAllTasksCancelled())
            {
                _FinishCancel();
            }
            else
            {
                OvrTime.Slice(_WaitForCancellation());
            }
            _hasCancelled = true;
        }

        private IEnumerator<OvrTime.SliceStep> _WaitForCancellation()
        {
            // Wait for all tasks to complete before proceeding with cleanup
            while (!AreAllTasksCancelled()) { yield return OvrTime.SliceStep.Delay; }

            // Finish cancellation, Dispose of Tasks and Tokens
            _FinishCancel();

            // Ensure any misc assets created during cancellation window are properly disposed
            Dispose(true);
        }

        private void _FinishCancel()
        {
            if (gpuPrimitiveBuilder != null)
            {
                OvrAvatarLog.LogDebug($"Stopping gpuPrimitiveBuilder {shortName}", primitiveLogScope);

                gpuPrimitiveBuilder.Dispose();
                gpuPrimitiveBuilder = null;
            }

            if (computePrimitive != null)
            {
                computePrimitive.Dispose();
                computePrimitive = null;
            }

            _needsImageData = _needsMeshData = _needsMorphData = _needsCompactSkinningData = false;
            _TryCleanupCancellationToken();
        }

        protected override void Dispose(bool disposing)
        {
            _loadMeshAsyncSliceHandle.Clear();
            _loadMaterialAsyncSliceHandle.Clear();

            if (!(mesh is null))
            {
                if (disposing) { Mesh.Destroy(mesh); }
                else
                {
                    OvrAvatarLog.LogError(
                        $"Mesh asset was not destroyed before OvrAvatarPrimitive ({name}, {assetId}) was finalized",
                        primitiveLogScope);
                }

                mesh = null;
            }

            if (!(material is null))
            {
                if (disposing) { Material.Destroy(material); }
                else
                {
                    OvrAvatarLog.LogError(
                        $"Material asset was not destroyed before OvrAvatarPrimitive ({name}, {assetId}) was finalized",
                        primitiveLogScope);
                }

                material = null;
            }

            if (!(gpuPrimitive is null))
            {
                if (disposing) { gpuPrimitive.Dispose(); }
                else
                {
                    OvrAvatarLog.LogError(
                        $"OvrAvatarGPUSkinnedPrimitive asset was not destroyed before OvrAvatarPrimitive ({name}, {assetId}) was finalized"
                        ,
                        primitiveLogScope);
                }

                gpuPrimitive = null;
            }

            if (!(computePrimitive is null))
            {
                if (disposing) { computePrimitive.Dispose(); }
                else
                {
                    OvrAvatarLog.LogError(
                        $"OvrAvatarComputeSkinnedPrimitive asset was not destroyed before OvrAvatarPrimitive ({name}, {assetId}) was finalized"
                        ,
                        primitiveLogScope);
                }

                computePrimitive = null;
            }

            DisposeVertexBuffer(_meshInfo);
            _meshInfo?.Dispose();

            joints = null;
            _shaderConfig = null;

            meshLoaded = false;
            materialLoaded = false;
        }

        //:: Main Thread Loading

        #region Main Thread Loading
        private List<Task> _apiTasks = new List<Task>();

        // This is fairly cheap, when using compute skinner, stream 2 isn't used, stream 0 is very small, only stream 1 has much real data.
        // And most of the actual work will happen on the unity render thread, here its basically just the cost of a memcpy.
        private void UploadStreamBuffersAndDispose(in VertexBufferFormat vertexBuffer)
        {
            MeshUpdateFlags flags = MeshUpdateFlags.DontResetBoneBounds | MeshUpdateFlags.DontNotifyMeshUsers;
            for (int idx = 0; idx < VF_STREAM_COUNT; ++idx)
            {
                ref NativeArray<byte> streamBuffer = ref vertexBuffer.vertexStreams[idx];
                if (idx == VF_STREAM_1)
                {
                    // for static attributes, we didn't need to make a copy, so vertexStreams[idx] will be empty,
                    // can just pass what we got from the SDK to Unity directly.
                    streamBuffer = ref _meshInfo.staticAttributes;
                }

                if (!streamBuffer.IsCreated) { continue; }

                if (streamBuffer.Length > 0)
                {
                    mesh.SetVertexBufferData(streamBuffer, 0, 0,
                        vertexBuffer.vertexCount * GetVertexStride(vertexBuffer, idx), idx, flags);
                    // Reset the buffer as soon as we're done with it to reduce peak memory allocations
                }
                streamBuffer.Reset();
            }
        }

        //11/23 This is ~125us. Mostly just getting things kicked off.
        private void PrepareLoadMeshAsync()
        {
            using var allocateScope = s_markers.PrepLoadMeshAsyncDataMarker.Auto();
            GetLodInfo();
            GetManifestationInfo();
            GetViewInfo();
            GetSubMeshInclusionInfo();
            GetQualityInfo();

            var unitySkinning = OvrAvatarManager.Instance.UnitySMRSupported;
            var gpuSkinning = OvrAvatarManager.Instance.OvrGPUSkinnerSupported;
            var computeSkinning = OvrAvatarManager.Instance.OvrComputeSkinnerSupported;
            var computeSkinningOnly = computeSkinning && !unitySkinning && !gpuSkinning;
            var disableMeshOptimization = OvrAvatarManager.Instance.disableMeshOptimization;

            var setupSkin = data.jointCount > 0 && (gpuSkinning || unitySkinning);
            var hasAnyJoints = data.jointCount > 0;
            var setupMorphTargets = morphTargetCount > 0 && (gpuSkinning || unitySkinning);

            _meshInfo = new MeshInfo();
            var morphTargetInfo = setupMorphTargets ? new MorphTargetInfo[morphTargetCount] : Array.Empty<MorphTargetInfo>();

            _apiTasks.Add(OvrAvatarManager.Instance.EnqueueLoadingTask(() => { RetrieveTriangles(_meshInfo); }));

            _apiTasks.Add(OvrAvatarManager.Instance.EnqueueLoadingTask(() => RetrieveMeshData(_meshInfo, computeSkinningOnly, disableMeshOptimization)));

            if (setupMorphTargets)
            {
                _apiTasks.Add(OvrAvatarManager.Instance.EnqueueLoadingTask(() => SetupMorphTargets(morphTargetInfo)));
            }

            if (setupSkin)
            {
                _apiTasks.Add(OvrAvatarManager.Instance.EnqueueLoadingTask(() => SetupSkin(ref _meshInfo)));
            }
            else if (hasAnyJoints)
            {
                _apiTasks.Add(OvrAvatarManager.Instance.EnqueueLoadingTask(SetupJointIndicesOnly));
            }
            else
            {
                joints = Array.Empty<int>();
            }

            _loadMeshAsyncSliceHandle = OvrTime.Slice(LoadMeshAsync(morphTargetInfo));
        }

        private IEnumerator<OvrTime.SliceStep> LoadMeshAsync(MorphTargetInfo[] morphTargetInfo)
        {
            Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.setupBuilders");
            // load triangles
            // load mesh & morph targets
            // create unity mesh and/or gpu skinning resources

            var unitySkinning = OvrAvatarManager.Instance.UnitySMRSupported;
            var gpuSkinning = OvrAvatarManager.Instance.OvrGPUSkinnerSupported;
            var computeSkinning = OvrAvatarManager.Instance.OvrComputeSkinnerSupported;

            var setupSkin = data.jointCount > 0 && (gpuSkinning || unitySkinning);

            if (gpuSkinning)
            {
                // Gpu skinning needs both a primitive and a primitive "builder"
                gpuPrimitiveBuilder = new OvrAvatarGpuSkinnedPrimitiveBuilder(shortName, morphTargetCount);
            }
            else
            {
                // Don't need to wait for gpu skinning
                gpuSkinningLoaded = true;
            }

            if (computeSkinning)
            {
                _meshInfo.WillBuildComputePrimitive();
            }
            else
            {
                // Don't need to wait for compute skinning
                computeSkinningLoaded = true;
            }

            Profiler.EndSample();   // "setupBuilders"
            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
            Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.getMinMax");

            CAPI.ovrAvatar2Vector3f minPos;
            CAPI.ovrAvatar2Vector3f maxPos;
            CAPI.ovrAvatar2Result result;

            var getSkinnedMinMaxPosition = data.jointCount > 0;
            if (getSkinnedMinMaxPosition)
            {
                result = CAPI.ovrAvatar2Primitive_GetSkinnedMinMaxPosition(data.id, out minPos, out maxPos);
            }
            else
            {
                result = CAPI.ovrAvatar2Primitive_GetMinMaxPosition(data.id, out minPos, out maxPos);
            }

            hasBounds = false;
            Bounds? sdkBounds = null;
            if (result.IsSuccess())
            {
                Vector3 unityMin = minPos;
                Vector3 unityMax = maxPos;
                sdkBounds = new Bounds(Vector3.zero, unityMax - unityMin);
                hasBounds = true;
            }

            Profiler.EndSample();   // "getMinMax"
            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

            while (!AllTasksFinished(_apiTasks))
            {
                if (AnyTasksFaulted(_apiTasks))
                {
                    // Allow Slicer to cancel before CancelLoad is called or we will cancel during slice!
                    OvrAvatarLog.LogError("Task fault detected! Disposing resource.", primitiveLogScope);
                    OvrTime.PostCleanupToUnityMainThread(Dispose);
                    yield return OvrTime.SliceStep.Cancel;
                }

                yield return OvrTime.SliceStep.Delay;
            }

            _needsMeshData = false;
            _needsMorphData = false;

            if (AllTasksSucceeded(_apiTasks))
            {
                _apiTasks.Clear();

                hasTangents = _meshInfo.hasTangents;
                hasCurvature = _meshInfo.hasCurvature;

                // TODO: Better way to setup this dependency, we need all preprocessing completed to build GPU resources though :/
                if (gpuPrimitiveBuilder != null)
                {
                    Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.CreateGpuPrimitiveHelperTask");

                    // Mark the "MeshInfo" as needing to build a GPU primitive here
                    // instead of in an task that may be enqueued later to prevent race condition
                    _meshInfo.WillBuildGpuPrimitive();
                    _apiTasks.Add(OvrAvatarManager.Instance.EnqueueLoadingTask(() => gpuPrimitiveBuilder.CreateGpuPrimitiveHelperTask(
                        _meshInfo,
                        morphTargetInfo,
                        hasTangents)));

                    Profiler.EndSample();   // "CreateGpuPrimitiveHelperTask"
                    if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                }
                else
                {
                    _apiTasks.Clear();
                }

                // TODO: It would be ideal to pull this directly from nativeSDK - requires LOD buffer split
                _meshVertexCount = _meshInfo.vertexCount;

                // Apply mesh info on main thread
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.CreateVertexBuffer");

                // Create a vertex buffer using the format and stride.
                CreateVertexBuffer(_meshInfo);

                Profiler.EndSample();   // "CreateVertexBuffer"
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.SetVertexBufferParams");

                // Set the mesh vertex buffer parameters from the vertex buffer created above.
                // Note: final vertex buffer data is not set until the finalized below.
                var vertexBuffer = _meshInfo.VertexBufferFormat;
                mesh.SetVertexBufferParams(vertexBuffer.vertexCount, vertexBuffer.vertexLayout);

                Profiler.EndSample();   // "SetVertexBufferParams"
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.StripExcludedSubMeshes");

                StripExcludedSubMeshes(ref _meshInfo.triangles);

                Profiler.EndSample();   // "SetVertexBufferParams"
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.SetIndices");

                // get number of submeshes
                // foreach submesh, check to see if it is included
                // if it is not, then remove this range from the index buffer

                mesh.SetIndexBufferParams(_meshInfo.triangles.Length, IndexFormat.UInt16);
                //Note that we aren't going to recalculate bounds here regardless of hasBounds, no point until later, after we set the vertex data.
                const MeshUpdateFlags flags = MeshUpdateFlags.DontResetBoneBounds | MeshUpdateFlags.DontValidateIndices | MeshUpdateFlags.DontRecalculateBounds | MeshUpdateFlags.DontNotifyMeshUsers;
                //MeshUpdateFlags flags = MeshUpdateFlags.Default;
                mesh.SetIndexBufferData(_meshInfo.triangles, 0, 0, _meshInfo.triangles.Length, flags);
                SubMeshDescriptor descriptor = new SubMeshDescriptor(0, _meshInfo.triangles.Length);
                if (hasBounds)
                {
                    descriptor.bounds = (Bounds)sdkBounds;
                }
                mesh.subMeshCount = 1;
                mesh.SetSubMesh(0, descriptor, flags);

                _meshInfo.TrianglesAreSetOnMesh();

                Profiler.EndSample();   // "SetIndices"

                // When UnitySMR is supported, include extra animation data
                if (OvrAvatarManager.Instance.UnitySMRSupported)
                {
                    if (setupSkin)
                    {
                        if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

                        mesh.bindposes = _meshInfo.bindPoses;
                        _meshInfo.bindPoses = null;
                    }

                    foreach (var morphTarget in morphTargetInfo)
                    {
                        if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

                        Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.AddBlendShapeFrame");
                        mesh.AddBlendShapeFrame(
                            morphTarget.name,
                            1,
                            morphTarget.targetPositions,
                            morphTarget.targetNormals,
                            morphTarget.targetTangents);
                        Profiler.EndSample();   // "AddBlendShapeFrame"
                    }
                }

                //Since this will call out to code we don't own, no telling how long this will take.
                if (OvrAvatarManager.Instance.HasMeshLoadListener)
                {
                    yield return OvrTime.SliceStep.Stall;
                    Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.InvokeOnMeshLoaded");
                    // Call the mesh loaded callback before the native arrays are reset.
                    InvokeOnMeshLoaded(mesh, _meshInfo);
                    Profiler.EndSample();   // "InvokeOnMeshLoaded"
                }

                // 9/8/2023 This block has a worst case of ~100us on LOD 0
                {
                    // Vertex buffer data.
                    // Copy the vertex data into the vertex buffer array.
                    if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                    Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.CopyMeshDataIntoVertexBufferAndDispose");
                    CopyMeshDataIntoVertexBufferAndDispose(_meshInfo);
                    Profiler.EndSample();   // "CopyMeshDataIntoVertexBufferAndDispose"

                    // Upload vertex data to the mesh.
                    UploadStreamBuffersAndDispose(in vertexBuffer);

                    if (!hasBounds)
                    {
                        mesh.RecalculateBounds();
                    }
                    mesh.MarkModified();
                }

                // 9/8/2023 This block has a worst case of ~100us on LOD 0
                {
                    // Upload mesh data to GPU
                    if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                    Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.UploadMeshData");
                    var markNoLongerReadable = !OvrAvatarManager.Instance.disableMeshOptimization;
                    mesh.UploadMeshData(markNoLongerReadable);
                    Profiler.EndSample();   // "UploadMeshData"

                    // It seems that almost every vert data assignment will recalculate (and override) bounds - excellent engine...
                    // So, we must delay this to the very end for no logical reason
                    if (sdkBounds.HasValue)
                    {
                        mesh.bounds = sdkBounds.Value;
                    }
                }

                if (gpuPrimitiveBuilder != null)
                {
                    if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                    // TODO: This is not ideal timing for this operation, but it does minimize disruption in this file which is key right now 3/3/2021
                    // - As of now, there really isn't any meaningful work that can be done off the main thread - pending D26787881
                    while (!AllTasksFinished(_apiTasks)) { yield return OvrTime.SliceStep.Delay; }
                    // Main thread operations (currently almost all of it), sliced as best possible
                    Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.gpuBuildPrimitive");
                    gpuPrimitive = gpuPrimitiveBuilder.BuildPrimitive(_meshInfo, joints);
                    Profiler.EndSample();   // "gpuBuildPrimitive"
                }

                if (computeSkinning)
                {
                    // 9/8/2023 This block has a worst case of ~30us on LOD 0, most of the work is on threads
                    Profiler.BeginSample("OvrAvatarPrimitive.LoadMeshAsync.computeBuildPrimitive");
                    computePrimitive = BuildPrimitive(
                        data.compactSkinningDataId,
                        _meshInfo.triangles,
                        () =>
                        {
                            OvrAvatarLog.LogWarning("Failed to build compute skinning primitive", primitiveLogScope);
                            _needsCompactSkinningData = false;
                            _meshInfo.FinishedBuildingComputePrimitive();
                        },
                        () =>
                        {
                            // Can free compact skinning data
                            _needsCompactSkinningData = false;
                        },
                        bufferHasTangents =>
                        {
                            _needsCompactSkinningData = false;

                            // In the case where the compute skinner is the only
                            // skinner used, the previous call to the "hasTangents" setter
                            // sets a default value (because the tangents buffer for the "mesh"
                            // isn't loaded as an optimization). So, set "hasTangents" here.
                            hasTangents = bufferHasTangents;
                            _meshInfo.FinishedBuildingComputePrimitive();
                        });
                    Profiler.EndSample();
                }

                while (gpuPrimitive != null && gpuPrimitive.IsLoading)
                {
                    yield return OvrTime.SliceStep.Wait;
                }
                if (gpuPrimitiveBuilder != null)
                {
                    gpuPrimitiveBuilder.Dispose();
                    gpuPrimitiveBuilder = null;
                }
                gpuSkinningLoaded = true;

                while (computePrimitive != null && computePrimitive.IsLoading)
                {
                    yield return OvrTime.SliceStep.Defer;
                }
                computeSkinningLoaded = true;

                if (gpuPrimitive != null && gpuPrimitive.MetaData.NumMorphTargetAffectedVerts == 0
                    || computePrimitive != null && computePrimitive.VertexBuffer?.NumMorphedVerts == 0)
                {
                    _morphTargetCount = 0;
                }


                _costData = new AvatarLODCostData(this);
                meshLoaded = true;
            }
            else if (isCancelled)
            {
                // Ignore cancellation related exceptions
                OvrAvatarLog.LogDebug($"LoadMeshAsync was cancelled", primitiveLogScope);
            }
            else
            {
                // Log errors from Tasks
                foreach (var task in _apiTasks)
                {
                    if (task is { Status: TaskStatus.Faulted }) { LogTaskErrors(task); }
                }
            }

            _apiTasks.Clear();
            _loadMeshAsyncSliceHandle.Clear();
            _TryCleanupCancellationToken();
        }

        public OvrAvatarComputeSkinnedPrimitive BuildPrimitive(
            ovrAvatar2CompactSkinningDataId id,
            in NativeArray<UInt16> meshIndices,
            Action failureCallback,
            Action compactSkinningDataLoadedCallback,
            Action<bool> finishCallback)
        {
            var primitive = new OvrAvatarComputeSkinnedPrimitive(
                id,
                meshIndices,
                failureCallback,
                compactSkinningDataLoadedCallback,
                finishCallback);

            return primitive;
        }

        private Task _texturesDataTask = null;

        //11/2023 This is ~30us. Mostly just getting things kicked off.
        private IEnumerator<bool> PrepareLoadMaterialAsync(OvrAvatarResourceLoader loader)
        {
            // Info to pass between threads
            var materialInfo = new MaterialInfo();
            {
                using var getTextureScope = s_markers.GetTextureDataMarker.Auto();
                Material_GetTexturesData(loader.resourceId, ref materialInfo);
            }


            _needsImageData = !(materialInfo.texturesData is null) && !(materialInfo.imageData is null);
            OvrAvatarImage[] images = null;
            if (_needsImageData)
            {
                // Check for images needed by this material. Request image loads on main thread and wait for them.
                uint numImages = (uint)materialInfo.imageData.Length;
                images = new OvrAvatarImage[(int)numImages];

                {
                    // This can take a while for the first LOD loaded. 400us sometimes, might get sliced.
                    var findTextures = FindTextures(loader, materialInfo, images, loader.resourceId);

                    bool step = true;
                    while (step)
                    {
                        step = findTextures.MoveNext();
                        if (step) { yield return false; }
                    }
                }
            }
            _loadMaterialAsyncSliceHandle = OvrTime.Slice(LoadMaterialAsync(loader, loader.resourceId, materialInfo, images));

            //yield break;
        }

        private IEnumerator<OvrTime.SliceStep> LoadMaterialAsync(OvrAvatarResourceLoader loader,
            CAPI.ovrAvatar2Id resourceId, MaterialInfo materialInfo, OvrAvatarImage[] images)
        {
            if (_needsImageData)
            {
                Debug.Assert(images != null);

                _needsImageData = false;

                // Image load wait loop.

                // Wait until all images are fully loaded
                foreach (var image in images)
                {
                    if (image == null) { continue; }

                    while (!image.isLoaded)
                    {
                        if (!image.isCancelled)
                        {
                            // Loading in progress, delay next slice
                            yield return OvrTime.SliceStep.Delay;
                        }
                        else // isCancelled
                        {
                            OvrAvatarLog.LogVerbose(
                                $"Image {image} cancelled during resource load.",
                                primitiveLogScope);

                            // Resume checking next frame
                            yield return OvrTime.SliceStep.Wait;

                            break; // move to next images
                        }
                    }
                }
            }

            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
            var (extensionTypes, materialExtensions) = LoadExtensions();
            // Configure shader manager and create material
            {
                // 11/23 ~75us
                using var prepMatScope = s_markers.CreateMaterialMarker.Auto();
                var managerInstance = OvrAvatarManager.Instance;
                if (managerInstance == null || managerInstance.ShaderManager == null)
                {
                    OvrAvatarLog.LogError(
                        "ShaderManager must be initialized so that a shader can be specified to generate Avatar primitive materials.",
                        primitiveLogScope);
                }
                else
                {
                    bool hasTextures = materialInfo.texturesData != null && materialInfo.texturesData.Length > 0;

                    materialInfo.useCelShading = (extensionTypes & ExtensionType.Cel) > 0;
                    shaderType =
                        OvrAvatarShaderManager.DetermineConfiguration(
                            name, materialInfo.hasMetallic,
                            false, hasTextures, materialInfo.useCelShading);
                    _shaderConfig = managerInstance.ShaderManager.GetConfiguration(shaderType);
                }

                if (_shaderConfig == null)
                {
                    OvrAvatarLog.LogError($"Could not find config for shaderType {shaderType}", primitiveLogScope);
                    yield break;
                }

                if (_shaderConfig.Material != null) { material = new Material(_shaderConfig.Material); }
                else
                {
                    var shader = _shaderConfig.Shader;

                    if (shader == null)
                    {
                        OvrAvatarLog.LogError($"Could not find shader for shaderType {shaderType}", primitiveLogScope);
                        yield break;
                    }

                    material = new Material(shader);
                }

                material.name = name;
            }

            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

            // Setup Material, apply textures and static Uniforms
            {
                // 11/23 ~50us
                hasNormalMap = false;
                using var prepMatScope = s_markers.SetupMaterialMarker.Auto();
                foreach (var textureData in materialInfo.texturesData)
                {
                    // Find corresponding image
                    if (OvrAvatarManager.GetOvrAvatarAsset(textureData.imageId, out OvrAvatarImage image))
                    {
                        ApplyTexture(image.Texture, textureData);
                        if (textureData.type == ovrAvatar2MaterialTextureType.Normal)
                        {
                            hasNormalMap = true;
                        }
                    }
                    else
                    {
                        OvrAvatarLog.LogError($"Could not find image {textureData.imageId}", primitiveLogScope);
                    }
                }

                if (material != null)
                {
                    _shaderConfig.RegisterShaderUsage();

                    // Finalize dynamically created material
                    _shaderConfig.ApplyKeywords(material);
                    _shaderConfig.ApplyFloatConstants(material);

                    bool enableNormalMap = (quality <= CAPI.ovrAvatar2EntityQuality.Standard);
                    bool enablePropertyHairMap = (quality <= CAPI.ovrAvatar2EntityQuality.Standard);
                    bool enableRimLighting = (quality <= CAPI.ovrAvatar2EntityQuality.Standard);
                    _shaderConfig.SetHasNormalMap(material, enableNormalMap);
                    _shaderConfig.SetHasHair(material, enablePropertyHairMap);
                    _shaderConfig.SetHasRim(material, enableRimLighting);

                    // Initialize static textures that are typically common to all avatars
                    if (!string.IsNullOrEmpty(_shaderConfig.NameTextureParameter_SSSCurvatureTexture) &&
                        _shaderConfig.Texture_SSSCurvatureTexture != null)
                    {
                        material.SetTexture(_shaderConfig.IDTextureParameter_SSSCurvatureTexture, _shaderConfig.Texture_SSSCurvatureTexture);
                    }
                    if (!string.IsNullOrEmpty(_shaderConfig.NameTextureParameter_SSSZHTexture) &&
                        _shaderConfig.Texture_SSSZHTexture != null)
                    {
                        material.SetTexture(_shaderConfig.IDTextureParameter_SSSZHTexture, _shaderConfig.Texture_SSSZHTexture);
                    }
                }
            }

            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

            ApplyExtensions(materialExtensions);

            // use an array of colors in floats to debug and prove that the floating point material blocks are working
            OvrAvatarDebugColors.ApplyFloatArrayToGlobal();

            // Extract all material parameter data from the SDK and assign it to the material
            // NOTE: from this point on if the material is copied these blocks must be deep copied also!
            // See the call to DeepCopyFloatArrays in OvrAvatarRenderable.
            OvrAvatarSubMeshIdentification.ApplyArraysToMaterial(material, GetCancellationToken(), assetId);

            materialLoaded = true;
            _loadMaterialAsyncSliceHandle.Clear();
            _TryCleanupCancellationToken();
        }

        private (ExtensionType extensionTypes, List<OvrAvatarMaterialExtension> materialExtensions) LoadExtensions()
        {
            Profiler.BeginSample("OvrAvatarPrimitive.LoadExtensions");

            var result = CAPI.ovrAvatar2Primitive_GetNumMaterialExtensions(assetId, out uint numExtensions);
            if (!result.IsSuccess())
            {
                OvrAvatarLog.LogError(
                    $"GetNumMaterialExtensions assetId:{assetId}, result:{result}"
                    , primitiveLogScope);
            }

            ExtensionType extensionTypes = ExtensionType.None;
            List<OvrAvatarMaterialExtension> materialExtensions = new List<OvrAvatarMaterialExtension>((int)numExtensions);
            Dictionary<string, ExtensionType> extensionNameToType = new Dictionary<string, ExtensionType> {
                { "FB_materials_hair", ExtensionType.Hair },
                { "FB_materials_rim_light", ExtensionType.RimLight },
                { "FB_materials_skin", ExtensionType.Skin },
                { "FB_materials_cel", ExtensionType.Cel },
            };
            for (uint extensionIdx = 0; extensionIdx < numExtensions; extensionIdx++)
            {
                if (OvrAvatarMaterialExtension.LoadExtension(
                        assetId,
                        extensionIdx,
                        out var extension))
                {
                    materialExtensions.Add(extension);
                    if (extensionNameToType.TryGetValue(extension.Name, out var extensionType))
                    {
                        extensionTypes |= extensionType;
                    }
                }
                else
                {
                    OvrAvatarLog.LogWarning(
                        $"Unable to load material extension at index {extensionIdx} for assetId:{assetId}",
                        primitiveLogScope);
                }
            }

            Profiler.EndSample();   // "LoadExtensions"
            return (extensionTypes, materialExtensions);
        }
        private void ApplyExtensions(List<OvrAvatarMaterialExtension> materialExtensions)
        {
            Profiler.BeginSample("OvrAvatarPrimitive.ApplyExtensions");
            foreach (var extension in materialExtensions)
            {
                extension.ApplyEntriesToMaterial(material, _shaderConfig.ExtensionConfiguration);
                extension.Dispose();
            }
            Profiler.EndSample();   // "ApplyExtensions"
        }
        private bool WaitForTask(Task task, out OvrTime.SliceStep step)
        {
            // TODO: isCancelled should be mostly unnecessary here.... mostly.
            if (isCancelled || task.Status == TaskStatus.Faulted)
            {
                step = OvrTime.SliceStep.Cancel;
                LogTaskErrors(task);
                return true;
            }

            if (!task.IsCompleted)
            {
                step = OvrTime.SliceStep.Delay;
                return true;
            }

            step = OvrTime.SliceStep.Continue;
            return false;
        }

        private bool AllTasksFinished(List<Task> tasks)
        {
            foreach (Task task in tasks)
            {
                if (task is { IsCompleted: false }) return false;
            }

            return true;
        }

        private bool AllTasksSucceeded(List<Task> tasks)
        {
            foreach (Task task in tasks)
            {
                if (task != null && (!task.IsCompleted || task.Status == TaskStatus.Faulted)) return false;
            }

            return true;
        }

        private bool AnyTasksFaulted(List<Task> tasks)
        {
            foreach (Task task in tasks)
            {
                if (task is { Status: TaskStatus.Faulted }) { return true; }
            }

            return false;
        }

        private void LogTaskErrors(Task task)
        {
            foreach (var e in task.Exception.InnerExceptions)
            {
                OvrAvatarLog.LogError($"{e.Message}\n{e.StackTrace}", primitiveLogScope);
            }
        }

        // Helper method for matching imageData to textureData, allows use of local references
        private IEnumerator<bool> FindTextures(OvrAvatarResourceLoader loader, MaterialInfo materialInfo, OvrAvatarImage[] images, CAPI.ovrAvatar2Id resourceId)
        {
            for (uint imageIndex = 0; imageIndex < images.Length; ++imageIndex)
            {
                var imageData = materialInfo.imageData[imageIndex];

                {
                    using var findTextureScope = s_markers.FindTextureDataMarker.Auto();
                    for (var texIdx = 0; texIdx < materialInfo.texturesData.Length; ++texIdx)
                    {
                        var textureData = materialInfo.texturesData[texIdx];

                        if (textureData.imageId == imageData.id)
                        {
                            OvrAvatarLog.LogVerbose(
                                $"Found match for image index {imageIndex} to texture index {texIdx}",
                                primitiveLogScope);
                            // Resolve the image now.
                            OvrAvatarImage image;
                            if (!OvrAvatarManager.GetOvrAvatarAsset(imageData.id, out image))
                            {
                                OvrAvatarLog.LogVerbose($"Created image for id {imageData.id}", primitiveLogScope);
                                image = loader.CreateImage(in textureData, in imageData, imageIndex, resourceId);
                            }

                            OvrAvatarLog.Assert(image != null, primitiveLogScope);
                            images[imageIndex] = image;

                            break;
                        }
                    }

                    if (images[imageIndex] == null)
                    {
                        OvrAvatarLog.LogWarning($"Failed to find textures data for image {imageData.id}", primitiveLogScope);
                        // TODO: Assign some sort of fallback image?
                    }
                }
                if (OvrTime.ShouldHold) { yield return false; }
            }
        }

        #endregion

        private CancellationToken GetCancellationToken()
        {
            return _cancellationTokenSource.Token;
        }

        private void StripExcludedSubMeshes(ref NativeArray<ushort> triangles)
        {
            var ct = GetCancellationToken();
            ct.ThrowIfCancellationRequested();

            if (subMeshInclusionFlags != CAPI.ovrAvatar2EntitySubMeshInclusionFlags.All)
            {
                uint subMeshCount = 0;
                var countResult = CAPI.ovrAvatar2Primitive_GetSubMeshCount(assetId, out subMeshCount);
                ct.ThrowIfCancellationRequested();

                if (countResult.IsSuccess())
                {
                    unsafe
                    {
                        for (uint subMeshIndex = 0; subMeshIndex < subMeshCount; subMeshIndex++)
                        {
                            CAPI.ovrAvatar2PrimitiveSubmesh subMesh;
                            var subMeshResult =
                                CAPI.ovrAvatar2Primitive_GetSubMeshByIndex(assetId, subMeshIndex, out subMesh);
                            ct.ThrowIfCancellationRequested();
                            if (subMeshResult.IsSuccess())
                            {
                                // TODO this should honor the _activeSubMeshesIncludeUntyped flag
                                // ^ This is not possible as that is an OvrAvatarEntity flag
                                var inclusionType = subMesh.inclusionFlags;
                                if ((inclusionType & subMeshInclusionFlags) == 0 &&
                                    inclusionType != CAPI.ovrAvatar2EntitySubMeshInclusionFlags.None)
                                {
                                    uint triangleIndex = subMesh.indexStart;
                                    for (uint triangleCount = 0; triangleCount < subMesh.indexCount; triangleCount++)
                                    {
                                        // current strategy is to degenerate the triangle...
                                        int triangleBase = (int)(triangleIndex + triangleCount);
                                        triangles[triangleBase] = 0;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        private void GetLodInfo()
        {
            lod = LOD_INVALID;

            var result = CAPI.ovrAvatar2Asset_GetLodFlags(assetId, out var lodFlag);
            if (result.IsSuccess())
            {
                lodFlags = lodFlag;

                // TODO: Handle lods as flags, not a single int. Until then, take the highest quality lod available (lowest bit)
                const UInt32 highBit = (UInt32)CAPI.ovrAvatar2EntityLODFlags.LOD_4;
                UInt32 flagValue = (UInt32)lodFlag;

                int i = 0, maskValue = 1 << 0;
                do
                {
                    if ((flagValue & maskValue) != 0)
                    {
                        lod = i;
                        break;
                    }

                    maskValue = 1 << ++i;
                } while (maskValue <= highBit);
            }
        }

        private void GetViewInfo()
        {
            var result = CAPI.ovrAvatar2Asset_GetViewFlags(assetId, out var flags);
            if (result.IsSuccess())
            {
                viewFlags = flags;
            }
            else
            {
                OvrAvatarLog.LogWarning($"GetViewFlags Failed: {result}", primitiveLogScope);
            }
        }

        private void GetManifestationInfo()
        {
            var result = CAPI.ovrAvatar2Asset_GetManifestationFlags(assetId, out var flags);
            if (result.IsSuccess())
            {
                manifestationFlags = flags;
            }
            else
            {
                OvrAvatarLog.LogWarning($"GetManifestationFlags Failed: {result}", primitiveLogScope);
            }
        }

        private void GetSubMeshInclusionInfo()
        {
            // sub mesh inclusion flags used at this stage will work as load filters,
            // they must be specified in the creationInfo of the AvatarEntity before loading.
            var result = CAPI.ovrAvatar2Asset_GetSubMeshInclusionFlags(assetId, out var flags);
            if (result.IsSuccess())
            {
                subMeshInclusionFlags = flags;
            }
            else
            {
                OvrAvatarLog.LogWarning($"GetSubMeshInclusionInfo Failed: {result}", primitiveLogScope);
            }
        }

        private void GetQualityInfo()
        {
            var result = CAPI.ovrAvatar2Asset_GetQuality(assetId, out var flags);
            if (result.IsSuccess())
            {
                quality = flags;
            }
            else
            {
                OvrAvatarLog.LogWarning($"GetQuality Failed: {result}", primitiveLogScope);
            }
        }

        /////////////////////////////////////////////////
        //:: Vertex Buffer API
        // TODO: Factor out into its own file, currently meshInfo access is required for that.

        private void CreateVertexBuffer(MeshInfo meshInfo)
        {
            unsafe
            {
                // Apply mesh info on main thread
                // Get the vertex format information from the fetched vertex data.
                // We need to build a dynamic layout based on the actual data present.
                var vertexCount = (int)meshInfo.vertexCount;
                var vertexFormat = GetVertexFormat(meshInfo, out var vertexStrides);

                var vertices = new NativeArray<byte>[VF_STREAM_COUNT];
                // always have positions of some sort
                vertices[VF_STREAM_0] = new NativeArray<byte>(vertexStrides[VF_STREAM_0] * vertexCount, _nativeAllocator, _nativeArrayInit);

                // VF_STREAM_1 is a direct copy from SDK to Unity, so nothing to do here

                // may or may not have a stream 2, we wont if using compute skinner
                if (vertexStrides[VF_STREAM_2] > 0)
                {
                    vertices[VF_STREAM_2] = new NativeArray<byte>(vertexStrides[VF_STREAM_2] * vertexCount, _nativeAllocator, _nativeArrayInit);

                }

                // Create a vertex buffer using the format and stride.
                meshInfo.VertexBufferFormat = new VertexBufferFormat
                (
                    /* vertexFormat = */ vertexFormat,
                    /* vertexCount = */ vertexCount,
                    /* vertexStrides = */ vertexStrides,
                    /* vertexLayout = */ CreateVertexLayout(vertexFormat, meshInfo),
                    /* vertexStreams = */ vertices
                );
            }
        }

        private VertexFormat GetVertexFormat(MeshInfo meshInfo, out VertexBufferFormat.VertexBufferStrides vertexStrides)
        {
            // TODO: Support different attribute formats rather than hardcoding them. This will be useful for quantizing
            // vertex data to reduce vertex shader read bandwidth.
            // TODO: Use constants for vector and color sizes.
            VertexFormat vertexFormat = VertexFormat.VF_POSITION;
            vertexStrides = default;

            if (meshInfo.verts.IsCreated && meshInfo.verts.Length > 0)
            {
                vertexStrides[VF_STREAM_0] = 3 * sizeof(float);
            }
            else
            {
                // don't actually need positions, just stand in garbage data to keep unity happy
                vertexStrides[VF_STREAM_0] = sizeof(UInt32);
            }

            if (OvrAvatarManager.Instance.UnitySMRSupported)
            {
                if (meshInfo.normals.IsCreated && meshInfo.normals.Length > 0)
                {
                    vertexFormat |= VertexFormat.VF_NORMAL;
                    vertexStrides[VF_STREAM_0] += 3 * sizeof(float);
                }
                if (meshInfo.hasTangents && meshInfo.tangents.Length > 0)
                {
                    vertexFormat |= VertexFormat.VF_TANGENT;
                    vertexStrides[VF_STREAM_0] += 4 * sizeof(float);
                }
            }

            if (meshInfo.staticAttributes.Length > 0)
            {
                if (meshInfo.hasColors)
                {
                    vertexFormat |= VertexFormat.VF_COLOR;
                    vertexStrides[VF_STREAM_1] += 4;
                }
                if (meshInfo.hasTextureCoords)
                {
                    vertexFormat |= VertexFormat.VF_TEXCOORD0;
                    vertexStrides[VF_STREAM_1] += 2 * sizeof(UInt16);
                }
                if (meshInfo.hasProperties)
                {
                    vertexFormat |= VertexFormat.VF_COLOR_ORMT;
                    vertexStrides[VF_STREAM_1] += 4;
                }
                if (meshInfo.hasCurvature)
                {
                    vertexFormat |= VertexFormat.VF_COLOR_CURVATURE;
                    vertexStrides[VF_STREAM_1] += 2 * sizeof(UInt16);
                }
            }
            if (data.jointCount > 0 && OvrAvatarManager.Instance.UnitySMRSupported)
            {
                vertexFormat |= (VertexFormat.VF_BONE_WEIGHTS | VertexFormat.VF_BONE_INDICES);
                vertexStrides[VF_STREAM_2] += 4 * sizeof(float);    // weights
                vertexStrides[VF_STREAM_2] += 4;    // bone indices
            }

            OvrAvatarLog.LogVerbose(
                $"Vertex Format = {vertexFormat}, Strides = [{vertexStrides[VF_STREAM_0]}, {vertexStrides[VF_STREAM_1]}, {vertexStrides[VF_STREAM_2]}]",
                primitiveLogScope);
            return vertexFormat;
        }

        private VertexAttributeDescriptor[] CreateVertexLayout(VertexFormat format, MeshInfo meshInfo)
        {
            const int kMinDescriptorLimit = 8;
            const int kMaxDescriptors
#if UNITY_EDITOR || UNITY_STANDALONE_WIN
                = 10;
#else // ^^^ UNITY_EDITOR || WIN / !UNITY_EDITOR && !WIN vvv
                = 8;
#endif // !UNITY_EDITOR && !WIN

            var numDescriptorsNeeded = ((UInt32)format).PopCount();
            if (numDescriptorsNeeded > kMaxDescriptors)
            {
                // explicit check to avoid building log-string when condition passes
                // ReSharper disable once ConditionIsAlwaysTrueOrFalse
                Debug.Assert(numDescriptorsNeeded <= kMaxDescriptors
                    , $"Needed {numDescriptorsNeeded} vertex attribute descriptors but limit is {kMaxDescriptors}!");
            }
            if (numDescriptorsNeeded > kMinDescriptorLimit)
            {
                OvrAvatarLog.LogWarning(
                    $"Need {numDescriptorsNeeded} vertex attribute descriptors which may exceed limit of {kMinDescriptorLimit} on some platforms!");
            }

            // TODO: Support different attribute formats rather than hardcoding them.
            // This will be useful for quantizing vertex data to reduce vertex shader read bandwidth.
            var vertexLayout = new VertexAttributeDescriptor[(int)numDescriptorsNeeded];

            int numDescriptors = 0;
            // Note: Unity expects vertex attributes to exist in a specific order, any deviation causes an error.
            // Order: Position, Normal, Tangent, Color, TexCoord0, TexCoord1, ..., BlendWeights, BlendIndices
            if ((format & VertexFormat.VF_POSITION) == VertexFormat.VF_POSITION)
            {
                if (meshInfo.verts.IsCreated && meshInfo.verts.Length > 0)
                {
                    vertexLayout[numDescriptors++] =
                        new VertexAttributeDescriptor(VertexAttribute.Position, VertexAttributeFormat.Float32, 3, VF_STREAM_0);
                }
                else
                {
                    // just some stand in garbage values to keep Unity happy. need 4 elements because Unity also requires 4 byte alignment.
                    // Not perfect, but 4 bytes instead of 12 isn't too bad.
                    vertexLayout[numDescriptors++] =
                        new VertexAttributeDescriptor(VertexAttribute.Position, VertexAttributeFormat.SNorm8, 4, VF_STREAM_0);
                }
            }
            if ((format & VertexFormat.VF_NORMAL) == VertexFormat.VF_NORMAL)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.Normal, VertexAttributeFormat.Float32, 3, VF_STREAM_0);
            }
            if ((format & VertexFormat.VF_TANGENT) == VertexFormat.VF_TANGENT)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.Tangent, VertexAttributeFormat.Float32, 4, VF_STREAM_0);
            }
            if ((format & VertexFormat.VF_COLOR) == VertexFormat.VF_COLOR)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.Color, VertexAttributeFormat.UNorm8, 4, VF_STREAM_1);
            }
            if ((format & VertexFormat.VF_TEXCOORD0) == VertexFormat.VF_TEXCOORD0)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.TexCoord0, VertexAttributeFormat.UNorm16, 2, VF_STREAM_1);
            }
            if ((format & VertexFormat.VF_COLOR_ORMT) == VertexFormat.VF_COLOR_ORMT)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.TexCoord1, VertexAttributeFormat.UNorm8, 4, VF_STREAM_1);
            }
            if ((format & VertexFormat.VF_COLOR_CURVATURE) == VertexFormat.VF_COLOR_CURVATURE)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.TexCoord2, VertexAttributeFormat.UNorm16, 2, VF_STREAM_1);
            }
            if ((format & VertexFormat.VF_BONE_WEIGHTS) == VertexFormat.VF_BONE_WEIGHTS)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.BlendWeight, VertexAttributeFormat.Float32, 4, VF_STREAM_2);
            }
            if ((format & VertexFormat.VF_BONE_INDICES) == VertexFormat.VF_BONE_INDICES)
            {
                vertexLayout[numDescriptors++] =
                    new VertexAttributeDescriptor(VertexAttribute.BlendIndices, VertexAttributeFormat.UInt8, 4, VF_STREAM_2);
            }

            Debug.Assert(numDescriptors > 0);
            Debug.Assert(numDescriptors == numDescriptorsNeeded);
            return vertexLayout;
        }

        private void CopyMeshDataIntoVertexBufferAndDispose(MeshInfo meshInfo)
        {
            var vertexBuffer = meshInfo.VertexBufferFormat;
            // Stream 1 is handled elsewhere, just look at stream 0 and 2 attributes.
            var vertexFormat = vertexBuffer.vertexFormat & (VertexFormat.VF_POSITION | VertexFormat.VF_NORMAL | VertexFormat.VF_TANGENT | VertexFormat.VF_BONE_WEIGHTS | VertexFormat.VF_BONE_INDICES);

            unsafe
            {
                // If using the compute skinner, and only the compute skinner, there won't be much work to do here. Stream 1 is handled elsewhere, and stream 0 and 2 aren't used.
                // we do have to fill out positions to keep unity happy in stream 0, even though it isn't used, but that will just be a single 0 uint32_t per vert.
                bool canFastPath = (vertexFormat == VertexFormat.VF_POSITION) && (!meshInfo.verts.IsCreated || meshInfo.verts.IsNull() || meshInfo.verts.Length == 0);

                if (canFastPath)
                {
                    var outBuffer = vertexBuffer.vertexStreams[VF_STREAM_0].GetPtr();
                    UnsafeUtility.MemClear(outBuffer, vertexBuffer.vertexCount * sizeof(UInt32));

                    meshInfo.MeshVertsComplete();
                    meshInfo.MeshNormalsComplete();
                    meshInfo.MeshTangentsComplete();
                    meshInfo.MeshBoneWeightsComplete();
                }
                else
                {
                    // VF_STREAM_0
                    if ((vertexFormat & (VertexFormat.VF_POSITION | VertexFormat.VF_NORMAL | VertexFormat.VF_TANGENT)) != 0)
                    {
                        var vertexStride = vertexBuffer.vertexStrides[VF_STREAM_0];

                        var vertsPtr = meshInfo.verts.IsCreated && !meshInfo.verts.IsNull() && meshInfo.verts.Length > 0
                                ? (Vector3*)meshInfo.verts.GetPtr() : null;
                        Vector3* normsPtr =
                            meshInfo.normals.IsCreated && !meshInfo.normals.IsNull() && meshInfo.normals.Length > 0
                                ? (Vector3*)meshInfo.normals.GetPtr() : null;
                        var tangsPtr =
                            meshInfo.tangents.IsCreated && !meshInfo.tangents.IsNull() && meshInfo.tangents.Length > 0
                                ? (Vector4*)meshInfo.tangents.GetPtr() : null;

                        Vector4 defaultTangent = Vector3.forward;
                        Vector3 defaultNormal = Vector3.forward;
                        Vector3 defaultPos = Vector3.zero;

                        var outBuffer = vertexBuffer.vertexStreams[VF_STREAM_0].GetPtr();
                        for (int i = 0; i < vertexBuffer.vertexCount; i++)
                        {
                            byte* outBufferOffset = outBuffer + (vertexStride * i);
                            if ((vertexFormat & VertexFormat.VF_POSITION) == VertexFormat.VF_POSITION)
                            {
                                if (vertsPtr != null)
                                {
                                    const int kPositionSize = 3 * sizeof(float);
                                    Vector3* outPos = (Vector3*)outBufferOffset;
                                    *outPos = vertsPtr != null ? vertsPtr[i] : defaultPos;
                                    outBufferOffset += kPositionSize;
                                }
                                else
                                {
                                    //dummy data to keep Unity happy, while using as little memory as possible
                                    const int kPositionSize = sizeof(UInt32);
                                    UInt32* outPos = (UInt32*)outBufferOffset;
                                    *outPos = 0;
                                    outBufferOffset += kPositionSize;
                                }
                            }

                            if ((vertexFormat & VertexFormat.VF_NORMAL) == VertexFormat.VF_NORMAL)
                            {
                                const int kNormalSize = 3 * sizeof(float);
                                Vector3* outNrm = (Vector3*)outBufferOffset;
                                *outNrm = normsPtr != null ? normsPtr[i] : defaultNormal;
                                outBufferOffset += kNormalSize;
                            }

                            if ((vertexFormat & VertexFormat.VF_TANGENT) == VertexFormat.VF_TANGENT)
                            {
                                const int kTangentSize = 4 * sizeof(float);
                                Vector4* outTan = (Vector4*)outBufferOffset;
                                *outTan = tangsPtr != null ? tangsPtr[i] : defaultTangent;
                                outBufferOffset += kTangentSize;
                            }
                        }

                        meshInfo.MeshVertsComplete();
                        meshInfo.MeshNormalsComplete();
                        meshInfo.MeshTangentsComplete();
                    }

                    // VF_STREAM_2
                    if ((vertexFormat & (VertexFormat.VF_BONE_WEIGHTS | VertexFormat.VF_BONE_INDICES)) != 0)
                    {
                        var vertexStride = vertexBuffer.vertexStrides[VF_STREAM_2];

                        var outBuffer = vertexBuffer.vertexStreams[VF_STREAM_2].GetPtr();
                        fixed (BoneWeight* boneWeightsPtr = meshInfo.boneWeights)
                        {
                            for (int i = 0; i < vertexBuffer.vertexCount; i++)
                            {
                                byte* outBufferOffset = outBuffer + (vertexStride * i);
                                var boneWeightPtr = boneWeightsPtr + i;
                                if ((vertexFormat & VertexFormat.VF_BONE_WEIGHTS) == VertexFormat.VF_BONE_WEIGHTS)
                                {
                                    const int kBoneWeightSize = 4 * sizeof(float);
                                    Vector4* outWeights = (Vector4*)outBufferOffset;
                                    outWeights->x = boneWeightPtr->weight0;
                                    outWeights->y = boneWeightPtr->weight1;
                                    outWeights->z = boneWeightPtr->weight2;
                                    outWeights->w = boneWeightPtr->weight3;
                                    outBufferOffset += kBoneWeightSize;
                                }

                                if ((vertexFormat & VertexFormat.VF_BONE_INDICES) == VertexFormat.VF_BONE_INDICES)
                                {
                                    const int kBoneIndexSize = 4;
                                    Color32* outIndices = (Color32*)outBufferOffset;
                                    outIndices->r = (byte)boneWeightPtr->boneIndex0;
                                    outIndices->g = (byte)boneWeightPtr->boneIndex1;
                                    outIndices->b = (byte)boneWeightPtr->boneIndex2;
                                    outIndices->a = (byte)boneWeightPtr->boneIndex3;
                                    outBufferOffset += kBoneIndexSize;
                                }
                            }
                        }

                        meshInfo.MeshBoneWeightsComplete();
                    } // VF_STREAM_2
                }
            }
        }

        private static void DisposeVertexBuffer(MeshInfo meshInfo)
        {
            if (meshInfo?.VertexBufferFormat.vertexStreams != null)
            {
                for (int i = 0; i < VF_STREAM_COUNT; ++i)
                {
                    meshInfo.VertexBufferFormat.vertexStreams[i].Reset();
                }
            }
        }

        /////////////////////////////////////////////////
        //:: Build Mesh

        private void RetrieveTriangles(MeshInfo meshInfo)
        {
            // Get index buffer, we will use this to strip out data for other LODs
            var triangles = CreateIndexBuffer(data);
            if (!triangles.IsCreated)
            {
                throw new Exception("RetrieveTriangles failed");
            }

            meshInfo.SetTrianglesBuffer(triangles);

            // TODO: Confirm topology - we only currently support triangle
            triCount = (uint)(meshInfo.triangles.Length / 3);
        }

        private void RetrieveMeshData(MeshInfo meshInfo, bool usesComputeSkinnerOnly, bool disableMeshOptimization)
        {
            var ct = GetCancellationToken();
            ct.ThrowIfCancellationRequested();

            // Apply Data
            meshInfo.vertexCount = _bufferVertexCount;


            meshInfo.staticAttributes = CreateVertexStaticData(meshInfo, ct);

            // Ideally we won't upload positions. However Unity does require some minimal placeholder values,
            // so we will just put 4 bytes of garbage data in positions by default. There are a few cases
            // where we will need to turn this optimization off though.
            bool keepPositions = false;
            // need to keep positions if mesh optimization is disabled
            keepPositions = keepPositions || disableMeshOptimization;
            // need to keep positions if using any other skinners other than the compute skinner
            keepPositions = keepPositions || !usesComputeSkinnerOnly;
            // Have to keep positions if in the editor.
#if UNITY_EDITOR
            keepPositions = true;
#endif

            if (keepPositions)
            {
                meshInfo.SetVertexBuffer(CreateVertexPositions(ct));
            }

            // All of these aren't needed if only using the compute skinner
            if (!usesComputeSkinnerOnly)
            {
                meshInfo.SetNormalsBuffer(CreateVertexNormals(ct));
                meshInfo.SetTangentsBuffer(CreateVertexTangents(ct));
                meshInfo.SetBoneWeights(data.jointCount > 0 ? RetrieveBoneWeights(ct) : null);
            }
        }

        private void InvokeOnMeshLoaded(Mesh sourceMesh, MeshInfo meshInfo)
        {
            OvrAvatarLog.LogInfo("InvokeOnAvatarMeshLoaded", primitiveLogScope, OvrAvatarManager.Instance);
            Profiler.BeginSample("OvrAvatarManager::InvokeOnAvatarMeshLoaded Callbacks");
            try
            {
                if (OvrAvatarManager.Instance.HasMeshLoadListener)
                {
                    var destMesh = new OvrAvatarManager.MeshData(
                        sourceMesh.name,
                        sourceMesh.triangles,
                        // We want to decouple the GPU vertex representation from the CPU representation.
                        // So instead of reading from the mesh directly, we read from the internal mesh info.
                        (meshInfo.verts.IsCreated) ? meshInfo.verts.ToArray() : Array.Empty<Vector3>(),
                        (meshInfo.normals.IsCreated) ? meshInfo.normals.ToArray() : Array.Empty<Vector3>(),
                        (meshInfo.tangents.IsCreated) ? meshInfo.tangents.ToArray() : Array.Empty<Vector4>(),
                        meshInfo.boneWeights,
                        // Bind poses are not part of the vertex data.
                        sourceMesh.bindposes
                    );
                    OvrAvatarManager.Instance.InvokeMeshLoadEvent(this, destMesh);
                }
            }
            catch (Exception e)
            {
                OvrAvatarLog.LogException(
                    "OnAvatarMeshLoaded user callback", e, primitiveLogScope,
                    OvrAvatarManager.Instance);
            }
            finally { Profiler.EndSample(); }
        }

        #region Retrieve Primitive Data

        private delegate CAPI.ovrAvatar2Result VertexBufferAccessor(
            CAPI.ovrAvatar2VertexBufferId vertexBufferId, IntPtr buffer, UInt32 bytes,
            UInt32 stride);

        private delegate CAPI.ovrAvatar2Result VertexBufferAccessorWithPrimId(
            CAPI.ovrAvatar2Id primitiveId, CAPI.ovrAvatar2VertexBufferId vertexBufferId, IntPtr buffer, UInt32 bytes,
            UInt32 stride);

        private NativeArray<T> CreateVertexData<T>(
            VertexBufferAccessor accessor
            , string accessorName, CancellationToken ct) where T : unmanaged
        {
            ct.ThrowIfCancellationRequested();

            NativeArray<T> vertsBufferArray = default;
            try
            {
                vertsBufferArray = new NativeArray<T>((int)bufferVertexCount, _nativeAllocator, _nativeArrayInit);
                IntPtr vertsBuffer = vertsBufferArray.GetIntPtr();

                if (vertsBuffer == IntPtr.Zero)
                {
                    OvrAvatarLog.LogError(
                        $"ERROR: Null buffer allocated for input during `{accessorName}` - aborting",
                        primitiveLogScope);
                    return default;
                }

                var elementSize = UnsafeUtility.SizeOf<T>();
                UInt32 stride = (UInt32)elementSize;
                UInt32 bufferSize = vertsBufferArray.GetBufferSize(elementSize);
                var result = accessor(
                    data.vertexBufferId, vertsBuffer, bufferSize, stride);

                switch (result)
                {
                    case CAPI.ovrAvatar2Result.Success:
                        var resultBuffer = vertsBufferArray;
                        vertsBufferArray = default;
                        return resultBuffer;

                    case CAPI.ovrAvatar2Result.DataNotAvailable:
                        return default;

                    default:
                        OvrAvatarLog.LogError($"{accessorName} {result}", primitiveLogScope);
                        return default;
                }
            }
            finally { vertsBufferArray.Reset(); }
        }

        private NativeArray<T> CreateVertexDataWithPrimId<T>(VertexBufferAccessorWithPrimId accessor
            , string accessorName, CancellationToken ct) where T : unmanaged
        {
            ct.ThrowIfCancellationRequested();

            NativeArray<T> vertsBufferArray = default;
            try
            {
                vertsBufferArray = new NativeArray<T>((int)bufferVertexCount, _nativeAllocator, _nativeArrayInit);
                {
                    var elementSize = UnsafeUtility.SizeOf<T>();
                    var vertsBuffer = vertsBufferArray.GetIntPtr();
                    if (vertsBuffer == IntPtr.Zero)
                    {
                        OvrAvatarLog.LogError(
                            $"ERROR: Null buffer allocated for input during `{accessorName}` - aborting",
                            primitiveLogScope);
                        return default;
                    }

                    var bufferSize = vertsBufferArray.GetBufferSize(elementSize);
                    var stride = (UInt32)elementSize;

                    var result = accessor(data.id, data.vertexBufferId, vertsBuffer, bufferSize, stride);
                    var resultBuffer = vertsBufferArray;
                    vertsBufferArray = default;
                    return resultBuffer;
                }
            }
            finally { vertsBufferArray.Reset(); }
        }

        private NativeArray<Vector3> CreateVertexPositions(CancellationToken ct)
        {
            return CreateVertexData<Vector3>(
                CAPI.ovrAvatar2VertexBuffer_GetPositions, "GetVertexPositions", ct);
        }

        private NativeArray<Vector3> CreateVertexNormals(CancellationToken ct)
        {
            return CreateVertexData<Vector3>(
                CAPI.ovrAvatar2VertexBuffer_GetNormals, "GetVertexNormals", ct);
        }

        private NativeArray<Vector4> CreateVertexTangents(CancellationToken ct)
        {
            return CreateVertexData<Vector4>(
                CAPI.ovrAvatar2VertexBuffer_GetTangents, "GetVertexTangents", ct);
        }

        private NativeArray<byte> CreateVertexStaticData(MeshInfo meshInfo, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();

            NativeArray<byte> resultBuffer = default;
            NativeArray<ovrAvatar2BufferMetaData> metaData = default;
            try
            {
                metaData = new NativeArray<ovrAvatar2BufferMetaData>(ovrAvatar2CompactMeshAttributesCount, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);

                UInt64 dataBufferSize;
                if (!OvrCompactMeshData_GetMetaData(data.vertexBufferId, ovrAvatar2CompactMeshAttributes.All, metaData, out dataBufferSize))
                {
                    OvrAvatarLog.LogError($"Failed to retrieve static mesh meta data from Avatar SDK", primitiveLogScope);
                    return default;
                }

                if (metaData[0].dataFormat != ovrAvatar2DataFormat.Invalid)
                {
                    meshInfo.hasColors = true;
                }

                if (metaData[1].dataFormat != ovrAvatar2DataFormat.Invalid)
                {
                    meshInfo.hasTextureCoords = true;
                }

                if (metaData[2].dataFormat != ovrAvatar2DataFormat.Invalid)
                {
                    meshInfo.hasProperties = true;
                }

                if (metaData[3].dataFormat != ovrAvatar2DataFormat.Invalid)
                {
                    meshInfo.hasCurvature = true;
                }

                resultBuffer = new NativeArray<byte>((int)dataBufferSize, _nativeAllocator, NativeArrayOptions.UninitializedMemory);

                unsafe
                {
                    ovrAvatar2DataBlock dataBlock;
                    dataBlock.data = resultBuffer.GetPtr();
                    dataBlock.size = dataBufferSize;
                    if (!OvrCompactMeshData_CopyBuffer(this.assetId, data.vertexBufferId, ovrAvatar2CompactMeshAttributes.All, dataBlock))
                    {
                        OvrAvatarLog.LogError($"Failed to retrieve static mesh attributes from Avatar SDK", primitiveLogScope);
                        resultBuffer.Dispose();
                        return default;
                    }
                }
            }
            finally
            {
                metaData.Reset();
            }

            return resultBuffer;
        }

        private BoneWeight[] RetrieveBoneWeights(CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();

            var vec4usStride = (UInt32)UnsafeUtility.SizeOf<CAPI.ovrAvatar2Vector4us>();
            var vec4fStride = (UInt32)UnsafeUtility.SizeOf<CAPI.ovrAvatar2Vector4f>();

            var indicesBuffer =
                new NativeArray<CAPI.ovrAvatar2Vector4us>((int)bufferVertexCount, _nativeAllocator, _nativeArrayInit);
            var weightsBuffer =
                new NativeArray<CAPI.ovrAvatar2Vector4f>((int)bufferVertexCount, _nativeAllocator, _nativeArrayInit);

            try
            {
                IntPtr indicesPtr = indicesBuffer.GetIntPtr();
                IntPtr weightsPtr = weightsBuffer.GetIntPtr();

                if (indicesPtr == IntPtr.Zero || weightsPtr == IntPtr.Zero)
                {
                    OvrAvatarLog.LogError(
                        "ERROR: Null buffer allocated for input during `RetrieveBoneWeights` - aborting",
                        primitiveLogScope);
                    return Array.Empty<BoneWeight>();
                }

                var indicesBufferSize = indicesBuffer.GetBufferSize(vec4usStride);
                var weightsBufferSize = weightsBuffer.GetBufferSize(vec4fStride);

                var result = CAPI.ovrAvatar2VertexBuffer_GetJointIndices(
                    data.vertexBufferId, indicesPtr, indicesBufferSize, vec4usStride);
                ct.ThrowIfCancellationRequested();
                if (result == CAPI.ovrAvatar2Result.DataNotAvailable) { return Array.Empty<BoneWeight>(); }
                else if (!result.EnsureSuccess("ovrAvatar2VertexBuffer_GetJointIndices", primitiveLogScope))
                {
                    return null;
                }

                result = CAPI.ovrAvatar2VertexBuffer_GetJointWeights(
                    data.vertexBufferId, weightsPtr,
                    weightsBufferSize, vec4fStride);
                ct.ThrowIfCancellationRequested();
                if (result == CAPI.ovrAvatar2Result.DataNotAvailable) { return Array.Empty<BoneWeight>(); }
                else if (!result.EnsureSuccess("ovrAvatar2VertexBuffer_GetJointWeights", primitiveLogScope))
                {
                    return null;
                }

                ct.ThrowIfCancellationRequested();

                using (var boneWeightsSrc =
                       new NativeArray<BoneWeight>((int)bufferVertexCount, _nativeAllocator, _nativeArrayInit))
                {
                    unsafe
                    {
                        var srcPtr = boneWeightsSrc.GetPtr();

                        // Check for allocation failure
                        if (srcPtr == null)
                        {
                            OvrAvatarLog.LogError(
                                "ERROR: Null buffer allocated for output during `RetrieveBoneWeights` - aborting",
                                primitiveLogScope);
                            return Array.Empty<BoneWeight>();
                        }

                        var indices = indicesBuffer.GetPtr();
                        var weights = weightsBuffer.GetPtr();

                        for (int i = 0; i < bufferVertexCount; ++i)
                        {
                            ref CAPI.ovrAvatar2Vector4us jointIndex = ref indices[i];
                            ref CAPI.ovrAvatar2Vector4f jointWeight = ref weights[i];

                            srcPtr[i] = new BoneWeight
                            {
                                boneIndex0 = jointIndex.x,
                                boneIndex1 = jointIndex.y,
                                boneIndex2 = jointIndex.z,
                                boneIndex3 = jointIndex.w,
                                weight0 = jointWeight.x,
                                weight1 = jointWeight.y,
                                weight2 = jointWeight.z,
                                weight3 = jointWeight.w
                            };
                        }
                    }

                    ct.ThrowIfCancellationRequested();

                    return boneWeightsSrc.ToArray();
                }
            }
            finally
            {
                indicesBuffer.Dispose();
                weightsBuffer.Dispose();
            }
        }

        private NativeArray<UInt16> CreateIndexBuffer(in CAPI.ovrAvatar2Primitive prim)
        {
            var ct = GetCancellationToken();
            ct.ThrowIfCancellationRequested();

            NativeArray<UInt16> triBuffer = default;
            try
            {
                triBuffer = new NativeArray<UInt16>((int)data.indexCount, _nativeAllocator, _nativeArrayInit);

                UInt32 bufferSize = triBuffer.GetBufferSize(sizeof(UInt16));
                bool result = CAPI.OvrAvatar2Primitive_GetIndexData(assetId, in triBuffer, bufferSize);
                if (!result)
                {
                    return default;
                }

                ct.ThrowIfCancellationRequested();
                return triBuffer;
            }
            finally { }
        }

        #endregion

        /////////////////////////////////////////////////
        //:: Build Material

        #region Build Material

        private void Material_GetTexturesData(CAPI.ovrAvatar2Id resourceId, ref MaterialInfo materialInfo)
        {
            var ct = GetCancellationToken();
            ct.ThrowIfCancellationRequested();

            CAPI.ovrAvatar2Result result;

            // Get data for all textures
            materialInfo.texturesData = new CAPI.ovrAvatar2MaterialTexture[data.textureCount];
            for (UInt32 i = 0; i < data.textureCount; ++i)
            {
                ref var materialTexture = ref materialInfo.texturesData[i];
                result = CAPI.ovrAvatar2Primitive_GetMaterialTextureByIndex(assetId, i, out materialTexture);
                ct.ThrowIfCancellationRequested();
                if (!result.EnsureSuccess("ovrAvatar2Primitive_GetMaterialTextureByIndex with index: " + i, primitiveLogScope))
                {
                    materialInfo.texturesData[i] = default;
                    continue;
                }

                if (materialTexture.type == CAPI.ovrAvatar2MaterialTextureType.MetallicRoughness)
                {
                    materialInfo.hasMetallic = true;
                }
            }

            // Get data for all images
            result = CAPI.ovrAvatar2Asset_GetImageCount(resourceId, out UInt32 imageCount);
            ct.ThrowIfCancellationRequested();
            if (!result.EnsureSuccess("ovrAvatar2Asset_GetImageCount", primitiveLogScope))
            {
                return;
            }

            materialInfo.imageData = new CAPI.ovrAvatar2Image[imageCount];

            for (UInt32 i = 0; i < imageCount; ++i)
            {
                ref var imageData = ref materialInfo.imageData[i];
                result = CAPI.ovrAvatar2Asset_GetImageByIndex(resourceId, i, out imageData);
                ct.ThrowIfCancellationRequested();
                if (!result.EnsureSuccess("ovrAvatar2Asset_GetImageByIndex with index: " + i, primitiveLogScope))
                {
                    materialInfo.imageData[i] = default;
                    continue;
                }
            }
        }

        private void ApplyTexture(Texture2D texture, CAPI.ovrAvatar2MaterialTexture textureData)
        {
            switch (textureData.type)
            {
                case CAPI.ovrAvatar2MaterialTextureType.BaseColor:
                    if (!string.IsNullOrEmpty(_shaderConfig.NameTextureParameter_baseColorTexture))
                        material.SetTexture(_shaderConfig.IDTextureParameter_baseColorTexture, texture);
                    material.SetColor(
                        _shaderConfig.IDColorParameter_BaseColorFactor,
                        _shaderConfig.UseColorParameter_BaseColorFactor ? textureData.factor : Color.white);
                    material.mainTexture = texture;
                    break;

                case CAPI.ovrAvatar2MaterialTextureType.Normal:
                    if (!string.IsNullOrEmpty(_shaderConfig.NameTextureParameter_normalTexture))
                        material.SetTexture(_shaderConfig.IDTextureParameter_normalTexture, texture);
                    break;

                case CAPI.ovrAvatar2MaterialTextureType.Emissive:
                    if (!string.IsNullOrEmpty(_shaderConfig.NameTextureParameter_emissiveTexture))
                        material.SetTexture(_shaderConfig.IDTextureParameter_emissiveTexture, texture);
                    break;

                case CAPI.ovrAvatar2MaterialTextureType.Occulusion:
                    if (!string.IsNullOrEmpty(_shaderConfig.NameTextureParameter_occlusionTexture))
                        material.SetTexture(_shaderConfig.IDTextureParameter_occlusionTexture, texture);
                    break;

                case CAPI.ovrAvatar2MaterialTextureType.MetallicRoughness:
                    if (!string.IsNullOrEmpty(_shaderConfig.NameTextureParameter_metallicRoughnessTexture))
                        material.SetTexture(_shaderConfig.IDTextureParameter_metallicRoughnessTexture, texture);
                    material.SetFloat(
                        _shaderConfig.IDFloatParameter_MetallicFactor,
                        _shaderConfig.UseFloatParameter_MetallicFactor ? textureData.factor.x : 1f);
                    material.SetFloat(
                        _shaderConfig.IDFloatParameter_RoughnessFactor,
                        _shaderConfig.UseFloatParameter_RoughnessFactor ? textureData.factor.y : 1f);
                    break;

                case CAPI.ovrAvatar2MaterialTextureType.UsedInExtension:
                    // Let extensions handle it
                    break;
                default:
                    throw new ArgumentOutOfRangeException();
            }
        }

        public void Material_ExtractParameterData(Material unityMaterial)
        {
            var ct = GetCancellationToken();

            OvrAvatarSubMeshIdentification.ApplyArraysToMaterial(unityMaterial, ct, assetId);
        }

        #endregion

        /////////////////////////////////////////////////
        //:: Build Other Data

        private void SetupMorphTargets(MorphTargetInfo[] morphTargetInfo)
        {
            var ct = GetCancellationToken();
            ct.ThrowIfCancellationRequested();

            var sizeOfOvrVector3 = UnsafeUtility.SizeOf<CAPI.ovrAvatar2Vector3f>();
            UInt32 bufferSize = (UInt32)(sizeOfOvrVector3 * bufferVertexCount);
            UInt32 stride = (UInt32)sizeOfOvrVector3;

            if (morphTargetInfo.Length != morphTargetCount)
            {
                throw new Exception(
                    $"Incorrect morphTargetInfo[] size. Was {morphTargetInfo.Length}, but expected {morphTargetCount}");
            }

            unsafe
            {
                const int nameBufferLength = 255;
                byte* nameBuffer = stackalloc byte[nameBufferLength];

                var minLength = Mathf.Min(morphTargetCount, morphTargetInfo.Length);
                for (UInt32 iMorphTarget = 0; iMorphTarget < minLength; ++iMorphTarget)
                {
                    // Would be nice if we had a single simple CAPI that returned what attributes were available, one call to get all 3
                    // we want to figure out which are available before we spend time allocating giant buffers.
                    var positionsResult =
                        CAPI.ovrAvatar2MorphTarget_GetVertexPositions(
                            data.morphTargetBufferId, iMorphTarget,
                            null, 0, stride);
                    if (!positionsResult.IsSuccess())
                    {
                        OvrAvatarLog.LogError(
                            $"MorphTarget_GetVertexPositions ({iMorphTarget}) {positionsResult}",
                            primitiveLogScope);
                        continue;
                    }

                    var normalsResult =
                        CAPI.ovrAvatar2MorphTarget_GetVertexNormals(
                            data.morphTargetBufferId, iMorphTarget,
                            null, 0, stride);
                    bool normalsAvailable = normalsResult.IsSuccess();
                    if (!normalsAvailable && normalsResult != CAPI.ovrAvatar2Result.DataNotAvailable)
                    {
                        OvrAvatarLog.LogError(
                            $"MorphTarget_GetVertexNormals ({iMorphTarget}) {normalsResult}",
                            primitiveLogScope);
                        continue;
                    }

                    var tangentsResult =
                        CAPI.ovrAvatar2MorphTarget_GetVertexTangents(
                            data.morphTargetBufferId, iMorphTarget,
                            null, 0, stride);
                    bool tangentsAvailable = tangentsResult.IsSuccess();
                    if (!tangentsAvailable && tangentsResult != CAPI.ovrAvatar2Result.DataNotAvailable)
                    {
                        OvrAvatarLog.LogError(
                            $"MorphTarget_GetVertexTangents ({iMorphTarget}) {tangentsResult}",
                            primitiveLogScope);
                        continue;
                    }

                    ct.ThrowIfCancellationRequested();

                    NativeArray<Vector3> positionsArray = default;
                    NativeArray<Vector3> normalsArray = default;
                    NativeArray<Vector3> tangentsArray = default;
                    try
                    {
                        // Positions
                        positionsArray =
                            new NativeArray<Vector3>((int)bufferVertexCount, _nativeAllocator, _nativeArrayInit);

                        positionsResult =
                            CAPI.ovrAvatar2MorphTarget_GetVertexPositions(
                                data.morphTargetBufferId, iMorphTarget,
                                positionsArray.CastOvrPtr(), bufferSize, stride);
                        ct.ThrowIfCancellationRequested();
                        if (!positionsResult.IsSuccess())
                        {
                            OvrAvatarLog.LogError(
                                $"MorphTarget_GetVertexPositions ({iMorphTarget}) {positionsResult}",
                                primitiveLogScope);
                            continue;
                        }

                        // Normals
                        if (normalsAvailable)
                        {
                            normalsArray = new NativeArray<Vector3>(
                                (int)bufferVertexCount, _nativeAllocator,
                                _nativeArrayInit);

                            normalsResult =
                                CAPI.ovrAvatar2MorphTarget_GetVertexNormals(
                                    data.morphTargetBufferId, iMorphTarget,
                                    normalsArray.CastOvrPtr(), bufferSize, stride);
                            ct.ThrowIfCancellationRequested();
                            normalsAvailable = normalsResult.IsSuccess();
                            if (!normalsAvailable && normalsResult != CAPI.ovrAvatar2Result.DataNotAvailable)
                            {
                                OvrAvatarLog.LogError(
                                    $"MorphTarget_GetVertexNormals ({iMorphTarget}) {normalsResult}",
                                    primitiveLogScope);
                                continue;
                            }
                        }

                        // Tangents
                        if (tangentsAvailable)
                        {
                            tangentsArray = new NativeArray<Vector3>(
                                (int)bufferVertexCount, _nativeAllocator,
                                _nativeArrayInit);

                            tangentsResult =
                                CAPI.ovrAvatar2MorphTarget_GetVertexTangents(
                                    data.morphTargetBufferId, iMorphTarget,
                                    tangentsArray.CastOvrPtr(),
                                    bufferSize, stride);
                            ct.ThrowIfCancellationRequested();
                            tangentsAvailable = tangentsResult.IsSuccess();
                            if (!tangentsAvailable && tangentsResult != CAPI.ovrAvatar2Result.DataNotAvailable)
                            {
                                OvrAvatarLog.LogError(
                                    $"MorphTarget_GetVertexTangents ({iMorphTarget}) {tangentsResult}",
                                    primitiveLogScope);
                                continue;
                            }
                        }

                        var nameResult =
                            CAPI.ovrAvatar2Asset_GetMorphTargetName(
                                data.morphTargetBufferId, iMorphTarget,
                                nameBuffer, nameBufferLength);
                        ct.ThrowIfCancellationRequested();

                        var name = string.Empty;
                        if (nameResult.IsSuccess())
                        {
                            name = Marshal.PtrToStringAnsi((IntPtr)nameBuffer);
                        }
                        else if (nameResult != CAPI.ovrAvatar2Result.NotFound)
                        {
                            OvrAvatarLog.LogError($"ovrAvatar2MorphTarget_GetName failed with {nameResult}"
                                , primitiveLogScope);
                        }

                        // If we failed to query the name, use the index
                        if (string.IsNullOrEmpty(name)) { name = "morphTarget" + iMorphTarget; }

                        // Add Morph Target
                        morphTargetInfo[iMorphTarget] = new MorphTargetInfo(
                            name,
                            positionsArray.ToArray(),
                            normalsAvailable ? normalsArray.ToArray() : null,
                            tangentsAvailable ? tangentsArray.ToArray() : null
                        );
                    }
                    finally
                    {
                        positionsArray.Reset();
                        normalsArray.Reset();
                        tangentsArray.Reset();
                    }
                }
            }
        }

        private void SetupSkin(ref MeshInfo meshInfo)
        {
            var ct = GetCancellationToken();
            ct.ThrowIfCancellationRequested();

            var bindPoses = Array.Empty<Matrix4x4>();
            var buildJoints = Array.Empty<int>();

            var jointCount = data.jointCount;
            if (jointCount > 0)
            {
                using var jointsInfoArray =
                    new NativeArray<CAPI.ovrAvatar2JointInfo>(
                        (int)jointCount, _nativeAllocator,
                        _nativeArrayInit);
                unsafe
                {
                    var jointInfoBuffer = jointsInfoArray.GetPtr();
                    var result = CAPI.ovrAvatar2Primitive_GetJointInfo(
                        assetId, jointInfoBuffer,
                        jointsInfoArray.GetBufferSize());
                    ct.ThrowIfCancellationRequested();

                    if (result.EnsureSuccess("ovrAvatar2Primitive_GetJointInfo", primitiveLogScope))
                    {
                        buildJoints = new int[jointCount];
                        bindPoses = new Matrix4x4[jointCount];
                        for (int i = 0; i < jointCount; ++i)
                        {
                            var jointInfoPtr = jointInfoBuffer + i;
                            ref var bindPose = ref bindPoses[i];

                            buildJoints[i] = jointInfoPtr->jointIndex;
                            jointInfoPtr->inverseBind.CopyToUnityMatrix(out bindPose); //Convert to Matrix4x4
                        }
                    }
                } // unsafe
            }

            ct.ThrowIfCancellationRequested();
            meshInfo.bindPoses = bindPoses;
            joints = buildJoints;
        }

        private void SetupJointIndicesOnly()
        {
            var ct = GetCancellationToken();
            ct.ThrowIfCancellationRequested();

            var buildJoints = Array.Empty<int>();

            var jointCount = data.jointCount;
            if (jointCount > 0)
            {
                using var jointsInfoArray =
                    new NativeArray<CAPI.ovrAvatar2JointInfo>(
                        (int)jointCount, _nativeAllocator,
                        _nativeArrayInit);
                unsafe
                {
                    var jointInfoBuffer = jointsInfoArray.GetPtr();
                    var result = CAPI.ovrAvatar2Primitive_GetJointInfo(
                        assetId, jointInfoBuffer,
                        jointsInfoArray.GetBufferSize());
                    ct.ThrowIfCancellationRequested();

                    if (result.EnsureSuccess("ovrAvatar2Primitive_GetJointInfo", primitiveLogScope))
                    {
                        buildJoints = new int[jointCount];
                    }
                } // unsafe
            }

            ct.ThrowIfCancellationRequested();
            joints = buildJoints;
        }

        private sealed class OvrAvatarGpuSkinnedPrimitiveBuilder : IDisposable
        {
            NativeArray<IntPtr> deltaPositions;
            NativeArray<IntPtr> deltaNormals;
            NativeArray<IntPtr> deltaTangents;

            GCHandle[] morphPosHandles;
            GCHandle[] morphNormalHandles;
            GCHandle[] morphTangentHandles;

            Task createPrimitivesTask = null;

            private MeshInfo _gpuSkinningMeshInfo;

            readonly string shortName;
            readonly uint morphTargetCount;

            public OvrAvatarGpuSkinnedPrimitiveBuilder(string name, uint morphTargetCnt)
            {
                shortName = name;
                morphTargetCount = morphTargetCnt;
            }

            public Task CreateGpuPrimitiveHelperTask(
                MeshInfo meshInfo,
                MorphTargetInfo[] morphTargetInfo,
                bool hasTangents)
            {
                OvrAvatarLog.AssertConstMessage(
                    createPrimitivesTask == null
                    , "recreating gpu and/or compute primitive",
                    primitiveLogScope);

                _gpuSkinningMeshInfo = meshInfo;

                createPrimitivesTask = Task.Run(
                    () =>
                    {
                        // TODO: should get pointers to morph target data directly from Native

                        if (morphTargetCount == 0)
                        {
                            //nothing to do
                            return;
                        }

                        deltaPositions = new NativeArray<IntPtr>(
                            (int)morphTargetCount, _nativeAllocator, _nativeArrayInit);
                        if (deltaPositions.GetIntPtr() == IntPtr.Zero)
                        {
                            OvrAvatarLog.LogError(
                                "ERROR: Null buffer allocated for `deltaPositions` `CreateGpuPrimitiveHelperTask` - aborting",
                                primitiveLogScope);
                            return;
                        }

                        deltaNormals = new NativeArray<IntPtr>(
                            (int)morphTargetCount, _nativeAllocator, _nativeArrayInit);
                        if (deltaNormals.GetIntPtr() == IntPtr.Zero)
                        {
                            OvrAvatarLog.LogError(
                                "ERROR: Null buffer allocated for `deltaNormals` `CreateGpuPrimitiveHelperTask` - aborting",
                                primitiveLogScope);
                            return;
                        }
                        if (hasTangents)
                        {
                            deltaTangents =
                                new NativeArray<IntPtr>((int)morphTargetCount, _nativeAllocator, _nativeArrayInit);
                            if (deltaTangents.GetIntPtr() == IntPtr.Zero)
                            {
                                OvrAvatarLog.LogError(
                                    "ERROR: Null buffer allocated for `deltaTangents` `CreateGpuPrimitiveHelperTask` - aborting",
                                    primitiveLogScope);
                                return;
                            }
                        }

                        try
                        {
                            morphPosHandles = new GCHandle[morphTargetCount];
                            morphNormalHandles = new GCHandle[morphTargetCount];
                            if (hasTangents) { morphTangentHandles = new GCHandle[morphTargetCount]; }
                        }
                        catch (OutOfMemoryException)
                        {
                            return;
                        }

                        var minLength = Mathf.Min(morphTargetCount, morphTargetInfo.Length);
                        for (var i = 0; i < minLength; ++i)
                        {
                            morphPosHandles[i] = GCHandle.Alloc(
                                morphTargetInfo[i].targetPositions, GCHandleType.Pinned);
                            morphNormalHandles[i] = GCHandle.Alloc(
                                morphTargetInfo[i].targetNormals, GCHandleType.Pinned);

                            deltaPositions[i] = morphPosHandles[i].AddrOfPinnedObject();
                            deltaNormals[i] = morphNormalHandles[i].AddrOfPinnedObject();

                            if (hasTangents)
                            {
                                morphTangentHandles[i] =
                                    GCHandle.Alloc(morphTargetInfo[i].targetTangents, GCHandleType.Pinned);
                                deltaTangents[i] = morphTangentHandles[i].AddrOfPinnedObject();
                            }
                        }

                        createPrimitivesTask = null;
                    }
                    );
                return createPrimitivesTask;
            }

            public OvrAvatarGpuSkinnedPrimitive BuildPrimitive(MeshInfo meshInfo, Int32[] joints)
            {
                OvrAvatarLog.Assert(meshInfo == _gpuSkinningMeshInfo, primitiveLogScope);

                var primitive = new OvrAvatarGpuSkinnedPrimitive(
                    shortName,
                    _gpuSkinningMeshInfo.vertexCount,
                    in _gpuSkinningMeshInfo.verts,
                    in _gpuSkinningMeshInfo.normals,
                    in _gpuSkinningMeshInfo.tangents,
                    morphTargetCount,
                    in deltaPositions,
                    in deltaNormals,
                    in deltaTangents,
                    (uint)joints.Length,
                    _gpuSkinningMeshInfo.boneWeights,
                    () => { _gpuSkinningMeshInfo.NeutralPoseTexComplete(); },
                    () =>
                    {
                        _gpuSkinningMeshInfo.DidBuildGpuPrimitive();
                        _gpuSkinningMeshInfo = null;
                    });


                return primitive;
            }

            public void Dispose()
            {
                Dispose(true);
                GC.SuppressFinalize(this);
            }

            private void Dispose(bool isDisposing)
            {
                if (createPrimitivesTask != null)
                {
                    createPrimitivesTask.Wait();
                    createPrimitivesTask = null;
                }

                deltaPositions.Reset();
                deltaNormals.Reset();
                deltaTangents.Reset();

                FreeHandles(ref morphPosHandles);
                FreeHandles(ref morphNormalHandles);
                FreeHandles(ref morphTangentHandles);

                if (_gpuSkinningMeshInfo != null)
                {
                    _gpuSkinningMeshInfo.CancelledBuildPrimitives();
                    _gpuSkinningMeshInfo = null;
                }
            }

            private static void FreeHandles(ref GCHandle[] handles)
            {
                if (handles != null)
                {
                    foreach (var handle in handles)
                    {
                        if (handle.IsAllocated) { handle.Free(); }
                    }

                    handles = null;
                }
            }

            ~OvrAvatarGpuSkinnedPrimitiveBuilder()
            {
                Dispose(false);
            }
        }

        private const Allocator _nativeAllocator = Allocator.Persistent;
        private const NativeArrayOptions _nativeArrayInit = NativeArrayOptions.UninitializedMemory;
    }
}
