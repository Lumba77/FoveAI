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

using System.Collections.Generic;
using System;
using UnityEngine;
using static UnityEngine.UI.GridLayoutGroup;
using System.Linq;

namespace Oculus.Avatar2
{
    public class OvrAvatarSocket : MonoBehaviour
    {
        [Header("Socket Parent")]
        public CAPI.ovrAvatar2JointType ParentJoint = CAPI.ovrAvatar2JointType.Invalid;
        public SocketLoadStatus LoadStatus = SocketLoadStatus.Uninitialized;
        public string LoadError = string.Empty;

        [Header("Canonical Positioning")]
        public Vector3 CanonicalPosition = Vector3.zero;
        public Vector3 CanonicalEulerAngles = Vector3.zero;
        public Vector3 CanonicalSize = Vector3.zero;

        [Header("Realized Positioning")]
        public Vector3 RealPosition = Vector3.zero;
        public Vector3 RealEulerAngles = Vector3.zero;
        public Vector3 RealSize = Vector3.zero;
        public Vector3 RealScale = Vector3.zero;

        public OvrAvatarSocketDefinition Definition;

        public bool DrawDebugGizmos = false;
#if UNITY_EDITOR
        public void OnDrawGizmos()
        {
            if (DrawDebugGizmos && LoadStatus == SocketLoadStatus.Done)
            {
                Transform jointTransform = transform.parent;
                if (jointTransform)
                {
                    var abstractWorldPos = jointTransform.TransformPoint(CanonicalPosition);
                    var worldPos = jointTransform.TransformPoint(RealPosition);
                    const float CROSS_HAIR_SIZE = 0.02f;

                    Gizmos.color = Color.green;
                    Gizmos.DrawSphere(jointTransform.position, CROSS_HAIR_SIZE);

                    Gizmos.color = Color.cyan;
                    Gizmos.DrawWireSphere(abstractWorldPos, CROSS_HAIR_SIZE);

                    Gizmos.color = Color.white;
                    Gizmos.DrawLine(abstractWorldPos, worldPos);

                    if (CanonicalSize.magnitude > 0)
                    {
                        List<Vector3> abstractPoints = new List<Vector3>();
                        List<Tuple<Vector3, Vector3>> abstractLines = new List<Tuple<Vector3, Vector3>>();
                        List<Vector3> localPoints = new List<Vector3>();
                        List<Tuple<Vector3, Vector3>> localLines = new List<Tuple<Vector3, Vector3>>();
                        var scalingP2P = Definition.Correspondences.Where(kvp => kvp.Key != SocketPoint2PointCorrespondenceType.Position && kvp.Key != SocketPoint2PointCorrespondenceType.Root).ToArray();

                        var root = Definition.Correspondences[SocketPoint2PointCorrespondenceType.Root];
                        if(!Definition.Correspondences.TryGetValue(SocketPoint2PointCorrespondenceType.Position, out var position)) {
                            position = root;
                        }
                        foreach ( var corr in Definition.Correspondences)
                        {
                            if(corr.Key!= SocketPoint2PointCorrespondenceType.Position && corr.Key!= SocketPoint2PointCorrespondenceType.Root)
                            {
                                Gizmos.color = Color.red;
                                Gizmos.DrawLine(Definition.owner.transform.TransformPoint(root.realWorldPosition),
                                                Definition.owner.transform.TransformPoint(position.realWorldPosition));
                                Gizmos.DrawLine(Definition.owner.transform.TransformPoint(root.realWorldPosition),
                                                Definition.owner.transform.TransformPoint(corr.Value.realWorldPosition));
                                Gizmos.color = Color.grey;
                                Gizmos.DrawLine(Definition.owner.transform.TransformPoint(root.abstractWorldPosition),
                                                Definition.owner.transform.TransformPoint(position.abstractWorldPosition));
                                Gizmos.DrawLine(Definition.owner.transform.TransformPoint(root.abstractWorldPosition),
                                                Definition.owner.transform.TransformPoint(corr.Value.abstractWorldPosition));
                            }
                        }
                        if (scalingP2P.Length == 1)
                        {
                            var a_p0 = scalingP2P[0].Value.abstractLocalPosition - CanonicalPosition;
                            abstractPoints.Add(a_p0);
                            abstractPoints.Add(-a_p0);
                            abstractLines.Add(Tuple.Create(a_p0, -a_p0));

                            var p0_p2p = scalingP2P[0].Value.realLocalPosition - RealPosition;
                            var p0 = a_p0 * (p0_p2p.magnitude / a_p0.magnitude);
                            localPoints.Add(p0);
                            localPoints.Add(-p0);
                            localLines.Add(Tuple.Create(p0, -p0));
                        }
                        if (scalingP2P.Length == 2)
                        {
                            //draw Box
                            var a_p0 = scalingP2P[0].Value.abstractLocalPosition;
                            var a_p1 = scalingP2P[1].Value.abstractLocalPosition;
                            var p0 = scalingP2P[0].Value.realLocalPosition;
                            var p1 = scalingP2P[1].Value.realLocalPosition;
                            foreach (var p0_sign in new int[] { 1, -1 })
                            {
                                foreach (var p1_sign in new int[] { 1, -1 })
                                {
                                    var a_vert = a_p0 * p0_sign + a_p1 * p1_sign;
                                    var vert = p0 * p0_sign + p1 * p1_sign;
                                    abstractPoints.Add(a_vert);
                                    localPoints.Add(vert);
                                    //Rendundant, but code simplicity worth it
                                    abstractLines.Add(Tuple.Create(a_vert, a_p0 * -p0_sign + a_p1 * p1_sign));
                                    abstractLines.Add(Tuple.Create(a_vert, a_p0 * p0_sign + a_p1 * -p1_sign));
                                    localLines.Add(Tuple.Create(vert, p0 * -p0_sign + p1 * p1_sign));
                                    localLines.Add(Tuple.Create(vert, p0 * p0_sign + p1 * -p1_sign));
                                }
                            }
                        }
                        if (scalingP2P.Length == 3)
                        {
                            var a_p0 = scalingP2P[0].Value.abstractLocalPosition;
                            var a_p1 = scalingP2P[1].Value.abstractLocalPosition;
                            var a_p2 = scalingP2P[2].Value.abstractLocalPosition;
                            var p0 = scalingP2P[0].Value.realLocalPosition;
                            var p1 = scalingP2P[1].Value.realLocalPosition;
                            var p2 = scalingP2P[2].Value.realLocalPosition;
                            foreach (var p0_sign in new int[] { 1, -1 })
                            {
                                foreach (var p1_sign in new int[] { 1, -1 })
                                {
                                    foreach (var p2_sign in new int[] { 1, -1 })
                                    {
                                        var a_vert = a_p0 * p0_sign + a_p1 * p1_sign + a_p2 * p2_sign;
                                        var vert = p0 * p0_sign + p1 * p1_sign + p2 * p2_sign;
                                        abstractPoints.Add(a_vert);
                                        localPoints.Add(vert);
                                        //Rendundant, but code simplicity worth it
                                        abstractLines.Add(Tuple.Create(a_vert, a_p0 * -p0_sign + a_p1 * p1_sign + a_p2 * p2_sign));
                                        abstractLines.Add(Tuple.Create(a_vert, a_p0 * p0_sign + a_p1 * -p1_sign + a_p2 * p2_sign));
                                        abstractLines.Add(Tuple.Create(a_vert, a_p0 * p0_sign + a_p1 * p1_sign + a_p2 * -p2_sign));
                                        localLines.Add(Tuple.Create(vert, p0 * -p0_sign + p1 * p1_sign + p2 * p2_sign));
                                        localLines.Add(Tuple.Create(vert, p0 * p0_sign + p1 * -p1_sign + p2 * p2_sign));
                                        localLines.Add(Tuple.Create(vert, p0 * p0_sign + p1 * p1_sign + p2 * -p2_sign));
                                    }
                                }
                            }
                        }
                        Gizmos.color = Color.grey;
                        foreach (var poses in abstractLines)
                        {
                            var rotationMatrix = Matrix4x4.TRS(Definition.owner.transform.TransformPoint(root.abstractWorldPosition), jointTransform.rotation, Vector3.one); // * Quaternion.Euler(RealEulerAngles)
                            var p0 = rotationMatrix.MultiplyPoint(poses.Item1);
                            var p1 = rotationMatrix.MultiplyPoint(poses.Item2);
                            Gizmos.DrawLine(p0, p1);
                        }
                        Gizmos.color = Color.yellow;
                        foreach (var poses in localLines)
                        {
                            var rotationMatrix = Matrix4x4.TRS(Definition.owner.transform.TransformPoint(root.realWorldPosition), jointTransform.rotation, Vector3.one); // * Quaternion.Euler(RealEulerAngles)
                            var p0 = rotationMatrix.MultiplyPoint(poses.Item1);
                            var p1 = rotationMatrix.MultiplyPoint(poses.Item2);
                            Gizmos.DrawLine(p0, p1);
                        }
                    }
                    Gizmos.color = Color.cyan;
                    Gizmos.DrawSphere(worldPos, CROSS_HAIR_SIZE);
                }
            }
        }
#endif // UNITY_EDITOR
    }
}
