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

using System.Collections.Generic;

using UnityEngine;

namespace Oculus.Avatar2
{
    public static class UnityExtensions
    {
        public static T? ToNullIfDestroyed<T>(this T obj) where T : UnityEngine.Object
            => obj is null || obj == null ? null : obj;

        public static T? GetComponentOrNull<T>(this GameObject obj) where T : Component
            => obj.GetComponent<T>().ToNullIfDestroyed();

        public static T? GetComponentOrNull<T>(this Component c) where T : Component
            => c.gameObject.GetComponentOrNull<T>();

        public static T GetOrAddComponent<T>(this GameObject obj) where T : Component
            => obj.GetComponentOrNull<T>() ?? obj.AddComponent<T>();
    }

    public static class ListExtensions
    {
        /// <summary>
        /// Insert an item into a sorted list using BinarySearch.
        /// </summary>
        public static void AddSorted<T>(this List<T> list, T item, IComparer<T> comparer)
        {
            int index = list.BinarySearch(item, comparer);
            list.Insert(index < 0 ? ~index : index, item);
        }

        /// <summary>
        /// Removes an item in a sorted list using BinarySearch.
        /// </summary>
        public static bool RemoveSorted<T>(this List<T> list, T item, IComparer<T> comparer)
        {
            int index = list.BinarySearch(item, comparer);
            if (index < 0)
            {
                return false;
            }

            list.RemoveAt(index);
            return true;
        }

        /// <summary>
        /// Insert an item into a sorted list range using BinarySearch.
        /// </summary>
        public static void AddSorted<T>(this List<T> list, int start, int count, T item, IComparer<T> comparer)
        {
            int index = list.BinarySearch(start, count, item, comparer);
            list.Insert(index < 0 ? ~index : index, item);
        }
    }

    public static class FloatExtenstions
    {
        private const float DEFAULT_EPS = 1e-30f;

        public static bool IsApproximatelyZero(this float x, float eps = DEFAULT_EPS)
        {
            return Mathf.Abs(x) <= eps;
        }
    }

    public static class TransformExtensions
    {
        public static Transform? FindChildRecursive(this Transform parent, string name)
        {
            for (int i = 0; i < parent.childCount; i++)
            {
                var child = parent.GetChild(i);
                if (child.name.Contains(name))
                {
                    return child;
                }

                var result = child.FindChildRecursive(name);
                if (result != null)
                {
                    return result;
                }
            }
            return null;
        }
    }
}
