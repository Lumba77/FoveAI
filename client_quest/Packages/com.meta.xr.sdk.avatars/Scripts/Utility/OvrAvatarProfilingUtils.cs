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

using Unity.Profiling;

namespace Oculus.Avatar2
{
    public static class OvrAvatarProfilingUtils
    {
        public sealed class Categories
        {
            // Animation related operations
            public readonly ProfilerCategory Animation;
            // Skinning related operations
            public readonly ProfilerCategory Skinning;
            // Streaming (Networking) operations
            public readonly ProfilerCategory Streaming;
            // Loading related operations
            public readonly ProfilerCategory Loading;
            // Callback from AvatarSDK Native code to AvatarSDK C# Code
            public readonly ProfilerCategory NativeCallback;
            // Callback from AvatarSDK C# code to Application C# Code
            public readonly ProfilerCategory AppCallback;

            public Categories()
            {
                Animation = new ProfilerCategory("MetaAvatarSDK::Animation", ProfilerCategoryColor.Animation);
                Skinning = new ProfilerCategory("MetaAvatarSDK::Skinning", ProfilerCategoryColor.Render);
                Streaming = new ProfilerCategory("MetaAvatarSDK::Streaming", ProfilerCategoryColor.Other);
                Loading = new ProfilerCategory("MetaAvatarSDK::Loading", ProfilerCategoryColor.Memory);
                NativeCallback = new ProfilerCategory("MetaAvatarSDK::NativeCallback", ProfilerCategoryColor.Internal);
                AppCallback = new ProfilerCategory("MetaAvatarSDK::AppCallback", ProfilerCategoryColor.Scripts);
            }
        }

        private static Categories s_avatarProfilerCategories = null;

        public static Categories AvatarCategories => s_avatarProfilerCategories ??= new Categories();
    }
}
