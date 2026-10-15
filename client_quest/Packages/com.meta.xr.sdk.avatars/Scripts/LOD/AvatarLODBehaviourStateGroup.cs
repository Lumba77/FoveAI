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
using System.Collections.Generic;


namespace Oculus.Avatar2
{
    public class AvatarLODBehaviourStateGroup : AvatarLODGroup
    {
        AvatarLODBehaviourStateGroup()
        {
            enabledStates_ = new List<bool>() { true };
            lodBehaviours_ = new List<Behaviour>();
        }

        public bool outOfRangeState = false;

        private List<Behaviour> lodBehaviours_ = null!;

        public List<Behaviour> LodBehaviours
        {
            set
            {
                lodBehaviours_ = value;
                UpdateLODGroup();
            }
        }

        public void AddBehaviour(Behaviour behavior)
        {
            lodBehaviours_.Add(behavior);
            UpdateLODGroup();
        }


        private List<bool> enabledStates_;

        public List<bool> EnabledStates
        {
            set
            {
                this.enabledStates_ = value;
                count = enabledStates_.Count;
                ResetLODGroup();
            }
        }

        public void AddEnabledState(bool state)
        {
            enabledStates_.Add(state);
            count = enabledStates_.Count;
            ResetLODGroup();
        }


        public override void ResetLODGroup()
        {
            for (int i = 0; i < lodBehaviours_.Count; i++)
            {
                if (lodBehaviours_[i] != null)
                {
                    lodBehaviours_[i].enabled = false;
                }
            }

            UpdateAdjustedLevel();
            UpdateLODGroup();
        }

        public override void UpdateLODGroup()
        {
            if (adjustedLevel_ < enabledStates_.Count)
            {
                for (int i = 0; i < lodBehaviours_.Count; i++)
                {
                    if (lodBehaviours_[i] == null)
                    {
                        continue;
                    }
                    if (adjustedLevel_ == -1)
                    {
                        lodBehaviours_[i].enabled = outOfRangeState;
                    }
                    else
                    {
                        lodBehaviours_[i].enabled = enabledStates_[adjustedLevel_];
                    }
                }
            }

            prevLevel_ = Level;
            prevAdjustedLevel_ = adjustedLevel_;
        }
    }
}
