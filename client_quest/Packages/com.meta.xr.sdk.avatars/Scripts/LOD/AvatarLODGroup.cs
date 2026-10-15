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
using UnityEngine;


namespace Oculus.Avatar2
{
    public class AvatarLODGroup : MonoBehaviour, IDisposable
    {
        protected int count;

        public AvatarLOD? parentLOD = null;

        public bool remapInOrder = false;

        protected int level_ = -1;
        protected int prevLevel_ = -1;
        protected int adjustedLevel_ = -1;

        public int AdjustedLevel
        {
            get { return this.adjustedLevel_; }
        }

        protected int prevAdjustedLevel_ = -1;

        public int Level
        {
            get { return this.level_; }
            set
            {
                if (value == prevLevel_ && value == prevAdjustedLevel_)
                    return;
                this.level_ = value;

                // Update if parentLOD previously did not have LODs loaded yet
                UpdateAdjustedLevel();
                if (adjustedLevel_ != prevAdjustedLevel_)
                {
                    UpdateLODGroup();
                }
            }
        }

        protected virtual void OnDestroy()
        {
            Dispose();
        }

        public void Dispose()
        {
            if (parentLOD is not null) { parentLOD.RemoveLODGroup(this); }
            parentLOD = null;
        }

        public virtual void ResetLODGroup()
        {
        }

        protected virtual void UpdateAdjustedLevel()
        {
            if (Level < 0 || !parentLOD)
            {
                adjustedLevel_ = -1;
                return;
            }

            if (parentLOD is not null)
            {
                adjustedLevel_ = parentLOD.CalcAdjustedLod(Level);
            }
        }

        public virtual void UpdateLODGroup()
        {
            prevLevel_ = Level;
            prevAdjustedLevel_ = adjustedLevel_;
        }

        public virtual void OnRenderableDisposed(OvrAvatarRenderable disposedRenderable)
        {
            // Intentionally empty
        }

        internal virtual byte LevelsWithAnimationUpdateCost => (byte)(1 << Level);
    }
}
