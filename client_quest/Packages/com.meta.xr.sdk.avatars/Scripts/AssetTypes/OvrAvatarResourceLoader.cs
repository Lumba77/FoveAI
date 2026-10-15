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
using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;


using Unity.Profiling;

using UnityEngine;
using UnityEngine.Profiling;

using static Oculus.Avatar2.OvrAvatarEntity;

namespace Oculus.Avatar2
{
    ///
    /// Represents a request to load a textured mesh.
    /// This will spawn requests to load one or more
    /// primitives which will in turn load one or more textures.
    /// This class accumulates the loaded meshes and textures
    /// as lists of @ref OvrAvatarPrimitive and @ref OvrAvatarImage instances.
    ///
    /// Resource loading is asynchronous and begins when
    /// @ref StartLoad is called.
    ///
    public sealed class OvrAvatarResourceLoader : IDisposable
    {
        private const string logScope = "resourceLoader";

        private OvrAvatarResourceTimer resourceTimer = null; // Should be only present in debug builds

        private OvrTime.SliceHandle _createResourceSliceHandle;

        internal static void ResourceCallbackHandler(
            in CAPI.ovrAvatar2Asset_Resource resource,
            Dictionary<CAPI.ovrAvatar2Id,
            OvrAvatarResourceLoader> resourceMap,
            out OvrAvatarResourceLoader queueLoad)
        {
            OvrAvatarLog.LogVerbose(
                $"Received resource callback {resource.assetID} with status {resource.status}"
                , logScope);

            queueLoad = null;

            switch (resource.status)
            {
                case CAPI.ovrAvatar2AssetStatus.ovrAvatar2AssetStatus_LoadFailed:
                {
                    Profiler.BeginSample("OvrAvatarResourceLoader::LoadFailed");
                    if (!OvrAvatarManager.shuttingDown)
                    {
                        OvrAvatarLog.LogError($"Failed to load resource");

                        // Try unload, just in case something has gone whacky
                        if (resourceMap.TryGetValue(
                                resource.assetID
                                , out OvrAvatarResourceLoader failedLoader))
                        {
                            failedLoader.Unload();
                            resourceMap.Remove(resource.assetID);
                            failedLoader.resourceTimer?.TrackStatusEvent(
                                OvrAvatarResourceTimer.AssetLifeTimeStatus.LoadFailed);
                        }
                    }
                    Profiler.EndSample(); // "OvrAvatarResourceLoader::LoadFailed"
                }
                break;

                case CAPI.ovrAvatar2AssetStatus.ovrAvatar2AssetStatus_Loaded:
                {
                    Profiler.BeginSample("OvrAvatarResourceLoader::Loaded");
                    if (!resourceMap.TryGetValue(resource.assetID, out var current))
                    {
                        var newLoader = new OvrAvatarResourceLoader(resource.assetID);
                        resourceMap.Add(resource.assetID, newLoader);
                        queueLoad = newLoader;
                        OvrAvatarLog.LogVerbose($"Mapped resource id:{resource.assetID}", logScope);
                    }
                    else
                    {
                        OvrAvatarLog.LogDebug(
                            $"Resource id: {resource.assetID} already loaded {current}", logScope);
                    }
                    Profiler.EndSample(); // "OvrAvatarResourceLoader::Loaded"
                }
                break;

                case CAPI.ovrAvatar2AssetStatus.ovrAvatar2AssetStatus_Unloaded:
                {
                    Profiler.BeginSample("OvrAvatarResourceLoader::Unloaded");
                    if (resourceMap.TryGetValue(resource.assetID, out var loader))
                    {
                        loader.Unload(nativeResourceReleased: true);
                        resourceMap.Remove(resource.assetID);
                        OvrAvatarLog.LogVerbose($"Unmapped resource id:{resource.assetID}", logScope);
                    }
                    else
                    {
                        OvrAvatarLog.LogWarning(
                            $"Unable to unload resource id:{resource.assetID}, not found", logScope);
                    }
                    Profiler.EndSample(); // "OvrAvatarResourceLoader::Unloaded"
                }
                break;

                case CAPI.ovrAvatar2AssetStatus.ovrAvatar2AssetStatus_Updated:
                    throw new InvalidOperationException("Resource updates are not currently supported");

                default:
                    throw new InvalidOperationException($"Unexpected resource status {resource.status}");
            }
        }

        private readonly List<OvrAvatarPrimitive> _primitives = new List<OvrAvatarPrimitive>();
        private readonly List<OvrAvatarImage> _images = new List<OvrAvatarImage>();

        // Effectively indicates whether load is in progress
        private OvrTime.SliceHandle _loadResourceAsyncCoroutine = default;

#if UNITY_EDITOR
        // Exposed only for use in AvatarResourcesWindow
        public IReadOnlyCollection<OvrAvatarPrimitive> Primitives => _primitives;

        public IReadOnlyCollection<OvrAvatarImage> Images => _images;
#endif

        private bool _hasReleasedNativeResources = false;
        public bool isCancelled { get; private set; } = false;
        public bool isDisposed { get; private set; } = false;

        public bool CanLoad => !(isCancelled || isDisposed);

        public readonly CAPI.ovrAvatar2Id resourceId;

        private class ProfilerMarkers
        {
            public readonly ProfilerMarker StartLoadSliceMarker;

            public ProfilerMarkers()
            {
                var categories = OvrAvatarProfilingUtils.AvatarCategories;
                StartLoadSliceMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarResourceLoader::StartLoadSlice");
            }
        }
        private static ProfilerMarkers s_markers = null;

        internal OvrAvatarImage CreateImage(in CAPI.ovrAvatar2MaterialTexture textureData
            , in CAPI.ovrAvatar2Image imageData, uint imageIndex, CAPI.ovrAvatar2Id resourceId)
        {
            bool srgb = (textureData.type == CAPI.ovrAvatar2MaterialTextureType.BaseColor);
            var newImage = new OvrAvatarImage(resourceId, imageIndex, in imageData, srgb);
            _images.Add(newImage);
            return newImage;
        }

        public OvrAvatarResourceLoader(CAPI.ovrAvatar2Id resourceIdentifier)
        {
            // Ensure profiling markers are initialized before they can possibly be used, avoiding static ctor overhead
            s_markers ??= new ProfilerMarkers();

            OvrAvatarLog.Assert(resourceIdentifier != CAPI.ovrAvatar2Id.Invalid);
            this.resourceId = resourceIdentifier;
            // only allow for load time tracking overhead if logging level is high enough
            if (Debug.isDebugBuild)
            {
                resourceTimer = new OvrAvatarResourceTimer(this);
            }

            resourceTimer?.TrackStatusEvent(OvrAvatarResourceTimer.AssetLifeTimeStatus.Created);
            _createResourceSliceHandle = OvrTime.Slice(CreateResourcePrimitivesAsync());
        }

        private IEnumerator<OvrTime.SliceStep> CreateResourcePrimitivesAsync()
        {
            // Get Primitive Count
            var result = CAPI.ovrAvatar2Asset_GetPrimitiveCount(resourceId, out UInt32 primitiveCount);
            if (!result.EnsureSuccess("ovrAvatar2Asset_GetPrimitiveCount", logScope))
            {
                ReleaseNativeResource();
                yield return OvrTime.SliceStep.Cancel;
            }

            // Load Primitives
            _primitives.Capacity = (int)primitiveCount;
            for (UInt32 i = 0; i < primitiveCount; ++i)
            {
                Profiler.BeginSample("CreateResourcePrimitives.load");
                result = CAPI.ovrAvatar2Asset_GetPrimitiveByIndex(resourceId, i,
                    out CAPI.ovrAvatar2Primitive primitiveData);
                if (!result.EnsureSuccess("ovrAvatar2Asset_GetPrimitiveByIndex", logScope))
                {
                    ReleaseNativeResource();
                    Profiler.EndSample();
                    yield return OvrTime.SliceStep.Cancel; // why is this a return instead of a continue?
                }

                if (OvrAvatarManager.IsOvrAvatarAssetLoaded(primitiveData.id))
                {
                    OvrAvatarLog.LogWarning(
                        $"Mesh primitive with id {primitiveData.id} already exists.", logScope);
                    Profiler.EndSample();
                    yield return OvrTime.SliceStep.Continue;
                }

                OvrAvatarLog.LogVerbose($"Mapped primitive id:{primitiveData.id}", logScope);
                var newPrimitive = new OvrAvatarPrimitive(this, in primitiveData);
                newPrimitive.primitiveStyle = GetPrimitiveStyle(newPrimitive);

                _primitives.Add(newPrimitive);
                Profiler.EndSample();
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
            }

            _createResourceSliceHandle.Clear(); // should this be here or inside the cancel, I don't know...
        }

        internal void StartLoad()
        {
            _loadResourceAsyncCoroutine = OvrTime.Slice(LoadResourceAsync());
        }

        private bool CheckCancel(OvrAvatarAssetBase asset, out OvrTime.SliceStep step)
        {
            bool cancelled = asset.isCancelled;
            if (cancelled)
            {
                OvrAvatarLog.LogVerbose(
                    $"{asset.typeName} {asset.assetName} cancelled during resource load."
                    , logScope);

                // Resume checking next frame
                // TODO: Switch to Wait, but currently no unit test - use Delay for now
                // yield return OvrTime.SliceStep.Wait;
                step = OvrTime.SliceStep.Delay;
            }
            else // !isCancelled
            {
                // Loading in progress, delay next slice
                step = OvrTime.SliceStep.Defer;
            }
            return cancelled;
        }

        private IEnumerator<OvrTime.SliceStep> LoadResourceAsync()
        {
            resourceTimer?.TrackStatusEvent(OvrAvatarResourceTimer.AssetLifeTimeStatus.LoadStarted);

            foreach (var primitive in _primitives)
            {
                bool step = true;
                var startLoadStep = primitive.StartLoad(this);
                while (step)
                {
                    {
                        using var startLoadMarker = s_markers.StartLoadSliceMarker.Auto();
                        step = startLoadStep.MoveNext();
                    }
                    if (step) { yield return OvrTime.SliceStep.Hold; }
                }

                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
            }

            foreach (var newPrimitive in _primitives)
            {
                while (!newPrimitive.hasCopiedAllResourceData)
                {
                    yield return OvrTime.SliceStep.Delay;
                }
            }
            foreach (var newImage in _images)
            {
                while (!newImage.HasCopiedAllResourceData)
                {
                    yield return OvrTime.SliceStep.Delay;
                }
            }

            resourceTimer?.TrackStatusEvent(OvrAvatarResourceTimer.AssetLifeTimeStatus.Loaded);

            // Notify nativeSDK that we no longer will access the resource data
            ReleaseNativeResource();

            OvrAvatarLog.LogVerbose($"Releasing native resources for resourceId {resourceId}", logScope);

            if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

            // Wait until all primitives are fully loaded
            foreach (var newPrimitive in _primitives)
            {
                while (!newPrimitive.isLoaded && !CheckCancel(newPrimitive, out var step))
                {
                    yield return step;
                }
            }
            foreach (var newImage in _images)
            {
                while (!newImage.isLoaded && !CheckCancel(newImage, out var step))
                {
                    yield return step;
                }
            }

            _loadResourceAsyncCoroutine.Clear();

            if (OvrAvatarManager.hasInstance)
            {
                OvrAvatarManager.Instance.ResourceLoadComplete(this);
            }

            MarkResourceReadyToRender();

            // If we reach here, we have finished w/out being (directly) cancelled - congratulations!
            OvrAvatarLog.LogVerbose($"LoadResourceAsync completed for resourceId {resourceId}", logScope);
        }

        public void CancelLoad()
        {
            if (!_hasReleasedNativeResources)
            {
                ReleaseNativeResource();
            }

            if (_loadResourceAsyncCoroutine.IsValid)
            {
                OvrAvatarLog.LogVerbose($"Stopping LoadResourceAsync coroutine for resourceId {resourceId}");

                if (!_loadResourceAsyncCoroutine.Cancel())
                {
                    // If cancellation fails w/out crashing - something gnarly has happened
                    OvrAvatarLog.LogError($"Slice for resourceId {resourceId} failed to Cancel");
                }

                if (OvrAvatarManager.hasInstance)
                {
                    OvrAvatarManager.Instance.ResourceLoadCancelled(this);
                }
            }

            isCancelled = true;
        }

        // Unity no longer needs access to the native resource, release it
        private void ReleaseNativeResource()
        {
            // TODO: Good use case for "ensure"
            OvrAvatarLog.Assert(resourceId != CAPI.ovrAvatar2Id.Invalid);

            if (resourceId != CAPI.ovrAvatar2Id.Invalid)
            {
                _hasReleasedNativeResources = CAPI.OvrAvatar2Asset_ReleaseResource(resourceId);
                OvrAvatarLog.Assert(_hasReleasedNativeResources);
            }
        }

        private void MarkResourceReadyToRender()
        {
            // TODO: Good use case for "ensure"
            OvrAvatarLog.Assert(resourceId != CAPI.ovrAvatar2Id.Invalid);

            if (resourceId != CAPI.ovrAvatar2Id.Invalid)
            {
                bool readyToRender = CAPI.OvrAvatar2Asset_ResourceReadyToRender(resourceId);
                OvrAvatarLog.Assert(readyToRender);
                resourceTimer?.TrackStatusEvent(OvrAvatarResourceTimer.AssetLifeTimeStatus.ReadyToRender);
            }
        }

        private void Unload(bool nativeResourceReleased = false)
        {
            OvrAvatarLog.LogDebug($"Unloading resource id: {resourceId}", logScope);
            if (nativeResourceReleased)
            {
                _hasReleasedNativeResources = true;
            }

            resourceTimer?.TrackStatusEvent(OvrAvatarResourceTimer.AssetLifeTimeStatus.Unloaded);
            Dispose();
        }

        // IDisposable interface
        private void Dispose(bool disposing)
        {
            if (disposing)
            {
                if (_primitives.Count > 0)
                {
                    OvrAvatarLog.LogVerbose(
                        $"Disposing {_primitives.Count} OvrAvatarPrimitive instances for resourceId {resourceId}");
                    foreach (var primitive in _primitives)
                    {
                        primitive.Dispose();
                    }
                    _primitives.Clear();
                }

                if (_images.Count > 0)
                {
                    OvrAvatarLog.LogVerbose(
                        $"Disposing {_images.Count} OvrAvatarImage instances for resourceId {resourceId}");
                    foreach (var image in _images)
                    {
                        image.Dispose();
                    }
                    _images.Clear();
                }
                CancelLoad();
                if (_createResourceSliceHandle.IsValid)
                {
                    _createResourceSliceHandle.Cancel();
                }
            }
            else
            {
                OvrAvatarLog.LogError($"Finalized {resourceId} w/out main thread dispose", logScope);
            }
            resourceTimer = null;
            isDisposed = true;
        }

        // Called from `OvrAvatarManager.Shutdown`
        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        ~OvrAvatarResourceLoader()
        {
            Dispose(false);
        }

        // Getting the style of the avatar (if the primitive is of an avatar at all)
        private static AvatarStyle GetPrimitiveStyle(OvrAvatarPrimitive primitive)
        {

            // Calling CAPI ovrAvatar2VertexBuffer_GetTexCoord2 with an NULL buffer (IntPtr.Zero)
            // will check for the existence rather than copy over the TexCoord2 data
            var texCoord2result = CAPI.ovrAvatar2VertexBuffer_GetTexCoord2(
                primitive.data.vertexBufferId, IntPtr.Zero, 0, 0);

            if (texCoord2result.IsSuccess()) // If the avatar does not have TexCoord2 data then it is a style 2 avatar
            {
                return AvatarStyle.Style2;
            }
            else
            {
                if (!texCoord2result.IsDataNotAvailable())
                {
                    OvrAvatarLog.LogWarning("Encountered unexpected failure when interpreting primitive, the avatar glb may be broken.");
                    return AvatarStyle.InvalidStyle;
                }
                return AvatarStyle.Style1;
            }
        }
    }
}
