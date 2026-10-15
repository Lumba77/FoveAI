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

using System.Collections;
using System.Collections.Generic;
using UnityEngine;

using Oculus.Avatar2;

namespace Oculus.Avatar2
{
    internal sealed class OvrAvatarResourceTimer
    {
        internal enum AssetLifeTimeStatus
        {
            Created,
            LoadStarted,
            LoadFailed,
            Loaded,
            Unloaded,
            ReadyToRender
        }

        private const string logScope = "ResourceTimers";

        private OvrAvatarResourceLoader parentLoader = null;

        private float _resourceCreatedTime = 0;
        internal float resourceCreatedTime
        {
            get { return _resourceCreatedTime; }
            private set
            {
                _resourceCreatedTime = value;
            }
        }

        private float _resourceLoadStartedTime = 0;
        internal float resourceLoadStartedTime
        {
            get { return _resourceLoadStartedTime; }
            private set
            {
                _resourceLoadStartedTime = value;
            }
        }

        private float _resourceLoadedTime;
        internal float resourceLoadedTime
        {
            get { return _resourceLoadedTime; }
            private set
            {
                _resourceLoadedTime = value;
                if (resourceCreatedTime != 0)
                {
                    float loadingTime = _resourceLoadedTime - resourceCreatedTime;
                    OvrAvatarLog.LogDebug($"Resource {parentLoader.resourceId} asset loading time: {loadingTime}", logScope);
                    OvrAvatarStatsTracker.Instance.TrackLoadDuration(parentLoader.resourceId, loadingTime);
                }
            }
        }


        private float _resourceLoadFailedTime;
        internal float resourceLoadFailedTime
        {
            get { return _resourceLoadFailedTime; }
            private set
            {
                _resourceLoadFailedTime = value;
                if (resourceCreatedTime != 0)
                {
                    float loadingTime = _resourceLoadFailedTime - resourceCreatedTime;
                    OvrAvatarLog.LogDebug($"Resource {parentLoader.resourceId} had a failure loading after: {loadingTime}", logScope);
                    OvrAvatarStatsTracker.Instance.TrackFailedDuration(parentLoader.resourceId, loadingTime);
                }
            }
        }

        private float _resourceReadyToRenderTime;
        internal float resourceReadyToRenderTime
        {
            get { return _resourceReadyToRenderTime; }
            private set
            {
                _resourceReadyToRenderTime = value;
                if (resourceCreatedTime != 0)
                {
                    float totalTime = _resourceReadyToRenderTime - resourceCreatedTime;
                    OvrAvatarLog.LogDebug($"Resource {parentLoader.resourceId} total creation time: {totalTime}", logScope);
                    OvrAvatarStatsTracker.Instance.TrackReadyDuration(parentLoader.resourceId, totalTime);
                }
            }
        }
        private float _resourceUnloadedTime;
        internal float resourceUnloadedTime
        {
            get { return _resourceUnloadedTime; }
            private set
            {
                _resourceUnloadedTime = value;
                if (resourceCreatedTime != 0)
                {
                    float totalTime = _resourceUnloadedTime - resourceCreatedTime;
                    OvrAvatarLog.LogDebug($"Resource {parentLoader.resourceId} unloaded after a lifetime of {totalTime}", logScope);
                }
            }
        }

        // For now we're tracking these status changes from direct calls to this function
        // but in the future we should recieve asynchronous callbacks from the SDK.
        internal void TrackStatusEvent(AssetLifeTimeStatus status)
        {
            float currentTime = Time.realtimeSinceStartup;

            switch (status)
            {
                case AssetLifeTimeStatus.LoadFailed:
                {
                    resourceLoadFailedTime = currentTime;
                }
                break;
                case AssetLifeTimeStatus.Loaded:
                {
                    resourceLoadedTime = currentTime;
                }
                break;
                case AssetLifeTimeStatus.Unloaded:
                {
                    resourceUnloadedTime = currentTime;
                }
                break;
                case AssetLifeTimeStatus.Created:
                {
                    resourceCreatedTime = currentTime;
                }
                break;
                case AssetLifeTimeStatus.LoadStarted:
                {
                    resourceLoadStartedTime = currentTime;
                }
                break;
                case AssetLifeTimeStatus.ReadyToRender:
                {
                    resourceReadyToRenderTime = currentTime;
                }
                break;

            }
        }

        private OvrAvatarResourceTimer() { }
        public OvrAvatarResourceTimer(OvrAvatarResourceLoader loader)
        {
            parentLoader = loader;
        }
    }

}
