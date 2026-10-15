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
    public class AvatarLODSkinnableGroup : AvatarLODGroup
    {
        private const string logScope = "AvatarLODSkinnableGroup";
        private const int INVALID_LEVEL = -1;

        private GameObject[] _gameObjects = Array.Empty<GameObject>();

        private List<OvrAvatarSkinnedRenderable>[] _childRenderables = Array.Empty<List<OvrAvatarSkinnedRenderable>>();
        private int _activeAndEnabledLevel = INVALID_LEVEL;

        private int _pendingTransitionLevel = INVALID_LEVEL;
        private readonly HashSet<OvrAvatarSkinnedRenderable> _pendingTransitionIncompleteRenderables =
          new HashSet<OvrAvatarSkinnedRenderable>();

        private byte _animatingLevels;
        internal override byte LevelsWithAnimationUpdateCost => _animatingLevels;

        private void FindAndCacheChildRenderables()
        {
            // Cache new renderables

            // Loop over all GameObjects in GameObjects property
            var numLodObjs = GameObjects.Length;
            Array.Resize(ref _childRenderables, numLodObjs);
            if (numLodObjs == 0)
            {
                return;
            }

            for (int i = 0; i < numLodObjs; i++)
            {
                // Initialize to be a new list if null since GetComponentsInChildren requires non-null (won't create a new one)
                if (_childRenderables[i] == null)
                {
                    _childRenderables[i] = new List<OvrAvatarSkinnedRenderable>();
                }

                var gameObj = GameObjects[i];
                if (gameObj != null)
                {
                    const bool GET_INACTIVE_COMPONENTS = true;
                    gameObj.GetComponentsInChildren(GET_INACTIVE_COMPONENTS, _childRenderables[i]);
                }

                // If no child renderables found, just add as empty array
                // rather than  do null checks in other code
                if (_childRenderables[i] != null)
                {
                    // NOTE: GetComponentsInChildren can return removed but not GC'd objects.
                    // So check via Unity overloaded != operator and remove if "Equals to null"
                    _childRenderables[i].RemoveAllNull();
                }
                else
                {
                    _childRenderables[i] = new List<OvrAvatarSkinnedRenderable>();
                }
            }
        }

        public GameObject[] GameObjects
        {
            get => _gameObjects;
            set
            {
                // Disable and pending transitions and stop listening for transition completion
                // This must be done first, since the renderables will be destroyed
                DisablePendingLevelRenderablesAnimationAndStopListening();
                _pendingTransitionLevel = INVALID_LEVEL;

                _gameObjects = value;
                count = GameObjects.Length;

                // Filter out the skinned renderables
                FindAndCacheChildRenderables();
                ResetLODGroup();
            }
        }

        public override void ResetLODGroup()
        {
            if (!Application.isPlaying) { return; }

            // Not 100% sure what "Reset" means in this context,
            // just using AvatarLODGameObjectGroup as an example

            // Disable and pending transitions and stop listening
            // for transition completion
            DisablePendingLevelRenderablesAnimationAndStopListening();
            _pendingTransitionLevel = INVALID_LEVEL;

            // Deactive all game objects
            foreach (GameObject t in GameObjects)
            {
                if (t == null) { continue; }
                t.SetActive(false);
            }
            _activeAndEnabledLevel = INVALID_LEVEL;

            // Stop all animations
            foreach (var renderablesForLevel in _childRenderables)
            {
                foreach (var r in renderablesForLevel)
                {
                    r.IsAnimationEnabled = false;
                }
            }
            ClearAnimatingLevels();

            UpdateAdjustedLevel();
            UpdateLODGroup();
        }

        public override void UpdateLODGroup()
        {
            base.UpdateLODGroup();

            // If same level that is pending is requested again, do nothing
            bool isRequestedLevelAlreadyPending = adjustedLevel_ == _pendingTransitionLevel;
            if (isRequestedLevelAlreadyPending)
            {
                return;
            }

            // If the requested level is already the level that is "active and enabled" (visible)
            // then the pending transaction just needs to be cancelled
            bool isRequestedLevelAlreadyActive = _activeAndEnabledLevel == adjustedLevel_;
            if (isRequestedLevelAlreadyActive)
            {
                DisablePendingLevelRenderablesAnimationAndStopListening();
                _pendingTransitionLevel = adjustedLevel_;
            }
            else
            {
                // Transition "out of" previous LOD and into a new one (if applicable)
                if (adjustedLevel_ < GameObjects.Length)
                {
                    DisablePendingLevelRenderablesAnimationAndStopListening();

                    _pendingTransitionLevel = adjustedLevel_;

                    EnableSkinnedRenderablesAnimationAndListenForCompletion();
                }
                else
                {
                    OvrAvatarLog.LogWarning("adjustedLevel outside bounds of GameObjects array", logScope, this);
                }
            }
        }

        public override void OnRenderableDisposed(OvrAvatarRenderable disposedRenderable)
        {
            base.OnRenderableDisposed(disposedRenderable);

            if (disposedRenderable is OvrAvatarSkinnedRenderable skinnedRenderable)
            {
                // Remove renderable from cached _childRenderables
                foreach (var renderersForLevel in _childRenderables)
                {
                    // ASSUMPTION: renderersForLevel is never null
                    renderersForLevel.Remove(skinnedRenderable);
                }

                // Remove from pending list (if it is there). If not
                // currently in the pending list, that's not a problem
                if (_pendingTransitionIncompleteRenderables.Count > 0)
                {
                    if (_pendingTransitionIncompleteRenderables.Remove(skinnedRenderable))
                    {
                        // If the renderable was removed, it's possible that it was the last
                        // renderable needed to complete animations before the LOD level
                        // transition could complete, so check for the transition completeness
                        // again
                        if (IsTransitionComplete)
                        {
                            OnLevelTransitionCompleted();
                        }
                    }
                }
            }
        }

        private bool IsTransitionComplete => _pendingTransitionIncompleteRenderables.Count == 0;

        private void DisablePendingLevelRenderablesAnimationAndStopListening()
        {
            // Disable animation for previously pending level (if it was valid)
            if (!IsTransitionComplete)
            {
                // Previously requested transition hasn't completed yet,
                // set all renderables to have animation disabled and stop listening for animation data completion
                RemoveFromAnimatingLevels(_pendingTransitionLevel);
                var renderables = _childRenderables[_pendingTransitionLevel];
                foreach (var r in renderables)
                {
                    r.IsAnimationEnabled = false;
                    r.AnimationDataComplete -= OnRenderableAnimDataComplete;
                }

                _pendingTransitionIncompleteRenderables.Clear();
            }
        }

        private void EnableSkinnedRenderablesAnimationAndListenForCompletion()
        {
            if (IsLevelValid(_pendingTransitionLevel))
            {
                AddToAnimatingLevels(_pendingTransitionLevel);
                var renderables = _childRenderables[_pendingTransitionLevel];
                foreach (var r in renderables)
                {
                    if (r.Visible)
                    {
                        r.IsAnimationEnabled = true;

                        // See if need to listen for data completion or not
                        if (!r.IsAnimationDataCompletelyValid)
                        {
                            _pendingTransitionIncompleteRenderables.Add(r);
                            r.AnimationDataComplete += OnRenderableAnimDataComplete;
                        }
                    }
                }
            }

            // Edge case here where all data is already completely valid and thus, the transition
            // is already complete
            if (IsTransitionComplete)
            {
                OnLevelTransitionCompleted();
            }
        }

        private void OnLevelTransitionCompleted()
        {
            // ASSUMPTION: The pending requests should never be completed
            // for the already active level (this should be caught upstream)
            Debug.Assert(_activeAndEnabledLevel != _pendingTransitionLevel);

            // Deactivate old game object and active new one.
            bool isOldLevelValid = IsLevelValid(_activeAndEnabledLevel);
            if (isOldLevelValid)
            {
                DeactiveGameObjectForLevelAndDisableAnimation(_activeAndEnabledLevel);
            }

            // Enable the new level
            if (IsLevelValid(_pendingTransitionLevel))
            {
                GameObjects[_pendingTransitionLevel].SetActive(true);
            }

            _activeAndEnabledLevel = _pendingTransitionLevel;
        }

        private void DeactiveGameObjectForLevelAndDisableAnimation(int level)
        {
            // ASSUMPTION: caller checks for level validity
            GameObjects[level].SetActive(false);

            // Disable animation for the skinned renderables as well
            RemoveFromAnimatingLevels(level);
            foreach (var r in _childRenderables[level])
            {
                r.IsAnimationEnabled = false;
            }
        }

        private void OnRenderableAnimDataComplete(OvrAvatarSkinnedRenderable sender)
        {
            _pendingTransitionIncompleteRenderables.Remove(sender);
            sender.AnimationDataComplete -= OnRenderableAnimDataComplete;

            // See if all renderers are complete
            if (IsTransitionComplete)
            {
                OnLevelTransitionCompleted();
            }
        }

        private void ClearAnimatingLevels()
        {
            _animatingLevels = 0;
        }

        private void AddToAnimatingLevels(int lev)
        {
            if (IsLevelValid(lev))
            {
                _animatingLevels |= (byte)(1 << lev);
            }
        }

        private void RemoveFromAnimatingLevels(int lev)
        {
            if (IsLevelValid(lev))
            {
                _animatingLevels &= (byte)~(1 << lev);
            }
        }

        private bool IsLevelValid(int level)
        {
            return level != INVALID_LEVEL && level >= 0 && level < GameObjects.Length;
        }

    } // end class AvatarLODSkinnableGroup
} // end namespace
