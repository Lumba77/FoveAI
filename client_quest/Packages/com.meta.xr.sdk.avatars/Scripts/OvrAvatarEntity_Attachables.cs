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
using System.Collections.Generic;

#if UNITY_EDITOR
using UnityEditor;

#endif
using UnityEngine;

using static Oculus.Avatar2.CAPI;

/**
 * @file OvrAvatarEntity.cs
 * This is the main file for a partial class.
 * Other functionality is split out into the files below:
 * - OvrAvatarEntity_Color.cs
 * - OvrAvatarEntity_Debug.cs
 * - OvrAvatarEntity_Loading.cs
 * - OvrAvatarEntity_LOD.cs
 * - OvrAvatarEntity_Rendering.cs
 * - OvrAvatarEntity_Streaming.cs
 */
namespace Oculus.Avatar2
{
    public partial class OvrAvatarEntity
    {
        protected Dictionary<string, OvrAvatarSocketDefinition> Sockets = new Dictionary<string, OvrAvatarSocketDefinition>();

        public OvrAvatarSocketDefinition CreateSocket(
            string name,
            CAPI.ovrAvatar2JointType parent,
            // Canonical position and rotation
            Vector3 position,
            Vector3 eulerAngles,
            Vector3? baseScale = null,
            // Canonical Sizes (for calculating scaling)
            float? width = null,
            float? depth = null,
            float? height = null,
            // Configuration
            bool createGameObject = true,
            bool scaleGameObject = false)
        {
            if (Sockets.ContainsKey(name))
            {
                Debug.LogError("Creating a socket with duplicate name: " + name);
                return Sockets[name];
            }
            OvrAvatarSocketDefinition socket = new OvrAvatarSocketDefinition(
                this,
                this.internalEntityId,
                name,
                parent,
                position,
                eulerAngles,
                baseScale ?? Vector3.one,
                width,
                depth,
                height,
                createGameObject,
                scaleGameObject
            );
            Sockets[name] = socket;
            _socketsDirty = true;
            return socket;
        }

        public Transform? GetTransformForSocket(string name)
        {
            if (Sockets.TryGetValue(name, out var socket))
            {
                return socket.socketObj?.transform;
            }
            return null;
        }

        public Transform? GetUnscaledTransformForSocket(string name)
        {
            if (Sockets.TryGetValue(name, out var socket))
            {
                if (socket.scaleGameObject)
                {
                    return socket.socketObjUnscaled?.transform;
                }
                else
                {
                    return socket.socketObj?.transform;
                }
            }
            return null;
        }

        public bool AllSocketsAreReadyToProcess()
        {
            if (Sockets.Count == 0)
            {
                return false;
            }

            foreach (var socket in Sockets)
            {
                // All sockets are not ready
                if (!socket.Value.IsReadyToProcess())
                {
                    return false;

                }
            }
            return true;
        }
        public bool AllSocketsAreDoneLoading()
        {
            foreach (var socket in Sockets)
            {
                // All sockets are not ready
                if (socket.Value.loadStatus != SocketLoadStatus.Done)
                {
                    return false;

                }
            }
            return true;
        }
        public bool InitializeSockets()
        {
            bool done = true;
            foreach (var socket in Sockets)
            {
                done |= socket.Value.Initialize();
            }
            if (AllSocketsAreReadyToProcess())
            {
                if (Point2PointCorrespondenceManager.Instance.ProcessPoint2PointCorrespondence(entityId))
                {
                    foreach (var socket in Sockets)
                    {
                        socket.Value.FinishProcessing();
                    }
                }
            }
            return done;
        }

        [Obsolete("Use dictionary access to Sockets[name]")]
        public OvrAvatarSocketDefinition FindSocketByName(string name)
        {
            return Sockets[name];
        }

#if SOCKET_LOGGING
        private HashSet<string> attachablesLogs = new();

        private const bool SUPPRESS_DUPLICATE_ATTACHABLES_LOGS = true;
        private void Log(string log, bool isWarning = false)
        {
            if (SUPPRESS_DUPLICATE_ATTACHABLES_LOGS)
            {
                if (!attachablesLogs.Contains(log))
                {
                    if (isWarning)
                    {
                        Avatar2.OvrAvatarLog.LogWarning(log);
                    }
                    else
                    {
                        Avatar2.OvrAvatarLog.LogInfo(log);
                    }
                    attachablesLogs.Add(log);
                }
            }
            else
            {
#pragma warning disable CS0162
                if (isWarning)
                {
                    Avatar2.OvrAvatarLog.LogWarning(log);
                }
                else
                {
                    Avatar2.OvrAvatarLog.LogInfo(log);
                }
            }
        }
#endif

        protected void OnUpdateAttachables()
        {
            using var livePerfMarker = OvrAvatarXLivePerf_Marker(ovrAvatarXLivePerf_UnitySectionID.Entity_Attachables_OnUpdate);
            // This will wait until critical joints and Point2point correspondence is ready,
            // then initialize the unity transforms and debug primitives. Once socket is
            // initialized, it will not be updated again.
            foreach (var socket in Sockets)
            {
                if (socket.Value.loadStatus == SocketLoadStatus.Uninitialized)
                {
                    if (socket.Value.Initialize(_skeletonLoaded))
                    {
#if SOCKET_LOGGING
                        Log("[Attachables][" + entityId + "] Initialize: " + socket.Value.name);
#endif
                    }
                }
            }
            if (_skeletonLoaded && (AllSocketsAreReadyToProcess() || _socketsDirty))
            {
#if SOCKET_LOGGING
                Log("[Attachables][" + entityId + "] ProcessPoint2PointCorrespondence");
#endif
                if (Point2PointCorrespondenceManager.Instance.ProcessPoint2PointCorrespondence(entityId))
                {
                    foreach (var socket in Sockets)
                    {
#if SOCKET_LOGGING
                        Log("[Attachables][" + entityId + "] FinishProcessing: " + socket.Value.name);
#endif
                        socket.Value.FinishProcessing();
                    }
#if SOCKET_LOGGING
                    Log("[Attachables][" + entityId + "] Marking Socket Not Dirty");
#endif
                    _socketsDirty = false;
                }
#if SOCKET_LOGGING
                else
                {
                    Log("[Attachables][" + entityId + "] ProcessPoint2PointCorrespondence FAILED", true);
                }
#endif
            }
        }
#if UNITY_EDITOR
        // Called when OvrAvatarEntity is modified in the Unity Inspector.
        // Does demonstrate Socket updating behavior.
        protected void OnValidateAttachables()
        {
            if (EditorApplication.isPlaying)
            {
#if SOCKET_LOGGING
                Log("[Attachables][" + entityId + "] OnValidateAttachables: Marking Socket Dirty");
#endif
                MarkSocketsDirty(this);
            }
        }
#endif //UNITY_EDITOR

        protected void MarkSocketsDirty(OvrAvatarEntity entity)
        {

#if SOCKET_LOGGING
            if (_socketsDirty)
            {
                Log("[Attachables][" + entityId + "] MarkSocketsDirty: Marking Socket Dirty, but already dirty");
            }
            if (Sockets.Count == 0)
            {
                Log("[Attachables][" + entityId + "] MarkSocketsDirty: Marking Socket Dirty, but Sockets.Count == 0");
            }
#endif
            if (!_socketsDirty && Sockets.Count > 0)
            {
#if SOCKET_LOGGING
                Log("[Attachables][" + entityId + "] MarkSocketsDirty: Marking Socket Dirty");
#endif

                _socketsDirty = true;
            }

            foreach (var (_, socket) in Sockets)
            {
                socket.ReInitialize();
            }
        }
        protected void MarkSkeletonLoaded(OvrAvatarEntity entity)
        {
#if SOCKET_LOGGING
            Log("[Attachables][" + entityId + "] MarkSkeletonLoaded: Marking Skeleton Loaded");
#endif
            _skeletonLoaded = true;

            foreach (var (_, socket) in Sockets)
            {
                socket.ReInitialize();
            }
        }
        protected void ReprocessSockets(OvrAvatarEntity entity)
        {
            if (_skeletonLoaded && AllSocketsAreDoneLoading())
            {
                if (Point2PointCorrespondenceManager.Instance.ProcessPoint2PointCorrespondence(entityId))
                {
                    foreach (var socket in Sockets)
                    {
                        if (socket.Value.loadStatus == SocketLoadStatus.Done)
                        {
                            socket.Value.RecalculatePositions();
                        }
                    }
                }
            }
        }
        private bool _skeletonLoaded = false;
        private bool _socketsDirty = false;
        protected void OnAwakeAttachables()
        {
            OnUserAvatarLoadedEvent.AddListener(MarkSocketsDirty);

            OnDefaultAvatarLoadedEvent.AddListener(MarkSocketsDirty);

            OnSkeletonLoadedEvent.AddListener(MarkSocketsDirty);
            OnSkeletonLoadedEvent.AddListener(MarkSkeletonLoaded);
        }
        protected void OnDestroyAttachables()
        {
            OnUserAvatarLoadedEvent.RemoveListener(MarkSocketsDirty);

            OnDefaultAvatarLoadedEvent.RemoveListener(MarkSocketsDirty);

            OnSkeletonLoadedEvent.RemoveListener(MarkSocketsDirty);
            OnSkeletonLoadedEvent.RemoveListener(MarkSkeletonLoaded);
        }
    }
}
