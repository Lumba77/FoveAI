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

using System.Runtime.InteropServices;
using System;
using System.Collections.Generic;

using AOT;

using Unity.Collections;
using UnityEngine;
using Unity.Collections.LowLevel.Unsafe;
// ReSharper disable BuiltInTypeReferenceStyle
// ReSharper disable InconsistentNaming
// ReSharper disable RedundantDefaultMemberInitializer
// ReSharper disable RedundantArgumentDefaultValue

namespace Oculus.Avatar2.Experimental
{
    using ovrAvatar2Result = Avatar2.CAPI.ovrAvatar2Result;
    using ovrAvatar2Space = Avatar2.CAPI.ovrAvatar2Space;
    using ovrAvatar2Transform = Avatar2.CAPI.ovrAvatar2Transform;
    using ovrAvatar2EntityId = Avatar2.CAPI.ovrAvatar2EntityId;
    using ovrAvatar2LogLevel = Avatar2.CAPI.ovrAvatar2LogLevel;
    using ovrAvatar2DataBuffer = Avatar2.CAPI.ovrAvatar2DataBuffer;
    using ovrAvatar2SizeType = UIntPtr;

    public static partial class CAPI
    {

        [StructLayout(LayoutKind.Sequential)]
        public unsafe ref struct ovrAvatar2Prototype_Behavior_Pose
        {
            // space that the pose is expressed in
            // must be either ovrAvatar2Space_Local or ovrAvatar2Space_Object
            public ovrAvatar2Space space;

            // number of transforms in the pose
            public UInt32 transformCount;

            // transformCount-sized array with transforms of all joints in the hierarchy
            public ovrAvatar2Transform* transforms;

            // transformCount-sized bit array with bits indicating whether corresponding transforms
            // are set (1) or masked out (0)
            // bit array comprised of 32-bit elements, so actual array size is: 1 + (transformCount - 1) / 32
            public UInt32* transformsMask;

            // number of floats in the pose
            public UInt32 floatCount;

            // floatCount-sized array with all values of float channels in the hierarchy
            public float* floats;

            // floatCount-sized bit array with bits indicating whether corresponding floats are
            // set (1) or masked out (0)
            // bit array comprised of 32-bit elements, so actual array size is: 1 + (floatCount - 1) /32
            public UInt32* floatsMask;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public unsafe ref struct ovrAvatar2Prototype_Behavior_Hierarchy
        {
            // number of joints in the hierarchy
            public UInt32 jointCount;

            // jointCount-sized array with names of all joints
            // optionally allocated/set?
            public byte** jointNames;

            // jointCount-sized array with parent indices of all joints
            public UInt32* jointParentIndices;

            // number of float channels in the hierarchy
            public UInt32 floatCount;

            // floatCount-sized array with names of all float channels
            // optionally allocated/set?
            public byte** floatNames;

            // vector pointing forward from the default-pose root the default pose
            public Avatar2.CAPI.ovrAvatar2Vector3f forwardDirection;

            // default pose of the hierarchy
            public ovrAvatar2Prototype_Behavior_Pose defaultPose;
        }

        // callback used to implement an app-defined pose node
        // a pose node may take a pose as an input, and produces an output pose
        // `pose` will be allocated and initialized by the SDK
        // if the pose node has an input pose hooked up to it, that's what the provided pose will be set to
        // otherwise the pose will be initialized to the hierarchy's default pose
        // the application may then modify or set the pose in place
        // return true if the pose was modified or set
        // otherwise return false
        //
        //          NOTE: Callback will be invoked during animation updates.
        //          NO guarantees are provided as to which threads will be used - callbacks must be fully thread safe
        //          Callback can and will be invoked multiple times concurrently (in parallel)
        //
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private unsafe delegate bool ovrAvatar2Prototype_Behavior_PoseNodeCallback(
            ovrAvatar2EntityId entityId,
            ref ovrAvatar2Prototype_Behavior_Pose pose,
          in ovrAvatar2Prototype_Behavior_Hierarchy hierarchy,
          void* userContext
        );

        // register a pose node function
        // name may be referenced by "funcName" property
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern unsafe ovrAvatar2Result ovrAvatar2Prototype_Behavior_RegisterPoseNodeFunc(
          ovrAvatar2StringView name,
          ovrAvatar2Prototype_Behavior_PoseNodeCallback callback,
          void* userContext);

        // unregister a pose node function
        // any evaluated pose node referencing this function will be treated as a passthrough node
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Prototype_Behavior_UnregisterPoseNode(ovrAvatar2StringView name);


        // register hierarchy with behavior system
        // this is required for any app pose node that performs retargeting
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Prototype_Behavior_RegisterHierarchy(
            ovrAvatar2StringView name, in ovrAvatar2Prototype_Behavior_Hierarchy hierarchy, bool forceOverride);

        // unregister hierarchy
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        private static extern ovrAvatar2Result ovrAvatar2Prototype_Behavior_UnregisterHierarchy(ovrAvatar2StringView name);

        public sealed class BehaviorPose : IDisposable
        {
            private const string LOG_SCOPE = nameof(BehaviorPose);
            private const NativeArrayOptions kArrayOptions = NativeArrayOptions.UninitializedMemory;
            private const Allocator kArrayAllocator = Allocator.Persistent;

            public ovrAvatar2Space space;
            public NativeArray<ovrAvatar2Transform> transforms;
            public NativeArray<bool> transformsMask;
            public NativeArray<float> floats;
            public NativeArray<bool> floatsMask;


            // Creates a pose in managed memory from a pose in unmanaged memory
            internal unsafe BehaviorPose(ovrAvatar2Prototype_Behavior_Pose unmanagedPose)
            {
                // read the space
                this.space = unmanagedPose.space;

                var transformCount = (int)unmanagedPose.transformCount;

                // read the transform arra
                this.transforms = new NativeArray<ovrAvatar2Transform>(transformCount, kArrayAllocator, kArrayOptions);
                var tmpTransforms = NativeArrayUnsafeUtility.ConvertExistingDataToNativeArray<ovrAvatar2Transform>(unmanagedPose.transforms, transformCount, Allocator.None);
#if ENABLE_UNITY_COLLECTIONS_CHECKS
                NativeArrayUnsafeUtility.SetAtomicSafetyHandle(ref tmpTransforms, AtomicSafetyHandle.GetTempMemoryHandle());
#endif
                this.transforms.CopyFrom(tmpTransforms);

                // read the transform masks
                this.transformsMask = new NativeArray<bool>(transformCount, kArrayAllocator, kArrayOptions);
                bool* transformsMaskPtr = (bool*)this.transforms.GetUnsafePtr();
                for (int i = 0; i < transformCount; i++)
                {
                    int offset = i / 32;
                    UInt32 val = unmanagedPose.transformsMask[offset];
                    int bitOffset = i % 32;
                    transformsMaskPtr[i] = (val & 1 << bitOffset) > 0;
                }

                var floatsCount = (int)unmanagedPose.floatCount;

                // read the float array
                this.floats = new NativeArray<float>(floatsCount, kArrayAllocator, kArrayOptions);
                var tmpFloats = NativeArrayUnsafeUtility.ConvertExistingDataToNativeArray<float>(unmanagedPose.floats, floatsCount, Allocator.None);
#if ENABLE_UNITY_COLLECTIONS_CHECKS
                NativeArrayUnsafeUtility.SetAtomicSafetyHandle(ref tmpFloats, AtomicSafetyHandle.GetTempMemoryHandle());
#endif
                this.floats.CopyFrom(tmpFloats);

                // read the float masks
                this.floatsMask = new NativeArray<bool>(floatsCount, kArrayAllocator, kArrayOptions);
                bool* floatsMaskPtr = (bool*)this.floatsMask.GetUnsafePtr();
                for (int i = 0; i < floatsCount; i++)
                {
                    int offset = i / 32;
                    UInt32 val = unmanagedPose.floatsMask[offset];
                    int bitOffset = i % 32;
                    floatsMaskPtr[i] = (val & 1 << bitOffset) > 0;
                }
            }

            internal unsafe BehaviorPose(BehaviorPose pose)
            {
                this.space = pose.space;
                // read the transform arra
                this.transforms = new NativeArray<ovrAvatar2Transform>(pose.transforms.Length, kArrayAllocator, kArrayOptions);
                this.transforms.CopyFrom(pose.transforms);

                // read the transform masks
                this.transformsMask = new NativeArray<bool>(pose.transformsMask.Length, kArrayAllocator, kArrayOptions);
                this.transformsMask.CopyFrom(pose.transformsMask);

                // read the float array
                this.floats = new NativeArray<float>(pose.floats.Length, kArrayAllocator, kArrayOptions);
                this.floats.CopyFrom(pose.floats);

                // read the float masks
                this.floatsMask = new NativeArray<bool>(pose.floatsMask.Length, kArrayAllocator, kArrayOptions);
                this.floatsMask.CopyFrom(pose.floatsMask);
            }

            internal unsafe ovrAvatar2Prototype_Behavior_Pose AllocateUnmanagedCopy()
            {
                var transformsCount = transforms.Length;
                var floatsCount = floats.Length;

                ovrAvatar2Prototype_Behavior_Pose unmanagedPose;
                unmanagedPose.space = space;
                unmanagedPose.transformCount = (uint)transformsCount;
                unmanagedPose.transforms = (ovrAvatar2Transform*)Marshal.AllocHGlobal(transformsCount * Marshal.SizeOf(typeof(ovrAvatar2Transform)));
                System.Diagnostics.Debug.Assert(unmanagedPose.transforms != null, "unmanagedPose.transforms != null");


                ovrAvatar2Transform* transformPtr = (ovrAvatar2Transform*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(this.transforms);
                for (uint i = 0; i < transformsCount; i++)
                {
                    unmanagedPose.transforms[i] = transformPtr[i];
                }

                int transformsMaskCount = 1 + (transformsCount - 1) / 32;
                unmanagedPose.transformsMask = (uint*)Marshal.AllocHGlobal(transformsMaskCount * Marshal.SizeOf(typeof(uint)));
                System.Diagnostics.Debug.Assert(unmanagedPose.transformsMask != null, "unmanagedPose.transformsMask != null");

                for (int i = 0; i < transformsMaskCount; i++)
                {
                    unmanagedPose.transformsMask[i] = 0;
                }

                bool* transformsMaskPtr = (bool*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(this.transformsMask);
                for (int i = 0; i < transformsCount; i++)
                {
                    int offset = i / 32;
                    int bitOffset = i % 32;
                    if (transformsMaskPtr[i])
                    {
                        uint val = (uint)1 << bitOffset;
                        unmanagedPose.transformsMask[offset] |= val;
                    }
                }

                unmanagedPose.floatCount = (uint)floatsCount;
                unmanagedPose.floats = (float*)Marshal.AllocHGlobal(floatsCount * Marshal.SizeOf(typeof(float)));
                System.Diagnostics.Debug.Assert(unmanagedPose.floats != null, "unmanagedPose.floats != null");

                float* floatsPtr = (float*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(this.floats);
                for (int i = 0; i < floatsCount; i++)
                {
                    unmanagedPose.floats[i] = floatsPtr[i];
                }

                int floatsMaskCount = 1 + (floats.Length - 1) / 32;
                unmanagedPose.floatsMask = (uint*)Marshal.AllocHGlobal(floatsMaskCount * Marshal.SizeOf(typeof(uint)));
                System.Diagnostics.Debug.Assert(unmanagedPose.floatsMask != null, "unmanagedPose.floatsMask != null");

                for (int i = 0; i < transformsMaskCount; i++)
                {
                    unmanagedPose.transformsMask[i] = 0;
                }

                bool* floatsMaskPtr = (bool*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(this.floatsMask);
                for (int i = 0; i < floatsCount; i++)
                {
                    int offset = i / 32;
                    int bitOffset = i % 32;
                    if (floatsMaskPtr[i])
                    {
                        uint val = (uint)1 << bitOffset;
                        unmanagedPose.floatsMask[offset] |= val;
                    }
                }

                return unmanagedPose;
            }

            internal static unsafe void ReleaseUnmanagedPose(ref ovrAvatar2Prototype_Behavior_Pose unmanagedPose)
            {
                unmanagedPose.transformCount = 0;
                Marshal.FreeHGlobal((IntPtr)unmanagedPose.transforms);
                unmanagedPose.transforms = null;
                Marshal.FreeHGlobal((IntPtr)unmanagedPose.transformsMask);
                unmanagedPose.transformsMask = null;
                unmanagedPose.floatCount = 0;
                Marshal.FreeHGlobal((IntPtr)unmanagedPose.floats);
                unmanagedPose.floats = null;
                Marshal.FreeHGlobal((IntPtr)unmanagedPose.floatsMask);
                unmanagedPose.floatsMask = null;
            }

            internal unsafe void UpdateUnmanagedPose(ref ovrAvatar2Prototype_Behavior_Pose unmanagedPose)
            {
                space = unmanagedPose.space;
                if (unmanagedPose.transformCount != transforms.Length)
                {
                    OvrAvatarLog.LogError("Transform array length mismatch. Unable to sync with unmanaged pose", LOG_SCOPE);
                }

                // set the transform array
                ovrAvatar2Transform* transformsPtr = (ovrAvatar2Transform*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(transforms);
                // set the transform array
                for (int i = 0; i < unmanagedPose.transformCount; i++)
                {
                    unmanagedPose.transforms[i] = transformsPtr[i];
                }

                if (unmanagedPose.floatCount != floats.Length)
                {
                    OvrAvatarLog.LogError("Float array length mismatch. Unable to sync with unmanaged pose", LOG_SCOPE);
                }

                // set the float array
                float* floatsPtr = (float*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(floats);
                for (int i = 0; i < unmanagedPose.floatCount; i++)
                {
                    unmanagedPose.floats[i] = floatsPtr[i];
                }
            }

            internal unsafe void SyncWithUnmanagedPose(in ovrAvatar2Prototype_Behavior_Pose unmanagedPose)
            {
                space = unmanagedPose.space;
                if (unmanagedPose.transformCount != transforms.Length)
                {
                    OvrAvatarLog.LogError("Transform array length mismatch. Unable to sync with unmanaged pose", LOG_SCOPE);
                }

                // set the transform array
                ovrAvatar2Transform* transformsPtr = (ovrAvatar2Transform*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(transforms);
                for (int i = 0; i < unmanagedPose.transformCount; i++)
                {
                    transformsPtr[i] = unmanagedPose.transforms[i];
                }

                if (unmanagedPose.floatCount != floats.Length)
                {
                    OvrAvatarLog.LogError("Float array length mismatch. Unable to sync with unmanaged pose", LOG_SCOPE);
                }

                float* floatsPtr = (float*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(floats);
                // set the float array
                for (int i = 0; i < unmanagedPose.floatCount; i++)
                {
                    floatsPtr[i] = unmanagedPose.floats[i];
                }
            }

            internal void SyncWithPose(BehaviorPose pose)
            {
                space = pose.space;
                if (pose.transforms.Length != transforms.Length)
                {
                    OvrAvatarLog.LogError("Transform array length mismatch. Unable to sync with unmanaged pose", LOG_SCOPE);
                }

                transforms.CopyFrom(pose.transforms);

                if (pose.floats.Length != floats.Length)
                {
                    OvrAvatarLog.LogError("Float array length mismatch. Unable to sync with unmanaged pose", LOG_SCOPE);
                }

                floats.CopyFrom(pose.floats);
            }

            public void Dispose()
            {
                transforms.Dispose();
                transformsMask.Dispose();
                floats.Dispose();
                floatsMask.Dispose();
            }
        }

        public sealed class BehaviorHierarchy : IDisposable
        {
            public string[] jointNames;
            public uint[] jointParentIndices;
            public string[] floatNames;
            public Avatar2.CAPI.ovrAvatar2Vector3f forwardDirection;
            public BehaviorPose defaultPose;
            private string? _name;
            private ovrAvatar2EntityId? _entityId;

            public bool Register(string name)
            {
                bool success = false;
                if (_name == null)
                {
                    var unmanagedHierarchy = AllocateUnmanagedCopy();
                    using (var nameStringView = new StringHelpers.StringViewAllocHandle(name, Allocator.Temp))
                    {
                        ovrAvatar2Result res;
                        res = ovrAvatar2Prototype_Behavior_RegisterHierarchy(
                                nameStringView.StringView, unmanagedHierarchy, false);
                        success = res.EnsureSuccess("ovrAvatar2Prototype_Behavior_RegisterHierarchy");
                    }

                    if (success)
                    {
                        _name = name;
                    }
                    ReleaseUnmanagedCopy(ref unmanagedHierarchy);
                }
                return success;
            }

            public bool Unregister()
            {
                bool success = false;
                if (_name != null)
                {
                    using var nameStringView = new StringHelpers.StringViewAllocHandle(_name, Allocator.Temp);
                    ovrAvatar2Result res;
                    res = ovrAvatar2Prototype_Behavior_UnregisterHierarchy(nameStringView.StringView);
                    if (res.EnsureSuccess("ovrAvatar2Prototype_Behavior_UnregisterHierarchy"))
                    {
                        _name = null;
                        success = true;
                    }
                }
                return success;
            }

            internal unsafe BehaviorHierarchy(ovrAvatar2Prototype_Behavior_Hierarchy unmanagedHierarchy, string? name = null)
            {
                _name = name;
                var jointCount = unmanagedHierarchy.jointCount;
                jointNames = new string[jointCount];
                for (var i = 0; i < jointCount; i++)
                {
                    jointNames[i] = Marshal.PtrToStringAnsi((IntPtr)unmanagedHierarchy.jointNames[i]);
                }
                jointParentIndices = new uint[jointCount];
                for (var i = 0; i < jointCount; i++)
                {
                    jointParentIndices[i] = unmanagedHierarchy.jointParentIndices[i];
                }
                var floatCount = unmanagedHierarchy.floatCount;
                floatNames = new string[floatCount];
                for (var i = 0; i < floatCount; i++)
                {
                    floatNames[i] = Marshal.PtrToStringAnsi((IntPtr)unmanagedHierarchy.floatNames[i]);
                }

                forwardDirection = unmanagedHierarchy.forwardDirection;
                defaultPose = new BehaviorPose(unmanagedHierarchy.defaultPose);
            }

            private unsafe ovrAvatar2Prototype_Behavior_Hierarchy AllocateUnmanagedCopy()
            {
                ovrAvatar2Prototype_Behavior_Hierarchy unmanagedHierarchy;
                unmanagedHierarchy.floatCount = (uint)floatNames.Length;
                unmanagedHierarchy.floatNames = (byte**)Marshal.AllocHGlobal(floatNames.Length * Marshal.SizeOf(typeof(byte*)));
                System.Diagnostics.Debug.Assert(unmanagedHierarchy.floatNames != null, "unmanagedHierarchy.floatNames != null");

                for (int i = 0; i < unmanagedHierarchy.floatCount; i++)
                {
                    unmanagedHierarchy.floatNames[i] = (byte*)Marshal.StringToHGlobalAnsi(floatNames[i]);
                }
                unmanagedHierarchy.jointCount = (uint)jointNames.Length;
                unmanagedHierarchy.jointNames = (byte**)Marshal.AllocHGlobal(jointNames.Length * Marshal.SizeOf(typeof(byte*)));
                System.Diagnostics.Debug.Assert(unmanagedHierarchy.jointNames != null, "unmanagedHierarchy.jointNames != null");

                unmanagedHierarchy.jointParentIndices = (uint*)Marshal.AllocHGlobal(jointNames.Length * Marshal.SizeOf(typeof(uint)));
                System.Diagnostics.Debug.Assert(unmanagedHierarchy.jointParentIndices != null, "unmanagedHierarchy.jointParentIndices != null");

                for (int i = 0; i < unmanagedHierarchy.jointCount; i++)
                {
                    unmanagedHierarchy.jointNames[i] = (byte*)Marshal.StringToHGlobalAnsi(jointNames[i]);
                    unmanagedHierarchy.jointParentIndices[i] = jointParentIndices[i];
                }
                unmanagedHierarchy.defaultPose = defaultPose.AllocateUnmanagedCopy();
                unmanagedHierarchy.forwardDirection = Vector3.forward.ConvertSpace();
                return unmanagedHierarchy;
            }

            private static unsafe void ReleaseUnmanagedCopy(ref ovrAvatar2Prototype_Behavior_Hierarchy unmanagedHierarchy)
            {
                for (int i = 0; i < unmanagedHierarchy.jointCount; i++)
                {
                    Marshal.FreeHGlobal((IntPtr)unmanagedHierarchy.jointNames[i]);
                    unmanagedHierarchy.jointNames[i] = null;
                }
                Marshal.FreeHGlobal((IntPtr)unmanagedHierarchy.jointNames);
                unmanagedHierarchy.jointNames = null;
                unmanagedHierarchy.jointCount = 0;
                for (int i = 0; i < unmanagedHierarchy.floatCount; i++)
                {
                    Marshal.FreeHGlobal((IntPtr)unmanagedHierarchy.floatNames[i]);
                    unmanagedHierarchy.floatNames[i] = null;
                }
                Marshal.FreeHGlobal((IntPtr)unmanagedHierarchy.floatNames);
                unmanagedHierarchy.floatNames = null;
                unmanagedHierarchy.floatCount = 0;
                BehaviorPose.ReleaseUnmanagedPose(ref unmanagedHierarchy.defaultPose);
            }

            public void Dispose()
            {
                Unregister();
                defaultPose.Dispose();
            }
        }

        public sealed class AppPoseNodeCallback : IDisposable
        {
            private const string LOG_SCOPE = "AppPoseNodeCallback";

            private static Dictionary<IntPtr, AppPoseNodeCallback>? s_nodeLookup = null;

            //  NOTE: PoseFunction will be invoked during animation updates.
            //      NO guarantees are provided as to which threads will be used
            //      PoseFunction must be fully thread safe
            //      PoseFunction can and will be invoked multiple times concurrently (in parallel)
            public delegate bool PoseFunction(ovrAvatar2EntityId entityId, ref BehaviorPose pose,
                in BehaviorHierarchy hierarchy, object? userData = null);

            private readonly string _name;
            private readonly ovrAvatar2EntityId? _entityId;
            private StringHelpers.StringViewAllocHandle _nameHandle;

            private bool IsRegistered => !_nameHandle.IsEmpty;

            private PoseFunction? _poseFunction;
            private object? _userData;

            private Dictionary<ovrAvatar2EntityId, EntityInfo> _entityInfoCache = new Dictionary<ovrAvatar2EntityId, EntityInfo>();

            //  NOTE: poseFunction will be invoked during animation updates.
            //      NO guarantees are provided as to which threads will be used
            //      poseFunction must be fully thread safe
            //      poseFunction can and will be invoked multiple times in parallel, and thus must be stateless
            public AppPoseNodeCallback(string name, PoseFunction poseFunction, object? userData = null)
                : this(name, null, poseFunction, userData)
            {
            }

            public AppPoseNodeCallback(string name, ovrAvatar2EntityId? entityId, PoseFunction poseFunction, object? userData = null)
            {
                _name = name;
                _entityId = entityId;
                _poseFunction = poseFunction;
                _userData = userData;
                Register();
            }


            ~AppPoseNodeCallback()
            {
                Unregister();
            }

            public void Dispose()
            {
                Unregister();
                GC.SuppressFinalize(this);
            }

            private bool Run(ovrAvatar2EntityId entityId, ref BehaviorPose pose,
                in BehaviorHierarchy hierarchy)
            {
                return _poseFunction != null && _poseFunction(entityId, ref pose, hierarchy, _userData);
            }

            private void Register()
            {
                _nameHandle = new StringHelpers.StringViewAllocHandle(_name, Allocator.Persistent);
                var nameView = _nameHandle.StringView;

                IntPtr nameKey;
                ovrAvatar2Result res;
                unsafe
                {
                    nameKey = (IntPtr)nameView.data;
                    res = ovrAvatar2Prototype_Behavior_RegisterPoseNodeFunc(
                            nameView, CallbackWrapper, nameView.data);
                }

                if (res.EnsureSuccess("ovrAvatar2Prototype_Behavior_RegisterPoseNodeFunc", LOG_SCOPE))
                {
                    s_nodeLookup ??= new();
                    s_nodeLookup.Add(nameKey, this);
                }
                else
                {
                    OvrAvatarLog.LogError($"AppPoseNode callback {_name} could not be registered", LOG_SCOPE);
                    _nameHandle.Reset();
                }
            }

            private void Unregister()
            {
                if (!IsRegistered) { return; }

                var nameView = _nameHandle.StringView;
                ovrAvatar2Result res = ovrAvatar2Prototype_Behavior_UnregisterPoseNode(_nameHandle.StringView);

                if (res.EnsureSuccess("ovrAvatar2Prototype_Behavior_UnregisterPoseNode", LOG_SCOPE))
                {
                    IntPtr nameKey;
                    unsafe { nameKey = (IntPtr)nameView.data; }
                    if (s_nodeLookup is not null)
                    {
                        s_nodeLookup.Remove(nameKey);
                    }
                }
                else
                {
                    OvrAvatarLog.LogError($"AppPoseNode callback {_name} could not be unregistered", LOG_SCOPE);
                }

                _poseFunction = null;
                _userData = null;

                _nameHandle.Reset();

                foreach (var entry in _entityInfoCache)
                {
                    entry.Value.Dispose();
                }

                _entityInfoCache.Clear();
            }

            private static unsafe ovrAvatar2Prototype_Behavior_PoseNodeCallback CallbackWrapper
                // ReSharper disable once HeapView.DelegateAllocation
                => s_callbackWrapperCache ??= _callbackWrapper;
            private static ovrAvatar2Prototype_Behavior_PoseNodeCallback? s_callbackWrapperCache = null;

            [MonoPInvokeCallback(typeof(ovrAvatar2Prototype_Behavior_PoseNodeCallback))]
            private static unsafe bool _callbackWrapper(
                ovrAvatar2EntityId entityId,
                ref ovrAvatar2Prototype_Behavior_Pose unmanagedPose,
                in ovrAvatar2Prototype_Behavior_Hierarchy unmanagedHierarchy,
                void* userContext)
            {
                if (s_nodeLookup == null || !s_nodeLookup.TryGetValue((IntPtr)userContext, out var node))
                {
                    return false;
                }

                // Caching hierarchy and pose to avoid generating a new container per frame
                if (!node._entityInfoCache.TryGetValue(entityId, out var cachedEntityInfo))
                {
                    cachedEntityInfo = new EntityInfo(new BehaviorHierarchy(unmanagedHierarchy), new BehaviorPose(unmanagedPose));
                    node._entityInfoCache[entityId] = cachedEntityInfo;
                }
                else
                {
                    // if cache exists, sync latest pose data from unmanaged pose to managed cached pose
                    cachedEntityInfo.CachedPose.SyncWithUnmanagedPose(unmanagedPose);
                }

                if (!node.Run(entityId, ref cachedEntityInfo.CachedPose, in cachedEntityInfo.CachedHierarchy))
                {
                    return false;
                }

                // assigning data back to unmanaged pose
                cachedEntityInfo.CachedPose.UpdateUnmanagedPose(ref unmanagedPose);
                return true;
            }

            public void SignalEntityDeregistration(ovrAvatar2EntityId entityId)
            {
                if (_entityInfoCache.TryGetValue(entityId, out var cachedEntityInfo))
                {
                    cachedEntityInfo.CachedHierarchy.Dispose();
                    cachedEntityInfo.CachedPose.Dispose();
                    _entityInfoCache.Remove(entityId);
                }
            }

            private class EntityInfo : IDisposable
            {
                public BehaviorHierarchy CachedHierarchy;
                public BehaviorPose CachedPose;

                public EntityInfo(BehaviorHierarchy hierarchy, BehaviorPose pose)
                {
                    CachedHierarchy = hierarchy;
                    CachedPose = pose;
                }

                public void Dispose()
                {
                    CachedHierarchy.Dispose();
                    CachedPose.Dispose();
                }
            }
        } // AppPoseNodeCallback

        //-----------------------------------------------------------------
        //
        //   Debug Queries
        //
        //   A Behavior Debug Query is used to request information that may be obtained during behavior system evaluation.
        //
        //
        //   Behavior Debug Query Types
        //
        //   Pose Trace
        //
        //   A pose trace is a trace of all pose operations executed by an entity's behavior. This includes information about
        //   all poses provided through SDK tracking/input APIs as well as sampled animation clips, slerp/additive blends,
        //   transform overriding, masking, etc.
        //
        //

        /// The type of this debug query, which determines the type and format of data retrieved from behavior evaluation.
        public enum ovrAvatar2Prototype_BehaviorDebugQueryType : Int32
        {
            // Default, invalid value for query type. If valid type is not set, ovrAvatar2Prototype_Behavior_AddDebugQuery will fail.
            Invalid = 0,

            // Trace of all operations performed to construct the final output pose. Does not include full pose/mask data.
            PoseTrace = 1,

            // Trace of all currently active state machine states.
            StateTrace = 2,
        }

        public enum ovrAvatar2Prototype_BehaviorDebugQueryId : Int32
        {
            Invalid = 0,
        }

        public enum ovrAvatar2Prototype_BehaviorDebugQueryFlag : Int32
        {
            /// whether the query should fire once and then be automatically removed
            FireOnce = 1 << 0,

            /// whether to send debug output formatted for readability as a null-terminated string to logs
            /// output is logged with Debug log level
            /// output may be split into chunks according to max log length to avoid truncation
            LogOutput = 1 << 1,

            /// whether to store debug output formatted for readability as a null-terminated string for retrieval with ovrAvatar2Prototype_Behavior_GetDebugQuery
            /// not compatible with FireOnce
            StoreOutput = 1 << 2,

            /// whether to call the provided callback with with debug output formatted for readability as a null-terminated string
            CallbackFormattedOutput = 1 << 3,

            /// whether to call the provided callback with with binary-encoded debug output
            CallbackBinaryOutput = 1 << 4,

            /// whether to send binary-encoded debug output via the debug server to any connected clients
            TransmitOutput = 1 << 5,

            None = 0,
            All = 0
                                                             | FireOnce
                                                             | LogOutput
                                                             | StoreOutput
                                                             | CallbackFormattedOutput
                                                             | CallbackBinaryOutput
                                                             | TransmitOutput,
        }

        // Callback used to handle debug query output.
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public unsafe delegate void ovrAvatar2Prototype_Behavior_DebugQueryCallback(
            ovrAvatar2DataView queryOutput,
            void* userContext
        );

        [StructLayout(LayoutKind.Sequential)]
        public unsafe struct ovrAvatar2Prototype_BehaviorDebugQuery
        {
            // the type of debug query
            public ovrAvatar2Prototype_BehaviorDebugQueryType type;

            // flags controlling how the query runs
            public ovrAvatar2Prototype_BehaviorDebugQueryFlag flags;

            // log level to be used with ovrAvatar2Prototype_BehaviorDebugQueryFlag_LogOutput
            public ovrAvatar2LogLevel logLevel;

            // callback for the app to handle debug output
            // this will be invoked during ovrAvatar2_Update after the entity's behavior has been evaluated
            public ovrAvatar2Prototype_Behavior_DebugQueryCallback callback;

            //< user context ptr provided to callback
            public void* callbackUserContext;
        }

        /// return ovrAvatar2Prototype_BehaviorDebugQuery with default values
        /// the query type will be initialized to invalid and must be explicitly set
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern ovrAvatar2Prototype_BehaviorDebugQuery ovrAvatar2Prototype_DefaultBehaviorDebugQuery();

        /// add a behavior debug query to the entity
        /// this will result in behavior evaluation performing additional work to fulfill the query
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern unsafe ovrAvatar2Result ovrAvatar2Prototype_Behavior_AddDebugQuery(
          ovrAvatar2EntityId entityId,
          in ovrAvatar2Prototype_BehaviorDebugQuery debugQuery,
          out ovrAvatar2Prototype_BehaviorDebugQueryId outDebugQueryId);

        /// remove behavior debug query from entity
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern unsafe ovrAvatar2Result ovrAvatar2Prototype_Behavior_RemoveDebugQuery(
          ovrAvatar2EntityId entityId,
          ovrAvatar2Prototype_BehaviorDebugQueryId debugQueryId);

        /// get the current size of this debug query's output, which is the size of buffer required by ovrAvatar2Prototype_Behavior_GetDebugQueryOutput
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern unsafe ovrAvatar2Result ovrAvatar2Prototype_Behavior_GetDebugQueryOutputSize(
          ovrAvatar2EntityId entityId,
          ovrAvatar2Prototype_BehaviorDebugQueryId debugQueryId,
          out ovrAvatar2SizeType queryOutputSize);


        /// get output of a behavior debug query, which will be copied into queryOutputBuffer
        /// if any output was copied, return ovrAvatar2Success.
        /// If the query is empty, return ovrAvatar2Result_DataNotAvailable (meaning ovrAvatar2Prototype_Behavior_GetDebugQueryOutputSize may have succeeded but gave a size of zero)
        [DllImport(Avatar2.CAPI.LibFile, CallingConvention = CallingConvention.Cdecl)]
        public static extern unsafe ovrAvatar2Result ovrAvatar2Prototype_Behavior_GetDebugQueryOutput(
          ovrAvatar2EntityId entityId,
          ovrAvatar2Prototype_BehaviorDebugQueryId debugQueryId,
          out ovrAvatar2DataBuffer queryOutput);

        public abstract class DebugQuery : IDisposable
        {
            private const string LOG_SCOPE = "DebugQuery";

            private static Dictionary<ovrAvatar2Prototype_BehaviorDebugQueryId, DebugQuery>? s_queryLookup = null;

            private ovrAvatar2Prototype_BehaviorDebugQuery _queryOptions;

            private readonly ovrAvatar2EntityId _entityId;
            private ovrAvatar2Prototype_BehaviorDebugQueryId _queryId;
            private bool IsRegistered => _queryId != ovrAvatar2Prototype_BehaviorDebugQueryId.Invalid;
            public delegate bool QueryCallbackFunction(in DebugQuery query);
            private unsafe QueryCallbackFunction? _callbackFunction;

            private string? _output;
            public string? Output => _output;

            private string _name;
            public string Name => _name;

            protected DebugQuery(
                string name,
                ovrAvatar2EntityId entityId,
                ovrAvatar2Prototype_BehaviorDebugQueryType queryType,
                ovrAvatar2Prototype_BehaviorDebugQueryFlag queryFlags,
                QueryCallbackFunction callbackFunction
                )
            {
                _name = name;
                _entityId = entityId;
                _callbackFunction = callbackFunction;
                _queryId = ovrAvatar2Prototype_BehaviorDebugQueryId.Invalid;
                _queryOptions.flags = queryFlags;
                _queryOptions.type = queryType;
                _queryOptions.callback = CallbackWrapper;
                unsafe
                {
                    fixed (void* queryIdPtr = &_queryId)
                    {
                        _queryOptions.callbackUserContext = queryIdPtr;
                    }
                }
                Register();
            }

            ~DebugQuery()
            {
                Unregister();
            }

            public void Dispose()
            {
                Unregister();
                GC.SuppressFinalize(this);
            }

            private void Register()
            {
                ovrAvatar2Result res;
                unsafe
                {
                    res = ovrAvatar2Prototype_Behavior_AddDebugQuery(
                        _entityId, _queryOptions, out _queryId);
                }

                if (res.EnsureSuccess("ovrAvatar2Prototype_Behavior_AddDebugQuery", LOG_SCOPE))
                {
                    s_queryLookup ??= new();
                    s_queryLookup.Add(_queryId, this);
                }
                else
                {
                    OvrAvatarLog.LogError($"DebugQuery could not be added", LOG_SCOPE);
                    _queryId = ovrAvatar2Prototype_BehaviorDebugQueryId.Invalid;
                }
            }

            private void Unregister()
            {
                if (!IsRegistered) { return; }

                if (ovrAvatar2Prototype_Behavior_RemoveDebugQuery(_entityId, _queryId)
                    .EnsureSuccess("ovrAvatar2Prototype_Behavior_RemoveDebugQuery", LOG_SCOPE))
                {
                    if (s_queryLookup is not null)
                    {
                        s_queryLookup.Remove(_queryId);
                    }
                }
                else
                {
                    OvrAvatarLog.LogError($"Debug Query {_queryId} could not be unregistered", LOG_SCOPE);
                }

                _callbackFunction = null;
                _queryId = ovrAvatar2Prototype_BehaviorDebugQueryId.Invalid;
            }

            private static unsafe ovrAvatar2Prototype_Behavior_DebugQueryCallback CallbackWrapper
                // ReSharper disable once HeapView.DelegateAllocation
                => s_callbackWrapperCache ??= _callbackWrapper;
            private static ovrAvatar2Prototype_Behavior_DebugQueryCallback? s_callbackWrapperCache = null;

            [MonoPInvokeCallback(typeof(ovrAvatar2Prototype_Behavior_DebugQueryCallback))]
            private static unsafe void _callbackWrapper(
                ovrAvatar2DataView queryOutput,
                void* userContext)
            {
                ovrAvatar2Prototype_BehaviorDebugQueryId queryId = ovrAvatar2Prototype_BehaviorDebugQueryId.Invalid;
                unsafe
                {
                    queryId = *(ovrAvatar2Prototype_BehaviorDebugQueryId*)userContext;
                }
                if (s_queryLookup == null || !s_queryLookup.TryGetValue(queryId, out var query))
                {
                    return;
                }
                if (query == null)
                {
                    return;
                }
                query._output =
                    StringHelpers.CreateManagedString((byte*)queryOutput.data, queryOutput.size.ToUInt32());
                query._callbackFunction?.Invoke(query);
            }
        } // DebugQuery


        public sealed class PoseTraceDebugQuery : DebugQuery
        {
            public PoseTraceDebugQuery(
                string name,
                ovrAvatar2EntityId entityId,
                QueryCallbackFunction callbackFunction)
                : base(
                    name,
                    entityId,
                    ovrAvatar2Prototype_BehaviorDebugQueryType.PoseTrace,
                    ovrAvatar2Prototype_BehaviorDebugQueryFlag.FireOnce,
                    callbackFunction
                    )
            { }
        }

        public sealed class StateTraceDebugQuery : DebugQuery
        {
            public StateTraceDebugQuery(
                string name,
                Avatar2.CAPI.ovrAvatar2EntityId entityId,
                QueryCallbackFunction callbackFunction)
                : base(
                    name,
                    entityId,
                    ovrAvatar2Prototype_BehaviorDebugQueryType.StateTrace,
                    ovrAvatar2Prototype_BehaviorDebugQueryFlag.FireOnce,
                    callbackFunction
                )
            {
            }
        }

    } // CAPI
}
