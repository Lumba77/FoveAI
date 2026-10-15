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
using Unity.Collections;
using UnityEngine;

using ovrAvatar2SizeType = System.UIntPtr;

namespace Oculus.Avatar2
{
    public sealed class Point2PointTransform
    {
        public Point2PointTransform parent;

        public Vector3 abstractLocalPosition;
        public Quaternion rotation;

        // Calculated from abstractLocalPosition and parent
        public Vector3 abstractWorldPosition
        {
            get
            {
                if (parent != null)
                {
                    return parent.abstractWorldPosition + parent.worldRotation * abstractLocalPosition;
                }
                else
                {
                    return abstractLocalPosition;
                }
            }
        }
        public Quaternion worldRotation
        {
            get
            {
                if (parent != null)
                {
                    return parent.rotation * rotation;
                }
                else
                {
                    return rotation;
                }
            }
        }
        public Vector3 realWorldPosition;
        // Calculated from realWorldPosition and parent
        public Vector3 realLocalPosition
        {
            get
            {
                if (parent != null)
                {
                    return Quaternion.Inverse(parent.worldRotation) * (realWorldPosition - parent.realWorldPosition);
                }
                else
                {
                    return realWorldPosition;
                }
            }
        }
        public void AssignRealWorldPositionFromLocal(Vector3 localPosition)
        {

            if (parent != null)
            {
                realWorldPosition = parent.realWorldPosition + parent.worldRotation * localPosition;
            }
            else
            {
                realWorldPosition = localPosition;
            }
        }
        public OvrAvatarEntity owner;
        public CAPI.ovrAvatar2EntityId ownerEntityId;
        public CAPI.ovrAvatar2JointType parentJoint;
        private bool _processed;
        public bool processed
        {
            get { return _processed && (parent == null || parent._processed); }
            set { _processed = value; }
        }
    }

    public sealed class Point2PointCorrespondenceManager
    {
        public static CAPI.ovrAvatar2Vector3f ONE => new CAPI.ovrAvatar2Vector3f(1.0f, 1.0f, 1.0f);
        public static CAPI.ovrAvatar2Quatf IDENTITY => new CAPI.ovrAvatar2Quatf(0.0f, 0.0f, 0.0f, 1.0f);

        private static Point2PointCorrespondenceManager _instance = null;

        public static bool HasInstance => _instance != null;
        // Singleton
        public static Point2PointCorrespondenceManager Instance => _instance ??= new Point2PointCorrespondenceManager();

        // [System.Obsolete("Use Instance instead", false)], TODO: Deprecate `INSTANCE` getter
        public static Point2PointCorrespondenceManager INSTANCE => Instance;

        private Dictionary<CAPI.ovrAvatar2EntityId, List<Point2PointTransform>> _point2PointCorrespondences = new Dictionary<CAPI.ovrAvatar2EntityId, List<Point2PointTransform>>();
        public bool TryGetPoint2Point(CAPI.ovrAvatar2EntityId entityId, Vector3 abstractLocalPosition, out Point2PointTransform p2p)
        {
            if (_point2PointCorrespondences.TryGetValue(entityId, out var p2ps))
            {
                foreach (var p in p2ps)
                {
                    if (p.abstractLocalPosition == abstractLocalPosition)
                    {
                        p2p = p;
                        return true;
                    }
                }
            }
            p2p = new Point2PointTransform();
            return false;
        }

        public Point2PointTransform RegisterPoint2PointCorrespondence(
            OvrAvatarEntity owner,
            CAPI.ovrAvatar2EntityId ownerEntityId,
            CAPI.ovrAvatar2JointType parentJoint,
            Vector3 abstractLocalPosition,
            Quaternion rotation,
            Point2PointTransform parent = null)
        {
            if (!_point2PointCorrespondences.ContainsKey(ownerEntityId))
            {
                _point2PointCorrespondences[ownerEntityId] = new List<Point2PointTransform>();
            }

            var p2p = new Point2PointTransform();

            p2p.abstractLocalPosition = abstractLocalPosition;
            p2p.rotation = rotation;
            p2p.owner = owner;
            p2p.ownerEntityId = ownerEntityId;
            p2p.parentJoint = parentJoint;
            p2p.parent = parent;

            _point2PointCorrespondences[ownerEntityId].Add(p2p);
            // I don't think we want to register in CAPI now. Instead, it is best to do
            // immediatecorrespondence calc as an array later during ProcessPoint2PointCorrespondence.

            return p2p;
        }

        public bool ProcessPoint2PointCorrespondence(CAPI.ovrAvatar2EntityId entityId)
        {
            bool ready = true;
            // Return false if Intentionality isn't initialized

            if (!_point2PointCorrespondences.ContainsKey(entityId))
            {
                return false;
            }

            unsafe
            {
                var queryCount = _point2PointCorrespondences[entityId].Count;
                // ideally this would be a `using` statement. We can't because we modify the collection when assigning the queries
                var correspondenceQueries = new NativeArray<CAPI.ovrAvatar2PointCorrespondenceQuery>(
                                                    queryCount,
                                                    Allocator.Temp,
                                                    NativeArrayOptions.ClearMemory);
                using (var correspondenceResults = new NativeArray<CAPI.ovrAvatar2PointCorrespondenceQueryResult>(
                                                        queryCount,
                                                        Allocator.Temp,
                                                        NativeArrayOptions.ClearMemory))
                {
                    var correspondenceQueriesPtr = correspondenceQueries.GetPtr();
                    var correspondenceResultsPtr = correspondenceResults.GetPtr();
                    for (int i = 0; i < _point2PointCorrespondences[entityId].Count; i++)
                    {
                        CAPI.ovrAvatar2PointCorrespondenceQuery query = new CAPI.ovrAvatar2PointCorrespondenceQuery();
                        query.pointSpace = CAPI.ovrAvatar2PointCorrespondenceQuerySpace.ovrAvatar2PointCorrespondenceQuerySpace_DefaultPoseCharacterSpace;
                        query.surfaceSelection.maxDist = 1; // 1 meter is sufficient
                        query.surfaceSelection.mode = CAPI.ovrAvatar2PointCorrespondenceSurfaceSelectionMode.ovrAvatar2PointCorrespondenceSurfaceSelectionMode_PointProximityToBox;
                        query.pointTransform.position = _point2PointCorrespondences[entityId][i].abstractWorldPosition;
                        query.pointTransform.orientation = IDENTITY;
                        query.pointTransform.scale = ONE;

                        correspondenceQueries[i] = query;
                    }

                    CAPI.ovrAvatar2Entity_ComputeImmediatePointCorrespondence(entityId, correspondenceQueriesPtr, (ovrAvatar2SizeType)queryCount, correspondenceResultsPtr);

                    for (int i = 0; i < _point2PointCorrespondences[entityId].Count; i++)
                    {
                        if (correspondenceResults[i].valid)
                        {
                            var p2p = _point2PointCorrespondences[entityId][i];
                            p2p.realWorldPosition = correspondenceResults[i].transform.position;

                            p2p.processed = correspondenceResults[i].valid;
                        }
                        else
                        {
                            ready = false;
                        }
                    }
                }
                correspondenceQueries.Dispose();
                return ready;
            }
        }

        public bool AllProcessed(CAPI.ovrAvatar2EntityId entityId)
        {
            if (!_point2PointCorrespondences.TryGetValue(entityId, out var p2ps))
            {
                return true;
            }
            foreach (var p2p in p2ps)
            {
                if (!p2p.processed) { return false; }
            }
            return true;
        }

        public bool GetRealPosition(CAPI.ovrAvatar2EntityId entityId, Vector3 abstractPosition, out Vector3 realLocalPosition)
        {
            if (!TryGetPoint2Point(entityId, abstractPosition, out var p2p))
            {
                realLocalPosition = Vector3.zero;
                return false;
            }
            realLocalPosition = p2p.realLocalPosition;
            return true;
        }

        public bool ClearP2PCorrespondences(CAPI.ovrAvatar2EntityId entityId)
        {
            if (_point2PointCorrespondences.TryGetValue(entityId, out var p2ps))
            {
                foreach (var p2p in p2ps)
                {
                    p2p.owner = null;
                    p2p.parent = null;
                }

                _point2PointCorrespondences.Remove(entityId);
                return true;
            }

            return false;
        }

        internal static bool Shutdown()
        {
            var instance = Instance;
            bool hadInstance = instance != null;
            if (hadInstance)
            {
                _instance = null;

                instance._point2PointCorrespondences.Clear();
            }
            return hadInstance;
        }
    }
}
