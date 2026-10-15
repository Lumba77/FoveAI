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
using Unity.Collections.LowLevel.Unsafe;
using UnityEngine;
using UnityEngine.Assertions;
using UnityEngine.Events;
using static Oculus.Avatar2.CAPI;
using static Oculus.Avatar2.Experimental.CAPI;
using static Oculus.Avatar2.OvrAvatarManager;
using static Oculus.Avatar2.OvrAvatarManager.PuppeteerInfo;
using static Oculus.Avatar2.OvrAvatarManager.RigInfo;

namespace Oculus.Avatar2
{
    /**
     * @class OvrAvatarManager
     * Animation partial class for OvrAvatarManager
     * It allows multiple avatars to register for app pose node callback, and handles
     * the initialization and cleanup of the callback.
     *
     * It also supports app pose node animation retargeting. Avatar can be controlled through
     * the Runtime Rig (RT-rig). It is a simplified and extendable skeletal hierarchy representation that
     * allows anything to drive an avatar. In the SDK we provide a verson of the RT-rig that
     * contains the elbow and knee joint, and the OvrAvatarManager retargets unity humanoid animations
     * onto this RT-rig which in turns animate the underlying avatar.
     */
    public partial class OvrAvatarManager
    {
        // App pose node callback identifier as defined in the .behavior file
        private const string APP_POSE_NODE_IDENTIFIER = "ovrAvatar2_fullOverride";
        private const string RIG_DELTA_FILE = "RigDelta";
        private readonly Dictionary<Avatar2.CAPI.ovrAvatar2EntityId, PuppeteerInfo> _entityPuppeteerInfoMap = new Dictionary<Avatar2.CAPI.ovrAvatar2EntityId, PuppeteerInfo>();
        private readonly Dictionary<Avatar2.CAPI.ovrAvatar2EntityId, CachedEntityInfo> _cachedEntityInfoMap = new Dictionary<CAPI.ovrAvatar2EntityId, CachedEntityInfo>();
        private AppPoseNodeCallback _appPoseCallback;

        public const float AvatarRemoteDynamicScalingInputMin = 0.8f;
        public const float AvatarRemoteDynamicScalingInputMax = 1.2f;
        public const float AvatarRemoteDynamicScalingOutputMin = 0.99f;
        public const float AvatarRemoteDynamicScalingOutputMax = 1.01f;

        private const float HingeAxisThreshold = -0.8f;
        private OvrAvatarRigMapper _rigMapper = null;

        [Header("Animation Debug")]
        [Tooltip(@"Enable this to visualize where an avatar's feet are being planted. Green indicates that " +
            "the position is actively being used, yellow means that the foot is currently being interpolated " +
            "out of the position, and red means it is now inactive.")]
        [SerializeField]
        private bool _enableFootPlantingDebugVisualizations = false;

        [Tooltip(@"How long, in seconds, each foot planting location visualization object will remain before automatically being destroyed. If set to a value less than zero, the visualizations will never be automatically destroyed.")]
        [SerializeField]
        private float _footPlantingLocationVisualizationDuration = 5.0f;

        private GameObject FootPlantVisualizationContainer { get; set; } = null;
        private GameObject FootPlantStatusVisualizationContainer { get; set; } = null;

        public AvatarFootFallEvent OnAvatarFootFall = new AvatarFootFallEvent();

        internal event Action OnAnimationSystemShutdown;

        // Register avatar for animation
        public void RegisterAnimatedAvatar(OvrAvatarEntity entity, PuppeteerInfo puppeteerInfo)
        {
            var entityId = entity.internalEntityId;
            _entityPuppeteerInfoMap[entityId] = puppeteerInfo;
        }

        // Update puppeteer info for an entity
        public void UpdateAnimatedAvatarBlendFactor(OvrAvatarEntity entity, float blendFactor)
        {
            var entityId = entity.internalEntityId;
            if (!_entityPuppeteerInfoMap.TryGetValue(entityId, out var puppeteerInfo))
            {
                OvrAvatarLog.LogError($"entity {entityId} not registered for animation, registering");
                return;
            }

            if (puppeteerInfo.PuppeteerRigType != PuppeteerInfo.RigType.Both)
            {
                OvrAvatarLog.LogError($"Unable to update blend factor for puppeteer animation type: {puppeteerInfo.PuppeteerRigType} ");
                return;
            }

            if (blendFactor < 0 || blendFactor > 1)
            {
                OvrAvatarLog.LogWarning($"Blend factor must be between [0-1], clamping");
                blendFactor = Mathf.Clamp01(blendFactor);
            }

            puppeteerInfo.BlendFactor = blendFactor;
        }

        public void UpdateAnimatedAvatarUpperBodyRotationFactors(OvrAvatarEntity entity, Vector3 rotationFactors)
        {
            var entityId = entity.internalEntityId;
            if (!_entityPuppeteerInfoMap.TryGetValue(entityId, out var puppeteerInfo))
            {
                OvrAvatarLog.LogError($"entity {entityId} not registered for animation, registering");
                return;
            }

            for (int index = 0; index < 3; ++index)
            {
                if (rotationFactors[index] < -1.0f || rotationFactors[index] > 1.0f)
                {
                    OvrAvatarLog.LogWarning($"Upper body rotationFactors[{index}]: factors must be between [-1,1], clamping");
                    rotationFactors[index] = Mathf.Clamp(rotationFactors[index], -1.0f, 1.0f);
                }
            }

            puppeteerInfo.UpperBodyRotationFactors = rotationFactors;
        }

        // Unregister avatar for animation
        public void UnregisterAnimatedAvatar(OvrAvatarEntity entity)
        {
            _entityPuppeteerInfoMap.Remove(entity.internalEntityId);
            _appPoseCallback?.SignalEntityDeregistration(entity.internalEntityId);

            if (_cachedEntityInfoMap.TryGetValue(entity.internalEntityId, out var entityInfo))
            {
                entityInfo.Dispose();
                _cachedEntityInfoMap.Remove(entity.internalEntityId);
            }
        }

        private void InitializeAnimationModule()
        {
            _appPoseCallback = GenerateAppPoseNodeCallback(APP_POSE_NODE_IDENTIFIER);
        }

        private void ShutdownAnimationModule()
        {
            OnAnimationSystemShutdown?.Invoke();

            if (_appPoseCallback != null)
            {
                _appPoseCallback.Dispose();
                _appPoseCallback = null;
            }

            foreach (var entry in _cachedEntityInfoMap)
            {
                entry.Value.Dispose();
            }

            _cachedEntityInfoMap.Clear();

            OvrAvatarEntity.TeardownEntityAnimation();
        }

        // There can only be one apn callback per identifier. Since most avatars using apn will be loading the same
        // default behavior, we are generating a callback that can differentiate between different avatars and apply the correct
        // puppeteer pose.
        private AppPoseNodeCallback GenerateAppPoseNodeCallback(string identifier)
        {
            Assert.IsNull(_appPoseCallback, "AppPose callback already initialized. This can be a result of faulty cleanup or double initialization.");
            return new AppPoseNodeCallback(
                identifier,
                (Avatar2.CAPI.ovrAvatar2EntityId entityId, ref BehaviorPose pose, in BehaviorHierarchy hierarchy, object userData) =>
                {
                    if (!_entityPuppeteerInfoMap.TryGetValue(entityId, out var puppeteerInfo))
                    {
                        // entity id not registered for animation callback, exit out of callback function without modifying pose.
                        OvrAvatarLog.LogWarning($"{entityId} not registered for avatar animation. Skipping");
                        return true;
                    }

                    if (!puppeteerInfo.DidInitializeBoneTransformIndexes())
                    {
                        InitializeBoneTransformMapping(ref puppeteerInfo, pose, hierarchy);
                    }

                    CachedEntityInfo cachedEntityInfo = null;
                    if (puppeteerInfo.EnableStaticAnimationOptimization)
                    {
                        if (!_cachedEntityInfoMap.TryGetValue(entityId, out cachedEntityInfo))
                        {
                            cachedEntityInfo = new CachedEntityInfo(pose);
                            _cachedEntityInfoMap[entityId] = cachedEntityInfo;
                        }

                        // Check if animator has stopped or whether entity has already been processed once this frame
                        if (!puppeteerInfo.CheckIsAnimating(puppeteerInfo.PuppeteerRigType) || Time.frameCount == cachedEntityInfo!.LastUpdatedFrame)
                        {
                            //Copy cached pose data into the ref pose to skip rig processing
                            pose.SyncWithPose(cachedEntityInfo.Pose);
                            return true;
                        }
                    }

                    UpdateFeet(puppeteerInfo);
                    UpdateUpperBodyRotation(puppeteerInfo);
                    ProcessPuppeteerRig(ref pose, in hierarchy, puppeteerInfo);

                    if (puppeteerInfo.EnableStaticAnimationOptimization && cachedEntityInfo != null)
                    {
                        cachedEntityInfo.Pose.SyncWithPose(pose);
                        cachedEntityInfo.LastUpdatedFrame = Time.frameCount;
                    }

                    return true;
                },
                null);
        }

        private void InitializeBoneTransformMapping(ref PuppeteerInfo puppeteerInfo, BehaviorPose pose, BehaviorHierarchy hierarchy)
        {
            if (puppeteerInfo.DefaultRig != null)
            {
                InitializeBoneTransformMapping(puppeteerInfo.DefaultRig, pose, hierarchy);
            }

            if (puppeteerInfo.HumanoidRig != null)
            {
                InitializeBoneTransformMapping(puppeteerInfo.HumanoidRig, pose, hierarchy);

                // capture the supplement joints in the humanoid rig
                puppeteerInfo.HumanoidRig.JointIndexArray[(int)RigInfo.CriticalJointIndex.LeftElbow] = new BoneTransformInfo { BoneTransform = puppeteerInfo.HumanoidRig.RigMap[OvrAvatarRigConstants.RT_RIG_LEFT_ELBOW] };
                puppeteerInfo.HumanoidRig.JointIndexArray[(int)RigInfo.CriticalJointIndex.RightElbow] = new BoneTransformInfo { BoneTransform = puppeteerInfo.HumanoidRig.RigMap[OvrAvatarRigConstants.RT_RIG_RIGHT_ELBOW] };
                puppeteerInfo.HumanoidRig.JointIndexArray[(int)RigInfo.CriticalJointIndex.LeftKnee] = new BoneTransformInfo { BoneTransform = puppeteerInfo.HumanoidRig.RigMap[OvrAvatarRigConstants.RT_RIG_LEFT_KNEE] };
                puppeteerInfo.HumanoidRig.JointIndexArray[(int)RigInfo.CriticalJointIndex.RightKnee] = new BoneTransformInfo { BoneTransform = puppeteerInfo.HumanoidRig.RigMap[OvrAvatarRigConstants.RT_RIG_RIGHT_KNEE] };
            }
        }

        private void EnsureRigMapperInitialized()
        {
            if (_rigMapper != null)
            {
                return;
            }

            var rigDeltaData = Resources.Load<TextAsset>(RIG_DELTA_FILE);
            if (rigDeltaData == null)
            {
                OvrAvatarLog.Assert(rigDeltaData != null, $"Unable to load rig delta file {RIG_DELTA_FILE}");
            }

            _rigMapper = new OvrAvatarRigMapper(rigDeltaData.text);
        }

        private void InitializeBoneTransformMapping(RigInfo rigInfo, BehaviorPose pose, BehaviorHierarchy hierarchy)
        {
            // already initialized
            if (rigInfo.BoneTransformInfoList != null)
            {
                return;
            }

            if (rigInfo.Version != RigVersion.V5)
            {
                EnsureRigMapperInitialized();
            }

            rigInfo.BoneTransformInfoList = new List<BoneTransformInfo>();

            for (var boneIndex = 0; boneIndex < pose.transforms.Length; boneIndex++)
            {
                var boneName = hierarchy.jointNames[boneIndex];
                if (!rigInfo.RigMap.TryGetValue(boneName, out var boneTransform))
                {
                    continue;
                }

                Matrix4x4? rigConversionMatrix = null;
                if (_rigMapper?.TryGetTranformMatrix(boneName, out var conversionMatrix) == true)
                {
                    rigConversionMatrix = conversionMatrix;
                }

                var boneTransformInfo = new BoneTransformInfo
                {
                    BoneIndex = boneIndex,
                    BoneTransform = boneTransform,
                    ConversionMatrix = rigConversionMatrix,
                };

                rigInfo.BoneTransformInfoList.Add(boneTransformInfo);
                if (CriticalJointNames.TryGetValue(boneName, out var criticalJointIndex))
                {
                    rigInfo.JointIndexArray[(int)criticalJointIndex] = boneTransformInfo;
                }
            };
        }

        private void ProcessPuppeteerRig(ref BehaviorPose pose, in BehaviorHierarchy hierarchy, PuppeteerInfo puppeteerInfo)
        {
            if (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Default
                // animation blending is at 0, full default locomotion
                || (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Both && Mathf.Approximately(puppeteerInfo.BlendFactor, 0))
                // animation blending disabled due to rig version mismatch, running full defaut locomotion when blend factor is below 0.5
                || (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Both
                        && puppeteerInfo.DefaultRig.Version != puppeteerInfo.HumanoidRig.Version
                        && puppeteerInfo.BlendFactor < 0.5f))
            {
                ProcessRigWithoutElbowAndKnee(ref pose, hierarchy, puppeteerInfo);
            }
            else if (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Humanoid
                // animation blending is at 1, full custom locomotion
                || (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Both && Mathf.Approximately(puppeteerInfo.BlendFactor, 1))
                // animation blending disabled due to rig version mismatch, running full custom locomotion when blend factor is above 0.5
                || (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Both
                        && puppeteerInfo.DefaultRig.Version != puppeteerInfo.HumanoidRig.Version
                        && puppeteerInfo.BlendFactor >= 0.5f))
            {
                ProcessRigWithElbowsAndKnees(ref pose, hierarchy, puppeteerInfo);
            }
            else
            {
                BlendDefaultAndHumanoidRig(ref pose, hierarchy, puppeteerInfo);
            }
        }

        private unsafe void BlendDefaultAndHumanoidRig(ref BehaviorPose pose, in BehaviorHierarchy hierarchy, PuppeteerInfo puppeteerInfo)
        {
            if (puppeteerInfo.DefaultRig == null || puppeteerInfo.HumanoidRig == null)
            {
                OvrAvatarLog.LogAssert("Incomplete rig information for blending.");
                return;
            }

            var defaultBoneTransformList = puppeteerInfo.DefaultRig.BoneTransformInfoList;
            var humanoidBoneTransformList = puppeteerInfo.HumanoidRig.BoneTransformInfoList;
            ovrAvatar2Transform* transformsPtr = (ovrAvatar2Transform*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(pose.transforms);
            for (var i = 0; i < defaultBoneTransformList.Count; i++)
            {
                var defaultBoneTransformInfo = defaultBoneTransformList[i];
                var humanoidBoneTransformInfo = humanoidBoneTransformList[i];
                var blendedTransform = BlendTransforms(defaultBoneTransformInfo.BoneTransform, humanoidBoneTransformInfo.BoneTransform, puppeteerInfo.BlendFactor);
                var boneIndex = defaultBoneTransformInfo.BoneIndex;
                transformsPtr[boneIndex] = ConvertTransform(blendedTransform.position, blendedTransform.orientation, Vector3.one, puppeteerInfo.DefaultRig.Version, defaultBoneTransformInfo.ConversionMatrix);
            }

            BlendJoints(ref transformsPtr, puppeteerInfo, CriticalJointIndex.LeftShoulder, CriticalJointIndex.LeftElbow, CriticalJointIndex.LeftWrist, puppeteerInfo.HingeCorrectOverride);
            BlendJoints(ref transformsPtr, puppeteerInfo, CriticalJointIndex.RightShoulder, CriticalJointIndex.RightElbow, CriticalJointIndex.RightWrist, puppeteerInfo.HingeCorrectOverride);
            BlendJoints(ref transformsPtr, puppeteerInfo, CriticalJointIndex.LeftHip, CriticalJointIndex.LeftKnee, CriticalJointIndex.LeftAnkle, puppeteerInfo.HingeCorrectOverride);
            BlendJoints(ref transformsPtr, puppeteerInfo, CriticalJointIndex.RightHip, CriticalJointIndex.RightKnee, CriticalJointIndex.RightAnkle, puppeteerInfo.HingeCorrectOverride);

            // Copy intentionality channels for default animations
            CopyIntentionalityChannels(ref pose, hierarchy, puppeteerInfo, PuppeteerInfo.RigType.Default);
        }

        // Results from blend transform doesn't have space converted
        private CAPI.ovrAvatar2Transform BlendTransforms(Transform t1, Transform t2, float blendFactor)
        {
            var finalPosition = Vector3.Lerp(t1.localPosition, t2.localPosition, blendFactor);
            var finalRotation = Quaternion.Slerp(t1.localRotation, t2.localRotation, blendFactor);
            var finalScale = Vector3.Lerp(t1.localScale, t2.localScale, blendFactor);
            return new CAPI.ovrAvatar2Transform(finalPosition, finalRotation, finalScale);
        }

        private unsafe void ProcessRigWithElbowsAndKnees(ref BehaviorPose pose, in BehaviorHierarchy hierarchy, PuppeteerInfo info)
        {
            var rigInfo = info.HumanoidRig;
            var boneTransformList = rigInfo.BoneTransformInfoList;
            ovrAvatar2Transform* transformsPtr = (ovrAvatar2Transform*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(pose.transforms);
            for (var i = 0; i < boneTransformList.Count; i++)
            {
                var boneTransformInfo = boneTransformList[i];
                var boneIndex = boneTransformInfo.BoneIndex;
                transformsPtr[boneIndex] = ConvertTransform(boneTransformInfo, rigInfo.Version);
            }

            // Updating arms and legs
            AlignJoints(ref transformsPtr, rigInfo, CriticalJointIndex.LeftShoulder, CriticalJointIndex.LeftElbow, CriticalJointIndex.LeftWrist, info.HingeCorrectOverride);
            AlignJoints(ref transformsPtr, rigInfo, CriticalJointIndex.RightShoulder, CriticalJointIndex.RightElbow, CriticalJointIndex.RightWrist, info.HingeCorrectOverride);
            AlignJoints(ref transformsPtr, rigInfo, CriticalJointIndex.LeftHip, CriticalJointIndex.LeftKnee, CriticalJointIndex.LeftAnkle, info.HingeCorrectOverride);
            AlignJoints(ref transformsPtr, rigInfo, CriticalJointIndex.RightHip, CriticalJointIndex.RightKnee, CriticalJointIndex.RightAnkle, info.HingeCorrectOverride);
        }

        private ovrAvatar2Transform ConvertTransform(BoneTransformInfo transformInfo, RigVersion version)
        {
            return ConvertTransform(transformInfo.BoneTransform.localPosition, transformInfo.BoneTransform.localRotation, transformInfo.BoneTransform.localScale, version, transformInfo.ConversionMatrix);
        }

        private ovrAvatar2Transform ConvertTransform(Vector3 localPosition, Quaternion localRotation, Vector3 localScale, RigVersion version, Matrix4x4? conversionMatrix)
        {
            if (version == RigVersion.V5 || conversionMatrix == null)
            {
                return new ovrAvatar2Transform(localPosition, localRotation, localScale).ConvertSpaceRT();
            }

            var localTransformMatrix = Matrix4x4.TRS(localPosition, localRotation, localScale);
            var convertedTransformMatrix = conversionMatrix.Value * localTransformMatrix;
            return new ovrAvatar2Transform(convertedTransformMatrix.GetPosition(), convertedTransformMatrix.rotation, convertedTransformMatrix.lossyScale).ConvertSpaceRT();
        }

        private unsafe void ProcessRigWithoutElbowAndKnee(ref BehaviorPose pose, in BehaviorHierarchy hierarchy, PuppeteerInfo info)
        {
            var boneTransformList = info.DefaultRig.BoneTransformInfoList;
            ovrAvatar2Transform* transformsPtr = (ovrAvatar2Transform*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(pose.transforms);
            for (var i = 0; i < boneTransformList.Count; i++)
            {
                var boneTransformInfo = boneTransformList[i];
                var boneIndex = boneTransformInfo.BoneIndex;
                transformsPtr[boneIndex] = ConvertTransform(boneTransformInfo, info.DefaultRig.Version);
            }

            // Copy intentionality channels for default animations
            CopyIntentionalityChannels(ref pose, hierarchy, info, PuppeteerInfo.RigType.Default);
        }

        private unsafe void CopyIntentionalityChannels(ref BehaviorPose pose, in BehaviorHierarchy hierarchy, PuppeteerInfo info, PuppeteerInfo.RigType rigType)
        {
            var dataChannelArray = info.GetDataChannelArray(rigType);
            if (dataChannelArray == null)
            {
                // Build data channel mapping once for animations to avoid looping
                // through entire float names array on every frame
                dataChannelArray = new List<(string, int)>();
                var dataChannelNames = info.GetAvaiableDataChannels(rigType);
                for (var index = 0; index < hierarchy.floatNames.Length; index++)
                {
                    var channelName = hierarchy.floatNames[index];
                    if (dataChannelNames.Contains(channelName))
                    {
                        dataChannelArray.Add((channelName, index));
                    }
                }

                info.SetDataChannelArray(rigType, dataChannelArray);
            }

            float* floatsPtr = (float*)NativeArrayUnsafeUtility.GetUnsafeBufferPointerWithoutChecks(pose.floats);
            for (var i = 0; i < dataChannelArray.Count; i++)
            {
                var tuple = dataChannelArray[i];
                if (!info.TryGetDataChannelValue(rigType, tuple.Item1, out var channelValue))
                {
                    continue;
                }

                floatsPtr[tuple.Item2] = channelValue;
            }
        }

        private unsafe void BlendJoints(
            ref ovrAvatar2Transform* transformsPtr,
            PuppeteerInfo puppeteerInfo,
            RigInfo.CriticalJointIndex startJointIndex,
            RigInfo.CriticalJointIndex supplementJointIndex,
            RigInfo.CriticalJointIndex endJointIndex,
            OvrAvatarAnimation.HingeCorrectionOverride hingeVectorOverride)
        {
            var alignmentResult = CalculateBlendedJointAlignment(puppeteerInfo, startJointIndex, supplementJointIndex, endJointIndex, hingeVectorOverride);
            transformsPtr[alignmentResult.StartJointInfo.Index] = alignmentResult.StartJointInfo.Transform;
            transformsPtr[alignmentResult.EndJointInfo.Index] = alignmentResult.EndJointInfo.Transform;
        }

        private unsafe void AlignJoints(
            ref ovrAvatar2Transform* transformsPtr,
            RigInfo info,
            RigInfo.CriticalJointIndex startJointIndex,
            RigInfo.CriticalJointIndex supplementJointIndex,
            RigInfo.CriticalJointIndex endJointIndex,
            OvrAvatarAnimation.HingeCorrectionOverride hingeVectorOverride)
        {
            var result = CalculateJointAlignment(info, startJointIndex, supplementJointIndex, endJointIndex, hingeVectorOverride);
            transformsPtr[result.StartJointInfo.Index] = result.StartJointInfo.Transform;
            transformsPtr[result.EndJointInfo.Index] = result.EndJointInfo.Transform;
        }

        // Align the startJoint and endJoint based on information of the supplementJoint
        // Critical assumption:
        // 1. Parent child relationship: startJoint->supplementJoint->endJoint
        //
        // AlignJointResults are returned in unity space
        private AlignJointResults CalculateJointAlignment(
            RigInfo info,
            RigInfo.CriticalJointIndex startJointIndex,
            RigInfo.CriticalJointIndex supplementJointIndex,
            RigInfo.CriticalJointIndex endJointIndex,
            OvrAvatarAnimation.HingeCorrectionOverride hingeOverride)
        {
            var startJointInfo = info.JointIndexArray[(int)startJointIndex];
            var endJointInfo = info.JointIndexArray[(int)endJointIndex];
            var startJointTransform = startJointInfo.BoneTransform;
            var supplementJointTransform = info.JointIndexArray[(int)supplementJointIndex].BoneTransform;
            var endJointTransform = endJointInfo.BoneTransform;

            var alignedPoses = CalculateJointAlignment(startJointTransform, supplementJointTransform, endJointTransform, hingeOverride);
            var startJointConvertedTransform = ConvertTransform(alignedPoses.Item1.position, alignedPoses.Item1.rotation, Vector3.one, info.Version, startJointInfo.ConversionMatrix);
            var endJointConvertedTransform = ConvertTransform(alignedPoses.Item2.position, alignedPoses.Item2.rotation, Vector3.one, info.Version, endJointInfo.ConversionMatrix);

            return new AlignJointResults
            {
                StartJointInfo = new JointInfo
                {
                    Index = startJointInfo.BoneIndex,
                    Transform = startJointConvertedTransform,
                },
                EndJointInfo = new JointInfo
                {
                    Index = endJointInfo.BoneIndex,
                    Transform = endJointConvertedTransform,
                },
            };
        }

        private AlignJointResults CalculateBlendedJointAlignment(
            PuppeteerInfo info,
            RigInfo.CriticalJointIndex startJointIndex,
            RigInfo.CriticalJointIndex supplementJointIndex,
            RigInfo.CriticalJointIndex endJointIndex,
            OvrAvatarAnimation.HingeCorrectionOverride hingeVectorOverride)
        {
            var startJointInfo = info.HumanoidRig.JointIndexArray[(int)startJointIndex];
            var endJointInfo = info.HumanoidRig.JointIndexArray[(int)endJointIndex];
            var startJointTransform = startJointInfo.BoneTransform;
            var supplementJointTransform = info.HumanoidRig.JointIndexArray[(int)supplementJointIndex].BoneTransform;
            var endJointTransform = endJointInfo.BoneTransform;
            var refStartJointTransform = info.DefaultRig.JointIndexArray[(int)startJointIndex].BoneTransform;
            var refEndJointTransform = info.DefaultRig.JointIndexArray[(int)endJointIndex].BoneTransform;

            var alignedPoses = CalculateBlendedJointAlignment(
                startJointTransform,
                supplementJointTransform,
                endJointTransform,
                refStartJointTransform,
                refEndJointTransform,
                info.BlendFactor,
                hingeVectorOverride);

            var startJointConvertedTransform = ConvertTransform(alignedPoses.Item1.position, alignedPoses.Item1.rotation, Vector3.one, info.DefaultRig.Version, startJointInfo.ConversionMatrix);
            var endJointConvertedTransform = ConvertTransform(alignedPoses.Item2.position, alignedPoses.Item2.rotation, Vector3.one, info.DefaultRig.Version, endJointInfo.ConversionMatrix);
            return new AlignJointResults
            {
                StartJointInfo = new JointInfo
                {
                    Index = startJointInfo.BoneIndex,
                    Transform = startJointConvertedTransform,
                },
                EndJointInfo = new JointInfo
                {
                    Index = endJointInfo.BoneIndex,
                    Transform = endJointConvertedTransform,
                },
            };
        }

        public static (Pose, Pose) CalculateBlendedJointAlignment(
            Transform startJoint,
            Transform supplementJoint,
            Transform endJoint,
            Transform refStartJoint,
            Transform refEndjoint,
            float blendRatio,
            OvrAvatarAnimation.HingeCorrectionOverride hingeOverride)
        {
            // use world space positions to calculate world space hinge axis
            var startJointPosition = startJoint.position;
            var supplementJointPosition = supplementJoint.position;
            var endJointPosition = endJoint.position;

            // rt rig convention xAxis points from end joint towards start joint in unity space
            var xAxisNormalized = Vector3.Normalize(startJointPosition - endJointPosition);

            // find the hinge axis of the supplement joint as yAxis hint for next step calculation
            // Using legs as an example, the yAxis hint would be the hinge axis of the knee
            Func<Vector3, Vector3, Vector3> yAxisHintOverride = GenerateHingeOverrideWithTransform(supplementJoint, hingeOverride);
            Vector3 yAxisHintNormalized = CalculateHingeAxis(startJointPosition, supplementJointPosition, endJointPosition, supplementJoint.up, yAxisHintOverride);
            var startJointWorldRotation = LookWithXAxisYHint(xAxisNormalized, yAxisHintNormalized);
            var startJointLocalRotation = startJoint.parent == null ? startJointWorldRotation : Quaternion.Inverse(startJoint.parent.rotation) * startJointWorldRotation;

            // blend start joint and ref start joint in local space
            var lerpStartPosition = Vector3.Lerp(refStartJoint.localPosition, startJoint.localPosition, blendRatio);
            var lerpedStartRotation = Quaternion.Lerp(refStartJoint.localRotation, startJointLocalRotation, blendRatio);
            var startJointParentToLocalMatrix = Matrix4x4.TRS(lerpStartPosition, lerpedStartRotation, Vector3.one).inverse;

            // Next, determine end joint transform in the start joint parent space. Use the parent space transform for blending
            var endJointPoseInParentSpace = CalculateLocalSpaceTransform(startJoint.parent, endJoint.position, endJoint.rotation);
            var refEndJointPoseInParentSpace = CalculateLocalSpaceTransform(refStartJoint.parent, refEndjoint.position, refEndjoint.rotation);
            var lerpedEndJointPosition = Vector3.Lerp(refEndJointPoseInParentSpace.Item1, endJointPoseInParentSpace.Item1, blendRatio);
            var lerpedEndJointRotation = Quaternion.Lerp(refEndJointPoseInParentSpace.Item2, endJointPoseInParentSpace.Item2, blendRatio);

            // Calculate the blended endJoint local position by taking the lerped end point position from start joint parent to local space
            var endJointLocalPosition = (Vector3)(startJointParentToLocalMatrix * new Vector4(lerpedEndJointPosition.x, lerpedEndJointPosition.y, lerpedEndJointPosition.z, 1));

            // Re-encode endJoint rotation in local space based on the updated startJoint rotation from above
            var endJointLocalRotation = Quaternion.Inverse(lerpedStartRotation) * lerpedEndJointRotation;

            return (new Pose(lerpStartPosition, lerpedStartRotation), new Pose(endJointLocalPosition, endJointLocalRotation));
        }

        private static Func<Vector3, Vector3, Vector3> GenerateHingeOverrideWithTransform(Transform referenceTransform, OvrAvatarAnimation.HingeCorrectionOverride hingeOverride)
        {
            if (hingeOverride == null)
            {
                return null;
            }

            return (Vector3 hingeVector, Vector3 referenceVector) =>
            {
                return hingeOverride.Invoke(referenceTransform, hingeVector, referenceVector);
            };
        }
        // Generate two poses based on the startJoint, supplementJoint and endJoint transforms
        //
        // The first pose represnets the start joint, with local y axis aligned with the hinge axis of the supplement joint.
        // The hinge axis is calculated by crossing the two vectors generated btn the 3 points represented by start/supplement/end joints.
        // The hinge axie should always be pointing in the opposite hemisphere of the up direction of the suppliment joint otherwise the
        // joint would be facing backwards
        //
        // The second pose has the same world position and orientation as the end joint, but represented in the local space of the first pose.
        public static (Pose, Pose) CalculateJointAlignment(Transform startJoint, Transform supplementJoint, Transform endJoint, OvrAvatarAnimation.HingeCorrectionOverride hingeOverride)
        {
            // All calculation are done in world space
            var startJointPosition = startJoint.position;
            var supplementJointPosition = supplementJoint.position;
            var endJointPosition = endJoint.position;

            // rt rig convention xAxis points from end joint towards start joint in unity space
            var xAxisNormalized = Vector3.Normalize(startJointPosition - endJointPosition);

            // find the hinge axis of the supplement joint as yAxis hint for next step calculation
            // Using legs as an example, the yAxis hint would be the hinge axis of the knee
            Func<Vector3, Vector3, Vector3> yAxisHintOverride = GenerateHingeOverrideWithTransform(supplementJoint, hingeOverride);
            Vector3 yAxisHintNormalized = CalculateHingeAxis(startJointPosition, supplementJointPosition, endJointPosition, supplementJoint.up, yAxisHintOverride);
            var startJointWorldRotation = LookWithXAxisYHint(xAxisNormalized, yAxisHintNormalized);
            var startJointLocalRotation = startJoint.parent == null ? startJointWorldRotation : Quaternion.Inverse(startJoint.parent.rotation) * startJointWorldRotation;

            var startJointParentToLocalMatrix = Matrix4x4.TRS(startJoint.localPosition, startJointLocalRotation, Vector3.one).inverse;

            // Next, determine end joint transform in the start joint parent space.
            var endJointPoseInParentSpace = CalculateLocalSpaceTransform(startJoint.parent, endJoint.position, endJoint.rotation);

            // Calculate original the endJoint rotation in startJoint's parent space
            var endJointLocalPosition = (Vector3)(startJointParentToLocalMatrix * new Vector4(endJointPoseInParentSpace.Item1.x, endJointPoseInParentSpace.Item1.y, endJointPoseInParentSpace.Item1.z, 1));

            // Re-encode endJoint rotation in local space based on the updated startJoint rotation from above
            var endJointLocalRotation = Quaternion.Inverse(startJointLocalRotation) * endJointPoseInParentSpace.Item2;

            return (new Pose(startJoint.localPosition, startJointLocalRotation), new Pose(endJointLocalPosition, endJointLocalRotation));
        }

        private static (Vector3, Quaternion) CalculateLocalSpaceTransform(Transform spaceTransfrom, Vector3 worldPosition, Quaternion worldRotation)
        {
            Vector3 localPosition;
            Quaternion localRotation;
            if (spaceTransfrom != null)
            {
                localPosition = spaceTransfrom.worldToLocalMatrix * new Vector4(worldPosition.x, worldPosition.y, worldPosition.z, 1);
                localRotation = Quaternion.Inverse(spaceTransfrom.rotation) * worldRotation;
            }
            else
            {
                // if joint has no parten, joint partent space equals world space
                localPosition = worldPosition;
                localRotation = worldRotation;
            }

            return (localPosition, localRotation);
        }

        private static Vector3 CalculateHingeAxis(Vector3 startJointPosition, Vector3 supplementJointPosition, Vector3 endJointPosition, Vector3 normalizedHingeReference, Func<Vector3, Vector3, Vector3> hingeOverride = null)
        {
            var v1 = (supplementJointPosition - endJointPosition).normalized;
            var v2 = (startJointPosition - supplementJointPosition).normalized;

            Vector3 normalizedHingeAxis;
            if (hingeOverride == null)
            {
                if (Mathf.Approximately(Mathf.Abs(Vector3.Dot(v1, v2)), 1))
                {
                    // if three joints lined up in a straight line, use the normalized hinge reference as a y-hint
                    // The hinge direction should always point in the opposite hemisphere compare to the supplement joint up direction.
                    normalizedHingeAxis = normalizedHingeReference;
                }
                else
                {
                    normalizedHingeAxis = Vector3.Cross(v1, v2).normalized;

                    // Check if the suppliment joint is bending backwards by comparing it with the direction of the hinge reference.
                    // If it is bent backwards, it would be pointing in the opposition directiton of the hinge reference.
                    // To compensate, flip the sign on the cross product in order to point the hinge axis towards the reference
                    if (Vector3.Dot(normalizedHingeAxis, normalizedHingeReference) < HingeAxisThreshold)
                    {
                        normalizedHingeAxis *= -1;
                    }
                }
            }
            else
            {
                if (Mathf.Approximately(Mathf.Abs(Vector3.Dot(v1, v2)), 1))
                {
                    normalizedHingeAxis = hingeOverride.Invoke(Vector3.zero, normalizedHingeReference);
                }
                else
                {
                    normalizedHingeAxis = hingeOverride.Invoke(Vector3.Cross(v1, v2).normalized, normalizedHingeReference);
                }
            }

            return normalizedHingeAxis;
        }

        // Generate a look rotation that looks down the normalized xAxis, the yHint input vector
        // is use to line up the yAxis rotation
        private static Quaternion LookWithXAxisYHint(Vector3 xAxisNormalized, Vector3 yHintNormalized)
        {
            var zAxis = Vector3.Cross(xAxisNormalized, yHintNormalized).normalized;
            return GetRotationFromBasisVectors(xAxisNormalized, yHintNormalized, zAxis);
        }

        // Extract rotation from a set of basis vectors
        private static Quaternion GetRotationFromBasisVectors(Vector3 x, Vector3 y, Vector3 z)
        {
            return new Matrix4x4(x, y, z, new Vector4(0, 0, 0, 1)).rotation;
        }

        private enum FootPlantState
        {
            // The foot is completely unplanted; do not modify the associated joint.
            Unplanted = 0,

            // The foot is completely planted (i.e., the foot planting parameter is >= 1); record the
            // joint's world space pose and fix it to that position.
            Planted,

            // When foot planting is ended (most commonly when the foot planting parameter drops below the transition
            // threshold), we enter this state to smoothly transition between the planted pose and the animated pose
            // for the associated joint.
            EndPlantingTransition,
        }

        // This class contains the data necessary to process and update foot planting for a given foot.
        private class FootPlantData
        {
            // When the foot is planted, it's pose (position and rotation) in world space is recorded here.
            public Vector3 recordedAnklePlantPosition = Vector3.zero;
            public Quaternion recordedAnklePlantRotation = Quaternion.identity;

            public string ankleJointName;

            public FootPlantState state = FootPlantState.Unplanted;
            public float footPlantParameter = 0.0f;
            public float lastFootPlantParameter = 0.0f;

            public float transitionTimer = 0.0f;

            public float positionDeviation = 0.0f;

            public bool allowFootfallCallback = true;

            public FootPlantData(string jointName)
            {
                ankleJointName = jointName;
            }

            public GameObject LastFootPlantVisualization { get; set; } = null;
            public GameObject FootPlantingStatusVisualization { get; set; } = null;
        }

        // This class bundles the left/right foot planting data for an individual entity.
        private class EntityFootPlantData
        {
            public FootPlantData leftFootPlantData = new FootPlantData(OvrAvatarRigConstants.RT_RIG_LEFT_ANKLE);
            public FootPlantData rightFootPlantData = new FootPlantData(OvrAvatarRigConstants.RT_RIG_RIGHT_ANKLE);
        }

        // We store the foot planting data for each entity in a dictionary, using its id as the key.
        private Dictionary<CAPI.ovrAvatar2EntityId, EntityFootPlantData> _footPlantDataDictionary = new Dictionary<ovrAvatar2EntityId, EntityFootPlantData>();

        // This is the duration of the transition, in seconds, that occurs when we need to cancel foot planting.
        private const float _cancelPlantTransitionDuration = 0.1f;

        private const float _footPlantParameterTransitionThreshold = 0.99f;

        // If the distance between the foot planting position and the animated position passes this threshold,
        // we'll automatically trigger the end planting transition, if one isn't already in progress.
        private const float _footPlantMinDeviation = 0.15f;
        private const float _footPlantMinDeviationSquared = _footPlantMinDeviation * _footPlantMinDeviation;

        // If the distance between the foot planting position and the animated position passes this threshold,
        // the foot is getting too far away from the avatar, and we'll immediately break out of foot planting entirely.
        private const float _footPlantMaxDeviation = 0.225f;
        private const float _footPlantMaxDeviationSquared = _footPlantMaxDeviation * _footPlantMaxDeviation;

        // This method returns the active rig from the given PuppeteerInfo. If both rigs are present, it will
        // return the Default Rig unless the BlendFactor is 1, in which case it will return the Humanoid Rig.
        RigInfo GetActiveRig(PuppeteerInfo puppeteerInfo)
        {
            if (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Both)
            {
                if (Mathf.Approximately(1.0f, puppeteerInfo.BlendFactor))
                {
                    return puppeteerInfo.HumanoidRig;
                }
                else
                {
                    return puppeteerInfo.DefaultRig;
                }
            }
            else if (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Humanoid)
            {
                return puppeteerInfo.HumanoidRig;
            }
            else
            {
                return puppeteerInfo.DefaultRig;
            }
        }

        private FootPlantState DetermineFootPlantState(PuppeteerInfo puppeteerInfo, FootPlantData footPlantData, Vector3 rootPosition)
        {
            // Allow the end planting transition to run its course before entering a different state.
            if (footPlantData.state == FootPlantState.EndPlantingTransition)
            {
                if (footPlantData.transitionTimer > 0.0f)
                {
                    // If the transition timer hasn't counted all the way down, we'll allow it to complete.
                    return FootPlantState.EndPlantingTransition;
                }
                else
                {
                    // Otherwise we'll enter the unplanted state to end the transition.
                    return FootPlantState.Unplanted;
                }
            }

            // If the foot plant parameter is less than or equal to 0...
            if (footPlantData.footPlantParameter <= 0.0f)
            {
                // The foot is fully unplanted.
                return FootPlantState.Unplanted;
            }

            // If the deviation between the foot planting position and where the animation wants the foot to be grows too
            // large, we need to break out of foot planting entirely to prevent the avatar's legs from stretching too much.
            if (footPlantData.positionDeviation > _footPlantMaxDeviationSquared)
            {
                return FootPlantState.Unplanted;
            }

            // If the foot plant parameter is greater than or equal to 1...
            if (footPlantData.footPlantParameter >= 1.0f)
            {
                // If the foot was already planted, and the position deviation
                // has gotten too large, we'll start to transition out.
                if (footPlantData.state == FootPlantState.Planted && footPlantData.positionDeviation > _footPlantMinDeviationSquared)
                {
                    // Trigger the transition out of foot planting.
                    footPlantData.transitionTimer = _cancelPlantTransitionDuration;
                    return FootPlantState.EndPlantingTransition;
                }
                else
                {
                    // Report it as planted so we can record its pose and fix it to that position.
                    return FootPlantState.Planted;
                }
            }

            // Otherwise, if the foot plant parameter is between 0 and 1...
            if (footPlantData.state == FootPlantState.Unplanted || footPlantData.state == FootPlantState.EndPlantingTransition)
            {
                // If the foot was already unplanted, we won't plant it until it's fully on the ground.
                return FootPlantState.Unplanted;
            }
            else
            {
                // To prevent jitter with foot planting, we won't start transitioning out of it until
                // the foot plant parameter drops below the _footPlantParameterTransitionThreshold
                if (footPlantData.footPlantParameter >= _footPlantParameterTransitionThreshold &&
                    footPlantData.state == FootPlantState.Planted)
                {
                    return FootPlantState.Planted;
                }

                // Trigger the transition out of foot planting.
                footPlantData.transitionTimer = _cancelPlantTransitionDuration;
                return FootPlantState.EndPlantingTransition;
            }
        }

        private void RecordFootPlantPose(Transform ankleJoint, PuppeteerInfo puppeteerInfo, FootPlantData footPlantData, Vector3 rootPosition, Quaternion rootRotation)
        {
            // Create a matrix for transforming out of the local space of the Avatar's root motion.
            Matrix4x4 rootMatrix = Matrix4x4.TRS(rootPosition, rootRotation, Vector3.one);

            // The position is currently defined in world space relative to the RTRig.
            // We want to save the position in world space relative to the Avatar's root.
            RigInfo rig = GetActiveRig(puppeteerInfo);

            // First, we convert the position into the RTRig's local space.
            Vector3 positionRTRig = rig.Root.worldToLocalMatrix.MultiplyPoint(ankleJoint.position);
            Quaternion rotationRTRig = rig.Root.worldToLocalMatrix.rotation * ankleJoint.rotation;

            // We then convert that position into world space relative to the Avatar's root.
            Vector3 positionRootWorld = rootMatrix.MultiplyPoint(positionRTRig);
            Quaternion rotationRootWorld = rootMatrix.rotation * rotationRTRig;

            // Record the foot plant position
            footPlantData.recordedAnklePlantPosition = positionRootWorld;
            footPlantData.recordedAnklePlantRotation = rotationRootWorld;

            // When foot planting starts, there is no deviation between the foot
            // planting position and where the animation says the foot should be.
            footPlantData.positionDeviation = 0.0f;

            CreateFootPlantPoseDebugVisualization(puppeteerInfo, footPlantData);
        }

        private void UpdateFootPlantAnklePose(Transform ankleJoint, PuppeteerInfo puppeteerInfo, FootPlantData footPlantData, Vector3 rootPosition, Quaternion rootRotation, float interpolant = 0.0f)
        {
            // Create matrices for transforming into and out of the local space of the Avatar's root motion.
            Matrix4x4 rootMatrix = Matrix4x4.TRS(rootPosition, rootRotation, Vector3.one);
            Matrix4x4 rootMatrixInv = rootMatrix.inverse;

            // The footPlantPosition is saved in world space relative to the Avatar's root so that
            // it will stay in the same position as the Avatar moves. However, we need the position
            // in world space relative to the RTRig before it can be piped into the AppPoseNode.

            // Convert the foot plant position into the Avatar root's local space
            Vector3 pointRootLocal = rootMatrixInv.MultiplyPoint(footPlantData.recordedAnklePlantPosition);
            Quaternion rotationRootLocal = rootMatrixInv.rotation * footPlantData.recordedAnklePlantRotation;

            RigInfo rig = GetActiveRig(puppeteerInfo);

            // Convert it into world space relative to the RT Rig
            Vector3 pointRTRigWorld = rig.Root.localToWorldMatrix.MultiplyPoint(pointRootLocal);
            Quaternion rotationRTRigWorld = rig.Root.localToWorldMatrix.rotation * rotationRootLocal;

            // If an interpolant value is specified, we'll use it to blend between the recorded foot plant
            // position and the current position of the ankle joint in the animation. This allows us to
            // smoothly transition out of foot planting.
            if (interpolant > 0.0f)
            {
                pointRTRigWorld = Vector3.Lerp(ankleJoint.position, pointRTRigWorld, interpolant);
                rotationRTRigWorld = Quaternion.Slerp(ankleJoint.rotation, rotationRTRigWorld, interpolant);
            }

            // Record how far away the foot planting position is from the position the animation wants the
            // foot to be in. If the deviation becomes too large, we'll either need to speed up transitioning
            // out of foot planting, or terminate it all together.
            footPlantData.positionDeviation = (pointRTRigWorld - ankleJoint.position).sqrMagnitude;

            // If the deviation has gone above the maximum threshold, we'll
            // immediately reject it and retain the animated position.
            if (footPlantData.positionDeviation > _footPlantMaxDeviationSquared)
            {
                return;
            }

            // Apply the position to the joint.
            ankleJoint.position = pointRTRigWorld;
            ankleJoint.rotation = rotationRTRigWorld;
        }

        private void UpdateFootPlantEndTransition(Transform ankleJoint, PuppeteerInfo puppeteerInfo, FootPlantData footPlantData, Vector3 rootPosition, Quaternion rootRotation, FootPlantState lastState)
        {
            if (footPlantData.transitionTimer < 0.0f)
            {
                return;
            }

            // If debug visualizations are enabled and we've just entered the end planting
            // transition,  we'll color them appropriately to show that they're in transition.
            if (_enableFootPlantingDebugVisualizations && lastState != FootPlantState.EndPlantingTransition)
            {
                if (footPlantData.positionDeviation > _footPlantMinDeviationSquared)
                {
                    // If we triggered the transition because the position deviation passed the minimum
                    // threshold, we'll color the visualization cyan to reflect what's going on.
                    UpdateDebugVisualizationObjectColor(footPlantData.LastFootPlantVisualization, Color.cyan);
                }
                else
                {
                    // Otherwise, we'll color the visualization yellow to show that a normal transition is in progress.
                    UpdateDebugVisualizationObjectColor(footPlantData.LastFootPlantVisualization, Color.yellow);
                }
            }

            // Calculate transition progress. This value starts at 1 and progresses towards 0.
            float transitionProgress = footPlantData.transitionTimer / _cancelPlantTransitionDuration;

            UpdateFootPlantAnklePose(ankleJoint, puppeteerInfo, footPlantData, rootPosition, rootRotation, transitionProgress);

            // Decrement the timer.
            footPlantData.transitionTimer -= Time.deltaTime;
        }

        private void CreateFootPlantPoseDebugVisualization(PuppeteerInfo puppeteerInfo, FootPlantData footPlantData)
        {
            if (!_enableFootPlantingDebugVisualizations)
            {
                return;
            }

            if (FootPlantVisualizationContainer == null)
            {
                FootPlantVisualizationContainer = new GameObject("FootPlantVisualizationContainer");
            }

            DeactivateFootPlantVisualization(footPlantData);

            GameObject footPlantingRepresentation = GameObject.CreatePrimitive(PrimitiveType.Cube);
            footPlantingRepresentation.name = $"FootPlantPosition{Time.time}";

            puppeteerInfo.GetEntityPose(out var entityPosition, out var entityRotation);

            footPlantingRepresentation.transform.position = entityPosition + footPlantData.recordedAnklePlantPosition;
            footPlantingRepresentation.transform.rotation = entityRotation * footPlantData.recordedAnklePlantRotation;
            footPlantingRepresentation.transform.localScale = new Vector3(0.2f, 0.1f, 0.05f);
            footPlantingRepresentation.transform.parent = FootPlantVisualizationContainer.transform;

            footPlantData.LastFootPlantVisualization = footPlantingRepresentation;
            UpdateDebugVisualizationObjectColor(footPlantingRepresentation, Color.green);
        }

        private void UpdateDebugVisualizationObjectColor(GameObject debugVisualizationObject, Color visualizationColor)
        {
            if (debugVisualizationObject == null)
            {
                return;
            }

            Renderer renderer = debugVisualizationObject.GetComponent<Renderer>();
            renderer.material.SetColor("_Color", visualizationColor);
        }

        private void DeactivateFootPlantVisualization(FootPlantData footPlantData)
        {
            if (footPlantData.LastFootPlantVisualization == null)
            {
                return;
            }

            Color visualizationColor = Color.red;

            // If foot planting was canceled because the position deviation exceeded the max threshold,
            // we'll color the foot planting visualization magenta to highlight what happened.
            if (footPlantData.positionDeviation > _footPlantMaxDeviationSquared)
            {
                visualizationColor = Color.magenta;
            }

            UpdateDebugVisualizationObjectColor(footPlantData.LastFootPlantVisualization, visualizationColor);

            // If the duration is less than zero, we won't automatically destroy the visualization.
            if (_footPlantingLocationVisualizationDuration >= 0.0f)
            {
                Destroy(footPlantData.LastFootPlantVisualization, _footPlantingLocationVisualizationDuration);
            }

            footPlantData.LastFootPlantVisualization = null;
        }

        private void UpdateFootPlantStatusRenameVisualizationForSide(bool isLeftSide, FootPlantData footPlantData)
        {
            if (footPlantData.FootPlantingStatusVisualization == null)
            {
                footPlantData.FootPlantingStatusVisualization = GameObject.CreatePrimitive(PrimitiveType.Sphere);

                footPlantData.FootPlantingStatusVisualization.transform.parent = FootPlantStatusVisualizationContainer.transform;
                footPlantData.FootPlantingStatusVisualization.transform.localScale = new Vector3(0.2f, 0.2f, 0.2f);

                if (isLeftSide)
                {
                    // Left
                    footPlantData.FootPlantingStatusVisualization.name = "LeftFootPlantStatus";
                    footPlantData.FootPlantingStatusVisualization.transform.localPosition = new Vector3(-0.5f, 1.5f, 0.0f);
                }
                else
                {
                    // Right
                    footPlantData.FootPlantingStatusVisualization.name = "RightFootPlantStatus";
                    footPlantData.FootPlantingStatusVisualization.transform.localPosition = new Vector3(0.5f, 1.5f, 0.0f);
                }
            }

            switch (footPlantData.state)
            {
                case FootPlantState.Unplanted:
                    UpdateDebugVisualizationObjectColor(footPlantData.FootPlantingStatusVisualization, Color.red);
                    break;
                case FootPlantState.Planted:
                    UpdateDebugVisualizationObjectColor(footPlantData.FootPlantingStatusVisualization, Color.green);
                    break;
                case FootPlantState.EndPlantingTransition:
                    UpdateDebugVisualizationObjectColor(footPlantData.FootPlantingStatusVisualization, Color.yellow);
                    break;
            }
        }

        private void UpdateFootPlantStatusDebugVisualization(PuppeteerInfo puppeteerInfo, FootPlantData leftFootPlantData, FootPlantData rightFootPlantData)
        {
            if (!_enableFootPlantingDebugVisualizations)
            {
                if (leftFootPlantData.FootPlantingStatusVisualization != null)
                {
                    Destroy(leftFootPlantData.FootPlantingStatusVisualization);
                }

                if (rightFootPlantData.FootPlantingStatusVisualization != null)
                {
                    Destroy(rightFootPlantData.FootPlantingStatusVisualization);
                }

                if (FootPlantStatusVisualizationContainer != null)
                {
                    Destroy(FootPlantStatusVisualizationContainer);
                }

                return;
            }

            if (FootPlantStatusVisualizationContainer == null)
            {
                FootPlantStatusVisualizationContainer = new GameObject("FootPlantStatusVisualizationContainer");
            }

            puppeteerInfo.GetRootPose(out var rootPosition, out var rootRotation);
            puppeteerInfo.GetEntityPose(out var entityPosition, out var entityRotation);

            FootPlantStatusVisualizationContainer.transform.position = entityPosition + rootPosition;
            FootPlantStatusVisualizationContainer.transform.rotation = entityRotation * rootRotation;

            UpdateFootPlantStatusRenameVisualizationForSide(true, leftFootPlantData);
            UpdateFootPlantStatusRenameVisualizationForSide(false, rightFootPlantData);
        }

        private EntityFootPlantData GetFootPlantData(PuppeteerInfo puppeteerInfo)
        {
            // If the entity callback is not defined, we won't be able to perform foot planting for this avatar.
            if (puppeteerInfo.GetEntityCallback == null)
            {
                OvrAvatarLog.LogInfo("GetEntityCallback not defined in PuppeteerInfo, unable to perform foot planting for avatar.");
                return null;
            }

            // If for some reason the entity callback isn't able to provide the entity,
            // we won't be able to perform footr planting for this avatar.
            OvrAvatarEntity entity = puppeteerInfo.GetEntityCallback();
            if (entity == null)
            {
                OvrAvatarLog.LogInfo("GetEntityCallback returned null; unable to perform foot planting for avatar.");
                return null;
            }

            // If the foot plant data already exists for this entity, return it now.
            if (_footPlantDataDictionary.TryGetValue(entity.internalEntityId, out var footPlantData))
            {
                return footPlantData;
            }

            // Otherwise we'll create foot plant data, and store it in the dictionary using the entity's id as the key.
            EntityFootPlantData newFootPlantData = new EntityFootPlantData();
            _footPlantDataDictionary[entity.internalEntityId] = newFootPlantData;

            return newFootPlantData;
        }

        private void PollFootPlantingParameters(PuppeteerInfo puppeteerInfo, EntityFootPlantData footPlantData)
        {
            // Save the old parameter values.
            footPlantData.leftFootPlantData.lastFootPlantParameter = footPlantData.leftFootPlantData.footPlantParameter;
            footPlantData.rightFootPlantData.lastFootPlantParameter = footPlantData.rightFootPlantData.footPlantParameter;

            // Poll the new parameter values.
            puppeteerInfo.GetFootPlantStatus(out footPlantData.leftFootPlantData.footPlantParameter, out footPlantData.rightFootPlantData.footPlantParameter);
        }

        private void UpdateFootPlanting(FootPlantData footPlantData, PuppeteerInfo puppeteerInfo)
        {
            // Ensure that we're able to get the Transform for the ankle joint.
            Transform ankleJoint;
            if (!GetActiveRig(puppeteerInfo).RigMap.TryGetValue(footPlantData.ankleJointName, out ankleJoint))
            {
                // Could not find the ankle joint for the foot; abort.
                OvrAvatarLog.LogWarning($"Could not find joint {footPlantData.ankleJointName} for foot planting");
                return;
            }

            // Poll the current root motion position and rotation.
            // TODO: we need to apply the root motion directly to the avatar's entity so we can instead reference that.
            puppeteerInfo.GetRootPose(out var rootPosition, out var rootRotation);

            FootPlantState oldState = footPlantData.state;

            // Determine the current foot plant state.
            footPlantData.state = DetermineFootPlantState(puppeteerInfo, footPlantData, rootPosition);

            // If the foot is unplanted, we don't need to do anything and we can back out here.
            if (footPlantData.state == FootPlantState.Unplanted)
            {
                if (oldState != FootPlantState.Unplanted)
                {
                    DeactivateFootPlantVisualization(footPlantData);
                    footPlantData.positionDeviation = 0.0f;
                }
                return;
            }

            // Process the foot plant state.
            switch (footPlantData.state)
            {
                case FootPlantState.Planted:
                    if (oldState != FootPlantState.Planted)
                    {
                        // If the foot is newly-planted, we need to record the ankle's current world space pose.
                        RecordFootPlantPose(ankleJoint, puppeteerInfo, footPlantData, rootPosition, rootRotation);
                    }
                    else
                    {
                        // If the foot is planted, fix the ankle joint to the recorded world space pose.
                        UpdateFootPlantAnklePose(ankleJoint, puppeteerInfo, footPlantData, rootPosition, rootRotation);
                    }

                    break;

                case FootPlantState.EndPlantingTransition:
                    // If we need to cancel out of foot planting, we'll use an interpolant based on a timer to
                    // smoothly blend out of the planted position.
                    UpdateFootPlantEndTransition(ankleJoint, puppeteerInfo, footPlantData, rootPosition, rootRotation, oldState);
                    break;

                default:
                    OvrAvatarLog.LogWarning($"Unhandled foot plant state: {footPlantData.state}");
                    break;
            }
        }

        private void CheckForFootFall(FootPlantData footPlantData, PuppeteerInfo puppeteerInfo, Side side)
        {
            if (footPlantData.allowFootfallCallback && footPlantData.footPlantParameter >= 1.0f && footPlantData.lastFootPlantParameter < 1.0f)
            {
                if (puppeteerInfo.GetEntityCallback == null)
                {
                    OvrAvatarLog.LogWarning("PuppeteerInfo.GetEntityCallback not set, unable to invoke OnAvatarFootFall event");
                    return;
                }

                // Provide the entity, so observers of the event will know which avatar is making the step.
                OnAvatarFootFall.Invoke(puppeteerInfo.GetEntityCallback(), side);
                footPlantData.allowFootfallCallback = false;
            }
            else if (footPlantData.footPlantParameter < 0.9f)
            {
                // We'll prevent the footfall callback from being made until after the
                // foot is lifted up past a certain threshold to prevent noise.
                footPlantData.allowFootfallCallback = true;
            }
        }

        private void UpdateFeet(PuppeteerInfo puppeteerInfo)
        {
            // Get the foot planting data for the entity.
            EntityFootPlantData footPlantData = GetFootPlantData(puppeteerInfo);

            // If for some reason we're not able to get the foot planting data for the entity
            if (footPlantData == null)
            {
                return;
            }


            // Get the foot plant status for each foot.
            PollFootPlantingParameters(puppeteerInfo, footPlantData);

            // Update foot planting for the left ankle
            UpdateFootPlanting(footPlantData.leftFootPlantData, puppeteerInfo);

            // Update foot planting for the right ankle
            UpdateFootPlanting(footPlantData.rightFootPlantData, puppeteerInfo);

            UpdateFootPlantStatusDebugVisualization(puppeteerInfo, footPlantData.leftFootPlantData, footPlantData.rightFootPlantData);

            // Determine if we need to need to make the footfall callback for the left foot.
            CheckForFootFall(footPlantData.leftFootPlantData, puppeteerInfo, Side.Left);

            // Determine if we need to need to make the footfall callback for the right foot.
            CheckForFootFall(footPlantData.rightFootPlantData, puppeteerInfo, Side.Right);
        }

        private void UpdateUpperBodyRotation(PuppeteerInfo puppeteerInfo)
        {
            if (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Default ||
                (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Both && Mathf.Approximately(puppeteerInfo.BlendFactor, 0)))
            {
                UpdateUpperBodyRotationWithRigInfo(puppeteerInfo.DefaultRig, puppeteerInfo.UpperBodyRotationFactors);
            }
            else if (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Humanoid ||
                (puppeteerInfo.PuppeteerRigType == PuppeteerInfo.RigType.Both && Mathf.Approximately(puppeteerInfo.BlendFactor, 1)))
            {
                UpdateUpperBodyRotationWithRigInfo(puppeteerInfo.HumanoidRig, puppeteerInfo.UpperBodyRotationFactors);
            }
            else
            {
                UpdateUpperBodyRotationWithRigInfo(puppeteerInfo.DefaultRig, puppeteerInfo.UpperBodyRotationFactors);
                UpdateUpperBodyRotationWithRigInfo(puppeteerInfo.HumanoidRig, puppeteerInfo.UpperBodyRotationFactors);
            }
        }

        private const float _maxUpperBodyRotationAngle = 60.0f;
        public float MaxUpperBodyRotationAngle
        {
            get { return _maxUpperBodyRotationAngle; }
        }

        private const float _chestRotationFactor = 0.33f;

        private void UpdateUpperBodyRotationWithRigInfo(RigInfo info, Vector3 upperBodyRotationFactors)
        {
            if (!info.RigMap.TryGetValue(OvrAvatarRigConstants.RT_RIG_CHEST, out Transform chestJoint))
            {
                // Could not find the chest joint for the rig; abort.
                OvrAvatarLog.LogWarning($"Could not find joint {OvrAvatarRigConstants.RT_RIG_CHEST} for applying upper body rotation");
                return;
            }

            if (!info.RigMap.TryGetValue(OvrAvatarRigConstants.RT_RIG_NECK, out Transform neckJoint))
            {
                // Could not find the neck joint for the rig; abort.
                OvrAvatarLog.LogWarning($"Could not find joint {OvrAvatarRigConstants.RT_RIG_NECK} for applying upper body rotation");
                return;
            }

            float totalXAxisRotationAngle = upperBodyRotationFactors.x * _maxUpperBodyRotationAngle; // X-axis rotation (lean forwards and back)
            float totalYAxisRotationAngle = upperBodyRotationFactors.y * _maxUpperBodyRotationAngle; // Y-axis rotation (horizontal rotation)
            float totalZAxisRotationAngle = upperBodyRotationFactors.z * _maxUpperBodyRotationAngle; // Z-axis rotation (lean side-to-side)

            // Most of the upper body rotation is done through the neck; about 1/3rd goes through the chest joint
            float chestXAxisRotationAngle = totalXAxisRotationAngle * _chestRotationFactor;
            float neckXAxisRotationAngle = totalXAxisRotationAngle - chestXAxisRotationAngle;

            float chestYAxisRotationAngle = totalYAxisRotationAngle * _chestRotationFactor;
            float neckYAxisRotationAngle = totalYAxisRotationAngle - chestYAxisRotationAngle;

            float chestZAxisRotationAngle = totalZAxisRotationAngle * _chestRotationFactor;
            float neckZAxisRotationAngle = totalZAxisRotationAngle - chestZAxisRotationAngle;

            // We need to apply the rotations for the chest and neck joints in their local spaces:
            // chest/neck forward = (0, 0, -1)
            // chest/neck right = (0, -1, 0)
            // check/neck up = (-1, 0, 0)
            Quaternion chestRot = Quaternion.AngleAxis(chestYAxisRotationAngle, -Vector3.right) * Quaternion.AngleAxis(chestXAxisRotationAngle, -Vector3.up) * Quaternion.AngleAxis(chestZAxisRotationAngle, -Vector3.forward);
            Quaternion neckRot = Quaternion.AngleAxis(neckYAxisRotationAngle, -Vector3.right) * Quaternion.AngleAxis(neckXAxisRotationAngle, -Vector3.up) * Quaternion.AngleAxis(neckZAxisRotationAngle, -Vector3.forward);

            chestJoint.localRotation = chestRot * chestJoint.localRotation;
            neckJoint.localRotation = neckRot * neckJoint.localRotation;
        }

        // Information for an animation rig
        public class RigInfo
        {
            // Root of the puppeteer rig
            public Transform Root { get; set; }
            public RigVersion Version { get; set; } = RigVersion.V3;

            // Joints mapping of the puppeteer rig
            public Dictionary<string, Transform> RigMap { get; set; }
            public List<BoneTransformInfo> BoneTransformInfoList;
            public List<(string, int)> DataChannelArray;

            public static readonly Dictionary<string, CriticalJointIndex> CriticalJointNames = new Dictionary<string, CriticalJointIndex>
            {
                { OvrAvatarRigConstants.RT_RIG_LEFT_HIP, CriticalJointIndex.LeftHip },
                { OvrAvatarRigConstants.RT_RIG_RIGHT_HIP, CriticalJointIndex.RightHip },
                { OvrAvatarRigConstants.RT_RIG_LEFT_ANKLE, CriticalJointIndex.LeftAnkle },
                { OvrAvatarRigConstants.RT_RIG_RIGHT_ANKLE, CriticalJointIndex.RightAnkle },
                { OvrAvatarRigConstants.RT_RIG_LEFT_SHOULDER, CriticalJointIndex.LeftShoulder },
                { OvrAvatarRigConstants.RT_RIG_RIGHT_SHOULDER, CriticalJointIndex.RightShoulder },
                { OvrAvatarRigConstants.RT_RIG_LEFT_WRIST, CriticalJointIndex.LeftWrist },
                { OvrAvatarRigConstants.RT_RIG_RIGHT_WRIST, CriticalJointIndex.RightWrist },
                { OvrAvatarRigConstants.RT_RIG_LEFT_KNEE, CriticalJointIndex.LeftKnee },
                { OvrAvatarRigConstants.RT_RIG_RIGHT_KNEE, CriticalJointIndex.RightKnee },
                { OvrAvatarRigConstants.RT_RIG_LEFT_ELBOW, CriticalJointIndex.LeftElbow },
                { OvrAvatarRigConstants.RT_RIG_RIGHT_ELBOW, CriticalJointIndex.RightElbow },
            };

            public BoneTransformInfo[] JointIndexArray = new BoneTransformInfo[CriticalJointNames.Count];

            public enum CriticalJointIndex
            {
                LeftHip = 0,
                RightHip = 1,
                LeftAnkle = 2,
                RightAnkle = 3,
                LeftShoulder = 4,
                RightShoulder = 5,
                LeftWrist = 6,
                RightWrist = 7,
                LeftKnee = 8, // does not exist in default rig
                RightKnee = 9, // does not exist in default rig
                LeftElbow = 10, // does not exist in default rig
                RightElbow = 11, // does not exist in default rig
            }
        }

        public class BoneTransformInfo
        {
            public int BoneIndex = -1;
            public Transform BoneTransform;
            public Matrix4x4? ConversionMatrix;
        }

        // Class that encapsulates puppeteer information
        public class PuppeteerInfo
        {
            public enum RigType
            {
                Default,
                Humanoid,
                Both
            }

            public float BlendFactor { get; set; } = 0;
            public Vector3 UpperBodyRotationFactors { get; set; } = Vector3.zero;
            public bool EnableFootPlantingDebugVisualizations { get; set; } = false;
            public RigInfo DefaultRig { get; }
            public RigInfo HumanoidRig { get; }
            public RigType PuppeteerRigType { get; }
            public bool IsInputBlended { get; set; }
            public bool HeadsetAnchoring { get; set; }
            public bool EnableOneToOneHandTracking { get; set; }
            public bool EnableStaticAnimationOptimization { get; set; }

            public PuppeteerInfo(RigInfo defaultRig, RigInfo humanoidRig, float blendFactor = 0)
            {
                if (defaultRig == null && humanoidRig == null)
                {
                    OvrAvatarLog.LogError("Default rig and humanoid Rig cannot both be null");
                }

                DefaultRig = defaultRig;
                HumanoidRig = humanoidRig;
                BlendFactor = blendFactor;
                if (defaultRig != null)
                {
                    if (humanoidRig != null)
                    {
                        PuppeteerRigType = RigType.Both;
                    }
                    else
                    {
                        PuppeteerRigType = RigType.Default;
                    }
                }
                else
                {
                    PuppeteerRigType = RigType.Humanoid;
                }
            }

            public delegate void PoseDelegate(out Vector3 position, out Quaternion rotation);

            // Delegate method for getting the current root position and rotation
            public PoseDelegate GetRootPose { get; set; }

            public PoseDelegate GetEntityPose { get; set; }

            public delegate void FootPlantStatus(out float leftFootPlanted, out float rightFootPlanted);

            // Delegate method for getting the foot plant status for the left & right feet
            public FootPlantStatus GetFootPlantStatus { get; set; }

            public delegate bool IsControllerInStateTransitionDelegate(int layerIndex);

            public IsControllerInStateTransitionDelegate GetIsControllerInStateTransition { get; set; }

            // Delegate method for retrieving the entity associated with the PuppeteerInfo
            public delegate OvrAvatarEntity EntityDelegate();

            public EntityDelegate GetEntityCallback { get; set; }

            public delegate bool DataChannelValueDelegate(RigType rigType, string dataChannelName, out float value);
            public DataChannelValueDelegate TryGetDataChannelValue { get; set; }

            public delegate HashSet<string> DataChannelDelegate(RigType rigType);
            public DataChannelDelegate GetAvaiableDataChannels { get; set; }

            public delegate bool CheckAnimationDelegate(RigType rigType);
            public CheckAnimationDelegate CheckIsAnimating { get; set; }

            /**
             * Delegate for hinge correction override

             * @see OvrAvatarAnimation.OvrAvatarAnimation.HingeCorrectionOverride
             */
            public OvrAvatarAnimation.HingeCorrectionOverride HingeCorrectOverride { get; set; }
            public bool DidInitializeBoneTransformIndexes()
            {
                return DefaultRig?.BoneTransformInfoList != null || HumanoidRig?.BoneTransformInfoList != null;
            }

            public List<(string, int)> GetDataChannelArray(RigType type)
            {
                if (type == RigType.Both)
                {
                    OvrAvatarLog.LogError("Attempting to get data channel for mixed type");
                }

                if (type == RigType.Default)
                {
                    return DefaultRig?.DataChannelArray;
                }
                else if (type == RigType.Humanoid)
                {
                    return HumanoidRig?.DataChannelArray;
                }

                OvrAvatarLog.LogAssert("Cannot get data channel array for mixed rig type");
                return null;
            }

            public void SetDataChannelArray(RigType type, List<(string, int)> dataChannelArray)
            {
                if (type == RigType.Both)
                {
                    OvrAvatarLog.LogError("Attempting to set data channel for mixed type");
                }

                if (PuppeteerRigType != type && PuppeteerRigType != RigType.Both)
                {
                    OvrAvatarLog.LogError($"Attempting to set data channel for wrong rig type. entity rig type: {PuppeteerRigType}, attempted type: {type}");
                }

                if (type == RigType.Default)
                {
                    DefaultRig.DataChannelArray = dataChannelArray;
                }
                else if (type == RigType.Humanoid)
                {
                    HumanoidRig.DataChannelArray = dataChannelArray;
                }
            }
        }

        public struct AlignJointResults
        {
            public JointInfo StartJointInfo;
            public JointInfo EndJointInfo;
        }

        public struct JointInfo
        {
            public int Index;
            public CAPI.ovrAvatar2Transform Transform;
        }

        public enum Side
        {
            Left,
            Right
        }

        private sealed class CachedEntityInfo : IDisposable
        {
            public BehaviorPose Pose;
            public int LastUpdatedFrame = Time.frameCount;

            public CachedEntityInfo(BehaviorPose pose)
            {
                Pose = new BehaviorPose(pose);
                LastUpdatedFrame = Time.frameCount;
            }

            public void Dispose()
            {
                Pose.Dispose();
                Pose = null;
            }
        }

        [Serializable]
        public class AvatarFootFallEvent : UnityEvent<OvrAvatarEntity, Side> { }
    }

    public static class OvrAvatarAnimation
    {
        /**
         * Delegate callback for hinge vector correction. The hinge vector is the vector in the direction of the hinge
         * axis for knees and elbows. There are two cases in which the hinge vector needs to be corrected, using legs as example:
         *
         * 1. If the hip/knee/ankle form a straight line, the hinge vector is undefined. The default correction for this case is to use
         * the referenceVector as the hinge vector
         *
         * 2. If the hip/knee/ankle bend backwards, this would cause the calculated hinge vector to flip 180 degrees. The default
         * correction in this case is to flip the hinge axis.
         *
         * Sometime these corrections can cause problems with direct rig manipulation, this delegate allows custom correction logic to
         * turn off or change the default correction behavior

         *
         * @param referenceTransform The transform on the humanoid rig that is being referenced. This can be elbow/knee
         * @param hingeVector        The calculated hinge vector. This value would be Vector3.Zero if joints form a straight line
         * @param referenceVector    The reference vector used for hinge correction. This value correlates to the up vector of the reference transform
         */
        public delegate Vector3 HingeCorrectionOverride(Transform referenceTransform, Vector3 hingeVector, Vector3 referenceVector);
    }
}
