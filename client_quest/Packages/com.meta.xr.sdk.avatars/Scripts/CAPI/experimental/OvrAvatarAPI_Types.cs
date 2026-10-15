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

using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Unity.Collections;
using CAPIStringEncoding = System.Text.UTF8Encoding;

namespace Oculus.Avatar2.Experimental
{
    using ovrAvatar2SizeType = UIntPtr;

    public static partial class CAPI
    {
        [StructLayout(LayoutKind.Sequential)]
        public readonly unsafe ref struct ovrAvatar2DataView
        {
            public readonly void* data;
            public readonly ovrAvatar2SizeType size;

            public ovrAvatar2DataView(void* data_, uint size_) : this(data_, (ovrAvatar2SizeType)size_) { }

            public ovrAvatar2DataView(void* data_, ovrAvatar2SizeType size_)
            {
                data = data_;
                size = size_;
            }

            public UInt64 Size64 => (UInt64)size;

            public ref T RefAs<T>() where T : unmanaged
            {
                System.Diagnostics.Debug.Assert((UInt64)sizeof(T) == Size64, "Payload size mismatch!");
                unsafe
                {
                    return ref *(T*)(data);
                }
            }

            public ref readonly T ReadonlyRefAs<T>() where T : unmanaged => ref RefAs<T>();

            public T CopyAs<T>() where T : unmanaged => RefAs<T>();
        }

        // CAPI call compatible immutable C struct which cannot compile unless there is a known owner of the allocation
        [StructLayout(LayoutKind.Sequential)]
        public readonly unsafe ref struct ovrAvatar2StringView
        {
            // Pointer to first character in string
            public readonly byte* data;
            // Number of valid bytes in `data`
            public readonly ovrAvatar2SizeType size;

            public ovrAvatar2StringView(in NativeArray<byte> byteBuffer, ovrAvatar2SizeType writtenByteCount)
                : this(byteBuffer.GetPtr(), writtenByteCount) { }

            public ovrAvatar2StringView(byte* data, int size) : this(data, (ovrAvatar2SizeType)size)
            {
                System.Diagnostics.Debug.Assert(size >= 0);
            }
            public ovrAvatar2StringView(byte* data, uint size) : this(data, (ovrAvatar2SizeType)size) { }
            public ovrAvatar2StringView(byte* data, ovrAvatar2SizeType size)
            {
                this.data = data;
                this.size = size;
            }

            public bool Empty() => data == null || size.IsZero();

            public override string ToString() => Empty() ? StringHelpers.EmptyString : this.AllocateManagedString();
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public unsafe struct ovrAvatar2StringBuffer
        {
            public ovrAvatar2StringBuffer(byte* buffer, uint size)
            {
                data = buffer;
                capacity = (UIntPtr)size;
                charactersWritten = ovrAvatar2SizeType.Zero;
            }

            // Pointer to first character in string buffer
            public readonly byte* data;

            // Maximum capacity of `data` block
            public readonly ovrAvatar2SizeType capacity;

            // Number of valid bytes in `data`
            public ovrAvatar2SizeType charactersWritten;
        }
    }

    internal static class StringHelpers
    {
        #region Constants
        // String.Empty is `static readonly`, not `const`
        public const string EmptyString = "";

        // UIntPtr.Zero is `static readonly`, not `const`
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static bool IsZero(this ovrAvatar2SizeType size)
        {
#if UNITY_64
            UInt64 primSize = (UInt64)size;
#else // 32 Bit
            UInt32 primSize = (UInt32)size;
#endif
            return primSize == 0;
        }
        #endregion

        #region `char` Validation and Conversion
        private static CAPIStringEncoding? _utf8EncoderCache = null;

        private static CAPIStringEncoding _capiEncoder => _utf8EncoderCache ??= new System.Text.UTF8Encoding(false, false);

        // Will always allocate a new `string` based on `data` and `size`
        internal static unsafe string CreateManagedString(byte* data, uint size)
            => _capiEncoder.GetString(data, (int)size);

        private static uint GetCapiByteLength(this string managedString)
            => unchecked((uint)_capiEncoder.GetByteCount(managedString));

        private static uint GetMaxCapiByteLength(this string managedString)
            => unchecked((uint)_capiEncoder.GetMaxByteCount(managedString.Length));

        // Default to `Persistent` as it is the safest, leaks _should_ get detected in Debug builds very easily
        private static NativeArray<byte> GetCapiEncodedBytes(
            this string managedString, out ovrAvatar2SizeType bytesWritten, Allocator bufferAllocator = Allocator.Persistent)
        {
            System.Diagnostics.Debug.Assert(bufferAllocator != Allocator.Invalid);

            // Temp allocations will be automatically cleaned up, the calculating exact final`byte` size is non-trivial
            bool useGreedyAllocation = bufferAllocator == Allocator.Temp;

            // If using greedy allocation, invoke the cheaper `GetXYZByteCount` method
            var byteAllocCount = useGreedyAllocation
                ? GetMaxCapiByteLength(managedString)
                : GetCapiByteLength(managedString);
            // Not clear whether all implementations account for sentinel/null-terminator/'\0'...
            // TODO: We can use the encoder to determine the "Max" sentinel size via encoder.GetMaxByteCount(1)...
            // ... but an extra vcall? could be cached... but that has runtime overhead as well. Could pad for "worst case"
            // We know that avatarSDK C++ expects 8bit characters... and the exact format is _vague_ at best.
            // unlikely that the extra byte will have an impact in practice, vs the cost of not having it already available :X
            // TLDR; add room for one `'\0'` _just in case_
            byteAllocCount++;

            var byteBuffer = new NativeArray<byte>((int)byteAllocCount, bufferAllocator, NativeArrayOptions.UninitializedMemory);
            unsafe
            {
                fixed (char* managedChars = managedString)
                {
                    bytesWritten = (ovrAvatar2SizeType)WriteEncodedBytes(managedChars, managedString.Length
                        , byteBuffer.GetPtr(), byteBuffer.Length);
                }
            }
            return byteBuffer;
        }

        private static unsafe int WriteEncodedBytes(char* managedStringPinnedBuffer, int managedBufferSize,
            byte* capiStringByteBuffer, int capiBufferSize)
        {
            var encoder = _capiEncoder;
            int bytesWritten = encoder.GetBytes(managedStringPinnedBuffer, managedBufferSize, capiStringByteBuffer,
                capiBufferSize);

            // Ensure sentinel/terminator
            var signedSentinelIdx = (bytesWritten < capiBufferSize) ? bytesWritten : (capiBufferSize - 1);
            capiStringByteBuffer[signedSentinelIdx] = 0 /* == '\0'*/;
            System.Diagnostics.Debug.Assert(0 < bytesWritten && bytesWritten < capiBufferSize);
            return signedSentinelIdx;
        }

        #endregion // `char` Validation and Conversion

        // Interface for managed `stringView`
        public interface IOvrAvatar2String : IDisposable
        {
            // This may trigger many allocations, be careful!
            string GetManagedString();
            // May trigger an allocation on the first invocation, but will not on subsequent calls
            CAPI.ovrAvatar2StringView StringView { get; }
        }

        // Will always allocate a new `string`
        public static string AllocateManagedString(this in CAPI.ovrAvatar2StringView view)
        {
            unsafe { return CreateManagedString(view.data, (uint)view.size); }
        }

        public static string AllocateManagedString(this in CAPI.ovrAvatar2StringBuffer buffer)
        {
            unsafe { return CreateManagedString(buffer.data, (uint)buffer.charactersWritten); }
        }

        // Heap allocated provider for `ovrAvatar2StringView` - encoding is deferred until first use
        // Provided `ovrAvatar2StringView`s are valid until `StringViewHeapContainer` is Disposed or Finalized
        public sealed class ManagedStringView : IOvrAvatar2String
        {
            public ManagedStringView(string str)
            {
                _data = new StringViewDeferredAllocWrapper(str, Allocator.Persistent);
            }
            public void Free()
            {
                _data.Free();
                _data = default;
            }

            public CAPI.ovrAvatar2StringView StringView => _data.StringView;

            public override string ToString() => _data.SourceString;

            void IDisposable.Dispose()
            {
                Free();
                GC.SuppressFinalize(this);
            }
            ~ManagedStringView() => Free();

            string IOvrAvatar2String.GetManagedString() => _data.SourceString;

            private StringViewDeferredAllocWrapper _data = default;
        }

        // Defer allocation+encoding until it is requested, then cache the result.
        internal struct StringViewDeferredAllocWrapper : IOvrAvatar2String
        {
            // Default to temp allocator since we presumably live on "the stack"
            internal StringViewDeferredAllocWrapper(string managedString, Allocator allocator = Allocator.Temp)
            {
                System.Diagnostics.Debug.Assert(!string.IsNullOrEmpty(managedString));
                System.Diagnostics.Debug.Assert(allocator != Allocator.Invalid);

                SourceString = managedString;
                _allocHandle = default;
                _allocator = allocator;
            }

            public void Free()
            {
                if (!_allocHandle.IsEmpty)
                {
                    _allocHandle.Reset();
                }
            }

            public readonly string SourceString;

            public CAPI.ovrAvatar2StringView StringView
            {
                get
                {
                    // In theory, this should never happen - but handle it "elegantly" for now
                    if (string.IsNullOrEmpty(SourceString)) { return default; }

                    if (_allocHandle.IsEmpty)
                    {
                        _allocHandle = new StringViewAllocHandle(SourceString, _allocator);
                    }
                    return _allocHandle.StringView;
                }
            }

            public override string ToString() => SourceString;

            void IDisposable.Dispose() => Free();
            string IOvrAvatar2String.GetManagedString() => SourceString;

            private StringViewAllocHandle _allocHandle;

            // Track allocator provided at construction for deferred allocation
            private readonly Allocator _allocator;
        }

        public readonly struct StringViewAllocHandle : IOvrAvatar2String
        {
            // Default to temp allocator since we presumably live on "the stack"
            internal StringViewAllocHandle(string managedString, Allocator allocator = Allocator.Persistent)
            {
                System.Diagnostics.Debug.Assert(allocator != Allocator.Invalid);
                _byteBuffer = managedString.GetCapiEncodedBytes(out _writtenByteCount, allocator);
            }

            internal void Free()
            {
                _byteBuffer.Dispose();
            }

            public bool IsEmpty => !_byteBuffer.IsCreated;

            public CAPI.ovrAvatar2StringView /*IOvrAvatar2String.*/StringView => new(_byteBuffer, _writtenByteCount);

            public override string ToString() => StringView.AllocateManagedString();

            private readonly NativeArray<byte> _byteBuffer;
            private readonly ovrAvatar2SizeType _writtenByteCount;

            // Virtual implementation if this is coerced into an `IDisposable`, ideally only for `using` statements
            void IDisposable.Dispose() => Free();
            string IOvrAvatar2String.GetManagedString() => ToString();
        }

        public static void Reset(ref this StringViewAllocHandle handle)
        {
            if (!handle.IsEmpty)
            {
                handle.Free();
                handle = default;
            }
        }

        public static void Reset(ref this StringViewDeferredAllocWrapper handle)
        {
            handle.Free();
            handle = default;
        }
    }
}
