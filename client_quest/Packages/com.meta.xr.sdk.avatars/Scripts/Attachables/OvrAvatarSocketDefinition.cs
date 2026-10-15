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
using System.Linq;
using UnityEngine;

namespace Oculus.Avatar2
{
    public enum SocketLoadStatus { Uninitialized, Initialized, Error, Done }

    public enum SocketPoint2PointCorrespondenceType { Invalid, Root, Position, Height, Depth, Width }

    [System.Serializable]
    public class OvrAvatarSocketDefinition
    {
        // Socket Identifying information
        public OvrAvatarEntity owner;
        public CAPI.ovrAvatar2EntityId ownerEntityId;
        public string name = "";

        // Authoring information
        public CAPI.ovrAvatar2JointType parentJoint;
        private Vector3 abstractLocalPosition;
        private Vector3 abstractSize;

        // Calculated transform information
        private Vector3 _localPosition; //real
        public Vector3 localPosition
        {
            get
            {
                if (loadStatus == SocketLoadStatus.Done)
                {
                    return _localPosition;
                }
                else
                {
                    throw new Exception("Accessing localPosition before Socket is initialized");
                }
            }
        }
        public Vector3 _localEulerAngles = Vector3.zero;
        public ref readonly Vector3 localEulerAngles => ref _localEulerAngles;
        private Vector3 _baseScale = Vector3.one;
        private Vector3 _localScale = Vector3.one;
        public ref readonly Vector3 localScale => ref _localScale;
        // Backing Point2Point Correspondence values
        private Dictionary<SocketPoint2PointCorrespondenceType, Point2PointTransform> _point2pointCorrespondences = new();
        public IReadOnlyDictionary<SocketPoint2PointCorrespondenceType, Point2PointTransform> Correspondences => _point2pointCorrespondences;
        // Scene Manifestation
        public SocketLoadStatus loadStatus = SocketLoadStatus.Uninitialized;
        public string loadError = "";
        public bool createGameObject = true;
        public bool scaleGameObject = false;
        public bool createDebugPrimitive = false;
        public GameObject? socketObj;
        public GameObject? socketObjUnscaled;
        public GameObject? socketed;

        public OvrAvatarSocketDefinition(
            OvrAvatarEntity owner,
            CAPI.ovrAvatar2EntityId ownerId,
            string name,
            CAPI.ovrAvatar2JointType parent,
            // Canonical position and rotation
            Vector3 position,
            Vector3 eulerAngles,
            Vector3 baseScale,
            // Canonical Sizes (for calculating scaling)
            float? width = null,
            float? depth = null,
            float? height = null,
            // Configuration
            bool createGameObject = true,
            bool scaleGameObject = false,
            bool createDebugPrimitive = false)
        {

            this.owner = owner;
            this.ownerEntityId = ownerId;
            this.name = string.Intern(name); // Intern name to optimize string lookups
            this.parentJoint = parent;
            var criticalJoints = owner.GetCriticalJoints();
            if (!criticalJoints.Contains(parentJoint))
            {
                Debug.LogWarning("[OvrAvatarSocket] " + name + " is being initialized to an unloaded critical Joint type: " + parentJoint);
            }
            this.abstractLocalPosition = position;
            // Current Point to Point Correspondence doesn't impact rotation in reproportioning
            this._localEulerAngles = eulerAngles;
            this._baseScale = baseScale;

            this.abstractSize = new Vector3(height ?? 0, depth ?? 0, width ?? 0);
            this.createGameObject = createGameObject;
            this.scaleGameObject = scaleGameObject;
            this.createDebugPrimitive = createDebugPrimitive;
            if (this.createGameObject)
            {
                _updateGameObject(null);
            }
        }

        private float Height => abstractSize.x;
        private float Depth => abstractSize.y;
        private float Width => abstractSize.z;

        // Called by OvrAvatarEntity_Attachables.OnUpdateAttachables, called by OvrAvatarEntity.Update
        // Polls for critical joint and Point2Point Correspondence to be processed, then updates the socket's local position
        // Most likely could use some polling rate protections to reduce CPU usage during Avatar loading.
        //
        // Not recommended to call on Start, since the avatar isn't going to be loaded, and "IsReadyToInitialize" will fail
        public bool Initialize(bool errorOnMissingSkeleton = true)
        {
            if (loadStatus == SocketLoadStatus.Uninitialized)
            {
                if (!ValidateConfig())
                {
                    // Allow delay of initialization while we await skeleton load
                    if (errorOnMissingSkeleton)
                    {
                        loadStatus = SocketLoadStatus.Error;
                        loadError = "No Critical Joint Found";
                    }
                    return false;
                }
                else if (HasRequiredCriticalJoints())
                {
                    if (_registerAllPoints())
                    {
                        loadStatus = SocketLoadStatus.Initialized;
                        return true;
                        // Don't process here
                        // Process();
                    }
                    else
                    {
                        loadStatus = SocketLoadStatus.Error;
                        loadError = "Failed to register Correspondence";
                        return false;
                    }
                }
                else
                {
                    return false; // Not ready to initialize
                }
            }
            else if (loadStatus == SocketLoadStatus.Done)
            {
                return true; //already initialized;
            }
            else //(loadStatus == SocketLoadStatus.Error)
            {
                return false; //already failed to initialized;
            }
        }
        public bool FinishProcessing()
        {
            if (Point2PointCorrespondenceManager.Instance.AllProcessed(ownerEntityId))
            {
                RecalculatePositions();
                loadStatus = SocketLoadStatus.Done;
                return true;
            }
            else
            {
                loadStatus = SocketLoadStatus.Error;
                loadError = "Failed to process Correspondence";
                return false;
            }
        }

        public bool ValidateConfig()
        {
            var criticalJoints = owner.GetCriticalJoints();
            return criticalJoints.Contains(parentJoint);
        }

        public bool HasRequiredCriticalJoints()
        {
            bool hasCriticalJoint = ValidateConfig();
            bool hasCriticalJointTransform = owner.GetSkeletonTransform(parentJoint) != null;
            return hasCriticalJoint && hasCriticalJointTransform;
        }
        public bool IsReadyToProcess()
        {
            return loadStatus == SocketLoadStatus.Initialized;
        }
        public bool IsProcessed()
        {
            return HasRequiredCriticalJoints() && Point2PointCorrespondenceManager.Instance.AllProcessed(ownerEntityId);
        }

        readonly Dictionary<CAPI.ovrAvatar2JointType, Vector3> _canonicalJointPositionOverrides = new()
        {
            [CAPI.ovrAvatar2JointType.Hips] = new Vector3(0, 0.933547020f, -0.00951099955f),
            [CAPI.ovrAvatar2JointType.Head] = new Vector3(-4.29339707e-07f, 1.56662250f, -0.00951099955f),
            [CAPI.ovrAvatar2JointType.Chest] = new Vector3(-1.53668225e-07f, 1.16398716f, -0.00951099955f)
        };
        readonly Dictionary<CAPI.ovrAvatar2JointType, Quaternion> _canonicalJointRotationOverrides = new()
        {
            [CAPI.ovrAvatar2JointType.Hips] = new Quaternion(-0.707107008f, 0.707107008f, 0, 0),
            [CAPI.ovrAvatar2JointType.Head] = new Quaternion(-0.707107008f, 0.707107008f, 0, 0),
            [CAPI.ovrAvatar2JointType.Chest] = new Quaternion(-0.707107008f, 0.707107008f, 0, 0)
        };
        private bool _registerAllPoints()
        {
            var origin = owner.GetSkeletonTransform(parentJoint);
            if (_canonicalJointPositionOverrides.ContainsKey(parentJoint))
            {
                origin.localPosition = _canonicalJointPositionOverrides[parentJoint];
            }
            if (_canonicalJointRotationOverrides.ContainsKey(parentJoint))
            {
                origin.localRotation = _canonicalJointRotationOverrides[parentJoint];
            }
            if (origin != null)
            {
                var root = _registerPoint2PointCorrespondence(origin.localPosition, origin.localRotation, SocketPoint2PointCorrespondenceType.Root);

                var pivot = _registerPoint2PointCorrespondence(abstractLocalPosition, Quaternion.Euler(_localEulerAngles), SocketPoint2PointCorrespondenceType.Position, parent: root);


                if (Height > 0.0f)
                {
                    _registerPoint2PointCorrespondence(new Vector3(Height / 2, 0, 0), Quaternion.identity, SocketPoint2PointCorrespondenceType.Height, parent: root);
                }
                if (Depth > 0.0f)
                {
                    _registerPoint2PointCorrespondence(new Vector3(0, Depth / 2, 0), Quaternion.identity, SocketPoint2PointCorrespondenceType.Depth, parent: root);
                }
                if (Width > 0.0f)
                {
                    _registerPoint2PointCorrespondence(new Vector3(0, 0, Width / 2), Quaternion.identity, SocketPoint2PointCorrespondenceType.Width, parent: root);
                }
                return true;
            }
            else
            {
                return false;
            }
        }

        private Point2PointTransform? _registerPoint2PointCorrespondence(Vector3 point, Quaternion rotation, SocketPoint2PointCorrespondenceType pointType, Point2PointTransform? parent = null)
        {
            if (point != Vector3.zero || rotation != Quaternion.identity)
            {
                var p2pMan = Point2PointCorrespondenceManager.Instance;
                var p2p = p2pMan.RegisterPoint2PointCorrespondence(owner, ownerEntityId, parentJoint, point, rotation, parent: parent);
                _point2pointCorrespondences[pointType] = p2p;
                return p2p;
            }
            return parent;
        }

        public void SetPosition(Vector3 pos)
        {
            this.abstractLocalPosition = pos;
            ReInitialize();
        }

        public void SetCanonicalSize(Vector3 size)
        {
            this.abstractSize = size;
            ReInitialize();
        }

        public void SetRotation(Vector3 rot)
        {
            this._localEulerAngles = rot;
            ReInitialize();
        }

        public void SetBaseScale(Vector3 baseScale)
        {
            this._baseScale = baseScale;
            ReInitialize();
        }

        public bool RecalculatePositions()
        {
            if (!IsProcessed())
            {
                return false;
            }
            _calculateRealPositions();
            _calculateLocalScaling();
            if (createGameObject)
            {
                var jointTransform = owner.GetSkeletonTransform(parentJoint);
                _updateGameObject(jointTransform);
            }
            return true;
        }

        public void ReInitialize()
        {
            if (!Point2PointCorrespondenceManager.Instance.ClearP2PCorrespondences(ownerEntityId))
            {
                if (loadStatus == SocketLoadStatus.Done)
                {
                    OvrAvatarLog.LogWarning($"Failed to remove p2p correspondence for entity {ownerEntityId}");
                }
                return;
            }
            loadStatus = SocketLoadStatus.Uninitialized;
            Initialize();
        }

        private void _calculateRealPositions()
        {
            if (this._point2pointCorrespondences.ContainsKey(SocketPoint2PointCorrespondenceType.Position))
            {
                var p2p_position = this._point2pointCorrespondences[SocketPoint2PointCorrespondenceType.Position];
                if (p2p_position.processed)
                {
                    _localPosition = p2p_position.realLocalPosition;
                }
            }
        }

        private void _calculateLocalScaling()
        {
            if (this._point2pointCorrespondences.ContainsKey(SocketPoint2PointCorrespondenceType.Height))
            {
                var p2p_height = this._point2pointCorrespondences[SocketPoint2PointCorrespondenceType.Height];
                if (p2p_height.processed)
                {
                    if (p2p_height.abstractLocalPosition.x != 0.0f)
                    {
                        // _localScale.x = _baseScale.x * p2p_height.realLocalPosition.x / p2p_height.abstractLocalPosition.x;
                        _localScale.x = _baseScale.x * p2p_height.realLocalPosition.magnitude / p2p_height.abstractLocalPosition.magnitude;
                    }
                }
            }
            if (this._point2pointCorrespondences.ContainsKey(SocketPoint2PointCorrespondenceType.Depth))
            {
                var p2p_depth = this._point2pointCorrespondences[SocketPoint2PointCorrespondenceType.Depth];
                if (p2p_depth.processed)
                {
                    if (p2p_depth.abstractLocalPosition.y != 0.0f)
                    {
                        // _localScale.y = _baseScale.y * p2p_depth.realLocalPosition.y / p2p_depth.abstractLocalPosition.y;
                        _localScale.y = _baseScale.y * p2p_depth.realLocalPosition.magnitude / p2p_depth.abstractLocalPosition.magnitude;
                    }
                }
            }
            if (this._point2pointCorrespondences.ContainsKey(SocketPoint2PointCorrespondenceType.Width))
            {
                var p2p_width = this._point2pointCorrespondences[SocketPoint2PointCorrespondenceType.Width];
                if (p2p_width.processed)
                {
                    if (p2p_width.abstractLocalPosition.z != 0.0f)
                    {
                        // _localScale.z = _baseScale.z * p2p_width.realLocalPosition.z / p2p_width.abstractLocalPosition.z;
                        _localScale.z = _baseScale.z * p2p_width.realLocalPosition.magnitude / p2p_width.abstractLocalPosition.magnitude;
                    }
                }
            }
        }

        private void _updateGameObject(Transform? jointTransform)
        {
            if (createGameObject && socketObj == null)
            {
                //Initialize gameObject
                GameObject attachmentObj = new GameObject("[SOCKET] " + name, typeof(OvrAvatarSocket));
                if (createDebugPrimitive)
                {
                    GameObject cubeObj = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    cubeObj.name = "[DEBUG MANIFESTATION] " + name;
                    cubeObj.transform.localScale = new Vector3(0.1f, 0.1f, 0.1f);
                    cubeObj.AddComponent<OvrAvatarSocket>();
                    cubeObj.transform.SetParent(attachmentObj.transform, false);
                }
                if (jointTransform != null)
                {
                    attachmentObj.transform.SetParent(jointTransform, false);
                }
                else
                {
                    attachmentObj.transform.SetParent(owner.transform);
                }
                socketObj = attachmentObj;

                if (scaleGameObject)
                {
                    GameObject attachmentObjUnscaled = new GameObject("[SOCKET] " + name + " (Unscaled)", typeof(OvrAvatarSocket));

                    if (jointTransform != null)
                    {
                        attachmentObjUnscaled.transform.SetParent(jointTransform, false);
                    }
                    else
                    {
                        attachmentObjUnscaled.transform.SetParent(owner.transform);
                    }

                    socketObjUnscaled = attachmentObjUnscaled;
                }
                else
                {
                    socketObjUnscaled = socketObj;
                }
            }
            _populateSocketObject(socketObj, jointTransform);
            _populateSocketObject(socketObjUnscaled, jointTransform, false);
        }

        private void _populateSocketObject(GameObject? obj, Transform? jointTransform, bool updateScale = true)
        {
            if (obj != null)
            {
                if (obj.transform.parent == owner.transform && jointTransform != null)
                {
                    obj.transform.SetParent(jointTransform, false);
                }
                var oas = obj.GetComponent<OvrAvatarSocket>();
                oas.ParentJoint = this.parentJoint;
                oas.LoadStatus = this.loadStatus;
                oas.LoadError = this.loadError;
                oas.CanonicalPosition = this.abstractLocalPosition;
                oas.CanonicalEulerAngles = this.localEulerAngles;
                oas.CanonicalSize = this.abstractSize;
                oas.RealPosition = this._localPosition;
                oas.RealEulerAngles = this.localEulerAngles;
                oas.RealSize = Vector3.Scale(this._localScale, this.abstractSize);
                oas.RealScale = this._localScale;
                oas.Definition = this;

                var socket_transform = obj.transform;
                socket_transform.localPosition = _localPosition;
                socket_transform.localEulerAngles = localEulerAngles;
                if (updateScale && scaleGameObject && jointTransform != null)
                {
                    // Scale is in the bone transform frame of reference, not the socket frame.
                    // Need to take each unit vector, scale them in parent frame, then use that derived scale
                    // This mitigates nonuniform scaling issues
                    var right_local = jointTransform.worldToLocalMatrix.MultiplyVector(socket_transform.right);
                    right_local.Scale(this._localScale);
                    var x = right_local.magnitude;
                    var up_local = jointTransform.worldToLocalMatrix.MultiplyVector(socket_transform.up);
                    up_local.Scale(this._localScale);
                    var y = up_local.magnitude;
                    var forward_local = jointTransform.worldToLocalMatrix.MultiplyVector(socket_transform.forward);
                    forward_local.Scale(this._localScale);
                    var z = forward_local.magnitude;

                    socket_transform.localScale = new Vector3(x, y, z);
                }
                else
                {
                    socket_transform.localScale = new Vector3(1, 1, 1);
                }
            }
        }

        public bool IsReady()
        {
            return loadStatus == SocketLoadStatus.Done;
        }

        public bool IsEmpty()
        {
            return socketed == null;
        }

        public bool Attach(GameObject go)
        {
            // If Avatar is mirrored, we probably want to disable all colliders from this gameobject?
            if (loadStatus == SocketLoadStatus.Done && socketObj != null)
            {
                if (go == socketed)
                {
                    return true;
                }
                if (socketed != null)
                {
                    GameObject? old;
                    Detach(out old);
                }
                go.transform.SetParent(socketObj.transform, false);
                go.transform.localScale = Vector3.one;
                go.transform.localPosition = Vector3.zero;
                go.transform.localRotation = Quaternion.identity;
                go.SetActive(true);
                socketed = go;
                return true;
            }
            return false;
        }
        public bool Detach(out GameObject? go)
        {
            if (loadStatus == SocketLoadStatus.Done && socketObj != null && socketed != null)
            {
                go = socketed;
                go.transform.SetParent(null);
                go.SetActive(false);
                socketed = go;
                return true;
            }
            go = null;
            return false;
        }
    }
}
