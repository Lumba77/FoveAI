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

namespace Oculus.Avatar2
{
    public class OvrStateMachine<T> where T : System.Enum
    {
        public T currentState;

        public delegate bool CanEnterDelegate(T nextState);
        public delegate void StateChangedDelegate(T nextState, T prevState);
        public CanEnterDelegate canEnter;
        public StateChangedDelegate onStateChange;
        public bool SetState(T nextState)
        {
            if (canEnter != null && !canEnter(nextState))
            {
                return false;
            }
            T prevState = currentState;
            currentState = nextState;
            if (onStateChange != null)
            {
                onStateChange(currentState, prevState);
            }
            return true;
        }


        public bool IsState(T checkState)
        {
            return Compare(currentState, checkState);
        }

        public bool Compare(T x, T y)
        {
            return EqualityComparer<T>.Default.Equals(x, y);
        }

        public string GetStateString()
        {
            return currentState.ToString();
        }
    }
}
