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

using Oculus.Avatar2.Experimental;

using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;

namespace Oculus.Avatar2
{
    public static partial class CAPI
    {
        private const string AvatarCapiLogScope = "OvrAvatarAPI_Avatar";

        private const string ScriptBinaryMismatchResolution = "update c-sharp scripts to match libovravatar2 version";

        // Native libovravatar2 version this integration was built against
        private static FBVersionNumber TargetLibVersion;

        /* Debug string indicating the native libovravatar2 version this manager is targeting */
        public static string TargetAvatarLibVersionString
            => $"{TargetLibProductVersion}.{TargetLibMajorVersion}.{TargetLibMinorVersion}.{TargetLibPatchVersion}";

        // Native libovravatar2 version this integration was built against
        private static int TargetLibProductVersion = -1;
        private static int TargetLibMajorVersion = -1;
        private static int TargetLibMinorVersion = -1;
        private static int TargetLibPatchVersion = -1;

        internal const string LibFile =
#if UNITY_EDITOR || !UNITY_IOS
#if UNITY_EDITOR_OSX
        OvrAvatarPlugin.FullPluginFolderPath + "libovravatar2.framework/libovravatar2";
#else
        OvrAvatarManager.IsAndroidStandalone ? "ovravatar2" : "libovravatar2";
#endif  // UNITY_EDITOR_OSX
#else   // !UNITY_EDITOR && UNITY_IOS
        "__Internal";
#endif  // !UNITY_EDITOR && UNITY_IOS

        // TODO: Add "INITIALIZED" frame count and assert in update when update called w/out init
        private const uint AVATAR_UPDATE_UNINITIALIZED_FRAME_COUNT = 0;

        //-----------------------------------------------------------------
        //
        // Forwards
        //
        //

        public const float DefaultAvatarColorRed = (30 / 255.0f);
        public const float DefaultAvatarColorGreen = (157 / 255.0f);
        public const float DefaultAvatarColorBlue = (255 / 255.0f);

        // Network thread update frequency.
        // 256 hz is updating every 0.004ms which we think is optimal in most use cases
        public const uint DefaultNetworkWorkerUpdateFrequency = 256;

        //-----------------------------------------------------------------
        //
        // Callback functions
        //
        //

        // Avatar Logging Level
        public enum ovrAvatar2LogLevel : Int32
        {
            Unknown = 0,
            Default = 1,
            Verbose = 2,
            Debug = 3,
            Info = 4,
            Warn = 5,
            Failure = 6,
            Error = 7,
            Fatal = 8,
            Silent = 9,
        };

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public unsafe delegate void LoggingDelegate(ovrAvatar2LogLevel prio, byte* msg, IntPtr context);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public unsafe delegate void LoggingViewDelegate(ovrAvatar2LogLevel prio, Experimental.CAPI.ovrAvatar2StringView msgView, void* context);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate void MemAllocDelegate(UInt64 byteCount, IntPtr context);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate void MemFreeDelegate(IntPtr buffer, IntPtr context);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate void ProfileMarkerDelegate(string name, bool isAsync);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate void ProfileCounterDelegate(string name, Int64 value);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate void ResourceDelegate(in ovrAvatar2Asset_Resource resource, IntPtr context);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate void RequestDelegate(ovrAvatar2RequestId requestId, ovrAvatar2Result status, IntPtr userContext);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        public delegate IntPtr FileOpenDelegate(IntPtr context, string filename);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        [return: MarshalAs(UnmanagedType.U1)]
        // TODO: Change return type, bool is an unreliable return type for an unmanaged function pointer
        public delegate bool FileReadDelegate(IntPtr context, IntPtr fileHandle, out IntPtr fileDataPtr, out UInt64 fileSize);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        [return: MarshalAs(UnmanagedType.U1)]
        // TODO: Change return type, bool is an unreliable return type for an unmanaged function pointer
        public delegate bool FileCloseDelegate(IntPtr context, IntPtr fileHandle);

        //-----------------------------------------------------------------
        //
        // Initialization
        //
        //

        public enum ovrAvatar2Platform : Int32
        {
            Invalid = 0,
            PC = 1,
            Quest = 2,
            Quest2 = 3,
            QuestPro = 4,
            Quest3 = 5,


            First = PC,

            Last = Quest3,

            Count = (Last - First) + 1,
            Num = Last + 1,
        }

        [Obsolete("Use `platform.ToPlatformString()` instead", false)]
        public static string ovrAvatar2PlatformToString(ovrAvatar2Platform platform)
        {
            return platform.ToPlatformString();
        }

        [Flags]
        public enum ovrAvatar2InitializeFlags : Int32
        {
            /// When set, ovrAvatar2_Shutdown() may return ovrAvatar2Result_MemoryLeak to indicate a
            /// detected memory leak
            CheckMemoryLeaks = 1 << 0,
            UseDefaultImage = 1 << 1,
            // When set, skinningOrigin in ovrAvatar2PrimitiveRenderState is set with the skinning origin
            // and the skinning matrices root will be the skinning Origin
            EnableSkinningOrigin = 1 << 3,

            /// When set, additional implicit operations will be performed in order to facilitate ease-of-use in tooling scenarios
            /// For example, automatically allowing hot-reloading of animations and more relaxed event registration requirements
            ToolMode = 1 << 4,

            /// When set, an Entity's default status is Pending instead of Success.
            /// It will go to Success when the RigResolver is ready.
            /// NOTE: This behavior will change in the future such that the current effect of
            /// `EntityPendingUntilRigResolverReady` will become the default, at which point this bit will be repurposed for other usage
            EntityPendingUntilRigResolverReady = 1 << 5,

            /// When set, the runtime rig system will run with a full detailed hierarchy which is lees performant
            /// though allows more detailed animations of skeleton extensions. Mostly intended for non VR scenarios.
            Experimental_EnableHighDetailRig = 1 << 8,

            None = 0,
            All = CheckMemoryLeaks
                  | UseDefaultImage
                  | EnableSkinningOrigin
                  | ToolMode
                  | EntityPendingUntilRigResolverReady
                  | Experimental_EnableHighDetailRig,

            First = CheckMemoryLeaks,

            Last = Experimental_EnableHighDetailRig,
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        // This needs to be the csharp equivalent of ovrAvatar2InitializeInfo in Avatar.h
        public struct ovrAvatar2InitializeInfo
        {
            public FBVersionNumber versionNumber;
            public string clientVersion; // client version string for the user app (ex. "Unity v2019.2")
            public ovrAvatar2Platform platform;

            public ovrAvatar2InitializeFlags flags;

            public ovrAvatar2LogLevel loggingLevel; // logging threshold to control what is logged

            [System.Obsolete("Use loggingViewCallback", true)]
            private readonly LoggingDelegate loggingCallback;

            public IntPtr loggingContext;
            public MemAllocDelegate memAllocCallback; // override memory management
            public MemFreeDelegate memFreeCallback; // override memory management
            public IntPtr memoryContext; // user context for memory callbacks

            public RequestDelegate requestCallback;

            public FileOpenDelegate fileOpenCallback; // used to open a file
            public FileReadDelegate fileReadCallback; // used to load file contents
            public FileCloseDelegate fileCloseCallback; // used to close a file
            public IntPtr fileReaderContext; // context for above file callbacks

            public ResourceDelegate resourceLoadCallback; // resource load callback
            public IntPtr resourceLoadContext;

            public string fallbackPathToOvrAvatar2AssetsZip;

            public UInt32 shouldCreateWorkerThreads;

            public Int64 maxNetworkRequests;
            public Int64 maxNetworkSendBytesPerSecond;
            public Int64 maxNetworkReceiveBytesPerSecond;

            public ovrAvatar2Vector3f defaultModelColor;
            ///
            /// Defines the right axis in the game engine coordinate system.
            /// For the Avatar SDK and Unity, this is (1, 0, 0)
            ///
            public ovrAvatar2Vector3f clientSpaceRightAxis;

            ///
            /// Defines the up axis in the game engine coordinate system.
            /// For the Avatar SDK and Unity, this is (0, 1, 0)
            ///
            public ovrAvatar2Vector3f clientSpaceUpAxis;

            ///
            /// Defines the forward axis in the game engine coordinate system.
            /// For the Avatar SDK this is (0, 0, -1). For Unity, it is (0, 0, 1)
            ///
            public ovrAvatar2Vector3f clientSpaceForwardAxis;

            public string clientName;

            // 0 for running network update on the main thread
            public UInt32 networkWorkerUpdateFrequency;

            private UInt32 reserved1;       // Reserved  / internal use only
            private IntPtr reserved2;       // Reserved  / internal use only

            private IntPtr reserved3;       // Reserved  / internal use only
            private IntPtr reserved4;       // Reserved  / internal use only
            private IntPtr reserved5;       // Reserved  / internal use only

            private IntPtr reserved6;       // Reserved  / internal use only

            public LoggingViewDelegate loggingViewCallback;

            private IntPtr reserved7;       // Reserved  / internal use only
            private Int64 reserved8;       // Reserved  / internal use only


            private IntPtr reserved9;       // Reserved  / internal use only
            private IntPtr reserved10;       // Reserved  / internal use only
            private IntPtr reserved11;       // Reserved  / internal use only

            public string extraJsonPayload;
        }

        internal static ovrAvatar2InitializeInfo OvrAvatar2_DefaultInitInfo(string clientVersion, ovrAvatar2Platform platform)
        {
            // TODO: T86822707, This should be a method in the loaderShim/ovravatar2 lib
            // return ovrAvatar2_DefaultInitInfo(clientVersion, platform);

            // Copied from //arvr/libraries/avatar/Libraries/api/include/OvrAvatar/Avatar.h
            ovrAvatar2InitializeInfo info = default;
            info.versionNumber = SDKVersionInfo.CurrentVersion();
            info.flags = ovrAvatar2InitializeFlags.UseDefaultImage;
            info.clientVersion = clientVersion;
            info.platform = platform;
            info.loggingLevel = ovrAvatar2LogLevel.Warn;
            info.shouldCreateWorkerThreads = 1;
            info.maxNetworkRequests = -1;
            info.maxNetworkSendBytesPerSecond = -1;
            info.maxNetworkReceiveBytesPerSecond = -1;

            // Default color of the default/blank avatar
            info.defaultModelColor.x = DefaultAvatarColorRed;
            info.defaultModelColor.y = DefaultAvatarColorGreen;
            info.defaultModelColor.z = DefaultAvatarColorBlue;

            // Transform from SDK space (-Z forward) to Unity space (+Z forward)
            info.clientSpaceRightAxis = UnityEngine.Vector3.right;
            info.clientSpaceUpAxis = UnityEngine.Vector3.up;
            info.clientSpaceForwardAxis = UnityEngine.Vector3.forward;

#if OVR_AVATAR_DISABLE_CLIENT_XFORM
            info.clientSpaceForwardAxis = -UnityEngine.Vector3.forward;
#endif

            info.clientName = "unknown_unity";

            info.networkWorkerUpdateFrequency = DefaultNetworkWorkerUpdateFrequency;

            return info;
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_Initialize(in ovrAvatar2InitializeInfo infoPtr);

        public static bool OvrAvatar2_Initialize(in ovrAvatar2InitializeInfo infoPtr)
        {
            if (ovrAvatar2_Initialize(in infoPtr)
                .EnsureSuccess("ovrAvatar2_Initialize", AvatarCapiLogScope))
            {
                TargetLibVersion = infoPtr.versionNumber;
                return true;
            }
            return false;
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_Shutdown();

        internal static bool OvrAvatar_Shutdown()
        {
            OvrAvatar_Shutdown(out var result);
            return result.EnsureSuccess("ovrAvatar2_Shutdown", AvatarCapiLogScope);
        }
        internal static void OvrAvatar_Shutdown(out ovrAvatar2Result result)
        {
            avatarUpdateCount = AVATAR_UPDATE_UNINITIALIZED_FRAME_COUNT;
            result = ovrAvatar2_Shutdown();
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern unsafe ovrAvatar2Result ovrAvatar2_UpdateAccessToken(byte* token);

        internal static bool OvrAvatar2_UpdateAccessToken(string token)
        {
            using var stringHandle = new StringHelpers.StringViewAllocHandle(token, Allocator.Temp);
            unsafe
            {
                return ovrAvatar2_UpdateAccessToken(stringHandle.StringView.data)
                    .EnsureSuccess("ovrAvatar2_UpdateAccessToken", AvatarCapiLogScope);
            }
        }


        /// Update the network settings
        /// \param maxNetworkSendBytesPerSecond -1 for no limit
        /// \param maxNetworkReceiveBytesPerSecond -1 for no limit
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2_UpdateNetworkSettings(
            Int64 maxNetworkSendBytesPerSecond, Int64 maxNetworkReceiveBytesPerSecond, Int64 maxNetworkRequests);

        //-----------------------------------------------------------------
        //
        // Work
        //
        //

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_Update(float deltaSeconds);

        // TODO: Could this just be 0.0f?
        private const float AVATAR_UPDATE_SMALL_STEP = 0.1f;
        internal static uint avatarUpdateCount { get; private set; } = AVATAR_UPDATE_UNINITIALIZED_FRAME_COUNT;
        internal static bool OvrAvatar2_Update(float deltaSeconds = AVATAR_UPDATE_SMALL_STEP)
        {
            var result = ovrAvatar2_Update(deltaSeconds);
            if (result.EnsureSuccess("ovrAvatar2_Update"))
            {
                ++avatarUpdateCount;
                return true;
            }
            return false;
        }

        /// Run a single task from the avatar task system.
        /// Return ovrAvatar2Result_Success upon completion after running a task.
        /// Return ovrAvatar2Result_NotFound when no tasks are currently in the queue.
        /// Return ovrAvatar2Result_Unsupported when library is configured to use worker threads.
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2_RunTask();

        public enum ovrAvatar2JobCategoryFlags : Int32
        {
            /// Jobs that are needed as part of the current frame.
            /// Examples include updating animations and applying
            /// network updates.
            ovrAvatar2JobCategoryFlags_FrameUpdate = 1 << 0,

            /// Jobs that are used for incremental refinement of
            /// the scene, but that don't have a strict deadline.
            /// Examples include updating the LOD manager.
            ovrAvatar2JobCategoryFlags_Incremental = 1 << 1,

            /// Background CPU-intensive tasks that have no deadline,
            /// like parsing and setting up loaded assets.
            ovrAvatar2JobCategoryFlags_BackgroundCPU = 1 << 2,

            /// Background IO-bound tasks that will leave threads
            /// stalled or blocked. Examples include loading
            /// files off of disk.
            ovrAvatar2JobCategoryFlags_BackgroundIO = 1 << 3,
        }

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        unsafe internal static extern ovrAvatar2Result ovrAvatar2_RunJobs(
            ovrAvatar2JobCategoryFlags jobCategories,
            bool sleepIfNoJobs,
            bool* pStopNow,
            float maxSeconds);


        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        internal static extern ovrAvatar2Result ovrAvatar2_WakeJobRunners(bool bForceReturn);

        //-----------------------------------------------------------------
        //
        // Query
        //
        //

        /// Query to see if a user has an avatar
        /// ovrAvatar2_RequestCallback is called when the request is fulfilled
        /// Request status:
        ///   ovrAvatar2Result_Success - request succeeded
        ///   ovrAvatar2Result_Unknown - error while querying user avatar status
        /// ovrAvatar2_GetRequestBool() result
        ///   true - user has an avatar
        ///   false - user does not have an avatar
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_HasAvatar(
            UInt64 userId, out ovrAvatar2RequestId requestId, IntPtr userContext);

        internal static bool OvrAvatar_HasAvatar(
            UInt64 userId, out ovrAvatar2RequestId requestId, IntPtr userContext)
        {
            var result = ovrAvatar2_HasAvatar(userId, out requestId, userContext);
            if (result.EnsureSuccess("ovrAvatar2_HasAvatar"))
            {
                return true;
            }
            requestId = ovrAvatar2RequestId.Invalid;
            return false;
        }

        /// Query to see if an entity's avatar has changed
        /// ovrAvatar2_RequestCallback is called when the request is fulfilled
        /// Request status:
        ///   ovrAvatar2Result_Success - request succeeded
        ///   ovrAvatar2Result_Unknown - error while querying user avatar status
        ///   ovrAvatar2Result_InvalidEntity - entity is no longer valid
        /// ovrAvatar2_GetRequestBool() result
        ///   true - user avatar has changed
        ///   false - user avatar has not changed
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_HasAvatarChanged(
            ovrAvatar2EntityId entityId, out ovrAvatar2RequestId requestId, IntPtr userContext);

        internal static bool OvrAvatar2_HasAvatarChanged(
            ovrAvatar2EntityId entityId, out ovrAvatar2RequestId requestId, IntPtr userContext)
        {
            var result = ovrAvatar2_HasAvatarChanged(entityId, out requestId, userContext);
            if (result.EnsureSuccess("ovrAvatar2_HasAvatarChanged"))
            {
                return true;
            }
            requestId = ovrAvatar2RequestId.Invalid;
            return false;
        }

        /// Get the result of a reqeust
        /// Should be called in ovrAvatar2_RequestCallback
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_GetRequestBool(
            ovrAvatar2RequestId requestId, [MarshalAs(UnmanagedType.U1)] out bool result);

        /* Query result of ovrAvatar2RequestId from `RequestCallback` */
        internal static bool OvrAvatar_GetRequestBool(
            ovrAvatar2RequestId requestId, out bool result)
        {
            if (ovrAvatar2_GetRequestBool(requestId, out result)
                .EnsureSuccess("ovrAvatar2_GetRequestBool"))
            {
                return true;
            }
            result = false;
            return false;
        }

        //-----------------------------------------------------------------
        //
        // Asset Sources
        //
        //

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        public static extern ovrAvatar2Result ovrAvatar2_AddZipSourceFile(string filename);

        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        public static extern ovrAvatar2Result ovrAvatar2_RemoveZipSource(string filename);


        //-----------------------------------------------------------------
        //
        // Stats
        //
        //

        // Avatar memory statistics

        [StructLayout(LayoutKind.Sequential)]
        public struct ovrAvatar2MemoryStats
        {
            public UInt64 currBytesUsed;
            public UInt64 currAllocationCount;
            public UInt64 maxBytesUsed;
            public UInt64 maxAllocationCount;
            public UInt64 totalBytesUsed;
            public UInt64 totalAllocationCount;
        }

        /// Updates the given memory stats struct with the current statistics
        /// \param pointer to a stats structure to update
        /// \param logging context, used if an error is encountered
        /// \return true for success, false if an error was encountered (most likely ovrAvatar2 is not initialized)
        public static bool OvrAvatar2_QueryMemoryStats(out ovrAvatar2MemoryStats stats
            , UnityEngine.Object? logContext = null)
        {
            var statsStructSize = (UInt32)UnsafeUtility.SizeOf<ovrAvatar2MemoryStats>();
            var result = ovrAvatar2_QueryMemoryStats(out stats, statsStructSize, out var bytesUpdated);
            return result.EnsureSuccessOrWarning(
                ovrAvatar2Result.BufferTooSmall, ovrAvatar2Result.BufferLargerThanExpected
                , ScriptBinaryMismatchResolution, "ovrAvatar2_QueryMemoryStats", AvatarCapiLogScope
                , logContext);
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct ovrAvatar2NetworkStats
        {
            public UInt64 downloadTotalBytes;
            public UInt64 downloadSpeed;
            public UInt64 totalRequests;
            public UInt64 activeRequests;
        }

        /// Updates the given network stats struct with the current statistics
        /// \param pointer to a stats structure to update
        /// \param logging context, used if an error is encountered
        /// \return true for success, false if an error was encountered (most likely ovrAvatar2 is not initialized)
        internal static bool OvrAvatar2_QueryNetworkStats(out ovrAvatar2NetworkStats stats
            , UnityEngine.Object? logContext = null)
        {
            var statsStructSize = (UInt32)UnsafeUtility.SizeOf<ovrAvatar2NetworkStats>();
            var result = ovrAvatar2_QueryNetworkStats(out stats, statsStructSize, out var bytesUpdated);
            return result.EnsureSuccessOrWarning(
                ovrAvatar2Result.BufferTooSmall, ovrAvatar2Result.BufferLargerThanExpected
                , ScriptBinaryMismatchResolution, "ovrAvatar2_QueryNetworkStats"
                , AvatarCapiLogScope, logContext);
        }

        /// Avatar task statistics
        ///

        public const int TaskHistogramSize = 32;

        [StructLayout(LayoutKind.Sequential)]
        public unsafe struct ovrAvatar2TaskStats
        {
            // UInt32 fixed size array of 32 items
            public fixed UInt32 histogram[TaskHistogramSize];
            public UInt32 pending;
        }

        /// Updates the given task stats struct with the current statistics
        /// \param pointer to a stats structure to update
        /// \param logging context, used if an error is encountered
        /// \return true for success, false if an error was encountered (most likely ovrAvatar2 is not initialized)
        internal static bool OvrAvatar2_QueryTaskStats(out ovrAvatar2TaskStats stats
            , UnityEngine.Object? logContext = null)
        {
            var statsStructSize = (UInt32)UnsafeUtility.SizeOf<ovrAvatar2TaskStats>();
            var result = ovrAvatar2_QueryTaskStats(out stats, statsStructSize, out var bytesUpdated);
            return result.EnsureSuccessOrWarning(
                ovrAvatar2Result.BufferTooSmall, ovrAvatar2Result.BufferLargerThanExpected
                , ScriptBinaryMismatchResolution, "ovrAvatar2_QueryTaskStats", AvatarCapiLogScope, logContext);
        }

        //-----------------------------------------------------------------
        //
        // Misc
        //
        //

        /// <summary>
        /// Get the string representation of an ovrAvatar2Result code
        /// </summary>
        /// <param name="result">The return code you want the string for</param>
        /// <param name="buffer">The buffer to return the string in</param>
        /// <param name="size">The size of the buffer</param>
        /// <returns>Success unless the result provided is out of range (BadParameter), or the buffer is
        /// null or too small (BufferTooSmall)</returns>
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern unsafe ovrAvatar2Result ovrAvatar2_GetResultString(ovrAvatar2Result result, char* buffer, UInt32* size);

        /// Get the avatar API version string
        /// \param versionBuffer string to populate with the version string
        /// \param bufferSize length of the version buffer
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        private static extern unsafe ovrAvatar2Result ovrAvatar2_GetVersionString(byte* versionBuffer, UInt32 bufferSize);

        internal static string OvrAvatar_GetVersionString()
        {
            unsafe
            {
                const int bufferSize = 1024;
                var versionBuffer = stackalloc byte[bufferSize];
                var result = ovrAvatar2_GetVersionString(versionBuffer, bufferSize);
                if (result.EnsureSuccess("ovrAvatar2_GetVersionString"))
                {
                    return Marshal.PtrToStringAnsi((IntPtr)versionBuffer);
                }
            }

            return string.Empty;
        }

        //-----------------------------------------------------------------
        //
        // CAPI Bindings
        //
        //

        /// Updates the given stats struct with the current statistics
        /// \param pointer to a stats structure to update
        /// \param size of the stats structure to update
        /// \param number of bytes updated in `stats`
        /// Returns result codes:
        ///   ovrAvatar2Result_Success - stats updated successfully
        ///   ovrAvatar2Result_DataNotAvailable - stats tracking unavailable
        ///   ovrAvatar2Result_BadParameter - stats is null or statsStructSize is 0
        ///   ovrAvatar2Result_BufferTooSmall - statsStructSize is smaller than expected
        ///   ovrAvatar2Result_BufferLargerThanExpected - statsStructSize is larger than expected
        ///     (note: Invoking `ovrAvatar2_Initialize` establishes primary thread)
        ///   ovrAvatar2Result_NotInitialized - ovrAvatar2 is currently not initialized
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_QueryMemoryStats(out ovrAvatar2MemoryStats stats,
            UInt32 statsStructSize, out UInt32 bytesUpdated);

        /// Updates the given stats struct with the current statistics
        /// \param pointer to a stats structure to update
        /// \param size of the stats structure to update
        /// \param number of bytes updated in `stats`
        /// Returns result codes:
        ///   ovrAvatar2Result_Success - stats updated successfully
        ///   ovrAvatar2Result_DataNotAvailable - stats tracking unavailable
        ///   ovrAvatar2Result_BadParameter - stats is null or statsStructSize is 0
        ///   ovrAvatar2Result_BufferTooSmall - statsStructSize is smaller than expected
        ///   ovrAvatar2Result_BufferLargerThanExpected - statsStructSize is larger than expected
        ///     (note: Invoking `ovrAvatar2_Initialize` establishes primary thread)
        ///   ovrAvatar2Result_NotInitialized - ovrAvatar2 is currently not initialized
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        private static extern ovrAvatar2Result ovrAvatar2_QueryNetworkStats(out ovrAvatar2NetworkStats stats
            , UInt32 statsStructSize, out UInt32 bytesUpdated);

        /// Update the given stats struct with the current task statistics
        /// \param pointer to a stats structure to update
        /// \param size of the stats structure to update
        /// \param number of bytes updated in `stats`
        /// Returns result codes:
        ///   ovrAvatar2Result_Success - stats updated successfully
        ///   ovrAvatar2Result_DataNotAvailable - stats tracking unavailable
        ///   ovrAvatar2Result_BadParameter - stats is null or statsStructSize is 0
        ///   ovrAvatar2Result_BufferTooSmall - statsStructSize is smaller than expected
        ///   ovrAvatar2Result_BufferLargerThanExpected - statsStructSize is larger than expected
        ///     (note: Invoking `ovrAvatar2_Initialize` establishes primary thread)
        ///   ovrAvatar2Result_NotInitialized - ovrAvatar2 is currently not initialized
        ///
        [DllImport(LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2_QueryTaskStats(out ovrAvatar2TaskStats stats
            , UInt32 statsStructSize, out UInt32 bytesUpdated);
    }

    public static class CapiHelperExtensions
    {
        public static string ToPlatformString(this CAPI.ovrAvatar2Platform platform)
        {
            switch (platform)
            {
                case CAPI.ovrAvatar2Platform.Invalid:
                    return "Invalid";
                case CAPI.ovrAvatar2Platform.PC:
                    return "PC";
                case CAPI.ovrAvatar2Platform.Quest:
                    return "Quest";
                case CAPI.ovrAvatar2Platform.Quest2:
                    return "Quest2";
                case CAPI.ovrAvatar2Platform.QuestPro:
                    return "QuestPro";
                case CAPI.ovrAvatar2Platform.Quest3:
                    return "Quest3";
            }

            return "Unknown";
        }
    }
}
