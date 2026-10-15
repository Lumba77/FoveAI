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
using System.Diagnostics.Contracts;
using UnityEngine;
using UnityEngine.XR;
using System.IO;
using UnityEngine.SceneManagement;

#if UNITY_EDITOR
using UnityEditor;
#endif

namespace Oculus.Avatar2
{
    public static class OvrAvatarUtility
    {
        public static CAPI.ovrAvatar2Transform CombineOvrTransforms(
            in CAPI.ovrAvatar2Transform parent, in CAPI.ovrAvatar2Transform child)
        {
            var scaledChildPose = new CAPI.ovrAvatar2Vector3f
            {
                x = child.position.x * parent.scale.x,
                y = child.position.y * parent.scale.y,
                z = child.position.z * parent.scale.z
            };

            var parentQuat = (Quaternion)parent.orientation;
            var result = new CAPI.ovrAvatar2Transform
            {
                position =
                  parent.position + (CAPI.ovrAvatar2Vector3f)(parentQuat * scaledChildPose),

                orientation = parentQuat * child.orientation,

                scale = new CAPI.ovrAvatar2Vector3f
                {
                    x = parent.scale.x * child.scale.x,
                    y = parent.scale.y * child.scale.y,
                    z = parent.scale.z * child.scale.z
                }
            };
            OvrAvatarLog.Assert(!result.position.IsNaN());
            OvrAvatarLog.Assert(!result.orientation.IsNaN());
            OvrAvatarLog.Assert(!result.scale.IsNaN());

            OvrAvatarLog.Assert(result.orientation.IsNormalized());

            return result;
        }

        [Pure]
        public static CAPI.ovrAvatar2Vector3f TransformPoint(this CAPI.ovrAvatar2Transform parent, in CAPI.ovrAvatar2Vector3f point)
        {
            Vector3 scale = new Vector3(
                parent.scale.x * point.x,
                parent.scale.y * point.y,
                parent.scale.z * point.z
            );
            CAPI.ovrAvatar2Vector3f result = (parent.orientation * scale) + parent.position;
            return result;
        }

        [Pure]
        public static string GetAsString(this in CAPI.ovrAvatar2Transform transform, int decimalPlaces = 2)
        {
            string format = "F" + decimalPlaces;
            return $"{((Vector3)transform.position).ToString(format)}, {((Quaternion)transform.orientation).eulerAngles.ToString(format)}, {((Vector3)transform.scale).ToString(format)}";
        }

        [Pure]
        public static bool IsNaN(this in CAPI.ovrAvatar2Vector3f v)
        {
            return float.IsNaN(v.x) || float.IsNaN(v.y) || float.IsNaN(v.z);
        }

        [Pure]
        public static bool IsNaN(this in CAPI.ovrAvatar2Quatf q)
        {
            return float.IsNaN(q.x) || float.IsNaN(q.y) || float.IsNaN(q.z) || float.IsNaN(q.w);
        }

        [Pure]
        public static bool IsNan(this in CAPI.ovrAvatar2Transform t)
        {
            return t.position.IsNaN() || t.orientation.IsNaN() || t.scale.IsNaN();
        }

        [Pure]
        public static bool IsZero(this in CAPI.ovrAvatar2Vector3f vec)
            => vec.x == 0.0f && vec.y == 0.0f && vec.z == 0.0f;

        [Pure]
        public static bool IsOne(this in CAPI.ovrAvatar2Vector3f vec)
            => vec.x == 1.0f && vec.y == 1.0f && vec.z == 1.0f;

        [Pure]
        public static bool IsIdentity(this in CAPI.ovrAvatar2Quatf quat)
            => quat.x == 0.0f && quat.y == 0.0f && quat.z == 0.0f && (quat.w == 1.0f || quat.w == -1.0f);

        [Pure]
        public static bool IsNormalized(this in CAPI.ovrAvatar2Quatf quat)
            => Mathf.Approximately(quat.LengthSquared, 1.0f);


        [Pure]
        public static bool IsNormalized(this in CAPI.ovrAvatar2Quatf quat, float tolerance)
        {
            return Mathf.Abs(quat.LengthSquared - 1.0f) < tolerance;
        }

        [Pure]
        public static bool IsValid(this in CAPI.ovrAvatar2Vector3f v)
        {
            return !v.IsNaN();
        }

        [Pure]
        public static bool IsValid(this in CAPI.ovrAvatar2Quatf q, float tolerance)
        {
            return !q.IsNaN() && q.IsNormalized(tolerance);
        }

        [Pure]
        public static bool IsUniform(this in CAPI.ovrAvatar2Vector3f v)
            => Mathf.Approximately(v.x, v.y) && Mathf.Approximately(v.x, v.z);

        [Pure]
        public static bool IsUniform(this in CAPI.ovrAvatar2Vector3f v, float tolerance = 0.0f)
        {
            return Mathf.Abs(v.x - v.y) <= tolerance && Math.Abs(v.x - v.z) <= tolerance;
        }

        [Pure]
        public static bool IsValid(this in CAPI.ovrAvatar2Transform t, float tolerance = 0.0f)
        {
            return t.position.IsValid() && t.orientation.IsValid(tolerance) && t.scale.IsValid() && t.scale.IsUniform(tolerance) && !t.scale.IsZero();
        }

        [Pure]
        public static bool IsIdentity(this in CAPI.ovrAvatar2Transform transform)
            => transform.position.IsZero() && transform.orientation.IsIdentity() && transform.scale.IsOne();

        public static Matrix4x4 ToUnityMatrix(this in CAPI.ovrAvatar2Matrix4f m)
        {
            m.CopyToUnityMatrix(out var unityM);
            return unityM;
        }

        public static CAPI.ovrAvatar2Matrix4f ToAvatarMatrix(this in Matrix4x4 m)
        {
            m.CopyToAvatarMatrix(out var avatarMat);
            return avatarMat;
        }

        public static void CopyToUnityMatrix(this in CAPI.ovrAvatar2Matrix4f m, out Matrix4x4 unityMatrix)
        {
            unityMatrix.m00 = m.m00;
            unityMatrix.m10 = m.m10;
            unityMatrix.m20 = m.m20;
            unityMatrix.m30 = m.m30;
            unityMatrix.m01 = m.m01;
            unityMatrix.m11 = m.m11;
            unityMatrix.m21 = m.m21;
            unityMatrix.m31 = m.m31;
            unityMatrix.m02 = m.m02;
            unityMatrix.m12 = m.m12;
            unityMatrix.m22 = m.m22;
            unityMatrix.m32 = m.m32;
            unityMatrix.m03 = m.m03;
            unityMatrix.m13 = m.m13;
            unityMatrix.m23 = m.m23;
            unityMatrix.m33 = m.m33;
        }

        public static void CopyToAvatarMatrix(this in Matrix4x4 unityMatrix, out CAPI.ovrAvatar2Matrix4f m)
        {
            m.m00 = unityMatrix.m00;
            m.m10 = unityMatrix.m10;
            m.m20 = unityMatrix.m20;
            m.m30 = unityMatrix.m30;
            m.m01 = unityMatrix.m01;
            m.m11 = unityMatrix.m11;
            m.m21 = unityMatrix.m21;
            m.m31 = unityMatrix.m31;
            m.m02 = unityMatrix.m02;
            m.m12 = unityMatrix.m12;
            m.m22 = unityMatrix.m22;
            m.m32 = unityMatrix.m32;
            m.m03 = unityMatrix.m03;
            m.m13 = unityMatrix.m13;
            m.m23 = unityMatrix.m23;
            m.m33 = unityMatrix.m33;
        }

        // Check if a XR device is connected.
        // This helps detect UnityEditor running on Link.
        public static bool IsHeadsetActive()
        {
            return XRSettings.enabled && XRSettings.isDeviceActive;
        }

        // Check if a single bit resides within a flags bitmap
        public static bool IsSingleEnumInFlags(Int32 singleEnum, Int32 flags)
        {
            return (singleEnum & flags) == singleEnum;
        }

        // Find lowest active bit flag
        public static Int32 GetLowestEnumValue(Int32 enumflags)
        {
            if (enumflags == 0)
            {
                return 0;
            }

            Int32 minBitValue = 1;
            while (!IsSingleEnumInFlags(minBitValue, enumflags))
            {
                minBitValue = minBitValue << 1;
            }

            return minBitValue;
        }

        // Determine if a scene is an environment from its path
        public static bool IsScenePathAnEnvironment(string scenePath)
        {
            scenePath = scenePath.Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar);
            return scenePath.Contains(Path.DirectorySeparatorChar + "Environments" + Path.DirectorySeparatorChar);
        }

        public static bool IsSceneAnEnvironment(Scene scene)
        {
            return IsScenePathAnEnvironment(scene.path);
        }

        // Get the path for going up "n" levels from a given path
        public static string UpNLevel(string path, int n)
        {
            while (true)
            {
                if (n <= 0)
                {
                    return path;
                }

                var lastIndex = path.LastIndexOfAny(new[] { '/', '\\' });
                if (lastIndex == -1)
                {
                    return path;
                }

                path = path[..lastIndex];
                n -= 1;
            }
        }
    }

#if UNITY_EDITOR
    /// <summary>
    /// The EnumFlagsValidator class is designed to facilitate the validation of edits made to enum values, which are
    /// internally represented as bit fields. It ensures the maintenance of consistency between an active set (either single or multiple values)
    /// and a valid set of values field. In the event of any inconsistency between these sets, the validator initiates an attempt to rectify the discrepancy.
    /// </summary>
    public class EnumFlagsValidator<TEnumType> where TEnumType : Enum
    {
        private TEnumType _lastActiveFlagsT;
        private TEnumType _lastValidBitsFieldT;
        private bool _Inited = false;

        private static Int32 EnumToInt32(TEnumType value) => (Int32)(object)value;

        private static TEnumType Int32ToEnum(Int32 value) => (TEnumType)(object)value;

        // DoValidation should be called from within an OnValidate() call triggered by editing changes in the Unity Editor
        //              It will  make sure the user does not unintentionally leave the active and valid bit fields in an inconsistent state
        //              An inconsistent state is one where the active bit fields have bits set where the valid bit fields don't
        //              The active bit fields can have either one unique value or multiple values, both are handled
        //
        // parameters :
        //
        // activeFlagsT           actual enumeration member we are tracking with the active state
        // validBitsFieldT        actual enumeration member we are tracking with the valid bits state
        // activeFlagsName        name to appear in dialog boxes for the active bits field
        // validBitsFieldName     name to appear in dialog boxes for the valid bits field
        public void DoValidation(ref TEnumType activeFlagsT, ref TEnumType validBitsFieldT, string activeFlagsName, string validBitsFieldName)
        {
            // First time OnValidate() is called (from which we would call this method) no ediitng in the fields has happened
            // it is only an initial validation check which we take advantage of in order to keep their previous state in order to track it
            if (!_Inited)
            {
                _lastActiveFlagsT = activeFlagsT;
                _lastValidBitsFieldT = validBitsFieldT;
                _Inited = true;
                return;
            }

            Int32 activeFlags = EnumToInt32(activeFlagsT);
            Int32 validBitsField = EnumToInt32(validBitsFieldT);
            Int32 lastActiveFlags = EnumToInt32(_lastActiveFlagsT);
            Int32 lastValidBitsField = EnumToInt32(_lastValidBitsFieldT);

            // Validate that activeFlagsT and validBitsFieldT are consistent with each other when they are edited

            // Check if the active flags field was edited and if it is still compatible with the valid bits field
            if (lastActiveFlags != activeFlags)
            {
                if (activeFlags == EnumToInt32(default(TEnumType))) // we expect the enumeration type to have a value of representing None
                {
                    // activeFlagsT changed to None , check if that is really what is wanted
                    if (!EditorUtility.DisplayDialog(activeFlagsName + " set to None",
                        activeFlagsName + " changed from (" + _lastActiveFlagsT + ") to (" + activeFlagsT +")\n" +
                        "Do you want to proceed ? ", "OK Proceed", "Skip"))
                    {
                        activeFlags = lastActiveFlags;
                    }
                }
                else if (!OvrAvatarUtility.IsSingleEnumInFlags(activeFlags, validBitsField))
                {
                    // activeFlagsT changed and its bit is not in the validBitsFieldT flags, lets suggest valid flags set to add the activeFlagsT flag bit
                    if (EditorUtility.DisplayDialog(activeFlagsName + " edited and incompatible with " + validBitsFieldName,
                        activeFlagsName + " changed from (" + _lastActiveFlagsT + ") to (" + activeFlagsT + ")\n" +
                        "Consider adding the flag (" + activeFlagsT + ") into " + validBitsFieldName,
                        "OK Proceed", "Skip"))
                    {
                        validBitsField |= activeFlags;
                    }
                }
            }

            // Check if the valid bits field was edited and if the active flags field is still compatible with it
            if (lastValidBitsField != validBitsField && !OvrAvatarUtility.IsSingleEnumInFlags(activeFlags, validBitsField))
            {
                if (validBitsField == EnumToInt32(default(TEnumType)))
                {
                    // validBitsFieldT changed to None , check if that is really what is wanted
                    if (!EditorUtility.DisplayDialog(validBitsFieldName + " set to None",
                        validBitsFieldName + " changed from (" + _lastValidBitsFieldT + ") to(" + validBitsFieldT + ")\n" +
                        "This may cause trouble with the " + activeFlagsName + " flag. Do you want to proceed ? ", "OK Proceed", "Skip"))
                    {
                        validBitsField |= lastValidBitsField;
                    }
                }
                else
                {
                    // validBitsFieldT changed and the current activeFlagsT is not compatible with that set, lets suggest to keep
                    // the necessary flags in the validBitsFieldT or to find a usable flag
                    Int32 compatibleFlags = activeFlags & validBitsField;
                    if (compatibleFlags == 0)
                    {
                        // no fields left in common between the active and the valid set, lets find one in the valid set that is usable
                        // this will alwasy be the case if the active field can hold only a single value (vs multiple values)
                        compatibleFlags = OvrAvatarUtility.GetLowestEnumValue(validBitsField);
                    }

                    if (EditorUtility.DisplayDialog(validBitsFieldName + " edited and incompatible with " + activeFlagsName,
                        validBitsFieldName + " changed from (" + _lastValidBitsFieldT + ") to(" + validBitsFieldT + ")\n" +
                        "Consider modifying the " + activeFlagsName + " flag to one compatible with the " + validBitsFieldName + " flags to synchronize them , going " +
                        "from (" + activeFlagsT + ") to (" + Int32ToEnum(compatibleFlags) + ")",
                        "OK Proceed", "Skip"))
                    {
                        activeFlags = compatibleFlags;
                    }
                }
            }

            activeFlagsT = Int32ToEnum(activeFlags);
            validBitsFieldT = Int32ToEnum(validBitsField);
            _lastActiveFlagsT = Int32ToEnum(activeFlags);
            _lastValidBitsFieldT = Int32ToEnum(validBitsField);
        }
    }

#endif
}
