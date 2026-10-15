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
using UnityEngine;


namespace Oculus.Avatar2
{
    public class AvatarLODGameObjectGroup : AvatarLODGroup
    {
        private const string logScope = "AvatarLODGameObjectGroup";

        [SerializeField]
        private GameObject[] gameObjects_ = Array.Empty<GameObject>();

        public GameObject[] GameObjects
        {
            get { return this.gameObjects_; }
            set
            {
                this.gameObjects_ = value;
                count = GameObjects.Length;
                ResetLODGroup();
            }
        }

        public override void ResetLODGroup()
        {
            if (!Application.isPlaying) return;
            for (int i = 0; i < GameObjects.Length; i++)
            {
                if (GameObjects[i] == null) continue;
                GameObjects[i].SetActive(false);
            }

            UpdateAdjustedLevel();
            UpdateLODGroup();
        }

        public override void UpdateLODGroup()
        {
            if (prevAdjustedLevel_ >= 0)
            {
                if (prevAdjustedLevel_ < GameObjects.Length)
                {
                    GameObjects[prevAdjustedLevel_]?.SetActive(false);
                }
                else
                {
                    OvrAvatarLog.LogWarning("prevAdjustedLevel outside bounds of GameObjects array", logScope, this);
                }
            }

            if (adjustedLevel_ >= 0)
            {
                if (adjustedLevel_ < GameObjects.Length)
                {
                    GameObjects[adjustedLevel_].SetActive(true);
                }
                else
                {
                    OvrAvatarLog.LogWarning("adjustedLevel outside bounds of GameObjects array", logScope, this);
                }
            }

            prevLevel_ = Level;
            prevAdjustedLevel_ = adjustedLevel_;
        }
    }
}
