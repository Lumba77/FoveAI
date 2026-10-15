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

using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;

using UnityEngine;

namespace Oculus.Avatar2
{
    [Flags]
    public enum ExtensionType
    {
        None = 0,
        Hair = 1 << 0,
        RimLight = 1 << 1,
        Skin = 1 << 2,
        Cel = 1 << 3,

    }
    public readonly struct OvrAvatarMaterialExtension
    {
        //////////////////////////////////////////////////
        // ExtenstionEntry<T>
        //////////////////////////////////////////////////
        private struct ExtensionEntry<T>
        {
            private int _nameIndex;
            private T _payload;

            public ExtensionEntry(int nameIndex, T payload)
            {
                _nameIndex = nameIndex;
                _payload = payload;
            }

            public int NameIndex => _nameIndex;
            public T Payload => _payload;
        }

        //////////////////////////////////////////////////
        // ExtenstionEntries
        //////////////////////////////////////////////////
        private class ExtensionEntries
        {
            private const string extensionLogScope = "OvrAvatarMaterialExtension_ExtensionEntries";

            private List<string> _names = null;

            private NativeArray<ExtensionEntry<Vector3>> _vector3Entries = default;
            private NativeArray<ExtensionEntry<Vector4>> _vector4Entries = default;
            private NativeArray<ExtensionEntry<float>> _floatEntries = default;
            private NativeArray<ExtensionEntry<int>> _intEntries = default;
            // can't store Texture2d in a Native array.
            private List<ExtensionEntry<Texture2D>> _textureEntries = null;

            public void Dispose()
            {
                Dispose(true);
                GC.SuppressFinalize(this);
            }

            private void Dispose(bool isDispose)
            {
                _floatEntries.Reset();
                _vector3Entries.Reset();
                _vector4Entries.Reset();
                _intEntries.Reset();

                OvrAvatarLog.Assert(isDispose, extensionLogScope);
            }

            public void ApplyToMaterial(Material mat, string extensionName,
                OvrAvatarMaterialExtensionConfig extensionConfig)
            {
                Debug.Assert(extensionConfig != null);
                Debug.Assert(_names != null);

                string nameInShader;
                foreach (var entry in _vector3Entries)
                {
                    if (extensionConfig.TryGetNameInShader(extensionName, _names[entry.NameIndex], out nameInShader))
                    {
                        mat.SetVector(nameInShader, entry.Payload);
                    }
                }

                foreach (var entry in _vector4Entries)
                {
                    if (extensionConfig.TryGetNameInShader(extensionName, _names[entry.NameIndex], out nameInShader))
                    {
                        mat.SetVector(nameInShader, entry.Payload);
                    }
                }

                foreach (var entry in _floatEntries)
                {
                    if (extensionConfig.TryGetNameInShader(extensionName, _names[entry.NameIndex], out nameInShader))
                    {
                        mat.SetFloat(nameInShader, entry.Payload);
                    }
                }

                foreach (var entry in _intEntries)
                {
                    if (extensionConfig.TryGetNameInShader(extensionName, _names[entry.NameIndex], out nameInShader))
                    {
                        mat.SetInt(nameInShader, entry.Payload);
                    }
                }

                if (_textureEntries != null)
                {
                    foreach (var entry in _textureEntries)
                    {
                        if (extensionConfig.TryGetNameInShader(extensionName, _names[entry.NameIndex], out nameInShader))
                        {
                            mat.SetTexture(nameInShader, entry.Payload);
                        }
                    }
                }
            }

            public bool LoadEntrys(CAPI.ovrAvatar2Id primitiveId, UInt32 extensionIndex)
            {
                if (!GetNumEntries(primitiveId, extensionIndex, out uint numEntries)) { return false; }

                NativeArray<CAPI.ovrAvatar2MaterialExtensionEntry> metaData =
                    new NativeArray<CAPI.ovrAvatar2MaterialExtensionEntry>((int)numEntries, Allocator.Temp, NativeArrayOptions.UninitializedMemory);

                bool success = true;
                int numFloats = 0;
                int numInts = 0;
                int numVec3s = 0;
                int numVec4s = 0;
                int numImgs = 0;
                // Loop over all entries, grab the meta data and figure out out many of each type
                unsafe
                {
                    var metaDataArray = metaData.GetPtr();
                    for (UInt32 entryIdx = 0; entryIdx < numEntries; entryIdx++)
                    {
                        success = GetEntryMetaData(primitiveId, extensionIndex, entryIdx, out metaDataArray[entryIdx]);
                        if (!success) { return false; }

                        switch (metaDataArray[entryIdx].entryType)
                        {
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Float:
                                ++numFloats;
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Int:
                                ++numInts;
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Vector3f:
                                ++numVec3s;
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Vector4f:
                                ++numVec4s;
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.ImageId:
                                ++numImgs;
                                break;

                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Invalid:
                                OvrAvatarLog.LogError(
                                    $"Invalid extension type for primitiveId:{primitiveId} extensionIndex:{extensionIndex} entryIndex:{entryIdx}"
                                    , extensionLogScope);

                                // Invalid signals an internal error in `libovravatar2` - should not have returned success
                                return false;

                            default:
                                OvrAvatarLog.LogWarning(
                                    $"Unrecognized extension type ({metaDataArray[entryIdx].entryType}) for primitiveId:{primitiveId} extensionIndex:{extensionIndex} entryIndex:{entryIdx}"
                                    , extensionLogScope);
                                break;
                        }
                    }
                }

                _floatEntries.Reset();
                _vector3Entries.Reset();
                _vector4Entries.Reset();
                _intEntries.Reset();

                _names = new List<string>((int)numEntries);
                _floatEntries = new NativeArray<ExtensionEntry<float>>(numFloats, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
                _intEntries = new NativeArray<ExtensionEntry<int>>(numInts, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
                _vector3Entries = new NativeArray<ExtensionEntry<Vector3>>(numVec3s, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
                _vector4Entries = new NativeArray<ExtensionEntry<Vector4>>(numVec4s, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
                if (numImgs != 0)
                {
                    _textureEntries = new List<ExtensionEntry<Texture2D>>(numImgs);
                }

                // Now grab the name and the data of the entry
                unsafe
                {
                    var metaDataArray = metaData.GetPtr();
                    var floatData = _floatEntries.GetPtr();
                    var intData = _intEntries.GetPtr();
                    var vec3Data = _vector3Entries.GetPtr();
                    var vec4Data = _vector4Entries.GetPtr();
                    int nextFloat = 0;
                    int nextInt = 0;
                    int nextVec3 = 0;
                    int nextVec4 = 0;
                    int nextTex = 0;

                    for (UInt32 entryIdx = 0; entryIdx < numEntries; entryIdx++)
                    {
                        switch (metaDataArray[entryIdx].entryType)
                        {
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Float:
                                success = StoreNameAndPayloadForEntry(
                                    primitiveId,
                                    extensionIndex,
                                    entryIdx,
                                    metaDataArray[entryIdx],
                                    ref floatData[nextFloat++]);
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Int:
                                success = StoreNameAndPayloadForEntry(
                                    primitiveId,
                                    extensionIndex,
                                    entryIdx,
                                    metaDataArray[entryIdx],
                                    ref intData[nextInt++]);
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Vector3f:
                                success = StoreNameAndPayloadForEntry(
                                    primitiveId,
                                    extensionIndex,
                                    entryIdx,
                                    metaDataArray[entryIdx],
                                    ref vec3Data[nextVec3++]);
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Vector4f:
                                success = StoreNameAndPayloadForEntry(
                                    primitiveId,
                                    extensionIndex,
                                    entryIdx,
                                    metaDataArray[entryIdx],
                                    ref vec4Data[nextVec4++]);
                                break;
                            case CAPI.ovrAvatar2MaterialExtensionEntryType.ImageId:
                                string entryName;
                                var payload = CAPI.ovrAvatar2Id.Invalid;
                                unsafe
                                {
                                    success = GetNameAndPayloadForEntry(
                                        primitiveId,
                                        extensionIndex,
                                        entryIdx,
                                        metaDataArray[entryIdx],
                                        out entryName,
                                        &payload);
                                }

                                if (success)
                                {
                                    OvrAvatarLog.Assert(payload != CAPI.ovrAvatar2Id.Invalid, extensionLogScope);
                                    // Convert image ID to texture
                                    success = OvrAvatarManager.GetOvrAvatarAsset(payload, out OvrAvatarImage image);
                                    if (success)
                                    {
                                        _textureEntries.Add(new ExtensionEntry<Texture2D>(_names.Count, image.Texture));
                                        _names.Add(entryName);
                                        ++nextTex;
                                    }
                                    else
                                    {
                                        OvrAvatarLog.LogError(
                                            $"Could not find image entryName:{entryName} assetId:{payload}"
                                            , extensionLogScope
                                            , image?.Texture);
                                    }
                                }

                                break;

                            case CAPI.ovrAvatar2MaterialExtensionEntryType.Invalid:
                                OvrAvatarLog.LogError(
                                    $"Invalid extension type for primitiveId:{primitiveId} extensionIndex:{extensionIndex} entryIndex:{entryIdx}"
                                    , extensionLogScope);

                                // Invalid signals an internal error in `libovravatar2` - should not have returned success
                                success = false;
                                break;

                            default:
                                OvrAvatarLog.LogWarning(
                                    $"Unrecognized extension type ({metaDataArray[entryIdx].entryType}) for primitiveId:{primitiveId} extensionIndex:{extensionIndex} entryIndex:{entryIdx}"
                                    , extensionLogScope);
                                break;
                        }
                    }
                }

                return success;
            }

            private static bool GetEntryMetaData(
                CAPI.ovrAvatar2Id primitiveId,
                UInt32 extensionIdx,
                UInt32 entryIdx,
                out CAPI.ovrAvatar2MaterialExtensionEntry metaData)
            {
                var success = CAPI.OvrAvatar2Primitive_MaterialExtensionEntryMetaDataByIndex(
                    primitiveId,
                    extensionIdx,
                    entryIdx,
                    out metaData);

                if (!success)
                {
                    OvrAvatarLog.LogError(
                        $"MaterialExtensionEntryMetaDataByIndex ({extensionIdx}, {entryIdx}) bufferSize:{metaData.dataBufferSize}"
                        , LOG_SCOPE);
                }

                return success;
            }

            private static unsafe bool GetNameAndPayloadForEntry<T>(
                CAPI.ovrAvatar2Id primitiveId,
                UInt32 extensionIndex,
                UInt32 entryIndex,
                in CAPI.ovrAvatar2MaterialExtensionEntry metaData,
                out string entryName,
                T* outPayload)
                where T : unmanaged
            {
                OvrAvatarLog.Assert(metaData.nameBufferSize > 0);
                OvrAvatarLog.Assert(metaData.dataBufferSize > 0);

                uint nameBufferSize = metaData.nameBufferSize;
                var nameBuffer = stackalloc byte[(int)nameBufferSize];

                bool success;

                uint managedSize = (uint)UnsafeUtility.SizeOf<T>();
                uint dataBufferSize = metaData.dataBufferSize;
                bool noMarshal = managedSize == dataBufferSize;
                if (noMarshal)
                {
                    success = CAPI.OvrAvatar2Primitive_MaterialExtensionEntryDataByIndex(
                        primitiveId,
                        extensionIndex,
                        entryIndex,
                        nameBuffer,
                        nameBufferSize,
                        (byte*)outPayload,
                        managedSize);
                }
                else
                {
                    var dataBuffer = stackalloc byte[(int)dataBufferSize];

                    success = CAPI.OvrAvatar2Primitive_MaterialExtensionEntryDataByIndex(
                        primitiveId,
                        extensionIndex,
                        entryIndex,
                        nameBuffer,
                        nameBufferSize,
                        dataBuffer,
                        dataBufferSize);

                    if (success) { *outPayload = Marshal.PtrToStructure<T>((IntPtr)dataBuffer); }
                }

                if (!success)
                {
                    OvrAvatarLog.LogWarning(
                        @$"MaterialExtensionEntryDataByIndex (extensionIdx:{extensionIndex}, entryIdx:{entryIndex})"
                        + $"nameSize:{nameBufferSize} managedSize:{managedSize} bufferSize:{dataBufferSize}"
                        , LOG_SCOPE);

                    entryName = string.Empty;
                    *outPayload = default;
                    return false;
                }

                entryName = Marshal.PtrToStringAnsi((IntPtr)nameBuffer);
                return true;
            }

            private bool StoreNameAndPayloadForEntry<T>(
                CAPI.ovrAvatar2Id primitiveId,
                UInt32 extensionIdx,
                UInt32 entryIdx,
                in CAPI.ovrAvatar2MaterialExtensionEntry metaData,
                ref ExtensionEntry<T> entryToStoreInto)
                where T : unmanaged
            {
                bool success;
                string entryName;
                T payload;
                unsafe
                {
                    success = GetNameAndPayloadForEntry(
                        primitiveId,
                        extensionIdx,
                        entryIdx,
                        metaData,
                        out entryName,
                        &payload);
                }

                if (success)
                {
                    entryToStoreInto = new ExtensionEntry<T>(_names.Count, payload);
                    _names.Add(entryName);
                }

                return success;
            }
        }

        //////////////////////////////////////////////////
        // OvrAvatarMaterialExtension
        //////////////////////////////////////////////////
        private readonly ExtensionEntries _entries;
        private readonly string _name;

        private const string LOG_SCOPE = "OvrAvatarMaterialExtension";

        private OvrAvatarMaterialExtension(string extensionName, ExtensionEntries entries)
        {
            _name = extensionName;
            _entries = entries;
        }
        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        private void Dispose(bool isDispose)
        {
            _entries.Dispose();

            OvrAvatarLog.Assert(isDispose, LOG_SCOPE);
        }

        public string Name => _name;

        public void ApplyEntriesToMaterial(Material material, OvrAvatarMaterialExtensionConfig extensionConfig)
        {
            if (_entries == null || material == null || extensionConfig == null) { return; }

            _entries.ApplyToMaterial(material, _name, extensionConfig);
        }

        public static bool LoadExtension(CAPI.ovrAvatar2Id primitiveId, UInt32 extensionIndex,
            out OvrAvatarMaterialExtension materialExtension)
        {
            materialExtension = default;

            // Get extension name
            if (!GetMaterialExtensionName(primitiveId, extensionIndex, out string extensionName)) { return false; }

            // Get entries for the extension
            ExtensionEntries entries = new ExtensionEntries();
            if (!entries.LoadEntrys(primitiveId, extensionIndex)) { return false; }

            materialExtension = new OvrAvatarMaterialExtension(extensionName, entries);

            return true;
        }

        private static bool GetMaterialExtensionName(CAPI.ovrAvatar2Id primitiveId, UInt32 extensionIdx,
            out string extensionName)
        {
            unsafe
            {
                extensionName = String.Empty;

                // Get extension name
                uint nameSize = 0;
                var result = CAPI.ovrAvatar2Primitive_GetMaterialExtensionName(
                    primitiveId,
                    extensionIdx,
                    null,
                    &nameSize);

                if (!result.EnsureSuccess($"GetMaterialExtensionName ({extensionIdx}) {result}", LOG_SCOPE))
                {
                    return false;
                }

                var nameBuffer = stackalloc byte[(int)nameSize];
                result = CAPI.ovrAvatar2Primitive_GetMaterialExtensionName(
                    primitiveId,
                    extensionIdx,
                    nameBuffer,
                    &nameSize);
                if (!result.EnsureSuccess($"GetMaterialExtensionName ({extensionIdx}) {result}", LOG_SCOPE))
                {
                    return false;
                }

                extensionName = Marshal.PtrToStringAnsi((IntPtr)nameBuffer);
            }

            return true;
        }

        private static bool GetNumEntries(CAPI.ovrAvatar2Id primitiveId, UInt32 extensionIndex, out UInt32 count)
        {
            count = 0;
            var result =
                CAPI.ovrAvatar2Primitive_GetNumEntriesInMaterialExtensionByIndex(
                    primitiveId, extensionIndex
                    , out count);

            if (!result.IsSuccess())
            {
                OvrAvatarLog.LogError($"GetNumEntriesInMaterialExtensionByIndex ({extensionIndex}) {result}"
                    , LOG_SCOPE);
                return false;
            }

            return true;
        }
    }
}
