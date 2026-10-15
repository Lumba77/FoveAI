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

using UnityEngine;

namespace Oculus.Avatar2.Utils
{
    public class AvatarLODLookat : MonoBehaviour
    {
        [SerializeField]
        public Transform? xform;
        [SerializeField]
        public UpVectorMode upVectorMode = UpVectorMode.WORLD_UP;
        [SerializeField]
        public Vector3 upVector = Vector3.up;
        [SerializeField]
        public GameObject? upObject = null;
        private Transform? camXform = null;

        public enum UpVectorMode
        {
            WORLD_UP, // World Pos Y  (Default)
            OBJECT_UP, // Vector from self to upObject
            OBJECT_AIM // Use upVector
        }

        protected virtual void Update()
        {
            if (xform == null)
                xform = this.transform;

            if (!AvatarLODManager.Instance)
            {
                return;
            }

            if (AvatarLODManager.Instance.CurrentCamera == null)
                return;

            camXform = AvatarLODManager.Instance.CurrentCamera.transform;

            if (upVectorMode == UpVectorMode.WORLD_UP)
            {
                xform.rotation = Quaternion.LookRotation(
                   camXform.position - xform.position,
                  upVector);
            }
            else if (upVectorMode == UpVectorMode.OBJECT_UP)
            {
                if (upObject == null)
                {
                    upObject = AvatarLODManager.Instance.CurrentCamera.gameObject;
                }
                xform.rotation = Quaternion.LookRotation(
                    camXform.position - xform.position,
                  upObject.transform.rotation * upVector);
            }
            else if (upObject != null)
            {
                // OBJECT_AIM
                xform.rotation = Quaternion.LookRotation(
                    camXform.position - xform.position,
                  xform.position - upObject.transform.position);
            }
        }
    }
}
