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
    /// <summary>
    /// C# wrapper around OVRBody lip sync api.
    /// </summary>
    public sealed class OvrAvatarVisemeContext : OvrAvatarLipSyncContextBase
    {
        // Synchronize access to context and callbacks
        private readonly object _contextLock = new object();

        private IntPtr _context;
        private CAPI.ovrAvatar2LipSyncContext _nativeCallbacks;

        internal CAPI.ovrAvatar2LipSyncContextNative NativeCallbacks { get; }

        // Cached so we can keep some previous options when calling SetSampleRate/SetMode
        private CAPI.ovrAvatar2LipSyncProviderConfig _config;

        #region Public Methods

        public OvrAvatarVisemeContext(CAPI.ovrAvatar2LipSyncProviderConfig config)
        {
            _config = config;
            var result = CAPI.ovrAvatar2LipSync_CreateProvider(ref config, ref _context);
            if (!result.EnsureSuccess("ovrAvatar2LipSync_CreateProvider"))
            {
                // New exception type?
                throw new Exception("Failed to create viseme context");
            }

            var callbacks = CreateLipSyncContext();
            if (callbacks.HasValue)
            {
                _nativeCallbacks = callbacks.Value;
            }

            result = CAPI.ovrAvatar2LipSync_InitializeContextNative(_context, out var nativeCb);
            if (result == CAPI.ovrAvatar2Result.Success)
            {
                NativeCallbacks = nativeCb;
            }
            else
            {
                OvrAvatarLog.LogError($"ovrAvatar2LipSync_InitializeContextNative failed with {result}");
            }
        }

        public void FeedAudio(float[] data, int channels)
        {
            FeedAudio(data, 0, data.Length, channels);
        }

        public void FeedAudio(ArraySegment<float> data, int channels)
        {
            FeedAudio(data.Array, data.Offset, data.Count, channels);
        }

        private void FeedAudio(float[] data, int offset, int count, int channels)
        {
            lock (_contextLock)
            {
                if (_context == IntPtr.Zero)
                {
                    OvrAvatarLog.LogError($"Attempted to call FeedAudio after context destroyed.");
                    return;
                }

                bool isStereo = channels == 2;
                CAPI.ovrAvatar2AudioDataFormat format =
                    isStereo ? CAPI.ovrAvatar2AudioDataFormat.F32_Stereo : CAPI.ovrAvatar2AudioDataFormat.F32_Mono;

                uint samples = (uint)(isStereo ? count / 2 : count);

                var handle = GCHandle.Alloc(data, GCHandleType.Pinned);
                var offsetAddress = IntPtr.Add(handle.AddrOfPinnedObject(), offset * sizeof(float));
                var result = CAPI.ovrAvatar2LipSync_FeedAudio(_context, format, offsetAddress, samples);
                handle.Free();
                result.EnsureSuccess("ovrAvatar2LipSync_FeedAudio");
            }
        }

        public void FeedAudio(short[] data, int channels)
        {
            FeedAudio(data, 0, data.Length, channels);
        }

        public void FeedAudio(ArraySegment<short> data, int channels)
        {
            FeedAudio(data.Array, data.Offset, data.Count, channels);
        }

        private void FeedAudio(short[] data, int offset, int count, int channels)
        {
            lock (_contextLock)
            {
                if (_context == IntPtr.Zero)
                {
                    OvrAvatarLog.LogError($"Attempted to call FeedAudio after context destroyed.");
                    return;
                }
                bool isStereo = channels == 2;
                CAPI.ovrAvatar2AudioDataFormat format =
                    isStereo ? CAPI.ovrAvatar2AudioDataFormat.S16_Stereo : CAPI.ovrAvatar2AudioDataFormat.S16_Mono;

                uint samples = (uint)(isStereo ? count / 2 : count);

                var handle = GCHandle.Alloc(data, GCHandleType.Pinned);
                var offsetAddress = IntPtr.Add(handle.AddrOfPinnedObject(), offset * sizeof(short));
                var result = CAPI.ovrAvatar2LipSync_FeedAudio(_context, format, offsetAddress, samples);
                handle.Free();
                result.EnsureSuccess("ovrAvatar2LipSync_FeedAudio");
            }
        }

        public void Reconfigure(CAPI.ovrAvatar2LipSyncProviderConfig config)
        {
            _config = config;
            Reconfigure();
        }

        public void SetMode(CAPI.ovrAvatar2LipSyncMode newMode)
        {
            _config.mode = newMode;
            Reconfigure();
        }

        public void SetSampleRate(UInt32 sampleRate, UInt32 bufferSize)
        {
            _config.audioSampleRate = sampleRate;
            _config.audioBufferSize = bufferSize;
            Reconfigure();
        }

        public void SetSmoothing(int smoothing)
        {
            var result = CAPI.ovrAvatar2LipSync_SetSmoothing(_context, smoothing);
            result.EnsureSuccessOnlyWarning(msgContext: "ovrAvatar2LipSync_SetSmoothing");
        }

        public void EnableViseme(CAPI.ovrAvatar2Viseme viseme)
        {
            var result = CAPI.ovrAvatar2LipSync_EnableViseme(_context, viseme);
            result.EnsureSuccessOnlyWarning(msgContext: "ovrAvatar2LipSync_EnableViseme");
        }

        public void DisableViseme(CAPI.ovrAvatar2Viseme viseme)
        {
            var result = CAPI.ovrAvatar2LipSync_DisableViseme(_context, viseme);
            result.EnsureSuccessOnlyWarning(msgContext: "ovrAvatar2LipSync_DisableViseme");
        }

        public void SetViseme(CAPI.ovrAvatar2Viseme viseme, int amount)
        {
            var result = CAPI.ovrAvatar2LipSync_SetViseme(_context, viseme, amount);
            result.EnsureSuccessOnlyWarning(msgContext: "ovrAvatar2LipSync_SetViseme");
        }

        public void SetLaughter(int amount)
        {
            var result = CAPI.ovrAvatar2LipSync_SetLaughter(_context, amount);
            result.EnsureSuccessOnlyWarning(msgContext: "ovrAvatar2LipSync_SetLaughter");
        }

        #endregion

        private CAPI.ovrAvatar2LipSyncContext? CreateLipSyncContext()
        {
            var lipSyncContext = new CAPI.ovrAvatar2LipSyncContext();
            var result = CAPI.ovrAvatar2LipSync_InitializeContext(_context, ref lipSyncContext);
            if (!result.EnsureSuccess("ovrAvatar2LipSync_InitializeContext"))
            {
                return null;
            }

            return lipSyncContext;
        }

        private void ReleaseUnmanagedResources()
        {
            lock (_contextLock)
            {
                if (_context == IntPtr.Zero) return;
                var result = CAPI.ovrAvatar2LipSync_DestroyProvider(_context);
                result.EnsureSuccess("ovrAvatar2LipSync_DestroyProvider");
                _context = IntPtr.Zero;
            }
        }

        protected override bool GetLipSyncState(OvrAvatarLipSyncState lipsyncState)
        {
            if (_nativeCallbacks.lipSyncCallback != null &&
                   _nativeCallbacks.lipSyncCallback(out var nativeState, _nativeCallbacks.context))
            {
                lipsyncState.FromNative(ref nativeState);
                return true;
            }
            return false;
        }

        private void Reconfigure()
        {
            lock (_contextLock)
            {
                var result = CAPI.ovrAvatar2LipSync_ReconfigureProvider(_context, ref _config);
                if (!result.IsSuccess())
                {
                    OvrAvatarLog.LogWarning($"ovrAvatar2LipSync_ReconfigureProvider failed with {result}");
                }
            }
        }

        protected override void Dispose(bool disposing)
        {
            ReleaseUnmanagedResources();
            base.Dispose(disposing);
        }

        ~OvrAvatarVisemeContext()
        {
            ReleaseUnmanagedResources();
        }
    }
}
