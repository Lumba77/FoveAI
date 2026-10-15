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

using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Android;

/// @file OvrAvatarManager_Textures.cs

namespace Oculus.Avatar2
{
    public partial class OvrAvatarManager
    {
        public const string PERMISSION_EYE_TRACKING = "com.oculus.permission.EYE_TRACKING";
        public const string PERMISSION_FACE_TRACKING = "com.oculus.permission.FACE_TRACKING";
        public const string PERMISSION_BODY_TRACKING = "com.oculus.permission.BODY_TRACKING";

        enum PermissionState { None, Requesting, Granted, Denied, DeniedNoAsk };
        private readonly Queue<string> permissionQueue = new Queue<string>();
        private readonly Dictionary<string, PermissionState> permissionCache = new Dictionary<string, PermissionState>();
#pragma warning disable CS0414
        private bool permissionManagerWaiting = false;
#pragma warning restore CS0414

        [Header("Permissions")]
        [SerializeField]
        public bool automaticallyRequestPermissions = true;

        private void PermissionGranted(string permission)
        {
            OvrAvatarLog.LogInfo($"[GRANTED] {permission}");
            permissionCache[permission] = PermissionState.Granted;
            permissionManagerWaiting = false;
        }
        private void PermissionDenied(string permission)
        {
            OvrAvatarLog.LogInfo($"[DENIED] {permission}");
            permissionCache[permission] = PermissionState.Denied;
            permissionManagerWaiting = false;
        }

#if !UNITY_6000_0_OR_NEWER
        private void PermissionDeniedAndDontAskAgain(string permission)
        {
            OvrAvatarLog.LogInfo($"[DENIED_NO_ASK] {permission}");
            permissionCache[permission] = PermissionState.DeniedNoAsk;
            permissionManagerWaiting = false;
        }
#endif // !UNITY_6000_0_OR_NEWER
        public void RequestEyeTrackingPermission()
        {
            QueuePermissionRequest(PERMISSION_EYE_TRACKING);
        }
        public void RequestFaceTrackingPermission()
        {
            QueuePermissionRequest(PERMISSION_FACE_TRACKING);
        }
        public void RequestBodyTrackingPermission()
        {
            QueuePermissionRequest(PERMISSION_BODY_TRACKING);
        }
        public void RequestMicPermission()
        {
            QueuePermissionRequest(Permission.Microphone);
        }
        public void QueuePermissionRequest(string perm)
        {
            if (!permissionQueue.Contains(perm) && !permissionCache.ContainsKey(perm))
            {
                permissionQueue.Enqueue(perm);
            }
        }
        public void EnablePermissionRequests()
        {
            automaticallyRequestPermissions = true;
        }
        private void Permission_Update()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (automaticallyRequestPermissions && permissionQueue.Count>0 && !permissionManagerWaiting)
            {
                var perm = permissionQueue.Dequeue();
                if (!permissionCache.ContainsKey(perm))
                {
                    if (!Permission.HasUserAuthorizedPermission(perm))
                    {
                        permissionManagerWaiting = true;
                        OvrAvatarLog.LogInfo("Requesting: " + perm);
                        var callbacks = new PermissionCallbacks();
                        callbacks.PermissionGranted += PermissionGranted;
                        callbacks.PermissionDenied += PermissionDenied;
#if !UNITY_6000_0_OR_NEWER
                        callbacks.PermissionDeniedAndDontAskAgain += PermissionDeniedAndDontAskAgain;
#endif // !UNITY_6000_0_OR_NEWER
                        Permission.RequestUserPermission(perm, callbacks);
                    }
                    else
                    {
                        permissionCache[perm] = PermissionState.Granted;
                        OvrAvatarLog.LogInfo("Skipping Permission Request for: " + perm + " (Already requested and: " + permissionCache[perm] + ")");
                    }
                } else
                {
                    OvrAvatarLog.LogInfo("Skipping Permission Request for: "+perm+" (Already requested and: "+ permissionCache[perm] + ")");
                }
            }
#endif
        }
    }
}
