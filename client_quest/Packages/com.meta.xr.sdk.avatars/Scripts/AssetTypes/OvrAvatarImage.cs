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

#if UNITY_EDITOR
#define OVR_AVATAR_ALLOCATE_TEXTURE_NAMES
#endif

using System;
using System.Collections.Generic;

using Unity.Collections;
using Unity.Profiling;

using UnityEngine;

/// @file OvrAvatarImage.cs

namespace Oculus.Avatar2
{
    ///
    /// Contains a 2D image used to texture a 3D mesh.
    /// The pixels of the texture come in a variety of formats.
    /// Mobile applications use ASTC compressed texture formats
    /// which are decompressed by hardware. PC applications
    /// need DXT compressed textures.
    ///
    /// The texture data begins loading asynchronously when
    /// the image is created.
    ///
    /// @see OvrAvatarPrimitive
    ///
    public sealed class OvrAvatarImage : OvrAvatarAsset<CAPI.ovrAvatar2Image>
    {
        private const string AVATAR_IMAGE_LOG_SCOPE = "ovrAvatarImage";
        private const bool ALLOW_MIP_GENERATION = false;
        private const TextureFormat ERROR_FORMAT = (TextureFormat)(-127);

        internal const FilterMode DEFAULT_FILTER_MODE = FilterMode.Trilinear;
        internal const int DEFAULT_ANISO_LEVEL = 1;

        public Texture2D? Texture => _texture;

        public override string typeName => AVATAR_IMAGE_LOG_SCOPE;
        public override string assetName => $"{assetId}:{_imageIndex}-{_format}";



        // Flag indicating if this instance still requires access to the native runtime stored image data
        public bool HasCopiedAllResourceData => _hasCopiedAllResourceData;

        private Texture2D? _texture = null;
        private OvrTime.SliceHandle _textureLoadSliceHandle = default;
        private readonly TextureFormat _format;
        private readonly UInt32 _imageIndex;
        private bool _hasCopiedAllResourceData = false;

        private class ProfilerMarkers
        {
            public readonly ProfilerMarker AllocateTextureMarker;
            public readonly ProfilerMarker AccessTextureDataMarker;
            public readonly ProfilerMarker CopyTextureDataMarker;
            public readonly ProfilerMarker UploadTextureDataMarker;

            public ProfilerMarkers()
            {
                var categories = OvrAvatarProfilingUtils.AvatarCategories;
                AllocateTextureMarker = new ProfilerMarker(OvrAvatarProfilingUtils.AvatarCategories.Loading, "OvrAvatarImage::AllocateTexture");
                AccessTextureDataMarker = new ProfilerMarker("OvrAvatarImage::AccessTextureData");
                CopyTextureDataMarker = new ProfilerMarker("OvrAvatarImage::CopyTextureData");
                UploadTextureDataMarker = new ProfilerMarker("OvrAvatarImage::UploadTextureData");
            }
        }
        private static ProfilerMarkers? s_markers = null;

        ///
        /// Create an image from the given image properties.
        /// The image begins asynchronously loading upon return.
        ///
        /// @param resourceId unique resource ID
        /// @param imageIndex index of image within material
        /// @param data       image properties (data format, height, width)
        /// @param srgb       true for images using SRGB color space,
        ///                   False for linear color space
        /// @see CAPI.ovrAvatar2Image
        ///
        public OvrAvatarImage(CAPI.ovrAvatar2Id resourceId, UInt32 imageIndex, in CAPI.ovrAvatar2Image data, bool srgb)
            : base(data.id, in data)
        {
            // Ensure profiling markers are initialized before they can possibly be used, avoiding static ctor overhead
            s_markers ??= new ProfilerMarkers();

            _imageIndex = imageIndex;
            var checkFormat = GetTextureFormat(data, out bool compressed);

            if (checkFormat == ERROR_FORMAT || !TextureFormatSupported(checkFormat))
            {
                _format = ERROR_FORMAT;

                // Can't load invalid format, all valid data has been copied (unblock remaining loading of the resource)
                _hasCopiedAllResourceData = true;
                // unblock loading for the primitive
                isLoaded = true;
            }
            else
            {
                using var allocateScope = s_markers.AllocateTextureMarker.Auto();

                _format = checkFormat;

                bool hasMipMaps = data.mipCount > 1;
                var buildTexture = new Texture2D((int)data.sizeX, (int)data.sizeY, _format, hasMipMaps, !srgb);

                // We are assuming this slice can't execute until next frame. if It executes this frame, GetRawTextureData will take a long time.
                // There needs to be 1 frame at least between new Texture2D and the call to GetRawTextureData.
                _textureLoadSliceHandle = OvrTime.Slice(LoadTextureAsync(resourceId, buildTexture, imageIndex, srgb, compressed));
            }
        }

        private IEnumerator<OvrTime.SliceStep> LoadTextureAsync(
            CAPI.ovrAvatar2Id resourceId, Texture2D buildTexture, UInt32 imageIndex, bool srgb, bool compressed)
        {
            Debug.Assert(s_markers != null);

            {
                // Oh Unity...
                if (buildTexture == null)
                {
                    OvrAvatarLog.LogError(
                        $"Unable to create texture with size ({data.sizeX}, {data.sizeY}) and formats ({data.format}, {_format})",
                        AVATAR_IMAGE_LOG_SCOPE, buildTexture);
                    yield return FailLoad(buildTexture!);
                }

                buildTexture!.name =
#if OVR_AVATAR_ALLOCATE_TEXTURE_NAMES
                    assetName;
#else // ^^^ OVR_AVATAR_ALLOCATE_TEXTURE_NAMES / !OVR_AVATAR_ALLOCATE_TEXTURE_NAMES vvv
                    "AvatarSDKTexture";
#endif // !OVR_AVATAR_ALLOCATE_TEXTURE_NAMES

                var manager = OvrAvatarManager.Instance;
                var filterMode = DEFAULT_FILTER_MODE;
                int anisoLevel = DEFAULT_ANISO_LEVEL;
                if (manager != null)
                {
                    filterMode = manager.TextureFilterMode;
                    anisoLevel = manager.TextureAnisoLevel;
                }
                buildTexture.filterMode = filterMode;
                buildTexture.anisoLevel = anisoLevel;
            }

            NativeArray<byte> textureData = default;
            {
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                using var accessScope = s_markers!.AccessTextureDataMarker.Auto();

                textureData = buildTexture.GetRawTextureData<byte>();
                // AvatarSDK will catch this at runtime, this just provides a more useful error when developing in Unity
                Debug.Assert(!textureData.IsNull() && textureData.Length == data.imageDataSize,
                    $"Texture data arrays are different sizes! Texture is {textureData.Length} but image is {data.imageDataSize}"
                    , buildTexture);
            }

            {
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }

                bool getImageDataResult = false;
                var getImageDataTask = OvrAvatarManager.Instance.EnqueueLoadingTask(() =>
                {
                    using var copyScope = s_markers.CopyTextureDataMarker.Auto();
                    getImageDataResult = CAPI.OvrAvatar2Asset_GetImageDataByIndex(resourceId, imageIndex, ref textureData, buildTexture);
                });

                while (!getImageDataTask.IsCompleted)
                {
                    // use wait instead of delay, so we can check every frame, the task typically ~250us, its nearly always done by next frame.
                    yield return OvrTime.SliceStep.Defer;
                }

                if (!getImageDataResult)
                {
                    OvrAvatarLog.LogError(
                        $"MeshPrimitive Error: GetImageDataByIndex ({imageIndex})", AVATAR_IMAGE_LOG_SCOPE, buildTexture);
                    yield return FailLoad(buildTexture);
                }

                _hasCopiedAllResourceData = true;
            }

            {
                if (OvrTime.ShouldHold) { yield return OvrTime.SliceStep.Hold; }
                // very cheap, ~5us. The actual upload happens on the render thread(very slow on that thread, a few ms), here its just letting the render thread know.
                using var uploadScope = s_markers.UploadTextureDataMarker.Auto();

                bool generateMips = ALLOW_MIP_GENERATION && !compressed && data.mipCount == 1;
                buildTexture.Apply(generateMips, true);
            }

            _texture = buildTexture;
            isLoaded = true;

            _textureLoadSliceHandle.Clear();
        }

        private OvrTime.SliceStep FailLoad(Texture2D buildTexture)
        {
            OvrAvatarLog.LogVerbose("Image load failed!", AVATAR_IMAGE_LOG_SCOPE);

            // Mark this load as "Complete" to unblock the overall load operation
            _hasCopiedAllResourceData = true;
            _textureLoadSliceHandle.Clear();

            return OvrTime.SliceStep.Cancel;
        }

        protected override void _ExecuteCancel()
        {
            if (_textureLoadSliceHandle.IsValid)
            {
                OvrAvatarLog.LogVerbose("Cancelled image during load", AVATAR_IMAGE_LOG_SCOPE);

                _textureLoadSliceHandle.Cancel();
            }

            // We will not load any more resource data, so we have effectively loaded all of it
            _hasCopiedAllResourceData = true;
        }

        protected override void Dispose(bool disposing)
        {
            if (_textureLoadSliceHandle.IsValid)
            {
                if (disposing)
                {
                    _textureLoadSliceHandle.Cancel();
                }
                else
                {
                    OvrAvatarLog.LogWarning("Finalized image w/ in progress loading slice", AVATAR_IMAGE_LOG_SCOPE);

                    var cpyHandle = _textureLoadSliceHandle;
                    _textureLoadSliceHandle.Clear();
                    OvrTime.PostCleanupToUnityMainThread(() => cpyHandle.Cancel());
                }
            }

            if (Texture is not null)
            {
                if (disposing)
                {
                    Texture2D.Destroy(Texture);
                }
                else
                {
                    OvrAvatarLog.LogError(
                        $"Texture2D asset was not destroyed before OvrAvatarImage ({assetId}) was finalized"
                        , AVATAR_IMAGE_LOG_SCOPE);

                    var holdTex = Texture;
                    OvrTime.PostCleanupToUnityMainThread(() => Texture2D.Destroy(holdTex));
                }
                _texture = null;
            }
        }

        private static TextureFormat GetTextureFormat(in CAPI.ovrAvatar2Image data, out bool isCompressed)
        {
            isCompressed = true;
            switch (data.format)
            {
                case CAPI.ovrAvatar2ImageFormat.RGBA32:
                    isCompressed = false;
                    return TextureFormat.RGBA32;
                case CAPI.ovrAvatar2ImageFormat.DXT1:
                    return TextureFormat.DXT1;
                case CAPI.ovrAvatar2ImageFormat.DXT5:
                    return TextureFormat.DXT5;
                case CAPI.ovrAvatar2ImageFormat.BC5S:
                    return TextureFormat.BC5;
                case CAPI.ovrAvatar2ImageFormat.BC7U:
                    return TextureFormat.BC7;
                case CAPI.ovrAvatar2ImageFormat.ASTC_RGBA_4x4:
                    return TextureFormat.ASTC_4x4;
                case CAPI.ovrAvatar2ImageFormat.ASTC_RGBA_6x6:
                    return TextureFormat.ASTC_6x6;
                case CAPI.ovrAvatar2ImageFormat.ASTC_RGBA_8x8:
                    return TextureFormat.ASTC_8x8;

                //  ASTC_RGBA_10x10 support is not currently implemented by AvatarSDK Runtime
                //                 case CAPI.ovrAvatar2ImageFormat.ASTC_RGBA_10x10:
                //                     return TextureFormat.ASTC_10x10;

                case CAPI.ovrAvatar2ImageFormat.ASTC_RGBA_12x12:
                    return TextureFormat.ASTC_12x12;

                case CAPI.ovrAvatar2ImageFormat.Invalid:
                    OvrAvatarLog.LogError(
                        $"Invalid image format for image {data.id}",
                        AVATAR_IMAGE_LOG_SCOPE);
                    return ERROR_FORMAT;

                case CAPI.ovrAvatar2ImageFormat.BC5U:
                    // Appears to be unsupported
                    OvrAvatarLog.LogError(
                        "BC5U is currently unsupported in Unity",
                        AVATAR_IMAGE_LOG_SCOPE);
                    // Can't load format, proceed w/ other assets
                    return ERROR_FORMAT;

                default:
                    OvrAvatarLog.LogError($"Unrecognized format {data.format}");
                    return ERROR_FORMAT;
            }
        }

        private static bool TextureFormatSupported(TextureFormat format)
        {
            // ReSharper disable once RedundantNameQualifier
            return UnityEngine.SystemInfo.SupportsTextureFormat(format)
#if UNITY_EDITOR
                    // This is supposed to report the compatibility of the target platform, but it doesn't appear to work at all
                    // leaving it in in case one day UnityTech fixes it.
                    // NOTE: Very subtle namespace difference :/
                    // https://docs.unity3d.com/ScriptReference/Device.SystemInfo.SupportsTextureFormat.html
                || UnityEngine.Device.SystemInfo.SupportsTextureFormat(format)
                    // Unity can software decode ASTC -> BMP in editor, but will still report ASTC as unsupported
                    // skip the format support check and let Unity do its thing

                    // TODO: T199676445 Don't rely on ASTC textures on desktop platforms
                    // ^- can probably still keep this (vvv) though when ANDROID/IOS are the target platform?
                    // ReSharper disable once MergeIntoPattern
                || (TextureFormat.ASTC_4x4 <= format && format <= TextureFormat.ASTC_12x12)
#endif // UNITY_EDITOR
                ;
        }
    }
}
